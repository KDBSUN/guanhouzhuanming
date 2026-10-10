# -*- coding: utf-8 -*-
"""
反馈语义层（claim 级反馈 + 边界样本 + 校准提案）
================================================
为什么要有这一层：整案级的二值反馈（应验/未验）**没有归因、没有局部性**——
一次校验同时用到 20+ 条规则与 5 类数值参数，一句"应验"无法归给任何一条旋钮，
因此不能用来调数值。本模块把反馈对象下沉到 **claim（可独立判定的小断言）**：

  claim = {id, type, text, rule(归属规则), params(参与参数), verifiability(可判定性),
           since/until(验证窗口), src(书证键)}

反馈以 claim 为单位，五档：应验 / 未验 / 反向 / 无法判定 / 未观察，另有"判错了"反例标记。

边界样本（`boundary_samples`）：校验时若某参数的判据值擦阈（|值−阈值| ≤ band），自动记账。
它是唯一能喂阈值的样本来源——只在边界上，才分得清"阈值该挪一挪"。

校准提案（`calibration_proposals`）：由 `analyze_calibration()` 生成，硬性护栏：
  ① 最小样本量；② 同向占比门槛；③ 单次变动幅度上限（±30%）；④ **必须人工批准**。
本模块只产出提案，**绝不自动改数**——术数案例没有对照组，拟合即自欺（weights.yaml 已声明）。
"""
import json
from datetime import date, datetime, timedelta

from decision_log import (add_boundary_samples, add_claim_feedback, add_proposal,
                          boundary_counts, claims_of, feedback_of, list_proposals,
                          pending_claims, recent, _UNSCOPED)
from weights import FLOW as _FLOW
from weights import ZERI_DAYS

VERDICTS = ("应验", "未验", "反向", "无法判定", "未观察")
VERIFIABILITY = ("客观可验", "主观可验", "不可验")

# 校准护栏（可在 weights.yaml · calibration 覆盖）
_CAL_DEFAULT = {"min_samples": 5, "min_same_direction": 4,
                "max_delta_ratio": 0.3, "flip_rate_threshold": 0.6}
BOUNDARY_BAND = float(_FLOW.get("boundary_band", 0.3))


def _cal() -> dict:
    from weights import CALIBRATION
    return {**_CAL_DEFAULT, **(CALIBRATION or {})}


# ---------------------------------------------------------------------------
# 一、claim 生成：把一次校验拆成可独立判定的断言
# ---------------------------------------------------------------------------

def _window(tier: str, today: str = "") -> tuple:
    days = int(ZERI_DAYS.get(tier or "S", 7))
    d0 = datetime.fromisoformat(today).date() if today else date.today()
    return d0.isoformat(), (d0 + timedelta(days=days)).isoformat()


