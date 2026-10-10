"""
梅花易数起卦引擎
起卦方式（method 键）：
  yizi   一字占（拆字取笔画）
  erzi   二字占（各取笔画）
  sanzi  三字占（三才：一字上卦、二三字合为下卦）
  duozi  字占：按字数自动分派取数法（1~3 笔画、4~10 声调、11 字以上字数），见 divine_text
  time   时间占（年月日时，年用地支序数）
  shuzi  数字起卦：三个数分任上卦／下卦／动爻（**不是**底本「物数占例」的口径，见 divine_shuzi）
  manual 手动起卦：用户直接指定上下卦与动爻（万物类象）
"""
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

import zhconv

from yaoci_zhu import notes_for as _yaoci_zhu_notes

# ============================================================
# 数据加载
# ============================================================
_data: Optional[dict] = None


def load_data() -> dict:
    """加载 meihua_data.json（单例）"""
    global _data
    if _data is None:
        data_path = Path(__file__).parent.parent / "data" / "meihua_data.json"
        with open(data_path, "r", encoding="utf-8") as f:
            _data = json.load(f)
    return _data


# ============================================================
# 八卦爻象（从下往上：初爻、二爻、三爻）
# ============================================================
BAGUA_YAO = {
    1: [1, 1, 1],  # 乾 ☰
    2: [1, 1, 0],  # 兑 ☱
    3: [1, 0, 1],  # 离 ☲
    4: [1, 0, 0],  # 震 ☳
    5: [0, 1, 1],  # 巽 ☴
    6: [0, 1, 0],  # 坎 ☵
    7: [0, 0, 1],  # 艮 ☶
    8: [0, 0, 0],  # 坤 ☷
}

# 反查：爻象 -> 卦数
YAO_TO_GUA = {tuple(v): k for k, v in BAGUA_YAO.items()}


def number_to_gua(n: int) -> int:
    """卦以八除: 数字 -> 八卦数(1-8), 0 视为 8(坤)"""
    r = n % 8
    return 8 if r == 0 else r


def number_to_yao(n: int) -> int:
    """爻以六除: 数字 -> 动爻(1-6), 0 视为 6"""
    r = n % 6
    return 6 if r == 0 else r


def _derive(n: int, label: str, source: str) -> dict:
    """取数中间量：把「哪个数、除几、余几、得几」原样交给上层去讲。

    存在的理由：AI 必须读引擎算好的数，不能自己重算。若只把最终卦象给它，
    它就会自己倒推出一个"为什么"，那是编。这里把算式本身钉死。
    """
    r8 = n % 8
    r6 = n % 6
    return {
        "gua": {"n": n, "divisor": 8, "remainder": r8,
                "value": 8 if r8 == 0 else r8,
                "note": f"{label}：{source}＝{n}，卦以八除：{n}÷8 余 {r8}"
                        + ("（余 0 视为 8）" if r8 == 0 else "")},
        "yao": {"n": n, "divisor": 6, "remainder": r6,
                "value": 6 if r6 == 0 else r6,
                "note": f"{label}：{source}＝{n}，爻以六除：{n}÷6 余 {r6}"
                        + ("（余 0 视为 6）" if r6 == 0 else "")},
    }


def build_hexagram_lines(upper_gua: int, lower_gua: int) -> list[int]:
    """构建六爻（从下往上：初爻=索引0 ... 上爻=索引5）"""
    lower_lines = BAGUA_YAO[lower_gua]  # 初、二、三爻
    upper_lines = BAGUA_YAO[upper_gua]  # 四、五、上交
    return lower_lines + upper_lines


def lines_to_trigram(lines: list[int]) -> int:
    """三根爻 -> 八卦数"""
    return YAO_TO_GUA.get(tuple(lines), 8)


