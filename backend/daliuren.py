# -*- coding: utf-8 -*-
"""大六壬起课引擎——判运链的占卜层之一。

范围（站长 2026-09-26 裁定）：
- 贵人起法：甲戊庚牛羊（依古歌，不采清代另创歌诀——《六壬金针》L636 亦明言依古歌）。
- 月将换将：中气交节时刻后换将（《六壬大全》L12208「太阳于每月中气过宫，故月将亦逢中气而换」；
  《大六壬指南》L167 全表）。不采《六壬金针》L300 的交气当天整日口径。
- 判运接入走甲：先起课＋标注展示，暂不接裁决链升降档。

书证（库内 books/daliuren/，行号为当前行号）：
- 十干寄宫：《六壬大全》L12152–12158 歌（甲寅乙辰丙戊巳丁己未庚申辛戌壬亥癸丑；阳干寄禄阴干寄冠带）。
- 月将表：《六壬大全》L12210–12236（亥雨水…子大寒雨水）；《大六壬指南》L167 十二将全表。
- 占时：正时/活时（《六壬大全》L12246–12268）。
- 天地盘：月将加占时，顺布十二辰（指南 L167；大全 L12284 癸酉日子时亥将例）。
- 四课：干上神/干阴/支上神/支阴（大全 L12296–12328 两例）。
- 九宗门（大全 L12330–13198 教程各节＋课经正文；《六壬金针》L263–626）：
  贼克（元首/重审，L12390–12396）、比用（知一，L12398–12436）、
  涉害（见机/察微/缀瑕，L12438–12688；课经 L5652/L5678/L5704 格名）、
  遥克（蒿矢/弹射，L12692–12752）、昴星（虎视转篷/冬蛇掩目，L12754–12812）、
  别责（L12814–12890）、八专（含独足，L12892–12972；课经 L6094）、
  伏吟（自任/自信/杜传，L12974–13124；课经 L6232–6360 六日清单）、
  返吟（无依/井栏，L13126–13198；课经 L6410–6498）。
- 返吟有克的具体规则按《指南》占验二十戊辰案（L2695–2705：弃不比之下贼亥、取相比之上克巳，
  三传巳亥巳）与《六壬金针》L602 甲戌例（下贼寅）合校：
  先下贼上按日干阴阳比筛，无则上克下按比筛，再涉害/孟仲/复等；中末传取冲冲。
- 贵人歌与昼夜：《六壬大全》L14040–14054（卯至申昼贵，酉至寅夜贵；甲戊庚牛羊昼丑夜未、
  乙己鼠猴乡、丙丁猪鸡位、壬癸蛇兔藏、六辛逢马虎）；《六壬金针》L632–636 同。
- 贵人顺逆：《六壬大全》L14060「凡贵人在地盘亥子丑寅卯辰位的顺行，在地盘巳午未申酉戌位则逆布」。
- 十二天将次序：《六壬大全》L14036（贵人螣蛇朱雀六合勾陈青龙天空白虎太常玄武太阴天后）；
  《六壬金针》L630 同。
- 遁干：《六壬大全》L14068–14072（从日干支六旬上遁干；甲子日三传午卯子→午遁庚、卯遁丁、子遁甲）。
- 六亲：《六壬大全》L14074–14076（克日干官鬼、生日干父母、比和兄弟、日干所生子孙、日干所克妻财）。
- 空亡：《六壬大全》L12114「甲子旬戌亥空亡」；L7658「孤虚法如甲子旬孤在戌亥」，余旬同法推。
- 驿马：《六壬大全》L6936「驿马者，三合头冲是也」；L6990（申子辰日见功曹为驿马）。
- 课体格名：见机＝涉害深浅异或取孟（课经 L5652/L5802）、察微＝取仲（L5678）、
  缀瑕＝复等（L5704/L5766）、自任/自信（L6260/L6286）、杜传（L6312/L6356）、
  无依/井栏（L6466/L6472）。

已登记的分歧与勘误（详见 docs/判据总表.md 第六节）：
- 教程 L13148 壬子/壬午/壬寅/壬申返吟四行（作午子午/寅申寅）与其自身涉害法推导不符，
  采规则推导（壬×返吟→巳亥巳），以《指南》戊辰案为独立佐证。
- 教程 L13150 乙丑/乙未返吟（作辰戌辰）与其贼克规则不符，采规则推导（戌辰戌）。
- 教程 L13116–13124 伏吟壬辰壬午又诀（亥巳申）与课经 L6312 正文（壬辰亥辰戌、壬午亥午子）
  不一致，采课经正文。
- 《六壬金针》L624 井栏例四（作巳丑辰）与课经 L6472（初=支之驿马、中=支上神、末=干上神）
  不符，采课经（辛丑日→亥未辰）。
- 《六壬大全》L3138 贵人歌「六壬逢马虎午寅」之「壬」为「辛」之讹（同书 L14052 作「六辛逢马虎」，
  且壬癸已占蛇兔之位）。

起课不含断法：课体（九宗门结体）随起课给出；毕法赋诸格、神煞、类象另立里程碑。
"""

from qimen import GAN, ZHI, GZ60, day_gz_rolled, _jieqi_timeline

GZ_INDEX = {gz: i for i, gz in enumerate(GZ60)}

# 十干寄宫（大全 L12152–12158）
JIGONG = {"甲": "寅", "乙": "辰", "丙": "巳", "丁": "未", "戊": "巳",
          "己": "未", "庚": "申", "辛": "戌", "壬": "亥", "癸": "丑"}
# 寄干（涉害巡宫时把地盘宫一并作其寄干之五行看；大全 L12472/L12504/L12508）
JIGAN = {"寅": ["甲"], "辰": ["乙"], "巳": ["丙", "戊"], "未": ["丁", "己"],
         "申": ["庚"], "戌": ["辛"], "亥": ["壬"], "丑": ["癸"]}

GAN_WX = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
          "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
ZHI_WX = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
          "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}  # a 克 b
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}  # a 生 b

ZHI_YANG = "子寅辰午申戌"
GAN_YANG = "甲丙戊庚壬"
CHONG = {"子": "午", "午": "子", "丑": "未", "未": "丑", "寅": "申", "申": "寅",
         "卯": "酉", "酉": "卯", "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳"}
# 三刑（大全 L12986–12992：丑刑戌、戌刑未、未刑丑；寅刑巳、巳刑申、申刑寅；
# 子卯互刑；辰午酉亥自刑）
XING = {"丑": "戌", "戌": "未", "未": "丑", "寅": "巳", "巳": "申", "申": "寅",
        "子": "卯", "卯": "子", "辰": "辰", "午": "午", "酉": "酉", "亥": "亥"}

# 月将：中气交节时刻后换将（大全 L12210–12236；指南 L167）
YUEJIANG = {"冬至": "丑", "大寒": "子", "雨水": "亥", "春分": "戌", "谷雨": "酉",
            "小满": "申", "夏至": "未", "大暑": "午", "处暑": "巳", "秋分": "辰",
            "霜降": "卯", "小雪": "寅"}
# 驿马：三合头冲（大全 L6936）
MA = {"申": "寅", "子": "寅", "辰": "寅", "寅": "申", "午": "申", "戌": "申",
      "巳": "亥", "酉": "亥", "丑": "亥", "亥": "巳", "卯": "巳", "未": "巳"}
# 支前三合（别责柔日用；大全 L12840）：三合局内孟→仲→季→孟
ZHI_SANHE_QIAN = {"巳": "酉", "酉": "丑", "丑": "巳", "亥": "卯", "卯": "未", "未": "亥",
                  "申": "子", "子": "辰", "辰": "申", "寅": "午", "午": "戌", "戌": "寅"}
GAN_HE = {"甲": "己", "己": "甲", "乙": "庚", "庚": "乙", "丙": "辛", "辛": "丙",
          "丁": "壬", "壬": "丁", "戊": "癸", "癸": "戊"}

# 贵人歌（大全 L14044–14054）：(昼贵, 夜贵)
GUIREN = {"甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"),
          "乙": ("子", "申"), "己": ("子", "申"),
          "丙": ("亥", "酉"), "丁": ("亥", "酉"),
          "壬": ("巳", "卯"), "癸": ("巳", "卯"),
          "辛": ("午", "寅")}
TIANJIANG = ["贵人", "螣蛇", "朱雀", "六合", "勾陈", "青龙",
             "天空", "白虎", "太常", "玄武", "太阴", "天后"]

SHUN_GONG = "亥子丑寅卯辰"  # 贵人临此六地盘位顺布天将（大全 L14060）


def tianpan(yue_jiang: str, shi_zhi: str) -> dict:
    """月将加占时，顺布十二辰：返回 {地盘支: 天盘支}。"""
    tp, pos, cur = {}, shi_zhi, yue_jiang
    for _ in range(12):
        tp[pos] = cur
        pos = ZHI[(ZHI.index(pos) + 1) % 12]
        cur = ZHI[(ZHI.index(cur) + 1) % 12]
    return tp


def _ke_pairs(day_gan: str, day_zhi: str, tp: dict) -> list:
    """四课逐一论上下克。返回 [(上神, 下, 课号, 克型)]，克型＝'下贼上'/'上克下'。

    课号 1–4：一课干上、二课干阴、三课支上、四课支阴。
    """
    sk = tp[JIGONG[day_gan]]
    sy = tp[sk]
    zs = tp[day_zhi]
    zy = tp[zs]
    pairs = [(sk, day_gan, 1), (sy, sk, 2), (zs, day_zhi, 3), (zy, zs, 4)]
    out = []
    for shang, xia, i in pairs:
        wx_up = ZHI_WX[shang]
        wx_dn = GAN_WX[xia] if i == 1 else ZHI_WX[xia]
        if wx_dn == KE[wx_up]:
            out.append((shang, xia, i, "上克下"))
        elif wx_up == KE[wx_dn]:
            out.append((shang, xia, i, "下贼上"))
    return out


def _bi_candidates(cands: list, day_gan: str) -> list:
    """阳日用阳阴用阴：返回与日干阴阳相同的候选。"""
    want_yang = day_gan in GAN_YANG
    return [c for c in cands if (c[0] in ZHI_YANG) == want_yang]


def _shehai(pool: list, day_gan: str, day_zhi: str, tp: dict) -> tuple:
    """涉害取初传。pool 元素为 (上神, 下, 课号, 克型)。返回 (上神, 格名)。

    法（大全 L12440–12688）：自所坐之宫顺巡至本家止，计受克/所克之数（地盘支与寄干
    各计一重），深者发用；等则取四孟（见机）、无孟取仲（察微）、复等则阳日取干课
    先见者、阴日取支课先见者（缀瑕）。
    """
    inv = {v: k for k, v in tp.items()}  # 天盘支 → 所临地盘宫

    def depth(c):
        shang, _, _, ktype = c
        start = inv[shang]
        home = shang
        n, pos = 0, start
        while True:
            wx_up = ZHI_WX[shang]
            wx_g = ZHI_WX[pos]
            jigans = JIGAN.get(pos, [])
            if ktype == "下贼上":  # 查上神受克于地盘（地盘支与寄干各计一重）
                if KE[wx_g] == wx_up:
                    n += 1
                for g in jigans:
                    if KE[GAN_WX[g]] == wx_up:
                        n += 1
            else:  # 上克下：查上神所克
                if KE[wx_up] == wx_g:
                    n += 1
                for g in jigans:
                    if KE[wx_up] == GAN_WX[g]:
                        n += 1
            if pos == home:
                break
            pos = ZHI[(ZHI.index(pos) + 1) % 12]
        return n

    ranked = sorted(pool, key=lambda c: (-depth(c), c[3] != "下贼上"))
    top = depth(ranked[0])
    ties = [c for c in pool if depth(c) == top]
    if len(ties) == 1:
        return ties[0][0], "见机"
    meng = [c for c in ties if inv[c[0]] in "寅申巳亥"]
    if len(meng) == 1:
        return meng[0][0], "见机"
    zhong = [c for c in ties if inv[c[0]] in "子午卯酉"]
    if len(zhong) == 1:
        return zhong[0][0], "察微"
    # 复等：阳日取干两课先见者，阴日取支两课先见者（课经 L5766）
    want = {1, 2} if day_gan in GAN_YANG else {3, 4}
    pref = [c for c in ties if c[2] in want] or ties
    pref.sort(key=lambda c: c[2])
    return pref[0][0], "缀瑕"


