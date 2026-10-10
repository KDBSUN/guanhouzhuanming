# -*- coding: utf-8 -*-
"""AI 输出回检回归（aicheck.py）

回检的价值全在**边界**上：报得准的必须一条不漏，报不准的必须老实待在提示级。
所以这里的断言一半是"该报"、一半是"不许报"（假阳性也是 bug，而且更贵——
它会让人连真报一起不信）。
"""
from datetime import date

from aicheck import (extract_dates, check_dates, check_wuxing, check_tier,
                     check_book_citations, review, summarize)


# ---------- 日期抽取 ----------

def test_extract_iso():
    ds = [d.isoformat() for d in extract_dates("宜在 2026-09-25 与 2026-10-03 两日")]
    assert ds == ["2026-09-25", "2026-10-03"]


def test_extract_md_and_cn():
    base = date(2026, 9, 20)
    ds = [d.isoformat() for d in extract_dates("取 9-25，或 10月3日", base)]
    assert ds == ["2026-09-25", "2026-10-03"]


def test_extract_cn_tolerates_spaces_and_hao():
    """「10 月 1 日」「10月1号」都是真实写法，抽不出来就会稳定误报"""
    base = date(2026, 9, 20)
    assert [d.isoformat() for d in extract_dates("10 月 1 日签约", base)] == ["2026-10-01"]
    assert [d.isoformat() for d in extract_dates("10月1号签约", base)] == ["2026-10-01"]


def test_extract_cn_with_year_keeps_that_year():
    """`2027年10月1日` 若被 `10月1日` 抢先匹配，会拿 base 年份补成 2026——静默错一年"""
    base = date(2026, 9, 20)
    assert [d.isoformat() for d in extract_dates("定在 2027年10月1日", base)] == ["2027-10-01"]


def test_extract_md_cross_year_rolls_forward():
    """跨年窗口：起卦在 12 月，AI 写 `1-03`，指的是次年——不能补成同年的 1 月 3 日"""
    base = date(2026, 12, 20)
    assert [d.isoformat() for d in extract_dates("1-03 可行", base)] == ["2027-01-03"]


def test_extract_dedupes_but_keeps_order():
    """同一日期被 iso 与月日两种写法各提一次，只留一条"""
    base = date(2026, 9, 20)
    ds = [d.isoformat() for d in extract_dates("2026-09-25 … 9-25", base)]
    assert ds == ["2026-09-25"]


def test_extract_ignores_invalid_and_bare_numbers():
    """2-30 不存在、`3 个`/`第 5 步` 不是日期——一条都不许抽出来"""
    ds = extract_dates("2-30 不存在，3 个方位，第 5 步，2026-13-01 也不存在",
                       date(2026, 9, 20))
    assert ds == []


def test_extract_does_not_read_iso_as_md():
    """2026-09-25 里的 `09-25` 不得被月日正则再抽一遍（否则同年份判断会跑偏）"""
    ds = extract_dates("2027-09-25", date(2026, 9, 20))
    assert [d.isoformat() for d in ds] == ["2027-09-25"]


# ---------- 日期越界（hard） ----------

def test_check_dates_flags_outside_whitelist():
    """真实故障形态：白名单 8 日，模型自补第 9 日（且干支还推错了）"""
    allow = {"2026-09-25", "2026-09-28"}
    assert check_dates("宜 2026-09-25，另可 2026-09-30", allow) == ["2026-09-30"]


def test_check_dates_empty_whitelist_checks_nothing():
    """没有可比对的表就不能开判——否则会把正文里每个日期都判成越界"""
    assert check_dates("2026-09-25 宜", set()) == []


def test_check_dates_accepts_whitelist_with_time_suffix():
    """白名单项带时间后缀（如 2026-09-25T00:00）时仍算命中"""
    assert check_dates("宜 2026-09-25", {"2026-09-25T00:00:00"}) == []


# ---------- 处方方向（soft） ----------

def test_check_wuxing_flags_wrong_direction():
    hits = check_wuxing("宜补【火】以助体", "土")
    assert [h["wx"] for h in hits] == ["火"]
    assert "宜补" in hits[0]["snippet"]


