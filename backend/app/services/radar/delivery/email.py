"""Email delivery channel for Research Radar."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from ....models.schemas import PushDigest
from ..contact_store import ContactStore, contact_store
from .base import DeliveryChannel


class EmailChannel(DeliveryChannel):
    name = "email"

    def __init__(self, contacts: ContactStore = contact_store):
        self.contacts = contacts

    def is_available(self) -> bool:
        return bool(os.getenv("SMTP_HOST"))

    def _render_body(self, digest: PushDigest) -> str:
        prefix = "【演示内容】" if digest.is_demo else ""
        lines = [
            f"{prefix}小光为你关注到 {digest.disease_keyword} 的新研究进展。",
            "",
        ]
        for idx, item in enumerate(digest.items, 1):
            lines.append(f"{idx}. {item.summary}")
            lines.append(f"研究阶段：{item.research_stage}；证据等级：{item.evidence_level}")
            if item.uncertainty_note:
                lines.append(f"不确定性提示：{item.uncertainty_note}")
            if item.source_id:
                lines.append(f"来源标识：{item.source_id}")
            lines.append("")
        lines.append("本内容为医学文献通俗化解释，仅供参考，不构成诊疗建议，不替代医生判断。")
        return "\n".join(lines)

    def deliver(self, anon_user_id: str, digest: PushDigest) -> bool:
        email = self.contacts.get_contact(anon_user_id, self.name)
        if not email:
            raise ValueError("Email channel enabled but no email contact is stored")

        if not self.is_available():
            raise RuntimeError("SMTP_HOST is not configured")

        host = os.getenv("SMTP_HOST", "")
        port = int(os.getenv("SMTP_PORT", "587"))
        username = os.getenv("SMTP_USERNAME", "")
        password = os.getenv("SMTP_PASSWORD", "")
        sender = os.getenv("SMTP_FROM", username or "noreply@localhost")
        use_tls = os.getenv("SMTP_USE_TLS", "true").lower() != "false"

        msg = EmailMessage()
        msg["Subject"] = f"小光研究雷达：{digest.disease_keyword} 有新进展"
        msg["From"] = sender
        msg["To"] = email
        msg.set_content(self._render_body(digest))

        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(msg)
        return True
