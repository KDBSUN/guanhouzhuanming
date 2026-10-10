# -*- coding: utf-8 -*-
"""五行流动判定表回归（wuxing_flow.py）——整表结构 + 状态分档 + 关键格 + 通关行 + 无档案路径"""
from wuxing_flow import (classify_state, flow_plan, TABLE, MOTHER, KEME, SHENG, KE, WX_ORDER,
                         STATES, GRADE_ORDER)

RELS = ("进气", "出水", "我克", "克我")


def test_every_table_grade_is_declared():
    """不变式：TABLE 里出现的每个档位都必须在 GRADE_ORDER 里声明。

    为什么单列一条：前端配色表（MingjuCheckBar.FLOW_GRADE_COLOR）与后端的
    「大忌/忌清单」都按档位名取值，**表里多一个没声明的档位，它就会静默掉色、
    静默漏进 AI 材料**——「忌多」正是这样漏了三个月（2026-09-23 规则命中审计
    tools/audit_rule_hits.py 查出：3 处「忌多」不在声明枚举内，前端取不到色值退回灰色，
    看起来像「无碍」，AI 也拿不到"别再添这一味"的约束）。此测试钉死这类漏声明。
    """
    seen = set()
    for wx in WX_ORDER:
        for st in STATES:
            for rel in RELS:
                seen.add(TABLE[wx][st][rel][0])
    undeclared = sorted(seen - set(GRADE_ORDER))
    assert not undeclared, "判定表用了未声明的档位：%s" % undeclared
    assert "忌多" in GRADE_ORDER, "「忌多」必须留在声明枚举里（前端配色与禁清单都按名取值）"


def mj(tally, month_wx="", from_ge="", effective_wx=""):
    return {"wuxing_tally": tally, "month_wx": month_wx,
            "from_ge": from_ge, "effective_wx": effective_wx}


# ---------- 状态分档 ----------

def test_state_weak_metal():
    state, _ = classify_state("金", mj({"金": 1, "木": 2, "火": 2, "土": 1, "水": 2}, month_wx="火"))
    assert state == "弱"


def test_state_missing_is_jiruo():
    state, note = classify_state("金", mj({"木": 3, "火": 2, "土": 2, "水": 1}))
    assert state == "弱极"
    assert "虚不受补" in note


def test_state_huo_wang_mid():
    state, _ = classify_state("火", mj({"火": 4, "土": 1, "木": 1, "金": 1, "水": 1}, month_wx="火"))
    assert state == "中和偏旺"


def test_state_zhuanwang_ge():
    state, _ = classify_state("金", mj({"金": 5, "土": 2, "水": 1}, month_wx="金",
                                       from_ge="专旺格（从革格）", effective_wx="金"))
    assert state == "旺极(从格)"


def test_state_hua_ge_effective():
    state, _ = classify_state("土", mj({"土": 4, "火": 2, "木": 1, "水": 1}, month_wx="土",
                                       from_ge="化气格（甲己化土）", effective_wx="土"))
    assert state == "旺极(从格)"


# ---------- 展示结构：强弱四档全出（命中行标 active）+ 通关行 ----------

def test_shows_all_state_rows_with_one_active():
    """丙·3①：强弱四档全出，只有命中那档标 active。

    只给命中行时，档位一旦判偏，整行建议跟着偏，而用户手上没有可对照的东西——
    他没法说"我觉得我是中和偏旺，你看那行是不是更对"。四档全出才给得了他这个对照。
    """
    plan = flow_plan("金", mj({"金": 1, "木": 2, "火": 2, "土": 1, "水": 2}, month_wx="火"))
    assert plan["state"] == "弱"
    assert set(plan["header"].keys()) == set(RELS)
    assert plan["header"]["进气"] == "进气（土·他生）"
    assert plan["header"]["出水"] == "出水（水·自生）"
    assert plan["header"]["我克"] == "我克（木·自克）"
    assert plan["header"]["克我"] == "克我（火·他克）"
    # 四档全在（顺序即 STATES）+ 末尾通关行
    assert [r["state"] for r in plan["rows"]] == list(STATES) + ["局中交战"]
    active = [r for r in plan["rows"] if r["active"]]
    assert len(active) == 1 and active[0]["state"] == "弱"
    # 通关行：出水列给通关，余列为 None（前端渲染"—"）
    tg = plan["rows"][-1]
    assert tg["cells"]["进气"] is None and tg["cells"]["我克"] is None
    assert "通关" in tg["cells"]["出水"]["note"]
    # 阴阳细分：该五行一对天干的十干体象（书证=滴天髓·论天干）
    assert [i["gan"] for i in plan["yinyang"]["items"]] == ["庚", "辛"]
    assert all(i["tags"] and i["tixiang"] for i in plan["yinyang"]["items"])


