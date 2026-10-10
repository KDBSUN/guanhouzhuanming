import { useState } from 'react'
import { postClaimVerdict, VERDICTS, type Verdict } from '../api/feedback'
import { CASE_OUTCOMES, postCaseOutcome, type CaseOutcome } from '../api/mingju'
import QuoteRef from './QuoteRef'
import type { FlowBlock, FlowCell, FlowRow, FlowYinyangItem, MingjuCheck } from '../api/types'

/* ============================================================
   命卦校验块（梅花 / 六爻共用）
   ------------------------------------------------------------
   区层与梅花体系一致：sys-zone 分区壳 + sys-zone-head 区头，
   内部各段用 .bz-head 小节标题分层（净档与裁决 → 补五行建议 →
   流动五行判定表 → 逐日宜忌 → 断言反馈 → 整案反馈）。
   一次覆盖：净档与裁决 · 命局基线 · 建议维度（方位/颜色/数字/物件/
   饮食/职业/健康/卦象/屋宅/四时/干支 + 质地味分档）· 流动五行判定表
   （默认当前命盘档位，其余档位小标签切换）· 逐日宜忌 · 断言反馈 ·
   整案反馈（所问之事后来如何？+ 实际发生日期）· 版本锚点 · 免责声明。
   ============================================================ */

const GATE_LABEL: Record<string, string> = { pass: '放行', limited: '限时放行', block: '拦截' }
const SRC_LABEL: Record<string, string> = { manual: '手动', auto: '自动', ambig: '存疑' }
/** 净档白话：顺/平/逆对用户意味着什么 */
const NET_PLAIN: Record<string, string> = {
  顺: '顺：卦象要补的五行与你的八字喜用同气或相生，可以照建议做。',
  平: '平：卦象与命局没有明显顺逆，建议限事项的时间窗使用，别长期照做。',
  逆: '逆：卦象要补的五行撞上你八字的忌神，系统已自动改方通关，请按"最终处方"来做。',
}
const SIDES = ['进气', '出水', '我克', '克我'] as const

/** 建议维度显示名（旧前端同一张表；质地特指"哪一味的器物"，故叫质地分档） */
const DIM_LABEL: Record<string, string> = {
  方位: '方位', 颜色: '颜色', 数字: '数字', 物件: '物件', 饮食: '饮食',
  职业: '职业方向', 健康: '养生', 卦象: '卦象', 屋宅: '屋宅朝向', 四时: '四时',
  天干: '天干', 地支: '地支', 质地: '质地分档',
}

