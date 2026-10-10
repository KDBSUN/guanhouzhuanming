# -*- coding: utf-8 -*-
"""
规则命中审计（开源做法 `audit_hit_distribution` 的本地实现）
============================================================
一句话：把"每条规则到底命中过几次"算出来——**恒真的规则是坏规则**（条件永远成立，
等于没写条件），**永不命中的规则是死规则**（条件不可达，或早被上游短路）。

为什么要它：判定表、处方分支、引文索引都是手写条件拼出来的。单测只验"给定输入
得到期望输出"，验不出"这条规则在真实输入分布下根本没被走到"。bazi-engine 用
`audit_hit_distribution.js` 跑大样本揪 100% 命中的断语，本工具是同一思路，另多做两件：

  1. **全枚举（证明，不是抽样）**：流动判定表的状态分档只依赖三个离散量——
     五行计数（8 字分 5 行，共 C(12,4)=495 种）、月令五行（5）、格局（11）。
     穷举 27225 个上下文，任何"从未产出的档位"就是结构性死规则，与样本量无关。
  2. **置信区间**：抽样部分给 Wilson 95% 区间。0/N 命中的规则，真实命中率的 95%
     上界约 3/N——N 小的时候"0 命中"什么都说明不了，报表里必须看得到这一点，
     否则会把"样本太少"读成"规则已死"。

用法：
    cd backend
    python tools/audit_rule_hits.py                 # 全跑（默认 300 盘 / 300 卦，约 1 分钟）
    python tools/audit_rule_hits.py --n 2000        # 加大样本（约 7 分钟，只为收紧置信区间）
    python tools/audit_rule_hits.py --only flow     # 只跑某一节（flow/liuyao/meihua/quotes）
    python tools/audit_rule_hits.py --seed 42

输出：data/audit_rule_hits_report.txt（全文）+ 终端摘要。
退出码：有 ✗ 级发现 → 1（可挂 CI）；只有 ? / · → 0。
"""
import argparse
import ast
import io
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 判定表状态分档的三个离散量：计数空间由"8 字"决定（4 干 + 4 支）
WX_ORDER = ["木", "火", "土", "金", "水"]
FLOW_STATES = ["弱", "弱极", "中和偏旺", "旺极(从格)"]
RELS = ("进气", "出水", "我克", "克我")
# from_ge 的全部形态（bazi_engine 判格处逐串核对）：专旺/化气会改分档，其余四类不参与
GE_KINDS = ([""] + ["专旺格（%s）" % w for w in WX_ORDER]
            + ["化气格（%s）" % w for w in WX_ORDER]
            + ["从儿格", "从杀格（弃命从杀）", "从财格", "从势格"])


# ---------------------------------------------------------------------------
# 统计小工具
# ---------------------------------------------------------------------------
def wilson(k: int, n: int, z: float = 1.96):
    """Wilson 95% 区间（工程统计，与术数无关；只为让"0 命中"别被读成"规则已死"）。"""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (max(0.0, (c - r) / d), min(1.0, (c + r) / d))


class Report:
    def __init__(self):
        self.lines = []
        self.hard = []       # ✗ 必须处置
        self.soft = []       # ? 待人工判
        self.info = []       # · 信息

    def add(self, s=""):
        self.lines.append(s)

    def hard_finding(self, s):
        self.hard.append(s)
        self.add("  ✗ " + s)

    def soft_finding(self, s):
        self.soft.append(s)
        self.add("  ? " + s)

    def note(self, s):
        self.info.append(s)
        self.add("  · " + s)


# ---------------------------------------------------------------------------
# 样本生成
# ---------------------------------------------------------------------------
def _rand_birth(rng):
    return {"year": rng.randint(1940, 2015), "month": rng.randint(1, 12),
            "day": rng.randint(1, 28), "hour": rng.randint(0, 23),
            "minute": rng.randint(0, 59), "gender": rng.choice([0, 1])}


