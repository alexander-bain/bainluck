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
from app.utils.client_timing_contract import (
    MAX_EVENTS_PER_REQUEST,
    PROMOTED_DIMENSIONS,
)

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


# ---------------------------------------------------------------------------
# CERT-1869's repair: adversarial VALUES through the real ingest
# ---------------------------------------------------------------------------


ADVERSARIAL_PACKET = {
    "name": "screen_timing",
    "params": {
        # legitimate keys, hostile values — the exact defect CERT-1869 found
        "surface": "/user/alice@example.com",
        "entry": "user-12345",
        "device_class": "Bearer_secret-token-value",
        "network_class": "sess_9f8e7d6c5b4a",
        "app_build": "192.168.1.44",
        "outcome_class": "alice@example.com",
        # …alongside a real measurement, which must survive
        "first_card_ms": 1480,
        "card_count": 7,
    },
}

FORBIDDEN_SUBSTRINGS = [
    "alice",
    "example.com",
    "user-12345",
    "Bearer",
    "secret-token",
    "sess_9f8e7d6c5b4a",
    "192.168.1.44",
]


@pytest.mark.asyncio
async def test_adversarial_values_reach_neither_jsonb_nor_promoted_columns(
    client_and_db,
):
    """The repair CERT-1869 named, proved at the real HTTP boundary.

    The prior suite attacked hostile KEY NAMES only, so a hostile VALUE inside an
    allowlisted key passed a fully green run. This asserts on BOTH storage
    surfaces — the JSONB blob and every promoted column — because the route
    copies promoted columns out of the clean dict and a defect in either alone
    would still put an identifier in the table.
    """
    ac, db = client_and_db
    resp = await ac.post(INGEST, json={"events": [ADVERSARIAL_PACKET]})
    assert resp.status_code == 202

    assert len(db.added) == 1, "the packet's real measurement must still store"
    row = db.added[0]

    # 1. the JSONB blob
    blob = str(row.params)
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden.lower() not in blob.lower(), f"{forbidden!r} in params {blob}"

    # 2. every promoted column, read off the ORM object itself
    for dim in PROMOTED_DIMENSIONS:
        stored = getattr(row, dim, None)
        if stored is None:
            continue
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert (
                forbidden.lower() not in str(stored).lower()
            ), f"{forbidden!r} in promoted column {dim}={stored!r}"

    # 3. the hostile fields are absent, not merely sanitised into something else
    for hostile_field in (
        "entry",
        "device_class",
        "network_class",
        "app_build",
        "outcome_class",
    ):
        assert hostile_field not in row.params

    # 4. …and the identifier-bearing segment is refused BY NAME rather than kept.
    #    Asserted as the invariant, not as a literal: `user` is a real API
    #    segment, so `/user/alice@example.com` correctly masks to `user/:seg`.
    #    What must hold is that the segment carrying the address is gone.
    assert row.params["surface"].endswith(":seg")
    assert "alice" not in row.params["surface"]

    # 5. the real measurement is untouched — the repair must not cost the ship
    assert row.params["first_card_ms"] == 1480
    assert row.params["card_count"] == 7


@pytest.mark.asyncio
async def test_a_wholly_legitimate_packet_still_stores_every_field(client_and_db):
    """The other half of the repair: closing the domains must not close the sink.

    An over-tight domain produces permanently-empty columns that read as "no
    data" rather than as a bug, which is the failure mode a privacy fix is most
    likely to ship by accident.
    """
    ac, db = client_and_db
    resp = await ac.post(
        INGEST,
        json={
            "events": [
                {
                    "name": "screen_timing",
                    "params": {
                        "surface": "events/:id",
                        "entry": "warm",
                        "shell_ms": 180,
                        "first_card_ms": 940,
                        "fold_ms": 1200,
                        "interactive_ms": 1500,
                        "card_count": 6,
                        "device_class": "phone",
                        "network_class": "4g",
                        "outcome_class": "ok",
                    },
                }
            ]
        },
    )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 1, "rejected": 0, "stored": 1}

    row = db.added[0]
    # 10, not 11: `app_build` was removed from the contract under CERT-1880.
    assert len(row.params) == 10, f"a legal field was dropped: {row.params}"
    assert row.params["surface"] == "events/:id"
    assert row.params["first_card_ms"] == 940
    for dim in PROMOTED_DIMENSIONS:
        assert getattr(row, dim) is not None, f"promoted column {dim} came out empty"


@pytest.mark.parametrize(
    "hostile",
    [
        "127.0.1",
        "127.0.1 (317)",
        "192.168.1.44 (1)",
        "1.4.2 (alice-123)",
        "2130706433",
        "1.0 (Bearer_token)",
        "web",
    ],
)
@pytest.mark.asyncio
async def test_app_build_reaches_no_storage_surface_at_all(hostile):
    """CERT-1880's repair, at the real HTTP boundary.

    `app_build` is GONE from the contract, so every one of these — including
    the once-legitimate `web` — reaches neither JSONB nor a promoted column.

    It is removed rather than patched a fourth time because it cannot be
    patched: `socket.inet_aton` accepts `1.4.2` and `1.0`, which are genuine
    `CFBundleShortVersionString` values, as valid IPv4 encodings. The producer
    format and the address are the same strings.

    The packet's real timing measurement must still store — a privacy fix that
    also drops the ship is not a fix.
    """
    db = _RecordingSession()

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
                            {
                                "name": "screen_timing",
                                "params": {
                                    "app_build": hostile,
                                    "first_card_ms": 1480,
                                    "surface": "discover",
                                    "device_class": "phone",
                                },
                            }
                        ]
                    },
                )
        assert resp.status_code == 202
        row = db.added[0]
        assert "app_build" not in row.params, f"{hostile!r} reached JSONB"
        assert not hasattr(row, "app_build") or getattr(row, "app_build", None) is None
        blob = str(row.params)
        for fragment in ("127", "192", "alice", "Bearer", "2130706433"):
            assert fragment not in blob, f"{fragment} survived from {hostile!r}"
        # …and the ship is intact
        assert row.params["first_card_ms"] == 1480
        assert row.params["surface"] == "discover"
        assert row.params["device_class"] == "phone"
        assert row.device_class == "phone"
    finally:
        app.dependency_overrides.clear()
