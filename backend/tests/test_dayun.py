# -*- coding: utf-8 -*-
"""
大运流年详批：确定性骨架 + /api/bazi/dayun 端点
================================================
定位（站长 2026-10 定）：确定性归代码、语言归 AI。
骨架（干支十神/喜忌/结构/引动/神煞/重点年份/流月）必须**全部由代码算定**；
AI 只讲白话并补事件/评分/标题（须标「AI 推断，非书证」）。

本文件盯：
  ① 骨架的确定性：同一输入两次结果逐字节一致；喜忌/结构/引动/流月 逐项可证；
  ② ai=False 只出 scaffold、不调 LLM、不扣额度（与两步解卦同一纪律）；
  ③ ai=True 走签到/自带 key 的同一条闸（未签到 → degraded scope=signin）；
  ④ 感情维度缺婚恋状态 → 400（技能要求：不臆测用户状态）。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dayun_detail as dd           # noqa: E402
import main                         # noqa: E402
import quota                        # noqa: E402
from dayun_detail import dayun_scaffold  # noqa: E402

BIRTH = {"year": 2009, "month": 9, "day": 4, "hour": 15, "minute": 34, "gender": 1}
DEV = {"X-Owner-Token": "tok-dev"}


def _events(resp) -> list:
    out = []
    for block in resp.text.split("\n\n"):
        if block.startswith("data: "):
            out.append(json.loads(block[6:]))
    return out


# ============================================================
# 骨架确定性
# ============================================================
def test_scaffold_shapes():
    s = dayun_scaffold(BIRTH, "shiye", 2026, 2035)
    assert s["dimension"] == "shiye"
    assert len(s["dayun_rows"]) == 12, "十二步真大运"
    assert len(s["year_rows"]) == 10
    g = s["gangxian"]
    assert g["day_master"] == "壬" and g["tier"] == "身弱"
    assert g["F"] == ["金", "水"] and g["T0"] == ["土"]
    for r in s["year_rows"]:
        assert r["干支"] and r["干十神"] and r["支十神"], r
        assert r["干喜忌"] in ("喜", "忌", "闲", "调候")
    assert isinstance(s["key_years"], dict) and isinstance(s["liu_yue"], dict)


def test_scaffold_deterministic():
    a = dayun_scaffold(BIRTH, "caiyun", 2026, 2035)
    b = dayun_scaffold(dict(BIRTH), "caiyun", 2026, 2035)
    assert a == b


def test_xiji_qualification():
    """喜忌定性：壬日主喜金水、忌火（本例火为闲）、调候土。"""
    s = dayun_scaffold(BIRTH, "shiye", 2026, 2026)
    r = s["year_rows"][0]
    assert r["干支"] == "丙午"
    assert r["干喜忌"] == "闲" and r["支喜忌"] == "闲"       # 丙午皆火，火不在 F/J/T0
    s2 = dayun_scaffold(BIRTH, "shiye", 2028, 2028)          # 戊申：干土(调候)/支金(喜)
    r2 = s2["year_rows"][0]
    assert r2["干喜忌"] == "调候" and r2["支喜忌"] == "喜"


def test_structure_detection():
    """结构判定：己丑壬申壬子戊申 → 官印相生半成（官透、印藏），杀刃相济成（七杀透+壬刃子）。"""
    s = dayun_scaffold(BIRTH, "shiye", 2026, 2027)
    st = {x["结构"]: x["状态"] for x in s["yuanju"]["结构"]}
    assert st["官印相生"] == "半成"
    assert st["杀刃相济"] == "成"
    assert st["食伤制杀"] == "未成"


def test_yin_dong_chong_he():
    """关系：2026 丙午（壬日主盘）——午冲日支子；丙与年己无合无冲、与月/日干壬有丙壬冲。"""
    s = dayun_scaffold(BIRTH, "shiye", 2026, 2026)
    rels = {d["柱"]: d["关系"] for d in s["year_rows"][0]["原局关系"]}
    assert "六冲" in rels.get("日柱", ""), rels
    assert any("丙壬冲" in x for x in rels.values()), rels


def test_chengpin_relations_2025():
    """成品 2025 乙巳 逐条对照：乙辛冲、巳丑拱酉、巳亥冲、乙克己、乙庚合（2006-11-17 盘）。"""
    cp = {"year": 2006, "month": 11, "day": 17, "hour": 5, "minute": 35, "gender": 1}
    s = dayun_scaffold(cp, "shiye", 2025, 2025)
    r = s["year_rows"][0]
    assert r["干支"] == "乙巳"
    assert any("乙辛冲" in x for x in r["大运关系"]), r["大运关系"]
    assert any("拱酉" in x for x in r["大运关系"]), r["大运关系"]
    byzhu = {d["柱"]: d["关系"] for d in r["原局关系"]}
    assert any("六冲" in x for x in byzhu["月柱"]), byzhu          # 巳亥冲
    assert any("乙庚合" in x for x in byzhu["日柱"]), byzhu        # 乙庚合
    assert any("乙克己" in x for x in byzhu["月柱"]), byzhu        # 财坏印
    assert any("乙生丙" in x for x in byzhu["年柱"]), byzhu


def test_chengpin_relations_2026_2027():
    """成品 2026/2027 对照：丙辛合＋午丑相害、午戌半合＋卯午破、丙克庚；2027 未戌刑＋亥卯未三合成局。"""
    cp = {"year": 2006, "month": 11, "day": 17, "hour": 5, "minute": 35, "gender": 1}
    s = dayun_scaffold(cp, "shiye", 2026, 2027)
    r26 = s["year_rows"][0]
    assert any("丙辛合" in x for x in r26["大运关系"]) and any("相害" in x for x in r26["大运关系"])
    byzhu = {d["柱"]: d["关系"] for d in r26["原局关系"]}
    assert any("伏吟" in x for x in byzhu["年柱"]) and any("半合" in x for x in byzhu["年柱"])
    assert any("相破" in x for x in byzhu["时柱"]) and any("丙克庚" in x for x in byzhu["日柱"])
    r27 = s["year_rows"][1]
    byzhu27 = {d["柱"]: d["关系"] for d in r27["原局关系"]}
    assert any("相刑" in x for x in byzhu27["年柱"]), byzhu27     # 未戌刑
    assert any("三合亥卯未局成" in x for x in r27["成局"]), r27["成局"]


def test_key_years_jixian_chengpin():
    """吉年＝干支皆印比（生扶）；险年＝干支皆克泄耗。成品吉年险年均为其子集。"""
    cp = {"year": 2006, "month": 11, "day": 17, "hour": 5, "minute": 35, "gender": 1}
    s = dayun_scaffold(cp, "shiye", 2025, 2060)
    good, bad = s["key_years"]["吉年"], s["key_years"]["险年"]
    for y in (2028, 2029, 2030, 2039, 2040, 2048, 2051):
        assert y in good, (y, good)
    for y in (2026, 2037, 2046, 2056, 2034, 2035):
        assert y in bad, (y, bad)
    assert 2027 not in bad and 2027 not in good   # 丁未：干凶支吉，混合年


def test_tier_reason_data():
    """强弱素材：2006 盘 庚金生亥月=失令，月令长生=病。"""
    cp = {"year": 2006, "month": 11, "day": 17, "hour": 5, "minute": 35, "gender": 1}
    s = dayun_scaffold(cp, "shiye", 2026, 2026)
    tr = s["gangxian"]["tier_reason"]
    assert tr["月令"].startswith("失令") and tr["月令长生"] == "病", tr
    assert s["gangxian"]["buxin"][0]["五行"] == "土" and s["gangxian"]["buxin"][0]["十神"] == "印"


def test_caiyun_caiku_and_lu():
    """财运：壬日主财星=火，库=戌；2026 丙午 财星当值。流年午 vs 壬禄（亥）/壬刃（子）均不命中。"""
    s = dayun_scaffold(BIRTH, "caiyun", 2026, 2026)
    assert s["yuanju"]["财星"] == {"五行": "火", "库": "戌", "喜忌": "闲"}
    r = s["year_rows"][0]
    assert r["财星当值"] == "闲" and "禄" not in r and "刃" not in r


def test_ganqing_peiou_and_taohua():
    """感情：男命配偶星=财（火，闲）；2026 丙午 流年咸池（午）→ 桃花，且午冲日支 → 夫妻宫引动。"""
    s = dayun_scaffold(BIRTH, "ganqing", 2026, 2026, "单身")
    assert s["yuanju"]["配偶星"]["五行"] == "火"
    r = s["year_rows"][0]
    assert r.get("桃花") is True
    assert r.get("夫妻宫引动") is True
    assert r.get("配偶星当值") == "闲"


def test_liu_yue_twelve_months_by_jie():
    """流月：12 个节气月。2026 丙午（壬日主盘）为险年 → 有流月；直接测月份函数。"""
    s = dayun_scaffold(BIRTH, "shiye", 2026, 2026)
    assert 2026 in s["key_years"]["险年"] and "2026" in s["liu_yue"]
    months = dd._months_of_year("壬", 2026)
    assert len(months) == 12
    gzs = [m["干支"] for m in months]
    assert len(set(gzs)) == 12, "十二个月干支互不重复：%s" % gzs
    assert gzs[0] == "己丑" and gzs[1] == "庚寅", gzs[:2]     # 2026 正月=丑月、二月=寅月
    assert months[0]["干十神"] == "正官"                       # 己（土）对壬 = 正官


# ============================================================
# 端点：两步 + 配额 + 参数校验
# ============================================================
@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("QUOTA_DB", str(Path(tmp_path) / "quota.db"))
    # 关掉真 API Key（ai=True 那条不该真去打上游）；其余测试会按需 monkeypatch
    monkeypatch.setitem(main.LLM_CONFIG, "api_key", "")
    return TestClient(main.app)


def test_endpoint_ai_false_sends_scaffold_only_and_no_quota(client):
    before = quota.status()["used"]
    r = client.post("/api/bazi/dayun", json={"birth": BIRTH, "dimension": "shiye",
                                             "year_from": 2026, "year_to": 2035, "ai": False})
    assert r.status_code == 200, r.text
    evs = _events(r)
    assert [e.get("type") for e in evs] == ["scaffold", "done"], [e.get("type") for e in evs]
    sc = evs[0]["data"]
    assert sc["dimension"] == "shiye" and len(sc["year_rows"]) == 10
    assert quota.status()["used"] == before, "只看骨架不能扣额度"


def test_endpoint_ai_true_without_signin_degrades_signin(client):
    """ai=True 未签到 → scaffold 照给，AI 段 degraded(scope=signin)，不静默花站长的钱。"""
    r = client.post("/api/bazi/dayun", json={"birth": BIRTH, "dimension": "shiye",
                                             "year_from": 2026, "year_to": 2027, "ai": True})
    evs = _events(r)
    assert [e.get("type") for e in evs] == ["scaffold", "degraded", "done"], [e.get("type") for e in evs]
    assert evs[1]["scope"] == "signin"


def test_endpoint_ganqing_requires_marital_status(client):
    r = client.post("/api/bazi/dayun", json={"birth": BIRTH, "dimension": "ganqing",
                                             "year_from": 2026, "year_to": 2027, "ai": False})
    assert r.status_code == 400 and "婚恋状态" in r.json()["detail"]


def test_endpoint_rejects_bad_dimension_and_range(client):
    assert client.post("/api/bazi/dayun", json={"birth": BIRTH, "dimension": "shiqe",
                                                "year_from": 2026, "year_to": 2027}).status_code == 400
    assert client.post("/api/bazi/dayun", json={"birth": BIRTH, "dimension": "shiye",
                                                "year_from": 2030, "year_to": 2027}).status_code == 400


def test_endpoint_ai_true_with_byok_uses_user_llm(client, monkeypatch):
    """自带 key：走用户配置、不计数（模拟 _stream_llm 捕获 llm 参数）。"""
    client.post("/api/quota/signin", headers=DEV)
    captured = {}

    async def _fake_stream(user_prompt="", system_prompt="", max_tokens=None,
                           disable_thinking=False, messages=None, state=None, llm=None):
        captured["llm"] = llm
        captured["max_tokens"] = max_tokens
        captured["messages"] = messages
        captured["disable_thinking"] = disable_thinking
        yield "试"

    monkeypatch.setattr(main, "_stream_llm", _fake_stream)
    r = client.post("/api/bazi/dayun", headers=DEV,
                    json={"birth": BIRTH, "dimension": "caiyun", "year_from": 2026, "year_to": 2027,
                          "ai": True, "llm": {"provider": "deepseek", "api_key": "sk-user", "model": "deepseek-v4-pro"}})
    evs = _events(r)
    assert [e.get("type") for e in evs] == ["scaffold", "text", "done"], [e.get("type") for e in evs]
    assert evs[1]["content"] == "试"
    assert captured["llm"]["provider"] == "deepseek" and captured["llm"]["api_key"] == "sk-user"
    assert captured["messages"][0]["content"] == main.DAYUN_SYSTEM_PROMPT
    assert captured["disable_thinking"] is True
    assert captured["max_tokens"] == main.DAYUN_MAX_TOKENS
    user_msg = captured["messages"][1]["content"]
    assert "【骨架·逐年表" in user_msg and "【财运·分析规则" in user_msg


def test_user_prompt_carries_scaffold_and_rules(client):
    """用户消息必须同时含 确定性骨架数据 与 规则表（AI 实收字句＝称引基准）。"""
    s = dayun_scaffold(BIRTH, "ganqing", 2026, 2027, "单身")
    up = main.build_dayun_user_prompt(s)
    assert "【骨架·命理纲线" in up and "【骨架·逐年表" in up
    assert "【感情·分析规则" in up
    assert "配偶星" in up and "夫妻宫" in up and "桃花" in up
    assert "单身" in up
    # 称引基准要求：规则表里的篇名必须逐字出现（回检以实收为基准）
    for name in ("渊海子平·论驿马", "子平真诠·论妻子", "子平真诠·论星辰无关格局",
                 "渊海子平·论十二支相穿", "渊海子平·论十二支相刑", "子平真诠·论刑冲会合解法",
                 "渊海子平·论十二支三合"):
        assert name in up, name