def _iter_baselines(n, seed):
    from mingju_profile import compute_baseline
    rng = random.Random(seed)
    for _ in range(n):
        b = _rand_birth(rng)
        try:
            yield b, compute_baseline(b)["mingju"]
        except Exception as e:                      # 排盘失败不该让审计停摆
            yield b, {"__error__": str(e)}


def _iter_guas(n, seed):
    """随机六爻卦：六次三钱 + 随机起卦时刻。"""
    import liuyao_engine as E
    rng = random.Random(seed + 7)
    base = datetime(2024, 1, 1)
    for _ in range(n):
        raw = []
        for _i in range(6):
            coins = [rng.randint(0, 1) for _ in range(3)]
            L = E.line_from_coins(coins)
            L["coins"] = list(coins)
            raw.append(L)
        dt = base + timedelta(minutes=rng.randint(0, 3 * 365 * 24 * 60))
        yield E._build_paipan_from_raw(raw, dt)


# ---------------------------------------------------------------------------
# ① 流动判定表：全枚举可达性
# ---------------------------------------------------------------------------
def _compositions(total, parts):
    """total 分成 parts 个非负整数份（8 字分 5 行 = 495 种）。"""
    if parts == 1:
        yield (total,)
        return
    for i in range(total + 1):
        for rest in _compositions(total - i, parts - 1):
            yield (i,) + rest


def audit_flow_exhaustive(rep: Report):
    from wuxing_flow import classify_state
    rep.add("\n【① 流动判定表 · 状态分档可达性（全枚举：495 计数 × 5 月令 × 11 格局）】")
    hit = Counter()
    n_ctx = 0
    for comp in _compositions(8, 5):
        tally = dict(zip(WX_ORDER, comp))
        for month_wx in WX_ORDER:
            for ge in GE_KINDS:
                eff = ""
                if ge.startswith("专旺格"):
                    eff = ge[4:-1]                       # 专旺格（金） → 金
                elif ge.startswith("化气格"):
                    eff = ge[4:-1]
                ctx = {"wuxing_tally": dict(tally), "month_wx": month_wx,
                       "wuxing_tally_hidden": dict(tally), "gans": [], "zhis": [],
                       "from_ge": ge, "effective_wx": eff}
                n_ctx += 1
                for wx in WX_ORDER:
                    st, _note = classify_state(wx, ctx)
                    hit[(wx, st)] += 1
    rep.note("上下文 %d 个；每个上下文对 5 个五行各判一次档" % n_ctx)
    dead = []
    for wx in WX_ORDER:
        parts = []
        for st in FLOW_STATES:
            c = hit[(wx, st)]
            parts.append("%s=%d" % (st, c))
            if c == 0:
                dead.append((wx, st))
        rep.add("  %s：%s" % (wx, "｜".join(parts)))
    if dead:
        rep.hard_finding("以下 (五行, 档位) 在全枚举下**从未产出**，该档四列判定是死规则：%s"
                         % "、".join("%s·%s" % d for d in dead))
    else:
        rep.note("20 个 (五行×档位) 组合全部可达（无一死档）")

    # 消费面：哪些 from_ge 形态会真正影响分档（其余四类从格不进流动表）
    consumed = set()
    for ge in GE_KINDS:
        eff = ge[4:-1] if ge else ""
        ctx = {"wuxing_tally": {"木": 2, "火": 2, "土": 2, "金": 1, "水": 1}, "month_wx": "木",
               "from_ge": ge, "effective_wx": eff}
        base = dict(ctx)
        for wx in WX_ORDER:
            st, _ = classify_state(wx, base)
            st2, _ = classify_state(wx, {**base, "from_ge": "", "effective_wx": ""})
            if st != st2:
                consumed.add(ge)
    rep.note("能改变分档结果的格局字样：%s" % ("、".join(sorted(consumed)) or "无"))
    ignored = [g for g in GE_KINDS if g and g not in consumed]
    if ignored:
        rep.soft_finding("以下 from_ge 字样对流动判定表的状态分档**无影响**（bazi_engine 会判出这几类，"
                         "但 classify_state 只认「专旺／化气」前缀）：%s——待人工判：是刻意如此，"
                         "还是从财/从杀/从儿/从势格在流动表里缺一条对应档？"
                         % "、".join(ignored))


