# -*- coding: utf-8 -*-
"""
五行生克关系格 与 命卦校验裁决引擎
====================================
校验层唯一消费对象是"处方五行 R（Remedy）"——为促成当前之事、此刻最应强化或引入的五行。
命局侧保留三个参考系：扶抑用神 F、忌神 J、终身调候倾向 T0。

五行两两之间必然且只存在五种关系之一：比和 / 我生 / 生我 / 我克 / 克我。
据此做五档判断（不存在"无关"），并按下述否决权分级短路裁决，最终只输出
顺 / 平 / 逆 三个净档，供校验条展示；建议（方位/颜色/数字/物件/饮食/职业）
全部由 R 派生，自动继承校验结果。

裁决顺序（否决权分级）：
  1. R = J 或 R 生 J        → 逆·助忌/生忌  → 红档，强制改方
  2. 调候转急 且 R 逆 T     → 逆·逆调      → 红档，改方或降级
  2b. 调候转急 且 R 同调 T  → 顺·共振加急  → 绿档加成/升格
  3. R 克 F                 → 逆·犯喜      → 红黄档，改方
  4. R = F 或 R 生 F        → 顺·共振/资生 → 绿档，放行
  5. 其余                   → 平            → 黄档，限时放行
"""
from typing import Optional

WUXING = ("木", "火", "土", "金", "水")

# 我生 / 我克
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def relation(r: str, t: str) -> str:
    """R 对 t 的关系（以 R 为视角）：比和 / 我生 / 生我 / 我克 / 克我"""
    if r == t:
        return "比和"
    if SHENG.get(r) == t:
        return "我生"      # R 生 t
    if SHENG.get(t) == r:
        return "生我"      # t 生 R
    if KE.get(r) == t:
        return "我克"      # R 克 t
    if KE.get(t) == r:
        return "克我"      # t 克 R
    raise ValueError(f"非法五行: {r!r} 或 {t!r}")


def sheng_me(wx: str) -> str:
    """生 wx 的那一行（wx 之母）"""
    for e in WUXING:
        if SHENG[e] == wx:
            return e
    raise ValueError(f"非法五行: {wx!r}")


def ke_me(wx: str) -> str:
    """克 wx 的那一行（wx 之鬼）"""
    for e in WUXING:
        if KE[e] == wx:
            return e
    raise ValueError(f"非法五行: {wx!r}")


# ---------------------------------------------------------------------
# 对 F 的五档
# ---------------------------------------------------------------------
def grade_F(R: str, F: str) -> dict:
    rel = relation(R, F)
    table = {
        "比和": ("顺", "共振", "直接加持喜用", "放行", "命卦共振"),
        "我生": ("顺", "资生", "间接生扶喜用", "放行", "资生喜用"),
        "生我": ("中", "泄气", "处方引泄喜用", "限时放行", "引泄喜用，勿久用"),
        "克我": ("中", "受制", "处方受喜用制约", "限时放行", "受喜用制约，效果打折"),
        "我克": ("逆", "犯喜", "处方攻击喜用", "改方", "攻击喜用，应改通关"),
    }
    net, label, sem, handle, tip = table[rel]
    return {"ref": "F", "target": F, "rel": rel, "net": net, "label": label,
            "semantic": sem, "handle": handle, "tip": tip}


# ---------------------------------------------------------------------
# 对 J 的五档（方向反向对称）
# ---------------------------------------------------------------------
def grade_J(R: str, J: str) -> dict:
    rel = relation(R, J)
    table = {
        "比和": ("逆", "助忌", "直接喂养忌神", "强制改方", "命卦犯忌，强制改方"),
        "我生": ("逆", "生忌", "间接资敌", "强制改方", "资生忌神，强制改方"),
        "生我": ("顺", "泄忌", "忌旺者宜泄", "放行", "泄忌神之旺"),
        "我克": ("顺", "制忌", "制住忌神", "放行", "制忌有力"),
        "克我": ("中", "耗战", "与忌神缠斗", "限时放行", "与忌神缠斗，可换通关"),
    }
    net, label, sem, handle, tip = table[rel]
    return {"ref": "J", "target": J, "rel": rel, "net": net, "label": label,
            "semantic": sem, "handle": handle, "tip": tip}


