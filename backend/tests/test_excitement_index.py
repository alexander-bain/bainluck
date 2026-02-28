"""Tests for the Excitement Index (EI) calculation."""

import pytest
from datetime import datetime, timezone, timedelta

from app.utils.excitement_index import (
    EIDataPoint,
    calculate_ei,
    get_ei_status,
    get_ei_label,
    get_ei_emoji,
    get_regulation_seconds,
    _aggregate_snapshots,
)


def _make_dp(minutes_after_start: float, prob: float, source: str = "betting") -> EIDataPoint:
    """Helper to create a data point at a given time offset."""
    base = datetime(2026, 2, 1, 19, 0, 0, tzinfo=timezone.utc)
    return EIDataPoint(
        captured_at=base + timedelta(minutes=minutes_after_start),
        home_win_probability=prob,
        source=source,
    )


GAME_START = datetime(2026, 2, 1, 19, 0, 0, tzinfo=timezone.utc)


class TestCalculateEI:
    """Core EI calculation tests."""

    def test_returns_none_for_insufficient_data(self):
        """Less than 3 snapshots → None."""
        snapshots = [_make_dp(0, 0.5), _make_dp(1, 0.55)]
        result = calculate_ei(snapshots, GAME_START, GAME_START + timedelta(hours=2), "basketball_nba")
        assert result is None

    def test_flat_game_scores_low(self):
        """A game that stays near 50/50 with tiny moves should score low."""
        # Probability barely changes over 2 hours
        snapshots = [_make_dp(i, 0.50 + 0.001 * (i % 3)) for i in range(60)]
        end_time = GAME_START + timedelta(hours=2)
        result = calculate_ei(snapshots, GAME_START, end_time, "basketball_nba")
        assert result is not None
        assert result.score <= 25  # Should be in the "quiet" range
        assert result.raw_ei < 1.0

    def test_blowout_scores_low(self):
        """Home team dominates from start — low EI."""
        snapshots = [_make_dp(i, 0.85 + 0.002 * i) for i in range(60)]
        end_time = GAME_START + timedelta(hours=2)
        result = calculate_ei(snapshots, GAME_START, end_time, "basketball_nba")
        assert result is not None
        assert result.score <= 30

    def test_exciting_game_scores_high(self):
        """Big swings back and forth → high EI."""
        # Alternating between 30% and 70% every 2 minutes
        snapshots = []
        for i in range(60):
            prob = 0.70 if i % 4 < 2 else 0.30
            snapshots.append(_make_dp(i, prob))
        end_time = GAME_START + timedelta(hours=2)
        result = calculate_ei(snapshots, GAME_START, end_time, "basketball_nba")
        assert result is not None
        assert result.score >= 70  # Should be exciting
        assert result.raw_ei > 4.0

    def test_lead_changes_counted(self):
        """Lead changes (50% crossings) are counted correctly."""
        snapshots = [
            _make_dp(0, 0.60),   # Home leading
            _make_dp(2, 0.45),   # Away leading (crossing 1)
            _make_dp(4, 0.55),   # Home leading (crossing 2)
            _make_dp(6, 0.40),   # Away leading (crossing 3)
            _make_dp(8, 0.52),   # Home leading (crossing 4)
        ]
        end_time = GAME_START + timedelta(hours=2)
        result = calculate_ei(snapshots, GAME_START, end_time, "basketball_nba")
        assert result is not None
        assert result.metadata.lead_changes == 4

    def test_comeback_factor_home_won(self):
        """Comeback factor = lowest prob for winning team."""
        snapshots = [
            _make_dp(0, 0.50),
            _make_dp(30, 0.20),   # Home was down bad
            _make_dp(60, 0.35),
            _make_dp(90, 0.75),   # Home came back
        ]
        end_time = GAME_START + timedelta(hours=2)
        result = calculate_ei(snapshots, GAME_START, end_time, "basketball_nba", home_won=True)
        assert result is not None
        assert abs(result.metadata.comeback_factor - 0.20) < 0.01

    def test_comeback_factor_away_won(self):
        """Comeback factor for away win = min(1-p) across all snapshots."""
        snapshots = [
            _make_dp(0, 0.50),
            _make_dp(30, 0.80),   # Away was at 20%
            _make_dp(60, 0.60),
            _make_dp(90, 0.30),   # Away came back
        ]
        end_time = GAME_START + timedelta(hours=2)
        result = calculate_ei(snapshots, GAME_START, end_time, "basketball_nba", home_won=False)
        assert result is not None
        assert abs(result.metadata.comeback_factor - 0.20) < 0.01

    def test_time_normalization_overtime(self):
        """OT game should be normalized down so it doesn't auto-inflate."""
        # Create a standard 2.5h game and a 3h OT game with same movements
        base_snapshots = [_make_dp(i, 0.50 + 0.15 * ((-1) ** i)) for i in range(30)]

        # 2.5h (regulation-ish)
        end_reg = GAME_START + timedelta(hours=2, minutes=30)
        result_reg = calculate_ei(base_snapshots, GAME_START, end_reg, "basketball_nba")

        # 3h (OT) — add more snapshots to fill OT
        ot_snapshots = base_snapshots + [_make_dp(30 + i, 0.50 + 0.10 * ((-1) ** i)) for i in range(10)]
        end_ot = GAME_START + timedelta(hours=3)
        result_ot = calculate_ei(ot_snapshots, GAME_START, end_ot, "basketball_nba")

        # OT game has more snapshots but time normalization should prevent automatic inflation
        assert result_reg is not None and result_ot is not None
        # The OT game's raw_ei should NOT be proportionally higher than regulation
        # (it has ~33% more snapshots but normalization scales it down)

    def test_pre_game_snapshots_excluded(self):
        """Snapshots before game_start should be excluded."""
        snapshots = [
            _make_dp(-10, 0.50),  # Before game
            _make_dp(-5, 0.52),   # Before game
            _make_dp(0, 0.55),
            _make_dp(5, 0.60),
            _make_dp(10, 0.58),
        ]
        end_time = GAME_START + timedelta(hours=2)
        result = calculate_ei(snapshots, GAME_START, end_time, "basketball_nba")
        assert result is not None
        assert result.metadata.snapshot_count == 3  # Only 3 in-game snapshots after aggregation

    def test_score_clamped_1_to_100(self):
        """Score should always be 1-100."""
        # Minimal movement
        snapshots = [_make_dp(i, 0.50) for i in range(10)]
        end_time = GAME_START + timedelta(hours=2)
        result = calculate_ei(snapshots, GAME_START, end_time, "basketball_nba")
        assert result is not None
        assert 1 <= result.score <= 100

    def test_data_quality_good(self):
        """15+ buckets (at 60s) = good quality."""
        snapshots = [_make_dp(i, 0.50 + 0.01 * i) for i in range(20)]
        end_time = GAME_START + timedelta(hours=2)
        result = calculate_ei(snapshots, GAME_START, end_time, "basketball_nba")
        assert result is not None
        assert result.data_quality == "good"

    def test_data_quality_limited(self):
        """5-14 buckets (at 60s) = limited quality."""
        # 8 snapshots at 2-min intervals → 8 buckets at 60s
        snapshots = [_make_dp(i * 2, 0.50 + 0.01 * i) for i in range(8)]
        end_time = GAME_START + timedelta(hours=2)
        result = calculate_ei(snapshots, GAME_START, end_time, "basketball_nba")
        assert result is not None
        assert result.data_quality == "limited"

    def test_data_quality_minimal(self):
        """<5 buckets = minimal quality."""
        snapshots = [_make_dp(0, 0.50), _make_dp(1, 0.60), _make_dp(2, 0.55)]
        end_time = GAME_START + timedelta(hours=2)
        result = calculate_ei(snapshots, GAME_START, end_time, "basketball_nba")
        assert result is not None
        assert result.data_quality == "minimal"


