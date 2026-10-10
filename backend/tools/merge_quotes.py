# -*- coding: utf-8 -*-
"""合并全部引文批次 → data/term_source_quotes.json（键：system::name），并汇总 null 清单"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
QUOTES = DATA / "quotes"

merged, nulls, counts = {}, [], {}
for f in sorted(QUOTES.glob("*.json")):
    batch = json.loads(f.read_text(encoding="utf-8"))
    system = "meihua" if f.name.startswith("meihua") else "liuyao"
    n = 0
    for name, q in batch.items():
        merged[f"{system}::{name}"] = {
            "book": q.get("book", ""), "loc": q.get("loc", ""),
            "quote": q.get("quote"), "line": q.get("line"),
        }
        if not q.get("quote"):
            nulls.append(f"{system}::{name}")
        n += 1
    counts[f.name] = n

(DATA / "term_source_quotes.json").write_text(
    json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"合并 {len(merged)} 条；各批：{counts}；null：{len(nulls)}")
if nulls:
    print("  " + "、".join(nulls))