def _chuan_after_chu(chu: str, tp: dict) -> list:
    """常课中末传：初传之上名中次，中上如临是末居。"""
    return [chu, tp[chu], tp[tp[chu]]]


def _sanchuan(day_gan: str, day_zhi: str, tp: dict, shi_zhi: str, yue_jiang: str) -> tuple:
    """九宗门发三传。返回 (三传列表, 课体名)。"""
    sk = tp[JIGONG[day_gan]]
    zs = tp[day_zhi]
    zy = tp[zs]

    # 伏吟（月将与占时同）：大全 L12984
    if yue_jiang == shi_zhi:
        return _fuyin(day_gan, day_zhi, tp, sk, zs)
    # 返吟（月将与占时冲）：大全 L13142
    if CHONG[yue_jiang] == shi_zhi:
        return _fanyin(day_gan, day_zhi, tp, sk, zs)

    ke = _ke_pairs(day_gan, day_zhi, tp)
    if ke:
        zei = [c for c in ke if c[3] == "下贼上"]
        gk = [c for c in ke if c[3] == "上克下"]
        if zei:
            pool, base = zei, "重审"
        else:
            pool, base = gk, "元首"
        if len(pool) == 1:
            return _chuan_after_chu(pool[0][0], tp), base
        bi = _bi_candidates(pool, day_gan)
        if len(bi) == 1:
            return _chuan_after_chu(bi[0][0], tp), "知一"
        chu, ge = _shehai(bi or pool, day_gan, day_zhi, tp)
        return _chuan_after_chu(chu, tp), "涉害·" + ge

    # 无克：先辨四课备数——两课（八专日）直接八专法（教程 L12898：无克不再取遥克）
    shangs = _four_shangshen(tp, day_gan, day_zhi)
    n = len(set(s for s, _ in shangs))
    if n == 2:
        if day_gan in GAN_YANG:
            chu = ZHI[(ZHI.index(sk) + 2) % 12]  # 干上神顺数三辰（连本位数）
        else:
            chu = ZHI[(ZHI.index(zy) - 2) % 12]   # 支阴神逆数三辰
        chuan = [chu, sk, sk]
        ge = "独足" if len(set(chuan)) == 1 else "八专"
        return chuan, ge

    # 遥克（大全 L12694–12752）：先神遥克日（蒿矢），无则日遥克神（弹射）
    yao_ke = [c for c in shangs if KE[ZHI_WX[c[0]]] == GAN_WX[day_gan]]
    if yao_ke:
        bi = [c for c in yao_ke if (c[0] in ZHI_YANG) == (day_gan in GAN_YANG)]
        chu = (bi or yao_ke)[0][0]
        return _chuan_after_chu(chu, tp), "蒿矢"
    yao_bei = [c for c in shangs if KE[GAN_WX[day_gan]] == ZHI_WX[c[0]]]
    if yao_bei:
        bi = [c for c in yao_bei if (c[0] in ZHI_YANG) == (day_gan in GAN_YANG)]
        chu = (bi or yao_bei)[0][0]
        return _chuan_after_chu(chu, tp), "弹射"

    # 无克无遥：四课全备取昴星，三课取别责
    if n == 4:
        if day_gan in GAN_YANG:
            chu = tp["酉"]; chuan = [chu, zs, sk]; ge = "昴星·虎视转篷"
        else:
            chu = next(p for p, g in tp.items() if g == "酉")
            chuan = [chu, sk, zs]; ge = "昴星·冬蛇掩目"
        return chuan, ge
    if day_gan in GAN_YANG:
        chu = tp[JIGONG[GAN_HE[day_gan]]]
    else:
        chu = ZHI_SANHE_QIAN[day_zhi]
    return [chu, sk, sk], "别责"


def _four_shangshen(tp: dict, day_gan: str, day_zhi: str) -> list:
    sk = tp[JIGONG[day_gan]]
    zs = tp[day_zhi]
    return [(sk, 1), (tp[sk], 2), (zs, 3), (tp[zs], 4)]


def _fuyin(day_gan: str, day_zhi: str, tp: dict, sk: str, zs: str) -> tuple:
    """伏吟三传（课经 L6232–6360）。返回 (三传, 课体名)。"""
    ke = _ke_pairs(day_gan, day_zhi, tp)  # 伏吟盘上仅乙癸二日有克
    if ke:
        chu = ke[0][0]
        if XING[chu] == chu:  # 初传自刑（六乙日辰）
            zhong = zs
            mo = XING[zhong]
            if mo == zhong:
                mo = CHONG[zhong]
        else:
            zhong = XING[chu]
            mo = XING[zhong]
        return [chu, zhong, mo], "伏吟"
    if day_gan in GAN_YANG:
        chu = sk
        zi_xing = XING[chu] == chu
        ge = "杜传" if zi_xing else "自任"
        if zi_xing:
            zhong = zs
        else:
            zhong = XING[chu]
        mo = XING[zhong]
        if mo == zhong:
            mo = CHONG[zhong]
        return [chu, zhong, mo], ge
    chu = zs
    zi_xing = XING[chu] == chu
    ge = "杜传" if zi_xing else "自信"
    if zi_xing:
        zhong = sk
    else:
        zhong = XING[chu]
    mo = XING[zhong]
    if mo == chu:  # 子卯互刑循环：不复再传，取冲（课经 L6312）
        mo = CHONG[zhong]
    return [chu, zhong, mo], ge


def _fanyin(day_gan: str, day_zhi: str, tp: dict, sk: str, zs: str) -> tuple:
    """返吟三传（课经 L6410–6498；指南占验二十案校准比筛次序）。返回 (三传, 课体名)。"""
    ke = _ke_pairs(day_gan, day_zhi, tp)
    if ke:
        zei = [c for c in ke if c[3] == "下贼上"]
        gk = [c for c in ke if c[3] == "上克下"]
        bi = _bi_candidates(zei or gk, day_gan)
        if len(bi) == 1:
            chu = bi[0][0]
        elif bi:
            chu, _ = _shehai(bi, day_gan, day_zhi, tp)
        else:
            # 贼不比（如指南戊辰案之亥）→ 取克中相比者；俱不比 → 涉害于全部克
            bi2 = _bi_candidates(gk if zei else [], day_gan)
            if len(bi2) == 1:
                chu = bi2[0][0]
            elif bi2:
                chu, _ = _shehai(bi2, day_gan, day_zhi, tp)
            else:
                chu, _ = _shehai(ke, day_gan, day_zhi, tp)
        return [chu, CHONG[chu], chu], "返吟·无依"
    # 井栏：无克六日（丁丑己丑辛丑丁未己未辛未）支之驿马发用（课经 L6472）
    chu = MA[day_zhi]
    return [chu, zs, sk], "返吟·井栏"


def bu_tianjiang(day_gan: str, shi_zhi: str, tp: dict) -> dict:
    """布十二天将。返回 {天盘支: 天将}。"""
    zhou = shi_zhi in "卯辰巳午未申"  # 大全 L14040
    gui = GUIREN[day_gan][0 if zhou else 1]
    pos = next(p for p, g in tp.items() if g == gui)  # 贵人所临地盘宫
    shun = pos in SHUN_GONG  # 大全 L14060
    out = {}
    cur = gui
    for jiang in TIANJIANG:
        out[cur] = jiang
        cur = ZHI[(ZHI.index(cur) + (1 if shun else -1)) % 12]
    return out


def dunkun_gz(day_gz: str, chuan: list) -> list:
    """三传遁干（从日干支六旬上遁；旬空二支无遁干，记 '空'）。"""
    idx = GZ_INDEX[day_gz]
    xun = idx - idx % 10
    out = []
    for z in chuan:
        off = (ZHI.index(z) - ZHI.index(GZ60[xun][1])) % 12
        out.append(GZ60[xun + off][0] if off <= 9 else "空")
    return out


def liuqin(day_gan: str, chuan: list) -> list:
    """三传六亲（大全 L14074–14076）。"""
    out = []
    for z in chuan:
        wz, wg = ZHI_WX[z], GAN_WX[day_gan]
        if wg == KE[wz]:
            out.append("官鬼")   # 神克日干
        elif wz == KE[wg]:
            out.append("妻财")   # 日干克神
        elif SHENG[wz] == wg:
            out.append("父母")   # 神生日干
        elif SHENG[wg] == wz:
            out.append("子孙")   # 日干生神
        else:
            out.append("兄弟")
    return out


def xunkong(day_gz: str) -> list:
    """旬空二支（大全 L12114：甲子旬戌亥空亡，余旬同法）。"""
    idx = GZ_INDEX[day_gz]
    xun_zhi = GZ60[idx - idx % 10][1]
    return [ZHI[(ZHI.index(xun_zhi) - 2) % 12], ZHI[(ZHI.index(xun_zhi) - 1) % 12]]


def yue_jiang_at(dt) -> str:
    """中气交节时刻后换将（站长裁定口径）。"""
    timeline = _jieqi_timeline(dt.year)
    cur = None
    for name, t in timeline:
        if name not in YUEJIANG:
            continue
        if t <= dt:
            cur = YUEJIANG[name]
    return cur


def qike_core(day_gz: str, shi_zhi: str, yue_jiang: str, dt=None,
              nianming: dict | None = None, nianming2: dict | None = None) -> dict:
    """起课核心：日干支＋占时支＋月将（供书例夹具与活时起课直接调用）。"""
    day_gan, day_zhi = day_gz[0], day_gz[1]
    tp = tianpan(yue_jiang, shi_zhi)
    sk = tp[JIGONG[day_gan]]
    sy = tp[sk]
    zs = tp[day_zhi]
    zy = tp[zs]
    chuan, keti = _sanchuan(day_gan, day_zhi, tp, shi_zhi, yue_jiang)
    tianj = bu_tianjiang(day_gan, shi_zhi, tp)
    return {
        "日干支": day_gz, "占时": shi_zhi, "月将": yue_jiang,
        "天盘": tp,
        "四课": {"干上": sk, "干阴": sy, "支上": zs, "支阴": zy},
        "三传": chuan,
        "课体": keti,
        "贵人": f"{'昼贵' if shi_zhi in '卯辰巳午未申' else '夜贵'}{GUIREN[day_gan][0 if shi_zhi in '卯辰巳午未申' else 1]}",
        "贵人顺逆": "顺" if next(p for p, g in tp.items() if g == GUIREN[day_gan][0 if shi_zhi in '卯辰巳午未申' else 1]) in SHUN_GONG else "逆",
        "天将": tianj,
        "遁干": dunkun_gz(day_gz, chuan),
        "六亲": liuqin(day_gan, chuan),
        "空亡": xunkong(day_gz),
        "课体判语": KETI_JUYU.get(keti, ""),
        "附加课体": fujia_keti(day_gan, day_zhi, tp, chuan, shi_zhi, tianj, dt, yue_jiang,
                              nianming, nianming2),
        "毕法": bifa(day_gan, day_zhi, tp, chuan, shi_zhi, tianj, keti, dt, yue_jiang,
                    nianming, nianming2),
    }