# ---------------------------------------------------------------------
# 对 T 的调候关系
# ---------------------------------------------------------------------
def grade_T(R: str, T: str) -> dict:
    rel = relation(R, T)
    if rel == "比和":
        return {"ref": "T", "target": T, "rel": rel, "net": "顺", "label": "共振加急",
                "semantic": "与调候同气，加急", "handle": "放行", "tip": "与调候共振"}
    if rel in ("我生", "生我"):
        return {"ref": "T", "target": T, "rel": rel, "net": "顺", "label": "同调",
                "semantic": "相生而同调", "handle": "放行", "tip": "与调候相生"}
    # 我克 / 克我 → 逆调
    return {"ref": "T", "target": T, "rel": rel, "net": "逆", "label": "逆调",
            "semantic": "与调候相克，逆调", "handle": "改方或降级", "tip": "与调候相克"}


def tiao_active(T0, month_wx: str) -> bool:
    """调候活性：T0 被当令生助(月令生 T 或比和)则休眠；被当令克泄则转急"""
    if not T0:
        return False
    for t in T0:
        rel = relation(month_wx, t)   # 以月令 M 为视角，看 M 对 t
        if rel in ("我生", "比和"):   # M 生 t 或 M==t → 调候得助
            return False
        # M 克 t（我克）、t 生 M（生我）、t 克 M（克我）→ 调候被克泄耗
        return True
    return False


# ---------------------------------------------------------------------
# 裁决引擎
# ---------------------------------------------------------------------
def adjudicate(R: str, F, J, T0, month_wx: str, liunian_wx: str = "") -> dict:
    """
    把"处方五行"放进命局里做安全检查，输出 顺/平/逆 + 放行等级。
    （白话：R 是"我建议你多用哪个五行"；F/J/T0 是命局里的三张检查清单——
      F=扶抑喜用（八字偏枯时能扶它回正的五行）、J=忌神（碰了就加重的五行）、
      T0=调候用神（命局过寒过燥时非补不可的五行）；month_wx=起卦当月的月令五行，
      用来判断调候是"转急"（火烧眉毛，优先级最高）还是"休眠"。）

    R: 处方五行（单字）
    F/J/T0: 列表（可为空）
    month_wx: 当令月令五行（用于调候活性）
    liunian_wx: 岁运层预留接口（流年干支五行），当前不参与判定；
                未来需叠加流年时，按同一"门禁参考量元组"规则追加即可，不动本判定逻辑。
                （白话：流年是"第四张检查清单"的插口——先占位、不生效，
                 等书里的行运喜忌从文字规则固化成判定表后，在这里接入即可。）
    返回: {net, level, gate, decision, hits, tiao_active}
    """
    # 岁运层预留：liunian_wx 保留但暂不启用（架构上等价于追加一个门禁参考量元组）
    _ = liunian_wx
    F = [f for f in (F or []) if f]
    J = [j for j in (J or []) if j]
    T0 = [t for t in (T0 or []) if t]
    hits = []
    t_active = tiao_active(T0, month_wx)

    # 1. 忌神硬约束：R=J 或 R 生 J → 红
    for j in J:
        g = grade_J(R, j)
        if g["net"] == "逆":
            hits.append(g)
    if hits:
        return _verdict("逆", "red", "block", "强制改方：处方五行喂养忌神", hits, t_active)

    # 2. 调候转急 且 R 逆 T → 红
    if t_active:
        for t in T0:
            g = grade_T(R, t)
            if g["net"] == "逆":
                hits.append(g)
        if hits:
            return _verdict("逆", "red", "block", "改方或降级：处方与调候相克", hits, t_active)

    # 2b. 调候转急 且 R 与 T 同调/共振 → 调候加成（转急则调候优先，同调升格）
    t_green = []
    if t_active:
        for t in T0:
            g = grade_T(R, t)
            if g["net"] == "顺":
                t_green.append(g)

    # 3. R 克 F → 红黄
    for f in F:
        g = grade_F(R, f)
        if g["net"] == "逆":
            hits.append(g)
    if hits:
        return _verdict("逆", "red_yellow", "block", "改方：处方攻击扶抑喜用", hits, t_active)

    # 4. R=F 或 R 生 F → 绿（调候转急且同调时一并加成）
    green = []
    for f in F:
        g = grade_F(R, f)
        if g["net"] == "顺":
            green.append(g)
    if t_green:
        green.extend(t_green)
    if green:
        _dec = "放行：处方与命局喜用同气或资生"
        if t_green:
            _dec += "；与转急调候同调共振，调候加成"
        return _verdict("顺", "green", "pass", _dec, green, t_active)

    # 4b. 未直中喜用，但调候转急且同调 → 升格为顺
    if t_green:
        return _verdict("顺", "green", "pass",
                        "放行：处方虽未直中喜用，但与转急调候同调共振，依调候优先升格",
                        t_green, t_active)

    # 5. 其余 → 黄（限时放行）
    # 补一条说明用的命中（对 J 的中档、对 F 的中档都归入平）
    for j in J:
        g = grade_J(R, j)
        if g["net"] == "中":
            hits.append(g)
    for f in F:
        g = grade_F(R, f)
        if g["net"] == "中":
            hits.append(g)
    if not hits:  # 无命局参考系可命中（例如未填八字）
        hits.append({"ref": None, "rel": None, "net": "平", "label": "无命局校验",
                     "semantic": "未提供命局基线，仅按事体输出", "handle": "限时放行", "tip": "未经命局校验"})
    return _verdict("平", "yellow", "limited", "限时放行：处方与命局无明显顺逆，限事项时间窗使用", hits, t_active)


