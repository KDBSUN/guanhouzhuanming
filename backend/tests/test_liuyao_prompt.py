# -*- coding: utf-8 -*-
"""
六爻断语 prompt 必须携带确定性算好的用神与处方五行（"确定性归代码，语言归 AI"）。
背景 bug：用户起卦前手动选定用神，但 AI 材料里没有该信息，断语文本自行取用神，
结果页置信度标签也因字段名错位永远显示"自动"。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from liuyao_engine import build_paipan          # noqa: E402
from liuyao_remedy import liuyao_remedy         # noqa: E402
from main import build_liuyao_user_prompt       # noqa: E402


def _gua():
    return build_paipan([{"x": 1.1, "y": 2.2, "duration": 300, "speed": 0.5}] * 6)


def test_prompt_carries_manual_yongshen():
    """手动指定用神 → prompt 的【用神】节必须标注'用户手动指定'并附判定依据"""
    g = _gua()
    g["remedy"] = liuyao_remedy(g, "这次跳槽能成吗", "官鬼")
    assert g["remedy"]["yongshen_source"] == "manual"
    p = build_liuyao_user_prompt(g, "这次跳槽能成吗")
    assert "【用神】官鬼（用户手动指定，必须以此用神为主线断卦，不得另行取用）" in p
    assert "手动指定：以官鬼爻为用神" in p
    assert "【事体与处方】" in p and g["remedy"]["R"] in p


def test_prompt_auto_yongshen_marked_auto():
    """自动判定 → prompt 标注'自动判定'，不带'手动指定'字样"""
    g = _gua()
    g["remedy"] = liuyao_remedy(g, "这次跳槽能成吗")
    assert g["remedy"]["yongshen_source"] == "auto"
    p = build_liuyao_user_prompt(g, "这次跳槽能成吗")
    assert "代码按《增删卜易·用神章》自动判定" in p
    assert "用户手动指定" not in p


def test_prompt_without_remedy_has_no_yongshen_section():
    """处方计算失败（remedy=None）→ 不输出用神节，AI 回退自行取用"""
    g = _gua()
    g["remedy"] = None
    p = build_liuyao_user_prompt(g, "测一测")
    assert "【用神】" not in p
    assert "【事体与处方】" not in p


# ============================================================================
# 数据层：把"已经算了却没给 AI"的字段接上（否则 AI 自己推旺衰 = 幻觉第一来源）
# ============================================================================

def _gua_with_remedy(q="这次跳槽能成吗"):
    g = _gua()
    g["remedy"] = liuyao_remedy(g, q)
    return g


def test_remedy_exposes_per_line_strength():
    """契约：remedy.details 必须暴露每爻旺衰（旺相/休囚 二分）+ 月令五态 + 分数 + 标志

    2026-09-23 改口径：综合旺衰由三档（旺相/平/衰）改为二分（旺相/休囚），
    与《卜筮正宗·四时旺相》两桶、《增删卜易·暗动章》两分对齐；书无明文的「平」去除。
    月令一项单列五态（旺相休囚死，书证《五行大义·论四时休王》《渊海子平》）。
    """
    d = _gua_with_remedy()["remedy"]["details"]
    assert "月建日辰" in d and "各爻旺衰" in d
    per = d["各爻旺衰"]
    assert len(per) == 6, "六爻必须逐爻给出旺衰"
    for row in per:
        assert row["旺衰"] in ("旺相", "休囚")
        assert row["月令五态"] in ("旺", "相", "休", "囚", "死")
        assert isinstance(row["分数"], int)
        assert isinstance(row["标志"], list)
        assert row["五行"] in ("金", "木", "水", "火", "土")
    md = d["月建日辰"]
    assert md["月建"] and md["月建五行"] and md["日辰"] and md["日辰五行"]
    # 卦气表＝月令五态逐五行取值：当令者旺、令生者相、生令者休、克令者囚、令克者死
    assert set(md["卦气"]) == {"金", "木", "水", "火", "土"}
    assert md["卦气"][md["月建五行"]] == "旺"
    assert set(md["卦气"].values()) == {"旺", "相", "休", "囚", "死"}


def test_composite_two_way_matches_book_buckets_when_month_is_the_only_term():
    """不变式：只有月令一项时，二分结果必与书的两桶一致——
    旺、相 → 旺相；休、囚、死 → 休囚（《卜筮正宗·四时旺相》「此八者旺相/此八者休囚」）"""
    from liuyao_remedy import _line_strength, SHIWANG_RANK
    line = {"zhi": "寅", "wuxing": "木", "moving": False}     # 不临月建/日辰、无空破
    for month_wx, want_state, want_grade in (("木", "旺", "旺相"), ("水", "相", "旺相"),
                                            ("火", "休", "休囚"), ("土", "囚", "休囚"),
                                            ("金", "死", "休囚")):
        g, score, flags = _line_strength(line, "木", "午", month_wx, "午", "火", [line])
        assert score == SHIWANG_RANK[want_state], (month_wx, score)
        assert g == want_grade, (month_wx, g)
        assert f"{want_state}于月令" in flags


def test_prompt_carries_per_line_strength():
    """prompt 的【各爻旺衰】必须六爻齐全，且带得出月令五态与标志（否则 AI 只能自己推）"""
    p = build_liuyao_user_prompt(_gua_with_remedy(), "这次跳槽能成吗")
    assert "【各爻旺衰（代码判定，照此解释，不得重算、不得自行加减分）】" in p
    for name in ("初爻", "二爻", "三爻", "四爻", "五爻", "上爻"):
        assert ("  %s " % name) in p, f"{name} 旺衰未注入"
    assert "旺衰旺相｜月令" in p or "旺衰休囚｜月令" in p


def test_prompt_carries_month_day_and_gua_ti():
    """月建日辰与卦气；本卦卦体（上下卦+宫五行+卦身）"""
    g = _gua_with_remedy()
    p = build_liuyao_user_prompt(g, "这次跳槽能成吗")
    t = g["time_info"]
    assert "【月建日辰（代码判定，不得重算）】" in p
    assert "月建 " + t["month_branch"] in p
    assert "【本卦卦体】" in p
    assert "上卦 " in p and "下卦 " in p
    assert "宫五行 " + g["palace_wuxing"] in p
    # 卦身一律用**月卦身**（《卜筮正宗·安月卦身诀》L502）。
    # 旧的 gua_shen 是《卜筮全书》"子午持世身居初"的**世身**，被《卜筮正宗》L1158
    # 斥为"大误于事……诸谬甚矣"，不得再当卦身注入。
    assert "卦身（月卦身）" in p and g["yue_guashen"] in p


def test_prompt_carries_yongshen_yuanshen_jishen_positions():
    """用神爻位 + 元神有力无力 + 忌神爻位旺衰 —— 断吉凶的第一环"""
    p = build_liuyao_user_prompt(_gua_with_remedy(), "这次跳槽能成吗")
    assert "【用神爻位】" in p and "旺衰 " in p
    assert "【元神】" in p and ("有力" in p or "无力" in p)
    assert "【忌神】" in p
    assert "【用神置信度】" in p


def test_prompt_carries_laoshao_yinyang():
    """排盘行必须带老少阴阳（老阳/老阴才动），否则只看得到'○动'"""
    p = build_liuyao_user_prompt(_gua_with_remedy(), "这次跳槽能成吗")
    assert any(k in p for k in ("老阳", "老阴", "少阳", "少阴"))


def test_state_label_is_not_duplicated():
    """回归：曾输出「（用神平：用神平（长生于日），…）」——state 与 R_reason 重复"""
    p = build_liuyao_user_prompt(_gua_with_remedy(), "这次跳槽能成吗")
    for line in p.split("\n"):
        if "【事体与处方】" in line:
            body = line.split("（", 1)[1]
            head = body.split("：", 1)[0]
            assert not body.startswith(head + "："), f"state 与 R_reason 重复：{line}"


# ============================================================================
# 月卦身：《卜筮正宗·安月卦身诀》"阴世则从午月起，阳世还从子月生。欲得识其卦中意，
# 从初数至世方真。" 用书自己的例子校验——乾宫首卦世在上爻（阳世），初起子数至上爻得巳；
# 乾卦六爻支为子寅辰午申戌，无巳，故书中逐卦注"本卦无卦身"。
# ============================================================================

def test_yue_guashen_matches_book_example_qian():
    from liuyao_engine import line_from_coins, _build_paipan_from_raw
    from datetime import datetime
    raw = []
    for _ in range(6):                      # 乾为天：六爻皆少阳（阳、静）
        L = line_from_coins([0, 0, 1])
        L["coins"] = [0, 0, 1]
        raw.append(L)
    g = _build_paipan_from_raw(raw, datetime(2026, 9, 19, 14, 30))
    assert g["ben_gua"]["name"] == "乾为天"
    assert [l["zhi"] for l in g["lines"]] == ["子", "寅", "辰", "午", "申", "戌"]
    assert g["yue_guashen"] == "巳"                  # 阳世，初起子，数至上爻
    assert g["yue_guashen_positions"] == []          # 卦中无巳
    assert g["yue_guashen_in_gua"] is False          # 书注"本卦无卦身"


def test_gua_shen_field_is_shi_shen_not_guashen():
    """gua_shen 是《卜筮全书》的世身，与月卦身是两回事，必须分列"""
    from liuyao_engine import build_paipan
    g = build_paipan([{"x": 1.1, "y": 2.2, "duration": 300, "speed": 0.5}] * 6)
    assert g["gua_shen"] == g["shi_shen"], "世身字段应同值"
    assert "yue_guashen" in g and "yue_guashen_positions" in g
    # 世身是"爻位"，月卦身是"地支"——类型不同，不可互相顶替
    assert isinstance(g["gua_shen"], int)
    assert isinstance(g["yue_guashen"], str)
