# -*- coding: utf-8 -*-
"""
确定性应期引擎（梅花 / 六爻）
============================
把"何时应"从 AI 自由发挥收归代码计算（确定性归代码，语言归 AI）。
干支历与八字择日模块（zeri.py）同源：lunar_python 逐日取干支，
旺相休囚死复用同一张月令称重表，保证八字/六爻/梅花三处口径一致。

书证（应期规则全部有出处，无一条自创）：
  梅花·应期三法（《梅花易数·体用总诀》）：
    其一，事成应于生体之卦卦气旺相之日，事败应于克体之卦卦气旺相之日；
    其二，以成卦总数定刻期远近——远事以年计、近事以月计、又近以日计；
    其三，占者动静调速——行则应速（取成卦数之半），坐则应迟（倍其数）。
  梅花·当值日（《梅花易数·先天卦定应期》）：应期日＝事体五行当值之日，
    "如乾、兑则应于庚、辛及申、酉金之日"——干支同权。
  六爻（《增删卜易·断应期总诀》）："静者逢值逢冲，动者逢合逢值"；
    月破者实破之日应；旬空者冲空之日应（空逢冲则实）；忌神受制逢冲。
"""
import math
from datetime import date as _date, datetime, timedelta

import lunar_python

from bazi_engine import GAN_WUXING
from liunian import ZHI_WUXING, shiwang_liunian
from wuxing_relation import SHENG, KE   # 与 remedy.py 同源，避免各处自建五行表

SRC_MH = ("梅花易数·体用总诀（应期三法）", "梅花易数·先天卦定应期")
SRC_LY = ("增删卜易·断应期总诀",)

# 八卦先天数（《梅花易数》起卦所用：乾一、兑二、离三、震四、巽五、坎六、艮七、坤八）
XIANTIAN_SHU = {"乾": 1, "兑": 2, "离": 3, "震": 4, "巽": 5, "坎": 6, "艮": 7, "坤": 8}

LIUHE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯",
         "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}
CHONG = {"子": "午", "午": "子", "丑": "未", "未": "丑", "寅": "申", "申": "寅",
         "卯": "酉", "酉": "卯", "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳"}


def _solar(d: _date):
    return lunar_python.Solar.fromYmdHms(d.year, d.month, d.day, 12, 0, 0)


def _day_pillar(d: _date) -> dict:
    """逐日干支（与 zeri._day_pillar 同一取法：日主以当天 12 点为准）"""
    lunar = _solar(d).getLunar()
    gz = lunar.getDayInGanZhi()
    return {"ganzhi": gz, "gan": gz[0], "zhi": gz[1],
            "gan_wx": GAN_WUXING[gz[0]], "zhi_wx": ZHI_WUXING[gz[1]]}


def _month_wx(d: _date) -> str:
    """月令五行（月支），供旺相休囚死称重。"""
    gz = _solar(d).getLunar().getMonthInGanZhi()
    return ZHI_WUXING[gz[1]]


def _matches(day: dict, wx: str) -> bool:
    """日辰天干或地支当值某五行（干支同权，据《先天卦定应期》）。"""
    return day["gan_wx"] == wx or day["zhi_wx"] == wx


def _strong(day: dict, month_wx: str) -> bool:
    """日辰主气（地支）是否卦气旺相（旺/相）。"""
    state, _w = shiwang_liunian(day["zhi_wx"], month_wx)
    return state in ("旺", "相")


def _d(d: _date) -> str:
    return d.isoformat()


