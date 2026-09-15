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
4. the falsy-zero trap: a 0-0 draw is a final score;
5. the status gate admits the ghost both BEFORE its invented kick-off
   (``scheduled``) and after it (``suspended``), and never a ``live`` row. An
   earlier cut read only ``scheduled``, which is the clock gate this module had
   already deleted restated as a word, and the sweep shipped inert on all 11
   pairs in its own window.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.soccer_ghost_twins import (  # noqa: E402
    GHOST_KICKOFF_GRACE,
    GHOST_STATUSES,
    MAX_GHOST_LAG,
    NOT_A_TWIN,
    REFUSE_AMBIGUOUS,
    TWIN_FOUND,
    UNCLASSIFIED_SPORT_KEY,
    SoccerRow,
    block_key,
    classify_block,
    fold_unclassified_blocks,
    loose_block_key,
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


def test_a_ghost_whose_advertised_time_has_passed_is_still_a_ghost():
    """The rule this replaces required the ghost to be in the future, on the
    premise that "a row nobody is being shown as upcoming is not this defect".

    It is being shown. A `scheduled` row with no score whose hour has passed
    does not leave the league page — it leaves *Upcoming* and reappears under
    *Live & Paused* as "No result reported", with the real result one rail
    below (lane1/288's production shot for #5918). Under the old rule all ten
    measured ghosts would have aged out of the selector at their own fake
    kick-off, into the worse card, for the rest of the -5d window.
    """
    past_ghost = ghost_row(
        15400006,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 12, 21, 0, tzinfo=timezone.utc),
    )

    outcome, tag, _ = classify_block([past_ghost, SEVILLA_REAL], now=NOW)

    assert outcome == TWIN_FOUND
    assert tag.ghost_id == 15400006
    assert tag.canonical_id == SEVILLA_REAL.event_id


def test_a_match_that_has_just_kicked_off_is_never_the_row_we_stop_printing():
    """The one thing the clock still buys. A real fixture reads `scheduled`
    with no score for the first minutes of its first half, so a row inside
    GHOST_KICKOFF_GRACE of its own kick-off is left alone even when a scored,
    anchored twin sits within the window and every other gate is satisfied.
    """
    just_started = ghost_row(
        15400016,
        "Sevilla",
        "Valencia",
        NOW - (GHOST_KICKOFF_GRACE / 2),
    )

    outcome, tag, _ = classify_block([just_started, SEVILLA_REAL], now=NOW)

    assert outcome == NOT_A_TWIN
    assert tag is None


def test_the_kickoff_grace_is_a_bound_and_not_an_era():
    """Pinned against the constant on both sides, so the grace cannot be
    widened into "we never tag a past row" without this failing. One second
    inside is protected; one second outside is judged."""
    inside = ghost_row(
        15400017,
        "Sevilla",
        "Valencia",
        NOW - GHOST_KICKOFF_GRACE + timedelta(seconds=1),
    )
    outside = ghost_row(
        15400018,
        "Sevilla",
        "Valencia",
        NOW - GHOST_KICKOFF_GRACE - timedelta(seconds=1),
    )

    assert classify_block([inside, SEVILLA_REAL], now=NOW)[0] == NOT_A_TWIN
    assert classify_block([outside, SEVILLA_REAL], now=NOW)[0] == TWIN_FOUND


def test_a_row_kicking_off_at_this_very_instant_is_protected():
    """The boundary the grace exists for, written explicitly because a
    half-open window is exactly where an off-by-one hides."""
    at_kickoff = ghost_row(15400019, "Sevilla", "Valencia", NOW)

    assert classify_block([at_kickoff, SEVILLA_REAL], now=NOW)[0] == NOT_A_TWIN


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


def test_a_live_match_can_never_be_the_canonical_that_condemns_another_row():
    """`row_has_final_score` answers "are both scores present", and a match
    that is 0-0 in the fourth minute answers YES. The canonical's status gate
    is therefore the ONLY thing standing between a game in progress and the
    authority to stop another row printing — production carried exactly this
    row while this was written (15311881 Getafe 0-0 Deportivo, `live`).
    """
    in_progress = row(
        15400021,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 11, 19, 0, tzinfo=timezone.utc),
        status="live",
        scored=True,
        anchored=True,
    )

    outcome, tag, _ = classify_block([SEVILLA_GHOST, in_progress], now=NOW)

    assert outcome == NOT_A_TWIN
    assert tag is None


