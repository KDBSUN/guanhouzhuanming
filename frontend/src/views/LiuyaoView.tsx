import { useCallback, useEffect, useRef, useState } from 'react'
import { FishTail, SealStamp } from '../art/book'
import BaguaProgress from '../art/BaguaProgress'
import { wxClass } from '../api/gua'
import { friendlyError } from '../api/client'
import MarkdownLite from '../common/MarkdownLite'
import ProfileLine from '../common/ProfileLine'
import CheckBlock from '../common/CheckBlock'
import FreeQuotaHint from '../common/FreeQuotaHint'
import QuoteRef from '../common/QuoteRef'
import PagedCards from '../common/PagedCards'
import { classifyYongshen, divine, remedyRecalc, type YongshenDetail } from '../api/liuyao'
import { checkMingju, getProfile, getTier, setTier, type MingjuProfile } from '../api/mingju'
import { fetchRecord, saveRecord, updateRecord } from '../api/records'
import {
  YAO_POS, coinsFromSeed, lineFromCoins, seedFromParams,
  type LineResult, type ThrowParams,
} from '../common/liuyaoSeed'
import type {
  DegradeInfo, LiuyaoGuaData, MingjuCheck, Tier, VerifyInfo,
} from '../api/types'

/* ============================================================
   纳甲六爻 —— 已接后端
   摇杆拖拽（记录释放点、时长、速度）→ 六次成卦 → 排盘（免费）
   → 用神 / 处方五行 / 应期 / 逐爻细看（都是代码算的）
   → 点「AI 断卦」才走流式解读（扣一次额度）
   ============================================================ */

/** 用神下拉：每一项都写清"什么问事取它"（旧版原文），避免用户不知道选哪个 */
const YONGSHEN_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: '自动（按《增删卜易·用神章》识别）' },
  { value: '世', label: '自占 · 我本人（世爻）' },
  { value: '父母', label: '父母 · 长辈、文书、房屋、车船' },
  { value: '官鬼', label: '官鬼 · 功名、官长、丈夫、忧患' },
  { value: '兄弟', label: '兄弟 · 同辈、朋友、竞争、劫财' },
  { value: '子孙', label: '子孙 · 子女晚辈、医药、僧道' },
  { value: '妻财', label: '妻财 · 妻子、钱财、货物财物' },
]

/** 记录副标题：卦名 + 用神/处方（排盘与 AI 回填共用同一套写法） */
function guaSubtitle(g: LiuyaoGuaData | null, q: string): string {
  if (!g) return ''
  const names = `${g.ben_gua?.name || '卦'}${g.bian_gua ? ' → ' + g.bian_gua.name : '（六爻安静）'}`
  const meta = [g.remedy?.yongshen ? `用神${g.remedy.yongshen}` : '', g.remedy?.R ? `补${g.remedy.R}` : '']
    .filter(Boolean).join(' · ')
  return q ? `${names} · ${meta}` : meta
}

/** 摇卦原理解释：让用户明白"为什么要拖拽而不是点按钮" */
const SHAKE_INTRO = '一事一占。先写下你要问的事，然后按住摇杆，拖向任意方向拉满后松手，即为一摇；'
  + '共摇六次，自初爻（最下）至上爻（最上）。神兆机于动——每一次摇动的轨迹、时长与速度都会参与成卦，'
  + '所以请按自己的心意拖，不要为了"摇准"而重复。'

interface Throw {
  params: ThrowParams
  coins: number[]
  line: LineResult
}

