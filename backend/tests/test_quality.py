# -*- coding: utf-8 -*-
"""质地层 + 关系层回归（wuxing_quality.py）
第一批：十干体象三标签 / 十二支任氏寒暖表 / 燥湿 / 质地取舍（R1）
第二批：月令五态（旺相休囚死）/ 克三值化（乘侮）/ 支作用（冲合会）/ 干合（R2）
"""
from wuxing_quality import (stem_texture, branch_texture, month_state,
                            ke_triple, branch_actions, hidden_tally, stem_actions,
                            pick_flavor, FLAVOR_TABLE, _EXTRAP_META)


# ---------- 第一批·质地层 ----------

def test_stem_texture_all_ten():
    for g in "甲乙丙丁戊己庚辛壬癸":
        t = stem_texture(g)
        assert t["tags"] and t["yinyang"] in ("阳", "阴") and t["tixiang"], g


def test_stem_gan_shi_zaorun():
    """戊土高亢偏燥而喜润（水润物生火燥物病）；己土卑湿——《滴天髓·论天干》"""
    assert "喜润" in stem_texture("戊")["zao_shi"]
    assert stem_texture("己")["zao_shi"] == "湿"
    assert "卑湿" in stem_texture("己")["tixiang"]


def test_branch_texture_ren_table():
    """十二支寒暖：任铁樵表——子阳寒/午阳暖/亥阴寒/巳阴暖；《寒暖》章金水寒木火暖"""
    assert branch_texture("子")["han_nuan"] == "阳寒"
    assert branch_texture("午")["han_nuan"] == "阳暖"
    assert branch_texture("亥")["han_nuan"] == "阴寒"
    assert branch_texture("巳")["han_nuan"] == "阴暖"
    assert branch_texture("申")["han_nuan"] == "阳寒"


def test_branch_texture_zaoshi():
    """燥湿按载体分列（R7 收口）：湿/燥为书证赋值，歧异＝源间方向相反，条件性＝缺逐支条文"""
    assert branch_texture("辰")["zao_shi"].startswith("湿")
    assert branch_texture("丑")["zao_shi"].startswith("湿")
    assert branch_texture("戌")["zao_shi"].startswith("燥")
    assert branch_texture("未")["zao_shi"].startswith("燥")
    assert branch_texture("午")["zao_shi"] == "燥"
    assert branch_texture("子")["zao_shi"] == "湿"


def test_zaoshi_three_states_no_ping():
    """"平"退场：每支只有 湿/燥/歧异/条件性 四态之一，且带来源强度"""
    for z in "子丑寅卯辰巳午未申酉戌亥":
        t = branch_texture(z)
        assert t["zao_shi_state"] in ("湿", "燥", "歧异", "条件性"), z
        assert t["zao_shi_strength"] in ("双源", "单源", "冲突", "条件性"), z
        assert t["zao_shi_sources"], z


def test_zaoshi_shenyou_conflict_split():
    """申酉＝歧异：方位层（西北为湿）与原注（金燥而宜湿）方向相反，分列不自行择一"""
    t = branch_texture("申")
    assert t["zao_shi_state"] == "歧异" and t["zao_shi_strength"] == "冲突"
    carriers = {s["carrier"][:3]: s["value"] for s in t["zao_shi_sources"]}
    assert carriers.get("方位层") == "湿" and carriers.get("燥湿章") == "燥"
    assert branch_texture("酉")["zao_shi_state"] == "歧异"


def test_zaoshi_yinmao_conditional():
    """寅卯＝条件性：三步皆无逐支燥湿条文，随局中水火与干支相配定（"燥湿者，水火相成之谓也"）"""
    for z in ("寅", "卯"):
        t = branch_texture(z)
        assert t["zao_shi_state"] == "条件性" and t["zao_shi_strength"] == "条件性"
        assert "水火相成" in t["zao_shi_sources"][0]["carrier"]


# ---------- 第二批·关系层之一：月令五态 ----------

def test_month_five_states():
    """春木旺金囚、冬火死、秋水相——《渊海子平·旺相休囚死》《卜筮正宗·四时旺相》"""
    assert month_state("木", "木")["state"] == "旺"
    assert month_state("火", "木")["state"] == "相"
    assert month_state("水", "木")["state"] == "休"
    assert month_state("金", "木")["state"] == "囚"
    assert month_state("土", "木")["state"] == "死"
    assert month_state("火", "水")["state"] == "死"
    assert month_state("水", "金")["state"] == "相"
    assert month_state("金", "土")["state"] == "相"   # 四季土月土旺金相
    assert month_state("木", "土")["state"] == "囚"


