import { useState } from 'react'
import { analyzeWaijing, type WaijingResult } from '../api/waijing'
import { friendlyError } from '../api/client'
import QuoteRef from './QuoteRef'
import type { MeihuaGuaData } from '../api/types'

/**
 * 外应参断（刻应）
 * 起卦之后新出现的闻见（看到、听到、遇到的事）作为"外卦"，与体用互变（内卦）合断。
 * 三件事必须显示清楚：配了哪一卦及凭什么、与体卦什么关系、配不到时如实说并给候选。
 * 原卦照旧：不重起、不动体用、不改互变、不换动爻。
 */
export default function WaijingBlock({
  gua, innerNet, onAskAi,
}: {
  gua: MeihuaGuaData
  /** 内卦净档（顺/平/逆），来自命卦校验；没有就留空 */
  innerNet?: string
  /** 让 AI 接着讲这条外应（交给追问流，不重新起卦） */
  onAskAi: (omen: string[], chosen: Record<string, string>) => void
}) {
  const [omen, setOmen] = useState('')
  const [direction, setDirection] = useState('')
  const [motion, setMotion] = useState('')
  const [res, setRes] = useState<WaijingResult | null>(null)
  const [chosen, setChosen] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const run = async (extraChosen: Record<string, string> = chosen) => {
    const text = omen.trim()
    if (!text) { setErr('先写下你看到、听到或遇到的那件事'); return }
    setBusy(true); setErr('')
    try {
      const r = await analyzeWaijing({
        omen: [text],
        guaData: gua,
        innerNet: innerNet || '',
        direction, motion,
        chosen: extraChosen,
      })
      setRes(r)
      setChosen(extraChosen)
    } catch (e) {
      setErr(friendlyError(e))
    } finally {
      setBusy(false)
    }
  }

  const choose = (omenText: string, g: string) => {
    const next = { ...chosen, [omenText]: g }
    setChosen(next)
    void run(next)
  }

  return (
    <div className="detail-block">
      <div className="d-title">外 应 参 断（刻 应）</div>
      <div className="d-src">遇吉则吉，遇凶则凶。外应是用来辅助判断吉凶和佐证卦象的，自行选取。</div>

      <textarea className="textarea" rows={2} maxLength={120} style={{ marginTop: 10 }}
        placeholder="例：看到一只喜鹊落在窗台上 / 听到外面有人敲锣 / 路上遇到出殡"
        value={omen} onChange={(e) => setOmen(e.target.value)} />

      <div className="btn-row" style={{ marginTop: 10 }}>
        <div className="slip-row">
          {['', '来', '去'].map((d) => (
            <button key={d || 'none'} type="button" className={`slip ${direction === d ? 'active' : ''}`}
              onClick={() => setDirection(d)}>{d === '' ? '来去不明' : `方${d}`}</button>
          ))}
        </div>
        <div className="slip-row">
          {['', '动', '不动'].map((m) => (
            <button key={m || 'none'} type="button" className={`slip ${motion === m ? 'active' : ''}`}
              onClick={() => setMotion(m)}>{m === '' ? '动静不明' : m}</button>
          ))}
        </div>
        <button type="button" className="btn-outline" disabled={busy} onClick={() => run()}>
          {busy ? '参断中…' : '参 断'}
        </button>
      </div>
      <span className="reg-hint">
        「方来」主事将至、力强；「已去」主事已过、力弱；「动而应」吉凶皆速；说不清就选"不明"，不臆断。
      </span>

      {err && <div className="notice notice-err"><b>错误</b><span className="n-body">{err}</span></div>}

      {res && (
        <div style={{ marginTop: 12 }}>
          {res.items.map((it) => (
            <div className="wj-item" key={it.omen}>
              <div className="wj-omen">「{it.omen}」</div>
              {it.adjudication ? (
                <>
                  <div className={`wj-verdict pol-${it.adjudication.polarity}`}>
                    {it.adjudication.relation} → <b>{it.adjudication.effect}</b>
                  </div>
                  <div className="wj-meta">
                    配卦 {it.adjudication.gua}（{it.adjudication.wuxing}）·
                    依据 {it.resolve.candidates[0]?.by}
                    {it.resolve.candidates[0]?.term ? `「${it.resolve.candidates[0].term}」` : ''}
                    {it.resolve.extrapolated ? '（类推）' : ''}
                  </div>
                  <div className="wj-src">
                    <QuoteRef k={it.adjudication.src} label="书证" />
                  </div>
                  {it.modulation?.notes?.length ? (
                    <div className="wj-mod">{it.modulation.notes.join(' ')}</div>
                  ) : null}
                  {it.moves_gua ? (
                    <div className="notice notice-warn" style={{ marginTop: 8 }}>
                      <b>注意</b>
                      <span className="n-body">{it.moves_gua_say || '此应可能动摇原断，请细看理由。'}</span>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="wj-choice">
                  未能定卦：{it.resolve.note || '没有匹配到明确的卦象条目'}
                  {it.resolve.candidates?.length ? (
                    <>
                      <div className="reg-hint">请从候选里挑一个（或重新描述得更具体）：</div>
                      <div className="slip-row">
                        {it.resolve.candidates.map((c) => (
                          <button key={c.gua + c.by} type="button" className="slip"
                            title={c.src}
                            onClick={() => choose(it.omen, c.gua)}>
                            {c.gua}（{c.by}{c.term ? `·${c.term}` : ''}{c.extrapolated ? '·类推' : ''}）
                          </button>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="reg-hint">换个更具体的说法（例如把"一个东西"写成"一只黑猫从左边走过"）再试。</div>
                  )}
                </div>
              )}
            </div>
          ))}

          {res.combined?.say && (
            <div className="notice notice-ok" style={{ marginTop: 10 }}>
              <b>内外合断</b>
              <span className="n-body">
                {res.combined.say}
                {res.combined.src ? <>　<QuoteRef k={res.combined.src} label="出处" /></> : null}
              </span>
            </div>
          )}
          {res.primary?.basis && <div className="d-src">多应并存时以「{res.primary.basis}」为主应。</div>}
          <div className="d-src">{res.version_note}</div>

          <div className="btn-row" style={{ marginTop: 10 }}>
            <button type="button" className="btn-outline"
              onClick={() => onAskAi([res.items[0]?.omen || omen.trim()], chosen)}>
              让 AI 就这条外应细讲（扣一次额度）
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
