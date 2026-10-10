import { useState } from 'react'
import { llmPayload } from '../api/llm'
import { postStream } from '../api/sse'
import MarkdownLite from '../common/MarkdownLite'

// ============================================================
// 大运流年详批（事业 / 财运 / 感情）—— 八字排盘页末（白金版）
// ============================================================
// 输出结构对齐站长给定成品《八字全年命理总览_2025-2060.md》与 skills 的
// output-format（〇命理总纲线 → 〇·一怎么看 → 〇·二关键年份速查 → 〇·三大运总览 →
// 逐年三档 → 重点年份流月 → 趋势总结 → 附评分总表）。
// 确定性（干支十神五行、喜忌、结构、合冲刑害破伏吟拱会、成局、吉年险年、流月）由
// 后端 /api/bazi/dayun 代码算定（scaffold 事件，不扣额度）；AI 按成品格式写白话与
// 事件/评分/标题（扣一次额度，自带 key 不限次），页脚统一声明 AI 边界。

const DIM_LABEL: Record<string, string> = { shiye: '事业', caiyun: '财运', ganqing: '感情' }
const MARITAL = ['单身', '恋爱中', '已婚']

type Scaffold = Record<string, any>

interface DimResult {
  scaffold: Scaffold | null
  aiText: string
  verify: string
}

const FOOTER = '\n\n> **说明**：本详批的确定性部分（干支十神、五行喜忌、结构、合冲刑害破伏吟拱会、成局、吉年险年、流月）由程序计算；具体事件、评分、标题为 AI 推断（无逐字书证、不可复现）。命理为传统学说，仅供参考，具体决策请结合现实判断。'

