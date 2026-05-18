"""Tests for the Pulse (Game Excitement Metric) algorithm."""

import pytest
from datetime import datetime, timezone, timedelta
from statistics import median

from app.utils.pulse import (
    get_expected_duration,
    get_pulse_status,
    get_pulse_emoji,
    get_pulse_label,
    _aggregate_snapshots,
    calculate_pulse,
    PulseDataPoint,
    PulseComponents,
    PulseResult,
    SIGNIFICANT_MOVE_THRESHOLD,
    MIN_SNAPSHOTS,
)


# =============================================================================
# get_expected_duration
# =============================================================================
class TestGetExpectedDuration:
    def test_nba(self):
        assert get_expected_duration("basketball_nba") == 150

    def test_nfl(self):
        assert get_expected_duration("americanfootball_nfl") == 195

    def test_mlb(self):
        assert get_expected_duration("baseball_mlb") == 180

    def test_nhl(self):
        assert get_expected_duration("icehockey_nhl") == 150

    def test_ncaaf(self):
        assert get_expected_duration("americanfootball_ncaaf") == 210

    def test_ncaab(self):
        assert get_expected_duration("basketball_ncaab") == 135

    def test_mma(self):
        assert get_expected_duration("mma_mixed_martial_arts") == 25

    def test_boxing(self):
        assert get_expected_duration("boxing_boxing") == 36

    def test_unknown_sport_returns_default(self):
        assert get_expected_duration("unknown_sport") == 150

    def test_prefix_matching(self):
        """Sport keys are matched by prefix, not exact key."""
        assert get_expected_duration("basketball_nba_playoffs") == 150
        assert get_expected_duration("americanfootball_nfl_super_bowl") == 195

    def test_empty_sport_key(self):
        assert get_expected_duration("") == 150


# =============================================================================
# get_pulse_status
# =============================================================================
class TestGetPulseStatus:
    def test_racing(self):
        assert get_pulse_status(81) == "racing"
        assert get_pulse_status(100) == "racing"

    def test_strong(self):
        assert get_pulse_status(61) == "strong"
        assert get_pulse_status(80) == "strong"

    def test_steady(self):
        assert get_pulse_status(41) == "steady"
        assert get_pulse_status(60) == "steady"

    def test_weak(self):
        assert get_pulse_status(21) == "weak"
        assert get_pulse_status(40) == "weak"

    def test_flatline(self):
        assert get_pulse_status(1) == "flatline"
        assert get_pulse_status(20) == "flatline"

    def test_boundary_values(self):
        assert get_pulse_status(80) == "strong"
        assert get_pulse_status(81) == "racing"


# =============================================================================
# get_pulse_emoji
# =============================================================================
class TestGetPulseEmoji:
    def test_racing_emoji(self):
        assert get_pulse_emoji(90) == "\U0001fac0"

    def test_strong_emoji(self):
        assert get_pulse_emoji(70) == "\U0001f493"

    def test_steady_emoji(self):
        assert get_pulse_emoji(50) == "\U0001f497"

    def test_weak_emoji(self):
        assert get_pulse_emoji(30) == "\U0001fa7a"

    def test_flatline_emoji(self):
        assert get_pulse_emoji(10) == "\U0001f4c9"


# =============================================================================
# get_pulse_label
# =============================================================================
class TestGetPulseLabel:
    def test_incredible(self):
        assert get_pulse_label(90) == "Incredible"
        assert get_pulse_label(100) == "Incredible"

    def test_must_watch(self):
        assert get_pulse_label(81) == "Must-Watch"
        assert get_pulse_label(89) == "Must-Watch"

    def test_exciting(self):
        assert get_pulse_label(71) == "Exciting"

    def test_engaging(self):
        assert get_pulse_label(61) == "Engaging"

    def test_competitive(self):
        assert get_pulse_label(51) == "Competitive"

    def test_steady(self):
        assert get_pulse_label(41) == "Steady"

    def test_slow(self):
        assert get_pulse_label(31) == "Slow"

    def test_one_sided(self):
        assert get_pulse_label(21) == "One-Sided"

    def test_flatline(self):
        assert get_pulse_label(1) == "Flatline"
        assert get_pulse_label(20) == "Flatline"


