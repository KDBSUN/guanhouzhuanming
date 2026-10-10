import { useCallback, useEffect, useState } from 'react'
import { FishTail, SealStamp } from '../art/book'
import { friendlyError } from '../api/client'
import {
  VERDICTS, claimIcs, downloadIcs, fetchCalibration, fetchClaimByReceipt, fetchFeedbackRecent,
  issueReceipt, postBetaNote, postClaimVerdict, receiptFromLocation, receiptLink,
  type CalibrationView, type Claim, type FeedbackItem, type Verdict,
} from '../api/feedback'

/* ============================================================
   公测反馈（客问）—— 已接后端
   两件事：
     1. 写留言（服务端会邮件通知站长）
     2. 对自己历史断语逐条标记应验/未验/反向…（进校准台账）
   另有「回执链接」路径：凭一枚只对一条断言有效的回执码作答，不需要登录
   ============================================================ */

const FEEDBACK_INTRO =
  '公测期间，反馈会直接进入校准台账：每条判断都可以单独标记"应验/未验/反向"，'
  + '边界样本（判定正好擦着阈值的那些）会用来复核阈值取值，改动需人工批准、绝不自动调参。'

const WINDOW_HINT: Record<string, string> = {
  客观可验: '有明确事实可查',
  主观可验: '只有你自己能判断',
  不可验: '无法事后判定',
}

export default function FeedbackPage() {
  const [receipt] = useState(receiptFromLocation)
  if (receipt) return <ReceiptView receipt={receipt} />

  return <FeedbackMain />
}

/* ==================== 回执落地页（极窄：只回答这一条断言） ==================== */

function ReceiptView({ receipt }: { receipt: string }) {
  const [data, setData] = useState<{ claim: Claim; verdicts: string[]; feedback: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [verdict, setVerdict] = useState('')
  const [note, setNote] = useState('')
  const [done, setDone] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    fetchClaimByReceipt(receipt).then((d) => {
      setData(d)
      if (d?.feedback) setVerdict(d.feedback)
      setLoading(false)
    }).catch(() => {
      setLoading(false)
      setMsg('链接验证失败，请稍后刷新重试。')
    })
  }, [receipt])

  const submit = async () => {
    if (!data || !verdict) { setMsg('请先选一个结果。'); return }
    const r = await postClaimVerdict(0, data.claim.id, verdict, note, receipt)
    if (!r.ok) { setMsg('提交失败，链接可能已失效。'); return }
    setDone(true)
    setMsg(`已记录：${verdict}。谢谢你回头补这一笔。`)
  }

  return (
    <div>
      <div className="leaf-head">
        <span className="juan-mark">观候·转明</span>
        <FishTail />
        <span className="juan">客问 · 凭回执作答</span>
        <span className="folio">卷六</span>
      </div>
      <div className="juan-title">
        <h1>这一件事后来如何</h1>
        <p className="juan-sub">凭回执码作答 · 不需要登录</p>
      </div>

      {loading && <div className="ink-skel" aria-hidden><span style={{ width: '40%' }} /><span style={{ width: '70%' }} /></div>}

      {!loading && !data && (
        <div className="notice notice-err">
          <b>链接无效</b>
          <span className="n-body">
            这个链接已经失效或不存在。回到本站「反馈」页，可以在任意一条断言上重新生成提醒与链接。
          </span>
        </div>
      )}

      {data && (
        <div className="register">
          <span className="reg-label">当 时 的 断 言</span>
          <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>{data.claim.text}</div>
          <div className="d-src" style={{ marginTop: 6 }}>
            {data.claim.type}
            {data.claim.rule ? ` · 归属规则：${data.claim.rule}` : ''}
            {data.claim.verifiability ? ` · ${data.claim.verifiability}` : ''}
            {data.claim.until ? ` · 验证窗口至 ${data.claim.until}` : ''}
            {data.claim.src ? ` · 书证：${data.claim.src}` : ''}
          </div>

          <div className="bz-head"><h2>后来如何</h2><span className="rule" /><span className="aside">选一个最贴近的</span></div>
          <div className="slip-row">
            {VERDICTS.map((v) => (
              <button key={v} type="button" className={`slip ${verdict === v ? 'active' : ''}`}
                disabled={done} onClick={() => setVerdict(v)}>{v}</button>
            ))}
          </div>
          <span className="reg-hint">若与上次记录不同，会更新为这一次的选择。</span>

          <textarea className="textarea" rows={3} maxLength={300} style={{ marginTop: 12 }}
            placeholder="补充说明：实际发生了什么？（判错的情况写清具体经过最有价值）"
            aria-label="补充说明"
            value={note} onChange={(e) => setNote(e.target.value)} disabled={done} />

          <div className="btn-row" style={{ marginTop: 14 }}>
            <button type="button" className="btn" disabled={done} onClick={submit}>提 交</button>
          </div>
          {msg && <div className={`notice ${done ? 'notice-ok' : 'notice-warn'}`}><b>{done ? '完成' : '提示'}</b><span className="n-body">{msg}</span></div>}

          <p className="stub-line" style={{ marginTop: 14 }}>
            这条链接只够回答上面这一条断言：读不到你的记录、档案或其它内容，也改不了别的东西。
            想把它作废，在本站重新生成一条即可（旧链接会继续指向同一条断言）。
          </p>
        </div>
      )}
    </div>
  )
}

