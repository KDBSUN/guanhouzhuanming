# -*- coding: utf-8 -*-
"""
pytest 共享夹具：把 backend 目录加入 sys.path，并提供合成命局工厂。
合成命局只喂给 build_xiji（纯函数），不依赖 lunar-python 排盘，
十神按 lunar-python 口径构造（非日柱的同干为比肩，日柱自身为日主）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bazi_engine import build_xiji, GAN_WUXING, ZHI_WUXING, gan_shishen  # noqa: E402

# 地支藏干（传统通行口径）
HIDE = {"子": "癸", "丑": "己癸辛", "寅": "甲丙戊", "卯": "乙", "辰": "戊乙癸",
        "巳": "丙庚戊", "午": "丁己", "未": "己丁乙", "申": "庚壬戊", "酉": "辛",
        "戌": "戊辛丁", "亥": "壬甲"}
LABELS = ["年柱", "月柱", "日柱", "时柱"]


def _pillar_ss(dm: str, g: str, i: int) -> str:
    if i == 2:
        return "日主"
    if g == dm:
        return "比肩"
    return gan_shishen(dm, g)


def mk_xiji(gans: str, zhis: str) -> dict:
    """四柱天干/地支字符串（如 '庚辛乙辛','戌酉酉巳'）→ build_xiji 完整输出"""
    dm = gans[2]
    pillars = []
    for i in range(4):
        g, z = gans[i], zhis[i]
        cang = [{"gan": h, "wuxing": GAN_WUXING[h],
                 "shishen": ("比肩" if h == dm else gan_shishen(dm, h))} for h in HIDE[z]]
        pillars.append({"label": LABELS[i], "ganzhi": g + z, "gan": g, "zhi": z,
                        "gan_wuxing": GAN_WUXING[g], "zhi_wuxing": ZHI_WUXING[z],
                        "shishen_gan": _pillar_ss(dm, g, i), "canggan": cang})
    tally = {w: 0 for w in "金木水火土"}
    for p in pillars:
        tally[p["gan_wuxing"]] += 1
        tally[p["zhi_wuxing"]] += 1
    return build_xiji({"bazi": pillars,
                       "day_master": {"gan": dm, "wuxing": GAN_WUXING[dm]},
                       "wuxing_tally": tally})
