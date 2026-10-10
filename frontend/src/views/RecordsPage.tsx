import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FishTail } from '../art/book'
import ProfileLine from '../common/ProfileLine'
import { fetchLogs, getProfile, postCaseOutcome, type LogRow, type MingjuProfile } from '../api/mingju'
import {
  KIND_LABEL, deleteRecord, emptyTrash, fetchRecords, fetchTrash, fmtTime,
  purgeRecord, restoreRecords, updateRecord,
  type RecordKind, type RecordRow, type TrashRow,
} from '../api/records'
import { friendlyError } from '../api/client'
import { exportBackup, importBackup, suggestPassphrase } from '../api/backup'
import { getOwnerToken, dismissAddToHomeScreenHint, requestPersistentStorage, shouldSuggestAddToHomeScreen } from '../api/owner'

/* ============================================================
   我的记录（占验录）—— 已接后端
   点一条记录＝跳回当时的界面重新看（快照回放，不重新起卦）
   删除是软删除，进「最近删除」保留 30 天，可恢复或彻底删除
   ============================================================ */

/** 备份文件大小的可读写法（导入时展示用户自己挑的那个文件） */
function fmtSize(n: number): string {
  if (n < 1024) return `${n} 字节`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

const FILTERS: { value: '' | RecordKind; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'meihua', label: '梅花' },
  { value: 'liuyao', label: '六爻' },
  { value: 'bazi', label: '八字' },
]

