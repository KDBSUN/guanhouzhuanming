# -*- coding: utf-8 -*-
"""
归属隔离回归（A 档最小安全集："设备即账户"）
============================================
规则：所有用户数据的读写都带 owner 令牌（前端 localStorage 的随机串 → X-Owner-Token），
服务端一律 `WHERE owner=?`；令牌即凭证，不需注册，但**拿不到别人的东西**。

覆盖：
  1. 记录：跨身份读/改/删全部被拒，只看到自己的；
  2. 老数据（迁移前无归属）改挂保留归属 __legacy__：对任何令牌都不可见；
  3. 空令牌只能看到空集（不会和老数据撞车），写入被端点拒绝；
  4. 决策日志与 claim 级反馈同样按归属过滤；
  5. 认领通道 claim_legacy() 能把老数据交给指定令牌（站长找回历史用）。
"""
import json
from pathlib import Path

import pytest

import decision_log
import records


@pytest.fixture()
def dbs(tmp_path, monkeypatch):
    monkeypatch.setattr(records, "_DB_PATH", Path(tmp_path) / "r.db")
    monkeypatch.setattr(decision_log, "_DB_PATH", Path(tmp_path) / "r.db")
    records.init_db()
    decision_log.init_log_db()
    return records


# ---------- 1. 记录跨身份 ----------

def test_records_are_isolated_per_owner(dbs):
    a1 = dbs.add("meihua", "A的记录", "A问", "A问", {}, owner="tok-A")
    dbs.add("liuyao", "A的记录2", "A问2", "A问2", {}, owner="tok-A")
    b1 = dbs.add("bazi", "B的记录", "", "", {}, owner="tok-B")

    assert sorted(r["title"] for r in dbs.list_all(owner="tok-A")) == ["A的记录", "A的记录2"]
    assert [r["title"] for r in dbs.list_all(owner="tok-B")] == ["B的记录"]

    # 跨身份：读不到、改不动、删不掉
    assert dbs.get(a1["id"], "tok-B") is None
    assert dbs.update(a1["id"], title="被改了", owner="tok-B") is False
    assert dbs.remove(a1["id"], "tok-B") is False
    assert dbs.purge(a1["id"], "tok-B") is False
    assert dbs.get(a1["id"], "tok-A")["title"] == "A的记录"     # 未被改动
    assert dbs.get(b1["id"], "tok-B")["title"] == "B的记录"


def test_trash_is_isolated(dbs):
    a = dbs.add("meihua", "A的记录", "", "", {}, owner="tok-A")
    b = dbs.add("meihua", "B的记录", "", "", {}, owner="tok-B")
    dbs.remove(a["id"], "tok-A")
    dbs.remove(b["id"], "tok-B")
    assert [r["title"] for r in dbs.list_deleted(owner="tok-A")] == ["A的记录"]
    # B 不能恢复 A 的
    assert dbs.restore(a["id"], "tok-B") is False
    assert dbs.restore(a["id"], "tok-A") is True
    # 清空回收站也只清自己的
    dbs.remove(a["id"], "tok-A")
    assert dbs.empty_trash("tok-A") == 1
    assert len(dbs.list_deleted(owner="tok-B")) == 1


# ---------- 2. 老数据（保留归属） ----------

def test_legacy_rows_invisible_to_everyone(dbs):
    """迁移前的老数据挂 __legacy__：任何真实令牌与空令牌都看不到。"""
    dbs.add("meihua", "老记录", "", "", {}, owner="__legacy__")
    dbs.add("meihua", "新记录", "", "", {}, owner="tok-A")
    assert [r["title"] for r in dbs.list_all(owner="tok-A")] == ["新记录"]
    assert dbs.list_all(owner="") == []
    assert dbs.list_all(owner="tok-B") == []


def test_claim_legacy_hands_rows_to_owner(dbs):
    """认领通道：把老数据交给指定令牌（站长找回历史记录用）。"""
    dbs.add("meihua", "老一", "", "", {}, owner="__legacy__")
    dbs.add("liuyao", "老二", "", "", {}, owner="__legacy__")
    assert dbs.claim_legacy("tok-me") == 2
    # 列表按 id 倒序（后建的在前）
    assert [r["title"] for r in dbs.list_all(owner="tok-me")] == ["老二", "老一"]
    assert dbs.list_all(owner="tok-A") == []
    with pytest.raises(ValueError):
        dbs.claim_legacy("")


# ---------- 3. 空令牌 ----------

