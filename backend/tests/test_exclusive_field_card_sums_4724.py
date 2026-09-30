"""#4724 — a one-winner card on an event page never adds up to more than 100%.

THE SPECIMEN, read 2026-09-30 15:05Z. `/events/14780550`, Steelers @ Browns
(Thursday Night Football), 390px, production. Additional Markets drew

    Pittsburgh vs Cleveland: Race to 21 Points
      Pittsburgh      45%
      Neither team    35%
      Cleveland       27%      <- 107% for three outcomes, exactly one happens

Kalshi market `63152878` is stored `mutually_exclusive = true`; its legs served
through `/api/events/14780550/game-markets` are 0.445 / 0.35 / 0.27 (sum 1.065).
Every row value below is copied from that payload and the production
`futures_markets` / `futures_outcomes` rows read the same minute.

Controls are the cards that MUST NOT move: a Receptions field flagged not
one-winner (sum 21.9), a first-half/full-time field summing UNDER 1 (0.95), a
settled field with an unpriced loser, a two-leg market, a merged row, and an
overrounded "one-winner" field past `_FIELD_SUM_MAX`.
"""

from types import SimpleNamespace


from app.routes import events as events_route
from app.routes.events import _squeeze_exclusive_field_markets
from app.utils.outcome_display import _FIELD_SUM_MAX


def _market(market_id, name, *, mex):
    return SimpleNamespace(id=market_id, name=name, mutually_exclusive=mex, market_metadata={})


def _rows(market_id, name, legs):
    return [
        {"market_name": name, "outcome_name": outcome, "probability": p, "source": "kalshi",
         "_market_id": market_id}
        for outcome, p in legs
    ]


RACE_21 = "Pittsburgh vs Cleveland: Race to 21 Points"
RACE_21_LEGS = [("Pittsburgh", 0.445), ("Neither team", 0.35), ("Cleveland", 0.27)]
RACE_14 = "Pittsburgh vs Cleveland: Race to 14 Points"
RACE_14_LEGS = [("Pittsburgh", 0.515), ("Cleveland", 0.415), ("Neither team", 0.095)]
RACE_35 = "Pittsburgh vs Cleveland: Race to 35 Points"
RACE_35_LEGS = [("Neither team", 0.875), ("Pittsburgh", 0.065), ("Cleveland", 0.04)]
HTFT = "Pittsburgh vs Cleveland: 1st Half / Fulltime Result"


def _pct(p):
    """What the web and native rows print: a whole percent."""
    return int(p * 100 + 0.5)


class TestTheSpecimenCardAddsUp:
    def test_race_to_21_stops_printing_107(self):
        rows = _rows(63152878, RACE_21, RACE_21_LEGS)
        before = sum(_pct(r["probability"]) for r in rows)
        out = _squeeze_exclusive_field_markets(rows, [_market(63152878, RACE_21, mex=True)])

        assert before == 107  # the defect, as the reader added it
        assert abs(sum(r["probability"] for r in out) - 1.0) < 1e-3
        assert [_pct(r["probability"]) for r in out] == [42, 33, 25]

    def test_race_to_14_is_reached_too_though_the_shared_squeeze_would_leave_it(self):
        """1.025 sits under politics' 105% line, and printed 52 + 42 + 10 = 104."""
        rows = _rows(63152879, RACE_14, RACE_14_LEGS)
        out = _squeeze_exclusive_field_markets(rows, [_market(63152879, RACE_14, mex=True)])

        assert sum(_pct(r["probability"]) for r in rows) == 104
        assert sum(_pct(r["probability"]) for r in out) <= 101
        # Order and standing are what a reader ranks by; the squeeze never reorders.
        assert [r["outcome_name"] for r in out] == [r["outcome_name"] for r in rows]

    def test_every_leg_moves_down_never_up(self):
        rows = _rows(63152878, RACE_21, RACE_21_LEGS)
        out = _squeeze_exclusive_field_markets(rows, [_market(63152878, RACE_21, mex=True)])
        assert all(a["probability"] < b["probability"] for a, b in zip(out, rows))

    def test_rows_are_copied_not_mutated(self):
        rows = _rows(63152878, RACE_21, RACE_21_LEGS)
        _squeeze_exclusive_field_markets(rows, [_market(63152878, RACE_21, mex=True)])
        assert [r["probability"] for r in rows] == [0.445, 0.35, 0.27]

    def test_a_squeezed_card_leaves_its_neighbours_alone(self):
        rows = _rows(63152878, RACE_21, RACE_21_LEGS) + _rows(63152876, RACE_35, RACE_35_LEGS)
        markets = [_market(63152878, RACE_21, mex=True), _market(63152876, RACE_35, mex=True)]
        out = _squeeze_exclusive_field_markets(rows, markets)
        # Race to 35, same page, same minute, sums to 0.98 — nothing to take out.
        assert out[3:] == rows[3:]
        assert out[0]["probability"] < rows[0]["probability"]