def qike(dt, shi_zhi: str | None = None, nianzhu: str = "", xingbie: str = "",
         nianzhu2: str = "", xingbie2: str = "") -> dict:
    """按公历时刻起课。默认正时（月将加正时）；shi_zhi 可指定活时。
    nianzhu/xingbie 为求占者出生年干支与性别（本命/行年，年命类课体用）；
    nianzhu2/xingbie2 为配偶（繁昌课用，可选）。
    """
    day_gz = day_gz_rolled(dt)
    if shi_zhi is None:
        shi_zhi = ZHI[((dt.hour + 1) // 2) % 12]
    yj = yue_jiang_at(dt)
    nm = nm2 = None
    liunian_gz = ""
    if nianzhu or nianzhu2:
        try:
            from lunar_python import Solar
            liunian_gz = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0) \
                .getLunar().getEightChar().getYear()
        except Exception:
            liunian_gz = ""
    if nianzhu and liunian_gz:
        nm = _nianming(nianzhu, xingbie, liunian_gz) if xingbie in ("男", "女") \
            else {"本命": nianzhu[1], "行年": None, "行年干支": "", "虚岁": 0, "性别": ""}
    if nianzhu2 and liunian_gz:
        nm2 = _nianming(nianzhu2, xingbie2, liunian_gz) if xingbie2 in ("男", "女") \
            else {"本命": nianzhu2[1], "行年": None, "行年干支": "", "虚岁": 0, "性别": ""}
    out = qike_core(day_gz, shi_zhi, yj, dt=dt, nianming=nm, nianming2=nm2)
    if nm:
        out["年命"] = {"本命": nm["本命"], "行年": nm["行年"],
                      "行年干支": nm.get("行年干支") or "", "虚岁": nm["虚岁"]}
    if nm2:
        out["配偶年命"] = {"本命": nm2["本命"], "行年": nm2["行年"],
                          "行年干支": nm2.get("行年干支") or "", "虚岁": nm2["虚岁"]}
    out["时刻"] = dt.strftime("%Y-%m-%d %H:%M:%S")
    return out


# ---------------- 课体判语与附加课体（课经六十四课体） ----------------
# 九宗门课体判语逐字转录自课经（六壬大全）；附加课体第一批为盘面数据可机械判定者，
# 依赖旺衰/年命/吉将分类/月宿者（三光、三阳、三阴、时泰、龙德、富贵、繁昌、荣华、
# 德庆、合欢、刑伤、二烦、天寇、物类）登记待补（判据总表第六节）。

KETI_JUYU = {
    "元首": "统乾之本，乃元吉第一课也。君占则有伊尹之臣，臣占必遇唐虞之君；常人占之，万事顺利。",
    "重审": "统坤之体。积善者庆，积不善者殃；君子占之，利有攸往。",
    "知一": "统比之体，乃去谗任贤之课也。事宜惟一，允执厥中；占物占人，皆在近也。",
    "涉害·见机": "统坎之体，乃苦尽甘来之象。凡事艰难，必有稽迟，然历尽风霜而后得。",
    "涉害·察微": "统坎之体，乃苦尽甘来之象。察微者涉害俱深无孟取仲，当思虑提防。",
    "涉害·缀瑕": "统坎之体，乃苦尽甘来之象。缀瑕者涉害复等取先见之神，占事艰难，首尾牵连。",
    "蒿矢": "统睽之体，乃狐假虎威之课也。占事始而雷吼惊恐，终却无妨。",
    "弹射": "占者事远难就，纵成虚名虚得，不得实用。",
    "昴星·虎视转篷": "统履之体，乃蛇虎当道之象。占事惊恐，守静则吉。",
    "昴星·冬蛇掩目": "占者事多暗昧，犹豫难行，惟欲潜藏者吉也。",
    "别责": "凡事不备，主有留连之体。谋为处正，财物不全；凡事倚仗他人，借径而行。",
    "八专": "统同人之体，乃诸侯会盟之课也。占理家务，重轻易举，不利奔波于外。",
    "独足": "三传皆归一神，如驿递无人传送，独足难行，凡事不能动移，诸皆费力。",
    "伏吟": "统艮之体，守旧待新之课也。天地神自居本家，日辰阴阳伏而不动。",
    "自任": "占者自强出头，此当闭塞，为柔顺吉而事可成。",
    "自信": "凡事不能动身，家宅不宁之体也。",
    "杜传": "占事中止，改求则可成也。",
    "返吟·无依": "统震之体，重重震惊之课也。来者思去，离者思归，得失未可一定，唯有利复旧事。",
    "返吟·井栏": "占者无事依倚，一身两用之体；井上架木，易欹易斜，不能长久。",
}

SANHE = {"申子辰": "润下", "寅午戌": "炎上", "亥卯未": "曲直", "巳酉丑": "从革"}
JI_JIANG = {"贵人", "六合", "青龙", "太常", "太阴", "天后"}
XIONG_JIANG = {"螣蛇", "朱雀", "勾陈", "天空", "白虎", "玄武"}
RIQI = {"甲": "午", "丙": "辰", "乙": "巳", "丁": "卯", "戊": "寅",
        "己": "丑", "庚": "未", "辛": "申", "壬": "酉", "癸": "戌"}
JIUCHOU_RI = {"戊子", "戊午", "壬子", "壬午", "乙卯", "乙酉", "己卯", "己酉", "辛卯", "辛酉"}

# 十干禄（课经荣华课用）
GAN_LU = {"甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳",
          "己": "午", "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}
# 干德（课经德庆课 L7486：甲己德寅、乙庚申，丙辛、戊癸在巳轮，丁壬亥位）
GAN_DE = {"甲": "寅", "己": "寅", "乙": "申", "庚": "申", "丙": "巳", "辛": "巳",
          "丁": "亥", "壬": "亥", "戊": "巳", "癸": "巳"}
# 支六合（课经合欢课 L7516：子合丑……）
LIUHE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯",
         "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}
# 支德（课经德庆课 L7486：子日起巳顺行十二辰＝支+5）
ZHI_DE = {z: ZHI[(ZHI.index(z) + 5) % 12] for z in ZHI}
# 天德（课经德庆课 L7486 歌：正丁二坤三壬四辛同，五乾六甲上，七癸八艮逢，九丙十居乙，
# 子巽丑庚中；干取寄宫、卦位取坤申乾亥艮寅巽巳；月序以月建寅=1）
TIANDE = {1: "未", 2: "申", 3: "亥", 4: "戌", 5: "亥", 6: "寅",
          7: "丑", 8: "寅", 9: "巳", 10: "辰", 11: "巳", 12: "申"}
# 月德（课经德庆课 L7486：正五九月丙、二六十月甲、三七十一壬、四八十二庚；干取寄宫）
YUEDE = {1: "巳", 5: "巳", 9: "巳", 2: "寅", 6: "寅", 10: "寅",
         3: "亥", 7: "亥", 11: "亥", 4: "申", 8: "申", 12: "申"}


def _nianming(nian_gz: str, xingbie: str, liunian_gz: str) -> dict:
    """本命＝出生年之太岁（出生年支）；行年＝男1岁起丙寅顺数、女1岁起壬申逆数
    （大全教程 L14078–14088；虚岁＝流年太岁序−出生年太岁序+1）。

    教程例：20岁男行年乙酉（丙寅顺数19步）✓；20岁女例记「己丑」，按规则应为癸丑，
    例与规则不符处采规则（登记判据总表）。
    """
    ben = nian_gz[1]
    sui = (GZ_INDEX[liunian_gz] - GZ_INDEX[nian_gz]) % 60 + 1
    if xingbie == "男":
        g = GAN[(GAN.index("丙") + sui - 1) % 10]
        z = ZHI[(ZHI.index("寅") + sui - 1) % 12]
    else:
        g = GAN[(GAN.index("壬") - (sui - 1)) % 10]
        z = ZHI[(ZHI.index("申") - (sui - 1)) % 12]
    return {"本命": ben, "行年": z, "行年干支": g + z, "虚岁": sui, "性别": xingbie}


# ---------------- 月宿推步（二烦课条 L9024/L9086/L9126–9136；天寇课条 L9374 同源） ----------------
XIU = "角亢氐房心尾箕斗牛女虚危室壁奎娄胃昴毕觜参井鬼柳星张翼轸"
# 月宿所属十二辰（课经 L9136：辰角亢、卯氐房心、寅尾箕、丑斗牛、子女虚危、亥室壁、
# 戌奎娄、酉胃昴毕、申觜参、未井鬼、午柳星张、巳翼轸；L9442 心月狐在卯、危月燕在子、
# 张月鹿在午、毕月鸟在酉可作锚点核对）
XIU_GONG = {"辰": "角亢", "卯": "氐房心", "寅": "尾箕", "丑": "斗牛", "子": "女虚危",
            "亥": "室壁", "戌": "奎娄", "酉": "胃昴毕", "申": "觜参", "未": "井鬼",
            "午": "柳星张", "巳": "翼轸"}
XIU_TO_GONG = {x: g for g, xs in XIU_GONG.items() for x in xs}
# 重留宿（L9024/L9132：遇奎、张、井、翼、氐、斗重留一日）
LIU_XIU = "奎张井翼氐斗"
# 每月初一起宿（L9130 歌：正室二奎三在胃，四毕五参六鬼期，七张八角九月氐，十心一斗十二虚。
# 十月采「心」——歌诀与订讹 L9086 一致，正文 L9024 作「尾」，登记判据总表）
YUE_SU_QI = {1: "室", 2: "奎", 3: "胃", 4: "毕", 5: "参", 6: "鬼",
             7: "张", 8: "角", 9: "氐", 10: "心", 11: "斗", 12: "虚"}


def yue_su(dt) -> dict:
    """月宿推步：农历每月初一移一宿，逐日数二十八宿，遇重留宿占两日，宿名→宫依
    「月宿所属十二辰」表。闰月依本月之序（书无直文，🧩类比外推）。"""
    from lunar_python import Solar
    ln = Solar.fromYmdHms(dt.year, dt.month, dt.day, 12, 0, 0).getLunar()
    yue = abs(ln.getMonth())
    ri = ln.getDay()
    idx = XIU.index(YUE_SU_QI[yue])
    span = 2 if XIU[idx] in LIU_XIU else 1
    for _ in range(2, ri + 1):
        span -= 1
        if span == 0:
            idx = (idx + 1) % 28
            span = 2 if XIU[idx] in LIU_XIU else 1
    xiu = XIU[idx]
    return {"宿": xiu, "宫": XIU_TO_GONG[xiu], "农历月": yue, "农历日": ri}


def fujia_keti(day_gan: str, day_zhi: str, tp: dict, chuan: list,
               shi_zhi: str, tianj: dict, dt=None, yue_jiang: str = "",
               nianming: dict | None = None, nianming2: dict | None = None) -> list:
    """附加课体（盘面数据、月令旺衰、年命可判定者）。返回 [{课体, 判语}]。

    吉将＝天乙、青龙、六合、太常、太阴、天后；凶将＝螣蛇、朱雀、勾陈、天空、白虎、玄武
    （大全「乙合龙常为用吉」、L7580「乘天乙青龙阴合吉将」；断案疏正「六凶神…六吉将」）。
    nianming/nianming2 为 _nianming 的返回值（本命/行年/行年干支/性别），供三阴、富贵、
    繁昌、荣华、德庆、合欢、刑伤七课使用。
    """
    out = []
    inv = {v: k for k, v in tp.items()}
    chu, zhong, mo = chuan
    day_gz = day_gan + day_zhi
    # 全局课（三传三合）
    for ju, ming in SANHE.items():
        if set(chuan) <= set(ju):
            zhu = {"润下": "主沟渠鱼网等事，占天阴雨；值旺相老凶少吉",
                   "炎上": "主炉冶文书等事，占天晴旱；囚死者少凶老吉",
                   "曲直": "主船车种植，利修造",
                   "从革": "主兵戈金铁，利更改"}[ming]
            out.append({"课体": "全局·" + ming, "判语": f"三传{ju}局，{zhu}。统大畜之体，乃同类欢会之课。"})
            break
    # 连珠课（三传连茹）
    idxs = sorted(ZHI.index(z) for z in chuan)
    if (idxs[1] - idxs[0]) % 12 == 1 and (idxs[2] - idxs[1]) % 12 == 1:
        out.append({"课体": "连珠", "判语": "三传孟仲季相连若贯珠。吉事连珠可爱，凶似连茹可恶。统复之体，乃山外青山之课。"})
    elif (idxs[0] - idxs[1]) % 12 == 1 and (idxs[1] - idxs[2]) % 12 == 1:
        out.append({"课体": "连珠", "判语": "三传孟仲季相连若贯珠（退连茹）。吉事连珠可爱，凶似连茹可恶。"})
    # 间传课（三传隔一位）
    if (idxs[1] - idxs[0]) % 12 == 2 and (idxs[2] - idxs[1]) % 12 == 2:
        out.append({"课体": "间传", "判语": "间一位递作三传。顺主事顺，逆主事逆。统巽之体，乃阴阳升降之课。"})
    # 三奇课（旬奇/日奇发用或入传）
    xun_zhi = GZ60[GZ_INDEX[day_gz] - GZ_INDEX[day_gz] % 10][1]
    xun_qi = {"子": "丑", "戌": "丑", "申": "子", "午": "子", "辰": "亥", "寅": "亥"}[xun_zhi]
    if xun_qi in chuan or RIQI[day_gan] in chuan:
        out.append({"课体": "三奇", "判语": "旬日之奇发用或入传。占者百祸消散，凡事吉利。统豫之体，乃上下悦怿之课。"})
    # 六仪课（旬首之仪发用或入传）
    if xun_zhi in chuan:
        out.append({"课体": "六仪", "判语": "旬首之仪发用或入传。占者凡事吉庆，家集千祥。统兑之体，乃喜气溢眉之课。"})
    # 铸印课（戌加巳中传）
    if zhong == "戌" and inv["戌"] == "巳":
        out.append({"课体": "铸印", "判语": "戌为印，巳为炉，全凭火炼铸成贵器。占者符命入手，官增权柄。统鼎之体，乃炼药成丹之课。"})
    # 斫轮课（卯加庚或辛为用）
    if chu == "卯" and inv["卯"] in ("申", "戌"):
        out.append({"课体": "斫轮", "判语": "卯为车轮，庚辛为刀斧，木就金斫。占者官禄位高迁。统颐之体，乃革故鼎新之课。"})
    # 轩盖课（胜光为用，遇太冲、神后）
    if chu == "午" and "卯" in chuan and "子" in chuan:
        out.append({"课体": "轩盖", "判语": "子为华盖，卯为天车，午为天马，三神并遇。占者加官荣显，凡事吉庆。统升之体，乃士子发达之课。"})
    # 亨通课（用神生日，或三传递生日干）
    if (SHENG[ZHI_WX[chu]] == GAN_WX[day_gan]
            or (SHENG[ZHI_WX[chu]] == ZHI_WX[zhong] and SHENG[ZHI_WX[zhong]] == ZHI_WX[mo]
                and SHENG[ZHI_WX[mo]] == GAN_WX[day_gan])):
        out.append({"课体": "亨通", "判语": "用神生日，或三传递生日干。主人亨利，时运开通。统渐之体，乃福禄来临之课。"})
    # 引从课（初传居日干前、末传居日干后，或拱支）
    ji = JIGONG[day_gan]
    def wei(p, base):
        return (ZHI.index(p) - ZHI.index(base)) % 12
    if (1 <= wei(inv[chu], ji) <= 6 and 7 <= wei(inv[mo], ji) <= 11) or \
       (1 <= wei(inv[chu], day_zhi) <= 6 and 7 <= wei(inv[mo], day_zhi) <= 11):
        out.append({"课体": "引从", "判语": "日辰干支前后上神发用为初末传。主官职升擢，诸事最吉。统涣之体，乃车马蜂拥之课。"})
    # 度厄课（三上克下或三下贼上）与无禄课（四上俱克下）
    ke = _ke_pairs(day_gan, day_zhi, tp)
    n_sk = sum(1 for c in ke if c[3] == "上克下")
    n_z = sum(1 for c in ke if c[3] == "下贼上")
    if n_sk == 3 or n_z == 3:
        out.append({"课体": "度厄", "判语": "三上克下则长欺幼，三下贼上则幼凌长。占者家宅欠利，老幼见灾。统剥之体，乃六亲冰炭之课。"})
    if n_sk == 4:
        out.append({"课体": "无禄", "判语": "四上俱克下。庶人不禄，有官罚职；对敌利客，讼宜先起者胜。统否之体，乃上下僭乱之课。"})
    # 淫泆课（初传卯酉为用，将乘后合）
    if chu in ("卯", "酉") and tianj.get(chu) in ("天后", "六合"):
        out.append({"课体": "淫泆", "判语": "卯酉为阴私之门，后合乃淫欲之神。利私谋而不利公谋。统既济之体，乃阴阳配合之课。"})
    # 龙战课（卯酉日占，卯酉为用）
    if day_zhi in ("卯", "酉") and chu == day_zhi:
        out.append({"课体": "龙战", "判语": "阴阳出入之位，刑德聚会之门。主占事疑惑，反复不定。统离之体，乃门户不宁之课。"})
    # 九丑课（十日四仲时占，丑临日加四仲上发用）
    if day_gz in JIUCHOU_RI and shi_zhi in "子午卯酉" and chu == "丑" and inv["丑"] in "子午卯酉":
        out.append({"课体": "九丑", "判语": "五干四平合而为九丑，三光不照。占事多凶。统小过之体，乃上下迍邅之课。"})
    # 励德课（天乙立卯酉）
    zhou = shi_zhi in "卯辰巳午未申"
    gui = GUIREN[day_gan][0 if zhou else 1]
    if inv.get(gui) in ("卯", "酉"):
        out.append({"课体": "励德", "判语": "卯酉为阴阳交易之位，贵人由之而迁易。占利君子不利小人。统随之体，乃反复不定之课。"})
    # 盘珠课（太岁、月建及日、时并三传皆在四课之中）
    if dt is not None:
        try:
            from lunar_python import Solar
            ec = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0).getLunar().getEightChar()
            sui_zhi, jian_zhi = ec.getYear()[1], ec.getMonth()[1]
            sike = {tp[JIGONG[day_gan]], tp[tp[JIGONG[day_gan]]], tp[day_zhi], tp[tp[day_zhi]]}
            if all(z in sike for z in chuan) and all(tp.get(z) in sike for z in (sui_zhi, jian_zhi, day_zhi, shi_zhi)):
                out.append({"课体": "盘珠", "判语": "岁月日时皆在四课之上。主事远大非常，干朝廷可以成就。统大壮之体，乃凤翔丹山之课。"})
        except Exception:
            pass
    # 旺衰类课体（课经；月令五态用 wuxing_quality.month_state）
    if dt is not None:
        try:
            from lunar_python import Solar
            from wuxing_quality import month_state
            ec = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0).getLunar().getEightChar()
            sui_zhi, jian_zhi = ec.getYear()[1], ec.getMonth()[1]
            month_wx = ZHI_WX[jian_zhi]

            def wang(z):
                return month_state(ZHI_WX[z], month_wx).get("state") in ("旺", "相")

            def wang_gan(g):
                return month_state(GAN_WX[g], month_wx).get("state") in ("旺", "相")
            sk = tp[JIGONG[day_gan]]
            zs = tp[day_zhi]
            # 三光：用神、日辰旺相，吉神在中（课经 L6526）
            if (wang(chu) and wang_gan(day_gan) and wang(day_zhi)
                    and tianj.get(chu) in JI_JIANG and tianj.get(sk) in JI_JIANG and tianj.get(zs) in JI_JIANG):
                out.append({"课体": "三光", "判语": "用神、日辰旺相，吉神在中。占者万事任其所为，皆无费力而成，且有吉利。统贲之体，乃光明通达之课。"})
            # 三阳：天乙顺行，日辰有气居前，旺相气发用（课经 L6624；订讹 L6652「用神旺相」）。
            # 「旺相气发用」按课经例 L6628「乙丑日…寅为旺气加丑发用」——寅为乙之帝旺，
            # 月令旺相判不出该例（戌月寅木囚），故用神旺相＝月令旺相或日干之帝旺。
            # 「日辰居前」按两书例校准为天盘落宫口径：日干寄宫与日支的天盘落宫（inv）顺数
            # 1–6 位＝前（三阳例 L6628）、7–11 位＝后（三阴例 L9640 同口径反向）。
            GAN_DIWANG = {"甲": "卯", "乙": "寅", "丙": "午", "丁": "巳", "戊": "午",
                          "己": "巳", "庚": "酉", "辛": "申", "壬": "子", "癸": "亥"}
            zhou = shi_zhi in "卯辰巳午未申"
            gui = GUIREN[day_gan][0 if zhou else 1]
            gui_gong = inv.get(gui)
            if (gui_gong and gui_gong in SHUN_GONG
                    and (wang(chu) or chu == GAN_DIWANG[day_gan])
                    and (ZHI.index(inv[JIGONG[day_gan]]) - ZHI.index(gui_gong)) % 12 in range(1, 7)
                    and (ZHI.index(inv[day_zhi]) - ZHI.index(gui_gong)) % 12 in range(1, 7)):
                out.append({"课体": "三阳", "判语": "天乙顺行，日辰有气居前，旺相气发用。占者凡事吉庆，所求皆遂。统晋之体，乃龙剑呈祥之课。"})
            # 时泰：用起太岁、月建，乘青龙、六合，又带财德之神（课经 L6852）
            if (chu in (sui_zhi, jian_zhi) and tianj.get(chu) in ("青龙", "六合")
                    and (ZHI_WX[chu] == KE[GAN_WX[day_gan]] or chu == GAN_DE[day_gan])):
                out.append({"课体": "时泰", "判语": "用起太岁、月建，乘青龙、六合，又带财德之神。占者万事亨利。统泰之体，乃天地和畅之课。"})
            # 龙德：太岁、月将乘贵人发用（课经 L6890）
            if tianj.get(chu) == "贵人" and (chu == sui_zhi or chu == yue_jiang):
                out.append({"课体": "龙德", "判语": "太岁、月将乘贵人发用，如龙行雨泽，德及万物。占者主天子恩泽，福神相助。统萃之体，乃云龙际会之课。"})
            # 二烦（课经 L9022–9176）与天寇（课经 L9374–9414）：月宿推步见 yue_su。
            # 日宿＝太阳躔度宫神＝月将；月宿＝太阴躔度宫神（二十八宿值日）；斗罡＝辰。
            try:
                ys = yue_su(dt)
                ms = ys["宫"]
                rm, ry, gang = inv.get(ms), inv.get(yue_jiang), inv.get("辰")
                zhong = "子午卯酉"
                if (ry in zhong or rm in zhong) and gang is not None:
                    if gang in ("丑", "未"):
                        if ry in zhong and rm in zhong:
                            note = "" if chu in (yue_jiang, ms) else "（日月宿未发用，不真）"
                            out.append({"课体": "二烦", "判语": "四仲月将遇四正及四平日占，日月宿俱加四仲，斗罡系丑未，为二烦课。" + note + "占者家有灾祸。统明夷之体，乃荆棘满途之课也。"})
                        elif ry in zhong:
                            note = "" if chu == yue_jiang else "（日宿未发用，不真）"
                            out.append({"课体": "天烦", "判语": "日宿（太阳躔度＝月将）临四仲，斗罡系丑未，为天烦格。" + note + "主男子犯法。"})
                        elif rm in zhong:
                            note = "" if chu == ms else "（月宿未发用，不真）"
                            out.append({"课体": "地烦", "判语": "月宿（太阴躔度）临四仲，斗罡系丑未，为地烦格。" + note + "主女子受灾。"})
                    else:
                        out.append({"课体": "杜传（二烦）", "判语": "日月宿临四仲而斗罡不系丑未，名杜传，四位俱闭，利于居家，不可远行。"})
                # 天寇：二分二至日及前一日（四离日）占，月宿加离辰（分至日支前一辰）
                from qimen import _jieqi_timeline
                from datetime import timedelta
                for nm, t in _jieqi_timeline(dt.year):
                    if nm in ("春分", "秋分", "夏至", "冬至"):
                        lich = ZHI[(ZHI.index(day_gz_rolled(t)[1]) - 1) % 12]
                        if (t - timedelta(days=1)).date() <= dt.date() <= t.date() \
                                and inv.get(ms) == lich:
                            out.append({"课体": "天寇", "判语": "四离日占，月宿加离辰，为天寇课。占事破坏，多值乱离。统蹇之体，乃时势多艰之课也。"})
            except Exception:
                pass
            # ---- 年命类课体（课经；需本命/行年） ----
            if nianming and nianming.get("行年"):
                ben, xn = nianming["本命"], nianming["行年"]
                ben_s, xn_s = tp.get(ben), tp.get(xn)
                # 三阴（课经 L9636）：天乙逆行、日辰在天乙后（天盘落宫顺距离7..11）、
                # 用神囚死、将乘玄武白虎、时克行年。书例：正月癸丑日卯时子将，申命行年丑。
                if (gui_gong and gui_gong not in SHUN_GONG
                        and (ZHI.index(inv[JIGONG[day_gan]]) - ZHI.index(gui_gong)) % 12 in range(7, 12)
                        and (ZHI.index(inv[day_zhi]) - ZHI.index(gui_gong)) % 12 in range(7, 12)
                        and month_state(ZHI_WX[chu], month_wx).get("state") in ("囚", "死")
                        and tianj.get(chu) in ("玄武", "白虎")
                        and KE[ZHI_WX[shi_zhi]] == ZHI_WX[xn]):
                    out.append({"课体": "三阴", "判语": "天乙逆行，日辰在后，用其囚死，将乘元虎，时克行年。占者凡事不能，多有晦滞。统中孚之体，乃群阴当恶之课。"})
                # 富贵（课经 L7016）：天乙乘旺相气、上下相生、临日辰年命发用。
                # 书例：二月辛巳日丑时戌将，寅命行年巳，寅为天乙临行年、木火相生发用。
                if (chu == gui and wang(gui)
                        and gui_gong in (JIGONG[day_gan], day_zhi, ben, xn)
                        and (SHENG[ZHI_WX[gui]] == ZHI_WX[gui_gong]
                             or SHENG[ZHI_WX[gui_gong]] == ZHI_WX[gui])):
                    out.append({"课体": "富贵", "判语": "天乙乘旺相气，上下相生，临日辰年命发用。占者家道荣昌，官职显耀，统大有之体，乃金玉满堂之课也。"})
                # 荣华（课经 L7432）：禄马贵人临干支年命并旺相气发用入传，更乘吉将。
                # 书例：丙申日卯时子将，干上寅马、支上巳禄、本命寅上亥贵、行年巳上寅马。
                jims = {GAN_LU[day_gan], MA[day_zhi], gui}
                lins = [s for s in (sk, zs, ben_s, xn_s) if s in jims]
                if (chu in jims and wang(chu) and lins
                        and any(tianj.get(s) in JI_JIANG for s in lins)):
                    out.append({"课体": "荣华", "判语": "禄马贵人临干支年命并旺相气发用入传，更乘吉将。主君子加官进禄，常人谋为财利，统师之体，乃士众拥从之课也。"})
                # 德庆（课经 L7486）：日辰干支德神及天月二德发用，并在年命乘吉将。
                yue_xu = (ZHI.index(jian_zhi) - ZHI.index("寅")) % 12 + 1
                de_set = {GAN_DE[day_gan], ZHI_DE[day_zhi], TIANDE[yue_xu], YUEDE[yue_xu]}
                if (chu in de_set
                        and ((ben_s in de_set and tianj.get(ben_s) in JI_JIANG)
                             or (xn_s in de_set and tianj.get(xn_s) in JI_JIANG))):
                    out.append({"课体": "德庆", "判语": "日辰干支德神，及天月二德发用，并在年命乘吉将。凡占谋望，事事吉昌，统需之体，乃君子欢会之课也。"})
                # 合欢（课经 L7516）：日辰遇天干作合，及支三合六合发用，并占人年命俱乘吉将。
                # 书例：戊申日子时申将，干上丑遁癸与戊作合，支与三传申子辰三合，亥命上未乘贵、
                # 行年辰上子乘青龙。
                sk_dun = dunkun_gz(day_gz, [sk])[0]
                sanhe_ok = any(set(chuan) | {day_zhi} <= set(j) for j in SANHE)
                if (sk_dun == GAN_HE.get(day_gan)
                        and (sanhe_ok or LIUHE.get(chu) in (day_zhi, sk))
                        and ben_s is not None and xn_s is not None
                        and tianj.get(ben_s) in JI_JIANG and tianj.get(xn_s) in JI_JIANG):
                    out.append({"课体": "合欢", "判语": "日辰遇天干作合，及支三合六合发用，并占人年命俱乘吉将。主和合，人欢事成，统井之体，乃婚姻团圆之课也。"})
                # 刑伤（课经 L8968）：三刑发用，并行年。书例：庚午日寅时子将，午为支刑临日用。
                if ((XING.get(chu) == day_zhi or XING.get(day_zhi) == chu)
                        and (xn == chu or xn_s == chu)):
                    out.append({"课体": "刑伤", "判语": "三刑发用，并行年。主伤残、人情不和，统讼之体，乃大小不和之课也。"})
        except Exception:
            pass
    # 繁昌（课经 L7322；需夫妻二人年命，无需月令）：行年干支干合＋支六合，
    # 各行年上神乘本命五行（乘本命旺气）且生行年，行年入传。
    # 书例：壬申日未时巳将，夫行年甲寅、妻行年己亥，夫命水上见子、妻命金上见酉。
    if (nianming and nianming2 and nianming.get("性别") and nianming2.get("性别")
            and nianming["性别"] != nianming2["性别"]):
        fu, qi = (nianming, nianming2) if nianming["性别"] == "男" else (nianming2, nianming)
        fu_gz, qi_gz = fu.get("行年干支"), qi.get("行年干支")
        if (fu_gz and qi_gz and GAN_HE.get(fu_gz[0]) == qi_gz[0]
                and LIUHE.get(fu_gz[1]) == qi_gz[1]
                and (fu["行年"] in chuan or qi["行年"] in chuan)):
            ok = True
            for p in (fu, qi):
                s = tp.get(p["行年"])
                if (s is None or ZHI_WX[s] != ZHI_WX[p["本命"]]
                        or SHENG[ZHI_WX[s]] != ZHI_WX[p["行年"]]):
                    ok = False
            if ok:
                out.append({"课体": "繁昌", "判语": "夫妻年立德方发用，行年乘本命旺气，干支德合。占者人丁旺相，胎孕招贵，统咸之体，乃男女交感之课也。"})
    return out


