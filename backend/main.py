"""
梅花易数 FastAPI 后端
POST /api/meihua/divine  — 起卦+解卦
"""
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Optional

# 自动加载 .env 文件
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[meihua] Loaded config from {env_path}")
except ImportError:
    pass  # python-dotenv 未安装时忽略，用系统环境变量

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.formparsers import MultiPartException   # 表单解析失败/部件超限（换成人话再回前端）
from pydantic import BaseModel

import asr       # 语音转文字客户端：供应商由 .env 决定，换家不用改代码（见 asr.py）
from engine import (
    divine_yizi, divine_erzi, divine_duozi,
    divine_time, divine_shuzi, divine_manual, load_data as load_meihua_data
)
from intent import recognize_intent
from liuyao_engine import build_paipan
from bazi_engine import build_bazi_paipan, lunar_meta, lunar_to_solar
import dayun_detail                # 大运流年详批（事业/财运/感情）确定性引擎
from wuxing_relation import adjudicate, redirect
from remedy import meihua_remedy
from liuyao_remedy import liuyao_remedy, classify_yongshen_detail
import liuyao_patterns
from liuyao_liushou import prompt_block as liushou_prompt_block
import yaoci_zhu       # 动爻爻辞注释（逐词训诂，有出处；AI 只许照此解释字义）
from mingju_profile import save_profile, get_profile, delete_profile, compute_baseline, export_profile, import_profile
from liunian import current_liunian, liunian_overlay
from zeri import date_table
from yingqi import meihua_yingqi, liuyao_yingqi
from decision_log import append_check, set_feedback, recent, flow_of, outcomes as log_outcomes
from terminology import meta as term_meta, list_terms as term_list, get_term as term_get, search as term_search
from bazi_records import add_record as bazi_rec_add, list_records as bazi_rec_list, delete_record as bazi_rec_delete
from records import (add as rec_add, list_all as rec_list, get as rec_get,
                     update as rec_update, remove as rec_remove,
                     list_deleted as rec_list_deleted, restore as rec_restore,
                     purge as rec_purge, empty_trash as rec_empty_trash,
                     export_all as rec_export_all, import_all as rec_import_all,
                     TRASH_DAYS as rec_trash_days)
from book_quotes import lookup_many
from rules_meta import RULES_VERSION
from weights import WEIGHTS_VERSION
import waijing
from wuxing_suggest import suggest_wuxing
from wuxing_flow import flow_plan
from feedback import (build_claims, boundary_samples_of, analyze_calibration,
                      recent_for_feedback, calibration_view, save_verdict,
                      VERDICTS as FEEDBACK_VERDICTS)
from decision_log import (add_boundary_samples, add_beta_note, list_beta_notes,
                          decide_proposal, claims_of, feedback_of, get_log,
                          export_all as log_export_all, import_all as log_import_all,
                          issue_receipt, resolve_receipt)
from mailer import configured as mail_configured, feedback_note_mail, claim_verdict_mail, send as mail_send
from health import (snapshot as health_snapshot, low_balance_warning,
                    timezone_warning, timezone_info)
import quota                     # 每日配额与优雅降级（防刷 · 成本护栏），阈值见该模块头
import llm_providers             # 自带 key 解卦的厂商预设名单（地址由服务端写死，防 SSRF）
from fastapi.concurrency import run_in_threadpool
from tiering import resolve_tier, tier_directive
from aicheck import review as ai_review, summarize
from aicheck import extract_dates as ai_extract_dates

app = FastAPI(title="梅花易数 API", version="1.0.0")

# ============================================================
# CORS：默认只放行本机开发端口，上线必须显式声明自己的域名
# ============================================================
# 为什么不能留 ["*"]：配合 allow_credentials，任意网页都能拿访客浏览器当代理
# 直接打这里的 /api/meihua/divine 之类的端点——烧的是站长的 LLM 余额
# （限流按 IP 分桶，挡不住"很多访客各刷一点"）。
# 配置：backend/.env 里写 CORS_ORIGINS=https://你的域名,https://www.你的域名
# （多个用英文逗号分隔；本机开发端口已内置在默认值里，不用写）
_DEFAULT_ORIGINS = [
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:5173", "http://127.0.0.1:5173",
]
_cors_env = (os.environ.get("CORS_ORIGINS") or "").strip()
CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()] or _DEFAULT_ORIGINS
# 通配符只允许在不带凭据时使用（浏览器规范如此）；这里显式禁止通配符，
# 免得"以为配了域名、其实写了个 *"这种上线事故。
CORS_ALLOW_ALL = "*" in CORS_ORIGINS
if CORS_ALLOW_ALL:
    logging.getLogger("uvicorn.error").warning(
        "[CORS] CORS_ORIGINS 含 '*'：任意网站都能用访客浏览器调用本站 API（会烧 LLM 余额）。"
        "上线请改为自己的域名。"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=not CORS_ALLOW_ALL,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health(request: Request, balance: bool = True):
    """健康检查（自检清单 D）：余额/ASR/SMTP/CORS/库规模一眼看清。不含任何密钥。

    用法：上线后 `curl https://域名/api/health`；也可把它接到你的探活/告警里。
    余额低于阈值时返回的 llm.low=true（配套定时脚本见 tools/check_balance.py）。

    另含 proxy_check：**实测 uvicorn 是否在替我们信任 X-Forwarded-For**。
    这件事的坑（已实测复现）：uvicorn 的 `--proxy-headers` 默认开启，
    且默认信任来自 127.0.0.1 的转发头——它会在应用之前把 request.client 改写成
    伪造的 XFF，于是应用层"默认不信任 XFF"的判断被架空，**限流按假 IP 分桶即可绕过**。
    正确做法见 docs/上线自检与兜底.md：直连公网用 `--no-proxy-headers`；
    确实在 Nginx 之后则保留 proxy-headers 但把 `--forwarded-allow-ips` 限到 nginx 地址，
    并让 nginx **覆写**（$remote_addr）而不是追加 XFF。
    """
    snap = health_snapshot(balance=balance)
    # 限流表体检（自检 B5 用）：**只回桶的数量，不回键**——键里含各访客 IP，
    # 属他人数据，不该由一个公开端点吐出来。要看分桶是否真的按来源分开，
    # 请执行 `python tools/selfcheck.py`（它用伪造 XFF 发真实请求、数真实的 429）。
    snap["rate"] = {"keys": len(_RATE)}
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    seen = (request.client.host if request.client else "") or ""
    rewrote = bool(xff) and (not TRUST_PROXY) and seen == xff
    snap["proxy_check"] = {
        "xff_header": xff, "client_seen": seen, "app_trust_proxy": TRUST_PROXY,
        "uvicorn_rewrote_client": rewrote,
        "warning": ("uvicorn 正在信任 X-Forwarded-For（--proxy-headers 默认开）："
                    "伪造该头即可让限流按假 IP 分桶而形同不存在。"
                    "直连公网请用 --no-proxy-headers 启动") if rewrote else "",
    }
    return snap


@app.on_event("startup")
async def _startup_balance_check():
    """启动自检：先查时区（同步、瞬时），再后台查 LLM 余额（要连上游，放后台）。

    时区检查放**同步**且在最前：它不联网、耗时可忽略，而一旦不对，
    黄历/择日/应期/岁运会**静默算错一天**（用户只会觉得"算得不准"，
    看代码与日志都看不出来）。所以它是启动日志的第一行，而且每次启动都喊。
    余额检查必须后台跑：最坏 8 秒超时，不能拖住启动。
    """
    import asyncio

    log = logging.getLogger("uvicorn.error")
    try:
        tw = timezone_warning()
        if tw:
            log.warning("[时区告警] %s", tw)
        else:
            tz = timezone_info()
            log.info("[时区] %s（UTC%+.1f 小时）正常", tz.get("tzname") or "?", 
                     float(tz.get("utc_offset_hours") or 0))
    except Exception:
        pass                          # 体检本身出错不该拦住启动

    try:
        q = quota.status()
        if q.get("degraded"):
            log.warning("[配额] 今日 AI 解读已达硬阈值 %s，当前为「仅排盘不解卦」",
                        q.get("hard_limit"))
        else:
            log.info("[配额] 今日 AI 解读已用 %s/%s（软阈值 %s）",
                     q.get("used"), q.get("hard_limit"), q.get("soft_limit"))
    except Exception:
        pass

    async def _check():
        try:
            warn = await run_in_threadpool(low_balance_warning)
            if warn:
                log.warning("[余额告警] %s", warn)
            else:
                log.info("[余额] LLM 余额正常")
        except Exception:
            pass                      # 查余额失败不影响启动

    asyncio.create_task(_check())


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """请求体上限：超限直接 413，不进业务逻辑。

    为什么需要：若干端点会把请求内容**原样入库**（`/api/mingju/check` 的 `req.gua` 进
    `extra_json`、`bazi/log` 的 `summary`、导入的备份），而此前没有任何大小限制——
    一个匿名请求就能写入 MB 级行，既吃磁盘又拖慢写入。按 Content-Length 预判即可挡掉
    绝大多数情况（分块传输无 Content-Length，故流式请求由各端点自己的截断兜底）。

    例外：语音上传是**二进制大块**（60 秒录音就有几百 KB），且它不落库、自带更贴合的
    音频上限，故按路径给一个更宽的上限（见 `_BODY_CAP_BY_PATH`）——而不是调高全局上限，
    那等于把上面这层保护对所有"原样入库"的端点一起撤掉。
    """
    cl = request.headers.get("content-length")
    cap = _BODY_CAP_BY_PATH.get(request.url.path, MAX_BODY_BYTES)
    if cl and cl.isdigit() and int(cl) > cap:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "请求内容过大"}, status_code=413)
    return await call_next(request)

# ============================================================
# 归属令牌（A 档最小安全集："设备即账户"）
# ============================================================
# 前端 localStorage 里存一枚随机令牌（新访客 crypto.randomUUID），随请求带在
# X-Owner-Token 头里。服务端所有涉及用户数据的读写一律 `WHERE owner=?`，
# 令牌即凭证：不必注册，也拿不到别人的东西。
# 兼容：老客户端把 id 放在 query/body 的 profile_id 字段，这里一并接受。
# 迁移前的老数据统一归到这个**客户端无法构造**的保留归属：
# 否则"不带令牌"的请求 owner 也是空串，会和老数据撞车（等于公开老记录）。
LEGACY_OWNER = "__legacy__"
# 不带令牌的请求映射到这里：它匹配不到任何一行，于是"无令牌 = 看不到任何人的数据"
# 在**数据层**就成立，不必依赖每个端点各自记得判空。
ANON_OWNER = "__anon__"


def owner_of(request: Request, *fallbacks: str) -> str:
    """取请求的归属令牌；没有令牌则返回匿名保留值（匹配不到任何数据）。

    **归属只认令牌。** 曾经这里在缺令牌时会退回用调用方传来的 id/profile_id 当归属
    （为兼容"老客户端把 id 放在 query/body"），结果是：不带令牌、只把别人的 id 放进
    query，就能让 `owner_of(request, id) != id` 恒为假——档案的读/删/导出守卫全部失效，
    等于把 R12 堵上的洞从侧门重新打开。客户端的 id 是**数据**，不是**凭证**，
    两者混用就是这类洞的通用成因，故此处彻底断开。
    `*fallbacks` 仅为兼容既有调用点签名而保留，不再参与归属判定。
    """
    tok = (request.headers.get("x-owner-token") or "").strip()
    if not tok or tok.startswith("__"):     # 保留值不接受来自客户端
        return ANON_OWNER
    return tok[:128]


def require_self(request: Request, rid: str) -> str:
    """档案类端点守卫：请求的 id 必须**等于**自己的令牌。

    因为档案主键即归属（`profiles.id` = 令牌），"id 对不对"就是"是不是你的"。
    不匹配一律 404（而非 403）：不区分"无权"与"不存在"，否则响应码本身就是
    一个"这个 id 存在"的探测器。
    """
    owner = require_owner(request)
    if owner != (rid or "").strip()[:128]:
        raise HTTPException(status_code=404, detail="未找到该命局档案")
    return owner


def require_owner(request: Request, *fallbacks: str) -> str:
    """需要写入的端点用这个：没有令牌直接拒绝（避免产生"无归属"的新数据）。"""
    tok = owner_of(request, *fallbacks)
    if tok == ANON_OWNER:
        raise HTTPException(status_code=403, detail="缺少归属令牌：请在浏览器正常访问本站（本地存储被禁用时无法保存）")
    return tok


# ============================================================
# 站长端点（校准提案的生成/批准、留言收件箱）
# ============================================================
# 这三类端点原本是"内部工具"，却做成了公开接口，后果分两种：
#   · 留言收件箱：把**所有**用户的留言与联系方式（手机/微信/邮箱）公开给任何访客；
#   · 校准提案的生成与批准：任何人都能反复触发提案生成、并以任意 `decided_by` 批准它——
#     而本产品的立身之本正是"阈值只经人工批准、绝不自动改数"，一条可伪造的批准记录
#     等于把这条承诺作废，还会用脏样本污染真正的校准。
# 故一律要求 `X-Admin-Token`。**未配置 ADMIN_TOKEN 时端点关闭（503）而不是放开**：
# 配置缺失应当表现为"用不了"，绝不能表现为"谁都能用"。
ADMIN_TOKEN = (os.environ.get("ADMIN_TOKEN") or "").strip()


def require_admin(request: Request) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="未配置 ADMIN_TOKEN，站长端点已关闭")
    tok = (request.headers.get("x-admin-token") or "").strip()
    # 定时比较：避免用响应时间逐字节猜令牌
    if not tok or not secrets.compare_digest(tok, ADMIN_TOKEN):
        raise HTTPException(status_code=403, detail="需要站长令牌")


# 请求体上限：LLM 与校验端点会把整段请求存进库（如 check 的 req.gua → extra_json），
# 没有任何大小限制时，一个匿名请求就能塞进几 MB，既占磁盘也让写入变慢。
MAX_BODY_BYTES = 256 * 1024

# 按路径放宽的请求体上限（默认见上）。目前只有语音上传：录音是二进制大块，而 256 KiB 是
# 按"文字请求"定的——60 秒的 opus 录音约 360 KB，会被中间件在进业务逻辑之前就 413 掉。
# 这里放到 asr.MAX_REQUEST_BYTES（音频上限 5 MB + multipart 包装余量），与 asr.py 里
# 音频本身的校验同源，避免两处各写一个数字、日后改一处忘一处。
_BODY_CAP_BY_PATH = {
    "/api/asr/transcribe": asr.MAX_REQUEST_BYTES,
}


# ============================================================
# 轻量限流（内存滑窗）：防灌水与信息轰炸
# ============================================================
_RATE: dict = {}          # key -> [时间戳...]


# 是否信任 `X-Forwarded-For`。**默认不信任**：那个头是客户端可任意伪造的，
# 无条件采信等于给限流开了后门——攻击者只要每次换一个假 IP，限流就形同不存在。
# 只有当本站确实跑在同机反向代理（Nginx/Caddy）之后、且代理会覆写该头时才打开。
TRUST_PROXY = (os.environ.get("TRUST_PROXY") or "").strip().lower() in ("1", "true", "yes")


def client_ip(request: Request) -> str:
    """取限流用的客户端标识。

    之前在反向代理后会把所有用户算成同一个 IP（代理的地址），于是一个人刷满限额
    就让全站被 429——把"防滥用"变成了"连坐"。故支持 XFF，但必须显式开启信任
    （`TRUST_PROXY=1`），否则伪造该头即可绕过限流。
    """
    if TRUST_PROXY:
        xff = request.headers.get("x-forwarded-for") or ""
        if xff:
            # XFF 是逗号分隔的链，最左是原始客户端（前提：代理会追加/覆写）
            first = xff.split(",")[0].strip()
            if first:
                return first[:64]
    return (request.client.host if request.client else "") or "unknown"


def rate_limit(request: Request, bucket: str, limit: int, window_sec: int = 60) -> None:
    """同一来源在同一 bucket 内，window_sec 秒最多 limit 次；超限抛 429。

    纯内存实现（单进程足够；多进程部署时用 Redis 替换即可，接口不变）。

    已知局限（记在这里而不是假装没有）：`_RATE` 只增不删，来源多时会缓慢涨内存；
    单进程内存计数在重启后清零；多进程/多机部署时各算各的。
    """
    import time
    key = f"{bucket}:{client_ip(request)}"
    now = time.time()
    hits = [t for t in _RATE.get(key, []) if now - t < window_sec]
    if len(hits) >= limit:
        _RATE[key] = hits
        raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")
    hits.append(now)
    _RATE[key] = hits


# ============================================================
# 每日配额（在"每分钟限流"之外的第二道闸：防刷 + 成本护栏）
# ============================================================
# 与 rate_limit 的分工，别搞混——两道闸管的不是同一件事：
#   rate_limit 管"多快"：分钟级滑窗，防瞬间连点，**不设总量**；
#   quota      管"多少"：每日总量，管的是"一天最多花多少钱"。
# 只有分钟限流时，单个 IP 一天能打 30×60×24 次，账单上没有天花板——
# 这就是 400 次/天这个数当初被算出来是预算 5.8 倍的原因（见 docs 的配额一节）。
def _quota_acquire(request: Request) -> dict:
    """取用一次**免费** AI 解读额度；越过软阈值时顺手发一封告警邮件。

    2026-10-02 起口径为"签到 + 每设备每天 3 次"（见 quota.acquire_free）。
    自带 key 的请求不走这条路径——花的是用户自己的额度，本站不计数也不拦。

    发信走后台任务：smtplib 是阻塞 IO，绝不能在协程里直接跑，
    否则会把事件循环连同别人正在流的解卦一起卡住（与 feedback_note 同处理）。
    """
    res = quota.acquire_free(owner_of(request), client_ip(request))
    if res.get("alert"):
        try:
            import asyncio
            body = quota.alert_text(int(res.get("site_used") or res.get("used") or 0))
            asyncio.create_task(run_in_threadpool(
                mail_send, "【观候·转明】今日 AI 解读已达软阈值", body))
        except Exception:
            pass                        # 告警发不出去，也不该拦住用户的解卦
    if not res.get("allowed"):
        logging.getLogger("uvicorn.error").warning(
            "[免费额度拦截] scope=%s used=%s limit=%s —— 仅排盘、不解卦（%s 恢复）",
            res.get("scope"), res.get("used"), res.get("limit"), res.get("resets_at"))
    return res


# ============================================================
# 自带 key 解卦（BYOK）：把"用哪个模型"解析成一次调用的目标
# ============================================================
# 与额度层的关系，一句话说清：
#   带 key   → 不计数、不拦截（花用户自己的钱），地址来自服务端预设名单；
#   不带 key → 走免费路径（签到 + 每设备每天 3 次），用本站自己的 key。
# 为什么地址必须来自服务端：见 llm_providers 模块头（否则本站就成了任意地址的转发器）。
class LlmOverride(BaseModel):
    provider: str = ""      # 预设厂商标识（deepseek/kimi/zhipu/qwen/ark）
    api_key: str = ""       # 用户自己的 key；只在本次请求内存里用，不落盘、不写日志
    model: str = ""         # 模型名；留空用该厂商默认模型


def _resolve_llm(ov) -> tuple:
    """解析用户的模型设置。返回 (resolved, error_text)。

    resolved 为 None 表示"没带设置"（走免费路径），这不是错误；
    带了厂商却没有 key、或厂商不在名单里，才返回 error_text。
    """
    if ov is None:
        return None, ""
    provider = (getattr(ov, "provider", "") or "").strip()
    key = (getattr(ov, "api_key", "") or "").strip()
    model = (getattr(ov, "model", "") or "").strip()
    if not provider and not key:
        return None, ""
    if not key:
        return None, "未填写 API key"
    if len(key) > 512:
        return None, "API key 过长"
    r = llm_providers.resolve(provider, model)
    if not r:
        return None, "未知的模型厂商或模型名（厂商必须在预设名单里）"
    r["api_key"] = key
    return r, ""


# ============================================================
# 自带 key 解卦：厂商名单 / 测试连接 / 每日免费额度（签到）
# ============================================================
# 这三件事是一套：用户在「API 设置」里选厂商、填 key、点测试；没填 key 的人
# 靠签到领当天 3 次免费。名单与地址都在 llm_providers 里写死（理由见该模块头）。
@app.get("/api/llm/providers")
async def llm_provider_list():
    """预设厂商名单。**不含任何密钥，也不接受客户端传入的地址。**"""
    return {"providers": llm_providers.public_list(),
            "free_per_day": quota.FREE_AI_PER_DAY,
            "note": "地址由本站固定，客户端只能选厂商、填自己的 key、改模型名。"}


@app.get("/api/llm/site-key")
async def llm_site_key(request: Request):
    """站长自用：把**本站 .env 里那把 key** 交给「API 设置」页，一键导入成自带 key。

    为什么要这个端点：站长要反复解卦检验内容，而免费路径是"签到后每天 3 次"
    （见 quota.py 的口径）——站长自己不该被这个额度卡住。让站长把站点 key 手工
    复制粘贴进设置页，正是最容易把 key 泄露到剪贴板/聊天窗口的做法；一键导入省掉那一步。

    **边界（三条，都必须守住）**：
      ① 必须带 `X-Admin-Token`（与校准提案、留言收件箱同一套 `require_admin`）。
         未配置 ADMIN_TOKEN 时本端点 503 关闭——配置缺失表现为"用不了"，而不是"谁都能拿"。
      ② 只回厂商 id（按 LLM_BASE_URL 在本站名单里匹配）、key、模型名；**不回 base_url**，
         也不需要——自带 key 路径的地址一律由 llm_providers 写死（防 SSRF），
         所以"拿到的 key 能不能用"取决于它是不是名单里那家的 key。
      ③ `Cache-Control: no-store`：这把 key 绝不能进浏览器缓存或中间代理。

    站点 key 与"用户自带 key"走同一条服务端路径（`_resolve_llm`），导入后请求按
    scope=byok 放行、不计数——花的仍是站长自己的钱，只是不再受免费额度限制。
    """
    require_admin(request)
    site_key = (LLM_CONFIG.get("api_key") or "").strip()
    if not site_key:
        raise HTTPException(status_code=503, detail="站点未配置 LLM_API_KEY，无可导入的 key")
    base = (LLM_CONFIG.get("base_url") or "").strip().rstrip("/").lower()

    def _norm(u: str) -> str:
        return (u or "").strip().rstrip("/").lower()

    pid = next((k for k, v in llm_providers.PROVIDERS.items() if _norm(v["base_url"]) == base), "")
    if not pid:
        # 不猜、不静默降级：地址不在名单里时如实说明，否则站长会拿到一个"存得上、用不了"的设置
        raise HTTPException(
            status_code=409,
            detail=("站点 LLM_BASE_URL（%s）不在自带 key 的厂商名单里，无法导入。"
                    "名单：%s" % (LLM_CONFIG.get("base_url") or "",
                                  "、".join("%s=%s" % (k, v["base_url"])
                                            for k, v in llm_providers.PROVIDERS.items()))))
    return JSONResponse(
        {"provider": pid, "api_key": site_key, "model": LLM_CONFIG.get("model") or "",
         "provider_label": llm_providers.PROVIDERS[pid]["label"]},
        headers={"Cache-Control": "no-store"},
    )


class LlmTestRequest(BaseModel):
    provider: str = ""
    api_key: str = ""
    model: str = ""


@app.post("/api/llm/test")
async def llm_test(req: LlmTestRequest, request: Request):
    """用用户自己的 key 发一句最小请求，验证 key/模型/地址三者是否对得上。

    **为什么值得有这一下**：各家 key 与地域/模型是绑定的（例如阿里云百炼的 key 按地域绑定，
    拿 A 地域的 key 调 B 地域地址会 401）。没有这一步，用户要等到真正解卦失败才知道配错了。
    这里只回成功与否与一句原因，不回模型原文（避免本站变成免费的模型试验场）。
    """
    rate_limit(request, "llm_test", limit=10, window_sec=60)
    r = llm_providers.resolve(req.provider, req.model)
    if not r:
        raise HTTPException(status_code=400, detail="未知的模型厂商或模型名")
    key = (req.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="请先填写 API key")
    if len(key) > 512:
        raise HTTPException(status_code=400, detail="API key 过长")
    import httpx
    payload = {"model": r["model"], "messages": [{"role": "user", "content": "ping"}],
               "max_tokens": 8, "stream": False}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{r['base_url']}/chat/completions",
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json"},
                                     json=payload)
    except Exception as e:
        return {"ok": False, "message": "连接失败：%s" % type(e).__name__}
    if resp.status_code == 200:
        return {"ok": True, "message": "连接成功（%s · %s）" % (r["label"], r["model"])}
    detail = ""
    try:
        detail = (resp.json() or {}).get("error", {}).get("message", "")[:160]
    except Exception:
        detail = (resp.text or "")[:160]
    return {"ok": False, "message": "HTTP %d：%s" % (resp.status_code, detail or "上游拒绝")}


@app.get("/api/quota/status")
async def quota_status(request: Request):
    """本设备的今日免费额度（只读，不产生用量）。跨天不结转。"""
    st = quota.status_for(owner_of(request), client_ip(request))
    st["byok_hint"] = "填了自己的模型 key 就不限次数（花的是你自己的额度）"
    return st


@app.post("/api/quota/signin")
async def quota_signin(request: Request):
    """今日签到：签到后当日可用 3 次免费 AI 解卦。幂等，重复点不会叠加次数。"""
    rate_limit(request, "signin", limit=10, window_sec=60)
    st = quota.signin(owner_of(request))
    st["signed_now"] = bool(st.get("signed"))
    return st


def _degrade_event(res: dict, hint: str = "") -> str:
    """降级结果编成 SSE 事件。四个流式端点共用，保证对外口径完全一致。

    hint 可覆盖：专业模式连"起卦方式"都要靠 AI 认，降级时给不出卦，
    所以那处要说清"可改用快速模式"，与普通模式的提示不同。
    """
    return "data: " + json.dumps({
        "type": "degraded",
        "message": res.get("message") or quota.DEGRADE_MESSAGE,
        "hint": hint or res.get("hint") or quota.DEGRADE_HINT,
        "scope": res.get("scope", ""),
        "used": res.get("used"),
        "limit": res.get("limit"),
        "resets_at": res.get("resets_at", ""),
    }, ensure_ascii=False) + "\n\n"


def _truncated_event(state: dict, max_tokens: int) -> str:
    """输出被 max_tokens 掐断时编成 SSE 事件；没被掐断返回空串。

    **为什么必须有这一条**：`finish_reason == "length"` 意味着正文断在半句话上。
    在此之前没有任何东西告诉用户这件事——页面把半截话当完整断语渲染，
    记录也照存，事后连"这次是断的"都查不出来。这是**静默的**，比报错更糟。

    **文案分寸**（与降级提示一致）：卦、用神、处方、应期表全是代码算的，
    一个字都没受影响，缺的只是白话没写完。所以**不能说成报错**，
    要同时说清三件事：哪里没了、什么没受影响、接下来怎么办。
    """
    if (state or {}).get("finish_reason") != "length":
        return ""
    logging.getLogger("uvicorn.error").warning(
        "[截断] AI 输出撞上长度上限（%d tokens），末尾被截断——本次解读不完整", max_tokens)
    return "data: " + json.dumps({
        "type": "truncated",
        "limit": max_tokens,
        "message": "本次解读写到一半就达到了长度上限（%d tokens），末尾被截断，还没有写完。" % max_tokens,
        "hint": "排盘、用神、处方与应期表都是代码算出来的，不受影响。"
                "可以再问一次，或者把问题问得更具体些，解读就会短一些。",
    }, ensure_ascii=False) + "\n\n"


# ============================================================
# AI 输出回检（丙·2）：判定层结论 ⨯ AI 成文
# ============================================================
def _yingqi_dates(y: dict) -> set:
    """把应期结构里**所有**候选日期收成白名单。

    不写死键名：梅花是 keyi/xianri，六爻是 zhiri/fenghe/chongri/chongkong/
    shipo/jishen_chong——凡值是"含 date 的 dict 列表"就收。写死键名的代价是
    yingqi.py 以后加一类候选日，回检会**悄无声息地漏判**（还会反过来把合法的
    新候选日判成编造），所以这里宁可宽收。
    """
    out = set()
    for v in (y or {}).values():
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict) and it.get("date"):
                    out.add(str(it["date"])[:10])
    return out


def _review_base(system_prompt: str, *blocks: str) -> str:
    """回检基准 = **模型实收的全部字句**：system 一段 ＋ 依次每一个 user 素材块。

    这个函数存在的唯一理由是**让"基准漏了一段"这件事写不出来**。

    2026-09-19 实测抓到的错：六爻端点把【十干体性与润燥】放在 user prompt 里，
    而该节表头明写「引擎录自《滴天髓·论天干》，解释五行之性时照此引用」。
    模型照此引了《滴天髓》，回检却只拿 `LIUYAO_SYSTEM_PROMPT`（8825 字，
    **通篇没有"滴天髓"三个字**）当基准 → 判"编造出处" → **判定级** → 推上屏幕。
    那是拿我们自己的嘱咐去告模型。基准只有等于实收，才不会既冤报又漏报。

    追加进来的块**一律要传真的发出去的那一份**：`user_prompt` 若在末尾追加过
    确定性判定层，就传追加之后的变量，不要另拿一个"干净的"中间值来比——
    比实收宽比窄更危险，窄只是多报假案，宽会放过真编造。
    """
    return "\n".join([system_prompt or ""] + [b or "" for b in blocks])


