# -*- coding: utf-8 -*-
"""合并白话批次 → data/term_plain.json，覆盖率与长度校验（对照可见词条清单）"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
PLAIN = DATA / "plain"

visible = json.loads((DATA / "visible_terms.json").read_text(encoding="utf-8"))
visible_names = [t["name"] for t in visible]
name_set = set(visible_names)

out, problems = {}, []
for f in sorted(PLAIN.glob("batch_*.json")):
    try:
        batch = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        problems.append(f"{f.name}: JSON 解析失败 {e}")
        continue
    for name, patch in batch.items():
        if name not in name_set:
            problems.append(f"{f.name}: 键「{name}」不在可见词条清单中")
            continue
        if name in out:
            problems.append(f"{f.name}: 键「{name}」与其他批次重复")
        role, detail = patch.get("role", ""), patch.get("detail", "")
        if not role or not detail:
            problems.append(f"{f.name}:「{name}」role/detail 为空")
        if len(detail) > 60:
            problems.append(f"{f.name}:「{name}」detail {len(detail)} 字超 60 上限（含标点）")
        out[name] = {"role": role, "detail": detail}

missing = [n for n in visible_names if n not in out]
print(f"批次文件：{len(list(PLAIN.glob('batch_*.json')))} 个；白话词条：{len(out)} / 可见 {len(visible_names)}")
if missing:
    print(f"未覆盖（{len(missing)}）：{'、'.join(missing[:12])}{'…' if len(missing) > 12 else ''}")
if problems:
    print("问题：")
    for p in problems:
        print(" -", p)

if "--write" in sys.argv and not problems and not missing:
    (DATA / "term_plain.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写入 term_plain.json（{len(out)} 条）")
elif "--write" in sys.argv:
    print("存在问题，未写入。")
    sys.exit(1)
