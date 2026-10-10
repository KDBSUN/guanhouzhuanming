# -*- coding: utf-8 -*-
"""
格局判定回归（滴天髓·从象/化象/专旺 + 穷通宝鉴调候）
=====================================================
- 10 个合成四柱（纯函数路径 build_xiji，不依赖排盘时钟）
- 2 个真实命例（完整管线 build_bazi_paipan，防回归）
期望值均按 2025 年书目改造后的引擎实测固化；改动格局规则导致失败时，
先对照《滴天髓》原文判断规则正误，再决定改引擎还是改期望。
"""
import pytest

from tests.conftest import mk_xiji
from bazi_engine import build_bazi_paipan

# (名称, 天干, 地支, from_ge 包含, ge_quality, F, J)
SYNTHETIC = [
    ("真从杀：乙生酉月，杀星当令乘势，四柱无一印比", "辛辛乙辛", "巳酉酉巳",
     "从杀格", "真从", ["金", "土"], ["木", "水", "火"]),
    ("真从财：甲生巳月，财星秉令，食伤生财一路顺行", "戊己甲戊", "戌巳戌午",
     "从财格", "真从", ["土", "火", "金"], ["木", "水"]),
    ("从儿：甲生午月，火当令食伤成方，儿又生儿", "丙丙甲丙", "午午午巳",
     "从儿格", "真从", ["土", "火"], ["水", "金"]),
    ("专旺曲直：甲木生寅月，支全寅亥，无金克", "甲甲甲癸", "寅寅寅亥",
     "曲直格", "真从", ["木", "水"], ["金", "土"]),
    ("假从杀：时透壬印受制，从之不纯", "辛辛乙壬", "巳酉酉午",
     "从杀格", "假从", ["金", "土"], ["木", "水", "火"]),
    ("假专旺：时逢庚金逆势，真中有假", "甲甲甲庚", "寅寅寅寅",
     "曲直格", "假从", ["木", "水"], ["金", "土"]),
    ("化气：丁壬合木生于寅卯，化神得令", "甲丁壬己", "寅卯午未",
     "化气格", "真化", ["水", "木"], ["金", "水"]),
    ("从势：财官食伤交战，日主无根弃命从势", "甲己癸丙", "寅未卯午",
     "从势格", "真从", ["土", "火"], ["水", "金", "木"]),
]

NO_HUA = [
    # 化神不真：甲己合而生于寅（木旺土囚），合而不化，仅作标记不入格
    ("甲丁壬戊", "寅丑子寅"),
    # 争合：丁日主三丁争一壬，妒合不化，转按财多身弱入从财
    ("丁丁壬丁", "卯卯寅未"),
]

REAL_REGRESSION = [
    # 2009-09-04 15:34 男：身弱，扶抑 F=[金,水]，调候首味戊（土）原与忌方相重。
    # 2026-10-06 H5 裁定「调候为急，权而用之」（《子平真诠·论用神配气候得失》）：
    # 土移出忌神表（J 变空）、T0 保持 [土]，adjust_marks 带「与扶抑忌方相重…移出忌神表」。
    (2009, 9, 4, 15, 34, "身弱", ["金", "水"], [], ["土"], None),
    # 1990-05-15 14:30 男：极弱但不从（印比虽少而受生有路），F=[土,金] J=[火] T0=[水]
    # （表 四月庚：壬、戊、丙 → 首味壬=水，与旧方向法一致）
    (1990, 5, 15, 14, 30, "极弱", ["土", "金"], ["火"], ["水"], None),
]


@pytest.mark.parametrize("name,gans,zhis,ge,quality,F,J", SYNTHETIC,
                         ids=[c[0] for c in SYNTHETIC])
def test_geju_synthetic(name, gans, zhis, ge, quality, F, J):
    m = mk_xiji(gans, zhis)["mingju"]
    assert ge in m["from_ge"], f"{name}: from_ge={m['from_ge']!r}"
    assert m["ge_quality"] == quality, f"{name}: ge_quality={m['ge_quality']!r}"
    assert m["F"] == F, f"{name}: F={m['F']}"
    assert m["J"] == J, f"{name}: J={m['J']}"


@pytest.mark.parametrize("gans,zhis", NO_HUA, ids=["合而不化", "争合"])
def test_he_er_bu_hua(gans, zhis):
    m = mk_xiji(gans, zhis)["mingju"]
    assert "化气" not in (m["from_ge"] or ""), f"不应成化：{m['from_ge']!r}"
    # 合而不化 → 回扶抑；争合 → 财多身弱入从财
    if gans == "丁丁壬丁":
        assert "从财" in m["from_ge"] and m["ge_quality"] == "真从"
        assert m["F"] == ["火", "木"] and m["J"] == ["水", "金", "土"]


@pytest.mark.parametrize("y,mo,d,h,mi,tier,F,J,T0,ge", REAL_REGRESSION,
                         ids=["2009-09-04", "1990-05-15"])
def test_geju_real_regression(y, mo, d, h, mi, tier, F, J, T0, ge):
    m = build_bazi_paipan(y, mo, d, h, mi, gender=1)["xiji"]["mingju"]
    assert m["tier"] == tier, f"tier={m['tier']!r}"
    assert m["F"] == F, f"F={m['F']}"
    assert m["J"] == J, f"J={m['J']}"
    assert m["T0"] == T0, f"T0={m['T0']}"
    assert m["from_ge"] == ge, f"from_ge={m['from_ge']!r}"


def test_h5_tiaohou_wins_over_jishen_with_marks():
    """H5 回归（2026-10-06 裁定）：调候字∈忌神（非从格、非火土旺极）→ 权而用之——
    移出 J、保留 T0、留标注（含书证「调候为急，权而用之也」与「已移出忌神表」）。"""
    data = build_bazi_paipan(2009, 9, 4, 15, 34, gender=1)
    xiji = data["xiji"]
    assert xiji["mingju"]["J"] == [] and xiji["mingju"]["T0"] == ["土"]
    marks = "；".join(xiji["adjust_marks"])
    assert "与扶抑忌方相重" in marks
    assert "权而用之" in marks
    assert "移出忌神表" in marks
