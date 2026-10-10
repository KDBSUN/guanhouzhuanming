# -*- coding: utf-8 -*-
"""反馈语义层回归（feedback.py · claim 级反馈 / 边界样本 / 校准护栏）
核心命题：整案级二值反馈无归因、无局部性，不能调数值；
反馈必须落在"可独立判定的断言"上，数值只能由"边界样本"驱动，且全程人工批准。
"""
import json
from pathlib import Path

import pytest

import decision_log
import feedback


@pytest.fixture()
def log_db(tmp_path, monkeypatch):
    decision_log._DB_PATH = Path(tmp_path) / "log.db"
    decision_log.init_log_db()
    return decision_log


def _verdict():
    return {"net": "平", "level": "yellow", "gate": "limited",
            "decision": "限时放行：避火，补土金", "hits": []}


def _flows(score=5.9):
    """一份近似真实输出的 flows（状态评分擦 state_strong_min=6.0 的边界）。"""
    return [{
        "wx": "金", "state": "中和偏旺", "state_note": "有根有源",
        "state_score": score, "state_note_extra": None,
        "header": {"我克": "我克（木·自克）", "克我": "克我（火·他克）"},
        "rows": [{"state": "中和偏旺", "active": True, "cells": {
            "我克": {"grade": "宜少量", "note": "旺金可任财", "src": "穷通宝鉴·论金",
                     "chengwu": {"value": "垂", "a": 3.0, "d": 3.4, "ratio": 0.88,
                                 "note": "势均", "src": "黄帝内经·乘侮"}},
            "克我": {"grade": "大忌", "note": "衰金遇火销熔", "src": "元理赋",
                     "chengwu": {"value": "乘", "a": 4.4, "d": 3.0, "ratio": 1.47,
                                 "note": "火乘金", "src": "黄帝内经·乘侮"}},
        }}],
        "branch_notes": [{"type": "六冲", "pair": "寅申", "note": "命局有寅，传统上主散。", "src": "增删卜易·六冲章"}],
        "flavor": {"gan": "辛", "note": "用神爻辛酉，取温润之味", "src": "滴天髓·论天干"},
    }]


def _liunian(weight=0.5):
    return {"ganzhi": "丙午", "wx": "火", "strength": "休", "weight": weight,
            "effective": True, "effect": "drag", "notes": []}


def _date_info():
    return {"days": [{"date": "2026-03-12", "yiji": "宜", "ganzhi": "丙申"},
                     {"date": "2026-03-15", "yiji": "宜", "ganzhi": "己亥"},
                     {"date": "2026-03-18", "yiji": "忌", "ganzhi": "壬寅"}]}


def test_claims_cover_types_and_metadata():
    claims = feedback.build_claims(_verdict(), _flows(), _liunian(), _date_info(),
                                  {"tier": "S"}, ["金"], {}, today="2026-03-10")
    types = {c["type"] for c in claims}
    assert {"裁决", "风险", "岁运", "择日", "关系", "建议"} <= types
    for c in claims:
        # 每条断言必须可归因（rule）、可定位（params/verifiability）、有验证窗口
        assert c["rule"] and c["verifiability"] in feedback.VERIFIABILITY
        assert c["since"] and c["until"] and c["text"]
    # 择日是唯一"客观可验"通道（公测期最有价值的反馈源）
    zeri = [c for c in claims if c["type"] == "择日"]
    assert zeri and all(c["verifiability"] == "客观可验" for c in zeri)
    assert zeri[0]["params"] == ["zeri_yi_states", "shiwang_weight"]
    # S 档窗口 7 天
    assert claims[0]["since"] == "2026-03-10" and claims[0]["until"] == "2026-03-17"


def test_claims_dedup_and_cap():
    claims = feedback.build_claims(_verdict(), _flows() * 3, _liunian(), None,
                                  {"tier": "L"}, ["金"], {})
    assert len(claims) <= 12
    keys = [(c["type"], c["text"][:60]) for c in claims]
    assert len(keys) == len(set(keys))


def test_boundary_samples_detects_near_threshold():
    """判据值擦阈才记账：state_score 5.9 距 6.0 在带宽内 → 记；乘侮差 1.4 距 1.0 在外 → 不记。"""
    samples = feedback.boundary_samples_of(_flows(score=5.9), _liunian(weight=0.5))
    params = {(s["param"], s["side"]) for s in samples}
    assert ("flow_thresholds.state_strong_min", "下沿") in params
    assert ("strong_threshold", "上沿") in params          # weight 0.5 恰在阈值上
    assert not any(s["param"] == "flow_thresholds.chengwu_margin" and s["value"] == 1.4
                   for s in samples)
    # 远离阈值 → 不记
    far = feedback.boundary_samples_of(_flows(score=2.0), _liunian(weight=0.2))
    assert not any(s["param"] == "flow_thresholds.state_strong_min" for s in far)


def test_claim_feedback_roundtrip_and_overwrite(log_db):
    lid = log_db.append_check({"owner": "p1", "profile_id": "p1",
                               "claims": [{"id": "c1", "text": "x"}]})
    assert log_db.claims_of(lid, "p1")[0]["id"] == "c1"
    feedback.save_verdict(lid, "c1", "应验", "", "p1")
    assert log_db.feedback_of(lid, "p1") == {"c1": "应验"}
    feedback.save_verdict(lid, "c1", "反向", "实际恰好相反", "p1")   # 后记覆盖前记
    assert log_db.feedback_of(lid, "p1") == {"c1": "反向"}
    with pytest.raises(ValueError):
        feedback.save_verdict(lid, "c1", "大吉", "", "p1")


