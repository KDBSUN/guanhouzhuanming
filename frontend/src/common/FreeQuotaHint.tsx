import { useEffect, useState } from 'react'
import { FreeQuota, fetchQuota, getLlmSetting, signinToday } from '../api/llm'
import '../styles/llm.css'

/**
 * 起卦页上的「AI 解卦要花什么」提示条（白金版）
 * ============================================================
 * 为什么必须有它：额度机制上线后，页面上一个字的说明都没有——用户点「AI 解卦」，
 * 要么被拦下（才知道要签到），要么已经在悄悄用站长付钱的额度。两者都不该靠撞墙才知道。
 *
 * 三种状态各说一句话，不讲第二件事：
 *   · 已填自己的 key   → 用你自己的额度，不限次数
 *   · 已签到、还有次数 → 今天还剩 N 次免费（不累加）
 *   · 还没签到         → 签到后可用 N 次免费（就地给签到按钮，不让用户自己找）
 */
export default function FreeQuotaHint() {
  const [quota, setQuota] = useState<FreeQuota | null>(null)
  const [busy, setBusy] = useState(false)
  const [mine, setMine] = useState(false)

  useEffect(() => {
    setMine(!!getLlmSetting())
    fetchQuota().then(setQuota)
  }, [])

  if (mine) {
    return (
      <div className="llm-hint">
        AI 解卦用<b>你自己填的模型 key</b>，不限次数（花的是你在模型厂商那边的额度）。
      </div>
    )
  }
  if (!quota) return null

  if (quota.signed) {
    return (
      <div className="llm-hint">
        今天还剩 <b>{quota.free_left}</b> 次免费 AI 解卦（每天 {quota.free_limit} 次，明天 0 点重置，
        剩余次数不带过去）。想不限次数，可在「API 设置」填自己的模型 key。
      </div>
    )
  }
  return (
    <div className="llm-hint">
      AI 解卦要调用大模型。<b>签到后今天可免费用 {quota.free_limit} 次</b>
      （按天算、不累加）；也可以填自己的模型 key，之后不限次数。
      <button type="button" className="llm-hint-btn" disabled={busy}
              onClick={async () => {
                setBusy(true)
                const st = await signinToday()
                setBusy(false)
                if (st) setQuota(st)
              }}>
        {busy ? '签到中…' : '现在签到'}
      </button>
    </div>
  )
}