# ---------------------------------------------------------------------------
# ② 流动判定表：真实随机命盘的命中率
# ---------------------------------------------------------------------------
def audit_flow_random(rep: Report, n: int, seed: int):
    from wuxing_flow import classify_state, TABLE
    rep.add("\n【② 流动判定表 · 真实随机命盘命中率（n=%d，seed=%d）】" % (n, seed))
    state_cnt = defaultdict(Counter)     # wx → state 计数
    cell_cnt = Counter()                 # (wx, state, rel) 计数
    grade_cnt = defaultdict(Counter)     # grade → (wx,state,rel)
    ok = 0
    for _b, mj in _iter_baselines(n, seed):
        if "__error__" in mj:
            continue
        ok += 1
        for wx in WX_ORDER:
            st, _note = classify_state(wx, mj)
            state_cnt[wx][st] += 1
            for rel in RELS:
                cell_cnt[(wx, st, rel)] += 1
                grade_cnt[TABLE[wx][st][rel][0]][(wx, st, rel)] += 1
    if ok == 0:
        rep.hard_finding("随机命盘一个都没成功排出，本节未生效")
        return
    rep.note("有效命盘 %d 个" % ok)
    always, never = [], []
    for wx in WX_ORDER:
        rep.add("  【%s】" % wx)
        for st in FLOW_STATES:
            c = state_cnt[wx][st]
            lo, hi = wilson(c, ok)
            rates = "｜".join("%s %.0f%%" % (rel, 100.0 * cell_cnt[(wx, st, rel)] / ok)
                              for rel in RELS)
            rep.add("    %-10s %5.1f%%（95%%CI %.1f–%.1f%%）  %s"
                    % (st, 100.0 * c / ok, 100.0 * lo, 100.0 * hi, rates))
            if c == ok:
                always.append("%s·%s" % (wx, st))
            if c == 0:
                never.append("%s·%s" % (wx, st))
    if always:
        rep.hard_finding("以下档位在 %d 个随机命盘里**每次都命中**（条件恒真，等于没条件）：%s"
                         % (ok, "、".join(always)))
    if never:
        lo_upper = 3.0 / ok
        rep.soft_finding("以下档位在 %d 个随机命盘里一次未命中（0 命中的 95%% 上界≈%.2f%%，"
                         "样本不足时不能据此判死，需结合①的全枚举结论看）：%s"
                         % (ok, 100 * lo_upper, "、".join(never)))
    # 档位级：同一五行四档的比例是否悬殊到"某档其实是唯一出口"
    for wx in WX_ORDER:
        top, cnt = state_cnt[wx].most_common(1)[0]
        if cnt == ok:
            rep.soft_finding("%s 的状态分档只有一个出口（%s 占 100%%），"
                             "说明该行的其余三档在真实分布里形同虚设" % (wx, top))
    grade_hits = Counter()
    for g, cells in grade_cnt.items():
        grade_hits[g] = sum(cells.values())
    rep.note("各档位被命中的判定格数（共 %d 格）：%s"
             % (len(cell_cnt), "、".join("%s %d 格" % (g, c) for g, c in grade_hits.most_common())))


# ---------------------------------------------------------------------------
# ③ 六爻：爻旺衰 / 处方分支 / 格局命中率
# ---------------------------------------------------------------------------
QUESTIONS = ["求财能成吗", "这次升职有望吗", "买这套房子合适吗", "孩子这次考试怎么样",
             "我最近运势如何", "父亲身体如何", "和合伙人能谈成吗", "这段感情能长久吗"]