export default function CheckBlock({ check }: { check: MingjuCheck }) {
  const [openDay, setOpenDay] = useState('')
  const [verdicts, setVerdicts] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState('')
  /** 整案级反馈（check_log.outcome）。与断言级的 verdicts 是两个粒度，各存各的 */
  const [caseOutcome, setCaseOutcome] = useState<CaseOutcome | ''>('')
  /** 所问之事实际发生的日期（选填）：后端应期分析靠它算偏差几天 */
  const [caseDate, setCaseDate] = useState('')
  const [caseBusy, setCaseBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const adj = check.adjudication
  const b = check.baseline
  const sug = check.suggestions || {}
  const flows = check.flow || []
  const claims = check.claims || []

  const mark = async (claimId: string, v: Verdict) => {
    if (!check.log_id) { setErr('这次校验没有留下台账号，无法标记。'); return }
    setBusy(claimId); setErr('')
    try {
      const r = await postClaimVerdict(check.log_id, claimId, v)
      if (!r.ok) { setErr('标记失败，稍后再试。'); return }
      setVerdicts((prev) => ({ ...prev, [claimId]: v }))
      setMsg(`已记录：${v}${r.mailed ? '（已邮件通知站长）' : ''}。标记过的断言会进校准台账。`)
    } catch {
      setErr('标记失败，请检查网络后重试。')
    } finally {
      setBusy('')
    }
  }

  /** 整案级标记：写 check_log.outcome（只有 应验/未验/还没结果 三个值），可附实际发生日期 */
  const markCase = async (o: CaseOutcome) => {
    if (!check.log_id) { setErr('这次校验没有留下台账号，无法标记。'); return }
    setCaseBusy(true); setErr('')
    try {
      const ok = await postCaseOutcome(check.log_id, o, caseDate)
      if (!ok) { setErr('整案标记失败，稍后再试。'); return }
      setCaseOutcome(o)
      setMsg(`已记录整案：${o}。可在「我的记录」页的校验台账里看到这一栏。`)
    } catch {
      setErr('整案标记失败，请检查网络后重试。')
    } finally {
      setCaseBusy(false)
    }
  }

  return (
    <div className="sys-zone">
      <div className="sys-zone-head">
        <span className="sys-zone-title">命卦校验</span>
        <span className="sys-zone-sub">处方五行先过你八字的忌神红线</span>
      </div>

      {/* ---------- 净档与裁决 ---------- */}
      <div className="bz-head" style={{ marginTop: 14 }}>
        <h2>净档与裁决</h2>
        <span className="rule" />
        <span className="aside">三道门：共振放行 · 犯忌改方</span>
      </div>

      <div className="check-grid">
        <div className="check-item">
          <span className="k">净档</span>
          <b style={{ color: adj?.net === '顺' ? 'var(--xi)' : adj?.net === '逆' ? 'var(--ji)' : 'var(--foil-4)' }}>
            {adj?.net || '—'}
          </b>
          {adj?.gate ? `（${GATE_LABEL[adj.gate] || adj.gate}）` : ''}
        </div>
        <div className="check-item">
          <span className="k">最终处方</span>
          <b>{check.final_R || check.R || '—'}</b>
          {check.redirect_note ? `　${check.redirect_note}` : ''}
        </div>
        <div className="check-item">
          <span className="k">档位</span>
          {check.tier
            ? `${check.tier.tier}（${SRC_LABEL[check.tier.source] || check.tier.source}）${check.tier.contract?.label ? ` · ${check.tier.contract.label}` : ''}`
            : '—'}
        </div>
        <div className="check-item">
          <span className="k">流年</span>
          {check.liunian
            ? `${check.liunian.ganzhi}（${check.liunian.wx}·${check.liunian.strength}）${check.liunian.effective ? '已引动' : '仅作背景'}`
            : '—'}
        </div>
      </div>

      {adj?.decision && <div className="d-body" style={{ marginTop: 8, fontSize: 'var(--type-body)' }}>{adj.decision}</div>}
      {adj?.net && NET_PLAIN[adj.net] && <div className="d-src">{NET_PLAIN[adj.net]}</div>}

      {/* 处方链：事体 → 处方 → 改方（2026-10 与旧前端对齐：改方逻辑可见，不是只给一个最终数） */}
      {check.X && (
        <div className="d-body" style={{ marginTop: 8, fontSize: 'var(--type-body)' }}>
          处方链：事体【<b>{check.X}</b>】→ 处方【<b>{check.R}</b>】
          {check.final_R && check.final_R !== check.R ? <> → 改方【<b>{check.final_R}</b>】</> : null}
          {check.state ? `（${check.state_desc || check.state}）` : ''}
        </div>
      )}
      {check.R_reason && <div className="d-src">处方理由：{check.R_reason}</div>}
      {check.R_alt && <div className="d-src">备改方：{check.R_alt}</div>}
      {check.notes?.length ? <div className="d-src">调整标记：{check.notes.join('；')}</div> : null}

      {/* 应期 · 按最终处方栏（2026-10 补：改方后的五行当值之日，工程口径；与按卦栏同一窗口） */}
      {check.yingqi_final?.length ? (
        <div style={{ marginTop: 12 }}>
          <div className="mo-line">
            <b>应期 · 按最终处方栏</b>（命局校验改方后的五行当值之日，工程口径）：
          </div>
          <div className="date-strip">
            <div className="date-group">
              <div className="date-group-h">按最终处方 · {check.yingqi_final[0].wx}<i>{check.yingqi_final.length}</i></div>
              <div className="date-group-row">
                {check.yingqi_final.map((d) => (
                  <button type="button" key={d.date} className="date-cell tone-good" title={d.reason}>
                    <b>{d.date.slice(5)}</b>
                    <span>{d.ganzhi}</span>
                    <i>{d.wx}</i>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {adj?.hits?.length ? (
        <div className="check-hits">
          {adj.hits.map((h, i) => (
            <div className="check-hit" key={i}>{h.label}：{h.semantic} → {h.handle}。{h.tip}</div>
          ))}
        </div>
      ) : null}

      {/* 命局基线 */}
      {b ? (
        <div className="d-src" style={{ marginTop: 8 }}>
          命局基线：喜用 {(b.F || []).join('、') || '—'} · 忌 {(b.J || []).join('、') || '—'}
          {b.T0?.length ? ` · 调候 ${b.T0.join('、')}` : ''}
          {b.tier ? ` · 强弱${b.tier}` : ''}
          {b.day_master?.gan ? ` · 日主${b.day_master.gan}（${b.day_master.wuxing}）` : ''}
          {b.month_wx ? ` · 月令${b.month_wx}` : ''}
        </div>
      ) : (
        <div className="notice notice-warn" style={{ marginTop: 10 }}>
          <b>未经命局校验</b>
          <span className="n-body">
            这次没有命局档案，只按事体本身给结论。要按你的八字避险，
            请先在「四柱八字」页排盘并存一份命局档案。
          </span>
        </div>
      )}

      {/* 档位产出说明 */}
      {check.tier?.contract && (
        <div className="d-src" style={{ marginTop: 8 }}>
          {check.tier.contract.label}（问的是"{check.tier.contract.question}"）：
          {check.tier.contract.content?.length ? ` ${check.tier.contract.content.join('；')}。` : ''}
          {check.tier.contract.length ? ` 篇幅：${check.tier.contract.length}。` : ''}
          {check.tier.contract.weight ? ` 权重：${check.tier.contract.weight}。` : ''}
          {check.tier.contract.disclaimer ? ` ${check.tier.contract.disclaimer}` : ''}
        </div>
      )}

      {/* ---------- 补五行建议 ---------- */}
      {Object.keys(sug).length > 0 && (
        <>
          <div className="bz-head" style={{ marginTop: 18 }}>
            <h2>补五行建议</h2>
            <span className="rule" />
            <span className="aside">方位 · 颜色 · 数字 · 物件 · 质地（味分档）· 饮食 · 职业 · 养生 · 屋宅</span>
          </div>
          {Object.entries(sug).map(([wx, dims]) => (
            <SugCard key={wx} wx={wx} dims={dims as Record<string, unknown>}
              yy={flows.find((f) => f.wx === wx)?.yinyang?.items} />
          ))}
        </>
      )}

      {/* ---------- 流动五行判定表 ---------- */}
      {flows.length > 0 && (
        <>
          <div className="bz-head" style={{ marginTop: 18 }}>
            <h2>流动五行判定表</h2>
            <span className="rule" />
            <span className="aside">四边：进气 / 出水 / 我克 / 克我 · 默认显示当前命盘档位，点标签换档对照</span>
          </div>
          {flows.map((f) => (
            <FlowCard key={f.wx} f={f}
              yyMerged={!!((sug[f.wx] as Record<string, unknown> | undefined)?.['质地'])} />
          ))}
        </>
      )}

      {/* ---------- 逐日宜忌 ---------- */}
      <div className="bz-head" style={{ marginTop: 18 }}>
        <h2>逐日宜忌</h2>
        <span className="rule" />
        <span className="aside">点某天看依据</span>
      </div>

      {check.date_table?.days?.length ? (
        <>
          <div className="yingqi-group-title">
            未来 {check.date_table.n_days} 天（宜 {check.date_table.best.length} 天 / 忌 {check.date_table.avoid.length} 天）
          </div>
          {/* 日期格子与「看应期」的横排长方形同款（76px、日期大字、干支楷体），
              第三行用宜/忌替掉那边的类别·五行，按日期顺序排列 */}
          <div className="date-strip">
            {check.date_table.days.map((d) => (
              <button
                type="button"
                key={d.date}
                className={`date-cell tone-${d.yiji === '宜' ? 'good' : d.yiji === '忌' ? 'warn' : 'mixed'} ${openDay === d.date ? 'sel' : ''}`}
                aria-pressed={openDay === d.date}
                onClick={() => setOpenDay(openDay === d.date ? '' : d.date)}
              >
                <b>{d.date.slice(5)}</b>
                <span>{d.ganzhi}</span>
                <i>{d.yiji}</i>
              </button>
            ))}
          </div>
          {openDay && (() => {
            const day = check.date_table!.days.find((x) => x.date === openDay)
            if (!day) return null
            return (
              <div className="day-detail">
                <div className="d-title">{day.date}（{day.ganzhi}）· {day.yiji}　{day.day_wx}{day.state ? ` · ${day.state}` : ''}</div>
                {(day.reasons || []).map((r, i) => (
                  <div className="check-hit" key={i}>{r.reason}{r.src ? `（出处：${r.src}）` : ''}</div>
                ))}
                {!(day.reasons || []).length && <div className="d-src">这一天没有特别理由，按平看待。</div>}
              </div>
            )
          })()}
          <div className="d-src">
            最宜：{check.date_table.best.slice(0, 6).join('、') || '—'}　
            最忌：{check.date_table.avoid.slice(0, 6).join('、') || '—'}
            <br />依据：{(check.date_table.src || []).map((s, i) => (
              <span key={s}>{i > 0 ? '、' : ''}<QuoteRef k={s} /></span>
            ))}
          </div>
          <div className="d-src">
            以上是代码按《梅花易数·先天卦定应期》与《增删卜易》应期诀算出的日期；
            AI 只能在此范围内取舍解释，超出这些日期的说法都不是本站推算。
          </div>
        </>
      ) : (
        <div className="d-src">
          没有逐日宜忌表：这个表要按你的八字逐日比对，需先在「四柱八字」页排盘并存档。
        </div>
      )}

      {/* ---------- 断言反馈 ---------- */}
      {claims.length > 0 && (
        <>
          <div className="bz-head" style={{ marginTop: 18 }}>
            <h2>断言反馈</h2>
            <span className="rule" />
            <span className="aside">可逐条标记应验/未验，进校准台账</span>
          </div>
          {/* 旧前端同款折叠：默认只露一行「想细究的话：逐条断言（N 条，已标 M 条）」，
              想细究才展开逐条标记——校准真正需要的最小信息在整案那一问里 */}
          <details className="claims-fold">
            <summary>
              想细究的话：逐条断言（{claims.length} 条
              {Object.keys(verdicts).length > 0 ? `，已标 ${Object.keys(verdicts).length} 条` : ''}）
            </summary>
            <div className="claims-body">
              {claims.map((c) => (
                <div className="claim-card" key={c.id}>
                  <div className="claim-head">
                    <span className="claim-type">{c.type}</span>
                    <span className="claim-text">{c.text}</span>
                  </div>
                  <div className="claim-meta">
                    {c.rule ? `规则：${c.rule}` : ''}
                    {c.verifiability ? ` · ${c.verifiability}` : ''}
                    {c.since || c.until ? ` · 验证窗口 ${c.since} → ${c.until}` : ''}
                    {c.src ? <> · 书证：<QuoteRef k={c.src} /></> : null}
                  </div>
                  <div className="slip-row" style={{ marginTop: 8 }}>
                    {VERDICTS.map((v) => (
                      <button key={v} type="button"
                        className={`slip ${verdicts[c.id] === v ? 'active' : ''}`}
                        disabled={busy === c.id}
                        onClick={() => mark(c.id, v)}>{v}</button>
                    ))}
                    <span className="hint-line" style={{ alignSelf: 'center' }}>
                      {verdicts[c.id] ? `已标记：${verdicts[c.id]}` : '未标记'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </details>
        </>
      )}

      {/* ---------- 整案级反馈（写 check_log.outcome） ----------
          旧前端同一框架（FeedbackRow）：一个问题「所问之事后来如何？」、
          三个按钮（应验/未验/还没结果）、一个可选的实际发生日期。
          与上面逐条断言是不同粒度：断言级标的是"某一条可检验的断言"，
          这里标的是"这件事整体后来如何"；台账列表里显示的是这一栏。 */}
      {check.log_id ? (
        <div className="case-fb">
          <div className="bz-head" style={{ marginTop: 18 }}>
            <h2>所问之事后来如何？</h2>
            <span className="rule" />
            <span className="aside">整案级 · 显示在「我的记录」的校验台账里</span>
          </div>
          {caseOutcome ? (
            <div className="case-done" role="status">
              反馈已记录：{caseOutcome}（进入校准台账，用于反例捕捉与边界样本复核）
            </div>
          ) : (
            <>
              <div className="slip-row">
                {CASE_OUTCOMES.map((o) => (
                  <button key={o} type="button"
                    className="slip"
                    disabled={caseBusy}
                    onClick={() => markCase(o)}>{o}</button>
                ))}
              </div>
              <label className="case-date">
                <span>哪一天发生的（选填）</span>
                <input
                  type="date"
                  value={caseDate}
                  onChange={(e) => setCaseDate(e.target.value)}
                  disabled={caseBusy}
                />
                <em>填了它，才能算出应期差几天；只点按钮也可以。</em>
              </label>
            </>
          )}
        </div>
      ) : null}

      {/* 两个粒度的标记结果都在这两行里显示 */}
      {msg && <div className="notice notice-ok" role="status"><b>完成</b><span className="n-body">{msg}</span></div>}
      {err && <div className="notice notice-err" role="alert"><b>错误</b><span className="n-body">{err}</span></div>}

      {/* 版本锚点 */}
      {(check.rules_version || check.weights_version) && (
        <div className="d-src" style={{ marginTop: 10 }}>
          规则库 v{check.rules_version || '?'} · 权重表 v{check.weights_version || '?'}
          （权重为工程默认值，未经案例校准，仅参与比较）
          {check.log_id ? ` · 本次校验台账 #${check.log_id}` : ''}
        </div>
      )}

      {/* 免责（与页脚同款，放在结果旁边，免得用户只看结果不看页脚） */}
      <div className="footer-caution" style={{ marginTop: 14 }}>
        <b>郑重提示</b>
        以上为传统术数典籍的架构性整理，仅作文化研究与产品设计参考，不构成投资、医疗或法律建议；
        请不要迷信，遇到难题请通过社会途径寻求帮助。相关内容未经现代科学验证，请自行判断并承担相应责任。
      </div>
    </div>
  )
}

/* ---------- 补五行建议：单个五行的落地建议卡 ---------- */

function SugCard({ wx, dims, yy }: { wx: string; dims: Record<string, unknown>; yy?: FlowYinyangItem[] }) {
  const { src, ...rest } = dims
  /* 方位/颜色/数字是"一眼能用"的三个值，升为一行格子；其余维度保持行式 */
  const GRID = ['方位', '颜色', '数字']
  const grid = GRID.filter((k) => k in rest)
  const others = Object.keys(rest).filter((k) => !GRID.includes(k))
  const srcKeys = srcKeysOf(src)
  return (
    <div className="stack-item">
      <div className="paged-inner-title">补 {wx} 的建议</div>
      {grid.length > 0 && (
        <div className="check-grid">
          {grid.map((k) => (
            <div className="check-item" key={k}>
              <span className="k">{DIM_LABEL[k] || k}</span>
              <SugValue dim={k} val={rest[k]} yy={yy} />
            </div>
          ))}
        </div>
      )}
      {others.map((k) => (
        <div className="sug-row" key={k}>
          <span className="sug-k">{DIM_LABEL[k] || k}</span>
          <span className="sug-v"><SugValue dim={k} val={rest[k]} yy={yy} /></span>
        </div>
      ))}
      {srcKeys.length > 0 && <SrcLine keys={srcKeys} label="典籍出处" />}
    </div>
  )
}

/** 建议维度取值渲染：按维度名分派（数字/物件/质地各走各的，其余按数组/对象/字符串兜底） */
function SugValue({ dim, val, yy }: { dim: string; val: unknown; yy?: FlowYinyangItem[] }) {
  if (dim === '数字') {
    const n = val as { 生数?: number; 成数?: number; 河图?: string } | null | undefined
    if (n) return <>生数 {n.生数 ?? '—'} · 成数 {n.成数 ?? '—'}{n.河图 ? `（河图 ${n.河图}）` : ''}</>
    return <span className="d-src">（暂无建议）</span>
  }
  if (dim === '物件') return <ObjectsBlock o={val as Record<string, unknown> | null | undefined} />
  if (dim === '质地') return <TextureBlock t={val as Record<string, unknown> | null | undefined} yinyang={yy} />
  if (Array.isArray(val)) return <>{val.length ? val.join('、') : '—'}</>
  if (val && typeof val === 'object') {
    const entries = Object.entries(val as Record<string, unknown>)
      .filter(([, v]) => v != null && v !== '')
    if (!entries.length) return <span className="d-src">（暂无建议）</span>
    return (
      <>
        {entries.map(([k, v]) => (
          <span key={k} style={{ display: 'block' }}>{k}：{fmtVal(v)}</span>
        ))}
      </>
    )
  }
  if (typeof val === 'string' && val) return <>{val}</>
  return <span className="d-src">（暂无建议）</span>
}

function fmtVal(v: unknown): string {
  if (Array.isArray(v)) return v.length ? v.join('、') : '—'
  if (v && typeof v === 'object') {
    const s = Object.entries(v as Record<string, unknown>)
      .filter(([, x]) => x != null && x !== '')
      .map(([k, x]) => `${k}：${fmtVal(x)}`)
      .join('；')
    return s || '—'
  }
  return String(v ?? '—')
}

/**
 * 物件（分三层标出层级）。
 * 「静物」一行是五行级的（乾兑合参），而「质地→味分档」已把金拆成庚/辛两列——
 * 不写清"这两行不是一回事"，读起来就是自相矛盾（旧前端实测出过这种观感）。
 */
function ObjectsBlock({ o }: { o: Record<string, unknown> | null | undefined }) {
  if (!o) return <span className="d-src">（暂无建议）</span>
  const arr = (k: string) => (Array.isArray(o[k]) ? (o[k] as string[]) : [])
  const rows: [string, string[], string][] = [
    ['当旺', arr('当旺'), '《五行大义》物象·王（五行级）'],
    ['次旺', arr('次旺'), '《五行大义》物象·相（五行级）'],
    ['静物', arr('静物'), '五行级·乾兑合参，仅供概览；按味细分见下方「质地」'],
  ]
  const shown = rows.filter(([, v]) => v.length > 0)
  if (!shown.length) return <span className="d-src">（暂无建议）</span>
  return (
    <span className="obj">
      {shown.map(([label, v, note]) => (
        <span className="obj-row" key={label}>
          <span className="obj-k">{label}</span>
          <span className="obj-v">{v.join('、')}</span>
          <span className="obj-note">{note}</span>
        </span>
      ))}
    </span>
  )
}

/**
 * 质地分档 + 味分档（这一味具体是什么东西）。
 * 味分档两列（阳/阴，十干列与八卦列）**并列**、各有出处、互不合并（R6：跨载体不得互推）；
 * 每列：干/名 + 具体器物清单 + 润燥宜忌 + 卦侧同类清单 + 注意 + 列内出处。
 */
function TextureBlock({ t, yinyang }: { t: Record<string, unknown> | null | undefined; yinyang?: FlowYinyangItem[] }) {
  if (!t) return <span className="d-src">（暂无建议）</span>
  const fs = (t['味分档'] as Record<string, unknown> | undefined) || {}
  const cols = (['阳', '阴'] as const)
    .map((pos) => ({ pos, c: fs[pos] as Record<string, unknown> | null | undefined }))
    .filter((x) => x.c && Object.keys(x.c).length > 0)
  if (!t['本味推荐'] && cols.length === 0) return <span className="d-src">（暂无建议）</span>
  /* 阴阳细分（寒暖燥湿）按干并入味分档列（2026-10 与旧前端对齐：有质地建议时
     不再单独列一行，避免同一信息出现两遍） */
  const yyByGan: Record<string, FlowYinyangItem> = {}
  for (const it of yinyang || []) yyByGan[it.gan] = it
  return (
    <span className="tex">
      {t['本味推荐'] ? <span className="tex-pick">{String(t['本味推荐'])}</span> : null}
      {t['推荐依据'] ? <span className="tex-note">推荐依据：{String(t['推荐依据'])}</span> : null}
      {cols.length > 0 && (
        <span className="tex-split">
          <span className="tex-head">味分档（这一味具体是什么东西，两列各有出处、不合并）</span>
          <span className="tex-cols">
            {cols.map(({ pos, c }) => {
              const rd = c!['润燥'] as Record<string, unknown> | undefined
              const colSrcs = [
                ...((c!['srcs'] as string[] | undefined) || []),
                ...((rd?.['srcs'] as string[] | undefined) || []),
                ...((c!['卦srcs'] as string[] | undefined) || []),
              ]
              const gan = String(c!['干'] ?? '')
              const yy = yyByGan[gan]
              return (
                <span className="tex-col" key={pos}>
                  <span className="tex-col-head">
                    <i>{pos}</i><b>{gan}</b><span>{String(c!['名'] ?? '')}</span>
                    {yy ? (
                      <em
                        className="tex-yy"
                        title={`${yy.gan}（${yy.yinyang}${yy.han_nuan ? `·${yy.han_nuan}` : ''}${yy.zao_shi ? `·${yy.zao_shi}` : ''}）${yy.note ? `：${yy.note}` : ''}`}
                      >
                        {yy.yinyang}{yy.han_nuan ? `·${yy.han_nuan}` : ''}{yy.zao_shi ? `·${yy.zao_shi}` : ''}
                      </em>
                    ) : null}
                  </span>
                  {((c!['物'] as string[] | undefined) || []).length > 0 && (
                    <span className="tex-goods">
                      {((c!['物'] as string[]) || []).map((w, i) => <em key={i}>{w}</em>)}
                    </span>
                  )}
                  {rd ? (
                    <span className="tex-rz">
                      <span className="tex-rz-tag">润燥·{String(rd['性'] ?? '')}</span>
                      {((rd['宜'] as string[] | undefined) || []).map((w, i) => <em key={`y${i}`} className="ok">{w}</em>)}
                      {((rd['忌'] as string[] | undefined) || []).map((w, i) => <em key={`j${i}`} className="bad">忌：{w}</em>)}
                    </span>
                  ) : null}
                  {c!['卦'] ? (
                    <span className="tex-gua">
                      <span className="tex-gua-tag">同类可参·卦侧「{String(c!['卦'])}」</span>
                      {((c!['卦物'] as string[] | undefined) || []).map((w, i) => <em key={i}>{w}</em>)}
                    </span>
                  ) : null}
                  {c!['note'] ? <span className="tex-caveat">注意：{String(c!['note'])}</span> : null}
                  {colSrcs.length > 0 && <SrcLine keys={colSrcs} label="出处" />}
                </span>
              )
            })}
          </span>
          {fs['note'] ? <span className="tex-note">{String(fs['note'])}</span> : null}
          {fs['五行级'] ? <span className="tex-note">{String(fs['五行级'])}</span> : null}
        </span>
      )}
      {t['约束'] ? <span className="tex-note">约束：{String(t['约束'])}</span> : null}
      {typeof t['src'] === 'string' && <SrcLine keys={splitKeys(t['src'])} label="质地出处" />}
    </span>
  )
}

/* ---------- 出处（多键，点开核原文） ---------- */

/** 后端 src 字符串用「、」并多键（或 "—" 表示无），拆成独立键去重 */
function splitKeys(s: string): string[] {
  return Array.from(new Set(
    s.split('、').map((x) => x.trim()).filter((x) => x && x !== '—'),
  ))
}

/** 每个五行的 src 表（{方位: 'A、B', 颜色: 'C', …}）→ 去重后的全部键 */
function srcKeysOf(src: unknown): string[] {
  if (!src || typeof src !== 'object') return []
  const keys = Object.values(src as Record<string, unknown>)
    .flatMap((v) => splitKeys(String(v ?? '')))
  return Array.from(new Set(keys))
}

function SrcLine({ keys, label = '出处' }: { keys: string[]; label?: string }) {
  const uniq = Array.from(new Set(keys.filter(Boolean)))
  if (!uniq.length) return null
  return (
    <span className="src-line">
      {label}：
      {uniq.map((k, i) => (
        <span key={k}>{i > 0 ? '、' : ''}<QuoteRef k={k} /></span>
      ))}
    </span>
  )
}

/* ---------- 流动五行判定表：默认当前命盘档位，其余档位小标签切换 ---------- */

function FlowCard({ f, yyMerged }: { f: FlowBlock; yyMerged?: boolean }) {
  const rows = f.rows || []
  /** 强弱四档（可切换的"档位"）；「局中交战」是通关行，不是档位 */
  const tierRows = rows.filter((r) => r.state !== '局中交战')
  const jzRow = rows.find((r) => r.state === '局中交战')
  const activeRow = tierRows.find((r) => r.active)
  /** 默认选中当前命盘命中的档位；无档案（没有档位行）时只有通关行 */
  const [sel, setSel] = useState(activeRow?.state ?? tierRows[0]?.state ?? jzRow?.state ?? '')
  const shown = rows.find((r) => r.state === sel) || activeRow || jzRow || tierRows[0] || null
  /** 看的是非命中的假设档：明标「假设」，免得被误读成"本站给了两套断语" */
  const hypo = !!shown && !shown.active && shown.state !== '局中交战'

  const cell = (c: FlowCell | null | undefined, side: string) => {
    // 没有条目的边不渲染「无条目」占位——只列有内容的边（站长要求）
    if (!c) return null
    return (
      <span className={`flow-cell ${c.conflict ? 'conflict' : ''}`} key={side}>
        <b>{f.header?.[side] || side}</b>　{c.grade ? `【${c.grade}】` : ''}{c.combined || c.note}
        {c.chengwu ? (
          <em className="cw-badge" title={c.chengwu.note}>
            乘侮·{c.chengwu.value}
          </em>
        ) : null}
        {c.sheng_three && c.sheng_three.value !== '正生' ? (
          <em className="cw-badge" title={c.sheng_three.note}>
            生害·{c.sheng_three.value}
          </em>
        ) : null}
        {c.conflict ? <em>（注意：静态格与边态不同源，需复核）</em> : null}
        {c.conflict_suppressed ? <em>（本次不告警的理由：{c.conflict_suppressed}）</em> : null}
        {c.src ? <span className="flow-src">出处：<QuoteRef k={c.src} /></span> : null}
      </span>
    )
  }

  const rowView = (r: FlowRow, isHypo: boolean) => (
    <div className="flow-row" key={r.state}>
      <span className="flow-rowstate">
        {r.state}
        {r.active ? <span className="flow-now">命盘当前</span> : null}
        {isHypo ? <span className="flow-hypo">假设</span> : null}
      </span>
      {SIDES.map((side) => cell(r.cells?.[side] as FlowCell | null | undefined, side))}
    </div>
  )

  return (
    <div className="stack-item">
      <div className="paged-inner-title">五行 {f.wx} · 四边判定</div>
      {f.state ? <div className="flow-state" style={{ display: 'inline-block', marginBottom: 6 }}>{f.state}{f.state_score !== undefined ? `（${f.state_score}）` : ''}</div> : null}
      {f.state_note && <div className="d-src">{f.state_note}</div>}
      {f.month_state?.note && <div className="d-src">月令五态：{f.month_state.note}</div>}
      {tierRows.length > 0 && (
        <div className="flow-tabs" role="tablist" aria-label={`五行 ${f.wx} 的强弱档位`}>
          {tierRows.map((r) => (
            <button
              key={r.state}
              type="button"
              role="tab"
              id={`flow-tab-${f.wx}-${r.state}`}
              aria-selected={sel === r.state}
              aria-controls={`flow-panel-${f.wx}`}
              className={`flow-tag ${sel === r.state ? 'on' : ''}`}
              title={r.active ? '当前命盘命中的档位' : '点一下看「若你是这一档」的判定'}
              onClick={() => setSel(r.state)}
            >
              {r.state}{r.active ? ' · 命盘当前' : ''}
            </button>
          ))}
        </div>
      )}
      <div role="tabpanel" id={`flow-panel-${f.wx}`} aria-labelledby={`flow-tab-${f.wx}-${sel}`}>
        {shown && rowView(shown, hypo)}
        {jzRow && shown && jzRow.state !== shown.state && rowView(jzRow, false)}
      </div>
      {(jzRow?.hits || []).map((h, i) => (
        <div className="d-src" key={i}>通关：{h}</div>
      ))}
      {f.tongguan_src && <div className="d-src">通关依据：<QuoteRef k={f.tongguan_src} /></div>}
      {/* 体性提示多条合并成一个带序号的清单（每条独立出处） */}
      {(f.qualities || []).length > 0 && (
        <div className="d-src">
          体性提示：
          {(f.qualities || []).map((q, i) => (
            <span key={i} style={{ display: 'block' }}>
              {i + 1}. {q.note}{q.src ? <>（<QuoteRef k={q.src} />）</> : ''}
            </span>
          ))}
        </div>
      )}
      {(f.branch_notes || []).map((n, i) => (
        <div className="d-src" key={i}>地支：{n.type} · {n.pair} — {n.note}{n.src ? <>（<QuoteRef k={n.src} />）</> : ''}</div>
      ))}
      {!yyMerged && f.yinyang?.items?.length ? (
        <div className="d-src">
          阴阳寒暖：{f.yinyang.items.map((it) => `${it.gan}（${it.yinyang}${it.han_nuan ? `·${it.han_nuan}` : ''}${it.zao_shi ? `·${it.zao_shi}` : ''}）`).join('、')}
        </div>
      ) : null}
      {f.branch_missing && <div className="d-src">地支作用校验未启用：命局基线缺四支信息（重新保存命局档案后自动启用）。</div>}
    </div>
  )
}
