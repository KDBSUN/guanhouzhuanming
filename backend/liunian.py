# -*- coding: utf-8 -*-
"""
岁运层（流年引动）
==================
把《滴天髓》从象/化象/假从三章的行运文字固化成判定表，从 adjudicate 的
liunian_wx 预留插口接入。接入原则（据 2025 年岁运层讨论定案）：
  1. 流年不推翻月令——流年五行先被起卦当月的月令"称重"（旺相休囚死），
     旺相权重高、休居中、囚死近乎不计；
  2. 以小权重参与"引动"检查：引动忌神→降级放行、生扶喜用→升格/加成、
     与转急调候同调/相克→复用主裁决 2/2b 的同一逻辑；
  3. 不参与改方：处方五行 R 的拦截与改方仍由主裁决（忌神/调候/喜用三道门）负责，
     岁运层只升降档位与加注记，绝不把 gate 推到 block。
行运判定以十神角色（相对日主）查表：印＝生我的、比劫＝同我的、
食伤＝我生的、财＝我克的、官杀＝克我的。

书证（《滴天髓》任铁樵注，见 books/ 图解滴天髓上）：
  从象章：从旺"官杀运谓之犯旺，凶祸立至；遇财星，群劫相争"；
          从势"须行财运以和之…行官杀运次之；行食伤运又次之；行比劫印绶必凶无疑"。
  从儿章："从儿格最忌印运，次忌官运""又要运行财地，儿又生孙"。
  假从章："假行真运…从财有比劫分争行官杀运必贵，行食伤运必富。
           有印绶暗生要行财运…反此者凶"。
  化象章：化神"旺而有余，宜泄化神之神为用；化神衰而不足，宜生助化神之神为用"。
  旺相休囚死（《渊海子平》/《五行大义》）：当令者旺、我生者相、生我者休、克我者囚、我克者死。
"""
import re
from datetime import datetime

from wuxing_relation import SHENG, KE, tiao_active, grade_T
from weights import SHIWANG_WEIGHT, STRONG_THRESHOLD

ZHI_WUXING = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
              "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}

# 过秤权重与阈值已迁入 weights.yaml 集中配置（带版本号与"工程默认值，未经案例校准"标注）；
# 权重数值变更走 yaml + weights_version，决策日志记录裁决发生时的版本。


def current_liunian() -> dict:
    """当前流年（以立春分界的八字年柱为准）。太岁以年支为主气（太岁者一年之主）。"""
    from lunar_python import Solar
    now = datetime.now()
    solar = Solar.fromYmdHms(now.year, now.month, now.day, now.hour, now.minute, 0)
    ganzhi = solar.getLunar().getEightChar().getYear()
    gan, zhi = ganzhi[0], ganzhi[1]
    return {"ganzhi": ganzhi, "gan": gan, "zhi": zhi, "wx": ZHI_WUXING[zhi]}


def shiwang_liunian(wx: str, month_wx: str) -> tuple:
    """流年五行过秤：按起卦月令打旺相休囚死（当令旺、令生相、生令休、克令囚、令克死）。"""
    if wx == month_wx:
        state = "旺"
    elif SHENG[month_wx] == wx:
        state = "相"
    elif SHENG[wx] == month_wx:
        state = "休"
    elif KE[wx] == month_wx:
        state = "囚"
    else:
        state = "死"
    return state, SHIWANG_WEIGHT[state]


def shishen_role(dm_wx: str, wx: str) -> str:
    """行运五行相对日主的十神角色（按五行，不分阴阳）。"""
    if wx == dm_wx:
        return "比劫"
    if SHENG[dm_wx] == wx:
        return "食伤"
    if KE[dm_wx] == wx:
        return "财"
    if SHENG[wx] == dm_wx:
        return "印"
    return "官杀"


