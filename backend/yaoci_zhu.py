# -*- coding: utf-8 -*-
"""爻辞【注释】查询
==================
数据由 tools/build_yaoci_zhu.py 从《周易》（杨天才、张善文 译注，中华书局·
全本全注全译丛书）的【注释】逐条抽出，落在 backend/yaoci_zhu.json。

为什么要单独立一层（而不是塞进 data/meihua_data.json）：
    1. 那份是六十四卦的**卦象本体**资料（卦名/卦辞/大象/爻辞），来源固定、长期不动；
       注释是**另一种来源**（现代译注本），出处不同就该分开放，免得日后分不清
       哪一句是卦书原本、哪一句是译注本的训释；
    2. 只有爻辞注释是零散取用的（一次只用一条动爻），单独一个小文件加载更省事。

【这一层只做什么】
    提供"某卦某爻的注释条目"给接口和提示词。
    **只给注释，不给译文**——《梅花易数》把爻辞当象的语言用（鸡悲鸣占只拈"血去"，
    《占物类例》逐句往物象上推），整句白话译文会把意思压平，正好妨碍拈字。
    逐词注释则告诉你每个字在讲什么象，那正是要拈的东西。
"""
import json
from functools import lru_cache
from pathlib import Path

_LIB = Path(__file__).resolve().parent / "yaoci_zhu.json"


@lru_cache(maxsize=1)
def _doc() -> dict:
    if not _LIB.exists():
        return {}
    return json.loads(_LIB.read_text(encoding="utf-8"))


def src_label() -> str:
    """出处标签：给页面和提示词共用，避免两处各写一个书名。"""
    src = (_doc() or {}).get("src") or {}
    return f"{src.get('book', '')}·{src.get('part', '')}".strip("·")


def notes_for(upper: int, lower: int, position: int) -> dict | None:
    """取某卦动爻的注释。

    返回 {"jing": 译注本经文行, "src": 出处, "notes": [{"word", "text"}, ...]}；
    没有数据就返回 None（页面与提示词都必须容忍这条缺失，不许现编）。
    """
    g = ((_doc() or {}).get("by_key") or {}).get(f"{int(upper)},{int(lower)}")
    if not g:
        return None
    y = (g.get("yao") or {}).get(str(int(position)))
    if not y or not y.get("notes"):
        return None
    return {"jing": y.get("jing", ""), "src": src_label(), "notes": y["notes"]}


def prompt_lines(z: dict | None) -> list:
    """把注释抄成给 AI 的提示行（入参就是 engine 挂在动爻上的那份 yaoci_zhu）。

    钉死三件事：照此解释、不得改字、不得另编字义；
    并明说**不要整句译成白话代替拈字**——爻辞是象的语言，
    占例里是拈"血去"这种字来点睛的（《梅花易数》鸡悲鸣占）。
    """
    if not z or not z.get("notes"):
        return []
    out = [f"- 动爻爻辞注释（{z.get('src', '')}，逐词训诂；照此解释，不得改写、"
           f"不得另编字义，也不得整句译成白话代替拈字）："]
    for n in z["notes"]:
        w = f"{n['word']}：" if n.get("word") else ""
        out.append(f"  {w}{n['text']}")
    return out


def prompt_lines_for(upper: int, lower: int, position: int) -> list:
    """按卦与爻位取注释再抄成提示行（不方便拿到 engine 结果时用）。"""
    return prompt_lines(notes_for(upper, lower, position))