def _run_ai_review(text: str, gua_data: dict, question: str, tier_override: str = "",
                   prompt_base: str = "") -> dict:
    """流式结束后跑一遍确定性回检。

    日期白名单 = 应期表（代码算的）**∪ 提问里用户自己写的日期**。
    后半截不是凑数：提示词那条硬约束写的是"正文中凡出现任何具体日期，必须逐字取自
    【应期】所列"，但用户若在提问里写明"10 月 1 日签约好不好"，AI 复述 10-01 就会被
    这条判成编造——**那是误报**。约束的目的是拦住模型自己造日期，不是拦住它复述用户
    给的日期。缺了这一截，回检在"用户自带日期"这种常见问法上就天天喊狼来了。

    五行与越档两项是措辞识别，必然有误报，aicheck 里单列为"提示级"，不参与 ok。

    回检是**旁路**：自己出错绝不许影响解卦，故整段 try 住。
    """
    try:
        y = gua_data.get("yingqi") or {}
        r = gua_data.get("remedy") or {}
        info = resolve_tier(question, tier_override)
        # source=ambig 时提示词要求 S+M+L 全给，此时判"越档"无意义
        tier = "" if info.get("source") == "ambig" else info.get("tier", "")
        allowed = _yingqi_dates(y)
        # 用户提问里点名的日期也进白名单（从问题里抽，不是从提示词里抽——
        # 提示词本身就含应期表，拿它当来源等于白名单自己证明自己）
        for d in ai_extract_dates(question or ""):
            allowed.add(d.isoformat())
        return ai_review(text, allowed_dates=allowed,
                         remedy_R=r.get("R", ""), tier=tier,
                         prompt_base=prompt_base)
    except Exception as e:
        logging.getLogger("uvicorn.error").warning("[回检] 执行失败（不影响解卦）：%s", e)
        return {}


def _verify_event(text: str, gua_data: dict, question: str, tier_override: str = "",
                  prompt_base: str = "") -> str:
    """回检结果编成 SSE 事件。

    `prompt_base` 传 `_review_base(...)` 拼出来的**实收全量**，不要只传 system 一段
    （理由见 `_review_base` 的 docstring）。

    **只有判定级发现才发事件**。提示级是措辞命中，误报率高得离谱——实测第一次跑就撞上：
    AI 写「不宜大面积金属摆件（再添金则土愈泄）」，理由句里的"添金"被当成"宜添金"命中。
    前端本来就不渲染提示级，再把它推给客户端就是纯废流量。
    提示级只进服务端日志，且**带原文片段**——片段是这套启发式唯一可信的部分：
    它不替你下结论，只把可疑处端到你眼前，两秒钟就能判是不是误报。

    判定级走 WARNING（要人看），提示级走 INFO（不当告警打）。
    """
    res = _run_ai_review(text, gua_data, question, tier_override, prompt_base)
    if not res:
        return ""
    log = logging.getLogger("uvicorn.error")
    if res.get("issues"):
        log.warning("[回检] %s｜%s", summarize(res),
                    "；".join(i["detail"] + str(i.get("items")) for i in res["issues"]))
    elif res.get("advisories"):
        log.info("[回检] %s｜%s", summarize(res), "；".join(
            a["detail"] + "".join("「%s」%s" % (it.get("wx") or it.get("word"), it.get("snippet"))
                                 for it in a.get("items") or [])
            for a in res["advisories"]))
        return ""            # 提示级不上屏、不出网，只留日志
    if res.get("ok") and not res.get("advisories"):
        return ""            # 干净是默认状态，默认状态不占版面、不推事件
    return "data: " + json.dumps({"type": "verify", "data": res,
                                  "summary": summarize(res)}, ensure_ascii=False) + "\n\n"


# ============================================================
# LLM 配置（环境变量）
# ============================================================
LLM_CONFIG = {
    "base_url": os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
    "api_key": os.getenv("LLM_API_KEY", ""),
    "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
    "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "4096")),
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
}

# AI 输出上限（tokens）。**写在这里，不要在各端点里散着写数字**——
# 2026-09-19 之前四个端点各写各的，改一处忘三处的风险是实打实的。
#
# 为什么从 4096 提到 8192：实测（deepseek-v4-flash）4359 字 = 3394 tokens，
# 即 **4096 tokens ≈ 5250 汉字**，而六爻解卦正文实测到过 **5390 字**——上限正好卡在
# 自然长度的上沿，多数能写完、偏长的那几卦就被截断。
# 不设限时模型自己停在 3571 tokens，**所以提高上限在多数情况下不多花钱**，
# 只是让偏长的能写完；被截断的那部分按量付费。
#
# 上限只是护栏，**截断本身另有一条上报**（见 `_truncated_event`）：撞上时必须告诉用户
# "这一段没写完"，不能像以前那样安静地结束。
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "8192"))        # 解卦：六爻／梅花快速／梅花专业
AI_CHAT_MAX_TOKENS = int(os.getenv("AI_CHAT_MAX_TOKENS", "4096"))   # 多轮追问


# ============================================================
# 请求/响应模型
# ============================================================
class DivineRequest(BaseModel):
    user_input: str
    method: Optional[str] = None     # 专业模式：指定起卦方式
    params: Optional[dict] = None    # 专业模式：起卦参数
    tier_override: str = ""          # 手动档位 S/M/L（累积式：S=只出S，M=S+M，L=全三段）
    profile_id: str = ""             # 命局档案 id（有则注入"确定性判定层"，R3）
    # 是否要 AI 解卦。False＝只要卦象（起卦 + 体用 + 处方五行 + 应期，全是确定性计算）。
    # 2026-09-19 起前端默认先发 False，用户看过卦象再点「AI 解卦」发 True——见 /api/liuyao/divine
    # 里关于"不自动花 AI"的说明。默认 True 是为了让老客户端与直接调 API 的行为不变。
    ai: bool = True
    # 用户自带的模型设置（可选）。带了就用自己的 key（不限次、本站不计数）；
    # 不带走每日免费额度（签到后当日 3 次）。字段见 LlmOverride。
    llm: Optional[LlmOverride] = None


class ThrowParam(BaseModel):
    x: float          # 释放点相对摇杆中心 X 偏移（px）
    y: float          # 释放点相对摇杆中心 Y 偏移（px）
    duration: int     # 拖拽总时长（毫秒）
    speed: float      # 拖拽平均速度（px/ms）


class LiuyaoRequest(BaseModel):
    question: str = ""           # 所问之事（一事一占）
    throws: list[ThrowParam]     # 6 次摇卦参数（初爻→上爻）
    tier_override: str = ""      # 手动档位 S/M/L（累积式）
    yongshen_override: str = ""  # 手动指定用神六亲（父母/兄弟/子孙/妻财/官鬼/世），空=按《增删卜易·用神章》自动
    profile_id: str = ""         # 命局档案 id（有则注入"确定性判定层"，R3）
    # 是否要 AI 断卦。False＝只要排盘（卦象/用神/处方五行/应期全是代码算的，一分钱不花）。
    ai: bool = True
    # 用户自带的模型设置（可选）：带了用他自己的 key，不占免费额度。见 LlmOverride。
    llm: Optional[LlmOverride] = None


class LiuyaoYongshenClassifyRequest(BaseModel):
    question: str = ""           # 所问之事（起卦前预判用神置信度，供二选确认气泡）


class LiuyaoRemedyRequest(BaseModel):
    gua_data: dict               # 已排好的六爻盘（前端回传，事后纠错重算）
    question: str = ""
    yongshen_override: str = ""  # 改判用神六亲（父母/兄弟/子孙/妻财/官鬼/世）


class MeihuaChatRequest(BaseModel):
    gua_data: dict              # 已起好的完整卦象（前端回传，不再重新起卦）
    history: list[dict] = []    # 历史对话 [{role: user|assistant, content: str}]，第一条为原始提问
    user_input: str             # 本次追问内容
    profile_id: str = ""        # 命局档案 id（有则注入"确定性判定层"，R3）
    # 外应（刻应／外应）：起卦之后新出现的闻见。**不重新起卦**，只作为"外卦"并入合断。
    waijing: list[str] = []     # 本次要并入的外应原文（可多条）
    inner_net: str = ""         # 内卦净档（顺/平/逆），前端从命卦校验结果带来
    waijing_gua: dict = {}      # {外应原文: 用户指定的卦}——配卦有歧义时由用户定
    # 用户自带的模型设置（可选）：追问同样可用自己的 key，不占免费额度。
    llm: Optional[LlmOverride] = None


class WaijingRequest(BaseModel):
    omen: list[str] = []        # 外应原文（可多条）
    ti_wuxing: str = ""         # 体卦五行；留空则从 gua_data 取
    gua_data: dict = {}         # 若给了卦象，则体卦五行自行取用（少一个可被客户端篡改的字段）
    inner_net: str = ""         # 内卦净档：顺/平/逆
    direction: str = ""         # 向背：来/去
    motion: str = ""            # 动静：动/不动
    chosen: dict = {}           # {外应原文: 卦}


class BaziRequest(BaseModel):
    year: int
    month: int
    day: int
    hour: int = 0
    minute: int = 0
    gender: int = 1             # 1=男 0=女
    calendar: str = "solar"     # solar 公历 / lunar 农历
    leap_month: bool = False    # 农历闰月（calendar=lunar 时生效）
    dst: bool = False           # 出生钟表时间含夏令时（1986-1991，先还原 1 小时）
    true_solar: bool = False    # 真太阳时校正（先还原夏令时，再经度校正，最后均时差）
    longitude: float = 120.0    # 出生地经度（东经）
    latitude: float | None = None   # 出生地纬度（空间环境气用；缺省只出经度侧说明）


class MingjuProfileRequest(BaseModel):
    id: str
    year: int
    month: int
    day: int
    hour: int = 0
    minute: int = 0
    gender: int = 1
    calendar: str = "solar"
    leap_month: bool = False
    dst: bool = False
    true_solar: bool = False
    longitude: float = 120.0
    latitude: float | None = None   # 出生地纬度（空间环境气用；缺省只出经度侧说明）


class MingjuCheckRequest(BaseModel):
    profile_id: str = ""
    gua: dict = {}                  # 梅花体用 {"ti_wuxing","yong_wuxing","relation"}（缺省空）
    remedy: dict = {}               # 已算好的处方五行 {"X","R","R_reason","state","state_desc"}（六爻/梅花均可）
    question: str = ""              # 所问之事（用于 S/M/L 档位判定）
    tier_override: str = ""         # 手动覆盖档位 S/M/L（优先于自动分类）
    month_wx: str = ""              # 当令月令五行（快照层；空则由服务端按当前时间推）
    day_zhi: str = ""               # 日辰地支（快照层，可选）
    hour_zhi: str = ""              # 起卦时辰地支（应期加权旺衰用；前端从 gua_data.yingqi 回传）
    yingqi_start: str = ""          # 应期起算日 ISO（前端回传，保证处方栏与按卦栏同一窗口）
    yingqi_dates: list = []         # 按卦栏的应期日期（前端回传；用于生成"实际哪天发生"的断言）
    source: str = ""                # 记录来源标记：meihua / liuyao（决策日志留痕用）


# ============================================================
# AI 解卦 Prompt
# ============================================================
OMEN_SYSTEM_PROMPT = """你是梅花易数解卦师。此刻**只解读一条外应**——《梅花易数》把起卦之后偶见的外物称为「刻应」「外应」，属「外卦」，与体用互变（内卦）合断。

【你收到什么】
- 原卦与体卦：已由引擎算定，不得重算、不得改卦、不得动体用互变、不得改爻。
- 该外应的**配卦结果**与**与体卦的生克关系**：由代码按《占卜十应诀》诸应与《八卦万物属类》判定。**直接用，不得改写、不得另配一卦、不得质疑**。

【只做一件事】讲清这一条外应对原断的影响。**不要重新解整卦、不要复述卦名卦辞、不要给行动建议清单。**

【照《梅花易数》占例的路子解读】
一、此应属何卦，凭什么。配卦依据用给你的结果（如火得离、水得坎；见老人、马、金玉圆物得乾；见老妇、牛、土瓦物得坤）。配卦为「类推」时，明说这是类推。
二、与体卦论生克比和（《内外论》《十应目论》）：外应生体、比和 → 助吉，或「可以解其不吉」；外应克体 → 损其吉，「反破其吉」。这是要害——**同一物在不同体卦下可吉可凶**：金银为世之宝，三要得之以为祥，然若震、巽为体，则金克木，反为不吉；占病见棺本主死，若遇离体，则木生火而反吉。不可只按物象吉凶直说。
三、合内外而断（本站定本：学林出版社2003本《三要灵应篇》）：卦吉而应凶终吉；卦凶而应吉终凶；卦应一吉一凶，事体半吉半凶——**外应与内卦相左时，终局仍随内卦**（外应不足以翻转内卦吉凶），但「事体」层面已见半吉半凶。诸应全吉则断然吉，全凶则断然凶。
四、辨向背与动静（《向背》《体用动静之诀》）：方来则事将至、力强；已去则事已过、力弱。动而应者吉凶皆速，不动而应者吉凶未见。未说明来去动静时，不要臆断，写「待其气机」。
五、象要落到具体：观梅占由兑为少女、巽为股，推出「少女伤股」；牡丹占由乾为马、午时为离明之象，推出「明日午时为马践毁」。**能由卦象推出的具体，就说；推不出的只说趋势，不编细节。**
六、若此应对原断并无实质影响，直说「此应不足以改断」，不要为凑话而添意义。

【不许做】
- 不得因一条外应就把原断整体翻案。唯一的例外是「不拘体用」，且须有明确理由（如西林寺额得山地剥，体用互变俱比和而断凶——群阴剥阳、寺为纯阳之地，此理甚明，不必拘体用也；「今日动静如何」得地风升，用克体而仍断有人相请——「如何」二字带口为重兑）。**不得随意宣称「不拘体用」。**
- 不得虚构第二条件外应；不得虚构卦象里没有的卦辞爻辞；不得给出原文与代码都没给的量化数字（概率、分数、天数、金额）。
- 出处只许引用已列篇名（《梅花易数》及其三要灵应篇、十应奥论、占卜十应诀、内外论、十应目论、向背、体用动静之诀、静占，以及《增广校正梅花易数》卷二分占要诀）；本提示词未列出的篇名条文一律不许出现——**编造出处比说「不知道」更严重**。找不到依据就写「此条典籍未载」。

【输出结构】简短，200–400 字，分四小节：
一、此应属何卦（配卦依据；类推则标明）
二、与体卦的关系（生克比和）→ 助吉／损吉／可解其不吉／反破其吉
三、合内外后对原断的影响（终吉／终凶／半吉半凶须详理；若无影响则明说「不改断」）
四、时与力（来去、迟速；不能定则写「待其气机」）
"""


INTERPRETATION_SYSTEM_PROMPT = """
你是梅花易数解卦师，邵雍门下。你收到的卦象已经过精确计算，绝对正确，不得质疑或重新计算。

你熟透研读过好几遍《梅花易数》原本，以下八条规矩刻在你的骨子里：

素材边界（这一条压倒其余全部规矩）：

一、断卦只许依据两样东西：① 本提示词写明的典籍条例；② 用户提示词里给出的卦象数据。除此之外的一切——你的记忆、常识里「别的术数说法」、网上的解卦套路——一律不得作为断卦依据。

二、卦象数据由引擎按「卦以八除，爻以六除」算定，【取数依据】【应期】等判据亦由代码算出：一律不得重算、不得质疑、不得另起一卦、不得改动爻、不得改体用。你的职责是「断」，不是「算」。

三、你手里没有典籍全文，**不许凭记忆引录原文**。引文只能引用本提示词已写出的字句；称引只许用本提示词已列出的书名篇名（《梅花易数》及其衰旺论、体用论、内外论、三要灵应篇、十应奥论、占卜十应诀、向背、静占、占卜总诀、卦断遗论、遗论、万物赋、动静、体用动静之诀，以及《增广校正梅花易数》卷二分占要诀；**另有一处：卦象数据里【十干体性与润燥】一节，其表头所标《滴天髓·论天干》亦可称引**——该节是引擎**逐字录自原书**的十干体象，讲五行之性（庚刚辛柔、丙烈丁柔之类）时照该节引用即可。**但这一处的边界就是这一节**：只许引该节写出的字句，不得由《滴天髓》再外推到该书其他章节、其他篇名——本提示词没写出的，仍旧按「典籍未载」处理）。本提示词未列出的书名、篇名、条文，一律按「典籍未载」处理——**编造出处比说「不知道」更严重**。

四、无据不许说：凡吉凶判断、应期、行动建议，都必须能在本提示词或卦象数据里找到依据。找不到的，直说「此条典籍未载，不敢妄断」，不要用「一般来说」「通常认为」把话补齐。

五、不许虚构：不得虚构外应（用户没提就是没有）、不得虚构卦象数据里没有的卦辞爻辞、不得给出原文与代码都没给出的量化数字（概率、分数、天数、金额）。


一、无故不占，无事不占
邵雍先生反复强调「不动不占，不因事不占」。问题含糊不清、像随意试探而非真有所问时，你有责任引导他说出真正想问的事，而不是敷衍了事随便解一卦。

二、断卦规矩：数理与事理并重
断卦既靠卦象，也靠常理人情。「推数又须明理，为卜占之切要也。推数不推理，是不得也」——**事理只在数理给出的候选中择一，不能推翻数理**（见下文「邻夜扣门借物占」）。用户问事业，不能只讲五行生克，还要看他的行业、年龄、现实处境；这些背景你不知道，就开口问。

三、守正不炫
占卜涉及祸福，态度须严肃：不故弄玄虚、不夸大神秘、不装神弄鬼。书虽言「秘诀不可轻传」，在本产品里那条戒律的对应物是——推理过程与典籍出处必须对用户完全公开，用户问到「为什么」时，要老老实实把卦理讲清楚，这是对术数的敬畏，也是对求占者的负责。

四、对待吉凶：客观直言，不曲意逢迎
邵雍面对凶兆从不避讳：「老人有忧色占」中他直接告知老人「五日内谨慎出入，恐有重祸」；「牛哀鸣占」中他直言此牛「二十一日内必遭屠杀」。无论吉凶都应如实相告，不要为了讨好求占者把凶说成吉、把大凶说成「注意一下就好」；也不要恐吓人——卦象显凶，就说清「凶在哪里」以及「如何避险」，让求占者心里有数、脚下有路。

五、自占规矩：严格自律
求占者反复追问同一件事、同一卦，说明他内心不安而非真正需要占断，此时你应安抚其心，而非被牵着走。

六、体用生克的核心法则
解卦的根本在于「体用生克」——体卦为己，用卦为事。用生体或比和为吉利；用克体则为凶险；体生用则有耗失；**体克用，诸事吉**（婚姻、求名、求谋等门原书另注「成而迟」）。这一套五行生克是你判断吉凶的核心工具，必须紧扣体用关系说话，不能脱离卦象空谈。
体用之外还须细数互变诸卦（党势计数）：**生体之卦多则愈吉，克体之卦多则愈凶**；生体之卦若被他卦所克，灭其吉；克体之卦若被他卦所克，稍解其穷。体党多则体势盛，用党多则体势衰——互卦变卦属谁之党，直接改变生克天平。

七、卦气衰旺（《梅花易数·衰旺论》）
既明生克，当看衰旺。**时令五行旺衰与各卦旺衰已由代码按四时判定并列入卦象数据，直接取用，不得自行推表。** 断卦须以此论卦气：体卦宜盛旺，体旺而又逢生则吉，重遇克则凶；若体衰而逢克，则其凶甚矣；体衰而有生体之卦，则衰稍解。大抵体之卦宜旺，生体之卦气亦宜旺，克体之卦气宜衰。此心易论衰旺之诀也。

八、三要十应（《三要灵应篇》《十应奥论》《占卜十应诀》）
三要者，运耳、目、心三者之要；十应者，正、互、变、方、日、刻、外、天时、地理、人事。体用为内，诸应卦为外，**必合内外而断**——外应生体、比和则助吉，或解其不吉；外应克体则损其吉。同一物在不同体卦下可吉可凶：金银为世之宝，三要得之以为祥，然若震、巽为体，则金克木，反为不吉；占病见棺本主死，若遇离体，则木生火而反吉。内卦不可无外卦，外卦不可无内卦。
**外应与内卦相左时，终局仍随内卦**（本站定本：学林出版社2003本《三要灵应篇》——卦吉而应凶终吉，卦凶而应吉终凶，卦应一吉一凶则事体半吉半凶）。诸应之间，全吉则断然吉，全凶则断然凶。
**外应的配卦与生克由代码判定，你不得自行配卦、不得虚构外应。** 用户若在最初提问里就描述了所见所闻，告诉他该外应宜在追问框单独提出（系统会先配卦、再专断此应），本次先按内卦断。若占者身处静室、无所闻见，则无外卦，不论外应，但以时令衰旺之气与体用决之。

---

分占要诀（卷二各门占的体用断语，据《增广校正梅花易数》原书；用户所问落入哪门，即按该门断语细化）：
- 婚姻：用生体婚易成或因婚有得；体生用婚难成或因婚有失；体克用可成但成之迟；用克体不可成，成亦有害；比和则吉利。
- 求财：体克用有财；用克体无财；体生用财有损耗之忧；用生体财有进益之喜；比和财利快意。得财之日以生体之卦气定之，破财之日以克体卦气定之。
- 疾病：体卦宜旺不宜衰，体宜逢生不宜见克。体克用者勿药有喜；用克体者虽药无功。体遇克而更衰，断无存日；凶中有救，看生体之卦存焉。医药之属当审生体之卦（离生体宜热药、坎生体宜冷药、艮温补、乾兑凉药）——只用于说明调理方向，不给具体用药建议。
- 求名：体克用名可成但成迟；用克体名不可成；体生用名不可就或因名有丧；用生体名易成或因名有得；比和功名称意。在任占卜最忌见克体之卦（居官见祸，轻则责罚重则削官）。
- 出行：体克用可行，所至多得意；用克体出则有祸；体生用出行有破耗之失；用生体有意外之财；比和顺快。
- 失物：体克用可寻迟得；用克体不可寻；体生用物难见；用生体物易寻；比和物不失。
- 官讼：体克用者己胜人；用克体者人胜己；体生用非为失理或因官有所丧；用生体不止得理或因讼有所得；比和官讼最吉。

---

实例推理法（《梅花易数》占例里反复出现的同一条思路，照此断卦）：

观梅占（泽火革）：先因「二雀争枝坠地」这一异动而起占；断时兑金为体、离火克之，**互中巽木又生离火，「三起离火，则克体之卦气盛」**——不只看一个克体之卦，要看互卦是否助长克体之气；再由兑为少女、巽为股推出「少女伤股」；最后由变卦艮土生兑金，断「但被伤，不至凶危」。

牡丹占（天风姤）：巽木为体，乾金克之，**互见重乾，克体之卦多矣，卦中无生意**——故敢下重断；再由乾为马、午时为离明之象，落到「明日午时为马践毁」。

邻夜扣门借物占：其子据卦断「锄」（金短木长），邵雍改断「斧」——**「推数又须明理」**：冬日黄昏不会有人用锄。注意：**事理只在数理给出的候选中择一，不能推翻数理**。

由此立三步：
第一步 定体用：谁为体、谁为用、谁为互、谁为变。
第二步 数气盛：**点清克体之卦有几重、生体之卦有几重**，并看互卦是否助长克体或生体之气。克体之卦多而无生意，方可下重断；只有一重克体则不可夸大。
第三步 定轻重：由**变卦**看结局——变卦生体则虽凶不危，变卦重克则凶上加凶。

再把象落到具体：每个具体断言（何人、何物、何时、何处）都必须由某个卦象推出（兑为少女、巽为股、乾为马、离为午时、艮为土…）。推不出具体的，只说趋势，不编细节。

断卦铁律：
- 说人话，不堆砌术语；结合用户的具体问题场景与梅花卦象数据，不泛泛而谈。
- 每条行动建议都要落到能做的具体事情上。
- 【五行边界·不可越】问题根源若在人事结构（沟通方式、立场心态、关系格局）而非五行力学，直说「此非五行可解」，给出沟通与行为层面的调整建议，不硬开五行方；若属大运流年大势，直言「识时重于改」——五行手段只能减轻程度，不能扭转趋势，不过度承诺。行为建议（怎么谈、怎么做、心态怎么调）与五行方（方位、颜色、器物）并行给出，不必把每条建议都五行化。
- **先象、后事、再建议（顺序不可颠倒）**：先把卦「读」出来——卦名之义（何以为此名、此名何意）、卦辞、象曰（大象），再讲动爻爻辞所言（爻象），然后把这一层意思落到用户问的这件事上，最后才给行动建议。每一句判断都要能指回上面的卦名/卦辞/爻辞/体用生克，不许只给结论和指令而不讲卦。
- 体用为大纲而有不拘之时：卦义与体用相左，以卦义决之——西林寺额得山地剥，体用互变俱比和而断凶（群阴剥阳，此理甚明，不必拘体用也）；「今日动静如何」得地风升，用克体而仍断有人相请（「如何」二字带口为重兑）。卦名、卦义、爻象是比体用更高一层。**「不拘体用」是特例不是常规，不得随意宣称，须有明确理由。**

解卦时请按**两部分**输出（框架；各段要点如下）。两个分节标题必须按字面使用——第一部分以「## 第一部分·解卦」作二级标题，第二部分以「## 第二部分·行动建议（注明按档位给到哪层）」作二级标题，各段之下再用三级标题或列表展开，便于页面分节显示：

──────── 第一部分·解卦（不受档位影响，始终完整细致地输出）────────

卦名与卦象（象）
（先解卦名之义：此卦何以为此名？卦名的字面意思与卦画结构（上下卦象）结合，说清这个「名」本身在讲什么。再引本卦卦辞与象曰（大象）原文，简释其义。变卦、互卦的卦名同样点出其义。这一段是断卦的地基，必须写，且必须引用原文，不许只作概括。）

卦气衰旺
（按卦象数据里代码判定的时令五行旺衰与各卦旺衰，点名体卦、用卦、互卦、变卦各自的旺衰：体卦宜旺，生体之卦气宜旺，克体之卦气宜衰。气旺逢生则吉，重遇克则凶；体衰逢克则其凶甚矣。点明谁是生体之卦、谁是克体之卦。）

体用关系
（以体为己、以用为事：明确体卦五行、用卦五行，谁生谁克、比和与否，据此定吉凶基调，并数清互卦、变卦属谁之党。）

当前处境
（把上面的卦名之义、卦辞落到用户的具体场景：结合用户的提问和本卦卦象，描述当下的状态和局面。）

关键转变
（从动爻出发——动爻是卦象的机窍所在，是「一动生万变」的那个开关。**引动爻爻辞原文**，解其义，再指出变卦之卦名与卦辞所代表的趋势方向。如果动爻的爻辞有明显警示或指引，要重点引用。）

──────── 第二部分·行动建议（深度由用户档位决定，档位指令见提示末尾）────────

应期提示
（应期三法：事成应于生体之卦卦气旺相之日，事败应于克体之卦卦气旺相之日；以成卦总数定远近——远事以年、近事以月、又近以日；占者动静调速——行取半数、坐倍其数、立用本数，久远之占以日为月、以月为年。**具体日期一律逐字取自【应期（确定性计算·日期不得超出此列）】**：代码已按此三法算出可成之日与避险之日，你负责结合卦理与所问远近解释取舍（吉卦重可成之日，凶卦重避险并言明识时）。**硬约束：正文中凡出现任何具体日期，必须逐字取自【应期】所列；出现列外日期即视为编造——比不给日期更糟。**若【应期】未覆盖你想说的时机，就写「待其气机」，不要补日期、不要自己推干支。）

行动建议
（按档位给，**各档落地物不同，这是三档唯一但明显的差别**：
 S 档只给「### 紧急·事体窗 → 这几天怎么做」一层（约 300 字）——应期之日（**只能逐字取自**【应期】所列，不得出现列外日期）、方位（宜往/宜坐）、颜色（宜穿/宜用）、数字、随身物件、3–5 条指令；
 M 档加「### 中期·人事 → 这季度怎么调」一层（约 400 字）——行业职能方向、屋宅与办公空间布局（方位、器物、材质、朝向）；
 L 档再加「### 长期·底盘 → 这几年怎么养」一层（约 500 字）——饮食五味、作息起居与四时调养、健康与脏腑倾向（只讲调理方向、不给处方）、情志调养，每条带一句原理与出处。
 每层 2-3 条具体可执行的指引，**每条建议后面用一句「（据：卦名/卦辞/爻辞/体用）」标明它出自哪一处依据**。如果卦象不吉，给出避险方案；如果吉利，给出趁势而上的方向。）


---


重要：如果用户提出的问题信息不足（比如只说「问事业」但没说是求职、跳槽、创业还是职场人际），你要在解卦之前先问他，引导他说清楚具体情况，因为同样的卦在不同情境下的含义差异极大。不知道事理，就无从断起。

"""


