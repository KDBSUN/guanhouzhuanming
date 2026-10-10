# -*- coding: utf-8 -*-
"""
处方五行 R（Remedy）——梅花易数
================================
把"体卦/用卦"封装为命局校验唯一入口的归一化输出：

  X        = 用卦五行（事体核心五行）
  R        = 为促成当前之事、此刻最应强化或引入的五行
  态势标签 = 体用五态（比和 / 用生体 / 体生用 / 体克用 / 用克体）

R 由体用生克推出（不以用神本卦五行直接比八字，避免误报）：
  用生体（吉）→ R = 用（顺其生势，维持"用生体"）
  体克用（吉）→ R = 体（我方掌控，强化体）
  比和（吉）  → R = 体 = 用
  体生用（泄）→ R = 生体者（帮扶体，补体之母）
  用克体（凶）→ R = 克用者（制用 / 通关，化解"用克体"）

依赖 wuxing_relation 中的 SHENG/KE 关系。
"""
from wuxing_relation import SHENG, KE, WUXING, sheng_me, ke_me

STATE_DESC = {
    "比和": "体用比和，百事顺遂",
    "用生体": "用生体，有进益之喜",
    "体生用": "体生用，有耗失之患",
    "体克用": "体克用，诸事可成但需费劲",
    "用克体": "用克体，诸事不利，宜守不宜攻",
}


def meihua_remedy(ti_wuxing: str, yong_wuxing: str, relation: str,
                  hu_wuxing=None, bian_wuxing=None, ti_status=None) -> dict:
    """
    ti_wuxing / yong_wuxing：体、用卦五行
    relation：体用五态之一（比和/用生体/体生用/体克用/用克体）
    hu_wuxing / bian_wuxing：互卦、变卦五行列表（《体用总诀》：他卦即用、互、变三卦）
    ti_status：体卦卦气旺衰（旺/相/休/囚/死，据《心易衰旺之诀》）

    R 规则（书证）：
      用克体（凶）→ R=克用者（制用）；变卦又克体→R_alt=克变者（防末后之凶）
      变卦克体 → R=克变者（"变卦克体，事于末后必有不吉"）
      体失令衰 → R=生体者（"体衰而有生体之卦则衰稍解"）
      体生用（泄）→ R=生体者
      用生体（吉）→ R=用（用即生体者，顺其生势）
      体克用（吉）→ R=体；比和 → R=体
    """
    if ti_wuxing not in WUXING or yong_wuxing not in WUXING:
        raise ValueError(f"非法五行: 体={ti_wuxing!r} 用={yong_wuxing!r}")
    hu_wuxing = hu_wuxing or []
    bian_wuxing = bian_wuxing or []

    X = yong_wuxing   # 事体核心五行 = 用卦五行
    notes = []
    R_alt = None

    def hu_note():
        for h in hu_wuxing:
            if SHENG[h] == ti_wuxing:
                notes.append(f"互卦【{h}】生体，中间渐有转机（互乃中间之应）")
                return

    if relation == "用克体":
        R = ke_me(yong_wuxing)
        reason = f"用克体为凶（《体用总诀》），取克用者【{R}】制用通关"
        hu_note()
        for b in bian_wuxing:
            if SHENG[b] == ti_wuxing:
                notes.append(f"变卦【{b}】生体，末后有救")
            elif KE[b] == ti_wuxing:
                notes.append(f"变卦【{b}】亦克体，末后尤凶")
                R_alt = ke_me(b)
    elif any(KE[b] == ti_wuxing for b in bian_wuxing):
        b = next(b for b in bian_wuxing if KE[b] == ti_wuxing)
        R = ke_me(b)
        reason = f"变卦【{b}】克体，事于末后不吉（《体用总诀》），取克变者【{R}】制变"
        hu_note()
    elif ti_status in ("休", "囚", "死"):
        R = sheng_me(ti_wuxing)
        reason = f"体卦失令（{ti_status}），取生体者【{R}】扶体（《衰旺之诀》：体衰而有生体之卦则衰稍解）"
        hu_note()
    elif relation == "体生用":
        R = sheng_me(ti_wuxing)
        reason = f"体生用为泄（有耗失之患），取生体者【{R}】帮扶体"
        hu_note()
    elif relation == "用生体":
        R = yong_wuxing
        reason = "用生体为吉（有进益之喜），顺其生势，维持用生体"
        hu_note()
    elif relation == "体克用":
        R = ti_wuxing
        reason = "体克用为吉（诸事吉），我方掌控，强化体"
        hu_note()
    else:  # 比和
        R = ti_wuxing
        reason = "体用比和，百事顺遂，R 取体用本气"

    return {
        "X": X,
        "R": R,
        "R_alt": R_alt,
        "R_reason": reason,
        "state": relation,
        "state_desc": STATE_DESC.get(relation, ""),
        "notes": notes,
    }


if __name__ == "__main__":
    for rel, tw, yw in [("用克体", "木", "金"), ("体生用", "木", "火"),
                        ("用生体", "木", "水"), ("体克用", "金", "木"),
                        ("比和", "木", "木")]:
        r = meihua_remedy(tw, yw, rel)
        print(f"体{tw} 用{yw} [{rel}] -> X={r['X']} R={r['R']} | {r['R_reason']}")
