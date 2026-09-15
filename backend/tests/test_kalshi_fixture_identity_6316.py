"""#6316 — the finished match still running a countdown, and the venue id that ends it.

THE SHIP THESE GUARD. `/events/15310639` is Liverpool FC v Fulham FC, `scheduled`,
kickoff stored at `2026-09-12 00:00:00+00`, running a live "Next update" countdown
and printing "No result reported" three days after the match was played.
`/events/15297677` is the same fixture, `completed`, 0-0, with a chart and a
settled rail. The ghost is direct-link reachable only, so no listing rule reaches
it, and the two rows are not a guess — they carry the SAME Kalshi event ticker::

    15297677  KXEPLGAME-26SEP12LFCFUL, KXEPLSPREAD-26SEP12LFCFUL, …  (15 markets)
    15310639  KXEPLSCORE-26SEP12LFCFUL, KXEPL1HSCORE-26SEP12LFCFUL,
              KXEPLFTTS-26SEP12LFCFUL                                 (3 markets)

`26SEP12LFCFUL` is the venue's own identifier for that fixture. That makes this
an ID-ANCHORED correspondence — ruling 048 arm A, the shared provider id gotcha
#32 requires before one row may stand in for another — and it is the arm none of
the four passes above `fixture_ticker_pass` has. They earn the right to proceed
without an id by spending a clock (passes 1-3) or a market asymmetry (pass 4) as
evidence. This pass has the id, so it spends neither, and the three tests named
`test_the_*_rule_refuses_this_specimen` below are the controls proving those four
genuinely cannot reach the population: each one ALSO passes on master.

WHY NAME WIDENING IS NOT THE ANSWER AND IS NOT ATTEMPTED. Three of the six proven
pairs do not share even the LOOSE name key — `RC Lens` against `Racing Club De
Lens`, `Brighton & Hove Albion` against `Brighton and Hove Albion`, `Deportivo`
against `RC Deportivo De La Coruña`. Nothing short of a fuzzy matcher reaches them
by name, and the last widening-on-a-hunch in this module was a net loss.

WHAT IS DELIBERATELY NOT REACHED, so a later reader does not mistake the scope.
Of #6316's six proven duplicates this pass takes five. The sixth — Getafe v
Deportivo, `15310513` against `15311881` — has a canonical carrying NO Kalshi
markets at all, so there is no shared id and pairing it would be absorption on
names and a date alone. `test_the_sixth_proven_pair_has_no_shared_id_and_is_left`
pins that refusal so nobody "fixes" it into a name match. #6316's wider population
is 477 rows across six sports, two thirds of them tennis; this pass is soccer-only
and id-only and says so.

PRECISION, MEASURED RATHER THAN ARGUED (production 2026-09-15, the sweep's own
-45d/+5d window, whole population, no sampling)::

    rows carrying an event key                                 1,636
      └─ carrying exactly ONE, so the pass reads them          1,617
    distinct event keys                                        1,522
      └─ shared by 2+ rows                                        76
           ├─ one played canonical + >=1 ghost                    13  ← acts
           ├─ two played canonicals                                1  ← refused
           └─ no canonical, or no ghost                           62  ← silent
    ghost rows tagged                                             16

Every shared-key block holding a canonical was read BY NAME — 15 of them, 33 rows
— and every one is genuinely one fixture. Zero collisions. The pure pass replayed
over the real 1,664-row population returns exactly those numbers: 76 blocks
examined, 16 tags, 0 refusals.

🔴 THE AMBIGUITY REFUSAL HAS NO LIVE SPECIMEN TODAY AND THAT IS WHY IT IS TESTED
HARDEST. The one production block holding two played canonicals holds no ghost, so
`classify_fixture_ticker_block` returns NOT_A_TWIN before the refusal is reached
and the branch never fires in the dry run. A guard with no natural specimen is
exactly the one that rots (gotcha #53's family), so it is manufactured here in
three shapes rather than inferred from a zero.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.soccer_ghost_twins import (  # noqa: E402
    GHOST_KICKOFF_GRACE,
    NOT_A_TWIN,
    REFUSE_AMBIGUOUS,
    TWIN_FOUND,
    SoccerRow,
    classify_block,
    classify_fixture_ticker_block,
    classify_stranded_block,
    competition_from_tickers,
    fixture_ticker_pass,
    kalshi_event_key,
    loose_block_key,
    plan_ghost_tags,
)

#: Offsets from a fixed anchor, applied BEFORE anything is truncated (gotcha #44).
#: The specimen's ghost is stored at midnight UTC and its canonical kicked off
#: fourteen hours later the same day; what every assertion here needs is that gap
#: and its SIGN — the ghost is EARLIER — never the calendar.
NOW = datetime(2026, 9, 15, 7, 0, tzinfo=timezone.utc)
GHOST_AT = NOW - timedelta(days=3)
CANON_AT = GHOST_AT + timedelta(hours=14)

GHOST_ID = 15310639
CANON_ID = 15297677
TICKET = "26SEP12LFCFUL"

#: The ghost's three real tickers. Every one has a series prefix that is NOT
#: registered in `KALSHI_TICKER_TO_SPORT_KEY`, which is exactly why `ticker_pass`
#: is blind to these rows — see `test_the_competition_map_is_blind_to_the_ghost`.
GHOST_TICKERS = [
    "KXEPLSCORE-26SEP12LFCFUL",
    "KXEPL1HSCORE-26SEP12LFCFUL",
    "KXEPLFTTS-26SEP12LFCFUL",
]
CANON_TICKERS = [
    "KXEPLGAME-26SEP12LFCFUL",
    "KXEPLSPREAD-26SEP12LFCFUL",
    "KXEPLTOTAL-26SEP12LFCFUL",
]


def row(
    event_id,
    home,
    away,
    when,
    *,
    status="scheduled",
    scored=False,
    anchored=False,
    sport_key="soccer_epl",
    market_count=0,
    ticker_event_key=TICKET,
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
        market_count=market_count,
        ticker_event_key=ticker_event_key,
    )


def ghost(**kw):
    """15310639 — Liverpool FC v Fulham FC, scheduled, midnight kickoff, 3 markets."""
    base = dict(
        event_id=GHOST_ID,
        home="Liverpool FC",
        away="Fulham FC",
        when=GHOST_AT,
        status="scheduled",
        scored=False,
        anchored=False,
        market_count=3,
    )
    return row(**{**base, **kw})


def canonical(**kw):
    """15297677 — Liverpool 0-0 Fulham, completed, ESPN-anchored, 15 markets."""
    base = dict(
        event_id=CANON_ID,
        home="Liverpool",
        away="Fulham",
        when=CANON_AT,
        status="completed",
        scored=True,
        anchored=True,
        market_count=15,
    )
    return row(**{**base, **kw})


class TestTheKeyIsTheVenuesOwnFixtureId:
    def test_the_specimens_three_unregistered_tickers_still_name_one_fixture(self):
        assert kalshi_event_key(GHOST_TICKERS) == TICKET
        assert kalshi_event_key(CANON_TICKERS) == TICKET

    def test_the_competition_map_is_blind_to_the_ghost(self):
        """The control for "this is not `ticker_pass` again".

        Every ghost ticker fails `is_kalshi_game_level_ticker`, so the pass that
        reads a COMPETITION off a ticker gets `None` and cannot block these rows
        at all. Passes on master too — if it ever goes red, the prefix maps have
        grown and the fifth pass may be redundant for this row.
        """
        assert competition_from_tickers(GHOST_TICKERS) is None
        assert kalshi_event_key(GHOST_TICKERS) is not None

    def test_two_fixtures_on_one_row_is_a_refusal_not_a_pick(self):
        """19 production rows are in this state. None-on-disagreement, as
        `competition_from_tickers` does, because a row holding two venues'
        fixtures reports a link defect and picking one builds on top of it."""
        assert (
            kalshi_event_key(["KXEPLGAME-26SEP12LFCFUL", "KXEPLGAME-26SEP13LFCFUL"])
            is None
        )
        assert (
            kalshi_event_key(["KXMLSGAME-26APR11SDMIN", "KXMLSGAME-26AUG01MINSD"])
            is None
        )

    def test_a_market_level_ticker_contributes_its_event_field_not_its_outcome(self):
        assert (
            kalshi_event_key(
                ["KXEPLGAME-26SEP12LFCFUL-LFC", "KXEPLGAME-26SEP12LFCFUL-FUL"]
            )
            == TICKET
        )

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXEPLGAME-26FOO12LFCFUL",  # three letters that are not a month
            "KXEPLGAME-LFCFUL",  # team codes with no date at all
            "KXEPLGAME-26SEP12",  # a date with no teams
            "KXEPLGAME-26SEP123LFCFUL",  # three-digit day: not the grammar
            "KXEPLGAME",  # a series ticker, no second field
            "KXEPLGAME-",  # a trailing dash
        ],
    )
    def test_a_second_field_that_is_not_a_dated_fixture_names_nothing(self, ticker):
        """The month allowlist is load-bearing, not decoration: the whole claim
        of this key is that it names ONE fixture on ONE date, and three arbitrary
        letters name neither."""
        assert kalshi_event_key([ticker]) is None

    @pytest.mark.parametrize("empty", [[], [None], [""], ["", None]])
    def test_no_tickers_names_no_fixture(self, empty):
        assert kalshi_event_key(empty) is None


class TestTheFourPassesAboveGenuinelyCannotReachIt:
    """Controls. Each ALSO passes on master; a red one means a pass above has
    started deciding this population and the fifth may be redundant."""

    def test_the_direction_rule_refuses_this_specimen(self):
        outcome, tag, _ = classify_block([ghost(), canonical()], now=NOW)
        assert outcome == NOT_A_TWIN
        assert tag is None

    def test_the_market_asymmetry_rule_refuses_this_specimen(self):
        outcome, tag, explanation = classify_stranded_block(
            [ghost(), canonical()], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tag is None
        assert "already serves 15 market(s)" in explanation

    def test_the_loose_name_key_does_not_even_pair_three_of_the_six(self):
        for home_a, away_a, home_b, away_b in (
            ("Le Mans FC", "Racing Club De Lens", "Le Mans FC", "RC Lens"),
            (
                "Coventry City",
                "Brighton & Hove Albion",
                "Coventry City",
                "Brighton and Hove Albion",
            ),
            (
                "Getafe CF",
                "RC Deportivo De La Coruña",
                "Getafe",
                "Deportivo",
            ),
        ):
            assert loose_block_key(home_a, away_a) != loose_block_key(home_b, away_b)


class TestOneBlockIsDecidedByTheAnchorNotByACount:
    def test_the_specimen_pairs_on_the_shared_ticker_alone(self):
        outcome, tags, why = classify_fixture_ticker_block(
            [ghost(), canonical()], now=NOW
        )
        assert outcome == TWIN_FOUND
        assert why == "fixture ticker"
        assert [(t.ghost_id, t.canonical_id) for t in tags] == [(GHOST_ID, CANON_ID)]
        assert TICKET in tags[0].reason

    def test_two_ghosts_on_one_ticker_both_tag_where_every_other_pass_refuses(self):
        """Three of the thirteen production blocks are this shape (Sevilla v
        Atlético, Chelsea v Brighton, Sunderland v Fulham) and all six ghosts are
        real. `classify_block` refuses two candidates because names and a clock
        cannot say which is the copy; here the anchor says it."""
        second = ghost(event_id=GHOST_ID + 1, home="Liverpool", away="Fulham")
        outcome, tags, _ = classify_fixture_ticker_block(
            [ghost(), second, canonical()], now=NOW
        )
        assert outcome == TWIN_FOUND
        assert {t.ghost_id for t in tags} == {GHOST_ID, GHOST_ID + 1}
        assert {t.canonical_id for t in tags} == {CANON_ID}

    def test_two_played_anchored_rows_on_one_ticker_are_refused(self):
        outcome, tags, explanation = classify_fixture_ticker_block(
            [ghost(), canonical(), canonical(event_id=CANON_ID + 1)], now=NOW
        )
        assert outcome == REFUSE_AMBIGUOUS
        assert tags == []
        assert "2 played" in explanation

    def test_a_block_with_no_played_row_decides_nothing(self):
        outcome, tags, _ = classify_fixture_ticker_block(
            [ghost(), ghost(event_id=GHOST_ID + 1)], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tags == []

    def test_a_block_with_no_ghost_decides_nothing(self):
        outcome, tags, _ = classify_fixture_ticker_block(
            [canonical(), canonical(event_id=CANON_ID + 1)], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tags == []

    def test_a_row_at_its_own_kickoff_is_not_relabelled(self):
        """The grace applies here for the reason it applies everywhere else — a
        reader may be watching that row right now — and that reason does not
        depend on what proved the pairing."""
        at_kickoff = ghost(when=NOW - GHOST_KICKOFF_GRACE / 2)
        outcome, tags, _ = classify_fixture_ticker_block(
            [at_kickoff, canonical()], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tags == []

    def test_a_scored_row_with_no_authority_id_is_not_a_canonical(self):
        """🔴 THE GUARD RULING 048 IS ACTUALLY ABOUT, and the one a reader of this
        pass would most plausibly weaken: "played" here means scored AND
        fixture-anchored, never scored alone.

        A shared Kalshi ticker says two rows are one fixture. It does NOT say
        which of them our own graph should keep — that is what the independent
        authority id answers. Drop the anchor and a scored, id-less row becomes a
        canonical, which is choosing between two id-less rows: the exact call
        gotcha #32 forbids. Caught by mutation, not by reading.
        """
        scored_but_idless = ghost(
            event_id=GHOST_ID + 5, status="completed", scored=True, anchored=False
        )
        outcome, tags, _ = classify_fixture_ticker_block(
            [ghost(), scored_but_idless], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tags == []

    @pytest.mark.parametrize(
        "weakened",
        [
            {"scored": False},  # anchored, but the match has not been played
            {"status": "scheduled"},  # scored and anchored, still advertised
        ],
        ids=["unscored", "not-settled"],
    )
    def test_the_canonical_must_be_played_and_not_merely_anchored(self, weakened):
        """All three coordinates of `row_is_a_played_canonical` are load-bearing
        here, and the reason is scope rather than principle.

        Pairing an upcoming ESPN-anchored fixture with a Kalshi copy that shares
        its ticker may well be right — but it is a DIFFERENT population from the
        one measured for this pass (76 shared keys read on played fixtures), and
        nobody has read those blocks by name. Widening to unscored rows is a new
        measurement, not a free parameter, exactly as `MAX_GHOST_LAG` is.
        """
        outcome, tags, _ = classify_fixture_ticker_block(
            [ghost(), canonical(**weakened)], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tags == []

    def test_a_scored_idless_row_beside_a_real_canonical_does_not_make_two(self):
        """The other half of the same guard: the id-less row must not be counted
        into the AMBIGUITY, or a block that is perfectly decidable starts refusing
        itself.

        Since #6358 it is counted as a second GHOST — see
        :class:`TestAPlayedCopyIsStillACopy` for why that is the ship rather than
        a relaxation — and the two halves of this guard are independent: what must
        never change is that an unanchored row cannot make the block ambiguous.
        """
        scored_but_idless = ghost(
            event_id=GHOST_ID + 5, status="completed", scored=True, anchored=False
        )
        outcome, tags, _ = classify_fixture_ticker_block(
            [ghost(), scored_but_idless, canonical()], now=NOW
        )
        assert outcome == TWIN_FOUND
        assert {(t.ghost_id, t.canonical_id) for t in tags} == {
            (GHOST_ID, CANON_ID),
            (GHOST_ID + 5, CANON_ID),
        }

    def test_an_anchored_row_is_never_the_ghost_half(self):
        """The half of the old `scored or anchored` guard that #6358 does NOT
        touch, and the one carrying the weight.

        A row an authority names independently of us is never a copy, whatever
        ticker it shares — that is what makes the canonical the canonical. The
        `scored` half was the other arm and it was dropped deliberately: six of
        the seven American football repairs are `completed` copies carrying their
        fixture's real final score (26SEP06LOUMISS reads 41-38 on both rows).
        """
        outcome, tags, _ = classify_fixture_ticker_block(
            [ghost(anchored=True), canonical()], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tags == []


class TestThePassOverAPopulation:
    def test_the_specimen_is_tagged_and_the_counter_counts_the_block(self):
        tags, refusals, examined = fixture_ticker_pass(
            [ghost(), canonical()], decided_ghost_ids=set(), now=NOW
        )
        assert examined == 1
        assert refusals == []
        assert [(t.ghost_id, t.canonical_id) for t in tags] == [(GHOST_ID, CANON_ID)]

    def test_a_ghost_an_earlier_pass_decided_is_withheld(self):
        tags, _, examined = fixture_ticker_pass(
            [ghost(), canonical()], decided_ghost_ids={GHOST_ID}, now=NOW
        )
        assert tags == []
        assert examined == 0

    def test_rows_naming_no_fixture_are_never_blocked_together(self):
        """The one that matters if `if r.ticker_event_key` ever becomes
        `is not None`: every keyless row would land in one giant block."""
        keyless = [
            ghost(event_id=9001, ticker_event_key=None),
            canonical(event_id=9002, ticker_event_key=None),
            ghost(event_id=9003, ticker_event_key=""),
            canonical(event_id=9004, ticker_event_key=""),
        ]
        tags, refusals, examined = fixture_ticker_pass(
            keyless, decided_ghost_ids=set(), now=NOW
        )
        assert (tags, refusals, examined) == ([], [], 0)

    def test_a_lone_row_on_a_ticker_is_not_examined(self):
        _, _, examined = fixture_ticker_pass(
            [ghost()], decided_ghost_ids=set(), now=NOW
        )
        assert examined == 0

    def test_two_different_tickers_never_share_a_block(self):
        other = canonical(event_id=CANON_ID + 7, ticker_event_key="26SEP12SUNARS")
        tags, _, examined = fixture_ticker_pass(
            [ghost(), other], decided_ghost_ids=set(), now=NOW
        )
        assert (tags, examined) == ([], 0)

    def test_the_two_halves_may_wear_different_sport_keys(self):
        """`15311681` (soccer_other) against `15299943` (soccer_brazil_campeonato),
        Grêmio v Vasco — a real production pair. The key holds no competition, so
        there is nothing to fold and nothing to refuse. Blocking on the sport key
        as well would lose it."""
        unclassified = ghost(event_id=15311681, sport_key="soccer_other")
        named = canonical(event_id=15299943, sport_key="soccer_brazil_campeonato")
        tags, refusals, _ = fixture_ticker_pass(
            [unclassified, named], decided_ghost_ids=set(), now=NOW
        )
        assert refusals == []
        assert [(t.ghost_id, t.canonical_id) for t in tags] == [(15311681, 15299943)]

    def test_the_refusal_names_the_ticker_so_an_operator_can_look_it_up(self):
        _, refusals, _ = fixture_ticker_pass(
            [ghost(), canonical(), canonical(event_id=CANON_ID + 1)],
            decided_ghost_ids=set(),
            now=NOW,
        )
        assert len(refusals) == 1
        assert refusals[0].startswith(f"{TICKET} (fixture ticker):")


class TestItRunsLastAndOnlyAdds:
    def test_the_plan_reports_the_fifth_pass_separately(self):
        plan = plan_ghost_tags([ghost(), canonical()], now=NOW)
        assert plan.fixture_blocks_examined == 1
        assert plan.fixture_tags == 1
        assert [(t.ghost_id, t.canonical_id) for t in plan.tags] == [
            (GHOST_ID, CANON_ID)
        ]
        # Every other pass's counters are untouched by it.
        assert (plan.residual_tags, plan.ticker_tags, plan.stranded_tags) == (0, 0, 0)

    def test_it_cannot_revise_a_decision_an_earlier_pass_made(self):
        """A pair the NARROW key already decides — the ghost dated after the
        canonical, same names — must be tagged once, by pass one, and the fifth
        pass must leave it alone even though both rows share a ticker."""
        early = canonical(when=NOW - timedelta(days=2), market_count=0)
        late = ghost(
            home="Liverpool",
            away="Fulham",
            when=NOW - timedelta(days=1),
            market_count=0,
        )
        plan = plan_ghost_tags([early, late], now=NOW)
        assert [(t.ghost_id, t.canonical_id) for t in plan.tags] == [
            (GHOST_ID, CANON_ID)
        ]
        assert plan.fixture_tags == 0

    def test_a_row_the_pass_calls_canonical_is_never_an_earlier_passes_ghost(self):
        """Structural, not incidental: every earlier pass can only tag an
        unanchored, unscored row, and this pass's canonical is both."""
        plan = plan_ghost_tags([ghost(), canonical()], now=NOW)
        assert CANON_ID not in {t.ghost_id for t in plan.tags}


