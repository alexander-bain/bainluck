"""#6277 — a soccer card's away slot stops carrying the whole draw.

THE DEFECT. A soccer game winner is a THREE-WAY question and every writer of a
``win_prob_snapshots`` row stored a home/away PAIR, filling the second slot with
``1 - home``. That is not the away side's price — it is ``P(not home)``, the
opposition price PLUS the entire draw. Measured over four days of completed
fixtures carrying a Kalshi ``Tie`` member: the complement was exact on **230 of
230** snapshots, and of the 45 whose three venue prices were all present **21
printed the wrong favourite**, because the served favourite is decided by
``home > away`` and every home favourite priced under 50% — the ordinary case in
soccer — lost that comparison to its own leftover mass. The photographed card
(event 15298124, Villarreal 1-2 Real Betis) called Real Betis a 51% pre-match
favourite off a board that priced them at 24.5%, one line above a ``Recent
upset`` chip that was telling the truth.

🔴 **WHY HALF THIS FILE IS ABOUT THE SERVE PATH.** Fixing the writers alone is
COMPLETELY INERT. ``prematch_reading._pair`` rebuilds a non-complementary pair
as ``1 - home`` at serve time, so with the venue's true prices in the row it
returned .495/.505 — the same fabricated number, and the card would not have
moved by a pixel. That was measured by calling it before a writer was touched.
So the writer guards below are necessary and not sufficient, and
``TestTheCardTheReaderActuallySees`` is the one that would catch a future change
that quietly restores the complement at either end.

Both directions are asserted throughout, which is the issue's own requirement:
**a three-way question never prints a fabricated complement, and a two-way
question still prints its pair.**
"""

from decimal import Decimal

import pytest

from app.tasks.prediction_market_matching import _second_slot
from app.utils.graded_card import duel_percents_by_side
from app.utils.live_blend import MarketOutcomes, compute_source_home_probability
from app.utils.prediction_market_matching import find_three_way_partition
from app.utils.prematch_reading import (
    PREMATCH_PRIOR_SQL,
    _pair,
    prematch_row_to_reading,
    resolve_prematch_reading,
)


# ── The photographed board, `KXLALIGAGAME-26SEP13VILRBB` ─────────────────────
# Read from production 2026-09-15, `futures_outcomes.opening_probability`.
SPECIMEN_TICKER = "KXLALIGAGAME-26SEP13VILRBB"
SPECIMEN_HOME = "Villarreal"
SPECIMEN_AWAY = "Real Betis"
K_HOME, K_AWAY, K_TIE = 0.505, 0.245, 0.240

#: The last pre-kickoff snapshot's home price for the same event — minutes to
#: days off the open, which is why it is .495 and not .505. Used wherever the
#: test is about what the CARD printed rather than about what the board opened.
SNAP_HOME = 0.4950


class _Outcome:
    def __init__(self, name, prob, rank=None):
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.rank = rank


class _Market:
    def __init__(self, id, source="kalshi", external_id=None, name=""):
        self.id = id
        self.source = source
        self.external_id = external_id
        self.name = name


def _group(outcomes, id=1, ticker=SPECIMEN_TICKER, name="Villarreal vs Real Betis"):
    return [
        MarketOutcomes(
            market=_Market(id, "kalshi", ticker, name), outcomes=list(outcomes)
        )
    ]


def _three_way():
    return [
        _Outcome(SPECIMEN_HOME, K_HOME, 1),
        _Outcome(SPECIMEN_AWAY, K_AWAY, 2),
        _Outcome("Tie", K_TIE, 3),
    ]


def _two_way():
    """A genuine two-way board — the case that must not move at all."""
    return [_Outcome("Boston Celtics", 0.62, 1), _Outcome("Golden State Warriors", 0.38, 2)]


class _Reading:
    """A BlendReading's shape, for the writers' shared second-slot helper."""

    def __init__(self, home, away=None, draw=None):
        self.home_probability = home
        self.away_probability = away
        self.draw_probability = draw


