"""#10407 A1 — when Kalshi's and Polymarket's series winner are one question.

PILLARS: MATCHING / TRUTH. SHIP: a playoff game page asks "who wins the
series" once, with one blended number; each venue keeps its own no-winner rules.

Specimens are the retained public evidence (shopper,
`~/bainluck-dev/shopper/artifacts/shopper/10407-series-identity/`, read
2026-10-04 15:11–15:13Z): our served markets 63551228 / 63849278 (NYY–TB ALDS)
and 63621762 / 63849227 (SD–MIL NLDS), Kalshi events KXMLBSERIES-26NYYTBALDS /
-26SDMILNLDS (expected expiration 10-18 22:30Z / 10-19 00:30Z), and Gamma
events 1120800 / 1120859 (stated cutoffs 10-24 / 10-23 11:59 PM ET). Prices
are the served ones. Team ids are synthetic; names and abbreviations are the
clubs'. The spread row's slug is synthetic — the real spread market is not in
Gamma event 1120800, which is the point.
"""

from __future__ import annotations

import dataclasses
import inspect
from datetime import datetime, timezone

import pytest

from app.utils import series_winner_correspondence as swc
from app.utils.futures_source_merge import blend_with_verdict
from app.utils.series_winner_correspondence import (
    SeriesLeg,
    SeriesMarketFacts,
    SeriesMember,
    compose_series_pairs,
    series_member,
)
from app.utils.futures_verified_title import title_team_index

TB, NYY, NYM, SD, MIL = 101, 102, 103, 104, 105
ROSTER = [
    {"id": TB, "name": "Tampa Bay Rays", "abbreviation": "TB", "location": "Tampa Bay",
     "alternate_names": ["Rays"]},
    {"id": NYY, "name": "New York Yankees", "abbreviation": "NYY", "location": "New York",
     "alternate_names": ["Yankees", "New York"]},
    {"id": NYM, "name": "New York Mets", "abbreviation": "NYM", "location": "New York",
     "alternate_names": ["Mets", "New York"]},
    {"id": SD, "name": "San Diego Padres", "abbreviation": "SD", "location": "San Diego",
     "alternate_names": ["Padres"]},
    {"id": MIL, "name": "Milwaukee Brewers", "abbreviation": "MIL", "location": "Milwaukee",
     "alternate_names": ["Brewers"]},
]


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def _cutoff(at="2026-10-25T03:59:00+00:00", **over):
    return {"at": at, "source": "polymarket_rules_text", "family": "mlb_series_winner",
            "clauses": 2, **over}


def _leg(oid, name, prob, external_id=None, *, is_winner=None, withheld=False):
    return SeriesLeg(outcome_id=oid, name=name, external_id=external_id, probability=prob,
                     is_winner=is_winner, withheld=withheld)


def kalshi_nyy_tb(**over):
    t = "KXMLBSERIES-26NYYTBALDS"
    base = dict(
        market_id=63551228, source="kalshi", external_id=t, status="open",
        resolution_date=_utc(2026, 10, 18, 22, 30), market_metadata={"kalshi_event_ticker": t},
        settled_before_the_game=False,
        legs=(_leg(239425230, "Tampa Bay", 0.63, f"{t}-TB"),
              _leg(239425229, "New York Y", 0.365, f"{t}-NYY")),
    )
    base.update(over)
    return SeriesMarketFacts(**base)


def poly_nyy_tb(**over):
    meta = {"polymarket_event_id": "1120800",
            "polymarket_event_slug": "mlb-playoffs-who-will-win-series-rays-vs-yankees",
            "no_winner_cutoff": _cutoff()}
    meta.update(over.pop("meta", {}))
    base = dict(
        market_id=63849278, source="polymarket", external_id="1120800", status="open",
        resolution_date=_utc(2026, 10, 12, 3, 59), market_metadata=meta,
        settled_before_the_game=False,
        legs=(_leg(240727165, "Rays", 0.645), _leg(240727164, "Yankees", 0.355)),
    )
    base.update(over)
    return SeriesMarketFacts(**base)


