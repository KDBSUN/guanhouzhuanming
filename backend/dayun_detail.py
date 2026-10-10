# -*- coding: utf-8 -*-
"""
大运流年详批（事业 / 财运 / 感情）——确定性引擎
==============================================
定位（确定性归代码，语言归 AI）：
  本模块把「大运流年详批」里**一切可计算的部分**算定——大运/流年干支十神、喜忌定性、
  原局结构成立与否（官印相生等六组）、引动哪柱、驿马/桃花/禄刃/财库当值、
  重点年份筛选的硬条件、重点年份十二流月的干支十神喜忌。
  AI 只负责把这些算定的事实讲成人话，并补「具体事件 / 1–10 评分 / 一句话标题 /
  路径推演」——**这四类无逐字书证、不可复现，属 AI 语言层**，提示词要求逐条标注
  「AI 推断，非书证」。

规则来源：站长提供的四个技能（D:\\DSH\\skills\\使用\\玄学\\bazi\\ 下 事业/财运/感情/
强弱喜忌）的规则表，经 books/ 逐字回源订正后采纳。核对记录：技能自称 38 条古籍引文，
31 条逐字命中、7 条义同文异（已按库内原文改写），细节见 docs/大运流年详批规则登记.md。

书证锚点（本模块与提示词引用的篇名全部在库内逐字可查）：
  · 十神分论：渊海子平·论正财 / 论偏财 / 论印绶 / 论食神 / 论伤官 / 论劫财 / 论偏官即七杀
  · 喜忌定吉凶：《子平真诠·论用神》「为我所喜，枭伤七煞，皆为吉神；犯我所忌，
    正官财印，同为恶物」（喜用为吉、忌神为凶的总门）
  · 结构六组：《子平真诠·论用神成败救应》《论用神》
  · 驿马：渊海子平·论驿马；桃花（咸池）断语：渊海子平·络绎赋；羊刃：渊海子平·论羊刃
  · 财库：子平真诠·论墓库刑冲之说——「财官入库无冲不发之说，最为流俗谬谈」，
    「故财官属土，冲则库启」；重在透干会支，非赖刑冲
  · 配偶星活看：子平真诠·论妻子「从财之喜忌看妻宫，非必以财为妻也」
  · 神煞为辅：子平真诠·论星辰无关格局「神煞吉凶，无关祸福」

站内口径：本子系统（八字大运流年详批）**接入 刑、害、破**——与梅花/命卦校验子系统的
  「刑害不接入」口径不同：详批的关系表直接来自站长给定的技能规则与成品（成品逐年原文
  即含 丑午害、未戌刑、卯午破、寅巳刑 等）。书证：渊海子平·论天干相合 / 论十二支六合 /
  论十二支三合 / 论十二支相冲 / 论十二支相穿（即六害）/ 论十二支相刑；子平真诠·
  论刑冲会合解法（三会六合）；六破见三命通会与穷通宝鉴评注徐注命例「午酉相破」；
  天干相冲（甲庚/乙辛/丙壬/丁癸）库内未查到专章（查过渊海、子平真诠、三命通会、
  穷通宝鉴），按技能规则表采用，标注为工程口径。
"""
from lunar_python import Solar

from bazi_engine import (GAN_WUXING, GROUP_OF, KE, LU, SANHE_RULE, SHENG, YANGREN, ZHI_WUXING,
                         build_bazi_paipan, gan_shishen_yun)
from wuxing_quality import SIX_CHONG, ZHI_CANGGAN

PILLAR_LABELS = ["年柱", "月柱", "日柱", "时柱"]
DIMENSIONS = {"shiye": "事业", "caiyun": "财运", "ganqing": "感情"}
MARITAL = ("单身", "恋爱中", "已婚")

SIX_HE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯",
          "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}
WUHE_GAN = {"甲": "己", "己": "甲", "乙": "庚", "庚": "乙", "丙": "辛", "辛": "丙",
            "丁": "壬", "壬": "丁", "戊": "癸", "癸": "戊"}
KU_OF = {"木": "未", "火": "戌", "金": "丑", "水": "辰", "土": "辰"}

# 天干相冲（四冲）：库内未查到专章，按技能规则表采用（工程口径）
GAN_CHONG = {"甲": "庚", "庚": "甲", "乙": "辛", "辛": "乙", "丙": "壬", "壬": "丙", "丁": "癸", "癸": "丁"}

# 三合组 → 中神（旺支）：半合＝两支中含中神；拱＝缺中神（渊海·论十二支三合）
SANHE_GROUPS = {"申子辰": "子", "寅午戌": "午", "巳酉丑": "酉", "亥卯未": "卯"}
# 三会方局（子平真诠·论刑冲会合解法「会者，三会也」；穷通宝鉴评注「东方寅卯辰，春令也」）
SANHUI_GROUPS = {"寅卯辰": "木", "巳午未": "火", "申酉戌": "金", "亥子丑": "水"}
# 三刑（恃势/无恩/无礼）+ 自刑（渊海·论十二支相刑）
XING_PAIRS = {("寅", "巳"), ("巳", "申"), ("申", "寅"),
              ("丑", "戌"), ("戌", "未"), ("未", "丑"),
              ("子", "卯"), ("卯", "子")}
SELF_XING = ("辰", "午", "酉", "亥")
# 六害＝十二支相穿（渊海·论十二支相穿）
HAI_PAIRS = {("子", "未"), ("未", "子"), ("丑", "午"), ("午", "丑"), ("寅", "巳"), ("巳", "寅"),
             ("卯", "辰"), ("辰", "卯"), ("申", "亥"), ("亥", "申"), ("酉", "戌"), ("戌", "酉")}
# 六破（三命通会；穷通宝鉴评注徐注命例「午酉相破」）
PO_PAIRS = {("子", "酉"), ("酉", "子"), ("午", "卯"), ("卯", "午"), ("辰", "丑"), ("丑", "辰"),
            ("未", "戌"), ("戌", "未"), ("寅", "亥"), ("亥", "寅"), ("巳", "申"), ("申", "巳")}

