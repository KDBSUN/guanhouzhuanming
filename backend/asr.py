# -*- coding: utf-8 -*-
"""
语音转文字（ASR）客户端：供应商无关，换供应商只改 .env
========================================================
用途：梅花页的语音输入。录音在浏览器本地完成（MediaRecorder），识别交到服务端。

**为什么必须放服务端**：Chrome 自带的 Web Speech API（webkitSpeechRecognition）把音频
送到 Google 的服务器，中国大陆基本连不通——表现是"按了没反应"或直接 network 错误，
而不是一句看得懂的报错。录音本身是纯本地能力，缺的只是"国内可达的识别后端"，
所以只把识别这一环挪到服务端。

**为什么写成"配置驱动"**：供应商还没定，将来换一家（百炼／硅基流动／自建 whisper.cpp）
必须只改 .env、不改代码。故这里只认 OpenAI 兼容的 `/audio/transcriptions` 形状，
把各家差异收敛到 ASR_BASE_URL 与 ASR_MODEL 两个变量上。默认值给阿里云百炼
（DashScope 兼容模式）：国内可直连，且新用户有免费额度（10 小时 / 90 天），
站长不必先充值就能把这条路验证通。

两条硬规矩：
  · 密钥只从环境变量读，绝不写进代码；**任何返回串（含错误串）里都不许出现密钥**——
    错误串会原样透到前端。见 _safe()。
  · 失败**不抛异常**，一律返回 {"ok": False, "error": "<中文、可操作的一句话>"}，
    由调用方（main.py 的 /api/asr/transcribe）决定 HTTP 状态码。与 mailer.py 同取向。
"""
import base64
import os
import re
import time
import wave
from io import BytesIO
from urllib.parse import urlparse

# 阿里云百炼（DashScope）OpenAI 兼容模式地址。选它作默认的理由：国内直连不用绕，
# 且新用户有 10 小时 / 90 天的免费额度——语音输入是"锦上添花"的功能，
# 不该让站长为了试用先充值。换别家只需改 ASR_BASE_URL / ASR_MODEL。
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3-asr-flash"
DEFAULT_LANGUAGE = "zh"
DEFAULT_TIMEOUT = 30.0

# 单段音频 5 MB 上限。60 秒语音在常见码率下只有几百 KB，5 MB 已远超"一次正常提问"的量；
# 再大既拖慢上传，也可能撞上供应商自己的单请求上限（且识别按秒计费，越大越贵）。
MAX_AUDIO_BYTES = 5 * 1024 * 1024
MAX_AUDIO_SECONDS = 60
# 上传请求体上限 = 音频上限 + multipart 包装余量（分隔线与部件头通常几百字节，留 64 KB 足够）。
# main.py 的 limit_body_size 中间件按这个值给本端点放行：全局上限是 256 KiB，
# 那段限制是给"把请求原样入库"的端点用的，套在录音上会让 60 秒的 opus 录音（约 360 KB）
# 在进业务逻辑之前就被 413 掉。
MAX_REQUEST_BYTES = MAX_AUDIO_BYTES + 64 * 1024

# 抹掉"看起来像密钥"的串：防止把本次密钥之外的其它密钥（中转网关有时会回显自己那把）
# 顺着错误信息漏到前端。
_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_\-]{6,}")


def _env_float(name: str, default: float) -> float:
    """读一个数字型环境变量；填了非数字（如 "30s"）不该让功能起不来，退回默认值。"""
    try:
        return float(os.getenv(name) or default)
    except (TypeError, ValueError):
        return default