export default function LiuyaoView({ initialQuestion = '', replay = null }: {
  initialQuestion?: string
  replay?: Record<string, unknown> | null
}) {
  const [question, setQuestion] = useState(initialQuestion)
  const [throws, setThrows] = useState<Throw[]>([])
  const [tier, setTierState] = useState<Tier>(getTier())
  const [ysDetail, setYsDetail] = useState<YongshenDetail | null>(null)
  const [ysOverride, setYsOverride] = useState('')
  const [gua, setGua] = useState<LiuyaoGuaData | null>(null)
  const [check, setCheck] = useState<MingjuCheck | null>(null)
  const checkRef = useRef<MingjuCheck | null>(null)
  const [aiText, setAiText] = useState('')
  const [degrade, setDegrade] = useState<DegradeInfo | null>(null)
  const [verify, setVerify] = useState<VerifyInfo | null>(null)
  const [error, setError] = useState('')
  const [casting, setCasting] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [profile, setProfile] = useState<MingjuProfile | null>(null)
  const [recalcing, setRecalcing] = useState(false)
  const [msg, setMsg] = useState('')
  /** 每摇一爻先锁定，点「继续」再摇下一爻（防手抖连摇） */
  const [locked, setLocked] = useState(false)
  /** 改判用神后的重解限制：none=还没断过；armed=可按新用神重解一次；used=已用掉 */
  const [rerun, setRerun] = useState<'none' | 'armed' | 'used'>('none')
  /** 进页时从本机恢复过上次摇卦进度 → 显示提示条（站长 2026-10 要求） */
  const [restoredHint, setRestoredHint] = useState(false)
  /** 应期横排日期里被点开的那一天（依据默认收起，点开才显示，与逐日宜忌同款） */
  const [selYqDate, setSelYqDate] = useState('')

  const abortRef = useRef<AbortController | null>(null)
  const resultRef = useRef<HTMLDivElement | null>(null)
  /** 六摇已满后自动排盘的延时：reset 时清掉，防止清盘后旧卦又冒出来 */
  const castTimerRef = useRef<number | null>(null)
  /** 本条记录 id：排盘出来先存，AI 断完回填 */
  const savedRecIdRef = useRef<number | null>(null)
  /** 回放模式：不存新记录、不重新排盘 */
  const replayRef = useRef(false)
  const guaRef = useRef<LiuyaoGuaData | null>(null)
  const aiTextRef = useRef('')
  /** 问句引用：命卦校验 effect 只在卦象变化时跑，不能把 question 列进依赖
      （否则每敲一个字都会重跑校验、多写一行台账），取最新值用这个 ref */
  const questionRef = useRef(question)

  useEffect(() => { guaRef.current = gua }, [gua])
  useEffect(() => { aiTextRef.current = aiText }, [aiText])
  useEffect(() => { questionRef.current = question }, [question])

  useEffect(() => { getProfile().then(setProfile).catch(() => setProfile(null)) }, [])

  /* ---------- 记录回放：用快照还原当时的盘与断语 ---------- */
  useEffect(() => {
    if (!replay) return
    replayRef.current = true
    savedRecIdRef.current = null
    const g = replay.gua_data as LiuyaoGuaData | undefined
    if (g) {
      setGua(g)
      // 爻册从盘里还原（每一爻都带三枚钱的结果），不用重摇
      setThrows(g.lines.map((l) => ({
        params: { x: 0, y: 0, duration: 0, speed: 0 },
        coins: l.coins || [],
        line: { yinYang: l.yin_yang, type: l.type, moving: l.moving, marker: '' },
      })))
    }
    if (typeof replay.ai_text === 'string') setAiText(replay.ai_text)
    if (typeof replay.question === 'string') setQuestion(replay.question)
    if (typeof replay.yongshen === 'string') setYsOverride(replay.yongshen)
    setError('')
    window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120)
  }, [replay])

  /* ---------- 摇卦状态恢复（刷新不丢；回放或带问句进入时不恢复） ---------- */
  useEffect(() => {
    if (initialQuestion || replay) return
    let saved: { v?: number; params?: ThrowParams[]; question?: string; yongshen?: string; rerun?: string; recId?: number }
    try {
      const raw = localStorage.getItem(CAST_KEY)
      if (!raw) return
      saved = JSON.parse(raw)
    } catch { return }
    if (saved?.v !== 1 || !Array.isArray(saved.params) || saved.params.length !== 6) return
    const list: Throw[] = saved.params.map((p) => {
      const seed = seedFromParams(p.x, p.y, p.duration, p.speed)
      const coins = coinsFromSeed(seed)
      return { params: p, coins, line: lineFromCoins(coins) }
    })
    setThrows(list)
    setRestoredHint(true)
    if (typeof saved.question === 'string') setQuestion(saved.question)
    if (typeof saved.yongshen === 'string') setYsOverride(saved.yongshen)
    if (saved.rerun === 'armed' || saved.rerun === 'used') setRerun(saved.rerun)
    if (typeof saved.recId === 'number') {
      savedRecIdRef.current = saved.recId
      /* 断语存在服务器上那条记录里：取回来。
         否则刷新后看着像"从没断过卦"，用户再点一次断卦就白花一次额度。 */
      fetchRecord(saved.recId).then((row) => {
        const t = (row?.payload as { ai_text?: string } | undefined)?.ai_text
        if (typeof t === 'string' && t) setAiText(t)
      }).catch(() => { /* 取不到就算了，不影响摇卦 */ })
    }
    // 恢复后不自动排盘：爻册已显示，点「排盘」按钮即可（免费，且复用原来那条记录）
  }, [initialQuestion, replay])

  const changeTier = (t: Tier) => { setTierState(t); setTier(t) }

  /* ---------- 摇卦状态持久化（刷新不丢） ----------
     写入时机：摇满六爻那一刻；恢复时机：页面加载且不是回放、没带问句。
     存的是六次摇动的物理参数 + 问句 + 用神 + 重解状态，恢复后可重新排盘。 */
  const CAST_KEY = 'bagua_liuyao_cast'
  const persistCast = useCallback((list: Throw[], q: string, override: string, rr: string,
                                  recId: number | null) => {
    try {
      localStorage.setItem(CAST_KEY, JSON.stringify({
        v: 1, params: list.map((t) => t.params), question: q, yongshen: override, rerun: rr,
        // 记下这一卦落到哪条记录上：刷新后重新排盘复用它，不再多出一条重复记录
        recId,
      }))
    } catch { /* 本地存储不可用就算了 */ }
  }, [])

  /** 排盘存完记录后，把记录 id 补写回本地（下次刷新就能认回同一条） */
  const rememberRecId = useCallback((id: number | null) => {
    try {
      const raw = localStorage.getItem(CAST_KEY)
      if (!raw) return
      const obj = JSON.parse(raw) as Record<string, unknown>
      obj.recId = id
      localStorage.setItem(CAST_KEY, JSON.stringify(obj))
    } catch { /* 忽略 */ }
  }, [])

  /* ---------- 排盘（不花 AI） ---------- */
  const cast = useCallback(async (list: Throw[], q: string, override: string) => {
    if (list.length !== 6) return
    /* 同一卦重排（刷新后点「排盘」、或再点一次「排盘」）：
       断语是花过额度的成果，不能因为重看一眼卦就把它抹掉。 */
    const reCast = savedRecIdRef.current != null
    setCasting(true); setError('')
    setGua(null); setCheck(null); setDegrade(null); setVerify(null); setSelYqDate('')
    if (!reCast) { setAiText(''); setRerun('none') }
    let got: LiuyaoGuaData | null = null
    try {
      await divine(q, list.map((t) => t.params), false, (e) => {
        if (e.gua) {
          got = e.gua
          setGua(e.gua)
          window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80)
        }
        if (e.error) setError(e.error)
      }, { yongshenOverride: override })
    } catch (err) {
      setError(friendlyError(err) || '排盘失败')
    } finally {
      setCasting(false)
    }
    if (!got) return
    const g0 = got as LiuyaoGuaData
    /* 落库：排盘一出来先存一条（盘不会丢），AI 断完再按 id 回填断语。
       如果本地记着这一卦的记录 id（刷新后重新排盘），就改那一条，不新增。 */
    if (!replayRef.current) {
      const payload = {
        gua_data: g0, ai_text: reCast ? aiTextRef.current : '',
        question: q, yongshen: override || '', chat: [],
        /* 校验台账的钥匙（2026-10 补，与旧前端一致；校验完成后会在下面补写） */
        log_id: null as number | null,
      }
      const subtitle = guaSubtitle(g0, q)
      let reused = false
      if (savedRecIdRef.current != null) {
        reused = await updateRecord(savedRecIdRef.current, { subtitle, payload })
        if (!reused) savedRecIdRef.current = null
      }
      if (!reused) {
        const row = await saveRecord({
          kind: 'liuyao',
          title: q || (g0.ben_gua?.name || '六爻'),
          subtitle,
          question: q,
          payload,
        })
        savedRecIdRef.current = row?.id ?? null
        rememberRecId(savedRecIdRef.current)
      }
    }
    /* 命卦校验不再在这里调：已移到下面的「盘就位 → 自动校验」effect，
       排盘与回放共用同一路径（见该 effect 的注释）。 */
  }, [])

  useEffect(() => { checkRef.current = check }, [check])

  /* ---------- 命卦校验：盘就位后自动比对命局 ----------
     排盘与回放共用这一条路径：排盘时 setGua 触发；回放时上面的回放 effect 还原盘面，
     这里照跑一次校验，回放视图因此和现时排盘一样有「命卦校验」板块（与梅花同款修法）。
     校验是确定性计算，不花 AI 额度；question 走 questionRef，不列进依赖。 */
  useEffect(() => {
    if (!gua) { setCheck(null); return }
    let cancelled = false
    checkMingju({
      remedy: (gua.remedy || {}) as Record<string, unknown>,
      question: questionRef.current.trim(),
      source: 'liuyao',
    })
      .then((res) => {
        if (!cancelled) setCheck(res)
        /* 校验台账号补写进记录快照（起卦时还没台账号；快照整体回填，不丢其它字段） */
        if (res.log_id && !replayRef.current && savedRecIdRef.current != null) {
          void updateRecord(savedRecIdRef.current, {
            payload: {
              gua_data: gua, ai_text: aiTextRef.current || '',
              question: questionRef.current || '', yongshen: ysOverride || '', chat: [],
              log_id: res.log_id,
            },
          })
        }
      })
      .catch(() => { if (!cancelled) setCheck(null) })
    return () => { cancelled = true }
  }, [gua])

  /* ---------- 摇一爻 ----------
     每摇满一爻先锁定，必须点「继续 · 摇X爻」确认后再摇下一爻——
     防止手一抖连摇两爻，一卦就废了。 */
  const onRelease = useCallback((p: ThrowParams) => {
    if (locked || throws.length >= 6) return
    const seed = seedFromParams(p.x, p.y, p.duration, p.speed)
    const coins = coinsFromSeed(seed)
    const line = lineFromCoins(coins)
    const next = [...throws, { params: p, coins, line }]
    setThrows(next)
    if (next.length === 6) {
      // 刚摇满的六爻是"新的一卦"：记录 id 作废，排盘时新建一条
      persistCast(next, question, ysOverride, rerun, null)
      // 六摇已满：自动排盘（免费），用户随后再决定要不要花钱解卦
      castTimerRef.current = window.setTimeout(() => { setLocked(false); cast(next, question, ysOverride) }, 300)
    } else {
      setLocked(true)
    }
  }, [locked, throws, cast, question, ysOverride, rerun, persistCast])

  const unlock = () => setLocked(false)

  const reset = () => {
    abortRef.current?.abort()
    if (castTimerRef.current != null) { window.clearTimeout(castTimerRef.current); castTimerRef.current = null }
    setThrows([]); setGua(null); setCheck(null); setAiText('')
    setError(''); setDegrade(null); setVerify(null); setYsDetail(null); setYsOverride('')
    setLocked(false); setRerun('none')
    savedRecIdRef.current = null
    try { localStorage.removeItem(CAST_KEY) } catch { /* 忽略 */ }
  }

  /* ---------- 用神预判（纯规则，不花钱） ---------- */
  const predictYongshen = useCallback(async () => {
    const q = question.trim()
    if (!q) { setError('先写下所问之事，才能预判用神'); return }
    try {
      const d = await classifyYongshen(q)
      setYsDetail(d)
      setYsOverride(d.need_confirm || d.confidence !== 'high' ? '' : d.yongshen)
    } catch (err) {
      setError(friendlyError(err) || '用神预判失败')
    }
  }, [question])

  /* ---------- AI 断卦（扣一次额度） ----------
     改判用神后允许按新用神重解一次（armed）；重解完即用掉（used），不再重解。 */
  const interpret = useCallback(async () => {
    if (throws.length !== 6 || thinking || rerun === 'used') return
    setThinking(true); setError(''); setAiText(''); setDegrade(null); setVerify(null)
    const ac = new AbortController()
    abortRef.current = ac
    let acc = ''
    try {
      await divine(question, throws.map((t) => t.params), true, (e) => {
        if (e.text) { acc += e.text; setAiText((prev) => prev + e.text) }
        if (e.gua) setGua(e.gua)
        if (e.degrade) setDegrade(e.degrade)
        const v = e.verify
        if (v) setVerify((prev) => ({ ...prev, ...v }))
        if (e.error) setError(e.error)
      }, { yongshenOverride: ysOverride, signal: ac.signal })
    } catch (err) {
      if ((err as { name?: string }).name !== 'AbortError') setError(friendlyError(err) || '断卦失败')
    } finally {
      setThinking(false)
    }
    /* 真出了断语才算用掉那一次重解机会（半途报错不算） */
    if (acc && rerun === 'armed') {
      setRerun('used')
      persistCast(throws, question, ysOverride, 'used', savedRecIdRef.current)
    }
    /* 断完回填同一条记录（重解也算同一次解读，仍写这一条） */
    if (acc && guaRef.current && !replayRef.current) {
      const payload = {
        gua_data: guaRef.current, ai_text: acc,
        question, yongshen: ysOverride || '', chat: [],
        log_id: checkRef.current?.log_id ?? null,
      }
      if (savedRecIdRef.current != null) {
        // 重解也是同一次解读：写回同一条，副标题里的用神跟着当前状态走
        if (await updateRecord(savedRecIdRef.current, {
          subtitle: guaSubtitle(guaRef.current, question), payload,
        })) return
        savedRecIdRef.current = null
      }
      const row = await saveRecord({
        kind: 'liuyao',
        title: question || (guaRef.current.ben_gua?.name || '六爻'),
        subtitle: `${guaRef.current.ben_gua?.name || ''} · AI 断卦`,
        question,
        payload,
      })
      savedRecIdRef.current = row?.id ?? null
      rememberRecId(savedRecIdRef.current)
    }
  }, [question, throws, thinking, ysOverride, rerun, persistCast, rememberRecId])

  /* ---------- 改判用神 → 重算处方（不重新起卦） ----------
     已经断过语的卦：改判后清空断语，允许按新用神重新解卦一次；
     那一次用掉之后，再改判就只重算处方，不再重解。 */
  const changeYongshen = useCallback(async (v: string) => {
    setYsOverride(v)
    if (!gua || recalcing) return
    setRecalcing(true)
    let next = gua
    try {
      const rm = await remedyRecalc(gua, question, v)
      next = { ...gua, remedy: { ...(gua.remedy || {}), ...rm } }
      setGua(next)
    } catch (err) {
      setError(friendlyError(err) || '重算处方失败')
    } finally {
      setRecalcing(false)
    }
    /* 断语是否保留：没断过语/还能重解一次 → 清空待重解；已经重解过 → 保留原断语 */
    const keepText = rerun === 'used' ? aiText : ''
    if (aiText.trim()) {
      if (rerun !== 'used') {
        setAiText('')
        setRerun('armed')
        setMsg('已改判用神：处方五行已重算，断语已清空——可按新用神重新解卦一次。')
      } else {
        setMsg('已按新用神重新解卦过一次——这一卦不再重解，处方五行已按新用神更新。')
      }
    }
    /* 把改判写进记录：否则记录里留着"旧用神 + 旧断语"，与屏幕上看到的不一致。
       副标题也一起改（里面写着"用神X · 补Y"）。 */
    persistCast(throws, question, v, rerun === 'used' ? 'used' : (aiText.trim() ? 'armed' : rerun),
      savedRecIdRef.current)
    if (!replayRef.current && savedRecIdRef.current != null) {
      await updateRecord(savedRecIdRef.current, {
        subtitle: guaSubtitle(next, question),
        payload: { gua_data: next, ai_text: keepText, question, yongshen: v, chat: [] },
      })
    }
  }, [gua, question, recalcing, aiText, rerun, throws, persistCast])

  const done = throws.length === 6
  const linesTopDown = gua ? [...gua.lines].reverse() : []

  /* 逐爻细看：后端放了两处（remedy.逐爻细看 / remedy.details.各爻），以后者兜底 */
  const perLine = (gua?.remedy as { 逐爻细看?: unknown[] } | undefined)?.['逐爻细看'] as
    | {
      position: number; name: string; 六神: string; 六亲: string; 干支: string; 五行: string
      卦位: string; 角色: string; 动静: string; 旬空: boolean; 月破: boolean; 兽性: string
      断语: { text: string; src: string; kind: string; plain: string }[]
      有专断: boolean; 无专断说明: string
    }[]
    | undefined

  return (
    <div>
      <div className="leaf-head">
        <span className="juan-mark">易占</span>
        <FishTail />
        <span className="juan">纳甲六爻</span>
        <span className="folio">卷二</span>
      </div>
      <div className="juan-title">
        <h1>摇钱纳甲</h1>
        <p className="juan-sub">三枚铜钱摇六次 · 纳甲装卦断吉凶</p>
      </div>

      {/* ---------- 问事 ---------- */}
      <div className="register">
        <span className="reg-label">所问之事</span>
        <textarea
          className="textarea"
          rows={3}
          maxLength={200}
          placeholder="例：下周的合同能签成吗（问什么，决定用神取哪一爻）"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <span className="reg-hint">一事一占 · 用神按《增删卜易 · 用神章》自动取，也可手动改判</span>

        <div className="bz-head">
          <h2>用神</h2>
          <span className="rule" />
          <span className="aside">纯规则预判，不花 AI 额度</span>
        </div>
        <div className="btn-row">
          <button type="button" className="btn-outline" onClick={predictYongshen} disabled={!question.trim()}>
            预判用神
          </button>
          {ysDetail && (
            <span className="hint-line">
              取「{ysDetail.yongshen}」· 把握 {ysDetail.confidence === 'high' ? '高' : ysDetail.confidence === 'medium' ? '中' : '低'}
              {ysDetail.reason ? ` · ${ysDetail.reason}` : ''}
            </span>
          )}
        </div>
        {(ysDetail?.candidates?.length ?? 0) > 1 && (
          <>
            <span className="reg-hint">候选不止一个，选一个更贴合你问的事（改判会重算处方五行）：</span>
            <div className="slip-row">
              {ysDetail!.candidates.map((c) => (
                <button key={c} type="button" className={`slip ${ysOverride === c ? 'active' : ''}`}
                  onClick={() => changeYongshen(c)}>{c}</button>
              ))}
            </div>
          </>
        )}
        <div style={{ marginTop: 10 }}>
          <span className="reg-label">用神（改了会重算处方五行与命局校验；已断过语的卦会清空断语，可按新用神重解一次）</span>
          <div className="btn-row">
            <select className="select" style={{ maxWidth: 320 }} value={ysOverride}
              onChange={(e) => changeYongshen(e.target.value)}>
              {YONGSHEN_OPTIONS.map((o) => (
                <option key={o.value || 'auto'} value={o.value}>{o.label}</option>
              ))}
            </select>
            {recalcing && <span className="hint-line">重算中…</span>}
          </div>
          <span className="reg-hint">
            用神认不准时手动锁定：只影响处方五行与建议，不改变卦象本身。
            还没断卦时改判只重算处方五行；已经断过卦的改判会清空断语，让你按新用神重新解一次——
            这一次用掉之后再改判就只重算处方五行，保留原来那段断语。
          </span>
        </div>

        <div className="bz-head">
          <h2>解读档位</h2>
          <span className="rule" />
          <span className="aside">解卦本身始终完整；档位只决定行动建议给几层：S 一层 / M 两层 / L 三层</span>
        </div>
        <div className="slip-row">
          {(['S', 'M', 'L'] as Tier[]).map((t) => (
            <button key={t} type="button" className={`slip ${tier === t ? 'active' : ''}`} onClick={() => changeTier(t)}>
              {t === 'S' ? 'S · 紧急' : t === 'M' ? 'M · 常规' : 'L · 详批'}
            </button>
          ))}
        </div>
        <ProfileLine profile={profile} />

        {error && <div className="notice notice-err" role="alert"><b>错误</b><span className="n-body">{error}</span></div>}
        {msg && <div className="notice notice-ok" role="status"><b>完成</b><span className="n-body">{msg}</span></div>}
        {degrade && (
          <div className="notice notice-warn" role="status">
            <b>降级</b>
            <span className="n-body">
              {degrade.message}
              {degrade.hint && <span className="n-hint">{degrade.hint}</span>}
            </span>
          </div>
        )}
      </div>

      {/* ---------- 摇卦 ---------- */}
      {restoredHint && (
        <div className="notice notice-warn" role="status" style={{ marginTop: 14 }}>
          <b>提示</b>
          <span className="n-body">
            已恢复上次的摇卦进度（六爻、问句、用神与断语都已还原，不会重复扣额度）。
            想重新起卦，点「重 摇」清空重来。
            <button type="button" className="btn-outline" style={{ marginLeft: 10, padding: '3px 14px', fontSize: 'var(--type-data)' }}
              onClick={() => setRestoredHint(false)}>知道了</button>
          </span>
        </div>
      )}
      <div className="bz-head">
        <h2>摇卦</h2>
        <span className="rule" />
        <span className="aside">{SHAKE_INTRO}</span>
      </div>

      <div className="cast-altar">
        <div className="coin-dish">
          <Joystick onRelease={onRelease} disabled={done || casting || locked} />
          <div className="throw-dots" aria-hidden>
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <span key={i} className={`throw-dot ${throws.length > i ? 'done' : ''}`} />
            ))}
          </div>
          <div className="cast-hint">
            {done
              ? '六摇已毕 · 装卦见下'
              : locked
                ? `第 ${throws.length} 摇已定 · 确认后再摇下一爻`
                : `第 ${throws.length + 1} 摇 · 默念所问，拉满松手`}
          </div>
          {locked && !done && (
            <button type="button" className="btn" style={{ padding: '9px 24px', fontSize: 'var(--type-data)' }} onClick={unlock}>
              继续 · 摇{YAO_POS[throws.length]}
            </button>
          )}
          {gua === null && throws.length > 0 && (
            <button type="button" className="btn-outline" style={{ padding: '6px 18px', fontSize: 'var(--type-data)' }}
              onClick={() => cast(throws, question, ysOverride)} disabled={casting}>
              {casting ? '排盘中…' : done ? '排 盘' : '先 排 盘'}
            </button>
          )}
          <button type="button" className="btn-outline" style={{ padding: '6px 18px', fontSize: 'var(--type-data)' }}
            onClick={reset} disabled={throws.length === 0 || casting}>
            重 摇
          </button>
        </div>

        <div className="throw-ledger">
          {[5, 4, 3, 2, 1, 0].map((i) => {
            const t = throws[i]
            return (
              <div className={`throw-row ${t ? 'done' : 'waiting'}`} key={i}>
                <span>{YAO_POS[i]}</span>
                <span className="mini-coins" aria-hidden>
                  {(t?.coins || [0, 0, 0]).map((c, k) => (
                    <span key={k} className={`mini-coin ${t ? (c === 1 ? 'back' : 'char') : ''}`} />
                  ))}
                </span>
                <span className="val">{t ? t.line.type : '待掷'}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* ---------- 装卦（排盘回来才显示） ---------- */}
      <div ref={resultRef} />
      {gua && (
        <>
          {/* ===== 六爻体系（分区）=====
               区层与梅花体系 / 命卦校验同款：sys-zone 分区壳 + bz-head 小节标题分层，
               把「六爻体系」（古法排盘解读）与下方「命卦校验」（结合八字）一眼分开。 */}
          <div className="sys-zone">
            <div className="sys-zone-head">
              <span className="sys-zone-title">六爻体系</span>
              <span className="sys-zone-sub">《增删卜易》《卜筮正宗》古法：摇卦 · 装卦 · 用神 · 应期</span>
            </div>

            <div className="bz-head" style={{ marginTop: 14 }}>
              <h2>装卦</h2>
              <span className="rule" />
              <span className="demo-badge">
                {gua.time_info.day_ganzhi}日 · {gua.time_info.hour_ganzhi}时 · 旬空 {gua.time_info.xunkong}
              </span>
            </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16, flexWrap: 'wrap', marginBottom: 14 }}>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 24, fontWeight: 700, letterSpacing: '0.14em', color: 'var(--ink)' }}>
              {gua.ben_gua.symbol} {gua.ben_gua.name}
            </span>
            <span className="kai" style={{ fontSize: 'var(--type-note)', color: 'var(--ink-3)', letterSpacing: '0.12em' }}>
              {gua.ben_gua.palace || gua.palace} · {gua.palace_wuxing}
            </span>
            {gua.ben_gua.markers?.map((m) => <SealStamp key={m} tone="gold" label={m}>{m}</SealStamp>)}
            {gua.bian_gua && (
              <>
                <span style={{ color: 'var(--foil-4)', fontSize: 18 }}>→</span>
                <span style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700, color: 'var(--ink)' }}>
                  {gua.bian_gua.symbol} {gua.bian_gua.name}
                </span>
                <span className="kai" style={{ fontSize: 'var(--type-note)', color: 'var(--ink-3)' }}>
                  {gua.bian_gua.palace} · {gua.bian_gua.upper.name}上{gua.bian_gua.lower.name}下
                </span>
              </>
            )}
          </div>

          <div className="book-table" tabIndex={0}>
            <div className="bt-row head">
              <span>六神</span><span>本卦 · 纳甲</span><span>变卦</span><span>爻位</span>
            </div>
            {linesTopDown.map((l) => (
              <div className="bt-row" key={l.position}>
                <span className="bt-liushen">{l.liushen}</span>
                <span className="bt-cell">
                  <span className={wxClass(l.wuxing)}>{l.liuqin}{l.gan}{l.zhi}</span>
                  <span className={`yao-mini ${l.yin_yang === 1 ? '' : 'yin'} wxl-${l.wuxing}`} aria-label={l.yin_yang === 1 ? '阳爻' : '阴爻'}>
                    <i />{l.yin_yang === 0 && <i />}
                  </span>
                  {l.moving && <span className="bt-flag" style={{ color: 'var(--foil-4)', borderColor: 'var(--foil-3)' }}>
                    {l.type}{l.yin_yang === 1 ? '○' : '×'}动
                  </span>}
                  {l.shi && <span className="bt-flag shi">世</span>}
                  {l.ying && <span className="bt-flag">应</span>}
                  {l.xunkong && <span className="bt-flag kong">空</span>}
                  {l.yuepo && <span className="bt-flag" style={{ color: 'var(--ji)', borderColor: 'var(--error-border)' }}>破</span>}
                </span>
                <span className="bt-cell">
                  {l.bian ? (
                    <>
                      <span className={wxClass(l.bian.wuxing)}>{l.bian.liuqin}{l.bian.gan}{l.bian.zhi}</span>
                      {/* 变卦列镜像爻符（2026-10 补，与旧前端一致：阴变阳、阳变阴画在变卦格） */}
                      <span className={`yao-mini ${l.yin_yang === 1 ? 'yin' : ''} wxl-${l.bian.wuxing}`}
                        aria-label={l.yin_yang === 1 ? '变卦阴爻' : '变卦阳爻'}>
                        <i />{l.yin_yang === 1 && <i />}
                      </span>
                    </>
                  ) : <span className="bt-empty">·</span>}
                </span>
                <span className="bt-liushen" style={{ textAlign: 'right' }}>{l.name}</span>
              </div>
            ))}
          </div>

          <div className="d-src" style={{ marginTop: 8 }}>
            起卦时间：{gua.time_info.solar} · 农历{gua.time_info.lunar} ·
            {gua.time_info.year_ganzhi}年 {gua.time_info.month_ganzhi}月 {gua.time_info.day_ganzhi}日 {gua.time_info.hour_ganzhi}时 ·
            日月建：{gua.time_info.month_branch}月 {gua.time_info.day_ganzhi}日
            {gua.gua_shen ? ` · 卦身：${gua.lines[gua.gua_shen - 1]?.name || '—'}` : ''}
            {gua.moving_positions?.length ? ` · 动爻：${gua.moving_positions.map((p) => YAO_POS[p - 1]).join('、')}` : ' · 六爻安静'}
          </div>

          {/* 用神详情 */}
          {gua.remedy?.yongshen && (
            <>
              <div className="bz-head" style={{ marginTop: 18 }}>
                <h2>用神</h2>
                <span className="rule" />
                <span className="aside">
                  {gua.remedy.confidence ? `把握 ${gua.remedy.confidence === 'high' ? '高' : gua.remedy.confidence === 'medium' ? '中' : '低'}` : ''}
                </span>
              </div>
              <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>
                取 <b>{gua.remedy.yongshen}</b>
                {gua.remedy.candidates?.length ? `　候选：${gua.remedy.candidates.join('、')}` : ''}
                <div style={{ marginTop: 6, color: 'var(--ink-3)' }}>{gua.remedy.reason}</div>
                {gua.remedy.matched?.length ? (
                  <div style={{ marginTop: 4, color: 'var(--ink-3)' }}>
                    命中：{gua.remedy.matched.map((m) => `${m.kw}→${m.liuqin}（${m.layer}）`).join('、')}
                  </div>
                ) : null}
                <div className="d-src" style={{ marginTop: 6 }}>
                  取用神的规矩见：<QuoteRef k="增删卜易·用神章" />
                </div>
              </div>
            </>
          )}

          {/* 卦气（建日辰与当令五行五态）：断用神旺衰看这个 */}
          {(() => {
            const d = (gua.remedy?.details || {}) as Record<string, Record<string, unknown>>
            const jd = d['月建日辰'] as { 月建?: string; 月建五行?: string; 日辰?: string; 日辰干支?: string; 日辰五行?: string; 卦气?: Record<string, string> } | undefined
            if (!jd?.卦气) return null
            return (
              <>
                <div className="bz-head" style={{ marginTop: 18 }}>
                  <h2>卦气衰旺</h2>
                  <span className="rule" />
                  <span className="aside">月建 {jd.月建}（{jd.月建五行}）· 日辰 {jd.日辰干支 || jd.日辰}（{jd.日辰五行}）</span>
                </div>
                <div className="qi-grid">
                  {(['金', '木', '水', '火', '土'] as const).map((w) => {
                    const st = jd.卦气?.[w] || '—'
                    return (
                      <span className={`qi-cell ${st.includes('旺') ? 'wang' : st.includes('死') || st.includes('囚') ? 'si' : ''}`} key={w}>
                        <b>{w}</b><span>{st}</span>
                      </span>
                    )
                  })}
                </div>
                <div className="d-src">
                  用神与忌神的旺衰，就以这里的月建、日辰与当令五态为准（旺相者力大，休囚死受制）。
                </div>
              </>
            )
          })()}

          {/* 处方五行 */}
          {gua.remedy?.R && (
            <>
              <div className="bz-head" style={{ marginTop: 18 }}>
                <h2>处方五行</h2>
                <span className="rule" />
                <span className="aside">该补 {gua.remedy.R}</span>
              </div>
              <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>
                {gua.remedy.X && gua.remedy.X !== gua.remedy.R ? <>避：<b>{gua.remedy.X}</b></> : null}
                <div style={{ marginTop: 6, color: 'var(--ink-3)' }}>{gua.remedy.R_reason}</div>
                <div style={{ marginTop: 4, color: 'var(--ink-3)' }}>用神状态：{gua.remedy.state} —— {gua.remedy.state_desc}</div>
              </div>
            </>
          )}

          {/* 应期：日期横排长方形，与命卦校验「逐日宜忌」同款；点某一天展开它的依据 */}
          {gua.yingqi && (
            <>
              <div className="bz-head" style={{ marginTop: 18 }}>
                <h2>应期</h2>
                <span className="rule" />
                <span className="aside">点某天看依据</span>
              </div>
              <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>
                用神：{gua.yingqi.yongshen?.liuqin}{gua.yingqi.yongshen?.ganzhi}（{gua.yingqi.yongshen?.wuxing}）
                {gua.yingqi.yongshen?.moving ? ' · 发动' : ' · 安静'}　判断法：{gua.yingqi.rule}
              </div>
              {(() => {
                const groups: [string, { date: string; ganzhi: string; reason: string }[]][] = [
                  ['值日', gua.yingqi.zhiri],
                  ['逢合', gua.yingqi.fenghe],
                  ['冲日', gua.yingqi.chongri],
                  ['冲空', gua.yingqi.chongkong],
                  ['实破', gua.yingqi.shipo],
                  ['忌神受冲', gua.yingqi.jishen_chong],
                ]
                const all = groups
                  .filter(([, items]) => items && items.length > 0)
                  .flatMap(([label, items]) => items.map((it) => ({ ...it, label })))
                if (all.length === 0) return <div className="d-src">后端未返回应期日期。</div>
                const hit = all.find((it) => `${it.label}${it.date}` === selYqDate)
                return (
                  <>
                    <div className="date-strip">
                      {all.map((it) => (
                        <button
                          type="button"
                          key={`${it.label}${it.date}`}
                          className={`date-cell ${selYqDate === `${it.label}${it.date}` ? 'sel' : ''}`}
                          onClick={() => setSelYqDate(selYqDate === `${it.label}${it.date}` ? '' : `${it.label}${it.date}`)}
                        >
                          <b>{it.date.slice(5)}</b>
                          <span>{it.ganzhi}</span>
                          <i>{it.label}</i>
                        </button>
                      ))}
                    </div>
                    {hit && (
                      <div className="date-detail">
                        <b>{hit.date}（{hit.ganzhi}）· {hit.label}</b>　{hit.reason}
                      </div>
                    )}
                  </>
                )
              })()}
              <div className="d-src">
                依据：{(gua.yingqi.src || []).map((s, i) => (
                  <span key={s}>{i > 0 ? '、' : ''}<QuoteRef k={s} /></span>
                ))}　{gua.yingqi.note}
              </div>
            </>
          )}

          {/* 逐爻细看 */}
          {perLine && perLine.length > 0 && (
            <>
              <div className="bz-head" style={{ marginTop: 18 }}>
                <h2>逐爻细看</h2>
                <span className="rule" />
                <span className="aside">左右翻页 · 一屏一爻</span>
              </div>
              <div className="d-src">
                <b>六亲本也，六兽末也</b>——六神只描述这一爻的情性，吉凶以五行六亲为准。
                角色读法：用神＝所问之事；元神＝生用神者（帮它的）；忌神＝克用神者（坏它的）；
                仇神＝克元神者；世＝自己；应＝对方；闲＝与本事无关。
              </div>
              <PagedCards
                items={perLine.map((r) => ({
                  key: String(r.position),
                  title: `${r.name} · ${r.六亲}${r.干支}`,
                  body: (
                    <>
                      <div className="paged-inner-title">{r.name}　{r.六亲}{r.干支}（{r.五行}）</div>
                      <div className="perline-head" style={{ fontSize: 'var(--type-data)' }}>
                        <span>{r.六神}</span>
                        {r.卦位 && <span className="role">{r.卦位}</span>}
                        <span className="role">{r.角色}</span>
                        <span>{r.动静}</span>
                        {r.旬空 && <span className="bt-flag kong">空</span>}
                        {r.月破 && <span className="bt-flag">破</span>}
                      </div>
                      {r.兽性 && <div className="perline-clause">{r.六神}：{r.兽性}</div>}
                      {(r.断语 || []).map((c, i) => (
                        <div className="perline-clause" key={i}>
                          {c.text}
                          {c.plain ? <span className="plain">　白话：{c.plain}</span> : null}
                          <span className="src">出处：<QuoteRef k={c.src} /></span>
                        </div>
                      ))}
                      {!r.有专断 && r.无专断说明 && <div className="perline-clause plain">{r.无专断说明}</div>}
                    </>
                  ),
                }))}
                label="逐爻细看"
              />
              <div className="d-src" style={{ marginTop: 8 }}>
                三书（《增删卜易》《卜筮正宗》等六爻诸书）未就某个组合立专断时，
                这里只列兽性与状态，<b>不代拟断语</b>——没写就是不写，不拿"一般来说"补齐。
              </div>
            </>
          )}
          </div>{/* /六爻体系 */}

          {/* 命卦校验：净档 · 命局基线 · 建议维度 · 流动五行表 · 逐日宜忌 · 断言反馈 · 整案反馈 · 版本锚点 · 免责 */}
          {check && <CheckBlock check={check} />}

          {/* AI 断卦 */}
          <div className="await-ink">
            <div className="ai-title">
              {thinking ? <BaguaProgress /> : <span className="dot" aria-hidden />}AI 断卦
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 10 }}>
                <button type="button" className="btn" style={{ padding: '7px 20px', fontSize: 'var(--type-data)' }}
                  disabled={thinking || !done || rerun === 'used'} onClick={interpret}>
                  {thinking ? '断卦中…'
                    : rerun === 'armed' ? '按新用神重新断卦（仅此一次 · 再消耗 1 次额度）'
                    : rerun === 'used' ? '已按新用神重解过'
                    : aiText ? '重新断卦（消耗 1 次额度）' : '断 卦（消耗 1 次额度）'}
                </button>
              </span>
            </div>
            {/* 额度提示：填了自己的 key 就不限次，没填则签到后每天 3 次免费（按天算、不累加）。 */}
            <FreeQuotaHint />
            {rerun === 'used' && (
              <div className="notice notice-warn">
                <b>说明</b>
                <span className="n-body">
                  已按新用神重新解卦过一次——这一卦不再重解。若问的已不是同一件事，
                  请点「重 摇」另起一卦；只是想改处方，直接换用神即可（处方会重算）。
                </span>
              </div>
            )}
            {!aiText && !thinking && rerun !== 'used' && (
              <p className="stub-line">
                排盘、用神、处方五行、应期都已算出，且不花额度。点「断 卦」再让 AI 把这一卦讲清楚（扣一次每日额度）。
              </p>
            )}
            {thinking && !aiText && (
              <div className="ink-skel" aria-hidden>
                <span style={{ width: '26%' }} /><span style={{ width: '92%' }} />
                <span style={{ width: '80%' }} /><span style={{ width: '54%' }} />
              </div>
            )}
            {aiText && (
              <div className="md-wrap" aria-live="polite" aria-busy={thinking} aria-label="AI 断卦正文">
                <MarkdownLite text={aiText} />
                {thinking && <span className="caret" aria-hidden />}
              </div>
            )}
            {/* 读屏用状态行：流式正文逐字变化时整段朗读会吵，只播报"开始/结束" */}
            <span className="sr-only" role="status">
              {thinking ? '正在生成断卦正文…' : aiText ? '断卦正文已生成' : ''}
            </span>
            {verify && (
              <div role="status" className={`notice ${verify.kind === 'truncated' || verify.ok === false ? 'notice-warn' : 'notice-ok'}`}>
                <b>{verify.kind === 'truncated' ? '截断' : '回检'}</b>
                <span className="n-body">
                  {verify.kind === 'truncated'
                    ? <>{verify.message}<span className="n-hint">{verify.hint}</span></>
                    : (verify.summary || (verify.issues?.length ? verify.issues.map((i) => i.detail).join('；') : '未发现编造或越档问题'))}
                </span>
              </div>
            )}
            {aiText && (
              <p className="stub-line">
                本解读由 AI 生成（排盘、用神、处方五行、应期日期由程序确定性计算），仅供参考；请勿迷信。
              </p>
            )}
          </div>
        </>
      )}
    </div>
  )
}