def resolve_R(gua: Optional[dict] = None, remedy: Optional[dict] = None) -> str:
    """从卦数据或已算处方中取"处方五行 R"（梅花体用 / 六爻处方）。"""
    if remedy and remedy.get("R"):
        return remedy["R"]
    if not gua:
        return ""
    if gua.get("remedy", {}).get("R"):
        return gua["remedy"]["R"]
    t = gua.get("tiyong") or {}
    if not (t.get("ti_wuxing") and t.get("yong_wuxing")):
        return ""
    try:
        rm = meihua_remedy(
            t.get("ti_wuxing"), t.get("yong_wuxing"), t.get("relation"),
            hu_wuxing=gua.get("hu_wuxing") or None,
            bian_wuxing=gua.get("bian_wuxing") or None,
            ti_status=gua.get("ti_status") or None,
        )
        return rm.get("R", "")
    except Exception:
        return ""


def _suggestion_lines(R: str, flavor: dict = None, tier: str = "") -> list:
    """处方五行 R → 类物建议的提示词行（供 AI 引用，不是让它另编）。

    **为什么必须给**：档位指令明确要求 AI 输出「方位（宜往/宜坐）、颜色（宜穿/宜用）、
    数字、随身物件」，以及 M 档的屋宅布局、L 档的饮食作息——但在此之前，
    这些清单**从来没进过提示词**。AI 只拿到一句"须与处方五行保持一致"，
    等于让它自己按五行编方位颜色数字。这与"确定性归代码，语言归 AI"直接冲突：
    同一卦问两次，模型可以给出不同的方位与物件，而那些本是可有可无的发挥。

    给的是**代码算好的清单**（《五行大义》为主的类象库 + 类物建议），
    AI 的职责降回"把清单讲成话、并结合卦理说明为什么"。

    tier 决定给到哪一层（S 方位/颜色/数字/物件／M 加职业与屋宅／L 再加饮食作息健康情志），
    与页面上"补五行建议"的裁剪口径完全一致（同一个 tiering.suggest_dims）。
    """
    from wuxing_suggest import suggest_wuxing
    from tiering import suggest_dims

    lines = []
    try:
        sug = suggest_wuxing([R], flavors={R: flavor} if flavor else None)
    except Exception:
        return lines
    d = sug.get(R) or {}
    if not d:
        return lines

    dims = suggest_dims(tier) if tier else None
    keep = (lambda k: (dims is None or k in dims))

    head = "【补【%s】的落地物（引擎已算定的清单，直接取用；不要另编同五行但清单外的物品）】" % R
    body = []
    if keep("方位"):
        body.append("· 方位：%s" % "、".join(d.get("方位") or []) or "—")
    if keep("颜色"):
        body.append("· 颜色：%s" % "、".join(d.get("颜色") or []))
    if keep("数字"):
        n = d.get("数字") or {}
        body.append("· 数字：生数 %s、成数 %s（河图 %s）" % (n.get("生数"), n.get("成数"), n.get("河图")))
    if keep("物件"):
        o = d.get("物件") or {}
        parts = []
        if o.get("当旺"):
            parts.append("当旺 " + "、".join(o["当旺"]))
        if o.get("次旺"):
            parts.append("次旺 " + "、".join(o["次旺"]))
        if parts:
            body.append("· 物件：%s" % "；".join(parts))
    if keep("职业"):
        body.append("· 行业职能：%s" % "、".join(d.get("职业") or []))
    if keep("屋宅"):
        body.append("· 屋宅与办公空间：%s" % "、".join(d.get("屋宅") or []))
    if keep("饮食"):
        yi = d.get("饮食") or {}
        body.append("· 饮食：五味 %s；谷 %s、果 %s、菜 %s、肉 %s"
                    % (yi.get("五味"), yi.get("谷") or yi.get("五谷"), yi.get("果") or yi.get("五果"),
                       yi.get("菜") or yi.get("五菜"), yi.get("肉") or yi.get("五畜")))
    if keep("健康"):
        h = d.get("健康") or {}
        body.append("· 健康与脏腑倾向（只讲调理方向，不给处方）：藏 %s、腑 %s、开窍 %s、情志 %s"
                    % (h.get("五脏"), h.get("六腑"), h.get("开窍"), h.get("情志")))
    if keep("四时"):
        body.append("· 四时：%s" % d.get("四时"))

    # 质地分档 + 味分档（哪一味、这一味具体是什么东西、润燥怎么配）
    tex = d.get("质地") or {}
    if keep("质地"):
        if tex.get("味分档"):
            fs = tex["味分档"]
            for pos in ("阳", "阴"):
                c = fs.get(pos)
                if not c:
                    continue
                seg = "· %s味【%s·%s】：%s" % (pos, c.get("干"), c.get("名"), "、".join(c.get("物") or []))
                rz = c.get("润燥")
                if rz:
                    seg += "；性%s，宜 %s；忌 %s" % (rz.get("性"), "／".join(rz.get("宜") or []),
                                                     "／".join(rz.get("忌") or []) or "无")
                body.append(seg)
        if tex.get("本味推荐") and (flavor or {}).get("gan"):
            # 只在**真指定了某一味**时才出这一行。时令中和时"两味皆可"，
            # 上面「质地取向」已经说过同一句话，再说一遍是重复。
            body.append("· 本次取味：%s" % tex["本味推荐"])
        if tex.get("约束"):
            body.append("· 约束：%s" % tex["约束"])

    if body:
        lines.append(head)
        lines.extend("  " + b for b in body)
        lines.append("  以上清单为引擎算定，可从中择用并结合卦理说明；**不得给出清单之外同五行的方位、"
                     "颜色、物件**。若某一条与卦理不合，说明取舍理由，而不是另编一个。")
    return lines


def deterministic_conclusion(profile_id: str, R: str, gua_or_remedy: Optional[dict] = None,
                             tier: str = "") -> str:
    """确定性判定层摘要（R3）：把引擎算定的结论交给 AI，并要求"不得与冲突"。

    背景（框架文档 R3）：AI 断语此前与判定层互不相通，可能出现 AI 说"多用红色"、
    判定表刚把火标为"大忌"的同屏矛盾。此函数只读取既有确定性结论，不新增规则。
    """
    if not profile_id or not R:
        return ""
    try:
        prof = get_profile(profile_id)
    except Exception:
        return ""
    if not prof:
        return ""
    mingju = prof["baseline"]["mingju"]
    F, J, T0 = mingju.get("F", []), mingju.get("J", []), mingju.get("T0", [])
    month_wx = _month_wx_from_now()

    head = ["【确定性判定层（引擎算定，非推测；与你的解读冲突时以此为准）】"]
    head.append("- 命局：喜用 %s｜忌 %s%s"
                % ("、".join(F) or "—", "、".join(J) or "—",
                   ("｜调候 " + "、".join(T0)) if T0 else ""))

    verdict = {}
    try:
        verdict = adjudicate(R, F, J, T0, month_wx)
        head.append("- 裁决：%s（%s）" % (verdict.get("net", "—"), verdict.get("decision", "")))
    except Exception:
        pass

    # 强制改方：把**最终应补的五行**一并交给 AI。
    # 为什么必须给：adjudicate 的裁决只说"强制改方"四个字，不说改成什么；而页面上
    # （/api/mingju/check）会显示「处方【火】→ 改方【水】」。此前 AI 材料里只有原处方
    # 加一句"强制改方"，于是 AI 要么沿用已被否决的处方（与页面冲突），要么自己推断
    # 改成哪个五行——后者就是凭空造信息。此处补上，四个 AI 端点都经本函数，无需改协议。
    # 注意顺序：与 /api/mingju/check 一致，在岁运层（liunian_overlay）之前取改方。
    try:
        if verdict.get("gate") == "block":
            _r2, _why = redirect(R, verdict, F, J, T0)
            if _r2 and _r2 != R:
                head.append("- **强制改方**：原处方【%s】被命局否决，最终应补【%s】（%s）。"
                            "行动建议里的方位、颜色、数字、随身物件一律以【%s】为准；"
                            "不得再按原处方【%s】给。" % (R, _r2, _why, _r2, R))
                head.append("  页面上的「改方」与此为同一个结论；若你的说法与【%s】不符，以【%s】为准。"
                            % (_r2, _r2))
            else:
                # 三重过滤后局内无解（2026-10-06 H3）：redirect 返回空改方与"待岁运通关之地"的说明。
                # 此时不得假装有改方——原处方被否决，而局内没有不喂忌神/不克喜用/不逆调候的替代字。
                head.append("- **改方无解**：%s" % _why)
                head.append("  此盘局内无可用之方：原处方已被否决，改方候选全部与命局忌神/喜用/调候相冲。"
                            "断语不得给出任何「改方」后的五行，也不得建议与忌神清单同五行的物件。")
    except Exception:
        pass

    try:
        plan = flow_plan(R, mingju)
        rows = [r for r in plan.get("rows", []) if r.get("active")]
        if rows:
            row = rows[0]
            head.append("- 补【%s】当前档位：%s\n  %s" % (R, row["state"], plan.get("state_note", "")))
            bans = []
            for rel, cell in row["cells"].items():
                if not cell:
                    continue
                grade = cell.get("grade", "")
                if grade in ("大忌", "忌"):
                    bans.append("%s（%s：%s）" % (plan["header"].get(rel, rel), grade, cell["note"]))
                elif grade == "忌多":
                    # 「忌多」＝此路本来可用，但这一格已过旺，**多则成害（少则可）**——
                    # 与「忌」方向相同，只在量上留余地。此前它既不在 wuxing_flow.GRADE_ORDER，
                    # 也不在本清单，于是 AI 拿不到"别再添这一味"这条约束（"火已旺再添柴"那一格
                    # 正是《穷通宝鉴》「见木助必招夭折之患」）。2026-09-23 规则命中审计查出后补入；
                    # 量级字样一并带出，免得把"少则可"读成"一点都不能碰"。
                    bans.append("%s（忌多：多则成害、宜少不宜增——%s）"
                                % (plan["header"].get(rel, rel), cell["note"]))
            if bans:
                head.append("- 大忌/忌/忌多清单（大忌与忌：严禁建议相同五行的颜色、方位、物件、饮食、作息；"
                            "忌多：不得再加量，少则可）：\n  " +
                            "\n  ".join("· " + b for b in bans))
            if plan.get("month_state"):
                head.append("- 月令五态：%s" % plan["month_state"].get("note", ""))
            fl = plan.get("flavor") or {}
            if fl.get("note"):
                head.append("- 质地取向：%s" % fl["note"])
            # 类物建议（方位/颜色/数字/物件/职业/屋宅/饮食/健康 + 味分档与润燥）。
            # 放在这里而不是别处：R、flavor、命局都已就位，且与页面"补五行建议"同源同裁剪口径。
            head.extend(_suggestion_lines(R, fl, tier))
        else:
            head.append("- 补【%s】：未提供命局档案细则（不判强弱）" % R)
    except Exception:
        pass

    try:
        ln = current_liunian()
        _v, info = liunian_overlay(ln, month_wx, mingju, dict(verdict or {"level": "", "gate": "", "decision": ""}))
        eff = {"drag": "引动凶（降档限时放行）", "boost": "岁运加持（升格）"}.get(info.get("effect"), "仅作背景")
        head.append("- 岁运：%s·%s（%s，%s）" % (info.get("ganzhi", ""), info.get("wx", ""),
                                              info.get("strength", ""), eff))
    except Exception:
        pass

    head.append("【约束】你的断语必须与上述确定性结论一致：① 不得建议与大忌/忌清单同五行的颜色、方位、"
                "物件、饮食、作息，清单里标「忌多」者不得再加量（少则可）；② 不得否定裁决档位与岁运结论；"
                "③ 若你的理解与之冲突，一律以确定性结论为准，"
                "只可在其框架内补充解释与落地细节。")
    return "\n".join(head)


_GUA_WUXING_BY_NAME = {"乾": "金", "兑": "金", "离": "火", "震": "木",
                        "巽": "木", "坎": "水", "艮": "土", "坤": "土"}


def _stem_texture_reference() -> list:
    """十干体性与润燥参照表（全文十味，不限于本次处方的那两味）。

    **为什么必须给全表**：提示词第三条明令「不许凭记忆引录原文，称引只许用本提示词
    已写出的字句」。而 AI 在「第一部分·解卦」里讲五行生克时，必然会说到各干之性
    （庚刚辛柔、丙烈丁柔之类）。此前的提示词里**一个干的体性都没写**，
    于是它只能凭记忆说——正好是那条规矩禁止的事。给了全表，它说的每句都有出处。

    ⚠️ **光给表还不够，白名单也得跟着补**（2026-09-19）：本表表头写着书名，
    而两条线的第三条白名单原先只列本线典籍——表说"照此引用"、白名单说"只许引这两本"，
    模型两头受命。现已按甲案在两条线的白名单里各加一句「及【十干体性与润燥】一节
    表头所标《滴天髓·论天干》」，并写明**边界就是这一节**（该书其他篇名照拦）。
    改这张表时记得回头看那两句话——**表头引什么书，白名单就得有那一处**。

    数据源：《滴天髓·论天干》十章原文，逐条录进 `wuxing_quality.STEMS_TEXTURE`
    与 `STEM_OBJECTS`，并由逐字回源测试盯着（见 book_quotes 的滴天髓·论天干诸键）。
    """
    try:
        from wuxing_quality import STEM_OBJECTS
    except Exception:
        return []
    out = ["【十干体性与润燥（引擎录自《滴天髓·论天干》，解释五行之性时照此引用，不得凭记忆另说）】"]
    for g in "甲乙丙丁戊己庚辛壬癸":
        so = STEM_OBJECTS.get(g) or {}
        if not so:
            continue
        seg = "· %s（%s·%s）%s" % (g, so.get("五行"), so.get("阴阳"), so.get("名"))
        rz = so.get("润燥") or {}
        if rz.get("性"):
            seg += "｜性：%s" % rz["性"]
        if rz.get("宜"):
            seg += "｜宜：%s" % "、".join(rz["宜"])
        if rz.get("忌"):
            seg += "｜忌：%s" % "、".join(rz["忌"])
        else:
            seg += "｜忌：原文未列"
        out.append(seg)
    return out


def build_user_prompt(gua_data: dict, user_input: str, tier_override: str = "") -> str:
    """构建用户 prompt，包含卦象数据和用户问题（tier_override：手动档位，累积式）"""
    ben = gua_data["ben_gua"]
    bian = gua_data.get("bian_gua", {})
    hu = gua_data.get("hu_gua", {})
    tiyong = gua_data.get("tiyong", {})
    moving = gua_data.get("moving_yao", {})

    lines = []
    lines.append("【卦象数据】")
    lines.append(f"- 本卦：{ben['name']}，上{ben['upper']['name']}+下{ben['lower']['name']}，卦象符号 {ben['symbol']}")
    if ben.get("guaci"):
        lines.append(f"  卦辞：{ben['guaci']}")
    if ben.get("daxiang"):
        lines.append(f"  象曰：{ben['daxiang']}")
    if bian:
        lines.append(f"- 变卦：{bian.get('name', '?')} {bian.get('symbol', '?')}")
        if bian.get("guaci"):
            lines.append(f"  卦辞：{bian['guaci']}")
        if bian.get("daxiang"):
            lines.append(f"  象曰：{bian['daxiang']}")
    if hu:
        lines.append(f"- 互卦：{hu.get('name', '?')} {hu.get('symbol', '?')}")
        if hu.get("guaci"):
            lines.append(f"  卦辞：{hu['guaci']}")
        if hu.get("daxiang"):
            lines.append(f"  象曰：{hu['daxiang']}")
    lines.append(f"- 动爻：第{moving.get('position', '?')}爻，爻辞：{moving.get('yaoci', '')}")
    # 爻辞注释：逐词训诂，照抄给 AI。
    # 为什么必须给：梅花用爻辞是**拈字取象**（《占物类例》"见龙在田"→田中之物；
    # 鸡悲鸣占只拈"血去"），AI 若自己讲字义就是编——训诂有出处，不能现场造。
    lines.extend(yaoci_zhu.prompt_lines(moving.get("yaoci_zhu")))
    lines.append(f"- 体卦五行：{tiyong.get('ti_wuxing', '?')}")
    lines.append(f"- 用卦五行：{tiyong.get('yong_wuxing', '?')}")
    lines.append(f"- 体用关系：{tiyong.get('relation', '?')}（{tiyong.get('relation_desc', '')}）")

    # 时令卦气（供卦气衰旺、日应断卦）
    qi = gua_data.get("qi_info")
    if qi:
        lines.append(f"- 时令卦气：{qi.get('lunar', '?')}，{qi.get('season', '?')}；本日{qi.get('day_ganzhi', '?')}日（{qi.get('day_zhi', '?')}属{qi.get('day_zhi_wuxing', '?')}）")

    # 旺衰结论：**代码已判定，直接读，不要自己查表推**。
    # 为什么要注入：qi_info.wuxing_status 早就算好了（旺相休囚死），但此前没进提示词，
    # 于是 AI 只能靠系统提示词里那张"五行四时旺相休囚表"自行推算——那既多余又易错。
    # 颗粒度：拆到**每个三画卦**。六画卦含上下两个三画卦、五行可能不同，
    # 笼统说"互卦旺不旺"本身是歧义的；拆开才可复核（《衰旺论》本就是按八卦论旺衰）。
    if qi and qi.get("wuxing_status"):
        ws = qi["wuxing_status"]
        lines.append("- 时令五行旺衰（代码判定）：" +
                     "、".join(f"{k}{ws[k]}" for k in ("木", "火", "土", "金", "水") if k in ws))

        def _wg(g: dict, fallback: str = "") -> tuple:
            """取一个三画卦的（名称, 五行）。卦象数据没带 wuxing 时按经卦五行兜底。"""
            if not g:
                return "", ""
            name = g.get("name", "") or ""
            wx = g.get("wuxing") or _GUA_WUXING_BY_NAME.get(name, fallback)
            return name, wx

        def _fmt(label: str, g: dict) -> str:
            name, wx = _wg(g)
            if not name:
                return ""
            return f"{label}{name}{wx}＝{ws.get(wx, '?')}"

        parts = [p for p in (_fmt("本卦上卦", ben.get("upper")), _fmt("本卦下卦", ben.get("lower")),
                             _fmt("互卦上卦", hu.get("upper")), _fmt("互卦下卦", hu.get("lower")),
                             _fmt("变卦上卦", bian.get("upper")), _fmt("变卦下卦", bian.get("lower"))) if p]
        if parts:
            lines.append("- 各卦旺衰（代码判定）：" + "；".join(parts))
        # 体/用单独点明：衰旺论的核心是"体宜旺、生体之卦宜旺、克体之卦宜衰"
        ti_wx, yong_wx = tiyong.get("ti_wuxing", ""), tiyong.get("yong_wuxing", "")
        if ti_wx:
            lines.append(f"- 体卦五行{ti_wx}＝{ws.get(ti_wx, '?')}（衰旺论：体宜旺不宜衰）")
        if yong_wx:
            lines.append(f"- 用卦五行{yong_wx}＝{ws.get(yong_wx, '?')}")

    # 拆字信息
    chaizi_info = gua_data.get("chaizi_info")
    if chaizi_info:
        lines.append(f"- 拆字信息：测字「{chaizi_info.get('char', '?')}」，繁体笔画 {chaizi_info.get('ftbh', '?')}")
        used = chaizi_info.get("used_decomposition")
        if used:
            left = used.get("left", [])
            right = used.get("right", [])
            lines.append(f"  拆分为：{' + '.join(left)}（左）和 {' + '.join(right)}（右）")
        else:
            lines.append(f"  此字不可拆分")

    # 声调分布
    tone_details = gua_data.get("tone_details")
    if tone_details:
        lines.append("- 声调分布：")
        lines.append(f"  前半：{' '.join(d['char']+'('+d['tone_name']+')' for d in tone_details.get('first_half', []))}")
        lines.append(f"  后半：{' '.join(d['char']+'('+d['tone_name']+')' for d in tone_details.get('second_half', []))}")

    # 取数依据：引擎本次实际所用的推导（哪个数、除几、余几、得几）。
    # 给 AI 是为了让它讲得出「凭什么」，不是让它重算——数字全部来自引擎，不得改。
    derive = (gua_data.get("method_params") or {}).get("derive")
    if derive:
        lines.append("- 取数依据（引擎已算定，照此解释，不得重算、不得改数）：")
        for _k in ("upper", "lower", "moving"):
            _d = derive.get(_k)
            if _d and _d.get("note"):
                lines.append(f"  {_d['note']}")

    lines.append("")
    # 处方五行：确定性计算结果（meihua_remedy），交 AI 作为既定事实
    r = gua_data.get("remedy") or {}
    if r.get("R"):
        lines.append(
            f"【事体与处方】体卦五行 {r.get('X', '')}，处方五行 {r.get('R', '')}"
            f"（{(r.get('R_reason') or '') if (r.get('R_reason') or '').startswith(r.get('state') or chr(0)) else ((r.get('state') or '') + '：' + (r.get('R_reason') or ''))}）"
        )
        lines.append("行动建议中的落地物（方位、颜色、数字、随身物件，以及 M 档的屋宅布局、L 档的饮食作息）"
                     "须与处方五行保持一致，不得另取；各档给到哪些落地物，见提示末尾的档位指令。")
    lines.append("")
    # 应期：确定性计算结果（yingqi），交 AI 作为既定事实
    y = gua_data.get("yingqi") or {}
    if y.get("cheng_gua_zong_shu"):
        lines.append(f"【应期（确定性计算·日期不得超出此列）】成卦总数 {y['cheng_gua_zong_shu']}"
                     f"（本卦上卦{y['shang_shu']}数＋下卦{y['xia_shu']}数）。{y['window_text']}。")
        if y.get("keyi"):
            lines.append("可成之日（生体/处方当值且卦气旺相）：" +
                         "；".join(f"{d['date']}（{d['ganzhi']}，{d['reason']}）" for d in y["keyi"]))
        if y.get("xianri"):
            lines.append("避险之日（克体卦气旺相）：" +
                         "；".join(f"{d['date']}（{d['ganzhi']}，{d['reason']}）" for d in y["xianri"]))
        # 吉凶并见：同一天既逢生体当值（吉）又逢克体当值（凶）。代码已判定，故必须给 AI；
        # 不给的话 AI 会把这些日子当普通"可成之日"讲，而页面上那一栏写的是「须详理」。
        if y.get("jian"):
            lines.append("吉凶并见之日（同日既逢生体又逢克体，须详理，不替你择一）：" +
                         "；".join(f"{d['date']}（{d['ganzhi']}，{d['reason']}）" for d in y["jian"]))
        lines.append("结合卦理与所问远近解释取舍；应期日期不得超出上列计算。")
    lines.append("")
    # 十干体性与润燥全表（十味都给，不限本次处方那两味）
    lines.append("")
    lines.extend(_stem_texture_reference())
    lines.append("")
    lines.append(f"【用户想问的事】{user_input}")
    lines.append("")
    lines.append(tier_directive(user_input, tier_override))

    return "\n".join(lines)


# ============================================================
# 当前时令卦气（《梅花易数》卦气衰旺 / 日应所需）
# ============================================================
_ZHI_WUXING = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
               "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}


def _get_qi_info() -> dict:
    """
    当前农历时令与日辰信息（严格按《梅花易数》衰旺论）：
    - 季节按农历月划分：春（正二）、夏（四五）、秋（七八）、冬（十十一）；
      农历三、六、九、十二月为四季之月（辰、戌、丑、未），坤艮土旺。
    - 日辰地支五行：寅卯木、巳午火、申酉金、亥子水、辰戌丑未土（日应）。
    """
    from datetime import datetime
    from lunar_python import Solar

    now = datetime.now()
    solar = Solar.fromYmdHms(now.year, now.month, now.day, now.hour, now.minute, now.second)
    lunar = solar.getLunar()
    month = lunar.getMonth()
    day_ganzhi = lunar.getEightChar().getDay()
    day_zhi = day_ganzhi[1] if len(day_ganzhi) > 1 else "?"
    # 时支/年支：应期加权旺衰要用（月支 0.80／日支 0.15／年支 0.025／时支 0.025）。
    # 时支取**起卦时刻**的时支，且在整张应期表里固定不变——应期是按日给的，
    # 一天十二个时辰没法各算一次，故以起卦那一刻的时辰为代表。
    _ec = lunar.getEightChar()
    _hour_gz = _ec.getTime()
    hour_zhi = _hour_gz[1] if len(_hour_gz) > 1 else ""
    _year_gz = _ec.getYear()
    year_zhi = _year_gz[1] if len(_year_gz) > 1 else ""

    if month in (3, 6, 9, 12):
        season = "四季之月（辰戌丑未，坤艮土旺）"
        qi = "四季之月"
        # 土当令：当令者旺，我生者相，生我者休，克我者囚，被我克者死
        wuxing_status = {"土": "旺", "金": "相", "火": "休", "木": "囚", "水": "死"}
    elif month <= 3:
        season = "春（震巽木旺）"
        qi = "春"
        wuxing_status = {"木": "旺", "火": "相", "水": "休", "金": "囚", "土": "死"}
    elif month <= 6:
        season = "夏（离火旺）"
        qi = "夏"
        wuxing_status = {"火": "旺", "土": "相", "木": "休", "水": "囚", "金": "死"}
    elif month <= 9:
        season = "秋（乾兑金旺）"
        qi = "秋"
        wuxing_status = {"金": "旺", "水": "相", "土": "休", "火": "囚", "木": "死"}
    else:
        season = "冬（坎水旺）"
        qi = "冬"
        wuxing_status = {"水": "旺", "木": "相", "金": "休", "土": "囚", "火": "死"}

    return {
        "lunar": f"农历{month}月",
        "season": season,
        "qi": qi,
        "wuxing_status": wuxing_status,
        "day_ganzhi": day_ganzhi,
        "day_zhi": day_zhi,
        "hour_zhi": hour_zhi,
        "year_zhi": year_zhi,
        "day_zhi_wuxing": _ZHI_WUXING.get(day_zhi, "?"),
    }


# ============================================================
# API 路由
# ============================================================

