"""
Event taxonomy — deterministic tag computation for events and futures.

Produces a flat array of namespaced tags (e.g., ["sport:basketball", "tier:1", ...])
from existing event data.  Pure functions, no DB, no async, no LLM cost.

Tags are queryable via GIN index: WHERE event_tags @> '["tier:1", "sport:basketball"]'
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.utils.highlights import LEAGUE_TIERS, EventFlags, HighlightResult
from app.utils.league_classification import LEAGUE_CLASS
from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY


# ── Controlled vocabulary per namespace ──────────────────────────────

ALLOWED_TAGS: dict[str, set[str]] = {
    "sport": {
        "basketball", "football", "baseball", "hockey", "soccer",
        "mma", "golf", "tennis", "cricket", "rugby", "boxing",
        "aussierules", "lacrosse", "motorsports", "horse_racing",
        "esports", "olympics",
        # Non-sports categories supported by futures
        "entertainment", "politics", "poker", "chess", "darts",
    },
    "league": {
        "nba", "nfl", "mlb", "nhl",
        "ncaab", "ncaaf", "wncaab", "wnba",
        "epl", "la_liga", "mls", "bundesliga", "serie_a",
        "ligue_1", "champions_league", "europa_league",
        "liga_mx", "brazilian_serie_a",
        "ufc", "pga",
        "afl", "nrl", "six_nations",
        "euroleague",
        "cfl", "xfl", "ufl", "ahl",
        "us_open", "french_open", "wimbledon", "australian_open",
        "masters", "pga_championship", "us_open_golf", "the_open",
        "fifa_world_cup",
        "t20_world_cup", "icc_world_cup",
        # Additional leagues from LEAGUE_TIERS
        "boxing", "copa_libertadores", "eredivisie", "primeira_liga",
        "efl_champ", "fa_cup", "europa_conference",
        "international_t20", "test_match", "olympics",
        "nbl", "league1", "league2",
        "liiga", "shl", "allsvenskan",
    },
    "tier": {"1", "2", "3", "4"},
    "class": {"pro_major", "pro_minor", "college", "international", "other"},
    "level": {"professional", "college", "amateur", "youth"},
    "gender": {"men", "women", "mixed"},
    "importance": {"championship", "playoff", "regular_season", "exhibition"},
    "status": {"scheduled", "live", "completed", "closed"},
    "signal": {
        "close_matchup", "very_close", "upset", "favorite_switched",
        "line_moving", "volatile", "lead_changes", "momentum",
        "blowout", "starting_soon",
    },
    "timing": {"weekend", "primetime", "national_tv"},
    "ei": {
        "incredible", "must_watch", "exciting", "engaging",
        "competitive", "average", "quiet", "flat",
    },
    # Futures-specific namespaces
    "category": {
        "championship", "conference", "division", "mvp",
        "awards", "prop", "game_prop", "other",
    },
    "source": {"odds_api", "kalshi", "polymarket"},
    "market_status": {"open", "suspended", "resolved"},
}

# ── Sport key → league mapping ───────────────────────────────────────

_SPORT_KEY_TO_LEAGUE: dict[str, str] = {
    "basketball_nba": "nba",
    "basketball_wnba": "wnba",
    "basketball_ncaab": "ncaab",
    "basketball_wncaab": "wncaab",
    "basketball_euroleague": "euroleague",
    "basketball_nbl": "nbl",
    "americanfootball_nfl": "nfl",
    "americanfootball_ncaaf": "ncaaf",
    "americanfootball_cfl": "cfl",
    "americanfootball_xfl": "xfl",
    "americanfootball_ufl": "ufl",
    "baseball_mlb": "mlb",
    "baseball_mlb_preseason": "mlb",
    "icehockey_nhl": "nhl",
    "icehockey_ahl": "ahl",
    "icehockey_liiga": "liiga",
    "icehockey_sweden_hockey_league": "shl",
    "icehockey_sweden_allsvenskan": "allsvenskan",
    "soccer_epl": "epl",
    "soccer_spain_la_liga": "la_liga",
    "soccer_usa_mls": "mls",
    "soccer_germany_bundesliga": "bundesliga",
    "soccer_italy_serie_a": "serie_a",
    "soccer_france_ligue_one": "ligue_1",
    "soccer_uefa_champs_league": "champions_league",
    "soccer_uefa_europa_league": "europa_league",
    "soccer_uefa_europa_conference_league": "europa_conference",
    "soccer_mexico_ligamx": "liga_mx",
    "soccer_brazil_serie_a": "brazilian_serie_a",
    "soccer_brazil_campeonato": "brazilian_serie_a",
    "soccer_fifa_world_cup": "fifa_world_cup",
    "soccer_conmebol_copa_libertadores": "copa_libertadores",
    "soccer_netherlands_eredivisie": "eredivisie",
    "soccer_portugal_primeira_liga": "primeira_liga",
    "soccer_efl_champ": "efl_champ",
    "soccer_fa_cup": "fa_cup",
    "soccer_england_league1": "league1",
    "soccer_england_league2": "league2",
    "mma_mixed_martial_arts": "ufc",
    "boxing_boxing": "boxing",
    "rugby_nrl": "nrl",
    "rugbyleague_nrl": "nrl",
    "rugbyunion_six_nations": "six_nations",
    "aussierules_afl": "afl",
    "cricket_t20_world_cup": "t20_world_cup",
    "cricket_icc_world_cup": "icc_world_cup",
    "cricket_international_t20": "international_t20",
    "cricket_test_match": "test_match",
    # Olympics
    "icehockey_olympics": "olympics",
    "basketball_olympics": "olympics",
    "soccer_olympics": "olympics",
    "fieldhockey_olympics": "olympics",
    "curling_olympics": "olympics",
    # Tennis Grand Slams
    "tennis_us_open": "us_open",
    "tennis_french_open": "french_open",
    "tennis_wimbledon": "wimbledon",
    "tennis_australian_open": "australian_open",
    "tennis_atp_aus_open_singles": "australian_open",
    "tennis_wta_aus_open_singles": "australian_open",
    # Golf Majors
    "golf_masters_tournament_winner": "masters",
    "golf_pga_championship_winner": "pga_championship",
    "golf_us_open_winner": "us_open_golf",
    "golf_the_open_championship_winner": "the_open",
    "golf_pga": "pga",
}

# National TV network patterns (case-insensitive)
_NATIONAL_TV_RE = re.compile(
    r"\b(ESPN|ABC|FOX|CBS|NBC|TNT|TBS|FS1|NFL\s*Network|NBA\s*TV|NHL\s*Network|MLB\s*Network)\b"
    r"|ESPN\+|Amazon|Prime\s*Video|Peacock|Apple\s*TV|Paramount\+",
    re.IGNORECASE,
)

# Extra sport key prefixes not covered by SPORT_PREFIX_TO_LLM_CATEGORY
_EXTRA_SPORT_PREFIXES: dict[str, str] = {
    "aussierules": "aussierules",
    "lacrosse": "lacrosse",
    "motorsport": "motorsports",
    "horseracing": "horse_racing",
    "esports": "esports",
    "fieldhockey": "hockey",
    "curling": "olympics",
}


# ── EI label thresholds ──────────────────────────────────────────────

def _ei_label(score: int) -> str:
    """Map EI score (1-100) to a tag value."""
    if score >= 90:
        return "incredible"
    if score >= 80:
        return "must_watch"
    if score >= 70:
        return "exciting"
    if score >= 60:
        return "engaging"
    if score >= 50:
        return "competitive"
    if score >= 40:
        return "average"
    if score >= 25:
        return "quiet"
    return "flat"


# ── Validation ────────────────────────────────────────────────────────

def validate_tag(tag: str) -> bool:
    """Check that a tag follows namespace:value format and is in the vocabulary."""
    parts = tag.split(":", 1)
    if len(parts) != 2:
        return False
    namespace, value = parts
    allowed = ALLOWED_TAGS.get(namespace)
    if allowed is None:
        return False
    return value in allowed


# ── Main function (events) ───────────────────────────────────────────

def compute_event_tags(
    sport_key: str,
    status: str,
    commence_time: datetime,
    llm_importance: Optional[str] = None,
    llm_gender: Optional[str] = None,
    llm_level: Optional[str] = None,
    llm_league: Optional[str] = None,
    raw_ei: Optional[float] = None,
    broadcast_info: Optional[str] = None,
    highlight_result: Optional[HighlightResult] = None,
) -> list[str]:
    """Compute deterministic tags for an event.

    Returns a sorted, deduplicated list of namespace:value strings.
    Each tag is validated against ALLOWED_TAGS before inclusion.
    """
    tags: set[str] = set()

    # ── sport ──
    sport_tag = _extract_sport(sport_key)
    if sport_tag:
        tags.add(f"sport:{sport_tag}")

    # ── league ──
    league_tag = _extract_league(sport_key, llm_league)
    if league_tag:
        tags.add(f"league:{league_tag}")

    # ── tier ──
    tier = LEAGUE_TIERS.get(sport_key, 4)
    tags.add(f"tier:{tier}")

    # ── class ──
    league_class = LEAGUE_CLASS.get(sport_key, "other")
    tags.add(f"class:{league_class}")

    # ── level ──
    if llm_level and llm_level in ALLOWED_TAGS["level"]:
        tags.add(f"level:{llm_level}")

    # ── gender ──
    if llm_gender and llm_gender in ALLOWED_TAGS["gender"]:
        tags.add(f"gender:{llm_gender}")

    # ── importance ──
    if llm_importance and llm_importance in ALLOWED_TAGS["importance"]:
        tags.add(f"importance:{llm_importance}")

    # ── status ──
    if status in ALLOWED_TAGS["status"]:
        tags.add(f"status:{status}")

    # ── signals from highlight_result ──
    if highlight_result:
        _extract_signals(highlight_result.flags, tags)

    # ── timing ──
    _extract_timing(commence_time, broadcast_info, tags)

    # ── ei ──
    if raw_ei is not None:
        ei_score = max(1, min(100, round(float(raw_ei) * 100)))
        label = _ei_label(ei_score)
        tags.add(f"ei:{label}")

    # Validate all tags against vocabulary and return sorted
    return sorted(t for t in tags if validate_tag(t))


# ── Main function (futures markets) ──────────────────────────────────

# Market tier → category mapping
_TIER_TO_CATEGORY: dict[int, str] = {
    1: "championship",
    2: "conference",
    3: "awards",
    4: "division",
    5: "prop",
}


def compute_market_tags(
    llm_sport_category: Optional[str] = None,
    llm_league: Optional[str] = None,
    llm_gender: Optional[str] = None,
    llm_level: Optional[str] = None,
    market_tier: Optional[int] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    resolution_date: Optional[datetime] = None,
    source: Optional[str] = None,
) -> list[str]:
    """Compute deterministic tags for a futures market.

    Returns a sorted, deduplicated list of namespace:value strings.
    Each tag is validated against ALLOWED_TAGS before inclusion.
    """
    tags: set[str] = set()

    # ── sport ──
    if llm_sport_category and llm_sport_category in ALLOWED_TAGS["sport"]:
        tags.add(f"sport:{llm_sport_category}")

    # ── league ──
    if llm_league:
        normalized = llm_league.lower().replace(" ", "_")
        if normalized in ALLOWED_TAGS["league"]:
            tags.add(f"league:{normalized}")

    # ── tier ──
    if market_tier is not None and str(market_tier) in ALLOWED_TAGS["tier"]:
        tags.add(f"tier:{market_tier}")

    # ── category ──
    if category and category in ALLOWED_TAGS["category"]:
        tags.add(f"category:{category}")
    elif market_tier is not None:
        cat = _TIER_TO_CATEGORY.get(market_tier)
        if cat and cat in ALLOWED_TAGS["category"]:
            tags.add(f"category:{cat}")

    # ── level ──
    if llm_level and llm_level in ALLOWED_TAGS["level"]:
        tags.add(f"level:{llm_level}")

    # ── gender ──
    if llm_gender and llm_gender in ALLOWED_TAGS["gender"]:
        tags.add(f"gender:{llm_gender}")

    # ── market_status ──
    if status and status in ALLOWED_TAGS["market_status"]:
        tags.add(f"market_status:{status}")

    # ── source ──
    if source and source in ALLOWED_TAGS["source"]:
        tags.add(f"source:{source}")

    # Validate all tags against vocabulary and return sorted
    return sorted(t for t in tags if validate_tag(t))


# ── Helpers ───────────────────────────────────────────────────────────

def _extract_sport(sport_key: str) -> Optional[str]:
    """Extract sport category from sport_key prefix."""
    if not sport_key:
        return None
    prefix = sport_key.split("_")[0] if "_" in sport_key else sport_key
    # Handle special prefixes
    if prefix == "rugbyleague" or prefix == "rugbyunion":
        prefix = "rugby"
    sport = SPORT_PREFIX_TO_LLM_CATEGORY.get(prefix)
    if sport and sport in ALLOWED_TAGS["sport"]:
        return sport
    # Fallback for prefixes not in SPORT_PREFIX_TO_LLM_CATEGORY
    sport = _EXTRA_SPORT_PREFIXES.get(prefix)
    if sport and sport in ALLOWED_TAGS["sport"]:
        return sport
    return None


def _extract_league(sport_key: str, llm_league: Optional[str]) -> Optional[str]:
    """Extract league tag. Prefers llm_league if it maps; falls back to sport_key lookup."""
    # Try llm_league first (normalized to lowercase with underscores)
    if llm_league:
        normalized = llm_league.lower().replace(" ", "_")
        if normalized in ALLOWED_TAGS["league"]:
            return normalized

    # Fall back to sport_key mapping
    league = _SPORT_KEY_TO_LEAGUE.get(sport_key)
    if league and league in ALLOWED_TAGS["league"]:
        return league
    return None


def _extract_signals(flags: EventFlags, tags: set[str]) -> None:
    """Map EventFlags to signal tags."""
    if flags.is_close_matchup:
        tags.add("signal:close_matchup")
    if flags.is_very_close:
        tags.add("signal:very_close")
    if flags.is_upset:
        tags.add("signal:upset")
    if flags.favorite_switched:
        tags.add("signal:favorite_switched")
    if flags.probability_swing == "major":
        tags.add("signal:line_moving")
    if flags.is_volatile:
        tags.add("signal:volatile")
    if flags.has_lead_changes:
        tags.add("signal:lead_changes")
    if flags.has_recent_momentum:
        tags.add("signal:momentum")
    if flags.is_blowout:
        tags.add("signal:blowout")
    if flags.is_starting_soon:
        tags.add("signal:starting_soon")


def _extract_timing(
    commence_time: datetime,
    broadcast_info: Optional[str],
    tags: set[str],
) -> None:
    """Extract timing tags from commence_time and broadcast_info."""
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)

    # Convert to US Eastern (UTC-5 approximation — no pytz dependency)
    eastern_offset = timedelta(hours=-5)
    eastern_time = commence_time + eastern_offset

    # Weekend: Saturday or Sunday
    if eastern_time.weekday() in (5, 6):
        tags.add("timing:weekend")

    # Primetime: 19:00-23:59 Eastern
    if 19 <= eastern_time.hour <= 23:
        tags.add("timing:primetime")

    # National TV
    if broadcast_info and _NATIONAL_TV_RE.search(broadcast_info):
        tags.add("timing:national_tv")
