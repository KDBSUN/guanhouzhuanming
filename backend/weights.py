# -*- coding: utf-8 -*-
"""
权重集中配置加载器（weights.yaml）
==================================
把数值标定从代码硬编码迁入集中配置，带版本号；每个数值在 yaml 中
带双行注释：序关系典籍出处 + "工程默认值，未经案例校准"的诚实标注。
加载失败时回落到内置默认值（与 yaml 当前内容一致），保证引擎永不因配置损坏而停摆。
"""
from pathlib import Path

_WEIGHTS_PATH = Path(__file__).parent / "weights.yaml"

# 回落默认值（与 weights.yaml 保持同步；修改权重请改 yaml，勿改此处）
FALLBACK = {
    "version": "1.3.0",
    "shiwang_weight": {"旺": 1.0, "相": 0.8, "休": 0.5, "囚": 0.3, "死": 0.2},
    "strong_threshold": 0.5,
    "zeri_yi_states": ["旺", "相"],
    # M=30（2026-09-18 yaml 已改；回落表漏同步，2026-09-23 补平）
    "zeri_days": {"S": 7, "M": 30, "L": 30},
    "flow_thresholds": {
        "state_jiruo_max": 1.0, "state_weak_max": 3.0, "state_strong_min": 6.0,
        "chengwu_margin": 1.0, "month_boost_wang": 1.0, "month_boost_xiang": 0.5,
        "hidden_qi_weights": {"本气": 1.0, "中气": 0.6, "余气": 0.4},
        "boundary_band": 0.3,
    },
    "calibration": {
        "min_samples": 5, "min_same_direction": 4,
        "max_delta_ratio": 0.3, "flip_rate_threshold": 0.6,
    },
    # 梅花应期的加权与门槛（原先硬编码在应期模块里；此处与 weights.yaml 保持同步）
    "yingqi": {
        "weights": {"month": 0.80, "day": 0.15, "year": 0.025, "hour": 0.025},
        "gate": 0.45,
        "month_states": {"旺": 1.0, "相": 0.7, "休": 0.4, "囚": 0.2, "死": 0.1},
        "other_states": {"同": 1.0, "生": 0.7, "泄": 0.3, "我克": 0.3, "被克": 0.1},
    },
    # 八字取用裁决（H5）：火土旺极/重逢的工程默认门槛（书证与层级见 docs/调候与改方书证登记.md）
    "xiji": {"huo_tu_wangji_min": 6},
}


def load_weights() -> dict:
    try:
        import yaml
        with open(_WEIGHTS_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or "version" not in data:
            raise ValueError("weights.yaml 缺少 version")
        return data
    except Exception:
        return dict(FALLBACK)


_W = load_weights()

WEIGHTS_VERSION: str = _W.get("version", FALLBACK["version"])
SHIWANG_WEIGHT: dict = _W.get("shiwang_weight", FALLBACK["shiwang_weight"])
STRONG_THRESHOLD: float = float(_W.get("strong_threshold", FALLBACK["strong_threshold"]))
ZERI_YI_STATES: list = _W.get("zeri_yi_states", FALLBACK["zeri_yi_states"])
ZERI_DAYS: dict = _W.get("zeri_days", FALLBACK["zeri_days"])
FLOW: dict = _W.get("flow_thresholds", FALLBACK["flow_thresholds"])
CALIBRATION: dict = _W.get("calibration", FALLBACK["calibration"])
# 梅花应期的加权与门槛（应期模块从这里读；改这些数请改 yaml 并升版本）
YINGQI: dict = _W.get("yingqi", FALLBACK["yingqi"])
# 八字取用裁决（H5）：火土旺极/重逢门槛（书证与层级见 docs/调候与改方书证登记.md）
XIJI: dict = _W.get("xiji", FALLBACK["xiji"])