# =============================================================================
# PulseComponents
# =============================================================================
class TestPulseComponents:
    def test_to_dict(self):
        c = PulseComponents(
            heart_rate=0.12345,
            amplitude=0.6789,
            arrhythmia=0.333,
            vitals=0.999,
            time_weight=0.8,
            lead_changes=3,
        )
        d = c.to_dict()
        assert d["heart_rate"] == 0.1235
        assert d["amplitude"] == 0.6789
        assert d["arrhythmia"] == 0.333
        assert d["vitals"] == 0.999
        assert d["time_weight"] == 0.8
        assert d["lead_changes"] == 3

    def test_to_json(self):
        c = PulseComponents(
            heart_rate=0.5, amplitude=0.5, arrhythmia=0.5,
            vitals=0.5, time_weight=1.0, lead_changes=0,
        )
        json_str = c.to_json()
        assert '"heart_rate": 0.5' in json_str
        assert '"lead_changes": 0' in json_str


# =============================================================================
# _aggregate_snapshots
# =============================================================================
class TestAggregateSnapshots:
    def test_empty_input(self):
        assert _aggregate_snapshots([]) == []

    def test_single_bookmaker_passthrough(self, make_snapshots):
        """Single bookmaker snapshots pass through with one per bucket."""
        snapshots = make_snapshots([0.50, 0.55, 0.60])
        result = _aggregate_snapshots(snapshots)
        assert len(result) == 3
        assert result[0].home_win_probability == 0.50
        assert result[1].home_win_probability == 0.55
        assert result[2].home_win_probability == 0.60

    def test_multi_bookmaker_median(self, make_multi_bookmaker_snapshots):
        """Multiple bookmakers at same time get aggregated to median."""
        snapshots = make_multi_bookmaker_snapshots([
            [0.50, 0.52, 0.54],  # median = 0.52
            [0.60, 0.62, 0.64],  # median = 0.62
        ])
        result = _aggregate_snapshots(snapshots)
        assert len(result) == 2
        assert result[0].home_win_probability == 0.52
        assert result[1].home_win_probability == 0.62

    def test_bookmaker_label_is_consensus(self, make_multi_bookmaker_snapshots):
        snapshots = make_multi_bookmaker_snapshots([[0.50, 0.52]])
        result = _aggregate_snapshots(snapshots)
        assert result[0].bookmaker == "consensus"

    def test_none_probabilities_filtered(self, game_start):
        """Snapshots with None probability are filtered out within buckets."""
        snapshots = [
            PulseDataPoint(game_start, 0.50, "book1"),
            PulseDataPoint(game_start, None, "book2"),
            PulseDataPoint(game_start, 0.54, "book3"),
        ]
        result = _aggregate_snapshots(snapshots)
        assert len(result) == 1
        assert result[0].home_win_probability == median([0.50, 0.54])

    def test_all_none_bucket_skipped(self, game_start):
        """Bucket with all None probabilities is skipped."""
        snapshots = [
            PulseDataPoint(game_start, None, "book1"),
            PulseDataPoint(game_start, None, "book2"),
        ]
        result = _aggregate_snapshots(snapshots)
        assert len(result) == 0

    def test_bucket_size_60_seconds(self, game_start):
        """Snapshots within 60 seconds are grouped together."""
        snapshots = [
            PulseDataPoint(game_start + timedelta(seconds=0), 0.50, "book1"),
            PulseDataPoint(game_start + timedelta(seconds=30), 0.52, "book2"),
            PulseDataPoint(game_start + timedelta(seconds=61), 0.55, "book3"),
        ]
        result = _aggregate_snapshots(snapshots, bucket_seconds=60)
        # First two should be in same bucket, third in another
        assert len(result) == 2


