"""Integration tests for POST /api/admin/db-query endpoint."""

import json
import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

_has_db = "DATABASE_URL" in os.environ
_needs_db = pytest.mark.skipif(not _has_db, reason="No DATABASE_URL — CI only")


@pytest.fixture
def admin_secret(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "test-secret")
    return "test-secret"


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_403_without_secret():
    async with _client() as client:
        resp = await client.post(
            "/api/admin/db-query?secret=wrong",
            json={"sql": "SELECT 1"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
@_needs_db
async def test_simple_select(admin_secret):
    async with _client() as client:
        resp = await client.post(
            f"/api/admin/db-query", headers={"Authorization": f"Bearer {admin_secret}"},
            json={"sql": "SELECT 1 AS n, 'hello' AS greeting"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "columns" in data
    assert "rows" in data
    assert data["row_count"] >= 1
    assert "duration_ms" in data


@pytest.mark.asyncio
@pytest.mark.parametrize("sql", [
    "INSERT INTO events (id) VALUES (1)",
    "UPDATE events SET status='live'",
    "DELETE FROM events",
    "DROP TABLE events",
    "TRUNCATE events",
    "ALTER TABLE events ADD COLUMN x TEXT",
])
async def test_mutation_rejected(admin_secret, sql):
    async with _client() as client:
        resp = await client.post(
            f"/api/admin/db-query", headers={"Authorization": f"Bearer {admin_secret}"},
            json={"sql": sql},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_multi_statement_rejected(admin_secret):
    async with _client() as client:
        resp = await client.post(
            f"/api/admin/db-query", headers={"Authorization": f"Bearer {admin_secret}"},
            json={"sql": "SELECT 1; DROP TABLE events"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
@_needs_db
async def test_row_cap_enforced(admin_secret):
    async with _client() as client:
        resp = await client.post(
            f"/api/admin/db-query", headers={"Authorization": f"Bearer {admin_secret}"},
            json={"sql": "SELECT generate_series(1, 5000)", "limit": 10},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] <= 10
    assert data["truncated"] is True


@pytest.mark.asyncio
@_needs_db
async def test_with_cte_allowed(admin_secret):
    async with _client() as client:
        resp = await client.post(
            f"/api/admin/db-query", headers={"Authorization": f"Bearer {admin_secret}"},
            json={"sql": "WITH x AS (SELECT 1 AS n) SELECT * FROM x"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] == 1


@pytest.mark.asyncio
@_needs_db
async def test_limit_capped_at_1000(admin_secret):
    async with _client() as client:
        resp = await client.post(
            f"/api/admin/db-query", headers={"Authorization": f"Bearer {admin_secret}"},
            json={"sql": "SELECT generate_series(1, 5000)", "limit": 9999},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] <= 1000


# ---------------------------------------------------------------------------
# LAT-P027 (#1641) — the `postgres_semantics_tested` element of
# `query_plan_rail_authority_contract.json`.
#
# These need a REAL Postgres and are CI-only: this repo's sandbox cannot run one
# (`initdb` dies on `shmget`), so they are skipped locally and must not be reported
# as executed there. The pure policy is covered anywhere by
# `tests/test_sql_read_guard_execution_policy.py`; what can ONLY be proven here is
# the database's own behaviour, which is the thing the fix's premise rests on.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_needs_db
async def test_read_only_transaction_does_not_block_backend_management(admin_secret):
    """The premise of #1641, proven against Postgres rather than asserted.

    If READ ONLY *did* stop `pg_cancel_backend`, the guard added by LAT-P027 would be
    redundant and this test would say so. It does not: READ ONLY forbids writes to
    tables and sequences, and cancelling a backend is neither.

    `pid = 0` is deliberate — never a real backend, so the call is inert; it returns
    false with a warning. The assertion is narrow on purpose: whatever happens, it
    must not be SQLSTATE 25006 (`read_only_sql_transaction`). Anything else, including
    a permission refusal, leaves the premise standing.
    """
    from sqlalchemy import text

    from app.services.database import async_session_maker

    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        try:
            await session.execute(text("SELECT pg_cancel_backend(0)"))
        except Exception as exc:  # noqa: BLE001 - the SQLSTATE is the assertion
            state = getattr(getattr(exc, "orig", None), "sqlstate", None) or getattr(
                exc, "sqlstate", None
            )
            assert state != "25006", (
                "READ ONLY blocked pg_cancel_backend, so the LAT-P027 premise is wrong "
                "and the function policy should be re-examined"
            )
        await session.rollback()


@pytest.mark.asyncio
@_needs_db
@pytest.mark.parametrize(
    "body",
    [
        {"sql": "SELECT pg_cancel_backend(0)", "explain": True, "analyze": True},
        {"sql": "SELECT pg_advisory_lock(987654321)", "explain": True, "analyze": True},
        {"sql": "SELECT pg_sleep(0)", "explain": True, "analyze": True},
        {"sql": "SELECT pg_cancel_backend(0)"},  # the row path executes too
        {"sql": "SELECT pg_advisory_lock(987654321)"},
    ],
)
async def test_operational_functions_are_refused_against_real_postgres(admin_secret, body):
    """End to end, with a live database behind the route.

    The pure tests prove the policy refuses; this proves the refusal happens on the
    real wiring — a guard that is correct but not reached is not a guard.
    """
    async with _client() as client:
        resp = await client.post(
            "/api/admin/db-query",
            headers={"Authorization": f"Bearer {admin_secret}"},
            json=body,
        )
    assert resp.status_code == 400, resp.text
    assert "operational function" in json.dumps(resp.json())


@pytest.mark.asyncio
@_needs_db
async def test_a_real_analyze_still_runs_and_returns_measured_rows(admin_secret):
    """Non-vacuity against real Postgres: the capability survives the policy.

    `Actual Rows` only exists when the statement genuinely executed, so this
    distinguishes a working ANALYZE from a policy that refused everything.
    """
    async with _client() as client:
        resp = await client.post(
            "/api/admin/db-query",
            headers={"Authorization": f"Bearer {admin_secret}"},
            json={"sql": "SELECT count(*) FROM pg_class", "explain": True, "analyze": True},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["analyzed"] is True
    assert data["explain_mode"] == "ANALYZE, BUFFERS, FORMAT JSON"
    assert "explain_sql" not in data
    assert data["truncated"] is False
    assert "Actual Rows" in json.dumps(data["plan"])


@pytest.mark.asyncio
@_needs_db
async def test_a_real_database_error_is_typed_and_does_not_echo_the_statement(admin_secret):
    """A real Postgres error message, and what the caller is allowed to see of it."""
    async with _client() as client:
        resp = await client.post(
            "/api/admin/db-query",
            headers={"Authorization": f"Bearer {admin_secret}"},
            json={"sql": "SELECT * FROM no_such_table_xyzzy WHERE c = 'alex@example.com'"},
        )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["reason"] == "undefined_table"
    assert detail["correlation_id"]
    assert "alex@example.com" not in resp.text
    assert "no_such_table_xyzzy" not in resp.text
