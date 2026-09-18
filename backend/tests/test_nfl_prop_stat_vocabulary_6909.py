"""#6909 — every NFL prop was ungradeable from the box score, because the stat
vocabulary was baseball, basketball and soccer only.

`_prop_stat_keys` resolves a Kalshi ticker prefix first and a market name
second. Both tables held NBA/NHL/MLB entries and nothing else, and
`_PROP_NAME_STAT_SINGLES` carries no football stat either, so every NFL prop
returned None and `_grade_settled_prop` bailed before it read a stat.

Measured on production 2026-09-18 (49ers 7 - Rams 27, `completed`, event
14632820): `actual` was null on **510 of 510** served props, and **35** printed
`Resolved · grading unavailable` while that same event's `box_score_data` held
the answer — Puka Nacua's line says 74 receiving yards, so the withheld
"Puka Nacua: 80+" was always a MISS.

Two things this file pins that the diff alone does not say:

1. **The key is what the BOX SCORE calls it, not what the series calls it.**
   Kalshi's Rushing Attempts series is `KXNFLRSHATT`; ESPN stores that quantity
   as `carries`. A plausible-looking `"rushing attempts"` entry would have gone
   on returning None forever and read as "still unmapped".

2. **`kxnflrec` is a proper prefix of `kxnflrecyds`** — the #1728 collision
   exactly. It is safe only because `_prop_stats_for_ticker` takes the LONGEST
   matching prefix; under first-match-wins every receiving-yards prop would
   grade off a reception COUNT.

The census runs the REAL route grading functions over the REAL captured payload
and asserts both directions (gotcha #43): every intended row newly grades, and
ZERO rows of any other class move. The 11 newly-graded verdicts below were each
hand-checked against the box-score line quoted beside them.
"""

import json
from pathlib import Path

import pytest

from app.routes.events import (
    _build_prop_grade_context,
    _grade_settled_prop,
    _prop_stat_keys,
)
from app.tasks.backfill_winners import _PROP_TICKER_TO_STAT

FIXTURE = Path(__file__).parent / "fixtures" / "event_nfl_prop_vocabulary_6909.json"