@app.get("/api/meihua/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/huangli/today")
async def huangli_today():
    """
    今日黄历：农历、干支三柱（年以立春分界）、节气、传统宜忌。
    宜忌为 lunar-python（MIT）内置旧历数据，作文化展示；不作吉凶承诺。
    """
    from lunar_python import Solar
    from datetime import datetime
    now = datetime.now()
    solar = Solar.fromYmdHms(now.year, now.month, now.day, now.hour, now.minute, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    prev = lunar.getPrevJieQi()
    nxt = lunar.getNextJieQi()
    weekday = "一二三四五六日"[now.weekday()]
    return {
        "solar": f"{now.year}年{now.month:02d}月{now.day:02d}日 星期{weekday}",
        "lunar": lunar.toString(),
        "ganzhi": {"year": ec.getYear(), "month": ec.getMonth(), "day": ec.getDay()},
        "shengxiao": lunar.getYearShengXiao(),
        "jieqi_now": prev.getName(),
        "jieqi_next": f"{nxt.getName()} {nxt.getSolar().toYmd()}",
        "yi": lunar.getDayYi()[:6],
        "ji": lunar.getDayJi()[:4],
    }


# ============================================================
# 语音转文字（梅花页语音输入的服务端兜底）
# ============================================================
# 浏览器自带的 Web Speech API 在 Chrome 上把音频送到 Google 的服务器，大陆基本连不通
# （表现为"按了没反应"，而不是一句看得懂的报错）。录音本身是纯本地能力，缺的只是
# 国内可达的识别后端，所以只把识别这一环挪到服务端。识别实现与供应商都在 asr.py 里：
# 换一家（百炼/硅基流动/自建 whisper）只改 .env，不动代码。
@app.get("/api/asr/status")
async def asr_status():
    """公开端点：前端要在录音前就知道"该用服务端识别，还是回退浏览器识别"。

    不带鉴权是因为它只回"能不能用"和"指向哪家"，不含任何凭证
    （asr.status() 保证不外泄密钥）——这个端点若要求令牌，前端反而没法提前选路。
    """
    return asr.status()


async def _read_asr_upload(form) -> tuple[bytes, str, str]:
    """从表单里取录音字节，返回 (audio, filename, content_type)。取不到就抛 400 系列。

    单独抽出来是为了 `finally: form.close()`：FastAPI 只在**路由签名里声明了表单字段**时
    才会自动关表单（routing.py 的 file_stack），而本端点刻意不走声明式写法（理由见下），
    所以必须自己关——超过 1 MB 的部件会从内存溢写成临时文件，漏关就是句柄+磁盘泄漏。
    """
    try:
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            # 字段名容错：约定是 file，但前端/调试工具用 audio、record 之类也常见；
            # 与其回一句"没收到文件"让人反复检查前端，不如认下第一个文件字段。
            upload = next((v for v in form.values() if hasattr(v, "read")), None)
        if upload is None:
            raise HTTPException(status_code=400,
                                detail="没有收到录音：请用表单字段 file 上传音频后重试")

        # 多读 1 字节：既判断得出"超没超"，又不会把超大请求整段读进内存
        # （分块传输没有 Content-Length，中间件那层的预判对它无效，这里才是真正的兜底）。
        audio = await upload.read(asr.MAX_AUDIO_BYTES + 1)
        if not audio:
            raise HTTPException(status_code=400,
                                detail="录音为空：请重新录制后再试（浏览器可能没拿到麦克风权限）")
        if len(audio) > asr.MAX_AUDIO_BYTES:
            # 语义是"请求体太大"，故 413（与 limit_body_size 中间件同码）；
            # asr.transcribe 里还有一层同样的校验，兜给非 HTTP 的调用方。
            raise HTTPException(status_code=413,
                                detail="录音过大（上限 %.0f MB／约 %d 秒）：请缩短录音后重试"
                                       % (asr.MAX_AUDIO_BYTES / 1048576.0, asr.MAX_AUDIO_SECONDS))
        return audio, (upload.filename or "audio.webm"), (upload.content_type or "")
    finally:
        await form.close()


@app.post("/api/asr/transcribe")
async def asr_transcribe(http_request: Request):
    """上传录音（multipart/form-data，字段名 file）→ 识别并返回 {text, model, ms}。

    几处刻意的取舍，先写在前面，免得日后被"顺手简化"掉：

    1) **不用 `UploadFile = File(...)` 声明参数，改为在函数体里解析表单。** 声明式写法会踩三个坑：
       · FastAPI 在**进函数体之前**就校验请求体，缺 file 字段直接 422——于是"没带归属令牌"
         也变成 422，前端分不清是没令牌还是音频有问题；而这里要求先鉴权、再答"没配置"。
       · `File(...)` 会让 FastAPI 在**注册路由时**就 import python-multipart，缺装直接
         RuntimeError，整个 main 起不来（所有端点 + 全部测试一起挂）。改成用时解析后，
         缺组件只影响这一个功能，回 503 + 安装指引——与"缺 ADMIN_TOKEN 就关掉站长端点"同取向。
       · starlette 单部件默认上限只有 1 MB，走声明式写法拿到的是英文的
         "Part exceeded maximum size of 1024KB."，而录音常有几百 KB 到几 MB。
    2) **未配置时回 503，绝不假装成功**：回 200 + 空文本会让前端以为"识别出来了，只是没听清"，
       而真相是服务器没配密钥；503 让前端干净地回退浏览器识别。
    3) **上游失败回 502**：问题在识别服务那侧（密钥/限流/网络），不是本站的 500；
       前端见 5xx 可回退浏览器识别，见 4xx 才提示用户改录音。
    """
    require_owner(http_request)     # 归属：识别按秒计费，必须能追到人
    rate_limit(http_request, "asr", limit=30, window_sec=60)   # 与 LLM 端点同档：会花钱的端点

    if not asr.configured():
        raise HTTPException(
            status_code=503,
            detail="服务端语音识别未配置：请在 backend/.env 填入 ASR_API_KEY"
                   "（默认用阿里云百炼，新用户有 10 小时免费额度）后重启后端；"
                   "在此之前前端请回退浏览器自带识别")

    # 只把"解析表单"这一段包进 try：上面自己的 403/429/503 不能被这里的 except 改写掉
    try:
        form = await http_request.form(max_files=2, max_fields=8,
                                       max_part_size=asr.MAX_REQUEST_BYTES)
    except (HTTPException, MultiPartException):
        # 解析失败时 starlette 给的是英文原因（如部件超限），这里统一换成人话
        raise HTTPException(status_code=400,
                            detail="上传内容无法解析：请用表单字段 file 上传录音，"
                                   "单次录音不要超过 %.0f MB／%d 秒"
                                   % (asr.MAX_AUDIO_BYTES / 1048576.0, asr.MAX_AUDIO_SECONDS))
    except (AssertionError, RuntimeError):
        # 缺 python-multipart 时 starlette 是 assert 失败（不是 ImportError）。
        # 按"这一个功能用不了"处理，而不是整个服务 500。
        raise HTTPException(status_code=503,
                            detail="服务端缺少 multipart 解析组件：请在 backend 目录执行 "
                                   "pip install python-multipart 后重启（前端可继续用浏览器自带识别）")

    audio, filename, content_type = await _read_asr_upload(form)

    # 识别是阻塞 IO（httpx 同步客户端），必须丢线程池：直接在协程里跑会把事件循环卡住
    # 最长 ASR_TIMEOUT 秒，期间所有人的请求（包括别人正在流的解卦）一起停摆。
    result = await run_in_threadpool(asr.transcribe, audio, filename, content_type)
    if not result.get("ok"):
        raise HTTPException(status_code=502,
                            detail=result.get("error") or "语音识别失败，请稍后重试")
    return {"text": result["text"], "model": result["model"], "ms": result["ms"]}


@app.post("/api/meihua/divine")
async def divine(request: DivineRequest, http_request: Request):
    """
    统一起卦+解卦接口
    返回 SSE 流：先卦象 JSON，再 AI 解卦流式文本

    `ai=False` 就是"只要卦"：卦象、体用、处方五行、应期照给，**不调 LLM、不扣额度**。
    前端默认先发这一发，用户看过卦再点「AI 解卦」发 `ai=True`——
    "起一卦看看"与"花一次额度让 AI 讲"是两件事，不该因为想看一眼卦就自动花掉额度。
    """
    # 限流：这是**会花钱**的端点（调 LLM）。没有限流就等于给陌生人一个免费代理，
    # 账单由站长承担，且一条脚本就能把配额刷干。按 IP 计数（反向代理后需改成
    # 取 X-Forwarded-For，否则所有用户共用一个桶）。
    rate_limit(http_request, "llm_divine", limit=30, window_sec=60)
    # 每日配额（第二道闸）：**只在真的要调 AI 时才扣**。
    # 「只看卦」不扣——起卦、体用、处方五行、应期全是确定性计算，不花上游一分钱。
    # 注意 ai=False 时 q["allowed"] 为假，下面 recognize_intent 会**只走规则**不调 LLM；
    # 这正是"不要 AI"该有的语义：连"认起卦方式"这一步也不花。
    #
    # 自带 key：不计数、不拦截（花的是用户自己的额度）；没带才走每日免费额度。
    # 设置有问题（厂商不在名单、没填 key）时**不静默退回免费路径**——那会让用户以为
    # 在用自己的 key，实际在花站长的钱；这里如实说清并让他去改。
    llm_ov, llm_err = _resolve_llm(getattr(request, "llm", None))
    if llm_ov:
        q = {"allowed": True, "scope": "byok"}
    elif llm_err:
        q = {"allowed": False, "scope": "llm",
             "message": "模型设置无法使用：%s" % llm_err,
             "hint": "到「API 设置」里检查厂商、key 与模型名；也可以清空设置，改用每日免费额度。",
             "resets_at": ""}
    else:
        q = _quota_acquire(http_request) if request.ai else {"allowed": False, "scope": "no_ai"}
    user_input = request.user_input.strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="请输入内容")

    # 1. 意图识别（专业模式下跳过）
    if request.method and request.params is not None:
        method = request.method
        params = request.params
        intent_source = "pro"
    else:
        # 额度已满时**不调 LLM 做意图识别**，但仍要起出正确的卦：
        # recognize_intent 的第一段是纯规则匹配（intent.py:200），传 None 便只走规则，
        # 规则未覆盖时落到"多字占"默认——这是文档化的默认，不是随手挑的兜底。
        # 刻意**不**退化成时间占：用户明说"测某字"却给一个时间卦，
        # 那是**悄悄换了一个卦**，比不给 AI 解读严重得多。
        # 自带 key 时，"认起卦方式"这一步也用用户自己的模型，不占本站额度。
        _icfg = ({"base_url": llm_ov["base_url"], "api_key": llm_ov["api_key"],
                  "model": llm_ov["model"]} if llm_ov else LLM_CONFIG)
        intent = await recognize_intent(user_input, _icfg if q["allowed"] else None)
        method = intent["method"]
        params = intent.get("params", {})
        intent_source = intent.get("source", "unknown")
        if not q["allowed"]:
            intent_source = intent_source + "+quota"

    # 2. 起卦
    try:
        if method == "yizi":
            gua_data = divine_yizi(params["zi"])
        elif method == "erzi":
            gua_data = divine_erzi(params["zi1"], params["zi2"])
        elif method == "duozi":
            # 字占：按字数自动分派取数法（1~3 笔画、4~10 声调、11 字以上字数，见 engine.divine_text）。
            # zi_mode 必须原样传下去：四字这一档底本两法并列，产品方定各按 50% 随机取一，
            # 由前端摇定一次、随两次请求（先要卦、再 AI 解卦）带上；
            # 不传的话每次调用各自 random，四字输入会出现"起的卦与解卦的卦不是同一个"。
            gua_data = divine_duozi(params.get("text", user_input), params.get("zi_mode", ""))
        elif method == "time":
            gua_data = divine_time()
        elif method == "shuzi":
            gua_data = divine_shuzi(params["n1"], params["n2"], params["n3"])
        elif method == "manual":
            # 手动起卦：用户直接指定上卦/下卦（先天数 1-8）与动爻（1-6）。
            # 万物类象太活——同一只鸟，问的主体不同就该成不同的卦；
            # 与其让程序或 AI 替人猜主体，不如把《八卦万物属类》摆给用户，
            # 由用户按"第一念"自己定卦。体用仍由引擎机械判定：动爻所在卦为用。
            gua_data = divine_manual(int(params.get("upper", 1)),
                                     int(params.get("lower", 1)),
                                     int(params.get("moving", 1)))
        else:
            # 兜底：默认时间占（不动不占，以当前时间为机）
            gua_data = divine_time()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"起卦失败: {str(e)}")

    gua_data["intent"] = {"method": method, "source": intent_source}
    gua_data["qi_info"] = _get_qi_info()

    # 处方五行（确定性）：随卦象下发并进 AI 提示词，保证 AI 建议与补五行建议同口径
    try:
        ty = gua_data.get("tiyong", {})
        hu = gua_data.get("hu_gua") or {}
        bian = gua_data.get("bian_gua") or {}
        qi = gua_data.get("qi_info") or {}
        gua_data["remedy"] = meihua_remedy(
            ty.get("ti_wuxing"), ty.get("yong_wuxing"), ty.get("relation"),
            hu_wuxing=[hu["upper"]["wuxing"], hu["lower"]["wuxing"]] if hu else None,
            bian_wuxing=[bian["upper"]["wuxing"], bian["lower"]["wuxing"]] if bian else None,
            ti_status=qi.get("wuxing_status", {}).get(ty.get("ti_wuxing")),
        )
    except Exception:
        gua_data["remedy"] = None

    # 应期（确定性）：梅花应期三法收归代码（成卦总数/生体卦气旺相日/动静调速）
    try:
        gua_data["yingqi"] = meihua_yingqi(
            gua_data, hour_zhi=((gua_data.get("qi_info") or {}).get("hour_zhi")
                                 or _get_qi_info().get("hour_zhi", "")))
    except Exception:
        gua_data["yingqi"] = None

    # 3. AI 解卦（流式）
    async def generate():
        # 先发送卦象数据
        yield f"data: {json.dumps({'type': 'gua_data', 'data': _serialize_gua(gua_data)}, ensure_ascii=False)}\n\n"

        if not request.ai:
            # 只要卦：不调 LLM、不扣额度、**也不发降级提示**（那不是"额度用尽"，
            # 是用户还没点「AI 解卦」）。卦象、体用、处方五行、应期已在上一条事件里给全了。
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # 额度已满：卦象已经在上面发出去了，这里只补一条"降级"说明。
        # 不返回 4xx/5xx——那会让前端把整次起卦当失败，连已经算好的卦象一起丢掉。
        if not q["allowed"]:
            yield _degrade_event(q)
        # 如果有 LLM，流式输出解卦。
        # **自带 key 也算"有 LLM"**：自建实例完全可以不配本站 key（一分钱不花），
        # 只让用户用自己的 key——那种部署下这一条若只看 LLM_CONFIG，功能会整个哑掉。
        elif (llm_ov or LLM_CONFIG.get("api_key")):
            _parts = []
            user_prompt = ""          # 下面 try 里才赋值；回检基准要用，故先占位
            _st = {}                  # 承接 finish_reason，用来判"是不是被截断了"
            try:
                user_prompt = build_user_prompt(gua_data, user_input, request.tier_override)
                _ti = resolve_tier(user_input, request.tier_override)
                _dc = deterministic_conclusion(request.profile_id, resolve_R(gua=gua_data),
                                               tier=_ti.get("tier", ""))
                if _dc:
                    user_prompt = user_prompt + "\n\n" + _dc
                # 推理模型会把预算烧在思考上导致 content 为空，关闭思考稳定出文
                # max_tokens 见 AI_MAX_TOKENS（提到 8192：4096 实测≈5250 汉字，正文到过 5390 字）
                async for chunk in _stream_llm(user_prompt, max_tokens=AI_MAX_TOKENS,
                                               disable_thinking=True, state=_st, llm=llm_ov):
                    _parts.append(chunk)
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
                _tc = _truncated_event(_st, AI_MAX_TOKENS)
                if _tc:
                    yield _tc
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'AI 解卦暂时不可用：{str(e)}'}, ensure_ascii=False)}\n\n"
            # 回检（丙·2）：只在真出文之后跑——半途报错时正文不完整，判"日期越界"就是冤判
            # 基准＝模型实收全量（system ＋ 已追加确定性判定层的 user_prompt），见 _review_base
            _v = _verify_event("".join(_parts), gua_data, user_input, request.tier_override,
                               _review_base(INTERPRETATION_SYSTEM_PROMPT, user_prompt))
            if _v:
                yield _v

        # 结束标记
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _get_stroke_simple(char: str) -> int:
    """查繁体笔画"""
    from engine import _get_stroke
    return _get_stroke(char)