# ---------- 第二批·关系层之二：克三值化（乘侮） ----------

def test_ke_wu():
    """侮：攻方不及、守方气足——金弱木坚，木反侮金（己所胜轻而侮之）"""
    r = ke_triple("金", "木", {"金": 1, "木": 4, "火": 1, "土": 1, "水": 1})
    assert r["value"] == "侮"


def test_ke_cheng():
    """乘：攻方气有余——金旺木衰，乘势过度克制（气有余则制己所胜）"""
    r = ke_triple("金", "木", {"金": 4, "木": 1, "火": 1, "土": 1, "水": 1})
    assert r["value"] == "乘"


def test_ke_zheng():
    """正克：势均力敌，制而不害"""
    r = ke_triple("金", "木", {"金": 2, "木": 2, "火": 1, "土": 1, "水": 2})
    assert r["value"] == "正克"


def test_ke_month_boost():
    """数量相同，攻方当令（旺）→ 乘——月令五态给乘侮提供时令分量"""
    r = ke_triple("金", "木", {"金": 2, "木": 2, "火": 1, "土": 1, "水": 2}, month_wx="金")
    assert r["value"] == "乘"


def test_ke_empty_tally():
    assert ke_triple("金", "木", {}) == {}


# ---------- 第二批·关系层之三：地支作用 ----------

def test_branch_chong():
    """补金逢寅：寅申相冲——冲者散也（增删卜易·六冲章）"""
    hits = branch_actions("金", ["寅", "午", "戌", "子"])
    assert any(h["type"] == "六冲" and h["pair"] == "寅申" for h in hits)


def test_branch_he_and_sanhe():
    """补金逢巳：巳申合水（三命通会·论六合）；补水而申子辰全：三合成局（子平真诠）"""
    hits = branch_actions("金", ["巳", "亥", "辰", "午"])
    assert any(h["type"] == "六合" and h["pair"] == "巳申" for h in hits)
    hits2 = branch_actions("水", ["申", "子", "辰", "午"])
    assert any(h["type"] == "三合成局" for h in hits2)
    hits3 = branch_actions("水", ["申", "子", "午", "卯"])
    assert any(h["type"] == "半合" for h in hits3)


def test_branch_actions_empty():
    assert branch_actions("金", []) == []


def test_branch_notes_extrapolation_template():
    """R6 处置回归：外推类条目按固定模板输出——断言主体是"传统"、禁止量化、落点是可执行动作，
    且条目自带 出身/接口/边界 三字段元数据（防止将来被静默挪进裁决链）。"""
    import re
    hits = branch_actions("金", ["寅", "午", "戌", "子"])
    chong = next(h for h in hits if h["type"] == "六冲")
    # ① 句子降级：断言主体让位给"传统"，删除结果断言"补力被冲减"
    assert "传统上主散" in chong["note"]
    assert "补力被冲减" not in chong["note"] and "补力被合住" not in chong["note"]
    # ② 禁止量化表述（百分比/强度值/精确程度）
    assert not re.search(r"\d+(\.\d+)?%|冲减\d|减力\d", chong["note"])
    # ③ 落点为可执行动作（另择时/合住之时再补），且动作有据（巳申六合在案）
    assert "可另择时" in chong["note"] and "再补" in chong["note"]
    assert "巳日合申" in chong["note"]
    # ④ 三字段元数据写死于条目
    assert "类比外推" in chong["meta"]["出身"]
    assert "不进裁决权重" in chong["meta"]["边界"]
    assert chong["meta"]["接口"]
    # 五合同类条目同模板
    gan_hits = stem_actions("金", ["乙", "丙", "戊", "壬"])
    assert all("传统上主" in h["note"] for h in gan_hits)
    assert all(h["meta"]["边界"] for h in gan_hits)


# ---------- 与流动判定表的整链 ----------

