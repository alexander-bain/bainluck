"""
Canonical sport key translation maps.

Every dict that translates between sport key formats (Odds API keys, ESPN paths,
StatPal identifiers, Kalshi tickers, LLM categories, win-prob model keys) lives
here.  Consumer modules import the dicts (or thin accessor functions) they need.

This module imports nothing from the rest of the codebase, so it cannot create
circular-import problems.
"""

from typing import Optional


# =============================================================================
# 1. SPORT_LEAGUE_MAP — Odds API key → ESPN (sport, league) tuple
# =============================================================================

SPORT_LEAGUE_MAP: dict[str, tuple[str, str]] = {
    # Football
    "americanfootball_nfl": ("football", "nfl"),
    "americanfootball_ncaaf": ("football", "college-football"),
    "americanfootball_cfl": ("football", "cfl"),
    # Basketball
    "basketball_nba": ("basketball", "nba"),
    "basketball_wnba": ("basketball", "wnba"),
    "basketball_ncaab": ("basketball", "mens-college-basketball"),
    "basketball_wncaab": ("basketball", "womens-college-basketball"),
    # Baseball
    "baseball_mlb": ("baseball", "mlb"),
    "baseball_mlb_preseason": ("baseball", "mlb"),
    # Hockey
    "icehockey_nhl": ("hockey", "nhl"),
    # Soccer
    "soccer_epl": ("soccer", "eng.1"),
    "soccer_usa_mls": ("soccer", "usa.1"),
    "soccer_uefa_champs_league": ("soccer", "uefa.champions"),
    "soccer_spain_la_liga": ("soccer", "esp.1"),
    "soccer_germany_bundesliga": ("soccer", "ger.1"),
    "soccer_italy_serie_a": ("soccer", "ita.1"),
    "soccer_france_ligue_one": ("soccer", "fra.1"),
    # Golf
    "golf_pga": ("golf", "pga"),
    "golf_lpga": ("golf", "lpga"),
    # Tennis
    "tennis_atp": ("tennis", "atp"),
    "tennis_wta": ("tennis", "wta"),
    # MMA
    "mma_ufc": ("mma", "ufc"),
    "mma_mixed_martial_arts": ("mma", "ufc"),
    # Lacrosse
    "lacrosse_ncaa": ("lacrosse", "mens-college-lacrosse"),
    "lacrosse_pll": ("lacrosse", "pll"),
    # Aussie Rules
    "aussierules_afl": ("australian-football", "afl"),
    # College Baseball
    "baseball_ncaa": ("baseball", "college-baseball"),
    # UFL
    "americanfootball_ufl": ("football", "ufl"),
}


# =============================================================================
# 2. ESPN_SPORT_MAPPING — Odds API key → ESPN path string ("sport/league")
# =============================================================================

ESPN_SPORT_MAPPING: dict[str, str] = {
    "basketball_nba": "basketball/nba",
    "basketball_ncaab": "basketball/mens-college-basketball",
    "basketball_wncaab": "basketball/womens-college-basketball",
    "americanfootball_nfl": "football/nfl",
    "americanfootball_ncaaf": "football/college-football",
    "icehockey_nhl": "hockey/nhl",
    "baseball_mlb": "baseball/mlb",
    "baseball_mlb_preseason": "baseball/mlb",
    "soccer_usa_mls": "soccer/usa.1",
    "soccer_epl": "soccer/eng.1",
    # New — match SPORT_LEAGUE_MAP coverage for live sync correction
    "basketball_wnba": "basketball/wnba",
    "americanfootball_cfl": "football/cfl",
    "soccer_uefa_champs_league": "soccer/uefa.champions",
    "golf_pga": "golf/pga",
    "golf_lpga": "golf/lpga",
    # Additional European soccer leagues
    "soccer_spain_la_liga": "soccer/esp.1",
    "soccer_germany_bundesliga": "soccer/ger.1",
    "soccer_italy_serie_a": "soccer/ita.1",
    "soccer_france_ligue_one": "soccer/fra.1",
    # Lacrosse
    "lacrosse_ncaa": "lacrosse/mens-college-lacrosse",
    "lacrosse_pll": "lacrosse/pll",
    # MMA
    "mma_mixed_martial_arts": "mma/ufc",
    # Aussie Rules
    "aussierules_afl": "australian-football/afl",
    # College Baseball
    "baseball_ncaa": "baseball/college-baseball",
    # UFL
    "americanfootball_ufl": "football/ufl",
}


# =============================================================================
# 3. STATPAL_SPORT_MAPPING — Odds API key → StatPal identifier
# =============================================================================

