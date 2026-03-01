"""Tests for event taxonomy tag computation."""

import pytest
from datetime import datetime, timezone, timedelta

from app.utils.event_taxonomy import (
    compute_event_tags,
    validate_tag,
    ALLOWED_TAGS,
    _extract_sport,
    _extract_league,
    _extract_timing,
    _extract_signals,
    _ei_label,
)
from app.utils.highlights import EventFlags, HighlightResult


# ── Test helpers ──────────────────────────────────────────────────────

def _make_time(weekday: int = 0, hour: int = 12) -> datetime:
    """Create a datetime with a specific weekday and hour in US Eastern (UTC-5).

    Hour is in Eastern time. The returned datetime is in UTC.
    """
    # Start from a known Monday (2026-03-02)
    base = datetime(2026, 3, 2, tzinfo=timezone.utc)
    # Advance to target weekday
    target = base + timedelta(days=weekday)
    # Set hour in Eastern (add 5 to get UTC equivalent)
    utc_hour = hour + 5
    if utc_hour >= 24:
        target = target + timedelta(days=1)
        utc_hour -= 24
    return target.replace(hour=utc_hour, minute=0, second=0)


# ── TestExtractSport ──────────────────────────────────────────────────

class TestExtractSport:
    def test_basketball_prefix(self):
        assert _extract_sport("basketball_nba") == "basketball"

    def test_football_prefix(self):
        assert _extract_sport("americanfootball_nfl") == "football"

    def test_hockey_prefix(self):
        assert _extract_sport("icehockey_nhl") == "hockey"

    def test_soccer_prefix(self):
        assert _extract_sport("soccer_epl") == "soccer"

    def test_unknown_sport(self):
        assert _extract_sport("quidditch_hogwarts") is None

    def test_empty_key(self):
        assert _extract_sport("") is None

    def test_rugby_league_prefix(self):
        assert _extract_sport("rugbyleague_nrl") == "rugby"

    def test_rugby_union_prefix(self):
        assert _extract_sport("rugbyunion_six_nations") == "rugby"


# ── TestExtractLeague ─────────────────────────────────────────────────

class TestExtractLeague:
    def test_nba_from_sport_key(self):
        assert _extract_league("basketball_nba", None) == "nba"

    def test_epl_from_sport_key(self):
        assert _extract_league("soccer_epl", None) == "epl"

    def test_llm_league_takes_precedence(self):
        # If llm_league maps to a valid value, use it
        assert _extract_league("basketball_nba", "NBA") == "nba"

    def test_llm_league_invalid_falls_back(self):
        # Invalid llm_league falls back to sport_key
        assert _extract_league("basketball_nba", "SomethingWeird") == "nba"

    def test_unknown_sport_key_no_league(self):
        assert _extract_league("quidditch_hogwarts", None) is None

    def test_champions_league(self):
        assert _extract_league("soccer_uefa_champs_league", None) == "champions_league"


# ── TestTierAndClass ──────────────────────────────────────────────────

class TestTierAndClass:
    def test_tier_1_nba(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
        )
        assert "tier:1" in tags

    def test_tier_4_unknown(self):
        tags = compute_event_tags(
            sport_key="quidditch_hogwarts",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
        )
        assert "tier:4" in tags

    def test_class_pro_major_nfl(self):
        tags = compute_event_tags(
            sport_key="americanfootball_nfl",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
        )
        assert "class:pro_major" in tags

    def test_class_college_ncaab(self):
        tags = compute_event_tags(
            sport_key="basketball_ncaab",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
        )
        assert "class:college" in tags


# ── TestImportance ────────────────────────────────────────────────────

class TestImportance:
    def test_championship(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            llm_importance="championship",
        )
        assert "importance:championship" in tags

    def test_playoff(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            llm_importance="playoff",
        )
        assert "importance:playoff" in tags

    def test_exhibition(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            llm_importance="exhibition",
        )
        assert "importance:exhibition" in tags

    def test_none_importance(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            llm_importance=None,
        )
        # No importance tag
        assert not any(t.startswith("importance:") for t in tags)


