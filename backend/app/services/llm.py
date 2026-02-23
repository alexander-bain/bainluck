"""
LLM utility service for smart text processing tasks.

Uses OpenAI's GPT-4o-mini for cost-effective classification and extraction.
"""

import os
import logging
from datetime import datetime, timezone
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
            _client = OpenAI(api_key=api_key, timeout=30.0)
        except ImportError:
            logger.warning("openai package not installed - LLM features disabled")
            return None
    return _client


def is_available() -> bool:
    """Check if LLM service is available."""
    return _get_client() is not None


def _get_seasonal_context() -> str:
    """
    Generate seasonal context for LLM classification based on current date.

    College teams play multiple sports, so "Iowa at Purdue" could be
    basketball, football, wrestling, etc. The current month disambiguates:
    - College football: Aug–Jan (bowls in Dec/Jan)
    - College basketball: Nov–Apr (March Madness in Mar/Apr)
    - NFL: Sep–Feb (Super Bowl in Feb)
    - MLB: Apr–Oct
    - NHL/NBA: Oct–Jun
    """
    now = datetime.now(timezone.utc)
    month = now.month
    month_name = now.strftime("%B")
    year = now.year

    # Build list of currently active sports
    active = []
    if month in (10, 11, 12, 1, 2, 3, 4, 5, 6):
        active.append("NBA/NCAAB basketball (Oct-Apr)")
    if month in (10, 11, 12, 1, 2, 3, 4, 5, 6):
        active.append("NHL hockey (Oct-Jun)")
    if month in (8, 9, 10, 11, 12, 1):
        active.append("NFL/NCAAF football (Aug-Jan)")
    if month in (4, 5, 6, 7, 8, 9, 10):
        active.append("MLB baseball (Apr-Oct)")

    active_str = ", ".join(active) if active else "various"

    # Special guidance for ambiguous college matchups
    college_hint = ""
    if month in (2, 3, 4):
        college_hint = (
            "IMPORTANT: College football season ended in January. "
            "College team matchups (e.g., 'Iowa at Purdue', 'Memphis at South Florida') "
            "in February-April are almost certainly basketball, NOT football."
        )
    elif month in (5, 6, 7):
        college_hint = (
            "Both college football and basketball are in off-season. "
            "College matchups may be baseball, softball, or other spring sports."
        )
    elif month in (8, 9, 10):
        college_hint = (
            "College football is in-season. College basketball starts in November. "
            "College team matchups in Aug-Oct are likely football."
        )
    elif month in (11, 12, 1):
        college_hint = (
            "Both college football and basketball are in-season. "
            "Use context clues (spreads, point totals) to determine which sport."
        )

    return (
        f"Current date: {month_name} {year}. "
        f"Sports currently in-season: {active_str}. "
        f"{college_hint}"
    )


