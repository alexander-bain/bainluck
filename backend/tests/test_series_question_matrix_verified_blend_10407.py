"""#10407 A1 — the Series matrix asks a verified two-venue series winner once.

PILLARS: MATCHING / TRUTH. SHIP: a playoff game page asks "who wins the
series" once, with one blended number; each venue keeps its own no-winner rules.

Contract rider 10238.v1 / 10407-R1 (Authority): with a composition, the two
per-market Series questions become ONE question
(`q:series_winner:<season>:<lo>-<hi>`, both original keys in
`merged_question_keys`), one option per team published as
`verified_series_blend` with `source: null`, both raw legs as evidence, the
comparison still `series_baseline_unsupported`. Without one, the output is
byte-identical. The matrix copies the number; it never blends. Served
`series_markets` and every other related-futures key are byte-identical.

Specimen: event 15322539 (Yankees at Rays, ALDS G1) as served 2026-10-04
15:11Z (shopper, `10407-series-identity/related-futures-15322539.json`):
Kalshi 63551228, Polymarket 63849278, and the Polymarket spread 63849276.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routes import events as events_route
from app.utils import series_winner_correspondence as swc
from app.utils.event_question_matrix import build_series_question_matrix
from app.utils.series_winner_correspondence import (
    SeriesLeg,
    SeriesMarketFacts,
    compose_series_pairs,
)

BACKEND = Path(__file__).resolve().parents[1]
TB, NYY, NYM = 101, 102, 103
ROSTER = [
    {"id": TB, "name": "Tampa Bay Rays", "abbreviation": "TB", "location": "Tampa Bay",
     "alternate_names": ["Rays"]},
    {"id": NYY, "name": "New York Yankees", "abbreviation": "NYY", "location": "New York",
     "alternate_names": ["Yankees", "New York"]},
    {"id": NYM, "name": "New York Mets", "abbreviation": "NYM", "location": "New York",
     "alternate_names": ["Mets", "New York"]},
]
KT = "KXMLBSERIES-26NYYTBALDS"
CUTOFF = {"at": "2026-10-25T03:59:00+00:00", "source": "polymarket_rules_text",
          "family": "mlb_series_winner", "clauses": 2}


def _utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def _markets(*, cutoff=CUTOFF):
    pm_meta = {"polymarket_event_id": "1120800",
               "polymarket_event_slug": "mlb-playoffs-who-will-win-series-rays-vs-yankees"}
    if cutoff is not None:
        pm_meta["no_winner_cutoff"] = cutoff
    return {
        63551228: SimpleNamespace(
            id=63551228, name="Series Winner: New York Y vs Tampa Bay", source="kalshi",
            external_id=KT, status="open", resolution_date=_utc(2026, 10, 18, 22, 30),
            mutually_exclusive=True, market_metadata={"kalshi_event_ticker": KT},
            probability_change_24h=None, commence_time=_utc(2026, 10, 31, 22, 30)),
        63849276: SimpleNamespace(
            id=63849276, name="MLB Playoffs: Rays vs. Yankees Series Spread", source="polymarket",
            external_id="1120799", status="open", resolution_date=_utc(2026, 10, 12, 3, 59),
            mutually_exclusive=False,
            market_metadata={"polymarket_event_id": "1120799",
                             "polymarket_event_slug": "mlb-playoffs-series-spread-rays-vs-yankees"},
            probability_change_24h=None, commence_time=None),
        63849278: SimpleNamespace(
            id=63849278, name="MLB Playoffs: Who Will Win Series? - Rays vs. Yankees",
            source="polymarket", external_id="1120800", status="open",
            resolution_date=_utc(2026, 10, 12, 3, 59), mutually_exclusive=False,
            market_metadata=pm_meta, probability_change_24h=None, commence_time=None),
    }


_LEGS = {
    63551228: [(239425230, "Tampa Bay", 0.63, f"{KT}-TB"), (239425229, "New York Y", 0.365, f"{KT}-NYY")],
    63849276: [(240727158, "Rays (-1.5)", 0.445, None), (240727159, "Rays (-2.5)", 0.18, None),
               (240727157, "Yankees (-1.5)", 0.17, None), (240727160, "Yankees (-2.5)", None, None)],
    63849278: [(240727165, "Rays", 0.645, None), (240727164, "Yankees", 0.355, None)],
}


def _legs(markets):
    return {
        mid: [SimpleNamespace(id=oid, market_id=mid, name=name, current_probability=prob,
                              probability_change_24h=None, is_winner=None, resolution_source=None,
                              external_id=ext, market=markets[mid])
              for oid, name, prob, ext in rows]
        for mid, rows in _LEGS.items()
    }


def _card(market, legs):
    rows = [{"outcome_id": leg.id, "name": leg.name, "probability": leg.current_probability,
             "probability_change_24h": None, "settled": False, "is_winner": None} for leg in legs]
    return {"market_id": market.id, "market_name": market.name, "source": market.source,
            "status": market.status, "resolution_date": market.resolution_date.isoformat(),
            "outcomes": rows}


def _facts(legs_by_market, withheld=frozenset()):
    return [
        SeriesMarketFacts(
            market_id=mid, source=legs[0].market.source, external_id=legs[0].market.external_id,
            status=legs[0].market.status, resolution_date=legs[0].market.resolution_date,
            market_metadata=legs[0].market.market_metadata or {}, settled_before_the_game=False,
            legs=tuple(SeriesLeg(outcome_id=leg.id, name=leg.name, external_id=leg.external_id,
                                 probability=leg.current_probability, is_winner=leg.is_winner,
                                 withheld=leg.id in withheld) for leg in legs),
        )
        for mid, legs in legs_by_market.items()
    ]


def _build(*, cutoff=CUTOFF, compositions="compute", cards_for=None, **kw):
    markets = _markets(cutoff=cutoff)
    legs = _legs(markets)
    cards = [_card(markets[mid], legs[mid]) for mid in (cards_for or sorted(markets))]
    if compositions == "compute":
        compositions = compose_series_pairs(_facts(legs), ROSTER)
    extra = {} if compositions == "omit" else {"series_compositions": compositions}
    return build_series_question_matrix(
        formatted_series=cards, series_by_market=legs, series_withheld=set(),
        settled_before_the_game=lambda m: False, home_team="Tampa Bay Rays",
        away_team="New York Yankees", **extra, **kw,
    )


def _dump(matrix):
    return json.dumps(matrix, sort_keys=True)


def _pair():
    markets = _markets()
    (pair,) = compose_series_pairs(_facts(_legs(markets)), ROSTER)
    assert pair.composed, pair.refusal
    return pair


class TestOneQuestionWithAComposition:
    def test_the_two_winner_questions_become_one_and_the_spread_stays(self):
        m = _build()
        keys = [q["question_key"] for q in m["questions"]]
        assert keys == ["q:series_winner:2026:101-102", "m:63849276"]
        assert m["coverage"]["questions"] == 2 and m["coverage"]["options"] == 6
        assert m["series_markets_count"] == {"eligible": 3, "returned": 3}

    def test_the_merged_question_carries_both_identities(self):
        q = _build()["questions"][0]
        assert q["merged_question_keys"] == ["m:63551228", "m:63849278"]
        assert q["kind"] == "named_options" and q["display_scope"] == "series"
        assert q["source_array"] == "series_markets"
        assert q["lifecycle"] == {"state": "open", "market_status": "open"}
        assert q["complete"] is True and q["missing_options"] == []
        assert "_market_ids" not in q
        assert q["source_totals"] == [{"source": "kalshi", "raw_sum": 0.995, "legs": 2},
                                      {"source": "polymarket", "raw_sum": 1.0, "legs": 2}]

    def test_one_option_per_team_published_as_the_verified_blend(self):
        q = _build()["questions"][0]
        tb, nyy = q["options"]
        assert (tb["label"], nyy["label"]) == ("Tampa Bay Rays", "New York Yankees")
        assert tb["option_key"] == "o:239425230+240727165"
        assert nyy["option_key"] == "o:239425229+240727164"
        assert tb["side"] == "home" and nyy["side"] == "away"
        assert tb["published"] == {"value": pytest.approx(0.6375), "value_state": "quoted",
                                   "basis": "verified_series_blend", "source": None,
                                   "observed_at": None}
        assert nyy["published"]["value"] == pytest.approx(0.36)
        assert tb["contributor_outcome_ids"] == [239425230, 240727165]
        assert nyy["contributor_outcome_ids"] == [239425229, 240727164]
        assert tb["market_ids"] == [63551228, 63849278]
        assert [(e["source"], e["market_id"], e["outcome_id"], e["raw_probability"])
                for e in tb["source_evidence"]] == [
            ("kalshi", 63551228, 239425230, 0.63), ("polymarket", 63849278, 240727165, 0.645)]
        for o in q["options"]:
            assert o["result"] == {"state": "open", "evidence_kind": "none"}
            assert o["comparison"] == {"state": "unavailable", "reason": "series_baseline_unsupported",
                                       "baseline": None, "latest": None, "delta_points": None}

    def test_the_whole_serialized_question_is_this_dto(self):
        """Every field, not one count: what Native decodes is pinned whole."""
        unsupported = {"state": "unavailable", "reason": "series_baseline_unsupported",
                       "baseline": None, "latest": None, "delta_points": None}

        def evidence(source, market_id, outcome_id, side, raw):
            return {"source": source, "market_id": market_id, "outcome_id": outcome_id,
                    "leg_side": side, "raw_probability": raw, "observed_at": None}

        def option(key, label, side, ids, value, ev):
            return {"option_key": key, "label": label, "side": side,
                    "market_ids": [63551228, 63849278], "contributor_outcome_ids": ids,
                    "published": {"value": value, "value_state": "quoted",
                                  "basis": "verified_series_blend", "source": None,
                                  "observed_at": None},
                    "source_evidence": ev, "result": {"state": "open", "evidence_kind": "none"},
                    "comparison": unsupported}

        q = json.loads(json.dumps(_build()["questions"][0]))
        assert q == {
            "question_key": "q:series_winner:2026:101-102",
            "merged_question_keys": ["m:63551228", "m:63849278"],
            "proposition_key": None, "display_scope": "series", "kind": "named_options",
            "label": "Series Winner: New York Y vs Tampa Bay",
            "market_name": "Series Winner: New York Y vs Tampa Bay",
            "source_array": "series_markets", "quantity": None, "period": None,
            "subject": None, "predicate": None, "complement_question_key": None,
            "typing": {"state": "typed", "reason": None},
            "lifecycle": {"state": "open", "market_status": "open"},
            "options": [
                option("o:239425230+240727165", "Tampa Bay Rays", "home", [239425230, 240727165],
                       0.6375, [evidence("kalshi", 63551228, 239425230, "home", 0.63),
                                evidence("polymarket", 63849278, 240727165, "category", 0.645)]),
                option("o:239425229+240727164", "New York Yankees", "away", [239425229, 240727164],
                       0.36, [evidence("kalshi", 63551228, 239425229, "away", 0.365),
                              evidence("polymarket", 63849278, 240727164, "category", 0.355)]),
            ],
            "missing_options": [],
            "option_counts": {"declared": 2, "loaded": 2, "returned": 2, "missing_identified": 0},
            "complete": True,
            "source_totals": [{"source": "kalshi", "raw_sum": 0.995, "legs": 2},
                              {"source": "polymarket", "raw_sum": 1.0, "legs": 2}],
        }

    def test_the_merged_shape_is_the_legacy_shape_plus_its_merged_keys(self):
        """Native decodes the merged question with the model it already has."""
        legacy = _build(compositions="omit")["questions"][0]
        merged = _build()["questions"][0]
        assert set(merged) == set(legacy) | {"merged_question_keys"}
        assert {frozenset(o) for o in merged["options"]} == {frozenset(legacy["options"][0])}
        assert {frozenset(e) for o in merged["options"] for e in o["source_evidence"]} == {
            frozenset(legacy["options"][0]["source_evidence"][0])}

    def test_a_divergent_pair_is_never_merged(self):
        markets = _markets()
        legs = _legs(markets)
        for leg, prob in zip(legs[63849278], (0.10, 0.90)):
            leg.current_probability = prob
        pairs = compose_series_pairs(_facts(legs), ROSTER)
        assert [p.refusal for p in pairs] == ["divergence_gate"]
        cards = [_card(markets[mid], legs[mid]) for mid in sorted(markets)]
        args = dict(formatted_series=cards, series_by_market=legs, series_withheld=set(),
                    settled_before_the_game=lambda m: False, home_team="Tampa Bay Rays",
                    away_team="New York Yankees")
        assert _dump(build_series_question_matrix(**args, series_compositions=pairs)) == _dump(
            build_series_question_matrix(**args))

    def test_the_published_number_is_the_compositions_exactly(self):
        pair = _pair()
        q = _build(compositions=[pair])["questions"][0]
        assert {o["option_key"]: o["published"]["value"] for o in q["options"]} == {
            "o:" + "+".join(str(c) for c in sorted(t.contributor_outcome_ids)): t.value
            for t in pair.teams}

    def test_the_matrix_never_blends(self, monkeypatch):
        pair = _pair()
        monkeypatch.setattr(swc, "blend_with_verdict", lambda rows: pytest.fail("matrix blended"))
        monkeypatch.setattr("app.utils.futures_source_merge.blend_with_verdict",
                            lambda rows: pytest.fail("matrix blended"))
        assert _build(compositions=[pair])["questions"][0]["question_key"].startswith("q:series_winner")
        source = (BACKEND / "app/utils/event_question_matrix.py").read_text()
        code = "\n".join(line.split("#")[0] for line in source.split('"""', 2)[2].splitlines())
        for forbidden in ("blend_with_verdict", "blend_probabilities", "_weighted_median",
                          "futures_source_merge"):
            assert forbidden not in code, forbidden


