"""Guards for the MetricKit ingest route (#12309).

The things only the ROUTE can get wrong:

  - a public write endpoint that is accidentally exempt from rate limiting
  - an oversized body that is parsed whole before it is refused
  - a kind outside the set, or a payload that is not an object, being stored
  - an identifier the phone did not mean to send reaching a stored row
  - a persistence failure that reports success, so the phone drops the payload
    (gotcha #53)
  - a retention sweep that runs on every request, or whose SQL cannot run
  - admin reads that are not actually admin-gated
"""

import asyncio
from datetime import date, timedelta
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routes import metrickit
from app.services import get_db, get_db_rw

INGEST = "/api/telemetry/metrickit"
SUMMARY = "/api/telemetry/metrickit/summary"

#: A trimmed real-shaped hang diagnostic, as `MXHangDiagnostic.jsonRepresentation()`.
HANG = {
    "version": "1.0.0",
    "callStackTree": {
        "callStackPerThread": True,
        "callStacks": [
            {
                "threadAttributed": True,
                "callStackRootFrames": [
                    {
                        "binaryUUID": "70B89F27-1634-3580-A695-57CDB41D7743",
                        "offsetIntoBinaryTextSegment": 123456,
                        "sampleCount": 20,
                        "binaryName": "Bain Luck",
                        "address": 74565,
                    }
                ],
            }
        ],
    },
    "diagnosticMetaData": {
        "appBuildVersion": "10",
        "appVersion": "1.0.6",
        "osVersion": "iPhone OS 26.1 (23B85)",
        "deviceType": "iPhone17,2",
        "hangDuration": "2.31 sec",
    },
}


def _body(**overrides):
    body = {
        "kind": "hang",
        "app_version": "1.0.6",
        "app_build": "10",
        "os_version": "iPhone OS 26.1 (23B85)",
        "device_type": "iPhone17,2",
        "payload": HANG,
    }
    body.update(overrides)
    return body


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _RecordingSession:
    """Captures what the route tried to persist and execute.

    A fake is legitimate here because the defects under test are "what row does
    the route BUILD" and "when does it SWEEP", both route-side.
    """

    def __init__(self, fail_on_commit: bool = False, persisted_today_bytes: int = 0):
        self.added: list = []
        self.executed: list = []
        self.commits = 0
        self.rolled_back = False
        self._fail = fail_on_commit
        self.persisted_today_bytes = persisted_today_bytes

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        if self._fail:
            raise RuntimeError("simulated database failure")
        self.commits += 1

    async def rollback(self):
        self.rolled_back = True

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.executed.append((sql, params))
        if "SUM(payload_bytes)" in sql:
            return _ScalarResult(
                self.persisted_today_bytes + sum(r.payload_bytes for r in self.added)
            )
        return []


class _FakeAsyncRedis:
    """Minimal shared async Redis stand-in for daily ceiling tests across workers."""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incrby(self, key: str, amount: int) -> int:
        val = self.counts.get(key, 0) + amount
        self.counts[key] = val
        return val

    async def decrby(self, key: str, amount: int) -> int:
        val = self.counts.get(key, 0) - amount
        self.counts[key] = val
        return val

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True


def _client(db):
    async def _mock_get_db():
        yield db

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def client_and_db():
    db = _RecordingSession()
    fake_redis = _FakeAsyncRedis()
    db.fake_redis = fake_redis
    # The sweep is its own test; here it has just run.
    metrickit._last_prune = time.monotonic()
    metrickit._reset_daily_bytes_state()
    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch.object(metrickit, "_get_daily_bytes_redis", AsyncMock(return_value=fake_redis)),
    ):
        async with _client(db) as ac:
            yield ac, db
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# The endpoint is metered and mounted
# ---------------------------------------------------------------------------


def test_the_ingest_path_is_not_rate_limit_exempt():
    """A public, unauthenticated WRITE endpoint must never be exempt."""
    from app.utils.rate_limit import _is_exempt

    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("BYPASS_RATE_LIMITS", None)
        assert not _is_exempt(INGEST)
        assert not _is_exempt(SUMMARY)


def test_the_router_is_mounted_and_exported():
    """Gotcha #2: mounted in `main.py` and exported from `routes/__init__.py`."""
    import app.routes as routes

    paths = {getattr(r, "path", None) for r in app.routes}
    assert INGEST in paths and SUMMARY in paths
    assert "metrickit" in routes.__all__


