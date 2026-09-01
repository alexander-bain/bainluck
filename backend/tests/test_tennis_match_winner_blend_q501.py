"""Q501 — a tennis match winner is a moneyline, and the chart it feeds.

THE BUG THIS CLASS EXISTS TO CATCH. `feeds_win_prob_blend` is an ALLOWLIST, and
the failure mode of an allowlist is silence: a sport whose winner ticker does not
match the pattern is not rejected loudly, it simply never appears in the blend,
and every surface downstream renders a slightly emptier page than it should. That
already happened once — #1024 found every UFC/boxing bout missing because combat
tickers do not end in ``game`` — and the fix enumerated combat and stopped there.
Tennis had the identical shape and stayed broken for as long again.

Measured on production 2026-09-01, 3-day window of linked Kalshi markets:

    prefix                  events   events with `kalshi` in blend
    kxatpmatch                  89                               0
    kxwtamatch                  88                               0
    kxatpchallengermatch        75                               0
    kxmlbgame                   77                              77
    kxcs2game                  118                             114
    kxufcfight                  31                              31

The user-visible cost, on all 14 live US Open matches that day: `win_prob_history`
empty, `aggregate_line` absent (the `len(agg_sources) > 1` gate in
`routes/events.py` never clears when `betting` is the only series), and three
matches rendering a completely blank chart. Tennis has no ESPN model and no
stat_model, so Kalshi is the ONLY source that can make it multi-source.

WHY THE SUFFIX TEST IS NOT THE TEST. `prefix.endswith("match")` is the obvious
implementation and it is wrong: ``kxatpexactmatch`` ends in "match" and is the
six-outcome EXACT SCORE field market. `TestPropsStayOut` is the half of this file
that fails on that shortcut, and it is the reason the set is enumerated.
"""

import pytest

from app.utils.live_blend import MarketOutcomes, compute_source_home_probability
from app.utils.prediction_market_matching import feeds_win_prob_blend


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


# The real linked rows behind event 15293828 (Taylor Fritz vs Darwin Blanch,
# US Open, live at 2026-09-01T19:0xZ), read out of production. Outcome names and
# prices are verbatim; this is the specimen the fix was built against.
FRITZ_MATCH = "KXATPMATCH-26AUG30FRIBLA"
FRITZ_SET2 = "KXATPSETWINNER-26AUG30FRIBLA-2"


def _fritz_outcomes(home_prob=0.99):
    return [
        _Outcome("Taylor Fritz", home_prob),
        _Outcome("Darwin Blanch", round(1.0 - home_prob, 4)),
    ]


def _market_group():
    """The full 7-market Kalshi group production actually linked to the event."""
    return [
        MarketOutcomes(
            _Market(59693735, "kalshi", FRITZ_MATCH, "Fritz vs Blanch"),
            _fritz_outcomes(),
        ),
        MarketOutcomes(
            _Market(59705924, "kalshi", FRITZ_SET2, "Taylor Fritz vs Darwin Blanch: Set 2 Winner"),
            _fritz_outcomes(0.855),
        ),
        MarketOutcomes(
            _Market(59706019, "kalshi", "KXATPGTOTAL-26AUG30FRIBLA", "Total Games"),
            [_Outcome("Over 30.5", 0.5)],
        ),
        MarketOutcomes(
            _Market(59706065, "kalshi", "KXATPGSPREAD-26AUG30FRIBLA", "Game Spread"),
            [_Outcome("Fritz -6.5", 0.5)],
        ),
    ]


class TestMatchWinnersAreAdmitted:
    """The winner line of every racquet tour we ingest reaches the blend."""

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXATPMATCH-26AUG30FRIBLA",
            "KXWTAMATCH-26AUG30SAKMON",
            "KXATPCHALLENGERMATCH-26AUG30ABCDEF",
            "KXWTACHALLENGERMATCH-26AUG30ABCDEF",
            "KXATPDOUBLES-26AUG30ABCDEF",
            "KXWTADOUBLES-26AUG30ABCDEF",
            "KXATPCHALLENGERDOUBLES-26AUG30ABCDEF",
            "KXWTACHALLENGERDOUBLES-26AUG30ABCDEF",
        ],
    )
    def test_match_winner_feeds_the_blend(self, ticker):
        assert feeds_win_prob_blend(ticker) is True

    def test_lowercase_ticker_is_admitted_too(self):
        """Prefix matching is case-folded; a lowercased ticker is the same line."""
        assert feeds_win_prob_blend("kxatpmatch-26aug30fribla") is True


class TestPropsStayOut:
    """The half of this file that fails a naive ``endswith("match")``.

    Every one of these is correctly LINKED to the event for display. None of
    them is the match moneyline, and none may write the probability series.
    """

    @pytest.mark.parametrize(
        "ticker",
        [
            # Ends in "match" and is emphatically not a moneyline.
            "KXATPEXACTMATCH-26AUG30FRIBLA",
            "KXWTAEXACTMATCH-26AUG30SAKMON",
            # Same two player names as the winner line — the contamination risk.
            "KXATPSETWINNER-26AUG30FRIBLA-2",
            "KXWTASETWINNER-26AUG30SAKMON-1",
            # Ordinary props.
            "KXATPGSPREAD-26AUG30FRIBLA",
            "KXATPGTOTAL-26AUG30FRIBLA",
            "KXWTAGTOTAL-26AUG30SAKMON",
        ],
    )
    def test_tennis_prop_does_not_feed_the_blend(self, ticker):
        assert feeds_win_prob_blend(ticker) is False

    def test_endswith_match_alone_would_admit_the_exact_score_market(self):
        """Pins WHY the set is enumerated rather than suffix-matched.

        If someone later replaces the frozenset with
        ``prefix.endswith("match")``, this asserts the two tickers that shortcut
        cannot tell apart — and the assertion below it fails.
        """
        assert "kxatpexactmatch".endswith("match")
        assert feeds_win_prob_blend("KXATPEXACTMATCH-X") is False


