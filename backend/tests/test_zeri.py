# -*- coding: utf-8 -*-
"""
确定性择日引擎回归（zeri.py）
============================
书证锚点：
  《梅花易数·先天卦定应期》："定事应之期，则取之卦气……应庚辛及申金之日"（干支同权）；
  《梅花易数·求名占》："根据生体之卦卦气的旺相时间推断"（应期日须旺相）；
  《梅花易数·心易衰旺诀》："生扶宜旺，克体宜衰"（忌神失令不足为患）。
全部为序关系判定，不依赖数值权重。
"""
from datetime import date

from zeri import date_table


def _days_by(dt, pred):
    return [d for d in dt["days"] if pred(d)]


def test_yi_days_are_matched_and_strong():
    # 处方土、无喜忌，土月：凡天干或地支属土之日（卦气旺）→ 宜
    dt = date_table("土", [], [], [], "土", "S", start_date=date(2026, 2, 10), n_days=14)
    yi = _days_by(dt, lambda d: d["yiji"] == "宜")
    assert yi, "土月应有处方当值且卦气旺的宜日"
    for d in yi:
        assert d["gan_wx"] == "土" or d["zhi_wx"] == "土"      # 干支同权
        assert d["state"] == "旺"                              # 应期日须旺相
    assert dt["avoid"] == []                                   # 无忌神无克喜用 → 无忌日

def test_ji_shiling_downgrades_to_ping():
    # 忌神火、水月（火处死地）：火当值但失令 → 平注记，不得判忌"得地"
    dt = date_table("土", [], ["火"], [], "水", "S", start_date=date(2026, 2, 10), n_days=30)
    for d in _days_by(dt, lambda d: d["gan_wx"] == "火" or d["zhi_wx"] == "火"):
        reasons = " / ".join(r["reason"] for r in d["reasons"])
        assert "失令不足为患" in reasons or "克喜用" in reasons  # 失令降平，但克喜用仍忌

def test_indirect_aid_and_clash():
    # 木生火（生忌神）→ 忌；金日克木? 用 克喜用：F=[金]，火日克金 → 忌
    dt = date_table("土", ["金"], ["火"], [], "金", "S", start_date=date(2026, 2, 10), n_days=30)
    sheng_ji = [d for d in dt["days"] if any("生忌神" in r["reason"] for r in d["reasons"])]
    assert sheng_ji, "应有木日生忌神火的间接资敌判例"
    for d in sheng_ji:
        assert d["yiji"] == "忌"
    # 火日克喜用金 → 忌（克喜用不受失令豁免，保守从严）
    ke_xi = [d for d in dt["days"] if d["gan_wx"] == "火" or d["zhi_wx"] == "火"]
    assert ke_xi and all(d["yiji"] == "忌" for d in ke_xi)

def test_zhi_ji_day_is_yi():
    # 日克忌神 → 制忌之日（宜）；但同日若另犯资敌/当值，忌优先级更高（保守从严）
    dt = date_table("土", [], ["木"], [], "金", "S", start_date=date(2026, 2, 10), n_days=30)
    zhi = [d for d in dt["days"] if any("制忌" in r["reason"] for r in d["reasons"])]
    assert zhi, "金月应有金日克忌神木的制忌判例"
    for d in zhi:
        if d["yiji"] == "宜":
            continue
        assert d["yiji"] == "忌"
        # 忌的来源只能是当值得地或间接资敌（失令平不抬级）
        assert any(("生忌神" in r["reason"]) or ("忌神" in r["reason"] and "失令" not in r["reason"])
                   for r in d["reasons"])

def test_window_by_tier():
    """档位→窗口天数（weights.yaml 的 zeri_days）。

    M 由 14 改为 30（2026-09-18，站长定）：14 天覆盖不到"本月内要办的事"——
    实测中用户要谈的日子在第 20 天、落在窗外，于是 AI 只能自己推日期，并推错了一个。
    窗口是"给 AI 多少依据"，不是"给用户看多长建议"，故宁宽勿窄。
    注意 M 与 L 现同为 30，两者差别只剩 AI 输出层数（M 两层 / L 三层）。
    """
    for tier, n in (("S", 7), ("M", 30), ("L", 30)):
        dt = date_table("土", [], [], [], "土", tier, start_date=date(2026, 2, 10))
        assert dt["n_days"] == n and len(dt["days"]) == n

def test_reasons_always_present_and_dated():
    dt = date_table("土", [], [], [], "土", "S", start_date=date(2026, 2, 10), n_days=7)
    for d in dt["days"]:
        assert d["reasons"] and d["ganzhi"] and d["date"].startswith("2026-02")
        for r in d["reasons"]:
            assert r["src"].startswith("梅花易数")
