"""
LLM utility service for smart text processing tasks.

Uses OpenAI's GPT-4o-mini for cost-effective classification and extraction.
"""

import os
import logging
from typing import Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# Lazy import to avoid issues if openai isn't installed
_client = None


def _get_client():
    """Get or create OpenAI client (lazy initialization)."""
    global _client
    if _client is None:
        try:
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY not set - LLM features disabled")
                return None
            _client = OpenAI(api_key=api_key)
        except ImportError:
            logger.warning("openai package not installed - LLM features disabled")
            return None
    return _client


def is_available() -> bool:
    """Check if LLM service is available."""
    return _get_client() is not None


def classify(
    text: str,
    categories: list[str],
    context: str = "",
    model: str = "gpt-4o-mini",
) -> Optional[str]:
    """
    Classify text into one of the provided categories.

    Args:
        text: The text to classify
        categories: List of valid category options
        context: Optional context to help with classification
        model: OpenAI model to use (default: gpt-4o-mini)

    Returns:
        The selected category, or None if classification failed
    """
    client = _get_client()
    if not client:
        return None

    categories_str = ", ".join(categories)

    system_prompt = f"""You are a classification assistant. Your task is to classify text into exactly one of these categories: {categories_str}

Rules:
- Respond with ONLY the category name, nothing else
- Choose the single best matching category
- If uncertain, choose the closest match
{f"Context: {context}" if context else ""}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            max_tokens=50,
            temperature=0,  # Deterministic for classification
        )

        result = response.choices[0].message.content.strip().lower()

        # Validate result is one of the categories
        categories_lower = [c.lower() for c in categories]
        if result in categories_lower:
            # Return the original case version
            return categories[categories_lower.index(result)]

        # Try partial match (e.g., "basketball" matches "basketball")
        for i, cat in enumerate(categories_lower):
            if cat in result or result in cat:
                return categories[i]

        logger.warning(f"LLM returned unexpected category '{result}' for text '{text[:50]}...'")
        return None

    except Exception as e:
        logger.error(f"LLM classification error: {e}")
        return None


# Sport categories for futures classification
SPORT_CATEGORIES = [
    "football",
    "basketball",
    "baseball",
    "hockey",
    "golf",
    "tennis",
    "soccer",
    "mma",
    "motorsports",
    "boxing",
    "cricket",
    "rugby",
    "olympics",
    "esports",
    "entertainment",
    "politics",
    "lacrosse",
    "chess",
    "poker",
    "other",
]

# Gender categories
GENDER_CATEGORIES = ["men", "women", "mixed", "unknown"]

# Level categories (professional vs amateur)
LEVEL_CATEGORIES = ["professional", "college", "amateur", "youth", "unknown"]

# Importance categories
IMPORTANCE_CATEGORIES = [
    "championship",  # Finals, Super Bowl, World Series
    "playoff",  # Playoff games, tournament rounds
    "regular_season",  # Regular season games
    "exhibition",  # Preseason, All-Star, friendlies
    "qualifier",  # Qualifying rounds, play-in games
    "unknown",
]

# Common league identifiers for classification
LEAGUE_OPTIONS = [
    # Football
    "NFL", "NCAAF", "CFL", "XFL", "USFL",
    # Basketball
    "NBA", "WNBA", "NCAAB", "WNCAAB", "EuroLeague", "G-League",
    # Baseball
    "MLB", "NPB", "KBO", "NCAA_Baseball",
    # Hockey
    "NHL", "AHL", "KHL", "NCAA_Hockey",
    # Soccer
    "EPL", "La_Liga", "Serie_A", "Bundesliga", "Ligue_1", "MLS",
    "Champions_League", "Europa_League", "World_Cup", "International",
    # Golf
    "PGA", "LPGA", "European_Tour", "LIV",
    # Tennis
    "ATP", "WTA", "Grand_Slam",
    # MMA/Boxing
    "UFC", "Bellator", "PFL", "Boxing",
    # Other
    "Olympics", "Other",
]


def classify_futures_market(market_name: str) -> Optional[str]:
    """
    Classify a futures market name into a sport category.

    This is a specialized wrapper around classify() for futures categorization.

    Args:
        market_name: The name of the futures market (e.g., "2026 Masters Tournament Winner")

    Returns:
        Sport category string, or None if classification failed
    """
    return classify(
        text=market_name,
        categories=SPORT_CATEGORIES,
        context="This is the name of a betting/prediction market. Classify it by the sport or topic it relates to.",
    )


# Simple in-memory cache for repeated classifications
@lru_cache(maxsize=1000)
def classify_futures_market_cached(market_name: str) -> Optional[str]:
    """
    Cached version of classify_futures_market.

    Uses LRU cache to avoid repeated API calls for the same market names.
    """
    return classify_futures_market(market_name)


def classify_gender(text: str, sport_key: Optional[str] = None) -> Optional[str]:
    """
    Classify whether an event/market is men's, women's, or mixed.

    Args:
        text: Event description or market name (e.g., "WNBA Championship", "Lakers vs Celtics")
        sport_key: Optional sport key for context (e.g., "basketball_wnba")

    Returns:
        One of: "men", "women", "mixed", "unknown"
    """
    # Quick heuristic checks before LLM call
    text_lower = text.lower()
    sport_lower = (sport_key or "").lower()

    # Check for explicit women's indicators
    if any(w in text_lower or w in sport_lower for w in ["wnba", "wncaa", "wpga", "wta", "lpga", "women"]):
        return "women"

    # Check for explicit mixed indicators
    if any(m in text_lower for m in ["mixed doubles", "mixed relay", "coed"]):
        return "mixed"

    # For ambiguous cases, use LLM
    context = f"Sport key: {sport_key}" if sport_key else ""
    context += " Determine if this is a men's, women's, or mixed (co-ed) sporting event or market."

    return classify(
        text=text,
        categories=GENDER_CATEGORIES,
        context=context,
    )


@lru_cache(maxsize=1000)
def classify_gender_cached(text: str, sport_key: Optional[str] = None) -> Optional[str]:
    """Cached version of classify_gender."""
    return classify_gender(text, sport_key)


def classify_level(text: str, sport_key: Optional[str] = None) -> Optional[str]:
    """
    Classify the competition level (professional, college, amateur, youth).

    Args:
        text: Event description or market name
        sport_key: Optional sport key for context

    Returns:
        One of: "professional", "college", "amateur", "youth", "unknown"
    """
    text_lower = text.lower()
    sport_lower = (sport_key or "").lower()

    # Quick heuristic checks
    if any(c in text_lower or c in sport_lower for c in ["ncaa", "college", "university", "ncaab", "ncaaf"]):
        return "college"

    if any(p in sport_lower for p in ["nfl", "nba", "mlb", "nhl", "pga", "atp", "wta", "ufc"]):
        return "professional"

    # For ambiguous cases, use LLM
    context = f"Sport key: {sport_key}" if sport_key else ""
    context += " Determine the competition level of this sporting event."

    return classify(
        text=text,
        categories=LEVEL_CATEGORIES,
        context=context,
    )


@lru_cache(maxsize=1000)
def classify_level_cached(text: str, sport_key: Optional[str] = None) -> Optional[str]:
    """Cached version of classify_level."""
    return classify_level(text, sport_key)


def classify_league(text: str, sport_key: Optional[str] = None) -> Optional[str]:
    """
    Classify the specific league (NFL, NBA, NCAAF, etc.).

    Args:
        text: Event description or market name
        sport_key: Optional sport key for context

    Returns:
        League identifier string (e.g., "NFL", "NBA", "NCAAF")
    """
    sport_lower = (sport_key or "").lower()

    # Quick extraction from sport key
    league_mapping = {
        "americanfootball_nfl": "NFL",
        "americanfootball_ncaaf": "NCAAF",
        "americanfootball_cfl": "CFL",
        "americanfootball_xfl": "XFL",
        "basketball_nba": "NBA",
        "basketball_wnba": "WNBA",
        "basketball_ncaab": "NCAAB",
        "basketball_wncaab": "WNCAAB",
        "basketball_euroleague": "EuroLeague",
        "baseball_mlb": "MLB",
        "icehockey_nhl": "NHL",
        "golf_pga": "PGA",
        "golf_lpga": "LPGA",
        "golf_masters": "PGA",  # Masters is a PGA major
        "tennis_atp": "ATP",
        "tennis_wta": "WTA",
        "mma_ufc": "UFC",
        "soccer_epl": "EPL",
        "soccer_spain_la_liga": "La_Liga",
        "soccer_germany_bundesliga": "Bundesliga",
        "soccer_italy_serie_a": "Serie_A",
        "soccer_france_ligue_one": "Ligue_1",
        "soccer_usa_mls": "MLS",
        "soccer_uefa_champs_league": "Champions_League",
    }

    if sport_lower in league_mapping:
        return league_mapping[sport_lower]

    # For ambiguous cases, use LLM
    context = f"Sport key: {sport_key}" if sport_key else ""
    context += " Identify the specific league or competition this event belongs to."

    return classify(
        text=text,
        categories=LEAGUE_OPTIONS,
        context=context,
    )


@lru_cache(maxsize=1000)
def classify_league_cached(text: str, sport_key: Optional[str] = None) -> Optional[str]:
    """Cached version of classify_league."""
    return classify_league(text, sport_key)


def classify_importance(text: str, sport_key: Optional[str] = None) -> Optional[str]:
    """
    Classify the importance/type of game (playoff, championship, regular season, etc.).

    Args:
        text: Event description or market name
        sport_key: Optional sport key for context

    Returns:
        One of: "championship", "playoff", "regular_season", "exhibition", "qualifier", "unknown"
    """
    text_lower = text.lower()

    # Quick heuristic checks
    championship_terms = ["super bowl", "world series", "stanley cup", "nba finals", "championship", "final"]
    if any(term in text_lower for term in championship_terms):
        return "championship"

    playoff_terms = ["playoff", "postseason", "wild card", "divisional", "conference"]
    if any(term in text_lower for term in playoff_terms):
        return "playoff"

    exhibition_terms = ["preseason", "exhibition", "all-star", "all star", "pro bowl", "friendly"]
    if any(term in text_lower for term in exhibition_terms):
        return "exhibition"

    qualifier_terms = ["qualifier", "qualifying", "play-in", "playin"]
    if any(term in text_lower for term in qualifier_terms):
        return "qualifier"

    # For ambiguous cases, use LLM
    context = f"Sport key: {sport_key}" if sport_key else ""
    context += " Classify the importance or stage of this sporting event."

    return classify(
        text=text,
        categories=IMPORTANCE_CATEGORIES,
        context=context,
    )


@lru_cache(maxsize=1000)
def classify_importance_cached(text: str, sport_key: Optional[str] = None) -> Optional[str]:
    """Cached version of classify_importance."""
    return classify_importance(text, sport_key)


def enrich_event_metadata(
    home_team: str,
    away_team: str,
    sport_key: Optional[str] = None,
    event_name: Optional[str] = None,
) -> dict:
    """
    Enrich an event with all metadata classifications.

    Args:
        home_team: Home team name
        away_team: Away team name
        sport_key: Sport key (e.g., "basketball_nba")
        event_name: Optional event name for additional context

    Returns:
        Dict with keys: gender, level, league, importance
    """
    # Build context text
    text = f"{away_team} at {home_team}"
    if event_name:
        text = f"{event_name}: {text}"

    return {
        "gender": classify_gender_cached(text, sport_key),
        "level": classify_level_cached(text, sport_key),
        "league": classify_league_cached(text, sport_key),
        "importance": classify_importance_cached(text, sport_key),
    }


def enrich_market_metadata(
    market_name: str,
    sport_key: Optional[str] = None,
) -> dict:
    """
    Enrich a futures market with metadata classifications.

    Args:
        market_name: Name of the futures market
        sport_key: Optional sport key for context

    Returns:
        Dict with keys: gender, level, league
    """
    return {
        "gender": classify_gender_cached(market_name, sport_key),
        "level": classify_level_cached(market_name, sport_key),
        "league": classify_league_cached(market_name, sport_key),
    }


def match_team_names(name1: str, name2: str, sport: Optional[str] = None) -> float:
    """
    Determine if two team names refer to the same team using LLM.

    Args:
        name1: First team name (e.g., "LA Lakers")
        name2: Second team name (e.g., "Los Angeles Lakers")
        sport: Optional sport for context

    Returns:
        Confidence score 0.0-1.0 that these are the same team
    """
    client = _get_client()
    if not client:
        return 0.0

    context = f"Sport: {sport}" if sport else ""

    prompt = f"""Are these two names referring to the same sports team?

Name 1: {name1}
Name 2: {name2}
{context}

Respond with a single number from 0.0 to 1.0 indicating your confidence that these are the same team.
0.0 = definitely different teams
1.0 = definitely the same team
0.5 = uncertain

Just respond with the number, nothing else."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt},
            ],
            max_tokens=10,
            temperature=0,
        )

        result = response.choices[0].message.content.strip()
        return float(result)

    except Exception as e:
        logger.error(f"Team matching error: {e}")
        return 0.0


@lru_cache(maxsize=2000)
def match_team_names_cached(name1: str, name2: str, sport: Optional[str] = None) -> float:
    """Cached version of match_team_names."""
    return match_team_names(name1, name2, sport)
