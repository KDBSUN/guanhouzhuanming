# -*- coding: utf-8 -*-
"""
裁决引擎回归（wuxing_relation.adjudicate）
==========================================
判定次序（调候升格改造后）：
  1. R=J/R生J → 红·强制改方
  2. 调候转急 且 R逆T → 红·改方或降级
  2b. 调候转急 且 R同调T → 收集 t_green
  3. R克F → 红黄·改方
  4. R=F/R生F → 绿（t_green 一并附 加成）
  4b. 未中喜用 但 t_green → 升格为绿
  5. 其余 → 黄·限时放行
调候活性（tiao_active）：月令生T或比和 → 休眠；月令克/泄/耗T → 转急。
"""
import pytest

from wuxing_relation import adjudicate, tiao_active, redirect, grade_J, grade_F, grade_T


# ---- 调候转急（T0=火，月令水克火 → 转急）下的五条主路径 ----
T0, M = ["火"], "水"

def test_tiao_active_basic():
    assert tiao_active(["火"], "水") is True      # 月令克调候 → 转急
    assert tiao_active(["火"], "木") is False     # 月令生调候 → 休眠
    assert tiao_active(["火"], "火") is False     # 月令比和 → 休眠
    assert tiao_active([], "水") is False         # 无调候 → 恒不转急

def test_rule1_jishen_beats_tiao():
    # 忌神硬约束优先于一切：R=土 与 T0=火 本是同调，但 R 助忌 J=[土] → 红
    v = adjudicate("土", F=["金"], J=["土"], T0=T0, month_wx=M)
    assert v["level"] == "red" and v["gate"] == "block"
    assert v["tiao_active"] is True

def test_rule2_r_ke_tiao_red():
    # R=水 与 T0=火 相克（我克→逆调）→ 红
    v = adjudicate("水", F=["金"], J=[], T0=T0, month_wx=M)
    assert v["level"] == "red" and v["gate"] == "block"
    assert v["decision"] == "改方或降级：处方与调候相克"

def test_rule2b_tiao_boost_on_green():
    # R=火 即调候本体，又直中喜用 F=[火] → 绿 + 调候加成
    v = adjudicate("火", F=["火"], J=[], T0=T0, month_wx=M)
    assert v["level"] == "green" and v["gate"] == "pass"
    assert "调候加成" in v["decision"]

def test_rule4b_upgrade_green():
    # R=火 未直中喜用（F=[木]，木生火→处方被喜用反生，中档不中不逆），
    # 但与转急调候同调 → 仍按调候优先升格放行（规则4合并 t_green 统一裁决）
    v = adjudicate("火", F=["木"], J=[], T0=T0, month_wx=M)
    assert v["level"] == "green" and v["gate"] == "pass"
    assert "调候加成" in v["decision"]

def test_rule3_ke_f_beats_boost():
    # R=火 克喜用 F=[金]（犯喜）→ 红黄，调候加成救不了
    v = adjudicate("火", F=["金"], J=[], T0=T0, month_wx=M)
    assert v["level"] == "red_yellow" and v["gate"] == "block"
    assert v["decision"] == "改方：处方攻击扶抑喜用"


# ---- 无调候时的基础裁决与历史回归 ----

def test_basic_yellow_f_sheng_r():
    # 事体木、喜水（水生木）→ 处方被喜用引泄 → 中·黄
    v = adjudicate("木", F=["水"], J=["金"], T0=None, month_wx="辰")
    assert v["net"] == "平" and v["level"] == "yellow" and v["gate"] == "limited"

def test_basic_red_r_sheng_j():
    # R=火 生忌神 J=[土] → 红·强制改方
    v = adjudicate("火", F=["金"], J=["土"], T0=None, month_wx="午")
    assert v["level"] == "red" and v["gate"] == "block"

def test_basic_green_r_sheng_f():
    # R=水 生喜用 F=[木] → 绿·放行
    v = adjudicate("水", F=["木"], J=["土"], T0=None, month_wx="子")
    assert v["level"] == "green" and v["gate"] == "pass"