def test_the_kinds_match_the_app():
    """The app's `MetricKitRecord12309.Kind` raw values are the same set."""
    assert metrickit.ACCEPTED_KINDS == {
        "crash", "hang", "cpu_exception", "disk_write", "launch", "metrics",
    }


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_diagnostic_is_stored_untouched_with_its_copied_fields(client_and_db):
    ac, db = client_and_db
    resp = await ac.post(INGEST, json=_body())
    assert resp.status_code == 202
    assert resp.json() == {"stored": 1}

    assert len(db.added) == 1
    row = db.added[0]
    assert row.kind == "hang"
    assert row.payload == HANG
    assert (row.app_version, row.app_build) == ("1.0.6", "10")
    assert row.os_version == "iPhone OS 26.1 (23B85)"
    assert row.device_type == "iPhone17,2"
    assert row.payload_bytes == len(json.dumps(HANG, separators=(",", ":")).encode())
    assert db.commits == 1


#: The exact bytes the app sent on the simulator (Nov 9, 2026, DEBUG sample
#: hang through `MetricKitForwarder12309`), as a local stand-in received them.
APP_BODY = (
    b'{"app_build":"10","os_version":"iPhone OS 27.0 (24A5260a)","device_type":"iPhone18,2",'
    b'"app_version":"1.0.6","payload":{"diagnosticMetaData":{"appBuildVersion":"10",'
    b'"osVersion":"iPhone OS 27.0 (24A5260a)","appVersion":"1.0.6","hangDuration":"2.31 sec",'
    b'"deviceType":"iPhone18,2"},"callStackTree":{"callStacks":[{"threadAttributed":true,'
    b'"callStackRootFrames":[{"offsetIntoBinaryTextSegment":123456,"address":74565,"sampleCount":20,'
    b'"binaryName":"Bain Luck","binaryUUID":"70B89F27-1634-3580-A695-57CDB41D7743"}]}],'
    b'"callStackPerThread":true},"version":"1.0.0"},"kind":"hang"}'
)


@pytest.mark.asyncio
async def test_the_body_the_app_sends_is_stored(client_and_db):
    """The app's own bytes, not a body written to fit the route."""
    ac, db = client_and_db
    resp = await ac.post(INGEST, content=APP_BODY, headers={"content-type": "application/json"})
    assert resp.status_code == 202
    row = db.added[0]
    assert row.kind == "hang"
    assert row.device_type == "iPhone18,2"
    assert row.payload == json.loads(APP_BODY)["payload"]


@pytest.mark.asyncio
async def test_a_day_of_metrics_is_stored_as_its_own_kind(client_and_db):
    ac, db = client_and_db
    metrics = {"applicationLaunchMetrics": {"histogrammedTimeToFirstDrawKey": {}}}
    resp = await ac.post(INGEST, json=_body(kind="metrics", payload=metrics))
    assert resp.status_code == 202
    assert db.added[0].kind == "metrics"
    assert db.added[0].payload == metrics


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        _body(kind="screenshot"),
        _body(payload=["not", "an", "object"]),
        _body(payload="text"),
        {"kind": "hang"},
        _body(app_version="x" * 65),
    ],
    ids=["unknown-kind", "payload-list", "payload-string", "no-payload", "long-version"],
)
async def test_a_body_the_phone_could_never_fix_is_refused_and_not_stored(client_and_db, body):
    ac, db = client_and_db
    resp = await ac.post(INGEST, json=body)
    assert resp.status_code == 422
    assert db.added == []


@pytest.mark.asyncio
async def test_malformed_json_is_refused_without_echoing_it(client_and_db):
    ac, db = client_and_db
    resp = await ac.post(
        INGEST, content=b'{"kind": "hang", "payload": {"secret-ish": ', headers={"content-type": "application/json"}
    )
    assert resp.status_code == 422
    assert "secret-ish" not in resp.text
    assert db.added == []


@pytest.mark.asyncio
async def test_an_identifier_the_phone_adds_never_reaches_a_stored_row(client_and_db):
    """Unknown top-level keys are ignored: the row has no column for them."""
    ac, db = client_and_db
    resp = await ac.post(
        INGEST, json=_body(user_id="u-1", session_id="s-1", email="a@b.c")
    )
    assert resp.status_code == 202
    row = db.added[0]
    for forbidden in ("user_id", "session_id", "email", "ip"):
        assert not hasattr(row, forbidden)
    blob = json.dumps(row.payload)
    for value in ("u-1", "s-1", "a@b.c"):
        assert value not in blob


