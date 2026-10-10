import { useState } from 'react'
import { fetchQuotes, type QuoteData } from '../api/mingju'

/**
 * 典籍原文核对（点一下展开）
 * 后端按出处键在 books/ 库里查：查到就显示原文与位置；没收录就如实写"原文待录，
 * 可在 books/ 库内检索书名核对"——**不代拟原文**。
 */
export default function QuoteRef({ k, label }: { k: string; label?: string }) {
  const [data, setData] = useState<QuoteData | null>(null)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const toggle = async () => {
    if (open) { setOpen(false); return }
    setOpen(true)
    if (data || loading) return
    setLoading(true)
    try {
      const res = await fetchQuotes([k])
      setData(res[k] || null)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <span className="quote-ref">
      <button type="button" className="quote-chip" onClick={toggle} title="点一下核对原文">
        {label || k}
        <span aria-hidden>{open ? ' ▾' : ' ▸'}</span>
      </button>
      {open && (
        <span className="quote-body">
          {loading && <span className="hint-line">正在取原文…</span>}
          {!loading && data?.text && (
            <>
              <span className="qb-text">「{data.text}」</span>
              <span className="qb-src">
                ——{data.book}{data.loc ? ` · ${data.loc}` : ''}
              </span>
            </>
          )}
          {!loading && !data?.text && (
            <span className="qb-src">
              原文待录：{data?.note || '该出处暂未录入原文索引，可在 books/ 库内检索书名核对'}
            </span>
          )}
        </span>
      )}
    </span>
  )
}
