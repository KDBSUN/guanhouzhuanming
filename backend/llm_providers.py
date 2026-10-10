# -*- coding: utf-8 -*-
"""模型厂商预设名单（用户自带 API key 解卦用）

## 为什么必须有这份名单，而不是让用户自己填接口地址

后端会拿"用户给的地址"去发请求。地址若由用户随便填，本站服务器就成了任意地址的
转发器（SSRF：可以拿它去打内网、打别人的接口）。所以**地址一律由服务端写死**，
用户只能做三件事：选厂商、填自己的 key、改模型名（模型名不影响请求去往哪个地址）。

## 事实来源（2026-10-02 逐一查证官方文档，不是凭记忆写的）

- **DeepSeek**：<https://api-docs.deepseek.com/> —— base_url `https://api.deepseek.com`，
  与 OpenAI/Anthropic 格式兼容；当前模型 `deepseek-flash`、`deepseek-v4-pro`；
  旧名 `deepseek-v4-flash`、`deepseek-v4-flash-vision-exp` 仍被接受，但对应模型已退役、
  由 DeepSeek-V4.1-Flash 承接并按 Flash 价格计费。key 在 <https://platform.deepseek.com/api_keys> 申请。
- **Kimi（月之暗面）**：<https://platform.kimi.com/docs/api/overview> ——
  OpenAI Chat Completions：`https://api.moonshot.cn/v1`；文档模型列表页给出的模型名包括
  `kimi-k3`、`kimi-k2.6`、`kimi-k2.7-code`、`kimi-k2.7-code-highspeed`。
- **智谱 GLM**：<https://docs.bigmodel.cn/cn/guide/develop/openai/introduction> ——
  `base_url="https://open.bigmodel.cn/api/paas/v4/"`，文档示例模型 `glm-5.3`；
  模型总览页另有 `GLM-5.3-Flash`、`GLM-5.2` 等。官方原文注明"某些场景下智谱与 OpenAI
  接口仍存在差异，但不影响整体兼容性"。
- **通义千问（阿里云百炼）**：<https://www.alibabacloud.com/help/zh/model-studio/compatibility-of-openai-with-dashscope>
  —— OpenAI 兼容地址以 `/compatible-mode/v1` 结尾（不含 `/chat/completions`）；
  文档原文："原 `https://dashscope.aliyuncs.com` 域名仍可正常使用，但建议优先使用业务空间
  专属域名"；**API Key 按地域绑定**，用 A 地域的 key 调 B 地域地址会返回 401
  `invalid_api_key`；流式输出需在请求体指定 `stream=true`。文档示例模型 `qwen3.8-max`。
- **豆包（火山方舟）**：<https://www.volcengine.com/docs/82379/1298454> ——
  `POST https://ark.cn-beijing.volces.com/api/v3/chat/completions`，文档自述"兼容 OpenAI SDK"，
  示例模型 `doubao-seed-2-1-pro-260628`。

## 未查证的部分（写在这里，不装懂）

- 除 DeepSeek 外，其余四家是否容忍本站请求体里的 `thinking` 字段（DeepSeek 专有，用来关掉
  推理模型的思考）。**官方文档都没写这一条**，故代码里的做法是"只对 DeepSeek 发这个字段"，
  这样就不需要依赖"别家会忽略未知字段"这种假设。
- 各家的限流与计费口径（各家定价页会变），本站不代为承诺；这些数字请以用户自己控制台为准。
- 四家的**流式响应字段**是否与 OpenAI 完全一致（如 DeepSeek 的 `reasoning_content`）：
  文档未逐一比对，接口里按 OpenAI 的 `choices[0].delta` 兼容读取。

## 真实 key 实测记录（2026-10-06，每家一次最小请求，经本站 /api/llm/test 接口，五家全部通过）

- **DeepSeek** · deepseek-flash → 连接成功（站长自己的付费 key）。
- **豆包（火山方舟）** · doubao-seed-evolving → 连接成功（用户实测）。
- **通义千问（百炼）** · qwen3.8-flash → 连接成功（用户实测）。
- **智谱 GLM** · GLM-5.3-Flash → 连接成功（用户实测）。
- **Kimi** · kimi-k2.6 → 连接成功（用户实测）。
- **Kimi** · kimi-k3 → HTTP 404「Not found the model kimi-k3 or Permission denied」——
  k3 需要账号开通权限，未开通的账号用 k3 会 404；默认模型因此取 k2.6。
- 上述结果同时证实了"各家模型名与账号开通状态有关"——所以模型名允许用户手填，
  是必要的，不是便利。
"""
from typing import Optional