# ============================================================
# 加权旺衰（**工程默认值，非书证**）
# ------------------------------------------------------------
# 这一段的比例与分值由产品方自行设定，任何典籍都没有给过权重或分数；
# 古书里甚至明确反对把生克分数化（《增删卜易》李我平曰：「七分八分，何以决疑？」）。
# 故一律标注为工程默认、未经案例校准，只用于"过与不过"的比较，
# 不得在断语里当作典籍依据引用。
#
# 数值本身**已入版本化配置**（weights.yaml · yingqi 段，R7，2026-09-23 迁入）：
# 改这些数请改 yaml 并升版本，决策日志里的 weights_version 才锚得住。
#   月支 0.80 ｜ 日支 0.15 ｜ 年支 0.025 ｜ 时支 0.025（年时两个合起来 5%）
#   判定基准：候选日的**地支五行**（日辰主气），不是"匹配到的那个五行"。
#   过门槛：总分 ≥ 0.45（取 0.45 是为了让「休」档能被日支救起：
#     休 0.32 + 日支同 0.15 + 年时 0.05 = 0.52 ≥ 0.45；取 0.55 则等价于「只看月令旺相」）
#
# 敏感度（2026-09-23 实测，14 个可复现真卦）：本组是全站最敏感的自定数字——
#   加权整体 −20% 或门槛 +20%，14 个卦的应期日期表全部改变。
# ============================================================
from weights import YINGQI as _YQ      # noqa: E402  （集中配置；缺段则回落内置默认）

WS_WEIGHTS = dict(_YQ.get("weights") or {"month": 0.80, "day": 0.15, "year": 0.025, "hour": 0.025})
WS_GATE = float(_YQ.get("gate", 0.45))
# 月支表：当令者旺、我生者相、生我者休、克我者囚、我克者死（《旺相休囚论》的五个态）
WS_MONTH = dict(_YQ.get("month_states") or {"旺": 1.0, "相": 0.7, "休": 0.4, "囚": 0.2, "死": 0.1})
# 其余三支表：同 / 该支生我 / 我泄于该支 / 该支克我 / 我克该支
WS_OTHER = dict(_YQ.get("other_states") or {"同": 1.0, "生": 0.7, "泄": 0.3, "被克": 0.1, "我克": 0.3})
# 页面小字：数字直接从上面取，避免文案与取值各写一套后互相脱节
_NUM = lambda v: ("%g" % v)                                            # noqa: E731
WS_NOTE = ("旺衰权重为工程默认值（月支 %s／日支 %s／年支 %s／时支 %s，门槛 %s），"
           "由产品方自行设定、未经案例校准；典籍未给权重，"
           "且《增删卜易》明言不以分数决疑，故此项不得当作典籍依据引用。"
           % (_NUM(WS_WEIGHTS["month"]), _NUM(WS_WEIGHTS["day"]),
              _NUM(WS_WEIGHTS["year"]), _NUM(WS_WEIGHTS["hour"]), _NUM(WS_GATE)))


def _month_state(target: str, month_zhi: str) -> str:
    """target 在月令的五个态（我 = 月令）。"""
    w = ZHI_WUXING.get(month_zhi, "")
    if not w or not target:
        return "休"
    if w == target:
        return "旺"
    if SHENG.get(w) == target:
        return "相"          # 月令生我者相
    if SHENG.get(target) == w:
        return "休"          # 生我者休
    if KE.get(w) == target:
        return "囚"          # 克我者囚
    return "死"              # 我克者死


def _other_state(target: str, zhi: str) -> str:
    w = ZHI_WUXING.get(zhi, "")
    if not w or not target:
        return "泄"
    if w == target:
        return "同"
    if SHENG.get(w) == target:
        return "生"
    if SHENG.get(target) == w:
        return "泄"
    if KE.get(w) == target:
        return "被克"
    return "我克"


def wangshuai_score(target: str, month_zhi: str, day_zhi: str,
                    year_zhi: str, hour_zhi: str) -> float:
    """四支加权后的旺衰分（0–1）。工程默认，非书证。"""
    m = WS_MONTH[_month_state(target, month_zhi)]
    d = WS_OTHER[_other_state(target, day_zhi)]
    y = WS_OTHER[_other_state(target, year_zhi)] if year_zhi else d
    h = WS_OTHER[_other_state(target, hour_zhi)] if hour_zhi else d
    return round(WS_WEIGHTS["month"] * m + WS_WEIGHTS["day"] * d
                 + WS_WEIGHTS["year"] * y + WS_WEIGHTS["hour"] * h, 4)


