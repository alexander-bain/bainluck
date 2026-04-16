"""
Futures outcome → Team linking utility.

Matches FuturesOutcome names to Team records using the canonical name
normalization from name_normalization.py.

Uses a conservative matching strategy (exact + suffix containment only,
no token overlap) because outcomes iterate through ALL teams and must
distinguish same-city teams like Lakers vs Clippers.
"""

import logging
from typing import Optional

from app.utils.name_normalization import normalize_name as _normalize_name  # noqa: F401 — re-exported

# Re-export for backward compatibility — canonical location is market_label_normalization
from app.utils.market_label_normalization import compute_market_tier  # noqa: F401

logger = logging.getLogger(__name__)


# =============================================================================
# Name matching for futures outcomes
# =============================================================================


def _names_match(candidate: str, team_name: str, alt_names: Optional[list] = None) -> bool:
    """Check if a candidate string (futures outcome name) matches a team.

    Uses conservative matching (exact + substring ≥8 chars) because futures
    outcomes iterate through ALL teams and need to distinguish same-city teams
    (e.g., "Los Angeles Clippers" must NOT match "LA Lakers").

    For 1:1 event matching (where both teams are known), use the more
    aggressive names_match() from name_normalization.py instead.
    """
    candidate_norm = _normalize_name(candidate)
    if not candidate_norm:
        return False

    all_names = [team_name] + (alt_names or [])

    for name in all_names:
        name_norm = _normalize_name(name)
        if not name_norm:
            continue

        # Exact match
        if candidate_norm == name_norm:
            return True

        # Substring match (only if both strings are long enough to avoid
        # false positives like "LA" matching everything)
        if len(candidate_norm) >= 8 and len(name_norm) >= 8:
            if candidate_norm in name_norm or name_norm in candidate_norm:
                return True

    return False


def match_outcome_to_team(
    outcome_name: str,
    teams: list[dict],
) -> Optional[int]:
    """
    Match a futures outcome name to a team record.

    Args:
        outcome_name: The outcome name (e.g., "Boston Celtics", "Los Angeles Lakers")
        teams: List of team dicts with keys: id, name, alternate_names

    Returns:
        team_id if matched, None otherwise
    """
    if not outcome_name or outcome_name.lower() in ("yes", "no", "over", "under"):
        return None

    for team in teams:
        if _names_match(outcome_name, team["name"], team.get("alternate_names")):
            return team["id"]

    return None


def _strip_diacritics(s: str) -> str:
    """Remove diacritics/accents for fuzzy name matching.

    'Luka Dončić' → 'Luka Doncic', 'José Ramírez' → 'Jose Ramirez'
    """
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def match_outcome_to_roster(
    outcome_name: str,
    team_rosters: dict[int, list[str]],
) -> Optional[int]:
    """
    Match a futures outcome name to a team via roster player names.

    Args:
        outcome_name: e.g., "Jaylen Brown" or "Aaron Judge Over 2.5 Hits"
        team_rosters: {team_id: ["Jayson Tatum", "Jaylen Brown", ...]}

    Returns:
        team_id if matched, None otherwise
    """
    if not outcome_name or len(outcome_name) < 4:
        return None

    # Skip generic outcomes
    name_lower = _strip_diacritics(outcome_name.lower().strip())
    if name_lower in ("yes", "no", "over", "under", "draw", "tie"):
        return None

    for team_id, players in team_rosters.items():
        for player in players:
            player_lower = _strip_diacritics(player.lower())
            # Require the full player name (first + last) to appear in the outcome.
            # Do NOT match if only a first or last name matches — too many collisions
            # (e.g., "Austin Eckroat" should not match "Austin FC").
            # Only match if the player name has 2+ words (skip single-word names
            # to avoid "Santos" matching random things).
            if " " not in player_lower:
                continue
            if player_lower in name_lower:
                return team_id

    return None


# =============================================================================
# Sport category → sport key mapping (for scoping team search)
# =============================================================================

from app.utils.sport_keys import (  # noqa: E402
    LLM_CATEGORY_TO_SPORT_KEYS as SPORT_CATEGORY_TO_KEYS,  # noqa: F401 — re-exported
    get_sport_keys_for_category,  # noqa: F401 — re-exported
)


