import { useCallback, useEffect, useRef, useState } from 'react'
import { FishTail } from '../art/book'
import { friendlyError } from '../api/client'
import {
  fetchTermDetail, fetchTermMeta, fetchTerms, searchTerms,
  type TermBrief, type TermDetail, type TermMeta,
} from '../api/terms'

/* ============================================================
   术语地图（名物考）—— 已接后端
   一句话定位（role）→ 详解（detail）→ 关联术语互跳 → 原文语录与出处
   ============================================================ */

export default function TermsPage() {
  const [meta, setMeta] = useState<TermMeta | null>(null)
  const [system, setSystem] = useState('meihua')
  const [category, setCategory] = useState('')
  const [q, setQ] = useState('')
  const [terms, setTerms] = useState<TermBrief[]>([])
  const [searching, setSearching] = useState(false)
  const [detail, setDetail] = useState<TermDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchTermMeta().then((m) => {
      setMeta(m)
      if (m.systems?.length && !m.systems.some((s) => s.system === system)) {
        setSystem(m.systems[0].system)
      }
    }).catch((e) => setError(friendlyError(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* E1：竞态取消——快速连续切分类/搜索时，丢弃过期响应，旧结果不得覆盖新结果 */
  useEffect(() => {
    let cancelled = false
    const run = async () => {
      setLoading(true); setError('')
      const hasQuery = !!q.trim()
      setSearching(hasQuery)
      try {
        let list: TermBrief[]
        if (hasQuery) {
          list = await searchTerms(q.trim())
        } else {
          list = await fetchTerms(system, category)
        }
        if (cancelled) return
        setTerms(list)
        /* E3：自动选第一条（有已选且仍在列表则保留） */
        const cur = detailRef.current
        const still = cur && list.some((t) => t.id === cur.id)
        setDetail((d) => (still ? d : null))
        if (list.length && !still) {
          fetchTermDetail(list[0].id).then((d) => { if (!cancelled) setDetail(d) })
            .catch(() => { /* 详情失败不影响列表 */ })
        }
      } catch (e) {
        if (!cancelled) { setError(friendlyError(e)); setTerms([]) }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void run()
    return () => { cancelled = true }
  }, [system, category, q])

  /** 当前右侧详情的 id（跨渲染共享，避免闭包旧值） */
  const detailRef = useRef<TermDetail | null>(null)
  useEffect(() => { detailRef.current = detail }, [detail])

  const open = useCallback(async (id: number) => {
    try {
      setDetail(await fetchTermDetail(id))
    } catch (e) {
      setError(friendlyError(e))
    }
  }, [])

  /** E2：互跳同步分类——跨体系点术语/关联时，把分类落到目标体系里它所属的分类 */
  const jumpTo = useCallback((t: { system: string; category: string; id: number }) => {
    if (t.system !== system) {
      setSystem(t.system)
      setCategory(t.category)
    }
    open(t.id)
    /* 详情出来后定位到右侧顶部的互跳点（旧前端 scrollIntoView） */
    window.setTimeout(() => {
      document.querySelector('.terms-col.detail')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }, 80)
  }, [system, open])

  const sysMeta = meta?.systems.find((s) => s.system === system)

  return (
    <div>
      <div className="leaf-head">
        <span className="juan-mark">易占</span>
        <FishTail />
        <span className="juan">名物考</span>
        <span className="folio">卷五</span>
      </div>
      <div className="juan-title">
        <h1>术语地图</h1>
        <p className="juan-sub">一句话定位 → 详解 → 关联术语互跳 → 原文与出处</p>
      </div>

      {/* 体系切换 */}
      <div className="btn-row" style={{ marginBottom: 10 }}>
        <div className="slip-row">
          {(meta?.systems || []).map((s) => (
            <button key={s.system} type="button"
              className={`slip ${system === s.system ? 'active' : ''}`}
              onClick={() => { setSystem(s.system); setCategory(''); setDetail(null) }}>
              {s.label} {s.total}
            </button>
          ))}
        </div>
        {sysMeta && <span className="hint-line">{sysMeta.total} 词条 · {sysMeta.links} 条关联</span>}
      </div>

      {/* 搜索 */}
      <div className="btn-row" style={{ marginBottom: 10 }}>
        <input className="mini-input" style={{ flex: 1, minWidth: 'min(100%, 220px)' }}
          placeholder="搜术语、别名或释义（如：体用、用神、旬空）"
          aria-label="搜索术语"
          value={q} onChange={(e) => setQ(e.target.value)} />
        {q && <button type="button" className="btn-outline" style={{ padding: '6px 16px', fontSize: 'var(--type-data)' }}
          onClick={() => setQ('')}>清空</button>}
      </div>

      {/* 分类 */}
      <div className="slip-row" style={{ marginBottom: 14 }}>
        <button type="button" className={`slip ${category === '' ? 'active' : ''}`}
          onClick={() => setCategory('')}>全部</button>
        {(sysMeta?.categories || []).map((c) => (
          <button key={c.name} type="button" className={`slip ${category === c.name ? 'active' : ''}`}
            onClick={() => setCategory(c.name)}>
            {c.name} {c.count}
          </button>
        ))}
      </div>

      {error && <div className="notice notice-err"><b>错误</b><span className="n-body">{error}</span></div>}

      <div className="terms-layout">
        {/* 列表 */}
        <div className="terms-col">
          <div className="reg-label">
            {searching ? `搜索「${q}」（两套体系）` : category || '全部'} · {terms.length} 条
          </div>
          {loading && <div className="ink-skel" aria-hidden><span style={{ width: '70%' }} /><span style={{ width: '55%' }} /></div>}
          {!loading && terms.length === 0 && <span className="hint-line">没有匹配的术语。</span>}
          <div className="term-list">
            {terms.map((t) => (
              <button key={t.id} type="button"
                className={`term-item ${detail?.id === t.id ? 'active' : ''}`}
                onClick={() => {
                  jumpTo({ system: t.system, category: t.category, id: t.id })
                }}>
                <span className="term-name">
                  {t.name}
                  {searching && (
                    <span className="term-sys">{t.system === 'liuyao' ? '爻' : '梅'}</span>
                  )}
                </span>
                {t.alias ? <span className="term-alias">{t.alias.split('｜')[0]}</span> : null}
                <span className="term-role">{t.role}</span>
              </button>
            ))}
          </div>
        </div>

        {/* 详解 */}
        <div className="terms-col detail">
          {!detail && <span className="hint-line">点左边任意一条术语，看它的详解、原文与关联术语。</span>}
          {detail && (
            <div className="term-detail">
              <div className="td-head">
                <span className="td-name">{detail.name}</span>
                <span className="td-cat">{detail.category}</span>
              </div>
              {detail.alias && <div className="td-alias">别名：{detail.alias}</div>}
              {detail.role && <div className="td-role">一句话：{detail.role}</div>}
              {detail.detail && <div className="td-body">{detail.detail}</div>}
              {detail.source_quote && (
                <div className="texture-quote" style={{ marginTop: 10 }}>
                  <div className="tq-head">原文语录</div>
                  <div className="tq-text">「{detail.source_quote}」</div>
                  <div className="tq-src">
                    出处：{detail.source_book}{detail.source_loc ? ` · ${detail.source_loc}` : ''}
                  </div>
                </div>
              )}
              {detail.sources && <div className="td-src">收录来源：{detail.sources}</div>}
              {detail.relations?.length > 0 && (
                <>
                  <div className="yingqi-group-title">关联术语（点一下互跳）</div>
                  <div className="slip-row">
                    {detail.relations.map((r) => (
                      <button key={`${r.id}-${r.name}`} type="button"
                        className={`slip ${r.exists ? '' : 'missing'}`}
                        aria-disabled={!r.exists}
                        tabIndex={r.exists ? undefined : -1}
                        title={r.exists ? `${r.system === 'liuyao' ? '六爻' : '梅花'} · ${r.category}` : '该关联在本库中暂缺'}
                        onClick={() => {
                          if (!r.exists) return
                          jumpTo({ system: r.system, category: r.category, id: r.id })
                        }}>
                        {r.name}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      <p className="stub-line" style={{ marginTop: 18 }}>
        词条来自《梅花易数》《增广校正梅花易数》《增删卜易》《卜筮正宗》等典籍的架构性整理；
        详情里的「原文语录」是逐字摘录，可用于核对解卦正文引用的出处。
      </p>

      <div className="footer-caution" style={{ marginTop: 18 }}>
        <b>郑重提示</b>
        请不要迷信。本站所有功能只是用程序的方式展示传统的占卜行为，没有神力，也不会替你做任何决定。
        术语与原文仅供文化研究参考，不构成任何专业建议；遇到实际难题请通过社会途径寻求帮助。
      </div>
    </div>
  )
}
