# -*- coding: utf-8 -*-
"""
六爻纳甲排盘书例回归（原本是 backend/test_liuyao.py 的手工脚本，97 项断言从未被 pytest 收集）
============================================================
为什么搬进来：那个脚本自带 `check()` 计数与 `sys.exit(1)`，只能 `python test_liuyao.py` 手跑，
于是 `pytest tests/` 永远看不到它——**"以为有覆盖其实没跑"是比没有测试更危险的状态**。
断言与书例文字一字未改，只改成 pytest 的形式（失败时能直接看到是哪一项、差多少）。

书例取自《增删卜易》：装卦（八宫/纳甲/六亲/世应/六神/变爻）是硬规则，逐项对书，
错了就是引擎错——这类"有明确书证、可逐字对照"的用例是排盘层的最高价值测试。
"""
import json
from datetime import datetime, timedelta

import pytest

from lunar_python import Solar

from liuyao_engine import (
    _build_paipan_from_raw, seed_from_params, coins_from_seed,
    PALACE_LOOKUP, build_paipan,
)


def raw(yin, moving=False):
    """构造一爻：yin=True 为阳（三背），否则为阴。"""
    return {"yin_yang": yin, "type": "老阳" if yin else "老阴", "moving": moving,
            "coins": [1, 1, 1] if yin else [0, 0, 0]}


def find_dt(day_ganzhi: str) -> datetime:
    """向前搜索某干支日的 datetime（六神与旬空都依赖日干支，故书例必须配上正确的日子）。"""
    d = datetime(2026, 8, 18)
    for _ in range(4000):
        s = Solar.fromYmdHms(d.year, d.month, d.day, 9, 0, 0)
        if s.getLunar().getEightChar().getDay() == day_ganzhi:
            return d
        d -= timedelta(days=1)
    raise RuntimeError(f"未找到 {day_ganzhi} 日")


def test_book_case_xun_zhihuan():
    """书例一：巳月甲寅日，占往营中贸易，得「巽之涣」（增删卜易·用神元神忌神仇神章）。

    巽为风（巽宫首卦）三爻官鬼辛酉金动，化子孙戊午火；世六应三。
    六神（甲日）：初青龙 二朱雀 三勾陈 四螣蛇 五白虎 上玄武。
    """
    lines = [
        raw(0),          # 初 阴 辛丑土 妻财
        raw(1),          # 二 阳 辛亥水 父母
        raw(1, True),    # 三 阳动 辛酉金 官鬼 应 → 子孙戊午火
        raw(0),          # 四 阴 辛未土 妻财
        raw(1),          # 五 阳 辛巳火 子孙
        raw(1),          # 上 阳 辛卯木 兄弟 世
    ]
    p = _build_paipan_from_raw(lines, dt=find_dt("甲寅"))
    assert p["palace"] == "巽宫"
    assert p["ben_gua"]["name"] == "巽为风"
    assert p["bian_gua"]["name"] == "风水涣"
    assert p["moving_positions"] == [3]
    assert p["lines"][5]["shi"], "世位错误（应为上爻）"
    assert p["lines"][2]["ying"], "应位错误（应为三爻）"
    assert [l["liuqin"] for l in p["lines"]] == ["妻财", "父母", "官鬼", "妻财", "子孙", "兄弟"]
    assert [l["gan"] + l["zhi"] for l in p["lines"]] == ["辛丑", "辛亥", "辛酉", "辛未", "辛巳", "辛卯"]
    # 三爻动 → 变爻戊午火子孙（照本卦巽宫木）
    b3 = p["lines"][2]["bian"]
    assert b3["gan"] + b3["zhi"] == "戊午"
    assert b3["liuqin"] == "子孙"
    # 六神（甲日 → 初青龙）
    assert [l["liushen"] for l in p["lines"]] == ["青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武"]


