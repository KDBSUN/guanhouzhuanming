# -*- coding: utf-8 -*-
"""
处方五行 R（Remedy）——六爻纳甲
================================
把六爻排盘归一化为命局校验入口的 X / R / 态势：

  X        = 用神爻五行（按事项取用神，卜筮正宗六亲取用）
  R        = 为促成当前之事、此刻最应强化或引入的五行
  态势标签 = 用神旺衰 + 元神/忌神发动

R 规则（增删卜易"元神—用神—忌神"三元）：
  忌神动克用神 → R = 制忌者五行（克忌神者）
  用神衰弱（旬空/月破/休囚受克）→ R = 元神五行（生用神者）
  用神旺相 → R = 用神五行（维持 / 直接加持）

六亲生克环（以卦宫五行为"我"）：
  生我者父母，我生者子孙，克我者官鬼，我克者妻财，比和者兄弟。
  相生：官生父、父生兄、兄生子、子生财、财生官。
  相克：兄克财、财克父、父克子、子克官、官克兄。
"""
from wuxing_relation import SHENG, KE, WUXING, sheng_me, ke_me
from wuxing_quality import month_state as _month_five      # 月令五态（旺相休囚死）唯一出处
from liuyao_liushou import per_line_readings

# 六亲 → 相对卦宫五行的五行
def _liuqin_wuxing_map(W):
    return {
        "父母": sheng_me(W),   # 生我者
        "兄弟": W,             # 同我者
        "子孙": SHENG[W],      # 我生者
        "妻财": KE[W],         # 我克者
        "官鬼": ke_me(W),      # 克我者
    }

# 元神（生用神者）/ 忌神（克用神者）——按用神六亲
def _yuanshen_jishen(W, yong_liuqin):
    wx = _liuqin_wuxing_map(W)
    table = {
        # 用神: (元神六亲, 元神五行, 忌神六亲, 忌神五行)
        "父母": ("官鬼", wx["官鬼"], "妻财", wx["妻财"]),
        "兄弟": ("父母", wx["父母"], "官鬼", wx["官鬼"]),
        "子孙": ("兄弟", wx["兄弟"], "父母", wx["父母"]),
        "妻财": ("子孙", wx["子孙"], "兄弟", wx["兄弟"]),
        "官鬼": ("妻财", wx["妻财"], "子孙", wx["子孙"]),
    }
    return table[yong_liuqin]


# ---------------------------------------------------------------------
# 用神分类（据《增删卜易·用神章》六亲取用定例）
# 分两层：先按"占事主体（人）"取用，再按"事类"取用；歧义不猜，默认世爻＝占自身。
# 书证：
#   父母爻＝占父母长辈师长仆占主人；宅舍屋宇舟车衣服文书文契一切庇护我身者
#   官鬼爻＝占功名官府雷霆鬼神妻占夫盗贼邪祟一切拘束我身者（考试属功名）
#   兄弟爻＝占兄弟姐妹结拜弟兄同类之人；劫财之神、阻隔之神
#   妻财爻＝占妻妾凡我驱使之人；货财珠宝金银仓库钱粮一切财物器皿（男占婚姻以财为用）
#   子孙爻＝占子孙侄甥门徒忠臣良将医士医药僧道兵卒六畜禽兽；福德制鬼解忧之神
#   自占疾病/自身/出行 → 世爻（官鬼为病、子孙为药是分析要素，非用神）
# ---------------------------------------------------------------------
PERSON_RULES = [
    ("子孙", ["子女", "孩子", "儿女", "子孙", "女儿", "儿子", "男孩", "女孩", "闺女", "宝宝",
              "宠物", "猫", "狗", "怀孕", "胎儿", "徒弟", "学生"]),
    ("官鬼", ["丈夫", "老公", "男朋友", "男友", "上司", "领导", "老板"]),
    ("妻财", ["老婆", "妻子", "对象", "未婚妻", "女友", "女朋友"]),
    ("父母", ["父母", "祖辈", "长辈", "母亲", "父亲", "妈妈", "爸爸", "丈人", "岳父", "岳母", "老师"]),
    ("兄弟", ["兄弟", "姐妹", "朋友", "同事", "合伙人", "合作伙伴", "对手", "竞争", "合股"]),
]
THING_RULES = [
    ("妻财", ["求财", "财运", "赚钱", "生意", "买卖", "交易", "投资", "钱", "财",
              "物价", "股票", "彩票", "工资", "收入", "债务", "还债", "货款",
              "婚姻", "姻缘", "感情", "嫁", "娶", "失物", "丢失", "找回", "找东西"]),
    ("官鬼", ["功名", "官运", "升职", "考公", "公务员", "事业", "工作", "职位", "职称",
              "考试", "科举", "考研", "考编", "诉讼", "官司", "官非", "报案", "职务"]),
    ("子孙", ["医药", "医生", "治疗", "药", "病重", "灾难", "灾"]),
    ("父母", ["房屋", "房子", "房产", "购房", "车", "购车", "文书", "合同", "证件",
              "学位", "论文", "单位", "学校", "执照", "证书"]),
    ("世", ["疾病", "病", "健康", "体检", "看病", "出行", "出门", "远行",
            "运势", "吉凶", "前程", "谋事"]),
]


