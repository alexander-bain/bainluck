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
# The near miss: the producer test is NECESSARY BUT NOT SUFFICIENT
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sport_key", ["tennis_other", "baseball_other"])
def test_a_producerless_bucket_is_still_refused_without_an_evidence_package(sport_key):
    """The regression test for the mistake this repair nearly shipped.

    `tennis_other` passes the producer test — no Kalshi ticker maps to it — and on
    2026-09-05 it measured 0 scores, 0 team_ids and 0 real external ids, i.e. every
    safety signal the population gate reads came back identical to the target
    bucket. It was at that moment carrying LIVE US OPEN DOUBLES, because tennis is
    produced by StatPal, which the Kalshi maps know nothing about.

    Only the population ceiling refused it, and only by 331 rows. That is a
    plan-drift check catching a safety failure by luck, so the licence is now an
    explicit per-bucket evidence package.
    """
    assert repair.producerless_refusal_reason(sport_key) is None, (
        f"fixture assumption dead: {sport_key} gained a Kalshi producer, so it no "
        f"longer demonstrates that the producer test is insufficient"
    )
    reason = repair.sweep_refusal_reason(sport_key)
    assert reason is not None, f"{sport_key} would be swept on the producer test alone"
    assert "EVIDENCED_SPORT_KEYS" in reason


def test_the_refusal_explains_the_us_open_near_miss_rather_than_just_saying_no():
    """A refusal whose reason is 'not in the list' teaches the next reader to add
    themselves to the list. This one has to say why the list exists."""
    reason = repair.sweep_refusal_reason("tennis_other")
    assert "US OPEN" in reason.upper()
    assert "census" in reason.lower()


def test_the_target_bucket_still_passes_the_full_licence_check():
    """The control. A gate that refuses everything ships nothing."""
    assert repair.sweep_refusal_reason(repair.TARGET_SPORT_KEY) is None


def test_every_evidenced_key_carries_its_evidence_and_passes_the_producer_test():
    """The allowlist is a record of measurements, not a convenience list."""
    assert repair.EVIDENCED_SPORT_KEYS, "the allowlist cannot be empty"
    for sport_key, evidence in repair.EVIDENCED_SPORT_KEYS.items():
        assert len(evidence) > 80, f"{sport_key} has no real evidence recorded"
        assert repair.producerless_refusal_reason(sport_key) is None, (
            f"{sport_key} is evidenced but now has a producer — the evidence is stale"
        )


def test_a_bucket_with_a_producer_is_refused_even_if_someone_evidences_it():
    """Both gates are load-bearing, in both orders: adding a key to the allowlist
    must not buy a pass on the producer test."""
    reason = repair.sweep_refusal_reason("basketball_other")
    assert reason is not None
    patched = dict(repair.EVIDENCED_SPORT_KEYS, basketball_other="x" * 100)
    original = repair.EVIDENCED_SPORT_KEYS
    try:
        repair.EVIDENCED_SPORT_KEYS = patched
        still_refused = repair.sweep_refusal_reason("basketball_other")
    finally:
        repair.EVIDENCED_SPORT_KEYS = original
    assert still_refused is not None, "the producer test stopped being consulted"
    assert "legitimate producer" in still_refused


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


class _SqliteRow:
    """Attribute access over a sqlite tuple, the way SQLAlchemy rows read."""

    def __init__(self, columns, values):
        for column, value in zip(columns, values):
            setattr(self, column, value)


class _SqliteResult:
    def __init__(self, cursor):
        self.rowcount = cursor.rowcount
        self._columns = [c[0] for c in (cursor.description or [])]
        self._rows = cursor.fetchall() if cursor.description else []

    def scalar(self):
        return self._rows[0][0] if self._rows else None

    def all(self):
        return [_SqliteRow(self._columns, values) for values in self._rows]

    def one(self):
        return self.all()[0]


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
        return _SqliteResult(cursor)

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

    written, failed = await repair.void_rows(session, [1, 2, 3, 4], progress_every=0)
    assert (written, failed) == (4, [])
    assert set(_statuses(conn).values()) == {repair.VOID_STATUS}

    plan = [{"event_id": eid, "old_status": status} for eid, status in seed]
    restored, failed = await restore.restore_rows(session, plan, progress_every=0)
    assert (restored, failed) == (4, [])
    assert _statuses(conn) == dict(seed)


@pytest.mark.asyncio
async def test_an_already_retired_row_is_left_alone_so_the_repair_is_idempotent():
    """A second run must not re-bank or re-write. The `NOT IN (retired)` clause in
    the UPDATE is what makes the rowcount honest on the second pass."""
    conn = _seeded_db([(1, "scheduled"), (2, "merged"), (3, "voided")])
    session = _SqliteSession(conn)

    first, _ = await repair.void_rows(session, [1, 2, 3], progress_every=0)
    assert first == 1, "only the un-retired row should have been written"

    second, _ = await repair.void_rows(session, [1, 2, 3], progress_every=0)
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
    restored, _ = await restore.restore_rows(session, plan, progress_every=0)
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


