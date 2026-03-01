"""
Golf category landing page endpoint.

Aggregates futures market odds across Polymarket, Kalshi, and The Odds API for golf tournaments.
Groups by tournament, merges cross-source golfer odds, and computes biggest movers.
"""

import logging
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket, Event, Sport
from app.services import get_db
from app.utils.odds_math import probability_to_american

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# Market validation — filter out non-golf false positives from LLM
# ============================================================================

# Non-golf terms in market names that indicate LLM miscategorization.
# The LLM sometimes classifies esports "Masters" events, entertainment props,
# and other non-golf markets as golf.
_NON_GOLF_RE = re.compile(
    r"\b(?:"
    # Esports
    r"vct|valorant|league\s+of\s+legends|\blol\b|dota|counter[-\s]?strike|"
    r"\bcs2?\b|esports?|overwatch|call\s+of\s+duty|fortnite|apex\s+legends|"
    r"rocket\s+league|starcraft|hearthstone|"
    # Sports leagues (not golf)
    r"\bnba\b|\bnfl\b|\bnhl\b|\bmlb\b|\bwnba\b|\bmls\b|\bufc\b|\bmma\b|"
    r"\bepl\b|la\s+liga|serie\s+a|\bbundesliga\b|"
    r"super\s+bowl|world\s+series|stanley\s+cup|"
    # Entertainment
    r"\boscar|emmy|grammy|golden\s+globe|tony\s+award|"
    r"netflix|hulu|disney\+|streaming|tv\s+show|television|"
    r"box\s+office|academy\s+award|"
    r"most[- ]watched|most[- ]streamed|"
    # Politics
    r"election|president(?:ial)?|senate|governor|congress|democrat|republican|"
    r"cabinet|supreme\s+court|"
    # Finance/crypto
    r"bitcoin|ethereum|crypto|stock\s+market|s&p|nasdaq|"
    # Weather
    r"temperature|weather|hurricane|tornado"
    r")\b",
    re.I,
)


def _is_golf_market(market) -> bool:
    """Validate that a market is actually golf-related, not a false positive."""
    source = market.source or ""
    external_id = (market.external_id or "").lower()
    name = market.name or ""

    # Odds API markets: trust the sport key prefix
    if source == "odds_api":
        return external_id.startswith("golf_")

    # For Kalshi/Polymarket: reject markets with clear non-golf signals
    if _NON_GOLF_RE.search(name):
        return False

    return True


# ============================================================================
# Tournament classification
# ============================================================================

# Order matters: more specific patterns first
_TOURNAMENT_PATTERNS = [
    (re.compile(r"(?:the\s+)?masters(?:\s+(?:tournament|golf|winner|champion))?(?!\s+(?:tour|bangkok|shanghai|madrid|tokyo|reykjavik|copenhagen))", re.I), "masters"),
    (re.compile(r"pga\s+championship", re.I), "pga_championship"),
    (re.compile(r"us\s+open|u\.s\.\s+open", re.I), "us_open"),
    (re.compile(r"open\s+championship|british\s+open|the\s+open\b", re.I), "the_open"),
    (re.compile(r"players\s+championship", re.I), "players"),
    (re.compile(r"ryder\s+cup", re.I), "ryder_cup"),
    (re.compile(r"presidents?\s+cup", re.I), "presidents_cup"),
    (re.compile(r"liv\s+golf", re.I), "liv"),
]

TOURNAMENT_DISPLAY_NAMES = {
    "masters": "The Masters",
    "pga_championship": "PGA Championship",
    "us_open": "U.S. Open",
    "the_open": "The Open Championship",
    "players": "The Players Championship",
    "ryder_cup": "Ryder Cup",
    "presidents_cup": "Presidents Cup",
    "liv": "LIV Golf",
    "other": "Other Tournaments",
}

MAJOR_TOURNAMENTS = {"masters", "pga_championship", "us_open", "the_open"}

TOURNAMENT_ORDER = [
    "masters", "pga_championship", "us_open", "the_open",
    "players", "ryder_cup", "presidents_cup", "liv", "other",
]

# Max golfers to return per tournament
_MAX_GOLFERS = 15


