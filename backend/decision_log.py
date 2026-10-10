# -*- coding: utf-8 -*-
"""
决策日志（案例库地基）
======================
每次命卦校验追加一行完整推理链快照（时间/问题/档位/处方/命局基线/裁决/岁运/
规则版本/权重版本）。两个用途：
  1. "可复核"的最终形态——任何一条历史建议都能还原当时的全部输入与规则版本；
  2. 生产回流：用户轻量反馈（"所问之事后来如何"三选项）把日志变成
     "裁决—结果"配对，供敏感度分析与反例捕捉（不追求统计显著，
     核心用途是暴露系统性应验失败的反例样本）。
存储与命局档案同库（backend/mingju_profiles.db），表 check_log 只增不改
（反馈除外）。
"""
import json
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

_DB_PATH = Path(__file__).parent / "mingju_profiles.db"

# 内部聚合（校准分析）用的哨兵：明确表示"不按归属过滤"，只在服务端统计里用，绝不出接口
_UNSCOPED = "__all__"


def _connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_log_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS check_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                profile_id TEXT DEFAULT '',
                kind TEXT DEFAULT 'check',
                question TEXT DEFAULT '',
                tier TEXT DEFAULT '',
                tier_source TEXT DEFAULT '',
                R TEXT DEFAULT '',
                final_R TEXT DEFAULT '',
                F TEXT DEFAULT '[]',
                J TEXT DEFAULT '[]',
                T0 TEXT DEFAULT '[]',
                from_ge TEXT DEFAULT '',
                net TEXT DEFAULT '',
                level TEXT DEFAULT '',
                gate TEXT DEFAULT '',
                decision TEXT DEFAULT '',
                liunian_json TEXT DEFAULT '',
                month_wx TEXT DEFAULT '',
                day_zhi TEXT DEFAULT '',
                rules_version TEXT DEFAULT '',
                weights_version TEXT DEFAULT '',
                outcome TEXT DEFAULT '',
                outcome_ts TEXT DEFAULT '',
                extra_json TEXT DEFAULT '',
                flow_json TEXT DEFAULT ''
            )
        """)
        # 旧库补列（只增不改：加列迁移，列已存在则忽略）
        for col, ddl in (("kind", "TEXT DEFAULT 'check'"), ("extra_json", "TEXT DEFAULT ''"),
                         ("claims_json", "TEXT DEFAULT ''"), ("owner", "TEXT DEFAULT ''"),
                         ("flow_json", "TEXT DEFAULT ''"),
                         # actual_date：所问之事**实际发生**的日期（用户可选填）。
                         # 为什么单独一列而不是塞进 outcome：outcome 是"应验/未验/还没结果"，
                         # 而应期分析要的是"第几天发生的"——两个信息不能互相替代。
                         ("actual_date", "TEXT DEFAULT ''")):
            try:
                conn.execute(f"ALTER TABLE check_log ADD COLUMN {col} {ddl}")
            except sqlite3.OperationalError:
                pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_checklog_owner ON check_log(owner, id DESC)")

        # —— 断言回执码（长期反馈的窄凭证）——
        #
        # 要解决的问题：claim 级反馈的价值在**长验证窗口**（择日按周、岁运按月甚至跨年），
        # 但"设备即账户"的令牌活不到那天——iOS Safari 7 天不访问就清空 localStorage（WebKit
        # 官方行为）。一年后用户回来，服务端那 88 条台账还在，却认不出他是谁。
        #
        # 为什么不是"再加个账号"：症结不是身份缺失，而是**凭证粒度**只剩下两极——
        # 全权令牌（会过期）和什么都没有（无法作答）。这里补上中间态：
        # 一枚只对**一条断言**有效的回执码，可以躺在用户自己的日历/便签里活很久。
        # 持它还只能做一件事：提交这一条的裁定。读不到记录、改不了别的、看不到别人的东西。
        conn.execute("""
            CREATE TABLE IF NOT EXISTS claim_receipt (
                receipt TEXT PRIMARY KEY,
                log_id INTEGER NOT NULL,
                claim_id TEXT NOT NULL,
                owner TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                used_at TEXT DEFAULT ''
            )
        """)
        # 幂等：同一条断言恒返回同一枚回执码，否则"再次加入日历"会生成一串死链接
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_receipt_claim "
                     "ON claim_receipt(log_id, claim_id)")

        # —— 反馈语义层（claim 级）——
        conn.execute("""
            CREATE TABLE IF NOT EXISTS claim_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                log_id INTEGER NOT NULL,
                claim_id TEXT NOT NULL,
                verdict TEXT NOT NULL,
                note TEXT DEFAULT '',
                contact TEXT DEFAULT ''
            )
        """)
        # 边界样本（判据值擦阈即自动记账；唯一能喂阈值的样本来源）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS boundary_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                log_id INTEGER NOT NULL,
                param TEXT NOT NULL,
                value REAL,
                threshold REAL,
                side TEXT DEFAULT '',
                at_verdict TEXT DEFAULT ''
            )
        """)
        # 校准提案（只产出"待批"，绝不自动改数）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS calibration_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                param TEXT NOT NULL,
                old_value REAL,
                new_value REAL,
                sample_ids TEXT DEFAULT '[]',
                n_samples INTEGER DEFAULT 0,
                flip_rate REAL,
                status TEXT DEFAULT '待批',
                decided_at TEXT DEFAULT '',
                decided_by TEXT DEFAULT '',
                applied_version TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
        """)
        # 公测自由留言（带可选联系方式）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS beta_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                text TEXT NOT NULL,
                contact TEXT DEFAULT '',
                log_id INTEGER DEFAULT 0
            )
        """)
        # 只增列迁移：留言标题（整页反馈表单用）
        cols = {r[1] for r in conn.execute("PRAGMA table_info(beta_notes)")}
        if "title" not in cols:
            conn.execute("ALTER TABLE beta_notes ADD COLUMN title TEXT DEFAULT ''")