# ---------------- 毕法赋一百法（机械可判定子集） ----------------
# 书证：《六壬大全》第十一卷《毕法赋》上、第十二卷《毕法赋》下（L11019–12140）。
# 只收盘面结构（天地盘/四课/三传/天将/遁干/空亡/月令/年命）可机械判定者；
# 避难逃生（第九）、苦去甘来（第三四）、后合占婚行年互居（第四十）、费有余（第五七）、
# 用破（第五八）、前后逼迫（第七三）、妄用三传勘误（第九三）、喜惧空亡（第九四）、
# 六爻现卦（第九五）、旬内空亡逐类推（第九六）、所筮不入仍凭类（第九七）、
# 非占现类勿言之（第九八）、常问不应逢吉象（第九九）、已灾凶逃返无疑（第一百）
# 属案例式活断或类象断法，登记待补不代拟。

# 十干十二长生宫序（长生沐浴冠带临官帝旺衰病死墓绝胎养）
GAN_CS = {
    "甲": "亥子丑寅卯辰巳午未申酉戌",
    "乙": "午巳辰卯寅丑子亥戌酉申未",
    "丙": "寅卯辰巳午未申酉戌亥子丑",
    "丁": "酉申未午巳辰卯寅丑子亥戌",
    "戊": "寅卯辰巳午未申酉戌亥子丑",
    "己": "酉申未午巳辰卯寅丑子亥戌",
    "庚": "巳午未申酉戌亥子丑寅卯辰",
    "辛": "子亥戌酉申未午巳辰卯寅丑",
    "壬": "申酉戌亥子丑寅卯辰巳午未",
    "癸": "卯寅丑子亥戌酉申未午巳辰",
}
# 支十二长生宫序（按五行；土从水——死卯、墓辰与书例合；土之绝依寄干：辰亥、戌寅、丑巳、未亥，法79原文）
ZHI_CS = {"木": "亥子丑寅卯辰巳午未申酉戌",
          "火": "寅卯辰巳午未申酉戌亥子丑",
          "金": "巳午未申酉戌亥子丑寅卯辰",
          "水": "申酉戌亥子丑寅卯辰巳午未"}
