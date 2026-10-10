/**
 * 万物类象 · 本地向量检索
 * ============================================================
 * 为什么在前端算：语义嵌入需要一个 embedding 服务，站长那把阿里云百炼 key 的
 * embedding 免费额度已用尽（实测 HTTP 400，错误码 AllocationQuota.FreeTierOnly），
 * DeepSeek 那把 key 不提供 embedding 接口。用户裁决：**只做前端向量，不动后端**。
 *
 * 做法（是真正的向量检索，不是字符串 includes）：
 *   1. 语料＝《八卦万物属类》916 条物象（后端 /api/meihua/gua_wanwu，逐字带底本行号）
 *      ＋ 用户规定的 8 段《八卦属性》（src/data/baguaAttr.ts）；
 *   2. 每条文档切成"字一元组 + 字二元组"，二元组权重 ×2（中文没有空格，二元组是
 *      不依赖分词器又能抓住词形的最小单位）；
 *   3. 词频 × IDF 得到文档向量，L2 归一化；查询同样处理；
 *   4. 用**倒排表**只累加与查询有共同词的文档，916 条也是亚毫秒级；
 *   5. 每条物象的最终分＝物象自身余弦 ＋ 0.35 × 该卦《八卦属性》余弦。
 *      后半项就是用户"规定的向量"在起作用：搜"领导力"时物象字面没有这三个字，
 *      但乾卦属性里有，于是乾的物象整体被抬起来。
 *
 * 局限（界面上如实写明，不假装是语义模型）：只认字面与近字面。
 * 搜"上司"命中不了"君父、大人、长者"——没有共同字。这种情况走"整卦命中"那一行
 * （属性文本里有"领导力/主宰"），或直接在八卦图里翻类目。
 */
import { BAGUA_ATTR } from '../data/baguaAttr'
import type { WanwuGua } from '../api/meihua'

export type { WanwuGua }

/** 摊平后的的一条物象 */
export interface WanwuItem {
  gua: string
  num: number
  /** 同一条物象可能出现在多个类目下（如"泽"在兑的天时与地理），合并列出 */
  cats: string[]
  text: string
  line: number          // 底本行号（回源用）：**该物象所属类目自己的行**，不是卦的起例行
}

export interface ItemHit {
  kind: 'item'
  item: WanwuItem
  score: number         // 综合分 0-1
  matched: string[]     // 命中的二元组，供界面加粗
}

export interface GuaHit {
  kind: 'gua'
  gua: string
  num: number
  score: number
  snippet: string       // 命中的那段属性原文
}

export type BaguaHit = ItemHit | GuaHit

/** 原文条目命中（可当书证）：三档之一。站长 2026-09-24 定：与 frontend/ 口径对齐。 */
export interface LiteralHit {
  item: WanwuItem
  tier: '精确' | '包含' | '检索词'
  /** 检索词档会写明经哪个口语词对到条目 */
  via?: string
  matched?: string[]
}

/** 一次搜索的完整结果，**分两栏**：
 *  literal＝原文条目命中（可当书证，带精确行号）；
 *  related＝相关度命中（tf-idf 余弦，**非原文条目**，仅供参考）。
 *  为什么分：余弦的相关度不能冒充书证——「出处写不出键就等于没有出处」。 */
export interface SearchResult {
  literal: LiteralHit[]
  related: BaguaHit[]
  searched: string
}

export interface BaguaIndex {
  guas: WanwuGua[]
  items: WanwuItem[]
  source: string
  /** 倒排表：token → [{文档下标, 归一化后的权重}] */
  postings: Map<string, { i: number; w: number }[]>
  /** 八卦属性向量（已归一化）：卦名 → token → 权重 */
  attrVec: Map<string, Map<string, number>>
  /** 口语词 → 物象下标（keys.map 的反向索引）。单字（如「门」）走不了子串匹配，
   *  靠这张表才能对到「门户枋」——检索词是人工核过的指针，不是放任子串。 */
  colloq: Map<string, number[]>
  builtAt: number
}

/* ---------- 切词 ---------- */

const PUNCT = /[\s，、。；：！？“”‘’（）()《》〈〉·…—\-/|,.\u200b]/g