class TestThePartitionIsProvenNotNamed:
    """`find_three_way_partition` — the resolver the whole ship rests on."""

    def test_the_photographed_board_resolves_both_other_members(self):
        outcomes = _three_way()
        found = find_three_way_partition(
            outcomes, outcomes[0], SPECIMEN_HOME, SPECIMEN_AWAY
        )
        assert found is not None
        away, draw = found
        assert (away.name, float(away.current_probability)) == (SPECIMEN_AWAY, K_AWAY)
        assert (draw.name, float(draw.current_probability)) == ("Tie", K_TIE)

    def test_a_two_way_board_has_no_partition(self):
        """The other half of the rule: nothing changes for a two-sided game."""
        outcomes = _two_way()
        assert find_three_way_partition(
            outcomes, outcomes[0], "Boston Celtics", "Golden State Warriors"
        ) is None

    def test_the_draw_is_recognised_by_ARITHMETIC_not_by_its_spelling(self):
        """A venue that writes `Empate` is priced correctly all the same.

        The deliberate design choice, and the reason there is no fourth copy of
        the draw vocabulary in this repo. If someone replaces the coherence test
        with a word list, this is the test that dies.
        """
        outcomes = [
            _Outcome(SPECIMEN_HOME, K_HOME, 1),
            _Outcome(SPECIMEN_AWAY, K_AWAY, 2),
            _Outcome("Empate", K_TIE, 3),
        ]
        found = find_three_way_partition(
            outcomes, outcomes[0], SPECIMEN_HOME, SPECIMEN_AWAY
        )
        assert found is not None and found[1].name == "Empate"

    def test_three_numbers_that_are_not_a_partition_are_refused(self):
        """The coherence band is load-bearing, not decoration.

        A game winner beside an unrelated third price sums nowhere near one, and
        calling that a partition would publish a stranger's number as the draw.
        """
        outcomes = [
            _Outcome(SPECIMEN_HOME, K_HOME, 1),
            _Outcome(SPECIMEN_AWAY, K_AWAY, 2),
            _Outcome("Both teams to score", 0.625, 3),
        ]
        assert find_three_way_partition(
            outcomes, outcomes[0], SPECIMEN_HOME, SPECIMEN_AWAY
        ) is None

    def test_a_settled_member_is_refused_like_the_moneyline_refuses_one(self):
        """0 and 1 are the result, not the forecast — the same rule one rung up.

        The specimen's own board reads 0/1/0 today. A partition built out of
        settled prices would describe what happened and be published as a
        pre-match reading.
        """
        outcomes = [
            _Outcome(SPECIMEN_HOME, 0.0, 1),
            _Outcome(SPECIMEN_AWAY, 1.0, 2),
            _Outcome("Tie", 0.0, 3),
        ]
        # The anchor is the board's OWN settled home row, not a stand-in. Handing
        # in a different object made this pass on the anchor guard instead of the
        # 0/1 one — a mutation that deleted the endpoint refusal survived it, and
        # the fixture was answering correctly for the wrong reason. A settled
        # board sums to exactly 1.0, so nothing else here would have stopped it.
        assert find_three_way_partition(
            outcomes, outcomes[0], SPECIMEN_HOME, SPECIMEN_AWAY
        ) is None

    def test_the_anchor_must_be_the_home_member_this_resolver_found(self):
        """The orientation guard, and the reason `home_outcome` is a parameter.

        `find_moneyline_outcome` has three routes to a number that never matched
        the home team by name, and each already reports a COMPLEMENT as the home
        probability. Pairing a real away price with one of those puts a true
        number on the wrong club — the same defect with the sides exchanged.
        """
        outcomes = _three_way()
        # The away row handed in as the anchor: refused, not silently re-oriented.
        assert find_three_way_partition(
            outcomes, outcomes[1], SPECIMEN_HOME, SPECIMEN_AWAY
        ) is None
        assert find_three_way_partition(
            outcomes, None, SPECIMEN_HOME, SPECIMEN_AWAY
        ) is None
        # And a row from some other market, which is neither member.
        assert find_three_way_partition(
            outcomes, _Outcome(SPECIMEN_HOME, K_HOME), SPECIMEN_HOME, SPECIMEN_AWAY
        ) is None

    def test_two_rows_matching_one_side_is_not_a_partition(self):
        """Kalshi's per-team pair and an ambiguous name land here. Neither is
        a three-way board, and neither can be oriented into one.

        The prices are chosen so the COUNT is the only thing that can refuse
        this: the three members the resolver would pick sum to exactly 1.00 and
        sail through the coherence band, and the anchor is the first home row.
        With a fixture that missed the band, relaxing the count guard to `< 1`
        survived — the test passed because of a rule it was not testing.
        """
        outcomes = [
            _Outcome(SPECIMEN_HOME, 0.45, 1),
            _Outcome("Villarreal B", 0.05, 2),
            _Outcome(SPECIMEN_AWAY, 0.30, 3),
            _Outcome("Tie", 0.25, 4),
        ]
        assert find_three_way_partition(
            outcomes, outcomes[0], SPECIMEN_HOME, SPECIMEN_AWAY
        ) is None

    def test_a_name_reaching_both_teams_refuses_the_whole_reading(self):
        """#4629's rule, applied to the partition: an outcome we cannot orient
        is not a member we can put in one."""
        outcomes = [
            _Outcome(SPECIMEN_HOME, K_HOME, 1),
            _Outcome(SPECIMEN_AWAY, K_AWAY, 2),
            _Outcome(f"{SPECIMEN_HOME} vs {SPECIMEN_AWAY}", K_TIE, 3),
        ]
        assert find_three_way_partition(
            outcomes, outcomes[0], SPECIMEN_HOME, SPECIMEN_AWAY
        ) is None


