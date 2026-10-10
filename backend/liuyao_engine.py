"""
六爻纳甲排盘引擎
严格依据《增删卜易》（野鹤老人）、《卜筮正宗》（王洪绪）规则：

- 起卦：三枚铜钱摇六次（初爻→上爻）。三背=老阳(动)、两背一字=少阴、
  两字一背=少阳、三字=老阴(动)。
- 八宫卦序 → 定卦宫、世应（首卦世六、游魂世四、归魂世三，应隔世两位）。
- 浑天甲子纳甲 → 逐爻干支五行。
- 六亲：生我父母 / 我生子孙 / 我克妻财 / 克我官鬼 / 比和兄弟（以卦宫五行为"我"）。
- 六神：日干 甲乙→青龙 丙丁→朱雀 戊→勾陈 己→螣蛇 庚辛→白虎 壬癸→玄武，自初爻起循环。
- 动变：阳动变阴、阴动变阳；变爻纳甲取变卦，变爻六亲照本卦宫五行。
- 旬空：六甲旬（lunar_python 计算）。月破：月建冲爻。
"""
import math
from datetime import datetime
from typing import Optional

from lunar_python import Solar

# ============================================================
# 基础数据
# ============================================================
TRIGRAMS = {
    1: {"name": "乾", "symbol": "☰", "wuxing": "金"},
    2: {"name": "兑", "symbol": "☱", "wuxing": "金"},
    3: {"name": "离", "symbol": "☲", "wuxing": "火"},
    4: {"name": "震", "symbol": "☳", "wuxing": "木"},
    5: {"name": "巽", "symbol": "☴", "wuxing": "木"},
    6: {"name": "坎", "symbol": "☵", "wuxing": "水"},
    7: {"name": "艮", "symbol": "☶", "wuxing": "土"},
    8: {"name": "坤", "symbol": "☷", "wuxing": "土"},
}

# 浑天甲子：每卦六爻（初→上）的 天干/地支/五行
NAJIA = {
    1: [("甲", "子", "水"), ("甲", "寅", "木"), ("甲", "辰", "土"), ("壬", "午", "火"), ("壬", "申", "金"), ("壬", "戌", "土")],  # 乾
    2: [("丁", "巳", "火"), ("丁", "卯", "木"), ("丁", "丑", "土"), ("丁", "亥", "水"), ("丁", "酉", "金"), ("丁", "未", "土")],  # 兑
    3: [("己", "卯", "木"), ("己", "丑", "土"), ("己", "亥", "水"), ("己", "酉", "金"), ("己", "未", "土"), ("己", "巳", "火")],  # 离
    4: [("庚", "子", "水"), ("庚", "寅", "木"), ("庚", "辰", "土"), ("庚", "午", "火"), ("庚", "申", "金"), ("庚", "戌", "土")],  # 震
    5: [("辛", "丑", "土"), ("辛", "亥", "水"), ("辛", "酉", "金"), ("辛", "未", "土"), ("辛", "巳", "火"), ("辛", "卯", "木")],  # 巽
    6: [("戊", "寅", "木"), ("戊", "辰", "土"), ("戊", "午", "火"), ("戊", "申", "金"), ("戊", "戌", "土"), ("戊", "子", "水")],  # 坎
    7: [("丙", "辰", "土"), ("丙", "午", "火"), ("丙", "申", "金"), ("丙", "戌", "土"), ("丙", "子", "水"), ("丙", "寅", "木")],  # 艮
    8: [("乙", "未", "土"), ("乙", "巳", "火"), ("乙", "卯", "木"), ("癸", "丑", "土"), ("癸", "亥", "水"), ("癸", "酉", "金")],  # 坤
}

