import { useCallback, useEffect, useRef, useState } from 'react'
import { BrushGua, FishTail } from '../art/book'
import BaguaProgress from '../art/BaguaProgress'
import { MicIcon } from '../art/icons'
import { friendlyError } from '../api/client'
import MarkdownLite from '../common/MarkdownLite'
import ProfileLine from '../common/ProfileLine'
import CheckBlock from '../common/CheckBlock'
import DuanGuaOrder from '../common/DuanGuaOrder'
import BaguaPicker from '../common/BaguaPicker'
import FloatingMic from '../common/FloatingMic'
import FreeQuotaHint from '../common/FreeQuotaHint'
import { useSpeech } from '../common/useSpeech'
import { guaLines, flipLine, wxClass } from '../api/gua'
import { divine, chat, type DivineBody, type MeihuaMethod } from '../api/meihua'
import { triName, YAO_NAMES } from '../data/trigrams'
import {
  checkMingju, getProfile, getTier, setTier,
  type MingjuCheck, type MingjuProfile,
} from '../api/mingju'
import { saveRecord, updateRecord } from '../api/records'
import type { DegradeInfo, MeihuaGuaData, Tier, VerifyInfo } from '../api/types'

/* ============================================================
   梅花易数 —— 已接后端
   起卦（ai=false，不花钱）→ 卦象 / 体用 / 处方五行 / 应期 / 命卦校验
   点「AI 解卦」再走 ai=true 的流式解读（这一步扣一次额度）
   ============================================================ */

/**
 * 起卦方式（2026-09-22 与旧前端同步为三种：时间占 · 手动起卦 · 字占）
 * ============================================================
 * · 「自动起卦」已按站长要求去掉（那一步走 /api/meihua/divine/pro，要调 AI 认起卦法并扣额度；
 *    该端点后来已从后端移除）。
 * · 一字占 / 二字占 / 多字占（声调）三项合并成一项「字占」：后端 engine.divine_text
 *    按字数自动分派取数法（1~3 字笔画、4 字按 zi_mode 二选一、5~10 字声调、11 字以上字数、
 *    0 汉字或超百字退回时间占），用户不必自己挑。
 * · 「物数占」已删：它与《八卦万物属类》是两套机制——物数占用"数出几个"（数量÷8），
 *    万物属类用"这东西属哪一卦的象"（端法：以物为上卦、方位为下卦）。
 * 后端仍保留 yizi / erzi / duozi / shuzi / time / manual 六个 method 键（历史记录要显示方式名），
 * 这里只暴露三个入口。
 */
const METHODS: { value: MeihuaMethod; label: string; hint: string }[] = [
  { value: 'time', label: '时间占', hint: '以起卦当下的农历年月日时起卦（不动不占）' },
  {
    value: 'manual', label: '手动起卦 · 万物类象',
    hint: '自己定上卦、下卦与动爻：搜物象或翻《八卦万物属类》。端法「以物为上卦，方位为下卦」，'
      + '动爻可按（上卦数＋下卦数＋时辰数）÷6 取余算，也可自己定。这一格不调 AI、不扣额度。',
  },
  {
    value: 'duozi', label: '字占',
    hint: '输入汉字即可，程序按字数自动定取数法（1~3 字笔画、4~10 字声调、11 字以上字数）',
  },
]

const METHOD_LABEL: Record<string, string> = {
  yizi: '一字占', erzi: '二字占', duozi: '多字占·声调', time: '时间占',
  shuzi: '物数占', manual: '手动起卦（自定上下卦与动爻）', shengyin: '声音占', renwu: '人物占',
  shen: '身占', wu: '物占', fuse: '服色占', waiying: '外应占', fangwei: '方位占', zhangchi: '丈尺占',
}

/** 起卦来源：后端给的是 rule / rule+quota / llm 这类标记，直接显示用户看不懂，翻成中文 */
const SOURCE_LABEL: Record<string, string> = {
  rule: '规则识别',
  'rule+quota': '规则识别（额度受限，未用 AI 认）',
  'rule+llm': 'AI 识别',
  llm: 'AI 识别',
  pro: '手动指定起卦法',
  ambig: '识别存疑',
}
const sourceLabel = (s?: string) => (s ? (SOURCE_LABEL[s] || s) : '')

const TIER_LABEL: Record<Tier, string> = { S: 'S · 紧急', M: 'M · 常规', L: 'L · 详批' }

/* 体用关系的白话（RELATION_PLAIN）已随「体用」一并移进 common/DuanGuaOrder.tsx，
   避免同一张表在两个文件里各存一份。 */

/** 档位说明（旧版原文照抄，讲清"解卦本身不受档位影响"） */
const TIER_HINT = '解卦本身始终完整（卦名·卦辞·爻象·体用生克）；档位只决定后面"行动建议"给几层：'
  + 'S 一层（这几天怎么做）/ M 两层（再加这季度怎么调）/ L 三层（再加这几年怎么养，每条附典籍出处）。'

const YAO_NAME = ['', '初爻', '二爻', '三爻', '四爻', '五爻', '上爻']
const yaoName = (pos: number) => YAO_NAME[pos] || `第 ${pos} 爻`

