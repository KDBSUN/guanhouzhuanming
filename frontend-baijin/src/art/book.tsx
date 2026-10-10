/* ============================================================
   书册构件（自线装本移植）：墨迹滤镜 / 鱼尾 / 墨笔卦爻 / 钤印 /
   铜钱 / 书脊
   ============================================================ */
import type { ReactNode } from 'react'

/** 墨迹粗糙滤镜（全局一次） */
export function InkDefs() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden>
      <defs>
        <filter id="ink-rough" x="-8%" y="-40%" width="116%" height="180%">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="2.2" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
    </svg>
  )
}

/** 鱼尾（中缝折标） */
export function FishTail({ size = 18 }: { size?: number }) {
  return (
    <svg className="fishtail" width={size} height={size} viewBox="0 0 20 20" fill="currentColor" aria-hidden>
      <path d="M10 2 C 5 6, 5 9, 2 12 L 10 9 Z" />
      <path d="M10 2 C 15 6, 15 9, 18 12 L 10 9 Z" />
      <path d="M10 18 C 5 14, 5 11, 2 8 L 10 11 Z" opacity="0.55" />
      <path d="M10 18 C 15 14, 15 11, 18 8 L 10 11 Z" opacity="0.55" />
    </svg>
  )
}

/* ---------- 墨笔卦爻 ---------- */

export function BrushYao({ yang, gold, delay = 0, wx }: { yang: boolean; gold?: boolean; delay?: number; wx?: string }) {
  const wxc = !gold && wx && '金木水火土'.includes(wx) ? `wxc-${wx}` : ''
  return (
    <div className={`brush-yao ${gold ? 'gold' : ''} ${wxc}`}>
      {yang
        ? <i style={{ animationDelay: `${delay}ms` }} />
        : (<><i style={{ animationDelay: `${delay}ms` }} /><i style={{ animationDelay: `${delay + 60}ms` }} /></>)}
    </div>
  )
}

/** 一卦：角色签 + 墨笔六爻（自上而下）+ 竖排卦名 + 五行/注 */
export function BrushGua({ role, name, lines, moving = [], wx, note, nameGold, lowerWx, upperWx }: {
  role: string
  name: string
  lines: number[]              // 自下而上
  moving?: number[]
  wx?: ReactNode
  note?: string
  nameGold?: boolean
  lowerWx?: string             // 下卦五行：给 1–3 爻着色
  upperWx?: string             // 上卦五行：给 4–6 爻着色
}) {
  const topDown = [...lines].map((v, i) => ({ v, pos: i + 1 })).reverse()
  return (
    <div>
      <div className="gua-role">{role}</div>
      <div className="brush-gua">
        {topDown.map(({ v, pos }, idx) => (
          <BrushYao
            key={pos}
            yang={v === 1}
            gold={moving.includes(pos)}
            delay={idx * 90}
            wx={pos <= 3 ? lowerWx : upperWx}
          />
        ))}
        <div className="gua-name-v" style={nameGold ? { color: 'var(--foil-4)' } : undefined}>{name}</div>
      </div>
      {wx && <div className="gua-wx">{wx}</div>}
      {note && <div className="gua-note">{note}</div>}
    </div>
  )
}

/** 钤印：吉=金箔印 / 凶=墨印 / 平=铂印 */
export function SealStamp({ tone, children, label }: {
  tone: 'gold' | 'ink' | 'plat'
  children: ReactNode
  label?: string
}) {
  return (
    <span className={`seal-stamp seal-${tone}`} role="img" aria-label={label || String(children)} title={label}>
      {children}
    </span>
  )
}

/** 铜钱：zi=字面（金箔） bei=背面（丝绢）；旋转中钱面留白，落定显字 */
export function Coin3D({ zi, spinning }: { zi: boolean; spinning: boolean }) {
  return (
    <div className={`coin3d ${spinning ? 'spinning' : ''}`}>
      <span className={`face ${zi ? 'zi' : 'bei'}`}>{zi ? '字' : '背'}</span>
    </div>
  )
}
