# -*- coding: utf-8 -*-
"""
每日配额与优雅降级（防刷 · 成本护栏）
=====================================
两道闸，顺序是"先告警、后降级"，而且降级时**不关站**：

  · 每设备每日 3 次（签到后可用）—— 2026-10-02 由站长定的新口径
  · 每 IP 每日 20 次兜底          —— 防"清掉本地令牌再签到"反复刷
  · 全站每日软阈值 80 次          —— 只发一封告警邮件给站长，**不拦任何人**
  · 全站每日硬阈值 100 次         —— 排盘/卦象/体用/处方五行/应期照常给，只把"AI 解读"关掉

## 2026-10-02 的改动：从"按 IP 50 次"改成"按设备 3 次 + 签到"

站长的定义（原文）："每 IP 每天 50 次的免费额度去除，因为我定义的是用户自己可以调用
他自己的 api，这样他就可以无限 ai 解卦，然后对于没有 api 的用户就给他每日三次的 ai 解卦。"

于是免费路径变成：**签到后当日 3 次，跨天不结转**（昨天的余额不累加到今天——
按"设备 + 日期"记当日已用次数，跨天自然归零，不存余额）。用户自带 key 时**不走这里**，
既不计数也不拦截（key 是用户自己的，花的是他自己的钱）。

## 为什么免费路径要签到

签到把"匿名可用"变成"有一个动作在前"。它不解决防刷（清令牌就能重签），所以防刷仍靠
IP 兜底与全站硬阈值；签到的价值是让用户知道额度是有限的、以及顺便有一个回访动作。

## 时间与持久化

一律按**北京时间 0 点**重置（下式显式取 +08:00，与服务器时区无关）。
计数落 `quota.db`（单表 quota_daily，另有 signin_daily）：内存计数会在重启后清零，
等于"当天额度可以靠重启白送"；这份计数本身不值钱，故**刻意不进备份清单**。

## 已知局限（写在这里，而不是假装没有）

  · 单进程 + SQLite：多进程/多机部署时各算各的（本站在 systemd 里固定单 worker）；
  · 按 IP 兜底在运营商大 NAT 下会误伤——所以单 IP 限额（20）**故意大于**真人一天的用量
    （3 次/设备 × 若干部），真正兜底的是全站硬阈值；
  · 只统计"发起调用"这一下，不区分上游是否真的成功（宁可多算，不可少算）。
"""
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

_CST = timezone(timedelta(hours=8))          # 北京时间：重置时点与"明日 0 点"以此为准
_SITE_KEY = "__site__"                       # 全站计数行的 key（真实 IP 不会长这样）
_DEV_PREFIX = "dev:"                         # 每设备计数行的前缀（设备令牌在局域网内不可能是这个形状）
_IPF_PREFIX = "ipf:"                         # 免费路径的 IP 兜底计数前缀
_LOCK = threading.Lock()                     # 读改写不是原子的，串行化免得并发下漏计


def _env_int(name: str, default: int) -> int:
    try:
        v = int((os.environ.get(name) or "").strip())
        return v if v > 0 else default
    except Exception:
        return default


def _db_path() -> Path:
    """允许用环境变量指到别处：测试用临时库，免得污染真计数。"""
    p = (os.environ.get("QUOTA_DB") or "").strip()
    return Path(p) if p else (Path(__file__).parent / "quota.db")


FREE_AI_PER_DAY = _env_int("QUOTA_FREE_AI_DAILY", 3)     # 每设备每天（签到后）免费次数
IP_FREE_AI_LIMIT = _env_int("QUOTA_FREE_IP_DAILY", 20)   # 每 IP 每天兜底（防清令牌重签）
SITE_SOFT_LIMIT = _env_int("QUOTA_SITE_SOFT", 80)
SITE_HARD_LIMIT = _env_int("QUOTA_SITE_HARD", 100)

# 站长指定的原文，一字不改。前端拿这句直接渲染，不要在别处再写一份。
DEGRADE_MESSAGE = "今日 AI 解读额度已满，排盘与卦象仍可正常使用，明日 0 点恢复。"

