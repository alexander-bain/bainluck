"""LAT-P017 (#1608) — the statement-timeout class that fails soft as 200/green.

Guards a CLASS of defect, not four instances of it: a measurement surface that
returns HTTP 200 / reports green while omitting the thing it was supposed to
measure. Gotcha #53 — "an empty 200 is not an absence, it is a response shape".

Production evidence these guards were written against (2026-08-09, deployed
30d10863, admin reads via /api/admin/*):

  GET /api/admin/dashboard  ->  HTTP 200 in 18,898ms with 5 of 9 panels degraded
      source_coverage      = [{"error": QueryCanceledError ...}]
      futures_coverage     = [{"error": QueryCanceledError ...}]   (COPY of the
                             same exception — this query never actually ran)
      coverage_trend       = []            <-- SILENT. no marker at all.
      database             = {"error": InFailedSQLTransactionError ...}  (cascade)
      game_state_coverage  = [{"error": InFailedSQLTransactionError ...}] (cascade)

  GET /api/admin/grid-sentinel/last  ->  mlb verdict=green, freshness skipped
                                         nba verdict=green, freshness skipped

Every assertion below is about call shape / compiled SQL / pure-function
behaviour. None is a wall-clock number, so none is flaky in CI (LAT-P005).
"""

from __future__ import annotations

import ast
import importlib
import inspect

import pytest

# The Celery task registry shadows the module name in app/tasks/__init__.py, so
# `from app.tasks import grid_sentinel` yields the TASK proxy, not the module.
gs = importlib.import_module("app.tasks.grid_sentinel")
ad = importlib.import_module("app.utils.admin_dashboard")


def _sql_literals(fn) -> str:
    """Every string CONSTANT in fn's body, excluding its docstring.

    LAT-P016's lesson, hit again while writing these guards: an assertion over
    raw `inspect.getsource` passes on a substring that appears only in the
    function's own prose. Parsing to AST and dropping the docstring means these
    guards can only be satisfied by the SQL itself.
    """
    tree = ast.parse(inspect.getsource(fn).lstrip())
    body = tree.body[0].body  # type: ignore[attr-defined]
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    out = []
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out.append(node.value)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 1. The cascade: one panel's failure must not abort a sibling's transaction
# ---------------------------------------------------------------------------

class _FakeSession:
    """Records rollbacks and can be told to fail, like an aborted asyncpg txn."""

    def __init__(self, fail_on: set[str] | None = None):
        self.rollbacks = 0
        self.executed: list[str] = []
        self.fail_on = fail_on or set()
        self.aborted = False

    async def execute(self, stmt, *a, **kw):
        sql = str(stmt)
        self.executed.append(sql)
        if self.aborted:
            raise RuntimeError("InFailedSQLTransactionError: current transaction is aborted")
        for marker in self.fail_on:
            if marker in sql:
                self.aborted = True
                raise RuntimeError("QueryCanceledError: canceling statement due to statement timeout")
        return None

    async def rollback(self):
        self.rollbacks += 1
        self.aborted = False


@pytest.mark.asyncio
async def test_panel_failure_rolls_back_so_the_next_panel_survives():
    """THE CASCADE FIX. A failing panel must leave the session usable."""
    db = _FakeSession()

    async def boom():
        raise RuntimeError("QueryCanceledError: canceling statement")

    out = await ad.run_db_panel(db, "p1", boom, on_error=lambda e: {"error": e})
    assert "error" in out
    assert db.rollbacks == 1, "a failed panel MUST roll back or it poisons its siblings"

    async def fine():
        return {"ok": True}

    out2 = await ad.run_db_panel(db, "p2", fine, on_error=lambda e: {"error": e})
    assert out2 == {"ok": True}, "the panel after a failure must still succeed"


@pytest.mark.asyncio
async def test_successful_panel_also_rolls_back_so_set_local_cannot_leak():
    """SET LOCAL is transaction-scoped; without a rollback on the success path
    one panel's statement_timeout silently governs every later panel."""
    db = _FakeSession()

    async def fine():
        return []

    await ad.run_db_panel(db, "p", fine, on_error=lambda e: [], statement_timeout="10s")
    assert db.rollbacks == 1
    assert any("SET LOCAL statement_timeout = '10s'" in s for s in db.executed)


@pytest.mark.asyncio
async def test_statement_timeout_is_set_inside_the_panel_transaction():
    """The bound must be issued AFTER the previous rollback, i.e. inside this
    panel's own transaction — not once for the whole section."""
    db = _FakeSession()

    order: list[str] = []

    async def fine():
        order.append("query")
        return []

    async def rb():
        order.append("rollback")
        db.rollbacks += 1
    db.rollback = rb  # type: ignore[method-assign]

    real_execute = db.execute

    async def exec_spy(stmt, *a, **kw):
        if "SET LOCAL" in str(stmt):
            order.append("set_local")
        return await real_execute(stmt, *a, **kw)
    db.execute = exec_spy  # type: ignore[method-assign]

    await ad.run_db_panel(db, "p", fine, on_error=lambda e: [], statement_timeout="10s")
    assert order == ["set_local", "query", "rollback"]


