"""Guards for the client-timing ingest route (LAT-P232, #2751).

The contract module has its own suite (`test_client_timing_contract.py`); this
file guards the things only the ROUTE can get wrong:

  - a public write endpoint that is accidentally exempt from rate limiting
  - a batch cap that is documented but not enforced
  - promoted columns that silently disagree with the stored JSONB
  - an aggregate read endpoint that is not actually admin-gated
  - a persistence failure that reports success (gotcha #53)
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import get_db, get_db_rw
from app.utils.client_timing_contract import MAX_EVENTS_PER_REQUEST

INGEST = "/api/telemetry/client-timing"
SUMMARY = "/api/telemetry/client-timing/summary"


class _RecordingSession:
    """Captures what the route tried to persist.

    A fake is legitimate here because the defect class under test is "what rows
    does the route BUILD", which is entirely route-side. It deliberately does
    NOT fake a query result — nothing in the ingest path reads.
    """

    def __init__(self, fail_on_commit: bool = False):
        self.added: list = []
        self.committed = False
        self.rolled_back = False
        self._fail = fail_on_commit

    def add_all(self, rows):
        self.added.extend(rows)

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        if self._fail:
            raise RuntimeError("simulated database failure")
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


@pytest_asyncio.fixture
async def client_and_db():
    db = _RecordingSession()

    async def _mock_get_db():
        yield db

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, db

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# The endpoint is metered
# ---------------------------------------------------------------------------


def test_the_ingest_path_is_not_rate_limit_exempt():
    """A public, unauthenticated WRITE endpoint must never be exempt.

    This is the guard that matters most on this route: the design leans on the
    global `RateLimitMiddleware` (60/min per anonymous IP) rather than adding a
    second bespoke limiter, so an exemption added later — for any reason — would
    quietly turn this into an unmetered public write with nothing to catch it.
    """
    from app.utils.rate_limit import _is_exempt

    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("BYPASS_RATE_LIMITS", None)
        assert not _is_exempt(INGEST)
        assert not _is_exempt(SUMMARY)


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_good_packet_is_stored_with_its_promoted_columns(client_and_db):
    ac, db = client_and_db
    resp = await ac.post(
        INGEST,
        json={
            "events": [
                {
                    "name": "screen_timing",
                    "params": {
                        "surface": "discover",
                        "entry": "cold",
                        "first_card_ms": 1480,
                        "device_class": "phone",
                        "network_class": "4g",
                        "app_build": "abc1234",
                        "outcome_class": "ok",
                        "card_count": 9,
                    },
                }
            ]
        },
    )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 1, "rejected": 0, "stored": 1}

    assert len(db.added) == 1
    row = db.added[0]
    assert row.event_name == "screen_timing"
    assert row.params["first_card_ms"] == 1480
    # The promoted columns must agree with the JSONB they were copied from — a
    # disagreement would make GROUP BY answer a different question than the blob.
    assert row.surface == row.params["surface"] == "discover"
    assert row.device_class == "phone"
    assert row.entry == "cold"
    assert row.outcome_class == "ok"
    assert db.committed


@pytest.mark.asyncio
async def test_a_hostile_packet_is_rejected_without_costing_the_good_one(
    client_and_db,
):
    """One bad item must never wipe the pass (gotcha #42)."""
    ac, db = client_and_db
    resp = await ac.post(
        INGEST,
        json={
            "events": [
                {"name": "evil_event", "params": {"user_id": 7}},
                {"name": "screen_timing", "params": {"first_card_ms": 900}},
                {"name": "screen_timing", "params": {"nothing_valid": 1}},
            ]
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body == {"accepted": 1, "rejected": 2, "stored": 1}
    assert len(db.added) == 1
    assert db.added[0].params == {"first_card_ms": 900}


@pytest.mark.asyncio
async def test_an_identifier_cannot_reach_a_stored_row_through_the_route(
    client_and_db,
):
    """End-to-end restatement of the privacy claim, at the HTTP boundary.

    The contract suite proves the function strips these. This proves nothing
    downstream of it puts them back.
    """
    ac, db = client_and_db
    await ac.post(
        INGEST,
        json={
            "events": [
                {
                    "name": "screen_timing",
                    "params": {
                        "first_card_ms": 500,
                        "user_id": "u-1",
                        "session_id": "s-1",
                        "email": "a@b.c",
                        "page_path": "/event/4242",
                    },
                }
            ]
        },
    )
    row = db.added[0]
    blob = str(row.params)
    for forbidden in ("u-1", "s-1", "a@b.c", "4242"):
        assert forbidden not in blob
    assert row.params == {"first_card_ms": 500}


@pytest.mark.asyncio
async def test_an_oversized_batch_is_refused_before_it_reaches_the_database(
    client_and_db,
):
    ac, db = client_and_db
    resp = await ac.post(
        INGEST,
        json={
            "events": [
                {"name": "screen_timing", "params": {"first_card_ms": 1}}
                for _ in range(MAX_EVENTS_PER_REQUEST + 1)
            ]
        },
    )
    assert resp.status_code == 422
    assert db.added == []


@pytest.mark.asyncio
async def test_an_empty_batch_writes_nothing_and_does_not_commit(client_and_db):
    ac, db = client_and_db
    resp = await ac.post(INGEST, json={"events": []})
    assert resp.status_code == 202
    assert resp.json()["stored"] == 0
    assert db.added == []
    assert not db.committed


@pytest.mark.asyncio
async def test_a_persistence_failure_reports_zero_stored_not_success():
    """ "It returned" is not "it worked" (gotcha #53).

    The beacon must not surface an error to the reader's page — but it must also
    never report `accepted: 1` for a row that rolled back, or a telemetry outage
    would read as a healthy quiet sink forever.
    """
    db = _RecordingSession(fail_on_commit=True)

    async def _mock_get_db():
        yield db

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    INGEST,
                    json={
                        "events": [
                            {"name": "screen_timing", "params": {"first_card_ms": 10}}
                        ]
                    },
                )
        assert resp.status_code == 202
        assert resp.json() == {"accepted": 0, "rejected": 1, "stored": 0}
        assert db.rolled_back
        assert not db.committed
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_summary_is_admin_gated(client_and_db, monkeypatch):
    """The ingest is public so the sample is honest; the READ is not."""
    ac, _ = client_and_db
    monkeypatch.setenv("ADMIN_TOKEN", "secret-p232")
    resp = await ac.get(SUMMARY)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_the_summary_refuses_an_unknown_event_name(client_and_db, monkeypatch):
    ac, _ = client_and_db
    monkeypatch.setenv("ADMIN_TOKEN", "secret-p232")
    resp = await ac.get(
        SUMMARY,
        params={"event_name": "page_view"},
        headers={"Authorization": "Bearer secret-p232"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_the_summary_window_is_bounded(client_and_db, monkeypatch):
    ac, _ = client_and_db
    monkeypatch.setenv("ADMIN_TOKEN", "secret-p232")
    resp = await ac.get(
        SUMMARY,
        params={"hours": 100000},
        headers={"Authorization": "Bearer secret-p232"},
    )
    assert resp.status_code == 422
