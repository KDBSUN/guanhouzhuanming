# -*- coding: utf-8 -*-
"""
决策日志回归（decision_log.py）
==============================
决策日志是"可复核"的最终形态与案例库地基：每条记录带完整推理链快照
（含当时的规则版本与权重版本锚点），反馈回流把日志变成"裁决—结果"配对。
"""
import json
from pathlib import Path

import pytest

import decision_log


@pytest.fixture()
def log_db(tmp_path, monkeypatch):
    decision_log._DB_PATH = Path(tmp_path) / "log.db"
    decision_log.init_log_db()
    return decision_log


def _record(**over):
    # owner 必填：决策日志没有"无主数据"这个合法状态（无主的行谁也读不到＝静默丢数据），
    # append_check 现在会直接拒绝缺失 owner 的写入。
    base = {
        "owner": "p1", "profile_id": "p1", "question": "最近适合谈合作吗",
        "tier": "S", "tier_source": "manual",
        "R": "火", "final_R": "土", "F": ["土", "金"], "J": ["火"], "T0": [],
        "from_ge": "", "net": "平", "level": "yellow", "gate": "limited",
        "decision": "限时放行", "liunian": {"ganzhi": "丙午", "wx": "火", "effect": "none"},
        "month_wx": "金", "day_zhi": "午",
        "rules_version": "1.0.0", "weights_version": "1.0.0",
    }
    base.update(over)
    return base


def test_append_and_roundtrip(log_db):
    lid = log_db.append_check(_record())
    rows = log_db.recent(owner="p1")
    assert len(rows) == 1 and rows[0]["id"] == lid
    r = rows[0]
    assert r["question"] == "最近适合谈合作吗"
    assert json.loads(r["F"]) == ["土", "金"]
    assert json.loads(r["liunian_json"])["ganzhi"] == "丙午"
    assert r["rules_version"] == "1.0.0" and r["weights_version"] == "1.0.0"
    assert r["outcome"] == "" and r["ts"]

def test_feedback_roundtrip(log_db):
    lid = log_db.append_check(_record())
    assert log_db.set_feedback(lid, "应验", "p1") is True
    r = log_db.recent(1, "p1")[0]
    assert r["outcome"] == "应验" and r["outcome_ts"]
    # 补记改判
    assert log_db.set_feedback(lid, "未验", "p1") is True
    assert log_db.recent(1, "p1")[0]["outcome"] == "未验"

def test_feedback_validation(log_db):
    lid = log_db.append_check(_record())
    with pytest.raises(ValueError):
        log_db.set_feedback(lid, "大吉")
    assert log_db.set_feedback(99999, "应验", "p1") is False

def test_versions_recorded_per_row(log_db):
    # 版本锚点按行落库：事后归因"这条结论是哪版规则/权重算的"
    log_db.append_check(_record(rules_version="0.9.0", weights_version="1.0.0"))
    log_db.append_check(_record(rules_version="1.0.0", weights_version="1.1.0"))
    rows = log_db.recent(10, "p1")
    by_rules = {r["rules_version"] for r in rows}
    assert by_rules == {"0.9.0", "1.0.0"}
    assert any(r["weights_version"] == "1.1.0" for r in rows)

def test_kind_defaults_to_check(log_db):
    lid = log_db.append_check(_record())
    r = log_db.recent(1, "p1")[0]
    assert r["id"] == lid and r["kind"] == "check"

def test_bazi_kind_and_extra_roundtrip(log_db):
    # 八字排盘留痕：kind=bazi + 四柱快照落 extra_json，记录页据此回看
    lid = log_db.append_check(_record(
        kind="bazi", question="", decision="八字排盘",
        extra={"pillars": "庚午 庚辰 甲子 辛未", "solar": "1990年5月15日", "gender": "男"},
    ))
    r = next(row for row in log_db.recent(10, "p1") if row["id"] == lid)
    assert r["kind"] == "bazi"
    assert r["decision"] == "八字排盘"
    extra = json.loads(r["extra_json"])
    assert extra["pillars"] == "庚午 庚辰 甲子 辛未" and extra["gender"] == "男"

def test_check_row_extra_source_recorded(log_db):
    # 起卦记录带来源标记（meihua/liuyao），供记录页分栏与日后归因
    lid = log_db.append_check(_record(extra={"source": "liuyao", "gua": {}}))
    r = next(row for row in log_db.recent(10, "p1") if row["id"] == lid)
    assert json.loads(r["extra_json"])["source"] == "liuyao"
