/**
 * 归属令牌（跟旧前端同一套约定，localStorage 键名保持一致）
 * ============================================================
 * 服务端用 X-Owner-Token 头认人：令牌即账户，不注册、不登录。
 * 三条规则与后端约定一致：
 *   1. 新访客生成一枚随机令牌（crypto.randomUUID，退化为 getRandomValues）；
 *   2. 老访客沿用既有的 mingju_profile_id，未丢档案与记录；
 *   3. 令牌丢了等于数据丢了 —— 加密导出/导入是唯一的搬家手段。
 *
 * 注意：localStorage 按"源"隔离，而源包含端口。
 * 所以 localhost:3000（旧前端）与 localhost:3001（本前端）各自持有一枚令牌，
 * 记录与命局档案互不相通。要让两边看到同一批数据，把旧前端的令牌复制过来即可
 * （见 copyTokenFrom 的说明；正式部署同域名同端口则不存在这个问题）。
 */
const OWNER_KEY = 'bagua_owner'
const LEGACY_PID_KEY = 'mingju_profile_id'

function newToken(): string {
  const c = globalThis.crypto
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  if (c && typeof c.getRandomValues === 'function') {
    const b = new Uint8Array(16)
    c.getRandomValues(b)
    return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
  }
  return 'tok-' + Math.random().toString(36).slice(2) + Date.now().toString(36)
}

/** 会话内缓存：localStorage 不可用（隐私模式）时至少保证本次会话自洽 */
let sessionToken = ''

export function getOwnerToken(): string {
  let tok = ''
  try { tok = localStorage.getItem(OWNER_KEY) || '' } catch { /* 隐私模式 */ }
  if (tok) { sessionToken = tok; return tok }
  if (sessionToken) return sessionToken
  let legacy = ''
  try { legacy = localStorage.getItem(LEGACY_PID_KEY) || '' } catch { /* 同上 */ }
  tok = legacy || newToken()
  sessionToken = tok
  try {
    localStorage.setItem(OWNER_KEY, tok)
    if (!legacy) localStorage.setItem(LEGACY_PID_KEY, tok)
  } catch { /* 写不进去也不影响本次会话 */ }
  return tok
}

/** 覆盖当前令牌（用于把旧前端的令牌搬过来）；返回是否写入成功 */
export function setOwnerToken(token: string): boolean {
  const t = (token || '').trim()
  if (!t) return false
  sessionToken = t
  try {
    localStorage.setItem(OWNER_KEY, t)
    localStorage.setItem(LEGACY_PID_KEY, t)
    return true
  } catch {
    return false
  }
}

/**
 * 让令牌活得久一点：持久化存储 + iOS 加主屏
 * ============================================================
 * 本站用 localStorage 里的令牌当账户，于是"令牌能活多久"直接等于"数据能留多久"。
 *   1. 浏览器默认是 best-effort 存储，空间紧张时可以不打招呼就清掉；
 *      navigator.storage.persist() 可申请豁免（Firefox 会弹窗询问，Chromium 按交互历史自动批准）。
 *   2. iOS Safari 更硬：7 天无用户交互即删除全部 script-writable 存储（WebKit 官方行为），
 *      persist() 在 Safari 上未实现、拦不住它——唯一的豁免是"添加到主屏幕"。
 * 所以 persist() 与加主屏引导是两件互补的事，缺一个都堵不住。
 */
const PERSIST_KEY = 'bagua_persist_state'
const HINT_KEY = 'bagua_a2hs_dismissed'

/** 申请持久化存储（幂等，失败静默：这只是"尽量别被清"，不是功能前置条件） */
export async function requestPersistentStorage(): Promise<boolean> {
  try {
    if (!navigator.storage?.persist) return false
    if (await navigator.storage.persisted?.()) return true
    const ok = await navigator.storage.persist()
    try { localStorage.setItem(PERSIST_KEY, ok ? 'granted' : 'denied') } catch { /* 忽略 */ }
    return ok
  } catch {
    return false
  }
}

/** 是否已装成 web app */
export function isStandalone(): boolean {
  try {
    if ((navigator as unknown as { standalone?: boolean }).standalone) return true
    return window.matchMedia?.('(display-mode: standalone)')?.matches === true
      || window.matchMedia?.('(display-mode: fullscreen)')?.matches === true
  } catch {
    return false
  }
}

function isIos(): boolean {
  const ua = navigator.userAgent || ''
  return /iPad|iPhone|iPod/.test(ua)
    || (/Macintosh/.test(ua) && (navigator.maxTouchPoints || 0) > 1)
}

/**
 * 是否该提示"添加到主屏幕"。
 * 只在确实受影响的地方提示：iOS + Safari 里打开（非已装 App）且用户没关过；
 * 桌面端不提示（那边 persist() 够用，提示了只是噪音）。
 */
export function shouldSuggestAddToHomeScreen(): boolean {
  try {
    if (!isIos() || isStandalone()) return false
    return localStorage.getItem(HINT_KEY) !== '1'
  } catch {
    return false
  }
}

export function dismissAddToHomeScreenHint(): void {
  try { localStorage.setItem(HINT_KEY, '1') } catch { /* 忽略 */ }
}

/**
 * 给所有同源 /api 请求自动加上归属令牌。
 * 用统一拦截而不是逐处手写：调用点一多，漏一处就是"看不到自己的数据"。
 */
export function installOwnerHeader(): void {
  const g = globalThis as Record<string, unknown>
  if (g.__baijinOwnerHeader) return
  g.__baijinOwnerHeader = true
  const orig = globalThis.fetch?.bind(globalThis)
  if (!orig) return
  globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string'
      ? input
      : (input instanceof URL ? input.toString() : input.url)
    const sameOrigin = url.startsWith('/') || url.startsWith(location.origin)
    if (!sameOrigin || !url.includes('/api/')) return orig(input, init)
    const headers = new Headers(
      init?.headers
      || (typeof input === 'object' && 'headers' in input ? (input as Request).headers : undefined),
    )
    if (!headers.has('X-Owner-Token')) headers.set('X-Owner-Token', getOwnerToken())
    return orig(input, { ...(init || {}), headers })
  }
}