# 每个厂商：显示名、写死的接口地址、默认模型、候选模型（前端下拉用）、是否发 thinking 字段
PROVIDERS: dict = {
    "deepseek": {
        "label": "DeepSeek",
        "note": "本站提示词与流式解析按它调校，推荐",
        "recommended": True,
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-flash",
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "send_thinking": True,
        "key_url": "https://platform.deepseek.com/api_keys",
    },
    "kimi": {
        "label": "Kimi（月之暗面）",
        "note": "kimi-k2.6 已实测通过；kimi-k3 需账号开通权限（未开通会 404）",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "kimi-k2.6",
        "models": ["kimi-k2.6", "kimi-k3", "kimi-k2.7-code", "kimi-k2.7-code-highspeed"],
        "send_thinking": False,
        "key_url": "https://platform.kimi.com/",
    },
    "zhipu": {
        "label": "智谱 GLM",
        "note": "官方注明部分场景与 OpenAI 仍有差异；GLM-5.3-Flash 已实测通过",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "GLM-5.3-Flash",
        "models": ["GLM-5.3-Flash", "glm-5.3", "GLM-5.2"],
        "send_thinking": False,
        "key_url": "https://bigmodel.cn/usercenter/proj-mgmt/apikeys",
    },
    "qwen": {
        "label": "通义千问（阿里云百炼）",
        "note": "key 与地域绑定：中国站 key 配中国站地址；qwen3.8-flash 已实测通过",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen3.8-flash",
        "models": ["qwen3.8-flash", "qwen3.8-max", "qwen-plus", "qwen-max"],
        "send_thinking": False,
        "key_url": "https://bailian.console.aliyun.com/",
    },
    "ark": {
        "label": "豆包（火山方舟）",
        "note": "文档自述兼容 OpenAI SDK；doubao-seed-evolving 已实测通过",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-seed-evolving",
        "models": ["doubao-seed-evolving", "doubao-seed-2-1-pro-260628"],
        "send_thinking": False,
        "key_url": "https://console.volcengine.com/ark",
    },
}

MODEL_RE_MAX = 64


def public_list() -> list:
    """给前端的名单（**不含任何密钥字段**，也不含内部标记以外的多余信息）。"""
    return [
        {"id": pid, "label": p["label"], "note": p.get("note", ""),
         "recommended": bool(p.get("recommended")),
         "default_model": p["default_model"], "models": list(p["models"]),
         "key_url": p.get("key_url", "")}
        for pid, p in PROVIDERS.items()
    ]


def valid_model(model: str) -> bool:
    """模型名只做形状校验：它不影响请求去往哪个地址，故允许手填（各家模型更新很快）。

    禁止的是能改变请求语义的字符（空格、路径分隔以外的符号、控制字符）。
    """
    m = (model or "").strip()
    if not m or len(m) > MODEL_RE_MAX:
        return False
    for ch in m:
        if not (ch.isalnum() or ch in "-._:/"):
            return False
    return True


def resolve(provider: str, model: str = "") -> Optional[dict]:
    """把"厂商 + 模型名"解析成一次调用的目标；未知厂商返回 None（调用方据此拒绝）。

    返回的 base_url **来自本文件**，不接受调用方传入。
    """
    p = PROVIDERS.get((provider or "").strip().lower())
    if not p:
        return None
    m = (model or "").strip() or p["default_model"]
    if not valid_model(m):
        return None
    return {"provider": provider.strip().lower(), "label": p["label"],
            "base_url": p["base_url"], "model": m,
            "send_thinking": bool(p.get("send_thinking"))}