def test_anon_and_empty_owner_see_nothing(dbs):
    """无令牌的请求在端点层被映射到匿名保留值 __anon__，它在数据层匹配不到任何行。

    （数据层里 owner='' 仍能匹配 owner='' 的历史行，这是 SQL 语义；线上不会产生新的无主
    数据，因为写端点走 require_owner，而迁移前的老数据已改挂 __legacy__。）
    """
    from main import ANON_OWNER
    dbs.add("meihua", "有主的", "", "", {}, owner="tok-A")
    dbs.add("meihua", "老数据", "", "", {}, owner="__legacy__")
    assert dbs.list_all(owner=ANON_OWNER) == []
    assert dbs.list_all(owner="tok-B") == []
    assert dbs.list_deleted(owner=ANON_OWNER) == []
    assert dbs.get(1, ANON_OWNER) is None


# ---------- 4. 决策日志与 claim 反馈 ----------

def test_check_log_isolated(dbs):
    la = decision_log.append_check({"profile_id": "tok-A", "owner": "tok-A", "question": "A的问事",
                                    "claims": [{"id": "c1", "text": "裁决：平"}]})
    lb = decision_log.append_check({"profile_id": "tok-B", "owner": "tok-B", "question": "B的问事",
                                    "claims": [{"id": "c1", "text": "裁决：顺"}]})
    assert [r["id"] for r in decision_log.recent(10, "tok-A")] == [la]
    assert [r["id"] for r in decision_log.recent(10, "tok-B")] == [lb]
    assert decision_log.get_log(lb, "tok-A") == {}
    assert decision_log.claims_of(lb, "tok-A") == []
    assert decision_log.claims_of(la, "tok-A")[0]["text"] == "裁决：平"


def test_claim_feedback_requires_ownership(dbs):
    la = decision_log.append_check({"owner": "tok-A", "kind": "check", "claims": [{"id": "c1"}]})
    # B 改不了 A 的
    assert decision_log.add_claim_feedback(la, "c1", "应验", owner="tok-B") is False
    assert decision_log.feedback_of(la, "tok-A") == {}
    # A 可以
    assert decision_log.add_claim_feedback(la, "c1", "应验", owner="tok-A") is True
    assert decision_log.feedback_of(la, "tok-A") == {"c1": "应验"}
    assert decision_log.feedback_of(la, "tok-B") == {}


def test_pending_claims_isolated(dbs):
    la = decision_log.append_check({"owner": "tok-A", "kind": "check", "claims": [{"id": "c1"}]})
    decision_log.append_check({"owner": "tok-B", "kind": "check", "claims": [{"id": "c1"}]})
    assert decision_log.pending_claims(5, "tok-A") == [la]


# ---------- 5. 端点级越权（这一层原先是空的，于是侧门洞没被测出来） ----------
#
# 教训：上面 1–4 全是**数据层**测试（直接调 records / decision_log 的函数），
# 它们永远测不到"端点守卫写错了"这类洞。而实际发生的越权正是端点级的：
# `owner_of(request, id)` 在缺令牌时会退回用 query 里的 id 当归属，
# 于是"不带令牌 + 带上别人的 id"就让 `owner_of(...) != id` 恒为假，档案读/删/导出全敞开。
# 下面的测试一律走 HTTP，专门盯端点守卫。

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """把三个模块的库都指到同一个临时库，再给一个 TestClient。"""
    import main
    import mingju_profile
    db = Path(tmp_path) / "api.db"
    monkeypatch.setattr(records, "_DB_PATH", db)
    monkeypatch.setattr(decision_log, "_DB_PATH", db)
    monkeypatch.setattr(mingju_profile, "_DB_PATH", db)
    records.init_db()
    decision_log.init_log_db()
    mingju_profile.init_db()
    from fastapi.testclient import TestClient
    return TestClient(main.app)


BIRTH = {"year": 1990, "month": 5, "day": 12, "hour": 9, "minute": 30, "gender": 1}


def _save(client, token):
    r = client.post("/api/mingju/profile", json={"id": token, **BIRTH},
                    headers={"X-Owner-Token": token})
    assert r.status_code == 200, r.text
    return r


