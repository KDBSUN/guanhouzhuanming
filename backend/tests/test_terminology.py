# -*- coding: utf-8 -*-
"""
术语知识地图库回归（terminology.py + terminology.db）
====================================================
库由 4 份 HTML 知识地图抽取合并而成（梅花 3 份合并为 10 类、六爻 1 份 7 类）。
本测试锁定：规模不小、分类齐全、关联零悬空、上轮典籍校正发现的缺口词条确实在库。
"""
from terminology import available, meta, list_terms, get_term, search
import books_corpus
import pytest


def test_db_available_and_meta():
    assert available(), "terminology.db 未生成"
    m = meta()
    systems = {s["system"]: s for s in m["systems"]}
    assert set(systems) == {"meihua", "liuyao"}
    # v2：梅花非术语类目（占例/测字/书论等）默认隐藏，对外可见约 83 条、7 个类目
    assert 78 <= systems["meihua"]["total"] <= 90
    assert len(systems["meihua"]["categories"]) == 7
    assert len(systems["liuyao"]["categories"]) == 7


def test_meihua_covers_yingqi_and_cases():
    """梅花：应期克应与占例（本轮典籍校正认定的缺口）必须在库"""
    yingqi = [t["name"] for t in list_terms("meihua", "应期克应")]
    assert any("全卦之数" in n for n in yingqi)
    assert any("行立坐卧" in n for n in yingqi)
    cases = [t["name"] for t in list_terms("meihua", "占例", include_hidden=True)]
    for kw in ("观梅占", "牡丹占", "邻夜", "老人有忧色占", "西林寺"):
        assert any(kw in n for n in cases), f"占例缺 {kw}"


def test_meihua_case_numbers_recorded():
    """补录占例：应期数字必须随词条入库（全卦之数定应期的实证）"""
    expect = {
        "牛哀鸣占": "二十一",
        "鸡悲鸣占": "十日",
        "枯枝坠地占": "十日",
        "少年有喜色占": "十七",
        "老人有忧色占": "五日",
    }
    for name, num in expect.items():
        hits = [t for t in list_terms("meihua", include_hidden=True) if t["name"] == name]
        assert hits, f"缺占例词条 {name}"
        item = get_term(hits[0]["id"])
        assert num in item["detail"], f"{name} 释义缺应期数字 {num}"


def test_overrides_applied():
    """覆盖层：改正与分歧注必须生效，错误与冗余必须清除（含隐藏词条的检查）"""
    meihua_names = [t["name"] for t in list_terms("meihua", include_hidden=True)]
    # 十七占统一为「十八占（十七占）」，独立"十八占"删除
    assert "十八占（十七占）" in meihua_names
    assert "十八占" not in meihua_names
    # 含错的"卦气旺、卦气衰"合并条已删（正确内容在 卦气旺/卦气衰 两条）
    assert "卦气旺、卦气衰" not in meihua_names
    assert "卦气旺" in meihua_names and "卦气衰" in meihua_names
    # 体克用诸事吉；全书不再有"小吉"与"夏艮兑"
    for t in list_terms("meihua"):
        item = get_term(t["id"])
        assert "夏艮兑" not in item["detail"], f"{t['name']} 仍含'夏艮兑'之误"
        if t["name"] in ("五行生克", "体用生克之诀"):
            assert "诸事吉" in item["detail"] and "小吉" not in item["detail"]
    # 六爻两处分歧注
    for name, kw in (("卦身（月卦身）", "两书分歧"), ("长生十二宫", "两书出入")):
        hits = [t for t in list_terms("liuyao") if t["name"] == name]
        assert hits, f"缺 {name}"
        assert kw in get_term(hits[0]["id"])["detail"]


def test_meihua_details_condensed():
    """浓缩层：梅花释义密度对标六爻地图（硬上限 200 字，含校注）"""
    for t in list_terms("meihua"):
        item = get_term(t["id"])
        assert len(item["detail"]) <= 200, f"{t['name']} 释义 {len(item['detail'])} 字，超浓缩上限"


