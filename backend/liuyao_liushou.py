# -*- coding: utf-8 -*-
"""六爻「逐爻细看」——六神逐位断语（显示层）
================================================

## 它做什么

给每一爻配一份可核对的说法：**六神 ＋ 六亲 ＋ 纳甲 ＋ 世应 ＋ 动静 ＋ 空破旺衰 ＋ 角色**，
再按《卜筮正宗·六兽歌断》《六兽评论第七》《增删卜易·六神章》《黄金策·总断千金赋》
的组合规则给出断语，**每条断语都带书名与行号**。

## 它绝不做什么（这是本模块的边界，写在最前面）

1. **不进判定**：逐爻细看不参与红黄绿、不改处方五行、不改应期。理由是三书自己定的规矩——
   《卜筮正宗·六兽评论第七》："六亲本也，六兽末也""六兽但可推其情性形状，至于吉凶得失，
   当专以六亲生克为主"；《黄金策·总断千金赋》："虎兴而遇吉神，不害其为吉；龙动而逢凶曜，
   难掩其为凶。"《增删卜易·六神章》称六神为"附和之神"。
2. **不代拟**：三书没有专断的「兽×角色」组合（例如青龙临安静的闲爻），只列兽性与状态，
   并明确标注"三书未就此组合立专断"——不编一句像样的话填满版面。

## 数据来源与可核验

条文全部放在 `liuyao_liushou.json`，text 字段为三书原文摘录；`tests/test_liushou.py`
会把每条 text 拿去 `books/` 的原文里逐字比对，改一个字即失败。
"""
import json
from functools import lru_cache
from pathlib import Path

from wuxing_relation import sheng_me

_LIB = Path(__file__).parent / "liuyao_liushou.json"

# 角色取值（顺序即优先级：一个爻可能既是世又是用神，取更具体的那个做主张）
ROLE_ORDER = ("用神", "元神", "忌神", "仇神", "世", "应", "闲")


@lru_cache(maxsize=1)
def load_lib() -> dict:
    return json.loads(_LIB.read_text(encoding="utf-8"))


def principle() -> dict:
    """三书对六神的定性（边界声明），供页面与提示词引用。"""
    return load_lib()["principle"]


def _liuqin_wx_map(lines: list) -> dict:
    """六亲 → 五行（同一卦宫下每个六亲的五行固定，取任一爻即可）。"""
    m = {}
    for l in lines:
        if l.get("liuqin") and l.get("wuxing"):
            m.setdefault(l["liuqin"], l["wuxing"])
    return m


def _role_of(line: dict, remedy: dict, liuqin_wx: dict) -> str:
    """判定这一爻在本次问事里的角色（用神 > 元神 > 忌神 > 仇神 > 世 > 应 > 闲）。"""
    det = (remedy or {}).get("details", {})
    yong_pos = (det.get("用神爻") or {}).get("position")
    if yong_pos is not None and line.get("position") == yong_pos:
        return "用神"
    lq = line.get("liuqin")
    if lq and lq == (det.get("元神") or {}).get("六亲"):
        return "元神"
    jishen = det.get("忌神") or {}
    if lq and lq == jishen.get("六亲"):
        return "忌神"
    # 仇神＝生忌神者（《增删卜易·用神章》：生忌神者仇神）
    js_wx = jishen.get("五行")
    if lq and js_wx:
        chou_wx = sheng_me(js_wx)
        if liuqin_wx.get(lq) == chou_wx:
            return "仇神"
    if line.get("shi"):
        return "世"
    if line.get("ying"):
        return "应"
    return "闲"


def _cell(lib: dict, role: str, beast: str) -> dict:
    return ((lib.get("cells") or {}).get(role) or {}).get(beast) or {}


def _item(text: str, src: str, kind: str, plain: str = "") -> dict:
    return {"text": text, "src": src, "kind": kind, "plain": plain}