function downloadMd(name: string, content: string) {
  const blob = new Blob(['\ufeff' + content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

/* ---------- 确定性兜底：无 AI 文字时由骨架拼成品格式 md ---------- */
function gangxianLines(g: any): string[] {
  const L: string[] = []
  L.push(`> **${g.zao}**：${g.pillars}（公历 ${g.solar}，农历 ${g.lunar}）｜${g.zao === '乾造' ? '男命' : '女命'}`)
  const qy = g['起运'] || {}
  L.push(`> 起运：${qy.years ?? '×'}岁${qy.months ?? '×'}个月（${qy.solar || ''} 交运）｜排盘复核：程序排定`)
  L.push('')
  L.push(`**强弱**：**${g.tier}**（日主${g.day_master}，${g.day_master_wx}；${((g.tier_reason || {}).月令) || ''}，${(g.tier_reason || {}).月令长生 || ''}）。`)
  L.push(`**喜用**：**${(g.F || []).join('、') || '无'}**（第一用神） ＋ ${(g.F || []).slice(1).join('、') || '—'}（次喜神）。`)
  L.push(`**忌神**：${(g.J || []).join('、') || '无'}。`)
  if (g.T0?.length) L.push(`**调候**：${g.T0.join('、')}（${g.t0_src || ''}）。`)
  if (g.from_ge) L.push(`**格局**：${g.from_ge}。`)
  L.push(`**一生总原则**：走「**以${(g.F || ['用神'])[0]}为用、以${(g.F || [])[1] || (g.F || ['用神'])[0]}为辅**」路线；忌神之乡只守不攻。`)
  L.push('')
  L.push('**现实"补身"三件事（按所缺五行，先补第一用神、再补次喜神）**：')
  ;(g.buxin || []).forEach((b: any, i: number) => {
    L.push(`${i + 1}. **补${b['性质'] === '忌神' ? '（管理）' : ''}「${b['五行']}·${b['十神']}」**${b['性质'] === '第一用神' ? '（最重要）' : ''}——现实对应：${b['现实']}。`)
  })
  return L
}

function scaffoldMd(sc: Scaffold, yFrom: number, yTo: number, label: string): string {
  const g = sc.gangxian || {}
  const L: string[] = []
  L.push(`# 命主大运流年详批（${yFrom}–${yTo}）· ${label}`)
  L.push('')
  L.push('## 〇、命理总纲线')
  L.push(...gangxianLines(g))
  L.push('')
  L.push('## 〇·二、关键年份速查')
  L.push('| 类别 | 🚨 关键吉年（主动投入） | 🚨 关键险年（主动防守） |')
  L.push('|---|---|---|')
  L.push(`| **${label}** | ${(sc.key_years?.['吉年'] || []).join(' / ') || '—'} | ${(sc.key_years?.['险年'] || []).join(' / ') || '—'} |`)
  L.push('')
  L.push('## 〇·三、大运总览')
  L.push('| 大运 | 干支十神 | 区间 | 年龄 |')
  L.push('|---|---|---|---|')
  for (const d of sc.dayun_rows || []) {
    L.push(`| ${d['干支']} | 干（${d['干十神']}·${d['干喜忌']}）＋支（${d['支十神']}·${d['支喜忌']}） | ${d['起年']}–${d['止年']} | ${d['起']}–${d['止']}岁 |`)
  }
  L.push('')
  L.push('## 三、逐年（确定性骨架）')
  L.push('| 年份 | 干支 | 十神·五行·喜忌 | 大运（关系） | 与原局关系 | 成局 | 神煞 | 标志 |')
  L.push('|---|---|---|---|---|---|---|---|')
  for (const r of sc.year_rows || []) {
    if (r.note) { L.push(`| ${r.year} | — | — | — | — | — | — | ${r.note} |`); continue }
    const flags = Object.entries(r)
      .filter(([k]) => !['year', 'age', '干支', '干十神', '支十神', '干五行', '支五行', '干喜忌', '支喜忌', '大运', '大运关系', '原局关系', '成局', '神煞'].includes(k))
      .map(([k, v]) => (v === true ? k : `${k}=${v}`)).join('；')
    L.push(`| ${r.year}（${r.age}岁） | ${r['干支']} | 干${r['干十神']}(${r['干五行']}·${r['干喜忌']})／支${r['支十神']}(${r['支五行']}·${r['支喜忌']}) | ${r['大运']}（${(r['大运关系'] || []).join('、') || '—'}） | ${(r['原局关系'] || []).map((x: any) => `${x['柱']}${x['干支']}${x['关系'].join('、')}`).join('；') || '—'} | ${(r['成局'] || []).join('、') || '—'} | ${(r['神煞'] || []).join('、') || '—'} | ${flags || '—'} |`)
  }
  L.push('')
  L.push('## 五、重点年份流月（干支月按节令）')
  for (const [y, months] of Object.entries(sc.liu_yue || {})) {
    L.push(`- ${y} 年：${(months as any[]).map((m) => `${m['月']}${m['干支']}(${m['干十神']}·${m['支十神']})`).join('｜')}`)
  }
  return L.join('\n') + FOOTER
}

/* ---------- 全年总览（niankan）：三档 AI 文本按年并排 ---------- */
function splitByYear(text: string): { year: number; content: string }[] {
  const re = /^# (\d{4}) [^\n]*$/gm
  const out: { year: number; content: string }[] = []
  let m: RegExpExecArray | null
  let lastIdx = -1
  let lastYear = -1
  while ((m = re.exec(text)) !== null) {
    if (lastIdx >= 0) out.push({ year: lastYear, content: text.slice(lastIdx, m.index).trim() })
    lastIdx = m.index
    lastYear = Number(m[1])
  }
  if (lastIdx >= 0) out.push({ year: lastYear, content: text.slice(lastIdx).trim() })
  return out
}

function niankanMd(results: Record<string, DimResult>, yFrom: number, yTo: number): string {
  const dims = ['shiye', 'caiyun', 'ganqing'].filter((d) => results[d]?.scaffold)
  const first = results[dims[0]]!
  let preamble = ''
  if (first.aiText) {
    const m = first.aiText.match(/^(.*?)(?=^# \d{4} )/ms)
    preamble = (m ? m[1] : '').trim()
  }
  if (!preamble) {
    // 无 AI 文字时用确定性纲线兜底
    const g = first.scaffold!.gangxian || {}
    preamble = ['## 〇、命理总纲线（开头一次 · 全档通用）', '', ...gangxianLines(g),
      '', '## 〇·二、关键年份速查', '',
      '| 类别 | 🚨 关键吉年（主动投入） | 🚨 关键险年（主动防守） |', '|---|---|---|',
      ...dims.map((d) => `| **${DIM_LABEL[d]}** | ${(results[d].scaffold?.key_years?.['吉年'] || []).join(' / ') || '—'} | ${(results[d].scaffold?.key_years?.['险年'] || []).join(' / ') || '—'} |`),
      '', '## 〇·三、大运总览（三档并列）', '',
      '| 大运 | 干支十神 | 区间 | 年龄 |',
      '|---|---|---|---|',
      ...(first.scaffold!.dayun_rows || []).map((d: any) => `| ${d['干支']} | 干（${d['干十神']}·${d['干喜忌']}）＋支（${d['支十神']}·${d['支喜忌']}） | ${d['起年']}–${d['止年']} | ${d['起']}–${d['止']}岁 |`)].join('\n')
  }
  const L: string[] = [`# 命主全年命理总览（${yFrom}–${yTo}）`, '',
    '> **一个文件看全部年份**。按年分节，每年内依次为：**事业 → 财运 → 感情**。命理大纲只在开头写一次，全档通用。', '', preamble, '']

  // 逐年三档并排：按 AI 文本的 `# YYYY …` 标题切年，再按 事业→财运→感情 拼接
  const byYear: Record<number, Record<string, string>> = {}
  for (const d of dims) {
    if (results[d].aiText) {
      for (const b of splitByYear(results[d].aiText)) {
        byYear[b.year] = byYear[b.year] || {}
        byYear[b.year][d] = b.content
      }
    }
  }
  const yearRow = (y: number) => {
    for (const d of dims) {
      const r = (results[d].scaffold?.year_rows || []).find((x: any) => x.year === y)
      if (r) return r
    }
    return null
  }
  for (const y of Object.keys(byYear).map(Number).sort((a, b) => a - b)) {
    const r = yearRow(y)
    const head = r && !r.note ? `${y} ${r['干支']}年 · ${r['大运']}大运（约${r.age}岁）` : `${y} 年`
    L.push(`# ${head}`)
    L.push('')
    for (const d of dims) {
      if (byYear[y][d]) {
        L.push(byYear[y][d].replace(/^# .*$/m, '').trim())
        L.push('')
      }
    }
  }
  if (!Object.keys(byYear).length) {
    // 全部维度都无 AI 文字：退回三份确定性骨架并排
    for (const d of dims) {
      L.push(`## ${DIM_LABEL[d]}（确定性骨架）`)
      L.push('')
      L.push(scaffoldMd(results[d].scaffold!, yFrom, yTo, DIM_LABEL[d]))
      L.push('')
    }
  }
  L.push('> **使用说明**：每年春节前通读当年一节即可。吉年顺势用力，凶年逆势守成；🚨 关键年份务必重点设防。')
  L.push('')
  L.push(FOOTER.replace(/^\n\n/, ''))
  return L.join('\n')
}

export default function DayunPanel({ birth }: { birth: Record<string, unknown> | null }) {
  const thisYear = new Date().getFullYear()
  const [yFrom, setYFrom] = useState(thisYear)
  const [yTo, setYTo] = useState(thisYear + 9)
  const [marital, setMarital] = useState('单身')
  const [loading, setLoading] = useState('')
  const [error, setError] = useState('')
  const [degrade, setDegrade] = useState('')
  const [results, setResults] = useState<Record<string, DimResult>>({})

  const run = async (dim: 'shiye' | 'caiyun' | 'ganqing') => {
    if (!birth || loading) return
    setLoading(dim)
    setError('')
    setDegrade('')
    setResults((prev) => ({ ...prev, [dim]: { scaffold: prev[dim]?.scaffold ?? null, aiText: '', verify: '' } }))
    try {
      await postStream('/api/bazi/dayun', {
        birth, dimension: dim, year_from: yFrom, year_to: yTo,
        marital_status: dim === 'ganqing' ? marital : '', ai: true, ...llmPayload(),
      }, (data) => {
        if (data.type === 'scaffold') {
          setResults((prev) => ({ ...prev, [dim]: { scaffold: data.data as Scaffold, aiText: '', verify: '' } }))
        } else if (data.type === 'text') {
          const chunk = String(data.content || '')
          setResults((prev) => ({ ...prev, [dim]: { ...prev[dim], aiText: (prev[dim]?.aiText || '') + chunk } }))
        } else if (data.type === 'degraded') {
          setDegrade(String(data.message || '') + (data.hint ? `（${data.hint}）` : ''))
        } else if (data.type === 'verify' || data.type === 'truncated') {
          const note = data.type === 'truncated'
            ? '解读未写完（超出长度上限），可重新生成或缩短年份范围。'
            : '回检提示：详见站点反馈台账。'
          setResults((prev) => ({ ...prev, [dim]: { ...prev[dim], verify: note } }))
        } else if (data.type === 'error') {
          setError(String(data.message || '请求失败'))
        }
      })
    } catch (e) {
      setError((e as Error)?.message || '请求失败')
    } finally {
      setLoading('')
    }
  }

  const dims = ['shiye', 'caiyun', 'ganqing'].filter((d) => results[d]?.scaffold)

  return (
    <div className="bj-dayun">
      <div className="bz-head">
        <h2>大运流年详批</h2>
        <span className="rule" />
        <span className="aside">输出格式对齐《全年命理总览》成品 · 确定性骨架由程序计算 · AI 只补白话与事件层</span>
      </div>
      {!birth && <div className="bj-dayun-sub">请先完成一次排盘，再生成详批（排盘为纯计算，不扣额度）。</div>}

      <div className="bj-dayun-controls">
        <label className="bj-dayun-field">年份
          <input type="number" min={1900} max={2200} value={yFrom}
                 onChange={(e) => setYFrom(Number(e.target.value))} />
        </label>
        <span className="bj-dayun-dash">–</span>
        <label className="bj-dayun-field">年份
          <input type="number" min={1900} max={2200} value={yTo}
                 onChange={(e) => setYTo(Number(e.target.value))} />
        </label>
        <label className="bj-dayun-field">婚恋状态
          <select value={marital} onChange={(e) => setMarital(e.target.value)}>
            {MARITAL.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
      </div>
      <div className="bj-dayun-sub">
        注：最好使用 <b>deepseek-v4-pro</b> 大模型（在「API 设置」页选择；未配置则用站点默认模型）。
        AI 详批消耗 1 次额度，自带 key 不限次。骨架含 合冲刑害破伏吟拱会（渊海·论十二支六合/三合/相冲/相穿/相刑；子平真诠·论刑冲会合解法）。
      </div>

      <div className="btn-row" style={{ marginTop: 10 }}>
        {(['shiye', 'caiyun', 'ganqing'] as const).map((d) => (
          <button key={d} type="button" className="btn" onClick={() => run(d)} disabled={!!loading || !birth}>
            {loading === d ? '生成中…' : `${DIM_LABEL[d]}${results[d]?.aiText ? '（重新生成）' : ''}`}
          </button>
        ))}
        {dims.length >= 2 && (
          <button type="button" className="btn-outline" onClick={() =>
            downloadMd(`全年命理总览-${yFrom}-${yTo}.md`, niankanMd(results, yFrom, yTo))
          }>
            全年总览（合并下载 md）
          </button>
        )}
      </div>

      {error && <div className="bj-dayun-error">{error}</div>}
      {degrade && <div className="bj-dayun-degrade">{degrade}</div>}

      {dims.map((d) => {
        const r = results[d]
        const sc = r.scaffold
        if (!sc) return null
        const g = sc.gangxian || {}
        return (
          <div className="bj-dayun-result" key={d}>
            <div className="bj-dayun-result-head">
              <b>{DIM_LABEL[d]}（{yFrom}–{yTo}）</b>
              <button type="button" className="bj-dayun-dl" onClick={() =>
                downloadMd(`大运流年详批-${DIM_LABEL[d]}-${yFrom}-${yTo}.md`,
                           r.aiText
                             ? `# 命主大运流年详批（${yFrom}–${yTo}）· ${DIM_LABEL[d]}\n\n${r.aiText.trim()}` + FOOTER
                             : scaffoldMd(sc, yFrom, yTo, DIM_LABEL[d]))
              }>下载 md</button>
            </div>

            <div className="bj-dayun-scaffold">
              <div className="bj-dayun-gangxian">
                四柱 <b>{g.pillars}</b> · {g.zao} · 日主{g.day_master}（{g.day_master_wx}） · {g.tier}
                {' '}· 喜用 {((g.F || []).join('、') || '无')} · 忌神 {((g.J || []).join('、') || '无')}
                {(g.T0 || []).length > 0 && <> · 调候 {(g.T0 || []).join('、')}</>}
              </div>
              <div className="bj-dayun-sub">
                吉年：{(sc.key_years?.['吉年'] || []).join('、') || '无'}　｜　
                险年：{(sc.key_years?.['险年'] || []).join('、') || '无'}
              </div>
              <div className="bj-dayun-sub">
                原局底盘：
                {d === 'ganqing'
                  ? `配偶星${sc.yuanju?.['配偶星']?.['五行'] || '—'}（${sc.yuanju?.['配偶星']?.['喜忌'] || '—'}）· 夫妻宫日支${sc.yuanju?.['夫妻宫']?.['日支'] || '—'}·${sc.yuanju?.['夫妻宫']?.['十神'] || '—'} · 桃花${sc.yuanju?.['桃花']?.['支'] || '—'}`
                  : (sc.yuanju?.['结构'] || []).filter((s: any) => s['状态'] !== '未成').map((s: any) => `${s['结构']}${s['状态']}`).join(' · ') || '无成立结构'}
              </div>
              <div className="bj-dayun-table-wrap">
                <table className="bj-dayun-table">
                  <thead><tr>
                    <th>年份</th><th>干支</th><th>十神·五行·喜忌</th><th>大运（关系）</th><th>与原局关系</th><th>成局</th><th>神煞</th><th>标志</th>
                  </tr></thead>
                  <tbody>
                    {(sc.year_rows || []).map((r: any, i: number) => (
                      <tr key={i}>
                        <td>{r.note ? r.year : `${r.year}（${r.age}岁）`}</td>
                        <td>{r['干支'] || '—'}</td>
                        <td>{r.note ? '—' : `干${r['干十神']}(${r['干五行']}·${r['干喜忌']})／支${r['支十神']}(${r['支五行']}·${r['支喜忌']})`}</td>
                        <td>{r.note ? '—' : `${r['大运'] || ''}${(r['大运关系'] || []).length ? '（' + r['大运关系'].join('、') + '）' : ''}`}</td>
                        <td>{r.note ? '—' : (r['原局关系'] || []).map((x: any) => `${x['柱']}${x['干支']}${x['关系'].join('、')}`).join('；') || '—'}</td>
                        <td>{r.note ? '—' : (r['成局'] || []).join('、') || '—'}</td>
                        <td>{r.note ? '—' : (r['神煞'] || []).join('、') || '—'}</td>
                        <td>{r.note ? r.note : Object.entries(r).filter(([k]) => !['year', 'age', '干支', '干十神', '支十神', '干五行', '支五行', '干喜忌', '支喜忌', '大运', '大运关系', '原局关系', '成局', '神煞'].includes(k)).map(([k, v]) => (v === true ? k : `${k}=${v}`)).join('；') || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {loading === d && !r.aiText && (
              <div className="bj-dayun-loading">AI 详批生成中…（内容较长，约需 30–120 秒）</div>
            )}
            {r.aiText && (
              <div className="bj-dayun-ai">
                <div className="bj-dayun-ai-note">AI 详批（格式对齐《全年命理总览》成品）：确定性部分由程序计算；具体事件、评分、标题为 AI 推断（无逐字书证、不可复现），仅供参考，请勿迷信。</div>
                <MarkdownLite text={r.aiText} />
                {r.verify && <div className="bj-dayun-verify">{r.verify}</div>}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