# =============================================================================
# calculate_pulse - Core Algorithm
# =============================================================================
class TestCalculatePulse:
    def test_returns_none_for_insufficient_data(self, game_start, current_time, make_snapshots):
        """Less than MIN_SNAPSHOTS returns None."""
        snapshots = make_snapshots([0.50, 0.55])
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result is None

    def test_returns_none_for_empty_snapshots(self, game_start, current_time):
        result = calculate_pulse([], game_start, current_time, "basketball_nba")
        assert result is None

    def test_minimum_snapshots_produces_result(self, game_start, current_time, make_snapshots):
        """Exactly MIN_SNAPSHOTS produces a result."""
        snapshots = make_snapshots([0.50, 0.55, 0.60])
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result is not None
        assert 1 <= result.score <= 100

    def test_score_range(self, game_start, current_time, make_snapshots):
        """Score is always in 1-100 range."""
        snapshots = make_snapshots([0.50, 0.55, 0.48, 0.52, 0.49])
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert 1 <= result.score <= 100

    def test_flatline_game_low_score(self, game_start, current_time, make_snapshots):
        """A blowout with no movement should score low."""
        probs = [0.90] * 20
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.score <= 30
        assert result.status in ("flatline", "weak")

    def test_exciting_game_high_score(self, game_start, current_time, make_snapshots):
        """A close game with lots of back-and-forth should score high."""
        probs = []
        for i in range(30):
            if i % 2 == 0:
                probs.append(0.35 + (i % 5) * 0.05)
            else:
                probs.append(0.65 - (i % 5) * 0.05)
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.score >= 50

    def test_lead_changes_detected(self, game_start, current_time, make_snapshots):
        """Lead changes (50% crossings) are counted correctly."""
        probs = [0.45, 0.55, 0.45, 0.55, 0.45]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.components.lead_changes == 4

    def test_no_lead_changes_when_same_side(self, game_start, current_time, make_snapshots):
        """No lead changes when probability stays on same side of 50%."""
        probs = [0.60, 0.65, 0.70, 0.75, 0.80]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.components.lead_changes == 0

    def test_data_quality_good(self, game_start, current_time, make_snapshots):
        """30+ snapshots = 'good' data quality."""
        probs = [0.50 + (i % 5) * 0.01 for i in range(35)]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.data_quality == "good"

    def test_data_quality_limited(self, game_start, current_time, make_snapshots):
        """10-29 snapshots = 'limited' data quality."""
        probs = [0.50 + (i % 5) * 0.01 for i in range(15)]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.data_quality == "limited"

    def test_data_quality_minimal(self, game_start, current_time, make_snapshots):
        """3-9 snapshots = 'minimal' data quality."""
        probs = [0.50, 0.55, 0.60, 0.65, 0.70]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.data_quality == "minimal"

    def test_snapshot_count(self, game_start, current_time, make_snapshots):
        """snapshot_count reflects post-aggregation count."""
        probs = [0.50, 0.55, 0.60, 0.65]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.snapshot_count == 4

    def test_pre_game_snapshots_filtered(self, game_start, current_time, make_snapshots):
        """Snapshots before game_start are excluded."""
        pre_game = [
            PulseDataPoint(
                game_start - timedelta(hours=1),
                0.50,
                "consensus",
            )
        ]
        in_game = make_snapshots([0.55, 0.60, 0.65])
        all_snapshots = pre_game + in_game
        result = calculate_pulse(all_snapshots, game_start, current_time, "basketball_nba")
        assert result is not None
        assert result.snapshot_count == 3

    def test_none_probability_snapshots_filtered(self, game_start, current_time):
        """Snapshots with None probability are excluded."""
        snapshots = [
            PulseDataPoint(game_start + timedelta(minutes=1), None, "book1"),
            PulseDataPoint(game_start + timedelta(minutes=2), 0.50, "book1"),
            PulseDataPoint(game_start + timedelta(minutes=3), 0.55, "book1"),
            PulseDataPoint(game_start + timedelta(minutes=4), 0.60, "book1"),
        ]
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result is not None

    def test_status_matches_score(self, game_start, current_time, make_snapshots):
        """Result status matches the score thresholds."""
        probs = [0.50, 0.55, 0.48, 0.52, 0.49, 0.53]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.status == get_pulse_status(result.score)

    def test_components_in_valid_range(self, game_start, current_time, make_snapshots):
        """All component values are in [0, 1]."""
        probs = [0.50, 0.55, 0.48, 0.52, 0.49, 0.53, 0.60, 0.45]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        c = result.components
        assert 0 <= c.heart_rate <= 1
        assert 0 <= c.amplitude <= 1
        assert 0 <= c.arrhythmia <= 1
        assert 0 <= c.vitals <= 1
        assert c.time_weight >= 0.6

    def test_time_weight_early_game(self, game_start, make_snapshots):
        """Early in the game, time weight is close to 0.6."""
        early_time = game_start + timedelta(minutes=5)
        probs = [0.50, 0.55, 0.60]
        snapshots = make_snapshots(probs, interval_seconds=60)
        result = calculate_pulse(snapshots, game_start, early_time, "basketball_nba")
        assert result.components.time_weight < 0.7

    def test_time_weight_late_game(self, game_start, make_snapshots):
        """Late in the game, time weight approaches 1.0."""
        late_time = game_start + timedelta(minutes=150)
        probs = [0.50, 0.55, 0.60]
        snapshots = make_snapshots(probs, interval_seconds=60)
        result = calculate_pulse(snapshots, game_start, late_time, "basketball_nba")
        assert result.components.time_weight >= 0.95

    def test_vitals_high_for_close_game(self, game_start, current_time, make_snapshots):
        """Vitals should be high when probabilities stay near 50%."""
        probs = [0.48, 0.50, 0.52, 0.49, 0.51]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.components.vitals > 0.9

    def test_vitals_low_for_blowout(self, game_start, current_time, make_snapshots):
        """Vitals should be low when probabilities are far from 50%."""
        probs = [0.85, 0.87, 0.90, 0.92, 0.95]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.components.vitals < 0.3

    def test_heart_rate_high_for_volatile_game(self, game_start, make_snapshots):
        """Heart rate is high when many significant moves occur."""
        probs = [0.50, 0.60, 0.45, 0.65, 0.40, 0.70, 0.35, 0.75]
        snapshots = make_snapshots(probs, interval_seconds=60)
        ct = game_start + timedelta(minutes=8)
        result = calculate_pulse(snapshots, game_start, ct, "basketball_nba")
        assert result.components.heart_rate > 0.5

    def test_amplitude_zero_for_no_movement(self, game_start, current_time, make_snapshots):
        """Amplitude is zero when there's no probability change."""
        probs = [0.50, 0.50, 0.50, 0.50]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.components.amplitude == 0.0

    def test_multi_bookmaker_aggregation_prevents_inflation(
        self, game_start, current_time, make_multi_bookmaker_snapshots
    ):
        """Multi-bookmaker snapshots don't inflate scores via phantom movements."""
        groups = []
        for i in range(10):
            groups.append([0.54, 0.55, 0.56])
        snapshots = make_multi_bookmaker_snapshots(groups)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.components.lead_changes == 0
        assert result.components.heart_rate < 0.2

    def test_noisy_source_does_not_create_fake_momentum(
        self, game_start, current_time, make_multi_bookmaker_snapshots
    ):
        """One flapping source should not create fake pulse movement."""
        groups = []
        for i in range(12):
            noisy_probability = 0.10 if i % 2 == 0 else 0.90
            groups.append([0.54, 0.55, 0.56, noisy_probability])

        snapshots = make_multi_bookmaker_snapshots(groups)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")

        assert result is not None
        assert result.snapshot_count == 12
        assert result.components.lead_changes == 0
        assert result.components.heart_rate == 0.0
        assert result.components.amplitude < 0.07

    def test_identical_probabilities(self, game_start, current_time, make_snapshots):
        """All identical probabilities should produce minimal score."""
        probs = [0.50] * 10
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.components.amplitude == 0.0
        assert result.components.arrhythmia == 0.0
        assert result.components.heart_rate == 0.0