def test_a_suspended_ghost_is_the_state_the_shipped_predicate_could_not_see():
    """The specimen again, two days later — which is where it actually lived.

    This assertion is inverted from the one it replaces, and the row is the
    reason: an earlier cut read `suspended` as "a match that started and
    stopped" and excluded it, noting that five such rows sat in the production
    window. Those five were not live matches. They were these ghosts, already
    promoted out of `scheduled` by their own invented kick-off passing, and
    excluding them made the sweep inert on its entire named population —
    enabled 2026-09-14, 1,184 rows read, 0 written, 11 pairs sitting in the
    window meeting every predicate except this one.

    So the clock is moved and nothing else is: the same ghost `15298125`
    against the same canonical `15298233`, judged at an hour by which
    `backfill_winners` Phase 0 has written `suspended` on it (it fires two days
    past a row's own kick-off). The pair is still 2 days apart, still inside
    `MAX_GHOST_LAG`, and still exactly one ghost against one scored,
    fixture-anchored real row.
    """
    two_days_after_the_fake_kickoff = datetime(
        2026, 9, 15, 20, 0, tzinfo=timezone.utc
    )
    suspended_ghost = row(
        15298125,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc),
        status="suspended",
    )

    outcome, tag, _ = classify_block(
        [suspended_ghost, SEVILLA_REAL], now=two_days_after_the_fake_kickoff
    )

    assert outcome == TWIN_FOUND
    assert tag is not None
    assert tag.ghost_id == 15298125
    assert tag.canonical_id == 15298233


def test_a_live_row_is_never_the_ghost_we_stop_printing():
    """`live` is the one state that does mean "being played", so it stays out.

    A ghost passes through `live` on its way to `suspended`, so this costs us
    tags on rows that really are ghosts. That is the intended direction: a
    genuinely in-progress match reads unscored and unanchored in its opening
    minutes exactly as a ghost does, nothing in the row separates the two, and
    the sweep will see the same pair again in `suspended` within the hour.
    """
    live_ghost = row(
        15400024,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc),
        status="live",
    )

    outcome, tag, _ = classify_block(
        [live_ghost, SEVILLA_REAL],
        now=datetime(2026, 9, 13, 19, 40, tzinfo=timezone.utc),
    )

    assert outcome == NOT_A_TWIN
    assert tag is None


def test_the_admitted_ghost_states_are_exactly_scheduled_and_suspended():
    """The membership itself, so widening it again is a deliberate act.

    Every other state has a row that must never be tagged behind it: `live` is
    a match in progress, `completed`/`closed` carry results, `voided`/`merged`
    are already unprintable. A constant is the whole of this module's status
    gate, so it is pinned here rather than inferred from the cases above.
    """
    assert GHOST_STATUSES == ("scheduled", "suspended")

    for never_a_ghost in ("live", "completed", "closed", "voided", "merged"):
        assert never_a_ghost not in GHOST_STATUSES


def test_the_ghost_must_be_advertised_AFTER_the_row_that_was_played():
    """Direction, not distance. A scheduled row dated BEFORE a played row is a
    postponement or a rescheduling artefact, and calling it a copy would stop
    printing the earlier of two rows on the strength of a later one.
    """
    earlier_ghost = ghost_row(
        15400023,
        "Sevilla",
        "Valencia",
        SEVILLA_REAL.commence_time - timedelta(hours=6),
    )

    outcome, tag, _ = classify_block([earlier_ghost, SEVILLA_REAL], now=NOW)

    assert outcome == NOT_A_TWIN
    assert tag is None


def test_a_scheduled_row_that_carries_a_result_is_not_a_ghost():
    """The ghost side of the score gate, which had no test until the kick-off
    rule was widened and a mutation survived on it.

    A `scheduled` row carrying a final score is a row whose status is lagging
    its own result — the reader is being shown a real score. Stopping it from
    printing would hide a result to fix a label, which is the wrong trade in
    both directions, so the score alone disqualifies it from the ghost role.
    """
    scored_but_scheduled = ghost_row(
        15400020,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc),
        scored=True,
    )

    outcome, tag, _ = classify_block([scored_but_scheduled, SEVILLA_REAL], now=NOW)

    assert outcome == NOT_A_TWIN
    assert tag is None


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