def _strip_diacritics(s: str) -> str:
    """Remove accent marks: e->e, a->a, u->u, etc."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _normalize_golfer_name(name: str) -> str:
    """Normalize a golfer name for display."""
    name = name.strip()
    name = re.sub(r"^(Yes|No)\s*[-:]\s*", "", name, flags=re.I)
    # Strip wrapping quotes (Polymarket NegRisk format)
    name = re.sub(r'^"(.*)"$', r"\1", name)
    return name


def _match_key(name: str) -> str:
    """
    Create a matching key from a golfer name for cross-source dedup.
    Strips diacritics, normalizes whitespace.
    """
    clean = _normalize_golfer_name(name)
    clean = re.split(r"\s+[-\u2013]\s+|\s+for\s+", clean, maxsplit=1)[0]
    clean = _strip_diacritics(clean)
    clean = clean.lower()
    clean = re.sub(r"^the\s+", "", clean)
    clean = clean.split(":")[0].strip()
    clean = re.sub(r"[^a-z0-9\s]", "", clean).strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean


def _normalize_tournament(market_name: str) -> str:
    """Extract tournament key from a market name. Returns 'other' if no match."""
    for pattern, key in _TOURNAMENT_PATTERNS:
        if pattern.search(market_name):
            return key
    return "other"


@router.get("")
async def get_golf(
    db: AsyncSession = Depends(get_db),
):
    """
    Get golf tournament futures with aggregated odds across sources.

    Returns tournaments ordered by importance (Majors first), with golfers
    merged across Polymarket, Kalshi, and Odds API sources.
    """
    # Query golf-related futures markets using both sport key and LLM category
    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            or_(
                # Odds API markets with golf_ sport key (authoritative)
                FuturesMarket.external_id.ilike("golf_%"),
                # LLM-classified golf markets (may have false positives)
                FuturesMarket.llm_sport_category == "golf",
            ),
        )
    )

    result = await db.execute(query)
    markets = result.scalars().unique().all()

    # Filter out game-level markets (e.g., "Player A vs Player B" matchups)
    markets = [m for m in markets if " vs " not in m.name.lower() and " vs." not in m.name.lower()]

    # Filter out non-golf false positives (esports, entertainment, politics, etc.)
    markets = [m for m in markets if _is_golf_market(m)]

    logger.info("Golf endpoint: %d markets after filtering", len(markets))

    # Group markets by tournament
    tournament_markets: dict[str, list] = defaultdict(list)

    for market in markets:
        tournament_key = _normalize_tournament(market.name)
        tournament_markets[tournament_key].append(market)

    # Build tournament response with cross-source aggregation
    tournaments = []

    for tourn_key, tourn_markets in tournament_markets.items():
        golfer_data: dict[str, dict] = {}  # match_key -> aggregated data

        market_ids = []
        earliest_commence = None
        latest_resolution = None

        for market in tourn_markets:
            market_ids.append(market.id)
            source = market.source or "unknown"

            # Track tournament timing
            if market.commence_time:
                if earliest_commence is None or market.commence_time < earliest_commence:
                    earliest_commence = market.commence_time
            if market.resolution_date:
                if latest_resolution is None or market.resolution_date > latest_resolution:
                    latest_resolution = market.resolution_date

            for outcome in market.outcomes:
                if outcome.current_probability is None:
                    continue

                prob = float(outcome.current_probability)

                # Skip Kalshi entries at exactly 0.5 — illiquid binary markets
                if source == "kalshi" and prob == 0.5:
                    continue

                # Skip generic outcomes
                raw_name = outcome.name.strip()
                if raw_name.lower() in ("tie", "field", "other", "the field"):
                    continue

                display_name = _normalize_golfer_name(raw_name)
                key = _match_key(raw_name)

                if not key:
                    continue

                if key not in golfer_data:
                    golfer_data[key] = {
                        "name": display_name,
                        "sources": {},
                        "probabilities": [],
                        "movement_24h": None,
                        "opening_probability": None,
                    }

                golfer_data[key]["sources"][source] = round(prob, 3)
                golfer_data[key]["probabilities"].append(prob)

                # Use the 24h movement from whichever source has it
                if outcome.probability_change_24h is not None:
                    existing = golfer_data[key]["movement_24h"]
                    change = float(outcome.probability_change_24h)
                    if existing is None or abs(change) > abs(existing):
                        golfer_data[key]["movement_24h"] = round(change, 4)

                # Track opening probability
                if outcome.opening_probability is not None and golfer_data[key]["opening_probability"] is None:
                    golfer_data[key]["opening_probability"] = round(float(outcome.opening_probability), 3)

        # Compute average probability
        golfers = []
        for data in golfer_data.values():
            avg_prob = sum(data["probabilities"]) / len(data["probabilities"])
            golfers.append({
                "name": data["name"],
                "probability": avg_prob,
                "movement_24h": data["movement_24h"],
                "sources": data["sources"],
                "opening_probability": data["opening_probability"],
            })

        # Sort by probability descending, cap at max
        golfers.sort(key=lambda g: g["probability"], reverse=True)
        golfers = golfers[:_MAX_GOLFERS]

        # Normalize probabilities so they sum to ~100%
        total_prob = sum(g["probability"] for g in golfers)
        if total_prob > 0:
            for g in golfers:
                g["probability"] = round(g["probability"] / total_prob, 3)
                g["american_odds"] = probability_to_american(g["probability"])
        else:
            for g in golfers:
                g["probability"] = round(g["probability"], 3)
                g["american_odds"] = probability_to_american(g["probability"])

        # Assign ranks
        for i, g in enumerate(golfers):
            g["rank"] = i + 1

        order_idx = TOURNAMENT_ORDER.index(tourn_key) if tourn_key in TOURNAMENT_ORDER else 99
        display_name = TOURNAMENT_DISPLAY_NAMES.get(tourn_key, tourn_key.replace("_", " ").title())

        tournaments.append({
            "key": tourn_key,
            "name": display_name,
            "is_major": tourn_key in MAJOR_TOURNAMENTS,
            "order": order_idx,
            "commence_time": earliest_commence.isoformat() if earliest_commence else None,
            "resolution_date": latest_resolution.isoformat() if latest_resolution else None,
            "market_ids": market_ids,
            "golfers": golfers,
        })

    # Sort tournaments by order
    tournaments.sort(key=lambda t: t["order"])
    # Remove the order field from response (internal use only)
    for t in tournaments:
        del t["order"]

    # ========================================================================
    # Biggest movers — top 5 golfers across all tournaments by |movement_24h|
    # ========================================================================
    all_movers = []
    for tourn in tournaments:
        for g in tourn["golfers"]:
            if g["movement_24h"] is not None and abs(g["movement_24h"]) >= 0.005:
                all_movers.append({
                    "name": g["name"],
                    "tournament_key": tourn["key"],
                    "tournament_name": tourn["name"],
                    "movement_24h": g["movement_24h"],
                    "probability": g["probability"],
                })
    all_movers.sort(key=lambda m: abs(m["movement_24h"]), reverse=True)
    biggest_movers = all_movers[:5]

    # ========================================================================
    # Golf events — live + upcoming from events table
    # ========================================================================
    now = datetime.now(timezone.utc)
    events_query = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .where(
            Sport.key.ilike("golf_%"),
            or_(
                # Currently live events
                Event.status == "live",
                # Upcoming events in next 30 days
                Event.commence_time.between(now, now + timedelta(days=30)),
                # Recently started (last 6h, may not be marked 'live' yet)
                Event.commence_time.between(now - timedelta(hours=6), now),
            ),
        )
        .order_by(Event.commence_time)
        .limit(10)
    )
    events_result = await db.execute(events_query)
    upcoming_events_rows = events_result.scalars().all()

    upcoming_events = [
        {
            "id": e.id,
            "name": f"{e.home_team_name} vs {e.away_team_name}" if e.away_team_name else e.home_team_name,
            "commence_time": e.commence_time.isoformat() if e.commence_time else None,
            "status": e.status,
        }
        for e in upcoming_events_rows
    ]

    return {
        "tournaments": tournaments,
        "biggest_movers": biggest_movers,
        "upcoming_events": upcoming_events,
        "total_tournaments": len(tournaments),
        "total_golfers": sum(len(t["golfers"]) for t in tournaments),
    }
