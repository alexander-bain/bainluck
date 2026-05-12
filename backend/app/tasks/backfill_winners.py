"""
Backfill is_winner on FuturesOutcome from settlement data.

Kalshi: Fetches settled events from the API — each market has result='yes'|'no'.
Polymarket: For resolved markets, outcome_prices=[1.0, 0.0] indicates the winner.
Events: Sets is_winner from game scores (home_score vs away_score).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update, text

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)


async def _backfill_kalshi_winners():
    """Fetch settled Kalshi events and set is_winner on matching outcomes."""
    from app.services.kalshi_api import KalshiAPIService
    from app.models import FuturesMarket, FuturesOutcome

    stats = {"events_fetched": 0, "winners_set": 0, "losers_set": 0,
             "not_found": 0, "errors": []}

    service = KalshiAPIService()
    try:
        cursor = None
        all_events = []
        while True:
            events, cursor = await service.get_events(
                status="settled", with_nested_markets=True,
                limit=200, cursor=cursor,
            )
            all_events.extend(events)
            stats["events_fetched"] += len(events)
            if not cursor or not events:
                break

        logger.info("Kalshi winner backfill: fetched %d settled events", len(all_events))

        async with get_task_session() as session:
            for event_data in all_events:
                event_ticker = event_data.get("event_ticker", "")
                nested = event_data.get("markets") or []

                for market_data in nested:
                    ticker = market_data.get("ticker", "")
                    result = market_data.get("result")
                    if not ticker or not result:
                        continue

                    is_winner = result == "yes"

                    updated = await session.execute(
                        update(FuturesOutcome)
                        .where(
                            FuturesOutcome.external_id == ticker,
                            FuturesOutcome.market_id.in_(
                                select(FuturesMarket.id).where(
                                    FuturesMarket.source == "kalshi",
                                    FuturesMarket.external_id == event_ticker,
                                )
                            ),
                        )
                        .values(is_winner=is_winner)
                    )
                    if updated.rowcount > 0:
                        if is_winner:
                            stats["winners_set"] += updated.rowcount
                        else:
                            stats["losers_set"] += updated.rowcount
                    else:
                        stats["not_found"] += 1

                # Also mark the market as resolved if not already
                await session.execute(
                    update(FuturesMarket)
                    .where(
                        FuturesMarket.source == "kalshi",
                        FuturesMarket.external_id == event_ticker,
                        FuturesMarket.status != "resolved",
                    )
                    .values(status="resolved")
                )

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Kalshi winner backfill error: %s", e)
    finally:
        await service.close()

    logger.info(
        "Kalshi winner backfill: %d events, %d winners, %d losers, %d not found, %d errors",
        stats["events_fetched"], stats["winners_set"], stats["losers_set"],
        stats["not_found"], len(stats["errors"]),
    )
    return stats


async def _backfill_polymarket_winners():
    """Set is_winner on Polymarket outcomes from current_probability on resolved markets."""
    stats = {"markets_checked": 0, "winners_set": 0, "losers_set": 0, "errors": []}

    try:
        async with get_task_session() as session:
            # For resolved Polymarket markets, the winning outcome has
            # current_probability >= 0.95 and the losing has <= 0.05.
            # Only update outcomes that haven't been set yet (is_winner = false).
            winner_result = await session.execute(
                text("""
                    UPDATE futures_outcomes fo
                    SET is_winner = true
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'polymarket'
                      AND fm.status = 'resolved'
                      AND fo.current_probability >= 0.95
                      AND fo.is_winner = false
                """)
            )
            stats["winners_set"] = winner_result.rowcount

            loser_result = await session.execute(
                text("""
                    UPDATE futures_outcomes fo
                    SET is_winner = false
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'polymarket'
                      AND fm.status = 'resolved'
                      AND fo.current_probability <= 0.05
                      AND fo.is_winner = false
                """)
            )
            stats["losers_set"] = loser_result.rowcount

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Polymarket winner backfill error: %s", e)

    logger.info(
        "Polymarket winner backfill: %d winners, %d losers, %d errors",
        stats["winners_set"], stats["losers_set"], len(stats["errors"]),
    )
    return stats


async def _backfill_all_winners():
    """Run all winner backfill tasks."""
    kalshi_stats = await _backfill_kalshi_winners()
    poly_stats = await _backfill_polymarket_winners()
    return {
        "kalshi": kalshi_stats,
        "polymarket": poly_stats,
    }
