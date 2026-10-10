# -*- coding: utf-8 -*-
"""
岁运层回归（liunian.py）
========================
接入原则（据岁运层讨论定案）：
  1. 流年被月令称重（旺相休囚死），囚死近乎不计；
  2. 小权重参与"引动"检查：引动忌神→降级、生扶喜用→升格/加成；
  3. 不参与改方：绝不把 gate 推到 block，绝不改处方 R；
  4. 从格行运按《滴天髓》判定表查（从象/假从/从儿/化象四章）。
"""
import pytest

from liunian import (shiwang_liunian, shishen_role, congge_xingyun,
                     liunian_overlay, current_liunian)


# ---- 流年过秤（旺相休囚死） ----

@pytest.mark.parametrize("wx,month,expect", [
    ("火", "火", ("旺", 1.0)),   # 当令者旺
    ("土", "火", ("相", 0.8)),   # 令生者相（火生土）
    ("木", "火", ("休", 0.5)),   # 生令者休（木生火）
    ("水", "火", ("囚", 0.3)),   # 克令者囚（水克火）
    ("金", "火", ("死", 0.2)),   # 令克者死（火克金）
])
def test_shiwang(wx, month, expect):
    assert shiwang_liunian(wx, month) == expect


def test_shishen_role():
    assert shishen_role("木", "水") == "印"
    assert shishen_role("木", "木") == "比劫"
    assert shishen_role("木", "火") == "食伤"
    assert shishen_role("木", "土") == "财"
    assert shishen_role("木", "金") == "官杀"


# ---- 从格行运判定表（《滴天髓》三章书证） ----

def test_congge_conger():
    # 从儿最忌印、次忌官；财最吉（儿又生孙）
    assert congge_xingyun("从儿格", "真从", "木", "水")["verdict"] == "bad"
    assert "最忌印运" in congge_xingyun("从儿格", "真从", "木", "水")["reason"]
    assert congge_xingyun("从儿格", "真从", "木", "金")["verdict"] == "bad"
    assert congge_xingyun("从儿格", "真从", "木", "土")["verdict"] == "good"
    assert congge_xingyun("从儿格", "真从", "木", "火")["verdict"] == "good"
    assert congge_xingyun("从儿格", "真从", "木", "木")["verdict"] == "good"

def test_congge_concai_guisha():
    # 从财行官杀运必贵（《假从》）；比劫分争凶
    assert congge_xingyun("从财格", "真从", "木", "金")["verdict"] == "good"
    assert "必贵" in congge_xingyun("从财格", "真从", "木", "金")["reason"]
    assert congge_xingyun("从财格", "真从", "木", "木")["verdict"] == "bad"

def test_congge_congsha_zhuanwang():
    # 从杀（金日主）：食伤（水）制杀破从；财（木）生杀吉
    assert congge_xingyun("从杀格（弃命从杀）", "真从", "金", "水")["verdict"] == "bad"
    assert congge_xingyun("从杀格（弃命从杀）", "真从", "金", "木")["verdict"] == "good"
    assert congge_xingyun("从杀格（弃命从杀）", "真从", "金", "火")["verdict"] == "good"
    # 专旺：官杀犯旺、比劫顺
    assert congge_xingyun("专旺格（曲直格）", "真从", "木", "金")["verdict"] == "bad"
    assert "犯旺" in congge_xingyun("专旺格（曲直格）", "真从", "木", "金")["reason"]
    assert congge_xingyun("专旺格（曲直格）", "真从", "木", "木")["verdict"] == "good"

def test_congge_congshi():
    assert congge_xingyun("从势格", "真从", "木", "土")["verdict"] == "good"
    assert congge_xingyun("从势格", "真从", "木", "水")["verdict"] == "bad"

def test_congge_jiacong():
    # 假从：假行真运——官杀/食伤/财皆吉，印比助假凶
    assert congge_xingyun("从财格", "假从", "木", "金")["verdict"] == "good"
    assert congge_xingyun("从财格", "假从", "木", "火")["verdict"] == "good"
    assert congge_xingyun("从财格", "假从", "木", "水")["verdict"] == "bad"
    # 假专旺：逆神与生逆者警示
    assert congge_xingyun("专旺格（曲直格）", "假从", "木", "金")["verdict"] == "warn"
    assert congge_xingyun("专旺格（曲直格）", "假从", "木", "木")["verdict"] == "good"

