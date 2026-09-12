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
