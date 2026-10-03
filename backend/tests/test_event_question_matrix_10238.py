"""#10238 → #10312 — the Game / Series question matrix (contract ``10238.v1``).

PILLARS: MATCHING / FORMATTING / TRUTH. SHIP (#10238): readers browse Game and
Series questions with their real sides, units, periods and source evidence;
finishing a Game does not finish an open Series.

The producer is ``app/utils/event_question_matrix.py``. These cases are the
contract's ten synthetic specifications (``GAME-SERIES-ADAPTER-CASES.md`` /
``game-series-fixture-specs.json``) made into real tests, plus every producer
gate §10 and the riders R1–R6 name. The route classes at the bottom prove the
two additive keys on the SERVED JSON and every legacy key byte-identical.

Every decision function handed to the builder here is the ROUTE'S OWN
(`_verdict_is_provable`, `_pregame_mark_is_pregame`, the period extractors,
`_row_market_ids`) — never a stub — so a case cannot pass on a decision the
route would not make.
"""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import events as events_route
from app.utils.event_question_matrix import (
    CONTRACT,
    build_game_question_matrix,
    build_series_question_matrix,
)

_game_markets_cache = events_route._game_markets_cache

BACKEND = Path(__file__).resolve().parents[1]
KICKOFF = datetime(2026, 10, 2, 19, 0, tzinfo=timezone.utc)
PIN_AT = "2026-10-02T18:00:00+00:00"
LATEST_AT = "2026-10-02T20:00:00+00:00"


# ── fixtures in the route's own row shapes ──────────────────────────────────


def _leg(id, market_id, name, prob, is_winner=None):
    return SimpleNamespace(
        id=id, market_id=market_id, name=name, current_probability=prob, is_winner=is_winner,
    )


def _facts(name, *, status="open", external_id=None, mutually_exclusive=None, meta=None):
    return {
        "name": name,
        "external_id": external_id,
        "status": status,
        "mutually_exclusive": mutually_exclusive,
        "market_metadata": meta,
    }


def _grade(is_winner=None, resolution_source=None):
    return {"is_winner": is_winner, "resolution_source": resolution_source}


def _other(mid, oid, name, prob, *, market_name="M", source="kalshi", observed=LATEST_AT, **grade):
    return {
        "market_name": market_name, "outcome_name": name, "observed_at": observed,
        "contributor_outcome_ids": [oid], "probability": prob, "source": source,
        **_grade(**grade), "_market_id": mid,
    }


def _total(mid, oid, name, threshold, over, *, market_type="game_total", period=None,
           market_name="Total", source="kalshi", observed=LATEST_AT, **grade):
    return {
        "threshold": threshold, "over_probability": over, "source": source,
        "market_type": market_type, "market_name": market_name, "outcome_name": name,
        "observed_at": observed, "contributor_outcome_ids": [oid], **_grade(**grade),
        "movement": None, "period": period, "_market_id": mid, "_external_id": None,
    }


def _spread(mid, oid, name, threshold, prob, *, market_name="Spread", source="kalshi",
            observed=LATEST_AT, **grade):
    return {
        "market_name": market_name, "outcome_name": name, "observed_at": observed,
        "contributor_outcome_ids": [oid], "threshold": threshold, "probability": prob,
        "source": source, **_grade(**grade), "_market_id": mid,
    }


def _period_row(mid, oid, name, threshold, prob, *, market_type, period, market_name="Period",
                observed=LATEST_AT, **grade):
    return {
        "market_name": market_name, "outcome_name": name, "observed_at": observed,
        "contributor_outcome_ids": [oid], "threshold": threshold, "probability": prob,
        "source": "kalshi", "market_type": market_type, "period": period, **_grade(**grade),
        "_market_id": mid,
    }


def _matchup(mid, legs, *, type="h2h", market_name="Matchup", source="kalshi"):
    outcomes = [
        {"name": name, "probability": prob, "observed_at": observed,
         "contributor_outcome_ids": [oid], **_grade()}
        for oid, name, prob, observed in legs
    ]
    return {
        "market_name": market_name, "type": type, "source": source, "outcomes": outcomes,
        "contributor_outcome_ids": sorted(oid for oid, *_ in legs), "_market_id": mid,
    }


def _game(served=None, legs=(), facts=None, *, observed=None, sport="baseball",
          home="Boston Red Sox", away="New York Yankees", winners=None):
    legs = list(legs)
    observed = observed if observed is not None else {leg.id: LATEST_AT for leg in legs}
    full = {k: [] for k in ("totals", "team_totals", "spreads", "period_markets", "matchups", "other")}
    full.update(served or {})
    return build_game_question_matrix(
        served=full,
        outcomes=legs,
        market_facts=facts or {},
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
        commence_time=KICKOFF,
    )


def _q(matrix, key):
    found = [q for q in matrix["questions"] if q["question_key"] == key]
    assert len(found) == 1, [q["question_key"] for q in matrix["questions"]]
    return found[0]


def _opt(question, key):
    found = [o for o in question["options"] if o["option_key"] == key]
    assert len(found) == 1, [o["option_key"] for o in question["options"]]
    return found[0]


def _pin(outcome_id, value, *, observed=PIN_AT, captured=PIN_AT):
    return {"pregame_mark": {
        "outcomes": {str(outcome_id): value}, "observed_at": observed, "captured_at": captured,
    }}


class _SeriesMarket:
    """A loaded Series market: plain attributes, `market_metadata` in `__dict__`."""

    def __init__(self, id, name, *, status="open", mutually_exclusive=None, meta=None):
        self.id, self.name, self.status = id, name, status
        self.mutually_exclusive = mutually_exclusive
        self.market_metadata = meta


def _series(cards, legs_by_market, *, withheld=(), settled_before=lambda m: False,
            home="Alpha", away="Beta"):
    return build_series_question_matrix(
        formatted_series=cards,
        series_by_market=legs_by_market,
        series_withheld=set(withheld),
        settled_before_the_game=settled_before,
        home_team=home,
        away_team=away,
    )


def _series_leg(id, market, name, prob, is_winner=None):
    leg = _leg(id, market.id, name, prob, is_winner)
    leg.market = market
    return leg


def _series_row(oid, name, prob, *, settled=False, is_winner=None, change=0.05):
    return {"outcome_id": oid, "name": name, "probability": prob,
            "probability_change_24h": change, "settled": settled, "is_winner": is_winner}


def _card(market, rows, *, source="kalshi"):
    return {"market_id": market.id, "market_name": market.name, "source": source,
            "status": market.status, "resolution_date": "2026-10-08T00:00:00+00:00",
            "outcomes": rows}


# ── the ten synthetic cases, made real ──────────────────────────────────────


class TestBinaryNamedNoInvention:
    def _matrix(self, beta_served=True):
        legs = [_leg(72001, 71001, "Alpha", 0.62), _leg(72002, 71001, "Beta", 0.38 if beta_served else None)]
        rows = [(72001, "Alpha", 0.62, LATEST_AT)]
        if beta_served:
            rows.append((72002, "Beta", 0.38, LATEST_AT))
        return _game(
            {"matchups": [_matchup(71001, rows, market_name="Alpha vs Beta winner")]},
            legs, {71001: _facts("Alpha vs Beta winner")}, home="Gamma", away="Delta",
        )

    def test_both_named_options_publish_their_own_display_and_identity(self):
        q = _q(self._matrix(), "m:71001")
        assert q["kind"] == "named_options" and q["label"] == "Alpha vs Beta winner"
        alpha = _opt(q, "o:72001")
        assert alpha["published"] == {
            "value": 0.62, "value_state": "quoted", "basis": "published_source_display",
            "source": "kalshi", "observed_at": LATEST_AT,
        }
        assert (alpha["market_ids"], alpha["contributor_outcome_ids"]) == ([71001], [72001])

    def test_unresolved_names_are_contenders_never_guessed_home_away(self):
        q = _q(self._matrix(), "m:71001")
        assert {o["side"] for o in q["options"]} == {"contender"}

    def test_no_pin_means_no_comparison(self):
        alpha = _opt(_q(self._matrix(), "m:71001"), "o:72001")
        assert alpha["comparison"]["reason"] == "no_pregame_pin"
        assert alpha["comparison"]["latest"] is None and alpha["comparison"]["delta_points"] is None

    def test_an_unpriced_beta_is_missing_never_one_minus_alpha(self):
        q = _q(self._matrix(beta_served=False), "m:71001")
        assert [o["option_key"] for o in q["options"]] == ["o:72001"]
        assert q["missing_options"] == [{
            "option_key": "o:72002", "outcome_id": 72002, "label": "Beta",
            "side": None, "value_state": "unpriced",
        }]
        assert q["complete"] is False
        assert "0.38" not in json.dumps(q)


