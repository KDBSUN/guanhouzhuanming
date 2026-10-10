/**
 * 大六壬起课
 * 贵人＝甲戊庚牛羊（站长裁定）；月将＝中气交节时刻后换将（站长裁定）；
 * 起课不含断法。数据由后端 /api/leixiang 出（起课＋类神取用＋射覆占物，
 * backend/daliuren.py、leixiang.py，书证见判据总表第六节）。
 */
import { api } from './client'

export interface DaliurenResult {
  日干支: string
  占时: string
  月将: string
  课体: string
  课体判语: string
  附加课体: { 课体: string; 判语: string }[]
  贵人: string
  贵人顺逆: string
  时刻: string
  天盘: Record<string, string>
  四课: { 干上: string; 干阴: string; 支上: string; 支阴: string }
  三传: string[]
  天将: Record<string, string>
  遁干: string[]
  六亲: string[]
  空亡: string[]
  年命?: { 本命: string; 行年: string | null; 行年干支: string; 虚岁: number }
  配偶年命?: { 本命: string; 行年: string | null; 行年干支: string; 虚岁: number }
  毕法: { 法: string; 名: string; 判语: string }[]
  类神取用?: {
    问事: string; 通类天将: string; 通类据: string; 取类规则: string; 口径: string
    类神: { 记号: string; 类神: string; 名: string; 状态: string[]; 与干上: string[] }[]
  }
  射覆?: { 口径: string; 线索: { 层: string; 候选: string[]; 据: string }[] }
  书证?: string
}

export interface DaliurenInput {
  dt: string
  shizhi: string | null
  wenshi: string
  nianzhu: string | null
  xingbie: string | null
  nianzhu2: string | null
  xingbie2: string | null
}

/** 起课＋类神取用＋射覆（问事类别决定类神层） */
export async function daliuren(input: DaliurenInput): Promise<DaliurenResult> {
  return api.post<DaliurenResult>('/api/leixiang', input)
}
