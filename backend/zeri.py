# -*- coding: utf-8 -*-
"""
确定性择日引擎（紧急层"宜忌日期表"）
====================================
把"应于生体/喜用卦气旺相之日"固化为代码：对未来 N 天逐日取干支，
按纯序关系（不依赖数值精度）判定 宜/平/忌，输出日期表。

书证：
  《梅花易数·先天卦定应期》："先天之卦，定事应之期，则取之卦气。
    如乾、兑则应如庚、辛及申金之日……如震、巽当应于甲、乙及支木之日。"
    —— 应期日 = 事体五行（干或支）当值之日。
  《梅花易数·求名占》（体用总诀）："若想得知功成名就之日，可根据
    生体之卦卦气的旺相时间推断。" —— 应期日须卦气旺相。
  《梅花易数·心易占卜玄机》："体卦之气宜于旺盛，而生扶本卦的卦气
    则宜于旺盛，克制体卦的卦气宜于衰弱。" —— 喜用之日宜旺相，忌神之日宜衰。
  旺相休囚死（月令称重）：《渊海子平》/《五行大义》通行表。

判定原则（确定性归代码，语言归 AI）：
  - 日辰天干或地支五行"当值"某五行即算该五行之日（干支同权，据先天卦定应期原文）；
  - 日辰主气以地支为准做月令称重（旺相休囚死，纯序关系）；
  - 忌：忌神当值（旺相）/ 日生忌神 / 日克喜用 / 与转急调候逆调；
  - 宜：处方或喜用当值且旺相（应期日）/ 日生处方或喜用且旺相 / 日克忌神；
  - 忌神当值但处囚死 → 忌神失令，降为平（生扶宜旺、克体宜衰的镜像）；
  - 优先级：忌 > 宜 > 平；绝不使用数值加权，全部为比较判断。
"""
from datetime import date as _date, datetime, timedelta

from bazi_engine import GAN_WUXING
from liunian import ZHI_WUXING, shiwang_liunian
from wuxing_relation import SHENG, KE, tiao_active, grade_T
from weights import ZERI_YI_STATES, ZERI_DAYS

SRC_YINGQI = "梅花易数·先天卦定应期/求名占"
SRC_SHUAIWANG = "梅花易数·心易占卜玄机（衰旺诀）"


def _day_pillar(d: _date) -> dict:
    solar = __import__("lunar_python").Solar.fromYmdHms(d.year, d.month, d.day, 12, 0, 0)
    lunar = solar.getLunar()
    gz = lunar.getDayInGanZhi()
    gan, zhi = gz[0], gz[1]
    return {"ganzhi": gz, "gan": gan, "zhi": zhi,
            "gan_wx": GAN_WUXING[gan], "zhi_wx": ZHI_WUXING[zhi]}


def _matches(day: dict, wx: str) -> bool:
    """日辰天干或地支当值某五行（干支同权，据《先天卦定应期》：乾兑应庚辛及申金之日）。"""
    return day["gan_wx"] == wx or day["zhi_wx"] == wx


def _day_wangxiang(day: dict, month_wx: str) -> tuple:
    """日辰主气（地支）相对月令的旺相休囚死。"""
    return shiwang_liunian(day["zhi_wx"], month_wx)