# 补身现实对应（技能·全年命理总览骨架「现实补身三件事」的固定语汇表）
WX_REAL = {
    "印": "学历证书、技能资质、贵人平台",
    "比劫": "强身健体、团队伙伴、过硬技术",
    "食伤": "技术表达、作品输出、节制耗损防过劳",
    "财": "经营理财、财务纪律（不投机不借贷）",
    "官杀": "守规矩不硬碰领导、规范担责",
}
SHISHEN_GROUP_OF_WX = {  # 五行 → 十神类（日主视角，供补身表用）
    "生我": "印", "我生": "食伤", "我克": "财", "克我": "官杀", "同我": "比劫",
}


def _pair_hit(a, b, pairs) -> bool:
    """无序对查表：任一方都在表内算命中。"""
    return (a, b) in pairs or (b, a) in pairs


def _gan_rel(a: str, b: str) -> str:
    """天干 a 对天干 b 的关系（成品口径：X生Y / X克Y / XY冲 / XY合 / XY伏吟）。"""
    if not a or not b:
        return ""
    if a == b:
        return "%s伏吟" % a
    if WUHE_GAN.get(a) == b:
        return "%s%s合" % (a, b)
    if GAN_CHONG.get(a) == b:
        return "%s%s冲" % (a, b)
    wa, wb = GAN_WUXING.get(a, ""), GAN_WUXING.get(b, "")
    if wa and wb:
        if SHENG.get(wa) == wb:
            return "%s生%s" % (a, b)
        if KE.get(wa) == wb:
            return "%s克%s" % (a, b)
    return ""


def _zhi_rel(a: str, b: str) -> str:
    """地支 a 对地支 b 的关系（成品口径：六合/六冲/三合/半合/拱/三会/半会/相刑/自刑/相害/相破/伏吟）。"""
    if not a or not b:
        return ""
    if a == b:
        return "伏吟（自刑）" if a in SELF_XING else "伏吟"
    rels = []
    if SIX_HE.get(a) == b:
        rels.append("六合")
    if SIX_CHONG.get(a) == b:
        rels.append("六冲")
    for group, mid in SANHE_GROUPS.items():
        if a in group and b in group:
            rels.append("半合（%s局）" % group if (a == mid or b == mid)
                        else "拱%s（%s局）" % (mid, group))
            break
    if not rels:
        for group, wx in SANHUI_GROUPS.items():
            if a in group and b in group:
                rels.append("半会%s（%s方）" % (group, wx))
                break
    if _pair_hit(a, b, XING_PAIRS):
        rels.append("相刑")
    if _pair_hit(a, b, HAI_PAIRS):
        rels.append("相害")
    if _pair_hit(a, b, PO_PAIRS):
        rels.append("相破")
    return "、".join(rels)


def _cheng_ju(year_zhi: str, pool: list) -> list:
    """三合/三会成局检测：流年支参与，且三支齐全（原局四支 + 大运支 + 流年支）。"""
    out = []
    zhis = list(pool) + ([year_zhi] if year_zhi and year_zhi not in pool else [])
    for group, mid in SANHE_GROUPS.items():
        if year_zhi in group and all(z in zhis for z in group):
            out.append("三合%s局成（%s）" % (group, _sanhe_wx(group)))
    for group, wx in SANHUI_GROUPS.items():
        if year_zhi in group and all(z in zhis for z in group):
            out.append("三会%s方局成（%s）" % (group, wx))
    return out


def _sanhe_wx(group: str) -> str:
    return {"申子辰": "水", "寅午戌": "火", "巳酉丑": "金", "亥卯未": "木"}.get(group, "")

# 十神集合（本模块自用；"官杀"＝正官+七杀，"财"＝正财+偏财，"印"＝正印+偏印）
GODS = {
    "比劫": ("比肩", "劫财"), "食伤": ("食神", "伤官"), "财": ("正财", "偏财"),
    "官杀": ("正官", "七杀"), "印": ("正印", "偏印"),
}
PEIOU_STAR = {"男": ("财", "配偶星（男命财星）"), "女": ("官杀", "配偶星（女命官杀）")}


