# -*- coding: utf-8 -*-
"""六爻格局补算：把提示词一直在讲、代码却从没算过的判据算出来，交 AI 只读。

为什么必须有这个模块
--------------------
断卦提示词里早就写着"元神化进神有力""忌神动化退神无力""静爻旺相受日冲为暗动"
之类的规则，但引擎一个都没算。AI 手里没有数据，就只能自己推——这是幻觉的第一来源。
本模块只**算事实**，不替任何一家写法做取舍；凡两书有异者，把两家的口径都标出来
（见 docs/六爻分歧登记表.md），措辞由议题级裁定决定。

书证（逐字核过，行号为各书自身行号）
------------------------------------
- 进退神：甲《进神退神章》；乙《变出进退神论第十七》。两书组合一致（本表 §5 公理）。
- 暗动/日破：甲《暗动章》「静爻休囚，日辰冲之，为日破；静爻旺相，日辰冲之，为暗动。」
  乙不立日破（见登记表 D-01 之外的差异：本站采甲，见登记表 §6 T 表外的已裁项）。
- 三墓：甲《随鬼入墓章》「古有日墓、动墓、化墓，谓之三墓。」并附野鹤门槛：
  「亦必休囚无气，始见凶危，若旺而有扶，仍有救解。」
- 旬空真假：甲《旬空章》野鹤曰「旺不为空，动不为空，动而化空，伏而旺相，皆不为空，
  有日建动爻生扶者，亦不为空，月破为空，有气不动亦为空，伏而被克亦为空，真空为空。」
- 月破：甲《月破章》「月建冲之为月破」＋出破三法「出月则不破、实破之日则不破、逢合之日则不破」。
- 反吟：乙《反吟卦定例第十一》「卦之反吟，卦变相冲也。爻之反吟，爻变相冲也。」
- 伏吟：乙《伏吟卦定例第十二》「伏吟卦有三」。
- 三合：甲《三合章》「此三合者有四」＋断法（世在局为美、局生世吉、局克世凶、虚一待用）。
- 伏神：乙《第九问》四出四不入（甲的对策"再占"由调用方按登记表 D-02 绑定）。
- 神煞：登记表 D-03 —— 一律不进判定链，故本模块**不产出**任何神煞变量。
"""
import re

# ---------------------------------------------------------------------------
# 五行基础（与 liuyao_remedy 同口径，此处独立以免循环依赖）
# ---------------------------------------------------------------------------
ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
ZHI_WX = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
          "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
SHENG = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
KE = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}
CHONG = {"子": "午", "午": "子", "丑": "未", "未": "丑", "寅": "申", "申": "寅",
         "卯": "酉", "酉": "卯", "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳"}
HE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯",
      "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}

# 长生/帝旺/墓/绝 —— 甲《生旺墓绝章》口径，与 liuyao_remedy.SHENG_WANG_MU_JUE 一致
SWMJ = {"金": {"长生": "巳", "帝旺": "酉", "墓": "丑", "绝": "寅"},
        "木": {"长生": "亥", "帝旺": "卯", "墓": "未", "绝": "申"},
        "火": {"长生": "寅", "帝旺": "午", "墓": "戌", "绝": "亥"},
        "水": {"长生": "申", "帝旺": "子", "墓": "辰", "绝": "巳"},
        "土": {"长生": "申", "帝旺": "子", "墓": "辰", "绝": "巳"}}

# ---------------------------------------------------------------------------
# 进神 / 退神（甲《进神退神章》原文八组，逐字核过；乙《变出进退神论》同）
#   进神：亥化子，寅化卯，巳化午，申化酉，丑化辰，辰化未，未化戌，戍化丑
#   退神：子化亥，卯化寅，午化巳，酉化申，辰化丑，未化辰，戌化未，丑化戍
# 注：原文"戍"为"戌"之异体，此处从正字；异体保留见登记表 §8。
# ---------------------------------------------------------------------------
JINSHEN = {"亥": "子", "寅": "卯", "巳": "午", "申": "酉",
           "丑": "辰", "辰": "未", "未": "戌", "戌": "丑"}
TUISHEN = {"子": "亥", "卯": "寅", "午": "巳", "酉": "申",
           "辰": "丑", "未": "辰", "戌": "未", "丑": "戌"}

# 三合四局（甲《三合章》）：申子辰水、巳酉丑金、寅午戌火、亥卯未木
SANHE = {"水": ("申", "子", "辰"), "金": ("巳", "酉", "丑"),
         "火": ("寅", "午", "戌"), "木": ("亥", "卯", "未")}

