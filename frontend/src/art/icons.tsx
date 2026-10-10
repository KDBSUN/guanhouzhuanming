import type { ReactNode } from 'react'

/* ============================================================
   易占 · 白金版 —— 线性图案与图标
   全部细线（1.2–1.6px）铂金银描边 + 金箔点缀（.art-accent），
   颜色跟随 currentColor，由容器控制。
   ============================================================ */

interface ArtProps { className?: string }

/** 梅花（五瓣细线 + 金色花蕊） */
export function PlumArt({ className }: ArtProps) {
  const petals = [0, 72, 144, 216, 288]
  return (
    <svg viewBox="0 0 100 100" fill="none" className={className} aria-hidden>
      {petals.map((a) => (
        <ellipse
          key={a}
          cx="50" cy="27" rx="12.5" ry="17.5"
          stroke="currentColor" strokeWidth="1.5"
          transform={`rotate(${a} 50 50)`}
        />
      ))}
      {petals.map((a) => (
        <line
          key={`v${a}`}
          x1="50" y1="44" x2="50" y2="14"
          stroke="currentColor" strokeWidth="0.7" opacity="0.45"
          transform={`rotate(${a} 50 50)`}
        />
      ))}
      <circle cx="50" cy="50" r="6.5" stroke="currentColor" strokeWidth="1.5" fill="#FBFAF7" />
      {[0, 60, 120, 180, 240, 300].map((a) => (
        <circle
          key={`s${a}`}
          cx="50" cy="45.4" r="1.15"
          fill="currentColor"
          className="art-accent"
          transform={`rotate(${a} 50 50)`}
        />
      ))}
      <circle cx="50" cy="50" r="1.7" fill="currentColor" className="art-accent" />
    </svg>
  )
}

/** 铜钱（外圆内方细线 + 金色弧光） */
export function CoinArt({ className }: ArtProps) {
  return (
    <svg viewBox="0 0 100 100" fill="none" className={className} aria-hidden>
      <circle cx="50" cy="50" r="40" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="50" cy="50" r="34" stroke="currentColor" strokeWidth="0.8" opacity="0.55" />
      <rect x="36" y="36" width="28" height="28" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <rect x="39.5" y="39.5" width="21" height="21" rx="1" stroke="currentColor" strokeWidth="0.7" opacity="0.5" />
      <path
        d="M 22 38 A 34 34 0 0 1 42 18"
        stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
        className="art-accent" opacity="0.85"
      />
      <text x="50" y="25.5" textAnchor="middle" fontSize="9.5" fill="currentColor" fontFamily="STZhongsong, SimSun, serif" opacity="0.85">纳</text>
      <text x="50" y="82" textAnchor="middle" fontSize="9.5" fill="currentColor" fontFamily="STZhongsong, SimSun, serif" opacity="0.85">甲</text>
    </svg>
  )
}

/** 太极（细线 + 金色阳鱼目） */
export function TaijiArt({ className }: ArtProps) {
  return (
    <svg viewBox="0 0 100 100" fill="none" className={className} aria-hidden>
      <circle cx="50" cy="50" r="40" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M50,10 A40,40 0 0,1 50,90 A20,20 0 0,1 50,50 A20,20 0 0,0 50,10 Z"
        stroke="currentColor" strokeWidth="1.4"
      />
      <circle cx="50" cy="30" r="4.6" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="50" cy="70" r="4.6" fill="currentColor" className="art-accent" />
      <circle cx="50" cy="50" r="46" stroke="currentColor" strokeWidth="0.7" strokeDasharray="3 4" opacity="0.4" />
    </svg>
  )
}

/** 命印（双框细线印章 + 命字） */
export function SealArt({ className }: ArtProps) {
  return (
    <svg viewBox="0 0 100 100" fill="none" className={className} aria-hidden>
      <rect x="16" y="16" width="68" height="68" rx="8" stroke="currentColor" strokeWidth="1.6" />
      <rect x="23.5" y="23.5" width="53" height="53" rx="4" stroke="currentColor" strokeWidth="0.8" opacity="0.6" />
      <text
        x="50" y="63" textAnchor="middle" fontSize="33"
        fill="currentColor" className="art-accent"
        fontFamily="STZhongsong, SimSun, serif" fontWeight="600"
      >命</text>
      <path d="M 24 12 L 24 6 L 30 6" stroke="currentColor" strokeWidth="1.2" className="art-accent" opacity="0.7" />
      <path d="M 76 88 L 76 94 L 70 94" stroke="currentColor" strokeWidth="1.2" className="art-accent" opacity="0.7" />
    </svg>
  )
}