class TestSoccerThreeProvenSides:
    def _matrix(self, names=("Gwangju", "Draw", "FC Anyang"), exclusive=True):
        legs = [_leg(72003, 71002, names[0], 0.40), _leg(72004, 71002, names[1], 0.30),
                _leg(72005, 71002, names[2], 0.30)]
        rows = [_other(71002, leg.id, leg.name, leg.current_probability, source="polymarket")
                for leg in legs]
        return _game({"other": rows}, legs,
                     {71002: _facts("Gwangju vs FC Anyang", mutually_exclusive=exclusive)},
                     sport="soccer", home="Gwangju FC", away="FC Anyang")

    def test_one_exclusive_market_of_three_proven_legs_is_home_draw_away_and_complete(self):
        q = _q(self._matrix(), "m:71002")
        assert {o["option_key"]: o["side"] for o in q["options"]} == {
            "o:72003": "home", "o:72004": "draw", "o:72005": "away",
        }
        assert q["complete"] is True
        assert q["option_counts"] == {"declared": None, "loaded": 3, "returned": 3, "missing_identified": 0}

    def test_home_and_away_strings_that_resolve_to_no_team_stay_category(self):
        q = _q(self._matrix(names=("Home", "Draw", "Away")), "m:71002")
        assert {o["side"] for o in q["options"]} == {"category"}
        assert q["complete"] is None

    def test_a_market_not_declared_exclusive_proves_no_three_way(self):
        q = _q(self._matrix(exclusive=None), "m:71002")
        assert {o["side"] for o in q["options"]} == {"category"}


class TestSoccerMissingAway:
    def test_the_loaded_away_leg_is_missing_by_identity_and_nothing_is_normalised(self):
        legs = [_leg(72006, 71003, "Gwangju", 0.40), _leg(72007, 71003, "Draw", 0.20),
                _leg(72008, 71003, "FC Anyang", 0.35)]
        rows = [_other(71003, 72006, "Gwangju", 0.40, observed=None),
                _other(71003, 72007, "Draw", 0.20, observed=None)]
        m = _game({"other": rows}, legs,
                  {71003: _facts("Gwangju vs FC Anyang", mutually_exclusive=True)},
                  observed={}, sport="soccer", home="Gwangju FC", away="FC Anyang")
        q = _q(m, "m:71003")
        home = _opt(q, "o:72006")
        assert home["published"]["value"] == 0.40 and home["published"]["observed_at"] is None
        assert home["side"] == "home" and _opt(q, "o:72007")["side"] == "draw"
        assert q["missing_options"] == [{
            "option_key": "o:72008", "outcome_id": 72008, "label": "FC Anyang",
            "side": "away", "value_state": "unavailable",
        }]
        assert q["complete"] is False
        assert all(o["result"]["state"] == "open" for o in q["options"])

    def test_with_only_two_legs_loaded_there_is_no_away_identity_and_no_three_way(self):
        legs = [_leg(72006, 71003, "Gwangju", 0.40), _leg(72007, 71003, "Draw", 0.20)]
        rows = [_other(71003, leg.id, leg.name, leg.current_probability) for leg in legs]
        q = _q(_game({"other": rows}, legs,
                     {71003: _facts("Gwangju vs FC Anyang", mutually_exclusive=True)},
                     sport="soccer", home="Gwangju FC", away="FC Anyang"), "m:71003")
        assert q["missing_options"] == []
        assert "draw" not in {o["side"] for o in q["options"]}
        assert q["complete"] is None


class TestMultiContenderDisplayNotRaw:
    def test_display_is_published_and_raw_sits_beside_it_with_the_raw_sum(self):
        legs = [_leg(72009, 71004, "Golfer A", 0.55), _leg(72010, 71004, "Golfer B", 0.25),
                _leg(72011, 71004, "Golfer C", 0.22)]
        m = _game({"matchups": [_matchup(71004, [
            (72009, "Golfer A", 0.5392, LATEST_AT), (72010, "Golfer B", 0.2451, LATEST_AT),
            (72011, "Golfer C", 0.2157, LATEST_AT)], type="3ball",
            market_name="Round 1 three-ball")]}, legs, {71004: _facts("Round 1 three-ball")},
            sport="golf")
        q = _q(m, "m:71004")
        assert [o["published"]["value"] for o in q["options"]] == [0.5392, 0.2451, 0.2157]
        assert [o["source_evidence"][0]["raw_probability"] for o in q["options"]] == [0.55, 0.25, 0.22]
        assert {o["side"] for o in q["options"]} == {"contender"}
        assert q["source_totals"] == [{"source": "kalshi", "raw_sum": 1.02, "legs": 3}]
        assert q["period"] is None and q["kind"] == "named_options"


class TestCountVersusSignedLine:
    def test_a_full_game_over_k5_is_an_inclusive_count_question(self):
        legs = [_leg(72012, 71005, "Over 7.5", 0.60)]
        m = _game({"totals": [_total(71005, 72012, "Over 7.5", 7.5, 0.60)]}, legs,
                  {71005: _facts("Red Sox vs Yankees: Total Runs")})
        q = _q(m, "q:count|runs|game|full_game|ge:8")
        assert (q["kind"], q["label"]) == ("count_threshold", "8+ runs")
        assert q["predicate"] == {"relation": "ge", "bound": 8, "line": 7.5}
        assert q["period"] == {"key": "full_game", "label": "Game"}
        assert q["quantity"] == {"key": "runs", "singular": "run", "plural": "runs", "integer": True}
        assert _opt(q, "o:72012")["published"]["value"] == 0.60
        assert _opt(q, "o:72012")["side"] == "over"

    def test_a_first_half_signed_spread_keeps_team_sign_line_and_period(self):
        legs = [_leg(72013, 71006, "Boston Celtics -3.5", 0.52)]
        m = _game({"period_markets": [_period_row(71006, 72013, "Boston Celtics -3.5", 3.5, 0.52,
                                                  market_type="half_spread", period="1H")]},
                  legs, {71006: _facts("Celtics at Knicks: 1st Half Spread",
                                       external_id="KXNBA1HSPREAD-26OCT02BOSNYK")},
                  sport="basketball", home="Boston Celtics", away="New York Knicks")
        q = _q(m, "q:handicap|points|home|half_1|-3.5")
        assert q["label"] == "Boston Celtics -3.5 points · 1st half"
        assert q["subject"] == {"side": "home", "label": "Boston Celtics"}
        assert q["predicate"]["line"] == -3.5

    def test_an_integer_over_line_is_untyped_predicate(self):
        legs = [_leg(1, 10, "Over 8", 0.5)]
        m = _game({"totals": [_total(10, 1, "Over 8", 8.0, 0.5)]}, legs, {10: _facts("Total Runs")})
        q = _q(m, "m:10")
        assert q["typing"] == {"state": "untyped", "reason": "untyped_predicate"}
        assert m["coverage"]["untyped"]["untyped_predicate"] == 1

    def test_an_unsigned_spread_name_is_untyped_predicate(self):
        legs = [_leg(1, 10, "Boston Red Sox", 0.5)]
        m = _game({"spreads": [_spread(10, 1, "Boston Red Sox", None, 0.5)]}, legs, {10: _facts("Run Line")})
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_predicate"

    def test_a_baseball_1h_by_ticker_is_untyped_period(self):
        legs = [_leg(1, 10, "Over 4.5", 0.5)]
        m = _game({"period_markets": [_total(10, 1, "Over 4.5", 4.5, 0.5, market_type="half_total",
                                             period="1H")]},
                  legs, {10: _facts("Red Sox vs Yankees: 1H Total", external_id="KXMLB1HTOTAL-X")})
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_period"

    def test_an_under_leg_totals_row_publishes_the_over_axis_and_refuses_comparison(self):
        legs = [_leg(72012, 71005, "Under 7.5", 0.40)]
        m = _game({"totals": [_total(71005, 72012, "Under 7.5", 7.5, 0.60)]}, legs,
                  {71005: _facts("Total Runs", meta=_pin(72012, 0.45))})
        opt = _opt(_q(m, "q:count|runs|game|full_game|ge:8"), "o:72012")
        assert opt["published"]["value"] == 0.60
        assert opt["source_evidence"][0]["leg_side"] == "under"
        assert opt["source_evidence"][0]["raw_probability"] == 0.40
        assert opt["comparison"]["reason"] == "leg_is_complement"


