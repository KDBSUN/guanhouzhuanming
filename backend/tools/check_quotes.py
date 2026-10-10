# -*- coding: utf-8 -*-
"""
引文校验 v2：每条 quote 的每个"…"分段都必须逐字出现在所标书籍中（分段可乱序，但都要在）。
同时做书名归一（《卜筮正宗》与"卜筮正宗"同书）。
输出 data/quote_check_report.txt
"""
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
BOOKS = {
    "梅花": BACKEND.parent / "books" / "meihua" / "增广校正梅花易数 (（宋）邵雍撰；李一忻点校；郑同增订, (宋)邵雍撰 , 李一忻点校 , 郑同增订 etc.) (z-library.sk, 1lib.sk, z-lib.sk).md",
    "增删": BACKEND.parent / "books" / "liuyao" / "增删卜易——附校评 (野鹤老人 著，李我平 鉴定，李文辉 增删) (z-library.sk, 1lib.sk, z-lib.sk).md",
    "正宗": BACKEND.parent / "books" / "liuyao" / "四库存目纳甲汇刊 2 校正全本卜筮正宗 (（清）王洪绪撰；郑同校, 王維德, 1669-1749, author etc.) (z-library.sk, 1lib.sk, z-lib.sk).md",
}
HEADERS = {"校正全本卜筮正宗", "增广校正梅花易数", "梅花易数", "增删卜易"}

def book_key(book: str) -> str:
    b = (book or "").replace("《", "").replace("》", "")
    if "梅花" in b:
        return "梅花"
    if "增删" in b:
        return "增删"
    if "正宗" in b:
        return "正宗"
    return ""

_cache = {}
def book_text(key: str) -> str:
    if key not in _cache:
        path = BOOKS.get(key)
        if path and path.exists():
            kept = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() not in HEADERS]
            _cache[key] = "".join("".join(kept).split())
        else:
            _cache[key] = ""
    return _cache[key]

quotes = json.loads((BACKEND / "data" / "term_source_quotes.json").read_text(encoding="utf-8"))
ok, bad, none_count = 0, [], 0
lines = []
for key, q in sorted(quotes.items()):
    if not q.get("quote"):
        none_count += 1
        lines.append(f"[无原文] {key}")
        continue
    hay = book_text(book_key(q.get("book", "")))
    frags = ["".join(f.split()) for f in q["quote"].split("…") if "".join(f.split())]
    missing = [f for f in frags if f not in hay]
    if not missing:
        ok += 1
    else:
        bad.append(key)
        lines.append(f"[未命中] {key}｜{q.get('book')}｜缺 {len(missing)}/{len(frags)} 段：{missing[0][:40]}")

report = [f"共 {len(quotes)} 条：逐字命中 {ok}｜无原文 {none_count}｜未命中 {len(bad)}", ""] + lines
(BACKEND / "data" / "quote_check_report.txt").write_text("\n".join(report), encoding="utf-8")
print(f"ok={ok} none={none_count} bad={len(bad)}")
if bad:
    print("未命中：" + "、".join(bad))