export default function RecordsPage({ onReplay }: {
  onReplay: (kind: RecordKind, payload: Record<string, unknown>, id?: number) => void
}) {
  const [kind, setKind] = useState<'' | RecordKind>('')
  const [rows, setRows] = useState<RecordRow[]>([])
  const [trash, setTrash] = useState<TrashRow[]>([])
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [profile, setProfile] = useState<MingjuProfile | null>(null)
  const [showTrash, setShowTrash] = useState(false)
  const [editing, setEditing] = useState<RecordRow | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editNote, setEditNote] = useState('')
  const editBoxRef = useRef<HTMLDivElement | null>(null)
  const editOpenerRef = useRef<HTMLElement | null>(null)

  /* ---------- 校验台账（check_log）：每次校验/排盘一行 ----------
     它与记录是两回事：记录存的是"回放快照"，台账存的是"当时怎么判的"
     （净档、处方、版本锚点、断言清单、整案反馈）。数据一直在库里，
     这里只是给它一个回看入口。整批一次取 60 行（后端上限 200）。 */
  const [ledger, setLedger] = useState<LogRow[]>([])
  const [showLedger, setShowLedger] = useState(false)
  const [ledgerBusy, setLedgerBusy] = useState(false)
  const [ledgerErr, setLedgerErr] = useState('')

  const loadLedger = useCallback(async () => {
    setLedgerBusy(true); setLedgerErr('')
    try {
      setLedger(await fetchLogs(60))
    } catch (e) {
      setLedgerErr(friendlyError(e))
    } finally {
      setLedgerBusy(false)
    }
  }, [])

  const load = useCallback(async (k: '' | RecordKind) => {
    setLoading(true); setError('')
    try {
      const list = await fetchRecords(k)
      setRows(list)
    } catch (e) {
      setError(friendlyError(e))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTrash = useCallback(async () => {
    try {
      const { rows: t, days: d } = await fetchTrash()
      setTrash(t); setDays(d)
    } catch (e) {
      setError(friendlyError(e))
    }
  }, [])

  useEffect(() => { load(kind) }, [kind, load])
  useEffect(() => { loadTrash(); getProfile().then(setProfile).catch(() => setProfile(null)) }, [loadTrash])

  /* ---------- 编辑弹窗：对话框语义 + 焦点陷阱 + 关闭后还焦 ---------- */
  useEffect(() => {
    if (!editing) return
    const box = editBoxRef.current
    if (!box) return
    const focusables = () => Array.from(
      box.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((el) => !el.hasAttribute('disabled'))
    focusables()[0]?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        setEditing(null)
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
      editOpenerRef.current?.focus()
      editOpenerRef.current = null
    }
  }, [editing])

  /* ---------- 操作 ---------- */
  const togglePin = async (row: RecordRow) => {
    setMsg('')
    try {
      const ok = await updateRecord(row.id, { pinned: row.pinned ? 0 : 1 })
      if (!ok) { setError('置顶失败（请稍后重试，或刷新页面）'); return }
      await load(kind)
    } catch (e) {
      setError(friendlyError(e))
    }
  }

  const remove = async (row: RecordRow) => {
    if (!window.confirm(`删除「${row.title || '未命名'}」？会先进「最近删除」，${days} 天内可找回。`)) return
    setMsg('')
    try {
      const ok = await deleteRecord(row.id)
      if (!ok) { setError('删除失败（请稍后重试，或刷新页面）'); return }
      setMsg('已移入「最近删除」。')
      await load(kind); await loadTrash()
    } catch (e) {
      setError(friendlyError(e))
    }
  }

  const openEdit = (row: RecordRow) => {
    editOpenerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setEditing(row); setEditTitle(row.title || ''); setEditNote(row.note || '')
  }

  const saveEdit = async () => {
    if (!editing) return
    try {
      const ok = await updateRecord(editing.id, { title: editTitle.trim(), note: editNote.trim() })
      if (!ok) { setError('保存失败（请稍后重试，或刷新页面）'); return }
      setEditing(null); setMsg('已保存。')
      await load(kind)
    } catch (e) {
      setError(friendlyError(e))
    }
  }

  const restore = async (ids: number[]) => {
    try {
      const n = await restoreRecords(ids)
      setMsg(n ? `已恢复 ${n} 条。` : '恢复失败（请稍后重试，或刷新页面）。')
      await load(kind); await loadTrash()
    } catch (e) {
      setError(friendlyError(e))
    }
  }

  const purge = async (row: TrashRow) => {
    if (!window.confirm('彻底删除这一条？不可恢复。')) return
    try {
      const ok = await purgeRecord(row.id)
      if (!ok) { setError('彻底删除失败（请稍后重试，或刷新页面）'); return }
      await loadTrash()
    } catch (e) {
      setError(friendlyError(e))
    }
  }

  const clearTrash = async () => {
    if (!window.confirm('清空「最近删除」？其中所有记录将不可恢复。')) return
    try {
      const n = await emptyTrash()
      setMsg(`已彻底删除 ${n} 条。`)
      await loadTrash()
    } catch (e) {
      setError(friendlyError(e))
    }
  }

  const counts = useMemo(() => {
    const c: Record<string, number> = { meihua: 0, liuyao: 0, bazi: 0 }
    rows.forEach((r) => { c[r.kind] = (c[r.kind] || 0) + 1 })
    return c
  }, [rows])

  /* ---------- 备份与搬家 ----------
     导出与导入各用各的密码框：导入的密码是「那个文件当初用的密码」，
     和本次导出要设的新密码不是同一件事，混用一个框必然出错。
     两个框都能切换明文显示——生成出来的密码必须看得见、能复制。 */
  const [expPass, setExpPass] = useState('')
  const [expShow, setExpShow] = useState(false)
  const [copied, setCopied] = useState(false)
  const [impFile, setImpFile] = useState<File | null>(null)
  const [impPass, setImpPass] = useState('')
  const [impShow, setImpShow] = useState(false)
  const [impError, setImpError] = useState('')
  const [busyBackup, setBusyBackup] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const genPass = () => {
    setExpPass(suggestPassphrase())
    setExpShow(true)   // 直接亮出来：看不见的密码等于没生成
    setCopied(false)
    setError('')
  }

  const copyPass = async () => {
    if (!expPass) return
    try {
      await navigator.clipboard.writeText(expPass)
      setCopied(true)
    } catch {
      setExpShow(true)
      setError('浏览器不让自动复制，密码已改为明文显示，请手动选中后复制')
    }
  }

  const doExport = async () => {
    setBusyBackup(true); setError(''); setMsg('')
    try {
      const name = await exportBackup(expPass, getOwnerToken())
      setMsg(`已导出加密备份 ${name}。请确认密码已经存好：密码不经过服务器，忘了谁也解不开。`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusyBackup(false)
    }
  }

  /** 选中文件只是「待导入」：不立刻解密，先让用户看到文件名并输入那个文件的密码 */
  const pickFile = (f: File | null) => {
    if (!f) return
    setImpFile(f)
    setImpPass('')
    setImpShow(false)
    setImpError('')
    setError(''); setMsg('')
  }

  const cancelImport = () => {
    setImpFile(null); setImpPass(''); setImpShow(false); setImpError('')
    if (fileRef.current) fileRef.current.value = ''
  }

  const doImport = async () => {
    if (!impFile) return
    if (!impPass) { setImpError('请先输入这个备份文件当初导出时用的密码'); return }
    setBusyBackup(true); setImpError(''); setError(''); setMsg('')
    try {
      const r = await importBackup(impPass, impFile)
      setMsg(`导入完成：命局档案 1 份 · 记录 ${r.records} 条 · 台账 ${r.ledger.logs} 条 / 断言反馈 ${r.ledger.feedback} 条。`)
      cancelImport()
      await load(kind); await loadTrash(); getProfile().then(setProfile).catch(() => {})
    } catch (e) {
      // 密码错、文件损坏都留在面板里，改密码重试，不必重新选文件
      setImpError((e as Error).message)
    } finally {
      setBusyBackup(false)
    }
  }

  /* ---------- 存储持久化与 iOS 加主屏提示 ---------- */
  const [a2hs, setA2hs] = useState(false)
  const [persistState, setPersistState] = useState('')
  useEffect(() => {
    if (shouldSuggestAddToHomeScreen()) setA2hs(true)
    // 进记录页就顺手申请持久化存储：失败也没关系，只是"尽量别被清"
    requestPersistentStorage().then((ok) => setPersistState(ok ? '已申请到持久化存储' : '浏览器未授予持久化存储'))
  }, [])

  return (
    <div>
      <div className="leaf-head">
        <span className="juan-mark">易占</span>
        <FishTail />
        <span className="juan">占验录</span>
        <span className="folio">卷四</span>
      </div>
      <div className="juan-title">
        <h1>我的记录</h1>
        <p className="juan-sub">点一条记录＝跳回当时的界面重新看 · 删除只是移入最近删除</p>
      </div>

      <div className="register" style={{ marginBottom: 16 }}>
        <span className="reg-label">命 局 档 案</span>
        <ProfileLine profile={profile} />
      </div>

      {/* 工具条 */}
      <div className="btn-row" style={{ marginBottom: 6 }}>
        <div className="slip-row" role="group" aria-label="按类型筛选">
          {FILTERS.map((f) => (
            <button key={f.value || 'all'} type="button"
              className={`slip ${kind === f.value ? 'active' : ''}`}
              onClick={() => setKind(f.value)}>
              {f.label}{f.value ? ` ${counts[f.value] || 0}` : ` ${rows.length}`}
            </button>
          ))}
        </div>
        <button type="button" className="btn-outline" style={{ padding: '6px 16px', fontSize: 'var(--type-data)' }}
          onClick={() => { load(kind); loadTrash() }}>
          刷 新
        </button>
      </div>
      <div className="d-src" style={{ marginBottom: 10 }}>
        点「回放」＝跳回当时的界面重新看那条卦（用当时的快照还原，不会重新起卦、也不会产生新记录）；
        编辑可改标题与备注，置顶会排在最前，删除只是移入「最近删除」。
      </div>

      {msg && <div className="notice notice-ok"><b>完成</b><span className="n-body">{msg}</span></div>}
      {error && <div className="notice notice-err"><b>错误</b><span className="n-body">{error}</span></div>}

      {/* 列表 */}
      {loading && <div className="ink-skel" aria-hidden><span style={{ width: '40%' }} /><span style={{ width: '72%' }} /><span style={{ width: '58%' }} /></div>}

      {!loading && rows.length === 0 && (
        <div className="dai-zuan" style={{ padding: '40px 0' }}>
          <p className="dz-sub">
            还没有记录。起一卦或排一盘就会自动留痕；点任意一条即可跳回当时的界面重新查看。
          </p>
        </div>
      )}

      {!loading && rows.length > 0 && (
        <div className="rec-list">
          {rows.map((r) => (
            <div className={`rec-row ${r.pinned ? 'pinned' : ''}`} key={r.id}>
              <div className="rec-main">
                <div className="rec-head">
                  <span className={`rec-kind k-${r.kind}`}>{KIND_LABEL[r.kind] || r.kind}</span>
                  {r.pinned ? <span className="rec-pin">已置顶</span> : null}
                  <span className="rec-title">{r.title || '未命名'}</span>
                  <span className="rec-time">{fmtTime(r.created_at)}</span>
                </div>
                {r.subtitle && <div className="rec-sub">{r.subtitle}</div>}
                {r.note && <div className="rec-note">备注：{r.note}</div>}
              </div>
              <div className="rec-actions">
                <button type="button" className="btn-outline" style={{ padding: '5px 14px', fontSize: 'var(--type-data)' }}
                  onClick={() => onReplay(r.kind, r.payload || {}, r.id)}>
                  回放 ↻
                </button>
                <button type="button" className="btn-outline" style={{ padding: '5px 14px', fontSize: 'var(--type-data)' }}
                  onClick={() => openEdit(r)}>
                  编辑
                </button>
                <button type="button" className="btn-outline" style={{ padding: '5px 14px', fontSize: 'var(--type-data)' }}
                  onClick={() => togglePin(r)}>
                  {r.pinned ? '取消置顶' : '置顶'}
                </button>
                <button type="button" className="btn-outline" style={{ padding: '5px 14px', fontSize: 'var(--type-data)' }}
                  onClick={() => remove(r)}>
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 最近删除 */}
      <div className="bz-head">
        <h2>最近删除</h2>
        <span className="rule" />
        <span className="aside">软删除保留 {days} 天，逾期自动清除</span>
      </div>
      <div className="btn-row" style={{ marginBottom: 10 }}>
        <button type="button" className="btn-outline" style={{ padding: '6px 16px', fontSize: 'var(--type-data)' }}
          aria-expanded={showTrash}
          onClick={() => setShowTrash((v) => !v)}>
          {showTrash ? '收起' : `展开（${trash.length}）`}
        </button>
        {showTrash && trash.length > 0 && (
          <>
            <button type="button" className="btn-outline" style={{ padding: '6px 16px', fontSize: 'var(--type-data)' }}
              onClick={() => restore(trash.map((t) => t.id))}>
              全部恢复
            </button>
            <button type="button" className="btn-outline" style={{ padding: '6px 16px', fontSize: 'var(--type-data)' }}
              onClick={clearTrash}>
              清空最近删除
            </button>
          </>
        )}
      </div>
      {showTrash && (
        trash.length === 0 ? (
          <span className="hint-line">最近删除是空的。</span>
        ) : (
          <div className="rec-list">
            {trash.map((t) => (
              <div className="rec-row trash" key={t.id}>
                <div className="rec-main">
                  <div className="rec-head">
                    <span className={`rec-kind k-${t.kind}`}>{KIND_LABEL[t.kind] || t.kind}</span>
                    <span className="rec-title">{t.title || '未命名'}</span>
                    <span className="rec-time">剩 {t.days_left} 天</span>
                  </div>
                  {t.subtitle && <div className="rec-sub">{t.subtitle}</div>}
                </div>
                <div className="rec-actions">
                  <button type="button" className="btn-outline" style={{ padding: '5px 14px', fontSize: 'var(--type-data)' }}
                    onClick={() => restore([t.id])}>
                    恢复
                  </button>
                  <button type="button" className="btn-outline" style={{ padding: '5px 14px', fontSize: 'var(--type-data)' }}
                    onClick={() => purge(t)}>
                    彻底删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {/* 校验台账（check_log） */}
      <div className="bz-head">
        <h2>校验台账</h2>
        <span className="rule" />
        <span className="aside">每次校验与八字排盘各留一行 · 存在服务器上，关页不丢</span>
      </div>
      <div className="detail-block">
        <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>
          这里记的是<b>当时怎么判的</b>：命卦净档、处方五行、规则与权重版本、
          这次生成了哪几条断言，以及你在结果页标的<b>整案反馈</b>（应验／未验／还没结果）。
          它与上面的「记录」分工不同——记录存的是可回放的那一卦，台账存的是判定过程。
        </div>
        <div className="btn-row" style={{ marginTop: 10 }}>
          <button type="button" className="btn-outline"
            aria-expanded={showLedger}
            disabled={ledgerBusy}
            onClick={() => {
              const next = !showLedger
              setShowLedger(next)
              if (next && ledger.length === 0) void loadLedger()
            }}>
            {ledgerBusy ? '读取中…' : showLedger ? '收起台账' : '展开台账'}
          </button>
          {showLedger && (
            <button type="button" className="btn-outline" disabled={ledgerBusy} onClick={() => void loadLedger()}>
              重新读取
            </button>
          )}
          {showLedger && ledger.length > 0 && (
            <span className="hint-line">共取回 {ledger.length} 行（最新在前，后端上限 200）</span>
          )}
        </div>

        {ledgerErr && <div className="bk-err" role="alert">{ledgerErr}</div>}

        {showLedger && !ledgerErr && ledger.length === 0 && !ledgerBusy && (
          <div className="ledger-empty">
            还没有台账行。做一次命卦校验（梅花/六爻）或在「四柱八字」页排一次盘，这里就会留下可回看的一行。
          </div>
        )}

        {showLedger && ledger.length > 0 && (
          <div className="ledger-list">
            {ledger.map((l) => {
              let nClaims = 0
              try {
                const v = l.claims_json ? JSON.parse(l.claims_json) : []
                nClaims = Array.isArray(v) ? v.length : 0
              } catch { /* 旧行可能不是合法 JSON，按 0 条处理 */ }
              let pillars = ''
              if (l.kind === 'bazi') {
                try { pillars = (JSON.parse(l.extra_json || '{}') as { pillars?: string }).pillars || '' } catch { /* 同上 */ }
              }
              return (
                <div className="ledger-row" key={l.id}>
                  <span className="lg-ts">{String(l.ts || '').slice(0, 16).replace('T', ' ')}</span>
                  <span className={`lg-kind ${l.kind === 'bazi' ? 'lg-kind-bazi' : ''}`}>
                    {l.kind === 'bazi' ? '排盘' : '校验'}
                  </span>
                  <span className="lg-main">
                    {l.kind === 'bazi'
                      ? (pillars || '八字排盘')
                      : (l.question || '（未填所问之事）')}
                  </span>
                  {l.kind !== 'bazi' && <span className="lg-net">净档 {l.net || '—'}</span>}
                  {l.kind !== 'bazi' && l.final_R ? <span className="lg-r">处方 {l.final_R}</span> : null}
                  {nClaims > 0 && <span className="lg-claims">{nClaims} 条断言</span>}
                  <span className="lg-id">#{l.id}</span>
                  {l.kind !== 'bazi' ? (
                    /* D2：行内整案反馈（2026-10 补，与旧前端一致——不用跳到卦的结果页） */
                    <LedgerOutcome l={l} onDone={() => void loadLedger()} />
                  ) : (
                    l.outcome
                      ? <span className="lg-outcome">{l.outcome}</span>
                      : <span className="lg-outcome lg-outcome-none">未标整案</span>
                  )}
                </div>
              )
            })}
          </div>
        )}
        {showLedger && ledger.length > 0 && (
          <div className="d-src">
            整案结果在每行直接标（可附实际发生日期）；逐条断言的应验标记在「反馈」页或卦的结果页。
            台账只是回看，改不动已判定的结果——阈值改动一律需人工批准。
          </div>
        )}
      </div>

      {/* 备份与搬家 */}
      <div className="bz-head">
        <h2>备份与搬家</h2>
        <span className="rule" />
        <span className="aside">加密 JSON · 密码不经过服务器</span>
      </div>
      <div className="detail-block">
        <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>
          <b>数据在哪：</b>存在本站服务器的数据库里，用一个只存在你浏览器里的<b>设备令牌</b>关联——
          没有账号密码。所以<b>清除浏览器数据、换设备、用无痕模式打开，都会失去关联</b>
          （记录仍在服务器上，但认不回你名下）。导出的文件用 AES-GCM 256 加密，
          <b>密码不经过服务器，忘了连站长也解不开</b>；加密强度取决于密码本身：
          4 位数字几秒可破，建议用「生成密码」并存进密码管理器。
        </div>
        {/* 壹 · 导出 */}
        <div className="bk-sec">
          <div className="bk-sec-head">
            <span className="bk-no">壹</span>
            <span className="bk-t">导出备份</span>
            <span className="bk-sub">给这次要生成的文件设一个密码，然后下载</span>
          </div>
          <div className="bk-row">
            <input className="mini-input" type={expShow ? 'text' : 'password'}
              autoComplete="new-password"
              placeholder="给这份备份设一个密码（至少 8 位，建议字母加数字）"
              value={expPass} onChange={(e) => { setExpPass(e.target.value); setCopied(false) }} />
            <button type="button" className="btn-outline" onClick={genPass}>生成密码</button>
            <button type="button" className="btn-outline" onClick={() => setExpShow((v) => !v)}>
              {expShow ? '隐藏' : '显示'}
            </button>
            <button type="button" className="btn-outline" disabled={!expPass} onClick={copyPass}>
              {copied ? '已复制' : '复制密码'}
            </button>
            <button type="button" className="btn" disabled={busyBackup} onClick={doExport}>
              {busyBackup ? '处理中…' : '导出备份'}
            </button>
          </div>
          {expPass && expShow && (
            <div className="bk-plain">
              <span className="bk-plain-tag">当前密码</span>
              <code className="bk-plain-val">{expPass}</code>
              <span className="bk-plain-tip">请现在抄下来或存进密码管理器</span>
            </div>
          )}
          <div className="d-src" style={{ marginTop: 8 }}>
            点「生成密码」会自动填好并显示明文，点「复制密码」可直接粘贴到别处保存。
            密码不会上传、服务器上也不存：<b>忘了它，这份文件就打不开，站长也帮不了你</b>。
            8 位以下不要用——4 位数字几分钟就能被人试出来。
          </div>
        </div>

        {/* 贰 · 导入 */}
        <div className="bk-sec">
          <div className="bk-sec-head">
            <span className="bk-no">贰</span>
            <span className="bk-t">导入备份</span>
            <span className="bk-sub">先选文件，再输入那个文件当初导出时用的密码</span>
          </div>
          <div className="bk-row">
            <button type="button" className="btn-outline" disabled={busyBackup}
              onClick={() => fileRef.current?.click()}>
              选择备份文件…
            </button>
            <span className="bk-file">
              {impFile ? `已选：${impFile.name} · ${fmtSize(impFile.size)}` : '还没有选择文件（备份文件后缀是 .mjson）'}
            </span>
            <input ref={fileRef} type="file" accept=".mjson,.json,application/json" style={{ display: 'none' }}
              onChange={(e) => pickFile(e.target.files?.[0] || null)} />
          </div>

          {impFile && (
            <div className="imp-panel">
              <div className="imp-q">
                请输入 <b>{impFile.name}</b> 当初导出时使用的密码：
              </div>
              <div className="bk-row">
                <input className="mini-input" type={impShow ? 'text' : 'password'} autoComplete="off"
                  placeholder="这个备份文件的加密密码"
                  aria-label="备份文件的加密密码"
                  value={impPass}
                  onChange={(e) => { setImpPass(e.target.value); setImpError('') }}
                  onKeyDown={(e) => { if (e.key === 'Enter') doImport() }} />
                <button type="button" className="btn-outline" onClick={() => setImpShow((v) => !v)}>
                  {impShow ? '隐藏' : '显示'}
                </button>
                <button type="button" className="btn" disabled={busyBackup} onClick={doImport}>
                  {busyBackup ? '导入中…' : '开始导入'}
                </button>
                <button type="button" className="btn-outline" disabled={busyBackup} onClick={cancelImport}>
                  取消
                </button>
              </div>
              {impError && <div className="bk-err">{impError}</div>}
              <div className="d-src" style={{ marginTop: 8 }}>
                密码不对或文件损坏都会停在这一步，改密码再点「开始导入」即可，不用重新选文件。
              </div>
            </div>
          )}
          <div className="d-src" style={{ marginTop: 8 }}>
            导入只搬数据、不搬凭证（拿到别人的备份文件不等于能冒用他的归属）。
          </div>
        </div>
        <div className="d-src">
          备份含：命局档案 + 全部记录（含最近删除）+ 校验台账与断言反馈。
          {persistState ? `　· 存储状态：${persistState}` : ''}
        </div>
        {a2hs && (
          <div className="notice notice-warn" style={{ marginTop: 10 }}>
            <b>建议</b>
            <span className="n-body">
              把本站添加到主屏幕：iPhone 上 Safari 会在 7 天不访问后清空本机存储，
              你的归属令牌与待应验的断言会一起丢失（服务端没有账号可以认回你）。
              点底部「分享」→「添加到主屏幕」即可避免。
              <span style={{ display: 'block', marginTop: 8 }}>
                <button type="button" className="btn-outline" style={{ padding: '5px 14px', fontSize: 'var(--type-data)' }}
                  onClick={() => { dismissAddToHomeScreenHint(); setA2hs(false) }}>
                  我知道了，不再提示
                </button>
              </span>
            </span>
          </div>
        )}
      </div>
      {/* 页脚统计 */}
      <p className="stub-line" style={{ marginTop: 18, textAlign: 'center' }}>
        {rows.length} 条记录 · 最近删除 {trash.length} 条 —— 记录用于回看当时的卦，反馈只是附件（可在「反馈」页逐条标记应验与否）
      </p>

      {/* 编辑弹窗 */}
      {editing && (
        <div className="modal-mask" onClick={() => setEditing(null)}>
          <div ref={editBoxRef} className="modal-box" role="dialog" aria-modal="true"
            aria-labelledby="records-edit-title"
            onClick={(e) => e.stopPropagation()}>
            <div className="modal-title" id="records-edit-title">编辑记录 #{editing.id}</div>
            <label className="reg-label" htmlFor="records-edit-title-input">标题</label>
            <input id="records-edit-title-input" className="input" value={editTitle} maxLength={60}
              onChange={(e) => setEditTitle(e.target.value)} />
            <label className="reg-label" style={{ marginTop: 10 }} htmlFor="records-edit-note">备注（可选）</label>
            <textarea id="records-edit-note" className="textarea" rows={3} maxLength={300} value={editNote}
              placeholder="给这条记录加个说明，比如后来事情怎么发展的"
              onChange={(e) => setEditNote(e.target.value)} />
            <div className="btn-row" style={{ marginTop: 14, justifyContent: 'flex-end' }}>
              <button type="button" className="btn-outline" onClick={() => setEditing(null)}>取消</button>
              <button type="button" className="btn" style={{ padding: '9px 22px', fontSize: 'var(--type-data)' }} onClick={saveEdit}>保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ---------- 台账行内整案反馈（D2，2026-10 补：三按钮 + 实际发生日期） ---------- */

function LedgerOutcome({ l, onDone }: { l: LogRow; onDone: () => void }) {
  const [busy, setBusy] = useState(false)
  const [date, setDate] = useState('')
  const [err, setErr] = useState('')
  const mark = async (o: '应验' | '未验' | '还没结果') => {
    if (busy) return
    setBusy(true); setErr('')
    const ok = await postCaseOutcome(l.id, o, date)
    setBusy(false)
    if (!ok) { setErr('标不上，稍后再试'); return }
    onDone()
  }
  return (
    <span className="lg-outcome-box">
      <span className="lg-o-btns">
        {(['应验', '未验', '还没结果'] as const).map((o) => (
          <button key={o} type="button" className={`lg-o-btn ${l.outcome === o ? 'on' : ''}`}
            disabled={busy} title={l.outcome === o ? '已标这一档' : '点一下标记'} onClick={() => mark(o)}>
            {o}
          </button>
        ))}
      </span>
      <input type="date" className="lg-o-date" value={date} onChange={(e) => setDate(e.target.value)}
        title="实际发生日期（选填；填了才能算应期差几天）" aria-label={`#${l.id} 实际发生日期`} />
      {l.outcome ? <i>{l.outcome}</i> : null}
      {err && <em title={err}>⚠</em>}
    </span>
  )
}
