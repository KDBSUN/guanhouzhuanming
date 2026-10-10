# -*- coding: utf-8 -*-
"""字占（按字数自动分派）的回归锁
================================
为什么单独立这一份：2026-09-22 查出两个真错误，而 480 条测试**一条都没覆盖到**——
  1. engine.divine_text 四字档调用了 random.random()，但 engine.py 里没有 import random，
     四字输入必 NameError（接口回 500）；
  2. main.py 的 duozi 分派没有把 params 里的 zi_mode 传给引擎，
     而四字档的取数法（声调／笔画）是 50% 随机定的——前端摇定一次随两次请求带上，
     不带就会出现"起卦一个卦、点 AI 解卦又是另一个卦"。
两条都是"没测试就没人发现"的典型，故在此锁死：
  · 四个字数档都要能起出卦（不许崩）；
  · 四字档传 zi_mode 必须稳定，且声调／笔画两法给出的卦不同；
  · 接口层的 zi_mode 必须原样落到 method_params 上（证明它真的传下去了）。
"""
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import engine          # noqa: E402
import main            # noqa: E402
from fastapi.testclient import TestClient   # noqa: E402

client = TestClient(main.app)


def _gua(text: str, zi_mode: str = "") -> str:
    return engine.divine_text(text, zi_mode)["ben_gua"]["name"]


# ---------- 1. 各字数档都要能起卦（不许 NameError／崩） ----------

@pytest.mark.parametrize("text", ["明", "雷风", "天地人", "天地玄黄", "今日动静如何",
                                  "一二三四五六七八九十十一"])
def test_every_length_bucket_casts(text):
    r = engine.divine_text(text)
    assert r["ben_gua"]["name"], f"{text}（{len(text)} 字）起不出卦"
    assert 1 <= r["moving_yao"]["position"] <= 6


def test_four_char_bucket_does_not_crash_without_zi_mode():
    """四字档要走 random 分支——曾经因为没 import random 直接 NameError。"""
    for _ in range(6):
        assert _gua("天地玄黄")


def test_no_hanzi_falls_back_to_time():
    r = engine.divine_text("123")
    assert r["method"] == "time"
    assert "zi_fallback" in r["method_params"]


# ---------- 2. 四字档：传 zi_mode 才稳定，两法不同卦 ----------

def test_four_char_is_random_without_zi_mode_but_two_modes_differ():
    tone = {_gua("天地玄黄", "tone") for _ in range(5)}
    stroke = {_gua("天地玄黄", "stroke") for _ in range(5)}
    assert len(tone) == 1 and len(stroke) == 1, "同一 zi_mode 必须稳定"
    assert tone != stroke, "声调／笔画两法应给出不同的卦（底本两法并列，故需固定其一）"


def test_unknown_zi_mode_is_ignored_not_crashed():
    assert _gua("天地玄黄", "乱写") in (_gua("天地玄黄", "tone"), _gua("天地玄黄", "stroke"))


# ---------- 3. 接口层：zi_mode 必须真的传下去 ----------

@pytest.mark.parametrize("mode", ["tone", "stroke"])
def test_endpoint_passes_zi_mode_through(mode):
    resp = client.post("/api/meihua/divine", json={
        "method": "duozi", "params": {"text": "天地玄黄", "zi_mode": mode},
        "user_input": "天地玄黄", "ai": False,
    })
    assert resp.status_code == 200, resp.text[:200]
    first = json.loads(resp.text.split("\n")[0][6:])
    g = first.get("data", first)
    assert (g.get("method_params") or {}).get("zi_mode") == mode, "zi_mode 没有传到引擎"
    # 同一个 zi_mode 连发两次必须同卦（这就是"先要卦、再 AI 解卦"要保证的事）
    resp2 = client.post("/api/meihua/divine", json={
        "method": "duozi", "params": {"text": "天地玄黄", "zi_mode": mode},
        "user_input": "天地玄黄", "ai": False,
    })
    g2 = json.loads(resp2.text.split("\n")[0][6:]).get("data", {})
    assert g2["ben_gua"]["name"] == g["ben_gua"]["name"]
    assert g2["moving_yao"]["position"] == g["moving_yao"]["position"]