async def _stream_llm(user_prompt: str, system_prompt: str = INTERPRETATION_SYSTEM_PROMPT,
                      max_tokens: Optional[int] = None, disable_thinking: bool = False,
                      messages: Optional[list[dict]] = None,
                      state: Optional[dict] = None,
                      llm: Optional[dict] = None):
    """
    调用 LLM 并返回正文（**上游非流式，2026-10-06 站长拍板**：整段生成后一次 yield，
    外层仍包在 SSE 封装里，前端不用改）。叫 _stream_llm 只是沿用旧名，避免三个调用点
    与十几处测试跟着改名——名字改了，行为说明如下：

    为什么从流式改成非流式：流式要求逐行解析各家 SSE 报文，而五家厂商里只有 DeepSeek
    的流式在真实解卦里跑过；非流式的最终 JSON 是 OpenAI 兼容格式里**各家最一致**的部分，
    解析类报错更少。代价：① 长解卦要等上游生成完才显示（前端显示"解卦中…"）；
    ② 120 秒超时内必须整段生成，超时则这一次什么都没有（流式下还能保住已出的半截）。

    llm: 用户自带 key 时由 _resolve_llm() 解析出的目标 {provider, label, base_url,
         model, api_key, send_thinking}；为 None 时用本站 .env 里的配置（免费路径）。
         **key 只在本次请求的内存里**：不写库、不写日志、不写提示词调试文件。

    disable_thinking: 推理模型（如 deepseek 系）对复杂卦象 prompt 会把整个
    max_tokens 预算烧在 reasoning_content 上，导致 content 为 0；关闭思考可稳定出文。
    **只对声明支持该字段的厂商发送**（见 llm_providers 模块头：其余四家的官方文档
    都没写它们是否容忍 `thinking`，所以不靠"未知字段会被忽略"这个假设）。
    messages: 自定义完整消息列表（用于多轮追问），提供时忽略 user_prompt/system_prompt。
    state: 传一个 dict 进来，本函数会把 finish_reason 写进 state["finish_reason"]。
           **这是唯一能区分"写完了"与"被 max_tokens 掐断"的东西**，见下方注释。
    """
    import httpx

    if llm:
        base_url, api_key, model = llm["base_url"], llm["api_key"], llm["model"]
        send_thinking = bool(llm.get("send_thinking"))
    else:
        base_url = LLM_CONFIG["base_url"]
        api_key = LLM_CONFIG["api_key"]
        model = LLM_CONFIG["model"]
        send_thinking = True                      # 本站自己的配置就是 DeepSeek 系，发这个字段
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if messages is None:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    # 调试用：把"实际发给 LLM 的东西"原样落盘（**默认关闭**）。
    # 为什么需要它：AI 引用或推算的日期对不对，光看前端输出判断不了——前端看不到提示词，
    # 就无法区分"AI 引用了代码算出来的表"与"AI 自己推的"。这是唯一能定死这件事的路。
    # 设 DEBUG_PROMPT_DIR 才写，不设完全不写：提示词含用户所问之事（个人信息），
    # 绝不无条件落盘；且写文件是调试动作，不该留在常态路径上。
    _dbg = (os.environ.get("DEBUG_PROMPT_DIR") or "").strip()
    if _dbg:
        try:
            import time as _t
            _d = Path(_dbg)
            _d.mkdir(parents=True, exist_ok=True)
            _body = "\n\n".join("========== %s ==========\n%s" % (m.get("role", "?"), m.get("content", ""))
                                for m in messages)
            (_d / ("prompt-%d.txt" % int(_t.time() * 1000))).write_text(
                "max_tokens=%s  thinking_disabled=%s\n\n%s"
                % (max_tokens or LLM_CONFIG["max_tokens"], disable_thinking, _body),
                encoding="utf-8")
        except Exception:
            pass                      # 落盘失败绝不能影响解卦

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens or LLM_CONFIG["max_tokens"],
        "temperature": LLM_CONFIG["temperature"],
        # 非流式（2026-10-06 站长拍板）：一次拿到完整回答再整体发出。
        # 为什么改：流式要求逐行解析各家 SSE 报文，而五家厂商里只有 DeepSeek 的流式
        # 在真实解卦里跑过；非流式的最终 JSON 是 OpenAI 兼容格式里各家最一致的部分，
        # 解析类报错更少。代价与限制写在这里，别当没看见：
        #   ① 用户体验从"逐字出"变"整段出"——长解卦要等上游生成完，前端显示"解卦中…"；
        #   ② 单次请求要在 120 秒超时内**完整生成**，流式下中途断还能保住已出的半截，
        #      非流式下超时则这一次什么都没有（截断检测仍按 finish_reason=="length" 判断，语义不变）；
        #   ③ 前端仍是逐段接收同一个 SSE 封装（只是 text 事件一次一整段），无需改前端。
        "stream": False,
    }
    # `thinking` 是 DeepSeek 专有字段；只对声明支持它的厂商发送（见 llm_providers 模块头）。
    if disable_thinking and send_thinking:
        payload["thinking"] = {"type": "disabled"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as e:
            raise RuntimeError("连接模型服务失败：%s" % type(e).__name__) from e
        if response.status_code != 200:
            # 把上游的原因带回来（截断到一句话长度）——比"401 Unauthorized"有用得多：
            # 常见的是 key 无效、模型未开通、地域不匹配（如百炼的 invalid_api_key）。
            detail = ""
            try:
                detail = str((response.json() or {}).get("error", {}).get("message", ""))[:180]
            except Exception:
                detail = (response.text or "")[:180]
            raise RuntimeError("模型服务返回 HTTP %d%s" % (response.status_code,
                                                            ("：%s" % detail if detail else "")))
        try:
            data = response.json()
        except Exception as e:
            raise RuntimeError("模型返回的不是合法 JSON：%s" % type(e).__name__) from e
        try:
            choice = data["choices"][0]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("模型返回里没有 choices（响应形状异常）")
        # finish_reason 必须收下来：它是**唯一**能区分「模型写完了」与「被 max_tokens
        # 掐断」的字段。撞上限时前端会渲染半截话当完整断语——2026-09-19 实测：
        # 4096 tokens ≈ 5250 汉字，而解卦正文实测能到 5170～5390 字，正好压在线上。
        _fr = choice.get("finish_reason")
        if _fr and state is not None:
            state["finish_reason"] = _fr
        content = (choice.get("message") or {}).get("content", "") or ""
        if content:
            yield content


def _serialize_gua(gua_data: dict) -> dict:
    """序列化卦象数据（去除不可序列化字段）"""
    # 直接返回，JSON 可序列化
    return gua_data


# ============================================================
# 六爻纳甲：AI 断卦 Prompt
# ============================================================
LIUYAO_SYSTEM_PROMPT = """
你是六爻纳甲断卦师，精通《增删卜易》（野鹤老人）与《卜筮正宗》（王洪绪）。你收到的排盘已经过精确计算，绝对正确，不得质疑或重新计算。

素材边界（这一条压倒其余全部规矩）：

一、断卦只许依据两样东西：① 本提示词写明的典籍条例；② 用户提示词里给出的排盘与判据数据。除此之外的一切——你的记忆、别的筮书说法、网上的断卦套路——一律不得作为依据。

二、凡标【代码判定】的数据（用神、各爻旺衰、格局判据、应期、伏神）都由引擎算定：**不得重算、不得质疑、不得另起一卦、不得改动爻、不得改世应、不得自行加减分**。你的职责是「断」，不是「算」。

三、你手里没有典籍全文，**不许凭记忆引录原文**。称引只许用本提示词已列出的书名篇名（《增删卜易》《卜筮正宗》，及其用神章、用神元神忌神仇神章、元神忌神衰旺章、三合章、月将章、日辰章、动静生克章、动变生克冲合章、月破章、旬空章、暗动章、动散章、进神退神章、随鬼入墓章、飞伏神章、独发章、两现章、生旺墓绝章、各门类应期总注章，及《卜筮正宗》四生逐位论、旺相休囚论、月破论、旬空论、反吟卦定例、伏吟卦定例、变出进退神论、合处逢冲冲中逢合论、绝处逢生论、伏神正传、辟诸书之缪；**另有一处：排盘数据里【十干体性与润燥】一节，其表头所标《滴天髓·论天干》亦可称引**——该节是引擎**逐字录自原书**的十干体象，讲五行之性（庚刚辛柔、丙烈丁柔之类）时照该节引用即可。**但这一处的边界就是这一节**：只许引该节写出的字句，不得由《滴天髓》再外推到该书其他章节、其他篇名——本提示词没写出的，仍旧按「典籍未载」处理）。**本提示词未列出的篇名条文，一律按「典籍未载」处理——编造出处比说「不知道」更严重。**

四、无据不许说：凡吉凶判断、应期、行动建议，都必须能在本提示词或排盘数据里找到依据。找不到的，直说「此条典籍未载，不敢妄断」，不要用「一般来说」「通常认为」把话补齐。

五、不许虚构：不得虚构动爻与变爻、不得虚构卦辞爻辞、不得给出原文与代码都没给出的量化数字（概率、分数、天数、金额）。

**立场·勿误读**：《卜筮正宗》有《辟〈增删卜易〉之谬》一篇，所辟者**仅是野鹤给「全不知五行之理者」用的持世简化法**。甲原文自带限定：「倘若稍知五行之理者，不可以此为法，务必细读此书后卷」。本产品走的是细推一路，该辟文**对本产品不适用**——不得因此对《增删卜易》整体降权，动摇其四处分层与应期总注。

──────────────── 断卦次序（不可颠倒）────────────────

《增删卜易·用神元神忌神仇神章》：「不拘占何事，先看何爻为用神。既得用神，须看旺相否？有元神动而生扶否？有忌神动而克害否？」照此六步走完再落笔：

第一步 · 取用神
- 六亲分属（《用神章》）：父母主父母祖辈师长及房屋车船文书衣服合同等庇护我身之物；官鬼主功名官府鬼神、妻占夫、及一切拘束我身之事；兄弟主兄弟姐妹同事朋友，求财为劫财之神、占妻为刑伤克害之神；妻财主妻妾婢仆及钱财货物等我所驱使支配之物；子孙主子女晚辈门徒及医药僧道六畜，为福神、制鬼之神、解忧之神。
- 自占吉凶以**世爻**为用神；占他人以**应爻**为用神；占彼此交涉之事则世应兼看（世为己、应为人）。
- **用神不上卦（不现）时的检索次序**（此序曾有两说，本产品定序为：先查变爻，再代用日月，最后寻伏）：① 本卦六爻明现；② **变爻有用神**——变爻有则不必寻伏神；③ 日辰月建临用神之支——临则以日月为用神；④ 本宫首卦（八纯）伏神，同爻位本卦之爻为飞神。**取伏来源两书一致，无争议。**
- **伏神得出与否，按《卜筮正宗》第九问「四出四不入」判定，不得自由心证**——得出者四：① 日月生者、日月持之者；② 飞神生伏、动爻生者；③ 日月动爻冲克飞神；④ **飞神空破休囚墓绝于日者**。不得出者四：① 休囚无气、日月克者；② 飞神旺相、日月生助飞神而克害伏神者；③ 伏神墓绝于日月及飞爻者；④ 伏神休囚兼旬空月破者。
- **飞伏四态**（《卜筮正宗·伏神正传》歌诀）：**飞来生伏得长生**，飞来克伏反伤身，伏去生飞名泄气，伏克飞神为出暴。**伏神能出不等于得力——四态定其出否，生克定其得失。**
- 用神不上卦而伏神**难出**时，按《增删卜易》之议请用户再占一卦以决（野鹤：「但逢不现，虽有伏神，亦不用之，再占两卦，用神自现」）。**伏神得出时不提再占。**
- **用神两现**：野鹤屡验「舍其不空而用旬空，舍其不破而用月破」，《卜筮正宗》第十七问同此说；古法反之（舍空破用不空不破）。故两现时**须明说取了哪一爻、凭什么取**，不得含糊。另：一爻动则取动者；两爻俱动或俱不动，择其旺者。
- 用神以用户提示中【用神】标注为准：标注「用户手动指定」时必须沿该用神展开全篇，不得另行取用、改判或两个并用。

第二步 · 定元神、忌神、仇神（《用神元神忌神仇神章》）
生用神者为**元神**，克用神者为**忌神**，克元神、反生忌神而克害用神者为**仇神**（如金为用神：土为元神、火为忌神、木为仇神）。
⚠️ **仇神是卦理术语，不等于人事上的仇人**：应爻生世才是恩人，应爻克世才是仇人。勿以仇神即仇人。

第三步 · 论旺衰（《月将章》《日辰章》《四生逐位论》）
- **月建掌一月之权、司三旬之令，为万卜之提纲**：爻之衰弱者能生之合之比之拱之扶之，衰而亦旺；爻之强旺者能冲之克之刑之破之，旺而亦衰。
- **日辰为六爻之主宰，司四时之旺相，四时俱旺、操生杀之权，与月建同功**。日辰能生扶拱合衰弱之爻，能克害刑冲强旺之爻。
- 两书均**拒绝**给月建日辰定权重分数（《卜筮正宗》：「七分八分，何以决疑？」）；只在具体卦中按「生多克少／生多克少」临时裁断。**不得说「月建比日辰重」或反之。**
- 四时旺相（《卜筮正宗·旺相休囚论》）：春木旺火相、夏火旺土相、秋金旺水相、冬水旺木相、四季之月土旺金相；余为休囚。**月令一项按书里的五态（旺相休囚死）判定并与综合旺衰一并列入排盘数据**（当令者旺、令生者相、生令者休、克令者囚、令克者死）；月建日辰与各爻综合旺衰**已由代码判定并列入排盘数据，直接取用**。
- **旬空**（《旬空章》）：旺不为空、动不为空、动而化空、伏而旺相、有日建动爻生扶者，皆不为空；月破为空、有气不动亦为空、伏而被克亦为空。**真空者：春土、夏金、秋木、三冬火。** 出空之法：冲空则实（日辰冲起）、填实（值日）、出旬。
- **月破**（《月破章》）：月建冲爻为月破。**出破三法：出月则不破、实破之日则不破（逢值）、逢合之日则不破。** 动则能伤于爻、变则能伤于动，仍有祸福之基；**惟静而不动、又无日辰动爻生助，实则到底而破**。「冲空」作**出破**法两书均未见明文，不得使用。
- **暗动与日破**（《暗动章》）：静爻**旺相**而被日辰冲为**暗动**，暗中生克有力（元神暗动生用为喜，忌神暗动克用为忌）；静爻**休囚**被日辰冲为**日破**，无力无为。综合旺衰为**二分**（旺相／休囚），与本章的两分正好对齐；月令一项另按五态（旺相休囚死）单列在【各爻旺衰】里，二者都照数据读，不得自行推。**此判据出《增删卜易》，《卜筮正宗》不立「日破」名目**（静而不空逢冲一律曰暗动）——本产品采甲，断语中如遇关键处可注明异说。
- **三墓**（《随鬼入墓章》）：日墓、动墓、化墓，谓之三墓。**野鹤门槛：须休囚无气始见凶危；若旺而有扶，仍有救解。**
- **十二长生唯长生、帝旺、墓、绝四位当看**：《增删卜易》「余得验者，只验生旺墓绝，其余不验，不必用也」，又「化养、化病、化胎及化沐浴，俱不验，已尽删矣」；《卜筮正宗》「卦中惟是长生、墓、绝三件，卦卦须看」，并同斥「不可执疑于养主狐疑、病主伤损、胎主勾连」（帝旺归旺相休囚论管）。**两书同口径，不取沐浴胎养病等八位**；乙「吉连沐浴，败而不成」一条是按生克再断的门类注（败中兼生/兼克、有救者险里逃生），不独立成断，本站不单列。

第四步 · 论动静与动变（《动静生克章》《动变生克冲合章》《动散章》）
- 六爻安静时，**旺相之静爻能生能克休囚之静爻**；动与静不对等：**动爻能克静爻，静爻虽旺相亦不能克动爻**；休囚之爻一旦发动，照样能克旺相之静爻。
- **变爻只作用于本位动爻**，不能生克他爻；他爻与本位动爻也不能生克变爻。**只有日月能生克冲合变爻。**
- **动散之断**（本产品采《增删卜易》）：古以日辰冲动爻为「冲散」，野鹤翻案——「旺相者冲之不散，有气者冲之不散，休囚者间有冲散，亦千百中之一二耳……神兆机于动，动则必有因，虽则今日受制，后逢值日而不散」。**故不得轻易把动爻断成「散而失效」。**
- **卦变相冲为卦之反吟，爻变相冲为爻之反吟**（《反吟卦定例》）：主事反复、去而复返。**门槛：用神不变冲克者，事虽主反覆，亦主事就；最嫌用神化冲克者，凡谋大凶。** 伏吟主忧抑呻吟、动如不动，内卦伏吟内不利、外卦伏吟外不利。（伏吟成立范围已裁：采《卜筮正宗》封闭三类为执行标准；《增删卜易》开放举例、分类同构，不冲突——登记表 §5。）
- **进神退神**（《进神退神章》《变出进退神论》）：进神者由此而前进，如春木之荣、有源之水；退神者由此而渐退，如秋天花木渐渐凋零。**吉神宜于化进，忌神宜于化退**；进神吉凶倍增其势，退神吉凶渐减其威。**化空破与进神已裁为一致**（登记表 §5）：定性不废（甲「亦能进」），应期待实（甲卦例「许之寅卯年，实空实破」即乙「待期填补合冲而进」）——代码同时给出「变爻旬空／变爻月破」两个事实位，你须据此说明该爻当下是否已得力，不得含糊。
- **三合局**（《三合章》）：申子辰水、巳酉丑金、寅午戌火、亥卯未木。三爻动而合局、两爻动一爻不动亦成局；三爻若只两爻动**不为成局，须待后来之月日补凑，谓之虚一待用**（一爻明动一爻暗动，亦作两爻动）。局生世则吉、局克世则凶；世爻在局为美；日月有一在局中谓之局旺。（此与《卜筮正宗》第四问逐条同构：一静二发待静者值日、暗动计动、空破待出空——两书互证，登记表 §5。）
- **冲中逢合、合处逢冲**（《合处逢冲冲中逢合论》）：合者聚也，冲者散也。冲中逢合先散后聚、先失后得；合处逢冲反之，谋虽成而终散。
- **合中带克**：如子变丑、戌变卯，合中带克；旺相得日月生扶作合论，休囚失令被克作克论。

第五步 · 定轻重
- **元神有力方能生用，其五**：旺相临日月或得日月动爻生扶；动化回头生、化进神；长生帝旺于日辰；与忌神同动；旺动临空。**元神无用者六**：休囚不动或动而被克；休囚又旬空月破；动化退神；衰而又绝；入三墓；动化绝克破散——虽有如无。
- **忌神有力则害用，其五**：旺相临日月；化回头生、化进神；旺动临空；长生帝旺于日辰；与仇神同动——势同斧钺。**忌神动而不克用者七**：休囚不动或被克；静临空破；入三墓；衰化退神；衰而又绝；动化绝克破散；**与元神同动**。
- **接续相生**：忌神与元神同动，忌神反生元神、元神转生用神，化凶为吉。
- **用神要有根**：「倘若用神无根，谓之元神有力亦难生，忌神无力亦休喜。」用神被月冲日克而衰绝者，纵有生扶也生之不起。
- **绝处逢生**（《绝处逢生论》）：用爻逢绝而卦中动爻相生，为凶中回吉之象。

第六步 · 定应期（《各门类应期总注章》，以用户提示【应期】所列日期为基准）
静者逢值逢冲；动者逢合逢值；动逢合而绊住者，**冲开之月日应**；太旺者逢墓逢冲；衰绝者遇生遇旺；入三墓者喜冲开；六合者宜相击；月破者喜逢填合；旬空者最爱填冲；大象吉而被克者，待克神受克之期；化进神者逢值逢合，化退神者忌值忌冲；有应于独发独静者，有应于变爻动爻者；远近当分；世空而元动者，待元神逢值；世衰而元静者，须元气逢冲。
- **迟速两轴并行，不互推**（登记表 §4 F-03，已裁）：远近之辨按甲「远事定之于年月，近事应之于日时」；快慢之辨按乙「速则动而克世，缓则静而生身」（用神动而克世来期甚速，动而生世则迟，静而生世又迟，并参衰旺）。两轴各管各的，不得拿其一推另一。

──────────────── 分占要诀（《卜筮正宗》逐门；用户所问落入哪门，即按该门细化）────────────────

- **婚姻**：男占女以妻财为用、女占男以官鬼为用；代占随称呼取子孙/兄弟，不可一概以官为夫财为妇。六合卦、世应相生相合者易成而吉；六冲卦纯阴纯阳者难成，纵成亦不利；世空自不欲成、应空彼不欲成；男占两财、女占两鬼主再续再嫁。
- **求财**：财为本、福为利（子孙为财之源），二者不可损坏。财爻旺相、子孙发动者称意；财生合世、持世克世为财来就我；得子孙发动则利必久远。父兄皆动如缘木求鱼；无鬼则兄必专权、财多虚耗；财化官化兄最凶（损折驳耗，恐因财致祸）。世空有财难得。
- **功名**：父爻为文章、鬼为官职，二者一卦之主，伤一则不成；世持官或得官生合者有望，世临子孙则仕途未通。喜合而不喜冲（官父相冲主出题生涩）；财福反为恶煞（财克父、子克鬼）；兄弟发动则同经者多、纵成亦名落。
- **官讼**：世为自己、应为对头；鬼为听讼官，动去克应则我胜、克世则我败；财为理，临世我有理、临应他有理；间爻为中证之人。世空我欲息争、应空他欲息争，世应俱空则两愿销息。世爻入墓化墓或临鬼墓而卦象凶者，防牢狱之祸。
- **疾病**：官鬼为病之轻重与病根，本人用神为安危，子孙为解神、为医药，卦中无子孙则鬼无制、服药无效。忌神发动其祸成；用爻墓绝空破无救者必死，有救（生扶拱合）者无妨；绝处逢生为凶中回吉。占自病怕鬼持世；卦身持鬼亦是旧病。
- **出行**：世为自己、父母为行李、妻财为盘缠、应为所往之处、间爻为往来经历与同伴。世克应则所向通达，应克世则所向闭塞；间爻动则途中有阻，安静则往来平安；世空去不成；官鬼临玄武动克世防盗贼。
- **失物**：财爻为所失物之主，通则如此；失舟车衣帽文书以父母为用，失飞禽走兽以子孙为用。财在内卦则物未出家庭、在他宫外卦则已出外、在间爻则邻里可寻；用爻动则迁移无常难寻，落空亡则杳无踪迹；兄动主财物失散难寻。
- **家宅**：内卦第二爻为宅舍、外卦第五爻为人口；父母为房屋、妻财为禄、子孙为福。内二爻生五爻（宅生人）吉、克五爻凶；鬼不宜动，动克世克宅主连生灾咎；月破之爻动克世爻及身命之爻主生灾不已。
- **产育**：子孙为占产用神，旺相单重为阳爻是男、休囚交拆为阴爻是女；夫占妻则财为产母、胎为胞胎、福为儿女。子孙墓绝又被刑冲克害者大凶；白虎为血神，临子孙或胎爻发动则其胎已破；父动克子孙，占产所忌。
- **天时**：占雨以父母为用、官鬼为原神；占晴以妻财为用、子孙为原神；兄弟管风云、官鬼管雷电。父动被日辰克制者不雨、日辰生扶主大雨；三合成财局无雨、三合父局有雨；父爻入墓而无冲开墓库则雨止。

──────────────── 实例推理法（两书占例里反复出现的同一条思路，照此断卦）────────────────

**用神无根，元神有力亦难生**（《增删卜易》自占病，得大过之鼎）：世爻亥水为用神，被未土忌神动而克水，幸得元神酉金亦动，忌神未土反生元神之酉金，金生亥水，接续相生，化凶为吉——**但亥水月冲日克、值月破而被克，虽有生扶，奈何生之不起，如树无根，寒谷不回春也**。果卒。此例示：先看用神有没有根，再看元神有没有力；根坏则生扶无效。

**爻值月建，旬内毕竟为空**（《增删卜易·月将章》）：古说「爻值月建，旺相当权，逢空不空」，野鹤不以为然——「在旬内者，毕竟为空」，须待出空之日方不空。此例示：**旺不为空与出空之日各管一段，不可用「旺」把旬空一笔抹去**。

**官临月破，定在实破之年**（《增删卜易·月破章》）：占将来有官否，得兑之讼，官动生世、世动化进神，显然是得官之象，但官逢月破、世遇旬空——「然此空犹有日辰相冲，冲空则实，不为空矣；而此破又无日辰动爻之生」。野鹤命之再占，后得官临世位，断「前卦官临月破，定在实破之年」，果于巳年承袭。此例示：**空与破各有出法，空可冲实、破须实破或逢合**；且此例正是「用神不现/不明则再占」的用法。

**伏去生飞，名为泄气**（《卜筮正宗》占逃仆）：用神伏而不现，飞神受伏神之生，谓之「伏去生飞，名为泄气」，盗去财物必尽费于炉火之家。此例示：伏神能出不等于得力，**四态定其出否，生克定其得失**。

**六合变六冲，合处逢冲**（《卜筮正宗》占讼）：卦得六合，婚姻最宜，然世被日冲、应爻月破，谓之合处逢冲，纵就不吉——「爻逢六合，官事必审，不宜月建冲世……必输无疑」。此例示：**合与冲要落到具体爻上，不可只看卦体吉凶**。

由此立三步：
第一步 定用神与根：用神是谁、有没有根（月冲日克衰绝者无根）。
第二步 数党势：点清生用神之卦有几重、克用神之卦有几重，并看互变是否助长；**克多生少则凶、生多克少则吉**。
第三步 定轻重：由**变爻**看结局——变爻生扶则虽凶不危，变爻重克则凶上加凶；再以月建日辰的最终裁断收口。

再把象落到具体：每个具体断言（何人、何物、何时、何处）都必须由某个卦象推出（六亲、六神、爻位、纳甲、月建日辰）。推不出具体的，只说趋势，不编细节。

──────────────── 断卦铁律 ────────────────

- 一事一占；信息不足先引导求占者说清，不臆断。
- **客观直言，不曲意逢迎**：吉则明言，凶则指出风险所在与规避之法，不恐吓、也不粉饰。不承诺必然——不说「一定」「必然应验」，卦象给的是趋势。
- 说人话，不堆砌术语；紧扣用户的具体问题场景与排盘数据，不泛泛而谈。
- **先象、后事、再建议（顺序不可颠倒）**：先讲卦名之义（本卦、变卦的卦名在讲什么）与卦辞、象曰原文，再讲爻象（哪一爻动、动爻爻辞所言、变爻如何、六亲旺衰），然后把这一层意思落到用户问的事上，最后才给行动建议。必须引用原文，不许只给结论和指令而不讲卦。
- **六爻以用神为主、卦名卦辞为辅**：卦名卦辞与用神旺衰相左时，吉凶以用神旺衰生克为主，但卦名卦辞之义要如实讲出来，作为情势与氛围的补充。
- **神煞不进推理链**：六神（青龙朱雀勾陈螣蛇白虎玄武）与一切神煞（贵人、驿马、禄马等）**只作取象描述，不得作为吉凶变量**。据《卜筮正宗》本人所论，贵人禄马驿马「临吉神是吉，临凶神是凶」——神煞不越爻本身的吉凶；「若贵人之爻临忌神动来克害，不可以贵人为吉」。
- **两书有异时如实标注，不自行择一**：本提示词已标出「甲／乙有异」的地方（日破之有无、动散、化空破能否即进、反吟伏吟范围），涉及处须说明该属两说之一，或说明本产品取哪一说及理由。
- **每条吉凶判断、应期与行动建议后面都要标出依据来源**：出自典籍的写篇名（只能用本提示词已列出的篇名）；出自排盘数据的写「卦象」；由生活事理补足的写「事理（非典籍明文）」。
- 不与投资、医疗、法律的专业意见相混：涉及看病、诉讼、投资决策时只按卦象说趋势，并明确建议当事人另行咨询相应专业人士。
- 【五行边界·不可越】问题根源若在人事结构（沟通方式、立场心态、关系格局）而非五行力学，直说「此非五行可解」，给出沟通与行为层面的调整建议，不硬开五行方；若属大运流年大势，直言「识时重于改」——五行手段只能减轻程度，不能扭转趋势，不过度承诺。

──────────────── 输出结构 ────────────────

请按**两部分**输出。两个分节标题必须按字面使用——第一部分以「## 第一部分·解卦」作二级标题，第二部分以「## 第二部分·行动建议（注明按档位给到哪层）」作二级标题，便于页面分节显示：

──────── 第一部分·解卦（不受档位影响，始终完整细致地输出）────────

1. **卦名与卦象**：先解本卦卦名之义（何以为此名、上下卦象合成什么意象），引本卦卦辞与象曰原文简释；变卦卦名之义同样点出。再总说本卦→变卦、卦宫、世应、旬空、卦身，一句话点出吉凶基调。
2. **用神定位**：明确所问之事取哪一爻为用神（含取用理由；两现或用户指定时说明取哪一爻），及其旺衰、旬空、月破状态；用神不现者说明四级检索走到哪一步、伏神出否。
3. **三神与党势**：元神、忌神、仇神各是什么六亲、什么状态（有力/无力，并指明凭哪一条），点清生用神之卦几重、克用神之卦几重。
4. **爻象与关键因素**：动爻/变爻、**引动爻爻辞原文**解其义；格局判据（暗动、日破、入墓、进退神、反吟伏吟、三合局）逐条落位，指出事情的关键转折。
5. **吉凶判断**：以用神旺衰与生克链条为主、卦名卦辞为辅，说清凭什么这样断。

──────── 第二部分·行动建议（深度由用户档位决定，档位指令见提示末尾）────────

6. **应期提示**：**以用户提示中【应期（确定性计算）】所列日期为基准**，按《各门类应期总注章》诸诀（静逢值逢冲、动逢合逢值、旬空填冲、月破填合、入墓喜冲开等）结合用神旺衰取舍解释。**硬约束：正文中凡出现任何具体日期，必须逐字取自【应期】所列；出现列外日期即视为编造——比不给日期更糟。** 若【应期】未覆盖你想说的时机，就写「待其气机」，不要补日期、不要自己推干支。迟速两轴并行、不互推：远近之辨按甲「远事定之于年月，近事应之于日时」；快慢之辨按乙「速则动而克世，缓则静而生身」（并参衰旺）。
7. **行动建议**：按档位给，**各档落地物不同，这是三档唯一但明显的差别**——
   S 档只给「### 紧急·事体窗 → 这几天怎么做」一层（约 300 字）：应期之日（**只能逐字取自**【应期】所列）、方位（宜往/宜坐）、颜色（宜穿/宜用）、数字、随身物件、3–5 条指令；
   M 档加「### 中期·人事 → 这季度怎么调」一层（约 400 字）：行业职能方向、屋宅与办公空间布局（方位、器物、材质、朝向）；
   L 档再加「### 长期·底盘 → 这几年怎么养」一层（约 500 字）：饮食五味、作息起居与四时调养、健康与脏腑倾向（只讲调理方向）、情志调养，每条带一句原理与出处。
   每条建议用一句「（据：用神/动爻爻辞/卦名之义/格局判据）」标明依据。

关于档位：用户提示末尾的【行动建议档位】只决定第二部分给到哪一层；**第一部分的解卦在任何档位都必须完整**——不得因档位低就压缩或省略卦名、卦辞、爻辞、用神、旺衰的交代，也不得在解卦里夹带行动指令。若本卦无动爻（六爻皆静），要明确说明「此卦六爻安静，以世应、用神旺衰与月建日辰断之」，不得凭空编造动爻。

**重要**：凡代码已给出的判据（【用神】及其置信度、【各爻旺衰】及其标志、【格局判据】、【应期】），一律照此解释，不得重算、不得自行加减分、不得另立规则。数据里没有的，就说数据未给，不要补。
"""


def _hexagram_classics(gua_info: dict) -> dict:
    """取某卦的卦名释义资料（卦辞/象曰/六爻爻辞）。

    数据源：data/meihua_data.json（与梅花共用同一份六十四卦资料，只读不改）。
    六爻本来只用纳甲装卦，但用户需要"从卦名、卦辞、爻辞讲清楚为什么这样断"，
    所以这里按上下卦编号把本卦/变卦的卦辞、象曰、动爻爻辞取出来交给 AI。
    """
    try:
        up = (gua_info or {}).get("upper", {}).get("num")
        low = (gua_info or {}).get("lower", {}).get("num")
        if not up or not low:
            return {}
        hx = load_meihua_data()["hexagrams"]["by_key"].get(f"{up},{low}") or {}
        return {"name": hx.get("name", ""), "guaci": hx.get("guaci", ""),
                "daxiang": hx.get("daxiang", ""), "yaoci": hx.get("yaoci", [])}
    except Exception:
        return {}


def build_liuyao_user_prompt(gua_data: dict, question: str, tier_override: str = "") -> str:
    """构建六爻断卦用户 prompt（含完整排盘数据 + 卦名卦辞爻辞经典依据）"""
    t = gua_data["time_info"]
    lines = []
    lines.append(f"【起卦时间】{t['year_ganzhi']}年{t['month_ganzhi']}月{t['day_ganzhi']}日{t['hour_ganzhi']}时 · 农历{t['lunar']} · 日旬空 {t['xunkong']}")
    # 月建为提纲、日辰为主宰（《增删卜易·月将章》《日辰章》）。旺衰由代码按
    # "当令者旺、我生者相，余俱休囚"判定，此处只念不判。
    _det0 = (gua_data.get("remedy") or {}).get("details") or {}
    _md = _det0.get("月建日辰") or {}
    if _md:
        lines.append(f"【月建日辰（代码判定，不得重算）】月建 {_md.get('月建', '')}（{_md.get('月建五行', '')}）"
                     f"｜日辰 {_md.get('日辰干支', '') or _md.get('日辰', '')}（{_md.get('日辰五行', '')}）"
                     f"｜五行卦气：" + "、".join(f"{k}{v}" for k, v in (_md.get("卦气") or {}).items()))

    ben = gua_data["ben_gua"]
    bian = gua_data.get("bian_gua")
    lines.append(f"【本卦】{ben['name']}（{gua_data['palace']}）{'·'.join(ben['markers']) if ben['markers'] else ''}")
    if bian:
        lines.append(f"【变卦】{bian['name']}（{bian['palace']}）{'·'.join(bian['markers']) if bian['markers'] else ''}")
    _u = ben.get("upper") or {}
    _lo = ben.get("lower") or {}
    if _u or _lo:
        lines.append(f"【本卦卦体】上卦 {_u.get('name', '')}{_u.get('wuxing', '')}{_u.get('symbol', '')}"
                     f" ＋ 下卦 {_lo.get('name', '')}{_lo.get('wuxing', '')}{_lo.get('symbol', '')}"
                     f"｜宫五行 {gua_data.get('palace_wuxing', '')}"
                     f"｜卦身（月卦身）{gua_data.get('yue_guashen', '')}"
                     + ("居" + "、".join("%d爻" % x for x in gua_data.get('yue_guashen_positions') or [])
                        if gua_data.get('yue_guashen_in_gua') else "（六爻皆不见卦身，事无头绪）"))
    if gua_data["moving_positions"]:
        lines.append(f"【动爻】第{'、'.join(str(p) for p in gua_data['moving_positions'])}爻")

    # 经典依据：卦名卦辞象曰 + 动爻爻辞（供"先象后事再建议"之用）
    cls_ben = _hexagram_classics(ben)
    if cls_ben:
        lines.append(f"【本卦经典依据】{cls_ben['name']}：卦辞「{cls_ben['guaci']}」；象曰「{cls_ben['daxiang']}」")
    cls_bian = _hexagram_classics(bian) if bian else {}
    if cls_bian:
        lines.append(f"【变卦经典依据】{cls_bian['name']}：卦辞「{cls_bian['guaci']}」；象曰「{cls_bian['daxiang']}」")
    yao_names = ["初", "二", "三", "四", "五", "上"]
    for pos in (gua_data.get("moving_positions") or []):
        idx = int(pos) - 1
        if 0 <= idx < len(cls_ben.get("yaoci", []) or []):
            lines.append(f"【动爻爻辞】第{pos}爻（{yao_names[idx] if idx < 6 else pos}）：{cls_ben['yaoci'][idx]}")
    if gua_data.get("moving_positions") and cls_bian:
        for pos in gua_data["moving_positions"]:
            idx = int(pos) - 1
            if 0 <= idx < len(cls_bian.get("yaoci", []) or []):
                lines.append(f"【变卦同位爻辞】第{pos}爻：{cls_bian['yaoci'][idx]}")

    lines.append("【六爻排盘】（自下而上）")
    for l in reversed(gua_data["lines"]):
        yin = "- -" if l["yin_yang"] == 0 else "───"
        parts = [f"{l['name']}", f"{l.get('type', '')}", f"{l['liushen']}",
                 f"{l['liuqin']}{l['gan']}{l['zhi']}", f"{l['wuxing']}", yin]
        if l["shi"]:
            parts.append("世")
        elif l["ying"]:
            parts.append("应")
        if l["moving"]:
            parts.append("○动")
            b = l["bian"]
            parts.append(f"→变{b['gan']}{b['zhi']}{b['wuxing']}({b['liuqin']})")
        if l["xunkong"]:
            parts.append("旬空")
        if l["yuepo"]:
            parts.append("月破")
        lines.append("  " + " ".join(parts))

    lines.append("")
    # 用神与处方五行：确定性计算结果（liuyao_remedy），作为既定事实交给 AI，
    # 手动指定时 AI 必须沿用，不得另行取用神（"确定性归代码，语言归 AI"）
    r = gua_data.get("remedy") or {}
    if r.get("yongshen"):
        src = "用户手动指定，必须以此用神为主线断卦，不得另行取用" if r.get("yongshen_source") == "manual" \
            else "代码按《增删卜易·用神章》自动判定"
        lines.append(f"【用神】{r['yongshen']}（{src}）")
        lines.append(f"【用神置信度】{r.get('confidence', '')}"
                     + ("｜候选：" + "、".join(r.get("candidates") or []) if r.get("candidates") else "")
                     + ("｜命中关键词：" + "、".join(
                         "%s→%s（%s）" % (x.get("kw", ""), x.get("liuqin", ""), x.get("layer", ""))
                         for x in (r.get("matched") or []) if isinstance(x, dict))
                        if r.get("matched") else "")
                     + ("（低置信：若与事理不符，须在断语中说明并请用户确认，不得默默换用神）"
                        if r.get("confidence") == "low" else ""))
        if r.get("reason"):
            lines.append(f"【用神判定依据】{r['reason']}")
        lines.append(
            f"【事体与处方】用神五行 {r.get('X', '')}，处方五行 {r.get('R', '')}"
            f"（{(r.get('R_reason') or '') if (r.get('R_reason') or '').startswith(r.get('state') or chr(0)) else ((r.get('state') or '') + '：' + (r.get('R_reason') or ''))}）"
        )
        _det = r.get("details") or {}
        _y = _det.get("用神爻") or {}
        if _y:
            lines.append(f"【用神爻位】{_y.get('name', '')} {_y.get('六亲', '')}{_y.get('干支', '')}"
                         f"（{_y.get('五行', '')}）{'发动' if _y.get('发动') else '静'}"
                         f"{'·世爻' if _y.get('世爻') else ''}"
                         f"｜旺衰 {_y.get('旺衰', '')}｜月令五态 {_y.get('月令五态', '')}"
                         f"（{'、'.join(_y.get('标志') or []) or '平和'}）")
        _ys = _det.get("元神") or {}
        if _ys:
            _yspos = (f"｜爻位 {_ys.get('name', '')} 旺衰 {_ys.get('旺衰', '')}"
                      f"（{'、'.join(_ys.get('标志') or []) or '平和'}）") if _ys.get("name") else ""
            lines.append(f"【元神】{_ys.get('六亲', '')}（{_ys.get('五行', '')}）"
                         f"{'有力' if _ys.get('有力') else '无力'}——{_ys.get('说明', '')}{_yspos}")
        _js = _det.get("忌神") or {}
        if _js:
            _jspos = "；".join(f"{x.get('name', '')} {x.get('旺衰', '')}"
                              f"（{'、'.join(x.get('标志') or []) or '平和'}）"
                              for x in (_js.get("爻位") or []))
            lines.append(f"【忌神】{_js.get('六亲', '')}（{_js.get('五行', '')}）{_js.get('状态', '')}"
                         + (f"｜爻位：{_jspos}" if _jspos else "｜不现"))
        _pl = _det.get("各爻旺衰") or []
        if _pl:
            lines.append("【各爻旺衰（代码判定，照此解释，不得重算、不得自行加减分）】"
                         "旺衰＝综合二分（旺相／休囚）；月令五态＝该爻五行在月令的旺相休囚死")
            for _p in _pl:
                lines.append("  %s %s%s（%s）%s%s 旺衰%s｜月令%s：%s"
                             % (_p.get("name", ""), _p.get("六亲", ""), _p.get("干支", ""),
                                _p.get("五行", ""), _p.get("卦位", ""), _p.get("动静", ""),
                                _p.get("旺衰", ""), _p.get("月令五态", ""),
                                "、".join(_p.get("标志") or []) or "平和"))
        # 逐爻细看（六神断语表）：站长要求 AI 也拿到这份材料。
        # 它是**显示层**——三书自定规矩"六亲本也，六兽末也"，故只许据此串人话，
        # 不得新增断语、不得拿六神改吉凶（边界原句随材料一起下发）。
        _plx = r.get("逐爻细看") or []
        if _plx:
            _lb = liushou_prompt_block(_plx)
            if _lb:
                lines.append(_lb)
    # 格局判据：进退神 / 暗动日破 / 三墓 / 旬空真假 / 月破出破 / 反伏吟 / 三合局 / 伏神。
    # 此前这些规则只写在系统提示词里、代码一个都没算，AI 手里没有数据只能自己推——
    # 那是幻觉的第一来源。此处只**陈述事实**，两书有异者把两家口径都标出
    # （措辞由 docs/六爻分歧登记表.md 的议题级裁定决定，不在此处替它取舍）。
    _pat = liuyao_patterns.analyze(gua_data, r, r.get("yongshen", ""))
    _pat_block = liuyao_patterns.to_prompt_block(_pat)
    if _pat_block:
        lines.append(_pat_block)
    lines.append("")
    # 十干体性与润燥全表（十味都给，不限本次处方那两味）
    lines.extend(_stem_texture_reference())
    lines.append("")
    lines.append(f"【用户想问的事】{question}")
    lines.append("")
    # 应期：确定性计算结果（yingqi），交 AI 作为既定事实
    y = gua_data.get("yingqi") or {}
    if y.get("yongshen") and (y.get("zhiri") or y.get("fenghe") or y.get("chongri")):
        ys = y["yongshen"]
        lines.append(f"【应期（确定性计算·日期不得超出此列）】用神{ys.get('liuqin', '')}{ys.get('ganzhi', '')}"
                     f"（{'动爻' if ys.get('moving') else '静爻'}——{y.get('rule', '')}）：")
        if y.get("zhiri"):
            lines.append("  逢值之期：" + "；".join(f"{d['date']}（{d['ganzhi']}）" for d in y["zhiri"]))
        if y.get("fenghe"):
            lines.append("  逢合之期：" + "；".join(f"{d['date']}（{d['ganzhi']}，{d['reason']}）" for d in y["fenghe"]))
        if y.get("chongri") and not ys.get("moving"):
            lines.append("  逢冲之期（静者逢值逢冲）：" + "；".join(f"{d['date']}（{d['ganzhi']}）" for d in y["chongri"]))
        if y.get("xunkong") and y.get("chongkong"):
            lines.append("  用神旬空：空逢冲则实，应于冲空之日——" +
                         "；".join(f"{d['date']}（{d['ganzhi']}）" for d in y["chongkong"]))
        if y.get("yuepo") and y.get("shipo"):
            lines.append("  用神月破：应于实破之日——" +
                         "；".join(f"{d['date']}（{d['ganzhi']}）" for d in y["shipo"]))
        if y.get("jishen_chong"):
            lines.append("  忌神受制之期（忌神受制逢冲）：" +
                         "；".join(f"{d['date']}（{d['ganzhi']}，{d['reason']}）" for d in y["jishen_chong"]))
        lines.append("结合卦理取舍解释；应期日期不得超出上列计算。")
        lines.append("")
    lines.append(tier_directive(question, tier_override))
    return "\n".join(lines)


@app.post("/api/liuyao/yongshen/classify")
async def liuyao_yongshen_classify(request: LiuyaoYongshenClassifyRequest):
    """
    起卦前预判用神：高置信（精确命中）前端直接起卦；
    低置信/多候选前端弹"您问的是 A 还是 B"二选气泡。
    """
    return classify_yongshen_detail(request.question)


@app.post("/api/liuyao/remedy")
async def liuyao_remedy_recalc(request: LiuyaoRemedyRequest):
    """
    事后纠错：改判用神后按已排好的盘重算处方五行（不重新起卦、不影响已生成断语）。
    """
    try:
        return liuyao_remedy(request.gua_data, request.question, request.yongshen_override)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重算失败: {str(e)}")


@app.post("/api/liuyao/divine")
async def liuyao_divine(request: LiuyaoRequest, http_request: Request):
    """
    六爻纳甲：摇杆参数 → 排盘 →（可选）AI 断卦（SSE 流）

    `ai=False` 就是"只要排盘"：卦象、用神、处方五行、应期照给，**不调 LLM、不扣额度**。
    前端默认先发这一发，用户看过盘再点「AI 解卦」发 `ai=True`——
    这样"起一卦看看"与"花一次额度让 AI 讲"是两件事，不会因为想看一眼卦就自动花掉额度。
    """
    rate_limit(http_request, "llm_liuyao", limit=30, window_sec=60)   # 调 LLM，必限流
    # 每日配额：**只在真的要调 AI 时才扣**。
    # 「只看排盘」不扣——排盘、用神、处方五行、应期全是确定性计算，不花上游一分钱；
    # 对不花钱的东西扣额度，用户就不敢看盘了，而这个盘本来就是本站最该被看到的部分。
    # 自带 key：不计数、不拦截；设置有问题时不静默退回免费路径（见梅花那处的说明）。
    llm_ov, llm_err = _resolve_llm(getattr(request, "llm", None))
    if llm_ov:
        q = {"allowed": True, "scope": "byok"}
    elif llm_err:
        q = {"allowed": False, "scope": "llm",
             "message": "模型设置无法使用：%s" % llm_err,
             "hint": "到「API 设置」里检查厂商、key 与模型名；也可以清空设置，改用每日免费额度。",
             "resets_at": ""}
    else:
        q = _quota_acquire(http_request) if request.ai else {"allowed": False, "scope": "no_ai"}
    if len(request.throws) != 6:
        raise HTTPException(status_code=400, detail="必须摇满六次（初爻→上爻）")

    # 1. 排盘
    try:
        gua_data = build_paipan([t.model_dump() for t in request.throws])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"排盘失败: {str(e)}")

    question = request.question.strip() or "（未填写，请结合排盘给予一般性断语）"

    # 1.5 处方五行 R（用神结构化 → X/R/态势），随 gua_data 一并下发
    try:
        gua_data["remedy"] = liuyao_remedy(gua_data, request.question, request.yongshen_override)
    except Exception:
        gua_data["remedy"] = None

    # 应期（确定性）：用神值日/逢合/冲空实破/忌神受冲，收归代码
    try:
        gua_data["yingqi"] = liuyao_yingqi(gua_data)
    except Exception:
        gua_data["yingqi"] = None

    # 2. SSE 流：先排盘 JSON，再（可选）AI 断卦
    async def generate():
        yield f"data: {json.dumps({'type': 'gua_data', 'data': gua_data}, ensure_ascii=False)}\n\n"
        if not request.ai:
            # 只要排盘：不调 LLM、不扣额度、**也不发降级提示**。
            # 这不是"额度用尽"，是用户还没点「AI 解卦」——发降级文案等于告诉他一个假原因，
            # 他会以为是额度不够才没有断语。排盘、用神、处方、应期已在上一条事件里给全了。
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        if not q["allowed"]:
            # 排盘（含用神/处方五行/应期）已在上一条事件给出，这里只补降级说明。
            # 不返 4xx/5xx：那会让前端把整次摇卦当失败，连排盘一起丢掉。
            yield _degrade_event(q)
        # 自带 key 也算"有 LLM"（理由同梅花那处：自建实例可以不配本站 key）
        elif (llm_ov or LLM_CONFIG.get("api_key")):
            _parts = []
            user_prompt = ""          # 下面 try 里才赋值；回检基准要用，故先占位
            _st = {}                  # 承接 finish_reason，用来判"是不是被截断了"
            try:
                user_prompt = build_liuyao_user_prompt(gua_data, question, request.tier_override)
                _ti = resolve_tier(question, request.tier_override)
                _dc = deterministic_conclusion(request.profile_id, resolve_R(gua=gua_data),
                                               tier=_ti.get("tier", ""))
                if _dc:
                    user_prompt = user_prompt + "\n\n" + _dc
                # 六爻 prompt 较复杂，关闭推理模型的思考阶段以保证 content 稳定输出
                async for chunk in _stream_llm(user_prompt, LIUYAO_SYSTEM_PROMPT,
                                               max_tokens=AI_MAX_TOKENS, disable_thinking=True,
                                               state=_st, llm=llm_ov):
                    _parts.append(chunk)
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
                _tc = _truncated_event(_st, AI_MAX_TOKENS)
                if _tc:
                    yield _tc
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'AI 断卦暂时不可用：{str(e)}'}, ensure_ascii=False)}\n\n"
            # 回检（丙·2）：只在真出文之后跑——半途报错时正文不完整，判"日期越界"就是冤判
            # 基准必须是实收全量：六爻的【十干体性与润燥】在 user prompt 里，
            # 那一节表头写着「引擎录自《滴天髓·论天干》」——只传 system 会把它判成编造
            _v = _verify_event("".join(_parts), gua_data, question, request.tier_override,
                               _review_base(LIUYAO_SYSTEM_PROMPT, user_prompt))
            if _v:
                yield _v
        else:
            yield f"data: {json.dumps({'type': 'error', 'message': '未配置 LLM API Key，仅显示排盘'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ============================================================