class TestTheReadingCarriesIt:
    """`compute_source_home_probability` — the one decision, three writers."""

    def test_a_three_way_group_publishes_the_venues_own_two_other_numbers(self):
        reading = compute_source_home_probability(
            _group(_three_way()), SPECIMEN_HOME, SPECIMEN_AWAY
        )
        assert reading is not None
        assert reading.home_probability == pytest.approx(K_HOME)
        assert reading.away_probability == pytest.approx(K_AWAY)
        assert reading.draw_probability == pytest.approx(K_TIE)

    def test_a_two_way_group_carries_no_partition_and_is_otherwise_unchanged(self):
        reading = compute_source_home_probability(
            _group(_two_way(), ticker="KXNBAGAME-26AUG30BOSGSW-BOS"),
            "Boston Celtics",
            "Golden State Warriors",
        )
        assert reading is not None
        assert reading.home_probability == pytest.approx(0.62)
        assert reading.away_probability is None
        assert reading.draw_probability is None

    def test_both_members_are_present_together_or_absent_together(self):
        """`BlendReading`'s stated invariant, asserted rather than assumed: a
        consumer testing either one must get the same answer."""
        for outcomes, names in (
            (_three_way(), (SPECIMEN_HOME, SPECIMEN_AWAY)),
            (_two_way(), ("Boston Celtics", "Golden State Warriors")),
        ):
            reading = compute_source_home_probability(
                _group(outcomes, ticker="KXNBAGAME-26AUG30BOSGSW-BOS"), *names
            )
            assert (reading.away_probability is None) == (
                reading.draw_probability is None
            )

    def test_a_devig_drops_the_partition(self):
        """The mean of two markets is not any one market's board, so the triple
        stops summing to one at the exact moment it stops being one reading."""
        name = "Villarreal vs Real Betis"
        pair = [
            MarketOutcomes(
                market=_Market(1, "kalshi", f"{SPECIMEN_TICKER}-VIL", name),
                outcomes=_three_way(),
            ),
            MarketOutcomes(
                market=_Market(2, "kalshi", f"{SPECIMEN_TICKER}-RBB", name),
                outcomes=[_Outcome(SPECIMEN_AWAY, 0.26, 1)],
            ),
        ]
        reading = compute_source_home_probability(pair, SPECIMEN_HOME, SPECIMEN_AWAY)
        assert reading is not None and reading.devigged is True
        assert reading.away_probability is None
        assert reading.draw_probability is None