def date_table(final_R: str, F, J, T0, month_wx: str, tier: str,
               start_date: _date = None, n_days: int = None) -> dict:
    """
    未来 N 天宜忌日期表。final_R＝改方后的处方五行（执行口径）；tier 决定窗口天数
    （S=7 / M=14 / L=30，来自 weights.yaml）。start_date 仅测试用，缺省今天。
    """
    F = [f for f in (F or []) if f]
    J = [j for j in (J or []) if j]
    T0 = [t for t in (T0 or []) if t]
    start = start_date or datetime.now().date()
    if n_days is None:
        n_days = int(ZERI_DAYS.get(tier, ZERI_DAYS["S"]))
    t_active = tiao_active(T0, month_wx)

    days = []
    for i in range(n_days):
        d = start + timedelta(days=i)
        day = _day_pillar(d)
        state, _w = _day_wangxiang(day, month_wx)
        day_wx = day["zhi_wx"]
        strong = state in ZERI_YI_STATES          # 旺相＝卦气旺相之日
        elements = (day["gan_wx"], day["zhi_wx"])  # 干支同权（先天卦定应期：庚辛与申酉同为金之日）
        reasons, yiji = [], "平"

        def mark(level, reason, src):
            reasons.append({"reason": reason, "src": src})
            nonlocal yiji
            if level == "忌":
                yiji = "忌"
            elif level == "宜" and yiji != "忌":
                yiji = "宜"

        # —— 忌 ——
        matched_j = [e for e in dict.fromkeys(elements) if e in J]
        if matched_j:
            j_states = [shiwang_liunian(e, month_wx)[0] for e in matched_j]
            if all(s in ("囚", "死") for s in j_states):
                mark("平", f"忌神{'、'.join(matched_j)}当值但处{'、'.join(j_states)}地，失令不足为患", SRC_SHUAIWANG)
            else:
                mark("忌", f"忌神{'、'.join(matched_j)}当值（{day['ganzhi']}日），忌神得地", SRC_SHUAIWANG)
        if any(SHENG[e] in J for e in elements):
            pairs = [(e, SHENG[e]) for e in dict.fromkeys(elements) if SHENG[e] in J]
            mark("忌", "日辰" + "、".join(f"{e}生忌神{k}" for e, k in pairs) + "，间接资敌", SRC_SHUAIWANG)
        if any(KE[e] in F for e in elements):
            pairs = [(e, KE[e]) for e in dict.fromkeys(elements) if KE[e] in F]
            mark("忌", "日辰" + "、".join(f"{e}克喜用{k}" for e, k in pairs) + "，喜用受制", SRC_SHUAIWANG)
        if t_active:
            g = grade_T(day_wx, T0[0])
            if g["net"] == "逆":
                mark("忌", f"日辰{day_wx}与转急调候{T0[0]}逆调", SRC_SHUAIWANG)
            else:
                mark("宜", f"日辰{day_wx}与转急调候{T0[0]}同调", SRC_SHUAIWANG)

        # —— 宜（应期日：处方/喜用当值且卦气旺相） ——
        if strong:
            if _matches(day, final_R):
                mark("宜", f"处方{final_R}当值且卦气{state}，应期之日", SRC_YINGQI)
            elif any(SHENG[e] == final_R for e in elements):
                mark("宜", f"日辰生处方{final_R}且卦气{state}", SRC_YINGQI)
            elif any(_matches(day, f) for f in F):
                mark("宜", f"喜用{day_wx}当值且卦气{state}", SRC_YINGQI)
            elif any(SHENG[e] in F for e in elements):
                pairs = [(e, SHENG[e]) for e in dict.fromkeys(elements) if SHENG[e] in F]
                mark("宜", "日辰" + "、".join(f"{e}生喜用{k}" for e, k in pairs) + f"且卦气{state}", SRC_YINGQI)
        # 日克忌神 → 制忌之日（不论旺衰）
        if any(KE[e] in J for e in elements):
            pairs = [(e, KE[e]) for e in dict.fromkeys(elements) if KE[e] in J]
            mark("宜", "日辰" + "、".join(f"{e}克忌神{k}" for e, k in pairs) + "，制忌之日", SRC_SHUAIWANG)

        if not reasons:
            if _matches(day, final_R) or any(_matches(day, f) for f in F):
                reasons.append({"reason": f"处方/喜用之五行当值但卦气{state}，未达旺相应期，作平日", "src": SRC_YINGQI})
            else:
                reasons.append({"reason": f"日辰{day_wx}处{state}地，与处方/喜忌无直接关涉", "src": SRC_SHUAIWANG})

        days.append({
            "date": d.isoformat(), "ganzhi": day["ganzhi"],
            "gan_wx": day["gan_wx"], "zhi_wx": day["zhi_wx"], "day_wx": day_wx,
            "state": state, "yiji": yiji,
            "reasons": reasons,
        })

    return {
        "tier": tier, "n_days": n_days, "start": start.isoformat(),
        "days": days,
        "best": [x["date"] for x in days if x["yiji"] == "宜"],
        "avoid": [x["date"] for x in days if x["yiji"] == "忌"],
        "src": [SRC_YINGQI, SRC_SHUAIWANG],
    }