# 卦之反吟：内外卦各自相冲（乙《反吟卦定例第十一》逐例归纳）
#   乾巽 / 坎离 / 艮坤 / 震兑 —— 乙所举八例（乾为天↔巽为风、天风姤↔风天小畜、
#   坎为水↔离为火、水火既济↔火水未济、艮为山↔坤为地、山地剥↔地山谦、
#   震为雷↔兑为泽、雷泽归妹↔泽雷随）全部满足此规则。
GUA_CHONG = {"乾": "巽", "巽": "乾", "坎": "离", "离": "坎",
             "艮": "坤", "坤": "艮", "震": "兑", "兑": "震"}


def _lines(gua):
    return gua.get("lines") or []


def _day_zhi(gua):
    """日支。

    引擎的 time_info **没有 day_zhi 字段**（只有 day_stem / month_branch），
    必须与 liuyao_remedy 同口径：取 day_ganzhi 的第二位（"丙申" → "申"）。
    曾经因为直接读 time_info["day_zhi"] 拿到 None，导致暗动/日破一条都检不出来。
    """
    return ((gua.get("time_info") or {}).get("day_ganzhi") or "")[1:2]


def _grades(remedy):
    """从 remedy.details 取每爻综合旺衰（旺相／休囚 二分），key 为爻位。"""
    out = {}
    det = ((remedy or {}).get("details") or {})
    for row in det.get("各爻旺衰") or []:
        out[row.get("position")] = row.get("旺衰")
    return out


# ---------------------------------------------------------------------------
# ① 进退神
# ---------------------------------------------------------------------------
def jintui(gua):
    """动爻化进神 / 化退神。只论动爻变出之爻（甲：「进退神者，爻之动而化也」）。

    附带产出"化空/化破"两个事实位。化空破与进神的关系两书已裁为一致
    （登记表 §5，2026-09-24）：定性不废——甲「亦能进」；应期待实——甲卦例
    「许之寅卯年，实空实破」即乙「待期填补合冲而进」。故只报事实，应期留给值日模块。
    """
    out = []
    for l in _lines(gua):
        b = l.get("bian")
        if not b or not l.get("moving"):
            continue
        a, c = l.get("zhi"), b.get("zhi")
        kind = None
        if JINSHEN.get(a) == c:
            kind = "化进神"
        elif TUISHEN.get(a) == c:
            kind = "化退神"
        if kind:
            out.append({
                "position": l["position"], "name": l["name"],
                "本爻": "%s%s" % (l.get("gan", ""), a), "变爻": "%s%s" % (b.get("gan", ""), c),
                "类型": kind,
                # 事实位：变出之爻是否空/破（空破由引擎的 xunkong/yuepo 判定，不在此重算）
                "变爻旬空": bool(b.get("xunkong")),
                "变爻月破": bool(b.get("yuepo")),
                "分歧": "已裁一致（登记表 §5，2026-09-24）：化空破不废进神定性，应期在实空实破/合冲之期",
            })
    return out


# ---------------------------------------------------------------------------
# ② 暗动 / 日破（采甲，见登记表议题级主从表）
# ---------------------------------------------------------------------------
def andong_ripo(gua, remedy):
    """静爻受日辰冲：旺相→暗动，休囚→日破。

    甲《暗动章》：「静爻休囚，日辰冲之，为日破；静爻旺相，日辰冲之，为暗动。」
    甲[乾按]：「暗动必旺相之静爻受日建相冲方动，休囚之爻无暗动也。」
    乙不立"日破"（静而不空逢冲一律曰暗动），此差异见登记表；本站采甲。
    综合旺衰自 2026-09-23 起为**二分**（旺相／休囚，见 liuyao_remedy._line_strength），
    与本章的两分正好对齐，故不再有"平（两书未及）"这一档。
    """
    day_zhi = _day_zhi(gua)
    grades = _grades(remedy)
    out = []
    for l in _lines(gua):
        if l.get("moving"):
            continue                       # 明动之爻不论暗动
        if CHONG.get(l.get("zhi")) != day_zhi:
            continue
        if l.get("xunkong"):
            continue                       # 空爻受冲为"冲空则实"，另算
        g = grades.get(l["position"])
        if g == "旺相":
            verdict, why = "暗动", "旺相之静爻受日辰冲"
        else:
            verdict, why = "日破", "休囚之静爻受日辰冲"
        out.append({"position": l["position"], "name": l["name"],
                    "六亲": l.get("liuqin", ""), "干支": l.get("gan", "") + l.get("zhi", ""),
                    "旺衰": g, "判定": verdict, "依据": why})
    return out


