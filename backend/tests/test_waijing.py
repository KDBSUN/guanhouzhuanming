# -*- coding: utf-8 -*-
"""
外应参断回归（waijing.py）
==========================
规则来源全部经回源核验（见 docs/产品逻辑链框架.md 第 12 节）。本文件守三件事：

  1. **配卦与参断按原文条例走**：十应诀诸应／类象表／形物占／听声音占／器物归卦；
  2. **不代拟**：原文未直断的组合（体生外应、体克外应）不得给吉凶；配卦有歧义或
     无命中时不得猜；且**引文必须是 books/ 内原文子串**（把"绝不代拟"延伸到本模块）；
  3. **不改卦**：任何路径下 moves_gua 恒为 False——不重起、不动体用互变、不换动爻。
"""
import json
import re
from pathlib import Path

import pytest

import waijing as wj
import books_corpus

_XIANG_PATH = Path(__file__).resolve().parents[1] / "waijing_xiang.json"


# ---------- 1. 逐字回源：本模块用到的原文必须真在书里 ----------

def _norm(s: str) -> str:
    s = re.sub(r"[\u2460-\u2473]", "", s)          # 圈码脚注
    return re.sub(r"\s+", "", s)


def test_all_cited_texts_are_verbatim_from_books():
    """waijing_xiang.json 里每一段 text 都必须是 books/ 内原文的逐字子串。

    与 test_quotes.py 同一思路：引文一旦被改写、拼装或代拟，这里立刻红。
    外应参断直接面向用户输出"书证"，所以必须受同一条红线约束。
    """
    reason = books_corpus.missing_reason()
    if reason:
        pytest.skip(reason)
    full = _norm(books_corpus.read_corpus())

    d = json.loads(_XIANG_PATH.read_text(encoding="utf-8"))
    frags = [("qiwu_guaxiang", d["qiwu_guaxiang"]["text"]),
             ("xingwu", d["xingwu"]["text"]),
             ("shengyin", d["shengyin"]["text"])]
    for name, item in d["shiying"]["items"].items():
        frags.append(("shiying." + name, item["text"]))

    miss = [(k, _norm(t)[:40]) for k, t in frags
            if len(_norm(t)) >= 6 and _norm(t).rstrip("。；，、") not in full]
    assert not miss, "以下外应引文不是 books/ 内逐字原文: %s" % miss


def test_bagua_entries_are_verbatim_from_books():
    """八卦万物属类的**每一条**都必须逐字来自底本。

    为什么单独立一条：上面的 `frags` 只收了 3 段总诀 + 十应诀的 `text` 字段，
    而 `bagua` 段（8 卦 × 约 30 维度、916 个条目）**一直不在名单里**——
    2026-09-24 手工核对时发现这层是空的：数据当时是对的（916 条全部逐字命中），
    但"它是对的"没有被机器守住，谁改一个字都不会红。
    万物搜索（/api/meihua/wanwu_search）与手动起卦页的类象表都直接展示这些条目，
    所以它们与总诀引文受同一条红线约束。
    """
    reason = books_corpus.missing_reason()
    if reason:
        pytest.skip(reason)
    full = _norm(books_corpus.read_corpus())
    d = json.loads(_XIANG_PATH.read_text(encoding="utf-8"))
    miss = []
    for gua, g in d["bagua"].items():
        for field, v in g.items():
            if field.startswith("_") or not isinstance(v, list):
                continue
            for it in v:
                t = _norm(str(it))
                if t and t not in full:
                    miss.append((gua, field, str(it)))
    assert not miss, "以下类象条目不是 books/ 内逐字原文: %s" % miss[:20]


