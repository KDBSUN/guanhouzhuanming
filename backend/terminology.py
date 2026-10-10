# -*- coding: utf-8 -*-
"""
术语知识地图 · 查询层
=====================
数据来源：backend/terminology.db（新库），由 tools/extract_term_maps.mjs 抽取
四份 HTML 知识地图 + tools/build_terms_db.py 合并建库而成：
  - 梅花易数：tabbit-code.html 为骨架，并入 (1) 版与初版的独占词条（占例/应期/篇目），统一 10 类
  - 六爻纳甲：六爻术语知识地图（补充版）.html，7 类
只读访问，不写库。术语原文未做人工改写（仅修复源文件的两处语法引号）。
"""
import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).parent / "terminology.db"

SYSTEM_LABEL = {"meihua": "梅花易数", "liuyao": "六爻纳甲"}


def _connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def available() -> bool:
    return _DB_PATH.exists()


def meta() -> dict:
    """体系、分类（含词条数）与来源说明"""
    if not available():
        return {"systems": [], "note": "术语库尚未生成（请运行 tools/ 下抽取与建库脚本）"}
    with _connect() as conn:
        systems = []
        for sysname in ("meihua", "liuyao"):
            cats = conn.execute(
                "SELECT category, COUNT(*) n FROM terms WHERE system=? AND hidden=0 "
                "GROUP BY category ORDER BY cat_order",
                (sysname,),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) FROM terms WHERE system=? AND hidden=0", (sysname,)).fetchone()[0]
            links = conn.execute(
                "SELECT COUNT(*) FROM term_links tl JOIN terms t ON t.id=tl.from_id "
                "WHERE t.system=? AND t.hidden=0",
                (sysname,),
            ).fetchone()[0]
            if total:
                systems.append({
                    "system": sysname,
                    "label": SYSTEM_LABEL.get(sysname, sysname),
                    "total": total,
                    "links": links,
                    "categories": [{"name": c["category"], "count": c["n"]} for c in cats],
                })
        note = conn.execute("SELECT value FROM meta WHERE key='note'").fetchone()
        generated = conn.execute("SELECT value FROM meta WHERE key='generated_at'").fetchone()
    return {
        "systems": systems,
        "note": note["value"] if note else "",
        "generated_at": generated["value"] if generated else "",
    }


def list_terms(system: str, category: str = "", q: str = "", limit: int = 0,
               include_hidden: bool = False) -> list:
    """按体系/分类/关键词列出词条（不含详解，列表用；默认排除隐藏词条）"""
    if not available():
        return []
    sql = ("SELECT id, system, category, name, alias, role FROM terms WHERE system=?")
    args: list = [system]
    if not include_hidden:
        sql += " AND hidden=0"
    if category:
        sql += " AND category=?"
        args.append(category)
    if q:
        sql += " AND (name LIKE ? OR alias LIKE ? OR role LIKE ? OR detail LIKE ?)"
        like = f"%{q}%"
        args += [like, like, like, like]
    sql += " ORDER BY cat_order, term_order"
    if limit and limit > 0:
        sql += " LIMIT ?"
        args.append(int(limit))
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def get_term(term_id: int) -> dict | None:
    """单词条详情 + 关联术语（解析到具体词条，未解析的标记 exists=False）"""
    if not available():
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM terms WHERE id=?", (int(term_id),)).fetchone()
        if not row:
            return None
        links = conn.execute(
            "SELECT tl.to_name, tl.to_id, t.name AS resolved_name, t.category AS resolved_cat, t.system AS resolved_system "
            "FROM term_links tl LEFT JOIN terms t ON t.id=tl.to_id WHERE tl.from_id=? "
            "GROUP BY COALESCE(tl.to_id, tl.to_name) "      # 同一目标只出一条（别名关联去重）
            "ORDER BY COALESCE(t.name, tl.to_name)",
            (int(term_id),),
        ).fetchall()
    item = dict(row)
    item["relations"] = [
        {
            "name": l["resolved_name"] or l["to_name"],
            "id": l["to_id"],
            "category": l["resolved_cat"],
            "system": l["resolved_system"],
            "exists": l["to_id"] is not None,
        }
        for l in links
    ]
    return item


def search(q: str, system: str = "", limit: int = 30) -> list:
    """跨体系搜索（按名称/别名/释义；隐藏词条不出现）"""
    if not available() or not q.strip():
        return []
    sql = ("SELECT id, system, category, name, alias, role FROM terms "
           "WHERE hidden=0 AND (name LIKE ? OR alias LIKE ? OR detail LIKE ?)")
    like = f"%{q.strip()}%"
    args: list = [like, like, like]
    if system:
        sql += " AND system=?"
        args.append(system)
    sql += " ORDER BY system, cat_order, term_order LIMIT ?"
    args.append(int(limit))
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
