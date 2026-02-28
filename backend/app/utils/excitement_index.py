"""
Excitement Index (EI) — Game excitement metric.

Standard Game Excitement Index formula from sports analytics:
  EI_raw = (T_regulation / T_actual) × Σ|pᵢ - pᵢ₋₁|

The raw value represents the total "distance traveled" by the win
probability curve, normalized to regulation game length. A raw EI of
4.0 means the probability traveled 400% total distance.

Typical raw EI ranges:
  - 1.0-2.0: Uneventful (blowout or minimal swings)
  - 2.0-3.5: Average game
  - 3.5-5.0: Exciting game
  - 5.0+:    Incredible drama

The final score shown to users is a percentile (0-100) based on all
completed games. Score 75 means "more exciting than 75% of games."

References:
  - Brian Burke (Advanced Football Analytics): original EI concept
  - Mike Beuoy (Inpredictable): NBA/WNBA Excitement Index
  - FiveThirtyEight: "The NBA Excitement Index"
  - Luke Benz (ncaahoopR): GEI = (T_reg / T_actual) × Σ|pᵢ - pᵢ₋₁|
"""

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Optional


# Minimum aggregated time buckets needed to compute EI
MIN_SNAPSHOTS = 3

# Regulation game length in seconds (for time normalization)
REGULATION_SECONDS = {
    "basketball_nba": 2880,       # 48 min
    "basketball_ncaab": 2400,     # 40 min
    "basketball_wncaab": 2880,    # 48 min (4x12 quarters)
    "basketball_wnba": 2400,      # 40 min
    "americanfootball_nfl": 3600, # 60 min
    "americanfootball_ncaaf": 3600, # 60 min
    "baseball_mlb": 8100,         # 9 innings × ~15 min avg (no clock)
    "icehockey_nhl": 3600,        # 60 min
    "soccer": 5400,               # 90 min
    "mma_mixed_martial_arts": 1500, # 25 min (5×5)
    "boxing_boxing": 2160,        # 36 min (12×3)
}

# Average wall-clock game duration (including stoppages, halftime, etc.)
# Used to estimate T_actual for completed games when we don't have exact end time
WALL_CLOCK_DURATIONS = {
    "basketball_nba": 9000,       # ~2h 30m
    "basketball_ncaab": 8100,     # ~2h 15m
    "basketball_wncaab": 8100,
    "basketball_wnba": 7200,
    "americanfootball_nfl": 11700, # ~3h 15m
    "americanfootball_ncaaf": 12600, # ~3h 30m
    "baseball_mlb": 10800,        # ~3h
    "icehockey_nhl": 9000,        # ~2h 30m
    "soccer": 6900,               # ~1h 55m
    "mma_mixed_martial_arts": 1500,
    "boxing_boxing": 3600,
}


@dataclass
class EIDataPoint:
    """A single probability snapshot for EI calculation."""
    captured_at: datetime
    home_win_probability: Optional[float]
    source: str  # "consensus", bookmaker name, "aggregate", etc.
    valid_until: Optional[datetime] = None  # When this reading was superseded


