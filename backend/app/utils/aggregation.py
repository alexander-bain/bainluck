"""
Multi-source probability aggregation engine.

Combines sportsbook consensus, prediction markets (Kalshi, Polymarket),
and statistical models (ESPN, Bain Luck Model) into a single "Bain Luck"
aggregate probability.

Algorithm: Weighted median with staleness decay and exponential smoothing.

The weighted median is inherently outlier-resistant — a single stale or
erratic source cannot drag the aggregate because it's just one data point
in the median calculation. This is preferred over weighted mean, which
is sensitive to outlier values.

Source weights reflect depth and reliability:
  - Sportsbook consensus (3.0): Deep liquidity, 5-15 bookmakers
  - ESPN model (1.5): Play-by-play responsive, proprietary
  - Bain Luck Model (1.0): Statistical, principled, but simple
  - Kalshi (0.8): Regulated prediction market, thinner liquidity
  - Polymarket (0.8): Largest prediction market, good liquidity
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# Base weights per source — higher = more influence on the aggregate
SOURCE_WEIGHTS: dict[str, float] = {
    "betting": 3.0,        # Sportsbook consensus (5-15 books)
    "espn": 1.5,           # ESPN proprietary model
    "stat_model": 1.0,     # Bain Luck statistical model
    "kalshi": 0.8,         # Kalshi prediction market
    "polymarket": 0.8,     # Polymarket prediction market
    "mlb": 0.8,            # MLB Model (MLB Stats API)
    "moneypuck": 0.8,      # MoneyPuck (NHL) — stub
}

# Staleness parameters (in seconds)
STALENESS_GRACE_PERIOD = 120   # 2 min: no penalty
STALENESS_DECAY_WINDOW = 180   # Next 3 min: linear decay to 0
MAX_STALENESS = STALENESS_GRACE_PERIOD + STALENESS_DECAY_WINDOW  # 5 min: fully stale

# Exponential smoothing factor (0-1, higher = more weight on new value)
SMOOTHING_ALPHA = 0.3


@dataclass
class TimestampedProb:
    """A probability reading at a point in time."""
    timestamp: datetime
    home_probability: float


@dataclass
class SourceReading:
    """Latest reading from a single source, with weight."""
    source: str
    probability: float
    weight: float
    stale_seconds: float


def _staleness_weight(stale_seconds: float) -> float:
    """
    Compute weight multiplier based on staleness.

    0-2 min: 1.0 (full weight)
    2-5 min: linear decay from 1.0 to 0.0
    5+ min:  0.0 (fully dropped)
    """
    if stale_seconds <= STALENESS_GRACE_PERIOD:
        return 1.0
    elif stale_seconds >= MAX_STALENESS:
        return 0.0
    else:
        elapsed_past_grace = stale_seconds - STALENESS_GRACE_PERIOD
        return max(0.0, 1.0 - elapsed_past_grace / STALENESS_DECAY_WINDOW)


def _weighted_median(values: list[float], weights: list[float]) -> float:
    """
    Compute weighted median.

    Sort values, accumulate weights, find the value at the 50th percentile
    of cumulative weight.
    """
    if not values:
        raise ValueError("Cannot compute weighted median of empty list")
    if len(values) == 1:
        return values[0]

    # Sort by value
    paired = sorted(zip(values, weights), key=lambda x: x[0])
    total_weight = sum(w for _, w in paired)
    if total_weight <= 0:
        # All weights are zero, fall back to simple median
        vals = [v for v, _ in paired]
        mid = len(vals) // 2
        return vals[mid]

    half = total_weight / 2.0
    cumulative = 0.0
    for value, weight in paired:
        cumulative += weight
        if cumulative >= half:
            return value

    # Shouldn't reach here, but return last value as fallback
    return paired[-1][0]


def compute_aggregated_probability(
    sources: dict[str, list[TimestampedProb]],
    bucket_seconds: int = 30,
    custom_weights: Optional[dict[str, float]] = None,
) -> list[TimestampedProb]:
    """
    Aggregate multiple probability sources into a single time series.

    For each time bucket:
    1. Find the latest reading from each source (carry-forward up to 5 min)
    2. Apply staleness-based weight decay
    3. Compute weighted median across all active sources
    4. Apply exponential smoothing to prevent jumps

    Args:
        sources: Dict mapping source key → list of timestamped probabilities
        bucket_seconds: Time bucket size in seconds (default 30s)
        custom_weights: Override default source weights

    Returns:
        Aggregated time series of probabilities
    """
    weights = custom_weights or SOURCE_WEIGHTS

    if not sources:
        return []

    # Collect all timestamps across all sources to define bucket boundaries
    all_timestamps: set[float] = set()
    for source_points in sources.values():
        for point in source_points:
            ts = point.timestamp.timestamp()
            bucket_key = int(ts // bucket_seconds) * bucket_seconds
            all_timestamps.add(bucket_key)

    if not all_timestamps:
        return []

    sorted_buckets = sorted(all_timestamps)

    # Build per-source sorted lists for efficient carry-forward lookup
    source_sorted: dict[str, list[TimestampedProb]] = {}
    for source_key, points in sources.items():
        source_sorted[source_key] = sorted(points, key=lambda p: p.timestamp)

    # For each bucket, find latest reading per source
    aggregated: list[TimestampedProb] = []
    prev_value: Optional[float] = None

    for bucket_ts in sorted_buckets:
        bucket_time = datetime.fromtimestamp(bucket_ts, tz=None)
        # Use timezone from the first source's first point
        for pts in sources.values():
            if pts:
                bucket_time = datetime.fromtimestamp(
                    bucket_ts, tz=pts[0].timestamp.tzinfo
                )
                break

        readings: list[SourceReading] = []

        for source_key, points in source_sorted.items():
            base_weight = weights.get(source_key, 0.5)  # Default weight for unknown sources

            # Find latest reading at or before this bucket
            latest: Optional[TimestampedProb] = None
            for point in points:
                if point.timestamp.timestamp() <= bucket_ts + bucket_seconds:
                    latest = point
                else:
                    break

            if latest is None:
                continue

            # Calculate staleness
            stale_seconds = bucket_ts - latest.timestamp.timestamp()
            if stale_seconds < 0:
                stale_seconds = 0

            # Apply staleness decay
            stale_mult = _staleness_weight(stale_seconds)
            effective_weight = base_weight * stale_mult

            if effective_weight > 0:
                readings.append(SourceReading(
                    source=source_key,
                    probability=latest.home_probability,
                    weight=effective_weight,
                    stale_seconds=stale_seconds,
                ))

        if not readings:
            continue

        # Compute weighted median
        values = [r.probability for r in readings]
        wts = [r.weight for r in readings]
        raw_aggregate = _weighted_median(values, wts)

        # Apply exponential smoothing
        if prev_value is not None:
            smoothed = SMOOTHING_ALPHA * raw_aggregate + (1 - SMOOTHING_ALPHA) * prev_value
        else:
            smoothed = raw_aggregate

        prev_value = smoothed

        aggregated.append(TimestampedProb(
            timestamp=bucket_time,
            home_probability=round(smoothed, 6),
        ))

    return aggregated


def compute_current_aggregate(
    source_readings: dict[str, tuple[float, datetime]],
    now: datetime,
    custom_weights: Optional[dict[str, float]] = None,
) -> Optional[float]:
    """
    Compute a single aggregate probability from current source readings.

    Simpler version of the full time-series aggregation, for use in
    real-time event serialization.

    Args:
        source_readings: Dict mapping source key → (probability, last_updated)
        now: Current time
        custom_weights: Override default source weights

    Returns:
        Aggregated probability (0-1) or None if no valid readings
    """
    weights = custom_weights or SOURCE_WEIGHTS

    values: list[float] = []
    wts: list[float] = []

    for source_key, (probability, updated_at) in source_readings.items():
        base_weight = weights.get(source_key, 0.5)
        stale_seconds = (now - updated_at).total_seconds()

        stale_mult = _staleness_weight(max(0, stale_seconds))
        effective_weight = base_weight * stale_mult

        if effective_weight > 0:
            values.append(probability)
            wts.append(effective_weight)

    if not values:
        return None

    return round(_weighted_median(values, wts), 6)


def compute_aggregate_probability(event) -> Optional[float]:
    """Compute aggregate home win probability from all available sources.

    Uses SOURCE_WEIGHTS to produce a weighted average of all available
    probability readings on the event model.  Falls back through three
    tiers of decreasing richness.

    Works on any object with win_probability_sources, espn_win_prob_home,
    and opening_home_probability attributes (typically an Event model).
    """
    # Tier 1: win_probability_sources JSONB (live games — multiple sources)
    wps = getattr(event, "win_probability_sources", None) or {}
    prob_readings: dict[str, float] = {}
    for k, v in wps.items():
        if k not in SOURCE_WEIGHTS:
            continue
        if isinstance(v, (int, float)):
            prob_readings[k] = float(v)
        elif isinstance(v, dict) and "value" in v:
            val = v["value"]
            if isinstance(val, (int, float)):
                prob_readings[k] = float(val)

    if prob_readings:
        total_weight = 0.0
        weighted_sum = 0.0
        for source, prob in prob_readings.items():
            w = SOURCE_WEIGHTS.get(source, 0.5)
            weighted_sum += prob * w
            total_weight += w
        if total_weight > 0:
            return round(weighted_sum / total_weight, 6)

    # Tier 2: ESPN win probability (live games, single source)
    espn_prob = getattr(event, "espn_win_prob_home", None)
    if espn_prob is not None:
        return round(float(espn_prob), 6)

    # Tier 3: Opening probability (Odds API sportsbook consensus)
    opening_prob = getattr(event, "opening_home_probability", None)
    if opening_prob is not None:
        return round(float(opening_prob), 6)

    return None