def _year_zhi(d: _date) -> str:
    return _solar(d).getLunar().getYearInGanZhi()[1]


def _month_zhi(d: _date) -> str:
    return _solar(d).getLunar().getMonthInGanZhi()[1]


# ============================================================
# 梅花：应期三法
# ============================================================
def meihua_yingqi(gua_data: dict, start: _date = None, final_R: str = "",
                  hour_zhi: str = "") -> dict:
    """确定性计算梅花应期。**两栏分开算、分开列，互不合并。**

    按卦栏（书证：《梅花易数·体用总诀》应期三法）
      可成：事成应于**生体之卦**卦气旺相之日
      避险：事败应于**克体之卦**卦气旺相之日
      并见：同一天既逢生体当值、又逢克体当值时，两边都不归，单列「吉凶并见」。
            处置方式与本站对「卦应一吉一凶」的一贯做法一致（《三要灵应篇》
            「卦应一吉一凶，事体半吉半凶……须详理」），不替用户择一。
      注：书里只说"生体之卦／克体之卦"，**没有**"处方五行当值"这一支。
      早先实现把处方五行也塞进可成条件，那一支不是书证，已移出本栏。

    按处方栏（工程口径，用于与页面「宜忌日期表」对齐）
      最终生效的处方五行（命局校验拦截后的改方）当值之日。不传 final_R 则本栏为空。
      为什么要分栏：应期（何时应）与处方／改方（补什么）本是两件事，此前混在一栏，
      于是同一页上「宜方水」与「火日可成」看着像互相打架。

    旺相门槛：四支加权（见 WS_NOTE），判定基准为**候选日的地支五行**。
    """
    ben = gua_data["ben_gua"]
    ti_wx = gua_data["tiyong"]["ti_wuxing"]
    r_wx = (gua_data.get("remedy") or {}).get("R") or ""
    sheng_ti = {"金": "土", "木": "水", "水": "金", "火": "木", "土": "火"}[ti_wx]
    ke_ti = {"金": "火", "木": "金", "水": "土", "火": "水", "土": "木"}[ti_wx]

    shang = XIANTIAN_SHU.get(ben["upper"]["name"], 0)
    xia = XIANTIAN_SHU.get(ben["lower"]["name"], 0)
    total = shang + xia
    kuai = max(1, math.ceil(total / 2))
    huan = total * 2

    start = start or datetime.now().date()
    scan_days = max(huan, 16)
    hz = hour_zhi or _solar(start).getLunar().getTimeInGanZhi()[1]

    keyi, xianri, jian, keyi_final, bihe = [], [], [], [], []
    for d, day, score in _scan(start, scan_days, hz):
        if score < WS_GATE:
            continue                     # 先按旺相过滤，再判归哪一栏
        why = "%s日：日支%s（%s）旺衰 %.3f ≥ %.2f" % (day["ganzhi"], day["zhi"],
                                                     day["zhi_wx"], score, WS_GATE)
        m_sheng, m_ke = _matches(day, sheng_ti), _matches(day, ke_ti)
        m_bi = _matches(day, ti_wx)      # 比和：体卦自身五行当值（与生体/克体互斥不成立，可并存）
        if m_sheng and m_ke:
            jian.append({"date": _d(d), "ganzhi": day["ganzhi"], "wx": "%s/%s" % (sheng_ti, ke_ti),
                         "basis": "卦", "kind": "吉凶并见",
                         "reason": (f"同日既逢生体之{sheng_ti}（吉）又逢克体之{ke_ti}（凶），"
                                    f"吉凶并见，须详理；{why}")})
        else:
            if m_sheng and not keyi_or_in(keyi, d):
                keyi.append({"date": _d(d), "ganzhi": day["ganzhi"], "wx": sheng_ti,
                             "basis": "卦", "kind": "可成",
                             "reason": f"生体之{sheng_ti}当值（事成应于生体之卦气旺相之日）；{why}"})
            if m_ke and len(xianri) < 6:
                xianri.append({"date": _d(d), "ganzhi": day["ganzhi"], "wx": ke_ti,
                               "basis": "卦", "kind": "避险",
                               "reason": f"克体之{ke_ti}当值（事败应于克体之卦气旺相之日）；{why}"})
        # 比和：体卦自身五行当值。书证：占卜克应之诀 L2826「但以生体及比和之年月为吉期，
        # 克体之年月为不吉之期也」——比和与生体同为吉期，故单列一组（2026-09-22 站长裁定加）。
        # 一天可同时是比和又是生体（天干地支各属一行），两组各记各的，不合并。
        if m_bi and score >= WS_GATE and not keyi_or_in(bihe, d):
            bihe.append({"date": _d(d), "ganzhi": day["ganzhi"], "wx": ti_wx,
                         "basis": "卦", "kind": "比和",
                         "reason": f"体卦之{ti_wx}当值（比和，与体卦同气；吉期）；{why}"})
        if final_R and _matches(day, final_R) and not keyi_or_in(keyi_final, d):
            keyi_final.append({"date": _d(d), "ganzhi": day["ganzhi"], "wx": final_R,
                               "basis": "处方", "kind": "按最终处方",
                               "reason": f"最终处方【{final_R}】当值；{why}"})

    return {
        "fa": "梅花应期三法（确定性计算）",
        "src": list(SRC_MH),
        "ti_wuxing": ti_wx, "sheng_ti_wuxing": sheng_ti, "ke_ti_wuxing": ke_ti,
        "cheng_gua_zong_shu": total,
        "shang_shu": shang, "xia_shu": xia,
        "kuai": kuai, "huan": huan,
        "window_text": f"近事约 {total} 日内；行则应速约 {kuai} 日、坐则应迟约 {huan} 日（动静调速）",
        "keyi": keyi[:6], "xianri": xianri[:6], "jian": jian[:6],      # 按卦栏（书证）
        "bihe": bihe[:6],                                              # 按卦栏（比和：体卦自身当值）
        "keyi_final": keyi_final[:6],                                  # 按处方栏（工程口径）
        "R": r_wx, "final_R": final_R, "hour_zhi": hz, "start": _d(start),
        "weight_note": WS_NOTE,
        "note": ("「按卦」栏据《体用总诀》应期三法（生体之卦／克体之卦）；"
                 "「按最终处方」栏为工程口径，用于与宜忌日期表对齐。"
                 "两栏互不合并；同一天若生体克体兼逢，单列「吉凶并见」，不替你择一。"),
    }