class TestTheMeasuredScope:
    def test_the_sixth_proven_pair_has_no_shared_id_and_is_left(self):
        """Getafe v Deportivo: the canonical carries no Kalshi markets at all, so
        there is no shared id. Pairing it would be absorption on names and a date
        alone, which is the thing ruling 048 forbids — this stays refused."""
        getafe_ghost = ghost(
            event_id=15310513,
            home="Getafe CF",
            away="RC Deportivo De La Coruña",
            sport_key="soccer_spain_la_liga",
            ticker_event_key="26SEP13GETDEP",
        )
        getafe_canonical = canonical(
            event_id=15311881,
            home="Getafe",
            away="Deportivo",
            sport_key="soccer_spain_la_liga",
            market_count=0,
            ticker_event_key=kalshi_event_key([]),
        )
        tags, refusals, examined = fixture_ticker_pass(
            [getafe_ghost, getafe_canonical], decided_ghost_ids=set(), now=NOW
        )
        assert (tags, refusals, examined) == ([], [], 0)

    @pytest.mark.parametrize(
        "ghost_when",
        [
            CANON_AT - timedelta(hours=14),  # #6316's shape: the copy is EARLIER
            CANON_AT + timedelta(hours=14),  # a card ghost: the copy is LATER
            CANON_AT + timedelta(days=40),  # far outside MAX_GHOST_LAG
        ],
        ids=["earlier", "later", "beyond-max-lag"],
    )
    def test_the_pass_never_reads_the_clock_for_ordering_or_distance(self, ghost_when):
        """Direction-agnostic AND lag-agnostic, in both directions, on purpose.

        The other four passes spend a clock as evidence and so must bound it.
        This one spends the venue's id, which already carries the fixture's date
        inside it — so re-deriving a lag from our two `commence_time` values would
        be a second, weaker matcher running underneath a stronger one, and would
        quietly refuse exactly the rows whose stored kickoff is the wrong kind of
        value in the first place. #6316's whole population is rows whose kickoff
        column holds a DATE.
        """
        outcome, tags, _ = classify_fixture_ticker_block(
            [ghost(when=ghost_when), canonical()], now=NOW
        )
        assert outcome == TWIN_FOUND
        assert [(t.ghost_id, t.canonical_id) for t in tags] == [(GHOST_ID, CANON_ID)]