def kalshi_sd_mil():
    t = "KXMLBSERIES-26SDMILNLDS"
    return SeriesMarketFacts(
        market_id=63621762, source="kalshi", external_id=t, status="open",
        resolution_date=_utc(2026, 10, 19, 0, 30), market_metadata={"kalshi_event_ticker": t},
        settled_before_the_game=False,
        legs=(_leg(239687440, "Milwaukee", 0.715, f"{t}-MIL"),
              _leg(239687441, "San Diego", 0.275, f"{t}-SD")),
    )


def poly_sd_mil():
    return SeriesMarketFacts(
        market_id=63849227, source="polymarket", external_id="1120859", status="open",
        resolution_date=_utc(2026, 10, 11, 3, 59),
        market_metadata={"polymarket_event_id": "1120859",
                         "polymarket_event_slug": "mlb-playoffs-who-will-win-series-brewers-vs-padres",
                         "no_winner_cutoff": _cutoff("2026-10-24T03:59:00+00:00")},
        settled_before_the_game=False,
        legs=(_leg(240726964, "Brewers", 0.72), _leg(240726965, "Padres", 0.28)),
    )


def poly_spread():
    return SeriesMarketFacts(
        market_id=63849276, source="polymarket", external_id="1120799", status="open",
        resolution_date=_utc(2026, 10, 12, 3, 59),
        market_metadata={"polymarket_event_id": "1120799",
                         "polymarket_event_slug": "mlb-playoffs-series-spread-rays-vs-yankees"},
        settled_before_the_game=False,
        legs=(_leg(240727158, "Rays (-1.5)", 0.445), _leg(240727159, "Rays (-2.5)", 0.18),
              _leg(240727157, "Yankees (-1.5)", 0.17), _leg(240727160, "Yankees (-2.5)", None)),
    )


def _pairs(*markets):
    return compose_series_pairs(list(markets), ROSTER)


def _one(*markets):
    pairs = _pairs(*markets)
    assert len(pairs) == 1, pairs
    return pairs[0]


class TestBothSpecimenPairsCompose:
    def test_yankees_rays(self):
        pair = _one(kalshi_nyy_tb(), poly_nyy_tb())
        assert pair.composed, pair.refusal
        assert pair.season == 2026 and pair.team_pair == (TB, NYY)
        assert pair.question_key == "q:series_winner:2026:101-102"
        assert pair.merged_question_keys == ("m:63551228", "m:63849278")
        assert pair.contributor_market_ids == (63551228, 63849278)
        by_team = {t.team_id: t for t in pair.teams}
        assert by_team[TB].contributor_outcome_ids == (239425230, 240727165)
        assert by_team[NYY].contributor_outcome_ids == (239425229, 240727164)
        assert by_team[TB].value == pytest.approx(0.6375)
        assert by_team[NYY].value == pytest.approx(0.36)
        assert {t.rule for t in pair.teams} == {"equal_weight_midpoint"}
        assert by_team[TB].name == "Tampa Bay Rays"

    def test_padres_brewers(self):
        pair = _one(kalshi_sd_mil(), poly_sd_mil())
        assert pair.composed, pair.refusal
        assert pair.question_key == "q:series_winner:2026:104-105"
        by_team = {t.team_id: t for t in pair.teams}
        assert by_team[MIL].contributor_outcome_ids == (239687440, 240726964)
        assert by_team[MIL].value == pytest.approx(0.7175)

    def test_both_pairs_on_one_input_compose_separately(self):
        pairs = _pairs(kalshi_nyy_tb(), poly_nyy_tb(), kalshi_sd_mil(), poly_sd_mil())
        assert [p.question_key for p in pairs] == [
            "q:series_winner:2026:101-102", "q:series_winner:2026:104-105"]
        assert all(p.composed for p in pairs)

    def test_the_number_is_blend_with_verdicts_unchanged(self):
        pair = _one(kalshi_nyy_tb(), poly_nyy_tb())
        tb = next(t for t in pair.teams if t.team_id == TB)
        assert (tb.value, None, tb.rule) == blend_with_verdict([
            {"probability": 0.63, "source": "kalshi"},
            {"probability": 0.645, "source": "polymarket"},
        ])


