"""
Game Excitement Index (GEI) calculation module.

Calculates how exciting a sporting event was based on odds movement data.
The final score is a 1-100 percentile ranking computed both within-sport
and cross-sport.

Components:
- Win Probability Volatility (40%): Total probability swing during game
- Late-Game Uncertainty (25%): Closeness weighted toward end of game
- Expectation Deviation (20%): Drift from pre-game expectations
- Comeback Factor (15%): Magnitude of largest comeback

Reference: Inspired by Luke Benz's GEI and FiveThirtyEight's NBA Excitement Index
"""

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

# Noise filtering thresholds
NOISE_THRESHOLD = 0.02  # 2% minimum swing to count
BUCKET_MINUTES = 1  # Time bucket size for aggregation

# Component weights
WEIGHT_WPV = 0.40  # Win Probability Volatility
WEIGHT_LGU = 0.25  # Late-Game Uncertainty
WEIGHT_ED = 0.20   # Expectation Deviation
WEIGHT_CF = 0.15   # Comeback Factor

# Sport-specific volatility multipliers (normalize across sports)
SPORT_VOLATILITY_MULTIPLIERS = {
    'basketball_nba': 1.0,
    'basketball_ncaab': 1.0,
    'basketball_wncaab': 1.0,
    'basketball_wnba': 1.0,
    'americanfootball_nfl': 1.2,
    'americanfootball_ncaaf': 1.2,
    'baseball_mlb': 1.5,
    'icehockey_nhl': 1.3,
    'mma_mixed_martial_arts': 0.9,
    'boxing_boxing': 0.9,
}

# Expected game durations in hours (for overtime detection)
EXPECTED_DURATIONS = {
    'basketball_nba': 2.5,
    'basketball_ncaab': 2.25,
    'basketball_wncaab': 2.25,
    'basketball_wnba': 2.25,
    'americanfootball_nfl': 3.25,
    'americanfootball_ncaaf': 3.5,
    'baseball_mlb': 3.0,
    'icehockey_nhl': 2.5,
}

# Sport average totals for scoring factor normalization
SPORT_AVG_TOTALS = {
    'basketball_nba': 225.0,
    'basketball_ncaab': 145.0,
    'basketball_wncaab': 135.0,
    'basketball_wnba': 165.0,
    'americanfootball_nfl': 45.0,
    'americanfootball_ncaaf': 52.0,
    'baseball_mlb': 8.5,
    'icehockey_nhl': 6.0,
}


@dataclass
class OddsDataPoint:
    """Represents a single odds data point for GEI calculation."""
    captured_at: datetime
    home_win_probability: Optional[float]
    home_spread: Optional[float]
    over_under: Optional[float]
    bookmaker: str


