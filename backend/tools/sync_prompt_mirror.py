# -*- coding: utf-8 -*-
"""把 main.py 里的提示词镜像回文档。配套 tools/prompt_audit.py。

    python tools/sync_prompt_mirror.py                 # 只报告差异（默认，不动文件）
    python tools/sync_prompt_mirror.py --write         # 写回
    python tools/sync_prompt_mirror.py --write --only OMEN_SYSTEM_PROMPT

为什么需要它：AI 读的是**代码**里的提示词，文档只是给人看的。只改文档等于没改；
反过来，代码改了而文档没跟上，下一个人就会照着过期文档继续改——越改越远。
两边必须由工具强制对齐，不能靠"我记得同步了"（本项目就这么漏过一次）。
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_prompts(only=None):
    import main
    out = {}
    for name in sorted(dir(main)):
        if name.endswith("_PROMPT") and name.isupper():
            v = getattr(main, name)
            if isinstance(v, str) and (not only or name == only):
                out[name] = v.strip()
    return out


def locate(doc, body):
    """在文档里定位这份提示词的围栏块，返回 (内容起, 内容止)。"""
    i = doc.find(body[:20])
    if i < 0:
        return None
    a = doc.rfind("```", 0, i)
    b = doc.find("```", i)
    if a < 0 or b < 0 or b < a:
        return None
    return a + 3, b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写回（默认只报告）")
    ap.add_argument("--only", default="", help="只处理某一个提示词常量名")
    ap.add_argument("--doc", default="docs/AI提示词汇总.md")
    args = ap.parse_args()

    docp = ROOT / args.doc
    doc = docp.read_text(encoding="utf-8")
    changed, missing = [], []

    for name, body in load_prompts(args.only or None).items():
        loc = locate(doc, body)
        if not loc:
            missing.append(name)
            print("✗ %-30s 文档里找不到（镜像缺失）" % name)
            continue
        a, b = loc
        cur = doc[a:b].strip()
        if cur == body:
            print("· %-30s 已一致（%d 字）" % (name, len(body)))
            continue
        print("≠ %-30s 文档 %d 字 → 代码 %d 字" % (name, len(cur), len(body)))
        if args.write:
            doc = doc[:a] + "\n" + body + "\n" + doc[b:]
            changed.append(name)

    if args.write and changed:
        docp.write_text(doc, encoding="utf-8")
        print("\n已写回：%s" % "、".join(changed))
    elif changed:
        print("\n以上为差异（未写；加 --write 写回）")
    if missing:
        print("\n缺失的需要人工确认该提示词是否**应该**进文档——不要盲目新建章节。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