class TestByteIdenticalWithout:
    def test_none_empty_and_omitted_are_one_output(self):
        omitted = _dump(_build(compositions="omit"))
        assert _dump(_build(compositions=None)) == omitted
        assert _dump(_build(compositions=[])) == omitted
        assert [q["question_key"] for q in json.loads(omitted)["questions"]] == [
            "m:63551228", "m:63849276", "m:63849278"]
        assert "merged_question_keys" not in omitted and "verified_series_blend" not in omitted

    def test_a_refused_pair_stays_two_questions(self):
        refused = compose_series_pairs(_facts(_legs(_markets(cutoff=None))), ROSTER)
        assert [p.refusal for p in refused] == ["settlement_rule_refused"]
        assert _dump(_build(cutoff=None, compositions=refused)) == _dump(
            _build(cutoff=None, compositions="omit"))

    def test_a_composition_whose_question_is_not_served_changes_nothing(self):
        """The card cap (`formatted_series[:10]`) can drop one venue's row."""
        served = [63551228, 63849276]
        assert _dump(_build(cards_for=served)) == _dump(_build(cards_for=served, compositions="omit"))

    def test_a_composition_naming_other_outcomes_changes_nothing(self):
        pair = _pair()
        teams = (dataclasses.replace(pair.teams[0], contributor_outcome_ids=(1, 2)),) + pair.teams[1:]
        assert _dump(_build(compositions=[dataclasses.replace(pair, teams=teams)])) == _dump(
            _build(compositions="omit"))

    def test_a_served_question_that_is_not_open_changes_nothing(self):
        markets = _markets()
        markets[63849278].status = "suspended"
        legs = _legs(markets)
        cards = [_card(markets[mid], legs[mid]) for mid in sorted(markets)]
        args = dict(formatted_series=cards, series_by_market=legs, series_withheld=set(),
                    settled_before_the_game=lambda m: False, home_team="Tampa Bay Rays",
                    away_team="New York Yankees")
        assert _dump(build_series_question_matrix(**args, series_compositions=[_pair()])) == _dump(
            build_series_question_matrix(**args))

    def test_a_served_option_the_composition_does_not_name_changes_nothing(self):
        """Never drop a served leg to make the merge fit."""
        markets = _markets()
        legs = _legs(markets)
        pair = _pair()
        extra = SimpleNamespace(id=239425299, market_id=63551228, name="Tie", current_probability=0.005,
                                probability_change_24h=None, is_winner=None, resolution_source=None,
                                external_id=f"{KT}-TIE", market=markets[63551228])
        legs[63551228] = legs[63551228] + [extra]
        cards = [_card(markets[mid], legs[mid]) for mid in sorted(markets)]
        args = dict(formatted_series=cards, series_by_market=legs, series_withheld=set(),
                    settled_before_the_game=lambda m: False, home_team="Tampa Bay Rays",
                    away_team="New York Yankees")
        assert _dump(build_series_question_matrix(**args, series_compositions=[pair])) == _dump(
            build_series_question_matrix(**args))

    def test_a_malformed_composition_changes_nothing(self):
        bad = dataclasses.replace(_pair(), merged_question_keys=("m:63551228",))
        assert _dump(_build(compositions=[bad])) == _dump(_build(compositions="omit"))

    def test_the_inputs_are_not_mutated(self):
        markets = _markets()
        legs = _legs(markets)
        cards = [_card(markets[mid], legs[mid]) for mid in sorted(markets)]
        before = copy.deepcopy(cards)
        build_series_question_matrix(
            formatted_series=cards, series_by_market=legs, series_withheld=set(),
            settled_before_the_game=lambda m: False, home_team="Tampa Bay Rays",
            away_team="New York Yankees",
            series_compositions=compose_series_pairs(_facts(legs), ROSTER))
        assert cards == before