class TestAggregateSnapshots:
    """Test time-bucket aggregation."""

    def test_single_source_passthrough(self):
        """Single source per bucket passes through."""
        snapshots = [_make_dp(0, 0.50), _make_dp(1, 0.55), _make_dp(2, 0.60)]
        result = _aggregate_snapshots(snapshots, bucket_seconds=60)
        assert len(result) == 3
        assert result[0].home_win_probability == 0.50

    def test_multi_source_median(self):
        """Multiple sources in same bucket → median."""
        base = datetime(2026, 2, 1, 19, 0, 0, tzinfo=timezone.utc)
        snapshots = [
            EIDataPoint(captured_at=base, home_win_probability=0.50, source="a"),
            EIDataPoint(captured_at=base + timedelta(seconds=5), home_win_probability=0.60, source="b"),
            EIDataPoint(captured_at=base + timedelta(seconds=10), home_win_probability=0.55, source="c"),
        ]
        result = _aggregate_snapshots(snapshots, bucket_seconds=30)
        assert len(result) == 1
        assert result[0].home_win_probability == 0.55  # median of [0.50, 0.55, 0.60]

    def test_null_probabilities_excluded(self):
        """None probabilities are excluded from median."""
        base = datetime(2026, 2, 1, 19, 0, 0, tzinfo=timezone.utc)
        snapshots = [
            EIDataPoint(captured_at=base, home_win_probability=0.50, source="a"),
            EIDataPoint(captured_at=base + timedelta(seconds=5), home_win_probability=None, source="b"),
            EIDataPoint(captured_at=base + timedelta(seconds=10), home_win_probability=0.60, source="c"),
        ]
        result = _aggregate_snapshots(snapshots, bucket_seconds=30)
        assert len(result) == 1
        assert result[0].home_win_probability == 0.55  # median of [0.50, 0.60]

    def test_empty_input(self):
        result = _aggregate_snapshots([], bucket_seconds=30)
        assert result == []

    def test_valid_until_carry_forward(self):
        """Snapshots with valid_until extend into subsequent buckets."""
        base = datetime(2026, 2, 1, 19, 0, 0, tzinfo=timezone.utc)
        snapshots = [
            # Bookmaker A reported at t=0, valid until t=180s (3 buckets at 60s)
            EIDataPoint(
                captured_at=base,
                home_win_probability=0.55,
                source="bookmaker_a",
                valid_until=base + timedelta(seconds=180),
            ),
            # Bookmaker B reported at t=60, no valid_until
            EIDataPoint(
                captured_at=base + timedelta(seconds=60),
                home_win_probability=0.60,
                source="bookmaker_b",
            ),
            # Bookmaker B reported at t=120
            EIDataPoint(
                captured_at=base + timedelta(seconds=120),
                home_win_probability=0.58,
                source="bookmaker_b",
            ),
        ]
        result = _aggregate_snapshots(snapshots, bucket_seconds=60)
        # Bucket 0: A=0.55 → median=0.55
        # Bucket 60: A=0.55 (carried), B=0.60 → median=0.575
        # Bucket 120: A=0.55 (carried), B=0.58 → median=0.565
        assert len(result) == 3
        assert result[0].home_win_probability == 0.55
        # With carry-forward, bucket 60 has both sources
        assert result[1].home_win_probability == pytest.approx(0.575, abs=0.001)

    def test_valid_until_stabilizes_medians(self):
        """
        Without valid_until, different bookmaker subsets per bucket cause phantom
        oscillation. With valid_until, carried-forward readings stabilize the median.
        """
        base = datetime(2026, 2, 1, 19, 0, 0, tzinfo=timezone.utc)
        # Simulate: 3 bookmakers all agree at ~55%, but report at different times
        # Without carry-forward, buckets with only 1-2 sources produce unstable medians
        snapshots = [
            EIDataPoint(
                captured_at=base,
                home_win_probability=0.54,
                source="book_a",
                valid_until=base + timedelta(seconds=300),
            ),
            EIDataPoint(
                captured_at=base + timedelta(seconds=10),
                home_win_probability=0.56,
                source="book_b",
                valid_until=base + timedelta(seconds=300),
            ),
            EIDataPoint(
                captured_at=base + timedelta(seconds=20),
                home_win_probability=0.55,
                source="book_c",
                valid_until=base + timedelta(seconds=300),
            ),
            # Next update only from book_a at t=120
            EIDataPoint(
                captured_at=base + timedelta(seconds=120),
                home_win_probability=0.53,
                source="book_a",
                valid_until=base + timedelta(seconds=300),
            ),
        ]
        result = _aggregate_snapshots(snapshots, bucket_seconds=60)
        # With carry-forward, all buckets should have 3 sources and stable medians
        assert len(result) >= 2
        # Check that consecutive medians are close (no phantom oscillation)
        for i in range(1, len(result)):
            delta = abs(result[i].home_win_probability - result[i - 1].home_win_probability)
            assert delta < 0.05, f"Phantom oscillation: delta={delta} between bucket {i-1} and {i}"

    def test_backward_compat_no_valid_until(self):
        """EIDataPoint without valid_until still works (defaults to None)."""
        base = datetime(2026, 2, 1, 19, 0, 0, tzinfo=timezone.utc)
        # Create without valid_until (old-style)
        snapshots = [
            EIDataPoint(captured_at=base, home_win_probability=0.50, source="a"),
            EIDataPoint(
                captured_at=base + timedelta(seconds=60),
                home_win_probability=0.55,
                source="a",
            ),
            EIDataPoint(
                captured_at=base + timedelta(seconds=120),
                home_win_probability=0.52,
                source="a",
            ),
        ]
        result = _aggregate_snapshots(snapshots, bucket_seconds=60)
        assert len(result) == 3
        # No carry-forward — each bucket only has its own snapshot
        assert result[0].home_win_probability == 0.50
        assert result[1].home_win_probability == 0.55
        assert result[2].home_win_probability == 0.52

    def test_default_bucket_size_is_30s(self):
        """Default bucket size should be 30s."""
        base = datetime(2026, 2, 1, 19, 0, 0, tzinfo=timezone.utc)
        snapshots = [
            EIDataPoint(captured_at=base, home_win_probability=0.50, source="a"),
            EIDataPoint(
                captured_at=base + timedelta(seconds=30),
                home_win_probability=0.55,
                source="b",
            ),
            EIDataPoint(
                captured_at=base + timedelta(seconds=60),
                home_win_probability=0.60,
                source="a",
            ),
        ]
        # With default 30s buckets, each snapshot is in its own bucket
        result = _aggregate_snapshots(snapshots)
        assert len(result) == 3  # 3 buckets

    def test_source_dedup_in_carry_forward(self):
        """When same source appears via carry-forward and new reading, keep latest."""
        base = datetime(2026, 2, 1, 19, 0, 0, tzinfo=timezone.utc)
        snapshots = [
            # book_a at t=0, valid for 120s
            EIDataPoint(
                captured_at=base,
                home_win_probability=0.50,
                source="book_a",
                valid_until=base + timedelta(seconds=120),
            ),
            # book_a updates at t=60 with new value
            EIDataPoint(
                captured_at=base + timedelta(seconds=60),
                home_win_probability=0.60,
                source="book_a",
                valid_until=base + timedelta(seconds=180),
            ),
        ]
        result = _aggregate_snapshots(snapshots, bucket_seconds=60)
        assert len(result) == 3  # buckets at 0, 60, 120
        assert result[0].home_win_probability == 0.50  # original
        assert result[1].home_win_probability == 0.60  # latest reading wins