def build_claims(verdict: dict, flows: list, liunian_info: dict = None,
                 date_info: dict = None, tier_info: dict = None,
                 elements: list = None, baseline_view: dict = None,
                 yingqi_info: dict = None, today: str = "") -> list:
    """一次校验 → claim 清单（可反馈、可核验、带归属与窗口）。"""
    tier = (tier_info or {}).get("tier", "S")
    since, until = _window(tier, today)
    claims, n = [], 0

    def _add(type_, text, rule, params=None, verifiability="主观可验", src="", win=None):
        nonlocal n
        n += 1
        claims.append({
            "id": "c%d" % n, "type": type_, "text": text, "rule": rule,
            "params": params or [], "verifiability": verifiability,
            "since": (win or (since, until))[0], "until": (win or (since, until))[1],
            "src": src,
        })

    v = verdict or {}
    if v.get("net"):
        _add("裁决", "本次裁决：%s（%s）" % (v.get("net"), v.get("decision", "")),
             "wuxing_relation.adjudicate",
             ["flow_thresholds", "weights.shiwang_weight"],
             "主观可验", "子平真诠·扶抑/穷通宝鉴·调候")

    # 大忌/忌清单（风险类：可主观核验"碰了它是否加重的迹象"）
    for f in (flows or []):
        wx = f.get("wx", "")
        for r in (f.get("rows") or []):
            if not r.get("active"):
                continue
            for rel, cell in (r.get("cells") or {}).items():
                if cell and cell.get("grade") in ("大忌", "忌"):
                    label = (f.get("header") or {}).get(rel, rel)   # 如 "克我（火·他克）"
                    _add("风险", "避免%s：%s（%s）" % (label, cell["grade"], cell.get("note", "")),
                         "wuxing_flow.row.%s" % rel, ["flow_thresholds"], "主观可验", cell.get("src", ""))

    if liunian_info and liunian_info.get("effective"):
        eff = {"drag": "引动凶（降档限时放行）", "boost": "岁运加持（升格）"}.get(liunian_info.get("effect"), "仅作背景")
        _add("岁运", "岁运%s·%s（%s）：%s" % (liunian_info.get("ganzhi", ""), liunian_info.get("wx", ""),
                                            liunian_info.get("strength", ""), eff),
             "liunian.liunian_overlay", ["shiwang_weight", "strong_threshold"],
             "主观可验", "滴天髓·从象/假从")

    # 择日（客观可验：自带日期，公测期最有价值的反馈源）
    if date_info and date_info.get("days"):
        yi = [d for d in date_info["days"] if d.get("yiji") == "宜"][:4]
        ji = [d for d in date_info["days"] if d.get("yiji") == "忌"][:4]
        if yi:
            _add("择日", "宜日：%s（卦气旺相）" % "、".join(d["date"][5:] for d in yi),
                 "zeri.date_table", ["zeri_yi_states", "shiwang_weight"],
                 "客观可验", "梅花易数·先天卦定应期",
                 win=(yi[0]["date"], yi[-1]["date"]))
        if ji:
            _add("择日", "忌日：%s（宜避开）" % "、".join(d["date"][5:] for d in ji),
                 "zeri.date_table", ["zeri_yi_states", "shiwang_weight"],
                 "客观可验", "梅花易数·先天卦定应期",
                 win=(ji[0]["date"], ji[-1]["date"]))

    # 关系类（乘侮/干合/冲合）与质地类：外推/表述类，标注不可独立核验或主观可验
    for f in (flows or []):
        for b in (f.get("branch_notes") or []):
            _add("关系", "%s：%s" % (b.get("type", ""), b.get("note", "")),
                 "wuxing_quality.%s" % ("stem_actions" if b.get("type") == "干合" else "branch_actions"),
                 [], "不可验", b.get("src", ""))
        for r in (f.get("rows") or []):
            for cell in (r.get("cells") or {}).values():
                cw = (cell or {}).get("chengwu")
                if cw and cw.get("value") in ("乘", "侮"):
                    _add("关系", "%s：%s" % (cw["value"], cw.get("note", "")),
                         "wuxing_quality.ke_triple", ["flow_thresholds.chengwu_margin"],
                         "主观可验", cw.get("src", ""))
        fl = f.get("flavor") or {}
        if fl.get("gan"):
            _add("建议", "补%s取【%s】味：%s" % (f.get("wx", ""), fl["gan"], fl.get("note", "")),
                 "wuxing_quality.pick_flavor", [], "主观可验", fl.get("src", ""))

    # 应期（客观可验，且是**唯一能收集"实际哪天发生"的断言**）：
    # 为什么单列这一条：应期的加权与门槛是全站最敏感的自定数字（实测：加权 −20% 或
    # 门槛 +20%，14 个真卦的日期表全部改变），但它此前**没有任何反馈通道**——
    # 反馈里的「择日」指的是宜忌日期表，与「应期之日」是两张不同的表。
    # 这条断言只报日期、不给吉凶，用户只需回答"实际是哪天发生的"（写在补充说明里）。
    if yingqi_info and (yingqi_info.get("dates") or []):
        ds = [str(d) for d in yingqi_info["dates"][:6]]
        extra = "；另按最终处方列有 %d 天" % yingqi_info["final_count"] if yingqi_info.get("final_count") else ""
        _add("应期", "应期之日（按卦）：%s%s；实际哪一天发生的，请写在补充说明里"
             % ("、".join(d[5:] for d in ds), extra),
             "yingqi.meihua_yingqi", ["yingqi.weights", "yingqi.gate"],
             "客观可验", "梅花易数·先天卦定应期",
             win=(ds[0], ds[-1]))

    # 去重（同类同文只留一条）＋限制条数（一次反馈不宜超过 12 条）
    seen, out = set(), []
    for c in claims:
        k = (c["type"], c["text"][:60])
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out[:12]


