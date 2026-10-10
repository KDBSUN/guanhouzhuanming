import { useState } from 'react'
import { FishTail } from '../art/book'
import { friendlyError } from '../api/client'
import { daliuren, type DaliurenResult } from '../api/daliuren'

/* ============================================================
   大六壬起课 —— 白金银设计系统
   贵人＝甲戊庚牛羊（站长裁定）；月将＝中气交节时刻后换将（站长裁定）；
   九宗门发三传；起课不含断法。数据由后端 /api/leixiang 出
   （起课＋类神取用＋射覆，书证见判据总表第六节）。
   ============================================================ */

const ZHI = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
// 地盘十二宫布局（巳午未申在上，自右向左按地盘序）
const PAN_ROWS: (string | null)[][] = [
  ['巳', '午', '未', '申'],
  ['辰', null, null, '酉'],
  ['卯', null, null, '戌'],
  ['寅', '丑', '子', '亥'],
]

const WENSHI = ['求财', '疾病', '婚姻', '文书', '干贵', '盗贼', '音信行人', '讼狱', '灾病',
  '科场', '武场', '捐纳', '仕宦', '贸易', '田地', '房屋', '山荡', '航海',
  '晴旱', '雨水', '风', '霜雪', '怪异', '争斗', '饮食', '奴婢', '阴私', '妇女']

