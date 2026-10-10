# -*- coding: utf-8 -*-
"""
术语知识地图 · 合并建库
======================
输入：data/term_maps_raw.json（由 tools/extract_term_maps.mjs 抽取）
输出：
  terminology.db          —— 新数据库（terms / term_links / meta）
  data/terminology_merged.json —— 合并后的规范化数据（可重建库，便于版本留痕）
  data/terminology_report.md   —— 合并与校验报告

合并策略：
  梅花：以 tabbit-code.html 为骨架（数据模型最好：id/别名/搜索），
        并入 (1) 版与初版的独占词条（占例、应期、篇目类）；
        分类统一为 10 类（源文件分类名不一，逐类映射，术语级例外见 OVERRIDE）。
  六爻：补充版本身分类干净、无悬空关联，直接采用其 7 类。
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DATA = BACKEND / "data"
DB_PATH = BACKEND / "terminology.db"

# —— 梅花统一分类（顺序即展示顺序）——
MEIHUA_CATS = [
    "起卦立卦", "体用纲纪", "卦象与辞", "三要十应", "观物克应",
    "内外动静与衰旺", "应期克应", "占例", "测字指迷", "书论与总诀",
]

# 源分类 → 统一分类
CAT_MAP = {
    "meihua_rich": {
        "一 · 起卦立卦": "起卦立卦", "二 · 体用纲纪": "体用纲纪", "三 · 卦象与辞": "卦象与辞",
        "四 · 三要十应": "三要十应", "五 · 观物克应": "观物克应", "六 · 衰旺内外动静": "内外动静与衰旺",
        "七 · 测字指迷": "测字指迷", "八 · 心易与总诀": "书论与总诀",
    },
    "meihua_v1": {
        "数卦与起卦": "起卦立卦", "体用体系": "体用纲纪", "卦气旺衰": "内外动静与衰旺",
        "断卦纲领": "书论与总诀", "三要十应": "三要十应", "应期克应": "应期克应", "占例歌诀": "占例",
    },
    "meihua_v0": {
        "起卦立卦": "起卦立卦", "体用纲纪": "体用纲纪", "取象时空": "卦象与辞",
        "三要十应": "三要十应", "观物克应": "观物克应", "内外衰旺": "内外动静与衰旺",
        "测字指迷": "测字指迷", "书论口诀": "书论与总诀",
    },
}

# 术语级分类例外（源分类归错位的个别词条）
OVERRIDE = {
    "meihua_v1": {
        "八卦万物属类": "卦象与辞", "取象比类": "卦象与辞",
        "观物看变爻": "观物克应", "物数为体诀": "观物克应",
        "十八占": "书论与总诀", "观物洞玄歌、观物玄妙歌诀": "观物克应",
        "万物赋": "观物克应", "拆字分支（卷四五）": "测字指迷",
    },
}

# 梅花源文件优先级（前者为骨架）
MEIHUA_ORDER = ["meihua_rich", "meihua_v1", "meihua_v0"]
SOURCE_LABEL = {
    "meihua_rich": "tabbit-code.html（骨架）",
    "meihua_v1": "梅花易数术语知识地图 (1).html",
    "meihua_v0": "梅花易数术语知识地图.html",
    "liuyao": "六爻术语知识地图（补充版）.html",
}


def norm_name(s: str) -> str:
    """名称归一：去括注、统一分隔符（用于跨文件去重与关联解析）"""
    out, depth = [], 0
    for ch in str(s):
        if ch in "（(":
            depth += 1
            continue
        if ch in "）)":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out).replace(" ", "").replace("　", "").replace("、", "").replace("·", "").replace("/", "").replace("／", "").strip()


def merge_meihua(raw: dict):
    """按优先级合并三份梅花数据"""
    terms, index = [], {}
    merges = []
    for src in MEIHUA_ORDER:
        parsed = raw[src]
        for t in parsed["terms"]:
            key = norm_name(t["name"])
            cat = OVERRIDE.get(src, {}).get(t["name"]) or CAT_MAP[src].get(t["cat"], "书论与总诀")
            if key in index:
                cur = index[key]
                if t["name"] != cur["name"] and t["name"] not in cur["alias"].split("｜"):
                    cur["alias"] = "｜".join([x for x in [cur["alias"], t["name"]] if x])
                cur["related"] = list(dict.fromkeys(cur["related"] + t["related"]))
                cur["sources"].append(src)
                merges.append({"name": cur["name"], "also": t["name"], "from": src})
                # 骨架词条释义过短时，采用更完整的一份
                if len(t["detail"]) > len(cur["detail"]) * 1.3:
                    cur["detail"] = t["detail"]
                    cur["detail_source"] = src
                continue
            item = {
                "name": t["name"], "alias": t["alias"], "role": t["role"], "detail": t["detail"],
                "detail_source": src, "related": list(dict.fromkeys(t["related"])),
                "cat": cat, "sources": [src],
            }
            index[key] = item
            terms.append(item)
    return terms, merges


def apply_condensed(terms: list, path: Path):
    """浓缩层：用人工验收过的精简文案替换梅花词条的 role/detail（不改名与关联）"""
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    idx = {norm_name(t["name"]): t for t in terms}
    n = 0
    for name, patch in data.items():
        t = idx.get(norm_name(name))
        if not t:
            continue
        if patch.get("role"):
            t["role"] = patch["role"]
        if patch.get("detail"):
            t["detail"] = patch["detail"]
        n += 1
    return n


def convert_liuyao(parsed: dict):
    terms = []
    for t in parsed["terms"]:
        terms.append({
            "name": t["name"], "alias": t["alias"], "role": t["role"], "detail": t["detail"],
            "detail_source": "liuyao", "related": list(dict.fromkeys(t["related"])),
            "cat": t["cat"], "sources": ["liuyao"],
        })
    return terms


# 六爻词条在合并阶段都带 sources 含 "liuyao"，据此判断词条属于哪个体系
def SYSTEM_OF(t: dict) -> str:
    return "liuyao" if "liuyao" in t.get("sources", []) else "meihua"


def apply_overrides(terms: list, path: Path):
    """覆盖层（最后应用，在浓缩层之后）：合并近重复 / 删除含错 / 新增占例 / 改写 / 隐藏。
    改动依据与书证见 data/term_overrides.json 与 docs/ 下的校正文档。
    执行顺序：合并 → 删除 → 新增 → 改写 → 隐藏（隐藏放最后，新增词条也在管控范围内）。"""
    if not path.exists():
        return {"added": 0, "patched": 0, "deleted": 0, "hidden": 0}
    ov = json.loads(path.read_text(encoding="utf-8"))

    # 合并（近重复词条去重）：败者关联并入胜者、败者名入胜者别名后删除
    for m in ov.get("merge_terms", []):
        loser = next((t for t in terms
                      if SYSTEM_OF(t) == m["system"] and t["name"] == m["from"]), None)
        win = next((t for t in terms
                    if SYSTEM_OF(t) == m["system"] and t["name"] == m["into"]), None)
        if not loser or not win or loser is win:
            continue
        win["related"] = list(dict.fromkeys(win["related"] + loser["related"]))
        if loser["name"] != win["name"] and loser["name"] not in win["alias"].split("｜"):
            win["alias"] = "｜".join([x for x in [win["alias"], loser["name"]] if x])
        terms.remove(loser)

    # 删除（按体系 + 名称精确匹配）
    deleted = 0
    for d in ov.get("delete_terms", []):
        before = len(terms)
        terms[:] = [t for t in terms
                    if not (SYSTEM_OF(t) == d["system"] and t["name"] == d["name"])]
        deleted += before - len(terms)

    names = {norm_name(t["name"]) for t in terms}

    # 新增
    added = 0
    for a in ov.get("add_terms", []):
        if norm_name(a["name"]) in names:
            continue
        terms.append({
            "name": a["name"], "alias": a.get("alias", ""), "role": a["role"], "detail": a["detail"],
            "detail_source": "override", "related": a.get("related", []),
            "cat": a["category"], "sources": ["override"],
        })
        names.add(norm_name(a["name"]))
        added += 1

    # 改写（detail 整体替换；note 追加校注；rename/alias_add 调名）
    patched = 0
    for p in ov.get("patch_terms", []):
        key = norm_name(p["name"])
        hit = next((t for t in terms
                    if SYSTEM_OF(t) == p["system"] and norm_name(t["name"]) == key), None)
        if not hit:
            continue
        if p.get("rename"):
            hit["name"] = p["rename"]
        if p.get("alias_add") and p["alias_add"] not in hit["alias"]:
            hit["alias"] = "｜".join([x for x in [hit["alias"], p["alias_add"]] if x])
        if p.get("detail"):
            hit["detail"] = p["detail"]
        if p.get("note"):
            base = hit["detail"].rstrip()
            hit["detail"] = (base if base.endswith("。") else base + "。") + p["note"]
        hit["sources"] = list(dict.fromkeys(hit["sources"] + ["override"]))
        patched += 1

    # 原文语录层（最后）：每条词条挂书籍原文引文与出处（data/term_source_quotes.json，
    # 由并行编辑逐条从 books/ 原书定位，并经逐字校验脚本核实）
    quotes_path = DATA / "term_source_quotes.json"
    if quotes_path.exists():
        quotes = json.loads(quotes_path.read_text(encoding="utf-8"))
        for t in terms:
            q = quotes.get(f"{SYSTEM_OF(t)}::{t['name']}")
            if q:
                t["source_book"] = q.get("book", "")
                t["source_loc"] = q.get("loc", "")
                t["source_quote"] = q.get("quote", "")

    # 隐藏（放最后：非术语类内容——占例/测字/书论/歌诀等。初学者版只留起卦、断卦、
    # 分析卦用到的专用名词；词条本体保留在库中备查，关联仍可解析到）
    hidden = 0
    for h in ov.get("hide", []):
        for t in terms:
            if SYSTEM_OF(t) == h.get("system", "meihua") and (
                    ("category" in h and t["cat"] == h["category"] or "name" in h and t["name"] == h["name"])):
                if not t.get("hidden"):
                    t["hidden"] = True
                    hidden += 1
    return {"added": added, "patched": patched, "deleted": deleted, "hidden": hidden}


# 来源键 → 页面显示标签（术语页"收录来源"用）
SOURCE_DISPLAY = {
    "meihua_rich": "梅花地图·骨架版",
    "meihua_v1": "梅花地图·补充版",
    "meihua_v0": "梅花地图·初版",
    "liuyao": "六爻术语地图（补充版）",
    "override": "书证补录/校正",
}


# 关联名修正：指向被改名/被合并词条的旧名，映射到现行词条名
REL_FIX = {
    "十八占": "十八占（十七占）",       # 十七占/十八占 已统一为「十八占（十七占）」
    "十七占": "十八占（十七占）",
    "卦气旺、卦气衰": "卦气旺",         # 含错的合并条已删，正确内容在 卦气旺/卦气衰 两条
}


def build_db(systems: dict, meta_note: str):
    """systems: {'meihua': {'cats': [...], 'terms': [...]}, 'liuyao': {...}}"""
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("""
            CREATE TABLE terms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                system TEXT NOT NULL,
                category TEXT NOT NULL,
                cat_order INTEGER NOT NULL,
                term_order INTEGER NOT NULL,
                name TEXT NOT NULL,
                alias TEXT DEFAULT '',
                role TEXT DEFAULT '',
                detail TEXT DEFAULT '',
                sources TEXT DEFAULT '',
                norm TEXT NOT NULL,
                hidden INTEGER DEFAULT 0,
                source_book TEXT DEFAULT '',
                source_loc TEXT DEFAULT '',
                source_quote TEXT DEFAULT '',
                UNIQUE(system, norm)
            )""")
        conn.execute("""
            CREATE TABLE term_links (
                from_id INTEGER NOT NULL,
                to_id INTEGER,
                to_name TEXT NOT NULL,
                PRIMARY KEY (from_id, to_name)
            )""")
        # 同一「来源→目标」只留一条：不同来源地图用别名指同一词条时
        # （如「卦以八除、爻以六除」与「卦数起例 / 年月日时起例」同指一条），
        # 否则页面上会出现两个指向同一词条的关联选项。
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_link_from_to ON term_links(from_id, to_id)")
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE INDEX idx_terms_sys_cat ON terms(system, category, term_order)")

        unresolved, stats = [], {}
        name_by_id = {}                       # id → 该词条正名（关联显示名统一用它）
        for system, pack in systems.items():
            by_norm = {}
            for cat_i, cat in enumerate(pack["cats"]):
                for t_i, t in enumerate([x for x in pack["terms"] if x["cat"] == cat]):
                    cur = conn.execute(
                        "INSERT INTO terms(system, category, cat_order, term_order, name, alias, role, detail, sources, norm, hidden, source_book, source_loc, source_quote) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (system, cat, cat_i, t_i, t["name"], t["alias"], t["role"], t["detail"],
                         "+".join(SOURCE_DISPLAY.get(s, s) for s in sorted(set(t["sources"]))), norm_name(t["name"]),
                         1 if t.get("hidden") else 0,
                         t.get("source_book", ""), t.get("source_loc", ""), t.get("source_quote", "")),
                    )
                    by_norm[norm_name(t["name"])] = cur.lastrowid
                    name_by_id[cur.lastrowid] = t["name"]
                    # 别名（含合并/改名前的旧名）也纳入解析索引——旧名关联自动找到新条
                    for nm in [a for a in t["alias"].split("｜") if a]:
                        by_norm.setdefault(norm_name(nm), cur.lastrowid)
            # 关联落库（解析到同体系词条；解析不到的记为悬空，保留名字）
            for t in pack["terms"]:
                fid = by_norm.get(norm_name(t["name"]))
                if not fid:
                    continue
                for rel in t["related"]:
                    rel = REL_FIX.get(rel, rel)
                    rn = norm_name(rel)
                    if not rn or rn == norm_name(t["name"]):
                        continue
                    tid = by_norm.get(rn)
                    # 显示名统一用目标词条的正名：来源地图里的别名关联不再另起一行
                    to_name = name_by_id.get(tid, rel) if tid else rel
                    conn.execute("INSERT OR IGNORE INTO term_links(from_id, to_id, to_name) VALUES(?,?,?)",
                                 (fid, tid, to_name))
                    if tid is None:
                        unresolved.append({"system": system, "from": t["name"], "to": rel})
            n_terms = conn.execute(
                "SELECT COUNT(*) FROM terms WHERE system=? AND hidden=0", (system,)).fetchone()[0]
            n_links = conn.execute(
                "SELECT COUNT(*) FROM term_links tl JOIN terms t ON t.id=tl.from_id WHERE t.system=? AND t.hidden=0",
                (system,)).fetchone()[0]
            stats[system] = {"categories": len(pack["cats"]), "terms": n_terms, "links": n_links}
        conn.execute("INSERT INTO meta(key,value) VALUES(?,?)", ("generated_at", datetime.now().isoformat(timespec="seconds")))
        conn.execute("INSERT INTO meta(key,value) VALUES(?,?)", ("note", meta_note or ""))
        conn.execute("INSERT INTO meta(key,value) VALUES(?,?)", ("stats", json.dumps(stats, ensure_ascii=False)))
    conn.close()
    return stats, unresolved


def main():
    raw = json.loads((DATA / "term_maps_raw.json").read_text(encoding="utf-8"))
    meihua_terms, merges = merge_meihua(raw)
    liuyao_terms = convert_liuyao(raw["liuyao"])

    # 浓缩层（梅花）：人工验收过的精简文案替换 role/detail
    n_cond = apply_condensed(meihua_terms, DATA / "term_condensed.json")
    # 白话层（梅花）：按用户认可的六爻基础版语体再改写（最后定的文案，优先级最高）
    n_plain = apply_condensed(meihua_terms, DATA / "term_plain.json")
    # 覆盖层（最后）：补占例 / 改错 / 加两书分歧注
    ov_stat = apply_overrides(meihua_terms, DATA / "term_overrides.json")
    apply_overrides(liuyao_terms, DATA / "term_overrides.json")

    systems = {
        "meihua": {"cats": MEIHUA_CATS, "terms": meihua_terms},
        "liuyao": {"cats": [c["name"] for c in raw["liuyao"]["cats"]], "terms": liuyao_terms},
    }
    # 说明文字留空：页面下方不再显示来源/改动清单那段自述（用户 2026-09-14 要求删除）
    note = ""
    stats, unresolved = build_db(systems, note)

    (DATA / "terminology_merged.json").write_text(
        json.dumps({"systems": systems, "source_label": SOURCE_LABEL, "merges": merges},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# 术语知识地图 · 合并与校验报告", "",
             f"生成时间：{datetime.now().isoformat(timespec='seconds')}", "", "## 一、规模", "",
             "| 体系 | 分类 | 词条 | 关联 |", "|---|---|---|---|"]
    for sysname, s in stats.items():
        lines.append(f"| {'梅花易数' if sysname == 'meihua' else '六爻'} | {s['categories']} | {s['terms']} | {s['links']} |")
    lines += ["", "## 二、跨文件合并（同名归一后并条）", "",
              f"共合并 {len(merges)} 条，示例（最多 20 条）：", ""]
    for m in merges[:20]:
        lines.append(f"- {m['name']}　∪　{m['also']}　（来自 {SOURCE_LABEL.get(m['from'], m['from'])}）")
    lines += ["", "## 三、悬空关联（入库后仍无法解析，页面显示为纯文本）", ""]
    if unresolved:
        for u in unresolved:
            lines.append(f"- [{u['system']}] {u['from']} → {u['to']}")
    else:
        lines.append("- 无")
    (DATA / "terminology_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=== 建库完成 ===")
    print(f"数据库：{DB_PATH}")
    for sysname, s in stats.items():
        print(f"  {sysname}: 分类 {s['categories']} / 词条 {s['terms']} / 关联 {s['links']}")
    print(f"  跨文件合并：{len(merges)} 条；浓缩替换：{n_cond} 条；白话替换：{n_plain} 条")
    print(f"  覆盖层：新增 {ov_stat['added']} / 改写 {ov_stat['patched']} / 删除 {ov_stat['deleted']}")
    print(f"  悬空关联：{len(unresolved)} 条" + (f"（{unresolved[0]['from']}→{unresolved[0]['to']} …）" if unresolved else ""))


if __name__ == "__main__":
    main()