def get_mutual_hexagram(lines: list[int]) -> tuple[int, int]:
    """
    互卦构建：从本卦六爻中取中间四爻
    二三四爻 -> 下互卦
    三四五爻 -> 上互卦
    返回 (上互卦数, 下互卦数)
    """
    lower_mutual = lines_to_trigram(lines[1:4])   # 二、三、四爻
    upper_mutual = lines_to_trigram(lines[2:5])    # 三、四、五爻
    return upper_mutual, lower_mutual


def get_changed_hexagram(lines: list[int], moving_yao: int) -> tuple[list[int], int, int]:
    """
    变卦构建：动爻翻转(阳变阴、阴变阳)
    返回 (变卦六爻, 变卦上卦数, 变卦下卦数)
    """
    changed = lines.copy()
    changed[moving_yao - 1] = 1 - changed[moving_yao - 1]  # 翻转
    upper = lines_to_trigram(changed[3:6])
    lower = lines_to_trigram(changed[0:3])
    return changed, upper, lower


def determine_tiyong(lines: list[int], moving_yao: int, upper_gua: int, lower_gua: int):
    """
    判定体卦与用卦
    动爻在上卦(4/5/6爻) → 上卦为用, 下卦为体
    动爻在下卦(1/2/3爻) → 下卦为用, 上卦为体
    返回: { "ti": 体卦数, "yong": 用卦数, "ti_wuxing": str, "yong_wuxing": str, "relation": str }
    """
    data = load_data()
    bagua = data["bagua"]
    sheng = data["wuxing_shengke"]["生"]
    ke = data["wuxing_shengke"]["克"]

    if moving_yao <= 3:
        # 动爻在下卦：下为用，上为体
        ti_gua = upper_gua
        yong_gua = lower_gua
    else:
        # 动爻在上卦：上为用，下为体
        ti_gua = lower_gua
        yong_gua = upper_gua

    ti_wx = bagua[str(ti_gua)]["wuxing"]
    yong_wx = bagua[str(yong_gua)]["wuxing"]

    # 判断体用关系
    if ti_wx == yong_wx:
        relation = "比和"
        relation_desc = "体用比和，百事顺遂"
    elif sheng.get(yong_wx) == ti_wx:
        relation = "用生体"
        relation_desc = "用生体，有进益之喜"
    elif sheng.get(ti_wx) == yong_wx:
        relation = "体生用"
        relation_desc = "体生用，有耗失之患"
    elif ke.get(ti_wx) == yong_wx:
        relation = "体克用"
        relation_desc = "体克用，诸事可成但需费劲"
    elif ke.get(yong_wx) == ti_wx:
        relation = "用克体"
        relation_desc = "用克体，诸事不利，宜守不宜攻"
    else:
        relation = "未知"
        relation_desc = ""

    return {
        "ti": ti_gua,
        "yong": yong_gua,
        "ti_wuxing": ti_wx,
        "yong_wuxing": yong_wx,
        "relation": relation,
        "relation_desc": relation_desc,
    }


def _get_stroke(char: str) -> int:
    """查繁体笔画(ftbh)。输入可以是简/繁。"""
    data = load_data()
    stroke_map = data["stroke"]
    # 直接查
    if char in stroke_map:
        return stroke_map[char]
    # 转简体再查
    simple = zhconv.convert(char, "zh-cn")
    if simple in stroke_map:
        return stroke_map[simple]
    # 兜底：用 Unicode 笔画估算（不精确但可用）
    import unicodedata
    try:
        name = unicodedata.name(char)
        if "CJK UNIFIED IDEOGRAPH" in name:
            # 粗略估算
            code = ord(char)
            return (code % 20) + 1  # 非常粗略的兜底
    except ValueError:
        pass
    return 1  # 最终兜底