@pytest.mark.asyncio
async def test_a_declared_oversized_body_is_refused_before_it_is_read(client_and_db):
    ac, db = client_and_db
    big = _body(payload={"pad": "x" * (metrickit.MAX_BODY_BYTES + 1)})
    resp = await ac.post(INGEST, json=big)
    assert resp.status_code == 413
    assert db.added == []


@pytest.mark.asyncio
async def test_an_oversized_body_without_a_length_is_refused_as_it_streams(client_and_db):
    """Chunked: no Content-Length to read, so the cap must hold on the stream."""
    ac, db = client_and_db
    chunk = b"x" * 65536

    async def stream():
        yield b'{"kind": "hang", "payload": {"pad": "'
        for _ in range(metrickit.MAX_BODY_BYTES // len(chunk) + 2):
            yield chunk
        yield b'"}}'

    resp = await ac.post(INGEST, content=stream(), headers={"content-type": "application/json"})
    assert resp.status_code == 413
    assert db.added == []


@pytest.mark.asyncio
async def test_a_failed_save_answers_503_so_the_phone_keeps_it(monkeypatch):
    """Gotcha #53: a 2xx here would make the phone delete a payload never stored."""
    db = _RecordingSession(fail_on_commit=True)
    fake_redis = _FakeAsyncRedis()
    day_one = date(2026, 11, 24)
    key = metrickit._daily_bytes_redis_key(day_one)
    metrickit._last_prune = time.monotonic()
    metrickit._reset_daily_bytes_state()
    monkeypatch.setattr(metrickit, "_utc_today", lambda: day_one)
    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch.object(metrickit, "_get_daily_bytes_redis", AsyncMock(return_value=fake_redis)),
        ):
            async with _client(db) as ac:
                with patch.object(metrickit.logger, "exception") as logged:
                    resp = await ac.post(INGEST, json=_body())
        assert resp.status_code == 503
        assert db.rolled_back
        assert db.commits == 0
        assert fake_redis.counts.get(key, 0) == 0
        logged.assert_called_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_the_daily_stored_bytes_ceiling_rejects_excess_with_429_and_resets_tomorrow(
    client_and_db, monkeypatch
):
    """Over the daily byte ceiling answers 429 so real phones keep queued files until tomorrow."""
    ac, db = client_and_db
    payload_bytes = len(json.dumps(HANG, separators=(",", ":")).encode())
    # Allow two payloads today, reject the third across senders, then allow after UTC midnight.
    monkeypatch.setattr(metrickit, "MAX_DAILY_STORED_BYTES", payload_bytes * 2)
    day_one = date(2026, 11, 24)
    day_two = day_one + timedelta(days=1)
    key_one = f"{metrickit.DAILY_BYTES_REDIS_KEY_PREFIX}{day_one.isoformat()}"
    monkeypatch.setattr(metrickit, "_utc_today", lambda: day_one)

    assert (await ac.post(INGEST, json=_body())).status_code == 202
    assert (await ac.post(INGEST, json=_body())).status_code == 202
    over = await ac.post(INGEST, json=_body())
    assert over.status_code == 429
    assert "too many" in over.json()["detail"].lower()
    assert len(db.added) == 2
    assert db.fake_redis.ttls[key_one] == 2 * 86400
    assert db.fake_redis.counts[key_one] == payload_bytes * 2

    monkeypatch.setattr(metrickit, "_utc_today", lambda: day_two)
    assert (await ac.post(INGEST, json=_body())).status_code == 202
    assert len(db.added) == 3


@pytest.mark.asyncio
async def test_daily_ceiling_still_refuses_after_module_memory_cleared_restart(
    client_and_db, monkeypatch
):
    """Fable 7:45 PM PT: worker restart / module memory reset must not lift the day's ceiling."""
    ac, db = client_and_db
    payload_bytes = len(json.dumps(HANG, separators=(",", ":")).encode())
    monkeypatch.setattr(metrickit, "MAX_DAILY_STORED_BYTES", payload_bytes * 2)
    day_one = date(2026, 11, 24)
    monkeypatch.setattr(metrickit, "_utc_today", lambda: day_one)

    assert (await ac.post(INGEST, json=_body())).status_code == 202
    assert (await ac.post(INGEST, json=_body())).status_code == 202

    # Simulate web_supervisor worker recycle clearing module globals.
    metrickit._reset_daily_bytes_state()

    over = await ac.post(INGEST, json=_body())
    assert over.status_code == 429
    assert len(db.added) == 2