def test_check_wuxing_allows_remedy_itself():
    assert check_wuxing("宜补土，土色黄，宜往西南", "土") == []


def test_check_wuxing_ignores_negated_advice():
    """「不宜补土」是在**劝阻**，不是开方向——这是最容易误报的一类"""
    assert check_wuxing("不宜补土，土多则滞", "火") == []
    assert check_wuxing("切忌补土", "火") == []


def test_check_wuxing_ignores_principle_talk():
    """「金旺则克木」是讲卦理，不带方向，抓它就是误报"""
    assert check_wuxing("金旺则克木，木受制而事缓", "土") == []


def test_check_wuxing_catches_explicit_prescription_claim():
    assert [h["wx"] for h in check_wuxing("本次处方为金，取金气通关", "土")] == ["金"]


# ---------- 越档（soft） ----------
# 一个前提必须先钉住：**档位只管第二部分·行动建议**。提示词的输出框架写死了
# 「## 第二部分·行动建议」，并明说第一部分·解卦「不受档位影响，始终完整细致地输出」。
# 所以下面每条都得按真实输出形状来写——第一部分 + 第二部分——否则测的不是线上会发生的东西。

_P1 = "## 第一部分·解卦\n\n卦名与卦象：地山谦，谦者退也。\n\n"
_P2 = "## 第二部分·行动建议（S 档）\n\n"


def test_check_tier_s_flags_m_and_l_content():
    txt = _P1 + _P2 + "宜朝南。行业可选文化，饮食宜温。"
    hits = [h["word"] for h in check_tier(txt, "S")]
    assert "行业" in hits and "饮食" in hits


def test_check_tier_m_flags_l_but_not_m():
    assert [h["word"] for h in check_tier(_P1 + _P2 + "行业可选文化，屋宅宜开南窗。", "M")] == []
    assert "饮食" in [h["word"] for h in check_tier(_P1 + _P2 + "饮食宜温", "M")]


def test_check_tier_ignores_part_one_which_is_tier_free():
    """**这条是重写提示词之后才暴露出来的真误报。**

    第一部分按输出契约「不受档位影响，始终完整细致地输出」——解卦讲到疾病门、
    脏腑经络是本职（分占要诀里本来就有「离生体宜热药、坎生体宜冷药」这类条文）。
    档位管的是第二部分，所以在第一部分里找越档词，是拿一把量错了地方的尺子量。
    """
    txt = ("## 第一部分·解卦\n\n卦气衰旺：体卦属土，脾胃脏腑之象，"
           "《梅花易数·衰旺论》云体宜旺。饮食起居皆属常理，与档位无关。\n\n"
           + _P2 + "宜往西南，宜穿黄色。")
    assert check_tier(txt, "S") == []


def test_check_tier_reports_when_part_two_heading_missing():
    """模型没写「第二部分」标题（违反输出契约）时：不硬扫全文制造误报，也不静默放过。

    静默放过等于整类检查悄悄失效；硬扫全文等于把第一部分的卦理词当成越档。
    两条都不行，所以回一条写明的条目，让人在日志里看得见这次没判。
    """
    hits = check_tier(_P1 + "宜朝南。饮食宜温。", "S")
    assert len(hits) == 1 and "未定位到" in hits[0]["word"]


def test_check_tier_exempts_disclaimer_sentences():
    """安全声明里的越档词不算越档——M 档末尾补「如有健康问题请就医」是尽责，不是越档。
    注意「饮食」本身就是 L 档内容，写进 M 档**该报**，不能拿豁免当遮羞布。"""
    assert check_tier(_P1 + _P2 + "行业可选文化。如有健康问题请就医。", "M") == []
    assert [h["word"] for h in check_tier(_P1 + _P2 + "饮食宜温", "M")] == ["饮食"]


def test_check_tier_reports_disclaimer_adjacent_real_advice():
    """豁免按句生效，不得连坐邻句：声明句之后真有 L 档内容，仍要报出来"""
    txt = _P1 + _P2 + "本建议不构成医疗建议。作息宜早睡，饮食宜温。"
    assert sorted(h["word"] for h in check_tier(txt, "M")) == ["作息", "饮食"]


