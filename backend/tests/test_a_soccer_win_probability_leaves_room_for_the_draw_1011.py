"""#1011 / #6576 — a soccer win probability leaves room for the draw.

THE SHIP: a soccer match's probability stops overstating either named side,
because the draw is no longer divided out of the board.

THE DEFECT. ``_parse_snapshot_values`` read the two named sides of the ``h2h``
market and normalized them against each other. That silently asserts the pair is
the entire market. On a soccer game winner it is not — the book quotes a draw
holding roughly a quarter of the mass — so ``home/(home+away)`` inflated both
named sides, and ``betting`` carries weight 3.0 against 0.8 for the prediction
markets, which put the blended hero **~8pp** onto the home team on every soccer
match with a sportsbook line.

THE EVIDENCE, from two independent directions:

* OUTCOME side (discover/126, #6576 comment 5700712242): over 80 soccer events
  holding both a draw-bearing Kalshi snapshot and a ``betting`` value,
  ``betting`` matched ``kalshi_home/(kalshi_home+kalshi_away)`` at abs Δ 0.0151,
  78/80 inside a 0.10 band — against 0.1289 and 16/80 for the raw three-way home.
* INPUT side (live/331, this fix): the raw vig-inclusive implied ``home+away``
  stored in ``odds_snapshots`` averages **0.743-0.808** across 25 soccer leagues
  and **1.043-1.110** across all 17 non-soccer sports, 2 days, 2026-09-16. A
  market a book really offers sums ABOVE 1 — the excess is the vig — so the
  soccer shortfall is not a thin market, it is an outcome we declined to read.

Those two are the same fact measured from opposite ends, which is the second
independent method notice 26(b) requires before a number is acted on.

WHAT IS DELIBERATELY NOT TESTED HERE, because it is not this fix: the away leg's
fabricated complement (``_second_slot``, lane1's file, #1011's other half), and
any reconstruction of history. This is the forward writer only.
"""

import pytest

from app.tasks.odds_polling import _parse_snapshot_values
from app.utils.odds_math import (
    MARKET_COMPLETENESS_FLOOR,
    american_to_probability,
    h2h_pair_on_the_full_board,
    moneyline_to_probability,
    probability_to_american,
)


# ── Real provider payload shapes ─────────────────────────────────────────────
#
# The Odds API `/v4/sports/{key}/odds?markets=h2h` response shape, verbatim: an
# event carries `home_team`/`away_team` and a `bookmakers[]` list, each with
# `markets[].outcomes[]` of `{name, price}`. The soccer board carries THREE
# outcomes and the third is named "Draw" — which this code never reads by name.
#
# Prices are chosen to reproduce the production arithmetic measured above:
# raw implied home+away lands at ~0.79 and the full board at ~1.05.

def _soccer_event(bookmaker_outcomes):
    """One Odds API event payload for a soccer fixture."""
    return {
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "bookmakers": [
            {
                "key": "pinnacle",
                "markets": [{"key": "h2h", "outcomes": bookmaker_outcomes}],
            }
        ],
    }


#: A three-way board. Raw implied: home .4762 + away .2381 + draw .2703 = .9846?
#: No — computed exactly below so the test states the real numbers rather than
#: approximations. -110/+320/+270 gives .5238 + .2381 + .2703 = 1.0322.
SOCCER_THREE_WAY = [
    {"name": "Arsenal", "price": -110},
    {"name": "Chelsea", "price": 320},
    {"name": "Draw", "price": 270},
]

#: The same fixture as the OLD parser saw it: the draw dropped on the floor.
SOCCER_TWO_WAY_FRAGMENT = [
    {"name": "Arsenal", "price": -110},
    {"name": "Chelsea", "price": 320},
]

#: A genuine two-way market — an NFL game. Raw implied sums above 1.
NFL_TWO_WAY = [
    {"name": "Kansas City Chiefs", "price": -150},
    {"name": "Denver Broncos", "price": 130},
]