def per_line_readings(gua_data: dict, remedy: dict) -> list:
    """逐爻细看：返回六条（初爻→上爻），每条的断语都带出处。

    只做「既有判定的呈现 + 书上条文的匹配」，不新增任何吉凶规则。
    """
    lib = load_lib()
    lines = gua_data.get("lines") or []
    liuqin_wx = _liuqin_wx_map(lines)
    out = []
    for l in lines:
        beast = l.get("liushen") or ""
        b = (lib.get("beasts") or {}).get(beast) or {}
        role = _role_of(l, remedy, liuqin_wx)
        items = []
        # ① 兽性（必有，原句）
        if b:
            items.append(_item(b["quote"], b["src"], "兽性", b.get("plain", "")))
        # ② 角色断语（书有专断才有）
        main_cell = _cell(lib, role, beast)
        if main_cell:
            items.append(_item(main_cell["text"], main_cell["src"], role + "·" + beast,
                               main_cell.get("plain", "")))
        # ③ 世应另算一格：一个爻可能既是用神又是世（自占取世）
        if role != "世" and l.get("shi"):
            c = _cell(lib, "世", beast)
            if c:
                items.append(_item(c["text"], c["src"], "世·" + beast, c.get("plain", "")))
        if role != "应" and l.get("ying"):
            c = _cell(lib, "应", beast)
            if c:
                items.append(_item(c["text"], c["src"], "应·" + beast, c.get("plain", "")))
        # ④ 状态修饰：动/静、空/破
        mods = lib.get("modifiers") or {}
        if l.get("moving") and "动" in mods:
            m = mods["动"]
            items.append(_item(m["text"], m["src"], "动", m.get("plain", "")))
        elif not l.get("moving") and role in ("用神", "元神", "忌神", "仇神") and "静" in mods:
            m = mods["静"]
            items.append(_item(m["text"], m["src"], "静", m.get("plain", "")))
        if l.get("xunkong") and "空" in mods:
            m = mods["空"]
            items.append(_item(m["text"], m["src"], "旬空", m.get("plain", "")))
        if l.get("yuepo") and "破" in mods:
            m = mods["破"]
            items.append(_item(m["text"], m["src"], "月破", m.get("plain", "")))

        out.append({
            "position": l.get("position"),
            "name": l.get("name", ""),
            "六神": beast,
            "六亲": l.get("liuqin", ""),
            "干支": (l.get("gan", "") or "") + (l.get("zhi", "") or ""),
            "五行": l.get("wuxing", ""),
            "卦位": "世" if l.get("shi") else ("应" if l.get("ying") else ""),
            "角色": role,
            "动静": "动" if l.get("moving") else "静",
            "旬空": bool(l.get("xunkong")),
            "月破": bool(l.get("yuepo")),
            "兽性": b.get("nature", ""),
            "断语": items,
            # 只有兽性、没有角色专断时为 False —— 页面据此显示"三书无专断，不代拟"
            "有专断": len(items) > 1,
            "无专断说明": (lib.get("roles_by_beast_absent_note", "")
                        if len(items) <= 1 else ""),
        })
    return out


def prompt_block(readings: list) -> str:
    """把逐爻细看编成给 AI 的确定性材料（它只许串人话，不许新增断语）。"""
    if not readings:
        return ""
    p = principle()
    rows = []
    for r in readings:
        tags = [t for t in (r["角色"], r["卦位"], r["动静"]) if t]
        if r["旬空"]:
            tags.append("旬空")
        if r["月破"]:
            tags.append("月破")
        say = "；".join("%s（%s）" % (i["plain"] or i["text"], i["src"]) for i in r["断语"][1:])
        rows.append("第%d爻 %s %s%s %s%s｜%s" % (
            r["position"], r["六神"], r["六亲"], r["干支"],
            "·" + "/".join(tags) if tags else "",
            "｜" + "；".join(i["text"] for i in r["断语"]) if r["断语"] else "",
            (say if r["有专断"] else (r["无专断说明"] or "只列兽性与状态")),
        ))
    return (
        "【逐爻细看（确定性材料·六神断语表）】\n"
        "用法：以下每爻的六神、六亲、干支、角色、状态与断语均已由代码查表给出，"
        "**你只可据此串成人话，不得新增断语、不得改换出处、不得拿六神改任何吉凶结论**。\n"
        "定性与边界（三书原话）：%s\n"
        "%s\n"
        "凡标注「三书无专断」的爻，只描述兽性与状态，不要替它编断语。"
        % ("；".join("「%s」——%s" % (q["text"], q["src"]) for q in p["quotes"][:3]),
           "\n".join(rows))
    )


if __name__ == "__main__":
    from liuyao_engine import build_paipan
    g = build_paipan([{"x": 1.1 * i, "y": 2.2, "duration": 300, "speed": 0.5} for i in range(1, 7)])
    from liuyao_remedy import liuyao_remedy
    r = liuyao_remedy(g, "这次合作能不能谈成")
    for row in per_line_readings(g, r):
        print("第%d爻 %s %s%s %s 角色=%s 有专断=%s"
              % (row["position"], row["六神"], row["六亲"], row["干支"], row["动静"],
                 row["角色"], row["有专断"]))
