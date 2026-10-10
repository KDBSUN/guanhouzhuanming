# -*- coding: utf-8 -*-
"""运气模块回归（改运链·天地气背景层）。

钉四件事：①起法表（天元纪大论两条）②六十年气化表**逐字回源**（对库内
《黄帝内经·六元正纪大论》原文，标点与圈码宽容）③规则算出的中运/司天/在泉
与转录表全 60 年一致（规则↔表互证）④六步主气客气客主加临结构。
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yunqi as Y                                                 # noqa: E402
from books_corpus import read_corpus, missing_reason              # noqa: E402


def _norm(s):
    """标点/圈码/空白宽容：只留汉字。"""
    return re.sub(r"[^\u4e00-\u9fff]", "", s or "")


def test_gan_jiyun_and_zhijian_qi_tables():
    """天元纪大论两条起法：甲己之岁土运统之……子午之岁上见少阴……"""
    assert Y.GAN_YUN == {"甲": "土", "乙": "金", "丙": "水", "丁": "木", "戊": "火",
                         "己": "土", "庚": "金", "辛": "水", "壬": "木", "癸": "火"}
    assert Y.SIZAI == {"子午": ("少阴君火", "阳明燥金"), "丑未": ("太阴湿土", "太阳寒水"),
                       "寅申": ("少阳相火", "厥阴风木"), "卯酉": ("阳明燥金", "少阴君火"),
                       "辰戌": ("太阳寒水", "太阴湿土"), "巳亥": ("厥阴风木", "少阳相火")}


def test_tai_shao_by_gan_yinyang():
    assert Y.yunqi("甲子")["中运"] == {"五音": "太宫", "五行": "土", "太过不及": "太过"}
    assert Y.yunqi("丁亥")["中运"] == {"五音": "少角", "五行": "木", "太过不及": "不及"}
    assert Y.yunqi("癸巳")["中运"] == {"五音": "少徵", "五行": "火", "太过不及": "不及"}


def test_liuyuan_zhengji_table_verbatim_from_corpus():
    """六元正纪大论 30 对年的逐年条文必须逐字在库内原文中（标点宽容）。"""
    reason = missing_reason()
    if reason:
        pytest.skip(reason)
    corpus = _norm(read_corpus())
    for p in Y.PAIRS:
        assert _norm(p["yuanwen"]) in corpus, "逐年条文未逐字回源：%s" % p["label"]


def test_rules_match_transcribed_table_all_60_years():
    """起法规则与转录表互证：60 个干支年的中运五音、司天、在泉逐一对上。"""
    assert Y.check_pairs_against_rules() == []


def test_tianfu_suihui_flags():
    assert Y.yunqi("丁亥")["特殊"] == ["天符"]                # 木运+厥阴风木司天
    assert Y.yunqi("乙酉")["特殊"] == ["太乙天符"]            # 金运+阳明司天+酉金支
    f = Y.yunqi("甲辰")["特殊"]
    assert "岁会" in f and "同天符" in f                      # 土运+辰土支；太宫+湿土在泉
    assert Y.yunqi("丙午")["特殊"] == []
    assert Y.yunqi("戊午")["特殊"] == ["太乙天符"]


def test_huashu_and_yaoshiyi_from_table():
    r = Y.yunqi("丁亥")
    assert r["化数"] == {"司天": "风化三", "中运": "风化三", "在泉": "火化七"}
    assert r["药食宜"] == {"上": "辛凉", "中": "辛和", "下": "咸寒"}
    r = Y.yunqi("丙午")
    assert r["化数"] == {"司天": "热化二", "中运": "寒化六", "在泉": "清化四"}
    assert r["药食宜"] == {"上": "咸寒", "中": "咸热", "下": "酸温"}


def test_buqi_structure_jueyin_sitian():
    """丁亥（厥阴风木司天）六步：主气年年不变；客气司天居三之气，
    前后按三阴三阳次序（初之气阳明燥金……终之气少阳相火）。
    厥阴司天之年六步客主皆异气（「春应温而反凉，冬应寒而反热」，讲解本）。"""
    b = Y.buqi("丁亥")
    assert [s["主气"] for s in b] == Y.ZHUQI
    assert [s["客气"] for s in b] == ["阳明燥金", "太阳寒水", "厥阴风木",
                                      "少阴君火", "太阴湿土", "少阳相火"]
    assert all(s["加临"] == "客主异气" for s in b)


def test_buqi_keszhu_tongqi_when_sitian_is_xianghuo():
    """客主同气只出现在司天恰为主气三之气（少阳相火）之年：戊申三之气同气。"""
    b = Y.buqi("戊申")
    assert b[2]["客气"] == "少阳相火" and b[2]["主气"] == "少阳相火"
    assert b[2]["加临"] == "客主同气"


def test_buqi_structure_shaoyin_sitian():
    """庚子（少阴君火司天）六步：初之气太阳寒水，三之气少阴君火。"""
    b = Y.buqi("庚子")
    assert b[0]["客气"] == "太阳寒水"
    assert b[2]["客气"] == "少阴君火"
    assert b[5]["客气"] == "阳明燥金"


def test_year_yunqi_uses_lichun_year():
    assert Y.year_yunqi(2026)["ganzhi"] == "丙午"
    assert Y.year_yunqi(2026)["司天"] == "少阴君火"
    assert Y.year_yunqi(2007)["ganzhi"] == "丁亥"


def test_buqi_notes_and_current_bu():
    b = Y.buqi("丙午", 2026)
    assert b[0]["主气说明"].startswith("大寒至惊蛰")
    assert all(s.get("起日") for s in b)          # 给 year 时六步各有公历起日
    cur = Y.current_bu(2026, 6, 1)                # 小满后 → 三之气
    assert cur["步"] == "三之气" and cur["主气"] == "少阳相火"
    cur = Y.current_bu(2026, 1, 10)               # 早于大寒 → 乙巳年六步的终之气
    assert cur["步"] == "终之气"
    cur = Y.current_bu(2026, 9, 26)               # 秋分后 → 五之气
    assert cur["步"] == "五之气" and cur["主气"] == "阳明燥金"


# ---------- 集成：命局基线 / 排盘端点 / 校验端点 ----------

BIRTH = {"year": 2007, "month": 3, "day": 17, "hour": 6, "minute": 0, "gender": 1,
         "calendar": "solar", "leap_month": False, "dst": False, "true_solar": True,
         "longitude": 113.0174, "latitude": 23.12}


def test_compute_baseline_carries_yunqi_and_dili():
    from mingju_profile import compute_baseline
    b = compute_baseline(BIRTH)
    assert b["yunqi"]["ganzhi"] == "丁亥"
    assert b["yunqi"]["中运"] == {"五音": "少角", "五行": "木", "太过不及": "不及"}
    assert b["yunqi"]["司天"] == "厥阴风木" and b["yunqi"]["特殊"] == ["天符"]
    assert b["dili"]["方位"] == "南" and b["dili"]["五行"] == "火"    # 东经113、北纬23 → 南方


def test_bazi_paipan_endpoint_returns_yunqi_and_dili():
    from fastapi.testclient import TestClient
    from main import app
    c = TestClient(app)
    r = c.post("/api/bazi/paipan", json=BIRTH)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["yunqi"]["ganzhi"] == "丁亥" and d["yunqi"]["药食宜"]["上"] == "辛凉"
    assert d["dili"]["方位"] == "南"


def test_qipan_summary_endpoint():
    """气盘总览端点：底账＋判运链＋改运链三块齐；旧档案缺 yunqi/dili 时就地现算。"""
    from fastapi.testclient import TestClient
    from main import app
    tok = "tok-qipan-summary"
    c = TestClient(app)
    try:
        r = c.post("/api/mingju/profile", json={"id": tok, **BIRTH}, headers={"X-Owner-Token": tok})
        assert r.status_code == 200, r.text
        r = c.get("/api/qipan", headers={"X-Owner-Token": tok})
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["profile"] and q["profile"]["baseline"]["yunqi"]["ganzhi"] == "丁亥"
        assert q["profile"]["baseline"]["dili"]["方位"] == "南"
        assert q["suinian"]["ganzhi"] and q["suinian"]["strength"] in ("旺", "相", "休", "囚", "死")
        assert q["dangnian"]["ganzhi"] and q["dangnian"]["六步"] and q["dangnian"]["当前步"]
        assert q["dangnian"]["当前步"]["主气说明"]
        assert isinstance(q["recent"], list)
    finally:
        c.delete("/api/mingju/profile", params={"id": tok}, headers={"X-Owner-Token": tok})


def test_mingju_check_returns_tiandi_background():
    from fastapi.testclient import TestClient
    from main import app
    tok = "tok-yunqi-check"
    c = TestClient(app)
    try:
        r = c.post("/api/mingju/profile", json={"id": tok, **BIRTH}, headers={"X-Owner-Token": tok})
        assert r.status_code == 200, r.text
        r = c.post("/api/mingju/check",
                   json={"profile_id": tok, "question": "测运气背景",
                         "remedy": {"R": "土", "X": "土", "state": "用生体", "state_desc": "测试"}},
                   headers={"X-Owner-Token": tok})
        assert r.status_code == 200, r.text
        tian = r.json().get("yunqi")
        assert tian and tian["当年"] and tian["当年"]["ganzhi"]
        assert tian["出生年"]["ganzhi"] == "丁亥"
        assert tian["空间"]["方位"] == "南"
    finally:
        c.delete("/api/mingju/profile", params={"id": tok}, headers={"X-Owner-Token": tok})
        # 校验端点会把台账写进真实库（测试库＝运行库的既有约定），
        # 断言用临时令牌，完事连台账一并清掉，不留测试残留。
        import sqlite3 as _sq
        _con = _sq.connect(Path(__file__).resolve().parents[1] / "mingju_profiles.db")
        _logs = [r[0] for r in _con.execute("select id from check_log where owner=?", (tok,)).fetchall()]
        if _logs:
            _con.execute("delete from boundary_samples where log_id in (%s)"
                         % ",".join("?" * len(_logs)), _logs)
            _con.execute("delete from claim_feedback where log_id in (%s)"
                         % ",".join("?" * len(_logs)), _logs)
            _con.execute("delete from check_log where owner=?", (tok,))
        _con.commit()
        _con.close()