def test_bagua_line_anchors_point_at_the_field():
    """带行号的维度，行号那一行必须以「维度名：」开头。

    `_lines` 是页面上"行号可回源"的锚；锚错了，用户点到的就不是那句话。
    2026-09-24 实测 214/214 全对——这条把当时的手工核对固化下来。
    """
    reason = books_corpus.missing_reason()
    if reason:
        pytest.skip(reason)
    mh = None
    for p in books_corpus.corpus_files():
        if p.name.startswith("梅花易数") and p.suffix == ".txt":
            mh = p
            break
    if mh is None:
        pytest.skip("底本 梅花易数.txt 不在语料内，行号锚点无从核对")
    lines = mh.read_text(encoding="utf-8", errors="replace").splitlines()
    d = json.loads(_XIANG_PATH.read_text(encoding="utf-8"))
    pat = re.compile(r"^\s*(天时|地理|人物|人事|身体|时序|静物|动物|屋舍|屋宿|家宅|饮食|婚姻|生产|"
                     r"求名|求利|交易|谋望|出行|谒见|疾病|官讼|坟墓|姓字|数目|方道|五味|五色)：")
    bad = []
    for gua, g in d["bagua"].items():
        for field, ln in (g.get("_lines") or {}).items():
            if not isinstance(ln, int) or not (0 < ln <= len(lines)):
                bad.append((gua, field, ln, "行号越界"))
            elif not pat.match(lines[ln - 1]):
                bad.append((gua, field, ln, lines[ln - 1][:40]))
    assert not bad, "行号锚点对不上: %s" % bad[:20]


def test_shiying_quotes_are_the_verified_ones():
    """十应诀诸应引文要与核验过的原文一致（防日后被顺手改写）。"""
    items = wj._XIANG["shiying"]["items"]
    assert "晴明为离，雨雪为坎，风为巽，雷为震" in items["天时应"]["text"]
    assert "在竹林间，为震、巽之地" in items["地理应"]["text"]
    assert "老人为乾，老妇为坤，少男为艮，少女为兑" in items["人事应"]["text"]
    assert "外应者，外卦之应也" in wj._XIANG["shiying"]["note"]


# ---------- 2. 配卦：五级来源 ----------

@pytest.mark.parametrize("text,gua", [
    ("外面下起了大雨", "坎"),        # 十应诀·天时应
    ("刮起了大风", "巽"),
    ("打了一声雷", "震"),
    ("天很晴", "离"),
    ("遇到一位老人", "乾"),          # 十应诀·人事应
    ("见到一位老妇", "坤"),
    ("一个少男", "艮"),
    ("一个小女孩", "兑"),
    ("竹林里", "震"),                # 十应诀·地理应（震巽之地）
    ("江河边", "坎"),
    ("敲钟的声音", "乾"),            # 听声音占
    ("鼓声", "震"),
    ("烧火的烈焰爆竹声", "离"),
    ("一只鸡", "巽"),                # 类象·动物
    ("一匹马", "乾"),
    ("一头牛", "坤"),
    ("一条鱼", "坎"),
    ("一副金玉镯子", "乾"),          # 类象·静物
    ("方形的布帛", "坤"),
    ("一个圆形的球", "乾"),          # 形物占
    ("一个破碎的碗", "兑"),
    ("一杯水", "坎"),                # 器物归卦（五行气）
])
def test_resolve_omen_hits_expected_gua(text, gua):
    r = wj.resolve_omen(text)
    assert gua in {c["gua"] for c in r["candidates"]}, (text, r["candidates"])


def test_resolve_omen_never_guesses():
    """配不到就返回空，绝不猜——这是本模块唯一的硬规矩。"""
    r = wj.resolve_omen("今天心情有点复杂说不清楚")
    assert r["candidates"] == []
    assert "不会替你猜" in r["note"]


def test_resolve_omen_marks_extrapolation():
    """类推命中的必须标 extrapolated，且排在原文命中之后。"""
    r = wj.resolve_omen("一只黑猫趴在墙头")
    assert any(c["extrapolated"] for c in r["candidates"]), r["candidates"]
    flags = [c["extrapolated"] for c in r["candidates"]]
    assert flags == sorted(flags), "类推项必须排在原文项之后"
    # 纯类推（原文一条都没中）
    r2 = wj.resolve_omen("邻居家的小孩在哭")
    assert r2["extrapolated"] is True


def test_resolve_omen_ambiguous_needs_choice():
    """一应可归数卦时不得替用户拍板。"""
    r = wj.resolve_omen("一只老虎在树林里")
    assert r["ambiguous"] is True and len({c["gua"] for c in r["candidates"]}) > 1
    assert "不替你拍板" in r["note"]


# ---------- 3. 与体卦论生克比和 ----------

def test_relation_directions():
    assert wj.relation_of("木", "金") == "外应克体"      # 金克木
    assert wj.relation_of("木", "水") == "外应生体"      # 水生木
    assert wj.relation_of("木", "木") == "比和"
    assert wj.relation_of("木", "火") == "体生外应"      # 木生火
    assert wj.relation_of("木", "土") == "体克外应"      # 木克土