/** 字一元组（权重 1）＋字二元组（权重 2）→ token 计数 */
function grams(s: string): Map<string, number> {
  const t = s.replace(PUNCT, '')
  const m = new Map<string, number>()
  const chars = Array.from(t)
  for (const ch of chars) m.set('u' + ch, (m.get('u' + ch) || 0) + 1)
  for (let i = 0; i < chars.length - 1; i++) {
    const bg = 'b' + chars[i] + chars[i + 1]
    m.set(bg, (m.get(bg) || 0) + 2)
  }
  return m
}

function l2norm(v: Map<string, number>): number {
  let s = 0
  for (const w of v.values()) s += w * w
  return Math.sqrt(s) || 1
}

/** 万物查卦只查**物类维度**——与 backend `/api/meihua/wanwu_search` 同一口径
 *  （站长 2026-09-24 定，两版对齐）。婚姻／疾病／官讼／求名／求利等是**占断维度**，
 *  不是"东西"，不参与：搜「门」时「利公门（谋望）」「公门中得财（求利）」这类就该被挡掉。 */
const WANWU_FIELDS = new Set(['静物', '动物', '人物', '屋宿', '屋舍', '饮食', '天时', '地理', '五色'])

/** 摊平 916 条物象，并按 (卦, 物象文本) 合并重复类目。
 *  `fieldLines`＝每个类目自己的底本行号（后端 `类象行`，2026-09-24 起下发）；
 *  给了它，每条物象的行号就是**所属类目**的行，不再一律用卦的起例行。
 *  **只收物类维度**（WANWU_FIELDS），占断维度不进索引——与旧前端口径对齐。 */
export function flattenWanwu(guas: WanwuGua[]): WanwuItem[] {
  const byKey = new Map<string, WanwuItem>()
  for (const g of guas) {
    const cats = g['类象'] || {}
    const fl = g['类象行'] || {}
    for (const [cat, arr] of Object.entries(cats)) {
      if (!WANWU_FIELDS.has(cat)) continue          // 占断维度不是"东西"，不参与
      if (!Array.isArray(arr)) continue
      for (const raw of arr) {
        const text = String(raw || '').trim()
        if (!text) continue
        const key = `${g['卦']}\u0000${text}`
        const hit = byKey.get(key)
        if (hit) { if (!hit.cats.includes(cat)) hit.cats.push(cat); continue }
        byKey.set(key, {
          gua: g['卦'], num: g['先天数'], cats: [cat], text,
          // 有类目行号就给精确的；没有则退回卦的起例行（旧数据）
          line: Number(fl[cat]) || Number(g['起例行']) || 0,
        })
      }
    }
  }
  return [...byKey.values()]
}

/* ---------- 建索引 ---------- */

export function buildIndex(guas: WanwuGua[], source = '', colloqMap?: Record<string, string[]>): BaguaIndex {
  const items = flattenWanwu(guas)

  // 文档文本：物象本身 + 所属类目（类目词让"静物""饮食"这类查询也能命中）
  const docTexts = items.map((it) => `${it.text}　${it.cats.join('　')}`)
  // 8 段八卦属性作为"卦级文档"，跟在物象文档之后（下标 items.length .. +7）
  const attrTexts = BAGUA_ATTR.map((a) => `${a.gua}卦 ${a.title} 核心属性 ${a.core} 类象逻辑 ${a.logic} ${a.gist}`)
  const allTexts = [...docTexts, ...attrTexts]

  const docGrams = allTexts.map(grams)
  const N = allTexts.length
  const df = new Map<string, number>()
  for (const g of docGrams) for (const tok of g.keys()) df.set(tok, (df.get(tok) || 0) + 1)
  const idf = (tok: string) => Math.log(1 + N / (df.get(tok) || 1))

  // 文档向量（tf·idf，L2 归一化）→ 倒排表
  const postings = new Map<string, { i: number; w: number }[]>()
  docGrams.forEach((g, i) => {
    const v = new Map<string, number>()
    for (const [tok, tf] of g) v.set(tok, tf * idf(tok))
    const n = l2norm(v)
    for (const [tok, w] of v) {
      const list = postings.get(tok)
      if (list) list.push({ i, w: w / n })
      else postings.set(tok, [{ i, w: w / n }])
    }
  })

  // 八卦属性向量单独留一份（供"整卦命中"与物象加分）
  const attrVec = new Map<string, Map<string, number>>()
  BAGUA_ATTR.forEach((a, k) => {
    const i = items.length + k
    const list = new Map<string, number>()
    for (const [tok, arr] of postings) {
      for (const e of arr) if (e.i === i) { list.set(tok, e.w); break }
    }
    attrVec.set(a.gua, list)
  })

  // 口语词 → 物象下标（keys.map 反向）。命中时按 tier「检索词」单列，可当书证。
  // keys.map 的形状是 {原文条目: [口语词...]}，这里翻转成 {口语词: [下标...]}。
  const colloq = new Map<string, number[]>()
  if (colloqMap) {
    const byText = new Map<string, number[]>()
    items.forEach((it, i) => {
      const arr = byText.get(it.text) || []
      arr.push(i)
      byText.set(it.text, arr)
    })
    for (const [entry, words] of Object.entries(colloqMap)) {
      const arr = Array.isArray(words) ? words : []
      for (const w of arr) {
        const wq = String(w || '').trim()
        if (!wq) continue
        for (const i of byText.get(entry) || []) {
          const list = colloq.get(wq) || []
          if (!list.includes(i)) list.push(i)
          colloq.set(wq, list)
        }
      }
    }
  }

  return { guas, items, source, postings, attrVec, colloq, builtAt: Date.now() }
}

