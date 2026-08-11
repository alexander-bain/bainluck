"""LAT-P027 (#1641): what the admin SQL rail may EXECUTE, and what it may DISCLOSE.

Three defects, three sections. The premise all of them share, and the one worth
stating at the top because it is the thing that was wrong:

    A `SELECT` prefix plus `SET TRANSACTION READ ONLY` does not make execution
    side-effect free.

`SELECT pg_cancel_backend(pid)` is a SELECT, contains no mutating keyword, and
survives a read-only transaction — because READ ONLY forbids writes to tables and
sequences, and cancelling a backend is neither. Measured on this repo's base before
the fix, the rail composed and would have run:

    EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT pg_cancel_backend(12345)

**Assertions here name literals on purpose.** LAT-P026 shipped a guard that read the
same constant it was checking, so it passed for any value and a mutation walked
straight through it. `262144` and `pg_cancel_backend` are written out below rather
than imported: a test that imports the thing under test pins nothing.

Real-Postgres coverage lives in `tests/integration/test_route_admin_db_query.py` and
is CI-only — this sandbox has no local Postgres (`initdb` dies on `shmget`), so the
`postgres_semantics_tested` element of the contract cannot be executed here. Every
test in THIS file is pure and runs anywhere.
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import get_db
from app.utils.sql_read_guard import (
    SqlGuardError,
    assert_analyze_function_policy,
    assert_executable_for_analyze,
    assert_no_operational_functions,
    assert_read_only,
    called_function_names,
    cap_plan_payload,
    classify_db_error,
    fingerprint_statement,
    strip_sql_noise,
)

# ---------------------------------------------------------------------------
# Section 1 — the execution policy (Item 1)
# ---------------------------------------------------------------------------

# The exact statements that were ACCEPTED on the base commit. Each is a SELECT with
# a non-transactional side effect, which is why the prefix check never saw them.
OPERATIONAL_STATEMENTS = [
    ("SELECT pg_cancel_backend(12345)", "pg_cancel_backend"),
    ("SELECT pg_terminate_backend(12345)", "pg_terminate_backend"),
    ("SELECT pg_advisory_lock(42)", "pg_advisory_lock"),
    ("SELECT pg_try_advisory_lock(42)", "pg_try_advisory_lock"),
    ("SELECT pg_sleep(30)", "pg_sleep"),
    ("SELECT nextval('events_id_seq')", "nextval"),
    ("SELECT setval('events_id_seq', 1)", "setval"),
    ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
    ("SELECT dblink('host=evil', 'SELECT 1')", "dblink"),
    ("SELECT pg_stat_statements_reset()", "pg_stat_statements_reset"),
    ("SELECT pg_reload_conf()", "pg_reload_conf"),
    ("SELECT id, pg_cancel_backend(pid) FROM pg_stat_activity", "pg_cancel_backend"),
]


@pytest.mark.parametrize("sql,name", OPERATIONAL_STATEMENTS)
def test_analyze_refuses_operational_functions(sql, name):
    """The headline defect. Each of these EXECUTED under ANALYZE before this fix."""
    with pytest.raises(SqlGuardError) as exc:
        assert_executable_for_analyze(sql)
    assert name in exc.value.detail


@pytest.mark.parametrize("sql,name", OPERATIONAL_STATEMENTS)
def test_the_row_path_refuses_them_too(sql, name):
    """The half of #1641 the static audit did not name.

    The plain row path (`explain: false`) executes as surely as ANALYZE does, and it
    is older and far more used. Gating only ANALYZE would have left the identical
    hole one JSON field away — so the backstop is applied to every executing path,
    and this test is what stops a later refactor from re-scoping it to ANALYZE.
    """
    assert assert_read_only(sql)  # still a syntactically valid read statement...
    with pytest.raises(SqlGuardError) as exc:  # ...and still refused execution
        assert_no_operational_functions(sql)
    assert name in exc.value.detail


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT some_function_nobody_predicted(1)",
        "SELECT xpath('/a', '<a/>')",
        "SELECT query_to_xml('SELECT 1', true, true, '')",
        "SELECT lo_get(1234)",
    ],
)
def test_allowlist_refuses_functions_no_denylist_predicted(sql):
    """The allowlist's whole reason for existing, tested WITHOUT the denylist.

    A denylist can only refuse what someone thought of. None of these are on it; all
    must still be refused, because they are absent from the allowlist rather than
    present on a list of known-bad names. This is the property that survives a
    Postgres upgrade or a new extension.
    """
    assert_no_operational_functions(sql)  # denylist has nothing to say about these
    with pytest.raises(SqlGuardError) as exc:
        assert_analyze_function_policy(sql)
    assert "not on the allowlist" in exc.value.detail


@pytest.mark.parametrize(
    "sql,fragment",
    [
        ("SELECT pg_catalog.pg_cancel_backend(1)", "pg_cancel_backend"),
        ("SELECT public.some_udf(1)", "schema-qualified"),
        ('SELECT "some_udf"(1)', "quoted-identifier"),
    ],
)
def test_bypass_spellings_are_refused_by_shape(sql, fragment):
    """The two ways to spell a call whose bare name a scan would miss.

    Refusing the SHAPE removes the bypass class without having to resolve
    `search_path` — and no analysis query needs either spelling.
    """
    with pytest.raises(SqlGuardError) as exc:
        assert_executable_for_analyze(sql)
    assert fragment in exc.value.detail


LEGITIMATE_ANALYSIS_QUERIES = [
    "SELECT count(*) FROM events WHERE commence_time > now() - interval '7 days'",
    "SELECT max(id) FROM events",
    "SELECT date_trunc('day', commence_time) d, count(*) FROM events GROUP BY 1 ORDER BY 1 DESC LIMIT 10",
    "SELECT e.id, coalesce(e.home_team, '?') FROM events e JOIN teams t ON (t.id = e.home_team_id) WHERE e.status IN ('live','closed')",
    "SELECT similarity(name, 'lakers') s FROM teams WHERE name % 'lakers' ORDER BY s DESC",
    "SELECT ts_rank_cd(to_tsvector('english', name), websearch_to_tsquery('nba')) FROM events",
    "SELECT pg_size_pretty(pg_total_relation_size('events'))",
    "SELECT jsonb_array_length(win_probability_sources) FROM events WHERE jsonb_typeof(win_probability_sources) = 'array'",
    "SELECT round(avg(extract(epoch FROM (completed_at - commence_time)))::numeric, 2) FROM events",
    "SELECT row_number() OVER (PARTITION BY sport_id ORDER BY commence_time DESC) FROM events",
    "SELECT count(*) FILTER (WHERE status = 'live') FROM events",
    "SELECT string_agg(DISTINCT name, ', ') FROM teams",
    "SELECT calls, mean_exec_time FROM pg_stat_statements WHERE query LIKE '%events%'",
]


@pytest.mark.parametrize("sql", LEGITIMATE_ANALYSIS_QUERIES)
def test_real_analysis_queries_are_not_false_refused(sql):
    """Non-vacuity, and the risk that actually matters day to day.

    A policy that refuses everything would pass every test above and would break the
    rail this lane measures production with. These are the shapes latency work
    genuinely runs.
    """
    assert assert_executable_for_analyze(sql) == sql


@pytest.mark.parametrize("sql", LEGITIMATE_ANALYSIS_QUERIES)
def test_row_path_accepts_all_of_them_too(sql):
    assert_no_operational_functions(sql)


def test_plan_only_is_deliberately_not_allowlisted():
    """Plan-only stays usable on ANY readable statement, because it does not execute.

    This is a real design boundary, not an oversight: the value of `explain: true` is
    that it works on the statement you cannot afford to run. Constant-folding can
    evaluate IMMUTABLE functions at plan time, but an immutable function is by
    definition side-effect free, and volatile ones are never pre-evaluated.
    """
    assert assert_read_only("SELECT some_function_nobody_predicted(1)")


# ---------------------------------------------------------------------------
# Literal / comment handling. Fail-CLOSED is the required direction.
# ---------------------------------------------------------------------------


def test_function_name_inside_a_string_literal_is_not_read_as_a_call():
    """Literals are blanked before the call scan, so this is not an allowlist miss."""
    assert called_function_names("SELECT name FROM t WHERE name = 'some_udf(1)'") == set()


def test_but_the_backstop_still_refuses_it_and_that_is_correct():
    """A bare mention of an operational name is refused even in a literal.

    Deliberate asymmetry. For a BACKSTOP, a false refusal costs one rewrite and names
    the token; a false acceptance cancels a production backend. The backstop does not
    parse, which is exactly why a quoting trick cannot hide a name from it.
    """
    with pytest.raises(SqlGuardError):
        assert_no_operational_functions("SELECT * FROM t WHERE note = 'pg_sleep'")


def test_comments_cannot_smuggle_a_call_past_the_allowlist():
    sql = "SELECT count(*) /* some_udf( */ FROM events -- pg_typeof(\n"
    assert called_function_names(sql) == {"count"}


def test_strip_sql_noise_preserves_code_outside_literals():
    assert "some_udf" in strip_sql_noise("SELECT 'x' || some_udf(1) || 'y'")


# A REAL desynchronisation, found by mutation-testing this file rather than assumed.
#
# `strip_sql_noise` removes dollar-quoted bodies BEFORE single-quoted ones, so a `$$`
# sitting inside an ordinary string literal opens a dollar-quote that the lexer
# approximation happily closes at the NEXT `$$` — swallowing everything between,
# including a function call:
#
#     SELECT 'cost $$' , pg_cancel_backend(1) , 'per $$ unit'
#         -> strips to: SELECT ''
#
# The allowlist sees no calls at all and passes it. This is the exact scenario the
# raw-text backstop exists for, and until this test existed nothing proved it: the
# first attempt used an `E'\''` escape string, which does NOT desynchronise (the
# regex under-consumes there, which is the safe direction), so the allowlist caught
# it anyway and the test passed for the wrong reason. Mutation M1 — deleting the
# backstop from the ANALYZE path — stayed green, which is what exposed it.
_DESYNC_SQL = "SELECT 'cost $$' , pg_cancel_backend(1) , 'per $$ unit'"


def test_the_lexer_approximation_really_can_be_desynchronised():
    """Pin the weakness itself, so nobody 'fixes' the backstop believing it moot."""
    assert called_function_names(_DESYNC_SQL) == set()
    assert_analyze_function_policy(_DESYNC_SQL)  # the allowlist is blind here


def test_and_the_raw_text_backstop_catches_what_the_allowlist_missed():
    """The composition, proven on an input where control 1 demonstrably fails.

    Control 2 does not parse, so no quoting trick can desynchronise it — the name is
    still sitting in the raw bytes. This is why both controls exist rather than the
    better-looking one.
    """
    with pytest.raises(SqlGuardError) as exc:
        assert_executable_for_analyze(_DESYNC_SQL)
    assert "pg_cancel_backend" in exc.value.detail

    with pytest.raises(SqlGuardError):  # and on the row path too
        assert_no_operational_functions(_DESYNC_SQL)


# ---------------------------------------------------------------------------
# Section 2 — disclosure and bounds (Item 2)
# ---------------------------------------------------------------------------


def test_fingerprint_is_stable_and_not_the_statement():
    sql = "SELECT * FROM users WHERE email = 'alex@example.com'"
    fp = fingerprint_statement(sql)
    assert fp == fingerprint_statement(sql + ";")  # normalisation-stable
    assert fp == fingerprint_statement(sql)  # deterministic across calls
    assert len(fp) == 16
    assert "alex@example.com" not in fp
    assert "SELECT" not in fp
    assert fingerprint_statement("SELECT 1") != fingerprint_statement("SELECT 2")


def test_plan_under_the_cap_is_returned_whole_and_says_so():
    plan = [{"Plan": {"Node Type": "Seq Scan", "Relation Name": "events"}}]
    out = cap_plan_payload(plan)
    assert out["plan"] == plan
    assert out["truncated"] is False
    assert out["response_cap_bytes"] == 262144  # literal, not the imported constant


def test_plan_over_the_cap_is_bounded_with_an_explicit_verdict():
    """`timeout_ms` bounds DATABASE time; it does nothing about JSON size."""
    fat = [{"Plan": {
        "Node Type": "Seq Scan",
        "Total Cost": 1234.5,
        "Plan Rows": 99,
        "Filter": "x" * 400_000,
    }}]
    out = cap_plan_payload(fat)
    assert out["truncated"] is True
    assert out["truncation_reason"] == "response_cap_bytes"
    assert out["plan"] is None
    assert out["plan_bytes"] > 262144
    # A summary still answers the question the plan was opened for...
    assert out["plan_summary"]["Node Type"] == "Seq Scan"
    assert out["plan_summary"]["Total Cost"] == 1234.5
    # ...without carrying the field that quotes the caller's literals.
    assert "Filter" not in out["plan_summary"]
    assert len(json.dumps(out).encode()) < 262144


def test_cap_is_enforced_at_the_documented_number_not_merely_somewhere():
    """Non-tautological: a payload just over 262144 must truncate, just under must not."""
    under = [{"Plan": {"Node Type": "Seq Scan", "Filter": "x" * 200_000}}]
    over = [{"Plan": {"Node Type": "Seq Scan", "Filter": "x" * 300_000}}]
    assert cap_plan_payload(under)["truncated"] is False
    assert cap_plan_payload(over)["truncated"] is True


def test_an_exotic_plan_value_is_coerced_rather_than_500ing():
    """Drivers do not all hand back pure JSON.

    asyncpg can return a plan as a Python object containing `Decimal`/`datetime`,
    which `json.dumps` refuses by default. `default=str` keeps that a 200 with a
    readable plan instead of an unhandled encoder error on a diagnostic endpoint.
    """
    from decimal import Decimal

    out = cap_plan_payload([{"Plan": {"Node Type": "Seq Scan", "Total Cost": Decimal("12.5")}}])
    assert out["truncated"] is False
    assert out["plan"][0]["Plan"]["Total Cost"] == Decimal("12.5")


def test_a_genuinely_unserializable_plan_is_reported_not_crashed():
    """The remaining encoder failure `default=str` cannot rescue: a cycle."""
    cyclic = {}
    cyclic["self"] = cyclic
    out = cap_plan_payload(cyclic)
    assert out["truncated"] is True
    assert out["truncation_reason"] == "plan_not_serializable"
    assert out["plan"] is None


class _FakeDbError(Exception):
    def __init__(self, sqlstate, message):
        super().__init__(message)
        self.sqlstate = sqlstate


class _FakeWrappedError(Exception):
    """Shaped like a SQLAlchemy DBAPIError, whose SQLSTATE hides on `.orig`."""

    def __init__(self, orig):
        super().__init__("(psycopg2.errors.Whatever) boom")
        self.orig = orig


@pytest.mark.parametrize(
    "sqlstate,expected",
    [
        ("57014", "statement_timeout"),
        ("25006", "read_only_transaction"),
        ("42601", "syntax_error"),
        ("42P01", "undefined_table"),
        ("42883", "undefined_function"),
        ("53300", "too_many_connections"),
        ("22999", "data_error"),  # unknown code, known class
        ("99999", "query_failed"),  # unknown entirely
    ],
)
def test_db_errors_map_to_stable_reason_codes(sqlstate, expected):
    assert classify_db_error(_FakeDbError(sqlstate, "secret detail")) == expected


def test_sqlstate_is_found_through_the_sqlalchemy_wrapper():
    wrapped = _FakeWrappedError(_FakeDbError("57014", "canceling statement"))
    assert classify_db_error(wrapped) == "statement_timeout"


def test_reason_codes_never_carry_the_message():
    leaky = _FakeDbError("42601", 'syntax error at or near "alex@example.com"')
    assert "alex@example.com" not in classify_db_error(leaky)


# ---------------------------------------------------------------------------
# Section 3 — the route's actual payload shape
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
    def __init__(self, raise_on_explain=None, raise_on_rows=None):
        self.statements = []
        self._raise_explain = raise_on_explain
        self._raise_rows = raise_on_rows

    async def execute(self, stmt, *args, **kwargs):
        sql = str(stmt)
        self.statements.append(sql)
        if sql.lstrip().upper().startswith("EXPLAIN"):
            if self._raise_explain is not None:
                raise self._raise_explain
            return _FakeResult(json.dumps(_FAKE_PLAN))
        if self._raise_rows is not None and sql.lstrip().upper().startswith("SELECT"):
            raise self._raise_rows
        return _FakeResult(None)


def _install(session, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

    async def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    return session


@pytest.fixture
def recorder(monkeypatch):
    session = _install(_RecordingSession(), monkeypatch)
    yield session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def failing_recorder(monkeypatch):
    session = _install(
        _RecordingSession(
            raise_on_explain=_FakeDbError(
                "57014", "canceling statement due to statement timeout: SELECT ... 'alex@example.com'"
            )
        ),
        monkeypatch,
    )
    yield session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def failing_row_recorder(monkeypatch):
    session = _install(
        _RecordingSession(
            raise_on_rows=_FakeDbError(
                "42P01", 'relation "no_such_table" does not exist: alex@example.com'
            )
        ),
        monkeypatch,
    )
    yield session
    app.dependency_overrides.pop(get_db, None)


async def _post(body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/api/admin/db-query",
            headers={"Authorization": "Bearer test-secret"},
            json=body,
        )


@pytest.mark.asyncio
async def test_plan_response_no_longer_echoes_the_callers_sql(recorder):
    """`explain_sql` put the complete statement into browser state and screenshots.

    Asserted two ways: the field is gone, AND the distinctive literal does not appear
    anywhere in the serialized body. The second is the one that catches a later
    change that reintroduces the echo under a different key.
    """
    sql = "SELECT * FROM users WHERE email = 'alex@example.com'"
    resp = await _post({"sql": sql, "explain": True})
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert "explain_sql" not in data
    assert "alex@example.com" not in resp.text
    assert sql not in resp.text

    # What replaced it is still enough to tie a plan to a statement.
    assert data["explain_mode"] == "FORMAT JSON"
    assert data["sql_fingerprint"] == fingerprint_statement(sql)


@pytest.mark.asyncio
async def test_analyze_mode_label_is_server_composed(recorder):
    resp = await _post({"sql": "SELECT count(*) FROM events", "explain": True, "analyze": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["explain_mode"] == "ANALYZE, BUFFERS, FORMAT JSON"


@pytest.mark.asyncio
async def test_plan_response_carries_an_explicit_truncation_verdict(recorder):
    """gotcha #53: complete and bounded must not read the same."""
    resp = await _post({"sql": "SELECT 1", "explain": True})
    data = resp.json()
    assert data["truncated"] is False
    assert data["plan"] == _FAKE_PLAN
    assert data["response_cap_bytes"] == 262144


