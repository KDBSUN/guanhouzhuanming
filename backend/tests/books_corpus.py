# -*- coding: utf-8 -*-
"""
典籍语料定位（测试专用，非测试文件本身——文件名不以 test_ 开头，pytest 不收集）
================================================================================
**为什么单独抽出来**：三组测试要靠 `books/` 里的原文来验"引文是逐字原文、不是代拟"
（`test_quotes` / `test_terminology` / `test_waijing`）。语料一旦不在原位，
这三条防线就会以"语料为空"的形式报错——报错本身对，但**不能变成静默通过**：
本项目吃过这个亏（"以为有覆盖其实没跑"），所以这里统一返回明确的缺失原因，
让调用方 `pytest.skip(原因)`，在测试摘要里留下可见的 `s`。

语料位置的解析次序（`books_root()`）：
  1. 环境变量 `BOOKS_DIR`（最高优先，站长把语料挪到任意位置时用）；
  2. 仓库根的 `books/`（语料放在项目内时的常规位置）；
  3. **仓库同级的 `books/`**（本站现状：`D:\\Web\\bagua` 与 `D:\\Web\\books` 并列——
     典籍是**只读资料**，不该放进产品目录，所以它一直在项目外面）。
找不到任何一个时，`missing_reason()` 会把"找过哪几处"一并说清。
"""
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# 候选位置（按优先级），最后一个仅用于生成"找不到"的提示，不参与存在性判断
_CANDIDATES = (_REPO_ROOT / "books", _REPO_ROOT.parent / "books")


def books_root() -> Path:
    """语料根目录：`BOOKS_DIR` 优先 → 仓库根 books/ → 仓库同级 books/。"""
    env = (os.getenv("BOOKS_DIR") or "").strip()
    if env:
        return Path(env)
    for cand in _CANDIDATES:
        if cand.exists():
            return cand
    return _CANDIDATES[0]


def corpus_files() -> list:
    """语料文件（.md/.txt）。返回空列表即表示语料不可用。"""
    root = books_root()
    if not root.exists():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        if p.suffix in (".md", ".txt") and p.is_file():
            out.append(p)
    return out


def missing_reason() -> str:
    """语料不可用时的**可照做**说明；可用时返回空串。"""
    root = books_root()
    if not root.exists():
        return ("典籍语料目录不存在：%s。逐字回源防线**当前未生效**——"
                "若已把 books/ 挪到别处，请设环境变量 BOOKS_DIR 指向它"
                "（例如 $env:BOOKS_DIR='D:\\某处\\books'）后重跑。"
                "注意：这与「引文写错」是两回事，别把跳过当成通过。" % root)
    if not corpus_files():
        return ("典籍语料目录 %s 存在但里面没有 .md/.txt：逐字回源防线**当前未生效**。"
                "请确认 BOOKS_DIR 指对了地方。" % root)
    return ""


def read_corpus() -> str:
    """把所有语料拼成一段文本（供「逐字子串」比对）。"""
    parts = []
    for p in corpus_files():
        try:
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
    return "\n".join(parts)
