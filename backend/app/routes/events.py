"""Events API endpoints."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert

from app.models import Event, OddsSnapshot, Sport, ScoreSnapshot, GEIPercentile, FuturesMarket, FuturesOutcome, Team
from app.services import get_db, OddsAPIService, fetch_current_odds
from app.utils import (
    moneyline_to_probability,
    project_scores,
    calculate_gei,
    aggregate_bookmaker_odds,
    compute_highlight,
    get_highlight_label,
    should_highlight,
)
from app.utils.odds_filtering import filter_stale_bookmaker_snapshots as _filter_stale_bookmaker_snapshots

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


async def _load_gei_percentiles(db: AsyncSession) -> dict:
    """Load GEI percentile thresholds from database.

    Returns empty dict if table doesn't exist or query fails,
    allowing the API to function without GEI data.
    """
    try:
        result = await db.execute(
            select(GEIPercentile.scope, GEIPercentile.percentile, GEIPercentile.raw_gei_threshold)
        )
        rows = result.all()

        percentiles = {}
        for scope, percentile, threshold in rows:
            if scope not in percentiles:
                percentiles[scope] = {}
            percentiles[scope][percentile] = float(threshold) if threshold else 0

        return percentiles
    except Exception:
        # Table may not exist yet - return empty dict
        return {}


@router.get("/highlights")
async def get_highlights(
    sport: Optional[str] = Query(None, description="Filter by sport key"),
    days: int = Query(7, description="Days of history to include"),
    limit: int = Query(20, description="Maximum number of events"),
    min_percentile: int = Query(75, description="Minimum GEI percentile"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the most exciting completed events.

    Returns events with highest GEI scores, useful for highlights/replay discovery.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Load GEI percentiles for formatting
    gei_percentiles = await _load_gei_percentiles(db)

    # Build query for completed events with GEI
    query = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.status == "completed",
            Event.raw_gei.isnot(None),
            Event.commence_time >= cutoff,
        )
        .order_by(Event.raw_gei.desc())
        .limit(limit * 2)  # Fetch extra to filter by percentile
    )

    if sport:
        query = query.join(Sport).where(Sport.key == sport)

    result = await db.execute(query)
    events = result.scalars().all()

    # Apply percentile filter
    highlights = []
    for event in events:
        formatted = _format_event(event, gei_percentiles)

        # Check Pulse score threshold
        pulse = formatted.get("pulse", {})
        pulse_score = pulse.get("score", 0)
        if pulse_score >= min_percentile:
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
async def get_pulse_rankings(
    limit: int = Query(25, ge=1, le=100, description="Number of events per list"),
    sport: Optional[str] = Query(None, description="Filter by sport key"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the all-time highest and lowest Pulse events.

    Returns two lists: the most exciting games ever tracked (highest Pulse)
    and the most boring/one-sided games (lowest Pulse).

    Only includes events with sufficient odds data (10+ snapshots) to avoid
    inflated scores from games with sparse data.
    """
    # Load GEI percentiles for formatting
    gei_percentiles = await _load_gei_percentiles(db)

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

    # Base query for completed events with GEI and enough data
    base_query = (
        select(Event)
        .options(selectinload(Event.sport))
        .join(snapshot_count, Event.id == snapshot_count.c.event_id)
        .where(
            Event.status.in_(["completed", "closed"]),
            Event.raw_gei.isnot(None),
            snapshot_count.c.snap_count >= MIN_SNAPSHOTS_FOR_RANKING,
        )
    )

    if sport:
        base_query = base_query.join(Sport).where(Sport.key == sport)

    # Highest Pulse (most exciting)
    highest_query = base_query.order_by(Event.raw_gei.desc()).limit(limit)
    highest_result = await db.execute(highest_query)
    highest_events = highest_result.scalars().all()

    # Lowest Pulse (least exciting) - must have some activity (raw_gei > 0)
    lowest_query = (
        base_query
        .where(Event.raw_gei > 0)
        .order_by(Event.raw_gei.asc())
        .limit(limit)
    )
    lowest_result = await db.execute(lowest_query)
    lowest_events = lowest_result.scalars().all()

    # Format events with rank
    highest_formatted = []
    for i, event in enumerate(highest_events, 1):
        formatted = _format_event(event, gei_percentiles)
        formatted["rank"] = i
        highest_formatted.append(formatted)

    lowest_formatted = []
    for i, event in enumerate(lowest_events, 1):
        formatted = _format_event(event, gei_percentiles)
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
    search_pattern = f"%{q}%"

    # Build base query - search both home and away team names
    query = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .options(selectinload(Event.sport))
        .where(
            or_(
                Event.home_team_name.ilike(search_pattern),
                Event.away_team_name.ilike(search_pattern),
            ),
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
            snaps = _filter_stale_bookmaker_snapshots(
                snaps,
                event_status=(ev.status if ev else "scheduled"),
                commence_time=(ev.commence_time if ev else None),
            )
            latest_time = max(s.captured_at for s in snaps) if snaps else None
            aggregated_odds_map[event_id] = {
                "snapshots": snaps,
                "aggregated": aggregate_bookmaker_odds(snaps),
                "captured_at": latest_time,
            }

    # Load GEI percentiles for formatting
    gei_percentiles = await _load_gei_percentiles(db)

    # Format results and group by sport
    formatted_results = []
    sports_found = {}

    for event in events:
        formatted = _format_event_with_aggregated_odds(
            event, aggregated_odds_map.get(event.id), gei_percentiles
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
async def debug_pulse_status(db: AsyncSession = Depends(get_db)):
    """
    Debug endpoint to check Pulse calculation status.

    Shows how many events have Pulse scores calculated.
    """
    # Count events by Pulse status
    result = await db.execute(
        select(
            Event.status,
            func.count().filter(Event.raw_gei.isnot(None)).label("with_pulse"),
            func.count().filter(Event.raw_gei.is_(None)).label("without_pulse"),
        )
        .group_by(Event.status)
    )
    rows = result.all()

    status_counts = {}
    total_with = 0
    total_without = 0

    for status, with_pulse, without_pulse in rows:
        status_counts[status] = {
            "with_pulse": with_pulse,
            "without_pulse": without_pulse,
        }
        total_with += with_pulse
        total_without += without_pulse

    # Get a sample of events with Pulse to verify it's working
    sample_result = await db.execute(
        select(Event.id, Event.home_team_name, Event.away_team_name, Event.raw_gei, Event.status)
        .where(Event.raw_gei.isnot(None))
        .order_by(Event.raw_gei.desc())
        .limit(5)
    )
    sample_events = [
        {
            "id": row[0],
            "matchup": f"{row[1]} vs {row[2]}",
            "pulse_score": round(float(row[3]) * 100) if row[3] else None,
            "status": row[4],
        }
        for row in sample_result.all()
    ]

    return {
        "total": {
            "with_pulse": total_with,
            "without_pulse": total_without,
        },
        "by_status": status_counts,
        "completion_pct": round(total_with / (total_with + total_without) * 100, 1) if (total_with + total_without) > 0 else 0,
        "sample_events_with_pulse": sample_events,
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
            snaps = _filter_stale_bookmaker_snapshots(
                snaps,
                event_status=(ev.status if ev else "scheduled"),
                commence_time=(ev.commence_time if ev else None),
            )
            latest_time = max(s.captured_at for s in snaps) if snaps else None
            aggregated_odds_map[event_id] = {
                "snapshots": snaps,
                "aggregated": aggregate_bookmaker_odds(snaps),
                "captured_at": latest_time,
            }

    # Load GEI percentiles for formatting
    gei_percentiles = await _load_gei_percentiles(db)

    # Build team lookup for colors/logos (single batch query for all teams)
    all_team_names = []
    for e in events:
        all_team_names.extend([e.home_team_name, e.away_team_name])
    team_lookup = await _build_team_lookup(db, list(set(all_team_names)))

    # Format response with aggregated odds
    return {
        "events": [
            _format_event_with_aggregated_odds(e, aggregated_odds_map.get(e.id), gei_percentiles, team_lookup=team_lookup)
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


@router.get("/{event_id}/props")
async def get_event_props(event_id: int, db: AsyncSession = Depends(get_db)):
    """
    Fetch player prop bets for an event from The Odds API, converted to probabilities.

    Returns props grouped by category (Passing, Rushing, Receiving, Scoring, Kicking)
    with vig-removed implied probabilities for each outcome.
    """
    from app.utils.odds_math import american_to_probability, remove_vig

    # Look up event to get external_id and sport
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if not event.external_id or not event.sport:
        raise HTTPException(
            status_code=400,
            detail="Event missing external ID or sport data"
        )

    sport_key = event.sport.key if event.sport else event.sport_key

    # Map market keys to human-readable names and categories
    PROP_MARKET_INFO = {
        "player_pass_tds": {"name": "Pass TDs", "category": "Passing"},
        "player_pass_yds": {"name": "Pass Yards", "category": "Passing"},
        "player_pass_completions": {"name": "Completions", "category": "Passing"},
        "player_pass_interceptions": {"name": "Interceptions", "category": "Passing"},
        "player_rush_yds": {"name": "Rush Yards", "category": "Rushing"},
        "player_reception_yds": {"name": "Rec Yards", "category": "Receiving"},
        "player_receptions": {"name": "Receptions", "category": "Receiving"},
        "player_anytime_td": {"name": "Anytime TD", "category": "Scoring"},
        "player_first_td": {"name": "First TD", "category": "Scoring"},
        "player_kicking_points": {"name": "Kicker Points", "category": "Kicking"},
    }

    service = OddsAPIService()

    # Try each market individually — The Odds API returns 422 if ANY requested
    # market isn't available, so we fetch one at a time and skip failures.
    all_bookmakers_data = []
    available_markets = []
    errors = []

    try:
        for market_key in PROP_MARKET_INFO.keys():
            try:
                api_data = await service.get_event_odds(
                    sport_key=sport_key,
                    event_id=event.external_id,
                    markets=market_key,
                )
                for bookmaker in api_data.get("bookmakers", []):
                    all_bookmakers_data.append(bookmaker)
                available_markets.append(market_key)
            except Exception:
                errors.append(market_key)
                continue
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to fetch props: {str(e)}"
        )
    finally:
        await service.close()

    if not all_bookmakers_data:
        return {
            "event_id": event_id,
            "home_team": event.home_team_name,
            "away_team": event.away_team_name,
            "categories": [],
            "total_props": 0,
            "available_markets": available_markets,
            "unavailable_markets": errors,
        }

    # Parse and aggregate props across bookmakers
    # Key: (player, market_key, line) -> list of {over_odds, under_odds} or {yes_odds}
    from collections import defaultdict
    prop_aggregator = defaultdict(lambda: {"over_odds": [], "under_odds": [], "yes_odds": [], "no_odds": []})

    TD_MARKETS = ("player_anytime_td", "player_first_td")

    for bookmaker in all_bookmakers_data:
        for market in bookmaker.get("markets", []):
            market_key = market["key"]
            if market_key not in PROP_MARKET_INFO:
                continue

            for outcome in market.get("outcomes", []):
                price = outcome.get("price")
                if price is None:
                    continue

                name = outcome.get("name", "")
                description = outcome.get("description", "")
                line = outcome.get("point")

                if market_key in TD_MARKETS:
                    # For TD markets: name=player, description=player (or empty)
                    # Each outcome is a different player with yes/no implied
                    player = description or name
                    if player in ("Yes", "No"):
                        continue  # Skip generic yes/no, we want player-specific
                    key = (player, market_key, line)
                    prop_aggregator[key]["yes_odds"].append(price)
                else:
                    # Standard over/under prop
                    player = description or name
                    key = (player, market_key, line)
                    if name == "Over":
                        prop_aggregator[key]["over_odds"].append(price)
                    elif name == "Under":
                        prop_aggregator[key]["under_odds"].append(price)

    # Build response grouped by category
    from statistics import median
    categories = defaultdict(list)

    for (player, market_key, line), odds_data in prop_aggregator.items():
        info = PROP_MARKET_INFO[market_key]

        prop_entry = {
            "player": player,
            "type": info["name"],
            "market_key": market_key,
            "line": line,
        }

        if odds_data["over_odds"] and odds_data["under_odds"]:
            # Over/Under prop - aggregate via median
            med_over = int(median(odds_data["over_odds"]))
            med_under = int(median(odds_data["under_odds"]))
            over_prob = american_to_probability(med_over)
            under_prob = american_to_probability(med_under)
            # Remove vig
            over_fair, under_fair = remove_vig(over_prob, under_prob)
            prop_entry["over_probability"] = round(over_fair, 4)
            prop_entry["under_probability"] = round(under_fair, 4)
            prop_entry["over_odds"] = med_over
            prop_entry["under_odds"] = med_under
            prop_entry["bookmaker_count"] = min(len(odds_data["over_odds"]), len(odds_data["under_odds"]))
        elif odds_data["yes_odds"]:
            # Yes/No prop (anytime TD, first TD)
            med_yes = int(median(odds_data["yes_odds"]))
            yes_prob = american_to_probability(med_yes)
            # For TD props, estimate no probability from yes
            yes_fair = min(yes_prob, 0.99)  # Cap to avoid division issues
            prop_entry["probability"] = round(yes_fair, 4)
            prop_entry["american_odds"] = med_yes
            prop_entry["bookmaker_count"] = len(odds_data["yes_odds"])
        else:
            continue

        categories[info["category"]].append(prop_entry)

    # Deduplicate: for over/under props, keep only the most popular line
    # per player+type (the one with the most bookmakers)
    for cat in categories:
        deduped = {}
        for prop in categories[cat]:
            dedup_key = (prop["player"], prop["market_key"])
            existing = deduped.get(dedup_key)
            if existing is None or prop.get("bookmaker_count", 0) > existing.get("bookmaker_count", 0):
                deduped[dedup_key] = prop
        categories[cat] = list(deduped.values())

    # Sort: TD props by probability descending, others by player name
    for cat in categories:
        if cat == "Scoring":
            categories[cat].sort(key=lambda p: -(p.get("probability", 0)))

    # Order categories
    category_order = ["Passing", "Rushing", "Receiving", "Scoring", "Kicking"]
    ordered_categories = []
    for cat in category_order:
        if cat in categories:
            ordered_categories.append({
                "category": cat,
                "props": categories[cat],
            })

    return {
        "event_id": event_id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "categories": ordered_categories,
        "total_props": sum(len(c["props"]) for c in ordered_categories),
        "available_markets": available_markets,
        "unavailable_markets": errors,
    }


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

    if event.odds_snapshots:
        # Get the most recent snapshot for each bookmaker
        # (deduplication means different bookmakers may have different latest times)
        latest_by_bookmaker = {}
        for s in event.odds_snapshots:
            if s.bookmaker not in latest_by_bookmaker or s.captured_at > latest_by_bookmaker[s.bookmaker].captured_at:
                latest_by_bookmaker[s.bookmaker] = s

        latest_snapshots = list(latest_by_bookmaker.values())
        latest_snapshots = _filter_stale_bookmaker_snapshots(
            latest_snapshots,
            event_status=event.status,
            commence_time=event.commence_time,
        )
        latest_time = max(s.captured_at for s in latest_snapshots)

        # Aggregate across bookmakers
        aggregated = aggregate_bookmaker_odds(latest_snapshots)

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

        # Also include individual bookmaker odds for transparency
        # Include captured_at so users can see when each book last updated
        response["bookmaker_odds"] = [
            {
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
            }
            for s in latest_snapshots
        ]

    return response


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

    # Aggregate each time bucket
    history = []
    for timestamp in sorted(snapshots_by_time.keys()):
        snaps = snapshots_by_time[timestamp]
        aggregated = aggregate_bookmaker_odds(snaps)

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
        "points": len(history),
        "bookmaker_count": len(bookmaker_history),
        "snapshot_count": len(snapshots),
        "espn_snapshot_count": len(espn_history),
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


async def _build_team_lookup(db: AsyncSession, team_names: list[str]) -> dict:
    """Build a mapping of team names to Team objects for color/logo data.

    Matches on exact name or alternate_names JSONB array.
    Only returns teams that have ESPN enrichment (color or logo).
    """
    if not team_names:
        return {}

    # Query teams that match by name or alternate names, and have ESPN data
    conditions = [Team.name.in_(team_names)]
    for name in team_names:
        conditions.append(Team.alternate_names.op('?')(name))

    result = await db.execute(
        select(Team).where(
            and_(
                or_(*conditions),
                or_(Team.primary_color.isnot(None), Team.logo_url_small.isnot(None)),
            )
        )
    )
    teams = result.scalars().all()

    # Build lookup: map all known names to team objects
    lookup = {}
    for team in teams:
        lookup[team.name] = team
        if team.alternate_names:
            for alt_name in team.alternate_names:
                lookup[alt_name] = team

    return lookup


def _format_team_data(team: Team) -> dict:
    """Format team data for API response."""
    return {
        "primary_color": team.primary_color,
        "secondary_color": team.secondary_color,
        "logo_small": team.logo_url_small,
        "logo_large": team.logo_url_large,
        "record": team.current_record,
    }


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

    # Add Pulse data if available (for live and completed events)
    # Wrap in try/except in case columns don't exist yet (migration not applied)
    try:
        if event.raw_gei is not None:
            from app.utils.pulse import get_pulse_label, get_pulse_emoji, get_pulse_status
            import json

            raw_gei = float(event.raw_gei)

            # Parse components if stored
            components = None
            if event.gei_components:
                try:
                    components = json.loads(event.gei_components)
                except json.JSONDecodeError:
                    pass

            # Compute percentile score from the stored thresholds.
            # Use sport-specific percentile if available, fall back to global.
            sport_key = event.sport.key if event.sport else None
            percentile_score = None
            if gei_percentiles:
                if sport_key:
                    percentile_score = _calculate_percentile(raw_gei, gei_percentiles, sport_key)
                if percentile_score is None:
                    percentile_score = _calculate_percentile(raw_gei, gei_percentiles, 'global')

            # Use percentile as the display score when available, raw conversion as fallback
            raw_score = max(1, min(100, round(raw_gei * 100)))
            display_score = percentile_score if percentile_score is not None else raw_score

            response["pulse"] = {
                "score": display_score,
                "raw_score": raw_score,
                "status": get_pulse_status(display_score),
                "label": get_pulse_label(display_score),
                "emoji": get_pulse_emoji(display_score),
                "components": components,
            }
    except Exception as e:
        # Pulse columns may not exist yet or other error - log for debugging
        import logging
        logging.warning(f"Error adding Pulse data for event {event.id}: {e}")

    return response


def _calculate_percentile(raw_gei: float, percentiles: dict, scope: str) -> int:
    """Calculate percentile from raw GEI using stored thresholds."""
    if not percentiles or scope not in percentiles:
        return None

    thresholds = percentiles[scope]
    for p in range(100, 0, -1):
        if p in thresholds and raw_gei >= thresholds[p]:
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


def _format_event_with_aggregated_odds(event: Event, odds_data: Optional[dict], gei_percentiles: dict = None, team_lookup: dict = None) -> dict:
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

        # Include individual bookmaker odds for transparency
        if snapshots:
            response["bookmaker_odds"] = [
                {
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
                }
                for s in snapshots
            ]

    # Compute highlight data
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
        "status": market.status,
        "source": market.source,
        "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
        "top_outcomes": top_outcomes,
        "outcome_count": len(market.outcomes),
        "updated_at": market.updated_at.isoformat() if market.updated_at else None,
    }
