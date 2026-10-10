# -*- coding: utf-8 -*-
"""
反义规则 · 同盘矛盾检测（开源做法 `check_conflicts.js` 的本地实现）
==================================================================
一句话：随机造大量命盘／卦，检查**同一屏**上不会同时出现两个互相打架的结论。
开源项目 bazi-engine 生成 1000 个随机盘去查 40 对反义规则（甲强 vs 甲弱）是否同盘双命中，
本工具是同一思路，但"反义对"按本站实际结构定义——本站的结论不是单条断语，
而是**四张清单**（喜用 F／忌神 J／调候 T0／处方 R）＋**流动判定表命中行**＋**大忌清单**：

  硬矛盾（✗，必须处置——都是引擎自相矛盾，与术数取舍无关）：
    H1  喜用 ∩ 忌神 ≠ ∅          ——同一五行既是喜用又是忌神
    H2  最终处方落在忌神里        ——裁决说"强制改方"却仍喂忌神
    H3  改方后的处方仍喂忌神      ——改方没改出矛盾（block → redirect → 还是逆）
    H4  裁决 block 而改方＝原方   ——页面会显示"改方 X → X"，等于说谎
  待人工判（?）：
    H5  调候 ∩ 忌神 ≠ ∅ 而未标注  ——书理冲突，本站的处置是"从格成格则调候让位"，
                                    必须留下 adjust_marks 痕迹，静默即缺陷
    A1  同一五行同屏既"开"又"禁"  ——跨来源（喜用说宜／流动表说忌）不算错，但必须计数
    A2  同一命中行内两条格的判词逐字相同 ——疑似复制粘贴
    A3  grade 不在声明枚举 GRADE_ORDER 内 ——前后端配色/禁清单会漏

用法：
    cd backend
    python tools/audit_conflicts.py                # 默认 300 盘（每盘再配 1 卦），约 1.5 分钟
    python tools/audit_conflicts.py --n 2000 --seed 42
    python tools/audit_conflicts.py --examples 5   # 每个发现打印几条可复现样本
输出：data/audit_conflicts_report.txt + 终端摘要。
退出码：有 ✗ → 1。
"""
import argparse
import io
import random
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WX = ("木", "火", "土", "金", "水")
# 反义档位对：同一屏同一个五行不得同时落进这两组（"忌多"单列——语义是"少则可、多则忌"，
# 是否纳入硬禁清单属术数取舍，见《六爻分歧登记表》（原待裁项已于 2026-09-24 全部裁定），
# 本工具只统计不替它定）
POSITIVE_GRADES = ("首选", "专用", "宜", "宜少量", "改补同类")
NEGATIVE_GRADES = ("忌", "大忌")
EXTRA_GRADES = ("忌多",)


class Findings:
    def __init__(self):
        self.lines = []
        self.hard = Counter()
        self.soft = Counter()
        self.samples = {}

    def add(self, s=""):
        self.lines.append(s)

    def hit(self, code, sample="", hard=True):
        (self.hard if hard else self.soft)[code] += 1
        if sample:
            self.samples.setdefault(code, [])
            if len(self.samples[code]) < 8:
                self.samples[code].append(sample)


def _rand_birth(rng):
    return {"year": rng.randint(1940, 2015), "month": rng.randint(1, 12),
            "day": rng.randint(1, 28), "hour": rng.randint(0, 23),
            "minute": rng.randint(0, 59), "gender": rng.choice([0, 1])}


def _rand_gua(rng):
    import liuyao_engine as E
    raw = []
    for _ in range(6):
        coins = [rng.randint(0, 1) for _ in range(3)]
        L = E.line_from_coins(coins)
        L["coins"] = list(coins)
        raw.append(L)
    base = datetime(2024, 1, 1)
    return E._build_paipan_from_raw(raw, base + timedelta(minutes=rng.randint(0, 300000)))


QUESTIONS = ["求财能成吗", "这次升职有望吗", "买这套房子合适吗", "孩子这次考试怎么样",
             "我最近运势如何", "父亲身体如何", "和合伙人能谈成吗", "这段感情能长久吗"]


def _flow_lists(R_final, mingju):
    """处方行的开／禁清单：{五行: [档位...]}。"""
    from wuxing_flow import flow_plan
    plan = flow_plan(R_final, mingju)
    active = next((r for r in plan["rows"] if r.get("active")), None)
    opened, banned, extra = {}, {}, {}
    if not active:
        return plan, opened, banned, extra
    for rel, cell in (active.get("cells") or {}).items():
        if not cell:
            continue
        grade = cell.get("grade", "")
        target = {"进气": None, "出水": None, "我克": None, "克我": None}
        from wuxing_flow import MOTHER, SHENG, KE, KEME, WX_ORDER
        wx = plan["wx"]
        target = {"进气": MOTHER[wx], "出水": SHENG[wx], "我克": KE[wx], "克我": KEME[wx]}[rel]
        if grade in POSITIVE_GRADES:
            opened.setdefault(target, []).append("%s·%s" % (rel, grade))
        elif grade in NEGATIVE_GRADES:
            banned.setdefault(target, []).append("%s·%s" % (rel, grade))
        elif grade in EXTRA_GRADES:
            extra.setdefault(target, []).append("%s·%s" % (rel, grade))
    return plan, opened, banned, extra


