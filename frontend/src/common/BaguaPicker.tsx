/**
 * 手动起卦面板 —— 上卦 / 下卦 / 动爻 三个格子 + 万物搜索 + 后天八卦图 + 物象框
 * ============================================================
 * 用户的要求（逐条对应）：
 *   1. 三个空填上卦、下卦、动爻 —— 见 .mc-fields（每格都能直接选，也能从图/搜索里填）；
 *   2. 八卦的万类属物用后天八卦图呈现 —— 见 BaguaChart（九宫、南上北下）；
 *   3. 鼠标移到卦上放大 + 高光，点击列出该卦已记录的物象 —— 见 .bg-cell:hover 与右侧 .ww-panel；
 *   4. 物象太多，所以在八卦图上面放一个向量搜索框，搜遍全部卦的万物 —— 见 .ww-search；
 *   5. 向量语义由用户规定的《八卦属性》文本决定 —— 见 data/baguaAttr.ts 与 baguaSearch.ts；
 *   6. 搜索结果除了「设为上卦」「设为下卦」，还要告诉用户谁该为上卦、谁该为下卦
 *      —— 见 .ww-rule，规则一律照《梅花易数》原文并附底本行号，不代拟。
 *
 * 起卦本身走后端 method:'manual'（engine.divine_manual）：用户给的就是卦，不取余、不换算；
 * 体用仍由引擎机械判定（动爻所在卦为用）。这一格不调 AI、不扣额度。
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import BaguaChart, { TrigramGlyph } from './BaguaChart'
import {
  buildIndex, searchBagua,
  type BaguaIndex, type SearchResult,
} from './baguaSearch'
import { fetchGuaWanwu, type WanwuGua } from '../api/meihua'
import { friendlyError } from '../api/client'
import { attrOf } from '../data/baguaAttr'
import { WUXING_AXES } from '../data/wuxingAxes'
import { TRIGRAMS, YAO_NAMES, movingByDuanfa, shichenOf, triOf } from '../data/trigrams'

/** 搜索命中文字里要把命中的词加粗 */
function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function highlight(text: string, matched: string[]): ReactNode {
  if (!matched.length) return text
  const re = new RegExp(`(${matched.map(escapeRe).join('|')})`, 'g')
  return text.split(re).map((p, i) => (
    matched.includes(p) ? <b className="ww-mark" key={i}>{p}</b> : <span key={i}>{p}</span>
  ))
}