class TestTheWritersSharedSecondSlot:
    """`_second_slot` — the ONE place the complement is still written."""

    def test_a_two_way_reading_gets_exactly_the_arithmetic_it_always_had(self):
        assert _second_slot(_Reading(0.62), 0.62) == (pytest.approx(0.38), None)

    def test_a_three_way_reading_gets_the_venues_numbers(self):
        away, draw = _second_slot(_Reading(K_HOME, K_AWAY, K_TIE), K_HOME)
        assert (away, draw) == (pytest.approx(K_AWAY), pytest.approx(K_TIE))

    def test_a_rounded_home_value_still_keeps_the_partition(self):
        """🔴 THE FAST LANE'S TRAP. It stamps the same 4-dp value it writes, so
        an equality test against the reading would read every rounding as an
        inversion and silently withdraw the partition from the fastest writer in
        the system — on every tick, during the match, which is the window the
        photographed card was taken in."""
        reading = _Reading(0.49503333, 0.2451, 0.2399)
        away, draw = _second_slot(reading, round(reading.home_probability, 4))
        assert (away, draw) == (pytest.approx(0.2451), pytest.approx(0.2399))

    def test_a_fired_inversion_withdraws_the_partition(self):
        """The books overruled the home/away assignment that NAMED the members,
        so the members are dropped and the row is left as it was."""
        away, draw = _second_slot(_Reading(K_HOME, K_AWAY, K_TIE), 1.0 - K_HOME)
        assert (away, draw) == (pytest.approx(K_HOME), None)

    def test_a_half_partition_is_never_published(self):
        for reading in (_Reading(K_HOME, K_AWAY, None), _Reading(K_HOME, None, K_TIE)):
            assert _second_slot(reading, K_HOME) == (pytest.approx(1.0 - K_HOME), None)


class TestTheServePathStopsRebuildingIt:
    """`_pair` — the gate that made a writer-only fix inert."""

    def test_a_coherent_triple_is_served_as_the_venue_priced_it(self):
        assert _pair(SNAP_HOME, K_AWAY, K_TIE) == (
            pytest.approx(SNAP_HOME),
            pytest.approx(K_AWAY),
        )

    def test_WITHOUT_the_draw_the_bug_comes_straight_back(self):
        """🔴 THE STRAWMAN, and the proof the third member is load-bearing.

        These are the same two true numbers. With no draw beside them the away
        slot is rebuilt as `1 - home` and the card prints the 51% Alex saw. If
        this ever starts passing `_pair`'s coherence guard has been loosened
        into the defect it is being kept apart from.
        """
        assert _pair(SNAP_HOME, K_AWAY) == (
            pytest.approx(SNAP_HOME),
            pytest.approx(1.0 - SNAP_HOME),
        )

    def test_a_two_way_pair_is_untouched(self):
        assert _pair(0.62, 0.38) == (pytest.approx(0.62), pytest.approx(0.38))

    def test_a_stale_or_unrelated_second_number_is_STILL_rebuilt(self):
        """The rule the guard was written for survives. A third number that does
        not close the partition proves nothing, so it buys nothing."""
        assert _pair(0.62, 0.11, 0.05) == (pytest.approx(0.62), pytest.approx(0.38))
        assert _pair(0.62, 0.11, None) == (pytest.approx(0.62), pytest.approx(0.38))

    def test_a_missing_away_still_derives_one(self):
        assert _pair(0.62, None, K_TIE) == (pytest.approx(0.62), pytest.approx(0.38))


