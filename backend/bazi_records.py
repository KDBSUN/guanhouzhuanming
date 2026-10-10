# -*- coding: utf-8 -*-
"""
八字档案记录（可保存多份）
==========================
此前"保存为命局档案"是单档位：一个浏览器只存一份八字，换个人排盘就把前一份覆盖了。
本模块提供多份记录：每份带名字（可选）、性别、阳历/农历、四柱，逐条列出、可载入可删。

存储：与命局档案同库（backend/mingju_profiles.db）的表 bazi_records。
其中 birth 字段保存排盘所需的出生参数，前端"设为命局档案"时直接复用（不重复存基线）。
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

_DB_PATH = Path(__file__).parent / "mingju_profiles.db"


def _connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bazi_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT DEFAULT '',
                gender TEXT DEFAULT '',
                solar TEXT DEFAULT '',
                lunar TEXT DEFAULT '',
                pillars TEXT DEFAULT '',
                birth_json TEXT DEFAULT '',
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bazi_records_created ON bazi_records(created_at DESC)")


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    try:
        d["birth"] = json.loads(d.pop("birth_json") or "{}")
    except Exception:
        d["birth"] = {}
    return d


def add_record(payload: dict) -> dict:
    """新增一份八字记录；name 可空（界面显示为"未命名"）"""
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO bazi_records(name, gender, solar, lunar, pillars, birth_json, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                str(payload.get("name", "") or "").strip()[:24],
                str(payload.get("gender", "") or ""),
                str(payload.get("solar", "") or ""),
                str(payload.get("lunar", "") or ""),
                str(payload.get("pillars", "") or ""),
                json.dumps(payload.get("birth") or {}, ensure_ascii=False),
                now, now,
            ),
        )
        rid = cur.lastrowid
        row = conn.execute("SELECT * FROM bazi_records WHERE id=?", (rid,)).fetchone()
    return _row_to_dict(row)


def list_records() -> list:
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM bazi_records ORDER BY id DESC").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_record(rid: int):
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM bazi_records WHERE id=?", (int(rid),)).fetchone()
    return _row_to_dict(row) if row else None


def delete_record(rid: int) -> bool:
    init_db()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM bazi_records WHERE id=?", (int(rid),))
    return cur.rowcount > 0