# 降级时给的补充说明（与上面那句分开：上面是站长定的对外文案，
# 这里是"那还能做什么"的操作指引，可以说改就改，不动主文案）。
DEGRADE_HINT = "排盘、卦象、体用、处方五行与应期日期不受影响；今日仍可继续起卦看卦，AI 白话解读明日恢复。"

# 免费路径的三种拦截文案（与全站降级分开：这三种都有明确、可执行的下一步）
SIGNIN_MESSAGE = "今天的免费 AI 解读需要先签到：签到后当日可用 %d 次，跨天不累加。" % FREE_AI_PER_DAY
SIGNIN_HINT = "在「API 设置」页点一下签到即可；也可以填入自己的模型 key，之后不限次数（花的是你自己的额度）。"
USED_MESSAGE = "今天的免费 AI 解读已用完（每天 %d 次，昨天的次数不累加到今天），明日 0 点恢复。" % FREE_AI_PER_DAY
USED_HINT = "排盘、卦象、体用、处方五行与应期日期不受影响。想要不限次数，可在「API 设置」里填自己的模型 key。"
IP_MESSAGE = "同一网络出口今天的免费 AI 解读次数已达上限（%d 次），明日 0 点恢复。" % IP_FREE_AI_LIMIT
IP_HINT = ("这是为了防「清掉本地记录再签到」而设的兜底限制。填入自己的模型 key 可不受此限。")


# ============================================================
# 时间：显式按北京时间
# ============================================================
def today() -> str:
    """北京时间的今天（YYYY-MM-DD）。不用服务器本地日期，见模块头的说明。"""
    return datetime.now(_CST).strftime("%Y-%m-%d")


def resets_at() -> str:
    """下一次重置的绝对时刻（北京时间次日 0 点，ISO 8601 带 +08:00）。"""
    now = datetime.now(_CST)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.isoformat(timespec="seconds")


# ============================================================
# 存储
# ============================================================
def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.execute("""CREATE TABLE IF NOT EXISTS quota_daily (
                        day         TEXT    NOT NULL,
                        key         TEXT    NOT NULL,
                        n           INTEGER NOT NULL DEFAULT 0,
                        soft_mailed INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (day, key))""")
    # 签到表：一天一行（day + owner）。**不存余额**——跨天要不要给次数，由当天的行决定，
    # 这正是"昨天的次数不累加到今天"在存储上的实现方式。
    conn.execute("""CREATE TABLE IF NOT EXISTS signin_daily (
                        day   TEXT NOT NULL,
                        owner TEXT NOT NULL,
                        ts    TEXT NOT NULL,
                        PRIMARY KEY (day, owner))""")
    return conn


def _row(conn: sqlite3.Connection, day: str, key: str) -> tuple:
    r = conn.execute("SELECT n, soft_mailed FROM quota_daily WHERE day=? AND key=?",
                     (day, key)).fetchone()
    return (int(r[0]), int(r[1])) if r else (0, 0)


def _put(conn: sqlite3.Connection, day: str, key: str, n: int, mailed: int) -> None:
    conn.execute("""INSERT INTO quota_daily(day, key, n, soft_mailed) VALUES(?,?,?,?)
                    ON CONFLICT(day, key) DO UPDATE SET n=excluded.n,
                                                        soft_mailed=excluded.soft_mailed""",
                 (day, key, n, mailed))


# ============================================================
# 查询（只读，供 /api/health 与前端）
# ============================================================
def status() -> dict:
    """全站用量与阈值（供 /api/health 与站长查看）。个人视角用 status_for()。"""
    day = today()
    try:
        with _LOCK, _connect() as conn:
            site, mailed = _row(conn, day, _SITE_KEY)
    except Exception as e:                      # 库坏了不该让健康检查 500
        return {"day": day, "used": None, "error": "%s: %s" % (type(e).__name__, e),
                "free_ai_limit": FREE_AI_PER_DAY, "ip_limit": IP_FREE_AI_LIMIT,
                "soft_limit": SITE_SOFT_LIMIT,
                "hard_limit": SITE_HARD_LIMIT, "degraded": False,
                "soft_mailed": False, "resets_at": resets_at(), "message": DEGRADE_MESSAGE}
    return {
        "day": day,
        "used": site,
        "remaining": max(0, SITE_HARD_LIMIT - site),
        "free_ai_limit": FREE_AI_PER_DAY, "ip_limit": IP_FREE_AI_LIMIT,
        "soft_limit": SITE_SOFT_LIMIT, "hard_limit": SITE_HARD_LIMIT,
        "degraded": site >= SITE_HARD_LIMIT,
        "soft_reached": site >= SITE_SOFT_LIMIT,
        "soft_mailed": bool(mailed),
        "resets_at": resets_at(),
        "message": DEGRADE_MESSAGE,
    }


