/**
 * 纳甲六爻接口
 *  - divine：六次摇卦参数 → 排盘（免费）→（可选）AI 断卦（流式，扣一次额度）
 *  - yongshenClassify：起卦前预判用神（纯规则，不调 LLM，见后端 classify_yongshen_detail）
 *  - remedyRecalc：已排好的盘上改判用神，重算处方五行（不重新起卦）
 */
import { postStream, type SseMessage } from './sse'
import { api } from './client'
import { getTier, getProfileId } from './mingju'
import { llmPayload } from './llm'
import type { DegradeInfo, LiuyaoGuaData, Remedy, VerifyInfo } from './types'
import type { ThrowParams } from '../common/liuyaoSeed'

export interface LiuyaoEvent {
  gua?: LiuyaoGuaData
  text?: string
  done?: boolean
  degrade?: DegradeInfo
  verify?: VerifyInfo
  error?: string
}

export interface YongshenDetail {
  yongshen: string
  source: string
  confidence: string
  candidates: string[]
  reason: string
  matched?: { kw: string; liuqin: string; layer: string }[]
  need_confirm?: boolean
}

/** 排盘 / 断卦 */
export async function divine(
  question: string,
  throws: ThrowParams[],
  ai: boolean,
  onEvent: (e: LiuyaoEvent) => void,
  opts?: { yongshenOverride?: string; signal?: AbortSignal },
): Promise<void> {
  await postStream('/api/liuyao/divine', {
    question,
    throws: throws.map((t) => ({
      x: t.x, y: t.y, duration: Math.round(t.duration), speed: t.speed,
    })),
    tier_override: getTier(),
    yongshen_override: opts?.yongshenOverride || '',
    profile_id: getProfileId(),
    ai,
    // 配了自己的模型 key 就带上（走用户自己的额度），没配就不带（走每日免费额度）
    ...llmPayload(),
  }, (msg) => dispatch(msg, onEvent), opts?.signal)
}

/** 起卦前预判用神（纯规则） */
export async function classifyYongshen(question: string): Promise<YongshenDetail> {
  return api.post<YongshenDetail>('/api/liuyao/yongshen/classify', { question })
}

/** 改判用神后重算处方五行（用已排好的盘） */
export async function remedyRecalc(
  guaData: LiuyaoGuaData, question: string, yongshenOverride: string,
): Promise<Remedy> {
  return api.post<Remedy>('/api/liuyao/remedy', {
    gua_data: guaData, question, yongshen_override: yongshenOverride,
  })
}

function dispatch(msg: SseMessage, onEvent: (e: LiuyaoEvent) => void): void {
  const m = msg as { type: string }
  switch (m.type) {
    case 'gua_data':
      onEvent({ gua: (msg as unknown as { data: LiuyaoGuaData }).data })
      break
    case 'text':
      onEvent({ text: (msg as unknown as { content: string }).content })
      break
    case 'done':
      onEvent({ done: true })
      break
    case 'degraded': {
      const d = msg as unknown as DegradeInfo & { type: string }
      onEvent({
        degrade: {
          message: d.message, hint: d.hint, scope: d.scope,
          used: d.used, limit: d.limit, resets_at: d.resets_at,
        },
      })
      break
    }
    case 'truncated': {
      const t = msg as unknown as VerifyInfo & { type: string }
      onEvent({ verify: { kind: 'truncated', ok: false, message: t.message, hint: t.hint, limit: t.limit } })
      break
    }
    case 'verify': {
      const v = msg as unknown as { data: VerifyInfo; summary?: string }
      onEvent({ verify: { ...v.data, kind: 'verify', summary: v.summary } })
      break
    }
    case 'error':
      onEvent({ error: (msg as unknown as { message?: string }).message || '断卦过程中出错' })
      break
    default:
      break
  }
}
