# -*- coding: utf-8 -*-
"""
命局档案（基线）存储与计算
==========================
三层结构：
  核心层（静态）：F / J / T0 / 强弱档 / 从格 / 五行分布 —— 注册时算一次入库，终身不变
  快照层（动态）：当令月令 M、日辰 D —— 每次起卦刷新，不落库（由调用方提供）
  岁运层（预留）：流年干支 / 大运 —— 只留接口，不实现

存储：SQLite（backend/mingju_profiles.db），按档案 id（客户端生成）持久化。
无用户认证体系，故以 id 定位；跨设备走"加密导出/导入"（前端 AES-GCM 加密，密码不经过服务器），
账号化留待真实多设备需求出现后再启用（届时出生信息端到端加密、服务端只存密文+不可逆索引）。

迁移：profile 自 schema_version=1 起带不可变 uuid（首次保存生成，更新/导入保持不变），
表结构变更只增列不改列，保证旧档案与新备份文件可平滑迁移。
"""
import json
import sqlite3
import uuid as _uuid
from datetime import datetime
from pathlib import Path

from bazi_engine import build_bazi_paipan
from wuxing_quality import hidden_tally as _hidden_tally   # 干支级力量（藏干加权）
from yunqi import yunqi, dili_wufang                       # 改运链：出生年运气＋空间环境气

_DB_PATH = Path(__file__).parent / "mingju_profiles.db"
SCHEMA_VERSION = 2


def _connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                birth_json TEXT NOT NULL,
                baseline_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # —— 平滑迁移：只增列，不改列 ——
        cols = {r[1] for r in conn.execute("PRAGMA table_info(profiles)")}
        if "uuid" not in cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN uuid TEXT")
        if "schema_version" not in cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1")
        # —— 基线口径迁移（2026-10-06 H5）：调候字与忌神相重的裁决改为「调候为急，
        # 权而用之」（《子平真诠·论用神配气候得失》），调候字移出忌神表；v1 档案的
        # J 列表可能仍带着调候字（旧口径只加标记不移出）。基线是出生信息的确定函数，
        # 故由 birth_json 重算回填（与导入口径一致，顺带补上新字段如 yunqi/dili）。
        if "schema_version" in cols:
            stale = conn.execute(
                "SELECT id, birth_json FROM profiles WHERE schema_version < ?",
                (SCHEMA_VERSION,)).fetchall()
            for row in stale:
                try:
                    base = compute_baseline(json.loads(row["birth_json"]))
                    conn.execute(
                        "UPDATE profiles SET baseline_json=?, schema_version=? WHERE id=?",
                        (json.dumps(base, ensure_ascii=False), SCHEMA_VERSION, row["id"]))
                except Exception:
                    pass    # 出生信息残缺的旧行：保留原基线，不让迁移崩掉整个库


def compute_baseline(birth: dict) -> dict:
    """由出生参数计算命局基线（核心静态层）。birth 与 BaziRequest 同构。"""
    data = build_bazi_paipan(
        birth.get("year"), birth.get("month"), birth.get("day"),
        birth.get("hour", 0), birth.get("minute", 0), birth.get("gender", 1),
        calendar=birth.get("calendar", "solar"),
        leap_month=birth.get("leap_month", False),
        dst=birth.get("dst", False),
        true_solar=birth.get("true_solar", False),
        longitude=birth.get("longitude", 120.0),
    )
    xiji = data["xiji"]
    mingju = xiji["mingju"]
    _gans = [p["gan"] for p in data["bazi"]]
    _zhis = [p["zhi"] for p in data["bazi"]]
    _hidden = _hidden_tally(_gans, _zhis)
    return {
        "solar": data["solar"],
        "lunar": data["lunar"],
        "gender": data["gender"],
        "day_master": data["day_master"],
        "mingju": {
            "F": mingju["F"],
            "J": mingju["J"],
            "T0": mingju["T0"],
            "t0_list": mingju.get("t0_list", []),   # 《穷通宝鉴》整串调候药单（按原文次序）
            "t0_src": mingju.get("t0_src", ""),      # 首味来源：表 / 寒燥方向 / ""（休眠）
            "tier": mingju["tier"],
            "from_ge": mingju["from_ge"],
            "ge_quality": mingju.get("ge_quality", ""),      # 真从/假从/真化（旧档案无此键，重存后补全）
            "ge_note": mingju.get("ge_note", ""),            # 格局判定依据（人话）
            "ge_basis": mingju.get("ge_basis", []),          # 格局判定依据（逐条书证）
            "day_master_wx": mingju["day_master_wx"],
            "month_wx": mingju["month_wx"],   # 出生月令五行（基线快照；动态校验用当令月令覆盖）
            "wuxing_tally": mingju["wuxing_tally"],
            "wuxing_tally_hidden": _hidden,                     # 干支级力量（藏干加权，R2）
            "gans": _gans,                                      # 四干（关系层·干合/地支作用校验用）
            "zhis": _zhis,                                      # 四支（地支作用：冲/合/会）
            "month_zhi": data["bazi"][1]["zhi"],                # 出生月支
        },
        "tiaohou": {"yongshen": data["tiaohou"]["yongshen"], "note": data["tiaohou"]["note"]},
        "geju": data["geju"],
        "shensha": data["shensha"],
        # —— 改运链（2026-09-25 三链框架）：出生年天地运气＋出生地空间环境气。
        # 只作背景展示与改运建议依据，不进吉凶升降档（判运由占卜与命家岁运负责）。
        "yunqi": yunqi(data["bazi"][0]["ganzhi"]),
        "dili": dili_wufang(birth.get("longitude", 120.0), birth.get("latitude")),
    }