# ---------------------------------------------------------------------------
# ③ 三墓（日墓 / 动墓 / 化墓）
# ---------------------------------------------------------------------------
def san_mu(gua):
    """三墓：日墓、动墓、化墓（甲《随鬼入墓章》「古有日墓、动墓、化墓，谓之三墓」）。

    野鹤门槛（同章）：「亦必休囚无气，始见凶危，若旺而有扶，仍有救解。」
    故此处只报"是否入墓"这一事实，**不判吉凶**——旺衰由调用方按既有旺衰表结合。
    """
    day_zhi = _day_zhi(gua)
    lines = _lines(gua)
    moving_zhi = [l.get("zhi") for l in lines if l.get("moving")]
    out = []
    for l in lines:
        wx = l.get("wuxing")
        mu = (SWMJ.get(wx) or {}).get("墓")
        if not mu:
            continue
        kinds = []
        if day_zhi == mu:
            kinds.append("日墓")
        if mu in moving_zhi:
            kinds.append("动墓")
        b = l.get("bian")
        if l.get("moving") and b and b.get("zhi") == mu:
            kinds.append("化墓")
        if kinds:
            out.append({"position": l["position"], "name": l["name"],
                        "五行": wx, "墓支": mu, "入墓": kinds,
                        "门槛": "野鹤：须休囚无气始见凶危，旺而有扶仍有救解"})
    return out


# ---------------------------------------------------------------------------
# ④ 旬空真假（甲《旬空章》野鹤曰逐条）
# ---------------------------------------------------------------------------
def xunkong_kind(gua, remedy, month_branch=""):
    """旬空之爻分真假。逐条照甲《旬空章》野鹤曰：

    不为空：旺 / 动 / 动而化空 / 伏而旺相 / 有日建动爻生扶
    为空：  月破 / 有气不动 / 伏而被克 / 真空（春土、夏金、秋木、三冬火）
    """
    grades = _grades(remedy)
    det = ((remedy or {}).get("details") or {})
    five = {row.get("position"): row.get("月令五态") or ""
            for row in det.get("各爻旺衰") or []}
    mb = month_branch or (gua.get("time_info") or {}).get("month_branch") or ""
    season_wx = {"寅": "木", "卯": "木", "辰": "土", "巳": "火", "午": "火", "未": "土",
                 "申": "金", "酉": "金", "戌": "土", "亥": "水", "子": "水", "丑": "土"}
    # 真空：春土、夏金、秋木、三冬火
    season = {"寅": "春", "卯": "春", "辰": "春", "巳": "夏", "午": "夏", "未": "夏",
              "申": "秋", "酉": "秋", "戌": "秋", "亥": "冬", "子": "冬", "丑": "冬"}.get(mb, "")
    zhenkong = {"春": "土", "夏": "金", "秋": "木", "冬": "火"}.get(season, "")

    out = []
    for l in _lines(gua):
        if not l.get("xunkong"):
            continue
        wx, g = l.get("wuxing"), grades.get(l["position"])
        reasons = []
        if l.get("moving"):
            reasons.append("动不为空")
        fv = five.get(l["position"]) or ("旺相" if g == "旺相" else "")
        if fv == "旺":
            reasons.append("旺不为空")
        elif fv == "相" and not l.get("moving"):
            reasons.append("有气不动亦为空（甲《旬空章》）")
        elif fv == "旺相":     # 无五态明细时的兜底（契约上不会走到）
            reasons.append("旺不为空（无五态明细，按二分）")
        if l.get("yuepo"):
            reasons.append("月破为空")
        if wx == zhenkong:
            reasons.append("真空（%s%s）" % (season, zhenkong))
        if l.get("moving") and l.get("bian") and l["bian"].get("xunkong"):
            reasons.append("动而化空")
        # 结论只给"倾向"，把判据全列出。
        # 「有气不动亦为空」是甲单列的一目（相而不动之爻作空论）；乙第十《旬空论》只分
        # 旺相/休囚两桶、未细论相——采甲细目，乙不冲突（登记表 §4 F-02，2026-09-24 裁）。
        if wx == zhenkong or l.get("yuepo"):
            lean = "倾向于空（含真空/月破）"
        elif l.get("moving") or fv == "旺":
            lean = "倾向不为空（旺/动）"
        else:
            lean = "有气不动或休囚，倾向于空"
        out.append({"position": l["position"], "name": l["name"],
                    "六亲": l.get("liuqin", ""), "五行": wx, "旺衰": g,
                    "判据": reasons, "倾向": lean,
                    "分歧": "已裁一致（登记表 §4 F-02，2026-09-24）：甲野鹤曰＝乙第十《旬空论》生克有无直断；疑难时甲附再占合决",
                    "两书均未见": "「冲空」作为出破法（登记表 §7-2）；作旬空出空法则有明文"})
    return out


