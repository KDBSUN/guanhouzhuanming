# -*- coding: utf-8 -*-
"""
AI 输出回检（丙·2）
====================
把 AI 的成文与**判定层结论**做一致性比对，抓"模型换种说法绕开约束"。

## 能做与不能做，先写在最前面

这条边界就是本模块存在的全部意义——不写清，就会有人以为它是语义审查。

| | 判得了 | 怎么判 |
|---|---|---|
| **日期越界** | ✅ | AI 正文里的日期必须落在代码算出的日期表内（确定性白名单） |
| **越档内容** | ⚠️ | S 档不能说 M／L 档的落地物，M 档不能说 L 档的 |
| **处方方向偏离** | ⚠️ | AI 明说"宜／补／取 X"时，X 与处方 R 不同 |

| | 判不了 | 为什么不做 |
|---|---|---|
| **语义级改写** | ❌ | 把"顺"说成"尚可"、把"忌"说成"慎"——要判就得再上一遍 LLM 去比对，那等于**用一个不确定的东西去校验另一个不确定的东西**。语义级冲突**仍靠人看**，本模块不假装能兜 |

## 两级发现，不许混着报

上面的 ✅ 与 ⚠️ 是**两种东西**，混在一个列表里等于拿启发式冒充确定性：

- **hard（判定级）**：日期越界。白名单是代码算的，日期是正则抽的；
  抽出来的东西**确实是个日期**，不在表内就是不在表内。无需人工再判。
- **soft（提示级）**：越档用词、处方方向。都是**措辞命中**——
  "宜补土"与"不宜补土"、"宜补土以通关（但体卦属土，不可再叠加）"都会被抽中。
  必然有误报，所以只报"疑似"+ **原文片段**，由人一眼定夺。

`ok` 只由 hard 决定。soft 单独列在 `advisories` 里，**不参与 ok**——
否则回检会天天喊狼来了，喊到最后连真狼都没人信。

本模块只**报告**，不改写、不拦截：判定层的结论仍是权威，
回检产出是给站长与反馈台账看的。
"""
import re
from datetime import date as _date

# ---------------------------------------------------------------------------
# 一、日期越界（hard）
# ---------------------------------------------------------------------------
# 中文数字月份/日期不做解析：AI 在这些写法上出现率很低而误判率高——
# 宁可不判，也不报一条假的（"报假"会让人连真报一起不信）。
# 汉字与数字之间允许少量空格："10 月 1 日"是真实用户的常见写法，
# 不放宽就等于在"用户自带日期"这类问法上稳定误报。
_S = r"\s{0,3}"
_RE_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_RE_MD = re.compile(r"(?<![\d\-])(\d{1,2})-(\d{1,2})(?![\d\-])")
# 年份式必须排在纯月日式前面并让后者避开：`2027年10月1日` 若被 `10月1日`
# 抢先匹配，就会拿 base 的年份去补，把 2027 写成 2026——静默判错一年。
_RE_CN_Y = re.compile(r"(?<!\d)(\d{4})%s年%s(\d{1,2})%s月%s(\d{1,2})%s[日号]" % (_S, _S, _S, _S, _S))
_RE_CN = re.compile(r"(?<!\d)(?<!年)(\d{1,2})%s月%s(\d{1,2})%s[日号]" % (_S, _S, _S))

WX = "木火土金水"


def _ymd(y: int, m: int, d: int):
    try:
        return _date(y, m, d)
    except ValueError:
        return None


