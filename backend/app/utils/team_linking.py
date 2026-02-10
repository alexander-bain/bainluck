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


def compute_market_tier(market_name: str, category: Optional[str] = None) -> int:
    """
    Assign a tier (1-5) to a futures market based on its name and category.

    Tiers:
        1 = Championship / title winner (highest relevance)
        2 = Conference winner
        3 = Awards / MVP / individual honors
        4 = Division winner
        5 = Props / other (lowest relevance)

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