export default function BaguaPicker({ upper, lower, moving, onUpper, onLower, onMoving }: {
  upper: number          // 先天数 1-8；0 = 未定
  lower: number
  moving: number         // 1-6；0 = 未定
  onUpper: (n: number) => void
  onLower: (n: number) => void
  onMoving: (n: number) => void
}) {
  /* ---------- 类象数据（静态字典，取一次就够） ---------- */
  const [guaList, setGuaList] = useState<WanwuGua[] | null>(null)
  const [source, setSource] = useState('')
  const [loadErr, setLoadErr] = useState('')
  /** 口语 → 原文条目的检索词表（keys.map）。单字（如「门」）靠它对到「门户枋」。 */
  const [colloqMap, setColloqMap] = useState<Record<string, string[]> | undefined>(undefined)

  const load = useCallback(() => {
    setLoadErr('')
    fetchGuaWanwu()
      .then((r) => {
        setGuaList(r['八卦'] || [])
        setSource(r['出处'] || '')
        setColloqMap(r['检索词'] || undefined)
      })
      .catch((e) => setLoadErr(friendlyError(e)))
  }, [])
  useEffect(() => { load() }, [load])

  const idx: BaguaIndex | null = useMemo(
    () => (guaList ? buildIndex(guaList, source, colloqMap) : null), [guaList, source, colloqMap])
  const itemCount = useMemo(() => (idx ? idx.items.length : 0), [idx])

  /* ---------- 搜索（180ms 防抖；本地向量，不发请求） ---------- */
  const [q, setQ] = useState('')
  const [res, setRes] = useState<SearchResult | null>(null)
  const [searched, setSearched] = useState('')
  useEffect(() => {
    const s = q.trim()
    if (!s) { setRes(null); setSearched(''); return }
    const t = window.setTimeout(() => {
      if (!idx) return
      setRes(searchBagua(idx, s, { limit: 30 }))
      setSearched(s)
    }, 180)
    return () => window.clearTimeout(t)
  }, [q, idx])

  /* ---------- 物象框 ---------- */
  const [selGua, setSelGua] = useState<number | null>(null)
  const [cat, setCat] = useState('')
  /** 物象框整框是否展开（用户要求：整框可收起，框内不变） */
  const [panelOpen, setPanelOpen] = useState(true)
  /** 点物象、双击图上的卦，都填进这一格：上卦或下卦 */
  const [clickTo, setClickTo] = useState<'upper' | 'lower'>('upper')
  const [placed, setPlaced] = useState('')

  const sel = useMemo(
    () => (selGua ? (guaList || []).find((g) => g['先天数'] === selGua) || null : null),
    [selGua, guaList])
  const selTri = selGua ? triOf(selGua) : null
  const selAttr = selTri ? attrOf(selTri.name) : null
  const selCats = useMemo(() => {
    if (!sel) return [] as [string, string[]][]
    return Object.entries(sel['类象'] || {})
      .filter((e): e is [string, string[]] => Array.isArray(e[1]) && e[1].length > 0)
  }, [sel])
  const selTotal = selCats.reduce((n, [, v]) => n + v.length, 0)
  const shownCats = cat ? selCats.filter(([k]) => k === cat) : selCats

  /** 把某一卦填进上卦或下卦，并把"填了什么"如实说一句。
      what 要自带全部限定（物象原文、所属卦、类目、先天数），这里不再另拼后缀，
      否则会出现「已把「金玉」（乾卦）（乾·先天数 1）」这种叠字。 */
  const place = (num: number, what: string, to: 'upper' | 'lower') => {
    if (to === 'upper') onUpper(num)
    else onLower(num)
    setPlaced(`已把${what}设为${to === 'upper' ? '上卦' : '下卦'}`)
  }
  const whatOfGua = (num: number) => `「${triOf(num)?.name}卦」（先天数 ${num}）`

  /* ---------- 端法算动爻 ---------- */
  const [duanfa, setDuanfa] = useState('')
  const byDuanfa = () => {
    if (!upper || !lower) {
      setDuanfa('要按端法算动爻，得先定上卦与下卦（(上卦先天数 + 下卦先天数 + 时辰数) ÷ 6 取余）')
      return
    }
    const sc = shichenOf()
    const r = movingByDuanfa(upper, lower, sc.num)
    onMoving(r.yao)
    setDuanfa(`按现在时辰 ${sc.label}（${sc.zhi}＝${sc.num}）：${r.formula}`)
  }

  /* ---------- 六爻预览（下卦爻1-3、上卦爻4-6；不猜卦名，卦名由后端排盘给） ---------- */
  const preview = upper && lower
    ? [...(triOf(lower)?.lines || []), ...(triOf(upper)?.lines || [])]
    : null

  const [showRule, setShowRule] = useState(false)
  const loading = guaList === null && !loadErr

  return (
    <div className="manual-cast">
      {/* ===== 三个格子 ===== */}
      <div className="mc-fields">
        <div className="mc-field">
          <span className="mc-label">上卦<span className="mc-why">物象所得之卦</span></span>
          <div className="mc-box">
            <span className="mc-glyph">
              {upper ? <TrigramGlyph t={triOf(upper)!} /> : <i className="mc-empty">?</i>}
            </span>
            <select className="select" value={upper} aria-label="上卦（先天数）"
              onChange={(e) => onUpper(Number(e.target.value))}>
              <option value={0}>未定 · 请选一卦</option>
              {TRIGRAMS.map((t) => (
                <option key={t.num} value={t.num}>{t.symbol} {t.name} · 先天{t.num} · {t.pos} · {t.nature}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="mc-field">
          <span className="mc-label">下卦<span className="mc-why">方位所得之卦</span></span>
          <div className="mc-box">
            <span className="mc-glyph">
              {lower ? <TrigramGlyph t={triOf(lower)!} /> : <i className="mc-empty">?</i>}
            </span>
            <select className="select" value={lower} aria-label="下卦（先天数）"
              onChange={(e) => onLower(Number(e.target.value))}>
              <option value={0}>未定 · 请选一卦</option>
              {TRIGRAMS.map((t) => (
                <option key={t.num} value={t.num}>{t.symbol} {t.name} · 先天{t.num} · {t.pos} · {t.nature}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="mc-field">
          <span className="mc-label">动爻<span className="mc-why">定体用：动者为用</span></span>
          <div className="mc-box">
            <span className="mc-glyph mc-yao">{moving ? YAO_NAMES[moving - 1] : '未定'}</span>
            <select className="select" value={moving} aria-label="动爻"
              onChange={(e) => onMoving(Number(e.target.value))}>
              <option value={0}>未定 · 请选一爻</option>
              {YAO_NAMES.map((n, i) => <option key={n} value={i + 1}>{n}（第 {i + 1} 爻）</option>)}
            </select>
          </div>
        </div>

        <div className="mc-side">
          <button type="button" className="btn-outline" onClick={byDuanfa}>按时辰算动爻</button>
          {duanfa && <span className="mc-note">{duanfa}</span>}
          <div className="mc-preview" aria-hidden>
            {preview
              ? [5, 4, 3, 2, 1, 0].map((i) => (
                <span key={i} className={`pv-line ${moving === i + 1 ? 'moving' : ''} ${preview[i] ? 'yang' : 'yin'}`} />
              ))
              : <span className="mc-note">定出上卦与下卦，这里先画出六爻（卦名由排盘给出）</span>}
          </div>
        </div>
      </div>
      {placed && <div className="mc-placed" role="status">{placed}</div>}

      {/* ===== 搜索（在八卦图上面） ===== */}
      <div className="ww-search">
        <span className="mc-label">搜万物<span className="mc-why">全部八卦 · {itemCount || '…'} 条物象 + 8 段八卦属性</span></span>
        <div className="ww-search-row">
          <input
            className="mini-input"
            value={q}
            maxLength={40}
            aria-label="搜万物类象"
            placeholder="输入你看到或想到的东西，如：金玉、老人、圆物、红色、口舌、鸡、文书、领导力"
            onChange={(e) => setQ(e.target.value)}
          />
          {q && (
            <button type="button" className="btn-outline" onClick={() => { setQ(''); setRes(null) }}>清空</button>
          )}
        </div>
        <span className="mc-note">
          本地向量检索：物象与《八卦属性》都切成字一元组＋二元组、按 TF-IDF 取余弦，
          物象分再叠加该卦属性分的 0.35 倍。<b>只认字面与近字面</b>——类象是《梅花易数》原文逐字抽取的，
          收的是「金玉、圆物、君父、天鹅」这类字眼；搜「钥匙」「汽车」这类今语命中不了，
          请换成古语或它的材质、形状、颜色（如「钥匙」→「金」「锁」）。
        </span>
      </div>

      {res && (
        <div className="ww-hits">
          {/* ===== 栏一：原文条目命中（可当书证）===== */}
          {res.literal.length > 0 && (
            <div className="ww-sec">
              <div className="ww-sec-title">
                原文条目命中
                <span className="mc-note">逐字出自《八卦万物属类》，带类目自己的底本行号，可当书证</span>
              </div>
              {res.literal.map((h, i) => (
                <div className="ww-hit lit" key={`l${i}`}>
                  <span className="wh-gua">
                    <TrigramGlyph t={triOf(h.item.num)!} />
                    <b>{h.item.gua}</b><i>先天{h.item.num}</i>
                  </span>
                  <span className="wh-body">
                    <span className="wh-text">{highlight(h.item.text, h.matched || [])}</span>
                    <span className="wh-why">
                      {h.item.cats.join(' · ')}　<b className="ww-tier">{h.tier}</b>{h.via ? `　${h.via}` : ''}
                      {h.item.line ? `　出处：${source || '《梅花易数·卷一·八卦万物属类》'}（底本第 ${h.item.line} 行）` : ''}
                    </span>
                  </span>
                  <span className="wh-act">
                    <button type="button" className="btn-outline"
                      onClick={() => place(h.item.num, `「${h.item.text}」（${h.item.gua}卦·${h.item.cats[0]}）`, 'upper')}>设为上卦</button>
                    <button type="button" className="btn-outline"
                      onClick={() => place(h.item.num, `「${h.item.text}」（${h.item.gua}卦·${h.item.cats[0]}）`, 'lower')}>设为下卦</button>
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* ===== 栏二：相关度命中（tf-idf 余弦，非原文条目）===== */}
          {res.related.length > 0 && (
            <div className="ww-sec">
              <div className="ww-sec-title">
                相关度命中
                <span className="mc-note">余弦相关度，<b>不是原文条目</b>——只作参考，别当书证引用</span>
              </div>
              {res.related.map((h, i) => (h.kind === 'gua' ? (
                <div className="ww-hit gua" key={`g${i}`}>
                  <span className="wh-gua">
                    <TrigramGlyph t={triOf(h.num)!} />
                    <b>{h.gua}</b><i>先天{h.num}</i>
                  </span>
                  <span className="wh-body">
                    <b className="wh-tag">整卦命中</b>
                    <span className="wh-text">{highlight(h.snippet, [])}</span>
                    <span className="wh-why">
                      出自<b>本站自定</b>的《八卦属性》（非典籍原文）· 匹配度 {Math.round(h.score * 100)}%
                    </span>
                  </span>
                  <span className="wh-act">
                    <button type="button" className="btn-outline"
                      onClick={() => place(h.num, `「${h.gua}卦整体类象」`, 'upper')}>设为上卦</button>
                    <button type="button" className="btn-outline"
                      onClick={() => place(h.num, `「${h.gua}卦整体类象」`, 'lower')}>设为下卦</button>
                    <button type="button" className="btn-outline" onClick={() => { setSelGua(h.num); setCat('') }}>看物象</button>
                  </span>
                </div>
              ) : (
                <div className="ww-hit" key={`i${i}`}>
                  <span className="wh-gua">
                    <TrigramGlyph t={triOf(h.item.num)!} />
                    <b>{h.item.gua}</b><i>先天{h.item.num}</i>
                  </span>
                  <span className="wh-body">
                    <span className="wh-text">{highlight(h.item.text, h.matched)}</span>
                    <span className="wh-why">
                      {h.item.cats.join(' · ')}　匹配度 {Math.round(h.score * 100)}%
                      {h.item.line ? `　出处：${source || '《梅花易数·卷一·八卦万物属类》'}（底本第 ${h.item.line} 行）` : ''}
                    </span>
                  </span>
                  <span className="wh-act">
                    <button type="button" className="btn-outline"
                      onClick={() => place(h.item.num, `「${h.item.text}」（${h.item.gua}卦·${h.item.cats[0]}）`, 'upper')}>设为上卦</button>
                    <button type="button" className="btn-outline"
                      onClick={() => place(h.item.num, `「${h.item.text}」（${h.item.gua}卦·${h.item.cats[0]}）`, 'lower')}>设为下卦</button>
                  </span>
                </div>
              )))}
            </div>
          )}

          {res.literal.length === 0 && res.related.length === 0 && (
            <div className="ww-none">
              <div className="ww-none-main">
                没有找到与「{searched}」字面相关的物象。《梅花易数·八卦万物属类》卷末：
                「以上万物之象，庶事之多，不止于此。占者宜各以其类而推之耳。」（底本行 1594）
                —— 原书本就让你按类自己推。你第一念注意的是它的哪一面？
              </div>
              <div className="ww-axes">
                {WUXING_AXES.map((ax) => (
                  <div className="ww-axis" key={ax.key}>
                    <div className="ww-axis-name">
                      {ax.name}
                      <span className="mc-note">{ax.src}</span>
                    </div>
                    <div className="ww-axis-items">
                      {ax.items.map((it, i) => (
                        <button key={i} type="button" className="btn-outline ww-axis-chip"
                          title={`${it.label} → ${it.gua}（设为${clickTo === 'upper' ? '上' : '下'}卦）`}
                          onClick={() => {
                            const t = TRIGRAMS.find((x) => x.name === it.gua)
                            if (t) place(t.num, `「${it.gua}卦」${ax.name}：${it.label}`, clickTo)
                          }}>
                          {it.label}
                          <b className="ww-axis-gua">{it.gua}</b>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
                <span className="mc-note">
                  点任一条即填入{clickTo === 'upper' ? '上卦' : '下卦'}（可在下方切换）。这几条都是原书原文映射；
                  原书未定先后，你看哪条更像就用哪条。
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ===== 图 + 物象框 ===== */}
      <div className="ww-layout">
        <div className="ww-left">
          {loading && (
            <div className="ink-skel" aria-hidden>
              <span style={{ width: '88%', height: 46 }} /><span style={{ width: '88%', height: 46 }} />
              <span style={{ width: '88%', height: 46 }} />
            </div>
          )}
          {loadErr && (
            <div className="notice notice-err" role="alert">
              <b>错误</b>
              <span className="n-body">
                {loadErr}
                <span className="n-hint">类象数据取不到时，八卦图与物象框都用不了（起卦本身不受影响：三个格子里直接选也能起）。</span>
                <span style={{ display: 'block', marginTop: 8 }}>
                  <button type="button" className="btn-outline" onClick={load}>重新取一次</button>
                </span>
              </span>
            </div>
          )}
          {!loading && !loadErr && (
            <BaguaChart
              selected={selGua} upper={upper || null} lower={lower || null}
              onPick={(n) => { setSelGua(n); setCat(''); setPanelOpen(true) }}
              onFill={(n) => place(n, whatOfGua(n), clickTo)}
              fillHint={clickTo === 'upper' ? '双击＝设为上卦' : '双击＝设为下卦'}
            />
          )}
        </div>

        <div className={`ww-panel ${sel && !panelOpen ? 'collapsed' : ''}`}>
          {!sel && (
            <div className="ww-none">
              点左边八卦图上的任意一卦，这里就列出《八卦万物属类》里它名下的全部物象。
              <span className="mc-note">
                一卦少则八十余条、多则两百余条，按类目（天时·地理·人物·身体·动物·静物·屋宿·饮食·求名·疾病·官讼·五色·数目…）分组；
                嫌多就用上面的搜索框。
              </span>
            </div>
          )}
          {sel && selTri && (
            <>
              {/* 整框可收起：点标题行切换。收起后只剩这一行，框内内容一个字不动。 */}
              <button type="button" className="wp-head" aria-expanded={panelOpen}
                title={panelOpen ? '收起物象' : '展开物象'}
                onClick={() => setPanelOpen((v) => !v)}>
                <span className="wp-caret" aria-hidden>{panelOpen ? '▾' : '▸'}</span>
                <TrigramGlyph t={selTri} className="big" />
                <span className="wp-title">
                  <b>{selTri.name}卦 {selTri.symbol}</b>
                  <span>先天数 {sel['先天数']} · 五行 {sel['五行'] || selTri.wx} · 后天方位 {sel['方位'] || selTri.pos}</span>
                </span>
                <span className="wp-count">{selTotal} 条物象 · {selCats.length} 类</span>
              </button>

              {panelOpen && selAttr && (
                <div className="wp-attr">
                  <b>{selAttr.title}</b>
                  <span>核心属性：{selAttr.core}</span>
                  <span>类象逻辑：{selAttr.logic}</span>
                  <span>{selAttr.gist}</span>
                </div>
              )}

              {panelOpen && (
                <div className="wp-acts">
                  <span className="mc-label" style={{ marginRight: 4 }}>选择</span>
                  <button type="button" className={`slip ${clickTo === 'upper' ? 'active' : ''}`}
                    onClick={() => setClickTo('upper')}>上卦</button>
                  <button type="button" className={`slip ${clickTo === 'lower' ? 'active' : ''}`}
                    onClick={() => setClickTo('lower')}>下卦</button>
                </div>
              )}

              {panelOpen && (
                <div className="wp-cats">
                  <button type="button" className={`slip ${cat === '' ? 'active' : ''}`} onClick={() => setCat('')}>
                    全部 {selTotal}
                  </button>
                  {selCats.map(([k, v]) => (
                    <button type="button" key={k} className={`slip ${cat === k ? 'active' : ''}`} onClick={() => setCat(k)}>
                      {k} {v.length}
                    </button>
                  ))}
                </div>
              )}

              {panelOpen && (
                <div className="wp-body">
                  {shownCats.map(([k, v]) => (
                    <div className="wp-cat" key={k}>
                      <div className="wp-cat-h">{k}<i>{v.length}</i></div>
                      <div className="wp-items">
                        {v.map((it, i) => (
                          <button type="button" className="ww-item" key={`${k}-${i}`}
                            title={`设为${clickTo === 'upper' ? '上卦' : '下卦'}：${selTri.name}卦 · ${k}`}
                            onClick={() => place(sel['先天数'],
                              `「${it}」（${selTri.name}卦·${k}，先天数 ${sel['先天数']}）`, clickTo)}>
                            {it}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* ===== 谁该为上卦、谁该为下卦（照原文，不代拟） ===== */}
      <div className="ww-rule">
        <button type="button" className="ww-rule-toggle" aria-expanded={showRule}
          onClick={() => setShowRule((v) => !v)}>
          {showRule ? '▾' : '▸'} 谁该为上卦、谁该为下卦？（照《梅花易数》原文，附底本行号）
        </button>
        {showRule && (
          <div className="ww-rule-body">
            <p><b>一、从万物类象取到的卦，作上卦。</b>这一篇的篇名本身就是这么写的：
              「八卦万物属类<b>（并为上卦）</b>」（底本第 808 行）。</p>
            <p><b>二、下卦取方位。</b>「后天端法：<b>以物为上卦，方位为下卦</b>，合物卦之数与方卦之数，
              加时数以取动爻。」（第 802 行）白话：「用《八卦万物属类》所得之卦作为上卦，
              用此《八卦方位图》所得的卦作为下卦……用上卦、下卦的先天卦数作为基数，
              再加时数，便可以确定要占的爻。」（第 862 行）</p>
            <p><b>三、只见到一物时</b>：「如见一物，则就以此物为上卦，<b>物来之方位为下卦</b>。
              合物卦数及方位卦数，加时数取爻。」（第 768 行）</p>
            <p><b>四、想用两个物象配上下卦？书里没有这个成法。</b>端法诸占一律是「一物（或一事）＋一时/一方」：
              「以来人的人品作上卦，以问何事作下卦」（第 702 行）、
              「以身体部位作上卦，以问何事作下卦」（第 710 行）、
              「以手拿的各种物品为上卦，以问何事为下卦」（第 718 行）、
              「以上身穿的衣服颜色……作上卦，以下身穿的裤、裙颜色……作下卦」（第 726 行）。
              所以要配两个物象，是你自己的取法，不是书里的成法——界面允许，但如实告诉你这一点。</p>
            <p><b>五、体用不由上下卦决定，由动爻决定。</b>动爻所在的那一卦为<b>用</b>
              （所问之事、对方、外部环境），另一卦为<b>体</b>（求测者自己）。引擎即按此机械判定。</p>
            <p><b>六、动爻按端法可算</b>：（上卦先天数 ＋ 下卦先天数 ＋ 时辰数）÷ 6 取余，
              <b>余 0 作 6</b>；时辰数子 1、丑 2……亥 12（第 480 行「时如子时一数，直至亥时为十二数」）。
              上面「按时辰算动爻」按钮走的就是这个算式，算完会把式子原样摆出来给你核对。</p>
          </div>
        )}
      </div>
    </div>
  )
}
