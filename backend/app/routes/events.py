"""Events API endpoints."""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_, func, case, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert

from app.models import Event, OddsSnapshot, Sport, ScoreSnapshot, EIPercentile, FuturesMarket, FuturesOutcome, Team
from app.services import get_db, OddsAPIService, fetch_current_odds
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
from app.utils.event_taxonomy import compute_event_tags
from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY as _SPORT_PREFIX_TO_LLM_CATEGORY

router = APIRouter()


@router.post("/discover")
@router.get("/discover")
async def discover_all_events(
    categories: Optional[str] = Query(
        None,
        description="Comma-separated category prefixes to discover (e.g., 'rugby,cricket,aussierules'). If not specified, discovers ALL sports."
    ),
    db: AsyncSession = Depends(get_db),
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

    # Subquery: count distinct time buckets (minutes) per event.
    # Raw odds_snapshots contain multiple bookmakers per polling cycle,
    # so counting raw rows inflates the count (10 rows from 2 polls with
    # 5 bookmakers each is only 2 actual data points). Counting distinct
    # minute-level buckets matches Pulse's 60-second aggregation and gives
    # an accurate measure of how much real data we have for the game.
    snapshot_count = (
        select(
            OddsSnapshot.event_id,
            func.count(
                func.distinct(func.date_trunc('minute', OddsSnapshot.captured_at))
            ).label("snap_count"),
        )
        .group_by(OddsSnapshot.event_id)
        .subquery()
    )

    MIN_SNAPSHOTS_FOR_RANKING = 20

    # Base query for completed events with EI and enough data
    base_query = (
        select(Event)
        .options(selectinload(Event.sport))
        .join(snapshot_count, Event.id == snapshot_count.c.event_id)
        .where(
            Event.status.in_(["completed", "closed"]),
            Event.raw_ei.isnot(None),
            snapshot_count.c.snap_count >= MIN_SNAPSHOTS_FOR_RANKING,
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
        team_filter = or_(
            Event.home_team_name.ilike(search_pattern),
            Event.away_team_name.ilike(search_pattern),
        )

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
    # For scheduled: order by commence_time ASC (soonest first)
    # For completed: order by commence_time DESC (most recent first)
    # We handle this by using different sort keys based on status
    query = query.order_by(
        status_order,
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
    total_pages = (total_count + per_page - 1) // per_page

    # Also search futures markets by name or outcome (label) name
    futures_query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.sport))
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            or_(
                FuturesMarket.name.ilike(search_pattern),
                FuturesMarket.outcomes.any(FuturesOutcome.name.ilike(search_pattern)),
            ),
            FuturesMarket.status == "open",
        )
        .order_by(FuturesMarket.updated_at.desc())
        .limit(10)  # Limit futures results
    )

    # Apply sport filter to futures if specified
    if sport:
        futures_query = futures_query.join(Sport, FuturesMarket.sport_id == Sport.id).where(
            Sport.key == sport
        )

    futures_result = await db.execute(futures_query)
    futures_markets = futures_result.scalars().unique().all()

    # Format futures results
    formatted_futures = [
        _format_futures_for_search(market)
        for market in futures_markets
    ]

    return {
        "query": q,
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
    now = datetime.now(timezone.utc)
    pattern = f"%{q}%"
    suggestions = []

    # Multi-word query support: "USA Canada" finds events where
    # one team is "USA" and the other is "Canada"
    terms = q.strip().split()
    if len(terms) > 1:
        event_term_conditions = []
        team_term_conditions = []
        for term in terms:
            tp = f"%{term}%"
            event_term_conditions.append(
                or_(Event.home_team_name.ilike(tp), Event.away_team_name.ilike(tp))
            )
            team_term_conditions.append(
                or_(Team.name.ilike(tp), Team.abbreviation.ilike(tp))
            )
        event_team_filter = and_(*event_term_conditions)
        team_filter = and_(*team_term_conditions)
    else:
        event_team_filter = or_(
            Event.home_team_name.ilike(pattern),
            Event.away_team_name.ilike(pattern),
        )
        team_filter = or_(
            Team.name.ilike(pattern),
            Team.abbreviation.ilike(pattern),
        )

    # 1. Find matching teams (deduplicated by name)
    team_query = (
        select(Team.name, Team.abbreviation, Team.sport_id, Team.logo_url_small)
        .where(team_filter)
        .order_by(Team.name)
        .limit(5)
    )
    team_result = await db.execute(team_query)
    teams_seen = set()
    for row in team_result.all():
        if row.name not in teams_seen:
            teams_seen.add(row.name)
            suggestions.append({
                "type": "team",
                "text": row.name,
                "abbreviation": row.abbreviation,
                "logo": row.logo_url_small,
            })

    # 2. Find upcoming/live events matching the query
    event_query = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .options(selectinload(Event.sport))
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
    for event in event_result.scalars().all():
        suggestions.append({
            "type": "event",
            "text": f"{event.away_team_name} at {event.home_team_name}",
            "event_id": event.id,
            "status": event.status,
            "sport": event.sport.key if event.sport else None,
            "commence_time": event.commence_time.isoformat() if event.commence_time else None,
        })

    # 3. Find matching futures markets
    futures_query = (
        select(FuturesMarket)
        .where(
            FuturesMarket.name.ilike(pattern),
            FuturesMarket.status == "open",
        )
        .order_by(FuturesMarket.market_tier.asc().nulls_last())
        .limit(3)
    )
    futures_result = await db.execute(futures_query)
    for market in futures_result.scalars().all():
        suggestions.append({
            "type": "futures",
            "text": market.name,
            "market_id": market.id,
            "market_tier": market.market_tier,
        })

    return {"suggestions": suggestions[:8], "query": q}


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

    return {"suggestions": suggestions[:8]}


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

    query = query.order_by(Event.commence_time)

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
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.odds_snapshots), selectinload(Event.sport))
        .where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Load GEI percentiles for formatting
    gei_percentiles = await _load_gei_percentiles(db)

    # Build team lookup for colors/logos
    team_lookup = await _build_team_lookup(
        db, [event.home_team_name, event.away_team_name]
    )

    response = _format_event(event, gei_percentiles, team_lookup=team_lookup)

    # Compute tags for this event
    response["event_tags"] = compute_event_tags(
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

    # Compute standings context for event detail
    standings_context = _compute_standings_context(
        team_lookup.get(event.home_team_name),
        team_lookup.get(event.away_team_name),
        event.home_team_name,
        event.away_team_name,
    )
    if standings_context:
        response["standings_context"] = standings_context

    if event.odds_snapshots:
        # Get the most recent snapshot for each bookmaker
        # (deduplication means different bookmakers may have different latest times)
        latest_by_bookmaker = {}
        for s in event.odds_snapshots:
            if s.bookmaker not in latest_by_bookmaker or s.captured_at > latest_by_bookmaker[s.bookmaker].captured_at:
                latest_by_bookmaker[s.bookmaker] = s

        all_latest_snapshots = list(latest_by_bookmaker.values())

        # Filter for aggregation: exclude pre-game-only bookmakers from consensus
        filtered_snapshots = _filter_stale_bookmaker_snapshots(
            all_latest_snapshots,
            event_status=event.status,
            commence_time=event.commence_time,
        )
        latest_time = max(s.captured_at for s in filtered_snapshots)

        # Detect bookmakers with reversed home/away odds
        reversed_bookmakers = detect_reversed_bookmakers(filtered_snapshots)

        # Aggregate across bookmakers (exclude reversed ones)
        agg_snapshots = [s for s in filtered_snapshots if s.bookmaker not in reversed_bookmakers]
        if not agg_snapshots:
            agg_snapshots = filtered_snapshots  # fallback: use all if all were flagged
        aggregated = aggregate_bookmaker_odds(agg_snapshots)

        response["current_odds"] = {
            "captured_at": latest_time.isoformat(),
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

    return response


# ── Scoring play extraction from StatPal play-by-play data ──────────────────

_SCORING_PLAY_TYPES = {
    "touchdown", "field_goal", "safety", "extra_point", "two_point_conversion",
    "goal", "power_play_goal", "shorthanded_goal", "empty_net_goal",
    "three_pointer", "dunk", "layup", "free_throw", "basket", "shot",
    "home_run", "rbi_single", "rbi_double", "rbi_triple", "sacrifice_fly",
    "run", "scoring", "score", "penalty_goal", "own_goal",
}


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
    r"\bvs\.?\s|\s–\s|\bat\b.*:\s*\w",
    re.IGNORECASE,
)


def _escape_like(s: str) -> str:
    """Escape special LIKE/ILIKE characters for safe pattern matching."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _team_name_patterns(full_name: str) -> list[str]:
    """Build ILIKE-safe patterns for matching a team in outcome names.

    Returns escaped patterns suitable for use in ILIKE '%pattern%' queries.
    Includes full team name and short name (last word, if >= 4 chars).
    """
    if not full_name:
        return []

    patterns = []
    escaped_full = _escape_like(full_name.strip())
    patterns.append(escaped_full)

    # Short name: last word (e.g., "Celtics" from "Boston Celtics")
    parts = full_name.strip().split()
    if len(parts) > 1:
        short = parts[-1]
        if len(short) >= 4:
            escaped_short = _escape_like(short)
            if escaped_short.lower() != escaped_full.lower():
                patterns.append(escaped_short)

    return patterns


@router.get("/{event_id}/related-futures")
async def get_related_futures(
    event_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get futures markets related to the teams in this event.

    Uses direct name matching on outcome names within sport-matching markets,
    eliminating dependency on pre-computed team_id links. Sport matching uses
    three strategies (OR): external_id prefix, llm_sport_category, and sport_id.
    """
    from app.utils.team_linking import compute_relevance_score

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
        "total_count": 0,
    }

    # 2. Determine sport family for filtering
    event_sport_key = event.sport.key if event.sport else None
    if not event_sport_key:
        return empty

    sport_prefix = event_sport_key.split("_")[0]  # e.g., "basketball", "americanfootball"
    llm_category = _SPORT_PREFIX_TO_LLM_CATEGORY.get(sport_prefix, sport_prefix)

    # Find compatible sport IDs (for markets that have sport_id populated)
    prefix_result = await db.execute(
        select(Sport.id).where(Sport.key.like(f"{sport_prefix}%"))
    )
    compatible_sport_ids = [row.id for row in prefix_result.all()]

    # 3. Find sport-matching open markets using multiple strategies (OR)
    #    This is the key improvement: instead of requiring sport_id (often NULL),
    #    we also match on external_id prefix (OddsAPI sport key) and
    #    llm_sport_category (works for Kalshi and LLM-categorized markets).
    sport_filters = [
        FuturesMarket.external_id.like(f"{sport_prefix}%"),
        FuturesMarket.llm_sport_category == llm_category,
    ]
    if compatible_sport_ids:
        sport_filters.append(FuturesMarket.sport_id.in_(compatible_sport_ids))

    market_result = await db.execute(
        select(FuturesMarket.id).where(
            FuturesMarket.status == "open",
            or_(*sport_filters),
        )
    )
    sport_market_ids = [row.id for row in market_result.all()]
    if not sport_market_ids:
        return empty

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
            # Add alternate team names (e.g., "Celtics", "BOS")
            alt_names = team_row.alternate_names
            if alt_names and isinstance(alt_names, list):
                for alt in alt_names:
                    if isinstance(alt, str) and len(alt) >= 4:
                        escaped = _escape_like(alt)
                        if escaped.lower() not in [p.lower() for p in patterns]:
                            patterns.append(escaped)
                            team_patterns.append(escaped)
            # Add roster player names from ESPN/MLB API (e.g., "Jayson Tatum")
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
                    if isinstance(player_name, str) and len(player_name) >= 4:
                        escaped = _escape_like(player_name)
                        if escaped.lower() not in [p.lower() for p in patterns]:
                            patterns.append(escaped)

    all_team_ids = home_team_ids | away_team_ids

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

    def _game_market_matches_event(mkt: FuturesMarket) -> bool:
        """Check if a game-specific market belongs to THIS event."""
        # Direct event_id link
        if mkt.event_id is not None:
            return mkt.event_id == event_id
        # Check if market name contains BOTH teams from this event
        name_lower = (mkt.name or "").lower()
        home_short = event.home_team_name.split()[-1].lower() if event.home_team_name else ""
        away_short = event.away_team_name.split()[-1].lower() if event.away_team_name else ""
        if (home_short and len(home_short) >= 4 and home_short in name_lower and
                away_short and len(away_short) >= 4 and away_short in name_lower):
            return True
        # Temporal proximity
        if event_commence_time:
            for dt in (mkt.commence_time, mkt.resolution_date):
                if dt:
                    diff = abs((dt - event_commence_time).total_seconds())
                    if diff <= GAME_TIME_WINDOW.total_seconds():
                        return True
        # No timing info — exclude to be safe
        return False

    for outcome in outcomes:
        if outcome.id in seen_ids:
            continue
        seen_ids.add(outcome.id)

        market = outcome.market

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

        entry = {
            "market_id": market.id,
            "market_name": market.name,
            "market_tier": market.market_tier,
            "category": market.category,
            "source": market.source,
            "outcome_id": outcome.id,
            "outcome_name": outcome.name,
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
        }

        # Add matched player metadata (ESPN headshot) when outcome matches a roster player
        matched = player_metadata.get(outcome.name.lower())
        if matched:
            entry["matched_player"] = matched

        if side == "home":
            home_futures.append(entry)
        else:
            away_futures.append(entry)

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
                # Generate via LLM
                from app.services.llm import generate_related_futures_summary
                summary = generate_related_futures_summary(
                    home_team=event.home_team_name,
                    away_team=event.away_team_name,
                    sport_key=event.sport.key if event.sport else "",
                    event_status=event.status or "scheduled",
                    home_futures=[
                        {
                            "market_name": f["market_name"],
                            "outcome_name": f["outcome_name"],
                            "probability": f["probability"],
                            "probability_change_24h": f.get("probability_change_24h"),
                            "opening_probability": f.get("opening_probability"),
                        }
                        for f in home_futures[:8]
                    ],
                    away_futures=[
                        {
                            "market_name": f["market_name"],
                            "outcome_name": f["outcome_name"],
                            "probability": f["probability"],
                            "probability_change_24h": f.get("probability_change_24h"),
                            "opening_probability": f.get("opening_probability"),
                        }
                        for f in away_futures[:8]
                    ],
                )
                if summary:
                    # Determine TTL
                    is_finished = event.status in ("completed", "closed")
                    if is_finished:
                        expires = None  # Never expires for finished games
                    else:
                        expires = now_ts + timedelta(hours=2)

                    if cached:
                        cached.explanation = summary
                        cached.expires_at = expires
                    else:
                        new_analysis = LineMovementAnalysis(
                            event_id=event_id,
                            analysis_type="related_futures",
                            explanation=summary,
                            expires_at=expires,
                        )
                        db.add(new_analysis)
                    await db.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("Related futures summary error: %s", e)

    # Extract box score player data for the response (if available)
    box_score_players = None
    if event.box_score_data and not event.box_score_data.get("error"):
        box_score_players = event.box_score_data.get("players")

    return {
        "event_id": event_id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "home_team_futures": home_futures,
        "away_team_futures": away_futures,
        "total_count": len(home_futures) + len(away_futures),
        "summary": summary,
        "event_status": event.status,
        "box_score": box_score_players,
    }


