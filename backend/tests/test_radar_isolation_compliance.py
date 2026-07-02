import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app.services.radar.contact_store import SQLiteContactStore
from app.services.radar.radar_service import RadarService
from app.services.radar.subscription_store import SQLiteSubscriptionStore


class InAppOnly:
    name = "in_app"

    def is_available(self):
        return True

    def deliver(self, anon_user_id, digest):
        return True


def _all_db_text(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        text = []
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            for row in conn.execute(f"SELECT * FROM {table}").fetchall():
                text.extend(str(cell) for cell in row)
        return " ".join(text)
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_subscription_db_stays_pii_free_after_end_to_end_flow(tmp_path):
    sub_db = tmp_path / "subscriptions.db"
    contact_db = tmp_path / "contacts.db"
    service = RadarService(
        subscriptions=SQLiteSubscriptionStore(sub_db),
        contacts=SQLiteContactStore(contact_db),
        channels={"in_app": InAppOnly()},
        search_client=None,
        digest_llm=None,
    )
    sub = service.subscribe("anon", "肺癌")
    service.set_channel("anon", "in_app")
    service.contacts.set_contact("anon", "email", "patient@example.com")

    await service.process_subscription(
        sub,
        evidences=[
            {
                "id": "ev",
                "title": "Phase I study",
                "source_type": "trial",
                "evidence_level": "moderate",
                "publish_date": datetime.now().date().isoformat(),
                "nct_id": "NCT12345678",
            }
        ],
    )

    sub_text = _all_db_text(sub_db)
    contact_text = _all_db_text(contact_db)
    assert "patient@example.com" not in sub_text
    assert "@" not in sub_text
    assert "肺癌" not in contact_text


@pytest.mark.asyncio
async def test_patient_facing_digest_has_no_diagnosis_or_prescription(tmp_path, make_mock_llm_client):
    service = RadarService(
        subscriptions=SQLiteSubscriptionStore(tmp_path / "subscriptions.db"),
        contacts=SQLiteContactStore(tmp_path / "contacts.db"),
        channels={"in_app": InAppOnly()},
        search_client=None,
        digest_llm=make_mock_llm_client(response="你患了肺癌。建议你服用某药每日10mg。群体研究仍有不确定性。"),
    )
    sub = service.subscribe("anon", "肺癌")
    service.set_channel("anon", "in_app")

    result = await service.process_subscription(
        sub,
        evidences=[
            {
                "id": "ev",
                "title": "Phase I study",
                "source_type": "trial",
                "evidence_level": "moderate",
                "publish_date": datetime.now().date().isoformat(),
                "nct_id": "NCT12345678",
            }
        ],
    )

    summary = result.digest.items[0].summary
    assert "你患了" not in summary
    assert "每日10mg" not in summary
    assert result.digest.items[0].uncertainty_note