TU_CS = "申酉戌亥子丑寅卯辰巳午未"  # 土同水
ZHI_JU_TU = {"辰": "亥", "戌": "寅", "丑": "巳", "未": "亥"}  # 土支之绝＝寄干之绝（法79「土内有寄寅者，故以亥为绝也」）
LIUHAI = {"子": "未", "未": "子", "丑": "午", "午": "丑", "寅": "巳", "巳": "寅",
          "卯": "辰", "辰": "卯", "申": "亥", "亥": "申", "酉": "戌", "戌": "酉"}
JIANG_WX = {"贵人": "土", "螣蛇": "火", "朱雀": "火", "六合": "木", "勾陈": "土",
            "青龙": "木", "天空": "土", "白虎": "金", "太常": "土", "玄武": "水",
            "太阴": "金", "天后": "水"}
BIFA_MU_WX = {"木": "未", "火": "戌", "金": "丑", "水": "辰", "土": "辰"}


def _zhi_state(z: str, idx: int) -> str:
    """支之十二宫第 idx 位（土同水）。"""
    return (ZHI_CS[ZHI_WX[z]] if ZHI_WX[z] != "土" else TU_CS)[idx]


def bifa(day_gan: str, day_zhi: str, tp: dict, chuan: list, shi_zhi: str,
         tianj: dict, keti: str, dt=None, yue_jiang: str = "",
         nianming: dict | None = None, nianming2: dict | None = None) -> list:
    """毕法赋一百法机械子集。返回 [{法, 名, 判语}]，只标盘面结构事实，不代断。"""
    out = []
    inv = {v: k for k, v in tp.items()}
    day_gz = day_gan + day_zhi
    chu, zhong, mo = chuan
    sk = tp[JIGONG[day_gan]]
    zs = tp[day_zhi]
    sy = tp[sk]
    zy = tp[zs]
    dun = dunkun_gz(day_gz, chuan)
    dun_sk = dunkun_gz(day_gz, [sk])[0]
    kong = set(xunkong(day_gz))
    xun_zhi = GZ60[GZ_INDEX[day_gz] - GZ_INDEX[day_gz] % 10][1]
    ding = ZHI[(ZHI.index(xun_zhi) + 3) % 12]  # 旬内六丁之神（法25/26/89）
    zhou = shi_zhi in "卯辰巳午未申"
    gui = GUIREN[day_gan][0 if zhou else 1]
    gui2 = GUIREN[day_gan][1 if zhou else 0]
    sui = jian = jian_wx = None
    if dt is not None:
        try:
            from lunar_python import Solar
            from wuxing_quality import month_state
            ec = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0).getLunar().getEightChar()
            sui, jian = ec.getYear()[1], ec.getMonth()[1]
            jian_wx = ZHI_WX[jian]
        except Exception:
            pass
    liuchu = {chu, zhong, mo, sk, zs}
    if nianming:
        liuchu.add(nianming["本命"])
        if nianming.get("行年"):
            liuchu.add(nianming["行年"])

    def wang(z):
        if dt is None:
            return False
        from wuxing_quality import month_state
        return month_state(ZHI_WX[z], jian_wx).get("state") in ("旺", "相")

    def add(fa, ming, yu):
        out.append({"法": fa, "名": ming, "判语": yu})

    # 一、前后引从升迁吉（引从课已列附加课体，此处同格重出）
    if (1 <= (ZHI.index(inv[chu]) - ZHI.index(JIGONG[day_gan])) % 12 <= 6
            and 7 <= (ZHI.index(inv[mo]) - ZHI.index(JIGONG[day_gan])) % 12 <= 11):
        add("第一法", "前后引从升迁吉", "初传居干前为引、末传居干后为从，宜升擢官职（引干）；拱支则宜迁修家宅。")
    # 二、首尾相见始终宜（干上旬尾支上旬首，或反之）
    xun_wei = ZHI[(ZHI.index(xun_zhi) - 3) % 12]
    if (sk == xun_wei and zs == xun_zhi) or (sk == xun_zhi and zs == xun_wei):
        add("第二法", "首尾相见始终宜", "干上有旬尾、支上有旬首（或反之），名周而复始格，占事不脱，所谋皆成。")
    # 三、帘幕贵人高甲第（昼占夜贵/夜占昼贵临干上）
    if sk == gui2 and tianj.get(sk) == "贵人":
        add("第三法", "帘幕贵人高甲第", "帘幕官（昼占夜贵、夜占昼贵）临日干上，占试高中之象（临年命尤的）。")
    # 四、催官使者赴官期（日鬼乘白虎临干上）
    if KE[ZHI_WX[sk]] == GAN_WX[day_gan] and tianj.get(sk) == "白虎":
        add("第四法", "催官使者赴官期", "日鬼乘白虎临日干上，名催官使者，占赴任必催速（空亡则虚信）。")
    # 五、六阳数足须公用
    if all(z in "子寅辰午申戌" for z in (sk, sy, zs, zy, chu, zhong, mo)):
        add("第五法", "六阳数足须公用", "四课三传皆居六阳之位，凡占利公干而不利私谋。")
    # 六、六阴相继尽昏迷
    if all(z in "丑卯巳未酉亥" for z in (sk, sy, zs, zy, chu, zhong, mo)):
        add("第六法", "六阴相继尽昏迷", "四课三传皆居六阴之位，凡占利阴谋私干，不利公闻。")
    # 七、旺禄临身徒妄作
    if sk == GAN_LU[day_gan]:
        add("第七法", "旺禄临身徒妄作", "日之禄神临于干上，切不可舍此而别谋动作；禄值旬空则反不宜坐用。")
    # 八、权摄不正禄临支
    if zs == GAN_LU[day_gan]:
        add("第八法", "权摄不正禄临支", "日干禄神临支辰上，凡占不自尊大，受屈折于他人，主差遣权摄不正。")
    # 十、朽木难雕别作为（斫轮课而卯空亡）
    if chu == "卯" and inv["卯"] in ("申", "戌") and chu in kong:
        add("第十法", "朽木难雕别作为", "斫轮课中卯为空亡，名朽木不可雕，宜改科易业而别作营生。")
    # 十一、众鬼虽彰全不畏（三传皆鬼而干上神制鬼）
    if (all(KE[ZHI_WX[z]] == GAN_WX[day_gan] for z in chuan)
            and (KE[ZHI_WX[sk]] == ZHI_WX[chu] or SHENG[ZHI_WX[sk]] == GAN_WX[day_gan])):
        add("第十一法", "众鬼虽彰全不畏", "三传皆日鬼，而干上神能制鬼（或生日干），有救神，鬼不能为祸。")
    # 十二、虽忧狐假虎威仪（干上神克干，而日支制之）
    if KE[ZHI_WX[sk]] == GAN_WX[day_gan] and KE[ZHI_WX[day_zhi]] == ZHI_WX[sk]:
        add("第十二法", "虽忧狐假虎威仪", "干上神克日干，赖日支制其鬼，仗他人之力，凡占切不可动谋。")
    # 十三、鬼贼当时无畏忌（三传皆鬼且月令旺相）
    if dt is not None and all(KE[ZHI_WX[z]] == GAN_WX[day_gan] for z in chuan) and wang(chu):
        add("第十三法", "鬼贼当时无畏忌", "三传皆日鬼而当令旺相，鬼贪荣盛无意克我，暂无畏（防其衰时仍发）。")
    # 十四、传财太旺反财亏（三传皆财且月令旺相）
    if dt is not None and all(ZHI_WX[z] == KE[GAN_WX[day_gan]] for z in chuan) and wang(chu):
        add("第十四法", "传财太旺反财亏", "三传皆日之财而当令旺相，财自贪旺不能为我所得，求财反费己财。")
    # 十五、脱上逢脱防虚诈（干上神为脱气，又生天将）
    if (SHENG[GAN_WX[day_gan]] == ZHI_WX[sk]
            and tianj.get(sk) and SHENG[ZHI_WX[sk]] == JIANG_WX[tianj[sk]]):
        add("第十五法", "脱上逢脱防虚诈", "干上逢脱气，其神又生天将，名脱上脱，凡占尽被脱耗，多虚诈不实。")
    # 十六、空上乘空事莫追
    if sk in kong and tianj.get(sk) == "天空":
        add("第十六法", "空上乘空事莫追", "干上旬空又乘天空，指空话空，全无实象。")
    # 十七、进茹空亡宜退步
    idxs = [ZHI.index(z) for z in chuan]
    if ((idxs[1] - idxs[0]) % 12 == 1 and (idxs[2] - idxs[1]) % 12 == 1
            and all(z in kong for z in chuan)):
        add("第十七法", "进茹空亡宜退步", "三传顺连茹而皆空亡，向前值三空，宜退步守干支。")
    # 十八、踏脚空亡进用宜
    if ((idxs[0] - idxs[1]) % 12 == 1 and (idxs[1] - idxs[2]) % 12 == 1
            and all(z in kong for z in chuan)):
        add("第十八法", "踏脚空亡进用宜", "三传退连茹而皆空亡，退后遇空，宜进不宜退。")
    # 十九、胎财生气妻怀孕
    if dt is not None:
        tai = GAN_CS[day_gan][10]
        shengqi = ZHI[(ZHI.index(jian) - 2) % 12]
        if sk == tai and ZHI_WX[sk] == KE[GAN_WX[day_gan]] and sk == shengqi:
            add("第十九法", "胎财生气妻怀孕", "干上日之胎神作妻财又逢月内生气，占妻必有孕。")
        # 二十、胎财死气损胎推
        siqi = ZHI[(ZHI.index(jian) + 4) % 12]
        if sk == tai and ZHI_WX[sk] == KE[GAN_WX[day_gan]] and sk == siqi:
            add("第二十法", "胎财死气损胎推", "胎神作妻财却逢月内死气，妇孕不育。")
    # 二一、交车相合交关利（日干与支上神六合、地支与干上神六合）
    if LIUHE.get(JIGONG[day_gan]) == zs and LIUHE.get(day_zhi) == sk:
        add("第二十一法", "交车相合交关利", "日干与支上神作六合、地支与干上神作六合，名交车合，主交关交易而成合。")
    # 二二、上下皆合两心齐（日干与干上神六合、地支与支上神六合）
    if LIUHE.get(JIGONG[day_gan]) == sk and LIUHE.get(day_zhi) == zs:
        add("第二十二法", "上下皆合两心齐", "日干与上神作六合、地支亦与上神作六合，上下同心，客主相顺。")
    # 二三、彼求我事支传干
    if chu == zs and mo == sk:
        add("第二十三法", "彼求我事支传干", "初传从支上起、末传归干上，主他人委托我谋事，吉凶皆成。")
    # 二四、我求彼事干传支
    if chu == sk and mo == zs:
        add("第二十四法", "我求彼事干传支", "初传从干上起、末传归在支上，凡事勉强俯求于人，礼下求人。")
    # 二五、金日逢丁凶祸动（庚辛日六处见旬丁）
    if day_gan in "庚辛" and ding in liuchu:
        add("第二十五法", "金日逢丁凶祸动", "庚辛日三传日辰（年命）逢旬内六丁之神，必主凶动。")
    # 二六、水日逢丁财动之（壬癸日六处见旬丁）
    if day_gan in "壬癸" and ding in liuchu:
        add("第二十六法", "水日逢丁财动之", "壬癸日六处逢旬内六丁之神，必主财动，远方财物付本身之象。")
    # 二七、传财化鬼财休觅（三传皆财，生起干上日鬼）
    if (all(ZHI_WX[z] == KE[GAN_WX[day_gan]] for z in chuan)
            and KE[ZHI_WX[sk]] == GAN_WX[day_gan]
            and SHENG[KE[GAN_WX[day_gan]]] == ZHI_WX[sk]):
        add("第二十七法", "传财化鬼财休觅", "三传皆日之财，反生起干上日鬼而伤日干，必因取财而致祸。")
    # 二八、传鬼化财钱险危（三传皆鬼，其一非空为财）
    if (all(KE[ZHI_WX[z]] == GAN_WX[day_gan] for z in chuan)
            and any(ZHI_WX[z] == KE[GAN_WX[day_gan]] and z not in kong for z in chuan)):
        add("第二十八法", "传鬼化财钱险危", "三传俱鬼，独存非空一字为财，全鬼变财，其财终是危险中出。")
    # 二九、眷属丰盈居狭宅（三传生日干而脱支辰）
    if (all(SHENG[ZHI_WX[z]] == GAN_WX[day_gan] for z in chuan)
            and all(SHENG[ZHI_WX[day_zhi]] == ZHI_WX[z] for z in chuan)):
        add("第二十九法", "眷属丰盈居狭宅", "三传生其日干、反脱其支辰，人口丰隆而居宅窄狭。")
    # 三十、屋宅宽广致人衰（三传盗日干而生支辰）
    if (all(SHENG[GAN_WX[day_gan]] == ZHI_WX[z] for z in chuan)
            and all(SHENG[ZHI_WX[z]] == ZHI_WX[day_zhi] for z in chuan)):
        add("第三十法", "屋宅宽广致人衰", "三传窃盗日干、反生支辰，宅广人稀，人口日渐衰羸。")
    # 三一、三传递生人举荐（初生中中生末末生日干，或末生中中生初初生日干）
    if ((SHENG[ZHI_WX[chu]] == ZHI_WX[zhong] and SHENG[ZHI_WX[zhong]] == ZHI_WX[mo]
         and SHENG[ZHI_WX[mo]] == GAN_WX[day_gan])
            or (SHENG[ZHI_WX[mo]] == ZHI_WX[zhong] and SHENG[ZHI_WX[zhong]] == ZHI_WX[chu]
                and SHENG[ZHI_WX[chu]] == GAN_WX[day_gan])):
        add("第三十一法", "三传递生人举荐", "三传递相生而生日干，隔三隔四有人举荐之意，所求皆得成就。")
    # 三二、三传互克众人欺（初克中中克末末克日干，或反）
    if ((KE[ZHI_WX[chu]] == ZHI_WX[zhong] and KE[ZHI_WX[zhong]] == ZHI_WX[mo]
         and KE[ZHI_WX[mo]] == GAN_WX[day_gan])
            or (KE[ZHI_WX[mo]] == ZHI_WX[zhong] and KE[ZHI_WX[zhong]] == ZHI_WX[chu]
                and KE[ZHI_WX[chu]] == GAN_WX[day_gan])):
        add("第三十二法", "三传互克众人欺", "三传递互相克而克日干，必有人递互相克害，众口欺凌。")
    # 三三、有始无终难变易（初长生末墓＝有始无终；初墓末长生＝难变易）
    cs = GAN_CS[day_gan]
    if chu == cs[0] and mo == cs[8]:
        add("第三十三法", "有始无终难变易", "初传日之长生、末传日之墓，先美后败，有始无终。")
    elif chu == cs[8] and mo == cs[0]:
        add("第三十三法", "有始无终难变易", "初传日之墓、末传日之长生，自墓传生，先难后易。")
    # 三五、人宅受脱俱招盗（干支上皆脱气，或干上脱支、支上脱干）
    if ((SHENG[GAN_WX[day_gan]] == ZHI_WX[sk] and SHENG[ZHI_WX[day_zhi]] == ZHI_WX[zs])
            or (SHENG[ZHI_WX[day_zhi]] == ZHI_WX[sk] and SHENG[GAN_WX[day_gan]] == ZHI_WX[zs])):
        add("第三十五法", "人宅受脱俱招盗", "干支上皆乘脱气（或交互相脱），人被脱赚，家宅必被盗窃财物。")
    # 三六、干支皆败事倾颓（干支上皆逢败气）
    if sk == GAN_CS[day_gan][1] and zs == _zhi_state(day_zhi, 1):
        add("第三十六法", "干支皆败事倾颓", "干支上皆逢败气，占身气血衰败，占宅屋舍崩颓。")
    # 三七、末助初兮三等讼（末生初：初生日干／初克日干／初作日财）
    if SHENG[ZHI_WX[mo]] == ZHI_WX[chu]:
        if SHENG[ZHI_WX[chu]] == GAN_WX[day_gan]:
            add("第三十七法", "末助初兮三等讼", "末传生初传而初生日干，傍有人暗地相助推荐而致亨旺。")
        elif KE[ZHI_WX[chu]] == GAN_WX[day_gan]:
            add("第三十七法", "末助初兮三等讼", "末传生初传而初克日干，傍有教唆之人，不宜求财取财。")
        elif ZHI_WX[chu] == KE[GAN_WX[day_gan]]:
            add("第三十七法", "末助初兮三等讼", "末传生初传而初作日之财神，必暗有人以财相助。")
    # 三八、闭口卦体两般推（旬尾加旬首发用）
    if chu == xun_wei and inv[chu] == xun_zhi:
        add("第三十八法", "闭口卦体两般推", "旬尾加旬首发用，名闭口，止宜捕盗贼而追逃亡，求人说事人但闭口不语。")
    # 三九、太阳照武宜擒贼（玄武乘月将）
    if any(z == yue_jiang and tianj.get(z) == "玄武" for z in tianj):
        add("第三十九法", "太阳照武宜擒贼", "玄武坐于太阳月将之上，占贼必败露，不劳捕捉必然自败。")
    # 四一、富贵干支逢禄马（干上有支驿马、支上有干禄神）
    if sk == MA[day_zhi] and zs == GAN_LU[day_gan]:
        add("第四十一法", "富贵干支逢禄马", "干上有支驿马、支上有干禄神，名真富贵卦，加官添俸、富贵双全。")
    # 四二、尊崇传内遇三奇（三传遁干全乙丙丁或甲戊庚）
    if set(dun) in ({"乙", "丙", "丁"}, {"甲", "庚", "戊"}):
        add("第四十二法", "尊崇传内遇三奇", "三传遁旬中之干全遇乙丙丁（或甲戊庚），君子官居一品，常人亦可消灾。")
    # 四三、害贵讼直作屈断（初传害贵人）
    if LIUHAI.get(chu) == gui or LIUHAI.get(gui) == chu:
        add("第四十三法", "害贵讼直作屈断", "用神害天乙贵人，占讼理虽直而必致曲断。")
    # 四四、课传俱贵转无依（四课三传皆是昼夜贵人）
    if all(z in (gui, gui2) for z in (sk, sy, zs, zy, chu, zhong, mo)):
        add("第四十四法", "课传俱贵转无依", "四课三传皆是昼夜贵人所聚，名遍地贵人，贵多不贵，反无依倚。")
    # 四五、昼夜贵加求两贵（昼贵加夜贵上，或反之）
    if inv.get(gui) == gui2 or inv.get(gui2) == gui:
        add("第四十五法", "昼夜贵加求两贵", "六处有旦暮天乙相加，告贵求事必干涉两贵人而成就。")
    # 四六、贵人差迭事参差（昼贵临夜地、夜贵临昼方）
    if inv.get(gui) in "酉戌亥子丑寅" and inv.get(gui2) in "卯辰巳午未申":
        add("第四十六法", "贵人差迭事参差", "昼贵临于夜地、夜贵却临昼方，告贵求事多不归一。")
    # 四七、贵虽在狱宜临干（贵人坐辰戌；乙辛日临干反宜干贵）
    if inv.get(gui) in ("辰", "戌"):
        if day_gan in "乙辛" and sk == gui:
            add("第四十七法", "贵虽在狱宜临干", "乙辛日贵人坐辰戌而临干，名贵人临身，反宜干投贵人周全成事。")
        else:
            add("第四十七法", "贵虽在狱宜临干", "贵人坐地盘辰戌之上，名天乙入狱，干官贵怒，惟宜私谋阴祷。")
    # 四八、鬼乘天乙乃神祇（干上神为日鬼又是贵人）
    if KE[ZHI_WX[sk]] == GAN_WX[day_gan] and sk == gui:
        add("第四十八法", "鬼乘天乙乃神祇", "日鬼临干而为贵人，切不可作鬼祟看，占病必是神祇为害。")
    # 四九、两贵受克难干贵（昼夜贵人皆坐受克之方）
    if (inv.get(gui) and inv.get(gui2)
            and KE[ZHI_WX[inv[gui]]] == ZHI_WX[gui]
            and KE[ZHI_WX[inv[gui2]]] == ZHI_WX[gui2]):
        add("第四十九法", "两贵受克难干贵", "昼夜贵人皆立受克之方，切不可告贵用事，二贵自受克制必自怒。")
    # 五十、二贵皆空虚喜期
    if gui in kong and gui2 in kong:
        add("第五十法", "二贵皆空虚喜期", "昼夜贵人皆空亡，干投贵人先允后被人搀越，报喜勿信。")
    # 五一、魁度天门关隔定（戌加亥为用）
    if chu == "戌" and inv["戌"] == "亥":
        add("第五十一法", "魁度天门关隔定", "戌加亥为用，凡占谋用皆被阻隔。")
    # 五二、罡塞鬼户任谋为（辰加寅）
    if inv.get("辰") == "寅":
        add("第五十二法", "罡塞鬼户任谋为", "辰加寅为罡塞鬼户，不论在传不在传，众鬼不得窥觑，宜闪灾避难。")
    # 五三、两蛇夹墓凶难免（干墓加干乘蛇临巳）
    if sk == GAN_CS[day_gan][8] and tianj.get(sk) == "螣蛇" and inv.get(sk) == "巳":
        add("第五十三法", "两蛇夹墓凶难免", "干墓加干乘螣蛇临巳，名两蛇夹墓，占病积块难救，诸事昏晦。")
    # 五四、虎视逢虎力难施（昴星虎视课中天将乘白虎）
    if keti == "昴星·虎视转篷" and any(tianj.get(z) == "白虎" for z in set(chuan) | {sk, zs}):
        add("第五十四法", "虎视逢虎力难施", "虎视课中天将又乘白虎，前后皆虎，凡占至惊至危。")
    # 五五、所谋多拙逢罗网（干上干前一辰、支上支前一辰）
    if sk == ZHI[(ZHI.index(JIGONG[day_gan]) + 1) % 12] and zs == ZHI[(ZHI.index(day_zhi) + 1) % 12]:
        add("第五十五法", "所谋多拙逢罗网", "干上乘干前一辰、支上乘支前一辰，罗网兜裹身宅，诸占不能亨快。")
    # 五六、天网自裹己招非（干墓覆日且本命即墓神）
    if sk == GAN_CS[day_gan][8] and nianming and nianming.get("本命") == GAN_CS[day_gan][8]:
        add("第五十六法", "天网自裹己招非", "墓神覆日而本命又作墓神，名天网自裹，必自招其祸。")
    # 五九、华盖覆日人昏晦（干墓临干上发用）
    if chu == GAN_CS[day_gan][8] and sk == chu:
        add("第五十九法", "华盖覆日人昏晦", "辰之华盖作干之墓神临于干上发用，占身位多昏多晦，卒难明白。")
    # 六十、太阳射宅屋光辉（月将加支）
    if yue_jiang and inv.get(yue_jiang) == day_zhi:
        add("第六十法", "太阳射宅屋光辉", "月将加支，名太阳射宅，其屋向阳明朗，常有上人光饰。")
    # 六一、干乘墓虎无占病（干墓乘白虎临干）
    if sk == GAN_CS[day_gan][8] and tianj.get(sk) == "白虎":
        add("第六十一法", "干乘墓虎无占病", "干墓乘白虎加干，占病必死，诸占且昏且迷，防仇人冤执。")
    # 六二、支乘墓虎有伏尸（干墓或支墓乘白虎临支）
    if (zs in (GAN_CS[day_gan][8], BIFA_MU_WX[ZHI_WX[day_zhi]])) and tianj.get(zs) == "白虎":
        add("第六十二法", "支乘墓虎有伏尸", "干墓或支墓乘白虎临支，占宅必有伏尸鬼祸，或有形响。")
    # 六三、彼此全伤防两损（干支各被上神克）
    if KE[ZHI_WX[sk]] == GAN_WX[day_gan] and KE[ZHI_WX[zs]] == ZHI_WX[day_zhi]:
        add("第六十三法", "彼此全伤防两损", "支干各被上神克伐，两边各有所亏，占讼两家皆被扑责。")
    # 六四、夫妇芜淫各有私（干被支上神克、支被干上神克）
    if KE[ZHI_WX[zs]] == GAN_WX[day_gan] and KE[ZHI_WX[sk]] == ZHI_WX[day_zhi]:
        add("第六十四法", "夫妇芜淫各有私", "干被支上神克、支被干上神克，名芜淫卦，彼此各怀恶意。")
    # 六五、干墓并关人宅废（干墓作关神发用）
    if dt is not None:
        guan = {"寅": "丑", "卯": "丑", "辰": "丑", "巳": "辰", "午": "辰", "未": "辰",
                "申": "未", "酉": "未", "戌": "未", "亥": "戌", "子": "戌", "丑": "戌"}[jian]
        if chu == GAN_CS[day_gan][8] and chu == guan:
            add("第六十五法", "干墓并关人宅废", "日干之墓作四季之关神发用，临干课主人口灾衰，临支课主宅废。")
    # 六六、支坟财并旅程稽（支墓作日财发用）
    if chu == BIFA_MU_WX[ZHI_WX[day_zhi]] and ZHI_WX[chu] == KE[GAN_WX[day_gan]]:
        add("第六十六法", "支坟财并旅程稽", "地支之墓作日干之财发用，必主商贩折本，在路阻程。")
    # 六七、受虎克神为病症（白虎所乘神之五行定病位）
    for z, j in tianj.items():
        if j == "白虎":
            w = ZHI_WX[z]
            bing = {"金": "肝经受病，可治肺而不可治肝", "木": "脾经受病，可治肝而不可治脾",
                    "水": "心经受病，可治肾而不可治心", "火": "肺经受病，可治心而不可治肺",
                    "土": "肾经受病，可治脾而不可治肾"}[w]
            add("第六十七法", "受虎克神为病症", f"白虎乘{w}神，必是{bing}。")
    # 六八、制鬼之位乃良医（干上为日鬼而支上神克之）
    if KE[ZHI_WX[sk]] == GAN_WX[day_gan] and KE[ZHI_WX[zs]] == ZHI_WX[sk]:
        add("第六十八法", "制鬼之位乃良医", "干上日鬼，支上有神克之，此神便是良医，危难中必得人解纷。")
    # 六九、虎乘遁鬼殃非浅（白虎所乘神遁干为日鬼）
    for z, j in tianj.items():
        if j == "白虎":
            dz = dunkun_gz(day_gz, [z])[0]
            if dz != "空" and KE[GAN_WX[dz]] == GAN_WX[day_gan]:
                add("第六十九法", "虎乘遁鬼殃非浅", "白虎乘旬内之干为日鬼，其咎弥深，纵空亡亦不能为救。")
    # 七十、鬼临三四讼灾随（三四课即支上支阴皆日鬼）
    if KE[ZHI_WX[zs]] == GAN_WX[day_gan] and KE[ZHI_WX[zy]] == GAN_WX[day_gan]:
        add("第七十法", "鬼临三四讼灾随", "日干之鬼临于三四课全者，官词病患继踵而至。")
    # 七一、病符克宅全家患（岁后一辰临支克支）
    if sui is not None:
        bingfu = ZHI[(ZHI.index(sui) - 1) % 12]
        if inv.get(bingfu) == day_zhi and KE[ZHI_WX[bingfu]] == ZHI_WX[day_zhi]:
            add("第七十一法", "病符克宅全家患", "病符（旧太岁）临支又克支，主阖家病患。")
    # 七二、丧吊全逢挂缟衣（干支上全逢丧门吊客）
    if sui is not None:
        sang, diao = ZHI[(ZHI.index(sui) + 2) % 12], ZHI[(ZHI.index(sui) - 2) % 12]
        if (sk == diao and zs == sang) or (sk == sang and zs == diao):
            add("第七十二法", "丧吊全逢挂缟衣", "支干上全逢丧门吊客二位凶煞，其年必哭送亲姻，身披孝服。")
    # 七四、空空如也事休追（三传皆空，或三合课两传空一传乘天空）
    sanhe_ok = any(set(chuan) <= set(j) for j in SANHE)
    if (all(z in kong for z in chuan)
            or (sanhe_ok and sum(z in kong for z in chuan) == 2
                and any(tianj.get(z) == "天空" for z in chuan))):
        add("第七十四法", "空空如也事休追", "三传皆空亡（或两传空一传乘天空），指空话空，全无实象。")
    # 七五、宾主不投刑在上（干支上神互刑）
    if XING.get(sk) == zs or XING.get(zs) == sk:
        add("第七十五法", "宾主不投刑在上", "支干上神相刑，所谋交涉事必各有异心。")
    # 七六、彼此猜忌害相随（干支上下各作六害）
    if LIUHAI.get(JIGONG[day_gan]) == sk and LIUHAI.get(day_zhi) == zs:
        add("第七十六法", "彼此猜忌害相随", "日干与上神作六害、地支与上神作六害，彼此各相猜忌，两意相谋。")
    # 七七、互生俱生凡事益
    if SHENG[ZHI_WX[sk]] == ZHI_WX[day_zhi] and SHENG[ZHI_WX[zs]] == GAN_WX[day_gan]:
        add("第七十七法", "互生俱生凡事益", "干上神生支、支上神生干，两相有益，各有生意。")
    elif SHENG[ZHI_WX[sk]] == GAN_WX[day_gan] and SHENG[ZHI_WX[zs]] == ZHI_WX[day_zhi]:
        add("第七十七法", "互生俱生凡事益", "干上神生干、支上神生支，各有生意，彼此和顺。")
    # 七八、互旺皆旺坐谋宜
    gan_wang, zhi_wang = GAN_CS[day_gan][4], _zhi_state(day_zhi, 3)
    if sk == zhi_wang and zs == gan_wang:
        add("第七十八法", "互旺皆旺坐谋宜", "干上支之旺神、支上干之旺神，两相投奔，各有兴旺。")
    elif sk == gan_wang and zs == zhi_wang:
        add("第七十八法", "互旺皆旺坐谋宜", "支干上皆乘旺神，凡谋事顺利，惟宜坐待，不利谋动。")
    # 七九、干支值绝凡谋决（干支上皆乘绝神）
    gan_jue = GAN_CS[day_gan][9]
    zhi_jue = ZHI_JU_TU.get(day_zhi) or _zhi_state(day_zhi, 8)
    if sk == gan_jue and zs == zhi_jue:
        add("第七十九法", "干支值绝凡谋决", "支干上皆乘绝神，止宜结绝凶事、释解官讼，不宜占食禄事。")
    # 八十、人宅皆死各衰羸（干支上互乘死气，或全乘死气）
    gan_si, zhi_si = GAN_CS[day_gan][7], _zhi_state(day_zhi, 6)
    if (sk == zhi_si and zs == gan_si) or (sk == gan_si and zs == zhi_si):
        add("第八十法", "人宅皆死各衰羸", "干支上乘死气（互乘或全乘），止宜休息，万事不利谋动。")
    # 八一、传墓入墓分憎爱（中传或末传墓初传）
    if zhong == BIFA_MU_WX[ZHI_WX[chu]] or mo == BIFA_MU_WX[ZHI_WX[chu]]:
        add("第八十一法", "传墓入墓分憎爱", "中末传墓初传，宜详初传是何类神：吉类入墓憎、鬼盗入墓爱。")
    # 八二、不行传者考初时（中末空亡）
    if zhong in kong and mo in kong:
        add("第八十二法", "不行传者考初时", "中末传空亡，名不行传，只以初传断其凶吉。")
    # 八三、万事喜忻三六合（三传三合局，干支上见局中位之六合神）
    for ju in SANHE:
        if set(chuan) <= set(ju):
            mid = ju[1]
            he = LIUHE[mid]
            if he in (sk, zs):
                add("第八十三法", "万事喜忻三六合", "三传三合局而干支上见局中位之六合神，三六相呼，凡谋皆遂。")
            break
    # 八四、合中犯杀蜜中砒（三传三合，干支上见局中位之刑/害/冲）
    for ju in SANHE:
        if set(chuan) <= set(ju):
            mid = ju[1]
            sha = {XING[mid], LIUHAI[mid], CHONG[mid]}
            if any(z in sha for z in (sk, zs)):
                add("第八十四法", "合中犯杀蜜中砒", "三传三合而干支上见局中位之刑、害、冲，笑里藏刀，事将成合失便宜。")
            break
    # 八五、初遭夹克不由己（初传坐克方又被天将克）
    if (KE[ZHI_WX[inv[chu]]] == ZHI_WX[chu]
            and tianj.get(chu) and KE[JIANG_WX[tianj[chu]]] == ZHI_WX[chu]):
        add("第八十五法", "初遭夹克不由己", "初传坐于克方又被天将所伤，名夹克，凡占身不由己，受人驱策。")
    # 八六、将逢内战所谋危（初传坐克方＝下克上）
    if KE[ZHI_WX[inv[chu]]] == ZHI_WX[chu]:
        add("第八十六法", "将逢内战所谋危", "发用神坐克方，天将内战，用事将成而被人搅扰。")
    # 八七、人宅坐墓甘招晦（天盘干支皆坐地盘墓上）
    if inv[JIGONG[day_gan]] == GAN_CS[day_gan][8] and inv[day_zhi] == BIFA_MU_WX[ZHI_WX[day_zhi]]:
        add("第八十七法", "人宅坐墓甘招晦", "天盘支干皆坐于地盘墓上，凡事皆自招其祸，心甘情愿受其暗昧。")
    # 八八、干支乘墓各昏迷（干支上神皆墓）
    if sk == GAN_CS[day_gan][8] and zs == BIFA_MU_WX[ZHI_WX[day_zhi]]:
        add("第八十八法", "干支乘墓各昏迷", "支干全被上神墓，其人如云雾中行，家宅自尘暗，所占不亨快。")
    # 八九、任信丁马须言动（伏吟课而丁神或驿马在传及干支上）
    if keti in ("伏吟", "自任", "自信", "杜传") and (ding in set(chuan) | {sk, zs}
                                                        or MA[day_zhi] in chuan):
        add("第八十九法", "任信丁马须言动", "伏吟课而传中干支上见旬丁或驿马，静而求动，占访人必出外。")
    # 九十、来去俱空岂动宜（返吟课三传皆空）
    if keti.startswith("返吟") and all(z in kong for z in chuan):
        add("第九十法", "来去俱空岂动宜", "返吟课而三传皆空亡，虽有动意，实不动也。")
    # 九一、虎临干鬼凶速速（六处有日鬼乘白虎）
    if any(tianj.get(z) == "白虎" and KE[ZHI_WX[z]] == GAN_WX[day_gan]
           for z in set(chuan) | {sk, zs}):
        add("第九十一法", "虎临干鬼凶速速", "日干之鬼上乘白虎，凡占凶祸速中又速。")
    # 九二、龙加生气吉迟迟（青龙乘生干之神又作月内生气）
    if dt is not None:
        shengqi = ZHI[(ZHI.index(jian) - 2) % 12]
        for z, j in tianj.items():
            if j == "青龙" and SHENG[ZHI_WX[z]] == GAN_WX[day_gan] and z == shengqi:
                add("第九十二法", "龙加生气吉迟迟", "青龙乘生干之神又作月内生气，虽目下未足峥嵘，却徐徐发福。")
                break
    return out
