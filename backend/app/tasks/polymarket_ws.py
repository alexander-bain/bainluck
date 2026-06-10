"""Polymarket WebSocket consumer task.

Streams live prices and resolution events from Polymarket's CLOB WebSocket.
No auth required. Runs alongside the Kalshi WS consumer on the same dyno.

Events:
  - best_bid_ask: price updates → FuturesOutcome.current_probability
  - last_trade_price: trade executions → FuturesOutcome.current_probability
  - market_resolved: settlement → FuturesMarket resolved + is_winner
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def _run_polymarket_ws_consumer():
    """Main Polymarket WebSocket consumer loop."""
    from sqlalchemy import select, update, text, or_, and_

    from app.models.models import (
        Event, FuturesMarket, FuturesOutcome,
    )
    from app.services.polymarket_ws import PolymarketWebSocket
    from app.tasks.base import get_task_session

    ws = PolymarketWebSocket()

    # Load linked Polymarket market asset IDs
    async with get_task_session() as session:
        result = await session.execute(
            select(
                FuturesOutcome.id,
                FuturesOutcome.market_id,
                FuturesOutcome.external_id,
                FuturesMarket.external_id.label("market_ext_id"),
            )
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(
                FuturesMarket.source == "polymarket",
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
        logger.info("Polymarket WS: no live/upcoming linked markets")
        return {"status": "no_markets"}

    # Polymarket outcomes store condition_id as external_id (e.g. "0xabc..._yes").
    # But the WS needs asset_ids (token IDs), which we store in market_metadata.
    # For now, load token IDs from the outcomes' market_metadata.
    # Build lookup: condition_id → (market_id, outcome_id)
    condition_to_ids: dict[str, tuple[int, int]] = {}
    market_ids = set()
    for outcome_id, market_id, ext_id, market_ext_id in rows:
        if ext_id:
            condition_to_ids[ext_id] = (market_id, outcome_id)
        market_ids.add(market_id)

    # Load clob_token_ids from market_metadata
    asset_ids: list[str] = []
    asset_to_outcome: dict[str, int] = {}  # asset_id → outcome_id
    asset_to_market: dict[str, int] = {}   # asset_id → market_id
    condition_to_market: dict[str, int] = {}  # condition_id → market_id

    async with get_task_session() as session:
        market_result = await session.execute(
            select(FuturesMarket.id, FuturesMarket.external_id, FuturesMarket.market_metadata)
            .where(FuturesMarket.id.in_(list(market_ids)))
        )
        for mid, mext, metadata in market_result.all():
            if mext:
                condition_to_market[mext] = mid
            if not metadata:
                continue
            tokens = metadata.get("clob_token_ids") or metadata.get("clobTokenIds")
            if not tokens:
                continue
            if isinstance(tokens, str):
                import json
                try:
                    tokens = json.loads(tokens)
                except Exception:
                    continue
            for token in tokens:
                asset_ids.append(str(token))
                asset_to_market[str(token)] = mid

        # Map asset_ids to outcomes via order (first token = yes, second = no)
        outcome_result = await session.execute(
            select(FuturesOutcome.id, FuturesOutcome.market_id, FuturesOutcome.external_id)
            .where(FuturesOutcome.market_id.in_(list(market_ids)))
            .order_by(FuturesOutcome.id)
        )
        outcomes_by_market: dict[int, list[tuple[int, str]]] = {}
        for oid, mid, ext in outcome_result.all():
            outcomes_by_market.setdefault(mid, []).append((oid, ext or ""))

    if not asset_ids:
        logger.info("Polymarket WS: no asset IDs found in market_metadata")
        return {"status": "no_asset_ids"}

    logger.info(
        "Polymarket WS: %d asset IDs (%d markets)",
        len(asset_ids), len(market_ids),
    )

    stats = {
        "assets_subscribed": len(asset_ids),
        "price_updates": 0,
        "trade_updates": 0,
        "resolutions": 0,
        "errors": 0,
    }

    # Buffered price updates
    price_buffer: dict[int, float] = {}
    buffer_lock = asyncio.Lock()

    async def flush_prices():
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
            stats["price_updates"] += len(batch)
        except Exception:
            stats["errors"] += 1
            logger.exception("Polymarket WS: flush error")

    async def handle_price(msg: dict):
        """Handle best_bid_ask event."""
        asset_id = msg.get("asset_id", "")
        market_id = asset_to_market.get(asset_id)
        if not market_id:
            return

        best_bid = msg.get("best_bid")
        best_ask = msg.get("best_ask")
        if best_bid is None or best_ask is None:
            return

        try:
            prob = (float(best_bid) + float(best_ask)) / 2
        except (ValueError, TypeError):
            return
        if prob <= 0 or prob >= 1:
            return

        # Find the outcome for this asset_id
        outcomes = outcomes_by_market.get(market_id, [])
        if not outcomes:
            return
        # First outcome is typically the "Yes" side
        outcome_id = outcomes[0][0]

        async with buffer_lock:
            price_buffer[outcome_id] = prob

    async def handle_trade(msg: dict):
        """Handle last_trade_price event."""
        asset_id = msg.get("asset_id", "")
        market_id = asset_to_market.get(asset_id)
        if not market_id:
            return

        price = msg.get("price")
        if price is None:
            return
        try:
            prob = float(price)
        except (ValueError, TypeError):
            return
        if prob <= 0 or prob >= 1:
            return

        outcomes = outcomes_by_market.get(market_id, [])
        if not outcomes:
            return
        outcome_id = outcomes[0][0]

        async with buffer_lock:
            price_buffer[outcome_id] = prob
        stats["trade_updates"] += 1

    async def handle_resolved(msg: dict):
        """Handle market_resolved event."""
        condition_id = msg.get("market", "")
        winning_outcome = msg.get("winning_outcome", "")
        winning_asset = msg.get("winning_asset_id", "")

        market_id = condition_to_market.get(condition_id)
        if not market_id:
            return

        try:
            async with get_task_session() as session:
                await session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == market_id)
                    .values(status="resolved")
                )

                outcomes = outcomes_by_market.get(market_id, [])
                for oid, ext in outcomes:
                    is_winner = False
                    if winning_outcome.lower() == "yes" and ext.endswith("_yes"):
                        is_winner = True
                    elif winning_outcome.lower() == "no" and ext.endswith("_no"):
                        is_winner = True
                    await session.execute(
                        update(FuturesOutcome)
                        .where(FuturesOutcome.id == oid)
                        .values(is_winner=is_winner)
                    )

            stats["resolutions"] += 1
            logger.info("Polymarket WS: %s resolved (winner=%s)", condition_id[:20], winning_outcome)
        except Exception:
            stats["errors"] += 1
            logger.exception("Polymarket WS: resolution error")

    ws.on_price = handle_price
    ws.on_trade = handle_trade
    ws.on_resolved = handle_resolved

    async def flush_loop():
        while True:
            await asyncio.sleep(2)
            await flush_prices()

    async def stats_loop():
        while True:
            await asyncio.sleep(60)
            logger.info(
                "Polymarket WS: %d prices, %d trades, %d resolutions, %d errors, %d msgs",
                stats["price_updates"], stats["trade_updates"],
                stats["resolutions"], stats["errors"],
                ws.stats.get("messages", 0),
            )

    flush_task = asyncio.create_task(flush_loop())
    stats_task = asyncio.create_task(stats_loop())

    try:
        await ws.run(asset_ids=asset_ids)
    except asyncio.CancelledError:
        pass
    finally:
        flush_task.cancel()
        stats_task.cancel()
        await flush_prices()

    logger.info("Polymarket WS consumer exiting: %s", stats)
    return stats
