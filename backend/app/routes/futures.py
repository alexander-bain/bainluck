"""Futures/Outrights API endpoints."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot, Sport
from app.services import get_db, OddsAPIService
from app.utils import probability_to_american

router = APIRouter()


def _derive_round_boundaries(metadata: dict | None) -> list[dict] | None:
    """Extract round boundary markers from FuturesMarket.market_metadata.round_history.

    Returns a list of {timestamp, label} dicts suitable for chart ReferenceLine markers,
    or None if no round history exists.
    """
    if not metadata:
        return None
    round_history = metadata.get("round_history")
    if not round_history:
        return None
    return [
        {"timestamp": entry["timestamp"], "label": entry.get("label", f"R{entry.get('round', '?')}")}
        for entry in round_history
        if "timestamp" in entry
    ]


# NOTE: Specific routes MUST come before /{market_id} to avoid being matched as IDs


@router.get("/debug/sources")
async def debug_futures_sources(db: AsyncSession = Depends(get_db)):
    """Debug endpoint to see futures counts by source and status."""
    # Count by source and status
    query = select(
        FuturesMarket.source,
        FuturesMarket.status,
        func.count(FuturesMarket.id).label("count")
    ).group_by(FuturesMarket.source, FuturesMarket.status)

    result = await db.execute(query)
    rows = result.all()

    breakdown = {}
    for row in rows:
        source = row.source or "unknown"
        if source not in breakdown:
            breakdown[source] = {"total": 0, "by_status": {}}
        breakdown[source]["by_status"][row.status] = row.count
        breakdown[source]["total"] += row.count

    # Get sample markets from each source
    samples = {}
    for source in breakdown.keys():
        sample_query = (
            select(FuturesMarket.id, FuturesMarket.name, FuturesMarket.status, FuturesMarket.updated_at)
            .where(FuturesMarket.source == source)
            .order_by(FuturesMarket.updated_at.desc())
            .limit(3)
        )
        sample_result = await db.execute(sample_query)
        samples[source] = [
            {"id": r.id, "name": r.name, "status": r.status, "updated_at": r.updated_at.isoformat() if r.updated_at else None}
            for r in sample_result.all()
        ]

    return {
        "breakdown": breakdown,
        "samples": samples,
    }


@router.get("/debug/sport-mapping")
async def debug_sport_mapping(db: AsyncSession = Depends(get_db)):
    """Debug endpoint to see how futures markets are linked to sports."""
    # Get all sports
    sports_result = await db.execute(
        select(Sport.id, Sport.key, Sport.name).order_by(Sport.key)
    )
    sports = [{"id": r.id, "key": r.key, "name": r.name} for r in sports_result.all()]
    sport_map = {s["key"]: s["id"] for s in sports}

    # Get all futures markets with their sport links
    markets_result = await db.execute(
        select(
            FuturesMarket.id,
            FuturesMarket.name,
            FuturesMarket.external_id,
            FuturesMarket.sport_id,
            Sport.key.label("sport_key"),
            Sport.name.label("sport_name"),
        )
        .outerjoin(Sport, FuturesMarket.sport_id == Sport.id)
        .order_by(FuturesMarket.external_id)
    )
    # Import here to avoid circular import issues
    from app.tasks import _infer_base_sport

    markets = []
    for r in markets_result.all():
        # Compute what _infer_base_sport would return
        inferred_key = _infer_base_sport(r.external_id) if r.external_id else None
        markets.append({
            "id": r.id,
            "name": r.name,
            "external_id": r.external_id,
            "sport_id": r.sport_id,
            "linked_sport_key": r.sport_key,
            "linked_sport_name": r.sport_name,
            "inferred_base_sport": inferred_key,
            "inferred_sport_id": sport_map.get(inferred_key) if inferred_key else None,
            "linking_works": r.sport_id is not None and r.sport_id == sport_map.get(inferred_key),
        })

    # Summary: count linked vs unlinked
    linked = sum(1 for m in markets if m["sport_id"])
    unlinked = sum(1 for m in markets if not m["sport_id"])

    return {
        "summary": {
            "total_sports": len(sports),
            "total_futures_markets": len(markets),
            "linked_markets": linked,
            "unlinked_markets": unlinked,
        },
        "sports": sports,
        "markets": markets,
    }


@router.get("/available")
async def get_available_futures():
    """
    Get list of sports with futures markets available from The Odds API.

    Useful for discovering what futures can be tracked.
    """
    try:
        service = OddsAPIService()
        sports = await service.get_sports_with_outrights()
        await service.close()

        return {
            "sports": [
                {
                    "key": s["key"],
                    "group": s.get("group"),
                    "title": s.get("title"),
                    "description": s.get("description"),
                }
                for s in sports
            ],
            "count": len(sports),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching from Odds API: {str(e)}")


@router.get("/movers")
async def get_futures_movers(
    hours: int = Query(24, description="Timeframe for movement calculation"),
    limit: int = Query(20, description="Number of movers to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get outcomes with biggest probability changes.

    Useful for discovering betting line movement and market sentiment shifts.
    """
    # Get outcomes with significant 24h changes
    now = datetime.now(timezone.utc)
    query = (
        select(FuturesOutcome)
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .options(selectinload(FuturesOutcome.market))
        .where(
            FuturesOutcome.probability_change_24h.isnot(None),
            or_(
                FuturesMarket.resolution_date.is_(None),
                FuturesMarket.resolution_date >= now,
            ),
        )
        .order_by(func.abs(FuturesOutcome.probability_change_24h).desc())
        .limit(limit)
    )

    result = await db.execute(query)
    outcomes = result.scalars().all()

    return {
        "movers": [
            {
                "outcome_id": o.id,
                "name": o.name,
                "market_id": o.market_id,
                "market_name": o.market.name if o.market else None,
                "current_probability": float(o.current_probability) if o.current_probability else None,
                "probability_change_24h": float(o.probability_change_24h) if o.probability_change_24h else None,
                "current_american_odds": o.current_american_odds,
                "rank": o.rank,
                "rank_change_24h": o.rank_change_24h,
            }
            for o in outcomes
        ],
        "timeframe_hours": hours,
    }


