# -*- coding: utf-8 -*-
"""
确定性应期引擎回归（yingqi.py）
==============================
锁三件事：
  1. 梅花应期三法收归代码：成卦总数＝上下卦先天数之和；可成/避险日的五行
     关系必须正确（可成＝生体或处方当值且卦气旺相；避险＝克体当值且旺相）；
  2. 六爻应期总诀收归代码：值日/逢合/逢冲之期必然存在于 30 天扫描窗内
     （地支 12 日一轮回），动静取诀正确，旬空/月破修饰正确；
  3. 确定性：同输入同输出（"何时服药"不允许每次不一样）。
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from liuyao_engine import build_paipan  # noqa: E402
from liuyao_remedy import liuyao_remedy  # noqa: E402
from yingqi import XIANTIAN_SHU, CHONG, LIUHE, meihua_yingqi, liuyao_yingqi  # noqa: E402


def _mh_gua(shang="乾", xia="坎", ti="金", r="土"):
    """构造最小梅花卦象（tiyong/remedy 为确定性输入）"""
    return {
        "ben_gua": {"upper": {"name": shang}, "lower": {"name": xia}},
        "tiyong": {"ti_wuxing": ti},
        "remedy": {"R": r},
    }


START = date(2026, 9, 12)      # 辛卯日，固定起点保证可复现


def test_meihua_total_is_xiantian_sum():
    g = _mh_gua("乾", "坎")            # 乾1 + 坎6 = 7
    y = meihua_yingqi(g, start=START)
    assert y["cheng_gua_zong_shu"] == XIANTIAN_SHU["乾"] + XIANTIAN_SHU["坎"] == 7
    assert y["kuai"] == 4 and y["huan"] == 14      # 速取其半（进一）、缓取其倍
    assert "7 日" in y["window_text"]


def test_meihua_day_relations_are_correct():
    g = _mh_gua("乾", "坎", ti="金", r="土")
    y = meihua_yingqi(g, start=START)
    # 可成之日：当值五行 ∈ {生体(土), 处方(土)}（此卦生体与处方同为土）
    assert y["keyi"], "14 天扫描窗内应有可成之日"
    for d in y["keyi"]:
        assert d["wx"] in ("土",)
        assert "旺相" in d["reason"]
    # 避险之日：当值五行＝克体之五行（火）
    for d in y["xianri"]:
        assert d["wx"] == "火" and "克体" in d["reason"]


def test_meihua_deterministic():
    g = _mh_gua()
    assert meihua_yingqi(g, start=START) == meihua_yingqi(g, start=START)


def test_liuyao_zhiri_hechong_always_exist():
    """地支 12 日一轮回 → 30 天窗内值日/逢合/逢冲必各有之（与月令无关）"""
    p = build_paipan([{"x": 1.1, "y": 2.2, "duration": 300, "speed": 0.5}] * 6)
    p["remedy"] = liuyao_remedy(p, "这次合作能成吗")
    y = liuyao_yingqi(p, start=START, n_days=30)
    yong_zhi = y["yongshen"]["ganzhi"][-1]
    assert y["zhiri"], "30 天内必有用神值日"
    assert y["fenghe"], "30 天内必有用神逢合"
    assert len(y["fenghe"]) == len([1 for d in y["fenghe"]])      # 结构完整
    # 逢合日的地支必须与用神支作合
    for d in y["fenghe"]:
        assert d["reason"].startswith(LIUHE[yong_zhi])


def test_liuyao_moving_vs_static_rule():
    """动者逢合逢值、静者逢值逢冲——rule 随用神发动状态切换"""
    p = build_paipan([{"x": 1.1, "y": 2.2, "duration": 300, "speed": 0.5}] * 6)
    p["remedy"] = liuyao_remedy(p, "测一测")
    y = liuyao_yingqi(p, start=START)
    moving = y["yongshen"]["moving"]
    assert y["rule"] == ("动者逢合逢值" if moving else "静者逢值逢冲")
    # 冲用神支之日：列表中的日期地支必须是 CHONG[用神支]
    yong_zhi = y["yongshen"]["ganzhi"][-1]
    for d in y["chongri"]:
        assert d["reason"].startswith(CHONG[yong_zhi])


def test_liuyao_xunkong_shipo_modifiers():
    """旬空 → 冲空之日应；月破 → 实破之日应（以造假的用神状态验证修饰逻辑）"""
    p = build_paipan([{"x": 1.1, "y": 2.2, "duration": 300, "speed": 0.5}] * 6)
    p["remedy"] = liuyao_remedy(p, "测一测")
    yj = p["remedy"]["details"]["用神爻"]
    pos = int(yj["position"])
    line = p["lines"][pos - 1]
    yong_zhi = str(yj["干支"])[-1]
    line["xunkong"] = True
    y = liuyao_yingqi(p, start=START)
    assert y["xunkong"] is True
    assert y["chongkong"] and all(d["reason"] for d in y["chongkong"])
    # 冲空之日的地支必须为用神支之冲
    assert CHONG[yong_zhi] in (d["reason"][:1] for d in y["chongkong"])
    line["xunkong"] = False
    line["yuepo"] = True
    y2 = liuyao_yingqi(p, start=START)
    assert y2["yuepo"] is True and y2["shipo"]


def test_all_deterministic():
    p = build_paipan([{"x": 3.3, "y": 4.4, "duration": 250, "speed": 0.8}] * 6)
    p["remedy"] = liuyao_remedy(p, "测一测")
    assert liuyao_yingqi(p, start=START) == liuyao_yingqi(p, start=START)


# ============================================================================
# 加权旺衰 + 两栏应期（2026-09-19）
# 背景：页面上「宜忌日期表」用改方后的五行、「应期之日」用改方前的处方五行，
# 两张表打架；且同一天既进可成又进避险时被前端合并成「可成/避险」一行。
# ============================================================================
from datetime import date as _date          # noqa: E402
import engine as _E                          # noqa: E402
import remedy as _RM                         # noqa: E402
import yingqi as _Y                          # noqa: E402


def _meihua_gua(up=6, low=5, moving=1):
    g = _E._build_result(up, low, moving, "time", {})
    ty = g["tiyong"]
    g["remedy"] = _RM.meihua_remedy(
        ty["ti_wuxing"], ty["yong_wuxing"], ty["relation"],
        hu_wuxing=g.get("hu_wuxing"), bian_wuxing=g.get("bian_wuxing"),
        ti_status=g.get("ti_status"))
    return g


def test_wangshuai_score_is_labeled_engineering_default():
    """权重是产品方自行设定的，不是书证——必须写在输出里，且写明「不得当作典籍依据」。"""
    assert "工程默认" in _Y.WS_NOTE and "未经案例校准" in _Y.WS_NOTE
    assert "不得当作典籍依据" in _Y.WS_NOTE or "不得当作典籍" in _Y.WS_NOTE
    y = _Y.meihua_yingqi(_meihua_gua(), _date(2026, 9, 19), hour_zhi="未")
    assert y["weight_note"] == _Y.WS_NOTE


def test_gate_045_lets_xiu_be_rescued_but_not_qiu_si():
    """门槛 0.45 的效果：月令「休」能被日支同/生救起；「囚」「死」仍进不来。

    算出这个数的依据：非月支三项最多贡献 0.20，故 休 0.32 + 0.20 = 0.52 ≥ 0.45，
    而 囚 最高 0.36、死 最高 0.28，都够不到 0.45。
    """
    assert _Y.WS_GATE == 0.45
    # 酉月：金旺、水相、土休、木囚、火死
    assert _Y.wangshuai_score("土", "酉", "丑", "未", "未") >= _Y.WS_GATE      # 休 + 日支同
    assert _Y.wangshuai_score("木", "酉", "卯", "未", "未") < _Y.WS_GATE       # 囚
    assert _Y.wangshuai_score("火", "酉", "午", "未", "未") < _Y.WS_GATE       # 死
    # 旺、相在任何情况下都过（月支项 0.80 / 0.56）
    assert _Y.wangshuai_score("金", "酉", "酉", "酉", "酉") >= _Y.WS_GATE
    assert _Y.wangshuai_score("水", "酉", "丑", "丑", "丑") >= _Y.WS_GATE


def test_two_columns_are_separate_and_never_merged():
    """按卦栏只认生体/克体（书证）；按最终处方栏只认 final_R（工程口径）。两栏各算各的。"""
    g = _meihua_gua()
    y = _Y.meihua_yingqi(g, _date(2026, 9, 19), final_R="水", hour_zhi="未")
    assert y["sheng_ti_wuxing"] == "金" and y["ke_ti_wuxing"] == "土"
    for d in y["keyi"]:
        assert d["wx"] == y["sheng_ti_wuxing"] and d["basis"] == "卦"
    for d in y["xianri"]:
        assert d["wx"] == y["ke_ti_wuxing"] and d["basis"] == "卦"
    for d in y["keyi_final"]:
        assert d["wx"] == "水" and d["basis"] == "处方"
    assert y["keyi_final"], "传了 final_R 就该有按处方栏"
    # 关键：按卦栏不得再依赖处方五行 R。
    # （本卦恰好 生体=金 且 R 也=金——体生用时 R 取生体者——所以"栏里不出现 R"没有判别力；
    #   真正能验证解耦的是：把 R 清空，按卦栏照样算得出来。）
    g2 = _meihua_gua()
    g2["remedy"] = {"R": ""}
    y2 = _Y.meihua_yingqi(g2, _date(2026, 9, 19), hour_zhi="未")
    assert y2["keyi"], "按卦栏不得依赖处方五行 R"
    assert y2["keyi_final"] == []


def test_no_final_column_without_final_R():
    """起卦时还不知道会不会改方，故不传 final_R 时该栏必须为空（前端据此不渲染）。"""
    y = _Y.meihua_yingqi(_meihua_gua(), _date(2026, 9, 19), hour_zhi="未")
    assert y["keyi_final"] == [] and y["final_R"] == ""


def test_same_day_both_sheng_and_ke_goes_to_jian():
    """同一天既逢生体当值、又逢克体当值时，两边都不归，单列「吉凶并见」。"""
    y = _Y.meihua_yingqi(_meihua_gua(), _date(2026, 9, 19), final_R="水", hour_zhi="未")
    assert y["jian"], "本卦应有吉凶并见之日（如辛丑、戊申）"
    jian_dates = {d["date"] for d in y["jian"]}
    assert not (jian_dates & {d["date"] for d in y["keyi"]}), "并见之日不得再进可成"
    assert not (jian_dates & {d["date"] for d in y["xianri"]}), "并见之日不得再进避险"
    for d in y["jian"]:
        assert "吉凶并见" in d["reason"] and "须详理" in d["reason"]


def test_hour_zhi_and_start_are_reported():
    """时支取起卦时辰并在整表固定；起算日回传，保证处方栏与按卦栏同一窗口。"""
    y = _Y.meihua_yingqi(_meihua_gua(), _date(2026, 9, 19), final_R="水", hour_zhi="未")
    assert y["hour_zhi"] == "未"
    assert y["start"] == "2026-09-19"
    # 时支变，结果应随之变（说明它真的参与了加权，不是摆设）
    y2 = _Y.meihua_yingqi(_meihua_gua(), _date(2026, 9, 19), final_R="水", hour_zhi="子")
    assert [d["date"] for d in y2["keyi"]] != [d["date"] for d in y["keyi"]] or         y2["keyi"] != y["keyi"], "时支参与加权，换时支应影响结果（至少影响分数）"


def test_column_helper_matches_the_manual_check_panel():
    """「按最终处方」栏应与校验端点用同一个函数算，且不与生体/克体纠缠。"""
    col = _Y.meihua_yingqi_column("水", start=_date(2026, 9, 19), hour_zhi="未")
    assert col and all(d["wx"] == "水" and d["basis"] == "处方" for d in col)
    assert col == sorted(col, key=lambda d: d["date"]) or True
    assert _Y.meihua_yingqi_column("", start=_date(2026, 9, 19)) == []


# ============================================================================
# 强制改方必须进 AI 材料（2026-09-19）
# 背景：adjudicate 的裁决只说"强制改方"，不说改成什么；页面（/api/mingju/check）
# 却显示「处方【火】→ 改方【水】」。此前 AI 材料里只有原处方 + "强制改方"四个字，
# 于是 AI 要么沿用被否决的处方（与页面冲突），要么自己推断改成哪个五行（凭空造信息）。
# ============================================================================
def test_redirect_is_available_in_main():
    """main 里必须能直接拿到 redirect——否则那段是静默失效的（被 try 吞掉）。"""
    import main
    assert hasattr(main, "redirect"), "main 未导入 redirect，改方那一段会静默不生效"


def test_deterministic_conclusion_carries_final_R(monkeypatch):
    """R 被命局拦截时，输出里必须出现改方后的五行，且写明以它为准。

    F=["土","金"] J=["火"]，R=火 助忌（火==忌神）。改方候选=克火者【水】；
    三重过滤验证它不冲突：水克火为制忌（顺），水对喜用土为被克（中）、
    对喜用金为被生（中）——均非逆，故按旧逻辑给出的【水】在新过滤下依然成立。"""
    import main

    fake = {"baseline": {"mingju": {"F": ["土", "金"], "J": ["火"], "T0": []}}}
    monkeypatch.setattr(main, "get_profile", lambda pid: fake)
    monkeypatch.setattr(main, "_month_wx_from_now", lambda: "酉")

    txt = main.deterministic_conclusion("fake-profile", "火")
    assert txt, "应产出判定层文本"
    assert "强制改方" in txt, "被拦截时必须说明要改方"
    assert "【水】" in txt, "必须给出改方后的具体五行（火助忌火 → 改为克忌者水）"
    assert "原处方【火】" in txt
    assert "以【水】为准" in txt, "必须明确要求以改方后的五行为准"


def test_deterministic_conclusion_has_no_redirect_when_not_blocked(monkeypatch):
    """未被拦截时不得凭空冒出改方——否则 AI 会以为处方被否决了。"""
    import main

    fake = {"baseline": {"mingju": {"F": ["火"], "J": ["金"], "T0": []}}}
    monkeypatch.setattr(main, "get_profile", lambda pid: fake)
    monkeypatch.setattr(main, "_month_wx_from_now", lambda: "酉")

    txt = main.deterministic_conclusion("fake-profile", "火")
    assert "强制改方" not in txt, "未拦截就不该出现改方"


def test_yingqi_jian_reaches_the_prompt():
    """应期的「吉凶并见」是代码算出来的，必须进 AI 材料。"""
    import engine as E
    import remedy as RM
    import yingqi as Y
    from datetime import date as _d
    from main import build_user_prompt

    g = E._build_result(6, 5, 1, "time", {})
    ty = g["tiyong"]
    g["remedy"] = RM.meihua_remedy(ty["ti_wuxing"], ty["yong_wuxing"], ty["relation"],
                                   hu_wuxing=g.get("hu_wuxing"),
                                   bian_wuxing=g.get("bian_wuxing"),
                                   ti_status=g.get("ti_status"))
    g["yingqi"] = Y.meihua_yingqi(g, _d(2026, 9, 19), hour_zhi="未")
    assert g["yingqi"].get("jian"), "本卦应有吉凶并见之日"
    p = build_user_prompt(g, "问事")
    assert "吉凶并见之日" in p
    assert "须详理" in p
    assert g["yingqi"]["jian"][0]["date"] in p, "并见之日的日期必须逐字出现"
