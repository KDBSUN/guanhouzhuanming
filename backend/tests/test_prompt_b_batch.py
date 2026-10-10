# -*- coding: utf-8 -*-
"""
提示词典籍校正落地锁（A批引文修正 + B批方法增补）
==================================================
锁定内容（详见 docs/梅花六爻提示词校正分析.md）：
  六爻：仇神、元神/忌神有力无力判据、接续相生、用神两现、用神不上卦（变爻→伏神→再占）、
        暗动/日破、进神退神、反吟伏吟、长生墓绝三件、月破句重写、应期补实破与合绊。
  梅花：体克用诸事吉（A1）、体党用党计数（B1）、应期三法（B2）、不拘体用（B3）、
        增辉/诀（A2/A3）、十条规矩（C1）、删六爻字样（C2）。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import INTERPRETATION_SYSTEM_PROMPT, LIUYAO_SYSTEM_PROMPT  # noqa: E402


def test_liuyao_b_batch():
    p = LIUYAO_SYSTEM_PROMPT
    for kw in ("仇神", "接续相生", "用神两现", "用神不上卦", "伏神", "暗动", "日破",
               "进神", "退神", "反吟", "伏吟", "长生、帝旺、墓、绝"):
        assert kw in p, f"六爻提示词缺 B 批内容：{kw}"
    # T-04（已裁一致，2026-09-24，登记表 §5）：十二长生两书同口径——
    # 甲「只验生旺墓绝，其余不验」「化养化病化胎及化沐浴，俱不验，已尽删矣」；
    # 乙「惟是长生、墓、绝三件，卦卦须看」并同斥「不可执疑于养主狐疑」。
    # 判定只用四位，且必须写明两书各自的原话。
    assert "已尽删矣" in p and "不取沐浴胎养病" in p
    assert "余得验者，只验生旺墓绝" in p
    assert "不可执疑于养主狐疑" in p
    # 判据清单骨架
    assert "元神有力方能生用，其五" in p and "忌神动而不克用者七" in p
    # 飞伏四象 + 伏神得出条件
    assert "飞来生伏得长生" in p and "飞神空破休囚墓绝" in p
    # 应期补全（钉内容不钉措辞：本轮蒸馏把「月破者实破之日」改写成《月破章》的三法原文）
    assert "实破之日则不破" in p and "逢合之日则不破" in p and "出月则不破" in p
    assert "冲开之月日应" in p
    # A批原意：月破不得被当成「到底无用」。但**不得**用「月破为空」四字来守——
    # 《增删卜易·旬空章》野鹤曰列"空"的诸条里确有「月破为空」一句：
    #   「旺不为空，动不为空，动而化空，伏而旺相，皆不为空，有日建动爻生扶者，亦不为空，
    #     月破为空，有气不动亦为空，伏而被克亦为空，真空为空。」
    # 那是**旬空判定上作空论**，与「月破即无用」是两回事；原来的字面守卫把书证一起禁了。
    # 改钉真正的意图：出破三法必须在，且须写明月破之爻动则仍有祸福之基。
    assert "出破三法" in p and "仍有祸福之基" in p
    assert "到底而破" in p, "须写明唯静而不动、又无生助才到底而破"


def test_meihua_a_b_batch():
    p = INTERPRETATION_SYSTEM_PROMPT
    # A1：体克用诸事吉（旧文"事可成但费力"不得残留）
    assert "体克用，诸事吉" in p
    assert "事可成但费力" not in p
    # A2/A3 字讹修正
    # A2 字讹（增辉/争辉）已随三要取象移出主提示词、搬进外应模块，故改在 JSON 上钉；
    # 并加钉一处旧稿讹字：「见蜂可以言『卦』」曾误作「封」。
    import json as _json
    from pathlib import Path as _P
    _sy = _json.loads((_P(__file__).resolve().parents[1] / "waijing_xiang.json")
                      .read_text(encoding="utf-8"))["sanyao"]["items"]
    assert _sy["天时之应"]["text"].startswith("云开见日，事必增辉")
    assert "见蜂可以言“卦”" in _sy["叶音之应"]["text"]
    assert "争辉" not in p and "封”" not in p
    assert "衰旺之诀也" in p and "衰旺之决也" not in p
    # C1：规矩条数**自洽**——开头自称的条数必须等于规矩区实际编号个数，且编号不重复。
    # 原断言写死 "十条规矩"，而正文实际只有九条、"四、"还重复出现过两次（历史手改编号的
    # 痕迹）——它锁住的是那个不一致，而不是正确性；增减规矩时也会误报。
    # 改为自洽性断言：无论将来是九条还是十条，只要自称与实情一致、编号不重，即通过。
    m = re.search(r"以下([一二三四五六七八九十]+)条规矩", p)
    assert m, "提示词未声明规矩条数"
    claimed = "一二三四五六七八九十".index(m.group(1)) + 1
    # 从第一条规矩起算，避开"素材边界"块自己的编号
    region = p[p.find("\n一、无故不占"):p.find("\n---\n")]
    heads = re.findall(r"^([一二三四五六七八九十]+)、", region, re.M)
    assert len(heads) == claimed, f"自称{claimed}条规矩，正文实为{len(heads)}条：{heads}"
    assert len(set(heads)) == len(heads), f"规矩编号有重复：{heads}"
    # C2：梅花提示词里不得出现六爻字样
    assert "梅花卦象数据" in p and "六爻排盘" not in p
    # B1 体党用党计数
    assert "生体之卦多则愈吉" in p and "体党多则体势盛" in p
    # B2 应期三法：钉"三法都在"，不钉旧措辞。
    # 原断言写死 "成卦总数定刻期""行则应速"——瘦身时措辞被压成
    # "以成卦总数定远近""行取半数、坐倍其数"（语义未变），旧措辞断言会误报。
    assert "事成应于生体之卦卦气旺相之日" in p          # 法一：卦气旺相
    assert "以成卦总数定远近" in p and "远事以年" in p    # 法二：成卦总数定远近
    assert "行取半数" in p and "坐倍其数" in p           # 法三：动静调速
    assert "以日为月" in p                              # 久远之占
    # B3 不拘体用
    assert "西林寺" in p and "不必拘体用" in p
