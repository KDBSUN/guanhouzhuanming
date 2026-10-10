# -*- coding: utf-8 -*-
"""
万物查卦（/api/meihua/wanwu_search）
====================================
手动起卦页的「查万物」搜索框。**三档匹配、零类推**，钉四件事：

  1. 精确／包含／检索词三档都真的能命中（接线，不是数据层空转）；
  2. **单字子串不许命中**——「药」⊂「药婆」（兑·人物，指卖药的人），
     若放行就是近义词假命中。站长 2026-09-24 明定「近义词不命中」，
     所以包含档要求查询词 ≥ 2 字。这条是本文件最要紧的一条：
     它失败不会报错、不会崩，只会让用户拿到一个「看着像、其实不是」的答案；
  3. 只查**物类维度**——婚姻／疾病／官讼等占断维度不是"东西"，不参与；
  4. 查不到返回空（hits=[]），**不做任何类推**——现代物属哪一卦
     由用户按《观物玄妙歌诀》形／色／性／位／体自己定（前端展示该路径）。

用 HTTP 测：匹配逻辑在端点里，数据层测试测不到"字段口径写错"这类洞。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main                                          # noqa: E402


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    return TestClient(main.app)


def _search(client, q):
    r = client.get("/api/meihua/wanwu_search", params={"q": q})
    assert r.status_code == 200, r.text
    return r.json()


def test_exact_hit_carries_line_and_wuxing(client):
    """「镜」就是乾·静物的原文条目：精确命中，带底本行号可回源。"""
    j = _search(client, "镜")
    hit = [h for h in j["hits"] if h["tier"] == "精确" and h["item"] == "镜"]
    assert hit, j["hits"]
    h = hit[0]
    assert h["gua"] == "乾" and h["field"] == "静物" and h["wuxing"] == "金"
    assert isinstance(h["line"], int) and h["line"] > 0


def test_two_char_substring_hits_both_directions(client):
    """包含档是**双向**的：查询词 ⊂ 条目（门口→门户枋）与 条目 ⊂ 查询词 都要能中。"""
    j = _search(client, "门口")
    assert any(h["item"] == "门户枋" and h["gua"] == "兑" for h in j["hits"]), j["hits"]
    j2 = _search(client, "镜子")
    assert any(h["item"] == "镜" and h["gua"] == "乾" for h in j2["hits"]), j2["hits"]


def test_single_char_cannot_ride_substring(client):
    """**本文件最要紧的一条**：单字不许走包含档。

    「药」是「药婆」的子串，而「药婆」（兑·人物）指卖药的人——不是"药"这个物。
    放行它，用户输入「药」就会拿到一个看着像、其实不是的答案，
    且不报错、不崩，只有懂行的人才看得出不对。
    """
    j = _search(client, "药")
    assert j["hits"] == [], "「药」不该命中任何条目（近义词不命中）: %s" % j["hits"]


def test_single_char_still_hits_when_it_is_the_whole_entry(client):
    """单字的**精确**命中照常：「火」就是离·静物的原文条目。
    上一条拦的是子串假命中，不是把单字全禁。"""
    j = _search(client, "火")
    assert any(h["item"] == "火" and h["gua"] == "离" and h["tier"] == "精确"
               for h in j["hits"]), j["hits"]


def test_colloquial_word_reaches_the_entry_via_keys_map(client):
    """检索词表：「缺口」→「缺器」（兑·静物）。检索词不是原文，只作指针。"""
    j = _search(client, "缺口")
    hit = [h for h in j["hits"] if h["item"] == "缺器" and h["gua"] == "兑"]
    assert hit, j["hits"]
    assert hit[0]["tier"] == "检索词" and "缺口" in hit[0].get("via", "")


def test_single_char_gate_via_keys_map_still_works(client):
    """「门」是单字（走不了包含档），但检索词表让它对到「门户枋」——这是设计的本意：
    单字的合法通路是**人工核过的检索词表**，不是放任子串。"""
    j = _search(client, "门")
    hit = [h for h in j["hits"] if h["item"] == "门户枋" and h["gua"] == "兑"]
    assert hit, j["hits"]
    assert hit[0]["tier"] == "检索词"


def test_only_thing_dimensions_participate(client):
    """占断维度（婚姻／疾病／官讼…）不参与——它们不是"东西"。
    反证：乾·婚姻「贵官之眷」这些条目，用其中两字去搜不该出现。"""
    j = _search(client, "贵官")
    assert all(h["field"] not in ("婚姻", "疾病", "官讼", "求名", "求利", "谋望")
               for h in j["hits"]), j["hits"]


def test_no_hit_returns_empty_and_never_guesses(client):
    """查不到就是查不到：hits 为空。**绝不做类推**——现代物属哪一卦由用户按五轴自己定。"""
    for q in ("空调", "阿巴阿巴", "手机"):
        j = _search(client, q)
        assert j["hits"] == [], "「%s」不该命中（类推未授权）: %s" % (q, j["hits"])
        assert "形" in json_note(j) or "推" in json_note(j)


def json_note(j):
    return j.get("note") or ""


def test_empty_query_is_not_an_error(client):
    j = _search(client, "")
    assert j["hits"] == [] and j["count"] == 0
    j2 = _search(client, "   ")
    assert j2["hits"] == []


def test_long_query_is_capped_not_rejected(client):
    """超长输入截断处理即可——这是站内静态查询，不该因为它报 4xx。"""
    j = _search(client, "镜" * 60)
    assert r_ok(j)


def r_ok(j):
    return "hits" in j and "note" in j