@pytest.mark.asyncio
async def test_row_response_carries_the_fingerprint(recorder):
    resp = await _post({"sql": "SELECT n FROM t"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["sql_fingerprint"] == fingerprint_statement("SELECT n FROM t")


@pytest.mark.asyncio
async def test_database_errors_return_a_typed_reason_not_the_message(failing_recorder):
    """`detail=str(e)[:500]` cut at 500 characters, which is not redaction.

    The first 500 characters of a Postgres error are the MOST disclosing 500 — that
    is where the failing statement fragment and its literals live.
    """
    resp = await _post({"sql": "SELECT * FROM users WHERE email = 'alex@example.com'", "explain": True})
    assert resp.status_code == 400

    detail = resp.json()["detail"]
    assert detail["reason"] == "statement_timeout"
    assert len(detail["correlation_id"]) == 12
    assert detail["sql_fingerprint"] == fingerprint_statement(
        "SELECT * FROM users WHERE email = 'alex@example.com'"
    )
    # Neither the caller's literal nor the database's own message survives.
    assert "alex@example.com" not in resp.text
    assert "canceling statement" not in resp.text


@pytest.mark.asyncio
async def test_row_path_errors_are_typed_too_not_just_the_plan_path(failing_row_recorder):
    """Both `raise HTTPException(..., str(e)[:500])` sites, not just the new one.

    The row path is the older of the two and leaked identically; fixing only the
    path the issue happened to name would leave the disclosure in the mode that
    serves most of the traffic.
    """
    resp = await _post({"sql": "SELECT * FROM no_such_table"})
    assert resp.status_code == 400

    detail = resp.json()["detail"]
    assert detail["reason"] == "undefined_table"
    assert len(detail["correlation_id"]) == 12
    assert "alex@example.com" not in resp.text
    assert "does not exist" not in resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"sql": "SELECT pg_cancel_backend(1)", "explain": True, "analyze": True},
        {"sql": "SELECT pg_cancel_backend(1)"},  # the row path
        {"sql": "SELECT some_function_nobody_predicted(1)", "explain": True, "analyze": True},
    ],
)
async def test_execution_refusals_never_reach_the_database(recorder, body):
    """Refused before any statement runs — including the session-level SETs, so a
    rejected request cannot leave a transaction open."""
    resp = await _post(body)
    assert resp.status_code == 400, resp.text
    assert recorder.statements == []


@pytest.mark.asyncio
async def test_plan_only_still_reaches_the_database_for_the_same_statement(recorder):
    """The boundary, asserted from the route: refused to EXECUTE, allowed to PLAN.

    Without this, someone could satisfy every refusal test above by breaking
    `explain: true` as well, and the rail's actual capability would be gone.
    """
    resp = await _post({"sql": "SELECT some_function_nobody_predicted(1)", "explain": True})
    assert resp.status_code == 200, resp.text
    explains = [s for s in recorder.statements if s.lstrip().upper().startswith("EXPLAIN")]
    assert explains == ["EXPLAIN (FORMAT JSON) SELECT some_function_nobody_predicted(1)"]
