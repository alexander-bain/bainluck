"""Q460 — guards for the one expression both blend writers share.

The class of bug these exist to catch is not "the arithmetic is wrong". It is
**the arithmetic is duplicated and one copy drifted**. Before this queue, the
120-second poll owned the only path from a venue price to
`Event.win_probability_sources`; the WebSocket fast lane now writes the same key
between polls. If those two ever disagree, the symptom is not an exception — it
is a hero that flickers between two numbers every two minutes, which reads as a
data problem and is actually a code-duplication problem.

So the load-bearing test in this file is `TestPollAndFastLaneAgree`: it drives
the extracted decision the way the poll does and the way the fast lane does, and
asserts one number comes out. Delete the shared module and that test fails.
"""

from app.utils.live_blend import (
    MarketOutcomes,
    compute_source_home_probability,
    is_game_winner_market,
    select_primary_market,
)


class _Outcome:
    """Lightweight FuturesOutcome stand-in — the attributes the decision reads."""

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


def _kalshi_game(id, ticker, name, outcomes):
    return MarketOutcomes(
        market=_Market(id, "kalshi", ticker, name), outcomes=outcomes
    )


class TestIsGameWinnerMarket:
    def test_kalshi_game_ticker_feeds_the_blend(self):
        m = _Market(1, "kalshi", "KXNBAGAME-26AUG30BOSGSW-BOS", "Celtics vs. Warriors")
        assert is_game_winner_market(m) is True

    def test_kalshi_prop_ticker_does_not(self):
        m = _Market(1, "kalshi", "KXNBAPOINTS-26AUG30-TATUM", "Tatum points")
        assert is_game_winner_market(m) is False

    def test_polymarket_is_never_gated_by_ticker(self):
        """Polymarket carries no equivalent signal — linkage is the authority."""
        m = _Market(1, "polymarket", "0xabc", "Celtics vs. Warriors")
        assert is_game_winner_market(m) is False

    def test_missing_external_id_is_not_a_game_winner(self):
        assert is_game_winner_market(_Market(1, "kalshi", None, "x")) is False


class TestSelectPrimaryMarket:
    def test_empty_group_selects_nothing(self):
        assert select_primary_market([]) is None

    def test_game_winner_beats_a_prop_regardless_of_id(self):
        prop = _kalshi_game(1, "KXNBAPOINTS-X-TATUM", "Tatum points", [])
        game = _kalshi_game(99, "KXNBAGAME-X-BOS", "Celtics vs. Warriors", [])
        assert select_primary_market([prop, game]).market.id == 99
        assert select_primary_market([game, prop]).market.id == 99

    def test_among_equals_lowest_id_wins_either_way_round(self):
        """Stable across passes — not dependent on the order rows arrived in."""
        a = _kalshi_game(7, "KXNBAGAME-X-BOS", "Celtics vs. Warriors", [])
        b = _kalshi_game(3, "KXNBAGAME-X-GSW", "Warriors vs. Celtics", [])
        assert select_primary_market([a, b]).market.id == 3
        assert select_primary_market([b, a]).market.id == 3


