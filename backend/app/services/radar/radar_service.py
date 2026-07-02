"""Research Radar orchestration service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ...models.schemas import PushDigest, Subscription
from ..knows_client import knows_client
from ..llm_client import llm_client
from .contact_store import ContactStore, contact_store
from .digest_generator import generate_push_digest
from .delivery.base import DeliveryChannel
from .delivery.email import EmailChannel
from .delivery.in_app import InAppChannel
from .delivery.wechat import WeChatChannel
from .fingerprint import is_new_progress, progress_fingerprint
from .subscription_store import SubscriptionStore, subscription_store


RADAR_SEARCH_SOURCES = ("trial", "meeting", "guide", "paper_en")


def is_demo_mode() -> bool:
    return os.getenv("RADAR_DEMO_MODE", "false").lower() in {"1", "true", "yes", "on"}


@dataclass
class DeliveryResult:
    channel: str
    delivered: bool
    skipped: bool = False
    error: str | None = None


@dataclass
class ProcessResult:
    subscription_id: str
    candidate_count: int = 0
    new_count: int = 0
    delivered: bool = False
    digest: PushDigest | None = None
    delivery_results: list[DeliveryResult] = field(default_factory=list)
    error: str | None = None


@dataclass
class PatrolReport:
    started_at: str
    processed: int = 0
    pushed: int = 0
    skipped: int = 0
    errors: list[dict] = field(default_factory=list)


def _evidence_to_dict(evidence: Any) -> dict:
    if isinstance(evidence, dict):
        return evidence
    if hasattr(evidence, "model_dump"):
        return evidence.model_dump()
    return dict(getattr(evidence, "__dict__", {}) or {})


class RadarService:
    def __init__(
        self,
        subscriptions: SubscriptionStore = subscription_store,
        contacts: ContactStore = contact_store,
        channels: dict[str, DeliveryChannel] | None = None,
        search_client=knows_client,
        digest_llm=llm_client,
    ):
        self.subscriptions = subscriptions
        self.contacts = contacts
        self.search_client = search_client
        self.digest_llm = digest_llm
        self.channels = channels or {
            "in_app": InAppChannel(subscriptions),
            "email": EmailChannel(contacts),
            "wechat": WeChatChannel(),
        }

    def subscribe(self, anon_user_id: str, disease_keyword: str) -> Subscription:
        return self.subscriptions.create(anon_user_id.strip(), disease_keyword.strip())

    def list_subscriptions(self, anon_user_id: str) -> list[Subscription]:
        return self.subscriptions.list_active(anon_user_id)

    def revoke(self, sub_id: str) -> None:
        self.subscriptions.revoke(sub_id)

    def delete(self, sub_id: str) -> None:
        self.subscriptions.delete(sub_id)

    def list_channels(self, anon_user_id: str) -> dict[str, bool]:
        enabled = set(self.subscriptions.list_consents(anon_user_id))
        return {name: name in enabled for name in self.channels}

    def set_channel(self, anon_user_id: str, channel: str, contact: str | None = None) -> None:
        self._validate_channel(channel)
        if channel in {"email", "wechat"}:
            if not contact or not contact.strip():
                raise ValueError(f"{channel} channel requires contact")
            self.contacts.set_contact(anon_user_id, channel, contact.strip())
        self.subscriptions.set_consent(anon_user_id, channel)

    def unset_channel(self, anon_user_id: str, channel: str) -> None:
        self._validate_channel(channel)
        self.subscriptions.unset_consent(anon_user_id, channel)
        if channel in {"email", "wechat"}:
            self.contacts.delete_contact(anon_user_id, channel)

    def delete_all(self, anon_user_id: str) -> None:
        # Requirements prefer service continuity and separate deletion: try both.
        first_error: Exception | None = None
        try:
            self.subscriptions.delete_by_user(anon_user_id)
        except Exception as exc:
            first_error = exc
        try:
            self.contacts.delete_by_user(anon_user_id)
        except Exception as exc:
            if first_error is None:
                first_error = exc
        if first_error:
            raise first_error

    async def run_patrol_once(self) -> PatrolReport:
        report = PatrolReport(started_at=datetime.now().isoformat())
        for sub in self.subscriptions.list_all_active():
            report.processed += 1
            try:
                evidences = self._search_for_subscription(sub)
                result = await self.process_subscription(sub, evidences=evidences)
                if result.delivered:
                    report.pushed += 1
                else:
                    report.skipped += 1
            except Exception as exc:
                report.errors.append(
                    {
                        "subscription_id": sub.id,
                        "error": str(exc),
                        "at": datetime.now().isoformat(),
                    }
                )
                continue
        return report

    async def process_subscription(
        self,
        sub: Subscription,
        *,
        evidences: list[Any] | None = None,
        is_demo: bool = False,
    ) -> ProcessResult:
        result = ProcessResult(subscription_id=sub.id)
        evidence_dicts = [_evidence_to_dict(ev) for ev in (evidences or [])]
        result.candidate_count = len(evidence_dicts)

        new_items: list[dict] = []
        fingerprints: list[str] = []
        for evidence in evidence_dicts:
            if not is_new_progress(evidence):
                continue
            fp = progress_fingerprint(evidence)
            if self.subscriptions.is_delivered(sub.id, fp):
                continue
            new_items.append(evidence)
            fingerprints.append(fp)

        result.new_count = len(new_items)
        if not new_items:
            return result

        digest = await generate_push_digest(
            sub.disease_keyword,
            new_items,
            self.digest_llm,
            is_demo=is_demo,
        )
        result.digest = digest

        delivery_results = self._deliver_to_enabled_channels(sub.anon_user_id, digest)
        result.delivery_results = delivery_results
        result.delivered = any(item.delivered for item in delivery_results)

        if result.delivered:
            for fp in fingerprints:
                self.subscriptions.mark_delivered(sub.id, fp)
        return result

    async def inject_demo_progress(
        self,
        sub_id: str,
        fake_evidences: list[dict] | None = None,
    ) -> ProcessResult:
        if not is_demo_mode():
            raise PermissionError("Radar demo mode is disabled")
        sub = self.subscriptions.get(sub_id)
        if sub is None or sub.status != "active":
            raise ValueError("Subscription not found or inactive")
        evidences = fake_evidences or [self._default_demo_evidence(sub.disease_keyword)]
        return await self.process_subscription(sub, evidences=evidences, is_demo=True)

    def _deliver_to_enabled_channels(
        self,
        anon_user_id: str,
        digest: PushDigest,
    ) -> list[DeliveryResult]:
        results: list[DeliveryResult] = []
        enabled = self.subscriptions.list_consents(anon_user_id)

        for channel_name in enabled:
            channel = self.channels.get(channel_name)
            if channel is None:
                results.append(DeliveryResult(channel_name, delivered=False, skipped=True, error="unknown channel"))
                continue
            if not channel.is_available():
                results.append(DeliveryResult(channel_name, delivered=False, skipped=True))
                continue
            try:
                delivered = bool(channel.deliver(anon_user_id, digest))
                results.append(DeliveryResult(channel_name, delivered=delivered, skipped=not delivered))
            except Exception as exc:
                results.append(DeliveryResult(channel_name, delivered=False, error=str(exc)))
                continue
        return results

    def _search_for_subscription(self, sub: Subscription) -> list[Any]:
        pairs = [(source, sub.disease_keyword) for source in RADAR_SEARCH_SOURCES]
        return self.search_client.search_multi_queries(pairs, max_results_per_source=10)

    def _validate_channel(self, channel: str) -> None:
        if channel not in self.channels:
            raise ValueError(f"Unknown channel: {channel}")

    @staticmethod
    def _default_demo_evidence(disease_keyword: str) -> dict:
        return {
            "id": f"demo-{disease_keyword}",
            "title": f"{disease_keyword} 相关新型治疗策略进入临床研究阶段",
            "abstract": "这是一条用于演示研究雷达推送链路的模拟证据，展示系统如何标注研究阶段和不确定性。",
            "source_type": "trial",
            "evidence_level": "moderate",
            "publish_date": datetime.now().date().isoformat(),
            "nct_id": "NCT12345678",
        }


radar_service = RadarService()
