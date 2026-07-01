from pathlib import Path

from fastapi.testclient import TestClient

from app.services.radar.contact_store import SQLiteContactStore
from app.services.radar.radar_service import RadarService
from app.services.radar.subscription_store import SQLiteSubscriptionStore
from backend.app.api import radar as radar_module
from backend.app.main import app


class NoopChannel:
    name = "in_app"

    def is_available(self):
        return True

    def deliver(self, anon_user_id, digest):
        return True


def _patch_service(monkeypatch, tmp_path: Path):
    service = RadarService(
        subscriptions=SQLiteSubscriptionStore(tmp_path / "subscriptions.db"),
        contacts=SQLiteContactStore(tmp_path / "contacts.db"),
        channels={"in_app": NoopChannel(), "email": NoopChannel(), "wechat": NoopChannel()},
        search_client=None,
        digest_llm=None,
    )
    monkeypatch.setattr(radar_module, "radar_service", service)
    return service


def test_radar_subscribe_email_channel_messages_and_delete(monkeypatch, tmp_path):
    service = _patch_service(monkeypatch, tmp_path)
    client = TestClient(app)

    resp = client.post(
        "/api/v1/radar/subscribe",
        json={"anon_user_id": "anon", "disease_keyword": "肺癌"},
    )
    assert resp.status_code == 200
    sub_id = resp.json()["id"]

    assert client.get("/api/v1/radar/subscriptions?anon_user_id=anon").json()[0]["id"] == sub_id
    channels = client.get("/api/v1/radar/channels?anon_user_id=anon").json()
    assert channels["in_app"] is False
    assert channels["email"] is False

    channel_resp = client.post(
        "/api/v1/radar/channels",
        json={"anon_user_id": "anon", "channel": "email", "contact": "patient@example.com"},
    )
    assert channel_resp.status_code == 200
    assert client.get("/api/v1/radar/channels?anon_user_id=anon").json()["email"] is True

    service.subscriptions.add_inapp_message("anon", {"disease_keyword": "肺癌", "items": [], "generated_at": "now", "is_demo": False})
    assert len(client.get("/api/v1/radar/messages?anon_user_id=anon").json()) == 1

    delete_resp = client.delete("/api/v1/radar/user/anon")
    assert delete_resp.status_code == 200
    assert client.get("/api/v1/radar/subscriptions?anon_user_id=anon").json() == []


def test_demo_trigger_hidden_when_disabled(monkeypatch, tmp_path):
    _patch_service(monkeypatch, tmp_path)
    monkeypatch.setenv("RADAR_DEMO_MODE", "false")
    client = TestClient(app)

    resp = client.post("/api/v1/radar/demo/trigger", json={"subscription_id": "nope"})

    assert resp.status_code == 404
