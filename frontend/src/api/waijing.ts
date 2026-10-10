/**
 * 外应（刻应）参断
 * 《梅花易数》把起卦之后偶见的外物称为「刻应」「外应」，属外卦，与体用互变（内卦）合断。
 * 本模块只产出一层"外卦"的参断结论：不重新起卦、不改体用互变、不换动爻。
 * 配卦有歧义或配不到时如实返回候选，由用户指定，绝不替用户猜一个卦。
 */
import { api } from './client'
import type { MeihuaGuaData } from './types'

export interface WaijingCandidate {
  gua: string
  wuxing: string
  by: string          // 配卦依据（类象·动物 / 听声音占 / 类推…）
  term?: string
  src?: string
  extrapolated?: boolean
}

export interface WaijingAdjudication {
  gua: string
  wuxing: string
  ti_wuxing: string
  relation: string     // 比和 / 外应生体 / 外应克体 / 体生外应 …
  effect: string       // 助吉 / 反破其吉 / 可解其不吉 …
  polarity: string     // 吉 / 凶 / 中
  reason: string
  src: string
}

export interface WaijingItem {
  omen: string
  resolve: {
    candidates: WaijingCandidate[]
    text: string
    ambiguous: boolean
    note: string
    extrapolated: boolean
  }
  chosen_gua: string
  needs_choice: boolean
  adjudication: WaijingAdjudication | null
  modulation?: { strength?: string; timing?: string; notes?: string[]; src?: string[] }
  combined?: Record<string, unknown>
  moves_gua?: boolean
  moves_gua_say?: string
  version_note?: string
}

export interface WaijingResult {
  items: WaijingItem[]
  primary?: { primary?: WaijingItem; basis?: string }
  combined: {
    net?: string
    verdict?: string
    polarity?: string
    policy?: string
    inner?: string
    outer?: string
    say?: string
    has_undecided?: boolean
    src?: string
  }
  needs_choice: string[]
  moves_gua: boolean
  version_note: string
  prompt_block: string
}

export interface WaijingInput {
  omen: string[]
  tiWuxing?: string
  guaData?: MeihuaGuaData | null
  innerNet?: string
  direction?: string    // 来 / 去
  motion?: string       // 动 / 不动
  chosen?: Record<string, string>
}

export async function analyzeWaijing(input: WaijingInput): Promise<WaijingResult> {
  return api.post<WaijingResult>('/api/meihua/waijing', {
    omen: input.omen,
    ti_wuxing: input.tiWuxing || '',
    gua_data: input.guaData || {},
    inner_net: input.innerNet || '',
    direction: input.direction || '',
    motion: input.motion || '',
    chosen: input.chosen || {},
  })
}
