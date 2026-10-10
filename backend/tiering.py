# -*- coding: utf-8 -*-
"""
S/M/L 档位判定 与 三档输出契约（累积式）
=============================================
档位语义（累积披露）：档位 = 输出上限，划到哪档就输出到哪档——
  S 档 → 只输出 S 段（紧急·事体窗）
  M 档 → 输出 S+M 两段
  L 档 → 输出 S+M+L 三段
默认档为 S（前端切换器默认落 S；自动分类仅作提示，让位于手动）。
建议维度同样按累积裁剪：M 含 S 的全部维度，L 含 S+M 的全部维度。

权重原则（固定）：短事重卦、长事重命、中事各半。
"""
from typing import Union

TIER = ("S", "M", "L")

# 各档自身维度（累积后为该档可用维度全集）
# 落地物分配（用户 2026-09-14 定）：S＝即时可做（方位/颜色/数字/随身物件）；
# M＝空间与职业（行业职能/屋宅布局）；L＝长期调养（饮食/作息/健康/情志）。
# （「数字」一维 2026-09-24 曾按四条检验 F2 删除，站长 2026-09-25 裁定恢复。）
# "质地"（补哪个味的X：庚辛/湿燥土分列）随"物件"走——物件怎么挑，质地说了算（R1）。
_TIER_DIMS = {
    "S": ["方位", "颜色", "数字", "物件", "质地"],
    "M": ["职业", "屋宅"],
    "L": ["饮食", "作息", "健康", "情志"],
}

# 自动映射关键词（按优先级：S → M → L → 歧义兜底；仅作默认提示）
S_KEYWORDS = ["出行", "出门", "远行", "失物", "丢失", "找回", "找东西", "近病", "感冒", "发烧",
              "天气", "今日", "今天", "明天", "应期", "什么时候", "何时", "急", "马上", "立刻",
              "即日", "本周", "这几天", "赴约", "赶", "迟到", "误"]
M_KEYWORDS = ["求职", "找工作", "跳槽", "面试", "交易", "搬迁", "搬家", "项目", "启动", "开业",
              "合作", "签约", "谈", "谈判", "入职", "离职", "买房", "购车", "贷款", "投资",
              "开店", "创业", "做生意", "经营", "开公司", "投标", "竞标", "调岗", "这季度",
              "本月", "近几个月"]
L_KEYWORDS = ["姻缘", "婚姻", "婚", "嫁娶", "久病", "慢性", "长期", "总运势", "一生", "命运",
              "起名", "择居", "定居", "养生", "事业方向", "方向", "规划", "近几年", "今后",
              "未来几年", "孩子", "子女", "学业", "长远", "终身"]
AMBIG_KEYWORDS = ["帮我看看", "怎么样", "看看", "如何", "好吗", "行吗", "测测", "算算", "占",
                  "帮我算", "看一下", "能不能"]


def classify_tier(question: str) -> Union[str, None]:
    """
    返回默认档 "S"/"M"/"L"；歧义或无法判断时返回 None。
    自动分类仅产生"默认提示"，永远让位于切换器手动档位。
    """
    q = question or ""
    for kw in S_KEYWORDS:
        if kw in q:
            return "S"
    for kw in M_KEYWORDS:
        if kw in q:
            return "M"
    for kw in L_KEYWORDS:
        if kw in q:
            return "L"
    # 歧义兜底：命中歧义词 → None（不猜）
    for kw in AMBIG_KEYWORDS:
        if kw in q:
            return None
    # 空/无关键词：也按歧义处理（不猜）
    return None


def cumulative_tiers(tier: str) -> list:
    """档位 → 累积包含的各段（S→[S]；M→[S,M]；L→[S,M,L]）"""
    order = ["S", "M", "L"]
    t = tier if tier in order else "S"
    return order[: order.index(t) + 1]


def suggest_dims(tier: str) -> list:
    """档位 → 累积后的补五行建议维度（补五行建议裁剪用）"""
    dims = []
    for t in cumulative_tiers(tier):
        for d in _TIER_DIMS[t]:
            if d not in dims:
                dims.append(d)
    return dims


