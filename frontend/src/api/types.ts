/**
 * 后端返回结构类型（按真实响应实测整理，只声明前端真正用到的字段）。
 * 数据来源：backend/main.py 与各引擎模块；字段名与后端保持一字不差。
 */

/* ---------- 通用 ---------- */

export type WuXing = '金' | '木' | '水' | '火' | '土'
export type Tier = 'S' | 'M' | 'L'

export interface Trigram {
  num: number
  name: string
  symbol: string
  wuxing: string
}

export interface GuaBrief {
  key: string
  name: string
  symbol: string
  upper: Trigram
  lower: Trigram
  lines?: number[]
  yao_display?: string[]
  guaci?: string
  daxiang?: string
  palace?: string
  markers?: string[]
}

/* ---------- 梅花 ---------- */

export interface YingqiItem {
  date: string
  ganzhi: string
  wx: string
  reason: string
  /** 后端给的分类字样：可成 / 避险 / 吉凶并见（梅花）｜按最终处方（工程口径） */
  kind?: string
  /** 依据分栏：'卦'＝典籍（按卦栏）｜'处方'＝命局改方后的工程口径 */
  basis?: string
}

export interface MeihuaYingqi {
  fa: string
  src: string[]
  ti_wuxing: string
  sheng_ti_wuxing: string
  ke_ti_wuxing: string
  cheng_gua_zong_shu: number
  shang_shu: number
  xia_shu: number
  kuai: number
  huan: number
  window_text: string
  keyi: YingqiItem[]
  xianri: YingqiItem[]
  /** 同日既逢生体又逢克体：单列「吉凶并见」，不替用户择一（backend/yingqi.py:195-197） */
  jian?: YingqiItem[]
  /** 比和：体卦自身五行当值之日（书证 L2826「生体及比和之年月为吉期」；2026-09-22 加） */
  bihe?: YingqiItem[]
  /** 按最终处方栏（命局校验改方后的五行当值之日）——工程口径，归「结合八字」区 */
  keyi_final?: YingqiItem[]
  R?: string
  final_R?: string
  hour_zhi?: string
  start?: string
  /** 加权分口径说明（月支/日支/年支/时支权重与过线值） */
  weight_note?: string
  note: string
}

/**
 * 动爻爻辞的逐词注释（训诂）。
 * 后端 backend/yaoci_zhu.py 提供，数据由 tools/build_yaoci_zhu.py 从《周易》
 * （杨天才、张善文译注，中华书局·全本全注全译丛书）的【注释】逐条抽出。
 * 只给注释、不给整句译文——《梅花易数》把爻辞当象的语言用（鸡悲鸣占只拈「血去」二字）。
 * 没有数据时后端返回 null，页面必须容忍缺失、不许现编。
 */
export interface YaociZhu {
  jing?: string
  src?: string
  notes?: { word?: string; text: string }[]
}

export interface Remedy {
  X: string
  R: string
  R_alt?: string | null
  R_reason: string
  state: string
  state_desc: string
  notes?: string[]
  yongshen?: string
  yongshen_desc?: string
  confidence?: string
  candidates?: string[]
  reason?: string
}

export interface MeihuaGuaData {
  method: string
  method_params: Record<string, unknown>
  ben_gua: GuaBrief
  hu_gua: GuaBrief | null
  bian_gua: GuaBrief | null
  moving_yao: { position: number; yaoci: string; is_yang: boolean; yaoci_zhu?: YaociZhu | null }
  tiyong: {
    ti: number; yong: number
    ti_wuxing: string; yong_wuxing: string
    relation: string; relation_desc: string
  }
  qi_info?: {
    lunar: string; season: string; qi: string
    wuxing_status: Record<string, string>
    day_ganzhi: string; day_zhi: string; day_zhi_wuxing: string
    hour_zhi?: string
  }
  time_info?: { lunar?: string; shichen?: string; solar?: string }
  intent?: { method: string; source: string; reason?: string }
  remedy?: Remedy
  yingqi?: MeihuaYingqi
  chaizi_info?: {
    char: string
    ftbh: number
    decomposition: string[][]
    /** 引擎实际采用的那种拆法（同一字可能多种拆法） */
    used_decomposition?: { left: string[]; right: string[] } | null
  }
  tone_details?: {
    first_half: { char: string; tone: number; tone_name: string }[]
    second_half: { char: string; tone: number; tone_name: string }[]
  }
}

/* ---------- 六爻 ---------- */

