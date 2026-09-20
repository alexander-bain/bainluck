"""#7549 — the copies beside a proof are drained, and nothing else is.

THE DEFECT, measured on production 2026-09-20. Searching ``feyenoord`` claimed
**63 games** and page one led with a card for a match that had finished 5-0 four
hours earlier. Fifty-seven of those rows are one Eredivisie fixture, minted one
per Kalshi market leg::

    canonical 15306199  Feyenoord v FC Utrecht  09-20 10:15Z  completed 5-0  statpal 9551358
    proven    15316082  Feyenoord v Utrecht     09-20 13:15Z  suspended      duplicate-of:15306199
    husk      15315219  Feyenoord v Utrecht     09-20 13:15Z  suspended      no score, no id, 0 markets
    …                                                                        × 56

One of the fifty-seven was already proven a duplicate by the Polymarket
container rail, off a shared provider event id. The other fifty-six carry no
proof of their own, and — this is what makes them invisible to every pass that
shipped — the canonical spells its away club ``FC Utrecht`` where all of them
spell it ``Utrecht``. That is a LEADING token, which ``loose_block_key``
deliberately does not strip, so no key in the module puts the copies and their
canonical in one block.

WHAT THIS SUITE PINS, in order:

1. the measured specimen drains — 56 husks tagged against ``15306199``, reached
   through the proven sibling and NOT through any widened name key;
2. the canonical arrives by PRIMARY KEY. Every case here keeps the canonical
   outside the block, because a canonical that happened to share the block would
   let a much weaker rule pass these tests;
3. every way the proof can be the wrong one to extend is refused rather than
   guessed: two canonicals named in one block, a named canonical that is not
   played/anchored today, a named canonical outside the window, a second real
   fixture sharing the key;
4. the pass extends a proof and never manufactures one — strip the tag from the
   sibling and the same 57 rows yield nothing at all;
5. it cannot revise an earlier pass's decision, and a row that already carries a
   tag is evidence rather than subject, so a second run over the same population
   writes nothing.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.soccer_ghost_twins import (  # noqa: E402
    GHOST_KICKOFF_GRACE,
    MAX_GHOST_LAG,
    NOT_A_TWIN,
    REFUSE_AMBIGUOUS,
    TWIN_FOUND,
    SoccerRow,
    classify_proven_sibling_block,
    plan_ghost_tags,
    proven_sibling_pass,
)

#: "Now" for every case here: four hours after the specimen's real kick-off, the
#: hour the defect was photographed. Fixed, so nothing below branches on the wall
#: clock (gotcha #44).
NOW = datetime(2026, 9, 20, 14, 15, tzinfo=timezone.utc)

KICKOFF = datetime(2026, 9, 20, 10, 15, tzinfo=timezone.utc)
ADVERTISED = datetime(2026, 9, 20, 13, 15, tzinfo=timezone.utc)

CANONICAL_ID = 15306199
PROVEN_ID = 15316082


def husk(event_id, *, when=ADVERTISED, home="Feyenoord", away="Utrecht", **kw):
    """One of the fifty-six: advertised, unscored, unanchored, id-less.

    ``market_count`` is 0 by default because most of them genuinely hold
    nothing — the leg that minted the row was re-linked later and left an empty
    husk. A husk holding markets is the same row to this pass, and
    :func:`test_a_husk_with_markets_is_the_same_row_to_this_pass` says so.
    """
    return SoccerRow(
        event_id=event_id,
        sport_key=kw.pop("sport_key", "soccer_netherlands_eredivisie"),
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        status=kw.pop("status", "suspended"),
        has_final_score=kw.pop("has_final_score", False),
        is_fixture_anchored=kw.pop("is_fixture_anchored", False),
        **kw,
    )


def proven(event_id=PROVEN_ID, *, names=CANONICAL_ID, **kw):
    """A husk that another rail has ALREADY proven a duplicate of ``names``."""
    return husk(event_id, duplicate_of=names, **kw)


def canonical(event_id=CANONICAL_ID, *, when=KICKOFF, **kw):
    """The real fixture: played, scored, fixture-anchored — and note the name.

    ``FC Utrecht`` against the copies' ``Utrecht`` is not decoration. It is the
    production spelling, and it is the reason this row is in a different block
    from every row that copies it.
    """
    return SoccerRow(
        event_id=event_id,
        sport_key=kw.pop("sport_key", "soccer_netherlands_eredivisie"),
        home_team_name=kw.pop("home", "Feyenoord"),
        away_team_name=kw.pop("away", "FC Utrecht"),
        commence_time=when,
        status=kw.pop("status", "completed"),
        has_final_score=kw.pop("has_final_score", True),
        is_fixture_anchored=kw.pop("is_fixture_anchored", True),
        market_count=kw.pop("market_count", 5),
        **kw,
    )


def specimen(husks=3):
    """The production shape: one canonical, one proven copy, ``husks`` husks."""
    return (
        [canonical(), proven()]
        + [husk(15315219 + i) for i in range(husks)]
    )


def tags_of(rows, *, now=NOW):
    tags, refusals, examined = proven_sibling_pass(
        rows, decided_ghost_ids=set(), now=now
    )
    return [(t.ghost_id, t.canonical_id) for t in tags], refusals, examined


# ── 1. the measured specimen ─────────────────────────────────────────────────


def test_the_production_specimen_drains_every_husk_onto_the_played_row():
    tags, refusals, examined = tags_of(specimen(husks=56))

    assert len(tags) == 56, "one tag per husk, and none for the proven sibling"
    assert {canonical_id for _, canonical_id in tags} == {CANONICAL_ID}
    assert PROVEN_ID not in {ghost_id for ghost_id, _ in tags}
    assert CANONICAL_ID not in {ghost_id for ghost_id, _ in tags}
    assert examined == 1, "the copies are one block; the canonical is not in it"
    assert refusals == []


def test_the_canonical_is_never_in_the_block_it_is_the_canonical_of():
    """The property the whole pass rests on, asserted rather than assumed.

    If the canonical shared the copies' block, a far weaker rule — "pair the
    played row with the id-less ones beside it" — would satisfy every other test
    in this file. It does not share it, in production or here.
    """
    rows = specimen(husks=2)
    _tags, _refusals, examined = tags_of(rows)

    assert examined == 1
    blocked_with_the_copies = [
        r for r in rows if (r.home_team_name, r.away_team_name) == ("Feyenoord", "Utrecht")
    ]
    assert CANONICAL_ID not in {r.event_id for r in blocked_with_the_copies}


def test_no_other_pass_reaches_the_specimen_so_this_one_is_the_whole_repair():
    """The five shipped passes plan NOTHING on these rows. #7549's measurement.

    Not a claim about the specimen only: it is why the pass exists, so a change
    that let another pass reach this population would make the sixth one
    unnecessary and this test is where that shows up.
    """
    plan = plan_ghost_tags(specimen(husks=56), now=NOW)

    assert plan.proven_tags == 56
    assert plan.residual_tags == 0
    assert plan.ticker_tags == 0
    assert plan.stranded_tags == 0
    assert plan.fixture_tags == 0
    assert len(plan.tags) == 56, "no first-pass tag either"


# ── 2. the proof is READ, never manufactured ─────────────────────────────────


def test_without_the_existing_proof_the_same_rows_yield_nothing():
    """Strip one tag and the drain stops. The pass extends; it does not decide.

    This is the mutation that matters most: a rule that quietly fell back to
    "the played row with the same clubs" would keep draining here.
    """
    rows = [canonical()] + [husk(15315219 + i) for i in range(57)]

    tags, refusals, examined = tags_of(rows)

    assert tags == []
    assert examined == 0, "a block with no proven member is never even examined"
    assert refusals == []


def test_two_canonicals_named_in_one_block_are_refused_rather_than_picked():
    rows = specimen(husks=3) + [proven(15316090, names=15306197)]

    tags, refusals, _examined = tags_of(rows)

    assert tags == []
    assert len(refusals) == 1
    assert "2 different canonicals" in refusals[0]


def test_a_named_canonical_outside_the_window_withholds_every_tag():
    """Under-tagging is the intended direction: we cannot verify what we cannot
    see, and the tag was written by a rail whose reasoning we are not re-running.
    """
    rows = [proven()] + [husk(15315219 + i) for i in range(3)]

    tags, refusals, examined = tags_of(rows)

    assert tags == []
    assert examined == 1, "the block was examined; it just could not be decided"
    assert refusals == [], "not an ambiguity — an absence"


def test_a_named_canonical_that_is_not_played_today_withholds_every_tag():
    """The tag says another rail proved this pair. This pass still checks that
    the row it names looks like a canonical NOW — scored, settled and anchored.
    """
    for weakened in (
        {"has_final_score": False},
        {"is_fixture_anchored": False},
        {"status": "scheduled"},
    ):
        rows = [canonical(**weakened), proven()] + [husk(15315219)]

        tags, _refusals, _examined = tags_of(rows)

        assert tags == [], f"{weakened} must withhold"


def test_a_second_real_fixture_sharing_the_key_is_refused():
    """Two clubs genuinely meeting twice inside the window is the one shape this
    must never resolve, and it is refused on the ROW rather than on the clock.
    """
    rival = canonical(
        15306300,
        when=KICKOFF - timedelta(days=1),
        away="Utrecht",  # in the copies' own block, unlike the real canonical
    )
    rows = specimen(husks=3) + [rival]

    tags, refusals, _examined = tags_of(rows)

    assert tags == []
    assert len(refusals) == 1
    assert "two real fixtures share this key" in refusals[0]


# ── 3. what a husk must be ───────────────────────────────────────────────────


def test_a_copy_that_has_acquired_a_score_or_an_anchor_is_left_alone():
    for grown_up in ({"has_final_score": True}, {"is_fixture_anchored": True}):
        rows = [canonical(), proven(), husk(15315219, **grown_up)]

        tags, _refusals, _examined = tags_of(rows)

        assert tags == [], f"{grown_up} is no longer an id-less copy"


def test_a_live_copy_is_never_the_row_we_stop_printing():
    rows = [canonical(), proven(), husk(15315219, status="live")]

    tags, _refusals, _examined = tags_of(rows)

    assert tags == []


def test_a_copy_inside_its_own_kickoff_grace_is_left_alone():
    """A real match that has just kicked off reads exactly like a husk for half
    an hour. The same grace, the same expression, as every other pass here.
    """
    inside = husk(15315219, when=NOW - GHOST_KICKOFF_GRACE / 2)
    outside = husk(15315220, when=NOW - GHOST_KICKOFF_GRACE - timedelta(minutes=1))

    tags, _refusals, _examined = tags_of([canonical(), proven(), inside, outside])

    assert [ghost_id for ghost_id, _ in tags] == [15315220]


def test_a_copy_further_than_the_measured_lag_from_the_canonical_is_left_alone():
    """The 3-day bound is the module's measured one and it is applied from the
    CANONICAL's kick-off, in both directions — a copy dated before the played row
    is as much a copy as one dated after (the direction rule is what the proof
    replaces).
    """
    before = husk(15315219, when=KICKOFF - MAX_GHOST_LAG)
    after = husk(15315220, when=KICKOFF + MAX_GHOST_LAG)
    too_early = husk(15315221, when=KICKOFF - MAX_GHOST_LAG - timedelta(hours=1))
    too_late = husk(15315222, when=KICKOFF + MAX_GHOST_LAG + timedelta(hours=1))

    tags, _refusals, _examined = tags_of(
        [canonical(), proven(), before, after, too_early, too_late],
        now=KICKOFF + MAX_GHOST_LAG + timedelta(days=2),
    )

    assert sorted(ghost_id for ghost_id, _ in tags) == [15315219, 15315220]


def test_a_husk_with_markets_is_the_same_row_to_this_pass():
    """Most husks hold nothing; #7549's proven sibling holds 66. The market count
    is evidence for the FOURTH pass and says nothing here, so it must not gate.
    """
    rows = [canonical(), proven(), husk(15315219, market_count=9)]

    tags, _refusals, _examined = tags_of(rows)

    assert [ghost_id for ghost_id, _ in tags] == [15315219]


def test_a_copy_in_a_different_competition_is_a_different_fixture():
    rows = [
        canonical(),
        proven(),
        husk(15315219, sport_key="soccer_netherlands_eerste_divisie"),
    ]

    tags, _refusals, _examined = tags_of(rows)

    assert tags == []


def test_the_pass_is_handed_the_soccer_partition_only():
    """``plan_ghost_tags`` hands the name-based passes ``soccer_rows``, and this
    pass is one of them: its key is our own club names.
    """
    nfl_husk = husk(
        15305030, sport_key="americanfootball_nfl", home="Rams", away="49ers"
    )
    nfl_canonical = canonical(
        14632820, sport_key="americanfootball_nfl", home="Rams", away="49ers"
    )
    # Named against the NFL canonical, so ONLY the partition can withhold it.
    nfl_proven = proven(
        15305029,
        names=14632820,
        sport_key="americanfootball_nfl",
        home="Rams",
        away="49ers",
    )

    plan = plan_ghost_tags([nfl_canonical, nfl_proven, nfl_husk], now=NOW)

    assert plan.proven_tags == 0


# ── 4. it can only ever add ──────────────────────────────────────────────────


def test_a_row_already_carrying_a_tag_is_evidence_and_never_a_subject():
    """So a second run over an unchanged population plans the same tags and the
    sweep writes none of them — the whole point of reading the tag back in.
    """
    first = specimen(husks=3)
    tags, _refusals, _examined = tags_of(first)
    assert len(tags) == 3

    # What the population looks like after the sweep applied those three.
    after = [canonical(), proven()] + [
        proven(ghost_id) for ghost_id, _ in tags
    ]

    second, _refusals, _examined = tags_of(after)

    assert second == [], "nothing left to extend"


def test_a_ghost_an_earlier_pass_already_decided_is_withheld():
    rows = specimen(husks=3)
    already = 15315220

    tags, _refusals, _examined = proven_sibling_pass(
        rows, decided_ghost_ids={already}, now=NOW
    )

    assert already not in {t.ghost_id for t in tags}
    assert len(tags) == 2


def test_the_plan_runs_this_pass_last_so_it_cannot_revise_a_decision():
    """A husk that the FIRST pass can decide (its name matches the canonical's
    exactly) keeps the first pass's tag, and this pass does not restate it.
    """
    exact = husk(15315300, home="Feyenoord", away="FC Utrecht", when=ADVERTISED)

    plan = plan_ghost_tags(specimen(husks=2) + [exact], now=NOW)

    assert (exact.event_id, CANONICAL_ID) in [
        (t.ghost_id, t.canonical_id) for t in plan.tags
    ]
    assert plan.proven_tags == 2, "the first pass's row is not tagged twice"
    assert len({t.ghost_id for t in plan.tags}) == len(plan.tags)


# ── 5. the block classifier's own vocabulary ─────────────────────────────────


def test_the_classifier_speaks_the_modules_three_words():
    rows = [proven(), husk(15315219)]
    by_id = {r.event_id: r for r in [canonical()] + rows}

    outcome, tags, _why = classify_proven_sibling_block(rows, by_id, now=NOW)
    assert outcome == TWIN_FOUND and len(tags) == 1

    outcome, tags, _why = classify_proven_sibling_block(
        [husk(15315219), husk(15315220)], by_id, now=NOW
    )
    assert outcome == NOT_A_TWIN and tags == []

    outcome, tags, why = classify_proven_sibling_block(
        rows + [proven(15316090, names=15306197)], by_id, now=NOW
    )
    assert outcome == REFUSE_AMBIGUOUS and tags == [] and "canonicals" in why


# ── 6. the wiring, which is the half a pure test cannot see ──────────────────


class _Row:
    """One row as ``load_rows`` hands it to ``build_plan``: attributes, not a dict."""

    def __init__(self, row: SoccerRow, tags_text="[]"):
        self.id = row.event_id
        self.sport_key = row.sport_key
        self.home_team_name = row.home_team_name
        self.away_team_name = row.away_team_name
        self.commence_time = row.commence_time
        self.status = row.status
        self.home_score = 5 if row.has_final_score else None
        self.away_score = 0 if row.has_final_score else None
        self.espn_id = None
        self.statpal_fixture_id = "9551358" if row.is_fixture_anchored else None
        self.tags_text = tags_text
        self.kalshi_tickers = None
        self.market_count = row.market_count


def test_the_sweep_reads_the_existing_tag_off_the_row_and_into_the_judgement():
    """The pass is inert unless ``build_plan`` parses ``tags_text``, and a pure
    test of the judgement cannot see that: it is handed the parsed value.

    So this is the call-site test. The proven sibling arrives exactly as the
    population SQL returns it — a serialised JSONB array — and the plan must
    come out the other side with the husks drained.
    """
    from app.tasks.soccer_ghost_twin_sweep import build_plan

    rows = [
        _Row(canonical()),
        _Row(
            husk(PROVEN_ID),
            tags_text=f'["provenance:duplicate-of:{CANONICAL_ID}"]',
        ),
        _Row(husk(15315219)),
        _Row(husk(15315220)),
    ]

    plan = build_plan(rows, now=NOW)

    assert plan.proven_tags == 2
    assert {t.canonical_id for t in plan.tags} == {CANONICAL_ID}


def test_a_mint_storm_does_not_spend_the_five_judgement_passes_ceiling():
    """The ceiling that catches a pairing regression must keep catching one.

    Fifty-six copies of one fixture is a legitimate day here, and raising
    ``MAX_EXPECTED_TAGS`` to fit them would have left a fifty-six-tag regression
    in passes one to five looking normal. The two ceilings are separate, and this
    is the test that fails if they are ever merged back.
    """
    from app.tasks.soccer_ghost_twin_sweep import (
        MAX_EXPECTED_PROVEN_TAGS,
        MAX_EXPECTED_TAGS,
        band_refusal_reason,
    )

    storm = plan_ghost_tags(specimen(husks=MAX_EXPECTED_TAGS + 20), now=NOW)
    assert storm.proven_tags == MAX_EXPECTED_TAGS + 20
    assert len(storm.tags) > MAX_EXPECTED_TAGS
    storm.soccer_rows_considered = 5_000
    storm.ticker_rows_considered = 5_000

    assert band_refusal_reason(storm) is None, "a storm is this pass's ordinary day"

    runaway = plan_ghost_tags(
        specimen(husks=MAX_EXPECTED_PROVEN_TAGS + 1), now=NOW
    )
    runaway.soccer_rows_considered = 5_000
    runaway.ticker_rows_considered = 5_000

    reason = band_refusal_reason(runaway)
    assert reason is not None and "proven-sibling" in reason


def test_the_five_judgement_passes_still_carry_their_own_ceiling():
    """The other direction of the same split: proven tags must not MASK a
    pairing regression by making the subtraction come out small.
    """
    from app.tasks.soccer_ghost_twin_sweep import (
        MAX_EXPECTED_TAGS,
        band_refusal_reason,
    )
    from app.utils.soccer_ghost_twins import GhostPlan, GhostTag

    plan = GhostPlan(
        tags=[GhostTag(i, CANONICAL_ID, "x") for i in range(MAX_EXPECTED_TAGS + 1)],
        soccer_rows_considered=5_000,
        ticker_rows_considered=5_000,
    )

    assert "five judgement passes" in (band_refusal_reason(plan) or "")