# ---------------------------------------------------------------------------
# CERT-1982's BLOCK: a short run must never exit 0 or print terminal success
# ---------------------------------------------------------------------------
#
# The defect: after retry exhaustion both loops printed `FAILED` and continued,
# and the caller judged success on `visible_total == 0` — the three page rails
# only. A failed row outside the 14-day window is invisible to those rails while
# remaining servable by the by-id read, search and the feed, so a partial repair
# could print the success message and exit 0. On a detached dyno whose stdout
# cannot be read, that is indistinguishable from a clean run.


class _FailingSqliteSession(_SqliteSession):
    """Fails one event id persistently, so its three retries all exhaust."""

    def __init__(self, conn, fail_id):
        super().__init__(conn)
        self.fail_id = fail_id

    async def execute(self, statement, params=None):
        if params and params.get("eid") == self.fail_id:
            raise RuntimeError(f"simulated persistent lock failure on {self.fail_id}")
        return await super().execute(statement, params)


@pytest.mark.asyncio
async def test_a_persistently_failing_row_is_returned_not_just_printed():
    """The repair direction. Row 1 commits first, THEN row 2 fails — so the run
    has real durable progress alongside a real failure, which is the case that
    used to report success."""
    conn = _seeded_db([(1, "scheduled"), (2, "scheduled"), (3, "scheduled")])
    session = _FailingSqliteSession(conn, fail_id=2)

    written, failed = await repair.void_rows(session, [1, 2, 3], progress_every=0)

    assert failed == [2], "the failed id was printed but not returned"
    assert written == 2
    statuses = _statuses(conn)
    assert statuses[1] == repair.VOID_STATUS, "earlier commit was not preserved"
    assert statuses[3] == repair.VOID_STATUS, "the loop stopped at the failure"
    assert statuses[2] == "scheduled", "the failing row is still servable"


@pytest.mark.asyncio
async def test_the_restore_direction_returns_its_failures_too():
    """The undo has the symmetric false-success path: an operator who believes
    the takedown was reversed stops looking."""
    conn = _seeded_db([(i, repair.VOID_STATUS) for i in (1, 2, 3)])
    session = _FailingSqliteSession(conn, fail_id=2)
    plan = [{"event_id": i, "old_status": "scheduled"} for i in (1, 2, 3)]

    written, failed = await restore.restore_rows(session, plan, progress_every=0)

    assert failed == [2]
    assert written == 2
    statuses = _statuses(conn)
    assert statuses[1] == "scheduled" and statuses[3] == "scheduled"
    assert statuses[2] == repair.VOID_STATUS, "still voided, and it must be reported"


@pytest.mark.asyncio
async def test_a_rerun_after_the_failure_clears_finishes_the_job():
    """Resumability. The per-row commits are the reason a partial run is
    recoverable rather than a mess, so the rerun must be a short one."""
    conn = _seeded_db([(1, "scheduled"), (2, "scheduled"), (3, "scheduled")])
    failing = _FailingSqliteSession(conn, fail_id=2)
    await repair.void_rows(failing, [1, 2, 3], progress_every=0)

    healthy = _SqliteSession(conn)
    written, failed = await repair.void_rows(healthy, [1, 2, 3], progress_every=0)

    assert failed == []
    assert written == 1, "the already-voided rows were written again"
    assert set(_statuses(conn).values()) == {repair.VOID_STATUS}




# ---------------------------------------------------------------------------
# CERT-1986's BLOCK: the promised resume must actually be possible
# ---------------------------------------------------------------------------
#
# The defect: the failure message told the operator to re-run, and the re-run
# then hit `population 1 is below the floor 3000` and refused. The floor exists
# so an empty or drifted run cannot report success, but it also made the repair's
# own instruction false.
#
# CERT-1986 also caught the reason the previous guards missed it: the harness
# monkeypatched `population_refusal_reason` away, and the "rerun" test called
# `void_rows()` rather than the command. So the harness below stubs ONLY the two
# Postgres-shaped readers, computes the population from the real sqlite state,
# and lets the real gate decide. `population_refusal_reason`, `is_resumption`
# and `measure_resume_evidence` all run for real.