class TestTheCardTheReaderActuallySees:
    """End to end: stored row -> ladder -> the two percents the card prints."""

    def _favourite(self, served):
        reading = resolve_prematch_reading(
            by_source={"kalshi": served}, books_home=0.6535, books_away=0.3465
        )
        percents = duel_percents_by_side(
            away_probability=reading["away_probability"],
            home_probability=reading["home_probability"],
        )
        return percents, ("away" if percents["away"] > percents["home"] else "home")

    def test_the_photographed_card_is_reproduced_by_the_OLD_stored_row(self):
        """The BEFORE, so nobody has to take the issue's screenshot on trust."""
        percents, favourite = self._favourite((SNAP_HOME, 1.0 - SNAP_HOME, None))
        assert (percents["away"], percents["home"]) == (51, 49)
        assert favourite == "away", "Real Betis, a 24.5% shot, printed as favourite"

    def test_the_new_stored_row_puts_the_favourite_back_on_the_right_club(self):
        percents, favourite = self._favourite((SNAP_HOME, K_AWAY, K_TIE))
        assert (percents["away"], percents["home"]) == (25, 50)
        assert favourite == "home"

    def test_a_two_way_sport_prints_its_pair_exactly_as_before(self):
        """The other direction of the issue's requirement, at the surface."""
        percents, favourite = self._favourite((0.62, 0.38, None))
        assert (percents["away"], percents["home"]) == (38, 62)
        assert favourite == "home"

    def test_a_two_element_tuple_still_unpacks(self):
        """Every caller that predates #6277 hands a pair, and must be unharmed."""
        reading = resolve_prematch_reading(by_source={"kalshi": (0.62, 0.38)})
        assert reading["home_probability"] == pytest.approx(0.62)
        assert reading["away_probability"] == pytest.approx(0.38)

    @pytest.mark.parametrize(
        "event_id,k_home,k_away,k_tie,snap_home",
        [
            (15297674, 0.385, 0.345, 0.265, 0.410),
            (15297676, 0.515, 0.235, 0.255, 0.460),
            (15297691, 0.435, 0.285, 0.275, 0.430),
            (15297742, 0.425, 0.285, 0.290, 0.360),
            (15297743, 0.360, 0.345, 0.285, 0.410),
            (15297787, 0.375, 0.345, 0.285, 0.340),
            (15297956, 0.455, 0.265, 0.285, 0.430),
            (15297965, 0.365, 0.325, 0.305, 0.340),
            (15298124, 0.505, 0.245, 0.240, 0.495),
            (15299370, 0.365, 0.355, 0.280, 0.390),
            (15299942, 0.430, 0.275, 0.295, 0.470),
            (15301223, 0.415, 0.305, 0.275, 0.490),
            (15303008, 0.455, 0.295, 0.245, 0.490),
            (15305027, 0.465, 0.265, 0.280, 0.480),
            (15305518, 0.360, 0.350, 0.290, 0.340),
            (15305917, 0.460, 0.230, 0.270, 0.440),
            (15306159, 0.345, 0.335, 0.285, 0.210),
            (15307039, 0.350, 0.340, 0.275, 0.390),
            (15307095, 0.455, 0.245, 0.285, 0.440),
            (15307096, 0.420, 0.290, 0.290, 0.420),
            (15307257, 0.490, 0.225, 0.300, 0.410),
        ],
    )
    def test_all_21_inverted_cards_stop_inverting(
        self, event_id, k_home, k_away, k_tie, snap_home
    ):
        """The measured population, by id, from the issue's own table.

        🔴 **THE TWO COLUMNS ARE TWO DIFFERENT INSTANTS AND THIS TEST REFUSES TO
        PRETEND OTHERWISE.** ``snap_home`` is the last pre-kickoff snapshot;
        ``k_*`` is the board's OPEN, minutes to days earlier. Feeding
        ``(snap_home, k_away, k_tie)`` to the resolver as though it were one row
        is a fixture no writer could ever produce — the three do not sum to one
        on 9 of these 21 — so each arm below is asserted only against an
        internally coherent set of numbers:

        * the BEFORE arm uses the STORED pair alone, and 21/21 of them put the
          away side in front, which is what put the row in this population;
        * the AFTER arm uses the BOARD alone, and 21/21 boards price the home
          side above the away side, so a card served from the board cannot
          invert.

        What the two arms together do NOT license is "21 cards were wrong about
        who was favourite". Modelling the drift (hold the board's away/tie ratio,
        re-anchor on ``snap_home``) leaves 4 of the 21 — 15297787, 15297965,
        15305518 and 15306159 — where the away side plausibly WAS in front by
        kickoff. 15306159's home price had drifted .345 -> .210. So 21 is an upper
        bound on the wrong-favourite count, and the defect this fixes is the
        FABRICATED COMPLEMENT (230/230, structural), which is true of all of them
        whatever the drift did.
        """
        assert k_home > k_away, "the board's own favourite is the home side"
        assert 0.90 <= k_home + k_away + k_tie <= 1.10, "the board is a partition"

        _, before = self._favourite((snap_home, 1.0 - snap_home, None))
        assert before == "away", "this row is in the population because it inverted"

        percents, after = self._favourite((k_home, k_away, k_tie))
        assert after == "home"
        assert percents["home"] > percents["away"]


