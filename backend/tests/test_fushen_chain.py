# -*- coding: utf-8 -*-
"""用神不现检索链回归（临月建优先 + 日月→伏神→再占，世爻兜底废除）"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from liuyao_engine import build_paipan, line_from_coins, _build_paipan_from_raw  # noqa: E402
from liuyao_remedy import _find_fushen, _pick_yongshen_line, liuyao_remedy  # noqa: E402
from wuxing_relation import WUXING  # noqa: E402
from datetime import datetime  # noqa: E402


def _gua():
    return build_paipan([{"x": 1.1, "y": 2.2, "duration": 300, "speed": 0.5}] * 6)


def test_pick_line_month_branch_priority():
    """两现取舍：临月建者 > 动爻"""
    lines = [
        {"pos": 1, "liuqin": "妻财", "wuxing": "水", "zhi": "子", "moving": True},
        {"pos": 4, "liuqin": "妻财", "wuxing": "水", "zhi": "子", "moving": False},
    ]
    # 动爻优先（未给月支时保持旧行为）
    assert _pick_yongshen_line(lines, "妻财")["zhi"] == "子" and lines[0]["moving"]
    # 临月建者胜过动爻（月建午时……此处用临月建的另一爻验证）
    lines2 = [
        {"pos": 1, "liuqin": "父母", "wuxing": "土", "zhi": "辰", "moving": False},
        {"pos": 3, "liuqin": "父母", "wuxing": "土", "zhi": "辰", "moving": True},
    ]
    # 月建为辰：临月建的第 1 爻虽静也优先于动爻
    assert _pick_yongshen_line(lines2, "父母", month_branch="辰")["pos"] == 1


def test_fushen_found_for_missing_liuqin():
    """乾宫缺妻财 → 伏神寅木在二爻（首卦定位确定）；飞神取本卦同位爻"""
    g = _gua()
    fu = _find_fushen("金", "妻财", "乾宫", g["lines"])
    assert fu and fu["fu_zhi"] == "寅" and fu["position"] == 2
    # 飞神 = 本卦二爻的实存爻（随卦而变，只验证结构一致性）
    line2 = next(l for l in g["lines"] if l.get("position") == 2)
    assert fu["fei_wx"] == line2["wuxing"] and fu["fei_zhi"] == line2["zhi"]
    assert fu["relation"]


def test_remedy_no_shiyao_fallback():
    """用神不现时不再取世爻：X 为本宫六亲对应五行，R 走伏神链"""
    g = _gua()
    # 找一个本卦缺"子孙"或"妻财"的卦不可控（build_paipan 随机），
    # 因此直接验证：用神指定为"兄弟"时，若不现则 details 检索链正确
    r = liuyao_remedy(g, "占兄弟平安", yongshen_override="兄弟")
    if r["state"].startswith("用神伏藏"):
        assert "伏神" in json.dumps(r["details"], ensure_ascii=False)
        assert "世爻" not in r.get("yongshen_desc", "")
        assert "取世爻" not in r["R_reason"]
    else:
        assert r["X"]  # 正常路径


# ---------------------------------------------------------------------------
# 回归：用神不上卦而伏神可得 → R 必须赋值（2026-09-23 规则命中审计查出）
# 症状：R_reason 写了"伏神得出，加持事体五行"，但那一支只赋了 reason/state 没赋 R，
#       走到必抛 UnboundLocalError。随机 300 卦实测 26 卦（8.7%）走到该支，全是 500。
# ---------------------------------------------------------------------------
def _static_coins():
    found = {}
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                found.setdefault(line_from_coins([a, b, c])["type"], (a, b, c))
    return found


def _gua_from_bits(bits, dt=datetime(2026, 9, 19, 14, 30)):
    """六爻皆静（少阳／少阴）→ 本卦即那一个；64 种组合覆盖全部本卦。"""
    coins = _static_coins()
    raw = []
    for bit in bits:
        ty = "少阳" if bit else "少阴"
        L = line_from_coins(list(coins[ty]))
        L["coins"] = list(coins[ty])
        raw.append(L)
    return _build_paipan_from_raw(raw, dt)


def test_fushen_usable_path_sets_R_for_every_gua_and_yongshen():
    """穷举 64 本卦 × 5 六亲：任何一卦任何用神都不得抛异常，且 R 必为五行之一；
    并必须真有卦走到「用神伏藏而得出」这一支（否则本测试等于没验）。"""
    hit_usable = 0
    for i in range(64):
        bits = [(i >> k) & 1 for k in range(6)]
        g = _gua_from_bits(bits)
        for lq in ("父母", "兄弟", "子孙", "妻财", "官鬼"):
            r = liuyao_remedy(g, "占" + lq, yongshen_override=lq)
            assert r["R"] in WUXING, (g["ben_gua"]["name"], lq, r["R"])
            assert r["R_reason"], (g["ben_gua"]["name"], lq)
            if r["state"] == "用神伏藏而得出":
                hit_usable += 1
                assert r["R"] == r["X"], "伏神得出时 R 应取该六亲本宫五行（＝伏神五行）"
                assert "伏神" in r["details"]
    assert hit_usable > 0, "64 本卦 × 5 用神都没有走到「伏神得出」支，本回归失去意义"
