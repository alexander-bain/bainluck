"""
Futures outcome → Team linking utility.

Matches FuturesOutcome names to Team records using:
1. Exact name match (case-insensitive)
2. Substring match against Team.name + Team.alternate_names
3. LLM player-team classification (for player names like "Jaylen Brown")

Also assigns market_tier values to FuturesMarket records.
"""

import logging
import re
import unicodedata
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Market tier assignment
# =============================================================================

# Tier 1: Championship / title winner
_TIER_1_PATTERNS = [
    re.compile(r"\b(championship|champion|super.bowl|world.series|stanley.cup|nba.finals|title)\b", re.I),
    re.compile(r"\bwinner\b", re.I),  # Catch-all for "X Winner" markets
]

# Tier 2: Conference winner
_TIER_2_PATTERNS = [
    re.compile(r"\b(conference|eastern|western|afc|nfc|american.league|national.league)\b", re.I),
]

# Tier 3: Awards / MVP / individual honors
_TIER_3_PATTERNS = [
    re.compile(r"\b(mvp|rookie|defensive.player|sixth.man|most.improved|cy.young|heisman)\b", re.I),
    re.compile(r"\b(hart.trophy|vezina|calder|norris.trophy|selke|conn.smythe|ballon.d.or)\b", re.I),
    re.compile(r"\b(award|trophy|player.of.the.year|golden.boot|golden.glove)\b", re.I),
]

# Tier 4: Division winner
_TIER_4_PATTERNS = [
    re.compile(r"\b(division|atlantic|pacific|central|southeast|northwest|southwest)\b", re.I),
    re.compile(r"\b(al.east|al.west|al.central|nl.east|nl.west|nl.central)\b", re.I),
    re.compile(r"\b(afc.east|afc.west|afc.north|afc.south|nfc.east|nfc.west|nfc.north|nfc.south)\b", re.I),
    re.compile(r"\b(metropolitan|atlantic.division|pacific.division|central.division)\b", re.I),
]


_NON_SPORT_CATEGORIES = {
    "politics", "crypto", "economics", "entertainment", "tech",
    "weather", "geopolitics", "culture",
}


def compute_market_tier(market_name: str, category: Optional[str] = None,
                        sport_category: Optional[str] = None) -> int:
    """
    Assign a tier (1-5) to a futures market based on its name and category.

    Tiers:
        1 = Championship / title winner (highest relevance)
        2 = Conference winner / non-sports top-level
        3 = Awards / MVP / individual honors
        4 = Division winner
        5 = Props / other (lowest relevance)

    Non-sports markets (politics, crypto, entertainment, etc.) default to
    tier 2 since they have no championship/conference hierarchy — they're
    all top-level questions that should rank alongside major sports futures.

    Returns:
        Integer 1-5
    """
    name_lower = (market_name or "").lower()
    cat_lower = (category or "").lower()

    # Check category field first for quick classification
    if cat_lower == "mvp":
        return 3

    # Division check before championship — "Division Winner" contains "winner"
    # but should be tier 4, not tier 1
    for pattern in _TIER_4_PATTERNS:
        if pattern.search(name_lower):
            return 4

    # Conference check before championship — "Conference Winner" also contains "winner"
    for pattern in _TIER_2_PATTERNS:
        if pattern.search(name_lower):
            return 2

    # Awards check before championship — "MVP Award" also might match "winner"
    for pattern in _TIER_3_PATTERNS:
        if pattern.search(name_lower):
            return 3

    # Championship / title
    if cat_lower == "championship":
        return 1
    for pattern in _TIER_1_PATTERNS:
        if pattern.search(name_lower):
            return 1

    # Non-sports markets default to tier 2 (no hierarchy — all top-level)
    effective_category = (sport_category or category or "").lower()
    if effective_category in _NON_SPORT_CATEGORIES:
        return 2

    return 5


# =============================================================================
# Name normalization (shared with ESPN sync)
# =============================================================================

def _normalize_name(name: str) -> str:
    """Normalize a name for matching: strip accents, lowercase, unify quotes."""
    normalized = unicodedata.normalize("NFD", name)
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    for ch in ("\u2018", "\u2019", "\u02BB", "\u02BC", "\u0060", "\u00B4", "\u2032"):
        normalized = normalized.replace(ch, "'")
    return normalized.lower().strip()


def _names_match(candidate: str, team_name: str, alt_names: Optional[list] = None) -> bool:
    """
    Check if a candidate string (futures outcome name) matches a team.

    Uses full-string matching to avoid false positives (e.g., "Los Angeles"
    matching both Lakers and Clippers). Only does substring matching when
    the candidate is long enough (>= 8 chars) to avoid city-only matches.

    Args:
        candidate: The outcome name to match (e.g., "Boston Celtics")
        team_name: The team's canonical name (e.g., "Boston Celtics")
        alt_names: List of alternate names (e.g., ["Celtics", "Boston"])
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


# =============================================================================
# Sport category → sport key mapping (for scoping team search)
# =============================================================================

# Maps llm_sport_category / categorization result to sport keys in the sports table
SPORT_CATEGORY_TO_KEYS = {
    "basketball": ["basketball_nba", "basketball_wnba", "basketball_ncaab", "basketball_wncaab"],
    "football": ["americanfootball_nfl", "americanfootball_ncaaf"],
    "baseball": ["baseball_mlb"],
    "hockey": ["icehockey_nhl"],
    "soccer": [
        "soccer_epl", "soccer_usa_mls", "soccer_spain_la_liga",
        "soccer_germany_bundesliga", "soccer_italy_serie_a",
        "soccer_france_ligue_one", "soccer_uefa_champs_league",
    ],
    "golf": ["golf_pga"],
    "tennis": ["tennis_atp", "tennis_wta"],
    "mma": ["mma_mixed_martial_arts"],
}


def get_sport_keys_for_category(category: Optional[str]) -> Optional[list[str]]:
    """
    Get sport keys to scope team search for a given sport category.

    Returns None if category is unknown (search all teams).
    """
    if not category:
        return None
    return SPORT_CATEGORY_TO_KEYS.get(category.lower())


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
