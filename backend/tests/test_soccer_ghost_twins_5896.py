"""#5896 — the judgement that stops a played match being advertised as tonight's.

THE DEFECT, measured on production 2026-09-13. Ten soccer rows were being shown
as upcoming fixtures for that evening, and every one of them was a second copy
of a game that had already been played::

    ghost  15298125 Sevilla v Valencia  09-13 19:00Z  scheduled  no score  no anchor
    real   15298233 Sevilla v Valencia  09-11 19:00Z  completed  1-0       espn 401882878

The ESPN slate for that date, read at the authority, held four La Liga fixtures
and none of the four ghosts among them; the Argentine, Segunda and Brasileirao
slates likewise.

WHAT THIS SUITE PINS, in order:

1. the measured specimen is decided, and decided in the right direction — the
   row that stops printing is the id-less one, which is the side ruling 048
   argues for;
2. the anchor is ``espn_id``/``statpal_fixture_id`` and NOT ``external_id``.
   This is the one substitution that looks like a tidy-up and silently refuses
   every pair: both halves of all ten measured pairs carry an ``external_id``,
   because the two Odds API passes minted two surrogate hashes for one fixture;
3. every way the pair can be a REAL rematch is refused rather than guessed —
   outside the measured 3-day window, orientation swapped, two candidates on
   either side;
4. the falsy-zero trap: a 0-0 draw is a final score.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.soccer_ghost_twins import (  # noqa: E402
    MAX_GHOST_LAG,
    NOT_A_TWIN,
    REFUSE_AMBIGUOUS,
    TWIN_FOUND,
    SoccerRow,
    block_key,
    classify_block,
    plan_ghost_tags,
    row_has_final_score,
    row_is_fixture_anchored,
)

#: "Now" for every case below — the hour the specimen was measured, so the
#: ghost's 19:00Z kick-off is genuinely still in the future and no assertion
#: here branches on the wall clock (gotcha #44).
NOW = datetime(2026, 9, 13, 14, 49, tzinfo=timezone.utc)


def row(
    event_id,
    home,
    away,
    when,
    *,
    status="scheduled",
    scored=False,
    anchored=False,
    sport_key="soccer_spain_la_liga",
):
    return SoccerRow(
        event_id=event_id,
        sport_key=sport_key,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        status=status,
        has_final_score=scored,
        is_fixture_anchored=anchored,
    )


def ghost_row(event_id, home, away, when, **kw):
    """The row being wrongly advertised: scheduled, no score, no fixture id.

    Deliberately NOT "an empty row" — ghost 15298075 carries eleven resolved
    Polymarket markets. What a ghost never carries is a final score or an
    authority fixture id.
    """
    return row(event_id, home, away, when, status="scheduled", **kw)


def real_row(event_id, home, away, when, **kw):
    kw.setdefault("scored", True)
    kw.setdefault("anchored", True)
    return row(event_id, home, away, when, status="completed", **kw)


# ── 1. the measured specimen ─────────────────────────────────────────────────


SEVILLA_GHOST = ghost_row(
    15298125, "Sevilla", "Valencia", datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc)
)
SEVILLA_REAL = real_row(
    15298233, "Sevilla", "Valencia", datetime(2026, 9, 11, 19, 0, tzinfo=timezone.utc)
)


def test_the_production_specimen_is_decided_and_the_id_less_row_is_the_ghost():
    outcome, tag, _ = classify_block([SEVILLA_GHOST, SEVILLA_REAL], now=NOW)

    assert outcome == TWIN_FOUND
    assert tag.ghost_id == 15298125, "the row we stop printing must be the id-less one"
    assert tag.canonical_id == 15298233


def test_the_decision_does_not_depend_on_which_row_was_seen_first():
    """Order-independence, because the population read is ordered by id and the
    ghost's id is LOWER than its canonical's on all ten measured pairs — a
    planner that quietly took `members[0]` would pass a one-order test."""
    forward, tag_a, _ = classify_block([SEVILLA_GHOST, SEVILLA_REAL], now=NOW)
    reverse, tag_b, _ = classify_block([SEVILLA_REAL, SEVILLA_GHOST], now=NOW)

    assert forward == reverse == TWIN_FOUND
    assert (tag_a.ghost_id, tag_a.canonical_id) == (tag_b.ghost_id, tag_b.canonical_id)


def test_the_whole_measured_population_plans_one_tag_per_pair():
    """All four La Liga pairs at once, through the planner rather than the
    classifier, so the blocking is exercised and not just the decision."""
    pairs = [
        (15298075, "Real Racing Club de Santander", "Alaves", 9, 12, 12, 0),
        (15298076, "Athletic Bilbao", "Elche CF", 9, 12, 16, 30),
        (15298079, "CA Osasuna", "Espanyol", 9, 12, 14, 15),
        (15298125, "Sevilla", "Valencia", 9, 11, 19, 0),
    ]
    rows = []
    for ghost_id, home, away, month, day, hour, minute in pairs:
        rows.append(
            ghost_row(
                ghost_id,
                home,
                away,
                datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc),
            )
        )
        rows.append(
            real_row(
                ghost_id + 158,
                home,
                away,
                datetime(2026, month, day, hour, minute, tzinfo=timezone.utc),
            )
        )

    plan = plan_ghost_tags(rows, now=NOW)

    assert plan.blocks_examined == 4
    assert {t.ghost_id for t in plan.tags} == {p[0] for p in pairs}
    assert plan.refusals == []


# ── 2. the anchor is the fixture id, never the ingest surrogate ──────────────


def test_external_id_is_not_an_anchor_here():
    """`row_is_fixture_anchored` reads two columns, not three.

    Swapping in `tennis_twin_pairs.row_is_id_anchored` — which also reads
    `external_id` — is the plausible tidy-up, and it would mark BOTH halves of
    every measured pair anchored and refuse all ten. This asserts the signature
    as much as the result: there is no `external_id` parameter to pass.
    """
    assert row_is_fixture_anchored(espn_id=None, statpal_fixture_id=None) is False
    assert row_is_fixture_anchored(espn_id="401882878", statpal_fixture_id=None) is True
    assert row_is_fixture_anchored(espn_id=None, statpal_fixture_id="9544351") is True


def test_a_ghost_that_has_acquired_a_fixture_id_is_never_tagged():
    """The tripwire. The day an anchorless row acquires an ESPN id it is a row
    an authority knows about, so it is not a ghost and this refuses rather than
    guesses — even though every other field still looks exactly like the
    specimen."""
    anchored_ghost = ghost_row(
        15298125,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc),
        anchored=True,
    )

    outcome, tag, _ = classify_block([anchored_ghost, SEVILLA_REAL], now=NOW)

    assert outcome == NOT_A_TWIN
    assert tag is None


def test_an_unanchored_completed_row_cannot_be_the_canonical():
    """The Coritiba pair (15299310 / 15299941) has no ESPN or StatPal id on
    EITHER side, so it is refused and stays visible. That is the intended
    failure direction: a duplicate we miss is fixable, a real fixture we hide is
    not."""
    unanchored_real = real_row(
        15299941,
        "Coritiba",
        "Atletico Paranaense",
        datetime(2026, 9, 12, 0, 0, tzinfo=timezone.utc),
        anchored=False,
        sport_key="soccer_brazil_campeonato",
    )
    ghost = ghost_row(
        15299310,
        "Coritiba",
        "Atletico Paranaense",
        datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc),
        sport_key="soccer_brazil_campeonato",
    )

    outcome, tag, _ = classify_block([ghost, unanchored_real], now=NOW)

    assert outcome == NOT_A_TWIN
    assert tag is None


# ── 3. every shape that could be a real fixture is refused ───────────────────


def test_a_reverse_fixture_never_shares_a_block():
    """A two-legged tie swaps home and away, so the key's ordering — not a time
    rule — is what keeps the second leg out of reach."""
    assert block_key("soccer_uefa_champs_league", "Sevilla", "Valencia") != block_key(
        "soccer_uefa_champs_league", "Valencia", "Sevilla"
    )


def test_a_meeting_outside_the_measured_window_is_not_a_twin():
    """Measured over 365 days of production soccer: zero genuine
    same-orientation rematches inside 3 days. Outside it, a scheduled fixture
    against the same opponent is an ordinary league season and must print."""
    later = ghost_row(
        15400000,
        "Sevilla",
        "Valencia",
        SEVILLA_REAL.commence_time + MAX_GHOST_LAG + timedelta(hours=1),
    )

    outcome, tag, _ = classify_block([later, SEVILLA_REAL], now=NOW)

    assert outcome == NOT_A_TWIN
    assert tag is None


def test_the_window_boundary_is_inclusive():
    at_bound = ghost_row(
        15400001, "Sevilla", "Valencia", SEVILLA_REAL.commence_time + MAX_GHOST_LAG
    )

    assert classify_block([at_bound, SEVILLA_REAL], now=NOW)[0] == TWIN_FOUND


def test_the_window_is_three_days_and_a_fourth_day_is_a_different_fixture():
    """Stated as literal dates, not as `MAX_GHOST_LAG + 1h`.

    A test written against the constant moves with it, so widening the window
    to thirty days would leave the suite green — and the window is the only
    thing standing between this sweep and a genuine rematch. The bound is
    measured (365 days of production soccer, zero same-orientation rematches
    inside three days), so the number is pinned here where changing it is a
    deliberate act that has to re-measure.
    """
    assert MAX_GHOST_LAG == timedelta(days=3)

    played = real_row(
        15400010, "Sevilla", "Valencia", datetime(2026, 9, 10, 19, 0, tzinfo=timezone.utc)
    )
    four_days_later = ghost_row(
        15400011, "Sevilla", "Valencia", datetime(2026, 9, 14, 19, 0, tzinfo=timezone.utc)
    )

    assert classify_block([four_days_later, played], now=NOW)[0] == NOT_A_TWIN


def test_a_ghost_dated_BEFORE_a_completed_row_is_never_hidden():
    """The lag test is signed, and that is not decoration.

    `completed_at >= commence_time` is an invariant (gotcha #46) and rows do
    violate it: a played row can carry a future kick-off. When one does, an
    unsigned `abs(lag) <= 3 days` would hide the genuinely upcoming fixture
    sitting just before it — hiding a real match on the strength of a corrupt
    partner. The correct answer is to refuse.
    """
    misdated_played = real_row(
        15400012, "Sevilla", "Valencia", datetime(2026, 9, 14, 19, 0, tzinfo=timezone.utc)
    )
    upcoming = ghost_row(
        15400013, "Sevilla", "Valencia", datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc)
    )

    outcome, tag, _ = classify_block([upcoming, misdated_played], now=NOW)

    assert outcome == NOT_A_TWIN
    assert tag is None


def test_two_candidate_ghosts_are_refused_rather_than_guessed():
    second_ghost = ghost_row(
        15400003,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 13, 21, 0, tzinfo=timezone.utc),
    )

    outcome, tag, why = classify_block(
        [SEVILLA_GHOST, second_ghost, SEVILLA_REAL], now=NOW
    )

    assert outcome == REFUSE_AMBIGUOUS
    assert tag is None
    assert "not decidable" in why


def test_two_candidate_real_rows_are_refused_rather_than_guessed():
    second_real = real_row(
        15400004,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 12, 19, 0, tzinfo=timezone.utc),
    )

    outcome, tag, _ = classify_block([SEVILLA_GHOST, second_real, SEVILLA_REAL], now=NOW)

    assert outcome == REFUSE_AMBIGUOUS
    assert tag is None


def test_a_refusal_is_reported_and_never_silently_dropped():
    """An ambiguous block is the one an operator has to see — it is where a new
    shape shows up first."""
    second_ghost = ghost_row(
        15400005,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 13, 21, 0, tzinfo=timezone.utc),
    )

    plan = plan_ghost_tags([SEVILLA_GHOST, second_ghost, SEVILLA_REAL], now=NOW)

    assert plan.tags == []
    assert len(plan.refusals) == 1
    assert "sevilla v valencia" in plan.refusals[0]


def test_a_ghost_whose_advertised_time_has_passed_is_left_alone():
    """A row nobody is being shown as upcoming is not this defect, and the sweep
    does not get to relabel history on its way past."""
    past_ghost = ghost_row(
        15400006,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 12, 21, 0, tzinfo=timezone.utc),
    )

    outcome, tag, _ = classify_block([past_ghost, SEVILLA_REAL], now=NOW)

    assert outcome == NOT_A_TWIN
    assert tag is None


def test_a_scheduled_row_with_no_played_partner_is_left_alone():
    """The overwhelming majority: two rows for two different fixtures between
    the same clubs, neither of them played yet."""
    other = ghost_row(
        15400007,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 14, 19, 0, tzinfo=timezone.utc),
    )

    outcome, _, _ = classify_block([SEVILLA_GHOST, other], now=NOW)

    assert outcome == NOT_A_TWIN


def test_a_canonical_must_carry_a_result_not_merely_a_status():
    """`completed` with no score is a row mid-ingest, not a played match."""
    scoreless = real_row(
        15400008,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 11, 19, 0, tzinfo=timezone.utc),
        scored=False,
    )

    outcome, _, _ = classify_block([SEVILLA_GHOST, scoreless], now=NOW)

    assert outcome == NOT_A_TWIN


# ── 4. the falsy-zero trap ───────────────────────────────────────────────────


def test_a_goalless_draw_is_a_final_score():
    """`if home_score` reads 0-0 as "no result" and would refuse every goalless
    match — which in soccer is roughly one game in ten."""
    assert row_has_final_score(home_score=0, away_score=0) is True
    assert row_has_final_score(home_score=0, away_score=None) is False
    assert row_has_final_score(home_score=None, away_score=None) is False


def test_the_block_key_folds_case_and_whitespace_and_nothing_else():
    """The narrow key is the measured one. Diacritic folding would match rows
    the 365-day precision measurement never examined, so it is deliberately
    absent and this pins that it stays absent."""
    assert block_key("soccer_spain_la_liga", " Sevilla ", "VALENCIA") == block_key(
        "SOCCER_SPAIN_LA_LIGA", "sevilla", "valencia"
    )
    assert block_key("soccer_spain_la_liga", "Alaves", "x") != block_key(
        "soccer_spain_la_liga", "Alavés", "x"
    )


def test_two_clubs_in_different_competitions_do_not_share_a_block():
    """Same names, different sport key — a cup tie and a league fixture are two
    fixtures, and the key says so before any time rule is consulted."""
    cup_ghost = ghost_row(
        15400009,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc),
        sport_key="soccer_spain_copa_del_rey",
    )

    plan = plan_ghost_tags([cup_ghost, SEVILLA_REAL], now=NOW)

    assert plan.blocks_examined == 0
    assert plan.tags == []
