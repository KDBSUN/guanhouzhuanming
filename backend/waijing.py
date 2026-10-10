# -*- coding: utf-8 -*-
"""
外应参断（waijing）——"合内外而断"的那一层
================================================
**这个模块存在的理由**：梅花重"机"，起卦之后随时可能出现新的外应（刻应／外应）。
书里对此的处置**不是重新起卦、也不是改动原卦**，而是"原来那一卦照旧，把新冒出来的
外应归入刻应／外应一类（即'外卦'），以体卦为主，与用卦、互卦、变卦参看，作加减损益
之后再定吉凶"。

条文依据（均经回源核验，标点宽容后逐字命中；详见 docs/产品逻辑链框架.md 第 12 节）：

  · 《内外论》：「凡占卜，体用为内，诸应卦为外卦，此占卜之例也。诸应卦与"三要"之应，
    与"十应"之应，必合内外卦而断之也。」「占卜之精者，无非合内外之道也。」
  · 《占卜总诀》：「必须以易卦为主，克应次之。俱吉则大吉，俱凶则大凶，有凶有吉，
    则详审卦辞，及克用体应之类，以断吉凶也，要在圆机，不可执。」
  · 《十应目论》：「"十应"并以体卦为主，诸用卦为用。每以内分外体，用卦参看为妙。
    内卦不吉而外卦又吉，可以解其不吉；内卦吉而外卦不吉，反破其吉。若内外卦全吉，
    则断然吉。全凶则断然凶。其内吉外凶，内凶外吉，又须详理以断吉凶，慎不可胶柱鼓瑟也。」
  · 《占卜十应诀》：「刻应者，即"三要"之诀也…」「外应者，外卦之应也。占卜之际，
    偶见外物之来者，即看其物属何卦。」
  · 《内外论》给"为何会反"的机制：「金银为世宝，三要为吉者，若震、巽为体，则金克木，
    反为不吉…占病见棺必死，若遇离体，则木生火而反吉。」→ **反不反，取决于外应之卦与体卦的生克**。
  · 《向背》辨来去、《体用动静之诀》辨迟速、《动静》给多应取舍、《静占》说无闻见则不论。

**本模块只做三件事**：配卦 → 与体卦论生克比和 → 内外合断。它**不改卦**：
不重起、不动体用、不改互变、不换动爻（输出恒带 `moves_gua: False`）。

**不做的事**：不发明原文没有的加法。原文只给"可以解其不吉／反破其吉／须详理"这类
定性方向，没给算式；故凡原文未直断的组合一律标 `verdict="须详理"`，绝不代拟一个吉凶。
"""
import json
import re
from pathlib import Path

_XIANG = json.loads((Path(__file__).parent / "waijing_xiang.json").read_text(encoding="utf-8"))

# 体卦五行的生克（用五行常理，与全书一致；出处：《五行大义》＋本书通篇用法）
_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}   # 我生
_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}      # 我克

GUA_WUXING = {g: e["wuxing"] for g, e in _XIANG["bagua"].items()}

# 版本声明与**用户裁定**：
# 《三要灵应篇》"卦吉而应□终吉"一句两版义理相反——
#   · 学林2003（通行本）：卦吉而应**凶**终吉。卦凶而应**吉**终凶 → **卦为主**（外应不翻转内卦）
#   · 增广校正2007      ：卦吉而应**吉**终吉，卦凶而应**凶**终凶 → 同向则加倍
# **用户已选定学林本**（原话："应凶终吉"），故默认 policy="gua_first"。
# 但《十应目论》另有一句方向相反且同样逐字可验的话：「内卦吉而外卦不吉，**反破其吉**」。
# 两者不是谁抄错，而是层次不同：三要灵应篇讲"终局归谁"，十应目论讲"外卦如何参与权衡"。
# 故做成可切换策略：默认按用户所定，另一条随时可切，且各自带自己的书证。
COMBINE_POLICY = "gua_first"    # "gua_first"（卦为主·学林本，默认）| "omen_breaks"（外应可反破·十应目论）