def reset(day: str = "") -> int:
    """把某天（默认今天）的计数与签到记录清掉，返回删掉的行数。给测试与站长应急用。"""
    d = day or today()
    with _LOCK, _connect() as conn:
        c1 = conn.execute("DELETE FROM quota_daily WHERE day=?", (d,))
        c2 = conn.execute("DELETE FROM signin_daily WHERE day=?", (d,))
        return int((c1.rowcount or 0) + (c2.rowcount or 0))


# ============================================================
# 签到（免费路径的入口）
# ============================================================
def signin(owner: str) -> dict:
    """今日签到；幂等（重复签到不报错、不叠加次数）。返回个人额度状态。"""
    day = today()
    o = (owner or "").strip()[:128] or "unknown"
    ts = datetime.now(_CST).isoformat(timespec="seconds")
    try:
        with _LOCK, _connect() as conn:
            conn.execute("INSERT OR IGNORE INTO signin_daily(day, owner, ts) VALUES(?,?,?)",
                         (day, o, ts))
    except Exception:
        pass                                     # 签到失败不让整页报错，状态查询会如实反映
    return status_for(o, "")


def status_for(owner: str, client_ip: str = "") -> dict:
    """某个设备的今日免费额度状态（**不产生用量**，只读）。

    跨天不结转：这里只读"今天这一行"，昨天用剩几次一概不参与计算。
    """
    day = today()
    o = (owner or "").strip()[:128] or "unknown"
    ip = ((client_ip or "")[:64] or "unknown")
    out = {"day": day, "free_limit": FREE_AI_PER_DAY,
           "signed": False, "free_used": 0, "free_left": FREE_AI_PER_DAY,
           "ip_limit": IP_FREE_AI_LIMIT, "ip_used": 0,
           "site_used": 0, "site_hard": SITE_HARD_LIMIT,
           "resets_at": resets_at()}
    try:
        with _LOCK, _connect() as conn:
            signed = conn.execute("SELECT 1 FROM signin_daily WHERE day=? AND owner=?",
                                  (day, o)).fetchone() is not None
            used, _ = _row(conn, day, _DEV_PREFIX + o)
            ip_used, _ = _row(conn, day, _IPF_PREFIX + ip)
            site, _ = _row(conn, day, _SITE_KEY)
    except Exception as e:
        out["error"] = "%s: %s" % (type(e).__name__, e)
        return out                                  # 计数不可用时前端仍能渲染（按 0 显示）
    out.update({"signed": bool(signed), "free_used": used,
                "free_left": max(0, FREE_AI_PER_DAY - used) if signed else 0,
                "ip_used": ip_used, "site_used": site})
    return out


