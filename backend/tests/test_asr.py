# -*- coding: utf-8 -*-
"""
语音转文字回归（asr.py + /api/asr/* 端点）
==========================================
**全部离线**：所有 HTTP 都被替身拦下（monkeypatch httpx.Client），绝不真发请求、绝不真用密钥。

为什么单独立一组测试：这条链上有三件"错了也不容易发现"的事——
  1. **密钥外泄**：错误串会原样透到前端，而"供应商在 401 的 body 里回显收到的密钥"是常见
     行为，故每个错误分支都要断言返回值里没有密钥；
  2. **请求形状**：POST 到 {base}/audio/transcriptions、multipart/form-data、字段 file +
     model（+ language）。手写 Content-Type 会把 boundary 写丢、改用 json= 发就成了另一种协议，
     这类错误在本机只表现为"供应商回 400"，很难归因；
  3. **端点守卫**：/status 公开、/transcribe 没令牌 403、没配密钥 503——前端就靠这三条决定
     "用服务端识别还是回退浏览器识别"，错一个就退化回大陆不可用的那条老路。
"""
import json
import wave
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient

import asr
import main

FAKE_KEY = "sk-fake-asr-key-0123456789abcdef"      # 假密钥：真请求一律被替身拦下
BASE = "https://example.invalid/v1"
AUDIO = b"\x1aE\xdf\xa3" + b"fake-webm-audio-bytes" * 8    # 内容不被解析（WAV 除外），非空即可
TOKEN = {"X-Owner-Token": "tok-asr-test"}


# ---------- 替身：httpx.Client ----------

class _Resp:
    """最小化的 httpx.Response 替身：只要 status_code / text / json()。"""

    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        if text is not None:
            self.text = text
        elif payload is not None:
            self.text = json.dumps(payload, ensure_ascii=False)
        else:
            self.text = ""

    def json(self):
        if self._payload is None:      # 模拟"返回体不是 JSON"（如网关的 HTML 报错页）
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


class _Recorder:
    """记录客户端怎么被用的，并按预设返回响应或抛异常。"""

    def __init__(self):
        self.calls = []
        self.response = _Resp(200, {"text": "你好"})
        self.exception = None
        self.client_kwargs = None

    def make_client(self):
        rec = self

        class _Client:
            def __init__(self, *args, **kwargs):
                rec.client_kwargs = kwargs

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def post(self, url, headers=None, data=None, files=None, **kwargs):
                # 记录 json=（百炼原生同步形状用它），并与 data/extra 分开存：
                # 两种形状的差别正是本组测试要断言的东西，混在一个字段里就断言不清了。
                rec.calls.append({"url": url, "headers": headers or {}, "data": data,
                                  "files": files, "json": kwargs.get("json"),
                                  "extra": kwargs})
                if rec.exception is not None:
                    raise rec.exception
                return rec.response

        return _Client


@pytest.fixture()
def http(monkeypatch):
    """换掉 httpx.Client。

    asr.transcribe 里是**延迟** import httpx，拿到的就是这个模块对象，所以改
    httpx.Client 即可拦下全部真实请求（不用 patch asr 内部的名字）。
    """
    rec = _Recorder()
    monkeypatch.setattr(httpx, "Client", rec.make_client())
    return rec


@pytest.fixture()
def keyed(monkeypatch):
    """一份"已配好"的配置：密钥是假的，地址故意带结尾斜杠（顺带验证会被收口）。"""
    monkeypatch.setenv("ASR_API_KEY", FAKE_KEY)
    monkeypatch.setenv("ASR_BASE_URL", BASE + "/")
    monkeypatch.setenv("ASR_MODEL", "test-asr-model")
    monkeypatch.setenv("ASR_LANGUAGE", "zh")
    # **必须显式钉住请求形状**：`_provider_kind` 会按域名推断（aliyuncs→dashscope），
    # 而站长真在 .env 里写了 ASR_PROVIDER=dashscope 时，dotenv 会把它带进 os.environ，
    # 于是"OpenAI 兼容形状"这组测试会静默跑到另一条分支上去（实测就发生了）。
    # 测试要断言的是形状，就该把形状钉死，不该让它随站长的 .env 变化。
    monkeypatch.setenv("ASR_PROVIDER", "openai")
    monkeypatch.delenv("ASR_TIMEOUT", raising=False)
    return FAKE_KEY


