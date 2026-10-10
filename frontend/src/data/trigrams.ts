/**
 * 八卦基础数据：先天数 · 爻画 · 后天方位 · 五行
 * ============================================================
 * 爻画与后端 engine.py 的 BAGUA_YAO 逐位一致（**从下往上**：初爻、二爻、三爻；1=阳 0=阴），
 * 所以前端画的卦与后端排出的卦必然相同。渲染时倒过来画（最上面是第三爻）。
 *
 * 两套数不要混：
 *   · 先天数（乾一兑二离三震四巽五坎六艮七坤八）——**起卦用**，手动起卦填的就是它；
 *   · 后天方位（离南坎北震东兑西…）——**取方位下卦与断方位用**。
 * 出处：《梅花易数》卷一「八卦万物属类（并为上卦）」第 808 行起、
 *       「后天端法：以物为上卦，方位为下卦」第 802 行。
 */
export interface Trigram {
  num: number          // 先天数 1-8
  name: string         // 卦名
  symbol: string       // ☰
  wx: string           // 五行
  pos: string          // 后天方位
  lines: number[]      // 从下往上 [初爻, 二爻, 三爻]，1=阳 0=阴
  nature: string       // 基本象（乾为天…）
}

export const TRIGRAMS: Trigram[] = [
  { num: 1, name: '乾', symbol: '☰', wx: '金', pos: '西北', lines: [1, 1, 1], nature: '天' },
  { num: 2, name: '兑', symbol: '☱', wx: '金', pos: '西',   lines: [1, 1, 0], nature: '泽' },
  { num: 3, name: '离', symbol: '☲', wx: '火', pos: '南',   lines: [1, 0, 1], nature: '火' },
  { num: 4, name: '震', symbol: '☳', wx: '木', pos: '东',   lines: [1, 0, 0], nature: '雷' },
  { num: 5, name: '巽', symbol: '☴', wx: '木', pos: '东南', lines: [0, 1, 1], nature: '风' },
  { num: 6, name: '坎', symbol: '☵', wx: '水', pos: '北',   lines: [0, 1, 0], nature: '水' },
  { num: 7, name: '艮', symbol: '☶', wx: '土', pos: '东北', lines: [0, 0, 1], nature: '山' },
  { num: 8, name: '坤', symbol: '☷', wx: '土', pos: '西南', lines: [0, 0, 0], nature: '地' },
]

export const triOf = (num: number): Trigram | null => TRIGRAMS.find((t) => t.num === num) || null
export const triName = (num: number): string => triOf(num)?.name || '未定'

/** 爻位名：1=初爻 … 6=上爻 */
export const YAO_NAMES = ['初爻', '二爻', '三爻', '四爻', '五爻', '上爻']

/**
 * 后天八卦九宫格（南上北下、东左西右——传统八卦图的方位惯例）。
 * 中央为空（中五宫），放太极。
 *   巽东南 │ 离南 │ 坤西南
 *   震东   │ 太极 │ 兑西
 *   艮东北 │ 坎北 │ 乾西北
 */
export const HOUTIAN_GRID: (number | null)[][] = [
  [5, 3, 8],
  [4, null, 2],
  [7, 6, 1],
]

/* ---------- 时辰（端法取动爻要用：子1 丑2 … 亥12） ---------- */

const ZHI = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']

/** 由小时数（0-23）求地支序：23-1 子、1-3 丑 …（子时跨日，按 23 点起算） */
export function hourToZhiIndex(hour: number): number {
  return Math.floor(((hour + 1) % 24) / 2)
}

export interface Shichen {
  zhi: string        // 酉
  num: number        // 10（子1…亥12）
  label: string      // 酉时（17:00-19:00）
}

/** 某个时刻的时辰；不传则取当下 */
export function shichenOf(d: Date = new Date()): Shichen {
  const i = hourToZhiIndex(d.getHours())
  const from = ((i * 2) + 23) % 24
  return {
    zhi: ZHI[i],
    num: i + 1,
    label: `${ZHI[i]}时（${String(from).padStart(2, '0')}:00-${String((from + 2) % 24).padStart(2, '0')}:00）`,
  }
}

/**
 * 端法取动爻：（上卦先天数 + 下卦先天数 + 时辰数）÷ 6 取余，余 0 作 6。
 * 与后端 engine.number_to_yao 的约定一致（余 0 视为 6）。
 * 出处：《梅花易数》第 802 行「合物卦之数与方卦之数，加时数以取动爻」、
 *       第 806 行白话「以事物的卦数与方位的卦数之和，再加上时辰数除六以取动爻」。
 */
export function movingByDuanfa(upper: number, lower: number, shichenNum: number): {
  sum: number; yao: number; formula: string
} {
  const sum = upper + lower + shichenNum
  const r = sum % 6
  const yao = r === 0 ? 6 : r
  return {
    sum,
    yao,
    formula: `${upper} + ${lower} + ${shichenNum} = ${sum}，${sum} ÷ 6 余 ${r}`
      + (r === 0 ? '（余 0 作 6）' : '') + ` → ${YAO_NAMES[yao - 1]}`,
  }
}
