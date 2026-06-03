"""Events API endpoints."""

import logging
import re

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, and_, or_, func, case, cast, Integer, String, literal_column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert

from app.models import Event, OddsSnapshot, Sport, ScoreSnapshot, EIPercentile, FuturesMarket, FuturesOutcome, Team
from app.services import get_db, get_db_rw, OddsAPIService, fetch_current_odds
from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY
from app.utils import (
    moneyline_to_probability,
    project_scores,
    calculate_gei,
    aggregate_bookmaker_odds,
    detect_reversed_bookmakers,
    compute_highlight,
    compute_time_series_metrics,
    get_highlight_label,
    should_highlight,
)
from app.utils.odds_filtering import filter_stale_bookmaker_snapshots as _filter_stale_bookmaker_snapshots
from app.utils.prediction_market_matching import is_kalshi_game_ticker
from app.utils.event_taxonomy import compute_event_tags, validate_tag
from app.utils.game_state import normalize_live_game_state
from app.utils.sport_keys import (
    SPORT_PREFIX_TO_LLM_CATEGORY as _SPORT_PREFIX_TO_LLM_CATEGORY,
    get_sport_key_from_ticker as _get_sport_key_from_ticker,
)

router = APIRouter()

_FUTURES_DEDUP_STRIP = re.compile(
    r"(nba\s+playoffs:\s*)?"
    r"(nhl\s+playoffs:\s*)?"
    r"(mlb\s+playoffs:\s*)?"
    r"(who\s+will\s+win\s+series\s*[\-–—?]\s*)?"
    r"(win\s+series\s*[\-–—]\s*)?",
    re.I,
)

def _normalize_futures_dedup_key(market) -> str:
    """Normalize a futures market name for cross-source deduplication.

    "2026 NBA Champion" and "NBA Championship Winner" → same key.
    "76ers vs. Celtics" and "Celtics vs 76ers" → same key.
    """
    if getattr(market, "canonical_market_key", None):
        # Strip trailing season (e.g., ":2025-26") and trailing colons
        key = re.sub(r":\d{4}(-\d{2,4})?$", "", market.canonical_market_key)
        key = key.rstrip(":")
        return f"canonical:{key}"
    name = (market.name or "").strip()
    name = _FUTURES_DEDUP_STRIP.sub("", name).strip()
    name = re.sub(r"\s*[?!]\s*$", "", name)
    name_lower = name.lower()
    # Normalize "2025-26 NBA Champion" / "NBA Championship Winner" → "nba champion"
    name_lower = re.sub(r"\b\d{4}(-\d{2,4})?\s*", "", name_lower).strip()
    name_lower = re.sub(r"\bchampionship\s+winner\b", "champion", name_lower)
    name_lower = re.sub(r"\bwinner\b", "champion", name_lower)
    # Split on matchup separators
    parts = re.split(r"\s+(?:vs\.?|at|@)\s+", name_lower, maxsplit=1)
    if len(parts) == 2:
        parts = sorted(p.strip() for p in parts)
        return f"matchup:{'|'.join(parts)}:{market.market_tier or 0}"
    return f"name:{name_lower}:{market.market_tier or 0}"


# Common sport abbreviation mapping — short queries like "NBA", "NFL"
# should match the sport key rather than accidentally matching substrings
# in team names (e.g., "NBA" matching "Gebenbach" or "Pekanbaru").
# Individual sports where the Odds API creates per-tournament sport keys
# (e.g., "tennis_atp_indian_wells" instead of just "tennis_atp").
# Map the base prefix to the canonical display key so search results
# show "Tennis — ATP" instead of "Tennis — ATP INDIAN WELLS".
_INDIVIDUAL_SPORT_BASE_KEYS: dict[str, str] = {
    "tennis_atp": "tennis_atp",
    "tennis_wta": "tennis_wta",
    "boxing_": "boxing_boxing",
}

# Sport key prefixes where "teams" are actually individual athletes (tennis
# players, MMA fighters, golfers, boxers).  The Odds API models these 1v1
# sports as team-vs-team, so every player gets a row in the ``teams`` table.
# We suppress these from team search results so users don't see
# "Carlos Alcaraz — ATP" as a Team card.
_INDIVIDUAL_SPORT_PREFIXES: tuple[str, ...] = (
    "tennis_",
    "mma_",
    "boxing_",
    "golf_",
)


def _is_individual_sport(sport_key: str | None) -> bool:
    """Return True if *sport_key* belongs to a 1-on-1 / individual sport."""
    if not sport_key:
        return False
    return sport_key.startswith(_INDIVIDUAL_SPORT_PREFIXES)


def _normalize_team_sport_key(sport_key: str | None) -> str | None:
    """Collapse tournament-specific sport keys to their base league.

    E.g., "tennis_atp_indian_wells" → "tennis_atp",
          "tennis_wta_italian_open" → "tennis_wta".
    """
    if not sport_key:
        return sport_key
    for prefix, base in _INDIVIDUAL_SPORT_BASE_KEYS.items():
        if sport_key.startswith(prefix) and sport_key != base:
            return base
    return sport_key


_SPORT_SEARCH_ALIASES: dict[str, list[str]] = {
    "nba": ["basketball_nba"],
    "nfl": ["americanfootball_nfl"],
    "mlb": ["baseball_mlb"],
    "nhl": ["icehockey_nhl"],
    "ncaab": ["basketball_ncaab"],
    "ncaaf": ["americanfootball_ncaaf"],
    "wnba": ["basketball_wnba"],
    "mls": ["soccer_usa_mls"],
    "epl": ["soccer_epl"],
    "ufc": ["mma_ufc"],
    "pga": ["golf_pga"],
    "mma": ["mma_ufc"],
    "soccer": ["soccer_epl", "soccer_usa_mls", "soccer_uefa_champs_league"],
    "football": ["americanfootball_nfl", "americanfootball_ncaaf"],
    "basketball": ["basketball_nba", "basketball_ncaab", "basketball_wnba", "basketball_wncaab"],
    "baseball": ["baseball_mlb"],
    "hockey": ["icehockey_nhl"],
    "golf": ["golf_pga", "golf_lpga"],
    "tennis": ["tennis_atp", "tennis_wta"],
}


_SEARCH_TS_CONFIG_SQL = literal_column("'english'")
_SEARCH_EVENT_TEAM_WEIGHT = "A"
_SEARCH_FUTURES_MARKET_WEIGHT = "B"
_SEARCH_FUTURES_OUTCOME_WEIGHT = "C"


def _search_tsquery(q: str):
    """Build a PostgreSQL query parser expression for user search text."""
    return func.websearch_to_tsquery(_SEARCH_TS_CONFIG_SQL, q.strip())


def _weighted_search_vector(column, weight: str):
    """Build a weighted query-time tsvector for a nullable text expression."""
    return func.setweight(
        func.to_tsvector(_SEARCH_TS_CONFIG_SQL, func.coalesce(column, "")),
        literal_column(f"'{weight}'"),
    )


def _combine_search_vectors(*vectors):
    combined = vectors[0]
    for vector in vectors[1:]:
        combined = combined.op("||")(vector)
    return combined


def _event_search_vector():
    return _combine_search_vectors(
        _weighted_search_vector(Event.home_team_name, _SEARCH_EVENT_TEAM_WEIGHT),
        _weighted_search_vector(Event.away_team_name, _SEARCH_EVENT_TEAM_WEIGHT),
    )


def _team_search_vector():
    return _combine_search_vectors(
        _weighted_search_vector(Team.name, _SEARCH_EVENT_TEAM_WEIGHT),
        _weighted_search_vector(Team.abbreviation, _SEARCH_EVENT_TEAM_WEIGHT),
        _weighted_search_vector(
            cast(Team.alternate_names, String),
            _SEARCH_EVENT_TEAM_WEIGHT,
        ),
    )


def _futures_search_vector():
    outcome_names = (
        select(func.string_agg(FuturesOutcome.name, " "))
        .where(FuturesOutcome.market_id == FuturesMarket.id)
        .correlate(FuturesMarket)
        .scalar_subquery()
    )
    return _combine_search_vectors(
        _weighted_search_vector(FuturesMarket.name, _SEARCH_FUTURES_MARKET_WEIGHT),
        _weighted_search_vector(outcome_names, _SEARCH_FUTURES_OUTCOME_WEIGHT),
    )


def _search_rank(search_vector, q: str):
    return func.ts_rank_cd(search_vector, _search_tsquery(q))


@router.post("/discover")
@router.get("/discover")
async def discover_all_events(
    categories: Optional[str] = Query(
        None,
        description="Comma-separated category prefixes to discover (e.g., 'rugby,cricket,aussierules'). If not specified, discovers ALL sports."
    ),
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Discover and create events for all sports from The Odds API.

    This fetches events from the API and upserts them into the database,
    along with their odds snapshots. Use this to populate events for
    sports that were previously excluded.

    Supports both GET and POST for compatibility.
    Call /api/sports/sync first to ensure sports exist in DB.
    """
    service = OddsAPIService()

    try:
        # Get all active sports from DB
        query = select(Sport).where(Sport.active == True)
        result = await db.execute(query)
        sports = result.scalars().all()

        if not sports:
            raise HTTPException(
                status_code=400,
                detail="No sports in database. Call POST /api/sports/sync first."
            )

        # Filter by categories if specified
        if categories:
            prefixes = [c.strip().lower() for c in categories.split(",")]
            sports = [s for s in sports if any(s.key.lower().startswith(p) for p in prefixes)]

        if not sports:
            raise HTTPException(
                status_code=400,
                detail=f"No sports found matching categories: {categories}"
            )

        total_events = 0
        total_snapshots = 0
        sports_processed = 0
        sports_with_events = {}
        errors = []

        for sport in sports:
            try:
                # Fetch events with odds from the API
                events_data = await service.get_odds(sport.key)

                if not events_data:
                    continue

                sport_events = 0
                sport_snapshots = 0

                for event_data in events_data:
                    # Parse commence time
                    commence_time = datetime.fromisoformat(
                        event_data["commence_time"].replace("Z", "+00:00")
                    )

                    # Determine status
                    now = datetime.now(timezone.utc)
                    if commence_time <= now:
                        event_status = "live"
                    else:
                        event_status = "scheduled"

                    # Upsert event
                    event_stmt = insert(Event).values(
                        external_id=event_data["id"],
                        sport_id=sport.id,
                        home_team_name=event_data["home_team"],
                        away_team_name=event_data["away_team"],
                        commence_time=commence_time,
                        status=event_status,
                    ).on_conflict_do_update(
                        index_elements=["external_id"],
                        set_={
                            "home_team_name": event_data["home_team"],
                            "away_team_name": event_data["away_team"],
                            # Don't overwrite commence_time — The Odds API occasionally
                            # returns local times as UTC. ESPN sync corrects these.
                            "status": case(
                                (Event.status == "scheduled", event_status),
                                else_=Event.status
                            ),
                        }
                    ).returning(Event.id)

                    event_result = await db.execute(event_stmt)
                    event_id = event_result.scalar_one()
                    sport_events += 1

                    # Create odds snapshots for each bookmaker
                    for bookmaker in event_data.get("bookmakers", []):
                        bookmaker_key = bookmaker["key"]

                        # Find h2h market
                        for market in bookmaker.get("markets", []):
                            if market["key"] != "h2h":
                                continue

                            outcomes = market.get("outcomes", [])
                            if len(outcomes) < 2:
                                continue

                            # Get home and away odds
                            home_odds = None
                            away_odds = None
                            for outcome in outcomes:
                                if outcome["name"] == event_data["home_team"]:
                                    home_odds = outcome["price"]
                                elif outcome["name"] == event_data["away_team"]:
                                    away_odds = outcome["price"]

                            if home_odds and away_odds:
                                # Convert to probabilities (returns tuple)
                                home_prob, away_prob = moneyline_to_probability(home_odds, away_odds)

                                # Insert snapshot (no upsert - just create new records)
                                snapshot = OddsSnapshot(
                                    event_id=event_id,
                                    bookmaker=bookmaker_key,
                                    home_moneyline=home_odds,
                                    away_moneyline=away_odds,
                                    home_win_probability=home_prob,
                                    away_win_probability=away_prob,
                                    captured_at=now,
                                )
                                db.add(snapshot)
                                sport_snapshots += 1

                total_events += sport_events
                total_snapshots += sport_snapshots
                sports_processed += 1

                # Commit after each sport to isolate failures
                await db.commit()

                if sport_events > 0:
                    # Categorize sport
                    if sport.key.startswith("rugby"):
                        cat = "rugby"
                    elif sport.key.startswith("cricket"):
                        cat = "cricket"
                    elif sport.key.startswith("aussierules"):
                        cat = "afl"
                    elif sport.key.startswith("soccer"):
                        cat = "soccer"
                    else:
                        cat = sport.key.split("_")[0]

                    if cat not in sports_with_events:
                        sports_with_events[cat] = {"sports": [], "events": 0, "snapshots": 0}
                    sports_with_events[cat]["sports"].append(sport.key)
                    sports_with_events[cat]["events"] += sport_events
                    sports_with_events[cat]["snapshots"] += sport_snapshots

            except Exception as e:
                # Rollback failed transaction so subsequent sports can proceed
                await db.rollback()
                errors.append(f"{sport.key}: {str(e)}")
                continue

        return {
            "success": True,
            "sports_processed": sports_processed,
            "total_events": total_events,
            "total_snapshots": total_snapshots,
            "by_category": sports_with_events,
            "errors": errors if errors else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Error discovering events: {str(e)}"
        )
    finally:
        await service.close()


# In-memory cache for EI percentiles (rarely changes, queried on every request)
_ei_cache: dict = {}
_ei_cache_time: float = 0
_EI_CACHE_TTL = 300  # 5 minutes

# In-memory cache for game-markets responses (roster queries are expensive)
# Completed games: cached indefinitely. Live/scheduled: 30s TTL.
_game_markets_cache: dict[int, tuple[float, str, dict]] = {}  # event_id → (timestamp, status, response)
_GAME_MARKETS_LIVE_TTL = 30
_GAME_MARKETS_MAX_SIZE = 200

# Sport-specific expected game-total threshold ranges.
# Thresholds outside these bounds are from a different sport (cross-game
# contamination via mis-linked event_id or overly broad fallback queries).
# Format: sport_key_prefix → (min_threshold, max_threshold)
_SPORT_TOTAL_RANGE: dict[str, tuple[float, float]] = {
    "basketball": (120, 320),    # NBA/NCAAB/WNBA game totals ~170-260
    "americanfootball": (15, 120),  # NFL/NCAAF game totals ~30-65
    "baseball": (0.5, 30),       # MLB game totals ~5-14
    "icehockey": (0.5, 15),      # NHL game totals ~4-8
    "soccer": (0.5, 10),         # Soccer game totals ~1.5-5
    "mma": (0.5, 10),            # MMA round totals ~1.5-5
    "tennis": (0.5, 60),         # Tennis game/set totals
    "rugby": (10, 120),          # Rugby totals ~30-60
    "lacrosse": (5, 50),         # Lacrosse totals ~15-30
    "aussierules": (80, 280),    # AFL totals ~140-200
    "cricket": (50, 800),        # Cricket totals vary widely
}

# Team-total ranges are roughly half the game-total range (each team's share).
_SPORT_TEAM_TOTAL_RANGE: dict[str, tuple[float, float]] = {
    "basketball": (60, 180),
    "americanfootball": (5, 65),
    "baseball": (0.5, 18),
    "icehockey": (0.5, 10),
    "soccer": (0.5, 7),
    "mma": (0.5, 7),
    "tennis": (0.5, 35),
    "rugby": (5, 70),
    "lacrosse": (2, 30),
    "aussierules": (30, 160),
    "cricket": (20, 500),
}

_event_detail_cache: dict[int, tuple[float, str, dict]] = {}  # event_id → (timestamp, status, response)
_EVENT_DETAIL_LIVE_TTL = 30
_EVENT_DETAIL_DEFAULT_TTL = 300
_EVENT_DETAIL_MAX_SIZE = 500


async def _load_ei_percentiles(db: AsyncSession) -> dict:
    """Load EI percentile thresholds from database.

    Returns cached data if available (TTL 5 min). Percentiles change
    only when recalculate is triggered, so per-request DB queries are
    wasteful.

    Returns empty dict if table doesn't exist or query fails,
    allowing the API to function without EI data.
    """
    import time

    global _ei_cache, _ei_cache_time

    now = time.monotonic()
    if _ei_cache and (now - _ei_cache_time) < _EI_CACHE_TTL:
        return _ei_cache

    try:
        result = await db.execute(
            select(EIPercentile.scope, EIPercentile.percentile, EIPercentile.raw_ei_threshold)
        )
        rows = result.all()

        percentiles = {}
        for scope, percentile, threshold in rows:
            if scope not in percentiles:
                percentiles[scope] = {}
            percentiles[scope][percentile] = float(threshold) if threshold else 0

        _ei_cache = percentiles
        _ei_cache_time = now
        return percentiles
    except Exception:
        # Table may not exist yet - return empty dict
        return {}


# Backward-compatible alias
_load_gei_percentiles = _load_ei_percentiles


@router.get("/highlights")
async def get_highlights(
    sport: Optional[str] = Query(None, description="Filter by sport key"),
    days: int = Query(7, description="Days of history to include"),
    limit: int = Query(20, description="Maximum number of events"),
    min_percentile: int = Query(75, description="Minimum EI percentile"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the most exciting completed events.

    Returns events with highest EI scores, useful for highlights/replay discovery.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Load EI percentiles for formatting
    ei_percentiles = await _load_ei_percentiles(db)

    # Build query for completed events with EI
    query = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.status == "completed",
            Event.raw_ei.isnot(None),
            Event.commence_time >= cutoff,
        )
        .order_by(Event.raw_ei.desc())
        .limit(limit * 2)  # Fetch extra to filter by percentile
    )

    if sport:
        query = query.join(Sport).where(Sport.key == sport)

    result = await db.execute(query)
    events = result.scalars().all()

    # Apply percentile filter
    highlights = []
    for event in events:
        formatted = _format_event(event, ei_percentiles)

        # Check EI score threshold
        ei = formatted.get("ei", formatted.get("pulse", {}))
        ei_score = ei.get("score", 0)
        if ei_score >= min_percentile:
            highlights.append(formatted)

        if len(highlights) >= limit:
            break

    return {
        "highlights": highlights,
        "filters": {
            "sport": sport,
            "days": days,
            "min_percentile": min_percentile,
        },
        "count": len(highlights),
    }


@router.get("/pulse-rankings")
@router.get("/ei-rankings")
async def get_ei_rankings(
    limit: int = Query(25, ge=1, le=100, description="Number of events per list"),
    sport: Optional[str] = Query(None, description="Filter by sport key"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the all-time highest and lowest EI events.

    Returns two lists: the most exciting games ever tracked (highest EI)
    and the most boring/one-sided games (lowest EI).

    Only includes events with sufficient odds data (10+ snapshots) to avoid
    inflated scores from games with sparse data.
    """
    # Load EI percentiles for formatting
    ei_percentiles = await _load_ei_percentiles(db)

    # Use snapshot_count from ei_metadata JSON instead of scanning
    # the (very large) odds_snapshots table. The EI calculation already
    # stores snapshot_count in ei_metadata when it computes the score.
    MIN_SNAPSHOTS_FOR_RANKING = 20

    # Extract snapshot_count from the ei_metadata JSON text column.
    # Cast Text -> JSONB, extract key as text, then cast to Integer.
    snap_count_expr = cast(
        cast(Event.ei_metadata, JSONB)["snapshot_count"].as_string(),
        Integer,
    )

    # Base query for completed events with EI and enough data
    base_query = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.status.in_(["completed", "closed"]),
            Event.raw_ei.isnot(None),
            Event.ei_metadata.isnot(None),
            snap_count_expr >= MIN_SNAPSHOTS_FOR_RANKING,
        )
    )

    if sport:
        base_query = base_query.join(Sport).where(Sport.key == sport)

    # Highest EI (most exciting)
    highest_query = base_query.order_by(Event.raw_ei.desc()).limit(limit)
    highest_result = await db.execute(highest_query)
    highest_events = highest_result.scalars().all()

    # Lowest EI (least exciting) - must have some activity (raw_ei > 0)
    lowest_query = (
        base_query
        .where(Event.raw_ei > 0)
        .order_by(Event.raw_ei.asc())
        .limit(limit)
    )
    lowest_result = await db.execute(lowest_query)
    lowest_events = lowest_result.scalars().all()

    # Format events with rank
    highest_formatted = []
    for i, event in enumerate(highest_events, 1):
        formatted = _format_event(event, ei_percentiles)
        formatted["rank"] = i
        highest_formatted.append(formatted)

    lowest_formatted = []
    for i, event in enumerate(lowest_events, 1):
        formatted = _format_event(event, ei_percentiles)
        formatted["rank"] = i
        lowest_formatted.append(formatted)

    return {
        "highest": highest_formatted,
        "lowest": lowest_formatted,
        "filters": {
            "sport": sport,
            "limit": limit,
        },
    }


@router.get("/faceted")
async def faceted_search(
    tags: Optional[str] = Query(None, description="JSON array of tags"),
    sport: Optional[str] = Query(None, description="Sport tag value"),
    event_status: Optional[str] = Query(None, alias="status", description="Status tag value"),
    stakes: Optional[str] = Query(None, description="Stakes tag value"),
    narrative: Optional[str] = Query(None, description="Narrative tag value"),
    audience: Optional[str] = Query(None, description="Audience tag value"),
    days: int = Query(7, ge=1, le=30, description="Time window in days"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Results per page"),
    db: AsyncSession = Depends(get_db),
):
    """Faceted search over events using GIN-indexed taxonomy tags."""
    import json as _json
    from sqlalchemy import literal_column, text as sql_text

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Build tag filter from both sources
    tag_filter: list[str] = []

    if tags:
        try:
            parsed = _json.loads(tags)
            if isinstance(parsed, list):
                tag_filter.extend(str(t) for t in parsed)
        except (ValueError, TypeError):
            pass

    convenience = {
        "sport": sport, "status": event_status, "stakes": stakes,
        "narrative": narrative, "audience": audience,
    }
    for ns, val in convenience.items():
        if val:
            tag_filter.append(f"{ns}:{val}")

    # Base conditions
    conditions = [Event.commence_time >= cutoff]

    # GIN containment filter — use literal_column to inline the JSONB
    # value directly, avoiding asyncpg bind-parameter JSONB casting issues
    valid_tags: list[str] = []
    if tag_filter:
        valid_tags = [t for t in tag_filter if validate_tag(t)]
        if valid_tags:
            escaped = _json.dumps(valid_tags).replace("'", "''")
            conditions.append(
                Event.event_tags.op("@>")(
                    literal_column(f"'{escaped}'::jsonb")
                )
            )

    # Count
    count_q = select(func.count(Event.id)).where(*conditions)
    total_count = (await db.execute(count_q)).scalar() or 0

    # Data
    offset_val = (page - 1) * per_page
    data_q = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(*conditions)
        .order_by(
            case(
                (Event.status == "live", 0),
                (Event.status == "scheduled", 1),
                else_=2,
            ),
            Event.commence_time.desc(),
        )
        .offset(offset_val)
        .limit(per_page)
    )
    events = (await db.execute(data_q)).scalars().all()

    # Team lookup
    team_names = []
    for event in events:
        if event.home_team_name:
            team_names.append(event.home_team_name)
        if event.away_team_name:
            team_names.append(event.away_team_name)
    team_lookup = await _build_team_lookup(db, team_names)

    # Format
    formatted = []
    for event in events:
        evt = _format_event(event, team_lookup=team_lookup)
        if event.event_tags:
            evt["event_tags"] = event.event_tags
        formatted.append(evt)

    # Facet counts — also use inline JSONB literal
    facet_sql = """
        SELECT split_part(tag, ':', 1) AS ns, tag, COUNT(*) AS cnt
        FROM events, jsonb_array_elements_text(event_tags) AS tag
        WHERE commence_time >= :cutoff
    """
    facet_params: dict = {"cutoff": cutoff}
    if valid_tags:
        escaped_facet = _json.dumps(valid_tags).replace("'", "''")
        facet_sql += f" AND event_tags @> '{escaped_facet}'::jsonb"
    facet_sql += " GROUP BY ns, tag ORDER BY ns, cnt DESC"

    facet_rows = (await db.execute(sql_text(facet_sql), facet_params)).all()
    facets: dict = {}
    for row in facet_rows:
        ns = row[0]
        if ns not in facets:
            facets[ns] = []
        facets[ns].append({"tag": row[1], "count": row[2]})

    return {
        "total": total_count,
        "page": page,
        "per_page": per_page,
        "filters": tag_filter,
        "events": formatted,
        "facets": facets,
    }


