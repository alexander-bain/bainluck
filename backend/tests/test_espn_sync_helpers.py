"""Tests for ESPN sync helper functions extracted to module level.

These functions were previously nested inside the 897-line
_sync_espn_live_events function and untestable.
"""

from types import SimpleNamespace

from app.tasks.espn_sync import (
    _espn_names_match_any,
    get_event_name_variations,
    get_espn_name_variants,
    espn_team_matches,
)


class TestEspnNamesMatchAny:

    def test_exact_match(self):
        assert _espn_names_match_any(["Boston Celtics"], "Boston Celtics")

    def test_suffix_match(self):
        assert _espn_names_match_any(["Celtics"], "Boston Celtics")

    def test_no_match(self):
        assert not _espn_names_match_any(["Los Angeles Lakers"], "Boston Celtics")

    def test_empty_espn_name(self):
        assert not _espn_names_match_any(["Celtics"], "")

    def test_none_espn_name(self):
        assert not _espn_names_match_any(["Celtics"], None)

    def test_multiple_our_names_any_matches(self):
        assert _espn_names_match_any(
            ["BOS", "Celtics", "Boston Celtics"],
            "Boston Celtics",
        )

    def test_empty_our_names(self):
        assert not _espn_names_match_any([], "Celtics")

    def test_none_in_our_names_skipped(self):
        assert _espn_names_match_any([None, "Celtics"], "Boston Celtics")


class TestGetEventNameVariations:

    def test_basic_names(self):
        event = SimpleNamespace(
            home_team_name="Boston Celtics",
            away_team_name="Los Angeles Lakers",
            home_team_normalized=None,
            away_team_normalized=None,
            home_team_alt_names=None,
            away_team_alt_names=None,
        )
        home, away = get_event_name_variations(event)
        assert home == ["Boston Celtics"]
        assert away == ["Los Angeles Lakers"]

    def test_includes_normalized(self):
        event = SimpleNamespace(
            home_team_name="Boston Celtics",
            away_team_name="LA Lakers",
            home_team_normalized="boston celtics",
            away_team_normalized="los angeles lakers",
            home_team_alt_names=None,
            away_team_alt_names=None,
        )
        home, away = get_event_name_variations(event)
        assert "boston celtics" in home
        assert "los angeles lakers" in away

    def test_includes_alt_names(self):
        event = SimpleNamespace(
            home_team_name="Boston Celtics",
            away_team_name="Lakers",
            home_team_normalized=None,
            away_team_normalized=None,
            home_team_alt_names=["BOS", "Celtics"],
            away_team_alt_names=["LAL", "Los Angeles Lakers"],
        )
        home, away = get_event_name_variations(event)
        assert "BOS" in home
        assert "Celtics" in home
        assert "LAL" in away


class TestGetEspnNameVariants:

    def test_all_fields(self):
        team = SimpleNamespace(
            display_name="Boston Celtics",
            short_name="Celtics",
            name="Celtics",
            location="Boston",
        )
        variants = get_espn_name_variants(team)
        assert "Boston Celtics" in variants
        assert "Celtics" in variants
        assert "Boston" in variants
        assert len(variants) == 3  # "Celtics" deduped

    def test_none_fields_skipped(self):
        team = SimpleNamespace(
            display_name="Celtics",
            short_name=None,
            name=None,
            location=None,
        )
        variants = get_espn_name_variants(team)
        assert variants == ["Celtics"]


class TestEspnTeamMatches:

    def test_matches_display_name(self):
        team = SimpleNamespace(
            display_name="Boston Celtics",
            short_name="Celtics",
            name="Celtics",
            location="Boston",
        )
        assert espn_team_matches(["Boston Celtics"], team)

    def test_matches_short_name(self):
        team = SimpleNamespace(
            display_name="Boston Celtics",
            short_name="Celtics",
            name="Celtics",
            location="Boston",
        )
        assert espn_team_matches(["Celtics"], team)

    def test_no_match(self):
        team = SimpleNamespace(
            display_name="Boston Celtics",
            short_name="Celtics",
            name="Celtics",
            location="Boston",
        )
        assert not espn_team_matches(["Los Angeles Lakers"], team)


class TestBoxScoreDrainMode:
    """Guard for the #816 one-shot cohort-drain knob on _backfill_box_scores.

    The period-score re-fetch gate is newest-first by default, so the oldest
    stuck cohort (Feb/Mar NCAAB 1H espn_id events) never gets reached by bounded
    runs. oldest_first=True flips the gate to ascending for a one-shot drain.
    The default MUST stay False so the live beat keeps its newest-first behavior.
    """

    def test_oldest_first_param_exists_and_defaults_false(self):
        import inspect
        from app.tasks.espn_sync import _backfill_box_scores

        sig = inspect.signature(_backfill_box_scores)
        assert "oldest_first" in sig.parameters
        assert sig.parameters["oldest_first"].default is False
        # The live beat calls priority_calibration without oldest_first; that
        # path must remain newest-first.
        assert sig.parameters["priority_calibration"].default is False