class TestSettlement:
    def test_kalshis_instant_before_the_cutoff_composes(self):
        assert _one(kalshi_nyy_tb(), poly_nyy_tb()).composed

    def test_a_cutoff_before_kalshis_instant_refuses(self):
        p = poly_nyy_tb(meta={"no_winner_cutoff": _cutoff("2026-10-18T00:00:00+00:00")})
        assert _one(kalshi_nyy_tb(), p).refusal == "settlement_rule_refused"

    def test_a_cutoff_equal_to_kalshis_instant_refuses(self):
        p = poly_nyy_tb(meta={"no_winner_cutoff": _cutoff("2026-10-18T22:30:00+00:00")})
        assert _one(kalshi_nyy_tb(), p).refusal == "settlement_rule_refused"

    def test_a_missing_cutoff_refuses(self):
        p = poly_nyy_tb()
        meta = {k: v for k, v in p.market_metadata.items() if k != "no_winner_cutoff"}
        assert _one(kalshi_nyy_tb(), dataclasses.replace(p, market_metadata=meta)).refusal == (
            "settlement_rule_refused")

    @pytest.mark.parametrize("bad", [
        _cutoff(source="gamma_end_date"), _cutoff(family="pro_football_title"),
        _cutoff(at="2026-10-25T03:59:00"), _cutoff(at=None), "2026-10-25T03:59:00+00:00",
    ])
    def test_a_cutoff_not_written_by_the_rules_text_reader_refuses(self, bad):
        p = poly_nyy_tb(meta={"no_winner_cutoff": bad})
        assert _one(kalshi_nyy_tb(), p).refusal == "settlement_rule_refused"

    def test_polymarkets_own_end_date_is_never_the_cutoff(self):
        """The stored PM `resolution_date` (Gamma endDate 10-12) is later than nothing
        here — if it were read as the cutoff, Kalshi's 10-18 would refuse."""
        assert poly_nyy_tb().resolution_date < kalshi_nyy_tb().resolution_date
        assert _one(kalshi_nyy_tb(), poly_nyy_tb()).composed

    def test_neg_risk_false_alone_does_not_refuse(self):
        p = poly_nyy_tb(meta={"neg_risk": False})
        assert _one(kalshi_nyy_tb(), p).composed

    def test_neg_risk_true_alone_does_not_admit(self):
        p = poly_nyy_tb(meta={"neg_risk": True})
        meta = {k: v for k, v in p.market_metadata.items() if k != "no_winner_cutoff"}
        assert _one(kalshi_nyy_tb(), dataclasses.replace(p, market_metadata=meta)).refusal == (
            "settlement_rule_refused")
        three = dataclasses.replace(p, legs=p.legs + (_leg(9, "Other", 0.01),))
        assert series_member(three, title_team_index(ROSTER)) == "leg_count"