/* ---------- 摇杆：按住拉满松手，记录释放点 / 时长 / 速度 ---------- */

function Joystick({ onRelease, disabled }: { onRelease: (p: ThrowParams) => void; disabled?: boolean }) {
  const R = 78
  const baseRef = useRef<HTMLDivElement | null>(null)
  const dragging = useRef(false)
  const startTime = useRef(0)
  const center = useRef({ x: 0, y: 0 })
  const last = useRef({ x: 0, y: 0 })
  const totalDist = useRef(0)
  const [offset, setOffset] = useState({ x: 0, y: 0 })

  const clamp = (dx: number, dy: number) => {
    const len = Math.hypot(dx, dy)
    if (len > R) return { x: (dx / len) * R, y: (dy / len) * R }
    return { x: dx, y: dy }
  }

  const move = (cx: number, cy: number) => {
    const c = center.current
    setOffset(clamp(cx - c.x, cy - c.y))
  }

  const down = (e: React.PointerEvent) => {
    if (disabled) return
    const el = baseRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    center.current = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
    dragging.current = true
    startTime.current = performance.now()
    last.current = { x: e.clientX, y: e.clientY }
    totalDist.current = 0
    e.currentTarget.setPointerCapture(e.pointerId)
    move(e.clientX, e.clientY)
  }

  const onMove = (e: React.PointerEvent) => {
    if (!dragging.current) return
    totalDist.current += Math.hypot(e.clientX - last.current.x, e.clientY - last.current.y)
    last.current = { x: e.clientX, y: e.clientY }
    move(e.clientX, e.clientY)
  }

  const up = (e: React.PointerEvent) => {
    if (!dragging.current) return
    dragging.current = false
    const duration = Math.max(1, Math.round(performance.now() - startTime.current))
    const speed = totalDist.current / duration
    const o = clamp(e.clientX - center.current.x, e.clientY - center.current.y)
    setOffset({ x: 0, y: 0 })
    onRelease({ x: o.x, y: o.y, duration, speed })
  }

  /** 系统打断（来电 / 手势被抢 / 误触）只复位，不算一次摇爻 */
  const cancelDrag = () => {
    if (!dragging.current) return
    dragging.current = false
    setOffset({ x: 0, y: 0 })
  }

  /** 键盘等价操作：Enter / Space 摇一爻（零位移、零速度，走同一随机种子管线） */
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return
    if (e.key !== 'Enter' && e.key !== ' ') return
    e.preventDefault()
    onRelease({ x: 0, y: 0, duration: 200, speed: 0 })
  }

  return (
    <div
      ref={baseRef}
      className={`jstick ${disabled ? 'locked' : ''}`}
      onPointerDown={down}
      onPointerMove={onMove}
      onPointerUp={up}
      onPointerCancel={cancelDrag}
      onKeyDown={onKeyDown}
      role="button"
      aria-label="摇卦摇杆：按住拉满后松手"
      tabIndex={0}
    >
      <div className="jstick-head" style={{ transform: `translate(${offset.x}px, ${offset.y}px)` }}>摇</div>
      <div className="jstick-caption">{disabled ? '六摇已毕' : '按住 · 拉满 · 松手'}</div>
    </div>
  )
}