def test_flow_plan_relation_layer_integration():
    from wuxing_flow import flow_plan
    mj = {"wuxing_tally": {"金": 1, "木": 3, "火": 1, "土": 1, "水": 2},
          "month_wx": "木", "from_ge": "", "effective_wx": "金",
          "zhis": ["寅", "午", "戌", "子"], "month_zhi": "寅"}
    plan = flow_plan("金", mj)
    assert plan["state"] == "弱"
    assert plan["month_state"]["state"] == "囚"          # 木月金囚
    active = next(r for r in plan["rows"] if r["active"])
    cw = active["cells"]["我克"]["chengwu"]
    assert cw and cw["value"] == "侮"                    # 金不及而木坚
    assert any(h["type"] == "六冲" and h["pair"] == "寅申" for h in plan["branch_notes"])


def test_flow_plan_no_zhis_flag():
    from wuxing_flow import flow_plan
    mj = {"wuxing_tally": {"金": 2}, "month_wx": "金", "from_ge": "", "effective_wx": "金"}
    plan = flow_plan("金", mj)
    assert plan["branch_notes"] == [] and plan["branch_missing"] is True


# ---------- R2：干支级（藏干加权力量 / 天干五合 / 卦侧干支取向） ----------

def test_hidden_tally_weights():
    """干支级力量：天干各 1.0，地支按藏干本气/中气/余气加权——《渊海子平》人元以本气为重"""
    t = hidden_tally(["庚"], ["申"])
    assert t["金"] == 2.0 and t["水"] == 0.6 and t["土"] == 0.4   # 庚1.0+申本气庚1.0；申中气壬、余气戊
    t2 = hidden_tally([], ["丑"])
    assert t2["土"] == 1.0 and t2["水"] == 0.6 and t2["金"] == 0.4


def test_hidden_tally_feeds_chengwu():
    """干支级力量进乘侮：同样"金1木1"，藏干加权后可判出强弱差"""
    weak = hidden_tally([], ["酉"])                     # 金 1.0
    strong = hidden_tally([], ["寅", "卯"])             # 木 1.0+1.0
    r = ke_triple("金", "木", {"金": weak["金"], "木": strong["木"]}, "")
    assert r["value"] == "侮"                            # 金不及而木气足 → 木反侮金


def test_stem_actions_gan_he():
    """天干五合：补金之干遇命局乙→乙庚合金（合而助我）；遇丙→丙辛合水（泄我）"""
    hits = stem_actions("金", ["乙", "丙", "戊", "壬"])
    pairs = {h["pair"]: h["hua"] for h in hits}
    assert pairs.get("庚乙") == "金" or pairs.get("乙庚") == "金"
    assert any(h["hua"] == "水" for h in hits)


def test_stem_actions_empty():
    assert stem_actions("金", []) == []
    assert stem_actions("金", ["甲", "戊"]) == []      # 甲己合、戊癸合，与庚辛无涉


def test_pick_flavor_from_yong_ganzhi():
    """六爻用神爻干支优先（干支级）：用神在酉 → 取辛金温润之味"""
    f = pick_flavor("金", yong_ganzhi="辛酉")
    assert f["gan"] == "辛" and "卦侧用神爻干支" in f["basis"]


def test_pick_flavor_by_season():
    """时令取向：起卦日支属燥暖乡→取寒润之味——《滴天髓·寒暖》"暖燥太过，喜雨露以润之\""""
    f = pick_flavor("金", month_wx="火", day_zhi="午")
    assert f["gan"] == "辛" and "润" in f["note"] or "寒润" in f["note"]
    f2 = pick_flavor("土", month_wx="水", day_zhi="子")
    assert f2["gan"] == "戊"                            # 寒湿宜暄 → 取戊土高亢厚重
    f3 = pick_flavor("金", month_wx="土", day_zhi="申")
    assert f3["basis"] == "时令中和"


def test_flavor_table_covers_all_wx():
    for wx in ("木", "火", "土", "金", "水"):
        assert wx in FLAVOR_TABLE and len(FLAVOR_TABLE[wx]["stems"]) == 2
        assert FLAVOR_TABLE[wx]["constraint"] and FLAVOR_TABLE[wx]["src"]


# ---------- 乘侮判据：《素问》四路径经"攻守比值"坍缩为两态 ----------

