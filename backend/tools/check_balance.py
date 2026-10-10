# -*- coding: utf-8 -*-
"""
余额告警脚本（自检清单 D4）
==========================
用法：
    python tools/check_balance.py            # 余额正常则静默退出 0；偏低/查询失败 → 打印原因并退出 1
    python tools/check_balance.py -v         # 总是打印一行状态

挂到定时任务（任选其一）：
    Linux  crontab：  0 */6 * * *  cd /path/backend && /usr/bin/python3 tools/check_balance.py || \
                                     echo "余额告警" | mail -s "[易占] LLM 余额告警" 你的邮箱
    systemd timer：   见 docs/上线自检与兜底.md 里的 unit 片段
    Windows 任务计划：程序 python，参数 tools/check_balance.py，起始于 backend 目录

为什么要脚本而不是"靠时不时的自觉"：余额耗尽时全站 AI 直接挂（起卦只剩排盘、断语全 empty），
而这件事只有主动查才知道——用户不会来告诉你，他们直接走。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from dotenv import load_dotenv  # noqa: E402

# 与 main.py 同一套配置加载方式：backend/.env
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from health import llm_balance, low_balance_warning  # noqa: E402


def main() -> int:
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    b = llm_balance(force=True)
    warn = low_balance_warning()
    if verbose or warn:
        cur = b.get("currency") or ""
        total = b.get("total")
        state = "正常" if not warn else "告警"
        print(f"[{state}] LLM 余额：{total} {cur} | 模型 {b.get('model') or '-'} | {warn or 'ok'}")
    return 1 if warn else 0


if __name__ == "__main__":
    raise SystemExit(main())