function nowLocal(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

export default function DaliurenView() {
  const [dt, setDt] = useState(nowLocal())
  const [shizhi, setShizhi] = useState('正时')
  const [wenshi, setWenshi] = useState('求财')
  const [nianzhu, setNianzhu] = useState('')
  const [xingbie, setXingbie] = useState('男')
  const [nianzhu2, setNianzhu2] = useState('')
  const [xingbie2, setXingbie2] = useState('女')
  const [data, setData] = useState<DaliurenResult | null>(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  const run = async () => {
    setLoading(true); setErr('')
    const nz = nianzhu.trim()
    try {
      setData(await daliuren({
        dt,
        shizhi: shizhi === '正时' ? null : shizhi,
        wenshi,
        nianzhu: nz || null,
        xingbie: nz ? xingbie : null,
        nianzhu2: nianzhu2.trim() || null,
        xingbie2: nianzhu2.trim() ? xingbie2 : null,
      }))
    } catch (e) {
      setErr(friendlyError(e))
    } finally {
      setLoading(false)
    }
  }

  const kongs = data ? new Set(data.空亡) : new Set<string>()

  return (
    <div>
      <div className="leaf-head">
        <span className="juan-mark">观候·转明</span>
        <FishTail />
        <span className="juan">大六壬</span>
        <span className="folio">卷八</span>
      </div>
      <div className="juan-title">
        <h1>六壬起课</h1>
        <p className="juan-sub">月将加时演四课 · 九宗门发三传 · 起课不含断法</p>
      </div>

      {/* ---------- 起课表单 ---------- */}
      <div className="register">
        <span className="reg-label">起课时刻</span>
        <div className="param-row">
          <input
            className="mini-input"
            style={{ gridColumn: '1 / -1' }}
            type="datetime-local"
            aria-label="起课时刻"
            value={dt}
            onChange={(e) => { setDt(e.target.value); setErr('') }}
          />
        </div>
        <span className="reg-hint">
          贵人起法＝甲戊庚牛羊 · 月将＝中气交节时刻后换将 · 九宗门发三传；规则逐条见判据总表第六节。
        </span>

        <div className="bz-head">
          <h2>起课参数</h2>
          <span className="rule" />
          <span className="aside">问事类别决定类神取用；年命选填（推本命行年）</span>
        </div>

        <div className="param-row">
          <label className="reg-label">占时（活时可选）</label>
          <select className="select" value={shizhi} onChange={(e) => setShizhi(e.target.value)}>
            <option value="正时">正时（按时刻）</option>
            {ZHI.map((z) => <option key={z} value={z}>{z}时</option>)}
          </select>
        </div>

        <div className="param-row">
          <label className="reg-label">问事（类神取用）</label>
          <select className="select" value={wenshi} onChange={(e) => setWenshi(e.target.value)}>
            {WENSHI.map((w) => <option key={w} value={w}>{w}</option>)}
          </select>
        </div>

        <div className="param-row">
          <label className="reg-label">出生年干支（可选）</label>
          <input
            className="mini-input"
            value={nianzhu}
            placeholder="如 丙子"
            onChange={(e) => setNianzhu(e.target.value)}
          />
          <select className="select" value={xingbie} onChange={(e) => setXingbie(e.target.value)}>
            <option value="男">男</option>
            <option value="女">女</option>
          </select>
        </div>

        <div className="param-row">
          <label className="reg-label">配偶年干支（可选）</label>
          <input
            className="mini-input"
            value={nianzhu2}
            placeholder="如 戊寅"
            onChange={(e) => setNianzhu2(e.target.value)}
          />
          <select className="select" value={xingbie2} onChange={(e) => setXingbie2(e.target.value)}>
            <option value="男">男</option>
            <option value="女">女</option>
          </select>
        </div>
        <span className="reg-hint">出生年干支与性别一起填才推本命行年；配偶年命用于繁昌课。</span>

        <div className="btn-row" style={{ marginTop: 16 }}>
          <button type="button" className="btn" disabled={loading || !dt} onClick={run}>
            {loading ? '起课中…' : '起 课'}
          </button>
        </div>
        {err && <div className="notice notice-err" role="alert"><b>错误</b><span className="n-body">{err}</span></div>}
      </div>

      {data && (
        <div className="sys-zone">
          <div className="sys-zone-head">
            <span className="sys-zone-title">课传盘面</span>
            <span className="sys-zone-sub">天地盘 · 四课 · 三传 · 类神 · 射覆</span>
          </div>

          {/* 课体总览 */}
          <div className="bz-head" style={{ marginTop: 14 }}>
            <h2>课体</h2>
            <span className="rule" />
            <span className="demo-badge">{data.贵人}·{data.贵人顺逆}布</span>
          </div>
          <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>
            <b>{data.日干支}</b>日 · {data.占时}时 · 月将 <b>{data.月将}</b> · 课体 <b>{data.课体}</b>
          </div>
          {data.课体判语 && <div className="d-src">课体：{data.课体判语}</div>}
          {data.年命 && (
            <div className="d-src">
              本命 <b>{data.年命.本命}</b> · 虚岁 {data.年命.虚岁}
              {data.年命.行年 ? <> · 行年 <b>{data.年命.行年干支}</b>（{data.年命.行年}）</> : '（行年需性别）'}
              {data.配偶年命 && <> ｜ 配偶本命 <b>{data.配偶年命.本命}</b> · 行年 <b>{data.配偶年命.行年干支}</b></>}
            </div>
          )}
          {data.附加课体.length > 0 && (
            <div className="qm-panji" style={{ marginTop: 8 }}>
              {data.附加课体.map((x, i) => (
                <span key={i} className="qm-badge">
                  {x.课体}
                  <span className="sr-only">：{x.判语}</span>
                </span>
              ))}
            </div>
          )}

          {/* 毕法赋 */}
          {data.毕法 && data.毕法.length > 0 && (
            <>
              <div className="bz-head" style={{ marginTop: 18 }}>
                <h2>毕法赋条目</h2>
                <span className="rule" />
                <span className="aside">机械可判定子集，只标盘面结构事实</span>
              </div>
              <div className="qm-panji">
                {data.毕法.map((x, i) => (
                  <span key={i} className="qm-badge">
                    {x.法}·{x.名}
                    <span className="sr-only">：{x.判语}</span>
                  </span>
                ))}
              </div>
            </>
          )}

          {/* 类神取用 */}
          {data.类神取用 && (
            <>
              <div className="bz-head" style={{ marginTop: 18 }}>
                <h2>类神取用</h2>
                <span className="rule" />
                <span className="aside">
                  问事「{data.类神取用.问事}」 · 通类天将 <b>{data.类神取用.通类天将}</b>
                </span>
              </div>
              <div className="dlr-leishen">
                {data.类神取用.类神.map((x, i) => (
                  <div className="check-hit" key={i}>
                    <b>{x.名}（{x.类神}）</b>［{x.记号}］ {x.状态.join('；')}
                    {x.与干上.length > 0 && <> ｜ {x.与干上.join('；')}</>}
                  </div>
                ))}
              </div>
              <div className="d-src">只标盘面事实，不代断。{data.类神取用.取类规则}</div>
            </>
          )}

          {/* 射覆 */}
          {data.射覆 && (
            <>
              <div className="bz-head" style={{ marginTop: 18 }}>
                <h2>射覆占物</h2>
                <span className="rule" />
                <span className="aside">多候选，不落单</span>
              </div>
              {data.射覆.线索.map((x, i) => (
                <div className="check-hit" key={i} title={x.据}>
                  <b>{x.层}</b>：{x.候选.join('；')}
                </div>
              ))}
              <div className="d-src">{data.射覆.口径}</div>
            </>
          )}

          {/* 天地盘 + 四课三传 */}
          <div className="bz-head" style={{ marginTop: 18 }}>
            <h2>天地盘 · 四课 · 三传</h2>
            <span className="rule" />
            <span className="aside">上＝天盘支·天将，下＝地盘支</span>
          </div>
          <div className="dlr-main">
            <div className="dlr-pan">
              {PAN_ROWS.map((row, i) => (
                <div key={i} className="dlr-pan-row">
                  {row.map((d, j) => (d === null ? (
                    <div key={j} className="dlr-pan-spacer" />
                  ) : (
                    <div key={j} className="dlr-cell">
                      <div className="dlr-jiang">{data.天将[data.天盘[d]] || '·'}</div>
                      <div className="dlr-tian">{data.天盘[d]}</div>
                      <div className="dlr-di">{d}</div>
                    </div>
                  )))}
                </div>
              ))}
            </div>

            <div className="dlr-side">
              <div className="dlr-sec">四课（一二课＝干，三四课＝支）</div>
              <div className="dlr-sike">
                {([
                  ['一课', data.四课.干上, data.日干支[0], data.天将[data.四课.干上]],
                  ['二课', data.四课.干阴, data.四课.干上, data.天将[data.四课.干阴]],
                  ['三课', data.四课.支上, data.日干支[1], data.天将[data.四课.支上]],
                  ['四课', data.四课.支阴, data.四课.支上, data.天将[data.四课.支阴]],
                ] as [string, string, string, string | undefined][]).map(([name, up, down, jiang], k) => (
                  <div key={k} className="dlr-sike-row">
                    <span className="dlr-sike-name">{name}</span>
                    <span className="dlr-sike-up">{up}{jiang ? <i>（{jiang}）</i> : ''}</span>
                    <span className="dlr-sike-down">{down}</span>
                  </div>
                ))}
              </div>

              <div className="dlr-sec">三传</div>
              <div className="dlr-chuan">
                {data.三传.map((z, k) => (
                  <div key={k} className={`dlr-chuan-cell${kongs.has(z) ? ' kong' : ''}`}>
                    <div className="dlr-chuan-zhi">{z}</div>
                    <div className="dlr-chuan-gan">{data.遁干[k] !== '空' ? `${data.遁干[k]}遁` : '旬空'}</div>
                    <div className="dlr-chuan-qin">{data.六亲[k]}</div>
                    <div className="dlr-chuan-jiang">{data.天将[z] || ''}</div>
                  </div>
                ))}
              </div>
              <div className="d-src">初传 → 中传 → 末传　空亡：{data.空亡.join('、')}（{data.日干支[0]}日旬空）</div>
            </div>
          </div>

          <div className="d-src" style={{ marginTop: 10 }}>
            三传上方为遁干（从日干支六旬上遁，旬空二支无遁干）与六亲（对日干）；四课括号内为乘将。
            {data.书证 || ''}
          </div>
        </div>
      )}
    </div>
  )
}