@pytest.mark.asyncio
async def test_daily_ceiling_enforced_when_two_workers_each_believe_they_are_under(
    client_and_db, monkeypatch
):
    """Fable 7:45 PM PT: shared Redis counter stops two workers from splitting the ceiling."""
    ac, db = client_and_db
    payload_bytes = len(json.dumps(HANG, separators=(",", ":")).encode())
    day_one = date(2026, 11, 24)
    monkeypatch.setattr(metrickit, "_utc_today", lambda: day_one)

    # (a) Sequential two-worker scenario with ceiling = 2 * payload_bytes:
    # Worker A stores 1, Worker B starts fresh (believes 0) and stores 1, then
    # Worker A (still believing only 1 stored) tries a 2nd -> 429.
    monkeypatch.setattr(metrickit, "MAX_DAILY_STORED_BYTES", payload_bytes * 2)
    assert (await ac.post(INGEST, json=_body())).status_code == 202
    worker_a_state = (
        metrickit._db_fallback_day,
        metrickit._db_fallback_read_at,
        metrickit._db_fallback_bytes,
    )
    metrickit._reset_daily_bytes_state()  # Worker B process state
    assert (await ac.post(INGEST, json=_body())).status_code == 202

    # Restore Worker A's process state (believing it is under ceiling).
    (
        metrickit._db_fallback_day,
        metrickit._db_fallback_read_at,
        metrickit._db_fallback_bytes,
    ) = worker_a_state
    assert (await ac.post(INGEST, json=_body())).status_code == 429
    assert len(db.added) == 2

    # (b) Concurrent dual-worker burst on ceiling = 1 * payload_bytes: exactly one 202, one 429.
    db_concurrent = _RecordingSession()
    shared_redis = _FakeAsyncRedis()
    monkeypatch.setattr(metrickit, "MAX_DAILY_STORED_BYTES", payload_bytes)
    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch.object(metrickit, "_get_daily_bytes_redis", AsyncMock(return_value=shared_redis)),
    ):
        async with _client(db_concurrent) as ac1, _client(db_concurrent) as ac2:
            resps = await asyncio.gather(
                ac1.post(INGEST, json=_body()),
                ac2.post(INGEST, json=_body()),
            )
    assert sorted(r.status_code for r in resps) == [202, 429]
    assert len(db_concurrent.added) == 1