def classify(
    text: str,
    categories: list[str],
    context: str = "",
    model: str = "gpt-4o-mini",
    fallback: Optional[str] = None,
) -> Optional[str]:
    """
    Classify text into one of the provided categories.

    Args:
        text: The text to classify
        categories: List of valid category options
        context: Optional context to help with classification
        model: OpenAI model to use (default: gpt-4o-mini)
        fallback: Value to return if classification fails (default: None)

    Returns:
        The selected category, or fallback if classification failed
    """
    client = _get_client()
    if not client:
        logger.debug(f"LLM client not available, using fallback: {fallback}")
        return fallback

    categories_str = ", ".join(categories)

    seasonal = _get_seasonal_context()

    system_prompt = f"""You are a classification assistant for a prediction market aggregator. Classify the given text into exactly one of these categories: {categories_str}

{seasonal}

Rules:
- Respond with ONLY the category name, nothing else (e.g., "football" or "crypto")
- If it mentions an athlete, classify by their sport (e.g., "Kyler Murray" → football, "LeBron James" → basketball, "Shai Gilgeous-Alexander" → basketball, "Josh Allen" → football)
- If it mentions a team, classify by their sport (e.g., "Manchester United" → soccer, "Boston Celtics" → basketball)
- "american football" and "NFL" → football
- Darts (PDC, BDO, Premier League Darts, darts tournaments) → darts
- Bitcoin, Ethereum, Solana, crypto prices/tokens → crypto
- Fed rate, inflation, GDP, tariffs, recession → economics
- AI, SpaceX, autonomous vehicles → tech
- Elections, Trump, Congress, legislation → politics
- TV shows, movies, Oscars, Grammys, reality TV, celebrities → entertainment
- Hurricanes, temperature, natural disasters → weather
- Pandemic, FDA, virus outbreaks → health
- War, sanctions, treaties, international relations → geopolitics
- Supreme Court, indictments, lawsuits → legal
- Nobel Prize, social media culture → culture
- Winter sports like curling, figure skating, skiing → olympics
- If outcomes list player names, use those to determine the sport
- If truly ambiguous or unrelated to any category, use "other"
- You MUST choose one of the provided categories
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

        # Common mappings the LLM might return
        mappings = {
            "american football": "football",
            "nfl": "football",
            "nba": "basketball",
            "mlb": "baseball",
            "nhl": "hockey",
            "pga": "golf",
            "ufc": "mma",
            "soccer/football": "soccer",
            "football/soccer": "soccer",
            "horse racing": "horse_racing",
            "horse_racing": "horse_racing",
            "auto racing": "motorsports",
            "motor sports": "motorsports",
            "motorsport": "motorsports",
            "nascar": "motorsports",
            "formula 1": "motorsports",
            "f1": "motorsports",
            "australian rules": "aussierules",
            "australian rules football": "aussierules",
            "aussie rules": "aussierules",
            "table tennis": "tennis",
            "pdc": "darts",
            "bdo": "darts",
            "premier league darts": "darts",
            "mixed martial arts": "mma",
            "e-sports": "esports",
            "video games": "esports",
            "tv": "entertainment",
            "movies": "entertainment",
            "film": "entertainment",
            "music": "entertainment",
            "awards": "entertainment",
            "reality tv": "entertainment",
            "television": "entertainment",
            "cryptocurrency": "crypto",
            "bitcoin": "crypto",
            "finance": "economics",
            "economy": "economics",
            "financial": "economics",
            "science": "tech",
            "technology": "tech",
            "space": "tech",
            "international relations": "geopolitics",
            "foreign policy": "geopolitics",
            "law": "legal",
            "court": "legal",
            "medical": "health",
            "pandemic": "health",
            "climate": "weather",
            "social": "culture",
        }
        if result in mappings:
            mapped = mappings[result]
            if mapped in categories_lower:
                return categories[categories_lower.index(mapped)]

        logger.warning(f"LLM returned unexpected category '{result}' for text '{text[:50]}...', using fallback: {fallback}")
        return fallback

    except Exception as e:
        logger.error(f"LLM classification error: {e}, using fallback: {fallback}")
        return fallback


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
    "aussierules",
    "horse_racing",
    "olympics",
    "esports",
    "entertainment",
    "politics",
    "lacrosse",
    "chess",
    "poker",
    "darts",
    "crypto",
    "economics",
    "tech",
    "weather",
    "health",
    "geopolitics",
    "legal",
    "culture",
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


def classify_futures_market(market_name: str) -> str:
    """
    Classify a futures market name into a sport category.

    This is a specialized wrapper around classify() for futures categorization.
    ALWAYS returns a category - uses "other" as fallback if classification fails.

    Args:
        market_name: The name of the futures market (e.g., "2026 Masters Tournament Winner")

    Returns:
        Sport category string (never None - defaults to "other")
    """
    result = classify(
        text=market_name,
        categories=SPORT_CATEGORIES,
        context="This is the name of a betting/prediction market. Classify it by the sport or topic it relates to.",
        fallback="other",  # Always return a category
    )
    # Extra safety: never return None
    return result if result else "other"


def classify_futures_market_with_outcomes(
    market_name: str,
    outcome_names: Optional[list[str]] = None,
) -> str:
    """
    Classify a futures market with optional outcome context.

    When outcome names are provided (e.g., player names like
    "Shai Gilgeous-Alexander"), the LLM can use them to disambiguate
    markets like "MVP Winner?" that are impossible to categorize by
    title alone.

    Args:
        market_name: The name of the futures market
        outcome_names: Optional list of outcome names for context

    Returns:
        Sport category string (never None - defaults to "other")
    """
    context_text = market_name
    if outcome_names:
        # Include top outcomes for context (limit to avoid token waste)
        top_outcomes = outcome_names[:15]
        context_text = f"{market_name}\nOutcomes: {', '.join(top_outcomes)}"

    seasonal = _get_seasonal_context()

    result = classify(
        text=context_text,
        categories=SPORT_CATEGORIES,
        context=(
            "This is a betting/prediction market. Classify by the sport or topic. "
            "Use outcome names (player/team names) as clues to determine the sport. "
            "For example, if outcomes include NBA players like Shai Gilgeous-Alexander "
            "or Nikola Jokic, classify as basketball. If outcomes include NFL players "
            "like Josh Allen or Lamar Jackson, classify as football. "
            f"{seasonal}"
        ),
        fallback="other",
    )
    return result if result else "other"


# =========================================================================
# Open-ended (unconstrained) classification — future-proof
# =========================================================================

# Maps common LLM free-text outputs to canonical category names.
# When the LLM suggests a category that's a known synonym, we normalize it.
# When it suggests something genuinely new, we keep it as-is.
_OPEN_ENDED_NORMALIZATIONS: dict[str, str] = {
    "american_football": "football",
    "college_football": "football",
    "pro_football": "football",
    "college_basketball": "basketball",
    "pro_basketball": "basketball",
    "ice_hockey": "hockey",
    "auto_racing": "motorsports",
    "auto": "motorsports",
    "automotive": "motorsports",
    "motor_sports": "motorsports",
    "motorsport": "motorsports",
    "formula_1": "motorsports",
    "horse_racing": "horse_racing",
    "mixed_martial_arts": "mma",
    "australian_rules": "aussierules",
    "australian_rules_football": "aussierules",
    "e_sports": "esports",
    "e-sports": "esports",
    "video_games": "esports",
    "darts_tournament": "darts",
    "pdc": "darts",
    "bdo": "darts",
    "premier_league_darts": "darts",
    "cryptocurrency": "crypto",
    "digital_assets": "crypto",
    "finance": "economics",
    "economy": "economics",
    "financial_markets": "economics",
    "stock_market": "economics",
    "monetary_policy": "economics",
    "science": "tech",
    "technology": "tech",
    "artificial_intelligence": "tech",
    "space_exploration": "tech",
    "space": "tech",
    "aerospace": "tech",
    "international_relations": "geopolitics",
    "foreign_policy": "geopolitics",
    "global_politics": "geopolitics",
    "law": "legal",
    "judiciary": "legal",
    "regulation": "legal",
    "medical": "health",
    "public_health": "health",
    "climate": "weather",
    "natural_disasters": "weather",
    "social_media": "culture",
    "pop_culture": "culture",
    "adventure": "entertainment",
    "travel": "entertainment",
    "business": "economics",
    "corporate": "economics",
    "reality_tv": "entertainment",
    "television": "entertainment",
    "movies": "entertainment",
    "film": "entertainment",
    "music": "entertainment",
    "awards": "entertainment",
    "celebrity": "entertainment",
}


def _normalize_open_ended_category(raw: str) -> str:
    """
    Normalize an LLM-generated free-text category to a canonical name.

    Maps known synonyms to standard categories. Passes through genuinely
    novel categories as-is, enabling auto-discovery of new category types.
    """
    if not raw:
        return "other"

    cleaned = raw.strip().lower().strip('"\'.')
    cleaned = cleaned.replace(" ", "_").replace("-", "_")

    # Direct match to existing SPORT_CATEGORIES
    categories_lower = [c.lower() for c in SPORT_CATEGORIES]
    if cleaned in categories_lower:
        return SPORT_CATEGORIES[categories_lower.index(cleaned)]

    # Check normalization map
    if cleaned in _OPEN_ENDED_NORMALIZATIONS:
        return _OPEN_ENDED_NORMALIZATIONS[cleaned]

    # Partial match against known categories
    for i, cat in enumerate(categories_lower):
        if cat in cleaned or cleaned in cat:
            return SPORT_CATEGORIES[i]

    # Novel category — pass through as-is
    # This is the future-proofing mechanism: new market types
    # automatically get descriptive categories without code changes
    if cleaned and cleaned != "other":
        return cleaned

    return "other"


def classify_open_ended(
    market_name: str,
    outcome_names: Optional[list[str]] = None,
) -> str:
    """
    Classify a market with NO constraints on category names.

    Unlike classify_futures_market() which picks from a fixed list, this
    lets the LLM freely name the best category. Used as a last resort
    when constrained classification returns 'other'.

    The result is normalized: mapped to known categories when possible,
    or stored as-is when truly novel (enabling auto-discovery).

    Args:
        market_name: The name of the futures market
        outcome_names: Optional list of outcome names for context

    Returns:
        Category string (never None - defaults to "other")
    """
    client = _get_client()
    if not client:
        return "other"

    context_text = market_name
    if outcome_names:
        top_outcomes = outcome_names[:15]
        context_text = f"{market_name}\nOutcomes: {', '.join(top_outcomes)}"

    seasonal = _get_seasonal_context()

    system_prompt = f"""You are a classification assistant for a prediction market aggregator.