def issue_receipt(log_id: int, claim_id: str, owner: str) -> dict:
    """签发（或取回）一条断言的窄凭证。**幂等**：同一 (log_id, claim_id) 恒返回同一枚。

    幂等的理由：回执码会被写进用户日历，如果每次调用都换一枚，重新"加入日历"就会
    留下一串失效链接，用户会以为这功能坏了。稳定的一枚也便于事后排查。

    先校验日志归属（`_UNSCOPED` 之外不接受跨人签发），否则就成了"给别人的断言发凭证"。
    """
    if owner != _UNSCOPED and not get_log(log_id, owner):
        return {}
    claim_id = str(claim_id or "")
    if not claim_id:
        return {}
    init_log_db()
    with _connect() as conn:
        row = conn.execute("SELECT receipt FROM claim_receipt WHERE log_id=? AND claim_id=?",
                           (int(log_id), claim_id)).fetchone()
        if row:
            return {"receipt": row["receipt"], "log_id": int(log_id), "claim_id": claim_id}
        receipt = secrets.token_urlsafe(24)
        conn.execute("INSERT INTO claim_receipt(receipt, log_id, claim_id, owner, created_at) "
                     "VALUES(?,?,?,?,?)",
                     (receipt, int(log_id), claim_id, str(owner or ""),
                      datetime.now().isoformat(timespec="seconds")))
    return {"receipt": receipt, "log_id": int(log_id), "claim_id": claim_id}


def resolve_receipt(receipt: str) -> dict:
    """回执码 → {log_id, claim_id, owner}；无效返回 {}。

    这是**唯一**接受"非令牌凭证"的入口，所以范围必须窄到底：只回这三个字段，
    不接受任何客户端补充的 log_id/claim_id（否则又变成"客户端字段决定归属"）。
    """
    receipt = (receipt or "").strip()
    if not receipt or len(receipt) > 64:
        return {}
    init_log_db()
    with _connect() as conn:
        row = conn.execute("SELECT log_id, claim_id, owner FROM claim_receipt WHERE receipt=?",
                           (receipt,)).fetchone()
        if not row:
            return {}
        conn.execute("UPDATE claim_receipt SET used_at=? WHERE receipt=?",
                     (datetime.now().isoformat(timespec="seconds"), receipt))
    return {"log_id": int(row["log_id"]), "claim_id": row["claim_id"], "owner": row["owner"] or ""}


def receipt_of(log_id: int, claim_id: str, owner: str = "") -> str:
    """已有回执码（没有则空串）。用于反馈页显示"这条已可凭链接作答"。"""
    if owner and owner != _UNSCOPED and not get_log(log_id, owner):
        return ""
    init_log_db()
    with _connect() as conn:
        row = conn.execute("SELECT receipt FROM claim_receipt WHERE log_id=? AND claim_id=?",
                           (int(log_id), str(claim_id or ""))).fetchone()
    return row["receipt"] if row else ""


