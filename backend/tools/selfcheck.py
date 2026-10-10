# -*- coding: utf-8 -*-
"""
上线自检（可在本机跑，也可对着已部署的域名跑）
==============================================
一次运行把"本地永远测不出来"的几项验掉：

  B7 时区        —— 错一天会静默算错黄历/择日/应期/岁运，看代码看不出来
  B4/B5 代理头   —— **实测**伪造 X-Forwarded-For 能不能让限流按假 IP 分桶
  B3 CORS        —— 是否仍为通配（通配 = 任意网站能用访客浏览器烧你的 LLM 余额）
  D4 余额        —— 余额耗尽 = 全站 AI 直接挂
  D6 配额        —— 今日是否已进入"仅排盘不解卦"的降级态

用法：
    python tools/selfcheck.py                          # 本机后端（默认 127.0.0.1:8000）
    python tools/selfcheck.py --base https://你的域名    # 线上（经 nginx，这才是真正要测的）
    python tools/selfcheck.py -v                       # 打印每项细节
退出码：0 = 全部通过；1 = 有硬失败（可接 cron/CI，与 check_balance.py 同约定）

## 为什么 XFF 那一项必须实测，而不能只看配置

限流按什么分桶，取决于**两层**叠加，而配置里只看得到一层：
  ① uvicorn 的 `--proxy-headers`（**默认开**）会在进应用之前把 `request.client`
     改写成请求里带的 XFF；
  ② 应用层 `TRUST_PROXY` 决定要不要自己读那个头。
只要 ① 开着，② 写"不信任"也是白写——应用拿到的已经是假 IP 了。
光读配置永远发现不了这件事，所以这里**发真的请求、数真的 429**。

## 判定表（本工具的核心逻辑）

用一个便宜端点（默认 `/api/meihua/waijing`，60 次/分钟、不调 LLM、不写库）
连发 K 个**互不相同**的伪造 XFF：

| app_trust_proxy | 结果 | 判定 |
|---|---|---|
| False | 出现 429（只有一个桶） | ✅ 直连公网的正确形态 |
| False | 一个 429 都没有（每个假 IP 各自成桶） | ❌ **限流可被伪造绕过**（uvicorn 改写了 client） |
| True  | 出现 429 | ✅ 说明请求确实经过了一个会**覆写** XFF 的代理 |
| True  | 一个 429 都没有 | ⚠ 直连后端时无法判定（TRUST_PROXY 本就依赖前置代理）；**请用 --base 域名 复测**，域名侧仍如此即为 ❌ |

注意最后两行的区别：`TRUST_PROXY=1` 时，绕过 nginx 直连后端发假头，分桶当然会按假头走
——这是该模式的既定前提，不是本站的漏洞。所以那种情况给"警告+复测指引"，不给"失败"，
免得把唯一正确的部署形态误报成红的。
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Windows 控制台默认是 GBK，而这个工具的输出几乎全是中文——不重设就会印成一堆乱码，
# 让人以为工具坏了。改成 UTF-8 输出（Windows Terminal / VS Code 终端都正常显示）。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # 便于 import health/quota

# 测试靶点：限流 60/分钟 + 不调 LLM + 不写库，是"能安全被打"的最便宜端点
PROBE_PATH = "/api/meihua/waijing"
PROBE_BODY = {"ti_wuxing": "木", "omen": ["雨"]}
PROBE_LIMIT = 60                 # 与 main.py 里 rate_limit(..., "waijing", 60, 60) 对齐
PROBE_N = PROBE_LIMIT + 10       # 多发几个，确保必定越过阈值

OK, FAIL, WARN, SKIP = "OK", "FAIL", "WARN", "SKIP"
_results: list = []


def _say(level: str, name: str, detail: str = "") -> None:
    _results.append((level, name, detail))
    icon = {OK: "[通过]", FAIL: "[失败]", WARN: "[注意]", SKIP: "[跳过]"}[level]
    print("%s %s%s" % (icon, name, ("  —— " + detail) if detail else ""))


def _get(base: str, path: str, xff: str = "", timeout: float = 15.0) -> tuple:
    """返回 (status, json_or_text)。不抛异常——自检工具自己不该崩。"""
    req = urllib.request.Request(base.rstrip("/") + path, headers={"Accept": "application/json"})
    if xff:
        req.add_header("X-Forwarded-For", xff)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return 0, "%s: %s" % (type(e).__name__, e)


def _post_probe(base: str, xff: str, timeout: float = 15.0) -> int:
    """打一次靶点，返回状态码（0 = 连不上）。"""
    data = json.dumps(PROBE_BODY).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + PROBE_PATH, data=data, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "X-Forwarded-For": xff})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
            return r.status
    except urllib.error.HTTPError as e:
        e.read()
        return e.code
    except Exception:
        return 0


# ============================================================
# 各项检查
# ============================================================
def check_timezone(health: dict, verbose: bool) -> None:
    tz = (health or {}).get("timezone") or {}
    if not tz:
        _say(FAIL, "B7 时区", "健康检查未返回 timezone 字段（后端版本过旧？）")
        return
    if verbose:
        print("      tzname=%s  UTC%+s  local=%s  beijing=%s"
              % (tz.get("tzname"), tz.get("utc_offset_hours"), tz.get("local"), tz.get("beijing")))
    if tz.get("ok"):
        if tz.get("date_differs"):
            _say(WARN, "B7 时区", "偏移正确但本地日期与北京日期不同——查系统时钟/tzdata：%s vs %s"
                 % (str(tz.get("local"))[:10], str(tz.get("beijing"))[:10]))
        else:
            _say(OK, "B7 时区", "%s（UTC%+.1f）" % (tz.get("tzname") or "?", float(tz.get("utc_offset_hours") or 0)))
    else:
        _say(FAIL, "B7 时区", tz.get("warning") or "不是 +08:00；修复：timedatectl set-timezone Asia/Shanghai")


def check_cors(health: dict, verbose: bool) -> None:
    cors = (health or {}).get("cors") or {}
    if verbose:
        print("      origins=%s  wildcard=%s  trust_proxy=%s"
              % (cors.get("origins"), cors.get("wildcard"), cors.get("trust_proxy")))
    if cors.get("wildcard"):
        _say(FAIL, "B3 CORS", cors.get("warning") or "仍为通配符：任意网站能用访客浏览器调用本站 API")
    elif not cors.get("origins"):
        _say(WARN, "B3 CORS", "未放行任何来源——若已上线请确认 .env 的 CORS_ORIGINS 填了域名")
    else:
        _say(OK, "B3 CORS", "已收紧到 %d 个来源" % len(cors.get("origins") or []))


def check_balance(health: dict, verbose: bool) -> None:
    llm = (health or {}).get("llm") or {}
    if verbose:
        print("      configured=%s ok=%s total=%s low=%s"
              % (llm.get("configured"), llm.get("ok"), llm.get("total"), llm.get("low")))
    if not llm.get("configured"):
        _say(FAIL, "D4 余额", "未配置 LLM_API_KEY：全站 AI 不可用")
    elif not llm.get("ok"):
        _say(WARN, "D4 余额", "查询失败（%s）——可能密钥失效或网络不通" % llm.get("error"))
    elif not llm.get("available", True):
        _say(FAIL, "D4 余额", "账户不可用（余额 %s）——AI 功能会全部失败" % llm.get("total"))
    elif llm.get("low"):
        _say(WARN, "D4 余额", "偏低：%s %s（低于 %s）" % (llm.get("total"), llm.get("currency"), llm.get("warn_below")))
    else:
        _say(OK, "D4 余额", "%s %s" % (llm.get("total"), llm.get("currency")))


def check_quota(health: dict, verbose: bool) -> None:
    q = (health or {}).get("quota") or {}
    if verbose:
        print("      day=%s used=%s soft=%s hard=%s ip_limit=%s"
              % (q.get("day"), q.get("used"), q.get("soft_limit"), q.get("hard_limit"), q.get("ip_limit")))
    if q.get("error"):
        _say(WARN, "D6 配额", "读取失败：%s" % q.get("error"))
    elif q.get("degraded"):
        _say(WARN, "D6 配额", "今日已进入「仅排盘不解卦」（已用 %s/%s，%s 恢复）"
              % (q.get("used"), q.get("hard_limit"), q.get("resets_at")))
    else:
        _say(OK, "D6 配额", "已用 %s/%s（软阈值 %s，单 IP %s）"
              % (q.get("used"), q.get("hard_limit"), q.get("soft_limit"), q.get("ip_limit")))


def check_proxy_and_buckets(base: str, health: dict, verbose: bool) -> None:
    """B4/B5 合并：先看应用怎么认 XFF，再用真实请求数 429。"""
    forged = "203.0.113.7"                       # TEST-NET-3，保留给文档/示例用，不会撞真 IP
    _, with_xff = _get(base, "/api/health", xff=forged)
    pc = (with_xff or {}).get("proxy_check") or {} if isinstance(with_xff, dict) else {}
    trusted = bool(pc.get("app_trust_proxy"))
    rewritten = bool(pc.get("uvicorn_rewrote_client"))
    if verbose:
        print("      伪造 XFF=%s → client_seen=%s  app_trust_proxy=%s  uvicorn_rewrote_client=%s"
              % (forged, pc.get("client_seen"), trusted, rewritten))

    if pc.get("warning"):
        _say(FAIL, "B4 代理头", pc["warning"])
    elif rewritten:
        _say(FAIL, "B4 代理头", "uvicorn 正在替我们信任 XFF（client_seen 被改写为 %s）" % pc.get("client_seen"))
    else:
        _say(OK, "B4 代理头", "uvicorn 未改写 client（client_seen=%s）；TRUST_PROXY=%s"
              % (pc.get("client_seen"), trusted))

    # --- 真实分桶实测 ---
    ips = ["198.51.100.%d" % (i + 1) for i in range(PROBE_N)]   # TEST-NET-2 段，逐个不同
    with ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(lambda ip: _post_probe(base, ip), ips))
    n429 = sum(1 for c in codes if c == 429)
    nerr = sum(1 for c in codes if c == 0)
    if verbose:
        print("      靶点 %s：发出 %d 次（%d 个不同假 XFF）→ 429×%d，连不上×%d"
              % (PROBE_PATH, len(codes), len(ips), n429, nerr))

    if nerr == len(codes):
        _say(SKIP, "B5 分桶实测", "靶点全部连不上，无法实测（确认服务在跑、路径与上限未改）")
        return
    if nerr:
        _say(WARN, "B5 分桶实测", "有 %d 次连不上，结果仅供参考" % nerr)

    if n429 > 0:
        _say(OK, "B5 分桶实测", "伪造 %d 个假 IP 后仍只有一个桶（429×%d）——限流不可被假头绕过" % (len(ips), n429))
    elif trusted:
        _say(WARN, "B5 分桶实测",
             "每个假 IP 各自成桶：TRUST_PROXY=1 时这是**绕过代理直连后端**的既定表现，"
             "本身不算漏洞。请用 `--base https://你的域名` 从域外侧复测；那边仍如此，就是 nginx 没覆写 XFF")
    else:
        _say(FAIL, "B5 分桶实测",
             "伪造 %d 个假 IP 后**一个 429 都没有**——每个假头都开了新桶，"
             "限流形同不存在。修复：uvicorn 用 --no-proxy-headers 启动" % len(ips))


def main() -> int:
    ap = argparse.ArgumentParser(description="上线自检（时区/代理头/CORS/余额/配额）")
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="后端或站点根地址")
    ap.add_argument("--skip-bucket", action="store_true",
                    help="跳过分桶实测（它会在靶点上打满一分钟额度）")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    print("=" * 72)
    print("上线自检  base=%s" % base)
    print("=" * 72)

    status, health = _get(base, "/api/health")
    if not isinstance(health, dict) or not health.get("ok"):
        print("[失败] 无法读取 %s/api/health（HTTP %s）：%s" % (base, status, str(health)[:200]))
        return 1

    check_timezone(health, args.verbose)
    check_cors(health, args.verbose)
    check_balance(health, args.verbose)
    check_quota(health, args.verbose)
    if args.skip_bucket:
        _say(SKIP, "B4/B5 代理头与分桶", "--skip-bucket")
    else:
        check_proxy_and_buckets(base, health, args.verbose)

    n_fail = sum(1 for lv, _, _ in _results if lv == FAIL)
    n_warn = sum(1 for lv, _, _ in _results if lv == WARN)
    print("-" * 72)
    print("结果：通过 %d · 注意 %d · 失败 %d"
          % (sum(1 for lv, _, _ in _results if lv == OK), n_warn, n_fail))
    if n_fail:
        print("有硬失败项，请按上面的提示处理后重跑。")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
