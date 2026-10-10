# -*- coding: utf-8 -*-
"""
引文索引查重与结构体检（开源做法 `check_dup_hits.js` 的本地实现）
==================================================================
一句话：同一段原文不该在索引里出现两遍，同一个出处不该挂两段打架的引文。
开源项目 bazi-engine 用 `check_dup_hits.js` 查"同文案规则同盘重复命中"；
本站要查的是**引文表本身**——`book_quotes.QUOTES` 的"出处键 → 原文摘录"是一对多还是多对多，
直接决定页面上"出处行"点开看到的是不是同一段话。

查七项（每项都标死是"硬问题"还是"待人工判"）：

  D1 逐字重复       两条键的 text 归一化后完全相同                      → ✗（重复收录）
  D2 同文异书       同一段 text 挂在两个不同 book 下                    → ✗（出处自相矛盾）
  D3 整段包含       一键 text 完整包含另一键的正文（长度差 > 20 字）      → ?
  D4 分段重复       按 …… 切段后，同一片段出现在两个键里                 → ?
  D5 同书同章异文   同一 (book, loc) 下挂了两段不同的 text               → ?
  D6 键前缀重叠     一键是另一键的前缀（lookup 按最长前缀匹配）          → ·（信息，非错）
  D7 键与书不符     键里"·"前的书名与 book 字段完全对不上                 → ?
  D8 引文过短       text 正文 < 20 字，撑不起一条判据                     → ?

另含 `--corpus`：把每段引文与 books/ 语料做逐字回源（与 tests/test_quotes.py 同一口径，
语料不在时明确说明"逐字回源未生效"，不静默当通过）。

用法：
    cd backend
    python tools/audit_quote_index.py
    python tools/audit_quote_index.py --corpus          # 加做逐字回源
    python tools/audit_quote_index.py --out data/xxx.txt
退出码：有 ✗ → 1。
"""
import argparse
import io
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_CIRCLED = re.compile(r"[\u2460-\u2473\u3251-\u325F\u32B1-\u32BF]")


def norm(s: str) -> str:
    """归一化：去圈码脚注、去空白、去引号差异——只比"字"，不比排版。"""
    s = _CIRCLED.sub("", s or "")
    return re.sub(r"\s+", "", s)