# ── TestGenderAndLevel ────────────────────────────────────────────────

class TestGenderAndLevel:
    def test_women(self):
        tags = compute_event_tags(
            sport_key="basketball_wnba",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            llm_gender="women",
        )
        assert "gender:women" in tags

    def test_college_level(self):
        tags = compute_event_tags(
            sport_key="basketball_ncaab",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            llm_level="college",
        )
        assert "level:college" in tags

    def test_invalid_gender_excluded(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            llm_gender="unknown",
        )
        assert not any(t.startswith("gender:") for t in tags)


# ── TestStatus ────────────────────────────────────────────────────────

class TestStatus:
    def test_live(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
        )
        assert "status:live" in tags

    def test_scheduled(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
        )
        assert "status:scheduled" in tags

    def test_completed(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="completed",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
        )
        assert "status:completed" in tags


# ── TestEI ────────────────────────────────────────────────────────────

class TestEI:
    def test_incredible(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="completed",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            raw_ei=0.95,  # 95 → incredible
        )
        assert "ei:incredible" in tags

    def test_exciting(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="completed",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            raw_ei=0.72,  # 72 → exciting
        )
        assert "ei:exciting" in tags

    def test_flat(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="completed",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            raw_ei=0.10,  # 10 → flat
        )
        assert "ei:flat" in tags

    def test_none_ei(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            raw_ei=None,
        )
        assert not any(t.startswith("ei:") for t in tags)


# ── TestTiming ────────────────────────────────────────────────────────

class TestTiming:
    def test_weekend_saturday(self):
        # Saturday in Eastern
        sat_utc = _make_time(weekday=5, hour=14)  # Saturday 2pm ET → 7pm UTC
        tags: set[str] = set()
        _extract_timing(sat_utc, None, tags)
        assert "timing:weekend" in tags

    def test_weekday_monday(self):
        mon_utc = _make_time(weekday=0, hour=14)  # Monday 2pm ET
        tags: set[str] = set()
        _extract_timing(mon_utc, None, tags)
        assert "timing:weekend" not in tags

    def test_primetime(self):
        # 8pm Eastern → 1am UTC next day
        prime_utc = _make_time(weekday=1, hour=20)  # Tuesday 8pm ET
        tags: set[str] = set()
        _extract_timing(prime_utc, None, tags)
        assert "timing:primetime" in tags

    def test_national_tv(self):
        tags: set[str] = set()
        _extract_timing(
            datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            "ESPN, ESPN+",
            tags,
        )
        assert "timing:national_tv" in tags

    def test_no_national_tv(self):
        tags: set[str] = set()
        _extract_timing(
            datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            "Bally Sports",
            tags,
        )
        assert "timing:national_tv" not in tags


# ── TestSignals ───────────────────────────────────────────────────────

class TestSignals:
    def test_close_matchup(self):
        flags = EventFlags(is_close_matchup=True)
        tags: set[str] = set()
        _extract_signals(flags, tags)
        assert "signal:close_matchup" in tags

    def test_upset(self):
        flags = EventFlags(is_upset=True)
        tags: set[str] = set()
        _extract_signals(flags, tags)
        assert "signal:upset" in tags

    def test_line_moving(self):
        flags = EventFlags(probability_swing="major")
        tags: set[str] = set()
        _extract_signals(flags, tags)
        assert "signal:line_moving" in tags

    def test_multiple_signals(self):
        flags = EventFlags(
            is_close_matchup=True,
            is_volatile=True,
            has_lead_changes=True,
        )
        tags: set[str] = set()
        _extract_signals(flags, tags)
        assert "signal:close_matchup" in tags
        assert "signal:volatile" in tags
        assert "signal:lead_changes" in tags

    def test_no_highlight_result(self):
        """When highlight_result is None, no signal tags."""
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            highlight_result=None,
        )
        assert not any(t.startswith("signal:") for t in tags)