Given a prediction market title (and optionally its outcome names), respond with the SINGLE most specific category.

{seasonal}

Rules:
- Respond with ONLY the category name (1-2 words), nothing else
- Use lowercase with underscores (e.g., "basketball", "horse_racing")
- Be specific: prefer "basketball" over "sports", "crypto" over "finance"
- For sports: use the sport name (football, basketball, baseball, hockey, golf, tennis, soccer, mma, motorsports, boxing, cricket, rugby, olympics, esports, horse_racing, lacrosse, chess, poker, darts, aussierules)
- For non-sports: politics, entertainment, crypto, economics, tech, weather, health, geopolitics, legal, culture
- Use outcome names (player/team names) as clues when the title is ambiguous
- If the market is genuinely about a novel topic, name it descriptively (e.g., "ai_safety", "education", "real_estate", "energy")
- Do NOT say "other" — always pick the most descriptive category possible"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_text},
            ],
            max_tokens=20,
            temperature=0,
        )

        raw = response.choices[0].message.content.strip()
        result = _normalize_open_ended_category(raw)

        if result != "other":
            logger.info(
                "Open-ended classified '%s' as '%s' (raw: '%s')",
                market_name[:60], result, raw,
            )
        return result

    except Exception as e:
        logger.error(f"Open-ended classification error: {e}")
        return "other"


