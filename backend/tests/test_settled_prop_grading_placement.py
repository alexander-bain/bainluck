"""#1976 §2 — the settled-prop grader assumed KALSHI'S PLAYER PLACEMENT.

Structural test over a REAL production payload (event 15194464, Orioles at Rays,
Final 7-6, captured 2026-08-18 from `/api/events/15194464/{game-markets,
related-futures}`), in the #1976 style: run the predicate across real rows and
assert the TRANSITION CENSUS — how many rows change disposition, and that every
change is of the intended class with zero of any other.

The defect: `_grade_settled_prop` derived the player from the OUTCOME name
("Jayson Tatum: 30+"), which is Kalshi's convention. Polymarket puts the player
in the MARKET name ("Pete Alonso: Home Runs O/U 0.5") and leaves the outcome a
bare "Over"/"Under". Every prop on this event is Polymarket, so the grader
looked up a player literally named "Over", missed, and returned actual=None on
all 11 rungs — while the box score in the SAME database held the answer. The
page rendered "Resolved · grading unavailable" twelve times on a settled game.

This is the same assumption class as UX-P097's line-placement bug, one layer up.
"""

import json
from pathlib import Path

import pytest

from app.routes.events import (
    _build_prop_grade_context,
    _grade_settled_prop,
    _prop_stat_keys,
)

FIXTURE = Path(__file__).parent / "fixtures" / "event_15194464_settled_props.json"


class _Obj:
    """Minimal stand-in for the ORM rows the grader reads (it only ever uses
    attribute access for name/external_id/is_winner/resolution_source)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


@pytest.fixture(scope="module")
def payload():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def ctx(payload):
    event = _Obj(box_score_data={"source": "espn", "players": payload["box_score"]})
    built = _build_prop_grade_context(event)
    assert built is not None, "real production box score must build a grade context"
    return built


def _grade(ctx, market_name, outcome_name, threshold, is_under):
    market = _Obj(name=market_name, external_id=None)
    outcome = _Obj(name=outcome_name, is_winner=None, resolution_source=None)
    return _grade_settled_prop(True, ctx, market, outcome, threshold, is_under)


def test_the_specimen_grades_and_the_box_score_agrees(ctx):
    """Pete Alonso hit 1 home run; O/U 0.5 must grade Over=hit, Under=miss."""
    over = _grade(ctx, "Pete Alonso: Home Runs O/U 0.5", "Over", 0.5, False)
    under = _grade(ctx, "Pete Alonso: Home Runs O/U 0.5", "Under", 0.5, True)
    assert over["actual"] == 1.0
    assert over["hit"] is True
    assert under["actual"] == 1.0
    assert under["hit"] is False


def test_under_side_grades_on_a_zero(ctx):
    """Jonny DeLuca hit 0 home runs; O/U 1.5 Under is the hit. A zero actual is
    a REAL grade — it must not be confused with 'never graded'."""
    under = _grade(ctx, "Jonny DeLuca: Home Runs O/U 1.5", "Under", 1.5, True)
    assert under["actual"] == 0.0
    assert under["hit"] is True


def test_kalshi_outcome_placement_still_wins(ctx):
    """The outcome is tried FIRST, so a Kalshi-shaped prop is unaffected even
    when the market name carries a different player.

    The decoy must have a DIFFERENT stat value or this assertion cannot tell
    the two orderings apart — Jonny DeLuca hit 0 home runs and Pete Alonso hit
    1, so 1.0 can only come from the outcome. (An earlier version of this test
    used a decoy who also had 1.0 and silently survived the mutation that
    disabled outcome placement entirely.)"""
    assert ctx["norm_box"][ctx["normalize"]("Jonny DeLuca")]["home runs"] == 0.0
    assert ctx["norm_box"][ctx["normalize"]("Pete Alonso")]["home runs"] == 1.0
    got = _grade(ctx, "Jonny DeLuca: Home Runs O/U 0.5", "Pete Alonso: 1+", 0.5, False)
    assert got["actual"] == 1.0  # Pete Alonso's HR total, not Jonny DeLuca's


def test_a_side_name_is_never_looked_up_as_a_player(ctx):
    """'Over'/'Under'/'Yes'/'No' are sides, never people. If a bare side name
    were ever resolvable as a player the grader would grade the wrong row."""
    for side in ("Over", "Under", "Yes", "No"):
        assert ctx["norm_box"].get(ctx["normalize"](side)) is None


def test_transition_census_over_the_real_slate(ctx, payload):
    """THE CENSUS. Over all 11 real prop rows: count what changed disposition
    and assert every change is of the intended class, zero of any other."""
    became_graded, still_ungraded, no_stat_key = [], [], []

    for market_name, outcome_name, threshold in payload["props"]:
        is_under = (outcome_name or "").strip().lower() == "under"
        market = _Obj(name=market_name, external_id=None)
        if _prop_stat_keys(market, ctx) is None:
            no_stat_key.append((market_name, outcome_name))
            continue
        got = _grade(ctx, market_name, outcome_name, threshold, is_under)
        if got.get("actual") is not None:
            became_graded.append((market_name, outcome_name, got["actual"]))
        else:
            still_ungraded.append((market_name, outcome_name))

    # BEFORE the fix this was 0. Four rungs (two home-run markets x two sides)
    # now carry a real actual.
    assert len(became_graded) == 4, became_graded

    # Every newly-graded row is a HOME RUNS prop — the only stat this ESPN box
    # score carries for these players. Zero changes of any other class.
    assert all("home runs" in m.lower() for m, _o, _a in became_graded), became_graded

    # The remainder is a DATA gap, not a read gap, and it is named: this box
    # score has batting stats only, so pitcher strikeouts cannot grade at all.
    assert all("strikeouts" in m.lower() for m, _o in still_ungraded), still_ungraded
    assert not any(
        "strikeouts" in (p or {}) for p in payload["box_score"].values()
    ), "if strikeouts ever appear in the box score, this gap is closed — retest"


def test_the_named_data_gap_is_real_not_a_lookup_miss(payload):
    """Route-out evidence: 0 of 34 players carry a 'strikeouts' key, so the
    strikeout props are ungradeable from this payload no matter how the player
    name is derived. This is the half that is NOT this lane's to fix."""
    players = payload["box_score"]
    assert len(players) == 34
    with_k = [n for n, s in players.items() if isinstance(s, dict) and "strikeouts" in s]
    assert with_k == [], with_k