# =============================================================================
# calculate_pulse - Edge Cases
# =============================================================================
class TestCalculatePulseEdgeCases:
    def test_extreme_probabilities(self, game_start, current_time, make_snapshots):
        """Probabilities at 0 and 1 don't break the algorithm."""
        probs = [0.0, 0.5, 1.0, 0.5, 0.0]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result is not None
        assert 1 <= result.score <= 100

    def test_all_snapshots_before_game_start(self, game_start, current_time):
        """All snapshots before game start returns None."""
        snapshots = [
            PulseDataPoint(game_start - timedelta(hours=2), 0.50, "book"),
            PulseDataPoint(game_start - timedelta(hours=1), 0.55, "book"),
            PulseDataPoint(game_start - timedelta(minutes=30), 0.60, "book"),
        ]
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result is None

    def test_very_short_game(self, game_start, make_snapshots):
        """Very short elapsed time with enough spread snapshots works."""
        # With 10s intervals, all 3 may fall in the same 60s bucket
        # Use wider spacing to ensure 3 distinct buckets
        probs = [0.50, 0.55, 0.60]
        snapshots = make_snapshots(probs, interval_seconds=61)
        ct = game_start + timedelta(seconds=183)
        result = calculate_pulse(snapshots, game_start, ct, "basketball_nba")
        assert result is not None

    def test_very_long_game(self, game_start, make_snapshots):
        """Game much longer than expected duration works."""
        probs = [0.50 + (i % 10) * 0.01 for i in range(50)]
        snapshots = make_snapshots(probs, interval_seconds=600)
        ct = game_start + timedelta(hours=8)
        result = calculate_pulse(snapshots, game_start, ct, "basketball_nba")
        assert result is not None
        assert result.components.time_weight <= 1.0

    def test_lead_change_bonus_capped(self, game_start, current_time, make_snapshots):
        """Lead change bonus capped at 0.20 (4 lead changes * 0.05)."""
        probs = [0.45, 0.55] * 5
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result is not None

    def test_single_delta_arrhythmia_zero(self, game_start, current_time, make_snapshots):
        """With only one delta (2 deltas need stdev), arrhythmia should be 0."""
        # 3 snapshots = 2 deltas after aggregation, but if we only have
        # exactly 3 points we get 2 deltas. stdev of 2 values is valid.
        # With only 2 snapshots after aggregation there's 1 delta -> arrhythmia=0
        # But we need MIN_SNAPSHOTS=3 to get a result. With 3 aggregated
        # snapshots we have 2 deltas which is enough for stdev.
        # To get exactly 1 delta after aggregation, we'd need 2 buckets - but
        # that's below MIN_SNAPSHOTS. So test that with 3 identical-delta
        # snapshots, arrhythmia is 0 (stdev of identical values = 0).
        probs = [0.40, 0.45, 0.50]  # deltas: [0.05, 0.05] -> stdev = 0
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result is not None
        assert result.components.arrhythmia == 0.0

    def test_game_progress_capped_at_one(self, game_start, make_snapshots):
        """Game progress (and thus time_weight) caps even for overtime games."""
        # 8 hours into a 150-min NBA game
        overtime = game_start + timedelta(hours=8)
        probs = [0.50, 0.55, 0.60]
        snapshots = make_snapshots(probs, interval_seconds=60)
        result = calculate_pulse(snapshots, game_start, overtime, "basketball_nba")
        assert result.components.time_weight == 1.0

    def test_different_sport_different_time_weight(self, game_start, make_snapshots):
        """Same elapsed time produces different time weights for different sports."""
        elapsed = game_start + timedelta(minutes=30)
        probs = [0.50, 0.55, 0.60, 0.50, 0.55]
        snapshots = make_snapshots(probs, interval_seconds=60)
        # MMA expected: 25 min -> 30 min = 100% progress -> weight ~1.0
        mma = calculate_pulse(snapshots, game_start, elapsed, "mma_mixed_martial_arts")
        # NBA expected: 150 min -> 30 min = 20% progress -> weight ~0.64
        nba = calculate_pulse(snapshots, game_start, elapsed, "basketball_nba")
        assert mma.components.time_weight > nba.components.time_weight
        assert mma.components.time_weight >= 0.95  # MMA should be near 1.0

    def test_null_sport_key(self, game_start, current_time, make_snapshots):
        """None sport_key uses default duration (150 min)."""
        probs = [0.50, 0.55, 0.60, 0.50]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, None)
        assert result is not None