@router.get("/live/{sport_key}")
async def get_live_futures(
    sport_key: str,
):
    """
    Fetch live futures odds directly from The Odds API.

    Bypasses the database for real-time data. Useful for debugging
    or when you need the absolute latest odds.
    """
    try:
        service = OddsAPIService()
        api_response = await service.get_futures_odds(sport_key)
        markets = service._parse_futures(api_response, sport_key)
        await service.close()

        return {
            "sport_key": sport_key,
            "markets": [
                {
                    "bookmaker": m.bookmaker,
                    "market_name": m.market_name,
                    "outcomes": [
                        {
                            "name": o.name,
                            "american_odds": o.american_odds,
                            "probability": round(o.probability, 4),
                        }
                        for o in sorted(m.outcomes, key=lambda x: x.probability, reverse=True)
                    ],
                }
                for m in markets
            ],
            "bookmaker_count": len(markets),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching from Odds API: {str(e)}")


@router.get("/compare")
async def compare_futures_sources(
    key: str = Query(..., description="Canonical market key (e.g., basketball:NBA:championship:2025-26)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Compare how different sources price the same market.

    Groups all FuturesMarket rows sharing the same canonical_market_key,
    then merges their outcomes by team_id (or name fallback) to show
    side-by-side probabilities from each source.
    """
    # Find all markets with this canonical key
    markets_result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.canonical_market_key == key)
        .order_by(FuturesMarket.source)
    )
    markets = markets_result.scalars().unique().all()

    if not markets:
        raise HTTPException(status_code=404, detail="No markets found for this canonical key")

    sources = sorted(set(m.source for m in markets))

    # Build outcome index: group outcomes across sources by team_id or normalized name
    # Priority: match by team_id first, then fall back to case-insensitive name match
    outcome_groups: dict[str, dict] = {}  # merge_key -> {name, team_id, by_source}

    for market in markets:
        for outcome in market.outcomes:
            merge_key = _outcome_merge_key(outcome)
            if merge_key not in outcome_groups:
                outcome_groups[merge_key] = {
                    "name": outcome.name,
                    "team_id": outcome.team_id,
                    "by_source": {},
                }

            source_data = {
                "probability": float(outcome.current_probability) if outcome.current_probability else None,
                "american_odds": outcome.current_american_odds,
                "rank": outcome.rank,
            }
            # Include bid/ask for prediction markets
            if outcome.current_yes_bid is not None:
                source_data["yes_bid"] = float(outcome.current_yes_bid)
            if outcome.current_yes_ask is not None:
                source_data["yes_ask"] = float(outcome.current_yes_ask)

            outcome_groups[merge_key]["by_source"][market.source] = source_data

            # Prefer the name from the source that has a team_id link
            if outcome.team_id and not outcome_groups[merge_key]["team_id"]:
                outcome_groups[merge_key]["team_id"] = outcome.team_id
                outcome_groups[merge_key]["name"] = outcome.name

    # Sort outcomes by average probability across sources (descending)
    sorted_outcomes = sorted(
        outcome_groups.values(),
        key=lambda o: _avg_probability(o["by_source"]),
        reverse=True,
    )

    return {
        "canonical_key": key,
        "sources": sources,
        "source_markets": [
            {
                "source": m.source,
                "market_id": m.id,
                "name": m.name,
                "outcome_count": len(m.outcomes),
            }
            for m in markets
        ],
        "outcomes": [
            {
                "name": o["name"],
                "team_id": o["team_id"],
                "by_source": o["by_source"],
            }
            for o in sorted_outcomes
        ],
        "outcome_count": len(sorted_outcomes),
    }


@router.get("/canonical-keys")
async def list_canonical_keys(
    sport: Optional[str] = Query(None, description="Filter by sport category"),
    has_multiple_sources: bool = Query(False, description="Only show keys with 2+ sources"),
    limit: int = Query(50, description="Max results"),
    db: AsyncSession = Depends(get_db),
):
    """
    List distinct canonical market keys across all futures markets.

    Useful for discovering which markets have cross-source coverage.
    """
    query = (
        select(
            FuturesMarket.canonical_market_key,
            func.count(FuturesMarket.id).label("market_count"),
            func.count(func.distinct(FuturesMarket.source)).label("source_count"),
            func.array_agg(func.distinct(FuturesMarket.source)).label("sources"),
        )
        .where(FuturesMarket.canonical_market_key.isnot(None))
        .group_by(FuturesMarket.canonical_market_key)
        .order_by(func.count(func.distinct(FuturesMarket.source)).desc())
    )

    if sport:
        query = query.where(FuturesMarket.llm_sport_category == sport)

    if has_multiple_sources:
        query = query.having(func.count(func.distinct(FuturesMarket.source)) > 1)

    query = query.limit(limit)

    result = await db.execute(query)
    rows = result.all()

    return {
        "keys": [
            {
                "canonical_key": row.canonical_market_key,
                "market_count": row.market_count,
                "source_count": row.source_count,
                "sources": sorted(row.sources) if row.sources else [],
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.get("/browse")
async def browse_futures(
    category: Optional[str] = Query(None, description="Filter by llm_sport_category"),
    q: Optional[str] = Query(None, description="Search within market names"),
    limit: int = Query(50, description="Results per page", ge=1, le=200),
    offset: int = Query(0, description="Pagination offset", ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Paginated category browsing for the Search tab.

    Returns markets with their top 3 outcomes, total count, and pagination info.
    Designed for lazy-loading: only fetches data when a user clicks into a category.
    """
    base_filters = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= datetime.now(timezone.utc),
        ),
        ~FuturesMarket.name.ilike('% vs %'),
        ~FuturesMarket.name.ilike('% vs. %'),
    ]

    if category:
        base_filters.append(FuturesMarket.llm_sport_category == category)

    if q:
        base_filters.append(FuturesMarket.name.ilike(f"%{q}%"))

    # Count total
    count_query = select(func.count(FuturesMarket.id)).where(*base_filters)
    total = (await db.execute(count_query)).scalar() or 0

    # Fetch page
    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(*base_filters)
        .order_by(FuturesMarket.resolution_date.asc().nulls_last())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    markets = result.scalars().unique().all()

    items = []
    for market in markets:
        sorted_outcomes = sorted(
            market.outcomes,
            key=lambda o: float(o.current_probability) if o.current_probability else 0,
            reverse=True,
        )
        top3 = [
            {
                "id": o.id,
                "name": o.name,
                "probability": float(o.current_probability) if o.current_probability else None,
                "movement": float(o.probability_change_24h) if o.probability_change_24h else None,
            }
            for o in sorted_outcomes[:3]
        ]
        items.append({
            "id": market.id,
            "name": market.name,
            "llm_sport_category": market.llm_sport_category,
            "source": market.source,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
            "top_outcomes": top3,
            "outcome_count": len(market.outcomes),
        })

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }


@router.get("/categories")
async def list_futures_categories(
    db: AsyncSession = Depends(get_db),
):
    """
    Lightweight category counts for the Search tab category grid.

    Single GROUP BY query, no outcome loading. Returns [{key, count}].
    """
    now = datetime.now(timezone.utc)

    query = (
        select(
            FuturesMarket.llm_sport_category,
            func.count(FuturesMarket.id).label("count"),
        )
        .where(
            FuturesMarket.status == "open",
            FuturesMarket.event_id.is_(None),
            or_(
                FuturesMarket.resolution_date.is_(None),
                FuturesMarket.resolution_date >= now,
            ),
            ~FuturesMarket.name.ilike('% vs %'),
            ~FuturesMarket.name.ilike('% vs. %'),
        )
        .group_by(FuturesMarket.llm_sport_category)
        .order_by(func.count(FuturesMarket.id).desc())
    )

    result = await db.execute(query)
    rows = result.all()

    categories = [
        {
            "key": row.llm_sport_category or "other",
            "count": row.count,
        }
        for row in rows
    ]

    return {
        "categories": categories,
        "total": sum(r["count"] for r in categories),
    }


@router.get("/faceted")
async def faceted_futures_search(
    tags: Optional[str] = Query(None, description="JSON array of tags"),
    sport: Optional[str] = Query(None, description="Sport tag value (e.g., basketball)"),
    category: Optional[str] = Query(None, description="llm_sport_category filter"),
    stakes: Optional[str] = Query(None, description="Stakes tag value"),
    narrative: Optional[str] = Query(None, description="Narrative tag value"),
    audience: Optional[str] = Query(None, description="Audience tag value"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Results per page"),
    db: AsyncSession = Depends(get_db),
):
    """Faceted search over futures markets using GIN-indexed taxonomy tags."""
    import json as _json
    from sqlalchemy import literal_column, text as sql_text
    from app.utils.event_taxonomy import validate_tag

    # Build tag filter from both sources
    tag_filter: list[str] = []
    if tags:
        try:
            parsed = _json.loads(tags)
            if isinstance(parsed, list):
                tag_filter.extend(str(t) for t in parsed)
        except (ValueError, TypeError):
            pass

    convenience = {"sport": sport, "stakes": stakes, "narrative": narrative, "audience": audience}
    for ns, val in convenience.items():
        if val:
            tag_filter.append(f"{ns}:{val}")

    # Base conditions — open, non-game-level, unresolved
    now = datetime.now(timezone.utc)
    conditions = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= now,
        ),
    ]

    if category:
        conditions.append(FuturesMarket.llm_sport_category == category)

    # GIN containment filter
    valid_tags: list[str] = []
    if tag_filter:
        valid_tags = [t for t in tag_filter if validate_tag(t)]
        if valid_tags:
            escaped = _json.dumps(valid_tags).replace("'", "''")
            conditions.append(
                FuturesMarket.market_tags.op("@>")(
                    literal_column(f"'{escaped}'::jsonb")
                )
            )

    # Count
    count_q = select(func.count(FuturesMarket.id)).where(*conditions)
    total_count = (await db.execute(count_q)).scalar() or 0

    # Data
    offset_val = (page - 1) * per_page
    data_q = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(*conditions)
        .order_by(FuturesMarket.resolution_date.asc().nulls_last())
        .offset(offset_val)
        .limit(per_page)
    )
    markets = (await db.execute(data_q)).scalars().unique().all()

    formatted = []
    for market in markets:
        sorted_outcomes = sorted(
            market.outcomes,
            key=lambda o: float(o.current_probability) if o.current_probability else 0,
            reverse=True,
        )
        top3 = [
            {
                "id": o.id,
                "name": o.name,
                "probability": float(o.current_probability) if o.current_probability else None,
                "movement": float(o.probability_change_24h) if o.probability_change_24h else None,
            }
            for o in sorted_outcomes[:3]
        ]
        formatted.append({
            "id": market.id,
            "name": market.name,
            "llm_sport_category": market.llm_sport_category,
            "source": market.source,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
            "market_tags": market.market_tags or [],
            "top_outcomes": top3,
            "outcome_count": len(market.outcomes),
        })

    # Facet counts
    facet_sql = """
        SELECT split_part(tag, ':', 1) AS ns, tag, COUNT(*) AS cnt
        FROM futures_markets, jsonb_array_elements_text(market_tags) AS tag
        WHERE status = 'open' AND event_id IS NULL
          AND (resolution_date IS NULL OR resolution_date >= :now)
    """
    facet_params: dict = {"now": now}
    if category:
        facet_sql += " AND llm_sport_category = :category"
        facet_params["category"] = category
    if valid_tags:
        escaped_facet = _json.dumps(valid_tags).replace("'", "''")
        facet_sql += f" AND market_tags @> '{escaped_facet}'::jsonb"
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
        "markets": formatted,
        "facets": facets,
    }