def test_profile_read_needs_token(client):
    """不带令牌读档案必须被拒。

    回归的是那个侧门：`owner_of(request, id)` 用 query 里的 id 当归属兜底，
    于是"只带别人的 id、不带令牌"就能读到完整档案（出生信息 + 命盘）。

    两种拒绝的语义不同，都有意为之：
      · 完全没令牌 → 403，并说明原因（多半是浏览器禁了本地存储；用 404 会让人
        误以为"我的档案没了"，那是更糟的误导）；
      · 拿了别人的令牌 → 404，与"不存在"不可区分（否则响应码本身成了存在性探测器）。
    """
    _save(client, "tok-A")
    r0 = client.get("/api/mingju/profile", params={"id": "tok-A"})
    assert r0.status_code == 403 and "令牌" in r0.json()["detail"]
    # 带别人的令牌也不行，且与不存在同形
    assert client.get("/api/mingju/profile", params={"id": "tok-A"},
                      headers={"X-Owner-Token": "tok-B"}).status_code == 404
    assert client.get("/api/mingju/profile", params={"id": "tok-不存在"},
                      headers={"X-Owner-Token": "tok-B"}).status_code == 404
    # 自己的令牌才行
    r = client.get("/api/mingju/profile", params={"id": "tok-A"},
                   headers={"X-Owner-Token": "tok-A"})
    assert r.status_code == 200 and r.json()["birth"]["year"] == 1990


def test_profile_delete_needs_token(client):
    """不带令牌删档案必须被拒，且档案确实还在。"""
    _save(client, "tok-A")
    assert client.delete("/api/mingju/profile", params={"id": "tok-A"}).status_code == 403
    assert client.delete("/api/mingju/profile", params={"id": "tok-A"},
                         headers={"X-Owner-Token": "tok-B"}).status_code == 404
    assert client.get("/api/mingju/profile", params={"id": "tok-A"},
                      headers={"X-Owner-Token": "tok-A"}).status_code == 200


def test_profile_export_needs_token(client):
    """不带令牌导出（全量备份）必须被拒——否则等于一键拖走别人的全部数据。"""
    _save(client, "tok-A")
    assert client.get("/api/mingju/export", params={"id": "tok-A"}).status_code == 403
    assert client.get("/api/mingju/export", params={"id": "tok-A"},
                      headers={"X-Owner-Token": "tok-B"}).status_code == 404
    assert client.get("/api/mingju/export", params={"id": "tok-A"},
                      headers={"X-Owner-Token": "tok-A"}).status_code == 200


def test_import_cannot_overwrite_others_and_needs_token(client):
    """导入的两条硬要求：必须带令牌；且**不能**用它覆盖别人的档案。

    原先该端点没有 request 参数、没有任何归属校验，而 import_profile 按备份文件里的 id
    做 ON CONFLICT DO UPDATE —— 于是"知道某个 id"就能把别人的出生信息改成任意值。
    这是数据破坏，比泄露更狠，所以单独一条测试盯着。
    """
    _save(client, "tok-A")
    forged = {"data": {"schema_version": 1,
                       "profile": {"id": "tok-A", "birth": dict(BIRTH, year=1904)}}}
    # 无令牌：拒绝
    assert client.post("/api/mingju/import", json=forged).status_code == 403
    # 有令牌（他人）：会成功，但**只能写进自己名下**，A 的档案不受影响
    r = client.post("/api/mingju/import", json=forged, headers={"X-Owner-Token": "tok-B"})
    assert r.status_code == 200
    a = client.get("/api/mingju/profile", params={"id": "tok-A"}, headers={"X-Owner-Token": "tok-A"})
    assert a.json()["birth"]["year"] == 1990, "A 的档案被他人的导入覆盖了"
    b = client.get("/api/mingju/profile", params={"id": "tok-B"}, headers={"X-Owner-Token": "tok-B"})
    assert b.status_code == 200 and b.json()["birth"]["year"] == 1904


