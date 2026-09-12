"""#5432 — the Polymarket curve a DERIVATIVE market wrote is retired; a real one is not.

THE DEFECT THESE GUARD. On `/events/15296755` — Barcelona 5-1 Feyenoord, a
finished Champions League tie — the Win Probability card drew a blue dashed
`Polymarket` line flat at ~3% from kickoff to full time, on the team that won by
four, while the card's own footer read `Barcelona 100% — Feyenoord 0%`. The 3%
was a correct price for a different question: `FC Barcelona vs. Feyenoord
Rotterdam - Exact Score`. 150,818 such rows across 5,057 events were measured on
production 2026-09-12.

WHY THESE ARE PURE GUARDS AND NOT DATABASE GUARDS. Every real-Postgres gate in
this repo is env-gated and SKIPS in CI, which has no Postgres service, and a
skipped guard is not a guard. So these exercise the repair's own decision
functions — the ones that choose what to delete — over hand-built rows.

🔴 THE ONE THING A ONE-SIDED TEST CANNOT SEE. A screen that refuses everything
passes every "the derivative is planned" test ever written. So every direction
below is asserted twice, and the decisive case is
`test_a_genuine_winner_on_a_twin_event_is_never_planned_5432`: it is the exact
row an EVENT-LEVEL screen deletes and this ROW-LEVEL one keeps.
"""

import importlib

import pytest


@pytest.fixture(scope="module")
def repair():
    """The repair module, imported by path the way `scripts/` modules are."""
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module(
        "scripts.repair_5432_derivative_polymarket_win_prob_snapshots"
    )


def _producers(*names):
    """Producer aggregate rows in the shape the stage-1 scan returns."""
    return [{"market_name": n, "n_rows": 1} for n in names]


# ── direction 1: the derivative books this repair exists for ─────────────────

#: Every family Polymarket mints per fixture, all wearing the match's own title.
#: Taken from the top of the production plan by row count, not invented.
DERIVATIVE_PRODUCERS = [
    "FC Barcelona vs. Feyenoord Rotterdam - Exact Score",
    "1. FC Köln vs. TSG 1899 Hoffenheim - Second Half Result",
    "Eintracht Frankfurt vs. SC Freiburg - Halftime Result",
    "Bromley FC vs. AFC Wimbledon - More Markets",
    "1. FC Union Berlin vs. Eintracht Frankfurt - First Team to Score",
    "SC Paderborn 07 vs. SC Freiburg: Both Teams to Score",
    "Cleveland Guardians vs. Minnesota Twins - Player Props",
    "St. Louis City SC vs. FC Dallas - Total Corners",
]


@pytest.mark.parametrize("name", DERIVATIVE_PRODUCERS)
def test_a_derivative_producer_is_planned_5432(repair, name):
    assert repair.refuted_producers(_producers(name)) == [name]


# ── direction 2: the real match winners that must survive ────────────────────

#: Real production producer names the gate admits. The accented and
#: tournament-prefixed entries are here because they are the two ways this
#: recognizer has silently mis-answered before (#5041 for the diacritics, and
#: `_strip_category_prefix` for `US Open ATP:`), and a repair that deleted them
#: would retire a correct curve on a marquee page.
WINNER_PRODUCERS = [
    "Cleveland Guardians vs. Minnesota Twins",
    "Cowboys vs. Giants",
    "1. FC Köln vs. SV Werder Bremen",
    "SE Palmeiras vs. São Paulo FC",
    "US Open ATP: Alexander Zverev vs Ben Shelton",
    "US Open WTA: Aryna Sabalenka vs Elena Rybakina",
    "Miami (OH) at Ohio State",
]


@pytest.mark.parametrize("name", WINNER_PRODUCERS)
def test_a_winner_producer_is_never_planned_5432(repair, name):
    assert repair.refuted_producers(_producers(name)) == []


def test_the_two_directions_are_asked_of_one_call_5432(repair):
    """Mixed input splits — the screen is not answering the same way twice.

    A screen stuck on "refuse" passes every derivative case above and a screen
    stuck on "admit" passes every winner case; only a mixed population catches
    both, and the count is asserted on each side so a partial collapse shows.
    """
    planned = repair.refuted_producers(
        _producers(*DERIVATIVE_PRODUCERS, *WINNER_PRODUCERS)
    )
    assert sorted(planned) == sorted(DERIVATIVE_PRODUCERS)
    assert len(planned) == len(DERIVATIVE_PRODUCERS) > 0


# ── the decisive case: the twin ──────────────────────────────────────────────