# 梅花易数：多轮追问（不重新起卦，基于原卦象继续对话）
# ============================================================
@app.post("/api/meihua/chat")
async def meihua_chat(request: MeihuaChatRequest, http_request: Request):
    """
    二次补充 / 多轮追问：携带原卦象与历史对话，AI 在原卦基础上继续回答。
    返回 SSE 流（text 分片 → done）。
    """
    rate_limit(http_request, "llm_chat", limit=20, window_sec=60)   # 多轮追问更贵，收紧一些
    # 每日配额：追问**计入** AI 解读额度——它同样调 LLM 花钱，
    # 不计数的话一个人可以靠无限追问把当天成本放大数倍，配额就形同虚设。
    # 自带 key 的追问不计入（花用户自己的额度）。
    llm_ov, llm_err = _resolve_llm(getattr(request, "llm", None))
    if llm_ov:
        q = {"allowed": True, "scope": "byok"}
    elif llm_err:
        q = {"allowed": False, "scope": "llm",
             "message": "模型设置无法使用：%s" % llm_err,
             "hint": "到「API 设置」里检查厂商、key 与模型名；也可以清空设置，改用每日免费额度。",
             "resets_at": ""}
    else:
        q = _quota_acquire(http_request)
    user_input = request.user_input.strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="请输入内容")
    if not llm_ov and not LLM_CONFIG.get("api_key"):
        raise HTTPException(status_code=400, detail="未配置 LLM API Key")

    # 额度已满：追问的全部内容就是 AI 文字，没有"排盘"可退，所以直接给说明并返回。
    # **放在这里而不是 generate() 里**：下面构建提示词、外应参断都是"给 LLM 吃的"，
    # 既然不打算调 LLM 就不该做——白算一遍，还平白多一条可能抛错的路径
    # （build_user_prompt 会读 gua_data["ben_gua"]，载荷不全就在这里炸）。
    if not q["allowed"]:
        async def _degraded_only():
            yield _degrade_event(q)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(
            _degraded_only(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                     "X-Accel-Buffering": "no"},
        )

    gua_data = request.gua_data
    history = request.history or []
    # 防止上下文过长：保留第一条（原始提问）和最近 14 条
    if len(history) > 15:
        history = [history[0]] + history[-14:]

    # 带外应时改用「外应解读」专用提示词：此时只该讲这一条外应对原断的影响，
    # 不该把整卦重解一遍（那会重复、且冲淡重点）。无外应则仍走普通追问提示词。
    _sys_prompt = OMEN_SYSTEM_PROMPT if request.waijing else INTERPRETATION_SYSTEM_PROMPT
    messages = [{"role": "system", "content": _sys_prompt}]
    first_user = ""
    if history:
        first_user = next((m.get("content", "") for m in history if m.get("role") == "user"), "")
        messages.append({"role": "user", "content": build_user_prompt(gua_data, first_user)})
        for m in history[1:]:
            role = "user" if m.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": str(m.get("content", ""))})
        messages.append({"role": "user", "content": user_input})
    else:
        # 无历史（首次追问前直接提问）：卦象数据 + 问题合并为一条
        messages.append({"role": "user", "content": build_user_prompt(gua_data, user_input)})

    # R3：追问同样带上确定性判定层，避免多轮对话里 AI 与判定表互相矛盾
    _ti = resolve_tier((first_user + " " + user_input).strip(), request.tier_override)
    _dc = deterministic_conclusion(request.profile_id, resolve_R(gua=gua_data),
                                   tier=_ti.get("tier", ""))
    if _dc:
        messages.append({"role": "user", "content": _dc})

    # 外应参断：起卦之后新出现的闻见，按原著条例并入"外卦"合断。
    # **必须由代码判定后钉死再交给 AI**：外应配卦与生克参断是有书证的判据，
    # 让模型自由发挥就等于让它现场编一条术数规则（本项目"绝不代拟"红线）。
    waijing_block = ""
    if request.waijing:
        try:
            ti_wx = _ti_wuxing_of(gua_data)
            wj_res = waijing.analyze_many(request.waijing, ti_wx,
                                          inner_net=request.inner_net,
                                          chosen=request.waijing_gua)
            waijing_block = waijing.to_prompt_block(wj_res)
            if waijing_block:
                messages.append({"role": "user", "content": waijing_block})
        except Exception:
            # 参断失败不该拦住追问：退化成"没有外应"，并在下方如实说明
            waijing_block = ""
            messages.append({"role": "user",
                             "content": "【外应参断】本次外应未能完成配卦（内部错误），"
                                        "请如实告知用户此应暂不参与合断，不要自行配卦。"})

    async def generate():
        _parts = []
        _st = {}                      # 承接 finish_reason，用来判"是不是被截断了"
        try:
            async for chunk in _stream_llm("", messages=messages, max_tokens=AI_CHAT_MAX_TOKENS,
                                           disable_thinking=True, state=_st, llm=llm_ov):
                _parts.append(chunk)
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
            _tc = _truncated_event(_st, AI_CHAT_MAX_TOKENS)
            if _tc:
                yield _tc
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'AI 暂时不可用：{str(e)}'}, ensure_ascii=False)}\n\n"
        # 追问也检。多轮才是"换种说法绕开约束"最容易发生的地方——
        # 单轮被提示词按住了，第二轮顺着用户的话头就漂了。
        # 档位按"原始提问 + 本轮提问"判：档位契约跟着问题深浅走，多轮里深浅是会变的。
        # 基准＝**整个 messages**（system ＋ 历史 ＋ 本轮 ＋ 确定性层 ＋ 外应块）——
        # 这一路本来就没有单独的 user_prompt 变量，实收就是 messages 本身。
        _v = _verify_event("".join(_parts), gua_data, (first_user + " " + user_input).strip(),
                           _review_base("", *[m.get("content", "") for m in messages]))
        if _v:
            yield _v
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ============================================================
# 梅花易数：外应参断（合内外而断）
# ============================================================
def _ti_wuxing_of(gua_data: dict) -> str:
    """从卦象里取体卦五行（外应参断以体卦为主，见《十应目论》）。"""
    try:
        return str((gua_data or {}).get("tiyong", {}).get("ti_wuxing") or "")
    except Exception:
        return ""


@app.get("/api/meihua/gua_wanwu")
async def meihua_gua_wanwu():
    """八卦万物属类（手动起卦的参考资料）。

    数据逐字取自《梅花易数》卷一「八卦万物属类」（waijing_xiang.json 的 bagua 段，
    每类带底本行号，逐字回源有测试守着）。只读静态数据，无归属、无额度。
    用途：万物起卦不再让 AI 猜——把每卦的类象摆给用户，由用户按第一念自己定上下卦与动爻。
    """
    try:
        raw = (waijing._XIANG.get("bagua") or {})
    except Exception:
        raw = {}
    out = []
    # 固定顺序：乾一、兑二、离三、震四、巽五、坎六、艮七、坤八（先天卦数）
    order = ["乾", "兑", "离", "震", "巽", "坎", "艮", "坤"]
    xiantian = {"乾": 1, "兑": 2, "离": 3, "震": 4, "巽": 5, "坎": 6, "艮": 7, "坤": 8}
    houTIAN方位 = {"乾": "西北", "兑": "西", "离": "南", "震": "东",
                  "巽": "东南", "坎": "北", "艮": "东北", "坤": "西南"}
    for name in order:
        v = None
        for k, val in raw.items():
            if str(k).startswith(name):
                v = val
                break
        if not v:
            continue
        cats = {kk: vv for kk, vv in v.items() if isinstance(vv, list)}
        out.append({
            "卦": name,
            "先天数": xiantian[name],
            "五行": v.get("wuxing", ""),
            "方位": houTIAN方位.get(name, ""),
            "原文": v.get("raw", ""),
            "起例行": v.get("line"),
            "类象": cats,
            # 每个类目**自己的**底本行号。frontend 的万物搜索要给到"这一类"的行——
            # 只给起例行的话，乾的 115 条物象会全部标成 1088（卦头那一行），回源对不上。
            "类象行": {k: vv for k, vv in (v.get("_lines") or {}).items()
                       if isinstance(vv, int)},
        })
    return {
        "八卦": out,
        "出处": "《梅花易数·卷一·八卦万物属类》（逐字抽取，每类带底本行号）",
        # 口语 → 原文条目的检索词表（frontend 本地索引用）。
        # 检索词**不是原文**，只是把口语对到已核实条目的指针（每条目标注底本行号）；
        # 加它是因为「门」这类单字走不了子串匹配（「药」⊂「药婆」就是教训）。
        "检索词": waijing._XIANG.get("keys", {}).get("map", {}),
    }


# 万物查卦只看**物类维度**——与 waijing.resolve_omen 配卦所用字段同一口径。
# 婚姻／疾病／官讼等是**占断维度**，不是"东西"，不参与：「药」不该命中「药婆」（人物）
# ——那是站长 2026-09-24 明定的「近义词不命中」。
_WANWU_FIELDS = ("静物", "动物", "人物", "屋宿", "屋舍", "饮食", "天时", "地理", "五色")
_WANWU_TIER_RANK = {"精确": 0, "包含": 1, "检索词": 2}


@app.get("/api/meihua/wanwu_search")
async def meihua_wanwu_search(request: Request, q: str = ""):
    """万物查卦：输入一个词，在《八卦万物属类》的物类维度里找它属哪一卦。

    三档匹配，逐档标明（hit.tier）：
      精确  —— 查询词就是原文条目
      包含  —— 双向子串（查询词 ⊂ 条目，或条目 ⊂ 查询词）。**查询词须 ≥ 2 字**：
               否则「药」会以子串命中「药婆」（兑·人物，指卖药的人）——
               近义词不命中是站长定的规矩，单字子串正是这类假命中的来源。
      检索词 —— keys.map（口语 → 原文条目）。检索词不是原文，只是把口语对到
               已核实的条目上（每一条目标注底本行号）；「门」因此能对到「门户枋」。

    只查物类维度（静物／动物／人物／天时／地理／屋宿／屋舍／饮食／五色），与配卦同口径。
    查不到时 `hits` 为空——前端展示《观物玄妙歌诀》的形／色／性／位／体自推路径，
    **本端点不做任何类推**：现代物属哪一卦由用户按原书给的路径自己定。
    纯静态数据查询：无归属、无额度、不写库。
    """
    rate_limit(request, "wanwu_search", limit=60, window_sec=60)
    qs = (q or "").strip()[:24]
    if not qs:
        return {"q": "", "hits": [], "count": 0,
                "note": "请输入要查的东西（一个词）。"}
    xiang = waijing._XIANG
    keys_map = xiang.get("keys", {}).get("map", {})
    seen: dict = {}
    for gua, g in xiang.get("bagua", {}).items():
        lm = g.get("_lines") or {}
        for field in _WANWU_FIELDS:
            items = g.get(field)
            if not isinstance(items, list):
                continue
            ln = lm.get(field)
            for it in items:
                it_s = str(it).strip()
                if not it_s:
                    continue
                tier = None
                if it_s == qs:
                    tier = "精确"
                elif len(qs) >= 2 and (qs in it_s or it_s in qs):
                    tier = "包含"
                elif qs in (keys_map.get(it_s) or []):
                    tier = "检索词"
                if not tier:
                    continue
                key = (gua, field, it_s)
                prev = seen.get(key)
                if prev is None or _WANWU_TIER_RANK[tier] < _WANWU_TIER_RANK[prev["tier"]]:
                    seen[key] = {"gua": gua, "wuxing": g.get("wuxing", ""), "field": field,
                                 "item": it_s, "line": ln, "tier": tier,
                                 **({"via": "检索词「%s」" % qs} if tier == "检索词" else {})}
    hits = sorted(seen.values(),
                  key=lambda h: (_WANWU_TIER_RANK[h["tier"]], h["gua"], h["field"]))
    return {"q": qs, "hits": hits[:24], "count": len(hits),
            "note": ("只查物类维度（静物／动物／人物／天时／地理／屋宿／屋舍／饮食／五色），与配卦同口径；"
                     "近义词不命中——查不到就走《观物玄妙歌诀》形／色／性／位／体的自推路径。")}


@app.post("/api/meihua/waijing")
async def meihua_waijing(req: WaijingRequest, request: Request):
    """外应参断：把新出现的外应配卦、与体卦论生克比和、内外合断。

    **不重新起卦、不动内卦**：原文只言"必合内外卦而断之"，未见因外来之应而改卦、
    改爻或另起一卦的条文。故本端点只产出一层"外卦"的参断结论，原卦照旧。

    配卦有歧义或配不到时**如实返回**（needs_choice / 空候选），由用户指定；
    本端点不会替用户猜一个卦。
    """
    rate_limit(request, "waijing", limit=60, window_sec=60)
    ti = req.ti_wuxing or _ti_wuxing_of(req.gua_data)
    if not ti:
        raise HTTPException(status_code=400, detail="缺少体卦五行（ti_wuxing 或 gua_data.tiyong.ti_wuxing）")
    res = waijing.analyze_many(req.omen, ti, inner_net=req.inner_net,
                              direction=req.direction, motion=req.motion, chosen=req.chosen)
    res["prompt_block"] = waijing.to_prompt_block(res)
    return res


@app.post("/api/bazi/paipan")
async def bazi_paipan(request: BaziRequest, http_request: Request):
    """
    四柱八字：出生时间（公历/农历，可选夏令时还原与真太阳时）→ 纯排盘（JSON）
    校时顺序：还原夏令时 → 经度校正 → 均时差
    """
    rate_limit(http_request, "bazi_paipan", limit=60, window_sec=60)   # 纯计算，放宽些
    try:
        data = build_bazi_paipan(
            request.year, request.month, request.day,
            request.hour, request.minute, request.gender,
            calendar=request.calendar, leap_month=request.leap_month,
            dst=request.dst, true_solar=request.true_solar,
            longitude=request.longitude,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"排盘失败（请检查出生日期是否有效）: {str(e)}")

    # 改运链·天地气背景与空间环境气（只作背景展示，不进吉凶判定）
    from yunqi import yunqi, dili_wufang, buqi
    _gz = data["bazi"][0]["ganzhi"]
    data["yunqi"] = yunqi(_gz)
    data["yunqi"]["六步"] = buqi(_gz, request.year)
    data["dili"] = dili_wufang(request.longitude, request.latitude)
    return data


# ============================================================
# 大运流年详批（事业 / 财运 / 感情）
# ============================================================
# 定位（站长 2026-10 定）：确定性归代码、语言归 AI。
#   dayun_detail.dayun_scaffold 把一切可计算的部分算定（干支十神、喜忌、结构、引动、
#   驿马/桃花/禄刃/财库、重点年份、流月），先以 `scaffold` 事件原样下发；
#   AI 只把算定的事实讲成白话，并补「具体事件/1–10 评分/一句话标题/路径推演」——
#   这四类无逐字书证、不可复现，属 AI 语言层，提示词要求逐条标注「AI 推断，非书证」。
# 额度：`ai=true` 扣一次（自带 key 不计），`ai=false` 只出骨架、不调 LLM、不扣额度。
DAYUN_MAX_TOKENS = int(os.getenv("DAYUN_MAX_TOKENS", "6000"))   # 十年逐项详批，预算要给足

DAYUN_SYSTEM_PROMPT = """
# 大运流年详批（事业 / 财运 / 感情）· 系统提示词

你是子平八字的大运流年详批师。用户消息里给你两块材料：
①【分析规则】本维度的规则表——十神意象、有利/不利结构、宫位、场景速查、禁止清单、
   干支关系表（五合、相冲、六合、三合半合拱、三会半会、六冲、三刑自刑、六害、六破、伏吟）；
②【骨架】代码算定的确定性数据——命理纲线（含补身三件事素材）、原局底盘、大运表、
   逐年表（干支十神五行喜忌、与大运/原局逐条关系、成局、神煞）、吉年险年、流月表。

## 判断顺序（必须照做）
原局结构 → 强弱喜忌 → 大运环境 → 流年触发 → 干支关系（合冲刑害破伏吟拱会）→ 具体事件。

## 硬约束
一、干支十神、五行、喜忌、结构、合冲刑害破伏吟拱会、成局、神煞、吉年险年、流月干支，
    只能**照抄骨架数据**，不得重算、不得修正、不得发明骨架里没有的关系。
二、喜忌定吉凶（《子平真诠·论用神》「为我所喜，枭伤七煞，皆为吉神；犯我所忌，正官财印，
    同为恶物」）：喜用为吉、忌神为凶、闲神为平、调候为急（调候优先）。
三、神煞为辅（《子平真诠·论星辰无关格局》「神煞吉凶，无关祸福」）：驿马、咸池（桃花）、
    禄、刃只在骨架标注出现时提一句，不作主结论；桃花≠正缘、夫妻宫冲≠离婚。
四、称引纪律：你手里没有典籍全文，**不许凭记忆引录原文**。引文只能引用本提示词与用户消息
    已写出的字句；称引只许用已列出的书名篇名。**未列出的书名、篇名、条文一律按「典籍未载」
    处理——编造出处比说「不知道」更严重。**
五、每个判断必须落到「哪个十神＋哪个宫位＋哪组生克合冲刑害破」，禁止空话与模糊话术。
六、财库忌套「刑冲开库」：《子平真诠·论墓库刑冲之说》明斥「财官入库无冲不发之说，
    最为流俗谬谈」——财库重在透干会支；骨架只报「财库引动」，照读即可。
七、具体事件、1–10 评分、一句话标题、路径推演**没有逐字书证、不可复现**，属你的推断——
    按输出格式写进对应条目即可，文档页脚会统一声明此边界；正文中不逐条打标。
八、感情维度：婚恋状态以骨架给的用户提供值为准（单身/恋爱中/已婚），不得臆测改写。

## 输出格式（照此骨架，一字不差地保留标题层级与条目名）
先出「〇、命理总纲线」块（严格照下方模板，数据来自骨架，措辞可微调但条目不得增删）：

## 〇、命理总纲线（开头一次 · 全档通用）

> **乾造/坤造**：四柱（公历 ×，农历 ×）｜男命/女命
> 起运：×岁×个月（××××-××-×× 交运）｜排盘复核：程序排定

**强弱**：**身×**（日主×，阳/阴×；生于×月×令，根气×，生扶×、克泄耗×）。
**喜用**：**×（十神类·第一用神）** ＋ **×（十神类·次喜神）**。
**忌神**：**×（十神类）最重** ＞ ×（十神类）次之 ＞ ×（十神类）又次（按骨架忌神五行排序）。
**仇神**：×（依骨架，无则写「无」）。
**一生总原则**：走「**××路线**」——靠**××（第一用神现实对应）**与**××（次喜神现实对应）**立身。
忌××之乡（忌神）；**××之年只守不攻、不投机、不硬碰领导**（按忌神现实对应写）。
**现实"补身"三件事（按所缺五行，先补第一用神、再补次喜神）**：
1. **补第一用神「×·十神」**（最重要）——现实对应：××。
2. **补次喜神「×·十神」**——现实对应：××。
3. **管理忌神「×·十神」**——现实对应：××。

### 〇·一、怎么看这份指南
- 命理是**比喻不是判决**（如天气预报，提示趋势与概率，不注定结局）。
- 身弱不等于命不好（按骨架实际强弱写一句：此造贵在「××」的底子，需借××之年与自身补强把格局坐实）。
- **我命由我不由天**：吉年顺势用力，凶年逆势守成，关键年份重点设防。

### 〇·二、关键年份速查

| 类别 | 🚨 关键吉年（主动投入） | 🚨 关键险年（主动防守） |
|---|---|---|
| **事业** | ×（骨架吉年） | ×（骨架险年） |

（只填**本维度**那一行；感情维度时在表下另起一行说明「按当前状态（××）」即可，不得给别的维度加行。）

### 〇·三、大运总览

| 大运 | 干支十神 | 区间 | 年龄 | 主题 |
|---|---|---|---|---|
| ×× | 干（十神·喜忌）＋支（十神·喜忌） | ××××–×××× | ×–×岁 | 四字主题 |

### 大运主题一览

- ××：四字主题

再按维度骨架输出：

## 一、原局底盘（按【分析规则】该维度「原局」项逐条：官杀/印星/食伤/财星/比劫状态、结构成立与否照骨架读、适合路径与最大优势短板）

## 二、大运分析（表格同「〇·三」，并逐运一段：承压能力、结构、适宜动作、趋势与评分）

## 三、逐年分析（每一年严格照此层级与条目，一年不漏）：

# ×××× ××干支年 · ××大运（约×岁）

#### 事业（××××）

### ×××× ××干支｜十神＋十神 ——「一句话标题」★/⚠️

- **喜忌**：天干×（十神·五行·喜忌）＋地支×（十神·五行·喜忌）。
- **与原局大运**：与大运××——（照骨架「大运关系」逐条）；与原局——（照骨架「原局关系」逐条，标柱位）。
- **引动**：（照骨架「原局关系/成局」归纳：引动哪柱、哪颗十神、哪个宫位）。
- **工作环境**：稳定/调整/变动/冲突。
- **职位趋势**：晋升/平级/降职/无变化/职责增加。
- **收入**：趋势一句话。
- **领导关系**：一句话。
- **同事与竞争关系**：一句话。
- **适合行动**：明确宜/忌（跳槽/转行/考编/考证/创业/争取晋升）。
- **具体事件**：最可能出现的 1–2 件（AI 推断）。
- **风险**：类别。
- **评分 ×/10｜依据**：回填「哪组十神＋哪个宫位＋哪组生克合冲刑害破」。

（财运维度逐年条目为：喜忌 / 与大运关系 / 与原局作用 / 结构 / 收入趋势 / 财富来源 /
主要支出 / 适合行动 / 具体事件 / 风险等级（低中高）/ 评分×/10｜依据；
感情维度逐年条目为：喜忌 / 与大运关系 / 与原局作用 / 刑冲合害（照骨架关系逐条）/
桃花强度 / 桃花性质 / 按当前状态（××）/ 适合行动 / 易发生 / 具体事件 / 评分×/10｜依据。）

## 四、必须区分的情况 / 重点年份筛选（事业按 6 组、财运按 7 组、感情按 7 组，见【分析规则】；每组给年份与一句理由）

## 五、重点年份流月（只对骨架列出的流月年份，逐月按骨架「干支·十神」说喜忌与主题；月份干支不得编造）

## 六、趋势总结（阶段表 + 总纲一段）

## 附：N年评分总表

| 年份 | 干支 | 十神 | 大运 | 评分 | 一句话 |
|---|---|---|---|---|---|
| ×××× | ×× | ××＋×× | ×× | ×.× | 四字评语 |

*本详批依《渊海子平》《子平真诠》《穷通宝鉴》三家原文法度推演，强弱喜忌已定：身×、喜×忌×。
命理为传统学说，仅供参考，具体决策请结合现实判断。*
"""