def test_ke_four_paths_collapse_to_two_states():
    """太过侧两条（制己所胜/侮所不胜）＋不及侧两条（守弱被乘/攻弱受侮）都必须触发——
    单侧绝对量判据会漏掉不及侧（如土虚木乘、金衰而木侮金）。"""
    # ① 攻方太过 → 乘（金旺木衰）
    assert ke_triple("金", "木", {"金": 4, "木": 1})["value"] == "乘"
    # ② 守方不足 → 乘（土虚木乘：木未必太过）
    assert ke_triple("木", "土", {"木": 1.5, "土": 0})["value"] == "乘"
    # ③ 守方气足 → 侮（木坚金缺）
    assert ke_triple("金", "木", {"金": 1, "木": 4})["value"] == "侮"
    # ④ 攻方不足 → 侮（金衰而木侮金：木未必气足）
    assert ke_triple("金", "木", {"金": 0, "木": 1.5})["value"] == "侮"


def test_ke_ratio_and_classics():
    """势均锚点 ratio≈1；侮载"侮反受邪"；乘载《元理赋》乘句；正克载"制则生化\""""
    zheng = ke_triple("金", "木", {"金": 2, "木": 2})
    assert zheng["value"] == "正克" and zheng["ratio"] == 1.0 and "制则生化" in zheng["note"]
    wu = ke_triple("金", "木", {"金": 1, "木": 4})
    assert "侮反受邪" in wu["note"] and "木坚金缺" in wu["note"] and wu["ratio"] == 0.25
    cheng = ke_triple("金", "木", {"金": 4, "木": 1})
    assert "木弱逢金，必为砍折" in cheng["note"] and cheng["ratio"] == 4.0


# ---------- R11：生边三值化（母多灭子／子旺侮母） ----------

def test_sheng_triple_three_values():
    """R11：生边与克边同构——母子比值分三值。

    《元理赋》生边十句本就是**成对的两侧**：
      母多灭子：「金赖土生，土多金埋」——生得过头；
      子旺侮母：「金能生水，水多金沉」——泄得过头。
    此前生边只有"生／不生"二值，只能说"能生，好"，说不出这两侧。
    """
    from wuxing_quality import sheng_triple
    # ① 母太过 → 母多灭子（土多金埋）
    mu = sheng_triple("土", "金", {"土": 4, "金": 1})
    assert mu["value"] == "母多灭子" and "土多金埋" in mu["note"]
    # ② 子太过 → 子旺侮母（水多金沉）
    zi = sheng_triple("金", "水", {"金": 1, "水": 4})
    assert zi["value"] == "子旺侮母" and "水多金沉" in zi["note"]
    # ③ 势均 → 正生
    zheng = sheng_triple("土", "金", {"土": 2, "金": 2})
    assert zheng["value"] == "正生" and zheng["ratio"] == 1.0
    # ④ 两气皆无 → 不判（与 ke_triple 同约定）
    assert sheng_triple("土", "金", {}) == {}


def test_sheng_triple_shares_margin_with_ke():
    """生边**不新设阈值**：与克边共用同一个势均带（chengwu_margin）。

    两侧若各定一套 margin，乘侮与生害之间就会出现无法解释的缝隙——
    同一个命局、同一个比值，换个边就得出不同结论。
    """
    from wuxing_quality import sheng_triple, ke_triple
    from weights import FLOW
    m = float(FLOW.get("chengwu_margin", 1.0))
    # 比值刚好落在势均带**边界外一点**：两侧都该判"非正"
    a, d = m + 1.0, 1.0                       # ratio = m + 1 > m → 越过带
    assert sheng_triple("土", "金", {"土": a, "金": d})["value"] == "母多灭子"
    assert ke_triple("土", "水", {"土": a, "水": d})["value"] == "乘"
    # 比值刚好落在带**之内**：两侧都该判"正"
    a2, d2 = 1.0 + m * 0.5, 1.0               # 差 = m/2 < m
    assert sheng_triple("土", "金", {"土": a2, "金": d2})["value"] == "正生"
    assert ke_triple("土", "水", {"土": a2, "水": d2})["value"] == "正克"