# ── Real production specimens, read from `odds_snapshots` on 2026-09-16 ──────
#
# `(home_moneyline, away_moneyline, market_home, stored_two_way)`. The two prices
# and `stored_two_way` are VERBATIM production rows — the draftkings column on
# each event, and the `home_win_probability` the old code actually stored beside
# it. `market_home` is what the prediction markets said about the same fixture,
# from `events.win_probability_sources`.
#
# The draw price is absent from all of this because WE NEVER STORED IT — that
# omission is the defect itself. It is reconstructed below from a stated
# overround, never solved for `market_home`.
PRODUCTION_SPECIMENS = [
    # 15298542, Europa League. betting .2868 vs kalshi .205
    (340, -130, 0.205, 0.2868),
    # 15308675, Allsvenskan. betting .5385 vs polymarket .415
    (140, 180, 0.415, 0.5385),
    # 15311024, Swiss Super League. betting .6095 vs polymarket .445
    (105, 220, 0.445, 0.6095),
]

#: The same boards without the market value, for the reproduction control.
PRODUCTION_BOARDS = [
    (home, away, stored) for home, away, _market, stored in PRODUCTION_SPECIMENS
]

#: Typical sportsbook overround on a soccer game winner. Used ONLY to
#: reconstruct the draw price our ingest threw away.
TYPICAL_OVERROUND = 0.05


def _draw_price_for_overround(home_price, away_price, overround=TYPICAL_OVERROUND):
    """The draw price that makes this real board carry a stated overround.

    The board a book actually posts sums to ``1 + overround``; we hold two of
    its three legs. This recovers the third from the margin alone, so nothing
    about the prediction markets' answer enters the reconstruction.
    """
    held = american_to_probability(home_price) + american_to_probability(away_price)
    return probability_to_american((1.0 + overround) - held)


class TestTheDrawIsNoLongerDividedOut:
    """The named sides stop absorbing the draw's mass."""

    def test_the_three_way_board_leaves_the_draw_its_share(self):
        home, away = h2h_pair_on_the_full_board(-110, 320, [270])

        # The board sums to 1 only WITH the draw. home+away must fall short of
        # 1 by exactly the draw's de-vigged share — that shortfall IS the ship.
        assert home + away < 1.0
        draw_share = 1.0 - home - away
        assert draw_share == pytest.approx(0.2703 / 1.0322, abs=1e-3)
        assert draw_share > 0.2, "the draw must hold real mass, not a rounding crumb"

    def test_it_is_strictly_lower_than_the_two_way_renormalization(self):
        """The old answer on the same board, and the gap is the harm."""
        old_home, old_away = moneyline_to_probability(-110, 320)
        new_home, new_away = h2h_pair_on_the_full_board(-110, 320, [270])

        assert old_home + old_away == pytest.approx(1.0), "the old pair filled the board"
        assert new_home < old_home
        assert new_away < old_away

        # Both named sides were inflated by the same factor, 1/(1-draw). That is
        # the mechanism discover measured from the outcome side.
        assert old_home == pytest.approx(new_home / (new_home + new_away), abs=1e-9)

    @pytest.mark.parametrize("home_price,away_price,stored_two_way", PRODUCTION_BOARDS)
    def test_the_old_answer_is_reproduced_exactly_from_the_real_prices(
        self, home_price, away_price, stored_two_way
    ):
        """The specimens are real: the old code's stored value is re-derived.

        This is the control that makes the rest of the file mean something. If
        these prices did not reproduce the probability actually sitting in
        `odds_snapshots.home_win_probability` on production, they would be a
        story about a board that never existed.
        """
        old_home, _ = moneyline_to_probability(home_price, away_price)
        assert round(old_home, 4) == pytest.approx(stored_two_way, abs=1e-4)

    @pytest.mark.parametrize(
        "home_price,away_price,market_home,stored_two_way", PRODUCTION_SPECIMENS
    )
    def test_it_lands_on_the_scale_the_prediction_markets_already_use(
        self, home_price, away_price, market_home, stored_two_way
    ):
        """The whole point: `betting` stops being the odd member of the blend.

        Kalshi and Polymarket already publish the three-way home probability
        (discover/126: they agree with each other, 2 of 33 pairs outside the
        band). `betting` was the one source on a different scale. After the fix
        it is on theirs — so the blend stops averaging two different questions.

        NOT CIRCULAR, and this is the part worth reading twice. The draw price
        is reconstructed from a generic 5% overround — it is NOT solved for the
        prediction market's answer. That the three boards then land within ~2pp
        of what Kalshi and Polymarket independently say is a RESULT, not an
        assumption, and it is the input-side confirmation of discover's
        outcome-side measurement.
        """
        draw_price = _draw_price_for_overround(home_price, away_price)
        old_home, _ = moneyline_to_probability(home_price, away_price)
        new_home, _ = h2h_pair_on_the_full_board(
            home_price, away_price, [draw_price]
        )

        assert abs(new_home - market_home) < abs(old_home - market_home), (
            f"the fix must move TOWARD the prediction markets: "
            f"old {old_home:.4f} -> new {new_home:.4f}, they say {market_home}"
        )
        assert abs(new_home - market_home) < 0.03, (
            f"new {new_home:.4f} vs market {market_home} — expected ~2pp"
        )
        # And the distance it travelled is the harm discover measured from the
        # other end: 7-17pp on the source, ~8pp once the blend has weighted it.
        assert 0.05 < old_home - new_home < 0.20


