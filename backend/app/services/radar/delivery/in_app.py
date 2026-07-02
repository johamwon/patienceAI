"""In-app delivery channel. Zero PII; writes by anonymous user id only."""

from __future__ import annotations

from ....models.schemas import PushDigest
from .base import DeliveryChannel
from ..subscription_store import SubscriptionStore, subscription_store


class InAppChannel(DeliveryChannel):
    name = "in_app"

    def __init__(self, store: SubscriptionStore = subscription_store):
        self.store = store

    def is_available(self) -> bool:
        return True

    def deliver(self, anon_user_id: str, digest: PushDigest) -> bool:
        payload = digest.model_dump() if hasattr(digest, "model_dump") else dict(digest)
        self.store.add_inapp_message(anon_user_id, payload)
        return True
