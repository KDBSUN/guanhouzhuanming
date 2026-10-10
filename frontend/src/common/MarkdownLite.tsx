/**
 * 轻量 Markdown 渲染（只覆盖 AI 解卦正文实际会用到的语法）：
 *   ## 二级标题 / ### 三级标题（后端提示词要求的分节标题）
 *   - / · / 1. 列表
 *   **加粗**
 *   > 引用块（连续多行合成一段）
 *   | 表格 |（GFM 表格：表头行 + |---| 分隔行 + 若干数据行，支持 :--: 对齐）
 * 不做完整 Markdown —— 解卦正文是模型输出，越简单的解析越不容易把内容渲染坏。
 *
 * 流式渲染的注意点：正文是一段段吐出来的，表格的分隔行可能还没到。
 * 所以"是不是表格"要看下一行——下一行不是分隔行时，这一行就按普通段落渲染，
 * 不会因为半个表格把后面的内容吃掉。
 */
import type { ReactNode } from 'react'

function inline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = []
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  parts.forEach((p, i) => {
    if (p.startsWith('**') && p.endsWith('**') && p.length > 4) {
      out.push(<strong key={`${keyBase}-b${i}`}>{p.slice(2, -2)}</strong>)
    } else if (p) {
      out.push(p)
    }
  })
  return out
}

/* ---------- 表格 ---------- */

/** `| a | b |` → ['a','b']（首尾竖线可有可无） */
function cellsof(row: string): string[] {
  let s = row.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|')) s = s.slice(0, -1)
  return s.split('|').map((c) => c.trim())
}

function isTableRow(t: string): boolean {
  return t.includes('|') && !t.startsWith('>')
}

/** 分隔行：| --- | :--: | ---: |，也容忍流式还没吐完的 |--- */
function isSeparator(t: string): boolean {
  if (!t.includes('-') || !/^[|\s:-]+$/.test(t)) return false
  const cs = cellsof(t)
  return cs.length > 0 && cs.every((c) => /^:?-+:?$/.test(c))
}

/** 对齐：:--- 左（默认）/ :--: 中 / ---: 右 */
function alignOf(sep: string): 'left' | 'center' | 'right' {
  const c = cellsof(sep)[0] || ''
  if (c.startsWith(':') && c.endsWith(':')) return 'center'
  if (c.endsWith(':')) return 'right'
  return 'left'
}

/* ---------- 正文 ---------- */

export default function MarkdownLite({ text }: { text: string }) {
  if (!text) return null
  const blocks: ReactNode[] = []
  const src = text.split('\n')
  let list: string[] = []
  let key = 0

  const flushList = () => {
    if (!list.length) return
    const k = key++
    blocks.push(
      <ul className="md-list" key={`ul-${k}`}>
        {list.map((item, i) => <li key={i}>{inline(item, `li-${k}-${i}`)}</li>)}
      </ul>,
    )
    list = []
  }

  for (let i = 0; i < src.length; i++) {
    const t = src[i].trimEnd().trim()
    if (!t) { flushList(); continue }

    /* 表格：本行是表格行，且下一行是分隔行 */
    if (isTableRow(t) && i + 1 < src.length && isSeparator(src[i + 1].trim())) {
      flushList()
      const head = cellsof(t)
      const sep = src[i + 1].trim()
      const aligns = cellsof(sep).map(alignOf)
      const rows: string[][] = []
      i += 2
      while (i < src.length) {
        const r = src[i].trim()
        if (!r || !isTableRow(r) || isSeparator(r)) { i--; break }
        rows.push(cellsof(r))
        i++
      }
      const k = key++
      blocks.push(
        <div className="md-table-wrap" key={`tb-${k}`}>
          <table className="md-table">
            <thead>
              <tr>
                {head.map((c, ci) => (
                  <th key={ci} style={{ textAlign: aligns[ci] || 'left' }}>
                    {inline(c, `th-${k}-${ci}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  {head.map((_, ci) => (
                    <td key={ci} style={{ textAlign: aligns[ci] || 'left' }}>
                      {inline(r[ci] || '', `td-${k}-${ri}-${ci}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    /* 引用块：连续以 > 开头的行合成一块；块内的空引用行（单独一个 >）分段 */
    if (t.startsWith('>')) {
      flushList()
      const paras: string[] = []
      let cur: string[] = []
      while (i < src.length) {
        const q = src[i].trim()
        if (!q.startsWith('>')) break
        const body = q.replace(/^>\s?/, '')
        if (!body.trim()) { if (cur.length) { paras.push(cur.join('')); cur = [] } }
        else cur.push(body)
        i++
      }
      if (cur.length) paras.push(cur.join(''))
      i--
      const k = key++
      blocks.push(
        <blockquote className="md-quote" key={`bq-${k}`}>
          {paras.map((p, pi) => <p key={pi}>{inline(p, `bq-${k}-${pi}`)}</p>)}
        </blockquote>,
      )
      continue
    }

    if (t.startsWith('### ')) {
      flushList()
      const k = key++
      blocks.push(<h4 className="md-h3" key={`h3-${k}`}>{inline(t.slice(4), `h3-${k}`)}</h4>)
      continue
    }
    if (t.startsWith('## ')) {
      flushList()
      const k = key++
      blocks.push(<h3 className="md-h2" key={`h2-${k}`}>{inline(t.slice(3), `h2-${k}`)}</h3>)
      continue
    }
    if (/^([-•·]|\d+[.、])\s*/.test(t)) {
      list.push(t.replace(/^([-•·]|\d+[.、])\s*/, ''))
      continue
    }
    flushList()
    const k = key++
    blocks.push(<p className="md-p" key={`p-${k}`}>{inline(t, `p-${k}`)}</p>)
  }
  flushList()

  return <div className="md-body">{blocks}</div>
}
