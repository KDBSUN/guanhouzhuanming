import { useEffect, useState } from 'react'
import type { View } from '../App'
import {
  PlumArt, CoinArt, TaijiArt, SealArt,
  ScaleIcon, CalendarIcon, ScrollIcon, CompassIcon,
} from '../art/icons'

/* ============================================================
   首页（v0）：黄历条 · 主视觉 + 快占卡 · 四入口 · 三步 · 特色 · 注脚
   数据策略：黄历/典籍规模尝试真接口，取不到就如实降级为占位标记，
   绝不编数字（宁缺毋假，与现有前端同一原则）。
   ============================================================ */

interface Huangli {
  solar: string
  lunar: string
  ganzhi: { year: string; month: string; day: string }
  shengxiao: string
  jieqi_now: string
  jieqi_next: string
  yi: string[]
  ji: string[]
}

function HuangliStrip() {
  const [hl, setHl] = useState<Huangli | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    fetch('/api/huangli/today')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => (d ? setHl(d) : setFailed(true)))
      .catch(() => setFailed(true))
  }, [])

  if (failed && !hl) {
    return (
      <div className="hl-strip">
        <div className="hl-left">
          <span className="hl-date">今日黄历</span>
          <span className="stub-mark">需启动后端 :8000 · 正式版实时接入</span>
        </div>
      </div>
    )
  }
  if (!hl) return null

  return (
    <div className="hl-strip">
      <div className="hl-left">
        <span className="hl-date">{hl.solar}</span>
        <span className="hl-lunar">{hl.lunar} · {hl.ganzhi.year}年 {hl.ganzhi.month}月 {hl.ganzhi.day}日</span>
        <span className="hl-jieqi">{hl.shengxiao}年 · {hl.jieqi_now} · 下一个节气：{hl.jieqi_next}</span>
      </div>
      <div className="hl-right">
        <span className="hl-yj"><b>宜</b>{hl.yi.slice(0, 4).join(' ')}</span>
        <span className="hl-yj hl-yj-ji"><b>忌</b>{hl.ji.slice(0, 3).join(' ')}</span>
      </div>
    </div>
  )
}

/* ---------- 快占卡 ---------- */

const QUICK_HINTS = ['今日运势', '近期财运', '近期姻缘', '眼下事业']

function QuickCastCard({ onGo }: { onGo: (v: View, q?: string) => void }) {
  const [q, setQ] = useState('')
  return (
    <div className="qc-card">
      <div className="qc-title">
        <span className="kicker">诚心静气 · 一事一占</span>
        写下所问之事
      </div>
      <textarea
        className="textarea"
        placeholder="此刻心里放不下的那件事——越具体，卦象越有针对性（如：这周五去谈合作顺利吗）"
        value={q}
        maxLength={200}
        onChange={(e) => setQ(e.target.value)}
        rows={3}
      />
      <div className="qc-chips">
        {QUICK_HINTS.map((h) => (
          <button key={h} type="button" className={`chip ${q === h ? 'active' : ''}`} onClick={() => setQ(h)}>
            {h}
          </button>
        ))}
      </div>
      <div className="qc-actions">
        <button type="button" className="btn btn-primary" onClick={() => onGo('meihua', q.trim())}>梅花起卦</button>
        <button type="button" className="btn btn-outline" onClick={() => onGo('liuyao', q.trim())}>六爻摇钱</button>
      </div>
      <div className="qc-quote">
        「初筮告，再三渎，渎则不告。」——《周易 · 蒙》｜同一件事，得卦之后先把它读完、放下，情势变了再问。
      </div>
    </div>
  )
}

/* ---------- 入口卡 ---------- */

function EntryCard({ onGo, view, art, name, sub, enter }: {
  onGo: (v: View) => void
  view: View
  art: React.ReactNode
  name: string
  sub: string
  enter: string
}) {
  return (
    <button type="button" className="entry-card" onClick={() => onGo(view)}>
      <span className="entry-art">{art}</span>
      <span className="entry-name">{name}</span>
      <span className="entry-sub">{sub}</span>
      <span className="entry-enter">{enter} →</span>
    </button>
  )
}

/* ---------- 三步 ---------- */

const STEPS = [
  { num: '壹', name: '立命局', desc: '一次填写出生年月日时，系统按《滴天髓》《穷通宝鉴》排出扶抑喜用、忌神与调候用神，划定你长期不能碰的红线。' },
  { num: '贰', name: '起卦问事', desc: '梅花时间数字取象，六爻三钱摇卦；卦象给出当下这件事的处方五行（该补什么、避什么）。' },
  { num: '叁', name: '领行动方案', desc: '处方先过命局三道门校验，冲突则自动改方通关；按档位输出宜忌日期表、方位物件建议，每一条都能点开典籍原文。' },
]

