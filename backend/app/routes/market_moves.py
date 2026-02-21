"""
'The Market Was Wrong' endpoint.

Surfaces recently completed games where the pre-game favorite lost (upsets)
and futures markets with the biggest post-game shifts. Shows how the betting
market misjudged outcomes — a daily highlight reel of market surprises.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, or_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, Sport, FuturesMarket, FuturesOutcome
from app.services import get_db
from app.utils.highlights import LEAGUE_TIERS

logger = logging.getLogger(__name__)

router = APIRouter()

# Tier 1 + 2 sport keys for prioritization
_PRIORITY_SPORT_KEYS = {k for k, v in LEAGUE_TIERS.items() if v <= 2}


@router.get("")
async def get_market_was_wrong(
    hours: int = Query(48, description="Look back period in hours", ge=6, le=168),
    limit: int = Query(20, description="Max items to return", ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a ranked list of recent market surprises.

    Surfaces:
    1. **Upsets**: Games where the pre-game favorite lost
    2. **Big swings**: Completed games with the largest probability errors
    3. **Futures movers**: Championship/MVP odds that shifted significantly after recent results

    Items are ranked by how wrong the market was (bigger surprise = higher rank).
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    items = []

    # === 1. FIND UPSETS AND BIG MARKET ERRORS ===
    event_query = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .options(selectinload(Event.sport))
        .where(
            Event.status.in_(["completed", "closed"]),
            Event.commence_time >= cutoff,
            Event.opening_home_probability.isnot(None),
            Event.home_score.isnot(None),
            Event.away_score.isnot(None),
        )
        .order_by(Event.commence_time.desc())
        .limit(200)  # Safety cap
    )

    result = await db.execute(event_query)
    events = result.scalars().all()

    for event in events:
        opening_home = float(event.opening_home_probability)
        opening_away = float(event.opening_away_probability) if event.opening_away_probability else 1 - opening_home

        home_score = event.home_score
        away_score = event.away_score

        # Determine who won and who was favored
        if home_score == away_score:
            continue  # Ties aren't "wrong" per se

        home_won = home_score > away_score
        home_was_favored = opening_home > 0.5
        away_was_favored = opening_away > 0.5

        # Calculate "wrongness" — how far the market was from the actual result
        # Actual result is 1.0 (home won) or 0.0 (away won)
        actual_home_prob = 1.0 if home_won else 0.0
        market_error = abs(actual_home_prob - opening_home)

        # Is this an upset? (favorite lost)
        is_upset = (home_was_favored and not home_won) or (away_was_favored and home_won)

        # Determine the winner/loser names and probabilities
        winner = event.home_team_name if home_won else event.away_team_name
        loser = event.away_team_name if home_won else event.home_team_name
        winner_prob = opening_home if home_won else opening_away
        loser_prob = opening_away if home_won else opening_home
        winner_score = home_score if home_won else away_score
        loser_score = away_score if home_won else home_score

        # Score this item: bigger upset = higher score
        # Base: market error percentage (0-100)
        wrongness_score = market_error * 100

        # Bonus for true upsets (favorite lost)
        if is_upset:
            wrongness_score += 20

        # Bonus for major league games
        sport_key = event.sport.key if event.sport else None
        if sport_key in _PRIORITY_SPORT_KEYS:
            wrongness_score += 15

        # Min threshold: at least 10% market error to be interesting
        if market_error < 0.10 and not is_upset:
            continue

        # Upsets must be real (favorite had >55% chance)
        if is_upset and max(opening_home, opening_away) < 0.55:
            continue

        # Generate description
        if is_upset:
            fav_pct = round(loser_prob * 100)
            description = f"{winner} upset {loser} ({winner_score}-{loser_score}). {loser} was a {fav_pct}% favorite."
        else:
            description = f"{winner} beat {loser} ({winner_score}-{loser_score}), but the market only gave them {round(winner_prob * 100)}%."

        items.append({
            "type": "upset" if is_upset else "market_error",
            "score": round(wrongness_score, 1),
            "event_id": event.id,
            "sport": sport_key,
            "sport_name": event.sport.name if event.sport else None,
            "home_team": event.home_team_name,
            "away_team": event.away_team_name,
            "home_score": home_score,
            "away_score": away_score,
            "winner": winner,
            "loser": loser,
            "winner_score": winner_score,
            "loser_score": loser_score,
            "winner_opening_prob": round(winner_prob, 3),
            "loser_opening_prob": round(loser_prob, 3),
            "market_error": round(market_error, 3),
            "is_upset": is_upset,
            "description": description,
            "commence_time": event.commence_time.isoformat(),
        })

    # === 2. FIND BIGGEST FUTURES MOVERS ===
    futures_query = (
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.outcomes),
            selectinload(FuturesMarket.sport),
        )
        .where(
            FuturesMarket.status == "open",
            FuturesMarket.market_tier.isnot(None),
            FuturesMarket.market_tier <= 3,  # Championship, conference, awards
        )
        .limit(50)
    )

    futures_result = await db.execute(futures_query)
    markets = futures_result.scalars().unique().all()

    for market in markets:
        for outcome in market.outcomes:
            change_24h = float(outcome.probability_change_24h) if outcome.probability_change_24h else 0
            abs_change = abs(change_24h)

            # Only include significant movers (>3% in 24h)
            if abs_change < 0.03:
                continue

            current_prob = float(outcome.current_probability) if outcome.current_probability else None
            if current_prob is None:
                continue

            direction = "surged" if change_24h > 0 else "dropped"
            pct_change = round(abs_change * 100, 1)

            # Score: bigger move = higher score
            mover_score = abs_change * 100
            # Bonus for championship markets
            if market.market_tier == 1:
                mover_score += 10
            # Bonus for major leagues
            if market.llm_sport_category in ("basketball", "football", "baseball", "hockey"):
                mover_score += 5

            description = (
                f"{outcome.name} {direction} {pct_change}% to {round(current_prob * 100)}% "
                f"in {market.name}"
            )

            items.append({
                "type": "futures_mover",
                "score": round(mover_score, 1),
                "market_id": market.id,
                "market_name": market.name,
                "market_tier": market.market_tier,
                "sport": market.sport.key if market.sport else None,
                "sport_name": market.sport.name if market.sport else None,
                "llm_sport_category": market.llm_sport_category,
                "outcome_name": outcome.name,
                "current_probability": round(current_prob, 3),
                "change_24h": round(change_24h, 3),
                "direction": direction,
                "description": description,
            })

    # === RANK AND RETURN ===
    items.sort(key=lambda x: x["score"], reverse=True)
    items = items[:limit]

    return {
        "items": items,
        "total": len(items),
        "hours": hours,
        "generated_at": now.isoformat(),
    }
