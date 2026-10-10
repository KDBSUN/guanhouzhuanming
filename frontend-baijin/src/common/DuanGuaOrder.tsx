/**
 * 断卦次序（梅花体系）
 * ============================================================
 * 按《梅花易数·占卜总诀》的次序，把这一卦的信息依次摆出来：
 *   ① 看爻辞（断吉凶）        底本 L1622
 *   ② 看体用（论五行生克）    底本 L1624
 *   ③ 看克应（外应）          底本 L1626
 *   ④ 看应期（成卦数定迟速）  底本 L1628；行/立/坐的算式在 L940（白话 L946）
 * 只放代码算出来的数据与结论，不抄书；每步标出处行号，引文逐字摘自
 * books/meihua/梅花易数.txt（行号即该文件行号，可回源核对）。
 *
 * 移植来源（2026-09-22）：旧前端 frontend/src/meihua/MeihuaPage.tsx 的 .mh-order 四步。
 * 按站长要求，第③步「看克应」新旧结合：旧前端的三要十应判据总表 ＋ 新前端的
 * WaijingBlock（外应配卦与内外合断，走 /api/meihua/waijing）。
 * 旧前端那句三要释义（"耳听其音知吉凶，目见其形知善恶，心思其理知祸福"）在底本里
 * **查无此文**（已 grep：耳听其音／目见其形／心思其理 均 0 命中），故不上屏，
 * 改用底本原文 L2016 与 L2058。
 */
import { useState } from 'react'
import WaijingBlock from './WaijingBlock'
import QuoteRef from './QuoteRef'
import { wxClass } from '../api/gua'
import type { MeihuaGuaData, YingqiItem } from '../api/types'

/** 体用关系 → 吉凶字样（与术语库校正口径一致，断语据《体用总诀》） */
const RELATION_LABEL: Record<string, string> = {
  用生体: '吉', 体克用: '诸事吉', 比和: '吉', 体生用: '泄气', 用克体: '凶',
}

/**
 * 体用关系的白话（从 MeihuaView 移过来，避免两处各存一份）。
 * 生克术语用户不一定懂，这里直接说"对你意味着什么"。
 */
const RELATION_PLAIN: Record<string, string> = {
  用生体: '外在环境在滋养你：这件事的条件对你有利，顺势做即可。',
  体克用: '你能掌控局面，但要花力气：事可成，需要你主动推进。',
  比和: '体用同类、势均力敌：多半平顺，按部就班即可。',
  体生用: '你在消耗自己去成全这件事：容易付出多于回报，注意留力，别过度投入。',
  用克体: '外部在压制你：宜守不宜攻，先避其锋，等条件变化再动。',
}

/** 生我者（生体之五行）／克我者（克体之五行） */
const SHENG_TI: Record<string, string> = { 金: '土', 水: '金', 木: '水', 火: '木', 土: '火' }
const KE_TI: Record<string, string> = { 金: '火', 水: '土', 木: '金', 火: '水', 土: '木' }

/** 体用之间的方向：谁作用于谁 */
function arrowOf(relation: string): string {
  switch (relation) {
    case '用生体': return '←生'
    case '体生用': return '生→'
    case '用克体': return '←克'
    case '体克用': return '克→'
    default: return '↔比和'
  }
}