class TestRankIsNotCountOrPriceRank:
    def _matrix(self, meta):
        legs = [_leg(72014, 71007, "Yes", 0.42), _leg(72015, 71007, "No", 0.58)]
        rows = [_other(71007, 72014, "Yes", 0.42, market_name="Presidents Cup - Top 10 Finish"),
                _other(71007, 72015, "No", 0.58, market_name="Presidents Cup - Top 10 Finish")]
        return _game({"other": rows}, legs,
                     {71007: _facts("Presidents Cup - Top 10 Finish", meta=meta)}, sport="golf")

    def test_a_stamped_participation_market_is_top_n_with_category_options(self):
        m = self._matrix({"shape": {"outcome_relation": "independent_participation"}})
        q = _q(m, "q:rank|finishing_position|m:71007|le:10")
        assert (q["kind"], q["label"]) == ("rank_predicate", "Top 10")
        assert q["predicate"] == {"relation": "le", "bound": 10, "line": None}
        assert [o["side"] for o in q["options"]] == ["category", "category"]
        assert m["coverage"]["by_kind"]["rank_predicate"] == 1

    def test_without_the_stamp_it_is_named_options_untyped_predicate(self):
        m = self._matrix(None)
        q = _q(m, "m:71007")
        assert q["typing"] == {"state": "untyped", "reason": "untyped_predicate"}
        assert m["coverage"]["untyped"]["untyped_predicate"] == 2

    def test_a_make_cut_name_has_no_n_and_is_refused(self):
        legs = [_leg(1, 10, "Yes", 0.5)]
        m = _game({"other": [_other(10, 1, "Yes", 0.5)]}, legs,
                  {10: _facts("Masters: Make Cut", meta={"shape": {"outcome_relation": "independent_participation"}})},
                  sport="golf")
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_predicate"


class TestQuotedSeriesSurvivesGameFinal:
    def test_an_open_series_stays_open_quoted_and_unsupported_for_comparison(self):
        market = _SeriesMarket(71008, "Alpha vs Beta win series", mutually_exclusive=True)
        legs = [_series_leg(72016, market, "Alpha", 0.70), _series_leg(72017, market, "Beta", 0.29)]
        m = _series([_card(market, [_series_row(72016, "Alpha", 0.70), _series_row(72017, "Beta", 0.29)])],
                    {71008: legs})
        q = _q(m, "m:71008")
        assert m["display_scope"] == "series" and q["display_scope"] == "series"
        assert q["lifecycle"] == {"state": "open", "market_status": "open"}
        assert [o["published"]["value"] for o in q["options"]] == [0.70, 0.29]
        assert {o["side"] for o in q["options"]} == {"home", "away"}
        for o in q["options"]:
            assert o["comparison"] == {"state": "unavailable", "reason": "series_baseline_unsupported",
                                       "baseline": None, "latest": None, "delta_points": None}
            assert o["published"]["observed_at"] is None
            assert o["source_evidence"][0]["observed_at"] is None
        assert "probability_change_24h" not in json.dumps(m)
        assert "0.05" not in json.dumps(m)
        assert m["series_markets_count"] == {"eligible": 1, "returned": 1}


class TestCappedSeriesAndTerminalOption:
    def test_a_publisher_lost_leg_beside_an_open_leg(self):
        market = _SeriesMarket(71009, "Series exact score", mutually_exclusive=True,
                               meta={"event_title": "Series exact score", "market_count": 4})
        legs = [_series_leg(72018, market, "Alpha 2-0", 0.0, is_winner=False),
                _series_leg(72019, market, "Alpha 2-1", 0.49)]
        m = _series([_card(market, [_series_row(72018, "Alpha 2-0", None, settled=True, is_winner=False),
                                    _series_row(72019, "Alpha 2-1", 0.49)])], {71009: legs})
        q = _q(m, "m:71009")
        lost, open_ = _opt(q, "o:72018"), _opt(q, "o:72019")
        assert lost["result"] == {"state": "lost", "evidence_kind": "outcome_is_settled"}
        assert lost["published"]["value"] is None and lost["published"]["basis"] == "result"
        assert open_["result"]["state"] == "open" and open_["published"]["value"] == 0.49
        assert q["lifecycle"]["state"] == "open"
        assert q["option_counts"]["declared"] == 4 and q["complete"] is False

    def test_more_than_ten_loaded_legs_is_never_complete_and_lists_counts_only(self):
        market = _SeriesMarket(71010, "Series total games", mutually_exclusive=True,
                               meta={"shape": {"exhaustive": True, "outcome_count": 12}})
        legs = [_series_leg(80000 + i, market, f"Rung {i}", 0.05) for i in range(12)]
        rows = [_series_row(leg.id, leg.name, 0.05) for leg in legs[:10]]
        q = _q(_series([_card(market, rows)], {71010: legs}), "m:71010")
        assert q["option_counts"] == {"declared": None, "loaded": 12, "returned": 10, "missing_identified": 0}
        assert q["missing_options"] == [] and q["complete"] is False


class TestNoQuoteModelOnly:
    def test_no_sourced_series_market_is_null(self):
        assert _series([], {}) is None

    def test_no_game_rows_is_null(self):
        assert _game() is None


class TestBaselinePairMatchAndClockGap:
    def _matrix(self, *, meta, observed=LATEST_AT, raw=0.55, served=0.55):
        legs = [_leg(72020, 71010, "Boston Red Sox", raw), _leg(72021, 71010, "New York Yankees", 0.45)]
        rows = [_other(71010, 72020, "Boston Red Sox", served),
                _other(71010, 72021, "New York Yankees", 0.45)]
        return _game({"other": rows}, legs,
                     {71010: _facts("Red Sox vs Yankees: First 5 Innings Winner", meta=meta)},
                     observed={72020: observed, 72021: LATEST_AT})

    def test_a_pregame_pin_and_a_later_raw_quote_give_fifteen_points(self):
        q = _q(self._matrix(meta=_pin(72020, 0.40)), "m:71010")
        assert q["period"] == {"key": "first_5_innings", "label": "First 5 innings"}
        home = _opt(q, "o:72020")
        assert home["side"] == "home"
        assert home["comparison"] == {
            "state": "comparable", "reason": None,
            "baseline": {"probability": 0.40, "observed_at": PIN_AT, "basis": "pregame_pin"},
            "latest": {"probability": 0.55, "observed_at": LATEST_AT},
            "delta_points": 15.0,
        }

    def test_a_missing_pin_for_this_outcome_is_no_pregame_pin(self):
        q = _q(self._matrix(meta=_pin(99999, 0.40)), "m:71010")
        assert _opt(q, "o:72020")["comparison"]["reason"] == "no_pregame_pin"

    def test_a_pin_captured_in_play_is_the_opening_line_not_a_pin(self):
        late = (KICKOFF + timedelta(minutes=40)).isoformat()
        q = _q(self._matrix(meta=_pin(72020, 0.40, observed=late, captured=late)), "m:71010")
        assert _opt(q, "o:72020")["comparison"]["reason"] == "baseline_basis_opening_line"

    def test_a_pin_without_its_own_clock_is_baseline_clock_unknown(self):
        meta = {"pregame_mark": {"outcomes": {"72020": 0.40}, "captured_at": PIN_AT}}
        q = _q(self._matrix(meta=meta), "m:71010")
        assert _opt(q, "o:72020")["comparison"]["reason"] == "baseline_clock_unknown"

    def test_a_leg_never_observed_is_current_clock_unknown(self):
        q = _q(self._matrix(meta=_pin(72020, 0.40), observed=None), "m:71010")
        assert _opt(q, "o:72020")["comparison"]["reason"] == "current_clock_unknown"

    def test_a_quote_not_later_than_the_pin_is_baseline_not_earlier(self):
        q = _q(self._matrix(meta=_pin(72020, 0.40), observed=PIN_AT), "m:71010")
        assert _opt(q, "o:72020")["comparison"]["reason"] == "baseline_not_earlier"