# ---------------------------------------------------------------------------
# ⑤ 月破与出破
# ---------------------------------------------------------------------------
def yuepo_state(gua, start=None):
    """月破之爻与出破三法（甲《月破章》）。

    「目下虽破，出月则不破。今日虽破，实破之日则不破，逢合之日则不破，
      近应日时，远应年月。惟静而不动，又无日辰动爻生助，实则到底而破矣。」
    """
    out = []
    for l in _lines(gua):
        if not l.get("yuepo"):
            continue
        z = l.get("zhi", "")
        chong = CHONG.get(z, "")
        he = HE.get(z, "")
        dong = bool(l.get("moving"))
        out.append({
            "position": l["position"], "name": l["name"], "干支": l.get("gan", "") + z,
            "六亲": l.get("liuqin", ""),
            "出破条件": ["出月（下月）", "实破之日（逢%s）" % z, "逢合之日（逢%s）" % he],
            "静动": "动" if dong else "静",
            "到底破": (not dong),
            "说明": ("动则能伤于爻、变则能伤于动，目下虽破仍有祸福之基"
                     if dong else "静而不动、又无日辰动爻生助，实则到底而破"),
            "冲支": chong,
        })
    return out


# ---------------------------------------------------------------------------
# ⑥ 反吟 / 伏吟
# ---------------------------------------------------------------------------
def fan_fu_yin(gua):
    """卦之反吟 / 爻之反吟 / 伏吟（乙《反吟卦定例第十一》《伏吟卦定例第十二》）。

    卦之反吟：变卦与本卦的内外卦各自相冲（乾巽/坎离/艮坤/震兑）。
    爻之反吟：动爻变出之爻与本爻地支相冲。
    伏吟：变卦与本卦**六爻地支全同**（乙所举乾变震、无妄变大壮、姤变恒等皆满足）。
    范围已裁（登记表 §5，2026-09-24）：采乙封闭三类为执行标准（查表），甲仅开放举例、
    分类同构（内外/外/内）且同举「无妄变大壮」，不冲突。
    """
    ben, bian = gua.get("ben_gua") or {}, gua.get("bian_gua") or {}
    res = {"卦之反吟": None, "爻之反吟": [], "伏吟": None}
    if not bian:
        return res
    bu, bl = (ben.get("upper") or {}).get("name"), (ben.get("lower") or {}).get("name")
    cu, cl = (bian.get("upper") or {}).get("name"), (bian.get("lower") or {}).get("name")
    if bu and bl and cu and cl and GUA_CHONG.get(bu) == cu and GUA_CHONG.get(bl) == cl:
        res["卦之反吟"] = {
            "本卦": ben.get("name"), "变卦": bian.get("name"),
            "内外双冲": "%s→%s、%s→%s" % (bu, cu, bl, cl),
            "书证": "乙《反吟卦定例第十一》：「卦之反吟，卦变相冲也。」",
        }
    for l in _lines(gua):
        b = l.get("bian")
        if b and l.get("moving") and CHONG.get(l.get("zhi")) == b.get("zhi"):
            res["爻之反吟"].append({
                "position": l["position"], "name": l["name"],
                "本爻": l.get("zhi"), "变爻": b.get("zhi"),
                "书证": "乙《反吟卦定例第十一》：「爻之反吟，爻变相冲也。」",
            })
    # 伏吟 = 变卦与本卦六爻地支全同。
    # 注意不能直接取 l["bian"]["zhi"]：引擎只给**动爻**挂 bian，静爻没有变爻。
    # 而变卦里静爻的支本就照抄本爻，故六爻支全同 ⟺ 每个动爻的变出之爻与本爻同支。
    # （乙所举乾变震、无妄变大壮、姤变恒等例皆满足此式。）
    moving = [l for l in _lines(gua) if l.get("moving") and l.get("bian")]
    if moving and all(l["bian"].get("zhi") == l.get("zhi") for l in moving):
        res["伏吟"] = {
            "本卦": ben.get("name"), "变卦": bian.get("name"),
            "六爻支": "".join(l.get("zhi") or "" for l in _lines(gua)),
            "动爻": [l["name"] for l in moving],
            "书证": "乙《伏吟卦定例第十二》：「伏吟卦有三」——变卦六爻地支与本卦全同。",
            "分歧": "已裁（登记表 §5，2026-09-24）：采乙封闭三类（乾震内外、六对外卦、六对内卦）；甲开放举例、分类同构，不冲突",
        }
    return res