def tier_contract(tier: str) -> dict:
    """三档输出契约（内容 / 字数 / 语气 / 命局权重 / 边界声明 / 建议维度——均按累积语义）。

    分两部分：第一部分"解卦"三档完全一样（卦名、卦辞、爻辞、体用或用神，不受档位影响）；
    档位只管第二部分"行动建议"的层数与落地物——
      S＝这几天怎么做（方位、颜色、数字、随身物件）
      M＝再加这季度怎么调（行业职能方向、屋宅与办公空间布局）
      L＝再加这几年怎么养（饮食五味、作息起居、健康脏腑、情志调养）
    """
    base = {
        "S": {
            "label": "紧急·事体窗",
            "question": "这几天怎么做",
            "content": ["应期之日（**只能逐字取自**提示中【应期】所列日期，不得出现列外日期）", "方位（宜往/宜坐）",
                        "颜色（宜穿/宜用）", "数字", "随身物件", "3–5 条指令"],
            "length": "第二部分约 300 字，指令式，日期另列表格",
            "tone": "指令式，每条标依据",
            "weight": "卦与月令为主，命局仅安全门",
            "disclaimer": "",
        },
        "M": {
            "label": "中期·人事",
            "question": "这季度怎么调",
            "content": ["行业职能方向（做什么、避开什么）",
                        "屋宅与办公空间布局（哪个方位、放什么器物、材质与朝向）",
                        "1–3 个可启动动作"],
            "length": "第二部分约 700 字（紧急层 ≈300 + 中期层 ≈400）",
            "tone": "中期层结论先行，依据随后（依据不得省略）",
            "weight": "命局与卦各半",
            "disclaimer": "非职业投资建议",
        },
        "L": {
            "label": "长期·底盘",
            "question": "这几年怎么养",
            "content": ["饮食五味（宜食/少食，按处方五行）", "作息起居与四时调养",
                        "健康与脏腑倾向（只讲调理方向，不给处方）", "情志调养",
                        "典籍出处（每条带一句原理）"],
            "length": "第二部分约 1200 字（紧急 ≈300 + 中期 ≈400 + 长期 ≈500）",
            "tone": "长期层说明式，温和，每条带一句原理",
            "weight": "命局为主，卦为触发",
            "disclaimer": "非医疗建议声明",
        },
    }.get(tier, {})
    if base:
        base = dict(base)
        base["suggest_dims"] = suggest_dims(tier)
        base["sections"] = cumulative_tiers(tier)   # 累积包含的段
    return base


def resolve_tier(question: str, manual_override: Union[str, None] = None) -> dict:
    """
    最终档位：切换器手动档位优先；无手动时按自动分类，歧义回落 S。
    返回 {tier, source: manual|auto|ambig, contract, expanded_default}
    """
    if manual_override in TIER:
        tier = manual_override
        source = "manual"
    else:
        auto = classify_tier(question)
        if auto in TIER:
            tier = auto
            source = "auto"
        else:
            tier = "S"                 # 歧义：默认 S
            source = "ambig"
    return {
        "tier": tier,
        "source": source,
        "auto_tier": classify_tier(question),
        "contract": tier_contract(tier),
        "expanded_default": tier,
    }


