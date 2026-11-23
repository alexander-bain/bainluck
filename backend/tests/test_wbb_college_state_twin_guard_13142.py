"""Guard tests for #13142: NCAA St/State and NC State twin folding & retrieval."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks import prediction_market_matching as pmm
from app.utils.event_twin_fold import (
    _college_squash,
    _squash_for_league,
    fold_twin_events,
    team_name_fold_key,
    twin_fold_key,
)
from app.utils.prediction_market_matching import (
    MatchupInfo,
    _expand_team_search_terms,
    _fuzzy_team_match,
    normalize_wbb_mascot,
    wbb_mascot_variants,
)


def _make_event(
    event_id: int,
    *,
    sport_key: str = "basketball_wncaab",
    sport_id: int = 10,
    away: str,
    home: str,
    commence_time: datetime = datetime(2025, 11, 20, 1, 0, tzinfo=timezone.utc),
    status: str = "live",
    external_id: str | None = None,
    espn_id: str | None = None,
    home_score: int | None = None,
    away_score: int | None = None,
    sources: dict | None = None,
    event_tags: list[str] | None = None,
    opening_home_probability: float | None = None,
    opening_away_probability: float | None = None,
):
    return SimpleNamespace(
        id=event_id,
        sport_id=sport_id,
        sport=SimpleNamespace(key=sport_key),
        away_team_name=away,
        home_team_name=home,
        commence_time=commence_time,
        status=status,
        external_id=external_id,
        espn_id=espn_id,
        home_score=home_score,
        away_score=away_score,
        event_tags=event_tags,
        opening_home_probability=opening_home_probability,
        opening_away_probability=opening_away_probability,
        win_probability_sources=dict(sources or {}),
    )


class TestCollegeStateTwinFold13142:
    def test_live_new_mexico_st_vs_state_folds_onto_sportsbook_row_with_polymarket_blended(
        self,
    ):
        """Exact #13142 live case: 15351654 + 15348230 collapse to one card even while live."""
        sportsbook_row = _make_event(
            15351654,
            away="New Mexico St Aggies",
            home="Arizona Wildcats",
            status="live",
            external_id="ead7cf26dee416dad667d2149fac6b34",
            home_score=57,
            away_score=53,
            sources={
                "stat_model": {"value": 0.9077},
                "betting_book_count": {"value": 2.0},
            },
        )
        polymarket_row = _make_event(
            15348230,
            away="New Mexico State Aggies",
            home="Arizona Wildcats",
            status="live",
            external_id=None,
            home_score=None,
            away_score=None,
            sources={"polymarket": {"value": 0.92}},
        )

        result = fold_twin_events([sportsbook_row, polymarket_row])
        assert result.folded_count == 1
        assert result.dropped_ids == [15348230]
        assert [e.id for e in result.events] == [15351654]
        assert result.events[0].home_score == 57
        assert result.events[0].away_score == 53
        assert "polymarket" in result.merged_sources[15351654]
        assert result.merged_sources[15351654]["polymarket"]["value"] == 0.92
        assert result.merged_sources[15351654]["stat_model"]["value"] == 0.9077

    def test_nc_state_vs_north_carolina_state_folds_onto_sportsbook_row(self):
        """Second #13142 pair: 15351490 + 15347867 collapse cleanly."""
        sportsbook_row = _make_event(
            15351490,
            away="Georgetown Hoyas",
            home="NC State Wolfpack",
            commence_time=datetime(2025, 11, 20, 0, 0, tzinfo=timezone.utc),
            status="completed",
            external_id="1c4e8373bbe2be0e9c28e95d8f3fe11f",
            sources={"espn": {"value": 0.96}, "stat_model": {"value": 0.99}},
        )
        idless_row = _make_event(
            15347867,
            away="Georgetown Hoyas",
            home="North Carolina State Wolfpack",
            commence_time=datetime(2025, 11, 20, 0, 0, tzinfo=timezone.utc),
            status="suspended",
            external_id=None,
            sources={"polymarket": {"value": 0.95}},
        )

        result = fold_twin_events([sportsbook_row, idless_row])
        assert result.folded_count == 1
        assert result.dropped_ids == [15347867]
        assert [e.id for e in result.events] == [15351490]
        assert "polymarket" in result.merged_sources[15351490]

    @pytest.mark.parametrize(
        "odds_name,pm_name",
        [
            ("Grambling St Tigers", "Grambling State Tigers"),
            ("Alcorn St Braves", "Alcorn State Braves"),
            ("Cal St Fullerton Titans", "Cal State Fullerton Titans"),
            ("Oklahoma St Cowgirls", "Oklahoma State Cowgirls"),
            ("Mississippi Valley St Delta Devils", "Mississippi Valley State Delta Devils"),
            ("NC St Wolfpack", "North Carolina State Wolfpack"),
        ],
    )
    def test_upcoming_state_abbreviations_fold_in_wncaab(self, odds_name, pm_name):
        a = _make_event(
            1001,
            away=odds_name,
            home="Central Arkansas Bears",
            status="scheduled",
            external_id="odds_1001",
            sources={"betting": {"value": 0.6}},
        )
        b = _make_event(
            1002,
            away=pm_name,
            home="Central Arkansas Bears",
            status="scheduled",
            external_id=None,
            sources={"polymarket": {"value": 0.62}},
        )
        result = fold_twin_events([a, b])
        assert result.folded_count == 1
        assert [e.id for e in result.events] == [1001]

    def test_saint_schools_and_distinct_colleges_never_false_fold(self):
        assert _college_squash("St. John's Red Storm") == "stjohnsredstorm"
        assert _college_squash("Mount St. Mary's Mountaineers") == "mountstmarysmountaineers"
        assert _college_squash("St. Bonaventure Bonnies") == "stbonaventurebonnies"

        # Distinct colleges must never collide
        kansas = _make_event(
            2001, away="Kansas Jayhawks", home="Duke Blue Devils", status="scheduled", external_id="k1"
        )
        kansas_st = _make_event(
            2002, away="Kansas State Wildcats", home="Duke Blue Devils", status="scheduled"
        )
        assert fold_twin_events([kansas, kansas_st]).folded_count == 0

        # Doubleheader at different minutes must never fold
        g1 = _make_event(
            2003,
            away="New Mexico St Aggies",
            home="Arizona Wildcats",
            commence_time=datetime(2025, 11, 20, 1, 0, tzinfo=timezone.utc),
            status="scheduled",
            external_id="g1",
        )
        g2 = _make_event(
            2004,
            away="New Mexico State Aggies",
            home="Arizona Wildcats",
            commence_time=datetime(2025, 11, 20, 4, 0, tzinfo=timezone.utc),
            status="scheduled",
        )
        assert fold_twin_events([g1, g2]).folded_count == 0

    def test_non_ncaa_leagues_and_team_name_fold_key_are_untouched(self):
        mlb = _make_event(
            3001,
            sport_key="baseball_mlb",
            sport_id=1,
            away="St. Louis Cardinals",
            home="New York Mets",
            status="scheduled",
            external_id="mlb1",
        )
        key = twin_fold_key(mlb)
        assert key is not None
        assert key[1] == "stlouiscardinals"
        assert team_name_fold_key("New Mexico St Aggies") == "newmexicostaggies"
        assert team_name_fold_key("New Mexico State Aggies") == "newmexicostateaggies"


