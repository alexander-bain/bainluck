"""
Multi-source probability aggregation engine.

Combines sportsbook consensus, prediction markets (Kalshi, Polymarket),
and statistical models (ESPN, Bain Luck Model) into a single "Bain Luck"
aggregate probability.

Algorithm: Weighted median with staleness decay. NO smoothing — see below.

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
    "final_result": 5.0,   # Resolved game outcome from score (always correct)
    "betting": 3.0,        # Sportsbook consensus (5-15 books)
    "espn": 1.5,           # ESPN proprietary model
    "stat_model": 1.0,     # Bain Luck statistical model
    "kalshi": 0.8,         # Kalshi prediction market
    "polymarket": 0.8,     # Polymarket prediction market
    "mlb": 0.8,            # MLB Model (MLB Stats API)
}

# Staleness parameters (in seconds)
STALENESS_GRACE_PERIOD = 120   # 2 min: no penalty
STALENESS_DECAY_WINDOW = 180   # Next 3 min: linear decay to 0
MAX_STALENESS = STALENESS_GRACE_PERIOD + STALENESS_DECAY_WINDOW  # 5 min: fully stale

# NO SMOOTHING (standing ruling #4, UX-P003). The blend line the chart draws used
# to run an α=0.3 exponential moving average over the per-bucket weighted median.
# That is smoothing, and smoothing HIDES real movement — the thing the chart exists
# to show. It also silently de-synced the surfaces: because the EMA lags, the last
# point of `aggregate_line` (the chart's live edge, and the web hero's live source)
# drifted away from `compute_aggregate_probability()` (the Discover card and the
# backend `hero_probability`), so one game showed two different numbers on two
# screens. Measured on production 2026-08-05 (live MLB): Giants @ Rangers card 60%
# vs chart 78%, of which +14.5 pts was attributable to the EMA alone.
#
# Staleness decay below is deliberately KEPT: that is source *weighting* (how much
# a reading counts), not smoothing (blurring the output over time).


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

    No smoothing is applied (standing ruling #4) — each bucket is the honest
    weighted median of what the sources actually said in that bucket.

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

        # No smoothing (ruling #4): emit the bucket's honest weighted median.
        aggregated.append(TimestampedProb(
            timestamp=bucket_time,
            home_probability=round(raw_aggregate, 6),
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


_EXCLUDE_WHEN_COMPLETED = {"kalshi", "polymarket"}


def compute_aggregate_probability(event, event_status: Optional[str] = None) -> Optional[float]:
    """Compute aggregate home win probability from all available sources.

    Uses SOURCE_WEIGHTS to produce a weighted average of all available
    probability readings on the event model.  Falls back through three
    tiers of decreasing richness.

    When event_status is "completed" or "closed", prediction market sources
    (Kalshi, Polymarket) are excluded — their prices go stale post-final
    and drag the aggregate away from the resolved sportsbook/ESPN values.

    Works on any object with win_probability_sources, espn_win_prob_home,
    and opening_home_probability attributes (typically an Event model).
    """
    status = event_status or getattr(event, "status", None)
    is_finished = status in ("completed", "closed")

    # Tier 1: win_probability_sources JSONB (live games — multiple sources)
    wps = getattr(event, "win_probability_sources", None) or {}
    prob_readings: dict[str, float] = {}
    for k, v in wps.items():
        if k not in SOURCE_WEIGHTS:
            continue
        if is_finished and k in _EXCLUDE_WHEN_COMPLETED:
            continue
        if isinstance(v, (int, float)):
            prob_readings[k] = float(v)
        elif isinstance(v, dict) and "value" in v:
            val = v["value"]
            if isinstance(val, (int, float)):
                prob_readings[k] = float(val)

    if prob_readings:
        # Weighted MEDIAN (not mean) — the same outlier-resistant method the
        # time-series blend (compute_aggregated_probability → the chart's
        # aggregate_line) uses. This is the module's stated design (see the
        # docstring): a single stale/lagged source cannot drag the aggregate.
        #
        # A weighted MEAN here let a stale sportsbook "betting" reading (weight
        # 3.0) that had not caught up to the live game state pull the hero toward
        # the pre-game number (~57%) while the chart's median-based blend line
        # read the live value (~20%) on the same screen — the 57%-hero vs
        # 20%-chart contradiction (#240 Item 1). Using the median here makes the
        # point-in-time hero match the chart's blend line: one number per
        # question.
        values = list(prob_readings.values())
        weights = [SOURCE_WEIGHTS.get(src, 0.5) for src in prob_readings]
        if any(w > 0 for w in weights):
            return round(_weighted_median(values, weights), 6)

    # Tier 2: ESPN win probability (live games, single source)
    espn_prob = getattr(event, "espn_win_prob_home", None)
    if espn_prob is not None:
        return round(float(espn_prob), 6)

    # Tier 3: Opening probability (Odds API sportsbook consensus)
    opening_prob = getattr(event, "opening_home_probability", None)
    if opening_prob is not None:
        return round(float(opening_prob), 6)

    return None