def _scan(start: _date, n_days: int, hour_zhi: str):
    """逐日算 (日期, 日柱, 旺衰分)。时支全天固定（取起卦时辰），月支/年支/日支取候选日自己。"""
    for i in range(n_days):
        d = start + timedelta(days=i)
        day = _day_pillar(d)
        score = wangshuai_score(day["zhi_wx"], _month_zhi(d), day["zhi"],
                                _year_zhi(d), hour_zhi)
        yield d, day, score


def meihua_yingqi_column(wx: str, start: _date = None, hour_zhi: str = "",
                         n_days: int = 16) -> list:
    """只算「某一五行当值且旺相」的日子——供「按最终处方」栏用。

    这里不碰生体/克体（那属按卦栏），所以可以在命局校验拿到 final_R 之后再算，
    把改方后的处方五行与页面上的宜忌日期表对齐。
    """
    if not wx:
        return []
    start = start or datetime.now().date()
    hz = hour_zhi or _solar(start).getLunar().getTimeInGanZhi()[1]
    out = []
    for d, day, score in _scan(start, n_days, hz):
        if score >= WS_GATE and _matches(day, wx) and not keyi_or_in(out, d):
            out.append({"date": _d(d), "ganzhi": day["ganzhi"], "wx": wx,
                        "basis": "处方", "kind": "按最终处方",
                        "reason": ("最终处方【%s】当值；%s日：日支%s（%s）旺衰 %.3f ≥ %.2f"
                                   % (wx, day["ganzhi"], day["zhi"], day["zhi_wx"],
                                      score, WS_GATE))})
    return out[:6]