class TestCollegeStateSearchTermExpansion13142:
    def test_symmetric_state_and_nc_state_retrieval_terms(self):
        assert "New Mexico St Aggies" in _expand_team_search_terms("New Mexico State Aggies")
        assert "New Mexico St" in _expand_team_search_terms("New Mexico State")
        assert "New Mexico State Aggies" in _expand_team_search_terms("New Mexico St Aggies")
        assert "NC State Wolfpack" in _expand_team_search_terms("North Carolina State Wolfpack")
        assert "NC State" in _expand_team_search_terms("North Carolina State")
        assert "North Carolina State Wolfpack" in _expand_team_search_terms("NC State Wolfpack")

    def test_saint_schools_do_not_expand_to_state(self):
        for saint in ("St. John's Red Storm", "Mount St. Mary's Mountaineers"):
            terms = _expand_team_search_terms(saint)
            assert all("State" not in t for t in terms), f"Unexpected State expansion: {terms}"


class TestWbbCowboysCowgirlsAndMenGuard13142:
    def test_live_oklahoma_st_cowgirls_vs_cowboys_folds_on_wncaab(self):
        """Exact #13142 live case: 15352801 + 15347911 collapse to one WBB card."""
        sportsbook_row = _make_event(
            15352801,
            away="Wichita St Shockers",
            home="Oklahoma St Cowgirls",
            commence_time=datetime(2026, 11, 22, 22, 0, tzinfo=timezone.utc),
            status="live",
            external_id="odds-15352801",
            sources={"espn": {"value": 0.001}, "stat_model": {"value": 0.999}},
        )
        polymarket_claim = _make_event(
            15347911,
            away="Wichita State Shockers",
            home="Oklahoma State Cowboys",
            commence_time=datetime(2026, 11, 22, 22, 0, tzinfo=timezone.utc),
            status="live",
            external_id=None,
            sources={"polymarket": {"value": 0.9965}},
        )

        result = fold_twin_events([sportsbook_row, polymarket_claim])
        assert result.folded_count == 1
        assert result.dropped_ids == [15347911]
        assert [e.id for e in result.events] == [15352801]
        assert result.merged_sources[15352801]["polymarket"]["value"] == pytest.approx(0.9965)

    def test_wyoming_cowboys_cowgirls_fold_in_wncaab(self):
        sportsbook_row = _make_event(
            2001,
            away="Wyoming Cowgirls",
            home="Colorado St Rams",
            commence_time=datetime(2026, 11, 22, 21, 0, tzinfo=timezone.utc),
            status="scheduled",
            external_id="odds-2001",
            sources={"betting": {"value": 0.62}},
        )
        polymarket_claim = _make_event(
            2002,
            away="Wyoming Cowboys",
            home="Colorado State Rams",
            commence_time=datetime(2026, 11, 22, 21, 0, tzinfo=timezone.utc),
            status="scheduled",
            external_id=None,
            sources={"polymarket": {"value": 0.60}},
        )

        result = fold_twin_events([sportsbook_row, polymarket_claim])
        assert result.folded_count == 1
        assert [e.id for e in result.events] == [2001]
        assert result.merged_sources[2001]["polymarket"]["value"] == pytest.approx(0.60)

    def test_mens_basketball_ncaab_never_equates_cowboys_and_cowgirls(self):
        assert _squash_for_league(
            "Oklahoma State Cowboys", "basketball_wncaab"
        ) == _squash_for_league("Oklahoma St Cowgirls", "basketball_wncaab")
        assert _squash_for_league(
            "Oklahoma State Cowboys", "basketball_ncaab"
        ) != _squash_for_league("Oklahoma St Cowgirls", "basketball_ncaab")
        assert _fuzzy_team_match("Oklahoma State Cowboys", "Oklahoma State Cowgirls") is False

        mens_row = _make_event(
            3001,
            sport_key="basketball_ncaab",
            away="Wichita State Shockers",
            home="Oklahoma State Cowboys",
            commence_time=datetime(2026, 11, 22, 22, 0, tzinfo=timezone.utc),
            status="scheduled",
            external_id="odds-3001",
            sources={"betting": {"value": 0.70}},
        )
        wbb_claim = _make_event(
            3002,
            sport_key="basketball_ncaab",
            away="Wichita State Shockers",
            home="Oklahoma State Cowgirls",
            commence_time=datetime(2026, 11, 22, 22, 0, tzinfo=timezone.utc),
            status="scheduled",
            external_id=None,
            sources={"polymarket": {"value": 0.68}},
        )
        assert twin_fold_key(mens_row) != twin_fold_key(wbb_claim)
        result = fold_twin_events([mens_row, wbb_claim])
        assert result.folded_count == 0
        assert [e.id for e in result.events] == [3001, 3002]