@router.get("")
async def list_futures_markets(
    sport: Optional[str] = Query(None, description="Filter by sport key"),
    status: str = Query("open", description="Filter by status (open, resolved, all)"),
    source: Optional[str] = Query(None, description="Filter by source (odds_api, kalshi)"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all futures markets.

    Returns markets with their top outcomes sorted by probability.
    """
    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.sport))
        .options(selectinload(FuturesMarket.outcomes))
    )

    # Apply filters
    conditions = []
    if status != "all":
        conditions.append(FuturesMarket.status == status)
        # Exclude resolved markets (past resolution_date) from non-"all" queries
        now = datetime.now(timezone.utc)
        conditions.append(
            or_(
                FuturesMarket.resolution_date.is_(None),
                FuturesMarket.resolution_date >= now,
            )
        )

    if source:
        conditions.append(FuturesMarket.source == source)

    if sport:
        # Join to Sport table to filter by sport key
        query = query.join(Sport, FuturesMarket.sport_id == Sport.id)
        conditions.append(Sport.key.ilike(f"%{sport}%"))

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(FuturesMarket.updated_at.desc())

    result = await db.execute(query)
    markets = result.scalars().unique().all()

    # Build canonical key → source count map for cross-source badges
    canonical_keys = [m.canonical_market_key for m in markets if m.canonical_market_key]
    source_count_map = {}
    if canonical_keys:
        source_query = (
            select(
                FuturesMarket.canonical_market_key,
                func.count(func.distinct(FuturesMarket.source)).label("source_count"),
                func.array_agg(func.distinct(FuturesMarket.source)).label("sources"),
            )
            .where(FuturesMarket.canonical_market_key.in_(canonical_keys))
            .group_by(FuturesMarket.canonical_market_key)
        )
        source_result = await db.execute(source_query)
        for row in source_result.all():
            source_count_map[row.canonical_market_key] = {
                "count": row.source_count,
                "sources": sorted(row.sources) if row.sources else [],
            }

    return {
        "markets": [
            _format_market_summary(market, source_count_map)
            for market in markets
        ],
        "count": len(markets),
    }


@router.get("/{market_id}")
async def get_futures_market(
    market_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed information about a specific futures market.

    Returns all outcomes with current and opening odds.
    """
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.sport))
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.id == market_id)
    )
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    # Get distinct bookmakers that have contributed odds for this market
    outcome_ids = [o.id for o in market.outcomes]
    bookmakers = []
    if outcome_ids:
        bookmakers_result = await db.execute(
            select(FuturesOddsSnapshot.bookmaker)
            .where(FuturesOddsSnapshot.outcome_id.in_(outcome_ids))
            .distinct()
            .order_by(FuturesOddsSnapshot.bookmaker)
        )
        bookmakers = [row[0] for row in bookmakers_result.all()]

    return _format_market_detail(market, bookmakers)


