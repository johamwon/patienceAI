from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services.radar.contact_store import SQLiteContactStore
from app.services.radar.radar_service import RadarService
from app.services.radar.subscription_store import SQLiteSubscriptionStore


class RecordingChannel:
    name = "in_app"

    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def deliver(self, anon_user_id, digest):
        self.calls += 1
        return True


class SearchClient:
    def __init__(self):
        self.calls = 0

    def search_multi_queries(self, pairs, max_results_per_source=10):
        self.calls += 1
        return [
            {
                "id": f"ev-{self.calls}",
                "title": "Phase III randomized controlled trial",
                "source_type": "trial",
                "evidence_level": "high",
                "publish_date": datetime.now().date().isoformat(),
                "nct_id": f"NCT{self.calls:08d}",
            }
        ]


def _service(tmp_path: Path, channel=None, search_client=None):
    return RadarService(
        subscriptions=SQLiteSubscriptionStore(tmp_path / "subscriptions.db"),
        contacts=SQLiteContactStore(tmp_path / "contacts.db"),
        channels={"in_app": channel or RecordingChannel()},
        search_client=search_client or SearchClient(),
        digest_llm=None,
    )


@pytest.mark.asyncio
async def test_subscribe_idempotent_and_no_progress_sends_nothing(tmp_path):
    channel = RecordingChannel()
    service = _service(tmp_path, channel=channel)
    s1 = service.subscribe("anon", "肺癌")
    s2 = service.subscribe("anon", "肺癌")
    service.set_channel("anon", "in_app")

    assert s1.id == s2.id
    result = await service.process_subscription(
        s1,
        evidences=[
            {
                "id": "old",
                "title": "Old guideline",
                "source_type": "guide",
                "evidence_level": "high",
                "publish_date": (datetime.now() - timedelta(days=90)).date().isoformat(),
            }
        ],
    )

    assert result.new_count == 0
    assert channel.calls == 0


@pytest.mark.asyncio
async def test_process_subscription_delivers_once_and_dedups(tmp_path):
    channel = RecordingChannel()
    service = _service(tmp_path, channel=channel)
    sub = service.subscribe("anon", "肺癌")
    service.set_channel("anon", "in_app")
    evidence = {
        "nct_id": "NCT12345678",
        "title": "Phase III randomized controlled trial",
        "source_type": "trial",
        "evidence_level": "high",
        "publish_date": datetime.now().date().isoformat(),
    }

    first = await service.process_subscription(sub, evidences=[evidence])
    second = await service.process_subscription(sub, evidences=[dict(evidence)])

    assert first.delivered is True
    assert second.delivered is False
    assert channel.calls == 1


@pytest.mark.asyncio
async def test_revoke_excludes_subscription_from_patrol(tmp_path):
    search = SearchClient()
    service = _service(tmp_path, search_client=search)
    sub = service.subscribe("anon", "肺癌")
    service.revoke(sub.id)

    report = await service.run_patrol_once()

    assert report.processed == 0
    assert search.calls == 0