# ── the producer gates §10 and the riders ───────────────────────────────────


class TestFiniteZeroIsReal:
    """F1: the route serves a stored 0.0 as null; the annotation says 0.0."""

    def test_series_stored_zero_is_quoted_beside_a_refused_sibling(self):
        market = _SeriesMarket(71011, "Alpha vs Beta win series")
        legs = [_series_leg(1, market, "Alpha", 0.0), _series_leg(2, market, "Beta", 0.97)]
        m = _series([_card(market, [_series_row(1, "Alpha", None), _series_row(2, "Beta", None)])],
                    {71011: legs}, withheld={2})
        q = _q(m, "m:71011")
        zero, refused = _opt(q, "o:1"), _opt(q, "o:2")
        assert zero["published"]["value"] == 0.0 and zero["published"]["value_state"] == "quoted"
        assert zero["source_evidence"][0]["raw_probability"] == 0.0
        assert refused["published"]["value"] is None
        assert refused["published"]["value_state"] == "refused"
        assert refused["source_evidence"] == []
        assert "0.97" not in json.dumps(m)

    def test_a_legacy_null_with_no_stored_price_is_unpriced_not_zero(self):
        market = _SeriesMarket(71012, "Alpha vs Beta win series")
        legs = [_series_leg(1, market, "Alpha", None)]
        q = _q(_series([_card(market, [_series_row(1, "Alpha", None)])], {71012: legs}), "m:71012")
        assert _opt(q, "o:1")["published"]["value_state"] == "unpriced"

    def test_game_other_stored_zero_served_null_is_quoted_zero(self):
        legs = [_leg(1, 10, "Yes", 0.0)]
        m = _game({"other": [_other(10, 1, "Yes", None)]}, legs, {10: _facts("Any run in the 1st?")})
        assert _opt(_q(m, "m:10"), "o:1")["published"]["value"] == 0.0

    def test_the_legacy_array_still_serves_its_null(self):
        row = _other(10, 1, "Yes", None)
        before = copy.deepcopy(row)
        _game({"other": [row]}, [_leg(1, 10, "Yes", 0.0)], {10: _facts("Q")})
        assert row == before


class TestResultsNeverInventLost:
    def test_bare_false_on_an_unprovable_market_is_unknown(self):
        legs = [_leg(1, 10, "Yes", 0.0, is_winner=False), _leg(2, 10, "No", 1.0, is_winner=False)]
        rows = [_other(10, 1, "Yes", None, is_winner=False, resolution_source="api_settlement"),
                _other(10, 2, "No", 1.0, is_winner=False, resolution_source="api_settlement")]
        q = _q(_game({"other": rows}, legs, {10: _facts("Q", status="resolved")}), "m:10")
        assert {o["result"]["state"] for o in q["options"]} == {"unknown"}
        assert "void" not in json.dumps(q)

    def test_a_provable_loss_beside_a_winner_is_lost(self):
        legs = [_leg(1, 10, "Yes", 1.0, is_winner=True), _leg(2, 10, "No", 0.0, is_winner=False)]
        rows = [_other(10, 1, "Yes", 1.0, is_winner=True, resolution_source="api_settlement"),
                _other(10, 2, "No", None, is_winner=False, resolution_source="api_settlement")]
        q = _q(_game({"other": rows}, legs, {10: _facts("Q", status="resolved")}), "m:10")
        assert _opt(q, "o:1")["result"] == {"state": "won", "evidence_kind": "settled_grade_fields"}
        assert _opt(q, "o:2")["result"] == {"state": "lost", "evidence_kind": "verdict_is_provable"}
        assert q["lifecycle"]["state"] == "settled"

    def test_an_ungraded_false_without_a_source_is_not_lost(self):
        legs = [_leg(1, 10, "Yes", 0.0)]
        q = _q(_game({"other": [_other(10, 1, "Yes", None, is_winner=False)]}, legs, {10: _facts("Q")}), "m:10")
        assert _opt(q, "o:1")["result"]["state"] == "unknown"

    def test_a_quoted_zero_on_an_open_market_is_open(self):
        legs = [_leg(1, 10, "Yes", 0.0)]
        q = _q(_game({"other": [_other(10, 1, "Yes", None)]}, legs, {10: _facts("Q")}), "m:10")
        assert _opt(q, "o:1")["result"]["state"] == "open"

    def test_an_unpriced_open_series_leg_is_open_not_lost(self):
        market = _SeriesMarket(71013, "Series exact score")
        legs = [_series_leg(1, market, "Alpha 2-0", None)]
        q = _q(_series([_card(market, [_series_row(1, "Alpha 2-0", None)])], {71013: legs}), "m:71013")
        assert _opt(q, "o:1")["result"]["state"] == "open"


class TestExactScoreStaysCategory:
    def test_an_exact_score_market_is_named_options_with_category_sides(self):
        market = _SeriesMarket(71014, "Series exact score")
        names = ["Alpha 2-0", "Alpha 2-1", "Beta 2-1", "Beta 2-0"]
        legs = [_series_leg(i + 1, market, n, 0.25) for i, n in enumerate(names)]
        q = _q(_series([_card(market, [_series_row(leg.id, leg.name, 0.25) for leg in legs])],
                       {71014: legs}), "m:71014")
        assert q["kind"] == "named_options" and q["predicate"] is None
        assert {o["side"] for o in q["options"]} == {"category"}


class TestUnblendedEquivalents:
    def test_two_served_rows_of_one_proposition_are_one_unblended_option(self):
        legs = [_leg(1, 10, "Over 4.5", 0.55), _leg(2, 10, "Under 4.5", 0.40)]
        rows = [_total(10, 1, "Over 4.5", 4.5, 0.55, market_type="team_total"),
                _total(10, 2, "Under 4.5", 4.5, 0.60, market_type="team_total")]
        for r in rows:
            r["team_side"], r["team_name"] = "home", "Boston Red Sox"
        m = _game({"team_totals": rows}, legs, {10: _facts("Red Sox Team Total Runs")})
        q = _q(m, "q:count|runs|home|full_game|ge:5")
        assert q["label"] == "Boston Red Sox 5+ runs"
        (opt,) = q["options"]
        assert opt["published"] == {"value": None, "value_state": "unblended_equivalents",
                                    "basis": "unknown", "source": None, "observed_at": None}
        assert [e["raw_probability"] for e in opt["source_evidence"]] == [0.55, 0.40]
        assert [e["leg_side"] for e in opt["source_evidence"]] == ["over", "under"]
        assert opt["comparison"]["reason"] == "not_quoted"


class TestR4NoBlendBranch:
    def test_no_multi_contributor_option_has_a_basis_other_than_unknown(self):
        legs = [_leg(1, 10, "Yes", 0.5), _leg(2, 11, "Yes", 0.6)]
        row = _other(10, 1, "Yes", 0.55)
        row["contributor_outcome_ids"], row["_market_ids"] = [1, 2], [10, 11]
        m = _game({"other": [row]}, legs, {10: _facts("Q", meta=_pin(1, 0.3)), 11: _facts("Q")})
        options = [o for q in m["questions"] for o in q["options"]]
        assert options and all(o["published"]["basis"] == "unknown"
                               for o in options if len(o["contributor_outcome_ids"]) > 1)
        assert options[0]["comparison"]["reason"] == "not_quoted"
        assert "published_blend" not in json.dumps(m)