/* ---------- 检索 ---------- */

function queryVec(q: string, idx: BaguaIndex): Map<string, number> {
  const g = grams(q)
  const N = idx.items.length + BAGUA_ATTR.length
  const v = new Map<string, number>()
  for (const [tok, tf] of g) v.set(tok, tf * Math.log(1 + N / 1))
  const n = l2norm(v)
  for (const [tok, w] of v) v.set(tok, w / n)
  return v
}

/** 命中的词（二元组优先；单字查询退回一元组），供界面把匹配到的字加粗 */
function matchedBigrams(qv: Map<string, number>, idx: BaguaIndex, docIdx: number): string[] {
  const bi: string[] = []
  const uni: string[] = []
  for (const tok of qv.keys()) {
    const arr = idx.postings.get(tok)
    if (!arr || !arr.some((e) => e.i === docIdx)) continue
    if (tok.startsWith('b')) bi.push(tok.slice(1))
    else uni.push(tok.slice(1))
    if (bi.length >= 6) break
  }
  return (bi.length ? bi : uni).slice(0, 6)
}

export interface SearchOpts {
  limit?: number
  /** 物象最低综合分。实测取值：0.05 能滤掉"领导力"带出的 0.039 弱字面噪声，
   *  同时保住"圆形金属"→圆物 0.134、"高官"→宦官 0.071 这类真命中。 */
  minItem?: number
  /** 整卦命中的最低属性余弦。实测：0.10 时"领导力"0.183、"坚硬"0.123 能进，
   *  "高官"这类只沾一个字的进不来（合理：它并没有讲清是哪一卦的性态）。 */
  minGua?: number
}

/** 单字不许走子串——「药」⊂「药婆」（兑·人物，指卖药的人），放行就是近义词假命中。
 *  单字的合法通路是**检索词表**（人工核过的指针，如「门」→「门户枋」）。
 *  站长 2026-09-24 定：近义词不命中。 */
const SUBSTR_MIN_LEN = 2

/** 三档字面命中（可当书证）：精确 ＞ 包含（双向子串，≥2 字）＞ 检索词（keys.map）。 */
function literalTier(q: string, idx: BaguaIndex): { tier: '精确' | '包含' | '检索词'; via?: string; idxs: number[] } | null {
  // 精确：查询词就是某个原文条目
  const exact: number[] = []
  idx.items.forEach((it, i) => { if (it.text === q) exact.push(i) })
  if (exact.length) return { tier: '精确', idxs: exact }

  // 检索词（先于包含）：单字也能走，且是人工核过的指针
  const col = idx.colloq.get(q)
  if (col && col.length) return { tier: '检索词', via: q, idxs: col }

  // 包含（双向子串），查询词 ≥ 2 字
  if (q.length >= SUBSTR_MIN_LEN) {
    const sub: number[] = []
    idx.items.forEach((it, i) => { if (it.text.includes(q) || q.includes(it.text)) sub.push(i) })
    if (sub.length) return { tier: '包含', idxs: sub }
  }
  return null
}