def test_every_db_panel_in_the_route_goes_through_the_isolator():
    """CLASS guard, not an instance guard.

    The cascade returns the moment ANY db-backed panel is awaited directly,
    because a direct call cannot roll the shared session back. Parsed from the
    AST, not matched as a substring, so a mention in a comment or docstring
    cannot satisfy it.
    """
    from app.routes import admin as admin_routes

    src = inspect.getsource(admin_routes.operations_dashboard)
    tree = ast.parse(src.lstrip())

    db_panels = {"build_database_section", "build_game_state_section"}
    direct_awaits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            fn = node.value.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name in db_panels:
                direct_awaits.append(name)

    assert not direct_awaits, (
        f"{direct_awaits} are awaited directly in the dashboard route. They must "
        "go through run_db_panel, which rolls back on failure; a direct await "
        "re-opens the InFailedSQLTransactionError cascade."
    )
    assert "run_db_panel" in src


def test_db_panels_do_not_swallow_their_own_exceptions():
    """A panel that catches its own error hides it from the isolator, so the
    rollback never happens and the cascade survives the isolator entirely."""
    for fn in (ad.build_database_section, ad.build_game_state_section):
        tree = ast.parse(inspect.getsource(fn).lstrip())
        handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]
        catch_alls = [
            h for h in handlers
            if h.type is None or getattr(h.type, "id", None) == "Exception"
        ]
        assert not catch_alls, (
            f"{fn.__name__} catches Exception itself. Error handling belongs to "
            "run_db_panel so the session is rolled back; a local handler returns "
            "an error marker while leaving the transaction aborted."
        )


# ---------------------------------------------------------------------------
# 2. Failure must never present as absence (gotcha #53)
# ---------------------------------------------------------------------------

class _FakeResult:
    def all(self):
        return []

    def one(self):
        raise AssertionError("not used by this path")

    def fetchall(self):
        return []

    def scalar(self):
        return None


class _SelectiveFailSession(_FakeSession):
    """Fails only the query containing a marker; others return empty results."""

    async def execute(self, stmt, *a, **kw):
        sql = str(stmt)
        self.executed.append(sql)
        if self.aborted:
            raise RuntimeError("InFailedSQLTransactionError: transaction is aborted")
        for marker in self.fail_on:
            if marker in sql:
                self.aborted = True
                raise RuntimeError(
                    "QueryCanceledError: canceling statement due to statement timeout"
                )
        return _FakeResult()


@pytest.mark.asyncio
async def test_coverage_trend_failure_is_marked_not_silently_empty():
    """The one that hid this bug for days.

    coverage_trend degraded to a bare [] — identical to the legitimate "no trend
    data" answer — so the panel looked merely empty instead of broken.

    Drives the REAL build_source_coverage_section wiring. An earlier version of
    this test called run_db_panel with an on_error lambda it supplied itself,
    which meant it asserted its own argument and stayed green when production
    was reverted to returning []. Mutation-checking caught it; it is written
    against the shipped call path now.
    """
    from datetime import datetime, timezone

    db = _SelectiveFailSession(fail_on={"WITH ev AS"})
    source_coverage, coverage_trend, futures_coverage = (
        await ad.build_source_coverage_section(db, datetime.now(timezone.utc))
    )

    assert coverage_trend and "error" in coverage_trend[0], (
        "a failed coverage_trend must carry an error marker; returning [] makes "
        "'I could not look' indistinguishable from 'there is nothing to report'"
    )
    # ...and the sibling that did NOT fail must not inherit the failure.
    assert futures_coverage == [], (
        "futures_coverage ran fine; it must not report a neighbour's exception"
    )


def test_source_coverage_section_isolates_its_three_outputs():
    """Previously ONE try produced ([err], [], [err]) — futures_coverage
    reported a failure it never suffered, its error string copied from a
    neighbour."""
    src = inspect.getsource(ad.build_source_coverage_section)
    tree = ast.parse(src.lstrip())

    handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]
    assert not handlers, (
        "build_source_coverage_section must not wrap its queries in a shared "
        "try — that is what made one timeout speak for three outputs."
    )

    isolated = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == "run_db_panel"
    ]
    assert len(isolated) >= 3, (
        "each of source_coverage / coverage_trend / futures_coverage must run in "
        f"its own isolated panel; found {len(isolated)}"
    )


# ---------------------------------------------------------------------------
# 3. The queries whose cost scaled with table volume, not with the answer
# ---------------------------------------------------------------------------