def keyi_or_in(lst: list, d: _date) -> bool:
    """同一天只进一条可成记录（生体与处方同日不重复列）。"""
    return any(x["date"] == _d(d) for x in lst)


# ============================================================
# 六爻：用神值日 / 逢合 / 冲空实破 / 忌神受冲
# ============================================================
def _line_of(gua_data: dict, pos: int) -> dict:
    lines = gua_data.get("lines") or []
    if 1 <= int(pos) <= len(lines):
        return lines[int(pos) - 1]
    return {}


def liuyao_yingqi(gua_data: dict, start: _date = None, n_days: int = 30) -> dict:
    """
    确定性计算六爻应期（《增删卜易·断应期总诀》）：
      静者逢值逢冲，动者逢合逢值；
      旬空者冲空之日应（空逢冲则实）；月破者实破之日应；忌神受制逢冲。
    用神爻与忌神信息取自 liuyao_remedy 的确定性结果（details）。
    """
    r = gua_data.get("remedy") or {}
    yj = (r.get("details") or {}).get("用神爻") or {}
    js = (r.get("details") or {}).get("忌神") or {}
    yong_gz = str(yj.get("干支") or "")
    yong_zhi = yong_gz[-1] if yong_gz else ""
    moving = bool(yj.get("发动"))

    start = start or datetime.now().date()
    zhiri, fenghe, chongri, jishen_chong = [], [], [], []
    for i in range(n_days):
        d = start + timedelta(days=i)
        day = _day_pillar(d)
        if yong_zhi:
            if day["zhi"] == yong_zhi:
                zhiri.append({"date": _d(d), "ganzhi": day["ganzhi"], "reason": f"用神{yong_zhi}值日"})
            if day["zhi"] == LIUHE.get(yong_zhi):
                fenghe.append({"date": _d(d), "ganzhi": day["ganzhi"], "reason": f"{day['zhi']}与用神{yong_zhi}作合"})
            if day["zhi"] == CHONG.get(yong_zhi):
                chongri.append({"date": _d(d), "ganzhi": day["ganzhi"], "reason": f"{day['zhi']}冲用神{yong_zhi}"})
        # 忌神受制逢冲：卦中忌神六亲之爻被日辰冲
        js_liuqin = js.get("六亲")
        if js_liuqin and len(jishen_chong) < 6:
            for l in gua_data.get("lines") or []:
                if l.get("liuqin") == js_liuqin and day["zhi"] == CHONG.get(l.get("zhi")):
                    jishen_chong.append({"date": _d(d), "ganzhi": day["ganzhi"],
                                         "reason": f"{day['zhi']}冲忌神{l['liuqin']}{l['gan']}{l['zhi']}（忌神受制）"})
                    break

    # 旬空 / 月破修饰（用神爻本身的状态）
    yong_line = _line_of(gua_data, yj.get("position", 0)) if yj else {}
    xunkong = bool(yong_line.get("xunkong"))
    yuepo = bool(yong_line.get("yuepo"))
    chongkong = chongri if (xunkong and yong_zhi) else []
    shipo = zhiri if (yuepo and yong_zhi) else []

    rule = "动者逢合逢值" if moving else "静者逢值逢冲"
    return {
        "fa": "六爻应期（确定性计算）",
        "src": list(SRC_LY),
        "yongshen": {"liuqin": yj.get("六亲"), "ganzhi": yong_gz,
                     "wuxing": yj.get("五行"), "moving": moving},
        "rule": rule,
        "zhiri": zhiri[:4], "fenghe": fenghe[:4], "chongri": chongri[:4],
        "xunkong": xunkong, "yuepo": yuepo,
        "chongkong": chongkong[:4], "shipo": shipo[:4],
        "jishen_chong": jishen_chong[:4],
        "note": ("用神旬空：空逢冲则实，应于冲空之日；用神月破：应于实破之日。"
                 if (xunkong or yuepo) else
                 "日期为代码算得的应期候选，结合卦理取舍归 AI，不得列出未计算的日期。"),
    }