class TestTheCardsThatMustNotMove:
    def test_a_field_not_declared_one_winner_keeps_its_raw_prices(self):
        """Receptions: 74 legs flagged False, summing 21.9 — many are true at once."""
        name = "Pittsburgh vs Cleveland: Receptions"
        rows = _rows(63152875, name, [("Pat Freiermuth: 4+", 0.40), ("Jaylen Warren: 3+", 0.44),
                                      ("Roman Wilson: 3+", 0.44)])
        out = _squeeze_exclusive_field_markets(rows, [_market(63152875, name, mex=False)])
        assert out == rows

    def test_a_one_winner_field_under_100_is_left_alone(self):
        rows = _rows(62733774, HTFT, [("PIT / PIT", 0.40), ("CLE / CLE", 0.30), ("Tie / PIT", 0.25)])
        out = _squeeze_exclusive_field_markets(rows, [_market(62733774, HTFT, mex=True)])
        assert out == rows

    def test_a_field_with_an_unpriced_leg_is_not_reasoned_about(self):
        """A settled market serves its losers as None (the row builder's `if prob else None`)."""
        legs = [("Pittsburgh", 1.0), ("Neither team", None), ("Cleveland", 0.08)]
        rows = _rows(63152878, RACE_21, legs)
        out = _squeeze_exclusive_field_markets(rows, [_market(63152878, RACE_21, mex=True)])
        assert out == rows

    def test_a_two_leg_market_is_not_touched(self):
        """`findWinProbMarkets` recognises the moneyline by its two legs' SUM."""
        name = "Pittsburgh vs Cleveland"
        rows = _rows(1, name, [("Pittsburgh", 0.58), ("Cleveland", 0.45)])
        out = _squeeze_exclusive_field_markets(rows, [_market(1, name, mex=True)])
        assert out == rows

    def test_a_field_past_the_overround_ceiling_stays_raw(self):
        name = "Field"
        p = (_FIELD_SUM_MAX + 0.3) / 3
        rows = _rows(2, name, [("A", p), ("B", p), ("C", p)])
        out = _squeeze_exclusive_field_markets(rows, [_market(2, name, mex=True)])
        assert out == rows

    def test_a_market_seen_through_a_merged_row_abstains(self):
        # Four legs, so three single-market legs remain once the merged one is set
        # aside — enough to be squeezed on their own if the abstention were lost.
        rows = _rows(63152878, RACE_21, RACE_21_LEGS + [("Tie", 0.05)])
        rows[3] = {**rows[3], "_market_ids": [63152878, 99]}
        out = _squeeze_exclusive_field_markets(rows, [_market(63152878, RACE_21, mex=True)])
        assert out == rows

    def test_a_mex_flag_that_is_not_literally_true_abstains(self):
        """A missing or None flag is not a declaration."""
        rows = _rows(63152878, RACE_21, RACE_21_LEGS)
        out = _squeeze_exclusive_field_markets(rows, [_market(63152878, RACE_21, mex=None)])
        assert out == rows


class TestTheRouteAppliesIt:
    def test_the_squeeze_runs_on_the_served_other_rows_after_the_partial_field_withhold(self):
        import inspect

        src = inspect.getsource(events_route)
        withhold = src.index("other_markets = _withhold_partial_field_markets(other_markets, markets)")
        squeeze = src.index("other_markets = _squeeze_exclusive_field_markets(other_markets, markets)")
        literal = src.index('"other": sorted(other_markets')
        assert withhold < squeeze < literal
