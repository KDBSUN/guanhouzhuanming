/**
 * 后天八卦九宫图（手动起卦用）
 * ============================================================
 * 方位惯例按传统八卦图：**南上北下、东左西右**，所以九宫排布是
 *   巽东南 │ 离南 │ 坤西南
 *   震东   │ 太极 │ 兑西
 *   艮东北 │ 坎北 │ 乾西北
 * 每格同时标出**先天数**（起卦要填的就是它）与**后天方位**（端法取下卦用的就是它）。
 *
 * 这张图在起卦里有两个用处，都出自《梅花易数》：
 *   · 物象 → 上卦：「八卦万物属类（并为上卦）」（底本第 808 行篇名）；
 *   · 方位 → 下卦：「后天端法：以物为上卦，方位为下卦」（第 802 行）。
 *
 * 交互（用户明确要求）：鼠标移到某个卦上 → 放大 + 高光；点击 → 下方列出该卦已记录的物象。
 * 放大只用 transform（不动 top/left/width），并在 prefers-reduced-motion 下退化成立即生效。
 * 每格都是真 button，可 Tab 聚焦、可回车选中，aria-pressed 表示"正在看这一卦的物象"。
 */
import { HOUTIAN_GRID, triOf, type Trigram } from '../data/trigrams'

/** 三爻卦画：自下而上 [初,二,三]，渲染时倒过来（最上面是第三爻）。阳爻整条，阴爻中断。 */
export function TrigramGlyph({ t, className = '' }: { t: Trigram; className?: string }) {
  return (
    <span className={`tri ${className}`} aria-hidden>
      {[2, 1, 0].map((i) => <i key={i} className={t.lines[i] ? 'yang' : 'yin'} />)}
    </span>
  )
}

/** 太极（中五宫）：只用墨与纸两色 + 金环，不引入新颜色 */
function Taiji() {
  return (
    <svg viewBox="0 0 100 100" className="taiji" aria-hidden focusable="false">
      <circle cx="50" cy="50" r="47" fill="var(--paper)" stroke="var(--foil-3)" strokeWidth="2.5" />
      <path d="M50 3 a47 47 0 0 1 0 94 a23.5 23.5 0 0 1 0-47 a23.5 23.5 0 0 0 0-47 z" fill="var(--ink)" />
      <circle cx="50" cy="26.5" r="6.5" fill="var(--ink)" />
      <circle cx="50" cy="73.5" r="6.5" fill="var(--paper)" />
    </svg>
  )
}

export default function BaguaChart({ selected, upper, lower, onPick, onFill, fillHint }: {
  /** 当前正在看物象的那一卦（先天数）；null = 还没点 */
  selected: number | null
  /** 已定的上卦 / 下卦（先天数）；在图上打「上」「下」角标，让用户看清自己选了什么 */
  upper: number | null
  lower: number | null
  onPick: (num: number) => void
  /** 双击：把这一卦填进"选择"里当前那一格（上卦或下卦） */
  onFill?: (num: number) => void
  /** 双击那件事的一句话说明，写进 title 与 aria-label；不传则不提示 */
  fillHint?: string
}) {
  return (
    <div className="bg-chart" role="group" aria-label="后天八卦方位图（南上北下）">
      {HOUTIAN_GRID.map((row, ri) =>
        row.map((num, ci) => {
          if (num === null) {
            return (
              <div className="bg-cell center" key={`${ri}-${ci}`} aria-hidden>
                <Taiji />
                <span className="bg-center-cap">中五 · 太极</span>
              </div>
            )
          }
          const t = triOf(num)
          if (!t) return <div className="bg-cell empty" key={`${ri}-${ci}`} aria-hidden />
          const isSel = selected === num
          const tags: string[] = []
          if (upper === num) tags.push('上')
          if (lower === num) tags.push('下')
          return (
            <button
              type="button"
              key={`${ri}-${ci}`}
              className={`bg-cell ${isSel ? 'sel' : ''} ${upper === num ? 'is-up' : ''} ${lower === num ? 'is-low' : ''}`}
              aria-pressed={isSel}
              title={fillHint || undefined}
              aria-label={`${t.name}卦，${t.symbol}，${t.pos}方，先天数${t.num}，五行属${t.wx}，${t.nature}`
                + `。${tags.length ? `已选为${tags.join('、')}卦。` : ''}点击查看这一卦的物象`
                + (fillHint ? `；${fillHint}` : '')}
              onClick={() => onPick(num)}
              onDoubleClick={onFill ? () => onFill(num) : undefined}
            >
              {tags.length > 0 && (
                <span className="bg-tags" aria-hidden>
                  {tags.map((g) => <b key={g} className={g === '上' ? 'up' : 'low'}>{g}</b>)}
                </span>
              )}
              <TrigramGlyph t={t} />
              <span className="bg-name">{t.name}</span>
              <span className="bg-pos">{t.pos}</span>
              <span className="bg-num">先天 {t.num}</span>
            </button>
          )
        }),
      )}
      <p className="bg-cap">
        后天八卦方位图 · 南上北下 · 东左西右
        <span className="bg-cap-sub">端法取卦：以物为上卦，方位为下卦</span>
      </p>
    </div>
  )
}