function HowItWorks() {
  return (
    <section className="home-how">
      <div className="sect-head home-section-head">
        <span className="kicker-ruled">三 步 问 卜</span>
      </div>
      <h2 className="home-section-title">
        古法起卦 · 先过你八字的边界
      </h2>
      <div className="how-grid">
        {STEPS.map((s) => (
          <div className="how-step" key={s.num}>
            <span className="how-num">{s.num}</span>
            <div className="how-name">{s.name}</div>
            <div className="how-desc">{s.desc}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ---------- 特色 ---------- */

const FEATURES = [
  { Icon: ScaleIcon, name: '命卦安全校验', desc: '卦象说要补的五行，先对照你八字的忌神红线——共振放行、犯忌自动改方通关，杜绝"补错五行反害自己"。' },
  { Icon: CalendarIcon, name: '确定性择日', desc: '按《梅花易数》卦气旺相之理逐日排未来 7–30 天的宜忌日期表，紧急层不再是 AI 散文。' },
  { Icon: ScrollIcon, name: '典籍可回溯', desc: '从处方五行到岁运行运，每一步标注出处并可展开原文摘录核对，把玄学变成可解释、可复核。' },
  { Icon: CompassIcon, name: '岁运引动层', desc: '流年五行先被月令称重（旺相休囚死），只以小权重引动降级或加持，《滴天髓》从格行运判定表逐句固化。' },
]

function Features() {
  return (
    <section className="home-features">
      <div className="sect-head home-section-head">
        <span className="kicker-ruled">与 众 不 同</span>
      </div>
      <h2 className="home-section-title">
        不是「运气好不好」，而是「这件事怎么办」
      </h2>
      <div className="feat-grid">
        {FEATURES.map(({ Icon, name, desc }) => (
          <div className="feat-card" key={name}>
            <span className="feat-ico"><Icon size={19} /></span>
            <div className="feat-name">{name}</div>
            <div className="feat-desc">{desc}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ---------- 首页 ---------- */

export default function HomeView({ onGo }: { onGo: (v: View, q?: string) => void }) {
  const [meta, setMeta] = useState<{ quote_keys: number; book_count: number } | null>(null)
  useEffect(() => {
    fetch('/api/meta/quotes')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d && typeof d.quote_keys === 'number') setMeta(d) })
      .catch(() => { /* 取不到就不显示这一格，宁缺毋假 */ })
  }, [])

  return (
    <div className="home-view">
      <HuangliStrip />

      <div className="home-hero">
        <div className="hero-intro">
          <h1 className="hero-title">
            观候·转明<span className="seal-dot" aria-hidden />
          </h1>
          <p className="hero-sub">自强不息，时乘六龙以御天</p>
          <div className="hero-stats">
            <span className="stat"><b>64</b>经卦</span>
            <span className="stat"><b>384</b>经爻</span>
            {meta && <span className="stat"><b>{meta.book_count}</b>部典籍 · <b>{meta.quote_keys}</b>条原文索引</span>}
            <span className="stat"><b>免费</b>无需注册</span>
          </div>
        </div>
        <QuickCastCard onGo={onGo} />
        <span className="hero-vertical vertical-text" aria-hidden>天行健，君子以自强不息</span>
      </div>

      <HowItWorks />

      <div className="entry-grid">
        <EntryCard onGo={onGo} view="bazi" art={<TaijiArt />} name="四柱八字" sub="以干支论命途 · 排盘定喜忌" enter="排盘论命" />
        <EntryCard onGo={onGo} view="meihua" art={<PlumArt />} name="梅花易数" sub="时间数字取象 · 体用断吉凶" enter="起卦观梅" />
        <EntryCard onGo={onGo} view="liuyao" art={<CoinArt />} name="纳甲六爻" sub="三枚铜钱摇六次 · 用神定处方" enter="摇钱纳甲" />
        <EntryCard onGo={onGo} view="records" art={<SealArt />} name="我的记录" sub="起过的卦、排过的盘 · 点开跳回当时界面" enter="回看记录" />
      </div>

      <Features />

      <div className="home-note">
        <span className="gua-mark" aria-hidden>☰</span>
        不动不占 · 无事不占 —— 心有所感，方可起卦
        <span className="gua-mark" aria-hidden>☷</span>
      </div>
    </div>
  )
}
