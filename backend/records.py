# -*- coding: utf-8 -*-
"""
记录库（统一表：起卦与排盘的可回放快照）
========================================
定位（用户明确）：**记录的首要用途是"回看/回放之前做过的东西"**，点开要能跳回当时的界面；
"应验/未验"反馈只是附在记录上的附件，不再是记录页的主角。

一条记录 = 一次完整快照：
  kind='meihua'  → payload {gua_data, ai_text, question, check?}   点开回放梅花结果页
  kind='liuyao'  → payload {gua_data, ai_text, question, throws}   点开回放六爻结果页
  kind='bazi'    → payload {birth, solar, lunar, gender, pillars}  点开回填八字页并重排

**归属隔离（A 档最小安全集）**：records 表带 owner 列，
所有读写一律 `WHERE owner=?`；owner 是前端 localStorage 里的随机令牌
（新访客用 crypto.randomUUID，老访客沿用既有 id 以免丢档案）——等价"设备即账户"，
用户不用注册，但**任何人都拿不到别人的记录**。

老数据（加 owner 列之前的行）owner=''，默认对所有人不可见；需要时可一次性
用 `claim_legacy(owner)` 认领（运维脚本用，不开放为接口）。

存储：backend/mingju_profiles.db 的 records 表（与命局档案同库）。
删除是**软删除**：删除只是打上 deleted_at 时间戳，进「最近删除」，30 天内可恢复；
超过 30 天在下次读写时自动彻底清除（purge_expired）。这样误删不会真的丢数据。
"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

_DB_PATH = Path(__file__).parent / "mingju_profiles.db"

TRASH_DAYS = 30                       # 最近删除保留天数

_NOT_DELETED = "(deleted_at IS NULL OR deleted_at = '')"


def _connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,                 -- meihua | liuyao | bazi
                title TEXT DEFAULT '',              -- 显示标题（卦名/四柱/名字，可编辑）
                subtitle TEXT DEFAULT '',            -- 副标题（问题/阳历/干支）
                question TEXT DEFAULT '',
                payload_json TEXT DEFAULT '{}',
                note TEXT DEFAULT '',                -- 用户备注（编辑功能写入）
                pinned INTEGER DEFAULT 0,
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT '',
                deleted_at TEXT DEFAULT '',          -- 软删除时间（进「最近删除」，可恢复）
                owner TEXT DEFAULT ''                -- 归属令牌（设备即账户；空=迁移前老数据）
            )""")
        _migrate_add_deleted_at(conn)
        _migrate_add_owner(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_kind ON records(kind, pinned DESC, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_deleted ON records(deleted_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_owner ON records(owner, kind, pinned DESC, id DESC)")
        _migrate_bazi_records(conn)
    purge_expired()                              # 每次初始化顺手清掉超过 30 天的


def _migrate_add_deleted_at(conn):
    """老库补列：records 表早期没有 deleted_at（幂等）"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(records)").fetchall()}
    if "deleted_at" not in cols:
        conn.execute("ALTER TABLE records ADD COLUMN deleted_at TEXT DEFAULT ''")


def _migrate_add_owner(conn):
    """老库补列：owner（归属令牌）。只增列，老行保持 owner=''（对所有人不可见，可 claim_legacy 认领）"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(records)").fetchall()}
    if "owner" not in cols:
        conn.execute("ALTER TABLE records ADD COLUMN owner TEXT DEFAULT ''")


def _migrate_bazi_records(conn):
    """把旧表 bazi_records 的数据迁入统一表（幂等：按 payload.birth 去重）"""
    try:
        rows = conn.execute("SELECT * FROM bazi_records").fetchall()
    except sqlite3.OperationalError:
        return                                   # 旧表不存在，无需迁移
    if not rows:
        return
    existing = conn.execute(
        "SELECT COUNT(*) FROM records WHERE kind='bazi'").fetchone()[0]
    if existing:
        return                                   # 已迁过
    for r in rows:
        payload = {
            "birth": json.loads(r["birth_json"] or "{}"),
            "solar": r["solar"], "lunar": r["lunar"],
            "gender": r["gender"], "pillars": r["pillars"],
        }
        conn.execute(
            "INSERT INTO records(kind, title, subtitle, question, payload_json, note, pinned, created_at, updated_at) "
            "VALUES('bazi',?,?,?,?,'',0,?,?)",
            (r["name"] or "未命名", r["pillars"] or r["solar"], "", json.dumps(payload, ensure_ascii=False),
             r["created_at"] or datetime.now().isoformat(timespec="seconds"),
             r["updated_at"] or r["created_at"] or datetime.now().isoformat(timespec="seconds")),
        )


def claim_legacy(owner: str) -> int:
    """把迁移前的老记录认领给某个令牌；返回认领条数。

    覆盖两种"无主"形态：加 owner 列之前的行（''/NULL）与迁移脚本统一改挂的保留归属
    `__legacy__`（客户端构造不出该值，故在此之前对所有人不可见）。
    仅运维使用（不进 HTTP 接口）：站长在浏览器里拿到自己的令牌后跑一次即可找回历史记录。
    """
    if not owner or str(owner).startswith("__"):
        raise ValueError("owner 不能为空，也不能是保留值")
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE records SET owner=? WHERE owner IS NULL OR owner='' OR owner='__legacy__'",
            (owner,),
        )
    return cur.rowcount


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    try:
        d["payload"] = json.loads(d.pop("payload_json") or "{}")
    except Exception:
        d["payload"] = {}
    return d