def _get_tone(char: str) -> int:
    """查声调: 平=1, 上=2, 去=3, 入=4, 未知默认平声=1"""
    data = load_data()
    tone_map = data["tone"]
    # 直接查
    if char in tone_map:
        t = tone_map[char]
        if t == 5:  # 词林正韵的"仄声"，细分默认为去声
            return 3
        return t
    # 转繁体查
    trad = zhconv.convert(char, "zh-hant")
    if trad in tone_map:
        t = tone_map[trad]
        if t == 5:
            return 3
        return t
    # 转简体查
    simple = zhconv.convert(char, "zh-cn")
    if simple in tone_map:
        t = tone_map[simple]
        if t == 5:
            return 3
        return t
    return 1  # 兜底默认平声


def _get_chaizi(char: str) -> list[list[str]]:
    """查拆字数据。输入简/繁均可，返回繁体拆字结果。"""
    data = load_data()
    chaizi_map = data["chaizi"]
    # 直接查
    if char in chaizi_map:
        return chaizi_map[char]
    # 转繁体查
    trad = zhconv.convert(char, "zh-hant")
    if trad in chaizi_map:
        return chaizi_map[trad]
    return []


def _yaoci_zhu(upper_gua: int, lower_gua: int, moving_yao: int):
    """动爻爻辞注释；查不到就返回 None（页面与提示词据此闭嘴，不现编）。"""
    try:
        return _yaoci_zhu_notes(upper_gua, lower_gua, moving_yao)
    except Exception:
        return None


def _build_result(upper_gua: int, lower_gua: int, moving_yao: int,
                  method: str, method_params: dict = None) -> dict:
    """构建完整的排盘结果"""
    data = load_data()
    bagua = data["bagua"]
    hexagrams = data["hexagrams"]

    # 构建本卦六爻
    lines = build_hexagram_lines(upper_gua, lower_gua)

    # 本卦
    ben_key = f"{upper_gua},{lower_gua}"
    ben_gua = hexagrams["by_key"].get(ben_key)
    if not ben_gua:
        raise ValueError(f"找不到本卦: {ben_key}")

    # 互卦
    hu_upper, hu_lower = get_mutual_hexagram(lines)
    hu_key = f"{hu_upper},{hu_lower}"
    hu_gua = hexagrams["by_key"].get(hu_key)

    # 变卦
    changed_lines, bian_upper, bian_lower = get_changed_hexagram(lines, moving_yao)
    bian_key = f"{bian_upper},{bian_lower}"
    bian_gua = hexagrams["by_key"].get(bian_key)

    # 体用
    tiyong = determine_tiyong(lines, moving_yao, upper_gua, lower_gua)

    # 动爻爻辞
    yaoci_text = ""
    yaoci_list = ben_gua.get("yaoci", [])
    if 1 <= moving_yao <= len(yaoci_list):
        yaoci_text = yaoci_list[moving_yao - 1]

    # 卦象符号（Unicode）
    ben_symbol = ben_gua.get("symbol", "?")
    bian_symbol = bian_gua.get("symbol", "?") if bian_gua else "?"
    hu_symbol = hu_gua.get("symbol", "?") if hu_gua else "?"

    # 构建六爻阴阳显示
    yao_display = ["—" if y == 1 else "- -" for y in lines]
    # 标注动爻
    yao_display[moving_yao - 1] = f"[{yao_display[moving_yao - 1]}] ← 动爻"

    result = {
        "method": method,
        "method_params": method_params or {},
        "ben_gua": {
            "key": ben_key,
            "name": ben_gua["name"],
            "symbol": ben_symbol,
            "upper": ben_gua["upper"],
            "lower": ben_gua["lower"],
            "lines": lines,
            "yao_display": yao_display,
            "guaci": ben_gua.get("guaci", ""),
            "daxiang": ben_gua.get("daxiang", ""),
        },
        "hu_gua": {
            "key": hu_key,
            "name": hu_gua["name"] if hu_gua else "未知",
            "symbol": hu_symbol,
            "upper": {"num": hu_upper, "name": bagua[str(hu_upper)]["name"],
                      "symbol": bagua[str(hu_upper)]["symbol"],
                      "wuxing": bagua[str(hu_upper)].get("wuxing", "")},
            "lower": {"num": hu_lower, "name": bagua[str(hu_lower)]["name"],
                      "symbol": bagua[str(hu_lower)]["symbol"],
                      "wuxing": bagua[str(hu_lower)].get("wuxing", "")},
            "guaci": hu_gua.get("guaci", "") if hu_gua else "",
            "daxiang": hu_gua.get("daxiang", "") if hu_gua else "",
        } if hu_gua else None,
        "bian_gua": {
            "key": bian_key,
            "name": bian_gua["name"] if bian_gua else "未知",
            "symbol": bian_symbol,
            "upper": {"num": bian_upper, "name": bagua[str(bian_upper)]["name"],
                      "symbol": bagua[str(bian_upper)]["symbol"],
                      "wuxing": bagua[str(bian_upper)].get("wuxing", "")},
            "lower": {"num": bian_lower, "name": bagua[str(bian_lower)]["name"],
                      "symbol": bagua[str(bian_lower)]["symbol"],
                      "wuxing": bagua[str(bian_lower)].get("wuxing", "")},
            "guaci": bian_gua.get("guaci", "") if bian_gua else "",
            "daxiang": bian_gua.get("daxiang", "") if bian_gua else "",
        } if bian_gua else None,
        "moving_yao": {
            "position": moving_yao,
            "yaoci": yaoci_text,
            # 爻辞注释（逐词训诂，取自《周易》译注本的【注释】）：
            # 《梅花易数》用爻辞是拈字取象——鸡悲鸣占只拈"血去"二字点睛，
            # 要拈字就得知道每个字在讲什么象。那是训诂不是创作，必须来自有出处的本子。
            "yaoci_zhu": _yaoci_zhu(upper_gua, lower_gua, moving_yao),
            "is_yang": lines[moving_yao - 1] == 1,
        },
        "tiyong": tiyong,
    }
    return result


