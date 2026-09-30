"""#9901 — a one-winner series card on an event page never adds up past 100%.

THE SPECIMEN, read 2026-09-30 18:00Z. `/events/15320289`, Phillies v Braves,
Wild Card Game 1, final (Atlanta won), 390px, production. Bigger Picture drew

    Series Exact Score: Philadelphia vs Atlanta
      ATL wins 2-0    49%
      ATL wins 2-1    30%
      PHI wins 2-1    27%
      PHI wins 2-0    ---      <- 106% for four outcomes, exactly one happens

Kalshi market `62898792` (KXMLBSERIESSCORE-26PHIATLWC) is stored
`mutually_exclusive = true`, `status = 'open'`. Its outcomes read the same minute:
0.485 (48/49), 0.295 (28/31), 0.265 (26/27) and PHI 2-0 at 0 with
`is_winner = False`. `/api/events/15320289/related-futures` served
`series_markets[0]` as 0.485 / 0.295 / 0.27 / None.

Controls are the cards that MUST NOT move: the two-leg Series Winner (74/27),
a field under 100%, a leg that is unpriced but NOT graded lost, a market not
declared one-winner, a card truncated to its top ten, and a field past the
overround ceiling.
"""

import inspect

from app.routes import events as events_route
from app.routes.events import _squeeze_exclusive_series_outcomes
from app.utils.outcome_display import _FIELD_SUM_MAX

# (outcome_id, name, served probability) — PHI 2-0 is None: stored 0, graded lost.
SPECIMEN = [
    (1, "ATL wins 2-0", 0.485),
    (2, "ATL wins 2-1", 0.295),
    (3, "PHI wins 2-1", 0.27),
    (4, "PHI wins 2-0", None),
]
DECIDED_LOST = {4}


def _card(legs):
    return [
        {"outcome_id": oid, "name": name, "probability": p, "probability_change_24h": None}
        for oid, name, p in legs
    ]


def _squeeze(legs, *, exclusive=True, decided_lost=DECIDED_LOST, whole_market=True):
    return _squeeze_exclusive_series_outcomes(
        _card(legs), exclusive=exclusive, decided_lost=decided_lost, whole_market=whole_market
    )


def _pct(p):
    """What the web and native rows print: a whole percent (`Math.round(p * 100)`)."""
    return int(p * 100 + 0.5)


def _printed_sum(card):
    return sum(_pct(o["probability"]) for o in card if o["probability"] is not None)


class TestTheSpecimenCardAddsUp:
    def test_series_exact_score_stops_printing_106(self):
        assert _printed_sum(_card(SPECIMEN)) == 106
        out = _squeeze(SPECIMEN)
        assert _printed_sum(out) <= 100
        assert [_pct(o["probability"]) for o in out[:3]] == [46, 28, 26]

    def test_the_decided_leg_keeps_printing_its_dash(self):
        out = _squeeze(SPECIMEN)
        assert out[3]["probability"] is None
        assert out[3]["name"] == "PHI wins 2-0"

    def test_every_priced_leg_moves_down_never_up_and_keeps_its_order(self):
        out = _squeeze(SPECIMEN)
        for before, after in zip(SPECIMEN[:3], out[:3]):
            assert after["probability"] < before[2]
        probs = [o["probability"] for o in out[:3]]
        assert probs == sorted(probs, reverse=True)

    def test_entries_are_copied_not_mutated(self):
        card = _card(SPECIMEN)
        _squeeze_exclusive_series_outcomes(card, exclusive=True, decided_lost=DECIDED_LOST, whole_market=True)
        assert [o["probability"] for o in card] == [0.485, 0.295, 0.27, None]

    def test_a_fully_priced_field_is_reached_too(self):
        legs = [(1, "A 3-0", 0.30), (2, "A 3-1", 0.30), (3, "B 3-1", 0.25), (4, "B 3-0", 0.20)]
        out = _squeeze(legs, decided_lost=set())
        assert abs(sum(o["probability"] for o in out) - 1.0) < 1e-3


class TestTheCardsThatMustNotMove:
    def test_a_two_leg_series_winner_is_not_touched(self):
        legs = [(1, "Atlanta", 0.74), (2, "Philadelphia", 0.27)]
        assert _squeeze(legs, decided_lost=set()) == _card(legs)

    def test_a_field_under_100_is_left_alone(self):
        legs = [(1, "ATL wins 2-0", 0.45), (2, "ATL wins 2-1", 0.28), (3, "PHI wins 2-1", 0.25), (4, "PHI wins 2-0", None)]
        assert _squeeze(legs) == _card(legs)

    def test_an_unpriced_leg_that_is_not_graded_lost_abstains(self):
        # A refused or untraded leg is an unknown price, not a known 0.
        assert _squeeze(SPECIMEN, decided_lost=set()) == _card(SPECIMEN)

    def test_a_market_not_declared_one_winner_keeps_its_raw_prices(self):
        assert _squeeze(SPECIMEN, exclusive=False) == _card(SPECIMEN)

    def test_a_flag_that_is_not_literally_true_abstains(self):
        assert _squeeze(SPECIMEN, exclusive=None) == _card(SPECIMEN)
        assert _squeeze(SPECIMEN, exclusive="true") == _card(SPECIMEN)

    def test_a_card_truncated_to_its_top_ten_abstains(self):
        assert _squeeze(SPECIMEN, whole_market=False) == _card(SPECIMEN)

    def test_a_field_past_the_overround_ceiling_stays_raw(self):
        legs = [(1, "a", 0.60), (2, "b", 0.60), (3, "c", _FIELD_SUM_MAX - 1.0 + 0.01)]
        assert _squeeze(legs, decided_lost=set()) == _card(legs)

    def test_a_settled_card_with_one_winner_is_not_touched(self):
        legs = [(1, "ATL wins 2-0", 1.0), (2, "ATL wins 2-1", None), (3, "PHI wins 2-1", None), (4, "PHI wins 2-0", None)]
        assert _squeeze(legs, decided_lost={2, 3, 4}) == _card(legs)


class TestTheRouteAppliesIt:
    def test_the_series_builder_squeezes_before_it_appends_and_relabels(self):
        src = inspect.getsource(events_route)
        squeeze = src.index("top_outcomes = _squeeze_exclusive_series_outcomes(")
        append = src.index("formatted_series.append({", squeeze - 4000)
        relabel = src.index("relabel_series_card(\n", squeeze)
        assert squeeze < append < relabel

    def test_the_route_grades_decided_legs_from_is_winner_false_and_whole_market_from_the_cap(self):
        src = inspect.getsource(events_route)
        call = src[src.index("top_outcomes = _squeeze_exclusive_series_outcomes("):][:600]
        assert "so.is_winner is False" in call
        assert "len(outcomes_list) <= 10" in call
        assert 'getattr(mkt, "mutually_exclusive", None)' in call
