# -*- coding: utf-8 -*-
"""六爻逐爻细看（liuyao_liushou）回归
=====================================

三组防线：
1. **逐字回源**：表里每条 text 必须是 books/ 原文里的连续子串——改一个字即失败。
   这是"绝不代拟"在六神这一层的延伸。
2. **边界不可破**：逐爻细看只呈现，不改判定；三书没立专断的组合必须留白并标注，不许编。
3. **角色判定**：用神 > 元神 > 忌神 > 仇神 > 世 > 应 > 闲，顺序与《增删卜易·用神章》一致。

语料缺席时本文件按既有约定显式跳过（不静默通过）。
"""
import json
import re
from pathlib import Path

import pytest

from liuyao_liushou import (load_lib, per_line_readings, principle, prompt_block)
from books_corpus import read_corpus, missing_reason

_LIB = Path(__file__).parent.parent / "liuyao_liushou.json"


def _norm(s: str) -> str:
    """比对前的宽容：去掉所有空白（语料里有换行与排版空格）。"""
    return re.sub(r"\s+", "", s or "")


def _all_texts(lib: dict):
    """把表里所有需要回源的原文摘录摊平（带定位标签，便于报错）。"""
    out = []
    for q in lib["principle"]["quotes"]:
        out.append(("principle/" + q["key"], q["text"]))
    for name, b in lib["beasts"].items():
        out.append(("beast/" + name, b["quote"]))
    for role, cells in lib["cells"].items():
        for beast, c in cells.items():
            out.append("cell/%s·%s" % (role, beast), ) if False else out.append(
                ("cell/%s·%s" % (role, beast), c["text"]))
    for name, m in lib["modifiers"].items():
        out.append(("modifier/" + name, m["text"]))
    return out


# ---------------------------------------------------------------------------
# 1. 逐字回源
# ---------------------------------------------------------------------------
def test_all_cited_texts_are_verbatim_from_books():
    reason = missing_reason()
    if reason:
        pytest.skip(reason)
    corpus = _norm(read_corpus())
    misses = []
    for label, text in _all_texts(load_lib()):
        if _norm(text) not in corpus:
            misses.append("%s：%s" % (label, text[:40]))
    assert not misses, "以下引文在典籍原文里找不到（改字或错引）：\n" + "\n".join(misses)


def test_every_cell_has_src_and_plain():
    lib = load_lib()
    for role, cells in lib["cells"].items():
        assert role in lib["roles"], "未登记的角色：%s" % role
        for beast, c in cells.items():
            assert beast in lib["beasts"], "未登记的六神：%s" % beast
            for k in ("text", "src", "plain"):
                assert c.get(k), "%s·%s 缺 %s" % (role, beast, k)
            assert "L" in c["src"] or "章" in c["src"], "%s·%s 出处未带行号/篇章" % (role, beast)


def test_principle_quotes_cover_three_books():
    """边界声明必须同时引到《黄金策》《卜筮正宗》《增删卜易》三家。"""
    qs = principle()["quotes"]
    joined = "".join(q["src"] for q in qs)
    assert "黄金策" in joined and "卜筮正宗" in joined and "增删卜易" in joined


# ---------------------------------------------------------------------------
# 2. 逐爻细看的行为
# ---------------------------------------------------------------------------
def _line(pos, liushen, liuqin, gan, zhi, wx, **kw):
    d = {"position": pos, "name": liuqin + gan + zhi, "liushen": liushen, "liuqin": liuqin,
         "gan": gan, "zhi": zhi, "wuxing": wx, "shi": False, "ying": False,
         "moving": False, "xunkong": False, "yuepo": False}
    d.update(kw)
    return d