# ── 6. `soccer_other` is not a competition, so it cannot separate two rows ────
#
# The section above pins the sport key as a separator, and it stays one for every
# key that NAMES a competition. `soccer_other` names none: it is the ingest's
# catch-all, 9,512 production rows in 90 days against 245 for La Liga, holding
# the Greek Cup, Copa do Brasil, four South American leagues and a cup's
# qualifying rounds all at once. Reading it as "a different competition" reads an
# absence as a fact, and it cost the sweep the Daejeon specimen below.
#
# The measurement that says this is safe is in the module docstring: over 365
# days of production soccer, played+scored+anchored rows with identical names in
# the same orientation inside MAX_GHOST_LAG number ONE, and that one is under a
# single sport key. Cross-key genuine rematches: zero.


#: The production specimen, 2026-09-14. The ghost is unclassified and three
#: hours late; the real row is a statpal-anchored K-League game that finished 2-2.
DAEJEON_GHOST = row(
    15307887,
    "Daejeon Citizen",
    "Pohang Steelers",
    datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc),
    status="suspended",
    sport_key="soccer_other",
)
DAEJEON_REAL = real_row(
    15305024,
    "Daejeon Citizen",
    "Pohang Steelers",
    datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc),
    sport_key="soccer_korea_kleague1",
)
DAEJEON_NOW = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)


def test_an_unclassified_ghost_is_decided_against_its_named_real_row():
    """The Daejeon specimen: `soccer_other` v `soccer_korea_kleague1`, one fixture.

    This is the whole reader-visible gain — before the fold the two rows sat in
    separate blocks, each a block of one, and `blocks_examined` was 0.
    """
    plan = plan_ghost_tags([DAEJEON_GHOST, DAEJEON_REAL], now=DAEJEON_NOW)

    assert plan.blocks_examined == 1
    assert [(t.ghost_id, t.canonical_id) for t in plan.tags] == [(15307887, 15305024)]


def test_the_fold_is_what_decides_it_and_not_some_other_relaxation():
    """Strawman guard: the same two rows under one NAMED key each still refuse.

    Without this, a test that merely deleted the sport key from the block key
    would pass the case above identically, and the narrow rule would be
    indistinguishable from the broad one this module rejected.
    """
    named_ghost = row(
        15307887,
        "Daejeon Citizen",
        "Pohang Steelers",
        datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc),
        status="suspended",
        sport_key="soccer_korea_fa_cup",
    )

    plan = plan_ghost_tags([named_ghost, DAEJEON_REAL], now=DAEJEON_NOW)

    assert plan.blocks_examined == 0
    assert plan.tags == []


def test_two_named_competitions_for_the_same_clubs_refuse_the_unclassified_row():
    """Which competition an unclassified row is in is a question we do not answer.

    A league fixture and a cup tie between the same clubs inside the window: the
    unclassified row could belong to either, so it joins neither and the refusal
    is reported.
    """
    cup_real = real_row(
        15305999,
        "Daejeon Citizen",
        "Pohang Steelers",
        datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc),
        sport_key="soccer_korea_fa_cup",
    )

    plan = plan_ghost_tags([DAEJEON_GHOST, DAEJEON_REAL, cup_real], now=DAEJEON_NOW)

    assert plan.tags == []
    assert any("2 named competitions" in r for r in plan.refusals), plan.refusals


def test_an_unclassified_row_with_no_named_sibling_is_left_where_it_is():
    """No named block for these clubs — the fold is a no-op, not an error."""
    other_ghost = row(
        15311117,
        "Sligo Rovers FC",
        "Galway United FC",
        datetime(2026, 9, 14, 18, 45, tzinfo=timezone.utc),
        status="suspended",
        sport_key="soccer_other",
    )
    other_twin = row(
        15310858,
        "Sligo Rovers FC",
        "Galway United FC",
        datetime(2026, 9, 14, 18, 45, tzinfo=timezone.utc),
        status="suspended",
        sport_key="soccer_other",
    )

    plan = plan_ghost_tags([other_ghost, other_twin], now=DAEJEON_NOW)

    assert plan.tags == []
    assert plan.refusals == []
    assert plan.blocks_examined == 1