def classify_yongshen_detail(question: str, yongshen_override: str = "") -> dict:
    """
    事项 → 用神判定详情（含置信度与候选），供前端两档流程使用：
      高置信（精确命中，如"父亲病情"→父母爻）→ 直接起卦，结果页展示判定依据；
      低置信/多候选（如"合作"→世应还是妻财）→ 起卦前弹二选气泡请用户确认。
    手动指定优先（参照《梅花易数》体用机械确定之思路：把《增删卜易·用神章》的
    封闭枚举表直接交给用户锁定，代替从问话自由文本猜测）。
    返回 {
      liuqin: 用神六亲（父母/官鬼/兄弟/妻财/子孙/世）,
      source: "manual"|"auto",
      confidence: "manual"|"high"|"low"|"default",
      candidates: [六亲...] 多候选时按规则优先级排列,
      matched: [{kw, liuqin, layer}...] 命中的关键词,
      reason: 判定依据（人话）
    }
    """
    ov = (yongshen_override or "").strip()
    if ov in ("世", "自占", "本人"):
        return {"liuqin": "世", "source": "manual", "confidence": "manual",
                "candidates": [], "matched": [], "reason": "手动指定：以世爻（占自身）为用神"}
    if ov in ("父母", "兄弟", "子孙", "妻财", "官鬼"):
        return {"liuqin": ov, "source": "manual", "confidence": "manual",
                "candidates": [], "matched": [], "reason": f"手动指定：以{ov}爻为用神"}

    q = question or ""
    matched = []
    for layer, rules in (("人主体", PERSON_RULES), ("事类", THING_RULES)):
        for liuqin, kws in rules:
            for kw in kws:
                if kw in q:
                    matched.append({"kw": kw, "liuqin": liuqin, "layer": layer})

    # 天然歧义词：一个词横跨两个六亲（如"合作"——问合伙之人（兄弟）还是生意钱财（妻财））
    distinct = list(dict.fromkeys(m["liuqin"] for m in matched))
    has_person = any(m["layer"] == "人主体" for m in matched)
    if not has_person:
        for words, cands in AMBIG_TRIGGERS:
            if any(w in q for w in words):
                for c in cands:
                    if c not in distinct:
                        distinct.append(c)
    # 人主体在场时，"世"（事类兜底桶，如"病/出行/运势"）不算独立候选：
    # 书例"父亲病情"→父母爻为用神（问人先问人），不因"病"字降级为低置信
    if has_person and len(distinct) > 1:
        distinct = [d for d in distinct if d != "世"]

    if not distinct:
        return {"liuqin": "世", "source": "auto", "confidence": "default",
                "candidates": ["世"], "matched": [],
                "reason": "问话未命中《用神章》关键词，按定例默认以世爻（占自身）为用神，可手动改判"}

    liuqin = distinct[0]
    if len(distinct) == 1:
        kw = matched[0]["kw"] if matched else "（歧义词）"
        layer = matched[0]["layer"] if matched else "歧义"
        return {"liuqin": liuqin, "source": "auto", "confidence": "high",
                "candidates": [liuqin], "matched": matched,
                "reason": f"精确命中关键词「{kw}」（{layer}）→ {YONGSHEN_GLOSS.get(liuqin, liuqin)}（《增删卜易·用神章》）"}

    matched_desc = "、".join(f"「{m['kw']}」→{m['liuqin']}" for m in matched) or "、".join(distinct)
    return {"liuqin": liuqin, "source": "auto", "confidence": "low",
            "candidates": distinct, "matched": matched,
            "reason": f"命中多义线索（{matched_desc}），用神存疑：{ ' / '.join(f'{c}（{YONGSHEN_GLOSS.get(c, c)}）' for c in distinct) }"}