# 八宫卦序（每宫 8 卦，次序即世位依据）: (上卦, 下卦, 卦名, 六十四卦Unicode符号)
PALACE_SEQUENCE = {
    "乾宫": [(1, 1, "乾为天", "䷀"), (1, 5, "天风姤", "䷫"), (1, 7, "天山遁", "䷠"),
             (1, 8, "天地否", "䷋"), (5, 8, "风地观", "䷓"), (7, 8, "山地剥", "䷖"),
             (3, 8, "火地晋", "䷢"), (3, 1, "火天大有", "䷍")],
    "坎宫": [(6, 6, "坎为水", "䷜"), (6, 2, "水泽节", "䷻"), (6, 4, "水雷屯", "䷂"),
             (6, 3, "水火既济", "䷾"), (2, 3, "泽火革", "䷰"), (4, 3, "雷火丰", "䷶"),
             (8, 3, "地火明夷", "䷣"), (8, 6, "地水师", "䷆")],
    "艮宫": [(7, 7, "艮为山", "䷳"), (7, 3, "山火贲", "䷕"), (7, 1, "山天大畜", "䷙"),
             (7, 2, "山泽损", "䷨"), (3, 2, "火泽睽", "䷥"), (1, 2, "天泽履", "䷉"),
             (5, 2, "风泽中孚", "䷼"), (5, 7, "风山渐", "䷴")],
    "震宫": [(4, 4, "震为雷", "䷲"), (4, 8, "雷地豫", "䷏"), (4, 6, "雷水解", "䷧"),
             (4, 5, "雷风恒", "䷟"), (8, 5, "地风升", "䷭"), (6, 5, "水风井", "䷯"),
             (2, 5, "泽风大过", "䷛"), (2, 4, "泽雷随", "䷐")],
    "巽宫": [(5, 5, "巽为风", "䷸"), (5, 1, "风天小畜", "䷈"), (5, 3, "风火家人", "䷤"),
             (5, 4, "风雷益", "䷩"), (1, 4, "天雷无妄", "䷘"), (3, 4, "火雷噬嗑", "䷔"),
             (7, 4, "山雷颐", "䷚"), (7, 5, "山风蛊", "䷑")],
    "离宫": [(3, 3, "离为火", "䷝"), (3, 7, "火山旅", "䷷"), (3, 5, "火风鼎", "䷱"),
             (3, 6, "火水未济", "䷿"), (7, 6, "山水蒙", "䷃"), (5, 6, "风水涣", "䷺"),
             (1, 6, "天水讼", "䷅"), (1, 3, "天火同人", "䷌")],
    "坤宫": [(8, 8, "坤为地", "䷁"), (8, 4, "地雷复", "䷗"), (8, 2, "地泽临", "䷒"),
             (8, 1, "地天泰", "䷊"), (4, 1, "雷天大壮", "䷡"), (2, 1, "泽天夬", "䷪"),
             (6, 1, "水天需", "䷄"), (6, 8, "水地比", "䷇")],
    "兑宫": [(2, 2, "兑为泽", "䷹"), (2, 6, "泽水困", "䷮"), (2, 8, "泽地萃", "䷬"),
             (2, 7, "泽山咸", "䷞"), (6, 7, "水山蹇", "䷦"), (8, 7, "地山谦", "䷎"),
             (4, 7, "雷山小过", "䷽"), (4, 2, "雷泽归妹", "䷵")],
}
PALACE_WUXING = {"乾宫": "金", "兑宫": "金", "离宫": "火", "震宫": "木",
                 "巽宫": "木", "坎宫": "水", "艮宫": "土", "坤宫": "土"}

# 卦序位 → 世爻位置（1-6）；应=世隔两位
# 首卦世六、第2卦世初、第3卦世二、第4卦世三、第5卦世四、第6卦世五、游魂世四、归魂世三
SHI_BY_ORDER = [6, 1, 2, 3, 4, 5, 4, 3]

# 三爻（下→上）→ 卦数
TRIGRAM_BY_LINES = {
    (1, 1, 1): 1,  # 乾
    (1, 1, 0): 2,  # 兑
    (1, 0, 1): 3,  # 离
    (1, 0, 0): 4,  # 震
    (0, 1, 1): 5,  # 巽
    (0, 1, 0): 6,  # 坎
    (0, 0, 1): 7,  # 艮
    (0, 0, 0): 8,  # 坤
}

# 五行生克
SHENG = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}  # 我生
KE = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}      # 我克

# 六神
LIUSHEN_ORDER = ["青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武"]
LIUSHEN_START = {"甲": 0, "乙": 0, "丙": 1, "丁": 1, "戊": 2,
                 "己": 3, "庚": 4, "辛": 4, "壬": 5, "癸": 5}

# 地支关系
CHONG = {"子": "午", "午": "子", "丑": "未", "未": "丑", "寅": "申", "申": "寅",
         "卯": "酉", "酉": "卯", "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳"}
