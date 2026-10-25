"""#9483 — a settled Game option carries its stored pregame pin, on its own.

PILLARS: TRUTH / FORMATTING. SHIP: a settled NBA card can show its genuinely
qualified pregame expectation beside its confirmed result, while missing
evidence stays explicitly unavailable.

``comparison`` (contract ``10238.v1``) refuses a settled option as
``not_quoted`` before it reads the pin, so the 82.5%-then-Lost story of
``/events/15320337`` (Over 206.5, outcome 240505185, market 63856441) had no
served baseline. ``pregame_reading`` is that same pin, admitted by the same
`pin_evidence` + the route's own `_pregame_mark_is_pregame`, read apart from
the current quote. The specimen ids below are shapes only: these cases prove
the producer rule, not that production holds a pin for that market.

Every decision function is the ROUTE'S OWN, as in the 10238 suite.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from app.routes import events as events_route
from app.utils.event_question_matrix import build_game_question_matrix
from tests.test_event_question_matrix_10238 import (
    KICKOFF,
    LATEST_AT,
    PIN_AT,
    _build_page,
    _clean_game_cache,  # noqa: F401 — the route class's fixture
    _facts,
    _grade,
    _leg,
    _nyy_team_total,
    _NYY_TT,
    _opt,
    _other,
    _pin,
    _q,
    _series,
    _series_leg,
    _series_row,
    _card,
    _SeriesMarket,
    _spread,
    _total,
)

MID, OVER_ID, UNDER_ID = 63856441, 240505185, 240505186
NBA_TOTAL = "Warriors at Clippers: Total Points"
COUNT_KEY = "q:count|points|game|full_game|ge:207"
UNAVAILABLE_FIELDS = {"probability": None, "observed_at": None, "basis": None, "outcome_id": None}
V1_OPTION_KEYS = {
    "option_key", "label", "side", "market_ids", "contributor_outcome_ids",
    "published", "source_evidence", "result", "comparison",
}


def _game(served, legs, facts, *, commence=KICKOFF, winners=None, observed=None,
          home="Los Angeles Clippers", away="Golden State Warriors", sport="basketball"):
    full = {k: [] for k in ("totals", "team_totals", "spreads", "period_markets", "matchups", "other")}
    full.update(served)
    observed = observed if observed is not None else {leg.id: LATEST_AT for leg in legs}
    return build_game_question_matrix(
        served=full,
        outcomes=list(legs),
        market_facts=facts,
        observed=lambda leg: observed.get(leg.id),
        markets_with_a_winner=(
            winners if winners is not None
            else {leg.market_id for leg in legs if leg.is_winner is True}
        ),
        verdict_is_provable=events_route._verdict_is_provable,
        is_pregame=events_route._pregame_mark_is_pregame,
        period_from_ticker=events_route._extract_period_from_ticker,
        period_from_name=events_route._extract_period_from_name,
        row_market_ids=events_route._row_market_ids,
        sport_prefix=sport,
        home_team=home,
        away_team=away,
        commence_time=commence,
    )


def _settled_over(meta, *, commence=KICKOFF, leg_name="Over 206.5", raw=0.0):
    """The specimen's shape: a Kalshi full-game Over 206.5, graded Lost on a
    resolved market, its stored leg at the settlement 0.0."""
    legs = [_leg(OVER_ID, MID, leg_name, raw, is_winner=False)]
    row = _total(MID, OVER_ID, leg_name, 206.5, None, market_name=NBA_TOTAL,
                 **_grade(False, "api_settlement"))
    m = _game({"totals": [row]}, legs, {MID: _facts(NBA_TOTAL, status="resolved", meta=meta)},
              commence=commence, winners={MID})
    return _opt(_q(m, COUNT_KEY), f"o:{OVER_ID}")


def _unavailable(reason):
    return {"state": "unavailable", "reason": reason, **UNAVAILABLE_FIELDS}


class TestSettledOptionCarriesItsQualifiedPin:
    def test_a_qualified_pin_reads_beside_the_lost_result(self):
        opt = _settled_over(_pin(OVER_ID, 0.825))
        assert opt["pregame_reading"] == {
            "state": "available", "reason": None, "probability": 0.825,
            "observed_at": PIN_AT, "basis": "pregame_pin", "outcome_id": OVER_ID,
        }
        # The result and the historical chance are separate facts: neither is
        # rewritten, and the settled 0.0 is never the chance.
        assert opt["result"] == {"state": "lost", "evidence_kind": "verdict_is_provable"}
        assert opt["published"]["value"] is None
        assert opt["published"]["value_state"] == "result"
        assert opt["source_evidence"][0]["raw_probability"] == 0.0
        # The current comparison refusal is unchanged.
        assert opt["comparison"] == {"state": "unavailable", "reason": "not_quoted",
                                     "baseline": None, "latest": None, "delta_points": None}

    def test_a_won_option_reads_its_pin_not_its_settlement_one(self):
        legs = [_leg(OVER_ID, MID, "Over 206.5", 1.0, is_winner=True)]
        row = _total(MID, OVER_ID, "Over 206.5", 206.5, None, market_name=NBA_TOTAL,
                     **_grade(True, "api_settlement"))
        m = _game({"totals": [row]}, legs,
                  {MID: _facts(NBA_TOTAL, status="resolved", meta=_pin(OVER_ID, 0.31))})
        opt = _opt(_q(m, COUNT_KEY), f"o:{OVER_ID}")
        assert opt["result"]["state"] == "won"
        assert opt["pregame_reading"]["probability"] == 0.31

    def test_no_pin_is_unavailable_never_the_settled_zero(self):
        opt = _settled_over(None)
        assert opt["pregame_reading"] == _unavailable("no_pregame_pin")
        assert opt["result"]["state"] == "lost"

    def test_a_pin_for_the_sibling_outcome_is_not_this_options(self):
        opt = _settled_over(_pin(UNDER_ID, 0.175))
        assert opt["pregame_reading"] == _unavailable("no_pregame_pin")


class TestPregameTimeQualification:
    def test_a_pin_written_after_the_start_is_refused(self):
        late = (KICKOFF + timedelta(minutes=12)).isoformat()
        opt = _settled_over(_pin(OVER_ID, 0.825, observed=late, captured=late))
        assert opt["pregame_reading"] == _unavailable("baseline_basis_opening_line")

    def test_a_pin_written_exactly_at_the_start_is_still_pregame(self):
        # The route's own rule: observed_at <= commence. Pinned, not re-derived.
        at = KICKOFF.isoformat()
        opt = _settled_over(_pin(OVER_ID, 0.825, observed=at, captured=at))
        assert opt["pregame_reading"]["state"] == "available"

    def test_an_event_moved_earlier_than_the_pin_is_refused(self):
        opt = _settled_over(_pin(OVER_ID, 0.825), commence=KICKOFF - timedelta(hours=2))
        assert opt["pregame_reading"] == _unavailable("baseline_basis_opening_line")

    def test_a_legacy_pin_without_its_own_write_clock_is_refused(self):
        meta = {"pregame_mark": {"outcomes": {str(OVER_ID): 0.825}, "captured_at": PIN_AT}}
        opt = _settled_over(meta)
        assert opt["pregame_reading"] == _unavailable("baseline_clock_unknown")

    def test_no_start_time_anywhere_is_ambiguous_and_refused(self):
        # `_pregame_mark_is_pregame` admits a pin it cannot judge; a reading does not.
        assert events_route._pregame_mark_is_pregame(_pin(OVER_ID, 0.825)["pregame_mark"], None)
        opt = _settled_over(_pin(OVER_ID, 0.825), commence=None)
        assert opt["pregame_reading"] == _unavailable("start_time_unknown")

    def test_the_pins_own_start_judges_it_when_the_event_carries_none(self):
        meta = _pin(OVER_ID, 0.825)
        meta["pregame_mark"]["commence_time"] = KICKOFF.isoformat()
        opt = _settled_over(meta, commence=None)
        assert opt["pregame_reading"]["state"] == "available"


class TestSettlementValuesAreNotChances:
    @pytest.mark.parametrize("value", [0.0, 1.0, 0, 1])
    def test_a_terminal_pin_is_refused(self, value):
        opt = _settled_over(_pin(OVER_ID, value))
        assert opt["pregame_reading"] == _unavailable("pin_is_settlement_value")

    @pytest.mark.parametrize("value", [0.001, 0.999])
    def test_a_near_terminal_pin_is_a_chance(self, value):
        assert _settled_over(_pin(OVER_ID, value))["pregame_reading"]["probability"] == value

    @pytest.mark.parametrize("value", [True, "x", 1.2, -0.1, float("nan"), None])
    def test_an_unreadable_pin_value_is_no_pin(self, value):
        assert _settled_over(_pin(OVER_ID, value))["pregame_reading"] == _unavailable("no_pregame_pin")


class TestSideAndPeriodAreTheContributorsOwn:
    def test_an_under_leg_on_the_over_axis_is_never_complemented(self):
        opt = _settled_over(_pin(OVER_ID, 0.175), leg_name="Under 206.5")
        assert opt["label"] == "Over 206.5" and opt["side"] == "over"
        assert opt["pregame_reading"] == _unavailable("leg_is_complement")

    def test_a_spread_side_reads_only_its_own_legs_pin(self):
        legs = [_leg(1, 10, "Los Angeles Clippers -3.5", 0.0, is_winner=False),
                _leg(2, 10, "Golden State Warriors +3.5", 1.0, is_winner=True)]
        rows = [_spread(10, 1, "Los Angeles Clippers -3.5", 3.5, None, **_grade(False, "api_settlement")),
                _spread(10, 2, "Golden State Warriors +3.5", 3.5, None, **_grade(True, "api_settlement"))]
        m = _game({"spreads": rows}, legs,
                  {10: _facts("Warriors at Clippers: Spread", status="resolved", meta=_pin(2, 0.44))})
        home = _opt(_q(m, "q:handicap|points|home|full_game|-3.5"), "o:1")
        away = _opt(_q(m, "q:handicap|points|away|full_game|+3.5"), "o:2")
        assert home["pregame_reading"] == _unavailable("no_pregame_pin")
        assert (away["side"], away["pregame_reading"]["probability"]) == ("away", 0.44)
        assert away["pregame_reading"]["outcome_id"] == 2

    def test_another_periods_market_holding_the_outcome_id_is_not_read(self):
        # The pin is read from the contributor's OWN market only; a first-half
        # market's metadata naming the same id never reaches the full-game option.
        legs = [_leg(OVER_ID, MID, "Over 206.5", 0.0, is_winner=False)]
        row = _total(MID, OVER_ID, "Over 206.5", 206.5, None, market_name=NBA_TOTAL,
                     **_grade(False, "api_settlement"))
        facts = {MID: _facts(NBA_TOTAL, status="resolved"),
                 MID + 1: _facts("Warriors at Clippers: 1st Half Total", meta=_pin(OVER_ID, 0.6))}
        m = _game({"totals": [row]}, legs, facts, winners={MID})
        opt = _opt(_q(m, COUNT_KEY), f"o:{OVER_ID}")
        assert opt["pregame_reading"] == _unavailable("no_pregame_pin")


class TestMultiContributorEvidenceIsNeverBlended:
    def test_one_row_with_two_contributors_is_refused_though_both_carry_pins(self):
        legs = [_leg(1, 10, "Yes", 0.5), _leg(2, 11, "Yes", 0.6)]
        row = _other(10, 1, "Yes", 0.55)
        row["contributor_outcome_ids"], row["_market_ids"] = [1, 2], [10, 11]
        m = _game({"other": [row]}, legs,
                  {10: _facts("Q", meta=_pin(1, 0.3)), 11: _facts("Q", meta=_pin(2, 0.4))})
        (opt,) = [o for q in m["questions"] for o in q["options"]]
        assert opt["pregame_reading"] == _unavailable("multiple_contributors")
        assert "0.35" not in json.dumps(opt["pregame_reading"])

    def test_a_settled_total_axis_fold_is_refused(self):
        legs = [_leg(240500335, 63854826, "Under", 1.0, is_winner=True),
                _leg(240500334, 63854826, "Over", 0.0, is_winner=False)]
        rows = _nyy_team_total(_grade(True, "api_settlement"), _grade(False, "api_settlement"))
        meta = {"pregame_mark": {"outcomes": {"240500334": 0.4, "240500335": 0.6},
                                 "observed_at": PIN_AT, "captured_at": PIN_AT}}
        m = _game({"team_totals": rows}, legs, {63854826: _facts(_NYY_TT, status="resolved", meta=meta)},
                  home="Tampa Bay Rays", away="New York Yankees", sport="baseball")
        (opt,) = _q(m, "m:63854826")["options"]
        assert opt["published"]["value_state"] == "result"
        assert opt["pregame_reading"] == _unavailable("multiple_contributors")

    def test_unblended_equivalents_are_refused(self):
        legs = [_leg(1, 10, "Over 4.5", 0.55), _leg(2, 10, "Under 4.5", 0.40)]
        rows = [_total(10, 1, "Over 4.5", 4.5, 0.55, market_type="team_total"),
                _total(10, 2, "Under 4.5", 4.5, 0.60, market_type="team_total")]
        for r in rows:
            r["team_side"], r["team_name"] = "home", "Boston Red Sox"
        m = _game({"team_totals": rows}, legs, {10: _facts("Red Sox Team Total Runs", meta=_pin(1, 0.5))},
                  home="Boston Red Sox", away="New York Yankees", sport="baseball")
        (opt,) = _q(m, "q:count|runs|home|full_game|ge:5")["options"]
        assert opt["published"]["value_state"] == "unblended_equivalents"
        assert opt["pregame_reading"] == _unavailable("multiple_contributors")


class TestOnlyAdmittedOptionsCarryAReading:
    def test_a_row_the_route_declined_is_refused_with_its_comparison_unchanged(self):
        legs = [_leg(OVER_ID, MID, "Over 206.5", 0.62)]
        row = _total(MID, OVER_ID, "Over 206.5", 206.5, None, market_name=NBA_TOTAL)
        m = _game({"totals": [row]}, legs, {MID: _facts(NBA_TOTAL, meta=_pin(OVER_ID, 0.825))})
        opt = _opt(_q(m, COUNT_KEY), f"o:{OVER_ID}")
        assert opt["published"]["value_state"] == "refused"
        assert opt["pregame_reading"] == _unavailable("option_not_admitted")
        assert opt["comparison"]["reason"] == "not_quoted"

    def test_an_unpriced_open_option_is_refused(self):
        legs = [_leg(OVER_ID, MID, "Over 206.5", None)]
        row = _total(MID, OVER_ID, "Over 206.5", 206.5, None, market_name=NBA_TOTAL)
        m = _game({"totals": [row]}, legs, {MID: _facts(NBA_TOTAL, meta=_pin(OVER_ID, 0.825))})
        opt = _opt(_q(m, COUNT_KEY), f"o:{OVER_ID}")
        assert opt["published"]["value_state"] == "unpriced"
        assert opt["pregame_reading"] == _unavailable("option_not_admitted")

    def test_a_contributor_whose_leg_was_not_loaded_is_refused(self):
        row = _total(MID, OVER_ID, "Over 206.5", 206.5, 0.62, market_name=NBA_TOTAL)
        m = _game({"totals": [row]}, [], {MID: _facts(NBA_TOTAL, meta=_pin(OVER_ID, 0.825))})
        opt = _opt(_q(m, COUNT_KEY), f"o:{OVER_ID}")
        assert opt["published"]["value_state"] == "quoted"
        assert opt["pregame_reading"] == _unavailable("contributor_not_loaded")

    def test_a_quoted_option_reads_the_same_pin_its_comparison_does(self):
        legs = [_leg(OVER_ID, MID, "Over 206.5", 0.62)]
        row = _total(MID, OVER_ID, "Over 206.5", 206.5, 0.62, market_name=NBA_TOTAL)
        m = _game({"totals": [row]}, legs, {MID: _facts(NBA_TOTAL, meta=_pin(OVER_ID, 0.825))})
        opt = _opt(_q(m, COUNT_KEY), f"o:{OVER_ID}")
        assert opt["comparison"]["state"] == "comparable"
        assert opt["comparison"]["delta_points"] == -20.5
        baseline = opt["comparison"]["baseline"]
        reading = opt["pregame_reading"]
        assert (reading["probability"], reading["observed_at"], reading["basis"]) == (
            baseline["probability"], baseline["observed_at"], baseline["basis"])

    def test_a_reading_survives_where_the_comparison_refuses_on_the_current_clock(self):
        # The comparison needs a dated current quote; the reading does not read one.
        legs = [_leg(OVER_ID, MID, "Over 206.5", 0.62)]
        row = _total(MID, OVER_ID, "Over 206.5", 206.5, 0.62, market_name=NBA_TOTAL)
        m = _game({"totals": [row]}, legs, {MID: _facts(NBA_TOTAL, meta=_pin(OVER_ID, 0.825))},
                  observed={OVER_ID: None})
        opt = _opt(_q(m, COUNT_KEY), f"o:{OVER_ID}")
        assert opt["comparison"]["reason"] == "current_clock_unknown"
        assert opt["pregame_reading"]["probability"] == 0.825

    def test_the_rows_opening_and_movement_fields_are_never_a_reading(self):
        legs = [_leg(OVER_ID, MID, "Over 206.5", 0.0, is_winner=False)]
        row = _total(MID, OVER_ID, "Over 206.5", 206.5, None, market_name=NBA_TOTAL,
                     **_grade(False, "api_settlement"))
        row.update(opening_probability=0.8, movement={"from": 0.8, "to": 0.0}, pregame_probability=0.8)
        m = _game({"totals": [row]}, legs, {MID: _facts(NBA_TOTAL, status="resolved")}, winners={MID})
        opt = _opt(_q(m, COUNT_KEY), f"o:{OVER_ID}")
        assert opt["pregame_reading"] == _unavailable("no_pregame_pin")


class TestLegacyConsumers:
    def test_every_game_option_gains_exactly_one_key(self):
        legs = [_leg(OVER_ID, MID, "Over 206.5", 0.62), _leg(1, 10, "Yes", 0.5), _leg(2, 11, "Yes", 0.6)]
        multi = _other(10, 1, "Yes", 0.55)
        multi["contributor_outcome_ids"], multi["_market_ids"] = [1, 2], [10, 11]
        m = _game({"totals": [_total(MID, OVER_ID, "Over 206.5", 206.5, 0.62, market_name=NBA_TOTAL)],
                   "other": [multi]}, legs,
                  {MID: _facts(NBA_TOTAL), 10: _facts("Q"), 11: _facts("Q")})
        options = [o for q in m["questions"] for o in q["options"]]
        assert len(options) == 2
        for opt in options:
            assert set(opt) == V1_OPTION_KEYS | {"pregame_reading"}
            assert set(opt["pregame_reading"]) == {
                "state", "reason", "probability", "observed_at", "basis", "outcome_id"}
        assert m["contract"] == "10238.v1"

    def test_series_options_do_not_carry_it(self):
        market = _SeriesMarket(71008, "Alpha vs Beta win series", mutually_exclusive=True,
                               meta=_pin(72016, 0.4))
        legs = {71008: [_series_leg(72016, market, "Alpha", 0.70),
                        _series_leg(72017, market, "Beta", 0.29)]}
        card = _card(market, [_series_row(72016, "Alpha", 0.70), _series_row(72017, "Beta", 0.29)])
        m = _series([card], legs)
        assert m is not None
        assert all("pregame_reading" not in o for q in m["questions"] for o in q["options"])


@pytest.mark.usefixtures("_clean_game_cache")
class TestGameMarketsRoute:
    def test_the_route_pin_reaches_the_reading_on_the_served_json(self):
        response, _ = _build_page()
        matrix = json.loads(json.dumps(response["game_question_matrix"], default=str))
        spread = _q(matrix, "q:handicap|points|home|full_game|-3.5")["options"][0]
        assert spread["pregame_reading"] == {
            "state": "available", "reason": None, "probability": 0.40,
            "observed_at": "2026-05-17T22:00:00+00:00", "basis": "pregame_pin", "outcome_id": 3,
        }
        under = _q(matrix, "q:count|points|game|full_game|ge:211")["options"][0]
        assert under["pregame_reading"]["reason"] == "leg_is_complement"
        for q in matrix["questions"]:
            for opt in q["options"]:
                assert set(opt) == V1_OPTION_KEYS | {"pregame_reading"}

    def test_no_legacy_served_row_gains_a_pregame_field(self):
        response, _ = _build_page()
        for key in ("totals", "team_totals", "spreads", "period_markets", "other"):
            for row in response.get(key) or []:
                assert "pregame_reading" not in row