export default function DuanGuaOrder({ gua, innerNet, onAskAi }: {
  gua: MeihuaGuaData
  /** 内卦净档（顺/平/逆），来自命卦校验；没有就留空 */
  innerNet?: string
  /** 让 AI 就某条外应细讲（走追问流，不重新起卦） */
  onAskAi: (omen: string[], chosen: Record<string, string>) => void
}) {
  const my = gua.moving_yao
  const ti = gua.tiyong
  const qi = gua.qi_info
  const yq = gua.yingqi
  const zhu = my?.yaoci_zhu
  /** 己身动静：行则半之、立用本数、坐则倍之（底本 L940） */
  const [motion, setMotion] = useState<'行' | '立' | '坐'>('立')
  /** 横排日期里被点开的那一天（其判定依据默认收起，点开才显示） */
  const [selDate, setSelDate] = useState('')

  const st = (wx?: string) => (wx && qi?.wuxing_status?.[wx]) || '—'
  const shengTi = SHENG_TI[ti?.ti_wuxing] || ''
  const keTi = KE_TI[ti?.ti_wuxing] || ''
  const strong = (wx: string) => st(wx) === '旺' || st(wx) === '相'

  const days = (arr?: YingqiItem[]) => (arr || []).filter((d) => d && d.date)

  return (
    <div className="mo">
      <div className="bz-head">
        <h2>断卦次序</h2>
        <span className="rule" />
        <span className="aside">《占卜总诀》：爻辞 → 体用 → 克应 → 己身动静</span>
      </div>

      <details className="mo-src">
        <summary>四步次序的底本原文（《梅花易数·占卜总诀》L1622–L1628）</summary>
        <div className="mo-src-body">
          <p><i>L1622</i>「大抵占卜之法，成卦之后，先看《周易》爻辞，以断吉凶。如乾卦初九“潜龙勿用”，则诸事未可为，宜隐伏之类；九二“见龙在田，利见大人”，则宜谒见贵人之类。余皆仿此。」</p>
          <p><i>L1624</i>「次看卦之体用，以论五行生克。体用即动静之说。体为主，用为事。应用生体及比和，则吉，体生用及克体，则不吉。」</p>
          <p><i>L1626</i>「又次看克应。如闻吉说见吉兆，则吉；闻凶说见凶兆，则凶。见圆物，事易成；见缺物，事终毁之类。」</p>
          <p><i>L1628</i>「复验己身之动静。坐则事应迟，行则事应速，走则愈速，卧则愈速之类。数者既备，可尽占卜之道，必须以易卦为主，克应次之。俱吉则大吉，俱凶则大凶，有凶有吉，则详审卦辞，及克用体应之类。以断吉凶也，要在圆机，不可执。」</p>
          <p className="mo-src-note">行号为 books/meihua/梅花易数.txt 的行号，可逐条回源核对。</p>
        </div>
      </details>

      {/* ---------- ① 看爻辞 ---------- */}
      <div className="mo-step">
        <span className="mo-no">一</span>
        <div className="mo-body">
          <div className="mo-name">
            看爻辞（断吉凶）
            <span className="mo-cite">《占卜总诀》L1622</span>
          </div>

          <div className="mo-line">
            第 <b>{my?.position}</b> 爻动
            <span className="mo-dim">（{my?.is_yang ? '阳变阴' : '阴变阳'}）</span>
          </div>
          {gua.ben_gua?.guaci && (
            <div className="mo-line">
              <b>卦辞</b>　{gua.ben_gua.guaci}
            </div>
          )}
          {gua.ben_gua?.daxiang && (
            <div className="mo-line mo-dim"><b>象曰</b>　{gua.ben_gua.daxiang}</div>
          )}
          {my?.yaoci && (
            <div className="mo-yaoci"><b>动爻爻辞</b>　{my.yaoci}</div>
          )}

          {zhu?.notes?.length ? (
            <div className="mo-zhu">
              <div className="mo-zhu-head">
                注释
                <span className="mo-cite">{zhu.src || '《周易》译注本'}</span>
              </div>
              <div className="mo-zhu-list">
                {zhu.notes.map((n, i) => (
                  <div className="mo-zhu-item" key={i}>
                    {n.word ? <b className="mo-zhu-word">{n.word}</b> : null}
                    <span>{n.text}</span>
                  </div>
                ))}
              </div>
              <div className="mo-zhu-usage">
                爻辞是象的语言：与卦象、外应相合者，可拈其中一二字为验证、点睛，不必整句照搬；
                没有卦象或外应支持时，单凭爻辞某一字不下断。
                <details className="mo-proof">
                  <summary>书证与占例（逐字摘自底本）</summary>
                  <div className="mo-proof-item">
                    《占卜总诀》L1622：「大抵占卜之法，成卦之后，<b>先看《周易》爻辞，以断吉凶</b>。」
                    ——这就是次序里的第一步。
                  </div>
                  <div className="mo-proof-item">
                    《占物类例》L3108：「凡看物数，看其成卦，<b>观其爻辞</b>。如得乾，曰“潜龙勿用”，
                    乃曰“不可用之物”；“见龙在田”，乃曰“田中之物”。」——逐词往物象上推。
                  </div>
                  <div className="mo-proof-item">
                    鸡悲鸣占 L976–978：小畜六四「有孚，<b>血去</b>惕出，无咎」，只拈「血去」二字，
                    合卦中巽木离火之烹饪象，断曰「此鸡十日当烹」。
                  </div>
                  <div className="mo-proof-item">
                    同类：泰之初九「<b>拔茅连茹</b>，以其汇」断为连根草木（L3186）；
                    「<b>鼎玉铉</b>，大吉」断为已破的玉环（L3188）。
                  </div>
                  <div className="mo-proof-item">
                    孤证不立 L1678：「凡占卜决断，固以体用为主，然有不拘体用者。……盖用《易》断卦，
                    <b>当用理胜处验之，不可拘于执一也</b>。」——占例里的爻辞都是与卦象或外应相合才成断
                    （牛哀鸣占：爻辞「舆尸」＋外应哀鸣）。
                  </div>
                </details>
              </div>
            </div>
          ) : (
            <div className="mo-line mo-dim">
              这一爻没有收录注释（后端无数据时返回 null，页面不代拟字义）。
            </div>
          )}
        </div>
      </div>

      {/* ---------- ② 看体用 ---------- */}
      <div className="mo-step">
        <span className="mo-no">二</span>
        <div className="mo-body">
          <div className="mo-name">
            看体用（论五行生克）
            <span className="mo-cite">《占卜总诀》L1624</span>
          </div>

          <div className="mo-tiyong">
            <span className={wxClass(ti?.ti_wuxing)}>体 {ti?.ti_wuxing}</span>
            <span className="mo-arrow">{arrowOf(ti?.relation || '')}</span>
            <span className={wxClass(ti?.yong_wuxing)}>用 {ti?.yong_wuxing}</span>
          </div>
          <div className="mo-rel">
            {ti?.relation} · {RELATION_LABEL[ti?.relation || ''] || ''}
          </div>
          {ti?.relation_desc && <div className="mo-line">{ti.relation_desc}</div>}
          {RELATION_PLAIN[ti?.relation || ''] && (
            <div className="mo-plain">{RELATION_PLAIN[ti?.relation || '']}</div>
          )}
          <div className="mo-dim mo-line">
            体为主、用为事：动爻所在之卦为用，另一卦为体（引擎按此机械判定）。
          </div>

          {/* 卦气衰旺（《梅花易数·衰旺论》L2416）：体用最要紧的旁证，归在这一步 */}
          {qi && (
            <div className="mo-in">
              <div className="mo-in-title">卦 气 衰 旺</div>
              <div className="mo-line mo-dim">
                起卦时令：{qi.lunar} · {qi.season} · 日辰 {qi.day_ganzhi}
                （{qi.day_zhi}属{qi.day_zhi_wuxing}）
              </div>
              <div className="qi-grid">
                {(['金', '木', '水', '火', '土'] as const).map((w) => {
                  const s = qi.wuxing_status?.[w] || '—'
                  return (
                    <span className={`qi-cell ${s === '旺' ? 'wang' : s === '死' || s === '囚' ? 'si' : ''}`} key={w}>
                      <b>{w}</b><span>{s}</span>
                    </span>
                  )
                })}
              </div>
              <div className="mo-verdict">
                <p>
                  体卦{ti?.ti_wuxing}卦气{st(ti?.ti_wuxing)}——
                  {strong(ti?.ti_wuxing || '')
                    ? '当令有力，根基稳固，气旺逢生则吉'
                    : '气衰力弱，逢克则其凶甚，宜守不宜攻'}；
                  用卦{ti?.yong_wuxing}卦气{st(ti?.yong_wuxing)}。
                </p>
                {shengTi && keTi && (
                  <p>
                    生体之{shengTi}卦气{st(shengTi)}（{strong(shengTi) ? '旺相，助力可期' : '不旺，助力有限'}），
                    克体之{keTi}卦气{st(keTi)}（{strong(keTi) ? '旺相，须防其凶' : '衰微，其害有限'}）。
                  </p>
                )}
              </div>
              <div className="mo-cite-block">
                底本 L2416：「凡占卜，体卦宜盛旺。气旺而又逢生则吉，重遇克则凶。若体衰而逢克，则其凶甚矣。
                体衰而有生体之卦，则衰稍解。大抵体之卦宜旺。生体之卦气亦宜旺，克体之卦气宜衰。
                此心易论衰旺之决也。」
                <QuoteRef k="梅花易数·心易衰旺诀" />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ---------- ③ 看克应（新旧结合） ---------- */}
      <div className="mo-step">
        <span className="mo-no">三</span>
        <div className="mo-body">
          <div className="mo-name">
            看克应（外应）
            <span className="mo-cite">《占卜总诀》L1626</span>
          </div>

          {/* 判据总表：三要十应（旧前端移植，逐条与底本核对） */}
          <details className="mo-sanyao">
            <summary>三要十应（这一步的判据总表）</summary>
            <div className="mo-sanyao-body">
              <p>
                <b>三要</b>（L2016）：「三要之妙，在于运耳、目、心三者之虚灵，俾应于事物也。
                耳之聪，目之明，吾心实总乎聪明。」又 L2058：「古人总结了用眼观、耳听以下几个方面，
                获取外应，然后用心思来总结判断。」
              </p>
              <p>
                <b>十应</b>（L3206）：「盖“十应”之说，有正应、互应、变应、方应、日应、刻应、外应、
                天时应、地理应、人事应，所谓十应也。」
              </p>
              <ul className="mo-shiying">
                <li><b>正应</b>（L3210）：即体用二卦决吉凶。</li>
                <li><b>互应</b>（L3212）：即互卦中决吉凶。</li>
                <li><b>变应</b>（L3214）：即变卦中决吉凶。</li>
                <li><b>方应</b>（L3216）：以体为主，看来占之人在何方位上；宜生体卦，又宜与体比和则吉，如克体卦则凶，如体卦生之，亦不吉矣。</li>
                <li><b>日应</b>（L3218）：以体卦为主，看所占属何卦，及体卦与本日衰旺如何。</li>
                <li><b>刻应</b>（L3220）：即「三要」之诀也。占卜之顷，随所闻所见吉凶之兆，以为吉凶之应。</li>
                <li><b>外应</b>（L3222）：外卦之应也。占卜之际，偶见外物之来者，即看其物属何卦。如见老人、马、金玉圆物，得乾；见老妇、牛、土瓦物，得坤之类。</li>
                <li><b>天时应</b>（L3226）：占卜之际，晴明为离，雨雪为坎，风为巽，雷为震。</li>
                <li><b>地理应</b>（L3228）：在竹林间为震、巽之地；在江河溪涧池沼之上为坎；在五金之处为乾、兑之乡；在窑灶、炉火之所为离；在土瓦之所为坤、艮。</li>
                <li><b>人事应</b>（L3230）：占卜之际，偶遇人事之吉为吉，偶遇人事之凶为凶。</li>
              </ul>
              <p>
                <b>常见外应</b>（皆出底本）：鹊报喜、鸦报灾，且须审其向背——「鸦飞适来，其灾将至；
                鸦飞而去，则灾已过去」（L2472）·「云开见日，事必争辉；烟雾障空，物当失色」（L2078）·
                「水流而事通，土积而事滞」（L2086）·「见圆物，事易成；见缺物，事终毁」（L1626）·
                见老人属乾、见老妇属坤（L3222）·闻笑语主有吉庆之事、遇哭泣主有悲愁之事（L3230）。
              </p>
            </div>
          </details>

          {/* 外应参断（新前端原有）：配卦 → 与体卦论生克比和 → 内外合断 */}
          <WaijingBlock gua={gua} innerNet={innerNet} onAskAi={onAskAi} />
        </div>
      </div>

      {/* ---------- ④ 看应期 ---------- */}
      <div className="mo-step">
        <span className="mo-no">四</span>
        <div className="mo-body">
          <div className="mo-name">
            看应期（成卦数定迟速）
            <span className="mo-cite">《占卜总诀》L1628 · 算式 L940（白话 L946）</span>
          </div>

          {yq && yq.cheng_gua_zong_shu ? (
            <>
              <div className="mo-line">主体此刻是动是静？</div>
              <div className="slip-row">
                {(['行', '立', '坐'] as const).map((k) => (
                  <button type="button" key={k} className={`slip ${motion === k ? 'active' : ''}`}
                    onClick={() => { setMotion(k); setSelDate('') }}>
                    {k === '行' ? '行走' : k === '立' ? '站立' : '坐着'}
                  </button>
                ))}
              </div>
              <div className="mo-result">
                成卦数 {yq.cheng_gua_zong_shu}（上卦 {yq.shang_shu} 数＋下卦 {yq.xia_shu} 数）→
                {motion === '行' ? '行走则半之（应速）' : motion === '立' ? '站立用本数（半迟半速）' : '坐着则加倍（应迟）'}：
                <b>{motion === '行' ? yq.kuai : motion === '立' ? yq.cheng_gua_zong_shu : yq.huan}</b>
              </div>
              <div className="mo-cite-block">
                底本 L940：「又凡占卜，克应之期，看自己之动静，以决事之迟速，故行则应速，以遂成卦之数，
                可中分而取其半也。坐则事应于迟，当倍其成卦之数而定之也；立则半迟半速，止以成卦之数定之可也。
                虽然如是，又在变通，如占牡丹及观梅之类，则二花皆朝夕之故，岂特成数之久也。」
              </div>
              <div className="mo-dim mo-line">
                上面三个数取自后端确定性计算（行＝{yq.kuai}、立＝{yq.cheng_gua_zong_shu}、坐＝{yq.huan}），
                与交给 AI 的应期材料同源，不带日期单位。
              </div>

              {/* 按卦栏（书证）：三类分组（助体卦=生体、同体卦=比和、克体）＋ 吉凶并见单列。
                  日期做成横排长方形，可左右滚动；每条的判定依据默认收起，点某一天在下方展开。
                  窗口绑定动静：行/立/坐各自的天数（后端已把 6.5 这类小数进一，yingqi.py:179）。
                  「按最终处方」栏属命局改方后的工程口径，归下方「结合八字」区，此处不列。 */}
              {(() => {
                const span = motion === '行' ? (yq.kuai || 0)
                  : motion === '立' ? (yq.cheng_gua_zong_shu || 0)
                  : (yq.huan || 0)
                const t0 = yq.start ? new Date(yq.start + 'T00:00:00').getTime() : null
                const inWin = (d: YingqiItem) => {
                  if (!t0) return true
                  const t = new Date(d.date + 'T00:00:00').getTime()
                  return Math.round((t - t0) / 86400000) >= 0
                    && Math.round((t - t0) / 86400000) < span
                }
                const groups = [
                  { name: '助体卦 · 生体当值（吉期）', items: days(yq.keyi).filter(inWin), tone: 'good' },
                  { name: '同体卦 · 比和当值（吉期）', items: days(yq.bihe).filter(inWin), tone: 'good' },
                  { name: '克体 · 克体之五行当值（须防）', items: days(yq.xianri).filter(inWin), tone: 'warn' },
                  { name: '吉凶并见（同日两逢，须详理）', items: days(yq.jian).filter(inWin), tone: 'mixed' },
                ].filter((g) => g.items.length > 0)
                const total = groups.reduce((n, g) => n + g.items.length, 0)
                return (
                  <>
                    <div className="mo-line">
                      窗口：{motion === '行' ? '行走则半之' : motion === '立' ? '站立用本数' : '坐着则加倍'}
                      ＝ {span} 天 → 下面只列这 {span} 天内过线的日子，共 {total} 天。
                      左右滑动查看；点某一天展开它的判定依据。
                    </div>
                    {total === 0 ? (
                      <div className="mo-line mo-dim">
                        这 {span} 天的窗口内没有过线（四支加权分 ≥ 0.45）的日子。
                        后端扫描窗为 {Math.max(yq.huan || 0, 16)} 天，可换「站立／坐着」放大窗口再看。
                      </div>
                    ) : (
                      <div className="date-strip">
                        {groups.map((g) => (
                          <div className="date-group" key={g.name}>
                            <div className="date-group-h">{g.name}<i>{g.items.length}</i></div>
                            <div className="date-group-row">
                              {g.items.map((d) => (
                                <button type="button" key={g.name + d.date}
                                  className={`date-cell tone-${g.tone} ${selDate === d.date ? 'sel' : ''}`}
                                  onClick={() => setSelDate(selDate === d.date ? '' : d.date)}>
                                  <b>{d.date.slice(5)}</b>
                                  <span>{d.ganzhi}</span>
                                  <i>{d.kind} · {d.wx}</i>
                                </button>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {selDate && (() => {
                      const all = [...days(yq.keyi), ...days(yq.bihe), ...days(yq.xianri), ...days(yq.jian)]
                      const hit = all.find((d) => d.date === selDate)
                      return hit ? (
                        <div className="date-detail">
                          <b>{hit.date}（{hit.ganzhi}）· {hit.kind}</b>　{hit.reason}
                        </div>
                      ) : null
                    })()}
                  </>
                )
              })()}
              <div className="mo-cite-block">
                {/* src 由后端给（yingqi.py:28 SRC_MH），逐个做成可点开核对原文的出处签 */}
                依据：{(yq.src || []).map((s, i) => (
                  <span key={s}>{i > 0 ? '、' : ''}<QuoteRef k={s} /></span>
                ))}
                　{yq.note}
              </div>
            </>
          ) : (
            <div className="mo-line mo-dim">后端未返回应期数据（yingqi 为空），这一步无从计算。</div>
          )}
        </div>
      </div>

      {/* ---------- 总断 ---------- */}
      <div className="mo-sum">
        <b>总断</b>（《占卜总诀》L1628）：「数者既备，可尽占卜之道，必须以易卦为主，克应次之。
        俱吉则大吉，俱凶则大凶，有凶有吉，则详审卦辞，及克用体应之类。以断吉凶也，要在圆机，不可执。」
      </div>
    </div>
  )
}
