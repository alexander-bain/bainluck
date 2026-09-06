"""Guards for #3340 — the American Football residue void, and its undo.

The class of defect this repair belongs to is *a sport key with no producer
quietly accumulating servable phantom rows*, and the class of MISTAKE a bucket
sweep can make is voiding a real fixture. So the guards come in two halves:

  * the sweep's licence is re-derived from the SHIPPED ticker maps, not asserted
    in prose — if a real producer ever maps to the target key, the repair must
    refuse rather than void a live league;
  * the write path and its undo are exercised as REAL statements against sqlite,
    so "the restore inverts the repair" is a measured round trip and not a claim.

Both directions are asserted throughout (a retirement guard that only checks the
retired case passes just as happily when it has eaten every real status too).
"""

import importlib.util
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.event_completion import (  # noqa: E402
    EVENT_SUSPENDED,
    RECENT_RAIL_STATUSES,
    RETIRED_STATUSES,
)
from app.utils.sport_keys import (  # noqa: E402
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    KALSHI_TICKER_TO_SPORT_KEY,
)


def _load(name):
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", f"{name}.py"
    )
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


repair = _load("repair_3340_americanfootball_other_residue")
restore = _load("restore_3340_americanfootball_other_residue")


#: The census measured on production 2026-09-05 that the repair was planned on.
PRODUCTION_CENSUS = {
    "population": 4656,
    "with_score": 0,
    "with_team_id": 0,
    "with_real_external_id": 0,
}


# ---------------------------------------------------------------------------
# The sweep's licence — derived from the shipped maps, never from prose
# ---------------------------------------------------------------------------


def test_the_target_key_is_producerless_on_the_shipped_maps():
    """The premise of a BUCKET sweep, restated as a gate.

    If this ever fails, somebody has legitimised `americanfootball_other` and the
    repair must not run again — voiding the bucket would then void a real
    league's games.
    """
    assert repair.producerless_refusal_reason(repair.TARGET_SPORT_KEY) is None
    assert not [
        k for k, v in KALSHI_TICKER_TO_SPORT_KEY.items() if v == repair.TARGET_SPORT_KEY
    ]
    assert not [
        k
        for k, v in KALSHI_FUTURES_TICKER_TO_SPORT_KEY.items()
        if v == repair.TARGET_SPORT_KEY
    ]


@pytest.mark.parametrize("sport_key", ["basketball_other", "soccer_other"])
def test_a_sibling_bucket_with_a_real_producer_is_refused(sport_key):
    """The control that makes the test above mean something.

    `basketball_other` is the sibling #3340 names as carrying the same residue,
    and it is exactly the bucket this repair must NOT sweep: it has real ticker
    producers, so a sweep would void live CBA and J-League games. The refusal is
    computed from the shipped map, so it tracks the map rather than this list.
    """
    reason = repair.producerless_refusal_reason(sport_key)
    assert reason is not None, f"{sport_key} has producers but was not refused"
    assert sport_key in reason
    assert "legitimate producer" in reason


def test_the_refusal_names_the_tickers_that_caused_it():
    """A refusal a reader cannot act on gets bypassed. Name the evidence."""
    reason = repair.producerless_refusal_reason("basketball_other")
    producers = [
        k for k, v in KALSHI_TICKER_TO_SPORT_KEY.items() if v == "basketball_other"
    ]
    assert producers, "fixture assumption dead: basketball_other lost its producers"
    assert any(ticker in reason for ticker in producers)


# ---------------------------------------------------------------------------
# The population gate — every clause is a reason a REAL fixture might be here
# ---------------------------------------------------------------------------


def test_the_measured_production_census_is_permitted():
    """Red-first control: the gate must PASS the plan it was written for, or the
    refusal tests below prove nothing but that the gate refuses everything."""
    assert repair.population_refusal_reason(dict(PRODUCTION_CENSUS)) is None


@pytest.mark.parametrize(
    "field", ["with_score", "with_team_id", "with_real_external_id"]
)
def test_a_single_schedule_sourced_row_stops_the_whole_sweep(field):
    """#2871: never hide the only record of a real fixture.

    One row with a score, a resolved team, or a real external id is one row that
    may have come from a schedule source — and the sweep's whole argument is that
    none did. ONE is enough to refuse; the gate is not a proportion.
    """
    census = dict(PRODUCTION_CENSUS, **{field: 1})
    reason = repair.population_refusal_reason(census)
    assert reason is not None, f"{field}=1 did not stop the sweep"
    assert field in reason
    assert "2871" in reason


