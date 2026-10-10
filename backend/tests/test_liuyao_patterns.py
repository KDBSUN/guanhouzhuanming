# -*- coding: utf-8 -*-
"""六爻格局补算回归。

这些判据此前**只写在系统提示词里、代码一个都没算**，AI 只能自己推。
本测试钉两件事：① 每条判据在书里的成立条件没被写错；② 它们确实进了 prompt。
凡与两书有异者，测试只钉"事实位"，不钉措辞（措辞归 docs/六爻分歧登记表.md）。
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import liuyao_patterns as P                                  # noqa: E402
from liuyao_engine import line_from_coins, _build_paipan_from_raw  # noqa: E402
from liuyao_remedy import liuyao_remedy                      # noqa: E402
from main import build_liuyao_user_prompt                     # noqa: E402

COINS = {}


def _coins_for(kind):
    if not COINS:
        for a in (0, 1):
            for b in (0, 1):
                for c in (0, 1):
                    COINS.setdefault(line_from_coins([a, b, c])["type"], (a, b, c))
    return list(COINS[kind])


def _gua(kinds, dt=datetime(2026, 9, 19, 14, 30)):
    raw = []
    for k in kinds:
        L = line_from_coins(_coins_for(k))
        L["coins"] = _coins_for(k)
        raw.append(L)
    return _build_paipan_from_raw(raw, dt)


# 火雷噬嗑之火山旅：初、三爻动，日辰丙申 —— 二爻寅木静而受申冲且衰 => 日破
CASE = ["老阳", "少阴", "老阴", "少阳", "少阴", "少阳"]


def test_day_zhi_is_derived_from_day_ganzhi():
    """time_info 没有 day_zhi 字段，必须取 day_ganzhi 第二位（曾经读成 None，
    结果暗动/日破一条都检不出来）。"""
    g = _gua(CASE)
    assert "day_zhi" not in g["time_info"]
    assert P._day_zhi(g) == "申"


def test_an_dong_and_ri_po_follow_jia():
    """甲《暗动章》：静爻旺相受日冲为暗动，静爻休囚受日冲为日破。"""
    g = _gua(CASE)
    g["remedy"] = liuyao_remedy(g, "问事")
    rows = P.andong_ripo(g, g["remedy"])
    assert rows, "二爻寅木静而受申冲，必须检出"
    r = next(x for x in rows if x["position"] == 2)
    assert r["判定"] == "日破" and r["旺衰"] == "休囚"
    for x in rows:
        assert "动" not in x["依据"] or "日辰冲" in x["依据"]


def test_jin_tui_shen_is_the_books_eight_pairs():
    """甲《进神退神章》原文八组，逐字核过（异体"戍"从正字"戌"）。"""
    assert P.JINSHEN == {"亥": "子", "寅": "卯", "巳": "午", "申": "酉",
                         "丑": "辰", "辰": "未", "未": "戌", "戌": "丑"}
    assert P.TUISHEN == {"子": "亥", "卯": "寅", "午": "巳", "酉": "申",
                         "辰": "丑", "未": "辰", "戌": "未", "丑": "戌"}
    # 进神/退神必须互逆
    for a, b in P.JINSHEN.items():
        assert P.TUISHEN.get(b) == a, "进神 %s→%s 的退神不对称" % (a, b)


def test_san_mu_reports_fact_not_verdict():
    """三墓只报事实；野鹤的门槛（须休囚无气始见凶危）必须一并带出。"""
    g = _gua(CASE)
    rows = P.san_mu(g)
    assert rows
    for r in rows:
        assert r["入墓"] and "休囚无气" in r["门槛"]


def test_san_mu_tomb_branches_match_the_book():
    """墓支表逐字核对。甲 L2029 原话：「如主事爻临午火，**火墓于戌**，后逢辰日则应之」。

    曾有一版表格误写「水火土墓在辰」——火墓其实在戌，不在辰；水土才是辰。
    这条测试把每个五行都钉住，谁改了表（或改了代码）立刻红。
    """
    assert P.SWMJ["金"]["墓"] == "丑"
    assert P.SWMJ["木"]["墓"] == "未"
    assert P.SWMJ["火"]["墓"] == "戌", "甲原文「火墓于戌」——写成辰就是错的"
    assert P.SWMJ["水"]["墓"] == "辰"
    assert P.SWMJ["土"]["墓"] == "辰"
    # 冲开应期跟着墓支走：火墓戌 → 辰戌相冲 → 辰日应
    assert P.CHONG["戌"] == "辰"


def test_san_mu_three_kinds_detected_separately():
    """日墓/动墓/化墓 三种要**各自**能检出（甲 L2645「古有日墓、动墓、化墓，谓之三墓」；
    L2011「乃用爻入日墓、入动墓，动而化墓」）。

    直接构造最小卦：san_mu 只读 日支、六爻（支/五行/动/变），不依赖纳甲——
    这样三种情形各自可控，不用为凑一个真实卦而把三件事搅在一起。
    """
    def gua(lines, day):
        return {"time_info": {"day_ganzhi": "甲" + day}, "lines": lines}

    W = {"五行": lambda z: {"辰": "水", "戌": "火", "未": "木", "丑": "金"}.get(z, "")}
    # 日墓：日支＝该爻五行之墓（水土墓辰）
    g = gua([{"position": 1, "name": "初爻", "zhi": "子", "wuxing": "水", "moving": False}],
            "辰")
    rows = P.san_mu(g)
    assert len(rows) == 1 and rows[0]["入墓"] == ["日墓"]

    # 动墓：某**动**爻之支＝该爻五行之墓（木动爻化出/动出未 → 木爻入动墓）
    g = gua([{"position": 1, "name": "初爻", "zhi": "寅", "wuxing": "木", "moving": True},
             {"position": 2, "name": "二爻", "zhi": "未", "wuxing": "土", "moving": True}],
            "午")
    rows = P.san_mu(g)
    mu_row = next(x for x in rows if x["五行"] == "木")
    assert "动墓" in mu_row["入墓"]

    # 化墓：动爻变出之支＝自己五行之墓（木动化未）
    g = gua([{"position": 1, "name": "初爻", "zhi": "寅", "wuxing": "木", "moving": True,
              "bian": {"zhi": "未", "wuxing": "土"}}],
            "午")
    rows = P.san_mu(g)
    assert rows and "化墓" in rows[0]["入墓"]

    # 不入墓：日支、动爻、变爻都不是它的墓 → 一条都不出
    g = gua([{"position": 1, "name": "初爻", "zhi": "寅", "wuxing": "木", "moving": False}],
            "午")
    assert P.san_mu(g) == []


def test_yuepo_three_ways_out_are_the_book_words():
    """甲《月破章》出破三法逐字核对：
    「目下虽破，**出月则不破**。今日虽破，**实破之日则不破**，**逢合之日则不破**，
      近应日时，远应年月。惟静而不动，又无日辰动爻生助，实则到底而破矣。」

    噬嗑书例没有月破爻，故自造：酉月占，卦中见午爻（午被酉冲＝月破）。
    """
    g = {"time_info": {"day_ganzhi": "甲辰"},
         "lines": [{"position": 1, "name": "初爻", "gan": "丙", "zhi": "午",
                    "wuxing": "火", "liuqin": "子孙", "yuepo": True, "moving": False}]}
    rows = P.yuepo_state(g)
    assert len(rows) == 1
    r = rows[0]
    conds = r["出破条件"]
    assert len(conds) == 3
    assert any("出月" in c for c in conds), "出破第一法：出月则不破"
    assert any("实破" in c for c in conds), "出破第二法：实破之日则不破"
    assert any("逢合" in c for c in conds), "出破第三法：逢合之日则不破"
    # 逢合的支必须真是该爻的六合（午破合未）
    assert any("未" in c for c in conds), "午之六合为未，括注必须写对"
    # 到底破只属于静爻（动则仍有祸福之基）
    assert r["到底破"] is True and "到底而破" in r["说明"]


def test_yuepo_dong_vs_jing_verdict_differs():
    """同一张表里动爻与静爻的结论必须相反——这正是野鹤那句话的分界。"""
    base = {"yuepo": True, "wuxing": "水", "gan": "丙"}
    dong = dict(base, position=1, name="初爻", zhi="子", moving=True)
    jing = dict(base, position=2, name="二爻", zhi="午", moving=False)
    g = {"time_info": {"day_ganzhi": "甲辰"}, "lines": [dong, jing]}
    rows = {r["position"]: r for r in P.yuepo_state(g)}
    assert rows[1]["到底破"] is False and "仍有祸福之基" in rows[1]["说明"]
    assert rows[2]["到底破"] is True and "到底而破" in rows[2]["说明"]


def test_sanhe_ju_four_groups_and_xuyi():
    """甲《三合章》四局；只两爻动不成局，谓之虚一待用。"""
    assert P.SANHE["水"] == ("申", "子", "辰")
    assert P.SANHE["金"] == ("巳", "酉", "丑")
    assert P.SANHE["火"] == ("寅", "午", "戌")
    assert P.SANHE["木"] == ("亥", "卯", "未")
    g = _gua(CASE)
    ju = P.sanhe_ju(g)
    shui = next((j for j in ju if j["局"].startswith("水局")), None)
    assert shui and shui["成局"] is True, "本卦子辰 + 变出申，水局应成"


def test_gua_fan_yin_by_inner_outer_chong():
    """乙《反吟卦定例第十一》：卦之反吟＝卦变相冲。乾为天初二…四爻动变巽为风，
    内外卦各自相冲（乾巽）。"""
    kinds = ["老阳", "少阳", "少阳", "老阳", "少阳", "少阳"]
    g = _gua(kinds)
    assert g["ben_gua"]["name"] == "乾为天"
    assert g["bian_gua"]["name"] == "巽为风"
    ff = P.fan_fu_yin(g)
    assert ff["卦之反吟"], "乾→巽内外双冲，须判卦之反吟"


def test_fu_yin_when_six_branches_identical():
    """乙《伏吟卦定例第十二》所举诸例皆满足"本卦与变卦六爻地支全同"；
    乾为天变震为雷即其一（子寅辰午申戌复化子寅辰午申戌）。"""
    kinds = ["少阳", "老阳", "老阳", "少阳", "老阳", "老阳"]
    g = _gua(kinds)
    assert g["ben_gua"]["name"] == "乾为天"
    assert g["bian_gua"]["name"] == "震为雷"
    assert [l["zhi"] for l in g["lines"]] == ["子", "寅", "辰", "午", "申", "戌"]
    ff = P.fan_fu_yin(g)
    assert ff["伏吟"], "六爻地支全同，须判伏吟"


def test_xunkong_kind_lists_judges():
    """甲《旬空章》野鹤曰诸条须逐条带出；两书主干已裁一致（登记表 §4 F-02）。"""
    g = _gua(CASE)
    g["remedy"] = liuyao_remedy(g, "问事")
    rows = P.xunkong_kind(g, g["remedy"])
    assert rows, "本卦三爻、上爻旬空"
    for r in rows:
        assert r["判据"] or r["倾向"]
        assert "再占合决" in r["分歧"]


def test_xunkong_youqi_budong_follows_jia():
    """「有气不动亦为空」采甲细目：相而不动之爻作空论；旺而不动仍不为空。

    乙第十《旬空论》只分旺相/休囚两桶、未细论相（登记表 §4 F-02，2026-09-24 裁）。
    构造最小卦：子月占（真空=火，不干扰水爻），两爻旬空、皆静。
    """
    g = {
        "time_info": {"day_ganzhi": "甲辰", "month_branch": "子"},
        "lines": [
            {"position": 1, "name": "初爻", "gan": "丙", "zhi": "子", "wuxing": "水",
             "liuqin": "兄弟", "xunkong": True, "yuepo": False, "moving": False},
            {"position": 2, "name": "二爻", "gan": "丁", "zhi": "丑", "wuxing": "土",
             "liuqin": "兄弟", "xunkong": True, "yuepo": False, "moving": False},
        ],
    }
    remedy = {"details": {"各爻旺衰": [
        {"position": 1, "旺衰": "旺相", "月令五态": "相"},   # 相而不动 → 空（甲）
        {"position": 2, "旺衰": "旺相", "月令五态": "旺"},   # 旺而不动 → 不空（两书同）
    ]}}
    rows = {r["position"]: r for r in P.xunkong_kind(g, remedy)}
    assert "有气不动亦为空" in "".join(rows[1]["判据"])
    assert "倾向于空" in rows[1]["倾向"]
    assert "旺不为空" in "".join(rows[2]["判据"])
    assert "倾向不为空" in rows[2]["倾向"]


def test_yuepo_lists_three_ways_out():
    g = _gua(CASE)
    for r in P.yuepo_state(g):
        assert len(r["出破条件"]) == 3
        assert r["到底破"] is (r["静动"] == "静")


def test_fushen_not_applicable_when_yongshen_is_shi():
    """用神取世/应时本卦必有此爻，无伏神可查——曾经误判为"用神不上卦"。"""
    g = _gua(CASE)
    assert P.fushen_chu(g, "世")["适用"] is False
    assert P.fushen_chu(g, "应")["适用"] is False


def test_fushen_four_out_four_in_when_yongshen_absent():
    """乙《第九问》四出四不入。用书自己的例子：天风姤无财。

    乙 L1056：「假令姤、遁无财，须向乾宫借寅木」；乙 L751（姤卦例）：
    「水生木，谓之『飞来生伏得长生』」——故伏神应为乾宫首卦二爻甲寅木，
    飞神为本卦二爻辛亥水，四态判「飞来生伏」。
    """
    g = _gua(["少阴", "少阳", "少阳", "少阳", "少阳", "少阳"])
    assert g["ben_gua"]["name"] == "天风姤" and g["palace"] == "乾宫"
    assert [l["liuqin"] for l in g["lines"]] == \
        ["父母", "子孙", "兄弟", "官鬼", "兄弟", "父母"]        # 无妻财
    fs = P.fushen_chu(g, "妻财")
    assert fs["适用"] is True
    assert fs["伏神"] == {"地支": "寅", "五行": "木", "六亲": "妻财", "爻位": 2}
    assert fs["飞神"]["干支"] == "辛亥"
    assert fs["飞伏四态"][0]["态"] == "飞来生伏"
    assert fs["判定"] == "伏神得出"
    assert "对策" not in fs, "伏神得出时不得附「再占」对策（登记表 D-02）"
    assert len(fs["四出"]) == 4 and len(fs["四不入"]) == 4


def test_fushen_zaizhan_advice_only_when_hard_to_emerge():
    """登记表 D-02：对策用甲，且**只在判定为难出时**附加。"""
    g = _gua(["少阴", "少阳", "少阳", "少阳", "少阳", "少阳"])
    fs = P.fushen_chu(g, "妻财")
    if fs.get("判定") == "伏神难出":
        assert "再占一卦" in fs.get("对策", "")
    else:
        assert "对策" not in fs


def test_fushen_not_applicable_when_yongshen_present():
    """用神已现、或用神取世/应，都不查伏神。"""
    g = _gua(CASE)
    for q in {l["liuqin"] for l in g["lines"]}:
        assert P.fushen_chu(g, q)["适用"] is False, "%s 已现，不必查伏神" % q
    assert P.fushen_chu(g, "世")["适用"] is False
    assert P.fushen_chu(g, "应")["适用"] is False


def test_no_shensha_variables_are_produced():
    """登记表 D-03：神煞一律不进判定链——本模块不得产出任何神煞变量。"""
    g = _gua(CASE)
    g["remedy"] = liuyao_remedy(g, "问事")
    res = P.analyze(g, g["remedy"], "妻财")
    assert "神煞" in res and isinstance(res["神煞"], str)
    blob = repr({k: v for k, v in res.items() if k != "神煞"})
    for shen in ("贵人", "驿马", "禄马", "天医", "羊刃"):
        assert shen not in blob, "神煞 %s 混进了判定链" % shen


def test_patterns_block_reaches_the_prompt():
    g = _gua(CASE)
    g["remedy"] = liuyao_remedy(g, "问事")
    p = build_liuyao_user_prompt(g, "问事")
    assert "【格局判据（代码依原著条例算出，照此解释，不得重算、不得自行加减）】" in p
    assert "日破" in p or "暗动" in p
    assert "三墓" in p or "入动墓" in p or "入日墓" in p


def test_liuhe_liuchong_yao_level():
    """甲《六合章》「相合之法有六」与《六冲章》「爻冲有五」——此处只算爻与爻之间
    （卦级六冲/六合由引擎 markers 给）。静而逢合谓之合起，动而逢合谓之合绊。"""
    g = _gua(CASE)
    hc = P.liuhe_liuchong(g)
    assert set(hc) == {"合好", "相击", "日月合", "化回头冲"}
    for it in hc["合好"]:
        a, b = it["支"]
        assert P.HE[a] == b
    for it in hc["相击"]:
        a, b = it["支"]
        assert P.CHONG[a] == b
    for it in hc["日月合"]:
        assert it["类"].startswith(("合起", "合绊"))


def test_six_he_six_chong_tables_are_complete():
    """六合六冲各六组（十二支两两配对），互逆且无自合自冲。"""
    assert len(P.HE) == 12 and len(set(P.HE.values())) == 12
    assert len(P.CHONG) == 12 and len(set(P.CHONG.values())) == 12
    for a, b in P.HE.items():
        assert P.HE[b] == a and a != b
    for a, b in P.CHONG.items():
        assert P.CHONG[b] == a and a != b