# ---------------------------------------------------------------------------
# ⑦ 三合局（甲《三合章》）
# ---------------------------------------------------------------------------
def sanhe_ju(gua):
    """三合局。甲《三合章》：「此三合者有四」＋「三爻若只两爻动，不为成局，
    须待后来之月日补凑，合成其局，谓之虚一待用。一爻明动，一爻暗动，亦作两爻动。」"""
    lines = _lines(gua)
    pool = []                      # (支, 位置, 是否动, 来源)
    for l in lines:
        pool.append((l.get("zhi"), l["position"], bool(l.get("moving")), "本卦"))
        b = l.get("bian")
        if b and l.get("moving") and b.get("zhi"):
            pool.append((b["zhi"], l["position"], True, "变出"))
    out = []
    for wx, trio in SANHE.items():
        present = [(z, p, mv, src) for (z, p, mv, src) in pool if z in trio]
        have = {z for z, _, _, _ in present}
        if len(have) == 3:
            movers = {z for z, _, mv, _ in present if mv}
            out.append({
                "局": "%s局（%s%s%s）" % (wx, trio[0], trio[1], trio[2]),
                "成局": True,
                "动爻数": len(movers),
                "待补": None if len(movers) >= 2 else "虚一待用（只两爻动，须待后来月日补凑）",
                "组成": [{"支": z, "爻位": p, "动": mv, "来源": s} for z, p, mv, s in present],
                "断法": "局生世则吉、局克世则凶；世爻在局为美；日月有一在局中谓之局旺",
            })
        elif len(have) == 2:
            movers = {z for z, _, mv, _ in present if mv}
            if len(movers) >= 2:
                missing = [z for z in trio if z not in have]
                out.append({
                    "局": "%s局（%s%s%s）" % (wx, trio[0], trio[1], trio[2]),
                    "成局": False, "动爻数": len(movers),
                    "待补": "虚一待用：缺「%s」，须待后来之月日补凑" % missing[0],
                    "组成": [{"支": z, "爻位": p, "动": mv, "来源": s} for z, p, mv, s in present],
                    "断法": "虚一待用——未成局，只记趋势",
                })
    return out


# ---------------------------------------------------------------------------
# ⑧ 伏神四出四不入（乙《第九问》）
# ---------------------------------------------------------------------------
def _liuqin(palace_wx, wx):
    """六亲：同我兄弟、生我父母、我生子女、克我官鬼、我克妻财。"""
    if not palace_wx or not wx:
        return ""
    if wx == palace_wx:
        return "兄弟"
    if SHENG.get(wx) == palace_wx:
        return "父母"
    if SHENG.get(palace_wx) == wx:
        return "子孙"
    if KE.get(wx) == palace_wx:
        return "官鬼"
    if KE.get(palace_wx) == wx:
        return "妻财"
    return ""


def _shou_gua_najia(palace):
    """本宫首卦（八纯）的六爻纳甲 [(gan, zhi, wuxing)] —— 伏神取法的依据。

    登记表 §5：取伏来源两书一致，本宫首卦为下七卦之伏神，**当公理写死**。
    """
    try:
        import liuyao_engine as E
    except Exception:
        return []
    seq = (getattr(E, "PALACE_SEQUENCE", {}) or {}).get(palace)
    najia = getattr(E, "NAJIA", {}) or {}
    if not seq or not najia:
        return []
    upper, lower = seq[0][0], seq[0][1]
    if lower not in najia or upper not in najia:
        return []
    return list(najia[lower][0:3]) + list(najia[upper][3:6])