def tier_directive(question: str, manual_override: Union[str, None] = None) -> str:
    """
    把档位契约转成一段可直接注入 AI 断卦 prompt 的指令（累积式输出）。
    手动档位恒定生效；无手动时自动分类，歧义按全档输出。

    【2026-09-12 改框架】S/M/L 只作用于**行动建议**的深浅，不再作用于整个解卦：
      第一部分·解卦（卦名之义、卦辞、象曰、动爻爻辞、体用或用神旺衰生克）
        —— 不受档位影响，始终完整输出；
      第二部分·行动建议 —— 档位决定给到哪一层：
        S = 只给【紧急·事体窗】（这几天怎么做）
        M = +【中期·人事】（这季度怎么调）
        L = +【长期·底盘】（这几年怎么养）
    依据标注（据：卦名/卦辞/爻辞/用神）在两部分里都不可省。
    """
    info = resolve_tier(question, manual_override)
    frame = (
        "【输出框架·两部分】第一部分·解卦：把卦讲透（卦名之义、卦辞、象曰、动爻爻辞，"
        "以及体用生克或用神旺衰），**不受档位影响，始终完整细致地输出**（三档一模一样）；"
        "第二部分·行动建议：**档位只管这里**——档位决定第二部分写几层、每层写哪些落地物，"
        "所以三档的长度差别应当一眼可见（S 短、M 中、L 长）。"
        "两部分中每条判断与每条建议都要标明依据（据：卦名/卦辞/爻辞/体用/用神），不得只给结论不引卦。"
    )
    if info["source"] == "ambig":
        return (
            frame + "\n"
            "【行动建议档位：全档（S+M+L 三层，约 1200 字）】此问题表述有歧义，不擅自假设深度，第二部分按三层全给："
            "①「### 紧急·事体窗 → 这几天怎么做」（约 300 字指令式）：应期之日（**只能逐字取自**【应期】所列，不得出现列外日期）、方位（宜往/宜坐）、"
            "颜色（宜穿/宜用）、数字、随身物件、3–5 条指令；"
            "②「### 中期·人事 → 这季度怎么调」（约 400 字）：行业职能方向、屋宅与办公空间布局（方位、器物、材质、朝向）；"
            "③「### 长期·底盘 → 这几年怎么养」（约 500 字说明式）：饮食五味、作息起居与四时调养、健康与脏腑倾向（只讲调理方向）、"
            "情志调养，每条带一句原理与出处。短事重卦、中事各半、长事重命。"
            f"须附声明：{tier_contract('M')['disclaimer']}；{tier_contract('L')['disclaimer']}。"
        )
    tier = info["tier"]
    if tier == "S":
        c = tier_contract("S")
        return (
            frame + "\n"
            f"【行动建议档位：S（只写一层，约 300 字）】第二部分只写「### 紧急·事体窗 → {c['question']}」这一层，"
            f"落地物只给：{'、'.join(c['content'])}。字数：{c['length']}。语气：{c['tone']}。"
            f"命局与卦的参考权重：{c['weight']}。"
            "**不要写行业职能、屋宅布局、饮食、作息、健康、情志这类 M/L 档内容**——S 档写了这些就算越档，"
            "会与 M/L 档重复、看不出差别。"
        )
    if tier == "M":
        cs, cm = tier_contract("S"), tier_contract("M")
        return (
            frame + "\n"
            f"【行动建议档位：M（写两层，约 700 字）】第二部分写两层："
            f"①「### 紧急·事体窗 → {cs['question']}」（约 300 字）：{'、'.join(cs['content'])}；"
            f"②「### 中期·人事 → {cm['question']}」（约 400 字，结论先行、依据随后）：{'、'.join(cm['content'])}。"
            f"命局与卦的参考权重各半。须附声明：{cm['disclaimer']}。"
            "**不要写饮食、作息、健康、情志这类 L 档内容**（留给 L 档，否则两档看不出差别）。"
        )
    cl, cm, cs = tier_contract("L"), tier_contract("M"), tier_contract("S")
    return (
        frame + "\n"
        f"【行动建议档位：L（写三层，约 1200 字）】第二部分写三层："
        f"①「### 紧急·事体窗 → {cs['question']}」（约 300 字）：{'、'.join(cs['content'])}；"
        f"②「### 中期·人事 → {cm['question']}」（约 400 字，结论先行）：{'、'.join(cm['content'])}，"
        f"须附声明：{cm['disclaimer']}；"
        f"③「### 长期·底盘 → {cl['question']}」（约 500 字，说明式温和、每条带一句原理）：{'、'.join(cl['content'])}，"
        f"命局与卦的参考权重：{cl['weight']}，须附声明：{cl['disclaimer']}。"
    )


if __name__ == "__main__":
    for q in ["明天出门顺利吗", "这次跳槽去新公司好吗", "我们的姻缘长久吗", "帮我看看", "我想创业开个店"]:
        r = resolve_tier(q)
        print(f"[{q}] -> {r['tier']} ({r['source']}) 段: {r['contract'].get('sections')} | 维度: {r['contract']['suggest_dims']}")
    for t in ("S", "M", "L"):
        print(f"--- 手动 {t} 档指令 ---")
        print(tier_directive("帮我看看", t))