def extract_dates(text: str, base: _date = None) -> list:
    """从正文里抽出日期，一律归一到 date。

    `base` 用于把 `9-25` 这种缺年份的写法补全（取 base 所在年；若补出来比 base 早半年以上，
    认为它指下一年——跨年窗口时 AI 会写 `1-03` 而实际是次年）。
    """
    base = base or _date.today()
    out, seen = [], set()

    def add(d):
        if d is None:
            return
        k = d.isoformat()
        if k not in seen:
            seen.add(k)
            out.append(d)

    def fix_year(m, dd):
        d = _ymd(base.year, m, dd)
        if d and (base - d).days > 183:
            d = _ymd(base.year + 1, m, dd)
        return d

    for m in _RE_ISO.finditer(text or ""):
        add(_ymd(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in _RE_CN_Y.finditer(text or ""):
        add(_ymd(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in _RE_MD.finditer(text or ""):
        add(fix_year(int(m.group(1)), int(m.group(2))))
    for m in _RE_CN.finditer(text or ""):
        add(fix_year(int(m.group(1)), int(m.group(2))))
    return out


def check_dates(text: str, allowed: set, base: _date = None) -> list:
    """正文里出现的、且**不在白名单内**的日期（ISO 字符串列表）。"""
    allow = {str(a)[:10] for a in (allowed or []) if a}
    if not allow:
        return []          # 没有可比对的表就不查——不能拿空表把人全判了
    return [d.isoformat() for d in extract_dates(text, base)
            if d.isoformat() not in allow]


# ---------------------------------------------------------------------------
# 二、处方向偏离（soft）
# ---------------------------------------------------------------------------
# 动词后紧跟一个五行字，才算"在开方向"；不带方向地提到某个五行
# （"金旺则克木"）是讲卦理，抓它就是误报。
# 否定前缀要挡掉："不宜补土"——两个 lookbehind 分别挡「不X」与「X不」两种位置。
_RE_ADVISE = re.compile(
    r"(?<![不勿莫忌毋])(?<![不勿莫忌毋].)"
    r"(?:宜|应|须|需要|建议|取|补|添|加|选用|采用)\s*[【\[]?\s*([%s])(?![%s])" % (WX, WX)
)
_RE_ADVISE2 = re.compile(
    r"处方\s*[为取是]?\s*[【\[]?\s*([%s])(?![%s])" % (WX, WX)
)


def _snippet(text: str, pos: int, width: int = 14) -> str:
    """截取命中处的上下文，让人一眼定性——soft 项没有片段就等于让人重读全文。"""
    a = max(0, pos - width)
    b = min(len(text), pos + width)
    return ("…" if a else "") + text[a:b].replace("\n", " ") + ("…" if b < len(text) else "")


def check_wuxing(text: str, remedy_R: str) -> list:
    """AI 明说"宜／补／取 X"或"处方为 X"时，X 与处方 R 不同 → 疑似偏离。

    刻意**不**检查"忌 X"：AI 说"忌火"而火正是忌神时那是对的；
    要判"忌"说没说对，需要忌神清单，那属于判定层已经在提示词里给过的东西。
    这里只兜最硬的一条：处方方向。返回 [{"wx","snippet"}, ...]。
    """
    text = text or ""
    if remedy_R not in WX:
        return []
    hits, seen = [], set()
    for rx in (_RE_ADVISE, _RE_ADVISE2):
        for m in rx.finditer(text):
            wx = m.group(1)
            if wx == remedy_R:
                continue
            key = (wx, m.start() // 40)      # 同一段里重复提到同一个五行只报一次
            if key in seen:
                continue
            seen.add(key)
            hits.append({"wx": wx, "snippet": _snippet(text, m.start())})
    return hits


# ---------------------------------------------------------------------------
# 三、越档内容（soft）
# ---------------------------------------------------------------------------
# 档位契约（tiering.py）：S＝方位/颜色/数字/随身物件；M＝+行业职能/屋宅布局；
# L＝+饮食五味/作息起居/健康脏腑/情志调养。越档即"低档说了高档才该有的落地物"。
_TIER_TERMS = {
    "M": ["行业", "职能", "屋宅", "办公空间", "朝向", "材质"],                    # M 档内容
    "L": ["饮食", "五味", "作息", "起居", "四时调养", "健康", "脏腑", "情志"],      # L 档内容
}
# 声明句豁免。注意：L 档要求的「非医疗建议声明」本身**不含**任何越档词
# （已逐字核过 tiering.py 的三条 disclaimer），所以原先按词遮蔽是死代码。
# 真正会误报的是模型自补的安全句——M 档末尾来一句"如有健康问题请就医"，
# 命中「健康」却显然不是越档。故按**句**豁免，不按词。
_TIER_EXEMPT_MARK = ("不构成", "非医疗", "非职业", "仅供参考", "请就医", "请咨询", "声明")
_RE_SENT = re.compile(r"[^。；！？\n]+[。；！？\n]?")

# 档位只管**第二部分·行动建议**。提示词的输出框架（SYSTEM 第 692 行）写死了两个二级标题，
# 并明说第一部分「不受档位影响，始终完整细致地输出」。
# 所以越档只许在第二部分里找——在第一部分里找，等于把一个"三档一模一样"的段落
# 按档位去判，讲卦理时顺口说到「脏腑」就会被报成 S 档越档。**误报是构造出来的，不是偶发。**
_RE_PART2 = re.compile(r"^#{1,6}\s*第二部分", re.M)


def _mask_disclaimer_sentences(text: str) -> str:
    """按**句**遮蔽声明句，**保持长度不变**（命中位置要能原样回指原文取片段）。

    早先的写法是把句子挑出来重新拼接，遇到孤立的「。」这类没有可匹配前缀的字符会漏掉一个，
    整体长度就短了一位——之后所有 `find()` 得到的下标都偏了，片段会指到错的地方。
    这类"片段错位"不会报错，只会让看日志的人读到一段对不上的上下文，最难查。
    """
    chars = list(text or "")
    for m in _RE_SENT.finditer(text or ""):
        s = m.group(0)
        if any(k in s for k in _TIER_EXEMPT_MARK):
            for i in range(m.start(), m.end()):
                chars[i] = "　"
    return "".join(chars)


def check_tier(text: str, tier: str) -> list:
    """越档用词。tier 为空或 source=ambig（全档输出）时不判。

    **只扫「第二部分·行动建议」**（理由见 _RE_PART2 上方）。返回 [{"word","snippet"}, ...]。
    若模型没写那个二级标题（违反输出契约），本次无从定位范围——不硬扫全文制造误报，
    也不静默放过，而是回一条写明的条目，让人在日志里看得见。
    """
    t = (tier or "").strip().upper()
    if t not in ("S", "M"):
        return []
    text = text or ""
    m = _RE_PART2.search(text)
    if not m:
        return [{"word": "（本次未定位到「第二部分·行动建议」，越档未判）", "snippet": ""}]
    start = m.start()
    # 先按句遮蔽声明句再找（长度不变，故下标仍指向原文同一位置）
    scan = _mask_disclaimer_sentences(text)
    banned = list(_TIER_TERMS["L"]) + (list(_TIER_TERMS["M"]) if t == "S" else [])
    hits, seen = [], set()
    for w in banned:
        i = scan.find(w, start)
        if i < 0 or w in seen:
            continue
        seen.add(w)
        hits.append({"word": w, "snippet": _snippet(text, i)})
    return hits


# ---------------------------------------------------------------------------
# 四、书名越界（hard）
# ---------------------------------------------------------------------------
# 提示词的「素材边界·三」原话：
#   「你手里没有典籍全文，**不许凭记忆引录原文**。引文只能引用本提示词已写出的字句；
#     称引只许用本提示词已列出的书名篇名（……）。**本提示词未列出的书名、篇名、条文，
#     一律按「典籍未载」处理——编造出处比说「不知道」更严重。**」
#
# 这句话把"能引什么"钉成了一个**封闭集合**，而且它的形状很特别：
# 它**不是一份需要人去维护的白名单**，而是「**本提示词已写出的字句**」——
# 也就是提示词自己。所以这里不另编一张书名表（编了就迟早与提示词漂移，而且
# "检查器比提示词宽"这种漂移是静默的），而是**直接拿提示词当基准**：
# 正文里每一个《X》里的字，都必须能在**模型实收的全部字句**里找到。
#
# 「全部字句」四个字是 2026-09-19 补上的，原先写的是"system prompt 原文"——
# **那一版是个真错**：六爻端点把【十干体性与润燥】一段放在 **user prompt** 里，
# 而那一节的表头明写「引擎录自《滴天髓·论天干》，解释五行之性时照此引用」。
# 于是模型**照我们自己的嘱咐**引了《滴天髓》，回检却拿只有 system 一段的基准去比，
# 判成"编造出处"，还是**判定级**——直接推到用户屏幕上。实测抓到，非推演。
# 基准比实收窄，报的全是假案；基准比实收宽，才会漏掉真编造。故基准只能等于实收。
#
# 已知边界（不在本层兜）：用户提问原样进 user prompt，所以用户在问题里点名的书名
# 也算"实收字句"、会被放行。这不是漏洞——**模型复述用户自己带来的书名不是编造**；
# 这一层要拦的是模型凭空造出处，不是拦用户带书来问。
#
# 为什么这样最稳：提示词改一个字，基准跟着变，不需要谁记得回来改代码。
# 判据也确实是确定的——"提示词里有没有这几个字"不猜语气、不判语义，只做子串比对
# （与 test_quotes 的"逐字回源"同一套办法）。
_RE_CITE = re.compile(r"《([^》]{1,40})》")
# 比对前把分隔符、书名号、括号、空白一律抹掉再比——模型会写
# 《梅花易数·衰旺论》《卜筮正宗·旺相休囚论》《辟〈增删卜易〉之谬》这类复合写法，
# 逐字比对要先把"写法差异"和"内容差异"分开，否则报的全是写法。
_SQUASH_CHARS = "·．・. 　\t\r\n〈〉《》「」『』（）()"


def _squash(s: str) -> str:
    out = s or ""
    for ch in _SQUASH_CHARS:
        out = out.replace(ch, "")
    return out


def _cite_passes(inner: str, base: str) -> bool:
    """一次称引是否全在基准里。**按成分拆开比对**，不是整串子串。

    为什么不能整串比：AI 会写《增删卜易·三合章》——
    「增删卜易」和「三合章」各自都在提示词里，但隔了几百字，连续子串找不到。
    整串比就会把这条合法称引误判成编造。
    所以拆开「·」逐个成分查，**每个成分都必须在基准里**——
    这样《滴天髓·论天干》在梅花提示词（两个成分都没有）仍然会被拦住，
    而《增删卜易·三合章》（两个成分都有）能正确放行。
    《辟〈增删卜易〉之谬》整条在提示词原文里连续出现，走整串快路。
    """
    sq = _squash(inner)
    if sq in base:
        return True
    parts = [p for p in re.split(r"[·．・]", inner) if _squash(p)]
    return bool(parts) and all(_squash(p) in base for p in parts)


def check_book_citations(text: str, prompt_base: str) -> list:
    """正文里称引的书名篇名，是否都出自**模型实收的全部字句**。

    返回 [{"book","snippet"}, ...]。`prompt_base` 为空则不判——
    没有基准就没法判，不能拿空基准把正文里每个书名都判成编造。

    参数名从 `system_prompt` 改成 `prompt_base`，是为了让**下一个人不会再把
    system 那一段单独递进来**：基准里必须同时有 system 与全部 user 素材块
    （排盘数据、【格局判据】、十干表、类物清单……），少一段就多一批假案。
    main 侧统一走 `_review_base()` 拼这份基准，不要手写拼接。
    """
    base = _squash(prompt_base)
    if not base:
        return []
    hits, seen = [], set()
    for m in _RE_CITE.finditer(text or ""):
        inner = m.group(1).strip()
        if not inner or inner in seen:
            continue
        if _cite_passes(inner, base):
            continue
        seen.add(inner)
        hits.append({"book": inner, "snippet": _snippet(text, m.start())})
    return hits


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
def review(text: str, allowed_dates=None, remedy_R: str = "", tier: str = "",
           base: _date = None, prompt_base: str = "") -> dict:
    """跑完回检，返回发现（**只报告，不改写、不拦截**）。

    ok=True 表示**判定级检查（日期越界、书名越界）通过**——不等于"AI 说的都对"，
    也**不等于提示级没发现**；提示级单列在 advisories 里，不参与 ok。
    语义级改写机器不判，写进 not_checked。

    `prompt_base` 必须传**模型实收的全部字句**（system ＋ 每一个 user 素材块），
    不是只传 system 一段。理由见文件上方「素材边界·三」那段注释。
    """
    text = text or ""

    hard = []
    bad_dates = check_dates(text, allowed_dates or set(), base)
    if bad_dates:
        hard.append({"kind": "date", "detail": "正文出现不在计算表内的日期",
                     "items": bad_dates})
    bad_books = check_book_citations(text, prompt_base)
    if bad_books:
        hard.append({"kind": "book",
                     "detail": "正文称引了本提示词未写出的书名/篇名"
                               "（素材边界·三：称引只许用本提示词已列出的书名篇名）",
                     "items": bad_books})

    advisories = []
    bad_wx = check_wuxing(text, remedy_R)
    if bad_wx:
        advisories.append({"kind": "wuxing",
                           "detail": "疑似处方方向偏离（处方 %s）" % remedy_R,
                           "items": bad_wx})
    bad_tier = check_tier(text, tier)
    if bad_tier:
        advisories.append({"kind": "tier",
                           "detail": "疑似越档（%s 档）" % (tier or "").upper(),
                           "items": bad_tier})

    return {
        "ok": not hard,
        "issues": hard,                                   # 判定级：日期越界、书名越界
        "advisories": advisories,                          # 提示级：需人一眼定夺
        "checked": ["date(hard)", "book(hard)", "wuxing(soft)", "tier(soft)"],
        # 写清"没查什么"，免得有人把 ok=True 读成"通篇无懈可击"
        "not_checked": "语义级改写（把'顺'说成'尚可'一类）——需人看，机器不兜",
    }


def summarize(res: dict) -> str:
    """一句话摘要（给日志/前端提示用）。无发现时返回空串。"""
    if not res:
        return ""
    n = len(res.get("issues") or [])
    m = len(res.get("advisories") or [])
    if not n and not m:
        return ""
    parts = []
    if n:
        parts.append("判定级 %d 处（%s）" % (n, "、".join(i["kind"] for i in res["issues"])))
    if m:
        parts.append("提示级 %d 处（%s）" % (m, "、".join(a["kind"] for a in res["advisories"])))
    return "AI 输出回检：" + "；".join(parts)
