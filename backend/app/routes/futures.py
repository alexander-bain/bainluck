"""Futures/Outrights API endpoints."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot, Sport
from app.services import get_db, OddsAPIService
from app.utils import probability_to_american

router = APIRouter()


@router.get("")
async def list_futures_markets(
    sport: Optional[str] = Query(None, description="Filter by sport key"),
    status: str = Query("open", description="Filter by status (open, resolved, all)"),
    limit: int = Query(50, description="Maximum number of markets to return"),
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

    if sport:
        # Join to Sport table to filter by sport key
        query = query.join(Sport, FuturesMarket.sport_id == Sport.id)
        conditions.append(Sport.key.ilike(f"%{sport}%"))

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(FuturesMarket.updated_at.desc()).limit(limit)

    result = await db.execute(query)
    markets = result.scalars().unique().all()

    return {
        "markets": [
            _format_market_summary(market)
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

    return _format_market_detail(market)


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

    # Group by outcome
    outcome_history = {}
    outcome_names = {o.id: o.name for o in market.outcomes}

    for snapshot in snapshots:
        oid = snapshot.outcome_id
        if oid not in outcome_history:
            outcome_history[oid] = {
                "outcome_id": oid,
                "name": outcome_names.get(oid, "Unknown"),
                "history": [],
            }
        outcome_history[oid]["history"].append({
            "timestamp": snapshot.captured_at.isoformat(),
            "probability": float(snapshot.probability) if snapshot.probability else None,
            "american_odds": snapshot.american_odds,
            "bookmaker": snapshot.bookmaker,
        })

    return {
        "market_id": market_id,
        "market_name": market.name,
        "hours": hours,
        "outcomes": list(outcome_history.values()),
    }


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
    query = (
        select(FuturesOutcome)
        .options(selectinload(FuturesOutcome.market))
        .where(FuturesOutcome.probability_change_24h.isnot(None))
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


def _format_market_summary(market: FuturesMarket) -> dict:
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


def _format_market_detail(market: FuturesMarket) -> dict:
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
        "status": market.status,
        "source": market.source,
        "external_id": market.external_id,
        "mutually_exclusive": market.mutually_exclusive,
        "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
        "outcomes": outcomes,
        "outcome_count": len(outcomes),
        "created_at": market.created_at.isoformat() if market.created_at else None,
        "updated_at": market.updated_at.isoformat() if market.updated_at else None,
    }
