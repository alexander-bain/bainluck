"""
Futures market sport categorization.

Uses a hybrid approach:
1. Pattern matching rules (fast, free, deterministic)
2. LLM fallback for edge cases (smart, cached)
"""

import re
import logging
from typing import Optional

from app.services import llm

logger = logging.getLogger(__name__)


# Sport categories with their regex patterns
# Order matters - more specific patterns should come first
SPORT_PATTERNS = [
    # Baseball - Match AL/NL awards, MVP, Cy Young, etc.
    (re.compile(r"\b(mlb|world.series)\b", re.I), "baseball"),
    (re.compile(r"\b(al|nl)\s+(mvp|cy.young|rookie|reliever|hank.aaron|manager|comeback)\b", re.I), "baseball"),
    (re.compile(r"\bamerican.league\b", re.I), "baseball"),
    (re.compile(r"\bnational.league\b", re.I), "baseball"),
    (re.compile(r"\bpro.baseball\b", re.I), "baseball"),

    # Football - Match college football, NFL, Super Bowl, Heisman, etc.
    (re.compile(r"\b(nfl|super.bowl)\b", re.I), "football"),
    (re.compile(r"\bcollege.football\b", re.I), "football"),
    (re.compile(r"\bncaaf\b", re.I), "football"),
    (re.compile(r"\bheisman\b", re.I), "football"),
    (re.compile(r"\b(afc|nfc)\s+(championship|winner|east|west|north|south)\b", re.I), "football"),
    (re.compile(r"\bpro.football\b", re.I), "football"),
    (re.compile(r"\b(acc|sec|big.ten|big.12|pac.12)\s+(championship|football)\b", re.I), "football"),

    # Basketball
    (re.compile(r"\b(nba|ncaab|wnba)\b", re.I), "basketball"),
    (re.compile(r"\bmarch.madness\b", re.I), "basketball"),
    (re.compile(r"\b(eastern|western).conference\b", re.I), "basketball"),
    (re.compile(r"\bpro.basketball\b", re.I), "basketball"),
    (re.compile(r"\brookie.of.the.year\b", re.I), "basketball"),  # Usually basketball context

    # Hockey
    (re.compile(r"\b(nhl|stanley.cup)\b", re.I), "hockey"),

    # Golf
    (re.compile(r"\b(pga|masters|british.open|the.open|ryder.cup)\b", re.I), "golf"),
    (re.compile(r"\bgolf\b", re.I), "golf"),

    # Tennis
    (re.compile(r"\b(wimbledon|french.open|australian.open|atp|wta)\b", re.I), "tennis"),

    # Soccer - Match Ballon d'Or, PFA, Premier League, etc.
    (re.compile(r"\b(ballon.d.or|pfa.player|epl|premier.league|champions.league|mls|la.liga|bundesliga|serie.a|nwsl)\b", re.I), "soccer"),
    (re.compile(r"\bworld.cup\b(?!.*college)", re.I), "soccer"),
    (re.compile(r"\bbarcelona\b", re.I), "soccer"),

    # MMA
    (re.compile(r"\b(ufc|mma)\b", re.I), "mma"),

    # Boxing
    (re.compile(r"\bboxing\b", re.I), "boxing"),

    # Motorsport
    (re.compile(r"\b(formula.1|f1|nascar|indycar|racing|motorsport)\b", re.I), "motorsports"),

    # Politics
    (re.compile(r"\b(election|president|congress|senate|governor|presidential)\b", re.I), "politics"),

    # Esports
    (re.compile(r"\b(lol|league.of.legends|csgo|cs.go|dota|valorant|esports)\b", re.I), "esports"),

    # Entertainment
    (re.compile(r"\b(oscar|emmy|grammy|golden.globe|academy.award|entertainer|box.office|movie|film|music|spotify|album)\b", re.I), "entertainment"),
    (re.compile(r"\b(tv.show|television|reality|bachelor|bachelorette)\b", re.I), "entertainment"),

    # Olympics
    (re.compile(r"\b(olympic|olympics)\b", re.I), "olympics"),
]


def categorize_by_rules(market_name: str, sport_key: Optional[str] = None) -> Optional[str]:
    """
    Try to categorize a market using regex pattern matching.

    Args:
        market_name: The name of the futures market
        sport_key: Optional sport key from the source (e.g., "basketball_nba_championship")

    Returns:
        Sport category string, or None if no pattern matches
    """
    # Build searchable text from sport key and market name
    search_text = " ".join(filter(None, [sport_key, market_name]))

    # Try prefix matching on sport_key first
    if sport_key:
        prefixes = {
            "americanfootball_": "football",
            "basketball_": "basketball",
            "baseball_": "baseball",
            "icehockey_": "hockey",
            "mma_": "mma",
            "boxing_": "boxing",
            "golf_": "golf",
            "tennis_": "tennis",
            "soccer_": "soccer",
            "politics_": "politics",
            "esports_": "esports",
            "motorsport_": "motorsports",
            "lacrosse_": "lacrosse",
        }
        for prefix, category in prefixes.items():
            if sport_key.startswith(prefix):
                return category

    # Try regex pattern matching
    for pattern, category in SPORT_PATTERNS:
        if pattern.search(search_text):
            return category

    return None


def categorize_market(
    market_name: str,
    sport_key: Optional[str] = None,
    use_llm: bool = True,
) -> Optional[str]:
    """
    Categorize a futures market into a sport category.

    Uses hybrid approach:
    1. Try pattern matching rules (fast, free)
    2. Fall back to LLM if rules don't match (smart, cached)

    Args:
        market_name: The name of the futures market
        sport_key: Optional sport key from the source
        use_llm: Whether to use LLM as fallback (default True)

    Returns:
        Sport category string, or None if categorization failed
    """
    # Try rules first
    category = categorize_by_rules(market_name, sport_key)
    if category:
        logger.debug(f"Categorized '{market_name}' as '{category}' via rules")
        return category

    # Fall back to LLM if enabled
    if use_llm and llm.is_available():
        category = llm.classify_futures_market_cached(market_name)
        if category:
            logger.info(f"Categorized '{market_name}' as '{category}' via LLM")
            return category

    logger.debug(f"Could not categorize '{market_name}'")
    return None