/* ==================== 主页面：留言 + 逐条反馈 + 校准台账 ==================== */

function FeedbackMain() {
  const [recent, setRecent] = useState<FeedbackItem[]>([])
  const [calib, setCalib] = useState<CalibrationView | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  /* 留言表单 */
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  /* F3：联系方式持久化（旧前端行为：localStorage 记着，提交后保留、下次进来自动填上） */
  const [contact, setContact] = useState(() => {
    try { return localStorage.getItem('beta_contact') || '' } catch { return '' }
  })
  const [sending, setSending] = useState(false)

  /* 逐条反馈的临时输入：key = `${log_id}:${claim_id}` */
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [codes, setCodes] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [items, c] = await Promise.all([fetchFeedbackRecent(8), fetchCalibration()])
      setRecent(items)
      setCalib(c)
    } catch (e) {
      setError(friendlyError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const sendNote = async () => {
    if (!content.trim()) { setError('请先写点内容'); return }
    setSending(true); setError(''); setMsg('')
    const r = await postBetaNote(content.trim(), contact.trim(), 0, title.trim())
    setSending(false)
    if (!r.ok) { setError('留言提交失败，稍后再试。'); return }
    setTitle(''); setContent('')     // 联系方式保留并记进本机（旧前端行为）
    try { localStorage.setItem('beta_contact', contact.trim()) } catch { /* 忽略 */ }
    setMsg(r.mailed
      ? '已收到，并已邮件通知站长。谢谢你。'
      : '已收到（邮件通知未发出，但留言已入库）。谢谢你。')
  }

  const mark = async (logId: number, claimId: string, verdict: Verdict) => {
    const key = `${logId}:${claimId}`
    setBusy(key); setError('')
    const r = await postClaimVerdict(logId, claimId, verdict, notes[key] || '')
    setBusy('')
    if (!r.ok) { setError('标记失败，稍后再试。'); return }
    setRecent((prev) => prev.map((it) => it.log_id === logId
      ? { ...it, feedback: { ...(it.feedback || {}), [claimId]: verdict } }
      : it))
    setMsg(`已记录：${verdict}${r.mailed ? '（已邮件通知）' : ''}。标记过的断言会进校准台账。`)
  }

  const remind = async (item: FeedbackItem, claim: Claim) => {
    const key = `${item.log_id}:${claim.id}`
    setBusy(`r-${key}`); setError('')
    const code = await issueReceipt(item.log_id, claim.id)
    setBusy('')
    if (!code) { setError('生成提醒失败，稍后再试。'); return }
    setCodes((prev) => ({ ...prev, [key]: code }))
    downloadIcs(`断言提醒-${claim.id}.ics`, claimIcs({ claim, question: item.question, receipt: code }))
    setMsg('已下载日历提醒文件（含作答链接）。导入日历后到期会提醒你回来标记。')
  }

  const copyLink = async (logId: number, claimId: string) => {
    const key = `${logId}:${claimId}`
    let code = codes[key]
    if (!code) {
      code = await issueReceipt(logId, claimId)
      if (!code) { setError('生成链接失败，稍后再试。'); return }
      setCodes((prev) => ({ ...prev, [key]: code }))
    }
    try {
      await navigator.clipboard.writeText(receiptLink(code))
      setMsg('已复制作答链接（不需要登录，换设备也能用）。')
    } catch {
      setMsg(`作答链接：${receiptLink(code)}`)
    }
  }

  return (
    <div>
      <div className="leaf-head">
        <span className="juan-mark">观候·转明</span>
        <FishTail />
        <span className="juan">客问</span>
        <span className="folio">卷六</span>
      </div>
      <div className="juan-title">
        <h1>公测反馈</h1>
        <p className="juan-sub">逐条标记应验 / 未验 / 反向 · 留言 · 校准台账透明可查</p>
      </div>

      <div className="register" style={{ marginBottom: 16 }}>
        <span className="reg-label">这 是 什 么</span>
        <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>{FEEDBACK_INTRO}</div>
        <span className="reg-hint">
          留言会邮件通知站长；断言反馈会进校准台账。台账里的阈值改动一律需要人工批准，系统不会自动改数。
        </span>
      </div>

      {/* 留言 */}
      <div className="bz-head">
        <h2>写留言</h2>
        <span className="rule" />
        <span className="aside">哪里不准、哪里好用、想要什么功能</span>
      </div>
      <div className="register">
        <label className="reg-label" htmlFor="fb-title">标题</label>
        <input id="fb-title" className="input" maxLength={40} value={title}
          placeholder="一句话说清主题，如：择日表某天不准" onChange={(e) => setTitle(e.target.value)} />
        <label className="reg-label" style={{ marginTop: 12 }} htmlFor="fb-content">内容</label>
        <textarea id="fb-content" className="textarea" rows={5} maxLength={500} value={content}
          placeholder="哪里不准、哪里好用、想要什么功能。若是某次判断不对，请写清：所问之事、系统怎么判、实际发生了什么。"
          onChange={(e) => setContent(e.target.value)} />
        <span className="reg-hint">{content.length}/500 字</span>
        <label className="reg-label" style={{ marginTop: 12 }} htmlFor="fb-contact">联系方式（选填，便于回访）</label>
        <input id="fb-contact" className="input" style={{ maxWidth: 300 }} value={contact}
          placeholder="邮箱 / 微信" onChange={(e) => setContact(e.target.value)} />
        <div className="btn-row" style={{ marginTop: 14 }}>
          <button type="button" className="btn" onClick={sendNote} disabled={sending}>
            {sending ? '提交中…' : '提交留言'}
          </button>
        </div>
      </div>

      {msg && <div className="notice notice-ok"><b>完成</b><span className="n-body">{msg}</span></div>}
      {error && <div className="notice notice-err"><b>错误</b><span className="n-body">{error}</span></div>}

      {/* 逐条反馈 */}
      <div className="bz-head">
        <h2>逐条反馈</h2>
        <span className="rule" />
        <span className="aside">最近 {recent.length} 次校验 · 每条断言单独标记</span>
      </div>

      {loading && <div className="ink-skel" aria-hidden><span style={{ width: '36%' }} /><span style={{ width: '78%' }} /><span style={{ width: '62%' }} /></div>}

      {!loading && recent.length === 0 && (
        <div className="dai-zuan" style={{ padding: '30px 0' }}>
          <p className="dz-sub">
            还没有可反馈的校验记录 —— 先去起一卦或排一次盘，回来就能逐条标记了。
          </p>
        </div>
      )}

      {recent.map((item) => (
        <div className="detail-block" key={item.log_id}>
          <div className="d-title">
            #{item.log_id} · {item.ts.replace('T', ' ').slice(0, 16)} · 净档 {item.net || '—'}
          </div>
          {item.question && <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>所问：{item.question}</div>}
          {item.decision && <div className="d-src" style={{ marginTop: 4 }}>裁决：{item.decision}</div>}

          {/* F2：断言折叠（与卦的结果页同款 summary，默认收起，不把整页撑长） */}
          <details className="pd-fold" style={{ marginTop: 10 }}>
            <summary>
              想细究的话：逐条断言（{(item.claims || []).length} 条，
              已标 {(item.claims || []).filter((c) => (item.feedback || {})[c.id]).length} 条）
            </summary>
            <div style={{ marginTop: 8 }}>
              {(item.claims || []).map((c) => {
            const key = `${item.log_id}:${c.id}`
            const cur = (item.feedback || {})[c.id] || ''
            return (
              <div className="claim-card" key={key}>
                <div className="claim-head">
                  <span className="claim-type">{c.type}</span>
                  <span className="claim-text">{c.text}</span>
                </div>
                <div className="claim-meta">
                  {c.rule ? `规则：${c.rule}` : ''}
                  {c.verifiability ? ` · ${c.verifiability}${WINDOW_HINT[c.verifiability] ? `（${WINDOW_HINT[c.verifiability]}）` : ''}` : ''}
                  {c.since || c.until ? ` · 验证窗口 ${c.since} → ${c.until}` : ''}
                  {c.params?.length ? ` · 参与参数：${c.params.join('、')}` : ''}
                </div>
                <div className="slip-row" style={{ marginTop: 8 }}>
                  {VERDICTS.map((v) => (
                    <button key={v} type="button"
                      className={`slip ${cur === v ? 'active' : ''}`}
                      aria-pressed={cur === v}
                      disabled={busy === key}
                      onClick={() => mark(item.log_id, c.id, v)}>
                      {v}
                    </button>
                  ))}
                  <span className="hint-line" style={{ alignSelf: 'center' }}>
                    {cur ? `已标记：${cur}` : '未标记'}
                  </span>
                </div>
                <div className="claim-actions">
                  <input className="mini-input" style={{ flex: 1, minWidth: 180 }}
                    placeholder="补充说明（选填）：实际发生了什么？"
                    aria-label="补充说明（选填）"
                    value={notes[key] || ''}
                    onChange={(e) => setNotes((prev) => ({ ...prev, [key]: e.target.value }))} />
                  <button type="button" className="btn-outline" style={{ padding: '5px 14px', fontSize: 'var(--type-data)' }}
                    disabled={busy === `r-${key}`} onClick={() => remind(item, c)}>
                    日历提醒
                  </button>
                  <button type="button" className="btn-outline" style={{ padding: '5px 14px', fontSize: 'var(--type-data)' }}
                    onClick={() => copyLink(item.log_id, c.id)}>
                    复制作答链接
                  </button>
                </div>
                {codes[key] && <div className="d-src">回执码已生成：{codes[key].slice(0, 8)}…（只对这一条断言有效）</div>}
              </div>
            )
          })}
            </div>
          </details>
        </div>
      ))}

      {/* 校准台账 */}
      <div className="bz-head">
        <h2>校准台账</h2>
        <span className="rule" />
        <span className="aside">透明可查 · 阈值只经人工批准</span>
      </div>
      {calib ? (
        <div className="detail-block">
          <div className="check-grid">
            <div className="check-item">
              <span className="k">待批提案</span><b>{calib.proposals?.length || 0}</b>
            </div>
            <div className="check-item">
              <span className="k">边界样本</span><b>{calib.boundary?.length || 0}</b>
            </div>
            {Object.keys(calib.guardrails || {}).length > 0 && (
              <>
                <div className="check-item">
                  <span className="k">护栏 · 单次变动</span>
                  ≤ ±{Math.round((calib.guardrails.max_delta_ratio ?? 0.3) * 100)}%
                </div>
                <div className="check-item">
                  <span className="k">护栏 · 最小样本</span>
                  {calib.guardrails.min_samples ?? 5} 条
                </div>
              </>
            )}
          </div>
          {calib.proposals?.length ? (
            calib.proposals.map((p) => (
              <div className="check-hit" key={p.id}>
                提案 #{p.id}：{p.param} {p.old_value} → {p.new_value}（{p.n_samples} 样本，未验/反向 {Math.round((p.flip_rate || 0) * 100)}%）
                · 状态 {p.status}
              </div>
            ))
          ) : (
            <div className="d-src">暂无待批提案。</div>
          )}
          {calib.boundary?.length ? (
            <>
              <div className="yingqi-group-title">边界样本（判定值正好擦着阈值的那些）</div>
              {calib.boundary.slice(0, 8).map((b) => (
                <div className="check-hit" key={`${b.param}-${b.side}-${b.n}`}>
                  {b.param} · {b.side} · {b.n} 个样本 · 阈值 {b.threshold}
                </div>
              ))}
            </>
          ) : (
            <div className="d-src">暂无边界样本。</div>
          )}
          <div className="d-src" style={{ marginTop: 8 }}>
            护栏：单次变动 ≤ ±{Math.round((calib.guardrails?.max_delta_ratio ?? 0.3) * 100)}%、
            最小样本 {calib.guardrails?.min_samples ?? 5} 条、必须人工批准——不做拟合、不自动调参。
          </div>
        </div>
      ) : (
        <span className="hint-line">校准台账读取失败（不影响留言与反馈标记）。</span>
      )}

      <div className="footer-caution" style={{ marginTop: 20 }}>
        <b>郑重提示</b>
        请不要迷信。本站所有功能只是用程序的方式展示传统的占卜行为，没有神力，也不会替你做任何决定。
        遇到实际难题，请通过社会途径寻求帮助。所涉内容未经现代科学验证，仅作文化研究参考。
      </div>
      <SealStamp tone="plat" label="公测">测</SealStamp>
    </div>
  )
}