def _seeded_league(rows, sport_key=None):
    """A sqlite store with the joins the real statements need.

    `_IDS_SQL` and `_RESUME_SQL` both join `sports` and read the backup table, so
    the guards give them a real one and run the production strings verbatim.
    """
    sport_key = sport_key or repair.TARGET_SPORT_KEY
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sports (id INTEGER PRIMARY KEY, key TEXT)")
    conn.execute("INSERT INTO sports (id, key) VALUES (1, ?)", (sport_key,))
    conn.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY, status TEXT, sport_id INTEGER)"
    )
    conn.executemany(
        "INSERT INTO events (id, status, sport_id) VALUES (?, ?, 1)", rows
    )
    conn.execute(
        f"CREATE TABLE {repair.BAK_TABLE} "
        "(event_id INTEGER PRIMARY KEY, old_status TEXT, sport_key TEXT)"
    )
    conn.commit()
    return conn


def _remaining(conn):
    retired = ", ".join(f"'{s}'" for s in sorted(RETIRED_STATUSES))
    return conn.execute(
        f"SELECT count(*) FROM events WHERE status NOT IN ({retired})"
    ).fetchone()[0]


def _install(monkeypatch, conn, session):
    """Wire the real `run()` to sqlite, stubbing only what is Postgres-shaped.

    Stubbed: `measure` (`FILTER`, `now() - interval`) — but its population is READ
    FROM sqlite, so "population zero" is a real observation; and `ensure_backup`
    (`timestamptz`, `DEFAULT now()`, `ON CONFLICT`) — but it banks real rows, so
    the resume evidence it produces is real.

    NOT stubbed, deliberately: `population_refusal_reason`, `is_resumption`,
    `measure_resume_evidence`, `_IDS_SQL`, `_RESUME_SQL`, `void_rows`, and every
    terminal check. Those are what CERT-1986 blocked on.
    """
    import app.tasks.base as task_base

    class _Ctx:
        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *exc):
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())

    async def fake_measure(_session, sport_key=repair.TARGET_SPORT_KEY):
        population = _remaining(conn)
        return {
            "population": population,
            "with_score": 0,
            "with_team_id": 0,
            "with_real_external_id": 0,
            "visible_upcoming": 0,
            "visible_unreported": 0,
            "visible_recent": population,
            "visible_total": population,
        }

    async def fake_ensure_backup(_session, sport_key=repair.TARGET_SPORT_KEY):
        retired = ", ".join(f"'{s}'" for s in sorted(RETIRED_STATUSES))
        cursor = conn.execute(
            f"INSERT OR IGNORE INTO {repair.BAK_TABLE} "
            "(event_id, old_status, sport_key) "
            f"SELECT id, status, ? FROM events WHERE status NOT IN ({retired})",
            (sport_key,),
        )
        conn.commit()
        return cursor.rowcount

    monkeypatch.setattr(repair, "measure", fake_measure)
    monkeypatch.setattr(repair, "ensure_backup", fake_ensure_backup)


#: Comfortably over MIN_EXPECTED_POPULATION so the FIRST run clears the real
#: floor without the floor being touched. Derived, so raising the constant cannot
#: leave this test quietly passing a floor it no longer exceeds.
_ABOVE_FLOOR = repair.MIN_EXPECTED_POPULATION + 2


@pytest.mark.asyncio
async def test_the_real_command_fails_short_then_resumes_to_zero_on_rerun(
    monkeypatch, capsys
):
    """CERT-1986's required regression: the SAME command, twice, real gate.

    Run 1 has durable progress plus one persistently failing row and must exit
    nonzero. Run 2, with the failure removed, must be ALLOWED past the population
    floor on the strength of the backup, and must finish to population zero.
    """
    ids = list(range(1, _ABOVE_FLOOR + 1))
    conn = _seeded_league([(i, "scheduled") for i in ids])
    fail_id = ids[-1]

    failing = _FailingSqliteSession(conn, fail_id=fail_id)
    _install(monkeypatch, conn, failing)
    with pytest.raises(SystemExit) as exit_info:
        await repair.run(backup=True, apply=True)

    assert exit_info.value.code == 1, "a partial repair exited 0"
    first_out = capsys.readouterr().out
    assert "INCOMPLETE" in first_out
    assert "✅" not in first_out
    assert _remaining(conn) == 1, "expected exactly the failing row to survive"

    # Run 2 — the failure is gone. This is the run the old build refused.
    healthy = _SqliteSession(conn)
    _install(monkeypatch, conn, healthy)
    await repair.run(backup=True, apply=True)

    second_out = capsys.readouterr().out
    assert "RESUMING" in second_out, "the resume evidence was not recognised"
    assert "below the floor" not in second_out, (
        "the floor refused the rerun its own failure message promised"
    )
    assert "✅" in second_out
    assert _remaining(conn) == 0
    assert set(_statuses(conn).values()) == {repair.VOID_STATUS}