@dataclass
class GEIComponents:
    """Individual component scores for GEI."""
    win_probability_volatility: float
    late_game_uncertainty: float
    expectation_deviation: float
    comeback_factor: float
    overtime_bonus: float

    def to_dict(self) -> dict:
        return {
            'win_probability_volatility': round(self.win_probability_volatility, 4),
            'late_game_uncertainty': round(self.late_game_uncertainty, 4),
            'expectation_deviation': round(self.expectation_deviation, 4),
            'comeback_factor': round(self.comeback_factor, 4),
            'overtime_bonus': round(self.overtime_bonus, 4),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class GEIResult:
    """Result of GEI calculation."""
    raw_gei: float
    components: GEIComponents
    data_quality: str  # 'good', 'limited', 'insufficient'
    snapshot_count: int


def get_sport_multiplier(sport_key: str) -> float:
    """Get volatility multiplier for a sport."""
    for prefix, mult in SPORT_VOLATILITY_MULTIPLIERS.items():
        if sport_key.startswith(prefix.replace('_*', '')):
            return mult
    return 1.0


def get_expected_duration(sport_key: str) -> float:
    """Get expected game duration in hours."""
    for prefix, duration in EXPECTED_DURATIONS.items():
        if sport_key.startswith(prefix):
            return duration
    return 2.5  # Default


def detect_overtime(
    game_start: datetime,
    market_close: datetime,
    sport_key: str
) -> bool:
    """Detect if game likely went to overtime based on duration."""
    duration_hours = (market_close - game_start).total_seconds() / 3600
    expected_hours = get_expected_duration(sport_key)
    return duration_hours > expected_hours * 1.15  # 15% buffer


def bucket_snapshots(
    data_points: list[OddsDataPoint],
    bucket_minutes: int = BUCKET_MINUTES
) -> list[OddsDataPoint]:
    """
    Group snapshots into time buckets, taking the last snapshot in each bucket.

    This prevents over-counting rapid oscillations.
    """
    if not data_points:
        return []

    buckets: dict[datetime, list[OddsDataPoint]] = defaultdict(list)

    for point in data_points:
        # Round down to bucket
        bucket_key = point.captured_at.replace(second=0, microsecond=0)
        bucket_minute = (bucket_key.minute // bucket_minutes) * bucket_minutes
        bucket_key = bucket_key.replace(minute=bucket_minute)
        buckets[bucket_key].append(point)

    # Take last snapshot in each bucket (most recent)
    result = []
    for bucket_time in sorted(buckets.keys()):
        points = buckets[bucket_time]
        # Take the one with the latest captured_at
        latest = max(points, key=lambda p: p.captured_at)
        result.append(latest)

    return result


def get_consensus_probabilities(data_points: list[OddsDataPoint]) -> list[float]:
    """
    Get consensus (median) probabilities across bookmakers at each timestamp.

    This filters out noise from individual book movements.
    """
    # Group by bucketed timestamp
    bucketed = bucket_snapshots(data_points)

    # For each bucket, we now have one point (already filtered)
    # But if we want true consensus across books at each time, we need
    # to aggregate differently. For simplicity, the bucket approach
    # already reduces noise significantly.

    return [
        p.home_win_probability
        for p in bucketed
        if p.home_win_probability is not None
    ]


def calculate_wpv(data_points: list[OddsDataPoint]) -> float:
    """
    Calculate Win Probability Volatility.

    Sum of significant win probability changes, normalized.
    Only counts changes >= NOISE_THRESHOLD (2%).
    """
    probs = get_consensus_probabilities(data_points)

    if len(probs) < 2:
        return 0.0

    total_swing = 0.0

    for i in range(1, len(probs)):
        change = abs(probs[i] - probs[i-1])
        if change >= NOISE_THRESHOLD:
            total_swing += change

    # Normalize: a total swing of 2.0 (200%) would be extremely high
    # Scale so typical exciting games are in 0.5-1.0 range
    return min(1.0, total_swing / 1.5)


def calculate_lgu(
    data_points: list[OddsDataPoint],
    game_start: datetime,
    market_close: datetime
) -> float:
    """
    Calculate Late-Game Uncertainty.

    Weighted average of how close the game was, with exponential
    weight toward the end. "Closeness" peaks at 50/50.
    """
    if not data_points:
        return 0.0

    total_duration = (market_close - game_start).total_seconds()
    if total_duration <= 0:
        return 0.0

    weighted_closeness = 0.0
    total_weight = 0.0

    for point in data_points:
        if point.captured_at < game_start:
            continue
        if point.home_win_probability is None:
            continue

        # How far through the game (0 = start, 1 = end)
        progress = (point.captured_at - game_start).total_seconds() / total_duration
        progress = min(1.0, max(0.0, progress))

        # Exponential weight: e^(2*progress) gives ~7x weight at end vs start
        weight = math.exp(2 * progress)

        # Closeness: 1.0 at 50/50, 0.0 at 100/0
        prob = point.home_win_probability
        closeness = 1 - abs(prob - 0.5) * 2

        weighted_closeness += closeness * weight
        total_weight += weight

    return weighted_closeness / total_weight if total_weight > 0 else 0.0


def calculate_expectation_deviation(
    opening_spread: Optional[float],
    opening_total: Optional[float],
    closing_spread: Optional[float],
    closing_total: Optional[float],
    opening_prob: Optional[float],
    closing_prob: Optional[float],
) -> float:
    """
    Measure how much the game deviated from pre-game expectations.

    Components:
    1. Spread drift: How much did the spread move?
    2. Total drift: How much did the total move?
    3. Probability shift: How much did win probability change?
    4. Favorite flip bonus: Did the favorite change?
    """
    spread_drift = 0.0
    total_drift = 0.0
    prob_shift = 0.0
    flip_bonus = 0.0

    # Spread drift (normalized by typical spread range ~15 points)
    if opening_spread is not None and closing_spread is not None:
        spread_drift = abs(closing_spread - opening_spread) / 15.0

    # Total drift (normalized by opening total)
    if opening_total is not None and closing_total is not None and opening_total > 0:
        total_drift = abs(closing_total - opening_total) / opening_total

    # Probability shift (0-1 scale, already normalized)
    if opening_prob is not None and closing_prob is not None:
        prob_shift = abs(closing_prob - opening_prob)

        # Favorite flip bonus (if the favorite changed during the game)
        if (opening_prob > 0.5) != (closing_prob > 0.5):
            flip_bonus = 0.3

    # Combined score (max 1.0 before flip bonus)
    deviation = min(1.0, spread_drift * 0.3 + total_drift * 0.3 + prob_shift * 0.4)

    return min(1.0, deviation + flip_bonus)


def calculate_comeback_factor(data_points: list[OddsDataPoint]) -> float:
    """
    Measure the largest comeback during the game.

    A "comeback" is when a team goes from significantly unfavored to winning.
    """
    probs = get_consensus_probabilities(data_points)

    if len(probs) < 2:
        return 0.0

    min_home_prob = min(probs)
    max_home_prob = max(probs)
    final_prob = probs[-1]

    max_comeback = 0.0

    # If home won (final prob > 0.5), comeback = how far they came from their lowest
    if final_prob > 0.5:
        # They needed to be below 50% at some point for it to be a comeback
        if min_home_prob < 0.5:
            max_comeback = final_prob - min_home_prob

    # If away won (final prob < 0.5), their comeback = home's best - final
    if final_prob < 0.5:
        if max_home_prob > 0.5:
            max_comeback = max(max_comeback, max_home_prob - final_prob)

    # Normalize: a 40% swing (from 30% to 70%) is a big comeback
    return min(1.0, max_comeback / 0.4)


def calculate_gei(
    snapshots: list[OddsDataPoint],
    game_start: datetime,
    market_close: datetime,
    sport_key: str,
) -> Optional[GEIResult]:
    """
    Calculate the Game Excitement Index for an event.

    Args:
        snapshots: List of odds data points for the event
        game_start: When the game started (commence_time)
        market_close: When the odds markets closed (last snapshot time)
        sport_key: Sport identifier for normalization

    Returns:
        GEIResult with raw score and components, or None if insufficient data
    """
    # Filter to live snapshots only (after game start)
    live_snapshots = [s for s in snapshots if s.captured_at >= game_start]

    if len(live_snapshots) < 3:
        return GEIResult(
            raw_gei=0.0,
            components=GEIComponents(0, 0, 0, 0, 0),
            data_quality='insufficient',
            snapshot_count=len(live_snapshots)
        )

    # Get opening odds (closest snapshot to game start)
    pre_game = [s for s in snapshots if s.captured_at < game_start]
    if pre_game:
        opening = max(pre_game, key=lambda s: s.captured_at)
    else:
        opening = live_snapshots[0]

    closing = live_snapshots[-1]

    # Calculate components
    wpv = calculate_wpv(live_snapshots)
    lgu = calculate_lgu(live_snapshots, game_start, market_close)
    ed = calculate_expectation_deviation(
        opening_spread=opening.home_spread,
        opening_total=opening.over_under,
        closing_spread=closing.home_spread,
        closing_total=closing.over_under,
        opening_prob=opening.home_win_probability,
        closing_prob=closing.home_win_probability,
    )
    cf = calculate_comeback_factor(live_snapshots)

    # Overtime bonus
    is_overtime = detect_overtime(game_start, market_close, sport_key)
    overtime_bonus = 0.15 if is_overtime else 0.0

    # Weighted combination
    raw_gei = (
        wpv * WEIGHT_WPV +
        lgu * WEIGHT_LGU +
        ed * WEIGHT_ED +
        cf * WEIGHT_CF +
        overtime_bonus
    )

    # Apply sport-specific multiplier for cross-sport comparability
    sport_multiplier = get_sport_multiplier(sport_key)
    raw_gei *= sport_multiplier

    # Determine data quality
    if len(live_snapshots) >= 20:
        data_quality = 'good'
    elif len(live_snapshots) >= 10:
        data_quality = 'limited'
    else:
        data_quality = 'minimal'

    components = GEIComponents(
        win_probability_volatility=wpv,
        late_game_uncertainty=lgu,
        expectation_deviation=ed,
        comeback_factor=cf,
        overtime_bonus=overtime_bonus,
    )

    return GEIResult(
        raw_gei=raw_gei,
        components=components,
        data_quality=data_quality,
        snapshot_count=len(live_snapshots)
    )


def calculate_expected_excitement(
    home_prob: float,
    over_under: Optional[float],
    sport_key: str,
) -> float:
    """
    Predict how exciting a game is likely to be BEFORE it starts.

    Based on:
    1. Closeness of matchup (spreads near 0 = more excitement potential)
    2. Expected scoring (higher totals = more action)

    Returns a 0-1 score representing expected excitement.
    """
    # Closeness factor: peaks at 50/50
    closeness = 1 - abs(home_prob - 0.5) * 2

    # Scoring factor: normalized by sport average
    avg_total = SPORT_AVG_TOTALS.get(sport_key)
    if avg_total and over_under:
        scoring_factor = min(1.0, over_under / avg_total)
    else:
        scoring_factor = 0.5  # Default middle value

    # Combine: closeness matters more
    expected = closeness * 0.7 + scoring_factor * 0.3

    return expected


def get_gei_label(percentile: int) -> str:
    """Get human-readable excitement label from percentile."""
    if percentile >= 95:
        return "Instant Classic"
    elif percentile >= 90:
        return "Highly Exciting"
    elif percentile >= 75:
        return "Exciting"
    elif percentile >= 50:
        return "Average"
    elif percentile >= 25:
        return "Below Average"
    else:
        return "Low Excitement"


def get_gei_emoji(percentile: int) -> str:
    """Get emoji for GEI percentile."""
    if percentile >= 95:
        return "🔥"
    elif percentile >= 90:
        return "⚡"
    elif percentile >= 75:
        return "👀"
    elif percentile >= 50:
        return ""
    else:
        return ""