export interface LiuyaoLine {
  position: number
  name: string
  yin_yang: number
  type: string
  moving: boolean
  coins: number[]
  gan: string
  zhi: string
  wuxing: string
  liuqin: string
  liushen: string
  shi: boolean
  ying: boolean
  xunkong: boolean
  yuepo: boolean
  bian?: { gan: string; zhi: string; wuxing: string; liuqin: string }
}

export interface LiuyaoYingqiItem { date: string; ganzhi: string; reason: string }

export interface LiuyaoYingqi {
  fa: string
  src: string[]
  yongshen: { liuqin: string; ganzhi: string; wuxing: string; moving: boolean }
  rule: string
  zhiri: LiuyaoYingqiItem[]        // 用神值日
  fenghe: LiuyaoYingqiItem[]       // 与用神作合
  chongri: LiuyaoYingqiItem[]      // 冲用神
  xunkong: boolean
  yuepo: boolean
  chongkong: LiuyaoYingqiItem[]    // 冲空
  shipo: LiuyaoYingqiItem[]        // 实破
  jishen_chong: LiuyaoYingqiItem[] // 忌神受冲
  note: string
}

export interface LiuyaoGuaData {
  method: string
  palace: string
  palace_wuxing: string
  ben_gua: GuaBrief
  bian_gua: GuaBrief | null
  moving_positions: number[]
  lines: LiuyaoLine[]
  time_info: {
    solar: string; lunar: string
    year_ganzhi: string; month_ganzhi: string; day_ganzhi: string; hour_ganzhi: string
    day_stem: string; month_branch: string; xunkong: string
  }
  markers: string[]
  gua_shen: number | null
  remedy?: (Remedy & {
    yongshen?: string
    yongshen_desc?: string
    confidence?: string
    candidates?: string[]
    matched?: { kw: string; liuqin: string; layer: string }[]
    details?: Record<string, unknown>
    逐爻细看?: LiuyaoPerLineRow[]
  }) | null
  yingqi?: LiuyaoYingqi | null
}

export interface LiuyaoPerLineRow {
  position: number
  name: string
  六神: string
  六亲: string
  干支: string
  五行: string
  卦位: string
  角色: string
  动静: string
  旬空: boolean
  月破: boolean
  兽性: string
  断语: { text: string; src: string; kind: string; plain: string }[]
  有专断: boolean
  无专断说明: string
}

/* ---------- 八字 ---------- */

export interface BaziCangGan { gan: string; wuxing: string; shishen: string }

export interface BaziTexture {
  yinyang: string
  han_nuan: string
  zao_shi: string
  tags: string
  tixiang?: string
  note?: string
  src?: string
  /** 燥湿：湿／燥／歧异／条件性（地支独有；歧异＝源间方向相反，故分列不择一） */
  zao_shi_state?: string
  /** 逐载体分列：每个载体的赋值各挂自己的出处，不合成一个结论 */
  zao_shi_sources?: { carrier: string; value: string; src: string }[]
  zao_shi_strength?: string
  tag_zao_shi?: string
}

export interface BaziPillar {
  label: string
  ganzhi: string
  gan: string
  zhi: string
  gan_wuxing: string
  zhi_wuxing: string
  nayin: string
  shishen_gan: string
  canggan: BaziCangGan[]
  dishis: string
  self_sit: string
  xunkong: string
  is_kong: boolean
  shensha: string[]
  gan_texture?: BaziTexture
  zhi_texture?: BaziTexture
}

export interface BaziLiuNian {
  year: number; age: number; ganzhi: string
  gan: string; zhi: string; gan_shishen: string; shensha: string[]
}

export interface BaziDayunStep {
  index: number; ganzhi: string; gan: string; zhi: string
  gan_shishen: string; shensha: string[]
  start_age: number; end_age: number; start_year: number; end_year: number
  liunian: BaziLiuNian[]
}

export interface BaziXiji {
  tier: string
  from_ge: string | null
  score: number
  adjust_marks: string[]
  steps: { step: string; title: string; logic: string; score: number }[]
  layers: { yongshen: string; xishen: string; xianshen: string; choushen: string; jishen: string }
  layers_meta: Record<string, { wuxing: string[]; note: string }>
  wuxing_summary: {
    tally: string; missing: string[]; missing_txt: string
    like_missing: string[]; like_note: string
  } | null
  /** 特殊格局判定结果（真/假从与成格说明；非特殊格局为空） */
  ge_quality?: string
  ge_note?: string
  ge_basis?: string
  /** 命局三参考系（供判定链展示：扶抑 F/J、调候 T0 与整串药单） */
  mingju?: {
    F: string[]; J: string[]; T0: string[]
    t0_list: string[]; t0_src: string
    tier: string; from_ge: string
    day_master_wx?: string; month_wx?: string
  }
  /** 喜忌整合视图：按五行聚合、带维度来源标签；冲突行挂裁定语（后端 layers_view） */
  layers_view?: {
    wx: string
    items: { role: string; role_label: string; source: '调候' | '扶抑' | '格局'; note: string }[]
    ruling?: string
  }[]
}