class TestR3PinReadInEveryStatus:
    def test_a_final_game_with_a_pregame_pin_on_an_open_market_is_comparable(self):
        legs = [_leg(1, 10, "Boston Red Sox", 0.55), _leg(2, 10, "New York Yankees", 0.45)]
        rows = [_other(10, 1, "Boston Red Sox", 0.55), _other(10, 2, "New York Yankees", 0.45)]
        m = _game({"other": rows}, legs, {10: _facts("Red Sox vs Yankees: Series Game", meta=_pin(1, 0.40))})
        assert _opt(_q(m, "m:10"), "o:1")["comparison"]["state"] == "comparable"


class TestR2LatestIsTheRawValue:
    def test_latest_and_delta_use_the_raw_leg_not_the_squeezed_display(self):
        legs = [_leg(1, 10, "Boston Red Sox", 0.55), _leg(2, 10, "New York Yankees", 0.25),
                _leg(3, 10, "Tie", 0.22)]
        rows = [_other(10, 1, "Boston Red Sox", 0.5392), _other(10, 2, "New York Yankees", 0.2451),
                _other(10, 3, "Tie", 0.2157)]
        m = _game({"other": rows}, legs,
                  {10: _facts("Red Sox vs Yankees", mutually_exclusive=True, meta=_pin(1, 0.40))})
        opt = _opt(_q(m, "m:10"), "o:1")
        assert opt["published"]["value"] == 0.5392
        assert opt["comparison"]["latest"] == {"probability": 0.55, "observed_at": LATEST_AT}
        assert opt["comparison"]["delta_points"] == 15.0
        others = [o for o in _q(m, "m:10")["options"] if o["option_key"] != "o:1"]
        assert all(o["comparison"]["latest"] is None for o in others)


class TestR1ReasonPrecedence:
    def test_not_quoted_beats_complement_and_pin(self):
        legs = [_leg(1, 10, "Under 7.5", None)]
        row = _total(10, 1, "Under 7.5", 7.5, None)
        m = _game({"totals": [row]}, legs, {10: _facts("Total Runs")})
        assert m["questions"][0]["options"][0]["comparison"]["reason"] == "not_quoted"

    def test_complement_beats_a_missing_pin(self):
        legs = [_leg(1, 10, "Under 7.5", 0.4)]
        m = _game({"totals": [_total(10, 1, "Under 7.5", 7.5, 0.6)]}, legs, {10: _facts("Total Runs")})
        assert m["questions"][0]["options"][0]["comparison"]["reason"] == "leg_is_complement"

    def test_series_not_quoted_beats_unsupported(self):
        market = _SeriesMarket(71015, "S")
        legs = [_series_leg(1, market, "Alpha", None)]
        q = _q(_series([_card(market, [_series_row(1, "Alpha", None)])], {71015: legs}), "m:71015")
        assert _opt(q, "o:1")["comparison"]["reason"] == "not_quoted"


class TestR6OverlapIndependence:
    def test_one_market_in_both_payloads_is_annotated_independently(self):
        market = _SeriesMarket(71016, "Red Sox vs Yankees: Series Winner", mutually_exclusive=True)
        game_legs = [_leg(1, 71016, "Boston Red Sox", 0.55), _leg(2, 71016, "New York Yankees", 0.45)]
        game = _game({"other": [_other(71016, 1, "Boston Red Sox", 0.55),
                                _other(71016, 2, "New York Yankees", 0.45)]},
                     game_legs, {71016: _facts(market.name, meta=_pin(1, 0.40))})
        series_legs = [_series_leg(1, market, "Boston Red Sox", 0.55),
                       _series_leg(2, market, "New York Yankees", 0.45)]
        series = _series([_card(market, [_series_row(1, "Boston Red Sox", 0.55),
                                         _series_row(2, "New York Yankees", 0.45)])],
                         {71016: series_legs}, home="Boston Red Sox", away="New York Yankees")
        g, s = _q(game, "m:71016"), _q(series, "m:71016")
        assert (game["display_scope"], series["display_scope"]) == ("game", "series")
        assert _opt(g, "o:1")["comparison"]["state"] == "comparable"
        assert _opt(s, "o:1")["comparison"]["reason"] == "series_baseline_unsupported"


class TestFinalGameDoesNotCloseOpenSeries:
    def test_series_lifecycle_reads_only_its_own_market(self):
        market = _SeriesMarket(71017, "Alpha vs Beta win series", status="open")
        legs = [_series_leg(1, market, "Alpha", 0.8), _series_leg(2, market, "Beta", 0.2)]
        q = _q(_series([_card(market, [_series_row(1, "Alpha", 0.8), _series_row(2, "Beta", 0.2)])],
                       {71017: legs}), "m:71017")
        assert q["lifecycle"]["state"] == "open"
        assert {o["result"]["state"] for o in q["options"]} == {"open"}

    def test_a_series_settled_before_the_game_is_not_eligible(self):
        market = _SeriesMarket(71018, "Old series", status="resolved")
        legs = [_series_leg(1, market, "Alpha", 1.0)]
        m = _series([], {71018: legs}, settled_before=lambda mk: True)
        assert m is None


class TestHandicapSpellingsAndComplement:
    def test_a_signed_pair_links_complements_and_the_margin_strict_spelling_types(self):
        legs = [_leg(1, 10, "Gwangju -1.5", 0.35), _leg(2, 10, "FC Anyang +1.5", 0.65),
                _leg(3, 11, "Gwangju wins by more than 1.5 goals", 0.30)]
        m = _game({"spreads": [_spread(10, 1, "Gwangju -1.5", 1.5, 0.35),
                               _spread(10, 2, "FC Anyang +1.5", 1.5, 0.65),
                               _spread(11, 3, "Gwangju wins by more than 1.5 goals", 1.5, 0.30)]},
                  legs, {10: _facts("Gwangju vs FC Anyang: Spread"), 11: _facts("Gwangju vs FC Anyang: Spread")},
                  sport="soccer", home="Gwangju FC", away="FC Anyang")
        home = _q(m, "q:handicap|goals|home|full_game|-1.5")
        away = _q(m, "q:handicap|goals|away|full_game|+1.5")
        assert home["complement_question_key"] == away["question_key"]
        assert away["complement_question_key"] == home["question_key"]
        assert len(home["options"]) == 1 or home["options"][0]["published"]["value_state"] == "unblended_equivalents"

    def test_an_at_least_margin_is_refused(self):
        legs = [_leg(1, 10, "Gwangju wins by 2 or more goals", 0.3)]
        m = _game({"spreads": [_spread(10, 1, "Gwangju wins by 2 or more goals", 2.0, 0.3)]},
                  legs, {10: _facts("Spread")}, sport="soccer", home="Gwangju FC", away="FC Anyang")
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_predicate"

    def test_a_signed_number_with_no_team_is_untyped_subject(self):
        legs = [_leg(1, 10, "Spread -1.5", 0.5)]
        m = _game({"spreads": [_spread(10, 1, "Spread -1.5", 1.5, 0.5)]}, legs, {10: _facts("Spread")},
                  sport="soccer", home="Gwangju FC", away="FC Anyang")
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_subject"

    def test_a_bare_nickname_names_no_side_and_is_untyped_subject(self):
        """`resolve_team_side` matches by prefix in either direction, so the
        locality ("Boston") resolves and the nickname alone ("Celtics", the
        4970 fixture's spelling) does not. The matrix inherits that refusal."""
        legs = [_leg(1, 10, "Celtics -3.5", 0.54)]
        m = _game({"spreads": [_spread(10, 1, "Celtics -3.5", 3.5, 0.54)]}, legs, {10: _facts("Spread")},
                  sport="basketball", home="Boston Celtics", away="New York Knicks")
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_subject"

    def test_a_sport_with_no_scoring_unit_is_untyped_unit(self):
        legs = [_leg(1, 10, "Alcaraz -2.5", 0.5)]
        m = _game({"spreads": [_spread(10, 1, "Alcaraz -2.5", 2.5, 0.5)]}, legs, {10: _facts("Games Spread")},
                  sport="tennis", home="Carlos Alcaraz", away="Jannik Sinner")
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_unit"