def test_disclaimer_masking_preserves_offsets():
    """遮蔽必须**等长**——否则片段会指到错的地方。

    早先的实现是把句子挑出来重新拼接，遇到孤立的「。」会漏掉一个字符，
    之后所有下标整体偏一位：不报错，只让看日志的人读到一段对不上的上下文。
    """
    from aicheck import _mask_disclaimer_sentences
    for txt in ["。开头就有句号。非医疗建议声明。后面还有内容。",
                "。。本建议不构成医疗建议。。饮食宜温。",
                "饮食宜温。请咨询医师。作息宜早。"]:
        m = _mask_disclaimer_sentences(txt)
        assert len(m) == len(txt), repr(txt)
        # 且未被遮蔽的字必须原位不动
        for i, ch in enumerate(txt):
            if m[i] != "　":
                assert m[i] == ch, (txt, i)


def test_check_tier_skips_when_tier_unknown_or_ambig():
    """全档输出（source=ambig，tier 传空）时不该判越档"""
    assert check_tier("饮食、作息、情志都写", "") == []


# ---------- 书名越界（hard） ----------
# 判据来自提示词「素材边界·三」的原话：「引文只能引用本提示词已写出的字句；
# 称引只许用本提示词已列出的书名篇名……编造出处比说「不知道」更严重」。
# 所以**基准就是模型实收的那一份字句**，不是另编的一张表。
# ⚠️ 是"实收全量"（system ＋ 全部 user 素材块），**不是只 system 一段**——
# 2026-09-19 抓到的那个假案就是只传 system 造成的，回归见本文件末尾两条。

def _prompts():
    import main
    return main.INTERPRETATION_SYSTEM_PROMPT, main.LIUYAO_SYSTEM_PROMPT


def test_book_citations_accepts_names_written_in_prompt():
    """提示词自己写过的书名篇名一律放行——这是规则的字面意思，也是它不会漂移的原因。"""
    meihua, _ = _prompts()
    for txt in ("《梅花易数》云体宜旺", "《梅花易数·衰旺论》曰", "《增广校正梅花易数》分占要诀",
                "《三要灵应篇》言", "《十应奥论》", "《占卜十应诀》"):
        assert check_book_citations(txt, meihua) == [], txt


def test_book_citations_flags_books_not_in_prompt():
    """提示词书单外的书一律判越界——反例用《穷通宝鉴》与《卜筮全书》。

    这不是假想：模型有很强的习惯拿子平线的书讲五行（《滴天髓》《穷通宝鉴》），
    而梅花线的书单里根本没有它们（它是梅花线的提示词，不是子平线的）。

    ⚠️ **2026-09-19 起《滴天髓》不能再当反例**：梅花与六爻的 user prompt 里本来就接了
    那张十干表、表头自己写着《滴天髓·论天干》，白名单已随之补上这一处。
    但补的只是**那一节**——该书其他篇名照样拦，见
    `test_ten_stem_source_is_citable_but_nothing_else_of_that_book`。
    """
    meihua, _ = _prompts()
    got = [h["book"] for h in check_book_citations("《穷通宝鉴·炎上格》说", meihua)]
    assert got == ["穷通宝鉴·炎上格"]
    assert [h["book"] for h in check_book_citations("《穷通宝鉴》云旺则抑之", meihua)] == ["穷通宝鉴"]
    assert [h["book"] for h in check_book_citations("《卜筮全书》云", meihua)] == ["卜筮全书"]
    assert check_book_citations("《穷通宝鉴》云", meihua)[0]["snippet"]


