# -*- coding: utf-8 -*-
"""大六壬起课引擎回归测试。

夹具来源（books/daliuren/，行号为当前行号）：
- 《六壬大全》起课教程各节实例（L12150–13198）：四课两例、贼克两例、比用一例、
  涉害五例、遥克两例、昴星两例、别责两例、八专三例、伏吟多例、返吟两例＋六日清单。
- 《六壬大全》课经正文：伏吟杜传六日清单（L6312）、返吟庚戌例（L6416）、井栏（L6472/L6498）。
- 《六壬金针》返吟四例（L596–624）。
- 《大六壬指南》占验二十戊辰案（L2695–2705，四课/三传/天将/六亲全链）、
  占验二十九甲子案（L2829–2843，三传午卯子＋天将龙/朱/后）。
- 遁干：《六壬大全》L14072（甲子日三传午卯子→午遁庚、卯遁丁、子遁甲）。
- 月将：中气交节时刻后换将（站长 2026-09-26 裁定；大全 L12208、指南 L167）。

已登记的分歧（测试断言采规则推导/课经正文，并注明出处）：
- 教程 L13148 壬子/壬午/壬寅/壬申返吟四行与其自身涉害法不符 → 采推导（巳亥巳），
  以指南戊辰案（弃不比之贼、取相比之克）为独立佐证。
- 教程 L13150 乙丑/乙未返吟（辰戌辰）→ 采贼克推导（戌辰戌）。
- 教程 L13116 伏吟壬辰壬午又诀（亥巳申）→ 采课经 L6312 正文（亥辰戌/亥午子）。
- 金针 L624 井栏例四（巳丑辰）→ 采课经 L6472（辛丑→亥未辰）。
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from daliuren import (qike_core, qike, tianpan, yue_jiang_at, dunkun_gz, liuqin, xunkong,
                      bu_tianjiang, YUEJIANG, MA)
from lunar_python import Solar


def _chuan(day_gz, shi, jiang):
    return qike_core(day_gz, shi, jiang)["三传"]


def _ti(day_gz, shi, jiang):
    return qike_core(day_gz, shi, jiang)["课体"]


def _sike(day_gz, shi, jiang):
    return qike_core(day_gz, shi, jiang)["四课"]


# ---------------- 一、月将（中气交节时刻后换将） ----------------

def test_yuejiang_table():
    # 大全 L12210–12236 月将表：亥雨水…子大寒雨水
    assert YUEJIANG == {"冬至": "丑", "大寒": "子", "雨水": "亥", "春分": "戌", "谷雨": "酉",
                        "小满": "申", "夏至": "未", "大暑": "午", "处暑": "巳", "秋分": "辰",
                        "霜降": "卯", "小雪": "寅"}


def test_yuejiang_mid_segment_dates():
    # 各段中部日期（远离交节时刻，与现行节气数据无关的稳区）
    cases = [
        (datetime(2024, 2, 10, 12, 0), "子"), (datetime(2024, 3, 1, 12, 0), "亥"),
        (datetime(2024, 3, 25, 12, 0), "戌"), (datetime(2024, 5, 1, 12, 0), "酉"),
        (datetime(2024, 5, 25, 12, 0), "申"), (datetime(2024, 6, 25, 12, 0), "未"),
        (datetime(2024, 7, 25, 12, 0), "午"), (datetime(2024, 8, 25, 12, 0), "巳"),
        (datetime(2024, 9, 25, 12, 0), "辰"), (datetime(2024, 10, 25, 12, 0), "卯"),
        (datetime(2024, 11, 25, 12, 0), "寅"), (datetime(2024, 12, 25, 12, 0), "丑"),
        (datetime(2025, 1, 25, 12, 0), "子"),
    ]
    for dt, want in cases:
        assert yue_jiang_at(dt) == want, (dt, yue_jiang_at(dt))


def test_yuejiang_jieqi_moment_boundary():
    # 中气交节时刻为界：交节前用旧将、交节后用新将（历法数据源＝lunar_python）
    from qimen import _jieqi_timeline
    names = ["雨水", "春分", "谷雨", "小满", "夏至", "大暑", "处暑", "秋分", "霜降", "小雪", "冬至", "大寒"]
    for year in (2024, 2025):
        tl = _jieqi_timeline(year)
        for name in names:
            t = next(t for n, t in tl if n == name and t.year == year)
            after = datetime(t.year, t.month, t.day, t.hour, t.minute, t.second) + \
                __import__("datetime").timedelta(minutes=1)
            before = after - __import__("datetime").timedelta(minutes=2)
            assert yue_jiang_at(before) != yue_jiang_at(after), (name, year)
            assert yue_jiang_at(after) == YUEJIANG[name], (name, year)


# ---------------- 二、天地盘与四课（教程两例） ----------------

def test_tianpan_sike_guichou():
    # 大全 L12284–12312：癸酉日子时亥将
    r = qike_core("癸酉", "子", "亥")
    assert r["天盘"]["子"] == "亥" and r["天盘"]["巳"] == "辰" and r["天盘"]["戌"] == "酉"
    assert r["四课"] == {"干上": "子", "干阴": "亥", "支上": "申", "支阴": "未"}


def test_tianpan_sike_renwu():
    # 大全 L12314–12326：壬午日未时戌将
    r = qike_core("壬午", "未", "戌")
    assert r["天盘"]["未"] == "戌" and r["天盘"]["申"] == "亥"
    assert r["四课"] == {"干上": "寅", "干阴": "巳", "支上": "酉", "支阴": "子"}


# ---------------- 三、贼克、比用、涉害（教程七例） ----------------

def test_zeke_yuanshou():
    # 大全 L12338–12362：丁丑日子时申将，元首，三传巳丑酉
    assert _chuan("丁丑", "子", "申") == ["巳", "丑", "酉"]
    assert _ti("丁丑", "子", "申") == "元首"


def test_zeke_chongshen():
    # 大全 L12364–12386：丙戌日巳时申将，重审，三传申亥寅
    assert _chuan("丙戌", "巳", "申") == ["申", "亥", "寅"]
    assert _ti("丙戌", "巳", "申") == "重审"


def test_biyong_zhiyi():
    # 大全 L12410–12432：壬辰日巳时辰将，知一，三传戌酉申
    assert _chuan("壬辰", "巳", "辰") == ["戌", "酉", "申"]
    assert _ti("壬辰", "巳", "辰") == "知一"


def test_shehai_li1():
    # 大全 L12446–12518：丁卯日丑时亥将，涉害深（6 对 2），三传亥酉未
    assert _chuan("丁卯", "丑", "亥") == ["亥", "酉", "未"]
    assert _ti("丁卯", "丑", "亥") == "涉害·见机"


def test_shehai_li2():
    # 大全 L12520–12594：庚子日戌时申将，午涉 4 戌涉 2，三传午辰寅
    assert _chuan("庚子", "戌", "申") == ["午", "辰", "寅"]
    assert _ti("庚子", "戌", "申") == "涉害·见机"


def test_shehai_li3_meng():
    # 大全 L12596–12622：丙子日辰时亥将，涉害等取孟上神，三传子未寅
    assert _chuan("丙子", "辰", "亥") == ["子", "未", "寅"]
    assert _ti("丙子", "辰", "亥") == "涉害·见机"


def test_shehai_li4_zhong():
    # 大全 L12628–12648：庚午日卯时未将，涉害等无孟取仲，三传辰申子，察微
    assert _chuan("庚午", "卯", "未") == ["辰", "申", "子"]
    assert _ti("庚午", "卯", "未") == "涉害·察微"


def test_shehai_li5_fudeng():
    # 大全 L12654–12680：戊辰日午时丑将，复等阳日取干课先见，三传子未寅，缀瑕
    assert _chuan("戊辰", "午", "丑") == ["子", "未", "寅"]
    assert _ti("戊辰", "午", "丑") == "涉害·缀瑕"


# ---------------- 四、遥克、昴星、别责、八专（教程九例） ----------------

def test_yaoke_haoshi():
    # 大全 L12708–12728：壬辰日寅时巳将，蒿矢，三传戌丑辰
    assert _chuan("壬辰", "寅", "巳") == ["戌", "丑", "辰"]
    assert _ti("壬辰", "寅", "巳") == "蒿矢"


def test_yaoke_tanshe():
    # 大全 L12730–12750：壬申日申时亥将，弹射，三传巳申亥
    assert _chuan("壬申", "申", "亥") == ["巳", "申", "亥"]
    assert _ti("壬申", "申", "亥") == "弹射"


def test_maoxing_hushi():
    # 大全 L12764–12784：戊寅日子时辰将，虎视转篷，三传丑午酉
    assert _chuan("戊寅", "子", "辰") == ["丑", "午", "酉"]
    assert _ti("戊寅", "子", "辰") == "昴星·虎视转篷"


def test_maoxing_dongshe():
    # 大全 L12786–12806：丁亥日寅时巳将，冬蛇掩目，三传午戌寅
    assert _chuan("丁亥", "寅", "巳") == ["午", "戌", "寅"]
    assert _ti("丁亥", "寅", "巳") == "昴星·冬蛇掩目"


def test_bieze_gang():
    # 大全 L12844–12866：丙辰日卯时辰将，三传亥午午
    assert _chuan("丙辰", "卯", "辰") == ["亥", "午", "午"]
    assert _ti("丙辰", "卯", "辰") == "别责"


def test_bieze_rou():
    # 大全 L12868–12890：辛酉日丑时子将，三传丑酉酉
    assert _chuan("辛酉", "丑", "子") == ["丑", "酉", "酉"]
    assert _ti("辛酉", "丑", "子") == "别责"


def test_bazhuan_gang():
    # 大全 L12904–12924：甲寅日辰时丑将，三传丑亥亥
    assert _chuan("甲寅", "辰", "丑") == ["丑", "亥", "亥"]
    assert _ti("甲寅", "辰", "丑") == "八专"


def test_bazhuan_rou():
    # 大全 L12926–12946：丁未日丑时辰将，三传亥戌戌
    assert _chuan("丁未", "丑", "辰") == ["亥", "戌", "戌"]
    assert _ti("丁未", "丑", "辰") == "八专"


def test_bazhuan_duzu():
    # 大全 L12950–12970：己未日未时酉将，独足，三传酉酉酉
    assert _chuan("己未", "未", "酉") == ["酉", "酉", "酉"]
    assert _ti("己未", "未", "酉") == "独足"


# ---------------- 五、伏吟（课经 L6312 六日清单） ----------------

def test_fuyin_youke():
    # 六癸日（L13032 丑戌未）；六乙日（L6312 清单：中传支上、末刑冲）
    assert _chuan("癸丑", "丑", "丑") == ["丑", "戌", "未"]
    for zhi, want in [("丑", ["辰", "丑", "戌"]), ("未", ["辰", "未", "丑"]),
                      ("巳", ["辰", "巳", "申"]), ("卯", ["辰", "卯", "子"]),
                      ("亥", ["辰", "亥", "巳"]), ("酉", ["辰", "酉", "卯"])]:
        assert _chuan("乙" + zhi, zhi, zhi) == want, ("乙" + zhi)
        assert _ti("乙" + zhi, zhi, zhi) == "伏吟", ("乙" + zhi)


def test_fuyin_ziren():
    # 课经 L6260/L6264：自任——甲寅巳申、丙戊巳申寅、庚申寅巳
    assert _chuan("甲子", "子", "子") == ["寅", "巳", "申"]
    assert _chuan("丙子", "子", "子") == ["巳", "申", "寅"]
    assert _chuan("戊子", "子", "子") == ["巳", "申", "寅"]
    assert _chuan("庚子", "子", "子") == ["申", "寅", "巳"]
    assert _ti("甲子", "子", "子") == "自任"


def test_fuyin_ren_duchuan():
    # 课经 L6312：壬日伏吟（初传亥自刑→中传支上、末刑冲）六日清单
    for zhi, want in [("子", ["亥", "子", "卯"]), ("寅", ["亥", "寅", "巳"]),
                      ("辰", ["亥", "辰", "戌"]), ("午", ["亥", "午", "子"]),
                      ("申", ["亥", "申", "寅"]), ("戌", ["亥", "戌", "未"])]:
        assert _chuan("壬" + zhi, zhi, zhi) == want, ("壬" + zhi)
        assert _ti("壬" + zhi, zhi, zhi) == "杜传", ("壬" + zhi)


def test_fuyin_zixin():
    # 课经 L6286/L6312：自信（阴日无克取支上神）与杜传（支上神自刑）清单
    for g in "丁己":
        for zhi, want in [("丑", ["丑", "戌", "未"]), ("卯", ["卯", "子", "午"]),
                          ("巳", ["巳", "申", "寅"]), ("未", ["未", "丑", "戌"]),
                          ("酉", ["酉", "未", "丑"]), ("亥", ["亥", "未", "丑"])]:
            assert _chuan(g + zhi, zhi, zhi) == want, (g + zhi)
            ti = _ti(g + zhi, zhi, zhi)
            assert ti in ("自信", "杜传"), (g + zhi, ti)
    for zhi, want in [("酉", ["酉", "戌", "未"]), ("亥", ["亥", "戌", "未"]),
                      ("丑", ["丑", "戌", "未"]), ("卯", ["卯", "子", "午"])]:
        assert _chuan("辛" + zhi, zhi, zhi) == want, ("辛" + zhi)


# ---------------- 六、返吟（课经/金针/教程/指南诸案） ----------------

def test_fanyin_gengxu_book_case():
    # 课经 L6416：庚戌日寅时申将，三传寅申寅
    assert _chuan("庚戌", "寅", "申") == ["寅", "申", "寅"]
    assert _ti("庚戌", "寅", "申") == "返吟·无依"


def test_fanyin_jinzhen_cases():
    # 金针 L602/L608/L614：甲戌、戊午、庚子（时/将取冲即可，均用寅时申将）
    assert _chuan("甲戌", "寅", "申") == ["寅", "申", "寅"]
    assert _chuan("戊午", "寅", "申") == ["午", "子", "午"]
    assert _chuan("庚子", "寅", "申") == ["寅", "申", "寅"]


def test_fanyin_wuchen_zhinan_case():
    # 指南占验二十：戊辰日丙辰时戌将。四课/天盘与指南记录一致；
    # 三传按课经订讹「有克照常克贼比涉等项论」推导为亥巳亥（亥涉 4＝巳涉 4，
    # 俱孟复等取干课先见），指南记录作巳亥巳，断案疏正 L4109 已指该案月将有疑——
    # 分歧登记判据总表第六节，本站采规则推导。
    r = qike_core("戊辰", "辰", "戌")
    assert r["四课"] == {"干上": "亥", "干阴": "巳", "支上": "戌", "支阴": "辰"}
    assert r["三传"] == ["亥", "巳", "亥"] and r["课体"] == "返吟·无依"


def test_fanyin_yichou_rule_derived():
    # 教程 L13150 作辰戌辰（乙丑乙未），其四课仅干课有下贼上（乙克戌）单克，
    # 辰戌辰与贼克规则不可复现；采推导戌辰戌（登记判据总表）
    assert _chuan("乙丑", "寅", "申") == ["戌", "辰", "戌"]
    assert _chuan("乙未", "寅", "申") == ["戌", "辰", "戌"]


def test_fanyin_guidings():
    # 教程 L13150–13152 逐例核对一致者：
    assert _chuan("癸丑", "寅", "申") == ["未", "丑", "未"]
    assert _chuan("癸未", "寅", "申") == ["未", "丑", "未"]
    assert _chuan("乙卯", "寅", "申") == ["卯", "酉", "卯"]
    assert _chuan("乙酉", "寅", "申") == ["卯", "酉", "卯"]
    assert _chuan("癸卯", "寅", "申") == ["卯", "酉", "卯"]
    # 乙亥/乙巳：干课贼戌（不比）与支课贼（巳，比）比筛取巳
    assert _chuan("乙亥", "寅", "申") == ["巳", "亥", "巳"]
    assert _chuan("乙巳", "寅", "申") == ["巳", "亥", "巳"]
    # 癸亥/癸巳：支课下贼上巳单取
    assert _chuan("癸亥", "寅", "申") == ["巳", "亥", "巳"]
    assert _chuan("癸巳", "寅", "申") == ["巳", "亥", "巳"]
    # 教程 L13148 壬日六支：子午→午子午、寅申→寅申寅、辰戌→巳亥巳（比筛逐例核对一致）
    assert _chuan("壬子", "寅", "申") == ["午", "子", "午"]
    assert _chuan("壬午", "寅", "申") == ["午", "子", "午"]
    assert _chuan("壬寅", "寅", "申") == ["寅", "申", "寅"]
    assert _chuan("壬申", "寅", "申") == ["寅", "申", "寅"]
    assert _chuan("壬辰", "寅", "申") == ["巳", "亥", "巳"]
    assert _chuan("壬戌", "寅", "申") == ["巳", "亥", "巳"]


def test_fanyin_jinglan():
    # 课经 L6472/L6498：辛丑日巳时亥将，井栏，三传亥未辰（初＝支之驿马）
    assert _chuan("辛丑", "巳", "亥") == ["亥", "未", "辰"]
    assert _ti("辛丑", "巳", "亥") == "返吟·井栏"
    # 丁未日（井栏六日之一，兼八专）：初＝未之驿马巳，中末支上＝干上＝丑
    assert _chuan("丁未", "巳", "亥") == ["巳", "丑", "丑"]
    assert MA["丑"] == "亥" and MA["未"] == "巳"


# ---------------- 七、贵人天将（指南两案逐宫核对） ----------------

def test_tianjiang_wuchen_zhinan():
    # 指南占验二十：戊辰日辰时（昼贵丑，临未宫逆布）。天将布法与指南记录逐宫一致；
    # 三传天将按本站规则推导的三传（亥巳亥）标注。
    r = qike_core("戊辰", "辰", "戌")
    tj = r["天将"]
    assert r["贵人"] == "昼贵丑" and r["贵人顺逆"] == "逆"
    # 四课天将：一课亥乘朱雀、二课巳乘太常、三课戌乘六合、四课辰乘玄武（与指南记录同）
    assert tj["亥"] == "朱雀" and tj["巳"] == "太常"
    assert tj["戌"] == "六合" and tj["辰"] == "玄武"
    # 三传天将：初传亥乘朱雀、中传巳乘太常、末传亥乘朱雀
    assert [tj[z] for z in r["三传"]] == ["朱雀", "太常", "朱雀"]


def test_tianjiang_jiazi_zhinan():
    # 指南占验二十九：甲子日巳时寅将（昼贵丑，临辰宫顺布）
    r = qike_core("甲子", "巳", "寅")
    assert r["三传"] == ["午", "卯", "子"] and r["课体"] == "元首"
    assert r["贵人"] == "昼贵丑" and r["贵人顺逆"] == "顺"
    tj = r["天将"]
    assert tj["午"] == "青龙" and tj["卯"] == "朱雀" and tj["子"] == "天后"
    assert [tj[z] for z in r["三传"]] == ["青龙", "朱雀", "天后"]


def test_tianjiang_yeguiren():
    # 酉至寅夜贵（大全 L14040）：甲日酉时用夜贵未
    r = qike_core("甲子", "酉", "寅")
    assert r["贵人"] == "夜贵未"


# ---------------- 八、遁干、六亲、空亡 ----------------

def test_dungan_jiazi():
    # 大全 L14072 逐字：甲子日起课得三传午卯子，午遁庚、卯遁丁、子遁甲
    assert dunkun_gz("甲子", ["午", "卯", "子"]) == ["庚", "丁", "甲"]


def test_dungan_liuqin_kong_wuchen():
    # 戊辰日（甲子旬）三传亥巳亥→遁干空/己/空；
    # 六亲：亥水为戊所克＝财、巳火生戊土＝父；空亡戌亥（亥在传中为空）
    # （指南占验二十记录的三传为巳亥巳，六亲标注「父巳常、财亥朱」；本站采规则推导三传，
    #   其六亲标注为财亥/父巳——登记判据总表）
    r = qike_core("戊辰", "辰", "戌")
    assert r["遁干"] == ["空", "己", "空"]
    assert r["六亲"] == ["妻财", "父母", "妻财"]
    assert r["空亡"] == ["戌", "亥"]
    assert "亥" in r["空亡"] and r["三传"][1] == "巳"


def test_liuqin_basic():
    # 甲木：申金克甲＝官鬼、亥水生甲＝父母、寅木比和＝兄弟、午火甲所生＝子孙、辰土甲所克＝妻财
    assert liuqin("甲", ["申", "亥", "寅", "午", "辰"]) == ["官鬼", "父母", "兄弟", "子孙", "妻财"]


def test_xunkong_liuxun():
    # 甲子旬戌亥空（大全 L12114），余旬同法推
    assert xunkong("甲子") == ["戌", "亥"]
    assert xunkong("甲戌") == ["申", "酉"]
    assert xunkong("甲申") == ["午", "未"]
    assert xunkong("甲午") == ["辰", "巳"]
    assert xunkong("甲辰") == ["寅", "卯"]
    assert xunkong("甲寅") == ["子", "丑"]


# ---------------- 九、起课入口（正时/活时） ----------------

def test_qike_realtime():
    # 2002-04-07 08:00：乙巳日辰时，春分后月将戌（春分 03-21 已过）→ 戌将加辰
    r = qike(datetime(2002, 4, 7, 8, 0))
    assert r["日干支"] == "乙巳" and r["占时"] == "辰" and r["月将"] == "戌"
    # 活时指定：同一时刻改午时起课
    r2 = qike(datetime(2002, 4, 7, 8, 0), shi_zhi="午")
    assert r2["占时"] == "午" and r2["月将"] == "戌"


def test_qike_zishi_day_roll():
    # 子时换日：2024-02-19 23:30 日干支按次日算
    from daliuren import day_gz_rolled
    assert day_gz_rolled(datetime(2024, 2, 19, 23, 30)) == \
        Solar.fromYmdHms(2024, 2, 20, 12, 0, 0).getLunar().getDayInGanZhi()


# ---------------- 十、起课接口 ----------------

def test_daliuren_endpoint():
    from fastapi.testclient import TestClient
    from main import app
    c = TestClient(app)
    # 启悟转盘阴2局书例同刻（2005-08-09 12:00）：乙丑日壬午时，大暑后月将午
    r = c.post("/api/daliuren", json={"dt": "2005-08-09 12:00"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["日干支"] == "乙丑" and d["占时"] == "午" and d["月将"] == "午"
    assert len(d["三传"]) == 3 and d["课体"]
    assert len(d["天将"]) == 12 and "书证" in d
    # 活时
    r2 = c.post("/api/daliuren", json={"dt": "2005-08-09 12:00", "shizhi": "申"})
    assert r2.status_code == 200 and r2.json()["占时"] == "申"
    # 坏时支
    r3 = c.post("/api/daliuren", json={"dt": "2005-08-09 12:00", "shizhi": "猫"})
    assert r3.status_code == 400
    # 缺省时间为现在
    r4 = c.post("/api/daliuren", json={})
    assert r4.status_code == 200 and r4.json()["日干支"]


def test_daliuren_endpoint_nianming():
    # 年命输入：丙子年生男，2005-08-09（乙酉年）起课＝虚岁10，行年＝丙寅顺数9步＝乙亥；
    # 断言值与 _nianming 同口径对拍（教程 L14084–14088）。
    from fastapi.testclient import TestClient
    from main import app
    from daliuren import _nianming
    c = TestClient(app)
    r = c.post("/api/daliuren", json={"dt": "2005-08-09 12:00",
                                      "nianzhu": "丙子", "xingbie": "男"})
    assert r.status_code == 200, r.text
    d = r.json()
    expect = _nianming("丙子", "男", "乙酉")
    assert d["年命"]["本命"] == expect["本命"] == "子"
    assert d["年命"]["行年"] == expect["行年"]
    assert d["年命"]["行年干支"] == expect["行年干支"]
    # 配偶年命（繁昌课用）
    r2 = c.post("/api/daliuren", json={"dt": "2005-08-09 12:00",
                                       "nianzhu": "丙子", "xingbie": "男",
                                       "nianzhu2": "戊寅", "xingbie2": "女"})
    assert r2.status_code == 200 and r2.json()["配偶年命"]["本命"] == "寅"
    # 非法年干支
    r3 = c.post("/api/daliuren", json={"nianzhu": "猫年"})
    assert r3.status_code == 400
    # 缺性别不能推行年
    r4 = c.post("/api/daliuren", json={"nianzhu": "丙子"})
    assert r4.status_code == 400


# ---------------- 十一、课体判语与附加课体（课经六十四课体） ----------------

def test_keti_judgement_book_texts():
    # 九宗门课体判语逐字（课经）
    assert qike_core("乙丑", "丑", "丑")["课体判语"].startswith("统艮之体，守旧待新之课也")
    assert "元吉第一课" in qike_core("丁丑", "子", "申")["课体判语"]  # 元首
    assert "狐假虎威" in qike_core("壬辰", "寅", "巳")["课体判语"]    # 蒿矢
    assert "留连之体" in qike_core("丙辰", "卯", "辰")["课体判语"]    # 别责
    assert "诸侯会盟" in qike_core("甲寅", "辰", "丑")["课体判语"]    # 八专
    assert "重重震惊" in qike_core("戊辰", "辰", "戌")["课体判语"]    # 返吟


def test_fujia_keti_mechanical():
    from daliuren import fujia_keti, tianpan
    def names(day_gz, tp, chuan, shi, tj=None):
        return [x["课体"] for x in fujia_keti(day_gz[0], day_gz[1], tp, chuan, shi, tj or {})]
    # 全局·润下（三传申子辰）
    assert "全局·润下" in names("壬子", tianpan("寅", "午"), ["申", "子", "辰"], "午")
    # 连珠（三传寅卯辰顺连）
    assert "连珠" in names("甲子", tianpan("寅", "午"), ["寅", "卯", "辰"], "午")
    # 间传（三传子寅辰隔位）
    assert "间传" in names("甲子", tianpan("寅", "午"), ["子", "寅", "辰"], "午")
    # 铸印（中传戌，戌加巳）：月将戌加巳时
    assert "铸印" in names("壬子", tianpan("戌", "巳"), ["巳", "戌", "寅"], "午")
    # 斫轮（初传卯，卯加申）：月将卯加申时
    assert "斫轮" in names("甲子", tianpan("卯", "申"), ["卯", "子", "未"], "午")
    # 三奇＋六仪（甲子旬用丑为旬奇、子为旬首之仪；日奇甲用午）
    r = fujia_keti("甲", "子", tianpan("寅", "午"), ["丑", "午", "子"], "午", {})
    got = [x["课体"] for x in r]
    assert "三奇" in got and "六仪" in got
    # 九丑（戊子日、四仲时、初传丑、丑临四仲宫）：月将丑加子时
    r = fujia_keti("戊", "子", tianpan("丑", "子"), ["丑", "午", "未"], "午", {})
    assert "九丑" in [x["课体"] for x in r]
    # 励德（甲日昼贵丑，丑临卯宫）：月将丑加卯时
    r = fujia_keti("甲", "子", tianpan("丑", "卯"), ["午", "寅", "子"], "午", {})
    assert "励德" in [x["课体"] for x in r]
    # 淫泆（初传卯乘天后）
    r = fujia_keti("甲", "子", tianpan("寅", "午"), ["卯", "子", "未"], "午", {"卯": "天后"})
    assert "淫泆" in [x["课体"] for x in r]
    # 龙战（卯日卯发用）
    r = fujia_keti("辛", "卯", tianpan("寅", "午"), ["卯", "子", "未"], "午", {})
    assert "龙战" in [x["课体"] for x in r]


def test_fujia_keti_wulu_degree():
    # 无禄（四课俱上克下）：丙子日辰时亥将（教程涉害例三的盘）
    from daliuren import tianpan, fujia_keti
    r = fujia_keti("丙", "子", tianpan("亥", "辰"), ["子", "未", "寅"], "辰", {})
    assert "无禄" in [x["课体"] for x in r]


# ---------------- 十二、旺衰类课体（三光/三阳/时泰/龙德） ----------------

def test_fujia_wangshuai_sanguang():
    # 三光（课经 L6526）：用神、日辰旺相，用神/干上/支上三处乘吉将。
    # 甲寅日午时寅月占：甲(木)旺、寅(木)旺、用神卯(木)旺，三处乘吉将（同 L6530「甲日春占」例构）。
    from daliuren import tianpan, fujia_keti
    from datetime import datetime
    tp = tianpan("寅", "午")
    sk, zs = tp["寅"], tp["寅"]
    tj = {"卯": "贵人", sk: "青龙", zs: "六合"}
    out = fujia_keti("甲", "寅", tp, ["卯", "辰", "巳"], "午", tj,
                     dt=datetime(2024, 2, 15, 12, 0), yue_jiang="")
    names = [x["课体"] for x in out]
    assert "三光" in names
    assert any(x["课体"] == "三光" and "光明通达" in x["判语"] for x in out)
    # 用神乘凶将则不三光（「吉神在中」）
    out2 = fujia_keti("甲", "寅", tp, ["卯", "辰", "巳"], "午",
                      {"卯": "螣蛇", sk: "青龙", zs: "六合"},
                      dt=datetime(2024, 2, 15, 12, 0), yue_jiang="")
    assert "三光" not in [x["课体"] for x in out2]


def test_fujia_wangshuai_sanyang():
    # 三阳（课经 L6624/L6628 例；订讹 L6652「用神旺相」）：天乙顺行、日辰居天乙前、
    # 用神旺相（月令旺相或日干帝旺——课经例「乙丑日…寅为旺气」寅即乙之帝旺）。
    # 「日辰居前」＝天盘落宫口径（inv）：甲寅日卯时丑将，甲昼贵丑临卯宫顺行，
    # 干寄寅、日支寅的天盘落宫辰皆居天乙前（顺距离1），初传寅于寅月旺。
    from daliuren import tianpan, fujia_keti
    from datetime import datetime
    tp = tianpan("丑", "卯")
    assert tp["卯"] == "丑"  # 贵人丑临卯宫（亥子丑寅卯辰位＝顺行）
    out = fujia_keti("甲", "寅", tp, ["寅", "辰", "午"], "卯",
                     {"寅": "太常", "子": "白虎"},
                     dt=datetime(2024, 2, 15, 6, 0), yue_jiang="")
    names = [x["课体"] for x in out]
    assert "三阳" in names
    assert any(x["课体"] == "三阳" and "龙剑呈祥" in x["判语"] for x in out)


def test_fujia_wangshuai_shitai():
    # 时泰（课经 L6852 例同构：子年戌月戊寅日戌时卯将）：用神子＝太岁、加未为用、
    # 乘青龙，又为戊日之财（戊土克子水）→ 时泰。
    from daliuren import tianpan, fujia_keti
    from datetime import datetime
    tp = tianpan("卯", "戌")  # 卯将加戌时；tp[未]=子（子加未为用，同课经例）
    assert tp["未"] == "子"
    tj = {"子": "青龙", "午": "六合"}
    out = fujia_keti("戊", "寅", tp, ["子", "寅", "午"], "戌", tj,
                     dt=datetime(2020, 10, 15, 20, 0), yue_jiang="卯")
    names = [x["课体"] for x in out]
    assert "时泰" in names
    assert any(x["课体"] == "时泰" and "天地和畅" in x["判语"] for x in out)


def test_fujia_wangshuai_longde():
    # 龙德（课经 L6890 例同构：巳年七月癸酉日酉时巳将）：巳＝太岁＝月将＝日贵，加酉发用。
    from daliuren import tianpan, fujia_keti
    from datetime import datetime
    tp = tianpan("巳", "酉")  # 巳将加酉时：tp[酉]=巳（巳加酉为用，同课经例）
    assert tp["酉"] == "巳"
    out = fujia_keti("癸", "酉", tp, ["巳", "丑", "子"], "酉", {"巳": "贵人"},
                     dt=datetime(2025, 5, 10, 18, 0), yue_jiang="巳")
    names = [x["课体"] for x in out]
    assert "龙德" in names
    assert any(x["课体"] == "龙德" and "云龙际会" in x["判语"] for x in out)


# ---------------- 十三、本命行年（教程 L14078–14088） ----------------

def test_nianming_xingnian():
    from daliuren import _nianming
    # 丙子年生人，乙未流年＝20岁：男行年乙酉（与教程例一致）
    n = _nianming("丙子", "男", "乙未")
    assert n["本命"] == "子" and n["虚岁"] == 20
    assert n["行年"] == "酉" and n["行年干支"] == "乙酉"
    # 女行年按规则（壬申逆数）为癸丑；教程例记「己丑」与规则不符，采规则（登记判据总表）
    n2 = _nianming("丙子", "女", "乙未")
    assert n2["本命"] == "子" and n2["虚岁"] == 20
    assert n2["行年"] == "丑" and n2["行年干支"] == "癸丑"


# ---------------- 十四、年命类课体（三阴/富贵/繁昌/荣华/德庆/合欢/刑伤） ----------------

def test_fujia_nianming_sanyin():
    # 三阴（课经 L9636 书例同构：正月癸丑日卯时子将，申命行年丑）：
    # 天乙巳乘申逆行，日辰天盘落宫辰在天乙后（顺距离8），戌乘白虎加癸为用（戌土寅月死），
    # 卯时木克行年丑土。
    from daliuren import tianpan, fujia_keti
    from datetime import datetime
    tp = tianpan("子", "卯")
    assert tp["申"] == "巳" and tp["丑"] == "戌"  # 天乙巳加申；戌加癸（寄丑）为用
    out = fujia_keti("癸", "丑", tp, ["戌", "未", "辰"], "卯", {"戌": "白虎"},
                     dt=datetime(2024, 2, 15, 6, 0), yue_jiang="子",
                     nianming={"本命": "申", "行年": "丑"})
    names = [x["课体"] for x in out]
    assert "三阴" in names
    assert any(x["课体"] == "三阴" and "群阴当恶" in x["判语"] for x in out)


def test_fujia_nianming_fugui():
    # 富贵（课经 L7016 例同构：二月辛巳日丑时戌将，寅命行年巳）：天乙寅临行年巳，
    # 寅木卯月旺、木火相生，寅为初传。
    from daliuren import tianpan, fujia_keti
    from datetime import datetime
    tp = tianpan("戌", "丑")
    assert tp["巳"] == "寅"  # 寅加巳（行年）发用
    out = fujia_keti("辛", "巳", tp, ["寅", "亥", "申"], "丑",
                     {"寅": "螣蛇", "亥": "螣蛇"},
                     dt=datetime(2024, 3, 10, 2, 0), yue_jiang="戌",
                     nianming={"本命": "寅", "行年": "巳"})
    names = [x["课体"] for x in out]
    assert "富贵" in names
    assert any(x["课体"] == "富贵" and "金玉满堂" in x["判语"] for x in out)


def test_fujia_nianming_ronghua():
    # 荣华（课经 L7432 例同构：丙申日卯时子将，寅命行年巳）：干上寅马、支上巳禄、
    # 本命寅上亥贵、行年巳上寅马，初传巳（禄）卯月相气，寅乘六合吉将。
    from daliuren import tianpan, fujia_keti
    from datetime import datetime
    tp = tianpan("子", "卯")
    assert tp["巳"] == "寅" and tp["申"] == "巳" and tp["寅"] == "亥"
    out = fujia_keti("丙", "申", tp, ["巳", "寅", "亥"], "卯",
                     {"寅": "六合", "巳": "天空", "亥": "贵人"},
                     dt=datetime(2024, 3, 10, 6, 0), yue_jiang="子",
                     nianming={"本命": "寅", "行年": "巳"})
    names = [x["课体"] for x in out]
    assert "荣华" in names
    assert any(x["课体"] == "荣华" and "士众拥从" in x["判语"] for x in out)


def test_fujia_nianming_deqing():
    # 德庆（课经 L7486 例同构：戊子日戌时卯将）：戊德巳加子为用（发用），
    # 行年子上神巳（德）乘太阴吉将。
    from daliuren import tianpan, fujia_keti
    from datetime import datetime
    tp = tianpan("卯", "戌")
    assert tp["子"] == "巳"  # 巳（戊德）加子发用
    out = fujia_keti("戊", "子", tp, ["巳", "戌", "卯"], "戌", {"巳": "太阴"},
                     dt=datetime(2024, 10, 15, 20, 0), yue_jiang="卯",
                     nianming={"本命": "丑", "行年": "子"})
    names = [x["课体"] for x in out]
    assert "德庆" in names
    assert any(x["课体"] == "德庆" and "君子欢会" in x["判语"] for x in out)


def test_fujia_nianming_hehuan():
    # 合欢（课经 L7516 例同构：戊申日子时申将，亥命行年辰）：干上丑遁癸与戊作合，
    # 支申与三传子申辰成三合，亥命上未乘贵人、行年辰上子乘青龙。
    from daliuren import tianpan, fujia_keti
    from datetime import datetime
    tp = tianpan("申", "子")
    assert tp["巳"] == "丑" and tp["亥"] == "未" and tp["辰"] == "子"
    out = fujia_keti("戊", "申", tp, ["子", "申", "辰"], "子",
                     {"子": "青龙", "未": "贵人"},
                     dt=datetime(2024, 6, 10, 0, 0), yue_jiang="申",
                     nianming={"本命": "亥", "行年": "辰"})
    names = [x["课体"] for x in out]
    assert "合欢" in names
    assert any(x["课体"] == "合欢" and "婚姻团圆" in x["判语"] for x in out)


def test_fujia_nianming_xingshang():
    # 刑伤（课经 L8968 例同构：庚午日寅时子将）：午为支刑临日发用，行年申上神午＝刑。
    from daliuren import tianpan, fujia_keti
    from datetime import datetime
    tp = tianpan("子", "寅")
    assert tp["申"] == "午"  # 午（支刑）加庚（寄申）为用
    out = fujia_keti("庚", "午", tp, ["午", "辰", "寅"], "寅",
                     {"午": "螣蛇", "辰": "六合", "寅": "青龙"},
                     dt=datetime(2024, 1, 25, 4, 0), yue_jiang="子",
                     nianming={"本命": "寅", "行年": "申"})
    names = [x["课体"] for x in out]
    assert "刑伤" in names
    assert any(x["课体"] == "刑伤" and "大小不和" in x["判语"] for x in out)


def test_fujia_nianming_fanchang():
    # 繁昌（课经 L7322 例同构：壬申日未时巳将）：夫行年甲寅（命子，寅上见子水木相生）、
    # 妻行年己亥（命酉，亥上见酉金水相宜），甲己合、寅亥合，行年寅入传。
    from daliuren import tianpan, fujia_keti
    from datetime import datetime
    tp = tianpan("巳", "未")
    assert tp["寅"] == "子" and tp["亥"] == "酉"
    out = fujia_keti("壬", "申", tp, ["午", "辰", "寅"], "未",
                     {"午": "天后", "辰": "螣蛇", "寅": "六合"},
                     dt=datetime(2024, 9, 10, 14, 0), yue_jiang="巳",
                     nianming={"本命": "子", "行年": "寅", "行年干支": "甲寅", "性别": "男"},
                     nianming2={"本命": "酉", "行年": "亥", "行年干支": "己亥", "性别": "女"})
    names = [x["课体"] for x in out]
    assert "繁昌" in names
    assert any(x["课体"] == "繁昌" and "男女交感" in x["判语"] for x in out)


# ---------------- 十五、毕法赋一百法（机械可判定子集） ----------------

def _mk_tp(pairs):
    """构造全天盘双射（12 支各落一宫）：pairs 指定 天盘支→地盘宫，通过换位保持双射。"""
    from daliuren import ZHI
    tp = {z: z for z in ZHI}
    for k, v in pairs.items():
        if tp[k] == v:
            continue
        w = next(x for x, y in tp.items() if y == v)
        tp[w] = tp[k]
        tp[k] = v
    return tp


def _bifa_names(day_gan, day_zhi, tp, chuan, tianj, keti="", dt=None, yue_jiang="", shi="午"):
    from daliuren import bifa
    return [x["名"] for x in bifa(day_gan, day_zhi, tp, chuan, shi, tianj, keti, dt, yue_jiang)]


def test_bifa_shouwei():
    # 第二法：乙未日（甲午旬，旬尾卯）干上卯、支上午（旬首）
    tp = _mk_tp({"卯": "辰", "午": "未"})  # 乙寄辰：干上卯；支未上神午
    names = _bifa_names("乙", "未", tp, ["子", "丑", "寅"], {})
    assert "首尾相见始终宜" in names


def test_bifa_lu():
    # 第七法（乙禄卯临干上）、第八法（禄临支）
    tp = _mk_tp({"卯": "辰"})
    assert "旺禄临身徒妄作" in _bifa_names("乙", "未", tp, ["子", "丑", "寅"], {})
    tp2 = _mk_tp({"卯": "未"})
    assert "权摄不正禄临支" in _bifa_names("乙", "未", tp2, ["子", "丑", "寅"], {})


def test_bifa_liuyang_liuyin():
    # 第五法：四课上神与三传皆阳支（例庚子日「四课三传皆居六阳之位」同构）
    tp = _mk_tp({"子": "辰", "寅": "子", "午": "未", "申": "午"})  # 乙寄辰
    names = _bifa_names("乙", "未", tp, ["辰", "申", "戌"], {})
    assert "六阳数足须公用" in names
    # 第六法：皆阴支
    tp2 = _mk_tp({"丑": "辰", "卯": "丑", "酉": "未", "亥": "酉"})
    names2 = _bifa_names("乙", "未", tp2, ["巳", "亥", "丑"], {})
    assert "六阴相继尽昏迷" in names2


def test_bifa_jiaoche():
    # 第二十一法：乙寄辰，六合辰=酉（支上）；未支六合=午（干上）
    tp = _mk_tp({"酉": "未", "午": "辰"})
    names = _bifa_names("乙", "未", tp, ["子", "丑", "寅"], {})
    assert "交车相合交关利" in names


def test_bifa_disheng():
    # 第三十一法：三传丑（土）申（金）子（水），土生金、金生水、水生乙木
    tp = _mk_tp({})
    names = _bifa_names("乙", "未", tp, ["丑", "申", "子"], {})
    assert "三传递生人举荐" in names


def test_bifa_zhichuangan():
    # 第二十三法：初传=支上神、末传=干上神（乙寄辰）
    tp = _mk_tp({"卯": "辰", "午": "未"})
    names = _bifa_names("乙", "未", tp, ["午", "子", "卯"], {})
    assert "彼求我事支传干" in names


def test_bifa_jiake():
    # 第八十五法：初传子坐辰（土克水）又被天空（土）所克
    tp = _mk_tp({"子": "辰"})
    names = _bifa_names("乙", "未", tp, ["子", "丑", "寅"], {"子": "天空"})
    assert "初遭夹克不由己" in names


def test_bifa_huguigan():
    # 第九十一法：乙木日干上酉（金鬼）乘白虎
    tp = _mk_tp({"酉": "辰"})
    names = _bifa_names("乙", "未", tp, ["子", "丑", "寅"], {"酉": "白虎"})
    assert "虎临干鬼凶速速" in names


def test_bifa_laiqu_jukong():
    # 第九十法：返吟课三传皆旬空（乙丑日甲子旬空戌亥）
    tp = _mk_tp({})
    names = _bifa_names("乙", "丑", tp, ["戌", "亥", "戌"], {}, keti="返吟·无依")
    assert "来去俱空岂动宜" in names


def test_bifa_renxin_dingma():
    # 第八十九法：伏吟（自信）课三传见旬丁（乙丑日甲子旬，丁卯=卯）
    tp = _mk_tp({})
    names = _bifa_names("乙", "丑", tp, ["卯", "子", "寅"], {}, keti="自信")
    assert "任信丁马须言动" in names


def test_bifa_bingfu():
    # 第七十一法：2024（甲辰年）病符卯临支未克支（卯木克未土）
    from datetime import datetime
    tp = _mk_tp({"卯": "未"})
    names = _bifa_names("乙", "未", tp, ["子", "丑", "寅"], {}, dt=datetime(2024, 6, 10))
    assert "病符克宅全家患" in names


def test_bifa_sangdiao():
    # 第七十二法：甲辰年丧门午、吊客寅；干上寅、支上神午
    from datetime import datetime
    tp = _mk_tp({"寅": "辰", "午": "未"})
    names = _bifa_names("乙", "未", tp, ["子", "丑", "寅"], {}, dt=datetime(2024, 6, 10))
    assert "丧吊全逢挂缟衣" in names


def test_bifa_luowang():
    # 第五十五法：乙寄辰，干上巳（前一辰）；支未上申（前一辰）
    tp = _mk_tp({"巳": "辰", "申": "未"})
    names = _bifa_names("乙", "未", tp, ["子", "丑", "寅"], {})
    assert "所谋多拙逢罗网" in names


def test_bifa_sanqi():
    # 第四十二法：己卯日（甲戌旬）三传亥子丑遁干乙丙丁
    tp = _mk_tp({})
    names = _bifa_names("己", "卯", tp, ["亥", "子", "丑"], {})
    assert "尊崇传内遇三奇" in names


def test_bifa_youshiwuzhong():
    # 第三十三法：乙木长生午、墓戌，初午末戌
    tp = _mk_tp({})
    names = _bifa_names("乙", "未", tp, ["午", "申", "戌"], {})
    assert "有始无终难变易" in names


def test_bifa_taiyangzhaowu():
    # 第三十九法：玄武乘月将（亥）
    tp = _mk_tp({})
    names = _bifa_names("乙", "未", tp, ["子", "丑", "寅"], {"亥": "玄武"}, yue_jiang="亥")
    assert "太阳照武宜擒贼" in names


def test_bifa_hukeshen_bingzheng():
    # 第六十七法：白虎乘午（火）→ 肺经受病
    from daliuren import bifa
    tp = _mk_tp({})
    got = bifa("乙", "未", tp, ["子", "丑", "寅"], "午", {"午": "白虎"}, "", None, "")
    assert any(x["名"] == "受虎克神为病症" and "肺经受病" in x["判语"] for x in got)


def test_bifa_endpoint():
    # 接口返回毕法条目（书例时刻 2005-08-09 12:00 乙丑日）
    from fastapi.testclient import TestClient
    from main import app
    c = TestClient(app)
    r = c.post("/api/daliuren", json={"dt": "2005-08-09 12:00"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d["毕法"], list)
    for x in d["毕法"]:
        assert x["法"] and x["名"] and x["判语"]


# ---------------- 十六、月宿推步与二烦/天寇课 ----------------

def test_yuesu_book_examples():
    # 月宿推步（课经二烦课条 L9024/L9126/L9130/L9136）
    from daliuren import yue_su
    from datetime import datetime
    # 2024-02-10 农历正月初一（起室）。按重留规则：初五＝娄（戌宫）。
    # L9126 正月例作「五日胃」（跳娄）、「十五张」——该例自身计数不贯；
    # 二月例 L9410「初一奎初二奎初三娄初四胃初五昴」、八月例 L9402「初三氐初四氐初五房」
    # 与「重留一日＝该宿占两日、次宿不跳」自洽，采规则（登记判据总表）。
    y5 = yue_su(datetime(2024, 2, 14))
    assert y5["宿"] == "娄" and y5["宫"] == "戌"
    # 正月十三＝鬼、十四＝柳、十五＝星（依规则）
    assert yue_su(datetime(2024, 2, 22))["宿"] == "鬼"
    assert yue_su(datetime(2024, 2, 23))["宿"] == "柳"
    assert yue_su(datetime(2024, 2, 24))["宿"] == "星"
    # 2024-03-10 农历二月初一（起奎）：二月初五＝昴（酉宫）——天寇课条 L9410「从奎数至昴为初五」
    y5b = yue_su(datetime(2024, 3, 14))
    assert y5b["宿"] == "昴" and y5b["宫"] == "酉"
    # 2024-09-03 农历八月初一（起角）：八月初五＝房（卯宫）——L9402「初五房」
    y5c = yue_su(datetime(2024, 9, 7))
    assert y5c["宿"] == "房" and y5c["宫"] == "卯"
    # 三月十五＝轸（巳宫）（2024-04-09 农历三月初一）
    assert yue_su(datetime(2024, 4, 23))["宿"] == "轸"


def test_fujia_erfan_tianfan():
    # 天烦（课经 L9054 例同构：三月十五己卯日子时酉将，日宿酉临子为仲，罡下系未；
    # 月宿轸居巳宫不临仲，故为天烦非二烦）
    from daliuren import fujia_keti
    from datetime import datetime
    tp = _mk_tp({"酉": "子", "辰": "未"})
    out = fujia_keti("己", "卯", tp, ["酉", "丑", "巳"], "子", {},
                     dt=datetime(2024, 4, 23, 0, 0), yue_jiang="酉")
    names = [x["课体"] for x in out]
    assert "天烦" in names and "二烦" not in names
    assert any(x["课体"] == "天烦" and "男子犯法" in x["判语"] for x in out)


def test_fujia_erfan_difan():
    # 地烦（课经 L9132「遇本日星发用者是地烦」）：八月初五房（卯宫）临午为仲，罡系未，卯发用
    from daliuren import fujia_keti
    from datetime import datetime
    tp = _mk_tp({"卯": "午", "辰": "未"})
    out = fujia_keti("丁", "酉", tp, ["卯", "丑", "巳"], "酉", {},
                     dt=datetime(2024, 9, 7, 18, 0), yue_jiang="巳")
    names = [x["课体"] for x in out]
    assert "地烦" in names
    assert any(x["课体"] == "地烦" and "女子受灾" in x["判语"] for x in out)


def test_fujia_erfan_erfan():
    # 二烦（课经 L9028 例同构：九月初三丙午日午时卯将，日月宿俱值卯宫加午为仲，罡临未。
    # 例文记月宿躔氐五度（七政历细度口径），整宿计数初三为房——同为卯宫，宫位一致）
    from daliuren import fujia_keti, yue_su
    from datetime import datetime
    dt = datetime(2024, 10, 5, 12, 0)  # 农历九月初三
    assert yue_su(dt)["宫"] == "卯"
    tp = _mk_tp({"卯": "午", "辰": "未"})
    out = fujia_keti("丙", "午", tp, ["卯", "丑", "巳"], "午", {},
                     dt=dt, yue_jiang="卯")
    names = [x["课体"] for x in out]
    assert "二烦" in names


def test_fujia_erfan_duchuan():
    # 杜传（二烦）（课经 L9092：日月宿临仲，斗不系丑未，又名杜传）
    from daliuren import fujia_keti
    from datetime import datetime
    tp = _mk_tp({"卯": "午", "辰": "申"})
    out = fujia_keti("丙", "午", tp, ["卯", "丑", "巳"], "午", {},
                     dt=datetime(2024, 10, 5, 12, 0), yue_jiang="卯")
    names = [x["课体"] for x in out]
    assert "杜传（二烦）" in names


def test_fujia_tiankou():
    # 天寇（课经 L9374：四离日＝二分二至前一日，月宿加离辰）
    # 2024-03-19 为春分（03-20）前一日壬午日，离辰午；农历二月初十月宿井（未宫），未加午
    from daliuren import fujia_keti, yue_su
    from datetime import datetime
    dt = datetime(2024, 3, 19, 12, 0)
    assert yue_su(dt)["宫"] == "未"
    tp = _mk_tp({"未": "午"})
    out = fujia_keti("壬", "午", tp, ["子", "丑", "寅"], "午", {},
                     dt=dt, yue_jiang="戌")
    names = [x["课体"] for x in out]
    assert "天寇" in names
    assert any(x["课体"] == "天寇" and "时势多艰" in x["判语"] for x in out)