# ---------------------------------------------------------------------
# 从格行运判定表（role → (verdict, reason, src)）
# verdict: good＝顺/吉（引动喜用）｜warn＝警示（注记）｜bad＝犯格（引动凶）
# ---------------------------------------------------------------------
CONGGE_TABLE = {
    "从儿": {
        "食伤": ("good", "顺势，秀气流行", "滴天髓·从儿：从儿不管身强弱"),
        "财": ("good", "儿又生孙，运行财地可享儿孙之荣", "滴天髓·从儿（任氏注）"),
        "比劫": ("good", "比劫仍去生助食伤，顺势不逆", "滴天髓·从儿（任氏注）"),
        "官杀": ("bad", "次忌官运——起争战之风，不伤人丁则散财", "滴天髓·从儿（任氏注）"),
        "印": ("bad", "从儿格最忌印运——印克食伤，其祸立至", "滴天髓·从儿（任氏注）"),
    },
    "从财": {
        "财": ("good", "从其旺势，财星得地", "滴天髓·从象"),
        "食伤": ("good", "食伤生财，从神得生", "滴天髓·从象（原注：看其意向）"),
        "官杀": ("good", "从财行官杀运必贵（财生官）", "滴天髓·假从（任氏注）"),
        "印": ("bad", "印绶生身破从，从之不真", "滴天髓·从象（绝无一毫生扶）"),
        "比劫": ("bad", "比劫分争，群劫争财", "滴天髓·假从（任氏注）"),
    },
    "从杀": {
        "官杀": ("good", "从其旺势，杀星得地", "滴天髓·从象"),
        "财": ("good", "财生杀党，行财运而禄重", "滴天髓·假从（任氏注）"),
        "印": ("bad", "印化杀生身，从之不真", "滴天髓·从象"),
        "食伤": ("bad", "食伤制杀，破从之根", "滴天髓·从象（任氏注：克神则衰）"),
        "比劫": ("bad", "比劫帮身不从", "滴天髓·从象"),
    },
    "从势": {
        "财": ("good", "行财运以和之——引通食伤、助其财官，最吉", "滴天髓·从象（任氏注）"),
        "官杀": ("good", "行官杀运次之", "滴天髓·从象（任氏注）"),
        "食伤": ("good", "行食伤运又次之", "滴天髓·从象（任氏注）"),
        "印": ("bad", "行比劫印绶必凶无疑", "滴天髓·从象（任氏注）"),
        "比劫": ("bad", "行比劫印绶必凶无疑", "滴天髓·从象（任氏注）"),
    },
    "专旺": {
        "比劫": ("good", "运行比劫则吉", "滴天髓·从象（任氏注：从旺）"),
        "印": ("good", "印绶运亦佳", "滴天髓·从象（任氏注）"),
        "食伤": ("good", "印轻行伤食亦佳，泄秀顺局", "滴天髓·从象（任氏注）"),
        "官杀": ("bad", "官杀运谓之犯旺，凶祸立至", "滴天髓·从象（任氏注）"),
        "财": ("bad", "遇财星群劫相争，九死一生", "滴天髓·从象（任氏注）"),
    },
}

# 假从（从财/从杀/从势之假从）：行运去假扶真则吉，助假则凶（《滴天髓·假从》）
CONGGE_TABLE_JIA = {
    "财": ("good", "假行真运——从神旺地，亦可取富贵", "滴天髓·假从（任氏注）"),
    "官杀": ("good", "假行真运——如从财有比劫分争，行官杀运必贵", "滴天髓·假从（任氏注）"),
    "食伤": ("good", "假行真运——行食伤运必富", "滴天髓·假从（任氏注）"),
    "印": ("bad", "助假破从，反此者凶", "滴天髓·假从（任氏注）"),
    "比劫": ("bad", "助假破从，反此者凶", "滴天髓·假从（任氏注）"),
}

# 假专旺：顺势之行吉；逆神与生逆者警示（假从可发其身，仍防犯旺）
CONGGE_TABLE_JIA_ZHUANWANG = {
    "比劫": ("good", "顺势，假行真运", "滴天髓·假从（任氏注）"),
    "印": ("good", "顺势生旺，假行真运", "滴天髓·假从（任氏注）"),
    "食伤": ("good", "泄秀顺局，去假存真", "滴天髓·假从（任氏注）"),
    "官杀": ("warn", "逆神当值——假从可发其身，仍防犯旺交战", "滴天髓·从象/假从"),
    "财": ("warn", "财生逆神，群劫相争之势", "滴天髓·从象（任氏注）"),
}


def _parse_ge(from_ge: str) -> tuple:
    """from_ge 字符串 → (格局类型, 化神五行或None)。如 '化气格（壬丁化木）' → ('化气', '木')"""
    if not from_ge:
        return None, None
    for k in ("从儿", "从财", "从杀", "从势", "专旺", "从强", "化气"):
        if from_ge.startswith(k):
            hua = None
            if k == "化气":
                m = re.search(r"化(.)）", from_ge)
                hua = m.group(1) if m else None
            return ("专旺" if k == "从强" else k), hua
    return None, None