export interface BaziData {
  method: string
  solar: string
  lunar: string
  shengxiao: string
  gender: string
  gender_code: number
  day_master: { gan: string; wuxing: string; yinyang: string }
  bazi: BaziPillar[]
  xunkong: string
  wuxing_tally: Record<string, number>
  shensha: string[]
  geju: { name: string; basis: string }
  tiaohou: { gan: string; month: string; yongshen: string; wuxing: string[]; note: string }
  xiji: BaziXiji
  input: { calendar: string; longitude: number; raw: string; leap_month?: boolean }
  dst: { applied: boolean; recorded?: string; restored?: string; note?: string } | null
  true_solar: {
    solar_used: string; original: string
    longitude: number; lon_correction: number; eot: number
  } | null
  dayun: {
    forward: boolean
    start: { years: number; months: number; days: number; solar: string; lunar: string }
    steps: BaziDayunStep[]
  }
  gong: {
    minggong: { ganzhi: string; nayin: string }
    taiyuan: { ganzhi: string; nayin: string }
    shengong: { ganzhi: string; nayin: string }
    taixi: { ganzhi: string; nayin: string }
  }
  /** 改运链·出生年天地运气（五运六气；只作背景展示与调养参考，不进判定） */
  yunqi?: YunqiInfo
  /** 改运链·出生地空间环境气（经纬度→五方之性；只作背景展示） */
  dili?: DiliInfo
}

/* ---------- 改运链 · 五运六气与空间环境气 ---------- */

export interface YunqiInfo {
  ganzhi: string
  中运: { 五音: string; 五行: string; 太过不及: string }
  司天: string
  在泉: string
  司天五行: string
  在泉五行: string
  特殊: string[]
  label: string
  化数?: { 司天: string; 中运: string; 在泉: string }
  药食宜?: { 上: string; 中: string; 下: string }
  胜复?: string
  灾宫?: string
  书证?: string
}

export interface DiliInfo {
  方位?: string
  五行?: string
  方性?: string
  书证?: string
  界值说明?: string
  地势高下?: string
  备注?: string
}

/* ---------- 命局校验 ---------- */

export interface MingjuHit {
  ref: string | null
  target?: string
  rel?: string | null
  net: string
  label: string
  semantic: string
  handle: string
  tip: string
}

/** 建议维度：方位 / 颜色 / 数字 / 物件（分当旺·次旺·静物）/ 质地（两味分列）等 */
export interface SuggestDimension {
  values?: string[]
  nums?: { 生数?: number; 成数?: number; 河图?: string }
  items?: { 当旺?: string[]; 次旺?: string[]; 静物?: string[] }
  flavors?: { 干?: string; 标签?: string; 取味?: string; 体象?: string; src?: string }[]
}

export interface FlowCell {
  grade?: string
  note?: string
  src?: string
  combined?: string
  conflict?: boolean
  conflict_note?: string
  conflict_suppressed?: string
  /** 乘侮（克边三值：正克/乘/侮；只挂在命中档，后端 wuxing_flow.py:433） */
  chengwu?: { value: string; note?: string; att?: string; dfd?: string } | null
  /** 生边三值（正生/母多灭子/子旺侮母；后端 wuxing_flow.py:473） */
  sheng_three?: { value: string; note?: string } | null
}

export interface FlowRow {
  state: string
  cells: Record<string, FlowCell | null>
  active: boolean
  hits?: string[]
}

/** 十干阴阳寒暖燥湿细分（干体性；有质地建议时并入味分档列，2026-10） */
export interface FlowYinyangItem {
  gan: string
  yinyang: string
  han_nuan?: string
  zao_shi?: string
  tixiang?: string
  note?: string
}