def _fushen_state(fei, fu_zhi, fu_wx, gua, day_zhi, month_branch, moving_lines):
    """飞伏四态（乙《伏神正传》歌诀，逐字核过）：

    伏克飞神为出暴，飞来克伏反伤身。伏去生飞名泄炁，飞来生伏得长生。
    """
    fei_wx = fei.get("wuxing")
    states = []
    if SHENG.get(fei_wx) == fu_wx:
        states.append(("飞来生伏", "飞来生伏得长生（伏神得出）"))
    if KE.get(fei_wx) == fu_wx:
        states.append(("飞来克伏", "飞来克伏反伤身（凶）"))
    if SHENG.get(fu_wx) == fei_wx:
        states.append(("伏去生飞", "伏去生飞名泄气（伏神泄气）"))
    if KE.get(fu_wx) == fei_wx:
        states.append(("伏克飞", "伏克飞神为出暴（伏神能出）"))
    if fei_wx == fu_wx:
        states.append(("飞伏比和", "飞伏比和，相助"))
    # 伏神入墓/绝于飞爻（乙所举：水墓在辰、金墓在丑、火绝在亥）
    swmj = SWMJ.get(fu_wx) or {}
    if swmj.get("墓") and swmj["墓"] == fei.get("zhi"):
        states.append(("伏神入墓于飞爻", "伏神墓于飞爻，受锁"))
    if swmj.get("绝") and swmj["绝"] == fei.get("zhi"):
        states.append(("伏神绝于飞爻", "伏神绝于飞爻，受锁"))

    # 四出四条（乙《第九问》，逐条取证）
    out = []
    day_wx = ZHI_WX.get(day_zhi, "")
    mon_wx = ZHI_WX.get(month_branch, "")
    if fu_zhi == day_zhi or fu_zhi == month_branch:
        out.append("① 日月持之（伏神临日辰/月建）")
    if SHENG.get(day_wx) == fu_wx or SHENG.get(mon_wx) == fu_wx:
        out.append("① 日月生之")
    if SHENG.get(fei_wx) == fu_wx:
        out.append("② 飞神生伏")
    if any(SHENG.get(l.get("wuxing")) == fu_wx for l in moving_lines):
        out.append("② 动爻生伏")
    if CHONG.get(fei.get("zhi")) in (day_zhi, month_branch):
        out.append("③ 日月冲飞神")
    if any(KE.get(l.get("wuxing")) == fei_wx for l in moving_lines):
        out.append("③ 动爻克飞神")
    if fei.get("xunkong") or fei.get("yuepo"):
        out.append("④ 飞神空破")
    return states, out


def fushen_chu(gua, yong_liuqin="", palace=""):
    """用神不上卦时，伏神得出与否（乙《第九问》四出四不入）。

    四出：① 日月生者、日月持之者；② 飞神生伏、动爻生者；
         ③ 日月动爻冲克飞神；④ 飞神空破休囚墓绝于日者。
    四不入：① 休囚无气、日月克者；② 飞神旺相、日月生助飞神而克害伏神者；
           ③ 伏神墓绝于日月及飞爻者；④ 伏神休囚兼旬空月破者。

    取伏来源两书一致（本宫首卦），见登记表 §5，当公理写死。
    对策（甲「宜再占一卦」）**不在此处产出**：按登记表 D-02，只在判定为"难出"时
    由调用方附加，伏神得出时不提。
    """
    if not yong_liuqin:
        return {"适用": False, "原因": "未指定用神六亲"}
    if yong_liuqin in ("世", "应"):
        return {"适用": False,
                "原因": "用神取世爻/应爻（非六亲），本卦必有此爻，无伏神可查"}
    lines = _lines(gua)
    if any(l.get("liuqin") == yong_liuqin for l in lines):
        return {"适用": False,
                "原因": "用神已现于本卦，不查伏神（乙：「既有用神现……不必再查伏神矣」）"}
    for l in lines:
        b = l.get("bian")
        if b and b.get("liuqin") == yong_liuqin:
            return {"适用": False,
                    "原因": "变爻已有用神，不必寻伏神（乙：「凡卦中用神不出现，查变爻有，不必寻伏神矣」）"}

    palace = palace or (gua.get("palace") or "")
    palace_wx = gua.get("palace_wuxing") or ""
    najia = _shou_gua_najia(palace)
    res = {"适用": True,
           "取法": "本宫首卦（八纯）同六亲之爻为伏神，本卦同爻位之爻为飞神（登记表 §5，两书共识）",
           "本宫": palace, "本宫首卦六爻": ["%s%s%s" % tuple(x) for x in najia] or None,
           "四出": ["日月生者、日月持之者", "飞神生伏、动爻生者",
                    "日月动爻冲克飞神", "飞神空破休囚墓绝于日者"],
           "四不入": ["休囚无气、日月克者", "飞神旺相、日月生助飞神而克害伏神者",
                      "伏神墓绝于日月及飞爻者", "伏神休囚兼旬空月破者"]}
    if len(najia) != 6 or not palace_wx:
        res["待接线"] = "缺本宫首卦纳甲表或宫五行，只能给出判定条目"
        return res

    pos = next((i for i, (_g, _z, wx) in enumerate(najia)
                if _liuqin(palace_wx, wx) == yong_liuqin), None)
    if pos is None:
        res["待接线"] = "本宫首卦中亦无此六亲（理论上八纯六亲俱全，不应发生）"
        return res
    _g, fu_zhi, fu_wx = najia[pos]
    fei = next((l for l in lines if l["position"] == pos + 1), None)
    if fei is None:
        res["待接线"] = "本卦无对应爻位"
        return res
    day_zhi = _day_zhi(gua)
    month_branch = ((gua.get("time_info") or {}).get("month_branch") or "")
    moving = [l for l in lines if l.get("moving")]
    states, out = _fushen_state(fei, fu_zhi, fu_wx, gua, day_zhi, month_branch, moving)
    res.update({
        "伏神": {"地支": fu_zhi, "五行": fu_wx, "六亲": yong_liuqin, "爻位": pos + 1},
        "飞神": {"地支": fei.get("zhi"), "五行": fei.get("wuxing"),
                 "干支": fei.get("gan", "") + fei.get("zhi", ""), "爻位": fei["position"],
                 "旬空": bool(fei.get("xunkong")), "月破": bool(fei.get("yuepo"))},
        "飞伏四态": [{"态": a, "解": b} for a, b in states],
        "得出去向": out,
    })
    # 判定层：只要有"四出"中任一条，即报"伏神得出"；否则报"伏神难出"
    res["判定"] = "伏神得出" if out else "伏神难出"
    if res["判定"] == "伏神难出":
        # 登记表 D-02：对策用甲，且**只在难出时**附加
        res["对策"] = ("依《增删卜易》，此时宜再占一卦以决，不必执伏神而断凶"
                       "（野鹤：「但逢不现，虽有伏神，亦不用之，再占两卦，用神自现」）")
    return res


