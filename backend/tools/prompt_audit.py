# -*- coding: utf-8 -*-
"""提示词体检：把「检校提示词」里可以机械化的部分做成一条命令。

    cd backend && python tools/prompt_audit.py

只读，不改任何文件。三类标记：
  ✗  确定的问题（自洽性破了、跨库字样串了、镜像漂移了）
  ?  待人工判（机械规则只能给候选，判断权归人）
  ·  信息（字数、篇名清单，供比对白名单）

为什么要它：提示词是"代码的一部分"，但它的错误不会让程序崩——只会让 AI 悄悄说错话。
人工逐字读 80 行能发现的问题有限，且改一次就要重读一次。这里把可判定的部分固定下来，
每次改完跑一遍，把"人的注意力"留给判断（哪句重复了、哪个引文其实不是原文）而不是搜寻。
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# 控制台默认 GBK，打不出 ✗ 这类符号；强制 UTF-8，并允许替换以免因一个字符整段失败
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 各提示词"不该出现"的外来字样：串库是最隐蔽的一类错误——
# 提示词不报错、AI 照着抄，于是六爻的断语里出现梅花篇名，用户完全看不出来。
FOREIGN = {
    "INTERPRETATION_SYSTEM_PROMPT": ["六爻", "纳甲", "增删卜易", "卜筮正宗"],
    "OMEN_SYSTEM_PROMPT": ["六爻", "纳甲", "增删卜易", "卜筮正宗"],
    "LIUYAO_SYSTEM_PROMPT": ["梅花易数", "体用生克", "外应", "十应"],
    "DAYUN_SYSTEM_PROMPT": ["六爻", "纳甲", "增删卜易", "卜筮正宗",
                            "梅花易数", "体用生克", "外应", "十应"],
}
CN = "一二三四五六七八九十"


def load_prompts():
    """从 main.py 里取所有 *_PROMPT 常量（真值，不是源码文本）。"""
    import main
    out = {}
    for name in dir(main):
        if name.endswith("_PROMPT") and name.isupper():
            v = getattr(main, name)
            if isinstance(v, str):
                out[name] = v
    return out


def _heading_runs(p):
    """把所有 ^N、 标题切成"连续递增"的若干段。

    必须这样做：一份提示词里常有多组编号（如梅花有「素材边界」一~五 + 「规矩」一~八），
    天真的做法（从自称处往下数到第一个 ---）会把两组混在一起，得出"自称8条实为13条"的假警报。
    规矩段 = 从「一」起、最长的那一段连续递增序列。
    """
    hs = [(m.start(), m.group(1)) for m in re.finditer(r"^([%s])、" % CN, p, re.M)]
    runs, cur = [], []
    for pos, ch in hs:
        n = CN.index(ch) + 1
        if cur and n == cur[-1][2] + 1:
            cur.append((pos, ch, n))
        else:
            if cur:
                runs.append(cur)
            cur = [(pos, ch, n)]
    if cur:
        runs.append(cur)
    return [r for r in runs if r and r[0][2] == 1]


def check_claim(p):
    """自称条数 vs 实际编号：梅花曾自称"十条"而正文只有九条、且「四、」重号。"""
    m = re.search(r"以下([%s]+)条" % CN, p)
    if not m:
        return None
    claimed = CN.index(m.group(1)) + 1
    runs = _heading_runs(p)
    if not runs:
        return claimed, [], []
    # 取最长的一段；并列时取最靠近自称处的那段
    best = max(runs, key=lambda r: (len(r), -abs(r[0][0] - m.end())))
    return claimed, [c for _, c, _ in best], [(pos, c) for pos, c, _ in best]


def check_mirror(p, doc):
    """文档镜像：doc 里若抄了这份提示词，必须逐字一致。

    只改文档等于没改（AI 读的是代码），所以镜像漂移是必须报的问题。
    但"找不到"这个结论太粗——多数漂移是**中了段**（如引号规范不一），
    开头 60 字就对不上。故用 20 字探针定位，再算最长公共前缀，报出漂移起点。
    """
    ps = p.strip()
    i = doc.find(ps[:20])
    if i < 0:
        return "missing", "", 0
    a = doc.rfind("```", 0, i)
    b = doc.find("```", i)
    seg = (doc[a + 3:b] if a >= 0 and b > 0 else doc[i:i + len(ps) + 800]).strip()
    if ps in seg:
        return "verbatim", seg, len(ps)
    n = 0
    while n < min(len(ps), len(seg)) and ps[n] == seg[n]:
        n += 1
    return "drift", seg, n


def dup_sentences(p, min_len=14):
    """重复句：提示词最典型的冗余形态是同一句换着说法出现两三次。"""
    parts = [s.strip() for s in re.split(r"[。；\n]", p) if len(s.strip()) >= min_len]
    c = Counter(parts)
    return [(s, n) for s, n in c.items() if n > 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mirror-doc", default="docs/AI提示词汇总.md")
    args = ap.parse_args()

    prompts = load_prompts()
    docp = ROOT / args.mirror_doc
    doc = docp.read_text(encoding="utf-8") if docp.exists() else ""

    hard = soft = 0
    for name, p in sorted(prompts.items()):
        print("\n" + "=" * 72)
        print("%s   %d 字 / %d 行" % (name, len(p), p.count("\n") + 1))

        r = check_claim(p)
        if r:
            claimed, heads, positions = r
            ok = len(heads) == claimed
            print("  %s 自称%s条，最大连续编号段实为%d条 %s"
                  % ("·" if ok else "✗", claimed, len(heads), heads))
            if not ok:
                hard += 1
            dups = [h for h in set(heads) if heads.count(h) > 1]
            if dups:
                print("  ? 同一段里编号重复 %s —— 请人工看一眼" % dups)
                soft += 1
        else:
            print("  · 未自称条数（无需自洽检查）")

        bad = [w for w in FOREIGN.get(name, []) if w in p]
        if bad:
            print("  ✗ 出现本库外来字样：%s —— 多半是串库，逐行看一下上下文" % bad)
            hard += 1
            for ln in p.split("\n"):
                if any(w in ln for w in bad):
                    print("      | %s" % ln[:88])

        names = sorted(set(re.findall(r"《([^》]{1,24})》", p)))
        print("  · 引用书名/篇名 %d 个：%s" % (len(names), "、".join(names)))

        if doc:
            state, seg, at = check_mirror(p, doc)
            ps = p.strip()
            if state == "verbatim":
                print("  · 文档镜像逐字一致（%d 字）" % len(seg))
            elif state == "missing":
                print("  ✗ 文档 %s 里找不到这份提示词——镜像缺失（或开头就已漂移）" % args.mirror_doc)
                hard += 1
            else:
                print("  ✗ 文档镜像漂移：自代码第 %d 字起不一致（doc %d 字 ≠ 代码 %d 字）"
                      % (at, len(seg), len(ps)))
                print("      代码…%s" % ps[max(0, at - 10):at + 26].replace("\n", "⏎"))
                print("      文档…%s" % (seg[max(0, at - 10):at + 26].replace("\n", "⏎")
                                        if at < len(seg) else "（该处起文档已无对应文字）"))
                hard += 1

        d = dup_sentences(p)
        if d:
            print("  ? 重复句 %d 组（需人判断是不是真冗余）：" % len(d))
            for s, n in d[:12]:
                print("      ×%d  %s" % (n, s[:70]))
            soft += 1
        else:
            print("  · 无 ≥14 字的重复句")

    print("\n" + "=" * 72)
    print("确定问题 %d 处；待人工判 %d 处。" % (hard, soft))
    print("机械检查到此为止——引文是否真为原文、哪句该删，只能靠人对着 books/ 读。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
