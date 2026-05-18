"""Tests for utils/related_futures.py — extracted dedup and formatting logic."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils.related_futures import build_futures_entry, dedup_by_merge_group


def _make_future(merge_group=None, outcome_name="Team A", source="odds_api", bookmaker_count=1):
    return {
        "merge_group": merge_group,
        "outcome_name": outcome_name,
        "source": source,
        "bookmaker_count": bookmaker_count,
        "market_id": hash(f"{merge_group}:{outcome_name}:{source}"),
    }


class TestDedupByMergeGroup:

    def test_no_merge_group_kept_as_is(self):
        futures = [_make_future(merge_group=None, outcome_name="X")]
        result = dedup_by_merge_group(futures)
        assert len(result) == 1

    def test_same_merge_group_different_outcomes_kept(self):
        futures = [
            _make_future("championship", "Team A", "odds_api"),
            _make_future("championship", "Team B", "odds_api"),
        ]
        result = dedup_by_merge_group(futures)
        assert len(result) == 2

    def test_same_merge_group_same_outcome_deduped(self):
        futures = [
            _make_future("championship", "Team A", "odds_api", bookmaker_count=5),
            _make_future("championship", "Team A", "kalshi", bookmaker_count=1),
        ]
        result = dedup_by_merge_group(futures)
        assert len(result) == 1
        assert result[0]["source"] == "odds_api"
        assert "all_sources" in result[0]
        assert set(result[0]["all_sources"]) == {"odds_api", "kalshi"}

    def test_per_team_group_deduped_by_merge_group_alone(self):
        futures = [
            _make_future("win_total", "Boston Celtics", "odds_api", bookmaker_count=3),
            _make_future("win_total", "Yes", "kalshi", bookmaker_count=1),
        ]
        result = dedup_by_merge_group(futures)
        assert len(result) == 1
        assert result[0]["source"] == "odds_api"

    def test_division_suffix_treated_as_per_team(self):
        futures = [
            _make_future("atlantic_division", "Celtics", "odds_api"),
            _make_future("atlantic_division", "Yes: Celtics", "kalshi"),
        ]
        result = dedup_by_merge_group(futures)
        assert len(result) == 1

    def test_conf_champion_suffix_treated_as_per_team(self):
        futures = [
            _make_future("eastern_conf_champion", "Celtics", "polymarket"),
            _make_future("eastern_conf_champion", "Boston Celtics", "odds_api"),
        ]
        result = dedup_by_merge_group(futures)
        assert len(result) == 1

    def test_highest_bookmaker_count_wins(self):
        futures = [
            _make_future("championship", "Team A", "kalshi", bookmaker_count=1),
            _make_future("championship", "Team A", "odds_api", bookmaker_count=10),
            _make_future("championship", "Team A", "polymarket", bookmaker_count=1),
        ]
        result = dedup_by_merge_group(futures)
        assert len(result) == 1
        assert result[0]["source"] == "odds_api"
        assert len(result[0]["all_sources"]) == 3

    def test_empty_input(self):
        assert dedup_by_merge_group([]) == []

    def test_single_entry_no_dedup_needed(self):
        futures = [_make_future("championship", "Team A")]
        result = dedup_by_merge_group(futures)
        assert len(result) == 1
        assert "all_sources" not in result[0]

    def test_mixed_grouped_and_ungrouped(self):
        futures = [
            _make_future(None, "Ungrouped 1"),
            _make_future("championship", "Team A", "odds_api"),
            _make_future("championship", "Team A", "kalshi"),
            _make_future(None, "Ungrouped 2"),
        ]
        result = dedup_by_merge_group(futures)
        assert len(result) == 3
        ungrouped = [r for r in result if r["merge_group"] is None]
        assert len(ungrouped) == 2

    def test_make_playoffs_is_per_team(self):
        futures = [
            _make_future("make_playoffs", "Boston Celtics", "odds_api"),
            _make_future("make_playoffs", "Yes", "kalshi"),
        ]
        result = dedup_by_merge_group(futures)
        assert len(result) == 1

    def test_same_outcome_dedup_is_case_insensitive(self):
        futures = [
            _make_future("nba_champion", "Boston Celtics", "kalshi", bookmaker_count=1),
            _make_future("nba_champion", "boston celtics", "polymarket", bookmaker_count=4),
        ]

        result = dedup_by_merge_group(futures)

        assert len(result) == 1
        assert result[0]["source"] == "polymarket"
        assert set(result[0]["all_sources"]) == {"kalshi", "polymarket"}

    @pytest.mark.parametrize(
        "merge_group",
        [
            "western_conf_1_seed",
            "eastern_conf_playin",
            "make_nfl_playoffs",
            "make_nhl_playoffs",
            "make_mlb_playoffs",
        ],
    )
    def test_per_team_merge_group_variants_ignore_outcome_shape(self, merge_group):
        futures = [
            _make_future(merge_group, "Team Name", "odds_api", bookmaker_count=2),
            _make_future(merge_group, "Yes", "kalshi", bookmaker_count=1),
        ]

        result = dedup_by_merge_group(futures)

        assert len(result) == 1
        assert result[0]["source"] == "odds_api"

    def test_non_per_team_group_keeps_yes_no_outcomes_separate(self):
        futures = [
            _make_future("series_winner", "Yes", "kalshi"),
            _make_future("series_winner", "No", "kalshi"),
        ]

        result = dedup_by_merge_group(futures)

        assert len(result) == 2
        assert {item["outcome_name"] for item in result} == {"Yes", "No"}

    def test_all_sources_ignores_missing_source_values(self):
        futures = [
            _make_future("nba_champion", "Boston Celtics", "kalshi", bookmaker_count=2),
            _make_future("nba_champion", "Boston Celtics", None, bookmaker_count=1),
        ]

        result = dedup_by_merge_group(futures)

        assert len(result) == 1
        assert result[0]["all_sources"] == ["kalshi"]


def _make_market(**overrides):
    values = {
        "id": 10,
        "name": "NBA Champion",
        "market_tier": 1,
        "category": "championship",
        "source": "kalshi",
        "resolution_date": datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _make_outcome(**overrides):
    values = {
        "id": 20,
        "name": "Jayson Tatum: MVP",
        "current_probability": 0.42,
        "current_american_odds": 138,
        "probability_change_24h": 0.03,
        "opening_probability": 0.31,
        "rank": 2,
        "last_updated": datetime(2026, 5, 17, 12, 30, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TestBuildFuturesEntry:

    def test_builds_serializable_entry_with_market_and_outcome_fields(self):
        entry = build_futures_entry(
            market=_make_market(),
            outcome=_make_outcome(),
            relevance_score=0.87,
            relevance_reason="high movement",
            clean_label="NBA Champion",
            display_category="playoff_path",
            merge_group="nba_champion",
            stage_display="Finals",
            stage_type="final",
            stage_order=4,
            bookmaker_count=5,
            next_update_iso="2026-05-17T13:00:00+00:00",
        )

        assert entry == {
            "market_id": 10,
            "market_name": "NBA Champion",
            "clean_label": "NBA Champion",
            "display_category": "playoff_path",
            "merge_group": "nba_champion",
            "playoff_stage": "Finals",
            "playoff_stage_type": "final",
            "stage_order": 4,
            "market_tier": 1,
            "category": "championship",
            "source": "kalshi",
            "outcome_id": 20,
            "outcome_name": "Jayson Tatum: MVP",
            "probability": 0.42,
            "american_odds": 138,
            "probability_change_24h": 0.03,
            "opening_probability": 0.31,
            "rank": 2,
            "relevance_score": 0.87,
            "relevance_reason": "high movement",
            "last_updated": "2026-05-17T12:30:00+00:00",
            "next_update_expected": "2026-05-17T13:00:00+00:00",
            "resolution_date": "2026-06-18T00:00:00+00:00",
            "bookmaker_count": 5,
        }

    def test_omits_optional_dates_and_numeric_fields_when_missing(self):
        entry = build_futures_entry(
            market=_make_market(resolution_date=None),
            outcome=_make_outcome(
                current_probability=None,
                probability_change_24h=None,
                opening_probability=None,
                last_updated=None,
            ),
            relevance_score=0.1,
            relevance_reason="low relevance",
            clean_label="NBA Champion",
            display_category="playoff_path",
            merge_group=None,
            stage_display=None,
            stage_type=None,
            stage_order=None,
            bookmaker_count=1,
            next_update_iso="2026-05-17T13:00:00+00:00",
        )

        assert entry["probability"] is None
        assert entry["probability_change_24h"] is None
        assert entry["opening_probability"] is None
        assert entry["last_updated"] is None
        assert entry["resolution_date"] is None

    def test_attaches_player_metadata_using_name_before_colon(self):
        entry = build_futures_entry(
            market=_make_market(),
            outcome=_make_outcome(name="Jayson Tatum: 30+ Points"),
            relevance_score=0.7,
            relevance_reason="player prop",
            clean_label="Player Points",
            display_category="player_prop",
            merge_group="player_points",
            stage_display=None,
            stage_type=None,
            stage_order=None,
            bookmaker_count=3,
            next_update_iso="2026-05-17T13:00:00+00:00",
            player_metadata={
                "jayson tatum": {
                    "name": "Jayson Tatum",
                    "espn_id": "4065648",
                    "headshot": "https://example.test/tatum.png",
                }
            },
        )

        assert entry["matched_player"] == {
            "name": "Jayson Tatum",
            "espn_id": "4065648",
            "headshot": "https://example.test/tatum.png",
        }