def append_check(record: dict) -> int:
    """追加一行校验记录，返回日志 id（前端反馈入口要回传它）。
    kind: 'check'（命卦校验，默认）| 'bazi'（八字排盘留痕）；
    extra: kind 专属快照（bazi → 四柱/阳历/农历；check → 来源与体用摘要）；
    claims: 本次输出的断言清单（claim 级反馈的对象，见 feedback.py）。

    **require_owner 之前必须先在这里拒绝无归属写入**：本表没有"无主数据"这个合法状态——
    无主的行谁读不到（各端点都 `WHERE owner=?`），等于静默丢数据；更糟的是原先这里用
    `owner or profile_id or ""` 兜底，而 profile_id 是**客户端可控值**，于是"客户端字段
    变成归属"这条错路又出现在数据层。故 owner 必须显式给出，缺失即报错。
    """
    init_log_db()
    owner = str(record.get("owner") or "").strip()
    if not owner or owner.startswith("__"):
        raise ValueError("append_check 需要显式且合法的 owner（不接受无归属或保留值）")
    now = datetime.now().isoformat(timespec="seconds")
    extra = record.get("extra")
    claims = record.get("claims")
    flow = record.get("flow")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO check_log(ts, profile_id, kind, question, tier, tier_source, R, final_R, "
            "F, J, T0, from_ge, net, level, gate, decision, liunian_json, month_wx, day_zhi, "
            "rules_version, weights_version, extra_json, claims_json, flow_json, owner) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                now,
                str(record.get("profile_id", "") or ""),
                str(record.get("kind", "check") or "check"),
                str(record.get("question", "") or "")[:200],
                str(record.get("tier", "") or ""),
                str(record.get("tier_source", "") or ""),
                str(record.get("R", "") or ""),
                str(record.get("final_R", "") or ""),
                json.dumps(record.get("F", []), ensure_ascii=False),
                json.dumps(record.get("J", []), ensure_ascii=False),
                json.dumps(record.get("T0", []), ensure_ascii=False),
                str(record.get("from_ge", "") or ""),
                str(record.get("net", "") or ""),
                str(record.get("level", "") or ""),
                str(record.get("gate", "") or ""),
                str(record.get("decision", "") or "")[:300],
                json.dumps(record.get("liunian"), ensure_ascii=False) if record.get("liunian") else "",
                str(record.get("month_wx", "") or ""),
                str(record.get("day_zhi", "") or ""),
                str(record.get("rules_version", "") or ""),
                str(record.get("weights_version", "") or ""),
                json.dumps(extra, ensure_ascii=False) if extra else "",
                json.dumps(claims, ensure_ascii=False) if claims else "",
                json.dumps(flow, ensure_ascii=False) if flow else "",
                str(record.get("owner", "") or ""),   # 已在函数开头校验非空（此处保留取值）
            ),
        )
        return cur.lastrowid


def set_feedback(log_id: int, outcome: str, owner: str = "", actual_date: str = "") -> bool:
    """用户回流：应验 / 未验 / 还没结果（只能改自己的日志）。

    actual_date：所问之事实际发生的日期（ISO，可空）。它对应期这一类判断最有用——
    "应期之日"说的是哪几天会应，只有拿到实际日期才能算出偏差几天。
    传空字符串时不覆盖已有值（避免用户第二次只点按钮就把日期抹掉）。
    """
    if outcome not in ("应验", "未验", "还没结果"):
        raise ValueError(f"非法反馈值: {outcome!r}")
    init_log_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        if actual_date:
            cur = conn.execute(
                "UPDATE check_log SET outcome=?, outcome_ts=?, actual_date=? WHERE id=? AND owner=?",
                (outcome, now, str(actual_date)[:10], int(log_id), str(owner or "")),
            )
        else:
            cur = conn.execute(
                "UPDATE check_log SET outcome=?, outcome_ts=? WHERE id=? AND owner=?",
                (outcome, now, int(log_id), str(owner or "")),
            )
    return cur.rowcount > 0