@pytest.fixture()
def zhanzhang_case():
    """站长实测那一局：世二爻勾陈官鬼辛亥、应五爻玄武子孙己未、上爻青龙兄弟己巳老阳动且旬空。

    日干丁 → 朱雀起初爻（《卜筮正宗·六兽起例》"从下装起"），与页面一致。
    """
    gua = {"lines": [
        _line(1, "朱雀", "子孙", "辛", "丑", "土"),
        _line(2, "勾陈", "官鬼", "辛", "亥", "水", shi=True),
        _line(3, "螣蛇", "妻财", "辛", "酉", "金"),
        _line(4, "白虎", "妻财", "己", "酉", "金"),
        _line(5, "玄武", "子孙", "己", "未", "土", ying=True),
        _line(6, "青龙", "兄弟", "己", "巳", "火", moving=True, xunkong=True),
    ]}
    remedy = {"details": {"用神爻": {"position": 3},
                          "元神": {"六亲": "子孙", "五行": "土"},
                          "忌神": {"六亲": "兄弟", "五行": "木"}}}
    return gua, remedy


def test_six_rows_and_beast_nature_always_present(zhanzhang_case):
    gua, remedy = zhanzhang_case
    rows = per_line_readings(gua, remedy)
    assert len(rows) == 6
    for r in rows:
        assert r["六神"], "每爻都应有六神"
        assert r["断语"], "每爻至少要有兽性一条"
        assert r["断语"][0]["kind"] == "兽性"


def test_zhangzhang_case_line6_gets_move_and_void(zhanzhang_case):
    gua, remedy = zhanzhang_case
    r6 = per_line_readings(gua, remedy)[5]
    assert (r6["六神"], r6["六亲"], r6["干支"], r6["动静"]) == ("青龙", "兄弟", "己巳", "动")
    assert r6["旬空"] is True
    kinds = [i["kind"] for i in r6["断语"]]
    # 兄弟是忌神，《六兽评论第七》"青龙……附忌神凡谋不利"正好对上；再加"动"与"旬空"两条状态
    assert "忌神·青龙" in kinds and "动" in kinds and "旬空" in kinds
    assert all(i["src"] for i in r6["断语"]), "每条断语都必须带出处"


def test_no_dogma_means_no_invented_sentence(zhanzhang_case):
    """三书没立专断的爻：只列兽性，并明确说明，不许编一句话填满。"""
    gua, remedy = zhanzhang_case
    r4 = per_line_readings(gua, remedy)[3]       # 四爻 白虎·妻财·静 → 闲爻，三书无专断
    assert r4["有专断"] is False
    assert len(r4["断语"]) == 1 and r4["断语"][0]["kind"] == "兽性"
    assert r4["无专断说明"]


def test_role_priority_and_choushen(zhanzhang_case):
    """角色判定：用神优先；仇神＝生忌神者（忌神木 → 仇神水）。"""
    gua, remedy = zhanzhang_case
    rows = per_line_readings(gua, remedy)
    assert rows[2]["角色"] == "用神"          # 三爻即用神爻
    assert rows[5]["角色"] == "忌神"          # 兄弟为忌神
    # 二爻官鬼亥：功能上是仇神（水生忌神木），同时它持世——两个身份都标出来，
    # 角色记功能、卦位记世应，页面两处都显示。
    assert rows[1]["角色"] == "仇神" and rows[1]["卦位"] == "世"
    gua2 = {"lines": [_line(1, "玄武", "官鬼", "辛", "亥", "水")]}
    remedy2 = {"details": {"用神爻": {"position": 9}, "元神": {"六亲": "子孙", "五行": "土"},
                           "忌神": {"六亲": "兄弟", "五行": "木"}}}
    assert per_line_readings(gua2, remedy2)[0]["角色"] == "仇神"   # 官鬼水＝生忌神木者


def test_prompt_block_carries_boundary_and_forbids_new_text(zhanzhang_case):
    gua, remedy = zhanzhang_case
    block = prompt_block(per_line_readings(gua, remedy))
    assert "不得新增断语" in block and "不得拿六神改任何吉凶结论" in block
    assert "虎兴而遇吉神" in block or "六亲本也" in block
    for beast in ("青龙", "朱雀", "白虎", "玄武"):
        assert beast in block
    assert "第6爻" in block


def test_json_is_valid_and_versioned():
    data = json.loads(_LIB.read_text(encoding="utf-8"))
    assert data["version"]
    assert set(data["beasts"]) == {"青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武"}
    assert "六亲本也" in data["principle"]["summary"] or "附和之神" in data["principle"]["summary"]
