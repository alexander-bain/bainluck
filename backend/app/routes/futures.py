"""Futures/Outrights API endpoints."""

import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, median
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot, Sport, Team
from app.services import get_db, OddsAPIService
from app.utils import probability_to_american
from app.utils.tournament_stages import (
    get_stages_for_sport,
    classify_market_stage,
    get_datagolf_prefix,
    extract_tournament_name,
    tournament_names_match,
    is_game_level_market,
)

router = APIRouter()


# Kalshi ticker suffix extraction for sibling market discovery.
# Kalshi golf tickers: KX{TYPE}-{SUFFIX} where SUFFIX = tournament abbreviation + year
# e.g., KXPGATOP10-ARPIPBM26 → suffix "ARPIPBM26"
_KALSHI_TICKER_RE = re.compile(r"^[A-Z0-9]+-([A-Z0-9]{4,})$", re.IGNORECASE)

# Non-decomposable letters that NFD normalization can't handle.
# Must be transliterated before NFD strip — used in _progression_merge_key().
_MERGE_KEY_TRANSLITERATIONS = str.maketrans({
    "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L",
    "æ": "ae", "Æ": "AE",
})


def _extract_kalshi_suffix(external_id: str) -> Optional[str]:
    """Extract the tournament suffix from a Kalshi external_id.

    Returns None if the external_id doesn't match Kalshi ticker format.
    """
    if not external_id:
        return None
    m = _KALSHI_TICKER_RE.match(external_id)
    return m.group(1) if m else None


def _detect_elimination(history, threshold=0.005):
    """Detect if a participant has been eliminated from a tournament."""
    if len(history) < 3:
        return {"eliminated": False, "eliminated_at": None}
    tail = history[-3:]
    if all((p.get("probability") or 0) <= threshold for p in tail):
        for i, point in enumerate(history):
            if (point.get("probability") or 0) <= threshold:
                remaining = history[i:]
                if all((p.get("probability") or 0) <= threshold for p in remaining):
                    return {"eliminated": True, "eliminated_at": point["timestamp"]}
        return {"eliminated": True, "eliminated_at": tail[0]["timestamp"]}
    return {"eliminated": False, "eliminated_at": None}


def _apply_settled_winner_freeze(market, outcome_history, outcome_names, outcome_id_filter=None):
    """Settled-means-settled evolution freeze (#1177, Queue #230).

    When a market has a graded champion — exactly one outcome with
    ``is_winner=True`` — the champion's path-to-resolution line MUST end at 1.0
    at settlement time, regardless of which source's snapshots we happened to
    chart. odds_api can fizzle to a longshot value on a settled field (Spain
    0.587 on the World Cup, Ryan Fox on the Open) while Kalshi resolves to ~1.0;
    #225 Item 3 already forces the winner's OUTCOME into the chart, but its LINE
    still ends wherever the charted source left it. This resolves the ending.

    Source-independent by design: it keys on the graded ``is_winner`` flag, NOT
    on the winner market's ``status`` (Kalshi settled winner markets stay
    ``status='open'`` — gotcha #33 — so status is unreliable) and NOT on which
    source is snapshot-richest. That means it also fires while the winner market
    is stuck open (the THOC26 class), as soon as the grade lands.

    Read-side only (gotcha #21): appends/synthesizes a terminal CHART point;
    never writes snapshots or ``is_winner``. The terminal point carries
    settlement-time semantics (gotcha #22 spirit — the completed journey ends at
    the finish, not fabricated mid-event movement): its timestamp is the
    settlement time (``resolution_date`` clamped to now, since Kalshi
    ``resolution_date`` can be a future close-time artifact — gotcha #14), and is
    never placed before the last real data point. Non-champion lines are left to
    terminate at their own last real value.
    """
    winners = [o for o in (market.outcomes or []) if getattr(o, "is_winner", False)]
    if len(winners) != 1:
        return  # freeze only a single, unambiguous champion (co-winners: leave as-is)
    champ = winners[0]
    # When the caller filtered to a single non-champion outcome, do not inject the
    # champion's line into a view that didn't ask for it.
    if outcome_id_filter is not None and outcome_id_filter != champ.id:
        return

    now = datetime.now(timezone.utc)
    settle_ts = now
    rd = getattr(market, "resolution_date", None)
    if rd is not None:
        if rd.tzinfo is None:
            rd = rd.replace(tzinfo=timezone.utc)
        settle_ts = min(rd, now)  # clamp future Kalshi close-times to now (gotcha #14)

    entry = outcome_history.get(champ.id)
    if entry and entry.get("history"):
        last = entry["history"][-1]
        last_ts = None
        try:
            last_ts = datetime.fromisoformat(str(last.get("timestamp")))
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
        except Exception:
            last_ts = None
        last_prob = last.get("probability")
        # Already resolved (the charted source converged to ~1.0) — the line
        # already ends at the win; nothing to add, just clear any spurious
        # elimination flag a fizzle-then-recover pattern may have set.
        if last_prob is not None and last_prob >= 0.999:
            entry["eliminated"] = False
            entry["eliminated_at"] = None
            return
        term_ts = settle_ts
        if last_ts is not None and term_ts <= last_ts:
            term_ts = last_ts + timedelta(seconds=1)
        entry["history"].append(
            {
                "timestamp": term_ts.isoformat(),
                "probability": 1.0,
                "american_odds": None,
                "bookmaker": "settlement",
            }
        )
        entry["eliminated"] = False
        entry["eliminated_at"] = None
    else:
        # Champion carried no charted snapshots at all — synthesize a minimal
        # terminal resolve point so the winner line exists and resolves.
        outcome_history[champ.id] = {
            "outcome_id": champ.id,
            "name": outcome_names.get(champ.id, getattr(champ, "name", None) or "Unknown"),
            "history": [
                {
                    "timestamp": settle_ts.isoformat(),
                    "probability": 1.0,
                    "american_odds": None,
                    "bookmaker": "settlement",
                }
            ],
            "eliminated": False,
            "eliminated_at": None,
        }


