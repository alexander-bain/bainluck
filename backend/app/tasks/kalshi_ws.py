"""Kalshi WebSocket consumer task.

Long-running process that streams live prices and settlement events from
Kalshi's WebSocket API. Replaces the 2-minute REST polling for linked markets
with sub-second latency updates.

Channels:
  - ticker: price updates → batch-write FuturesOutcome.current_probability
  - market_lifecycle_v2: settlement → mark FuturesMarket as resolved
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def _run_kalshi_ws_consumer():
    """Main WebSocket consumer loop.

    1. Load linked Kalshi market tickers from DB
    2. Connect to WS and subscribe to ticker + lifecycle channels
    3. Buffer price updates, flush every 2s
    4. Process settlements immediately
    """
    from sqlalchemy import select, update, text, or_, and_
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import (
        Event, FuturesMarket, FuturesOutcome,
    )
    from app.services.kalshi_ws import KalshiWebSocket
    from app.tasks.base import get_task_session

    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    has_key = os.getenv("KALSHI_RSA_PRIVATE_KEY") or os.getenv("KALSHI_PRIVATE_KEY_PATH")

    if not api_key_id or not has_key:
        logger.warning("Kalshi WS: missing credentials, skipping")
        return {"status": "skipped", "reason": "no_credentials"}

    ws = KalshiWebSocket()

    # -- Load market tickers to subscribe to --
    async with get_task_session() as session:
        result = await session.execute(
            select(
                FuturesMarket.external_id,
                FuturesMarket.id,
            )
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(
                FuturesMarket.source == "kalshi",
                FuturesMarket.event_id.isnot(None),
                or_(
                    Event.status == "live",
                    and_(
                        Event.status == "scheduled",
                        Event.commence_time.isnot(None),
                        Event.commence_time <= text("NOW() + INTERVAL '6 hours'"),
                    ),
                ),
            )
        )
        rows = result.all()

    if not rows:
        logger.info("Kalshi WS: no live/upcoming linked markets")
        return {"status": "no_markets"}

    event_tickers = list({row[0] for row in rows})
    market_id_by_ext = {row[0]: row[1] for row in rows}

    # Load outcome tickers for subscription
    all_market_ids = list(market_id_by_ext.values())
    async with get_task_session() as session:
        outcome_result = await session.execute(
            select(
                FuturesOutcome.external_id,
                FuturesOutcome.market_id,
                FuturesOutcome.id,
            ).where(
                FuturesOutcome.market_id.in_(all_market_ids),
                FuturesOutcome.external_id.isnot(None),
            )
        )
        outcome_rows = outcome_result.all()

    ticker_to_ids: dict[str, tuple[int, int]] = {}
    for ext_id, market_id, outcome_id in outcome_rows:
        ticker_to_ids[ext_id.upper()] = (market_id, outcome_id)

    market_tickers = list(ticker_to_ids.keys())

    logger.info(
        "Kalshi WS: %d tickers (%d events)", len(market_tickers), len(event_tickers),
    )

    stats = {
        "tickers_subscribed": len(market_tickers),
        "price_updates": 0,
        "flushes": 0,
        "settlements": 0,
        "errors": 0,
    }

    # -- Buffered price updates --
    price_buffer: dict[int, float] = {}  # outcome_id → probability
    buffer_lock = asyncio.Lock()

    async def flush_prices():
        """Write buffered price updates to DB in one batch."""
        async with buffer_lock:
            if not price_buffer:
                return
            batch = dict(price_buffer)
            price_buffer.clear()

        try:
            async with get_task_session() as session:
                for outcome_id, prob in batch.items():
                    await session.execute(
                        update(FuturesOutcome)
                        .where(FuturesOutcome.id == outcome_id)
                        .values(current_probability=prob)
                    )
            stats["flushes"] += 1
            stats["price_updates"] += len(batch)
        except Exception:
            stats["errors"] += 1
            logger.exception("Kalshi WS: flush error (%d updates)", len(batch))

    def _parse_dollar(val) -> float | None:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    async def handle_ticker(msg: dict):
        ticker = (msg.get("market_ticker") or msg.get("ticker", "")).upper()
        ids = ticker_to_ids.get(ticker)
        if not ids:
            return

        _, outcome_id = ids

        last_price = _parse_dollar(msg.get("price_dollars"))
        yes_bid = _parse_dollar(msg.get("yes_bid_dollars"))
        yes_ask = _parse_dollar(msg.get("yes_ask_dollars"))

        if last_price is not None and 0 < last_price < 1:
            prob = last_price
        elif yes_bid is not None and yes_ask is not None:
            mid = (yes_bid + yes_ask) / 2
            if 0 < mid < 1:
                prob = mid
            else:
                return
        else:
            return

        async with buffer_lock:
            price_buffer[outcome_id] = prob

    async def handle_lifecycle(msg: dict):
        ticker = (msg.get("market_ticker") or "").upper()
        status = msg.get("status", "")
        result = msg.get("result")

        if status not in ("closed", "settled", "finalized"):
            return

        parts = ticker.rsplit("-", 1)
        if len(parts) < 2:
            return
        event_ticker = parts[0]
        if event_ticker not in market_id_by_ext:
            return

        market_id = market_id_by_ext[event_ticker]

        # Capture closing price from the buffer before flushing
        async with buffer_lock:
            ids = ticker_to_ids.get(ticker)
            closing_price = price_buffer.get(ids[1]) if ids else None

        try:
            async with get_task_session() as session:
                await session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == market_id)
                    .values(status="resolved")
                )

                if result in ("yes", "no"):
                    is_winner = result == "yes"
                    # Set is_winner on the settling outcome
                    await session.execute(
                        update(FuturesOutcome)
                        .where(
                            FuturesOutcome.market_id == market_id,
                            FuturesOutcome.external_id == ticker,
                        )
                        .values(
                            is_winner=is_winner,
                            calibration_probability=closing_price,
                        )
                    )
                    # Set is_winner=False on the opposite outcome
                    await session.execute(
                        update(FuturesOutcome)
                        .where(
                            FuturesOutcome.market_id == market_id,
                            FuturesOutcome.external_id != ticker,
                        )
                        .values(
                            is_winner=not is_winner,
                            calibration_probability=(
                                1.0 - closing_price if closing_price else None
                            ),
                        )
                    )

            stats["settlements"] += 1
            logger.info(
                "Kalshi WS: %s settled (result=%s, closing=%.3f)",
                ticker, result, closing_price or 0,
            )
        except Exception:
            stats["errors"] += 1
            logger.exception("Kalshi WS: settlement error for %s", ticker)

    ws.on_ticker = handle_ticker
    ws.on_lifecycle = handle_lifecycle

    # -- Periodic flush task --
    async def flush_loop():
        while True:
            await asyncio.sleep(2)
            await flush_prices()

    # -- Periodic stats logging --
    async def stats_loop():
        while True:
            await asyncio.sleep(60)
            logger.info(
                "Kalshi WS: %d updates, %d flushes, %d settlements, %d errors, %d msgs",
                stats["price_updates"], stats["flushes"],
                stats["settlements"], stats["errors"],
                ws.stats.get("messages", 0),
            )

    flush_task = asyncio.create_task(flush_loop())
    stats_task = asyncio.create_task(stats_loop())

    try:
        await ws.run(market_tickers=market_tickers)
    except asyncio.CancelledError:
        pass
    finally:
        flush_task.cancel()
        stats_task.cancel()
        await flush_prices()

    logger.info("Kalshi WS consumer exiting: %s", stats)
    return stats
