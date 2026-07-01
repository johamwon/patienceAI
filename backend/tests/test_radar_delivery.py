from datetime import datetime
from pathlib import Path

from app.models.schemas import PushDigest, PushDigestItem
from app.services.radar.contact_store import SQLiteContactStore
from app.services.radar.delivery.wechat import WeChatChannel
from app.services.radar.radar_service import RadarService
from app.services.radar.subscription_store import SQLiteSubscriptionStore


class RecordingChannel:
    def __init__(self, name: str, fail: bool = False, available: bool = True):
        self.name = name
        self.fail = fail
        self.available = available
        self.calls: list[str] = []

    def is_available(self) -> bool:
        return self.available

    def deliver(self, anon_user_id: str, digest):
        self.calls.append(anon_user_id)
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        return True


def _service(tmp_path: Path, channels: dict):
    return RadarService(
        subscriptions=SQLiteSubscriptionStore(tmp_path / "subscriptions.db"),
        contacts=SQLiteContactStore(tmp_path / "contacts.db"),
        channels=channels,
        search_client=None,
        digest_llm=None,
    )


def _digest():
    return PushDigest(
        disease_keyword="肺癌",
        items=[
            PushDigestItem(
                summary="群体研究进展摘要。",
                research_stage="breakthrough_rct",
                evidence_level="high",
            )
        ],
        generated_at=datetime.now().isoformat(),
    )


def test_delivery_failure_does_not_block_other_enabled_channels(tmp_path):
    in_app = RecordingChannel("in_app")
    email = RecordingChannel("email", fail=True)
    service = _service(tmp_path, {"in_app": in_app, "email": email})
    service.set_channel("anon", "in_app")
    service.set_channel("anon", "email", "a@example.com")

    results = service._deliver_to_enabled_channels("anon", _digest())

    assert in_app.calls == ["anon"]
    assert email.calls == ["anon"]
    assert any(r.channel == "in_app" and r.delivered for r in results)
    assert any(r.channel == "email" and r.error for r in results)


def test_disabled_channel_is_not_used(tmp_path):
    in_app = RecordingChannel("in_app")
    email = RecordingChannel("email")
    service = _service(tmp_path, {"in_app": in_app, "email": email})
    service.set_channel("anon", "in_app")

    service._deliver_to_enabled_channels("anon", _digest())

    assert in_app.calls == ["anon"]
    assert email.calls == []


def test_wechat_placeholder_degrades_gracefully():
    channel = WeChatChannel()
    assert channel.is_available() is False
    assert channel.deliver("anon", _digest()) is False
