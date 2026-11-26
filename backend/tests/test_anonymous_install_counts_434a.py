r"""Guards for `434: A` / `424: A` anonymous lifecycle counts endpoint & table (#13261).

Verifies:
- `POST /api/telemetry/anonymous-counts` is NOT exempt from global `RateLimitMiddleware`
- Atomic upsert increments daily counts (1 -> 2 -> 3) in a single composite-PK row per
  `(day, app_version, event)` across all three closed events with zero per-event rows
- Server UTC clock partitions `day` and rejects days more than ±1 day away (`422`)
- Strict `app_version` format (`^\d+(?:\.\d+){0,3}$`, len <= 16) rejects junk (`422`)
- Closed 3-key payload (`extra="forbid"`, `StrictStr`, closed event set) rejects extra/bad keys (`422`)
- DB failure rolls back and returns `503` (gotcha #53)
- Migration `anon_install_counts_434a` chains cleanly off `retired_team_redirects_13229`,
  stays <= 32 chars, and cleanly defines table/PK/constraints + downgrade.
"""

from __future__ import annotations

from datetime import date, timedelta
import importlib.util
from pathlib import Path
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.models import AnonymousInstallCount
from app.routes.telemetry import (
    MAX_ANONYMOUS_VERSIONS_PER_DAY,
    _ANONYMOUS_COUNT_LOCK_NS,
    _UPSERT_ANONYMOUS_COUNT_SQL,
)
from app.services import get_db, get_db_rw

ENDPOINT = "/api/telemetry/anonymous-counts"
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "anon_install_counts_434a.py"
)


class _SqliteResult:
    """Minimal AsyncSession result shim exposing ``rowcount`` and ``scalar()``."""

    def __init__(self, cursor: sqlite3.Cursor):
        self.rowcount = cursor.rowcount
        row = cursor.fetchone() if cursor.description is not None else None
        self._scalar = row[0] if row is not None else None

    def scalar(self):
        return self._scalar