export function searchBagua(idx: BaguaIndex, query: string, opts: SearchOpts = {}): SearchResult {
  const q = query.trim()
  if (!q) return { literal: [], related: [], searched: '' }
  const limit = opts.limit ?? 40
  const minItem = opts.minItem ?? 0.05
  const minGua = opts.minGua ?? 0.10
  const qv = queryVec(q, idx)

  // 0) 字面命中（可当书证）：精确／包含／检索词。命中的不再进相关度栏。
  const lit = literalTier(q, idx)
  const literalHits: LiteralHit[] = []
  const litIdx = new Set<number>()
  if (lit) {
    for (const i of lit.idxs) {
      litIdx.add(i)
      literalHits.push({
        item: idx.items[i],
        tier: lit.tier,
        ...(lit.via ? { via: `检索词「${lit.via}」` } : {}),
        matched: matchedBigrams(qv, idx, i),
      })
    }
    // 检索词命中按类目数排前；其余按字面长度（更长的条目更具体）
    literalHits.sort((a, b) =>
      a.tier === b.tier ? (b.item.text.length - a.item.text.length) : 0)
  }

  // 1) 物象余弦（只走倒排表，不遍历全部文档）
  const cos = new Float64Array(idx.items.length)
  for (const [tok, w] of qv) {
    const arr = idx.postings.get(tok)
    if (!arr) continue
    for (const e of arr) if (e.i < idx.items.length) cos[e.i] += w * e.w
  }

  // 2) 八卦属性余弦（只有 8 条，直接算）
  const attrCos = new Map<string, number>()
  for (const a of BAGUA_ATTR) {
    const av = idx.attrVec.get(a.gua)
    if (!av) { attrCos.set(a.gua, 0); continue }
    let s = 0
    for (const [tok, w] of qv) s += w * (av.get(tok) || 0)
    attrCos.set(a.gua, s)
  }

  // 3) 相关度命中：tf-idf 余弦。**非原文条目，仅供参考**，与字面命中分栏。
  //    **单字查询不出物象相关度**——单字能共字的条目太多，且这正是「药」→「药婆」
  //    （兑·人物，指卖药的人）那类假命中的来源（站长 2026-09-24 定：近义词不命中）。
  //    整卦命中不受此限：它走《八卦属性》文本，与查询字面长度无关。
  const allowItemRelated = q.length >= SUBSTR_MIN_LEN
  const hits: BaguaHit[] = []
  for (let i = 0; i < idx.items.length; i++) {
    if (cos[i] <= 0) continue
    if (litIdx.has(i)) continue                    // 已在原文命中栏，不重复
    if (!allowItemRelated) continue                // 单字查询：不出物象相关度
    const it = idx.items[i]
    const score = Math.min(1, cos[i] + 0.35 * (attrCos.get(it.gua) || 0))
    if (score < minItem) continue
    hits.push({ kind: 'item', item: it, score, matched: matchedBigrams(qv, idx, i) })
  }
  hits.sort((a, b) => (b as ItemHit).score - (a as ItemHit).score)

  // 4) 整卦命中：查询主要落在"性态"上时（物象字面没有），把该卦整体端出来。
  //    依据是《八卦属性》——**站长自定文本，非典籍原文**，故归入相关度栏。
  const guaHits: GuauaHitTmp[] = []
  for (const a of BAGUA_ATTR) {
    const s = attrCos.get(a.gua) || 0
    if (s >= minGua) guaHits.push({ a, s })
  }
  guaHits.sort((x, y) => y.s - x.s)

  const related: BaguaHit[] = guaHits.slice(0, 3).map(({ a, s }) => ({
    kind: 'gua' as const,
    gua: a.gua,
    num: a.num,
    score: Math.min(1, s),
    snippet: `${a.title}｜核心属性：${a.core}｜${a.gist}`,
  }))
  related.push(...hits.slice(0, limit))
  return { literal: literalHits, related, searched: q }
}

interface GuauaHitTmp { a: typeof BAGUA_ATTR[number]; s: number }