export default function MeihuaView({ initialQuestion = '', replay = null, replayId = null }: {
  initialQuestion?: string
  replay?: Record<string, unknown> | null
  replayId?: number | null
}) {
  /* 表单 */
  const [question, setQuestion] = useState(initialQuestion)
  const [method, setMethod] = useState<MeihuaMethod>('time')
  /** 字占的输入文本（留空则用「所问之事」那段话起卦） */
  const [text, setText] = useState('')
  /* 手动起卦：上卦 / 下卦（先天数 1-8）与动爻（1-6）；0 = 还没定，定了才让起卦 */
  const [upper, setUpper] = useState(0)
  const [lower, setLower] = useState(0)
  const [moving, setMoving] = useState(0)
  const [tier, setTierState] = useState<Tier>(getTier())

  /* 结果 */
  const [gua, setGua] = useState<MeihuaGuaData | null>(null)
  const [check, setCheck] = useState<MingjuCheck | null>(null)
  const [aiText, setAiText] = useState('')
  const [degrade, setDegrade] = useState<DegradeInfo | null>(null)
  const [verify, setVerify] = useState<VerifyInfo | null>(null)
  const [error, setError] = useState('')
  const [casting, setCasting] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [profile, setProfile] = useState<MingjuProfile | null>(null)

  /* 追问 */
  const [thread, setThread] = useState<{ role: 'user' | 'assistant'; content: string }[]>([])
  const [ask, setAsk] = useState('')
  const [asking, setAsking] = useState(false)

  const bodyRef = useRef<DivineBody | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const resultRef = useRef<HTMLDivElement | null>(null)
  /** 本条记录 id：卦一出来先存一条，AI 断完按 id 回填，一次解读只留一条 */
  const savedRecIdRef = useRef<number | null>(null)
  /** 回放模式：不存新记录、不重新起卦 */
  const replayRef = useRef(false)
  /** 当前卦象的引用：AI 断完回填记录时要用（状态在回调里可能是旧值） */
  const guaRef = useRef<MeihuaGuaData | null>(null)
  const threadRef = useRef<{ role: 'user' | 'assistant'; content: string }[]>([])
  const aiTextRef = useRef('')
  const checkRef = useRef<MingjuCheck | null>(null)
  /** 问句引用：命卦校验 effect 只在卦象变化时跑，不能把 question 列进依赖
      （否则每敲一个字都会重跑校验、多写一行台账），取最新值用这个 ref */
  const questionRef = useRef(question)

  useEffect(() => { guaRef.current = gua }, [gua])
  useEffect(() => { threadRef.current = thread }, [thread])
  useEffect(() => { aiTextRef.current = aiText }, [aiText])
  useEffect(() => { checkRef.current = check }, [check])
  useEffect(() => { questionRef.current = question }, [question])

  useEffect(() => {
    getProfile().then(setProfile).catch(() => setProfile(null))
  }, [])

  /* ---------- 命卦校验：卦象就位后自动比对命局 ----------
     起卦与回放共用这一条路径（与旧前端 MeihuaPage 的 guaData effect 同款做法）：
     起卦时 setGua 触发；回放时上面的回放 effect 还原卦象，这里照跑一次校验，
     回放视图因此和现时起卦一样有「命卦校验」板块。校验是确定性计算，不花 AI 额度。
     依赖只挂 gua——question 走 questionRef（挂在依赖里的话每敲一个字都会重跑校验、
     多写一行台账）。 */
  useEffect(() => {
    if (!gua) { setCheck(null); return }
    let cancelled = false
    checkMingju({
      gua: {
        ti_wuxing: gua.tiyong?.ti_wuxing,
        yong_wuxing: gua.tiyong?.yong_wuxing,
        relation: gua.tiyong?.relation,
      },
      remedy: (gua.remedy || {}) as Record<string, unknown>,
      question: questionRef.current.trim(),
      // 回传应期起算信息：保证「按处方栏」（check 响应里的 yingqi_final）与按卦栏同一窗口
      hour_zhi: gua.yingqi?.hour_zhi,
      yingqi_start: gua.yingqi?.start,
      yingqi_dates: gua.yingqi?.keyi?.map((d) => d.date),
      source: 'meihua',
    })
      .then((res) => { if (!cancelled) setCheck(res) })
      .catch(() => { if (!cancelled) setCheck(null) })   // 校验失败不影响卦象本身
    return () => { cancelled = true }
  }, [gua])

  /* ---------- 记录回放：用快照还原当时的卦与断语 ---------- */
  useEffect(() => {
    if (!replay) return
    replayRef.current = true
    savedRecIdRef.current = null
    const g = replay.gua_data as MeihuaGuaData | undefined
    if (g) setGua(g)
    if (typeof replay.ai_text === 'string') setAiText(replay.ai_text)
    if (typeof replay.question === 'string') setQuestion(replay.question)
    if (Array.isArray(replay.chat)) setThread(replay.chat as { role: 'user' | 'assistant'; content: string }[])
    setError('')
    window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120)
  }, [replay])

  const changeTier = (t: Tier) => { setTierState(t); setTier(t) }

  /* ---------- 语音输入：说出来的话填进「所问之事」，你看过再起卦 ---------- */
  const appendQuestion = useCallback((t: string) => {
    const clean = t.trim()
    if (!clean) return
    setQuestion((prev) => {
      if (!prev.trim()) return clean
      const joiner = /[。，！？、]$/.test(prev.trim()) ? '' : '，'
      return `${prev.trim()}${joiner}${clean}`
    })
  }, [])
  const speech = useSpeech(appendQuestion)

  /* ---------- 组装起卦请求体（与后端约定：选了起卦法必须同时传 params） ---------- */
  const buildBody = useCallback((): DivineBody | string => {
    const q = question.trim()
    if (method === 'duozi') {
      // 字占：留空就用「所问之事」那段话起卦（输入框上就是这么写的）
      const t = text.trim() || q
      if (!t) return '请输入要起卦的汉字，或先在「所问之事」里写下问句'
      return {
        user_input: q && q !== t ? `${t}，${q}` : t,
        method,
        // 四字这一档底本两法并列（「合四字的画数除六取动爻。也可以不计画数，而仅以平上去入
        // 四声起卦」），产品定各按 50% 取一：骰子在这里摇一次并存进请求体。
        // 必须存——AI 解卦会重发同一份请求体，后端拿不到 zi_mode 时每次各自随机
        // （engine.py:476-477），于是"起出来的卦"与"解卦时的卦"可能不是同一个。
        params: { text: t, zi_mode: Math.random() < 0.5 ? 'tone' : 'stroke' },
      }
    }
    if (method === 'time') {
      if (!q) return '时间占也要写下所问之事（不动不占）'
      return { user_input: q, method, params: {} }
    }
    if (method === 'manual') {
      // 三个格子必须都定下来：少一个就不知道该起哪一卦，宁可不发请求
      if (!upper || !lower || !moving) return '手动起卦要先把三个格子都定下来：上卦、下卦、动爻'
      const head = `手动起卦：上${triName(upper)}下${triName(lower)}，${YAO_NAMES[moving - 1]}动`
      return { user_input: q ? `${head}。${q}` : head, method, params: { upper, lower, moving } }
    }
    // 兜底：时间占（不动不占，以当下为机）
    if (!q) return '时间占也要写下所问之事（不动不占）'
    return { user_input: q, method: 'time', params: {} }
  }, [question, method, text, upper, lower, moving])

  /* ---------- 起卦 ----------
     一律走 /api/meihua/divine(ai=false)：只要卦，不花钱、不扣额度；
     看过卦再决定要不要点「AI 解卦」（那一步才花钱）。
     「自动起卦」（/api/meihua/divine/pro，让 AI 认起卦法并顺带解卦）已按用户要求去掉。
  */
  const cast = useCallback(async () => {
    if (casting) return
    const built = buildBody()
    if (typeof built === 'string') { setError(built); return }
    setError(''); setCasting(true)
    setGua(null); setCheck(null); setAiText(''); setDegrade(null); setVerify(null)
    setThread([])
    bodyRef.current = built
    let got: MeihuaGuaData | null = null
    try {
      await divine(built, false, (e) => {
        if (e.gua) {
          got = e.gua
          setGua(e.gua)
          window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80)
        }
        if (e.text) setAiText((prev) => prev + e.text)
        if (e.degrade) setDegrade(e.degrade)
        if (e.verify) setVerify((prev) => ({ ...prev, ...e.verify! }))
        if (e.error) setError(e.error)
      })
    } catch (err) {
      setError(friendlyError(err) || '起卦失败')
    } finally {
      setCasting(false)
    }
    if (!got) return
    /* 落库：卦一出来就存一条（保证盘不会丢），AI 断完再按 id 回填断语 */
    const g = got as MeihuaGuaData
    if (!replayRef.current) {
      const guaName = `${g.ben_gua?.name || '卦'}${g.bian_gua ? ' → ' + g.bian_gua.name : ''}`
      const meta = `${METHOD_LABEL[g.method] || g.method || ''}·${g.tiyong?.relation_desc || g.tiyong?.relation || ''}`
      const row = await saveRecord({
        kind: 'meihua',
        title: built.user_input || guaName,
        subtitle: built.user_input ? `${guaName} · ${meta}` : meta,
        question: built.user_input,
        payload: { gua_data: g, ai_text: '', question: built.user_input, chat: [] },
      })
      savedRecIdRef.current = row?.id ?? null
    }
    /* 命卦校验不再在这里调：已移到上面的「gua 就位 → 自动校验」effect，
       起卦与回放共用同一路径（见该 effect 的注释）。 */
  }, [buildBody, casting])

  /* ---------- 回放补跑「AI 解卦」：解的是快照里已存的卦，不重新起卦 ----------
     为什么不能复用 interpret：那一步靠 bodyRef 重发同一请求体去重起卦（时间占重起
     会换成另一个卦）；回放里没有起卦请求体，故走 /api/meihua/chat 解存量卦
     （history 空 = 首次解卦），断语回填进这条记录，下次回看直接有。 */
  const replayInterpret = useCallback(async () => {
    if (!guaRef.current || thinking) return
    const q = (questionRef.current || '').trim()
    if (!q) { setError('这条记录没有所问内容，无法解卦（可回到起卦页重新问一次）'); return }
    setThinking(true); setError(''); setAiText(''); setDegrade(null); setVerify(null)
    let acc = ''
    try {
      await chat(guaRef.current, [], q, (e) => {
        if (e.text) { acc += e.text; setAiText((prev) => prev + e.text) }
        if (e.degrade) setDegrade(e.degrade)
        const v = e.verify
        if (v) setVerify((prev) => ({ ...prev, ...v }))
        if (e.error) setError(e.error)
      })
    } catch (err) {
      setError(friendlyError(err) || '解卦失败')
    } finally {
      setThinking(false)
    }
    if (acc && replayId != null && replay) {
      void updateRecord(replayId, { payload: { ...replay, ai_text: acc } })
    }
  }, [thinking, replayId, replay])

  /* ---------- AI 解卦（扣一次额度） ---------- */
  const interpret = useCallback(async () => {
    if (!bodyRef.current) {
      // 回放来的卦没有起卦请求体，改走解存量卦的路径；两者都缺就什么也不做
      if (replay && guaRef.current) { await replayInterpret(); return }
      return
    }
    if (thinking) return
    setThinking(true); setError(''); setAiText(''); setDegrade(null); setVerify(null)
    const ac = new AbortController()
    abortRef.current = ac
    let acc = ''
    try {
      await divine(bodyRef.current, true, (e) => {
        if (e.text) { acc += e.text; setAiText((prev) => prev + e.text) }
        if (e.gua) setGua(e.gua)
        if (e.degrade) setDegrade(e.degrade)
        const v = e.verify
        if (v) setVerify((prev) => ({ ...prev, ...v }))
        if (e.error) setError(e.error)
      }, ac.signal)
    } catch (err) {
      const name = (err as { name?: string }).name
      if (name !== 'AbortError') setError(friendlyError(err) || '解卦失败')
    } finally {
      setThinking(false)
    }
    /* 断完回填：把带断语的完整快照盖回同一条记录（记录被删了就退回新增） */
    if (acc && guaRef.current && !replayRef.current) {
      const payload = {
        gua_data: guaRef.current, ai_text: acc,
        question: bodyRef.current.user_input, chat: [],
        /* 校验台账的钥匙：记录行要能按 log_id 回显应验状态（2026-10 补，旧前端一直带着） */
        log_id: checkRef.current?.log_id ?? null,
      }
      if (savedRecIdRef.current != null) {
        if (await updateRecord(savedRecIdRef.current, { payload })) return
        savedRecIdRef.current = null
      }
      const row = await saveRecord({
        kind: 'meihua',
        title: bodyRef.current.user_input,
        subtitle: `${guaRef.current.ben_gua?.name || ''} · AI 解读`,
        question: bodyRef.current.user_input,
        payload,
      })
      savedRecIdRef.current = row?.id ?? null
    }
  }, [thinking, replay, replayInterpret])

  /* ---------- 追问（不重新起卦） ---------- */
  /** 追问（含"就某条外应细讲"）：都不重新起卦，只把新内容并入已起的卦 */
  const runChat = useCallback(async (
    q: string, opts?: { waijing?: string[]; waijingGua?: Record<string, string> },
  ) => {
    if (!q || !guaRef.current || asking) return
    setAsking(true)
    const next = [...threadRef.current, { role: 'user' as const, content: q }, { role: 'assistant' as const, content: '' }]
    setThread(next)
    /* 追问的 history 三层构造（2026-10 与旧前端对齐）：原始提问 → 首次解卦全文 → 既往追问，
       让 AI 追问时还能看到最初的问题与完整首解，而不是只剩零星对话。 */
    const history: { role: 'user' | 'assistant'; content: string }[] = []
    const q0 = bodyRef.current?.user_input?.trim()
    const a0 = aiTextRef.current?.trim()
    if (q0) history.push({ role: 'user', content: q0 })
    if (a0) history.push({ role: 'assistant', content: a0 })
    history.push(...threadRef.current)
    try {
      await chat(guaRef.current, history, q, (e) => {
        if (e.text) {
          setThread((prev) => {
            const copy = [...prev]
            copy[copy.length - 1] = {
              role: 'assistant',
              content: (copy[copy.length - 1]?.content || '') + e.text,
            }
            return copy
          })
        }
        if (e.degrade) setDegrade(e.degrade)
        const v2 = e.verify
        if (v2) setVerify((prev) => ({ ...prev, ...v2 }))
        if (e.error) setError(e.error)
      }, {
        waijing: opts?.waijing,
        innerNet: checkRef.current?.adjudication?.net || '',
        waijingGua: opts?.waijingGua,
      })
    } catch (err) {
      setError(friendlyError(err) || '追问失败')
    } finally {
      setAsking(false)
    }
    /* 追问内容一并存进这条记录的快照（回放时能连对话一起看到） */
    const finalThread = threadRef.current
    if (finalThread.length && guaRef.current && !replayRef.current && savedRecIdRef.current != null) {
      void updateRecord(savedRecIdRef.current, {
        payload: {
          gua_data: guaRef.current,
          ai_text: aiTextRef.current,
          question: bodyRef.current?.user_input || '',
          chat: finalThread,
          log_id: checkRef.current?.log_id ?? null,
        },
      })
    }
  }, [asking])

  const followUp = useCallback(async () => {
    const q = ask.trim()
    if (!q) return
    setAsk('')
    await runChat(q)
  }, [ask, runChat])

  /* ---------- 渲染 ---------- */
  const benLines = guaLines(gua?.ben_gua)
  const huLines = guaLines(gua?.hu_gua)
  const bianLines = gua?.bian_gua ? guaLines(gua.bian_gua) : (gua ? flipLine(benLines, gua.moving_yao.position) : [])
  const movingPos = gua?.moving_yao?.position ?? 0

  const methodHint = METHODS.find((m) => m.value === method)?.hint || METHODS[0].hint

  /**
   * 字占：把后端 engine.divine_text 的分派口径先讲给用户听，起卦前就知道会怎么取数。
   * 阈值与该函数逐条一致（engine.py:455-482）：0 汉字或超百字退回时间占、1~3 字笔画、
   * 4 字按 zi_mode 二选一、5~10 字声调、11 字以上字数。汉字范围也与后端一致
   * （U+3400–U+4DBF 与 U+4E00–U+9FFF）。
   */
  const ziCount = Array.from(text.trim() || question.trim())
    .filter((c) => /[\u3400-\u4dbf\u4e00-\u9fff]/.test(c)).length
  const ziHint = ziCount === 0
    ? '现在没有汉字：后端会退回时间占。'
    : ziCount > 100
      ? `共 ${ziCount} 个汉字，超过百字：后端会退回时间占。`
      : ziCount === 1
        ? '共 1 个汉字 → 一字占：按字的左、右部件笔画取数。'
        : ziCount === 2
          ? '共 2 个汉字 → 二字占：第一字笔画定上卦、第二字笔画定下卦。'
          : ziCount === 3
            ? '共 3 个汉字 → 三字占：第一字笔画定上卦、后二字笔画和定下卦。'
            : ziCount === 4
              ? '共 4 个汉字 → 底本两法并列（笔画／声调），本站各按 50% 取一：'
                + '起卦时摇定一次并记在请求体里，所以「起卦」与「AI 解卦」必是同一卦。'
              : ziCount <= 10
                ? `共 ${ziCount} 个汉字 → 用声调取数（平 1、上 2、去 3、入 4）：`
                  + '前半声调之和定上卦、后半定下卦，动爻＝两个取数之和除六。'
                : `共 ${ziCount} 个汉字 → 用字数取数：前半字数定上卦、后半定下卦，动爻＝总字数除六。`

  /** 手动起卦要三个格子都定了才能起；缺哪个就说缺哪个，别让用户点了才吃一条报错 */
  const manualMissing = method === 'manual'
    ? [!upper && '上卦', !lower && '下卦', !moving && '动爻'].filter(Boolean) as string[]
    : []
  const castReady = manualMissing.length === 0

  return (
    <div>
      <div className="leaf-head">
        <span className="juan-mark">观候·转明</span>
        <FishTail />
        <span className="juan">梅花易数</span>
        <span className="folio">卷一</span>
      </div>
      <div className="juan-title">
        <h1>起卦观梅</h1>
        <p className="juan-sub">以卦象观天机 · 以易理悟人事</p>
      </div>

      {/* ---------- 起卦表单 ---------- */}
      <div className="register">
        <span className="reg-label">所问之事</span>
        <textarea
          className="textarea"
          rows={3}
          maxLength={200}
          placeholder="此刻心里放不下的那件事——越具体，卦象越有针对性（如：这周五去谈合作顺利吗）"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <span className="reg-hint">不动不占 · 无事不占 —— 一次只问一件具体的事</span>

        <div className="bz-head">
          <h2>起卦方式</h2>
          <span className="rule" />
          <span className="aside">三种起卦法，起卦本身都不调 AI、不扣额度</span>
        </div>
        <div className="slip-row">
          {METHODS.map((m) => (
            <button
              key={m.value}
              type="button"
              title={m.hint}
              className={`slip ${method === m.value ? 'active' : ''}`}
              onClick={() => setMethod(m.value)}
            >
              {m.label}
            </button>
          ))}
        </div>
        <span className="reg-hint">{methodHint}</span>

        {/* 手动起卦：三个格子 + 万物搜索 + 后天八卦图 + 物象框 */}
        {method === 'manual' && (
          <BaguaPicker
            upper={upper} lower={lower} moving={moving}
            onUpper={setUpper} onLower={setLower} onMoving={setMoving}
          />
        )}

        {/* 字占：一个输入框，取数法由后端按字数自动分派（engine.divine_text） */}
        {method === 'duozi' && (
          <>
            <div className="param-row">
              <input className="mini-input" style={{ gridColumn: '1 / -1' }}
                placeholder="要起卦的汉字（可留空，用上面「所问之事」那段话起卦）"
                value={text} maxLength={120} onChange={(e) => setText(e.target.value)} />
            </div>
            <span className="reg-hint">{ziHint}</span>
          </>
        )}

        {/* 参考资料：各法共用的序数与五行取值（旧前端 ReferencePanel，2026-10 搬回；
            声调口径按后端实行的《词林正韵》写，不照搬旧端的「平水韵」错句） */}
        <details className="pd-fold" style={{ marginTop: 18 }}>
          <summary>参考资料：取数所用序数与五行</summary>
          <div className="texture-block">
            <p>年支序数：子1 丑2 寅3 卯4 辰5 巳6 午7 未8 申9 酉10 戌11 亥12</p>
            <p>时辰序数：子1(23-01) 丑2(01-03) 寅3(03-05) 卯4(05-07) 辰5(07-09) 巳6(09-11)</p>
            <p style={{ paddingLeft: 30 }}>午7(11-13) 未8(13-15) 申9(15-17) 酉10(17-19) 戌11(19-21) 亥12(21-23)</p>
            <p>八卦序数（先天）：乾1☰ 兑2☱ 离3☲ 震4☳ 巽5☴ 坎6☵ 艮7☶ 坤8☷</p>
            <p>五行：乾兑金 | 坤艮土 | 震巽木 | 坎水 | 离火</p>
            <p>笔画取繁体（康熙字典）；声调按《词林正韵》表（后端定稿口径），表值 5（仄声）一律细分作去声。</p>
            <div className="bz-head" style={{ marginTop: 12 }}>
              <h2>体用生克五种关系</h2>
              <span className="rule" />
            </div>
            <table className="tone-table" style={{ marginTop: 6 }}>
              <thead><tr><th>关系</th><th>判断</th><th>含义</th></tr></thead>
              <tbody>
                <tr><td>用生体</td><td>吉</td><td>事来就我，有进益之喜</td></tr>
                <tr><td>体克用</td><td>诸事吉</td><td>婚姻、求名、求谋等门则成而迟</td></tr>
                <tr><td>比和</td><td>吉</td><td>百事顺遂</td></tr>
                <tr><td>体生用</td><td>泄气</td><td>劳而耗己，有耗失之患</td></tr>
                <tr><td>用克体</td><td>凶</td><td>事来压我</td></tr>
              </tbody>
            </table>
            <div className="d-src" style={{ marginTop: 8 }}>断语据《梅花易数 · 体用总诀》校正：用生体有进益之喜，体克用诸事吉，比和百事顺遂，体生用有耗失之患，用克体诸事凶。</div>
          </div>
        </details>

        <div className="bz-head">
          <h2>解读档位</h2>
          <span className="rule" />
          <span className="aside">累积式：S 只出紧急层，M 加常规层，L 全三段</span>
        </div>
        <div className="slip-row">
          {(['S', 'M', 'L'] as Tier[]).map((t) => (
            <button key={t} type="button" className={`slip ${tier === t ? 'active' : ''}`} onClick={() => changeTier(t)}>
              {TIER_LABEL[t]}
            </button>
          ))}
        </div>
        <span className="reg-hint">{TIER_HINT}</span>

        <div className="bz-head">
          <h2>命局校验</h2>
          <span className="rule" />
          <span className="aside">处方五行先过你八字的忌神红线</span>
        </div>
        <ProfileLine profile={profile} />

        <div className="btn-row" style={{ marginTop: 20 }}>
          <button type="button" className="btn" disabled={casting || !castReady} onClick={cast}>
            {casting ? '起卦中…' : '起 卦'}
          </button>
          <button type="button" className="btn-outline"
            disabled={!gua || thinking}
            title={!bodyRef.current
              ? '回放快照也可补跑 AI 解卦：解的是这条记录里已存的卦（不重新起卦），断语会回填进这条记录。'
              : undefined}
            onClick={interpret}>
            {thinking ? '解卦中…' : (aiText ? '重新解卦' : 'AI 解卦（扣一次额度）')}
          </button>
          <button
            type="button"
            className={`btn-outline ${speech.state === 'recording' ? 'rec-on' : ''}`}
            disabled={!speech.supported}
            title={speech.supported ? (speech.state === 'recording' ? '点一下结束并识别' : '点一下开始说话') : speech.reason}
            onClick={() => (speech.state === 'recording' ? speech.stop() : void speech.start())}
          >
            <MicIcon size={15} />
            {speech.state === 'recording' ? '说完点这里' : speech.state === 'uploading' ? '识别中…' : '语音输入'}
          </button>
          {!speech.supported && <span className="hint-line">{speech.reason}</span>}
          {speech.error && <span className="hint-line" style={{ color: 'var(--ji)' }}>{speech.error}</span>}
        </div>
        <span className="reg-hint">
          起卦、体用、处方五行、应期都是后端代码算的，不调 AI、不扣额度；只有点「AI 解卦」才花一次额度。
          {manualMissing.length > 0 && (
            <b className="mc-missing">　还差：{manualMissing.join('、')}——三个格子都定下来才能起卦。</b>
          )}
        </span>
        {/* 额度提示：填了自己的 key 就不限次，没填则签到后每天 3 次免费（按天算、不累加）。 */}
        {gua && <FreeQuotaHint />}

        {error && <div className="notice notice-err" role="alert"><b>错误</b><span className="n-body">{error}</span></div>}
        {degrade && (
          <div className="notice notice-warn" role="status">
            <b>降级</b>
            <span className="n-body">
              {degrade.message}
              {degrade.hint && <span className="n-hint">{degrade.hint}</span>}
              {(degrade.used !== undefined && degrade.limit) ? (
                <span className="n-hint">今日已用 {String(degrade.used)}/{String(degrade.limit)}{degrade.resets_at ? ` · ${degrade.resets_at} 恢复` : ''}</span>
              ) : null}
            </span>
          </div>
        )}
      </div>

      {/* ---------- 卦象（真实计算） ---------- */}
      <div ref={resultRef} />
      {gua && (
        <>
          <div className="bz-head">
            <h2>卦象</h2>
            <span className="rule" />
            <span className="demo-badge">
              {METHOD_LABEL[gua.method] || gua.method}
              {gua.qi_info?.day_ganzhi ? ` · ${gua.qi_info.day_ganzhi}日` : ''}
              {gua.intent?.source
                ? ` · ${gua.intent.method === 'manual'
                  ? '用户自定上卦·下卦·动爻（不经识别）'
                  : sourceLabel(gua.intent.source)}`
                : ''}
            </span>
          </div>
          {gua.qi_info && (
            <div className="d-src" style={{ marginTop: 8 }}>
              起卦时间：
              {gua.qi_info.lunar ? `农历${gua.qi_info.lunar}` : ''}
              {gua.qi_info.day_ganzhi ? ` · ${gua.qi_info.day_ganzhi}日` : ''}
              {gua.qi_info.hour_zhi ? ` · ${gua.qi_info.hour_zhi}时起卦` : ''}
              {gua.qi_info.season ? ` · ${gua.qi_info.season}` : ''}
            </div>
          )}

          <div className="gua-row">
            <BrushGua
              role="本 卦" name={gua.ben_gua.name} lines={benLines} moving={[movingPos]} nameGold
              lowerWx={gua.ben_gua.lower.wuxing} upperWx={gua.ben_gua.upper.wuxing}
              wx={<>
                <span className={wxClass(gua.ben_gua.upper.wuxing)}>{gua.ben_gua.upper.name}{gua.ben_gua.upper.wuxing}</span>上 · 下
                <span className={wxClass(gua.ben_gua.lower.wuxing)}>{gua.ben_gua.lower.name}{gua.ben_gua.lower.wuxing}</span>
              </>}
              note={`${yaoName(gua.moving_yao.position)}动`}
            />
            {gua.hu_gua && (
              <BrushGua
                role="互 卦" name={gua.hu_gua.name} lines={huLines}
                lowerWx={gua.hu_gua.lower.wuxing} upperWx={gua.hu_gua.upper.wuxing}
                wx={<>
                  <span className={wxClass(gua.hu_gua.upper.wuxing)}>{gua.hu_gua.upper.name}{gua.hu_gua.upper.wuxing}</span>上 · 下
                  <span className={wxClass(gua.hu_gua.lower.wuxing)}>{gua.hu_gua.lower.name}{gua.hu_gua.lower.wuxing}</span>
                </>}
                note="事之中间过程"
              />
            )}
            {gua.bian_gua && (
              <BrushGua
                role="变 卦" name={gua.bian_gua.name} lines={bianLines}
                lowerWx={gua.bian_gua.lower.wuxing} upperWx={gua.bian_gua.upper.wuxing}
                wx={<>
                  <span className={wxClass(gua.bian_gua.upper.wuxing)}>{gua.bian_gua.upper.name}{gua.bian_gua.upper.wuxing}</span>上 · 下
                  <span className={wxClass(gua.bian_gua.lower.wuxing)}>{gua.bian_gua.lower.name}{gua.bian_gua.lower.wuxing}</span>
                </>}
                note="事之结局"
              />
            )}
          </div>

          {/* ===== 梅花体系（分区）=====
              区层与旧前端一致：《梅花易数》古法在上，本站工程层（结合八字）在下。
              标题下面就是「断卦次序」四步（爻辞 → 体用 → 克应 → 应期）；
              断卦次序之外的区块（起卦依据、处方五行）按站长要求排在它后面，不删。
              原来散在这里的 体用行 / 卦辞·大象·动爻 / 卦气衰旺 三块已并入对应步骤
              （同一内容只出现一次），不是删除：卦辞与大象在第①步，体用与衰旺在第②步。 */}
          <div className="sys-zone">
            <div className="sys-zone-head">
              <span className="sys-zone-title">梅花体系</span>
              <span className="sys-zone-sub">《梅花易数》古法：爻辞 · 体用 · 克应 · 应期</span>
            </div>

            <DuanGuaOrder
              gua={gua}
              innerNet={check?.adjudication?.net}
              onAskAi={(omen, chosen) => {
                void runChat(`请就这条外应细讲：${omen.join('；')}`, { waijing: omen, waijingGua: chosen })
              }}
            />

            {/* 取数依据 / 拆字 / 声调：让"这一卦怎么来的"可复核 */}
            {(gua.method_params?.derive || gua.chaizi_info || gua.tone_details) && (
              <div className="detail-block">
                <div className="d-title">起 卦 依 据</div>
                {(() => {
                  const d = gua.method_params?.derive as
                    | { upper?: { note?: string }; lower?: { note?: string }; moving?: { note?: string } }
                    | undefined
                  if (!d) return null
                  /* 后端给的 note 自己就带「上卦：」这样的前缀（engine._derive 与
                     divine_manual 都是这么拼的），前端再补一遍就成了「上卦：上卦：…」。
                     所以只在 note 没带前缀时才补。 */
                  const line = (label: string, note?: string) => {
                    if (!note) return null
                    return (
                      <div className="derive-line">
                        {note.startsWith(label) ? note : `${label}：${note}`}
                      </div>
                    )
                  }
                  return (
                    <>
                      {line('上卦', d.upper?.note)}
                      {line('下卦', d.lower?.note)}
                      {line('动爻', d.moving?.note)}
                    </>
                  )
                })()}
                {gua.chaizi_info && (
                  <div className="derive-line">
                    拆字：「{gua.chaizi_info.char}」繁体笔画 {gua.chaizi_info.ftbh}
                    {gua.chaizi_info.used_decomposition
                      ? ` · 拆为「${gua.chaizi_info.used_decomposition.left.join('')}」与「${gua.chaizi_info.used_decomposition.right.join('')}」`
                      : (gua.chaizi_info.decomposition?.length
                        ? ` · 可拆为 ${gua.chaizi_info.decomposition.map((g) => g.join('')).join('、')}`
                        : ' · 此字不可拆分，上下卦同数')}
                  </div>
                )}
                {gua.tone_details && (
                  <>
                    <div className="derive-line" style={{ marginTop: 6 }}>声调分布（平上去入）：</div>
                    {(['first_half', 'second_half'] as const).map((half) => {
                      const arr = gua.tone_details?.[half] || []
                      if (!arr.length) return null
                      return (
                        <div key={half}>
                          <div className="hint-line">{half === 'first_half' ? '前半（定上卦）' : '后半（定下卦）'}</div>
                          <div className="tone-row">
                            {arr.map((t, i) => (
                              <span className="tone-chip" key={`${half}-${i}`}>
                                {t.char}<small>{t.tone_name}</small>
                              </span>
                            ))}
                          </div>
                        </div>
                      )
                    })}
                    {/* 声调口径必须写明：底本白话按现代音标注，后端表按《词林正韵》，
                        两者对同一句话会算出不同的上下卦。不写清楚，用户拿书一对就以为程序算错了。 */}
                    <div className="d-src">
                      声调取值来自后端声调表（data/meihua_data.json 的 tone 段，8329 字）；
                      engine.py:209 注明该表按<b>《词林正韵》</b>口径，表值 5（仄声，41 字）一律细分作去声。
                      这与底本白话按现代音标注的声调可能不同：《梅花易数》L904「今日动静如何」白话算
                      前半 8、后半 5（得地风升），本表算前半 7、后半 6（得山水蒙）——
                      差在「动」「静」（表记上声、白话记去声）与「如」（表记去声、白话记平声）三字；
                      六字总数同为 13，动爻同为初爻。
                    </div>
                  </>
                )}
                <div className="d-src">
                  这些是引擎按"卦以八除、爻以六除"算出来的取数过程，可逐条复核。
                </div>
              </div>
            )}

            {/* 处方五行 */}
            {gua.remedy && (
              <div className="detail-block">
                <div className="d-title">处 方 五 行</div>
                <div className="d-body" style={{ fontSize: 'var(--type-body)' }}>
                  该补：<b>{gua.remedy.R}</b>
                  {gua.remedy.X && gua.remedy.X !== gua.remedy.R ? <>　避：<b>{gua.remedy.X}</b></> : null}
                  {gua.remedy.R_alt ? <>　备选：<b>{gua.remedy.R_alt}</b></> : null}
                  <div style={{ marginTop: 6, color: 'var(--ink-3)' }}>{gua.remedy.R_reason}</div>
                  <div style={{ marginTop: 4, color: 'var(--ink-3)' }}>状态：{gua.remedy.state} —— {gua.remedy.state_desc}</div>
                </div>
              </div>
            )}

            {/* 应期与外应参断已并入上面「断卦次序」的第④步与第③步（同一内容只出现一次）：
                应期＝成卦数 + 行/立/坐调速 + 按卦栏日期（可成/吉凶并见/避险）；
                外应＝三要十应判据总表 + WaijingBlock（配卦与内外合断）。 */}
          </div>{/* /梅花体系 */}

          {/* 命卦校验：净档 · 命局基线 · 建议维度 · 流动五行表 · 逐日宜忌 · 断言反馈 · 整案反馈 · 版本锚点 · 免责 */}
          {check && <CheckBlock check={check} />}

          {/* AI 解卦
              回放的记录不带当初的起卦请求体（bodyRef 为空）；2026-10 起回放也可补跑——
              走 /api/meihua/chat 解快照里那份存量卦（不重新起卦），断语回填进记录。 */}
          <div className="await-ink">
            <div className="ai-title">
              {thinking ? <BaguaProgress /> : <span className="dot" aria-hidden />}AI 解卦
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 10 }}>
                <button type="button" className="btn" style={{ padding: '7px 20px', fontSize: 'var(--type-data)' }}
                  disabled={thinking || !gua}
                  title={!bodyRef.current
                    ? '回放快照也可补跑 AI 解卦：解的是这条记录里已存的卦（不重新起卦），断语会回填进这条记录。'
                    : undefined}
                  onClick={interpret}>
                  {thinking ? '解卦中…' : aiText ? '重新解卦' : '解 卦'}
                </button>
              </span>
            </div>

            {gua && !bodyRef.current && (
              <p className="stub-line" role="status">
                这是回放的历史快照。点「解 卦」可以补跑 AI 解读——解的是快照里那份卦（不重新起卦，
                时间占也不会换成另一个卦），断语会回填进这条记录；已有断语时点「重新解卦」会覆盖旧文。
              </p>
            )}

            {!aiText && !thinking && bodyRef.current && (
              <p className="stub-line">
                还没有解读。点「解 卦」把这一卦交给 AI 讲清楚（会消耗一次每日额度）。
                解读分两节：「第一部分 · 解卦」与「第二部分 · 行动建议」。
              </p>
            )}
            {thinking && !aiText && (
              <div className="ink-skel" aria-hidden>
                <span style={{ width: '30%' }} /><span style={{ width: '92%' }} />
                <span style={{ width: '84%' }} /><span style={{ width: '58%' }} />
              </div>
            )}
            {aiText && (
              <div className="md-wrap" aria-live="polite" aria-busy={thinking} aria-label="AI 解卦正文">
                <MarkdownLite text={aiText} />
                {thinking && <span className="caret" aria-hidden />}
              </div>
            )}
            {/* 读屏用状态行：流式正文逐字变化时整段朗读会吵，只播报"开始/结束" */}
            <span className="sr-only" role="status">
              {thinking ? '正在生成解卦正文…' : aiText ? '解卦正文已生成' : ''}
            </span>

            {verify && (
              <div role="status" className={`notice ${verify.kind === 'truncated' ? 'notice-warn' : verify.ok === false ? 'notice-warn' : 'notice-ok'}`}>
                <b>{verify.kind === 'truncated' ? '截断' : '回检'}</b>
                <span className="n-body">
                  {verify.kind === 'truncated'
                    ? <>{verify.message}<span className="n-hint">{verify.hint}</span></>
                    : (verify.summary || (verify.issues?.length ? verify.issues.map((i) => i.detail).join('；') : '未发现编造或越档问题'))}
                </span>
              </div>
            )}

            {/* 追问：起卦后即可问（2026-10 改，与旧前端一致——未 AI 解卦时追问
                等于在首次解读前补充信息，不必先花一次额度） */}
            {gua && !thinking && (
              <>
                {thread.length > 0 && (
                  <div className="chat-thread" aria-live="polite" aria-busy={asking}>
                    {thread.map((t, i) => (
                      <div className={`chat-turn ${t.role === 'user' ? 'me' : ''}`} key={i}>
                        <span className="who">{t.role === 'user' ? '问' : '答'}</span>
                        {t.role === 'assistant' ? <MarkdownLite text={t.content} /> : t.content}
                      </div>
                    ))}
                  </div>
                )}
                <div className="chat-ask">
                  <input
                    className="mini-input" style={{ flex: 1 }}
                    placeholder={aiText ? '追问（不重新起卦）：把疑问问得更具体些' : '还没解卦也可以先补充：把背景或疑问说得更具体些'}
                    aria-label="追问内容"
                    value={ask}
                    onChange={(e) => setAsk(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') followUp() }}
                  />
                  <button type="button" className="btn-outline" disabled={asking || !ask.trim()} onClick={followUp}>
                    {asking ? '追问中…' : '追 问'}
                  </button>
                </div>
                {asking && <p className="stub-line stream-progress"><BaguaProgress />正在回答这一次追问…</p>}
              </>
            )}

            {(aiText || thinking) && (
              <p className="stub-line">
                本解读由 AI 生成（卦象、体用、处方五行、应期日期由程序确定性计算），仅供参考；请勿迷信。
              </p>
            )}
          </div>
        </>
      )}

      {/* 浮动语音钮：可拖动，位置记在本机；说完的话填进「所问之事」 */}
      <FloatingMic onText={appendQuestion} label="语音输入" />
    </div>
  )
}
