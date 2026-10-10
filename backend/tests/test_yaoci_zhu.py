# -*- coding: utf-8 -*-
"""爻辞【注释】的回归锁
======================
三条红线：
1. **逐字回源**：每条注释都要能在书里逐字找到，且它所属的那一节必须是【注释】——
   不许出现"看着像注释、其实是译文或评析"的东西；
2. **不许缺、不许编**：三百八十四爻一条不少；查不到的必须返回 None 而不是现编；
3. **只给注释不给译文**：这是产品口径——《梅花易数》用爻辞是拈字取象（鸡悲鸣占取"血去"），
   整句白话会把意思压平。所以这一层不得混入【译文】。
"""
import json
import re
from pathlib import Path

import engine
import main
import yaoci_zhu
from tools import build_yaoci_zhu as B  # 提取工具；测试直接复用它读同一本书

BACKEND = Path(__file__).resolve().parents[1]
LIB = BACKEND / "yaoci_zhu.json"
DATA = BACKEND.parent / "data" / "meihua_data.json"


def _lib() -> dict:
    assert LIB.exists(), "缺少 yaoci_zhu.json（跑 backend/tools/build_yaoci_zhu.py 生成）"
    return json.loads(LIB.read_text(encoding="utf-8"))


def _meihua() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


# ---------- 1. 逐字回源 ----------

def test_book_file_present():
    """回源测试只有在书确实存在时才有意义——书不在了就该红，而不是默默放过。"""
    assert (B.REPO / B.BOOK_FILE).exists(), f"找不到书：{B.BOOK_FILE}"


def test_every_note_is_verbatim_in_the_book():
    book = B.norm(B.read_book())
    miss = []
    for key, g in _lib()["by_key"].items():
        for pos, y in g["yao"].items():
            if B.norm(y["raw"]) not in book:
                miss.append(f"{g['name']}第{pos}爻")
    assert not miss, f"以下注释在书里找不到原文：{miss[:8]}"


def test_every_note_belongs_to_a_comment_section():
    """光"能在书里找到"不够：还要确认它归属的那一节是【注释】，不是【译文】/【评析】。"""
    lines = B.read_book().split("\n")
    flat = [B.norm(l) for l in lines]
    bad = []
    for key, g in _lib()["by_key"].items():
        for pos, y in g["yao"].items():
            first = B.norm(y["raw"].split("\n")[0])
            idx = next((i for i, f in enumerate(flat) if first and first in f), None)
            if idx is None:
                bad.append(f"{g['name']}第{pos}爻：找不到起始行")
                continue
            head = next((lines[j].strip() for j in range(idx, -1, -1)
                         if B.HEAD.match(lines[j].strip())), "")
            m = B.HEAD.match(head)
            if not (m and m.group(1) == "注释"):
                bad.append(f"{g['name']}第{pos}爻：所属小节是「{head}」")
    assert not bad, f"注释归属不对：{bad[:8]}"


# ---------- 2. 不许缺、不许编 ----------

def test_all_384_yao_have_notes():
    by = _meihua()["hexagrams"]["by_key"]
    lib = _lib()["by_key"]
    missing = []
    for key, g in by.items():
        for pos in range(1, 7):
            n = lib.get(key, {}).get("yao", {}).get(str(pos))
            if not n or not n.get("notes"):
                missing.append(f"{g['name']}第{pos}爻")
    assert not missing, f"缺注释：{missing[:8]}"
    assert sum(len(g["yao"]) for g in lib.values()) == 384


def test_jing_line_matches_our_yaoci():
    """取到的经文行必须就是这一爻的爻辞（容忍电子本 OCR 差字，但不超过记录值）。"""
    by = _meihua()["hexagrams"]["by_key"]
    bad = []
    for key, g in _lib()["by_key"].items():
        for pos, y in g["yao"].items():
            yc = by[key]["yaoci"][int(pos) - 1]
            ti = B.YAO_TI.match(yc).group(1)
            core = B.norm(y["jing"])[len(ti):]
            body = B.norm(B.YAO_TI.sub("", yc))
            if abs(len(core) - len(body)) > 4:
                bad.append(f"{g['name']}第{pos}爻：经文行长度对不上")
            if not any(core[i:i + 2] in body or body[i:i + 2] in core
                       for i in range(max(1, len(body) - 1))):
                bad.append(f"{g['name']}第{pos}爻：经文行与爻辞不是同一句")
    assert not bad, f"经文行对不上：{bad[:8]}"


def test_lookup_returns_none_instead_of_inventing():
    """查不到就得是 None——页面和提示词据此闭嘴，不许现编字义。"""
    assert yaoci_zhu.notes_for(1, 1, 1)["notes"]
    assert yaoci_zhu.notes_for(99, 99, 1) is None
    assert yaoci_zhu.notes_for(1, 1, 9) is None


# ---------- 3. 只给注释，不给译文 ----------

def test_no_translation_leaked_in():
    """译文的口径特征：以"《象传》说"开头，或整段是白话长句而无训诂标记。

    这里用可判定的写法：注释原文里必须出现"字词＋："式的条目（word 非空）至少一条；
    且不得出现该书【译文】的固定开头。整句译文不可能带着被注的字词。
    """
    lib = _lib()
    bad = []
    for key, g in lib["by_key"].items():
        for pos, y in g["yao"].items():
            if not any(n.get("word") for n in y["notes"]):
                bad.append(f"{g['name']}第{pos}爻：没有逐词条目（疑似整段译文）")
            if "《象传》说" in y["raw"]:
                bad.append(f"{g['name']}第{pos}爻：混入了译文")
    assert not bad, f"疑似混入译文：{bad[:8]}"


# ---------- 4. 接到接口与提示词 ----------

def test_engine_exposes_notes_on_moving_yao():
    r = engine.divine_manual(3, 4, 3)          # 上离下震（雷火丰），三爻动
    z = r["moving_yao"].get("yaoci_zhu")
    assert z and z["notes"], "动爻应带注释"
    assert "中华书局" in z["src"]
    assert z["notes"][0]["text"]


def test_prompt_carries_notes_with_provenance():
    r = engine.divine_manual(3, 4, 3)
    p = main.build_user_prompt(r, "问事")
    assert "动爻爻辞注释" in p
    assert "中华书局" in p
    assert r["moving_yao"]["yaoci_zhu"]["notes"][0]["text"] in p
    assert "不得另编字义" in p