def generate_tags_via_llm(
    market_name: str,
    outcome_names: Optional[list[str]] = None,
    existing_tags: Optional[list[str]] = None,
) -> list[str]:
    """
    Generate descriptive tags for a prediction market using LLM.

    Used to enrich category_tags when pattern-based tag extraction
    produces sparse results. Returns a merged set of existing + new tags.

    Args:
        market_name: The market name
        outcome_names: Optional list of outcome names for context
        existing_tags: Tags already assigned (won't be duplicated)

    Returns:
        Sorted list of unique tags (existing + LLM-generated)
    """
    client = _get_client()
    if not client:
        return existing_tags or []

    context_text = market_name
    if outcome_names:
        top_outcomes = outcome_names[:10]
        context_text = f"{market_name}\nOutcomes: {', '.join(top_outcomes)}"

    existing_str = ""
    if existing_tags:
        existing_str = f"\nAlready tagged: {', '.join(existing_tags)}. Do NOT repeat these."

    system_prompt = f"""Generate 3-5 descriptive tags for this prediction market.{existing_str}

Rules:
- Tags should be lowercase with underscores (e.g., "nba", "trump", "bitcoin")
- Include the sport or topic (e.g., "basketball", "politics", "crypto")
- Include specific entities mentioned (teams, people, events, companies)
- Include the league if applicable (e.g., "nfl", "nba", "epl")
- Be specific and useful for browsing/searching
- Respond with ONLY a comma-separated list of tags, nothing else

Example: nba, basketball, mvp, lebron_james, lakers"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_text},
            ],
            max_tokens=100,
            temperature=0,
        )

        raw = response.choices[0].message.content.strip()
        tags = set(existing_tags or [])
        for tag in raw.split(","):
            tag = tag.strip().lower().strip('"\'.')
            tag = tag.replace(" ", "_")
            # Only add reasonable-length tags
            if tag and 2 <= len(tag) <= 50:
                tags.add(tag)

        return sorted(tags)

    except Exception as e:
        logger.error(f"LLM tag generation error: {e}")
        return existing_tags or []


# Simple in-memory cache for repeated classifications (doesn't cache None)
_classification_cache: dict[str, str] = {}


def classify_futures_market_cached(market_name: str) -> Optional[str]:
    """
    Cached version of classify_futures_market.

    Only caches successful classifications - failures can be retried.
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

    # Combat sports (MMA, boxing) are typically men's unless specified
    if any(cs in sport_lower for cs in ["mma", "ufc", "boxing"]):
        # Check for women's combat sports
        if any(w in text_lower for w in ["women", "female", "wmma"]):
            return "women"
        return "men"

    # Major US sports leagues are men's by default
    if any(league in sport_lower for league in ["_nfl", "_nba", "_mlb", "_nhl", "_ncaaf", "_ncaab"]):
        return "men"

    # Soccer leagues are men's by default (women's soccer has explicit indicators like "nwsl", "women")
    if "soccer" in sport_lower:
        return "men"

    # For ambiguous cases, use LLM with "unknown" fallback
    context = f"Sport key: {sport_key}" if sport_key else ""
    context += " Determine if this is a men's, women's, or mixed (co-ed) sporting event or market."

    return classify(
        text=text,
        categories=GENDER_CATEGORIES,
        context=context,
        fallback="unknown",
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

    # Professional leagues and sports (including combat sports and soccer)
    pro_indicators = [
        "nfl", "nba", "mlb", "nhl", "pga", "atp", "wta", "ufc",
        "mma", "boxing", "epl", "la_liga", "bundesliga", "serie_a",
        "champions_league", "euroleague", "lpga", "soccer",
    ]
    if any(p in sport_lower for p in pro_indicators):
        return "professional"

    # For ambiguous cases, use LLM with "unknown" fallback
    context = f"Sport key: {sport_key}" if sport_key else ""
    context += " Determine the competition level of this sporting event."

    return classify(
        text=text,
        categories=LEVEL_CATEGORIES,
        context=context,
        fallback="unknown",
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
        # American Football
        "americanfootball_nfl": "NFL",
        "americanfootball_ncaaf": "NCAAF",
        "americanfootball_cfl": "CFL",
        "americanfootball_xfl": "XFL",
        # Basketball
        "basketball_nba": "NBA",
        "basketball_wnba": "WNBA",
        "basketball_ncaab": "NCAAB",
        "basketball_wncaab": "WNCAAB",
        "basketball_euroleague": "EuroLeague",
        # Baseball
        "baseball_mlb": "MLB",
        # Hockey
        "icehockey_nhl": "NHL",
        # Golf
        "golf_pga": "PGA",
        "golf_lpga": "LPGA",
        "golf_masters": "PGA",
        # Tennis
        "tennis_atp": "ATP",
        "tennis_wta": "WTA",
        # Combat sports
        "mma_ufc": "UFC",
        "mma_mixed_martial_arts": "UFC",
        "boxing_boxing": "Boxing",
        # Soccer - Top leagues
        "soccer_epl": "EPL",
        "soccer_spain_la_liga": "La_Liga",
        "soccer_germany_bundesliga": "Bundesliga",
        "soccer_italy_serie_a": "Serie_A",
        "soccer_france_ligue_one": "Ligue_1",
        "soccer_usa_mls": "MLS",
        "soccer_uefa_champs_league": "Champions_League",
        # Soccer - England lower divisions
        "soccer_efl_champ": "EFL_Championship",
        "soccer_england_league1": "EFL_League_One",
        "soccer_england_league2": "EFL_League_Two",
        "soccer_england_efl_cup": "EFL_Cup",
        # Soccer - Other European
        "soccer_france_ligue_two": "Ligue_2",
        "soccer_germany_liga3": "3_Liga",
        "soccer_italy_serie_b": "Serie_B",
        "soccer_spain_segunda": "La_Liga_2",
        "soccer_netherlands_eredivisie": "Eredivisie",
        "soccer_portugal_primeira_liga": "Primeira_Liga",
        "soccer_turkey_super_league": "Super_Lig",
        "soccer_belgium_first_div": "Belgian_First_Division",
        # Soccer - Americas
        "soccer_brazil_serie_a": "Brasileirao",
        "soccer_mexico_ligamx": "Liga_MX",
        "soccer_argentina_primera": "Argentina_Primera",
        # Soccer - Other regions
        "soccer_australia_aleague": "A_League",
        "soccer_japan_j_league": "J_League",
        # Soccer - International
        "soccer_uefa_europa_league": "Europa_League",
        "soccer_fifa_world_cup": "World_Cup",
    }

    # Also check for partial matches in sport_key for soccer
    if sport_lower.startswith("soccer_") and sport_lower not in league_mapping:
        # Extract league name from sport_key as fallback
        league_part = sport_lower.replace("soccer_", "").replace("_", " ").title()
        return league_part

    if sport_lower in league_mapping:
        return league_mapping[sport_lower]

    # For ambiguous cases, use LLM with "Other" fallback
    context = f"Sport key: {sport_key}" if sport_key else ""
    context += " Identify the specific league or competition this event belongs to."

    return classify(
        text=text,
        categories=LEAGUE_OPTIONS,
        context=context,
        fallback="Other",
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
    sport_lower = (sport_key or "").lower()

    # Quick heuristic checks
    championship_terms = ["super bowl", "world series", "stanley cup", "nba finals", "championship", "final", "title fight", "title bout"]
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

    # Combat sports (MMA/boxing) individual fights default to regular_season equivalent
    # Most tracked MMA/boxing fights are significant matchups
    if any(cs in sport_lower for cs in ["mma", "ufc", "boxing"]):
        return "regular_season"

    # Soccer league games are regular season unless explicitly a cup/final
    # Note: "efl_champ" is the Championship league name, not a championship game
    if "soccer" in sport_lower:
        # Cup competitions
        if any(cup in sport_lower for cup in ["cup", "copa", "coupe"]):
            return "playoff"  # Cup games are knockout/playoff format
        # Regular league games
        return "regular_season"

    # For ambiguous cases, use LLM with "regular_season" as default
    # Most events are regular season games
    context = f"Sport key: {sport_key}" if sport_key else ""
    context += " Classify the importance or stage of this sporting event."

    return classify(
        text=text,
        categories=IMPORTANCE_CATEGORIES,
        context=context,
        fallback="regular_season",
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


def normalize_team_name(
    team_name: str,
    sport_key: Optional[str] = None,
) -> dict:
    """
    Normalize a team name to its canonical form and generate common variations.

    This helps with matching across different data sources (ESPN, The Odds API, etc.)
    that may use different name formats.

    Args:
        team_name: The team name to normalize (e.g., "Lakers", "LA Lakers")
        sport_key: Sport key for context (e.g., "basketball_nba")

    Returns:
        Dict with:
        - normalized: Full canonical name (e.g., "Los Angeles Lakers")
        - variations: List of common name variations
    """
    client = _get_client()
    if not client:
        # Return original name if LLM not available
        return {"normalized": team_name, "variations": [team_name]}

    sport_context = f"Sport: {sport_key}" if sport_key else ""

    prompt = f"""Given this sports team name, provide:
1. The full official/canonical team name
2. Common name variations (abbreviations, nicknames, city variations)

Team name: {team_name}
{sport_context}

Respond in this exact JSON format (no markdown, just JSON):
{{"normalized": "Full Team Name", "variations": ["variation1", "variation2", "variation3"]}}

Examples:
- "Lakers" → {{"normalized": "Los Angeles Lakers", "variations": ["Lakers", "LA Lakers", "L.A. Lakers"]}}
- "Man United" → {{"normalized": "Manchester United", "variations": ["Man United", "Man Utd", "MUFC"]}}
- "Celtics" → {{"normalized": "Boston Celtics", "variations": ["Celtics", "Boston"]}}

Keep variations to 3-5 most common. Include the original input as a variation."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0,
        )

        result = response.choices[0].message.content.strip()

        # Parse JSON response
        import json
        # Handle potential markdown code blocks
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        result = result.strip()

        data = json.loads(result)

        # Ensure original name is in variations
        variations = data.get("variations", [])
        if team_name not in variations:
            variations.append(team_name)

        return {
            "normalized": data.get("normalized", team_name),
            "variations": variations,
        }

    except Exception as e:
        logger.error(f"Team normalization error for '{team_name}': {e}")
        return {"normalized": team_name, "variations": [team_name]}


@lru_cache(maxsize=2000)
def normalize_team_name_cached(team_name: str, sport_key: Optional[str] = None) -> tuple:
    """
    Cached version of normalize_team_name.

    Returns tuple (normalized, variations_tuple) for hashability.
    """
    result = normalize_team_name(team_name, sport_key)
    return (result["normalized"], tuple(result["variations"]))


def classify_player_team(
    player_name: str,
    sport_category: Optional[str] = None,
    market_name: Optional[str] = None,
) -> Optional[str]:
    """
    Determine which team a player belongs to using LLM.

    Used to link player-specific futures outcomes (e.g., "Jaylen Brown" in
    an MVP market) to the correct Team record.

    Args:
        player_name: The player's name (e.g., "Jaylen Brown")
        sport_category: Sport category for context (e.g., "basketball")
        market_name: Market name for context (e.g., "NBA MVP 2025-26")

    Returns:
        Team name string (e.g., "Boston Celtics"), or None if unable to determine
    """
    client = _get_client()
    if not client:
        return None

    context_parts = []
    if sport_category:
        context_parts.append(f"Sport: {sport_category}")
    if market_name:
        context_parts.append(f"Market: {market_name}")
    context = ". ".join(context_parts)

    prompt = f"""What professional sports team does this person currently play for (2025-26 season)?

Name: {player_name}
{context}

Rules:
- Respond with ONLY the full official team name (e.g., "Boston Celtics", "Los Angeles Lakers")
- If this is not a recognizable athlete or you're unsure, respond with "UNKNOWN"
- Use the current season's roster (account for trades, free agency)
- For retired players, respond with "UNKNOWN"

Team name:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt},
            ],
            max_tokens=50,
            temperature=0,
        )

        result = response.choices[0].message.content.strip()

        if result.upper() == "UNKNOWN" or not result:
            return None

        # Clean up common LLM formatting artifacts
        result = result.strip('"').strip("'").strip(".")
        return result

    except Exception as e:
        logger.error(f"Player team classification error for '{player_name}': {e}")
        return None


