/**
 * 公测反馈接口（claim 级）
 *   GET  /api/feedback/recent?limit=   最近若干次校验（含断言与已有反馈）
 *   GET  /api/feedback/claims?log_id=  单次校验的断言清单
 *   POST /api/feedback/claim           逐条断言反馈（五档）
 *   POST /api/feedback/claim/receipt   领一枚回执码（只对这一条断言有效的窄凭证）
 *   GET  /api/feedback/claim?receipt=  凭回执码读这一条断言（不需要归属令牌）
 *   POST /api/feedback/note            自由留言（可附联系方式，会邮件通知站长）
 *   GET  /api/feedback/calibration     校准台账（边界样本 + 待批提案 + 护栏）
 */
import { api, qs } from './client'

export const VERDICTS = ['应验', '未验', '反向', '无法判定', '未观察'] as const
export type Verdict = (typeof VERDICTS)[number]

export interface Claim {
  id: string
  type: string          // 裁决 / 风险 / 岁运 / 择日 / 关系 / 建议
  text: string
  rule: string
  params: string[]
  verifiability: string
  since: string
  until: string
  src: string
}

export interface FeedbackItem {
  log_id: number
  ts: string
  question: string
  net: string
  decision: string
  claims: Claim[]
  feedback: Record<string, string>
  outcome: string
}

export interface CalibrationView {
  proposals: {
    id: number; ts: string; param: string; old_value: number; new_value: number
    n_samples: number; flip_rate: number; status: string; note: string
  }[]
  boundary: { param: string; side: string; n: number; threshold: number }[]
  guardrails: Record<string, number>
}

export async function fetchFeedbackRecent(limit = 5): Promise<FeedbackItem[]> {
  try {
    const data = await api.get<{ items: FeedbackItem[] }>(`/api/feedback/recent${qs({ limit })}`)
    return Array.isArray(data.items) ? data.items : []
  } catch {
    return []
  }
}

export async function fetchClaimFeedback(logId: number): Promise<{ claims: Claim[]; feedback: Record<string, string> }> {
  try {
    const data = await api.get<{ claims: Claim[]; feedback: Record<string, string> }>(
      `/api/feedback/claims${qs({ log_id: logId })}`)
    return { claims: data.claims || [], feedback: data.feedback || {} }
  } catch {
    return { claims: [], feedback: {} }
  }
}

/** 逐条反馈。带 receipt 时归属与目标断言都由服务端从回执行取，log_id/claim_id 被忽略。 */
export async function postClaimVerdict(
  logId: number, claimId: string, verdict: Verdict | string, note = '', receipt = '',
): Promise<{ ok: boolean; mailed: boolean }> {
  try {
    const r = await api.post<{ ok: boolean; mailed?: boolean }>('/api/feedback/claim',
      { log_id: logId, claim_id: claimId, verdict, note, receipt })
    return { ok: true, mailed: !!r?.mailed }
  } catch {
    return { ok: false, mailed: false }
  }
}

export async function postBetaNote(
  text: string, contact = '', logId = 0, title = '',
): Promise<{ ok: boolean; mailed: boolean }> {
  try {
    const r = await api.post<{ ok: boolean; mailed?: boolean }>('/api/feedback/note',
      { text, contact, log_id: logId, title })
    return { ok: true, mailed: !!r?.mailed }
  } catch {
    return { ok: false, mailed: false }
  }
}

export async function fetchCalibration(): Promise<CalibrationView | null> {
  try {
    return await api.get<CalibrationView>('/api/feedback/calibration')
  } catch {
    return null
  }
}

/* ---------- 回执码与日历提醒 ---------- */

export interface ReceiptClaim {
  claim: Claim
  verdicts: string[]
  feedback: string
}

export async function issueReceipt(logId: number, claimId: string): Promise<string> {
  try {
    const r = await api.post<{ receipt: string }>('/api/feedback/claim/receipt',
      { log_id: logId, claim_id: claimId })
    return r?.receipt || ''
  } catch {
    return ''
  }
}

/** 凭回执码读这一条断言（回执链接的落地页数据源；不需要归属令牌） */
export async function fetchClaimByReceipt(receipt: string): Promise<ReceiptClaim | null> {
  try {
    return await api.get<ReceiptClaim>(`/api/feedback/claim${qs({ receipt })}`)
  } catch {
    return null
  }
}

/** 从地址里取回执码（兼容 `#/feedback?r=xxx` 与 `#/feedback&r=xxx`） */
export function receiptFromLocation(): string {
  const h = location.hash || ''
  const m = h.match(/[?&]r=([A-Za-z0-9_-]+)/)
  return m ? m[1] : ''
}

export function receiptLink(receipt: string): string {
  return `${location.origin}${location.pathname}#/feedback?r=${receipt}`
}

function icsEscape(s: string): string {
  return (s || '').replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,')
    .replace(/\r?\n/g, '\\n')
}

function icsDate(iso: string): string {
  const d = iso ? new Date(`${iso}T09:00:00`) : new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`
}

/**
 * 一条断言的日历事件。提醒取验证窗口末端（该回头看应验没有的时候），
 * 并在前一天再响一次——当天才想起往往已经错过复盘时机。
 */
export function claimIcs(opts: { claim: Claim; question: string; receipt: string }): string {
  const { claim, question, receipt } = opts
  const day = icsDate(claim.until)
  const uid = `claim-${receipt || claim.id}-${claim.until}@yizhan`
  const desc = [
    question ? `所问：${question}` : '',
    `断言：${claim.text}`,
    `归属规则：${claim.rule}（${claim.verifiability}）`,
    claim.src ? `书证：${claim.src}` : '',
    '',
    '到期后点此直接作答（无需登录；换设备也有效）：',
    receiptLink(receipt),
  ].filter(Boolean).join('\n')
  const stamp = `${new Date().toISOString().replace(/[-:]/g, '').split('.')[0]}Z`
  return [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//yizhan//claim-verify//CN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    'BEGIN:VEVENT',
    `UID:${uid}`,
    `DTSTAMP:${stamp}`,
    `DTSTART;VALUE=DATE:${day}`,
    `SUMMARY:${icsEscape(`验证应验：${claim.text.slice(0, 40)}`)}`,
    `DESCRIPTION:${icsEscape(desc)}`,
    `URL:${receiptLink(receipt)}`,
    'BEGIN:VALARM',
    'TRIGGER:-P1D',
    'ACTION:DISPLAY',
    `DESCRIPTION:${icsEscape(`明天到期：${claim.text.slice(0, 40)}`)}`,
    'END:VALARM',
    'END:VEVENT',
    'END:VCALENDAR',
  ].join('\r\n')
}

export function downloadIcs(filename: string, text: string): void {
  // 加 BOM：Windows 日历/Outlook 对无 BOM 的 UTF-8 中文常乱码
  const blob = new Blob([`\ufeff${text}`], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
