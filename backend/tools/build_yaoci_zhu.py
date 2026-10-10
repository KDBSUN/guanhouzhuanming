# -*- coding: utf-8 -*-
"""爻辞【注释】提取工具
========================
从《周易》（杨天才、张善文 译注，中华书局·全本全注全译丛书）里，
把六十四卦 × 六爻的【注释】逐条抽出来，落到 backend/yaoci_zhu.json。

为什么要这个文件（而不是让 AI 现场讲字义）：
    《梅花易数·占卜总诀》："大抵占卜之法，成卦之后，先看《周易》爻辞，以断吉凶。"
    爻辞在梅花里是**象的语言**，不是必须整句照搬的教条——鸡悲鸣占只拈"血去"二字
    点睛，《占物类例》更是逐句把爻辞往物象上推（"见龙在田"→田中之物）。
    要拈字，就得知道每个字在讲什么象；那是训诂，不是创作：AI 现场讲字义就是编。
    所以逐词注释必须来自有出处的本子，逐条可回源。

【取什么、不取什么】
    只取该书【注释】（逐词训诂，且注明《正义》《释文》《集解》等古注出处）；
    **不取【译文】**——整句白话会把意思压平，正好妨碍拈字；
    也不取【评析】（那是该书的议论，非训诂）。

【版式现实】（决定了本工具的做法）
    1. 标题行不可靠：'## 大过()' / '## 小过()' 两条标题在电子本里丢了，
       所以**不用标题切卦**，改用"每卦卦辞原文"作锚点顺序定位；
    2. 经文行有的带 '## ' 前缀、有的不带；【注释】也一样，故一律容忍可选前缀；
    3. 注释条目用 ①②③ 编号，且每条以"被注的字词＋："开头——
       这正好是拈字时要找的那个"字"，故拆成 {word, text} 结构存下来；
    4. 正文里他卦注释会引用本卦爻辞（如"此句引自《大过》之初六爻辞"），
       属于诱饵：用"经文行后面紧跟着【注释】标题"这一条把它排除。

用法：
    cd backend && python tools/build_yaoci_zhu.py            # 生成 yaoci_zhu.json
    cd backend && python tools/build_yaoci_zhu.py --report   # 只打印核对报告，不写文件
"""
import difflib
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
OUT = BACKEND / "yaoci_zhu.json"
MEIHUA_DATA = REPO / "data" / "meihua_data.json"

BOOK_FILE = "books/wuxing/周易 (杨天才 张善文) (z-library.sk, 1lib.sk, z-lib.sk).md"
BOOK_LABEL = "《周易》（杨天才、张善文 译注，中华书局·全本全注全译丛书）"

# 通行本次序（上经三十、下经三十四）——用来核对电子本没有缺卦、没有错序
CANON = ("乾 坤 屯 蒙 需 讼 师 比 小畜 履 泰 否 同人 大有 谦 豫 随 蛊 临 观 噬嗑 贲 剥 复 "
         "无妄 大畜 颐 大过 坎 离 咸 恒 遁 大壮 晋 明夷 家人 睽 蹇 解 损 益 夬 姤 萃 升 "
         "困 井 革 鼎 震 艮 渐 归妹 丰 旅 巽 兑 涣 节 中孚 小过 既济 未济").split()

# 纯卦的通行名与本站 name 不同（本站作"乾为天"），单列一张对照
PURE = {"乾": "乾为天", "坤": "坤为地", "坎": "坎为水", "离": "离为火",
        "震": "震为雷", "艮": "艮为山", "巽": "巽为风", "兑": "兑为泽"}

# 异体字/版本字折叠：只用于**匹配**，存下来的原文一字不改
FOLD = str.maketrans({"無": "无", "於": "于", "祐": "佑", "乾": "干", "説": "说", "輹": "辐",
                      "後": "后", "繫": "系", "幾": "几", "禮": "礼", "兇": "凶", "賁": "贲",
                      "復": "复", "離": "离", "兌": "兑", "恆": "恒", "遯": "遁", "巳": "已",
                      "豐": "丰", "祗": "祇", "梯": "稊", "濱": "滨", "獲": "获", "畫": "画"})