class TestIdentity:
    def test_kalshi_teams_come_from_each_legs_own_ticker(self):
        """`New York Y` resolves to nothing by name; the `-NYY` leg ticker names the club."""
        m = series_member(kalshi_nyy_tb(), title_team_index(ROSTER))
        assert isinstance(m, SeriesMember)
        assert m.leg_by_team[NYY].outcome_id == 239425229
        assert m.round_label == "ALDS" and m.season == 2026

    def test_a_kalshi_name_naming_another_club_vetoes_its_ticker(self):
        k = kalshi_nyy_tb()
        legs = (k.legs[0], dataclasses.replace(k.legs[1], name="New York Mets"))
        assert series_member(dataclasses.replace(k, legs=legs), title_team_index(ROSTER)) == (
            "team_unresolved")

    def test_an_ambiguous_alias_refuses(self):
        p = poly_nyy_tb(legs=(_leg(240727165, "Rays", 0.645), _leg(240727164, "New York", 0.355)))
        assert series_member(p, title_team_index(ROSTER)) == "team_unresolved"
        assert _one(kalshi_nyy_tb(), p).refusal == "single_venue"

    def test_a_bare_city_is_not_an_alias(self):
        """`title_team_index` drops `location`: "Tampa Bay" alone names no club."""
        p = poly_nyy_tb(legs=(_leg(240727165, "Tampa Bay", 0.645), _leg(240727164, "Yankees", 0.355)))
        assert series_member(p, title_team_index(ROSTER)) == "team_unresolved"

    def test_two_outcomes_naming_one_club_refuse(self):
        p = poly_nyy_tb(legs=(_leg(1, "Rays", 0.6), _leg(2, "Tampa Bay Rays", 0.4)))
        assert series_member(p, title_team_index(ROSTER)) == "teams_not_distinct"

    def test_a_different_year_is_a_different_series(self):
        p = poly_nyy_tb(resolution_date=_utc(2025, 10, 12, 3, 59))
        pairs = _pairs(kalshi_nyy_tb(), p)
        assert [(x.season, x.refusal) for x in pairs] == [(2025, "single_venue"), (2026, "single_venue")]

    def test_a_kalshi_ticker_year_that_disagrees_with_its_date_refuses(self):
        k = kalshi_nyy_tb(resolution_date=_utc(2027, 10, 18, 22, 30))
        assert series_member(k, title_team_index(ROSTER)) == "season_mismatch"

    def test_a_disagreeing_round_label_refuses(self):
        index = title_team_index(ROSTER)
        k = series_member(kalshi_nyy_tb(), index)
        p = dataclasses.replace(series_member(poly_nyy_tb(), index), round_label="ALCS")
        facts = {63551228: kalshi_nyy_tb(), 63849278: poly_nyy_tb()}
        refused = swc._compose(2026, (TB, NYY), [k, p], facts, {})
        assert refused.refusal == "round_label_disagrees"
        agreeing = dataclasses.replace(p, round_label="ALDS")
        assert swc._compose(2026, (TB, NYY), [k, agreeing], facts, {}).composed

    def test_two_polymarket_rows_for_one_series_refuse(self):
        twin = poly_nyy_tb(market_id=63849999, external_id="1120801",
                           meta={"polymarket_event_id": "1120801"})
        assert _one(kalshi_nyy_tb(), poly_nyy_tb(), twin).refusal == "duplicate_per_venue"

    def test_two_kalshi_rows_for_one_series_refuse(self):
        t = "KXMLBSERIES-26TBNYYALDS"
        twin = kalshi_nyy_tb(market_id=63559999, external_id=t,
                             market_metadata={"kalshi_event_ticker": t},
                             legs=(_leg(1, "Tampa Bay", 0.6, f"{t}-TB"),
                                   _leg(2, "New York Y", 0.4, f"{t}-NYY")))
        assert _one(kalshi_nyy_tb(), twin, poly_nyy_tb()).refusal == "duplicate_per_venue"

    def test_a_stored_event_ticker_that_disagrees_refuses(self):
        k = kalshi_nyy_tb(market_metadata={"kalshi_event_ticker": "KXMLBSERIES-26NYMTBALDS"})
        assert series_member(k, title_team_index(ROSTER)) == "event_ticker_mismatch"

    def test_a_leg_from_another_event_refuses(self):
        k = kalshi_nyy_tb()
        legs = (k.legs[0], dataclasses.replace(k.legs[1], external_id="KXMLBSERIES-26NYYBOSALDS-NYY"))
        assert series_member(dataclasses.replace(k, legs=legs), title_team_index(ROSTER)) == (
            "leg_not_of_event")

    def test_a_polymarket_child_row_is_not_the_event(self):
        p = poly_nyy_tb(external_id="5215308")
        assert series_member(p, title_team_index(ROSTER)) == "event_id_mismatch"
        multi = poly_nyy_tb(meta={"market_count": 2})
        assert series_member(multi, title_team_index(ROSTER)) == "not_one_market"


