/**
 * 命局档案与命卦校验（前端共享模块）
 * 档案 id 与归属令牌是同一枚字符串：服务端会校验两者一致，防止冒写他人档案。
 */
import { api, qs } from './client'
import { getOwnerToken } from './owner'
import type { MingjuBaseline, MingjuCheck, Tier, TierInfo } from './types'

const TIER_KEY = 'mingju_tier'

/* ---------- 档位（累积式：S 只出 S，M=S+M，L=S+M+L） ---------- */

export function getTier(): Tier {
  try {
    const t = localStorage.getItem(TIER_KEY)
    return t === 'M' || t === 'L' ? t : 'S'
  } catch {
    return 'S'
  }
}

export function setTier(t: Tier): void {
  try { localStorage.setItem(TIER_KEY, t) } catch { /* 忽略 */ }
}

/* ---------- 档案 ---------- */

export function getProfileId(): string {
  return getOwnerToken()
}

export interface BirthInput {
  year: number
  month: number
  day: number
  hour: number
  minute: number
  gender: number          // 1=男 0=女
  calendar: 'solar' | 'lunar'
  leap_month?: boolean
  dst?: boolean
  true_solar?: boolean
  longitude?: number
}

/**
 * 档案返回结构（按后端真实响应）：
 *   baseline.solar/lunar/gender/day_master 在最外层，
 *   而喜用 F / 忌神 J / 调候 T0 在 baseline.mingju 下面（容易读错，这里一次写清）。
 */
export interface MingjuProfile {
  id: string
  birth: BirthInput
  baseline: {
    solar?: string
    lunar?: string
    gender?: string
    day_master?: { gan: string; wuxing: string; yinyang: string }
    mingju?: MingjuBaseline
    tiaohou?: { yongshen: string; note: string }
    geju?: { name: string; basis: string }
    shensha?: string[]
  }
  created_at?: string
  updated_at?: string
}

/** 命局摘要：三页共用同一份读法，避免各写各的又读错层级 */
export function profileSummary(p: MingjuProfile | null) {
  const b = p?.baseline
  const m = b?.mingju
  return {
    solar: b?.solar || '',
    lunar: b?.lunar || '',
    gender: b?.gender || '',
    dayMaster: b?.day_master?.gan || '',
    dayMasterWx: b?.day_master?.wuxing || '',
    F: m?.F || [],
    J: m?.J || [],
    T0: m?.T0 || m?.t0_list || [],
    tiao: b?.tiaohou?.yongshen || '',
    tier: m?.tier || '',
    geju: b?.geju?.name || '',
    tally: m?.wuxing_tally || null,
    shensha: b?.shensha || [],
  }
}

/** 读档案：没有档案返回 null（404 是正常状态，不是错误） */
export async function getProfile(): Promise<MingjuProfile | null> {
  try {
    return await api.get<MingjuProfile>(`/api/mingju/profile${qs({ id: getProfileId() })}`)
  } catch (e) {
    const status = (e as { status?: number }).status
    if (status === 404) return null
    throw e
  }
}

/** 存档案：服务端返回算好的基线（喜用/忌神/调候/格局等）。除年月日外都可省略 */
export type BirthInputPartial = Pick<BirthInput, 'year' | 'month' | 'day'> & Partial<BirthInput>

export async function saveProfile(birth: BirthInputPartial): Promise<{ id: string; baseline: MingjuBaseline }> {
  const defaults: Omit<BirthInput, 'year' | 'month' | 'day'> = {
    hour: 0, minute: 0, gender: 1, calendar: 'solar',
    leap_month: false, dst: false, true_solar: false, longitude: 120,
  }
  return api.post('/api/mingju/profile', { id: getProfileId(), ...defaults, ...birth })
}

export async function deleteProfile(): Promise<void> {
  await api.del(`/api/mingju/profile${qs({ id: getProfileId() })}`)
}

/* ---------- 命卦校验 ---------- */

export interface CheckInput {
  gua?: { ti_wuxing?: string; yong_wuxing?: string; relation?: string }
  remedy?: Record<string, unknown>
  question?: string
  tier_override?: string
  month_wx?: string
  day_zhi?: string
  /** 起卦时辰地支（应期加权旺衰用；从 gua.yingqi 回传） */
  hour_zhi?: string
  /** 应期起算日 ISO（回传保证「按处方栏」与「按卦栏」同一窗口） */
  yingqi_start?: string
  /** 按卦栏的应期日期（用于生成「实际哪天发生」的断言） */
  yingqi_dates?: string[]
  source?: string
}

