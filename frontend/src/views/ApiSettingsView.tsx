import { useCallback, useEffect, useState } from 'react'
import {
  FreeQuota, LlmProvider, LlmSetting, fetchProviders, fetchQuota, fetchSiteKey,
  getLlmSetting, maskKey, saveLlmSetting, signinToday, testLlm,
} from '../api/llm'
import '../styles/llm.css'

/**
 * API 设置页（白金版）：自带模型 key + 每日免费额度
 * ============================================================
 * 与旧前端同一后端、同一规则（细节见 backend/docs/模型接口与免费额度.md），这里只讲三件事：
 *   ① key 存在你自己的浏览器里，本站服务器不保存、不写日志，只在解卦那一次请求里转交；
 *   ② 地址由本站固定（防"本站服务器被当成任意地址的转发器"），只能选厂商、改模型名；
 *   ③ 免费额度按天算、不累加——昨天的次数不会留到今天。
 *
 * 2026-10-08 追加（站长要求）：**保存后本页不再回显完整 key**。
 *   · 载入时只回填厂商与模型名，key 一律留空（此前回填进输入框，随手就能选中复制）；
 *   · 已保存时只显示打码末四位（该行 user-select:none，连打码也不许复制）；
 *   · 想换 key 直接把新 key 粘进输入框再保存（覆盖旧的）。
 *   **诚实边界**：key 仍在 localStorage 里（每次解卦都要把它发给服务端），
 *   本页能做到的是"不再显示、不再可复制"，不是"这台设备上取不出来"（开发者工具仍看得到）。
 *
 * 另有站长专用入口：带 `X-Admin-Token` 从后端取回**本站 .env 那把 key** 一键导入，
 * 免得站长为了自测把 key 手工复制粘贴（最容易落进剪贴板的一步）。
 */