@router.get("/{event_id}/history")
async def get_event_odds_history(
    event_id: int,
    hours: int = Query(24, description="Hours of history to return"),
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

    if is_finished:
        # Return all snapshots for finished events
        result = await db.execute(
            select(OddsSnapshot)
            .where(OddsSnapshot.event_id == event_id)
            .order_by(OddsSnapshot.captured_at)
        )
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

    # Extract scoring plays from StatPal play-by-play data
    scoring_plays = extract_scoring_plays(
        (event.win_probability_sources or {}).get("statpal_plays", [])
    )

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

    return {
        "event_id": event_id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "history": history,
        "bookmaker_history": bookmaker_history,
        "score_history": score_history,
        "espn_history": espn_history,
        "win_prob_history": win_prob_history,
        "win_prob_sources": win_prob_sources_meta,
        "scoring_plays": scoring_plays,
        "aggregate_line": aggregate_line if aggregate_line else None,
        "points": len(history),
        "bookmaker_count": len(bookmaker_history),
        "snapshot_count": len(snapshots),
        "espn_snapshot_count": len(espn_history),
    }


@router.get("/{event_id}/line-movement")
async def get_line_movement_analysis(
    event_id: int,
    db: AsyncSession = Depends(get_db),
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

        if event.status == "live":
            game_context = {
                "home_team": event.home_team_name,
                "away_team": event.away_team_name,
                "home_score": event.home_score,
                "away_score": event.away_score,
                "period": event.period,
                "clock": event.game_clock,
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
        has_any_context = bool(injuries_data) or bool(news_headlines) or bool(game_context) or bool(team_stats)
        if has_any_context:
            prompt = build_llm_prompt(
                analysis,
                injuries=injuries_data,
                news_headlines=news_headlines,
                game_context=game_context,
                team_stats=team_stats,
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
        "primary_color": team.primary_color,
        "secondary_color": team.secondary_color,
        "logo_small": team.logo_url_small,
        "logo_large": team.logo_url_large,
        "record": team.current_record,
    }
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
        if event.game_clock:
            espn_data["game_clock"] = event.game_clock
        if event.period:
            espn_data["period"] = event.period
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


def _format_futures_for_search(market: FuturesMarket) -> dict:
    """Format a futures market for search results."""
    # Sort outcomes by probability to get top outcomes
    sorted_outcomes = sorted(
        market.outcomes,
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

    return {
        "id": market.id,
        "name": market.name,
        "sport": market.sport.key if market.sport else None,
        "sport_name": market.sport.name if market.sport else None,
        "category": market.category,
        "llm_sport_category": market.llm_sport_category,
        "status": market.status,
        "source": market.source,
        "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
        "top_outcomes": top_outcomes,
        "outcome_count": len(market.outcomes),
        "updated_at": market.updated_at.isoformat() if market.updated_at else None,
    }
