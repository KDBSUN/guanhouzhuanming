# -*- coding: utf-8 -*-
"""
五行补益建议生成器
====================
依据 backend/wuxing_xiang.json（五行类象库，以《五行大义》为主，辅以《黄帝内经》《梅花易数》等）。

输入：待补五行列表（如 ["木", "水"]）。
输出：按维度（方位/颜色/数字/物件/饮食/职业/健康/卦象/屋宅/四时干支）的结构化建议，
供"补五行建议"输出层与前端直接取用。

用法：
    from wuxing_suggest import suggest_wuxing, suggest_text
    data = suggest_wuxing(["木", "水"])     # 结构化
    md   = suggest_text(["木", "水"])       # 文案（Markdown）
"""
import json
from functools import lru_cache
from pathlib import Path

_LIB_PATH = Path(__file__).parent / "wuxing_xiang.json"

# 河图成数（"三八为木"式）
# （「数字」一维 2026-09-24 曾按四条检验 F2 删除，站长 2026-09-25 裁定恢复原样；
#   五行配数出处《五行大义·论五行及生成数》，详见《学术板块四条检验》F2 记录。）
HE_TU = {"木": "三八", "火": "二七", "土": "五十", "金": "四九", "水": "一六"}


@lru_cache(maxsize=1)
def load_lib() -> dict:
    """加载五行类象库（缓存）"""
    return json.loads(_LIB_PATH.read_text(encoding="utf-8"))


def _bagua_aggregate(guas: list, lib: dict) -> dict:
    """聚合某五行所辖八卦的类象（静物/屋宅/饮食，去重保序）"""
    static = []
    house = []
    food = []
    for g in guas:
        b = lib.get("bagua", {}).get(g, {})
        for it in b.get("静物", []):
            if it not in static:
                static.append(it)
        h = b.get("屋宅")
        if h and h not in house:
            house.append(h)
        for it in b.get("饮食", []):
            if it not in food:
                food.append(it)
    return {"静物": static, "屋宅": house, "饮食": food}


def _field_src(w: dict, keys) -> str:
    """多字段合并去重出处"""
    srcs = []
    for k in keys:
        s = (w.get(k) or {}).get("src")
        if s and s not in srcs:
            srcs.append(s)
    return "、".join(srcs) if srcs else "—"


def _bagua_src(guas: list, lib: dict) -> str:
    srcs = []
    for g in guas:
        s = (lib.get("bagua", {}).get(g) or {}).get("src")
        if s and s not in srcs:
            srcs.append(s)
    return "、".join(srcs) if srcs else "—"


def _merge_src(*items: str) -> str:
    srcs = []
    for s in items:
        for part in s.split("、"):
            if part and part != "—" and part not in srcs:
                srcs.append(part)
    return "、".join(srcs) if srcs else "—"


def _texture_block(wx: str, flavor: dict = None) -> dict:
    """质地分档（R1）+ 味分档（丙·4）：把质地层精度输送到建议物品——"补哪个味的X"。

    体象定药性（📜滴天髓·论天干），物件归类为工程映射（🔢）；约束条文见于各论（📜）。

    ## 「两味分列」与「味分档」是两件事，别混

    - `两味分列`：只讲**取味**（这一味该往燥润寒暖哪个方向取），条目来自 FLAVOR_TABLE。
    - `味分档`：讲**器物**（这一味具体是什么东西），条目来自 STEM_OBJECTS，
      并按十干列／八卦列**并列**给出，各有出处、互不合并（R6：跨载体不得互推）。
      丙·4 的由来：原先"补金"只给一张五行级物件清单，庚（斧钺）与辛（首饰）混作一团，
      而《滴天髓》把两章标题直接写成"庚金：斧钺之金""辛金：首饰之金"——
      是我们在建议层把书上分明的两味揉成了一味。
    """
    from wuxing_quality import FLAVOR_TABLE, STEMS_TEXTURE, flavor_split
    t = FLAVOR_TABLE.get(wx)
    if not t:
        return {}
    flavor = flavor or {}
    stems = []
    for gan, desc in t["stems"].items():
        st = STEMS_TEXTURE.get(gan, {})
        stems.append({
            "干": gan,
            "标签": st.get("tags", ""),
            "取味": desc,
            "体象": st.get("tixiang", ""),
            "推荐": bool(flavor.get("gan") == gan),
        })
    split = flavor_split(wx, load_lib().get("bagua", {}))
    return {
        "两味分列": stems,
        "味分档": split,
        "本味推荐": ("取【%s】味：%s" % (flavor.get("gan"), flavor.get("note", ""))
                     if flavor.get("gan") else flavor.get("note", "")),
        "推荐依据": flavor.get("basis", ""),
        "约束": t["constraint"],
        "src": t["src"] + (" + " + flavor.get("src", "") if flavor.get("src") else ""),
    }