class TestGenuineTwoWayMarketsAreUntouched:
    """The control. A two-way board must take the identical arithmetic."""

    def test_a_two_way_board_is_byte_identical_to_the_old_answer(self):
        assert h2h_pair_on_the_full_board(-150, 130) == moneyline_to_probability(
            -150, 130
        )

    def test_an_empty_other_list_is_the_same_as_no_other_list(self):
        assert h2h_pair_on_the_full_board(-150, 130, []) == h2h_pair_on_the_full_board(
            -150, 130
        )

    @pytest.mark.parametrize(
        "sport,home_price,away_price",
        [
            ("americanfootball_nfl", -150, 130),
            ("baseball_mlb", -110, -110),
            ("basketball_nba", -500, 380),
            # 🪤 CRICKET. It sits in the existing `DRAW_CAPABLE_CATEGORIES`
            # beside soccer, but `cricket_odi` reads 1.0570 and
            # `cricket_international_t20` 1.0585 on production — genuine,
            # complete TWO-way markets, because limited-overs cricket is not
            # drawn the way Test cricket is. A rule that inferred three-wayness
            # from the SPORT would have deleted the sportsbook line from every
            # cricket match. This is why the fix never asks what sport it is.
            ("cricket_odi", -130, 110),
            ("cricket_international_t20", -140, 120),
        ],
    )
    def test_the_pair_sums_to_one_where_the_pair_is_the_whole_market(
        self, sport, home_price, away_price
    ):
        home, away = h2h_pair_on_the_full_board(home_price, away_price)
        assert home + away == pytest.approx(1.0)

    def test_a_genuinely_two_way_soccer_market_is_preserved(self):
        """An advancement or shootout-decided line quotes two and sums above 1.

        Shape is decided by what the book QUOTES, so this is preserved with no
        special case: it never reaches the three-way path at all.
        """
        home, away = h2h_pair_on_the_full_board(-160, 135)
        assert home + away == pytest.approx(1.0)


class TestAnIncompleteBoardIsRefusedNotRescaled:
    """A missing outcome makes the board unreadable — it is never inferred."""

    def test_the_two_way_fragment_of_a_three_way_board_is_refused(self):
        """The exact shape the old parser fed itself: 0.79, not a market."""
        raw_sum = american_to_probability(-110) + american_to_probability(320)
        assert raw_sum < MARKET_COMPLETENESS_FLOOR, (
            "this specimen must actually be a fragment, or the test proves nothing"
        )
        assert h2h_pair_on_the_full_board(-110, 320) is None

    def test_the_refusal_is_none_and_not_a_zero(self):
        """gotcha #53: 'we cannot say' must not render as a number."""
        assert h2h_pair_on_the_full_board(-110, 320) is None

    def test_a_missing_draw_price_is_not_inferred_as_zero(self):
        """A `None` third price leaves the board short, and short is refused."""
        assert h2h_pair_on_the_full_board(-110, 320, [None]) is None

    def test_a_missing_side_is_refused(self):
        assert h2h_pair_on_the_full_board(None, 320, [270]) is None
        assert h2h_pair_on_the_full_board(-110, None, [270]) is None

    def test_the_floor_sits_between_the_two_measured_populations(self):
        """0.95 is above every fragment and below every complete market.

        Measured 2026-09-16: soccer fragments top out at 0.808, complete markets
        bottom out at 1.043. The floor must separate them with room on each side,
        and must stay under the 1.0 a zero-vig book would post.
        """
        assert 0.808 < MARKET_COMPLETENESS_FLOOR < 1.0
        assert MARKET_COMPLETENESS_FLOOR < 1.043