HE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯",
      "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}

# 卦身：子午持世身居初，丑未身居二，寅申身居三，卯酉身居四，辰戌身居五，巳亥身居上
GUASHEN_BY_ZHI = {"子": 1, "午": 1, "丑": 2, "未": 2, "寅": 3, "申": 3,
                  "卯": 4, "酉": 4, "辰": 5, "戌": 5, "巳": 6, "亥": 6}

YAO_NAMES = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]


def _build_lookup():
    """(上卦,下卦) → 宫信息反查表"""
    lookup = {}
    for palace, seq in PALACE_SEQUENCE.items():
        for idx, (up, lo, name, symbol) in enumerate(seq):
            lookup[(up, lo)] = {
                "palace": palace,
                "wuxing": PALACE_WUXING[palace],
                "order": idx,
                "name": name,
                "symbol": symbol,
                "shi": SHI_BY_ORDER[idx],
            }
    return lookup


PALACE_LOOKUP = _build_lookup()


# ============================================================
# 摇杆种子 → 三枚铜钱（确定性，前后端算法一致）
# ============================================================
def fract(v: float) -> float:
    """取小数部分（JS/Python 均为 IEEE-754 double，结果一致）"""
    return v - math.floor(v)


def seed_from_params(x: float, y: float, duration: int, speed: float) -> float:
    """
    摇杆物理参数 → 高精度种子 [0,1)
    捕获释放点坐标 X/Y（px）、拖拽总时长（ms）、平均速度（px/ms）。
    每个参数都按不同比例缩放后求和取小数部分，确保四个维度都对种子有贡献。
    该公式与前端 Joystick 的 seedFromParams 完全一致。
    """
    raw = x * 1000.0 + y * 100.0 + duration / 1000.0 + speed * 1000.0
    return fract(raw)


def coins_from_seed(seed: float) -> list[int]:
    """
    由种子生成 3 个 0/1（模拟三枚铜钱字背，1=背/阳面，0=字/阴面）。

    【2026-09-12 修】旧写法三枚共用同一个倍数、只差一个常数偏移：
        u_i = seed * 2654435761.0 + i * 227018.53125
    数学上这使三枚的结果被死死绑定——设 a = fract(seed*2654435761)：
        c0 = [a ≥ 1/2]；c1 = [fract(a+0.53125) ≥ 1/2]；c2 = [fract(a+0.0625) ≥ 1/2]
    联立可知"三背"与"三字"都不可能成立 → **老阳/老阴永远摇不出来**，
    六爻就没有动爻、没有变卦、没有动变可用神（20 万次实测：三同面 0 次）。
    现值改为三枚各自用不同倍率与盐值（互质），实测四种结果回到三钱法本来的
    1/8（三字·老阴）、3/8（一背·少阳）、3/8（两背·少阴）、1/8（三背·老阳）。
    纯 double 运算，与前端 liuyaoSeed.ts 的 coinsFromSeed 逐位一致。
    """
    mult = (2654435761.0, 4050300333.0, 1103515245.0)
    salt = (227018.53125, 99991.75, 31415.92653)
    coins = []
    for i in range(3):
        u = seed * mult[i] + salt[i]
        coins.append(1 if fract(u) >= 0.5 else 0)
    return coins


def line_from_coins(coins: list[int]) -> dict:
    """
    三枚铜钱 → 爻型
    三背=老阳(动)、两背一字=少阴、两字一背=少阳、三字=老阴(动)
    """
    backs = sum(coins)
    if backs == 3:
        return {"yin_yang": 1, "type": "老阳", "moving": True, "marker": "○"}
    if backs == 2:
        return {"yin_yang": 0, "type": "少阴", "moving": False, "marker": "×"}
    if backs == 1:
        return {"yin_yang": 1, "type": "少阳", "moving": False, "marker": "·"}
    return {"yin_yang": 0, "type": "老阴", "moving": True, "marker": "×"}