VERSION_NOTE = (
    "版本已定：采学林出版社2003本《三要灵应篇》——「卦吉而应凶终吉。卦凶而应吉终凶，"
    "卦应一吉一凶，事体半吉半凶」。即**外应与内卦相左时，终局仍随内卦**（终吉／终凶），"
    "「事体」层面则标为半吉半凶。另注：《十应目论》有「内卦吉而外卦不吉，反破其吉」一句，"
    "方向与此相反；本模块以学林本为准，如需改用那一读法，把 COMBINE_POLICY 改成 omen_breaks。"
)


# ---------------------------------------------------------------------------
# 一、外应配卦：由具体到一般，四级次序即原文次序
# ---------------------------------------------------------------------------

def _field_terms(gua: str, field: str) -> list:
    return list(_XIANG["bagua"][gua].get(field) or [])


_KEYS = _XIANG.get("keys", {}).get("map", {})

# 口语虚词遮蔽：单字类象词（天／日／月／山／水…）会落在日常词汇里被误配。
# 实例：用户说"今天心情复杂"，"天"是乾卦天时，于是被配成"乾·金→外应克体→反破其吉"——
# 一句与占问无关的托辞竟能改结论。故先把这类词整体遮蔽掉再匹配。
# 只遮蔽"整词"，不动任何原文；表外的新词一旦出现同类误配，往这里加即可。
_SHIELD = ("今天", "明天", "昨天", "前天", "后天", "每天", "那天", "这天", "白天", "天天",
           "一天", "半天", "聊天", "心情", "事情", "东西", "时候", "有点", "说不清")
_SHIELD_RE = re.compile("|".join(_SHIELD))


def _shield(text: str) -> str:
    """把日常虚词换成等长占位符（保留长度，避免影响"邻近"之类判断）。"""
    return _SHIELD_RE.sub(lambda m: "\u3000" * len(m.group(0)), text)


def _expand(term: str) -> list:
    """原文词 → 可用于检索的词序列（原文词本身 + 检索词表里的近义说法）。

    检索词表存在的理由：原文写"钟声钲铎"，用户会说"敲钟"；原文写"百禽"，用户会说"麻雀"。
    表里只有检索用词，不改动任何原文，命中后给出的仍是原文条目与行号。
    """
    out = [term]
    for k in _KEYS.get(term, []) or []:
        if k not in out:
            out.append(k)
    return out