# ============================================================
# 规则表（提示词与展示的单一来源；src 全部在库内逐字可查）
# ============================================================
def _rules():
    """三维度规则表。骨架项数：事业 14 / 财运 14 / 感情 11（照技能骨架）。"""
    return {
        "shiye": {
            "意象": [
                ("正官", "职位、权柄、规则、管理、秩序、组织",
                 "晋升、掌权、职务稳定、编制内", "压力、管制、处罚、领导压制、官非",
                 "渊海子平·论偏官即七杀"),
                ("七杀", "竞争、魄力、威权、高压、变革",
                 "权柄威势、攻坚克难、杀刃相济", "被压制、排挤、危机、工作强度失控",
                 "渊海子平·论偏官即七杀"),
                ("正印", "学历、证书、资格、文书、名誉",
                 "学习考证、得文凭、贵人提携、平台", "依赖、保守、停滞、缺乏进取",
                 "渊海子平·论印绶"),
                ("偏印", "专业、偏门技能、研究、思考",
                 "独特技术、冷门资质、专业深度", "孤僻多疑、思虑过度、枭神夺食坏财源",
                 "渊海子平·论印绶"),
                ("食神", "表达、技艺、产品、温和输出",
                 "才华发挥、业绩产出、被认可", "宣泄过度、不思进取", "渊海子平·论食神"),
                ("伤官", "创意、技术、反规则、才华外露",
                 "创新、技术岗、业绩、改换赛道", "伤官见官、与领导冲突、激进闯祸",
                 "渊海子平·论伤官"),
                ("正财", "稳定工资、正当收入、项目经营",
                 "薪酬上升、业绩、财生官得权", "为钱所累、因钱担责", "渊海子平·论正财"),
                ("偏财", "大额收入、市场、投资、经营",
                 "项目收益、市场化发展", "财来财去、投机风险、财坏印", "渊海子平·论偏财"),
                ("比肩", "同辈、团队、竞争、自主",
                 "团队协作、自主创业", "竞争分利、单打独斗、固执", "渊海子平·论劫财"),
                ("劫财", "竞争、争夺、执行力",
                 "冲破僵局、开拓市场", "比劫争财、同行相害、破财", "渊海子平·论劫财"),
            ],
            "有利结构": [
                ("官印相生", "官星生印、印星生身", "有实权而合法，学历证书平台加持，体制内晋升",
                 "子平真诠·论用神成败救应"),
                ("杀印相生", "七杀生印、印星化杀", "高压中成长，危机变机遇，权柄显赫",
                 "子平真诠·论用神成败救应"),
                ("食伤制杀", "食伤克制七杀", "以能力技术化解竞争压力，技术立身", "子平真诠·论用神"),
                ("伤官生财", "伤官泄秀生财", "才华变现，靠技术表达产品赚钱", "子平真诠·论用神成败救应"),
                ("财生官", "财星生官星", "业绩收入带来职级提升，财官两得", "子平真诠·论用神成败救应"),
                ("杀刃相济", "七杀配羊刃", "魄力加执行力，适合攻坚、创业、掌权",
                 "渊海子平·论羊刃"),
            ],
            "不利结构": [
                ("伤官见官", "伤官与正官同现", "与领导制度冲突、犯上、丢职风险",
                 "子平真诠·论用神成败救应（例外：金水伤官，金寒水冷，调候为急，可以见官）"),
                ("官杀混杂", "正官七杀并见", "职务混乱、多头管理、抉择两难、压力大",
                 "渊海子平·论偏官即七杀"),
                ("枭神夺食", "偏印克食神", "才华被压抑、财路被断、事业卡顿",
                 "子平真诠·论用神成败救应"),
                ("比劫争财", "比劫夺财星", "利益被分、同行竞争、合伙破财", "渊海子平·论劫财"),
                ("财坏印", "财星克印星", "因利弃学弃平台、证书学历受扰、贵人受损",
                 "渊海子平·论印绶"),
                ("杀重身轻", "七杀太旺身弱难担", "被压制、压力超载、健康拖累",
                 "渊海子平·论偏官即七杀"),
            ],
            "宫位": [("年柱", "祖业、早年环境、第一份职业的背景、单位出身"),
                    ("月柱", "事业宫/财帛之源，青年期、正职、单位与环境；被引动多主职务变动"),
                    ("日支", "自身根基、夫妻宫（牵动生活重心），也主内心定力"),
                    ("时柱", "中晚年、下属、成果归属、退休前的事业收成")],
            "场景": [("升职", "官印相生、官星为喜得生、月柱引动、印星落实"),
                    ("跳槽/变动", "驿马、六冲、伤官（主动辞）或七杀（被迫走）"),
                    ("考证/考编/进修", "印星当值（正印为文凭）、官星为编制"),
                    ("创业/副业", "偏财、劫财、食伤生财、驿马、羊刃"),
                    ("领导关系", "官星（正官吉/七杀凶）、伤官见官（冲突）"),
                    ("同事竞争", "比劫（助力/争财）、劫财透出"),
                    ("收入", "财星（正财稳、偏财浮动）、伤官生财、财生官"),
                    ("风险", "官杀为忌、伤官见官、杀重身轻、枭神夺食")],
            "禁止": ["只用「事业有机遇」「注意小人」式模糊话术",
                    "脱离强弱喜忌谈吉凶",
                    "每个判断不说十神/宫位/生克合冲依据",
                    "不按骨架「大运关系/原局关系/成局」照抄而自行发明合冲刑害",
                    "编造具体事件当作必然（事件属 AI 推断，必须标注）"],
            "骨架": ["流年干支十神（标题）", "喜忌", "与原局大运关系", "引动", "工作环境",
                   "职位趋势", "收入", "领导关系", "同事与竞争", "适合行动", "具体事件",
                   "风险", "评分", "依据"],
        },
        "caiyun": {
            "意象": [
                ("正财", "稳定工资、正当收入、家庭财",
                 "薪酬上升、财源稳定、财生官得权", "为钱所累、因钱担责、财多身弱",
                 "渊海子平·论正财"),
                ("偏财", "市场、投资、经营、横财",
                 "项目收益、投资得利、市场化财", "财来财去、投机亏损、财坏印",
                 "渊海子平·论偏财"),
                ("食神", "技艺生财、温和输出",
                 "技术变现、产品业绩、细水长流", "泄身过度、财源疲软", "渊海子平·论食神"),
                ("伤官", "才华变现、创业、反规则求财",
                 "副业、创业、靠创新赚钱", "伤官生财被劫、激进破财", "渊海子平·论伤官"),
                ("正印", "文凭、资质、平台、贵人",
                 "证书学历带来收入、贵人生财、承财能力提高", "依赖、守旧、财路窄",
                 "渊海子平·论印绶"),
                ("偏印", "偏门专业、策划、资源",
                 "冷门技术生财、特殊资质", "枭神夺食断财源、思虑误财", "渊海子平·论印绶"),
                ("比肩", "同辈合作、自主经营",
                 "合伙得力、自主创业、承财稳固", "竞争分利、固执投资", "渊海子平·论劫财"),
                ("劫财", "竞争、争夺、破财之神",
                 "打破僵局、抢到市场", "比劫争财、被夺财、合伙破财", "渊海子平·论劫财"),
                ("正官", "职位工资来源、财生官",
                 "职务收入稳、财官相生", "财生官杀攻身、为职位花钱", "渊海子平·论偏官即七杀"),
                ("七杀", "高压竞争、风险经营",
                 "高风险高回报、魄力获利", "财生杀、因财惹祸、压身破财",
                 "渊海子平·论偏官即七杀"),
            ],
            "有利结构": [
                ("食伤生财", "有技艺产品源源生财", "财源活", "子平真诠·论用神"),
                ("财生官", "财星生官，财官相生", "名利兼得；官杀为忌则财生杀攻身",
                 "子平真诠·论用神成败救应"),
                ("身旺任财", "日主旺能任财", "承财正理，担得住", "子平真诠·论妻子"),
            ],
            "不利结构": [
                ("比劫夺财", "比劫旺而财为喜用", "合伙破财、被劫", "渊海子平·论劫财"),
                ("财破印", "财克印", "为财损学历平台贵人", "渊海子平·论印绶"),
                ("财多身弱", "财旺身弱", "富屋贫人，钱多难安；反喜比劫分财帮身",
                 "子平真诠·论妻子"),
                ("财生官杀攻身", "财为忌、生官杀", "因财惹事、负债压力", "渊海子平·论偏官即七杀"),
            ],
            "场景": [("收入明显增加", "财星为喜得生、食伤生财、财库引动、禄到"),
                    ("跳槽涨薪", "财星印星引动、驿马冲（良性）"),
                    ("副业/创业", "偏财、伤官、劫财、驿马"),
                    ("买房/置业/资产", "财星入命且能担、财库透干会支得用、印星（不动产）"),
                    ("破财/负债/投资失误", "比劫夺财、财生官杀攻身、财多身弱"),
                    ("进账留不住", "比劫争财、财被合走、财星虚浮")],
            "禁止": ["见财星即断发财（财星为忌、身弱不担财时财旺反主支出负债）",
                    "脱离身强身弱和喜忌",
                    "把财星年份说成桃花年份",
                    "空话（「可能会有一些机会」式）",
                    "不按骨架关系照抄而自行发明合冲刑害；编造事件不作标注"],
            "骨架": ["流年干支十神（标题）", "喜忌", "与大运关系", "与原局作用",
                   "引动（财星财库禄刃宫位）", "结构", "收入趋势", "财富来源", "主要支出",
                   "适合行动", "具体事件", "风险等级", "评分", "依据"],
        },
        "ganqing": {
            "意象": [
                ("比肩", "同辈、竞争、自我", "平等伴侣、知己", "竞争第三者、固执",
                 "渊海子平·论劫财"),
                ("劫财", "争夺、第三方", "打破僵局", "争夫/争财、三角", "渊海子平·论劫财"),
                ("食神", "温柔、魅力输出", "甜蜜、会经营", "过度付出、讨好", "渊海子平·论食神"),
                ("伤官", "魅力表达、挑剔", "有吸引力、敢爱", "克官（女命伤夫）、挑剔冲突",
                 "渊海子平·论伤官"),
                ("印星", "稳定、依赖、包容", "婚姻安稳、被照顾", "依赖成性、疏离冷淡",
                 "渊海子平·论印绶"),
                ("财星", "女命争夺丈夫、现实", "现实考量", "感情功利", "渊海子平·论正财"),
                ("官杀", "男命社会压力", "责任担当", "权威压制、易争吵", "渊海子平·论偏官即七杀"),
            ],
            "铁律": ["配偶星活看：从财之喜忌看妻宫，非必以财为妻也；女命以用神为夫星，不必定用官"
                     "（子平真诠·论妻子）",
                     "桃花（咸池）、驿马属星辰，为辅不主导（子平真诠·论星辰无关格局「神煞吉凶，无关祸福」；"
                     "驿马主迁动、异地之象，见渊海子平·论驿马）",
                     "夫妻宫冲≠必然离婚：须结合喜忌与岁运救应（子平真诠·论妻子）",
                     "不机械套用「桃花=恋爱」「财星=结婚」「夫妻宫冲=离婚」"],
            "场景": [("容易遇到对象", "配偶星引动、桃花为喜、合动"),
                    ("容易确定关系", "配偶星＋合夫妻宫＋喜用"),
                    ("订婚/见家长", "印星、正官吉"),
                    ("结婚登记", "配偶星得力＋夫妻宫安稳＋喜用齐备"),
                    ("分手/矛盾爆发", "冲夫妻宫、忌神引动"),
                    ("旧情复燃", "合、伏吟"),
                    ("竞争者/三角", "劫财、争合")],
            "禁止": ["见桃花断正缘；见夫妻宫冲断离婚；见配偶星现断结婚",
                    "脱离身强身弱和喜忌",
                    "「会有机会」「遇到不错的人」式空话",
                    "不按骨架关系照抄而自行发明合冲刑害；臆测用户婚恋状态（单身/恋爱中/已婚须用户提供）"],
            "骨架": ["流年干支十神（标题）", "喜忌", "与大运关系", "与原局作用（配偶星/夫妻宫/桃花位）",
                   "刑冲合害（本产品只报合冲会）", "桃花强度", "桃花性质", "按当前状态", "适合行动",
                   "易发生", "具体事件+评分+依据"],
        },
    }


