"""Decision 220-A: POST /api/feedback/testflight-webhook.

Off (404) until configured; a bad signature files nothing; a ping and other
events are accepted and ignored; a repeated delivery files nothing new; a new
submission is stored and handed to the shake report's issue task.
"""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.services import testflight_feedback as tf

SECRET = "w" * 32


@pytest.fixture(autouse=True)
def stub_github_enqueue(monkeypatch):
    scheduled = []
    monkeypatch.setattr("app.routes.feedback._enqueue_bug_report_github_issue",
                        lambda report_id: scheduled.append(report_id))
    return scheduled


@pytest.fixture
def configured(monkeypatch):
    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    monkeypatch.setenv("TESTFLIGHT_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ASC_API_ISSUER_ID", "issuer-1")
    monkeypatch.setenv("ASC_API_KEY_ID", "ABCDE12345")
    monkeypatch.setenv("ASC_API_PRIVATE_KEY", pem)


def _signed(payload):
    body = json.dumps(payload).encode()
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Apple-SIGNATURE": f"hmacsha256={sig}", "Content-Type": "application/json"}


def _event(sid="s1"):
    return {"data": {"type": "betaFeedbackScreenshotSubmissionCreated",
                     "relationships": {"instance": {"data": {"type": tf.SCREENSHOT, "id": sid}}}}}


def _no_prior(mock_db, prior=None):
    result = MagicMock()
    result.scalar_one_or_none = lambda: prior
    mock_db.execute = AsyncMock(return_value=result)


async def test_switched_off_without_its_settings(client, monkeypatch):
    for name in ("TESTFLIGHT_WEBHOOK_SECRET", "ASC_API_ISSUER_ID", "ASC_API_KEY_ID", "ASC_API_PRIVATE_KEY"):
        monkeypatch.delenv(name, raising=False)
    body, headers = _signed(_event())
    resp = await client.post("/api/feedback/testflight-webhook", content=body, headers=headers)
    assert resp.status_code == 404


async def test_a_bad_signature_files_nothing(client, configured, mock_db, stub_github_enqueue):
    body, headers = _signed(_event())
    headers["X-Apple-SIGNATURE"] = "hmacsha256=" + "0" * 64
    resp = await client.post("/api/feedback/testflight-webhook", content=body, headers=headers)
    assert resp.status_code == 401
    assert stub_github_enqueue == []


async def test_a_ping_and_other_events_are_accepted_and_ignored(client, configured, stub_github_enqueue):
    for payload, status in (({"data": {"type": "webhookPingCreated"}}, "ping"),
                            ({"data": {"type": "buildUploadStateUpdated"}}, "ignored")):
        body, headers = _signed(payload)
        resp = await client.post("/api/feedback/testflight-webhook", content=body, headers=headers)
        assert resp.status_code == 200 and resp.json()["status"] == status
    assert stub_github_enqueue == []


async def test_a_repeated_delivery_files_nothing_new(client, configured, mock_db, stub_github_enqueue):
    _no_prior(mock_db, prior=41)
    body, headers = _signed(_event())
    resp = await client.post("/api/feedback/testflight-webhook", content=body, headers=headers)
    assert resp.json() == {"status": "duplicate", "id": 41}
    assert stub_github_enqueue == []


async def test_a_new_submission_is_stored_and_filed_like_a_shake(client, configured, mock_db, stub_github_enqueue, monkeypatch):
    _no_prior(mock_db)
    stored = []
    mock_db.add = stored.append
    mock_db.commit = AsyncMock()

    async def refresh(obj):
        obj.id = 77
    mock_db.refresh = refresh

    async def fake_fetch(config, event, client):
        return {"attributes": {"comment": "Score is wrong", "deviceModel": "iPhone17,1"},
                "screenshot_base64": None, "crash_log": None}
    monkeypatch.setattr(tf, "fetch_submission", fake_fetch)

    body, headers = _signed(_event("s7"))
    resp = await client.post("/api/feedback/testflight-webhook", content=body, headers=headers)
    assert resp.status_code == 200 and resp.json() == {"status": "ok", "id": 77}
    assert stored[0].session_id == "tf-shot:s7"
    assert stored[0].description == "Score is wrong"
    assert stored[0].app_state["source"] == "testflight"
    assert stub_github_enqueue == [77]


async def test_a_fetch_failure_asks_apple_to_deliver_again(client, configured, mock_db, stub_github_enqueue, monkeypatch):
    _no_prior(mock_db)

    async def failing(config, event, client):
        raise RuntimeError("asc down")
    monkeypatch.setattr(tf, "fetch_submission", failing)
    body, headers = _signed(_event())
    resp = await client.post("/api/feedback/testflight-webhook", content=body, headers=headers)
    assert resp.status_code == 503
    assert stub_github_enqueue == []