# ============================================================
# 起卦时间（lunar_python）
# ============================================================
def get_time_info(dt: Optional[datetime] = None) -> dict:
    """当前(或指定)时间的干支/农历/旬空/月支"""
    now = dt or datetime.now()
    solar = Solar.fromYmdHms(now.year, now.month, now.day, now.hour, now.minute, now.second)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    day_ganzhi = ec.getDay()          # 如 "甲子"
    month_ganzhi = ec.getMonth()      # 如 "丙申"
    return {
        "solar": f"{now.year}年{now.month}月{now.day}日 {now.hour}:{now.minute:02d}",
        "lunar": lunar.toString(),
        "year_ganzhi": ec.getYear(),
        "month_ganzhi": month_ganzhi,
        "day_ganzhi": day_ganzhi,
        "hour_ganzhi": ec.getTime(),
        "day_stem": day_ganzhi[0],
        "month_branch": month_ganzhi[1],
        "xunkong": lunar.getDayXunKong(),   # 如 "戌亥"
    }


# ============================================================
# 排盘
# ============================================================
def _trigram_from_lines(lines: list[int]) -> int:
    return TRIGRAM_BY_LINES[tuple(lines)]


def _liuqin(palace_wx: str, line_wx: str) -> str:
    """六亲：以卦宫五行为'我'"""
    if line_wx == palace_wx:
        return "兄弟"
    if SHENG.get(line_wx) == palace_wx:   # 爻生我
        return "父母"
    if KE.get(line_wx) == palace_wx:      # 爻克我
        return "官鬼"
    if SHENG.get(palace_wx) == line_wx:   # 我生爻
        return "子孙"
    return "妻财"                          # 我克爻