# ---------------------------------------------------------------------------
# 二、边界样本：判据值擦阈 —— 唯一能喂阈值的样本
# ---------------------------------------------------------------------------

def boundary_samples_of(flows: list, liunian_info: dict = None) -> list:
    """抽取擦阈样本：{param, value, threshold, side, at_verdict}。"""
    out = []
    for f in (flows or []):
        sc = f.get("state_score")
        if sc is None:
            continue
        for param in ("state_jiruo_max", "state_weak_max", "state_strong_min"):
            th = _FLOW.get(param)
            if th is None:
                continue
            th = float(th)
            if abs(float(sc) - th) <= BOUNDARY_BAND:
                out.append({"param": "flow_thresholds.%s" % param, "value": float(sc),
                            "threshold": th, "side": "上沿" if sc >= th else "下沿",
                            "at_verdict": f.get("state", "")})
        for r in (f.get("rows") or []):
            for rel, cell in (r.get("cells") or {}).items():
                cw = (cell or {}).get("chengwu")
                if not cw or cw.get("a") is None:
                    continue
                th = float(_FLOW.get("chengwu_margin", 1.0))
                diff = abs(float(cw["a"]) - float(cw["d"]))
                if abs(diff - th) <= BOUNDARY_BAND:
                    out.append({"param": "flow_thresholds.chengwu_margin", "value": round(diff, 2),
                                "threshold": th, "side": "上沿" if diff >= th else "下沿",
                                "at_verdict": cw.get("value", "")})
    if liunian_info and liunian_info.get("weight") is not None:
        th = float(_FLOW.get("strong_threshold", 0.5))
        w = float(liunian_info["weight"])
        if abs(w - th) <= BOUNDARY_BAND:
            out.append({"param": "strong_threshold", "value": w, "threshold": th,
                        "side": "上沿" if w >= th else "下沿",
                        "at_verdict": liunian_info.get("strength", "")})
    return out


# ---------------------------------------------------------------------------
# 三、校准提案：只看边界样本，只在护栏内，只等人工批准
# ---------------------------------------------------------------------------