def test_only_active_row_carries_edge_state_modifiers():
    """边态（乘侮／生害）**只挂命中档**，假档一行都不许带。

    它们是按这盘真实力量分布（ke_tally）算的，磨的是"你这一档的方向该加多少量"。
    挂到假设档上等于说"你若换一档，量级修正也是这个"——那是错的，
    且会让人误以为四行都是给他的断语（四行并排最容易被这么误读）。
    """
    plan = flow_plan("金", mj({"金": 1, "木": 2, "火": 2, "土": 1, "水": 2}, month_wx="火"))
    for r in plan["rows"]:
        for rel, c in (r["cells"] or {}).items():
            if c is None or r["state"] == "局中交战":
                continue
            if r["active"]:
                continue
            assert "chengwu" not in c, (r["state"], rel)
            assert "sheng_three" not in c, (r["state"], rel)
            assert "combined" not in c, (r["state"], rel)
            assert "conflict" not in c, (r["state"], rel)


def test_without_profile_no_state_rows():
    """无命局档案：不判强弱，一行强弱都不出，只留通关行。

    不是省字节——没有命局就连"我在哪一档"都不知道，这时摆四行假设
    等于让用户对着四个可能猜，那不是对照，是四个假答案。
    """
    plan = flow_plan("水", None)
    assert plan["state"] is None
    assert [r["state"] for r in plan["rows"]] == ["局中交战"]
    assert all(not r["active"] for r in plan["rows"])
    assert "未提供命局档案" in plan["state_note"]


# ---------- 各状态关键格（典籍条件规则） ----------

def test_ruojin_kewo_daji():
    """弱金：克我（火）大忌、我克（木）忌——《元理赋》金衰遇火销熔/木坚金缺"""
    plan = flow_plan("金", mj({"金": 1, "木": 2, "火": 2, "土": 1, "水": 2}, month_wx="火"))
    row = next(r for r in plan["rows"] if r["state"] == "弱")
    assert row["cells"]["克我"]["grade"] == "大忌"
    assert row["cells"]["我克"]["grade"] == "忌"
    assert row["cells"]["进气"]["grade"] == "宜少量"


def test_jijin_butu_gai_bilei():
    """弱极之金：虚不受补，进气改补同类（比劫）——穷通宝鉴"春金弱喜比劫不喜印生\""""
    plan = flow_plan("金", mj({"金": 0, "木": 2, "火": 2, "土": 2, "水": 2}))
    assert plan["state"] == "弱极"
    row = next(r for r in plan["rows"] if r["state"] == "弱极")
    assert row["cells"]["进气"]["grade"] == "改补同类"


def test_huowang_shui_jiji_shouxuan():
    """中和偏旺之火：克我（水）= 首选（水火既济，"水辅阳光非克也"）"""
    plan = flow_plan("火", mj({"火": 4, "土": 1, "木": 1, "金": 1, "水": 1}, month_wx="火"))
    row = next(r for r in plan["rows"] if r["state"] == "中和偏旺")
    assert row["cells"]["克我"]["grade"] == "首选"
    assert row["cells"]["克我"]["note"].startswith("水火既济")


