"""
Market type classification for futures markets.

Classifies futures markets into structural types (championship, award, game,
stat_prop, etc.) based on market name pattern matching. This is orthogonal to
sport categorization (what sport) — market_type answers "what kind of market."

The frontend has equivalent logic in RelatedFutures.tsx (effectiveTier,
STAT_PROP_PATTERNS, GAME_MARKET_PATTERNS, AWARD_PATTERNS, etc.). This module
is the backend single source of truth; the frontend patterns should converge
toward using this via the API's market_type field.
"""

import re
from enum import Enum
from typing import Optional


class MarketType(str, Enum):
    """
    Structural type of a futures market.

    Ordered roughly by display priority (championship > conference > award >
    division > game > stat_prop > other).
    """
    championship = "championship"
    conference = "conference"
    award = "award"
    division = "division"
    game = "game"
    stat_prop = "stat_prop"
    other = "other"


# =============================================================================
# Stat prop detection
# =============================================================================

# Pattern: "Team at Team: Stat" — Kalshi game stat prop format
_STAT_PROP_RE = re.compile(
    r":\s*(?:points|assists|rebounds|steals|blocks|three\s*pointers?|"
    r"3[-\s]?pointers?|turnovers|strikeouts|hits|runs|home\s*runs|goals|"
    r"saves|sacks|passing\s*yards|rushing\s*yards|receiving\s*yards|"
    r"touchdowns|completions|interceptions|aces|double\s*faults|kills|"
    r"double\s*doubles?|triple\s*doubles?)",
    re.IGNORECASE,
)


def is_stat_prop(name: str) -> bool:
    """Check if a market name looks like a player/team stat prop."""
    return bool(_STAT_PROP_RE.search(name))


# =============================================================================
# Game-level market detection
# =============================================================================

_GAME_MARKET_PATTERNS = [
    re.compile(r"\bvs\.?\s", re.IGNORECASE),              # "Team A vs. Team B"
    re.compile(r"\s–\s"),                                   # "Team A – Team B" (en-dash)
    re.compile(r"more\s+markets$", re.IGNORECASE),          # "... - More Markets"
    re.compile(r"moneyline$", re.IGNORECASE),               # "Game X Moneyline"
    re.compile(r"\bgame\s+\d", re.IGNORECASE),              # "Game 1", "Game 7"
    re.compile(                                              # "Stanford at Miami"
        r"^\w[\w\s.'()-]+\bat\b\s+\w[\w\s.'()-]+$",
        re.IGNORECASE,
    ),
]


def is_game_market(name: str) -> bool:
    """Check if a market name looks like a game-level market (moneyline, matchup)."""
    return any(p.search(name) for p in _GAME_MARKET_PATTERNS)


# =============================================================================
# Award market detection
# =============================================================================

_AWARD_PATTERNS = [
    re.compile(r"\bmvp\b", re.IGNORECASE),
    re.compile(r"\bgolden\s+boot\b", re.IGNORECASE),
    re.compile(r"\bgold(?:en)?\s+glove\b", re.IGNORECASE),
    re.compile(r"\bcy\s*young\b", re.IGNORECASE),
    re.compile(r"\bnewcomer\b|\brookie\b", re.IGNORECASE),
    re.compile(r"player\s+of\s+(?:the\s+)?year", re.IGNORECASE),
    re.compile(r"\bballon\b", re.IGNORECASE),
    re.compile(r"\bbest\s+(?:actor|actress|picture|director|supporting)\b", re.IGNORECASE),
    re.compile(r"\bleader\b", re.IGNORECASE),
    re.compile(r"\bper\s+game\b", re.IGNORECASE),
    re.compile(r"\bclutch\b", re.IGNORECASE),
    re.compile(r"\bfinals\s+mvp\b", re.IGNORECASE),
    re.compile(r"\b[ew]cf\s+mvp\b", re.IGNORECASE),
    re.compile(r"\bmost\s+improved\b", re.IGNORECASE),
    re.compile(r"\bsixth\s+man\b", re.IGNORECASE),
    re.compile(r"\b6th\s+man\b", re.IGNORECASE),
    re.compile(r"\ball[- ]?star\s+mvp\b", re.IGNORECASE),
    re.compile(r"\bscoring\s+(?:leader|title|champion)", re.IGNORECASE),
    re.compile(r"\bhome\s+run\s+(?:leader|king)", re.IGNORECASE),
    re.compile(r"\bcover\s+of\b", re.IGNORECASE),
    re.compile(r"\b2k\b", re.IGNORECASE),
    re.compile(r"\bnba2k\b", re.IGNORECASE),
    # Hockey trophies
    re.compile(r"\b(?:hart|vezina|calder|conn\s+smythe|norris|selke|lady\s+byng|rocket\s+richard)\s*(?:trophy|award)?\b", re.IGNORECASE),
    # Heisman
    re.compile(r"\bheisman\b", re.IGNORECASE),
]


def is_award(name: str) -> bool:
    """Check if a market name looks like a player/team award market."""
    return any(p.search(name) for p in _AWARD_PATTERNS)


# =============================================================================
# NOT-championship detection (markets that look like championship but aren't)
# =============================================================================

