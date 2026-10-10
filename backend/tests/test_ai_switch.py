# -*- coding: utf-8 -*-
"""
两步解卦：起卦/排盘不花 AI，AI 解卦要另外点一下
================================================
2026-09-19 由站长定的产品规则，理由一句话：**"起一卦看看"与"花一次额度让 AI 讲"是两件事**。
摇完六爻就想看一眼卦，是很常见的用法；不该因为看一眼就自动花掉一次额度。

实现上就是两个端点各多了一个 `ai` 开关（`/api/liuyao/divine`、`/api/meihua/divine`）：
  · `ai=False` → 只出卦/盘（卦象、用神、体用、处方五行、应期），**不调 LLM、不扣额度**；
  · `ai=True`  → 照旧。

2026-10-02 追加的口径（站长）：**自带 key 的请求走用户自己的额度，不计数也不拦**；
没带 key 的走"签到 + 每设备当日 3 次"，不签到不给用。这个文件因此还盯三件事：
  · 未签到时 `ai=True` 必须降级（scope=signin），而不是静默花站长的钱；
  · 模型设置写错（厂商不在名单/没填 key）必须如实报错（scope=llm），**不许悄悄退回免费路径**；
  · 自带 key 时额度计数一动不动。

这个文件盯的是**接线**而不是排盘本身：
  ① `ai=False` 时确实没有 `text` 事件、也没有 `degraded`（那不是"额度用尽"，是用户还没点）；
  ② `ai=False` 时配额计数**一动不动**——这条最容易写漏：多扣一次额度不会报错，
     用户只会觉得"我就看了一眼盘怎么额度就少了"；
  ③ `ai=True` 时照样扣，别为了省事把闸整个拆了。

为什么这一层必须用 HTTP 测：`_quota_acquire` 在端点里，直接调 `quota.acquire_free()` 测不到
"端点在 ai=False 时到底调没调它"。与 test_owner_scope.py 里那批端点守卫测试同一个道理。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import decision_log                                   # noqa: E402
import main                                           # noqa: E402
import mingju_profile                                 # noqa: E402
import quota                                          # noqa: E402
import records                                        # noqa: E402

THROWS = [{"x": 9.0 + i * 2.5, "y": 3.0 + i, "duration": 620 + i * 15, "speed": 0.4}
          for i in range(6)]

# 免费额度按"设备令牌"记账，所以这些测试必须带上令牌，签到与解卦才是同一个设备
DEV = {"X-Owner-Token": "tok-dev"}


def _signin(client) -> None:
    r = client.post("/api/quota/signin", headers=DEV)
    assert r.status_code == 200, r.text


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """临时库 + 临时配额库 + 关掉真 API Key（免得测试真去调 LLM）。"""
    db = Path(tmp_path) / "api.db"
    monkeypatch.setattr(records, "_DB_PATH", db)
    monkeypatch.setattr(decision_log, "_DB_PATH", db)
    monkeypatch.setattr(mingju_profile, "_DB_PATH", db)
    monkeypatch.setenv("QUOTA_DB", str(Path(tmp_path) / "quota.db"))
    records.init_db()
    decision_log.init_log_db()
    mingju_profile.init_db()
    # 默认（含 .env）里 api_key 是有值的；不关掉的话 ai=True 那条会真去打上游。
    monkeypatch.setitem(main.LLM_CONFIG, "api_key", "")
    from fastapi.testclient import TestClient
    return TestClient(main.app)


def _events(resp) -> list:
    out = []
    for block in resp.text.split("\n\n"):
        if block.startswith("data: "):
            out.append(json.loads(block[6:]))
    return out


def _types(evs) -> list:
    return [e.get("type") for e in evs]


def test_liuyao_paipan_only_sends_no_text_and_no_degrade(client):
    """ai=False：只出排盘。**不能发 degraded**——那不是"额度用尽"，是用户还没点 AI。"""
    r = client.post("/api/liuyao/divine",
                    json={"question": "这份合作能不能谈成", "throws": THROWS, "ai": False})
    assert r.status_code == 200, r.text
    evs = _events(r)
    assert _types(evs) == ["gua_data", "done"], _types(evs)
    gd = evs[0]["data"]
    # 排盘该给的东西一样不能少：这些都是确定性计算，与 AI 无关
    for k in ("ben_gua", "lines", "remedy", "yingqi", "time_info"):
        assert gd.get(k), "ai=False 漏了 %s" % k


def test_liuyao_paipan_only_does_not_spend_quota(client):
    """**这条是本文件最要紧的一条**：只看盘不能扣额度。

    多扣不会报错、不会崩、页面上也看不出来，用户只会觉得额度莫名其妙少了。
    """
    before = quota.status()["used"]
    client.post("/api/liuyao/divine",
                json={"question": "问事", "throws": THROWS, "ai": False})
    assert quota.status()["used"] == before, "ai=False 竟然扣了额度"


def test_liuyao_ai_step_spends_exactly_one(client):
    """ai=True 照旧扣一次——别为了省事把闸整个拆了。"""
    _signin(client)
    before = quota.status()["used"]
    r = client.post("/api/liuyao/divine",
                    json={"question": "问事", "throws": THROWS, "ai": True}, headers=DEV)
    assert r.status_code == 200
    assert quota.status()["used"] == before + 1


def test_liuyao_default_is_still_ai(client):
    """不传 ai 时按原样走 AI（老客户端与直接调 API 的行为不变）。"""
    _signin(client)
    before = quota.status()["used"]
    client.post("/api/liuyao/divine", json={"question": "问事", "throws": THROWS}, headers=DEV)
    assert quota.status()["used"] == before + 1


def test_liuyao_ai_without_signin_degrades_with_signin_scope(client):
    """没签到就点 AI：必须降级、且**说明是去签到**（2026-10-02 的新口径）。

    这条同时守住"不许静默花站长的钱"：未签到时若仍然照常出 AI 文字，
    说明闸门形同虚设，而页面上完全看不出来。
    """
    r = client.post("/api/liuyao/divine",
                    json={"question": "问事", "throws": THROWS, "ai": True}, headers=DEV)
    assert r.status_code == 200, r.text
    evs = _events(r)
    assert "text" not in _types(evs), "未签到竟然出了 AI 正文"
    deg = [e for e in evs if e.get("type") == "degraded"]
    assert deg and deg[0]["scope"] == "signin", evs
    assert "签到" in deg[0]["message"]
    # 卦照常给全（这是本站所有降级一贯的取向）
    assert _types(evs)[0] == "gua_data"
    assert quota.status()["used"] == 0, "未签到不该产生任何用量"


def test_device_free_limit_blocks_fourth_call(client):
    """签到后当日 3 次，第 4 次拦下（scope=device）。"""
    _signin(client)
    for i in range(3):
        client.post("/api/liuyao/divine",
                    json={"question": "问事", "throws": THROWS, "ai": True}, headers=DEV)
    r = client.post("/api/liuyao/divine",
                    json={"question": "问事", "throws": THROWS, "ai": True}, headers=DEV)
    deg = [e for e in _events(r) if e.get("type") == "degraded"]
    assert deg and deg[0]["scope"] == "device", _events(r)


# ---------- 自带 key（BYOK）：不计数、不拦，且用用户的模型 ----------

def test_byok_does_not_touch_quota_and_uses_user_model(client, monkeypatch):
    """带 key 时不签到也能用，且**不产生任何本站用量**。"""
    seen = {}

    async def fake_stream(user_prompt, system_prompt=None, max_tokens=None,
                          disable_thinking=False, messages=None, state=None, llm=None):
        seen["llm"] = llm
        yield "（示例断语）"

    monkeypatch.setattr(main, "_stream_llm", fake_stream)
    r = client.post("/api/liuyao/divine", headers=DEV, json={
        "question": "问事", "throws": THROWS, "ai": True,
        "llm": {"provider": "deepseek", "api_key": "sk-user-test", "model": "deepseek-flash"},
    })
    assert r.status_code == 200, r.text
    evs = _events(r)
    assert "text" in _types(evs), evs
    assert not [e for e in evs if e.get("type") == "degraded"]
    assert quota.status()["used"] == 0, "自带 key 不该计入本站免费额度"
    assert seen["llm"]["base_url"] == "https://api.deepseek.com"   # 地址来自服务端名单
    assert seen["llm"]["model"] == "deepseek-flash"
    assert seen["llm"]["api_key"] == "sk-user-test"


def test_byok_key_never_reaches_the_log(client):
    """用户的 key 绝不能进决策日志（它对本站是敏感信息，对用户更是）。"""
    r = client.post("/api/liuyao/divine", headers=DEV, json={
        "question": "问事", "throws": THROWS, "ai": True,
        "llm": {"provider": "deepseek", "api_key": "sk-should-not-be-stored"},
    })
    assert r.status_code == 200, r.text
    rows = decision_log.recent(5, "tok-dev")
    blob = json.dumps(rows, ensure_ascii=False)
    assert "sk-should-not-be-stored" not in blob, "用户的 key 被写进了决策日志"


def test_bad_provider_degrades_with_llm_scope(client):
    """厂商不在预设名单里：如实报错，**不许悄悄退回免费路径**。"""
    r = client.post("/api/liuyao/divine", headers=DEV, json={
        "question": "问事", "throws": THROWS, "ai": True,
        "llm": {"provider": "some-unknown-vendor", "api_key": "sk-x"},
    })
    deg = [e for e in _events(r) if e.get("type") == "degraded"]
    assert deg and deg[0]["scope"] == "llm", _events(r)
    assert quota.status()["used"] == 0


def test_provider_without_key_degrades_with_llm_scope(client):
    """选了厂商却没填 key：同样是 llm 作用域的报错，而不是当没设置。"""
    r = client.post("/api/liuyao/divine", headers=DEV, json={
        "question": "问事", "throws": THROWS, "ai": True,
        "llm": {"provider": "deepseek", "api_key": ""},
    })
    deg = [e for e in _events(r) if e.get("type") == "degraded"]
    assert deg and deg[0]["scope"] == "llm", _events(r)


def test_providers_endpoint_lists_five_and_hides_nothing_secret(client):
    """名单接口：五家都在，且**不带出任何密钥或内部地址字段**。

    这里按**字段名**判断，不按字符串扫——`key_url`（申请 key 的页面地址）里含 "api_key"
    这几个字母，用子串扫会误报，那种断言查不出真问题、只会制造假红。
    """
    r = client.get("/api/llm/providers")
    assert r.status_code == 200
    data = r.json()
    ids = [p["id"] for p in data["providers"]]
    assert ids == ["deepseek", "kimi", "zhipu", "qwen", "ark"], ids
    assert data["providers"][0]["recommended"] is True, "DeepSeek 应标注推荐"
    assert data["free_per_day"] == quota.FREE_AI_PER_DAY
    allowed = {"id", "label", "note", "recommended", "default_model", "models", "key_url"}
    for p in data["providers"]:
        assert set(p.keys()) == allowed, "名单多带了字段：%s" % (set(p.keys()) - allowed)
        assert "base_url" not in p and "api_key" not in p
    assert set(data.keys()) == {"providers", "free_per_day", "note"}


def test_llm_test_endpoint_rejects_unknown_provider(client):
    r = client.post("/api/llm/test", json={"provider": "nope", "api_key": "sk-x"})
    assert r.status_code == 400


# ============================================================================
# 站长导入站点 key（/api/llm/site-key，2026-10-08）
# 为什么要它：站点 key 走的是"签到后每天 3 次"的免费路径，站长要反复解卦检验内容
# 会被这个额度卡住；而让站长手工把 .env 里的 key 复制粘贴到设置页，恰恰是最容易把
# key 落进剪贴板的一步。边界：必须带 X-Admin-Token（与校准提案同一套 require_admin）。
# ============================================================================
def _site_cfg(monkeypatch, api_key="sk-site-secret", base_url="https://api.deepseek.com",
              model="deepseek-flash"):
    monkeypatch.setattr(main, "LLM_CONFIG",
                        {**main.LLM_CONFIG, "api_key": api_key, "base_url": base_url, "model": model})


def test_site_key_endpoint_requires_admin_token(client, monkeypatch):
    """未配置 ADMIN_TOKEN → 503 关闭；令牌错/缺 → 403。**绝不能对匿名开放**（那是站点 key）。"""
    _site_cfg(monkeypatch)
    monkeypatch.setattr(main, "ADMIN_TOKEN", "")
    assert client.get("/api/llm/site-key").status_code == 503

    monkeypatch.setattr(main, "ADMIN_TOKEN", "tok-admin")
    assert client.get("/api/llm/site-key").status_code == 403
    assert client.get("/api/llm/site-key", headers={"X-Admin-Token": "wrong"}).status_code == 403


def test_site_key_returns_key_to_admin_and_forbids_caching(client, monkeypatch):
    """对令牌：返回厂商 id（按 LLM_BASE_URL 在名单里匹配）、key、模型名；并带 no-store。"""
    _site_cfg(monkeypatch)
    monkeypatch.setattr(main, "ADMIN_TOKEN", "tok-admin")
    r = client.get("/api/llm/site-key", headers={"X-Admin-Token": "tok-admin"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["provider"] == "deepseek" and j["api_key"] == "sk-site-secret"
    assert j["model"] == "deepseek-flash"
    assert r.headers.get("cache-control") == "no-store", "站点 key 不得进缓存"


def test_site_key_refuses_base_url_outside_provider_list(client, monkeypatch):
    """站点地址不在名单里 → 409 并列出名单：不猜厂商，也不返回一个"存得上、用不了"的设置。"""
    _site_cfg(monkeypatch, base_url="https://api.example.com/v1")
    monkeypatch.setattr(main, "ADMIN_TOKEN", "tok-admin")
    r = client.get("/api/llm/site-key", headers={"X-Admin-Token": "tok-admin"})
    assert r.status_code == 409 and "名单" in r.json()["detail"]


def test_site_key_empty_site_key_is_503(client, monkeypatch):
    """站点自己没配 key：503 说明"无可导入"，而不是回一个空 key 让前端存进去。"""
    _site_cfg(monkeypatch, api_key="")
    monkeypatch.setattr(main, "ADMIN_TOKEN", "tok-admin")
    assert client.get("/api/llm/site-key", headers={"X-Admin-Token": "tok-admin"}).status_code == 503


def test_meihua_paipan_only_does_not_spend_quota(client):
    """梅花同一条规矩。"""
    before = quota.status()["used"]
    r = client.post("/api/meihua/divine",
                    json={"user_input": "测事", "method": "time", "params": {}, "ai": False})
    assert r.status_code == 200, r.text
    assert _types(_events(r)) == ["gua_data", "done"], _types(_events(r))
    assert quota.status()["used"] == before, "ai=False 竟然扣了额度"


def test_meihua_ai_step_spends_exactly_one(client):
    _signin(client)
    before = quota.status()["used"]
    client.post("/api/meihua/divine", headers=DEV,
                json={"user_input": "测事", "method": "time", "params": {}, "ai": True})
    assert quota.status()["used"] == before + 1


def test_meihua_paipan_only_degrades_intent_to_rules(client, monkeypatch):
    """ai=False 时连"认起卦方式"也必须降级成纯规则——**一次 LLM 都不许调**。

    梅花这条端点在没给 `method` 时会调 `recognize_intent` 去认起卦方式，而它是**会花钱**的
    （传了 LLM 配置就走模型）。端点是靠 `q["allowed"]` 为假把它降级成 `recognize_intent(..., None)`，
    所以这条同时钉住了"ai=False 必须让 q 不 allowed"这个实现细节：
    谁把额度那段写成 `if not request.ai: q = {"allowed": True, ...}`，这条立刻红。
    """
    seen = []
    real = main.recognize_intent

    async def spy(user_input, llm_config):
        seen.append(llm_config)
        return await real(user_input, llm_config)

    monkeypatch.setattr(main, "recognize_intent", spy)
    # 刻意**不传 method**：传了就走不到意图识别那一步，这条测试就空转了
    r = client.post("/api/meihua/divine", json={"user_input": "今天出门顺利吗", "ai": False})
    assert r.status_code == 200, r.text
    assert seen, "意图识别根本没被调用，这条测试没测到东西"
    assert seen[0] is None, "ai=False 却把 LLM 配置递给了意图识别：%r" % (seen,)


def test_meihua_ai_step_does_hand_llm_config_to_intent(client, monkeypatch):
    """反过来也要钉住：ai=True 时意图识别照旧拿得到 LLM 配置。

    少了这条，上面那条可以被"永远传 None"这种写法骗过去——
    那样认起卦方式就退化成纯规则了，功能其实是坏的，而测试全绿。
    """
    seen = []
    real = main.recognize_intent

    async def spy(user_input, llm_config):
        seen.append(llm_config)
        return await real(user_input, llm_config)

    monkeypatch.setattr(main, "recognize_intent", spy)
    _signin(client)
    r = client.post("/api/meihua/divine", headers=DEV,
                    json={"user_input": "今天出门顺利吗", "ai": True})
    assert r.status_code == 200, r.text
    assert seen and seen[0] is not None, "ai=True 却把意图识别降级了：%r" % (seen,)


def test_meihua_byok_hands_user_config_to_intent(client, monkeypatch):
    """自带 key 时，连"认起卦方式"这一步也该用用户自己的模型（不占本站额度）。"""
    seen = []
    real = main.recognize_intent

    async def spy(user_input, llm_config):
        seen.append(llm_config)
        return await real(user_input, llm_config)

    async def fake_stream(user_prompt, system_prompt=None, max_tokens=None,
                          disable_thinking=False, messages=None, state=None, llm=None):
        yield "（示例断语）"

    monkeypatch.setattr(main, "recognize_intent", spy)
    monkeypatch.setattr(main, "_stream_llm", fake_stream)
    r = client.post("/api/meihua/divine", headers=DEV, json={
        "user_input": "今天出门顺利吗", "ai": True,
        "llm": {"provider": "kimi", "api_key": "sk-user", "model": "kimi-k3"},
    })
    assert r.status_code == 200, r.text
    assert seen and seen[0], "自带 key 却没把模型配置交给意图识别"
    assert seen[0]["base_url"] == "https://api.moonshot.cn/v1"
    assert seen[0]["model"] == "kimi-k3"
    assert quota.status()["used"] == 0


# ---------- 记录回填（payload）----------
# 起卦与 AI 分成两步后，一条解读有两次落库时机：先存卦（保证不丢），AI 断完再回填断语。
# 没有这条回填，两步就会各存一条（重复），或者为了不重复而拖到 AI 之后才存
# （那样"只看卦、不要 AI"的那次就什么都不剩）。

def test_record_update_can_backfill_payload(client):
    r = client.post("/api/records", json={
        "kind": "liuyao", "title": "问事", "subtitle": "", "question": "问事",
        "payload": {"gua_data": {"ben_gua": {"name": "坎为水"}}, "ai_text": ""},
    }, headers={"X-Owner-Token": "tok-A"})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]

    ok = client.patch("/api/records", json={
        "id": rid,
        "payload": {"gua_data": {"ben_gua": {"name": "坎为水"}}, "ai_text": "断语到此"},
    }, headers={"X-Owner-Token": "tok-A"})
    assert ok.status_code == 200, ok.text

    got = client.get("/api/records/detail", params={"id": rid},
                     headers={"X-Owner-Token": "tok-A"}).json()
    assert got["payload"]["ai_text"] == "断语到此"
    assert got["payload"]["gua_data"]["ben_gua"]["name"] == "坎为水"


def test_record_payload_backfill_cannot_touch_someone_elses_record(client):
    """回填走的是同一个 owner 守卫：别人的记录改不动（也不能靠它探测存在性）。"""
    r = client.post("/api/records", json={
        "kind": "liuyao", "title": "x", "subtitle": "", "question": "",
        "payload": {"ai_text": "原样"},
    }, headers={"X-Owner-Token": "tok-A"})
    rid = r.json()["id"]
    bad = client.patch("/api/records", json={"id": rid, "payload": {"ai_text": "被改了"}},
                       headers={"X-Owner-Token": "tok-B"})
    assert bad.status_code == 404
    got = client.get("/api/records/detail", params={"id": rid},
                     headers={"X-Owner-Token": "tok-A"}).json()
    assert got["payload"]["ai_text"] == "原样"
