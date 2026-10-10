# -*- coding: utf-8 -*-
"""
健康检查 / 兜底自检（自检清单 D）
================================
一个端点看清"上线后最容易悄悄挂掉的东西"：
  · LLM 是否配置、**余额还剩多少**（余额耗尽 = 全站 AI 直接挂，是最容易忽视的单点）
  · ASR（语音）与 SMTP（反馈邮件）是否配置
  · CORS 是收紧到域名还是仍然通配、是否信任代理头
  · 库里有多少档案/记录/台账（顺带确认数据库可读）

安全约定：**只回"配没配"与公开信息，绝不回密钥、授权码、令牌**。
余额查询走 DeepSeek 的 /user/balance（只读、不计费），带 8 秒超时与 10 分钟缓存，
免得健康检查本身把上游打爆。
"""
import json
import os
import sqlite3
import time
import urllib.request
from pathlib import Path

_BALANCE_CACHE: dict = {"ts": 0.0, "data": None}
_BALANCE_TTL = 600          # 10 分钟内复用上次结果
BALANCE_WARN_CNY = 5.0      # 低于这个余额视为告警（跑几次长断语就没了）


def _env(key: str) -> str:
    return (os.environ.get(key) or "").strip()


def llm_balance(timeout: float = 8.0, force: bool = False) -> dict:
    """查 LLM 余额（DeepSeek 兼容端点）。不配置 key 时返回 configured=False。"""
    key = _env("LLM_API_KEY")
    base = (_env("LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    if not key:
        return {"configured": False, "ok": False, "error": "未配置 LLM_API_KEY"}
    now = time.time()
    if not force and _BALANCE_CACHE["data"] and now - _BALANCE_CACHE["ts"] < _BALANCE_TTL:
        return _BALANCE_CACHE["data"]
    out = {"configured": True, "ok": False, "base_url": base, "model": _env("LLM_MODEL")}
    try:
        req = urllib.request.Request(f"{base}/user/balance",
                                     headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        infos = data.get("balance_infos") or []
        cny = next((i for i in infos if i.get("currency") == "CNY"), infos[0] if infos else None)
        if cny:
            total = float(cny.get("total_balance") or 0)
            out.update({
                "ok": True, "currency": cny.get("currency"), "total": cny.get("total_balance"),
                "available": bool(data.get("is_available", True)),
                "low": total < BALANCE_WARN_CNY, "warn_below": BALANCE_WARN_CNY,
            })
        else:
            out.update({"ok": True, "note": "接口未返回余额明细"})
    except Exception as e:                       # 网络/密钥问题都不该让健康检查 500
        out["error"] = f"{type(e).__name__}: {getattr(e, 'code', '') or e}"
    _BALANCE_CACHE.update({"ts": now, "data": out})
    return out


def timezone_info() -> dict:
    """服务器时区体检（自检 B7）——**这一项错了会静默算错日期**。

    为什么单列：后端有 7 处取"现在几号/几时"决定**结果正确性**（择日起点 zeri.py:65、
    应期起点 yingqi.py:95/157、岁运 liunian.py:41、黄历与起卦默认时辰 main.py:743/800/1146/1158），
    用的都是本地时区的 `datetime.now()` / `date.today()`。云镜像（尤其 Ubuntu/Debian 海外与非大陆节点）
    默认常是 UTC，于是**北京时间每天 08:00 之前，"今天"会被算成昨天** ——
    黄历、择日、应期整体错一天，而用户只会觉得"算得不准"，看代码看不出来。

    这里给两个字段，含义不同、别混：
      · ok=False     配置不对（时区不是 +08:00）——**隐患**
      · date_differs=True  本地日期与北京日期**此刻已经不同**——**正在出错**
    UTC 机器上，每天 00:00–08:00（北京时间）这段 date_differs 为 True，其余时段为 False
    ——所以它不能单独当判据，ok 才是配置层的判据。
    """
    from datetime import datetime, timedelta, timezone as _tz
    now = datetime.now()                      # 本地（服务器）时间
    bj = datetime.now(_tz(timedelta(hours=8)))  # 北京时间为准
    off = now.astimezone().utcoffset() or timedelta(0)
    hours = round(off.total_seconds() / 3600.0, 2)
    out = {
        "tzname": time.tzname[0] if time.tzname else "",
        "utc_offset_hours": hours,
        "local": now.isoformat(timespec="seconds"),
        "beijing": bj.isoformat(timespec="seconds"),
        "ok": abs(hours - 8.0) < 1e-9,
        "date_differs": now.date() != bj.date(),
    }
    if not out["ok"]:
        out["warning"] = (
            "服务器时区不是 +08:00（当前 %+.2f 小时）：黄历「今日」、择日起点、应期与岁运"
            "会按本地日期算，整体偏一天。修复：timedatectl set-timezone Asia/Shanghai"
            "（并在 systemd 单元里加 Environment=TZ=Asia/Shanghai 双保险），随后重启后端。"
            % hours)
    elif time.tzname and time.tzname[0] not in ("CST",):
        # 偏移对但名字不是 CST：tzdata 缺失/别名时的边缘情况，提示但不判失败
        out["note"] = "偏移已是 +08:00，但时区名为 %s（期望 CST）——取自 POSIX TZ 变量亦可接受" % time.tzname[0]
    return out


def _quota_status() -> dict:
    """每日配额（自检 D6）：额度用尽会静默降级为"仅排盘"，这里看得见。"""
    try:
        from quota import status as _q
        return _q()
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}


def _db_counts() -> dict:
    """库可读性 + 规模（健康检查顺手确认数据库没坏）。"""
    counts: dict = {}
    try:
        from records import _DB_PATH as records_db
        with sqlite3.connect(records_db) as conn:
            for name, sql in (("profiles", "SELECT COUNT(*) FROM profiles"),
                              ("records", "SELECT COUNT(*) FROM records WHERE deleted_at IS NULL OR deleted_at=''"),
                              ("check_log", "SELECT COUNT(*) FROM check_log")):
                try:
                    counts[name] = conn.execute(sql).fetchone()[0]
                except sqlite3.OperationalError:
                    counts[name] = None
        counts["db"] = str(records_db)
    except Exception as e:
        counts["error"] = f"{type(e).__name__}: {e}"
    return counts


def snapshot(balance: bool = True) -> dict:
    """一眼看清的运行时快照（不含任何密钥）。"""
    try:
        from rules_meta import RULES_VERSION
        from weights import WEIGHTS_VERSION
        versions = {"rules": RULES_VERSION, "weights": WEIGHTS_VERSION}
    except Exception:
        versions = {}
    # CORS / 代理：直接从 main 取实际生效值（避免这里再算一遍、算岔了）
    try:
        import main as _m
        cors = {"origins": list(getattr(_m, "CORS_ORIGINS", [])),
                "wildcard": bool(getattr(_m, "CORS_ALLOW_ALL", False)),
                "trust_proxy": bool(getattr(_m, "TRUST_PROXY", False))}
    except Exception:
        cors = {"origins": [], "wildcard": None, "trust_proxy": None}
    if cors.get("wildcard"):
        cors["warning"] = "CORS 仍为通配符：任意网站都能用访客浏览器调用本站 API（会烧 LLM 余额）"
    if not cors.get("trust_proxy"):
        cors["note"] = "未信任 X-Forwarded-For（直连公网时应如此；若确实在 Nginx 后面则全站共用一个限流桶，见自检 B4）"

    smtp_host = _env("SMTP_HOST")
    return {
        "ok": True,
        "versions": versions,
        "llm": llm_balance() if balance else {"configured": bool(_env("LLM_API_KEY"))},
        "asr": {"configured": bool(_env("ASR_API_KEY")), "provider": _env("ASR_PROVIDER"),
                "base_url": _env("ASR_BASE_URL"), "model": _env("ASR_MODEL")},
        "smtp": {"configured": bool(smtp_host and _env("SMTP_USER")), "host": smtp_host,
                 "to_configured": bool(_env("FEEDBACK_TO"))},
        "cors": cors,
        "timezone": timezone_info(),
        "quota": _quota_status(),
        "data": _db_counts(),
    }


def low_balance_warning() -> str:
    """给定时任务用：余额偏低/不可用时返回一句人话，否则空串。"""
    b = llm_balance(force=True)
    if not b.get("configured"):
        return "LLM 未配置：全站 AI 功能不可用"
    if not b.get("ok"):
        return f"LLM 余额查询失败（{b.get('error')}）——可能密钥失效或网络不通"
    total = float(b.get("total") or 0)
    if not b.get("available", True):
        return f"LLM 账户不可用（余额 {total} {b.get('currency')}）——AI 功能会全部失败"
    if total < BALANCE_WARN_CNY:
        return f"LLM 余额偏低：{total} {b.get('currency')}（低于 {BALANCE_WARN_CNY}）——请尽快充值"
    return ""


def timezone_warning() -> str:
    """给启动检查与定时任务用：时区不对时返回一句人话（含修复命令），否则空串。

    与 low_balance_warning 同一个形状：`python tools/check_server.py` 用它决定退出码，
    main.py 的启动钩子用它打日志。
    """
    tz = timezone_info()
    if tz.get("ok"):
        if tz.get("date_differs"):
            # 偏移对却日期不同：只可能是 tzdata/时钟异常，值得单独喊一声
            return ("时区偏移正确但本地日期(%s)与北京日期(%s)不一致——请检查系统时钟与 tzdata"
                    % (tz.get("local"), tz.get("beijing")))
        return ""
    msg = tz.get("warning") or "服务器时区不是 +08:00"
    if tz.get("date_differs"):
        msg += "  ⚠ 此刻本地日期已与北京日期不同（%s vs %s），黄历/择日/应期正在算错。" % (
            str(tz.get("local"))[:10], str(tz.get("beijing"))[:10])
    return msg
