# -*- coding: utf-8 -*-
"""
每日免费额度与降级（quota.py）的回归测试
========================================
2026-10-02 起口径由站长改成：**自带 key 不限次；没 key 的人签到后当日 3 次**。
所以这个文件盯的东西也跟着换了，但锁住的仍然是"改一行就会静默失效"的那些：

  1. **不签到不给用**，签到后当日 3 次；
  2. **跨天不结转**——昨天的剩余次数不许累加到今天（站长明确要求）；
  3. **到阈值才拦**，且拦住之后**不再计数**（否则次日零点前的用量完全失真）；
  4. **IP 兜底与全站硬阈值**都还在（防"清掉本地记录再签到"与成本天花板）；
  5. **降级文案**是对外承诺，一字不改；**软阈值只告警一次**（落库，重启不重复发）；
  6. **计数本身坏掉时放行**（护栏不该变成新的故障源）。

隔离：每个测试把 QUOTA_DB 指到临时文件，绝不碰真正的 quota.db。
"""
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import quota

_BJ = timezone(timedelta(hours=8))


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """每个测试一个空库；数值改小便于触阈值，跑完自动还原。"""
    monkeypatch.setenv("QUOTA_DB", str(tmp_path / "quota_test.db"))
    monkeypatch.setattr(quota, "FREE_AI_PER_DAY", 3, raising=True)
    monkeypatch.setattr(quota, "IP_FREE_AI_LIMIT", 8, raising=True)
    monkeypatch.setattr(quota, "SITE_SOFT_LIMIT", 4, raising=True)
    monkeypatch.setattr(quota, "SITE_HARD_LIMIT", 5, raising=True)
    yield


def _use(owner: str = "dev-a", ip: str = "1.1.1.1", signin: bool = True) -> dict:
    """签到（默认签）+ 取用一次免费额度。"""
    if signin:
        quota.signin(owner)
    return quota.acquire_free(owner, ip)


# ------------------------------------------------------------
# 1. 签到与文案
# ------------------------------------------------------------
def test_signin_is_required():
    """没签到不给用，且**说清下一步**——不能只说"额度已满"。"""
    r = _use(signin=False)
    assert r["allowed"] is False
    assert r["scope"] == "signin"
    assert "签到" in r["message"] and r["hint"]
    assert quota.status_for("dev-a", "1.1.1.1")["signed"] is False


def test_signin_then_three_times_then_denied():
    quota.signin("dev-a")
    for i in range(3):
        assert _use()["allowed"] is True, "第 %d 次应放行" % (i + 1)
    r = _use()
    assert r["allowed"] is False
    assert r["scope"] == "device"
    assert r["used"] == 3
    assert "不累加" in r["message"], "拒绝文案要写明不累加，否则用户会以为明天能攒"


def test_signin_is_idempotent():
    """重复签到不叠加次数，也不报错。"""
    quota.signin("dev-a")
    quota.signin("dev-a")
    st = quota.status_for("dev-a", "1.1.1.1")
    assert st["signed"] is True and st["free_left"] == quota.FREE_AI_PER_DAY


def test_degrade_message_is_verbatim():
    """站长定的原句，一字不改。改这句等于改对外承诺，必须是一次有意识的决定。"""
    assert quota.DEGRADE_MESSAGE == "今日 AI 解读额度已满，排盘与卦象仍可正常使用，明日 0 点恢复。"
    assert "错误" not in quota.DEGRADE_MESSAGE and "失败" not in quota.DEGRADE_MESSAGE


# ------------------------------------------------------------
# 2. 跨天不结转（站长 2026-10-02 明确要求）
# ------------------------------------------------------------
def test_no_carryover_from_yesterday():
    """昨天的剩余次数不许带到今天。

    造法：直接往库里写"昨天"的行（签到 + 用掉 3 次），再看今天的口径是否从 0 起算。
    """
    y = (datetime.now(_BJ) - timedelta(days=1)).strftime("%Y-%m-%d")
    with quota._LOCK, quota._connect() as conn:
        conn.execute("INSERT OR IGNORE INTO signin_daily(day, owner, ts) VALUES(?,?,?)",
                     (y, "dev-a", "2026-01-01T00:00:00+08:00"))
        quota._put(conn, y, quota._DEV_PREFIX + "dev-a", 1, 0)      # 昨天用掉 1 次、还剩 2 次
    quota.signin("dev-a")
    st = quota.status_for("dev-a", "1.1.1.1")
    assert st["free_used"] == 0, "昨天的用量被算进了今天"
    assert st["free_left"] == quota.FREE_AI_PER_DAY, "昨天的剩余次数被结转到了今天"