class TestLifecycle:
    @pytest.mark.parametrize("which", ["kalshi", "poly"])
    def test_a_settled_leg_composes_nothing(self, which):
        for verdict in (True, False):
            k, p = kalshi_nyy_tb(), poly_nyy_tb()
            target = k if which == "kalshi" else p
            legs = (dataclasses.replace(target.legs[0], is_winner=verdict), target.legs[1])
            target = dataclasses.replace(target, legs=legs)
            k, p = (target, p) if which == "kalshi" else (k, target)
            assert _one(k, p).refusal == "leg_settled"

    def test_a_withheld_leg_composes_nothing(self):
        p = poly_nyy_tb()
        p = dataclasses.replace(p, legs=(dataclasses.replace(p.legs[0], withheld=True), p.legs[1]))
        assert _one(kalshi_nyy_tb(), p).refusal == "leg_withheld"

    def test_a_market_settled_before_the_game_composes_nothing(self):
        k = kalshi_nyy_tb(settled_before_the_game=True)
        assert _one(k, poly_nyy_tb()).refusal == "settled_before_the_game"

    @pytest.mark.parametrize("status", ["resolved", "closed", "suspended", None])
    def test_a_market_that_is_not_open_composes_nothing(self, status):
        assert _one(kalshi_nyy_tb(status=status), poly_nyy_tb()).refusal == "not_open"


class TestDivergenceAndPrice:
    def test_legs_beyond_the_gate_compose_nothing(self):
        p = poly_nyy_tb(legs=(_leg(240727165, "Rays", 0.10), _leg(240727164, "Yankees", 0.90)))
        assert _one(kalshi_nyy_tb(), p).refusal == "divergence_gate"

    def test_an_unpriced_leg_composes_nothing(self):
        p = poly_nyy_tb(legs=(_leg(240727165, "Rays", None), _leg(240727164, "Yankees", 0.355)))
        assert _one(kalshi_nyy_tb(), p).refusal == "unpriced_leg"

    def test_a_zero_is_a_price(self):
        k = kalshi_nyy_tb()
        k = dataclasses.replace(k, legs=(dataclasses.replace(k.legs[0], probability=0.0), k.legs[1]))
        p = poly_nyy_tb(legs=(_leg(240727165, "Rays", 0.0), _leg(240727164, "Yankees", 0.355)))
        assert _one(k, p).composed


class TestControlsStaySeparate:
    def test_the_series_spread_is_not_a_member(self):
        assert series_member(poly_spread(), title_team_index(ROSTER)) == "not_series_winner"
        pairs = _pairs(kalshi_nyy_tb(), poly_nyy_tb(), poly_spread())
        assert [p.market_ids for p in pairs] == [(63551228, 63849278)]

    def test_an_adjacent_game_winner_is_not_a_member(self):
        t = "KXMLBGAME-26OCT041605NYYTB"
        game = kalshi_nyy_tb(market_id=1, external_id=t, market_metadata={},
                             legs=(_leg(1, "Tampa Bay", 0.5, f"{t}-TB"),
                                   _leg(2, "New York Y", 0.5, f"{t}-NYY")))
        assert series_member(game, title_team_index(ROSTER)) == "not_series_winner"

    @pytest.mark.parametrize("make", [kalshi_nyy_tb, poly_nyy_tb])
    def test_a_single_venue_stays_separate(self, make):
        assert _one(make()).refusal == "single_venue"

    def test_another_source_is_never_a_member(self):
        assert series_member(kalshi_nyy_tb(source="odds_api"), title_team_index(ROSTER)) == (
            "not_series_winner")


def test_the_module_never_reads_commence_time_neg_risk_or_a_clock():
    source = inspect.getsource(swc)
    code = "\n".join(line.split("#")[0] for line in source.split('"""', 2)[2].splitlines())
    for forbidden in ("commence_time", "neg_risk", "now(", "mutually_exclusive", "canonical_market_key"):
        assert forbidden not in code, forbidden
    assert "blend_with_verdict(" in code