def test_shuiwang_tu_difang_shouxuan():
    """中和偏旺之水：克我（土）= 首选（堤防）——"水流泛滥赖土克以提防\""""
    plan = flow_plan("水", mj({"水": 4, "金": 1, "木": 1, "火": 1, "土": 1}, month_wx="水"))
    row = next(r for r in plan["rows"] if r["state"] == "中和偏旺")
    assert row["cells"]["克我"]["grade"] == "首选"


def test_tuwang_mushu_jinxie():
    """中和偏旺之土：克我（木）疏土首选 + 出水（金）泄秀首选"""
    plan = flow_plan("土", mj({"土": 4, "火": 1, "木": 1, "金": 1, "水": 1}, month_wx="土"))
    row = next(r for r in plan["rows"] if r["state"] == "中和偏旺")
    assert row["cells"]["克我"]["grade"] == "首选"
    assert row["cells"]["出水"]["grade"] == "首选"


def test_wangji_jin_congge():
    """旺极(从革)：出水（水）专用、克我（火）大忌、进气（土）大忌"""
    plan = flow_plan("金", mj({"金": 5, "土": 2, "水": 1}, month_wx="金",
                              from_ge="专旺格（从革格）", effective_wx="金"))
    assert plan["state"] == "旺极(从格)"
    row = next(r for r in plan["rows"] if r["state"] == "旺极(从格)")
    assert row["cells"]["出水"]["grade"] == "专用"
    assert row["cells"]["克我"]["grade"] == "大忌"
    assert row["cells"]["进气"]["grade"] == "大忌"


def test_wangji_huo_yanshang_zhuanyong_tu():
    """旺极(炎上)：出水（土）专用（釜底抽薪）、克我（水）大忌（水激破格）"""
    plan = flow_plan("火", mj({"火": 5, "木": 2, "土": 1}, month_wx="火",
                              from_ge="专旺格（炎上格）", effective_wx="火"))
    row = next(r for r in plan["rows"] if r["state"] == "旺极(从格)")
    assert row["cells"]["出水"]["grade"] == "专用"
    assert row["cells"]["克我"]["grade"] == "大忌"


# ---------- 通关命中说明 ----------

def test_tongguan_jin_mu_zhan_qu_shui():
    """金木对峙（我克方向）→ 命中"添水通关"——子平真诠"金木相战，取水通关\""""
    plan = flow_plan("金", mj({"金": 2, "木": 2, "火": 1, "土": 2, "水": 1}, month_wx="金"))
    hits = [h for r in plan["rows"] for h in (r.get("hits") or [])]
    assert any("通关" in h and "水" in h for h in hits)


def test_tongguan_shui_huo_zhan_qu_mu():
    """水火对峙（克我方向）→ 命中"添木通关"——滴天髓"水火相战，必须有木\""""
    plan = flow_plan("火", mj({"火": 2, "水": 2, "木": 1, "土": 1, "金": 2}, month_wx="火"))
    hits = [h for r in plan["rows"] for h in (r.get("hits") or [])]
    assert any("通关" in h and "木" in h for h in hits)


def test_no_tongguan_without_duizhi():
    plan = flow_plan("金", mj({"金": 1, "木": 1, "火": 1, "土": 2, "水": 3}, month_wx="金"))
    hits = [h for r in plan["rows"] for h in (r.get("hits") or [])]
    assert hits == []


# ---------- 完整性与一致性 ----------

def test_all_wx_all_states_complete():
    for wx in WX_ORDER:
        for state in STATES:
            row = TABLE[wx][state]
            for rel in RELS:
                grade, note, src = row[rel]
                assert grade and note and src, (wx, state, rel)


def test_relation_mapping_consistent():
    for wx in WX_ORDER:
        assert SHENG[MOTHER[wx]] == wx      # 母生我
        assert KE[KEME[wx]] == wx           # 克我者克我
        assert KE[wx] != MOTHER[wx] and KEME[wx] != SHENG[wx]


def test_qualities_and_header_per_wx():
    for wx in WX_ORDER:
        plan = flow_plan(wx, None)
        assert plan["qualities"]
        assert plan["header"]["进气"].startswith("进气（")