def test_book_citations_is_per_prompt_not_one_global_list():
    """**六爻与梅花各用各的基准**——拿错一份，会把对方合法的书名全判成编造。

    这是本办法最容易被写错的地方：一个全局白名单看着更省事，
    但梅花没有《增删卜易》、六爻没有《梅花易数》，两边都合法且互不重叠。
    """
    meihua, liuyao = _prompts()
    # 六爻提示词写过的，梅花判越界
    assert check_book_citations("《增删卜易·用神元神忌神仇神章》", meihua)
    assert check_book_citations("《增删卜易·用神元神忌神仇神章》", liuyao) == []
    # 梅花提示词写过的，六爻判越界
    assert check_book_citations("《梅花易数·衰旺论》", liuyao)
    assert check_book_citations("《梅花易数·衰旺论》", meihua) == []


def test_book_citations_tolerates_composite_writing():
    """写法差异不是内容差异：《辟〈增删卜易〉之谬》用书名号套书名号，
    比对前要把书名号、括号、间隔号、空白一并抹掉，否则报的全是写法。"""
    _, liuyao = _prompts()
    assert check_book_citations("《辟〈增删卜易〉之谬》一篇", liuyao) == []
    assert check_book_citations("《卜筮正宗 · 旺相休囚论》", liuyao) == []


def test_book_citations_skips_when_no_baseline():
    """没有基准就不判——不能拿空基准把正文里每个书名都判成编造。"""
    assert check_book_citations("《滴天髓》云", "") == []


def test_book_citations_dedupes():
    meihua, _ = _prompts()
    hits = check_book_citations("《穷通宝鉴》云…又说《穷通宝鉴》曰", meihua)
    assert len(hits) == 1


def test_review_book_violation_is_hard_not_advisory():
    """书名越界算**判定级**：名单内/名单外是确定的，不猜语气。
    它和日期同级，会翻 ok、会出到前端。"""
    meihua, _ = _prompts()
    res = review("《穷通宝鉴》云旺则抑之。", allowed_dates={"2026-09-25"}, prompt_base=meihua)
    assert res["ok"] is False
    assert [i["kind"] for i in res["issues"]] == ["book"]
    assert res["advisories"] == []


def test_review_without_prompt_skips_book_check_only():
    """不传 prompt_base（如旧调用点）时只跳过书名这一类，别的照跑。"""
    res = review("宜在 2026-09-30 行事", allowed_dates={"2026-09-25"}, prompt_base="")
    assert [i["kind"] for i in res["issues"]] == ["date"]
    assert "book(hard)" in res["checked"]


def test_verify_event_carries_book_violation():
    """判定级书名越界要真的出网（`_verify_event` 是接线，`review` 只是数据层）。

    这条单独钉接线：数据层全对、而端点忘了把基准传下去，
    书名这一类就会**静默空转**（基准为空 → check_book_citations 直接返回 []），
    上面所有只调 review() 的测试都看不出来。
    """
    import main
    gd = {"remedy": {"R": "土"}, "yingqi": {"keyi": [{"date": "2026-09-25"}]}}
    txt = "《穷通宝鉴》云旺则抑之。"
    ev = main._verify_event(txt, gd, "我该怎么办",
                            prompt_base=main.INTERPRETATION_SYSTEM_PROMPT)
    assert '"type": "verify"' in ev and "穷通宝鉴" in ev
    # 不传基准时这一类不判（其余照跑），故此处只剩日期类、本句无越界日期 → 不发事件
    assert main._verify_event(txt, gd, "我该怎么办") == ""