def test_flow_wires_sheng_three_on_both_sheng_edges():
    """流动表的两条生边都要接上三值：进气＝母生我、出水＝我生子。"""
    from wuxing_flow import flow_plan
    # 补金：进气边＝土生金（母=土），出水边＝金生水（子=水）
    # 土气 4 > 金气 1 → 「土多金埋」；水气 4 > 金气 1 → 「水多金沉」
    mj = {"wuxing_tally": {"金": 1, "土": 4, "水": 4}, "month_wx": "",
          "wuxing_tally_hidden": {"金": 1, "土": 4, "水": 4}}
    plan = flow_plan("金", mj)
    row = next(r for r in plan["rows"] if r["active"])
    jin = row["cells"]["进气"]
    chu = row["cells"]["出水"]
    assert jin["sheng_three"]["value"] == "母多灭子" and "土多金埋" in jin["sheng_three"]["note"]
    assert chu["sheng_three"]["value"] == "子旺侮母" and "水多金沉" in chu["sheng_three"]["note"]
    # 命中生害时静态格不裸输出，改出复合句（与克边的 R5 处理同形）
    assert "生害修正" in jin["combined"] and "方向：" in jin["combined"]
    assert "生害修正" in chu["combined"]
    # 生边**不出** R5 那类冲突告警（生害是同一方向的量级修正，不是两套结论）
    assert not jin.get("conflict") and not chu.get("conflict")


def test_flow_cell_combined_and_conflict():
    """R5：乘侮＝量级调制器——边态命中时静态格禁止裸输出，改出复合句；
    方向与量级不同源（静态格开此克却判乘 / 忌此克却判侮）则告警而非静默择一。"""
    from wuxing_flow import flow_plan
    # 中和偏旺之金（静态格"克我：宜少量·成器"）＋火气有余（边态判乘）→ 复合句 + 告警
    mj = {"wuxing_tally": {"金": 4, "火": 5, "木": 1, "土": 1, "水": 1},
          "month_wx": "火", "from_ge": "", "effective_wx": "金"}
    plan = flow_plan("金", mj)
    row = next(r for r in plan["rows"] if r["active"])
    cell = row["cells"]["克我"]
    assert cell["grade"] in ("宜少量", "宜")
    assert cell["chengwu"]["value"] == "乘"
    assert "方向：" in cell["combined"] and "量级修正：乘" in cell["combined"]
    assert cell["conflict"] is True and cell["conflict_note"]
    # 弱金（静态格"克我：大忌"）＋火乘金 → 方向与量级同向，不需告警，但仍出复合句
    mj2 = {"wuxing_tally": {"金": 1, "火": 4, "木": 1, "土": 1, "水": 1},
           "month_wx": "火", "from_ge": "", "effective_wx": "金"}
    plan2 = flow_plan("金", mj2)
    row2 = next(r for r in plan2["rows"] if r["active"])
    cell2 = row2["cells"]["克我"]
    assert cell2["grade"] == "大忌" and cell2["chengwu"]["value"] == "乘"
    assert cell2["combined"] and not cell2.get("conflict")


def test_conflict_suppressed_for_antike_cells():
    """R5 边界（2026-09-18 补）：静态格判「忌」的理由若**本就是"克不动、反受其伤"**
    （＝《元理赋》反生反克组），则它与边态的「侮」（克制不成立）是**同一个判断**，
    同向确认，不该告警——此前判据只看 grade 字面，把它误报成了"不同源冲突"。

    本测试固化站长核查的结论：出告警的 21 条样本里，15 条落在反克组（误报）、
    6 条落在格局侧（真冲突，须继续告警）。
    """
    from wuxing_flow import flow_plan, ANTI_KE_CELLS

    # ① 反克组 → 不告警，但要留下"为什么不告警"的记录（不静默少报）
    #   金·弱 的「我克」＝「弱金砍不动强木，反崩刃（木坚金缺）」，正是【反克】本身。
    #   构造：木（守方）气足 → ke_triple 判「侮」。
    mj = {"wuxing_tally": {"金": 1, "木": 2}, "month_wx": "",
          "wuxing_tally_hidden": {"金": 1, "木": 2}}
    plan = flow_plan("金", mj)
    row = next(r for r in plan["rows"] if r["active"])
    cell = row["cells"]["我克"]
    assert cell["grade"] == "忌" and cell["chengwu"]["value"] == "侮"
    assert ("金", "弱", "我克") in ANTI_KE_CELLS
    assert not cell.get("conflict"), "反克组的「忌+侮」是同向确认，不该告警"
    assert "同源" in cell.get("conflict_suppressed", ""), "压制告警必须留下理由，不得静默"

    # ② 格局侧 → **仍须告警**（此克确实有害，与"克不成立"方向相反）
    #   木·旺极(从格) 的「克我」＝「见庚辛即官杀非此格」——忌的是"破格"，不是"克不动"。
    mj2 = {"wuxing_tally": {"木": 6, "金": 5}, "month_wx": "",
           "wuxing_tally_hidden": {"木": 6, "金": 5}}
    plan2 = flow_plan("木", mj2)
    row2 = next(r for r in plan2["rows"] if r["active"])
    cell2 = row2["cells"]["克我"]
    assert cell2["grade"] == "大忌" and cell2["chengwu"]["value"] == "侮"
    assert ("木", "旺极(从格)", "克我") not in ANTI_KE_CELLS
    assert cell2.get("conflict") is True and cell2.get("conflict_note"), \
        "格局侧（逆势/破格）与「侮」方向相反，必须继续告警"

    # ③ 边界不得扩大：木/火/金 的「弱极·克我」判词是"顺势（从格）另判"（属从格一路），
    #    不属反克组——即便它们因 d=0 实际判不出「侮」，也不该被误收进豁免集。
    for w in ("木", "火", "金"):
        assert (w, "弱极", "克我") not in ANTI_KE_CELLS


