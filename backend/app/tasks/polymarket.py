"""
Polymarket prediction market polling task.

Fetches sports and non-sports prediction market data from Polymarket's
public API (no API key required). Stores as futures markets/outcomes
with source="polymarket".
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)


# =========================================================================
# Tag-to-category mapping
# =========================================================================

# Map Polymarket tags to our internal llm_sport_category values.
# Polymarket provides rich tagging — use it to avoid unnecessary LLM calls.
_TAG_TO_CATEGORY: dict[str, str] = {
    # Sports
    "nba": "basketball",
    "basketball": "basketball",
    "ncaab": "basketball",
    "wnba": "basketball",
    "nfl": "football",
    "football": "football",
    "ncaaf": "football",
    "college football": "football",
    "mlb": "baseball",
    "baseball": "baseball",
    "nhl": "hockey",
    "hockey": "hockey",
    "ufc": "mma",
    "mma": "mma",
    "soccer": "soccer",
    "epl": "soccer",
    "premier league": "soccer",
    "la liga": "soccer",
    "champions league": "soccer",
    "ucl": "soccer",
    "bundesliga": "soccer",
    "serie a": "soccer",
    "mls": "soccer",
    "ligue 1": "soccer",
    "golf": "golf",
    "pga": "golf",
    "tennis": "tennis",
    "atp": "tennis",
    "wta": "tennis",
    "boxing": "boxing",
    "cricket": "cricket",
    "rugby": "rugby",
    "motorsports": "motorsports",
    "f1": "motorsports",
    "formula 1": "motorsports",
    "nascar": "motorsports",
    "olympics": "olympics",
    "esports": "esports",
    # Non-sports
    "politics": "politics",
    "elections": "politics",
    "entertainment": "entertainment",
    "oscars": "entertainment",
    "movies": "entertainment",
    "music": "entertainment",
    "crypto": "crypto",
    "bitcoin": "crypto",
    "ethereum": "crypto",
    "economy": "economics",
    "fed": "economics",
    "inflation": "economics",
    "tech": "tech",
    "ai": "tech",
    "science": "tech",
    "weather": "weather",
    "climate": "weather",
}

# Categories that map to "championship" internal category for sport-linked futures
_SPORT_CATEGORIES = {
    "basketball", "football", "baseball", "hockey", "mma", "soccer",
    "golf", "tennis", "boxing", "cricket", "rugby", "motorsports",
    "olympics", "esports",
}


def _tags_to_category(tags: list[str]) -> tuple[str, Optional[str]]:
    """
    Map Polymarket tags to (internal_category, llm_sport_category).

    Returns:
        Tuple of (category for FuturesMarket.category, llm_sport_category)
    """
    llm_sport_category = None

    for tag in tags:
        tag_lower = tag.lower().strip()
        if tag_lower in _TAG_TO_CATEGORY:
            mapped = _TAG_TO_CATEGORY[tag_lower]
            if mapped in _SPORT_CATEGORIES:
                return "championship", mapped
            else:
                return mapped, mapped

    # If "Sports" tag is present but no specific sport matched
    for tag in tags:
        if tag.lower().strip() == "sports":
            return "championship", None

    return "other", None


# =========================================================================
# Polling implementation
# =========================================================================

async def _poll_polymarket_markets():
    """Async implementation of Polymarket polling."""
    from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
    from app.services.polymarket_api import PolymarketAPIService
    from app.utils.odds_math import probability_to_american
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    service = PolymarketAPIService()
    stats = {
        "events_processed": 0,
        "markets_processed": 0,
        "outcomes_updated": 0,
        "snapshots_created": 0,
        "errors": [],
    }

    try:
        # Fetch all sports events via the /sports endpoint
        events = await service.get_all_sports_events()
        logger.info("Polymarket: fetched %d sports events", len(events))

        async with get_task_session() as session:
            now = datetime.now(timezone.utc)

            for event in events:
                try:
                    if not event.markets:
                        continue

                    # Determine category from tags
                    category, llm_sport_category = _tags_to_category(event.tags)

                    # Compute market tier
                    from app.utils.team_linking import compute_market_tier
                    market_tier = compute_market_tier(event.title, category)

                    # Timing: use event start/end dates
                    commence_time = event.start_date
                    resolution_date = event.end_date

                    # Upsert FuturesMarket
                    market_stmt = pg_insert(FuturesMarket).values(
                        source="polymarket",
                        external_id=event.id,
                        name=event.title,
                        category=category,
                        llm_sport_category=llm_sport_category,
                        market_tier=market_tier,
                        mutually_exclusive=event.neg_risk,
                        commence_time=commence_time,
                        resolution_date=resolution_date,
                        status="open" if event.active else "resolved",
                    ).on_conflict_do_update(
                        index_elements=["source", "external_id"],
                        set_={
                            "name": event.title,
                            "market_tier": market_tier,
                            "commence_time": commence_time,
                            "resolution_date": resolution_date,
                            "status": "open" if event.active else "resolved",
                            "updated_at": func.now(),
                        },
                    ).returning(FuturesMarket.id)

                    result = await session.execute(market_stmt)
                    futures_market_id = result.scalar_one()
                    stats["events_processed"] += 1

                    # Collect outcome data for ranking
                    outcome_data = []

                    if event.neg_risk and len(event.markets) > 1:
                        # NegRisk multi-outcome event: each market is one outcome
                        # (e.g., "NBA Championship Winner" with one market per team)
                        for market in event.markets:
                            if not market.outcome_prices:
                                continue

                            # "Yes" price is the probability for this outcome
                            prob = market.outcome_prices[0] if market.outcome_prices else None
                            if prob is None or prob <= 0:
                                continue

                            # Outcome name: use the market question, cleaned up
                            # e.g., "Will the Lakers win?" -> extract team name
                            outcome_name = _extract_outcome_name(
                                market.question, event.title
                            )

                            # Get bid/ask from CLOB token IDs
                            yes_bid = market.best_bid
                            yes_ask = market.best_ask

                            outcome_data.append({
                                "external_id": market.condition_id,
                                "name": outcome_name,
                                "prob": prob,
                                "yes_bid": yes_bid,
                                "yes_ask": yes_ask,
                                "last_price": market.last_trade_price,
                            })
                    else:
                        # Single-market or non-negRisk event
                        for market in event.markets:
                            if not market.outcome_prices:
                                continue

                            prob = market.outcome_prices[0] if market.outcome_prices else None
                            if prob is None or prob <= 0:
                                continue

                            # For binary events, use "Yes" as outcome name
                            if len(event.markets) == 1:
                                outcome_name = "Yes"
                            else:
                                outcome_name = _extract_outcome_name(
                                    market.question, event.title
                                )

                            outcome_data.append({
                                "external_id": market.condition_id,
                                "name": outcome_name,
                                "prob": prob,
                                "yes_bid": market.best_bid,
                                "yes_ask": market.best_ask,
                                "last_price": market.last_trade_price,
                            })

                    # Sort by probability descending to compute ranks
                    outcome_data.sort(key=lambda x: x["prob"], reverse=True)

                    # Upsert outcomes with ranks
                    for rank, od in enumerate(outcome_data, 1):
                        prob = od["prob"]
                        american = probability_to_american(prob) if prob > 0 else None
                        stats["markets_processed"] += 1

                        outcome_stmt = pg_insert(FuturesOutcome).values(
                            market_id=futures_market_id,
                            external_id=od["external_id"],
                            name=od["name"],
                            current_probability=prob,
                            current_american_odds=american,
                            current_yes_bid=od["yes_bid"],
                            current_yes_ask=od["yes_ask"],
                            opening_probability=prob,
                            opening_american_odds=american,
                            opening_captured_at=now,
                            rank=rank,
                        ).on_conflict_do_update(
                            index_elements=["market_id", "external_id"],
                            set_={
                                "name": od["name"],
                                "current_probability": prob,
                                "current_american_odds": american,
                                "current_yes_bid": od["yes_bid"],
                                "current_yes_ask": od["yes_ask"],
                                "rank": rank,
                                "last_updated": func.now(),
                            },
                        ).returning(FuturesOutcome.id)

                        result = await session.execute(outcome_stmt)
                        outcome_id = result.scalar_one()
                        stats["outcomes_updated"] += 1

                        # Create snapshot
                        snapshot_stmt = pg_insert(FuturesOddsSnapshot).values(
                            outcome_id=outcome_id,
                            bookmaker="polymarket",
                            probability=prob,
                            american_odds=american,
                            yes_bid=od["yes_bid"],
                            yes_ask=od["yes_ask"],
                            last_price=od["last_price"],
                            captured_at=now,
                        )
                        await session.execute(snapshot_stmt)
                        stats["snapshots_created"] += 1

                except Exception as e:
                    stats["errors"].append(f"{event.id}: {str(e)}")
                    continue

            await session.commit()

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    finally:
        await service.close()

    logger.info(
        "Polymarket poll complete: %d events, %d outcomes, %d snapshots, %d errors",
        stats["events_processed"],
        stats["outcomes_updated"],
        stats["snapshots_created"],
        len(stats["errors"]),
    )
    return stats


def _extract_outcome_name(question: str, event_title: str) -> str:
    """
    Extract a clean outcome name from a Polymarket market question.

    For negRisk markets, the question is often like:
    "Will the Los Angeles Lakers win the 2025-26 NBA Championship?"
    We want to extract "Los Angeles Lakers".

    Falls back to the full question if extraction fails.
    """
    if not question:
        return "Unknown"

    # Common patterns: "Will X win...", "Will X be...", "X to win..."
    import re

    # "Will the X win/be/become..."
    match = re.match(
        r"^Will\s+(?:the\s+)?(.+?)\s+(?:win|be|become|make|reach|qualify|finish)\b",
        question,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    # "X to win..."
    match = re.match(
        r"^(.+?)\s+to\s+(?:win|be|become|make|reach)\b",
        question,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    # If question is short enough, use it directly (minus trailing ?)
    cleaned = question.rstrip("?").strip()
    if len(cleaned) <= 60:
        return cleaned

    # Last resort: use first 60 chars
    return cleaned[:60]