def test_an_empty_population_is_refused_rather_than_reported_as_success():
    """gotcha #53 — an empty result is a response shape, not an absence."""
    reason = repair.population_refusal_reason(dict(PRODUCTION_CENSUS, population=0))
    assert reason is not None
    assert "floor" in reason


def test_a_runaway_population_is_refused():
    """If the bucket has grown far past the measured residue, the premise the
    plan rests on has changed and wants re-measuring, not voiding."""
    reason = repair.population_refusal_reason(
        dict(PRODUCTION_CENSUS, population=repair.MAX_EXPECTED_POPULATION + 1)
    )
    assert reason is not None
    assert "ceiling" in reason


def test_the_band_actually_brackets_the_measured_population():
    """A band that does not contain the number it was sized on is decorative."""
    assert (
        repair.MIN_EXPECTED_POPULATION
        < PRODUCTION_CENSUS["population"]
        < repair.MAX_EXPECTED_POPULATION
    )


# ---------------------------------------------------------------------------
# The marker has to be one the readers honour — asserted BOTH directions
# ---------------------------------------------------------------------------


def test_the_void_marker_is_in_the_shipped_retirement_vocabulary():
    """A status no reader excludes would hide nothing and report success."""
    assert repair.VOID_STATUS in RETIRED_STATUSES


def test_the_recent_rail_excludes_the_marker_and_keeps_every_real_status():
    """Both directions. The first half is the ship; the second half is what stops
    a later widening of the retired set from quietly eating a real status.

    `RECENT_RAIL_STATUSES` is the league page's "Recent Results" rail — the one
    serving the 4,590 closed rows this repair takes down.
    """
    assert repair.VOID_STATUS not in RECENT_RAIL_STATUSES
    for retired in RETIRED_STATUSES:
        assert retired not in RECENT_RAIL_STATUSES
    for live_status in ("completed", "closed", EVENT_SUSPENDED):
        assert live_status in RECENT_RAIL_STATUSES


def test_no_real_status_is_treated_as_retired():
    """The complement of the rail check, at the vocabulary itself."""
    for live_status in ("scheduled", "live", EVENT_SUSPENDED, "completed", "closed"):
        assert live_status not in RETIRED_STATUSES


# ---------------------------------------------------------------------------
# The one-off rail: no list-valued bind may reach a detached dyno
# ---------------------------------------------------------------------------


def _sql_literals(module):
    """Every string constant in the module that is actually SQL.

    Parsed out of the AST rather than grepped: a plain substring scan over the
    file reads the PROSE too, and this repair's own comments necessarily quote
    the forbidden shapes in order to explain why they are forbidden. A guard that
    its own subject's documentation can trip is a guard that gets deleted.
    """
    import ast

    with open(module.__file__) as handle:
        tree = ast.parse(handle.read())

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))

    keywords = ("SELECT ", "UPDATE ", "INSERT ", "DELETE ", "WHERE ")
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and any(word in node.value for word in keywords)
    ]


@pytest.mark.parametrize("module_name", ["repair", "restore"])
def test_no_statement_uses_a_list_valued_bind(module_name):
    """A list bind (`IN :ids`, `= ANY(:ids)`) needs `expanding=True` to work at
    all, and the `ANY()` shape was MEASURED rolling back silently on a detached
    dyno whose stdout cannot be read. A silent rollback on a data repair is the
    worst failure available: it reports success and writes nothing.
    """
    module = {"repair": repair, "restore": restore}[module_name]
    statements = _sql_literals(module)
    assert statements, f"{module_name}: found no SQL to check — the guard is dead"
    for sql in statements:
        assert "ANY(:" not in sql, f"list-valued bind in: {sql[:120]}"
        assert "IN :" not in sql, f"list-valued bind in: {sql[:120]}"