def resolve_omen(text: str, max_candidates: int = 4) -> dict:
    """把一句外应描述配成卦。**匹配不到就返回空，绝不猜。**

    五级次序（前四级皆原文，第五级为标注过的类推）：
      ① 《占卜十应诀》诸应（天时应／地理应／人事应）——**该篇正是"外应"的定义章节，故优先**
      ② 《八卦万物属类》逐卦类象表（静物／动物／人物／屋宿／饮食／天时／地理／五色）
      ③ 《形物占》（"物之圆者属乾，刚者属兑…"）
      ④ 《复明静物之应》器物归卦（"水属坎，火属离，木之气属震巽…"）
      ⑤ 类推表（原文无此词，依"触类而长之"延伸；**恒标 extrapolated，供人复核**）
    """
    raw = (text or "").strip()
    if not raw:
        return {"candidates": [], "text": raw, "ambiguous": False,
                "note": "外应为空，未配卦。", "extrapolated": False}
    probe = _shield(raw)          # 匹配用文本：已遮蔽日常虚词（见 _SHIELD 说明）

    hits = []

    def add(gua, by, term, src, extrapolated=False):
        hits.append({"gua": gua, "wuxing": GUA_WUXING[gua], "by": by, "term": term,
                     "src": src, "extrapolated": extrapolated})

    # ① 《占卜十应诀》诸应
    shi = _XIANG.get("shiying", {}).get("items", {})
    for name, item in shi.items():
        for term, guas in item.get("rules") or []:
            if any(k in probe for k in _expand(term)):
                for g in guas:
                    add(g, name, term, "%s·%s" % (_XIANG["shiying"]["src"], name))

    # ② 类象表（先长词后短词，长词更能定性）
    if not hits:
        fields = [("静物", "静物"), ("动物", "动物"), ("人物", "人物"), ("屋宿", "屋宿"),
                  ("屋舍", "屋舍"), ("饮食", "饮食"), ("天时", "天时"), ("地理", "地理"),
                  ("五色", "五色")]
        found = []
        for gua in _XIANG["bagua"]:
            for f, label in fields:
                for term in _field_terms(gua, f):
                    for k in _expand(term):
                        if k and k in probe:
                            found.append((len(k), gua, term, k, label))
        found.sort(key=lambda x: -x[0])
        if found:
            top = found[0][0]
            # 只保留与最长命中同量级的：避免"水""黑"这类单字把一堆卦都拉进来。
            # 但阈值下限是 1——单字命中（如"雨""风"）本身就是原文条目，不能一并滤掉；
            # 有双字以上命中时则只取最长的，避免色名等弱命中盖过器物名。
            keep = top if top >= 2 else 1
            for ln, gua, term, k, label in found:
                if ln >= keep:
                    add(gua, "类象·%s" % label, term,
                        "《梅花易数》卷一·八卦万物属类（%s）" % label)

    # ③ 形物占
    if not hits:
        for shape, guas in _XIANG["xingwu"]["rules"]:
            if shape in probe:
                for g in guas:
                    add(g, "形物占", shape, "《梅花易数》卷一·形物占（1048–1051 行）")

    # ④ 听声音占
    if not hits:
        for snd, guas in _XIANG["shengyin"]["rules"]:
            if any(k in probe for k in _expand(snd)):
                for g in guas:
                    add(g, "听声音占", snd, "《梅花易数》卷一·听声音占（1042 行）")
        if not hits and any(w in probe for w in ("说话", "人语", "叫声", "鸣叫", "哭泣", "哭", "笑声", "笑", "喊", "叫")):
            add("兑", "听声音占·口出之声", "人语/鸣叫",
                "《梅花易数》卷一·听声音占（1042 行）：如人语声，及动物鸣叫之声，声自口出者属兑")

    # ⑤ 器物归卦（五行之气）
    if not hits:
        for wx, guas in _XIANG["qiwu_guaxiang"]["map"].items():
            if wx + "气" in probe or wx in probe:
                for g in guas:
                    add(g, "器物归卦（五行气）", wx + "气",
                        "《梅花易数》卷二·复明静物之应（2320–2328 行）")

    # ⑥ 类推（原文无此词，依授权延伸；恒标 extrapolated 并排在原文命中之后）
    # 为什么**不**只在"原文一条都没命中"时才跑：外应里最显眼的往往是活物（猫、车、手机），
    # 而原文类象表收的是"百兽""大途"这类类名，逐字匹配不到。若一律不补，
    # 用户说"一只黑猫趴在墙头"只会得到"墙→兑"，把最要紧的那一应漏掉。
    # 故补齐但排在后面、且带标，由用户定取舍（《动静》"取强不取弱"本就要人判断）。
    extrapolated = False
    lt = _XIANG.get("leitui", {})
    for word, guas in lt.get("rules") or []:
        if word in probe:
            for g in guas:
                add(g, "类推", word, lt.get("src", "工程类推"), extrapolated=True)
            extrapolated = True

    # 去重（同卦同依据同词只留一条）
    seen, uniq = set(), []
    for h in hits:
        k = (h["gua"], h["by"], h["term"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(h)

    # 排序：原文命中优先于类推；同类则具体（词长）优先。
    # 理由：《动静》讲"取强不取弱"，而"哪一应更强"最终由人判断（"以吾之一念所在者"），
    # 故这里只做**排序建议**，不裁掉候选——裁掉就等于替用户拍板。
    uniq.sort(key=lambda h: (h["extrapolated"], -len(h["term"])))

    guas = {h["gua"] for h in uniq}
    if not uniq:
        note = ("未能在类象表中找到对应。请换一个说法——说出**器物名、形状、颜色、方位、"
                "或它是五行中的哪一类**最容易被配到卦；也可以直接指定卦。"
                "本模块不会替你猜一个卦。")
    elif len(guas) > 1:
        note = ("命中多个卦。原文类象本是'以类相推'的开放框架，同一外应可归数卦，"
                "故此处不替你拍板——请指定其中一个。")
    else:
        note = ""
    return {"candidates": uniq[:max_candidates], "text": raw,
            "ambiguous": len(guas) > 1, "note": note, "extrapolated": extrapolated}


# ---------------------------------------------------------------------------
# 二、与体卦论生克比和（《十应目论》《内外论》）
# ---------------------------------------------------------------------------

# 方向 → 原文断语。**原文只对"生体／比和／克体"三种给了明确方向**，
# 体生（泄）与体克（我克）在"十应"框架里没有直断，故标"须详理"，不代拟吉凶。
_REL_EFFECT = {
    "外应生体": ("可以解其不吉", "吉", "《十应目论》：内卦不吉而外卦又吉，可以解其不吉。"),
    "比和": ("助吉", "吉", "《十应目论》以体卦为主，比和则同气相助；《观物诸诀》谓比和者乃有用成器之物。"),
    "外应克体": ("反破其吉", "凶", "《十应目论》：内卦吉而外卦不吉，反破其吉。"),
    "体生外应": ("泄体，须详理", "须详理", "原文于'十应'参断未直断体生外应之吉凶（《又诀》仅谓'体生者为不成之器'），故不代拟。"),
    "体克外应": ("我克之，须详理", "须详理", "原文于'十应'参断未直断体克外应之吉凶（《又卦》仅谓'体克者为破碎损折之物'），故不代拟。"),
}


def relation_of(ti_wuxing: str, omen_wuxing: str) -> str:
    """体卦与外应之卦的五行关系。"""
    ti, om = (ti_wuxing or "").strip(), (omen_wuxing or "").strip()
    if ti not in _SHENG or om not in _SHENG:
        return "未知"
    if ti == om:
        return "比和"
    if _SHENG[om] == ti:
        return "外应生体"
    if _SHENG[ti] == om:
        return "体生外应"
    if _KE[om] == ti:
        return "外应克体"
    if _KE[ti] == om:
        return "体克外应"
    return "未知"


def adjudicate(ti_wuxing: str, omen_gua: str) -> dict:
    """单个外应与体卦的参断。"""
    wx = GUA_WUXING.get(omen_gua, "")
    rel = relation_of(ti_wuxing, wx)
    effect, polarity, src = _REL_EFFECT.get(rel, ("未知", "须详理", ""))
    return {
        "gua": omen_gua, "wuxing": wx, "ti_wuxing": ti_wuxing,
        "relation": rel, "effect": effect, "polarity": polarity,
        "reason": "体%s，外应%s（%s）→ %s" % (ti_wuxing, wx, omen_gua, rel),
        "src": src,
    }


# ---------------------------------------------------------------------------
# 三、向背与动静：只调"力之强弱与迟速"，不改吉凶本身
# ---------------------------------------------------------------------------

def modulate(direction: str = "", motion: str = "") -> dict:
    """《向背》辨来去、《体用动静之诀》辨迟速。

    direction: '来' | '去' | ''（未说）
    motion:    '动' | '不动' | ''（未说）
    """
    out = {"strength": "中", "timing": "", "notes": [], "src": []}
    if direction == "来":
        out["strength"] = "强"
        out["notes"].append("外应方来，事将至，信息力强（《向背》）。")
        out["src"].append("《向背》：其克体之卦，器物方来，其祸将至，去则祸散。")
    elif direction == "去":
        out["strength"] = "弱"
        out["notes"].append("外应已去，所主之事已成过去，参考价值减弱（《向背》）。")
        out["src"].append("《向背》：其生体之卦，器物方来则吉，去则吉已过矣。")
    if motion == "动":
        out["timing"] = "应期速"
        out["notes"].append("动而应者，吉凶皆速（《体用动静之诀》）。")
        out["src"].append("《体用动静之诀》：动而吉者，应吉之速；动而凶者，应凶之速。")
    elif motion == "不动":
        out["timing"] = "吉凶未见"
        out["notes"].append("不动而应者，吉凶之未见也（《体用动静之诀》）。")
        out["src"].append("《体用动静之诀》：不动而应者，吉凶之未见也。")
    if not out["notes"]:
        out["notes"].append("未说明来去与动静，故不调强弱迟速（原文以此二者定之，缺则不臆断）。")
    return out


# ---------------------------------------------------------------------------
# 四、多应并存时的取舍（《动静》）
# ---------------------------------------------------------------------------

def pick_primary(omens: list) -> dict:
    """群动之中的取舍法则。

    原文：「盖于群动之中，或观其身临吾耳目之近者，或以先见者，或以群事分明者，
    或以吾之一念所在者，此发占之所用。」

    **工程默认（须声明）**：用户按先后顺序说出的外应，以**第一条**当"先见者"。
    其余三条（近者／分明者／一念所在）需要用户自己标注，本函数不替用户判断
    ——那属于"当下之机"，代码无从得知。
    """
    if not omens:
        return {"primary": None, "basis": "", "note": "无外应。"}
    return {
        "primary": omens[0],
        "basis": "先见者",
        "note": ("工程默认：以用户最先说出的外应为'先见者'。原文取舍另有"
                 "'近耳目者／群事分明者／一念所在者'三条，需你自行指明——"
                 "那属当下之机，代码无从得知。"),
        "src": "《动静》：盖于群动之中，或观其身临吾耳目之近者，或以先见者，或以群事分明者，或以吾之一念所在者，此发占之所用。",
    }


# ---------------------------------------------------------------------------
# 五、内外合断（《十应目论》＋《三要灵应篇》）
# ---------------------------------------------------------------------------

_INNER_POLARITY = {"顺": "吉", "平": "中", "逆": "凶"}


def combine(inner_net: str, effects: list, policy: str = "") -> dict:
    """内卦（体用互变的结论）× 外卦（新外应）→ 合断。

    inner_net: 内卦净档 '顺' | '平' | '逆'（本项目 wuxing_relation 的三档）
    effects:   adjudicate() 的结果列表
    policy:    外应与内卦相左时谁说了算（默认取模块级 COMBINE_POLICY，即用户选定的学林本读法）
    """
    pol = policy or COMBINE_POLICY
    inner = _INNER_POLARITY.get((inner_net or "").strip(), "中")
    pols = [e.get("polarity") for e in effects if e.get("polarity") in ("吉", "凶")]
    has_unknown = any(e.get("polarity") == "须详理" for e in effects)

    if not effects:
        return {"net": inner_net, "verdict": "内卦照旧", "polarity": inner, "policy": pol,
                "say": "未闻未见外应，则无外卦，即不论外卦——径以体用（内卦）决之。",
                "src": "《静占》：凡应占在静室，无所闻见，则无外卦，即不论外卦。但以全卦年、月、日值五行衰旺之气，以体用决之。"}

    # 外卦的吉凶：**"全吉""全凶"要求诸应一致**。原文说"若内外卦全吉，则断然吉；
    # 全凶则断然凶"，"全"字是有分量的——几条外应一吉一凶时不是"全"，据同段末句
    # "又须详理以断吉凶"，应落到"事体半吉半凶"那一档，不能取最坏的那一条当结论。
    if not pols:
        ext = "中"
    elif all(p == "吉" for p in pols):
        ext = "吉"
    elif all(p == "凶" for p in pols):
        ext = "凶"
    else:
        ext = "杂"

    if inner == "吉" and ext == "吉":
        v = ("断然吉", "吉", "若内外卦全吉，则断然吉。",
             "《十应目论》：若内外卦全吉，则断然吉。")
    elif inner == "凶" and ext == "凶":
        v = ("断然凶", "凶", "全凶则断然凶。",
             "《十应目论》：全凶则断然凶。")
    elif inner == "吉" and ext == "凶" and pol == "gua_first":
        v = ("终吉（外应相左，事体半吉半凶）", "吉",
             "卦吉而应凶终吉——外应相左不足以翻转内卦，但事体层面已见半吉半凶。",
             "《三要灵应篇》（学林本）：卦吉而应凶终吉。卦应一吉一凶，事体半吉半凶。")
    elif inner == "凶" and ext == "吉" and pol == "gua_first":
        v = ("终凶（外应相左，事体半吉半凶）", "凶",
             "卦凶而应吉终凶——外应相左不足以翻转内卦，但事体层面已见半吉半凶。",
             "《三要灵应篇》（学林本）：卦凶而应吉终凶。卦应一吉一凶，事体半吉半凶。")
    elif inner == "吉" and ext == "凶":
        v = ("反破其吉", "凶", "内卦吉而外卦不吉，反破其吉。",
             "《十应目论》：内卦吉而外卦不吉，反破其吉。")
    elif inner == "凶" and ext == "吉":
        v = ("可以解其不吉", "中", "内卦不吉而外卦又吉，可以解其不吉。",
             "《十应目论》：内卦不吉而外卦又吉，可以解其不吉。")
    else:
        v = ("事体半吉半凶，须详理", "中",
             "卦应一吉一凶，事体半吉半凶；又须详理以断吉凶，慎不可胶柱鼓瑟也。",
             "《三要灵应篇》：卦应一吉一凶，事体半吉半凶。明生克之理，察动静之机…务要相机而发，须要临事而详。")
    verdict, polarity, why, src = v
    return {
        "net": inner_net, "verdict": verdict, "polarity": polarity, "policy": pol,
        "inner": inner, "outer": ext,
        "say": why,
        "has_undecided": has_unknown,
        "src": src,
        "tie_break_src": "《三要灵应篇》：卦应一吉一凶，事体半吉半凶。明生克之理，察动静之机…务要相机而发，须要临事而详。",
    }


# ---------------------------------------------------------------------------
# 总入口
# ---------------------------------------------------------------------------

def sanyao_lines(text: str, limit: int = 3) -> list:
    """《三要灵应篇》取象断语里与本条外应相关的**原文**。

    取象断语是"这一物象本身主什么"（云开见日，事必增辉），不是配卦规则——所以不进
    resolve_omen 的候选，只作可引用的原文附在参断块后面。给 AI 是为了让它引得出原文
    （引得出原文才算有据），否则它只能空口说吉凶，那是代拟。
    """
    probe = _shield(text or "")
    if not probe:
        return []
    hits = []
    for name, item in (_XIANG.get("sanyao", {}).get("items") or {}).items():
        for k in item.get("keys") or []:
            if k and k in probe:
                hits.append({"name": name, "text": item["text"], "matched": k,
                             "src": _XIANG["sanyao"]["src"]})
                break
    hits.sort(key=lambda h: -len(h["matched"]))
    return hits[:limit]


def analyze(text: str, ti_wuxing: str, chosen_gua: str = "",
            direction: str = "", motion: str = "", inner_net: str = "") -> dict:
    """一次外应参断的完整结果（供端点与前端直接用）。

    chosen_gua 为空时，若配卦候选唯一则自动采用；有歧义则不采用、交回用户选择
    ——**歧义时不猜**，这是本模块唯一的硬规矩。
    """
    resolved = resolve_omen(text)
    cands = resolved["candidates"]
    gua = chosen_gua or (cands[0]["gua"] if len({c["gua"] for c in cands}) == 1 else "")
    adj = adjudicate(ti_wuxing, gua) if gua else None
    eff = [adj] if adj else []
    mod = modulate(direction, motion)
    return {
        "omen": text,
        "resolve": resolved,
        "chosen_gua": gua,
        "needs_choice": (not gua) and bool(cands),
        "adjudication": adj,
        "modulation": mod,
        "combined": combine(inner_net, eff) if inner_net else None,
        "sanyao": sanyao_lines(text),
        "moves_gua": False,
        "moves_gua_say": ("内卦（体用互变）**不动**：原文只言'必合内外卦而断之'，"
                          "未见因外来之应而改卦、改爻或另起一卦的条文。"),
        "version_note": VERSION_NOTE,
    }


def analyze_many(texts, ti_wuxing: str, inner_net: str = "",
                 direction: str = "", motion: str = "",
                 chosen: dict = None) -> dict:
    """多条外应的整体参断。

    chosen: {外应原文: 卦} —— 用户在歧义时指定的卦；未指定的按自动配卦结果。
    多应并存时按《动静》给出"先见者"作为主应（工程默认，见 pick_primary）。
    """
    chosen = chosen or {}
    items = []
    for t in (texts or []):
        t = (t or "").strip()
        if not t:
            continue
        items.append(analyze(t, ti_wuxing, chosen_gua=chosen.get(t, ""),
                             direction=direction, motion=motion, inner_net=inner_net))
    picked = pick_primary(items)
    # 整体合断：以已定卦的那些外应参与（未配到卦的不能参与，否则等于拿空气加减）
    decided = [it for it in items if it["adjudication"]]
    combined = combine(inner_net, [it["adjudication"] for it in decided]) if inner_net else None
    sy, seen = [], set()
    for it in items:
        for h in it.get("sanyao") or []:
            if h["name"] not in seen:
                seen.add(h["name"])
                sy.append(h)
    return {
        "items": items,
        "sanyao": sy,
        "primary": picked,
        "combined": combined,
        "needs_choice": [it["omen"] for it in items if it["needs_choice"] or not it["adjudication"]],
        "moves_gua": False,
        "version_note": VERSION_NOTE,
    }


def to_prompt_block(result: dict) -> str:
    """把参断结果编成给 LLM 的**只读**上下文块。

    为什么必须由代码给、而不是让 AI 自己推：外应配卦与生克参断是**有书证的判据**
    （见模块头），交给模型自由发挥就等于让它现场编一条术数规则——那是本项目
    "绝不代拟"红线禁止的。所以这里把结论钉死，并明确要求 AI 不得改写判定，
    只负责用白话把已定的结论讲清楚。
    """
    lines = ["【外应参断（由代码依原著条例判定，不得改写、不得另立规则）】"]
    for it in result.get("items") or []:
        res, adj = it["resolve"], it["adjudication"]
        cand = "、".join("%s(%s)" % (c["gua"], c["by"]) for c in res["candidates"]) or "无"
        if adj:
            lines.append("· 外应「%s」→ 配卦 %s（%s，%s）｜体%s → %s｜断：%s（%s）"
                         % (it["omen"], adj["gua"], adj["wuxing"],
                            "类推" if res.get("extrapolated") else "原文类象",
                            adj["ti_wuxing"], adj["relation"], adj["effect"], adj["polarity"]))
            if adj.get("src"):
                lines.append("  书证：%s" % adj["src"])
        elif res["candidates"]:
            lines.append("· 外应「%s」→ 候选 %s（**有歧义，未定**，请如实说明需用户指定，不要自行选定）"
                         % (it["omen"], cand))
        else:
            lines.append("· 外应「%s」→ **未能配卦**（类象表中无对应）：不要凭空配卦，"
                         "请说明此应暂不参与加减，并建议用户换个说法或直接指定卦。" % it["omen"])
        mod = it.get("modulation") or {}
        for n in mod.get("notes") or []:
            lines.append("  · %s" % n)
    sy = result.get("sanyao") or []
    if sy:
        lines.append("· 相应三要取象（%s；**原文照录，可直接引用；不得改写、不得添句**）：" % sy[0]["src"])
        for h in sy:
            lines.append("  【%s】%s" % (h["name"], h["text"]))
    comb = result.get("combined")
    if comb:
        lines.append("· 内外合断：内卦「%s」× 外卦「%s」→ **%s**（%s）"
                     % (comb.get("inner"), comb.get("outer"), comb["verdict"], comb["say"]))
        lines.append("  书证：%s" % comb["src"])
    p = result.get("primary") or {}
    if p.get("primary"):
        lines.append("· 多应并存时择主（%s）：以「%s」为主应。%s"
                     % (p.get("basis", ""), p["primary"]["omen"], p.get("note", "")))
    lines.append("· **内卦不动**：不得因外应而重起一卦、改体用、改互变或改动爻。")
    lines.append("· 若外应与内卦结论相左，照《十应目论》「反破其吉／可以解其不吉」如实说，"
                 "并提醒「须详理」，不要机械加减。")
    lines.append("· 版本提示：%s" % result.get("version_note", ""))
    return "\n".join(lines)