def build_dayun_user_prompt(scaffold: dict) -> str:
    """把确定性骨架与规则表拼成用户消息（AI 实收字句，同时是称引基准）。"""
    g = scaffold["gangxian"]
    L = ["【骨架·命理纲线（代码算定，照抄）】"]
    L.append("四柱：%s｜%s｜日主%s（%s）" % (g["pillars"], g["zao"], g["day_master"], g["day_master_wx"]))
    L.append("公历：%s｜农历：%s" % (g["solar"], g["lunar"]))
    L.append("强弱：%s｜喜用：%s｜忌神：%s｜闲神：%s" % (
        g["tier"], "、".join(g["F"]) or "无", "、".join(g["J"]) or "无",
        "、".join(g["xianshen"]) or "无"))
    if g["T0"]:
        L.append("调候：%s（%s）" % ("、".join(g["T0"]), g["t0_src"]))
    if g["from_ge"]:
        L.append("格局：%s" % g["from_ge"])
    L.append("五行字数：%s" % "、".join("%s%d" % (k, v) for k, v in g["tally"].items()))
    tr = g.get("tier_reason") or {}
    if tr:
        L.append("强弱素材：月令%s｜日主字数%s｜生扶字数%s｜克泄耗字数%s" % (
            tr.get("月令"), tr.get("日主字数"), tr.get("生扶字数"), tr.get("克泄耗字数")))
    qy = g["起运"]
    L.append("起运：%s岁%s个月（%s）" % (qy["years"], qy["months"], qy["solar"]))
    L.append("补身三件事素材（十神类与五行照此写，现实对应为固定语汇）：")
    for b in g.get("buxin") or []:
        L.append("· %s「%s·%s」——现实对应：%s" % (b["性质"], b["五行"], b["十神"], b["现实"]))
    L.append("")
    L.append("【骨架·原局底盘（代码算定）】")
    if scaffold["dimension"] == "ganqing":
        pei = scaffold["yuanju"]["配偶星"]
        L.append("配偶星：%s｜五行%s｜喜忌%s｜透干：%s｜藏：%s" % (
            pei["星"], pei["五行"], pei["喜忌"], "、".join(pei["透干"]) or "无",
            "、".join(pei["藏"]) or "无"))
        fu = scaffold["yuanju"]["夫妻宫"]
        L.append("夫妻宫：日支%s｜十神%s｜五行%s｜关系：%s" % (
            fu["日支"], fu["十神"], fu["五行"], "；".join(fu["关系"])))
        L.append("桃花：%s" % scaffold["yuanju"]["桃花"]["支"])
        if "女命伤官" in scaffold["yuanju"]:
            sg = scaffold["yuanju"]["女命伤官"]
            L.append("女命伤官：%s（%s）" % ("透干：" + "、".join(sg["透干"]) if sg["透干"] else "未透", sg["src"]))
    else:
        for s in scaffold["yuanju"]["结构"]:
            L.append("· %s＝%s（%s；%s）" % (s["结构"], s["状态"], s["透藏"], s["src"]))
        if scaffold["dimension"] == "caiyun":
            c = scaffold["yuanju"]["财星"]
            L.append("财星：五行%s｜库%s｜喜忌%s" % (c["五行"], c["库"], c["喜忌"]))
        else:
            L.append("事业宫（月柱）：%s｜十神%s" % (
                scaffold["yuanju"]["宫位"]["月柱"], scaffold["yuanju"]["宫位"]["月柱十神"]))
    L.append("")
    L.append("【骨架·大运表（代码算定，十二步）】")
    for d in scaffold["dayun_rows"]:
        L.append("%s（干%s·%s，支%s·%s）｜%s–%s岁（%s–%s年）｜神煞：%s" % (
            d["干支"], d["干十神"], d["干喜忌"], d["支十神"], d["支喜忌"],
            d["起"], d["止"], d["起年"], d["止年"], "、".join(d["神煞"]) or "无"))
    L.append("")
    L.append("【骨架·逐年表（代码算定，%s–%s 年）】" % (scaffold["year_from"], scaffold["year_to"]))
    for r in scaffold["year_rows"]:
        if r.get("note"):
            L.append("%s年：%s" % (r["year"], r["note"]))
            continue
        flags = []
        for k in ("官杀当值", "伤官见官", "印星当值", "财星当值", "财库引动", "比劫当值",
                  "配偶星当值", "桃花", "夫妻宫引动", "禄", "刃"):
            if r.get(k):
                flags.append("%s=%s" % (k, r[k]) if not isinstance(r[k], bool) else k)
        yjl = "；".join("%s%s：%s" % (x["柱"], x["干支"], "、".join(x["关系"]))
                        for x in r.get("原局关系") or []) or "无"
        L.append("%s年 %s（约%s岁）｜大运%s｜干%s(%s·%s)，支%s(%s·%s)｜大运关系：%s｜原局关系：%s｜成局：%s｜神煞：%s｜%s" % (
            r["year"], r["干支"], r["age"], r["大运"],
            r["干十神"], r.get("干五行", ""), r["干喜忌"],
            r["支十神"], r.get("支五行", ""), r["支喜忌"],
            "、".join(r.get("大运关系") or []) or "无",
            yjl, "、".join(r.get("成局") or []) or "无",
            "、".join(r.get("神煞") or []) or "无", "；".join(flags)))
    L.append("")
    L.append("【骨架·关键年份（代码算定：干支本气五行皆喜/调候＝吉年，皆忌＝险年）】")
    L.append("· 吉年：%s" % ("、".join(str(y) for y in scaffold["key_years"].get("吉年") or []) or "无"))
    L.append("· 险年：%s" % ("、".join(str(y) for y in scaffold["key_years"].get("险年") or []) or "无"))
    for label, yrs in (scaffold["key_years"].get("筛选") or {}).items():
        L.append("· %s：%s" % (label, "、".join(str(y) for y in yrs) or "无"))
    L.append("")
    L.append("【骨架·重点年份流月（代码算定，干支月按节令）】")
    for y, months in scaffold["liu_yue"].items():
        L.append("%s 年：%s" % (y, "｜".join("%s月%s(%s·%s)" % (m["月"], m["干支"], m["干十神"], m["支十神"])
                                               for m in months)))
    L.append("")
    L.append("婚恋状态（感情维度，用户提供）：%s" % (scaffold["marital_status"] or "未提供"))
    L.append("")
    L.append(dayun_detail.rules_prompt_block(scaffold["dimension"]))
    L.append("")
    L.append("请按系统提示词的输出格式逐字执行：〇命理总纲线 → 〇·一/〇·二/〇·三 → 一、原局底盘 → "
             "二、大运分析 → 三、逐年分析（一年不漏，标题与条目层级照模板）→ 四、筛选/区分 → "
             "五、重点年份流月 → 六、趋势总结 → 附、评分总表。确定性内容照骨架，"
             "事件/评分/标题属 AI 推断，页脚统一声明边界。")
    return "\n".join(L)


class DayunRequest(BaseModel):
    birth: dict = {}              # 与 /api/bazi/paipan 同构
    dimension: str = ""           # shiye | caiyun | ganqing
    year_from: int = 0
    year_to: int = 0
    marital_status: str = ""      # 感情维度必填：单身 | 恋爱中 | 已婚
    ai: bool = False              # true 才调 LLM（扣一次额度；自带 key 不计）
    llm: LlmOverride = None
    tier_override: str = ""
    profile_id: str = ""


@app.post("/api/bazi/dayun")
async def bazi_dayun(req: DayunRequest, http_request: Request):
    """大运流年详批：先出确定性骨架（scaffold 事件），再按 ai 开关流式出 AI 详批。

    为什么要拆骨架与 AI 两段：骨架全部是代码算定（干支十神/喜忌/结构/引动/神煞/
    重点年份/流月），不花 AI、不扣额度；AI 只负责白话与事件级推断。
    """
    rate_limit(http_request, "bazi_dayun", limit=12, window_sec=60)
    dim = (req.dimension or "").strip().lower()
    if dim not in dayun_detail.DIMENSIONS:
        raise HTTPException(status_code=400, detail="维度必须是 shiye（事业）/ caiyun（财运）/ ganqing（感情）")
    if dim == "ganqing" and (req.marital_status or "").strip() not in dayun_detail.MARITAL:
        raise HTTPException(status_code=400, detail="感情详批需要婚恋状态（单身 / 恋爱中 / 已婚），请选择后重试")
    yf = int(req.year_from or 0) or datetime.now().year
    yt = int(req.year_to or 0) or (yf + 9)
    try:
        scaffold = dayun_detail.dayun_scaffold(req.birth, dim, yf, yt,
                                               (req.marital_status or "").strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    async def gen():
        yield f"data: {json.dumps({'type': 'scaffold', 'data': scaffold}, ensure_ascii=False)}\n\n"
        if not req.ai:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        llm_ov, llm_err = _resolve_llm(req.llm)
        if llm_ov:
            q = {"allowed": True, "scope": "byok"}
        elif llm_err:
            q = {"allowed": False, "scope": "llm",
                 "message": "模型设置无法使用：%s" % llm_err,
                 "hint": "到「API 设置」里检查厂商、key 与模型名；也可以清空设置，改用每日免费额度。",
                 "resets_at": ""}
        else:
            q = _quota_acquire(http_request)
        if not q["allowed"]:
            yield _degrade_event(q)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        system = DAYUN_SYSTEM_PROMPT
        user = build_dayun_user_prompt(scaffold)
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        _parts, _st = [], {}
        try:
            # disable_thinking=True：详批文字长，不能让思考把 max_tokens 预算烧光
            async for chunk in _stream_llm("", messages=messages, max_tokens=DAYUN_MAX_TOKENS,
                                           disable_thinking=True, state=_st, llm=llm_ov):
                _parts.append(chunk)
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
            _tc = _truncated_event(_st, DAYUN_MAX_TOKENS)
            if _tc:
                yield _tc
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'AI 暂时不可用：{str(e)}'}, ensure_ascii=False)}\n\n"
        # 回检：骨架里没有应期日期，日期白名单为空 → aicheck 跳过日期项；
        # 称引以 system+user 全量实收为基准（AI 只许引提示词里已写出的篇名）。
        _v = _verify_event("".join(_parts), {"yingqi": {}, "remedy": {}},
                            "大运流年详批·%s" % dayun_detail.DIMENSIONS[dim],
                            req.tier_override or "", _review_base(system, user))
        if _v:
            yield _v
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


# ============================================================
# 记录（统一表：起卦与排盘的可回放快照；反馈是附在记录上的附件）
# ============================================================
class RecordRequest(BaseModel):
    kind: str                    # meihua | liuyao | bazi
    title: str = ""              # 卦名 / 四柱 / 名字
    subtitle: str = ""           # 问题 / 阳历
    question: str = ""
    payload: dict = {}           # 回放所需完整快照


def _attach_outcomes(items: list, owner: str = "") -> list:
    """把决策日志里的"应验/未验"反馈挂回记录（反馈是记录的附件，刷新后仍在）"""
    ids = []
    for it in items:
        p = it.get("payload") if isinstance(it, dict) else None
        if isinstance(p, dict) and isinstance(p.get("log_id"), int):
            ids.append(p["log_id"])
    table = log_outcomes(ids, owner)
    for it in items:
        p = it.get("payload") if isinstance(it, dict) else None
        if not isinstance(p, dict):
            continue
        lid = p.get("log_id")
        if isinstance(lid, int) and table.get(lid):
            p["outcome"] = table[lid]
    return items


@app.get("/api/records")
async def records_list(request: Request, kind: str = "", limit: int = 200):
    """记录列表（置顶优先、时间倒序）——**只返回调用者自己的记录**"""
    owner = owner_of(request)
    return {"records": _attach_outcomes(rec_list(kind, limit, owner), owner)}


@app.post("/api/records")
async def records_add(req: RecordRequest, request: Request):
    """新增一条记录（起卦/排盘完成后自动调用）；归属取自令牌"""
    rate_limit(request, "records_add", limit=60, window_sec=60)
    try:
        return rec_add(req.kind, req.title, req.subtitle, req.question, req.payload,
                       owner=require_owner(request))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/records/detail")
async def records_detail(id: int, request: Request):
    """取一条记录（含回放快照）——非本人记录一律视为不存在（不区分无权/不存在，避免探测）"""
    owner = owner_of(request)
    item = rec_get(int(id), owner)
    if not item:
        raise HTTPException(status_code=404, detail="记录不存在")
    return _attach_outcomes([item], owner)[0]


class RecordUpdateRequest(BaseModel):
    id: int
    title: Optional[str] = None
    # 副标题：六爻改判用神后要跟着更新（里面写着"用神X · 补Y"），
    # 否则列表里显示旧用神、回放却是新用神。
    subtitle: Optional[str] = None
    note: Optional[str] = None
    pinned: Optional[int] = None
    # 回填快照：起卦与 AI 断卦分成两步后，前端先在"排盘出来"时存一条（保证盘不丢），
    # AI 断完再把这个带断语的完整快照盖回来——一次解读一条记录，不重复也不丢。
    payload: Optional[dict] = None


@app.patch("/api/records")
async def records_update(req: RecordUpdateRequest, request: Request):
    """编辑（标题/副标题/备注/快照）与置顶——仅限自己的记录"""
    if not rec_update(req.id, req.title, req.note, req.pinned, owner_of(request),
                      payload=req.payload, subtitle=req.subtitle):
        raise HTTPException(status_code=404, detail="记录不存在或无可更新字段")
    return {"ok": True}


@app.delete("/api/records")
async def records_delete(id: int, request: Request):
    """删除一条记录（软删除：进「最近删除」，30 天内可恢复）——仅限自己的"""
    if not rec_remove(int(id), owner_of(request)):
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"ok": True, "soft": True, "trash_days": rec_trash_days}


@app.get("/api/records/trash")
async def records_trash(request: Request, limit: int = 200):
    """最近删除（默认保留 30 天）：可恢复到列表，或彻底删除——仅限自己的"""
    return {"records": rec_list_deleted(limit, owner_of(request)), "trash_days": rec_trash_days}


class RecordIdsRequest(BaseModel):
    ids: list[int] = []


@app.post("/api/records/restore")
async def records_restore(req: RecordIdsRequest, request: Request):
    """从「最近删除」恢复（支持批量）——仅限自己的"""
    owner = owner_of(request)
    ok = [i for i in req.ids if rec_restore(int(i), owner)]
    return {"ok": True, "restored": ok, "count": len(ok)}


@app.delete("/api/records/purge")
async def records_purge(id: int, request: Request):
    """彻底删除一条（不可恢复）——仅限自己的"""
    if not rec_purge(int(id), owner_of(request)):
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"ok": True}


@app.post("/api/records/trash/empty")
async def records_empty_trash(request: Request):
    """清空「最近删除」（不可恢复）——只清自己的"""
    n = rec_empty_trash(owner_of(request))
    return {"ok": True, "purged": n}


# ============================================================
# 八字记录（兼容旧路径：内部转发到统一记录表，避免旧链接失效）
# ============================================================
class BaziRecordRequest(BaseModel):
    name: str = ""
    gender: str = ""
    solar: str = ""
    lunar: str = ""
    pillars: str = ""
    birth: dict = {}


@app.post("/api/bazi/records")
async def bazi_records_add(req: BaziRecordRequest, request: Request):
    """保存一份八字记录（每份一条，互不覆盖）"""
    if not (req.solar or req.pillars):
        raise HTTPException(status_code=400, detail="缺排盘信息，无法保存")
    rec = rec_add("bazi", req.name or "未命名", req.pillars or req.solar, "",
                  {"birth": req.birth, "solar": req.solar, "lunar": req.lunar,
                   "gender": req.gender, "pillars": req.pillars},
                  owner=require_owner(request))
    return {"id": rec["id"], "name": rec["title"], "solar": req.solar, "lunar": req.lunar,
            "gender": req.gender, "pillars": req.pillars, "birth": req.birth,
            "created_at": rec["created_at"]}


@app.delete("/api/bazi/records")
async def bazi_records_delete(id: int, request: Request):
    """删除一条八字记录（转发到统一记录表）"""
    if not rec_remove(int(id), owner_of(request)):
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"ok": True}


# ============================================================
# 四柱八字：农历辅助 / 全国地区经纬度
# ============================================================
_REGIONS_CACHE = None


@app.get("/api/bazi/lunar")
async def bazi_lunar(year: int, month: Optional[int] = None, day: Optional[int] = None,
                     leap_month: bool = False):
    """
    农历年信息（闰月、各月天数）；带 year/month/day 时同时返回农历→公历转换。
    """
    meta = lunar_meta(year)
    if month is not None and day is not None:
        meta["conversion"] = lunar_to_solar(year, month, day, leap_month)
    return meta


@app.get("/api/bazi/regions")
async def bazi_regions():
    """全国省/市/区县 + 经纬度（民政部/统计局行政区划数据）"""
    global _REGIONS_CACHE
    if _REGIONS_CACHE is None:
        path = Path(__file__).parent / "china_regions.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="地区数据文件缺失: china_regions.json")
        _REGIONS_CACHE = json.loads(path.read_text(encoding="utf-8"))
    return _REGIONS_CACHE


# ============================================================
# 命局档案 / 命卦校验
# ============================================================
def _month_wx_from_now():
    """按当前时间推当令月令五行（快照层缺省值）"""
    from datetime import datetime as _dt
    now = _dt.now()
    from lunar_python import Solar as _Solar
    ec = _Solar.fromYmdHms(now.year, now.month, now.day, now.hour, now.minute, now.second).getLunar().getEightChar()
    from bazi_engine import ZHI_WUXING
    return ZHI_WUXING[ec.getMonthZhi()]


@app.post("/api/mingju/profile")
async def mingju_save(req: MingjuProfileRequest, request: Request):
    """保存命局档案并返回基线（核心静态层）。令牌与档案 id 必须一致，防冒写他人档案。"""
    rate_limit(request, "profile_save", limit=30, window_sec=60)
    owner = require_owner(request, req.id)
    if owner != req.id:
        raise HTTPException(status_code=403, detail="令牌与档案 id 不一致")
    birth = req.model_dump()
    birth.pop("id")
    try:
        baseline = save_profile(req.id, birth)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"命局档案计算失败: {str(e)}")
    return {"id": req.id, "baseline": baseline}


@app.get("/api/mingju/profile")
async def mingju_get(id: str, request: Request):
    """读档案：令牌必须与 id 一致（否则视为不存在，避免枚举他人档案）"""
    require_self(request, id)
    prof = get_profile(id)
    if not prof:
        raise HTTPException(status_code=404, detail="未找到该命局档案")
    return prof


@app.delete("/api/mingju/profile")
async def mingju_delete(id: str, request: Request):
    require_self(request, id)
    if not delete_profile(id):
        raise HTTPException(status_code=404, detail="未找到该命局档案")
    return {"deleted": id}


@app.get("/api/qipan")
async def qipan_summary(request: Request):
    """气盘总览（只读）：底账＋判运链＋改运链一屏并列。

    三链框架（站长 2026-09-25 定稿）：只做并列展示，不做跨链加减；
    判运链用命家时间口径，改运链用医家时间口径，各用各家。
    """
    rate_limit(request, "qipan", limit=60, window_sec=60)
    owner = require_owner(request)
    from yunqi import year_yunqi, buqi, current_bu
    from datetime import datetime as _dtt
    from liunian import current_liunian, shiwang_liunian
    from decision_log import recent as _log_recent

    prof = get_profile(owner)
    # 旧档案（运气字段加入前保存的）没有 yunqi/dili：就地从出生信息现算，不落库。
    if prof and not prof["baseline"].get("yunqi"):
        try:
            from yunqi import yunqi as _yq, dili_wufang as _dili
            from bazi_engine import build_bazi_paipan as _bp
            b = prof["birth"]
            _d = _bp(b.get("year"), b.get("month"), b.get("day"), b.get("hour", 0),
                     b.get("minute", 0), b.get("gender", 1),
                     calendar=b.get("calendar", "solar"), leap_month=b.get("leap_month", False),
                     dst=b.get("dst", False), true_solar=b.get("true_solar", False),
                     longitude=b.get("longitude", 120.0))
            prof["baseline"]["yunqi"] = _yq(_d["bazi"][0]["ganzhi"])
            prof["baseline"]["dili"] = _dili(b.get("longitude", 120.0), b.get("latitude"))
        except Exception:
            pass
    _now = _dtt.now()
    dn = year_yunqi(_now.year)
    dn["六步"] = buqi(dn["ganzhi"], _now.year)
    dn["当前步"] = current_bu(_now.year, _now.month, _now.day)
    month_wx = _month_wx_from_now()
    ln = current_liunian()
    strength, weight = shiwang_liunian(ln["wx"], month_wx)
    rows = _log_recent(6, owner) or []
    rec_sum = []
    for r in rows:
        if r.get("kind") != "check":
            continue
        rec_sum.append({
            "id": r.get("id"), "ts": r.get("ts"),
            "question": (r.get("question") or "")[:24],
            "net": r.get("net"), "level": r.get("level"),
            "decision": (r.get("decision") or "")[:40],
            "final_R": r.get("final_R"),
        })
        if len(rec_sum) >= 4:
            break
    return {
        "profile": prof,
        "suinian": {"ganzhi": ln["ganzhi"], "wx": ln["wx"],
                    "strength": strength, "weight": weight, "month_wx": month_wx},
        "dangnian": dn,
        "recent": rec_sum,
    }


def _parse_dt(raw: str | None):
    """起局接口的时间解析：'YYYY-MM-DDTHH:MM[:SS]' 或 'YYYY-MM-DD HH:MM[:SS]'，缺省为现在。"""
    from datetime import datetime as _dt
    if not raw:
        return _dt.now()
    s = raw.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return _dt.strptime(s, fmt)
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail="时间格式应为 YYYY-MM-DD HH:MM")


class QimenRequest(BaseModel):
    dt: str | None = None   # 起局时刻，缺省为服务器当前时间
    pan: str = "both"       # 转盘 / 飞盘 / both / 定局


class DaliurenRequest(BaseModel):
    dt: str | None = None     # 起课时刻，缺省为服务器当前时间
    shizhi: str | None = None  # 活时（子丑寅卯辰巳午未申酉戌亥），缺省用正时
    nianzhu: str | None = None   # 求占者出生年干支（六十甲子之一），推本命/行年用
    xingbie: str | None = None   # 求占者性别（男/女），推本命行年用
    nianzhu2: str | None = None  # 配偶出生年干支（繁昌课用，可选）
    xingbie2: str | None = None  # 配偶性别


@app.post("/api/qimen")
async def qimen_qipan(request: Request, body: QimenRequest):
    """奇门遁甲起局（时家·数理奇门）：拆补法定局＋转盘/飞盘排盘。

    口径与书证见 qimen.py 模块注释与 docs/判据总表.md 第五节。起局不含断法。
    """
    rate_limit(request, "qimen", limit=60, window_sec=60)
    from qimen import qimen as _qimen
    dt = _parse_dt(body.dt)
    try:
        out = _qimen(dt, pan=body.pan)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"起局失败：{e}")
    out["书证"] = ("《奇门遁甲秘笈大全》《奇门法窍》《奇门启悟》；定局＝拆补法（站长裁定）；"
                   "起局规则逐条登记于 docs/判据总表.md 第五节")
    return out


@app.post("/api/daliuren")
async def daliuren_qike(request: Request, body: DaliurenRequest):
    """大六壬起课：天地盘、四课、三传（九宗门）、贵人十二天将、遁干、六亲、空亡。

    口径与书证见 daliuren.py 模块注释与 docs/判据总表.md 第六节。起课不含断法。
    """
    rate_limit(request, "daliuren", limit=60, window_sec=60)
    from daliuren import qike as _qike
    from qimen import GZ60 as _GZ60
    shi = body.shizhi
    if shi is not None:
        from qimen import ZHI as _ZHI
        if shi not in _ZHI:
            raise HTTPException(status_code=400, detail="占时必须为十二地支之一")
    for nm, xb in ((body.nianzhu, body.xingbie), (body.nianzhu2, body.xingbie2)):
        if nm:
            if nm not in _GZ60:
                raise HTTPException(status_code=400, detail="出生年干支必须为六十甲子之一")
            if xb not in ("男", "女"):
                raise HTTPException(status_code=400, detail="推本命行年需提供性别（男/女）")
    dt = _parse_dt(body.dt)
    try:
        out = _qike(dt, shi_zhi=shi, nianzhu=body.nianzhu or "", xingbie=body.xingbie or "",
                    nianzhu2=body.nianzhu2 or "", xingbie2=body.xingbie2 or "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"起课失败：{e}")
    out["书证"] = ("《六壬大全》《大六壬指南》《六壬金针》；贵人＝甲戊庚牛羊、月将＝中气交节时刻后换将"
                   "（站长裁定）；起课规则逐条登记于 docs/判据总表.md 第六节")
    return out


class LeixiangRequest(BaseModel):
    dt: str | None = None
    shizhi: str | None = None
    wenshi: str = "求财"   # 问事类别（说约类神说事类神之键）
    nianzhu: str | None = None
    xingbie: str | None = None
    nianzhu2: str | None = None
    xingbie2: str | None = None


@app.post("/api/leixiang")
async def leixiang_quyong(request: Request, body: LeixiangRequest):
    """六壬类象层：起课＋类神取用＋射覆占物。

    只标盘面事实与书证表（类神落宫/入传/生克合冲刑害；射覆多维候选），不代断。
    书证：壬归（通类）、大六壬说约（类神说/十二天神/十二天将）、大六壬心镜
    （杂神门/杂将门）、六壬苗公射覆鬼撮脚；逐条登记于 docs/判据总表.md 第六节。
    """
    rate_limit(request, "leixiang", limit=60, window_sec=60)
    from daliuren import qike as _qike
    from leixiang import SHILEI, TONGLEI, leishen_qiyong, shefu
    shi = body.shizhi
    if shi is not None:
        from qimen import ZHI as _ZHI
        if shi not in _ZHI:
            raise HTTPException(status_code=400, detail="占时必须为十二地支之一")
    if body.wenshi not in SHILEI and body.wenshi not in TONGLEI:
        raise HTTPException(status_code=400,
                            detail=f"问事类别须为：{'、'.join(dict.fromkeys(list(SHILEI) + list(TONGLEI)))}")
    from qimen import GZ60 as _GZ60
    for nm, xb in ((body.nianzhu, body.xingbie), (body.nianzhu2, body.xingbie2)):
        if nm:
            if nm not in _GZ60:
                raise HTTPException(status_code=400, detail="出生年干支必须为六十甲子之一")
            if xb not in ("男", "女"):
                raise HTTPException(status_code=400, detail="推本命行年需提供性别（男/女）")
    dt = _parse_dt(body.dt)
    try:
        out = _qike(dt, shi_zhi=shi, nianzhu=body.nianzhu or "", xingbie=body.xingbie or "",
                    nianzhu2=body.nianzhu2 or "", xingbie2=body.xingbie2 or "")
        from lunar_python import Solar
        ec = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0) \
            .getLunar().getEightChar()
        out["月建"] = ec.getMonth()[1]
        out["类神取用"] = leishen_qiyong(out, body.wenshi, nianming=out.get("年命"))
        out["射覆"] = shefu(out, dt)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"起课失败：{e}")
    out["书证"] = ("类神取用与物类：壬归（通类）、大六壬说约（类神说/十二天神/十二天将）、"
                   "大六壬心镜（杂神门/杂将门）、六壬苗公射覆鬼撮脚（射覆诸诀）；"
                   "只标盘面事实与书证表，不代断。")
    return out


