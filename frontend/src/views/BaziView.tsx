import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FishTail } from '../art/book'
import {
  lunarConvert, lunarMeta, paipan, regionLngLat, regions,
  type LunarMeta, type RegionCity, type RegionProvince,
} from '../api/bazi'
import { deleteProfile, getProfile, logBaziPaipan, saveProfile, type MingjuProfile } from '../api/mingju'
import { saveRecord } from '../api/records'
import DayunPanel from './DayunPanel'
import ProfileLine from '../common/ProfileLine'
import QuoteRef from '../common/QuoteRef'
import { TimePickerModal, RegionModal } from '../common/BaziPickers'
import type { BaziData, BaziDayunStep, BaziPillar } from '../api/types'

/* ============================================================
   四柱八字 —— 已接后端
   排盘（纯计算，不花 AI 额度）：四柱 / 十神 / 藏干 / 纳音 / 地势 /
   自坐 / 旬空 / 干支体性 / 五行分布 / 格局 / 调候 / 喜忌 /
   大运流年 / 命宫胎元（神煞已按四条检验 F1 删展示，2026-09-24）
   存为命局档案后，梅花与六爻的命卦校验、逐日宜忌表才有依据。
   ============================================================ */

const SHICHEN = [
  { name: '子时', range: '23:00–00:59', hour: 23 },
  { name: '丑时', range: '01:00–02:59', hour: 2 },
  { name: '寅时', range: '03:00–04:59', hour: 4 },
  { name: '卯时', range: '05:00–06:59', hour: 6 },
  { name: '辰时', range: '07:00–08:59', hour: 8 },
  { name: '巳时', range: '09:00–10:59', hour: 10 },
  { name: '午时', range: '11:00–12:59', hour: 12 },
  { name: '未时', range: '13:00–14:59', hour: 14 },
  { name: '申时', range: '15:00–16:59', hour: 16 },
  { name: '酉时', range: '17:00–18:59', hour: 18 },
  { name: '戌时', range: '19:00–20:59', hour: 20 },
  { name: '亥时', range: '21:00–22:59', hour: 22 },
]

const shichenOf = (h: number) => SHICHEN[Math.floor(((h + 1) % 24) / 2)]

/* ============================================================
   排盘前预览（2026-10 与旧前端对齐搬回：C1 换算预览、C2 夏令时窗口判定、C3 校时多层预览）
   口径与后端一致（backend/main.py _parse_dt 的夏令时处理）：1986–1991，
   1986 特例 5 月 4 日起；1987–1991 每年 4 月 11 日后首个周日 03:00 至 9 月 11 日后首个周日 02:00
   ============================================================ */

const CN_NUM = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
const pad2 = (n: number) => String(n).padStart(2, '0')

function dayOfYear(y: number, m: number, d: number): number {
  const t0 = new Date(y, 0, 0).getTime()
  const t1 = new Date(y, m - 1, d).getTime()
  return Math.round((t1 - t0) / 86400000)
}

function eotMinutes(y: number, m: number, d: number): number {
  const n = dayOfYear(y, m, d)
  const B = ((n - 1) * 360 / 365) * Math.PI / 180
  return 229.18 * (
    0.000075 + 0.001868 * Math.cos(B) - 0.032077 * Math.sin(B)
    - 0.014615 * Math.cos(2 * B) - 0.04089 * Math.sin(2 * B)
  )
}

/** 公历 → 农历预览（浏览器内置中国历法 Intl） */
function lunarPreview(y: number, m: number, d: number): string | null {
  try {
    const fmt = new Intl.DateTimeFormat('zh-CN-u-ca-chinese', { year: 'numeric', month: 'long', day: 'numeric' })
    const parts = fmt.formatToParts(new Date(y, m - 1, d, 12))
    const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
    let month = get('month')
    month = month.replace('十一月', '冬月').replace('十二月', '腊月').replace('一月', '正月')
    const dayNum = Number(get('day'))
    let dayCn: string
    if (dayNum === 1) dayCn = '初一'
    else if (dayNum <= 10) dayCn = `初${CN_NUM[dayNum]}`
    else if (dayNum < 20) dayCn = `十${CN_NUM[dayNum - 10]}`
    else if (dayNum === 20) dayCn = '二十'
    else if (dayNum < 30) dayCn = `廿${CN_NUM[dayNum - 10]}`
    else dayCn = '三十'
    return `农历${get('yearName')}年 ${month}${dayCn}`
  } catch {
    return null
  }
}

function firstSundayOnOrAfter(y: number, m: number, d0: number): Date {
  const dt = new Date(y, m - 1, d0, 12)
  const delta = (7 - dt.getDay()) % 7
  return new Date(y, m - 1, d0 + delta, 12)
}

function chinaDstClockWindow(y: number): { start: Date; end: Date } | null {
  if (y < 1986 || y > 1991) return null
  const startBase = y === 1986 ? new Date(1986, 4, 4) : firstSundayOnOrAfter(y, 4, 11)
  const endDay = firstSundayOnOrAfter(y, 9, 11)
  return {
    start: new Date(startBase.getFullYear(), startBase.getMonth(), startBase.getDate(), 3, 0),
    end: new Date(endDay.getFullYear(), endDay.getMonth(), endDay.getDate(), 2, 0),
  }
}