def test_the_fold_never_reaches_a_row_under_a_named_key():
    """The cup-tie guard, restated against the fold rather than the block key.

    `soccer_spain_copa_del_rey` and `soccer_spain_la_liga` are both real
    competitions, so nothing moves and Sevilla v Valencia stays two fixtures.
    """
    cup_ghost = ghost_row(
        15400009,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc),
        sport_key="soccer_spain_copa_del_rey",
    )

    folded, refusals = fold_unclassified_blocks(
        {
            block_key(r.sport_key, r.home_team_name, r.away_team_name): [r]
            for r in (cup_ghost, SEVILLA_REAL)
        }
    )

    assert len(folded) == 2
    assert refusals == []


def test_folding_cannot_turn_a_refusal_into_a_tag():
    """An unclassified SECOND ghost makes the named block ambiguous, not decided.

    The fold only ever adds rows to a block, so the direction it can fail in is
    under-tagging. This pins that: the Sevilla pair is decidable on its own, and
    an unclassified third row between the same clubs takes the decision away
    rather than getting one of the two rows tagged anyway.
    """
    decided = plan_ghost_tags([SEVILLA_GHOST, SEVILLA_REAL], now=NOW)
    assert len(decided.tags) == 1

    unclassified_extra = ghost_row(
        15400077,
        "Sevilla",
        "Valencia",
        datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc),
        sport_key="soccer_other",
    )
    plan = plan_ghost_tags(
        [SEVILLA_GHOST, SEVILLA_REAL, unclassified_extra], now=NOW
    )

    assert plan.tags == []
    assert any("not decidable" in r for r in plan.refusals), plan.refusals


def test_an_unplaceable_row_that_could_not_be_a_ghost_is_not_reported():
    """The refusal list is for decisions we declined, not for every unplaced row.

    Two named competitions carry these clubs, so the unclassified block cannot be
    placed — but its only row is settled and scored, so there was never a
    decision to decline. Without this the noise guard is unmeasured and the
    refusal list fills with rows nobody was ever going to tag.
    """
    settled_unclassified = real_row(
        15305111,
        "Daejeon Citizen",
        "Pohang Steelers",
        datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc),
        sport_key="soccer_other",
    )
    cup_real = real_row(
        15305999,
        "Daejeon Citizen",
        "Pohang Steelers",
        datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc),
        sport_key="soccer_korea_fa_cup",
    )

    plan = plan_ghost_tags(
        [settled_unclassified, cup_real, DAEJEON_REAL], now=DAEJEON_NOW
    )

    assert plan.refusals == []
    assert plan.tags == []


def test_every_soccer_key_shares_one_llm_category():
    """The property that keeps a cross-key fold from losing the ghost's prices.

    The ghost usually holds the markets (8 on 15307887, 0 on its canonical), so
    the tag is only safe because `_build_game_markets` folds them onto the
    canonical. That reader's cross-sport safety net is
    `sport_id == event.sport_id OR llm_sport_category == expected_category`, and
    an unclassified ghost fails the first clause by construction — its markets
    carry the unclassified `sport_id`. It survives on the second, which holds
    only because `expected_category` is derived from the sport key's PREFIX.

    Measured on production 2026-09-14, whole population: 2,865 markets on
    unclassified ghost candidates, all 2,865 categorised `soccer`, none null and
    none other. This pins the mechanism behind that number, so a future split of
    the soccer prefix into two categories fails here rather than silently
    emptying a folded fixture.
    """
    from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY

    assert (
        UNCLASSIFIED_SPORT_KEY.split("_")[0]
        == "soccer_korea_kleague1".split("_")[0]
        == "soccer"
    )
    assert SPORT_PREFIX_TO_LLM_CATEGORY.get("soccer") == "soccer"


# ── 7. the second pass: the same rule, with the club's legal suffix folded ───
#
# What the first pass leaves behind was measured by lane1 on production
# 2026-09-14 (comment 5670673213 on #3813): 18 ghosts holding 59 markets whose
# canonical serves zero, and the reader-visible failure is not a duplicate card —
# it is /events/15307330, Sligo Rovers 1-3 Galway United, Final, chart, and then
# no market rail at all, because its settled goal-total rungs sit on a row the
# page never reads.
#
# The tests below pin the three things that make the second pass safe: it can
# only ADD, it still refuses to cross two NAMED competitions, and the suffix it
# strips is a legal form and never a squad.