class TestSiblingSurvival:
    def test_a_row_that_cannot_be_read_is_counted_and_its_siblings_survive(self):
        legs = [_leg(1, 10, "Yes", 0.5), _leg(2, 11, "Over 7.5", 0.6)]
        bad = _other(10, 1, "Yes", 0.5)
        bad["contributor_outcome_ids"] = ["not-an-id"]
        m = _game({"other": [bad], "totals": [_total(11, 2, "Over 7.5", 7.5, 0.6)]}, legs,
                  {10: _facts("Q"), 11: _facts("Total Runs")})
        assert m["coverage"]["build_errors"] == 1
        assert [q["question_key"] for q in m["questions"]] == ["q:count|runs|game|full_game|ge:8"]

    def test_a_market_whose_facts_break_typing_is_counted_and_siblings_survive(self):
        legs = [_leg(1, 10, "Over 6.5", 0.5), _leg(2, 11, "Over 7.5", 0.6)]
        m = _game({"totals": [_total(10, 1, "Over 6.5", 6.5, 0.5), _total(11, 2, "Over 7.5", 7.5, 0.6)]},
                  legs, {10: _facts(12345), 11: _facts("Total Runs")})
        assert m["coverage"]["build_errors"] == 1
        assert [q["question_key"] for q in m["questions"]] == ["q:count|runs|game|full_game|ge:8"]


class TestCoverageAndOrder:
    def test_coverage_counts_what_this_response_served_and_order_is_array_then_market(self):
        legs = [_leg(1, 20, "Boston Red Sox", 0.55), _leg(2, 20, "New York Yankees", 0.45),
                _leg(3, 10, "Over 7.5", 0.6), _leg(4, 30, "Over 8", 0.5)]
        m = _game({"other": [_other(20, 1, "Boston Red Sox", 0.55), _other(20, 2, "New York Yankees", 0.45)],
                   "totals": [_total(10, 3, "Over 7.5", 7.5, 0.6), _total(30, 4, "Over 8", 8.0, 0.5)]},
                  legs, {10: _facts("Total Runs"), 20: _facts("Winner"), 30: _facts("Total Runs")})
        assert [q["question_key"] for q in m["questions"]] == [
            "q:count|runs|game|full_game|ge:8", "m:30", "m:20",
        ]
        assert m["coverage"] == {
            "scope": "rows_served_by_this_response", "questions": 3, "options": 4,
            "by_kind": {"count_threshold": 1, "signed_handicap": 0, "rank_predicate": 0},
            "untyped": {"untyped_period": 0, "untyped_unit": 0, "untyped_subject": 0,
                        "untyped_predicate": 1},
            "build_errors": 0,
        }
        assert m["contract"] == "10238.v1" and m["series_markets_count"] is None


# ── A3 + A4: every admitted spelling ships on a retained real market name ───

# (shape, market name, leg name, sport, home, away, retained in). The market
# name is what proves the unit (A4), so it is the real one, never a stand-in.
ADMITTED_SPELLINGS = (
    ("count:total_phrase", "Celtics at Knicks: Total Points", "Over 210.5", "basketball",
     "Boston Celtics", "New York Knicks", "tests/test_a_game_market_row_carries_its_own_price_age_4970.py"),
    ("count:total_phrase", "Yankees at Red Sox: Total Runs", "Over 8.5", "baseball",
     "Boston Red Sox", "New York Yankees", "tests/test_game_markets.py"),
    ("count:total_phrase", "Oilers at Kings: Total Goals", "Over 5.5", "icehockey",
     "Los Angeles Kings", "Edmonton Oilers", "tests/test_game_markets.py"),
    ("count:team_segment", "LAL Lakers at BOS Celtics: Points", "Over 110.5", "basketball",
     "Boston Celtics", "Los Angeles Lakers", "tests/test_repair_kalshi_nhl_prop_category_4365.py"),
    ("count:team_segment", "Cubs at Cardinals: Runs", "Over 4.5", "baseball",
     "St. Louis Cardinals", "Chicago Cubs", "tests/test_futures_categorization.py"),
    ("count:bare_ou", "Cardinals vs. Reds: O/U 10.5", "Over", "baseball",
     "Cincinnati Reds", "St. Louis Cardinals", "tests/test_a_runs_map_is_not_four_players_props_3594.py"),
    ("count:bare_ou", "IR Iran vs. New Zealand: 1st Half O/U 1.5", "Over", "soccer",
     "IR Iran", "New Zealand", "tests/test_ladder_coherence_p106.py"),
    ("handicap:spread", "Gwangju vs FC Anyang: Spread", "Gwangju -1.5", "soccer",
     "Gwangju FC", "FC Anyang", "tests/test_a_settled_margin_market_is_graded_from_the_final_score_6312.py"),
    ("handicap:spread", "Dallas vs New York: Spread", "Dallas -3.5", "americanfootball",
     "Dallas Cowboys", "New York Giants", "tests/test_kalshi_spread_phrasing_3948.py"),
    ("handicap:run_line", "Yankees at Red Sox: Run Line", "Boston Red Sox -1.5", "baseball",
     "Boston Red Sox", "New York Yankees", "tests/test_game_market_class.py"),
    ("handicap:first_5_spread", "Tampa Bay vs Atlanta: First 5 Spread", "Tampa Bay -1.5", "baseball",
     "Tampa Bay Rays", "Atlanta Braves", "tests/test_deep_otm_settled_spread_4845.py"),
    ("handicap:handicap", "Arsenal vs Chelsea: Handicap -1.5", "Arsenal -1.5", "soccer",
     "Arsenal", "Chelsea", "tests/evals/fixtures/soccer_classifier_contract.json"),
    ("handicap:margin_strict", "Gwangju vs FC Anyang: Spread", "Gwangju wins by more than 1.5 goals",
     "soccer", "Gwangju FC", "FC Anyang",
     "tests/test_a_settled_margin_market_is_graded_from_the_final_score_6312.py"),
    ("rank:top_n", "Presidents Cup - Top 10 Finish", "Yes", "golf", None, None,
     "tests/test_golf_team_match_play_has_no_individual_markets_7985.py"),
)


def _retained(text: str, path: str) -> bool:
    return f'"{text}"' in (BACKEND / path).read_text()


class TestEveryAdmittedSpelling:
    @pytest.mark.parametrize("shape,market,leg,sport,home,away,source_file", ADMITTED_SPELLINGS,
                             ids=[f"{s[0]}:{s[1]}" for s in ADMITTED_SPELLINGS])
    def test_the_spelling_types_on_its_retained_real_market(
        self, shape, market, leg, sport, home, away, source_file,
    ):
        assert _retained(market, source_file), f"{market!r} is no longer retained in {source_file}"
        legs = [_leg(1, 10, leg, 0.5)]
        if shape == "rank:top_n":
            m = _game({"other": [_other(10, 1, leg, 0.5, market_name=market)]}, legs,
                      {10: _facts(market, meta={"shape": {"outcome_relation": "independent_participation"}})},
                      sport=sport)
            assert m["questions"][0]["kind"] == "rank_predicate"
            return
        line = events_route._extract_threshold(market if shape == "count:bare_ou" else leg)
        if shape.startswith("count:"):
            row = _total(10, 1, leg, line, 0.5, market_name=market,
                         market_type="team_total" if shape == "count:team_segment" else "game_total")
            if shape == "count:team_segment":
                row["team_side"] = "home"
                served = {"team_totals": [row]}
            elif "1st Half" in market:
                row["market_type"], row["period"] = "half_total", "1H"
                served = {"period_markets": [row]}
            else:
                served = {"totals": [row]}
        else:
            served = {"spreads": [_spread(10, 1, leg, line, 0.5, market_name=market)]}
        m = _game(served, legs, {10: _facts(market)}, sport=sport, home=home, away=away)
        (q,) = m["questions"]
        assert q["typing"] == {"state": "typed", "reason": None}, (q["typing"], q["question_key"])
        assert q["kind"] == ("count_threshold" if shape.startswith("count:") else "signed_handicap")

    def test_the_n_plus_leg_spelling_has_no_retained_fixture_and_is_refused(self):
        legs = [_leg(1, 10, "8+", 0.5)]
        m = _game({"totals": [_total(10, 1, "8+", 8.0, 0.5)]}, legs, {10: _facts("Total Runs")})
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_predicate"