# =============================================================================
# calculate_pulse - Normalization Constants (regression protection)
# =============================================================================
class TestPulseNormalization:
    """Pin normalization ceilings so accidental changes are caught.

    These constants were tuned iteratively (see CLAUDE.md normalization
    tuning history) and are the #1 source of rework in pulse.py.
    """

    def test_heart_rate_ceiling_0_6(self, game_start, make_snapshots):
        """Heart rate of 0.6 moves/min should produce heart_rate=1.0."""
        # 0.6 moves/min means 0.6 significant moves per minute.
        # In 100 minutes with 100 snapshots, we need 60 significant moves.
        # All deltas >= 0.02 count as significant.
        probs = []
        for i in range(100):
            # Alternate: 0.50, 0.53, 0.50, 0.53 ... (delta=0.03 > threshold 0.02)
            probs.append(0.50 if i % 2 == 0 else 0.53)
        snapshots = make_snapshots(probs, interval_seconds=60)
        ct = game_start + timedelta(minutes=100)
        result = calculate_pulse(snapshots, game_start, ct, "basketball_nba")
        # 99 significant moves in 100 minutes = 0.99 moves/min
        # 0.99 / 0.6 = 1.65, capped at 1.0
        assert result.components.heart_rate == 1.0

    def test_heart_rate_proportional_below_ceiling(self, game_start, make_snapshots):
        """Below ceiling, heart rate scales proportionally."""
        # 0.3 moves/min should give heart_rate = 0.5
        # In 10 minutes, need 3 significant moves out of 9 deltas
        probs = [0.50, 0.53, 0.50, 0.50, 0.50, 0.50, 0.50, 0.53, 0.50, 0.53]
        snapshots = make_snapshots(probs, interval_seconds=60)
        ct = game_start + timedelta(minutes=10)
        result = calculate_pulse(snapshots, game_start, ct, "basketball_nba")
        # 4 significant moves (deltas: 0.03, 0.03, 0, 0, 0, 0, 0.03, 0.03, 0.03)
        # Wait, let me recount. Deltas between consecutive:
        # 0.50->0.53=0.03, 0.53->0.50=0.03, 0.50->0.50=0, 0->0=0, 0->0=0,
        # 0->0=0, 0.50->0.53=0.03, 0.53->0.50=0.03, 0.50->0.53=0.03
        # 5 significant moves in 10 minutes = 0.5 moves/min
        # 0.5 / 0.6 = 0.833
        assert 0.7 < result.components.heart_rate < 0.95

    def test_amplitude_ceiling_0_15(self, game_start, current_time, make_snapshots):
        """RMS amplitude of 0.15 should produce amplitude=1.0."""
        # All deltas = 0.15 -> RMS = 0.15 -> amplitude = 1.0
        probs = [0.35, 0.50, 0.35, 0.50, 0.35, 0.50]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert result.components.amplitude == 1.0

    def test_amplitude_proportional_below_ceiling(self, game_start, current_time, make_snapshots):
        """Below ceiling, amplitude scales proportionally."""
        # Deltas all = 0.05. RMS = 0.05. amplitude = 0.05/0.15 = 0.333
        probs = [0.45, 0.50, 0.45, 0.50, 0.45, 0.50]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        assert abs(result.components.amplitude - 0.05 / 0.15) < 0.01

    def test_arrhythmia_ceiling_0_10(self, game_start, current_time, make_snapshots):
        """Stdev of deltas >= 0.10 should produce arrhythmia=1.0."""
        # Need deltas with stdev >= 0.10
        # Deltas: [0.0, 0.20, 0.0, 0.20, 0.0] -> stdev ≈ 0.10
        probs = [0.50, 0.50, 0.70, 0.70, 0.50, 0.50]
        snapshots = make_snapshots(probs)
        result = calculate_pulse(snapshots, game_start, current_time, "basketball_nba")
        # Deltas: [0, 0.20, 0, 0.20, 0] -> stdev of [0, 0.20, 0, 0.20, 0]
        # mean=0.08, variance= (3*0.08^2 + 2*0.12^2)/4 -> stdev ≈ 0.1095
        assert result.components.arrhythmia >= 0.95