def recent(limit: int = 50, owner: str = "") -> list:
    """最近若干条日志；**只返回调用者自己的**（owner 为空则只返回无归属的老行，不跨人）。

    **刻意不返回 `flow_json`（整张流动表）**：它是详情级数据，一张表几 KB，
    而"我的记录"页一次要 60 行——带上它，打开一页就多传几百 KB。
    要看整表走 `flow_of(log_id)`（单条、限本人）。

    列名由 PRAGMA 现取而不是写死：本表是**只增不改**地加列的（`kind`/`extra_json`/
    `claims_json`/`owner`/`flow_json` 都是后补的），写死列名意味着以后每加一列
    都得回来改这里一次，漏一次就是"存了却读不出"。
    """
    init_log_db()
    with _connect() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(check_log)").fetchall()]
        sel = ",".join(c for c in cols if c != "flow_json")
        rows = conn.execute(
            f"SELECT {sel} FROM check_log WHERE owner=? ORDER BY id DESC LIMIT ?",
            (str(owner or ""), int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]


def flow_of(log_id: int, owner: str = "") -> list:
    """取某次校验当时的**整张流动五行判定表**（限本人）。

    为什么值得单独存一张表：R5 那条规矩要求"同源不告警时**不静默**，写明为何不告警"
    （`conflict_suppressed`）。此前那句话只写在接口返回里，**页面一关就没了**——
    等于"不静默"只做到了当场那一刻。整表入库后，事后能回答的不再只是
    "当时判了什么"，而是"当时那张表长什么样、哪一格被压制了、理由是什么"。

    返回 [] 表示该行没有存表（旧行）、或不属于调用者（不区分二者，同"与不存在同形"）。
    """
    init_log_db()
    with _connect() as conn:
        row = conn.execute("SELECT flow_json FROM check_log WHERE id=? AND owner=?",
                           (int(log_id), str(owner or ""))).fetchone()
    if not row or not row["flow_json"]:
        return []
    try:
        v = json.loads(row["flow_json"])
    except (ValueError, TypeError):
        return []
    return v if isinstance(v, list) else []


def outcomes(log_ids: list, owner: str = "") -> dict:
    """按 log_id 批量取反馈结论。

    用处：记录页把"应验/未验"作为**记录上的附件**显示——记录本身存的是
    回放快照，反馈存在决策日志里，这里做一次关联，让附件刷新后仍在。
    """
    ids = [int(i) for i in log_ids if isinstance(i, int)]
    if not ids:
        return {}
    init_log_db()
    q = ",".join("?" * len(ids))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT id, outcome FROM check_log WHERE id IN ({q}) AND owner=?", ids + [str(owner or "")]
        ).fetchall()
    return {int(r["id"]): (r["outcome"] or "") for r in rows}


# ===========================================================================
# 反馈语义层（claim 级）——见 feedback.py 的分层说明
# ===========================================================================

def get_log(log_id: int, owner: str = "") -> dict:
    """取单条决策日志（负反馈邮件要带上"所问之事"）——限本人。"""
    init_log_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM check_log WHERE id=? AND owner=?",
                           (int(log_id), str(owner or ""))).fetchone()
    return dict(row) if row else {}


def claims_of(log_id: int, owner: str = "") -> list:
    """取某次校验的断言清单（限本人）。

    `_UNSCOPED` 例外：校准是**服务端聚合统计**（要跨人取样算边界样本的翻转率），
    与 `feedback_of` 保持同一约定。该哨兵客户端构造不出来（`owner_of` 把 `__` 前缀的
    令牌一律映射成匿名值，`require_owner` 直接 403），故不构成越权入口。
    """
    init_log_db()
    sql = "SELECT claims_json FROM check_log WHERE id=?"
    args: list = [int(log_id)]
    if owner != _UNSCOPED:
        sql += " AND owner=?"
        args.append(str(owner or ""))
    with _connect() as conn:
        row = conn.execute(sql, args).fetchone()
    if not row or not row["claims_json"]:
        return []
    try:
        return json.loads(row["claims_json"])
    except Exception:
        return []


def export_all(owner: str) -> dict:
    """全量导出该归属的校验台账（备份用）。

    带出 claim 反馈：它是"断言后来应验了吗"的答案，是本产品最不可再生的数据——
    用户手写的判定理由丢了就永远补不回来，所以必须在备份里。
    boundary_samples / proposals 不带：那是**跨用户的校准研究数据**（全局聚合，
    不按用户划分），不属于"某个人的备份"，带出去也没有归属意义。
    """
    init_log_db()
    with _connect() as conn:
        logs = [dict(r) for r in conn.execute(
            "SELECT * FROM check_log WHERE owner=? ORDER BY id ASC", (str(owner or ""),)).fetchall()]
        ids = [r["id"] for r in logs]
        fb: list = []
        if ids:
            q = ",".join("?" * len(ids))
            fb = [dict(r) for r in conn.execute(
                f"SELECT * FROM claim_feedback WHERE log_id IN ({q}) ORDER BY id ASC", ids).fetchall()]
    return {"logs": logs, "claim_feedback": fb}