/** 流动五行判定表的一行（某五行的四边状况与说明书证） */
export interface FlowBlock {
  wx: string
  header: Record<string, string>
  state?: string | null
  state_note?: string
  state_score?: number
  month_state?: { state?: string; note?: string; src?: string }
  branch_notes?: { type: string; pair: string; note: string; src?: string }[]
  branch_missing?: boolean
  flavor?: { gan?: string; basis?: string; note?: string; src?: string }
  rows?: FlowRow[]
  tongguan_src?: string
  qualities?: { note: string; src?: string }[]
  yinyang?: { items?: FlowYinyangItem[] }
}

/** 断言：可逐条标记应验/未验/反向的对象 */
export interface Claim {
  id: string
  type: string
  text: string
  rule: string
  params: string[]
  verifiability: string
  since: string
  until: string
  src: string
}

export interface DateDay {
  date: string
  ganzhi: string
  gan_wx: string
  zhi_wx: string
  day_wx: string
  state: string
  yiji: '宜' | '平' | '忌'
  reasons: { reason: string; src: string }[]
}

export interface DateTable {
  tier: string
  n_days: number
  start: string
  days: DateDay[]
  best: string[]
  avoid: string[]
  src: string[]
}

export interface TierContract {
  label: string
  question: string
  length: string
  tone: string
  weight: string
  disclaimer: string
  sections?: string[]
  suggest_dims?: string[]
  content?: string[]
}

export interface TierInfo {
  tier: string
  source: 'manual' | 'auto' | 'ambig'
  auto_tier: string | null
  contract: TierContract
  expanded_default: string
}

export interface MingjuBaseline {
  F: WuXing[]
  J: WuXing[]
  T0: WuXing[]
  t0_list: WuXing[]
  t0_src: string
  tier: string
  day_master_wx: string
  month_wx: string
  day_master?: { gan: string; wuxing: string; yinyang: string }
  wuxing_tally: Record<string, number>
  wuxing_tally_hidden: Record<string, number>
  gans: string[]
  zhis: string[]
  month_zhi: string
}

export interface MingjuCheck {
  X: string
  R: string
  R_alt: string | null
  final_R: string
  R_reason: string
  redirect_note: string
  state: string
  state_desc: string
  notes: string[]
  month_wx: string
  day_zhi: string
  baseline: MingjuBaseline | null
  adjudication: {
    net: '顺' | '平' | '逆'
    level: 'green' | 'yellow' | 'red_yellow' | 'red'
    gate: 'pass' | 'limited' | 'block'
    decision: string
    hits: MingjuHit[]
    tiao_active: boolean
  } | null
  liunian?: {
    ganzhi: string; wx: string; strength: string; weight: number
    effective: boolean; effect: 'none' | 'drag' | 'boost'
    from_ge_table?: { role: string; verdict: 'good' | 'warn' | 'bad'; reason: string; src: string } | null
    notes: string[]
  }
  date_table?: DateTable | null
  tier?: TierInfo
  /** 改运链·天地气背景（当年运气＋出生年运气＋出生地空间气；只作调养参考，不进判定） */
  yunqi?: {
    当年?: YunqiInfo
    出生年?: YunqiInfo | null
    空间?: DiliInfo | null
  } | null
  /** 「按最终处方」栏应期（命局改方后的五行当值之日，工程口径；后端 main.py:3039） */
  yingqi_final?: YingqiItem[]
  /** 建议：按五行分维度（方位/颜色/数字/物件/饮食/职业/健康/卦象/屋宅/四时/天干/地支/质地
      以及该五行的 src 出处键表）。后端 wuxing_suggest.py 按 {五行: {维度: 值}} 返回，
      维度形状互不相同（数组/对象/嵌套），前端按维度名分派渲染，故这里保持宽松类型。 */
  suggestions?: Record<string, Record<string, unknown>>
  /** 流动五行判定表（每档位的生克标注与"为何不告警"的记名） */
  flow?: FlowBlock[]
  claims?: Claim[]
  log_id?: number
  rules_version?: string
  weights_version?: string
}

/* ---------- 通用反馈事件（降级 / 截断 / 回检） ---------- */

export interface DegradeInfo {
  message: string
  hint: string
  scope?: string
  used?: number | null
  limit?: number | null
  resets_at?: string
}

export interface VerifyIssue {
  level: string
  code?: string
  detail: string
  items?: { word?: string; wx?: string; snippet?: string }[]
}

export interface VerifyInfo {
  kind: 'verify' | 'truncated'
  ok?: boolean
  summary?: string
  issues?: VerifyIssue[]
  message?: string
  hint?: string
  limit?: number
}