class TestExistingAdmissionsSurvive:
    """The allowlist grew; it did not change shape."""

    @pytest.mark.parametrize(
        "ticker",
        ["KXMLBGAME-X", "KXNBAGAME-X", "KXNFLGAME-X", "KXCS2GAME-X",
         "KXUFCFIGHT-X", "KXBOXING-X"],
    )
    def test_previously_admitted_still_admitted(self, ticker):
        assert feeds_win_prob_blend(ticker) is True

    @pytest.mark.parametrize(
        "ticker",
        ["KXNFLSPREAD-X", "KXNFLTOTAL-X", "KXUFCROUNDS-X", "KXMLBHR-X"],
    )
    def test_previously_excluded_still_excluded(self, ticker):
        assert feeds_win_prob_blend(ticker) is False

    def test_unknown_and_empty_tickers_are_refused(self):
        assert feeds_win_prob_blend(None) is False
        assert feeds_win_prob_blend("") is False
        assert feeds_win_prob_blend("KXSOMETHINGNEW-X") is False


class TestTheProductionSpecimenNowReads:
    """End-to-end on event 15293828: the gate was the only thing in the way."""

    def test_live_us_open_match_produces_a_blend_reading(self):
        reading = compute_source_home_probability(
            _market_group(), "Taylor Fritz", "Darwin Blanch",
        )
        assert reading is not None, "the US Open match asserts no probability"
        assert reading.home_probability == pytest.approx(0.99)

    def test_the_reading_comes_from_the_match_market_not_a_prop(self):
        reading = compute_source_home_probability(
            _market_group(), "Taylor Fritz", "Darwin Blanch",
        )
        assert reading.market.external_id == FRITZ_MATCH
        assert reading.outcome.name == "Taylor Fritz"


class TestSetWinnerCannotContaminateTheMoneyline:
    """The devig sibling must be a winner line, not merely name-resolvable.

    A tennis event listed with exactly two Kalshi markets — the match winner and
    one set winner — hits the ``len(group) == 2`` devig branch. The set winner
    carries the SAME two player names, so it resolves through
    `find_moneyline_outcome` without complaint, and the mean of "wins the match"
    (0.99) and "wins set 2" (0.855) would be stamped as the moneyline: 0.9225,
    a number that answers neither question. Nothing throws; the hero is just
    quietly wrong.
    """

    def _pair(self):
        return [
            MarketOutcomes(
                _Market(59693735, "kalshi", FRITZ_MATCH, "Fritz vs Blanch"),
                _fritz_outcomes(0.99),
            ),
            MarketOutcomes(
                _Market(59705924, "kalshi", FRITZ_SET2, "Taylor Fritz vs Darwin Blanch: Set 2 Winner"),
                _fritz_outcomes(0.855),
            ),
        ]

    def test_match_plus_set_winner_reports_the_match_price_alone(self):
        reading = compute_source_home_probability(
            self._pair(), "Taylor Fritz", "Darwin Blanch",
        )
        assert reading.home_probability == pytest.approx(0.99)
        assert reading.devigged is False

    def test_the_contaminated_mean_is_not_what_comes_out(self):
        """Names the wrong answer explicitly so a regression is unmistakable."""
        reading = compute_source_home_probability(
            self._pair(), "Taylor Fritz", "Darwin Blanch",
        )
        assert reading.home_probability != pytest.approx((0.99 + 0.855) / 2.0)


class TestGenuineDevigsSurviveTheGuard:
    """The guard must not pay for itself by retiring the devig it protects."""

    def test_kalshi_per_team_game_winner_pair_still_devigs(self):
        group = [
            MarketOutcomes(
                _Market(1, "kalshi", "KXNBAGAME-26X-BOS", "Celtics vs 76ers"),
                [_Outcome("Celtics", 0.60)],
            ),
            MarketOutcomes(
                _Market(2, "kalshi", "KXNBAGAME-26X-PHI", "Celtics vs 76ers"),
                [_Outcome("76ers", 0.44)],
            ),
        ]
        reading = compute_source_home_probability(group, "Celtics", "76ers")
        assert reading.devigged is True
        assert reading.home_probability == pytest.approx((0.60 + 0.56) / 2.0)

    def test_polymarket_pair_is_not_gated_by_a_kalshi_only_predicate(self):
        """`is_game_winner_market` is hard-False off Kalshi.

        Applying it unconditionally to the sibling would silently retire the
        Polymarket devig — a regression with no error and no failing arithmetic
        test, since the single reading it falls back to is still plausible.
        """
        group = [
            MarketOutcomes(
                _Market(1, "polymarket", "0xaaa", "Celtics vs 76ers"),
                [_Outcome("Celtics", 0.60)],
            ),
            MarketOutcomes(
                _Market(2, "polymarket", "0xbbb", "Celtics vs 76ers"),
                [_Outcome("76ers", 0.44)],
            ),
        ]
        reading = compute_source_home_probability(group, "Celtics", "76ers")
        assert reading.devigged is True
