/**
 * 语音识别（ASR）
 * 服务端识别优先（/api/asr/transcribe，按秒计费、需要归属令牌）；
 * 服务端未配置（503）时前端回退浏览器自带识别。
 */
import { api } from './client'

export interface AsrStatus {
  configured: boolean
  provider?: string
  base_url?: string
  model?: string
}

export async function asrStatus(): Promise<AsrStatus> {
  try {
    return await api.get<AsrStatus>('/api/asr/status')
  } catch {
    return { configured: false }
  }
}

/** 上传录音并识别：字段名固定为 file（后端契约） */
export async function transcribe(blob: Blob, filename = 'speech.webm'): Promise<{ text: string; model?: string; ms?: number }> {
  const form = new FormData()
  form.append('file', blob, filename)
  const res = await fetch('/api/asr/transcribe', { method: 'POST', body: form })
  if (!res.ok) {
    let detail = `识别失败 (${res.status})`
    try {
      const data = await res.json()
      if (typeof data?.detail === 'string') detail = data.detail
    } catch { /* 保留默认文案 */ }
    const err = new Error(detail) as Error & { status?: number }
    err.status = res.status
    throw err
  }
  return res.json()
}
