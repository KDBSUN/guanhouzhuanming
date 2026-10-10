# -*- coding: utf-8 -*-
"""
反馈邮件通知（SMTP）
====================
用途：公测期把"用户留言"与"高价值负反馈（反向/未验）"即时送到站长邮箱，
      免得要登后台才看得到。

安全约束（重要）：
  · 授权码/密码**只从环境变量（backend/.env）读取**，绝不写进代码、绝不进前端；
  · 前端只知道"收件地址"（可公开），发信凭据一律留在服务端；
  · 发信是"尽力而为"：任何失败只返回原因，绝不抛异常打断用户的反馈提交；
  · 在 FastAPI 里请用 run_in_threadpool 调用（smtplib 是阻塞 IO）。

QQ 邮箱：smtp.qq.com，SSL 465（或 STARTTLS 587）；SMTP_PASS 填"授权码"而非登录密码。
"""
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate


def _cfg() -> dict:
    port = int(os.getenv("SMTP_PORT", "465") or 465)
    return {
        "host": (os.getenv("SMTP_HOST") or "").strip(),
        "port": port,
        "ssl": (os.getenv("SMTP_SSL", "1") or "1").strip() not in ("0", "false", "False"),
        "user": (os.getenv("SMTP_USER") or "").strip(),
        "password": os.getenv("SMTP_PASS") or "",      # 授权码：仅来自 .env
        "to": (os.getenv("FEEDBACK_TO") or os.getenv("SMTP_USER") or "").strip(),
        "sender_name": os.getenv("SMTP_SENDER_NAME", "易占·公测反馈"),
    }


def configured() -> bool:
    """是否具备发信条件（缺任一项即视为未配置，功能静默降级为"仅入库"）。"""
    c = _cfg()
    return bool(c["host"] and c["user"] and c["password"] and c["to"])


def send(subject: str, body: str) -> dict:
    """发一封纯文本邮件。返回 {"ok": bool, "reason": str}，绝不抛异常。"""
    c = _cfg()
    if not configured():
        return {"ok": False, "reason": "未配置 SMTP（反馈已入库，仅不发邮件）"}
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((c["sender_name"], c["user"]))
    msg["To"] = c["to"]
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)
    try:
        ctx = ssl.create_default_context()
        if c["ssl"] or c["port"] == 465:
            with smtplib.SMTP_SSL(c["host"], c["port"], context=ctx, timeout=20) as s:
                s.login(c["user"], c["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(c["host"], c["port"], timeout=20) as s:
                s.starttls(context=ctx)
                s.login(c["user"], c["password"])
                s.send_message(msg)
        return {"ok": True, "reason": ""}
    except smtplib.SMTPAuthenticationError as e:
        return {"ok": False, "reason": "SMTP 认证失败（授权码是否正确/是否已过期）：%s" % e}
    except Exception as e:                                  # 网络/超时/证书等
        return {"ok": False, "reason": "%s: %s" % (type(e).__name__, e)}


def feedback_note_mail(text: str, contact: str = "", log_id: int = 0, title: str = "") -> dict:
    """用户留言 → 邮件。"""
    body = [
        "【易占·公测留言】%s" % (title or "（无标题）"),
        "",
        text,
        "",
        "————————————",
        "联系方式：%s" % (contact or "（未留）"),
        "关联记录：#%s" % (log_id or "—"),
        "（本邮件由站点反馈页自动发送；回复时请注意对方可能未留联系方式）",
    ]
    subj = title.strip() or text[:30].replace("\n", " ")
    return send("【易占公测】新留言：%s" % subj, "\n".join(body))


def claim_verdict_mail(question: str, claim_text: str, verdict: str,
                       note: str = "", log_id: int = 0) -> dict:
    """高价值负反馈（反向/未验）→ 邮件。这是校准台账最需要的样本。"""
    body = [
        "【易占·负反馈】用户标记：%s" % verdict,
        "",
        "所问之事：%s" % (question or "（未填）"),
        "被标记的断言：%s" % claim_text,
        "用户补充：%s" % (note or "（无）"),
        "",
        "————————————",
        "记录编号：#%s（可在决策日志/校准台账按此编号回溯当时的规则与权重版本）" % (log_id or "—"),
    ]
    return send("【易占公测】%s：%s" % (verdict, (question or claim_text)[:24]), "\n".join(body))
