"""
Pulse - Bain Luck's Proprietary Game Excitement Metric

Pulse measures how "alive" a game is based on probability movement patterns,
using a vital signs metaphor. A strong pulse means an exciting, dramatic game.
A flatline means a boring blowout.

Components:
- Heart Rate (25%): Frequency of significant probability moves
- Amplitude (30%): Magnitude of probability swings
- Arrhythmia (15%): Unpredictability of changes
- Vitals (30%): Current game competitiveness (closeness to 50%)
- Bonuses: Lead changes, comeback events

Output: 1-100 scale where:
- 1-20: Flatline (blowout, no drama)
- 21-40: Weak pulse (one-sided but not dead)
- 41-60: Steady pulse (competitive but calm)
- 61-80: Strong pulse (exciting, back-and-forth)
- 81-100: Racing pulse (incredible drama, must-watch)

Copyright Bain Luck. All rights reserved.
"""

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean, median, stdev
from typing import Optional


# Thresholds
SIGNIFICANT_MOVE_THRESHOLD = 0.02  # 2% probability change counts as significant
MIN_SNAPSHOTS = 3  # Minimum snapshots needed for calculation

# Expected game durations in minutes (for time weighting)
EXPECTED_DURATIONS = {
    'basketball_nba': 150,
    'basketball_ncaab': 135,
    'basketball_wncaab': 135,
    'basketball_wnba': 135,
    'americanfootball_nfl': 195,
    'americanfootball_ncaaf': 210,
    'baseball_mlb': 180,
    'icehockey_nhl': 150,
    'soccer': 105,
    'mma_mixed_martial_arts': 25,
    'boxing_boxing': 36,
}


@dataclass
class PulseDataPoint:
    """A single snapshot for Pulse calculation."""
    captured_at: datetime
    home_win_probability: Optional[float]
    bookmaker: str