# =============================================================================
# Relevance scoring for related futures
# =============================================================================

# Tier score: lower tier = more relevant (championship is most important context)
_TIER_SCORES = {1: 1.0, 2: 0.7, 3: 0.5, 4: 0.3, 5: 0.1}

# Round-number thresholds that create narrative moments
_THRESHOLD_BOUNDARIES = [0.10, 0.20, 0.25, 0.33, 0.50, 0.67, 0.75, 0.80, 0.90]


def compute_relevance_score(
    market_tier: Optional[int],
    probability: Optional[float],
    probability_change_24h: Optional[float],
    days_to_resolution: Optional[float],
    bookmaker_count: int = 1,
) -> tuple[float, str]:
    """
    Compute a relevance score (0-100) for a related future.

    Returns (score, reason) where reason is a human-readable label
    explaining why this future is relevant.

    Weights:
        - tier_score:      25% — championship > conference > awards > division > props
        - movement_score:  30% — is this future reacting to current events?
        - probability_score: 15% — does the team/player have a real shot?
        - threshold_score: 15% — is the outcome near a significant boundary?
        - urgency_score:   10% — how soon does this resolve?
        - liquidity_score:  5% — how many sources contribute odds?
    """
    # Tier score (0-1)
    tier = market_tier or 5
    tier_s = _TIER_SCORES.get(tier, 0.1)

    # Movement score (0-1): absolute 24h change, capped at 5%
    change = abs(float(probability_change_24h or 0))
    movement_s = min(change / 0.05, 1.0)

    # Probability score (0-1): higher probability = more interesting
    # But very low probs (< 1%) are noise, and near-certainties (> 95%) are boring
    prob = float(probability or 0)
    if prob < 0.01:
        prob_s = 0.0
    elif prob > 0.95:
        prob_s = 0.3  # Still somewhat interesting but not exciting
    else:
        # Peak relevance around 0.3-0.5 range
        prob_s = min(prob / 0.3, 1.0) if prob <= 0.3 else 1.0

    # Threshold proximity score (0-1): near a round-number boundary
    threshold_s = 0.0
    if prob > 0:
        min_distance = min(abs(prob - b) for b in _THRESHOLD_BOUNDARIES)
        # Full score if within 2%, zero if > 5% away
        if min_distance < 0.05:
            threshold_s = 1.0 - (min_distance / 0.05)

    # Urgency score (0-1): resolves sooner = more relevant
    if days_to_resolution is not None and days_to_resolution > 0:
        urgency_s = max(0, 1.0 - (days_to_resolution / 180))  # 6 months = 0
    else:
        urgency_s = 0.3  # Unknown resolution = moderate

    # Liquidity score (0-1): more bookmakers = more reliable
    liquidity_s = min(bookmaker_count / 8, 1.0)

    # Weighted sum
    score = (
        0.25 * tier_s
        + 0.30 * movement_s
        + 0.15 * prob_s
        + 0.15 * threshold_s
        + 0.10 * urgency_s
        + 0.05 * liquidity_s
    ) * 100

    # Determine reason label
    reason = _determine_reason(tier, change, prob, threshold_s, days_to_resolution)

    return round(score, 1), reason


def _determine_reason(
    tier: int,
    change: float,
    prob: float,
    threshold_score: float,
    days_to_resolution: Optional[float],
) -> str:
    """Pick the most relevant reason label for why this future matters."""
    # Moving futures are the most interesting
    if change >= 0.02:
        return "moving today"
    if change >= 0.005:
        return "shifting"

    # Near a threshold boundary
    if threshold_score > 0.6 and prob > 0.05:
        if prob > 0.45 and prob < 0.55:
            return "near 50/50"
        return "near threshold"

    # Resolving soon
    if days_to_resolution is not None and days_to_resolution < 14:
        return "resolves soon"

    # Fall back to tier-based label
    tier_labels = {
        1: "championship context",
        2: "conference context",
        3: "award watch",
        4: "division context",
        5: "related market",
    }
    return tier_labels.get(tier, "related market")
