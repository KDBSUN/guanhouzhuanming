# -*- coding: utf-8 -*-
"""
典籍原文索引回归（book_quotes.py）
=================================
出处键按最长前缀归并到 books/ 库内原文摘录；未收录键返回 text=None（原文待录，不代拟）。
另含"逐字回源"回归：QUOTES 里每段引文必须是 books/ 库内原文的逐字子串
（容许：圈码脚注①②被剥离、片段结尾截断标点），防止将来手滑写进库外拼装文字。
"""
import re
from pathlib import Path

from book_quotes import QUOTES, lookup, lookup_many
import books_corpus
import pytest


def test_prefix_merge():
    q = lookup("滴天髓·从儿（任氏注）")
    assert q["book"].startswith("滴天髓·从儿")
    assert "最忌印运" in q["text"]
    q2 = lookup("梅花易数·先天卦定应期/求名占")
    assert "定事应之期" in q2["text"]
    q3 = lookup("滴天髓·从象（任氏注）")
    assert "犯旺" in q3["text"]


def test_unknown_key_not_fabricated():
    q = lookup("不存在的出处键")
    assert q["text"] is None
    assert "待录" in q["note"] or "核对" in q["note"]


def test_lookup_many_dedup_and_coverage():
    keys = ["滴天髓·从儿（任氏注）", "滴天髓·从儿（任氏注）", "渊海子平·旺相休囚死", "", "未知键"]
    out = lookup_many(keys)
    assert len(out) == 3      # 重复键归并、空键剔除
    assert "当令者旺" in out["渊海子平·旺相休囚死"]["text"]
    assert out["未知键"]["text"] is None


# ---------- 键别名与键名改正（2026-09-23，引文表审计 tools/audit_quote_index.py 查出） ----------

def test_alias_points_to_the_same_quote():
    """别名键必须落到同一段原文上（zeri.py 写的是「梅花易数·心易占卜玄机（衰旺诀）」，
    索引键是「梅花易数·心易衰旺诀」）——加别名而不是重收一遍原文，
    否则同一段话在表里出现两遍，将来改一处漏一处。"""
    from book_quotes import ALIASES
    assert ALIASES["梅花易数·心易占卜玄机（衰旺诀）"] == "梅花易数·心易衰旺诀"
    a = lookup("梅花易数·心易占卜玄机（衰旺诀）")
    b = lookup("梅花易数·心易衰旺诀")
    assert a["text"] and a["text"] == b["text"] and a["book"] == b["book"]
    assert "体卦之气宜于旺盛" in a["text"]


def test_wuhuo_key_names_the_real_book():
    """键名必须与 book 字段的书是同一部：原键「三命通会·论火」挂的其实是
    《渊海子平·论火》（「夏月之火，乘旺秉权」）——键名是要显示给用户看的标签，
    先摆错书名、点开才见真书，等于把错处摆在最前面。已改正为「渊海子平·论火」。"""
    assert "三命通会·论火" not in QUOTES
    q = lookup("渊海子平·论火")
    assert q["text"] and "夏月之火" in q["text"]
    assert "渊海子平" in q["book"]


def test_no_duplicate_quote_text():
    """引文表里不得有两键挂同一段原文（重复收录＝将来改一处漏一处）。
    这条原先是 tools/audit_quote_index.py 的 D1，落一条测试免得回退。"""
    seen = {}
    dups = []
    for k, v in QUOTES.items():
        t = re.sub(r"\s+", "", v.get("text") or "")
        if not t:
            continue
        if t in seen:
            dups.append((seen[t], k))
        seen[t] = k
    assert not dups, "以下键挂了同一段原文：%s" % dups


# ---------- 逐字回源：每段引文必须是库内原文子串 ----------

def _norm(s: str) -> str:
    s = re.sub(r"[\u2460-\u2473\u3251-\u325F\u32B1-\u32BF]", "", s)  # 去圈码脚注①②…
    return re.sub(r"\s+", "", s)


def test_all_quotes_verbatim_from_books():
    # 语料位置统一由 books_corpus 决定（支持 BOOKS_DIR 覆盖）。语料不在时**跳过并说明**，
    # 而不是丢一句"语料为空"的 assert——但那句跳过必须在摘要里看得见：
    # "以为有覆盖其实没跑"正是本项目吃过亏的地方，故 skip 原因写明"防线当前未生效"。
    reason = books_corpus.missing_reason()
    if reason:
        pytest.skip(reason)
    full = _norm(books_corpus.read_corpus())
    miss = []
    for key, q in QUOTES.items():
        for frag in re.split(r"……|\.\.\.", q.get("text") or ""):
            f = _norm(frag)
            if len(f) >= 6 and f not in full and f.rstrip("。；，、！？：") not in full:
                miss.append((key, f[:40]))
    assert not miss, "以下引文不是库内逐字原文（违反'绝不代拟'红线）: %s" % miss