#: The production specimen the second pass exists for, 2026-09-14. One character
#: of difference — `FC` — put these two rows in different blocks.
GWANGJU_GHOST = row(
    15307681,
    "Gwangju",
    "FC Anyang",
    datetime(2026, 9, 13, 8, 30, tzinfo=timezone.utc),
    status="suspended",
    sport_key=UNCLASSIFIED_SPORT_KEY,
)
GWANGJU_REAL = real_row(
    15306857,
    "Gwangju FC",
    "FC Anyang",
    datetime(2026, 9, 13, 5, 30, tzinfo=timezone.utc),
    sport_key="soccer_korea_kleague1",
)
GWANGJU_NOW = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)


def test_the_suffix_specimen_is_decided_by_the_second_pass():
    """Gwangju: the first pass cannot see this pair, the second can.

    `Gwangju` and `Gwangju FC` are one club, so the narrow key puts the ghost and
    its canonical in different blocks and `classify_block` is never handed them.
    """
    plan = plan_ghost_tags([GWANGJU_GHOST, GWANGJU_REAL], now=GWANGJU_NOW)

    assert [(t.ghost_id, t.canonical_id) for t in plan.tags] == [(15307681, 15306857)]
    assert plan.residual_tags == 1, "it must be the SECOND pass that found it"
    assert plan.blocks_examined == 0, "the narrow key must still see two blocks"


def test_the_first_pass_is_what_the_second_one_cannot_touch():
    """The whole safety argument, as an assertion: adding rows the second pass
    can reach never changes what the first pass decided.

    Sevilla is decidable today. This is the exact pair the rejected design — one
    widened `block_key` instead of two passes — turned into a refusal, by merging
    two blocks that had each already resolved.
    """
    sevilla_suffixed_ghost = ghost_row(
        15400010,
        "Sevilla FC",
        "Valencia CF",
        datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc),
    )

    alone = plan_ghost_tags([SEVILLA_GHOST, SEVILLA_REAL], now=NOW)
    crowded = plan_ghost_tags(
        [SEVILLA_GHOST, SEVILLA_REAL, sevilla_suffixed_ghost], now=NOW
    )

    assert [(t.ghost_id, t.canonical_id) for t in alone.tags] == [(15298125, 15298233)]
    assert (15298125, 15298233) in [(t.ghost_id, t.canonical_id) for t in crowded.tags]


def test_a_block_the_first_pass_refused_is_never_resolved_by_the_second():
    """Ambiguity is monotone, and that is what makes re-blocking safe at all.

    Two candidate ghosts under one narrow key are refused. The second pass sees
    the same two rows plus a suffixed third; a larger block can only add pairs,
    so it must refuse too and must never pick one.
    """
    ghost_a = ghost_row(
        15400011, "Sevilla", "Valencia", datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc)
    )
    ghost_b = ghost_row(
        15400012, "Sevilla", "Valencia", datetime(2026, 9, 13, 21, 0, tzinfo=timezone.utc)
    )
    ghost_c = ghost_row(
        15400013,
        "Sevilla FC",
        "Valencia",
        datetime(2026, 9, 13, 22, 0, tzinfo=timezone.utc),
    )

    plan = plan_ghost_tags([ghost_a, ghost_b, ghost_c, SEVILLA_REAL], now=NOW)

    assert plan.tags == []
    assert plan.refusals, "a refusal is reported, never silently dropped"