def liuhe_liuchong(gua):
    """爻级六合 / 六冲（甲《六合章》《六冲章》）。

    甲《六合章》「相合之法有六」：静而逢合谓之**合起**，动而逢合谓之**合绊**，
    爻与爻合谓之**合好**，爻动化合谓之**化扶**……动逢合而绊住者，后逢冲开之月日吉凶依然应。
    甲《六冲章》「爻冲有五」：爻遇月冲为**月破**，静爻旺遇日冲为**暗动**，
    休囚而遇日冲为**日破**，动爻自化回头冲如逢仇敌，爻遇爻冲谓之**相击**。
    卦级六冲/六合（六爻皆冲/皆合）由引擎 markers 给，此处只算爻与爻之间。
    """
    lines = _lines(gua)
    day_zhi = _day_zhi(gua)
    month_branch = ((gua.get("time_info") or {}).get("month_branch") or "")
    he, chong = [], []
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            za, zb = a.get("zhi"), b.get("zhi")
            if HE.get(za) == zb:
                he.append({"爻": [a["name"], b["name"]], "支": [za, zb], "类": "合好"})
            if CHONG.get(za) == zb:
                chong.append({"爻": [a["name"], b["name"]], "支": [za, zb], "类": "相击"})
    # 动爻逢日月合 = 合绊；静爻逢日月合 = 合起
    bound = []
    for l in lines:
        z = l.get("zhi")
        for src, zhi in (("月建", month_branch), ("日辰", day_zhi)):
            if zhi and HE.get(z) == zhi:
                bound.append({"name": l["name"], "干支": l.get("gan", "") + z,
                              "类": "合绊（动逢合而绊住，须待冲开之月日）" if l.get("moving")
                                    else "合起（静而逢合）",
                              "合于": src})
    # 动爻自化回头冲
    back_chong = []
    for l in lines:
        b = l.get("bian")
        if b and l.get("moving") and CHONG.get(l.get("zhi")) == b.get("zhi"):
            back_chong.append({"name": l["name"], "本爻": l.get("zhi"), "变爻": b.get("zhi")})
    return {"合好": he, "相击": chong, "日月合": bound, "化回头冲": back_chong}


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
def analyze(gua, remedy=None, yong_liuqin="") -> dict:
    """一次算全，供 build_liuyao_user_prompt 直接注入。"""
    return {
        "进退神": jintui(gua),
        "暗动日破": andong_ripo(gua, remedy),
        "三墓": san_mu(gua),
        "旬空": xunkong_kind(gua, remedy),
        "月破": yuepo_state(gua),
        "反伏吟": fan_fu_yin(gua),
        "三合局": sanhe_ju(gua),
        "六合六冲": liuhe_liuchong(gua),
        "伏神": fushen_chu(gua, yong_liuqin, (gua.get("palace") or "")),
        "神煞": "不进判定链（登记表 D-03）：本模块不产出任何神煞变量，仅排盘照旧显示六神",
    }