# ---------- R1：质地精度进入建议层（suggest_wuxing） ----------

def test_suggest_wuxing_texture_block():
    from wuxing_suggest import suggest_wuxing
    flavors = {"金": pick_flavor("金", yong_ganzhi="辛酉")}
    sug = suggest_wuxing(["金"], flavors=flavors)
    tex = sug["金"]["质地"]
    assert tex["两味分列"] and len(tex["两味分列"]) == 2
    rec = [s for s in tex["两味分列"] if s["推荐"]]
    assert rec and rec[0]["干"] == "辛"
    assert "燥土不生金" in tex["约束"]
    assert "质地" in sug["金"]["src"]


def test_suggest_wuxing_texture_without_flavor():
    from wuxing_suggest import suggest_wuxing
    sug = suggest_wuxing(["土"])
    assert sug["土"]["质地"]["两味分列"] and not sug["土"]["质地"]["本味推荐"]


# ---------- 丙·4：建议颗粒按味细分（flavor_split） ----------

def _xiang_lib():
    """取五行类象库的 bagua 段——用 wuxing_suggest 自己的加载器，测试不另开一份读取路径。"""
    from wuxing_suggest import load_lib
    return load_lib()["bagua"]

# 这一组守两件事：①书上真分了的，我们要分开（庚斧钺／辛首饰）；
# ②书上没分的、或分不出的，我们绝不许替它分（火水单卦、十干级的方位颜色数字五味）。

def test_flavor_split_jin_two_flavors_with_own_sources():
    """补金必须给出庚／辛两列，且**各有各的出处**——这是"颗粒降到味级"的核心。"""
    from wuxing_quality import flavor_split
    lib = _xiang_lib()
    r = flavor_split("金", lib)
    assert r["阳"]["干"] == "庚" and r["阳"]["名"] == "斧钺之金"
    assert r["阴"]["干"] == "辛" and r["阴"]["名"] == "首饰之金"
    assert "斧钺" in r["阳"]["物"] and "剑戟" in r["阳"]["物"]
    assert "首饰" in r["阴"]["物"]
    # 两列的出处必须不同（各回各源），否则"分列"就只是排版
    assert r["阳"]["srcs"] != r["阴"]["srcs"]
    assert "滴天髓·论天干·庚金" in r["阳"]["srcs"]
    assert "滴天髓·论天干·辛金" in r["阴"]["srcs"]


def test_flavor_split_sources_are_resolvable_quote_keys():
    """**每一个出处键都必须在 book_quotes 里查得到原文**。

    这是把"逐字回源"落到建议颗粒上的验收条件：出处的价值不在于写得像出处，
    而在于点得开、核得了。查不到的键在页面上显示"原文待录"——那等于没有出处。
    """
    from wuxing_quality import STEM_OBJECTS, flavor_split
    from book_quotes import lookup
    lib = _xiang_lib()
    checked = 0
    for wx in "木火土金水":
        r = flavor_split(wx, lib)
        for pos in ("阳", "阴"):
            c = r[pos]
            if not c:
                continue
            for k in c["srcs"] + (c.get("卦srcs") or []):
                assert lookup(k)["text"], "出处键查不到原文：%s" % k
                checked += 1
    # 顺带覆盖 STEM_OBJECTS 全表（有些干可能不会出现在 flavor_split 的某一侧）
    for gan, so in STEM_OBJECTS.items():
        for k in so["srcs"]:
            assert lookup(k)["text"], "%s 的出处键查不到原文：%s" % (gan, k)
    assert checked >= 10


