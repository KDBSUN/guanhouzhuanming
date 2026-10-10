"""
四柱八字排盘引擎
依据传统子平八字（四柱：年柱/月柱/日柱/时柱）方法，由公历出生时间排盘。

排盘核心由 MIT 许可的 lunar-python（6tail）库精确计算：
- 干支历换算（以节气定月、以立春定年）
- 四柱干支 / 五行 / 纳音 / 十神 / 藏干 / 空亡 / 十二长生
- 大运（阳男阴女顺行、阴男阳女逆行）、流年
- 命宫 / 胎元 / 身宫 / 胎息

神煞（据《三命通会》卷三"论神煞"各节、《渊海子平》）：
- 年支/日支三合起：驿马、将星、华盖、咸池、劫煞、亡神、灾煞、孤辰、寡宿
- 日干起：天乙贵人、文昌贵人、禄神、羊刃、金舆、红艳煞
- 月支起：天德贵人、月德贵人、天喜
- 日柱定：魁罡、十恶大败、孤鸾煞、阴差阳错
- 三奇：天上三奇甲戊庚、地下三奇乙丙丁、人中三奇壬癸辛（年、月、日干顺排）

说明：四柱八字为流传千年的传统公共知识，本引擎由开源库与古籍规则独立实现，
不依赖、不提取任何商业 App 的代码或数据。

另支持：
- calendar="lunar"：以农历（可能闰月）输入 → 转公历后排盘
- true_solar=True：真太阳时校正（东经 120° 经度差修正 + 均时差，NOAA 太阳位置公式）
"""
import math
from datetime import date, datetime, timedelta
from typing import Optional

from lunar_python import Lunar, LunarMonth, LunarYear, Solar

# 八字取用裁决（H5）的数值门槛（书证与层级见 docs/调候与改方书证登记.md；
# 本模块原不依赖 weights，此导入仅取 xiji 一段——weights 无项目侧依赖，无环）
from weights import XIJI as _XIJI

# ============================================================
# 基础数据（传统公共知识）
# ============================================================
GAN_WUXING = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
              "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
ZHI_WUXING = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
              "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
GAN_YINYANG = {"甲": "阳", "丙": "阳", "戊": "阳", "庚": "阳", "壬": "阳",
               "乙": "阴", "丁": "阴", "己": "阴", "辛": "阴", "癸": "阴"}

# 五行生克（我生 / 我克）
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

# 十神（以日干为"我"）
def gan_shishen(day_gan: str, target_gan: str) -> str:
    """某天干相对日主的十神"""
    if target_gan == day_gan:
        return "日主"
    same_polarity = GAN_YINYANG[day_gan] == GAN_YINYANG[target_gan]
    dw = GAN_WUXING[day_gan]
    tw = GAN_WUXING[target_gan]
    if tw == dw:                                   # 同我
        return "比肩" if same_polarity else "劫财"
    if SHENG[dw] == tw:                            # 我生
        return "食神" if same_polarity else "伤官"
    if KE[dw] == tw:                               # 我克
        return "偏财" if same_polarity else "正财"
    if SHENG[tw] == dw:                            # 生我
        return "偏印" if same_polarity else "正印"
    return "七杀" if same_polarity else "正官"      # 克我


def gan_shishen_yun(day_gan: str, target_gan: str) -> str:
    """十神通例（日干见日干＝比肩）——大运/流年用。
    「日主」称谓仅四柱日干位使用（gan_shishen 的 target==day 分支）。"""
    return "比肩" if target_gan == day_gan else gan_shishen(day_gan, target_gan)


WUXING_ORDER = ["金", "木", "水", "火", "土"]
PILLAR_LABELS = ["年柱", "月柱", "日柱", "时柱"]

# ============================================================
# 神煞表（据《三命通会》论神煞、《渊海子平》）
# ============================================================
# 地支 → 三合局
GROUP_OF = {
    "申": "申子辰", "子": "申子辰", "辰": "申子辰",
    "寅": "寅午戌", "午": "寅午戌", "戌": "寅午戌",
    "巳": "巳酉丑", "酉": "巳酉丑", "丑": "巳酉丑",
    "亥": "亥卯未", "卯": "亥卯未", "未": "亥卯未",
}
# 三合局 → 各神煞所临之支（驿马/将星/华盖/咸池/劫煞/亡神/灾煞）
SANHE_RULE = {
    "申子辰": {"驿马": "寅", "将星": "子", "华盖": "辰", "咸池": "酉",
                "劫煞": "巳", "亡神": "亥", "灾煞": "午"},
    "寅午戌": {"驿马": "申", "将星": "午", "华盖": "戌", "咸池": "卯",
                "劫煞": "亥", "亡神": "巳", "灾煞": "子"},
    "巳酉丑": {"驿马": "亥", "将星": "酉", "华盖": "丑", "咸池": "午",
                "劫煞": "寅", "亡神": "申", "灾煞": "卯"},
    "亥卯未": {"驿马": "巳", "将星": "卯", "华盖": "未", "咸池": "子",
                "劫煞": "申", "亡神": "寅", "灾煞": "酉"},
}

# 以日干查地支（《三命通会》通行法："甲戊庚牛羊，乙己鼠猴乡，丙丁猪鸡位，壬癸兔蛇藏，六辛逢马虎"）
TIANYI = {"甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"),
          "乙": ("子", "申"), "己": ("子", "申"),
          "丙": ("酉", "亥"), "丁": ("酉", "亥"),
          "壬": ("卯", "巳"), "癸": ("卯", "巳"),
          "辛": ("寅", "午")}
# 文昌贵人（甲巳 乙亥 丙戌 丁辰 戊申 己午 庚寅 辛未 壬卯 癸丑）
WENCHANG = {"甲": "巳", "乙": "亥", "丙": "戌", "丁": "辰", "戊": "申",
            "己": "午", "庚": "寅", "辛": "未", "壬": "卯", "癸": "丑"}