# ── the route: `_build_related_futures` series block ────────────────────────


class _Result:
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


class _Row(SimpleNamespace):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return None


class _Session:
    """Answers the route's statements by what they read (the #10238 harness,
    plus the roster read). The season pass gets one leg of last season's
    settled market, which #9042 skips, so the Series card is the payload."""

    def __init__(self, event, series_outcomes):
        self.event, self.series_outcomes = event, series_outcomes
        old = SimpleNamespace(id=500, name="2025 World Series Winner", status="resolved",
                              source="kalshi", resolution_date=_utc(2025, 11, 1), external_id=None,
                              market_metadata=None, mutually_exclusive=True, market_tier=1)
        self.season = [SimpleNamespace(id=501, market_id=500, name="Tampa Bay Rays", team_id=None,
                                       current_probability=1.0, is_winner=True,
                                       resolution_source="api_settlement", market=old,
                                       probability_change_24h=None, external_id=None)]
        self.roster = [SimpleNamespace(sport_id=7, logo_url_small=None, logo_url=None,
                                       **{k: t[k] for k in ("id", "name", "abbreviation",
                                                            "location", "alternate_names")})
                       for t in ROSTER]

    async def execute(self, stmt, *args, **kwargs):
        sql = str(stmt)
        if sql.startswith("SELECT teams.id, teams.sport_id, teams.name, teams.abbreviation"):
            return _Result(rows=self.roster)
        if "FROM events" in sql and "futures" not in sql:
            return _Result(scalar=self.event)
        if "FROM sports" in sql:
            return _Result(rows=[SimpleNamespace(id=7)])
        if "FROM futures_outcomes" in sql and "ORDER BY futures_outcomes.market_id" in sql:
            return _Result(rows=self.series_outcomes)
        if "FROM futures_outcomes" in sql:
            return _Result(rows=self.season)
        if sql.startswith("SELECT futures_markets.id, futures_markets.market_tier"):
            return _Result(rows=[SimpleNamespace(id=500, market_tier=1)])
        if sql.startswith("SELECT futures_markets.id \nFROM futures_markets") and "LIMIT" in sql:
            return _Result(rows=[SimpleNamespace(id=i) for i in sorted(_LEGS)])
        return _Result(rows=[])