def test_flavor_split_does_not_merge_shi_gan_and_bagua():
    """十干列与八卦列**并列而不合并**——R6：跨载体不得互推。

    乾／兑的静物出自《说卦传》《梅花易数》，庚／辛的器物出自《滴天髓》《三命通会》，
    两本书各说各的。把它们并成一张"补金之物"清单，就等于替书上做了它没做过的对应。
    """
    from wuxing_quality import flavor_split
    lib = _xiang_lib()
    r = flavor_split("金", lib)
    assert r["阳"]["卦"] == "乾" and r["阴"]["卦"] == "兑"
    # 乾兑的静物只出现在"卦物"里，**不许混进"物"**（混进去就是合并了）
    for pos, gua in (("阳", "乾"), ("阴", "兑")):
        assert r[pos]["卦物"], pos
        for w in r[pos]["卦物"]:
            assert w not in r[pos]["物"], "%s：卦侧物类 %r 混进了十干列" % (gua, w)


def test_flavor_split_xin_not_defined_as_zhuyu():
    """辛金不许被定义成"珠玉"——《滴天髓》原注明说"辛乃阴金，非珠玉之谓也"。

    这是一处**照抄成句就会与原书相违**的地方：书上把"珠玉"当成需要否定的误解，
    所以产品里必须带上这条警示，不能只留"珠玉"两个字。
    """
    from wuxing_quality import STEM_OBJECTS, flavor_split
    assert "非珠玉之谓也" in STEM_OBJECTS["辛"]["note"]
    assert "温软清润" in STEM_OBJECTS["辛"]["note"]
    lib = _xiang_lib()
    assert "珠玉" not in flavor_split("金", lib)["阴"]["物"], \
        "辛的十干器物里不该出现『珠玉』——原注正是在否定这个等式"


def test_flavor_split_single_gua_rows_not_padded():
    """火只辖离、水只辖坎：只有一侧有卦，另一侧如实为空并说明原因——不凑数。

    凑一个"丙＝离、丁＝某卦"出来，读者看不出来，但那是编的。
    """
    from wuxing_quality import flavor_split
    lib = _xiang_lib()
    fire = flavor_split("火", lib)
    assert fire["阳"].get("卦") is None and fire["阴"]["卦"] == "离"
    assert "只有一卦" in fire["note"] and "不凑数" in fire["note"]
    water = flavor_split("水", lib)
    assert water["阳"]["卦"] == "坎" and water["阴"].get("卦") is None
    assert "只有一卦" in water["note"]


def test_flavor_split_declares_what_stays_wu_xing_level():
    """分不动的地方也要说清"分不动"，否则读者会以为是我们漏了。

    方位/颜色/数字/五味在书上只给到五行这一层；乾（西北）与兑（西）的差别属**卦**，
    不是庚辛的味差。
    """
    from wuxing_quality import flavor_split
    lib = _xiang_lib()
    note = flavor_split("金", lib)["五行级"]
    assert "方位" in note and "五味" in note
    assert "R6" in note


def test_flavor_split_carries_no_house_dimension():
    """味分档里**不许带屋宅**：屋宅是 M 档落地物，而本块挂在 S 档的「质地」维度下。

    带上它，S 档用户就会在自己的建议里读到屋宅布局——正是"越档"。
    屋宅有自己的顶层维度，由档位过滤统一管。
    """
    from wuxing_quality import flavor_split
    lib = _xiang_lib()
    r = flavor_split("金", lib)
    for pos in ("阳", "阴"):
        assert "卦屋宅" not in r[pos]
    import json as _json
    assert "屋宅" not in _json.dumps(r, ensure_ascii=False)


def test_suggest_text_labelled_by_level():
    """文案里每一行都要标出层级：味级（十干）、卦侧（另有出处）、五行级（合参）。

    不标层级的话，上面刚拆开的乾/兑与下面那张"乾兑合参"清单会被读成互相打架。
    """
    from wuxing_suggest import suggest_text
    txt = suggest_text(["金"])
    assert "阳味【庚·斧钺之金】" in txt and "阴味【辛·首饰之金】" in txt
    assert "同类可参（卦侧·乾" in txt and "同类可参（卦侧·兑" in txt
    assert "五行级，乾兑合参，仅供概览" in txt
    # 出处逐个列出，供人点开核对
    assert "滴天髓·论天干·庚金" in txt and "滴天髓·论天干·辛金" in txt
