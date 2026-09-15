"""#3813 — the played match whose prices are sitting on a row nobody opens.

THE SHIP THESE GUARD: `14959571` is AS Roma 4-0 Fiorentina, Serie A, ESPN
`401874928`, and it has ZERO linked markets — `_build_game_markets` assembles
its rail only from `FuturesMarket` rows whose `event_id` is in
`folded_event_ids`, and returns the empty body the moment that set is empty. The
prices are not missing: `14968103` is the same two clubs in the same competition
fifty-three hours earlier, `closed`, no score, no fixture id, holding 28
Polymarket markets. A marquee Serie A result with its whole rail on a row nobody
opens (notice 27).

🔴 MEASURED ON THE LINKED COUNT AND NOT ON THE SERVED PAYLOAD, deliberately.
On 2026-09-15 nine of the eleven canonicals served 38-83 markets while holding
zero linked rows, and two consecutive reads returned the identical `created_at`
— so "the page looks fine" is unfalsifiable from outside the cache. Tracing one
served market settles it: `/api/events/14961230/game-markets` serves
`_market_id 58728702`, whose `event_id` **is NULL**. Those bodies are
photographs of an input set that no longer exists. The builder's own input set
answers the question the served payload cannot.

WHY THE THREE PASSES ALREADY IN THE MODULE CANNOT REACH IT, which is the whole
reason a fourth exists. All of them hunt a row still ADVERTISED after its fixture
was played, and `classify_block` writes that down as a direction::

    0 < ghost.commence_time - canonical.commence_time <= MAX_GHOST_LAG

A phantom card is always dated later than the match it copies. A hidden row
holding the prices is dated EARLIER, and measured on production 2026-09-15 over
365 days of soccer, every single one of them is::

    pairs (same competition, narrow key, same orientation, inside
    MAX_GHOST_LAG; one side played/scored/anchored serving ZERO
    markets, the other unscored, unanchored, holding >= 1)        19
      └─ with the ghost dated AFTER the canonical                  0
      └─ needing any name widening to pair                         0

`test_the_card_rule_alone_refuses_the_specimen` is the control for that claim and
is deliberately a test that ALSO passes on master: if it ever goes green-by-
accident — i.e. `classify_block` starts deciding this pair — the fourth pass has
become redundant and someone should delete it rather than maintain two rules.

WHAT REPLACES THE DIRECTION RULE. The market asymmetry itself, which is strictly
MORE evidence than the passes above require rather than less: the played row must
have NOTHING linked to it and its copy must hold something. That is also what
bounds the blast radius — this pass can only fire where the builder has no
markets to assemble, so a wrong tag puts the wrong prices on a rail that would
otherwise be empty and can never displace a correct one. Three tests below are
about that single property
(`test_a_played_row_that_already_serves_markets_is_left_alone`,
`test_a_copy_holding_no_markets_is_not_a_stranded_pair`, and the ambiguity one),
because removing any of them is how this pass would turn into a blunt instrument.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.soccer_ghost_twins import (  # noqa: E402
    GHOST_KICKOFF_GRACE,
    MAX_GHOST_LAG,
    NOT_A_TWIN,
    REFUSE_AMBIGUOUS,
    TWIN_FOUND,
    SoccerRow,
    classify_block,
    classify_stranded_block,
    plan_ghost_tags,
    stranded_market_pass,
)

#: Offsets from a fixed anchor, never literal dates, and the offset is applied
#: before anything is truncated (gotcha #44). The specimen's real kick-off was
#: 2026-08-24 18:45Z with its copy at 2026-08-22 13:00Z; what matters to every
#: assertion here is the 53h gap and its SIGN, not the calendar.
NOW = datetime(2026, 9, 15, 7, 0, tzinfo=timezone.utc)
PLAYED_AT = NOW - timedelta(days=22)
COPY_AT = PLAYED_AT - timedelta(hours=53)

CANON_ID = 14959571
COPY_ID = 14968103


def row(
    event_id,
    home,
    away,
    when,
    *,
    status="scheduled",
    scored=False,
    anchored=False,
    sport_key="soccer_italy_serie_a",
    market_count=0,
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
    )


def played(**kw):
    """14959571 — AS Roma 4-0 Fiorentina, ESPN 401874928, zero linked markets.

    The row a reader actually lands on, and the row whose rail is empty.
    """
    base = dict(
        event_id=CANON_ID,
        home="AS Roma",
        away="Fiorentina",
        when=PLAYED_AT,
        status="closed",
        scored=True,
        anchored=True,
        market_count=0,
    )
    return row(**{**base, **kw})


def copy_holding_prices(**kw):
    """14968103 — the same fixture, 53h earlier, `closed`, holding all 28.

    `closed` is not incidental and is the reason this pass cannot read
    `GHOST_STATUSES`: this row is advertised nowhere, so every rule written for
    the duplicate-card defect is blind to it while it holds the prices.
    """
    base = dict(
        event_id=COPY_ID,
        home="AS Roma",
        away="Fiorentina",
        when=COPY_AT,
        status="closed",
        scored=False,
        anchored=False,
        market_count=28,
    )
    return row(**{**base, **kw})


class TestTheMeasuredSpecimen:
    def test_the_fixture_really_does_carry_the_asymmetry(self):
        """Positive control: the two rows below are not accidentally identical.

        Every assertion in this file rests on one row serving nothing while the
        other holds markets. A fixture that quietly lost that shape would make
        several of these tests pass for the wrong reason.
        """
        assert played().market_count == 0
        assert copy_holding_prices().market_count == 28
        assert copy_holding_prices().commence_time < played().commence_time

    def test_the_specimen_is_decided_and_the_hidden_row_is_the_copy(self):
        outcome, tag, _ = classify_stranded_block(
            [played(), copy_holding_prices()], now=NOW
        )
        assert outcome == TWIN_FOUND
        assert tag.ghost_id == COPY_ID, "the row that stops printing is the id-less one"
        assert tag.canonical_id == CANON_ID

    def test_the_reason_names_the_evidence_a_reader_could_check(self):
        _, tag, _ = classify_stranded_block([played(), copy_holding_prices()], now=NOW)
        assert "28 market(s)" in tag.reason
        assert "serves none" in tag.reason

    @pytest.mark.parametrize(
        "copy_status,expected_reason",
        [
            # As measured. The card rule never even reaches the direction
            # question: `closed` is not in GHOST_STATUSES, so the block holds no
            # ghost at all.
            ("closed", "no ghost/canonical pair in this block"),
            # And with that barrier removed, the direction rule is the second
            # one. Both have to be named, or a reader could conclude the fourth
            # pass exists for only one of them.
            ("scheduled", "no ghost sits within 3d after a played row"),
        ],
    )
    def test_the_card_rule_alone_refuses_the_specimen(
        self, copy_status, expected_reason
    ):
        """The control for this whole file, and it passes on master too.

        `classify_block` is the first three passes' judgement. If it ever starts
        deciding this pair, the fourth pass is redundant and should be deleted
        rather than kept beside it — so this failing is a design signal, not a
        regression.
        """
        outcome, tag, explanation = classify_block(
            [played(), copy_holding_prices(status=copy_status)], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tag is None
        assert explanation == expected_reason


class TestTheDirectionRuleIsTheThingThatChanged:
    @pytest.mark.parametrize(
        "offset,label",
        [
            (-timedelta(hours=53), "before — the measured majority"),
            (timedelta(0), "the same instant — the Angers v Stade Rennais pair"),
            (timedelta(hours=53), "after — what the card rule already covers"),
        ],
    )
    def test_a_copy_pairs_on_either_side_of_its_played_row(self, offset, label):
        outcome, tag, _ = classify_stranded_block(
            [played(), copy_holding_prices(when=PLAYED_AT + offset)], now=NOW
        )
        assert outcome == TWIN_FOUND, label
        assert tag.ghost_id == COPY_ID

    @pytest.mark.parametrize(
        "offset",
        [-MAX_GHOST_LAG - timedelta(hours=1), MAX_GHOST_LAG + timedelta(hours=1)],
    )
    def test_the_window_still_binds_in_both_directions(self, offset):
        """Direction-agnostic is not window-agnostic — `abs(...)`, not no bound.

        A mutant dropping the comparison entirely pairs two clubs' fixtures a
        season apart, and this is the test that catches it.
        """
        outcome, tag, _ = classify_stranded_block(
            [played(), copy_holding_prices(when=PLAYED_AT + offset)], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tag is None


class TestTheMarketAsymmetryIsTheEvidence:
    def test_a_played_row_that_already_serves_markets_is_left_alone(self):
        """Nothing of its is stranded, so there is no defect and no evidence.

        This is the check that bounds the blast radius: with it gone, the pass
        can move prices onto a page that was already serving its own.
        """
        outcome, tag, explanation = classify_stranded_block(
            [played(market_count=7), copy_holding_prices()], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tag is None
        assert "already serves 7 market(s)" in explanation

    def test_a_copy_holding_no_markets_is_not_a_stranded_pair(self):
        """Two bare rows are a duplicate-card question, not this one.

        The other three passes own that case and own it with a direction rule;
        answering it here direction-agnostically is precisely the widening this
        pass must not perform.
        """
        outcome, tag, _ = classify_stranded_block(
            [played(), copy_holding_prices(market_count=0)], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tag is None

    def test_a_row_built_without_a_market_count_can_only_withhold(self):
        """`SoccerRow.market_count` defaults to 0, and that default is load-bearing.

        Every caller and every test written before this pass existed constructs
        rows without it. The default has to be the value that makes a row neither
        half of a stranded pair, or the fourth pass would start deciding cases
        nobody handed it market data for.
        """
        bare = SoccerRow(
            event_id=1,
            sport_key="soccer_italy_serie_a",
            home_team_name="AS Roma",
            away_team_name="Fiorentina",
            commence_time=COPY_AT,
            status="closed",
            has_final_score=False,
            is_fixture_anchored=False,
        )
        assert bare.market_count == 0
        outcome, tag, _ = classify_stranded_block([played(), bare], now=NOW)
        assert outcome == NOT_A_TWIN
        assert tag is None


class TestTheStatusGate:
    @pytest.mark.parametrize("status", ["closed", "completed", "scheduled", "suspended"])
    def test_a_stranded_market_is_stranded_at_every_status(self, status):
        """`GHOST_STATUSES` is not consulted here, and four production pairs say why.

        Roma v Fiorentina, Bologna v Lazio, Torino v AC Milan, Atalanta v
        Sassuolo and Freiburg v Werder Bremen strand 113 markets between them on
        `closed` rows — advertised nowhere, invisible to every rule written for
        the card defect, still holding the prices.
        """
        outcome, tag, _ = classify_stranded_block(
            [played(), copy_holding_prices(status=status)], now=NOW
        )
        assert outcome == TWIN_FOUND, status
        assert tag.ghost_id == COPY_ID

    def test_a_live_row_is_never_called_a_copy(self):
        """The one exclusion, and the one mistake here that reaches a reader.

        A match in progress is unscored and may not be anchored yet. Labelling it
        a duplicate hides a live game mid-match.
        """
        outcome, tag, _ = classify_stranded_block(
            [played(), copy_holding_prices(status="live")], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tag is None

    def test_the_kickoff_grace_applies_here_too(self):
        """Same predicate, same half hour, same reason as every other pass."""
        just_kicked_off = copy_holding_prices(
            when=NOW - GHOST_KICKOFF_GRACE + timedelta(minutes=1)
        )
        outcome, tag, _ = classify_stranded_block(
            [played(when=NOW - timedelta(hours=2)), just_kicked_off], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tag is None


class TestAmbiguityIsCountedOverEveryPlayedRow:
    def test_two_market_holding_copies_are_refused(self):
        """The Real Sociedad v Espanyol shape — three copies, one played row."""
        outcome, tag, explanation = classify_stranded_block(
            [
                played(),
                copy_holding_prices(),
                copy_holding_prices(event_id=99, when=COPY_AT + timedelta(hours=1)),
            ],
            now=NOW,
        )
        assert outcome == REFUSE_AMBIGUOUS
        assert tag is None
        assert "not decidable" in explanation

    def test_a_second_played_row_refuses_even_though_it_serves_markets(self):
        """🔴 The subtle one, and the reason the ambiguity count ignores markets.

        Count only the ZERO-market played rows and this block looks decidable:
        one bare canonical, one copy. But two played, scored, fixture-anchored
        rows for these two clubs inside three days is "they played twice", and
        that is the shape that must never resolve — whichever of them happens to
        serve markets today.
        """
        outcome, tag, explanation = classify_stranded_block(
            [
                played(),
                played(event_id=77, when=PLAYED_AT + timedelta(hours=6), market_count=5),
                copy_holding_prices(),
            ],
            now=NOW,
        )
        assert outcome == REFUSE_AMBIGUOUS
        assert tag is None
        assert "2 played row(s)" in explanation


class TestItCannotUndoTheThreePassesAboveIt:
    def test_a_copy_already_decided_by_an_earlier_pass_is_withheld(self):
        tags, _, _ = stranded_market_pass(
            [played(), copy_holding_prices()],
            decided_ghost_ids={COPY_ID},
            now=NOW,
        )
        assert tags == []

    def test_a_played_row_can_never_be_this_passs_copy(self):
        """The two roles are disjoint by predicate, not by ordering.

        An earlier pass can only tag a row that is unscored and unanchored; this
        pass can only call a row canonical when it is scored AND anchored. So no
        row it protects is already someone else's ghost, whatever order the
        passes run in.
        """
        tags, _, _ = stranded_market_pass(
            [played(), played(event_id=77, when=COPY_AT, market_count=46)],
            decided_ghost_ids=set(),
            now=NOW,
        )
        assert tags == []


class TestThePlanReportsTheFourthPassOnItsOwnNumbers:
    def test_the_specimen_reaches_the_plan_and_is_counted_separately(self):
        plan = plan_ghost_tags([played(), copy_holding_prices()], now=NOW)
        assert [t.ghost_id for t in plan.tags] == [COPY_ID]
        assert plan.stranded_tags == 1
        assert plan.stranded_blocks_examined == 1
        assert (
            plan.residual_tags == 0 and plan.ticker_tags == 0
        ), "the earlier passes contribute nothing here, by construction"

    def test_orientation_is_still_load_bearing(self):
        """A two-legged tie's second leg can no more pair here than anywhere else."""
        plan = plan_ghost_tags(
            [played(), copy_holding_prices(home="Fiorentina", away="AS Roma")],
            now=NOW,
        )
        assert plan.tags == []

    def test_two_competitions_carrying_the_same_clubs_do_not_pair(self):
        """The Köln women/men shape: the sport key stays in the key here too."""
        plan = plan_ghost_tags(
            [
                played(),
                copy_holding_prices(sport_key="soccer_italy_serie_b"),
            ],
            now=NOW,
        )
        assert plan.tags == []