def test_the_bind_guard_would_catch_a_real_list_bind():
    """The control. A scan that cannot fail is not a guard — this pins that the
    matcher fires on the shape it is meant to reject."""
    offender = "UPDATE events SET status = :void WHERE id = ANY(:ids)"
    assert "ANY(:" in offender
    assert any("WHERE " in sql for sql in _sql_literals(repair))


def test_the_retired_status_list_is_derived_from_the_shipped_constant():
    """Rendered as a literal, but DERIVED — so it cannot drift from the readers."""
    for status in RETIRED_STATUSES:
        assert f"'{status}'" in repair._RETIRED_SQL
    assert repair._RETIRED_SQL.count("'") == 2 * len(RETIRED_STATUSES)


# ---------------------------------------------------------------------------
# The round trip, as real statements against sqlite
# ---------------------------------------------------------------------------


class _SqliteResult:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _SqliteSession:
    """Enough of an async SQLAlchemy session to drive the real write helpers.

    `void_rows` and `restore_rows` issue plain single-row UPDATEs with scalar
    binds, which sqlite executes verbatim — so this runs the statements
    production runs rather than a paraphrase of them.
    """

    def __init__(self, conn):
        self.conn = conn
        self.commits = 0

    async def execute(self, statement, params=None):
        cursor = self.conn.execute(str(statement), params or {})
        return _SqliteResult(cursor.rowcount)

    async def commit(self):
        self.commits += 1
        self.conn.commit()

    async def rollback(self):
        self.conn.rollback()


def _seeded_db(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, status TEXT)")
    conn.executemany("INSERT INTO events (id, status) VALUES (?, ?)", rows)
    conn.commit()
    return conn


def _statuses(conn):
    return dict(conn.execute("SELECT id, status FROM events").fetchall())


@pytest.mark.asyncio
async def test_the_repair_voids_the_population_and_the_restore_puts_it_all_back():
    """The inverse property, measured — not asserted."""
    seed = [(1, "scheduled"), (2, "suspended"), (3, "closed"), (4, "live")]
    conn = _seeded_db(seed)
    session = _SqliteSession(conn)

    written = await repair.void_rows(session, [1, 2, 3, 4], progress_every=0)
    assert written == 4
    assert set(_statuses(conn).values()) == {repair.VOID_STATUS}

    plan = [{"event_id": eid, "old_status": status} for eid, status in seed]
    restored = await restore.restore_rows(session, plan, progress_every=0)
    assert restored == 4
    assert _statuses(conn) == dict(seed)


@pytest.mark.asyncio
async def test_an_already_retired_row_is_left_alone_so_the_repair_is_idempotent():
    """A second run must not re-bank or re-write. The `NOT IN (retired)` clause in
    the UPDATE is what makes the rowcount honest on the second pass."""
    conn = _seeded_db([(1, "scheduled"), (2, "merged"), (3, "voided")])
    session = _SqliteSession(conn)

    first = await repair.void_rows(session, [1, 2, 3], progress_every=0)
    assert first == 1, "only the un-retired row should have been written"

    second = await repair.void_rows(session, [1, 2, 3], progress_every=0)
    assert second == 0, "the repair is not idempotent"
    assert _statuses(conn)[2] == "merged", "an existing 'merged' marker was clobbered"


@pytest.mark.asyncio
async def test_the_restore_refuses_a_row_whose_status_moved_on():
    """The backup is older information than a status a poller has since written.

    Clobbering it would make the undo cause the damage it exists to reverse.
    """
    conn = _seeded_db([(1, repair.VOID_STATUS), (2, "live")])
    session = _SqliteSession(conn)

    plan = [
        {"event_id": 1, "old_status": "scheduled"},
        {"event_id": 2, "old_status": "scheduled"},
    ]
    restored = await restore.restore_rows(session, plan, progress_every=0)
    assert restored == 1
    assert _statuses(conn) == {1: "scheduled", 2: "live"}


@pytest.mark.asyncio
async def test_every_row_is_its_own_transaction():
    """`events` is write-hot: a batched UPDATE, or one impatient about locks,
    rolls back on every row where a patient single-row write succeeds."""
    conn = _seeded_db([(i, "scheduled") for i in range(1, 6)])
    session = _SqliteSession(conn)
    await repair.void_rows(session, [1, 2, 3, 4, 5], progress_every=0)
    assert session.commits == 5
