"""
意图识别模块
规则优先 + AI 兜底
"""
import re
import json
from typing import Optional


# ============================================================
# 规则匹配
# ============================================================

def _is_chinese_char(c: str) -> bool:
    """判断是否中文字符"""
    return '一' <= c <= '鿿' or '㐀' <= c <= '䶿'


def _extract_chinese_chars(text: str) -> list[str]:
    """提取中文字符列表"""
    return [c for c in text if _is_chinese_char(c)]


def rule_based_intent(user_input: str) -> Optional[dict]:
    """
    规则优先意图识别
    返回: {"method": str, "params": dict} 或 None（需要AI兜底）
    """
    text = user_input.strip()
    if not text:
        return None

    chars = _extract_chinese_chars(text)

    # ---- 时间起卦（高优先级：时间词 + 日期 > 一切） ----
    time_keywords = ["现在", "最近", "今天", "今年", "此刻", "当前", "近来",
                     "今日运势", "现在运势", "最近运势", "当前时间", "此时此刻",
                     "当下", "今日", "今年运势", "此刻运势"]
    date_keywords = ["年", "月", "日", "时", "分", "秒"]
    fortune_keywords = ["运势", "运气", "怎么样", "如何", "好吗", "好不好"]

    has_time = any(kw in text for kw in time_keywords)
    has_cezi = any(kw in text for kw in ["测", "占", "算", "起卦", "占卜"])

    # 检测日期格式：纯数字日期 或 中文数字日期
    has_date = bool(re.search(r'\d{2,4}\s*[年/\-]\s*\d{1,2}\s*[月/\-]', text))  # 2026年6月 等
    has_chinese_date = bool(re.search(r'[二三四五六七八九]?[一二三四五六七八九十]?[年月日]', text))
    has_time_chinese = has_date or has_chinese_date
    # 农历相关关键词
    lunar_keywords = ["农历", "阴历", "八字", "时辰"]
    has_lunar = any(kw in text for kw in lunar_keywords)

    # 明确的时间占：时间词 + (运势/占卜意图/日期/农历/很短的纯时间)
    if has_time or has_time_chinese or has_lunar:
        is_fortune = any(kw in text for kw in fortune_keywords)
        # 短输入=纯时间词(如"现在"/"今天")，不含描述性内容
        is_pure_time = len(chars) <= 4 and has_time
        # 含占卜意图 + 时间词 → 明确时间占
        has_divine_intent = has_cezi and has_time
        if is_pure_time or is_fortune or has_time_chinese or has_lunar or has_divine_intent:
            return {"method": "time", "params": {}}

    # ---- 3. 一字占 ----
    # 检测模式: "测'X'" / "测"X"" / "字占X" / "测字X" / "占X字" 等等
    cezi_patterns = [
        r"测['\"]?(.)['\"]?(?:字|$)",
        r"字占['\"]?(.)['\"]?",
        r"测字['\"]?(.)['\"]?",
        r"占['\"]?(.)['\"]?字",
        r"算['\"]?(.)['\"]?字",
    ]
    for pattern in cezi_patterns:
        m = re.search(pattern, text)
        if m:
            ch = m.group(1)
            if _is_chinese_char(ch):
                return {"method": "yizi", "params": {"zi": ch}}

    # "测'变'字问事业" 这种模式
    m = re.search(r"测['\"]?([^'\"]{1,2})['\"]?字", text)
    if m:
        ch = m.group(1).strip()
        if len(ch) == 1 and _is_chinese_char(ch):
            return {"method": "yizi", "params": {"zi": ch}}

    # ---- 4. 单/双字测字意图 ----
    if len(chars) <= 2 and has_cezi:
        if len(chars) == 1:
            return {"method": "yizi", "params": {"zi": chars[0]}}
        elif len(chars) == 2:
            return {"method": "erzi", "params": {"zi1": chars[0], "zi2": chars[1]}}

    # ---- 5. 数字占（纯数字，非日期上下文） ----
    if not has_time and not has_time_chinese and not has_lunar:
        nums = re.findall(r'\d+', text)
        if len(nums) == 3:
            try:
                n1, n2, n3 = int(nums[0]), int(nums[1]), int(nums[2])
                # 只有在文本本身包含日期关键词时才跳过数字占
                # "3 5 8" 这种纯数字不跳过
                if has_date and n1 > 31:
                    pass  # 大数字+日期关键词=明确日期输入，不按数字占
                else:
                    return {"method": "shuzi", "params": {"n1": n1, "n2": n2, "n3": n3}}
            except ValueError:
                pass

    # ---- 6. 单字/二字自动判断 ----
    if len(chars) == 1:
        return {"method": "yizi", "params": {"zi": chars[0]}}
    if len(chars) == 2:
        return {"method": "erzi", "params": {"zi1": chars[0], "zi2": chars[1]}}

    # ---- 7. 多字占（一般文本输入） ----
    if len(chars) >= 3:
        return {"method": "duozi", "params": {"text": text}}

    # ---- 未匹配 → AI 兜底 ----
    return None


# ============================================================
# AI 意图识别（兜底）
# ============================================================

AI_INTENT_PROMPT = """你是梅花易数起卦助手。分析用户输入，判断应该使用哪种起卦方式。

可选方式（注意：没有"随机起卦"，不动不占、无故不占）：
- yizi（一字占）：用户想测一个字
- erzi（二字占）：用户想测两个字
- duozi（多字占）：用户输入一句话/词组，用声调起卦
- time（时间起卦）：用户问当前运势或以时间为机
- shuzi（物数占）：用户见可数之物，提供了具体数字

请只输出 JSON，格式：{"method": "方法名", "params": {...}}

params 要求：
- yizi: {"zi": "字"}
- erzi: {"zi1": "字1", "zi2": "字2"}
- duozi: {"text": "完整文本"}
- shuzi: {"n1": 数1, "n2": 数2, "n3": 数3}
- time: {}

用户输入："""


async def ai_intent(user_input: str, llm_config: dict) -> dict:
    """调用 AI 进行意图识别"""
    import httpx

    url = f"{llm_config['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {llm_config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": llm_config["model"],
        "messages": [
            {"role": "system", "content": "你是一个 JSON 输出助手，只输出 JSON，不输出其他内容。"},
            {"role": "user", "content": AI_INTENT_PROMPT + user_input},
        ],
        "max_tokens": 200,
        "temperature": 0,
        # 推理模型会把预算烧在 reasoning_content 上导致 content 为空，关闭思考保证 JSON 稳定输出
        "thinking": {"type": "disabled"},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

    # 解析 JSON
    # 处理可能的 markdown 代码块
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # 如果 AI 返回格式不对，默认走多字占
        return {"method": "duozi", "params": {"text": user_input}}


# ============================================================
# 统一入口
# ============================================================

async def recognize_intent(user_input: str, llm_config: dict = None) -> dict:
    """
    统一意图识别入口
    1. 先试规则匹配
    2. 未匹配且配置了 LLM → AI 兜底
    3. 否则走默认（多字占）
    """
    # 规则优先
    result = rule_based_intent(user_input)
    if result is not None:
        result["source"] = "rule"
        return result

    # AI 兜底
    if llm_config and llm_config.get("api_key"):
        try:
            result = await ai_intent(user_input, llm_config)
            result["source"] = "ai"
            return result
        except Exception:
            pass

    # 默认：多字占
    return {"method": "duozi", "params": {"text": user_input}, "source": "default"}