RULES = _rules()


# ============================================================
# 基础判定
# ============================================================
def _wx_xi(wx: str, F, J, T0) -> str:
    """五行喜忌定性（书：《子平真诠·论用神》喜用为吉、忌神为凶）。"""
    if wx in (T0 or []):
        return "调候"
    if wx in (F or []):
        return "喜"
    if wx in (J or []):
        return "忌"
    return "闲"


def _zhi_benqi(dm: str, zhi: str):
    """地支本气天干的十神与五行。"""
    cg = ZHI_CANGGAN.get(zhi) or []
    gan = cg[0][0] if cg else ""
    return {"gan": gan, "wuxing": GAN_WUXING.get(gan, ""),
            "shishen": gan_shishen_yun(dm, gan) if gan else ""}


def _god_present(pillars, dm: str, names) -> dict:
    """某类十神在四柱的透藏情况（透干=天干直现，藏=地支藏干，均不含日主位）。"""
    tou = [p["gan"] for i, p in enumerate(pillars)
           if i != 2 and gan_shishen_yun(dm, p["gan"]) in names]
    cang = []
    for i, p in enumerate(pillars):
        for c in p.get("canggan") or []:
            if c.get("shishen") in names:
                cang.append({"gan": c["gan"], "zhi": p["zhi"], "柱": PILLAR_LABELS[i]})
    return {"透干": tou, "藏": cang}


