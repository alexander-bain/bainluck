"""League-scoped futures endpoint.

Returns all open futures markets for a specific league, grouped by section
(series, awards, playoff_props, season_stats, novelty). Powers the league
page's below-the-grid sections.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

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

# Section assignment based on market_tier + category + name patterns
SECTION_RULES: list[tuple[str, dict]] = [
    ("series", {"name_patterns": ["%series%", "% vs %"]}),
    ("awards", {"tiers": [3], "categories": ["award", "mvp"]}),
    ("championship", {"tiers": [1, 2]}),
    ("playoff_props", {"tiers": [4, 5], "name_patterns": ["%sweep%", "%game 7%", "%playoff%win%total%"]}),
    ("season_stats", {"categories": ["season_stat"], "name_patterns": ["%leader%", "%win total%", "%record%"]}),
    ("novelty", {}),
]


def _assign_section(market: FuturesMarket) -> str:
    """Assign a market to a display section."""
    name_lower = (market.name or "").lower()
    cat = (market.category or "").lower()
    tier = market.market_tier

    # Series markets
    if "series" in name_lower or (" vs " in name_lower and tier == 5):
        return "series"

    # Awards (tier 3 or award category)
    if tier == 3 or cat in ("award", "mvp"):
        return "awards"

    # Championship / conference (tier 1-2) — already on grid, skip
    if tier in (1, 2):
        return "championship"

    # Playoff props
    playoff_keywords = ["sweep", "game 7", "playoff win total", "elimination"]
    if any(kw in name_lower for kw in playoff_keywords):
        return "playoff_props"

    # Season stats
    stat_keywords = ["leader", "win total", "regular season", "scoring title",
                     "assists title", "rebounds title", "record"]
    if cat == "season_stat" or any(kw in name_lower for kw in stat_keywords):
        return "season_stats"

    # Division (tier 4) — already on grid, skip
    if tier == 4:
        return "championship"

    return "novelty"


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
        "playoff_props": [],
        "season_stats": [],
        "novelty": [],
    }

    seen_canonical: dict[str, dict] = {}

    for market in markets:
        section = _assign_section(market)

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