def test_book_case_guan_zhifou():
    """书例二：辰月己巳日（旬空戌亥），占会试，得「观之否」（增删卜易·六神章）。

    风地观（乾宫序四）四爻父母辛未土世动，化官鬼壬午火；世四应初。
    六神（己日）：初螣蛇 二白虎 三玄武 四青龙 五朱雀 上勾陈。变卦天地否为六合卦。
    """
    lines = [
        raw(0),          # 初 阴 乙未土
        raw(0),          # 二 阴 乙巳火
        raw(0),          # 三 阴 乙卯木
        raw(0, True),    # 四 阴动 辛未土 父母 世 → 官鬼壬午火
        raw(1),          # 五 阳 辛巳火
        raw(1),          # 上 阳 辛卯木
    ]
    p = _build_paipan_from_raw(lines, dt=find_dt("己巳"))
    assert p["palace"] == "乾宫"
    assert p["ben_gua"]["name"] == "风地观"
    assert p["bian_gua"]["name"] == "天地否"
    assert p["moving_positions"] == [4]
    assert p["lines"][3]["shi"], "世位错误（应为四爻）"
    assert p["lines"][0]["ying"], "应位错误（应为初爻）"
    b4 = p["lines"][3]["bian"]
    assert b4["gan"] + b4["zhi"] == "壬午"
    assert b4["liuqin"] == "官鬼"
    assert "六合" not in p["markers"], "本卦不应标六合"
    assert p["bian_gua"] is not None and "六合" in p["bian_gua"]["markers"], "变卦应标六合"
    assert [l["liushen"] for l in p["lines"]] == ["螣蛇", "白虎", "玄武", "青龙", "朱雀", "勾陈"]


def test_book_case_qian_weitian():
    """书例三：乾为天（六冲，八纯），世六应三。"""
    p = _build_paipan_from_raw([raw(1)] * 6)
    assert "六冲" in p["markers"]
    assert p["lines"][5]["shi"]
    assert p["lines"][2]["ying"]
    assert p["lines"][5]["liuqin"] == "父母" and p["lines"][5]["gan"] == "壬"


def test_palace_lookup_complete():
    """64 卦反查完整性：每个八卦组合都能查到，且世位在 1..6。"""
    assert len(PALACE_LOOKUP) == 64
    missing = [(up, lo) for up in range(1, 9) for lo in range(1, 9)
               if not (PALACE_LOOKUP.get((up, lo)) and 1 <= PALACE_LOOKUP[(up, lo)]["shi"] <= 6)]
    assert missing == []


def test_seed_and_coins_deterministic():
    """种子与铜钱：同参数同结果（起卦可复现是"记录可回放"的前提），时长参与种子。"""
    x, y, duration, speed = 40.37, -25.61, 812, 0.42
    seed = seed_from_params(x, y, duration, speed)
    assert 0 <= seed < 1
    assert seed == seed_from_params(x, y, duration, speed)
    coins = coins_from_seed(seed)
    assert coins == coins_from_seed(seed) and len(coins) == 3
    assert all(c in (0, 1) for c in coins)
    assert seed != seed_from_params(x, y, 900, speed), "时长应影响种子"


def test_paipan_is_deterministic():
    throws = [
        {"x": 40.37, "y": -25.61, "duration": 812, "speed": 0.42},
        {"x": -12.0, "y": 55.2, "duration": 1453, "speed": 0.31},
        {"x": 3.14, "y": 2.71, "duration": 666, "speed": 0.88},
        {"x": -33.3, "y": -44.4, "duration": 999, "speed": 1.12},
        {"x": 70.0, "y": 0.0, "duration": 1200, "speed": 0.55},
        {"x": 0.01, "y": -80.9, "duration": 500, "speed": 0.77},
    ]
    r1 = build_paipan(throws)
    r2 = build_paipan(throws)
    assert json.dumps(r1, ensure_ascii=False) == json.dumps(r2, ensure_ascii=False)