def test_a_genuine_winner_on_a_twin_event_is_never_planned_5432(repair):
    """The row an EVENT-LEVEL screen deletes and this one keeps.

    Event 15309638 (Guardians-Twins) carries 42 Polymarket markets and not one
    is a bare matchup — every event-level screen calls it derivative-only and
    plans its 109 Polymarket snapshot rows. Those rows recorded their producer:
    market 60383004, `Cleveland Guardians vs. Minnesota Twins`, a genuine
    moneyline whose `futures_markets.event_id` points at 15310687, this game's
    TWIN. The market was split onto the duplicate event; the snapshots stayed.

    So the guard is that the verdict reads the ROW's recorded producer and
    nothing about the event's current market list. There is deliberately no
    event context in this call — if a future edit needs some, it cannot get it
    here, and this test is what says so.
    """
    rows = _producers("Cleveland Guardians vs. Minnesota Twins")
    assert repair.refuted_producers(rows) == []

    # …and the container that DOES sit on that event is still planned, so the
    # twin protection is not simply "admit everything named after these teams".
    container = "Cleveland Guardians vs. Minnesota Twins - Player Props"
    assert repair.refuted_producers(_producers(container)) == [container]


# ── fail-open on absence ─────────────────────────────────────────────────────


@pytest.mark.parametrize("name", [None, "", "   "])
def test_a_producer_with_no_name_is_never_planned_5432(repair, name):
    """No recorded producer is NO EVIDENCE, not evidence of guilt.

    `"   "` is in the list because a whitespace name is falsy to the
    recognizer's own `if not name` but truthy to Python's `if name`, and the
    difference decides whether a blank-named producer is deleted or skipped.
    """
    assert repair.refuted_producers(_producers(name)) == []


# ── the shim ─────────────────────────────────────────────────────────────────


def test_shim_external_id_is_inert_5432(repair):
    """`external_id=None` must answer exactly as a real Polymarket id does.

    The shim drops the id because the recognizer consults it only for a Kalshi
    `kx…` ticker, and Polymarket ids are opaque numerics. That is a property of
    today's recognizer, not a law — so it is pinned. If a future recognizer
    starts reading Polymarket ids, this fails instead of the population
    silently re-classifying under a repair that cannot see them.
    """
    import app.utils.live_blend as lb

    class Real:
        def __init__(self, name, external_id):
            self.name = name
            self.external_id = external_id

    for name in DERIVATIVE_PRODUCERS + WINNER_PRODUCERS:
        assert lb._class_says_game_winner(Real(name, "982744")) == (
            not repair.refuted_producers(_producers(name))
        )


def test_the_recognizer_is_called_not_copied_5432(repair, monkeypatch):
    """The verdict must come from `live_blend`, not from a second copy here.

    A re-implemented recognizer is the #1951 failure: the copy does not throw
    when it disagrees, it just quietly answers differently — and this script's
    whole safety argument is that it refuses exactly what the shipped #5323 gate
    refuses. Delegation is asserted behaviourally: flip the shared rule and the
    plan must flip with it. A source scan for the import would pass on a module
    that imported it and then ignored it.
    """
    import app.utils.live_blend as lb

    monkeypatch.setattr(lb, "_class_says_game_winner", lambda market: False)
    assert repair.refuted_producers(_producers(*WINNER_PRODUCERS)) == list(
        WINNER_PRODUCERS
    )

    monkeypatch.setattr(lb, "_class_says_game_winner", lambda market: True)
    assert repair.refuted_producers(_producers(*DERIVATIVE_PRODUCERS)) == []


# ── the group-cost refusal ───────────────────────────────────────────────────


def _survivor(event_id, wp_left, odds_left):
    return {"event_id": event_id, "wp_left": wp_left, "odds_left": odds_left}


def test_an_event_left_with_nothing_is_refused_5432(repair):
    assert repair.refuse_events_that_would_go_dark([_survivor(1, 0, 0)]) == {1}


def test_an_event_keeping_either_rail_is_not_refused_5432(repair):
    """Both rails, and not either alone.

    `win_prob_history` and the sportsbook `history` array are separate inputs to
    the event page's chart, so an event keeping EITHER still draws and must not
    be refused — refusing it would leave a wrong Polymarket curve on a page that
    had something honest to show. 261 of the 1,568 events stripped of every
    win-prob row are exactly this case (they keep a sportsbook line), so an
    `or` written where the `and` belongs changes a measured population.
    """
    rows = [
        _survivor(1, 5, 0),  # keeps a win-prob row from another source
        _survivor(2, 0, 9),  # keeps a sportsbook line
        _survivor(3, 5, 9),  # keeps both
    ]
    assert repair.refuse_events_that_would_go_dark(rows) == set()


