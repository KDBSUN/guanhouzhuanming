/**
 * 奇门遁甲起局（时家·数理奇门）
 * 定局＝拆补法（站长裁定）；转盘为主、飞盘并收；起局不含断法。
 * 盘面数据由后端 /api/qimen 出（backend/qimen.py，书证见判据总表第五节）。
 */
import { api } from './client'

export interface QimenCell {
  宫: number
  地盘: string
  星: string[]
  天盘: string[]
  门: string | null
  神: string | null
  注?: string
}

export interface QimenGejuItem { 格: string; 吉凶: string; 判语: string }

export interface QimenPan {
  盘式: string
  局数: number
  阴阳遁: string
  值符: string
  值使: string
  旬首: string
  日干支: string
  时干支: string
  九宫: Record<string, QimenCell>
  格局?: {
    盘级: QimenGejuItem[]
    九宫: Record<string, QimenGejuItem[]>
    门宫: Record<string, { 生克: string; 主客: string; 判语: string; 门卦?: string; 门卦断?: string }>
  }
  择时择方?: {
    口径: string
    择时: { 可用: boolean; 判: string; 五不遇: boolean; 伏吟: boolean; 返吟: boolean; 三奇入墓: string[] }
    择方: Record<string, {
      宫: string; 方位: string; 门: string; 门吉凶: string; 吉格: string[]; 凶格: string[]
      趋避门宫: string; 日干生克: string; 建议: string; 理由: string
    }>
    日干落宫: { 宫: string; 方位: string }
    书证: string
  }
}

export interface QimenResult {
  定局: {
    节气: string
    阴阳遁: string
    元: string
    局数: number
    符头: string
    日干支: string
    时干支: string
    交节时刻: string
    下一节气: string
    下一交节时刻: string
    定局法: string
  }
  转盘?: QimenPan
  飞盘?: QimenPan
  书证?: string
}

/** 起局（dt=起局时刻；缺省用服务器当前时间） */
export async function qimen(dt: string, pan = 'both'): Promise<QimenResult> {
  return api.post<QimenResult>('/api/qimen', { dt, pan })
}