class TestComputeSourceHomeProbability:
    def test_single_market_yes_is_home(self):
        group = [
            _kalshi_game(
                1, "KXNBAGAME-26AUG30BOSGSW-BOS", "Celtics vs. Warriors",
                [_Outcome("Boston Celtics", 0.67), _Outcome("Golden State Warriors", 0.33)],
            )
        ]
        reading = compute_source_home_probability(
            group, "Boston Celtics", "Golden State Warriors",
        )
        assert reading is not None
        assert reading.home_probability == 0.67
        assert reading.yes_probability == 0.67
        assert reading.outcome.name == "Boston Celtics"
        assert reading.devigged is False

    def test_yes_is_away_inverts(self):
        group = [
            _kalshi_game(
                1, "KXNBAGAME-26AUG30BOSGSW-GSW", "Warriors vs. Celtics",
                [_Outcome("Golden State Warriors", 0.4), _Outcome("Boston Celtics", 0.6)],
            )
        ]
        reading = compute_source_home_probability(
            group, "Boston Celtics", "Golden State Warriors",
        )
        assert reading is not None
        # YES side is the away team, so the home reading is its complement.
        assert abs(reading.home_probability - 0.6) < 1e-9

    def test_kalshi_prop_market_asserts_nothing(self):
        """A prop linked to a game must never write the game's blend."""
        group = [
            _kalshi_game(
                1, "KXNBAPOINTS-26AUG30-TATUM", "Celtics vs. Warriors",
                [_Outcome("Boston Celtics", 0.67), _Outcome("Golden State Warriors", 0.33)],
            )
        ]
        assert compute_source_home_probability(
            group, "Boston Celtics", "Golden State Warriors",
        ) is None

    def test_unparseable_matchup_asserts_nothing(self):
        group = [
            MarketOutcomes(
                market=_Market(1, "polymarket", "0xabc", "Who knows"),
                outcomes=[_Outcome("Boston Celtics", 0.67)],
            )
        ]
        assert compute_source_home_probability(
            group, "Boston Celtics", "Golden State Warriors",
        ) is None

    def test_no_outcomes_asserts_nothing(self):
        group = [_kalshi_game(1, "KXNBAGAME-X-BOS", "Celtics vs. Warriors", [])]
        assert compute_source_home_probability(
            group, "Boston Celtics", "Golden State Warriors",
        ) is None

    def test_two_markets_devig_averages_both_sides(self):
        """Kalshi's per-team pair: both YES prices carry vig in opposite
        directions, so the average is the fair line."""
        group = [
            _kalshi_game(
                1, "KXNBAGAME-26AUG30BOSGSW-BOS", "Celtics vs. Warriors",
                [_Outcome("Boston Celtics", 0.70), _Outcome("Golden State Warriors", 0.30)],
            ),
            _kalshi_game(
                2, "KXNBAGAME-26AUG30BOSGSW-GSW", "Celtics vs. Warriors",
                [_Outcome("Boston Celtics", 0.60), _Outcome("Golden State Warriors", 0.40)],
            ),
        ]
        reading = compute_source_home_probability(
            group, "Boston Celtics", "Golden State Warriors",
        )
        assert reading is not None
        assert abs(reading.home_probability - 0.65) < 1e-9
        assert reading.devigged is True

    def test_unresolvable_sibling_leaves_the_single_reading_alone(self):
        """An average of one usable number and one absent one is not a devig."""
        group = [
            _kalshi_game(
                1, "KXNBAGAME-26AUG30BOSGSW-BOS", "Celtics vs. Warriors",
                [_Outcome("Boston Celtics", 0.70), _Outcome("Golden State Warriors", 0.30)],
            ),
            _kalshi_game(
                2, "KXNBAGAME-26AUG30BOSGSW-GSW", "Celtics vs. Warriors",
                [_Outcome("Over 220.5", 0.5), _Outcome("Under 220.5", 0.5)],
            ),
        ]
        reading = compute_source_home_probability(
            group, "Boston Celtics", "Golden State Warriors",
        )
        assert reading is not None
        assert abs(reading.home_probability - 0.70) < 1e-9
        assert reading.devigged is False

    def test_three_markets_do_not_devig(self):
        """Devig is defined for the two-market pair only; three is not a pair."""
        common = [_Outcome("Boston Celtics", 0.70), _Outcome("Golden State Warriors", 0.30)]
        group = [
            _kalshi_game(i, f"KXNBAGAME-26AUG30BOSGSW-{i}", "Celtics vs. Warriors", common)
            for i in (1, 2, 3)
        ]
        reading = compute_source_home_probability(
            group, "Boston Celtics", "Golden State Warriors",
        )
        assert reading is not None
        assert reading.devigged is False


