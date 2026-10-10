/**
 * SSE 流式读取：后端四个解卦端点都返回 text/event-stream，
 * 每行形如 `data: {"type": "...", ...}`，事件之间空行分隔。
 *
 * 解析要点（与后端 _degrade_event / _truncated_event / _verify_event 对齐）：
 *  · 按空行切帧，最后一段留在缓冲里等下一个 chunk；
 *  · 一帧可能有多行 data:（规范允许），拼起来再 JSON.parse；
 *  · 解析失败**不抛错**——旁路事件（回检）不能影响正文流。
 */

export interface SseMessage {
  type: string
  [k: string]: unknown
}

import { ApiError, friendlyError } from './client'

export async function postStream(
  url: string,
  body: unknown,
  onEvent: (msg: SseMessage) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
      signal,
    })
  } catch (e) {
    if ((e as { name?: string }).name === 'AbortError') throw e
    throw new Error(friendlyError(e))
  }
  if (!res.ok) {
    let detail = `请求失败 (${res.status})`
    try {
      const data = await res.json()
      const d = (data as { detail?: unknown }).detail
      if (typeof d === 'string') detail = d
    } catch { /* 保留默认文案 */ }
    throw new Error(res.status >= 500 ? friendlyError(new ApiError(detail, res.status)) : detail)
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error('无法读取响应流')

  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      const payload = frame
        .split('\n')
        .filter((l) => l.startsWith('data:'))
        .map((l) => l.slice(5).trim())
        .join('')
      if (!payload) continue
      try {
        onEvent(JSON.parse(payload) as SseMessage)
      } catch { /* 单帧坏了不影响整条流 */ }
    }
  }
}
