"""#7640 — the guards the repair script's *shape* has to hold, with no server.

The behaviour of this repair is graded against a real PostgreSQL in
`tests/integration/test_repair_7640_rank_roundtrip_real_postgres.py` — the
round trip, the settled exemption and the spared-row clause of the undo all need
a planner and cannot be asserted by reading. What lives HERE is the set of
claims that can go wrong in the source and would never show up as a failing
query:

1. **The script does not own an ordering rule.** #6598's whole premise is that
   `rank` has exactly one definition. A repair that re-derives it from a window
   function of its own authorship would "fix" 13,130 boards to a rule the live
   writers do not follow, and the next poll would undo every one of them — a
   pass that looks like a success in its own output and is invisible afterwards.
2. **The plan asks the same question the write answers**, compiled, not
   asserted by eye.
3. **The write gate refuses off its named app**, on every writing flag, and
   permits the plan anywhere.
4. **A plan past the sanity ceiling writes nothing** — proven by a session that
   raises on any statement but the plan, rather than by reading the `return 2`.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import importlib.util
import pathlib

import pytest
from sqlalchemy.dialects import postgresql

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scripts"
    / "repair_7640_stale_futures_ranks.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("repair_7640", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def repair():
    return _load()


@pytest.fixture(scope="module")
def tree():
    return ast.parse(SCRIPT.read_text())


def _args(**kw):
    ns = argparse.Namespace(
        backup=False, apply=False, restore=False, limit=0, dry_run=False
    )
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def _non_docstring_strings(tree: ast.AST) -> list[str]:
    """Every string CONSTANT in the module that is not a bare-expression docstring.

    The distinction matters and is the reason this is not a `grep`: the module
    docstring spells out the tie rule in prose (``rank()`` ties: 0.280 -> 1),
    so a text search for the ordering finds the explanation of why the ordering
    is not here. Only strings that are *operands* — the SQL constants — can
    carry a second copy of the rule.
    """
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                docstrings.add(id(node.value))
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and id(n) not in docstrings
    ]


# ── 1. no second opinion about the ordering ─────────────────────────────────


def test_the_repair_imports_the_shipped_ordering_rather_than_owning_one(tree):
    """The POSITIVE half, and it has to come first.

    Without it the negative assertion below is vacuous: a script that does no
    ranking at all also contains no window function.
    """
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "app.utils.futures_rank"
        for alias in node.names
    }
    assert "field_rank_expr" in imported, (
        "the plan must ask its question with the shipped expression, not a copy"
    )
    assert "rerank_market_fields_stmt" in imported, (
        "the forward write must be #6598's own statement, not a copy"
    )


def test_the_repair_calls_no_window_function_of_its_own(tree):
    """No `func.rank()` / `func.row_number()` / `func.dense_rank()` anywhere."""
    offenders = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"rank", "row_number", "dense_rank", "percent_rank"}
    ]
    assert offenders == [], (
        f"the repair builds its own ranking with {offenders} — #6598's premise is "
        "that `rank` has exactly one definition, and a second one here would "
        "renumber 13k boards to a rule no live writer follows"
    )


def test_no_raw_sql_constant_carries_a_window_clause(tree):
    """The same rule for the raw statements, which the AST check above cannot see."""
    bad = [
        s[:80]
        for s in _non_docstring_strings(tree)
        if "over (" in s.lower() or "partition by" in s.lower()
    ]
    assert bad == [], f"a raw SQL constant re-derives the ordering: {bad}"


# ── 2. the plan asks the question the write answers ─────────────────────────


def _compiled(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_plan_and_write_render_the_identical_ordering(repair):
    """Change the partition, the tie rule or the NULL placement and this fails.

    Both statements are rendered and the shipped expression's own SQL is
    required to appear verbatim in each. A substring test is weak in general;
    it has teeth here because the substring is produced by compiling the thing
    under test rather than typed into the assertion.
    """
    from app.models.models import FuturesOutcome
    from app.utils.futures_rank import field_rank_expr, rerank_market_fields_stmt

    ordering = _compiled(field_rank_expr())
    assert ordering.startswith("rank() OVER ")
    assert "PARTITION BY futures_outcomes.market_id" in ordering
    assert "DESC NULLS LAST" in ordering

    plan_sql = _compiled(repair.plan_select())
    write_sql = _compiled(
        rerank_market_fields_stmt([1]).returning(FuturesOutcome.id, FuturesOutcome.rank)
    )
    assert ordering in plan_sql, "the plan does not ask the shipped question"
    assert ordering in write_sql, "the write does not answer the shipped question"


def test_the_plan_is_scoped_to_open_markets(repair):
    """#6325: a finished field's rank is the record of how it finished."""
    sql = str(
        repair.plan_select().compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "futures_markets.status = 'open'" in sql


def test_the_write_time_status_check_takes_a_lock_in_a_deterministic_order(repair):
    """CERT-3201's required repair, in the statement.

    An unlocked re-read is a TOCTOU against `backfill_winners`, which is a
    `HEAVY_TASKS` member — the same app this repair runs on — and couples
    `status = 'resolved'` to its winner write in committed chunks.
    """
    sql = " ".join(repair.SQL["lock_open_markets"].split())
    assert "status = 'open'" in sql
    assert "FOR UPDATE" in sql
    # Rows lock in the order they are returned; a deterministic order is what
    # stops two overlapping chunks from deadlocking.
    assert sql.index("ORDER BY id") < sql.index("FOR UPDATE")


def test_the_named_settlement_writer_really_is_a_concurrent_one(repair):
    """The premise of the lock. If this stops holding, re-read the reasoning.

    Two halves, and the second is the one that makes the lock load-bearing
    rather than merely prudent: `backfill_winners` writes the status, and it
    runs on a DIFFERENT dyno from this repair — `_HEAVY_KEEP_ON_BACKGROUND`
    keeps it on the main app's background queue while the repair is invoked on
    `bainluck-heavy`. Two processes, one database, nothing in the application
    serialising them. A row lock is the only thing that can.
    """
    import pathlib

    from app.tasks import HEAVY_TASKS, _HEAVY_KEEP_ON_BACKGROUND

    assert "app.tasks.backfill_winners" in _HEAVY_KEEP_ON_BACKGROUND
    assert "app.tasks.backfill_winners" not in HEAVY_TASKS
    source = (
        pathlib.Path(repair.__file__).resolve().parents[1]
        / "app"
        / "tasks"
        / "backfill_winners.py"
    ).read_text()
    assert "UPDATE futures_markets SET status = 'resolved'" in source


def test_the_lock_and_the_write_are_one_transaction(tree):
    """A lock is ownership only for the life of its transaction.

    `apply_chunk` takes the lock itself rather than accepting a list from a
    caller who might have committed in between, and it must not commit before
    the write. Hoisting the lock out to the loop, or adding a commit here, is
    exactly how the race CERT-3201 blocked gets reintroduced by someone tidying
    up.
    """
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "apply_chunk"
    )
    calls = [
        n.func.attr
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    ]
    names = [
        n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert "lock_open_markets" in names, "apply_chunk must take the lock itself"
    assert "commit" not in calls, (
        "apply_chunk commits before its write — the status lock is released and "
        "the settlement race is back"
    )


# ── 3. the write gate ───────────────────────────────────────────────────────


def test_a_plan_only_invocation_runs_anywhere(repair, monkeypatch):
    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    assert repair.wrong_app_refusal(_args()) is None


@pytest.mark.parametrize("flag", ["backup", "apply", "restore"])
@pytest.mark.parametrize("app", [None, "bainluck", "", "bainluck-heavy-staging"])
def test_every_writing_flag_refuses_off_the_named_app(repair, monkeypatch, flag, app):
    if app is None:
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    else:
        monkeypatch.setenv("HEROKU_APP_NAME", app)
    refusal = repair.wrong_app_refusal(_args(**{flag: True}))
    assert refusal is not None and "REFUSING to write" in refusal


@pytest.mark.parametrize("flag", ["backup", "apply", "restore"])
def test_every_writing_flag_is_permitted_on_the_named_app(repair, monkeypatch, flag):
    monkeypatch.setenv("HEROKU_APP_NAME", repair.WRITER_APP)
    assert repair.wrong_app_refusal(_args(**{flag: True})) is None


def test_the_named_app_is_the_one_the_dominant_producer_runs_on(repair):
    """`refresh_stale_futures_prices` is the sweep this repair exists to supplement."""
    from app.tasks import HEAVY_TASKS

    assert "app.tasks.refresh_stale_futures_prices" in HEAVY_TASKS
    assert repair.WRITER_APP == "bainluck-heavy"


# ── 4. the reconciliation and the ceiling ───────────────────────────────────


@pytest.mark.parametrize(
    "recon",
    [
        {"table": "absent"},
        {},
        {"missing": 1, "stale": 0},
        {"missing": 0, "stale": 3},
    ],
)
def test_an_incomplete_backup_is_not_exact(repair, recon):
    """Gotcha #53: an absent reconciliation is a shape, not a clean bill."""
    assert repair.backup_is_exact(recon) is False


def test_a_complete_backup_is_exact(repair):
    assert repair.backup_is_exact({"missing": 0, "stale": 0}) is True


class _PlanOnlySession:
    """A session that answers the plan and REFUSES everything else.

    The ceiling guard's claim is not "it returns 2", it is "nothing is written".
    Asserting the exit code would pass just as happily on a script that wrote
    first and refused afterwards.
    """

    def __init__(self, rows):
        self._rows = rows
        self.writes = []

    async def execute(self, stmt, params=None):
        from sqlalchemy import Select

        if isinstance(stmt, Select):
            return _Result(self._rows)
        self.writes.append(str(stmt))
        raise AssertionError(f"the ceiling guard let a statement through: {stmt}")

    async def commit(self):
        raise AssertionError("the ceiling guard committed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


def test_a_plan_past_the_ceiling_writes_nothing(repair, monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", repair.WRITER_APP)

    oversized = [
        {
            "market_id": i,
            "legs": 4,
            "bad_legs": 2,
            "market_name": f"m{i}",
            "source": "kalshi",
            "market_tier": 5,
            "volume": 1,
        }
        for i in range(repair.SANITY_CEILING_MARKETS + 1)
    ]
    session = _PlanOnlySession(oversized)

    import app.services.database as db

    monkeypatch.setattr(db, "async_session_maker", lambda: session)

    code = asyncio.run(repair.run(_args(backup=True, apply=True)))
    assert code == 2
    assert session.writes == []


def test_the_ceiling_sits_above_the_measured_plan_and_below_the_population(repair):
    """13,130 of 26,968 open markets on 2026-09-21. A plan near the whole
    population means a clause stopped discriminating, most likely the
    `status = 'open'` scope or the `IS DISTINCT FROM` comparison."""
    assert 13_130 < repair.SANITY_CEILING_MARKETS < 26_968


# ── 5. the undo binds to what was written ───────────────────────────────────


def test_the_restore_requires_both_witnesses(repair):
    """A tripwire, not the proof — the proof executes in the PostgreSQL gate.

    `rank` alone cannot carry the test: a poller that re-derives the board
    arrives at the same number this pass wrote, so "still holds what we wrote"
    is true whether or not anybody touched the row. `last_updated` separates
    them, because #6598's statement provably cannot move it.
    """
    sql = " ".join(repair.SQL["restore"].split())
    assert "o.rank IS NOT DISTINCT FROM m.wrote_rank" in sql
    assert "o.last_updated IS NOT DISTINCT FROM m.seen_last_updated" in sql


def test_last_updated_can_actually_serve_as_the_witness():
    """The restore's second clause rests on a schema fact — assert the fact.

    `futures_outcomes.last_updated` must have NO `onupdate`. If it grew one, a
    re-rank would move it, the undo would spare rows nothing had touched, and
    the whole two-witness argument would quietly become a one-witness one.
    """
    from app.models.models import FuturesOutcome

    column = FuturesOutcome.__table__.c.last_updated
    assert column.onupdate is None
    assert column.server_onupdate is None


def test_the_manifest_banks_both_witnesses(repair):
    for column in ("wrote_rank", "seen_last_updated"):
        assert column in repair.SQL["man_create"]
        assert column in repair.SQL["man_record"]


def test_the_backup_stages_whole_markets_not_just_the_bad_legs(repair):
    """Backup granularity below write granularity is how an undo stops being one.

    The write re-derives the WHOLE field, so a price that moves between the plan
    and the write can legitimately renumber a leg the plan considered fine. Keyed
    on `market_id`, that leg is covered; keyed on the mismatched outcome ids it
    would have a manifest row and no backup behind it.
    """
    for key in ("bak_copy", "bak_missing", "bak_stale", "bak_evict_stale"):
        assert "o.market_id = ANY" in repair.SQL[key], key


def test_the_repair_never_touches_the_two_columns_6598_left_alone(tree):
    """`rank_change_24h` (#2408's class) and `last_updated` (playoffs' liveness gate).

    `last_updated` is also the restore's own witness, so a write to it would
    disarm the undo as well as lie about freshness.
    """
    written = {
        s
        for s in _non_docstring_strings(tree)
        if "SET " in s.upper() or "UPDATE " in s.upper()
    }
    for statement in written:
        upper = statement.upper()
        assert "RANK_CHANGE_24H" not in upper, statement[:120]
        assert "SET LAST_UPDATED" not in upper, statement[:120]