class TestADedupedRowDoesNotKeepAStaleSecondSlot:
    """`_create_or_update_win_prob_snapshot` — sameness is decided on HOME alone.

    That test was complete for as long as away was `1 - home`: the two could not
    disagree. Now they can, and on the FIRST pass after this ships every existing
    row holds the fabricated complement. Without the refresh, a soccer market
    whose home price happens to hold across that pass keeps the number this issue
    is about — on the settled card, which is where it is read.
    """

    class _Existing:
        def __init__(self, home, away, draw=None):
            self.home_win_probability = home
            self.away_win_probability = away
            self.draw_probability = draw
            self.game_state = None
            self.reading_count = 1
            self.valid_until = None
            self.captured_at = None

    class _Session:
        def __init__(self, existing):
            self._existing = existing

        async def execute(self, *_a, **_k):
            existing = self._existing

            class _R:
                def scalar_one_or_none(self):
                    return existing

            return _R()

    async def _write(self, existing, **kwargs):
        from app.tasks.snapshots import _create_or_update_win_prob_snapshot

        return await _create_or_update_win_prob_snapshot(
            self._Session(existing), event_id=1, source="kalshi", **kwargs
        )

    @pytest.mark.asyncio
    async def test_an_unchanged_home_price_still_corrects_the_away_slot(self):
        existing = self._Existing(SNAP_HOME, 1.0 - SNAP_HOME, None)
        row, is_new = await self._write(
            existing,
            home_win_probability=SNAP_HOME,
            away_win_probability=K_AWAY,
            draw_probability=K_TIE,
        )
        assert is_new is False, "a corrected second slot is not a new price point"
        assert row is existing
        assert float(row.away_win_probability) == pytest.approx(K_AWAY)
        assert float(row.draw_probability) == pytest.approx(K_TIE)

    @pytest.mark.asyncio
    async def test_a_two_way_source_still_deduped_to_a_bare_complement(self):
        existing = self._Existing(0.62, 0.38, None)
        row, is_new = await self._write(
            existing, home_win_probability=0.62, away_win_probability=0.38
        )
        assert (is_new, float(row.away_win_probability), row.draw_probability) == (
            False,
            pytest.approx(0.38),
            None,
        )

    @pytest.mark.asyncio
    async def test_a_new_row_carries_the_draw(self):
        row, is_new = await self._write(
            None,
            home_win_probability=SNAP_HOME,
            away_win_probability=K_AWAY,
            draw_probability=K_TIE,
        )
        assert is_new is True
        assert float(row.draw_probability) == pytest.approx(K_TIE)