def _verdict(net, level, gate, decision, hits, t_active) -> dict:
    return {
        "net": net,          # 顺 / 平 / 逆
        "level": level,      # green / yellow / red_yellow / red
        "gate": gate,        # pass / limited / block
        "decision": decision,
        "hits": hits,
        "tiao_active": t_active,
    }


def _redirect_filter_ok(cand: str, F, J, T0, t_active: bool) -> tuple[bool, str]:
    """改方字的三重过滤（2026-09-23 规则命中审计 H3 后补）。

    改方字不得：
      ① 生助任何忌神——对每个 j，grade_J(cand, j) 不得为逆（比和＝直接喂养、我生＝间接资敌）；
      ② 克任何喜用——对每个 f，grade_F(cand, f) 不得为逆；
      ③ 调候转急时不得逆任何调候字。
    书理依据：《子平真诠·论用神》「通关……用神如是，而喜神与忌神之间，亦以运行通关之地，
    调和其气为美」；《论相神紧要》「合去忌神者为相，制化忌神者亦为相」（相神＝救应之神，
    其职分正是"去忌而不伤用"——本过滤是该职分的形式化；把改方字当作局外引入的相神，
    属工程类比，见 docs/调候与改方书证登记.md）。"""
    for j in J:
        if grade_J(cand, j)["net"] == "逆":
            return False, "生助忌神【%s】" % j
    for f in F:
        if grade_F(cand, f)["net"] == "逆":
            return False, "克喜用【%s】" % f
    if t_active:
        for t in T0:
            if grade_T(cand, t)["net"] == "逆":
                return False, "逆调候【%s】" % t
    return True, ""


