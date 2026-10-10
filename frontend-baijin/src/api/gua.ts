/**
 * 卦画工具：把后端返回的卦（上卦/下卦）还原成六爻数组。
 * 八卦二进制（自下而上，1=阳）：乾111 兑110 离101 震100 巽011 坎010 艮001 坤000
 * —— 与后端 engine.py 的先天八卦数一致，已用真实响应核对（地山谦 = [0,0,1,0,0,0]）。
 */
import type { GuaBrief } from './types'

export const TRIGRAM_LINES: Record<number, number[]> = {
  1: [1, 1, 1], // 乾
  2: [1, 1, 0], // 兑
  3: [1, 0, 1], // 离
  4: [1, 0, 0], // 震
  5: [0, 1, 1], // 巽
  6: [0, 1, 0], // 坎
  7: [0, 0, 1], // 艮
  8: [0, 0, 0], // 坤
}

/** 六爻数组（自下而上）。后端只在部分卦里带 lines，其余按上下卦推 */
export function guaLines(g: GuaBrief | null | undefined): number[] {
  if (!g) return []
  if (Array.isArray(g.lines) && g.lines.length === 6) return g.lines
  const lower = TRIGRAM_LINES[g.lower?.num] || []
  const upper = TRIGRAM_LINES[g.upper?.num] || []
  return [...lower, ...upper]
}

/** 阴阳翻转指定爻（1 起，自下而上）——变卦即本卦动爻翻转 */
export function flipLine(lines: number[], position: number): number[] {
  const out = [...lines]
  const i = position - 1
  if (i >= 0 && i < out.length) out[i] = out[i] === 1 ? 0 : 1
  return out
}

/** 五行 → 签样式类名 */
export function wxClass(wx: string | undefined): string {
  return wx && '金木水火土'.includes(wx) ? `wx-chip wx-${wx}` : 'wx-chip'
}