def test_the_refusal_splits_a_mixed_population_5432(repair):
    """A refusal that fires on everything, or nothing, is not a refusal."""
    rows = [
        _survivor(1, 0, 0),
        _survivor(2, 0, 3),
        _survivor(3, 4, 0),
        _survivor(4, 0, 0),
    ]
    assert repair.refuse_events_that_would_go_dark(rows) == {1, 4}


@pytest.mark.parametrize("blank", [None, 0])
def test_a_null_count_reads_as_empty_not_as_survival_5432(repair, blank):
    """`count(*)` cannot be NULL, but the subselects are read defensively.

    If a NULL ever reached here and were treated as truthy, the event would read
    as "still draws" and its wrong curve would be deleted anyway — the refusal
    failing OPEN, which is the direction that costs a reader a blank page.
    """
    assert repair.refuse_events_that_would_go_dark(
        [_survivor(1, blank, blank)]
    ) == {1}


# ── the D51 gates ────────────────────────────────────────────────────────────


def test_an_empty_reconciliation_is_not_a_pass_5432(repair):
    """gotcha #53 — `all()` over an empty mapping is True.

    Without the emptiness test a reconciliation that inspected nothing reads as
    a clean pass and `--apply` proceeds with no undo. That is precisely the
    first run on a database with no backup table, where the existence probe
    returns `{}`.
    """
    assert repair.backup_is_exact({}) is False
    assert repair.backup_is_exact({"win_prob_snapshots": 0}) is True
    assert repair.backup_is_exact({"win_prob_snapshots": 1}) is False


def test_the_small_plan_discriminator_reaches_the_decision_5432(repair):
    """Two causes, two outcomes — the #5246 lesson.

    #5246 shipped this discriminator as a bare message while its caller tested
    `if small:`, so a drained backlog and a broken filter both refused `--apply`
    identically and the discriminator only ever changed the wording. It cost
    that repair a session. So the guard asserts the FLAG, not the prose: a
    message alone would pass a test that only read `.message`.
    """
    floor = repair.SANITY_FLOOR

    big = repair.explain_small_plan(floor, 0)
    assert big.blocks_apply is False and big.message == ""

    drained = repair.explain_small_plan(10, floor)
    assert drained.blocks_apply is False
    assert "ALREADY APPLIED" in drained.message

    broken = repair.explain_small_plan(10, 0)
    assert broken.blocks_apply is True
    assert "FILTER BROKE" in broken.message


def test_the_floor_sits_below_the_measured_plan_5432(repair):
    """A floor at or above the plan refuses the run it was written for.

    140,978 rows were planned on production 2026-09-12. The floor must leave
    headroom for the population to shrink — it only ever shrinks, because the
    #5323 gate stops new refuted rows joining it — while still catching a filter
    that has half-broken.
    """
    assert 0 < repair.SANITY_FLOOR < 140_978
    assert repair.SANITY_FLOOR > 140_978 * 0.5


# ── #5595: the backup is checked by content, not by id ──────────────────────
#
# `bak_copy` skips any id already in the backup and the old reconciliation
# asked only "is this id present?". So a row staged in one session, re-parented
# to another `event_id`, then deleted by a later pass reconciled CLEAN — the
# delete's CAS covers source and producer name, not parentage — and the
# documented undo reinserted the backup's stale `event_id`, hanging a snapshot
# on a game it never belonged to. These are the guards for that class.


class _RecordingSession:
    """Records the SQL `backup()` issues, in order, and fakes rowcounts."""

    def __init__(self, evicted=0):
        self.statements = []
        self._evicted = evicted
        self.commits = 0

    async def execute(self, statement, params=None):
        self.statements.append(str(statement))
        return _Result(self._evicted)

    async def commit(self):
        self.commits += 1


class _Result:
    def __init__(self, rowcount):
        self.rowcount = rowcount


def _index_of(session, sql_key, repair):
    """Position of the first statement matching SQL[sql_key]."""
    needle = repair.SQL[sql_key]
    for i, s in enumerate(session.statements):
        if s == needle:
            return i
    return -1


def test_a_stale_backup_row_refuses_apply_5595(repair):
    """A backup that disagrees with the live row is not an undo.

    `missing == 0` is no longer sufficient: the row is *there*, and restoring
    it would write the wrong event.
    """
    assert repair.backup_is_exact(
        {"win_prob_snapshots": 0, "stale_backup_rows": 0}
    ) is True
    assert repair.backup_is_exact(
        {"win_prob_snapshots": 0, "stale_backup_rows": 1}
    ) is False


