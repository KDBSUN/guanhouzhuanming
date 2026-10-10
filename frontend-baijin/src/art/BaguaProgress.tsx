import { TRIGRAMS } from '../data/trigrams'

/** 纯装饰的生成中指示。显示条件由调用处已有 thinking/asking 控制，
 * 不参与进度计算、计费或排盘；读屏继续使用页面原有状态文案。 */
export default function BaguaProgress() {
  const ring = [3, 8, 2, 1, 6, 7, 4, 5]
  return (
    <svg className="bagua-progress" viewBox="0 0 100 100" aria-hidden="true" focusable="false">
      <g className="bagua-progress-rotor" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="50" cy="50" r="47" strokeOpacity="0.3" />
        <circle cx="50" cy="50" r="20" strokeOpacity="0.5" />
        {ring.map((num, i) => (
          <g key={num} transform={`rotate(${i * 45} 50 50)`}>
            {[...(TRIGRAMS.find((t) => t.num === num)?.lines || [])].reverse().map((yang, j) => (
              <path key={j} d={yang
                ? `M41 ${10 + j * 5}h18`
                : `M41 ${10 + j * 5}h6m6 0h6`} />
            ))}
          </g>
        ))}
        <path d="M50 32a18 18 0 0 1 0 36c12 0 12-18 0-18s-12-18 0-18Z" fill="currentColor" stroke="none" />
        <circle cx="50" cy="41" r="2.5" fill="currentColor" stroke="none" />
        <circle cx="50" cy="59" r="2.5" fill="var(--surface)" stroke="none" />
      </g>
    </svg>
  )
}