def test_effects_follow_shiying_mulun():
    """《十应目论》：生体可解其不吉、克体反破其吉、比和助吉。"""
    assert wj.adjudicate("木", "坎")["effect"] == "可以解其不吉"   # 水（坎）生木
    assert wj.adjudicate("木", "乾")["effect"] == "反破其吉"       # 金（乾）克木
    assert wj.adjudicate("木", "巽")["effect"] == "助吉"           # 木木比和


def test_neiyi_neiwai_does_not_invent():
    """原文未直断的两种关系不得给吉凶——不代拟。"""
    for ti, gua in (("木", "离"), ("木", "坤")):      # 体生外应 / 体克外应
        a = wj.adjudicate(ti, gua)
        assert a["polarity"] == "须详理", a
        assert "未直断" in a["src"], a


def test_adjudication_carries_src():
    """每条断语都要带书证，供 UI 回源。"""
    a = wj.adjudicate("木", "乾")
    assert "十应目论" in a["src"]
    assert a["reason"].startswith("体木")


# ---------- 4. 向背与动静：只调强弱迟速，不改吉凶 ----------

def test_modulate_direction_and_motion():
    m = wj.modulate("来", "动")
    assert m["strength"] == "强" and m["timing"] == "应期速"
    m2 = wj.modulate("去", "不动")
    assert m2["strength"] == "弱" and m2["timing"] == "吉凶未见"
    m3 = wj.modulate()
    assert m3["strength"] == "中" and "不臆断" in m3["notes"][0]


# ---------- 5. 内外合断 ----------

@pytest.mark.parametrize("inner,ti,gua,verdict", [
    ("顺", "木", "坎", "断然吉"),        # 内吉 + 外应生体（吉）→ 全吉
    ("逆", "木", "乾", "断然凶"),        # 内凶 + 外应克体（凶）→ 全凶
    ("平", "木", "坎", "事体半吉半凶，须详理"),
])
def test_combine_inner_outer(inner, ti, gua, verdict):
    c = wj.combine(inner, [wj.adjudicate(ti, gua)])
    assert c["verdict"] == verdict, c


def test_combine_left_right_uses_user_chosen_version():
    """外应与内卦相左时，按**用户选定的学林本**读法：终局随内卦。

    用户裁定原话："应凶终吉"。即「卦吉而应凶终吉。卦凶而应吉终凶」——
    外应相左不足以翻转内卦，但「事体」层面标为半吉半凶。这是默认策略。
    """
    c1 = wj.combine("顺", [wj.adjudicate("木", "乾")])      # 内吉 + 外应克体（凶）
    assert c1["verdict"].startswith("终吉") and c1["polarity"] == "吉"
    assert "卦吉而应凶终吉" in c1["src"]
    c2 = wj.combine("逆", [wj.adjudicate("木", "坎")])      # 内凶 + 外应生体（吉）
    assert c2["verdict"].startswith("终凶") and c2["polarity"] == "凶"
    assert "卦凶而应吉终凶" in c2["src"]
    assert c1["policy"] == "gua_first"


def test_combine_alternate_policy_keeps_shiying_mulun():
    """另一条同样逐字可验的读法（《十应目论》"反破其吉"）保留为可切换策略。

    两句不是谁抄错，而是层次不同：三要灵应篇讲"终局归谁"，十应目论讲"外卦如何参与权衡"。
    故不删除，只改 policy 即可切换——免得哪天要改回来又得重推一遍。
    """
    c = wj.combine("顺", [wj.adjudicate("木", "乾")], policy="omen_breaks")
    assert c["verdict"] == "反破其吉" and c["polarity"] == "凶"
    assert "十应目论" in c["src"]
    c2 = wj.combine("逆", [wj.adjudicate("木", "坎")], policy="omen_breaks")
    assert c2["verdict"] == "可以解其不吉"