def test_ten_stem_source_is_citable_but_nothing_else_of_that_book():
    """【十干体性与润燥】的出处可引，**边界就在这一节**——六爻与梅花两线一致。

    2026-09-19 实测抓到的假案：模型写「据：《滴天髓》戊土条「忌火燥」」，
    回检判"正文称引了本提示词未写出的书名"——**判定级，直接推上用户屏幕**。
    可那一节的表头是我们自己写的：「引擎录自《滴天髓·论天干》，解释五行之性时照此引用」。
    拿自己的嘱咐去告模型，病根是基准只取了 system 那一半。

    两处一起修：① 回检基准＝**模型实收全量**（`main._review_base`）；
    ② 白名单补上这一处（原先两线的白名单都只列本线典籍，表头却写着子平线的书）。

    **本条同时钉住"补白名单不等于开门"**：《滴天髓·通神论》《滴天髓·从象》
    这些该书其他篇名**仍旧判越界**——否则补一处就等于把整本八字书放进断语里。
    这一条也是"基准宽度"那件事唯一还剩的活证据：只 system 与实收全量如今都得放行，
    对照已经消失，所以基准宽度改由 `test_every_verify_call_site_passes_the_whole_prompt`
    从源码层盯住。
    """
    import main
    table = "\n".join(main._stem_texture_reference())
    assert "《滴天髓·论天干》" in table, "十干表不再标出处了？那本条测试要跟着改"
    for nm, sysp in (("六爻", main.LIUYAO_SYSTEM_PROMPT),
                     ("梅花", main.INTERPRETATION_SYSTEM_PROMPT)):
        assert "滴天髓" in sysp, "%s 的白名单没补上这一处" % nm
        base = main._review_base(sysp, table)
        assert check_book_citations("《滴天髓》云戊土性燥", base) == [], nm
        assert check_book_citations("《滴天髓·论天干》云戊土性燥", base) == [], nm
        # 边界：该书其他篇名不许跟着放行
        assert check_book_citations("《滴天髓·通神论》云", base), nm
        assert check_book_citations("《滴天髓·从象》云", base), nm