@lru_cache(maxsize=2000)
def classify_player_team_cached(
    player_name: str,
    sport_category: Optional[str] = None,
    market_name: Optional[str] = None,
) -> Optional[str]:
    """Cached version of classify_player_team."""
    return classify_player_team(player_name, sport_category, market_name)


# =========================================================================
# Line movement explanation — "Why Did the Line Move?"
# =========================================================================

def generate_line_movement_explanation(prompt: str) -> Optional[str]:
    """
    Generate a natural-language explanation for why odds moved.

    Uses GPT-4o-mini to analyze odds movement context and produce
    a casual-fan-friendly explanation of likely causes.

    Args:
        prompt: Full prompt with movement context (built by
                line_movement.build_llm_prompt)

    Returns:
        2-3 sentence explanation string, or None if LLM unavailable.
    """
    client = _get_client()
    if not client:
        return None

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.3,  # Slight creativity for natural language
        )

        result = response.choices[0].message.content.strip()

        # Clean up common artifacts
        if result.startswith('"') and result.endswith('"'):
            result = result[1:-1]

        return result

    except Exception as e:
        logger.error(f"Line movement explanation error: {e}")
        return None


def generate_market_disagreement_explanation(
    home_team: str,
    away_team: str,
    sport_key: str,
    sportsbook_home_prob: float,
    prediction_market_home_prob: float,
    prediction_market_source: str,
    divergence_pct: float,
) -> Optional[str]:
    """
    Explain why prediction market odds diverge from sportsbook consensus.

    Args:
        home_team: Home team name
        away_team: Away team name
        sport_key: Sport key
        sportsbook_home_prob: Sportsbook consensus probability
        prediction_market_home_prob: Prediction market probability
        prediction_market_source: "Kalshi" or "Polymarket"
        divergence_pct: Absolute divergence in percentage points

    Returns:
        2-3 sentence explanation, or None if LLM unavailable.
    """
    client = _get_client()
    if not client:
        return None

    sport_name = sport_key.replace("_", " ").title() if sport_key else "game"

    sb_home_pct = round(sportsbook_home_prob * 100, 1)
    pm_home_pct = round(prediction_market_home_prob * 100, 1)
    div_pct = round(divergence_pct * 100, 1)

    # Determine who the prediction market favors more
    if prediction_market_home_prob > sportsbook_home_prob:
        pm_favors = home_team
        sb_favors = away_team
    else:
        pm_favors = away_team
        sb_favors = home_team

    prompt = f"""You are a sports analyst explaining to casual fans why different odds sources disagree.

Sport: {sport_name}
Matchup: {away_team} at {home_team}

Sportsbook consensus: {home_team} {sb_home_pct}% / {away_team} {round(100-sb_home_pct, 1)}%
{prediction_market_source}: {home_team} {pm_home_pct}% / {away_team} {round(100-pm_home_pct, 1)}%

Divergence: {div_pct} percentage points — {prediction_market_source} is more bullish on {pm_favors}

Explain in 2-3 sentences why sportsbooks and prediction markets might disagree on this game. Consider:
- Prediction markets reflect individual bettors' opinions; sportsbooks balance risk
- Prediction markets may react faster to news (injuries, lineup changes)
- Sportsbooks may have more historical data / sharper pricing
- Public money on prediction markets can create temporary mispricings
- {prediction_market_source} traders may have different information than traditional bettors

Be specific to the teams and sport. Use casual language. No betting advice.
Start directly with the explanation (no preamble).

Explanation:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.3,
        )

        result = response.choices[0].message.content.strip()
        if result.startswith('"') and result.endswith('"'):
            result = result[1:-1]
        return result

    except Exception as e:
        logger.error(f"Market disagreement explanation error: {e}")
        return None


def generate_oscars_category_preview(
    category_name: str,
    nominees: list[dict],
) -> Optional[str]:
    """
    Generate a 1-2 sentence casual preview of an Oscar race.

    Args:
        category_name: e.g. "Best Picture"
        nominees: Top 5 nominees with keys: name, probability, movement_24h, opening_probability

    Returns:
        1-2 sentence preview string, or None if LLM unavailable.
    """
    client = _get_client()
    if not client:
        return None

    if not nominees:
        return None

    # Build structured nominee data
    lines = []
    for n in nominees[:5]:
        pct = round(n["probability"] * 100, 1) if n["probability"] else 0
        parts = [f"{n['name']}: {pct}%"]
        if n.get("movement_24h") and abs(n["movement_24h"]) >= 0.005:
            direction = "+" if n["movement_24h"] > 0 else ""
            parts.append(f"(24h: {direction}{round(n['movement_24h'] * 100, 1)}%)")
        if n.get("opening_probability"):
            parts.append(f"(opened at {round(n['opening_probability'] * 100, 1)}%)")
        lines.append(" ".join(parts))

    nominee_text = "\n".join(lines)

    prompt = f"""Write a 1-2 sentence casual preview of this Oscar race for {category_name}.