YAO_TI = re.compile(r"^(初九|初六|九二|六二|九三|六三|九四|六四|九五|六五|上九|上六|用九|用六)[：，,]?")
HEAD = re.compile(r"^#{0,4}\s*【(.{2,4})】\s*$")
MARKERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"


def norm(s: str) -> str:
    """匹配用归一：只留汉字，折异体字。"""
    return re.sub(r"[^\u4e00-\u9fff]", "", s or "").translate(FOLD)


def read_book() -> str:
    for p in (REPO / BOOK_FILE, REPO / "books" / Path(BOOK_FILE).name):
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    raise SystemExit(f"找不到书：{REPO / BOOK_FILE}")


def find_yao_anchor(lines, start: int, ti: str, body: str):
    """从 start 起找某一爻的经文行，返回 (经文起始行, 结束行, 差字数)。

    判据（缺一不可）：
      1. 行首是这个爻题（初九/六二/…）；
      2. 经文行后面（跳过空行、含**折行**）紧跟的第一个标题必须是【注释】——
         这一条排掉译文行（也以"初六，"开头）与他处引用本句爻辞的注释正文；
      3. 拼起来（含折行）的正文与本站爻辞，差字不超过 max(1, 25%)。
         这一条容忍电子本的 OCR 换字：实测 輹→复、入→人、窞→窗、汔→汽、繘→缅，
         但不容忍整句换成另一爻（那样差字远超两成）。
    """
    b = norm(body)
    if not b:
        return None, None, 0
    allow = max(1, round(len(b) * 0.25))
    for i in range(start, len(lines)):
        s = lines[i].strip()
        if not s or HEAD.match(s):
            continue
        if not norm(s).startswith(ti):
            continue
        # 经文行可能折行：一直拼到下一个【…】标题为止
        buf, j = [], i
        while j < len(lines) and not HEAD.match(lines[j].strip()):
            buf.append(lines[j].strip())
            j += 1
        m = HEAD.match(lines[j].strip()) if j < len(lines) else None
        if not (m and m.group(1) == "注释"):
            continue
        text = norm("".join(buf))
        core = text[len(ti):]
        if not core or len(core) > len(b) + 4:
            continue
        sm = difflib.SequenceMatcher(None, core, b)
        mismatch = max(len(core), len(b)) - sum(bl.size for bl in sm.get_matching_blocks())
        if mismatch > allow:
            continue
        return i, j, mismatch, " ".join(x for x in buf if x)
    return None, None, 0, ""


def comment_block(lines, header_idx: int):
    """取第 header_idx 行（【注释】标题）之后的注释正文，直到下一个【…】标题。"""
    if header_idx >= len(lines):
        return None
    m = HEAD.match(lines[header_idx].strip())
    if not (m and m.group(1) == "注释"):
        return None
    j = header_idx + 1
    buf = []
    while j < len(lines):
        s = lines[j].strip()
        if HEAD.match(s):
            break
        buf.append(s)
        j += 1
    return "\n".join(buf).strip()


def split_notes(block: str):
    """把注释块拆成 [{word, text}]：①②③ 编号分段，段首到第一个冒号是被注的字词。

    被注的字词就是拈字时要找的那个"字"（如"血去惕出"），所以单列出来。
    两处清理，都只动 headword、不动 text：
      · 去掉随注的拼音（"枯杨生梯(tí)" → "枯杨生梯"）——拼音是给读音的，不是被注的字；
      · 冒号远在第 40 字之后的，不算 headword（那是一条总说，不是针对某个字词）。
        （被注的整句爻辞也允许，如"过涉灭顶，凶。无咎"，那正是要拈的那句。）
    """
    if not block:
        return []
    parts, cur = [], ""
    for ch in block:
        if ch in MARKERS:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    out = []
    for p in parts:
        t = p.replace("\n", " ").strip()
        if not t:
            continue
        head, sep, rest = t.partition("：")
        if not sep:
            head, sep, rest = t.partition(":")
        if sep and len(head) <= 40:
            word = re.sub(r"[（(][^）)]*[）)]", "", head).strip()
            out.append({"word": word, "text": rest.strip()})
        else:
            out.append({"word": "", "text": t})
    return out