class TestTheRowSurvivesTheTripOutOfTheCursor:
    """`prematch_row_to_reading` — the link that used to be unreachable.

    A fix that stored an honest draw and then dropped it between the cursor and
    the ladder would pass every other test in this file and change nothing a
    reader sees. That is the whole shape of this issue, so it gets a test.
    """

    class _Row:
        def __init__(self, home, away, draw):
            self.home_win_probability = home
            self.away_win_probability = away
            self.draw_probability = draw

    def test_all_three_members_come_through(self):
        assert prematch_row_to_reading(self._Row(SNAP_HOME, K_AWAY, K_TIE)) == (
            pytest.approx(SNAP_HOME),
            pytest.approx(K_AWAY),
            pytest.approx(K_TIE),
        )

    def test_a_two_way_row_reads_as_a_pair_with_no_third(self):
        assert prematch_row_to_reading(self._Row(0.62, 0.38, None)) == (0.62, 0.38, None)

    def test_the_statement_actually_selects_the_column(self):
        """The mapping cannot read a column the query never asked for."""
        assert PREMATCH_PRIOR_SQL.count("draw_probability") == 2

    def test_decimals_from_the_driver_arrive_as_floats(self):
        """`Numeric(5,4)` comes back as Decimal, and every consumer downstream
        does float arithmetic with it."""
        row = self._Row(Decimal("0.4950"), Decimal("0.2450"), Decimal("0.2400"))
        assert [type(v) for v in prematch_row_to_reading(row)] == [float] * 3

    def test_the_mapping_and_the_ladder_agree_end_to_end(self):
        """Driven the way `_score_events` drives it, so the two halves of the
        contract are exercised together rather than each against a fixture."""
        reading = resolve_prematch_reading(
            by_source={
                "kalshi": prematch_row_to_reading(
                    self._Row(Decimal("0.4950"), Decimal("0.2450"), Decimal("0.2400"))
                )
            }
        )
        assert reading["away_probability"] == pytest.approx(K_AWAY)


class TestTheWriterAndTheReaderAgreeOnWhatAPartitionIs:
    """The pin between the two bands — the gap that would go silently half-inert.

    A reader narrower than its writer stores a truthful row and then discards it
    at serve time: the database changes, every unit test passes, and the card
    does not move. That is the exact failure `_pair` already caused once, and the
    only thing standing between this ship and a repeat of it is that these two
    constants agree. Proximity is not agreement, so it is asserted.
    """

    def test_the_serve_gate_admits_every_sum_the_writer_can_publish(self):
        from app.utils.prediction_market_matching import _THREE_WAY_SUM_BAND
        from app.utils.prematch_reading import _PARTITION_TOLERANCE

        low, high = _THREE_WAY_SUM_BAND
        assert 1.0 - low <= _PARTITION_TOLERANCE
        assert high - 1.0 <= _PARTITION_TOLERANCE

    @pytest.mark.parametrize("total", [0.90, 0.95, 1.0, 1.05, 1.10])
    def test_a_board_at_each_end_of_the_writers_band_survives_the_round_trip(
        self, total
    ):
        """Driven through BOTH halves on one board, so a future narrowing of
        either constant fails here rather than on production."""
        home, away = 0.45 * total, 0.25 * total
        draw = total - home - away
        outcomes = [
            _Outcome(SPECIMEN_HOME, home, 1),
            _Outcome(SPECIMEN_AWAY, away, 2),
            _Outcome("Tie", draw, 3),
        ]
        reading = compute_source_home_probability(
            _group(outcomes), SPECIMEN_HOME, SPECIMEN_AWAY
        )
        assert reading.away_probability is not None, "the writer refused this board"

        served = _pair(
            reading.home_probability,
            reading.away_probability,
            reading.draw_probability,
        )
        assert served[1] == pytest.approx(away), "the reader discarded it again"