class TestA4TheUnitIsProvenByTheMarketName:
    """Authority A4 on c326156218: the unit and the full-game period were
    admitted on evidence that did not prove them. Each case below typed a
    false label on that sha."""

    def test_a_real_total_home_runs_market_is_not_runs(self):
        name = "Pro Baseball All-Star Game: Total Home Runs"
        assert _retained(name, "tests/fixtures/prop_family_keys_before_6630.json")
        legs = [_leg(1, 10, "Over 2.5", 0.5)]
        m = _game({"totals": [_total(10, 1, "Over 2.5", 2.5, 0.5, market_name=name)]}, legs,
                  {10: _facts(name)})
        q = _q(m, "m:10")
        assert q["kind"] == "named_options"
        assert q["typing"] == {"state": "untyped", "reason": "untyped_unit"}
        assert m["coverage"]["untyped"]["untyped_unit"] == 1
        assert "runs" not in json.dumps([x["label"] for x in m["questions"]])

    @pytest.mark.parametrize("name,leg,line,market_type,period,sport", [
        ("Arsenal vs Chelsea: Total Cards O/U 4.5", "Over", 4.5, "game_total", None, "soccer"),
        ("Bills at Texans: 1st Half Total Touchdowns", "Over 2.5", 2.5, "half_total", "1H", "americanfootball"),
    ])
    def test_cards_and_touchdowns_are_not_goals_or_points(self, name, leg, line, market_type, period, sport):
        legs = [_leg(1, 10, leg, 0.5)]
        row = _total(10, 1, leg, line, 0.5, market_name=name, market_type=market_type, period=period)
        served = {"period_markets": [row]} if market_type == "half_total" else {"totals": [row]}
        m = _game(served, legs, {10: _facts(name, external_id="KXNFL1HTOTAL-X" if period else None)},
                  sport=sport, home="Houston Texans", away="Buffalo Bills")
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_unit"

    def test_a_corners_handicap_is_not_a_goal_handicap(self):
        legs = [_leg(1, 10, "Arsenal -1.5", 0.5)]
        m = _game({"spreads": [_spread(10, 1, "Arsenal -1.5", 1.5, 0.5,
                                       market_name="Arsenal vs Chelsea: Corners Handicap")]},
                  legs, {10: _facts("Arsenal vs Chelsea: Corners Handicap")},
                  sport="soccer", home="Arsenal", away="Chelsea")
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_unit"

    def test_a_period_stated_only_in_the_leg_is_not_full_game(self):
        legs = [_leg(1, 10, "Boston Celtics -3.5 1st half", 0.5)]
        m = _game({"spreads": [_spread(10, 1, "Boston Celtics -3.5 1st half", 3.5, 0.5,
                                       market_name="Celtics at Knicks: Spread")]},
                  legs, {10: _facts("Celtics at Knicks: Spread")},
                  sport="basketball", home="Boston Celtics", away="New York Knicks")
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_period"

    def test_a_puck_line_has_no_retained_name_and_is_not_admitted(self):
        legs = [_leg(1, 10, "Edmonton Oilers -1.5", 0.5)]
        m = _game({"spreads": [_spread(10, 1, "Edmonton Oilers -1.5", 1.5, 0.5)]}, legs,
                  {10: _facts("Oilers at Kings: Puck Line")}, sport="icehockey",
                  home="Los Angeles Kings", away="Edmonton Oilers")
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_unit"

    def test_a_noun_of_another_sport_is_not_this_sports_unit(self):
        legs = [_leg(1, 10, "Over 5.5", 0.5)]
        m = _game({"totals": [_total(10, 1, "Over 5.5", 5.5, 0.5)]}, legs,
                  {10: _facts("Red Sox vs Yankees: Total Goals")})
        assert _q(m, "m:10")["typing"]["reason"] == "untyped_unit"


class TestF1StaysOnTheLegsOwnAxis:
    def test_an_under_legs_stored_zero_is_never_published_as_over_axis_zero(self):
        legs = [_leg(1, 10, "Under 7.5", 0.0)]
        m = _game({"totals": [_total(10, 1, "Under 7.5", 7.5, None)]}, legs, {10: _facts("Total Runs")})
        opt = m["questions"][0]["options"][0]
        assert opt["published"]["value"] is None
        assert opt["published"]["value_state"] == "refused"


# ── the route: served JSON, legacy byte-identity, the under-leg parity ──────

NOW = datetime(2026, 5, 17, 23, 30, tzinfo=timezone.utc)


@pytest.fixture
def _clean_game_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


def _result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _route_market(*, id, name, external_id=None, metadata=None):
    market = MagicMock()
    market.id, market.name, market.external_id = id, name, external_id
    market.event_id, market.category, market.status = 42, "game_prop", "open"
    market.source, market.sport_id = "kalshi", 1
    market.llm_sport_category = "basketball"
    market.commence_time = datetime(2026, 5, 17, 23, 0, tzinfo=timezone.utc)
    market.group_id = market.group_type = None
    market.market_metadata = metadata
    market.mutually_exclusive = None
    market.market_tier = 5
    return market


def _route_outcome(*, id, market_id, name, prob):
    outcome = MagicMock()
    outcome.id, outcome.market_id, outcome.name = id, market_id, name
    outcome.current_probability = prob
    outcome.opening_probability = 0.5
    outcome.is_winner = outcome.resolution_source = None
    outcome.last_updated = NOW
    return outcome


def _route_event():
    event = MagicMock()
    event.id, event.status, event.sport_id = 42, "live", 1
    event.sport = MagicMock()
    event.sport.key = "basketball_nba"
    event.home_team_name, event.away_team_name = "Boston Celtics", "New York Knicks"
    event.home_score, event.away_score = 88, 82
    event.commence_time = datetime(2026, 5, 17, 23, 0, tzinfo=timezone.utc)
    event.completed_at = event.box_score_data = None
    event.period, event.game_clock = "3rd Quarter", "6:32"
    event.score_observed_at = event.score_source = None
    return event


def _route_page():
    pin = {"pregame_mark": {"outcomes": {"3": 0.40}, "observed_at": "2026-05-17T22:00:00+00:00",
                            "captured_at": "2026-05-17T22:00:00+00:00"}}
    markets = [
        _route_market(id=101, name="Celtics at Knicks: Total Points"),
        _route_market(id=102, name="Celtics at Knicks: Spread", metadata=pin),
        _route_market(id=104, name="Head-to-Head: Scheffler vs McIlroy"),
        _route_market(id=106, name="Celtics at Warriors"),
    ]
    outcomes = [
        _route_outcome(id=2, market_id=101, name="Under 210.5", prob=0.48),
        _route_outcome(id=3, market_id=102, name="Boston Celtics -3.5", prob=0.54),
        _route_outcome(id=5, market_id=104, name="Scheffler", prob=0.55),
        _route_outcome(id=6, market_id=104, name="McIlroy", prob=0.45),
        _route_outcome(id=8, market_id=106, name="Yes", prob=0.70),
    ]
    return markets, outcomes


def _route_db(markets, outcomes):
    rows = [SimpleNamespace(id=o.id, observed_at=NOW - timedelta(minutes=o.id),
                            price_changed_at=None, resolution_source=None, current_probability=None)
            for o in outcomes]
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _result(scalar=_route_event()),
        _result(),
        _result(rows=[]),
        _result(rows=markets),
        _result(all_rows=[]),
        _result(rows=[]),
        _result(rows=outcomes),
        _result(all_rows=rows),
    ])
    return db


def _build_page():
    markets, outcomes = _route_page()
    response, _status, ids = asyncio.run(
        events_route._build_game_markets(42, _route_db(markets, outcomes))
    )
    return response, ids