def test_backup_roundtrip_moves_everything_to_new_device(client):
    """搬家真的能用：导出 → 换设备导入 → 档案/记录/台账都归新设备。

    同时钉住"备份只搬数据、不搬凭证"：新设备的令牌仍是自己的，
    拿到别人的备份文件也无法冒用他的归属。
    """
    _save(client, "dev-old")
    records.add("meihua", "旧设备的一条卦", "", "问", {"ai_text": "x"}, owner="dev-old")
    log_id = decision_log.append_check({"owner": "dev-old", "kind": "check", "question": "问",
                                        "claims": [{"id": "c1"}]})
    decision_log.add_claim_feedback(log_id, "c1", "应验", owner="dev-old")

    backup = client.get("/api/mingju/export", params={"id": "dev-old"},
                        headers={"X-Owner-Token": "dev-old"}).json()
    assert "id" not in backup["profile"]           # 档案主键 = 令牌，不写进文件
    assert len(backup["records"]) == 1 and len(backup["ledger"]["logs"]) == 1
    assert len(backup["ledger"]["claim_feedback"]) == 1
    # 备份里不得出现任何等于令牌的凭证字段（文件被解开也不等于交出账号）
    assert "dev-old" not in json.dumps(backup, ensure_ascii=False)
    assert all(r["owner"] == "" for r in backup["records"])
    assert all(r["owner"] == "" and r["profile_id"] == "" for r in backup["ledger"]["logs"])
    # …但本地行号 id 必须保留：claim_feedback 的重映射要靠它
    assert backup["ledger"]["logs"][0]["id"] and backup["ledger"]["claim_feedback"][0]["log_id"]

    # 新设备：自己的令牌 + 这份备份
    r = client.post("/api/mingju/import", json={"data": backup},
                    headers={"X-Owner-Token": "dev-new"})
    assert r.status_code == 200
    assert r.json()["records"] == 1 and r.json()["ledger"]["logs"] == 1

    # 新设备看得见
    assert client.get("/api/mingju/profile", params={"id": "dev-new"},
                      headers={"X-Owner-Token": "dev-new"}).status_code == 200
    assert [x["title"] for x in records.list_all(owner="dev-new")] == ["旧设备的一条卦"]
    # 台账与断言反馈一起过来，且反馈没挂错行
    new_logs = decision_log.recent(10, "dev-new")
    assert [x["question"] for x in new_logs] == ["问"]
    assert new_logs[0]["owner"] == "dev-new" and new_logs[0]["profile_id"] == "dev-new"
    assert decision_log.feedback_of(new_logs[0]["id"], "dev-new") == {"c1": "应验"}
    # 老设备的归属仍然独立：它的台账没被搬走，也没被改成新设备
    old = decision_log.recent(10, "dev-old")
    assert [x["id"] for x in old] == [log_id] and old[0]["owner"] == "dev-old"


def test_check_endpoint_needs_token_and_never_writes_shared_bucket(client):
    """校验端点必须带令牌，且**任何情况下**都不会产生共享归属的数据。

    这里原先的写法是"无令牌照常算、只是不落账"，当时的理由是"校验是无状态计算，
    不该为了补洞砍功能"。但那个折中本身有害：返回 200 却不落账，意味着这个用户的
    断言清单永远不会出现在他自己的反馈页里——**功能静默少了一半**，比明确报错更难查。
    而现在令牌在会话内恒定（common/owner.ts 的内存缓存），真实用户不会处于"无令牌"状态，
    所以直接 require_owner 既安全又不伤用户。

    同时钉住数据层的不变量：`append_check` 拒绝无归属写入，因此这张表里不可能出现
    谁都读不到的孤儿行，也不可能出现"所有无令牌请求共用一个桶"（那个桶任何人都读得到）。
    """
    main_mod = __import__("main")
    payload = {"profile_id": "", "question": "无令牌的问事", "tier": "M", "remedy": {"R": "木"}}
    assert client.post("/api/mingju/check", json=payload).status_code == 403
    import decision_log as dl
    assert dl.recent(50, main_mod.ANON_OWNER) == []
    # 带令牌 → 正常，且落在自己名下
    r = client.post("/api/mingju/check", json=payload, headers={"X-Owner-Token": "tok-A"})
    assert r.status_code == 200
    assert [x["owner"] for x in dl.recent(50, "tok-A")] == ["tok-A"]


def test_append_check_refuses_ownerless_write(dbs):
    """数据层不变量：决策日志不存在"无主"这个合法状态。

    原先 append_check 用 `owner or profile_id or ""` 兜底，而 profile_id 是客户端可控值——
    "客户端字段变成归属"这条错路又出现在了数据层。现在 owner 必须显式给出。
    """
    with pytest.raises(ValueError):
        decision_log.append_check({"profile_id": "tok-VICTIM", "question": "x"})
    with pytest.raises(ValueError):
        decision_log.append_check({"owner": "__anon__", "question": "x"})
    assert decision_log.recent(10, "tok-VICTIM") == []


def test_check_profile_id_must_be_own(client):
    """`profile_id` 只接受自己的：档案主键就是令牌，所以它是**凭证别名**，不是普通参数。

    IDOR 的前置条件就此堵死——否则一旦档案 id 不再等于令牌、或 id 出现在某个链接里，
    "无令牌 + 知道 id" 就能拿回该命局的派生结论（F/J/T0 与四柱）。
    """
    _save(client, "tok-A")
    payload = {"profile_id": "tok-A", "question": "x", "tier": "M", "remedy": {"R": "木"}}
    assert client.post("/api/mingju/check", json=payload,
                       headers={"X-Owner-Token": "tok-B"}).status_code == 404
    assert client.post("/api/mingju/check", json=payload,
                       headers={"X-Owner-Token": "tok-A"}).status_code == 200
    # 不带 profile_id（纯卦侧校验）仍然可以
    assert client.post("/api/mingju/check", json={"question": "x", "tier": "M", "remedy": {"R": "木"}},
                       headers={"X-Owner-Token": "tok-A"}).status_code == 200