def _route(monkeypatch, *, withheld=frozenset(), compose=None):
    monkeypatch.setattr(events_route, "_related_futures_withheld_ids",
                        AsyncMock(return_value=set(withheld)))
    if compose is not None:
        monkeypatch.setattr(swc, "compose_series_pairs", compose)
    event = _Row(
        id=15322539, sport=SimpleNamespace(id=7, key="baseball_mlb"), sport_id=7, status="completed",
        home_team_name="Tampa Bay Rays", away_team_name="New York Yankees",
        commence_time=_utc(2026, 10, 3, 20, 8), home_team_id=None, away_team_id=None,
        period=None, game_clock=None, box_score_data=None, llm_league="MLB",
        home_score=1, away_score=0,
    )
    legs = _legs(_markets())
    outcomes = [leg for mid in sorted(legs) for leg in legs[mid]]
    response, _status, _ids, cacheable = asyncio.run(
        events_route._build_related_futures(15322539, _Session(event, outcomes)))
    assert cacheable and response["series_markets"], response.get("series_markets")
    return json.loads(json.dumps(response, default=str))


class TestTheRoute:
    def test_the_page_asks_the_series_winner_once(self, monkeypatch):
        matrix = _route(monkeypatch)["series_question_matrix"]
        assert [q["question_key"] for q in matrix["questions"]] == [
            "q:series_winner:2026:101-102", "m:63849276"]
        q = matrix["questions"][0]
        assert q["merged_question_keys"] == ["m:63551228", "m:63849278"]
        assert [o["published"]["value"] for o in q["options"]] == [
            pytest.approx(0.6375), pytest.approx(0.36)]

    def test_every_served_list_is_byte_identical_with_and_without_the_composition(self, monkeypatch):
        with_it = _route(monkeypatch)
        without = _route(monkeypatch, compose=lambda markets, teams: [])
        assert len(with_it["series_question_matrix"]["questions"]) == 2
        assert len(without["series_question_matrix"]["questions"]) == 3
        assert sorted(with_it) == sorted(without)
        for key in sorted(set(with_it) - {"series_question_matrix"}):
            assert json.dumps(with_it[key], sort_keys=True) == json.dumps(
                without[key], sort_keys=True), key
        assert [s["market_id"] for s in with_it["series_markets"]] == [63551228, 63849276, 63849278]

    def test_a_withheld_leg_reaches_the_rule_and_refuses(self, monkeypatch):
        matrix = _route(monkeypatch, withheld={240727165})["series_question_matrix"]
        assert [q["question_key"] for q in matrix["questions"]] == [
            "m:63551228", "m:63849276", "m:63849278"]

    def test_an_error_in_the_rule_leaves_the_matrix_as_today(self, monkeypatch):
        def boom(markets, teams):
            raise RuntimeError("correspondence failed")

        broken = _route(monkeypatch, compose=boom)
        plain = _route(monkeypatch, compose=lambda markets, teams: [])
        assert broken["series_question_matrix"] is not None
        assert json.dumps(broken, sort_keys=True) == json.dumps(plain, sort_keys=True)
