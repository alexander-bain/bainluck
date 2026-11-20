"""Guard tests for #13142: NCAA St/State and NC State twin folding & retrieval."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_twin_fold import (
    _college_squash,
    fold_twin_events,
    team_name_fold_key,
    twin_fold_key,
)
from app.utils.prediction_market_matching import _expand_team_search_terms


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