def test_missing_and_stale_are_reported_separately_5595(repair):
    """Two causes must not be summed into one count.

    They have different remedies — a missing row needs staging, a stale row
    needs evicting — so a single number would hide which one fired.
    """
    recon = {"win_prob_snapshots": 3, "stale_backup_rows": 5}
    assert recon["win_prob_snapshots"] != recon["stale_backup_rows"]
    assert repair.backup_is_exact(recon) is False


def test_the_staleness_test_compares_the_whole_row_5595(repair):
    """Not `event_id`, and not the id it already had.

    A whole-row `IS DISTINCT FROM` also keeps covering a column added to
    `win_prob_snapshots` later, which an enumerated column list would silently
    stop doing.
    """
    sql = repair.SQL["bak_stale"]
    assert "(b.*) IS DISTINCT FROM (s.*)" in sql
    assert repair.BAK_TABLE in sql
    # it must not be satisfiable by mere presence
    assert "NOT EXISTS" not in sql


def test_the_eviction_runs_before_the_copy_5595(repair):
    """Ordering IS the fix.

    `bak_copy` skips ids already present, so evicting after copying would leave
    every divergent row exactly as stale as it was found.
    """
    import asyncio

    session = _RecordingSession()
    asyncio.run(repair.backup(session, [1, 2, 3]))

    evict = _index_of(session, "bak_evict_stale", repair)
    copy = _index_of(session, "bak_copy", repair)
    assert evict >= 0, "the eviction statement never ran"
    assert copy >= 0, "the copy statement never ran"
    assert evict < copy, "evicting after the copy re-stages nothing"


def test_backup_reports_what_it_refreshed_5595(repair):
    """A silent self-repair is a lost signal — the operator is told."""
    import asyncio

    assert asyncio.run(repair.backup(_RecordingSession(evicted=0), [1])) == 0
    assert asyncio.run(repair.backup(_RecordingSession(evicted=7), [1])) == 7


def test_the_backup_still_commits_5595(repair):
    """The refresh must not cost the backup its durability."""
    import asyncio

    session = _RecordingSession()
    asyncio.run(repair.backup(session, [1, 2]))
    assert session.commits == 1


class _ScalarSession:
    """Answers each statement with a scalar keyed by which SQL it matches.

    Drives `reconcile_backup` end to end. The hand-built-dict tests above
    exercise the GATE; this exercises the function that builds the dict the
    gate reads, which is where a dropped key would otherwise hide.
    """

    def __init__(self, repair, *, exists=True, missing=0, stale=0):
        self._repair = repair
        self._answers = {
            repair.SQL["bak_exists"]: exists,
            repair.SQL["bak_missing"]: missing,
            repair.SQL["bak_stale"]: stale,
        }
        self.seen = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.seen.append(sql)
        if sql not in self._answers:
            raise AssertionError(f"unexpected statement: {sql[:80]}")
        return _Scalar(self._answers[sql])


class _Scalar:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


def test_the_reconciliation_actually_asks_about_staleness_5595(repair):
    """The gate can only refuse on a key the reconciliation returns.

    Kills the mutation that drops `stale_backup_rows` from the returned
    mapping: every gate test above still passes without it, because they build
    the mapping by hand.
    """
    import asyncio

    recon = asyncio.run(
        repair.reconcile_backup(_ScalarSession(repair, missing=0, stale=4), [1, 2])
    )
    assert recon["stale_backup_rows"] == 4
    assert recon["win_prob_snapshots"] == 0
    assert repair.backup_is_exact(recon) is False


def test_the_staleness_statement_is_actually_issued_5595(repair):
    """Not merely reported — the query runs against the database."""
    import asyncio

    session = _ScalarSession(repair, missing=0, stale=0)
    asyncio.run(repair.reconcile_backup(session, [1]))
    assert repair.SQL["bak_stale"] in session.seen
    assert repair.SQL["bak_missing"] in session.seen


def test_a_clean_reconciliation_still_passes_5595(repair):
    """The new key must not refuse a backup that is genuinely exact."""
    import asyncio

    recon = asyncio.run(
        repair.reconcile_backup(_ScalarSession(repair, missing=0, stale=0), [1])
    )
    assert recon == {"win_prob_snapshots": 0, "stale_backup_rows": 0}
    assert repair.backup_is_exact(recon) is True


def test_no_backup_table_still_reads_as_not_a_pass_5595(repair):
    """gotcha #53 is unchanged by the new key: `{}` is still a refusal."""
    import asyncio

    recon = asyncio.run(
        repair.reconcile_backup(_ScalarSession(repair, exists=False), [1])
    )
    assert recon == {}
    assert repair.backup_is_exact(recon) is False