@dataclass
class EIMetadata:
    """Companion metrics stored alongside the EI score."""
    raw_ei: float           # Raw EI value (e.g., 3.45 = 345% total travel)
    lead_changes: int       # Number of 50% crossings
    comeback_factor: float  # Lowest probability the eventual winner had (0-1)
    snapshot_count: int     # Aggregated time buckets used

    def to_dict(self) -> dict:
        return {
            "raw_ei": round(self.raw_ei, 4),
            "lead_changes": self.lead_changes,
            "comeback_factor": round(self.comeback_factor, 4),
            "snapshot_count": self.snapshot_count,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class EIResult:
    """Result of Excitement Index calculation."""
    score: int              # 1-100 (raw score; percentile applied later)
    raw_ei: float           # Raw EI value
    metadata: EIMetadata
    data_quality: str       # 'good', 'limited', 'minimal'


def get_regulation_seconds(sport_key: str) -> int:
    """Get regulation game length in seconds for time normalization."""
    for prefix, seconds in REGULATION_SECONDS.items():
        if sport_key and sport_key.startswith(prefix):
            return seconds
    return 3600  # Default 60 min


def get_ei_status(score: int) -> str:
    """Convert score to status label."""
    if score >= 80:
        return "incredible"
    elif score >= 60:
        return "exciting"
    elif score >= 40:
        return "competitive"
    elif score >= 20:
        return "quiet"
    else:
        return "flat"


def get_ei_label(score: int) -> str:
    """Get human-readable label for EI score."""
    if score >= 90:
        return "Incredible"
    elif score >= 80:
        return "Must-Watch"
    elif score >= 70:
        return "Exciting"
    elif score >= 60:
        return "Engaging"
    elif score >= 50:
        return "Competitive"
    elif score >= 40:
        return "Average"
    elif score >= 25:
        return "Quiet"
    else:
        return "Flat"


def get_ei_emoji(score: int) -> str:
    """Get emoji for EI score."""
    if score >= 80:
        return "🔥"
    elif score >= 60:
        return "⚡"
    elif score >= 40:
        return "📊"
    elif score >= 20:
        return "😴"
    else:
        return "📉"


def _aggregate_snapshots(
    snapshots: list[EIDataPoint],
    bucket_seconds: int = 30,
) -> list[EIDataPoint]:
    """
    Aggregate multi-source snapshots into one data point per time bucket.

    Groups snapshots into time buckets and takes the median probability
    across all sources in each bucket, producing a clean time series.

    When a snapshot has valid_until set, it is carried forward into all
    subsequent buckets up to valid_until. This prevents phantom oscillation
    caused by stale bookmakers dropping out of current buckets due to
    write-time dedup.

    Args:
        snapshots: Raw snapshots (may contain multiple sources per timestamp)
        bucket_seconds: Time bucket size in seconds (default 30s)

    Returns:
        Aggregated list with one EIDataPoint per time bucket
    """
    if not snapshots:
        return []

    buckets: dict[int, list[EIDataPoint]] = defaultdict(list)
    for s in snapshots:
        ts = s.captured_at.timestamp()
        bucket_key = int(ts // bucket_seconds) * bucket_seconds
        buckets[bucket_key].append(s)

        # Carry forward: if valid_until extends beyond this bucket,
        # include this snapshot in subsequent buckets up to valid_until
        if s.valid_until is not None and s.home_win_probability is not None:
            vu_ts = s.valid_until.timestamp()
            next_bucket = bucket_key + bucket_seconds
            while next_bucket < vu_ts:
                buckets[next_bucket].append(s)
                next_bucket += bucket_seconds

    aggregated = []
    for bucket_key in sorted(buckets.keys()):
        bucket = buckets[bucket_key]
        # Deduplicate by source: if the same source appears multiple times
        # in a bucket (from carry-forward), keep the latest reading
        by_source: dict[str, EIDataPoint] = {}
        for s in bucket:
            existing = by_source.get(s.source)
            if existing is None or s.captured_at > existing.captured_at:
                by_source[s.source] = s

        probs = [
            s.home_win_probability
            for s in by_source.values()
            if s.home_win_probability is not None
        ]
        if not probs:
            continue

        representative_time = min(s.captured_at for s in by_source.values())
        # Use the bucket start time for consistent spacing
        bucket_time = datetime.fromtimestamp(bucket_key, tz=representative_time.tzinfo)
        aggregated.append(EIDataPoint(
            captured_at=bucket_time,
            home_win_probability=median(probs),
            source="consensus",
        ))

    return aggregated


def calculate_ei(
    snapshots: list[EIDataPoint],
    game_start: datetime,
    current_time: datetime,
    sport_key: str,
    home_won: Optional[bool] = None,
) -> Optional[EIResult]:
    """
    Calculate the Excitement Index for a game.

    Uses the standard GEI formula:
      EI_raw = (T_regulation / T_actual) × Σ|pᵢ - pᵢ₋₁|

    Args:
        snapshots: List of probability snapshots (may contain multiple sources)
        game_start: When the game started
        current_time: Current time (or game end time for completed games)
        sport_key: Sport identifier for regulation length
        home_won: Whether home team won (for comeback factor). None if unknown.

    Returns:
        EIResult with score and metadata, or None if insufficient data
    """
    # Filter to valid in-game snapshots
    valid_snapshots = [
        s for s in snapshots
        if s.home_win_probability is not None
        and s.captured_at >= game_start
    ]

    if len(valid_snapshots) < MIN_SNAPSHOTS:
        return None

    # Aggregate into time buckets (30s with valid_until carry-forward)
    valid_snapshots = _aggregate_snapshots(valid_snapshots, bucket_seconds=30)

    if len(valid_snapshots) < MIN_SNAPSHOTS:
        return None

    # Sort by time
    valid_snapshots.sort(key=lambda s: s.captured_at)

    # Extract probability sequence
    probs = [s.home_win_probability for s in valid_snapshots]

    # =========================================================================
    # CORE: Sum of absolute probability changes
    # =========================================================================
    total_change = sum(abs(probs[i] - probs[i - 1]) for i in range(1, len(probs)))

    # =========================================================================
    # Time normalization: scale to regulation length
    # =========================================================================
    t_regulation = get_regulation_seconds(sport_key)
    t_actual = (current_time - game_start).total_seconds()

    # Guard against very short or zero durations
    if t_actual < 60:
        t_actual = t_regulation  # Fallback to regulation length

    # Cap the time normalization ratio at 2.0x to prevent games with thin
    # data coverage (e.g., 12 min of a 135-min baseball game) from getting
    # inflated scores. If we have less than half the regulation time in data,
    # assume the unseen portion was average, not extrapolated from a short window.
    time_ratio = t_regulation / t_actual
    time_ratio = min(time_ratio, 2.0)

    raw_ei = time_ratio * total_change

    # =========================================================================
    # Lead changes: count 50% crossings
    # =========================================================================
    lead_changes = 0
    for i in range(1, len(probs)):
        if (probs[i - 1] < 0.5 and probs[i] >= 0.5) or \
           (probs[i - 1] >= 0.5 and probs[i] < 0.5):
            lead_changes += 1

    # =========================================================================
    # Comeback factor: lowest probability the winning team had
    # =========================================================================
    if home_won is True:
        comeback_factor = min(probs)
    elif home_won is False:
        comeback_factor = min(1.0 - p for p in probs)
    else:
        # Unknown winner (live game) — use the currently leading team
        latest = probs[-1]
        if latest >= 0.5:
            comeback_factor = min(probs)
        else:
            comeback_factor = min(1.0 - p for p in probs)

    # =========================================================================
    # Raw score → 0-100 scale
    # =========================================================================
    # Map raw EI to 0-100 using empirical ranges (calibrated with valid_until
    # carry-forward which removes phantom oscillation from stale bookmakers):
    #   0.0 → 0, ~0.16 → 25, ~0.63 → 50, ~1.41 → 75, ~2.5 → 100
    # Using a sqrt transform for natural compression at high end:
    #   score = min(100, sqrt(raw_ei / 2.5) * 100)
    scaled = math.sqrt(min(raw_ei, 2.5) / 2.5) * 100
    final_score = max(1, min(100, round(scaled)))

    # Determine data quality
    # Thresholds for 30s buckets:
    #   good (15+) = 7.5+ minutes of data
    #   limited (5-14) = 2.5-7 minutes
    #   minimal (<5) = under 2.5 minutes
    if len(valid_snapshots) >= 15:
        data_quality = "good"
    elif len(valid_snapshots) >= 5:
        data_quality = "limited"
    else:
        data_quality = "minimal"

    metadata = EIMetadata(
        raw_ei=raw_ei,
        lead_changes=lead_changes,
        comeback_factor=comeback_factor,
        snapshot_count=len(valid_snapshots),
    )

    return EIResult(
        score=final_score,
        raw_ei=raw_ei,
        metadata=metadata,
        data_quality=data_quality,
    )


# =============================================================================
# Backward-compatible aliases for imports that reference old pulse names
# =============================================================================
PulseDataPoint = EIDataPoint
PulseResult = EIResult

def calculate_pulse(snapshots, game_start, current_time, sport_key, **kwargs):
    """Backward-compatible alias for calculate_ei."""
    # Convert PulseDataPoint to EIDataPoint if needed (same structure)
    return calculate_ei(snapshots, game_start, current_time, sport_key, **kwargs)

def get_pulse_status(score: int) -> str:
    return get_ei_status(score)

def get_pulse_label(score: int) -> str:
    return get_ei_label(score)

def get_pulse_emoji(score: int) -> str:
    return get_ei_emoji(score)