def _struct_status(a, b) -> str:
    if a["透干"] and b["透干"]:
        return "成"
    if (a["透干"] or a["藏"]) and (b["透干"] or b["藏"]):
        return "半成"
    return "未成"


def _yangren_present(zhis, dm) -> dict:
    z = YANGREN.get(dm, "")
    hits = [zh for zh in zhis if zh == z]
    return {"透干": [], "藏": [{"gan": "", "zhi": z}] if hits else []}


# ============================================================
# 流月
# ============================================================
def _months_of_year(dm: str, year: int) -> list:
    """一年十二个节气月的 月干支 + 十神 + 五行（按公历每月 15 日取样——
    节令月的边界（节）都在每月 4–9 日，15 日必落在当月节令月内，故 12 个月各取一个）。"""
    out = []
    for m in range(1, 13):
        l = Solar.fromYmd(year, m, 15).getLunar()
        gz = l.getMonthInGanZhi()
        b = _zhi_benqi(dm, gz[1])
        out.append({"月": "%d月" % m, "干支": gz, "干十神": gan_shishen_yun(dm, gz[0]),
                    "支十神": b["shishen"], "五行": GAN_WUXING.get(gz[0], "")})
    return out


# ============================================================
# 主入口
# ============================================================
def dayun_scaffold(birth: dict, dimension: str, year_from: int, year_to: int,
                   marital_status: str = "") -> dict:
    """确定性骨架。birth 与 /api/bazi/paipan 同构；dimension ∈ {shiye,caiyun,ganqing}。"""
    dim = (dimension or "").strip().lower()
    if dim not in DIMENSIONS:
        raise ValueError("未知维度: %r" % dimension)
    year_from, year_to = int(year_from), int(year_to)
    if year_to < year_from:
        raise ValueError("结束年必须不早于起始年")
    if year_to - year_from > 60:
        raise ValueError("单次详批年份跨度最多 60 年")

    data = build_bazi_paipan(
        birth.get("year"), birth.get("month"), birth.get("day"),
        birth.get("hour", 12), birth.get("minute", 0), birth.get("gender", 1),
        calendar=birth.get("calendar", "solar"),
        leap_month=birth.get("leap_month", False),
        dst=birth.get("dst", False), true_solar=birth.get("true_solar", False),
        longitude=birth.get("longitude", 120.0))
    pillars = data["bazi"]
    dm = data["day_master"]["gan"]
    dm_wx = data["day_master"]["wuxing"]
    xiji = data["xiji"]
    mj = xiji["mingju"]
    F, J, T0 = mj["F"], mj["J"], mj["T0"]
    tier = mj["tier"]
    tally = mj["wuxing_tally"]
    gender = data["gender"]
    gender_code = birth.get("gender", 1)

    # —— 命理纲线 ——
    def _wx_group(wx: str) -> str:
        """五行相对日主的十神类（生我=印、我生=食伤、我克=财、克我=官杀、同我=比劫）。"""
        if wx == dm_wx:
            return "比劫"
        if SHENG[wx] == dm_wx:
            return "印"
        if SHENG[dm_wx] == wx:
            return "食伤"
        if KE[wx] == dm_wx:
            return "官杀"
        return "财"

    def _buxin_rows(wxs: list, kind: str) -> list:
        out = []
        for w in wxs:
            grp = _wx_group(w)
            out.append({"五行": w, "十神": grp, "性质": kind,
                        "现实": WX_REAL.get(grp, "")})
        return out

    buxin = []
    if F:
        buxin.append(_buxin_rows([F[0]], "第一用神")[0])
    if len(F) > 1:
        buxin.append(_buxin_rows([F[1]], "次喜神")[0])
    for j in (J or [])[:2]:
        buxin.append(_buxin_rows([j], "忌神")[0])
    # 强弱理由素材：月令对日主的生克 + 比劫印根气计数（提示词据此写「强弱」一句的理由）
    month_wx = mj.get("month_wx") or ZHI_WUXING.get(pillars[1]["zhi"], "")
    if month_wx == dm_wx or SHENG.get(month_wx) == dm_wx:
        ling = "得令"
    elif SHENG.get(dm_wx) == month_wx or KE.get(month_wx) == dm_wx:
        ling = "失令"
    else:
        ling = "中和"
    tier_reason = {"月令": "%s（%s月%s）" % (ling, pillars[1]["zhi"], month_wx),
                   "月令长生": pillars[1].get("dishis") or "",
                   "日主字数": tally.get(dm_wx, 0),
                   "生扶字数": sum(tally.get(w, 0) for w in F or []),
                   "克泄耗字数": sum(tally.get(w, 0) for w in (J or []) + [x for x in tally
                                        if x not in (F or []) and x != dm_wx])}

    gangxian = {
        "zao": "乾造" if gender_code == 1 else "坤造",
        "solar": data["solar"], "lunar": data["lunar"],
        "pillars": " ".join("%s%s" % (p["gan"], p["zhi"]) for p in pillars),
        "day_master": dm, "day_master_wx": dm_wx,
        "tier": tier, "from_ge": mj.get("from_ge") or "",
        "F": F, "J": J, "T0": T0,
        "t0_src": mj.get("t0_src", ""),
        "xianshen": [w for w in (xiji.get("layers_meta") or {}).get("xianshen", {}).get("wuxing", [])],
        "起运": data["dayun"]["start"],
        "tally": tally,
        "buxin": buxin,
        "tier_reason": tier_reason,
    }

    # —— 原局底盘（按维度） ——
    zhis = [p["zhi"] for p in pillars]
    yuanju = {"结构": [], "说明": []}
    if dim == "shiye":
        checks = [
            ("官印相生", GODS["官杀"], GODS["印"], "子平真诠·论用神成败救应"),
            ("杀印相生", ("七杀",), GODS["印"], "子平真诠·论用神成败救应"),
            ("食伤制杀", GODS["食伤"], ("七杀",), "子平真诠·论用神"),
            ("伤官生财", ("伤官",), GODS["财"], "子平真诠·论用神成败救应"),
            ("财生官", GODS["财"], ("正官",), "子平真诠·论用神成败救应"),
        ]
        for name, a_g, b_g, src in checks:
            a = _god_present(pillars, dm, a_g)
            b = _god_present(pillars, dm, b_g)
            yuanju["结构"].append({
                "结构": name, "状态": _struct_status(a, b),
                "透藏": "／".join(a["透干"] + ["藏" + c["gan"] for c in a["藏"]] or ["无"]) + " → " +
                        "／".join(b["透干"] + ["藏" + c["gan"] for c in b["藏"]] or ["无"]),
                "src": src})
        # 杀刃相济：七杀透 + 日主羊刃在支
        a = _god_present(pillars, dm, ("七杀",))
        b = _yangren_present(zhis, dm)
        yuanju["结构"].append({
            "结构": "杀刃相济", "状态": "成" if (a["透干"] and b["藏"]) else ("半成" if (a["透干"] or b["藏"]) else "未成"),
            "透藏": "／".join(a["透干"] or ["无"]) + " → 羊刃" + (b["藏"][0]["zhi"] if b["藏"] else "无"),
            "src": "渊海子平·论羊刃"})
        # 宫位快照：月柱（事业宫）被原局何物所克合
        yuanju["宫位"] = {"月柱": pillars[1]["ganzhi"], "月柱十神": pillars[1]["shishen_gan"]}
    elif dim == "caiyun":
        # 财星五行 = 日主所克之五行（我克者为财，渊海子平·论正财）
        cai_wx = KE[dm_wx]
        checks = [
            ("食伤生财", GODS["食伤"], GODS["财"], "子平真诠·论用神"),
            ("财生官", GODS["财"], ("正官",), "子平真诠·论用神成败救应"),
            ("比劫夺财", GODS["比劫"], GODS["财"], "渊海子平·论劫财"),
            ("财破印", GODS["财"], GODS["印"], "渊海子平·论印绶"),
        ]
        for name, a_g, b_g, src in checks:
            a = _god_present(pillars, dm, a_g)
            b = _god_present(pillars, dm, b_g)
            yuanju["结构"].append({
                "结构": name, "状态": _struct_status(a, b),
                "透藏": "／".join(a["透干"] + ["藏" + c["gan"] for c in a["藏"]] or ["无"]) + " → " +
                        "／".join(b["透干"] + ["藏" + c["gan"] for c in b["藏"]] or ["无"]),
                "src": src})
        # 财多身弱：日主弱/极弱 且 财星五行计数 ≥3（工程默认阈值，书给定性未给数量）
        cai_n = tally.get(cai_wx, 0)
        yuanju["结构"].append({
            "结构": "财多身弱",
            "状态": "成" if (tier in ("弱", "极弱") and cai_n >= 3) else "未成",
            "透藏": "财%s（%s%d字）｜日主%s" % (cai_wx, cai_wx, cai_n, tier),
            "src": "子平真诠·论妻子（「财多身弱则须以比劫分财为美」；≥3 字为工程默认阈值）"})
        yuanju["财星"] = {"五行": cai_wx, "库": KU_OF[cai_wx],
                          "喜忌": _wx_xi(cai_wx, F, J, T0)}
    else:  # ganqing
        star_key, star_name = PEIOU_STAR["男" if gender_code == 1 else "女"]
        star_gods = GODS[star_key]
        sp = _god_present(pillars, dm, star_gods)
        # 配偶星五行＝该六亲对应五行（男财＝我克、女官杀＝克我）
        spouse_wx = KE[dm_wx] if star_key == "财" else next(w for w, k in KE.items() if k == dm_wx)
        star_xi = _wx_xi(spouse_wx, F, J, T0)
        ri_zhi = pillars[2]["zhi"]
        ri_b = _zhi_benqi(dm, ri_zhi)
        fuqi = []
        for i, p in enumerate(pillars):
            if i == 2:
                continue
            if SIX_CHONG.get(p["zhi"]) == ri_zhi:
                fuqi.append("%s与日支冲" % PILLAR_LABELS[i])
            if SIX_HE.get(p["zhi"]) == ri_zhi:
                fuqi.append("%s与日支合" % PILLAR_LABELS[i])
        taohua_zhi = None
        for rule_zhi in (pillars[0]["zhi"], ri_zhi):
            rule = SANHE_RULE[GROUP_OF[rule_zhi]]
            for p in pillars:
                if p["zhi"] == rule["咸池"]:
                    taohua_zhi = p["zhi"]
        yuanju["配偶星"] = {
            "星": star_name, "五行": spouse_wx, "喜忌": star_xi,
            "透干": sp["透干"], "藏": ["%s(%s)" % (c["gan"], c["柱"]) for c in sp["藏"]]}
        yuanju["夫妻宫"] = {"日支": ri_zhi, "十神": ri_b["shishen"],
                            "五行": ri_b["wuxing"], "关系": fuqi or ["无冲合"]}
        yuanju["桃花"] = {"支": taohua_zhi or "四柱无咸池"}
        if gender_code == 0:
            sg = _god_present(pillars, dm, ("伤官",))
            yuanju["女命伤官"] = {"透干": sg["透干"],
                                  "状态": "透" if sg["透干"] else "未透",
                                  "src": "渊海子平·络绎赋"}

    # —— 大运表（12 步） ——
    dayun_rows = []
    for st in data["dayun"]["steps"]:
        if not st.get("ganzhi"):
            continue
        dayun_rows.append({
            "index": st["index"], "干支": st["ganzhi"],
            "干十神": st["gan_shishen"],
            "支十神": _zhi_benqi(dm, st["zhi"])["shishen"],
            "干喜忌": _wx_xi(GAN_WUXING.get(st["gan"], ""), F, J, T0),
            "支喜忌": _wx_xi(ZHI_WUXING.get(st["zhi"], ""), F, J, T0),
            "起": st["start_age"], "止": st["end_age"],
            "起年": st["start_year"], "止年": st["end_year"],
            "神煞": st.get("shensha") or [],
        })

    # —— 逐年 ——
    liunian_map = {}
    for st in data["dayun"]["steps"]:
        for ln in st.get("liunian") or []:
            liunian_map[ln["year"]] = {"ln": ln, "dayun": st}

    year_rows = []
    for y in range(year_from, year_to + 1):
        hit = liunian_map.get(y)
        if not hit:
            year_rows.append({"year": y, "note": "超出大运排算范围"})
            continue
        ln, dy = hit["ln"], hit["dayun"]
        g, z = ln["gan"], ln["zhi"]
        b = _zhi_benqi(dm, z)
        dy_g, dy_z = (dy.get("gan") or ""), (dy.get("zhi") or "")
        # 与原局四柱的干支关系（成品「与原局大运 / 与原局作用」逐条素材）
        yuanju_rel = []
        for i, p in enumerate(pillars):
            gr = _gan_rel(g, p["gan"])
            zr = _zhi_rel(z, p["zhi"])
            if gr or zr:
                yuanju_rel.append({"柱": PILLAR_LABELS[i],
                                   "干支": p["ganzhi"],
                                   "关系": [x for x in (gr, zr) if x]})
        dayun_rel = [x for x in (_gan_rel(g, dy_g), _zhi_rel(z, dy_z)) if x]
        chengju = _cheng_ju(z, [p["zhi"] for p in pillars] + [dy_z])
        row = {
            "year": y, "age": ln["age"], "干支": ln["ganzhi"],
            "干十神": ln["gan_shishen"], "支十神": b["shishen"],
            "干五行": GAN_WUXING.get(g, ""), "支五行": ZHI_WUXING.get(z, ""),
            "干喜忌": _wx_xi(GAN_WUXING.get(g, ""), F, J, T0),
            "支喜忌": _wx_xi(ZHI_WUXING.get(z, ""), F, J, T0),
            "大运": dy["ganzhi"] if dy.get("ganzhi") else "",
            "大运关系": dayun_rel,
            "原局关系": yuanju_rel,
            "成局": chengju,
            "神煞": ln.get("shensha") or [],
        }
        if z == LU.get(dm):
            row["禄"] = True
        if z == YANGREN.get(dm):
            row["刃"] = True
        # 维度专属硬条件
        if dim == "caiyun":
            cai_wx = yuanju["财星"]["五行"]
            if GAN_WUXING.get(g) == cai_wx or b["wuxing"] == cai_wx:
                row["财星当值"] = _wx_xi(cai_wx, F, J, T0)
            if z == yuanju["财星"]["库"]:
                row["财库引动"] = True
            if ln["gan_shishen"] in GODS["比劫"] or b["shishen"] in GODS["比劫"]:
                row["比劫当值"] = True
        elif dim == "shiye":
            if ln["gan_shishen"] in GODS["官杀"] or b["shishen"] in GODS["官杀"]:
                row["官杀当值"] = "喜" if _wx_xi(ZHI_WUXING.get(z, ""), F, J, T0) in ("喜", "调候") else "忌"
            if ln["gan_shishen"] == "伤官":
                guan_tou = _god_present(pillars, dm, ("正官",))["透干"]
                if guan_tou:
                    row["伤官见官"] = True
            if ln["gan_shishen"] in GODS["印"] or b["shishen"] in GODS["印"]:
                row["印星当值"] = _wx_xi(GAN_WUXING.get(g, ""), F, J, T0)
        else:
            spouse_wx = yuanju["配偶星"]["五行"]
            if GAN_WUXING.get(g) == spouse_wx or b["wuxing"] == spouse_wx:
                row["配偶星当值"] = yuanju["配偶星"]["喜忌"]
            if "咸池" in (ln.get("shensha") or []):
                row["桃花"] = True
            if any(x["柱"] == "日柱" for x in yuanju_rel):
                row["夫妻宫引动"] = True
        year_rows.append(row)

    # —— 关键年份（成品「〇·二 关键年份速查」）——
    # 吉凶按「十神方向 × 喜用」判：生我/同我（印比）＝吉性；克泄耗（官杀/财/食伤）且非喜用＝凶性。
    # 吉年＝干支皆吉性；险年＝干支皆凶性（工程默认：与成品圈选同向，取全列不挑前几名）。
    def _wx_ji(wx):
        if not wx:
            return "平"
        if wx in F or wx == dm_wx:
            return "吉"
        if wx in (T0 or []) and _wx_group(wx) in ("印", "比劫"):
            return "吉"   # 调候字为生扶类（如冬木丙火）时亦吉
        return "凶"

    def _both(r, kind):
        return _wx_ji(r.get("干五行")) == kind and _wx_ji(r.get("支五行")) == kind

    good_years = [r["year"] for r in year_rows if _both(r, "吉")]
    bad_years = [r["year"] for r in year_rows if _both(r, "凶")]
    key_years = {
        "吉年": good_years,
        "险年": bad_years,
        "筛选": {},  # 维度专属候选（供提示词「四、必须区分的情况/重点年份筛选」用）
    }
    if dim == "shiye":
        key_years["筛选"]["升职候选（官杀为喜当值）"] = [r["year"] for r in year_rows if r.get("官杀当值") == "喜"]
        key_years["筛选"]["变动候选（驿马或月柱被引动）"] = [r["year"] for r in year_rows
                                              if "驿马" in (r.get("神煞") or [])
                                              or any(x["柱"] == "月柱" for x in r.get("原局关系") or [])]
        key_years["筛选"]["风险候选（伤官见官/官杀为忌当值）"] = [r["year"] for r in year_rows
                                               if r.get("伤官见官") or r.get("官杀当值") == "忌"]
        key_years["筛选"]["考证候选（印星为喜当值）"] = [r["year"] for r in year_rows if r.get("印星当值") in ("喜", "调候")]
    elif dim == "caiyun":
        key_years["筛选"]["增收候选（财星为喜当值/财库引动）"] = [r["year"] for r in year_rows
                                            if r.get("财星当值") in ("喜", "调候") or r.get("财库引动")]
        key_years["筛选"]["破财风险（比劫当值且财为喜）"] = [r["year"] for r in year_rows
                                          if r.get("比劫当值") and yuanju["财星"]["喜忌"] in ("喜", "调候")]
        key_years["筛选"]["压力风险（财星为忌当值）"] = [r["year"] for r in year_rows if r.get("财星当值") == "忌"]
    else:
        key_years["筛选"]["遇缘候选（配偶星为喜当值）"] = [r["year"] for r in year_rows
                                         if r.get("配偶星当值") in ("喜", "调候")]
        key_years["筛选"]["桃花年（咸池当值）"] = [r["year"] for r in year_rows if r.get("桃花")]
        key_years["筛选"]["变动风险（夫妻宫被引动）"] = [r["year"] for r in year_rows if r.get("夫妻宫引动")]

    # —— 流月（吉年险年 + 筛选候选，最多 6 年） ——
    liu_yue = {}
    picked = []
    for yrs in [good_years, bad_years] + list(key_years["筛选"].values()):
        for y in yrs:
            if y not in picked:
                picked.append(y)
        if len(picked) >= 6:
            break
    for y in picked[:6]:
        liu_yue[str(y)] = _months_of_year(dm, y)

    return {
        "dimension": dim, "dimension_label": DIMENSIONS[dim],
        "year_from": year_from, "year_to": year_to,
        "marital_status": marital_status if dim == "ganqing" else "",
        "gangxian": gangxian, "yuanju": yuanju,
        "dayun_rows": dayun_rows, "year_rows": year_rows,
        "key_years": key_years, "liu_yue": liu_yue,
        "notes": [
            "本骨架全部由代码确定性计算（干支十神五行、喜忌、结构、合冲刑害破伏吟拱会、成局、神煞、吉年险年、流月）。",
            "具体事件、1–10 评分、一句话标题、路径推演为 AI 推断（无逐字书证、不可复现），由文档页脚统一标注边界。",
            "天干相冲（甲庚/乙辛/丙壬/丁癸）按技能规则表采用；库内未查到专章（工程口径）。",
        ],
    }