def test_bazi_log_requires_token_and_is_readable_back(client):
    """八字排盘留痕：必须带令牌，且**作者自己读得回来**。

    原实现无令牌校验、行落成 owner=''，于是每次排盘的留痕静默消失（功能自我否定），
    同时给陌生人留了一个无限制的共享表写入口。这两件事是同一个 bug 的两面。
    """
    assert client.post("/api/mingju/bazi/log",
                       json={"summary": {"pillars": "甲子 乙丑"}}).status_code == 403
    r = client.post("/api/mingju/bazi/log", json={"summary": {"pillars": "甲子 乙丑"}},
                    headers={"X-Owner-Token": "tok-A"})
    assert r.status_code == 200
    logs = client.get("/api/mingju/logs", headers={"X-Owner-Token": "tok-A"}).json()["logs"]
    assert [x["kind"] for x in logs] == ["bazi"]
    assert logs[0]["extra_json"] and "甲子 乙丑" in logs[0]["extra_json"]


def test_bazi_log_rejects_oversized_summary(client):
    """排盘快照本来就几百字节；过大时截断而不是原样入库（防匿名膨胀磁盘）。"""
    big = {"blob": "x" * 40000}
    r = client.post("/api/mingju/bazi/log", json={"summary": big},
                    headers={"X-Owner-Token": "tok-A"})
    assert r.status_code == 200
    logs = client.get("/api/mingju/logs", headers={"X-Owner-Token": "tok-A"}).json()["logs"]
    assert "truncated" in (logs[0]["extra_json"] or "")


def test_admin_endpoints_require_admin_token(client, monkeypatch):
    """校准提案的生成/批准与留言收件箱必须是站长端点。

    最要紧的是 `decide`：`decided_by` 来自请求体，公开时任何人都能以任意署名把提案标成
    "已生效"——而"阈值只经人工批准、绝不自动改数"正是本产品的立身之本，
    一条可伪造的批准记录等于让这条承诺作废。
    未配置 ADMIN_TOKEN 时端点关闭（503）而非放开：配置缺失应当表现为"用不了"。
    """
    import main as m
    monkeypatch.setattr(m, "ADMIN_TOKEN", "")
    assert client.get("/api/feedback/notes").status_code == 503
    assert client.post("/api/feedback/calibration/analyze").status_code == 503
    assert client.post("/api/feedback/calibration/decide",
                       json={"id": 1, "status": "已生效"}).status_code == 503
    monkeypatch.setattr(m, "ADMIN_TOKEN", "s3cret-admin")
    assert client.get("/api/feedback/notes").status_code == 403
    assert client.post("/api/feedback/calibration/analyze").status_code == 403
    assert client.post("/api/feedback/calibration/decide",
                       json={"id": 1, "status": "已生效"}).status_code == 403
    assert client.get("/api/feedback/notes",
                      headers={"X-Admin-Token": "s3cret-admin"}).status_code == 200


def test_public_calibration_view_hides_log_ids(client):
    """校准台账**有意公开**（这是"透明可查"这条承诺），但不带 log_ids。

    行号是内部标识，对用户没有任何用处，留着只是把他人的样本编号漏出去。
    """
    r = client.get("/api/feedback/calibration")
    assert r.status_code == 200
    body = r.json()
    assert "guardrails" in body and "proposals" in body
    assert all("log_ids" not in b for b in body.get("boundary") or [])


# ---------- 7. 断言回执码（长期反馈的窄凭证） ----------

def test_receipt_allows_answering_without_token(client):
    """回执码的核心用途：**令牌没了也能作答**。

    长窗口反馈（择日按周、岁运跨月甚至跨年）在 iOS 上必然丢令牌（Safari 7 天清空
    本机存储），届时服务端台账还在却认不出是谁。回执码就是为这一刻存在的窄凭证。
    """
    _save(client, "dev-1")
    log_id = decision_log.append_check({"owner": "dev-1", "kind": "check", "profile_id": "dev-1",
                                        "question": "问", "claims": [{"id": "c1"}]})
    r = client.post("/api/feedback/claim/receipt", json={"log_id": log_id, "claim_id": "c1"},
                    headers={"X-Owner-Token": "dev-1"})
    assert r.status_code == 200
    rc = r.json()["receipt"]
    assert len(rc) >= 20
    # 完全不带令牌，只凭回执码作答
    ok = client.post("/api/feedback/claim", json={"verdict": "应验", "receipt": rc})
    assert ok.status_code == 200, ok.text
    assert decision_log.feedback_of(log_id, "dev-1") == {"c1": "应验"}
    # 回执落地页只回这一条断言，且不需要令牌
    got = client.get("/api/feedback/claim", params={"receipt": rc})
    assert got.status_code == 200
    body = got.json()
    assert body["claim"]["id"] == "c1" and body["feedback"] == "应验"
    assert "question" not in body and "claims" not in body     # 有意不返回问题原文与其它断言