STATPAL_SPORT_MAPPING: dict[str, str] = {
    "americanfootball_nfl": "nfl",
    "basketball_nba": "nba",
    "baseball_mlb": "mlb",
    "icehockey_nhl": "nhl",
    "soccer_epl": "soccer",
    "soccer_usa_mls": "soccer",
    "golf_pga": "pga",
    # Note: StatPal does NOT cover college sports (NCAAB, NCAAF) or WNBA.
    # Their API only supports 13 pro/international sports:
    # NFL, NBA, MLB, NHL, soccer, golf, cricket, esports, F1, handball,
    # horse racing, tennis, volleyball. College sports rely on
    # The Odds API + ESPN for event creation and commence_time correction.
    # More soccer leagues (StatPal uses sport="soccer" for all)
    "soccer_spain_la_liga": "soccer",
    "soccer_germany_bundesliga": "soccer",
    "soccer_italy_serie_a": "soccer",
    "soccer_france_ligue_one": "soccer",
    "soccer_uefa_champs_league": "soccer",
    # Tennis (ATP + WTA both use StatPal sport="tennis")
    "tennis_atp": "tennis",
    "tennis_wta": "tennis",
}

# Sports where StatPal actually provides play-by-play data.
# Other sports return 404 for the PBP endpoint — skip them to save API calls.
STATPAL_PBP_SPORTS: set[str] = {"nfl"}


# =============================================================================
# 4. ODDS_API_TO_WIN_PROB_KEY — Odds API key → win-prob model key
# =============================================================================

ODDS_API_TO_WIN_PROB_KEY: dict[str, str] = {
    "americanfootball_nfl": "football_nfl",
    "americanfootball_ncaaf": "football_ncaaf",
    "icehockey_nhl": "hockey_nhl",
}


# =============================================================================
# 5. SPORT_PREFIX_TO_LLM_CATEGORY — sport key prefix → LLM category
# =============================================================================

SPORT_PREFIX_TO_LLM_CATEGORY: dict[str, str] = {
    "americanfootball": "football",
    "basketball": "basketball",
    "icehockey": "hockey",
    "baseball": "baseball",
    "soccer": "soccer",
    "mma": "mma",
    "golf": "golf",
    "tennis": "tennis",
    "cricket": "cricket",
    "rugby": "rugby",
    "boxing": "boxing",
}


# =============================================================================
# 6. LLM_CATEGORY_TO_SPORT_PREFIX — LLM category → sport key prefix
# =============================================================================

LLM_CATEGORY_TO_SPORT_PREFIX: dict[str, str] = {
    "basketball": "basketball",
    "football": "americanfootball",
    "soccer": "soccer",
    "hockey": "icehockey",
    "baseball": "baseball",
    "golf": "golf",
    "tennis": "tennis",
    "mma": "mma",
    "boxing": "boxing",
    "cricket": "cricket",
    "rugby": "rugby",
    "motorsports": "motorsport",
    "lacrosse": "lacrosse",
    "esports": "esports",
    "aussierules": "aussierules",
    "olympics": "olympics",
}


# =============================================================================
# 7. KALSHI_TICKER_TO_SPORT_KEY — Kalshi ticker prefix → Odds API sport key
# =============================================================================

KALSHI_TICKER_TO_SPORT_KEY: dict[str, str] = {
    # Major US sports
    "kxnbagame": "basketball_nba",
    "kxnflgame": "americanfootball_nfl",
    "kxnhlgame": "icehockey_nhl",
    "kxmlbgame": "baseball_mlb",
    "kxwnbagame": "basketball_wnba",
    "kxmlsgame": "soccer_usa_mls",
    # College sports — men's
    "kxncaabgame": "basketball_ncaab",
    "kxncaabbgame": "basketball_ncaab",       # NIT/CBI/CIT post-season
    "kxncaamb1hwinner": "basketball_ncaab",   # 1st half winner markets
    "kxncaafgame": "americanfootball_ncaaf",
    "kxncaamlaxgame": "lacrosse_ncaa",
    "kxncaahockeygame": "icehockey_ncaa",
    # College sports — women's
    "kxncaawbgame": "basketball_wncaab",
    # Hockey leagues
    "kxahlgame": "icehockey_ahl",
    "kxkhlgame": "icehockey_other",
    "kxdelgame": "icehockey_other",           # DEL (German hockey)
    # Tennis
    "kxatpmatch": "tennis_atp",
    "kxatpchallengermatch": "tennis_atp",
    "kxatpsetwinner": "tennis_atp",
    "kxwtamatch": "tennis_wta",
    # Combat sports
    "kxufcfight": "mma_mixed_martial_arts",
    "kxboxingfight": "boxing_boxing",
    # Esports
    "kxlolgame": "esports",
    "kxcs2game": "esports",
    "kxvalorantgame": "esports",
    "kxdimayorgame": "esports",               # Dota 2 DPC
    # Soccer
    "kxsoccergame": "soccer",
    "kxeculpgame": "soccer_other",            # Ecuadorian league
    "kxvenfutvegame": "soccer_other",         # Venezuelan league
    "kxapfddhgame": "soccer_other",           # Dominican league
    # Asian basketball
    "kxcbagame": "basketball_other",          # Chinese CBA
    "kxjbleaguegame": "basketball_other",     # Japanese B.League
    "kxarglnbgame": "basketball_other",       # Argentine LNB
    # Winter Olympics
    "kxwohockey": "icehockey_olympics",
    "kxwocurling": "curling_olympics",
    # Summer Olympics
    "kxsohockey": "fieldhockey_olympics",
    "kxsobasketball": "basketball_olympics",
    "kxsosoccer": "soccer_olympics",
}