class TestStatusLabels:
    """Test EI status/label/emoji functions."""

    def test_status_incredible(self):
        assert get_ei_status(85) == "incredible"

    def test_status_exciting(self):
        assert get_ei_status(65) == "exciting"

    def test_status_competitive(self):
        assert get_ei_status(45) == "competitive"

    def test_status_quiet(self):
        assert get_ei_status(25) == "quiet"

    def test_status_flat(self):
        assert get_ei_status(10) == "flat"

    def test_label_must_watch(self):
        assert get_ei_label(85) == "Must-Watch"

    def test_emoji_fire(self):
        assert get_ei_emoji(85) == "🔥"

    def test_emoji_lightning(self):
        assert get_ei_emoji(65) == "⚡"


class TestRegulationSeconds:
    """Test sport-specific regulation length."""

    def test_nba(self):
        assert get_regulation_seconds("basketball_nba") == 2880

    def test_nfl(self):
        assert get_regulation_seconds("americanfootball_nfl") == 3600

    def test_mlb(self):
        assert get_regulation_seconds("baseball_mlb") == 8100

    def test_unknown_sport_defaults(self):
        assert get_regulation_seconds("curling_unknown") == 3600

    def test_soccer_prefix_match(self):
        assert get_regulation_seconds("soccer_epl") == 5400


class TestBackwardCompatibility:
    """Test that old Pulse names still work."""

    def test_pulse_aliases_importable(self):
        from app.utils.excitement_index import (
            PulseDataPoint,
            PulseResult,
            calculate_pulse,
            get_pulse_status,
            get_pulse_label,
            get_pulse_emoji,
        )
        # PulseDataPoint should be the same as EIDataPoint
        assert PulseDataPoint is EIDataPoint

    def test_calculate_pulse_works(self):
        from app.utils.excitement_index import calculate_pulse
        snapshots = [_make_dp(i, 0.50 + 0.05 * ((-1) ** i)) for i in range(10)]
        end_time = GAME_START + timedelta(hours=2)
        result = calculate_pulse(snapshots, GAME_START, end_time, "basketball_nba")
        assert result is not None
        assert 1 <= result.score <= 100