def test_no_baseline_limited():
    # 无命局参考系 → 黄·限时放行，附"无命局校验"说明
    v = adjudicate("木", F=[], J=[], T0=None, month_wx="寅")
    assert v["level"] == "yellow" and v["hits"][0]["ref"] is None

def test_redirect_for_jishen():
    # R 喂忌神 → redirect 给出克忌者
    v = adjudicate("火", F=["金"], J=["土"], T0=None, month_wx="午")
    r2, why = redirect("火", v, ["金"], ["土"], None)
    assert r2 == "木" and "制忌" in why


# ---- 三重过滤与失败语义（2026-10-06 H3：改方不得生助任何忌神、不得克任何喜用、
#      调候转急时不得逆调候；候选全灭 → 空改方＋「待岁运通关之地」，不以喂忌之方充数） ----

def test_redirect_f_branch_keeps_tongguan():
    """纯犯喜（无忌神命中）：R=火克喜用金 → 通关字土；土不喂忌神（土克水为制忌）→ 通过。"""
    v = adjudicate("火", F=["金"], J=["水"], T0=None, month_wx="火")
    assert v["gate"] == "block"
    r2, why = redirect("火", v, ["金"], ["水"], None)
    assert r2 == "土" and "通关" in why


def test_redirect_tiao_candidate_that_is_jishen_returns_empty():
    """改方=调候字，但调候字本身是忌神（人工构造——引擎 H5 已从源头消除此情形，
    此处钉住 redirect 自身的防线）：候选【火】生助忌神【火】→ 全灭 → 空改方＋岁运说明。"""
    v = adjudicate("水", F=[], J=["火"], T0=["火"], month_wx="水")
    assert v["gate"] == "block"
    r2, why = redirect("水", v, [], ["火"], ["火"])
    assert r2 == "" and "岁运" in why


def test_redirect_multi_jishen_drops_feeding_candidate():
    """多忌神：第一个候选（克火者水）本身即忌神（J 含水）→ 过滤掉，改试下一候选
    （生扶喜用者土）→ 通过。"""
    v = adjudicate("木", F=["金"], J=["火", "水"], T0=None, month_wx="火")
    r2, why = redirect("木", v, ["金"], ["火", "水"], None)
    assert r2 == "土" and "通关" in why


def test_redirect_no_solution_returns_empty():
    """三重过滤后候选全灭 → 空改方＋岁运说明。
    书证：《子平真诠·论用神》「如原局无通关之神，亦必运程弥其缺憾」；
    同书「病药为用，如原局无去病之神，必须运程弥其缺憾，方得发展」。
    构造：R=水生忌神木；克木者金∈J、克金者火∈J、克火者水又生木——三忌神把
    制忌一路包圆，其余候选（通关/生扶）无喜用可依 → 无解。"""
    v = adjudicate("水", F=[], J=["木", "金", "火"], T0=None, month_wx="水")
    assert v["gate"] == "block"
    r2, why = redirect("水", v, [], ["木", "金", "火"], None)
    assert r2 == ""
    assert "岁运" in why and "通关" in why


def test_redirect_always_satisfies_filters():
    """属性测试：常见 (F,J,T0) 组合 × 5 处方，凡给出改方者必过三重过滤。"""
    combos = [(["金"], ["土"], None), (["土", "金"], ["火"], None), (["金"], ["火", "水"], None),
              (["木"], [], ["火"]), (["木"], ["火"], ["火"]), (["金"], ["土", "木"], None)]
    for F, J, T0 in combos:
        for R in "木火土金水":
            v = adjudicate(R, F, J, T0, month_wx="水")
            if v["gate"] != "block":
                continue
            r2, why = redirect(R, v, F, J, T0)
            if not r2:
                continue
            assert r2 in "木火土金水"
            for j in J:
                assert grade_J(r2, j)["net"] != "逆", (R, F, J, T0, r2)
            for f in F:
                assert grade_F(r2, f)["net"] != "逆", (R, F, J, T0, r2)
            if v.get("tiao_active"):
                for t in T0:
                    assert grade_T(r2, t)["net"] != "逆", (R, F, J, T0, r2)
