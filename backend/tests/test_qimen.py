# -*- coding: utf-8 -*-
"""奇门遁甲起局引擎回归测试。

夹具来源（books/qimendunjia/，行号为当前行号）：
- 转盘阳6局：启悟 L631–635「壬午年甲辰月乙巳日庚辰时，阳遁6局」完整成图。
- 转盘阴2局：启悟 L684–690「乙酉年甲申月乙丑日壬午时，阴遁2局」完整成图。
- 飞盘阳1局：启悟 L732–778「丙戌年庚子月丙戌日丙申时，阳一局」成图（星门神三表）。
- 飞盘阴4局：启悟 L790–826「丙戌年乙未月癸亥日丁巳时，阴四局」完整成图。
- 拆补法：法窍 L953 丙申年立春实例的结构（交节丙子日丑正一刻，甲戌下局符头统领残局
  即用立春下局、己卯起立春上局、甲申中局、己丑下局补至雨水交节）+ L3297 交节换局口径。
- 局数表：启悟歌诀 L445–467 与秘笈大全歌诀 L239–253 逐字一致。
- 三元符头：启悟 L519–525（上元符头甲子/甲午/己卯/己酉，中元甲寅/甲申/己巳/己亥，
  下元甲辰/甲戌/己丑/己未）。

注：启悟各例的「局数」是他自用定局法（置闰/茅山）所得；本站定局用拆补法（站长裁定），
故本测试把定局与排盘分两层：排盘层以书例局数直接进盘（逐宫对照成图），
定局层以拆补法规则与法窍实例结构验证。
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qimen import (JU_TABLE, YANGDUN, JIEQI_ORDER, GZ60, FU_TOU_SETS, ZHI_YUAN,
                   dipan, shichen_gz, xunshou, dingju, qimen,
                   qipan_zhuanpan, qipan_feipan)

# ---------------- 一、局数表与符头规则（逐字回源） ----------------

# 启悟歌诀 L445–467（与秘笈大全 L239–253 逐字一致）转录
BOOK_JU = {
    "冬至": (1, 7, 4), "小寒": (2, 8, 5), "大寒": (3, 9, 6),
    "立春": (8, 5, 2), "雨水": (9, 6, 3), "惊蛰": (1, 7, 4),
    "春分": (3, 9, 6), "清明": (4, 1, 7), "谷雨": (5, 2, 8),
    "立夏": (4, 1, 7), "小满": (5, 2, 8), "芒种": (6, 3, 9),
    "夏至": (9, 3, 6), "小暑": (8, 2, 5), "大暑": (7, 1, 4),
    "立秋": (2, 5, 8), "处暑": (1, 4, 7), "白露": (9, 3, 6),
    "秋分": (7, 1, 4), "寒露": (6, 9, 3), "霜降": (5, 8, 2),
    "立冬": (6, 9, 3), "小雪": (5, 8, 2), "大雪": (4, 7, 1),
}


def test_ju_table_verbatim():
    assert JU_TABLE == BOOK_JU
    assert set(JU_TABLE) == set(JIEQI_ORDER)
    assert len(JIEQI_ORDER) == 24
    # 阳遁＝冬至至芒种十二节气（启悟 L477：冬至起阳遁至夏至止）
    assert YANGDUN == set(JIEQI_ORDER[:12])


def test_futou_sets_verbatim():
    # 启悟 L525：上元符头甲子、甲午、己卯、己酉；中元甲寅、甲申、己巳、己亥；
    # 下元甲辰、甲戌、己丑、己未
    assert FU_TOU_SETS == {
        "上元": {"甲子", "甲午", "己卯", "己酉"},
        "中元": {"甲寅", "甲申", "己巳", "己亥"},
        "下元": {"甲辰", "甲戌", "己丑", "己未"},
    }


def test_yuan_by_futou_branch():
    # 六十甲子每五日一元：符头日支定元（子午卯酉上、寅申巳亥中、辰戌丑未下）。
    # 注意：支-元对应只约束每元第一天（符头），元内第2~5天的地支不参与定元。
    for idx, gz in enumerate(GZ60):
        futou = GZ60[idx - idx % 5]
        yuan = (idx // 5) % 3
        assert futou[0] in "甲己"
        assert ZHI_YUAN[futou[1]] == yuan
        if idx % 5 == 0:
            assert ZHI_YUAN[gz[1]] == yuan


def test_shichen_wuziyuandun():
    # 五子元遁：甲己日起甲子、乙庚丙子、丙辛戊子、丁壬庚子、戊癸壬子（法窍 L3642）
    cases = {
        ("甲子", 0): "甲子", ("己丑", 1): "乙丑", ("乙巳", 7): "庚辰",
        ("乙丑", 11): "壬午", ("丙戌", 15): "丙申", ("癸亥", 9): "丁巳",
        ("戊戌", 23): "壬子",
    }
    for (dg, h), want in cases.items():
        assert shichen_gz(dg, h) == want, (dg, h)


def test_xunshou_liujia_dunyi():
    # 六甲遁仪：甲子同戊、甲戌同己、甲申同庚、甲午同辛、甲辰同壬、甲寅同癸
    assert xunshou("庚辰") == ("甲戌", "己")
    assert xunshou("壬午") == ("甲戌", "己")
    assert xunshou("丙申") == ("甲午", "辛")
    assert xunshou("丁巳") == ("甲寅", "癸")
    assert xunshou("壬子") == ("甲辰", "壬")
    assert xunshou("甲子") == ("甲子", "戊")


# ---------------- 二、地盘（阳顺阴逆布三奇六仪） ----------------

def test_dipan_yang6():
    # 启悟 L595：阳遁6局，戊排乾6、己兑7、庚艮8、辛离9、壬坎1、癸坤2、丁震3、丙巽4、乙中5
    d = dipan(6, "阳遁")
    assert d == {6: "戊", 7: "己", 8: "庚", 9: "辛", 1: "壬", 2: "癸",
                 3: "丁", 4: "丙", 5: "乙"}


def test_dipan_yin2():
    # 启悟 L652：阴遁2局，戊坤2、己坎1、庚离9、辛艮8、壬兑7、癸乾6、丁中5、丙巽4、乙震3
    d = dipan(2, "阴遁")
    assert d == {2: "戊", 1: "己", 9: "庚", 8: "辛", 7: "壬", 6: "癸",
                 5: "丁", 4: "丙", 3: "乙"}


# ---------------- 三、转盘排盘（书例成图逐宫对照） ----------------

def _cells(r):
    return {p: c for p, c in r["九宫"].items()}


def test_zhuanpan_yang6_book_chart():
    # 启悟 L631–635 完整成图
    r = qipan_zhuanpan(6, "阳遁", "乙巳", "庚辰")
    assert r["值符"] == "天柱" and r["值使"] == "惊"
    b = _cells(r)
    want = {
        4: ("丙", ["天蓬"], ["壬"], "惊", "太阴"),
        9: ("辛", ["天任"], ["庚"], "开", "六合"),
        2: ("癸", ["天冲"], ["丁"], "休", "白虎"),
        3: ("丁", ["天心"], ["戊"], "死", "螣蛇"),
        5: ("乙", [], [], None, None),
        7: ("己", ["天辅"], ["丙"], "生", "玄武"),
        8: ("庚", ["天柱"], ["己"], "景", "值符"),
        1: ("壬", ["天芮", "天禽"], ["癸", "乙"], "杜", "九天"),
        6: ("戊", ["天英"], ["辛"], "伤", "九地"),
    }
    for p, (dp, star, tp, men, shen) in want.items():
        c = b[p]
        assert c["地盘"] == dp, p
        assert c["星"] == star, p
        assert c["天盘"] == tp, p
        assert c["门"] == men, p
        assert c["神"] == shen, p


def test_zhuanpan_yin2_book_chart():
    # 启悟 L684–690 完整成图
    r = qipan_zhuanpan(2, "阴遁", "乙丑", "壬午")
    assert r["值符"] == "天蓬" and r["值使"] == "休"
    b = _cells(r)
    want = {
        4: ("丙", ["天芮", "天禽"], ["戊", "丁"], "惊", "六合"),
        9: ("庚", ["天柱"], ["壬"], "开", "太阴"),
        2: ("戊", ["天心"], ["癸"], "休", "螣蛇"),
        3: ("乙", ["天英"], ["庚"], "死", "白虎"),
        5: ("丁", [], [], None, None),
        7: ("壬", ["天蓬"], ["己"], "生", "值符"),
        8: ("辛", ["天辅"], ["丙"], "景", "玄武"),
        1: ("己", ["天冲"], ["乙"], "杜", "九地"),
        6: ("癸", ["天任"], ["辛"], "伤", "九天"),
    }
    for p, (dp, star, tp, men, shen) in want.items():
        c = b[p]
        assert c["地盘"] == dp, p
        assert c["星"] == star, p
        assert c["天盘"] == tp, p
        assert c["门"] == men, p
        assert c["神"] == shen, p


# ---------------- 四、飞盘排盘（书例成图逐宫对照） ----------------

def test_feipan_yang1_book_chart():
    # 启悟 L750（星盘）/L764（门盘）/L774（神盘）合成成图
    r = qipan_feipan(1, "阳遁", "丙戌", "丙申")
    assert r["值符"] == "天辅" and r["值使"] == "杜"
    b = _cells(r)
    want = {
        4: ("辛", ["天英"], ["乙"], "伤", "太常"),
        9: ("乙", ["天禽"], ["壬"], "生", "螣蛇"),
        2: ("己", ["天柱"], ["丁"], "休", "六合"),
        3: ("庚", ["天任"], ["丙"], "死", "勾陈"),
        5: ("壬", ["天蓬"], ["戊"], None, "朱雀"),
        7: ("丁", ["天冲"], ["庚"], "开", "九天"),
        8: ("丙", ["天辅"], ["辛"], "惊", "值符"),
        1: ("戊", ["天心"], ["癸"], "景", "太阴"),
        6: ("癸", ["天芮"], ["己"], "杜", "九地"),
    }
    for p, (dp, star, tp, men, shen) in want.items():
        c = b[p]
        assert c["地盘"] == dp, p
        assert c["星"] == star, p
        assert c["天盘"] == tp, p
        assert c["门"] == men, p
        assert c["神"] == shen, p


def test_feipan_yin4_book_chart():
    # 启悟 L826 完整成图（值使生门落中五寄坤二）
    r = qipan_feipan(4, "阴遁", "癸亥", "丁巳")
    assert r["值符"] == "天任" and r["值使"] == "生"
    b = _cells(r)
    want = {
        4: ("戊", ["天芮"], ["庚"], "开", "六合"),
        9: ("壬", ["天心"], ["丙"], "休", "九地"),
        2: ("庚", ["天辅"], ["戊"], "生", "太常"),
        3: ("己", ["天冲"], ["己"], "惊", "白虎"),
        5: ("乙", ["天蓬"], ["辛"], None, "太阴"),
        7: ("丁", ["天任"], ["癸"], "伤", "值符"),
        8: ("癸", ["天柱"], ["丁"], "死", "九天"),
        1: ("辛", ["天禽"], ["乙"], "景", "玄武"),
        6: ("丙", ["天英"], ["壬"], "杜", "螣蛇"),
    }
    for p, (dp, star, tp, men, shen) in want.items():
        c = b[p]
        assert c["地盘"] == dp, p
        assert c["星"] == star, p
        assert c["天盘"] == tp, p
        assert c["门"] == men, p
        assert c["神"] == shen, p


# ---------------- 五、拆补法定局 ----------------

def _find_day(year, target_gz):
    """在 year 年内找干支日为 target_gz 的日期（lunar_python 独立查）。"""
    from lunar_python import Solar
    d = datetime(year, 1, 1, 12, 0)
    for _ in range(370):
        if Solar.fromYmdHms(d.year, d.month, d.day, 12, 0, 0).getLunar().getDayInGanZhi() == target_gz:
            return d
        d += timedelta(days=1)
    raise AssertionError(f"{year} 年内找不到 {target_gz} 日")


def test_dingju_chaibu_faqiao_scenario():
    """法窍 L953 拆补结构：交节丙子日丑正一刻，甲戌下局符头统领残局即用立春下局，
    己卯起立春上局、甲申中局、己丑下局补至雨水交节（L3297 口径同）。

    用真实连续干支日（甲戌起）＋注入合成交节时刻，隔离验证拆补规则本身。
    """
    d0 = _find_day(2024, "甲戌")  # 甲戌
    def day(n, h=12, mi=0):
        return datetime(d0.year, d0.month, d0.day, h, mi) + timedelta(days=n)
    jieqi = [("大寒", day(0, 0, 0)), ("立春", day(2, 2, 15)), ("雨水", day(17, 7, 15))]
    cases = [
        # (时刻, 节气, 阴阳遁, 元, 局数, 说明)
        (day(2, 1, 0), "大寒", "阳遁", "下元", 6, "立春交节前仍属大寒"),
        (day(2, 12, 0), "立春", "阳遁", "下元", 2, "法窍：甲戌下局符头统领之残局即用立春下局"),
        (day(5, 12, 0), "立春", "阳遁", "上元", 8, "己卯符头起立春上局"),
        (day(10, 12, 0), "立春", "阳遁", "中元", 5, "甲申符头立春中局"),
        (day(15, 12, 0), "立春", "阳遁", "下元", 2, "己丑符头立春下局"),
        (day(17, 5, 0), "立春", "阳遁", "下元", 2, "补局：雨水交节前仍用立春下局"),
        (day(17, 12, 0), "雨水", "阳遁", "下元", 3, "雨水交节后换雨水下局"),
    ]
    for dt, jq, yy, yuan, ju, note in cases:
        d = dingju(dt, _jieqi=jieqi)
        assert (d["节气"], d["阴阳遁"], d["元"], d["局数"]) == (jq, yy, yuan, ju), (dt, note, d)
    # 丙子日午时＝甲午时（丙日起戊子）
    assert dingju(day(2, 12, 0), _jieqi=jieqi)["时干支"] == "甲午"
    # 交节时刻字段
    d = dingju(day(2, 12, 0), _jieqi=jieqi)
    assert d["交节时刻"] == "2024-02-12 02:15:00".replace("2024-02-12", day(2).strftime("%Y-%m-%d"))


def test_dingju_real_dates():
    """真实日期定局（lunar_python 交节时刻，逐条手推核对）。"""
    cases = [
        # 与启悟书例全链一致的两条（定局结果＝书例局数）：
        (datetime(2005, 8, 9, 12, 0), "立秋", "阴遁", "上元", 2, "甲子", "乙丑", "壬午"),
        (datetime(2006, 8, 2, 10, 0), "大暑", "阴遁", "下元", 4, "己未", "癸亥", "丁巳"),
        # 交节时刻分界（2024 立春 02-04 16:27:07）：
        (datetime(2024, 2, 4, 12, 0), "大寒", "阳遁", "上元", 3, "甲午", "戊戌", "戊午"),
        (datetime(2024, 2, 4, 17, 0), "立春", "阳遁", "上元", 8, "甲午", "戊戌", "辛酉"),
        # 阴阳遁分界（冬至起阳、夏至起阴）：
        (datetime(2023, 12, 23, 10, 0), "冬至", "阳遁", "中元", 7, "甲寅", "乙卯", "辛巳"),
        (datetime(2023, 6, 22, 10, 0), "夏至", "阴遁", "上元", 9, "己酉", "辛亥", "癸巳"),
        # 拆补与启悟置闰标注不同的一条（登记判据总表）：
        (datetime(2002, 4, 7, 8, 0), "清明", "阳遁", "下元", 7, "甲辰", "乙巳", "庚辰"),
    ]
    for dt, jq, yy, yuan, ju, futou, dgz, sgz in cases:
        d = dingju(dt)
        assert (d["节气"], d["阴阳遁"], d["元"], d["局数"]) == (jq, yy, yuan, ju), (dt, d)
        assert d["符头"] == futou and d["日干支"] == dgz and d["时干支"] == sgz, (dt, d)


def test_qimen_full_chain_book_examples():
    """定局+排盘全链：定局得出的局数与书例一致时，排出的盘必须等于书例成图。"""
    # 启悟阴2局例（2005-08-09 12:00）：拆补定局=立秋上元阴遁2局＝书例局数
    q = qimen(datetime(2005, 8, 9, 12, 0), pan="转盘")
    assert q["定局"]["局数"] == 2 and q["定局"]["阴阳遁"] == "阴遁"
    assert q["转盘"]["值符"] == "天蓬" and q["转盘"]["值使"] == "休"
    assert _cells(q["转盘"])[4] == {"宫": 4, "地盘": "丙", "星": ["天芮", "天禽"],
                                    "天盘": ["戊", "丁"], "门": "惊", "神": "六合"}
    # 启悟阴4局例（2006-08-02 10:00）：拆补定局=大暑下元阴遁4局＝书例局数
    q = qimen(datetime(2006, 8, 2, 10, 0), pan="飞盘")
    assert q["定局"]["局数"] == 4 and q["定局"]["阴阳遁"] == "阴遁"
    assert q["飞盘"]["值符"] == "天任" and q["飞盘"]["值使"] == "生"
    assert _cells(q["飞盘"])[2]["门"] == "生" and _cells(q["飞盘"])[2]["星"] == ["天辅"]


# ---------------- 六、边界：值符禽（甲辰壬落中五）与时干落中五 ----------------

def test_zhifu_qin_mid5_zhuanpan():
    # 阳1局壬子时：甲辰壬落中五→值符天禽、值使寄坤二之门（死门）；
    # 时干壬亦落中五→值符星按寄坤二口径落坤二（判据总表第五节登记）。
    # 壬子为甲辰旬第8个时辰，值使自中五起顺数8步至巽4。
    r = qipan_zhuanpan(1, "阳遁", "戊戌", "壬子")
    assert r["值符"] == "天禽" and r["值使"] == "死"
    b = _cells(r)
    assert b[2]["星"] == ["天芮", "天禽"] and b[2]["天盘"] == ["己", "壬"]
    assert b[5]["星"] == [] and b[5]["地盘"] == "壬"
    assert b[2]["神"] == "值符" and b[4]["门"] == "死"


def test_zhifu_qin_mid5_feipan():
    # 飞盘：值符禽飞加时干宫（中五），值使=阳遁寄艮八之门（生门）；
    # 值使自中五起顺数8步至巽4。
    r = qipan_feipan(1, "阳遁", "戊戌", "壬子")
    assert r["值符"] == "天禽" and r["值使"] == "生"
    b = _cells(r)
    assert b[5]["星"] == ["天禽"] and b[5]["天盘"] == ["壬"]
    assert b[4]["门"] == "生" and b[5]["神"] == "值符"


def test_shigan_mid5_zhuanpan_jigong():
    # 阳6局乙丑时（己日乙丑时）：时干乙落中五→值符天心寄坤二
    r = qipan_zhuanpan(6, "阳遁", "己丑", "乙丑")
    b = _cells(r)
    assert b[2]["星"] == ["天心"] and b[2]["天盘"] == ["戊"]
    assert b[2]["神"] == "值符" and b[5]["星"] == []
    # 其余七单元按轮序在环上：天蓬落兑7（环上坤二之后）
    assert b[7]["星"] == ["天蓬"]


# ---------------- 七、起局接口 ----------------

def test_qimen_endpoint():
    from fastapi.testclient import TestClient
    from main import app
    c = TestClient(app)
    # 启悟阴2局书例时刻（2005-08-09 12:00）：拆补定局＝立秋上元阴遁2局，全链与书例一致
    r = c.post("/api/qimen", json={"dt": "2005-08-09 12:00", "pan": "both"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["定局"]["节气"] == "立秋" and d["定局"]["阴阳遁"] == "阴遁"
    assert d["定局"]["元"] == "上元" and d["定局"]["局数"] == 2
    assert d["转盘"]["值符"] == "天蓬" and d["转盘"]["值使"] == "休"
    assert d["飞盘"]["值符"] == "天蓬"
    assert d["转盘"]["九宫"]["4"]["星"] == ["天芮", "天禽"]
    # 格局层随接口返回：门宫生克＋门卦断
    assert d["转盘"]["格局"]["门宫"]["7"]["门卦"] == "损卦"
    assert "书证" in d
    # 缺省时间为现在
    r2 = c.post("/api/qimen", json={})
    assert r2.status_code == 200 and r2.json()["定局"]["节气"]
    # 坏时间格式
    r3 = c.post("/api/qimen", json={"dt": "2024-13-99"})
    assert r3.status_code == 400


# ---------------- 八、格局吉凶与门宫主客（运筹层） ----------------

def test_geju_zhuanpan_yin2_book_case():
    # 启悟阴2局书例盘（2005-08-09 12:00）：逐宫核对格局与门宫生克
    from qimen import qimen
    from datetime import datetime
    r = qimen(datetime(2005, 8, 9, 12, 0))
    g = r["转盘"]["格局"]
    names4 = [x["格"] for x in g["九宫"].get(4, [])]
    # 巽4：天盘戊加地盘丙＝青龙返首；天盘丁加地盘丙＝交泰（法窍吉格注释）
    assert "青龙返首" in names4 and "交泰" in names4
    assert any(x["格"] == "青龙返首" and x["吉凶"] == "吉" for x in g["九宫"][4])
    # 艮8：天盘丙加地盘辛＝奇仪相合（丙辛合）
    assert "奇仪相合" in [x["格"] for x in g["九宫"].get(8, [])]
    # 坎1：天盘乙加地盘己＝三奇得使
    assert "三奇得使" in [x["格"] for x in g["九宫"].get(1, [])]
    # 门宫：兑7 生门（土）生宫（金）＝门生宫·利主；乾6 伤门（木）被宫（金）克＝宫克门·利主
    assert g["门宫"][7]["生克"] == "门生宫（和）" and g["门宫"][7]["主客"] == "利主"
    assert g["门宫"][6]["生克"] == "宫克门（制）" and g["门宫"][6]["主客"] == "利主"
    # 盘级：乙日壬午时（壬生乙，非克）无五不遇；值符蓬落兑7非本位非冲，无伏吟返吟
    assert not any(x["格"] in ("五不遇", "伏吟", "返吟") for x in g["盘级"])


def test_geju_feipan_yang1_fixture():
    # 飞盘阳1局书例盘（丙戌日丙申时）：震3 天盘丙加地盘庚＝荧入太白（凶）
    from qimen import qipan_feipan, pan_geju
    r = qipan_feipan(1, "阳遁", "丙戌", "丙申")
    g = pan_geju(r, {}, None)
    names3 = [x["格"] for x in g["九宫"].get(3, [])]
    assert "荧入太白" in names3
    assert any(x["格"] == "荧入太白" and x["吉凶"] == "凶" for x in g["九宫"][3])


def test_geju_panji_wubuyu():
    # 五不遇：时干克日干（法窍凶格注释）。甲子日庚午时：庚金克甲木
    from qimen import qipan_zhuanpan, pan_geju
    r = qipan_zhuanpan(1, "阳遁", "甲子", "庚午")
    g = pan_geju(r, {}, None)
    assert any(x["格"] == "五不遇" and x["吉凶"] == "凶" for x in g["盘级"])


def test_liujia_shi_shigan_jia():
    # 六甲时（时干甲遁于旬首仪，甲不显于盘）：时干宫＝旬首遁仪宫
    # 阳1局甲子日甲子时：旬首甲子戊在坎1，值符天蓬落坎1
    r = qipan_zhuanpan(1, "阳遁", "甲子", "甲子")
    assert r["值符"] == "天蓬" and r["值使"] == "休"
    assert _cells(r)[1]["星"] == ["天蓬"]
    # 飞盘同样可起
    r2 = qipan_feipan(1, "阳遁", "甲子", "甲子")
    assert r2["值符"] == "天蓬"


# ---------------- 九、门卦断六十四条（法窍 L1398–1528） ----------------

def test_men_gua_duan_complete():
    from qimen import MEN_GUA_DUAN
    # 八门×八宫共六十四条
    assert len(MEN_GUA_DUAN) == 64
    for (men, gong) in MEN_GUA_DUAN:
        assert men in "开休生伤杜景死惊" and gong in (1, 2, 3, 4, 6, 7, 8, 9)
    # 刊误核对：原文讹字已改正（良→艮、责→贲、嚏嗑→噬嗑）
    assert MEN_GUA_DUAN[("生", 8)][0] == "艮卦"
    assert MEN_GUA_DUAN[("生", 9)][0] == "贲卦"
    assert MEN_GUA_DUAN[("景", 3)][0] == "噬嗑"
    # 卦名与断语抽查（逐字源自法窍）
    assert MEN_GUA_DUAN[("开", 6)][0] == "乾卦"
    assert "访道、求贤、积粮、收货" in MEN_GUA_DUAN[("开", 6)][1]
    assert MEN_GUA_DUAN[("休", 9)][0] == "既济"
    assert "散粮、赏赐、放水、开沟" in MEN_GUA_DUAN[("休", 9)][1]
    assert MEN_GUA_DUAN[("惊", 4)][0] == "大过"
    assert MEN_GUA_DUAN[("生", 7)][0] == "损卦"
    assert "贼必求和" in MEN_GUA_DUAN[("生", 7)][1]


def test_men_gua_yin2_book_case():
    # 启悟阴2局书例盘（2005-08-09 12:00）：门卦与门卦断
    from qimen import qimen
    from datetime import datetime
    r = qimen(datetime(2005, 8, 9, 12, 0))
    mg = r["转盘"]["格局"]["门宫"]
    assert mg[7]["门卦"] == "损卦" and mg[4]["门卦"] == "大过"
    assert mg[1]["门卦"] == "涣卦" and mg[9]["门卦"] == "同人"
    assert mg[6]["门卦"] == "大壮" and mg[2]["门卦"] == "比卦"
    assert "出兵利主" in mg[7]["门卦断"]   # 损卦断语（法窍原文）
    assert "战利为客" in mg[4]["门卦断"]    # 大过断语（法窍原文）
    # 飞盘同盘也出卦（门卦断按门+宫，盘式无关）
    mgf = r["飞盘"]["格局"]["门宫"]
    assert mgf[7]["门卦"] == "履卦" and mgf[3]["门卦"] == "噬嗑"


# ---------------- 十、择时择方运筹建议（改运链建议层） ----------------

def test_zeshi_zefang_yin2_book_case():
    # 阴2局书例盘（2005-08-09 12:00）：择时可用；兑7生门（三吉门、方来生我）宜往，
    # 乾6伤门（凶门）宜避、坤2休门但其方克我宜避（启悟出行章口径）。
    from qimen import qimen
    from datetime import datetime
    r = qimen(datetime(2005, 8, 9, 12, 0))
    zz = r["转盘"]["择时择方"]
    assert zz["口径"].startswith("运筹建议")
    assert zz["择时"]["判"] == "本时可用" and zz["择时"]["可用"] is True
    f = zz["择方"]
    assert len(f) == 8
    assert f["7"]["门"] == "生" and f["7"]["门吉凶"] == "吉" and f["7"]["建议"] == "宜往"
    assert f["7"]["方位"] == "西" and f["7"]["日干生克"] == "方来生我，吉"
    assert f["6"]["门"] == "伤" and f["6"]["建议"] == "宜避"
    assert f["2"]["建议"] == "宜避" and f["2"]["日干生克"] == "其方克我，凶"
    assert f["9"]["门"] == "开" and f["9"]["建议"] == "宜往"
    # 飞盘同构输出
    assert len(r["飞盘"]["择时择方"]["择方"]) == 8


def test_zeshi_wubuyu():
    # 择时：五不遇时虽有门奇不宜取用（法窍「选时之法」段）
    from qimen import qipan_zhuanpan, pan_geju, zeshi_zefang
    zp = qipan_zhuanpan(1, "阳遁", "甲子", "庚午")
    zz = zeshi_zefang(zp, pan_geju(zp, {}, None))
    assert zz["择时"]["可用"] is False and "五不遇" in zz["择时"]["判"]
