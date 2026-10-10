import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Wheel } from './Wheel'
import type { RegionCity, RegionProvince } from '../api/bazi'

/**
 * 八字的两个选择弹层：时间滚轮 + 地区三级选择。
 * 弹层样式与整站一致：宣纸卡面、发丝线、楷体标签、金箔主按钮；
 * 遮罩用暖墨色半透明，点遮罩关闭。
 */

function ModalShell({ title, onClose, children, footer }: {
  title: string
  onClose: () => void
  children: React.ReactNode
  footer?: React.ReactNode
}) {
  const boxRef = useRef<HTMLDivElement | null>(null)
  const titleId = useRef(`modal-title-${Math.random().toString(36).slice(2)}`).current
  const openerRef = useRef<Element | null>(document.activeElement)

  useEffect(() => {
    const box = boxRef.current
    if (!box) return
    const focusables = () => Array.from(
      box.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((el) => !el.hasAttribute('disabled') && el.offsetParent !== null)
    focusables()[0]?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const list = focusables()
      if (list.length === 0) return
      const first = list[0]
      const last = list[list.length - 1]
      const active = document.activeElement
      if (event.shiftKey) {
        if (active === first || !box.contains(active)) { event.preventDefault(); last.focus() }
      } else if (active === last || !box.contains(active)) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      const opener = openerRef.current
      if (opener instanceof HTMLElement) opener.focus()
    }
  }, [onClose])

  return createPortal(
    <div className="modal-mask" onClick={onClose}>
      <div ref={boxRef} className="modal-box picker-box" role="dialog" aria-modal="true" aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}>
        <div className="modal-title" id={titleId}>{title}</div>
        {children}
        {footer && <div className="btn-row" style={{ marginTop: 16, justifyContent: 'flex-end' }}>{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}

/* ==================== 时间滚轮 ==================== */

/** 年份范围：1900 – 今年（C6，2026-10 放宽：旧端 1900 起，此前新端 1940 起排不了更早的生辰） */
const YEAR_MIN = 1900
const YEAR_MAX = new Date().getFullYear()

function daysInMonth(y: number, m: number): number {
  return new Date(y, m, 0).getDate()
}
const HOURS = Array.from({ length: 24 }, (_, i) => i)
const MINUTES = Array.from({ length: 60 }, (_, i) => i)

export function TimePickerModal({
  calendar, lunarDays, leapMonth,
  init, onClose, onOk,
}: {
  calendar: 'solar' | 'lunar'
  lunarDays: number
  leapMonth: number
  init: { y: number; m: number; d: number; leap: boolean; hour: number; minute: number }
  onClose: () => void
  onOk: (v: { y: number; m: number; d: number; leap: boolean; hour: number; minute: number }) => void
}) {
  const [y, setY] = useState(init.y)
  const [m, setM] = useState(init.m)
  /** 公历日数按实际月份天数（C5，2026-10 补：此前固定 31 天，选 2 月 31 日会撞后端校验） */
  const solarDays = useMemo(() => daysInMonth(y, m), [y, m])
  const [d, setD] = useState(Math.min(init.d, lunarDays))
  const [leap, setLeap] = useState(init.leap)
  const [h, setH] = useState(init.hour)
  const [mi, setMi] = useState(init.minute)

  const monthItems = useMemo(() => {
    const base = Array.from({ length: 12 }, (_, i) => `${i + 1} 月`)
    if (leapMonth > 0) {
      base.splice(leapMonth, 0, `闰 ${leapMonth} 月`)
    }
    return base
  }, [leapMonth])

  const monthIndexToValue = (idx: number): { m: number; leap: boolean } => {
    if (calendar === 'lunar' && leapMonth > 0 && idx === leapMonth) {
      return { m: leapMonth, leap: true }
    }
    const real = calendar === 'lunar' && leapMonth > 0 && idx > leapMonth ? idx - 1 : idx
    return { m: real + 1, leap: false }
  }
  const valueToMonthIndex = (m: number, lp: boolean): number => {
    if (calendar === 'lunar' && lp && leapMonth > 0) return leapMonth
    if (calendar === 'lunar' && leapMonth > 0 && m > leapMonth) return m
    return m - 1
  }

  return (
    <ModalShell
      title="选择出生时间"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn-outline" onClick={onClose}>取消</button>
          <button
            type="button"
            className="btn"
            style={{ padding: '9px 24px' }}
            onClick={() => onOk({ y, m, d, leap, hour: h, minute: mi })}
          >
            确 定
          </button>
        </>
      }
    >
      <div className="picker-wheels">
        <Wheel label="年" items={Array.from({ length: YEAR_MAX - YEAR_MIN + 1 }, (_, i) => `${YEAR_MIN + i}`)}
          index={Math.max(0, y - YEAR_MIN)}
          onChange={(i) => { setY(YEAR_MIN + i); setD(Math.min(d, calendar === 'lunar' ? lunarDays : daysInMonth(YEAR_MIN + i, m))) }}
          width={96} />
        {calendar === 'lunar' ? (
          <Wheel
            label="月"
            items={monthItems}
            index={Math.max(0, valueToMonthIndex(m, leap))}
            onChange={(idx) => { const r = monthIndexToValue(idx); setM(r.m); setLeap(r.leap) }}
            width={104}
          />
        ) : (
          <Wheel label="月" items={Array.from({ length: 12 }, (_, i) => `${i + 1} 月`)} index={m - 1}
            onChange={(i) => { setM(i + 1); setD(Math.min(d, daysInMonth(y, i + 1))) }} width={96} />
        )}
        <Wheel
          label="日"
          items={Array.from({ length: calendar === 'lunar' ? lunarDays : solarDays }, (_, i) => `${i + 1} 日`)}
          index={Math.max(0, Math.min(d, (calendar === 'lunar' ? lunarDays : solarDays)) - 1)}
          onChange={(i) => setD(i + 1)}
          width={96}
        />
        <Wheel label="时" items={HOURS.map((v) => `${String(v).padStart(2, '0')} 时`)} index={h} onChange={setH} width={104} />
        <Wheel label="分" items={MINUTES.map((v) => `${String(v).padStart(2, '0')} 分`)} index={mi} onChange={setMi} width={104} />
      </div>
      <div className="d-src">
        上下滚动或直接点某一项即可选中，松手自动对准中间。农历的闰月与每月天数按该年历表给出；公历日数按当月实际天数。
      </div>
    </ModalShell>
  )
}

/* ==================== 地区选择（省 / 市 / 区县 + 搜索） ==================== */

export function RegionModal({
  provinces, init, onClose, onOk,
}: {
  provinces: RegionProvince[]
  init: { p: number; c: number; d: number }
  onClose: () => void
  onOk: (sel: { p: number; c: number; d: number }) => void
}) {
  const [tab, setTab] = useState<'p' | 'c' | 'd'>('p')
  const [p, setP] = useState(init.p)
  const [c, setC] = useState(init.c)
  const [d, setD] = useState(init.d)
  const [q, setQ] = useState('')

  const prov: RegionProvince | null = p >= 0 ? provinces[p] : null
  const city: RegionCity | null = prov && c >= 0 ? prov.c[c] : null

  const list = useMemo(() => {
    const kw = q.trim()
    if (tab === 'p') {
      return provinces.map((x, i) => ({ name: x.n, i })).filter((x) => !kw || x.name.includes(kw))
    }
    if (tab === 'c' && prov) {
      return prov.c.map((x, i) => ({ name: x.n, i })).filter((x) => !kw || x.name.includes(kw))
    }
    if (tab === 'd' && city) {
      return (city.d || []).map((x, i) => ({ name: x.n, i })).filter((x) => !kw || x.name.includes(kw))
    }
    return []
  }, [tab, q, provinces, prov, city])

  const pick = (i: number) => {
    if (tab === 'p') { setP(i); setC(-1); setD(-1); setTab('c'); setQ('') }
    else if (tab === 'c') { setC(i); setD(-1); setTab('d'); setQ('') }
    else { setD(i); setTab('d') }
  }

  const picked = { p, c, d }
  const pickedName = [
    p >= 0 ? provinces[p]?.n : '',
    p >= 0 && c >= 0 ? provinces[p]?.c[c]?.n : '',
    p >= 0 && c >= 0 && d >= 0 ? provinces[p]?.c[c]?.d?.[d]?.n : '',
  ].filter(Boolean).join(' · ')

  return (
    <ModalShell
      title="选择出生地区"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn-outline" onClick={onClose}>取消</button>
          <button
            type="button"
            className="btn"
            style={{ padding: '9px 24px' }}
            disabled={p < 0}
            onClick={() => onOk(picked)}
          >
            确 定
          </button>
        </>
      }
    >
      <div className="slip-row" role="tablist" aria-label="地区层级" style={{ marginBottom: 10 }}>
        {(['p', 'c', 'd'] as const).map((t, i) => (
          <button key={t} type="button"
            className={`slip ${tab === t ? 'active' : ''}`}
            role="tab"
            id={`region-tab-${t}`}
            aria-selected={tab === t}
            aria-controls="region-list"
            disabled={(i === 1 && p < 0) || (i === 2 && (p < 0 || c < 0))}
            onClick={() => setTab(t)}>
            {t === 'p' ? '省份' : t === 'c' ? '城市' : '区县'}
          </button>
        ))}
        {(pickedName || q) && <span className="hint-line" style={{ alignSelf: 'center' }}>{pickedName}</span>}
      </div>
      <input className="input" style={{ marginBottom: 10 }} placeholder="输入名称过滤" value={q}
        aria-label="输入省市区名称过滤" onChange={(e) => setQ(e.target.value)} />
      <div className="region-list" role="tabpanel" id="region-list" aria-labelledby={`region-tab-${tab}`}>
        {list.length === 0 && <span className="hint-line">没有匹配的地区。</span>}
        {list.map((x) => (
          <button type="button" className={`region-item ${(tab === 'p' ? p : tab === 'c' ? c : d) === x.i ? 'on' : ''}`}
            key={`${x.name}-${x.i}`} onClick={() => pick(x.i)}>
            {x.name}
          </button>
        ))}
      </div>
      <div className="d-src" style={{ marginTop: 8 }}>
        经纬度取市一级；区县只用于确认归属。确定后按当地经度做真太阳时校正。
      </div>
    </ModalShell>
  )
}
