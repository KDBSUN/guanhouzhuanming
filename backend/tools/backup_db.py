# -*- coding: utf-8 -*-
"""
备份 / 恢复演练（自检清单 D1）
==============================
"只备份不演练等于没备份"——所以这个脚本有两件事，都别省：
    python tools/backup_db.py                 # 备份：把两个库 + .env 快照到 backups/<时间戳>/
    python tools/backup_db.py --list          # 列出已有备份
    python tools/backup_db.py --drill         # **恢复演练**：把最近一次备份还原到临时目录，
                                              # 逐表比对行数，并真的打开一个还原后的库做读取
    python tools/backup_db.py --restore <dir> # 真出事时用：把备份还原覆盖线上库（会先自动备份现状）

备份内容：
    mingju_profiles.db  命局档案 / 记录 / 最近删除 / 校验台账 / 断言反馈（用户的全部资产）
    terminology.db      术语地图库（可重建，但重建要跑抽取脚本，所以一起备）
    .env                配置与密钥（**含明文密钥**，备份目录请勿放到公开位置）

保留策略：默认留最近 14 份（--keep N 可改），更早的自动清理。
演练为什么能信：还原用的是 SQLite 自己的 backup API（不是复制文件），
所以"备份文件其实损坏/被占用写坏"这种最常见的事故会在演练里当场暴露。
"""
import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
BACKUP_ROOT = BACKEND / "backups"
DBS = ["mingju_profiles.db", "terminology.db"]
KEEP_DEFAULT = 14

# 每个库要核对的关键表（演练按这个清单逐表比行数）
KEY_TABLES = {
    "mingju_profiles.db": ["profiles", "records", "check_log", "claim_feedback"],
    "terminology.db": ["terms", "term_links", "meta"],
}


def _table_counts(db: Path) -> dict:
    out = {}
    if not db.exists():
        return out
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in KEY_TABLES.get(db.name, sorted(have)):
            if t in have:
                try:
                    out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except sqlite3.OperationalError as e:
                    out[t] = f"ERR:{e}"
    return out


def backup(keep: int = KEEP_DEFAULT) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_ROOT / stamp
    dest.mkdir(parents=True, exist_ok=True)
    for name in DBS:
        src = BACKEND / name
        if not src.exists():
            print(f"  · 跳过（不存在）：{name}")
            continue
        # 用 SQLite backup API：即便线上正在写，也能拿到一致快照（复制文件可能拿到半截页）
        with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as s, sqlite3.connect(dest / name) as d:
            s.backup(d)
        counts = _table_counts(dest / name)
        print(f"  · {name}: " + "，".join(f"{k}={v}" for k, v in counts.items()))
    env = BACKEND / ".env"
    if env.exists():
        shutil.copy2(env, dest / ".env")
        print("  · .env（含密钥，请勿外传）")
    (dest / "MANIFEST.txt").write_text(
        "\n".join([
            f"备份时间：{datetime.now().isoformat(timespec='seconds')}",
            f"来源目录：{BACKEND}",
            "内容：mingju_profiles.db（档案/记录/台账/反馈）、terminology.db、.env",
            "恢复：python tools/backup_db.py --restore <本目录>",
        ]), encoding="utf-8")

    # 保留策略
    dirs = sorted([d for d in BACKUP_ROOT.iterdir() if d.is_dir()], reverse=True)
    for old in dirs[keep:]:
        shutil.rmtree(old, ignore_errors=True)
        print(f"  · 清理旧备份：{old.name}")
    print(f"备份完成 → {dest}")
    return dest


def drill(src: Path = None) -> int:
    """恢复演练：还原到临时目录并逐表核对。返回 0=通过，1=失败。"""
    src = src or _latest()
    if not src:
        print("没有可用备份，先跑一次 python tools/backup_db.py")
        return 1
    print(f"恢复演练 ← {src}")
    tmp = BACKEND / "_drill_restore"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    ok = True
    for name in DBS:
        b = src / name
        if not b.exists():
            print(f"  · {name}: 备份里没有，跳过")
            continue
        live = _table_counts(BACKEND / name)
        with sqlite3.connect(f"file:{b}?mode=ro", uri=True) as s, sqlite3.connect(tmp / name) as d:
            s.backup(d)
        got = _table_counts(tmp / name)
        mism = {k: (live.get(k), got.get(k)) for k in got if live.get(k) != got.get(k)}
        # 真的读一次还原后的库（能读出来才算没坏）
        try:
            with sqlite3.connect(tmp / name) as conn:
                conn.execute("PRAGMA integrity_check").fetchone()
                sample = conn.execute(f"SELECT * FROM {sorted(got)[0]} LIMIT 1").fetchone() if got else None
            readable = True
        except Exception as e:
            readable, sample = False, str(e)
        status = "通过" if (readable and not mism) else "不通过"
        if status != "通过":
            ok = False
        print(f"  · {name}: {status}｜还原后可读={readable}｜抽样={'-' if sample is None else '有数据'}")
        for k, (a, b2) in mism.items():
            print(f"      ！行数差异 {k}: 线上={a} 备份={b2}（线上新增数据属正常，备份≤线上即可）")
    print(f"演练结果：{'全部通过' if ok else '存在问题'}（还原目录 {tmp}，确认后可删）")
    return 0 if ok else 1


def restore(src: Path) -> int:
    src = Path(src)
    if not (src / DBS[0]).exists():
        print(f"备份目录里没有 {DBS[0]}：{src}")
        return 1
    safety = backup()                       # 覆盖前先备份现状，别把"最后一次机会"也弄丢
    print(f"（已自动备份当前现状 → {safety}）")
    for name in DBS:
        b = src / name
        if b.exists():
            shutil.copy2(b, BACKEND / name)
            print(f"  · 已还原 {name}")
    print("还原完成。请重启后端使连接失效重连。")
    return 0


def _latest() -> Path | None:
    if not BACKUP_ROOT.exists():
        return None
    dirs = sorted([d for d in BACKUP_ROOT.iterdir() if d.is_dir()], reverse=True)
    return dirs[0] if dirs else None


def main() -> int:
    ap = argparse.ArgumentParser(description="备份 / 恢复演练")
    ap.add_argument("--list", action="store_true", help="列出已有备份")
    ap.add_argument("--drill", action="store_true", help="恢复演练（还原到临时目录并核对）")
    ap.add_argument("--restore", metavar="DIR", help="用指定备份覆盖还原线上库")
    ap.add_argument("--keep", type=int, default=KEEP_DEFAULT, help=f"保留份数（默认 {KEEP_DEFAULT}）")
    a = ap.parse_args()
    if a.list:
        if not BACKUP_ROOT.exists():
            print("还没有备份")
            return 0
        for d in sorted([x for x in BACKUP_ROOT.iterdir() if x.is_dir()], reverse=True):
            size = sum(f.stat().st_size for f in d.glob("*") if f.is_file())
            print(f"  {d.name}  ({size/1024:.0f} KB)")
        return 0
    if a.drill:
        return drill()
    if a.restore:
        return restore(Path(a.restore))
    backup(keep=a.keep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