def test_the_second_pass_still_refuses_to_cross_two_named_competitions():
    """The Köln pair, and the reason the sport key did not leave the key.

    Measured on production 2026-09-14 over 365 days of played, scored soccer
    (8,838 rows, anchoring NOT required — requiring it is what hid this):

        15293467  1. FC Köln v TSG Hoffenheim  08-28 16:30Z  1-0  ..._bundesliga_women
        14970278  1. FC Köln v TSG Hoffenheim  08-29 13:30Z  3-2  ..._bundesliga

    Two real fixtures, 21 hours apart, different results, the same two club names
    in the same orientation, separated by nothing but the sport key. A second
    pass that dropped the key would call the women's fixture a ghost.
    """
    womens_ghost = row(
        15293467,
        "1. FC Köln",
        "TSG Hoffenheim",
        datetime(2026, 8, 28, 16, 30, tzinfo=timezone.utc),
        status="scheduled",
        sport_key="soccer_germany_bundesliga_women",
    )
    mens_real = real_row(
        14970278,
        "1. FC Köln",
        "TSG Hoffenheim",
        datetime(2026, 8, 27, 13, 30, tzinfo=timezone.utc),
        sport_key="soccer_germany_bundesliga",
    )

    plan = plan_ghost_tags([womens_ghost, mens_real], now=GWANGJU_NOW)

    assert plan.tags == [], "a women's fixture is not a copy of the men's"
    assert plan.residual_blocks_examined == 0


def test_the_suffix_strip_is_a_legal_form_and_never_a_squad():
    """`Sabadell FC` is `Sabadell`; `Real Sociedad B` is NOT `Real Sociedad`.

    The reserve side is a different team that plays a different competition, and
    it is the one trailing token that must survive the strip. `b` is absent from
    CLUB_LEGAL_SUFFIXES for exactly this reason.
    """
    assert loose_block_key("Sabadell FC", "Andorra CF") == ("sabadell", "andorra")
    assert loose_block_key("Sligo Rovers FC", " GALWAY UNITED FC ") == (
        "sligo rovers",
        "galway united",
    )
    assert loose_block_key("Real Sociedad B", "x") == ("real sociedad b", "x")
    assert loose_block_key("Real Sociedad", "x") != loose_block_key("Real Sociedad B", "x")


def test_the_strip_is_trailing_only_and_takes_one_token():
    """A LEADING `FC` is not a legal form we can drop: nothing measured says
    `FC Zurich` and `Zurich` are one club, and each extra strip is another shape
    the precision measurement never examined."""
    assert loose_block_key("FC Zurich", "x") == ("fc zurich", "x")
    assert loose_block_key("FC Sion", "x") != loose_block_key("Sion", "x")
    assert loose_block_key("Real Madrid CF SC", "x") == ("real madrid cf", "x")


def test_a_reverse_fixture_never_shares_a_block_under_the_loose_key_either():
    """Orientation is load-bearing in the precision measurement, so it has to
    survive the relaxation that the measurement was re-run for."""
    assert loose_block_key("Sabadell FC", "Mallorca") != loose_block_key(
        "Mallorca", "Sabadell FC"
    )


def test_the_second_pass_does_not_re_report_a_block_the_first_one_examined():
    """A block whose rows already share one narrow key was decided by the first
    pass. Re-reading it would double-count the block and restate its refusal in
    different words."""
    plan = plan_ghost_tags([SEVILLA_GHOST, SEVILLA_REAL], now=NOW)

    assert plan.blocks_examined == 1
    assert plan.residual_blocks_examined == 0
    assert len(plan.refusals) == len(set(plan.refusals))


def test_one_played_fixture_may_have_two_id_less_copies():
    """A canonical is NOT withheld from the second pass.

    Ghost 15305187 and ghost 15307878 are both copies of Andorra CF v Real
    Sociedad B. Withholding the canonical once the first pass has used it drops
    the second ghost for no reason but bookkeeping.
    """
    exact_ghost = ghost_row(
        15305187,
        "Andorra CF",
        "Real Sociedad B",
        datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc),
        sport_key=UNCLASSIFIED_SPORT_KEY,
    )
    suffixed_ghost = row(
        15307878,
        "Andorra",
        "Real Sociedad B",
        datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc),
        status="suspended",
        sport_key=UNCLASSIFIED_SPORT_KEY,
    )
    real = real_row(
        15305059,
        "Andorra CF",
        "Real Sociedad B",
        datetime(2026, 9, 11, 19, 0, tzinfo=timezone.utc),
        sport_key="soccer_spain_segunda_division",
    )

    plan = plan_ghost_tags([exact_ghost, suffixed_ghost, real], now=NOW)

    assert sorted(t.ghost_id for t in plan.tags) == [15305187, 15307878]
    assert {t.canonical_id for t in plan.tags} == {15305059}