def add(kind: str, title: str = "", subtitle: str = "", question: str = "",
        payload: dict | None = None, owner: str = "") -> dict:
    if kind not in ("meihua", "liuyao", "bazi"):
        raise ValueError(f"非法记录类型: {kind!r}")
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO records(kind, title, subtitle, question, payload_json, note, pinned, created_at, updated_at, owner) "
            "VALUES(?,?,?,?,?,'',0,?,?,?)",
            (kind, str(title or "")[:60], str(subtitle or "")[:120], str(question or "")[:200],
             json.dumps(payload or {}, ensure_ascii=False), now, now, str(owner or "")),
        )
        row = conn.execute("SELECT * FROM records WHERE id=?", (cur.lastrowid,)).fetchone()
    return _row(row)


def list_all(kind: str = "", limit: int = 200, owner: str = "") -> list:
    """置顶优先、时间倒序；**只返回调用者自己的记录**"""
    init_db()
    sql = f"SELECT * FROM records WHERE {_NOT_DELETED} AND owner=?"
    args: list = [str(owner or "")]
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    sql += " ORDER BY pinned DESC, id DESC LIMIT ?"
    args.append(int(limit))
    with _connect() as conn:
        return [_row(r) for r in conn.execute(sql, args).fetchall()]


def _days_left(deleted_at: str) -> int:
    """距离自动彻底删除还剩几天（不足一天按 0 计）"""
    try:
        dt = datetime.fromisoformat(deleted_at)
    except Exception:
        return TRASH_DAYS
    left = TRASH_DAYS - (datetime.now() - dt).days
    return max(0, left)


def list_deleted(limit: int = 200, owner: str = "") -> list:
    """最近删除（近 30 天内删掉的），最近删的在前；只含自己的"""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM records WHERE NOT " + _NOT_DELETED + " AND owner=?"
            " ORDER BY deleted_at DESC, id DESC LIMIT ?", (str(owner or ""), int(limit))
        ).fetchall()
    out = []
    for r in rows:
        d = _row(r)
        d["days_left"] = _days_left(d.get("deleted_at") or "")
        out.append(d)
    return out


def export_all(owner: str) -> list:
    """全量导出（备份用）：**含回收站里的**，只含自己的。

    为什么含回收站：备份的语义是"把这台设备上的东西整包带走"，而回收站里的记录
    对用户仍然可见可恢复，漏掉它们等于备份悄悄丢东西。
    """
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM records WHERE owner=? ORDER BY id ASC", (str(owner or ""),)
        ).fetchall()
    return [_row(r) for r in rows]


def import_all(rows: list, owner: str) -> int:
    """把备份里的记录收归 owner 所有，返回导入条数。

    两条设计决定：
      1. **id 一律重新分配**，不沿用备份里的 id——id 是本地自增值，沿用会与既有行冲突
         （`INSERT` 撞主键或覆盖本地记录），而"备份恢复不该破坏本机现有数据"。
      2. **owner 一律改写为导入者**，不信备份里的 owner——备份文件只带数据、不带凭证；
         否则拿到别人的备份文件就等于拿到他数据在你库里的归属。
    内容、置顶、时间戳与软删除状态原样保留。
    """
    if not isinstance(rows, list):
        return 0
    init_db()
    n = 0
    with _connect() as conn:
        for r in rows:
            if not isinstance(r, dict):
                continue
            kind = str(r.get("kind") or "")
            if kind not in ("meihua", "liuyao", "bazi"):
                continue                      # 不认识的类型直接跳过，不整包失败
            payload = r.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            now = datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO records(kind, title, subtitle, question, payload_json, note, pinned,"
                " created_at, updated_at, deleted_at, owner) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (kind, str(r.get("title") or "")[:60], str(r.get("subtitle") or "")[:120],
                 str(r.get("question") or "")[:200],
                 json.dumps(payload, ensure_ascii=False), str(r.get("note") or "")[:300],
                 1 if r.get("pinned") else 0, str(r.get("created_at") or now), now,
                 str(r.get("deleted_at") or ""), str(owner or "")),
            )
            n += 1
    return n