def _cfg() -> dict:
    """每次调用时读环境变量，而不是 import 时读一次。

    与 mailer.py 的 _cfg() 保持一致：好处是测试可以直接改 os.environ 而不用重载模块。
    注意 .env 仍只在 main.py 导入时被 dotenv 读一次，所以**改了 .env 要重启后端**才生效。
    """
    base_url = (os.getenv("ASR_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    # rstrip("/")：.env 里手滑写成 ".../v1/" 时，拼出来会变成 "//audio/transcriptions"，
    # 有的网关直接 404。这里统一收口，免得错误表现成"接口不存在"让人查半天。
    return {
        "base_url": base_url,
        "api_key": (os.getenv("ASR_API_KEY") or "").strip(),
        "model": (os.getenv("ASR_MODEL") or DEFAULT_MODEL).strip(),
        "language": (os.getenv("ASR_LANGUAGE") or "").strip(),
        "timeout": _env_float("ASR_TIMEOUT", DEFAULT_TIMEOUT),
        "provider": _provider_label(base_url),
        # 请求形状：默认按地址推断。指向 aliyuncs/dashscope 就走原生同步接口，
        # 其余（硅基流动／OpenAI／自建）走 OpenAI 兼容的 multipart。
        # 也可用 ASR_PROVIDER 显式覆盖（例如百炼的兼容端点确实可用时）。
        "provider_kind": _provider_kind(
            (os.getenv("ASR_PROVIDER") or "").strip(), base_url),
    }


def _provider_kind(explicit: str, base_url: str) -> str:
    if explicit in ("dashscope", "openai"):
        return explicit
    host = (urlparse(base_url).netloc or "").lower()
    return "dashscope" if ("dashscope" in host or "aliyuncs" in host) else "openai"


def _net_fail(fail, exc: Exception, host: str) -> dict:
    """把网络异常翻成能照做的话——连不上和密钥错是两回事，不能都说"识别失败"。"""
    return fail("连不上识别服务（%s）：本机到 %s 的网络或 DNS 不通——"
                "检查网络、代理，或改 ASR_BASE_URL 换一家供应商"
                % (type(exc).__name__, host))


def _finish(fail, resp, cfg: dict, started: float, url: str) -> dict:
    """统一收尾：状态码 → 人话，再从各种响应形状里抠出文本。

    文本形状的宽容是有原因的：同一条链路上出现过三种外壳——
    `{text}`（OpenAI 兼容）、`{output:{choices:[{message:{content:[{text}]}}]}}`（百炼原生）、
    `{results:[{text}]}`（别家）。只认一种的话，换个供应商就"识别成功但没有文字"。
    """
    if resp.status_code == 401 or resp.status_code == 403:
        return fail("识别服务拒绝了这个密钥（HTTP %d）：检查 ASR_API_KEY 是否填错、"
                    "是否开通了对应模型（百炼需在控制台开通）" % resp.status_code)
    if resp.status_code == 429:
        return fail("识别服务限流（HTTP 429）：稍后再试，或检查账户余额/并发配额")
    if resp.status_code == 404:
        return fail("识别接口不存在（HTTP 404）：地址 %s 上找不到该路径。"
                    "百炼请留空 ASR_BASE_URL 用默认值（走原生同步接口）；"
                    "换别家请同时改 ASR_BASE_URL 与 ASR_MODEL" % url)
    if resp.status_code >= 500:
        return fail("识别服务暂时故障（HTTP %d）：稍后再试" % resp.status_code)
    if resp.status_code != 200:
        return fail("识别失败（HTTP %d）：%s" % (resp.status_code, _safe(resp.text, cfg["api_key"], 200)))

    try:
        payload = resp.json()
    except Exception:
        return fail("识别服务返回了非 JSON 内容（HTTP 200）：%s" % _safe(resp.text, cfg["api_key"], 120))

    text = _extract_text(payload)
    if not text:
        # 200 但没文字：常见于音频里没有人声。这不算故障，如实说。
        return {"ok": True, "text": "", "provider": cfg["provider"], "model": cfg["model"],
                "ms": int((time.monotonic() - started) * 1000),
                "error": "识别成功但没有文字（可能没说话或只有噪声）"}
    return {"ok": True, "text": text, "provider": cfg["provider"], "model": cfg["model"],
            "ms": int((time.monotonic() - started) * 1000), "error": ""}


def _provider_label(base_url: str) -> str:
    """给一个人类可读的供应商标签，用于 status() 与排障。

    刻意**只从 base_url 推断**：排障的人需要一眼看出"这份配置指向谁"，
    而它又不能是密钥或密钥的一部分。
    """
    host = (urlparse(base_url).netloc or "").lower()
    for needle, label in (("dashscope", "aliyun-dashscope"), ("aliyuncs", "aliyun"),
                          ("siliconflow", "siliconflow"), ("openai.com", "openai"),
                          ("volces", "volcengine"), ("localhost", "self-hosted"),
                          ("127.0.0.1", "self-hosted")):
        if needle in host:
            return label
    return host or "unknown"


def configured() -> bool:
    """是否可用：地址/模型都有默认值，只有密钥必须由站长填，故"有密钥=已配置"。"""
    return bool(_cfg()["api_key"])


def status() -> dict:
    """给前端判断"用服务端识别还是回退浏览器识别"。**绝不返回密钥。**

    只回报"能不能用"和"指向谁"，不含任何可用作凭证的字段——这个端点是公开的
    （前端要在录音前就知道该走哪条路），公开信息里混进密钥就等于把密钥公开。
    """
    cfg = _cfg()
    return {
        "configured": bool(cfg["api_key"]),
        "provider": cfg["provider"],
        "base_url": cfg["base_url"],
        "model": cfg["model"],
    }


def _safe(text, secret: str = "", limit: int = 160) -> str:
    """把外部文本（异常串／供应商返回体）收拾成一句能放进错误信息的话。

    为什么非做不可：错误信息会原样透到前端，而这些文本来自**外部**——供应商在 401 的
    body 里回显收到的密钥是常见行为，httpx 的异常串里也可能带上完整请求 URL。
    故：折叠空白 → 抹掉本次密钥 → 抹掉 sk- 形状的串 → 截断
    （不把一整页 HTML 报错塞给前端）。
    """
    s = " ".join(str(text or "").split())
    if secret:
        s = s.replace(secret, "***")
    s = _SECRET_RE.sub("sk-***", s)
    return s[:limit]


def _wav_seconds(audio: bytes):
    """WAV 的真实时长（秒）；非 WAV 或读不出来则返回 None。

    为什么只认 WAV：webm/ogg/mp4 的真实时长要解容器，标准库做不到，得引入 ffmpeg 或
    音频库——与"不加重依赖"直接冲突。故时长这一关做成"能精确就精确，不能精确就靠字节上限
    兜底"：WAV 在浏览器里少见（MediaRecorder 出的是 webm/ogg），所以真正拦住超长录音的
    是 MAX_AUDIO_BYTES；这一支只是顺手把 WAV（体积大、最容易超）量准。
    """
    if len(audio) < 44 or audio[:4] != b"RIFF":
        return None
    try:
        with wave.open(BytesIO(audio), "rb") as w:
            rate = w.getframerate() or 0
            if rate <= 0:
                return None
            return w.getnframes() / float(rate)
    except (wave.Error, EOFError, OSError):
        return None


def _extract_text(payload) -> str:
    """从各家可能不同的返回形状里取识别文本。

    为什么容错：换供应商只改 .env 是本模块的设计目标，但"OpenAI 兼容"各家只兼容到主路径——
    同一条链路上实测出现过三种外壳：
      · 百炼**原生同步**（我们默认走的那条）：
        {"output": {"choices": [{"message": {"content": [{"text": "..."}]}}]}}
      · OpenAI 兼容：{"text": "..."}
      · 自建/中转（whisper.cpp server、one-api、fastwhisper）：{"results": [{"text": "..."}]}
    只认一种的话，换个供应商就变成"识别通了但没有文字"，而错误信息会把矛头指向麦克风，
    越查越远。故按常见形状依次取，取到就用。
    """
    if isinstance(payload, dict):
        candidates = [payload.get("text")]
        output = payload.get("output")
        if isinstance(output, dict):
            candidates.append(output.get("text"))
            # 百炼原生：output.choices[].message.content[].text（真实返回形状）
            for choice in (output.get("choices") or []):
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message") or {}
                content = message.get("content")
                if isinstance(content, str):
                    candidates.append(content)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            candidates.append(part.get("text"))
        for choice in (payload.get("choices") or []):        # OpenAI chat 风格的外壳
            if isinstance(choice, dict):
                message = choice.get("message") or {}
                if isinstance(message.get("content"), str):
                    candidates.append(message["content"])
        results = payload.get("results")
        if isinstance(results, list) and results and isinstance(results[0], dict):
            candidates.append(results[0].get("text"))
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def transcribe(audio: bytes, filename: str, content_type: str) -> dict:
    """把一段音频发给识别服务，返回文本。**不抛异常**，失败信息在 error 里。

    **两种请求形状**（由 ASR_PROVIDER 选，默认 dashscope）：
      · `dashscope`：阿里云百炼**原生同步**接口
        `POST {host}/api/v1/services/aigc/multimodal-generation/generation`，
        音频以 base64 data-URL 放在 messages 的 content 里，**一次请求直接拿结果**。
        这是实测可用的那条（见下）。
      · `openai`：OpenAI 兼容 `POST {base}/audio/transcriptions`，multipart 直传。
        留给换别家（硅基流动／OpenAI／自建）用。

    **为什么默认不是"OpenAI 兼容端点"**：最初按兼容形状接（`/audio/transcriptions`），
    实测在 `dashscope.aliyuncs.com` 上**该路径不存在**——换任何模型名都是 404 且响应体为空
    （这是网关级 404，不是"模型不存在"）。而原生 multimodal-generation 端点对
    `qwen3-asr-flash` 返回 200 并给出文本。教训：**"兼容端点"这四个字不能当验证用**。

    这里是**同步**实现（httpx.Client）：调用方是 FastAPI，用 run_in_threadpool 丢进
    线程池即可（见 main.py）——一次性请求不值得为它维护 async 客户端的生命周期，
    而且同步函数在测试里最好替换。
    """
    cfg = _cfg()
    started = time.monotonic()

    def fail(msg: str) -> dict:
        return {"ok": False, "text": "", "provider": cfg["provider"], "model": cfg["model"],
                "ms": int((time.monotonic() - started) * 1000), "error": msg}

    # ---- 前置检查（不花网络往返就能说清的问题，先说完） ----
    if not cfg["api_key"]:
        return fail("未配置 ASR_API_KEY：请在 backend/.env 里填入语音识别服务的密钥后重启后端")
    if not audio:
        return fail("收到的音频为空：请重新录制后再试（浏览器可能没拿到麦克风权限）")
    if len(audio) > MAX_AUDIO_BYTES:
        return fail("录音过大（%.1f MB，上限 %.0f MB／约 %d 秒语音）：请缩短录音后重试"
                    % (len(audio) / 1048576.0, MAX_AUDIO_BYTES / 1048576.0, MAX_AUDIO_SECONDS))
    seconds = _wav_seconds(audio)
    if seconds is not None and seconds > MAX_AUDIO_SECONDS:
        return fail("录音过长（约 %.0f 秒，上限 %d 秒）：请缩短录音后重试" % (seconds, MAX_AUDIO_SECONDS))

    try:
        import httpx        # 延迟导入：与 main.py 既有写法一致，缺这个包也不该让 main 起不来
    except ImportError:
        return fail("服务端缺少 httpx 依赖：请在后端目录执行 pip install httpx 后重启")

    headers = {"Authorization": "Bearer %s" % cfg["api_key"]}

    if cfg["provider_kind"] == "dashscope":
        # 只取 host：ASR_BASE_URL 里若带 /compatible-mode/v1 之类的路径，对原生接口无意义，
        # 硬拼会把路径叠成 .../compatible-mode/v1/api/v1/... 而 404。
        host = "{0.scheme}://{0.netloc}".format(urlparse(cfg["base_url"]))
        url = host + "/api/v1/services/aigc/multimodal-generation/generation"
        fmt = (content_type or "audio/wav").split("/")[-1].split(";")[0] or "wav"
        payload = {
            "model": cfg["model"],
            "input": {"messages": [{"role": "user", "content": [
                {"audio": "data:audio/%s;base64,%s"
                          % (fmt, base64.b64encode(audio).decode())}]}]},
            "parameters": {"format": fmt},
        }
        if cfg["language"]:
            payload["parameters"]["language"] = cfg["language"]
        try:
            with httpx.Client(timeout=cfg["timeout"]) as client:
                resp = client.post(url, headers={**headers, "Content-Type": "application/json"},
                                   json=payload)
        except httpx.TimeoutException:
            return fail("识别超时（%d 秒）：录音较长或网络较慢，可缩短录音，"
                        "或在 .env 里调大 ASR_TIMEOUT 后重启后端" % int(cfg["timeout"]))
        except Exception as e:                      # noqa: BLE001 — 任何网络异常都要变成人话
            return _net_fail(fail, e, host)
        return _finish(fail, resp, cfg, started, url)

    # ---- OpenAI 兼容形状（换别家用）----
    url = "%s/audio/transcriptions" % cfg["base_url"]
    # 不手写 Content-Type：传 files= 时 httpx 会自己生成带 boundary 的 multipart 头，
    # 手写会把 boundary 写丢，供应商只会回一个语义模糊的 400。
    files = {"file": (filename or "audio.webm", audio,
                      content_type or "application/octet-stream")}
    data = {"model": cfg["model"]}
    if cfg["language"]:
        data["language"] = cfg["language"]
    try:
        with httpx.Client(timeout=cfg["timeout"]) as client:
            resp = client.post(url, headers=headers, data=data, files=files)
    except httpx.TimeoutException:
        return fail("识别超时（%d 秒）：录音较长或网络较慢，可缩短录音，"
                    "或在 .env 里调大 ASR_TIMEOUT 后重启后端" % int(cfg["timeout"]))
    except httpx.TransportError as e:
        return _net_fail(fail, e, cfg["base_url"])
    except Exception as e:                              # 兜底：绝不把异常抛给调用方
        return fail("识别请求发送失败（%s）：%s" % (type(e).__name__, _safe(e, cfg["api_key"])))

    return _finish(fail, resp, cfg, started, url)