def test_every_verify_call_site_passes_the_whole_prompt():
    """接线回归：每个 `_verify_event` 调用点都必须走 `_review_base(...)`。

    为什么行为测试之外还要一条**源码级**的：上面那条只能证明"传全量时判得对"，
    管不住端点**日后又退回只传 system 一段**——那正是本次真实发生过的写法，
    而且退回去以后 review() 层的测试**照样全绿**（基准非空，只是窄）。
    这一层没有便宜的办法从行为上测（要起真的 SSE 流），源码断言是够用的下策。
    """
    import inspect
    import main
    src = inspect.getsource(main)
    calls, i = [], 0
    while True:
        j = src.find("_verify_event(", i)
        if j < 0:
            break
        i = j + 1
        if src[max(0, j - 4):j] == "def ":
            continue                      # 定义行本身不算调用点
        k, depth = j + len("_verify_event"), 0
        while k < len(src):
            if src[k] == "(":
                depth += 1
            elif src[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        calls.append(src[j:k + 1])
    # 专业模式（divine_pro）已于 2026-09-19 按产品决定移除，调用点从 4 变 3。
    assert len(calls) >= 3, "只找到 %d 个调用点，预期至少 3 个（梅花两条／六爻／追问）" % len(calls)
    for c in calls:
        assert "_review_base(" in c, "有调用点绕过 _review_base，基准会漏掉 user 那一段：\n" + c


# ---------- AI 提示词必须拿到类物清单（不是让它另编） ----------

def test_suggestion_lines_carry_objects_and_runzao():
    """处方五行 → 落地物清单必须进提示词。

    在此之前提示词里**只有一句"须与处方五行保持一致"**，方位/颜色/数字/物件
    全靠模型自己按五行编——同一卦问两次可以给出不同的方位与物件。
    这条钉住：清单、味分档、润燥都要真的出现在给 AI 的文字里。
    """
    import main
    lines = main._suggestion_lines("金", {"gan": "辛", "note": "取【辛】味"}, "L")
    txt = "\n".join(lines)
    assert "补【金】的落地物" in txt
    assert "方位" in txt and "颜色" in txt and "数字" in txt and "物件" in txt
    # 味分档两列 + 每列的物件 + 润燥
    assert "阳味【庚" in txt and "阴味【辛" in txt
    assert "斧钺" in txt and "首饰" in txt
    assert "润燥" not in txt or "性刚健燥刚" in txt or "性温润清秀" in txt
    assert "未戌燥土" in txt, "庚的润燥忌项必须在"
    # 真指定了某一味才出「本次取味」
    assert "本次取味" in txt


def test_suggestion_lines_respect_tier():
    """档位决定给到哪一层：S 不给屋宅/饮食，M 给屋宅不给饮食，L 两者都给。

    这条与页面上"补五行建议"用同一个 tiering.suggest_dims，口径必须一致——
    否则会出现"页面上没给用户看的屋宅，却让 AI 在 S 档里写出来"。
    """
    import main
    s = "\n".join(main._suggestion_lines("土", None, "S"))
    m = "\n".join(main._suggestion_lines("土", None, "M"))
    l = "\n".join(main._suggestion_lines("土", None, "L"))
    assert "屋宅" not in s and "饮食" not in s
    assert "屋宅" in m and "饮食" not in m
    assert "屋宅" in l and "饮食" in l
    # 三档都要有最基础的方位/颜色/数字
    for t in (s, m, l):
        assert "方位" in t and "颜色" in t and "数字" in t


def test_suggestion_lines_forbid_offlist_items():
    """给清单的同时必须说清"不得给清单外同五行的东西"，
    否则模型仍可自己加一个（比如给"补金"写上"水晶"，而清单里没有）。"""
    import main
    txt = "\n".join(main._suggestion_lines("金", None, "S"))
    assert "不得给出清单之外同五行" in txt


def test_suggestion_lines_empty_when_no_such_element():
    assert __import__("main")._suggestion_lines("", None, "S") == []


def test_stem_texture_reference_has_all_ten():
    """十干体性润燥**全表**要进提示词，不限本次处方那两味。

    为什么必须给全：提示词第三条「不许凭记忆引录原文，称引只许用本提示词已写出的字句」——
    而 AI 讲五行生克时必然说到各干之性。此前提示词里一个干的体性都没写，
    它只能凭记忆说，正好是那条规矩禁止的事。
    """
    import main
    lines = main._stem_texture_reference()
    txt = "\n".join(lines)
    for g in "甲乙丙丁戊己庚辛壬癸":
        assert ("· %s（" % g) in txt, "缺 %s" % g
    # 每条都要有性；宜/忌按原文如实（无则写明"原文未列"，不编）
    assert txt.count("｜性：") == 10
    assert "原文未列" in txt, "丁/己/壬/癸原文无忌项，须如实标注而不是留空"
    # 关键几条抽查（防手滑改错方向）
    assert "庚（金·阳）斧钺之金｜性：刚健燥刚" in txt
    assert "辛（金·阴）首饰之金｜性：温润清秀" in txt


def test_stem_reference_enters_both_prompts():
    """梅花与六爻两个提示词组装函数都要带上这张表——只加一边就是漏。"""
    import inspect
    import main
    for fn in (main.build_user_prompt, main.build_liuyao_user_prompt):
        src = inspect.getsource(fn)
        assert "_stem_texture_reference()" in src, "%s 没接十干表" % fn.__name__


# ---------- 汇总两级不许混 ----------

def test_review_ok_is_decided_by_hard_only():
    """提示级发现再多，ok 仍是 True——否则回检天天喊狼来了"""
    res = review("宜补火，行业可选文化", allowed_dates={"2026-09-25"},
                 remedy_R="土", tier="S", base=date(2026, 9, 20))
    assert res["ok"] is True
    assert res["issues"] == []
    assert {a["kind"] for a in res["advisories"]} == {"wuxing", "tier"}


def test_review_hard_issue_flips_ok():
    res = review("宜在 2026-09-30", allowed_dates={"2026-09-25"}, remedy_R="土")
    assert res["ok"] is False
    assert [i["kind"] for i in res["issues"]] == ["date"]
    assert res["issues"][0]["items"] == ["2026-09-30"]


def test_review_declares_what_it_did_not_check():
    """"没查什么"必须随结果一起返回，免得 ok=True 被读成通篇无懈可击"""
    res = review("宜补土", allowed_dates={"2026-09-25"}, remedy_R="土")
    assert "语义级" in res["not_checked"]
    assert res["checked"] == ["date(hard)", "book(hard)", "wuxing(soft)", "tier(soft)"]


def test_summarize_quiet_when_clean_and_counts_both_levels():
    assert summarize(review("宜补土", {"2026-09-25"}, "土")) == ""
    s = summarize(review("宜在 2026-09-30 补火", {"2026-09-25"}, "土", tier="S"))
    assert "判定级 1 处" in s and "提示级" in s


def test_review_handles_empty_text():
    res = review("", {"2026-09-25"}, "土")
    assert res["ok"] is True and res["advisories"] == []


# ---------- 接线（main.py） ----------
# 上面都是模块级单测；这几条盯的是"接没接上、接错没有"——洞往往出在这里。

def test_yingqi_dates_covers_both_systems():
    """梅花（keyi/xianri）与六爻（zhiri/fenghe/chongri/chongkong/shipo/jishen_chong）
    键名完全不同，白名单必须一份代码通吃。写死键名的代价：yingqi.py 以后加一类
    候选日，回检会**静默漏判**，还会把合法的新候选日反过来判成编造。"""
    import main
    y = {"zhiri": [{"date": "2026-09-25"}],
         "jishen_chong": [{"date": "2026-09-28"}],
         "src": ["《增删卜易》"],                       # 字符串列表，不许被收进来
         "yongshen": {"liuqin": "父母"},               # dict，不是列表，跳过
         "note": "…"}
    assert main._yingqi_dates(y) == {"2026-09-25", "2026-09-28"}
    assert main._yingqi_dates({"keyi": [{"date": "2026-09-25T00:00"}], "xianri": []}) \
        == {"2026-09-25"}


def test_verify_event_silent_when_clean():
    """干净时不发事件——每次解卦都多推一条"我检查过了"是纯噪音"""
    import main
    assert main._verify_event("宜补土，方位西南。", {"remedy": {"R": "土"}}, "我该怎么办") == ""


def test_verify_event_silent_on_soft_only():
    """只有提示级发现时**不出网**。

    这不是洁癖：提示级误报率高得离谱，实测第一次跑就撞上——AI 写
    「不宜大面积金属摆件（再添金则土愈泄）」，理由句里的"添金"被当成"宜添金"命中。
    前端本来就不渲染它，再推给客户端就是纯废流量；留在日志里带片段，人才判得动。
    """
    import main
    # 处方 火，正文里"宜补金" → 五行提示级命中；没有日期越界 → 不该发事件
    ev = main._verify_event("宜补金，金气通关。", {"remedy": {"R": "火"}}, "我该怎么办")
    assert ev == ""


def test_verify_event_still_emits_hard_alongside_soft():
    """判定级和提示级同时命中时，事件照发（且两段都在，前端只渲染判定级）"""
    import main
    gd = {"remedy": {"R": "火"}, "yingqi": {"keyi": [{"date": "2026-09-25"}]}}
    ev = main._verify_event("宜在 2026-09-30 补金", gd, "我该怎么办")
    assert '"type": "verify"' in ev and "2026-09-30" in ev and "wuxing" in ev


def test_verify_event_emits_on_whitelist_breach():
    import main
    gd = {"remedy": {"R": "土"}, "yingqi": {"keyi": [{"date": "2026-09-25"}]}}
    ev = main._verify_event("宜在 2026-09-30 行事", gd, "我该怎么办")
    assert '"type": "verify"' in ev and "2026-09-30" in ev


def test_run_ai_review_never_raises():
    """回检是**旁路**：喂进垃圾也不能炸——它炸了会连累已经流完的解卦"""
    import main
    assert main._run_ai_review(None, None, "") == {}
    assert main._run_ai_review("宜补土", {}, "问题")["ok"] is True


def test_run_ai_review_whitelists_dates_the_user_named():
    """用户提问里点名的日期不算编造——AI 复述它不该被判越界。

    这是真实误报：约束写的是"日期必须取自【应期】"，可用户若问"10 月 1 日签约好不好"，
    AI 复述 10-01 就命中"列外日期"。约束的目的是拦模型自己造日期，不是拦它复述用户给的。
    """
    import main
    from datetime import date
    gd = {"remedy": {"R": "土"},
          "yingqi": {"keyi": [{"date": "2026-09-25"}]}}
    # AI 复述用户点名的 2026-10-01 → 不该报
    res = main._run_ai_review("你问的 2026-10-01 那天不宜动", gd, "10 月 1 日签约好不好")
    assert res["issues"] == []
    assert not any(i["kind"] == "date" for i in res["issues"])
    # 白名单外的另一个日期 → 仍要报（不许因为开了口子就把判定级整个放空）
    res2 = main._run_ai_review("你问的 2026-10-01 那天不宜，可改 2026-11-07",
                               gd, "10 月 1 日签约好不好")
    assert res2["issues"] and res2["issues"][0]["items"] == ["2026-11-07"]
    assert date(2026, 10, 1).isoformat() == "2026-10-01"


# ---------- 输出截断（finish_reason=length）：同样不许静默 ----------
# 与回检同一件事的两半：都是"这次输出有什么不对劲"，都在流结束后才算得出，
# 都走同一条 SSE 通道、同一个前端组件（`common/verify.tsx`），所以放在同一个文件里。
#
# 实测（2026-09-19，deepseek-v4-flash）：4359 字 = 3394 tokens，故 4096 tokens
# ≈ 5250 汉字；而六爻解卦实测出现过 5170 字与 5390 字的正文——正好压在线上。

def test_truncated_event_only_fires_on_length():
    """只有 `finish_reason == "length"` 才算截断。

    `stop` 是正常收尾；`None`（流里没给、或供应商不返回这个字段）也不能乱报——
    把正常结束说成"被截断"，用户会白白重跑一遍，久了就不信这个提示了。
    """
    import main
    assert main._truncated_event({}, 4096) == ""
    assert main._truncated_event(None, 4096) == ""
    assert main._truncated_event({"finish_reason": "stop"}, 4096) == ""
    assert main._truncated_event({"finish_reason": "tool_calls"}, 4096) == ""
    ev = main._truncated_event({"finish_reason": "length"}, 4096)
    assert '"type": "truncated"' in ev and '"limit": 4096' in ev


def test_truncated_event_says_what_is_unaffected():
    """文案要同时说清三件事：哪里没了、**什么没受影响**、接下来怎么办。

    这不是文字洁癖：排盘、用神、处方、应期全是代码算的，一个字都没受影响，
    而用户看到"输出有问题"最容易的反应是**以为整卦废了**。少这半句就是误导。
    """
    import json
    import main
    d = json.loads(main._truncated_event({"finish_reason": "length"}, 2048)[6:])
    assert "截断" in d["message"] and "2048" in d["message"]
    assert "不受影响" in d["hint"] and "再问一次" in d["hint"]


def test_every_stream_call_records_finish_reason_and_reports_truncation():
    """接线回归：每个 `_stream_llm` 调用点都要 ① 传 `state` ② 发截断事件。

    与 `_verify_event` 那条同样的道理——**光有函数没用，得接上**。
    少传 state，`_truncated_event` 永远收到空 dict、永远不报；而这失败是**静默的**：
    测试全绿、日志干净、前端也没有任何异常，用户那边半截话照样当完整断语显示。
    所以这条只能从源码层盯。
    """
    import inspect
    import main
    src = inspect.getsource(main)
    calls, i = [], 0
    while True:
        j = src.find("_stream_llm(", i)
        if j < 0:
            break
        i = j + 1
        if src[max(0, j - 4):j] == "def ":
            continue                      # 定义行本身不算调用点
        k, depth = j + len("_stream_llm"), 0
        while k < len(src):
            if src[k] == "(":
                depth += 1
            elif src[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        calls.append(src[j:k + 1])
    # 专业模式移除后从 4 变 3（见上一条说明）。
    assert len(calls) >= 3, "只找到 %d 个 _stream_llm 调用点，预期至少 3 个" % len(calls)
    for c in calls:
        assert "state=" in c, "调用点没传 state，截断永远不会被发现：\n" + c
    # 每个流式调用点都要有且只有一处对应的截断上报
    assert src.count("_truncated_event(_st,") == len(calls), (
        "_stream_llm 调用 %d 处，_truncated_event 上报 %d 处，对不上"
        % (len(calls), src.count("_truncated_event(_st,")))
