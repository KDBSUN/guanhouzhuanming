import { profileSummary, type MingjuProfile } from '../api/mingju'

/**
 * 命局档案一行摘要（三页共用）。
 * 为什么单独抽出来：喜用/忌神藏在 baseline.mingju 下面，
 * 各页各写一遍就会各错一遍（实测就出现过"喜用  · 忌 "空白的情况）。
 */
export default function ProfileLine({ profile }: { profile: MingjuProfile | null }) {
  if (!profile) {
    return (
      <span className="stub-mark">
        还没有命局档案 —— 去「四柱八字」排盘并存档；命卦校验与逐日宜忌表都要先有档案
      </span>
    )
  }
  const s = profileSummary(profile)
  return (
    <span className="hint-line">
      已立命局档案：{s.solar || '（时间未记录）'}
      {s.gender ? ` · ${s.gender}` : ''}
      {s.dayMaster ? ` · 日主${s.dayMaster}${s.dayMasterWx ? `（${s.dayMasterWx}）` : ''}` : ''}
      {s.geju ? ` · ${s.geju}` : ''}
      {s.tier ? ` · 强弱${s.tier}` : ''}
      {' · '}喜用 {(s.F || []).join('') || '—'} · 忌 {(s.J || []).join('') || '—'}
      {s.tiao ? ` · 调候 ${s.tiao}` : ''}
    </span>
  )
}