class TestWbbReversedAnchoredClaim13142:
    def test_scheduled_reversed_wbb_claim_15352902_15348085_folds_and_flips_prob(self):
        """Exact #13142 pair: 15352902 + 15348085 fold with Polymarket inverted 0.53 -> 0.47."""
        sportsbook_row = _make_event(
            15352902,
            away="Kansas St Wildcats",
            home="Missouri Tigers",
            commence_time=datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc),
            status="scheduled",
            external_id="odds-15352902",
            sources={"betting": {"value": 0.4718}},
            opening_home_probability=0.45,
            opening_away_probability=0.55,
        )
        polymarket_claim = _make_event(
            15348085,
            away="Missouri Tigers",
            home="Kansas State Wildcats",
            commence_time=datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc),
            status="scheduled",
            external_id=None,
            sources={"polymarket": {"value": 0.53}},
            opening_home_probability=0.54,
            opening_away_probability=0.46,
        )

        result = fold_twin_events([sportsbook_row, polymarket_claim])
        assert result.folded_count == 1
        assert result.dropped_ids == [15348085]
        assert [e.id for e in result.events] == [15352902]
        assert result.merged_sources[15352902]["polymarket"]["value"] == pytest.approx(0.47)

    def test_live_reversed_wbb_claim_with_live_state_changed_at_folds_and_inverts(self):
        sportsbook_row = _make_event(
            15352902,
            away="Kansas St Wildcats",
            home="Missouri Tigers",
            commence_time=datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc),
            status="live",
            external_id="odds-15352902",
            sources={"betting": {"value": 0.4718}},
        )
        polymarket_claim = _make_event(
            15348085,
            away="Missouri Tigers",
            home="Kansas State Wildcats",
            commence_time=datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc),
            status="live",
            external_id=None,
            sources={
                "polymarket": {"value": 0.53},
                "live_state_changed_at": "2026-11-23T00:35:00+00:00",
            },
        )

        result = fold_twin_events([sportsbook_row, polymarket_claim])
        assert result.folded_count == 1
        assert result.dropped_ids == [15348085]
        assert [e.id for e in result.events] == [15352902]
        assert result.merged_sources[15352902]["polymarket"]["value"] == pytest.approx(0.47)
        assert (
            result.merged_sources[15352902]["live_state_changed_at"]
            == "2026-11-23T00:35:00+00:00"
        )

    def test_reversed_claim_refuses_different_minute_both_anchored_or_other_leagues(self):
        # 1) Different minute refuses
        sb = _make_event(
            4001,
            away="Kansas St Wildcats",
            home="Missouri Tigers",
            commence_time=datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc),
            status="scheduled",
            external_id="odds-4001",
            sources={"betting": {"value": 0.47}},
        )
        diff_min = _make_event(
            4002,
            away="Missouri Tigers",
            home="Kansas State Wildcats",
            commence_time=datetime(2026, 11, 23, 0, 31, tzinfo=timezone.utc),
            status="scheduled",
            external_id=None,
            sources={"polymarket": {"value": 0.53}},
        )
        assert fold_twin_events([sb, diff_min]).folded_count == 0

        # 2) Both anchored refuses
        both_anchored = _make_event(
            4003,
            away="Missouri Tigers",
            home="Kansas State Wildcats",
            commence_time=datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc),
            status="scheduled",
            external_id="odds-4003",
            sources={"polymarket": {"value": 0.53}},
        )
        assert fold_twin_events([sb, both_anchored]).folded_count == 0

        # 3) Non-allowlisted league (e.g. basketball_ncaab) refuses reversed twins
        ncaab_a = _make_event(
            4004,
            sport_key="basketball_ncaab",
            away="Kansas St Wildcats",
            home="Missouri Tigers",
            commence_time=datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc),
            status="scheduled",
            external_id="odds-4004",
            sources={"betting": {"value": 0.47}},
        )
        ncaab_b = _make_event(
            4005,
            sport_key="basketball_ncaab",
            away="Missouri Tigers",
            home="Kansas State Wildcats",
            commence_time=datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc),
            status="scheduled",
            external_id=None,
            sources={"polymarket": {"value": 0.53}},
        )
        assert fold_twin_events([ncaab_a, ncaab_b]).folded_count == 0