def _detect_round_boundaries_from_eliminations(outcome_histories, existing_boundaries):
    """Detect round boundaries from simultaneous elimination patterns."""
    if existing_boundaries:
        return existing_boundaries
    elimination_times = []
    for info in outcome_histories.values():
        elim = info.get("eliminated_at")
        if elim:
            try:
                ts = datetime.fromisoformat(elim.replace("Z", "+00:00")).timestamp()
                elimination_times.append(ts)
            except (ValueError, AttributeError):
                continue
    if len(elimination_times) < 2:
        return None
    elimination_times.sort()
    clusters = []
    current_cluster = [elimination_times[0]]
    for ts_val in elimination_times[1:]:
        if ts_val - current_cluster[-1] < 24 * 3600:
            current_cluster.append(ts_val)
        else:
            clusters.append(current_cluster)
            current_cluster = [ts_val]
    clusters.append(current_cluster)
    boundaries = []
    for i, cluster in enumerate(clusters):
        if len(cluster) >= 2:
            avg_ts = sum(cluster) / len(cluster)
            boundaries.append({
                "timestamp": datetime.fromtimestamp(avg_ts, tz=timezone.utc).isoformat(),
                "label": "Round " + str(i + 1),
            })
    return boundaries if boundaries else None

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
    import json as _json
    from app.tasks.redis_state import get_redis_client

    cache_key = f"bainluck:movers:{hours}:{limit}"
    try:
        redis = get_redis_client()
        cached = redis.get(cache_key)
        if cached:
            return _json.loads(cached)
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    query = (
        select(FuturesOutcome)
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .options(joinedload(FuturesOutcome.market))
        .where(
            FuturesOutcome.probability_change_24h.isnot(None),
            FuturesMarket.status.in_(["open", "active"]),
        )
        .order_by(func.abs(FuturesOutcome.probability_change_24h).desc())
        .limit(limit)
    )

    result = await db.execute(query)
    outcomes = result.unique().scalars().all()

    response = {
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
            if not _GARBAGE_OUTCOME_RE.match(o.name or "")
        ],
        "timeframe_hours": hours,
    }

    try:
        redis.setex(cache_key, 60, _json.dumps(response, default=str))
    except Exception:
        pass

    return response


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
            if _GARBAGE_OUTCOME_RE.match(outcome.name or ""):
                continue
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
        real_outcomes = [
            o for o in market.outcomes
            if not _GARBAGE_OUTCOME_RE.match(o.name or "")
        ]
        sorted_outcomes = sorted(
            real_outcomes,
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
            "outcome_count": len(real_outcomes),
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
    q: Optional[str] = Query(None, description="Search within market names"),
    sort: Optional[str] = Query(None, description="Sort order: soonest (default), newest, trending"),
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

    if q:
        conditions.append(FuturesMarket.name.ilike(f"%{q}%"))

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

    # Sort order
    if sort == "trending":
        # Order by max absolute 24h movement across outcomes (desc)
        trending_sub = (
            select(
                FuturesOutcome.market_id,
                func.max(func.abs(FuturesOutcome.probability_change_24h)).label("max_move"),
            )
            .group_by(FuturesOutcome.market_id)
            .subquery()
        )
        data_q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .outerjoin(trending_sub, FuturesMarket.id == trending_sub.c.market_id)
            .where(*conditions)
            .order_by(trending_sub.c.max_move.desc().nulls_last())
            .offset(offset_val)
            .limit(per_page)
        )
    elif sort == "newest":
        data_q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(*conditions)
            .order_by(FuturesMarket.updated_at.desc().nulls_last())
            .offset(offset_val)
            .limit(per_page)
        )
    else:
        # Default: soonest resolution date
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
        real_outcomes = [
            o for o in market.outcomes
            if not _GARBAGE_OUTCOME_RE.match(o.name or "")
        ]
        sorted_outcomes = sorted(
            real_outcomes,
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
            "outcome_count": len(real_outcomes),
            "image_url": market.image_url,
            "hook_description": market.hook_description,
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

    query = query.order_by(FuturesMarket.updated_at.desc()).limit(500)

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


# =============================================================================
# Playoff / tournament progression grid (league-wide)
# IMPORTANT: This route MUST appear before /{market_id} to avoid being
# swallowed by the dynamic path parameter.
# =============================================================================


@router.get("/playoff-grid")
async def get_playoff_grid(
    sport: str = Query(..., description="Sport category (basketball, football, hockey, baseball, golf, soccer, tennis)"),
    league: str = Query("", description="League filter (NBA, NFL, NHL, MLB, NCAAB, NCAAF, etc.). Optional."),
    season: str = Query("", description="Season filter (2025-26, 2025). Auto-detected if omitted."),
    top_n: int = Query(40, ge=1, le=64, description="Max teams/participants to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    League-wide playoff progression grid.

    Returns all teams in a league with their probability of making each
    playoff round, merged across sources (Kalshi, Polymarket, Odds API).

    For NCAA basketball, returns March Madness rounds (Round of 32 through Champion).
    For pro leagues, returns Make Playoffs through Championship.

    Example: /api/futures/playoff-grid?sport=basketball&league=NBA
    → columns: Make Playoffs, Conference, Championship
    → rows: all 30 NBA teams with probabilities at each stage
    """
    sport_lower = sport.lower().strip()
    league_upper = league.upper().strip() if league else None

    stages = get_stages_for_sport(sport_lower, league_upper)
    if not stages:
        return {
            "sport": sport_lower,
            "league": league_upper,
            "season": None,
            "stages": [],
            "teams": [],
            "sources": [],
        }

    # --- Find progression markets ---
    # Strategy 1: canonical_market_key pattern matching
    # Keys look like "basketball:NBA:championship:2025-26"
    # We want all keys matching "basketball:NBA:*:*" (or with season filter)

    # Map canonical key market_type → stage key
    # The canonical key "market_type" uses slightly different names than
    # tournament_stages keys (e.g., "conference_winner" vs "conference")
    _CANONICAL_TO_STAGE = {
        "championship": "championship",
        "conference_winner": "conference",
        "division_winner": "division",
        "make_playoffs": "make_playoffs",
        "pennant": "pennant",
        # Golf
        "win": "win",
        "top_5": "top_5",
        "top_10": "top_10",
        "top_20": "top_20",
        "make_cut": "make_cut",
        # Soccer / tennis
        "group_stage": "group_stage",
        "make_final": "make_final",
        # March Madness / NCAA tournament
        "round_of_32": "round_of_32",
        "sweet_16": "sweet_16",
        "elite_eight": "elite_eight",
        "final_four": "final_four",
        "title_game": "title_game",
        # CFP
        "quarterfinal": "quarterfinal",
        "semifinal": "semifinal",
    }

    # Build canonical key patterns that ONLY match valid stage types.
    # Without this filter, "basketball:NBA:%" would also match win_totals,
    # mvp, dpoy, roy, game_prop, etc. — all of which are NOT playoff stages.
    ck_prefix = sport_lower
    if league_upper:
        ck_prefix += f":{league_upper}"
    else:
        ck_prefix += ":"

    # Build OR of specific canonical key patterns for each valid stage type
    valid_ck_types = list(_CANONICAL_TO_STAGE.keys())
    ck_conditions = []
    for ck_type in valid_ck_types:
        pattern = f"{ck_prefix}:{ck_type}:%"
        if season:
            pattern = f"{ck_prefix}:{ck_type}:{season.strip()}"
        ck_conditions.append(FuturesMarket.canonical_market_key.ilike(pattern))

    # NOTE: We intentionally do NOT fall back to leagueless keys
    # (e.g., "basketball::championship:2026") when a league is specified.
    # Those keys are a dumping ground for misclassified markets
    # (NASCAR drivers, hockey teams, misc props all under "basketball::").

    ck_markets: list = []
    if ck_conditions:
        result = await db.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                or_(*ck_conditions),
                FuturesMarket.status == "open",
            )
        )
        ck_markets = list(result.scalars().unique().all())

    # Strategy 2: Also find markets by sport category + name-based stage detection
    # (catches Odds API markets that may have no/wrong canonical key)
    name_filters = [
        FuturesMarket.llm_sport_category == sport_lower,
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),  # Not game-level
    ]
    if league_upper:
        name_filters.append(
            or_(
                FuturesMarket.canonical_market_key.ilike(f"%:{league_upper}:%"),
                # Also check market name for league references
                FuturesMarket.name.ilike(f"%{league_upper}%"),
            )
        )
    result2 = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(*name_filters)
        .limit(500)
    )
    name_markets = list(result2.scalars().unique().all())

    # Merge and dedup
    seen_ids: set[int] = set()
    all_markets: list[FuturesMarket] = []
    for m in ck_markets + name_markets:
        if m.id not in seen_ids:
            seen_ids.add(m.id)
            all_markets.append(m)

    # Filter out game-level markets
    all_markets = [m for m in all_markets if not is_game_level_market(m.name)]

    # Filter out markets that are NOT playoff progression (draft, awards, stat leaders, etc.)
    _NOT_PROGRESSION_RE = re.compile(
        r"""
        \bdraft\b                 |   # "2026 NBA Draft: 1st Overall pick"
        \b\d+(?:st|nd|rd|th)\s+overall\b |  # "1st Overall pick"
        per\s+game\s+leader       |   # "NBA Assists Per Game Leader"
        scoring\s+leader          |   # "NBA Scoring Leader"
        \bbest\s+record\b         |   # "NBA Best Record"
        \bworst\s+record\b        |   # "NBA Worst Record"
        \b(?:\#?\d+)\s*seed\b     |   # "Western Conference #1 Seed"
        \bseeding\b               |   # "NBA Seeding"
        \bwin\s+total\b           |   # "Win Total"
        \bwins?\s+totals?\b       |   # "Wins Total" / "Win Totals"
        \bover.under\s+wins\b     |   # "Over/Under Wins"
        \bmvp\b                   |   # "NBA MVP"
        \bdpoy\b                  |   # "NBA DPOY"
        \broy\b                   |   # "NBA ROY"
        \brookie\s+of\s+the\s+year\b |
        \bdefensive\s+player\b    |
        \bcoach\s+of\s+the\s+year\b |
        \bmost\s+improved\b       |
        \ball[- ]?star\b          |
        \btotal\s+(?:points|rebounds|assists|wins)\b |
        \b6th\s+man\b             |
        \bexecutive\b             |
        \bretire\b                |   # "Will LeBron James retire before..."
        \bcover\s+of\b            |   # "Who will be on the cover of NBA 2K27?"
        \b2k\d+\b                 |   # "NBA 2K27"
        \badd\s+a\s+new\s+team\b  |   # "Will the NBA add a new team before 2030?"
        \bcba\b                   |   # "New WNBA CBA agreement by...?"
        \bplay[- ]?in\b           |   # "play-in tournament" — not a standard stage
        \bbefore\s+the\s+\d{4}\b  |   # "Canadian team wins X before the 2031 season?"
        \bcanadian\s+team\b           # "Canadian team wins the Stanley Cup"
        """,
        re.IGNORECASE | re.VERBOSE,
    )
    all_markets = [
        m for m in all_markets
        if not _NOT_PROGRESSION_RE.search(m.name)
    ]

    # --- Classify each market into a stage ---
    # Group by stage, allowing multiple markets per stage (from different sources)
    stage_market_groups: dict[str, list[FuturesMarket]] = defaultdict(list)
    detected_season: str | None = season.strip() if season else None

    for m in all_markets:
        # Extract season from canonical key if available
        if not detected_season and m.canonical_market_key:
            parts = m.canonical_market_key.split(":")
            if len(parts) >= 4 and parts[3]:
                detected_season = parts[3]

        # ALWAYS use name-based classification — canonical keys are unreliable
        # (Polymarket assigns "championship" key to draft, awards, stat leaders, etc.)
        stage_key = classify_market_stage(
            m.name, m.external_id, m.market_tier, stages
        )

        # Only include stages that are part of this sport's progression
        if stage_key and any(s["key"] == stage_key for s in stages):
            stage_market_groups[stage_key].append(m)

    if not stage_market_groups:
        return {
            "sport": sport_lower,
            "league": league_upper,
            "season": detected_season,
            "stages": [],
            "teams": [],
            "sources": [],
        }

    # --- Merge outcomes across sources within each stage ---
    # participant merge_key → {name, team_id, probabilities by stage, sources by stage}
    participants: dict[str, dict] = {}
    all_sources: set[str] = set()

    # Load teams for this league for name resolution
    # This lets us merge "Oklahoma City" (Kalshi) with "Oklahoma City Thunder" (Odds API)
    # IMPORTANT: When a league is specified, ONLY load teams from that league
    # to prevent college/MLS/other teams from being matched
    sport_team_lookup: dict[str, dict] = {}  # lowercase name/fragment → team info
    _SPORT_KEY_PREFIXES = {
        "basketball": "basketball_",
        "football": "americanfootball_",
        "hockey": "icehockey_",
        "baseball": "baseball_",
        "soccer": "soccer_",
    }
    # Map league to specific sport key for precise team filtering
    _LEAGUE_TO_SPORT_KEY = {
        "NBA": "basketball_nba",
        "WNBA": "basketball_wnba",
        "NCAAB": "basketball_ncaab",
        "NFL": "americanfootball_nfl",
        "NCAAF": "americanfootball_ncaaf",
        "NHL": "icehockey_nhl",
        "MLB": "baseball_mlb",
        "MLS": "soccer_usa_mls",
    }
    sport_prefix = _SPORT_KEY_PREFIXES.get(sport_lower)
    if sport_prefix or league_upper:
        team_query = select(Team)
        if league_upper and league_upper in _LEAGUE_TO_SPORT_KEY:
            # League-specific: ONLY load teams from this exact league
            # Prevents NCAAB teams from appearing in NBA grid, etc.
            exact_sport_key = _LEAGUE_TO_SPORT_KEY[league_upper]
            team_query = team_query.where(
                Team.sport_id.in_(
                    select(Sport.id).where(Sport.key == exact_sport_key)
                )
            )
        elif league_upper:
            # Unknown league — try ILIKE match
            team_query = team_query.where(
                Team.sport_id.in_(
                    select(Sport.id).where(Sport.key.ilike(f"%{league_upper.lower()}%"))
                )
            )
        elif sport_prefix:
            team_query = team_query.where(
                Team.sport_id.in_(
                    select(Sport.id).where(Sport.key.ilike(f"{sport_prefix}%"))
                )
            )
        team_result = await db.execute(team_query)
        for t in team_result.scalars().all():
            t_dict = {
                "id": t.id,
                "name": t.name,
                "logo_url": t.logo_url_small or t.logo_url,
                "primary_color": t.primary_color,
                "secondary_color": t.secondary_color,
                # Only include record when standings data has active season info
                # (prevents showing stale past-season records during offseason)
                "record": t.current_record if (t.standings_data or {}).get("wins") is not None else None,
                "conference": (t.standings_data or {}).get("conference"),
                "division": (t.standings_data or {}).get("division"),
            }
            # Index by full name, lowercase
            sport_team_lookup[t.name.lower()] = t_dict
            # Also index by short name fragments for partial matching
            # "Oklahoma City Thunder" → also index "oklahoma city"
            parts = t.name.rsplit(" ", 1)
            if len(parts) == 2 and len(parts[0]) >= 3:
                # "Oklahoma City" from "Oklahoma City Thunder"
                sport_team_lookup[parts[0].lower()] = t_dict
            # Index alternate names
            for alt in (t.alternate_names or []):
                sport_team_lookup[alt.lower()] = t_dict

    # Market-level league validation: reject markets from wrong leagues
    # that were miskeyed with a matching canonical key.
    # Strategy: If the market name explicitly mentions a DIFFERENT league, reject it.
    if league_upper:
        _OTHER_LEAGUES = {
            "NBA": [r"\bMLS\b", r"\bWNBA\b", r"\bNHL\b", r"\bNFL\b", r"\bMLB\b", r"\bNCAA\b", r"\bPGA\b"],
            "NFL": [r"\bNBA\b", r"\bMLS\b", r"\bWNBA\b", r"\bNHL\b", r"\bMLB\b", r"\bNCAA\b"],
            "NHL": [r"\bNBA\b", r"\bMLS\b", r"\bWNBA\b", r"\bNFL\b", r"\bMLB\b", r"\bNCAA\b"],
            "MLB": [r"\bNBA\b", r"\bMLS\b", r"\bWNBA\b", r"\bNHL\b", r"\bNFL\b", r"\bNCAA\b"],
            "MLS": [r"\bNBA\b", r"\bWNBA\b", r"\bNHL\b", r"\bNFL\b", r"\bMLB\b", r"\bNCAA\b"],
        }
        wrong_league_patterns = _OTHER_LEAGUES.get(league_upper, [])
        if wrong_league_patterns:
            wrong_league_re = re.compile("|".join(wrong_league_patterns), re.IGNORECASE)
            for stage_key in list(stage_market_groups.keys()):
                stage_market_groups[stage_key] = [
                    m for m in stage_market_groups[stage_key]
                    if not wrong_league_re.search(m.name)
                ]

    # Additionally validate markets with no league in their name by checking
    # if their outcomes match known teams (catches NHL teams miskeyed as NBA, etc.)
    if sport_team_lookup and league_upper:
        for stage_key in list(stage_market_groups.keys()):
            validated = []
            for m in stage_market_groups[stage_key]:
                non_binary_outcomes = [
                    o for o in m.outcomes
                    if o.name and not re.match(r"^(yes|no)$", o.name.strip(), re.IGNORECASE)
                ]
                if not non_binary_outcomes:
                    validated.append(m)
                    continue
                matched = 0
                for o in non_binary_outcomes:
                    name = re.sub(r"^(?:Yes|No)\s*[-:]\s*", "", o.name, flags=re.IGNORECASE).strip()
                    name_lower = name.lower()
                    if name_lower in sport_team_lookup:
                        matched += 1
                match_rate = matched / len(non_binary_outcomes)
                if match_rate >= 0.3:
                    validated.append(m)
                # else: skip — outcomes don't match league teams
            stage_market_groups[stage_key] = validated

    # Build team_info from the sport-specific team lookup ONLY
    # Do NOT blindly load teams from outcome team_ids — those could point
    # to NCAAB/MLS/other teams that shouldn't appear in the NBA grid
    team_info: dict[int, dict] = {}
    # Build team_info from sport_team_lookup (league-specific teams only)
    seen_team_ids: set[int] = set()
    for t_dict in sport_team_lookup.values():
        if t_dict["id"] not in seen_team_ids:
            seen_team_ids.add(t_dict["id"])
            team_info[t_dict["id"]] = t_dict

    def _resolve_outcome_team(outcome) -> tuple[str, int | None, dict | None]:
        """Resolve an outcome to a team, returning (merge_key, team_id, team_info).

        Uses outcome.team_id if available, otherwise fuzzy-matches
        the outcome name against the sport's team list.
        """
        if outcome.team_id and outcome.team_id in team_info:
            return f"team:{outcome.team_id}", outcome.team_id, team_info[outcome.team_id]

        # Try name-based resolution against sport teams
        name = outcome.name or ""
        # Strip "Yes: " / "No: " prefixes (Kalshi format)
        clean_name = re.sub(r"^(?:Yes|No)\s*[-:]\s*", "", name, flags=re.IGNORECASE).strip()

        # Exact match on full cleaned name
        t_info = sport_team_lookup.get(clean_name.lower())
        if t_info:
            return f"team:{t_info['id']}", t_info["id"], t_info

        # Try without trailing "s" (e.g. "76er" → won't work, but catches edge cases)
        # Try stripping common suffixes like "Celtics" → match "Boston Celtics"
        # by checking if any team name ends with this word
        for team_name_lower, t_info in sport_team_lookup.items():
            # "Celtics" matches "Boston Celtics" (exact suffix)
            if team_name_lower.endswith(clean_name.lower()) and len(clean_name) >= 4:
                return f"team:{t_info['id']}", t_info["id"], t_info
            # "Oklahoma City" matches "Oklahoma City Thunder" (exact prefix)
            if team_name_lower.startswith(clean_name.lower()) and len(clean_name) >= 4:
                return f"team:{t_info['id']}", t_info["id"], t_info

        # No match — use name-based merge key
        return _progression_merge_key(outcome), None, None

    # Outcomes to skip — binary outcomes, over/under, dates, generic names
    _SKIP_OUTCOME_RE = re.compile(
        r"""
        ^(yes|no)$                |   # Binary market outcomes
        \bover\b.*\(              |   # "Team: Over (41.5)"
        \bunder\b.*\(             |   # "Team: Under (41.5)"
        ^\d{1,2}\+?\s*(wins?|losses?)|  # "50 wins", "10+ wins"
        ^at\s+least\s+\d          |   # "At least 10% of total games"
        ^(january|february|march|april|may|june|july|august|september|october|november|december)\b |  # month names
        ^\d{1,2}\s*$              |   # bare numbers like "5"
        ^(first|second|third)\s+half |  # "First Half"
        \d+\.\d+\)$                  # trailing "41.5)" from over/under
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # For team sports, require outcomes to resolve to a known team
    # This filters out player names (Wembanyama, Edwards), wrong-league teams
    # (NCAAB teams in NBA grid), and other non-team outcomes
    require_team_resolution = bool(sport_team_lookup) and sport_lower in (
        "basketball", "football", "hockey", "baseball",
    )

    for stage_key, markets in stage_market_groups.items():
        for m in markets:
            source = m.source or "unknown"
            all_sources.add(source)

            for o in m.outcomes:
                # Skip non-team outcomes (binary yes/no, over/under, dates)
                if _SKIP_OUTCOME_RE.search(o.name):
                    continue

                merge_key, resolved_team_id, resolved_info = _resolve_outcome_team(o)

                # For team sports: skip outcomes that don't resolve to a known team
                # This filters player names, wrong-league teams, etc.
                if require_team_resolution and not resolved_team_id:
                    continue

                if merge_key not in participants:
                    t_info = resolved_info or (team_info.get(o.team_id) if o.team_id else None)
                    participants[merge_key] = {
                        "name": resolved_info["name"] if resolved_info else o.name,
                        "team_id": resolved_team_id or o.team_id,
                        "logo_url": t_info["logo_url"] if t_info else None,
                        "primary_color": t_info["primary_color"] if t_info else None,
                        "secondary_color": t_info["secondary_color"] if t_info else None,
                        "conference": t_info["conference"] if t_info else None,
                        "division": t_info["division"] if t_info else None,
                        "record": t_info["record"] if t_info else None,
                        "stages": {},
                    }

                p = participants[merge_key]
                prob = float(o.current_probability) if o.current_probability else None

                # Update team info if resolved in this iteration but not before
                effective_team_id = resolved_team_id or o.team_id
                if effective_team_id and not p["team_id"]:
                    p["team_id"] = effective_team_id
                    t_info = resolved_info or team_info.get(effective_team_id)
                    if t_info:
                        p["name"] = t_info.get("name", p["name"])
                        p["logo_url"] = t_info["logo_url"]
                        p["primary_color"] = t_info["primary_color"]
                        p["secondary_color"] = t_info["secondary_color"]
                        p["conference"] = t_info["conference"]
                        p["division"] = t_info["division"]
                        p["record"] = t_info["record"]

                if stage_key not in p["stages"]:
                    p["stages"][stage_key] = {
                        "sources": [],
                        "probability": None,
                        "change_24h": None,
                        "status": None,
                        "market_id": None,
                    }

                stage_data = p["stages"][stage_key]
                stage_data["sources"].append({
                    "source": source,
                    "probability": prob,
                    "market_id": m.id,
                    "change_24h": float(o.probability_change_24h) if o.probability_change_24h else None,
                })

    # --- Infer conference from conference/pennant stage market names ---
    # When standings_data doesn't have conference (e.g., NFL offseason), we can
    # infer it from which conference-stage market a team appears in.
    # E.g., a team in "NFL: 2027 AFC Champion" → conference = "AFC"
    # A team in "NBA Eastern Conference Champion" → conference = "Eastern Conference"
    _CONF_MARKET_PATTERNS: list[tuple[re.Pattern, str]] = [
        # NFL: "AFC" / "NFC" (no "Conference" suffix in NFL naming)
        (re.compile(r"\bAFC\b(?!\s+(?:East|North|South|West))", re.IGNORECASE), "AFC"),
        (re.compile(r"\bNFC\b(?!\s+(?:East|North|South|West))", re.IGNORECASE), "NFC"),
        # NBA / NHL: "Eastern Conference" / "Western Conference"
        (re.compile(r"\bEastern\b", re.IGNORECASE), "Eastern Conference"),
        (re.compile(r"\bWestern\b", re.IGNORECASE), "Western Conference"),
        # MLB: "American League" / "National League"
        (re.compile(r"\bAmerican\s+League\b", re.IGNORECASE), "American League"),
        (re.compile(r"\bNational\s+League\b", re.IGNORECASE), "National League"),
    ]
    # Only check conference/pennant stage markets
    conf_stage_keys = {"conference", "pennant"}
    for stage_key in conf_stage_keys:
        if stage_key not in stage_market_groups:
            continue
        for m in stage_market_groups[stage_key]:
            # Detect conference from market name
            detected_conf = None
            for pat, conf_name in _CONF_MARKET_PATTERNS:
                if pat.search(m.name):
                    detected_conf = conf_name
                    break
            if not detected_conf:
                continue

            # Assign conference to all outcomes in this market
            for o in m.outcomes:
                if _SKIP_OUTCOME_RE.search(o.name):
                    continue
                merge_key, _, _ = _resolve_outcome_team(o)
                if merge_key in participants and not participants[merge_key].get("conference"):
                    participants[merge_key]["conference"] = detected_conf

    # Average probabilities across sources per stage
    for p in participants.values():
        for stage_key, stage_data in p["stages"].items():
            probs = [s["probability"] for s in stage_data["sources"] if s["probability"] is not None]
            if probs:
                avg_prob = sum(probs) / len(probs)
                stage_data["probability"] = round(avg_prob, 4)
                # Pick best market_id (prefer source with most outcomes for linking)
                stage_data["market_id"] = stage_data["sources"][0]["market_id"]
                # Average 24h changes
                changes = [s["change_24h"] for s in stage_data["sources"] if s["change_24h"] is not None]
                if changes:
                    stage_data["change_24h"] = round(sum(changes) / len(changes), 4)
                # Detect clinched / eliminated
                if avg_prob >= 0.999:
                    stage_data["status"] = "clinched"
                elif avg_prob <= 0.001:
                    stage_data["status"] = "eliminated"

    # Normalize probabilities per stage so they sum to ~100%
    # Sportsbook/prediction market odds often have overround (sum > 100%)
    for stage_key in stage_market_groups:
        stage_total = sum(
            p["stages"][stage_key]["probability"]
            for p in participants.values()
            if stage_key in p["stages"] and p["stages"][stage_key]["probability"] is not None
        )
        if stage_total > 0 and abs(stage_total - 1.0) > 0.05:  # Only normalize if >5% off
            scale = 1.0 / stage_total
            for p in participants.values():
                if stage_key in p["stages"] and p["stages"][stage_key]["probability"] is not None:
                    p["stages"][stage_key]["probability"] = round(
                        p["stages"][stage_key]["probability"] * scale, 4
                    )

    # Sort by highest-stage probability (championship first, fallback to conference, etc.)
    stage_order = sorted(
        [s for s in stages if s["key"] in stage_market_groups],
        key=lambda s: s["order"],
        reverse=True,
    )

    def sort_key(p: dict) -> tuple:
        for stage_def in stage_order:
            sk = stage_def["key"]
            stage_data = p["stages"].get(sk)
            if stage_data and stage_data["probability"] is not None:
                return (stage_def["order"], stage_data["probability"])
        return (0, 0)

    sorted_participants = sorted(participants.values(), key=sort_key, reverse=True)[:top_n]

    # Build ordered stages response
    stages_response = []
    for stage_def in sorted(stages, key=lambda s: s["order"]):
        if stage_def["key"] in stage_market_groups:
            markets_in_stage = stage_market_groups[stage_def["key"]]
            sources_in_stage = list({m.source or "unknown" for m in markets_in_stage})
            stages_response.append({
                "key": stage_def["key"],
                "label": stage_def["label"],
                "order": stage_def["order"],
                "market_count": len(markets_in_stage),
                "sources": sources_in_stage,
                "market_ids": [m.id for m in markets_in_stage],
            })

    return {
        "sport": sport_lower,
        "league": league_upper,
        "season": detected_season,
        "stages": stages_response,
        "teams": sorted_participants,
        "sources": sorted(all_sources),
    }


@router.get("/grouped-feed")
async def grouped_feed(
    category: Optional[str] = Query(None, description="Filter by category (sports, crypto, politics, weather)"),
    sport: Optional[str] = Query(None, description="Filter by sport"),
    sports_only: bool = Query(False, description="Restrict to /sports-page sport categories (excludes esports/geopolitics/crypto/etc.)"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a feed of grouped futures markets optimized for display.

    Returns markets intelligently grouped into:
    - stat_prop: Player stat props (e.g., "Tatum 25+ Points")
    - playoff_progression: Tournament stage progressions
    - threshold: Numeric threshold variants (e.g., Bitcoin price targets)
    - ungrouped: Markets without detected groupings

    Each group includes metadata for rendering the appropriate card type
    (ThresholdSparkline, PlayerStatCard, ProgressionLadder, etc.)
    """
    from ..utils.market_grouping import (
        detect_stat_prop_groups,
        detect_playoff_progression_groups,
        detect_threshold_groups,
    )

    filters = [
        FuturesMarket.status.in_(["active", "open"]),
    ]
    if category:
        filters.append(FuturesMarket.category == category)
    if sport:
        filters.append(FuturesMarket.llm_sport_category == sport)
    if sports_only:
        # #959: real sports filter on llm_sport_category (NOT FuturesMarket.category,
        # which holds values like "championship"). esports is excluded — it stays in
        # Discover/Browse but is not a /sports surface (#958). Function-level import
        # keeps this route circular-import-safe.
        from app.routes.feed import SPORTS_PAGE_CATEGORIES

        filters.append(
            FuturesMarket.llm_sport_category.in_(SPORTS_PAGE_CATEGORIES)
        )

    stmt = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(and_(*filters))
        .order_by(FuturesMarket.updated_at.desc())
        .limit(limit * 5)
    )
    result = await db.execute(stmt)
    markets = result.scalars().unique().all()

    market_dicts = []
    outcome_dicts = []
    for m in markets:
        m_dict = {
            "id": m.id,
            "name": m.name,
            "source": m.source,
            "category": m.category,
            "sport": m.llm_sport_category,
            "status": m.status,
            "group_id": m.group_id,
            "group_type": m.group_type,
            "outcomes": [],
        }
        for o in m.outcomes:
            o_dict = {
                "id": o.id,
                "name": o.name,
                "probability": o.probability,
                "american_odds": o.american_odds,
                "market_id": m.id,
                # #1102: thread parent-market context so threshold grouping scopes
                # to a single real-world question (player/game/entity) instead of
                # pooling every "over #" outcome across unrelated markets.
                "market_name": m.name,
                "group_id": m.group_id,
                "source": m.source,
            }
            m_dict["outcomes"].append(o_dict)
            outcome_dicts.append(o_dict)
        market_dicts.append(m_dict)

    stat_prop_groups = detect_stat_prop_groups(market_dicts)
    playoff_groups = detect_playoff_progression_groups(market_dicts)
    threshold_groups = detect_threshold_groups(outcome_dicts)

    grouped_market_ids = set()
    grouped_outcome_ids = set()
    feed_items = []

    for group_key, group_markets in stat_prop_groups.items():
        if len(group_markets) < 2:
            continue
        for gm in group_markets:
            grouped_market_ids.add(gm["id"])
        first = group_markets[0]
        feed_items.append({
            "type": "stat_prop",
            "group_key": group_key,
            "player_name": first.get("player_name", ""),
            "stat_category": first.get("stat_category", ""),
            "lines": [
                {
                    "id": gm["id"],
                    "name": gm["name"],
                    "probability": gm["outcomes"][0]["probability"] if gm.get("outcomes") else None,
                    "threshold_value": gm.get("threshold_value", 0),
                    "threshold_direction": gm.get("threshold_direction", "above"),
                    "source": gm.get("source", ""),
                }
                for gm in group_markets
            ],
            "market_count": len(group_markets),
        })

    for group_key, group_markets in playoff_groups.items():
        if len(group_markets) < 2:
            continue
        for gm in group_markets:
            grouped_market_ids.add(gm["id"])
        first = group_markets[0]
        feed_items.append({
            "type": "playoff_progression",
            "group_key": group_key,
            "entity_name": first.get("team_name", ""),
            "stages": [
                {
                    "id": gm["id"],
                    "name": gm["name"],
                    "stage_name": gm.get("stage_name", ""),
                    "stage_order": gm.get("stage_order", 0),
                    "probability": gm["outcomes"][0]["probability"] if gm.get("outcomes") else None,
                    "source": gm.get("source", ""),
                }
                for gm in group_markets
            ],
            "market_count": len(group_markets),
        })

    for scope, outcomes in threshold_groups.items():
        if len(outcomes) < 2:
            continue
        for o in outcomes:
            grouped_outcome_ids.add(o["id"])
        # #1102: build a context-carrying title from the parent market name
        # (strip the specific numeric threshold, preserve case for the entity),
        # falling back to the shared stem for legacy/context-free groups.
        market_name = (outcomes[0].get("market_name") or "").strip()
        if market_name:
            title = re.sub(
                r"\$?\b[\d,]+(?:\.\d+)?\+?\b\s*(?:°[FCK]|%|points?|goals?|runs?|yards?)?",
                "",
                market_name,
            )
            title = re.sub(r"\s{2,}", " ", title).strip(" :–-·?")
            if not title:
                title = market_name
        else:
            title = scope.replace("#", "").strip()
        feed_items.append({
            "type": "threshold",
            "group_key": f"threshold:{scope}",
            "title": title,
            "points": [
                {
                    "id": o["id"],
                    "name": o["name"],
                    "probability": o.get("probability"),
                    "threshold_value": o.get("threshold_value", 0),
                    "threshold_unit": o.get("threshold_unit", ""),
                    "threshold_direction": o.get("threshold_direction", "above"),
                }
                for o in outcomes
            ],
            "outcome_count": len(outcomes),
        })

    ungrouped = [
        m for m in market_dicts
        if m["id"] not in grouped_market_ids
    ][:limit]

    for m in ungrouped:
        feed_items.append({
            "type": "market",
            "market": {
                "id": m["id"],
                "name": m["name"],
                "source": m["source"],
                "category": m.get("category"),
                "sport": m.get("sport"),
                "outcomes": m["outcomes"][:5],
            },
        })

    return {
        "feed": feed_items[:limit],
        "total_grouped": len([f for f in feed_items if f["type"] != "market"]),
        "total_ungrouped": len(ungrouped),
        "group_counts": {
            "stat_prop": len(stat_prop_groups),
            "playoff_progression": len(playoff_groups),
            "threshold": len(threshold_groups),
        },
    }


@router.get("/multi-history")
async def get_multi_market_history(
    market_ids: str = Query(..., description="Comma-separated market IDs to aggregate"),
    hours: int = Query(168, description="Hours of history (default 7 days)"),
    top_n: int = Query(10, description="Number of top outcomes to return (default 10, max 50)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregated historical odds across multiple markets (cross-source).

    Merges snapshots from multiple market IDs (e.g., Kalshi + Polymarket + Odds API
    for the same stage) into a single timeline. Outcomes are matched across markets
    by team_id or normalized name, and probabilities are averaged per time bucket.

    Returns the same shape as the single-market history endpoint for drop-in compatibility.
    """
    # Parse market IDs
    try:
        parsed_ids = [int(x.strip()) for x in market_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="market_ids must be comma-separated integers")

    if not parsed_ids:
        raise HTTPException(status_code=400, detail="At least one market_id is required")

    # Single market: delegate to the standard endpoint logic
    if len(parsed_ids) == 1:
        return await get_futures_history(parsed_ids[0], hours=hours, top_n=top_n, db=db)

    # Load all markets with their outcomes
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.id.in_(parsed_ids))
    )
    markets = list(result.scalars().unique().all())

    if not markets:
        raise HTTPException(status_code=404, detail="No markets found")

    # Use the first market for metadata
    primary_market = markets[0]

    # Merge outcomes across markets by team_id or normalized name
    # merge_key -> {name, outcome_ids: [int], current_probabilities: [float]}
    merged_outcomes: dict[str, dict] = {}
    for market in markets:
        for outcome in market.outcomes:
            merge_key = _progression_merge_key(outcome)
            if merge_key not in merged_outcomes:
                merged_outcomes[merge_key] = {
                    "name": outcome.name,
                    "outcome_ids": [],
                    "current_probabilities": [],
                    "changes_24h": [],
                }
            entry = merged_outcomes[merge_key]
            entry["outcome_ids"].append(outcome.id)
            if outcome.current_probability is not None:
                entry["current_probabilities"].append(float(outcome.current_probability))
            if outcome.probability_change_24h is not None:
                entry["changes_24h"].append(float(outcome.probability_change_24h))

    # Sort by average current probability to pick top N
    # Track merge_key alongside each entry for later lookup
    sorted_merged: list[tuple[str, dict]] = sorted(
        merged_outcomes.items(),
        key=lambda kv: mean(kv[1]["current_probabilities"]) if kv[1]["current_probabilities"] else 0,
        reverse=True,
    )

    capped_n = min(top_n, 50)
    top_entries = sorted_merged[:capped_n]

    all_outcome_ids = []
    for _, entry in sorted_merged:
        all_outcome_ids.extend(entry["outcome_ids"])

    if not all_outcome_ids:
        return {
            "market_id": primary_market.id,
            "market_name": primary_market.name,
            "hours": hours,
            "outcomes": [],
            "round_boundaries": None,
            "leaderboard": None,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Fetch all snapshots
    snapshot_query = (
        select(FuturesOddsSnapshot)
        .where(
            FuturesOddsSnapshot.outcome_id.in_(all_outcome_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
        )
        .order_by(FuturesOddsSnapshot.captured_at)
    )
    snap_result = await db.execute(snapshot_query)
    snapshots = snap_result.scalars().all()

    # Build outcome_id -> merge_key lookup
    oid_to_merge_key: dict[int, str] = {}
    for mk, entry in merged_outcomes.items():
        for oid in entry["outcome_ids"]:
            oid_to_merge_key[oid] = mk

    # Group snapshots: merge_key -> captured_at -> [probabilities]
    # This naturally averages across sources since different outcome_ids
    # from different source markets map to the same merge_key
    merged_time_groups: dict[str, dict[datetime, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for snap in snapshots:
        if snap.probability is not None:
            mk = oid_to_merge_key.get(snap.outcome_id)
            if mk is None:
                continue
            merged_time_groups[mk][snap.captured_at].append(float(snap.probability))

    # Build aggregated history per merged outcome
    outcome_history_list = []

    for mk, entry in top_entries:
        synthetic_id = entry["outcome_ids"][0]
        time_groups = merged_time_groups.get(mk, {})

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

        elim = _detect_elimination(history)
        outcome_history_list.append({
            "outcome_id": synthetic_id,
            "name": entry["name"],
            "history": history,
            "eliminated": elim["eliminated"],
            "eliminated_at": elim["eliminated_at"],
        })

    # Round boundaries from primary market
    explicit_boundaries = _derive_round_boundaries(primary_market.market_metadata)
    round_boundaries = _detect_round_boundaries_from_eliminations(
        {oh["outcome_id"]: oh for oh in outcome_history_list}, explicit_boundaries
    )

    return {
        "market_id": primary_market.id,
        "market_name": primary_market.name,
        "hours": hours,
        "outcomes": outcome_history_list,
        "round_boundaries": round_boundaries,
        "leaderboard": (primary_market.market_metadata or {}).get("leaderboard"),
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
    source_breakdown = []
    if outcome_ids:
        bookmakers_result = await db.execute(
            select(FuturesOddsSnapshot.bookmaker)
            .where(FuturesOddsSnapshot.outcome_id.in_(outcome_ids))
            .distinct()
            .order_by(FuturesOddsSnapshot.bookmaker)
        )
        bookmakers = [row[0] for row in bookmakers_result.all()]

        if len(bookmakers) > 1:
            source_breakdown = await _get_source_breakdown(db, outcome_ids)

    detail = _format_market_detail(market, bookmakers)
    if source_breakdown:
        detail["source_breakdown"] = source_breakdown
    return detail


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


@router.get("/{market_id}/progression")
async def get_progression(
    market_id: int,
    top_n: int = Query(32, ge=1, le=64, description="Max participants to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get tournament progression table for a futures market.

    Given any market, finds sibling markets at different stages for the same
    sport/season and assembles a cross-stage pivot showing each participant's
    probability at each stage (e.g., Make Cut → Top 20 → Top 10 → Top 5 → Win).
    """
    # Load starting market
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.id == market_id)
    )
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    sport_cat = market.llm_sport_category
    if not sport_cat:
        return {"sport": None, "stages": [], "participants": []}

    stages = get_stages_for_sport(sport_cat)
    if not stages:
        return {"sport": sport_cat, "stages": [], "participants": []}

    # --- Discover sibling markets ---
    sibling_markets: list[FuturesMarket] = [market]
    source_tournament_name = extract_tournament_name(market.name)

    # Method 1: DataGolf prefix matching
    dg_prefix = get_datagolf_prefix(market.external_id) if market.external_id else None
    if dg_prefix:
        dg_result = await db.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.external_id.ilike(f"{dg_prefix}:%"),
                FuturesMarket.id != market_id,
                FuturesMarket.status == "open",
            )
        )
        sibling_markets.extend(dg_result.scalars().unique().all())

    # Method 1b: Kalshi ticker suffix matching
    # Kalshi golf tickers: KX{TYPE}-{SUFFIX} where SUFFIX identifies the tournament
    # e.g., KXPGATOP10-ARPIPBM26 and KXPGAR3LEAD-ARPIPBM26 share suffix ARPIPBM26
    if len(sibling_markets) < 2 and market.external_id:
        kalshi_suffix = _extract_kalshi_suffix(market.external_id)
        if kalshi_suffix and len(kalshi_suffix) >= 4:
            ks_result = await db.execute(
                select(FuturesMarket)
                .options(selectinload(FuturesMarket.outcomes))
                .where(
                    FuturesMarket.external_id.ilike(f"%-{kalshi_suffix}"),
                    FuturesMarket.id != market_id,
                    FuturesMarket.status == "open",
                )
            )
            sibling_markets.extend(ks_result.scalars().unique().all())

    # Method 2: Canonical key siblings
    if len(sibling_markets) < 2 and market.canonical_market_key:
        # Parse key: "sport:league:category:season" → find same sport:league:*:season
        parts = market.canonical_market_key.split(":")
        if len(parts) >= 4:
            sport_part, league_part = parts[0], parts[1]
            season_part = parts[-1]
            # Search for markets sharing sport:league:*:season
            ck_result = await db.execute(
                select(FuturesMarket)
                .options(selectinload(FuturesMarket.outcomes))
                .where(
                    FuturesMarket.canonical_market_key.ilike(
                        f"{sport_part}:{league_part}:%:{season_part}"
                    ),
                    FuturesMarket.id != market_id,
                    FuturesMarket.status == "open",
                )
            )
            sibling_markets.extend(ck_result.scalars().unique().all())

    # Method 3: Tournament name matching (fallback)
    # Only include markets whose extracted tournament name matches the source market
    if len(sibling_markets) < 2 and source_tournament_name:
        filters = [
            FuturesMarket.llm_sport_category == sport_cat,
            FuturesMarket.id != market_id,
            FuturesMarket.status == "open",
            FuturesMarket.event_id.is_(None),  # Not game-level
        ]
        if market.resolution_date:
            # Look for markets resolving within 30 days of this one
            window = timedelta(days=30)
            filters.append(
                FuturesMarket.resolution_date.between(
                    market.resolution_date - window,
                    market.resolution_date + window,
                )
            )
        scan_result = await db.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(*filters)
            .limit(100)
        )
        candidates = scan_result.scalars().unique().all()
        # Filter: must be same tournament AND not a game-level market
        for candidate in candidates:
            if is_game_level_market(candidate.name):
                continue
            candidate_name = extract_tournament_name(candidate.name)
            if tournament_names_match(source_tournament_name, candidate_name):
                sibling_markets.append(candidate)

    # Deduplicate by market ID
    seen_ids: set[int] = set()
    unique_markets: list[FuturesMarket] = []
    for m in sibling_markets:
        if m.id not in seen_ids:
            seen_ids.add(m.id)
            unique_markets.append(m)

    # Filter out non-golf false positives (soccer, esports, etc.) for golf markets
    if sport_cat == "golf":
        from app.routes.golf import _is_golf_market
        unique_markets = [m for m in unique_markets if _is_golf_market(m)]

    # --- Classify each market into a stage ---
    stage_markets: dict[str, FuturesMarket] = {}
    for m in unique_markets:
        stage_key = classify_market_stage(
            m.name, m.external_id, m.market_tier, stages
        )
        if stage_key and stage_key not in stage_markets:
            stage_markets[stage_key] = m

    if len(stage_markets) < 1:
        return {"sport": sport_cat, "stages": [], "participants": []}

    # --- Build participant cross-reference ---
    # outcome merge key → {name, team_id, probabilities by stage, ...}
    participants: dict[str, dict] = {}

    # Load team info for team_id lookups
    all_team_ids = set()
    for m in stage_markets.values():
        for o in m.outcomes:
            if o.team_id:
                all_team_ids.add(o.team_id)

    team_info: dict[int, dict] = {}
    if all_team_ids:
        team_result = await db.execute(
            select(Team).where(Team.id.in_(all_team_ids))
        )
        for t in team_result.scalars().all():
            team_info[t.id] = {
                "logo_url": t.logo_url_small or t.logo_url,
                "primary_color": t.primary_color,
                "record": t.current_record,
                "conference": (t.standings_data or {}).get("conference"),
            }

    for stage_key, m in stage_markets.items():
        for o in m.outcomes:
            merge_key = _progression_merge_key(o)
            if merge_key not in participants:
                t_info = team_info.get(o.team_id) if o.team_id else None
                participants[merge_key] = {
                    "name": o.name,
                    "team_id": o.team_id,
                    "logo_url": t_info["logo_url"] if t_info else None,
                    "primary_color": t_info["primary_color"] if t_info else None,
                    "conference": t_info["conference"] if t_info else None,
                    "record": t_info["record"] if t_info else None,
                    "probabilities": {},
                    "changes_24h": {},
                    "status": {},
                }
            p = participants[merge_key]
            prob = float(o.current_probability) if o.current_probability else None
            p["probabilities"][stage_key] = prob
            if o.probability_change_24h:
                p["changes_24h"][stage_key] = float(o.probability_change_24h)
            # Detect clinched / eliminated
            if prob is not None:
                if prob >= 0.999:
                    p["status"][stage_key] = "clinched"
                elif prob <= 0.001:
                    p["status"][stage_key] = "eliminated"
            # Update team_id if we found one in a later stage
            if o.team_id and not p["team_id"]:
                p["team_id"] = o.team_id
                t_info = team_info.get(o.team_id)
                if t_info:
                    p["logo_url"] = t_info["logo_url"]
                    p["primary_color"] = t_info["primary_color"]
                    p["conference"] = t_info["conference"]
                    p["record"] = t_info["record"]

    # Sort participants by highest-stage probability (rightmost stage first)
    stage_order = sorted(stage_markets.keys(), key=lambda k: next(
        (s["order"] for s in stages if s["key"] == k), 0
    ), reverse=True)

    def sort_key(p: dict) -> tuple:
        for sk in stage_order:
            prob = p["probabilities"].get(sk)
            if prob is not None:
                return (1, prob)
        return (0, 0)

    sorted_participants = sorted(participants.values(), key=sort_key, reverse=True)[:top_n]

    # Build ordered stages response (only include stages that have markets)
    stages_response = []
    for stage in sorted(stages, key=lambda s: s["order"]):
        if stage["key"] in stage_markets:
            m = stage_markets[stage["key"]]
            stages_response.append({
                "key": stage["key"],
                "label": stage["label"],
                "order": stage["order"],
                "market_id": m.id,
                "market_name": m.name,
            })

    return {
        "sport": sport_cat,
        "tournament_name": source_tournament_name,
        "stages": stages_response,
        "participants": sorted_participants,
    }


def _progression_merge_key(outcome: FuturesOutcome) -> str:
    """Generate a merge key for cross-market participant matching.

    Priority: team_id (most reliable) > normalized name (fallback).

    Name normalization handles cross-source variations:
    - DataGolf: "Scheffler, Scottie" → "scottie scheffler"
    - Kalshi: "Yes: Scottie Scheffler" → "scottie scheffler"
    - Polymarket: "Scottie Scheffler" → "scottie scheffler"
    - Diacritics: "Skarsgård" → "skarsgard"
    - Suffixes: "Jr.", "Sr.", "III" stripped
    """
    if outcome.team_id:
        return f"team:{outcome.team_id}"
    name = outcome.name or ""
    # Strip "Yes: " / "No: " prefixes (Kalshi format)
    name = re.sub(r"^(?:Yes|No)\s*[-:]\s*", "", name, flags=re.IGNORECASE)
    # Strip wrapping quotes (Polymarket NegRisk format)
    name = re.sub(r'^"(.*)"$', r"\1", name)
    # Convert "Last, First" to "First Last" (DataGolf format)
    comma_match = re.match(r"^(\w[\w'-]+),\s+(\w[\w'-]+.*)$", name, flags=re.UNICODE)
    if comma_match:
        name = f"{comma_match.group(2)} {comma_match.group(1)}"
    # Strip diacritics: transliterate non-decomposable letters first (ø→o, đ→d),
    # then NFD decomposition + remove combining marks for the rest (ü→u, é→e)
    name = name.translate(_MERGE_KEY_TRANSLITERATIONS)
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower().strip()
    # Remove Jr./Sr./III suffixes
    name = re.sub(r"\b(?:jr|sr|iii|ii|iv)\.?\b", "", name)
    # Remove non-alphanumeric (keep spaces)
    name = re.sub(r"[^a-z0-9\s]", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    return f"name:{name}"


@router.get("/{market_id}/probability-timeline")
async def get_probability_timeline(
    market_id: int,
    top: int = Query(10, ge=1, le=50, description="Number of top outcomes to show"),
    hours: int = Query(168, ge=1, le=8760, description="Hours of history (default 7 days)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a time-bucketed probability timeline for a futures market.

    Aggregates FuturesOddsSnapshot data into time buckets, takes the median
    probability across bookmakers per outcome, and returns the top N outcomes
    plus a "Field" entry that sums all remaining outcomes' probabilities.

    Designed for multi-participant charts (golf tournaments, championship
    markets with many contestants). Auto-extends the time window for sparse
    markets (common for non-sports futures).
    """
    # Verify market exists and load outcomes + team enrichment
    result = await db.execute(
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.outcomes)
            .selectinload(FuturesOutcome.team)
        )
        .where(FuturesMarket.id == market_id)
    )
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    requested_hours = hours
    actual_hours = hours
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    # #1138: for a live in-play market (golf major, etc.), pin the window's left
    # edge to the event start ("since the event started" — Kalshi's LIVE view).
    # The fixed now-Nh lookback otherwise pads the x-axis with a flat pre-event
    # dead zone (The Open: ~3 of 7 days), which visually crushes real intra-round
    # movement into a sliver. Clamping to commence_time makes the tournament fill
    # the frame at full resolution.
    in_play = bool(market.commence_time and now >= market.commence_time)
    # Only clamp (and skip the extend below) when the start is INSIDE the
    # requested window — i.e. a recently-started short event like a 4-day golf
    # tournament. A season-long futures that commenced months ago
    # (commence_time < cutoff) is left on its normal window + extend behavior.
    clamped_to_start = in_play and market.commence_time > cutoff
    if clamped_to_start:
        cutoff = market.commence_time
        actual_hours = max(1, int((now - cutoff).total_seconds() // 3600))

    # Get ALL outcome IDs (we need them all to compute Field)
    all_outcome_ids = [o.id for o in market.outcomes]

    if not all_outcome_ids:
        return {
            "market_id": market_id,
            "market_name": market.name,
            "hours": hours,
            "actual_hours": hours,
            "top": top,
            "timeline": [],
            "outcomes": [],
        }

    # Fetch all snapshots
    snapshot_query = (
        select(FuturesOddsSnapshot)
        .where(
            FuturesOddsSnapshot.outcome_id.in_(all_outcome_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
        )
        .order_by(FuturesOddsSnapshot.captured_at)
    )

    result = await db.execute(snapshot_query)
    snapshots = list(result.scalars().all())

    # Auto-extend for sparse markets (same logic as /history endpoint). Skipped
    # for in-play markets (#1138): those are pinned to the event start above and
    # are snapshot-dense, so extending would only re-introduce the pre-event dead
    # zone the clamp exists to remove.
    _TIMELINE_EXTEND_TIERS = [] if clamped_to_start else [
        (20, 720),   # <20 snapshots -> try 30 days
        (10, 2160),  # <10 snapshots -> try 90 days
    ]
    for threshold, extended_hours in _TIMELINE_EXTEND_TIERS:
        if len(snapshots) < threshold and extended_hours > actual_hours:
            extended_cutoff = datetime.now(timezone.utc) - timedelta(hours=extended_hours)
            ext_query = (
                select(FuturesOddsSnapshot)
                .where(
                    FuturesOddsSnapshot.outcome_id.in_(all_outcome_ids),
                    FuturesOddsSnapshot.captured_at >= extended_cutoff,
                )
                .order_by(FuturesOddsSnapshot.captured_at)
            )
            ext_result = await db.execute(ext_query)
            extended_snapshots = list(ext_result.scalars().all())
            if len(extended_snapshots) > len(snapshots):
                snapshots = extended_snapshots
                actual_hours = extended_hours

    if not snapshots:
        return {
            "market_id": market_id,
            "market_name": market.name,
            "hours": requested_hours,
            "actual_hours": actual_hours,
            "top": top,
            "timeline": [],
            "outcomes": [],
        }

    # Determine bucket size based on market state.
    # If commence_time is set and we're past it, use 15-min buckets.
    # Otherwise use 1-hour buckets. (`now`/`in_play` computed above.)
    if in_play:
        bucket_seconds = 900  # 15 minutes
    else:
        bucket_seconds = 3600  # 1 hour

    # Determine the top N outcomes by current probability
    sorted_outcomes = sorted(
        market.outcomes,
        key=lambda o: o.current_probability or 0,
        reverse=True,
    )
    top_outcome_ids = {o.id for o in sorted_outcomes[:top]}
    outcome_names = {o.id: o.name for o in market.outcomes}

    # Group snapshots: outcome_id -> bucket_key -> [probabilities]
    # bucket_key is the truncated timestamp
    outcome_buckets: dict[int, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for snap in snapshots:
        if snap.probability is not None:
            ts = int(snap.captured_at.timestamp())
            bucket_key = (ts // bucket_seconds) * bucket_seconds
            outcome_buckets[snap.outcome_id][bucket_key].append(
                float(snap.probability)
            )

    # Collect all bucket keys across all outcomes
    all_bucket_keys = set()
    for buckets in outcome_buckets.values():
        all_bucket_keys.update(buckets.keys())
    sorted_bucket_keys = sorted(all_bucket_keys)

    # Build timeline: for each time bucket, compute median probability per outcome
    timeline = []
    for bucket_key in sorted_bucket_keys:
        bucket_ts = datetime.fromtimestamp(bucket_key, tz=timezone.utc).isoformat()
        entry = {"timestamp": bucket_ts, "outcomes": {}}

        field_prob = 0.0

        for outcome in market.outcomes:
            oid = outcome.id
            probs = outcome_buckets.get(oid, {}).get(bucket_key, [])
            if not probs:
                continue

            med_prob = median(probs)

            if oid in top_outcome_ids:
                entry["outcomes"][outcome_names[oid]] = round(med_prob, 6)
            else:
                field_prob += med_prob

        # Add Field if there are outcomes outside the top N. Cap at 1.0 (#1139):
        # independent binaries carry bookmaker overround and can sum >100%
        # (gotcha #23), which renders as an impossible >100% line.
        if len(market.outcomes) > top:
            entry["outcomes"]["Field"] = round(min(field_prob, 1.0), 6)

        timeline.append(entry)

    # Build outcome metadata list (ordered by current probability)
    outcomes_meta = []
    for o in sorted_outcomes[:top]:
        meta: dict = {
            "id": o.id,
            "name": o.name,
            "current_probability": float(o.current_probability) if o.current_probability else None,
            "rank": o.rank,
            "probability_change_24h": float(o.probability_change_24h) if o.probability_change_24h else None,
            "opening_probability": float(o.opening_probability) if o.opening_probability else None,
        }
        # Team enrichment (logos, colors, record)
        if o.team:
            meta["team_id"] = o.team.id
            meta["logo_small"] = o.team.logo_url_small
            meta["logo_large"] = o.team.logo_url_large
            meta["primary_color"] = o.team.primary_color
            meta["secondary_color"] = o.team.secondary_color
            meta["abbreviation"] = o.team.abbreviation
            meta["record"] = o.team.current_record
            meta["location"] = o.team.location
            meta["espn_id"] = o.team.espn_id
        else:
            meta["team_id"] = o.team_id  # FK may exist without loaded team
        outcomes_meta.append(meta)
    if len(market.outcomes) > top:
        # Sum remaining probabilities for Field
        field_current = sum(
            float(o.current_probability) for o in sorted_outcomes[top:]
            if o.current_probability
        )
        outcomes_meta.append({
            "id": None,
            "name": "Field",
            "current_probability": round(field_current, 6),
        })

    return {
        "market_id": market_id,
        "market_name": market.name,
        "sport_category": market.llm_sport_category,
        "source": market.source,
        "hours": requested_hours,
        "actual_hours": actual_hours,
        "top": top,
        "bucket_seconds": bucket_seconds,
        "timeline": timeline,
        "outcomes": outcomes_meta,
    }


@router.get("/cross-source-timeline")
async def get_cross_source_timeline(
    canonical_key: str = Query(..., description="Canonical market key"),
    top: int = Query(10, ge=1, le=50, description="Number of top outcomes to show"),
    hours: int = Query(168, ge=1, le=8760, description="Hours of history"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a merged probability timeline across all sources sharing a canonical key.

    Outcomes are matched across sources by team_id or normalized name.
    For each time bucket, probabilities from multiple sources are averaged.
    Returns the same shape as the single-market probability-timeline endpoint.
    """
    # Find all markets sharing this canonical key
    markets_result = await db.execute(
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.outcomes)
            .selectinload(FuturesOutcome.team)
        )
        .where(FuturesMarket.canonical_market_key == canonical_key)
        .order_by(FuturesMarket.source)
    )
    markets = markets_result.scalars().unique().all()

    if not markets:
        raise HTTPException(status_code=404, detail="No markets found for this canonical key")

    sources = sorted(set(m.source for m in markets))

    # Merge outcomes across sources by team_id or normalized name
    # merge_key -> { name, team_id, outcome_ids: [int], team: Team|None }
    merged_outcomes: dict[str, dict] = {}
    for market in markets:
        for outcome in market.outcomes:
            merge_key = _outcome_merge_key(outcome)
            if merge_key not in merged_outcomes:
                merged_outcomes[merge_key] = {
                    "name": outcome.name,
                    "team_id": outcome.team_id,
                    "team": outcome.team,
                    "outcome_ids": [],
                    "current_probabilities": [],
                    "changes_24h": [],
                    "opening_probabilities": [],
                    "ranks": [],
                }
            entry = merged_outcomes[merge_key]
            entry["outcome_ids"].append(outcome.id)
            if outcome.current_probability is not None:
                entry["current_probabilities"].append(float(outcome.current_probability))
            if outcome.probability_change_24h is not None:
                entry["changes_24h"].append(float(outcome.probability_change_24h))
            if outcome.opening_probability is not None:
                entry["opening_probabilities"].append(float(outcome.opening_probability))
            if outcome.rank is not None:
                entry["ranks"].append(outcome.rank)
            # Prefer the team-linked entry for name/team
            if outcome.team and not entry["team"]:
                entry["team"] = outcome.team
                entry["name"] = outcome.name

    # Sort merged outcomes by average current probability
    sorted_merged = sorted(
        merged_outcomes.values(),
        key=lambda o: (
            mean(o["current_probabilities"]) if o["current_probabilities"] else 0
        ),
        reverse=True,
    )

    # Top N outcome merge keys
    top_entries = sorted_merged[:top]
    top_outcome_ids = set()
    for entry in top_entries:
        top_outcome_ids.update(entry["outcome_ids"])

    # All outcome IDs for Field computation
    all_outcome_ids = []
    for entry in sorted_merged:
        all_outcome_ids.extend(entry["outcome_ids"])

    if not all_outcome_ids:
        return {
            "market_id": markets[0].id,
            "market_name": markets[0].name,
            "canonical_key": canonical_key,
            "sources": sources,
            "hours": hours,
            "top": top,
            "timeline": [],
            "outcomes": [],
        }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Fetch all snapshots across all sibling markets
    snapshot_query = (
        select(FuturesOddsSnapshot)
        .where(
            FuturesOddsSnapshot.outcome_id.in_(all_outcome_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
        )
        .order_by(FuturesOddsSnapshot.captured_at)
    )
    result = await db.execute(snapshot_query)
    snapshots = result.scalars().all()

    if not snapshots:
        return {
            "market_id": markets[0].id,
            "market_name": markets[0].name,
            "canonical_key": canonical_key,
            "sources": sources,
            "hours": hours,
            "top": top,
            "timeline": [],
            "outcomes": [],
        }

    # Build outcome_id -> merge_key lookup
    oid_to_merge_key: dict[int, str] = {}
    merge_key_list = list(merged_outcomes.keys())
    for mk in merge_key_list:
        for oid in merged_outcomes[mk]["outcome_ids"]:
            oid_to_merge_key[oid] = mk

    # Determine bucket size
    now = datetime.now(timezone.utc)
    primary = markets[0]
    if primary.commence_time and now >= primary.commence_time:
        bucket_seconds = 900
    else:
        bucket_seconds = 3600

    # Group snapshots: merge_key -> bucket_key -> [probabilities]
    # This averages across sources automatically since different outcome_ids
    # from different sources map to the same merge_key
    merged_buckets: dict[str, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for snap in snapshots:
        if snap.probability is not None:
            mk = oid_to_merge_key.get(snap.outcome_id)
            if mk is None:
                continue
            ts = int(snap.captured_at.timestamp())
            bucket_key = (ts // bucket_seconds) * bucket_seconds
            merged_buckets[mk][bucket_key].append(float(snap.probability))

    # Collect all bucket keys
    all_bucket_keys: set[int] = set()
    for buckets in merged_buckets.values():
        all_bucket_keys.update(buckets.keys())
    sorted_bucket_keys = sorted(all_bucket_keys)

    # Top merge keys
    top_merge_keys = set()
    for entry in top_entries:
        mk_match = _outcome_merge_key_from_entry(entry)
        top_merge_keys.add(mk_match)

    # Build timeline
    timeline = []
    for bucket_key in sorted_bucket_keys:
        bucket_ts = datetime.fromtimestamp(bucket_key, tz=timezone.utc).isoformat()
        tl_entry: dict = {"timestamp": bucket_ts, "outcomes": {}}
        field_prob = 0.0

        for mk, entry in merged_outcomes.items():
            probs = merged_buckets.get(mk, {}).get(bucket_key, [])
            if not probs:
                continue
            avg_prob = mean(probs)

            if mk in top_merge_keys:
                tl_entry["outcomes"][entry["name"]] = round(avg_prob, 6)
            else:
                field_prob += avg_prob

        if len(sorted_merged) > top and field_prob > 0:
            tl_entry["outcomes"]["Field"] = round(field_prob, 6)

        timeline.append(tl_entry)

    # Build outcome metadata
    outcomes_meta = []
    for entry in top_entries:
        avg_prob = mean(entry["current_probabilities"]) if entry["current_probabilities"] else None
        avg_change = mean(entry["changes_24h"]) if entry["changes_24h"] else None
        avg_opening = mean(entry["opening_probabilities"]) if entry["opening_probabilities"] else None
        best_rank = min(entry["ranks"]) if entry["ranks"] else None

        meta: dict = {
            "id": entry["outcome_ids"][0] if entry["outcome_ids"] else None,
            "name": entry["name"],
            "current_probability": round(avg_prob, 6) if avg_prob is not None else None,
            "rank": best_rank,
            "probability_change_24h": round(avg_change, 6) if avg_change is not None else None,
            "opening_probability": round(avg_opening, 6) if avg_opening is not None else None,
        }
        team = entry.get("team")
        if team:
            meta["team_id"] = team.id
            meta["logo_small"] = team.logo_url_small
            meta["logo_large"] = team.logo_url_large
            meta["primary_color"] = team.primary_color
            meta["secondary_color"] = team.secondary_color
            meta["abbreviation"] = team.abbreviation
            meta["record"] = team.current_record
            meta["location"] = team.location
            meta["espn_id"] = team.espn_id

        outcomes_meta.append(meta)

    # Add Field
    if len(sorted_merged) > top:
        remaining = sorted_merged[top:]
        field_current = 0.0
        for entry in remaining:
            if entry["current_probabilities"]:
                field_current += mean(entry["current_probabilities"])
        outcomes_meta.append({
            "id": None,
            "name": "Field",
            "current_probability": round(field_current, 6),
        })

    return {
        "market_id": markets[0].id,
        "market_name": markets[0].name,
        "canonical_key": canonical_key,
        "sources": sources,
        "sport_category": markets[0].llm_sport_category,
        "source": "merged",
        "hours": hours,
        "top": top,
        "bucket_seconds": bucket_seconds,
        "timeline": timeline,
        "outcomes": outcomes_meta,
    }


@router.get("/{market_id}/history")
async def get_futures_history(
    market_id: int,
    outcome_id: Optional[int] = Query(None, description="Filter to specific outcome"),
    hours: int = Query(168, description="Hours of history (default 7 days)"),
    top_n: int = Query(10, description="Number of top outcomes to return (default 10, max 50)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get historical odds movement for a futures market.

    Returns time-series data for charting probability changes.
    Auto-extends the time window for sparse markets (common for non-sports
    futures like politics, economics, entertainment) to ensure meaningful
    chart data density.
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

    # Get outcome IDs to fetch history for
    if outcome_id:
        outcome_ids = [outcome_id]
    else:
        # Default to top N outcomes by current probability
        capped_n = min(top_n, 50)
        sorted_outcomes = sorted(
            market.outcomes,
            key=lambda o: o.current_probability or 0,
            reverse=True
        )[:capped_n]
        outcome_ids = [o.id for o in sorted_outcomes]
        # #225 Item 3 — settled charts show the completed journey: the graded
        # winner's line MUST appear even when it was a longshot (low
        # current_probability) or the market's prices went stale/None at
        # settlement. Without this, a settled winner-field charts everyone BUT the
        # winner (the "path to resolution" that never resolves).
        _selected = set(outcome_ids)
        for o in market.outcomes:
            if getattr(o, "is_winner", False) and o.id not in _selected:
                outcome_ids.append(o.id)
                _selected.add(o.id)

    # --- Auto-extend for sparse markets ---
    # Try the requested window first. If too few snapshots, widen to 30d then 90d.
    # This is critical for non-sports futures (polled every 1-2h) whose 7-day
    # window may contain only a handful of data points.
    requested_hours = hours
    actual_hours = hours
    auto_extended = False
    _EXTEND_TIERS = [
        (20, 720),   # <20 snapshots → try 30 days
        (10, 2160),  # <10 snapshots → try 90 days
    ]

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Fetch snapshots for the initial window
    snapshot_query = (
        select(FuturesOddsSnapshot)
        .where(
            FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
        )
        .order_by(FuturesOddsSnapshot.captured_at)
    )
    result = await db.execute(snapshot_query)
    snapshots = list(result.scalars().all())

    # Auto-extend if sparse
    for threshold, extended_hours in _EXTEND_TIERS:
        if len(snapshots) < threshold and extended_hours > actual_hours:
            extended_cutoff = datetime.now(timezone.utc) - timedelta(hours=extended_hours)
            ext_query = (
                select(FuturesOddsSnapshot)
                .where(
                    FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
                    FuturesOddsSnapshot.captured_at >= extended_cutoff,
                )
                .order_by(FuturesOddsSnapshot.captured_at)
            )
            ext_result = await db.execute(ext_query)
            extended_snapshots = list(ext_result.scalars().all())
            if len(extended_snapshots) > len(snapshots):
                snapshots = extended_snapshots
                actual_hours = extended_hours
                auto_extended = True

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

    # Count total unique data points across all outcomes
    total_data_points = sum(len(tg) for tg in outcome_time_groups.values())

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
        elim = _detect_elimination(history)
        outcome_history[oid] = {
            "outcome_id": oid,
            "name": outcome_names.get(oid, "Unknown"),
            "history": history,
            "eliminated": elim["eliminated"],
            "eliminated_at": elim["eliminated_at"],
        }

    # Round boundaries: prefer DataGolf round_history, fall back to
    # inferring rounds from simultaneous elimination patterns
    explicit_boundaries = _derive_round_boundaries(market.market_metadata)
    round_boundaries = _detect_round_boundaries_from_eliminations(
        outcome_history, explicit_boundaries
    )

    # Settled-means-settled evolution freeze (#1177, Queue #230): resolve the
    # graded champion's line to 1.0 at settlement time. Runs AFTER round-boundary
    # detection (which reads real eliminations) so the injected terminal point
    # never perturbs boundary inference. Source-independent: fires on the
    # ``is_winner`` grade even while the winner market is stuck ``status='open'``.
    _apply_settled_winner_freeze(market, outcome_history, outcome_names, outcome_id)

    response: dict = {
        "market_id": market_id,
        "market_name": market.name,
        "hours": requested_hours,
        "actual_hours": actual_hours,
        "outcomes": list(outcome_history.values()),
        "round_boundaries": round_boundaries,
        "leaderboard": (market.market_metadata or {}).get("leaderboard"),
        "total_data_points": total_data_points,
    }

    # Signal to the frontend when data is sparse so it can show appropriate UI
    if auto_extended:
        response["auto_extended"] = True
    if total_data_points < 10:
        response["sparse"] = True

    return response


def _format_market_summary(market: FuturesMarket, source_count_map: dict = None) -> dict:
    """Format a market for list view with top outcomes."""
    # Filter out placeholder outcomes before sorting/display
    real_outcomes = [
        o for o in market.outcomes
        if not _GARBAGE_OUTCOME_RE.match(o.name or "")
    ]

    # Sort outcomes by probability
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
        "outcome_count": len(real_outcomes),
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


_GARBAGE_OUTCOME_RE = re.compile(r"^player\s+[A-Z]{1,3}$", re.I)

SOURCE_DISAGREEMENT_THRESHOLD_PP = 5
SOURCE_STALENESS_DAYS = 7


async def _get_source_breakdown(
    db: AsyncSession, outcome_ids: list[int]
) -> list[dict]:
    """Get the latest probability per bookmaker for each outcome.

    Returns a list of per-source rows sorted alphabetically by bookmaker.
    Sources with ``captured_at`` older than SOURCE_STALENESS_DAYS are flagged
    ``stale: true`` so the frontend can exclude them from spread math and
    render them muted.
    """
    from sqlalchemy import desc

    row_number = func.row_number().over(
        partition_by=[FuturesOddsSnapshot.outcome_id, FuturesOddsSnapshot.bookmaker],
        order_by=desc(FuturesOddsSnapshot.captured_at),
    ).label("rn")

    subq = (
        select(
            FuturesOddsSnapshot.outcome_id,
            FuturesOddsSnapshot.bookmaker,
            FuturesOddsSnapshot.probability,
            FuturesOddsSnapshot.captured_at,
            row_number,
        )
        .where(FuturesOddsSnapshot.outcome_id.in_(outcome_ids))
        .subquery()
    )

    rows = await db.execute(
        select(
            subq.c.outcome_id,
            subq.c.bookmaker,
            subq.c.probability,
            subq.c.captured_at,
        ).where(subq.c.rn == 1)
    )

    staleness_cutoff = datetime.now(timezone.utc) - timedelta(days=SOURCE_STALENESS_DAYS)

    by_bookmaker: dict[str, dict] = {}
    for outcome_id, bookmaker, probability, captured_at in rows.all():
        if bookmaker not in by_bookmaker:
            is_stale = bool(captured_at and captured_at < staleness_cutoff)
            by_bookmaker[bookmaker] = {
                "source": bookmaker,
                "outcomes": {},
                "captured_at": captured_at.isoformat() if captured_at else None,
                "stale": is_stale,
            }
        by_bookmaker[bookmaker]["outcomes"][outcome_id] = round(
            float(probability) * 100, 1
        )
        if captured_at and (
            by_bookmaker[bookmaker]["captured_at"] is None
            or captured_at.isoformat() > by_bookmaker[bookmaker]["captured_at"]
        ):
            by_bookmaker[bookmaker]["captured_at"] = captured_at.isoformat()
            by_bookmaker[bookmaker]["stale"] = captured_at < staleness_cutoff

    return sorted(by_bookmaker.values(), key=lambda s: s["source"])


def _format_market_detail(market: FuturesMarket, bookmakers: list[str] = None) -> dict:
    """Format a market for detail view with all outcomes.

    #993: the click-through must MATCH the answer search shows. Apply the SAME
    shared display pipeline (app.utils.outcome_display) — placeholder filter
    (incl. "Team C"), #23 normalization, leader-pick — so the detail page never
    leads with "Other 100%" while search shows "Cleveland Cavaliers 31%".
    """
    from app.utils.outcome_display import (
        is_placeholder_outcome_name,
        normalize_display_probs,
        leader_pick_order,
    )

    valid_outcomes = [
        o for o in market.outcomes
        if not is_placeholder_outcome_name(o.name)
    ]
    sorted_outcomes = sorted(
        valid_outcomes,
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
    # #993: #23-normalize the displayed distribution + demote a generic
    # "Other/Field" from the headline (same rules as search).
    # #199: gate on mutual-exclusivity — golf make-cut/top-N (mutually_exclusive
    # False) are NOT one-winner fields; normalizing them squashed an honest 86%
    # make-cut down to ~1% on The Open's detail/ladder rail.
    normalize_display_probs(
        outcomes, mutually_exclusive=getattr(market, "mutually_exclusive", True)
    )
    leader_pick_order(outcomes)

    # B7 (L2-91): the up-link mesh. Resolve this market's event-concept key
    # (`event:<domain>:<slug>`, richer per-event page) and its competition hub slug
    # (`/hub/<slug>`) via the shared server-side resolver so the frontend breadcrumb
    # links UP without client-side slug guessing. Best-effort — a derivation slip
    # must never 500 the detail page (honest degrade to no breadcrumb).
    event_concept_key = None
    hub_slug = None
    category_page = None
    sport_page_key = None
    try:
        from app.utils.concept_links import (
            derive_market_category_page,
            derive_market_concept_key,
            derive_market_hub_slug,
            derive_market_sport_page_key,
        )

        event_concept_key = derive_market_concept_key(
            market.external_id,
            market.name,
            market.llm_sport_category,
            len(outcomes),
        )
        hub_slug = derive_market_hub_slug(market.llm_sport_category)
        # L2-94: fallbacks below the hub — themed section page then hub-less sport
        # page. The frontend picks the first of concept/hub/category/sport that's set.
        category_page = derive_market_category_page(market.llm_sport_category)
        sport_page_key = derive_market_sport_page_key(
            market.sport.key if market.sport else None,
            market.llm_sport_category,
        )
    except Exception:
        pass

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
        "group_id": market.group_id,
        "canonical_market_key": market.canonical_market_key,
        "hook_description": market.hook_description,
        "image_url": market.image_url,
        # B7 (L2-91): up-link mesh — concept page + competition hub (null where none).
        "event_concept_key": event_concept_key,
        "hub_slug": hub_slug,
        # L2-94: mesh fallbacks — themed section page then hub-less sport page.
        "category_page": category_page,
        "sport_page_key": sport_page_key,
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


def _outcome_merge_key_from_entry(entry: dict) -> str:
    """
    Reconstruct a merge key from a merged_outcomes entry dict.
    Used by cross-source-timeline to match entries back to merge keys.
    """
    if entry.get("team_id"):
        return f"team:{entry['team_id']}"
    return f"name:{entry['name'].lower().strip()}"


def _avg_probability(by_source: dict) -> float:
    """Average probability across all sources for sorting."""
    probs = [
        v["probability"]
        for v in by_source.values()
        if v.get("probability") is not None
    ]
    return sum(probs) / len(probs) if probs else 0.0


# ── Market Grouping Endpoints ──


@router.get("/groups/{group_id:path}")
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all markets in a specific group, with their outcomes.

    Returns markets sharing the same group_id, enriched with
    threshold detection and cross-source comparison data.
    """
    from app.utils.market_grouping import detect_threshold_groups

    # Fetch markets in this group
    stmt = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.group_id == group_id)
        .order_by(FuturesMarket.group_position.nulls_last(), FuturesMarket.id)
    )
    result = await db.execute(stmt)
    markets = result.scalars().all()

    if not markets:
        raise HTTPException(status_code=404, detail="Group not found")

    # Build market list
    market_list = []
    all_outcomes = []
    for m in markets:
        outcomes = []
        for o in sorted(m.outcomes, key=lambda x: -(x.current_probability or 0)):
            od = {
                "id": o.id,
                "name": o.name,
                "probability": o.current_probability,
                "american_odds": probability_to_american(o.current_probability) if o.current_probability and 0 < o.current_probability < 1 else None,
                "market_id": m.id,
                "source": m.source,
            }
            outcomes.append(od)
            all_outcomes.append(od)

        market_list.append({
            "id": m.id,
            "name": m.name,
            "source": m.source,
            "external_id": m.external_id,
            "group_type": m.group_type,
            "group_position": m.group_position,
            "canonical_market_key": m.canonical_market_key,
            "market_tier": m.market_tier,
            "llm_sport_category": m.llm_sport_category,
            "status": m.status,
            "market_metadata": m.market_metadata,
            "commence_time": m.commence_time.isoformat() if m.commence_time else None,
            "resolution_date": m.resolution_date.isoformat() if m.resolution_date else None,
            "outcomes": outcomes,
            "outcome_count": len(outcomes),
        })

    # Detect threshold groups across all outcomes
    threshold_groups = detect_threshold_groups(all_outcomes)

    # Determine group title from market metadata or market names
    group_title = None
    for m in markets:
        if m.market_metadata and m.market_metadata.get("event_title"):
            group_title = m.market_metadata["event_title"]
            break
    if not group_title and markets:
        group_title = markets[0].name

    return {
        "group_id": group_id,
        "group_title": group_title,
        "group_type": markets[0].group_type if markets else None,
        "market_count": len(market_list),
        "markets": market_list,
        "threshold_groups": {
            stem: [
                {
                    "outcome_id": o["id"],
                    "name": o["name"],
                    "probability": o["probability"],
                    "threshold_value": o["threshold_value"],
                    "threshold_unit": o["threshold_unit"],
                    "threshold_direction": o["threshold_direction"],
                    "source": o["source"],
                }
                for o in outcomes_list
            ]
            for stem, outcomes_list in threshold_groups.items()
        },
        "sources": list({m.source for m in markets}),
    }


@router.get("/groups")
async def list_groups(
    source: Optional[str] = Query(None, description="Filter by source (polymarket, kalshi)"),
    group_type: Optional[str] = Query(None, description="Filter by group type"),
    sport: Optional[str] = Query(None, description="Filter by sport category"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    List all market groups.

    Returns distinct group_ids with summary information.
    """
    # Subquery: get distinct group_ids with their first market's info
    filters = [FuturesMarket.group_id.isnot(None)]
    if source:
        filters.append(FuturesMarket.source == source)
    if group_type:
        filters.append(FuturesMarket.group_type == group_type)
    if sport:
        filters.append(FuturesMarket.llm_sport_category == sport)

    # Get distinct group_ids with count and representative market info
    stmt = (
        select(
            FuturesMarket.group_id,
            FuturesMarket.group_type,
            func.count(FuturesMarket.id).label("market_count"),
            func.min(FuturesMarket.name).label("representative_name"),
            func.min(FuturesMarket.id).label("representative_id"),
            func.array_agg(func.distinct(FuturesMarket.source)).label("sources"),
            func.max(FuturesMarket.updated_at).label("last_updated"),
        )
        .where(and_(*filters))
        .group_by(FuturesMarket.group_id, FuturesMarket.group_type)
        .order_by(func.max(FuturesMarket.updated_at).desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Count total
    count_stmt = (
        select(func.count(func.distinct(FuturesMarket.group_id)))
        .where(and_(*filters))
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "groups": [
            {
                "group_id": row.group_id,
                "group_type": row.group_type,
                "market_count": row.market_count,
                "representative_name": row.representative_name,
                "representative_id": row.representative_id,
                "sources": row.sources or [],
                "last_updated": row.last_updated.isoformat() if row.last_updated else None,
            }
            for row in rows
        ],
    }