@router.get("/search")
async def search_events(
    q: str = Query(..., min_length=2, description="Search query (team name, city, etc.)"),
    sport: Optional[str] = Query(None, description="Filter by sport key (e.g., basketball_nba)"),
    tags: Optional[str] = Query(None, description="Filter by taxonomy tags (JSON array, e.g., [\"sport:basketball\", \"importance:playoff\"])"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Results per page"),
    days_back: int = Query(30, ge=1, le=365, description="How many days back to search"),
    include_upcoming: bool = Query(True, description="Include scheduled games"),
    db: AsyncSession = Depends(get_db),
):
    """
    Search for events by team name, city, or other keywords.

    Returns paginated results grouped by sport/league for disambiguation
    when multiple teams share the same name (e.g., "Celtics" in NBA vs other leagues).

    Results are ordered:
    1. Live games (currently in progress)
    2. Upcoming scheduled games (soonest first)
    3. Completed games (most recent first)
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_back)

    # search_pattern is the full query for futures name search (always works)
    search_pattern = f"%{q}%"

    sport_alias_keys = _SPORT_SEARCH_ALIASES.get(q.strip().lower())

    # Split multi-word queries: "USA Canada" should match events where
    # one team is "USA" and the other is "Canada"
    terms = q.strip().split()
    if len(terms) > 1:
        # Multi-word: each term must match EITHER home or away team name.
        # This finds "USA vs Canada" when searching "USA Canada".
        term_conditions = []
        for term in terms:
            term_pattern = f"%{term}%"
            term_conditions.append(
                or_(
                    Event.home_team_name.ilike(term_pattern),
                    Event.away_team_name.ilike(term_pattern),
                )
            )
        team_filter = and_(*term_conditions)
    else:
        # For single-word queries, match team names OR sport key alias.
        # Sport key matching handles "NBA" → basketball_nba events,
        # preventing false positives from substring matches like "Gebenbach".
        name_filter = or_(
            Event.home_team_name.ilike(search_pattern),
            Event.away_team_name.ilike(search_pattern),
        )
        if sport_alias_keys:
            team_filter = or_(
                name_filter,
                Sport.key.in_(sport_alias_keys),
            )
        else:
            team_filter = name_filter

    # Build base query - search both home and away team names
    query = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .options(selectinload(Event.sport))
        .where(
            team_filter,
            Event.commence_time >= cutoff,
        )
    )

    # Filter by status based on include_upcoming
    if include_upcoming:
        query = query.where(Event.status.in_(["scheduled", "live", "completed", "closed"]))
    else:
        query = query.where(Event.status.in_(["live", "completed", "closed"]))

    # Filter by sport if specified
    if sport:
        query = query.where(Sport.key == sport)

    # Filter by taxonomy tags via GIN index
    if tags:
        import json as _json
        try:
            tag_list = _json.loads(tags)
            if isinstance(tag_list, list) and tag_list:
                query = query.where(
                    Event.event_tags.op("@>")(cast(_json.dumps(tag_list), JSONB))
                )
        except (ValueError, TypeError):
            pass

    # Custom ordering: live first, then upcoming (soonest), then completed (most recent)
    # Using CASE statement for status priority
    status_order = case(
        (Event.status == "live", 0),
        (Event.status == "scheduled", 1),
        else_=2
    )

    # Tag-based relevance boost within each status group.
    # Events with contextual LLM tags (rivalry, elimination, etc.) or
    # importance tags (playoff, championship) rank higher in search.
    from sqlalchemy import literal_column as _lc
    tag_boost = case(
        # Championship/playoff events first
        (Event.event_tags.op("@>")(_lc("'[\"importance:championship\"]'::jsonb")), 0),
        (Event.event_tags.op("@>")(_lc("'[\"importance:playoff\"]'::jsonb")), 1),
        # High-stakes LLM tags
        (Event.event_tags.op("@>")(_lc("'[\"stakes:elimination\"]'::jsonb")), 2),
        (Event.event_tags.op("@>")(_lc("'[\"stakes:title_defense\"]'::jsonb")), 2),
        (Event.event_tags.op("@>")(_lc("'[\"narrative:rivalry\"]'::jsonb")), 3),
        (Event.event_tags.op("@>")(_lc("'[\"narrative:historic_rivalry\"]'::jsonb")), 3),
        (Event.event_tags.op("@>")(_lc("'[\"audience:national_interest\"]'::jsonb")), 4),
        (Event.event_tags.op("@>")(_lc("'[\"stakes:clinch\"]'::jsonb")), 4),
        (Event.event_tags.op("@>")(_lc("'[\"stakes:playoff_race\"]'::jsonb")), 5),
        else_=9
    )
    search_rank = _search_rank(_event_search_vector(), q)

    # For scheduled: order by commence_time ASC (soonest first)
    # For completed: order by commence_time DESC (most recent first)
    # We handle this by using different sort keys based on status
    query = query.order_by(
        status_order,
        tag_boost,
        search_rank.desc(),
        # For live/scheduled, sort ascending; for completed, we want descending
        # Using a compound sort: status priority, then time
        case(
            (Event.status.in_(["live", "scheduled"]), Event.commence_time),
            else_=None
        ).asc().nulls_last(),
        case(
            (Event.status.in_(["completed", "closed"]), Event.commence_time),
            else_=None
        ).desc().nulls_last(),
    )

    # Get total count (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_count = total_result.scalar()

    # Fuzzy fallback: re-query with trigram similarity when ILIKE finds nothing
    fuzzy_corrected: str | None = None
    if total_count == 0 and len(terms) == 1 and not sport_alias_keys:
        try:
            best_team = await db.execute(
                select(Team.name, func.similarity(Team.name, q).label("sim"))
                .where(func.similarity(Team.name, q) > 0.25)
                .order_by(func.similarity(Team.name, q).desc())
                .limit(1)
            )
            best = best_team.first()
            if best:
                fuzzy_corrected = best.name
                fuzzy_pattern = f"%{fuzzy_corrected}%"
                fuzzy_filter = or_(
                    Event.home_team_name.ilike(fuzzy_pattern),
                    Event.away_team_name.ilike(fuzzy_pattern),
                )
                query = (
                    select(Event)
                    .join(Sport, Event.sport_id == Sport.id)
                    .options(selectinload(Event.sport))
                    .where(fuzzy_filter, Event.commence_time >= cutoff)
                )
                if include_upcoming:
                    query = query.where(Event.status.in_(["scheduled", "live", "completed", "closed"]))
                else:
                    query = query.where(Event.status.in_(["live", "completed", "closed"]))
                if sport:
                    query = query.where(Sport.key == sport)
                fuzzy_search_rank = _search_rank(_event_search_vector(), fuzzy_corrected)
                query = query.order_by(
                    status_order,
                    fuzzy_search_rank.desc(),
                    Event.commence_time.desc().nulls_last(),
                )
                total_count_r = await db.execute(select(func.count()).select_from(query.subquery()))
                total_count = total_count_r.scalar()
        except Exception:
            pass

    # Apply pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    # Execute
    result = await db.execute(query)
    events = result.scalars().all()

    # Get latest aggregated odds for each event
    event_ids = [e.id for e in events]
    aggregated_odds_map = {}

    if event_ids:
        # Get the most recent snapshot per bookmaker per event
        ranked_subq = (
            select(
                OddsSnapshot.id,
                OddsSnapshot.event_id,
                func.row_number().over(
                    partition_by=[OddsSnapshot.event_id, OddsSnapshot.bookmaker],
                    order_by=OddsSnapshot.captured_at.desc()
                ).label("rn")
            )
            .where(OddsSnapshot.event_id.in_(event_ids))
            .subquery()
        )

        latest_odds_query = (
            select(OddsSnapshot)
            .join(ranked_subq, and_(
                OddsSnapshot.id == ranked_subq.c.id,
                ranked_subq.c.rn == 1
            ))
        )

        latest_odds_result = await db.execute(latest_odds_query)
        all_snapshots = latest_odds_result.scalars().all()

        # Group snapshots by event and aggregate
        from collections import defaultdict
        snapshots_by_event = defaultdict(list)
        for snap in all_snapshots:
            snapshots_by_event[snap.event_id].append(snap)

        # Build event lookups for stale bookmaker filtering
        event_info_map = {e.id: e for e in events}

        for event_id, snaps in snapshots_by_event.items():
            ev = event_info_map.get(event_id)
            all_snaps = snaps  # Keep unfiltered for bookmaker table
            filtered_snaps = _filter_stale_bookmaker_snapshots(
                snaps,
                event_status=(ev.status if ev else "scheduled"),
                commence_time=(ev.commence_time if ev else None),
            )
            # Exclude bookmakers with reversed home/away odds from aggregation
            reversed_bks = detect_reversed_bookmakers(filtered_snaps)
            agg_snaps = [s for s in filtered_snaps if s.bookmaker not in reversed_bks] if reversed_bks else filtered_snaps
            latest_time = max(s.captured_at for s in filtered_snaps) if filtered_snaps else None
            aggregated_odds_map[event_id] = {
                "snapshots": filtered_snaps,
                "all_snapshots": all_snaps,
                "aggregated": aggregate_bookmaker_odds(agg_snaps if agg_snaps else filtered_snaps),
                "captured_at": latest_time,
            }

    # Load GEI percentiles for formatting
    gei_percentiles = await _load_gei_percentiles(db)

    # Build team lookup for logos/colors in search results
    all_team_names = []
    for event in events:
        all_team_names.append(event.home_team_name)
        all_team_names.append(event.away_team_name)
    team_lookup = await _build_team_lookup(db, list(set(all_team_names)))

    # Format results and group by sport
    formatted_results = []
    sports_found = {}

    for event in events:
        formatted = _format_event_with_aggregated_odds(
            event, aggregated_odds_map.get(event.id), gei_percentiles, team_lookup
        )
        formatted_results.append(formatted)

        # Track sports for disambiguation info
        sport_key = event.sport.key if event.sport else "unknown"
        sport_name = event.sport.name if event.sport else "Unknown"
        if sport_key not in sports_found:
            sports_found[sport_key] = {
                "key": sport_key,
                "name": sport_name,
                "count": 0,
            }
        sports_found[sport_key]["count"] += 1

    # Calculate pagination metadata
    total_count = total_count or 0
    total_pages = (total_count + per_page - 1) // per_page

    # Also search futures markets by name or outcome (label) name.
    # For multi-word queries, split into individual terms so that
    # "PGA championship playoff" matches "PGA Championship: Playoff"
    # even when the exact phrase doesn't appear verbatim in the name.
    if len(terms) > 1:
        futures_name_conditions = [
            FuturesMarket.name.ilike(f"%{term}%") for term in terms
        ]
        futures_name_match = and_(*futures_name_conditions)
        # Also try matching outcome names with per-term AND logic
        futures_outcome_conditions = [
            FuturesMarket.outcomes.any(FuturesOutcome.name.ilike(f"%{term}%"))
            for term in terms
        ]
        futures_outcome_match = and_(*futures_outcome_conditions)
    else:
        futures_name_match = FuturesMarket.name.ilike(search_pattern)
        futures_outcome_match = FuturesMarket.outcomes.any(
            FuturesOutcome.name.ilike(search_pattern)
        )

    futures_search_rank = _search_rank(_futures_search_vector(), q)
    futures_query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.sport))
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            or_(
                futures_name_match,
                futures_outcome_match,
            ),
            FuturesMarket.status == "open",
            or_(
                FuturesMarket.resolution_date.is_(None),
                FuturesMarket.resolution_date >= datetime.now(timezone.utc),
            ),
        )
        .order_by(
            futures_search_rank.desc(),
            FuturesMarket.market_tier.asc().nulls_last(),
            FuturesMarket.volume.desc().nulls_last(),
            FuturesMarket.updated_at.desc(),
        )
        .limit(20)
    )

    # Apply sport filter to futures if specified
    if sport:
        futures_query = futures_query.join(Sport, FuturesMarket.sport_id == Sport.id).where(
            Sport.key == sport
        )

    futures_result = await db.execute(futures_query)
    futures_markets_raw = futures_result.scalars().unique().all()

    # Deduplicate by normalized name
    seen_search_keys: set[str] = set()
    futures_markets = []
    for m in futures_markets_raw:
        dkey = _normalize_futures_dedup_key(m)
        if dkey in seen_search_keys:
            continue
        seen_search_keys.add(dkey)
        futures_markets.append(m)
        if len(futures_markets) >= 10:
            break

    formatted_futures = [
        _format_futures_for_search(market)
        for market in futures_markets
    ]

    # Search teams
    team_search_filter = or_(
        Team.name.ilike(search_pattern),
        Team.abbreviation.ilike(search_pattern),
        cast(Team.alternate_names, String).ilike(search_pattern),
    )
    if fuzzy_corrected:
        fuzzy_team_pattern = f"%{fuzzy_corrected}%"
        team_search_filter = or_(
            team_search_filter,
            Team.name.ilike(fuzzy_team_pattern),
        )
    team_search_q = (
        select(Team.id, Team.name, Team.slug, Team.abbreviation,
               Team.logo_url_small, Team.current_record, Sport.key.label("sport_key"))
        .join(Sport, Team.sport_id == Sport.id, isouter=True)
        .where(team_search_filter)
        .order_by(_search_rank(_team_search_vector(), q).desc(), Team.name)
        .limit(5)
    )
    if sport:
        team_search_q = team_search_q.where(Sport.key == sport)
    team_search_result = await db.execute(team_search_q)
    teams_seen: set[str] = set()
    matched_teams = []
    for row in team_search_result.all():
        # Suppress individual-sport "teams" (tennis players, MMA fighters,
        # golfers, boxers) — they are artifacts of the Odds API modelling
        # 1v1 sports as team-vs-team.  Users will still find these athletes
        # via event and futures results.
        if _is_individual_sport(row.sport_key):
            continue
        if row.name not in teams_seen:
            teams_seen.add(row.name)
            matched_teams.append({
                "id": row.id,
                "name": row.name,
                "slug": row.slug,
                "abbreviation": row.abbreviation,
                "logo": row.logo_url_small,
                "record": row.current_record,
                "sport_key": _normalize_team_sport_key(row.sport_key),
            })

    return {
        "query": q,
        "teams": matched_teams,
        "results": formatted_results,
        "futures": formatted_futures,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_results": total_count,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
        "sports": list(sports_found.values()),
        "filters": {
            "sport": sport,
            "days_back": days_back,
            "include_upcoming": include_upcoming,
        },
        **({"did_you_mean": fuzzy_corrected} if fuzzy_corrected else {}),
    }



@router.get("/typeahead")
async def typeahead_search(
    q: str = Query(..., min_length=2, max_length=50, description="Search query"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lightweight typeahead search for the search bar.

    Returns up to 8 suggestions: matching teams, upcoming events, and futures.
    Much faster than the full search endpoint — no aggregation or pagination.
    """
    import json as _json
    from app.tasks.redis_state import get_redis_client
    _cache_key = f"bainluck:typeahead:{q.lower().strip()}"
    try:
        _rc = get_redis_client()
        _cached = _rc.get(_cache_key)
        if _cached:
            return _json.loads(_cached)
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    pattern = f"%{q}%"
    suggestions = []

    # Multi-word query support: "USA Canada" finds events where
    # one team is "USA" and the other is "Canada"
    terms = q.strip().split()
    is_multi_word = len(terms) > 1
    if is_multi_word:
        event_term_conditions = []
        team_term_conditions = []
        futures_term_conditions = []
        for term in terms:
            tp = f"%{term}%"
            event_term_conditions.append(
                or_(Event.home_team_name.ilike(tp), Event.away_team_name.ilike(tp))
            )
            team_term_conditions.append(
                or_(Team.name.ilike(tp), Team.abbreviation.ilike(tp),
                    cast(Team.alternate_names, String).ilike(tp))
            )
            futures_term_conditions.append(FuturesMarket.name.ilike(tp))
        event_team_filter = and_(*event_term_conditions)
        team_filter = and_(*team_term_conditions)
        futures_name_filter = and_(*futures_term_conditions)
    else:
        # Sport alias matching for short queries like "NBA", "NFL"
        sport_alias_keys = _SPORT_SEARCH_ALIASES.get(q.strip().lower())

        name_event_filter = or_(
            Event.home_team_name.ilike(pattern),
            Event.away_team_name.ilike(pattern),
        )
        if sport_alias_keys:
            event_team_filter = or_(
                name_event_filter,
                Sport.key.in_(sport_alias_keys),
            )
        else:
            event_team_filter = name_event_filter

        team_filter = or_(
            Team.name.ilike(pattern),
            Team.abbreviation.ilike(pattern),
            cast(Team.alternate_names, String).ilike(pattern),
        )
        futures_name_filter = FuturesMarket.name.ilike(pattern)

    # --- Collect candidates into separate pools (all 3 queries run) ---
    _TIER_LABELS = {1: "Championship", 2: "Conference", 3: "Award", 4: "Division", 5: "Prop"}

    # 1. Teams
    team_query = (
        select(Team.id, Team.name, Team.slug, Team.abbreviation, Team.sport_id, Team.logo_url_small, Sport.key.label("sport_key"))
        .join(Sport, Team.sport_id == Sport.id, isouter=True)
        .where(team_filter)
        .order_by(Team.name)
        .limit(3)
    )
    team_result = await db.execute(team_query)
    team_pool = []
    teams_seen = set()
    for row in team_result.all():
        # Skip individual-sport "teams" (tennis/MMA/golf/boxing players)
        if _is_individual_sport(row.sport_key):
            continue
        if row.name not in teams_seen:
            teams_seen.add(row.name)
            team_pool.append({
                "type": "team",
                "text": row.name,
                "abbreviation": row.abbreviation,
                "logo": row.logo_url_small,
                "team_id": row.id,
                "team_slug": row.slug,
                "sport_key": _normalize_team_sport_key(row.sport_key),
            })

    # 2. Events (live/upcoming) — with team logos
    event_query = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .options(
            selectinload(Event.sport),
            selectinload(Event.home_team),
            selectinload(Event.away_team),
        )
        .where(
            event_team_filter,
            Event.status.in_(["live", "scheduled"]),
            Event.commence_time >= now - timedelta(hours=1),
            Event.commence_time <= now + timedelta(days=7),
        )
        .order_by(
            case((Event.status == "live", 0), else_=1),
            Event.commence_time.asc(),
        )
        .limit(4)
    )
    event_result = await db.execute(event_query)
    event_pool = []
    for event in event_result.scalars().all():
        home = event.home_team
        away = event.away_team
        event_pool.append({
            "type": "event",
            "text": f"{event.away_team_name} at {event.home_team_name}",
            "event_id": event.id,
            "status": event.status,
            "sport_key": event.sport.key if event.sport else None,
            "commence_time": event.commence_time.isoformat() if event.commence_time else None,
            "home_logo": home.logo_url_small if home else None,
            "away_logo": away.logo_url_small if away else None,
        })

    # 3. Futures (sports + non-sports, deduplicated)
    futures_query = (
        select(FuturesMarket)
        .where(
            or_(
                futures_name_filter,
                FuturesMarket.outcomes.any(FuturesOutcome.name.ilike(pattern)),
            ),
            FuturesMarket.status == "open",
            or_(
                FuturesMarket.resolution_date.is_(None),
                FuturesMarket.resolution_date >= now,
            ),
        )
        .order_by(
            FuturesMarket.market_tier.asc().nulls_last(),
            FuturesMarket.volume.desc().nulls_last(),
        )
        .limit(20)
    )
    futures_result = await db.execute(futures_query)
    futures_pool = []
    seen_futures_keys: set[str] = set()
    for market in futures_result.scalars().all():
        if len(futures_pool) >= 5:
            break
        dedup_key = _normalize_futures_dedup_key(market)
        if dedup_key in seen_futures_keys:
            continue
        seen_futures_keys.add(dedup_key)
        label = _TIER_LABELS.get(market.market_tier, None)
        if not label and market.sport_id is None:
            label = (market.llm_sport_category or market.category or "Market").replace("_", " ").title()
        futures_pool.append({
            "type": "futures",
            "text": market.name,
            "market_id": market.id,
            "market_tier": market.market_tier,
            "market_type_label": label or market.market_type or "Market",
            "sport_key": market.llm_sport_category,
        })

    # --- Fuzzy fallback: trigram search when ILIKE finds too few results ---
    did_you_mean: str | None = None
    if not team_pool and not event_pool and len(futures_pool) < 2:
        try:
            from sqlalchemy import text as sql_text
            fuzzy_teams = await db.execute(
                select(
                    Team.id, Team.name, Team.slug, Team.abbreviation,
                    Team.logo_url_small, Sport.key.label("sport_key"),
                    func.similarity(Team.name, q).label("sim"),
                )
                .join(Sport, Team.sport_id == Sport.id, isouter=True)
                .where(func.similarity(Team.name, q) > 0.25)
                .order_by(func.similarity(Team.name, q).desc())
                .limit(3)
            )
            for row in fuzzy_teams.all():
                if _is_individual_sport(row.sport_key):
                    continue
                if row.name not in teams_seen:
                    teams_seen.add(row.name)
                    team_pool.append({
                        "type": "team",
                        "text": row.name,
                        "abbreviation": row.abbreviation,
                        "logo": row.logo_url_small,
                        "team_id": row.id,
                        "team_slug": row.slug,
                        "sport_key": row.sport_key,
                    })

            if team_pool and not event_pool:
                best_team = team_pool[0]["text"]
                best_pattern = f"%{best_team}%"
                fuzzy_events = await db.execute(
                    select(Event)
                    .join(Sport, Event.sport_id == Sport.id)
                    .options(
                        selectinload(Event.sport),
                        selectinload(Event.home_team),
                        selectinload(Event.away_team),
                    )
                    .where(
                        or_(
                            Event.home_team_name.ilike(best_pattern),
                            Event.away_team_name.ilike(best_pattern),
                        ),
                        Event.status.in_(["live", "scheduled"]),
                        Event.commence_time >= now - timedelta(hours=1),
                        Event.commence_time <= now + timedelta(days=7),
                    )
                    .order_by(
                        case((Event.status == "live", 0), else_=1),
                        Event.commence_time.asc(),
                    )
                    .limit(3)
                )
                for event in fuzzy_events.scalars().all():
                    home = event.home_team
                    away = event.away_team
                    event_pool.append({
                        "type": "event",
                        "text": f"{event.away_team_name} at {event.home_team_name}",
                        "event_id": event.id,
                        "status": event.status,
                        "sport_key": event.sport.key if event.sport else None,
                        "commence_time": event.commence_time.isoformat() if event.commence_time else None,
                        "home_logo": home.logo_url_small if home else None,
                        "away_logo": away.logo_url_small if away else None,
                    })
                did_you_mean = best_team
        except Exception:
            pass

    # --- Slot-based assembly ---
    # Guarantee: 1 team, up to 2 events, up to 3 futures. Max 7 total.
    # Events get priority for extra slots over futures.
    suggestions = []
    suggestions.extend(team_pool[:1])
    suggestions.extend(event_pool[:2])
    suggestions.extend(futures_pool[:2])

    remaining = 7 - len(suggestions)
    if remaining > 0:
        # Prioritize more events over more futures
        extras = event_pool[2:4] + futures_pool[2:3] + team_pool[1:2]
        suggestions.extend(extras[:remaining])

    result: dict = {"suggestions": suggestions, "query": q}
    if did_you_mean:
        result["did_you_mean"] = did_you_mean

    # Track query for trending searches (fire-and-forget, no PII)
    try:
        from app.tasks.redis_state import get_redis_client
        rc = get_redis_client()
        normalized = q.strip().lower()
        if len(normalized) >= 3:
            rc.zincrby("search:trending:24h", 1, normalized)
            rc.expire("search:trending:24h", 86400)
    except Exception:
        pass

    return result


@router.get("/search/trending")
async def get_trending_searches():
    """Return top 5 search queries from the last 24 hours."""
    try:
        from app.tasks.redis_state import get_redis_client
        rc = get_redis_client()
        top = rc.zrevrange("search:trending:24h", 0, 4, withscores=True)
        return {
            "trending": [
                {"query": q.decode() if isinstance(q, bytes) else q, "count": int(score)}
                for q, score in top
            ]
        }
    except Exception:
        return {"trending": []}


@router.get("/search-suggestions")
async def search_suggestions(
    db: AsyncSession = Depends(get_db),
):
    """Return 6-8 smart, data-driven search suggestions for the search zero-state.

    Sources: live close games, live upsets, starting soon, futures movers,
    recent upsets, popular championship markets.
    """
    from app.utils.highlights import LEAGUE_TIERS

    now = datetime.now(timezone.utc)
    suggestions: list[dict] = []
    seen_queries: set[str] = set()

    def _add(query: str, label: str, type_: str, **kwargs):
        key = query.lower().strip()
        if key in seen_queries:
            return
        seen_queries.add(key)
        item = {"query": query, "label": label, "type": type_}
        item.update(kwargs)
        suggestions.append(item)

    def _shorter_team(home: str, away: str) -> str:
        return home if len(home) <= len(away) else away

    # Helper: tier 1-2 sport keys
    tier_12_keys = {k for k, t in LEAGUE_TIERS.items() if t <= 2}

    # --- 1. Live close games (home prob 35-65%) ---
    try:
        live_events_q = (
            select(Event)
            .where(Event.status == "live")
            .options(selectinload(Event.sport))
            .limit(50)
        )
        live_result = await db.execute(live_events_q)
        live_events = live_result.scalars().all()

        # Get latest odds for live events via subquery
        if live_events:
            live_ids = [e.id for e in live_events]
            # Ranked window: latest snapshot per event
            ranked = (
                select(
                    OddsSnapshot.event_id,
                    OddsSnapshot.home_probability,
                    func.row_number().over(
                        partition_by=OddsSnapshot.event_id,
                        order_by=OddsSnapshot.captured_at.desc()
                    ).label("rn")
                )
                .where(
                    OddsSnapshot.event_id.in_(live_ids),
                    OddsSnapshot.bookmaker == "aggregate",
                )
                .subquery()
            )
            odds_q = select(ranked.c.event_id, ranked.c.home_probability).where(ranked.c.rn == 1)
            odds_result = await db.execute(odds_q)
            odds_map = {row[0]: row[1] for row in odds_result.all()}

            for ev in live_events:
                if len(suggestions) >= 8:
                    break
                hp = odds_map.get(ev.id)
                if hp is None:
                    continue

                opponent = ev.away_team_name if hp >= 0.5 else ev.home_team_name
                short = _shorter_team(ev.home_team_name, ev.away_team_name)

                # Close game: 35-65%
                if 0.35 <= hp <= 0.65:
                    _add(
                        short,
                        f"Live — tight game vs {opponent}",
                        "event",
                        event_id=ev.id,
                    )
                # Upset check: opening favorite flipped
                elif ev.opening_home_probability is not None:
                    opened_home_fav = ev.opening_home_probability > 0.55
                    now_away_fav = hp < 0.45
                    opened_away_fav = ev.opening_home_probability < 0.45
                    now_home_fav = hp > 0.55
                    if (opened_home_fav and now_away_fav) or (opened_away_fav and now_home_fav):
                        underdog = ev.away_team_name if opened_home_fav else ev.home_team_name
                        _add(
                            underdog,
                            "Upset brewing",
                            "event",
                            event_id=ev.id,
                        )
    except Exception:
        pass  # Non-critical — continue to other sources

    # --- 2. Starting soon (tier 1-2, within 3 hours) ---
    try:
        soon_q = (
            select(Event)
            .join(Sport)
            .where(
                Event.status == "scheduled",
                Event.commence_time.between(now, now + timedelta(hours=3)),
                Sport.key.in_(tier_12_keys),
            )
            .order_by(Event.commence_time.asc())
            .limit(10)
        )
        soon_result = await db.execute(soon_q)
        for ev in soon_result.scalars().all():
            if len(suggestions) >= 8:
                break
            minutes = int((ev.commence_time - now).total_seconds() / 60)
            if minutes < 60:
                time_label = f"Tips off in {minutes} min"
            else:
                hours = minutes // 60
                time_label = f"Starts in {hours}h"
            short = _shorter_team(ev.home_team_name, ev.away_team_name)
            _add(short, time_label, "event", event_id=ev.id)
    except Exception:
        pass

    # --- 3. Futures big movers (|probability_change_24h| > 0.02) ---
    try:
        movers_q = (
            select(FuturesOutcome)
            .join(FuturesMarket)
            .where(
                FuturesMarket.status == "open",
                FuturesOutcome.probability_change_24h.isnot(None),
                func.abs(FuturesOutcome.probability_change_24h) > 0.02,
            )
            .order_by(func.abs(FuturesOutcome.probability_change_24h).desc())
            .options(selectinload(FuturesOutcome.market))
            .limit(5)
        )
        movers_result = await db.execute(movers_q)
        for outcome in movers_result.scalars().all():
            if len(suggestions) >= 8:
                break
            change = outcome.probability_change_24h
            direction = "Surging" if change > 0 else "Falling"
            pct = f"{'+' if change > 0 else ''}{round(change * 100, 1)}%"
            market_name = outcome.market.name if outcome.market else ""
            # Shorten market name
            short_market = market_name
            if len(short_market) > 30:
                short_market = short_market[:27] + "..."
            _add(
                outcome.name,
                f"{direction} {pct} — {short_market}",
                "futures",
                market_id=outcome.market_id,
            )
    except Exception:
        pass

    # --- 4. Recent upsets (completed last 24h, opening underdog won) ---
    try:
        upsets_q = (
            select(Event)
            .where(
                Event.status.in_(["completed", "closed"]),
                Event.commence_time >= now - timedelta(hours=24),
                Event.opening_home_probability.isnot(None),
                Event.home_score.isnot(None),
                Event.away_score.isnot(None),
            )
            .options(selectinload(Event.sport))
            .order_by(Event.commence_time.desc())
            .limit(20)
        )
        upsets_result = await db.execute(upsets_q)
        for ev in upsets_result.scalars().all():
            if len(suggestions) >= 8:
                break
            home_won = ev.home_score > ev.away_score
            if home_won and ev.opening_home_probability < 0.40:
                # Home was underdog and won
                loser = ev.away_team_name
                _add(ev.home_team_name, f"Pulled the upset vs {loser}", "event", event_id=ev.id)
            elif not home_won and ev.opening_home_probability > 0.60:
                # Away was underdog and won
                loser = ev.home_team_name
                _add(ev.away_team_name, f"Pulled the upset vs {loser}", "event", event_id=ev.id)
    except Exception:
        pass

    # --- 5. Popular championship markets (tier 1, open) ---
    try:
        champ_q = (
            select(FuturesMarket)
            .where(
                FuturesMarket.status == "open",
                FuturesMarket.market_tier == 1,
            )
            .order_by(FuturesMarket.outcome_count.desc().nulls_last())
            .limit(5)
        )
        champ_result = await db.execute(champ_q)
        for market in champ_result.scalars().all():
            if len(suggestions) >= 8:
                break
            # Extract a short query from the market name
            name = market.name
            # Try to get just the league championship part
            _add(name, "Championship odds", "futures", market_id=market.id)
    except Exception:
        pass

    _response = {"suggestions": suggestions[:8]}
    try:
        _rc = get_redis_client()
        _rc.setex(_cache_key, 60, _json.dumps(_response, default=str))
    except Exception:
        pass
    return _response


@router.get("/debug/sport-keys")
async def debug_sport_keys(db: AsyncSession = Depends(get_db)):
    """Debug endpoint to see all sport keys in the database."""
    # Get sports with event counts
    result = await db.execute(
        select(
            Sport.key,
            Sport.name,
            Sport.active,
            func.count(Event.id).label("event_count")
        )
        .outerjoin(Event, and_(Sport.id == Event.sport_id, Event.status.in_(["scheduled", "live"])))
        .group_by(Sport.key, Sport.name, Sport.active)
        .order_by(Sport.key)
    )
    sports = result.all()

    # Summary by category
    categories = {}
    for s in sports:
        # Determine category from key prefix
        key = s[0]
        if key.startswith("rugby"):
            cat = "rugby"
        elif key.startswith("cricket"):
            cat = "cricket"
        elif key.startswith("aussierules"):
            cat = "aussierules"
        elif key.startswith("soccer"):
            cat = "soccer"
        else:
            cat = key.split("_")[0] if "_" in key else key

        if cat not in categories:
            categories[cat] = {"sports": 0, "events": 0}
        categories[cat]["sports"] += 1
        categories[cat]["events"] += s[3]

    return {
        "sports": [
            {
                "key": s[0],
                "name": s[1],
                "active": s[2],
                "event_count": s[3],
            }
            for s in sports
        ],
        "categories": categories,
        "total_sports": len(sports),
        "total_events": sum(s[3] for s in sports),
    }


