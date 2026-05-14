"""League-scoped futures endpoint.

Returns all open futures markets for a specific league, grouped by section
(series, awards, props, season_stats, more_markets). Powers the league
page's below-the-grid sections.

Phase 3 generalizes the sectioned layout to all major sports (NBA, NHL, MLB, NFL)
with sport-aware keyword classification for awards, series, and props.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Path
from sqlalchemy import select, and_, or_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket, FuturesOutcome, Sport
from app.services import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# Sport key → league name patterns for filtering (case-insensitive SQL ILIKE).
# Markets matching ANY pattern are included for that league.
LEAGUE_NAME_PATTERNS: dict[str, list[str]] = {
    "basketball_nba": ["NBA%", "%National Basketball%"],
    "basketball_wnba": ["WNBA%", "%Women_s National Basketball%"],
    "basketball_ncaab": ["%NCAA%Basketball%", "%March Madness%", "%College Basketball%"],
    "icehockey_nhl": ["NHL%", "%National Hockey%", "%Stanley Cup%"],
    "baseball_mlb": ["MLB%", "%Major League Baseball%", "%World Series%"],
    "americanfootball_nfl": ["NFL%", "%National Football%", "%Super Bowl%"],
    "americanfootball_ncaaf": ["%NCAA%Football%", "%College Football%", "%CFP%"],
    "soccer_epl": ["%Premier League%", "%EPL%"],
    "soccer_usa_mls": ["%MLS%", "%Major League Soccer%"],
}

# Sport key → Kalshi external_id prefix for precise filtering
LEAGUE_TICKER_PREFIXES: dict[str, list[str]] = {
    "basketball_nba": ["KXNBA"],
    "basketball_wnba": ["KXWNBA"],
    "basketball_ncaab": ["KXNCAAB", "KXMM"],
    "icehockey_nhl": ["KXNHL"],
    "baseball_mlb": ["KXMLB"],
    "americanfootball_nfl": ["KXNFL"],
    "americanfootball_ncaaf": ["KXNCAAF", "KXCFP"],
    "soccer_epl": ["KXEPL"],
}

# ---------------------------------------------------------------------------
# Section assignment: sport-aware classification
# ---------------------------------------------------------------------------
# Target sections (matching frontend expectations):
#   series       — Playoff series matchups (Team A vs Team B, total games O/U)
#   awards       — MVP, ROY, Cy Young, Vezina, Selke, etc.
#   props        — Team-level props (win totals, div winners, playoff quals,
#                  trades, no-hitters, draft, Madden cover, etc.)
#   season_stats — Player stat-based markets (scoring leader, HR leader, etc.)
#   more_markets — Everything else
# ---------------------------------------------------------------------------

# Sport-specific award name fragments (matched case-insensitively).
# Generic awards ("MVP", "Rookie of the Year") are caught by tier == 3.
_AWARD_KEYWORDS: list[str] = [
    # NBA
    "defensive player of the year", "sixth man", "most improved",
    "clutch player", "finals mvp",
    # NHL
    "vezina", "selke", "norris", "conn smythe", "hart", "calder",
    "richard trophy", "art ross", "jack adams", "lady byng",
    # MLB
    "cy young", "hank aaron", "gold glove", "silver slugger",
    "reliever of the year", "manager of the year", "rookie of the year",
    # NFL
    "comeback player", "offensive player of the year",
    "defensive player of the year", "walter payton",
    "offensive rookie", "defensive rookie", "coach of the year",
]

# Keywords that identify a market as a playoff series matchup.
_SERIES_KEYWORDS: list[str] = [
    "series", "total games o/u", "total games over",
]

# Keywords for team/season-level props (not player stats).
_PROPS_KEYWORDS: list[str] = [
    "win total", "win more than", "win 100", "win 90", "win 80",
    "division winner", "make playoff", "clinch",
    "postseason", "wild card",
    "traded", "be traded", "trade",
    "no-hitter", "perfect game",
    "draft", "lottery",
    "cover of madden", "madden nfl",
    "debut date", "free agent",
    "sweep", "game 7", "playoff win total", "elimination",
    "fired", "general manager", "head coach",
]

# Keywords for player-stat markets (season stats section).
_SEASON_STAT_KEYWORDS: list[str] = [
    "leader", "scoring title", "assists title", "rebounds title",
    "home run leader", "batting average", "era leader", "strikeout leader",
    "rushing leader", "passing leader", "receiving leader",
    "goal leader", "points leader", "save leader",
    "regular season record", "regular season wins",
]


def _assign_section(market: FuturesMarket, sport_key: str = "") -> str:
    """Assign a market to a display section.

    Uses sport-aware keyword matching to classify into one of five sections:
    series, awards, props, season_stats, more_markets.
    """
    name_lower = (market.name or "").lower()
    cat = (market.category or "").lower()
    tier = market.market_tier

    # Championship / conference / division (tier 1-2, 4) — already on grid
    if tier in (1, 2):
        return "championship"
    if tier == 4:
        return "championship"

    # --- Series markets ---
    # "vs" in a tier-5 market is almost always a series matchup.
    # Also catch "Total Games O/U" which is a series-length bet.
    if any(kw in name_lower for kw in _SERIES_KEYWORDS):
        # Exception: "World Series Winner" is a championship, not a series
        if "world series winner" in name_lower:
            return "championship"
        return "series"
    if " vs " in name_lower or " vs. " in name_lower:
        # Tier-5 matchup = series (e.g., "Bruins vs. Sabres")
        if tier == 5:
            return "series"

    # --- Awards ---
    # Tier 3 = award by definition. Also match known award name fragments.
    if tier == 3 or cat in ("award", "mvp"):
        return "awards"
    if any(kw in name_lower for kw in _AWARD_KEYWORDS):
        return "awards"

    # --- Season stats (player-level) ---
    # Check before props because "leader" could overlap with "win total" props.
    if cat == "season_stat" or any(kw in name_lower for kw in _SEASON_STAT_KEYWORDS):
        return "season_stats"

    # --- Props (team/season-level) ---
    if any(kw in name_lower for kw in _PROPS_KEYWORDS):
        return "props"

    return "more_markets"


@router.get("/{sport_key}")
async def get_league_futures(
    sport_key: str = Path(..., description="Sport key (e.g., basketball_nba, icehockey_nhl)"),
    db: AsyncSession = Depends(get_db),
):
    """Get all open futures markets for a league, grouped by section."""
    now = datetime.now(timezone.utc)

    # Determine the sport category from the key
    # e.g., basketball_nba → llm_sport_category = "basketball"
    sport_category = sport_key.split("_")[0]
    # Map common prefixes
    if sport_category == "americanfootball":
        sport_category = "football"
    elif sport_category == "icehockey":
        sport_category = "hockey"

    # Build query filters
    filters = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= now,
        ),
        FuturesMarket.llm_sport_category == sport_category,
    ]

    # League-level filtering: use ticker prefix (Kalshi) + name patterns
    league_conditions = []
    ticker_prefixes = LEAGUE_TICKER_PREFIXES.get(sport_key, [])
    for prefix in ticker_prefixes:
        league_conditions.append(FuturesMarket.external_id.ilike(f"{prefix}%"))

    name_patterns = LEAGUE_NAME_PATTERNS.get(sport_key, [])
    for pattern in name_patterns:
        league_conditions.append(FuturesMarket.name.ilike(pattern))

    # Also match llm_league if set
    league_short = sport_key.split("_", 1)[1] if "_" in sport_key else sport_key
    league_conditions.append(FuturesMarket.llm_league.ilike(league_short))

    if league_conditions:
        filters.append(or_(*league_conditions))

    # Exclude game-level matchup markets (vs patterns)
    filters.append(~FuturesMarket.name.ilike("% at %"))

    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(*filters)
        .order_by(FuturesMarket.market_tier.asc().nulls_last())
        .limit(200)
    )

    result = await db.execute(query)
    markets = list(result.scalars().unique().all())

    # Group by section + deduplicate by canonical_market_key
    sections: dict[str, list[dict]] = {
        "series": [],
        "awards": [],
        "props": [],
        "season_stats": [],
        "more_markets": [],
    }

    seen_canonical: dict[str, dict] = {}

    for market in markets:
        section = _assign_section(market, sport_key)

        # Skip championship/conference/division — already on the grid
        if section == "championship":
            continue

        # Sort outcomes by probability descending
        sorted_outcomes = sorted(
            market.outcomes,
            key=lambda o: float(o.current_probability) if o.current_probability else 0,
            reverse=True,
        )

        # Skip effectively resolved markets (leader ≥97% and opened ≥85%)
        if sorted_outcomes:
            leader_prob = float(sorted_outcomes[0].current_probability) if sorted_outcomes[0].current_probability else 0
            if leader_prob >= 0.97:
                leader_opening = float(sorted_outcomes[0].opening_probability) if sorted_outcomes[0].opening_probability else None
                if leader_opening is not None and leader_opening >= 0.85:
                    continue
            # All-settled filter: skip if every outcome is <3% or >97% (post-season resolved)
            probs = [float(o.current_probability) for o in sorted_outcomes if o.current_probability is not None]
            if len(probs) >= 2 and all(p < 0.03 or p > 0.97 for p in probs):
                continue

        outcomes_data = [
            {
                "id": o.id,
                "name": o.name,
                "probability": float(o.current_probability) if o.current_probability else None,
                "opening_probability": float(o.opening_probability) if o.opening_probability else None,
                "rank": o.rank,
                "movement_24h": float(o.probability_change_24h) if o.probability_change_24h else None,
                "team_id": o.team_id,
            }
            for o in sorted_outcomes[:10]
        ]

        market_data = {
            "id": market.id,
            "name": market.name,
            "source": market.source,
            "market_tier": market.market_tier,
            "category": market.category,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
            "outcome_count": len(market.outcomes),
            "top_outcomes": outcomes_data,
            "canonical_market_key": market.canonical_market_key,
            "section": section,
        }

        # Deduplicate by canonical key (keep highest-tier / most outcomes)
        ck = market.canonical_market_key
        if ck:
            if ck in seen_canonical:
                existing = seen_canonical[ck]
                if len(outcomes_data) > len(existing["top_outcomes"]):
                    # Remove old from its section
                    old_section = existing["section"]
                    sections[old_section] = [m for m in sections[old_section] if m.get("canonical_market_key") != ck]
                    seen_canonical[ck] = market_data
                else:
                    continue
            else:
                seen_canonical[ck] = market_data

        sections[section].append(market_data)

    # Sort within each section by market importance
    for section_name, items in sections.items():
        items.sort(key=lambda m: (
            -(m.get("market_tier") or 99),
            -(m.get("outcome_count") or 0),
        ))

    # Remove empty sections
    sections = {k: v for k, v in sections.items() if v}

    return {
        "sport_key": sport_key,
        "sections": sections,
        "total_markets": sum(len(v) for v in sections.values()),
    }