# ============================================================
# 起卦方法
# ============================================================

def divine_yizi(zi: str) -> dict:
    """一字占"""
    # 确保用简体查笔画
    simple = zhconv.convert(zi, "zh-cn")
    ftbh = _get_stroke(simple)

    # 拆字（用繁体）
    chaizi = _get_chaizi(zi)
    chaizi_info = {"char": zi, "ftbh": ftbh, "decomposition": chaizi}

    if chaizi and len(chaizi) > 0 and chaizi[0]:
        # 可拆分：取第一个拆法
        parts = chaizi[0]
        if len(parts) >= 2:
            # 左/上部件 = parts[0]，右/下部件 = parts[1:]
            left_parts = [parts[0]]
            right_parts = parts[1:]

            left_sum = sum(_get_stroke(p) for p in left_parts)
            right_sum = sum(_get_stroke(p) for p in right_parts)

            upper_gua = number_to_gua(left_sum)
            lower_gua = number_to_gua(right_sum)
            moving_yao = number_to_yao(left_sum + right_sum)

            chaizi_info["used_decomposition"] = {
                "left": left_parts, "right": right_parts,
                "left_strokes": left_sum, "right_strokes": right_sum,
            }
        else:
            # 只有一个部件：视为不可拆分
            upper_gua = number_to_gua(ftbh)
            lower_gua = number_to_gua(ftbh)
            moving_yao = number_to_yao(ftbh)
            chaizi_info["used_decomposition"] = None
    else:
        # 不可拆分：上下卦同数
        upper_gua = number_to_gua(ftbh)
        lower_gua = number_to_gua(ftbh)
        moving_yao = number_to_yao(ftbh)
        chaizi_info["used_decomposition"] = None

    if chaizi_info.get("used_decomposition"):
        _u = _derive(left_sum, "上卦", "左部件笔画")
        _l = _derive(right_sum, "下卦", "右部件笔画")
        _m = _derive(left_sum + right_sum, "动爻", "左右部件笔画之和")
    else:
        _u = _derive(ftbh, "上卦", "繁体笔画")
        _l = _derive(ftbh, "下卦", "繁体笔画")
        _m = _derive(ftbh, "动爻", "繁体笔画")

    result = _build_result(upper_gua, lower_gua, moving_yao, "yizi",
                           {"zi": zi, "ftbh": ftbh,
                            "derive": {"upper": _u["gua"], "lower": _l["gua"],
                                       "moving": _m["yao"]}})
    result["chaizi_info"] = chaizi_info
    return result