# 六亲取用释义（结果页展示判定依据用）
YONGSHEN_GLOSS = {
    "世": "自占以世爻为用神",
    "父母": "父母爻为用神（长辈·文书·房屋）",
    "官鬼": "官鬼爻为用神（功名·官长·忧患）",
    "兄弟": "兄弟爻为用神（同辈·朋友·竞争）",
    "子孙": "子孙爻为用神（子女·晚辈·医药）",
    "妻财": "妻财爻为用神（妻子·钱财·货物）",
}

# 天然跨六亲的歧义词（低置信确认气泡的触发词表）
AMBIG_TRIGGERS = [
    (["合作", "合伙", "合资", "合股"], ["兄弟", "妻财"]),   # 问合伙之人还是生意钱财
]


def classify_yongshen(question: str, yongshen_override: str = "") -> tuple:
    """
    事项 → 用神六亲（父母/官鬼/兄弟/妻财/子孙/世）。
    手动指定优先；否则人主体规则 → 事类规则 → 默认世。
    返回 (用神六亲, 来源 "manual"|"auto")。需要置信度/候选时用 classify_yongshen_detail。
    """
    d = classify_yongshen_detail(question, yongshen_override)
    return d["liuqin"], d["source"]


# ---------------------------------------------------------------------
# 六爻 R
# ---------------------------------------------------------------------
def _pick_yongshen_line(lines, yong_liuqin, month_branch=""):
    """选用神爻：临月建优先（古法：两现取旺，野鹤验例择临月建者）> 动爻 > 不空破 > 先见。"""
    if yong_liuqin == "世":
        for l in lines:
            if l.get("shi"):
                return l
        return lines[0] if lines else None
    cands = [l for l in lines if l.get("liuqin") == yong_liuqin]
    if not cands:
        return None
    # 临月建优先（野鹤：当择其旺者而用之，今辰土父母临月建即用辰土）
    if month_branch:
        for l in cands:
            if l.get("zhi") == month_branch:
                return l
    # 动爻优先
    for l in cands:
        if l.get("moving"):
            return l
    # 旺相优先（不旬空不月破）
    for l in cands:
        if not l.get("xunkong") and not l.get("yuepo"):
            return l
    return cands[0]


# —— 本宫首卦纳支（浑天甲子，初爻→上爻）——
# 用神不现时的检索链（据《卜筮正宗·伏神正传》与《增删卜易·飞伏神章》）：
#   本卦爻上 → 日月临用神之支 → 本宫首卦伏神 → （仍不明时）再占。
# 世爻是"我"的参照系，不是所问事物的状态量，不作兜底（两书皆无"取世爻"之法）。
SHOU_GUA_ZHI = {
    "乾宫": ["子", "寅", "辰", "午", "申", "戌"],
    "坎宫": ["寅", "辰", "午", "申", "戌", "子"],
    "艮宫": ["辰", "午", "申", "戌", "子", "寅"],
    "震宫": ["子", "寅", "辰", "午", "申", "戌"],
    "巽宫": ["丑", "亥", "酉", "未", "巳", "卯"],
    "离宫": ["卯", "丑", "亥", "酉", "未", "巳"],
    "坤宫": ["未", "巳", "卯", "丑", "亥", "酉"],
    "兑宫": ["巳", "卯", "丑", "亥", "酉", "未"],
}


