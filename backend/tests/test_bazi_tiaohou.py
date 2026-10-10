# -*- coding: utf-8 -*-
"""
调候判定回归（月令优先 2026-09-15 修差异1 + 表用神次序 2026-09-15 修差异2）
==========================================================================
两条规则：
  1.【月令优先】寒暖先看月令（巳午未→燥 / 亥子丑→寒）；月令中性（寅卯辰申酉戌）
    才用"有根"干支的寒暖多寡兜底（±2 字；天干虚浮不计）。
    旧 bug：`if season_hot or dc >= 2` 让计数与月令平权且计数在前——
    冬月火土多会被误判燥局（己日主子月火土 6 字 → 旧判燥局补水，
    《穷通宝鉴》十一月己却要丙、戊，方向反了）。
  2.【表用神次序】寒燥失衡触发调候时，第一用神取《穷通宝鉴》月令表**首味**
    （不再固定取水/火——表中用神兼扶抑病药）；整串次序 t0_list 随档案存档；
    首味与寒燥方向不同时以表为准并加标注（不静默吞差异）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bazi_engine import TIAOHOU, GAN_WUXING, build_bazi_paipan  # noqa: E402


def _case(y, m, d, h, mi=0, gender=1):
    p = build_bazi_paipan(y, m, d, h, mi, gender=gender)
    x = p["xiji"]
    s5 = next(s for s in x["steps"] if s["step"] == "步骤五")
    return p, x, s5


def test_winter_month_is_cold_even_with_many_hot_chars():
    """回归①：己日主子月、火土 6 字 → 旧判燥局（反），修后必须寒局；
    回归②：调候第一用神取《穷通宝鉴》首味「丙」（火），整串 丙、戊 存档"""
    p, x, s5 = _case(1990, 12, 20, 10)
    assert p["bazi"][1]["zhi"] == "子"
    assert "寒局" in s5["logic"] and "冬水当令" in s5["logic"]
    assert x["mingju"]["T0"] == ["火"]
    assert "调候用神次序 丙、戊" in s5["logic"]
    assert x["mingju"]["t0_list"] == ["火", "土"]
    assert x["mingju"]["t0_src"] == "穷通宝鉴·月令调候表"


def test_summer_month_is_hot():
    """巳午未月 → 燥局补水（月令优先）；表 五月丙：壬、庚 → 首味壬（水）"""
    p, x, s5 = _case(1990, 6, 20, 12)
    assert p["bazi"][1]["zhi"] == "午"
    assert "燥局" in s5["logic"]
    assert x["mingju"]["T0"] == ["水"]
    assert x["mingju"]["t0_list"] == ["水", "金"]


def test_t0_follows_table_first_char():
    """不变式：寒燥触发时，T0 必＝《穷通宝鉴》该格首味的五行（不再固定水/火）"""
    for y, m, d, h, mi in ((1990, 12, 20, 10, 0), (1990, 6, 20, 12, 0), (1985, 3, 15, 8, 0),
                           (2009, 9, 4, 15, 34), (1990, 5, 15, 14, 30)):
        p, x, s5 = _case(y, m, d, h, mi)
        dm, mz = p["day_master"]["gan"], p["bazi"][1]["zhi"]
        tk = TIAOHOU.get(dm, {}).get(mz, "")
        t0 = x["mingju"]["T0"]
        if "燥局" in s5["logic"] or "寒局" in s5["logic"]:
            assert tk, f"{y}-{m}-{d}: 触发调候但表内无此格"
            want = GAN_WUXING[tk[0]]
            assert t0 == [want], f"{y}-{m}-{d}: T0={t0} ≠ 表首味 {tk[0]}({want})"
            assert x["mingju"]["t0_list"] == list(dict.fromkeys(GAN_WUXING[c] for c in tk))
            # 首味与寒燥方向不同时必须有标注（不静默）
            direction = "水" if "燥局" in s5["logic"] else "火"
            if want != direction:
                assert any("以表为准" in mk for mk in x["adjust_marks"]), (y, m, d)


def test_direction_divergence_is_marked_not_hidden():
    """表首味与寒燥方向不同时：T0 以表为准，且 adjust_marks 里有说明
    （癸日主卯月：表 庚、辛 → 首味金，而燥局方向本是水——两书取舍透明化）"""
    p, x, s5 = _case(1985, 3, 15, 8)
    assert x["mingju"]["T0"] == ["金"]                     # 表首味 庚
    assert x["mingju"]["t0_list"] == ["金"]
    assert any("以表为准" in mk for mk in x["adjust_marks"])


def test_dormant_keeps_full_list_for_reference():
    """无寒燥失衡 → 调候门休眠（T0 空），但《穷通宝鉴》整串药单仍随档案存档备查
    （戊日主酉月：表 丙、癸 → t0_list=[火,水]）"""
    p, x, s5 = _case(1990, 9, 20, 10)
    assert p["day_master"]["gan"] == "戊" and p["bazi"][1]["zhi"] == "酉"
    assert "寒暖中和" in s5["logic"]
    assert x["mingju"]["T0"] == []
    assert x["mingju"]["t0_list"] == ["火", "水"]


def test_neutral_month_uses_count_fallback():
    """中性月（申）：有根计数达 ±2 字才判寒燥——2009-09-04 金多水寒 → 寒局，
    表 七月壬 戊、丁 → 首味戊（土）"""
    p, x, s5 = _case(2009, 9, 4, 15, 34)
    assert p["bazi"][1]["zhi"] == "申"
    assert "金多水寒" in s5["logic"]
    assert x["mingju"]["T0"] == ["土"]
    assert x["mingju"]["t0_list"] == ["土", "火"]


def test_tiaohou_vs_jishen_conflict_removed_with_mark():
    """调候字落在扶抑忌方（壬日子月：寒局调候首味戊土＝身弱扶抑的官杀忌神）：
    按「寒燥失衡先调候」「调候为急，权而用之」（《子平真诠·论用神配气候得失》）
    以调候字为第一用神，且**移出忌神表**并加标记——2026-10-06 站长裁定。
    （此前口径是"忌神位仍按扶抑列出、只加标记"，页面同屏出现两个相反结论；
    此版起忌神表与显示层都不再列该五行，扶抑口径仅作岁运参考。）"""
    p, x, s5 = _case(1970, 1, 2, 8)
    assert p["day_master"]["gan"] == "壬"
    assert p["bazi"][1]["zhi"] == "子"
    assert x["mingju"]["T0"] == ["土"]                        # 《穷通宝鉴》十一月壬：首味 戊（土）
    assert x["mingju"]["J"] == []                             # 土已移出忌神表
    assert "土" not in x["layers_meta"]["jishen"]["wuxing"]   # 显示层忌神亦不列土
    assert "土（寒局调候，第一用神）" in x["layers"]["yongshen"]
    assert any("与扶抑忌方相重" in mk for mk in x["adjust_marks"])
    assert any("权而用之" in mk for mk in x["adjust_marks"])
    assert any("移出忌神表" in mk for mk in x["adjust_marks"])
    # 扶抑本义保留在 note 里（第一用神注仍写扶抑用神）
    assert "寒燥失衡先调候" in x["layers_meta"]["yongshen"]["note"]


def test_layers_view_aggregates_by_wuxing_with_sources():
    """喜忌整合视图（layers_view）：同一五行聚合一行、带维度来源标签；
    冲突行挂裁定语（壬日子月：土＝调候第一用神，扶抑忌神位已按「权而用之」移出，
    故土行只有调候·用神一条，裁定语说明移出）；
    行序按站内五行展示序 木火土金水（与 tally 同一口径，2026-10 修错位排列）"""
    p, x, s5 = _case(1970, 1, 2, 8)
    tv = {v["wx"]: v for v in x["layers_view"]}
    assert [v["wx"] for v in x["layers_view"]] == ["木", "火", "土", "金", "水"]
    assert "土" in tv
    tu = {(i["source"], i["role_label"]) for i in tv["土"]["items"]}
    assert ("调候", "用神") in tu
    assert ("扶抑", "忌神") not in tu          # 忌神位已移出（2026-10-06 权而用之）
    assert "与扶抑忌方相重" in tv["土"].get("ruling", "")
    assert "移出忌神表" in tv["土"].get("ruling", "")
    # 无冲突行不带 ruling；每个 item 都有 note 与 source
    for v in x["layers_view"]:
        for it in v["items"]:
            assert it["source"] in ("调候", "扶抑", "格局")
            assert isinstance(it["note"], str)


def test_tiaohou_vs_choushen_conflict_marked_and_fuyi_first():
    """调候字落在扶抑仇神（癸日子月：寒局调候用火＝身弱扶抑的财星仇神）：
    同样必须加标记点破（2026-10 补：此前只查忌方，落仇方时两条路线相反却无标记）；
    且行内项目按站长要求扶抑排在调候前面"""
    p, x, s5 = _case(1985, 1, 4, 8)
    assert p["day_master"]["gan"] == "癸"
    assert x["mingju"]["T0"] == ["火"]                              # 寒局调候用火
    assert "火" in x["layers_meta"]["choushen"]["wuxing"]           # 扶抑：火＝财星仇神
    assert "火" not in x["layers_meta"]["jishen"]["wuxing"]         # 不在忌方
    assert any("与扶抑仇方相重" in mk for mk in x["adjust_marks"])
    tv = {v["wx"]: v for v in x["layers_view"]}
    huo = tv["火"]["items"]
    assert huo[0]["source"] == "扶抑" and huo[0]["role_label"] == "仇神"
    assert huo[-1]["source"] == "调候" and huo[-1]["role_label"] == "用神"
    assert "与扶抑仇方相重" in tv["火"].get("ruling", "")


def test_dayun_spans_120_years():
    """大运排 12 步真大运 = 120 年（站长 2026-10 要求：默认 10 步扩到 12 步真运；
    lunar-python 第 0 步是起运前占位（空干支），故总步数 13）"""
    p = build_bazi_paipan(1995, 6, 15, 6, 0, gender=1)
    assert len(p["dayun"]["steps"]) == 13
    real = [s for s in p["dayun"]["steps"] if s["ganzhi"]]
    assert len(real) == 12                        # 12 步真大运 × 10 年 = 120 年
    assert not p["dayun"]["steps"][0]["ganzhi"]   # 第 0 步为起运前占位
    assert real[-1]["start_age"] - real[0]["start_age"] == 110


def test_tiaohou_guiyou_order_book_verbatim():
    """调候表八月癸水＝辛丙（穷通宝鉴评注 L9549「取辛为用，丙火佐之，名水暖金温」）；
    九月癸水才是「辛癸甲」（L9611「专用辛金，次用癸甲」）。
    2026-11 勘误：旧表癸酉误录九月次序「辛甲癸」（串月）。"""
    from bazi_engine import TIAOHOU, build_tiaohou
    assert TIAOHOU["癸"]["酉"] == "辛丙"
    assert TIAOHOU["癸"]["戌"] == "辛癸甲"
    t = build_tiaohou("癸", "酉")
    assert t["yongshen"] == "辛丙"
    assert "辛、丙" in t["note"] or "辛丙" in t["note"]


def test_dayun_shishen_bijian_not_rizhu():
    """大运/流年十神通例：日干见日干＝比肩（「日主」称谓仅四柱日干位使用）。
    2008-09-10 癸日主阳男：癸亥运应标比肩（旧版误标「日主」）。"""
    p = build_bazi_paipan(2008, 9, 10, 10, 33, gender=1)
    by_gz = {s["ganzhi"]: s["gan_shishen"] for s in p["dayun"]["steps"] if s["ganzhi"]}
    assert by_gz["壬戌"] == "劫财"
    assert by_gz["癸亥"] == "比肩"
    assert by_gz["甲子"] == "伤官" and by_gz["乙丑"] == "食神"
    # 四柱日干位仍为「日主」
    assert p["bazi"][2]["shishen_gan"] == "日主"
    # 流年同口径：癸亥运内癸年流年＝比肩
    guihai = next(s for s in p["dayun"]["steps"] if s["ganzhi"] == "癸亥")
    assert all(n["gan_shishen"] == "比肩" for n in guihai["liunian"] if n["gan"] == "癸")
