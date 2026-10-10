# -*- coding: utf-8 -*-
"""最小反馈 + 应期断言 的回归锁（2026-09-23 改）

两件事各守一条：
1. **应期必须有一条可反馈的断言**——它是全站最敏感的自定数字（实测：加权 −20%
   或门槛 +20%，14 个真卦的日期表全变），此前却没有任何反馈通道
   （反馈里的「择日」指宜忌日期表，与「应期之日」是两张不同的表）；
2. **最小提问**：整案一问可带"实际发生日期"，且该日期必须真的落库
   （应期分析靠它算偏差几天）；不传日期时不许把已填的日期抹掉。
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


# ---------- 1. 应期断言 ----------

def test_yingqi_claim_appears_with_dates():
    claims = feedback.build_claims(
        {"net": "平", "decision": "放行"}, [], None, None, {"tier": "S"},
        ["金"], {}, {"dates": ["2026-09-23", "2026-09-24", "2026-10-01"], "final_count": 2},
        today="2026-09-21")
    yq = [c for c in claims if c["type"] == "应期"]
    assert yq, "应期没有生成断言"
    c = yq[0]
    assert "09-23" in c["text"] and "10-01" in c["text"], "应期断言里必须列出日期"
    assert "实际哪一天发生" in c["text"], "必须明确请用户回答实际日期"
    assert c["verifiability"] == "客观可验"
    assert c["params"] == ["yingqi.weights", "yingqi.gate"], "参数名要指到应期那一组"
    assert (c["since"], c["until"]) == ("2026-09-23", "2026-10-01"), "验证窗口应取应期首末日期"


def test_no_yingqi_claim_without_dates():
    """没有应期数据时不许凭空造一条。"""
    claims = feedback.build_claims({"net": "平", "decision": "x"}, [], None, None,
                                  {"tier": "S"}, ["金"], {}, None, today="2026-09-21")
    assert not [c for c in claims if c["type"] == "应期"]
    claims2 = feedback.build_claims({"net": "平", "decision": "x"}, [], None, None,
                                   {"tier": "S"}, ["金"], {}, {"dates": []}, today="2026-09-21")
    assert not [c for c in claims2 if c["type"] == "应期"]


def test_yingqi_params_match_calibration_naming():
    """断言的参数名必须与配置里的键一致，否则将来接校准时会断了对应关系。"""
    from weights import YINGQI
    assert "weights" in YINGQI and "gate" in YINGQI
    claims = feedback.build_claims({"net": "平", "decision": "x"}, [], None, None,
                                  {"tier": "S"}, ["金"], {}, {"dates": ["2026-09-23"]},
                                  today="2026-09-21")
    c = [x for x in claims if x["type"] == "应期"][0]
    for p in c["params"]:
        assert p.split(".")[-1] in YINGQI, f"参数 {p} 在应期配置里找不到"


# ---------- 2. 最小提问：实际发生日期 ----------

def test_actual_date_is_stored(log_db):
    lid = log_db.append_check({"owner": "p1", "profile_id": "p1", "claims": []})
    assert log_db.set_feedback(lid, "应验", "p1", "2026-09-25") is True
    row = [r for r in log_db.recent(5, "p1") if r["id"] == lid][0]
    assert row["outcome"] == "应验"
    assert row["actual_date"] == "2026-09-25"


def test_actual_date_not_wiped_by_button_only(log_db):
    """用户第二次只点了按钮（不填日期），已填的日期不能被抹掉。"""
    lid = log_db.append_check({"owner": "p1", "profile_id": "p1", "claims": []})
    log_db.set_feedback(lid, "应验", "p1", "2026-09-25")
    log_db.set_feedback(lid, "未验", "p1", "")
    row = [r for r in log_db.recent(5, "p1") if r["id"] == lid][0]
    assert row["outcome"] == "未验"
    assert row["actual_date"] == "2026-09-25"


def test_actual_date_is_truncated_to_day(log_db):
    lid = log_db.append_check({"owner": "p1", "profile_id": "p1", "claims": []})
    log_db.set_feedback(lid, "应验", "p1", "2026-09-25T13:20:00")
    row = [r for r in log_db.recent(5, "p1") if r["id"] == lid][0]
    assert row["actual_date"] == "2026-09-25"


def test_outcome_still_three_options(log_db):
    lid = log_db.append_check({"owner": "p1", "profile_id": "p1", "claims": []})
    with pytest.raises(ValueError):
        log_db.set_feedback(lid, "大吉", "p1")


# ---------- 3. 应期加权已入版本化配置 ----------

def test_yingqi_weights_come_from_config():
    import yingqi
    from weights import YINGQI, WEIGHTS_VERSION
    assert yingqi.WS_WEIGHTS == YINGQI["weights"]
    assert yingqi.WS_GATE == float(YINGQI["gate"])
    assert yingqi.WS_MONTH == YINGQI["month_states"]
    assert yingqi.WS_OTHER == YINGQI["other_states"]
    # 版本号必须带得动它们：改成 1.2.0 之后，决策日志的 weights_version 才会区分"改之前/之后"
    assert tuple(int(x) for x in WEIGHTS_VERSION.split(".")) >= (1, 2, 0)


def test_page_note_reflects_config_values():
    """页面上那行小字里的数字必须与配置一致（不许各写一套后脱节）。"""
    import yingqi
    from weights import YINGQI
    note = yingqi.WS_NOTE
    assert "%g" % YINGQI["weights"]["month"] in note
    assert "%g" % YINGQI["gate"] in note