def congge_xingyun(from_ge: str, quality: str, dm_wx: str, wx: str, F=None) -> dict | None:
    """
    查从格行运判定表。from_ge/quality 来自命局基线，wx 为流年五行，F 为扶抑喜用（化气判余/不足用）。
    返回 {role, verdict, reason, src}；非从格/化格或查不到 → None。
    """
    ge, hua = _parse_ge(from_ge)
    if not ge:
        return None
    jia = (quality == "假从")

    if ge == "化气":
        if not hua:
            return None
        hua_ym = SHENG[hua]                      # 泄化神者（化神所生）
        # 化神余/不足：基线喜用中含泄神或化神所克之神 → 有余（引擎化气取用同源）
        F = [f for f in (F or []) if f]
        abundant = (hua_ym in F) or (KE[hua] in F)
        if wx == hua:
            return {"role": "化神", "verdict": "good", "reason": "化神当值，从一而终",
                    "src": "滴天髓·化象"}
        if SHENG[wx] == hua:
            if abundant:
                return {"role": "生化神", "verdict": "warn", "reason": "化神有余，再生则太过",
                        "src": "滴天髓·化象（旺而有余）"}
            return {"role": "生化神", "verdict": "good", "reason": "化神不足，宜生助",
                    "src": "滴天髓·化象（衰而不足，宜生助）"}
        if KE[wx] == hua:
            return {"role": "克化神", "verdict": "bad", "reason": "克化神，破化",
                    "src": "滴天髓·化象（随其所向，论其喜忌）"}
        if wx == hua_ym:
            if abundant:
                return {"role": "泄化神", "verdict": "good", "reason": "化神有余，宜泄",
                        "src": "滴天髓·化象（旺而有余，宜泄）"}
            return {"role": "泄化神", "verdict": "warn", "reason": "化神不足，泄之则弱",
                    "src": "滴天髓·化象（衰而不足）"}
        # 化神所克（财）：有余取之为用，不足泄气
        return ({"role": "化神所克", "verdict": "good", "reason": "化神有余，取财为用",
                 "src": "滴天髓·化象（原注：土太旺，取水为财）"} if abundant else
                {"role": "化神所克", "verdict": "warn", "reason": "化神不足，再泄则弱",
                 "src": "滴天髓·化象"})

    if ge == "专旺":
        role = shishen_role(dm_wx, wx)
        v = CONGGE_TABLE_JIA_ZHUANWANG.get(role) if jia else CONGGE_TABLE["专旺"].get(role)
        return {"role": role, "verdict": v[0], "reason": v[1], "src": v[2]} if v else None

    if ge in ("从儿", "从财", "从杀", "从势"):
        role = shishen_role(dm_wx, wx)
        v = CONGGE_TABLE_JIA.get(role) if (jia and ge in ("从财", "从杀", "从势")) else CONGGE_TABLE[ge].get(role)
        return {"role": role, "verdict": v[0], "reason": v[1], "src": v[2]} if v else None

    return None


def liunian_overlay(liunian: dict, month_wx: str, baseline: dict, verdict: dict) -> tuple:
    """
    岁运层叠加：在主裁决（adjudicate）结果之上做引动检查。
    baseline: 命局基线 mingju（F/J/T0/from_ge/ge_quality/day_master_wx）。
    verdict: adjudicate 输出（会被复制后微调，绝不改 R、绝不设 block）。
    返回 (新verdict, liunian_info)。
    """
    v = dict(verdict)
    F = [f for f in (baseline.get("F") or []) if f]
    J = [j for j in (baseline.get("J") or []) if j]
    T0 = [t for t in (baseline.get("T0") or []) if t]
    from_ge = baseline.get("from_ge") or ""
    quality = baseline.get("ge_quality") or ""
    dm_wx = baseline.get("day_master_wx") or ""
    wx = liunian["wx"]

    strength, weight = shiwang_liunian(wx, month_wx)
    strong = weight >= STRONG_THRESHOLD
    notes = []
    info = {
        "ganzhi": liunian["ganzhi"], "wx": wx, "gan": liunian.get("gan", ""),
        "zhi": liunian.get("zhi", ""),
        "strength": strength, "weight": weight, "effective": strong,
        "effect": "none", "from_ge_table": None, "notes": notes,
    }

    if not strong:
        notes.append(f"流年{liunian['ganzhi']}（{wx}）处{strength}地，失令近乎不计，仅作背景")
        return v, info

    drag = boost = False

    # 1. 从格行运判定表（《滴天髓》从象/假从/从儿/化象）
    t = congge_xingyun(from_ge, quality, dm_wx, wx, F)
    if t:
        info["from_ge_table"] = t
        notes.append(f"岁运行{wx}（{t['role']}）：{t['reason']}（{t['src']}）")
        if t["verdict"] == "bad":
            drag = True
        elif t["verdict"] == "good":
            boost = True

    # 2. 忌神引动（直接当值 / 间接资敌）
    if wx in J:
        notes.append(f"流年{wx}当值，直接引动忌神")
        drag = True
    elif SHENG[wx] in J:
        notes.append(f"流年{wx}生忌神{SHENG[wx]}，间接资敌")
        drag = True

    # 3. 喜用引动
    if wx in F:
        notes.append(f"流年{wx}当值，直接生扶喜用")
        boost = True

    # 4. 调候引动（复用主裁决 2/2b 同一逻辑：调候转急时查流年与调候的顺逆）
    if T0 and tiao_active(T0, month_wx):
        g = grade_T(wx, T0[0])
        if g["net"] == "逆":
            notes.append(f"流年{wx}与转急调候{T0[0]}相克，逆调")
            drag = True
        else:
            notes.append(f"流年{wx}与转急调候{T0[0]}同调共振")
            boost = True

    # 汇效：凶引动优先；只升降一档，绝不设 block、绝不改 R
    if drag:
        info["effect"] = "drag"
        if v["level"] == "green":
            v["level"] = "yellow"
            v["gate"] = "limited"
            v["decision"] += "；流年引动凶，绿档降为限时放行"
    elif boost:
        info["effect"] = "boost"
        if v["level"] == "yellow" and v["gate"] == "limited":
            v["level"] = "green"
            v["gate"] = "pass"
            v["decision"] += "；流年生扶喜用，升格放行"
        elif v["level"] == "green":
            v["decision"] += "；流年生扶喜用，岁运加成"

    return v, info