def test_receipt_is_idempotent_and_owned(client):
    """回执码幂等（同一断言恒同一枚，否则"再次加入日历"会留一串死链），且不能跨人签发。"""
    _save(client, "dev-1")
    log_id = decision_log.append_check({"owner": "dev-1", "kind": "check", "profile_id": "dev-1",
                                        "claims": [{"id": "c1"}]})
    h = {"X-Owner-Token": "dev-1"}
    a = client.post("/api/feedback/claim/receipt", json={"log_id": log_id, "claim_id": "c1"}, headers=h).json()
    b = client.post("/api/feedback/claim/receipt", json={"log_id": log_id, "claim_id": "c1"}, headers=h).json()
    assert a["receipt"] == b["receipt"]
    # 别人签不出来
    assert client.post("/api/feedback/claim/receipt", json={"log_id": log_id, "claim_id": "c1"},
                       headers={"X-Owner-Token": "dev-2"}).status_code == 404
    # 无令牌更不行
    assert client.post("/api/feedback/claim/receipt",
                       json={"log_id": log_id, "claim_id": "c1"}).status_code == 403


def test_receipt_ignores_client_supplied_target(client):
    """带 receipt 时，客户端传的 log_id/claim_id **一律忽略**——归属与目标都取自回执行。

    否则"客户端字段决定改哪条"这条错路又从反馈端点回来了：持一枚自己那条的回执码，
    再把 log_id 换成别人的，就能改别人的裁定。
    """
    _save(client, "dev-1")
    victim = decision_log.append_check({"owner": "dev-1", "kind": "check", "profile_id": "dev-1",
                                        "claims": [{"id": "c1"}, {"id": "c2"}]})
    other = decision_log.append_check({"owner": "dev-2", "kind": "check", "profile_id": "dev-2",
                                       "claims": [{"id": "c1"}]})
    rc = client.post("/api/feedback/claim/receipt", json={"log_id": victim, "claim_id": "c1"},
                     headers={"X-Owner-Token": "dev-1"}).json()["receipt"]
    # 拿着 c1 的回执码，却把目标写成别人的日志/别的断言
    r = client.post("/api/feedback/claim", json={"verdict": "应验", "receipt": rc,
                                                 "log_id": other, "claim_id": "c1"})
    assert r.status_code == 200
    assert decision_log.feedback_of(victim, "dev-1") == {"c1": "应验"}    # 改的是自己那条
    assert decision_log.feedback_of(other, "dev-2") == {}                 # 别人的没被碰
    assert decision_log.feedback_of(victim, "dev-1").get("c2") is None    # 同次校验的别的断言也没被碰


def test_forged_receipt_rejected(client):
    """伪造/超长回执码一律 404，且不产生任何写入。

    空回执码单列：它不等于"无效凭证"，而等于"没给凭证"——此时走令牌那条路，
    于是无令牌请求得到 403（缺少归属令牌）而不是 404。这个区分有意义：
    403 告诉用户"你需要带上身份"，404 会让人以为链接坏了。
    """
    _save(client, "dev-1")
    log_id = decision_log.append_check({"owner": "dev-1", "kind": "check", "profile_id": "dev-1",
                                        "claims": [{"id": "c1"}]})
    for bad in ("nope", "x" * 200):
        assert client.post("/api/feedback/claim",
                           json={"verdict": "应验", "receipt": bad}).status_code == 404
    assert client.post("/api/feedback/claim",
                       json={"verdict": "应验", "receipt": ""}).status_code == 403
    assert client.get("/api/feedback/claim", params={"receipt": "nope"}).status_code == 404
    assert decision_log.feedback_of(log_id, "dev-1") == {}


def test_receipt_not_in_backup(client):
    """回执码**不进备份**：它是凭证，而备份文件只搬数据、不搬凭证（同 R12-f 的规则）。

    导入后重新签发即可，所以不带上没有任何损失。
    """
    _save(client, "dev-1")
    log_id = decision_log.append_check({"owner": "dev-1", "kind": "check", "profile_id": "dev-1",
                                        "claims": [{"id": "c1"}]})
    rc = client.post("/api/feedback/claim/receipt", json={"log_id": log_id, "claim_id": "c1"},
                     headers={"X-Owner-Token": "dev-1"}).json()["receipt"]
    backup = client.get("/api/mingju/export", params={"id": "dev-1"},
                        headers={"X-Owner-Token": "dev-1"}).json()
    assert rc not in json.dumps(backup, ensure_ascii=False)
    assert "receipt" not in json.dumps(backup, ensure_ascii=False)