# ── TestIntegration ───────────────────────────────────────────────────

class TestIntegration:
    def test_full_live_nba_game(self):
        """Full integration: live NBA game with upset, close, volatile."""
        flags = EventFlags(
            is_live=True,
            is_close_matchup=True,
            is_very_close=True,
            favorite_switched=True,
            is_volatile=True,
            has_lead_changes=True,
        )
        hr = HighlightResult(score=85, flags=flags)
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=datetime(2026, 3, 1, 1, 0, tzinfo=timezone.utc),  # 8pm ET Sat
            llm_importance="regular_season",
            llm_gender="men",
            llm_level="professional",
            llm_league="NBA",
            raw_ei=0.82,
            broadcast_info="ESPN, ABC",
            highlight_result=hr,
        )
        assert "sport:basketball" in tags
        assert "league:nba" in tags
        assert "tier:1" in tags
        assert "class:pro_major" in tags
        assert "level:professional" in tags
        assert "gender:men" in tags
        assert "importance:regular_season" in tags
        assert "status:live" in tags
        assert "signal:close_matchup" in tags
        assert "signal:very_close" in tags
        assert "signal:favorite_switched" in tags
        assert "signal:volatile" in tags
        assert "signal:lead_changes" in tags
        assert "ei:must_watch" in tags
        assert "timing:national_tv" in tags

    def test_minimal_scheduled(self):
        """Minimal event: only sport_key, status, commence_time."""
        tags = compute_event_tags(
            sport_key="soccer_epl",
            status="scheduled",
            commence_time=datetime(2026, 3, 3, 20, 0, tzinfo=timezone.utc),
        )
        assert "sport:soccer" in tags
        assert "league:epl" in tags
        assert "tier:1" in tags
        assert "class:international" in tags
        assert "status:scheduled" in tags
        # No signal, ei, gender, level, importance tags
        assert not any(t.startswith("signal:") for t in tags)
        assert not any(t.startswith("ei:") for t in tags)

    def test_sorted_unique(self):
        """Output is sorted and has no duplicates."""
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
            llm_importance="playoff",
            raw_ei=0.75,
        )
        assert tags == sorted(tags)
        assert len(tags) == len(set(tags))


# ── TestValidation ────────────────────────────────────────────────────

class TestValidation:
    def test_valid_tag(self):
        assert validate_tag("sport:basketball") is True
        assert validate_tag("tier:1") is True
        assert validate_tag("signal:upset") is True

    def test_invalid_tag(self):
        assert validate_tag("sport:quidditch") is False
        assert validate_tag("invalid_format") is False
        assert validate_tag("unknown_namespace:value") is False
        assert validate_tag("tier:5") is False


# ── TestEILabel ───────────────────────────────────────────────────────

class TestEILabel:
    def test_thresholds(self):
        assert _ei_label(95) == "incredible"
        assert _ei_label(90) == "incredible"
        assert _ei_label(85) == "must_watch"
        assert _ei_label(80) == "must_watch"
        assert _ei_label(75) == "exciting"
        assert _ei_label(65) == "engaging"
        assert _ei_label(55) == "competitive"
        assert _ei_label(45) == "average"
        assert _ei_label(30) == "quiet"
        assert _ei_label(10) == "flat"
        assert _ei_label(1) == "flat"


# ── TestAllowedTags completeness ──────────────────────────────────────

class TestAllowedTags:
    def test_all_namespaces_have_values(self):
        """Every namespace in ALLOWED_TAGS has at least one allowed value."""
        for ns, values in ALLOWED_TAGS.items():
            assert len(values) > 0, f"Namespace {ns} has no allowed values"

    def test_golf_sport(self):
        tags = compute_event_tags(
            sport_key="golf_pga",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
        )
        assert "sport:golf" in tags

    def test_mma_sport(self):
        tags = compute_event_tags(
            sport_key="mma_mixed_martial_arts",
            status="scheduled",
            commence_time=datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc),
        )
        assert "sport:mma" in tags
        assert "league:ufc" in tags
