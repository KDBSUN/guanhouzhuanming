/**
 * 梅花易数接口：起卦（可只起卦不花钱）+ AI 解卦（流式）+ 多轮追问（流式）
 *
 * 两步走的意义：起卦/体用/处方五行/应期全是代码算的，不调 LLM、不扣额度；
 * 只有用户点「AI 解卦」那一步才花钱。请求体原样保存，第二步重发即可得到同一卦
 * （起卦是确定性的）。
 */
import { postStream, type SseMessage } from './sse'
import { cachedGet } from './client'
import { getTier, getProfileId } from './mingju'
import { llmPayload } from './llm'
import type {
  DegradeInfo, MeihuaGuaData, MeihuaYingqi, Remedy, VerifyInfo,
} from './types'

/** manual = 手动起卦：用户自己定上卦、下卦（先天数 1-8）与动爻（1-6），后端不做换算 */
export type MeihuaMethod = 'yizi' | 'erzi' | 'duozi' | 'time' | 'shuzi' | 'manual'

export interface DivineBody {
  user_input: string
  method?: MeihuaMethod | ''
  params?: Record<string, unknown>
}

export interface DivineEvent {
  gua?: MeihuaGuaData
  text?: string          // 增量正文
  done?: boolean
  degrade?: DegradeInfo
  verify?: VerifyInfo
  error?: string
}

interface SseGuaEvent { type: 'gua_data'; data: MeihuaGuaData }
interface SseTextEvent { type: 'text'; content: string }
interface SseDegradeEvent extends DegradeInfo { type: 'degraded' }
interface SseVerifyEvent { type: 'verify'; data: VerifyInfo; summary?: string }
interface SseTruncEvent extends VerifyInfo { type: 'truncated' }
interface SseErrorEvent { type: 'error'; message?: string }

/** 起卦 / 解卦：ai=false 只要卦，ai=true 再落一段流式解读 */
export async function divine(
  body: DivineBody,
  ai: boolean,
  onEvent: (e: DivineEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  await postStream('/api/meihua/divine', {
    tier_override: getTier(),
    profile_id: getProfileId(),
    ai,
    method: body.method || undefined,
    params: body.params || undefined,
    user_input: body.user_input,
    // 配了自己的模型 key 就带上（走用户自己的额度），没配就不带（走每日免费额度）
    ...llmPayload(),
  }, (msg) => dispatch(msg, onEvent), signal)
}

/**
 * 八卦万物属类（手动起卦的参考资料，也是万物搜索的语料）
 * 后端逐字取自《梅花易数·卷一·八卦万物属类》，每卦带底本行号；静态数据、无归属、不扣额度。
 * 走 cachedGet：一份 15KB 的静态字典，同一次会话里反复取没有意义（并发去重 + 长缓存）。
 */
export interface WanwuGua {
  卦: string
  先天数: number
  五行: string
  方位: string
  原文: string
  起例行: number
  类象: Record<string, string[]>
  /** 每个类目**自己的**底本行号。旧版只有卦的「起例行」，于是乾的 115 条物象
   *  全部标成 1088（卦头那行）——回源对不上。2026-09-24 补发。 */
  类象行?: Record<string, number>
}

export interface GuaWanwuResponse {
  八卦: WanwuGua[]
  出处: string
  /** 口语 → 原文条目的检索词表（keys.map）。检索词**不是原文**，
   *  只是把口语对到已核实条目的指针；单字（如「门」）靠它才能对到「门户枋」。 */
  检索词?: Record<string, string[]>
}

export function fetchGuaWanwu(): Promise<GuaWanwuResponse> {
  return cachedGet<GuaWanwuResponse>('/api/meihua/gua_wanwu', 60 * 60_000)
}

/** 多轮追问：不重新起卦，只把追问并入已起的卦；也可把外应作为"外卦"一并送进去 */
export async function chat(
  guaData: MeihuaGuaData,
  history: { role: 'user' | 'assistant'; content: string }[],
  userInput: string,
  onEvent: (e: DivineEvent) => void,
  opts?: {
    signal?: AbortSignal
    /** 本次要并入的外应原文（起卦之后新出现的闻见，不重新起卦） */
    waijing?: string[]
    /** 内卦净档（顺/平/逆），来自命卦校验结果 */
    innerNet?: string
    /** 配卦有歧义时由用户指定的卦：{外应原文: 卦} */
    waijingGua?: Record<string, string>
  },
): Promise<void> {
  await postStream('/api/meihua/chat', {
    gua_data: guaData,
    history,
    user_input: userInput,
    profile_id: getProfileId(),
    waijing: opts?.waijing || [],
    inner_net: opts?.innerNet || '',
    waijing_gua: opts?.waijingGua || {},
    ...llmPayload(),
  }, (msg) => dispatch(msg, onEvent), opts?.signal)
}

function dispatch(msg: SseMessage, onEvent: (e: DivineEvent) => void): void {
  const m = msg as unknown
  switch ((m as { type: string }).type) {
    case 'gua_data':
      onEvent({ gua: (m as SseGuaEvent).data })
      break
    case 'text':
      onEvent({ text: (m as SseTextEvent).content })
      break
    case 'done':
      onEvent({ done: true })
      break
    case 'degraded': {
      const d = m as SseDegradeEvent
      onEvent({
        degrade: {
          message: d.message, hint: d.hint, scope: d.scope,
          used: d.used, limit: d.limit, resets_at: d.resets_at,
        },
      })
      break
    }
    case 'truncated': {
      const t = m as SseTruncEvent
      onEvent({
        verify: {
          kind: 'truncated', ok: false, message: t.message,
          hint: t.hint, limit: t.limit,
        },
      })
      break
    }
    case 'verify': {
      const v = m as SseVerifyEvent
      onEvent({ verify: { ...v.data, kind: 'verify', summary: v.summary } })
      break
    }
    case 'error': {
      const e = m as SseErrorEvent
      onEvent({ error: e.message || '解卦过程中出错' })
      break
    }
    default:
      break
  }
}

export function relationOf(gua: MeihuaGuaData): { verdict: string; tone: 'gold' | 'ink' | 'plat' } {
  switch (gua.tiyong.relation) {
    case '用生体':
    case '体克用':
      return { verdict: gua.tiyong.relation, tone: 'gold' }
    case '比和':
      return { verdict: gua.tiyong.relation, tone: 'plat' }
    case '体生用':
    case '用克体':
      return { verdict: gua.tiyong.relation, tone: 'ink' }
    default:
      return { verdict: gua.tiyong.relation, tone: 'plat' }
  }
}

export type { MeihuaGuaData, MeihuaYingqi, Remedy }