def save_profile(pid: str, birth: dict) -> dict:
    """保存/更新档案，返回基线。uuid 不可变：首次保存生成，更新保持不变。"""
    init_db()
    baseline = compute_baseline(birth)
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        row = conn.execute("SELECT uuid FROM profiles WHERE id=?", (pid,)).fetchone()
        uid = row["uuid"] if row and row["uuid"] else _uuid.uuid4().hex
        conn.execute(
            "INSERT INTO profiles(id, birth_json, baseline_json, created_at, updated_at, uuid, schema_version) "
            "VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET birth_json=excluded.birth_json, "
            "baseline_json=excluded.baseline_json, updated_at=excluded.updated_at",
            (pid, json.dumps(birth, ensure_ascii=False), json.dumps(baseline, ensure_ascii=False),
             now, now, uid, SCHEMA_VERSION),
        )
    return baseline


def get_profile(pid: str):
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id=?", (pid,)).fetchone()
    if not row:
        return None
    return {"id": row["id"], "uuid": row["uuid"], "birth": json.loads(row["birth_json"]),
            "baseline": json.loads(row["baseline_json"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "schema_version": row["schema_version"]}


def delete_profile(pid: str) -> bool:
    init_db()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM profiles WHERE id=?", (pid,))
    return cur.rowcount > 0


def export_profile(pid: str):
    """导出档案（不含基线也可由 birth 重算；连基线一并带出便于人工查验）。"""
    p = get_profile(pid)
    if not p:
        return None
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "profile": p,
    }


def import_profile(data: dict, owner: str):
    """
    导入档案：校验 schema 版本，基线一律由 birth 现算（不信任备份文件里的基线，
    既防篡改也兼容 schema 演进）。

    **归属由参数 owner 决定，绝不采信备份文件里的 id。**
    这一条同时修掉两个问题：
      · 安全：原先按文件里的 id 做 `ON CONFLICT(id) DO UPDATE`，而该端点当时没有归属校验，
        于是任何人只凭"知道某个 id"就能把别人的出生信息覆盖掉（数据破坏，不只是泄露）；
      · 功能：原先导入后档案挂在**备份里的 id**（= 导出设备的令牌）下，而新设备的令牌是
        另一串，于是新设备用自己的令牌读不到它——"换手机导入备份"实际看到的是"还没有档案"，
        导入成功的返回是假象。改为挂在 owner 下，令牌与档案 id 的对应关系才重新成立。
    uuid 沿用备份里的值（它才是"同一份档案"的不可变标识），被占用则新生成。
    data = {schema_version, profile: {id, uuid?, birth}}
    """
    init_db()
    if not isinstance(data, dict) or "profile" not in data:
        raise ValueError("备份文件缺少 profile 字段")
    prof = data["profile"]
    ver = int(data.get("schema_version", 0) or 0)
    if ver > SCHEMA_VERSION:
        raise ValueError(f"备份文件 schema 版本（v{ver}）高于当前应用（v{SCHEMA_VERSION}），请先升级应用")
    if ver < 1:
        raise ValueError("备份文件缺少 schema_version，不是本应用导出的档案")
    pid = (owner or "").strip()
    if not pid:
        raise ValueError("导入缺少归属，无法确定档案归属")
    birth = prof.get("birth")
    if not isinstance(birth, dict) or not birth.get("year"):
        raise ValueError("备份文件中的档案缺少出生信息")
    baseline = compute_baseline(birth)
    now = datetime.now().isoformat(timespec="seconds")
    uid = prof.get("uuid") or _uuid.uuid4().hex
    with _connect() as conn:
        # uuid 是"同一份档案"的标识：若已被别人占用（uuid 换过设备/被复制过），
        # 不能抢占，只能新生成，否则两行共享一个 uuid 会让将来按 uuid 的操作二义。
        taken = conn.execute("SELECT 1 FROM profiles WHERE uuid=? AND id<>?", (uid, pid)).fetchone()
        if taken:
            uid = _uuid.uuid4().hex
        conn.execute(
            "INSERT INTO profiles(id, birth_json, baseline_json, created_at, updated_at, uuid, schema_version) "
            "VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET birth_json=excluded.birth_json, "
            "baseline_json=excluded.baseline_json, updated_at=excluded.updated_at, uuid=excluded.uuid, "
            "schema_version=excluded.schema_version",
            (pid, json.dumps(birth, ensure_ascii=False), json.dumps(baseline, ensure_ascii=False),
             prof.get("created_at") or now, now, uid, SCHEMA_VERSION),
        )
    return get_profile(pid)


if __name__ == "__main__":
    init_db()
    p = save_profile("test-1", {"year": 2009, "month": 9, "day": 4, "hour": 15, "minute": 34, "gender": 1})
    print("基线:", json.dumps(p["mingju"], ensure_ascii=False, indent=1))
    print("调候:", p["tiaohou"]["yongshen"], "| 格局:", p["geju"]["name"])
    got = get_profile("test-1")
    print("读回:", got["baseline"]["mingju"]["F"], got["baseline"]["mingju"]["J"], got["baseline"]["mingju"]["T0"])
    delete_profile("test-1")
    print("删除后:", get_profile("test-1"))