class TestSiblingUsesPrimaryMatchup:
    """The sibling must be read through the PRIMARY's matchup parse.

    Kalshi's two markets for one game carry two different names. Re-deriving the
    matchup per market lets the two halves of a devig disagree about which side
    is home — and then the average of a home reading and an away reading is a
    number with no meaning, produced silently, only on the two-market path.
    """

    def test_devig_of_a_reversed_sibling_name_stays_on_the_home_side(self):
        group = [
            _kalshi_game(
                1, "KXNBAGAME-26AUG30BOSGSW-BOS", "Celtics vs. Warriors",
                [_Outcome("Boston Celtics", 0.70), _Outcome("Golden State Warriors", 0.30)],
            ),
            # Same game, name written the other way round.
            _kalshi_game(
                2, "KXNBAGAME-26AUG30BOSGSW-GSW", "Warriors vs. Celtics",
                [_Outcome("Boston Celtics", 0.60), _Outcome("Golden State Warriors", 0.40)],
            ),
        ]
        reading = compute_source_home_probability(
            group, "Boston Celtics", "Golden State Warriors",
        )
        assert reading is not None
        # Both halves read as HOME probabilities (0.70, 0.60) → 0.65.
        # If the sibling had been read through its own reversed parse it would
        # have contributed 0.40, giving 0.55.
        assert abs(reading.home_probability - 0.65) < 1e-9


class TestPollAndFastLaneAgree:
    """The anti-drift guard. Both callers, same rows, one number.

    This is the test that justifies the module existing. It builds the group the
    way `_poll_live_prediction_market_prices` builds it (from its
    `all_per_event_source_live` / `outcomes_by_market` pair) and the way
    `LiveBlendRefresher._refresh_batch` builds it (from a per-event grouping),
    and asserts the readings are identical.
    """

    def _rows(self):
        out_a = [_Outcome("Boston Celtics", 0.70), _Outcome("Golden State Warriors", 0.30)]
        out_b = [_Outcome("Boston Celtics", 0.62), _Outcome("Golden State Warriors", 0.38)]
        m_a = _Market(11, "kalshi", "KXNBAGAME-26AUG30BOSGSW-BOS", "Celtics vs. Warriors")
        m_b = _Market(12, "kalshi", "KXNBAGAME-26AUG30BOSGSW-GSW", "Celtics vs. Warriors")
        return [(m_a, out_a), (m_b, out_b)]

    def test_both_construction_paths_produce_one_number(self):
        rows = self._rows()

        # Poll shape: markets grouped by (event, source), outcomes in a side map.
        outcomes_by_market = {m.id: o for m, o in rows}
        poll_group = [
            MarketOutcomes(market=m, outcomes=outcomes_by_market.get(m.id, []))
            for m, _ in rows
        ]

        # Fast-lane shape: markets accumulated per event as rows stream back.
        fast_group = []
        for m, o in rows:
            fast_group.append(MarketOutcomes(market=m, outcomes=o))

        poll_reading = compute_source_home_probability(
            poll_group, "Boston Celtics", "Golden State Warriors",
        )
        fast_reading = compute_source_home_probability(
            fast_group, "Boston Celtics", "Golden State Warriors",
        )
        assert poll_reading is not None and fast_reading is not None
        assert poll_reading.home_probability == fast_reading.home_probability
        assert poll_reading.market.id == fast_reading.market.id
        assert poll_reading.outcome.name == fast_reading.outcome.name

    def test_row_order_does_not_change_the_number(self):
        """The fast lane accumulates rows in whatever order the DB returns."""
        rows = self._rows()
        forward = [MarketOutcomes(market=m, outcomes=o) for m, o in rows]
        backward = [MarketOutcomes(market=m, outcomes=o) for m, o in reversed(rows)]
        a = compute_source_home_probability(
            forward, "Boston Celtics", "Golden State Warriors",
        )
        b = compute_source_home_probability(
            backward, "Boston Celtics", "Golden State Warriors",
        )
        assert a is not None and b is not None
        assert a.home_probability == b.home_probability
        assert a.market.id == b.market.id