def check_chart(f: Findings, birth, mingju, rem=None, tag="八字", marks=None):
    """对一张盘跑全部一致性检查。rem 非空时表示处方来自六爻（走同一条命卦校验链）。

    marks 必须由调用方从 `build_bazi_paipan(...)["xiji"]["adjust_marks"]` 取——
    compute_baseline 的返回里**没有** adjust_marks，早先在这里读 mingju["adjust_marks"]
    永远为空，会把 61 个已标注的从格盘误报成"未标注"（工具自己踩过一次，记此存照）。
    """
    from wuxing_relation import adjudicate, redirect, grade_J, grade_F, grade_T
    F, J, T0 = mingju.get("F") or [], mingju.get("J") or [], mingju.get("T0") or []
    month_wx = mingju.get("month_wx") or ""
    who = "%s %s" % (tag, birth.get("solar") if isinstance(birth, dict) and birth.get("solar")
                    else birth)

    # H1 喜用 ∩ 忌神
    both = sorted(set(F) & set(J))
    if both:
        f.hit("H1 喜用∩忌神", "%s → %s" % (who, "、".join(both)))

    # H5 调候 ∩ 忌神（须有 adjust_marks 痕迹，否则是静默冲突）
    t_j = sorted(set(T0) & set(J))
    if t_j:
        noted = any("调候" in m for m in (marks or []))
        f.hit("H5 调候∩忌神未标注", "%s → %s（from_ge=%s marks=%s）"
              % (who, "、".join(t_j), mingju.get("from_ge") or "无", marks),
              hard=not noted)

    Rs = [rem["R"]] if rem else list(WX)
    for R in Rs:
        if R not in WX:
            f.hit("H0 处方非五行", "%s → R=%r" % (who, R))
            continue
        v = adjudicate(R, F, J, T0, month_wx)
        R_final, why = R, ""
        if v.get("gate") == "block":
            R_final, why = redirect(R, v, F, J, T0)
            if not R_final:
                # 新契约（2026-10-06 H3）：三重过滤后候选全灭 → redirect 返回空改方，
                # 这是书证兜底（《子平真诠》「如原局无通关之神，亦必运程弥其缺憾」），
                # 不是缺陷——计为信息，不回退成 H4。
                f.hit("· 改方无解（待岁运通关之地）", "%s → R=%s" % (who, R), hard=False)
            elif R_final == R:
                f.hit("H4 裁决block但改方＝原方", "%s → R=%s／%s（%s）" % (who, R, R_final, v.get("decision")))
            else:
                bad = [j for j in J if grade_J(R_final, j)["net"] == "逆"]
                bad_f = [x for x in F if grade_F(R_final, x)["net"] == "逆"]
                if bad or bad_f:
                    f.hit("H3 改方仍喂忌神/克喜用",
                          "%s → 原方%s 改方%s 仍喂忌神%s／克喜用%s"
                          % (who, R, R_final, "、".join(bad), "、".join(bad_f)))
                if v.get("tiao_active"):
                    bad_t = [t for t in T0 if grade_T(R_final, t)["net"] == "逆"]
                    if bad_t:
                        f.hit("H3 改方仍喂忌神/克喜用",
                              "%s → 原方%s 改方%s 仍逆调候%s" % (who, R, R_final, "、".join(bad_t)))
        # H2 最终处方落在忌神里（非 block 路径）
        if R_final in J and v.get("gate") != "block":
            f.hit("H2 最终处方∈忌神", "%s → R=%s" % (who, R_final))

        # 无解时（redirect 返回空）按原处方画流动表——与 deterministic_conclusion 同口径
        flow_wx = R_final if R_final in WX else R
        plan, opened, banned, extra = _flow_lists(flow_wx, mingju)
        if not plan.get("rows"):
            continue
        # A1 同一五行同屏既开又禁（跨来源：喜用/调候/处方 一侧 vs 禁清单 一侧）
        pos = set(F) | set(T0) | ({flow_wx} if flow_wx in WX else set())
        for x in sorted(pos & set(banned)):
            src = []
            if x in F:
                src.append("喜用")
            if x in T0:
                src.append("调候")
            if x == flow_wx:
                src.append("处方")
            f.hit("A1 同屏既开又禁",
                  "%s → %s（%s）⇒ 禁：%s" % (who, x, "+".join(src), "、".join(banned[x])),
                  hard=False)
        # A2 同一命中行内判词逐字相同
        notes = {}
        for rel, cell in (next(r for r in plan["rows"] if r.get("active")).get("cells") or {}).items():
            if cell and cell.get("note"):
                notes.setdefault(cell["note"], []).append(rel)
        dup = {k: v for k, v in notes.items() if len(v) > 1}
        if dup:
            f.hit("A2 同行内判词重复",
                  "%s → R=%s 判词重复于 %s" % (who, R_final, "、".join("／".join(v) for v in dup.values())),
                  hard=False)
        # A3 grade 不在声明枚举内
        from wuxing_flow import GRADE_ORDER
        for rel, cell in (next(r for r in plan["rows"] if r.get("active")).get("cells") or {}).items():
            g = (cell or {}).get("grade", "")
            if g and g not in GRADE_ORDER:
                f.hit("A3 grade不在GRADE_ORDER内", "%s → %s·%s=%s" % (who, R_final, rel, g), hard=False)
        if extra:
            f.hit("· 忌多档位出现", "%s → R=%s %s" % (who, R_final, extra), hard=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260923)
    ap.add_argument("--examples", type=int, default=3)
    ap.add_argument("--out", default="data/audit_conflicts_report.txt")
    args = ap.parse_args()

    from wuxing_flow import GRADE_ORDER
    from liuyao_remedy import liuyao_remedy
    from bazi_engine import build_bazi_paipan
    from wuxing_quality import hidden_tally
    f = Findings()
    f.add("反义规则·同盘矛盾检测（%s）｜n=%d｜seed=%d"
          % (datetime.now().strftime("%Y-%m-%d %H:%M"), args.n, args.seed))
    f.add("GRADE_ORDER（声明枚举）：%s" % "、".join(GRADE_ORDER))

    rng = random.Random(args.seed)
    n_bazi = n_liuyao = 0
    for _ in range(args.n):
        b = _rand_birth(rng)
        try:
            # 一次排盘拿全：xiji.mingju 就是命局基线，adjust_marks 也在 xiji 里
            # （compute_baseline 只转发 mingju 的一部分、丢掉 adjust_marks，
            #   而大运计算很贵——审计要跑上千张盘，不能排两次）
            data = build_bazi_paipan(b["year"], b["month"], b["day"], b["hour"], b["minute"],
                                     b["gender"])
            xiji = data["xiji"]
            gans = [p["gan"] for p in data["bazi"]]
            zhis = [p["zhi"] for p in data["bazi"]]
            mingju = dict(xiji["mingju"])
            mingju.update({"wuxing_tally_hidden": hidden_tally(gans, zhis),
                           "gans": gans, "zhis": zhis, "month_zhi": zhis[1]})
        except Exception:
            continue
        n_bazi += 1
        b["solar"] = data["solar"]
        marks = xiji.get("adjust_marks") or []
        check_chart(f, b, mingju, rem=None, tag="八字", marks=marks)
        # 六爻侧：随机卦 × 这张命盘 → 走产品同一条"命卦校验"链
        try:
            g = _rand_gua(rng)
            rem = liuyao_remedy(g, QUESTIONS[n_liuyao % len(QUESTIONS)])
        except Exception as e:
            f.hit("H9 六爻处方抛异常", "%s：%s" % (type(e).__name__, e))
            continue
        n_liuyao += 1
        check_chart(f, {"solar": "%s ｜ 卦：%s（问：%s）" % (data["solar"], g["ben_gua"]["name"],
                                                           QUESTIONS[n_liuyao % len(QUESTIONS)])},
                    mingju, rem=rem, tag="六爻", marks=marks)
    f.add("\n样本：命盘 %d 张（每张遍历 5 个候选处方）＋ 六爻 %d 卦" % (n_bazi, n_liuyao))

    f.add("\n【✗ 硬矛盾（引擎自相矛盾，必须处置）】")
    if not f.hard:
        f.add("  无")
    for code, c in f.hard.most_common():
        f.add("  ✗ %-26s %d 次" % (code, c))
    f.add("\n【? / · 待人工判与信息】")
    for code, c in f.soft.most_common():
        f.add("  · %-26s %d 次" % (code, c))
    if args.examples:
        f.add("\n【样本（各取前 %d 条，便于复现）】" % args.examples)
        for code, items in f.samples.items():
            f.add("  %s：" % code)
            for s in items[:args.examples]:
                f.add("    - %s" % s)

    text = "\n".join(f.lines)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(text)
    print("\n报告已写入：%s" % out)
    return 1 if f.hard else 0


if __name__ == "__main__":
    sys.exit(main())