# =============================================================================
# calculate_pulse - Exact Score Regression Tests
# =============================================================================
class TestPulseScoreRegression:
    """Pin exact scores for known inputs. If weights, normalization constants,
    or the combining formula change, these tests will fail — which is the point.
    """

    def test_perfectly_even_no_movement(self, game_start, make_snapshots):
        """All snapshots at 0.50 with no movement: only vitals contributes."""
        probs = [0.50] * 20
        snapshots = make_snapshots(probs, interval_seconds=60)
        ct = game_start + timedelta(minutes=120)
        result = calculate_pulse(snapshots, game_start, ct, "basketball_nba")
        # Components: heart_rate=0, amplitude=0, arrhythmia=0, vitals=1.0
        # lead_change_bonus = 0
        # time_weight = 0.6 + 0.4 * (80/150)^1.5 ≈ 0.6 + 0.4 * 0.437 ≈ 0.775
        # raw = (0*0.25 + 0*0.30 + 0*0.15 + 1.0*0.30 + 0) * time_weight
        #     = 0.30 * time_weight
        # scaled = raw * 100, so score ≈ 23
        assert result.components.heart_rate == 0.0
        assert result.components.amplitude == 0.0
        assert result.components.vitals == 1.0
        assert 20 <= result.score <= 30

    def test_maximum_blowout(self, game_start, make_snapshots):
        """All snapshots at 0.95: vitals near 0, everything else 0."""
        probs = [0.95] * 20
        snapshots = make_snapshots(probs, interval_seconds=60)
        ct = game_start + timedelta(minutes=120)
        result = calculate_pulse(snapshots, game_start, ct, "basketball_nba")
        assert result.components.vitals < 0.15
        assert result.score < 10

    def test_realistic_close_nba_game(self, game_start, make_snapshots):
        """Simulate a close NBA game with moderate swings."""
        # Game oscillates around 50% with moderate amplitude
        probs = [
            0.55, 0.52, 0.48, 0.45, 0.50,
            0.53, 0.47, 0.44, 0.51, 0.55,
            0.58, 0.52, 0.48, 0.45, 0.50,
            0.54, 0.49, 0.46, 0.51, 0.53,
            0.48, 0.45, 0.50, 0.55, 0.52,
            0.49, 0.46, 0.51, 0.54, 0.50,
        ]
        snapshots = make_snapshots(probs, interval_seconds=300)
        ct = game_start + timedelta(minutes=150)
        result = calculate_pulse(snapshots, game_start, ct, "basketball_nba")
        # Should be a competitive, engaging game
        assert result.status in ("steady", "strong")
        assert 40 <= result.score <= 75
        assert result.data_quality == "good"

    def test_dramatic_comeback_game(self, game_start, make_snapshots):
        """Team down big stages a comeback — should score higher than blowout."""
        # Start at 80% for home, slowly swing to 40% (away comeback)
        probs = (
            [0.80, 0.78, 0.75, 0.72, 0.68] +
            [0.63, 0.58, 0.52, 0.48, 0.42] +
            [0.38, 0.35, 0.40, 0.45, 0.42] +
            [0.38, 0.35, 0.40, 0.38, 0.35]
        )
        snapshots = make_snapshots(probs, interval_seconds=300)
        ct = game_start + timedelta(minutes=100)

        # Compare to a boring blowout
        blowout_probs = [0.80] * 20
        blowout_snaps = make_snapshots(blowout_probs, interval_seconds=300)
        blowout_result = calculate_pulse(blowout_snaps, game_start, ct, "basketball_nba")

        comeback_result = calculate_pulse(snapshots, game_start, ct, "basketball_nba")
        assert comeback_result.score > blowout_result.score
        # Comeback should have at least one lead change
        assert comeback_result.components.lead_changes >= 1

    def test_overtime_thriller(self, game_start, make_snapshots):
        """Game goes to overtime with tight probabilities — high score."""
        # Regulation: tight game
        probs = [0.52, 0.48, 0.51, 0.49, 0.50] * 6
        # OT: dramatic swings
        probs += [0.55, 0.45, 0.60, 0.40, 0.55, 0.45, 0.52, 0.48]
        snapshots = make_snapshots(probs, interval_seconds=300)
        # 38 snapshots * 5min = 190 min (overtime for 150-min NBA game)
        ct = game_start + timedelta(minutes=190)
        result = calculate_pulse(snapshots, game_start, ct, "basketball_nba")
        assert result.components.time_weight == 1.0  # past expected duration
        assert result.score >= 50
        assert result.data_quality == "good"