def divine_erzi(zi1: str, zi2: str) -> dict:
    """二字占"""
    s1 = _get_stroke(zhconv.convert(zi1, "zh-cn"))
    s2 = _get_stroke(zhconv.convert(zi2, "zh-cn"))

    upper_gua = number_to_gua(s1)
    lower_gua = number_to_gua(s2)
    moving_yao = number_to_yao(s1 + s2)

    result = _build_result(upper_gua, lower_gua, moving_yao, "erzi",
                           {"zi1": zi1, "zi2": zi2,
                            "stroke1": s1, "stroke2": s2,
                            "derive": {"upper": _derive(s1, "上卦", "前一字笔画")["gua"],
                                       "lower": _derive(s2, "下卦", "后一字笔画")["gua"],
                                       "moving": _derive(s1 + s2, "动爻", "两字笔画之和")["yao"]}})
    return result


def divine_text(text: str, zi_mode: str = "") -> dict:
    """字占：**按字数自动分派取数法**，用户不需要自己选。

    分界线（两版原文一致；学林本白话另把它写成"必须严格掌握"的规矩）：
      1~3 字   用笔画
      4~10 字  用声调（平 1、上 2、去 3、入 4）
      11 字以上 只用字数
    四字这一档原文两法并列（"合四字的画数除六取动爻。也可以不计画数，而仅以平上去入
    四声起卦"），产品方定：各按 50% 随机取一，界面上不显示；由调用方传 zi_mode 固定，
    同一次起卦的两次请求（先要卦、再 AI 解卦）才能得到同一个卦。

    动爻：一律＝上卦取数 ＋ 下卦取数，再除以六。
    书证算例（《梅花易数》"今日动静如何"六字，L904）：前半声调和 8（坤）、后半声调和
    5（巽），"又以八五总为十三数，除二六一十二，余得一数"——初爻动，不加时辰。

    与数字起卦的分工：本函数**只认汉字**，数字不参与取数。纯数字走 divine_shuzi，
    但两件事必须写清，免得把它当物数占引用：
      1) 入口现状：旧前端 frontend/ 已删「物数占」入口（它与《八卦万物属类》是两套机制——
         一个用数出的数量、一个用事物的类象）；新前端 frontend 仍在使用它。
      2) divine_shuzi 的三数口径（上=n1÷8、下=n2÷8、动=n3÷6）**不是**底本「物数占例」的口径。
         底本（L486-488）是「凡见可数之物，即以此数起作上卦，以时数配作下卦。即以卦数并时数
         总除六，取动爻」——一个数即可成卦，下卦取时辰数。底本口径已录在旧前端
         「万物类象」页签的起卦规则里（CAST_RULES 物数占例条）备查。
    """
    chars = [c for c in text if '一' <= c <= '鿿' or '㐀' <= c <= '䶿']
    n = len(chars)

    if n == 0:
        res = divine_time()
        res["method_params"]["zi_fallback"] = "输入中没有汉字，退回时间占"
        return res
    if n > 100:
        # 学林本《梅花易数》字占章白话："如果总的字数超过百字以上，就没有必要用此方法，
        # 我们可以用'按时间起卦法'等替而代之。" —— 此句是译注建议，不是古籍原文条例。
        res = divine_time()
        res["method_params"]["zi_fallback"] = ("字数 %d 超过百字。学林本字占章白话建议改用时间起卦"
                                               "（此句为译注，非原文条例）" % n)
        return res
    if n == 1:
        return divine_yizi(chars[0])
    if n == 2:
        return divine_erzi(chars[0], chars[1])
    if n == 3:
        return divine_sanzi(chars[0], chars[1], chars[2])
    if n == 4:
        mode = zi_mode if zi_mode in ("tone", "stroke") else \
            ("tone" if random.random() < 0.5 else "stroke")
        return (_zi_by_tone(chars, zi_mode=mode) if mode == "tone"
                else _zi_by_stroke4(chars))
    if n <= 10:
        return _zi_by_tone(chars)
    return _zi_by_count(chars)