def test_congge_huaqi():
    # 化气格（壬丁化木）：化神木不足（F 无泄神火）→ 生助水吉、克化神金凶
    d = congge_xingyun("化气格（壬丁化木）", "真化", "木", "水", F=["水", "木"])
    assert d["verdict"] == "good" and "宜生助" in d["reason"]
    d2 = congge_xingyun("化气格（壬丁化木）", "真化", "木", "金", F=["水", "木"])
    assert d2["verdict"] == "bad"
    # 有余（F 含泄神火）→ 泄吉、再生则太过
    d3 = congge_xingyun("化气格（壬丁化木）", "真化", "木", "火", F=["火", "木"])
    assert d3["verdict"] == "good"
    d4 = congge_xingyun("化气格（壬丁化木）", "真化", "木", "水", F=["火", "木"])
    assert d4["verdict"] == "warn"

def test_congge_none_for_normal():
    assert congge_xingyun(None, "", "木", "水") is None
    assert congge_xingyun("", "", "木", "水") is None


# ---- 叠加（引动检查：降级/升格/背景注记） ----

def _verdict(level="green", gate="pass", net="顺"):
    return {"net": net, "level": level, "gate": gate, "decision": "放行", "hits": [], "tiao_active": False}


def test_overlay_drag_downgrades_green():
    # 流年土（火月相地）当值引动忌神 J=[土] → 绿档降为限时放行
    base = {"F": ["金"], "J": ["土"], "T0": [], "from_ge": None, "ge_quality": "", "day_master_wx": "木"}
    ln = {"ganzhi": "己丑", "gan": "己", "zhi": "丑", "wx": "土"}
    v, info = liunian_overlay(ln, "火", base, _verdict())
    assert info["effect"] == "drag"
    assert v["level"] == "yellow" and v["gate"] == "limited"
    assert "绿档降为限时放行" in v["decision"]
    assert v["gate"] != "block"          # 绝不设拦截

def test_overlay_indirect_drag():
    # 流年金生忌神水（间接资敌）→ drag
    base = {"F": ["木"], "J": ["水"], "T0": [], "from_ge": None, "day_master_wx": "木"}
    ln = {"ganzhi": "甲申", "wx": "金"}
    v, info = liunian_overlay(ln, "水", base, _verdict())
    assert info["effect"] == "drag" and v["level"] == "yellow"

def test_overlay_boost_upgrades_yellow():
    # 流年金（相）生扶喜用 F=[金] → 黄档升格放行
    base = {"F": ["金"], "J": ["木"], "T0": [], "from_ge": None, "day_master_wx": "木"}
    ln = {"ganzhi": "乙丑", "wx": "金"}
    v, info = liunian_overlay(ln, "土", base, _verdict("yellow", "limited", "平"))
    assert info["effect"] == "boost"
    assert v["level"] == "green" and v["gate"] == "pass"
    assert "升格放行" in v["decision"]

def test_overlay_weak_year_note_only():
    # 流年金在寅月处囚地 → 失令近乎不计，仅注记，档位不动
    base = {"F": [], "J": ["木"], "T0": [], "from_ge": None, "day_master_wx": "木"}
    ln = {"ganzhi": "癸卯", "wx": "金"}
    v, info = liunian_overlay(ln, "木", base, _verdict())
    assert info["effective"] is False and info["effect"] == "none"
    assert v["level"] == "green" and v["gate"] == "pass"
    assert "失令近乎不计" in info["notes"][0]

def test_overlay_congge_bad_drag():
    # 从儿格行印运（水，相地）→ 犯格降级
    base = {"F": ["土", "火"], "J": ["水", "金"], "T0": [], "from_ge": "从儿格",
            "ge_quality": "真从", "day_master_wx": "木"}
    ln = {"ganzhi": "丙子", "wx": "水"}
    v, info = liunian_overlay(ln, "金", base, _verdict())
    assert info["from_ge_table"]["verdict"] == "bad"
    assert info["effect"] == "drag" and v["level"] == "yellow"
    assert any("最忌印运" in n for n in info["notes"])

def test_overlay_never_changes_r_or_blocks():
    # 任何叠加都不产生 block（block 只属于主裁决）
    base = {"F": [], "J": ["土"], "T0": [], "from_ge": None, "day_master_wx": "木"}
    ln = {"ganzhi": "己丑", "wx": "土"}
    v, _ = liunian_overlay(ln, "火", base, _verdict("green", "pass", "顺"))
    assert v["gate"] in ("pass", "limited")

def test_current_liunian_shape():
    ln = current_liunian()
    assert len(ln["ganzhi"]) == 2 and ln["wx"] in ("金", "木", "水", "火", "土")