# =============================================================================
# 8. KALSHI_GAME_TICKER_PREFIXES — tuple of Kalshi game ticker prefixes
# =============================================================================

KALSHI_GAME_TICKER_PREFIXES: tuple[str, ...] = tuple(KALSHI_TICKER_TO_SPORT_KEY.keys())


# =============================================================================
# 9. KALSHI_TICKER_TO_DISPLAY_LABEL — Kalshi ticker prefix → display label
# =============================================================================

KALSHI_TICKER_TO_DISPLAY_LABEL: dict[str, str] = {
    "kxnbagame": "NBA",
    "kxnflgame": "NFL",
    "kxnhlgame": "NHL",
    "kxmlbgame": "MLB",
    "kxncaabgame": "NCAAB",
    "kxncaabbgame": "NCAAB",
    "kxncaamb1hwinner": "NCAAB",
    "kxncaawbgame": "WNCAAB",
    "kxncaafgame": "NCAAF",
    "kxncaamlaxgame": "NCAA Lax",
    "kxncaahockeygame": "NCAA Hockey",
    "kxwnbagame": "WNBA",
    "kxmlsgame": "MLS",
    "kxahlgame": "AHL",
    "kxkhlgame": "KHL",
    "kxdelgame": "DEL",
    "kxsoccergame": "Soccer",
    "kxufcfight": "UFC",
    "kxboxingfight": "Boxing",
    "kxlolgame": "LoL",
    "kxcs2game": "CS2",
    "kxvalorantgame": "Valorant",
    "kxdimayorgame": "Dota 2",
    "kxatpmatch": "ATP",
    "kxatpchallengermatch": "ATP Challenger",
    "kxatpsetwinner": "ATP",
    "kxwtamatch": "WTA",
}


# =============================================================================
# 10. LLM_CATEGORY_TO_SPORT_KEYS — LLM category → list of full sport keys
# =============================================================================

LLM_CATEGORY_TO_SPORT_KEYS: dict[str, list[str]] = {
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


# =============================================================================
# Accessor functions
# =============================================================================

def get_espn_path(sport_key: str) -> Optional[tuple[str, str]]:
    """Look up the ESPN (sport, league) tuple for an Odds API sport key."""
    return SPORT_LEAGUE_MAP.get(sport_key)


def normalize_to_win_prob_key(sport_key: str) -> str:
    """Map an Odds API sport key to the canonical win-prob model key.

    Returns the key unchanged if no alias exists (passthrough).
    """
    return ODDS_API_TO_WIN_PROB_KEY.get(sport_key, sport_key)


def get_sport_prefix_for_category(llm_category: str) -> Optional[str]:
    """Map an LLM sport category to an Odds API sport key prefix."""
    return LLM_CATEGORY_TO_SPORT_PREFIX.get(llm_category)


def get_sport_key_from_ticker(external_id: str) -> Optional[str]:
    """Get the Odds API sport key for a Kalshi game ticker.

    Returns a sport key (e.g., ``"basketball_nba"``) or ``None``.
    """
    if not external_id:
        return None
    ext_lower = external_id.lower()
    for prefix, sport in KALSHI_TICKER_TO_SPORT_KEY.items():
        if ext_lower.startswith(prefix):
            return sport
    return None


def is_kalshi_game_ticker(external_id: str) -> bool:
    """Check whether a Kalshi ``external_id`` is a game-level ticker."""
    if not external_id:
        return False
    ext_lower = external_id.lower()
    return any(ext_lower.startswith(prefix) for prefix in KALSHI_GAME_TICKER_PREFIXES)


def get_sport_keys_for_category(category: Optional[str]) -> Optional[list[str]]:
    """Get sport keys to scope team search for a given sport category.

    Returns ``None`` if category is unknown (search all teams).
    """
    if not category:
        return None
    return LLM_CATEGORY_TO_SPORT_KEYS.get(category.lower())


def get_llm_category_for_prefix(sport_prefix: str) -> str:
    """Map a sport key prefix to its LLM category.

    Falls back to the prefix itself if no mapping exists.
    """
    return SPORT_PREFIX_TO_LLM_CATEGORY.get(sport_prefix, sport_prefix)
