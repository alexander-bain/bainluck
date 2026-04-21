"""Tests for utils/related_futures.py — extracted dedup and formatting logic."""

from app.utils.related_futures import dedup_by_merge_group


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
