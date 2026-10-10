# -*- coding: utf-8 -*-
"""
夏令时（夏时制）还原回归：1986–1991 六年区间逐年核对
======================================================
**核实时点**：2026-09-23。核实结论：`bazi_engine.china_dst_window_clock` 的六年区间
与 IANA 时区库逐年一致，无偏差（此前无人核对过，本文件把六年区间钉死，防漂移）。

证据链（两级，均为外部原始资料）：
1. **国务院通知原文**（经 IANA tz 邮件列表 tz@iana.org「China DST」一帖逐条给出公报页码）：
   · 1986-04-12 通知（浙江省政府公报 1986 年第 8 期 p.21-22）：
     自 1986 年起实行夏时制，「5 月 4 日 2 时拨快一小时」「9 月 14 日 2 时拨回一小时」；
   · 1987-02-15 通知（国务院公报 1987 年第 3 期 p.114）：1987 年 4 月 12 日起至 9 月 13 日止；
   · 1987-09-09 通知（国务院公报 1987 年第 21 期 p.709）：
     **自 1988 年起**，每年「四月中旬第一个星期日 2 时」起至「九月中旬第一个星期日 2 时」止；
   · 1992-03-03 通知（国务院公报 1992 年第 5 期 p.152）：自 1992 年起暂停夏时制。
   · **1988 年起日为 4 月 17 日**（不是「四月中旬第一个星期日」字面所推的 4 月 10 日）：
     见《人民日报》1988-04-12 头版公告；tz 库因此把规则写成 `Apr Sun>=11`。
2. **IANA tzdata 2026d（Asia/Shanghai）跃变实测**（2026-09-23 用 tzdata 2026.4 wheel 逐分钟扫描得出）：
     1986-05-04 02:00→03:00 起 ／ 1986-09-14 02:00→01:00 止
     1987-04-12 起 ／ 1987-09-13 止
     1988-04-17 起 ／ 1988-09-11 止
     1989-04-16 起 ／ 1989-09-17 止
     1990-04-15 起 ／ 1990-09-16 止
     1991-04-14 起 ／ 1991-09-15 止
   与本引擎输出逐年一致。

口径（本引擎）：
  · 用户填的是**钟表时间**；落在夏时制区间内 → 减 1 小时得法定标准时间，再走
    经度校正、均时差（校时顺序见 build_bazi_paipan docstring）。
  · 起日 02:00–02:59 是**尚未拨快**的标准钟点，不还原；止日 02:00 已拨回，也不还原。
  · 止日 01:00–01:59 这个钟点在现实中出现两次（夏令时一次、拨回后标准时一次），
    不可避免有歧义；本引擎按**先出现的那次**（夏令时读数）处理，即减 1 小时。
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bazi_engine import _restore_dst, build_bazi_paipan, china_dst_window_clock  # noqa: E402

# tzdata 2026d（Asia/Shanghai）实测区间，夏令时钟表：
# (年起日 03:00（＝标准 02:00 拨快后）, 年止日 02:00)
TZDB_WINDOWS = {
    1986: ("1986-05-04 03:00", "1986-09-14 02:00"),
    1987: ("1987-04-12 03:00", "1987-09-13 02:00"),
    1988: ("1988-04-17 03:00", "1988-09-11 02:00"),
    1989: ("1989-04-16 03:00", "1989-09-17 02:00"),
    1990: ("1990-04-15 03:00", "1990-09-16 02:00"),
    1991: ("1991-04-14 03:00", "1991-09-15 02:00"),
}


def _win(year):
    w = china_dst_window_clock(year)
    if w is None:
        return None
    return (w[0].strftime("%Y-%m-%d %H:%M"), w[1].strftime("%Y-%m-%d %H:%M"))


def test_windows_match_iana_tzdb_year_by_year():
    """六年区间逐年与 tzdata 2026d 一致（这是本次核实的核心断言）"""
    for year, want in TZDB_WINDOWS.items():
        assert _win(year) == want, f"{year} 年区间与 IANA tzdb 不符：{_win(year)} ≠ {want}"


def test_only_1986_to_1991_has_dst():
    """区间之外（1985、1992 及以后）无夏时制——《1992-03-03 通知》自 1992 年起暂停"""
    for year in (1900, 1949, 1985, 1992, 1993, 2000, 2026):
        assert china_dst_window_clock(year) is None


def test_1986_is_the_special_case_not_the_general_rule():
    """1986 是特例：国务院 1986-04-12 通知定的就是 5 月 4 日，
    不是「四月中旬第一个星期日」（那年 4 月中旬第一个星期日是 4 月 13 日）"""
    start, _end = china_dst_window_clock(1986)
    assert (start.month, start.day) == (5, 4)


def test_1988_start_is_april_17_not_april_10():
    """1988 年起日按《人民日报》1988-04-12 头版公告为 4 月 17 日。

    这条单独钉死，是因为「四月中旬第一个星期日」按字面（Sun>=10）推会得 4 月 10 日，
    tz 库用的是 `Sun>=11`（得 4 月 17 日）。若有人照字面「顺手改正」，本断言会立刻报警。
    """
    start, _end = china_dst_window_clock(1988)
    assert (start.month, start.day) == (4, 17)
    # 4 月 10 日–16 日一律**不得**还原（这一周是最容易被误还原的窗口）
    for day in range(10, 17):
        r = _restore_dst(1988, 4, day, 10, 0)
        assert r["applied"] is False, f"1988-04-{day} 不该还原"


@pytest.mark.parametrize("y,m,d,h,mi", [
    (1988, 4, 12, 10, 0),    # 起日前（这一周钟表仍是标准时）
    (1988, 4, 17, 2, 30),    # 起日 02:30：尚未拨快
    (1988, 9, 11, 2, 0),     # 止日 02:00：已拨回
    (1986, 5, 4, 2, 30),     # 1986 特例起日 02:30
    (1985, 7, 1, 10, 0),     # 无夏时制年份
    (1992, 7, 1, 10, 0),
])
def test_no_restore_outside_the_dst_window(y, m, d, h, mi):
    assert _restore_dst(y, m, d, h, mi)["applied"] is False


@pytest.mark.parametrize("y,m,d,h,mi,restored", [
    (1988, 4, 17, 3, 0, "1988年4月17日 02:00"),     # 起日 03:00 起（＝标准 02:00）
    (1988, 9, 11, 1, 30, "1988年9月11日 00:30"),    # 止日 01:30（夏令时读数，取先出现的那次）
    (1986, 5, 4, 3, 0, "1986年5月4日 02:00"),
    (1990, 7, 15, 12, 0, "1990年7月15日 11:00"),
])
def test_restore_subtracts_one_hour_inside_window(y, m, d, h, mi, restored):
    r = _restore_dst(y, m, d, h, mi)
    assert r["applied"] is True
    assert r["restored"] == restored


def test_paipan_moves_hour_pillar_and_can_cross_the_day():
    """端到端：1988-07-01（夏令时内）01:30 → 还原 00:30 → 时柱由丑变子；
    00:30 → 还原前一日 23:30 → 日柱也随之后退一位。不勾选则一律不动。"""
    off = build_bazi_paipan(1988, 7, 1, 1, 30, dst=False)
    on = build_bazi_paipan(1988, 7, 1, 1, 30, dst=True)
    assert off["bazi"][3]["ganzhi"] != on["bazi"][3]["ganzhi"]
    assert on["dst"]["applied"] is True and on["solar"] == "1988年7月1日 00:30"

    off2 = build_bazi_paipan(1988, 7, 1, 0, 30, dst=False)
    on2 = build_bazi_paipan(1988, 7, 1, 0, 30, dst=True)
    assert on2["dst"]["applied"] is True and on2["solar"] == "1988年6月30日 23:30"
    assert off2["bazi"][2]["ganzhi"] != on2["bazi"][2]["ganzhi"]


def _shanghai_tz():
    """有 tzdata 时才做活体交叉核对；没装则跳过（不写成硬依赖）。"""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Shanghai")
    except Exception:
        return None


def test_cross_check_against_installed_tzdata():
    """活体交叉核对：装了 tzdata 的机器上，用 zoneinfo 直接验四个钟点的 UTC 偏移。

    · 起日 03:00 → +09:00（已拨快）
    · 止日 01:59 → +09:00（夏令时一侧，fold=0 取先出现的那次）
    · 止日 02:00 → +08:00（已拨回）
    · 起日前一天 12:00 → +08:00
    """
    tz = _shanghai_tz()
    if tz is None:
        pytest.skip("本机无 tzdata/zoneinfo 数据，跳过活体交叉核对（区间已由 TZDB_WINDOWS 钉死）")
    for year, (start_s, end_s) in TZDB_WINDOWS.items():
        start = datetime.strptime(start_s, "%Y-%m-%d %H:%M")
        end = datetime.strptime(end_s, "%Y-%m-%d %H:%M")
        assert start.replace(tzinfo=tz).utcoffset() == timedelta(hours=9), start
        assert (end - timedelta(minutes=1)).replace(tzinfo=tz).utcoffset() == timedelta(hours=9), end
        assert end.replace(tzinfo=tz).utcoffset() == timedelta(hours=8), end
        before = (start - timedelta(days=1)).replace(hour=12, minute=0)
        assert before.replace(tzinfo=tz).utcoffset() == timedelta(hours=8), before
