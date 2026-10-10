# -*- coding: utf-8 -*-
"""
记录库回归（records.py）
========================
定位：记录是"可回放的快照"（点开能跳回当时的界面），反馈只是附件。
覆盖：三类记录增删改查、置顶排序、旧 bazi_records 自动迁移。
"""
import json
from pathlib import Path

import records


def _use_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(records, "_DB_PATH", Path(tmp_path) / "r.db")
    records.init_db()


def test_add_list_kinds(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    m = records.add("meihua", "泽火革", "这周五去谈合作顺利吗", "这周五去谈合作顺利吗",
                    {"gua_data": {"ben_gua": {"name": "泽火革"}}, "ai_text": "断语…"})
    l = records.add("liuyao", "地水师", "父亲的病情能好转吗", "父亲的病情能好转吗",
                    {"gua_data": {"ben_gua": {"name": "地水师"}}, "ai_text": "断语…", "throws": []})
    b = records.add("bazi", "本人", "己巳 丙子 丙寅 甲午", "",
                    {"birth": {"year": 1990, "month": 1, "day": 1}, "pillars": "己巳 丙子 丙寅 甲午"})
    rows = records.list_all()
    assert len(rows) == 3
    assert {r["kind"] for r in rows} == {"meihua", "liuyao", "bazi"}
    # 回放快照完整可取
    got = records.get(m["id"])
    assert got["payload"]["gua_data"]["ben_gua"]["name"] == "泽火革"
    assert got["payload"]["ai_text"]
    assert records.get(b["id"])["payload"]["birth"]["year"] == 1990
    assert [r["id"] for r in records.list_all("bazi")] == [b["id"]]


def test_pin_orders_first(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    a = records.add("meihua", "甲", "", "", {})
    b = records.add("meihua", "乙", "", "", {})
    assert [r["id"] for r in records.list_all()] == [b["id"], a["id"]]
    assert records.update(a["id"], pinned=1) is True
    assert [r["id"] for r in records.list_all()] == [a["id"], b["id"]]
    assert records.update(a["id"], pinned=0) is True
    assert [r["id"] for r in records.list_all()] == [b["id"], a["id"]]


def test_edit_title_and_note(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    r = records.add("bazi", "未命名", "己巳 丙子 丙寅 甲午", "", {})
    assert records.update(r["id"], title="我自己的盘", note="1990年正月初五") is True
    got = records.get(r["id"])
    assert got["title"] == "我自己的盘" and got["note"] == "1990年正月初五"
    assert records.update(r["id"]) is False          # 无字段可更新


def test_delete(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    r = records.add("liuyao", "地水师", "", "", {})
    assert records.remove(r["id"]) is True
    assert records.remove(r["id"]) is False           # 已在回收站，不再重复软删
    assert records.list_all() == []


def test_soft_delete_goes_to_trash_and_restores(tmp_path, monkeypatch):
    """删除先软删进「最近删除」，可恢复（误删保险）"""
    _use_tmp(tmp_path, monkeypatch)
    r = records.add("meihua", "火天大有", "", "问事", {"ai_text": "断语"})
    assert records.remove(r["id"]) is True
    assert records.list_all() == []                    # 列表里消失
    trash = records.list_deleted()
    assert len(trash) == 1 and trash[0]["id"] == r["id"]
    assert trash[0]["deleted_at"] and trash[0]["days_left"] == records.TRASH_DAYS
    assert records.get(r["id"])["payload"]["ai_text"] == "断语"    # 数据还在
    assert records.restore(r["id"]) is True
    assert records.restore(r["id"]) is False           # 不在回收站了
    assert [x["id"] for x in records.list_all()] == [r["id"]]
    assert records.list_deleted() == []


def test_purge_and_empty_trash(tmp_path, monkeypatch):
    """彻底删除 / 清空回收站"""
    _use_tmp(tmp_path, monkeypatch)
    a = records.add("meihua", "甲", "", "", {})
    b = records.add("meihua", "乙", "", "", {})
    records.remove(a["id"]); records.remove(b["id"])
    assert records.purge(a["id"]) is True
    assert records.get(a["id"]) is None
    assert [x["id"] for x in records.list_deleted()] == [b["id"]]
    assert records.empty_trash() == 1
    assert records.list_deleted() == []
    assert records.list_all() == []


def test_purge_expired_after_retention(tmp_path, monkeypatch):
    """超过保留期（默认 30 天）的记录在下次读写时自动彻底清除"""
    import sqlite3
    from datetime import datetime, timedelta
    _use_tmp(tmp_path, monkeypatch)
    old = records.add("meihua", "旧", "", "", {})
    fresh = records.add("meihua", "新", "", "", {})
    records.remove(old["id"]); records.remove(fresh["id"])
    stale = (datetime.now() - timedelta(days=records.TRASH_DAYS + 1)).isoformat(timespec="seconds")
    with sqlite3.connect(records._DB_PATH) as conn:
        conn.execute("UPDATE records SET deleted_at=? WHERE id=?", (stale, old["id"]))
    records.init_db()                                  # 触发过期清理
    left = [x["id"] for x in records.list_deleted()]
    assert left == [fresh["id"]]
    assert records.get(old["id"]) is None


def test_migrate_adds_deleted_at_column(tmp_path, monkeypatch):
    """老库（records 表没有 deleted_at 列）自动补列，历史数据仍在"""
    import sqlite3
    db = Path(tmp_path) / "r.db"
    monkeypatch.setattr(records, "_DB_PATH", db)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE records (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, "
                 "title TEXT DEFAULT '', subtitle TEXT DEFAULT '', question TEXT DEFAULT '', "
                 "payload_json TEXT DEFAULT '{}', note TEXT DEFAULT '', pinned INTEGER DEFAULT 0, "
                 "created_at TEXT DEFAULT '', updated_at TEXT DEFAULT '')")
    conn.execute("INSERT INTO records(kind, title) VALUES('meihua','老记录')")
    conn.commit(); conn.close()
    records.init_db()                                  # 自动补列
    rows = records.list_all()
    assert len(rows) == 1 and rows[0]["title"] == "老记录"
    assert rows[0]["deleted_at"] == ""
    assert records.remove(rows[0]["id"]) is True       # 新列可用
    assert records.list_all() == []


def test_migrate_old_bazi_records(tmp_path, monkeypatch):
    """旧表 bazi_records 的数据自动迁入统一表（不丢用户已存盘）"""
    import sqlite3
    db = Path(tmp_path) / "r.db"
    monkeypatch.setattr(records, "_DB_PATH", db)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE bazi_records (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, gender TEXT, "
                 "solar TEXT, lunar TEXT, pillars TEXT, birth_json TEXT, created_at TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO bazi_records(name,gender,solar,lunar,pillars,birth_json,created_at,updated_at) "
                 "VALUES('老爸','男','1970年1月1日 08:00','','庚戌 丁丑 壬子 甲辰','{\"year\":1970}','2026-01-01T00:00:00','2026-01-01T00:00:00')")
    conn.commit()
    conn.close()
    records.init_db()
    rows = records.list_all("bazi")
    assert len(rows) == 1
    assert rows[0]["title"] == "老爸"
    assert json.loads(json.dumps(rows[0]["payload"]))["birth"]["year"] == 1970
    records.init_db()                                 # 幂等：不会重复迁
    assert len(records.list_all("bazi")) == 1


def test_feedback_outcome_attaches_to_record(tmp_path, monkeypatch):
    """反馈（应验/未验）作为记录的附件挂回列表：匹配 log_id，且不误伤别的记录。"""
    import main

    _use_tmp(tmp_path, monkeypatch)
    with_log = records.add("meihua", "泽火革", "", "考题", {"log_id": 42})
    no_log = records.add("meihua", "山水蒙", "", "", {})
    m = {42: "应验", 99: "未验"}

    monkeypatch.setattr(main, "log_outcomes", lambda ids, owner="": {k: v for k, v in m.items() if k in ids})
    items = main._attach_outcomes(records.list_all())
    by_id = {r["id"]: r for r in items}
    assert by_id[with_log["id"]]["payload"]["outcome"] == "应验"
    assert "outcome" not in by_id[no_log["id"]]["payload"]
    # payload 里没有 log_id 时不去查日志
    assert main._attach_outcomes([{"payload": {}}]) == [{"payload": {}}]
