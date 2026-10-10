# -*- coding: utf-8 -*-
"""类象层测试：通类表、类神取用、射覆、物类查询（书证：壬归/说约/心镜/苗公射覆）。"""
from datetime import datetime


def test_tonglei_table():
    from leixiang import TONGLEI
    assert len(TONGLEI) == 12
    # 壬归「凡占必以天官为万类之主」逐条
    assert TONGLEI["盗贼"] == "玄武" and TONGLEI["求财"] == "青龙"
    assert TONGLEI["文书"] == "朱雀" and TONGLEI["干贵"] == "天乙"
    assert TONGLEI["怪异"] == "螣蛇" and TONGLEI["争斗"] == "勾陈"
    assert TONGLEI["疾病"] == "白虎" and TONGLEI["婚姻"] == "六合"
    assert TONGLEI["饮食"] == "太常" and TONGLEI["奴婢"] == "天空"
    assert TONGLEI["阴私"] == "太阴" and TONGLEI["妇女"] == "天后"


def test_zhishen_wulei_shuoyue():
    # 说约卷上十二天神逐条抽查（用户所引「太乙蛇虫釜甑、胜光马雉图画」）
    from leixiang import ZHISHEN
    assert ZHISHEN["子"]["名"] == "神后" and ZHISHEN["子"]["数"] == 9 and ZHISHEN["子"]["味"] == "咸"
    assert "釜甑" in ZHISHEN["巳"]["在物"] and "蚕" in ZHISHEN["巳"]["在物"]
    assert "虹霓" in ZHISHEN["巳"]["在天"]
    assert "马" in ZHISHEN["午"]["在物"] and "雉" in ZHISHEN["午"]["在物"]
    assert ZHISHEN["丑"]["数"] == 8 and ZHISHEN["寅"]["数"] == 7 and ZHISHEN["卯"]["数"] == 6
    assert ZHISHEN["辰"]["数"] == 5 and ZHISHEN["巳"]["数"] == 4 and ZHISHEN["未"]["数"] == 8
    assert ZHISHEN["申"]["数"] == 7 and ZHISHEN["酉"]["数"] == 6 and ZHISHEN["戌"]["数"] == 5
    assert ZHISHEN["亥"]["数"] == 4
    assert "胃昴毕" not in ZHISHEN["酉"]["星"] and ZHISHEN["酉"]["星"] == "昴毕"
    assert "觜参" in ZHISHEN["申"]["星"]


def test_tianjiang_wulei():
    from leixiang import TIANJIANG
    assert set(TIANJIANG) == {"贵人", "螣蛇", "朱雀", "六合", "勾陈", "青龙",
                              "天空", "白虎", "太常", "玄武", "太阴", "天后"}
    # 说约卷上十二天将逐条抽查
    assert TIANJIANG["白虎"]["五行"] == "金" and TIANJIANG["白虎"]["吉凶"] == "凶"
    assert "杀戮" in TIANJIANG["白虎"]["说约主"]
    assert TIANJIANG["青龙"]["五行"] == "木" and "财宝" in TIANJIANG["青龙"]["说约主"]
    assert TIANJIANG["贵人"]["临"]["丑"] == "升堂" and TIANJIANG["贵人"]["临"]["亥"] == "登天门·秉笏"
    assert TIANJIANG["螣蛇"]["临"]["申"] == "衔剑" and TIANJIANG["玄武"]["临"]["酉"] == "拔剑"
    assert TIANJIANG["青龙"]["苗公加"]["巳"] == "酒食宴会"
    # 心镜主事在录
    assert "文书" in TIANJIANG["朱雀"]["心镜主"] and "信息" in TIANJIANG["六合"]["心镜主"]


def test_leishen_qiyong_qiucai():
    # 求财（书例时刻 2005-08-09 12:00 乙丑日）：通类青龙；类神含财爻（乙木克土：辰戌丑未）
    from leixiang import leishen_qiyong
    from daliuren import qike
    ke = qike(datetime(2005, 8, 9, 12, 0))
    r = leishen_qiyong(ke, "求财")
    assert r["通类天将"] == "青龙"
    names = [(x["记号"], x["类神"]) for x in r["类神"]]
    assert "青龙" in [t for t, _ in names]
    cai = [z for t, z in names if t == "财爻"]
    assert all(z in "辰戌丑未" for z in cai) and len(cai) > 0
    for x in r["类神"]:
        assert x["状态"] and x["名"]


def test_leishen_yinxin_erma():
    # 音信行人：类神含传送、驿马（乙丑日驿马＝亥）、丁神（甲子旬丁卯＝卯）、朱雀、白虎
    from leixiang import leishen_qiyong, _tianma
    from daliuren import qike
    ke = qike(datetime(2005, 8, 9, 12, 0))
    r = leishen_qiyong(ke, "音信行人")
    names = [(x["记号"], x["类神"]) for x in r["类神"]]
    # 乙丑日：驿马亥（qike 无月建时二马仅驿马）；丁神＝甲子旬丁卯＝卯；传送＝申
    got = [z for t, z in names if t == "二马"]
    assert got == ["亥"]
    ding = [z for t, z in names if t == "丁神"]
    assert ding == ["卯"]
    chuan = [z for t, z in names if t == "传送"]
    assert chuan == ["申"]
    # 天马表（大全 L2876：正月午顺行六阳辰）
    assert _tianma("寅") == "午" and _tianma("卯") == "申" and _tianma("辰") == "戌"
    assert _tianma("巳") == "子" and _tianma("午") == "寅" and _tianma("未") == "辰"


def test_shefu_candidates():
    # 射覆：多维线索候选清单（书例时刻 2005-08-09 12:00）
    from leixiang import shefu
    from daliuren import qike
    ke = qike(datetime(2005, 8, 9, 12, 0))
    r = shefu(ke, datetime(2005, 8, 9, 12, 0))
    layers = [x["层"] for x in r["线索"]]
    assert "五行类（发用）" in layers and "颜色" in layers
    assert "形状" in layers and "卦宫物类" in layers and "数目" in layers
    for x in r["线索"]:
        assert x["候选"] and x["据"]
    assert r["线索"][0]["候选"]


def test_wulei_query():
    from leixiang import wulei_query
    r = wulei_query("支神", "太乙")
    assert r["支"] == "巳" and r["五行"] == "火"
    r2 = wulei_query("天将", "白虎")
    assert r2["将"] == "白虎" and r2["吉凶"] == "凶"
    r3 = wulei_query("天将", "天乙")
    assert r3["将"] == "贵人"
    r4 = wulei_query("支神", "猫")
    assert "未查到" in r4["口径"]


def test_leixiang_endpoint():
    from fastapi.testclient import TestClient
    from main import app
    c = TestClient(app)
    r = c.post("/api/leixiang", json={"dt": "2005-08-09 12:00", "wenshi": "求财"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["类神取用"]["通类天将"] == "青龙"
    assert d["类神取用"]["问事"] == "求财"
    assert d["射覆"]["线索"]
    assert "不代断" in d["类神取用"]["口径"]
    # 坏问事
    r2 = c.post("/api/leixiang", json={"dt": "2005-08-09 12:00", "wenshi": "猫"})
    assert r2.status_code == 400
    # 年命一起返回（类神取用带年命状态）
    r3 = c.post("/api/leixiang", json={"dt": "2005-08-09 12:00", "wenshi": "疾病",
                                       "nianzhu": "丙子", "xingbie": "男"})
    assert r3.status_code == 200 and r3.json()["年命"]["本命"] == "子"