def test_feedback_endpoints_need_token(client):
    """反馈写入与"待反馈"列表都必须带令牌（否则共享桶里能读到别人的待办）。"""
    assert client.post("/api/mingju/feedback",
                       json={"log_id": 1, "outcome": "应验"}).status_code == 403
    assert client.get("/api/feedback/recent").status_code == 403
    assert client.get("/api/mingju/logs").status_code == 403


# ---------- 6. 备份内容不丢东西 ----------

def test_export_includes_trash(dbs):
    """备份必须含回收站：它也是"用户还能看见的东西"，漏掉等于备份悄悄丢数据。"""
    a = dbs.add("meihua", "留下", "", "", {}, owner="tok-A")
    b = dbs.add("meihua", "删了但可恢复", "", "", {}, owner="tok-A")
    dbs.remove(b["id"], "tok-A")
    titles = sorted(r["title"] for r in dbs.export_all("tok-A"))
    assert titles == ["删了但可恢复", "留下"]


def test_import_rewrites_ids_and_owner(dbs):
    """导入的记录：id 重分配（不撞本地既有行）、owner 改写为导入者、内容与删除态保留。"""
    dbs.add("meihua", "本机原有", "", "", {}, owner="tok-new")
    backup = [dict(r, title="从备份来", deleted_at="") for r in dbs.export_all("tok-old")]
    assert backup == []                                  # 老归属没有记录
    src = dbs.add("meihua", "从备份来", "副标题", "问", {"k": 1}, owner="tok-old")
    dbs.remove(src["id"], "tok-old")
    payload = dbs.export_all("tok-old")
    assert dbs.import_all(payload, "tok-new") == 1
    # 导入的那条是**软删除态**，所以出现在回收站而不是列表里（删除状态原样保留）
    assert [r["title"] for r in dbs.list_deleted(owner="tok-new")] == ["从备份来"]
    assert dbs.list_all(owner="tok-old") == []                          # 归属改写
    assert dbs.list_all(owner="") == []
    # 本机原有记录没被覆盖，且 id 是重分配的（不与备份里的 id 撞车）
    rows = dbs.list_all(owner="tok-new")
    assert [r["title"] for r in rows] == ["本机原有"]
    assert rows[0]["id"] != payload[0]["id"] or rows[0]["title"] != payload[0]["title"]


def test_ledger_import_remaps_claim_feedback(dbs):
    """台账导入必须重映射 log_id，否则断言反馈会挂到别人的日志上。"""
    la = decision_log.append_check({"owner": "tok-old", "kind": "check", "question": "老问",
                                    "claims": [{"id": "c1"}]})
    decision_log.add_claim_feedback(la, "c1", "未验", note="后来没成", owner="tok-old")
    data = decision_log.export_all("tok-old")
    # 新归属下先有别的日志，制造 id 冲突的可能
    lb = decision_log.append_check({"owner": "tok-new", "kind": "check", "question": "新问",
                                    "claims": [{"id": "cX"}]})
    out = decision_log.import_all(data, "tok-new")
    assert out == {"logs": 1, "feedback": 1}
    logs = {x["question"]: x["id"] for x in decision_log.recent(10, "tok-new")}
    assert set(logs) == {"老问", "新问"}
    assert decision_log.feedback_of(logs["老问"], "tok-new") == {"c1": "未验"}
    assert decision_log.feedback_of(logs["新问"], "tok-new") == {}     # 没被错误挂上
    assert decision_log.feedback_of(lb, "tok-new") == {}


# ---------- 整张流动表入库（站长 2026-09-19 定：存整张，不存摘要） ----------

_FLOW = [{"wx": "金", "state": "弱", "rows": [
            {"state": "弱", "active": True,
             "cells": {"克我": {"grade": "宜", "note": "…", "src": "滴天髓",
                               "conflict_suppressed": "静态格「忌」与边态「侮」同源，非方向冲突，故不告警"}}},
            {"state": "旺极(从格)", "active": False, "cells": {}}]}]


def test_flow_table_is_stored_and_readable(dbs):
    """整张流动表要存得下、读得回。

    存它的唯一理由是 R5 那句"不静默"——`conflict_suppressed`（为何这次不告警）
    此前只活在接口返回里，页面一关就没了。所以这条测试盯的就是那一格能不能事后取回。
    """
    lid = decision_log.append_check({"owner": "tok-A", "kind": "check",
                                     "question": "看流动表", "flow": _FLOW})
    got = decision_log.flow_of(lid, "tok-A")
    assert got == _FLOW
    cell = got[0]["rows"][0]["cells"]["克我"]
    assert "不告警" in cell["conflict_suppressed"]