@dataclass
class PulseComponents:
    """Individual component scores for Pulse."""
    heart_rate: float      # 0-1: frequency of significant moves
    amplitude: float       # 0-1: average magnitude of swings
    arrhythmia: float      # 0-1: unpredictability of changes
    vitals: float          # 0-1: current competitiveness
    time_weight: float     # multiplier based on game progress
    lead_changes: int      # count of 50% crossings

    def to_dict(self) -> dict:
        return {
            'heart_rate': round(self.heart_rate, 4),
            'amplitude': round(self.amplitude, 4),
            'arrhythmia': round(self.arrhythmia, 4),
            'vitals': round(self.vitals, 4),
            'time_weight': round(self.time_weight, 4),
            'lead_changes': self.lead_changes,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class PulseResult:
    """Result of Pulse calculation."""
    score: int             # 1-100 final score
    components: PulseComponents
    status: str            # 'racing', 'strong', 'steady', 'weak', 'flatline'
    data_quality: str      # 'good', 'limited', 'minimal'
    snapshot_count: int


def get_expected_duration(sport_key: str) -> int:
    """Get expected game duration in minutes."""
    for prefix, duration in EXPECTED_DURATIONS.items():
        if sport_key and sport_key.startswith(prefix):
            return duration
    return 150  # Default 2.5 hours


def get_pulse_status(score: int) -> str:
    """Convert score to status label."""
    if score >= 81:
        return 'racing'
    elif score >= 61:
        return 'strong'
    elif score >= 41:
        return 'steady'
    elif score >= 21:
        return 'weak'
    else:
        return 'flatline'


def get_pulse_emoji(score: int) -> str:
    """Get emoji for pulse score."""
    if score >= 81:
        return '🫀'  # Racing heart
    elif score >= 61:
        return '💓'  # Strong heartbeat
    elif score >= 41:
        return '💗'  # Steady
    elif score >= 21:
        return '🩺'  # Weak, needs attention
    else:
        return '📉'  # Flatline


def get_pulse_label(score: int) -> str:
    """Get human-readable label for pulse score."""
    if score >= 90:
        return 'Incredible'
    elif score >= 81:
        return 'Must-Watch'
    elif score >= 71:
        return 'Exciting'
    elif score >= 61:
        return 'Engaging'
    elif score >= 51:
        return 'Competitive'
    elif score >= 41:
        return 'Steady'
    elif score >= 31:
        return 'Slow'
    elif score >= 21:
        return 'One-Sided'
    else:
        return 'Flatline'


def _aggregate_snapshots(snapshots: list[PulseDataPoint], bucket_seconds: int = 60) -> list[PulseDataPoint]:
    """
    Aggregate multi-bookmaker snapshots into one data point per time bucket.

    Multiple bookmakers report slightly different probabilities at each polling
    cycle. Without aggregation, the algorithm treats bookmaker disagreements as
    probability "movements", massively inflating heart_rate, amplitude,
    arrhythmia, and phantom lead changes.

    Groups snapshots into time buckets and takes the median probability across
    all bookmakers in each bucket, producing a single clean time series.

    Args:
        snapshots: Raw snapshots (may contain multiple bookmakers per timestamp)
        bucket_seconds: Time bucket size in seconds (default 60s)

    Returns:
        Aggregated list with one PulseDataPoint per time bucket
    """
    if not snapshots:
        return []

    # Group snapshots into time buckets
    buckets: dict[int, list[PulseDataPoint]] = defaultdict(list)
    for s in snapshots:
        # Round timestamp to nearest bucket
        ts = s.captured_at.timestamp()
        bucket_key = int(ts // bucket_seconds) * bucket_seconds
        buckets[bucket_key].append(s)

    # Produce one data point per bucket using median probability
    aggregated = []
    for bucket_key in sorted(buckets.keys()):
        bucket = buckets[bucket_key]
        probs = [s.home_win_probability for s in bucket if s.home_win_probability is not None]
        if not probs:
            continue

        # Use the midpoint of the bucket as the timestamp
        representative_time = bucket[0].captured_at
        aggregated.append(PulseDataPoint(
            captured_at=representative_time,
            home_win_probability=median(probs),
            bookmaker="consensus",
        ))

    return aggregated


def calculate_pulse(
    snapshots: list[PulseDataPoint],
    game_start: datetime,
    current_time: datetime,
    sport_key: str,
) -> Optional[PulseResult]:
    """
    Calculate the Pulse score for a game.

    Args:
        snapshots: List of probability snapshots
        game_start: When the game started
        current_time: Current time (or game end time for completed games)
        sport_key: Sport identifier for duration estimation

    Returns:
        PulseResult with score and components, or None if insufficient data
    """
    # Filter to snapshots with valid probability data
    valid_snapshots = [
        s for s in snapshots
        if s.home_win_probability is not None
        and s.captured_at >= game_start
    ]

    if len(valid_snapshots) < MIN_SNAPSHOTS:
        # Not enough data to compute a meaningful score
        return None

    # Aggregate multi-bookmaker snapshots into one data point per time bucket.
    # This prevents bookmaker disagreements from being counted as movements.
    raw_count = len(valid_snapshots)
    valid_snapshots = _aggregate_snapshots(valid_snapshots)

    if len(valid_snapshots) < MIN_SNAPSHOTS:
        # Not enough distinct time buckets after aggregation
        return None

    # Sort by time
    valid_snapshots.sort(key=lambda s: s.captured_at)

    # Calculate time-related values
    elapsed_minutes = (current_time - game_start).total_seconds() / 60
    expected_duration = get_expected_duration(sport_key)
    game_progress = min(1.0, elapsed_minutes / expected_duration)

    # Extract probability sequence
    probs = [s.home_win_probability for s in valid_snapshots]

    # Calculate deltas (changes between consecutive snapshots)
    deltas = [abs(probs[i] - probs[i-1]) for i in range(1, len(probs))]

    # =========================================================================
    # 1. HEART RATE: Frequency of significant moves
    # =========================================================================
    significant_moves = sum(1 for d in deltas if d >= SIGNIFICANT_MOVE_THRESHOLD)

    # Normalize: ceiling of 0.6 moves/min lets the most exciting observed games
    # reach ~95% while spreading the middle. (0.3 caused 26% saturation, 1.5
    # compressed everything below 38%.)
    moves_per_minute = significant_moves / max(1, elapsed_minutes)
    heart_rate = min(1.0, moves_per_minute / 0.6)

    # =========================================================================
    # 2. AMPLITUDE: Average magnitude of swings
    # =========================================================================
    if deltas:
        # Use RMS (root mean square) to weight larger swings more
        rms_amplitude = math.sqrt(mean([d**2 for d in deltas]))
        # Normalize: 15% RMS swing = max amplitude (was 8%, too easy to saturate)
        amplitude = min(1.0, rms_amplitude / 0.15)
    else:
        amplitude = 0.0

    # =========================================================================
    # 3. ARRHYTHMIA: Unpredictability (variance of changes)
    # =========================================================================
    if len(deltas) >= 2:
        try:
            delta_stdev = stdev(deltas)
            # Normalize: high variance = unpredictable = exciting
            arrhythmia = min(1.0, delta_stdev / 0.10)
        except:
            arrhythmia = 0.0
    else:
        arrhythmia = 0.0

    # =========================================================================
    # 4. VITALS: Average competitiveness across the game
    # =========================================================================
    # Use average closeness to 50% across all snapshots, not just the final one.
    # This rewards games that stayed competitive throughout, not just games that
    # happened to end close. Each snapshot contributes: 1.0 at 50%, 0.0 at 0%/100%.
    closeness_scores = [1.0 - abs(p - 0.5) * 2 for p in probs]
    vitals = mean(closeness_scores)

    # =========================================================================
    # 5. TIME WEIGHT: Late game drama matters more
    # =========================================================================
    # Exponential curve: starts at 0.6, reaches 1.0 at end, accelerates late
    time_weight = 0.6 + (0.4 * (game_progress ** 1.5))

    # =========================================================================
    # 6. LEAD CHANGES: Count of 50% threshold crossings
    # =========================================================================
    lead_changes = 0
    for i in range(1, len(probs)):
        # Check if probability crossed 50%
        if (probs[i-1] < 0.5 and probs[i] >= 0.5) or (probs[i-1] >= 0.5 and probs[i] < 0.5):
            lead_changes += 1

    # Lead change bonus (each lead change adds up to 5 points, max 20)
    lead_change_bonus = min(0.20, lead_changes * 0.05)

    # =========================================================================
    # COMBINE COMPONENTS
    # =========================================================================
    raw_score = (
        heart_rate * 0.25 +
        amplitude * 0.30 +
        arrhythmia * 0.15 +
        vitals * 0.30 +
        lead_change_bonus
    ) * time_weight

    # Scale to 1-100
    # The max theoretical raw_score is about 1.2 (all components 1.0 + 0.2 lead bonus)
    # A divisor of 1.0 means only truly exceptional games reach 100:
    # - All components maxed without lead changes = exactly 100
    # - Lead changes can push past, but get clamped to 100
    # - A typical close game scores 60-75 instead of hitting the ceiling
    scaled_score = raw_score / 1.0 * 100
    final_score = max(1, min(100, round(scaled_score)))

    # Determine data quality
    if len(valid_snapshots) >= 30:
        data_quality = 'good'
    elif len(valid_snapshots) >= 10:
        data_quality = 'limited'
    else:
        data_quality = 'minimal'

    components = PulseComponents(
        heart_rate=heart_rate,
        amplitude=amplitude,
        arrhythmia=arrhythmia,
        vitals=vitals,
        time_weight=time_weight,
        lead_changes=lead_changes,
    )

    return PulseResult(
        score=final_score,
        components=components,
        status=get_pulse_status(final_score),
        data_quality=data_quality,
        snapshot_count=len(valid_snapshots),
    )