def _find_fushen(W: str, yong_liuqin: str, palace: str, lines: list,
                 month_wx: str = "", day_wx: str = "") -> dict:
    """用神不现 → 回本宫首卦取伏神（首卦六亲俱全，是结构上的全息模板；
    伏神退回首卦同爻位取回该六亲，与本卦同位之爻构成飞伏一对）。
    返回飞神/伏神信息与可用性评估（据《卜筮正宗》伏神得出四条件简化）。"""
    fu_wx = _liuqin_wuxing_map(W)[yong_liuqin]
    zhi_seq = SHOU_GUA_ZHI.get(palace, [])
    cands = [i + 1 for i, z in enumerate(zhi_seq) if ZHI_WUXING.get(z) == fu_wx]
    best = None
    for pos in cands:
        fei = next((l for l in lines if l.get("position") == pos), None)
        if not fei:
            continue
        fei_wx = fei.get("wuxing", "")
        if SHENG.get(fei_wx) == fu_wx:
            rel, usable = "飞来生伏得长生", True
        elif KE.get(fei_wx) == fu_wx:
            rel, usable = "飞来克伏反伤身", False
        elif SHENG.get(fu_wx) == fei_wx:
            rel, usable = "伏去生飞泄气", False
        elif KE.get(fu_wx) == fei_wx:
            rel, usable = "伏克飞为出暴", True
        else:
            rel, usable = "飞伏比和", True
        if fei.get("xunkong") or fei.get("yuepo"):
            rel += "（飞神空破，压制失效）"
            usable = True
        if month_wx == fu_wx or day_wx == fu_wx:
            rel += "（日月临伏神之支，引拔而出）"
            usable = True
        cand = {"position": pos, "fu_zhi": zhi_seq[pos - 1], "fu_wx": fu_wx,
                "fei_zhi": fei.get("zhi", ""), "fei_wx": fei_wx,
                "relation": rel, "usable": usable,
                "yaoqi": "冲飞之日、飞神空破填实之期、伏神值日之期"}
        if best is None or (usable and not best["usable"]):
            best = cand
    if best and len(cands) > 1:
        best["note"] = f"首卦另有 {len(cands) - 1} 处同六亲爻位"
    return best or {}


# —— 旺衰判定依据（《增删卜易》月将章/日辰章/四时旺相章/生旺墓绝章/元神忌神衰旺章） ——
ZHI_WUXING = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
              "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
CHONG = {"子": "午", "午": "子", "丑": "未", "未": "丑", "寅": "申", "申": "寅",
         "卯": "酉", "酉": "卯", "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳"}
# 生旺墓绝：金生巳旺酉墓丑绝寅；木生亥旺卯墓未绝申；火生寅旺午墓戌绝亥；水土生申旺子墓辰绝巳
SHENG_WANG_MU_JUE = {
    "金": {"长生": "巳", "帝旺": "酉", "墓": "丑", "绝": "寅"},
    "木": {"长生": "亥", "帝旺": "卯", "墓": "未", "绝": "申"},
    "火": {"长生": "寅", "帝旺": "午", "墓": "戌", "绝": "亥"},
    "水": {"长生": "申", "帝旺": "子", "墓": "辰", "绝": "巳"},
    "土": {"长生": "申", "帝旺": "子", "墓": "辰", "绝": "巳"},
}


