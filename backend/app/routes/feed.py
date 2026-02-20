"""Unified feed API endpoint.

Merges scored events and scored futures into a single ranked list,
providing a "what's interesting right now" view across all content types.

Supports optional authentication: logged-in users get personalized scoring
based on their favorite teams, sport affinities, and pinned items.
Anonymous users see the generic interestingness feed.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies.auth import get_optional_user
from app.models import Event, OddsSnapshot, Sport, FuturesMarket, FuturesOutcome
from app.models.models import User, UserFavorite, UserPreference, UserPin
from app.services import get_db
from app.utils import (
    aggregate_bookmaker_odds,
    detect_reversed_bookmakers,
    compute_highlight,
    get_highlight_label,
    should_highlight,
)
from app.utils.odds_filtering import filter_stale_bookmaker_snapshots as _filter_stale_bookmaker_snapshots
from app.utils.futures_highlights import compute_futures_highlight, should_highlight_futures
from app.utils.feed_reasons import generate_event_reason, generate_futures_reason
from app.utils.personalization import (
    PersonalizationContext,
    compute_event_multiplier,
    compute_futures_multiplier,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def get_feed(
    limit: int = Query(20, description="Number of feed items to return", ge=1, le=50),
    offset: int = Query(0, description="Offset for pagination", ge=0),
    sport: Optional[str] = Query(None, description="Filter by sport category (e.g., basketball, football)"),
    include_events: bool = Query(True, description="Include game events in feed"),
    include_futures: bool = Query(True, description="Include futures markets in feed"),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """
    Get a unified ranked feed of interesting events and futures.

    When authenticated, scores are personalized based on:
    - Favorite teams (follow, local, alma_mater, rival relationships)
    - Sport affinities (boost/suppress by sport preference)
    - Pinned items (boosted in feed)
    - Rival schadenfreude (rival losing = extra boost)

    Returns a single list where each item has:
    - type: "event" or "futures"
    - score: 0-100 interestingness (personalized if authenticated)
    - reason: human-readable explanation
    - headline: short label for badges
    - data: full event or futures payload
    - personalized: whether score was personalized (only present if true)
    """
    now = datetime.now(timezone.utc)

    # Load personalization context (one DB query for all user data)
    ctx = await _load_personalization_context(db, user)

    feed_items = []

    # === SCORE EVENTS ===
    if include_events:
        event_items = await _score_events(db, now, sport, ctx)
        feed_items.extend(event_items)

    # === SCORE FUTURES ===
    if include_futures:
        futures_items = await _score_futures(db, now, sport, ctx)
        feed_items.extend(futures_items)

    # === RANK AND PAGINATE ===
    # Sort by score descending, then by recency as tiebreaker
    feed_items.sort(key=lambda x: (x["score"], x.get("_sort_time", 0)), reverse=True)

    total = len(feed_items)
    paginated = feed_items[offset:offset + limit]

    # Remove internal sort keys
    for item in paginated:
        item.pop("_sort_time", None)

    response = {
        "items": paginated,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }

    # Include personalization metadata if authenticated
    if ctx.is_authenticated:
        response["personalized"] = True
        response["personalization"] = {
            "team_count": len(ctx.team_relations),
            "sport_affinities_count": len(ctx.sport_affinities),
            "pinned_events": len(ctx.pinned_event_ids),
            "pinned_futures": len(ctx.pinned_futures_ids),
        }

    return response


async def _load_personalization_context(
    db: AsyncSession,
    user: Optional[User],
) -> PersonalizationContext:
    """Load all user personalization data into a context object.

    Single query pattern: load favorites, preferences, and pins in parallel-ish
    SQLAlchemy queries, then assemble into the context.
    """
    if not user:
        return PersonalizationContext()

    # Load user favorites (team relationships)
    favorites_result = await db.execute(
        select(UserFavorite).where(UserFavorite.user_id == user.id)
    )
    favorites = favorites_result.scalars().all()

    team_relations: dict[int, set[str]] = {}
    team_weights: dict[int, float] = {}
    for fav in favorites:
        if fav.team_id not in team_relations:
            team_relations[fav.team_id] = set()
        team_relations[fav.team_id].add(fav.relation_type)
        team_weights[fav.team_id] = float(fav.weight) if fav.weight else 1.0

    # Load user preferences (sport affinities)
    prefs_result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )
    prefs = prefs_result.scalar_one_or_none()
    sport_affinities = prefs.sport_affinities if prefs and prefs.sport_affinities else {}

    # Load user pins
    pins_result = await db.execute(
        select(UserPin).where(UserPin.user_id == user.id)
    )
    pins = pins_result.scalars().all()
    pinned_event_ids = {p.target_id for p in pins if p.pin_type == "event"}
    pinned_futures_ids = {p.target_id for p in pins if p.pin_type == "future"}

    return PersonalizationContext(
        team_relations=team_relations,
        team_weights=team_weights,
        sport_affinities=sport_affinities,
        pinned_event_ids=pinned_event_ids,
        pinned_futures_ids=pinned_futures_ids,
        is_authenticated=True,
    )


async def _score_events(
    db: AsyncSession,
    now: datetime,
    sport_filter: Optional[str],
    ctx: PersonalizationContext,
) -> list[dict]:
    """Score and format events for the feed."""
    # Fetch events: live + upcoming (2 days) + recently finished (24h)
    yesterday = now - timedelta(hours=24)
    upcoming_cutoff = now + timedelta(days=2)

    query = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .options(selectinload(Event.sport))
        .where(
            or_(
                Event.status == "live",
                and_(
                    Event.status == "scheduled",
                    Event.commence_time >= now,
                    Event.commence_time <= upcoming_cutoff,
                ),
                and_(
                    Event.status.in_(["completed", "closed"]),
                    Event.commence_time >= yesterday,
                ),
            )
        )
    )

    if sport_filter:
        query = query.where(Sport.key.ilike(f"%{sport_filter}%"))

    result = await db.execute(query)
    events = result.scalars().all()

    if not events:
        return []

    # Get latest odds for scoring
    event_ids = [e.id for e in events]
    aggregated_odds_map = await _get_aggregated_odds(db, event_ids, {e.id: e for e in events})

    # Score each event
    scored_items = []
    for event in events:
        odds_data = aggregated_odds_map.get(event.id, {})
        aggregated = odds_data.get("aggregated", {})

        current_home_prob = aggregated.get("home_probability") if aggregated else None
        current_away_prob = aggregated.get("away_probability") if aggregated else None
        current_spread = aggregated.get("home_spread") if aggregated else None
        current_ou = aggregated.get("over_under") if aggregated else None

        opening_home_prob = float(event.opening_home_probability) if event.opening_home_probability else None
        opening_away_prob = float(event.opening_away_probability) if event.opening_away_probability else None

        highlight_result = compute_highlight(
            status=event.status,
            commence_time=event.commence_time,
            sport_key=event.sport.key if event.sport else None,
            current_home_prob=current_home_prob,
            current_away_prob=current_away_prob,
            current_home_spread=current_spread,
            current_over_under=current_ou,
            opening_home_prob=opening_home_prob,
            opening_away_prob=opening_away_prob,
            opening_home_spread=float(event.opening_home_spread) if event.opening_home_spread else None,
            opening_over_under=float(event.opening_over_under) if event.opening_over_under else None,
            opening_favorite=event.opening_favorite,
            now=now,
        )

        base_score = highlight_result.score

        # Apply personalization multiplier
        p_result = compute_event_multiplier(
            ctx=ctx,
            home_team_id=event.home_team_id,
            away_team_id=event.away_team_id,
            sport_key=event.sport.key if event.sport else None,
            event_id=event.id,
            home_score=event.home_score,
            away_score=event.away_score,
        )
        personalized_score = min(100, int(base_score * p_result.multiplier))

        # Lower the threshold for personalized items — if the user follows a team,
        # surface it even at lower base scores
        min_score = 10 if p_result.is_personalized else 20
        if personalized_score < min_score:
            continue

        # Generate reason text
        reason = generate_event_reason(
            home_team=event.home_team_name,
            away_team=event.away_team_name,
            status=event.status,
            highlight_reasons=highlight_result.reasons,
            home_probability=current_home_prob,
            away_probability=current_away_prob,
            opening_home_prob=opening_home_prob,
            home_score=event.home_score,
            away_score=event.away_score,
        )

        # Build compact event data for the feed
        event_data = {
            "id": event.id,
            "external_id": event.external_id,
            "sport": event.sport.key if event.sport else None,
            "sport_name": event.sport.name if event.sport else None,
            "home_team": event.home_team_name,
            "away_team": event.away_team_name,
            "commence_time": event.commence_time.isoformat(),
            "status": event.status,
            "home_score": event.home_score,
            "away_score": event.away_score,
        }

        if current_home_prob is not None:
            event_data["current_odds"] = {
                "home_probability": current_home_prob,
                "away_probability": current_away_prob,
                "bookmaker_count": aggregated.get("bookmaker_count", 0) if aggregated else 0,
            }

        if opening_home_prob is not None:
            event_data["opening_odds"] = {
                "home_probability": opening_home_prob,
                "away_probability": opening_away_prob,
                "favorite": event.opening_favorite,
            }

        # Compute sort time: live games first (far future), then by commence_time
        sort_time = event.commence_time.timestamp()
        if event.status == "live":
            sort_time = now.timestamp() + 86400  # Push live to top

        item = {
            "type": "event",
            "score": personalized_score,
            "reason": reason,
            "headline": get_highlight_label(highlight_result),
            "data": event_data,
            "_sort_time": sort_time,
        }

        # Include personalization debug info when score was boosted/suppressed
        if p_result.is_personalized:
            item["personalized"] = True
            item["base_score"] = base_score
            item["multiplier"] = round(p_result.multiplier, 2)
            item["personalization_reasons"] = p_result.reasons

        scored_items.append(item)

    return scored_items


async def _score_futures(
    db: AsyncSession,
    now: datetime,
    sport_filter: Optional[str],
    ctx: PersonalizationContext,
) -> list[dict]:
    """Score and format futures markets for the feed."""
    # Fetch open futures with outcomes
    query = (
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.outcomes),
            selectinload(FuturesMarket.sport),
        )
        .where(FuturesMarket.status == "open")
    )

    if sport_filter:
        query = query.where(
            or_(
                FuturesMarket.llm_sport_category.ilike(f"%{sport_filter}%"),
                FuturesMarket.external_id.ilike(f"%{sport_filter}%"),
            )
        )

    result = await db.execute(query)
    markets = result.scalars().unique().all()

    if not markets:
        return []

    # Build canonical key → source count map for cross-source scoring
    canonical_source_counts = await _get_canonical_source_counts(db)

    scored_items = []
    for market in markets:
        # Prepare outcome data for scoring
        outcomes_data = []
        leader_name = None
        leader_prob = None

        sorted_outcomes = sorted(
            market.outcomes,
            key=lambda o: float(o.current_probability) if o.current_probability else 0,
            reverse=True,
        )

        for o in sorted_outcomes[:10]:  # Score based on top 10 outcomes
            prob = float(o.current_probability) if o.current_probability else None
            change = float(o.probability_change_24h) if o.probability_change_24h else None
            outcomes_data.append({
                "name": o.name,
                "probability": prob,
                "probability_change_24h": change,
                "rank": o.rank,
                "rank_change_24h": o.rank_change_24h,
                "opening_probability": float(o.opening_probability) if o.opening_probability else None,
            })

        if sorted_outcomes:
            leader = sorted_outcomes[0]
            leader_name = leader.name
            leader_prob = float(leader.current_probability) if leader.current_probability else None

        # Get source count from canonical key
        source_count = 1
        if market.canonical_market_key:
            source_count = canonical_source_counts.get(market.canonical_market_key, 1)

        highlight_result = compute_futures_highlight(
            market_tier=market.market_tier,
            sport_category=market.llm_sport_category,
            resolution_date=market.resolution_date,
            outcomes=outcomes_data,
            source_count=source_count,
            now=now,
        )

        base_score = highlight_result.score

        # Apply personalization multiplier
        outcome_team_ids = [o.team_id for o in market.outcomes if o.team_id is not None]
        p_result = compute_futures_multiplier(
            ctx=ctx,
            sport_category=market.llm_sport_category,
            outcome_team_ids=outcome_team_ids,
            futures_market_id=market.id,
        )
        personalized_score = min(100, int(base_score * p_result.multiplier))

        min_score = 10 if p_result.is_personalized else 20
        if personalized_score < min_score:
            continue

        # Find the actual biggest mover (with sign) for reason generation
        top_mover_name = highlight_result.top_mover_name
        top_mover_change = None
        if top_mover_name:
            for o in outcomes_data:
                if o["name"] == top_mover_name and o.get("probability_change_24h"):
                    top_mover_change = o["probability_change_24h"]
                    break

        reason = generate_futures_reason(
            market_name=market.name,
            highlight_reasons=highlight_result.reasons,
            top_mover_name=top_mover_name,
            top_mover_change=top_mover_change,
            leader_name=leader_name,
            leader_probability=leader_prob,
            source_count=source_count,
        )

        # Build compact futures data for the feed
        top_outcomes_data = [
            {
                "id": o.id,
                "name": o.name,
                "probability": float(o.current_probability) if o.current_probability else None,
                "rank": o.rank,
                "movement": float(o.probability_change_24h) if o.probability_change_24h else None,
            }
            for o in sorted_outcomes[:3]  # Show top 3 in feed card
        ]

        futures_data = {
            "id": market.id,
            "name": market.name,
            "sport": market.sport.key if market.sport else None,
            "sport_name": market.sport.name if market.sport else None,
            "llm_sport_category": market.llm_sport_category,
            "source": market.source,
            "source_count": source_count,
            "market_tier": market.market_tier,
            "status": market.status,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
            "top_outcomes": top_outcomes_data,
            "outcome_count": len(market.outcomes),
            "canonical_market_key": market.canonical_market_key,
        }

        # Sort time: higher-tier markets and markets resolving soon get priority
        sort_time = now.timestamp()
        if market.resolution_date:
            # Closer resolution = more timely
            days_until = (market.resolution_date - now).total_seconds()
            sort_time = now.timestamp() + max(0, 86400 * 30 - days_until)

        item = {
            "type": "futures",
            "score": personalized_score,
            "reason": reason,
            "headline": highlight_result.primary_reason,
            "data": futures_data,
            "_sort_time": sort_time,
        }

        if p_result.is_personalized:
            item["personalized"] = True
            item["base_score"] = base_score
            item["multiplier"] = round(p_result.multiplier, 2)
            item["personalization_reasons"] = p_result.reasons

        scored_items.append(item)

    return scored_items


async def _get_aggregated_odds(
    db: AsyncSession, event_ids: list[int], event_map: dict
) -> dict:
    """Get latest aggregated odds for a batch of events."""
    if not event_ids:
        return {}

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

    latest_odds_query = (
        select(OddsSnapshot)
        .join(ranked_subq, and_(
            OddsSnapshot.id == ranked_subq.c.id,
            ranked_subq.c.rn == 1
        ))
    )

    latest_odds_result = await db.execute(latest_odds_query)
    all_snapshots = latest_odds_result.scalars().all()

    # Group and aggregate
    snapshots_by_event = defaultdict(list)
    for snap in all_snapshots:
        snapshots_by_event[snap.event_id].append(snap)

    aggregated_odds_map = {}
    for event_id, snaps in snapshots_by_event.items():
        ev = event_map.get(event_id)
        filtered_snaps = _filter_stale_bookmaker_snapshots(
            snaps,
            event_status=(ev.status if ev else "scheduled"),
            commence_time=(ev.commence_time if ev else None),
        )
        reversed_bks = detect_reversed_bookmakers(filtered_snaps)
        agg_snaps = [s for s in filtered_snaps if s.bookmaker not in reversed_bks] if reversed_bks else filtered_snaps
        aggregated_odds_map[event_id] = {
            "aggregated": aggregate_bookmaker_odds(agg_snaps if agg_snaps else filtered_snaps),
        }

    return aggregated_odds_map


async def _get_canonical_source_counts(db: AsyncSession) -> dict[str, int]:
    """Get source count for each canonical market key."""
    result = await db.execute(
        select(
            FuturesMarket.canonical_market_key,
            func.count(func.distinct(FuturesMarket.source)).label("source_count"),
        )
        .where(FuturesMarket.canonical_market_key.isnot(None))
        .group_by(FuturesMarket.canonical_market_key)
    )
    return {row.canonical_market_key: row.source_count for row in result.all()}
