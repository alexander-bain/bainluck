"""Tests for ESPN sync helper functions extracted to module level.

These functions were previously nested inside the 897-line
_sync_espn_live_events function and untestable.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.tasks.espn_sync import (
    _espn_names_match_any,
    get_event_name_variations,
    get_espn_name_variants,
    espn_team_matches,
    _apply_final_pm_win_prob,
    _is_bogus_future_settled,
)


class TestIsBogusFutureSettled:
    """Queue #234 Item 2 / gotcha #32/#46: a SETTLED event cannot start in the
    future (invariant completed_at >= commence_time). The cross-merge recurrence
    (#190) leaves a stale settlement stuck on a row whose commence_time was
    overwritten to a future series game. Only rows with NO real result get
    un-settled — a real score is a distinct class and must be preserved."""

    NOW = datetime(2026, 7, 22, 19, 0, tzinfo=timezone.utc)

    def test_settled_future_commence_zero_zero_is_bogus(self):
        # The exact production case: Phillies@Dodgers completed, 0-0, commence tonight.
        commence = datetime(2026, 7, 22, 22, 40, tzinfo=timezone.utc)
        assert _is_bogus_future_settled("completed", commence, 0, 0, self.NOW) is True

    def test_settled_future_commence_null_scores_is_bogus(self):
        commence = self.NOW + timedelta(hours=48)
        assert _is_bogus_future_settled("closed", commence, None, None, self.NOW) is True

    def test_settled_future_commence_real_score_is_preserved(self):
        # A genuinely-played game whose commence got overwritten (Direction B) —
        # must NOT be matched, or un-settling would destroy the 5-0 result.
        commence = self.NOW + timedelta(hours=48)
        assert _is_bogus_future_settled("completed", commence, 5, 0, self.NOW) is False
        assert _is_bogus_future_settled("completed", commence, 0, 3, self.NOW) is False

    def test_legit_completed_past_commence_untouched(self):
        # The normal case: a settled game started in the past — invariant holds.
        commence = self.NOW - timedelta(hours=4)
        assert _is_bogus_future_settled("completed", commence, 0, 0, self.NOW) is False

    def test_scheduled_future_commence_not_matched(self):
        commence = self.NOW + timedelta(hours=5)
        assert _is_bogus_future_settled("scheduled", commence, None, None, self.NOW) is False

    def test_near_now_future_within_tolerance_not_matched(self):
        # 30-min future: settlement/refinement race tolerance — leave it.
        commence = self.NOW + timedelta(minutes=30)
        assert _is_bogus_future_settled("completed", commence, 0, 0, self.NOW) is False


class TestApplyFinalPmWinProb:
    """#1000: bare-float win_probability_sources entries must not crash the
    live→closed transition (TypeError: 'float' object item assignment)."""

    def test_bare_float_entry_does_not_crash(self):
        wps = {"kalshi": 0.62, "polymarket": 0.58}
        out = _apply_final_pm_win_prob(wps, 1.0)
        assert out["kalshi"] == 1.0
        assert out["polymarket"] == 1.0
        assert out["final_result"] == 1.0

    def test_dict_entry_sets_value_key(self):
        wps = {"kalshi": {"value": 0.62, "weight": 0.8}}
        out = _apply_final_pm_win_prob(wps, 0.0)
        assert out["kalshi"]["value"] == 0.0
        assert out["kalshi"]["weight"] == 0.8  # preserved

    def test_mixed_shapes(self):
        wps = {"kalshi": {"value": 0.7}, "polymarket": 0.4, "espn": {"value": 0.5}}
        out = _apply_final_pm_win_prob(wps, 1.0)
        assert out["kalshi"]["value"] == 1.0
        assert out["polymarket"] == 1.0
        assert out["espn"] == {"value": 0.5}  # untouched (not a PM source)

    def test_missing_sources_and_none_input(self):
        assert _apply_final_pm_win_prob(None, 1.0) == {"final_result": 1.0}
        assert _apply_final_pm_win_prob({}, 0.5) == {"final_result": 0.5}

    def test_does_not_mutate_input(self):
        wps = {"kalshi": {"value": 0.62}}
        _apply_final_pm_win_prob(wps, 1.0)
        assert wps["kalshi"]["value"] == 0.62  # original untouched


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
