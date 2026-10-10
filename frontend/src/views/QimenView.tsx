import { useState } from 'react'
import { FishTail } from '../art/book'
import { friendlyError } from '../api/client'
import { qimen, type QimenPan, type QimenResult } from '../api/qimen'

/* ============================================================
   奇门遁甲起局 —— 时家·数理奇门（白金银设计系统）
   定局＝拆补法（站长裁定）；转盘为主、飞盘并收；起局不含断法。
   盘面数据由后端 /api/qimen 出（backend/qimen.py，书证见判据总表第五节）。
   与梅花/六爻/八字同款版式：leaf-head 卷首 + register 表单 + sys-zone 分区壳。
   ============================================================ */

const LUOSHU: number[][] = [[4, 9, 2], [3, 5, 7], [8, 1, 6]]

function nowLocal(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

export default function QimenView() {
  const [dt, setDt] = useState(nowLocal())
  const [panSel, setPanSel] = useState<'转盘' | '飞盘'>('转盘')
  const [data, setData] = useState<QimenResult | null>(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  const run = async () => {
    setLoading(true); setErr('')
    try {
      setData(await qimen(dt, 'both'))
    } catch (e) {
      setErr(friendlyError(e))
    } finally {
      setLoading(false)
    }
  }

  const pan: QimenPan | undefined = data?.[panSel]
  const cells = pan ? Object.fromEntries(Object.values(pan.九宫).map((c) => [c.宫, c])) : {}

  return (
    <div>
      <div className="leaf-head">
        <span className="juan-mark">易占</span>
        <FishTail />
        <span className="juan">奇门遁甲</span>
        <span className="folio">卷七</span>
      </div>
      <div className="juan-title">
        <h1>奇门起局</h1>
        <p className="juan-sub">时家奇门 · 数理奇门：拆补法定局，转盘为主、飞盘并收 · 起局不含断法</p>
      </div>

      {/* ---------- 起局表单 ---------- */}
      <div className="register">
        <span className="reg-label">起局时刻</span>
        <div className="param-row">
          <input
            className="mini-input"
            style={{ gridColumn: '1 / -1' }}
            type="datetime-local"
            aria-label="起局时刻"
            value={dt}
            onChange={(e) => { setDt(e.target.value); setErr('') }}
          />
        </div>
        <span className="reg-hint">
          默认取当前时间（正时）。定局＝拆补法（站长裁定）；转盘为主、飞盘并收；起局不含断法，规则逐条见判据总表第五节。
        </span>
        <div className="btn-row" style={{ marginTop: 16 }}>
          <button type="button" className="btn" disabled={loading || !dt} onClick={run}>
            {loading ? '起局中…' : '起 局'}
          </button>
        </div>
        {err && <div className="notice notice-err" role="alert"><b>错误</b><span className="n-body">{err}</span></div>}
      </div>

      {data && (
        <div className="sys-zone">
          <div className="sys-zone-head">
            <span className="sys-zone-title">起局盘面</span>
            <span className="sys-zone-sub">九宫自上而下：神 · 天盘干 · 九星 · 八门 · 地盘干</span>
          </div>

          {/* 定局 */}
          <div className="bz-head" style={{ marginTop: 14 }}>
            <h2>定局</h2>
            <span className="rule" />
            <span className="demo-badge">
              {data.定局.节气} · {data.定局.阴阳遁} · {data.定局.元} · {data.定局.局数}局
            </span>
          </div>
          <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>
            日 <b>{data.定局.日干支}</b> · 时 <b>{data.定局.时干支}</b> · 符头 <b>{data.定局.符头}</b>
            　<span className="d-src">{data.定局.定局法}</span>
          </div>
          <div className="d-src">
            交节 {data.定局.交节时刻} 起 · 下一节气 {data.定局.下一节气}（{data.定局.下一交节时刻}）
          </div>

          {/* 盘式切换 */}
          <div className="bz-head" style={{ marginTop: 18 }}>
            <h2>盘式</h2>
            <span className="rule" />
            <span className="aside">转盘为主、飞盘并收</span>
          </div>
          <div className="slip-row" role="tablist" aria-label="盘式">
            {(['转盘', '飞盘'] as const).map((k) => (
              <button
                key={k}
                type="button"
                className={`slip ${panSel === k ? 'active' : ''}`}
                role="tab"
                id={`pan-tab-${k}`}
                aria-selected={panSel === k}
                aria-controls="pan-panel"
                disabled={!data[k]}
                onClick={() => setPanSel(k)}
              >
                {k}
              </button>
            ))}
          </div>

          <div role="tabpanel" id="pan-panel" aria-labelledby={`pan-tab-${panSel}`}>
            {pan ? <PanBoard p={pan} cells={cells} /> : <div className="d-src">该盘式未返回。</div>}
          </div>

          {/* 择时择方 */}
          {pan?.择时择方 && (
            <>
              <div className="bz-head" style={{ marginTop: 18 }}>
                <h2>择时择方</h2>
                <span className="rule" />
                <span className="aside">运筹建议 · {pan.择时择方.择时.判}</span>
              </div>
              <div className="qm-zz-grid">
                {Object.values(pan.择时择方.择方).map((f) => (
                  <div
                    key={f.宫}
                    className={`qm-zz-item${f.建议 === '宜往' ? ' good' : f.建议 === '宜避' ? ' bad' : ''}`}
                  >
                    <b>{f.方位}</b>·{f.门}·{f.建议}
                    <span className="sr-only">
                      {`${f.宫}宫·${f.方位}·${f.门}（${f.门吉凶}）·趋避：${f.趋避门宫}·日干：${f.日干生克}`
                        + `${f.吉格.length ? '·吉格：' + f.吉格.join('、') : ''}`
                        + `${f.凶格.length ? '·凶格：' + f.凶格.join('、') : ''}｜${f.理由}`}
                    </span>
                  </div>
                ))}
              </div>
              <div className="d-src" style={{ marginTop: 8 }}>{pan.择时择方.书证}</div>
            </>
          )}

          <div className="d-src" style={{ marginTop: 10 }}>
            每宫自上而下：神 · 天盘干（星所带之地盘干）· 九星 · 八门/九门 · 地盘干。
            {panSel === '转盘'
              ? '转盘：中五无星门神，天禽随天芮同宫（寄坤二）。'
              : '飞盘：中五有星有神、无门；八门不入中五，值使落中五则寄宫。'}
            {data.书证 || ''}
          </div>
        </div>
      )}
    </div>
  )
}

/* ---------- 盘面（洛书九宫 3×3） ---------- */

function PanBoard({ p, cells }: { p: QimenPan; cells: Record<number, QimenPan['九宫'][string]> }) {
  const ge = p.格局
  const gejuOf = (pal: number) => ge?.九宫?.[String(pal)] ?? []
  const mengongOf = (pal: number) => ge?.门宫?.[String(pal)]
  return (
    <div className="qm-pan" style={{ marginTop: 12 }}>
      <div className="qm-pan-head">
        值符 <b>{p.值符}</b> · 值使 <b>{p.值使}</b> · 旬首 <b>{p.旬首}</b>
        <span className="qm-tag">{p.阴阳遁}{p.局数}局</span>
      </div>
      {ge && ge.盘级.length > 0 && (
        <div className="qm-panji">
          {ge.盘级.map((x, i) => (
            <span key={i} className={`qm-badge ${x.吉凶 === '吉' ? 'good' : 'bad'}`} title={x.判语}>
              {x.格}
            </span>
          ))}
        </div>
      )}
      <div className="qm-grid">
        {LUOSHU.map((row, i) => (
          <div key={i} className="qm-row">
            {row.map((pal) => {
              const c = cells[pal]
              if (!c) return <div key={pal} className="qm-cell qm-cell-empty" />
              const gj = gejuOf(pal)
              const mg = mengongOf(pal)
              const shown = gj.slice(0, 2)
              if (pal === 5) {
                const hasContent = c.星.length > 0 || !!c.神
                return (
                  <div key={pal} className="qm-cell qm-cell-mid">
                    {hasContent ? (
                      <>
                        {c.神 && <div className="qm-shen">{c.神}</div>}
                        {c.天盘.length > 0 && <div className="qm-tian">{c.天盘.join('')}</div>}
                        {c.星.length > 0 && <div className="qm-star">{c.星.join('·')}</div>}
                        <div className="qm-di">{c.地盘}</div>
                      </>
                    ) : (
                      <>
                        <div className="qm-di">{c.地盘}</div>
                        <div className="qm-mid-note">中宫无星门神，天禽随天芮（寄坤二）</div>
                      </>
                    )}
                  </div>
                )
              }
              return (
                <div key={pal} className="qm-cell">
                  <div className="qm-shen">{c.神}</div>
                  <div className="qm-tian">{c.天盘.join('')}</div>
                  <div className="qm-star">{c.星.join('·')}</div>
                  <div className="qm-men">{c.门}</div>
                  <div className="qm-di">{c.地盘}</div>
                  {mg && (
                    <div
                      className="qm-mg"
                      title={mg.门卦 ? `${mg.判语}｜${mg.门卦}：${mg.门卦断}` : mg.判语}
                    >
                      {mg.主客}{mg.门卦 ? `·${mg.门卦}` : ''}
                    </div>
                  )}
                  {shown.map((x, k) => (
                    <div
                      key={k}
                      className={`qm-geju ${x.吉凶 === '吉' ? 'good' : 'bad'}`}
                      title={x.判语}
                    >
                      {x.格}{gj.length > 2 && k === 1 ? ` +${gj.length - 2}` : ''}
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
