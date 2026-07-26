"""Queue #256 Item 2 — every admin Celery enqueue degrades consistently.

Queue #255 Item 3 gave ``POST /api/admin/calibration/recompute`` a single
retryable-503 contract via ``_safe_send_task``. This queue generalizes that
helper (now in ``app.routes.admin_utils``) to every admin enqueue: a transient
broker/transport failure must surface as HTTP 503 (retryable), never an opaque
500, while task name / queue routing / args / kwargs are preserved verbatim, and
auth still fails closed (403) before any enqueue is attempted.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

try:  # broker connection error class (kombu ships with Celery)
    from kombu.exceptions import OperationalError as BrokerError
except Exception:  # pragma: no cover — fallback if kombu is unavailable
    BrokerError = Exception

from app.routes.admin_utils import _safe_send_task

ADMIN = "test-admin-token-256"


# ---------------------------------------------------------------------------
# Helper-level coverage
# ---------------------------------------------------------------------------


def test_safe_send_task_happy_path_forwards_verbatim():
    """The AsyncResult is returned and name/args/kwargs (incl. queue=) pass through."""
    import app.tasks as tasks

    fake_result = type("R", (), {"id": "abc"})()

    with patch.object(tasks.celery_app, "send_task", return_value=fake_result) as sent:
        result = _safe_send_task(
            "app.tasks.some_task",
            "positional",
            kwargs={"limit": 5},
            queue="background",
        )

    assert result is fake_result
    assert result.id == "abc"
    # Task name is the first positional; extra *args/**kwargs forwarded verbatim.
    args, kwargs = sent.call_args
    assert args == ("app.tasks.some_task", "positional")
    assert kwargs == {"kwargs": {"limit": 5}, "queue": "background"}


def test_safe_send_task_forwards_no_queue():
    """Call sites that omit queue= must use Celery default routing (no queue kwarg)."""
    import app.tasks as tasks

    fake_result = type("R", (), {"id": "xyz"})()

    with patch.object(tasks.celery_app, "send_task", return_value=fake_result) as sent:
        _safe_send_task("app.tasks.no_queue_task", args=[7])

    args, kwargs = sent.call_args
    assert args == ("app.tasks.no_queue_task",)
    assert kwargs == {"args": [7]}
    assert "queue" not in kwargs


@pytest.mark.parametrize("queue", ["heavy", "background", None])
def test_safe_send_task_broker_failure_becomes_503(queue):
    """A broker/transport error becomes a retryable HTTPException(503), never a 500.

    Covers heavy-queue, background-queue, and default-routing call sites.
    """
    import app.tasks as tasks

    def _boom(*_a, **_k):
        raise BrokerError("broker unreachable")

    call_kwargs = {} if queue is None else {"queue": queue}

    with patch.object(tasks.celery_app, "send_task", side_effect=_boom):
        with pytest.raises(HTTPException) as exc_info:
            _safe_send_task("app.tasks.whatever", **call_kwargs)

    assert exc_info.value.status_code == 503
    assert "broker" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Integration coverage — mounted admin endpoints under /api/admin
# ---------------------------------------------------------------------------


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
async def test_admin_enqueue_fails_closed_without_auth(client):
    """No Bearer token -> 403, and the broker is never touched (auth before enqueue)."""
    import app.tasks as tasks

    with patch.object(tasks.celery_app, "send_task") as sent:
        resp = await client.post("/api/admin/calibration/recompute")

    assert resp.status_code == 403
    sent.assert_not_called()


@pytest.mark.asyncio
async def test_heavy_endpoint_converts_broker_failure_to_503(client):
    """A heavy-queue endpoint (calibration recompute) surfaces 503 on broker failure."""
    import app.tasks as tasks

    def _boom(*_a, **_k):
        raise BrokerError("broker unreachable")

    with patch.object(tasks.celery_app, "send_task", side_effect=_boom):
        resp = await client.post(
            "/api/admin/calibration/recompute",
            headers={"Authorization": f"Bearer {ADMIN}"},
        )

    assert resp.status_code == 503
    assert "broker" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_heavy_endpoint_happy_path_routes_to_heavy(client):
    """Healthy broker -> task queued on the dedicated heavy lane (#224)."""
    import app.tasks as tasks

    fake_result = type("R", (), {"id": "heavy-256"})()

    with patch.object(tasks.celery_app, "send_task", return_value=fake_result) as sent:
        resp = await client.post(
            "/api/admin/calibration/recompute",
            headers={"Authorization": f"Bearer {ADMIN}"},
        )

    assert resp.status_code == 200
    assert resp.json()["task_id"] == "heavy-256"
    _, kwargs = sent.call_args
    assert kwargs.get("queue") == "heavy"


@pytest.mark.asyncio
async def test_background_endpoint_converts_broker_failure_to_503(client):
    """A background-queue endpoint (backfill-winners) surfaces 503 on broker failure."""
    import app.tasks as tasks

    def _boom(*_a, **_k):
        raise BrokerError("broker unreachable")

    with patch.object(tasks.celery_app, "send_task", side_effect=_boom):
        resp = await client.post(
            "/api/admin/backfill-winners",
            headers={"Authorization": f"Bearer {ADMIN}"},
        )

    assert resp.status_code == 503
    assert "broker" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_background_endpoint_happy_path_routes_to_background(client):
    """Healthy broker -> task queued on the background lane with args forwarded."""
    import app.tasks as tasks

    fake_result = type("R", (), {"id": "bg-256"})()

    with patch.object(tasks.celery_app, "send_task", return_value=fake_result) as sent:
        resp = await client.post(
            "/api/admin/backfill-winners",
            headers={"Authorization": f"Bearer {ADMIN}"},
        )

    assert resp.status_code == 200
    assert resp.json()["task_id"] == "bg-256"
    _, kwargs = sent.call_args
    assert kwargs.get("queue") == "background"
    assert kwargs.get("kwargs") == {"dry_run": False, "limit": 2000}
