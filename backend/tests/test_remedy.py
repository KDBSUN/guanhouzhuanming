# -*- coding: utf-8 -*-
"""
处方五行回归（remedy.py 梅花 + liuyao_remedy.py 六爻）
=====================================================
梅花 R 按《体用总诀》体用生克与《心易衰旺之诀》卦气；
六爻用神按《增删卜易·用神章》定例，手动指定参照梅花体用的
"机械确定性"思路（封闭枚举锁定，不从问话自由文本猜测）。
"""
import pytest

from remedy import meihua_remedy
from liuyao_remedy import (classify_yongshen, classify_yongshen_detail,
                           _yuanshen_jishen, _pick_yongshen_line)

# ---------------------------------------------------------------------
# 梅花易数 R（《体用总诀》）
# ---------------------------------------------------------------------

def test_yong_ke_ti():
    # 用金克体木 → R=克用者火（制用通关）
    r = meihua_remedy("木", "金", "用克体")
    assert r["X"] == "金" and r["R"] == "火"
    assert "制用" in r["R_reason"]

def test_yong_ke_ti_plus_bian_ke_ti():
    # 用金克体木 且 变卦金又克体 → R=克用者火，R_alt=克变者火（防末后之凶）
    r = meihua_remedy("木", "金", "用克体", bian_wuxing=["金"])
    assert r["R"] == "火" and r["R_alt"] == "火"
    assert any("末后" in n for n in r["notes"])

def test_bian_ke_ti_only():
    # 用生体但变卦金克体（末后不吉）→ R=克变者火，理由注明"变卦克体"
    r = meihua_remedy("木", "水", "用生体", bian_wuxing=["金"])
    assert r["R"] == "火"
    assert "变卦" in r["R_reason"] and "制变" in r["R_reason"]

def test_ti_shuai():
    # 体卦失令（休囚死）→ R=生体者（衰旺之诀优先于比和取本气）
    r = meihua_remedy("木", "木", "比和", ti_status="囚")
    assert r["R"] == "水"
    assert "体卦失令" in r["R_reason"]

def test_ti_sheng_yong():
    # 体生用为泄 → R=生体者
    r = meihua_remedy("木", "火", "体生用")
    assert r["R"] == "水"

def test_yong_sheng_ti():
    # 用生体为吉 → 顺其生势 R=用
    r = meihua_remedy("木", "水", "用生体")
    assert r["R"] == "水"

def test_ti_ke_yong_and_bihe():
    assert meihua_remedy("金", "木", "体克用")["R"] == "金"
    assert meihua_remedy("木", "木", "比和")["R"] == "木"

def test_hu_sheng_note():
    # 互卦生体 → 中间渐有转机
    r = meihua_remedy("木", "金", "用克体", hu_wuxing=["水"])
    assert any("转机" in n for n in r["notes"])

def test_invalid_wuxing():
    with pytest.raises(ValueError):
        meihua_remedy("木", "岩", "比和")


# ---------------------------------------------------------------------
# 六爻用神（《增删卜易·用神章》）
# ---------------------------------------------------------------------

@pytest.mark.parametrize("question,expect", [
    ("孩子这次考试怎么样", "子孙"),     # 人主体优先：占子孙
    ("我的婚姻如何", "妻财"),           # 事类：婚姻以财为用（男占）
    ("这次考编能上岸吗", "官鬼"),       # 事类：功名以官鬼为用
    ("买这套房子合适吗", "父母"),       # 事类：宅舍以父母为用
    ("我最近运势如何", "世"),           # 自占疾病/自身/出行 → 世爻
    ("今天出门顺利吗", "世"),
])
def test_classify_auto(question, expect):
    assert classify_yongshen(question)[0] == expect

@pytest.mark.parametrize("override,expect", [
    ("父母", "父母"), ("兄弟", "兄弟"), ("子孙", "子孙"),
    ("妻财", "妻财"), ("官鬼", "官鬼"), ("世", "世"), ("自占", "世"),
])
def test_classify_manual_beats_question(override, expect):
    # 手动指定优先：问话里出现别的六亲线索也不改判
    src = classify_yongshen("我的婚姻如何", override)[1]
    assert src == "manual"
    assert classify_yongshen("我的婚姻如何", override)[0] == expect

def test_yuanshen_jishen_wife():
    # 以妻财为用（卦宫金）：元神=子孙（水），忌神=兄弟（金，与卦宫同气）
    ys_name, ys_wx, js_name, js_wx = _yuanshen_jishen("金", "妻财")
    assert (ys_name, js_name) == ("子孙", "兄弟")
    assert ys_wx == "水" and js_wx == "金"

def test_pick_line_manual_override():
    lines = [
        {"pos": 1, "liuqin": "父母", "wuxing": "火", "shi": False, "ying": False, "moving": False},
        {"pos": 2, "liuqin": "妻财", "wuxing": "木", "shi": False, "ying": False, "moving": True},
        {"pos": 3, "liuqin": "妻财", "wuxing": "土", "shi": False, "ying": False, "moving": False},
        {"pos": 4, "liuqin": "官鬼", "wuxing": "水", "shi": True, "ying": False, "moving": False},
    ]
    # 手动指定妻财：动爻优先于先见
    assert _pick_yongshen_line(lines, "妻财")["wuxing"] == "木"
    # 手动指定世（自占）
    assert _pick_yongshen_line(lines, "世")["liuqin"] == "官鬼"
    # 用神不现（如兄弟）→ None（上层回退世爻）
    assert _pick_yongshen_line(lines, "兄弟") is None


# ---------------------------------------------------------------------
# 用神两档流程（高置信直接断 / 低置信起卦前二选确认）
# ---------------------------------------------------------------------

def test_detail_high_person_beats_world():
    # 书例"父亲病情"→父母爻高置信：人主体在场时"世"（病）不算独立候选
    d = classify_yongshen_detail("父亲的病情能好转吗")
    assert d["confidence"] == "high" and d["liuqin"] == "父母"
    assert any(m["kw"] == "父亲" for m in d["matched"])
    assert "世" not in d["candidates"]

def test_detail_low_multi_candidates():
    # 朋友（兄弟·人主体）+ 生意（妻财·事类）→ 低置信多候选，人主体排前
    d = classify_yongshen_detail("跟朋友合伙做生意能成吗")
    assert d["confidence"] == "low"
    assert set(d["candidates"]) >= {"兄弟", "妻财"}
    assert d["liuqin"] == "兄弟"

def test_detail_ambig_trigger():
    # 天然歧义词"合作"：问合伙之人（兄弟）还是生意钱财（妻财）
    d = classify_yongshen_detail("想跟人合作，行吗")
    assert d["confidence"] == "low"
    assert set(d["candidates"]) == {"兄弟", "妻财"}

def test_detail_manual_and_default():
    d = classify_yongshen_detail("我的婚姻如何", "官鬼")
    assert d["confidence"] == "manual" and d["liuqin"] == "官鬼"
    d2 = classify_yongshen_detail("帮我看看")
    assert d2["confidence"] == "default" and d2["liuqin"] == "世"