def main() -> int:
    report_only = "--report" in sys.argv
    data = json.loads(MEIHUA_DATA.read_text(encoding="utf-8"))
    by_order = data["hexagrams"]["by_order"]
    lines = read_book().split("\n")

    # ---- 逐卦逐爻抽注释 ----
    # 不用标题、也不用卦辞切卦：这个电子本的标题行丢了两条（大过/小过），
    # 卦辞又被 OCR 改过字（复作覆、汔作汽、繘作缅）。改为按通行本次序
    # 逐爻往下锚定：顺序本身就把六十四卦串起来了，锚不上的立刻报出来。
    out, bad, stat = {}, [], []
    cursor = 0
    for n in range(1, 65):
        g = by_order[str(n)]
        key = f"{g['upper']['num']},{g['lower']['num']}"
        canon = PURE.get(CANON[n - 1], CANON[n - 1])
        if g["name"] != canon and not g["name"].endswith(CANON[n - 1]):
            bad.append(f"第{n}卦 名称对不上：本站 {g['name']} / 通行本 {CANON[n - 1]}")
        yao, diffs = {}, []
        for pos, yc in enumerate(g["yaoci"], 1):
            ti = YAO_TI.match(yc).group(1) if YAO_TI.match(yc) else ""
            idx, hd, mismatch, jing = find_yao_anchor(lines, cursor, ti, YAO_TI.sub("", yc))
            if idx is None:
                bad.append(f"{g['name']} 第{pos}爻：锚不到经文行（{yc}）")
                continue
            blk = comment_block(lines, hd)
            if not blk:
                bad.append(f"{g['name']} 第{pos}爻：经文行后没有【注释】块（第{idx + 1}行）")
                continue
            notes = split_notes(blk)
            if not notes:
                bad.append(f"{g['name']} 第{pos}爻：注释块拆不出条目（第{idx + 1}行）")
                continue
            # 经文行可能折行（实测地天泰九三就折了），拼起来才是完整一句
            yao[str(pos)] = {"jing": jing.lstrip("#").strip(),
                             "raw": blk, "notes": notes, "line": idx + 1,
                             "diff": mismatch}
            diffs.append(mismatch)
            cursor = idx + 1
        out[key] = {"name": g["name"], "order": n, "canon": CANON[n - 1], "yao": yao}
        stat.append((g["name"], len(yao), sum(len(v["notes"]) for v in yao.values()),
                     max(diffs) if diffs else 0))

    total_yao = sum(s[1] for s in stat)
    total_note = sum(s[2] for s in stat)
    print(f"爻：{total_yao}/384　注释条目：{total_note}")
    fuzzy = [(s[0], s[3]) for s in stat if s[3] > 0]
    if fuzzy:
        print(f"含 OCR 差字的卦（{len(fuzzy)}，括号内为该卦最大差字数）："
              + "、".join(f"{a}({b})" for a, b in fuzzy))
    if bad:
        print(f"问题 {len(bad)} 条：")
        for b in bad[:40]:
            print("  -", b)
    with_word = sum(1 for g in out.values() for v in g["yao"].values()
                    for nt in v["notes"] if nt["word"])
    print(f"带被注字词的条目：{with_word}/{total_note}")
    if report_only:
        return 0 if not bad else 1

    doc = {
        "version": 1,
        "src": {"book": BOOK_LABEL, "part": "【注释】", "file": BOOK_FILE},
        "note": ("逐词训诂取自该书【注释】原文，只作字词与象的训释；"
                 "本站不取该书【译文】，整句白话会把爻辞的意思压平，妨碍拈字。"
                 "爻辞是象的语言：与卦象、外应相合者，可拈其中一二字为验证，不必整句照搬。"),
        "by_key": out,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写入 {OUT}（{OUT.stat().st_size} 字节）")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