def test_today_uses_beijing_time_not_server_tz():
    """服务器时区错了也不影响重置时点——这是"明日 0 点恢复"能兑现的前提。"""
    assert quota.today() == datetime.now(_BJ).strftime("%Y-%m-%d")


def test_resets_at_is_next_beijing_midnight():
    iso = quota.resets_at()
    dt = datetime.fromisoformat(iso)
    assert dt.utcoffset() == timedelta(hours=8), "重置时刻必须带 +08:00"
    assert (dt.hour, dt.minute, dt.second) == (0, 0, 0)
    now = datetime.now(_BJ)
    assert dt > now
    assert dt - now <= timedelta(days=1, seconds=1)


# ------------------------------------------------------------
# 3. 阈值与"拦下后不再计数"
# ------------------------------------------------------------
def test_ip_backstop_blocks_after_limit(monkeypatch):
    """IP 兜底：同一条网络出口换设备签到也不能无限刷。"""
    monkeypatch.setattr(quota, "IP_FREE_AI_LIMIT", 5, raising=True)
    monkeypatch.setattr(quota, "SITE_HARD_LIMIT", 50, raising=True)   # 本测只测 IP 那道闸
    used = 0
    for i in range(5):
        owner = "dev-%d" % i          # 每次换设备（各签各的到），模拟"清掉令牌再签"
        quota.signin(owner)
        r = quota.acquire_free(owner, "9.9.9.9")
        assert r["allowed"] is True, "第 %d 次不该被拦" % (i + 1)
        used += 1
    owner = "dev-x"
    quota.signin(owner)
    r = quota.acquire_free(owner, "9.9.9.9")
    assert r["allowed"] is False
    assert r["scope"] == "ip"
    assert r["used"] == 5, "拦下时 used 应停在阈值上"


def test_other_ip_unaffected_by_one_ip_exhausting(monkeypatch):
    """单 IP 用尽不该连坐别人——这正是当初加 XFF 支持要解决的问题。"""
    monkeypatch.setattr(quota, "IP_FREE_AI_LIMIT", 3, raising=True)
    monkeypatch.setattr(quota, "SITE_HARD_LIMIT", 50, raising=True)
    for i in range(3):
        owner = "dev-%d" % i
        quota.signin(owner)
        quota.acquire_free(owner, "3.3.3.3")
    quota.signin("dev-other")
    assert quota.acquire_free("dev-other", "3.3.3.3")["allowed"] is False
    quota.signin("dev-far")
    assert quota.acquire_free("dev-far", "4.4.4.4")["allowed"] is True


def test_site_hard_limit_blocks_everyone(monkeypatch):
    """全站硬阈值：换设备换 IP 都没用（这是"一天最多花多少钱"的那道闸）。"""
    monkeypatch.setattr(quota, "IP_FREE_AI_LIMIT", 99, raising=True)
    used = 0
    i = 0
    while used < quota.SITE_HARD_LIMIT:
        owner = "dev-%d" % i
        quota.signin(owner)
        r = quota.acquire_free(owner, "10.0.0.%d" % i)
        assert r["allowed"] is True, "全站第 %d 次不该被拦" % (used + 1)
        used += 1
        i += 1
    quota.signin("dev-last")
    r = quota.acquire_free("dev-last", "10.0.0.99")
    assert r["allowed"] is False
    assert r["scope"] == "site"
    assert r["used"] == quota.SITE_HARD_LIMIT, "拦下时 used 应停在阈值上"