class _Obj:
    """Stand-in for the ORM rows the grader reads (attribute access only)."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture(scope="module")
def captured():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def ctx(captured):
    event = _Obj(box_score_data={"players": captured["box_score_players"]})
    built = _build_prop_grade_context(event)
    # Not an assertion about the fix: the context built fine BEFORE it too. The
    # box score was never the missing piece, which is the whole point of #6909.
    assert built is not None
    return built


def _grade_every_prop(captured, ctx):
    """Run the real grader over every captured row. Returns (row, result) pairs.

    🪤 THE PRICE COMES FROM `_stored`, NOT FROM THE SERVED `over_probability`.
    `_venue_typed_hit` (#6751) reads `outcome.current_probability`, and the two
    are not the same number: on 3 of these 510 rows the route serves 0.01 for a
    Team Sacks rung the database stores at 0.12-0.31. Feeding the served value
    back in put those rungs under the 0.1 loss ceiling and made this rig type
    three MISS verdicts production never printed — a finding about the harness
    wearing the shape of a finding about the fix.
    """
    out = []
    for row in captured["player_props"]:
        meta = captured["markets"][str(row["_market_id"])]
        stored = row["_stored"] or {}
        market = _Obj(external_id=meta["external_id"], name=meta["name"])
        outcome = _Obj(
            name=row["outcome_name"],
            is_winner=stored.get("is_winner", row["is_winner"]),
            resolution_source=stored.get("resolution_source", row["resolution_source"]),
            current_probability=stored.get("current_probability"),
        )
        graded = _grade_settled_prop(
            True, ctx, market, outcome, row["threshold"], row["_inverted"]
        )
        out.append((row, graded))
    return out


# Every row the fix newly grades, with the box-score line that decides it.
# `served` is what production printed on 2026-09-18: None == the reader saw
# "Resolved · grading unavailable".
EXPECTED_NEWLY_GRADED = {
    ("Puka Nacua: 80+", "Receiving Yards"): (74.0, False),
    ("Demarcus Robinson: 50+", "Receiving Yards"): (50.0, True),
    ("Kyren Williams: 50+", "Rushing Yards"): (41.0, False),
    ("Kyren Williams: 60+", "Rushing Yards"): (41.0, False),
    ("Christian McCaffrey: 110+", "Rushing Yards"): (68.0, False),
    ("Matthew Stafford: 19+", "Passing Completions"): (15.0, False),
    ("Brock Purdy: 5+", "Rushing Attempts"): (5.0, True),
    ("Brock Purdy: 7+", "Rushing Attempts"): (5.0, False),
    ("Deebo Samuel Sr.: 6+", "Receptions"): (6.0, True),
    ("Puka Nacua: 6+", "Receptions"): (5.0, False),
    ("Colby Parkinson: 2+", "Receptions"): (1.0, False),
}


def _label(row, captured):
    return (
        row["outcome_name"],
        captured["markets"][str(row["_market_id"])]["name"].split(": ")[-1],
    )


def test_the_captured_payload_still_carries_the_defect(captured):
    """The fixture is the BEFORE and must not be refreshed from a fixed tree."""
    props = captured["player_props"]
    assert len(props) == 510
    assert sum(1 for r in props if r["hit"] is None) == 35
    assert all(r.get("actual") is None for r in props if "actual" in r)
    # Every row carries its STORED price/verdict, including the 20 TEAM rungs
    # whose served label the route lengthens ("Los Angeles R" -> "Los Angeles
    # Rams") so it no longer keys the stored outcome by name. Those were
    # re-matched on the "N+" tail plus a prefix-compatible team; a fixture that
    # loses them silently withholds 13 verdicts production printed, which is
    # what the rig-validity test below exists to catch.
    assert all(r["_stored"] for r in props)


def test_the_rig_reproduces_production_wherever_the_box_score_stays_silent(
    captured, ctx
):
    """Rig validity, asserted before anything is concluded from the rig.

    On every row the box score CANNOT answer, this harness must print exactly
    what production printed on 2026-09-18 — same verdict, same withholding.
    Where it does not, the harness is the story and no census taken with it
    means anything (gotcha #124's shape, applied to a fixture rig).
    """
    mismatches = []
    for row, graded in _grade_every_prop(captured, ctx):
        if graded.get("actual") is not None:
            continue  # the box score answered; that IS the change under test
        if graded.get("hit") != row["hit"]:
            mismatches.append((_label(row, captured), row["hit"], graded.get("hit")))
    assert mismatches == []


def test_every_withheld_row_the_box_score_can_answer_is_now_graded(captured, ctx):
    newly = {}
    for row, graded in _grade_every_prop(captured, ctx):
        if row["hit"] is None and graded.get("hit") is not None:
            newly[_label(row, captured)] = (graded["actual"], graded["hit"])
    assert newly == EXPECTED_NEWLY_GRADED


def test_no_row_that_graded_before_changes_its_verdict(captured, ctx):
    """The direction that would be a REGRESSION, asserted on its own.

    #4783 is open about venue-contradicted grades on NFL pages, so a fix that
    newly disagrees with a Kalshi settlement is not obviously an improvement.
    Measured: on this game it disagrees with none of them — 0 flips against 312
    box-score-confirmed agreements. A future mapping that flips one has to come
    past this test and say so.
    """
    flips, preserved, box_confirmed = [], 0, 0
    for row, graded in _grade_every_prop(captured, ctx):
        served, fresh = row["hit"], graded.get("hit")
        if served is None or fresh is None:
            continue
        if served != fresh:
            flips.append((_label(row, captured), served, fresh))
            continue
        preserved += 1
        if graded.get("actual") is not None:
            # The box score read the stat itself and landed on the same verdict
            # the venue had already typed off the price. This is the cell that
            # makes the whole ship safe, so it is counted apart from the rows
            # the venue is still carrying alone.
            box_confirmed += 1
    assert flips == []
    assert preserved == 475
    assert box_confirmed == 312


def test_the_newly_graded_rows_corroborate_the_venue_in_the_band_it_refuses(
    captured, ctx
):
    """Why the fix is the vocabulary and NOT a looser `_VENUE_GRADE_*` bound.

    #6751's venue fallback types a verdict only when the settled price
    corroborates it (>= 0.9 won / <= 0.1 lost). Those bounds were calibrated on
    `KXNFLFFPTS`, whose settled prices converge; NFL box-score props do not, so
    the refused rows sit at 0.5-0.89 and the gate withholds exactly the close
    calls. There was no ground truth for that band — zero box-score-graded rows
    live in it — and `is_winner` agreeing on the rows the gate already passes
    cannot speak for the rows it refuses.

    The box score supplies that missing ground truth, and the venue was right
    all 11 times, INCLUDING "Brock Purdy: 7+" at a settled price of 0.89 that a
    looser floor would have graded a HIT off a 5-carry game. So the constants
    stay where they are.
    """
    checked = 0
    for row, graded in _grade_every_prop(captured, ctx):
        if row["hit"] is not None or graded.get("hit") is None:
            continue
        assert graded["hit"] == row["is_winner"], _label(row, captured)
        checked += 1
    assert checked == 11


def test_the_rushing_attempts_key_is_carries_not_rushing_attempts():
    """The naming trap, pinned: ESPN has no "rushing attempts" key at all."""
    assert _PROP_TICKER_TO_STAT["kxnflrshatt"] == "carries"


def test_kxnflrecyds_outranks_the_kxnflrec_prefix_it_extends(captured):
    """#1728's collision, on the pair this ship adds."""
    recyds = _Obj(external_id="KXNFLRECYDS-26SEP10SFLAR", name="x: Receiving Yards")
    rec = _Obj(external_id="KXNFLREC-26SEP10SFLAR", name="x: Receptions")
    assert _prop_stat_keys(recyds, {"stats_for_ticker": _stats}) == ["receiving yards"]
    assert _prop_stat_keys(rec, {"stats_for_ticker": _stats}) == ["receptions"]


def _stats(ticker_lower):
    from app.tasks.backfill_winners import _prop_stats_for_ticker

    return _prop_stats_for_ticker(ticker_lower)


@pytest.mark.parametrize(
    "prefix,why",
    [
        ("kxnflpassatt", "an ESPN line has completions, no attempts key"),
        ("kxnfltd", "does not say which of rushing/receiving/return TDs it sums"),
        ("kxnflffpts", "a scoring formula, not a box-score stat (#6751 grades it)"),
    ],
)
def test_the_deliberate_absences_stay_absent(prefix, why):
    """Each of these is a WITHHOLDING, not a gap for a later pattern-fill.

    Mapping one of them to a plausible neighbouring key is how a confident
    wrong verdict gets published, which is the failure #1728 exists for.
    """
    assert _stats(f"{prefix}-26sep10sflar") is None, why


def test_team_and_leaderboard_tickers_are_not_swept_up_by_a_player_prefix():
    """The blast-radius check: these share the KXNFL stem and must stay unmapped."""
    for ticker in (
        "kxnflteamyds",
        "kxnflteamtd",
        "kxnflteamsack",
        "kxnflfg",
        "kxnflmostrshyds",
        "kxnflmostrecyds",
        "kxnflrryds",
    ):
        assert _stats(f"{ticker}-26sep10sflar") is None, ticker