def _branch_of(rem: dict) -> str:
    """处方分支归类（与 liuyao_remedy 的分支一一对应，供命中率统计）。"""
    st, rs = rem.get("state", ""), rem.get("R_reason", "")
    if st == "忌神动克":
        return "忌神动克→取克忌者"
    if st == "用神衰弱":
        return "用神休囚且元神无力→取生元神者" if "取生元神者" in rs else "用神休囚→取元神"
    if st.startswith("用神伏藏"):
        return "用神伏藏而得出" if "得出" in st and "受制" not in st else "用神伏藏受制"
    if st == "用神旺相":
        return "用神旺相→直接加持"
    return "用神休囚→直接加持（其余）"


def audit_liuyao(rep: Report, n: int, seed: int):
    from liuyao_remedy import liuyao_remedy
    import liuyao_patterns as P
    rep.add("\n【③ 六爻 · 爻旺衰与处方分支命中率（n=%d 卦，seed=%d）】" % (n, seed))
    branch, grade_cnt, five_cnt = Counter(), Counter(), Counter()
    pat_cnt = Counter()
    yong_grade = Counter()
    ok = 0
    for i, g in enumerate(_iter_guas(n, seed)):
        q = QUESTIONS[i % len(QUESTIONS)]
        try:
            rem = liuyao_remedy(g, q)
        except Exception as e:
            pat_cnt["处方异常：" + type(e).__name__] += 1
            continue
        ok += 1
        branch[_branch_of(rem)] += 1
        det = rem.get("details") or {}
        for row in det.get("各爻旺衰") or []:
            grade_cnt[row.get("旺衰")] += 1
            five_cnt[row.get("月令五态")] += 1
        y = det.get("用神爻") or {}
        yong_grade[y.get("旺衰")] += 1
        try:
            res = P.analyze(g, rem, rem.get("yongshen", ""))
        except Exception as e:
            pat_cnt["格局异常：" + type(e).__name__] += 1
            continue
        for it in res.get("暗动日破") or []:
            pat_cnt["暗动日破·" + it["判定"]] += 1
        for it in res.get("旬空") or []:
            pat_cnt["旬空·" + it["倾向"]] += 1
        for it in res.get("进退神") or []:
            pat_cnt[it["类型"]] += 1
        for it in res.get("三墓") or []:
            pat_cnt["三墓"] += 1
        for it in res.get("三合局") or []:
            pat_cnt["三合局·" + ("成局" if it["成局"] else "未成局")] += 1
        hc = res.get("六合六冲") or {}
        pat_cnt["六合"] += len(hc.get("合好") or [])
        pat_cnt["六冲"] += len(hc.get("相击") or [])
        pat_cnt["月破"] += len(res.get("月破") or [])
        pat_cnt["反伏吟"] += (1 if (res.get("反伏吟") or {}).get("卦之反吟") else 0)
        pat_cnt["伏吟"] += (1 if (res.get("反伏吟") or {}).get("伏吟") else 0)
        if (res.get("伏神") or {}).get("适用"):
            pat_cnt["伏神适用"] += 1
    if ok == 0:
        rep.hard_finding("随机卦一个都没算出来，本节未生效")
        return
    rep.note("有效卦 %d 个" % ok)
    rep.add("  处方分支命中率：")
    for k, c in branch.most_common():
        lo, hi = wilson(c, ok)
        rep.add("    %-34s %5.1f%%（95%%CI %.1f–%.1f%%）" % (k, 100.0 * c / ok, 100.0 * lo, 100.0 * hi))
        if c == ok:
            rep.hard_finding("处方分支「%s」在 %d 卦里每次都命中（前置条件恒真）" % (k, ok))
        if c == 0:
            rep.soft_finding("处方分支「%s」一次未命中（0/%d）" % (k, ok))
    tot_lines = sum(grade_cnt.values()) or 1
    rep.add("  逐爻综合旺衰（二分）：%s"
            % "、".join("%s %d 爻（%.1f%%）" % (k, v, 100.0 * v / tot_lines)
                        for k, v in grade_cnt.most_common()))
    rep.add("  逐爻月令五态：%s"
            % "、".join("%s %d" % (k, v) for k, v in five_cnt.most_common()))
    rep.add("  用神爻旺衰：%s" % "、".join("%s %d" % (k, v) for k, v in yong_grade.most_common()))
    missing_states = [s for s in ("旺", "相", "休", "囚", "死") if not five_cnt.get(s)]
    if missing_states:
        rep.soft_finding("月令五态里 %s 未出现——若是采样不足则加大 --n，"
                         "若加大后仍不出现，说明该态在真实时令下不可达" % "、".join(missing_states))
    if len(grade_cnt) == 1:
        rep.hard_finding("逐爻综合旺衰只出现一个档（%s），二分开合形同虚设"
                         % list(grade_cnt)[0])
    rep.add("  格局判据命中（次数／样本）：%s"
            % "、".join("%s %d" % (k, v) for k, v in pat_cnt.most_common()))
    dead_pat = [k for k, v in pat_cnt.items() if v == 0]
    if dead_pat:
        rep.soft_finding("以下格局判据一次未命中：%s" % "、".join(dead_pat))