@pytest.mark.asyncio
async def test_redis_unreachable_falls_back_to_table_sum_cached_60s_and_survives_restart(
    monkeypatch
):
    """When Redis is unreachable, fall back to metrickit_payloads daily sum cached <=60s."""
    payload_bytes = len(json.dumps(HANG, separators=(",", ":")).encode())
    db = _RecordingSession()
    now = 1000.0
    day_one = date(2026, 11, 24)
    metrickit._last_prune = now
    metrickit._reset_daily_bytes_state()
    monkeypatch.setattr(metrickit, "MAX_DAILY_STORED_BYTES", payload_bytes * 2)
    monkeypatch.setattr(metrickit, "_utc_today", lambda: day_one)
    monkeypatch.setattr(metrickit.time, "monotonic", lambda: now)

    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch.object(
                metrickit,
                "_get_daily_bytes_redis",
                AsyncMock(side_effect=ConnectionError("redis down")),
            ),
        ):
            async with _client(db) as ac:
                assert (await ac.post(INGEST, json=_body())).status_code == 202
                assert (await ac.post(INGEST, json=_body())).status_code == 202

                sum_queries = [
                    (sql, params) for sql, params in db.executed if "SUM(payload_bytes)" in sql
                ]
                assert len(sum_queries) == 1, "DB fallback sum should be cached for 60s"
                sql, params = sum_queries[0]
                assert "received_at >= :day_start AND received_at < :day_end" in sql
                assert params["day_start"].isoformat() == "2026-11-24T00:00:00+00:00"
                assert params["day_end"].isoformat() == "2026-11-25T00:00:00+00:00"

                # Over ceiling in cache -> 429 without extra DB query.
                assert (await ac.post(INGEST, json=_body())).status_code == 429
                assert len([q for q in db.executed if "SUM(payload_bytes)" in q[0]]) == 1

                # Worker restart clears memory -> re-reads DB sum and still refuses 429.
                metrickit._reset_daily_bytes_state()
                assert (await ac.post(INGEST, json=_body())).status_code == 429
                assert len([q for q in db.executed if "SUM(payload_bytes)" in q[0]]) == 2

                # Another worker persists bytes; once 60s TTL passes, refresh sees total -> 429.
                monkeypatch.setattr(metrickit, "MAX_DAILY_STORED_BYTES", payload_bytes * 3)
                db.persisted_today_bytes = payload_bytes  # 2 local + 1 peer == 3 total
                now += metrickit.DAILY_BYTES_DB_CACHE_SECONDS + 1.0
                metrickit._last_prune = now
                assert (await ac.post(INGEST, json=_body())).status_code == 429
                assert len([q for q in db.executed if "SUM(payload_bytes)" in q[0]]) == 3
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_redis_and_db_sum_unavailable_answers_503_never_no_ceiling(monkeypatch):
    """If Redis is down and DB table-sum also fails, refuse 503 rather than fail-open."""
    db = _RecordingSession()
    metrickit._last_prune = time.monotonic()
    metrickit._reset_daily_bytes_state()

    async def boom(statement, params=None):
        raise RuntimeError("simulated DB fallback failure")

    db.execute = boom
    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch.object(metrickit, "_get_daily_bytes_redis", AsyncMock(return_value=None)),
            patch.object(metrickit.logger, "exception") as logged,
        ):
            async with _client(db) as ac:
                resp = await ac.post(INGEST, json=_body())
        assert resp.status_code == 503
        assert db.added == []
        logged.assert_called_once()
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_sweep_runs_once_per_period_and_after_the_save(client_and_db, monkeypatch):
    ac, db = client_and_db
    metrickit._last_prune = None  # never swept, even when process monotonic clock < 1h
    monkeypatch.setattr(metrickit.time, "monotonic", lambda: 42.0)
    await ac.post(INGEST, json=_body())
    await ac.post(INGEST, json=_body())

    sweeps = [(sql, params) for sql, params in db.executed if "DELETE FROM metrickit_payloads" in sql]
    assert len(sweeps) == 1, "the second request inside the period must not sweep again"
    sql, params = sweeps[0]
    # The untyped bind beside an INTERVAL literal fails only on a real database.
    assert "CAST(:days AS integer)" in sql
    assert params == {"days": metrickit.RETENTION_DAYS}
    # Both payloads were stored; the sweep came after the first one's commit.
    assert len(db.added) == 2
    assert db.commits == 3


@pytest.mark.asyncio
async def test_a_failed_sweep_never_costs_the_payload_just_stored(client_and_db, monkeypatch):
    ac, db = client_and_db
    metrickit._last_prune = None
    monkeypatch.setattr(metrickit.time, "monotonic", lambda: 15.0)

    async def boom(statement, params=None):
        raise RuntimeError("simulated sweep failure")

    db.execute = boom
    with patch.object(metrickit.logger, "exception") as logged:
        resp = await ac.post(INGEST, json=_body())
    assert resp.status_code == 202
    assert len(db.added) == 1
    logged.assert_called_once()


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_summary_is_admin_gated(client_and_db, monkeypatch):
    """The ingest is public; the crash stacks are not."""
    ac, _ = client_and_db
    monkeypatch.setenv("ADMIN_TOKEN", "secret-12309")
    assert (await ac.get(SUMMARY)).status_code == 403
    assert (await ac.get(f"{INGEST}/1")).status_code == 403


@pytest.mark.asyncio
async def test_the_summary_window_is_bounded_by_retention(client_and_db, monkeypatch):
    ac, _ = client_and_db
    monkeypatch.setenv("ADMIN_TOKEN", "secret-12309")
    resp = await ac.get(
        SUMMARY,
        params={"days": metrickit.RETENTION_DAYS + 1},
        headers={"Authorization": "Bearer secret-12309"},
    )
    assert resp.status_code == 422