def import_all(data: dict, owner: str) -> dict:
    """把备份里的校验台账收归 owner 所有，返回 {"logs": n, "feedback": n}。

    与记录同理：log id 一律重新分配（本地自增，沿用会撞车），owner 一律改写为导入者，
    并**同步重映射** claim_feedback 的 log_id——不映射的话反馈会挂到别人的日志上，
    既是数据错位也可能跨归属泄露。
    """
    if not isinstance(data, dict):
        return {"logs": 0, "feedback": 0}
    logs = data.get("logs")
    fb = data.get("claim_feedback")
    if not isinstance(logs, list):
        logs = []
    if not isinstance(fb, list):
        fb = []
    init_log_db()
    id_map: dict = {}
    n_log = n_fb = 0
    with _connect() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(check_log)").fetchall()]
        insert_cols = [c for c in cols if c != "id"]
        for r in logs:
            if not isinstance(r, dict):
                continue
            vals = [r.get(c) for c in insert_cols]
            vals[insert_cols.index("owner")] = str(owner or "")
            # profile_id 同样等于令牌（档案主键即归属），也必须改写成导入者——
            # 否则导入的台账会指向导出设备的档案 id，在新设备上永远对不上档案。
            if "profile_id" in insert_cols:
                vals[insert_cols.index("profile_id")] = str(owner or "")
            # 时间戳 NOT NULL：备份文件可能没有 ts（或写成 null），
            # 直接塞 None 会 IntegrityError → 整个台账导入失败。补当前时间即可。
            if "ts" in insert_cols:
                i = insert_cols.index("ts")
                if not vals[i]:
                    vals[i] = datetime.now().isoformat(timespec="seconds")
            # 文本列按与 append_check 相同的上限截断：备份是不受信输入，
            # 不该因为"它自称是备份"就允许写入比正常路径大得多的行。
            for col, cap in (("question", 200), ("decision", 300), ("profile_id", 128)):
                if col in insert_cols:
                    i = insert_cols.index(col)
                    if isinstance(vals[i], str) and len(vals[i]) > cap:
                        vals[i] = vals[i][:cap]
            cur = conn.execute(
                f"INSERT INTO check_log({','.join(insert_cols)}) "
                f"VALUES({','.join('?' * len(insert_cols))})", vals)
            id_map[int(r.get("id") or 0)] = cur.lastrowid
            n_log += 1
        for r in fb:
            if not isinstance(r, dict):
                continue
            new_id = id_map.get(int(r.get("log_id") or 0))
            if not new_id:
                continue              # 找不到对应日志的孤儿反馈直接丢，不猜归属
            conn.execute("INSERT INTO claim_feedback(ts, log_id, claim_id, verdict, note, contact) "
                         "VALUES(?,?,?,?,?,?)",
                         (r.get("ts") or datetime.now().isoformat(timespec="seconds"), new_id,
                          str(r.get("claim_id") or ""), str(r.get("verdict") or ""),
                          str(r.get("note") or ""), str(r.get("contact") or "")))
            n_fb += 1
    return {"logs": n_log, "feedback": n_fb}


def add_claim_feedback(log_id: int, claim_id: str, verdict: str, note: str = "",
                       contact: str = "", owner: str = "") -> bool:
    """claim 级反馈：同一 claim 后记覆盖前记（更新式）。**先校验日志归属**，防跨人改数据。"""
    init_log_db()
    if not get_log(log_id, owner):
        return False
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute("UPDATE claim_feedback SET verdict=?, note=?, contact=?, ts=? "
                           "WHERE log_id=? AND claim_id=?",
                           (verdict, note or "", contact or "", now, int(log_id), str(claim_id)))
        if cur.rowcount == 0:
            conn.execute("INSERT INTO claim_feedback(ts, log_id, claim_id, verdict, note, contact) "
                         "VALUES(?,?,?,?,?,?)",
                         (now, int(log_id), str(claim_id), verdict, note or "", contact or ""))
    return True


