"""Personalization scoring for the unified feed.

Computes a multiplier (typically 0.5x–2.0x) applied to each feed item's
base interestingness score based on the user's preferences, favorite teams,
sport affinities, and team relationships (follow, local, alma_mater, rival).

Design principles:
- Anonymous users always get 1.0x (no change to base score)
- Users without onboarding completed still benefit from any favorites they've set
- Multiplier is computed on-the-fly, not stored in DB
- Rival bonus applies when the rival is *losing*, adding schadenfreude
- Sport affinities scale smoothly: high affinity boosts, low suppresses
- Stacking is capped to prevent extreme scores

Multiplier sources (applied additively, then clamped):
  base: 1.0
  + team_in_event: up to +0.5  (favorite team is playing)
  + rival_losing:  up to +0.5  (rival team is losing)
  + local_team:    up to +0.3  (team from user's home market)
  + alma_mater:    up to +0.3  (user's college team)
  + sport_affinity: -0.5 to +0.2  (based on sport_affinities dict)
  + pinned_item:   +0.3  (user explicitly pinned this)
  = clamped to [0.3, 2.0]
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# --- Constants ---

# Team relationship multiplier bonuses
FOLLOW_BONUS = 0.5       # User explicitly follows this team
LOCAL_BONUS = 0.3         # Team is from user's home market
ALMA_MATER_BONUS = 0.3   # User's college/university team
RIVAL_LOSING_BONUS = 0.5 # Rival is currently losing (schadenfreude)
RIVAL_PLAYING_BONUS = 0.2  # Rival is playing (interest even if not losing)
PINNED_BONUS = 0.3        # User has this item pinned

# Sport affinity thresholds
HIGH_AFFINITY_THRESHOLD = 0.5   # sport_affinities value above this = boost
LOW_AFFINITY_THRESHOLD = 0.2    # below this = suppress
HIGH_AFFINITY_BONUS = 0.2       # boost for high-affinity sports
LOW_AFFINITY_PENALTY = -0.5     # penalty for low-affinity sports

# Clamp range
MIN_MULTIPLIER = 0.3
MAX_MULTIPLIER = 2.0


@dataclass
class PersonalizationContext:
    """Pre-loaded user personalization data for efficient feed scoring.

    Load once per feed request, then pass to compute_multiplier for each item.
    """
    # team_id → set of relation_types (e.g., {1: {"follow", "local"}, 5: {"rival"}})
    team_relations: dict[int, set[str]] = field(default_factory=dict)
    # team_id → weight from UserFavorite (default 1.0)
    team_weights: dict[int, float] = field(default_factory=dict)
    # sport_key → affinity score (0.0-1.0), e.g., {"basketball_nba": 1.0}
    sport_affinities: dict[str, float] = field(default_factory=dict)
    # Set of pinned event IDs
    pinned_event_ids: set[int] = field(default_factory=set)
    # Set of pinned futures market IDs
    pinned_futures_ids: set[int] = field(default_factory=set)
    # Whether this is a real user context (vs anonymous)
    is_authenticated: bool = False


@dataclass
class PersonalizationResult:
    """Result of personalization scoring for a single feed item."""
    multiplier: float = 1.0
    reasons: list[str] = field(default_factory=list)
    is_personalized: bool = False


def compute_event_multiplier(
    ctx: PersonalizationContext,
    home_team_id: Optional[int],
    away_team_id: Optional[int],
    sport_key: Optional[str],
    event_id: Optional[int] = None,
    home_score: Optional[int] = None,
    away_score: Optional[int] = None,
) -> PersonalizationResult:
    """Compute personalization multiplier for a game event.

    Args:
        ctx: Pre-loaded user context
        home_team_id: Home team DB ID (from events.home_team_id)
        away_team_id: Away team DB ID (from events.away_team_id)
        sport_key: Sport key (e.g., "basketball_nba")
        event_id: Event ID for pin checking
        home_score: Current home score (for rival schadenfreude)
        away_score: Current away score (for rival schadenfreude)

    Returns:
        PersonalizationResult with multiplier and explanation reasons
    """
    if not ctx.is_authenticated:
        return PersonalizationResult()

    bonus = 0.0
    reasons = []

    team_ids = [tid for tid in [home_team_id, away_team_id] if tid is not None]

    # --- Team relationship bonuses ---
    for team_id in team_ids:
        relations = ctx.team_relations.get(team_id, set())
        weight = ctx.team_weights.get(team_id, 1.0)

        if "follow" in relations:
            team_bonus = FOLLOW_BONUS * weight
            bonus += team_bonus
            reasons.append(f"your_team:{team_bonus:.2f}")

        if "local" in relations:
            bonus += LOCAL_BONUS * weight
            reasons.append(f"local_team:{LOCAL_BONUS * weight:.2f}")

        if "alma_mater" in relations:
            bonus += ALMA_MATER_BONUS * weight
            reasons.append(f"alma_mater:{ALMA_MATER_BONUS * weight:.2f}")

        if "rival" in relations:
            # Check if the rival is losing (schadenfreude boost)
            rival_is_losing = False
            if home_score is not None and away_score is not None:
                if team_id == home_team_id and home_score < away_score:
                    rival_is_losing = True
                elif team_id == away_team_id and away_score < home_score:
                    rival_is_losing = True

            if rival_is_losing:
                bonus += RIVAL_LOSING_BONUS
                reasons.append(f"rival_losing:{RIVAL_LOSING_BONUS:.2f}")
            else:
                bonus += RIVAL_PLAYING_BONUS
                reasons.append(f"rival_playing:{RIVAL_PLAYING_BONUS:.2f}")

    # --- Sport affinity ---
    if sport_key and ctx.sport_affinities:
        affinity = ctx.sport_affinities.get(sport_key)
        if affinity is not None:
            if affinity >= HIGH_AFFINITY_THRESHOLD:
                bonus += HIGH_AFFINITY_BONUS
                reasons.append(f"sport_boost:{HIGH_AFFINITY_BONUS:.2f}")
            elif affinity < LOW_AFFINITY_THRESHOLD:
                bonus += LOW_AFFINITY_PENALTY
                reasons.append(f"sport_suppress:{LOW_AFFINITY_PENALTY:.2f}")

    # --- Pinned item bonus ---
    if event_id and event_id in ctx.pinned_event_ids:
        bonus += PINNED_BONUS
        reasons.append(f"pinned:{PINNED_BONUS:.2f}")

    # --- Clamp and return ---
    multiplier = max(MIN_MULTIPLIER, min(MAX_MULTIPLIER, 1.0 + bonus))

    return PersonalizationResult(
        multiplier=multiplier,
        reasons=reasons,
        is_personalized=bool(reasons),
    )


def compute_futures_multiplier(
    ctx: PersonalizationContext,
    sport_category: Optional[str],
    outcome_team_ids: list[int],
    futures_market_id: Optional[int] = None,
) -> PersonalizationResult:
    """Compute personalization multiplier for a futures market.

    Futures personalization is simpler than events:
    - Check if any outcome team is a user favorite
    - Check sport affinity
    - Check if pinned

    Args:
        ctx: Pre-loaded user context
        sport_category: LLM sport category (e.g., "basketball")
        outcome_team_ids: List of team_ids from FuturesOutcome records
        futures_market_id: Market ID for pin checking

    Returns:
        PersonalizationResult with multiplier and explanation reasons
    """
    if not ctx.is_authenticated:
        return PersonalizationResult()

    bonus = 0.0
    reasons = []

    # --- Check if any outcome team is a user favorite ---
    matched_follow = False
    matched_rival = False
    for team_id in outcome_team_ids:
        if team_id is None:
            continue
        relations = ctx.team_relations.get(team_id, set())
        weight = ctx.team_weights.get(team_id, 1.0)

        if "follow" in relations and not matched_follow:
            bonus += FOLLOW_BONUS * weight
            reasons.append(f"your_team_futures:{FOLLOW_BONUS * weight:.2f}")
            matched_follow = True

        if "rival" in relations and not matched_rival:
            bonus += RIVAL_PLAYING_BONUS
            reasons.append(f"rival_futures:{RIVAL_PLAYING_BONUS:.2f}")
            matched_rival = True

        if "alma_mater" in relations:
            bonus += ALMA_MATER_BONUS * weight
            reasons.append(f"alma_mater_futures:{ALMA_MATER_BONUS * weight:.2f}")

    # --- Sport affinity (use category → sport_key mapping) ---
    if sport_category and ctx.sport_affinities:
        # Try matching sport_category against known sport_key prefixes
        matched_affinity = _match_sport_affinity(sport_category, ctx.sport_affinities)
        if matched_affinity is not None:
            if matched_affinity >= HIGH_AFFINITY_THRESHOLD:
                bonus += HIGH_AFFINITY_BONUS
                reasons.append(f"sport_boost:{HIGH_AFFINITY_BONUS:.2f}")
            elif matched_affinity < LOW_AFFINITY_THRESHOLD:
                bonus += LOW_AFFINITY_PENALTY
                reasons.append(f"sport_suppress:{LOW_AFFINITY_PENALTY:.2f}")

    # --- Pinned item bonus ---
    if futures_market_id and futures_market_id in ctx.pinned_futures_ids:
        bonus += PINNED_BONUS
        reasons.append(f"pinned:{PINNED_BONUS:.2f}")

    # --- Clamp and return ---
    multiplier = max(MIN_MULTIPLIER, min(MAX_MULTIPLIER, 1.0 + bonus))

    return PersonalizationResult(
        multiplier=multiplier,
        reasons=reasons,
        is_personalized=bool(reasons),
    )


def _match_sport_affinity(
    category: str,
    sport_affinities: dict[str, float],
) -> Optional[float]:
    """Match a futures sport category to the user's sport affinities.

    Futures use categories like "basketball", "football", "hockey"
    while sport_affinities use full keys like "basketball_nba",
    "americanfootball_nfl", etc.

    Returns the best-matching affinity value, or None.
    """
    if not category or not sport_affinities:
        return None

    category_lower = category.lower()

    # Direct match on category name within sport keys
    best_match = None
    for sport_key, affinity in sport_affinities.items():
        key_lower = sport_key.lower()

        # Check if category is a substring of the sport key
        # e.g., "basketball" in "basketball_nba"
        if category_lower in key_lower:
            if best_match is None or affinity > best_match:
                best_match = affinity

        # Handle special mappings
        # "football" could match "americanfootball_nfl" or "americanfootball_ncaaf"
        if category_lower == "football" and "football" in key_lower:
            if best_match is None or affinity > best_match:
                best_match = affinity

        # "hockey" matches "icehockey_nhl"
        if category_lower == "hockey" and "hockey" in key_lower:
            if best_match is None or affinity > best_match:
                best_match = affinity

        # "soccer" matches "soccer_epl", "soccer_usa_mls", etc.
        if category_lower == "soccer" and "soccer" in key_lower:
            if best_match is None or affinity > best_match:
                best_match = affinity

        # "mma" matches "mma_mixed_martial_arts"
        if category_lower == "mma" and "mma" in key_lower:
            if best_match is None or affinity > best_match:
                best_match = affinity

    return best_match
