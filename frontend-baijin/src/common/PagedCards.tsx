import { useEffect, useState, type ReactNode } from 'react'

/**
 * 左右翻页卡片：把同一类信息按条分组，一屏一条，左右按钮（或点圆点）翻页。
 * 为什么这么做（用户要求 + taste-skill 的同一条规则）：
 *  · 长列表读着累、页面被拉得很长；
 *  · 一屏一条才能把字放大，老人也看得清；
 *  · 同类信息本来就该按条阅读，而不是挤成一竖列。
 * items 顺序即阅读顺序；标题栏显示"第几条 / 共几条"。
 */
export default function PagedCards({
  items, label, startAt = 0,
}: {
  items: { key: string; title?: string; body: ReactNode }[]
  label?: string
  startAt?: number
}) {
  const [idx, setIdx] = useState(startAt)
  const total = items.length

  useEffect(() => {
    if (idx >= total) setIdx(Math.max(0, total - 1))
  }, [total, idx])

  if (total === 0) return null
  const cur = items[Math.min(idx, total - 1)]

  return (
    <div className="paged">
      <div className="paged-bar">
        <button
          type="button"
          className="btn-outline"
          style={{ padding: '7px 18px' }}
          disabled={idx === 0}
          onClick={() => setIdx((i) => Math.max(0, i - 1))}
          aria-label="上一条"
        >
          ← 上一条
        </button>
        <span className="paged-counter">
          {label ? `${label}　` : ''}
          <b>{idx + 1}</b> / {total}
          {cur.title ? <span className="paged-cur">　{cur.title}</span> : null}
        </span>
        <button
          type="button"
          className="btn-outline"
          style={{ padding: '7px 18px' }}
          disabled={idx === total - 1}
          onClick={() => setIdx((i) => Math.min(total - 1, i + 1))}
          aria-label="下一条"
        >
          下一条 →
        </button>
      </div>

      <div className="paged-dots" aria-hidden>
        {items.map((it, i) => (
          <button
            key={it.key}
            type="button"
            tabIndex={-1}
            className={`paged-dot ${i === idx ? 'on' : ''}`}
            onClick={() => setIdx(i)}
            aria-label={`第 ${i + 1} 条`}
          />
        ))}
      </div>

      <div className="paged-body" key={cur.key}>
        {cur.body}
      </div>
    </div>
  )
}