_NOT_CHAMPIONSHIP_PATTERNS = [
    re.compile(r"\bwin\s+total", re.IGNORECASE),
    re.compile(r"\bover/under\b", re.IGNORECASE),
    re.compile(r"\bregular\s+season\s+wins", re.IGNORECASE),
    re.compile(r"\bcover\s+of\b", re.IGNORECASE),
    re.compile(r"\b2k\b", re.IGNORECASE),
    re.compile(r"\bplayoff\s+appearance", re.IGNORECASE),
    re.compile(r"\bmake\s+playoffs", re.IGNORECASE),
    re.compile(r"\bplayoff\s*berth", re.IGNORECASE),
    re.compile(r"\bto\s+make\b", re.IGNORECASE),
    re.compile(r"\bseeding\b", re.IGNORECASE),
    re.compile(r"\bseed\b", re.IGNORECASE),
    re.compile(r"\bover\s+\d", re.IGNORECASE),
    re.compile(r"\bunder\s+\d", re.IGNORECASE),
    re.compile(r"\bexact\s+wins", re.IGNORECASE),
]


def is_not_championship(name: str) -> bool:
    """Check if a market should NOT be treated as championship despite backend tier."""
    return any(p.search(name) for p in _NOT_CHAMPIONSHIP_PATTERNS)


# =============================================================================
# Championship / conference / division detection
# =============================================================================

_CHAMPIONSHIP_PATTERNS = [
    re.compile(r"\bchampionship\b", re.IGNORECASE),
    re.compile(r"\bchampion\b", re.IGNORECASE),
    re.compile(r"\bwinner\b", re.IGNORECASE),
    re.compile(r"\bsuper\s+bowl\b", re.IGNORECASE),
    re.compile(r"\bworld\s+series\b", re.IGNORECASE),
    re.compile(r"\bstanley\s+cup\b", re.IGNORECASE),
    re.compile(r"\bnba\s+finals\b", re.IGNORECASE),
    re.compile(r"\bmarch\s+madness\b", re.IGNORECASE),
    re.compile(r"\bfinal\s+four\b", re.IGNORECASE),
]

_CONFERENCE_PATTERNS = [
    re.compile(r"\b(?:eastern|western)\s+conference\b", re.IGNORECASE),
    re.compile(r"\b(?:afc|nfc)\s+(?:championship|winner)\b", re.IGNORECASE),
    re.compile(r"\b(?:american|national)\s+league\s+(?:pennant|champion)", re.IGNORECASE),
    re.compile(r"\bconference\s+(?:champion|winner|final)", re.IGNORECASE),
]

_DIVISION_PATTERNS = [
    re.compile(r"\bdivision\s+(?:winner|champion)", re.IGNORECASE),
    re.compile(r"\b(?:afc|nfc)\s+(?:east|west|north|south)\b", re.IGNORECASE),
    re.compile(r"\b(?:al|nl)\s+(?:east|west|central)\b", re.IGNORECASE),
]


# =============================================================================
# Main classification function
# =============================================================================

def classify_market(
    name: str,
    market_tier: Optional[int] = None,
    category: Optional[str] = None,
) -> MarketType:
    """
    Classify a futures market into a structural type.

    Uses pattern matching on the market name. Checked in priority order:
    1. Stat props (tier 6 in frontend) — "Team at Team: Points"
    2. Game markets (tier 5) — "vs.", "–", "Moneyline", "Game N"
    3. Awards (tier 3) — MVP, Rookie, Heisman, trophies
    4. NOT-championship guard — win totals, make playoffs, seeding
    5. Conference — Eastern/Western Conference, AFC/NFC Championship
    6. Division — AFC East, NL Central
    7. Championship — championship, winner, Super Bowl, World Series
    8. Fall through to backend tier/category or "other"

    Args:
        name: Market name string
        market_tier: Optional backend market_tier (1-5)
        category: Optional backend category string

    Returns:
        MarketType enum value
    """
    if not name:
        return MarketType.other

    # 1. Stat props always get their own type
    if is_stat_prop(name):
        return MarketType.stat_prop

    # 2. Game-level markets (moneylines, matchups)
    if is_game_market(name):
        return MarketType.game

    # 3. Awards
    if is_award(name):
        return MarketType.award

    # 4. NOT-championship guard — must check before championship
    if is_not_championship(name):
        return MarketType.other

    # 5. Conference
    if any(p.search(name) for p in _CONFERENCE_PATTERNS):
        return MarketType.conference

    # 6. Division
    if any(p.search(name) for p in _DIVISION_PATTERNS):
        return MarketType.division

    # 7. Championship
    if any(p.search(name) for p in _CHAMPIONSHIP_PATTERNS):
        return MarketType.championship

    # 8. Fall through to backend hints
    if market_tier is not None:
        tier_map = {
            1: MarketType.championship,
            2: MarketType.conference,
            3: MarketType.award,
            4: MarketType.division,
        }
        if market_tier in tier_map:
            return tier_map[market_tier]

    if category:
        cat_lower = category.lower()
        if cat_lower in MarketType.__members__:
            return MarketType(cat_lower)

    return MarketType.other