Nominees (with current odds):
{nominee_text}

Rules:
- Mention specific names and percentages from the data above
- Note if odds are shifting, if there's a clear frontrunner, or if it's tight
- Be conversational but specific — no generic filler
- Do NOT give betting advice
- Start directly with the preview

Preview:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.2,
        )
        result = response.choices[0].message.content.strip()
        if result.startswith('"') and result.endswith('"'):
            result = result[1:-1]
        return result
    except Exception as e:
        logger.error(f"Oscars category preview error: {e}")
        return None


def generate_oscars_movers_summary(
    movers: list[dict],
) -> Optional[str]:
    """
    Generate a 1-sentence summary of the biggest Oscars odds movements.

    Args:
        movers: List of dicts with keys: name, category_name, movement_24h, probability

    Returns:
        1-sentence summary, or None if LLM unavailable.
    """
    client = _get_client()
    if not client:
        return None

    if not movers:
        return None

    lines = []
    for m in movers[:5]:
        direction = "+" if m["movement_24h"] > 0 else ""
        pct = round(m["movement_24h"] * 100, 1)
        lines.append(f"{m['name']} ({m['category_name']}): {direction}{pct}%")

    movers_text = "\n".join(lines)

    prompt = f"""Write exactly 1 sentence summarizing today's biggest Oscars odds movements.

Movers:
{movers_text}

Rules:
- Be specific about names and numbers
- Casual tone, no hedging
- Start directly

Summary:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.2,
        )
        result = response.choices[0].message.content.strip()
        if result.startswith('"') and result.endswith('"'):
            result = result[1:-1]
        return result
    except Exception as e:
        logger.error(f"Oscars movers summary error: {e}")
        return None


def generate_related_futures_summary(
    home_team: str,
    away_team: str,
    sport_key: str,
    event_status: str,
    home_futures: list[dict],
    away_futures: list[dict],
) -> Optional[str]:
    """
    Generate a casual summary of what championship/award futures mean for a game.

    Produces a 2-4 sentence "Bigger Picture" blurb that contextualizes the
    game within each team's broader season. Used in the related-futures section
    on event detail pages.

    Args:
        home_team: Home team name
        away_team: Away team name
        sport_key: Sport key (e.g., "basketball_nba")
        event_status: "scheduled", "live", "completed", "closed"
        home_futures: List of dicts with keys: market_name, outcome_name, probability
        away_futures: Same format for away team

    Returns:
        2-4 sentence summary string, or None if LLM unavailable or no futures data.
    """
    client = _get_client()
    if not client:
        return None

    if not home_futures and not away_futures:
        return None

    sport_name = sport_key.replace("_", " ").title() if sport_key else "game"

    # Build structured data for prompt — include movement data
    def _format_futures(team: str, futures: list[dict]) -> str:
        if not futures:
            return f"  {team}: No championship/award markets found."
        lines = [f"  {team}:"]
        for f in futures[:8]:  # Cap at 8 per team to limit tokens
            prob = f.get("probability")
            prob_pct = f"{round(prob * 100, 1)}%" if prob else "?"
            parts = [f"    - {f.get('market_name', '?')}: {prob_pct}"]

            # Add movement data if available
            change = f.get("probability_change_24h")
            if change and abs(change) >= 0.005:
                direction = "+" if change > 0 else ""
                parts.append(f"(24h: {direction}{round(change * 100, 1)}%)")

            opening = f.get("opening_probability")
            if opening and prob:
                shift = prob - opening
                if abs(shift) >= 0.01:
                    direction = "+" if shift > 0 else ""
                    parts.append(f"(opened at {round(opening * 100, 1)}%)")

            lines.append(" ".join(parts))
        return "\n".join(lines)

    home_section = _format_futures(home_team, home_futures)
    away_section = _format_futures(away_team, away_futures)

    status_instruction = {
        "scheduled": "The game hasn't started yet.",
        "live": "The game is currently in progress.",
        "completed": "The game is over. If odds moved since opening, mention the shift.",
        "closed": "The game is over. If odds moved since opening, mention the shift.",
    }.get(event_status, "")

    prompt = f"""Summarize these futures odds for a sports app. Write exactly 2-3 sentences using ONLY the numbers provided below. Do not invent or assume any probabilities — state only what the data shows.

Sport: {sport_name}
Matchup: {away_team} at {home_team}
{status_instruction}

Futures odds:
{home_section}
{away_section}

Rules:
- State the actual probabilities from the data above. Example: "The Celtics sit at 18.5% to win the NBA Championship while the Bulls are at 0.2%."
- If there's notable 24h movement or a gap between opening and current odds, mention it with the actual numbers.
- Compare the two teams' odds only if there's a meaningful difference.
- Do NOT editorialize, speculate, or add generic sports commentary. No phrases like "this game could be pivotal" or "a lot is on the line."
- Do NOT give betting advice.
- Start directly with the data.

Summary:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt},
            ],
            max_tokens=250,
            temperature=0.1,
        )

        result = response.choices[0].message.content.strip()
        if result.startswith('"') and result.endswith('"'):
            result = result[1:-1]
        return result

    except Exception as e:
        logger.error(f"Related futures summary error: {e}")
        return None