class TestWbbMatcherEndToEnd13142:
    def test_wbb_mascot_variants_and_normalization(self):
        assert wbb_mascot_variants("Oklahoma State Cowboys") == ["Oklahoma State Cowgirls"]
        assert wbb_mascot_variants("Oklahoma State Cowgirls") == ["Oklahoma State Cowboys"]
        assert wbb_mascot_variants("Arizona Wildcats") == []
        assert normalize_wbb_mascot("Wyoming Cowboys") == "Wyoming Cowgirls"

    def test_market_is_wbb_detection(self):
        cwbb_market = SimpleNamespace(
            external_id="pm-cwbb-1",
            name="Wichita State vs. Oklahoma State",
            llm_sport_category="basketball",
            market_metadata={"polymarket_event_slug": "cwbb-wichst-okst-2026-11-22"},
        )
        women_paren_market = SimpleNamespace(
            external_id="pm-w-2",
            name="Wichita State vs. Oklahoma State (W)",
            llm_sport_category="basketball",
            market_metadata={},
        )
        wncaab_tagged_market = SimpleNamespace(
            external_id="pm-w-3",
            name="Kansas State vs Missouri",
            llm_sport_category="basketball_wncaab",
            market_metadata={},
        )
        mens_cbb_market = SimpleNamespace(
            external_id="pm-cbb-1",
            name="Wichita State vs. Oklahoma State",
            llm_sport_category="basketball",
            market_metadata={"polymarket_event_slug": "cbb-wichst-okst-2026-11-22"},
        )
        assert pmm._market_is_wbb(cwbb_market) is True
        assert pmm._market_is_wbb(women_paren_market) is True
        assert pmm._market_is_wbb(wncaab_tagged_market) is True
        assert pmm._market_is_wbb(mens_cbb_market) is False

    def test_score_candidates_matches_cwbb_cowboys_market_to_wncaab_cowgirls_and_refuses_ncaab(self):
        now = datetime(2026, 11, 22, 22, 0, tzinfo=timezone.utc)
        wncaab_sportsbook = _make_event(
            15352801,
            sport_key="basketball_wncaab",
            sport_id=10,
            away="Wichita St Shockers",
            home="Oklahoma St Cowgirls",
            commence_time=now,
            status="live",
            external_id="odds-15352801",
        )
        ncaab_men_row = _make_event(
            999001,
            sport_key="basketball_ncaab",
            sport_id=11,
            away="Wichita St Shockers",
            home="Oklahoma St Cowboys",
            commence_time=now,
            status="live",
            external_id="odds-999001",
        )
        cwbb_market = SimpleNamespace(
            id=8801,
            source="polymarket",
            external_id="pm-cwbb-okst-1",
            name="Wichita State vs. Oklahoma State (W)",
            llm_sport_category="basketball",
            commence_time=now,
            market_metadata={"polymarket_event_slug": "cwbb-wichst-okst-2026-11-22"},
        )
        matchup = MatchupInfo(
            team_a="Wichita State",
            team_b="Oklahoma State Cowboys",
            yes_team="Wichita State",
            format_type="vs",
        )

        # WBB market matches the basketball_wncaab Cowgirls row cleanly
        matched = pmm._score_candidates(
            [wncaab_sportsbook], matchup, cwbb_market, now,
        )
        assert matched is not None
        assert matched["event_id"] == 15352801

        # Men's basketball_ncaab Cowboys row is NOT matched by the Cowgirls market and
        # if only a basketball_ncaab "Cowgirls" row were tested with Cowboys matchup on a
        # men's cbb market, the WBB mascot fallback does NOT fire.
        mens_market = SimpleNamespace(
            id=8802,
            source="polymarket",
            external_id="pm-cbb-okst-2",
            name="Wichita State vs. Oklahoma State",
            llm_sport_category="basketball",
            commence_time=now,
            market_metadata={"polymarket_event_slug": "cbb-wichst-okst-2026-11-22"},
        )
        ncaab_cowgirls_hypothetical = _make_event(
            999002,
            sport_key="basketball_ncaab",
            sport_id=11,
            away="Wichita St Shockers",
            home="Oklahoma St Cowgirls",
            commence_time=now,
            status="live",
            external_id="odds-999002",
        )
        assert pmm._score_candidates(
            [ncaab_cowgirls_hypothetical], matchup, mens_market, now,
        ) is None

        # A men's cbb "Cowgirls" market does not coerce to a basketball_ncaab Cowboys row.
        mens_cowgirls_matchup = MatchupInfo(
            team_a="Wichita State",
            team_b="Oklahoma State Cowgirls",
            yes_team="Wichita State",
            format_type="vs",
        )
        assert pmm._score_candidates(
            [ncaab_men_row], mens_cowgirls_matchup, mens_market, now,
        ) is None

        # Even if a basketball_ncaab Cowgirls row existed, a cwbb WBB market only applies
        # mascot normalization on event.sport.key == "basketball_wncaab".
        assert pmm._score_candidates(
            [ncaab_cowgirls_hypothetical], matchup, cwbb_market, now,
        ) is None

        # When both an id-less WBB Cowboys claim and a sportsbook WBB Cowgirls row
        # exist, the cwbb market selects the sportsbook WBB row (15352801).
        idless_wbb_cowboys = _make_event(
            15347911,
            sport_key="basketball_wncaab",
            sport_id=10,
            away="Wichita State Shockers",
            home="Oklahoma State Cowboys",
            commence_time=now,
            status="live",
            external_id=None,
        )
        preferred = pmm._score_candidates(
            [idless_wbb_cowboys, wncaab_sportsbook], matchup, cwbb_market, now,
        )
        assert preferred is not None
        assert preferred["event_id"] == 15352801