def test_event_source_coverage_scopes_win_prob_snapshots_to_the_window():
    """The unbounded/mis-indexed win-prob arm is what actually timed out."""
    sql = _sql_literals(ad._query_event_source_coverage)
    assert "JOIN recent_events re ON re.id = wp.event_id" in sql, (
        "win_prob_snapshots must be scoped to the windowed events"
    )
    assert "wp.captured_at" not in sql, (
        "captured_at is not in ix_winprob_event_source (event_id, source); "
        "re-adding it breaks the index-only scan and restores the timeout "
        "(measured 549ms -> 7,927ms on an identical window)"
    )
    assert "win_probability_sources" not in sql, (
        "the large JSONB column is selected but never read"
    )


def test_event_source_coverage_does_not_row_multiply():
    """Pre-aggregate to one row per event, so COUNT(*) is an event count."""
    sql = _sql_literals(ad._query_event_source_coverage)
    assert "FROM wp_pairs GROUP BY event_id" in sql
    assert "FROM pm_pairs GROUP BY event_id" in sql
    assert "COUNT(DISTINCT CASE WHEN" not in sql, (
        "COUNT(DISTINCT ...) here is the tell of a row-multiplying join"
    )


def test_coverage_trend_scopes_both_source_ctes():
    """The second, independent timeout: a DISTINCT over the ENTIRE
    win_prob_snapshots table to answer a 14-day question."""
    sql = _sql_literals(ad._query_coverage_trend)
    assert "JOIN ev ON ev.id = wp.event_id" in sql
    assert "JOIN ev ON ev.id = fm.event_id" in sql
    unscoped = [
        ln for ln in sql.splitlines()
        if "FROM win_prob_snapshots" in ln and "JOIN ev" not in sql.split(ln)[1][:120]
    ]
    assert not unscoped, (
        "an unfiltered DISTINCT over win_prob_snapshots is the original defect"
    )


def test_grid_freshness_does_not_join_outcomes_to_markets():
    """The joined MAX() form timed out at 15s and silently skipped the check.

    Asserted against parsed call nodes rather than source text: this guard is
    about CODE shape, so a string/comment mention must not be able to satisfy
    (or break) it.
    """
    tree = ast.parse(inspect.getsource(gs._grid_freshness).lstrip())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    names = {getattr(c.func, "attr", None) for c in calls}

    joins_market = any(
        getattr(c.func, "attr", None) == "join"
        and c.args
        and getattr(c.args[0], "id", None) == "FuturesMarket"
        for c in calls
    )
    assert not joins_market, (
        "joining futures_outcomes to futures_markets and taking MAX() across the "
        "join is the shape that timed out; resolve market ids first"
    )
    assert "scalar_subquery" in names, "market ids must be resolved as a subquery"
    assert "in_" in names, "the MAX() must be keyed by market_id IN (...)"


# ---------------------------------------------------------------------------
# 4. Green must mean "all checks ran"
# ---------------------------------------------------------------------------

def test_skipped_check_cannot_produce_plain_green():
    """The headline. RED means REAL only if GREEN means everything ran."""
    clean = {"real": [], "explained": [], "watch": []}
    assert gs.grid_verdict(clean) == "green"
    assert gs.grid_verdict(clean, []) == "green"
    assert gs.grid_verdict(clean, ["freshness"]) == gs.GREEN_UNVERIFIED, (
        "a league whose freshness self-check could not run must not report a "
        "confident green (production: mlb + nba did exactly that)"
    )


def test_red_still_wins_over_unverified():
    """A REAL defect outranks a skipped check — RED semantics are unchanged."""
    real = {"real": [{"code": "x"}], "explained": [], "watch": []}
    assert gs.grid_verdict(real, ["freshness"]) == "red"


def test_unverified_league_does_not_auto_close_its_issue():
    """The consequential half: verdict == 'green' gates close-on-green, which
    auto-CLOSES a league's open grid issue. A check that never ran must not be
    able to close one."""
    src = inspect.getsource(gs._run_grid_sentinel)
    assert 'lg["verdict"] == "green"' in src, (
        "close-on-green must test STRICT green; loosening this to 'not red' "
        "would let a skipped check close a real issue"
    )
    assert gs.GREEN_UNVERIFIED != "green"


def test_scorecard_counts_green_instead_of_inferring_it():
    """`total - red` counted an unverified league as green."""
    src = inspect.getsource(gs._run_grid_sentinel)
    assert "leagues_unverified" in src
    assert 'len(stats["leagues"]) - len(red) - len(unverified)' in src, (
        "green must exclude unverified, not be everything that is not red"
    )


def test_cockpit_tile_cannot_render_green_over_a_skipped_check():
    """The tile recomputes its own status, so fixing the sentinel alone leaves
    the rendered surface still claiming green."""
    from app.routes import admin_cockpit

    src = inspect.getsource(admin_cockpit)
    assert '"red" if real else "amber" if (arts or skipped) else "green"' in src
    assert "any_unverified" in src