def _build_paipan_from_raw(raw_lines: list[dict], dt: Optional[datetime] = None) -> dict:
    """由逐爻爻型（yin_yang/moving/coins）构建完整排盘"""
    if len(raw_lines) != 6:
        raise ValueError("必须摇满六次")

    # 2. 定上下卦、卦宫、世应
    lower_gua = _trigram_from_lines([raw_lines[i]["yin_yang"] for i in range(3)])
    upper_gua = _trigram_from_lines([raw_lines[i]["yin_yang"] for i in range(3, 6)])
    gua_key = (upper_gua, lower_gua)
    palace_info = PALACE_LOOKUP[gua_key]
    shi_pos = palace_info["shi"]
    ying_pos = ((shi_pos + 2) % 6) + 1

    # 3. 纳甲（本卦逐爻干支）
    ben_najia = NAJIA[lower_gua][0:3] + NAJIA[upper_gua][3:6]

    # 4. 变卦（动爻翻转）
    moving_positions = [i for i in range(6) if raw_lines[i]["moving"]]
    changed_yinyang = [1 - raw_lines[i]["yin_yang"] if raw_lines[i]["moving"] else raw_lines[i]["yin_yang"] for i in range(6)]
    bian_lower_gua = _trigram_from_lines(changed_yinyang[0:3])
    bian_upper_gua = _trigram_from_lines(changed_yinyang[3:6])
    bian_key = (bian_upper_gua, bian_lower_gua)
    bian_info = PALACE_LOOKUP[bian_key]
    bian_najia = NAJIA[bian_lower_gua][0:3] + NAJIA[bian_upper_gua][3:6]

    # 5. 六神起点（日干）
    time_info = get_time_info(dt)
    liush_en_start = LIUSHEN_START.get(time_info["day_stem"], 0)

    # 6. 组装六爻
    lines = []
    for i in range(6):
        line = raw_lines[i]
        gan, zhi, wx = ben_najia[i]
        bian_gan, bian_zhi, bian_wx = bian_najia[i]
        entry = {
            "position": i + 1,
            "name": YAO_NAMES[i],
            "yin_yang": line["yin_yang"],
            "type": line["type"],
            "moving": line["moving"],
            "coins": line.get("coins", []),
            "gan": gan,
            "zhi": zhi,
            "wuxing": wx,
            "liuqin": _liuqin(palace_info["wuxing"], wx),
            "liushen": LIUSHEN_ORDER[(liush_en_start + i) % 6],
            "shi": (i + 1) == shi_pos,
            "ying": (i + 1) == ying_pos,
            "xunkong": zhi in time_info["xunkong"],
            "yuepo": zhi == CHONG.get(time_info["month_branch"], ""),
        }
        if line["moving"]:
            # 变爻纳甲取变卦，变爻六亲照本卦宫五行
            entry["bian"] = {
                "gan": bian_gan, "zhi": bian_zhi, "wuxing": bian_wx,
                "liuqin": _liuqin(palace_info["wuxing"], bian_wx),
            }
        lines.append(entry)

    # 7. 卦逢六冲/六合（本卦、变卦各自判定）
    chong_pairs = [(0, 3), (1, 4), (2, 5)]

    def _hex_markers(najia, order):
        all_chong = all(CHONG.get(najia[a][1]) == najia[b][1] for a, b in chong_pairs)
        all_he = all(HE.get(najia[a][1]) == najia[b][1] for a, b in chong_pairs)
        markers = []
        if all_chong:
            markers.append("六冲")
        if all_he:
            markers.append("六合")
        if order == 6:
            markers.append("游魂")
        elif order == 7:
            markers.append("归魂")
        return markers

    ben_markers = _hex_markers(ben_najia, palace_info["order"])
    bian_markers = _hex_markers(bian_najia, bian_info["order"]) if moving_positions else []

    # 卦身 / 世身 —— 这是两套**不同**的东西，历史上常被混为一谈，必须分开：
    #
    # ① 月卦身（本书正法）：《卜筮正宗·安月卦身诀》"阴世则从午月起，阳世还从子月生。
    #    欲得识其卦中意，从初数至世方真。" —— 阳世初爻起子、阴世初爻起午，数到世爻，
    #    所得地支即卦身。卦身为"所占事之体"，六爻（含飞变伏）皆不见卦身者，事无头绪。
    #    用书自己的例子校验：乾宫首卦世在上爻（阳世），初起子→上爻得巳；
    #    乾卦六爻支为子寅辰午申戌，无巳，故《卜筮正宗》逐卦注"本卦无卦身"。✓
    #
    # ② 世身（《卜筮全书》法）："子午持世身居初，丑未持世身居二……"，即旧 gua_shen。
    #    《卜筮正宗》L1158 明确斥之："今人宗之，大误于事……由此观之，而子午持世身居初爻，
    #    诸谬甚矣。" 故保留旧字段以免破坏既有调用，但**不得再称其为卦身**，
    #    数据层一律以 yue_guashen 为准。
    shi_line = next(l for l in lines if l["shi"])
    shi_zhi = shi_line["zhi"]
    gua_shen_pos = GUASHEN_BY_ZHI.get(shi_zhi)      # ← 旧"世身"，沿用不改

    _ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
    _start = "子" if shi_line.get("yin_yang") == 1 else "午"
    yue_guashen = _ZHI[(_ZHI.index(_start) + shi_line["position"] - 1) % 12]
    yue_guashen_pos = [l["position"] for l in lines if l["zhi"] == yue_guashen]

    return {
        "method": "liuyao",
        "palace": palace_info["palace"],
        "palace_wuxing": palace_info["wuxing"],
        "ben_gua": {
            "name": palace_info["name"],
            "symbol": palace_info["symbol"],
            "palace": palace_info["palace"],
            "markers": ben_markers,
            "upper": {"num": upper_gua, **TRIGRAMS[upper_gua]},
            "lower": {"num": lower_gua, **TRIGRAMS[lower_gua]},
        },
        "bian_gua": {
            "name": bian_info["name"],
            "symbol": bian_info["symbol"],
            "palace": bian_info["palace"],
            "markers": bian_markers,
            "upper": {"num": bian_upper_gua, **TRIGRAMS[bian_upper_gua]},
            "lower": {"num": bian_lower_gua, **TRIGRAMS[bian_lower_gua]},
        } if moving_positions else None,
        "moving_positions": [i + 1 for i in moving_positions],
        "lines": lines,
        "time_info": time_info,
        "markers": ben_markers,
        # gua_shen 是《卜筮全书》的"世身"，**不是**卦身（《卜筮正宗》斥为谬），
        # 仅为向后兼容保留；一切取"卦身"义的地方用 yue_guashen。
        "gua_shen": gua_shen_pos,
        "shi_shen": gua_shen_pos,
        "yue_guashen": yue_guashen,
        "yue_guashen_positions": yue_guashen_pos,
        "yue_guashen_in_gua": bool(yue_guashen_pos),
    }