class _SqliteAsyncSession:
    """In-memory stdlib `sqlite3` session executing the route's compiled upsert SQL."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self.rolled_back = False

    async def execute(self, statement, params=None):
        sql_str = statement.text if hasattr(statement, "text") else str(statement)
        bound = {
            k: (v.isoformat() if isinstance(v, date) else v)
            for k, v in (params or {}).items()
        }
        cur = self._conn.execute(sql_str, bound)
        return _SqliteResult(cur)

    async def commit(self):
        self._conn.commit()

    async def rollback(self):
        self.rolled_back = True
        self._conn.rollback()


@pytest_asyncio.fixture
async def sqlite_client(monkeypatch):
    conn = sqlite3.connect(":memory:")
    ddl = str(CreateTable(AnonymousInstallCount.__table__).compile(dialect=postgresql.dialect()))
    conn.execute(ddl)
    conn.commit()

    async def _override_get_db():
        yield _SqliteAsyncSession(conn)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_db_rw] = _override_get_db
    fixed_today = date(2026, 6, 15)
    monkeypatch.setattr("app.routes.telemetry._utc_today", lambda: fixed_today)

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, conn, fixed_today

    app.dependency_overrides.clear()
    conn.close()


def _fetch_all_rows(conn: sqlite3.Connection) -> list[tuple[str, str, str, int]]:
    cur = conn.execute(
        "SELECT day, app_version, event, count "
        "FROM anonymous_install_counts "
        "ORDER BY day, app_version, event"
    )
    return list(cur.fetchall())


def test_anonymous_counts_endpoint_is_metered_by_rate_limit():
    from app.utils.rate_limit import _is_exempt

    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("BYPASS_RATE_LIMITS", None)
        assert not _is_exempt(ENDPOINT)


@pytest.mark.asyncio
async def test_valid_events_increment_single_daily_counter_row(sqlite_client):
    client, conn, fixed_today = sqlite_client

    for expected_count in (1, 2, 3):
        resp = await client.post(
            ENDPOINT,
            json={
                "event": "first_open",
                "app_version": "1.0.8",
                "day": fixed_today.isoformat(),
            },
        )
        assert resp.status_code == 202
        assert resp.json() == {"status": "accepted", "day": fixed_today.isoformat()}

        rows = _fetch_all_rows(conn)
        assert rows == [(fixed_today.isoformat(), "1.0.8", "first_open", expected_count)]

    for ev in ("first_run_finished", "previous_session_crashed"):
        resp = await client.post(
            ENDPOINT,
            json={
                "event": ev,
                "app_version": "1.0.8",
                "day": fixed_today.isoformat(),
            },
        )
        assert resp.status_code == 202

    rows = _fetch_all_rows(conn)
    assert rows == [
        (fixed_today.isoformat(), "1.0.8", "first_open", 3),
        (fixed_today.isoformat(), "1.0.8", "first_run_finished", 1),
        (fixed_today.isoformat(), "1.0.8", "previous_session_crashed", 1),
    ]


@pytest.mark.asyncio
async def test_day_enforces_server_clock_and_plus_minus_one_day_window(sqlite_client):
    client, conn, fixed_today = sqlite_client

    # Client within ±1 day is accepted and consolidated onto server_today.
    for delta in (-1, 0, 1):
        resp = await client.post(
            ENDPOINT,
            json={
                "event": "first_open",
                "app_version": "1.0.8",
                "day": (fixed_today + timedelta(days=delta)).isoformat(),
            },
        )
        assert resp.status_code == 202
        assert resp.json()["day"] == fixed_today.isoformat()

    assert _fetch_all_rows(conn) == [(fixed_today.isoformat(), "1.0.8", "first_open", 3)]

    # Outside ±1 day or invalid calendar/format dates are rejected and write nothing.
    for bad_day in (
        (fixed_today - timedelta(days=2)).isoformat(),
        (fixed_today + timedelta(days=2)).isoformat(),
        "2026-02-30",
        "20260615",
        "2026-06-15T00:00:00Z",
        "",
    ):
        resp = await client.post(
            ENDPOINT,
            json={
                "event": "first_open",
                "app_version": "1.0.8",
                "day": bad_day,
            },
        )
        assert resp.status_code == 422, f"Expected 422 for day={bad_day!r}"

    assert _fetch_all_rows(conn) == [(fixed_today.isoformat(), "1.0.8", "first_open", 3)]


@pytest.mark.asyncio
async def test_app_version_enforces_digits_and_dots_limit(sqlite_client):
    client, conn, fixed_today = sqlite_client

    for ok_ver in ("1", "1.0", "1.0.8", "2026.11.26.1"):
        resp = await client.post(
            ENDPOINT,
            json={
                "event": "first_run_finished",
                "app_version": ok_ver,
                "day": fixed_today.isoformat(),
            },
        )
        assert resp.status_code == 202, f"Expected 202 for version={ok_ver!r}"

    bad_versions = (
        "",
        "unknown",
        "1.0.8-beta",
        "v1.0.8",
        " 1.0.8",
        "1.0.8 ",
        "1.0.8\n",
        "1..0",
        ".1.0",
        "1.0.",
        "1.2.3.4.5",
        "12345678901234567",  # 17 chars (> 16)
    )
    for bad_ver in bad_versions:
        resp = await client.post(
            ENDPOINT,
            json={
                "event": "first_run_finished",
                "app_version": bad_ver,
                "day": fixed_today.isoformat(),
            },
        )
        assert resp.status_code == 422, f"Expected 422 for version={bad_ver!r}"

    rows = _fetch_all_rows(conn)
    assert [r[1] for r in rows] == ["1", "1.0", "1.0.8", "2026.11.26.1"]


@pytest.mark.asyncio
async def test_closed_payload_rejects_extra_keys_unknown_events_and_wrong_types(sqlite_client):
    client, conn, fixed_today = sqlite_client

    bad_payloads = [
        {"event": "other_event", "app_version": "1.0.8", "day": fixed_today.isoformat()},
        {"event": "screen_view", "app_version": "1.0.8", "day": fixed_today.isoformat()},
        {
            "event": "first_open",
            "app_version": "1.0.8",
            "day": fixed_today.isoformat(),
            "user_id": "123",
        },
        {
            "event": "first_open",
            "app_version": "1.0.8",
            "day": fixed_today.isoformat(),
            "device_id": "abc",
        },
        {"event": "first_open", "app_version": 108, "day": fixed_today.isoformat()},
        {"event": "first_open", "app_version": "1.0.8"},
        {"event": "first_open"},
        {},
    ]
    for payload in bad_payloads:
        resp = await client.post(ENDPOINT, json=payload)
        assert resp.status_code == 422, f"Expected 422 for payload={payload!r}"

    assert _fetch_all_rows(conn) == []


@pytest.mark.asyncio
async def test_db_failure_rolls_back_and_returns_503(monkeypatch):
    class _FailingSession:
        def __init__(self):
            self.rolled_back = False

        async def execute(self, *args, **kwargs):
            raise RuntimeError("simulated db error")

        async def commit(self):
            raise AssertionError("commit must not run after failed execute")

        async def rollback(self):
            self.rolled_back = True

    db = _FailingSession()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_db_rw] = _override_get_db
    fixed_today = date(2026, 6, 15)
    monkeypatch.setattr("app.routes.telemetry._utc_today", lambda: fixed_today)
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    ENDPOINT,
                    json={
                        "event": "previous_session_crashed",
                        "app_version": "1.0.8",
                        "day": fixed_today.isoformat(),
                    },
                )
        assert resp.status_code == 503
        assert db.rolled_back
    finally:
        app.dependency_overrides.clear()


def test_migration_metadata_and_constraints():
    spec = importlib.util.spec_from_file_location("anon_install_counts_434a", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    assert module.revision == "anon_install_counts_434a"
    assert len(module.revision) <= 32
    assert module.down_revision == "retired_team_redirects_13229"

    cols = {c.name: c for c in AnonymousInstallCount.__table__.columns}
    assert set(cols.keys()) == {"day", "app_version", "event", "count"}
    assert [c.name for c in AnonymousInstallCount.__table__.primary_key.columns] == [
        "day",
        "app_version",
        "event",
    ]
    compiled_pg = str(_UPSERT_ANONYMOUS_COUNT_SQL.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (day, app_version, event)" in compiled_pg


@pytest.mark.asyncio
async def test_daily_distinct_app_version_cap_drops_overflow_and_keeps_admitted_versions(
    sqlite_client, monkeypatch
):
    client, conn, fixed_today = sqlite_client
    assert MAX_ANONYMOUS_VERSIONS_PER_DAY == 20

    # Fill the day up to the cap of 20 distinct app_versions.
    for idx in range(1, MAX_ANONYMOUS_VERSIONS_PER_DAY + 1):
        resp = await client.post(
            ENDPOINT,
            json={
                "event": "first_open",
                "app_version": f"1.0.{idx}",
                "day": fixed_today.isoformat(),
            },
        )
        assert resp.status_code == 202

    assert (
        conn.execute(
            "SELECT COUNT(DISTINCT app_version) FROM anonymous_install_counts WHERE day = ?",
            (fixed_today.isoformat(),),
        ).fetchone()[0]
        == MAX_ANONYMOUS_VERSIONS_PER_DAY
    )

    # Past the cap, brand-new versions are accepted (202) and store nothing.
    for overflow_ver in ("1.0.21", "9.9.9999", "2.0.1"):
        resp = await client.post(
            ENDPOINT,
            json={
                "event": "first_open",
                "app_version": overflow_ver,
                "day": fixed_today.isoformat(),
            },
        )
        assert resp.status_code == 202
        assert resp.json() == {"status": "accepted", "day": fixed_today.isoformat()}

    assert (
        conn.execute(
            "SELECT COUNT(DISTINCT app_version) FROM anonymous_install_counts WHERE day = ?",
            (fixed_today.isoformat(),),
        ).fetchone()[0]
        == MAX_ANONYMOUS_VERSIONS_PER_DAY
    )

    # An already-admitted version still increments existing rows and admits another event.
    inc_resp = await client.post(
        ENDPOINT,
        json={
            "event": "first_open",
            "app_version": "1.0.1",
            "day": fixed_today.isoformat(),
        },
    )
    assert inc_resp.status_code == 202
    new_event_resp = await client.post(
        ENDPOINT,
        json={
            "event": "first_run_finished",
            "app_version": "1.0.1",
            "day": fixed_today.isoformat(),
        },
    )
    assert new_event_resp.status_code == 202

    rows_101 = conn.execute(
        "SELECT event, count FROM anonymous_install_counts WHERE day = ? AND app_version = ? ORDER BY event",
        (fixed_today.isoformat(), "1.0.1"),
    ).fetchall()
    assert rows_101 == [("first_open", 2), ("first_run_finished", 1)]

    # Advancing to the next UTC day resets the per-day cap so previously dropped versions succeed.
    next_day = fixed_today + timedelta(days=1)
    monkeypatch.setattr("app.routes.telemetry._utc_today", lambda: next_day)
    next_day_resp = await client.post(
        ENDPOINT,
        json={
            "event": "first_open",
            "app_version": "1.0.21",
            "day": next_day.isoformat(),
        },
    )
    assert next_day_resp.status_code == 202
    assert (
        conn.execute(
            "SELECT count FROM anonymous_install_counts WHERE day = ? AND app_version = ?",
            (next_day.isoformat(), "1.0.21"),
        ).fetchone()[0]
        == 1
    )


@pytest.mark.asyncio
async def test_postgres_slow_path_acquires_daily_advisory_lock_and_fast_path_skips_it(monkeypatch):
    class _FakeDialect:
        name = "postgresql"

    class _FakeBind:
        dialect = _FakeDialect()

    class _FakeResult:
        def __init__(self, rowcount: int = 0, scalar_val=None):
            self.rowcount = rowcount
            self._scalar = scalar_val

        def scalar(self):
            return self._scalar

    class _PgTraceSession:
        def __init__(self, initial_rowcount: int):
            self.initial_rowcount = initial_rowcount
            self.calls: list[tuple[str, dict]] = []
            self.committed = 0
            self.rolled_back = 0

        def get_bind(self):
            return _FakeBind()

        async def execute(self, statement, params=None):
            sql_str = statement.text if hasattr(statement, "text") else str(statement)
            self.calls.append((sql_str, dict(params or {})))
            if sql_str.lstrip().startswith("UPDATE anonymous_install_counts"):
                return _FakeResult(rowcount=self.initial_rowcount)
            if "SELECT 1" in sql_str:
                return _FakeResult(scalar_val=None)
            if "COUNT(DISTINCT app_version)" in sql_str:
                return _FakeResult(scalar_val=0)
            return _FakeResult(rowcount=1)

        async def commit(self):
            self.committed += 1

        async def rollback(self):
            self.rolled_back += 1

    fixed_today = date(2026, 6, 15)
    monkeypatch.setattr("app.routes.telemetry._utc_today", lambda: fixed_today)

    # Slow path (rowcount == 0) must take per-day pg_advisory_xact_lock before counting/inserting.
    slow_db = _PgTraceSession(initial_rowcount=0)

    async def _override_slow():
        yield slow_db

    app.dependency_overrides[get_db] = _override_slow
    app.dependency_overrides[get_db_rw] = _override_slow
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    ENDPOINT,
                    json={"event": "first_open", "app_version": "1.0.8", "day": fixed_today.isoformat()},
                )
        assert resp.status_code == 202
        lock_calls = [p for sql, p in slow_db.calls if "pg_advisory_xact_lock" in sql]
        assert lock_calls == [{"ns": _ANONYMOUS_COUNT_LOCK_NS, "key": fixed_today.toordinal()}]
        assert slow_db.committed == 1
    finally:
        app.dependency_overrides.clear()

    # Fast path (rowcount == 1) updates in place and skips advisory locking.
    fast_db = _PgTraceSession(initial_rowcount=1)

    async def _override_fast():
        yield fast_db

    app.dependency_overrides[get_db] = _override_fast
    app.dependency_overrides[get_db_rw] = _override_fast
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    ENDPOINT,
                    json={"event": "first_open", "app_version": "1.0.8", "day": fixed_today.isoformat()},
                )
        assert resp.status_code == 202
        assert not any("pg_advisory_xact_lock" in sql for sql, _ in fast_db.calls)
        assert fast_db.committed == 1
    finally:
        app.dependency_overrides.clear()