# 十干禄（甲禄寅，乙禄卯，丙戊禄巳，丁己禄午，庚禄申，辛禄酉，壬禄亥，癸禄子）
LU = {"甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳",
      "己": "午", "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}
# 羊刃（禄前一辰：卯甲 辰乙 午丙 未丁 午戊 未己 酉庚 戌辛 子壬 丑癸）
YANGREN = {"甲": "卯", "乙": "辰", "丙": "午", "丁": "未", "戊": "午",
           "己": "未", "庚": "酉", "辛": "戌", "壬": "子", "癸": "丑"}
# 金舆（禄前二辰：甲辰 乙巳 丙戊未 丁己申 庚戌 辛亥 壬丑 癸寅）
JINYU = {"甲": "辰", "乙": "巳", "丙": "未", "丁": "申", "戊": "未",
         "己": "申", "庚": "戌", "辛": "亥", "壬": "丑", "癸": "寅"}
# 红艳煞（甲乙午 丙寅 丁未 戊子 己辰 庚戌 辛酉 壬巳 癸申）
HONGYAN = {"甲": "午", "乙": "午", "丙": "寅", "丁": "未", "戊": "子",
           "己": "辰", "庚": "戌", "辛": "酉", "壬": "巳", "癸": "申"}

# 天德贵人（以月支查："正丁二坤中，三壬四辛同，五乾六甲上，七癸八艮逢，九丙十居乙，子巽丑庚中"）
TIANDE_GAN = {"寅": "丁", "辰": "壬", "巳": "辛", "未": "甲", "申": "癸",
              "戌": "丙", "亥": "乙", "丑": "庚"}      # 天德在天干之月
TIANDE_ZHI = {"卯": "申", "午": "亥", "酉": "寅", "子": "巳"}  # 天德在地支（坤/乾/艮/巽）之月
# 月德贵人（三合局之旺干：寅午戌月丙，亥卯未月甲，申子辰月壬，巳酉丑月庚）
YUEDE_GAN = {"寅": "丙", "午": "丙", "戌": "丙",
             "亥": "甲", "卯": "甲", "未": "甲",
             "申": "壬", "子": "壬", "辰": "壬",
             "巳": "庚", "酉": "庚", "丑": "庚"}
# 孤辰寡宿（以年支查：亥子丑→孤寅寡戌；寅卯辰→孤巳寡丑；巳午未→孤申寡辰；申酉戌→孤亥寡未）
GUCHEN = {"亥": "寅", "子": "寅", "丑": "寅", "寅": "巳", "卯": "巳", "辰": "巳",
          "巳": "申", "午": "申", "未": "申", "申": "亥", "酉": "亥", "戌": "亥"}
GUASU = {"亥": "戌", "子": "戌", "丑": "戌", "寅": "丑", "卯": "丑", "辰": "丑",
         "巳": "辰", "午": "辰", "未": "辰", "申": "未", "酉": "未", "戌": "未"}
# 天喜（以月支定季：春戌、夏丑、秋辰、冬未，日支见者即是）
TIANXI_BY_MONTH = {"寅": "戌", "卯": "戌", "辰": "戌",
                   "巳": "丑", "午": "丑", "未": "丑",
                   "申": "辰", "酉": "辰", "戌": "辰",
                   "亥": "未", "子": "未", "丑": "未"}

# 日柱定神煞
KUIGANG = {"庚辰", "庚戌", "壬辰", "戊戌"}                     # 魁罡四日
SHIWU_DAIBAI = {"甲辰", "乙巳", "壬申", "丙申", "丁亥", "庚辰", "戊戌", "癸亥", "辛巳", "己丑"}  # 十恶大败
GULUAN = {"乙巳", "丁巳", "辛亥", "戊申", "甲寅", "丙午", "戊午", "壬子"}                       # 孤鸾煞
YINCHAYANGCUO = {"丙子", "丁丑", "戊寅", "辛卯", "壬辰", "癸巳", "丙午", "丁未", "戊申", "辛酉", "壬戌", "癸亥"}  # 阴差阳错
# 三奇（年、月、日干顺排）
SANQI = [("甲", "戊", "庚", "天上三奇"), ("乙", "丙", "丁", "地下三奇"), ("壬", "癸", "辛", "人中三奇")]

# ============================================================
# 十二长生（星运/自坐）——《渊海子平》"阳生阴死，阳死阴生，循环逆顺"
# 阳干顺行、阴干逆行；长生起：甲亥 乙午 丙戊寅 丁己酉 庚巳 辛子 壬申 癸卯
# ============================================================
ZHI_IDX = {"子": 0, "丑": 1, "寅": 2, "卯": 3, "辰": 4, "巳": 5, "午": 6,
           "未": 7, "申": 8, "酉": 9, "戌": 10, "亥": 11}
STAGES = ["长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养"]
CHANGSHENG_IDX = {"甲": 11, "乙": 6, "丙": 2, "丁": 9, "戊": 2, "己": 9,
                  "庚": 5, "辛": 0, "壬": 8, "癸": 3}
YANG_GAN = {"甲", "丙", "戊", "庚", "壬"}


def self_sit(gan: str, zhi: str) -> str:
    """自坐：该柱天干坐本柱地支之十二长生"""
    cs = CHANGSHENG_IDX[gan]
    zi = ZHI_IDX[zhi]
    off = (zi - cs) % 12 if gan in YANG_GAN else (cs - zi) % 12
    return STAGES[off]


def month_geju(day_gan: str, month_zhi: str, month_canggan: list[dict]) -> dict:
    """月令取格（《子平真诠》简化）：月支为日主禄 → 建禄格；为阳刃 → 阳刃格；
    否则按月支本气藏干之十神取格"""
    basis = "月令取格（子平真诠）"
    if month_zhi == LU[day_gan]:
        return {"name": "建禄格", "basis": f"月支为日主临官禄地（{basis}）"}
    if month_zhi == YANGREN[day_gan]:
        return {"name": "阳刃格", "basis": f"月支为日主羊刃（{basis}）"}
    if month_canggan:
        shishen = month_canggan[0]["shishen"]
        if shishen in ("正官", "七杀", "正财", "偏财", "正印", "偏印", "食神", "伤官"):
            return {"name": f"{shishen}格",
                    "basis": f"月支本气 {month_canggan[0]['gan']} 为{shishen}（{basis}）"}
    return {"name": "普通格", "basis": basis}


# ============================================================
# 神煞计算
# ============================================================
def _pillar_shensha(bazi: list[dict], i: int, day_gan: str, year_zhi: str, day_zhi: str) -> list[str]:
    """
    单柱神煞。bazi 为四柱 [{gan,zhi,...}]。
    - 日干起：天乙、文昌、禄、羊刃、金舆、红艳（查地支）
    - 年支/日支三合起：驿马、将星、华盖、咸池、劫煞、亡神（查地支）
    - 年支起（不含年柱）：灾煞、孤辰、寡宿
    - 月支起：天德、月德（查天干或地支）
    """
    gan, zhi = bazi[i]["gan"], bazi[i]["zhi"]
    month_zhi = bazi[1]["zhi"]
    names = []

    # —— 日干起 ——
    if zhi in TIANYI[day_gan]:
        names.append("天乙贵人")
    if zhi == WENCHANG[day_gan]:
        names.append("文昌贵人")
    if zhi == LU[day_gan]:
        names.append("禄神")
    if zhi == YANGREN[day_gan]:
        names.append("羊刃")
    if zhi == JINYU[day_gan]:
        names.append("金舆")
    if zhi == HONGYAN[day_gan]:
        names.append("红艳")

    # —— 年支 / 日支 三合起 ——
    for rule_zhi, inclusive in ((year_zhi, True), (day_zhi, True)):
        rule = SANHE_RULE[GROUP_OF[rule_zhi]]
        for key in ("驿马", "将星", "华盖", "咸池", "劫煞", "亡神"):
            if zhi == rule[key] and key not in names:
                names.append(key)

    # —— 年支起（灾煞/孤辰/寡宿，依《三命通会》"以年支为主，其他三柱见者即是"） ——
    if i != 0:
        year_rule = SANHE_RULE[GROUP_OF[year_zhi]]
        if zhi == year_rule["灾煞"]:
            names.append("灾煞")
        if zhi == GUCHEN[year_zhi]:
            names.append("孤辰")
        if zhi == GUASU[year_zhi]:
            names.append("寡宿")

    # —— 月支起：天德、月德 ——
    if TIANDE_GAN.get(month_zhi) == gan:
        names.append("天德贵人")
    if TIANDE_ZHI.get(month_zhi) == zhi:
        names.append("天德贵人")
    if YUEDE_GAN.get(month_zhi) == gan:
        names.append("月德贵人")

    return names


def _chart_shensha(bazi: list[dict]) -> list[str]:
    """命局整体神煞（日柱定 + 三奇 + 天喜）"""
    names = []
    day_gz = bazi[2]["ganzhi"]
    if day_gz in KUIGANG:
        names.append("魁罡")
    if day_gz in SHIWU_DAIBAI:
        names.append("十恶大败")
    if day_gz in GULUAN:
        names.append("孤鸾煞")
    if day_gz in YINCHAYANGCUO:
        names.append("阴差阳错")
    # 三奇：年、月、日干顺排
    gan_triple = (bazi[0]["gan"], bazi[1]["gan"], bazi[2]["gan"])
    for a, b, c, label in SANQI:
        if gan_triple == (a, b, c):
            names.append(label)
    # 天喜：以月支定季，日支见者即是
    if bazi[2]["zhi"] == TIANXI_BY_MONTH[bazi[1]["zhi"]]:
        names.append("天喜")
    return names


def _zhi_shensha_names(zhi: str, year_zhi: str, day_zhi: str) -> list[str]:
    """大运/流年地支的神煞（年支、日支三合起，六项）"""
    names = []
    for rule_zhi in (year_zhi, day_zhi):
        rule = SANHE_RULE[GROUP_OF[rule_zhi]]
        for key in ("驿马", "将星", "华盖", "咸池", "劫煞", "亡神"):
            if zhi == rule[key] and key not in names:
                names.append(key)
    return names


# ============================================================
# 排盘
# ============================================================
def _build_pillar(ec, getter_prefix: str, label: str, day_gan: str, kong_zhi: set) -> dict:
    """由 EightChar 对象构造单柱"""
    gz = getattr(ec, f"get{getter_prefix}")()          # 如 "庚午"
    gan, zhi = gz[0], gz[1]
    hide = getattr(ec, f"get{getter_prefix}HideGan")()          # 藏干列表
    shishen_zhi = getattr(ec, f"get{getter_prefix}ShiShenZhi")()  # 藏干对应十神
    shishen_gan = getattr(ec, f"get{getter_prefix}ShiShenGan")()  # 天干十神
    nayin = getattr(ec, f"get{getter_prefix}NaYin")()
    dishis = getattr(ec, f"get{getter_prefix}DiShi")()            # 十二长生（星运）
    xunkong = getattr(ec, f"get{getter_prefix}XunKong")()         # 本柱自身旬空

    canggan = []
    for i, hg in enumerate(hide):
        canggan.append({
            "gan": hg,
            "wuxing": GAN_WUXING[hg],
            "shishen": shishen_zhi[i] if i < len(shishen_zhi) else "",
        })

    return {
        "label": label,
        "ganzhi": gz,
        "gan": gan,
        "zhi": zhi,
        "gan_wuxing": GAN_WUXING[gan],
        "zhi_wuxing": ZHI_WUXING[zhi],
        "nayin": nayin,
        "shishen_gan": shishen_gan,
        "canggan": canggan,
        "dishis": dishis,                 # 星运：日主对本柱地支之十二长生
        "self_sit": self_sit(gan, zhi),   # 自坐：本柱天干坐本柱地支之十二长生
        "xunkong": xunkong,               # 本柱自身旬空（如 "午未"）
        "is_kong": zhi in kong_zhi,       # 是否落日柱旬空
    }


# ============================================================
# 农历 / 真太阳时 辅助
# ============================================================
def lunar_meta(year: int) -> dict:
    """农历年信息：闰月序号（0=无闰）、各月天数、闰月天数"""
    ly = LunarYear.fromYear(year)
    leap = ly.getLeapMonth()
    month_days = [LunarMonth.fromYm(year, m).getDayCount() for m in range(1, 13)]
    leap_days = LunarMonth.fromYm(year, -leap).getDayCount() if leap else 0
    return {"year": year, "leap_month": leap, "month_days": month_days, "leap_month_days": leap_days}


def lunar_to_solar(year: int, month: int, day: int, leap_month: bool = False,
                   hour: int = 0, minute: int = 0) -> dict:
    """农历 → 公历（闰月以负月传入）"""
    lunar = Lunar.fromYmdHms(year, -month if leap_month else month, day, hour, minute, 0)
    solar = lunar.getSolar()
    return {
        "solar": f"{solar.getYear()}年{solar.getMonth()}月{solar.getDay()}日 "
                 f"{solar.getHour():02d}:{solar.getMinute():02d}",
        "lunar": f"农历{lunar.getYearInChinese()}年{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}",
    }


def _eq_of_time(year: int, month: int, day: int) -> float:
    """均时差（分钟）。NOAA 太阳位置公式近似：B=(n−1)×360/365 度"""
    n = (date(year, month, day) - date(year, 1, 1)).days + 1
    B = math.radians((n - 1) * 360 / 365)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(B)
        - 0.032077 * math.sin(B)
        - 0.014615 * math.cos(2 * B)
        - 0.04089 * math.sin(2 * B)
    )


