/**
 * 请求封装：JSON 读写 + 后端 detail 错误提取。
 * 归属令牌由 owner.ts 的 fetch 拦截统一注入，这里不再重复处理。
 */

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** 后端根本没起来时地址栏不会告诉你原因，这里把它讲清楚 */
export const BACKEND_DOWN_HINT =
  '连不上后端服务：请确认后端已启动（在 backend 目录执行 '
  + 'python -m uvicorn main:app --host 127.0.0.1 --port 8000 --no-proxy-headers）'

/** fetch 抛出的网络错误（TypeError）与 5xx 一律换成能看懂的话 */
export function friendlyError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status >= 500 && /Internal Server Error|请求失败 \(5\d\d\)/.test(e.message)) {
      return `${BACKEND_DOWN_HINT}（后端返回 ${e.status}）`
    }
    return e.message
  }
  const msg = (e as Error)?.message || String(e)
  if (/Failed to fetch|NetworkError|Load failed|ERR_CONNECTION|fetch failed/i.test(msg)) {
    return BACKEND_DOWN_HINT
  }
  return msg
}

/** 把后端返回的错误体（FastAPI 的 detail，可能是字符串或校验数组）转成人话 */
async function errorText(res: Response): Promise<string> {
  try {
    const data = await res.json()
    const d = (data as { detail?: unknown }).detail
    if (typeof d === 'string') return d
    if (Array.isArray(d) && d.length) {
      const first = d[0] as { msg?: string; loc?: unknown[] }
      const where = Array.isArray(first.loc) ? first.loc.slice(1).join('.') : ''
      return `${where ? where + '：' : ''}${first.msg || '请求参数有误'}`
    }
    return `请求失败 (${res.status})`
  } catch {
    return `请求失败 (${res.status})`
  }
}

async function request<T>(method: string, url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (e) {
    if ((e as { name?: string }).name === 'AbortError') throw e
    throw new ApiError(friendlyError(e), 0)
  }
  if (!res.ok) throw new ApiError(await errorText(res), res.status)
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export const api = {
  get: <T>(url: string, signal?: AbortSignal) => request<T>('GET', url, undefined, signal),
  post: <T>(url: string, body?: unknown, signal?: AbortSignal) => request<T>('POST', url, body ?? {}, signal),
  patch: <T>(url: string, body?: unknown, signal?: AbortSignal) => request<T>('PATCH', url, body ?? {}, signal),
  del: <T>(url: string, signal?: AbortSignal) => request<T>('DELETE', url, undefined, signal),
}

/* ---------- 只读 GET 的缓存 + 并发去重 ----------
   用途：同一份只读数据被反复要（最典型的是术语表——每切一次分类就重取一遍）。
   两条规则：
     1. 同一个 URL 正在请求中 → 后来的调用共用同一个 Promise，不发第二个请求；
     2. 拿到结果后在 TTL 内直接用缓存（刷新/失败不留缓存）。
   只给"公共只读"的接口用（术语表、出处原文），不带缓存的接口一律走 api.get。 */
interface CacheEntry { at: number; data: unknown }
const getCache = new Map<string, CacheEntry>()
const getInflight = new Map<string, Promise<unknown>>()

export function cachedGet<T>(url: string, ttlMs = 5 * 60_000): Promise<T> {
  const hit = getCache.get(url)
  if (hit && Date.now() - hit.at < ttlMs) return Promise.resolve(hit.data as T)
  const running = getInflight.get(url)
  if (running) return running as Promise<T>
  const p = api.get<T>(url)
    .then((data) => {
      getCache.set(url, { at: Date.now(), data })
      return data
    })
    .finally(() => { getInflight.delete(url) })
  getInflight.set(url, p)
  return p
}

/** 查询串拼装：只拼有值的键，避免 ?id=&kind= 这种噪声 */
export function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}
