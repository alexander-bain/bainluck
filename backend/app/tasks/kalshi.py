"""
Kalshi prediction market polling task.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func

from app.tasks.base import get_task_session, run_async

logger = logging.getLogger(__name__)


def _parse_kalshi_ticker_name(ticker: str) -> str:
    """Extract a human-readable name from a Kalshi market ticker.

    Kalshi tickers look like 'KXCOTY-24-BELICHICK' or 'NBACHAMP-BOS'.
    We take the last segment that isn't purely numeric and title-case it.
    """
    if not ticker:
        return "Unknown"
    parts = ticker.split("-")
    # Walk backwards to find the last non-numeric segment
    for part in reversed(parts):
        if part and not part.isdigit():
            # Title-case and return (e.g. "BELICHICK" -> "Belichick")
            return part.title()
    return ticker


def _kalshi_category_to_internal(kalshi_category: Optional[str]) -> str:
    """Map Kalshi category to internal category."""
    if not kalshi_category:
        return "other"

    category_lower = kalshi_category.lower()

    # Sports categories
    if any(s in category_lower for s in ["sports", "golf", "football", "basketball", "baseball", "hockey", "soccer", "tennis"]):
        return "championship"

    # Olympics
    if "olympic" in category_lower:
        return "championship"

    # Other categories
    if "politic" in category_lower or "election" in category_lower:
        return "politics"
    if "econom" in category_lower or "fed" in category_lower or "inflation" in category_lower:
        return "economics"
    if "entertainment" in category_lower or "movie" in category_lower or "award" in category_lower:
        return "entertainment"
    if "tech" in category_lower or "crypto" in category_lower:
        return "tech"

    return "other"


async def _poll_kalshi_markets():
    """Async implementation of Kalshi polling."""
    from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
    from app.services.kalshi_api import KalshiAPIService
    from app.utils.odds_math import probability_to_american
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    import os

    # Check if Kalshi API key is configured
    if not os.getenv("KALSHI_API_KEY"):
        return {"status": "skipped", "reason": "KALSHI_API_KEY not configured"}

    service = KalshiAPIService()
    stats = {
        "events_processed": 0,
        "markets_processed": 0,
        "outcomes_updated": 0,
        "snapshots_created": 0,
        "errors": [],
    }

    try:
        # Fetch ALL open Kalshi events (no category filter).
        # This ensures we capture every market including sports subcategories
        # (Olympics, etc.) and non-sports markets (politics, economics, etc.)
        # that we'll want as the site expands beyond sports.
        events = await service.get_all_events(categories=None)

        async with get_task_session() as session:
            now = datetime.now(timezone.utc)

            for event in events:
                try:
                    # Each Kalshi event can have multiple markets
                    # For multivariate events, we create one FuturesMarket per event
                    # with outcomes for each market within

                    if not event.markets:
                        continue

                    # Determine category based on Kalshi's category
                    category = _kalshi_category_to_internal(event.category)

                    # For events with multiple markets (multivariate), create one FuturesMarket
                    # For single-market events, use the market directly
                    if len(event.markets) == 1:
                        market = event.markets[0]
                        market_name = event.title
                        commence_time = market.close_time  # When trading ends
                        expiration_time = market.expiration_time
                    else:
                        market_name = event.title
                        # Use earliest close time from all markets
                        close_times = [m.close_time for m in event.markets if m.close_time]
                        commence_time = min(close_times) if close_times else None
                        expiration_times = [m.expiration_time for m in event.markets if m.expiration_time]
                        expiration_time = max(expiration_times) if expiration_times else None

                    # Compute market tier for relevance ranking
                    from app.utils.team_linking import compute_market_tier
                    market_tier = compute_market_tier(market_name, category)

                    # Upsert the FuturesMarket
                    market_stmt = pg_insert(FuturesMarket).values(
                        source="kalshi",
                        external_id=event.event_ticker,
                        name=market_name,
                        category=category,
                        market_tier=market_tier,
                        mutually_exclusive=event.mutually_exclusive,
                        commence_time=commence_time,
                        resolution_date=expiration_time,
                        status="open",
                    ).on_conflict_do_update(
                        index_elements=["source", "external_id"],
                        set_={
                            "name": market_name,
                            "market_tier": market_tier,
                            "commence_time": commence_time,
                            "resolution_date": expiration_time,
                            "updated_at": func.now(),
                        }
                    ).returning(FuturesMarket.id)

                    result = await session.execute(market_stmt)
                    futures_market_id = result.scalar_one()
                    stats["events_processed"] += 1

                    # First pass: compute probabilities and names for all outcomes
                    outcome_data = []
                    for market in event.markets:
                        # Calculate probability from bid/ask midpoint or last price
                        if market.yes_bid is not None and market.yes_ask is not None:
                            prob = (market.yes_bid + market.yes_ask) / 2
                        elif market.last_price is not None:
                            prob = market.last_price
                        else:
                            continue  # Skip markets without pricing

                        american = probability_to_american(prob) if prob and prob > 0 else None

                        # For single-market events, use "Yes" as outcome name
                        # For multi-market events, prefer yes_sub_title (player/team name),
                        # then subtitle, then title if it differs from event title,
                        # then parsed ticker as last resort
                        if len(event.markets) == 1:
                            outcome_name = "Yes"
                        else:
                            if market.yes_sub_title:
                                outcome_name = market.yes_sub_title
                            elif market.subtitle:
                                outcome_name = market.subtitle
                            elif market.title and market.title != event.title:
                                outcome_name = market.title
                            else:
                                # Extract name from ticker (e.g. "COTY-24-BELICHICK" -> "Belichick")
                                outcome_name = _parse_kalshi_ticker_name(market.ticker)

                        outcome_data.append({
                            "market": market,
                            "prob": prob,
                            "american": american,
                            "outcome_name": outcome_name,
                        })

                    # Sort by probability descending to compute ranks (1 = highest)
                    outcome_data.sort(key=lambda x: x["prob"], reverse=True)

                    # Second pass: upsert outcomes with correct probability-based ranks
                    for rank, od in enumerate(outcome_data, 1):
                        market = od["market"]
                        prob = od["prob"]
                        american = od["american"]
                        outcome_name = od["outcome_name"]
                        stats["markets_processed"] += 1

                        # Upsert outcome
                        outcome_stmt = pg_insert(FuturesOutcome).values(
                            market_id=futures_market_id,
                            external_id=market.ticker,
                            name=outcome_name,
                            current_probability=prob,
                            current_american_odds=american,
                            current_yes_bid=market.yes_bid,
                            current_yes_ask=market.yes_ask,
                            opening_probability=prob,
                            opening_american_odds=american,
                            opening_captured_at=now,
                            rank=rank,
                        ).on_conflict_do_update(
                            index_elements=["market_id", "external_id"],
                            set_={
                                "name": outcome_name,
                                "current_probability": prob,
                                "current_american_odds": american,
                                "current_yes_bid": market.yes_bid,
                                "current_yes_ask": market.yes_ask,
                                "rank": rank,
                                "last_updated": func.now(),
                            }
                        ).returning(FuturesOutcome.id)

                        result = await session.execute(outcome_stmt)
                        outcome_id = result.scalar_one()
                        stats["outcomes_updated"] += 1

                        # Create snapshot with Kalshi-specific data
                        snapshot_stmt = pg_insert(FuturesOddsSnapshot).values(
                            outcome_id=outcome_id,
                            bookmaker="kalshi",
                            probability=prob,
                            american_odds=american,
                            yes_bid=market.yes_bid,
                            yes_ask=market.yes_ask,
                            last_price=market.last_price,
                            captured_at=now,
                        )
                        await session.execute(snapshot_stmt)
                        stats["snapshots_created"] += 1

                except Exception as e:
                    stats["errors"].append(f"{event.event_ticker}: {str(e)}")
                    continue

            await session.commit()

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    finally:
        await service.close()

    return stats
