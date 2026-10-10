// ============================================================
// 术语知识地图抽取器（Node）
// 把 4 份 HTML 里内嵌的 JS 数据字面量原样 eval 出来，归一化为统一结构，
// 并做完整性检查（悬空关联 / 重名 / 计数）。
// 用法： node extract_term_maps.mjs [输出目录]
// ============================================================
import fs from 'node:fs'
import path from 'node:path'

const OUT_DIR = process.argv[2] || path.resolve(process.cwd(), 'data')
const SRC = {
  liuyao: 'D:\\360Downloads\\六爻术语知识地图（补充版）.html',
  meihua_rich: 'D:\\360Downloads\\tabbit-code.html',            // 结构最好（id/别名/搜索）
  meihua_v1: 'D:\\360Downloads\\梅花易数术语知识地图 (1).html',   // 含占例与应期
  meihua_v0: 'D:\\360Downloads\\梅花易数术语知识地图.html',       // 含篇目与书论
}

const repairStats = []
const CJK = '\\u4e00-\\u9fff\\u3000-\\u303f\\uff00-\\uffef'

function readLiteral(file, startMark, endMark) {
  const src = fs.readFileSync(file, 'utf8')
  const s = src.indexOf(startMark)
  if (s < 0) throw new Error(`未找到起始标记 ${startMark} :: ${file}`)
  const e = src.indexOf(endMark, s)
  if (e < 0) throw new Error(`未找到结束标记 ${endMark} :: ${file}`)
  let literal = src.slice(s + startMark.length, e).trim().replace(/;\s*$/, '')
  // 修复：中文文本里混入的未转义英文双引号（会令整个 <script> 语法错误、页面失效）
  let repaired = 0
  literal = literal.replace(new RegExp(`(?<=[${CJK}])\\s*"\\s*(?=[${CJK}])`, 'g'), (m) => {
    repaired++
    return m.replace('"', '\\"')
  })
  if (repaired) repairStats.push({ file: path.basename(file), repaired })
  try {
    return new Function('return ' + literal)()
  } catch (err) {
    const m = /<anonymous_script>:(\d+)/.exec(err.stack || '')
    const line = m ? literal.split('\n')[Number(m[1]) - 1] : ''
    throw new Error(`${path.basename(file)} 数据字面量仍无法解析：${err.message}\n  位置行：${String(line).slice(0, 160)}`)
  }
}

// —— 结构一：{分类:[[名称,一句话,详解,关联串], ...]} ——
function parseArrayStyle(file, system) {
  const D = readLiteral(file, 'const D=', 'const cats=Object.keys(D)')
  const cats = [], terms = []
  Object.keys(D).forEach((cat, ci) => {
    cats.push({ name: cat, order: ci })
    D[cat].forEach((t, ti) => {
      terms.push({
        cat, order: ti,
        name: String(t[0] || '').trim(),
        alias: '',
        role: String(t[1] || '').trim(),
        detail: String(t[2] || '').trim(),
        related: String(t[3] || '').split('|').map((x) => x.trim()).filter(Boolean),
      })
    })
  })
  return { file, system, cats, terms }
}

// —— 结构二：{CATS:[{id,name,desc}], TERMS:[{id,cat,name,alias,pos,detail,rel:[id]}]} ——
// id 修复：源文件有 6 处 rel 写成 "wanwu"（TERMS 中并不存在该 id），按上下文实指「八卦万物属类」
const ID_FIX = { wanwu: 'baguaXiangli2' }

function parseRichStyle(file, system) {
  const CATS = readLiteral(file, 'const CATS = ', 'const TERMS = ')
  const TERMS = readLiteral(file, 'const TERMS = ', 'const byId')
  const byId = {}
  TERMS.forEach((t) => { byId[t.id] = t })
  const cats = CATS.map((c, i) => ({ name: c.name, order: i, desc: c.desc || '', id: c.id }))
  const catName = {}
  cats.forEach((c) => { catName[c.id] = c.name })
  const terms = TERMS.map((t, i) => ({
    cat: catName[t.cat] || t.cat,
    order: i,
    name: String(t.name || '').trim(),
    alias: String(t.alias || '').trim(),
    role: String(t.pos || '').trim(),
    detail: String(t.detail || '').trim(),
    related: (t.rel || []).map((r) => (byId[r] ? byId[r].name : byId[ID_FIX[r]] ? byId[ID_FIX[r]].name : `!${r}`)),
  }))
  return { file, system, cats, terms }
}

// —— 名称归一（用于跨文件合并与关联解析）：去掉括注，统一顿号/中点/空格 ——
function normName(s) {
  return String(s)
    .replace(/[（(][^）)]*[）)]/g, '')
    .replace(/[\s、·,，/／]+/g, '')
    .trim()
}

function check(parsed) {
  const names = new Set(parsed.terms.map((t) => normName(t.name)))
  const dangling = [], dup = []
  const seen = new Map()
  parsed.terms.forEach((t) => {
    const n = normName(t.name)
    if (seen.has(n)) dup.push(t.name)
    seen.set(n, t.name)
    t.related.forEach((r) => {
      const rn = normName(r)
      if (!rn || !names.has(rn)) dangling.push({ from: t.name, to: r })
    })
  })
  return {
    file: path.basename(parsed.file),
    systems: parsed.system,
    cats: parsed.cats.length,
    terms: parsed.terms.length,
    perCat: parsed.cats.map((c) => `${c.name}:${parsed.terms.filter((t) => t.cat === c.name).length}`),
    duplicateNames: dup,
    danglingRelations: dangling,
  }
}

const files = Object.entries(SRC).map(([key, file]) =>
  key === 'meihua_rich' ? { key, parsed: parseRichStyle(file, 'meihua') } : { key, parsed: parseArrayStyle(file, 'liuyao' === key ? 'liuyao' : 'meihua') })

const report = files.map((f) => ({ key: f.key, ...check(f.parsed) }))
fs.mkdirSync(OUT_DIR, { recursive: true })
fs.writeFileSync(path.join(OUT_DIR, 'term_maps_raw.json'),
  JSON.stringify(Object.fromEntries(files.map((f) => [f.key, f.parsed])), null, 1), 'utf8')
fs.writeFileSync(path.join(OUT_DIR, 'term_maps_check.json'), JSON.stringify(report, null, 1), 'utf8')

console.log('=== 抽取结果 ===')
report.forEach((r) => {
  console.log(`\n[${r.key}] ${r.file}`)
  console.log(`  分类 ${r.cats} 个 / 词条 ${r.terms} 条`)
  console.log(`  分布： ${r.perCat.join('  ')}`)
  console.log(`  重名： ${r.duplicateNames.length ? r.duplicateNames.join('、') : '无'}`)
  console.log(`  悬空关联： ${r.danglingRelations.length ? r.danglingRelations.map((d) => `${d.from}→${d.to}`).join('；') : '无'}`)
})
console.log('\n=== 语法修复 ===')
console.log(repairStats.length ? repairStats.map((x) => `${x.file}：修复未转义引号 ${x.repaired} 处`).join('\n') : '无需修复')