@router.get("/debug/all-events")
async def debug_all_events(
    category: Optional[str] = Query(None, description="Filter by category prefix (rugby, cricket, aussierules, soccer)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Debug endpoint to see ALL events regardless of date/odds filters.

    Shows events that may be hidden due to:
    - Missing odds data
    - Being too far in the future
    - Being old completed events
    """
    query = (
        select(
            Event.id,
            Event.external_id,
            Event.home_team_name,
            Event.away_team_name,
            Event.status,
            Event.commence_time,
            Sport.key.label("sport_key"),
            Sport.name.label("sport_name"),
            func.count(OddsSnapshot.id).label("snapshot_count"),
        )
        .join(Sport, Event.sport_id == Sport.id)
        .outerjoin(OddsSnapshot, Event.id == OddsSnapshot.event_id)
        .group_by(Event.id, Sport.key, Sport.name)
        .order_by(Event.commence_time.desc())
    )

    if category:
        query = query.where(Sport.key.ilike(f"{category}%"))

    result = await db.execute(query.limit(200))
    events = result.all()

    # Categorize events
    by_status = {}
    by_sport = {}
    events_without_odds = []

    for e in events:
        status = e.status
        sport = e.sport_key

        if status not in by_status:
            by_status[status] = 0
        by_status[status] += 1

        if sport not in by_sport:
            by_sport[sport] = {"total": 0, "with_odds": 0, "without_odds": 0}
        by_sport[sport]["total"] += 1

        if e.snapshot_count > 0:
            by_sport[sport]["with_odds"] += 1
        else:
            by_sport[sport]["without_odds"] += 1
            events_without_odds.append({
                "id": e.id,
                "sport": e.sport_key,
                "teams": f"{e.home_team_name} vs {e.away_team_name}",
                "status": e.status,
                "commence_time": e.commence_time.isoformat() if e.commence_time else None,
            })

    return {
        "total_events": len(events),
        "by_status": by_status,
        "by_sport": by_sport,
        "events_without_odds": events_without_odds[:50],  # First 50
        "events": [
            {
                "id": e.id,
                "sport": e.sport_key,
                "teams": f"{e.home_team_name} vs {e.away_team_name}",
                "status": e.status,
                "commence_time": e.commence_time.isoformat() if e.commence_time else None,
                "has_odds": e.snapshot_count > 0,
                "snapshot_count": e.snapshot_count,
            }
            for e in events[:100]  # First 100
        ],
    }


@router.get("/debug/api-bookmakers/{sport_key}")
async def debug_api_bookmakers(sport_key: str):
    """
    Debug endpoint to check what bookmakers the API is returning.

    This makes a direct call to the-odds-api.com to see all available
    bookmakers for a sport. Useful for diagnosing why only one bookmaker
    appears in the data.
    """
    service = OddsAPIService()
    try:
        events_data = await service.get_odds(sport_key)

        # Collect all unique bookmakers across all events
        all_bookmakers = set()
        events_summary = []

        for event in events_data:
            event_bookmakers = [b["key"] for b in event.get("bookmakers", [])]
            all_bookmakers.update(event_bookmakers)
            events_summary.append({
                "id": event["id"],
                "home_team": event["home_team"],
                "away_team": event["away_team"],
                "bookmaker_count": len(event_bookmakers),
                "bookmakers": event_bookmakers,
            })

        # Check API quota
        quota = await service.check_quota()

        return {
            "sport_key": sport_key,
            "total_events": len(events_data),
            "unique_bookmakers": sorted(list(all_bookmakers)),
            "bookmaker_count": len(all_bookmakers),
            "api_quota": quota,
            "events": events_summary[:5],  # First 5 events for brevity
            "note": "If only 1 bookmaker appears, your API subscription tier may limit available bookmakers."
        }
    except Exception as e:
        return {
            "error": str(e),
            "sport_key": sport_key,
        }
    finally:
        await service.close()


@router.get("/debug/db-bookmakers")
async def debug_db_bookmakers(db: AsyncSession = Depends(get_db)):
    """
    Debug endpoint to check what bookmakers are stored in the database.

    Shows events that have odds from multiple bookmakers, proving
    the system CAN store multi-bookmaker data.
    """
    # Find events with multiple bookmakers
    result = await db.execute(
        select(
            Event.id,
            Event.home_team_name,
            Event.away_team_name,
            func.count(func.distinct(OddsSnapshot.bookmaker)).label("bookmaker_count"),
            func.array_agg(func.distinct(OddsSnapshot.bookmaker)).label("bookmakers")
        )
        .join(OddsSnapshot, Event.id == OddsSnapshot.event_id)
        .group_by(Event.id, Event.home_team_name, Event.away_team_name)
        .having(func.count(func.distinct(OddsSnapshot.bookmaker)) > 1)
        .order_by(func.count(func.distinct(OddsSnapshot.bookmaker)).desc())
        .limit(10)
    )
    multi_bookmaker_events = result.all()

    # Get overall stats
    total_result = await db.execute(
        select(
            func.count(func.distinct(OddsSnapshot.bookmaker)).label("total_bookmakers"),
            func.count(func.distinct(OddsSnapshot.event_id)).label("total_events_with_odds")
        )
    )
    totals = total_result.one()

    # Get all unique bookmakers in the database
    bookmakers_result = await db.execute(
        select(func.distinct(OddsSnapshot.bookmaker))
    )
    all_bookmakers = [row[0] for row in bookmakers_result.all()]

    return {
        "summary": {
            "total_unique_bookmakers_in_db": totals[0],
            "total_events_with_odds": totals[1],
            "events_with_multiple_bookmakers": len(multi_bookmaker_events),
            "all_bookmakers": sorted(all_bookmakers),
        },
        "events_with_multiple_bookmakers": [
            {
                "event_id": row[0],
                "home_team": row[1],
                "away_team": row[2],
                "bookmaker_count": row[3],
                "bookmakers": row[4],
            }
            for row in multi_bookmaker_events
        ],
        "diagnosis": "If events_with_multiple_bookmakers is empty but total_unique_bookmakers > 1, "
                     "then bookmakers are not overlapping on the same events. "
                     "If total_unique_bookmakers = 1, the API is only returning one bookmaker."
    }


@router.get("/debug/pulse")
@router.get("/debug/ei")
async def debug_ei_status(db: AsyncSession = Depends(get_db)):
    """
    Debug endpoint to check EI (Excitement Index) calculation status.

    Shows how many events have EI scores calculated.
    """
    # Count events by EI status
    result = await db.execute(
        select(
            Event.status,
            func.count().filter(Event.raw_ei.isnot(None)).label("with_ei"),
            func.count().filter(Event.raw_ei.is_(None)).label("without_ei"),
        )
        .group_by(Event.status)
    )
    rows = result.all()

    status_counts = {}
    total_with = 0
    total_without = 0

    for status, with_ei, without_ei in rows:
        status_counts[status] = {
            "with_ei": with_ei,
            "without_ei": without_ei,
        }
        total_with += with_ei
        total_without += without_ei

    # Get a sample of events with EI to verify it's working
    sample_result = await db.execute(
        select(Event.id, Event.home_team_name, Event.away_team_name, Event.raw_ei, Event.status)
        .where(Event.raw_ei.isnot(None))
        .order_by(Event.raw_ei.desc())
        .limit(5)
    )
    sample_events = [
        {
            "id": row[0],
            "matchup": f"{row[1]} vs {row[2]}",
            "ei_score": round(float(row[3]) * 100) if row[3] else None,
            "status": row[4],
        }
        for row in sample_result.all()
    ]

    return {
        "total": {
            "with_ei": total_with,
            "without_ei": total_without,
        },
        "by_status": status_counts,
        "completion_pct": round(total_with / (total_with + total_without) * 100, 1) if (total_with + total_without) > 0 else 0,
        "sample_events_with_ei": sample_events,
    }


@router.get("")
async def list_events(
    sport: Optional[str] = Query(None, description="Filter by sport key"),
    status: Optional[str] = Query(None, description="Filter by status"),
    days: int = Query(7, description="Number of days ahead to show"),
    limit: int = Query(200, ge=1, le=500, description="Max events to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db),
):
    """
    List upcoming and live events.

    Returns events with their current win probabilities.
    Memory-optimized: only fetches latest odds snapshot per event.
    """
    # Build query with explicit join to Sport for reliable filtering
    query = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .options(selectinload(Event.sport))
    )

    conditions = []

    if sport:
        conditions.append(Sport.key == sport)

    if status:
        conditions.append(Event.status == status)
    else:
        # Default: show scheduled, live, completed, and closed
        # "closed" = inferred completion via stale odds (Scores API didn't confirm)
        conditions.append(Event.status.in_(["scheduled", "live", "completed", "closed"]))

    # Date range - but always include live games regardless of start time
    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=days)
    # Include completed events from yesterday and today
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Show events that either:
    # 1. Are live (regardless of when they started), OR
    # 2. Are scheduled and start within the date range, OR
    # 3. Are completed/closed and started yesterday or today
    conditions.append(
        or_(
            Event.status == "live",
            and_(
                Event.status == "scheduled",
                Event.commence_time >= now,
                Event.commence_time <= end_date
            ),
            and_(
                Event.status.in_(["completed", "closed"]),
                Event.commence_time >= yesterday_start
            )
        )
    )

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(Event.commence_time).limit(limit).offset(offset)

    result = await db.execute(query)
    events = result.scalars().all()

    # Get the latest odds snapshots for each event, aggregated across bookmakers
    event_ids = [e.id for e in events]
    aggregated_odds_map = {}

    if event_ids:
        # Get the most recent snapshot per bookmaker per event
        # (deduplication means different bookmakers may have different latest times)

        # Subquery: rank snapshots by recency within each event+bookmaker group
        ranked_subq = (
            select(
                OddsSnapshot.id,
                OddsSnapshot.event_id,
                func.row_number().over(
                    partition_by=[OddsSnapshot.event_id, OddsSnapshot.bookmaker],
                    order_by=OddsSnapshot.captured_at.desc()
                ).label("rn")
            )
            .where(OddsSnapshot.event_id.in_(event_ids))
            .subquery()
        )

        # Get only the most recent snapshot per bookmaker per event (rn=1)
        latest_odds_query = (
            select(OddsSnapshot)
            .join(ranked_subq, and_(
                OddsSnapshot.id == ranked_subq.c.id,
                ranked_subq.c.rn == 1
            ))
        )

        latest_odds_result = await db.execute(latest_odds_query)
        all_snapshots = latest_odds_result.scalars().all()

        # Group snapshots by event and aggregate
        from collections import defaultdict
        snapshots_by_event = defaultdict(list)
        for snap in all_snapshots:
            snapshots_by_event[snap.event_id].append(snap)

        # Build event lookups for stale bookmaker filtering
        event_info_map = {e.id: e for e in events}

        for event_id, snaps in snapshots_by_event.items():
            ev = event_info_map.get(event_id)
            all_snaps = snaps  # Keep unfiltered for bookmaker table
            filtered_snaps = _filter_stale_bookmaker_snapshots(
                snaps,
                event_status=(ev.status if ev else "scheduled"),
                commence_time=(ev.commence_time if ev else None),
            )
            # Exclude bookmakers with reversed home/away odds from aggregation
            reversed_bks = detect_reversed_bookmakers(filtered_snaps)
            agg_snaps = [s for s in filtered_snaps if s.bookmaker not in reversed_bks] if reversed_bks else filtered_snaps
            latest_time = max(s.captured_at for s in filtered_snaps) if filtered_snaps else None
            aggregated_odds_map[event_id] = {
                "snapshots": filtered_snaps,
                "all_snapshots": all_snaps,
                "aggregated": aggregate_bookmaker_odds(agg_snaps if agg_snaps else filtered_snaps),
                "captured_at": latest_time,
            }

    # Load GEI percentiles for formatting
    gei_percentiles = await _load_gei_percentiles(db)

    # Build team lookup for colors/logos (single batch query for all teams)
    all_team_names = []
    for e in events:
        all_team_names.extend([e.home_team_name, e.away_team_name])
    team_lookup = await _build_team_lookup(db, list(set(all_team_names)))

    # Level 2: Compute time-series metrics for live events
    # Batch-query aggregated probabilities for all live event IDs
    live_event_ids = [e.id for e in events if e.status == "live"]
    ts_metrics_map: dict[int, object] = {}
    if live_event_ids:
        try:
            # Get median home_probability per 60-second time bucket per event
            # This reuses the same aggregation strategy as Pulse
            from sqlalchemy import text
            ts_query = text("""
                WITH bucketed AS (
                    SELECT
                        event_id,
                        date_trunc('minute', captured_at) AS bucket,
                        percentile_cont(0.5) WITHIN GROUP (ORDER BY home_win_probability) AS median_prob,
                        MIN(captured_at) AS bucket_time
                    FROM odds_snapshots
                    WHERE event_id = ANY(:event_ids)
                      AND home_win_probability IS NOT NULL
                    GROUP BY event_id, date_trunc('minute', captured_at)
                    ORDER BY event_id, bucket
                )
                SELECT event_id, median_prob, bucket_time
                FROM bucketed
            """)
            ts_result = await db.execute(ts_query, {"event_ids": live_event_ids})
            ts_rows = ts_result.fetchall()

            # Group by event_id
            from collections import defaultdict as _defaultdict
            event_buckets: dict[int, list] = _defaultdict(list)
            for row in ts_rows:
                event_buckets[row.event_id].append((float(row.median_prob), row.bucket_time))

            # Compute metrics for each event
            for eid, buckets in event_buckets.items():
                if len(buckets) >= 3:
                    probs = [b[0] for b in buckets]
                    timestamps = [b[1] for b in buckets]
                    ts_metrics_map[eid] = compute_time_series_metrics(probs, timestamps)
        except Exception:
            # Time-series metrics are a bonus — don't fail the whole endpoint
            pass

    # Format response with aggregated odds
    return {
        "events": [
            _format_event_with_aggregated_odds(
                e, aggregated_odds_map.get(e.id), gei_percentiles,
                team_lookup=team_lookup,
                time_series_metrics=ts_metrics_map.get(e.id),
            )
            for e in events
        ],
        "count": len(events),
    }


@router.get("/live")
async def list_live_events(db: AsyncSession = Depends(get_db)):
    """List currently live events."""
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(Event.status == "live")
        .order_by(Event.commence_time)
    )
    events = result.scalars().all()

    # Load GEI percentiles for formatting
    gei_percentiles = await _load_gei_percentiles(db)

    return {
        "events": [_format_event(e, gei_percentiles) for e in events],
        "count": len(events),
    }


@router.get("/live-odds/{sport_key}")
async def get_live_odds(sport_key: str):
    """
    Fetch live odds directly from API (not from database).

    Useful for real-time updates without waiting for the
    polling job. Use sparingly to conserve API quota.

    Returns both individual bookmaker odds and aggregated consensus.
    """
    try:
        snapshots = await fetch_current_odds(sport_key)

        # Group by event
        events_map = {}
        for snap in snapshots:
            if snap.event_id not in events_map:
                events_map[snap.event_id] = {
                    "event_id": snap.event_id,
                    "home_team": snap.home_team,
                    "away_team": snap.away_team,
                    "commence_time": snap.commence_time.isoformat(),
                    "bookmakers": [],
                    "_snapshots": [],  # Temporary for aggregation
                }

            # Calculate probability
            home_prob = None
            away_prob = None
            if snap.home_moneyline and snap.away_moneyline:
                home_prob, away_prob = moneyline_to_probability(
                    snap.home_moneyline, snap.away_moneyline
                )

            bookmaker_data = {
                "key": snap.bookmaker,
                "home_moneyline": snap.home_moneyline,
                "away_moneyline": snap.away_moneyline,
                "home_probability": round(home_prob, 4) if home_prob else None,
                "away_probability": round(away_prob, 4) if away_prob else None,
                "spread": snap.home_spread,
                "over_under": float(snap.over_under) if snap.over_under else None,
            }
            events_map[snap.event_id]["bookmakers"].append(bookmaker_data)

            # Store for aggregation
            events_map[snap.event_id]["_snapshots"].append({
                "home_win_probability": home_prob,
                "away_win_probability": away_prob,
                "over_under": snap.over_under,
                "home_spread": snap.home_spread,
            })

        # Add aggregated consensus to each event
        for event_data in events_map.values():
            aggregated = aggregate_bookmaker_odds(event_data["_snapshots"])
            event_data["consensus"] = {
                "home_probability": aggregated["home_probability"],
                "away_probability": aggregated["away_probability"],
                "over_under": aggregated["over_under"],
                "spread": aggregated["home_spread"],
                "bookmaker_count": aggregated["bookmaker_count"],
                "probability_range": {
                    "min": aggregated["min_home_probability"],
                    "max": aggregated["max_home_probability"],
                },
            }
            # Remove temporary storage
            del event_data["_snapshots"]

        return {
            "sport": sport_key,
            "events": list(events_map.values()),
            "count": len(events_map),
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to fetch odds: {str(e)}"
        )


@router.get("/{event_id}")
async def get_event(event_id: int, db: AsyncSession = Depends(get_db)):
    """Get event details with aggregated odds from all bookmakers."""
    import time as _time
    _now = _time.time()
    if event_id in _event_detail_cache:
        _cached_at, _cached_status, _cached_resp = _event_detail_cache[event_id]
        _ttl = _EVENT_DETAIL_LIVE_TTL if _cached_status == "live" else _EVENT_DETAIL_DEFAULT_TTL
        if _cached_status in ("completed", "closed") or _now - _cached_at < _ttl:
            return _cached_resp

    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Load only the latest odds snapshot per bookmaker (not ALL snapshots).
    # This prevents R14 memory errors on events with thousands of snapshots.
    ranked = (
        select(
            OddsSnapshot.id,
            func.row_number().over(
                partition_by=OddsSnapshot.bookmaker,
                order_by=OddsSnapshot.captured_at.desc(),
            ).label("rn"),
        )
        .where(OddsSnapshot.event_id == event_id)
        .subquery()
    )
    latest_ids_result = await db.execute(
        select(ranked.c.id).where(ranked.c.rn == 1)
    )
    latest_ids = [row[0] for row in latest_ids_result.fetchall()]
    if latest_ids:
        snap_result = await db.execute(
            select(OddsSnapshot).where(OddsSnapshot.id.in_(latest_ids))
        )
        latest_snapshots = list(snap_result.scalars().all())
    else:
        latest_snapshots = []

    # Load GEI percentiles for formatting
    gei_percentiles = await _load_gei_percentiles(db)

    # Build team lookup for colors/logos
    team_lookup = await _build_team_lookup(
        db, [event.home_team_name, event.away_team_name]
    )

    response = _format_event(event, gei_percentiles, team_lookup=team_lookup)

    # Compute deterministic tags, then merge in stored LLM-enriched tags
    # (competitive_structure, stakes, narrative, audience) from background enrichment.
    from app.utils.event_taxonomy import LLM_ENRICHMENT_NAMESPACES
    deterministic_tags = compute_event_tags(
        sport_key=event.sport.key if event.sport else "",
        status=event.status,
        commence_time=event.commence_time,
        llm_importance=getattr(event, "llm_importance", None),
        llm_gender=getattr(event, "llm_gender", None),
        llm_level=getattr(event, "llm_level", None),
        llm_league=getattr(event, "llm_league", None),
        raw_ei=float(event.raw_ei) if event.raw_ei else None,
        broadcast_info=getattr(event, "broadcast_info", None),
    )
    # Preserve LLM-enriched tags from the stored event_tags
    stored_tags = event.event_tags or []
    llm_tags = [t for t in stored_tags if t.split(":")[0] in LLM_ENRICHMENT_NAMESPACES]
    response["event_tags"] = sorted(set(deterministic_tags) | set(llm_tags))

    # Compute standings context for event detail
    standings_context = _compute_standings_context(
        team_lookup.get(event.home_team_name),
        team_lookup.get(event.away_team_name),
        event.home_team_name,
        event.away_team_name,
    )
    if standings_context:
        response["standings_context"] = standings_context

    # Use compute_aggregate_probability() as primary probability source,
    # matching the feed endpoint. This blends all sources (sportsbooks, ESPN,
    # Kalshi, Polymarket, stat model) with SOURCE_WEIGHTS for consistency.
    from app.utils.aggregation import compute_aggregate_probability
    agg_prob = compute_aggregate_probability(event)

    if latest_snapshots:
        # latest_snapshots already contains only the most recent per bookmaker
        all_latest_snapshots = latest_snapshots

        # Filter for aggregation: exclude pre-game-only bookmakers from consensus
        filtered_snapshots = _filter_stale_bookmaker_snapshots(
            all_latest_snapshots,
            event_status=event.status,
            commence_time=event.commence_time,
        )
        latest_time = max(s.captured_at for s in filtered_snapshots)

        # Detect bookmakers with reversed home/away odds
        reversed_bookmakers = detect_reversed_bookmakers(filtered_snapshots)

        # Aggregate across bookmakers (exclude reversed ones) — used for
        # spread, over/under, projected scores, and bookmaker count.
        agg_snapshots = [s for s in filtered_snapshots if s.bookmaker not in reversed_bookmakers]
        if not agg_snapshots:
            agg_snapshots = filtered_snapshots  # fallback: use all if all were flagged
        aggregated = aggregate_bookmaker_odds(agg_snapshots)

        # Hero probability: use multi-source aggregate (matching feed),
        # fall back to bookmaker-only consensus if aggregate unavailable.
        hero_home_prob = agg_prob if agg_prob is not None else aggregated["home_probability"]
        hero_away_prob = round(1.0 - hero_home_prob, 6) if hero_home_prob is not None else aggregated["away_probability"]

        response["current_odds"] = {
            "captured_at": latest_time.isoformat(),
            "home_probability": hero_home_prob,
            "away_probability": hero_away_prob,
            "spread": aggregated["home_spread"],
            "over_under": aggregated["over_under"],
            "projected_home_score": aggregated["projected_home_score"],
            "projected_away_score": aggregated["projected_away_score"],
            "bookmaker_count": aggregated["bookmaker_count"],
            "probability_range": {
                "min": aggregated["min_home_probability"],
                "max": aggregated["max_home_probability"],
            },
        }

        # Show ALL bookmakers in the table (not just filtered ones)
        # so users see every book we ever had odds from.
        # Detect reversed bookmakers across all snapshots for display correction.
        all_reversed = detect_reversed_bookmakers(all_latest_snapshots)
        bookmaker_odds_list = []
        for s in all_latest_snapshots:
            if s.bookmaker in all_reversed:
                bookmaker_odds_list.append({
                    "bookmaker": s.bookmaker,
                    "home_moneyline": s.away_moneyline,
                    "away_moneyline": s.home_moneyline,
                    "home_probability": float(s.away_win_probability)
                        if s.away_win_probability else None,
                    "away_probability": float(s.home_win_probability)
                        if s.home_win_probability else None,
                    "captured_at": s.captured_at.isoformat(),
                    "spread": -float(s.home_spread) if s.home_spread else None,
                    "over_under": float(s.over_under) if s.over_under else None,
                    "projected_home_score": float(s.projected_away_score)
                        if s.projected_away_score else None,
                    "projected_away_score": float(s.projected_home_score)
                        if s.projected_home_score else None,
                })
            else:
                bookmaker_odds_list.append({
                    "bookmaker": s.bookmaker,
                    "home_moneyline": s.home_moneyline,
                    "away_moneyline": s.away_moneyline,
                    "home_probability": float(s.home_win_probability)
                        if s.home_win_probability else None,
                    "away_probability": float(s.away_win_probability)
                        if s.away_win_probability else None,
                    "captured_at": s.captured_at.isoformat(),
                    "spread": float(s.home_spread) if s.home_spread else None,
                    "over_under": float(s.over_under) if s.over_under else None,
                    "projected_home_score": float(s.projected_home_score)
                        if s.projected_home_score else None,
                    "projected_away_score": float(s.projected_away_score)
                        if s.projected_away_score else None,
                })
        response["bookmaker_odds"] = bookmaker_odds_list

    # Fallback: if no odds snapshots, use aggregate from alternative sources
    if "current_odds" not in response and agg_prob is not None:
        response["current_odds"] = {
            "home_probability": agg_prob,
            "away_probability": round(1.0 - agg_prob, 6),
            "source": "aggregate",
            "bookmaker_count": 0,
        }

    # Include opening odds in event detail response for frontend fallback
    if event.opening_home_probability is not None:
        response["opening_odds"] = {
            "home_probability": float(event.opening_home_probability),
            "away_probability": float(event.opening_away_probability) if event.opening_away_probability else round(1.0 - float(event.opening_home_probability), 4),
            "favorite": event.opening_favorite,
        }

    # Box score data for player props display
    if event.box_score_data and not event.box_score_data.get("error"):
        response["box_score_data"] = {
            "players": event.box_score_data.get("players"),
        }

    if len(_event_detail_cache) >= _EVENT_DETAIL_MAX_SIZE:
        oldest = min(_event_detail_cache, key=lambda k: _event_detail_cache[k][0])
        del _event_detail_cache[oldest]
    _event_detail_cache[event_id] = (_now, event.status, response)

    return response


# ── Scoring play extraction from StatPal play-by-play data ──────────────────

_SCORING_PLAY_TYPES = {
    "touchdown", "field_goal", "safety", "extra_point", "two_point_conversion",
    "goal", "power_play_goal", "shorthanded_goal", "empty_net_goal",
    "three_pointer", "dunk", "layup", "free_throw", "basket", "shot",
    "home_run", "rbi_single", "rbi_double", "rbi_triple", "sacrifice_fly",
    "run", "scoring", "score", "penalty_goal", "own_goal",
}


def _assign_wall_clock_timestamps(
    espn_plays: list[dict],
    espn_history: list[dict],
) -> list[dict]:
    """Map ESPN scoring plays to wall-clock timestamps.

    ESPN scoring plays have period + clock (game time) but no wall-clock time.
    We find the first ESPN snapshot where (home_score, away_score) matches the
    post-play score. That snapshot's captured_at ≈ the play's wall-clock time.

    Falls back to ordering-based interpolation when no snapshot match is found.
    """
    if not espn_plays:
        return []

    result = []

    # Build index of (home_score, away_score) → first matching timestamp
    score_to_timestamp: dict[tuple[int, int], str] = {}
    for snap in espn_history:
        hs = snap.get("home_score")
        aw = snap.get("away_score")
        if hs is not None and aw is not None:
            key = (int(hs), int(aw))
            if key not in score_to_timestamp:
                score_to_timestamp[key] = snap["timestamp"]

    # Track last assigned timestamp for fallback ordering
    last_timestamp = espn_history[0]["timestamp"] if espn_history else None

    for play in espn_plays:
        home_score = play.get("home_score")
        away_score = play.get("away_score")

        timestamp = None
        if home_score is not None and away_score is not None:
            timestamp = score_to_timestamp.get((int(home_score), int(away_score)))

        if not timestamp:
            timestamp = last_timestamp

        if timestamp:
            last_timestamp = timestamp

        # Format period display string
        period = play.get("period")
        period_str = None
        if period is not None:
            period_str = str(period)

        result.append({
            "timestamp": timestamp,
            "description": play.get("description", ""),
            "short_text": play.get("short_text", ""),
            "team": play.get("team", ""),
            "type": play.get("type", ""),
            "home_score": home_score,
            "away_score": away_score,
            "period": period_str,
            "clock": play.get("clock"),
        })

    return [p for p in result if p["timestamp"]]


def extract_scoring_plays(raw_plays: list[dict]) -> list[dict]:
    """
    Filter StatPal play-by-play data to scoring plays with timestamps.

    Only returns plays that have a captured_at timestamp (needed for chart placement)
    and match scoring play types.
    """
    scoring_plays = []
    for play in raw_plays:
        play_type = (play.get("type") or "").lower()
        is_scoring = (
            play_type in _SCORING_PLAY_TYPES
            or "score" in play_type
            or "goal" in play_type
            or "touchdown" in play_type
        )
        if is_scoring and play.get("captured_at"):
            scoring_plays.append({
                "timestamp": play["captured_at"],
                "description": play.get("description", ""),
                "team": play.get("team", ""),
                "type": play.get("type", ""),
                "home_score": play.get("home_score"),
                "away_score": play.get("away_score"),
                "period": play.get("period"),
                "clock": play.get("clock"),
            })
    return scoring_plays


# Regex patterns for detecting game-specific markets (stat props and matchups).
# These are compiled once at module level, not per-request.
_GAME_STAT_PROP_RE = re.compile(
    r":\s*(?:points|assists|rebounds|steals|blocks|three\s*pointers?|"
    r"3-?pointers?|turnovers|strikeouts|hits|runs|home\s*runs|goals|"
    r"saves|sacks|passing\s*yards|rushing\s*yards|receiving\s*yards|"
    r"touchdowns|completions|interceptions|aces|double\s*faults|kills|"
    r"double\s*doubles?|triple\s*doubles?)",
    re.IGNORECASE,
)
_GAME_MATCHUP_RE = re.compile(
    r"\bvs\.?\s|\s–\s|\bat\b.*:\s*\w|^[\w][\w\s.'\-()]+\bat\b\s+[\w][\w\s.'\-()]+$",
    re.IGNORECASE,
)


def _escape_like(s: str) -> str:
    """Escape special LIKE/ILIKE characters for safe pattern matching."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _team_name_patterns(full_name: str) -> list[str]:
    """Build ILIKE-safe patterns for matching a team in outcome names.

    Returns escaped patterns suitable for use in ILIKE '%pattern%' queries.
    Includes full name, city/location, and mascot/short name.

    Examples:
        "Texas Rangers" → ["Texas Rangers", "Rangers", "Texas"]
        "Los Angeles Dodgers" → ["Los Angeles Dodgers", "Dodgers", "Los Angeles"]
        "New York Yankees" → ["New York Yankees", "Yankees", "New York"]
        "Athletics" → ["Athletics"]
    """
    if not full_name:
        return []

    patterns = []
    escaped_full = _escape_like(full_name.strip())
    patterns.append(escaped_full)

    parts = full_name.strip().split()
    if len(parts) > 1:
        # Mascot/short name: last word (e.g., "Celtics" from "Boston Celtics")
        short = parts[-1]
        if len(short) >= 4:
            escaped_short = _escape_like(short)
            if escaped_short.lower() != escaped_full.lower():
                patterns.append(escaped_short)

        # City/location name: first word(s) (e.g., "Texas" from "Texas Rangers",
        # "Los Angeles" from "Los Angeles Dodgers")
        # Kalshi uses city names as outcome labels ("Texas", "Houston", "Seattle")
        city = " ".join(parts[:-1])
        if len(city) >= 4:
            escaped_city = _escape_like(city)
            if escaped_city.lower() not in [p.lower() for p in patterns]:
                patterns.append(escaped_city)

        # For multi-word cities ("Boston Red", "New York"), also add
        # individual words ≥4 chars. Kalshi uses just "Boston" not "Boston Red".
        if len(parts) >= 3:
            for word in parts[:-1]:
                if len(word) >= 4:
                    escaped_word = _escape_like(word)
                    if escaped_word.lower() not in [p.lower() for p in patterns]:
                        patterns.append(escaped_word)

    return patterns


# ── Regex helpers for game-market classification ────────────────────────
_TOTAL_RE = re.compile(
    r"(?:total|over|under|o/u)\b",
    re.IGNORECASE,
)
_SPREAD_RE = re.compile(
    r"(?:spread|margin|handicap)\b",
    re.IGNORECASE,
)
_PLAYER_PROP_RE = re.compile(
    r"(?:points|assists|rebounds|steals|blocks|three.?pointers?|3.?pointers?|"
    r"turnovers|strikeouts|hits|runs|home.?runs|goals|saves|sacks|"
    r"passing.?yards|rushing.?yards|receiving.?yards|touchdowns|"
    r"PRA|PA|PR|RA|double.?doubles?|triple.?doubles?|first.?basket)\b",
    re.IGNORECASE,
)
_THRESHOLD_RE = re.compile(r"(\d+(?:\.\d+)?)")

# Matches per-player outcome names inside team stat markets.
# Kalshi uses "PlayerName: X+" format for individual player contracts
# within team-level markets (e.g., "Joel Embiid: 1+" inside "Team at Team: Steals").
# Requires at least two name tokens (first + last) before ": digit".
# Handles apostrophes (De'Aaron), hyphens (Gilgeous-Alexander), suffixes (Jr.).
_PLAYER_OUTCOME_RE = re.compile(
    r"^[A-Z][A-Za-z']+(?:-[A-Z][A-Za-z']+)*"
    r"(?:\s+[A-Z][A-Za-z'.]+(?:-[A-Z][A-Za-z']+)*)+\s*:\s*\d",
)


def _is_team_stat_market(name: str) -> bool:
    """Check if this is a team-level stat market (not a player prop).

    Team stat markets have patterns like "Cleveland at LA: Points" where
    the part after the colon is ONLY a stat word. Player props have a
    player name before the stat: "Cleveland at LA: Trae Young Points".
    """
    colon_idx = name.find(":")
    if colon_idx < 0:
        return False
    after_colon = name[colon_idx + 1:].strip()
    # If the text after the colon is JUST a stat word (with optional whitespace),
    # it's a team stat market, not a player prop
    return bool(re.fullmatch(
        r"(?:points|assists|rebounds|steals|blocks|three.?pointers?|3.?pointers?|"
        r"turnovers|strikeouts|hits|runs|home.?runs|goals|saves|sacks|"
        r"passing.?yards|rushing.?yards|receiving.?yards|touchdowns|kills|"
        r"double.?doubles?|triple.?doubles?)",
        after_colon,
        re.IGNORECASE,
    ))


def _classify_game_market(name: str, external_id: Optional[str] = None) -> str:
    """Classify a game-level market name into a type.

    Distinguishes team-level stat markets ("Cleveland at LA: Rebounds")
    from player props ("Trae Young Points") by checking whether the
    stat word is the ENTIRE content after the colon (team stat) vs.
    having a player name before it (player prop).

    Falls back to the Kalshi ticker prefix (``external_id``) when the
    market *name* doesn't contain explicit period markers such as "1st
    Half" or "2H".  Kalshi uses tickers like ``KXNBA2HSPREAD-…`` even
    though the event title is just "Celtics at Warriors".
    """
    lower = name.lower()

    _HALF_PATTERNS = ("1st half", "1h", "2nd half", "2h", "first half", "second half",
                      "first 5 innings", "f5 innings", "f5",
                      "first inning", "1st inning")
    _QUARTER_PATTERNS = ("1st quarter", "2nd quarter", "3rd quarter", "4th quarter",
                         "1q", "2q", "3q", "4q")

    # Head-to-head and 3-ball matchups (golf)
    if any(x in lower for x in ("head-to-head", "h2h", "head to head")):
        return "h2h"
    # "matchup" alone is too generic (used in team vs team contexts),
    # only classify as h2h when combined with golf-specific signals
    if "matchup" in lower and any(x in lower for x in ("golf", "vs.", "vs ")):
        return "h2h"
    if any(x in lower for x in ("3-ball", "3ball", "three-ball", "three ball", "3 ball")):
        return "3ball"

    # Totals first — "Total Points" is a total, not a player prop
    if "total" in lower or "o/u" in lower:
        if "team" in lower:
            return "team_total"
        if any(x in lower for x in _HALF_PATTERNS):
            return "half_total"
        if any(x in lower for x in _QUARTER_PATTERNS):
            return "quarter_total"
        # Name says "total" but no period marker — check ticker for period
        ticker_type = _classify_from_ticker(external_id) if external_id else None
        if ticker_type and ticker_type.endswith("_total"):
            return ticker_type  # half_total or quarter_total
        return "game_total"
    # Over/Under without "total" — check if it's a player prop or game total
    if "over" in lower or "under" in lower:
        # If a stat word precedes "Over/Under", it's a player prop
        # e.g., "Rebounds Over 8.5" vs just "Over 224.5"
        if _PLAYER_PROP_RE.search(name) and not _is_team_stat_market(name):
            return "player_prop"
        return "game_total"
    if "spread" in lower or "margin" in lower or "handicap" in lower:
        if any(x in lower for x in _HALF_PATTERNS):
            return "half_spread"
        if any(x in lower for x in _QUARTER_PATTERNS):
            return "quarter_spread"
        # Name says "spread" but no period marker — check ticker
        ticker_type = _classify_from_ticker(external_id) if external_id else None
        if ticker_type and ticker_type.endswith("_spread"):
            return ticker_type  # half_spread or quarter_spread
        return "spread"
    # Team-level stat markets: "Team at Team: Points" (no player name)
    if _is_team_stat_market(name):
        return "team_total"
    # Player props without over/under (e.g., "Trae Young Points")
    if _PLAYER_PROP_RE.search(name):
        return "player_prop"
    if "moneyline" in lower or "winner" in lower or "win" in lower:
        if any(x in lower for x in _HALF_PATTERNS):
            return "half_winner"
        if any(x in lower for x in _QUARTER_PATTERNS):
            return "quarter_winner"
        # Name says "winner" but no period marker — check ticker
        ticker_type = _classify_from_ticker(external_id) if external_id else None
        if ticker_type and ticker_type.endswith("_winner"):
            return ticker_type  # half_winner or quarter_winner
        return "moneyline"

    # ── Ticker-only fallback ───────────────────────────────────────────
    # Market name has no recognizable keywords at all.  Derive entirely
    # from the Kalshi ticker prefix when available.
    if external_id:
        ticker_type = _classify_from_ticker(external_id)
        if ticker_type != "other":
            return ticker_type
    return "other"


# Ticker-prefix → market type mapping.  Built once at import time so
# the hot path in _classify_game_market does a cheap dict lookup.
_KALSHI_PERIOD_LEAGUE_PREFIXES = (
    "nba", "nfl", "nhl", "mlb", "wnba", "mls", "ncaab", "ncaamb", "ncaaf"
)

_TICKER_PERIOD_MAP: dict[str, str] = {}
for _league in _KALSHI_PERIOD_LEAGUE_PREFIXES:
    for _h in ("1h", "2h"):
        _TICKER_PERIOD_MAP[f"kx{_league}{_h}total"] = "half_total"
        _TICKER_PERIOD_MAP[f"kx{_league}{_h}spread"] = "half_spread"
        _TICKER_PERIOD_MAP[f"kx{_league}{_h}winner"] = "half_winner"
    for _q in ("1q", "2q", "3q", "4q"):
        _TICKER_PERIOD_MAP[f"kx{_league}{_q}total"] = "quarter_total"
        _TICKER_PERIOD_MAP[f"kx{_league}{_q}spread"] = "quarter_spread"
        _TICKER_PERIOD_MAP[f"kx{_league}{_q}winner"] = "quarter_winner"


def _classify_from_ticker(external_id: str) -> str:
    """Derive market type from a Kalshi external_id (ticker).

    Returns a period-specific type (half_spread, quarter_total, …) or
    "other" if the ticker doesn't match any known period prefix.
    """
    ticker_lower = external_id.lower()
    for prefix, mtype in _TICKER_PERIOD_MAP.items():
        if ticker_lower.startswith(prefix):
            return mtype
    # Catch-all for base types when no period prefix matched.
    if "spread" in ticker_lower:
        return "spread"
    if "total" in ticker_lower:
        return "game_total"
    if "winner" in ticker_lower or "game" in ticker_lower:
        return "moneyline"
    return "other"


# Ticker-prefix → period label.  Built once at import time alongside
# _TICKER_PERIOD_MAP so _extract_period_from_ticker is a cheap dict lookup.
_TICKER_PERIOD_LABEL: dict[str, str] = {}
for _league2 in _KALSHI_PERIOD_LEAGUE_PREFIXES:
    for _h2 in ("1h", "2h"):
        for _kind in ("total", "spread", "winner"):
            _TICKER_PERIOD_LABEL[f"kx{_league2}{_h2}{_kind}"] = _h2.upper()
    for _q2 in ("1q", "2q", "3q", "4q"):
        for _kind in ("total", "spread", "winner"):
            _TICKER_PERIOD_LABEL[f"kx{_league2}{_q2}{_kind}"] = _q2.upper()


def _extract_period_from_ticker(external_id: Optional[str]) -> Optional[str]:
    """Return the period label ("1H", "2H", "1Q"–"4Q") from a Kalshi ticker.

    Returns ``None`` when the ticker is absent or doesn't encode a period.
    """
    if not external_id:
        return None
    ticker_lower = external_id.lower()
    for prefix, label in _TICKER_PERIOD_LABEL.items():
        if ticker_lower.startswith(prefix):
            return label
    return None


def _extract_period_from_name(market_name: str, outcome_name: str) -> Optional[str]:
    """Derive period label from market or outcome name text.

    Fallback for non-Kalshi markets (e.g., Polymarket) where there is no
    ticker prefix.  Returns ``None`` when no period is detected.
    """
    text = f"{outcome_name} {market_name}".lower()
    if "1st half" in text or "first half" in text or "first 5" in text:
        return "1H"
    # Check for "1h" carefully – avoid false-positives on words like "1hr"
    if re.search(r'\b1h\b', text):
        return "1H"
    if "2nd half" in text or "second half" in text:
        return "2H"
    if re.search(r'\b2h\b', text):
        return "2H"
    for q_label, q_pattern in [("1Q", "1st quarter"), ("2Q", "2nd quarter"),
                                ("3Q", "3rd quarter"), ("4Q", "4th quarter")]:
        if q_pattern in text or re.search(rf'\b{q_label.lower()}\b', text):
            return q_label
    return None


def _extract_threshold(outcome_name: str) -> Optional[float]:
    """Extract the numeric threshold from an outcome name like 'Over 224.5'."""
    m = _THRESHOLD_RE.search(outcome_name)
    return float(m.group(1)) if m else None


def _estimate_game_pace(
    home_score: Optional[int],
    away_score: Optional[int],
    period: Optional[str],
    game_clock: Optional[str],
    sport_key: Optional[str],
) -> Optional[dict]:
    """Estimate current scoring pace for total points spectrum.

    Returns {total_scored, projected_total, fraction_elapsed, time_remaining_display}
    or None if insufficient data.
    """
    if home_score is None or away_score is None:
        return None
    total_scored = home_score + away_score

    # Parse sport-specific game duration
    sport_prefix = (sport_key or "").split("_")[0]
    total_minutes = {"basketball": 48, "americanfootball": 60, "icehockey": 60, "baseball": 54}.get(sport_prefix)
    if total_minutes is None:
        return None

    # Parse elapsed time from period + clock
    if not period:
        return None

    period_str = period.lower().strip()
    # Strip clock prefix like "6:55 - 3rd Quarter"
    if " - " in period_str:
        period_str = period_str.split(" - ", 1)[-1].strip()

    # Basketball quarters
    quarter_map = {"1st quarter": 1, "q1": 1, "2nd quarter": 2, "q2": 2,
                   "3rd quarter": 3, "q3": 3, "4th quarter": 4, "q4": 4}
    half_map = {"1st half": 1, "halftime": 2, "ht": 2, "2nd half": 2}
    # Football quarters (same)
    # Hockey periods
    hockey_map = {"1st period": 1, "p1": 1, "2nd period": 2, "p2": 2, "3rd period": 3, "p3": 3}

    elapsed_minutes = None
    period_minutes = total_minutes / 4 if sport_prefix in ("basketball", "americanfootball") else total_minutes / 3

    for label, num in {**quarter_map, **hockey_map}.items():
        if label in period_str:
            # Parse remaining clock time
            clock_remaining = 0
            if game_clock:
                parts = game_clock.replace(":", " ").split()
                try:
                    if len(parts) >= 2:
                        clock_remaining = int(parts[0]) + int(parts[1]) / 60
                    elif len(parts) == 1:
                        clock_remaining = float(parts[0])
                except (ValueError, IndexError):
                    pass
            elapsed_minutes = (num - 1) * period_minutes + (period_minutes - clock_remaining)
            break

    for label, num in half_map.items():
        if label in period_str:
            half_minutes = total_minutes / 2
            # Halftime/HT means exactly half is done, no clock needed
            if label in ("halftime", "ht"):
                elapsed_minutes = half_minutes
                break
            clock_remaining = 0
            if game_clock:
                parts = game_clock.replace(":", " ").split()
                try:
                    if len(parts) >= 2:
                        clock_remaining = int(parts[0]) + int(parts[1]) / 60
                    elif len(parts) == 1:
                        clock_remaining = float(parts[0])
                except (ValueError, IndexError):
                    pass
            elapsed_minutes = (num - 1) * half_minutes + (half_minutes - clock_remaining)
            break

    if "ot" in period_str or "overtime" in period_str:
        elapsed_minutes = float(total_minutes)

    if elapsed_minutes is None or elapsed_minutes <= 0:
        return None

    fraction = min(elapsed_minutes / total_minutes, 1.0)
    projected = round(total_scored / fraction) if fraction > 0.05 else None
    remaining = max(total_minutes - elapsed_minutes, 0)
    mins_left = int(remaining)
    secs_left = int((remaining - mins_left) * 60)

    return {
        "total_scored": total_scored,
        "projected_total": projected,
        "fraction_elapsed": round(fraction, 3),
        "time_remaining_display": f"{mins_left}:{secs_left:02d} left",
    }


@router.get("/{event_id}/game-markets")
async def get_game_markets(
    event_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get game-level markets for an event (totals spectrum, player props, spreads).

    Returns markets linked via FuturesMarket.event_id OR matching event teams
    in game-prop markets.
    """
    import time as _time
    from app.models import FuturesOddsSnapshot

    # Check in-memory cache (completed games cached indefinitely, live 30s)
    now_ts = _time.time()
    if event_id in _game_markets_cache:
        cached_ts, cached_status, cached_response = _game_markets_cache[event_id]
        is_final = cached_status in ("completed", "closed")
        if is_final or (now_ts - cached_ts) < _GAME_MARKETS_LIVE_TTL:
            return cached_response

    # 1. Load event with sport
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    sport_key = event.sport.key if event.sport else None

    expected_category = None
    if sport_key:
        prefix = sport_key.split("_")[0]
        expected_category = SPORT_PREFIX_TO_LLM_CATEGORY.get(prefix)

    # 2. Find game-level markets linked to this event
    # Trust linked markets for status — if the matching task set event_id,
    # don't filter by status (resolved markets on completed games should show).
    # BUT do enforce sport compatibility as a safety net against cross-sport
    # mislinkage (e.g., baseball World Series market linked to a cricket event).
    # Sport filtering uses sport_id OR llm_sport_category — either must match.
    event_is_finished = event.status in ("completed", "closed")
    linked_filters = [FuturesMarket.event_id == event_id]
    if event.sport_id and expected_category:
        # Safety net: only show markets whose sport matches the event's sport.
        # Uses OR(sport_id match, llm_sport_category match, both NULL) to avoid
        # dropping markets with incomplete metadata while still blocking cross-sport.
        linked_filters.append(
            or_(
                FuturesMarket.sport_id == event.sport_id,
                FuturesMarket.llm_sport_category == expected_category,
                and_(
                    FuturesMarket.sport_id.is_(None),
                    FuturesMarket.llm_sport_category.is_(None),
                ),
            )
        )
    linked_query = select(FuturesMarket).where(*linked_filters)
    market_result = await db.execute(linked_query)
    markets = list(market_result.scalars().all())

    # Status filter — only used for the FALLBACK (unlinked) query below.
    status_filter = (
        FuturesMarket.status.in_(("open", "resolved", "closed"))
        if event_is_finished
        else or_(FuturesMarket.status == "open", FuturesMarket.status.is_(None))
    )

    # 3. Also find unlinked game-prop markets matching team names + time window
    # Require BOTH teams to appear in the market name to prevent cross-event
    # contamination (e.g., "Minnesota vs New York M" leaking onto a NYY vs BOS game).
    if sport_key and event.commence_time:
        home_patterns = _team_name_patterns(event.home_team_name)
        away_patterns = _team_name_patterns(event.away_team_name)
        home_conditions = [FuturesMarket.name.ilike(f"%{p}%") for p in home_patterns if len(p) >= 4]
        away_conditions = [FuturesMarket.name.ilike(f"%{p}%") for p in away_patterns if len(p) >= 4]

        if home_conditions and away_conditions:
            window = timedelta(hours=6)
            sport_conditions = []
            if event.sport_id:
                sport_conditions.append(FuturesMarket.sport_id == event.sport_id)
            if expected_category:
                sport_conditions.append(FuturesMarket.llm_sport_category == expected_category)

            sport_filter = or_(*sport_conditions) if sport_conditions else True

            # Accept markets tagged as game_prop OR with game-level ticker prefixes.
            # Moneylines ("Winner?") may not get category="game_prop" but DO have
            # game-level tickers like KXMLBGAME, KXNBAGAME, etc.
            from app.utils.sport_keys import KALSHI_TICKER_TO_SPORT_KEY
            game_ticker_conditions = [
                FuturesMarket.external_id.ilike(f"{prefix}%")
                for prefix in KALSHI_TICKER_TO_SPORT_KEY
                if KALSHI_TICKER_TO_SPORT_KEY[prefix] == sport_key
            ]
            category_or_ticker = [FuturesMarket.category == "game_prop"]
            if game_ticker_conditions:
                category_or_ticker.extend(game_ticker_conditions)

            # Time window: only match markets whose commence_time is within ±12h
            # of this event. Prevents Game 1's 1H total from leaking into Game 3.
            time_lower = event.commence_time - timedelta(hours=12)
            time_upper = event.commence_time + timedelta(hours=12)

            # Also find Polymarket sub-markets via parent group_id.
            # Polymarket series events (e.g., "Celtics vs. 76ers") contain sub-markets
            # like "O/U 196.5" that don't include team names. We find the parent by
            # team name match, then pull all sub-markets from the same group.
            poly_parent_result = await db.execute(
                select(FuturesMarket.group_id)
                .where(
                    FuturesMarket.source == "polymarket",
                    FuturesMarket.group_id.isnot(None),
                    FuturesMarket.group_type.in_(["polymarket_event", "negrisk"]),
                    or_(*home_conditions),
                    or_(*away_conditions),
                    or_(
                        and_(
                            FuturesMarket.commence_time >= time_lower,
                            FuturesMarket.commence_time <= time_upper,
                        ),
                        FuturesMarket.commence_time.is_(None),
                    ),
                )
                .limit(5)
            )
            poly_group_ids = [r[0] for r in poly_parent_result.all() if r[0]]

            if poly_group_ids:
                existing_ids = {m.id for m in markets}
                poly_sub_result = await db.execute(
                    select(FuturesMarket)
                    .where(
                        FuturesMarket.source == "polymarket",
                        FuturesMarket.group_id.in_(poly_group_ids),
                        FuturesMarket.group_type == "polymarket_sub_market",
                        status_filter,
                    )
                )
                for sub in poly_sub_result.scalars().all():
                    if sub.id not in existing_ids:
                        markets.append(sub)
                        existing_ids.add(sub.id)

            unlinked_result = await db.execute(
                select(FuturesMarket)
                .where(
                    FuturesMarket.event_id.is_(None),
                    status_filter,
                    or_(*category_or_ticker),
                    sport_filter,
                    or_(*home_conditions),
                    or_(*away_conditions),
                    or_(
                        and_(
                            FuturesMarket.commence_time >= time_lower,
                            FuturesMarket.commence_time <= time_upper,
                        ),
                        FuturesMarket.commence_time.is_(None),
                    ),
                )
            )
            linked_ids = {m.id for m in markets}
            for m in unlinked_result.scalars().all():
                if m.id not in linked_ids:
                    markets.append(m)

    if not markets:
        return {"event_id": event_id, "totals": [], "player_props": [], "spreads": [], "matchups": [], "other": [], "pace": None}

    # 4. Load outcomes for all markets
    market_ids = [m.id for m in markets]
    outcomes_result = await db.execute(
        select(FuturesOutcome)
        .where(FuturesOutcome.market_id.in_(market_ids))
        .order_by(FuturesOutcome.current_probability.desc().nullslast())
    )
    outcomes = outcomes_result.scalars().all()

    # Build market_id → market lookup
    market_map = {m.id: m for m in markets}

    # 5. Classify and group
    #
    # Period markets (half_spread, half_total, quarter_*, half_winner,
    # quarter_winner) are all routed into period_markets[].  The frontend
    # currently renders half_spread as margin maps and half_total as total
    # maps for both 1H and 2H.  half_winner/quarter_winner entries are
    # included in the response but the frontend does not yet have a
    # dedicated visualization for binary period winner markets — they
    # appear only when a frontend component iterates period_markets
    # generically (a known display gap, not a data gap).
    totals_thresholds: list[dict] = []
    player_props: list[dict] = []
    spreads: list[dict] = []
    period_markets: list[dict] = []
    matchups: list[dict] = []
    other_markets: list[dict] = []

    # Group outcomes by market
    from collections import defaultdict
    outcomes_by_market: dict[int, list] = defaultdict(list)
    for o in outcomes:
        outcomes_by_market[o.market_id].append(o)

    for market in markets:
        market_outcomes = outcomes_by_market.get(market.id, [])
        if not market_outcomes:
            continue

        market_type = _classify_game_market(market.name, external_id=market.external_id)

        # Determine period label ("1H", "2H", "1Q"–"4Q") for period markets.
        # Ticker is authoritative; fall back to name-based detection.
        market_period: Optional[str] = None
        if market_type.startswith("half_") or market_type.startswith("quarter_"):
            market_period = _extract_period_from_ticker(market.external_id)
            if market_period is None:
                market_period = _extract_period_from_name(market.name, "")

        if market_type in ("game_total", "half_total", "quarter_total", "team_total"):
            # Extract thresholds with probabilities
            for o in market_outcomes:
                threshold = _extract_threshold(o.name)
                if threshold is None:
                    continue
                name_lower = o.name.lower().strip()
                is_over = (
                    name_lower.startswith("over")
                    or "yes" in name_lower
                    or re.match(r'^\d+\+', name_lower)  # "2+", "3+" = threshold-style over
                )
                is_under = name_lower.startswith("under") or name_lower == "no"
                prob = float(o.current_probability) if o.current_probability is not None else None
                if prob is None:
                    continue
                # For "Under X", convert to "probability of going OVER"
                # For threshold outcomes ("2+", "3+"), prob IS the over probability
                over_prob = prob if is_over or not is_under else 1.0 - prob

                # Detect player props hiding inside team_total markets.
                # Kalshi names markets "Team at Team: Steals" but outcomes
                # are per-player: "Joel Embiid: 1+". Route these to player_props.
                if market_type == "team_total" and _PLAYER_OUTCOME_RE.match(o.name):
                    tt_opening_over = None
                    if o.opening_probability is not None:
                        tt_op = float(o.opening_probability)
                        tt_opening_over = round(tt_op if is_over or not is_under else 1.0 - tt_op, 4)
                    player_props.append({
                        "market_name": market.name,
                        "outcome_name": o.name,
                        "threshold": threshold,
                        "over_probability": round(over_prob, 4),
                        "opening_over_probability": tt_opening_over,
                        "source": market.source,
                        "movement": round(float(o.current_probability) - float(o.opening_probability), 4)
                            if o.opening_probability is not None and o.current_probability is not None else None,
                    })
                    continue

                totals_thresholds.append({
                    "threshold": threshold,
                    "over_probability": round(over_prob, 4),
                    "source": market.source,
                    "market_type": market_type,
                    "market_name": market.name,
                    "outcome_name": o.name,
                    "movement": round(float(o.current_probability) - float(o.opening_probability), 4)
                        if o.opening_probability is not None and o.current_probability is not None else None,
                    "period": market_period,
                    "_market_id": market.id,
                    "_external_id": market.external_id,
                })

        elif market_type == "player_prop":
            for o in market_outcomes:
                threshold = _extract_threshold(o.name)
                prob = float(o.current_probability) if o.current_probability is not None else None
                if prob is None:
                    continue
                pp_name_lower = o.name.lower().strip()
                is_over = (
                    pp_name_lower.startswith("over")
                    or "yes" in pp_name_lower
                    or re.match(r'^\d+\+', pp_name_lower)
                    or re.match(r'^.+:\s*\d+\+', pp_name_lower)  # "Aaron Judge: 1+"
                )
                is_under = pp_name_lower.startswith("under") or pp_name_lower == "no"
                over_prob = prob if is_over or not is_under else 1.0 - prob

                # Try to extract player name and stat type from market name
                # Market names look like "Boston at Atlanta: Trae Young Points"
                opening_over = None
                if o.opening_probability is not None:
                    op = float(o.opening_probability)
                    opening_over = round(op if is_over or not is_under else 1.0 - op, 4)

                player_props.append({
                    "market_name": market.name,
                    "outcome_name": o.name,
                    "threshold": threshold,
                    "over_probability": round(over_prob, 4),
                    "opening_over_probability": opening_over,
                    "source": market.source,
                    "movement": round(float(o.current_probability) - float(o.opening_probability), 4)
                        if o.opening_probability is not None and o.current_probability is not None else None,
                })

        elif market_type == "spread":
            for o in market_outcomes:
                threshold = _extract_threshold(o.name)
                prob = float(o.current_probability) if o.current_probability is not None else None
                spreads.append({
                    "market_name": market.name,
                    "outcome_name": o.name,
                    "threshold": threshold,
                    "probability": round(prob, 4) if prob else None,
                    "source": market.source,
                })

        elif market_type in ("half_spread", "quarter_spread", "half_winner", "quarter_winner"):
            for o in market_outcomes:
                prob = float(o.current_probability) if o.current_probability is not None else None
                threshold = _extract_threshold(o.name)
                period_markets.append({
                    "market_name": market.name,
                    "outcome_name": o.name,
                    "threshold": threshold,
                    "probability": round(prob, 4) if prob else None,
                    "source": market.source,
                    "market_type": market_type,
                    "period": market_period,
                })

        elif market_type in ("h2h", "3ball"):
            # Head-to-head or 3-ball matchup — group outcomes under one entry
            outcomes_list = []
            for o in market_outcomes:
                prob = float(o.current_probability) if o.current_probability is not None else None
                if prob is not None:
                    outcomes_list.append({
                        "name": o.name,
                        "probability": round(prob, 4),
                    })
            if outcomes_list:
                matchups.append({
                    "market_name": market.name,
                    "type": market_type,
                    "source": market.source,
                    "outcomes": outcomes_list,
                })

        else:
            # Rescue player-prop-shaped outcomes from "other" markets.
            # Some markets land here because their name is a generic matchup
            # ("Celtics at Warriors") with no stat keywords, yet their
            # outcomes are player props ("Patrick Mahomes: 250+").  Route
            # any outcome matching the player-name regex into player_props
            # instead of other_markets.
            for o in market_outcomes:
                prob = float(o.current_probability) if o.current_probability is not None else None
                if prob is None:
                    continue
                # Check if outcome looks like a player prop: "PlayerName: N+"
                if _PLAYER_OUTCOME_RE.match(o.name):
                    threshold = _extract_threshold(o.name)
                    if threshold is not None:
                        name_lower = o.name.lower().strip()
                        is_over = (
                            name_lower.startswith("over")
                            or "yes" in name_lower
                            or re.match(r'^\d+\+', name_lower)
                            or re.match(r'^.+:\s*\d+\+', name_lower)
                        )
                        is_under = name_lower.startswith("under") or name_lower == "no"
                        over_prob = prob if is_over or not is_under else 1.0 - prob
                        opening_over = None
                        if o.opening_probability is not None:
                            op = float(o.opening_probability)
                            opening_over = round(op if is_over or not is_under else 1.0 - op, 4)
                        player_props.append({
                            "market_name": market.name,
                            "outcome_name": o.name,
                            "threshold": threshold,
                            "over_probability": round(over_prob, 4),
                            "opening_over_probability": opening_over,
                            "source": market.source,
                            "movement": round(float(o.current_probability) - float(o.opening_probability), 4)
                                if o.opening_probability is not None and o.current_probability is not None else None,
                        })
                        continue
                # Also rescue if the market name itself has a player-stat
                # pattern (e.g., "Patrick Mahomes Passing Yards") but wasn't
                # caught by _classify_game_market because no "over/under" or
                # "total" keyword was present.
                if _PLAYER_PROP_RE.search(market.name) and not _is_team_stat_market(market.name):
                    threshold = _extract_threshold(o.name)
                    name_lower = o.name.lower().strip()
                    is_over = (
                        name_lower.startswith("over")
                        or "yes" in name_lower
                        or re.match(r'^\d+\+', name_lower)
                        or re.match(r'^.+:\s*\d+\+', name_lower)
                    )
                    is_under = name_lower.startswith("under") or name_lower == "no"
                    over_prob = prob if is_over or not is_under else 1.0 - prob
                    opening_over = None
                    if o.opening_probability is not None:
                        op = float(o.opening_probability)
                        opening_over = round(op if is_over or not is_under else 1.0 - op, 4)
                    player_props.append({
                        "market_name": market.name,
                        "outcome_name": o.name,
                        "threshold": threshold,
                        "over_probability": round(over_prob, 4),
                        "opening_over_probability": opening_over,
                        "source": market.source,
                        "movement": round(float(o.current_probability) - float(o.opening_probability), 4)
                            if o.opening_probability is not None and o.current_probability is not None else None,
                    })
                    continue
                other_markets.append({
                    "market_name": market.name,
                    "outcome_name": o.name,
                    "probability": round(prob, 4) if prob else None,
                    "source": market.source,
                })

    # 6. Sort totals by threshold value
    totals_thresholds.sort(key=lambda t: t["threshold"])

    # 7. Deduplicate totals — split game_total vs team_total vs period totals
    seen_thresholds: dict[float, dict] = {}
    team_total_items: list[dict] = []
    home_lower = (event.home_team_name or "").lower()
    away_lower = (event.away_team_name or "").lower()
    for t in totals_thresholds:
        if t["market_type"] == "game_total":
            key = t["threshold"]
            if key not in seen_thresholds or t["source"] == "kalshi":
                seen_thresholds[key] = t
        elif t["market_type"] == "team_total":
            mname = (t.get("market_name") or "").lower()
            if home_lower and any(w in mname for w in home_lower.split() if len(w) >= 4):
                t["team_name"] = event.home_team_name
                t["team_side"] = "home"
            elif away_lower and any(w in mname for w in away_lower.split() if len(w) >= 4):
                t["team_name"] = event.away_team_name
                t["team_side"] = "away"
            team_total_items.append(t)
        elif t["market_type"] in ("half_total", "quarter_total"):
            period_markets.append(t)
    game_totals = sorted(seen_thresholds.values(), key=lambda t: t["threshold"])

    # 7a. Sport-range guard — drop game/team totals with thresholds wildly
    # outside the expected range for this sport.  This catches cross-game
    # contamination from mis-linked markets (e.g., an NHL "Over 5.5" showing
    # on an NBA page, or an NBA "Over 220.5" on an NHL page).
    sport_prefix = sport_key.split("_")[0] if sport_key else None
    game_range = _SPORT_TOTAL_RANGE.get(sport_prefix) if sport_prefix else None
    team_range = _SPORT_TEAM_TOTAL_RANGE.get(sport_prefix) if sport_prefix else None

    if game_range:
        lo, hi = game_range
        game_totals = [t for t in game_totals if lo <= t["threshold"] <= hi]

    if team_range:
        lo, hi = team_range
        team_total_items = [t for t in team_total_items if lo <= t["threshold"] <= hi]

    # 7b. Enforce monotonicity on totals — P(Over X) must decrease as X increases.
    # Thinly traded Kalshi half-period markets often have non-monotonic prices
    # (e.g., Over 98.5 at 68% but Over 101.5 at 75%). Cap violating points
    # to the previous value instead of dropping them (preserves all thresholds).
    # Also filter out resolved/stale thresholds with 0% probability.
    def _enforce_monotonicity(items: list[dict], prob_key: str = "over_probability") -> list[dict]:
        # Filter out 0% (resolved/stale) thresholds
        items = [i for i in items if i.get(prob_key) is not None and i.get(prob_key, 0) > 0]
        if len(items) < 2:
            return items
        result = [items[0]]
        for item in items[1:]:
            prev_prob = result[-1].get(prob_key)
            cur_prob = item.get(prob_key)
            if cur_prob is not None and prev_prob is not None and cur_prob > prev_prob:
                capped = {**item}
                capped[prob_key] = prev_prob
                result.append(capped)
            else:
                result.append(item)
        return result

    game_totals = _enforce_monotonicity(game_totals)

    # Also apply sport-range guard to period totals (use team_total range
    # as a generous proxy — half/quarter totals are never larger than a
    # team's full-game total).
    if team_range:
        lo, hi = team_range
        period_markets = [
            pm for pm in period_markets
            if pm.get("market_type") not in ("half_total", "quarter_total")
            or pm.get("threshold") is None
            or lo <= pm["threshold"] <= hi
        ]

    # Also enforce on period totals within each market group
    period_total_groups: dict[str, list[dict]] = {}
    period_non_totals: list[dict] = []
    for pm in period_markets:
        if pm.get("market_type") in ("half_total", "quarter_total") and pm.get("over_probability") is not None:
            key = pm.get("market_name", "")
            period_total_groups.setdefault(key, []).append(pm)
        else:
            period_non_totals.append(pm)
    cleaned_period_totals = []
    for group in period_total_groups.values():
        group.sort(key=lambda x: x.get("threshold", 0) or 0)
        cleaned_period_totals.extend(_enforce_monotonicity(group))
    period_markets = period_non_totals + cleaned_period_totals

    # 7c. Enforce monotonicity on team totals — group by team side
    team_total_by_side: dict[str, list[dict]] = {}
    for tt in team_total_items:
        side = tt.get("team_side", "unknown")
        team_total_by_side.setdefault(side, []).append(tt)
    team_total_items = []
    for group in team_total_by_side.values():
        group.sort(key=lambda x: x.get("threshold", 0) or 0)
        team_total_items.extend(_enforce_monotonicity(group))

    # 8. Calculate pace
    pace = _estimate_game_pace(
        event.home_score,
        event.away_score,
        event.period,
        event.game_clock,
        sport_key,
    )

    # 9. Filter out boring player props where neither side is interesting
    # (e.g., "2+ home runs: 98%" — the "over" is a near-certainty)
    player_props = [
        p for p in player_props
        if 0.05 <= p["over_probability"] <= 0.95
    ]

    # 9b. Cross-source dedup: when Kalshi and Polymarket both have the same
    # player+stat+threshold, merge into one entry with averaged probability
    # and a sources list, instead of showing duplicate rows.
    if len(player_props) > 1:
        dedup_map: dict[tuple, list[dict]] = {}
        for p in player_props:
            # Extract player name from outcome ("Aaron Judge: 1+" → "aaron judge")
            oname = p.get("outcome_name", "")
            colon_idx = oname.find(":")
            player_part = oname[:colon_idx].strip().lower() if colon_idx > 0 else oname.lower()
            key = (player_part, p.get("threshold"))
            dedup_map.setdefault(key, []).append(p)

        merged_props = []
        for entries in dedup_map.values():
            if len(entries) == 1:
                merged_props.append(entries[0])
            else:
                probs = [e["over_probability"] for e in entries]
                avg_prob = round(sum(probs) / len(probs), 4)
                best = max(entries, key=lambda e: 1 if e.get("source") == "kalshi" else 0)
                best["over_probability"] = avg_prob
                best["all_sources"] = list({e.get("source") for e in entries})
                best["source_count"] = len(entries)
                merged_props.append(best)
        player_props = merged_props

    # 9c. Enforce monotonicity on player props — within each player+stat group,
    # P(Over X) must decrease as X increases. Drops violating thresholds.
    if len(player_props) > 1:
        from collections import defaultdict
        player_stat_groups: dict[tuple, list[dict]] = defaultdict(list)
        for p in player_props:
            oname = p.get("outcome_name", "")
            colon_idx = oname.find(":")
            player_part = oname[:colon_idx].strip().lower() if colon_idx > 0 else oname.lower()
            stat = p.get("market_name", "").split(":")[-1].strip().lower() if ":" in p.get("market_name", "") else "other"
            player_stat_groups[(player_part, stat)].append(p)
        monotonic_props = []
        for group in player_stat_groups.values():
            group.sort(key=lambda x: x.get("threshold", 0) or 0)
            monotonic_props.extend(_enforce_monotonicity(group))
        player_props = monotonic_props

    # 10. Enrich player props with headshot URLs + team assignment from rosters
    if player_props and event.sport_id:
        # player_name_lower → {"headshot": url, "team": "home"|"away"}
        player_roster_info: dict[str, dict] = {}
        try:
            # Primary: exact team name match — query both teams with name so we know home vs away
            team_result = await db.execute(
                select(Team.name, Team.roster_players).where(
                    Team.name.in_([event.home_team_name, event.away_team_name]),
                    Team.sport_id == event.sport_id,
                )
            )
            for team_name, roster in team_result.all():
                side = "home" if team_name == event.home_team_name else "away"
                if roster and isinstance(roster, list):
                    for item in roster:
                        if isinstance(item, dict) and item.get("name"):
                            info: dict = {"team": side}
                            if item.get("headshot"):
                                info["headshot"] = item["headshot"]
                            player_roster_info[item["name"].lower()] = info

            # Fallback: ILIKE match on team short names
            if not player_roster_info:
                home_short = event.home_team_name.split()[-1] if event.home_team_name else ""
                away_short = event.away_team_name.split()[-1] if event.away_team_name else ""
                fallback_result = await db.execute(
                    select(Team.name, Team.roster_players).where(
                        Team.sport_id == event.sport_id,
                        or_(
                            Team.name.ilike(f"%{home_short}%") if len(home_short) >= 4 else False,
                            Team.name.ilike(f"%{away_short}%") if len(away_short) >= 4 else False,
                        ),
                    )
                )
                for team_name, roster in fallback_result.all():
                    tn_lower = team_name.lower() if team_name else ""
                    side = "home" if home_short.lower() in tn_lower else "away"
                    if roster and isinstance(roster, list):
                        for item in roster:
                            if isinstance(item, dict) and item.get("name"):
                                info = {"team": side}
                                if item.get("headshot"):
                                    info["headshot"] = item["headshot"]
                                player_roster_info[item["name"].lower()] = info
        except Exception:
            pass

        if player_roster_info:
            for prop in player_props:
                name = prop.get("market_name", "")
                colon_idx = name.find(":")
                after_colon = name[colon_idx + 1:].strip() if colon_idx >= 0 else ""
                outcome = prop.get("outcome_name", "")
                outcome_colon = outcome.find(":")
                outcome_player = outcome[:outcome_colon].strip() if outcome_colon > 0 else ""

                for candidate in [after_colon, outcome_player]:
                    if not candidate:
                        continue
                    # Exact match
                    info = player_roster_info.get(candidate.lower())
                    if info:
                        if info.get("headshot"):
                            prop["player_headshot"] = info["headshot"]
                        prop["player_team"] = info["team"]
                        break
                    # Partial match
                    for pname, pinfo in player_roster_info.items():
                        if pname in candidate.lower() or candidate.lower() in pname:
                            if pinfo.get("headshot"):
                                prop["player_headshot"] = pinfo["headshot"]
                            prop["player_team"] = pinfo["team"]
                            break
                    if "player_team" in prop:
                        break

    response = {
        "event_id": event_id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "home_score": event.home_score,
        "away_score": event.away_score,
        "status": event.status,
        "totals": game_totals,
        "player_props": player_props,
        "team_totals": team_total_items,
        "spreads": spreads,
        "period_markets": period_markets,
        "matchups": matchups,
        "other": other_markets,
        "pace": pace,
    }

    # Cache response (evict oldest if over size limit)
    if len(_game_markets_cache) >= _GAME_MARKETS_MAX_SIZE:
        oldest_key = min(_game_markets_cache, key=lambda k: _game_markets_cache[k][0])
        del _game_markets_cache[oldest_key]
    _game_markets_cache[event_id] = (now_ts, event.status or "", response)

    return response


_related_futures_cache: dict[int, tuple[float, str, dict]] = {}
_RELATED_FUTURES_LIVE_TTL = 60
_RELATED_FUTURES_MAX_SIZE = 200


@router.get("/{event_id}/related-futures")
async def get_related_futures(
    event_id: int,
    debug: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """
    Get futures markets related to the teams in this event.

    Uses direct name matching on outcome names within sport-matching markets,
    eliminating dependency on pre-computed team_id links. Sport matching uses
    three strategies (OR): external_id prefix, llm_sport_category, and sport_id.
    """
    import time as _time
    _now = _time.time()
    if not debug and event_id in _related_futures_cache:
        _cached_at, _cached_status, _cached_resp = _related_futures_cache[event_id]
        _ttl = _RELATED_FUTURES_LIVE_TTL
        if _cached_status in ("completed", "closed") or _now - _cached_at < _ttl:
            return _cached_resp

    from app.utils.team_linking import compute_relevance_score
    from app.utils.market_label_normalization import (
        normalize_market_label,
        classify_market_category,
        get_merge_group,
        is_wrong_sport_leak,
        compute_playoff_stage,
    )

    # 1. Load event with sport
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    empty = {
        "event_id": event_id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "home_team_futures": [],
        "away_team_futures": [],
        "series_markets": [],
        "total_count": 0,
    }

    # 2. Determine sport family for filtering
    event_sport_key = event.sport.key if event.sport else None
    if not event_sport_key:
        return empty

    sport_prefix = event_sport_key.split("_")[0]  # e.g., "basketball", "americanfootball"
    llm_category = _SPORT_PREFIX_TO_LLM_CATEGORY.get(sport_prefix, sport_prefix)

    # Gender-aware filtering: don't show men's futures for women's events
    # or women's futures for men's events. Detect via sport key suffixes.
    is_womens = event_sport_key in (
        "basketball_wnba", "basketball_wncaab",
    ) or "_women" in event_sport_key
    is_mens_specific = event_sport_key in (
        "basketball_nba", "basketball_ncaab",
        "americanfootball_nfl", "americanfootball_ncaaf",
    )

    # Build sport key pattern for external_id matching
    if is_womens:
        # Only match women's sport keys
        ext_id_patterns = [event_sport_key + "%"]
    elif is_mens_specific:
        # Only match this specific men's league (not women's variant)
        ext_id_patterns = [event_sport_key + "%"]
    else:
        # Generic: match all sports with this prefix
        ext_id_patterns = [sport_prefix + "%"]

    # Find compatible sport IDs (for markets that have sport_id populated)
    if is_womens or is_mens_specific:
        # Narrow to exact sport key
        prefix_result = await db.execute(
            select(Sport.id).where(Sport.key == event_sport_key)
        )
    else:
        prefix_result = await db.execute(
            select(Sport.id).where(Sport.key.like(f"{sport_prefix}%"))
        )
    compatible_sport_ids = [row.id for row in prefix_result.all()]

    # Gender-aware llm_sport_category: women's basketball → only "women's basketball"
    # markets, not "basketball" generically
    gender_market_name_filter = None
    if is_womens:
        gender_market_name_filter = "women"
    elif is_mens_specific:
        # For men's leagues, exclude markets with "women" or "WNBA" in name
        gender_market_name_filter = "exclude_women"

    # 3. Find sport-matching open markets using multiple strategies (OR)
    #    - external_id LIKE 'baseball_mlb%' (Odds API markets)
    #    - external_id LIKE 'KXMLB%' (Kalshi futures tickers — championship, awards, etc.)
    #    - llm_sport_category = 'baseball' (LLM-classified markets)
    #    - sport_id IN (...) (directly linked markets)
    sport_filters = []
    for pat in ext_id_patterns:
        sport_filters.append(FuturesMarket.external_id.like(pat))
    sport_filters.append(FuturesMarket.llm_sport_category == llm_category)
    if compatible_sport_ids:
        sport_filters.append(FuturesMarket.sport_id.in_(compatible_sport_ids))

    # Also match Kalshi futures ticker prefixes (e.g., KXNBA%, KXMLB%, KXNFL%)
    # These don't start with the Odds API sport key but belong to the same sport.
    # Use a compact set of root prefixes to avoid generating 30+ ILIKE patterns.
    _SPORT_TO_KALSHI_ROOTS: dict[str, list[str]] = {
        "basketball": ["KXNBA", "KXWNBA", "KXNCAAMB", "KXNCAAB", "KXNCAAWB"],
        "americanfootball": ["KXNFL", "KXNCAAF"],
        "baseball": ["KXMLB", "KXLEADERMLB", "KXNEXTTEAMMLB", "KXCITYMLBEXPAND"],
        "icehockey": ["KXNHL"],
        "soccer": ["KXMLS", "KXSOCCER"],
        "golf": [],  # Golf uses DataGolf, not Kalshi futures
        "mma": ["KXUFC"],
        "boxing": ["KXBOXING"],
        "tennis": ["KXATP", "KXWTA"],
    }
    kalshi_roots = _SPORT_TO_KALSHI_ROOTS.get(sport_prefix, [])
    for root in kalshi_roots:
        sport_filters.append(FuturesMarket.external_id.ilike(f"{root}%"))

    # Include markets regardless of status — many Kalshi markets have status=NULL
    # (never explicitly set). For completed events, also include resolved/closed.
    event_is_finished = event.status in ("completed", "closed")
    rf_status_filter = (
        or_(
            FuturesMarket.status.in_(("open", "resolved", "closed")),
            FuturesMarket.status.is_(None),
        )
        if event_is_finished
        else or_(FuturesMarket.status == "open", FuturesMarket.status.is_(None))
    )
    # Tier-aware market discovery:
    # Pass 1: Season-long markets (tiers 1-4: championship, conference, awards, division)
    #         These are relevant to any event in the sport. Relatively small set.
    # Pass 2: Game-specific props (tier 5) — only for THIS event via event_id FK.
    #         Avoids loading props from every other game in the sport.
    base_season_filters = [
        rf_status_filter,
        or_(*sport_filters),
    ]
    if event_is_finished:
        recency_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        base_season_filters.append(FuturesMarket.updated_at >= recency_cutoff)

    # Load season markets across all tiers in one query with per-tier limits.
    # Uses a window function to rank within each tier, then filters to top 100.
    from sqlalchemy import text as _sql_text
    _tier_query = await db.execute(
        select(FuturesMarket.id, FuturesMarket.market_tier)
        .where(
            *base_season_filters,
            FuturesMarket.market_tier.in_([1, 2, 3, 4]),
        )
        .order_by(FuturesMarket.market_tier, FuturesMarket.id)
        .limit(400)
    )
    _tier_rows = _tier_query.all()
    _tier_counts: dict[int, int] = {}
    season_market_ids = []
    for row in _tier_rows:
        tier = row.market_tier or 4
        _tier_counts[tier] = _tier_counts.get(tier, 0) + 1
        if _tier_counts[tier] <= 100:
            season_market_ids.append(row.id)

    # Debug: tier breakdown of season markets
    if debug and season_market_ids:
        tier_result = await db.execute(
            select(FuturesMarket.market_tier, func.count())
            .where(FuturesMarket.id.in_(season_market_ids))
            .group_by(FuturesMarket.market_tier)
        )
        tier_breakdown = {tier: count for tier, count in tier_result.all()}
        # Also check if known division IDs are in the set
        known_div_ids = [446, 447, 449, 444, 445, 450, 432]
        div_in_set = [mid for mid in known_div_ids if mid in season_market_ids]
        import logging
        logging.getLogger(__name__).info(
            f"Related futures debug: season_market_ids={len(season_market_ids)}, "
            f"tier_breakdown={tier_breakdown}, div_ids_in_set={div_in_set}"
        )

    # Game props (tier 5): only load markets linked to THIS specific event
    # Strict sport check — don't allow NULL sport_id through (catches cross-sport
    # contamination where hockey markets were incorrectly linked to baseball events)
    game_prop_filters = [
        rf_status_filter,
        FuturesMarket.event_id == event_id,
        FuturesMarket.market_tier == 5,
    ]
    if event.sport_id:
        game_prop_filters.append(
            or_(
                FuturesMarket.sport_id == event.sport_id,
                # For markets without sport_id, check llm_sport_category
                and_(
                    FuturesMarket.sport_id.is_(None),
                    FuturesMarket.llm_sport_category == llm_category,
                ),
            )
        )
    game_prop_result = await db.execute(
        select(FuturesMarket.id).where(*game_prop_filters)
    )
    game_prop_ids = [row.id for row in game_prop_result.all()]

    # Pass 3: Series-level markets (tier 5, not linked to events)
    # During playoffs, Kalshi has rich series-level markets (Series Winner,
    # Series Exact Score, Series Total Games) that should appear on every
    # game's event detail page within that playoff series.
    # These markets are tier 5 (not loaded in season passes) and have no
    # event_id (not loaded in game prop pass). Find them by matching BOTH
    # team names in the market name + series-related ticker prefixes.
    series_market_ids: list[int] = []
    if event.home_team_name and event.away_team_name:
        _series_home_patterns = _team_name_patterns(event.home_team_name)
        _series_away_patterns = _team_name_patterns(event.away_team_name)
        # Require a team pattern of at least 4 chars from each side
        _series_home_ilike = [
            FuturesMarket.name.ilike(f"%{p}%")
            for p in _series_home_patterns if len(p) >= 4
        ]
        _series_away_ilike = [
            FuturesMarket.name.ilike(f"%{p}%")
            for p in _series_away_patterns if len(p) >= 4
        ]
        if _series_home_ilike and _series_away_ilike:
            # Detect series markets by ticker prefix or name pattern
            from app.utils.sport_keys import KALSHI_FUTURES_TICKER_TO_SPORT_KEY
            _series_ticker_conditions = [
                FuturesMarket.external_id.ilike(f"{prefix}%")
                for prefix, sk in KALSHI_FUTURES_TICKER_TO_SPORT_KEY.items()
                if "series" in prefix and sk == event_sport_key
            ]
            _series_name_conditions = [
                FuturesMarket.name.ilike("%series%"),
            ]
            _series_detection = _series_ticker_conditions + _series_name_conditions
            if _series_detection:
                series_result = await db.execute(
                    select(FuturesMarket.id)
                    .where(
                        rf_status_filter,
                        or_(*sport_filters),
                        or_(*_series_detection),
                        or_(*_series_home_ilike),
                        or_(*_series_away_ilike),
                    )
                    .limit(50)
                )
                series_market_ids = [row.id for row in series_result.all()]

    sport_market_ids = season_market_ids + game_prop_ids
    # Series markets are returned as a separate top-level array, not mixed
    # into the home/away classification flow. They belong to the matchup
    # (both teams), not one side.
    if not sport_market_ids and not series_market_ids:
        return empty

    # Apply gender name filter to exclude cross-gender markets
    if gender_market_name_filter and sport_market_ids:
        if gender_market_name_filter == "women":
            # Women's event: only keep markets with women-related keywords
            gender_q = await db.execute(
                select(FuturesMarket.id).where(
                    FuturesMarket.id.in_(sport_market_ids),
                    or_(
                        FuturesMarket.name.ilike("%women%"),
                        FuturesMarket.name.ilike("%WNBA%"),
                        FuturesMarket.name.ilike("%WNCAA%"),
                        FuturesMarket.external_id.like("basketball_wnba%"),
                        FuturesMarket.external_id.like("basketball_wncaab%"),
                    ),
                )
            )
            women_ids = {r.id for r in gender_q.all()}
            if women_ids:
                sport_market_ids = list(women_ids)
            # If no women-specific markets found, keep all (better than empty)
        elif gender_market_name_filter == "exclude_women":
            # Men's event: exclude markets with women-related keywords
            gender_q = await db.execute(
                select(FuturesMarket.id).where(
                    FuturesMarket.id.in_(sport_market_ids),
                    ~FuturesMarket.name.ilike("%women%"),
                    ~FuturesMarket.name.ilike("%WNBA%"),
                    ~FuturesMarket.name.ilike("%WNCAA%"),
                    ~FuturesMarket.external_id.like("basketball_wnba%"),
                    ~FuturesMarket.external_id.like("basketball_wncaab%"),
                )
            )
            mens_ids = [r.id for r in gender_q.all()]
            if mens_ids:
                sport_market_ids = mens_ids

    # 4. Build name patterns for both teams
    home_patterns = _team_name_patterns(event.home_team_name)
    away_patterns = _team_name_patterns(event.away_team_name)

    # Save team-level patterns BEFORE adding roster players
    # (used for market name matching — player names in market names would be too noisy)
    home_team_patterns = list(home_patterns)
    away_team_patterns = list(away_patterns)

    # Look up Team records for alternate names, roster players, AND team_ids
    home_team_ids = set()
    away_team_ids = set()
    # Build player metadata lookup: name_lower → {espn_id, headshot}
    player_metadata: dict[str, dict] = {}
    for team_name, patterns, team_patterns, id_set in [
        (event.home_team_name, home_patterns, home_team_patterns, home_team_ids),
        (event.away_team_name, away_patterns, away_team_patterns, away_team_ids),
    ]:
        team_filters = [Team.name == team_name]
        if event.sport_id:
            team_filters.append(Team.sport_id == event.sport_id)
        team_result = await db.execute(
            select(Team.id, Team.alternate_names, Team.roster_players).where(*team_filters)
        )
        team_row = team_result.first()
        if team_row:
            id_set.add(team_row.id)
            # Add alternate team names (e.g., "Celtics", "BOS", "A's")
            alt_names = team_row.alternate_names
            if alt_names and isinstance(alt_names, list):
                for alt in alt_names:
                    if isinstance(alt, str) and len(alt) >= 2:
                        escaped = _escape_like(alt)
                        if escaped.lower() not in [p.lower() for p in patterns]:
                            patterns.append(escaped)
                            team_patterns.append(escaped)
            # Add roster player names from ESPN/MLB API (e.g., "Jayson Tatum")
            # For completed events, skip adding names to ILIKE patterns (expensive SQL)
            # but still build player_metadata for headshot enrichment on awards.
            roster = team_row.roster_players
            if roster and isinstance(roster, list):
                for item in roster:
                    if isinstance(item, dict):
                        player_name = item.get("name")
                        # Store metadata for player image enrichment
                        if player_name and (item.get("espn_id") or item.get("headshot")):
                            player_metadata[player_name.lower()] = {
                                k: v for k, v in item.items()
                                if k in ("espn_id", "headshot", "name")
                            }
                    elif isinstance(item, str):
                        player_name = item
                    else:
                        continue
                    if not event_is_finished and isinstance(player_name, str) and len(player_name) >= 4:
                        escaped = _escape_like(player_name)
                        if escaped.lower() not in [p.lower() for p in patterns]:
                            patterns.append(escaped)

    all_team_ids = home_team_ids | away_team_ids

    # Supplement player_metadata with ALL rosters in this sport for award headshots.
    # Award outcomes (MVP, DPOY) reference players from any team, not just the event's two.
    if event.sport_id and len(player_metadata) < 500:
        all_rosters_result = await db.execute(
            select(Team.roster_players)
            .where(Team.sport_id == event.sport_id, Team.roster_players.isnot(None))
        )
        for row in all_rosters_result.all():
            roster = row.roster_players
            if not isinstance(roster, list):
                continue
            for item in roster:
                if isinstance(item, dict):
                    pname = item.get("name")
                    if pname and pname.lower() not in player_metadata:
                        if item.get("espn_id") or item.get("headshot"):
                            player_metadata[pname.lower()] = {
                                k: v for k, v in item.items()
                                if k in ("espn_id", "headshot", "name")
                            }

    # Build ILIKE conditions for outcome name matching
    home_ilike = [FuturesOutcome.name.ilike(f"%{p}%") for p in home_patterns]
    away_ilike = [FuturesOutcome.name.ilike(f"%{p}%") for p in away_patterns]
    all_name_conditions = home_ilike + away_ilike

    # Combine name matching + team_id matching (catches player outcomes from backfill)
    match_conditions = list(all_name_conditions)
    if all_team_ids:
        match_conditions.append(FuturesOutcome.team_id.in_(list(all_team_ids)))

    # ALSO: Match by MARKET name for game props
    # Markets like "Boston at Golden State: Rebounds" have team names in the
    # market name, not the outcome names (which are "Over 218.5", etc.)
    market_name_conditions = []
    for p in home_team_patterns + away_team_patterns:
        if len(p) >= 4:  # Skip very short patterns
            market_name_conditions.append(FuturesMarket.name.ilike(f"%{p}%"))
    if market_name_conditions:
        market_name_subq = (
            select(FuturesMarket.id)
            .where(
                FuturesMarket.id.in_(sport_market_ids),
                or_(*market_name_conditions),
            )
        )
        match_conditions.append(
            FuturesOutcome.market_id.in_(market_name_subq)
        )

    if not match_conditions:
        return empty

    # 5. Query matching outcomes with their markets
    outcomes_result = await db.execute(
        select(FuturesOutcome)
        .options(selectinload(FuturesOutcome.market))
        .where(
            FuturesOutcome.market_id.in_(sport_market_ids),
            or_(*match_conditions),
        )
    )
    outcomes = outcomes_result.scalars().all()

    if not outcomes:
        return empty

    # 6. Classify each outcome as home or away
    # Priority: team_id (reliable for player outcomes) > name matching (team outcomes)
    def _matches_any(name: str, patterns: list[str]) -> bool:
        name_lower = name.lower()
        for p in patterns:
            clean = p.replace("\\%", "%").replace("\\_", "_").replace("\\\\", "\\")
            if clean.lower() in name_lower:
                return True
        return False

    # 7. Count bookmakers per outcome for liquidity scoring
    outcome_ids = [o.id for o in outcomes]
    bookmaker_counts = {}
    if outcome_ids:
        from app.models import FuturesOddsSnapshot
        bm_result = await db.execute(
            select(
                FuturesOddsSnapshot.outcome_id,
                func.count(func.distinct(FuturesOddsSnapshot.bookmaker)).label("bm_count"),
            )
            .where(FuturesOddsSnapshot.outcome_id.in_(outcome_ids))
            .group_by(FuturesOddsSnapshot.outcome_id)
        )
        for row in bm_result.all():
            bookmaker_counts[row.outcome_id] = row.bm_count

    now = datetime.now(timezone.utc)
    home_futures = []
    away_futures = []
    seen_ids = set()

    # ── Game-specific market filtering ────────────────────────────
    # Game-specific markets (stat props AND matchup markets) are tied to a
    # single game and should only appear on THAT event's detail page.
    # For completed/closed events, game-specific markets are always hidden —
    # their probabilities are stale (markets may not have resolved in our data).
    # Season-long markets (championship, MVP, awards) always show.
    event_is_finished = event.status in ("completed", "closed")
    event_commence_time = event.commence_time
    GAME_TIME_WINDOW = timedelta(hours=6)  # ±6h for game market matching

    def _is_game_specific_market(mkt: FuturesMarket) -> bool:
        """Check if a market is tied to a specific game (stat prop or matchup)."""
        name = mkt.name or ""
        # Stat prop patterns: "Team at Team: Points/Rebounds/etc."
        if _GAME_STAT_PROP_RE.search(name):
            return True
        # Matchup patterns: "Team vs. Team", "Team – Team"
        # These are game moneylines, spreads, O/U tied to a single game.
        if _GAME_MATCHUP_RE.search(name):
            return True
        return False

    def _extract_market_teams(market_name: str) -> list[str]:
        """Extract team names from a game-specific market name.

        Handles patterns like:
          "Boston Celtics at Miami Heat: Points" → ["Boston Celtics", "Miami Heat"]
          "Golden State vs. Boston" → ["Golden State", "Boston"]
          "Miami (OH) at SMU: Rebounds" → ["Miami (OH)", "SMU"]
        """
        if not market_name:
            return []
        # Strip stat prop suffix: "Team at Team: Points" → "Team at Team"
        base = re.split(r":\s*(?:points|assists|rebounds|steals|blocks|"
                        r"three\s*pointers?|3-?pointers?|turnovers|strikeouts|"
                        r"hits|runs|home\s*runs|goals|saves|sacks|"
                        r"passing\s*yards|rushing\s*yards|receiving\s*yards|"
                        r"touchdowns|completions|interceptions|aces|"
                        r"double\s*faults|kills|double\s*doubles?|"
                        r"triple\s*doubles?|total\s*points|spread|"
                        r"moneyline|over|under|winner)",
                        market_name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        # Try "Team1 at Team2" or "Team1 vs. Team2" split
        parts = re.split(r"\s+(?:at|vs\.?|–)\s+", base, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            return [p.strip() for p in parts if p.strip()]
        return []

    def _market_teams_match_event(market_teams: list[str]) -> bool:
        """Check if extracted market teams match this event's teams.

        For two-team markets (e.g., "Team A at Team B"), BOTH must match
        (one per event side). This prevents "Miami (OH) at SMU" from
        matching a Celtics-Heat game just because "Miami" overlaps.

        For single-team extraction, requires the team to match either side.
        """
        from app.utils.name_normalization import names_match
        if not market_teams:
            return False

        event_teams = []
        if event.home_team_name:
            event_teams.append(event.home_team_name)
        if event.away_team_name:
            event_teams.append(event.away_team_name)
        if not event_teams:
            return False

        if len(market_teams) == 2:
            # Two-team market: each must match a DIFFERENT event team.
            # This prevents "Miami (OH) at SMU" matching Celtics vs Heat.
            matched_event_teams: set[int] = set()
            for mt in market_teams:
                for i, et in enumerate(event_teams):
                    if i not in matched_event_teams and names_match(mt, et):
                        matched_event_teams.add(i)
                        break
            return len(matched_event_teams) == 2
        else:
            # Single team: must match at least one side
            mt = market_teams[0]
            return any(names_match(mt, et) for et in event_teams)

    def _game_market_matches_event(mkt: FuturesMarket) -> bool:
        """Check if a game-specific market belongs to THIS event.

        Requires BOTH temporal proximity AND team name validation.
        Temporal proximity alone is not sufficient — prevents cross-game
        leaks like "Miami (OH) at SMU" appearing on a Celtics-Heat page.
        """
        # Direct event_id link — most reliable
        if mkt.event_id is not None:
            return mkt.event_id == event_id

        name_lower = (mkt.name or "").lower()
        home_short = event.home_team_name.split()[-1].lower() if event.home_team_name else ""
        away_short = event.away_team_name.split()[-1].lower() if event.away_team_name else ""

        # Strong match: BOTH teams appear in market name
        if (home_short and len(home_short) >= 4 and home_short in name_lower and
                away_short and len(away_short) >= 4 and away_short in name_lower):
            return True

        # Moderate match: parse "Team A at/vs Team B" from market name,
        # require team match + temporal proximity
        market_teams = _extract_market_teams(mkt.name or "")
        has_team_match = _market_teams_match_event(market_teams) if market_teams else False

        if has_team_match and event_commence_time:
            for dt in (mkt.commence_time, mkt.resolution_date):
                if dt:
                    diff = abs((dt - event_commence_time).total_seconds())
                    if diff <= GAME_TIME_WINDOW.total_seconds():
                        return True

        # No team match or no timing confirmation — exclude
        return False

    for outcome in outcomes:
        if outcome.id in seen_ids:
            continue
        seen_ids.add(outcome.id)

        market = outcome.market

        # ── Ticker-based sport validation ──
        # Reject markets whose Kalshi game ticker indicates a different sport
        # family than the event. Catches LLM miscategorization (e.g., NHL game
        # markets with llm_sport_category='basketball').
        if market.external_id:
            ticker_sport_key = _get_sport_key_from_ticker(market.external_id)
            if ticker_sport_key:
                ticker_prefix = ticker_sport_key.split("_")[0]
                if ticker_prefix != sport_prefix:
                    continue

        # ── Wrong-sport leak detection ──
        # Catches NCAA "Boston College" and NHL "Boston Bruins" leaking into NBA
        if is_wrong_sport_leak(market.name or "", outcome.name, event_sport_key):
            continue

        # ── Filter game-specific markets ──
        # For finished events: show stat props IF we have box score data,
        # but hide matchup markets (moneylines, spreads — meaningless post-game).
        # For live/scheduled: only show game-specific markets that match THIS event.
        if _is_game_specific_market(market):
            is_stat_prop = bool(_GAME_STAT_PROP_RE.search(market.name or ""))
            if event_is_finished:
                # Only allow stat props through when we have box score data
                if not is_stat_prop or not event.box_score_data or event.box_score_data.get("error"):
                    continue
                if not _game_market_matches_event(market):
                    continue
            elif not _game_market_matches_event(market):
                continue

        # Classify: team_id first (reliable for player outcomes), then name matching
        is_home = outcome.team_id in home_team_ids if outcome.team_id else False
        is_away = outcome.team_id in away_team_ids if outcome.team_id else False

        if not is_home and not is_away:
            # Fall back to name matching on outcome (team outcomes)
            is_home = _matches_any(outcome.name, home_patterns)
            is_away = _matches_any(outcome.name, away_patterns)

        if not is_home and not is_away:
            # Fall back to name matching on MARKET name (game props)
            # e.g., "Boston at Golden State: Rebounds" → market name matches
            is_home = _matches_any(market.name, home_team_patterns)
            is_away = _matches_any(market.name, away_team_patterns)

        if not is_home and not is_away:
            continue

        # If matches both teams, prefer home (rare edge case)
        side = "home" if is_home else "away"

        # Compute days to resolution
        days_to_resolution = None
        if market.resolution_date:
            delta = (market.resolution_date - now).total_seconds() / 86400
            days_to_resolution = max(0, delta)

        # Compute relevance score
        relevance_score, relevance_reason = compute_relevance_score(
            market_tier=market.market_tier,
            probability=float(outcome.current_probability) if outcome.current_probability else None,
            probability_change_24h=float(outcome.probability_change_24h) if outcome.probability_change_24h else None,
            days_to_resolution=days_to_resolution,
            bookmaker_count=bookmaker_counts.get(outcome.id, 1),
        )

        # Compute next update time based on source
        current_minute = now.minute
        next_poll_minute = 45 if market.source == "kalshi" else 30
        if current_minute >= next_poll_minute:
            next_update = now.replace(minute=next_poll_minute, second=0, microsecond=0) + timedelta(hours=1)
        else:
            next_update = now.replace(minute=next_poll_minute, second=0, microsecond=0)

        # ── Normalize label, category, merge group ──
        clean_label = normalize_market_label(market.name or "")
        display_category = classify_market_category(
            clean_label, raw_name=market.name or "", market_category=market.category or "",
        )
        merge_group = get_merge_group(clean_label)

        # Compute playoff stage classification (single source of truth)
        stage_type, stage_display, stage_order = compute_playoff_stage(
            clean_label, raw_name=market.name or "",
        )

        # Resolve "Yes"/"No" outcome names for binary matchup markets.
        # Polymarket uses "Yes"/"No" for game moneylines like "Celtics vs. 76ers".
        # "Yes" = first team wins, "No" = first team loses.
        resolved_name = outcome.name
        if outcome.name in ("Yes", "No") and market.name:
            matchup = re.match(r'^(.+?)\s+(?:vs\.?|at|@)\s+(.+?)(?:\s*[-:]|$)', market.name)
            if matchup:
                if outcome.name == "Yes":
                    resolved_name = f"{matchup.group(1).strip()} Win"
                else:
                    resolved_name = f"{matchup.group(2).strip()} Win"

        entry = {
            "market_id": market.id,
            "market_name": market.name,
            "clean_label": clean_label,
            "display_category": display_category,
            "merge_group": merge_group,
            "playoff_stage": stage_display,
            "playoff_stage_type": stage_type,
            "stage_order": stage_order,
            "market_tier": market.market_tier,
            "category": market.category,
            "source": market.source,
            "outcome_id": outcome.id,
            "outcome_name": resolved_name,
            "probability": float(outcome.current_probability) if outcome.current_probability else None,
            "american_odds": outcome.current_american_odds,
            "probability_change_24h": float(outcome.probability_change_24h) if outcome.probability_change_24h else None,
            "opening_probability": float(outcome.opening_probability) if outcome.opening_probability else None,
            "rank": outcome.rank,
            "relevance_score": relevance_score,
            "relevance_reason": relevance_reason,
            "last_updated": outcome.last_updated.isoformat() if outcome.last_updated else None,
            "next_update_expected": next_update.isoformat(),
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
            "bookmaker_count": bookmaker_counts.get(outcome.id, 1),
        }

        # Add matched player metadata (ESPN headshot) when outcome matches a roster player
        player_lookup = outcome.name.split(":")[0].strip().lower()
        matched = player_metadata.get(player_lookup)
        if matched:
            entry["matched_player"] = matched

        if side == "home":
            home_futures.append(entry)
        else:
            away_futures.append(entry)

    # ── Cross-source deduplication ──────────────────────────────────
    # Merge entries with the same (merge_group, outcome_name) across sources.
    # Keeps the entry with the highest bookmaker count (most liquid).
    # Aggregates all sources into an `all_sources` list on the winner.
    #
    # Per-team merge groups (win_total, make_playoffs, etc.) use merge_group
    # alone as the key because each team has exactly one entry per source,
    # but outcome names may differ structurally ("Boston Celtics" vs "Yes").
    # Per-team: futures already classified into home/away, so within each
    # list there's at most one entry per merge group per source.
    # Division winners use dynamic keys like "atlantic_division" —
    # match with suffix check.
    from app.utils.related_futures import dedup_by_merge_group
    home_futures = dedup_by_merge_group(home_futures)
    away_futures = dedup_by_merge_group(away_futures)

    # ── Enrich matchup outcomes with team logos ───────────────────
    # For "matchup" outcomes (e.g., "Los Angeles Lakers" in a Finals matchup
    # market), look up the team logo so the frontend can display it.
    matchup_outcomes = set()
    for f in home_futures + away_futures:
        mg = f.get("merge_group") or ""
        if "_matchup" in mg:
            matchup_outcomes.add(f["outcome_name"])
    if matchup_outcomes and event.sport_id:
        from app.utils.name_normalization import names_match
        team_logo_result = await db.execute(
            select(Team.name, Team.logo_url_small, Team.logo_url).where(
                Team.sport_id == event.sport_id,
            )
        )
        team_rows = team_logo_result.all()
        for f in home_futures + away_futures:
            mg = f.get("merge_group") or ""
            if "_matchup" not in mg:
                continue
            oname = f["outcome_name"]
            for tname, logo_sm, logo_lg in team_rows:
                if names_match(oname, tname):
                    f["team_logo"] = logo_sm or logo_lg
                    break

    # Sort each side by relevance score descending
    home_futures.sort(key=lambda x: x["relevance_score"], reverse=True)
    away_futures.sort(key=lambda x: x["relevance_score"], reverse=True)

    # ── Generate or retrieve cached LLM summary ─────────────────────
    summary = None
    if home_futures or away_futures:
        try:
            from app.models.models import LineMovementAnalysis
            # Check cache
            cache_result = await db.execute(
                select(LineMovementAnalysis).where(
                    LineMovementAnalysis.event_id == event_id,
                    LineMovementAnalysis.analysis_type == "related_futures",
                )
            )
            cached = cache_result.scalar_one_or_none()

            now_ts = datetime.now(timezone.utc)
            if cached and cached.explanation:
                # Check if expired
                if cached.expires_at is None or cached.expires_at > now_ts:
                    summary = cached.explanation
                else:
                    # Expired — regenerate
                    cached = None

            if not cached or not cached.explanation:
                pass  # LLM generation deferred to Celery — don't block request
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("Related futures summary error: %s", e)

    # Extract box score player data for the response (if available)
    box_score_players = None
    if event.box_score_data and not event.box_score_data.get("error"):
        box_score_players = event.box_score_data.get("players")

    # Enrich with league context (B2) — provides merged multi-source
    # championship probabilities for the Playoff Path card
    league_ctx = None
    try:
        from app.services.league_context import enrich_event_with_context
        league_ctx = await enrich_event_with_context(event, db)
    except Exception:
        pass

    # ── Load series markets as a dedicated top-level array ─────────────
    # Series markets (Win Series, Series Exact Score, Series Total Games)
    # belong to the matchup between BOTH teams, not one side. Loading them
    # separately avoids the home/away classification problems (Yes/No outcomes,
    # both-teams-match ambiguity) that caused them to be dropped or misplaced.
    formatted_series: list[dict] = []
    if series_market_ids:
        series_outcomes_result = await db.execute(
            select(FuturesOutcome)
            .options(selectinload(FuturesOutcome.market))
            .where(FuturesOutcome.market_id.in_(series_market_ids))
            .order_by(FuturesOutcome.market_id, FuturesOutcome.current_probability.desc())
        )
        series_outcomes = series_outcomes_result.scalars().all()

        # Group outcomes by market, then format each market as one entry
        from collections import defaultdict
        series_by_market: dict[int, list] = defaultdict(list)
        for so in series_outcomes:
            series_by_market[so.market_id].append(so)

        for mid, outcomes_list in series_by_market.items():
            if not outcomes_list:
                continue
            mkt = outcomes_list[0].market
            if not mkt:
                continue
            top_outcomes = []
            for so in outcomes_list[:10]:  # cap outcomes per market
                top_outcomes.append({
                    "outcome_id": so.id,
                    "name": so.name,
                    "probability": float(so.current_probability) if so.current_probability else None,
                    "probability_change_24h": float(so.probability_change_24h) if so.probability_change_24h else None,
                })
            formatted_series.append({
                "market_id": mkt.id,
                "market_name": mkt.name,
                "source": mkt.source,
                "status": mkt.status,
                "resolution_date": mkt.resolution_date.isoformat() if mkt.resolution_date else None,
                "outcomes": top_outcomes,
            })
        # Limit to 10 series markets total
        formatted_series = formatted_series[:10]

    resp = {
        "event_id": event_id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "home_team_futures": home_futures,
        "away_team_futures": away_futures,
        "series_markets": formatted_series,
        "total_count": len(home_futures) + len(away_futures),
        "summary": summary,
        "event_status": event.status,
        "box_score": box_score_players,
        "game_period": event.period,
        "game_clock": event.game_clock,
        "league_context": league_ctx,
    }
    if debug:
        resp["_debug"] = {
            "season_market_count": len(season_market_ids),
            "game_prop_count": len(game_prop_ids),
            "series_market_count": len(series_market_ids),
            "sport_prefix": sport_prefix,
            "llm_category": llm_category,
            "home_patterns": home_team_patterns,
            "away_patterns": away_team_patterns,
        }

    if len(_related_futures_cache) >= _RELATED_FUTURES_MAX_SIZE:
        oldest = min(_related_futures_cache, key=lambda k: _related_futures_cache[k][0])
        del _related_futures_cache[oldest]
    _related_futures_cache[event_id] = (_now, event.status or "", resp)

    return resp


@router.get("/{event_id}/team-progression")
async def get_team_progression(
    event_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get championship grid progression for both teams in an event.

    Returns each team's probability of reaching each playoff stage
    (e.g., make playoffs → conference → championship), sourced from
    the LeagueContextService (merged multi-source, volume-weighted,
    cached in Redis).

    Used by the GridPlayoffPathPair component on event detail pages.
    """
    import json as _json
    from app.tasks.redis_state import get_redis_client
    _cache_key = f"bainluck:team_progression:{event_id}"
    try:
        _rc = get_redis_client()
        _cached = _rc.get(_cache_key)
        if _cached:
            return _json.loads(_cached)
    except Exception:
        pass

    from app.services.league_context import enrich_event_with_context
    from app.config.league_configs import get_league_for_sport_key, LEAGUE_TO_SPORT

    # Load event with sport
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    sport_key = event.sport.key if event.sport else None
    if not sport_key:
        return {"event_id": event_id, "league": None, "home_team": None, "away_team": None}

    config = get_league_for_sport_key(sport_key)
    if not config:
        return {"event_id": event_id, "league": None, "home_team": None, "away_team": None}

    league_ctx = await enrich_event_with_context(event, db)
    if not league_ctx:
        return {"event_id": event_id, "league": None, "home_team": None, "away_team": None}

    # Convert LeagueContext format to TeamProgressionResponse format
    # so the existing GridPlayoffPathPair component renders correctly
    sport_group = LEAGUE_TO_SPORT.get(config.slug, "")
    grid_url = f"/playoffs/{config.slug}"

    def _build_team(team_ctx, team_name):
        if not team_ctx:
            return None
        stages = []
        for col in league_ctx["columns"]:
            prob = team_ctx["cells"].get(col["key"])
            trend = team_ctx["changes_24h"].get(col["key"])
            # Build per-stage sources from the sources_available list
            sources = [
                {"source": s, "probability": prob}
                for s in (team_ctx.get("sources_available") or [])
            ] if prob is not None else []
            stages.append({
                "key": col["key"],
                "label": col["label"],
                "probability": prob,
                "trend_24h": trend,
                "sources": sources,
            })
        short = team_name.split()[-1] if team_name else ""
        return {
            "name": team_name,
            "short_name": short,
            "team_id": None,
            "logo_url": None,
            "record": team_ctx.get("record"),
            "conference": team_ctx.get("conference"),
            "stages": stages,
        }

    _response = {
        "event_id": event_id,
        "league": config.slug,
        "league_name": config.name,
        "grid_url": grid_url,
        "home_team": _build_team(league_ctx.get("home_team"), event.home_team_name),
        "away_team": _build_team(league_ctx.get("away_team"), event.away_team_name),
    }
    try:
        _rc = get_redis_client()
        _rc.setex(_cache_key, 300, _json.dumps(_response, default=str))
    except Exception:
        pass
    return _response


@router.get("/{event_id}/history")
async def get_event_odds_history(
    event_id: int,
    hours: int = Query(24, description="Hours of history to return"),
    response: Response = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get odds history for trending chart.

    Returns aggregated probability snapshots over time for visualization.
    Each data point represents the consensus across all bookmakers at that time.
    """
    # Verify event exists
    event_result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(Event.id == event_id)
    )
    event = event_result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Get snapshots within time range
    # For completed/closed events, return ALL snapshots (no time window)
    # so users can always see the full probability history.
    # For live/scheduled events, apply a time window to keep responses focused.
    now = datetime.now(timezone.utc)
    is_finished = event.status in ("completed", "closed")

    if response and is_finished:
        response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=300"

    if is_finished:
        # Return snapshots up to 30 min after game end to exclude stale
        # prediction market data from hours/days after completion.
        end_cap = None
        if event.completed_at:
            end_cap = event.completed_at + timedelta(minutes=30)
        elif event.commence_time:
            from app.tasks.odds_polling import get_max_duration_for_sport
            sport_key = event.sport.key if event.sport else ""
            max_hours = get_max_duration_for_sport(sport_key)
            end_cap = event.commence_time + timedelta(hours=max_hours + 0.5)

        query = select(OddsSnapshot).where(OddsSnapshot.event_id == event_id)
        if end_cap:
            query = query.where(OddsSnapshot.captured_at <= end_cap)
        result = await db.execute(query.order_by(OddsSnapshot.captured_at).limit(3000))
        cutoff = None
    else:
        # Include snapshots where:
        # 1. captured_at >= cutoff (created within the window), OR
        # 2. captured_at < cutoff AND valid_until >= cutoff (created before but still valid during window)
        # This ensures we show trend lines even when odds haven't changed for a while
        cutoff = now - timedelta(hours=hours)

        result = await db.execute(
            select(OddsSnapshot)
            .where(
                and_(
                    OddsSnapshot.event_id == event_id,
                    or_(
                        # Case 1: Snapshot created within the time window
                        OddsSnapshot.captured_at >= cutoff,
                        # Case 2: Snapshot created before window but was valid during it
                        and_(
                            OddsSnapshot.captured_at < cutoff,
                            or_(
                                OddsSnapshot.valid_until >= cutoff,
                                # Include if valid_until is NULL (snapshot never superseded)
                                OddsSnapshot.valid_until.is_(None)
                            )
                        )
                    )
                )
            )
            .order_by(OddsSnapshot.captured_at)
            .limit(3000)
        )
    snapshots = result.scalars().all()

    # Group snapshots by capture time and aggregate across bookmakers
    # For snapshots that started before the cutoff but were valid during it,
    # create a synthetic data point at the cutoff time
    from collections import defaultdict
    snapshots_by_time = defaultdict(list)
    for snap in snapshots:
        if cutoff is None or snap.captured_at >= cutoff:
            # Normal case: use actual capture time
            time_key = snap.captured_at.replace(second=0, microsecond=0)
            snapshots_by_time[time_key].append(snap)
        else:
            # Snapshot predates cutoff but was valid during window
            # Create synthetic point at cutoff to show starting value
            time_key = cutoff.replace(second=0, microsecond=0)
            snapshots_by_time[time_key].append(snap)

            # Also add a point at valid_until or now to show the line extends
            if snap.valid_until and snap.valid_until <= now:
                end_key = snap.valid_until.replace(second=0, microsecond=0)
            else:
                end_key = now.replace(second=0, microsecond=0)
            if end_key != time_key:
                snapshots_by_time[end_key].append(snap)

    # Aggregate each time bucket (excluding reversed bookmakers)
    history = []
    for timestamp in sorted(snapshots_by_time.keys()):
        snaps = snapshots_by_time[timestamp]
        reversed_bks = detect_reversed_bookmakers(snaps)
        agg_snaps = [s for s in snaps if s.bookmaker not in reversed_bks] if reversed_bks else snaps
        aggregated = aggregate_bookmaker_odds(agg_snaps if agg_snaps else snaps)

        history.append({
            "timestamp": timestamp.isoformat(),
            "home_probability": aggregated["home_probability"],
            "away_probability": aggregated["away_probability"],
            "over_under": aggregated["over_under"],
            "projected_home_score": aggregated["projected_home_score"],
            "projected_away_score": aggregated["projected_away_score"],
            "bookmaker_count": aggregated["bookmaker_count"],
            "probability_range": {
                "min": aggregated["min_home_probability"],
                "max": aggregated["max_home_probability"],
            },
        })

    # Build per-bookmaker history for individual sportsbook lines
    # Group snapshots by bookmaker
    snapshots_by_bookmaker = defaultdict(list)
    for snap in snapshots:
        snapshots_by_bookmaker[snap.bookmaker].append(snap)

    bookmaker_history = {}
    for bookmaker, bm_snaps in snapshots_by_bookmaker.items():
        # Sort by time
        bm_snaps_sorted = sorted(bm_snaps, key=lambda s: s.captured_at)
        bm_points = []

        for snap in bm_snaps_sorted:
            point_data = {
                "home_probability": float(snap.home_win_probability) if snap.home_win_probability is not None else None,
                "away_probability": float(snap.away_win_probability) if snap.away_win_probability is not None else None,
                "valid_until": snap.valid_until.replace(second=0, microsecond=0).isoformat() if snap.valid_until else None,
                "projected_home_score": float(snap.projected_home_score) if snap.projected_home_score is not None else None,
                "projected_away_score": float(snap.projected_away_score) if snap.projected_away_score is not None else None,
            }

            if cutoff is None or snap.captured_at >= cutoff:
                # Normal case: use actual capture time
                bm_points.append({
                    "timestamp": snap.captured_at.replace(second=0, microsecond=0).isoformat(),
                    **point_data
                })
            else:
                # Snapshot predates cutoff - check if it was valid during window
                # Include if: valid_until >= cutoff OR valid_until is NULL (still current)
                if snap.valid_until is None or snap.valid_until >= cutoff:
                    # Create synthetic point at cutoff
                    bm_points.append({
                        "timestamp": cutoff.replace(second=0, microsecond=0).isoformat(),
                        **point_data
                    })

        # Sort by timestamp
        bm_points_sorted = sorted(bm_points, key=lambda p: p["timestamp"])
        bookmaker_history[bookmaker] = bm_points_sorted

    # Build score history from ScoreSnapshots
    # Wrap in try/except in case the table doesn't exist yet (migration not run)
    score_history = []
    try:
        score_result = await db.execute(
            select(ScoreSnapshot)
            .where(ScoreSnapshot.event_id == event_id)
            .order_by(ScoreSnapshot.captured_at)
        )
        score_snapshots = score_result.scalars().all()

        score_history = [
            {
                "timestamp": snap.captured_at.isoformat(),
                "home_score": snap.home_score,
                "away_score": snap.away_score,
            }
            for snap in score_snapshots
        ]
    except Exception:
        # Table may not exist yet - return empty history
        pass

    # Build ESPN win probability history (legacy, for backwards compatibility)
    espn_history = []
    try:
        from app.models import ESPNSnapshot
        espn_query = select(ESPNSnapshot).where(
            ESPNSnapshot.event_id == event_id,
        )
        if cutoff is not None:
            espn_query = espn_query.where(ESPNSnapshot.captured_at >= cutoff)
        espn_result = await db.execute(
            espn_query.order_by(ESPNSnapshot.captured_at)
        )
        espn_snapshots = espn_result.scalars().all()

        espn_history = [
            {
                "timestamp": snap.captured_at.isoformat(),
                "home_probability": float(snap.home_win_probability) if snap.home_win_probability is not None else None,
                "away_probability": float(snap.away_win_probability) if snap.away_win_probability is not None else None,
                "home_score": snap.home_score,
                "away_score": snap.away_score,
                "game_clock": snap.game_clock,
                "period": snap.period,
            }
            for snap in espn_snapshots
        ]
    except Exception:
        # Table may not exist yet - return empty history
        pass

    # Build multi-source win probability history from generic table
    win_prob_history = {}
    win_prob_sources_meta = {}
    try:
        from app.models.models import WinProbSnapshot
        from app.config.win_prob_sources import WIN_PROB_SOURCES

        wp_query = select(WinProbSnapshot).where(
            WinProbSnapshot.event_id == event_id,
        )
        if cutoff is not None:
            wp_query = wp_query.where(WinProbSnapshot.captured_at >= cutoff)
        if is_finished and end_cap:
            wp_query = wp_query.where(WinProbSnapshot.captured_at <= end_cap)
        wp_result = await db.execute(
            wp_query.order_by(WinProbSnapshot.captured_at)
        )
        wp_snapshots = wp_result.scalars().all()

        # Group by source
        for snap in wp_snapshots:
            source = snap.source
            if source not in win_prob_history:
                win_prob_history[source] = []
            win_prob_history[source].append({
                "timestamp": snap.captured_at.isoformat(),
                "home_probability": float(snap.home_win_probability) if snap.home_win_probability is not None else None,
                "away_probability": float(snap.away_win_probability) if snap.away_win_probability is not None else None,
                "draw_probability": float(snap.draw_probability) if snap.draw_probability is not None else None,
                "game_state": snap.game_state,
            })

        # Build source metadata for sources that have data
        for source_key in win_prob_history:
            source_config = WIN_PROB_SOURCES.get(source_key, {})
            win_prob_sources_meta[source_key] = {
                "display_name": source_config.get("display_name", source_key),
                "type": source_config.get("source_type", "model"),
                "color": source_config.get("color", "#6b7280"),
                "dash_pattern": source_config.get("dash_pattern"),
                "description": source_config.get("description", ""),
                "methodology": source_config.get("methodology", ""),
                "attribution_url": source_config.get("attribution_url"),
                "attribution_name": source_config.get("attribution_name"),
                "snapshot_count": len(win_prob_history[source_key]),
            }
    except Exception:
        # Table may not exist yet
        pass

    # Supplement espn_history with score data from win_prob_history sources.
    # ESPN's scoreboard API provides sparse score data for MLB (~2 points/game).
    # The MLB Stats API source has dense score data in game_state (~50 points/game).
    if len(espn_history) < 10:
        espn_timestamps = {eh["timestamp"][:16] for eh in espn_history}
        for source_key in ("mlb", "stat_model"):
            for wp in win_prob_history.get(source_key, []):
                gs = wp.get("game_state") or {}
                if gs.get("home_score") is not None and gs.get("away_score") is not None:
                    ts_minute = wp["timestamp"][:16]
                    if ts_minute not in espn_timestamps:
                        espn_history.append({
                            "timestamp": wp["timestamp"],
                            "home_probability": wp.get("home_probability"),
                            "away_probability": wp.get("away_probability"),
                            "home_score": gs["home_score"],
                            "away_score": gs["away_score"],
                            "game_clock": gs.get("game_clock"),
                            "period": gs.get("period") or gs.get("inning"),
                        })
                        espn_timestamps.add(ts_minute)
        espn_history.sort(key=lambda x: x["timestamp"])

    # Extract scoring plays — prefer ESPN (full game history) over StatPal (last 10 only)
    espn_scoring = (event.box_score_data or {}).get("scoring_plays", [])
    if espn_scoring:
        # Assign wall-clock timestamps by matching post-play scores to ESPN snapshots
        scoring_plays = _assign_wall_clock_timestamps(espn_scoring, espn_history)
    else:
        # Fallback to StatPal play-by-play data
        scoring_plays = extract_scoring_plays(
            (event.win_probability_sources or {}).get("statpal_plays", [])
        )

    # ── Period markers from scoring_plays table ──
    # Query distinct periods with their earliest timestamp.
    # This provides reliable period boundaries even when ESPN history is empty
    # and win_prob_history lacks period data (e.g., stat_model-only games).
    period_markers = []
    try:
        from app.models.models import ScoringPlay
        pm_result = await db.execute(
            select(
                ScoringPlay.period,
                func.min(ScoringPlay.captured_at).label("first_seen"),
            )
            .where(
                ScoringPlay.event_id == event_id,
                ScoringPlay.period.isnot(None),
                ScoringPlay.period != "",
            )
            .group_by(ScoringPlay.period)
            .order_by(func.min(ScoringPlay.captured_at))
        )
        period_markers = [
            {"timestamp": row.first_seen.isoformat(), "period": row.period}
            for row in pm_result.all()
        ]
    except Exception:
        pass

    # Fallback: derive period markers from computed scoring_plays (ESPN box score)
    # when the ScoringPlay table is empty (e.g., completed games where StatPal
    # only syncs plays during live status).
    if not period_markers and scoring_plays:
        first_seen: dict[str, str] = {}
        for play in scoring_plays:
            period = play.get("period")
            ts = play.get("timestamp")
            if period and ts and period not in first_seen:
                first_seen[period] = ts
        period_markers = [
            {"timestamp": ts, "period": period}
            for period, ts in sorted(first_seen.items(), key=lambda x: x[1])
        ]

    # Third fallback: derive period markers from win_prob_history game_state.
    # Covers games where ScoringPlay table is empty and no ESPN box_score
    # scoring_plays exist, but win_prob_snapshots carry game_state.period
    # (e.g., from ESPN sync or stat_model with period data).
    if not period_markers and win_prob_history:
        first_seen_wp: dict[str, str] = {}
        for source_points in win_prob_history.values():
            for point in source_points:
                gs = point.get("game_state") or {}
                period_val = gs.get("period")
                if isinstance(period_val, str) and period_val:
                    if period_val not in first_seen_wp:
                        first_seen_wp[period_val] = point["timestamp"]
                    continue
                # MLB format: inning + inning_half
                inning = gs.get("inning")
                if isinstance(inning, int) and inning > 0:
                    half = gs.get("inning_half", "top")
                    ordinal = (
                        "1st" if inning == 1 else
                        "2nd" if inning == 2 else
                        "3rd" if inning == 3 else
                        f"{inning}th"
                    )
                    period_str = f"{str(half).capitalize()} {ordinal}"
                    if period_str not in first_seen_wp:
                        first_seen_wp[period_str] = point["timestamp"]
        if first_seen_wp:
            period_markers = [
                {"timestamp": ts, "period": period}
                for period, ts in sorted(first_seen_wp.items(), key=lambda x: x[1])
            ]

    # Fourth fallback: sport-specific estimated period markers.
    # For completed events with no period data from any source, use
    # the sport's standard period structure + commence_time to place
    # approximate markers. Only for sports with fixed period durations.
    if not period_markers and event.commence_time and event.status in ("completed", "closed"):
        sport_key = event.sport.key if event.sport else ""
        ct = event.commence_time
        if sport_key.startswith("soccer"):
            period_markers = [
                {"timestamp": ct.isoformat(), "period": "1H"},
                {"timestamp": (ct + timedelta(minutes=47)).isoformat(), "period": "2H"},
            ]
        elif sport_key.startswith("aussierules"):
            # AFL: 4 quarters, ~20 min each + breaks (~6 min quarter, ~20 min half)
            period_markers = [
                {"timestamp": ct.isoformat(), "period": "1st Quarter"},
                {"timestamp": (ct + timedelta(minutes=26)).isoformat(), "period": "2nd Quarter"},
                {"timestamp": (ct + timedelta(minutes=72)).isoformat(), "period": "3rd Quarter"},
                {"timestamp": (ct + timedelta(minutes=98)).isoformat(), "period": "4th Quarter"},
            ]
        elif sport_key.startswith("basketball"):
            if "ncaab" in sport_key or "wncaab" in sport_key:
                # NCAA basketball: 2 halves of 20 min each
                period_markers = [
                    {"timestamp": ct.isoformat(), "period": "1st Half"},
                    {"timestamp": (ct + timedelta(minutes=55)).isoformat(), "period": "2nd Half"},
                ]
            else:
                # NBA: 4 quarters of 12 min each (real-time ~30-35 min per quarter)
                period_markers = [
                    {"timestamp": ct.isoformat(), "period": "1st Quarter"},
                    {"timestamp": (ct + timedelta(minutes=33)).isoformat(), "period": "2nd Quarter"},
                    {"timestamp": (ct + timedelta(minutes=80)).isoformat(), "period": "3rd Quarter"},
                    {"timestamp": (ct + timedelta(minutes=113)).isoformat(), "period": "4th Quarter"},
                ]
        elif sport_key.startswith("americanfootball"):
            # NFL/NCAA football: 4 quarters of 15 min each (real-time ~45 min per quarter)
            period_markers = [
                {"timestamp": ct.isoformat(), "period": "1st Quarter"},
                {"timestamp": (ct + timedelta(minutes=45)).isoformat(), "period": "2nd Quarter"},
                {"timestamp": (ct + timedelta(minutes=110)).isoformat(), "period": "3rd Quarter"},
                {"timestamp": (ct + timedelta(minutes=155)).isoformat(), "period": "4th Quarter"},
            ]
        elif sport_key.startswith("icehockey"):
            # NHL: 3 periods of 20 min each (real-time ~40 min per period with intermissions)
            period_markers = [
                {"timestamp": ct.isoformat(), "period": "1st Period"},
                {"timestamp": (ct + timedelta(minutes=40)).isoformat(), "period": "2nd Period"},
                {"timestamp": (ct + timedelta(minutes=80)).isoformat(), "period": "3rd Period"},
            ]

    # ── Prediction market spread/total binary contracts ──
    # Query FuturesMarkets linked to this event for spread/total data,
    # then derive implied spread, total, and projected final score.
    pm_spread_data = {}
    try:
        from app.utils.binary_spread import (
            binary_to_implied_spread,
            binary_to_implied_total,
            projected_final_score as calc_projected_score,
            extract_spread_threshold,
            extract_total_threshold,
        )
        from app.models.models import FuturesOddsSnapshot

        # Get all futures markets linked to this event
        fm_result = await db.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(FuturesMarket.event_id == event_id)
        )
        linked_markets = fm_result.scalars().all()

        # Separate spread vs total contracts by source
        spread_contracts_by_source: dict[str, list] = {}
        total_contracts_by_source: dict[str, list] = {}

        for market in linked_markets:
            source = market.source  # "kalshi" or "polymarket"
            for outcome in market.outcomes:
                name = outcome.name or ""
                prob = float(outcome.current_probability) if outcome.current_probability else None
                if prob is None or prob <= 0:
                    continue

                # Try to extract spread threshold
                spread_val = extract_spread_threshold(name)
                if spread_val is not None:
                    if source not in spread_contracts_by_source:
                        spread_contracts_by_source[source] = []
                    spread_contracts_by_source[source].append({
                        "threshold": spread_val,
                        "probability": prob,
                        "name": name,
                    })
                    continue

                # Try to extract total threshold
                total_val = extract_total_threshold(name)
                if total_val is not None:
                    if source not in total_contracts_by_source:
                        total_contracts_by_source[source] = []
                    total_contracts_by_source[source].append({
                        "threshold": total_val,
                        "probability": prob,
                        "name": name,
                    })

        # Derive implied values per source
        implied_spreads = {}
        implied_totals = {}

        for source, contracts in spread_contracts_by_source.items():
            result = binary_to_implied_spread(contracts)
            if result:
                implied_spreads[source] = {
                    "spread": result.spread,
                    "confidence": result.confidence,
                    "contracts": sorted(
                        [{"threshold": c["threshold"], "probability": c["probability"]}
                         for c in contracts],
                        key=lambda x: x["threshold"],
                    ),
                }

        for source, contracts in total_contracts_by_source.items():
            result = binary_to_implied_total(contracts)
            if result:
                implied_totals[source] = {
                    "total": result.total,
                    "confidence": result.confidence,
                    "contracts": sorted(
                        [{"threshold": c["threshold"], "probability": c["probability"]}
                         for c in contracts],
                        key=lambda x: x["threshold"],
                    ),
                }

        # Also include sportsbook spread/total from the odds history
        if history:
            latest = history[-1]
            sb_ou = latest.get("over_under")
            sb_home = latest.get("projected_home_score")
            sb_away = latest.get("projected_away_score")
            if sb_home is not None and sb_away is not None:
                sb_spread = sb_away - sb_home  # negative = home favored
                implied_spreads["sportsbook"] = {
                    "spread": round(sb_spread, 1),
                    "confidence": 1.0,
                    "contracts": [],
                }
            if sb_ou is not None:
                implied_totals["sportsbook"] = {
                    "total": sb_ou,
                    "confidence": 1.0,
                    "contracts": [],
                }

        # Compute projected final score from best available data
        # Priority: kalshi > polymarket > sportsbook
        best_spread = None
        best_spread_source = None
        for src in ["kalshi", "polymarket", "sportsbook"]:
            if src in implied_spreads:
                best_spread = implied_spreads[src]["spread"]
                best_spread_source = src
                break

        best_total = None
        best_total_source = None
        for src in ["kalshi", "polymarket", "sportsbook"]:
            if src in implied_totals:
                best_total = implied_totals[src]["total"]
                best_total_source = src
                break

        projected = None
        if best_spread is not None and best_total is not None:
            proj = calc_projected_score(best_spread, best_total)
            projected = {
                "home_score": proj.home_score,
                "away_score": proj.away_score,
                "spread_source": best_spread_source,
                "total_source": best_total_source,
            }

        pm_spread_data = {
            "implied_spreads": implied_spreads,
            "implied_totals": implied_totals,
            "projected_final": projected,
        }
    except Exception as e:
        logger.warning("Error computing PM spread data for event %d: %s", event_id, e)
        pm_spread_data = {}

    # ── Compute backend aggregate line using the aggregation engine ──
    # Combines sportsbook consensus + all win prob sources into a single
    # weighted-median time series with staleness decay and smoothing.
    aggregate_line = []
    try:
        from app.utils.aggregation import compute_aggregated_probability, TimestampedProb

        agg_sources: dict[str, list] = {}

        # Add sportsbook consensus as "betting" source
        if history:
            agg_sources["betting"] = [
                TimestampedProb(
                    timestamp=datetime.fromisoformat(h["timestamp"]),
                    home_probability=h["home_probability"],
                )
                for h in history
                if h.get("home_probability") is not None
            ]

        # Add each win_prob source
        for source_key, points in win_prob_history.items():
            source_points = [
                TimestampedProb(
                    timestamp=datetime.fromisoformat(p["timestamp"]),
                    home_probability=p["home_probability"],
                )
                for p in points
                if p.get("home_probability") is not None
            ]
            if source_points:
                agg_sources[source_key] = source_points

        if len(agg_sources) > 1:  # Only compute if multiple sources exist
            agg_result = compute_aggregated_probability(agg_sources, bucket_seconds=60)
            aggregate_line = [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "home_probability": p.home_probability,
                }
                for p in agg_result
            ]
    except Exception:
        # Graceful degradation — frontend falls back to naive averaging
        pass

    # ── Inject terminal "final result" data point for completed events ──
    # Without this, the chart's last data point is whatever the last
    # polled value was (e.g., 92%/8%), which can mislead users about
    # the actual outcome. For completed games with scores, inject a
    # resolved 100%/0% (or 0%/100%) point so the chart converges to
    # the correct winner.
    if is_finished and event.home_score is not None and event.away_score is not None:
        if event.home_score != event.away_score:  # Skip ties
            home_won = event.home_score > event.away_score
            resolved_home_prob = 1.0 if home_won else 0.0
            resolved_away_prob = 0.0 if home_won else 1.0

            # Determine terminal timestamp: completed_at if available,
            # otherwise last data point + 1 minute.
            terminal_ts = None
            if event.completed_at:
                terminal_ts = event.completed_at
            else:
                # Find the latest timestamp across all data sources
                latest_candidates = []
                if history:
                    latest_candidates.append(
                        datetime.fromisoformat(history[-1]["timestamp"])
                    )
                if espn_history:
                    latest_candidates.append(
                        datetime.fromisoformat(espn_history[-1]["timestamp"])
                    )
                for wp_points in win_prob_history.values():
                    if wp_points:
                        latest_candidates.append(
                            datetime.fromisoformat(wp_points[-1]["timestamp"])
                        )
                if latest_candidates:
                    terminal_ts = max(latest_candidates) + timedelta(minutes=1)

            if terminal_ts:
                terminal_iso = terminal_ts.replace(second=0, microsecond=0).isoformat()

                # Append to sportsbook history
                if history:
                    history.append({
                        "timestamp": terminal_iso,
                        "home_probability": resolved_home_prob,
                        "away_probability": resolved_away_prob,
                        "over_under": None,
                        "projected_home_score": None,
                        "projected_away_score": None,
                        "bookmaker_count": 0,
                        "probability_range": {
                            "min": resolved_home_prob,
                            "max": resolved_home_prob,
                        },
                    })

                # Append to each win_prob_history source
                for source_key in win_prob_history:
                    if win_prob_history[source_key]:
                        win_prob_history[source_key].append({
                            "timestamp": terminal_iso,
                            "home_probability": resolved_home_prob,
                            "away_probability": resolved_away_prob,
                            "draw_probability": None,
                            "game_state": {"final": True},
                        })

                # Append to ESPN history
                if espn_history:
                    espn_history.append({
                        "timestamp": terminal_iso,
                        "home_probability": resolved_home_prob,
                        "away_probability": resolved_away_prob,
                        "home_score": event.home_score,
                        "away_score": event.away_score,
                        "game_clock": "Final",
                        "period": "Final",
                    })

                # Append to aggregate line
                if aggregate_line:
                    aggregate_line.append({
                        "timestamp": terminal_iso,
                        "home_probability": resolved_home_prob,
                    })

    return {
        "event_id": event_id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "commence_time": event.commence_time.isoformat() if event.commence_time else None,
        "completed_at": event.completed_at.isoformat() if event.completed_at else None,
        "status": event.status,
        "history": history,
        "bookmaker_history": bookmaker_history,
        "score_history": score_history,
        "espn_history": espn_history,
        "win_prob_history": win_prob_history,
        "win_prob_sources": win_prob_sources_meta,
        "scoring_plays": scoring_plays,
        "period_markers": period_markers,
        "aggregate_line": aggregate_line if aggregate_line else None,
        "pm_spread_data": pm_spread_data if pm_spread_data else None,
        "points": len(history),
        "bookmaker_count": len(bookmaker_history),
        "snapshot_count": len(snapshots),
        "espn_snapshot_count": len(espn_history),
    }


@router.get("/{event_id}/line-movement")
async def get_line_movement_analysis(
    event_id: int,
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Get line movement analysis and AI-generated explanations for an event.

    Detects significant odds movements from historical snapshots and returns
    AI-generated explanations for why lines moved and any prediction market
    disagreements.

    Results are cached in the database with TTLs based on event status:
    - Scheduled: 1 hour
    - Live: 15 minutes
    - Completed/Closed: permanent (never re-computed)
    """
    from app.models import LineMovementAnalysis as LineMovementModel
    from app.utils.line_movement import detect_line_movements, build_llm_prompt

    # Verify event exists
    event_result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(Event.id == event_id)
    )
    event = event_result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    now = datetime.now(timezone.utc)

    # Check for cached analysis
    cached = await db.execute(
        select(LineMovementModel)
        .where(
            LineMovementModel.event_id == event_id,
            LineMovementModel.analysis_type == "line_movement",
        )
        .order_by(LineMovementModel.created_at.desc())
        .limit(1)
    )
    cached_analysis = cached.scalar_one_or_none()

    if cached_analysis:
        # Check if still valid
        if cached_analysis.expires_at is None or cached_analysis.expires_at > now:
            # Extract stored context metadata if available
            stored_movement_data = cached_analysis.movement_data or []
            stored_context = None
            if isinstance(stored_movement_data, dict):
                stored_context = stored_movement_data.get("context")
                stored_movement_data = stored_movement_data.get("movements", [])
            return {
                "event_id": event_id,
                "movements": stored_movement_data,
                "explanation": cached_analysis.explanation,
                "disagreement_explanation": cached_analysis.disagreement_explanation,
                "disagreement_data": cached_analysis.disagreement_data,
                "context": stored_context,
                "cached": True,
                "created_at": cached_analysis.created_at.isoformat(),
            }

    # Build fresh analysis from snapshots
    result = await db.execute(
        select(OddsSnapshot)
        .where(OddsSnapshot.event_id == event_id)
        .order_by(OddsSnapshot.captured_at)
    )
    snapshots = result.scalars().all()

    # Aggregate snapshots into time buckets (median across bookmakers per minute)
    from collections import defaultdict
    import statistics

    snapshots_by_time = defaultdict(list)
    for snap in snapshots:
        time_key = snap.captured_at.replace(second=0, microsecond=0)
        if snap.home_win_probability is not None:
            snapshots_by_time[time_key].append({
                "home_probability": float(snap.home_win_probability),
                "bookmaker_count": 1,
            })

    aggregated_snapshots = []
    for timestamp in sorted(snapshots_by_time.keys()):
        probs = [s["home_probability"] for s in snapshots_by_time[timestamp]]
        aggregated_snapshots.append({
            "timestamp": timestamp,
            "home_probability": statistics.median(probs),
            "bookmaker_count": len(probs),
        })

    # Detect line movements
    opening_home_prob = float(event.opening_home_probability) if event.opening_home_probability else None
    analysis = detect_line_movements(
        snapshots=aggregated_snapshots,
        opening_home_prob=opening_home_prob,
        event_status=event.status,
        home_team=event.home_team_name or "",
        away_team=event.away_team_name or "",
        sport_key=event.sport.key if event.sport else "",
    )

    # Serialize movements for response and caching
    movements_data = [
        {
            "timestamp_start": m.timestamp_start.isoformat(),
            "timestamp_end": m.timestamp_end.isoformat(),
            "home_prob_before": round(m.home_prob_before, 4),
            "home_prob_after": round(m.home_prob_after, 4),
            "change": round(m.change, 4),
            "magnitude": round(m.magnitude, 4),
            "direction": m.direction,
            "context": m.context,
            "is_major": m.is_major,
        }
        for m in analysis.movements
    ]

    # Generate AI explanation if significant movements found
    explanation = None
    injuries_data = None
    news_headlines = None
    game_context = None
    scoring_plays_data = None

    if analysis.movements:
        # Fetch real context from ESPN for grounded explanations
        if event.espn_id and event.sport:
            try:
                from app.services.espn_api import ESPNAPIService
                espn = ESPNAPIService()
                ctx = await espn.get_event_context(event.sport.key, event.espn_id)
                if ctx.get("injuries"):
                    injuries_data = [
                        {
                            "player_name": i.player_name,
                            "team_name": i.team_name,
                            "status": i.status,
                            "injury_type": i.injury_type,
                        }
                        for i in ctx["injuries"]
                    ]
                if ctx.get("news"):
                    news_headlines = [n.headline for n in ctx["news"][:5]]
                await espn.close()
            except Exception as e:
                logger.warning(f"ESPN context fetch failed for event {event_id}: {e}")

        # Merge StatPal injuries (pre-fetched in DB) with ESPN injuries
        statpal_injuries_raw = (event.win_probability_sources or {}).get("statpal_injuries", [])
        if statpal_injuries_raw:
            # Map StatPal keys to ESPN-format keys
            statpal_injuries = [
                {
                    "player_name": inj.get("player", ""),
                    "team_name": inj.get("team", ""),
                    "status": inj.get("status", ""),
                    "injury_type": inj.get("type", ""),
                    "detail": inj.get("detail", ""),
                    "expected_return": inj.get("expected_return", ""),
                }
                for inj in statpal_injuries_raw
                if inj.get("player")
            ]
            if injuries_data:
                # Dedup by player name — ESPN takes priority
                espn_players = {inj["player_name"].lower() for inj in injuries_data}
                for sp_inj in statpal_injuries:
                    if sp_inj["player_name"].lower() not in espn_players:
                        injuries_data.append(sp_inj)
            else:
                injuries_data = statpal_injuries

        # For completed games, only include injuries for players actually OUT
        # (skip Questionable/Day-to-Day which are noise for post-game explanation)
        if event.status in ("completed", "closed") and injuries_data:
            injuries_data = [i for i in injuries_data if i.get("status") in ("Out", "Doubtful")]
        injuries_data = (injuries_data or [])[:5]

        # Extract scoring plays — prefer scoring_plays table (full history),
        # fall back to JSONB (last 10 plays) for events without table data
        try:
            from app.models.models import ScoringPlay
            sp_result = await db.execute(
                select(ScoringPlay)
                .where(ScoringPlay.event_id == event.id)
                .order_by(ScoringPlay.captured_at.asc())
            )
            sp_rows = sp_result.scalars().all()
            if sp_rows:
                scoring_plays_data = [
                    {
                        "period": p.period,
                        "clock": p.game_clock,
                        "description": p.description,
                        "type": p.play_type,
                        "team": p.team_name,
                        "player": p.player_name,
                        "home_score": p.home_score,
                        "away_score": p.away_score,
                    }
                    for p in sp_rows
                ]
        except Exception as e:
            logger.warning(f"ScoringPlay query failed for event {event_id}: {e}")

        # Fallback: JSONB blob (backward compat for events without table data)
        if not scoring_plays_data:
            scoring_plays_data = extract_scoring_plays(
                (event.win_probability_sources or {}).get("statpal_plays", [])
            )

        if event.status in ("live", "completed", "closed"):
            game_context = {
                "home_team": event.home_team_name,
                "away_team": event.away_team_name,
                "home_score": event.home_score,
                "away_score": event.away_score,
                "period": event.period if event.status == "live" else "Final",
                "clock": event.game_clock if event.status == "live" else None,
            }

        # Fetch team season stats for richer context
        team_stats = None
        try:
            team_result = await db.execute(
                select(Team).where(
                    Team.name.in_([event.home_team_name, event.away_team_name])
                )
            )
            teams = {t.name: t for t in team_result.scalars().all()}
            home_t = teams.get(event.home_team_name)
            away_t = teams.get(event.away_team_name)
            if (home_t and getattr(home_t, "season_stats", None)) or \
               (away_t and getattr(away_t, "season_stats", None)):
                team_stats = {
                    "home_team": event.home_team_name,
                    "away_team": event.away_team_name,
                    "home_stats": home_t.season_stats if home_t else None,
                    "away_stats": away_t.season_stats if away_t else None,
                }
        except Exception as e:
            logger.warning(f"Team stats fetch failed for event {event_id}: {e}")

        # Skip LLM when we have no real context — it can only restate
        # what the movement cards already show, producing filler text
        has_any_context = bool(injuries_data) or bool(news_headlines) or bool(game_context) or bool(team_stats) or bool(scoring_plays_data)
        if has_any_context:
            prompt = build_llm_prompt(
                analysis,
                injuries=injuries_data,
                news_headlines=news_headlines,
                game_context=game_context,
                team_stats=team_stats,
                scoring_plays=scoring_plays_data,
            )
            try:
                from app.services.llm import generate_line_movement_explanation
                explanation = generate_line_movement_explanation(prompt)
            except Exception as e:
                logger.warning(f"LLM explanation failed for event {event_id}: {e}")

    # Check for prediction market disagreement
    disagreement_explanation = None
    disagreement_data = None

    # Look for prediction market win_prob_snapshots
    try:
        from app.models.models import WinProbSnapshot
        pm_result = await db.execute(
            select(WinProbSnapshot)
            .where(
                WinProbSnapshot.event_id == event_id,
                WinProbSnapshot.source.in_(["kalshi", "polymarket"]),
            )
            .order_by(WinProbSnapshot.captured_at.desc())
            .limit(2)
        )
        pm_snapshots = pm_result.scalars().all()

        if pm_snapshots and opening_home_prob is not None:
            # Compare latest prediction market price to sportsbook consensus
            pm_snap = pm_snapshots[0]
            pm_prob = float(pm_snap.home_probability) if pm_snap.home_probability is not None else None
            sportsbook_prob = opening_home_prob

            # Use latest aggregated odds if available
            if aggregated_snapshots:
                sportsbook_prob = aggregated_snapshots[-1]["home_probability"]

            if pm_prob is not None and sportsbook_prob is not None:
                divergence = abs(pm_prob - sportsbook_prob)
                if divergence >= 0.05:  # 5% disagreement threshold
                    disagreement_data = {
                        "sportsbook_home_prob": round(sportsbook_prob, 4),
                        "prediction_market_home_prob": round(pm_prob, 4),
                        "source": pm_snap.source,
                        "divergence": round(divergence, 4),
                    }

                    try:
                        from app.services.llm import generate_market_disagreement_explanation
                        disagreement_explanation = generate_market_disagreement_explanation(
                            home_team=event.home_team_name or "",
                            away_team=event.away_team_name or "",
                            sport_key=event.sport.key if event.sport else "",
                            sportsbook_home_prob=sportsbook_prob,
                            prediction_market_home_prob=pm_prob,
                            prediction_market_source=pm_snap.source,
                            divergence_pct=divergence,
                        )
                    except Exception as e:
                        logger.warning(f"Disagreement explanation failed for event {event_id}: {e}")
    except Exception:
        pass  # win_prob_snapshots table may not exist or other DB issue

    # Cache the analysis
    ttl = None
    if event.status == "scheduled":
        ttl = timedelta(hours=1)
    elif event.status == "live":
        ttl = timedelta(minutes=15)
    # completed/closed: no expiry (permanent cache)

    expires_at = (now + ttl) if ttl else None

    # Build context metadata for response
    context_meta = {
        "injuries_count": len(injuries_data) if injuries_data else 0,
        "news_count": len(news_headlines) if news_headlines else 0,
        "has_game_state": bool(game_context),
        "has_team_stats": bool(team_stats),
        "scoring_plays_count": len(scoring_plays_data) if scoring_plays_data else 0,
    }

    # Store movements + context together in movement_data JSONB
    cache_data = {
        "movements": movements_data,
        "context": context_meta,
    }

    # Upsert cached analysis
    if cached_analysis:
        cached_analysis.movement_data = cache_data
        cached_analysis.explanation = explanation
        cached_analysis.disagreement_explanation = disagreement_explanation
        cached_analysis.disagreement_data = disagreement_data
        cached_analysis.expires_at = expires_at
    else:
        new_analysis = LineMovementModel(
            event_id=event_id,
            movement_data=cache_data,
            explanation=explanation,
            disagreement_explanation=disagreement_explanation,
            disagreement_data=disagreement_data,
            analysis_type="line_movement",
            expires_at=expires_at,
        )
        db.add(new_analysis)

    try:
        await db.commit()
    except Exception:
        await db.rollback()

    return {
        "event_id": event_id,
        "movements": movements_data,
        "explanation": explanation,
        "disagreement_explanation": disagreement_explanation,
        "disagreement_data": disagreement_data,
        "context": context_meta,
        "cached": False,
        "created_at": now.isoformat(),
    }


@router.get("/{event_id}/debug")
async def debug_event_snapshots(
    event_id: int,
    limit: int = Query(10, description="Number of snapshots to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Debug endpoint to check raw snapshot data for an event.

    Returns recent snapshots with all fields to diagnose data issues.
    """
    # Verify event exists
    event_result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(Event.id == event_id)
    )
    event = event_result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Get recent snapshots
    result = await db.execute(
        select(OddsSnapshot)
        .where(OddsSnapshot.event_id == event_id)
        .order_by(OddsSnapshot.captured_at.desc())
        .limit(limit)
    )
    snapshots = result.scalars().all()

    # Return raw data for debugging
    snapshot_data = []
    for snap in snapshots:
        snapshot_data.append({
            "id": snap.id,
            "bookmaker": snap.bookmaker,
            "captured_at": snap.captured_at.isoformat(),
            "valid_until": snap.valid_until.isoformat() if snap.valid_until else None,
            "reading_count": snap.reading_count,
            "home_moneyline": snap.home_moneyline,
            "away_moneyline": snap.away_moneyline,
            "home_win_probability": float(snap.home_win_probability) if snap.home_win_probability else None,
            "away_win_probability": float(snap.away_win_probability) if snap.away_win_probability else None,
            "home_spread": float(snap.home_spread) if snap.home_spread else None,
            "home_spread_odds": snap.home_spread_odds,
            "away_spread_odds": snap.away_spread_odds,
            "over_under": float(snap.over_under) if snap.over_under else None,
            "over_odds": snap.over_odds,
            "under_odds": snap.under_odds,
            "projected_home_score": float(snap.projected_home_score) if snap.projected_home_score else None,
            "projected_away_score": float(snap.projected_away_score) if snap.projected_away_score else None,
        })

    # Summary statistics
    has_spread = sum(1 for s in snapshot_data if s["home_spread"] is not None)
    has_totals = sum(1 for s in snapshot_data if s["over_under"] is not None)
    has_projected = sum(1 for s in snapshot_data if s["projected_home_score"] is not None)

    return {
        "event_id": event_id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "total_snapshots": len(snapshot_data),
        "summary": {
            "snapshots_with_spread": has_spread,
            "snapshots_with_totals": has_totals,
            "snapshots_with_projected_scores": has_projected,
        },
        "snapshots": snapshot_data,
    }


# In-memory cache for team lookup data (colors/logos change very rarely)
_team_cache: dict = {}
_team_cache_time: float = 0
_TEAM_CACHE_TTL = 300  # 5 minutes


async def _build_team_lookup(db: AsyncSession, team_names: list[str]) -> dict:
    """Build a mapping of team names to Team objects for color/logo data.

    Matches on exact name or alternate_names JSONB array.
    Only returns teams that have ESPN enrichment (color or logo).

    Uses an in-memory cache since the teams table is small (~500 rows)
    and team colors/logos change very rarely. This avoids N JSONB ?
    conditions per request (previously one per team name).
    """
    import time

    global _team_cache, _team_cache_time

    if not team_names:
        return {}

    now = time.monotonic()
    if _team_cache and (now - _team_cache_time) < _TEAM_CACHE_TTL:
        # Fast path: filter cached lookup by requested names
        names_set = set(team_names)
        return {k: v for k, v in _team_cache.items() if k in names_set}

    # Load all teams with ESPN data (small table) — single simple query
    result = await db.execute(
        select(Team).where(
            or_(Team.primary_color.isnot(None), Team.logo_url_small.isnot(None))
        )
    )
    teams = result.scalars().all()

    # Build full lookup: map all known names to team objects
    full_lookup = {}
    for team in teams:
        full_lookup[team.name] = team
        if team.alternate_names:
            for alt_name in team.alternate_names:
                full_lookup[alt_name] = team

    _team_cache = full_lookup
    _team_cache_time = now

    # Return only the subset matching requested names
    names_set = set(team_names)
    return {k: v for k, v in full_lookup.items() if k in names_set}


def _compute_standings_context(home_team, away_team, home_name: str, away_name: str) -> dict | None:
    """Compute standings context text for an event.

    Returns a dict with 'home', 'away' record strings and optional 'stakes' text,
    or None if no standings data is available.
    """
    if not home_team and not away_team:
        return None

    context = {}

    # Format record strings (e.g., "34-18, 2nd East")
    for team, name, key in [(home_team, home_name, "home"), (away_team, away_name, "away")]:
        if not team or not getattr(team, "standings_data", None):
            continue
        s = team.standings_data
        parts = []
        # Win-loss record
        if "wins" in s and "losses" in s:
            record = f"{s['wins']}-{s['losses']}"
            if s.get("draws") or s.get("ties"):
                record += f"-{s.get('draws') or s.get('ties')}"
            parts.append(record)
        # Conference/division rank
        if s.get("conf_rank"):
            conf = s.get("conference", "")
            parts.append(f"#{s['conf_rank']} {conf}".strip())
        elif s.get("div_rank"):
            div = s.get("division", "")
            parts.append(f"#{s['div_rank']} {div}".strip())
        elif s.get("league_rank"):
            parts.append(f"#{s['league_rank']}")
        # Points (soccer)
        if "points" in s and "wins" in s:
            parts.append(f"{s['points']} pts")

        if parts:
            context[key] = ", ".join(parts)

    if not context:
        return None

    # Compute simple stakes text via rules
    stakes = None
    if home_team and away_team:
        hs = getattr(home_team, "standings_data", None) or {}
        aws = getattr(away_team, "standings_data", None) or {}

        # Same division rivals
        if hs.get("division") and hs.get("division") == aws.get("division"):
            try:
                hr = int(hs["div_rank"])
                ar = int(aws["div_rank"])
                if abs(hr - ar) <= 2:
                    stakes = "Division rivals"
            except (KeyError, ValueError, TypeError):
                pass

        # Fighting for top seed
        if not stakes:
            try:
                hr = int(hs.get("conf_rank") or hs.get("league_rank"))
                ar = int(aws.get("conf_rank") or aws.get("league_rank"))
                if hr <= 3 and ar <= 3:
                    stakes = "Top seed matchup"
            except (ValueError, TypeError):
                pass

        # Games back context
        if not stakes and hs.get("gb") is not None and aws.get("gb") is not None:
            try:
                diff = abs(float(hs["gb"]) - float(aws["gb"]))
                if diff <= 2:
                    stakes = f"{diff:.1f} games apart in standings".rstrip("0").rstrip(".")
            except (ValueError, TypeError):
                pass

    if stakes:
        context["stakes"] = stakes

    return context


def _format_team_data(team: Team) -> dict:
    """Format team data for API response."""
    data = {
        "team_id": team.id,
        "slug": getattr(team, "slug", None),
        "primary_color": team.primary_color,
        "secondary_color": team.secondary_color,
        "logo_small": team.logo_url_small,
        "logo_large": team.logo_url_large,
        "record": team.current_record,
    }
    if team.abbreviation:
        data["abbreviation"] = team.abbreviation
    # Include standings if available
    if getattr(team, "standings_data", None):
        data["standings"] = team.standings_data
    # Include season stats if available
    if getattr(team, "season_stats", None):
        data["season_stats"] = team.season_stats
    return data


def _format_event(event: Event, gei_percentiles: dict = None, team_lookup: dict = None) -> dict:
    """Format event for API response.

    Args:
        team_lookup: Optional dict mapping team names to Team objects for color/logo data.
    """
    response = {
        "id": event.id,
        "external_id": event.external_id,
        "sport": event.sport.key if event.sport else None,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "commence_time": event.commence_time.isoformat(),
        "status": event.status,
        "home_score": event.home_score,
        "away_score": event.away_score,
    }

    # Add team data (colors, logos) from lookup
    if team_lookup:
        home_team = team_lookup.get(event.home_team_name)
        away_team = team_lookup.get(event.away_team_name)
        if home_team and (home_team.primary_color or home_team.logo_url_small):
            response["home_team_data"] = _format_team_data(home_team)
        if away_team and (away_team.primary_color or away_team.logo_url_small):
            response["away_team_data"] = _format_team_data(away_team)

    # Add LLM metadata if available
    try:
        if event.llm_gender or event.llm_level or event.llm_league or event.llm_importance:
            response["metadata"] = {
                "gender": event.llm_gender,
                "level": event.llm_level,
                "league": event.llm_league,
                "importance": event.llm_importance,
            }
    except AttributeError:
        pass  # Columns may not exist yet

    # Add ESPN enrichment if available
    try:
        espn_data = {}
        if event.espn_id:
            espn_data["espn_id"] = event.espn_id
        sport_key = event.sport.key if event.sport else None
        display_period, display_clock = normalize_live_game_state(
            sport_key,
            event.period,
            event.game_clock,
        )
        if display_clock:
            espn_data["game_clock"] = display_clock
        if display_period:
            espn_data["period"] = display_period
        if event.broadcast_info:
            espn_data["broadcast"] = event.broadcast_info
        if event.espn_win_prob_home is not None:
            espn_data["win_probability"] = float(event.espn_win_prob_home)
        if event.win_probability_sources:
            espn_data["probability_sources"] = event.win_probability_sources

        if espn_data:
            response["espn"] = espn_data

        # Also expose win_probability_sources at top level with source metadata
        if event.win_probability_sources:
            try:
                from app.config.win_prob_sources import WIN_PROB_SOURCES
                wp_sources = {}
                for src_key, src_value in event.win_probability_sources.items():
                    if src_key.startswith("_"):
                        continue
                    source_config = WIN_PROB_SOURCES.get(src_key, {})
                    wp_sources[src_key] = {
                        "value": src_value,
                        "display_name": source_config.get("display_name", src_key),
                        "type": source_config.get("source_type", "model"),
                        "color": source_config.get("color", "#6b7280"),
                    }
                if wp_sources:
                    response["win_probability_sources"] = wp_sources
            except Exception:
                pass
    except AttributeError:
        pass  # Columns may not exist yet

    # Add EI (Excitement Index) data if available (for live and completed events)
    # Wrap in try/except in case columns don't exist yet (migration not applied)
    try:
        if event.raw_ei is not None:
            from app.utils.excitement_index import get_ei_label, get_ei_emoji, get_ei_status
            import json

            raw_ei = float(event.raw_ei)

            # Parse metadata if stored
            metadata = None
            if event.ei_metadata:
                try:
                    metadata = json.loads(event.ei_metadata)
                except json.JSONDecodeError:
                    pass

            # Compute percentile score from the stored thresholds.
            # Use sport-specific percentile if available, fall back to global.
            sport_key = event.sport.key if event.sport else None
            percentile_score = None
            if gei_percentiles:
                if sport_key:
                    percentile_score = _calculate_percentile(raw_ei, gei_percentiles, sport_key)
                if percentile_score is None:
                    percentile_score = _calculate_percentile(raw_ei, gei_percentiles, 'global')

            # Use percentile as the display score when available, raw conversion as fallback
            raw_score = max(1, min(100, round(raw_ei * 100)))
            display_score = percentile_score if percentile_score is not None else raw_score

            ei_data = {
                "score": display_score,
                "raw_score": raw_score,
                "status": get_ei_status(display_score),
                "label": get_ei_label(display_score),
                "emoji": get_ei_emoji(display_score),
                "metadata": metadata,
            }
            response["ei"] = ei_data
            # Backward compatibility: also emit as "pulse" for existing frontends
            response["pulse"] = ei_data
    except Exception as e:
        # EI columns may not exist yet or other error - log for debugging
        import logging
        logging.warning(f"Error adding EI data for event {event.id}: {e}")

    return response


def _calculate_percentile(raw_ei: float, percentiles: dict, scope: str) -> int:
    """Calculate percentile from raw EI using stored thresholds."""
    if not percentiles or scope not in percentiles:
        return None

    thresholds = percentiles[scope]
    for p in range(100, 0, -1):
        if p in thresholds and raw_ei >= thresholds[p]:
            return p
    return 1


def _format_event_with_odds(event: Event) -> dict:
    """Format event for API response including current odds."""
    response = _format_event(event)

    # Get latest odds snapshot
    if event.odds_snapshots:
        latest_odds = max(
            event.odds_snapshots,
            key=lambda x: x.captured_at
        )
        response["current_odds"] = {
            "bookmaker": latest_odds.bookmaker,
            "captured_at": latest_odds.captured_at.isoformat(),
            "home_moneyline": latest_odds.home_moneyline,
            "away_moneyline": latest_odds.away_moneyline,
            "home_probability": float(latest_odds.home_win_probability)
                if latest_odds.home_win_probability else None,
            "away_probability": float(latest_odds.away_win_probability)
                if latest_odds.away_win_probability else None,
            "spread": float(latest_odds.home_spread)
                if latest_odds.home_spread else None,
            "over_under": float(latest_odds.over_under)
                if latest_odds.over_under else None,
            "projected_home_score": float(latest_odds.projected_home_score)
                if latest_odds.projected_home_score else None,
            "projected_away_score": float(latest_odds.projected_away_score)
                if latest_odds.projected_away_score else None,
        }

    return response


def _format_event_with_latest_odds(event: Event, latest_odds: Optional[OddsSnapshot]) -> dict:
    """Format event for API response with pre-fetched latest odds (memory efficient)."""
    response = _format_event(event)

    if latest_odds:
        response["current_odds"] = {
            "bookmaker": latest_odds.bookmaker,
            "captured_at": latest_odds.captured_at.isoformat(),
            "home_moneyline": latest_odds.home_moneyline,
            "away_moneyline": latest_odds.away_moneyline,
            "home_probability": float(latest_odds.home_win_probability)
                if latest_odds.home_win_probability else None,
            "away_probability": float(latest_odds.away_win_probability)
                if latest_odds.away_win_probability else None,
            "spread": float(latest_odds.home_spread)
                if latest_odds.home_spread else None,
            "over_under": float(latest_odds.over_under)
                if latest_odds.over_under else None,
            "projected_home_score": float(latest_odds.projected_home_score)
                if latest_odds.projected_home_score else None,
            "projected_away_score": float(latest_odds.projected_away_score)
                if latest_odds.projected_away_score else None,
        }

    return response


def _format_event_with_aggregated_odds(event: Event, odds_data: Optional[dict], gei_percentiles: dict = None, team_lookup: dict = None, time_series_metrics=None) -> dict:
    """Format event for API response with aggregated odds from multiple bookmakers."""
    response = _format_event(event, gei_percentiles, team_lookup=team_lookup)

    current_home_prob = None
    current_away_prob = None
    current_spread = None
    current_ou = None

    if odds_data and odds_data.get("aggregated"):
        aggregated = odds_data["aggregated"]
        captured_at = odds_data.get("captured_at")
        snapshots = odds_data.get("snapshots", [])

        current_home_prob = aggregated["home_probability"]
        current_away_prob = aggregated["away_probability"]
        current_spread = aggregated["home_spread"]
        current_ou = aggregated["over_under"]

        response["current_odds"] = {
            "captured_at": captured_at.isoformat() if captured_at else None,
            "home_probability": aggregated["home_probability"],
            "away_probability": aggregated["away_probability"],
            "spread": aggregated["home_spread"],
            "over_under": aggregated["over_under"],
            "projected_home_score": aggregated["projected_home_score"],
            "projected_away_score": aggregated["projected_away_score"],
            "bookmaker_count": aggregated["bookmaker_count"],
            "probability_range": {
                "min": aggregated["min_home_probability"],
                "max": aggregated["max_home_probability"],
            },
        }

        # Include ALL bookmakers in the table (not just filtered ones)
        # so users see every book we ever had odds from
        all_snapshots = odds_data.get("all_snapshots", snapshots)
        if all_snapshots:
            reversed_bks = detect_reversed_bookmakers(all_snapshots)
            bookmaker_odds_list = []
            for s in all_snapshots:
                if s.bookmaker in reversed_bks:
                    bookmaker_odds_list.append({
                        "bookmaker": s.bookmaker,
                        "home_moneyline": s.away_moneyline,
                        "away_moneyline": s.home_moneyline,
                        "home_probability": float(s.away_win_probability)
                            if s.away_win_probability else None,
                        "away_probability": float(s.home_win_probability)
                            if s.home_win_probability else None,
                        "captured_at": s.captured_at.isoformat(),
                        "spread": -float(s.home_spread) if s.home_spread else None,
                        "over_under": float(s.over_under) if s.over_under else None,
                        "projected_home_score": float(s.projected_away_score)
                            if s.projected_away_score else None,
                        "projected_away_score": float(s.projected_home_score)
                            if s.projected_home_score else None,
                    })
                else:
                    bookmaker_odds_list.append({
                        "bookmaker": s.bookmaker,
                        "home_moneyline": s.home_moneyline,
                        "away_moneyline": s.away_moneyline,
                        "home_probability": float(s.home_win_probability)
                            if s.home_win_probability else None,
                        "away_probability": float(s.away_win_probability)
                            if s.away_win_probability else None,
                        "captured_at": s.captured_at.isoformat(),
                        "spread": float(s.home_spread) if s.home_spread else None,
                        "over_under": float(s.over_under) if s.over_under else None,
                        "projected_home_score": float(s.projected_home_score)
                            if s.projected_home_score else None,
                        "projected_away_score": float(s.projected_away_score)
                            if s.projected_away_score else None,
                    })
            response["bookmaker_odds"] = bookmaker_odds_list

    # Compute highlight data (Level 1 + Level 2 if time_series available)
    highlight_result = compute_highlight(
        status=event.status,
        commence_time=event.commence_time,
        sport_key=event.sport.key if event.sport else None,
        current_home_prob=current_home_prob,
        current_away_prob=current_away_prob,
        current_home_spread=current_spread,
        current_over_under=current_ou,
        opening_home_prob=float(event.opening_home_probability) if event.opening_home_probability else None,
        opening_away_prob=float(event.opening_away_probability) if event.opening_away_probability else None,
        opening_home_spread=float(event.opening_home_spread) if event.opening_home_spread else None,
        opening_over_under=float(event.opening_over_under) if event.opening_over_under else None,
        opening_favorite=event.opening_favorite,
        time_series=time_series_metrics,
    )

    response["highlight"] = {
        "score": highlight_result.score,
        "reasons": highlight_result.reasons,
        "label": get_highlight_label(highlight_result),
        "should_feature": should_highlight(highlight_result),
        "flags": {
            "is_live": highlight_result.flags.is_live,
            "is_close_matchup": highlight_result.flags.is_close_matchup,
            "is_blowout": highlight_result.flags.is_blowout,
            "favorite_switched": highlight_result.flags.favorite_switched,
            "probability_swing": highlight_result.flags.probability_swing,
            "score_swing": highlight_result.flags.score_swing,
            "is_starting_soon": highlight_result.flags.is_starting_soon,
            "is_recently_finished": highlight_result.flags.is_recently_finished,
            "is_upset": highlight_result.flags.is_upset,
            "league_tier": highlight_result.flags.league_tier,
            "is_volatile": highlight_result.flags.is_volatile,
            "has_lead_changes": highlight_result.flags.has_lead_changes,
            "has_recent_momentum": highlight_result.flags.has_recent_momentum,
        },
    }

    # Include opening odds for transparency
    if event.opening_home_probability:
        response["opening_odds"] = {
            "home_probability": float(event.opening_home_probability),
            "away_probability": float(event.opening_away_probability) if event.opening_away_probability else None,
            "spread": float(event.opening_home_spread) if event.opening_home_spread else None,
            "over_under": float(event.opening_over_under) if event.opening_over_under else None,
            "favorite": event.opening_favorite,
        }

    return response


def _is_placeholder_outcome_name(name: str) -> bool:
    """Detect Polymarket placeholder outcome names (e.g., 'Player B', 'Player S')."""
    return bool(re.match(r"^Player\s+[A-Z]$", (name or "").strip()))


def _format_futures_for_search(market: FuturesMarket) -> dict:
    """Format a futures market for search results."""
    # Filter out Polymarket placeholder outcomes before sorting/display.
    # These are reserved slots with names like "Player B" and fake 100% probs.
    real_outcomes = [
        o for o in market.outcomes
        if not _is_placeholder_outcome_name(o.name)
    ]

    # Sort outcomes by probability to get top outcomes
    sorted_outcomes = sorted(
        real_outcomes,
        key=lambda o: o.current_probability or 0,
        reverse=True
    )

    top_outcomes = [
        {
            "id": o.id,
            "name": o.name,
            "probability": float(o.current_probability) if o.current_probability else None,
            "american_odds": o.current_american_odds,
            "rank": o.rank,
            "movement": float(o.probability_change_24h) if o.probability_change_24h else None,
        }
        for o in sorted_outcomes[:5]
    ]

    _TIER_LABELS_SEARCH = {1: "Championship", 2: "Conference", 3: "Award", 4: "Division", 5: "Prop"}
    return {
        "id": market.id,
        "name": market.name,
        "sport": market.sport.key if market.sport else None,
        "sport_name": market.sport.name if market.sport else None,
        "category": market.category,
        "llm_sport_category": market.llm_sport_category,
        "market_tier": market.market_tier,
        "market_type_label": _TIER_LABELS_SEARCH.get(market.market_tier, market.market_type or "Market"),
        "status": market.status,
        "source": market.source,
        "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
        "top_outcomes": top_outcomes,
        "outcome_count": len(real_outcomes),
        "updated_at": market.updated_at.isoformat() if market.updated_at else None,
    }