def test_blocked_calls_do_not_inflate_counter():
    """被拦之后计数不再增长——否则"今日已用"会一路虚涨，次日前的用量完全失真。"""
    quota.signin("dev-a")
    for _ in range(3):
        _use()
    before = quota.status()["used"]
    for _ in range(10):
        _use()
    assert quota.status()["used"] == before


# ------------------------------------------------------------
# 4. 软阈值：只告警一次
# ------------------------------------------------------------
def test_soft_threshold_alerts_exactly_once(monkeypatch):
    monkeypatch.setattr(quota, "IP_FREE_AI_LIMIT", 99, raising=True)
    alerts = []
    for i in range(quota.SITE_SOFT_LIMIT + 1):
        owner = "dev-%d" % i
        quota.signin(owner)
        r = quota.acquire_free(owner, "6.6.%d.1" % i)
        if r.get("alert"):
            alerts.append(r.get("site_used"))
    assert len(alerts) == 1, "软阈值只该报一次（重复发信 = 信息轰炸）"
    assert alerts[0] >= quota.SITE_SOFT_LIMIT


def test_soft_mailed_flag_survives_reload(monkeypatch):
    """mailed 落库：进程重启也不会把同一阈值再报一遍。"""
    monkeypatch.setattr(quota, "IP_FREE_AI_LIMIT", 99, raising=True)
    for i in range(quota.SITE_SOFT_LIMIT):
        owner = "dev-%d" % i
        quota.signin(owner)
        quota.acquire_free(owner, "7.7.%d.1" % i)
    assert quota.status()["soft_mailed"] is True
    quota.signin("dev-after")
    assert quota.acquire_free("dev-after", "8.8.8.8")["alert"] is False


# ------------------------------------------------------------
# 5. 状态口径一致 / 坏库放行 / 重置
# ------------------------------------------------------------
def test_status_matches_usage():
    quota.signin("dev-a")
    _use()
    st = quota.status_for("dev-a", "1.1.1.1")
    assert st["free_used"] == 1 and st["free_left"] == quota.FREE_AI_PER_DAY - 1
    assert st["signed"] is True
    assert st["resets_at"] == quota.resets_at()
    site = quota.status()
    assert site["used"] == 1
    assert site["degraded"] is False
    assert site["remaining"] == quota.SITE_HARD_LIMIT - 1


def test_status_reports_degraded_at_hard_limit(monkeypatch):
    monkeypatch.setattr(quota, "IP_FREE_AI_LIMIT", 99, raising=True)
    for i in range(quota.SITE_HARD_LIMIT):
        owner = "dev-%d" % i
        quota.signin(owner)
        quota.acquire_free(owner, "11.0.0.%d" % i)
    st = quota.status()
    assert st["degraded"] is True
    assert st["used"] == quota.SITE_HARD_LIMIT
    assert st["remaining"] == 0


def test_count_failure_allows_request(monkeypatch):
    """计数坏掉时**放行**：护栏不该变成新的故障源，把正常用户挡在外面。"""
    def _boom(*a, **kw):
        raise sqlite3.OperationalError("模拟：库不可写")
    monkeypatch.setattr(quota, "_connect", _boom)
    r = quota.acquire_free("dev-a", "12.12.12.12")
    assert r["allowed"] is True
    assert r.get("count_error")
    # 只读状态也不能抛
    assert "error" in quota.status_for("dev-a", "12.12.12.12")


def test_reset_clears_today():
    quota.signin("dev-a")
    _use()
    assert quota.status()["used"] == 1
    assert quota.status_for("dev-a", "1.1.1.1")["signed"] is True
    n = quota.reset()
    assert n >= 2, "重置要同时清掉用量行与签到行"
    assert quota.status()["used"] == 0
    assert quota.status_for("dev-a", "1.1.1.1")["signed"] is False


def test_alert_text_mentions_both_thresholds():
    txt = quota.alert_text(quota.SITE_SOFT_LIMIT)
    assert str(quota.SITE_SOFT_LIMIT) in txt and str(quota.SITE_HARD_LIMIT) in txt
    # 必须说清"不会关站"——这是这套设计的取向，不能只在代码注释里
    assert "不会关站" in txt
