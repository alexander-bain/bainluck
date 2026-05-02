"""Team detail page API."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_, case, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Team, Event, Sport, FuturesMarket, FuturesOutcome
from app.services import get_db

router = APIRouter()


@router.get("/{identifier}")
async def get_team(identifier: str, db: AsyncSession = Depends(get_db)):
    """Get a team page with upcoming/recent games, futures, and championship path."""
    # Try integer ID first, then slug
    team_filter = Team.slug == identifier
    try:
        team_id = int(identifier)
        team_filter = or_(Team.id == team_id, Team.slug == identifier)
    except ValueError:
        pass

    result = await db.execute(
        select(Team).options(selectinload(Team.sport)).where(team_filter)
    )
    team = result.scalars().first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    now = datetime.now(timezone.utc)

    # --- Events: upcoming + recent ---
    base_event_filter = or_(
        Event.home_team_id == team.id,
        Event.away_team_id == team.id,
        Event.home_team_name == team.name,
        Event.away_team_name == team.name,
    )

    upcoming_q = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            base_event_filter,
            Event.status.in_(["live", "scheduled"]),
            Event.commence_time >= now - timedelta(hours=2),
        )
        .order_by(
            case((Event.status == "live", 0), else_=1),
            Event.commence_time.asc(),
        )
        .limit(5)
    )

    recent_q = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            base_event_filter,
            Event.status == "completed",
            Event.commence_time >= now - timedelta(days=30),
        )
        .order_by(Event.commence_time.desc())
        .limit(5)
    )

    upcoming_r, recent_r = await db.execute(upcoming_q), await db.execute(recent_q)
    upcoming_events = [_format_event_brief(e, team) for e in upcoming_r.scalars().all()]
    recent_events = [_format_event_brief(e, team) for e in recent_r.scalars().all()]

    # --- Team futures (championship, conference, division, awards) ---
    from app.routes.user import _query_team_futures
    futures_data = await _query_team_futures([team.id], db, limit=30)

    # --- Championship path (tier 1/2/4 probabilities) ---
    champ_path = await _get_championship_path(team.id, db)

    return {
        "team": _format_team(team),
        "upcoming_events": upcoming_events,
        "recent_events": recent_events,
        "futures": futures_data.get("items", []),
        "championship_path": champ_path,
    }


def _format_team(team: Team) -> dict:
    sport = team.sport
    return {
        "id": team.id,
        "slug": team.slug,
        "name": team.name,
        "abbreviation": team.abbreviation,
        "sport_key": sport.key if sport else None,
        "sport_name": sport.name if sport else None,
        "location": team.location,
        "primary_color": team.primary_color,
        "secondary_color": team.secondary_color,
        "logo_small": team.logo_url_small,
        "logo_large": team.logo_url_large,
        "record": team.current_record,
        "standings": team.standings_data,
        "season_stats": team.season_stats,
        "roster": team.roster_players,
    }


def _format_event_brief(event: Event, team: Team) -> dict:
    """Compact event format for team page game lists."""
    sport = event.sport
    is_home = (event.home_team_id == team.id) or (event.home_team_name == team.name)
    opponent = event.away_team_name if is_home else event.home_team_name

    wp = None
    if event.win_probability_sources and isinstance(event.win_probability_sources, dict):
        agg = event.win_probability_sources.get("aggregate", {})
        wp = agg.get("home") if is_home else agg.get("away")

    return {
        "id": event.id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "home_score": event.home_score,
        "away_score": event.away_score,
        "status": event.status,
        "commence_time": event.commence_time.isoformat() if event.commence_time else None,
        "sport_key": sport.key if sport else None,
        "is_home": is_home,
        "opponent": opponent,
        "win_probability": round(wp, 3) if wp is not None else None,
    }


async def _get_championship_path(team_id: int, db: AsyncSession) -> list[dict]:
    """Get championship/conference/division probabilities for a team."""
    result = await db.execute(
        select(FuturesOutcome, FuturesMarket)
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(
            FuturesOutcome.team_id == team_id,
            FuturesMarket.status == "open",
            FuturesMarket.event_id.is_(None),
            FuturesMarket.market_tier.in_([1, 2, 4]),
        )
        .order_by(FuturesMarket.market_tier.asc())
    )

    seen_tiers: set[int] = set()
    path = []
    tier_labels = {1: "Championship", 2: "Conference", 4: "Division"}
    for outcome, market in result.all():
        tier = market.market_tier
        if tier in seen_tiers:
            continue
        seen_tiers.add(tier)
        path.append({
            "tier": tier,
            "label": tier_labels.get(tier, "Other"),
            "market_name": market.name,
            "market_id": market.id,
            "probability": float(outcome.current_probability) if outcome.current_probability else None,
            "rank": outcome.rank,
            "movement": float(outcome.probability_change_24h) if outcome.probability_change_24h else None,
        })
    return path