@router.get("/{market_id}/related-events")
async def get_related_events(
    market_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get upcoming and live events related to a futures market.

    Finds events where home or away team has a linked outcome in this market.
    Returns events sorted: live first, then upcoming by commence_time.
    """
    from app.models import Event, Team

    # Load market with outcomes (need team_ids)
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.id == market_id)
    )
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    # Get all team_ids from linked outcomes
    team_ids = [o.team_id for o in market.outcomes if o.team_id is not None]
    if not team_ids:
        return {
            "market_id": market_id,
            "market_name": market.name,
            "events": [],
        }

    # Build team_id → outcome mapping for context
    team_outcome_map = {}
    for o in market.outcomes:
        if o.team_id:
            team_outcome_map[o.team_id] = {
                "outcome_name": o.name,
                "probability": float(o.current_probability) if o.current_probability else None,
                "american_odds": o.current_american_odds,
                "rank": o.rank,
            }

    # Find events where either team is linked
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=1)  # Include recently completed games
    week_ahead = now + timedelta(days=7)

    events_result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            or_(
                Event.home_team_id.in_(team_ids),
                Event.away_team_id.in_(team_ids),
            ),
            Event.commence_time.between(week_ago, week_ahead),
        )
        .order_by(
            # Live first, then upcoming, then completed
            case(
                (Event.status == "live", 0),
                (Event.status == "scheduled", 1),
                else_=2,
            ),
            Event.commence_time.asc(),
        )
        .limit(20)
    )
    events = events_result.scalars().all()

    formatted_events = []
    for event in events:
        # Determine which team in this event is linked to the market
        linked_teams = []
        for team_id in [event.home_team_id, event.away_team_id]:
            if team_id in team_outcome_map:
                side = "home" if team_id == event.home_team_id else "away"
                linked_teams.append({
                    "side": side,
                    "team_name": event.home_team_name if side == "home" else event.away_team_name,
                    **team_outcome_map[team_id],
                })

        formatted_events.append({
            "event_id": event.id,
            "home_team": event.home_team_name,
            "away_team": event.away_team_name,
            "commence_time": event.commence_time.isoformat(),
            "status": event.status,
            "sport": event.sport.key if event.sport else None,
            "home_score": event.home_score,
            "away_score": event.away_score,
            "linked_teams": linked_teams,
        })

    return {
        "market_id": market_id,
        "market_name": market.name,
        "events": formatted_events,
        "total_count": len(formatted_events),
    }


@router.get("/{market_id}/history")
async def get_futures_history(
    market_id: int,
    outcome_id: Optional[int] = Query(None, description="Filter to specific outcome"),
    hours: int = Query(168, description="Hours of history (default 7 days)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get historical odds movement for a futures market.

    Returns time-series data for charting probability changes.
    """
    # Verify market exists
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.id == market_id)
    )
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Get outcome IDs to fetch history for
    if outcome_id:
        outcome_ids = [outcome_id]
    else:
        # Default to top 10 outcomes by current probability
        sorted_outcomes = sorted(
            market.outcomes,
            key=lambda o: o.current_probability or 0,
            reverse=True
        )[:10]
        outcome_ids = [o.id for o in sorted_outcomes]

    # Fetch snapshots for these outcomes
    snapshot_query = (
        select(FuturesOddsSnapshot)
        .where(
            FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
        )
        .order_by(FuturesOddsSnapshot.captured_at)
    )

    result = await db.execute(snapshot_query)
    snapshots = result.scalars().all()

    # Group snapshots by outcome, then aggregate per-bookmaker snapshots
    # at the same timestamp into a single consensus value.
    # This prevents chart jaggedness caused by plotting each bookmaker's
    # slightly different probability as a separate data point.
    outcome_names = {o.id: o.name for o in market.outcomes}

    # Group: outcome_id -> captured_at -> [probabilities from different bookmakers]
    outcome_time_groups: dict[int, dict[datetime, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for snapshot in snapshots:
        if snapshot.probability is not None:
            outcome_time_groups[snapshot.outcome_id][snapshot.captured_at].append(
                float(snapshot.probability)
            )

    # Build aggregated history: one data point per timestamp per outcome
    outcome_history = {}
    for oid, time_groups in outcome_time_groups.items():
        history = []
        for captured_at in sorted(time_groups.keys()):
            probs = time_groups[captured_at]
            avg_prob = mean(probs)
            history.append({
                "timestamp": captured_at.isoformat(),
                "probability": avg_prob,
                "american_odds": probability_to_american(avg_prob) if avg_prob > 0 else None,
                "bookmaker": "consensus",
            })
        outcome_history[oid] = {
            "outcome_id": oid,
            "name": outcome_names.get(oid, "Unknown"),
            "history": history,
        }

    return {
        "market_id": market_id,
        "market_name": market.name,
        "hours": hours,
        "outcomes": list(outcome_history.values()),
        "round_boundaries": _derive_round_boundaries(market.market_metadata),
        "leaderboard": (market.market_metadata or {}).get("leaderboard"),
    }


def _format_market_summary(market: FuturesMarket, source_count_map: dict = None) -> dict:
    """Format a market for list view with top outcomes."""
    # Sort outcomes by probability
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

    # Cross-source info from canonical key
    source_info = None
    if source_count_map and market.canonical_market_key:
        source_info = source_count_map.get(market.canonical_market_key)

    result = {
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
        "category_tags": market.category_tags or [],
        "updated_at": market.updated_at.isoformat() if market.updated_at else None,
    }

    # Add source count if multiple sources track this market
    if source_info and source_info["count"] > 1:
        result["source_count"] = source_info["count"]
        result["sources"] = source_info["sources"]
    else:
        result["source_count"] = 1

    return result


def _format_market_detail(market: FuturesMarket, bookmakers: list[str] = None) -> dict:
    """Format a market for detail view with all outcomes."""
    sorted_outcomes = sorted(
        market.outcomes,
        key=lambda o: o.current_probability or 0,
        reverse=True
    )

    outcomes = [
        {
            "id": o.id,
            "name": o.name,
            "probability": float(o.current_probability) if o.current_probability else None,
            "american_odds": o.current_american_odds,
            "rank": o.rank,
            "rank_change_24h": o.rank_change_24h,
            "probability_change_24h": float(o.probability_change_24h) if o.probability_change_24h else None,
            "opening_probability": float(o.opening_probability) if o.opening_probability else None,
            "opening_american_odds": o.opening_american_odds,
            "is_winner": o.is_winner,
            "last_updated": o.last_updated.isoformat() if o.last_updated else None,
        }
        for o in sorted_outcomes
    ]

    return {
        "id": market.id,
        "name": market.name,
        "description": market.description,
        "sport": market.sport.key if market.sport else None,
        "sport_name": market.sport.name if market.sport else None,
        "category": market.category,
        "llm_sport_category": market.llm_sport_category,
        "status": market.status,
        "source": market.source,
        "external_id": market.external_id,
        "mutually_exclusive": market.mutually_exclusive,
        "commence_time": market.commence_time.isoformat() if hasattr(market, 'commence_time') and market.commence_time else None,
        "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
        "outcomes": outcomes,
        "outcome_count": len(outcomes),
        "bookmakers": bookmakers or [],
        "category_tags": market.category_tags or [],
        "created_at": market.created_at.isoformat() if market.created_at else None,
        "updated_at": market.updated_at.isoformat() if market.updated_at else None,
    }


def _outcome_merge_key(outcome: FuturesOutcome) -> str:
    """
    Generate a merge key for cross-source outcome matching.

    Priority: team_id (most reliable) > normalized name (fallback).
    """
    if outcome.team_id:
        return f"team:{outcome.team_id}"
    # Normalize name for matching: lowercase, strip whitespace
    return f"name:{outcome.name.lower().strip()}"


def _avg_probability(by_source: dict) -> float:
    """Average probability across all sources for sorting."""
    probs = [
        v["probability"]
        for v in by_source.values()
        if v.get("probability") is not None
    ]
    return sum(probs) / len(probs) if probs else 0.0