# ---------------------------------------------------------------------------
# ④ 梅花处方分支：全枚举
# ---------------------------------------------------------------------------
def audit_meihua(rep: Report):
    import itertools
    from remedy import meihua_remedy
    from wuxing_relation import SHENG as S, KE as K
    rep.add("\n【④ 梅花处方 R · 分支全枚举（体/用五行 × 体卦旺衰 × 变卦五行）】")
    # 分支识别按 R_reason 的特征片段（每条分支的措辞在 remedy.py 里唯一）
    MARKERS = [("取克用者", "用克体→制用（克用者）"),
               ("取克变者", "变卦克体→制变（克变者）"),
               ("体卦失令", "体失令（休囚死）→生体者"),
               ("体生用为泄", "体生用→生体者"),
               ("用生体为吉", "用生体→取用卦本气"),
               ("体克用为吉", "体克用→取体卦本气"),
               ("体用比和", "比和→取体用本气")]

    def _branch(reason: str) -> str:
        for mk, label in MARKERS:
            if mk in reason:
                return label
        return "未识别：" + reason[:20]

    branch = Counter()
    n = 0
    for ti, yong in itertools.product(WX_ORDER, WX_ORDER):
        if ti == yong:
            rel = "比和"
        elif S.get(yong) == ti:
            rel = "用生体"
        elif S.get(ti) == yong:
            rel = "体生用"
        elif K.get(ti) == yong:
            rel = "体克用"
        elif K.get(yong) == ti:
            rel = "用克体"
        else:
            continue
        for ti_status in ("旺", "相", "休", "囚", "死", None):
            for bian in [None] + WX_ORDER:
                n += 1
                r = meihua_remedy(ti, yong, rel, hu_wuxing=[],
                                  bian_wuxing=[bian] if bian else [], ti_status=ti_status)
                branch[_branch(r["R_reason"])] += 1
    rep.note("组合 %d 个" % n)
    for k, c in branch.most_common():
        rep.add("    %-30s %6d 次（%.1f%%）" % (k, c, 100.0 * c / n))
    if len(branch) < 2:
        rep.hard_finding("梅花处方只走到一个分支，其余分支全不可达")
    for k, c in branch.items():
        if c == 0:
            rep.hard_finding("梅花处方分支「%s」在全部组合下一次都没走到（死分支）" % k)
    unreached = [label for _mk, label in MARKERS if not branch.get(label)]
    if unreached:
        rep.hard_finding("梅花处方以下分支在全枚举下不可达（死分支）：%s" % "、".join(unreached))


