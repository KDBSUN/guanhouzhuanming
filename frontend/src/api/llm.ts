/**
 * 自带模型 key 与每日免费额度
 * ============================================================
 * 与旧前端的 llm/llmStore.ts 同一套后端接口与同一套规则：
 *   ① 地址由服务端名单写死（防本站服务器被当任意地址转发器），用户只选厂商、填 key、改模型名；
 *   ② key 只存在本设备浏览器（localStorage），服务器只在当次请求内存里使用，不落盘、不写日志；
 *   ③ 没配 key 就不带 llm 字段，走"签到 + 每天 3 次免费"（按天算、不累加）。
 *
 * localStorage 键名与旧前端**刻意相同**（bagua_llm_setting）：两个前端对着同一个后端、
 * 同一个 origin，用户在哪个前端填的 key 都该互相看得见。
 */
import { api, friendlyError } from './client'

export interface LlmProvider {
  id: string
  label: string
  note: string
  recommended: boolean
  default_model: string
  models: string[]
  key_url: string
}

export interface LlmSetting {
  provider: string
  api_key: string
  model: string
}

export interface FreeQuota {
  day: string
  signed: boolean
  free_limit: number
  free_used: number
  free_left: number
  ip_limit: number
  ip_used: number
  site_used: number
  site_hard: number
  resets_at: string
  byok_hint?: string
}

const KEY = 'bagua_llm_setting'

export function getLlmSetting(): LlmSetting | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const s = JSON.parse(raw) as LlmSetting
    if (!s || !s.provider || !s.api_key) return null
    return { provider: s.provider, api_key: s.api_key, model: s.model || '' }
  } catch {
    return null
  }
}

export function saveLlmSetting(s: LlmSetting | null): void {
  try {
    if (!s || !s.provider || !s.api_key) localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, JSON.stringify(s))
  } catch {
    /* 隐私模式下写不进去：功能降级为本次会话有效，不该因此报错 */
  }
}

/** 解卦请求要带的字段；没配 key 时返回空对象（什么都不带 = 走免费额度） */
export function llmPayload(): Record<string, unknown> {
  const s = getLlmSetting()
  if (!s) return {}
  return { llm: { provider: s.provider, api_key: s.api_key, model: s.model } }
}

export async function fetchProviders(): Promise<{
  providers: LlmProvider[]; free_per_day: number; note: string
} | null> {
  try {
    return await api.get('/api/llm/providers')
  } catch {
    return null
  }
}

export async function testLlm(s: LlmSetting): Promise<{ ok: boolean; message: string }> {
  try {
    const data = await api.post<{ ok: boolean; message: string }>('/api/llm/test', s)
    return { ok: !!data.ok, message: data.message || '' }
  } catch (e) {
    return { ok: false, message: friendlyError(e) }
  }
}

/**
 * 站长自用：取回**本站 .env 里那把 key**，一键导入成"自带 key"。
 *
 * 为什么需要它：站点 key 走的是"签到后每天 3 次"的免费路径，站长要反复解卦检验内容
 * 时会被这个额度卡住；而让站长手工把 .env 里的 key 复制粘贴到设置页，恰恰是最容易
 * 把 key 落进剪贴板/聊天窗口的做法。
 *
 * 边界：需要 `X-Admin-Token`（后端 require_admin；未配置 ADMIN_TOKEN 时端点 503 关闭），
 * 因此**普通访客拿不到**。取回的 key 与手工粘贴走完全相同的保存路径（localStorage）。
 */
export async function fetchSiteKey(adminToken: string): Promise<{
  ok: boolean; provider?: string; api_key?: string; model?: string; label?: string; message: string
}> {
  try {
    const res = await fetch('/api/llm/site-key', {
      headers: { 'X-Admin-Token': (adminToken || '').trim() },
      cache: 'no-store',
    })
    const data = await res.json().catch(() => null)
    if (!res.ok) return { ok: false, message: data?.detail || `请求失败 (${res.status})` }
    if (!data?.api_key) return { ok: false, message: '站点未返回可用 key' }
    return { ok: true, provider: data.provider, api_key: data.api_key,
             model: data.model || '', label: data.provider_label || data.provider || '', message: '' }
  } catch (e) {
    return { ok: false, message: friendlyError(e) }
  }
}

/** 打码显示：只留末四位用于辨认，**不回显完整 key**（本页保存后不再显示原值）。 */
export function maskKey(k: string): string {
  const s = (k || '').trim()
  if (!s) return ''
  return s.length <= 4 ? '••••' : '••••••••' + s.slice(-4)
}

export async function fetchQuota(): Promise<FreeQuota | null> {
  try {
    return await api.get('/api/quota/status')
  } catch {
    return null
  }
}

/** 今日签到（幂等）。签到后当日 3 次免费 AI 解卦；跨天不累加。 */
export async function signinToday(): Promise<FreeQuota | null> {
  try {
    return await api.post('/api/quota/signin')
  } catch {
    return null
  }
}