def _zi_by_tone(chars, zi_mode=None):
    """声调法（4~10 字）：前半声调之和为上卦、后半声调之和为下卦，
    动爻＝两半声调之和（即全部声调之和）除六。"""
    n = len(chars)
    first_half = chars[:n // 2]
    second_half = chars[n // 2:]
    tone_details, first_sum, second_sum = [], 0, 0
    names = {1: "平", 2: "上", 3: "去", 4: "入"}
    for c in first_half:
        t = _get_tone(c)
        first_sum += t
        tone_details.append({"char": c, "tone": t, "tone_name": names.get(t, "?")})
    for c in second_half:
        t = _get_tone(c)
        second_sum += t
        tone_details.append({"char": c, "tone": t, "tone_name": names.get(t, "?")})
    upper_gua = number_to_gua(first_sum)
    lower_gua = number_to_gua(second_sum)
    total = first_sum + second_sum
    moving_yao = number_to_yao(total)      # ← 书证算例：8+5=13 除六余一（原用字数，错）

    result = _build_result(upper_gua, lower_gua, moving_yao, "duozi",
                           {"text": "".join(chars), "char_count": n,
                            "first_half": "".join(first_half),
                            "second_half": "".join(second_half),
                            "first_sum": first_sum, "second_sum": second_sum,
                            "zi_mode": zi_mode or "tone",
                            "取数": "声调（平1上2去3入4）",
                            "derive": {
                                "upper": _derive(first_sum, "上卦", "前半声调之数")["gua"],
                                "lower": _derive(second_sum, "下卦", "后半声调之数")["gua"],
                                "moving": _derive(total, "动爻", "全部声调之和")["yao"]}})
    result["tone_details"] = {
        "first_half": tone_details[:len(first_half)],
        "second_half": tone_details[len(first_half):],
    }
    return result


def _zi_by_stroke4(chars):
    """四字·笔画法：前两字笔画和为上卦、后两字笔画和为下卦，动爻＝四字笔画总和除六。"""
    strokes = [_get_stroke(zhconv.convert(c, "zh-cn")) for c in chars]
    first_sum = sum(strokes[:2])
    second_sum = sum(strokes[2:])
    upper_gua = number_to_gua(first_sum)
    lower_gua = number_to_gua(second_sum)
    total = first_sum + second_sum
    return _build_result(upper_gua, lower_gua, number_to_yao(total), "duozi",
                         {"text": "".join(chars), "char_count": len(chars),
                          "first_sum": first_sum, "second_sum": second_sum,
                          "zi_mode": "stroke", "取数": "笔画",
                          "derive": {
                              "upper": _derive(first_sum, "上卦", "前两字笔画")["gua"],
                              "lower": _derive(second_sum, "下卦", "后两字笔画")["gua"],
                              "moving": _derive(total, "动爻", "四字笔画总和")["yao"]}})


def _zi_by_count(chars):
    """十一字以上·字数法：前半字数为上卦、后半字数为下卦，动爻＝总字数除六。"""
    n = len(chars)
    a, b = (n // 2, n // 2) if n % 2 == 0 else (n // 2, n - n // 2)
    upper_gua = number_to_gua(a)
    lower_gua = number_to_gua(b)
    return _build_result(upper_gua, lower_gua, number_to_yao(n), "duozi",
                         {"text": "".join(chars), "char_count": n,
                          "first_half": "".join(chars[:a]),
                          "second_half": "".join(chars[a:]),
                          "first_sum": a, "second_sum": b,
                          "取数": "字数（十一字以上专用）",
                          "derive": {
                              "upper": _derive(a, "上卦", "前半字数")["gua"],
                              "lower": _derive(b, "下卦", "后半字数")["gua"],
                              "moving": _derive(n, "动爻", "总字数")["yao"]}})


def divine_sanzi(zi1: str, zi2: str, zi3: str) -> dict:
    """三字占：三字为三才。以一字为上卦，二字为下卦（L532）；
    动爻＝三个字的总笔画数除六（白话 L538）。

    此前这份实现内联在 main.py 的专业模式端点里（该端点前端已不调用），
    现挪进引擎，让所有调用方共用同一份。
    """
    s1 = _get_stroke(zhconv.convert(zi1, "zh-cn"))
    s2 = (_get_stroke(zhconv.convert(zi2, "zh-cn"))
          + _get_stroke(zhconv.convert(zi3, "zh-cn")))
    return _build_result(number_to_gua(s1), number_to_gua(s2),
                         number_to_yao(s1 + s2), "sanzi",
                         {"zi1": zi1, "zi2": zi2, "zi3": zi3, "s1": s1, "s2": s2,
                          "取数": "笔画",
                          "derive": {
                              "upper": _derive(s1, "上卦", "第1字笔画")["gua"],
                              "lower": _derive(s2, "下卦", "第2+3字笔画之和")["gua"],
                              "moving": _derive(s1 + s2, "动爻", "三字笔画之和")["yao"]}})


def divine_duozi(text: str, zi_mode: str = "") -> dict:
    """向后兼容的旧名。现按字数自动分派（1~3 笔画、4~10 声调、11 字以上字数），
    详见 divine_text。"""
    return divine_text(text, zi_mode)



# ============================================================
# 时间占（端法后天起卦之例）
# ============================================================
# 书证（《梅花易数》端法后天起卦之例；两条占例都带完整算式，L868 / L880）：
#   年数＋月数＋日数，除八取上卦；加时辰数，除八取下卦；总数除六取动爻。
#   观梅占：辰5＋十二月12＋十七17＝34，34÷8 余 2 → 兑为上；
#           加申时 9＝43，43÷8 余 3 → 离为下；43÷6 余 1 → 初爻动。泽火革。
#   牡丹占：巳6＋三月3＋十六16＝25，25÷8 余 1 → 乾为上；
#           加卯时 4＝29，29÷8 余 5 → 巽为下；29÷6 余 5 → 五爻动。天风姤。
# 月、日用农历月数/日数；年、时用**地支序数**（子1…亥12）。
_ZHI_SEQ = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]


def divine_time(now: Optional[datetime] = None) -> dict:
    """时间占（端法后天起卦之例）：以年月日时之数起卦。

    now：起卦时刻（缺省取当前时间）。可注入，以便复现书内占例与回归测试。

    年＝年支序数（子1…亥12）；月＝农历月数；日＝农历日数；时＝时辰序数。
    上卦＝(年＋月＋日) 除八取余；下卦＝再加时除八取余；动爻＝总数除六取余。
    余 0 按卦以八除、爻以六除的约定取 8/6。
    """
    from lunar_python import Solar

    now = now or datetime.now()
    lunar = Solar.fromYmdHms(now.year, now.month, now.day,
                             now.hour, now.minute, now.second).getLunar()
    ec = lunar.getEightChar()
    year_zhi = ec.getYear()[-1]
    hour_zhi = ec.getTime()[-1]
    month_num = abs(lunar.getMonth())        # 闰月取本月数
    day_num = lunar.getDay()

    y = _ZHI_SEQ.index(year_zhi) + 1
    h = _ZHI_SEQ.index(hour_zhi) + 1
    n1 = y + month_num + day_num
    n2 = n1 + h
    upper_gua = number_to_gua(n1)
    lower_gua = number_to_gua(n2)
    moving_yao = number_to_yao(n2)

    return _build_result(upper_gua, lower_gua, moving_yao, "time",
                         {"year_zhi": year_zhi, "year_num": y,
                          "month_num": month_num, "day_num": day_num,
                          "hour_zhi": hour_zhi, "hour_num": h,
                          "n1": n1, "n2": n2,
                          "derive": {
                              "upper": _derive(n1, "上卦", "年支%s(%d)＋农历%d月＋%d日"
                                               % (year_zhi, y, month_num, day_num))["gua"],
                              "lower": _derive(n2, "下卦", "加%s时(%d)" % (hour_zhi, h))["gua"],
                              "moving": _derive(n2, "动爻", "总数（含时辰）")["yao"],
                          }})


def divine_shuzi(n1: int, n2: int, n3: int) -> dict:
    """数字起卦：三个数分任上卦／下卦／动爻（上=n1÷8、下=n2÷8、动=n3÷6，余 0 作 8／6）。

    **这不是底本「物数占例」的口径**，别按物数占引用：
      底本 L486-488：「凡见可数之物，即以此数起作上卦，以时数配作下卦。即以卦数并时数总除六，
      取动爻」——一个数（数出的物数）即可成卦，下卦取时辰数，动爻＝(物数＋时辰数)÷6。
      本函数是任取三数，与"数物"无关，底本没有这一法。
    入口现状：旧前端 frontend/ 已删「物数占」按钮；新前端 frontend 仍在使用。
    底本口径已录在旧前端「万物类象」页签的起卦规则里备查。
    """
    upper_gua = number_to_gua(n1)
    lower_gua = number_to_gua(n2)
    moving_yao = number_to_yao(n3)

    result = _build_result(upper_gua, lower_gua, moving_yao, "shuzi",
                           {"n1": n1, "n2": n2, "n3": n3})
    return result



def divine_manual(upper: int, lower: int, moving: int) -> dict:
    """手动起卦：用户直接指定上卦、下卦（先天八卦数 1-8）与动爻（初爻 1 至上爻 6）。

    与端法诸占的区别：**不取余、不换算**——用户给的就是卦。
    这是有意的取舍：万物类象太活，同一只鸟可以因问的主体不同而成不同的卦；
    与其让程序（或 AI）替人猜主体，不如把《八卦万物属类》摆给用户看，
    由用户按"第一念"自己定上下卦与动爻（体用仍由引擎机械判定：动爻所在卦为用）。

    越界值收拢到合法范围（1-8 / 1-6），不做除法换算。
    """
    u = max(1, min(8, int(upper)))
    lo = max(1, min(8, int(lower)))
    m = max(1, min(6, int(moving)))

    result = _build_result(u, lo, m, "manual",
                           {"upper": u, "lower": lo, "moving": m})
    # 取数依据（提示词会逐条念给 AI：这几条是"用户指定"，不是计算）
    names = {1: "乾", 2: "兑", 3: "离", 4: "震", 5: "巽", 6: "坎", 7: "艮", 8: "坤"}
    yao_name = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"][m - 1]
    result["method_params"] = {
        "upper": u, "lower": lo, "moving": m,
        "derive": {
            "upper": {"note": f"上卦：用户手动指定先天数 {u}（{names[u]}）"},
            "lower": {"note": f"下卦：用户手动指定先天数 {lo}（{names[lo]}）"},
            "moving": {"note": f"动爻：用户手动指定 {yao_name}（第 {m} 爻）"},
        },
    }
    return result