def _apply_true_solar(year: int, month: int, day: int, hour: int, minute: int,
                      longitude: float) -> dict:
    """真太阳时 = 钟表时间 + (经度−120)×4 分 + 均时差（分钟，可跨日）"""
    lon_corr = (longitude - 120.0) * 4
    eot = _eq_of_time(year, month, day)
    total = hour * 60 + minute + lon_corr + eot
    dt = datetime(year, month, day, 0, 0) + timedelta(minutes=total)
    return {
        "year": dt.year,
        "month": dt.month,
        "day": dt.day,
        "hour": dt.hour,
        "minute": dt.minute,
        "lon_correction": round(lon_corr, 2),
        "eot": round(eot, 2),
    }


# ============================================================
# 夏令时（夏时制）还原
# 我国 1986–1991 年实行夏令时（IANA tzdb Asia/Shanghai 的 PRC 规则）：
#   1986 年：5月4日 02:00 起
#   1987–1991 年：每年4月11日后首个周日 02:00 起
#   1986–1991 年：每年9月11日后首个周日 02:00（夏令时钟表）止，拨回 1 小时
# 处理顺序（先还原夏令时 → 再经度校正 → 最后均时差）
# ============================================================
def _first_sunday_on_or_after(year: int, month: int, day0: int) -> date:
    """month 月 day0 日当日起、之后的第一个星期日（day0∈[11,17] 时月内落定）"""
    d = date(year, month, day0)
    d += timedelta(days=(6 - d.weekday()) % 7)
    return d


def china_dst_window_clock(year: int):
    """返回该年夏令时区间（夏令时钟表时间），无夏令时的年份返回 None。
    返回 (start_clock, end_clock)：start 当天 03:00（=标准02:00拨快后）起，
    end 当天 02:00（夏令时钟表）止。"""
    if not 1986 <= year <= 1991:
        return None
    if year == 1986:
        start = datetime(year, 5, 4, 3, 0)          # 1986 特例：5月4日 02:00 标准时起
    else:
        start = datetime(_first_sunday_on_or_after(year, 4, 11).year,
                         _first_sunday_on_or_after(year, 4, 11).month,
                         _first_sunday_on_or_after(year, 4, 11).day, 3, 0)
    end_day = _first_sunday_on_or_after(year, 9, 11)
    end = datetime(end_day.year, end_day.month, end_day.day, 2, 0)
    return start, end


def _restore_dst(year: int, month: int, day: int, hour: int, minute: int) -> dict:
    """夏令时还原：出生钟表时间若落在夏令时区间，减回 1 小时得法定标准时间"""
    win = china_dst_window_clock(year)
    recorded = f"{year}年{month}月{day}日 {hour:02d}:{minute:02d}"
    if win is None:
        return {"applied": False, "recorded": recorded,
                "note": f"{year}年未实行夏令时（仅 1986–1991 年实行）"}
    start_clock, end_clock = win
    t = datetime(year, month, day, hour, minute)
    if start_clock <= t < end_clock:
        restored = t - timedelta(hours=1)
        return {
            "applied": True,
            "recorded": recorded,
            "restored": f"{restored.year}年{restored.month}月{restored.day}日 "
                        f"{restored.hour:02d}:{restored.minute:02d}",
            "restored_dt": {"year": restored.year, "month": restored.month, "day": restored.day,
                            "hour": restored.hour, "minute": restored.minute},
            "window": (f"{start_clock.year}-{start_clock.month:02d}-{start_clock.day:02d} "
                       f"{start_clock.hour:02d}:00 ~ {end_clock.year}-{end_clock.month:02d}-"
                       f"{end_clock.day:02d} {end_clock.hour:02d}:00（夏令时钟表）"),
            "note": "1986–1991 夏令时：钟表时间已拨快 1 小时，已还原为法定标准时间",
        }
    return {"applied": False, "recorded": recorded,
            "note": "出生时刻不在当年夏令时区间内（1986–1991 每年4月中旬至9月中旬），无需还原"}