@pytest.mark.asyncio
async def test_a_small_population_this_repair_did_not_leave_is_still_refused(
    monkeypatch, capsys
):
    """The control that keeps the waiver honest.

    Same tiny population, but nothing is banked — so this is drift, not a resume,
    and the floor must still refuse it. Without this, the fix for CERT-1986 would
    simply be "delete the floor".
    """
    conn = _seeded_league([(1, "scheduled"), (2, "scheduled")])
    session = _SqliteSession(conn)
    _install(monkeypatch, conn, session)
    monkeypatch.setattr(repair, "ensure_backup", _async_return(0))

    with pytest.raises(SystemExit) as exit_info:
        await repair.run(backup=True, apply=True)

    assert exit_info.value.code == 1
    out = capsys.readouterr().out
    assert "below the floor" in out
    assert _statuses(conn) == {1: "scheduled", 2: "scheduled"}, "rows were voided"


@pytest.mark.asyncio
async def test_a_partly_banked_remainder_is_drift_not_a_resume(monkeypatch, capsys):
    """A row we never banked is a row this repair did not leave behind.

    Evidence must cover the WHOLE remainder, or "resume" becomes a way to sweep
    rows that arrived after the repair started.
    """
    conn = _seeded_league([(1, "scheduled"), (2, "scheduled")])
    conn.execute(
        f"INSERT INTO {repair.BAK_TABLE} (event_id, old_status, sport_key) "
        "VALUES (1, 'scheduled', ?)",
        (repair.TARGET_SPORT_KEY,),
    )
    conn.commit()

    session = _SqliteSession(conn)
    evidence = await repair.measure_resume_evidence(session)
    assert evidence == {
        "banked_for_key": 1,
        "remaining_total": 2,
        "remaining_banked": 1,
    }
    assert repair.is_resumption(evidence) is False

    _install(monkeypatch, conn, session)
    monkeypatch.setattr(repair, "ensure_backup", _async_return(0))
    with pytest.raises(SystemExit):
        await repair.run(backup=True, apply=True)
    assert "below the floor" in capsys.readouterr().out


def test_the_resume_waiver_needs_evidence_that_covers_every_remaining_row():
    """The pure gate, at its edges."""
    small = {
        "population": 1,
        "with_score": 0,
        "with_team_id": 0,
        "with_real_external_id": 0,
    }
    covered = {"banked_for_key": 4656, "remaining_total": 1, "remaining_banked": 1}
    assert repair.population_refusal_reason(small, resume=covered) is None

    for bad in (
        None,
        {"banked_for_key": 0, "remaining_total": 1, "remaining_banked": 1},
        {"banked_for_key": 4656, "remaining_total": 2, "remaining_banked": 1},
        {"banked_for_key": 4656, "remaining_total": 0, "remaining_banked": 0},
    ):
        assert repair.population_refusal_reason(small, resume=bad) is not None, bad


def test_a_resume_does_not_waive_the_schedule_source_hazards():
    """The floor is the ONLY thing a resume waives. A row that grew a score since
    the first pass is still a reason to stop."""
    resume = {"banked_for_key": 4656, "remaining_total": 1, "remaining_banked": 1}
    for field in ("with_score", "with_team_id", "with_real_external_id"):
        census = dict(
            population=1, with_score=0, with_team_id=0, with_real_external_id=0
        )
        census[field] = 1
        reason = repair.population_refusal_reason(census, resume=resume)
        assert reason is not None, f"{field} was waived by the resume"
        assert "2871" in reason


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


@pytest.mark.asyncio
async def test_the_restore_command_fails_short_then_completes_on_rerun(
    monkeypatch, capsys
):
    """CERT-1986's symmetric requirement, on the undo, through the real command."""
    import app.tasks.base as task_base

    conn = _seeded_league([(i, repair.VOID_STATUS) for i in (1, 2, 3)])
    conn.executemany(
        f"INSERT INTO {repair.BAK_TABLE} (event_id, old_status, sport_key) "
        "VALUES (?, 'scheduled', ?)",
        [(i, repair.TARGET_SPORT_KEY) for i in (1, 2, 3)],
    )
    conn.commit()

    def wire(session):
        class _Ctx:
            async def __aenter__(self_inner):
                return session

            async def __aexit__(self_inner, *exc):
                return False

        monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())

    wire(_FailingSqliteSession(conn, fail_id=2))
    with pytest.raises(SystemExit) as exit_info:
        await restore.run(apply=True)

    assert exit_info.value.code == 1
    first_out = capsys.readouterr().out
    assert "RESTORE INCOMPLETE" in first_out
    assert "✅" not in first_out
    assert _statuses(conn) == {1: "scheduled", 2: repair.VOID_STATUS, 3: "scheduled"}

    wire(_SqliteSession(conn))
    await restore.run(apply=True)

    second_out = capsys.readouterr().out
    assert "✅" in second_out
    assert "INCOMPLETE" not in second_out
    assert _statuses(conn) == {1: "scheduled", 2: "scheduled", 3: "scheduled"}