/** 处方五行过命局三道门；没有档案也能调（只做卦侧校验） */
export async function checkMingju(input: CheckInput): Promise<MingjuCheck> {
  return api.post<MingjuCheck>('/api/mingju/check', {
    profile_id: getProfileId(),
    tier_override: getTier(),
    ...input,
  })
}

export type { MingjuCheck, TierInfo }

/* ---------- 典籍原文核对 ---------- */

export interface QuoteData {
  key: string
  book: string
  loc: string
  /** 库里有原文就返回原文；没收录返回 null（原文待录，不代拟） */
  text: string | null
  note: string
}

/** 按出处键批量取原文（支持前缀归并）。
 *  模块级缓存（2026-10 补：旧前端有 quoteCache，新端此前每点一次出处签都打一次接口） */
const _quoteCache = new Map<string, QuoteData>()
export async function fetchQuotes(keys: string[]): Promise<Record<string, QuoteData>> {
  const miss = keys.filter((k) => !_quoteCache.has(k))
  if (miss.length) {
    try {
      const res = await api.post<{ quotes: Record<string, QuoteData> }>('/api/mingju/quotes', { keys: miss })
      for (const [k, v] of Object.entries(res.quotes || {})) _quoteCache.set(k, v)
    } catch {
      /* 取不到就按未命中返回，不缓存失败 */
    }
  }
  const out: Record<string, QuoteData> = {}
  for (const k of keys) {
    const hit = _quoteCache.get(k)
    if (hit) out[k] = hit
  }
  return out
}

/* ============================================================
   校验台账（check_log）
   ------------------------------------------------------------
   一行 = 一次命卦校验（kind='check'）或一次八字排盘（kind='bazi'）。
   三个端点各自管一件事，别混：
     POST /api/mingju/bazi/log   排盘留痕（写一行 kind=bazi）
     GET  /api/mingju/logs       台账列表（有哪些次）
     POST /api/mingju/feedback   整案级反馈：应验 / 未验 / 还没结果
   第四个端点 GET /api/mingju/logs/flow（回看某一次的整张流动五行表）站长说不接，
   故这里不提供——要看整表只有当次校验响应里的 flow。
   ============================================================ */

/**
 * 台账一行。后端 decision_log.recent 用 PRAGMA 现取列名（这张表是只增不改地加列的），
 * 所以这里只声明前端真正用到的字段，其余走索引签名，不把库表结构抄死在前端。
 * 后端**刻意不返回 flow_json**（整张流动表一张几 KB，列表一次 60 行）。
 */
export interface LogRow {
  id: number
  ts: string
  kind: string            // 'check' 校验 ｜ 'bazi' 八字排盘
  question: string
  net: string
  decision: string
  tier: string
  R: string
  final_R: string
  rules_version: string
  weights_version: string
  /** 整案级反馈：应验 / 未验 / 还没结果；未标记为空串 */
  outcome: string
  claims_json: string
  extra_json: string
  [k: string]: unknown
}

/** 台账列表（最新在前，只返回自己的）。limit 后端夹在 1–200 */
export async function fetchLogs(limit = 60): Promise<LogRow[]> {
  const res = await api.get<{ logs: LogRow[] }>(`/api/mingju/logs${qs({ limit })}`)
  return res.logs || []
}

/**
 * 八字排盘留痕：把这次排盘写进台账（kind=bazi），关页不丢、可事后回看。
 * **尽力而为**——失败不阻塞排盘主流程（旧前端同一约定）。
 * 服务端 require_owner + 限流 60/分；快照超 20KB 会截断。
 */
export async function logBaziPaipan(summary: Record<string, unknown>, question = ''): Promise<boolean> {
  try {
    await api.post('/api/mingju/bazi/log', { question, summary })
    return true
  } catch {
    return false
  }
}

/** 整案级反馈只接受这三个值（后端 decision_log.set_feedback 会拒绝其他值） */
export const CASE_OUTCOMES = ['应验', '未验', '还没结果'] as const
export type CaseOutcome = (typeof CASE_OUTCOMES)[number]

/**
 * 整案级反馈：写 check_log.outcome（只能改自己的那一行）。
 * 与断言级（POST /api/feedback/claim，五档）不是一回事：
 *   断言级标的是"某一条可检验的断言"，整案级标的是"这件事整体后来如何"。
 * 台账列表里显示的是这一栏（outcome），所以两者都要有。
 * actualDate 可选：所问之事实际发生的日期，后端应期分析靠它算偏差几天（选填）。
 */
export async function postCaseOutcome(logId: number, outcome: CaseOutcome, actualDate = ''): Promise<boolean> {
  try {
    await api.post('/api/mingju/feedback', { log_id: logId, outcome, actual_date: actualDate })
    return true
  } catch {
    return false
  }
}
