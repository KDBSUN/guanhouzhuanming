# -*- coding: utf-8 -*-
"""取数依据注入 + 外应解读专用提示词 的回归锁。

两件事各自守一条红线：
1. 取数中间量只能由引擎算（AI 读了解释，不许自己倒推重算）；
2. 带外应时只解读外应，不把整卦重解一遍。
"""
import inspect

import main
import engine


# ---------- 1. 取数依据 ----------

def test_derive_present_for_all_methods():
    cases = [
        engine.divine_yizi("明"),
        engine.divine_erzi("雷", "风"),
        engine.divine_duozi("今日动静如何"),
        engine.divine_time(),
        engine.divine_manual(3, 4, 3),
    ]
    for r in cases:
        d = (r.get("method_params") or {}).get("derive")
        assert d, f"{r.get('method')} 缺 derive"
        for k in ("upper", "lower", "moving"):
            assert d[k]["note"], f"{r.get('method')}.{k} 无 note"
            # 手动起卦不取余（用户给的就是卦），所以只有它不必带算式
            if r.get("method") != "manual":
                assert "÷" in d[k]["note"], "note 应含算式"
        if r.get("method") == "manual":
            assert "手动指定" in d["upper"]["note"]


def test_derive_matches_deduced_gua_for_every_method():
    """note 里的数必须与最终卦象自洽——否则中间量就是假的。

    时间占最需要这条：用户拿农历年月日自己加一遍，必须得到同一个卦。
    手动起卦的 derive 只有说明、没有算式，故只比 note 里写明的数。
    """
    for r in (engine.divine_erzi("雷", "风"), engine.divine_time(),
              engine.divine_duozi("今日动静如何")):
        d = r["method_params"]["derive"]
        u, lo = (int(x) for x in r["ben_gua"]["key"].split(","))
        assert d["upper"]["value"] == u, f"{r['method']} 上卦取数与卦象不符"
        assert d["lower"]["value"] == lo, f"{r['method']} 下卦取数与卦象不符"
        assert d["moving"]["value"] == r["moving_yao"]["position"], f"{r['method']} 动爻取数不符"
    # 手动起卦无算式，只核 note 里报的数与卦象一致（用户给的数就是卦）
    m = engine.divine_manual(3, 4, 3)
    u, lo = (int(x) for x in m["ben_gua"]["key"].split(","))
    assert (u, lo, m["moving_yao"]["position"]) == (3, 4, 3)
    assert "3" in m["method_params"]["derive"]["upper"]["note"]
    assert "4" in m["method_params"]["derive"]["lower"]["note"]
    # 余 0 必须显式说明"视为 8/6"，否则 AI 会读成"没有余数"
    # 六字走声调法，动爻＝全部声调之和除六（书证算例：8+5=13÷6 余 1，L904）。
    # 旧断言钉"视为"，那是按字数取动爻时的产物（6÷6 余 0），取数改声调后不再成立。
    z = engine.divine_duozi("今日动静如何")["method_params"]["derive"]
    assert "声调" in z["moving"]["note"], z["moving"]["note"]


def test_derive_is_injected_into_user_prompt():
    r = engine.divine_yizi("明")
    p = main.build_user_prompt(r, "测字问事业")
    assert "取数依据" in p
    assert "卦以八除" in p and "爻以六除" in p
    assert "不得重算" in p


def test_time_prompt_carries_derive():
    """时间占也要把算式交给 AI：年用支序数这一点不说清，AI 就会自己编一个由来。"""
    p = main.build_user_prompt(engine.divine_time(), "问事")
    assert "取数依据" in p
    assert "年支" in p and "卦以八除" in p


def test_prompt_without_derive_stays_clean():
    """没有 derive 的卦（异常/旧数据）不该出现空的取数依据小节。"""
    r = engine.divine_time()
    r["method_params"].pop("derive", None)
    assert "取数依据" not in main.build_user_prompt(r, "问事")


# ---------- 2. 外应解读专用提示词 ----------

def test_omen_prompt_is_separate_and_wired():
    assert hasattr(main, "OMEN_SYSTEM_PROMPT")
    src = inspect.getsource(main.meihua_chat)
    assert "OMEN_SYSTEM_PROMPT if request.waijing" in src, "追问路径未按外应切换提示词"
    assert "INTERPRETATION_SYSTEM_PROMPT" in src, "无外应时仍应走主提示词"


def test_omen_prompt_only_does_omen():
    """它必须按住"重解整卦"，并钉死合内外口径与"不许随意不拘体用"。"""
    p = main.OMEN_SYSTEM_PROMPT
    assert "只解读一条外应" in p
    assert "不要重新解整卦" in p
    assert "终局仍随内卦" in p          # 学林本《三要灵应篇》
    assert "不得随意宣称「不拘体用」" in p
    assert "不得虚构" in p
    # 不得把主提示词那套两部分输出结构带过来
    assert "两部分" not in p


def test_omen_prompt_not_leaked_into_main_prompt():
    """主提示词是整卦解读用的，不能混入"只解读一条外应"的口径。"""
    assert "只解读一条外应" not in main.INTERPRETATION_SYSTEM_PROMPT