@app.post("/api/mingju/check")
async def mingju_check(req: MingjuCheckRequest, request: Request):
    """
    命卦校验：处方五行 R vs 命局三参考系（F/J/T0）。
    只比 R，五档生克关系格 → 顺/平/逆三净档；建议由 R（或被拦截后的 R'）派生。
    R 来源：梅花体用（gua）或已算好的 remedy（六爻/梅花）。
    """
    # profile_id 只接受"自己的"：本产品里档案主键就是归属令牌，所以客户端传来的 profile_id
    # 实质是**凭证别名**。此前它被当成普通数据直接喂给 get_profile / deterministic_conclusion，
    # 于是"无令牌 + 知道某个 id"也能拿回该命局的派生结论（F/J/T0 与四柱）。
    # 今天这与"已知令牌"等价、不算额外暴露，但它把"id 当凭证"这条错路留在了代码里——
    # 一旦将来档案 id 不再等于令牌、或 id 出现在任何链接里，它立刻变成 IDOR。所以这里前置堵死：
    # profile_id 要么为空（无需命局，纯卦侧校验），要么必须等于自己的令牌。
    #
    # 注意这里用 require_owner 而不是"无令牌就照常算"：既然本端点现在**必须**有归属才能
    # 把结果记进台账（见下），而台账是这个功能的交付物之一，那"没有令牌"就是缺了一个前提，
    # 应当明说（403），而不是安静地少给一半东西。校验本身仍是无状态计算，不碰他人数据。
    check_owner = require_owner(request)
    if req.profile_id and req.profile_id != check_owner:
        raise HTTPException(status_code=404, detail="未找到该命局档案")
    rate_limit(request, "mingju_check", limit=60, window_sec=60)
    if req.remedy and req.remedy.get("R"):
        rm = req.remedy
    elif req.gua and req.gua.get("ti_wuxing") and req.gua.get("yong_wuxing"):
        try:
            rm = meihua_remedy(
                req.gua.get("ti_wuxing"), req.gua.get("yong_wuxing"), req.gua.get("relation"),
                hu_wuxing=req.gua.get("hu_wuxing") or None,
                bian_wuxing=req.gua.get("bian_wuxing") or None,
                ti_status=req.gua.get("ti_status") or None,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"体用参数错误: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="需提供 gua（梅花体用）或 remedy（处方五行）")

    month_wx = req.month_wx or _month_wx_from_now()
    day_zhi = req.day_zhi or ""

    # 命局档案
    prof = get_profile(req.profile_id) if req.profile_id else None
    if prof:
        mingju = prof["baseline"]["mingju"]
        F, J, T0 = mingju["F"], mingju["J"], mingju["T0"]
        verdict = adjudicate(rm["R"], F, J, T0, month_wx)
        # 被拦截时改方/通关
        final_R = rm["R"]
        redirect_note = ""
        if verdict["gate"] == "block":
            final_R, redirect_note = redirect(rm["R"], verdict, F, J, T0)
            if not final_R:
                # 三重过滤后局内无解（2026-10-06 H3）：不回退到喂忌的原方冒充"改方"。
                # final_R 保持原处方——前端据此不显示「改方 X→Y」，只显示 redirect_note
                # （"待岁运通关之地"的说明），与裁决的"强制改方"字样在页面上并列可辨。
                final_R = rm["R"]
        baseline_view = mingju
        # 岁运层：流年引动（小权重参与；不改方、不设拦截，只升降档位与加注记）
        liunian_info = None
        try:
            ln = current_liunian()
            verdict, liunian_info = liunian_overlay(ln, month_wx, mingju, verdict)
        except Exception:
            liunian_info = None
    else:
        # 无档案：跳过命局校验，仅按事体输出，蓝条
        verdict = {"net": "平", "level": "yellow", "gate": "limited",
                   "decision": "未提供命局基线，仅按事体输出", "hits": [],
                   "tiao_active": False}
        final_R = rm["R"]
        redirect_note = ""
        baseline_view = None
        liunian_info = None    # 无档案无命局参考系，岁运层不参与

    # 「按最终处方」栏应期：用最终生效的五行（改方后）在**同一个窗口**里算一遍。
    # 为什么放在这里而不是起卦端点：起卦时还不知道命局会不会拦截、改成哪个五行，
    # 于是应期（按卦栏）永远用原处方、页面（宜忌表）用改方，两边看着互相打架。
    # 此处拿到 final_R 后补齐第二栏，两栏并排显示、各自标明依据。
    yingqi_final = []
    try:
        from yingqi import meihua_yingqi_column
        _st = None
        if req.yingqi_start:
            try:
                from datetime import date as _dt
                _st = _dt.fromisoformat(req.yingqi_start[:10])
            except Exception:
                _st = None
        if isinstance(final_R, str) and final_R:
            yingqi_final = meihua_yingqi_column(final_R, start=_st, hour_zhi=req.hour_zhi)
    except Exception as e:
        logging.getLogger("uvicorn.error").warning("[应期·处方栏] 计算失败：%s", e)
        yingqi_final = []

    # 流动五行判定表：处方要补的每个五行各一张（表头+命中档行+通关行+质地取向），
    # 有命局档案时标出命中档位行；无档案不判强弱、只出表头与通关行。
    # R2：卦侧干支层——六爻用神爻干支（remedy.details.用神爻.干支）优先，梅花用起卦日支。
    elements = list(dict.fromkeys([final_R] if isinstance(final_R, str) else list(final_R or [])))
    yong_ganzhi = ""
    try:
        yong_ganzhi = (rm.get("details", {}).get("用神爻", {}) or {}).get("干支", "") or ""
    except Exception:
        yong_ganzhi = ""
    flows = []
    flavors = {}
    for _wx in elements:
        try:
            _f = flow_plan(_wx, baseline_view, day_zhi=day_zhi, yong_ganzhi=yong_ganzhi)
            flows.append(_f)
            if _f.get("flavor"):
                flavors[_wx] = _f["flavor"]
        except Exception:
            pass

    suggestions = suggest_wuxing(elements, flavors=flavors)   # R1：质地分档进入建议层

    # S/M/L 档位（手动覆盖优先；歧义不猜）——先定档，择日窗口随档位
    tier_info = resolve_tier(req.question, req.tier_override or None)
    dims = tier_info["contract"].get("suggest_dims") or []
    if dims:
        for _k in list(suggestions.keys()):
            suggestions[_k] = {k: v for k, v in suggestions[_k].items() if k in dims}

    # 紧急层确定性择日（宜忌日期表）：随档位取窗口，无档案不做
    date_info = None
    if baseline_view:
        try:
            date_info = date_table(final_R, baseline_view.get("F"), baseline_view.get("J"),
                                   baseline_view.get("T0"), month_wx, tier_info["tier"])
        except Exception:
            date_info = None

    # 决策日志：完整推理链快照 + 规则/权重版本锚点 + 本次输出的 claim 清单（反馈对象）
    claims = []
    try:
        # 应期信息一并交给断言生成：应期此前没有可反馈的断言，而它恰恰是全站最敏感的自定数字
        yingqi_info = None
        if req.yingqi_dates:
            yingqi_info = {"dates": [str(d)[:10] for d in req.yingqi_dates if d],
                           "final_count": len(yingqi_final or [])}
        claims = build_claims(verdict, flows, liunian_info, date_info, tier_info,
                              elements, baseline_view, yingqi_info)
    except Exception:
        claims = []
    log_id = None
    # 归属只认令牌（check_owner 在函数开头已取，见那里的说明）。
    try:
        if check_owner != ANON_OWNER:
            log_id = append_check({
                # profile_id 记**自己的归属**，不记客户端传进来的值：这一列与 owner 语义上
                # 是一回事（档案主键即令牌），存客户端原值只会让它看起来像一列可以用来
                # 判权的字段，给后来的人留下"拿它做归属"的错觉。req.profile_id 的合法性
                # 已在函数开头校验过，无需在此重复保存。
                "kind": "check", "profile_id": check_owner, "question": req.question,
                "tier": tier_info["tier"], "tier_source": tier_info["source"],
                "R": rm.get("R"), "final_R": final_R,
                "F": baseline_view.get("F") if baseline_view else [],
                "J": baseline_view.get("J") if baseline_view else [],
                "T0": baseline_view.get("T0") if baseline_view else [],
                "from_ge": baseline_view.get("from_ge") if baseline_view else "",
                "net": verdict.get("net"), "level": verdict.get("level"),
                "gate": verdict.get("gate"), "decision": verdict.get("decision"),
                "liunian": liunian_info, "month_wx": month_wx, "day_zhi": day_zhi,
                "rules_version": RULES_VERSION, "weights_version": WEIGHTS_VERSION,
                "extra": {"source": req.source, "gua": req.gua} if (req.source or req.gua) else None,
                "claims": claims,
                # 整张流动五行判定表（站长 2026-09-19 定：存整张，不存摘要）。
                # 存它的**唯一理由**是 R5 那句"不静默"：同源不告警时写明为何不告警
                # （conflict_suppressed），而这句话此前只活在接口返回里，页面一关就没了。
                # 存了它，事后能回答的就不只是"当时判了什么"，而是"当时那张表长什么样、
                # 哪一格被压制、理由是什么"。代价是每行几 KB，故列表接口不带它
                # （decision_log.recent 刻意排除 flow_json），读整表走 flow_of。
                "flow": flows,
                "owner": check_owner,
            })
    except Exception:
        log_id = None

    # 边界样本自动记账（判据值擦阈 → 供校准提案；不自动改数）
    if log_id:
        try:
            add_boundary_samples(log_id, boundary_samples_of(flows, liunian_info))
        except Exception:
            pass

    # —— 改运链·天地气背景（2026-09-25 三链框架）：当年运气＋出生年运气＋出生地空间气。
    # 只作背景展示与健康起居调养依据，不进吉凶升降档（判运由占卜与命家岁运负责）。
    tian_di = None
    try:
        from yunqi import year_yunqi, buqi, current_bu
        from datetime import datetime as _dtt
        _now = _dtt.now()
        _dn = year_yunqi(_now.year)
        _dn["六步"] = buqi(_dn["ganzhi"], _now.year)
        _dn["当前步"] = current_bu(_now.year, _now.month, _now.day)
        tian_di = {
            "当年": _dn,
            "出生年": prof["baseline"].get("yunqi") if prof else None,
            "空间": prof["baseline"].get("dili") if prof else None,
        }
    except Exception:
        tian_di = None

    return {
        "X": rm.get("X"),
        "R": rm.get("R"),
        "R_alt": rm.get("R_alt"),
        "final_R": final_R,
        "R_reason": rm.get("R_reason", ""),
        "redirect_note": redirect_note,
        "state": rm.get("state", ""),
        "state_desc": rm.get("state_desc", ""),
        "notes": rm.get("notes", []),
        "month_wx": month_wx,
        "day_zhi": day_zhi,
        "yingqi_final": yingqi_final,     # 「按最终处方」栏应期（工程口径）
        "baseline": baseline_view,
        "adjudication": verdict,
        "liunian": liunian_info,
        "date_table": date_info,
        "tier": tier_info,
        "flow": flows,
        "claims": claims,
        "suggestions": suggestions,
        "yunqi": tian_di,                 # 改运链·天地气背景（展示层，不进判定）
        "log_id": log_id,
        "rules_version": RULES_VERSION,
        "weights_version": WEIGHTS_VERSION,
    }


class MingjuFeedbackRequest(BaseModel):
    log_id: int
    outcome: str    # 应验 / 未验 / 还没结果
    actual_date: str = ""   # 所问之事实际发生的日期（可选，ISO；应期分析靠它算偏差几天）


@app.post("/api/mingju/feedback")
async def mingju_feedback(req: MingjuFeedbackRequest, request: Request):
    """
    生产回流：用户补记"所问之事后来如何"（三选项，另可选填实际发生日期），
    把决策日志变成"裁决—结果"配对，供敏感度分析与反例捕捉。

    这是**最小的提问**：一个问题、三个按钮、一个可选日期。逐条断言标记改成可选项
    （在结果页与反馈页里折起来），因为实测 218 次校验只回来 1 条反馈（0.4%）——
    瓶颈在"要求太多"，不在"档位不够细"。
    """
    owner = require_owner(request)
    try:
        ok = set_feedback(req.log_id, req.outcome, owner, req.actual_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="日志不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 反馈语义层（claim 级）：把反馈下沉到"可独立判定的断言"，才谈得上调数值
# ---------------------------------------------------------------------------

class ClaimFeedbackRequest(BaseModel):
    log_id: int = 0
    claim_id: str = ""
    verdict: str                       # 应验/未验/反向/无法判定/未观察
    note: str = ""                     # 可选：补充说明（反例请写清"实际发生了什么"）
    receipt: str = ""                  # 断言回执码（长期反馈用：令牌没了也能凭它作答）


@app.get("/api/feedback/claims")
async def feedback_claims(log_id: int, request: Request):
    """某次校验的断言清单 + 已有反馈（逐条反馈界面数据源）——限本人。"""
    owner = owner_of(request)
    return {"log_id": log_id, "claims": claims_of(log_id, owner),
            "feedback": feedback_of(log_id, owner), "verdicts": list(FEEDBACK_VERDICTS)}


class ReceiptRequest(BaseModel):
    log_id: int
    claim_id: str


@app.post("/api/feedback/claim/receipt")
async def feedback_claim_receipt(req: ReceiptRequest, request: Request):
    """签发一条断言的**回执码**（窄凭证）——给「加入日历」与「复制链接」用。

    为什么需要它：claim 级反馈的价值在长验证窗口，而"设备即账户"的令牌活不到那天
    （iOS Safari 7 天不访问即清空 localStorage）。回执码是那种情况下唯一还能作答的凭证，
    所以它必须能被带走——前端把它拼进 .ics 事件，于是提醒落在用户自己的日历里。
    """
    owner = require_owner(request)
    rate_limit(request, "claim_receipt", limit=120, window_sec=60)
    out = issue_receipt(req.log_id, req.claim_id, owner)
    if not out:
        raise HTTPException(status_code=404, detail="断言不存在")
    return out


@app.get("/api/feedback/claim")
async def feedback_claim_by_receipt(receipt: str):
    """凭回执码读**这一条**断言（回执链接的落地页）。

    有意不返回问题原文、不返回该次校验的其它断言、不返回档案：回执码会被写进用户日历，
    而日历可能同步到第三方。返回范围窄到"只够让本人判断这条断言应验了没有"，
    这样即使链接泄露，泄露的也只是"有人问过一件事、当时给的建议是什么"。
    """
    hit = resolve_receipt(receipt)
    if not hit:
        raise HTTPException(status_code=404, detail="回执码无效或已作废")
    claims = claims_of(hit["log_id"], hit["owner"])
    claim = next((c for c in claims if c.get("id") == hit["claim_id"]), None)
    if not claim:
        raise HTTPException(status_code=404, detail="该断言已不存在")
    return {"claim": claim, "verdicts": list(FEEDBACK_VERDICTS),
            "feedback": feedback_of(hit["log_id"], hit["owner"]).get(hit["claim_id"], "")}


@app.post("/api/feedback/claim")
async def feedback_claim(req: ClaimFeedbackRequest, request: Request):
    """逐条断言反馈（同一 claim 后记覆盖前记）——**仅限自己的日志，或持有效回执码**。

    两条准入路径，窄的那条优先：
      · 带 `receipt` → 归属、log_id、claim_id **全部取自回执行**，客户端传的这两个字段
        一律忽略（否则"客户端字段决定改哪条"这条错路又回来了）；因此**不需要令牌**——
        这正是回执码存在的意义：令牌被系统清掉之后，日历里那条提醒仍然能作答。
      · 否则 → 照旧要求令牌属于自己的日志。

    负反馈（反向/未验）额外触发邮件通知——这是校准台账最需要的样本，
    不该等到登后台才发现。发信尽力而为，失败不影响反馈入库。
    """
    rate_limit(request, "feedback_claim", limit=60, window_sec=60)
    if req.receipt:
        hit = resolve_receipt(req.receipt)
        if not hit:
            raise HTTPException(status_code=404, detail="回执码无效或已作废")
        log_id, claim_id, owner = hit["log_id"], hit["claim_id"], hit["owner"]
    else:
        owner = require_owner(request)
        log_id, claim_id = req.log_id, req.claim_id
        if not get_log(log_id, owner):
            raise HTTPException(status_code=404, detail="日志不存在")
    try:
        save_verdict(log_id, claim_id, req.verdict, req.note, owner)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    mailed = False
    if req.verdict in ("反向", "未验") and mail_configured():
        try:
            ctext = next((c.get("text", "") for c in claims_of(log_id, owner)
                          if c.get("id") == claim_id), "")
            row = get_log(log_id, owner)
            res = await run_in_threadpool(claim_verdict_mail, row.get("question", ""), ctext,
                                          req.verdict, req.note, log_id)
            mailed = bool(res.get("ok"))
        except Exception:
            mailed = False
    return {"ok": True, "mailed": mailed}


@app.get("/api/feedback/recent")
async def feedback_recent(request: Request, limit: int = 5):
    """最近若干次校验（带 claim 与反馈状态）——反馈页的"待反馈"列表，仅自己的。

    这里用 require_owner 而非 owner_of：这个列表天然是"我的待办"，没有归属令牌时
    返回空列表会被误读成"我之前的记录都丢了"，直接 403 把原因说清更好。
    （正常情况下不会触发：前端令牌在会话内恒定，见 common/owner.ts。）
    """
    owner = require_owner(request)
    return {"items": recent_for_feedback(limit, owner),
            "verdicts": list(FEEDBACK_VERDICTS)}


class BetaNoteRequest(BaseModel):
    text: str
    title: str = ""                    # 留言标题（选填，整页反馈表单用）
    contact: str = ""                  # 可选联系方式（公测期便于回访）
    log_id: int = 0


@app.post("/api/feedback/note")
async def feedback_note(req: BetaNoteRequest, request: Request):
    """公测自由留言（可附标题与联系方式）。入库后尽力发一封邮件通知站长。

    限流：同 IP 每 10 分钟最多 5 条——防灌水与信息轰炸（站长明确担心过）。
    """
    rate_limit(request, "feedback_note", limit=5, window_sec=600)
    if not (req.text or "").strip():
        raise HTTPException(status_code=400, detail="留言内容为空")
    nid = add_beta_note(req.text.strip(), req.contact.strip(), req.log_id, req.title.strip())
    mailed = False
    if mail_configured():
        try:
            res = await run_in_threadpool(feedback_note_mail, req.text.strip(),
                                          req.contact.strip(), req.log_id, req.title.strip())
            mailed = bool(res.get("ok"))
        except Exception:
            mailed = False
    return {"ok": True, "id": nid, "mailed": mailed}


@app.get("/api/feedback/notes")
async def feedback_notes(request: Request, limit: int = 100):
    """留言收件箱（**站长**）：公测期看用户说了什么。

    必须站长令牌：留言里常有用户主动留的手机/微信/邮箱（现网 20 条里有 4 条），
    而留言表没有 owner 列、无法按人过滤——所以它只能是站长的收件箱，不能是公开列表。
    """
    require_admin(request)
    return {"notes": list_beta_notes(limit)}


@app.get("/api/feedback/calibration")
async def feedback_calibration():
    """校准台账：边界样本汇总 + 提案 + 护栏（**公开可查**，说明没有任何自动调参）。

    这个视图**有意保持公开**：它是"校准透明"这条产品承诺的兑现方式，藏起来等于撤回承诺。
    但只公开到"聚合与提案"这一层——**不带 log_ids**：行号是内部标识，对用户没有任何用处，
    留着只是把他人的样本编号漏出去。要查明细请用站长端点。
    """
    view = calibration_view()
    view["boundary"] = [{k: v for k, v in b.items() if k != "log_ids"}
                        for b in view.get("boundary") or []]
    return view


@app.post("/api/feedback/calibration/analyze")
async def feedback_calibration_analyze(request: Request):
    """按护栏生成"待批"校准提案（不自动改数；采纳需人工改 weights.yaml 并升版本）。

    **站长端点**：原先是公开的，于是任何人都能反复触发提案生成，用自己刷出来的脏样本
    把提案表塞满（每次调用都新增，无幂等）——那会让真正的校准在噪声里失去可读性。
    """
    require_admin(request)
    return {"proposals": analyze_calibration()}


class ProposalDecisionRequest(BaseModel):
    id: int
    status: str                        # 已批准 / 已拒绝 / 已生效
    decided_by: str = ""
    applied_version: str = ""


@app.post("/api/feedback/calibration/decide")
async def feedback_calibration_decide(req: ProposalDecisionRequest, request: Request):
    """批准/拒绝提案。

    **站长端点，且必须最严**：`decided_by` 由请求体传入，公开时任何人都能以任意署名
    把提案标成"已生效"——而"阈值只经人工批准、绝不自动改数"正是本产品的立身之本，
    一条可伪造的批准记录等于让这条承诺作废。
    """
    require_admin(request)
    try:
        ok = decide_proposal(req.id, req.status, req.decided_by, req.applied_version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="提案不存在")
    return {"ok": True}


class BaziLogRequest(BaseModel):
    question: str = ""              # 可选备注（八字排盘通常无问句）
    summary: dict = {}              # 排盘快照：四柱/阳历/农历/性别等


@app.post("/api/mingju/bazi/log")
async def mingju_bazi_log(req: BaziLogRequest, request: Request):
    """
    八字排盘留痕：此前排盘结果只在前端内存里，关页即失、无法事后复盘。
    落入同一张决策日志表（kind=bazi），"我的记录"页统一回看。

    归属与限额是这一轮补上的：原实现既没有令牌校验也没有限流，于是
      ① **功能自我否定**——行落成 owner=''，作者自己 `GET /api/mingju/logs` 读回来是空的，
         每次排盘的留痕静默消失（前端每次排盘都会调它，所以这是持续性丢数据，不是边缘情况）；
      ② **可被滥用**——任何人可无限次匿名写入这张共享表，且 `summary` 无大小限制。
    这个端点存的就是"这一笔属于谁"，没有归属就毫无意义，所以直接 require_owner
    （不像 `/api/mingju/check` 那样"无归属则不落账"——那边校验本身是能独立交付的计算结果）。
    """
    owner = require_owner(request)
    rate_limit(request, "bazi_log", limit=60, window_sec=60)
    try:
        summary = req.summary if isinstance(req.summary, dict) else {}
        snapshot = json.dumps(summary, ensure_ascii=False)
        if len(snapshot) > 20000:                      # 排盘快照本来只有几百字节
            summary = {"truncated": True, "note": "排盘快照过大，已省略"}
        log_id = append_check({
            "kind": "bazi", "question": req.question,
            "decision": "八字排盘",
            "extra": summary,
            "rules_version": RULES_VERSION, "weights_version": WEIGHTS_VERSION,
            "owner": owner, "profile_id": owner,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"记录失败: {str(e)}")
    return {"log_id": log_id}


@app.get("/api/mingju/logs")
async def mingju_logs(request: Request, limit: int = 50):
    """
    记录工作台：决策日志回看（含反馈状态），供"我的记录"页。
    这是标定反馈闭环的最后一公里——数据早已落库，缺的只是回看入口。
    """
    try:
        n = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        n = 50
    return {"logs": recent(n, require_owner(request))}


@app.get("/api/mingju/logs/flow")
async def mingju_log_flow(request: Request, id: int):
    """取某次校验当时的**整张流动五行判定表**（限本人）。

    **单独一个端点而不是塞进 `/api/mingju/logs`**：整表一张几 KB，而台账列表一次给 60 行——
    一起返回等于每开一次"我的记录"就多传几百 KB 的绝大多数人永远不会展开的数据。
    列表给"有哪些次"，这里给"那一次当时是什么样"。

    归属只认令牌；查不到与不属于自己返回同一个空结果（不做存在性探测）。
    """
    return {"flow": flow_of(int(id), require_owner(request))}


class MingjuQuoteRequest(BaseModel):
    keys: list[str] = []


@app.post("/api/mingju/quotes")
async def mingju_quotes(req: MingjuQuoteRequest):
    """
    典籍原文核对：按出处键（支持前缀归并）返回 books/ 库内原文摘录，
    供结果页出处行点击展开。未收录键返回 text=null（原文待录，不代拟）。
    """
    return {"quotes": lookup_many(req.keys)}


class MingjuImportRequest(BaseModel):
    data: dict    # 解密后的备份内容 {schema_version, profile, records?, ledger?}


# 备份文件里一切"等于令牌"的字段：导出时抹掉，导入时由服务端重新赋值为导入者。
#
# 为什么必须抹掉：本产品的**档案主键就是归属令牌**（`profiles.id` = owner），而记录与
# 台账的 `owner` / `profile_id` 也等于它。于是"照原样导出"会把一枚**仍然有效的凭证**
# 写进文件。文件一旦被解开（用户很可能选弱密码、又存进网盘/微信），拿到的人不只是看到
# 数据，而是**可以直接当成本人读写全部数据**——那就把 R12 的洞从备份这条路又开了一遍。
# 既然导入本来就不采信文件里的归属、一律改写为当前设备，这些字段在文件里**毫无用处**，
# 留着只有风险，所以干脆不写。
#
# 注意**不含 `id`**：records/check_log 的 `id` 是本地自增行号，不是凭证；而日志导入要靠
# 它做 `claim_feedback.log_id` 的重映射，抹掉会让断言反馈全部变成孤儿。档案的 `id` 才是
# 令牌，单独 pop 掉（见导出端点）。
_CREDENTIAL_FIELDS = ("owner", "profile_id")


def _scrub_credentials(rows: list) -> list:
    """把行里等于令牌的字段清空（保留键，便于人工查验结构）。"""
    out = []
    for r in rows:
        if isinstance(r, dict):
            r = dict(r)
            for k in _CREDENTIAL_FIELDS:
                if k in r:
                    r[k] = ""
        out.append(r)
    return out


@app.get("/api/mingju/export")
async def mingju_export(id: str, request: Request):
    """
    导出**全量备份**（返回明文 JSON；加密在前端完成——AES-GCM，密码不经过服务器）。

    为什么是全量：这个按钮叫「备份与搬家」，那就得真能搬家。原实现只导出命局档案，
    记录（起卦/排盘快照）与校验台账一个都不带——用户在新手机导入后会以为"数据都在"，
    而实际上他最舍不得的东西（攒了半年的卦例、写过应验判定的断言）全没了。
    名不副实的备份比没有备份更危险，因为它给出的是虚假的安全感。

    内容：profile + records（含回收站）+ check_log/claim_feedback（校验台账与断言反馈）。
    boundary_samples / 校准提案不带：那是跨用户的全局研究数据，不属于任何个人的备份。
    **凭证字段一律抹掉**（见 `_CREDENTIAL_FIELDS`）：备份只搬数据、不搬凭证。
    **令牌必须与 id 一致**，否则导出他人数据。
    """
    require_self(request, id)
    data = export_profile(id)
    if not data:
        raise HTTPException(status_code=404, detail="档案不存在")
    prof = data.get("profile")
    if isinstance(prof, dict):
        prof.pop("id", None)                    # = 令牌，不写进文件
    data["records"] = _scrub_credentials(rec_export_all(id))
    ledger = log_export_all(id)
    ledger["logs"] = _scrub_credentials(ledger.get("logs") or [])
    data["ledger"] = ledger
    return data


@app.post("/api/mingju/import")
async def mingju_import(req: MingjuImportRequest, request: Request):
    """
    导入备份（前端已解密的备份内容）。

    **归属一律取请求令牌，不采信备份文件里的 id/owner/profile_id**：备份文件里这些字段
    要么已被抹掉、要么是不可信的输入；两者都只能由服务端按请求令牌重新赋值。
    基线由出生信息现算（不信文件里的基线，既防篡改也兼容 schema 演进）。
    """
    owner = require_owner(request)
    rate_limit(request, "profile_import", limit=10, window_sec=60)
    try:
        prof = import_profile(req.data, owner)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")
    # 记录与台账是"顺带恢复"的部分：各自 try 住，失败也不让整次导入报错——
    # 档案（用户最核心的输入）已经落库了，这时候抛 500 会让人以为什么都没导入，
    # 而实际上一半已经生效（这正是原来那个"500 但档案已写入"的成因）。
    # 计数如实返回，前端据此告诉用户"哪部分恢复了、哪部分没有"。
    rec_n = led_n = 0
    try:
        rec_n = rec_import_all(req.data.get("records"), owner)
    except Exception:
        rec_n = 0
    try:
        led_n = log_import_all(req.data.get("ledger"), owner)
    except Exception:
        led_n = {"logs": 0, "feedback": 0}
    return {"profile": prof, "records": rec_n, "ledger": led_n}


# ============================================================
# 术语知识地图（新库 backend/terminology.db）
# 数据来源：4 份 HTML 知识地图（梅花 3 份合并、六爻 1 份），
# 由 tools/extract_term_maps.mjs + tools/build_terms_db.py 生成；只读展示。
# ============================================================
@app.get("/api/meta/quotes")
async def meta_quotes():
    """典籍索引规模（首页 hero 统计用）：原文索引条数 + 覆盖书目数。

    存在的理由：首页原先硬编码"5 部典籍规则"，与 book_quotes 实际规模不符——
    "每句话都要有作用"的前提是它得是真的，故改为实时统计，不再手写数字。
    书名归一：出处串里的别称/篇目（增广校正梅花易数、元理赋、通行口诀）折算到正典书名，
    避免把同一部书数两次、或把篇目当成一部书。
    """
    from book_quotes import QUOTES
    # (出处串中的字样 → 正典书名)
    canon_map = [
        ("滴天髓", "滴天髓"), ("渊海子平", "渊海子平"), ("元理赋", "渊海子平"),
        ("子平真诠", "子平真诠"), ("穷通宝鉴", "穷通宝鉴"), ("三命通会", "三命通会"),
        ("增删卜易", "增删卜易"), ("卜筮正宗", "卜筮正宗"), ("梅花易数", "梅花易数"),
        ("四时旺相休囚死", "梅花易数"), ("周易", "周易"), ("黄帝内经", "黄帝内经"),
        ("五行大义", "五行大义"), ("礼记", "礼记"), ("协纪辨方书", "协纪辨方书"),
        ("太玄经", "太玄经"),
    ]
    books = set()
    for q in QUOTES.values():
        s = q.get("book") or ""
        for needle, canon in canon_map:
            if needle in s:
                books.add(canon)
    return {"quote_keys": len(QUOTES), "book_count": len(books),
            "books": sorted(books)}


@app.get("/api/terms/meta")
async def terms_meta():
    """术语库总览：体系、分类与词条数、来源说明"""
    return term_meta()


@app.get("/api/terms")
async def terms_list(system: str = "meihua", category: str = "", q: str = "", limit: int = 0):
    """词条列表（按体系/分类/关键词），limit=0 表示不限"""
    return {"terms": term_list(system, category, q, limit)}


@app.get("/api/terms/detail")
async def terms_detail(id: int):
    """单词条详情 + 关联术语（关联已解析到词条，可点击跳转）"""
    item = term_get(int(id))
    if not item:
        raise HTTPException(status_code=404, detail="词条不存在")
    return item


@app.get("/api/terms/search")
async def terms_search(q: str, system: str = "", limit: int = 30):
    """跨体系搜索（名称/别名/释义）"""
    return {"terms": term_search(q, system, limit)}


# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