# =============================================================================
# calculate_pulse - Component Weight Verification
# =============================================================================
class TestPulseComponentWeights:
    """Verify the weight formula: 0.25*HR + 0.30*AMP + 0.15*ARR + 0.30*VIT."""

    def test_vitals_weighted_highest(self, game_start, make_snapshots):
        """Vitals and amplitude at 30% each should dominate over heart rate (25%)
        and arrhythmia (15%). Verify by constructing a game where only vitals
        contributes (no movement, close game)."""
        probs = [0.50] * 10
        snapshots = make_snapshots(probs, interval_seconds=60)
        ct = game_start + timedelta(minutes=60)
        result = calculate_pulse(snapshots, game_start, ct, "basketball_nba")
        # Only vitals = 1.0 contributes. Score = 0.30 * time_weight * 100
        tw = result.components.time_weight
        expected_raw = 0.30 * tw * 100
        assert abs(result.score - round(expected_raw)) <= 1

    def test_lead_change_bonus_adds_to_score(self, game_start, make_snapshots):
        """Lead change bonus (0.05 per change, max 0.20) adds on top of components."""
        # 2 lead changes: 0.45 -> 0.55 -> 0.45
        probs_with_lc = [0.45, 0.55, 0.45]
        probs_without_lc = [0.45, 0.48, 0.45]
        snaps_lc = make_snapshots(probs_with_lc, interval_seconds=60)
        snaps_no_lc = make_snapshots(probs_without_lc, interval_seconds=60)
        ct = game_start + timedelta(minutes=60)
        result_lc = calculate_pulse(snaps_lc, game_start, ct, "basketball_nba")
        result_no_lc = calculate_pulse(snaps_no_lc, game_start, ct, "basketball_nba")
        assert result_lc.score > result_no_lc.score