# ---------------------------------------------------------------------------
# ⑤ 引文索引使用率：死键 / 未录键
# ---------------------------------------------------------------------------
_BOOK_STEMS = ("滴天髓", "穷通宝鉴", "渊海子平", "三命通会", "子平真诠", "元理赋", "增删卜易",
               "卜筮正宗", "梅花易数", "增广校正梅花易数", "黄帝内经", "五行大义", "周易",
               "图解三命通会", "图解滴天髓", "校正全本卜筮正宗")


def _code_string_literals():
    """backend/**.py 里所有字符串字面量（AST 取真值，不用正则扫源码）。

    **排除 book_quotes.py 自身**：那里的 book/loc 字段本来就是"书名·章节"形态，
    留着会把 60 多条章节名全报成"未录键"，把真信号淹掉。
    """
    out = []
    for p in sorted(ROOT.rglob("*.py")):
        if "__pycache__" in p.parts or p.name in (Path(__file__).name, "book_quotes.py"):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out.append((p.name, node.value))
    return out


def audit_quotes(rep: Report):
    from book_quotes import QUOTES, lookup
    rep.add("\n【⑤ 引文索引（book_quotes.QUOTES，共 %d 键）· 使用率】" % len(QUOTES))
    lits = _code_string_literals()
    dead, used = [], []
    for key in QUOTES:
        # 用**子串**判断"被引用"而不是 startswith：提示词散文里的称引写作「《增删卜易·用神章》」，
        # 带书名号；只认 startswith 会把这类全报成死键（工具第一版就这么误报过 10 条）。
        hits = [(f, s) for f, s in lits if key in s]
        if hits:
            used.append((key, hits[0][0]))
        else:
            dead.append(key)
    rep.note("被代码引用 %d 键；未被任何字符串字面量引用 %d 键" % (len(used), len(dead)))
    if dead:
        rep.soft_finding("以下引文键**没有任何代码引用**（可能是死键，也可能是提示词/文档里动态拼出的键，"
                         "需人工确认）：%s" % "、".join(dead))
    # 未录键：代码里像出处键、但 QUOTES 没有 → 前端"出处行"会显示"原文待录"
    unrecorded = Counter()
    for fname, s in lits:
        if "·" not in s or not s.startswith(_BOOK_STEMS) or len(s) > 40:
            continue
        if lookup(s)["text"] is None:
            unrecorded[(s, fname)] += 1
    if unrecorded:
        rep.note("代码引用但索引未录原文的键 %d 个（前端出处行会显示「原文待录」，不代拟）："
                 % len(unrecorded))
        for (s, fname), c in sorted(unrecorded.items()):
            rep.add("      %s（首发于 %s）" % (s, fname))
    else:
        rep.note("代码引用的出处键全部已录原文")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260923)
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default="data/audit_rule_hits_report.txt")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    rep = Report()
    rep.add("规则命中审计（%s）｜样本 n=%d｜seed=%d"
            % (datetime.now().strftime("%Y-%m-%d %H:%M"), args.n, args.seed))
    rep.add("读法：✗＝必须处置（恒真/死规则）；?＝待人工判（可能只是样本不足）；·＝信息")

    if not only or "flow" in only:
        audit_flow_exhaustive(rep)
        audit_flow_random(rep, args.n, args.seed)
    if not only or "liuyao" in only:
        audit_liuyao(rep, args.n, args.seed)
    if not only or "meihua" in only:
        audit_meihua(rep)
    if not only or "quotes" in only:
        audit_quotes(rep)

    rep.add("\n【汇总】✗ %d 处；? %d 处；· %d 处"
            % (len(rep.hard), len(rep.soft), len(rep.info)))
    text = "\n".join(rep.lines)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(text)
    print("\n报告已写入：%s" % out)
    return 1 if rep.hard else 0


if __name__ == "__main__":
    sys.exit(main())