def test_calibration_guardrails(log_db):
    """护栏：样本不足不提案；达标才生成"待批"提案，且幅度受 ±30% 限制、绝不自动生效。

    注意 claim 必须带 `params` 且与边界参数同根：样本只在"这条反馈确实与那个参数有关"
    时才计入（见下一条反作弊测试）。
    """
    # 3 条边界样本 + 全部"未验" → 低于 min_samples=5，不提案
    for _ in range(3):
        lid = log_db.append_check({"owner": "p", "profile_id": "p",
                                   "claims": [{"id": "c1", "params": ["flow_thresholds"]}]})
        log_db.add_boundary_samples(lid, [{"param": "flow_thresholds.state_strong_min", "value": 5.9,
                                           "threshold": 6.0, "side": "下沿", "at_verdict": "中和偏旺"}])
        log_db.add_claim_feedback(lid, "c1", "未验", owner="p")
    assert feedback.analyze_calibration() == []
    # 补到 5 条 → 生成提案
    for _ in range(2):
        lid = log_db.append_check({"owner": "p", "profile_id": "p",
                                   "claims": [{"id": "c1", "params": ["flow_thresholds"]}]})
        log_db.add_boundary_samples(lid, [{"param": "flow_thresholds.state_strong_min", "value": 5.9,
                                           "threshold": 6.0, "side": "下沿", "at_verdict": "中和偏旺"}])
        log_db.add_claim_feedback(lid, "c1", "未验", owner="p")
    props = feedback.analyze_calibration()
    assert len(props) == 1
    p = props[0]
    assert p["status"] == "待批" and p["param"] == "flow_thresholds.state_strong_min"
    assert p["n_samples"] == 5 and p["flip_rate"] == 1.0
    # 幅度护栏：下沿 → 阈值向下挪，且不超过 ±30%
    assert p["new_value"] < p["old_value"]
    assert abs(p["new_value"] - p["old_value"]) <= 0.3 * abs(p["old_value"]) + 1e-9
    # 人工批准留痕
    assert log_db.decide_proposal(p["id"], "已批准", "user") is True
    assert log_db.list_proposals("已批准")[0]["id"] == p["id"]


def test_one_log_cannot_satisfy_min_samples(log_db):
    """反作弊：**一条**日志上点满 5 个 claim 不能凑成 5 个样本。

    原实现把一个日志上的全部 verdict 都累加计数，于是"一个人在一个案例里连点五下"
    就等于五个独立样本，min_samples=5 这条护栏（"样本太少不许动阈值"）当场失效，
    还会产出一个 flip_rate=1.0 的提案。样本单位必须是**案例（日志）**。
    """
    lid = log_db.append_check({"owner": "p", "profile_id": "p",
                               "claims": [{"id": "c%d" % i, "params": ["strong_threshold"]}
                                          for i in range(5)]})
    log_db.add_boundary_samples(lid, [{"param": "strong_threshold", "value": 5.95,
                                       "threshold": 6.0, "side": "下沿", "at_verdict": "中和偏旺"}])
    for i in range(5):
        log_db.add_claim_feedback(lid, "c%d" % i, "未验", owner="p")
    assert feedback.analyze_calibration() == [], "一条日志不该凑满 min_samples"


def test_unrelated_claim_does_not_count_toward_param(log_db):
    """只有"参与该参数"的 claim 的反馈才计入该参数的样本。

    否则任意一条与阈值无关的反馈（比如择日宜忌）都能去推动 flow 的阈值。
    """
    for _ in range(5):
        lid = log_db.append_check({"owner": "p", "profile_id": "p",
                                   "claims": [{"id": "c1", "params": ["zeri_yi_states"]}]})
        log_db.add_boundary_samples(lid, [{"param": "strong_threshold", "value": 5.95,
                                           "threshold": 6.0, "side": "下沿", "at_verdict": "中和偏旺"}])
        log_db.add_claim_feedback(lid, "c1", "未验", owner="p")
    assert feedback.analyze_calibration() == [], "不相干的反馈不应推动该参数的阈值"


def test_recent_for_feedback_and_beta_notes(log_db):
    lid = log_db.append_check({"owner": "p1", "kind": "check", "question": "合作能成吗", "net": "平",
                               "decision": "限时放行", "claims": [{"id": "c1", "text": "裁决：平"}]})
    log_db.append_check({"owner": "p1", "kind": "bazi", "question": "", "claims": []})
    items = feedback.recent_for_feedback(5, "p1")
    assert len(items) == 1 and items[0]["log_id"] == lid and items[0]["claims"][0]["id"] == "c1"
    nid = log_db.add_beta_note("宜日很准", "me@example.com", lid)
    notes = log_db.list_beta_notes()
    assert notes[0]["id"] == nid and notes[0]["contact"] == "me@example.com"


def test_calibration_view_exposes_guardrails(log_db):
    view = feedback.calibration_view()
    assert set(["proposals", "boundary", "guardrails"]) <= set(view.keys())
    assert view["guardrails"]["min_samples"] >= 1