# ============================================================
# 取用（核心）
# ============================================================
def acquire_free(owner: str, client_ip: str) -> dict:
    """尝试取用一次**免费** AI 解读（自带 key 的路径不走这里）。

    返回 dict（**不抛异常**——调用点都在流式端点里，抛异常会变成一整页 500，
    而这里要的是"把卦象照常给出去、只少一段 AI 文字"）：
        allowed     True=放行；False=应降级（调用方**不要**再调 LLM）
        scope       ""｜"signin"（未签到）｜"device"（当日 3 次用完）｜"ip"｜"site"
        message     对外文案（站长原文或对应的免费路径文案）
        hint        补充指引
        alert       True=本次刚好越过软阈值，调用方应发一封告警邮件
        used/limit  当前用量与所触阈值，便于日志与排查
    """
    day = today()
    o = (owner or "").strip()[:128] or "unknown"
    ip = ((client_ip or "")[:64] or "unknown")
    dkey, ikey = _DEV_PREFIX + o, _IPF_PREFIX + ip
    out = {"allowed": True, "scope": "", "message": "", "hint": "",
           "alert": False, "used": 0, "limit": FREE_AI_PER_DAY,
           "free_limit": FREE_AI_PER_DAY, "resets_at": resets_at(),
           "ip_limit": IP_FREE_AI_LIMIT, "soft_limit": SITE_SOFT_LIMIT,
           "hard_limit": SITE_HARD_LIMIT}

    def _deny(scope: str, used: int, limit: int, message: str, hint: str) -> dict:
        out.update({"allowed": False, "scope": scope, "used": used, "limit": limit,
                    "message": message, "hint": hint})
        return out

    try:
        with _LOCK, _connect() as conn:
            site, mailed = _row(conn, day, _SITE_KEY)
            dev_n, _ = _row(conn, day, dkey)
            ip_n, _ = _row(conn, day, ikey)
            signed = conn.execute("SELECT 1 FROM signin_daily WHERE day=? AND owner=?",
                                  (day, o)).fetchone() is not None

            # 顺序：先全站（成本天花板）→ 再签到 → 再设备 → 再 IP。
            # 全站已满时不计任何数，免得计数继续涨、次日零点前的用量失真。
            if site >= SITE_HARD_LIMIT:
                return _deny("site", site, SITE_HARD_LIMIT, DEGRADE_MESSAGE, DEGRADE_HINT)
            if not signed:
                return _deny("signin", 0, FREE_AI_PER_DAY, SIGNIN_MESSAGE, SIGNIN_HINT)
            if dev_n >= FREE_AI_PER_DAY:
                return _deny("device", dev_n, FREE_AI_PER_DAY, USED_MESSAGE, USED_HINT)
            if ip_n >= IP_FREE_AI_LIMIT:
                return _deny("ip", ip_n, IP_FREE_AI_LIMIT, IP_MESSAGE, IP_HINT)

            site_new, dev_new, ip_new = site + 1, dev_n + 1, ip_n + 1
            _put(conn, day, _SITE_KEY, site_new, mailed)
            _put(conn, day, dkey, dev_new, 0)
            _put(conn, day, ikey, ip_new, 0)

            # 软阈值：只报一次（mailed 落库，重启也不会重复发）
            if site_new >= SITE_SOFT_LIMIT and not mailed:
                _put(conn, day, _SITE_KEY, site_new, 1)
                out["alert"] = True

            out.update({"used": dev_new, "limit": FREE_AI_PER_DAY,
                        "site_used": site_new, "free_left": max(0, FREE_AI_PER_DAY - dev_new)})
            return out
    except Exception as e:
        # 计数失败时**放行**：护栏坏掉不该让正常用户用不了站。
        # 这条与"宁可多算"不冲突——多算是计数正常时的取向，这里是计数根本不可用的降级取向。
        out.update({"used": -1, "limit": FREE_AI_PER_DAY,
                    "count_error": "%s: %s" % (type(e).__name__, e)})
        return out


def alert_text(used: int) -> str:
    """软阈值告警邮件正文（由调用方交给 mailer.send）。"""
    return "\n".join([
        "【观候·转明·用量告警】今日 AI 解读已到软阈值。",
        "",
        "今日已用：%d 次（软阈值 %d · 硬降级 %d）" % (used, SITE_SOFT_LIMIT, SITE_HARD_LIMIT),
        "预计今日上限花费 ≈ %.1f 元（按 0.02 元/次估算）" % (SITE_HARD_LIMIT * 0.02),
        "",
        "————————————",
        "达到硬阈值后本站不会关站：排盘、卦象、体用、处方五行与应期照常，",
        "只把 AI 白话解读关掉，并在页面上如实说明（明日 0 点恢复）。",
        "",
        "若今天是被刷量：查 nginx/后端日志里同一 IP 的密集请求；",
        "若确是真实用户增长：可上调 backend/.env 的 QUOTA_SITE_HARD（改完重启后端）。",
    ])