def analyze_calibration() -> list:
    """边界样本 × claim 反馈 → 校准提案（不自动改数，全部落成"待批"）。

    **样本单位是"日志"，不是"反馈条数"** —— 这一点原先错了，而且是护栏失效的根因：
    原实现把一个日志上的**全部** verdict 都计数（`for verdict in fb.values()`），
    于是一条日志里 5 个 claim 全打「未验」，就凑满了 `min_samples=5`，
    提案随即产出，`flip_rate` 还是 1.0。护栏本来是防"样本太少就动阈值"的，
    结果它数的是**点击数**而不是**案例数**，一个人连点几下就能推动阈值。

    现在改成：同一日志对同一参数最多贡献 1 个样本，且只认**参与该参数的 claim** 的反馈
    （claim 自带 `params` 字段，正是为此而记）。`flip_rate` 也据此重算。
    """
    cal = _cal()
    counts = boundary_counts()
    proposals = []
    for item in counts:
        param, side = item["param"], item["side"]
        logs = item.get("log_ids") or []
        good = bad = 0
        for lid in logs:
            fb = feedback_of(lid, _UNSCOPED)      # 校准是服务端聚合统计，需跨人取样（不出接口原文）
            if not fb:
                continue
            claims = claims_of(lid, _UNSCOPED)
            # 只取"参与参数与本次边界参数相关"的 claim 的反馈；取不到 claim 明细时
            # （老数据没有 claims_json）退化为"该日志只算一条"，总之不再按条数累加。
            votes = [_param_matches(c.get("params") or [], param) and fb.get(c.get("id"))
                     for c in claims] if claims else []
            votes = [v for v in votes if v]
            if not votes:
                continue
            # 一条日志只投一票：只要有一个相关 claim 判为未验/反向，这条日志算反例
            if any(v in ("未验", "反向") for v in votes):
                bad += 1
            elif any(v in ("应验",) for v in votes):
                good += 1
        n = good + bad
        if n < int(cal["min_samples"]):
            continue
        flip = bad / n if n else 0.0
        if flip < float(cal["flip_rate_threshold"]):
            continue
        old = item["threshold"]
        step = 1.0
        # 方向：反馈差 → 把阈值朝"让这些边界样本离开边界"的方向挪（远离样本值）
        move = step * (1 if side == "上沿" else -1)
        new = round(old + move * float(cal["max_delta_ratio"]), 3)
        proposals.append(add_proposal(
            param=param, old_value=old, new_value=new, sample_ids=logs,
            n_samples=n, flip_rate=round(flip, 2),
            note="边界样本（%s）共 %d 例有效反馈（按日志去重），未验/反向占 %.0f%%；建议幅度受 ±%.0f%% 护栏限制，需人工批准"
                 % (side, n, flip * 100, float(cal["max_delta_ratio"]) * 100),
        ))
    return proposals


def _param_matches(claim_params: list, boundary_param: str) -> bool:
    """claim 的参与参数是否与边界样本的参数相关。

    两侧命名不总是一致：边界样本用 "flow_thresholds.state_jiruo_max"（具体到键），
    claim 的 params 有时只写到 "flow_thresholds"（到模块）。故按"同根"匹配：
    完全相同、或一方的首段等于对方的首段（flow_thresholds / strong_threshold …）。
    """
    root = boundary_param.split(".")[0]
    for p in claim_params or []:
        p = str(p)
        if p == boundary_param or p.split(".")[0] == root:
            return True
    return False


# ---------------------------------------------------------------------------
# 四、对外只读视图（反馈面板用）
# ---------------------------------------------------------------------------

def recent_for_feedback(limit: int = 5, owner: str = "") -> list:
    """最近若干次校验 + 其 claim 与已有反馈（反馈页的输入）——**限本人**。"""
    out = []
    for row in recent(limit, owner):
        if row.get("kind") != "check":
            continue
        claims = claims_of(row["id"], owner)
        if not claims:
            continue
        out.append({
            "log_id": row["id"], "ts": row["ts"], "question": row.get("question", ""),
            "net": row.get("net", ""), "decision": (row.get("decision") or "")[:120],
            "claims": claims, "feedback": feedback_of(row["id"], owner),
            "outcome": row.get("outcome", ""),
            # 实际发生日期：回给前端，让用户看到自己上次填的是什么（也便于补填）
            "actual_date": row.get("actual_date", "") or "",
        })
    return out


def calibration_view() -> dict:
    return {"proposals": list_proposals(), "boundary": boundary_counts(), "guardrails": _cal()}


def save_verdict(log_id: int, claim_id: str, verdict: str, note: str = "", owner: str = "") -> bool:
    if verdict not in VERDICTS:
        raise ValueError("非法反馈档：%r（合法：%s）" % (verdict, "、".join(VERDICTS)))
    return add_claim_feedback(int(log_id), str(claim_id), verdict, note or "", owner=owner)


__all__ = ["VERDICTS", "VERIFIABILITY", "BOUNDARY_BAND", "build_claims",
           "boundary_samples_of", "analyze_calibration", "recent_for_feedback",
           "calibration_view", "save_verdict", "pending_claims", "json"]