function dstStatus(y: number, m: number, d: number, h: number, min: number):
  { applied: boolean; restored?: Date; window?: string; note: string } {
  if (y < 1986 || y > 1991) return { applied: false, note: `${y} 年未实行夏令时（仅 1986–1991）` }
  const win = chinaDstClockWindow(y)!
  const fmt = (dt: Date) => `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())} ${pad2(dt.getHours())}:00`
  const t = new Date(y, m - 1, d, h, min)
  if (t >= win.start && t < win.end) {
    return {
      applied: true,
      restored: new Date(t.getTime() - 3600000),
      window: `${fmt(win.start)} ~ ${fmt(win.end)}`,
      note: '出生在夏令时区间内，已还原标准时间',
    }
  }
  return { applied: false, window: `${fmt(win.start)} ~ ${fmt(win.end)}`, note: '出生时刻不在当年夏令时区间内，无需还原' }
}

export default function BaziView({ replay = null }: { replay?: Record<string, unknown> | null }) {
  /* 表单 */
  const [name, setName] = useState('')
  const [calendar, setCalendar] = useState<'solar' | 'lunar'>('solar')
  const [gender, setGender] = useState<number>(1)
  const [solarDate, setSolarDate] = useState('1995-06-15')
  const [ly, setLy] = useState(1995)
  const [lm, setLm] = useState(5)
  const [ld, setLd] = useState(18)
  const [leap, setLeap] = useState(false)
  const [meta, setMeta] = useState<LunarMeta | null>(null)
  const [hour, setHour] = useState(12)
  const [minute, setMinute] = useState(0)

  /* 地区 */
  const [provs, setProvs] = useState<RegionProvince[]>([])
  const [pidx, setPidx] = useState(-1)
  const [cidx, setCidx] = useState(-1)
  const [didx, setDidx] = useState(-1)
  const [regionErr, setRegionErr] = useState('')

  const [trueSolar, setTrueSolar] = useState(true)
  const [dst, setDst] = useState(false)
  /** 时间滚轮弹层 / 地区弹层 */
  const [timeOpen, setTimeOpen] = useState(false)
  const [regionOpen, setRegionOpen] = useState(false)

  /* 结果 */
  const [data, setData] = useState<BaziData | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [profile, setProfile] = useState<MingjuProfile | null>(null)
  const [dayunIdx, setDayunIdx] = useState<number | null>(null)
  /** 排盘时的表单快照：表单未变时，输入面板农历行直接显示排盘结果（lunar_python 口径），
      避免浏览器 Intl 农历与排盘引擎对个别日期差一天（2026-11 勘误） */
  const [castKey, setCastKey] = useState('')
  /** 排盘时实际生效的出生参数快照（大运流年详批用；表单再改也不影响已出的盘） */
  const [castInput, setCastInput] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    getProfile().then(setProfile).catch(() => setProfile(null))
    regions().then(setProvs).catch(() => setRegionErr('地区数据没取到，可先不用地区，直接按默认经度 120° 排盘'))
  }, [])

  /* ---------- 记录回放：直接还原当时的排盘结果与出生信息 ---------- */
  const replayRef = useRef(false)
  useEffect(() => {
    if (!replay) return
    replayRef.current = true
    const d = replay.data as BaziData | undefined
    if (d) setData(d)
    if (typeof replay.birth === 'object' && replay.birth) {
      const b = replay.birth as Record<string, unknown>
      const cal: 'solar' | 'lunar' = b.calendar === 'lunar' ? 'lunar' : 'solar'
      if (typeof b.year === 'number') setLy(b.year)
      if (typeof b.month === 'number') setLm(b.month)
      if (typeof b.day === 'number') setLd(b.day)
      if (typeof b.hour === 'number') setHour(b.hour)
      if (typeof b.minute === 'number') setMinute(b.minute)
      if (b.gender === 0 || b.gender === 1) setGender(b.gender)
      setCalendar(cal)
      // 公历日期框必须一并还原（2026-10-06 修）：此前只还原农历字段，公历记录回放时
      // 表单停在写死的默认值 1995-06-15——日期预览、重新排盘都拿这个默认值去算。
      if (cal === 'solar' && typeof b.year === 'number'
          && typeof b.month === 'number' && typeof b.day === 'number') {
        setSolarDate(`${b.year}-${pad2(b.month)}-${pad2(b.day)}`)
      }
      if (typeof b.leap_month === 'boolean') setLeap(b.leap_month)
      if (typeof b.dst === 'boolean') setDst(b.dst)
      if (typeof b.true_solar === 'boolean') setTrueSolar(b.true_solar)
    }
    // 回放也要能出大运流年详批：直接用记录里存的出生参数快照
    if (typeof replay.birth === 'object' && replay.birth) {
      setCastInput(replay.birth as Record<string, unknown>)
    }
    setMsg('这是从记录里回放的排盘结果（不会重复留痕）。')
  }, [replay])

  /* 农历年份变化 → 取闰月与各月天数 */
  useEffect(() => {
    if (calendar !== 'lunar') return
    let alive = true
    lunarMeta(ly).then((m) => { if (alive) setMeta(m) }).catch(() => { if (alive) setMeta(null) })
    return () => { alive = false }
  }, [calendar, ly])

  /* C1：农历 → 公历实时换算预览（250ms 防抖，与旧前端一致） */
  const [lunarConv, setLunarConv] = useState('')
  useEffect(() => {
    if (calendar !== 'lunar') { setLunarConv(''); return }
    const maxDay = meta?.months?.[lm - 1] ?? 30
    const d = Math.min(ld, maxDay)
    const timer = window.setTimeout(() => {
      lunarConvert(ly, lm, d, leap).then((m) => {
        const c = m.conversion as { solar?: string; lunar?: string } | undefined
        setLunarConv(c?.solar ? `${c.solar}` : (c?.lunar ? `${c.lunar}` : ''))
      }).catch(() => setLunarConv(''))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [calendar, ly, lm, ld, leap, meta])

  const prov = pidx >= 0 ? provs[pidx] : null
  const city: RegionCity | null = prov && cidx >= 0 ? prov.c[cidx] : null
  const lnglat = regionLngLat(prov, city)

  const lunarDays = useMemo(() => {
    if (calendar !== 'lunar') return 30
    const arr = (meta?.months as number[] | undefined) || undefined
    if (arr && arr.length >= lm) return arr[lm - 1] || 30
    const map = meta?.month_days as Record<string, number> | undefined
    if (map && map[String(lm)]) return map[String(lm)]
    return 30
  }, [calendar, meta, lm])

  const leapMonth = typeof meta?.leap_month === 'number' ? meta!.leap_month : 0

  /* C2/C3：排盘前校时预览（与旧前端同口径：夏令时窗口 → 经度差 → 均时差） */
  const solarParts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(solarDate)
  const sy = solarParts ? Number(solarParts[1]) : ly
  const sm = solarParts ? Number(solarParts[2]) : lm
  const sd = solarParts ? Number(solarParts[3]) : Math.min(ld, lunarDays)
  const solarLunarLine = calendar === 'solar'
    ? (data?.lunar && castKey === `${sy}-${sm}-${sd}`
      ? `农历${data.lunar}`
      : lunarPreview(sy, sm, sd))
    : null
  const longitude = lnglat ? lnglat.lng : 120
  const lonCorr = (longitude - 120) * 4
  const eot = eotMinutes(sy, sm, sd)
  const dstSt = useMemo(() => dstStatus(sy, sm, sd, hour, minute), [sy, sm, sd, hour, minute])
  const correctionPreview = useMemo(() => {
    const lines: string[] = []
    let base = new Date(sy, sm - 1, sd, hour, minute)
    const rawTxt = `${sy}年${sm}月${sd}日 ${pad2(hour)}:${pad2(minute)}`
    const sign = (v: number) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(1)
    if (dstSt.applied && dstSt.restored) {
      const r = dstSt.restored
      lines.push(`夏令时记录 ${rawTxt} → 还原标准时间 ${r.getFullYear()}年${r.getMonth() + 1}月${r.getDate()}日 ${pad2(r.getHours())}:${pad2(r.getMinutes())}`)
      base = r
    } else if (dst) {
      lines.push(dstSt.note)
    }
    if (trueSolar) {
      if (!lnglat) lines.push('真太阳时：请选择出生地区（未选按东经120°无经度校正）')
      const dt = new Date(base.getTime() + (lonCorr + eot) * 60000)
      lines.push(`真太阳时 ${dt.getFullYear()}年${dt.getMonth() + 1}月${dt.getDate()}日 ${pad2(dt.getHours())}:${pad2(dt.getMinutes())}（经度差 ${sign(lonCorr)} 分 + 均时差 ${sign(eot)} 分）`)
    }
    return lines
  }, [sy, sm, sd, hour, minute, dst, dstSt, trueSolar, lnglat, lonCorr, eot])

  /* ---------- 组装输入 ---------- */
  const buildInput = useCallback(() => {
    let year: number, month: number, day: number
    if (calendar === 'solar') {
      const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(solarDate)
      if (!m) return '请选择有效的出生日期'
      year = Number(m[1]); month = Number(m[2]); day = Number(m[3])
    } else {
      if (leap && leapMonth !== lm) return '所选月份没有闰月，请重新选择'
      year = ly; month = lm; day = Math.min(ld, lunarDays)
    }
    return {
      year, month, day, hour, minute, gender, calendar,
      leap_month: calendar === 'lunar' ? leap : false,
      dst, true_solar: trueSolar,
      longitude: lnglat ? lnglat.lng : 120,
      latitude: lnglat ? lnglat.lat : undefined,
    }
  }, [calendar, solarDate, ly, lm, ld, leap, leapMonth, lunarDays, hour, minute, gender, dst, trueSolar, lnglat])

  /* ---------- 排盘 ---------- */
  const cast = useCallback(async () => {
    const input = buildInput()
    if (typeof input === 'string') { setError(input); return }
    setLoading(true); setError(''); setMsg('')
    try {
      const d = await paipan(input)
      setData(d)
      setCastKey(`${input.year}-${input.month}-${input.day}`)
      setCastInput(input as unknown as Record<string, unknown>)
      setDayunIdx(null)
      /* 排盘留痕：写进校验台账（check_log 的 kind=bazi 行），关页不丢、可事后回看。
         尽力而为——失败不影响排盘主流程（旧前端同一约定）。 */
      void logBaziPaipan({
        name: name.trim(),
        solar: d.solar,
        lunar: d.lunar,
        gender: d.gender,
        pillars: d.bazi.map((p) => p.ganzhi).join(' '),
      })
    } catch (err) {
      setError((err as Error).message || '排盘失败')
    } finally {
      setLoading(false)
    }
  }, [buildInput, name])

  /* ---------- 存为命局档案 ---------- */
  const save = useCallback(async () => {
    const input = buildInput()
    if (typeof input === 'string') { setError(input); return }
    setSaving(true); setError(''); setMsg('')
    try {
      const res = await saveProfile(input)
      const p = await getProfile()
      setProfile(p)
      if (!data) {
        const d = await paipan(input).catch(() => null)
        if (d) { setData(d); setCastKey(`${input.year}-${input.month}-${input.day}`) }
      }
      setMsg(`命局档案已保存（档案号 ${res.id.slice(0, 8)}…）。梅花、六爻的命卦校验与逐日宜忌表现在可用。`)
    } catch (err) {
      setError((err as Error).message || '保存档案失败')
    } finally {
      setSaving(false)
    }
  }, [buildInput, data])

  /* ---------- 把这次排盘存成一条记录（可在「我的记录」里回放） ---------- */
  const [savingRec, setSavingRec] = useState(false)
  const saveAsRecord = useCallback(async () => {
    if (!data || savingRec) return
    setSavingRec(true); setError(''); setMsg('')
    try {
      const input = buildInput()
      const row = await saveRecord({
        kind: 'bazi',
        title: name.trim() || `${data.solar} · ${data.gender}`,
        subtitle: `${data.bazi.map((p) => p.ganzhi).join(' ')} · ${data.geju?.name || ''}${data.day_master ? ` · 日主${data.day_master.gan}` : ''}`,
        question: '',
        payload: { data, birth: typeof input === 'string' ? null : input },
      })
      setMsg(row ? `已保存为记录（#${row.id}），可在「我的记录」里点开回放。` : '保存记录失败，稍后再试。')
    } catch (err) {
      setError((err as Error).message || '保存记录失败，稍后再试。')
    } finally {
      setSavingRec(false)
    }
  }, [data, name, buildInput, savingRec])

  /* ---------- 删除命局档案 ---------- */
  const removeProfile = useCallback(async () => {
    if (!window.confirm('确定删除命局档案？删除后梅花/六爻的命卦校验与逐日宜忌表会失效（记录不受影响）。')) return
    setSaving(true); setError(''); setMsg('')
    try {
      await deleteProfile()
      setProfile(null)
      setMsg('命局档案已删除。')
    } catch (err) {
      setError((err as Error).message || '删除失败')
    } finally {
      setSaving(false)
    }
  }, [])

  const pickedRegionName = [
    pidx >= 0 ? provs[pidx]?.n : '',
    pidx >= 0 && cidx >= 0 ? provs[pidx]?.c[cidx]?.n : '',
    pidx >= 0 && cidx >= 0 && didx >= 0 ? provs[pidx]?.c[cidx]?.d?.[didx]?.n : '',
  ].filter(Boolean).join(' · ')

  const timeInit = useMemo(() => {
    if (calendar === 'solar') {
      const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(solarDate)
      return { y: m ? Number(m[1]) : 1990, m: m ? Number(m[2]) : 1, d: m ? Number(m[3]) : 1, leap: false, hour, minute }
    }
    return { y: ly, m: lm, d: ld, leap, hour, minute }
  }, [calendar, solarDate, ly, lm, ld, leap, hour, minute])

  const timeOk = (v: { y: number; m: number; d: number; leap: boolean; hour: number; minute: number }) => {
    if (calendar === 'solar') {
      setSolarDate(`${v.y}-${String(v.m).padStart(2, '0')}-${String(v.d).padStart(2, '0')}`)
    } else {
      setLy(v.y); setLm(v.m); setLd(v.d); setLeap(v.leap)
    }
    setHour(v.hour); setMinute(v.minute)
    setTimeOpen(false)
  }

  return (
    <div>
      <div className="leaf-head">
        <span className="juan-mark">易占</span>
        <FishTail />
        <span className="juan">四柱八字</span>
        <span className="folio">卷三</span>
      </div>
      <div className="juan-title">
        <h1>排盘论命</h1>
        <p className="juan-sub">以节气定月 · 以干支论命 · 立命局划红线</p>
      </div>

      {/* ---------- 表单 ---------- */}
      <div className="register">
        <div className="reg-grid">
          <div className="reg-cell full">
            <span className="reg-label">名字（可选，只用于记录标题）</span>
            <input className="input" style={{ maxWidth: 260 }} value={name} maxLength={20}
              placeholder="如：自己 / 家人名字" onChange={(e) => setName(e.target.value)} />
            <span className="reg-hint">不填就按出生时间当标题；排盘后点「存为记录」才会写进「我的记录」</span>
          </div>
          <div className="reg-cell">
            <span className="reg-label">历法</span>
            <div className="slip-row">
              <button type="button" className={`slip ${calendar === 'solar' ? 'active' : ''}`} onClick={() => setCalendar('solar')}>公历</button>
              <button type="button" className={`slip ${calendar === 'lunar' ? 'active' : ''}`} onClick={() => setCalendar('lunar')}>农历</button>
            </div>
            <span className="reg-hint">
              排盘以节气换月，不是按农历初一分月——所以同一天在两种历法下月柱可能不同，这是正常的
            </span>
          </div>

          <div className="reg-cell">
            <span className="reg-label">性别</span>
            <div className="slip-row">
              <button type="button" className={`slip ${gender === 1 ? 'active' : ''}`} onClick={() => setGender(1)}>乾造 · 男</button>
              <button type="button" className={`slip ${gender === 0 ? 'active' : ''}`} onClick={() => setGender(0)}>坤造 · 女</button>
            </div>
            <span className="reg-hint">大运顺逆由性别与年干阴阳共同决定，必须选</span>
          </div>

          <div className="reg-cell">
            <span className="reg-label">出生日期（{calendar === 'solar' ? '公历' : '农历'}）</span>
            <button type="button" className="btn-outline" style={{ width: '100%', justifyContent: 'space-between', fontSize: 'var(--type-data)' }}
              onClick={() => setTimeOpen(true)}>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700 }}>
                {calendar === 'solar'
                  ? solarDate
                  : `${ly}年${leap ? `闰${lm}月` : `${lm}月`}${ld}日`}
              </span>
              <span aria-hidden>▾</span>
            </button>
            <span className="reg-hint">
              点开用滚轮选年月日{calendar === 'lunar' && leapMonth > 0 ? '（含闰月）' : ''}
              {calendar === 'lunar'
                ? (lunarConv ? `　换算公历：${lunarConv}` : '')
                : (solarLunarLine ? `　${solarLunarLine}` : '')}
            </span>
          </div>

          <div className="reg-cell">
            <span className="reg-label">出生时间</span>
            <button type="button" className="btn-outline" style={{ width: '100%', justifyContent: 'space-between', fontSize: 'var(--type-data)' }}
              onClick={() => setTimeOpen(true)}>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700 }}>
                {String(hour).padStart(2, '0')}:{String(minute).padStart(2, '0')} · {shichenOf(hour).name}
              </span>
              <span aria-hidden>▾</span>
            </button>
            <span className="reg-hint">时辰按真太阳时判定更准：靠近时辰交界（如 12:50）时，校正后可能落到下一个时辰</span>
          </div>

          <div className="reg-cell full">
            <span className="reg-label">出生地区（真太阳时经度校正用）</span>
            <button type="button" className="btn-outline" style={{ width: '100%', justifyContent: 'space-between', fontSize: 'var(--type-data)' }}
              disabled={provs.length === 0}
              onClick={() => setRegionOpen(true)}>
              <span style={{ fontFamily: 'var(--font-kai)' }}>
                {pickedRegionName || '点开选择省份 / 城市（全国）'}
              </span>
              <span aria-hidden>▾</span>
            </button>
            <span className="reg-hint">
              {lnglat
                ? `经度 ${lnglat.lng.toFixed(2)}° / 纬度 ${lnglat.lat.toFixed(2)}°（取市一级）`
                : regionErr || '不选地区就按东经 120° 算：每偏 1° 约差 4 分钟'}
            </span>
          </div>

          <div className="reg-cell">
            <span className="reg-label">真太阳时校正</span>
            <button type="button" className={`slip ${trueSolar ? 'active' : ''}`} onClick={() => setTrueSolar((v) => !v)}>
              {trueSolar ? '已开启' : '关闭'}
            </button>
            <span className="reg-hint">
              开启后按出生地经度与均时差把钟表时间还原为真实太阳时；只影响时柱与大运起运时间
            </span>
          </div>
          <div className="reg-cell">
            <span className="reg-label">夏令时</span>
            <button type="button" className={`slip ${dst ? 'active' : ''}`} onClick={() => setDst((v) => !v)}>
              {dst ? '含夏令时（先减 1 小时）' : '不含'}
            </button>
            <span className="reg-hint">
              {dstSt.note}{dstSt.window ? `（当年夏令时窗口 ${dstSt.window}）` : ''}
              {dstSt.applied ? '　勾选后排盘会先还原标准时间再继续校正。' : ''}
            </span>
          </div>
        </div>

        {/* C3：排盘前校时预览（勾了夏令时或真太阳时才逐层展示） */}
        {correctionPreview.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <div className="d-title">排盘前校时预览</div>
            {correctionPreview.map((l, i) => (
              <div className="d-src" key={i}>{l}</div>
            ))}
          </div>
        )}

        <div className="btn-row" style={{ marginTop: 20 }}>
          <button type="button" className="btn" onClick={cast} disabled={loading}>
            {loading ? '排盘中…' : '排 盘'}
          </button>
          <button type="button" className="btn-outline" onClick={save} disabled={saving}>
            {saving ? '处理中…' : '排盘并存为命局档案'}
          </button>
          {data && (
            <button type="button" className="btn-outline" onClick={saveAsRecord} disabled={savingRec}>
              {savingRec ? '保存中…' : '存为记录'}
            </button>
          )}
          {profile && (
            <button type="button" className="btn-inkline" onClick={removeProfile} disabled={saving}>删除命局档案</button>
          )}
        </div>
        <span className="reg-hint">
          存档后，梅花与六爻给的建议会先过你八字的喜用/忌神红线；逐日宜忌表也依赖这份档案。
        </span>
        <div style={{ marginTop: 10 }}><ProfileLine profile={profile} /></div>

        {error && <div className="notice notice-err"><b>错误</b><span className="n-body">{error}</span></div>}
        {msg && <div className="notice notice-ok"><b>完成</b><span className="n-body">{msg}</span></div>}
      </div>

      {/* ---------- 排盘结果（sys-zone 分区壳，与梅花/六爻一致） ---------- */}
      {data && (
        <div className="sys-zone">
          <div className="sys-zone-head">
            <span className="sys-zone-title">四柱八字</span>
            <span className="sys-zone-sub">以节气定月 · 以干支论命 · 立命局划红线</span>
          </div>

          {/* ===== 四柱 ===== */}
          <div className="bz-head" style={{ marginTop: 14 }}>
            <h2>四柱</h2>
            <span className="rule" />
            <span className="demo-badge">
              {data.solar} · {data.lunar} · {data.shengxiao}年 · {data.gender} · 空亡 {data.xunkong}
            </span>
          </div>

          {data.true_solar && (
            <div className="d-src" style={{ marginBottom: 8 }}>
              真太阳时：钟表时间 {data.true_solar.original} → 校正后 {data.true_solar.solar_used}
              （经度 {data.true_solar.longitude}°，经度差 {data.true_solar.lon_correction} 分钟，
              均时差 {data.true_solar.eot} 分钟）
            </div>
          )}
          {data.dst?.applied && (
            <div className="d-src" style={{ marginBottom: 8 }}>
              夏令时：{data.dst.recorded} → 还原 {data.dst.restored}（{data.dst.note || '1986–1991 年夏令时'}）
            </div>
          )}
          {data.dst && !data.dst.applied && data.dst.note && (
            <div className="d-src" style={{ marginBottom: 8 }}>
              夏令时：{data.dst.note}
            </div>
          )}

          {/* 四柱并排：十神/藏干/纳音/地势/自坐/旬空直接显示（用于比较）；
              干支体性折叠点开（《滴天髓》原文+燥湿分列） */}
          <div className="pillar-row">
            {data.bazi.map((p, i) => (
              <PillarCard key={p.label + i} p={p} isDay={p.label === '日柱'} />
            ))}
          </div>
          <TextureFold pillars={data.bazi} />

          {/* ===== 判定链（主线：强弱 → 格局 → 调候 → 喜忌整合） ===== */}
          <div className="bz-head" style={{ marginTop: 18 }}>
            <h2>判定链</h2>
            <span className="rule" />
            <span className="aside">强弱 → 格局 → 调候 → 喜忌整合 · 每环节标维度来源</span>
          </div>

          <div className="chain-grid">
            {/* ① 强弱（扶抑） */}
            <div className="chain-item">
              <div className="chain-head">
                <span className="chain-no">一</span>强弱（扶抑）
                <span className="chain-src">《子平真诠》得时得地得势 · 权重工程值</span>
              </div>
              <div className="chain-body">
                <span className="chain-main">{data.xiji?.tier || '—'}</span>
                <span className="chain-sub">强弱比 {data.xiji ? data.xiji.score.toFixed(2) : '—'}</span>
                {data.xiji?.from_ge ? (
                  <div className="chain-note">
                    特殊格局成立：{data.xiji.from_ge}（{data.xiji.ge_quality || ''}）→ 取用让位于格局
                  </div>
                ) : null}
              </div>
            </div>

            {/* ② 格局 */}
            <div className="chain-item">
              <div className="chain-head">
                <span className="chain-no">二</span>格局
                <span className="chain-src">月令取格《子平真诠》 · 从化格《滴天髓》</span>
              </div>
              <div className="chain-body">
                <span className="chain-main">{data.geju?.name || '—'}</span>
                {data.xiji?.from_ge ? (
                  <div className="chain-note">{data.xiji.from_ge}（{data.xiji.ge_quality || ''}）：{data.xiji.ge_note || ''}</div>
                ) : null}
                {data.geju?.basis ? <div className="chain-src-note">{data.geju.basis}</div> : null}
                {data.xiji?.from_ge && data.xiji.ge_basis ? (
                  <div className="chain-src-note">{data.xiji.ge_basis}</div>
                ) : null}
                <div className="chain-src-note">
                  取格总则：<QuoteRef k="子平真诠·论用神" />
                  　<QuoteRef k="滴天髓·八格（原注）" />
                  　<QuoteRef k="渊海子平·继善篇（提纲）" />
                </div>
                <div className="chain-src-note">
                  成格/破格条件：<QuoteRef k="子平真诠·论用神成败救应" />
                  　<QuoteRef k="三命通会·元机赋（月支取格）" />
                </div>
              </div>
            </div>

            {/* ③ 调候 */}
            <div className="chain-item">
              <div className="chain-head">
                <span className="chain-no">三</span>调候
                <span className="chain-src">气候维度 · 《穷通宝鉴》月令调候表</span>
              </div>
              <div className="chain-body">
                <span className="chain-main">
                  {data.xiji?.mingju?.T0?.length ? data.xiji.mingju.T0.join('、') : (data.tiaohou?.yongshen || '—')}
                </span>
                <div className="chain-note">
                  {coldDryOf(data.xiji)}　
                  {data.xiji?.mingju?.T0?.length
                    ? `调候第一用神：${data.xiji.mingju.T0.join('、')}（${data.xiji.mingju.t0_src || ''}）`
                    : '调候门休眠（寒暖中和）'}
                </div>
                {data.tiaohou?.note ? <div className="chain-src-note">{data.tiaohou.note}</div> : null}
                <div className="chain-src-note">
                  调候总纲：<QuoteRef k="穷通宝鉴·调候为急" />
                  　<QuoteRef k="子平真诠·论用神配气候得失" />
                </div>
              </div>
            </div>

            {/* ④ 喜忌整合（宽占一行） */}
            <div className="chain-item wide">
              <div className="chain-head">
                <span className="chain-no">四</span>喜忌整合
                <span className="chain-src">调候 + 扶抑合并输出 · 同一五行标维度来源</span>
              </div>
              <div className="chain-body">
                {(data.xiji?.layers_view || []).map((v) => (
                  <div className="lv-row" key={v.wx}>
                    <span className={`lv-wx wxl-${v.wx}`}>{v.wx}</span>
                    <span className="lv-items">
                      {v.items.map((it, i) => (
                        <span key={i} className={`lv-item src-${it.source}`}>
                          <i>{it.source}</i>{it.role_label}
                          {it.note ? <em>{it.note}</em> : null}
                        </span>
                      ))}
                    </span>
                    {v.ruling ? <div className="lv-ruling">{v.ruling}</div> : null}
                  </div>
                ))}
                {/* 旧快照回放（无 layers_view）时退回五档并列 */}
                {(!data.xiji?.layers_view || data.xiji.layers_view.length === 0) && (
                  <div className="check-grid">
                    {([['用神', 'yongshen'], ['喜神', 'xishen'], ['闲神', 'xianshen'], ['仇神', 'choushen'], ['忌神', 'jishen']] as const).map(([label, key]) => (
                      <div className="check-item" key={key}>
                        <span className="k">{label}</span>
                        <b>{(data.xiji.layers as Record<string, string>)[key] || '—'}</b>
                      </div>
                    ))}
                  </div>
                )}
                {data.xiji?.wuxing_summary && (
                  <div className="d-src" style={{ marginTop: 8 }}>
                    {data.xiji.wuxing_summary.tally}
                    {data.xiji.wuxing_summary.missing_txt ? ` · ${data.xiji.wuxing_summary.missing_txt}` : ''}
                    {data.xiji.wuxing_summary.like_note ? ` · ${data.xiji.wuxing_summary.like_note}` : ''}
                  </div>
                )}
                {data.xiji?.adjust_marks?.length ? (
                  <div className="d-src">调整标记：{data.xiji.adjust_marks.join('、')}</div>
                ) : null}
                <details className="claims-fold" style={{ marginTop: 10 }}>
                  <summary>判定步骤（六步验算，点开核对）</summary>
                  <div className="claims-body">
                    {data.xiji?.steps?.map((s, i) => (
                      <div className="check-hit" key={i}>
                        {s.step}. {s.title}：{s.logic}{s.score !== undefined ? `（得分 ${s.score}）` : ''}
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            </div>
          </div>

          {/* ===== 结构层：命宫 · 胎元 ===== */}
          {data.gong && (
            <>
              <div className="bz-head" style={{ marginTop: 18 }}>
                <h2>命宫 · 胎元</h2>
                <span className="rule" />
                <span className="aside">结构层 · 命局的作用细节</span>
              </div>
              <div className="check-grid">
                {([['命宫', 'minggong'], ['胎元', 'taiyuan'], ['身宫', 'shengong'], ['胎息', 'taixi']] as const).map(([label, key]) => {
                  const g = (data.gong as Record<string, { ganzhi: string; nayin: string }>)[key]
                  return (
                    <div className="check-item" key={key}>
                      <span className="k">{label}</span><b>{g?.ganzhi || '—'}</b>
                      <div className="d-src" style={{ marginTop: 2 }}>{g?.nayin}</div>
                    </div>
                  )
                })}
              </div>
            </>
          )}

          {/* 神煞：四条检验 F1（站长裁甲，2026-09-24）——八字排盘不再展示神煞 */}

          {/* ===== 时间区：大运 · 流年 ===== */}
          {data.dayun?.steps?.length ? (
            <>
              <div className="bz-head" style={{ marginTop: 18 }}>
                <h2>大运 · 流年</h2>
                <span className="rule" />
                <span className="aside">
                  时间区 · {data.dayun.forward ? '顺行' : '逆行'} · 起运 {data.dayun.start.years}年{data.dayun.start.months}月{data.dayun.start.days}天
                </span>
              </div>
              <div className="d-src">起运日期：{data.dayun.start.solar} · 点任一步看该运十年流年</div>
              <div className="dayun-grid">
                {data.dayun.steps.map((s: BaziDayunStep, i: number) => (
                  <button
                    type="button"
                    key={s.index ?? i}
                    className={`dayun-item ${dayunIdx === i ? 'active' : ''}`}
                    onClick={() => setDayunIdx(dayunIdx === i ? null : i)}
                  >
                    <span className="dz">{s.ganzhi}</span>
                    <span className="ds">{s.start_age}–{s.end_age} 岁</span>
                    <span className="ds">{s.start_year}–{s.end_year}</span>
                    <span className="ds">{s.gan_shishen}</span>
                  </button>
                ))}
              </div>
              {dayunIdx !== null && data.dayun.steps[dayunIdx]?.liunian?.length ? (
                <div className="liunian-table">
                  <div className="yingqi-group-title">
                    {data.dayun.steps[dayunIdx].ganzhi} 运内的流年
                  </div>
                  {data.dayun.steps[dayunIdx].liunian.map((n) => (
                    <div className="liunian-row" key={n.year}>
                      <span className="y">{n.year}</span>
                      <span className="a">{n.age} 岁</span>
                      <span className="g">{n.ganzhi} · {n.gan_shishen}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}

          {/* ===== 背景区：改运链（灰底弱化，只作背景不进判定） ===== */}
          <div className="bg-zone">
            {data.yunqi ? (
              <>
                <div className="bz-head">
                  <h2>出生年天地运气（改运链）</h2>
                  <span className="rule" />
                  <span className="aside">背景区 · 只作调养参考，不进判定</span>
                </div>
                <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>
                  {data.yunqi.ganzhi}年：中运 {data.yunqi.中运.五音}（{data.yunqi.中运.五行}运{data.yunqi.中运.太过不及}）
                  · 司天 {data.yunqi.司天} · 在泉 {data.yunqi.在泉}
                  {data.yunqi.特殊?.length ? ` · ${data.yunqi.特殊.join('、')}` : ''}
                  {data.yunqi.化数 ? <><br />化数：司天{data.yunqi.化数.司天} · 中运{data.yunqi.化数.中运} · 在泉{data.yunqi.化数.在泉}</> : null}
                  {data.yunqi.药食宜 ? <><br />药食宜：上{data.yunqi.药食宜.上} · 中{data.yunqi.药食宜.中} · 下{data.yunqi.药食宜.下}</> : null}
                  {data.yunqi.胜复 ? <><br />{data.yunqi.胜复}（灾{data.yunqi.灾宫}）</> : null}
                  <div className="d-src" style={{ marginTop: 2 }}>书证：{data.yunqi.书证 || '《素问·六元正纪大论》'}</div>
                </div>
              </>
            ) : null}

            {data.dili ? (
              <>
                <div className="bz-head" style={{ marginTop: 14 }}>
                  <h2>出生地空间气（改运链）</h2>
                  <span className="rule" />
                  <span className="aside">背景区 · 只作背景，不进判定</span>
                </div>
                <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>
                  {data.dili.方位 ? `五方：${data.dili.方位}${data.dili.五行 ? `（属${data.dili.五行}）` : ''} · ` : ''}
                  {data.dili.方性 || data.dili.备注}
                  <div className="d-src" style={{ marginTop: 2 }}>{data.dili.书证 || ''}{data.dili.地势高下 ? ` · ${data.dili.地势高下}` : ''}</div>
                  {data.dili.界值说明 ? <div className="d-src">{data.dili.界值说明}</div> : null}
                </div>
              </>
            ) : null}
          </div>

          {/* ===== 大运流年详批（事业 / 财运 / 感情）：确定性骨架 + AI 详批 + 下载 md ===== */}
          <DayunPanel birth={castInput} />
        </div>
      )}

      {/* 弹层：时间滚轮 / 地区选择 */}
      {timeOpen && (
        <TimePickerModal
          calendar={calendar}
          lunarDays={lunarDays}
          leapMonth={leapMonth}
          init={timeInit}
          onClose={() => setTimeOpen(false)}
          onOk={timeOk}
        />
      )}
      {regionOpen && (
        <RegionModal
          provinces={provs}
          init={{ p: pidx, c: cidx, d: didx }}
          onClose={() => setRegionOpen(false)}
          onOk={(sel) => { setPidx(sel.p); setCidx(sel.c); setDidx(sel.d); setRegionOpen(false) }}
        />
      )}
    </div>
  )
}

/* ---------- 调候寒燥状态（从步骤五的判语提取，供判定链③环节显示） ---------- */

function coldDryOf(xiji: BaziData['xiji']): string {
  if (!xiji) return ''
  const s5 = xiji.steps?.find((s) => s.step === '步骤五')
  if (!s5) return ''
  if (s5.logic.includes('燥局')) return '燥局（寒暖燥湿失衡）'
  if (s5.logic.includes('寒局')) return '寒局（寒暖燥湿失衡）'
  return '寒暖中和'
}

/* ---------- 单柱卡片：十神/藏干/纳音/地势/自坐/旬空并排直接显示 ---------- */

function PillarCard({ p, isDay }: { p: BaziPillar; isDay: boolean }) {
  return (
    <div className={`pillar-card ${isDay ? 'day' : ''}`}>
      <div className="pc-head">
        <span className="pc-label">{isDay ? '日柱 · 日主' : p.label}</span>
      </div>
      <div className="pc-gz">
        <span className={`pc-gan wxl-${p.gan_wuxing}`}>{p.gan}</span>
        <span className={`pc-zhi wxl-${p.zhi_wuxing}`}>{p.zhi}</span>
      </div>
      <div className="pc-wx">{p.gan_wuxing}干 · {p.zhi_wuxing}支</div>
      <div className="pc-rows">
        <div className="pc-row"><span className="k">十神</span><b>{p.shishen_gan || '—'}</b></div>
        <div className="pc-row">
          <span className="k">藏干</span>
          <span className="pc-cg">
            {p.canggan?.length
              ? p.canggan.map((c, i) => (
                <span key={i} className={`wxl-${c.wuxing}`}>{c.gan}{c.wuxing}（{c.shishen}）</span>
              ))
              : '—'}
          </span>
        </div>
        <div className="pc-row"><span className="k">纳音</span><span>{p.nayin}</span></div>
        <div className="pc-row"><span className="k">地势</span><span>{p.dishis} · 自坐 {p.self_sit}</span></div>
        <div className="pc-row"><span className="k">旬空</span><span>{p.xunkong || '—'}{p.is_kong ? '（落空）' : ''}</span></div>
      </div>
    </div>
  )
}

/* ---------- 干支体性（默认收起：四柱的《滴天髓》原文+燥湿分列） ---------- */

function TextureFold({ pillars }: { pillars: BaziPillar[] }) {
  const withTex = pillars.filter((p) => p.gan_texture || p.zhi_texture)
  if (!withTex.length) return null
  return (
    <details className="pd-fold" style={{ marginTop: 10 }}>
      <summary>干支体性（《滴天髓》原文 · 燥湿分列）</summary>
      <div className="pd-fold-body">
        {withTex.map((p) => (
          <div key={p.label} className="texture-block">
            <div className="yingqi-group-title">{p.label} · {p.ganzhi}{p.label === '日柱' ? '（日主）' : ''}</div>
            {p.gan_texture && (
              <div className="texture-quote">
                <div className="tq-head">天干 · {p.gan}（{p.gan_texture.tags || ''}）</div>
                {p.gan_texture.tixiang && <div className="tq-text">「{p.gan_texture.tixiang}」</div>}
                {p.gan_texture.note && <div className="tq-note">{p.gan_texture.note}</div>}
                <div className="tq-src">出处：{p.gan_texture.src}</div>
              </div>
            )}
            {p.zhi_texture && (
              <div className="texture-quote">
                <div className="tq-head">地支 · {p.zhi}（{p.zhi_texture.tags || ''}）</div>
                {p.zhi_texture.tixiang && <div className="tq-text">「{p.zhi_texture.tixiang}」</div>}
                {p.zhi_texture.note && <div className="tq-note">{p.zhi_texture.note}</div>}
                {p.zhi_texture.zao_shi_sources?.length ? (
                  <div className="tq-note">
                    燥湿（按载体分列，不跨载体互推）：
                    {p.zhi_texture.zao_shi_sources.map((s, i) => (
                      <span key={i} style={{ display: 'block' }}>
                        · {s.carrier} → {s.value}（{s.src}）
                      </span>
                    ))}
                    {p.zhi_texture.zao_shi_state ? `综合标记：${p.zhi_texture.zao_shi_state}` : ''}
                    {p.zhi_texture.zao_shi_strength ? `（${p.zhi_texture.zao_shi_strength}）` : ''}
                  </div>
                ) : null}
                <div className="tq-src">出处：{p.zhi_texture.src}</div>
              </div>
            )}
          </div>
        ))}
        <div className="d-src" style={{ marginTop: 6 }}>
          燥湿读法：<b>歧异</b>＝两处书证方向相反，故分列不择一；<b>条件性</b>＝没有逐支燥湿条文，
          由局中水火与干支相配来定。燥湿按载体分列、<b>不跨载体互推</b>。
        </div>
      </div>
    </details>
  )
}