# 月令五态（旺相休囚死）与序关系分值
# ---------------------------------------------------------------------------
# 书证（表与八字/梅花共用一处，见 wuxing_quality.MONTH_FIVE，保证三处口径一致）：
#   《五行大义·论四时休王》《渊海子平·旺相休囚死》通行表——
#   当令者旺、令生者相、生令者休、克令者囚、令克者死。
#   《卜筮正宗·四时旺相》原文自己只分两桶（「此八者旺相也……此八者休囚也」），
#   故**二分口径（旺相／休囚）就是书的原口径**，五态是这二分内部的细分。
# 分值：旺 2／相 1／休 0／囚 −1／死 −2。**纯序关系分**——次序来自上表，数值是工程默认
#   （未入 weights.yaml；改动须同步 docs/自定数值清单与反馈评估.md）。
SHIWANG_RANK = {"旺": 2, "相": 1, "休": 0, "囚": -1, "死": -2}


def _shiwang(wx: str, month_wx: str):
    """该五行在月令的五态。返回 (态名, 序关系分值)；月令未知时返回 ("", 0)。"""
    st = (_month_five(wx, month_wx) or {}).get("state", "")
    return st, SHIWANG_RANK.get(st, 0)


def _line_strength(line, wx, month_branch, month_wx, day_zhi, day_wx, lines):
    """爻综合旺衰。返回 (旺相/休囚, 分数, 标志)。

    口径（月令分量五档 · 综合二分开合）：
      · 月令一项按五态取序关系分（旺 2／相 1／休 0／囚 −1／死 −2，见 _shiwang）；
      · 日辰、动变、月破、旬空、生旺墓绝各项照旧加减；
      · 综合**二分**：分数 ≥ 1 为「旺相」，否则「休囚」。
        裁点取 1 的用意——**只有月令一项时，二分结果与书的两桶完全相同**
        （旺、相 → 旺相；休、囚、死 → 休囚），日辰动变在此基础上再加减。
      · 取消原先的「平」档：两书都只有旺相／休囚二分（《卜筮正宗·四时旺相》两桶、
        《增删卜易·暗动章》「静爻旺相…为暗动，静爻休囚…为日破」），
        原来的「平」是分值裁点造出来的第三档，书无明文。
      · 旧代码另计「月建生 +1／月建克 −1」，与五态中的相／死重复计分，今由月令五态
        一项承担，不再重复（标志相应改记「相于月令」「死于月令」等五态名）。
    """
    score = 0
    flags = []
    st, pts = _shiwang(wx, month_wx)
    score += pts
    if st:
        flags.append(f"{st}于月令")
    if line.get("zhi") == month_branch:
        score += 2
        flags.append("临月建")
    if line.get("zhi") == day_zhi:
        score += 2
        flags.append("临日辰")
    if SHENG[day_wx] == wx:
        score += 1
        flags.append("日辰生")
    if KE[day_wx] == wx:
        score -= 1
        flags.append("日辰克")
    if line.get("yuepo"):
        score -= 2
        flags.append("月破")
    if line.get("xunkong"):
        score -= 1
        flags.append("旬空")
    swmj = SHENG_WANG_MU_JUE[wx]
    if day_zhi == swmj["长生"]:
        score += 1
        flags.append("长生于日")
    if day_zhi == swmj["帝旺"]:
        score += 1
        flags.append("帝旺于日")
    if day_zhi == swmj["墓"]:
        score -= 1
        flags.append("墓于日")
    if day_zhi == swmj["绝"]:
        score -= 1
        flags.append("绝于日")
    for l in lines:
        if l is line or not l.get("moving"):
            continue
        if SHENG[l["wuxing"]] == wx:
            score += 1
            flags.append(f"动爻{l['wuxing']}生")
        elif KE[l["wuxing"]] == wx:
            score -= 1
            flags.append(f"动爻{l['wuxing']}克")
    if line.get("moving") and line.get("bian"):
        bw = line["bian"]["wuxing"]
        if bw == wx or SHENG[bw] == wx:
            score += 1
            flags.append("化回头生/比助")
        elif KE[bw] == wx:
            score -= 1
            flags.append("化回头克")
    return ("旺相" if score >= 1 else "休囚"), score, flags