# ============================================================
# 规则表 → 提示词块（AI 实收字句，同时是称引基准的一部分）
# ============================================================
def rules_prompt_block(dimension: str) -> str:
    dim = (dimension or "").strip().lower()
    R = RULES[dim]
    L = ["【%s·分析规则（照此取象与断吉凶，不得另立规则）】" % DIMENSIONS[dim]]
    L.append("十神意象（吉象用喜用定、凶象用忌神定；喜忌定吉凶总门＝《子平真诠·论用神》"
             "「为我所喜，枭伤七煞，皆为吉神；犯我所忌，正官财印，同为恶物」）：")
    for name, img, ji_x, xiong_x, src in R["意象"]:
        L.append("· %s＝%s｜喜用：%s｜忌神：%s（%s）" % (name, img, ji_x, xiong_x, src))
    if R.get("有利结构"):
        L.append("有利结构（成立与否已由代码判定并列入骨架，照读）：")
        for name, meaning, point, src in R["有利结构"]:
            L.append("· %s＝%s→%s（%s）" % (name, meaning, point, src))
    if R.get("不利结构"):
        L.append("不利结构（同上，照读）：")
        for name, meaning, point, src in R["不利结构"]:
            L.append("· %s＝%s→%s（%s）" % (name, meaning, point, src))
    if R.get("铁律"):
        L.append("铁律：")
        for t in R["铁律"]:
            L.append("· %s" % t)
    if R.get("宫位"):
        L.append("宫位（引动哪柱照骨架数据读）：")
        for g, meaning in R["宫位"]:
            L.append("· %s＝%s" % (g, meaning))
    if R.get("场景"):
        L.append("场景速查（看什么）：")
        for s, what in R["场景"]:
            L.append("· %s：看 %s" % (s, what))
    L.append("禁止清单：")
    for x in R["禁止"]:
        L.append("· 禁止 %s" % x)
    L.append("")
    L.append("【干支关系表（骨架「大运关系/原局关系/成局」即据此算定；叙述时照用这些术语）】")
    L.append("· 天干五合：甲己合土、乙庚合金、丙辛合水、丁壬合木、戊癸合火（渊海子平·论天干相合）")
    L.append("· 天干相冲：甲庚冲、乙辛冲、丙壬冲、丁癸冲（工程口径）")
    L.append("· 地支六合：子丑合、寅亥合、卯戌合、辰酉合、巳申合、午未合（渊海子平·论十二支六合）")
    L.append("· 地支三合：申子辰水局、亥卯未木局、寅午戌火局、巳酉丑金局（渊海子平·论十二支三合）；"
             "两支且带中神＝半合，两支缺中神＝拱")
    L.append("· 地支三会：寅卯辰东方木、巳午未南方火、申酉戌西方金、亥子丑北方水（子平真诠·论刑冲会合解法）；"
             "两支相邻＝半会")
    L.append("· 六冲：子午冲、丑未冲、寅申冲、卯酉冲、辰戌冲、巳亥冲（渊海子平·论十二支相冲）")
    L.append("· 三刑：寅巳申恃势之刑、丑戌未无恩之刑、子卯无礼之刑；辰午酉亥自刑（渊海子平·论十二支相刑）")
    L.append("· 六害（相穿）：子未、丑午、寅巳、卯辰、申亥、酉戌相穿（渊海子平·论十二支相穿）")
    L.append("· 六破：子酉、午卯、辰丑、未戌、寅亥、巳申相破（三命通会；穷通宝鉴评注徐注命例「午酉相破」）")
    L.append("· 伏吟＝干支重现；反吟＝干支相冲（同上各条）")
    L.append("· 注意区分「相害」与「相穿」是同物异名：骨架统一称「相害」。")
    return "\n".join(L)
