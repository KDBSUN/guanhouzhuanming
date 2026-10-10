# -*- coding: utf-8 -*-
"""合并浓缩批次 → data/term_condensed.json，并做覆盖率与长度校验"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
COND = DATA / "condensed"

merged = json.loads((DATA / "terminology_merged.json").read_text(encoding="utf-8"))
meihua_names = [t["name"] for t in merged["systems"]["meihua"]["terms"]]
name_set = set(meihua_names)

out, problems = {}, []
for f in sorted(COND.glob("batch_*.json")):
    try:
        batch = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        problems.append(f"{f.name}: JSON 解析失败 {e}")
        continue
    for name, patch in batch.items():
        if name not in name_set:
            problems.append(f"{f.name}: 键「{name}」不在梅花词条名清单中")
            continue
        if name in out:
            problems.append(f"{f.name}: 键「{name}」与其他批次重复")
        role, detail = patch.get("role", ""), patch.get("detail", "")
        if not role or not detail:
            problems.append(f"{f.name}:「{name}」role/detail 为空")
        if len(detail) > 160:
            problems.append(f"{f.name}:「{name}」detail {len(detail)} 字超上限")
        out[name] = {"role": role, "detail": detail}

missing = [n for n in meihua_names if n not in out]
print(f"批次文件：{len(list(COND.glob('batch_*.json')))} 个；浓缩词条：{len(out)} / {len(meihua_names)}")
if missing:
    print(f"未覆盖（{len(missing)}）：{'、'.join(missing[:12])}{'…' if len(missing) > 12 else ''}")
if problems:
    print("问题：")
    for p in problems:
        print(" -", p)

if "--write" in sys.argv and not problems and not missing:
    (DATA / "term_condensed.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写入 term_condensed.json（{len(out)} 条）")
elif "--write" in sys.argv:
    print("存在问题，未写入。先解决上述问题。")
    sys.exit(1)
