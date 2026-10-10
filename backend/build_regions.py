# -*- coding: utf-8 -*-
"""解析 pfinal/city 的 region.sql → 紧凑 JSON 树（省→市→区县，含经纬度）
来源: https://github.com/pfinal/city (民政部/国家统计局行政区划 + 百度经纬度)
输出: backend/china_regions.json
结构: [{"n":"北京市","l":116.413,"t":39.911,"c":[{"n":"北京市","l":116.414,"t":39.911,"d":[{"n":"东城区","l":116.416,"t":39.928}]}]}]
"""
import json
import os
import re
from pathlib import Path

SRC = Path(os.environ.get("TEMP", r"D:\Temp")) / "region.sql"
OUT = Path(__file__).parent / "china_regions.json"

REC = re.compile(r"^\s*\('([^']*)','([^']*)','([^']*)','([\d.]+)','([\d.]+)'")

rows = {}  # id -> (name, lng, lat, parent_id)
for line in SRC.read_text(encoding="utf-8", errors="ignore").splitlines():
    m = REC.match(line)
    if m:
        rid = m.group(1)
        rows[rid] = (m.group(2), round(float(m.group(4)), 4), round(float(m.group(5)), 4), m.group(3))

# 省
prov = []
for rid, (name, lng, lat, pid) in rows.items():
    if pid == "":
        prov.append({"n": name, "l": lng, "t": lat, "c": []})

# 市（父级是省）
for rid, (name, lng, lat, pid) in rows.items():
    if pid and pid in rows and rows[pid][3] == "":
        pname = rows[pid][0]
        for p in prov:
            if p["n"] == pname:
                p["c"].append({"n": name, "l": lng, "t": lat, "d": []})
                break

# 区县（父级是市）
for rid, (name, lng, lat, pid) in rows.items():
    if pid and pid in rows and rows[pid][3] != "":
        cname = rows[pid][0]
        pname = rows[rows[pid][3]][0]
        for p in prov:
            if p["n"] == pname:
                for c in p["c"]:
                    if c["n"] == cname:
                        c["d"].append({"n": name, "l": lng, "t": lat})
                        break
                break

total_city = sum(len(p["c"]) for p in prov)
total_district = sum(len(c["d"]) for p in prov for c in p["c"])
print(f"省 {len(prov)} 市 {total_city} 区县 {total_district}")

# 补全台湾省（源数据不含港澳台）：见 tools/add_taiwan_regions.py
try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent / "tools"))
    from add_taiwan_regions import build_taiwan
    prov = [p for p in prov if p["n"] != "台湾省"] + [build_taiwan()]
    total_city = sum(len(p["c"]) for p in prov)
    total_district = sum(len(c["d"]) for p in prov for c in p["c"])
    print(f"含台湾省后：省 {len(prov)} 市 {total_city} 区县 {total_district}")
except Exception as e:
    print(f"台湾省补全跳过：{e}")

if prov and prov[0]["c"] and prov[0]["c"][0]["d"]:
    print(f"样例: {prov[0]['n']} / {prov[0]['c'][0]['n']} / {prov[0]['c'][0]['d'][0]}")

out = json.dumps(prov, ensure_ascii=False, separators=(",", ":"))
OUT.write_text(out, encoding="utf-8")
print(f"written {OUT} ({OUT.stat().st_size} bytes)")