def build_paipan(throws: list[dict], dt: Optional[datetime] = None) -> dict:
    """
    由 6 次摇杆参数排盘
    throws: [{"x":..,"y":..,"duration":..,"speed":..}, ...] 初爻→上爻
    """
    if len(throws) != 6:
        raise ValueError("必须摇满六次")

    raw_lines = []
    for t in throws:
        seed = seed_from_params(t["x"], t["y"], int(t["duration"]), t["speed"])
        coins = coins_from_seed(seed)
        line = line_from_coins(coins)
        line["coins"] = coins
        line["seed"] = seed
        raw_lines.append(line)

    return _build_paipan_from_raw(raw_lines, dt)


# ============================================================
# 校验/自测（对照《增删卜易》书内卦例）
# ============================================================
def verify_book_cases() -> list[str]:
    """用书内明确排盘的卦例逐项核对引擎输出"""
    errors = []

    def check(label: str, cond: bool, detail: str = ""):
        if not cond:
            errors.append(f"[{label}] {detail}")

    # 例一：巳月甲寅日，占往营中贸易，得「巽之涣」
    # 三爻官鬼辛酉金动，化子孙戊午火；世在六爻兄弟辛卯木
    # 验证构成巽为风（巽宫：初二三爻 辛丑/辛亥/辛酉，四五上爻 辛未/辛巳/辛卯）的基础映射
    check("巽卦爻象(阴阴阳)", _trigram_from_lines([0, 1, 1]) == 5)
    check("乾卦爻象(阳阳阳)", _trigram_from_lines([1, 1, 1]) == 1)
    check("坤卦爻象(阴阴阴)", _trigram_from_lines([0, 0, 0]) == 8)
    check("乾宫晋(游魂)反查", PALACE_LOOKUP[(3, 8)]["name"] == "火地晋")
    check("乾宫晋世位", PALACE_LOOKUP[(3, 8)]["shi"] == 4)
    check("巽宫木爻生我=父母", _liuqin("木", "水") == "父母")
    check("巽宫木爻我克=妻财", _liuqin("木", "土") == "妻财")
    check("巽宫木爻克我=官鬼", _liuqin("木", "金") == "官鬼")
    check("乾宫金爻我生=子孙", _liuqin("金", "水") == "子孙")
    check("乾宫金爻我克=妻财", _liuqin("金", "木") == "妻财")

    # 例二：辰月己巳日（旬空戌亥），占会试，得「观之否」
    # 己日 → 初爻螣蛇；本卦风地观（乾宫，世四应初），六神自初爻: 螣蛇白虎玄武青龙朱雀勾陈
    check("己日起螣蛇", LIUSHEN_START["己"] == 3)
    check("己日初爻螣蛇", LIUSHEN_ORDER[(LIUSHEN_START["己"] + 0) % 6] == "螣蛇")
    check("己日二爻白虎", LIUSHEN_ORDER[(LIUSHEN_START["己"] + 1) % 6] == "白虎")
    check("己日上爻勾陈", LIUSHEN_ORDER[(LIUSHEN_START["己"] + 5) % 6] == "勾陈")

    # 例三：甲日初爻青龙
    check("甲日起青龙", LIUSHEN_ORDER[(LIUSHEN_START["甲"] + 0) % 6] == "青龙")

    # 纳甲抽查：乾内卦初爻甲子水
    check("乾纳甲子", NAJIA[1][0] == ("甲", "子", "水"))
    # 巽内卦二爻辛亥水
    check("巽纳辛亥", NAJIA[5][1] == ("辛", "亥", "水"))
    # 坤外卦五爻癸亥水
    check("坤纳癸亥", NAJIA[8][4] == ("癸", "亥", "水"))

    # 世应：应=世隔两位
    check("世六应三", ((6 + 2) % 6) + 1 == 3)
    check("世初应四", ((1 + 2) % 6) + 1 == 4)
    check("世三应六", ((3 + 2) % 6) + 1 == 6)

    # 旬空/月破/六冲六合标记
    lines = build_paipan([
        {"x": 1.1, "y": 2.2, "duration": 300, "speed": 0.5}] * 6)
    check("排盘含六爻", len(lines["lines"]) == 6)
    check("排盘含时间信息", "day_ganzhi" in lines["time_info"])

    return errors


if __name__ == "__main__":
    errs = verify_book_cases()
    if errs:
        print("校验失败：")
        for e in errs:
            print(" -", e)
    else:
        print("全部书例校验通过 ✅")