export default function ApiSettingsView() {
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [freePerDay, setFreePerDay] = useState(3)
  const [quota, setQuota] = useState<FreeQuota | null>(null)
  const [sel, setSel] = useState('')
  const [key, setKey] = useState('')
  const [model, setModel] = useState('')
  const [msg, setMsg] = useState<{ ok?: boolean; text: string } | null>(null)
  const [testing, setTesting] = useState(false)
  const [saved, setSaved] = useState<LlmSetting | null>(null)
  const [adminTok, setAdminTok] = useState('')
  const [importing, setImporting] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)
  const [quotaFailed, setQuotaFailed] = useState(false)
  const [signing, setSigning] = useState(false)

  const loadMeta = useCallback(() => {
    fetchProviders().then((d) => {
      if (!d) return
      setProviders(d.providers)
      setFreePerDay(d.free_per_day)
      const rec = d.providers.find((p) => p.recommended) || d.providers[0]
      if (rec) { setSel(rec.id); setModel(rec.default_model) }
    }).catch(() => setLoadFailed(true))
    fetchQuota().then(setQuota).catch(() => setQuotaFailed(true))
  }, [])

  useEffect(() => {
    setLoadFailed(false); setQuotaFailed(false)
    loadMeta()
    const cur = getLlmSetting()
    // **刻意不 setKey(cur.api_key)**：见文件头，保存后本页不再回显完整 key
    if (cur) { setSaved(cur); setSel(cur.provider); setModel(cur.model) }
  }, [loadMeta])

  const cur = providers.find((p) => p.id === sel)

  const onPick = (id: string) => {
    setSel(id)
    const p = providers.find((x) => x.id === id)
    if (p) setModel(p.default_model)
    setMsg(null)
  }

  const onSave = () => {
    if (!sel || !key.trim()) { setMsg({ text: '请先选择厂商并填写 API key' }); return }
    const s: LlmSetting = { provider: sel, api_key: key.trim(), model: model.trim() }
    saveLlmSetting(s)
    setSaved(s)
    setKey('')       // 立即从表单/内存里清掉明文，转由下方打码行显示
    setMsg({ ok: true, text: '已保存到这台设备的浏览器里。解卦时将用你自己的 key，不限次数；本页不再显示完整 key。' })
  }

  const onClear = () => {
    saveLlmSetting(null)
    setSaved(null)
    setKey('')
    setMsg({ text: `已清除。此后走每日免费额度（签到后每天 ${freePerDay} 次，不累加）。` })
  }

  const onTest = async () => {
    if (testing) return
    // 输入框空但已保存时，用**已存的那把**测（这样不必为了测试把 key 再显示出来）
    const k = key.trim() || (saved?.api_key || '')
    if (!sel || !k) { setMsg({ text: '请先选择厂商并填写 API key' }); return }
    setTesting(true)
    setMsg({ text: '正在用你的 key 发一句最小请求…' })
    const r = await testLlm({ provider: sel, api_key: k, model: model.trim() })
    setTesting(false)
    setMsg({ ok: r.ok, text: r.message })
  }

  const onImportSiteKey = async () => {
    if (!adminTok.trim()) { setMsg({ text: '请先填站长令牌（后端 backend/.env 里的 ADMIN_TOKEN）' }); return }
    setImporting(true)
    setMsg({ text: '正在取回站点 key…' })
    const r = await fetchSiteKey(adminTok)
    setImporting(false)
    if (!r.ok) { setMsg({ ok: false, text: r.message }); return }
    setSel(r.provider || '')
    setKey(r.api_key || '')
    setModel(r.model || '')
    setMsg({ ok: true, text: `已取回站点 key（${r.label || r.provider || ''}）。点「保存」写入本机浏览器后即生效；保存后本页不再显示完整 key。` })
  }

  const onSignin = async () => {
    if (signing) return
    setSigning(true)
    try {
      const st = await signinToday()
      if (st) {
        setQuota(st)
        setMsg({ ok: true, text: `签到成功：今天可用 ${st.free_limit} 次免费 AI 解卦（明天不累加）。` })
      } else setMsg({ text: '签到失败，请稍后重试' })
    } catch {
      setMsg({ text: '签到失败，请稍后重试' })
    } finally {
      setSigning(false)
    }
  }

  return (
    <div className="llm-page">
      <p className="llm-intro">
        排盘、卦象、体用、处方五行、应期日期<b>全部由代码算定、不花钱</b>；只有「AI 解卦」那一段
        白话要调用大模型。你可以填自己的模型 key，用自己的额度、不限次数；不填也行——
        <b>每天签到后可用 {freePerDay} 次免费</b>（按天算，不累加到明天）。
      </p>

      {/* 免费额度 */}
      <section className="card llm-sec">
        <h2 className="llm-h2">今日免费额度</h2>
        <div className="llm-quota">
          {quota ? (
            <span className="llm-quota-line">
              今天已用 <b>{quota.free_used}</b> / {quota.free_limit} 次{quota.signed ? '' : '（还没签到）'}
            </span>
          ) : quotaFailed ? (
            <span className="llm-quota-line">
              今日额度读取失败
              <button type="button" className="btn-outline" style={{ marginLeft: 8 }} onClick={loadMeta}>重试</button>
            </span>
          ) : <span className="llm-sub">正在读取…</span>}
          <button type="button" className="btn" onClick={onSignin} disabled={!!quota?.signed || signing}>
            {quota?.signed ? '今天已签到' : signing ? '签到中…' : '签到（领今天的免费次数）'}
          </button>
        </div>
        <div className="llm-sub">
          {quota?.signed
            ? `还剩 ${quota.free_left} 次；明天 0 点（北京时间）重置，剩余次数不带过去。`
            : '签到后今天才有免费次数；签到一次即可，重复点不会多给。'}
        </div>
        {saved && (
          <div className="llm-sub">
            你已配置自己的 key（{providers.find((p) => p.id === saved.provider)?.label || saved.provider}），
            解卦走你自己的额度，<b>不占</b>上面这几次免费。
          </div>
        )}
      </section>

      {/* 自带 key */}
      <section className="card llm-sec">
        <h2 className="llm-h2">用自己的模型 key</h2>

        <div className="llm-field">
          <span className="llm-label">模型厂商</span>
          <div className="llm-providers">
            {providers.map((p) => (
              <button key={p.id} type="button"
                      className={`llm-prov ${sel === p.id ? 'on' : ''}`}
                      aria-pressed={sel === p.id}
                      onClick={() => onPick(p.id)}>
                {p.label}
                {p.recommended && <em className="llm-rec">推荐</em>}
                {p.note && <span className="llm-prov-note">{p.note}</span>}
              </button>
            ))}
          </div>
          {loadFailed && (
            <div className="llm-sub" style={{ marginTop: 8 }}>
              厂商列表读取失败
              <button type="button" className="btn-outline" style={{ marginLeft: 8 }} onClick={loadMeta}>重试</button>
            </div>
          )}
        </div>

        <label className="llm-field">
          <span className="llm-label">API key（只存在你自己的浏览器里）</span>
          <input className="input" type="password" value={key} autoComplete="off"
                 placeholder={saved ? '已保存（见下方打码）——粘贴新 key 可覆盖旧的'
                                    : (cur ? `到 ${cur.label} 控制台申请后粘贴到这里` : '先选择厂商')}
                 onChange={(e) => setKey(e.target.value)} />
          {cur?.key_url && (
            <em className="llm-sub">
              申请入口：<a href={cur.key_url} target="_blank" rel="noreferrer">{cur.key_url}</a>
            </em>
          )}
        </label>

        {/* 保存后只显示打码末四位：完整 key 不再进 DOM，也就无从选中复制（见文件头说明） */}
        {saved && (
          <div className="llm-keymask">
            已保存：<code>{maskKey(saved.api_key)}</code>
            <em>本页不再显示完整 key、也不能从本页复制；要更换就直接把新 key 粘进上面输入框再保存。</em>
          </div>
        )}

        {/* 站长专用：一键取回本站 .env 那把 key。需 X-Admin-Token；
            后端未配置 ADMIN_TOKEN 时该端点 503 关闭（配置缺失＝用不了，而不是谁都能拿）。 */}
        <details className="llm-admin">
          <summary>站长入口：导入本站的 key（需站长令牌）</summary>
          <div className="llm-admin-row">
            <input className="input" type="password" value={adminTok} autoComplete="off"
                   aria-label="站长令牌 (ADMIN_TOKEN)"
                   placeholder="backend/.env 里的 ADMIN_TOKEN"
                   onChange={(e) => setAdminTok(e.target.value)} />
            <button type="button" className="btn-outline" onClick={onImportSiteKey} disabled={importing}>
              {importing ? '取回中…' : '导入站点 key'}
            </button>
          </div>
          <em className="llm-sub">
            取回的是本站 <code>backend/.env</code> 里那把 key，用于站长自测
            （免费路径每天只有 {freePerDay} 次，反复检验会被卡住）。令牌只随这一次请求发出，不保存。
          </em>
        </details>

        <label className="llm-field">
          <span className="llm-label">模型名（可改，留空用默认）</span>
          <input className="input" value={model} list="llm-models" onChange={(e) => setModel(e.target.value)} />
          <datalist id="llm-models">
            {(cur?.models || []).map((m) => <option key={m} value={m} />)}
          </datalist>
          {cur && <em className="llm-sub">该厂商常用：{cur.models.join('、')}（模型名与你的账号开通状态有关）</em>}
        </label>

        <div className="btn-row">
          <button type="button" className="btn" onClick={onSave}>保存</button>
          <button type="button" className="btn-outline" onClick={onTest} disabled={testing}>
            {testing ? '测试中…' : '测试连接'}
          </button>
          <button type="button" className="btn-outline" onClick={onClear} disabled={!saved}>
            清除
          </button>
        </div>
        {msg && (
          <div className={`notice ${msg.ok === true ? 'notice-ok' : msg.ok === false ? 'notice-err' : 'notice-warn'}`}
               role="status">
            <span className="n-body">{msg.text}</span>
          </div>
        )}
      </section>

      {/* 三件必须说清的事 */}
      <section className="card llm-sec llm-notes">
        <h2 className="llm-h2">关于你的 key 与额度</h2>
        <ul>
          <li><b>key 存在哪里</b>：只存在你这台设备的浏览器（localStorage）。本站服务器不保存、不写日志；
            解卦时它随那一次请求转交给服务端，服务端只在本次请求的内存里用它调用上游，用完即弃。
            <b>保存后本页不再显示完整 key</b>（只留末四位供辨认）；但要说明白：key 仍在浏览器存储里
            ——每次解卦都得把它发出去——所以这一步防的是"屏幕上被看到、被顺手复制"，
            不是"这台设备上取不出来"（开发者工具仍看得到）。</li>
          <li><b>为什么不能自己填接口地址</b>：若地址可以由客户端指定，本站服务器就变成了任意地址的转发器
            （可以被打内网、被别人当代理用）。所以地址由本站固定，你只能选厂商、改模型名。</li>
          <li><b>额度怎么算</b>：用自己的 key = 不限次数，花的是你在模型厂商那边的钱；
            不填 key = 每天签到后 {freePerDay} 次，<b>按天算、不累加</b>，剩余次数不会留到第二天。</li>
          <li><b>各家的限制以厂商为准</b>：速率限制、计费、内容政策都由模型厂商决定，本站不代为承诺；
            例如阿里云百炼的 key 是按地域绑定的，用错地域会请求失败。</li>
        </ul>
      </section>
    </div>
  )
}
