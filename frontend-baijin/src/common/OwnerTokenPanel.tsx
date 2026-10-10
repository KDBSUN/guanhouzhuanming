import { useState } from 'react'
import { getOwnerToken, setOwnerToken } from '../api/owner'

/**
 * 数据身份（归属令牌）面板 —— 放在页脚，收起状态，需要时才展开。
 *
 * 为什么要给用户看这个东西：
 *  1. 本站不注册账号，"账户"就是浏览器里的一枚随机令牌。记录、命局档案都挂在它下面。
 *  2. 令牌即凭证：换了令牌就等于换了一个人，看到的数据完全不同；令牌丢了数据就找不回。
 *  3. 端口不同（旧前端 3000 / 新前端 3001）属于不同的"源"，浏览器各存一枚令牌，
 *     所以两边数据默认不通。把旧前端的令牌粘过来，就能在新前端看到原来的记录与档案。
 */
export default function OwnerTokenPanel() {
  const [token] = useState(getOwnerToken())
  const [input, setInput] = useState('')
  const [showFull, setShowFull] = useState(false)
  const [msg, setMsg] = useState('')

  const masked = token.length > 12 ? `${token.slice(0, 8)}……${token.slice(-4)}` : token

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(token)
      setMsg('已复制到剪贴板。把它保存好：这枚令牌丢了，数据就找不回来。')
    } catch {
      setMsg('浏览器不允许自动复制，请手动选中下面的令牌复制。')
    }
  }

  const apply = () => {
    const v = input.trim()
    if (!v) { setMsg('请先粘贴一枚令牌。'); return }
    if (v === token) { setMsg('这就是当前令牌，不用换。'); return }
    if (!setOwnerToken(v)) { setMsg('写入失败：浏览器可能禁用了本地存储（无痕模式）。'); return }
    setMsg('已改用新令牌，正在按新身份重新读取数据…')
    window.setTimeout(() => window.location.reload(), 600)
  }

  return (
    <details className="token-panel">
      <summary>数据身份（归属令牌）</summary>
      <div className="token-body">
        <p className="token-text">
          本站不注册账号。浏览器本地存着一枚随机令牌，它就相当于你的"账户"——
          记录、命局档案都挂在这枚令牌下面。令牌即凭证：<b>换了令牌就等于换了个人</b>，
          看到的记录完全不同；令牌丢了，数据也就找不回来了。
        </p>
        <p className="token-text">
          注意：浏览器按"网址 + 端口"隔离本地存储。旧前端跑在 3000 端口、新版跑在 3001 端口，
          属于两个不同的源，各存了一枚令牌，所以默认互相看不到对方的记录与命局档案。
          若要把旧前端的数据接过来，在旧前端打开同一面板复制令牌，粘到下面即可。
        </p>
        <div className="token-row">
          <span className="reg-label" style={{ margin: 0 }}>当前令牌</span>
          <code className="token-code">{showFull ? token : masked}</code>
          <button type="button" className="btn-outline" style={{ padding: '5px 14px' }}
            onClick={() => setShowFull((v) => !v)}>
            {showFull ? '隐藏' : '显示全部'}
          </button>
          <button type="button" className="btn-outline" style={{ padding: '5px 14px' }} onClick={copy}>
            复制
          </button>
        </div>
        <div className="token-row">
          <input
            className="mini-input" style={{ flex: 1, minWidth: 240 }}
            placeholder="粘贴另一枚令牌（例如旧前端里复制出来的那枚）"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button type="button" className="btn" style={{ padding: '8px 20px' }} onClick={apply}>
            改用这枚令牌
          </button>
        </div>
        {msg && <p className="token-msg">{msg}</p>}
      </div>
    </details>
  )
}