@pytest.fixture()
def client(monkeypatch):
    """TestClient。默认把密钥清掉，与"站长还没填 ASR_API_KEY"的出厂状态一致。

    用 delenv 而不是"假设 .env 里是空的"：站长填上真密钥之后，这组测试仍要照样通过。
    """
    monkeypatch.delenv("ASR_API_KEY", raising=False)
    monkeypatch.delenv("ASR_BASE_URL", raising=False)
    monkeypatch.delenv("ASR_MODEL", raising=False)
    monkeypatch.delenv("ASR_LANGUAGE", raising=False)
    return TestClient(main.app)


def _wav(seconds: float, rate: int = 8000) -> bytes:
    """造一段静音 WAV（标准库即可，不需要音频库）：验证"时长"那一关。"""
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(b"\x80" * int(rate * seconds))
    return buf.getvalue()


# ---------- 1. 配置与 status：绝不能带出密钥 ----------

def test_configured_false_without_key(monkeypatch):
    monkeypatch.delenv("ASR_API_KEY", raising=False)
    assert asr.configured() is False
    assert asr.status()["configured"] is False


def test_status_never_exposes_key(keyed):
    st = asr.status()
    assert st["configured"] is True
    assert set(st) == {"configured", "provider", "base_url", "model"}
    assert FAKE_KEY not in json.dumps(st, ensure_ascii=False)


