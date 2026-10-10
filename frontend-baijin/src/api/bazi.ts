/**
 * 四柱八字接口：排盘 + 农历换算 + 地区经纬度
 * 排盘是纯计算，不调 AI、不扣额度。
 */
import { api, qs } from './client'
import type { BaziData } from './types'

export interface BaziInput {
  year: number
  month: number
  day: number
  hour: number
  minute: number
  gender: number             // 1=男 0=女
  calendar: 'solar' | 'lunar'
  leap_month?: boolean
  dst?: boolean
  true_solar?: boolean
  longitude?: number
  latitude?: number            // 出生地纬度（空间环境气用，可选）
}

/** 年月日必填，其余可省（省了就按默认：男、公历、不校正、东经 120°、0 时 0 分） */
export type BaziInputPartial = Pick<BaziInput, 'year' | 'month' | 'day'> & Partial<BaziInput>

export async function paipan(input: BaziInputPartial): Promise<BaziData> {
  const defaults: Omit<BaziInput, 'year' | 'month' | 'day'> = {
    gender: 1, calendar: 'solar', leap_month: false, dst: false,
    true_solar: false, longitude: 120, hour: 0, minute: 0,
  }
  return api.post<BaziData>('/api/bazi/paipan', { ...defaults, ...input })
}

/* ---------- 农历信息 / 换算 ---------- */

export interface LunarMeta {
  year: number
  leap_month?: number | null      // 闰几月（没有闰月则 null/0）
  months?: number[]               // 各月天数（下标即月份，闰月另计）
  month_days?: Record<string, number>
  conversion?: { solar?: string; date?: string; [k: string]: unknown }
  [k: string]: unknown
}

export async function lunarMeta(year: number, month?: number, day?: number, leap = false): Promise<LunarMeta> {
  return api.get<LunarMeta>(`/api/bazi/lunar${qs({ year, month, day, leap_month: leap ? 'true' : '' })}`)
}

/** 农历 → 公历实时换算（C1，2026-10 补：与旧前端一致，250ms 防抖由调用方做） */
export async function lunarConvert(year: number, month: number, day: number, leap = false): Promise<LunarMeta> {
  return api.get<LunarMeta>(`/api/bazi/lunar${qs({ year, month, day, leap_month: leap ? 'true' : '' })}`)
}

/* ---------- 地区（省 → 市 → 区县，经纬度在市一级） ---------- */

export interface RegionDistrict { n: string }
export interface RegionCity { n: string; l?: number; t?: number; d?: RegionDistrict[] }
export interface RegionProvince { n: string; l?: number; t?: number; c: RegionCity[] }

let _regions: RegionProvince[] | null = null

export async function regions(): Promise<RegionProvince[]> {
  if (_regions) return _regions
  _regions = await api.get<RegionProvince[]>('/api/bazi/regions')
  return _regions
}

/** 取经纬度：优先市一级，其次省一级 */
export function regionLngLat(p: RegionProvince | null, c: RegionCity | null): { lng: number; lat: number } | null {
  const l = c?.l ?? p?.l
  const t = c?.t ?? p?.t
  if (typeof l !== 'number' || typeof t !== 'number') return null
  return { lng: l, lat: t }
}