def key_book(key: str) -> str:
    return key.split("·")[0].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="store_true", help="加做 books/ 逐字回源")
    ap.add_argument("--out", default="data/audit_quote_index_report.txt")
    args = ap.parse_args()

    from book_quotes import QUOTES
    L = []
    hard, soft, info = [], [], []

    def add(s=""):
        L.append(s)

    add("引文索引查重与结构体检（共 %d 键）" % len(QUOTES))
    add("读法：✗＝必须处置；?＝待人工判；·＝信息")

    # 归一化正文（供逐字比较）；保留原文（供打印）
    body = {k: norm(v.get("text") or "") for k, v in QUOTES.items()}

    # ---------- D1 逐字重复 ----------
    add("\n【D1 逐字重复（归一化后完全相同）】")
    by_text = defaultdict(list)
    for k, b in body.items():
        if b:
            by_text[b].append(k)
    d1 = {b: ks for b, ks in by_text.items() if len(ks) > 1}
    if d1:
        for b, ks in d1.items():
            add("  ✗ %s ← %s" % ("、".join(ks), b[:40]))
            hard.append("D1 逐字重复：%s" % "、".join(ks))
    else:
        add("  无")

    # ---------- D2 同文异书 ----------
    add("\n【D2 同文异书（同一段正文挂在两个 book 下）】")
    d2 = []
    for b, ks in by_text.items():
        books = {QUOTES[k].get("book", "") for k in ks}
        if len(books) > 1:
            d2.append((b, ks, books))
    if d2:
        for b, ks, books in d2:
            add("  ✗ %s ｜ books=%s" % ("、".join(ks), "／".join(sorted(books))))
            hard.append("D2 同文异书：%s" % "、".join(ks))
    else:
        add("  无")

    # ---------- D3 整段包含 ----------
    add("\n【D3 整段包含（一键正文完整出现在另一键里，且差 > 20 字）】")
    keys = [k for k in body if body[k]]
    d3 = []
    for i, a in enumerate(keys):
        for b in keys:
            if a == b:
                continue
            # 用去掉首尾标点的核心段比较，避免"……"接续造成的假包含
            core = body[a].strip("。；，、……")
            if len(core) >= 12 and core in body[b] and len(body[b]) - len(core) > 20:
                d3.append((a, b))
    if d3:
        for a, b in d3:
            add("  ? %s 的正文完整包含在 %s 里（%d 字 ⊂ %d 字）"
                % (a, b, len(body[a]), len(body[b])))
            soft.append("D3 整段包含：%s ⊂ %s" % (a, b))
    else:
        add("  无")

    # ---------- D4 分段重复 ----------
    add("\n【D4 分段重复（同一 …… 片段出现在两个键里）】")
    frag = defaultdict(set)
    for k, v in QUOTES.items():
        for f in re.split(r"……|\.\.\.", v.get("text") or ""):
            f = norm(f)
            if len(f) >= 10:
                frag[f].add(k)
    d4 = {f: ks for f, ks in frag.items() if len(ks) > 1}
    if d4:
        for f, ks in sorted(d4.items(), key=lambda x: -len(x[0]))[:20]:
            add("  ? %s ← %s" % ("、".join(sorted(ks)), f[:40]))
            soft.append("D4 分段重复：%s（%s）" % ("、".join(sorted(ks)), f[:16]))
    else:
        add("  无")

    # ---------- D5 同书同章异文 ----------
    add("\n【D5 同书同章下挂了不同正文】")
    by_loc = defaultdict(list)
    for k, v in QUOTES.items():
        by_loc[(v.get("book", ""), v.get("loc", ""))].append(k)
    d5 = {loc: ks for loc, ks in by_loc.items() if len(ks) > 1 and len({body[k] for k in ks}) > 1}
    if d5:
        for (bk, loc), ks in d5.items():
            add("  ? 《%s》%s ← %s（%d 段不同的正文）" % (bk, loc, "、".join(ks), len(ks)))
            soft.append("D5 同书同章异文：%s" % "、".join(ks))
    else:
        add("  无（同一章节只挂一段，或挂的多段正文相同）")

    # ---------- D6 键前缀重叠 ----------
    add("\n【D6 键前缀重叠（lookup 走最长前缀匹配，重叠本身不是错）】")
    ov = [(a, b) for a in QUOTES for b in QUOTES if a != b and b.startswith(a)]
    if ov:
        for a, b in sorted(ov):
            add("  · %s ⊂ %s：以 %s 开头的出处键会命中更长的那条" % (a, b, a))
            info.append("D6 前缀重叠：%s ⊂ %s" % (a, b))
    else:
        add("  无")

    # ---------- D7 键与书不符 ----------
    add("\n【D7 键里的书名与 book 字段对不上】")
    d7 = []
    for k, v in QUOTES.items():
        kb, bk = key_book(k), norm(v.get("book", ""))
        if kb and norm(kb) not in bk:
            d7.append((k, v.get("book", "")))
    if d7:
        for k, bk in d7:
            add("  ? 键「%s」的书名在 book 字段「%s」里找不到" % (k, bk))
            soft.append("D7 键与书不符：%s" % k)
    else:
        add("  无")

    # ---------- D8 引文过短 ----------
    add("\n【D8 正文过短（< 20 字，撑不起一条判据）】")
    d8 = [(k, len(b)) for k, b in body.items() if 0 < len(b) < 20]
    if d8:
        for k, n in sorted(d8, key=lambda x: x[1]):
            add("  ? %s（%d 字）" % (k, n))
            soft.append("D8 引文过短：%s（%d 字）" % (k, n))
    else:
        add("  无")

    # ---------- 逐字回源（可选） ----------
    if args.corpus:
        add("\n【逐字回源（books/ 语料，与 tests/test_quotes.py 同口径）】")
        sys.path.insert(0, str(ROOT / "tests"))
        try:
            import books_corpus
            reason = books_corpus.missing_reason()
            if reason:
                add("  ! 未生效：%s" % reason)
                info.append("逐字回源未生效")
            else:
                full = norm(books_corpus.read_corpus())
                miss = []
                for k, v in QUOTES.items():
                    for f in re.split(r"……|\.\.\.", v.get("text") or ""):
                        f2 = norm(f)
                        if len(f2) >= 6 and f2 not in full and f2.rstrip("。；，、！？：") not in full:
                            miss.append((k, f2[:40]))
                if miss:
                    for k, f in miss:
                        add("  ✗ %s ｜ 非库内逐字原文：%s" % (k, f))
                        hard.append("逐字回源失败：%s" % k)
                else:
                    add("  全部 %d 键的每段引文都在语料内逐字可检" % len(QUOTES))
        except Exception as e:
            add("  ! 未能加载语料定位模块：%s" % e)
            info.append("逐字回源未生效")

    add("\n【汇总】✗ %d 处；? %d 处；· %d 处" % (len(hard), len(soft), len(info)))
    text = "\n".join(L)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(text)
    print("\n报告已写入：%s" % out)
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