@pytest.mark.usefixtures("_clean_game_cache")
class TestGameMarketsRoute:
    def test_the_key_reaches_the_served_json_through_the_publisher(self, monkeypatch):
        from app.utils import game_markets_cache as gmc

        monkeypatch.setattr(gmc, "compute_watermark", AsyncMock(return_value=None))
        monkeypatch.setattr(gmc, "write", lambda *a, **k: None)
        response, ids = _build_page()
        served = asyncio.run(events_route._publish_game_markets(42, "live", response, ids, None))
        matrix = json.loads(json.dumps(served))["game_question_matrix"]
        assert matrix["contract"] == "10238.v1" and matrix["display_scope"] == "game"
        keys = {q["question_key"] for q in matrix["questions"]}
        assert "q:handicap|points|home|full_game|-3.5" in keys
        assert "m:104" in keys

    def test_every_legacy_key_is_byte_identical_with_and_without_the_matrix(self, monkeypatch):
        with_matrix, _ = _build_page()
        _game_markets_cache.clear()
        monkeypatch.setattr(events_route, "build_game_question_matrix", lambda **kw: None)
        without, _ = _build_page()
        assert with_matrix["game_question_matrix"] is not None
        assert without["game_question_matrix"] is None
        legacy = sorted(set(with_matrix) - {"game_question_matrix"})
        assert legacy == sorted(set(without) - {"game_question_matrix"})
        for key in legacy:
            assert json.dumps(with_matrix[key], sort_keys=True, default=str) == json.dumps(
                without[key], sort_keys=True, default=str), key

    def test_a_builder_failure_never_fails_the_page(self, monkeypatch):
        def boom(**kw):
            raise RuntimeError("synthetic")

        monkeypatch.setattr(events_route, "build_game_question_matrix", boom)
        response, _ = _build_page()
        assert response["game_question_matrix"] is None
        assert response["spreads"] and response["matchups"]

    def test_the_under_leg_reading_agrees_with_the_route_on_the_served_row(self):
        """`_leg_reads_under` re-reads the route's own `is_under and not is_over`
        test; this pins the two together on the route's served totals row."""
        response, _ = _build_page()
        (row,) = [r for r in response["totals"] if r["contributor_outcome_ids"] == [2]]
        assert row["over_probability"] == round(1 - 0.48, 4)
        q = _q(response["game_question_matrix"], "q:count|points|game|full_game|ge:211")
        assert q["options"][0]["source_evidence"][0]["leg_side"] == "under"
        assert q["options"][0]["comparison"]["reason"] == "leg_is_complement"

    def test_the_route_pin_reaches_the_comparison_from_the_g0_snapshot(self):
        response, _ = _build_page()
        q = _q(response["game_question_matrix"], "q:handicap|points|home|full_game|-3.5")
        assert q["options"][0]["comparison"]["state"] == "comparable"
        assert q["options"][0]["comparison"]["delta_points"] == 14.0


class _RFResult:
    def __init__(self, rows=None, scalar=None):
        self._rows, self._scalar = rows or [], scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _SeriesSession:
    """Answers `_build_related_futures`'s statements by what they read; the
    Series id query and the Series outcome load get the specimen.

    The route only reaches its Series block when the season-futures pass
    loads at least one outcome (`if not outcomes: return empty`), so that pass
    gets one leg of last season's settled market, which the route then skips
    under #9042 — the season arrays stay empty and the Series card is the
    whole payload under test."""

    def __init__(self, event, series_ids, series_outcomes):
        self.event, self.series_ids, self.series_outcomes = event, series_ids, series_outcomes
        old_market = SimpleNamespace(
            id=500, name="2025 World Series Winner", status="resolved", source="kalshi",
            resolution_date=datetime(2025, 11, 1, tzinfo=timezone.utc), external_id=None,
            market_metadata=None, mutually_exclusive=True, market_tier=1,
        )
        self.season_outcomes = [SimpleNamespace(
            id=501, market_id=500, name="Boston Red Sox", team_id=None, current_probability=1.0,
            is_winner=True, resolution_source="api_settlement", market=old_market,
            probability_change_24h=None, external_id=None,
        )]

    async def execute(self, stmt, *args, **kwargs):
        sql = str(stmt)
        if "FROM events" in sql and "futures" not in sql:
            return _RFResult(scalar=self.event)
        if "FROM sports" in sql:
            return _RFResult(rows=[SimpleNamespace(id=7)])
        if "FROM futures_outcomes" in sql and "ORDER BY futures_outcomes.market_id" in sql:
            return _RFResult(rows=self.series_outcomes)
        if "FROM futures_outcomes" in sql:
            return _RFResult(rows=self.season_outcomes)
        if sql.startswith("SELECT futures_markets.id, futures_markets.market_tier"):
            return _RFResult(rows=[SimpleNamespace(id=500, market_tier=1)])
        if sql.startswith("SELECT futures_markets.id \nFROM futures_markets") and "LIMIT" in sql:
            return _RFResult(rows=[SimpleNamespace(id=i) for i in self.series_ids])
        return _RFResult(rows=[])


class _Row(SimpleNamespace):
    """A loaded row: every field the test does not set reads as NULL."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return None


def _series_build(monkeypatch, *, disable=False):
    from app.routes import league_futures

    monkeypatch.setattr(events_route, "_related_futures_withheld_ids", AsyncMock(return_value=set()))
    if disable:
        monkeypatch.setattr(events_route, "build_series_question_matrix", lambda **kw: None)
    market = SimpleNamespace(id=900, name="Red Sox vs Yankees: Series Winner", source="kalshi",
                             status="open", resolution_date=None, mutually_exclusive=True,
                             market_metadata=None, probability_change_24h=None,
                             commence_time=None, external_id="KXMLBSERIES-X")
    legs = [SimpleNamespace(id=901, market_id=900, name="Boston Red Sox", current_probability=0.6,
                            probability_change_24h=None, is_winner=None, resolution_source=None,
                            external_id="KXMLBSERIES-X-BOS", market=market),
            SimpleNamespace(id=902, market_id=900, name="New York Yankees", current_probability=0.4,
                            probability_change_24h=None, is_winner=None, resolution_source=None,
                            external_id="KXMLBSERIES-X-NYY", market=market)]
    event = _Row(
        id=55, sport=SimpleNamespace(id=7, key="baseball_mlb"), sport_id=7, status="completed",
        home_team_name="Boston Red Sox", away_team_name="New York Yankees",
        commence_time=datetime(2026, 10, 2, 23, 0, tzinfo=timezone.utc),
        home_team_id=None, away_team_id=None, period=None, game_clock=None,
        box_score_data=None, llm_league="MLB", home_score=5, away_score=3,
    )
    assert league_futures._field_has_a_winner(legs) is False
    session = _SeriesSession(event, [900], legs)
    response, _status, ids, cacheable = asyncio.run(events_route._build_related_futures(55, session))
    return response, ids, cacheable


class TestRelatedFuturesRoute:
    def test_the_series_key_reaches_the_served_json_and_stays_open_after_the_final(self, monkeypatch):
        from app.utils import related_futures_cache as rfc

        response, ids, cacheable = _series_build(monkeypatch)
        assert cacheable and response["series_markets"], response.get("series_markets")
        monkeypatch.setattr(rfc, "compute_watermark", AsyncMock(return_value=None))
        monkeypatch.setattr(rfc, "write", lambda *a, **k: None)
        served = asyncio.run(events_route._publish_related_futures(55, "completed", response, ids, None))
        matrix = json.loads(json.dumps(served))["series_question_matrix"]
        q = _q(matrix, "m:900")
        assert q["lifecycle"]["state"] == "open"
        assert {o["side"] for o in q["options"]} == {"home", "away"}
        assert matrix["series_markets_count"] == {"eligible": 1, "returned": 1}

    def test_every_legacy_key_is_byte_identical_with_and_without_the_matrix(self, monkeypatch):
        with_matrix, _, _ = _series_build(monkeypatch)
        without, _, _ = _series_build(monkeypatch, disable=True)
        assert with_matrix["series_question_matrix"] is not None
        assert without["series_question_matrix"] is None
        legacy = sorted(set(with_matrix) - {"series_question_matrix"})
        assert legacy == sorted(set(without) - {"series_question_matrix"})
        for key in legacy:
            assert json.dumps(with_matrix[key], sort_keys=True, default=str) == json.dumps(
                without[key], sort_keys=True, default=str), key


def test_the_module_reads_no_movement_or_change_field():
    source = (BACKEND / "app/utils/event_question_matrix.py").read_text()
    code = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )
    body = code.split('"""', 2)[2]
    for forbidden in (".probability_change_24h", "[\"probability_change_24h\"]",
                      ".opening_probability", ".last_updated", "\"movement\"]"):
        assert forbidden not in body, forbidden
    assert CONTRACT == "10238.v1"
