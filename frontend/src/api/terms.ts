/**
 * 术语地图接口（梅花 / 六爻两套术语网）
 *  - meta：体系、分类与词条数（用来建导航）
 *  - list：按体系/分类取词条
 *  - search：按名称、别名、释义搜
 *  - detail：一条术语的详解、出处原文与关联术语
 */
import { cachedGet, qs } from './client'

export interface TermMeta {
  systems: {
    system: string
    label: string
    total: number
    links: number
    categories: { name: string; count: number }[]
  }[]
}

export interface TermBrief {
  id: number
  system: string
  category: string
  name: string
  alias: string
  role: string
}

export interface TermRelation {
  name: string
  id: number
  category: string
  system: string
  exists: boolean
}

export interface TermDetail extends TermBrief {
  cat_order?: number
  term_order?: number
  detail: string
  sources: string
  source_book: string
  source_loc: string
  source_quote: string
  relations: TermRelation[]
}

/* 术语表是"公共只读字典"：内容不随用户变化，同一次会话里反复读没意义。
   所以走 cachedGet（同 URL 并发共用一次请求 + 5 分钟缓存）——切分类来回点不再重复打后端。 */
const TERM_TTL = 5 * 60_000

export async function fetchTermMeta(): Promise<TermMeta> {
  return cachedGet<TermMeta>('/api/terms/meta', TERM_TTL)
}

export async function fetchTerms(system = '', category = ''): Promise<TermBrief[]> {
  const res = await cachedGet<{ terms: TermBrief[] }>(`/api/terms${qs({ system, category })}`, TERM_TTL)
  return res.terms || []
}

export async function searchTerms(q: string): Promise<TermBrief[]> {
  // 搜索词千变万化，缓存短一点（30 秒），主要靠并发去重挡连点
  const res = await cachedGet<{ terms: TermBrief[] }>(`/api/terms/search${qs({ q })}`, 30_000)
  return res.terms || []
}

export async function fetchTermDetail(id: number): Promise<TermDetail> {
  return cachedGet<TermDetail>(`/api/terms/detail${qs({ id })}`, TERM_TTL)
}