def to_prompt_block(res: dict) -> str:
    """编成给 AI 的只读上下文。**只陈述事实，不替两书做取舍。**"""
    L = ["【格局判据（代码依原著条例算出，照此解释，不得重算、不得自行加减）】"]
    for it in res.get("进退神") or []:
        L.append("· %s %s→%s：%s%s%s"
                 % (it["name"], it["本爻"], it["变爻"], it["类型"],
                    "｜变爻旬空" if it["变爻旬空"] else "",
                    "｜变爻月破" if it["变爻月破"] else ""))
    for it in res.get("暗动日破") or []:
        L.append("· %s %s（%s）：%s——%s" % (it["name"], it["六亲"], it["干支"],
                                            it["判定"], it["依据"]))
    for it in res.get("三墓") or []:
        L.append("· %s 入%s（墓支%s）｜%s" % (it["name"], "、".join(it["入墓"]),
                                             it["墓支"], it["门槛"]))
    for it in res.get("旬空") or []:
        L.append("· %s 旬空（%s）：%s｜%s" % (it["name"], it["五行"], it["倾向"],
                                             "、".join(it["判据"]) or "无特别判据"))
    for it in res.get("月破") or []:
        L.append("· %s 月破（%s）｜出破：%s｜%s"
                 % (it["name"], it["静动"], "、".join(it["出破条件"]), it["说明"]))
    ff = res.get("反伏吟") or {}
    if ff.get("卦之反吟"):
        L.append("· 卦之反吟：%s（内外双冲 %s）"
                 % (ff["卦之反吟"]["内外双冲"], ff["卦之反吟"]["书证"]))
    for it in ff.get("爻之反吟") or []:
        L.append("· 爻之反吟：%s %s→%s" % (it["name"], it["本爻"], it["变爻"]))
    if ff.get("伏吟"):
        L.append("· 伏吟：本卦与变卦六爻地支全同（%s）" % ff["伏吟"]["六爻支"])
    for it in res.get("三合局") or []:
        L.append("· %s：%s%s" % (it["局"], "成局" if it["成局"] else "未成局",
                                 ("｜" + it["待补"]) if it.get("待补") else ""))
    hc = res.get("六合六冲") or {}
    for it in hc.get("合好") or []:
        L.append("· 六合（合好）：%s %s%s" % ("与".join(it["爻"]), it["支"][0], it["支"][1]))
    for it in hc.get("相击") or []:
        L.append("· 六冲（相击）：%s %s%s" % ("与".join(it["爻"]), it["支"][0], it["支"][1]))
    for it in hc.get("日月合") or []:
        L.append("· %s（%s）%s" % (it["类"], it["合于"], it["name"]))
    for it in hc.get("化回头冲") or []:
        L.append("· 动爻自化回头冲：%s %s→%s" % (it["name"], it["本爻"], it["变爻"]))
    fs = res.get("伏神") or {}
    if fs.get("适用"):
        L.append("· 用神不上卦 → 查伏神：%s" % fs["取法"])
        L.append("  得出者四：%s" % "；".join(fs["四出"]))
        L.append("  不得出者四：%s" % "；".join(fs["四不入"]))
    return "\n".join(L) if len(L) > 1 else ""


if __name__ == "__main__":
    import io
    import sys as _s
    from datetime import datetime
    _s.stdout = io.TextIOWrapper(_s.stdout.buffer, encoding="utf-8")
    _s.path.insert(0, r"D:\Web\bagua\backend")
    import liuyao_engine as E
    import liuyao_remedy as R
    found = {}
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                found.setdefault(E.line_from_coins([a, b, c])["type"], (a, b, c))
    raw = []
    for ty in ["老阳", "少阴", "老阴", "少阳", "少阴", "少阳"]:
        L = E.line_from_coins(list(found[ty]))
        L["coins"] = list(found[ty])
        raw.append(L)
    g = E._build_paipan_from_raw(raw, datetime(2026, 9, 19, 14, 30))
    g["remedy"] = R.liuyao_remedy(g, "我这次跳槽能不能成")
    print(g["ben_gua"]["name"], "→", (g.get("bian_gua") or {}).get("name"))
    print(to_prompt_block(analyze(g, g["remedy"], g["remedy"].get("yongshen"))))