def redirect(R: str, verdict: dict, F, J, T0) -> tuple[str, str]:
    """gate=block 时的替代处方 R' 与理由（制忌 / 调候 / 通关 / 生扶）。

    候选按既有优先级生成（克忌者 → 调候字 → 通关字 → 生扶喜用者 → 喜用本气），
    **每个候选都要过三重过滤**（_redirect_filter_ok）：改方字不得生助任何忌神、不得克任何喜用、
    调候转急时不得逆调候。为什么必须过滤：裁决把"喂忌神"判为逆并强制改方，改出来的方
    若仍喂另一个忌神，等于没改（2026-09-23 审计实测：旧逻辑下约 37% 的改方仍喂忌神——
    多忌神时只避开了触发的那一个）。

    全部候选都过不了滤 → 返回 ("", 说明)。书里的兜底是岁运，不是硬凑——
    《子平真诠·论用神》：「通关之法，极为重要，**如原局无通关之神，亦必运程弥其缺憾**，
    方有发展。用神如是，而喜神与忌神之间，亦以运行通关之地，调和其气为美」；
    同书：「病药为用，如原局无去病之神，必须运程弥其缺憾，方得发展，调候亦然。
    倘格局转变则不在此例。」故局内无解时如实标注"待岁运通关之地"，不以喂忌之方充数。
    """
    F = [x for x in (F or []) if x]
    J = [x for x in (J or []) if x]
    T0 = [x for x in (T0 or []) if x]
    t_active = bool(verdict.get("tiao_active"))
    cands = []
    # 候选生成（按既有四路优先级：制忌 → 调候 → 通关 → 生扶）——
    # 注意：adjudicate 的 hits 在**第一个 J 命中处就短路**，其余忌神不会出现在 hits 里；
    # 改方要对整张忌神表负责，故 J 候选不读 hits，直接对每个 j 生成克忌者。
    for j in J:
        r2 = ke_me(j)
        cands.append((r2, f"改取克忌神【{j}】者【{r2}】制忌通关"))
    if t_active:
        for t in T0:
            cands.append((t, f"原处方与调候相克，改为调候用神【{t}】"))
    for h in verdict.get("hits", []):
        if h.get("net") != "逆":
            continue
        ref, t = h.get("ref"), h.get("target")
        if ref == "F" and t:
            r2 = SHENG[R]
            cands.append((r2, f"原处方克喜用【{t}】，取通关【{r2}】（{R}生{r2}生{t}）"))
    if F:
        cands.append((sheng_me(F[0]), f"改取生扶喜用者【{sheng_me(F[0])}】通关"))
        # 喜用本气本身也是合法候选：门4「R=F 或 R生F → 绿」即引擎自己承认的放行项，
        # 《子平真诠·论用神》「为我所喜，枭伤七煞，皆为吉神」——不把喜用列入候选，
        # 就会出现"adjudicate 判木为绿、redirect 却报无解"的自相矛盾
        # （2026-10-06 审计复检一个无解样本时发现，候选表补此一路）。
        for f in F:
            cands.append((f, f"改取喜用本气【{f}】"))
    seen, failed = set(), []
    for cand, why in cands:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        ok, bad = _redirect_filter_ok(cand, F, J, T0, t_active)
        if ok:
            return cand, why
        failed.append("【%s】%s" % (cand, bad))
    return "", ("原处方【%s】被否决，改方候选无一通过三重过滤（%s）：依《子平真诠·论用神》"
                "「如原局无通关之神，亦必运程弥其缺憾」，待岁运通关之地，不以喂忌之方充数"
                % (R, "；".join(failed) if failed else "无可用候选"))


if __name__ == "__main__":
    # 自测：用户例子 事体木、八字喜水（水生木）→ F生R → 中·泄气 → 平
    r = adjudicate("木", F=["水"], J=["金"], T0=None, month_wx="辰")
    print("木 R / 喜水:", r["net"], r["level"], r["decision"])
    for h in r["hits"]:
        print("  ", h["label"], h["semantic"], h["tip"])
    # 事体木、八字喜火（木生火）→ R生F → 顺·资生
    r2 = adjudicate("木", F=["火"], J=[], T0=None, month_wx="辰")
    print("木 R / 喜火:", r2["net"], r2["level"], r2["decision"], [h["label"] for h in r2["hits"]])
    # 忌神犯：R=金，忌神=金 → 红
    r3 = adjudicate("金", F=["水"], J=["金"], T0=None, month_wx="辰")
    print("金 R / 忌金:", r3["net"], r3["level"], r3["decision"])
    # 调候转急：寒命喜火，月令水（冬月属水）→ 调候转急；R=水 逆火 → 红
    r4 = adjudicate("水", F=["木"], J=[], T0=["火"], month_wx="水")
    print("水 R / 寒命喜火 冬月:", r4["net"], r4["level"], r4["decision"], "tiao_active=", r4["tiao_active"])
