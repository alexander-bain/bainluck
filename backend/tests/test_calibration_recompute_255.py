"""Queue #255 Item 3 — the recompute enqueue operational contract.

``POST /api/admin/calibration/recompute`` returned an opaque 500 "instead of
enqueueing" when the Celery/Redis broker was briefly unreachable
(``send_task`` raises a connection error). The fix routes the enqueue through
``_safe_send_task``, which converts a broker failure into a retryable 503 and
never a bare 500. Auth still fails closed (403) before any enqueue is attempted.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from kombu.exceptions import OperationalError

ADMIN = "test-admin-token-255"


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)

    from app.main import app

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


@pytest.mark.asyncio
async def test_recompute_returns_503_when_broker_down(client):
    """A broker connection error becomes a retryable 503, not an opaque 500."""
    import app.tasks as tasks

    def _boom(*_a, **_k):
        raise OperationalError("broker unreachable")

    with patch.object(tasks.celery_app, "send_task", side_effect=_boom):
        resp = await client.post(
            "/api/admin/calibration/recompute",
            headers={"Authorization": f"Bearer {ADMIN}"},
        )

    assert resp.status_code == 503
    assert "broker" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_recompute_enqueues_on_happy_path(client):
    """When the broker is healthy the task is queued and its id returned."""
    import app.tasks as tasks

    fake_result = type("R", (), {"id": "task-255-abc"})()

    with patch.object(tasks.celery_app, "send_task", return_value=fake_result) as sent:
        resp = await client.post(
            "/api/admin/calibration/recompute",
            headers={"Authorization": f"Bearer {ADMIN}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert body["task_id"] == "task-255-abc"
    # Routed to the dedicated heavy calibration lane (#224).
    _, kwargs = sent.call_args
    assert kwargs.get("queue") == "heavy"


@pytest.mark.asyncio
async def test_recompute_fails_closed_without_admin_auth(client):
    """No Bearer token -> 403, and the broker is never touched."""
    import app.tasks as tasks

    with patch.object(tasks.celery_app, "send_task") as sent:
        resp = await client.post("/api/admin/calibration/recompute")

    assert resp.status_code == 403
    sent.assert_not_called()