def test_liuyao_covers_prompt_gaps():
    """六爻：上轮提示词校正列出的缺口词条必须全部在库"""
    names = [t["name"] for t in list_terms("liuyao")]
    joined = "".join(names)
    for kw in ("仇神", "用神两现", "用神不上卦", "伏神", "飞神", "暗动", "日破",
               "进神、退神", "反吟", "伏吟", "三合局", "独发、独静", "贪生忘克", "月破", "旬空"):
        assert kw in joined, f"六爻库缺 {kw}"


def test_relations_all_resolved():
    """全库关联不得悬空（页面上的关联术语都能点开）"""
    for system in ("meihua", "liuyao"):
        for t in list_terms(system):
            item = get_term(t["id"])
            dangling = [r for r in item["relations"] if not r["exists"]]
            assert not dangling, f"{system}/{t['name']} 关联悬空：{dangling}"


def test_source_quotes_present_and_verbatim():
    """每条可见词条都挂原文语录，且语录逐字存在于所标书籍中（防编造）"""
    # 三本书按文件名定位（文件名很长且带版本后缀）；语料根由 books_corpus 决定，
    # 语料不在时**跳过并说明防线未生效**，而不是给一句费解的 assert。
    root = books_corpus.books_root()
    books = {
        "梅花": root / "meihua" / "增广校正梅花易数 (（宋）邵雍撰；李一忻点校；郑同增订, (宋)邵雍撰 , 李一忻点校 , 郑同增订 etc.) (z-library.sk, 1lib.sk, z-lib.sk).md",
        "增删": root / "liuyao" / "增删卜易——附校评 (野鹤老人 著，李我平 鉴定，李文辉 增删) (z-library.sk, 1lib.sk, z-lib.sk).md",
        "正宗": root / "liuyao" / "四库存目纳甲汇刊 2 校正全本卜筮正宗 (（清）王洪绪撰；郑同校, 王維德, 1669-1749, author etc.) (z-library.sk, 1lib.sk, z-lib.sk).md",
    }
    absent = [k for k, p in books.items() if not p.is_file()]
    if absent:
        pytest.skip("语料缺失 %s（根目录 %s）：逐字回源防线**当前未生效**；"
                    "若已把 books/ 挪走，请设 BOOKS_DIR 指向它后重跑" % (absent, root))
    headers = {"校正全本卜筮正宗", "增广校正梅花易数", "梅花易数", "增删卜易"}
    cache = {}
    def text_of(book: str) -> str:
        k = "梅花" if "梅花" in book else ("增删" if "增删" in book else "正宗")
        if k not in cache:
            kept = [ln for ln in books[k].read_text(encoding="utf-8").splitlines() if ln.strip() not in headers]
            cache[k] = "".join("".join(kept).split())
        return cache[k]

    checked = 0
    for system in ("meihua", "liuyao"):
        for t in list_terms(system):
            item = get_term(t["id"])
            assert item["source_quote"], f"{t['name']} 缺原文语录"
            assert item["source_book"] and item["source_loc"], f"{t['name']} 缺出处"
            hay = text_of(item["source_book"])
            for frag in item["source_quote"].split("…"):
                frag = "".join(frag.split())
                if frag:
                    assert frag in hay, f"{t['name']} 引文未逐字命中：{frag[:30]}"
            checked += 1
    assert checked >= 155          # 162 条（含隐藏词条）至少 155 有引文


def test_search_and_detail():
    hits = search("仇神")
    assert any(h["name"] == "仇神" for h in hits)
    hit = next(h for h in hits if h["name"] == "仇神")
    item = get_term(hit["id"])
    assert item["system"] == "liuyao"
    assert "元神" in item["detail"] or "忌神" in item["detail"]
    assert get_term(999999) is None


def test_detail_relations_clickable():
    """关联项带 id/category，前端可直接跳转"""
    hit = next(h for h in search("体用总诀") if h["system"] == "meihua")
    item = get_term(hit["id"])
    assert item["relations"], "体用总诀应有相关术语"
    assert all(r["id"] and r["category"] for r in item["relations"])