class TestTheParserWiresItUp:
    """The helper is correct AND it is actually reached — #6277's lesson.

    A fix to the arithmetic that the writer never calls is inert, and that
    inertness is invisible in a unit test of the arithmetic alone.
    """

    def test_a_soccer_payload_leaves_the_draw_its_mass(self):
        event = _soccer_event(SOCCER_THREE_WAY)
        values = _parse_snapshot_values(event["bookmakers"][0], event)

        home = values["home_win_probability"]
        away = values["away_win_probability"]
        assert home is not None and away is not None
        assert home + away < 0.8, "the stored pair must no longer fill the board"
        assert values["home_moneyline"] == -110
        assert values["away_moneyline"] == 320

    def test_the_draw_is_found_without_being_named(self):
        """Rename it and nothing changes — there is no vocabulary map."""
        named = _soccer_event(SOCCER_THREE_WAY)
        renamed = _soccer_event(
            [
                {"name": "Arsenal", "price": -110},
                {"name": "Chelsea", "price": 320},
                {"name": "Empate", "price": 270},
            ]
        )
        assert _parse_snapshot_values(
            named["bookmakers"][0], named
        ) == _parse_snapshot_values(renamed["bookmakers"][0], renamed)

    def test_a_book_omitting_the_draw_writes_no_probability(self):
        event = _soccer_event(SOCCER_TWO_WAY_FRAGMENT)
        values = _parse_snapshot_values(event["bookmakers"][0], event)

        assert values["home_win_probability"] is None
        assert values["away_win_probability"] is None
        # The raw prices are still recorded — the refusal is about the DERIVED
        # probability, not about discarding what the book said.
        assert values["home_moneyline"] == -110
        assert values["away_moneyline"] == 320

    def test_a_two_way_sport_payload_is_unchanged(self):
        event = {
            "home_team": "Kansas City Chiefs",
            "away_team": "Denver Broncos",
            "bookmakers": [
                {"key": "draftkings", "markets": [{"key": "h2h", "outcomes": NFL_TWO_WAY}]}
            ],
        }
        values = _parse_snapshot_values(event["bookmakers"][0], event)

        expected_home, expected_away = moneyline_to_probability(-150, 130)
        assert values["home_win_probability"] == round(expected_home, 4)
        assert values["away_win_probability"] == round(expected_away, 4)
        assert (
            values["home_win_probability"] + values["away_win_probability"]
            == pytest.approx(1.0, abs=1e-4)
        )

    def test_spreads_and_totals_are_untouched_by_the_h2h_change(self):
        """The other market arms must not have moved."""
        event = {
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "markets": [
                        {"key": "h2h", "outcomes": SOCCER_THREE_WAY},
                        {
                            "key": "spreads",
                            "outcomes": [
                                {"name": "Arsenal", "price": -110, "point": -0.5},
                                {"name": "Chelsea", "price": -110, "point": 0.5},
                            ],
                        },
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Over", "price": -105, "point": 2.5},
                                {"name": "Under", "price": -115, "point": 2.5},
                            ],
                        },
                    ],
                }
            ],
        }
        values = _parse_snapshot_values(event["bookmakers"][0], event)

        assert values["home_spread"] == -0.5
        assert values["over_under"] == 2.5
        assert values["over_odds"] == -105
        assert values["under_odds"] == -115