def test_defaults_point_at_aliyun_dashscope(monkeypatch):
    """默认值就是给大陆直连用的（百炼兼容模式）：不配任何变量也能看出指向哪家。"""
    for name in ("ASR_API_KEY", "ASR_BASE_URL", "ASR_MODEL", "ASR_LANGUAGE"):
        monkeypatch.delenv(name, raising=False)
    st = asr.status()
    assert st["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert st["provider"] == "aliyun-dashscope"
    assert st["model"] == "qwen3-asr-flash"


# ---------- 2. 请求形状：multipart/form-data、字段 file + model ----------

def test_transcribe_builds_multipart_request(keyed, http):
    http.response = _Resp(200, {"text": "  今天天气不错  "})
    out = asr.transcribe(AUDIO, "rec.webm", "audio/webm")

    assert out["ok"] is True, out
    assert out["text"] == "今天天气不错"           # 两端空白剔除
    assert out["model"] == "test-asr-model"
    assert out["provider"] == "example.invalid"    # 标签取自 base_url 的域名
    assert isinstance(out["ms"], int) and out["ms"] >= 0
    assert out["error"] == ""

    assert len(http.calls) == 1
    call = http.calls[0]
    # 结尾斜杠被收口，不会拼成 ".../v1//audio/transcriptions"
    assert call["url"] == BASE + "/audio/transcriptions"
    assert call["headers"]["Authorization"] == "Bearer " + FAKE_KEY
    assert call["data"] == {"model": "test-asr-model", "language": "zh"}
    assert call["files"]["file"] == ("rec.webm", AUDIO, "audio/webm")
    assert "json" not in call["extra"] and "content" not in call["extra"]   # 不是 JSON 请求

    # 把这次调用在内存里真编一遍 multipart 请求体：字段名、boundary、音频字节都要在里面
    # （只看 kwargs 是证不出"真的发了 multipart"的）。
    req = httpx.Request("POST", call["url"], headers=call["headers"],
                        data=call["data"], files=call["files"])
    assert req.headers["content-type"].startswith("multipart/form-data; boundary=")
    body = req.read()
    assert b'name="file"' in body and b'filename="rec.webm"' in body
    assert b'name="model"' in body and b'name="language"' in body
    assert AUDIO in body
    assert b"Content-Type: audio/webm" in body          # 音频的 MIME 也要带给供应商


def test_language_omitted_when_empty(keyed, http, monkeypatch):
    """ASR_LANGUAGE 留空就不带 language 字段：有的供应商对未知语言值直接 400。"""
    monkeypatch.setenv("ASR_LANGUAGE", "")
    asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert http.calls[0]["data"] == {"model": "test-asr-model"}


def test_timeout_env_is_passed_to_client(keyed, http, monkeypatch):
    asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert http.client_kwargs["timeout"] == 30.0        # 默认 30 秒
    monkeypatch.setenv("ASR_TIMEOUT", "7")
    asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert http.client_kwargs["timeout"] == 7.0


@pytest.mark.parametrize("payload,expect", [
    ({"text": "标准形状"}, "标准形状"),                                  # OpenAI 兼容模式
    ({"output": {"text": "输出形状"}}, "输出形状"),                       # DashScope 原生模式
    ({"results": [{"text": "结果数组形状"}]}, "结果数组形状"),             # whisper.cpp/中转
    ({"text": "", "results": [{"text": "回退"}]}, "回退"),               # 主键为空则继续找
])
def test_tolerant_response_shapes(keyed, http, payload, expect):
    """兼容模式之外还有原生模式与自建实现，形状不同但都得认（换供应商只改 .env 的前提）。"""
    http.response = _Resp(200, payload)
    out = asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert out["ok"] is True, out
    assert out["text"] == expect


# ---------- 3. 错误映射：中文、可操作、绝不带密钥 ----------

def test_401_maps_to_actionable_chinese(keyed, http):
    http.response = _Resp(401, text='{"error":{"message":"Invalid API-key: %s"}}' % FAKE_KEY)
    out = asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert out["ok"] is False
    assert "密钥" in out["error"] and "开通" in out["error"]
    assert FAKE_KEY not in out["error"]


def test_403_also_treated_as_key_problem(keyed, http):
    http.response = _Resp(403, text="forbidden")
    out = asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert out["ok"] is False and "密钥" in out["error"] and FAKE_KEY not in out["error"]


def test_429_maps_to_rate_limit_message(keyed, http):
    http.response = _Resp(429, text="too many requests")
    out = asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert out["ok"] is False
    assert "429" in out["error"] and "限流" in out["error"]


def test_5xx_maps_to_provider_down(keyed, http):
    http.response = _Resp(503, text="upstream busy")
    out = asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert out["ok"] is False and "503" in out["error"] and "故障" in out["error"]


@pytest.mark.parametrize("exc,needle", [
    (httpx.ReadTimeout("timed out"), "超时"),
    (httpx.ConnectTimeout("connect timed out"), "超时"),
    (httpx.ConnectError("[Errno 11001] getaddrinfo failed"), "连不上"),
    (httpx.ProxyError("proxy refused"), "连不上"),
])
def test_network_errors_are_distinguished(keyed, http, exc, needle):
    """超时与"根本连不上"必须分开说：前者让用户缩录音，后者是机器到那个域名不通。

    连不上的提示必须点明"这台机器到该地址不通"，否则站长会去查密钥、查模型名，越查越远。
    """
    http.exception = exc
    out = asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert out["ok"] is False and needle in out["error"]
    if needle == "连不上":
        assert "DNS" in out["error"] and BASE in out["error"]
    else:
        assert "ASR_TIMEOUT" in out["error"]           # 给出可操作的出路：调大超时
    assert FAKE_KEY not in out["error"]


def test_key_echoed_in_error_body_is_redacted(keyed, http):
    """供应商把收到的密钥回显在 400 的 body 里时，错误串必须先抹掉再回前端。

    这是本模块最要紧的一条：错误串会原样渲染给用户，漏一次就等于把密钥公开一次。
    """
    http.response = _Resp(400, text='{"error":"bad request, Authorization: Bearer %s"}' % FAKE_KEY)
    out = asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert out["ok"] is False
    assert "400" in out["error"]
    assert FAKE_KEY not in out["error"]
    assert "***" in out["error"]                       # 确实是被抹掉，而不是恰好没带进来


def test_non_json_body_is_reported(keyed, http):
    http.response = _Resp(200, text="<html><body>502 Bad Gateway</body></html>")
    out = asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert out["ok"] is False and "JSON" in out["error"] and FAKE_KEY not in out["error"]


def test_empty_transcript_is_not_a_failure(keyed, http):
    """**识别通了但没文字 ≠ 识别失败**。

    契约有意改过：早期把"空文本"当作失败（ok=False），但那是把两件事混为一谈——
    服务商 200 且链路完好，只是这段音频里没有人声（用户没开口、或全是噪声）。
    判成失败会让前端弹"识别失败"，而正确的动作是提示"没听清，再说一次"并让用户重试。
    故现在返回 ok=True + 一句说明，由前端决定措辞。
    """
    http.response = _Resp(200, {"text": "   "})
    out = asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert out["ok"] is True and out["text"] == ""
    assert "没有文字" in out["error"]


def test_dashscope_shape_is_used_for_aliyun(monkeypatch, http):
    """**默认走百炼原生同步形状**——这是实测可用那条。

    为什么单列一条测试：最初按"OpenAI 兼容端点"接（POST {base}/audio/transcriptions），
    在 dashscope.aliyuncs.com 上该路径**不存在**（换任何模型名都是空体 404，网关级）。
    真正可用的是原生 multimodal-generation：音频以 base64 data-URL 放进 messages.content。
    这条形状一旦被改回去，用户那边表现为"识别接口不存在"，很难归因，所以钉死。
    """
    monkeypatch.setenv("ASR_API_KEY", FAKE_KEY)
    monkeypatch.setenv("ASR_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("ASR_MODEL", "qwen3-asr-flash")
    monkeypatch.delenv("ASR_PROVIDER", raising=False)     # 让代码按域名自行推断
    http.response = _Resp(200, {"output": {"choices": [
        {"message": {"content": [{"text": "今天天气不错"}]}}]}})
    out = asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert out["ok"] is True and out["text"] == "今天天气不错"
    call = http.calls[0]
    # 只取 host：base_url 里带的 /compatible-mode/v1 不能叠进原生路径
    assert call["url"] == ("https://dashscope.aliyuncs.com"
                           "/api/v1/services/aigc/multimodal-generation/generation")
    assert call["json"]["model"] == "qwen3-asr-flash"
    audio_part = call["json"]["input"]["messages"][0]["content"][0]["audio"]
    assert audio_part.startswith("data:audio/") and ";base64," in audio_part


# ---------- 4. 前置检查：不花网络往返就该拦住 ----------

def test_missing_key_does_not_call_provider(monkeypatch, http):
    monkeypatch.delenv("ASR_API_KEY", raising=False)
    out = asr.transcribe(AUDIO, "a.webm", "audio/webm")
    assert out["ok"] is False and "ASR_API_KEY" in out["error"]
    assert http.calls == []                            # 没密钥就不该发请求


def test_empty_audio_rejected(keyed, http):
    out = asr.transcribe(b"", "a.webm", "audio/webm")
    assert out["ok"] is False and "为空" in out["error"]
    assert http.calls == []


def test_oversized_audio_rejected(keyed, http):
    out = asr.transcribe(b"\x00" * (asr.MAX_AUDIO_BYTES + 1), "big.webm", "audio/webm")
    assert out["ok"] is False
    assert "过大" in out["error"] and "5 MB" in out["error"]
    assert http.calls == []


def test_too_long_wav_rejected(keyed, http):
    """WAV 的时长标准库就能算准，故"超过 60 秒"这一关对它是真校验（不是按字节折算）。"""
    out = asr.transcribe(_wav(61), "long.wav", "audio/wav")
    assert out["ok"] is False and "过长" in out["error"] and "60" in out["error"]
    assert http.calls == []


def test_short_wav_still_passes(keyed, http):
    """别把正常录音误伤：1 秒的 WAV 必须放行（WAV 体积大，最容易撞上"过大/过长"）。"""
    http.response = _Resp(200, {"text": "好的"})
    out = asr.transcribe(_wav(1), "ok.wav", "audio/wav")
    assert out["ok"] is True and out["text"] == "好的"


# ---------- 5. 端点：状态公开、无令牌 403、未配置 503 ----------

def test_status_endpoint_is_public(client):
    r = client.get("/api/asr/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is False              # .env 里 ASR_API_KEY 是空的
    assert "api_key" not in json.dumps(body)


def test_status_endpoint_still_hides_key(client, monkeypatch):
    """即使配了密钥，公开端点也只回报"能不能用"。"""
    monkeypatch.setenv("ASR_API_KEY", FAKE_KEY)
    r = client.get("/api/asr/status")
    assert r.status_code == 200
    assert r.json()["configured"] is True
    assert FAKE_KEY not in r.text


def test_transcribe_requires_owner_token(client):
    """没令牌：403（不是 422）。

    这里同时覆盖"连请求体都没有"和"带了音频"两种：鉴权必须在解析请求体**之前**发生，
    否则前端拿到 422 会以为是音频格式问题。
    """
    assert client.post("/api/asr/transcribe").status_code == 403
    r = client.post("/api/asr/transcribe", files={"file": ("a.webm", AUDIO, "audio/webm")})
    assert r.status_code == 403
    assert "归属令牌" in r.json()["detail"]


def test_transcribe_503_when_not_configured(client):
    r = client.post("/api/asr/transcribe", headers=TOKEN,
                    files={"file": ("a.webm", AUDIO, "audio/webm")})
    assert r.status_code == 503
    assert "ASR_API_KEY" in r.json()["detail"]      # 明确告诉站长该填哪个键，而不是"服务异常"


def test_transcribe_400_when_no_file_field(client, monkeypatch):
    monkeypatch.setenv("ASR_API_KEY", FAKE_KEY)
    r = client.post("/api/asr/transcribe", headers=TOKEN, data={"model": "x"})
    assert r.status_code == 400
    assert "file" in r.json()["detail"]


def test_transcribe_happy_path(client, monkeypatch):
    monkeypatch.setenv("ASR_API_KEY", FAKE_KEY)
    seen = {}

    def fake_transcribe(audio, filename, content_type):
        seen.update(audio=audio, filename=filename, content_type=content_type)
        return {"ok": True, "text": "梅花易数", "provider": "fake", "model": "test-asr-model",
                "ms": 12, "error": ""}

    monkeypatch.setattr(asr, "transcribe", fake_transcribe)
    r = client.post("/api/asr/transcribe", headers=TOKEN,
                    files={"file": ("rec.webm", AUDIO, "audio/webm")})
    assert r.status_code == 200, r.text
    assert r.json() == {"text": "梅花易数", "model": "test-asr-model", "ms": 12}
    # 端点必须把音频原样、连同文件名与类型一起交给客户端模块
    assert seen == {"audio": AUDIO, "filename": "rec.webm", "content_type": "audio/webm"}


def test_transcribe_upstream_failure_is_502(client, monkeypatch):
    monkeypatch.setenv("ASR_API_KEY", FAKE_KEY)
    monkeypatch.setattr(asr, "transcribe", lambda *a, **k: {
        "ok": False, "text": "", "provider": "fake", "model": "m", "ms": 3,
        "error": "识别服务暂时不可用（HTTP 503）：请稍后重试"})
    r = client.post("/api/asr/transcribe", headers=TOKEN,
                    files={"file": ("a.webm", AUDIO, "audio/webm")})
    # 502：锅在上游识别服务，不在本站（前端见 5xx 可回退浏览器识别）
    assert r.status_code == 502
    assert "503" in r.json()["detail"]


def test_transcribe_accepts_any_file_field_name(client, monkeypatch):
    """字段名容错：规范是 file，但前端写成 audio/record 也认，别让人对着"没收到文件"发懵。"""
    monkeypatch.setenv("ASR_API_KEY", FAKE_KEY)
    monkeypatch.setattr(asr, "transcribe", lambda *a, **k: {
        "ok": True, "text": "ok", "provider": "fake", "model": "m", "ms": 1, "error": ""})
    r = client.post("/api/asr/transcribe", headers=TOKEN,
                    files={"audio": ("a.webm", AUDIO, "audio/webm")})
    assert r.status_code == 200, r.text


# ---------- 6. 体积：全局 256 KiB 上限不能把录音挡在门外 ----------

def test_upload_over_global_body_cap_still_reaches_handler(client, monkeypatch):
    """回归：/api/asr/transcribe 必须按音频上限放行。

    全局 MAX_BODY_BYTES 是 256 KiB（给"请求原样入库"的端点定的），而 60 秒录音就有几百 KB
    ——不放行的话，音频会在进业务逻辑之前被中间件 413 掉，表现为"语音输入永远失败"。
    """
    monkeypatch.setenv("ASR_API_KEY", FAKE_KEY)
    audio = b"x" * (600 * 1024)                     # 600 KiB > 256 KiB，且 < 5 MB
    got = {}
    monkeypatch.setattr(asr, "transcribe", lambda a, f, c: got.update(size=len(a)) or {
        "ok": True, "text": "长录音", "provider": "fake", "model": "m", "ms": 5, "error": ""})
    r = client.post("/api/asr/transcribe", headers=TOKEN,
                    files={"file": ("long.webm", audio, "audio/webm")})
    assert r.status_code == 200, r.text
    assert got["size"] == len(audio)                # 一个字节都没被截断


def test_oversized_audio_413(client, monkeypatch):
    """超过 5 MB：413，且提示里给出具体上限（"请求内容过大"太笼统，用户不知道该录多短）。"""
    monkeypatch.setenv("ASR_API_KEY", FAKE_KEY)
    r = client.post("/api/asr/transcribe", headers=TOKEN,
                    files={"file": ("huge.webm", b"x" * (asr.MAX_AUDIO_BYTES + 2048),
                                    "audio/webm")})
    assert r.status_code == 413
    assert "录音过大" in r.json()["detail"]


def test_absurd_upload_stopped_by_middleware(client, monkeypatch):
    """再大（> 请求体上限）由中间件在进业务逻辑之前挡掉，不让它进内存。"""
    monkeypatch.setenv("ASR_API_KEY", FAKE_KEY)
    r = client.post("/api/asr/transcribe", headers=TOKEN,
                    files={"file": ("huge.webm", b"x" * (asr.MAX_REQUEST_BYTES + 4096),
                                    "audio/webm")})
    assert r.status_code == 413
    assert r.json()["detail"] == "请求内容过大"


def test_other_endpoints_keep_the_256k_cap(client):
    """别把放宽做成了全局放宽：普通端点的请求体上限必须原样。"""
    assert main.MAX_BODY_BYTES == 256 * 1024
    assert main._BODY_CAP_BY_PATH == {"/api/asr/transcribe": asr.MAX_REQUEST_BYTES}
    r = client.post("/api/mingju/check", json={"question": "x" * (300 * 1024)})
    assert r.status_code == 413


# 说明：/api/asr/transcribe 的 30 次/分钟限流没有做成测试——它按**客户端 IP** 计数
# （TestClient 全部算作 "testclient"），跑满 31 次会污染同一进程里其它 ASR 端点测试的
# 配额，测试之间就会互相绊倒。限流本身是 rate_limit() 的既有能力，这里只保证它被调用。
