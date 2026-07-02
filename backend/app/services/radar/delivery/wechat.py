"""WeChat delivery placeholder.

MVP keeps the interface but degrades gracefully because real WeChat/openclaw
delivery needs account credentials and openid binding outside this demo.
"""

from __future__ import annotations

from ....models.schemas import PushDigest
from .base import DeliveryChannel


class WeChatChannel(DeliveryChannel):
    name = "wechat"

    def is_available(self) -> bool:
        return False

    def deliver(self, anon_user_id: str, digest: PushDigest) -> bool:
        return False