def test_combine_requires_all_for_duanran():
    """「全吉」「全凶」要求诸应一致——几条外应一吉一凶时不能取最坏的当结论。

    原文说"若内外卦**全**吉，则断然吉；**全**凶则断然凶"，"全"字有分量；
    混杂时据同段末句"又须详理以断吉凶"，应落在"事体半吉半凶"那一档。
    回归的是一个真实逻辑错：曾把"内逆 + 一吉一凶"判成"断然凶"。
    """
    mixed = [wj.adjudicate("木", "坎"), wj.adjudicate("木", "乾")]   # 生体(吉) + 克体(凶)
    assert {e["polarity"] for e in mixed} == {"吉", "凶"}
    c = wj.combine("逆", mixed)
    assert c["outer"] == "杂"
    assert c["verdict"] == "事体半吉半凶，须详理", c
    # 全凶 / 全吉 仍照原文直断
    assert wj.combine("逆", [wj.adjudicate("木", "乾")])["verdict"] == "断然凶"
    assert wj.combine("顺", [wj.adjudicate("木", "坎")])["verdict"] == "断然吉"


def test_combine_without_omen_follows_jingzhan():
    """无所闻见则不论外卦，径以体用决之（《静占》）。"""
    c = wj.combine("顺", [])
    assert c["verdict"] == "内卦照旧"
    assert "静占" in c["src"]


def test_combine_undecided_marks_detail():
    """含'须详理'的外应时，合断要标出来，不假装已定。"""
    c = wj.combine("顺", [wj.adjudicate("木", "坤")])
    assert c["has_undecided"] is True


# ---------- 6. 不改卦（红线） ----------

def test_never_moves_gua():
    for text in ("外面下起了大雨", "今天心情复杂", "一只黑猫"):
        r = wj.analyze(text, "木", inner_net="顺")
        assert r["moves_gua"] is False
        assert "不动" in r["moves_gua_say"]
    r2 = wj.analyze_many(["大雨", "敲钟"], "木", inner_net="平")
    assert r2["moves_gua"] is False
    for it in r2["items"]:
        assert it["moves_gua"] is False


def test_ambiguous_does_not_auto_pick():
    """多卦候选时 analyze 不自动选用，交回用户。"""
    r = wj.analyze("一只老虎在树林里", "土", inner_net="顺")
    assert r["needs_choice"] is True
    assert r["chosen_gua"] == ""
    assert r["adjudication"] is None
    # 用户指定后即可判定
    r2 = wj.analyze("一只老虎在树林里", "土", chosen_gua="艮", inner_net="顺")
    assert r2["chosen_gua"] == "艮" and r2["adjudication"]["gua"] == "艮"


def test_unmatched_does_not_participate_in_combine():
    """没配到卦的外应不能参与加减——否则等于拿空气去改结论。"""
    res = wj.analyze_many(["今天心情复杂", "外面下起了大雨"], "木", inner_net="顺")
    assert res["needs_choice"] == ["今天心情复杂"]
    # 合断只由"大雨→坎"这一条决定
    assert res["combined"]["outer"] == "吉"


# ---------- 7. 交给 LLM 的上下文块：钉死判定、禁止改写 ----------

def test_prompt_block_pins_the_verdict():
    res = wj.analyze_many(["外面下起了大雨"], "木", inner_net="顺")
    block = wj.to_prompt_block(res)
    assert "不得改写" in block
    assert "内卦不动" in block
    assert "反破其吉" in block or "可以解其不吉" in block
    assert "书证" in block


def test_prompt_block_forbids_inventing():
    """配不到／有歧义时，明确要求 AI 不要自行配卦或选定。"""
    b1 = wj.to_prompt_block(wj.analyze_many(["今天心情复杂"], "木", inner_net="顺"))
    assert "不要凭空配卦" in b1
    b2 = wj.to_prompt_block(wj.analyze_many(["一只老虎在树林里"], "土", inner_net="顺"))
    assert "不要自行选定" in b2


def test_version_note_records_the_settled_choice():
    """版本声明要写明**已定哪一版**，并交代与另一条相反读法的关系。

    早期这句只是"两版相反、待定"；用户裁定"应凶终吉"（学林本）之后，
    声明必须改成"已定"并说明另一读法怎么切——否则将来没人知道当时凭什么这么定。
    """
    res = wj.analyze("外面下起了大雨", "木", inner_net="顺")
    note = res["version_note"]
    assert "版本已定" in note
    assert "学林" in note and "卦吉而应凶终吉" in note
    assert "十应目论" in note and "omen_breaks" in note   # 另一读法可切，且写明怎么切
    assert wj.COMBINE_POLICY == "gua_first"                # 默认即为用户所选