/* ---------- 卦爻画 ---------- */

/**
 * 六爻/梅花通用的卦画。
 * lines：自下而上 1=阳 0=阴；moving：自下而上 1 起的动爻位。
 * 渲染时翻转为自上而下（上爻在最上）。
 */
export function GuaLines({
  lines, moving = [], className = '', width,
}: {
  lines: number[]
  moving?: number[]
  className?: string
  width?: number
}) {
  const topDown = [...lines].map((v, i) => ({ v, pos: i + 1 })).reverse()
  const hasMoving = moving.length > 0
  return (
    <div className={`gua-lines ${hasMoving ? 'moving' : ''} ${className}`} style={width ? { width } : undefined}>
      {topDown.map(({ v, pos }) => (
        <div key={pos} className={`yao ${moving.includes(pos) ? 'is-moving' : ''}`}>
          {v === 1 ? <i /> : (<><i /><i /></>)}
        </div>
      ))}
    </div>
  )
}

/* ---------- 细线小图标（stroke 1.4，Phosphor-light 同族气质） ---------- */

const ico = (children: ReactNode, viewBox = '0 0 24 24') =>
  function Icon({ size = 18 }: { size?: number }) {
    return (
      <svg
        width={size} height={size} viewBox={viewBox} fill="none"
        stroke="currentColor" strokeWidth="1.4"
        strokeLinecap="round" strokeLinejoin="round"
        aria-hidden
      >
        {children}
      </svg>
    )
  }

export const MenuIcon = ico(<><line x1="4" y1="7" x2="20" y2="7" /><line x1="4" y1="12" x2="20" y2="12" /><line x1="4" y1="17" x2="20" y2="17" /></>)
export const CloseIcon = ico(<><line x1="6" y1="6" x2="18" y2="18" /><line x1="18" y1="6" x2="6" y2="18" /></>)
export const ArrowRightIcon = ico(<><line x1="4" y1="12" x2="19" y2="12" /><polyline points="13.5,6.5 19.5,12 13.5,17.5" /></>)
export const MicIcon = ico(<><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0" /><line x1="12" y1="18" x2="12" y2="21" /></>)
export const EnvelopeIcon = ico(<><rect x="3" y="5.5" width="18" height="13" rx="1.5" /><polyline points="3.8,6.6 12,13 20.2,6.6" /></>)
export const ScaleIcon = ico(<><line x1="12" y1="4" x2="12" y2="19" /><line x1="5" y1="7" x2="19" y2="7" /><path d="M5 7 L2.6 12.6a3.4 3.4 0 0 0 4.8 0Z" /><path d="M19 7 L16.6 12.6a3.4 3.4 0 0 0 4.8 0Z" /><line x1="8.5" y1="19.5" x2="15.5" y2="19.5" /></>)
export const CalendarIcon = ico(<><rect x="3.5" y="5" width="17" height="15.5" rx="1.5" /><line x1="3.5" y1="9.5" x2="20.5" y2="9.5" /><line x1="8" y1="3" x2="8" y2="6.6" /><line x1="16" y1="3" x2="16" y2="6.6" /></>)
export const ScrollIcon = ico(<><path d="M6 3.5h12a1.5 1.5 0 0 1 1.5 1.5v13a2.5 2.5 0 0 1-2.5 2.5H7" /><path d="M7 20.5A2.5 2.5 0 0 1 4.5 18V6" /><path d="M4.5 6A2.5 2.5 0 0 1 7 3.5" /><line x1="9" y1="8" x2="15.5" y2="8" /><line x1="9" y1="11.5" x2="15.5" y2="11.5" /><line x1="9" y1="15" x2="13" y2="15" /></>)
export const CompassIcon = ico(<><circle cx="12" cy="12" r="8.6" /><polygon points="14.8,9.2 10.4,10.4 9.2,14.8 13.6,13.6" /></>)
export const BaguaIcon = ico(<><circle cx="12" cy="12" r="8.6" opacity="0.4" /><line x1="8.4" y1="9" x2="15.6" y2="9" /><line x1="8.4" y1="12" x2="11.2" y2="12" /><line x1="12.8" y1="12" x2="15.6" y2="12" /><line x1="8.4" y1="15" x2="15.6" y2="15" /></>, '0 0 24 24')