def feedback_of(log_id: int, owner: str = "") -> dict:
    """某次校验的 claim 反馈：{claim_id: verdict}（限本人）。"""
    if owner != _UNSCOPED and not get_log(log_id, owner):
        return {}
    init_log_db()
    with _connect() as conn:
        rows = conn.execute("SELECT claim_id, verdict FROM claim_feedback WHERE log_id=?",
                            (int(log_id),)).fetchall()
    return {r["claim_id"]: r["verdict"] for r in rows}


def add_boundary_samples(log_id: int, samples: list) -> int:
    """边界样本批量落库（判据值擦阈即记）。"""
    if not samples:
        return 0
    init_log_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.executemany(
            "INSERT INTO boundary_samples(ts, log_id, param, value, threshold, side, at_verdict) "
            "VALUES(?,?,?,?,?,?,?)",
            [(now, int(log_id), str(s.get("param", "")), float(s.get("value", 0) or 0),
              float(s.get("threshold", 0) or 0), str(s.get("side", "")), str(s.get("at_verdict", "")))
             for s in samples],
        )
    return len(samples)


def boundary_counts(param: str = "") -> list:
    """按 参数+侧别 汇总边界样本（含样本 log_id 列表，供提案引用）。"""
    init_log_db()
    with _connect() as conn:
        if param:
            rows = conn.execute("SELECT * FROM boundary_samples WHERE param=? ORDER BY id", (param,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM boundary_samples ORDER BY id").fetchall()
    agg = {}
    for r in rows:
        k = (r["param"], r["side"])
        it = agg.setdefault(k, {"param": r["param"], "side": r["side"], "n": 0,
                                "threshold": r["threshold"], "log_ids": []})
        it["n"] += 1
        if int(r["log_id"]) not in it["log_ids"]:
            it["log_ids"].append(int(r["log_id"]))
    return sorted(agg.values(), key=lambda x: -x["n"])


def add_proposal(param: str, old_value: float, new_value: float, sample_ids: list,
                 n_samples: int, flip_rate: float, note: str = "") -> dict:
    """写入一条校准提案（状态恒为"待批"——采纳需人工）。"""
    init_log_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO calibration_proposals(ts, param, old_value, new_value, sample_ids, "
            "n_samples, flip_rate, status, note) VALUES(?,?,?,?,?,?,?,?,?)",
            (now, param, float(old_value), float(new_value),
             json.dumps([int(i) for i in sample_ids], ensure_ascii=False),
             int(n_samples), float(flip_rate), "待批", note),
        )
        pid = cur.lastrowid
    return get_proposal(pid)


def get_proposal(pid: int) -> dict:
    init_log_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM calibration_proposals WHERE id=?", (int(pid),)).fetchone()
    return dict(row) if row else {}


def list_proposals(status: str = "") -> list:
    init_log_db()
    with _connect() as conn:
        if status:
            rows = conn.execute("SELECT * FROM calibration_proposals WHERE status=? ORDER BY id DESC",
                                (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM calibration_proposals ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def decide_proposal(pid: int, status: str, decided_by: str = "", applied_version: str = "") -> bool:
    """人工批准/拒绝（approved→applied 由改 yaml + 升版本完成，此处只留痕）。"""
    if status not in ("已批准", "已拒绝", "已生效"):
        raise ValueError("非法提案状态：%r" % status)
    init_log_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute("UPDATE calibration_proposals SET status=?, decided_at=?, decided_by=?, "
                           "applied_version=? WHERE id=?",
                           (status, now, decided_by or "", applied_version or "", int(pid)))
    return cur.rowcount > 0


def pending_claims(limit: int = 5, owner: str = "") -> list:
    """最近尚无 claim 反馈的校验（反馈页的"待反馈"列表）——限本人。"""
    init_log_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id FROM check_log WHERE kind='check' AND claims_json != '' AND owner=? "
            "AND id NOT IN (SELECT DISTINCT log_id FROM claim_feedback) "
            "ORDER BY id DESC LIMIT ?", (str(owner or ""), int(limit))).fetchall()
    return [int(r["id"]) for r in rows]


def add_beta_note(text: str, contact: str = "", log_id: int = 0, title: str = "") -> int:
    """公测自由留言（含可选标题与联系方式）。"""
    init_log_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute("INSERT INTO beta_notes(ts, text, contact, log_id, title) VALUES(?,?,?,?,?)",
                           (now, str(text)[:2000], str(contact)[:200], int(log_id or 0), str(title)[:120]))
        return cur.lastrowid


def list_beta_notes(limit: int = 100) -> list:
    init_log_db()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM beta_notes ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    return [dict(r) for r in rows]
