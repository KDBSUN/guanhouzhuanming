import { useEffect, useRef, useState } from 'react'

/**
 * 滚轮选择器（CSS scroll-snap 实现）
 * · 上下滚动或直接点某一项都可以选中，松手自动吸附到中间；
 * · 中间一格放大加粗，上下渐淡——像转盘，但实现只用原生滚动；
 * · 触屏与鼠标滚轮都顺手，不写拖拽物理。
 */
const ITEM_H = 46
const VISIBLE = 5

export function Wheel({
  items, index, onChange, width = 110, label,
}: {
  items: string[]
  index: number
  onChange: (i: number) => void
  width?: number
  label?: string
}) {
  const ref = useRef<HTMLDivElement | null>(null)
  const programmatic = useRef(false)
  const timer = useRef<number | null>(null)
  const [center, setCenter] = useState(index)

  /* index 被外部改变（如切换年导致日数变化）时，滚到对应位置 */
  useEffect(() => {
    const el = ref.current
    if (!el) return
    programmatic.current = true
    el.scrollTop = index * ITEM_H
    setCenter(index)
    window.setTimeout(() => { programmatic.current = false }, 0)
  }, [index, items.length])

  const onScroll = () => {
    if (programmatic.current) return
    const el = ref.current
    if (!el) return
    const i = Math.min(items.length - 1, Math.max(0, Math.round(el.scrollTop / ITEM_H)))
    setCenter(i)
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      if (i !== index) onChange(i)
    }, 120)
  }

  const pad = ((VISIBLE - 1) / 2) * ITEM_H

  /* 键盘：listbox 模式的方向键 / Home / End 导航 */
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return
    const el = ref.current
    if (!el) return
    e.preventDefault()
    let next = center
    if (e.key === 'ArrowDown') next = Math.min(items.length - 1, center + 1)
    else if (e.key === 'ArrowUp') next = Math.max(0, center - 1)
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = items.length - 1
    el.scrollTo({ top: next * ITEM_H, behavior: 'smooth' })
    setCenter(next)
    if (next !== index) onChange(next)
  }

  return (
    <div className="wheel-col" style={{ width }}>
      {label && <span className="wheel-label">{label}</span>}
      <div className="wheel" ref={ref} onScroll={onScroll} onKeyDown={onKeyDown} tabIndex={0}
        style={{ height: ITEM_H * VISIBLE }} role="listbox" aria-label={label}>
        <div style={{ height: pad }} />
        {items.map((it, i) => (
          <div
            key={`${it}-${i}`}
            role="option"
            aria-selected={i === center}
            className={`wheel-item ${i === center ? 'center' : ''}`}
            style={{ height: ITEM_H }}
            onClick={() => {
              const el = ref.current
              if (el) el.scrollTo({ top: i * ITEM_H, behavior: 'smooth' })
            }}
          >
            {it}
          </div>
        ))}
        <div style={{ height: pad }} />
      </div>
    </div>
  )
}
