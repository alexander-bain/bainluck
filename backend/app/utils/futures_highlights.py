"""
Futures market highlight scoring and classification.

Parallel to highlights.py (game events), this scores futures markets
on interestingness (0-100) for the unified feed.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


# Market tier weights (lower tier number = more important)
MARKET_TIER_WEIGHTS = {
    1: 15,  # Championship
    2: 10,  # Conference
    3: 8,   # Awards (MVP, etc.)
    4: 5,   # Division
    5: 2,   # Props/other
}

# Sport/league tier for futures (mirrors LEAGUE_TIERS in highlights.py)
FUTURES_LEAGUE_TIERS: dict[str, int] = {
    "basketball": 1,
    "football": 1,
    "baseball": 1,
    "hockey": 1,
    "soccer": 2,
    "golf": 2,
    "tennis": 2,
    "mma": 2,
    "politics": 1,  # High general interest
    "entertainment": 2,
}

# Scoring weights
FUTURES_WEIGHTS = {
    "major_movement_24h": 25,       # Leader moved >5% in 24h
    "moderate_movement_24h": 15,    # Leader moved 2-5% in 24h
    "leader_change": 30,            # #1 ranking changed
    "rank_shakeup": 15,             # Multiple rank changes in top 5
    "high_tier_market": 15,         # Championship/conference
    "major_league": 10,             # Major sport/league
    "secondary_league": 5,          # Secondary sport
    "resolving_soon_7d": 15,        # Resolves within 7 days
    "resolving_soon_30d": 8,        # Resolves within 30 days
    "multi_source": 10,             # Available from 2+ sources
    "source_divergence": 20,        # Sources disagree by >5%
}

# Thresholds
MAJOR_MOVEMENT_THRESHOLD = 0.05    # 5% change in 24h
MODERATE_MOVEMENT_THRESHOLD = 0.02 # 2% change
SOURCE_DIVERGENCE_THRESHOLD = 0.05 # 5% disagreement between sources


@dataclass
class FuturesFlags:
    """Boolean flags describing futures market characteristics."""
    has_major_movement: bool = False
    has_moderate_movement: bool = False
    leader_changed: bool = False
    has_rank_shakeup: bool = False
    is_high_tier: bool = False
    is_resolving_soon: bool = False
    has_multi_source: bool = False
    has_source_divergence: bool = False
    league_tier: int = 3
    market_tier: int = 5


@dataclass
class FuturesHighlightResult:
    """Complete highlight analysis for a futures market."""
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    flags: FuturesFlags = field(default_factory=FuturesFlags)
    primary_reason: Optional[str] = None
    top_mover_name: Optional[str] = None
    top_mover_change: Optional[float] = None


def compute_futures_highlight(
    # Market metadata
    market_tier: Optional[int] = None,
    sport_category: Optional[str] = None,
    resolution_date: Optional[datetime] = None,
    # Outcome movement data
    outcomes: Optional[list[dict]] = None,
    # Cross-source data
    source_count: int = 1,
    max_source_divergence: Optional[float] = None,
    # Timing
    now: Optional[datetime] = None,
) -> FuturesHighlightResult:
    """
    Compute highlight score and flags for a futures market.

    Args:
        market_tier: 1=championship, 2=conference, 3=awards, 4=division, 5=props
        sport_category: LLM-assigned category (basketball, football, politics, etc.)
        resolution_date: When the market resolves
        outcomes: List of dicts with keys: name, probability, probability_change_24h,
                  rank, rank_change_24h, opening_probability
        source_count: Number of sources covering this market
        max_source_divergence: Max probability difference across sources for any outcome
        now: Current time (defaults to UTC now)

    Returns:
        FuturesHighlightResult with score, reasons, flags, and primary display reason.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    result = FuturesHighlightResult()
    flags = result.flags
    outcomes = outcomes or []

    # === Market tier scoring ===
    tier = market_tier or 5
    flags.market_tier = tier
    tier_weight = MARKET_TIER_WEIGHTS.get(tier, 2)
    if tier <= 2:
        flags.is_high_tier = True
    result.score += tier_weight
    result.reasons.append(f"tier_{tier}")

    # === League/sport scoring ===
    if sport_category:
        sport_lower = sport_category.lower()
        league_tier = FUTURES_LEAGUE_TIERS.get(sport_lower, 3)
        flags.league_tier = league_tier
        if league_tier == 1:
            result.score += FUTURES_WEIGHTS["major_league"]
            result.reasons.append("major_league")
        elif league_tier == 2:
            result.score += FUTURES_WEIGHTS["secondary_league"]
            result.reasons.append("secondary_league")

    # === Outcome movement analysis ===
    if outcomes:
        # Find the biggest 24h mover
        biggest_change = 0.0
        biggest_mover_name = None

        rank_changes_in_top5 = 0
        current_leader = None
        leader_was_different = False

        for o in outcomes:
            change_24h = abs(float(o.get("probability_change_24h") or 0))
            rank = o.get("rank")
            rank_change = o.get("rank_change_24h")
            opening_prob = o.get("opening_probability")
            current_prob = o.get("probability")

            # Track biggest mover
            if change_24h > biggest_change:
                biggest_change = change_24h
                biggest_mover_name = o.get("name")

            # Track rank changes in top 5
            if rank is not None and rank <= 5 and rank_change and rank_change != 0:
                rank_changes_in_top5 += 1

            # Track leader change
            if rank == 1:
                current_leader = o.get("name")
                if rank_change and rank_change != 0:
                    leader_was_different = True

        # Major movement scoring
        if biggest_change >= MAJOR_MOVEMENT_THRESHOLD:
            flags.has_major_movement = True
            result.score += FUTURES_WEIGHTS["major_movement_24h"]
            result.reasons.append("major_movement_24h")
            result.top_mover_name = biggest_mover_name
            result.top_mover_change = biggest_change
        elif biggest_change >= MODERATE_MOVEMENT_THRESHOLD:
            flags.has_moderate_movement = True
            result.score += FUTURES_WEIGHTS["moderate_movement_24h"]
            result.reasons.append("moderate_movement_24h")
            result.top_mover_name = biggest_mover_name
            result.top_mover_change = biggest_change

        # Leader change scoring
        if leader_was_different:
            flags.leader_changed = True
            result.score += FUTURES_WEIGHTS["leader_change"]
            result.reasons.append("leader_change")

        # Rank shakeup (multiple top-5 rank changes)
        if rank_changes_in_top5 >= 2:
            flags.has_rank_shakeup = True
            result.score += FUTURES_WEIGHTS["rank_shakeup"]
            result.reasons.append("rank_shakeup")

    # === Resolution proximity ===
    if resolution_date is not None:
        if resolution_date.tzinfo is None:
            resolution_date = resolution_date.replace(tzinfo=timezone.utc)
        days_until = (resolution_date - now).days
        if 0 < days_until <= 7:
            flags.is_resolving_soon = True
            result.score += FUTURES_WEIGHTS["resolving_soon_7d"]
            result.reasons.append("resolving_soon_7d")
        elif 0 < days_until <= 30:
            flags.is_resolving_soon = True
            result.score += FUTURES_WEIGHTS["resolving_soon_30d"]
            result.reasons.append("resolving_soon_30d")

    # === Cross-source scoring ===
    if source_count >= 2:
        flags.has_multi_source = True
        result.score += FUTURES_WEIGHTS["multi_source"]
        result.reasons.append("multi_source")

    if max_source_divergence is not None and max_source_divergence >= SOURCE_DIVERGENCE_THRESHOLD:
        flags.has_source_divergence = True
        result.score += FUTURES_WEIGHTS["source_divergence"]
        result.reasons.append("source_divergence")

    # === Cap score at 100 ===
    result.score = min(100, result.score)

    # === Determine primary reason for display ===
    priority_order = [
        ("leader_change", "New favorite"),
        ("source_divergence", "Sources disagree"),
        ("major_movement_24h", "Big odds movement"),
        ("rank_shakeup", "Rankings shakeup"),
        ("moderate_movement_24h", "Odds moving"),
        ("resolving_soon_7d", "Resolving soon"),
        ("resolving_soon_30d", "Resolving this month"),
        ("multi_source", "Multi-source"),
    ]

    for reason_code, display_text in priority_order:
        if reason_code in result.reasons:
            result.primary_reason = display_text
            break

    return result


def should_highlight_futures(result: FuturesHighlightResult, min_score: int = 25) -> bool:
    """Determine if a futures market should appear in the feed."""
    # Always highlight leader changes and source divergence
    if result.flags.leader_changed:
        return True
    if result.flags.has_source_divergence:
        return True
    # Always highlight major movements in high-tier markets
    if result.flags.has_major_movement and result.flags.is_high_tier:
        return True
    # Otherwise, use score threshold
    return result.score >= min_score
