"""LAT-P019 (#1619): guards for the admin EXPLAIN rail and the read-only SQL policy.

Two layers, both runnable WITHOUT a database — which is the point. The pre-existing
db-query guards in `tests/integration/test_route_admin_db_query.py` are
`skipif("DATABASE_URL" not in environ)`, and this repo's sandbox has no local
Postgres, so those guards only ever execute in CI. Adding plan support — the one
change to this endpoint that can actually *execute* something (`EXPLAIN ANALYZE`) —
under a set of tests nobody can run locally would be the wrong trade.

Layer 1: pure functions in `app.utils.sql_read_guard`.
Layer 2: the route, driven through a recording session that captures the SQL the
code path really emits. Per LAT-P018's finding, a guard that hand-writes a query
resembling the shipped one cannot catch a defect in the shipped one; the statements
asserted below are the statements the endpoint actually executed.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import get_db
from app.utils.sql_read_guard import (
    DEFAULT_STATEMENT_TIMEOUT_MS,
    MAX_EXPLAIN_TIMEOUT_MS,
    MAX_ROW_CAP,
    MIN_EXPLAIN_TIMEOUT_MS,
    SqlGuardError,
    assert_executable_for_analyze,
    assert_read_only,
    build_explain_sql,
    needs_limit_wrap,
    normalize_statement,
    resolve_explain_timeout_ms,
    resolve_row_cap,
)

# ---------------------------------------------------------------------------
# Layer 1 — pure policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "EXPLAIN SELECT 1",
        "EXPLAIN ANALYZE SELECT 1",
        "explain (analyze) select 1",
        "  EXPLAIN\n SELECT 1",
    ],
)
def test_caller_supplied_explain_is_still_rejected(sql):
    """The rail composes EXPLAIN server-side; it is never accepted as input.

    This is the guard that keeps the allowlist load-bearing. If a future change
    widens the prefix list to admit EXPLAIN, this test is what fails.
    """
    with pytest.raises(SqlGuardError) as exc:
        assert_read_only(sql)
    assert "must start with SELECT or WITH" in exc.value.detail


@pytest.mark.parametrize(
    "sql,fragment",
    [
        ("SELECT 1; DROP TABLE events", "Multi-statement"),
        ("INSERT INTO events (id) VALUES (1)", "Only SELECT"),
        ("UPDATE events SET status='live'", "Only SELECT"),
        ("DELETE FROM events", "Only SELECT"),
        ("DROP TABLE events", "Only SELECT"),
        ("TRUNCATE events", "Only SELECT"),
        ("CREATE INDEX ix ON events (id)", "Only SELECT"),
        ("COPY events TO '/tmp/x'", "Only SELECT"),
        ("VACUUM", "must start with SELECT or WITH"),
        ("", "must start with SELECT or WITH"),
    ],
)
def test_read_only_policy_rejections(sql, fragment):
    with pytest.raises(SqlGuardError) as exc:
        assert_read_only(sql)
    assert fragment in exc.value.detail


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select 1",
        "WITH x AS (SELECT 1 AS n) SELECT * FROM x",
        "  SELECT 1  ;  ",
    ],
)
def test_read_only_policy_accepts(sql):
    assert assert_read_only(sql)


def test_trailing_semicolon_stripped_not_treated_as_multi_statement():
    assert normalize_statement("SELECT 1;") == "SELECT 1"
    assert assert_read_only("SELECT 1;") == "SELECT 1"


def test_analyze_refuses_leading_with():
    """Planning a CTE is safe; EXECUTING one is where data-modifying CTEs live."""
    sql = "WITH x AS (SELECT 1 AS n) SELECT * FROM x"
    assert assert_read_only(sql)  # fine to plan
    with pytest.raises(SqlGuardError) as exc:
        assert_executable_for_analyze(sql)  # not fine to execute
    assert "beginning with SELECT" in exc.value.detail


def test_analyze_refuses_data_modifying_cte():
    with pytest.raises(SqlGuardError):
        assert_executable_for_analyze(
            "WITH x AS (SELECT 1) INSERT INTO events (id) SELECT 1"
        )


def test_analyze_accepts_plain_select():
    assert assert_executable_for_analyze("SELECT max(id) FROM events") == (
        "SELECT max(id) FROM events"
    )


def test_build_explain_sql_shapes():
    assert build_explain_sql("SELECT 1") == "EXPLAIN (FORMAT JSON) SELECT 1"
    assert build_explain_sql("SELECT 1", analyze=True) == (
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT 1"
    )


def test_plan_only_never_emits_analyze():
    """The default mode must not execute the statement."""
    assert "ANALYZE" not in build_explain_sql("SELECT * FROM events")


@pytest.mark.parametrize(
    "requested,expected",
    [
        (None, DEFAULT_STATEMENT_TIMEOUT_MS),
        (0, MIN_EXPLAIN_TIMEOUT_MS),
        (-5, MIN_EXPLAIN_TIMEOUT_MS),
        (1, MIN_EXPLAIN_TIMEOUT_MS),
        (5000, 5000),
        (999_999, MAX_EXPLAIN_TIMEOUT_MS),
        ("nonsense", DEFAULT_STATEMENT_TIMEOUT_MS),
    ],
)
def test_explain_timeout_is_always_bounded(requested, expected):
    assert resolve_explain_timeout_ms(requested) == expected


@pytest.mark.parametrize(
    "limit,expected", [(None, MAX_ROW_CAP), (0, 1), (-3, 1), (500, 500), (9999, MAX_ROW_CAP)]
)
def test_row_cap_is_always_bounded(limit, expected):
    assert resolve_row_cap(limit) == expected


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("SELECT 1", True),
        ("SELECT 1 LIMIT 5", False),
        ("SELECT 1 ORDER BY 1 LIMIT 5", False),
        ("SELECT 1 FETCH FIRST 5 ROWS ONLY", False),
    ],
)
def test_needs_limit_wrap(sql, expected):
    assert needs_limit_wrap(sql) is expected


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM t ORDER BY limit_col",  # column name contains "limit"
        "SELECT * FROM t ORDER BY unlimited",  # ...as a substring of another word
        "SELECT * FROM t WHERE note='fetch'",  # "fetch" anywhere in the statement
    ],
)
def test_needs_limit_wrap_substring_quirk_is_recorded_not_fixed_here(sql):
    """PRE-EXISTING behaviour, pinned deliberately rather than corrected.

    The heuristic is a substring test (`"limit" in sql.split("order")[-1]`), so any
    statement that merely CONTAINS "limit" or "fetch" is treated as already bounded
    and the server-side row cap is not appended. Found by LAT-P019 while extracting
    this policy; filed rather than fixed, because changing the row rail's behaviour
    is not in a queue whose deliverable is the plan rail.

    It is bounded in the direction that matters: the endpoint still calls
    `fetchmany(row_cap)`, so the CLIENT never receives more than the cap. The cost
    is server-side — Postgres materialises the full result set — which is a latency
    defect, not a row-cap breach. This test exists so the fix, when it lands, has to
    delete a test that says "this is wrong" rather than quietly change a `True`.
    """
    assert needs_limit_wrap(sql) is False


# ---------------------------------------------------------------------------
# Layer 2 — the route, with the SQL captured from the code path
# ---------------------------------------------------------------------------

_FAKE_PLAN = [{"Plan": {"Node Type": "Seq Scan", "Relation Name": "events"}}]


class _FakeResult:
    def __init__(self, payload):
        self._payload = payload

    def scalar(self):
        return self._payload

    def keys(self):
        return ["n"]

    def fetchmany(self, n):
        return [(1,)]


class _RecordingSession:
    """Captures every statement the endpoint executes, in order."""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt, *args, **kwargs):
        sql = str(stmt)
        self.statements.append(sql)
        if sql.lstrip().upper().startswith("EXPLAIN"):
            import json

            return _FakeResult(json.dumps(_FAKE_PLAN))
        return _FakeResult(None)


@pytest.fixture
def recorder(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "test-secret")
    session = _RecordingSession()

    async def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    yield session
    app.dependency_overrides.pop(get_db, None)


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _post(body):
    async with _client() as client:
        return await client.post(
            "/api/admin/db-query",
            headers={"Authorization": "Bearer test-secret"},
            json=body,
        )


@pytest.mark.asyncio
async def test_plan_path_emits_bound_and_read_only_and_no_limit(recorder):
    resp = await _post({"sql": "SELECT max(x) FROM big_table", "explain": True})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["explain"] is True
    assert data["analyzed"] is False
    assert data["plan"] == _FAKE_PLAN
    assert data["statement_timeout_ms"] == DEFAULT_STATEMENT_TIMEOUT_MS

    stmts = recorder.statements
    assert any("SET TRANSACTION READ ONLY" in s for s in stmts), stmts
    assert any("statement_timeout = '10000ms'" in s for s in stmts), stmts

    explain_stmts = [s for s in stmts if s.lstrip().upper().startswith("EXPLAIN")]
    assert len(explain_stmts) == 1, stmts
    # Plan fidelity: the planned statement must be the caller's statement verbatim.
    # A row-cap LIMIT here would return the plan of a query production never runs.
    assert explain_stmts[0] == "EXPLAIN (FORMAT JSON) SELECT max(x) FROM big_table"
    assert "LIMIT" not in explain_stmts[0]


@pytest.mark.asyncio
async def test_analyze_path_emits_analyze_and_buffers(recorder):
    resp = await _post({"sql": "SELECT 1", "explain": True, "analyze": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["analyzed"] is True
    explain_stmts = [s for s in recorder.statements if s.lstrip().upper().startswith("EXPLAIN")]
    assert explain_stmts == ["EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT 1"]


@pytest.mark.asyncio
async def test_plan_timeout_is_clamped_on_the_wire(recorder):
    resp = await _post({"sql": "SELECT 1", "explain": True, "timeout_ms": 999999})
    assert resp.status_code == 200, resp.text
    assert resp.json()["statement_timeout_ms"] == MAX_EXPLAIN_TIMEOUT_MS
    assert any(
        f"statement_timeout = '{MAX_EXPLAIN_TIMEOUT_MS}ms'" in s for s in recorder.statements
    ), recorder.statements


@pytest.mark.asyncio
async def test_row_path_still_appends_the_row_cap(recorder):
    """The pre-existing behaviour must be untouched by the plan addition."""
    resp = await _post({"sql": "SELECT n FROM t", "limit": 25})
    assert resp.status_code == 200, resp.text
    assert any(s == "SELECT n FROM t LIMIT 25" for s in recorder.statements), recorder.statements
    assert not any(s.lstrip().upper().startswith("EXPLAIN") for s in recorder.statements)


@pytest.mark.asyncio
async def test_row_path_still_bounded_read_only(recorder):
    await _post({"sql": "SELECT n FROM t"})
    assert any("SET TRANSACTION READ ONLY" in s for s in recorder.statements)
    assert any("statement_timeout = '10s'" in s for s in recorder.statements)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,fragment",
    [
        ({"sql": "SELECT 1", "analyze": True}, "requires `explain: true`"),
        ({"sql": "SELECT 1", "timeout_ms": 5000}, "only supported with `explain: true`"),
        (
            {"sql": "WITH x AS (SELECT 1) SELECT * FROM x", "explain": True, "analyze": True},
            "beginning with SELECT",
        ),
        (
            {"sql": "EXPLAIN SELECT 1", "explain": True},
            "must start with SELECT or WITH",
        ),
        (
            {"sql": "UPDATE events SET x=1", "explain": True, "analyze": True},
            "Only SELECT",
        ),
        (
            {"sql": "SELECT 1; DROP TABLE events", "explain": True},
            "Multi-statement",
        ),
    ],
)
async def test_plan_path_rejections_never_reach_the_database(recorder, body, fragment):
    resp = await _post(body)
    assert resp.status_code == 400, resp.text
    assert fragment in resp.json()["detail"]
    # The refusal must happen before any statement is executed — including the
    # session-level SETs, so a rejected request cannot leave a transaction open.
    assert recorder.statements == []


# ---------------------------------------------------------------------------
# LAT-P020 — the gate signal. An unknown field must ERROR, never silently 200.
#
# Named failure: before the EXPLAIN rail existed, `POST /api/admin/db-query`
# with `explain: true` returned HTTP 200 with the field dropped and the query
# EXECUTED. By status code that is indistinguishable from a server honouring the
# request, so LAT-P020's Phase-0 capability gate read the rail as PRESENT when it
# was absent, and the lane spent a cycle on a scope it could not run.
#
# Same shape as gotcha #53: one response for "did it" and "ignored it" lets the
# caller infer a capability that is not there.
# ---------------------------------------------------------------------------
import pytest
from pydantic import ValidationError

from app.routes.admin_data_quality import _DbQueryRequest


def test_unknown_field_is_rejected_not_silently_dropped():
    """The whole point: a field the server does not understand must be loud."""
    with pytest.raises(ValidationError) as exc:
        _DbQueryRequest(sql="SELECT 1", not_a_real_option=True)
    # FastAPI turns this into a 422, which a capability probe can read.
    assert "not_a_real_option" in str(exc.value)


def test_known_fields_all_still_accepted():
    """Non-vacuity: extra="forbid" must not have broken the real surface.

    A guard that rejects everything would pass the test above and be useless.
    """
    req = _DbQueryRequest(
        sql="SELECT 1", limit=10, explain=True, analyze=False, timeout_ms=250
    )
    assert req.sql == "SELECT 1"
    assert req.limit == 10
    assert req.explain is True
    assert req.analyze is False
    assert req.timeout_ms == 250


def test_the_minimal_request_still_works():
    req = _DbQueryRequest(sql="SELECT 1")
    assert req.limit == 500
    assert req.explain is False
    assert req.analyze is False
    assert req.timeout_ms is None


def test_a_misspelled_known_field_is_caught_too():
    """The realistic case -- `explain_analyze` instead of `analyze`.

    Under extra="ignore" this ran a plain query and returned 200, so the caller
    believed it had a plan and got rows.
    """
    with pytest.raises(ValidationError):
        _DbQueryRequest(sql="SELECT 1", explain_analyze=True)