def build_bazi_paipan(year: int, month: int, day: int, hour: int = 0,
                      minute: int = 0, gender: int = 1, sect: int = 1,
                      calendar: str = "solar", leap_month: bool = False,
                      true_solar: bool = False, longitude: float = 120.0,
                      dst: bool = False) -> dict:
    """
    公历出生时间 → 完整八字排盘
    gender:      1=男, 0=女（lunar-python 约定）
    sect:        流派（早晚子时差异），默认 1
    calendar:    "solar" 公历输入 / "lunar" 农历输入（闰月用 leap_month=True）
    dst:         出生钟表时间含夏令时（1986–1991）→ 先还原标准时间
    true_solar:  开启真太阳时校正（按 longitude 东经，120° 无校正）
    校时顺序：还原夏令时 → 经度校正 → 均时差
    """
    input_info = {"calendar": calendar, "longitude": longitude}

    if calendar == "lunar":
        lunar_in = Lunar.fromYmdHms(year, -month if leap_month else month, day, hour, minute, 0)
        solar_in = lunar_in.getSolar()
        year, month, day = solar_in.getYear(), solar_in.getMonth(), solar_in.getDay()
        input_info["raw"] = (f"农历{lunar_in.getYearInChinese()}年"
                             f"{lunar_in.getMonthInChinese()}月{lunar_in.getDayInChinese()} "
                             f"{hour:02d}:{minute:02d}")
        input_info["leap_month"] = leap_month
    else:
        input_info["raw"] = f"{year}年{month}月{day}日 {hour:02d}:{minute:02d}"

    # —— 第 1 层：夏令时还原 ——
    dst_info = None
    if dst:
        dst_info = _restore_dst(year, month, day, hour, minute)
        if dst_info["applied"]:
            r = dst_info["restored_dt"]
            year, month, day, hour, minute = r["year"], r["month"], r["day"], r["hour"], r["minute"]

    # —— 第 2、3 层：真太阳时校正 ——
    true_solar_info = None
    if true_solar:
        ts = _apply_true_solar(year, month, day, hour, minute, longitude)
        year, month, day, hour, minute = ts["year"], ts["month"], ts["day"], ts["hour"], ts["minute"]
        true_solar_info = {
            "solar_used": f"{year}年{month}月{day}日 {hour:02d}:{minute:02d}",
            "original": dst_info["restored"] if (dst_info and dst_info["applied"])
                        else input_info["raw"],
            "longitude": longitude,
            "lon_correction": ts["lon_correction"],
            "eot": ts["eot"],
        }

    solar = Solar.fromYmdHms(year, month, day, hour, minute, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()

    day_gan = ec.getDayGan()
    # 空亡：以日柱旬空为准（子平通行取法），应用于四柱与各柱地支
    kong = ec.getDayXunKong() or ""
    kong_zhi = set(kong) if kong else set()

    pillars = [
        _build_pillar(ec, "Year", PILLAR_LABELS[0], day_gan, kong_zhi),
        _build_pillar(ec, "Month", PILLAR_LABELS[1], day_gan, kong_zhi),
        _build_pillar(ec, "Day", PILLAR_LABELS[2], day_gan, kong_zhi),
        _build_pillar(ec, "Time", PILLAR_LABELS[3], day_gan, kong_zhi),
    ]

    # 神煞
    year_zhi, day_zhi = pillars[0]["zhi"], pillars[2]["zhi"]
    for i, p in enumerate(pillars):
        p["shensha"] = _pillar_shensha(pillars, i, day_gan, year_zhi, day_zhi)
    chart_shensha = _chart_shensha(pillars)

    # 质地层三标签（第一批：阴阳/燥湿/寒暖，滴天髓·论天干/寒暖/燥湿）——排盘输出层，每个干支挂三标签
    from wuxing_quality import stem_texture, branch_texture
    for p in pillars:
        p["gan_texture"] = stem_texture(p["gan"])
        p["zhi_texture"] = branch_texture(p["zhi"])

    # 格局（《子平真诠》月令取格简化）
    geju = month_geju(day_gan, pillars[1]["zhi"], pillars[1]["canggan"])

    # 五行统计（四柱八字八字的五行分布）
    wuxing_tally = {w: 0 for w in WUXING_ORDER}
    for p in pillars:
        wuxing_tally[p["gan_wuxing"]] += 1
        wuxing_tally[p["zhi_wuxing"]] += 1

    # 大运（120 年 = 12 步真大运 × 10 年；lunar-python 的 getDaYun(n) 里
    #   第 0 步是起运前占位（空干支），所以 12 步真大运要传 13——站长要求 2026-10）
    yun = ec.getYun(gender, sect)
    da_yun = yun.getDaYun(13)
    steps = []
    for dy in da_yun:
        gz = dy.getGanZhi()
        steps.append({
            "index": dy.getIndex(),
            "ganzhi": gz,
            "gan": gz[0] if gz else "",
            "zhi": gz[1] if gz else "",
            "gan_shishen": gan_shishen_yun(day_gan, gz[0]) if gz else "",
            "shensha": _zhi_shensha_names(gz[1], year_zhi, day_zhi) if gz else [],
            "start_age": dy.getStartAge(),
            "end_age": dy.getEndAge(),
            "start_year": dy.getStartYear(),
            "end_year": dy.getEndYear(),
            "liunian": _build_liunian(dy, day_gan, year_zhi, day_zhi),
        })

    start_solar = yun.getStartSolar()

    return {
        "method": "bazi",
        "solar": f"{year}年{month}月{day}日 {hour:02d}:{minute:02d}",
        "lunar": lunar.toString(),
        "shengxiao": lunar.getYearShengXiao(),
        "gender": "男" if gender == 1 else "女",
        "gender_code": gender,
        "input": input_info,
        "true_solar": true_solar_info,
        "dst": dst_info,
        "day_master": {
            "gan": day_gan,
            "wuxing": GAN_WUXING[day_gan],
            "yinyang": GAN_YINYANG[day_gan],
        },
        "bazi": pillars,
        "xunkong": kong,
        "wuxing_tally": wuxing_tally,
        "shensha": chart_shensha,
        "geju": geju,
        "tiaohou": build_tiaohou(day_gan, pillars[1]["zhi"]),
        "xiji": build_xiji({"bazi": pillars, "day_master": {"gan": day_gan, "wuxing": GAN_WUXING[day_gan]},
                            "wuxing_tally": wuxing_tally}),
        "dayun": {
            "forward": yun.isForward(),
            "start": {
                "years": yun.getStartYear(),
                "months": yun.getStartMonth(),
                "days": yun.getStartDay(),
                "solar": f"{start_solar.getYear()}年{start_solar.getMonth()}月{start_solar.getDay()}日",
                "lunar": start_solar.getLunar().toString(),
            },
            "steps": steps,
        },
        "gong": {
            "minggong": {"ganzhi": ec.getMingGong(), "nayin": ec.getMingGongNaYin()},
            "taiyuan": {"ganzhi": ec.getTaiYuan(), "nayin": ec.getTaiYuanNaYin()},
            "shengong": {"ganzhi": ec.getShenGong(), "nayin": ec.getShenGongNaYin()},
            "taixi": {"ganzhi": ec.getTaiXi(), "nayin": ec.getTaiXiNaYin()},
        },
    }


def _build_liunian(dy, day_gan: str, year_zhi: str, day_zhi: str) -> list[dict]:
    """某步大运内的流年"""
    result = []
    for ln in dy.getLiuNian():
        gz = ln.getGanZhi()
        result.append({
            "year": ln.getYear(),
            "age": ln.getAge(),
            "ganzhi": gz,
            "gan": gz[0],
            "zhi": gz[1],
            "gan_shishen": gan_shishen_yun(day_gan, gz[0]),
            "shensha": _zhi_shensha_names(gz[1], year_zhi, day_zhi),
        })
    return result


# ============================================================
# 《穷通宝鉴》调候用神表（按原文用神次序：先用X，次用Y）
# ============================================================
TIAOHOU = {
    "甲": {"寅": "丙癸", "卯": "庚丙丁", "辰": "庚丁壬", "巳": "癸丁庚", "午": "癸丁庚",
           "未": "丁庚", "申": "庚丁", "酉": "丁丙庚", "戌": "丁壬癸", "亥": "庚丁戊",
           "子": "丁庚丙", "丑": "丁庚"},
    "乙": {"寅": "丙癸", "卯": "丙癸", "辰": "癸丙", "巳": "癸辛庚", "午": "癸丙",
           "未": "丙癸", "申": "丙癸己", "酉": "丙癸", "戌": "癸", "亥": "丙戊",
           "子": "丙", "丑": "丙"},
    "丙": {"寅": "壬庚", "卯": "壬庚辛", "辰": "壬甲", "巳": "壬庚", "午": "壬庚",
           "未": "壬庚", "申": "壬甲", "酉": "壬甲", "戌": "甲壬", "亥": "甲戊庚",
           "子": "壬戊甲", "丑": "壬甲"},
    "丁": {"寅": "庚壬", "卯": "庚甲", "辰": "甲庚", "巳": "甲庚", "午": "壬癸",
           "未": "甲壬", "申": "甲庚丙", "酉": "甲庚丙戊", "戌": "甲庚", "亥": "甲庚戊",
           "子": "甲庚戊", "丑": "甲庚戊"},
    "戊": {"寅": "丙甲癸", "卯": "丙甲癸", "辰": "甲癸丙", "巳": "甲丙癸", "午": "壬甲",
           "未": "癸丙甲", "申": "丙癸甲", "酉": "丙癸", "戌": "甲癸丙", "亥": "甲丙",
           "子": "丙甲", "丑": "甲丙"},
    "己": {"寅": "丙癸", "卯": "甲癸丙", "辰": "丙癸甲", "巳": "癸辛庚", "午": "癸辛",
           "未": "癸辛", "申": "丙癸", "酉": "丙癸", "戌": "丙癸", "亥": "丙戊",
           "子": "丙戊", "丑": "丙戊"},
    "庚": {"寅": "丙甲", "卯": "丁甲", "辰": "甲丁", "巳": "壬戊丙", "午": "壬癸",
           "未": "丁甲", "申": "丁甲", "酉": "丁甲丙", "戌": "甲壬", "亥": "丁丙甲",
           "子": "丙", "丑": "丙丁甲"},
    "辛": {"寅": "己壬", "卯": "壬甲", "辰": "壬甲", "巳": "壬甲癸", "午": "壬己",
           "未": "壬庚", "申": "壬甲", "酉": "壬", "戌": "壬甲", "亥": "壬丙",
           "子": "丙壬", "丑": "丙壬"},
    "壬": {"寅": "庚丙戊", "卯": "戊辛", "辰": "甲庚", "巳": "辛庚壬", "午": "庚辛壬",
           "未": "辛甲", "申": "戊丁", "酉": "甲", "戌": "甲丙戊", "亥": "戊丙庚",
           "子": "戊丙庚", "丑": "丙甲戊"},
    "癸": {"寅": "辛丙", "卯": "庚辛", "辰": "丙辛", "巳": "辛庚", "午": "庚辛壬",
           "未": "庚辛", "申": "丁甲", "酉": "辛丙", "戌": "辛癸甲", "亥": "庚辛",
           "子": "丙辛", "丑": "丙"},
}

SHENG_FU = {"比肩", "劫财", "正印", "偏印"}          # 生扶
KE_XIE_HAO = {"正官", "七杀", "正财", "偏财", "食神", "伤官"}  # 克泄耗
# 天干五合化气（《滴天髓·化象》："甲己合而化土、乙庚化金、丙辛化水、丁壬化木、戊癸化火"）
GAN_HE = {"甲": ("己", "土"), "乙": ("庚", "金"), "丙": ("辛", "水"),
          "丁": ("壬", "木"), "戊": ("癸", "火"), "己": ("甲", "土"),
          "庚": ("乙", "金"), "辛": ("丙", "水"), "壬": ("丁", "木"),
          "癸": ("戊", "火")}
# 专旺五格（《滴天髓》："专旺五格炎上、曲直、润下、从革、稼穑"）
ZHUANWANG = {"木": "曲直格", "火": "炎上格", "土": "稼穑格", "金": "从革格", "水": "润下格"}
MONTH_NAMES = {"寅": "正月", "卯": "二月", "辰": "三月", "巳": "四月", "午": "五月", "未": "六月",
               "申": "七月", "酉": "八月", "戌": "九月", "亥": "十月", "子": "十一月", "丑": "十二月"}


def season_status(dm_wx: str, month_wx: str) -> tuple[str, float, str]:
    """日主五行对月令五行之旺相休囚死（当令者旺，我生者相，生我者休，克我者囚，我克者死）"""
    if dm_wx == month_wx:
        return "旺", 1.0, "日主五行与月令相同，当令而旺，得令"
    if SHENG[month_wx] == dm_wx:
        return "相", 0.5, "月令生扶日主（我生者相），气得月令，得令次之"
    if SHENG[dm_wx] == month_wx:
        return "休", 0.0, "日主泄气于月令（生我者休），失令"
    if KE[dm_wx] == month_wx:
        return "囚", 0.0, "日主克月令而劳耗（克我者囚），失令"
    return "死", 0.0, "月令克制日主（我克者死），失令"


def _root_info(pillar: dict, dm_wx: str) -> tuple[int, int, str]:
    """(本气根数, 余气根数, 说明)"""
    ben = 0
    yu = 0
    marks = []
    for i, c in enumerate(pillar["canggan"]):
        is_root = GAN_WUXING[c["gan"]] == dm_wx
        if is_root and i == 0:
            ben += 1
            marks.append(f"{c['gan']}（本气根）")
        elif is_root:
            yu += 1
            marks.append(f"{c['gan']}（余气根）")
    mark = "、".join(marks) if marks else "无"
    return ben, yu, mark


def build_xiji(data: dict) -> dict:
    """强弱喜忌分析（子平扶抑 + 调候双核心，按六步验算）"""
    pillars = data["bazi"]
    dm_gan = data["day_master"]["gan"]
    dm_wx = data["day_master"]["wuxing"]
    month_zhi = pillars[1]["zhi"]
    month_wx = ZHI_WUXING[month_zhi]
    steps = []
    marks = []

    # ---------- 步骤一：得令（月令权重 50%） ----------
    status, ling_score, ling_note = season_status(dm_wx, month_wx)
    steps.append({
        "step": "步骤一",
        "title": "得令判定（月令权重 50%）",
        "logic": (
            f"日主{dm_gan}属{dm_wx}，生于{MONTH_NAMES[month_zhi]}（{month_zhi}），月令{month_wx}当令。"
            f"四季旺衰：木春、火夏、金秋、水冬、土四季末。{dm_wx}于{month_zhi}月为「{status}」——{ling_note}。"
            f"得令分 = {ling_score:.1f}×50%"
        ),
        "score": ling_score,
    })

    # ---------- 步骤二：通根得地（权重 30%） ----------
    root_lines = []
    ben_total = 0
    yu_total = 0
    for i in range(4):
        ben, yu, mk = _root_info(pillars[i], dm_wx)
        ben_total += ben
        yu_total += yu
        root_lines.append(f"{pillars[i]['label']}（{pillars[i]['zhi']}）：{mk}")
    if ben_total >= 2:
        root_level = "双本气根，根基厚重"
    elif ben_total == 1 and yu_total >= 2:
        root_level = "一本气根加多支余气，根基较厚"
    elif ben_total == 1:
        root_level = "一本气根（或有余气），根基中等"
    elif yu_total >= 2:
        root_level = "两支余气根，根气偏弱"
    elif yu_total == 1:
        root_level = "一余气根，根气偏弱"
    else:
        root_level = "无根，日主虚浮"
    di_score = min(1.0, ben_total * 0.6 + yu_total * 0.3)
    steps.append({
        "step": "步骤二",
        "title": "通根得地（权重 30%）",
        "logic": (
            f"清点四柱地支通根（区分本气/余气）：{'；'.join(root_lines)}。"
            f"本气根 {ben_total} 个，余气根 {yu_total} 个 → {root_level}。得地分 = {di_score:.2f}×30%"
        ),
        "score": di_score,
    })

    # ---------- 步骤三：天干得势（权重 20%）与全局克泄耗 ----------
    sheng_stems = []
    ke_stems = []
    for i in (0, 1, 3):
        ss = pillars[i]["shishen_gan"]
        if ss in SHENG_FU:
            sheng_stems.append(f"{pillars[i]['gan']}({ss})")
        elif ss in KE_XIE_HAO:
            ke_stems.append(f"{pillars[i]['gan']}({ss})")
    shi_score = min(1.0, len(sheng_stems) / 3)
    ke_ben = 0
    ke_yu = 0
    for p in pillars:
        for i, c in enumerate(p["canggan"]):
            if c["shishen"] in KE_XIE_HAO:
                if i == 0:
                    ke_ben += 1
                else:
                    ke_yu += 0.5
    ke_total = len(ke_stems) + ke_ben + ke_yu
    ke_score = min(1.0, ke_total / 4)
    steps.append({
        "step": "步骤三",
        "title": "天干得势（权重 20%）与全局克泄耗",
        "logic": (
            f"天干除日主外：生扶（印、比劫）{'、'.join(sheng_stems) if sheng_stems else '无'}；"
            f"克泄耗（官杀、财、食伤）{'、'.join(ke_stems) if ke_stems else '无'}。"
            f"得势分 = {shi_score:.2f}×20%；支中克泄耗再计：本气 {ke_ben}、余气折半计 {ke_yu:.1f}，"
            f"全局克泄耗总能量 = {ke_total:.1f}（满分4，折算 {ke_score:.2f}）"
        ),
        "score": shi_score,
    })

    # ---------- 格局判材：生扶/克泄耗分类明细（天干+藏干）与天干五合 ----------
    sheng_stem_pairs = []
    ke_stem_pairs = []
    for i in (0, 1, 3):
        ss = pillars[i]["shishen_gan"]
        if ss in SHENG_FU:
            sheng_stem_pairs.append((pillars[i]["label"], pillars[i]["gan"], ss))
        elif ss in KE_XIE_HAO:
            ke_stem_pairs.append((pillars[i]["label"], pillars[i]["gan"], ss))
    sheng_hidden = []
    guan_chars = []
    cai_chars = []
    shi_chars = []
    for p in pillars:
        for c in p["canggan"]:
            if c["shishen"] in SHENG_FU:
                sheng_hidden.append((p["label"], c["gan"], c["shishen"]))
            elif c["shishen"] in ("正官", "七杀"):
                guan_chars.append((p["label"], c["gan"], c["shishen"]))
            elif c["shishen"] in ("正财", "偏财"):
                cai_chars.append((p["label"], c["gan"], c["shishen"]))
            elif c["shishen"] in ("食神", "伤官"):
                shi_chars.append((p["label"], c["gan"], c["shishen"]))
    for _label, _g, ss in ke_stem_pairs:
        if ss in ("正官", "七杀"):
            guan_chars.append((_label, _g, ss))
        elif ss in ("正财", "偏财"):
            cai_chars.append((_label, _g, ss))
        elif ss in ("食神", "伤官"):
            shi_chars.append((_label, _g, ss))
    sheng_total = len(sheng_stem_pairs) + len(sheng_hidden)

    # 天干五合（《滴天髓·化象》）：日干与年/月/时干相合
    hua_info = None
    if dm_gan in GAN_HE:
        _partner, _hua_wx = GAN_HE[dm_gan]
        _pairs = [(pillars[i]["label"], pillars[i]["gan"]) for i in (0, 1, 3)
                  if pillars[i]["gan"] == _partner]
        if _pairs:
            hua_info = {"pair": f"{dm_gan}{_partner}", "hua_wx": _hua_wx,
                        "partners": _pairs, "zheng_he": len(_pairs) == 1,
                        "dang_ling": ZHI_WUXING[month_zhi] == _hua_wx}
    # 月令是否食伤当令（《滴天髓·从儿》："月建逢食伤，必要食伤在提纲"）
    month_shi = bool(pillars[1]["canggan"]) and pillars[1]["canggan"][0]["shishen"] in ("食神", "伤官")

    # 五行角色基准（以日主为"我"）
    yin_wx = next(e for e in "木火土金水" if SHENG[e] == dm_wx)   # 生我者 → 印
    guan_wx = next(e for e in "木火土金水" if KE[e] == dm_wx)     # 克我者 → 官杀
    shi_wx = SHENG[dm_wx]                                          # 我生 → 食伤
    cai_wx = KE[dm_wx]                                             # 我克 → 财
    bi_wx = dm_wx                                                  # 同我 → 比劫

    # ---------- 步骤四：三权重加权 ----------
    F = 0.5 * ling_score + 0.3 * di_score + 0.2 * shi_score
    K = ke_score
    R = F / (F + K) if (F + K) > 0 else 0.5

    # 特殊标注（双羊刃 / 四库 / 伤官见官）对强弱的加减
    adj = 0.0
    yangren_count = sum(1 for p in pillars if p["zhi"] == YANGREN[dm_gan])
    if yangren_count >= 2:
        marks.append(f"双羊刃（{YANGREN[dm_gan]}支两见）：身旺之气加倍，旺度 +0.05")
        adj += 0.05
    zhis = {p["zhi"] for p in pillars}
    if {"辰", "戌", "丑", "未"} <= zhis:
        if dm_wx == "土":
            marks.append("四库全见（辰戌丑未）：土气厚实帮身，旺度 +0.05")
            adj += 0.05
        else:
            marks.append(f"四库全见（辰戌丑未）：土重为{dm_wx}之财库耗身，旺度 −0.05")
            adj -= 0.05
    all_ss = set()
    for p in pillars:
        all_ss.add(p["shishen_gan"])
        for c in p["canggan"]:
            all_ss.add(c["shishen"])
    if "伤官" in all_ss and "正官" in all_ss:
        marks.append("伤官见官：官星受伤，格局损耗，旺度 −0.05")
        adj -= 0.05
    R_adj = min(1.0, max(0.0, R + adj))

    def tier_of(r: float) -> str:
        if r >= 0.70:
            return "极旺"
        if r >= 0.55:
            return "身旺"
        if r >= 0.45:
            return "中和偏弱"
        if r >= 0.30:
            return "身弱"
        return "极弱"

    tier = tier_of(R_adj)

    # ---------- 特殊格局判定（《滴天髓》从象/化象/假从/从儿） ----------
    from_ge = None
    ge_quality = ""
    ge_note = ""
    ge_basis = ""

    # 1) 化气格（真化）：日干相合、化神得令、日主衰弱且四柱无印比生扶 —— "化得真者只论化"
    if (hua_info and hua_info["zheng_he"] and hua_info["dang_ling"]
            and tier in ("身弱", "极弱") and sheng_total == 0):
        from_ge = f"化气格（{hua_info['pair']}化{hua_info['hua_wx']}）"
        ge_quality = "真化"
        ge_basis = "《滴天髓·化象》：化神得令、日主无根衰弱则化得真，用神只论化神喜忌"
        ge_note = (f"日干{hua_info['pair'][0]}与{hua_info['partners'][0][0]}"
                   f"{hua_info['partners'][0][1]}相合，化神{hua_info['hua_wx']}当令于"
                   f"{MONTH_NAMES[month_zhi]}，日主无根，成真化")
    elif hua_info and hua_info["zheng_he"]:
        if hua_info["dang_ling"]:
            _why = ("日主有印比生扶，不从化神（《滴天髓》作假化）" if sheng_total > 0
                    else "日主自旺，不从化神（《滴天髓》作假化）")
        else:
            _why = "化神不得月令，其气不盛"
        marks.append(f"日干与{hua_info['partners'][0][1]}干相合，但{_why}——"
                     f"合而不化，仍按扶抑论（《滴天髓·化象》）")

    # 2) 从儿格：月令食伤成势，"从儿不管身强弱，只要吾儿再见儿"
    #    "只见儿者，食伤多也"（任注）：食伤须为全局最盛之气势
    if (from_ge is None and month_shi and len(shi_chars) >= 3
            and len(shi_chars) >= max(len(guan_chars), len(cai_chars))):
        has_yin = any(t[2] in ("正印", "偏印") for t in sheng_stem_pairs + sheng_hidden)
        from_ge = "从儿格"
        ge_quality = "假从" if has_yin else "真从"
        ge_basis = "《滴天髓·从儿》：月建逢食伤、全局食伤成势，不论身强弱"
        ge_note = (f"月令食伤当令，全局食伤共 {len(shi_chars)} 字成势；"
                   + ("有印绶克破食伤，作假从儿" if has_yin else "格局纯粹，真从儿"))

    # 3) 专旺（从旺/从强）：日主得令或得地，天干尽印比（官杀食伤不现），地支皆禄刃印地 —— 顺其旺势
    #    （《滴天髓·从旺》："日主得令，要么得地……天干上只出现比肩劫财、印绶……没有出现官星七杀、
    #      食神伤官"；任注命例：癸卯、乙卯、甲寅、乙亥）
    if from_ge is None:
        za_zhi = [p["zhi"] for p in pillars if p["zhi_wuxing"] not in (dm_wx, yin_wx)]
        if ((ling_score >= 0.5 or ben_total >= 2) and len(sheng_stem_pairs) >= 2):
            if len(ke_stem_pairs) == 0 and not za_zhi:
                from_ge = f"专旺格（{ZHUANWANG[dm_wx]}）"
                ge_quality = "真从"
                ge_basis = "《滴天髓·从旺》：日主得令得地、天干只现印比、地支皆禄刃印地，旺极而从其旺势"
                ge_note = "全局印比成势、无官杀食伤混杂，格局纯粹，真从旺"
            elif len(ke_stem_pairs) <= 1 and len(za_zhi) <= 1:
                from_ge = f"专旺格（{ZHUANWANG[dm_wx]}）"
                ge_quality = "假从"
                ge_basis = "《滴天髓·从旺》：印比成势而见财杀混杂，象不纯粹，行运去杂存纯亦能成格"
                _mix = []
                if ke_stem_pairs:
                    _mix.append("天干" + "、".join(t[1] for t in ke_stem_pairs))
                if za_zhi:
                    _mix.append("支" + "、".join(za_zhi))
                ge_note = f"见财杀混杂（{'；'.join(_mix)}），作假从旺"

    # 4) 从弱（从财/从杀/从势）：日主孤立无气，从所旺之财官食伤
    if from_ge is None and tier == "极弱":
        dom_cat = max((("官杀", len(guan_chars)), ("财", len(cai_chars)), ("食伤", len(shi_chars))),
                      key=lambda kv: kv[1])
        second_n = sorted([len(guan_chars), len(cai_chars), len(shi_chars)], reverse=True)[1]
        if sheng_total == 0:
            # 真从：四柱绝无一毫生扶（《滴天髓》："无地人元，绝无一毫生扶之意"）
            if dom_cat[1] >= 2 and dom_cat[1] > second_n:
                from_ge = {"官杀": "从杀格（弃命从杀）", "财": "从财格", "食伤": "从势格"}[dom_cat[0]]
            else:
                from_ge = "从势格"
            ge_quality = "真从"
            ge_basis = "《滴天髓·从象》：日主孤立无气，四柱无生扶之意，财官食伤强甚，乃为真从"
            ge_note = f"印比全无（生扶 0 字），{dom_cat[0]}势盛，从所旺之{dom_cat[0]}"
        else:
            # 假从：有印比暗生但皆受制（印被财破、比劫被官杀制），自顾不暇
            cai_any = {g for _, g, ss in cai_chars if ss in ("正财", "偏财")}
            guan_any = {g for _, g, ss in guan_chars if ss in ("正官", "七杀")}
            restrained = True
            for _, _g, ss in sheng_stem_pairs + sheng_hidden:
                if ss in ("正印", "偏印"):
                    restrained &= bool(cai_any)
                else:
                    restrained &= bool(guan_any)
            if restrained and sheng_total <= 2:
                if dom_cat[1] >= 2 and dom_cat[1] > second_n:
                    from_ge = {"官杀": "从杀格", "财": "从财格", "食伤": "从势格"}[dom_cat[0]]
                else:
                    from_ge = "从势格"
                ge_quality = "假从"
                ge_basis = "《滴天髓·假从》：日主弱、财官强，中有比劫印绶暗生，从之不真，行运去杂存纯亦能发"
                ge_note = f"生扶 {sheng_total} 字皆受制（印被财破、劫被官制），自顾不暇，假从{dom_cat[0]}"

    steps.append({
        "step": "步骤四",
        "title": "三权重加权结论",
        "logic": (
            f"扶助能量 F = 0.5×{ling_score:.1f}(令) + 0.3×{di_score:.2f}(地) + 0.2×{shi_score:.2f}(势) = {F:.2f}；"
            f"克泄耗 K = {K:.2f}；强弱比 R = F/(F+K) = {R:.2f}"
            + (f"；特殊标注校正后 R' = {R_adj:.2f}" if adj else "")
            + f" → 身强身弱五档划分：{tier}"
            + (f"；另按《滴天髓》从象/化象/从儿章判为【{from_ge}】（{ge_quality}）：{ge_note}"
               if from_ge else "")
        ),
        "score": R_adj,
    })

    # ---------- 步骤五：调候优先 ----------
    # 寒暖计数：只数"有根"之字——天干五行须在地支（本气或藏干）见根，虚浮不计；
    # 地支以本气论，自坐即有根。（硬性限制2：不得只数五行个数，须区分根气、月令优先级）
    zhi_wx_set = {p["zhi_wuxing"] for p in pillars}
    canggan_wx_set = {GAN_WUXING[c["gan"]] for p in pillars for c in p["canggan"]}

    def _rooted(wx: str) -> bool:
        return wx in zhi_wx_set or wx in canggan_wx_set

    hot = 0
    cold = 0
    for p in pillars:
        if p["gan_wuxing"] in ("火", "土") and _rooted(p["gan_wuxing"]):
            hot += 1
        if p["gan_wuxing"] in ("金", "水") and _rooted(p["gan_wuxing"]):
            cold += 1
        if p["zhi_wuxing"] in ("火", "土"):
            hot += 1
        if p["zhi_wuxing"] in ("金", "水"):
            cold += 1
    dc = hot - cold
    season_hot = month_zhi in ("巳", "午", "未")
    season_cold = month_zhi in ("亥", "子", "丑")
    # 【2026-09-15 修·月令优先】月令为提纲，寒暖先看月令、干支只作辅证：
    #   巳午未月 → 燥局；亥子丑月 → 寒局（无论干支多寡）；
    #   月令中性（寅卯辰申酉戌）才以全局有根干支的寒暖多寡定之（火土比金水多 ≥2 字为燥，反之 2 字为寒）。
    # 旧写法 `if season_hot or dc >= 2` 让计数与月令平权、且计数分支在前——
    #   冬月火土多的盘会被误判「燥局」（实测：己日主子月，火土 6 字金水 2 字 → 旧判燥局补水，
    #   《穷通宝鉴》十一月己却要丙、戊，调候方向正好相反）。
    if season_hot:
        cold_dry = ("燥局", "水", "壬癸")
        cd_reason = f"生于{MONTH_NAMES[month_zhi]}（{month_zhi}），夏火当令，火炎土燥（月令定寒暖，干支只作辅证）"
    elif season_cold:
        cold_dry = ("寒局", "火", "丙丁")
        cd_reason = f"生于{MONTH_NAMES[month_zhi]}（{month_zhi}），冬水当令，金寒水冷（月令定寒暖，干支只作辅证）"
    elif dc >= 2:
        cold_dry = ("燥局", "水", "壬癸")
        cd_reason = f"月令{MONTH_NAMES[month_zhi]}不寒不燥，但全局有根火土 {hot} 字、有根金水 {cold} 字，火多燥盛"
    elif dc <= -2:
        cold_dry = ("寒局", "火", "丙丁")
        cd_reason = f"月令{MONTH_NAMES[month_zhi]}不寒不燥，但全局有根金水 {cold} 字、有根火土 {hot} 字，金多水寒"
    else:
        cold_dry = None
        cd_reason = f"月令不寒不燥，全局有根火土 {hot} 字、有根金水 {cold} 字，寒暖中和"
    # 调候取用（2026-09-15 差异2 落地）：寒燥失衡触发时，用神不再只取"寒燥方向"（寒→火、燥→水），
    # 而是按《穷通宝鉴》月令调候表的**用神次序**取首味，整串次序（t0_list）随命局档案存档；
    # 表内无此格时回退寒燥方向法。首味与寒燥方向不同时（表中用神兼扶抑病药，不单是寒暖剂），
    # 以表为准并加标注说明，不静默吞掉差异。
    tk_chars = TIAOHOU.get(dm_gan, {}).get(month_zhi, "")
    tk_wuxing = list(dict.fromkeys(GAN_WUXING[c] for c in tk_chars))
    t0_src = ""
    yongshen_adj = None
    if cold_dry:
        if tk_chars:
            yongshen_adj = GAN_WUXING[tk_chars[0]]
            t0_src = "穷通宝鉴·月令调候表"
            steps.append({
                "step": "步骤五",
                "title": "调候优先判定",
                "logic": (
                    f"{cd_reason} → 判定为【{cold_dry[0]}】。依《穷通宝鉴》{MONTH_NAMES[month_zhi]}{dm_gan}："
                    f"调候用神次序 {'、'.join(tk_chars)}（{'、'.join(tk_wuxing)}）"
                    f"→ 第一用神取首味「{tk_chars[0]}」（{yongshen_adj}），整串次序随命局档案存档；"
                    f"再以扶抑取用神辅助；寒燥失衡不作纯扶抑推断。"
                ),
                "score": 1.0,
            })
            if yongshen_adj != cold_dry[1]:
                marks.append(
                    f"《穷通宝鉴》首味「{tk_chars[0]}」（{yongshen_adj}）与寒燥方向（{cold_dry[0]}宜{cold_dry[1]}）不同："
                    f"表中用神兼扶抑病药、不单是寒暖剂，以表为准（整串「{'、'.join(tk_chars)}」已存档）"
                )
        else:
            yongshen_adj = cold_dry[1]
            t0_src = "寒燥方向（表内无此格）"
            steps.append({
                "step": "步骤五",
                "title": "调候优先判定",
                "logic": (
                    f"{cd_reason} → 判定为【{cold_dry[0]}】。依《穷通宝鉴》调候优先："
                    f"先取{cold_dry[2]}为第一用神以调候，再以扶抑取用神辅助；寒燥失衡不作纯扶抑推断。"
                ),
                "score": 1.0,
            })
    else:
        steps.append({
            "step": "步骤五",
            "title": "调候优先判定",
            "logic": f"{cd_reason}，无寒燥失衡 → 纯扶抑取用（调候门休眠；《穷通宝鉴》月令药单仍随档案存档备查）。",
            "score": 0.0,
        })

    # ---------- 步骤六：分层取用（含具体五行，便于"喜什么缺什么"） ----------
    tally = data.get("wuxing_tally", {})

    def _mk(role_label, wuxing, role_note, extra=""):
        return {"wuxing": wuxing, "text": f"{wuxing[0] if len(wuxing) == 1 else '、'.join(wuxing)}{('·' + extra) if extra else ''}", "note": role_note}

    if from_ge and from_ge.startswith("化气格"):
        # 化神旺而有馀宜泄、衰而不足宜生助（《滴天髓·化象》）；化神最忌逆势（克化神者）
        h_wx = hua_info["hua_wx"]
        h_ke = next(e for e in "木火土金水" if KE[e] == h_wx)        # 克化神者
        h_xie = SHENG[h_wx]                                          # 泄化神者
        h_sheng = next(e for e in "木火土金水" if SHENG[e] == h_wx)  # 生化神者
        h_yu = tally.get(h_wx, 0) >= 4
        role_map = {
            "yongshen": _mk("第一用神", [h_xie if h_yu else h_sheng],
                            "化神有馀，宜泄化神之神" if h_yu else "化神不足，宜生助化神之神",
                            f"化神{h_wx}" + ("有馀" if h_yu else "不足")),
            "xishen": _mk("次喜神", [h_wx], "化神同党，助其气势", "助化"),
            "xianshen": _mk("闲神", [], "与化神无涉", ""),
            "choushen": _mk("仇神", [yin_wx, bi_wx], "日主印比还原破格", "还原"),
            "jishen": _mk("忌神", [h_ke], "克伐化神，逆化神旺势", "逆势")}
    elif from_ge and from_ge.startswith("从儿格"):
        role_map = {"yongshen": _mk("第一用神", [cai_wx], "儿又生儿，财星流通为用", "儿见儿"),
                    "xishen": _mk("次喜神", [shi_wx], "食伤所从之势，顺其旺气", "从儿"),
                    "xianshen": _mk("闲神", [bi_wx], "比劫仍去生助食伤，不碍成格", ""),
                    "choushen": _mk("仇神", [guan_wx], "官杀暗伤食伤之气，次忌", "次忌"),
                    "jishen": _mk("忌神", [yin_wx], "印绶克破食伤，从儿最忌", "破格")}
    elif from_ge and (from_ge.startswith("从杀") or from_ge.startswith("从财")
                      or from_ge.startswith("从势")):
        # 所从之神 S：从杀→官杀、从财→财、从势→全局最旺之类别
        if from_ge.startswith("从杀"):
            s_wx = guan_wx
        elif from_ge.startswith("从财"):
            s_wx = cai_wx
        else:
            top_cat, _top_n = max({"官杀": len(guan_chars), "财": len(cai_chars),
                                   "食伤": len(shi_chars)}.items(), key=lambda kv: kv[1])
            s_wx = {"官杀": guan_wx, "财": cai_wx, "食伤": shi_wx}[top_cat]
        s_sheng = next(e for e in "木火土金水" if SHENG[e] == s_wx)   # 生从神者
        s_ke = next(e for e in "木火土金水" if KE[e] == s_wx)         # 克从神者（伤从神）
        s_xie = SHENG[s_wx]                                            # 泄从神者
        # "从神又有吉和凶"（《滴天髓·从象》任注）：从财太过喜泄从神；
        # 从杀/从势以顺为贵，不作太过论。生从神者若即日主印比，则帮身破从，不作喜神
        s_yu = from_ge.startswith("从财") and tally.get(s_wx, 0) >= 4
        xi_extra = []
        xi_note = "生助从神"
        if s_sheng not in (bi_wx, yin_wx):
            xi_extra.append(s_sheng)
        else:
            xi_note = "生从神者即日主印比，帮身破从，不作喜神"
        if s_yu:
            xi_extra.append(s_xie)
            xi_note += "；从神有馀再以泄调之"
        role_map = {
            "yongshen": _mk("第一用神", [s_wx], f"从所旺之{s_wx}势，只论所从之神", "从神"),
            "xishen": _mk("次喜神", xi_extra, xi_note, "助从"),
            "xianshen": _mk("闲神", [], "", ""),
            "choushen": _mk("仇神", [s_xie] if not s_yu and s_xie not in (bi_wx, yin_wx) else [],
                            "泄从神之气，从神不足则凶", "泄从"),
            "jishen": _mk("忌神", list(dict.fromkeys([bi_wx, yin_wx, s_ke])),
                          "比劫印绶帮身破从；克从神则从神衰（金不可克木，克木财衰矣）", "破从")}
    elif from_ge and from_ge.startswith("专旺"):
        role_map = {"yongshen": _mk("第一用神", [bi_wx], "专旺成格，顺其旺势", "从旺神"),
                    "xishen": _mk("次喜神", [yin_wx], "印绶生身助旺，与比劫同顺其势", "助旺"),
                    "xianshen": _mk("闲神", [shi_wx], "食伤泄秀，岁运见之有得有失", "泄秀"),
                    "choushen": _mk("仇神", [cai_wx], "财星生官而逆旺，群劫争财", "逆势"),
                    "jishen": _mk("忌神", [guan_wx], "官杀克伐旺神而破格，犯旺", "破格")}
    elif tier in ("身旺", "极旺"):
        role_map = {"yongshen": _mk("第一用神", [guan_wx], "官杀克身制旺", "克身"),
                    "xishen": _mk("次喜神", [shi_wx, cai_wx], "食伤泄秀、财星耗身", "泄耗"),
                    "xianshen": _mk("闲神", [], "无明显喜忌", ""),
                    "choushen": _mk("仇神", [yin_wx], "印绶生身而助旺，生忌", "助旺"),
                    "jishen": _mk("忌神", [bi_wx], "比劫同党加重失衡", "助旺")}
    else:  # 身弱（含中和偏弱/身弱/极弱）
        role_map = {"yongshen": _mk("第一用神", [yin_wx], "印绶生身（核心解药）", "生身"),
                    "xishen": _mk("次喜神", [bi_wx], "比劫帮扶日主", "帮身"),
                    "xianshen": _mk("闲神", [shi_wx], "食伤泄秀，无明显好坏", "泄秀"),
                    "choushen": _mk("仇神", [cai_wx], "财星耗身、克印生官", "耗身"),
                    "jishen": _mk("忌神", [guan_wx], "官杀克身，加重失衡", "克身")}

    # —— 命局三参考系（供命卦校验用），在调候覆盖前取"扶抑/格局"本义 ——
    F = []
    for _key in ("yongshen", "xishen"):
        for _w in role_map[_key]["wuxing"]:
            if _w and _w not in F:
                F.append(_w)
    J = [w for w in role_map["jishen"]["wuxing"] if w]
    if from_ge:
        # 从/化格局：仇神同属逆势（生忌克喜），一并计入忌方（如从儿次忌官杀、化格忌还原）
        for _w in role_map["choushen"]["wuxing"]:
            if _w and _w not in J:
                J.append(_w)
    T0 = [yongshen_adj] if yongshen_adj else []

    # 调候优先：寒燥失衡时以调候字为第一用神；从/化格局若调候字正落忌方则格局优先。
    # 扶抑（非从格）若调候字落在扶抑忌方（如壬日子月：寒局调候首味戊土，而身弱扶抑忌官杀土），
    # 两条取用路线在此相反——按「寒燥失衡先调候」以调候字为第一用神。
    # 2026-10-06 裁定（书证《子平真诠·论用神配气候得失》「调候为急，权而用之也」）：
    # 调候字**移出忌神表**并记标注；例外让位两条——从格成格（「倘格局转变则不在此例」）、
    # 火土旺极/重逢（《穷通宝鉴评注》徐注，阈值工程默认）。落仇方者仍并列标注不移出
    # （仇神在非从格不进裁决 J，只是扶抑本义的显示列）。
    fy: list = []
    fy_note = ""
    if yongshen_adj:
        fy = role_map["yongshen"]["wuxing"]
        fy_note = role_map["yongshen"]["note"]
        chou_wuxing = role_map["choushen"]["wuxing"]
        if from_ge and yongshen_adj in J:
            # 让位：调候字移出 T0（裁决层不再开调候门），仅随 t0_list 存档作岁运参考——
            # 《子平真诠》「病药为用……调候亦然。倘格局转变则不在此例」（评注页）：
            # 格局转变（从格成格）时调候不在此例，若不空 T0，门2仍会按它拦截/加成，
            # 等于让位只让了一半。
            T0 = []
            t0_src = ""
            marks.append(f"调候字{yongshen_adj}与【{from_ge}】忌方相重：从化格局忌逆势，"
                         f"仍以格局用神为先，调候字仅作岁运参考（《滴天髓》从神又有吉和凶）")
        elif yongshen_adj in J and (
                int(tally.get("火", 0)) + int(tally.get("土", 0))
                >= int(_XIJI.get("huo_tu_wangji_min", 6))):
            # 例外让位②：火土旺极/重逢 → 无须调候（《穷通宝鉴评注》十二月辛金「若火土重逢，
            # 无须调候」、三冬己土「除非四柱火土旺极，借用癸水」——均徐乐吾注）。
            # 调候字移出 T0（裁决层不再按它开调候门），仅随 t0_list 整串药单存档。
            # 「火土合计≥6 字」为工程默认门槛（weights.yaml xiji.huo_tu_wangji_min）。
            T0 = []
            t0_src = ""
            marks.append(
                f"调候字「{yongshen_adj}」与扶抑忌方相重，而局中火土旺极/重逢"
                f"（火{tally.get('火', 0)}土{tally.get('土', 0)}），无须调候"
                f"（《穷通宝鉴评注》「若火土重逢，无须调候」「除非四柱火土旺极」，均徐乐吾注）："
                f"调候字移出调候用神表，仅随《穷通宝鉴》整串药单存档作岁运参考；"
                f"「火土合计≥{_XIJI.get('huo_tu_wangji_min', 6)}字」为工程默认门槛"
            )
        elif yongshen_adj in J:
            # 调候为急，权而用之（2026-10-06 站长裁定，书证《子平真诠·论用神配气候得失》原文：
            # 「伤官见官，为祸百端，而金水见之，反为秀气。非官之不畏夫伤，而调候为急，权而用之也」）：
            # 调候字**移出忌神表**——裁决层不再否决自己的第一用神；扶抑口径仅作岁运参考。
            # （此前做法是"忌神位仍按扶抑列出、加标记"，页面仍同屏出现两个相反结论；此版起移除。）
            J.remove(yongshen_adj)
            rm_j = role_map["jishen"]
            _j_extra = rm_j["text"].split("·", 1)[1] if "·" in rm_j["text"] else ""
            role_map["jishen"] = _mk(
                "忌神", [w for w in rm_j["wuxing"] if w != yongshen_adj],
                rm_j["note"] + f"；调候字「{yongshen_adj}」原列于此，"
                f"依《子平真诠》「调候为急，权而用之也」移出，仅作岁运参考",
                _j_extra)
            marks.append(
                f"调候字「{yongshen_adj}」与扶抑忌方相重：调候与扶抑两条取用路线在此相反"
                f"（调候取「{yongshen_adj}」为第一用神，扶抑以「{yongshen_adj}」为忌神）；"
                f"本站按「寒燥失衡先调候」以调候字为第一用神"
                f"（《子平真诠·论用神配气候得失》「非官之不畏夫伤，而调候为急，权而用之也」），"
                f"调候字已移出忌神表，扶抑口径仅作岁运参考"
            )
        elif yongshen_adj in chou_wuxing:
            # 调候字落在扶抑仇神（2026-10 补：此前只查忌方，落仇方（如调候补水、
            # 身弱扶抑以水为仇神财星耗身）时两条路线相反却裸示无标记，用户无从判断看哪个）
            marks.append(
                f"调候字「{yongshen_adj}」与扶抑仇方相重：调候与扶抑两条取用路线在此相反"
                f"（调候取「{yongshen_adj}」为第一用神，扶抑以「{yongshen_adj}」为仇神）；"
                f"本站按「寒燥失衡先调候」以调候字为第一用神"
                f"（《子平真诠·论用神配气候得失》「故取用神，于扶抑之外，必须参合气候，即调候之法也」），"
                f"仇神位仍按扶抑列出、不与调候合并"
            )
        if not (from_ge and yongshen_adj in J) and not (
                yongshen_adj in J and
                int(tally.get("火", 0)) + int(tally.get("土", 0))
                >= int(_XIJI.get("huo_tu_wangji_min", 6))):
            role_map["yongshen"] = {
                "wuxing": [yongshen_adj],
                "text": f"{yongshen_adj}（{cold_dry[0]}调候，第一用神）",
                "note": f"寒燥失衡先调候；扶抑用神为：{('、'.join(fy) if fy else '—')}（{fy_note}）",
            }

    layers = {k: v["text"] for k, v in role_map.items()}
    layers_meta = {k: {"wuxing": v["wuxing"], "note": v["note"]} for k, v in role_map.items()}

    # —— 喜忌整合视图：按五行聚合、带维度来源标签（2026-10 起供前端"一五行一行"渲染）——
    # 同一五行在两个参考系里可能扮演相反角色（如燥局调候用水为第一用神、身弱扶抑忌官杀水），
    # 五档并列的 layers 会把这种冲突拆成两条互不相干的条目；这里聚合成一行，标出
    # 「调候 / 扶抑 / 格局」维度来源，冲突时挂裁定语（adjust_marks 里「与扶抑忌方相重」那条）。
    tiao_overrode = bool(yongshen_adj) and not (from_ge and yongshen_adj in J)
    agg: dict = {}
    wx_order: list = []

    def _put(wx: str, role: str, label: str, src: str, note: str) -> None:
        if not wx:
            return
        if wx not in agg:
            agg[wx] = []
            wx_order.append(wx)
        agg[wx].append({"role": role, "role_label": label, "source": src, "note": note})

    role_label = {"yongshen": "用神", "xishen": "喜神", "xianshen": "闲神",
                  "choushen": "仇神", "jishen": "忌神"}
    for key in ("yongshen", "xishen", "xianshen", "choushen", "jishen"):
        m = role_map[key]
        if key == "yongshen" and tiao_overrode:
            src = "调候"
        elif from_ge:
            src = "格局"
        else:
            src = "扶抑"
        for wx in m["wuxing"]:
            _put(wx, key, role_label[key], src, m["note"])
    if tiao_overrode:
        # 调候覆盖时，扶抑本义用神（fy）单独挂到它的五行下，标「扶抑」——它是"参考线"不是最终裁定
        for wx in fy:
            _put(wx, "yongshen", "用神（扶抑本义）", "扶抑", fy_note)
    conflict_ruling = next(
        (mk for mk in marks if "与扶抑忌方相重" in mk or "与扶抑仇方相重" in mk), "")
    # 行内项目排序：扶抑在前、调候在后（站长 2026-10 定：两条参考系冲突时先看扶抑本义，
    # 再看调候裁定，避免「用神」被挤在行尾）；格局项只在从/化格出现，不与调候混行。
    _SRC_ORDER = {"扶抑": 0, "调候": 1, "格局": 2}
    for wx in wx_order:
        agg[wx].sort(key=lambda it: _SRC_ORDER.get(it["source"], 9))
    # 行序按站内五行的展示序（木火土金水，与「命局五行数量」tally 同一口径）——
    # 按角色插入序会得到 水→火→土→金→木 这类看似错位的排列（2026-10 修）。
    _WX_DISPLAY_ORDER = ["木", "火", "土", "金", "水"]
    layers_view = []
    for wx in sorted(wx_order, key=lambda w: _WX_DISPLAY_ORDER.index(w) if w in _WX_DISPLAY_ORDER else 9):
        view = {"wx": wx, "items": agg[wx]}
        if tiao_overrode and wx == yongshen_adj and conflict_ruling:
            view["ruling"] = conflict_ruling
        layers_view.append(view)

    steps.append({
        "step": "步骤六",
        "title": "分层输出五行层级（喜忌含具体五行）",
        "logic": (
            (f"【{from_ge}】（{ge_quality}）：{ge_note}。{ge_basis}，顺其势取用：" if from_ge
             else f"日主{dm_wx}{tier}，扶抑取用：")
            + (f"以日主五行 {bi_wx} 为基准：印在{yin_wx}、比劫在{bi_wx}，" if not from_ge else "")
            + f"食伤在{shi_wx}、财在{cai_wx}、官杀在{guan_wx}；"
            + ("旺则抑泄耗、弱则印比生扶 → " if not from_ge else "")
            + f"第一用神（核心解药）：{layers['yongshen']}；次喜神（辅助用神）：{layers['xishen']}；"
            f"闲神（无明显好坏）：{layers['xianshen']}；仇神（生忌克喜）：{layers['choushen']}；"
            f"忌神（加重命局失衡）：{layers['jishen']}"
        ),
        "score": 1.0,
    })

    # 命局五行数量与所缺（"缺什么"）
    if tally:
        order = ["木", "火", "土", "金", "水"]
        tally_txt = "，".join(f"{w}{tally.get(w, 0)}" for w in order)
        missing = [w for w in order if tally.get(w, 0) == 0]
        missing_txt = "、".join(missing) if missing else "无"
        # 喜用五行是否在命局透出/缺失
        like_wx = set()
        for k in ("yongshen", "xishen"):
            for w in role_map[k]["wuxing"]:
                like_wx.add(w)
        like_missing = [w for w in like_wx if tally.get(w, 0) == 0]
        like_note = (f"喜用五行 {('、'.join(like_missing))} 在四柱不透，宜岁运补益"
                     if like_missing else "喜用五行在四柱有根气，岁运逢之得力")
        wuxing_summary = {"tally": tally_txt, "missing": missing, "missing_txt": missing_txt,
                          "like_missing": like_missing, "like_note": like_note}
    else:
        wuxing_summary = None

    return {
        "tier": tier,
        "from_ge": from_ge,
        "score": round(R_adj, 2),
        "adjust_marks": marks,
        "steps": steps,
        "layers": layers,
        "layers_meta": layers_meta,
        "layers_view": layers_view,
        "wuxing_summary": wuxing_summary,
        "mingju": {
            "F": F,
            "J": J,
            "T0": T0,
            "t0_list": (tk_wuxing if tk_chars else []),   # 《穷通宝鉴》整串药单（按原文次序，五行）
            "t0_src": t0_src,                             # 首味取自表还是寒燥方向（""=调候门休眠）
            "tier": tier,
            "from_ge": from_ge,
            "ge_quality": ge_quality,
            "ge_note": ge_note,
            "ge_basis": ge_basis,
            "effective_wx": (hua_info["hua_wx"]
                             if from_ge and from_ge.startswith("化气格") else dm_wx),
            "day_master_wx": dm_wx,
            "month_wx": month_wx,
            "wuxing_tally": tally,
        },
    }


def build_tiaohou(dm_gan: str, month_zhi: str) -> dict:
    """《穷通宝鉴》调候用神（按原文用神次序）"""
    s = TIAOHOU.get(dm_gan, {}).get(month_zhi, "")
    return {
        "gan": dm_gan,
        "month": month_zhi,
        "yongshen": s,
        "wuxing": [GAN_WUXING[c] for c in s],
        "note": f"《穷通宝鉴》{MONTH_NAMES[month_zhi]}{dm_gan}：用神次序 {('、'.join(s)) if s else '—'}",
    }


if __name__ == "__main__":
    import json
    data = build_bazi_paipan(1990, 5, 15, 14, 30, gender=1)
    print(json.dumps(data, ensure_ascii=False, indent=2))