def _yishen_youli(line, month_branch, month_wx, day_zhi, day_wx, lines):
    """元神/忌神爻 有力否（书证：元神忌神衰旺章——旺相临日月得生扶、动化回头生化进、
    旺动临空化空为有力；休囚不动被伤、休囚逢旬空月破、动化退、衰绝入墓、化绝克破散为无力）

    门槛随综合旺衰改为二分（旺相／休囚）：有力＝旺相（发动者另须不旬空），
    休囚即无力——正对书里「休囚不动或动而被克……虽有如无」一路。"""
    if line is None:
        return False, "不现"
    g, _score, flags = _line_strength(line, line["wuxing"], month_branch, month_wx, day_zhi, day_wx, lines)
    if line.get("moving") and not line.get("xunkong") and g == "旺相":
        return True, "发动有力"
    if g == "旺相":
        return True, "旺相有力"
    return False, ("、".join(flags) if flags else "休囚无力")


def liuyao_remedy(gua_data: dict, question: str, yongshen_override: str = "") -> dict:
    """
    gua_data: liuyao_engine.build_paipan 输出
    question: 所问之事
    yongshen_override: 手动指定用神六亲（父母/兄弟/子孙/妻财/官鬼/世），空则自动分类
    返回 {X, R, R_reason, yongshen, yongshen_source, yongshen_desc, state, state_desc, details}
    """
    W = gua_data.get("palace_wuxing")
    lines = gua_data.get("lines", [])
    ti = gua_data.get("time_info", {})
    month_branch = ti.get("month_branch", "")
    day_zhi = ti.get("day_ganzhi", "子子")[1]
    if W not in WUXING:
        raise ValueError(f"非法卦宫五行: {W!r}")

    yong = classify_yongshen_detail(question, yongshen_override)
    yong_liuqin, yong_source = yong["liuqin"], yong["source"]
    yong_meta = {k: yong[k] for k in ("confidence", "candidates", "matched", "reason")}
    month_wx_early = ZHI_WUXING.get(month_branch, "")
    day_wx_early = ZHI_WUXING.get(day_zhi, "")
    yong_line = _pick_yongshen_line(lines, yong_liuqin, month_branch)

    if yong_line is None:
        # 用神不现：检索链 本卦爻上 → 日月临用神之支 → 本宫首卦伏神 → 再占
        # （据《卜筮正宗·伏神正传》与《增删卜易·飞伏神章》；世爻是"我"的参照系，
        #   不是所问事物的状态量，两书皆无"取世爻兜底"之法，故废除。）
        wx_map = _liuqin_wuxing_map(W)
        X = wx_map[yong_liuqin]                      # 该六亲在本宫结构性对应的五行
        fu = _find_fushen(W, yong_liuqin, gua_data.get("palace", ""), lines,
                          month_wx_early, day_wx_early)
        if fu and fu.get("usable"):
            # R 必须在这里给：R_reason 写的是"伏神得出，加持事体五行"，
            # 而伏神的五行就是该六亲在本宫的五行 X（_find_fushen 的 fu_wx 即 wx_map[yong]）。
            # 2026-09-23 修：此前本支只写了 reason/state 没给 R，走到这一支必抛
            # UnboundLocalError（规则命中审计实测：随机 300 卦里有 26 卦走到这里，全崩）。
            R = fu.get("fu_wx") or X
            reason = (f"用神不上卦，日月又不临，取本宫首卦伏神【{fu['fu_zhi']}】"
                      f"伏于{fu['position']}爻{fu['fei_zhi']}之下（{fu['relation']}），"
                      f"伏神得出，加持事体五行；应期取{fu['yaoqi']}")
            state = "用神伏藏而得出"
        else:
            R = sheng_me(X)
            rel_txt = fu.get("relation", "飞伏关系不明") if fu else "首卦亦无可取"
            reason = (f"用神不上卦，取本宫首卦伏神（{rel_txt}），伏神受制难出，"
                      f"取生伏神者【{R}】以救；断语宜说明可再摇一卦以决（野鹤再占之法，得其一即止）")
            state = "用神伏藏受制"
            X_wx = X
            return {
                "X": X, "R": R, "R_reason": reason,
                "yongshen": yong_liuqin, "yongshen_source": yong_source,
                "yongshen_desc": f"用神不现，取本宫首卦伏神（{yong_liuqin}）",
                "state": state, "state_desc": "用神伏藏，宜冲飞露伏；再占可决",
                "details": {"伏神": fu or {"六亲": yong_liuqin, "五行": X},
                            "检索链": "本卦→日月→本宫伏神→再占"},
                **yong_meta,
            }
        return {
            "X": X, "R": R, "R_reason": reason,
            "yongshen": yong_liuqin, "yongshen_source": yong_source,
            "yongshen_desc": f"用神不现，取本宫首卦伏神{fu['fu_zhi']}（{yong_liuqin}）",
            "state": state, "state_desc": "用神伏藏得出，宜冲飞露伏",
            "details": {"伏神": {"爻位": fu["position"], "地支": fu["fu_zhi"], "五行": fu["fu_wx"]},
                        "飞神": {"爻位": fu["position"], "地支": fu["fei_zhi"], "五行": fu["fei_wx"]},
                        "飞伏关系": fu["relation"],
                        "检索链": "本卦→日月→本宫伏神→再占"},
            **yong_meta,
        }

    X = yong_line["wuxing"]
    day_wx = ZHI_WUXING.get(day_zhi, "")
    month_wx = ZHI_WUXING.get(month_branch, "")
    grade, score, flags = _line_strength(yong_line, X, month_branch, month_wx, day_zhi, day_wx, lines)

    # 元神 / 忌神 五行与爻
    if yong_liuqin == "世":
        yuanshen_wx = sheng_me(X)
        jishen_wx = ke_me(X)
        yuanshen_name = "生世之爻"
        jishen_name = "克世之爻"
        ys_lines = [l for l in lines if l["wuxing"] == yuanshen_wx]
        js_lines = [l for l in lines if l["wuxing"] == jishen_wx]
    else:
        yuanshen_name, yuanshen_wx, jishen_name, jishen_wx = _yuanshen_jishen(W, yong_liuqin)
        ys_lines = [l for l in lines if l.get("liuqin") == yuanshen_name]
        js_lines = [l for l in lines if l.get("liuqin") == jishen_name]

    # 忌神动克且有力 → 制忌
    jishen_strong = False
    jishen_status = []
    for l in js_lines:
        if not l.get("moving"):
            continue
        ok, why = _yishen_youli(l, month_branch, month_wx, day_zhi, day_wx, lines)
        if ok:
            jishen_strong = True
        jishen_status.append(f"{l['name']}{'有力' if ok else '无力'}")

    # 元神有力否
    ys_line = next((l for l in ys_lines if l.get("moving")), ys_lines[0] if ys_lines else None)
    yuanshen_strong, ys_why = _yishen_youli(ys_line, month_branch, month_wx, day_zhi, day_wx, lines)

    if jishen_strong:
        R = ke_me(jishen_wx)          # 制忌者五行
        reason = f"忌神【{jishen_name}】发动有力克用神，取克忌者【{R}】制忌"
        state = "忌神动克"
    elif grade == "休囚":
        if yuanshen_strong:
            R = yuanshen_wx           # 元神生用神
            reason = f"用神休囚（{'、'.join(flags)}），取元神【{yuanshen_name}】五行【{R}】生扶"
        else:
            R = sheng_me(yuanshen_wx)  # 元神无力 → 取生元神者以救
            reason = f"用神休囚且元神无力（{ys_why}），取生元神者【{R}】以救元神"
        state = "用神衰弱"
    else:
        R = X                         # 用神旺，维持
        reason = f"用神{grade}（{'、'.join(flags) if flags else '平和'}），直接加持用神五行【{R}】"
        state = f"用神{grade}"

    # ---- 以下为"已算未给"的补齐：_line_strength 早就把每爻的旺衰、分数、标志算出来了，
    # 但此前只用来选处方五行，从未交给 AI。AI 拿不到旺衰就只能自己推，这是幻觉第一来源。
    # 这里只**暴露**既有判定，不新增任何规则、不改判定结果。
    def _strength_of(ln):
        g, s, f = _line_strength(ln, ln["wuxing"], month_branch, month_wx,
                                 day_zhi, day_wx, lines)
        # 月令五态单列：综合档位只报二分（旺相／休囚），而书里的五态是月令一项的细分，
        # 二者都交出去——AI 才看得到"为什么这爻虽是休囚却相于月令"。
        return {"旺衰": g, "分数": s, "标志": list(f),
                "月令五态": _shiwang(ln["wuxing"], month_wx)[0]}

    per_line = []
    for l in lines:
        _st = _strength_of(l)
        per_line.append({
            "position": l["position"], "name": l["name"], "六亲": l["liuqin"],
            "干支": l.get("gan", "") + l.get("zhi", ""), "五行": l["wuxing"],
            "卦位": "世" if l.get("shi") else ("应" if l.get("ying") else ""),
            "动静": "动" if l.get("moving") else "静",
            **{k: _st[k] for k in ("旺衰", "分数", "月令五态")},
            "标志": _st["标志"],
        })

    yong_st = _strength_of(yong_line)
    ys_pos = ({**_strength_of(ys_line),
               "name": ys_line["name"], "position": ys_line["position"]}
              if ys_line is not None else {})
    js_st = [{"name": l["name"], "position": l["position"], **_strength_of(l)}
             for l in js_lines]

    month_day = {
        "月建": month_branch, "月建五行": month_wx,
        "日辰": day_zhi, "日辰干支": gua_data.get("time_info", {}).get("day_ganzhi", ""),
        "日辰五行": day_wx,
        # 卦气表：由 _shiwang 逐五行取月令五态（当令者旺、令生者相、生令者休、克令者囚、令克者死）
        "卦气": {w: _shiwang(w, month_wx)[0] for w in ("金", "木", "水", "火", "土")},
    }

    result = {
        "X": X,
        "R": R,
        "R_reason": reason,
        "yongshen": yong_liuqin,
        "yongshen_source": yong_source,
        "yongshen_desc": yong_line["liuqin"] + ("（手动指定）" if yong_source == "manual" else ""),
        **yong_meta,
        "state": state,
        "state_desc": "、".join(flags) if flags else "平和",
        "details": {
            "月建日辰": month_day,
            "用神爻": {"position": yong_line["position"], "name": yong_line["name"],
                        "六亲": yong_line["liuqin"], "五行": yong_line["wuxing"],
                        "干支": yong_line.get("gan", "") + yong_line.get("zhi", ""),
                        "发动": yong_line.get("moving", False),
                        "世爻": yong_line.get("shi", False),
                        **{k: yong_st[k] for k in ("旺衰", "分数", "月令五态")},
                        "标志": yong_st["标志"]},
            "元神": {"六亲": yuanshen_name, "五行": yuanshen_wx, "有力": yuanshen_strong,
                      "说明": ys_why, **ys_pos},
            "忌神": {"六亲": jishen_name, "五行": jishen_wx, "发动": bool(jishen_status),
                      "状态": "、".join(jishen_status) if jishen_status else "静",
                      "爻位": js_st},
            "各爻旺衰": per_line,
        },
    }

    # 逐爻细看（六神断语表·显示层）：放在最后算，因为角色的判定要用到上面这份结果。
    # 它只呈现既有判定 + 书上条文，不进红黄绿、不改处方、不改应期（见 liuyao_liushou.py 的边界声明）。
    result["逐爻细看"] = per_line_readings(gua_data, result)
    return result


if __name__ == "__main__":
    from liuyao_engine import build_paipan
    g = build_paipan([{"x": 1.1, "y": 2.2, "duration": 300, "speed": 0.5}] * 6)
    for q in ["求财能成吗", "这次升职有望吗", "买这套房子合适吗", "孩子这次考试怎么样", "我最近运势如何"]:
        r = liuyao_remedy(g, q)
        print(f"[{q}] 用神={r['yongshen']} X={r['X']} R={r['R']} | {r['state']} | {r['R_reason']}")
