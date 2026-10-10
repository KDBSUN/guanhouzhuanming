# -*- coding: utf-8 -*-
"""
摇卦算法回归（liuyao_engine 三枚铜钱）
======================================
锁住一个曾经真实存在的严重缺陷：旧的三枚铜钱算法里，"三背/三字"在数学上
不可能出现，于是**老阳、老阴（动爻）永远摇不出来** —— 六爻就没有动爻、
没有变卦、没有动变可用神，断卦只能看静卦。

本测试锁三件事：
  1. 四种爻象都能摇出来（尤其是老阳/老阴这两个动爻）；
  2. 频率符合三钱法本来的 1/8、3/8、3/8、1/8；
  3. 确定性：同一种子必得同一结果（前后端一致的前提）。
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from liuyao_engine import build_paipan, coins_from_seed, line_from_coins, seed_from_params  # noqa: E402


def _seeds(n=20000):
    """铺满 [0,1) 的种子（真实摇杆参数会带来这样的分布）"""
    return [i / n for i in range(1, n + 1)]


def test_moving_lines_are_reachable():
    """老阳/老阴必须能摇出来 —— 否则六爻无动爻（历史 bug）"""
    kinds = Counter(line_from_coins(coins_from_seed(s))["type"] for s in _seeds())
    for t in ("老阳", "老阴", "少阳", "少阴"):
        assert kinds[t] > 0, f"{t} 摇不出来（三枚铜钱算法又退化了）"
    assert sum(1 for t in ("老阳", "老阴") if kinds[t] > 0) == 2


def test_coin_distribution_is_classical():
    """三钱法分布：三字 1/8、一背 3/8、两背 3/8、三背 1/8"""
    c = Counter(sum(coins_from_seed(s)) for s in _seeds())
    total = sum(c.values())
    assert abs(c[0] / total - 0.125) < 0.02      # 三字（老阴）
    assert abs(c[1] / total - 0.375) < 0.02      # 一背（少阳）
    assert abs(c[2] / total - 0.375) < 0.02      # 两背（少阴）
    assert abs(c[3] / total - 0.125) < 0.02      # 三背（老阳）


def test_coins_deterministic():
    """同种子同结果（前端 liuyaoSeed.ts 与后端必须逐位一致）"""
    for s in (0.0, 0.123456789, 0.5, 0.999999):
        assert coins_from_seed(s) == coins_from_seed(s)
    # 已知向量：与前端 JS 逐位比对过的固定值（防单边改动）
    known = {
        0.2037000000000262: [0, 1, 0],
        0.61850000000004: [1, 1, 1],
        0.411099999999351: [1, 1, 0],
    }
    for s, want in known.items():
        assert coins_from_seed(s) == want, f"种子 {s} 的铜钱结果与前端不一致"


def test_paipan_can_have_moving_and_bian_gua():
    """排盘层面：能排出带动爻与变卦的盘（不再是"永远静卦"）"""
    found = None
    for i in range(1, 4000):
        throws = [{"x": (i * 0.137 + k * 0.719) % 9 - 4.5,
                   "y": (i * 0.291 + k * 0.433) % 7 - 3.5,
                   "duration": 100 + (i * 3.7 + k * 11.3) % 500,
                   "speed": (i * 0.017 + k * 0.031) % 3} for k in range(6)]
        p = build_paipan(throws)
        if p["moving_positions"] and p.get("bian_gua"):
            found = p
            break
    assert found is not None, "四千次摇卦都没有动爻，摇卦算法有问题"
    assert any(l["moving"] for l in found["lines"])
    assert found["bian_gua"]["name"] != found["ben_gua"]["name"] or found["moving_positions"]