def get(rid: int, owner: str = ""):
    """取单条：必须属于调用者，否则视为不存在（不区分 404 与无权，避免探测）"""
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM records WHERE id=? AND owner=?",
                           (int(rid), str(owner or ""))).fetchone()
    return _row(row) if row else None


def update(rid: int, title: str | None = None, note: str | None = None,
           pinned: int | None = None, owner: str = "", payload: dict | None = None,
           subtitle: str | None = None) -> bool:
    """编辑（标题/副标题/备注/快照）与置顶（仅限自己的记录）

    `payload` 是**回填**用的：2026-09-19 起起卦与 AI 断卦分成两步（见 quota.py 与
    `/api/liuyao/divine` 的 `ai` 开关），前端在"排盘出来"时就把记录存下（保证盘不会丢），
    等 AI 断完再把带断语的完整快照**盖回去**。
    没有这条回填，两步就会各存一条（重复），或者为了不重复而推迟到 AI 之后才存
    （那样只看盘、不要 AI 的那次就什么都不剩）。

    `subtitle` 可改是为了六爻的**改判用神**：副标题里带着"用神X · 补Y"，
    改判后它必须跟着变，否则列表显示旧用神、点进去回放却是新用神，前后对不上。
    """
    init_db()
    sets, args = [], []
    if title is not None:
        sets.append("title=?")
        args.append(str(title)[:60])
    if subtitle is not None:
        sets.append("subtitle=?")
        args.append(str(subtitle)[:200])
    if note is not None:
        sets.append("note=?")
        args.append(str(note)[:300])
    if pinned is not None:
        sets.append("pinned=?")
        args.append(1 if pinned else 0)
    if payload is not None:
        sets.append("payload_json=?")
        args.append(json.dumps(payload, ensure_ascii=False))
    if not sets:
        return False
    sets.append("updated_at=?")
    args.append(datetime.now().isoformat(timespec="seconds"))
    args.extend([int(rid), str(owner or "")])
    with _connect() as conn:
        cur = conn.execute(f"UPDATE records SET {', '.join(sets)} WHERE id=? AND owner=?", args)
    return cur.rowcount > 0


def remove(rid: int, owner: str = "") -> bool:
    """软删除：进「最近删除」，30 天内可 restore，逾期由 purge_expired 彻底清除。"""
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE records SET deleted_at=?, updated_at=? WHERE id=? AND owner=? AND " + _NOT_DELETED,
            (now, now, int(rid), str(owner or "")),
        )
    return cur.rowcount > 0


def restore(rid: int, owner: str = "") -> bool:
    """从「最近删除」恢复"""
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE records SET deleted_at='', updated_at=? WHERE id=? AND owner=? AND NOT " + _NOT_DELETED,
            (datetime.now().isoformat(timespec="seconds"), int(rid), str(owner or "")),
        )
    return cur.rowcount > 0


def purge(rid: int, owner: str = "") -> bool:
    """彻底删除（不可恢复）"""
    init_db()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM records WHERE id=? AND owner=?", (int(rid), str(owner or "")))
    return cur.rowcount > 0


def purge_expired(days: int = TRASH_DAYS) -> int:
    """清掉「最近删除」里超过保留期的记录，返回清除条数（全库维护任务，不涉及用户可见性）"""
    cutoff = (datetime.now() - timedelta(days=int(days))).isoformat(timespec="seconds")
    with _connect() as conn:
        try:
            cur = conn.execute(
                "DELETE FROM records WHERE deleted_at IS NOT NULL AND deleted_at != '' AND deleted_at < ?",
                (cutoff,),
            )
        except sqlite3.OperationalError:
            return 0                              # 表/列还不存在
    return cur.rowcount


def empty_trash(owner: str = "") -> int:
    """清空「最近删除」（只清自己的）"""
    init_db()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM records WHERE NOT " + _NOT_DELETED + " AND owner=?",
                           (str(owner or ""),))
    return cur.rowcount