def test_flow_table_absent_is_empty_not_error(dbs):
    """旧行（没有 flow_json）读出来是空表，不是异常——加列迁移不回头补历史数据。"""
    lid = decision_log.append_check({"owner": "tok-A", "kind": "check", "question": "老行"})
    assert decision_log.flow_of(lid, "tok-A") == []


def test_flow_table_is_owner_scoped(dbs):
    """整表也是本人数据：别人拿着 id 也读不到，且与"不存在"同形。"""
    lid = decision_log.append_check({"owner": "tok-A", "kind": "check", "flow": _FLOW})
    assert decision_log.flow_of(lid, "tok-B") == []
    assert decision_log.flow_of(lid, "") == []
    assert decision_log.flow_of(999999, "tok-A") == []


def test_recent_omits_flow_table(dbs):
    """**列表不带整表**：一张几 KB，而台账一次给 60 行——带上它等于每开一次
    "我的记录"就多传几百 KB 的、绝大多数人永远不会展开的数据。"""
    decision_log.append_check({"owner": "tok-A", "kind": "check", "flow": _FLOW})
    rows = decision_log.recent(10, "tok-A")
    assert rows and all("flow_json" not in r for r in rows)
    # 但别的列一个都不能少（列名是 PRAGMA 现取的，漏列就是"存了却读不出"）
    assert "claims_json" in rows[0] and "extra_json" in rows[0] and "owner" in rows[0]


def test_backup_carries_flow_table(dbs):
    """备份必须把整表带走。导出用 `SELECT *`、导入按 PRAGMA 动态取列，
    所以这条**应当自动成立**——但"应当自动成立"正是最该锁住的东西：
    哪天有人为了瘦身把导出改成显式列清单，整表就会在备份里静默消失。"""
    lid = decision_log.append_check({"owner": "tok-old", "kind": "check", "flow": _FLOW})
    data = decision_log.export_all("tok-old")
    assert decision_log.import_all(data, "tok-new")["logs"] == 1
    new = [r for r in decision_log.recent(10, "tok-new")][0]
    assert decision_log.flow_of(new["id"], "tok-new") == _FLOW
    assert decision_log.flow_of(new["id"], "tok-new")[0]["wx"] == "金"


def test_check_endpoint_persists_flow_table_end_to_end(client):
    """**整条链路**：起卦校验落库时把整张流动表带上，再由读端点取回。

    上面几条测的是数据层（直接调 append_check / flow_of）。这一条走 HTTP——
    数据层全过而端点忘了传 `flow=`，是"存了却全是空表"的典型漏法，
    而那种漏法在上面几条测试里一个字都看不出来。
    """
    _save(client, "tok-A")
    payload = {"profile_id": "tok-A", "question": "这周谈合作", "tier": "M",
               "remedy": {"R": "木"}, "source": "meihua"}
    r = client.post("/api/mingju/check", json=payload, headers={"X-Owner-Token": "tok-A"})
    assert r.status_code == 200, r.text
    lid = r.json()["log_id"]
    assert lid, "带令牌的校验应当落账"

    flow = client.get(f"/api/mingju/logs/flow?id={lid}",
                      headers={"X-Owner-Token": "tok-A"}).json()["flow"]
    assert flow, "端点没把流动表传进 append_check"
    # 档位是 M，而 M 档含屋宅维度 → 至少要有 target 五行与状态
    assert all("wx" in f and "rows" in f for f in flow)
    # 列表侧仍不带整表
    logs = client.get("/api/mingju/logs", headers={"X-Owner-Token": "tok-A"}).json()["logs"]
    assert logs and all("flow_json" not in x for x in logs)


def test_log_flow_endpoint_is_owner_scoped(client):
    """整表读端点同样只认令牌：别人拿着 id 读不到，且与不存在同形。"""
    _save(client, "tok-A")
    r = client.post("/api/mingju/check",
                    json={"profile_id": "tok-A", "question": "x", "tier": "M",
                          "remedy": {"R": "木"}},
                    headers={"X-Owner-Token": "tok-A"})
    lid = r.json()["log_id"]
    assert client.get(f"/api/mingju/logs/flow?id={lid}",
                      headers={"X-Owner-Token": "tok-B"}).json()["flow"] == []
    assert client.get(f"/api/mingju/logs/flow?id={lid}").status_code == 403