def suggest_wuxing(wuxing_list, flavors: dict = None) -> dict:
    """待补五行 → 结构化建议。wuxing_list 为 ['木','火','土','金','水'] 的子集。

    flavors（可选）：{五行: pick_flavor 结果}——来自卦侧干支/起卦时令的质地取向，
    用于把"补哪个味的X"落到建议里（R1：精度输送到物品层）。
    """
    lib = load_lib()
    flavors = flavors or {}
    out = {}
    for wx in wuxing_list:
        w = lib.get("wuxing", {}).get(wx)
        if not w:
            continue
        guas = w.get("八卦", {}).get("v", [])
        agg = _bagua_aggregate(guas, lib)
        out[wx] = {
            "方位": w.get("方位", {}).get("v", []),
            "颜色": w.get("五色", {}).get("v", []) + w.get("间色", {}).get("v", []),
            "数字": {
                "生数": w.get("数", {}).get("生"),
                "成数": w.get("数", {}).get("成"),
                "河图": HE_TU.get(wx, ""),
            },
            "物件": {
                "当旺": w.get("物象", {}).get("v", {}).get("王", []),
                "次旺": w.get("物象", {}).get("v", {}).get("相", []),
                "静物": agg["静物"],
            },
            "饮食": {
                "五味": w.get("五味", {}).get("v"),
                "五谷": w.get("五谷", {}).get("v"),
                "五果": w.get("五果", {}).get("v"),
                "五菜": w.get("五菜", {}).get("v"),
                "五畜": w.get("五畜", {}).get("v"),
                "宜食": agg["饮食"],
            },
            "职业": w.get("职业方向", {}).get("v", []),
            "健康": {
                "五脏": w.get("五脏", {}).get("v"),
                "六腑": w.get("六腑", {}).get("v"),
                "开窍": w.get("开窍", {}).get("v"),
                "情志": w.get("五志", {}).get("v"),
            },
            "卦象": guas,
            "屋宅": agg["屋宅"],
            "四时": w.get("四时", {}).get("v"),
            "天干": w.get("天干", {}).get("v"),
            "地支": w.get("地支", {}).get("v"),
            # 质地分档（R1）：补哪个味的X（阴阳/燥湿/寒暖取向）
            "质地": _texture_block(wx, flavors.get(wx)),
            # 各维度典籍出处（可回溯）
            "src": {
                "方位": _field_src(w, ["方位"]),
                "颜色": _field_src(w, ["五色", "间色"]),
                "数字": _field_src(w, ["数"]),
                "物件": _merge_src(_field_src(w, ["物象"]), _bagua_src(guas, lib)),
                "饮食": _merge_src(_field_src(w, ["五味", "五谷", "五果", "五菜", "五畜"]),
                                   _bagua_src(guas, lib)),
                "职业": _field_src(w, ["职业方向"]),
                "健康": _field_src(w, ["五脏", "六腑", "开窍", "五志"]),
                "卦象": _bagua_src(guas, lib),
                "屋宅": _bagua_src(guas, lib),
                "四时": _field_src(w, ["四时"]),
                "干支": _field_src(w, ["天干", "地支"]),
                "质地": _texture_block(wx, flavors.get(wx)).get("src", ""),
            },
        }
    return out


def _join(items):
    return "、".join(str(x) for x in items) if items else "—"


def suggest_text(wuxing_list) -> str:
    """待补五行 → 一段可读建议文案（Markdown，可直接作为 AI prompt 上下文或展示）。"""
    data = suggest_wuxing(wuxing_list)
    lines = []
    for wx, d in data.items():
        lines.append(f"## 补【{wx}】")
        lines.append(f"- 方位：{_join(d['方位'])}")
        lines.append(f"- 颜色：{_join(d['颜色'])}")
        num = d["数字"]
        lines.append(f"- 数字：{num['生数']}、{num['成数']}（河图{num['河图']}）")
        lines.append(f"- 物件·当旺（《五行大义》物象·王）：{_join(d['物件']['当旺'])}")
        # 五行级静物＝乾兑合参。**必须标明层级**：下面味分档已经把乾/兑拆开了，
        # 这里再摆一张合参清单，不标层级就会被读成"和上面那两行打架"。
        lines.append(f"- 物件·静物（五行级，乾兑合参，仅供概览）：{_join(d['物件']['静物'])}")
        # 味分档（丙·4）：十干列与八卦列**并列**，谁也不给谁作证（R6：跨载体不得互推）。
        # 给 AI 时也必须保持两列分开——合并成一张清单，等于替书上做它没做过的对应。
        fs = (d.get("质地") or {}).get("味分档") or {}
        if fs.get("阳") or fs.get("阴"):
            for pos in ("阳", "阴"):
                c = fs.get(pos)
                if not c:
                    continue
                seg = "%s味【%s·%s】%s" % (pos, c["干"], c["名"], _join(c["物"]))
                lines.append("- " + seg)
                if c.get("srcs"):
                    lines.append("  · 出处：" + "；".join(c["srcs"]))
                if c.get("note"):
                    lines.append("  · " + c["note"])
                if c.get("卦"):
                    lines.append("  · 同类可参（卦侧·%s，另有出处，不与上行合并）：静物 %s" % (
                        c["卦"], _join(c.get("卦物", []))))
                    if c.get("卦srcs"):
                        lines.append("    · 出处：" + "；".join(c["卦srcs"]))
            if fs.get("note"):
                lines.append("  · " + fs["note"])
            if fs.get("五行级"):
                lines.append("  · " + fs["五行级"])
        yi = d["饮食"]
        lines.append(
            f"- 饮食：味{yi['五味']}；谷 {yi['五谷']}、果 {yi['五果']}、菜 {yi['五菜']}、肉 {yi['五畜']}"
        )
        lines.append(f"- 职业方向：{_join(d['职业'])}")
        h = d["健康"]
        lines.append(f"- 养生：藏{h['五脏']}、腑{h['六腑']}、开窍{h['开窍']}、情志{h['情志']}")
        lines.append(f"- 卦象：{_join(d['卦象'])}；四时 {d['四时']}；干支 {_join(d['天干'])}（{_join(d['地支'])}）")
        if d["屋宅"]:
            lines.append(f"- 屋宅朝向：{_join(d['屋宅'])}")
        srcs = sorted({s for s in d.get("src", {}).values() if s != "—"})
        if srcs:
            lines.append(f"- 典籍出处：{'；'.join(srcs)}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(suggest_text(["木", "水"]))
