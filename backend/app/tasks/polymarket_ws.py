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


async def _apply_ws_resolution(session, market_id, outcomes, winning_outcome):
    """Apply a Polymarket ``market_resolved`` settlement to the DB.

    Queue #261 Item 2: sets ``status='resolved'`` on the market and ``is_winner``
    on its outcomes, routed through the resolution-authority contract — and NEVER
    writes ``calibration_probability``. A terminal price must not both define the
    winner AND grade the earlier/current forecast (self-grading leakage, C20/C21);
    the terminal price still reaches ``current_probability`` via the ordinary
    buffered flush loop, and the published forecast is left to the timestamped
    snapshot pipeline. An outcome already settled by an authoritative source
    (tier 3) is left untouched — a bare websocket push must not downgrade it.

    Module-level (not a closure) so the leakage contract is unit-testable.
    Returns the number of outcome winner-writes applied.
    """
    from sqlalchemy import select, update

    from app.models.models import FuturesMarket, FuturesOutcome
    from app.utils.resolution_authority import is_authoritative

    outcome_ids = [oid for oid, _ in outcomes]
    existing_sources: dict = {}
    if outcome_ids:
        existing_sources = {
            r.id: r.resolution_source
            for r in (
                await session.execute(
                    select(
                        FuturesOutcome.id, FuturesOutcome.resolution_source
                    ).where(FuturesOutcome.id.in_(outcome_ids))
                )
            ).all()
        }

    await session.execute(
        update(FuturesMarket)
        .where(FuturesMarket.id == market_id)
        .values(status="resolved")
    )

    written = 0
    for oid, ext in outcomes:
        if is_authoritative(existing_sources.get(oid)):
            continue  # venue already settled authoritatively — leave it
        is_winner = (
            (winning_outcome.lower() == "yes" and ext.endswith("_yes"))
            or (winning_outcome.lower() == "no" and ext.endswith("_no"))
        )
        # Deliberately NOT setting calibration_probability here (Queue #261).
        await session.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.id == oid)
            .values(is_winner=is_winner)
        )
        written += 1
    return written


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
        """Handle market_resolved event.

        Sets status=resolved and is_winner, routed through the resolution-authority
        contract. Queue #261 Item 2: this path NEVER copies the last buffered
        trade into ``calibration_probability`` — a terminal price must not both
        define the winner AND grade the earlier/current forecast (self-grading
        leakage, C20/C21). The terminal price still reaches ``current_probability``
        through the ordinary buffered flush loop, and the published calibration
        forecast is left to the timestamped snapshot pipeline (opening/closing
        lines). An outcome already settled by an authoritative source (tier 3) is
        left untouched — a bare websocket push must not downgrade it.
        """
        condition_id = msg.get("market", "")
        winning_outcome = msg.get("winning_outcome", "")

        market_id = condition_to_market.get(condition_id)
        if not market_id:
            return

        outcomes = outcomes_by_market.get(market_id, [])

        try:
            async with get_task_session() as session:
                written = await _apply_ws_resolution(
                    session, market_id, outcomes, winning_outcome
                )
            stats["resolutions"] += 1
            logger.info(
                "Polymarket WS: %s resolved (winner=%s, %d/%d outcomes written, "
                "no calibration scalar captured)",
                condition_id[:20], winning_outcome, written, len(outcomes),
            )
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


async def _run_polymarket_ws_shadow_consumer():
    """#837 fast-follow (SHADOW): widened resolution-only grader that records
    its verdict to Redis (NEVER is_winner). Subscribes to ALL markets'
    resolution pushes (not the price firehose) so every Polymarket settlement
    is graded in real time — into the shadow store, for the automated
    source-agnostic comparison (`compare_shadow_verdicts`).

    Runs ONLY when the `bainluck:ws_shadow_enabled` flag is on (deploy-dark).
    The authoritative `_run_polymarket_ws_consumer` is untouched and keeps
    owning `is_winner`.
    """
    from app.services.polymarket_ws import PolymarketWebSocket
    from app.services.ws_shadow import (
        is_ws_shadow_enabled,
        verdict_from_polymarket_resolved,
        record_shadow_verdict,
    )

    if not await is_ws_shadow_enabled():
        return {"status": "shadow_disabled"}

    ws = PolymarketWebSocket()
    stats = {"shadow_verdicts": 0, "errors": 0}

    async def handle_resolved_shadow(msg: dict):
        parsed = verdict_from_polymarket_resolved(msg)
        if not parsed:
            return
        # SHADOW ONLY — record BOTH outcome verdicts, keyed by each outcome's
        # external_id ({condition_id}_yes / {condition_id}_no). The comparison
        # joins FuturesOutcome.external_id == key exactly, source-agnostic.
        for ext_id, is_winner in parsed:
            try:
                await record_shadow_verdict(ext_id, is_winner)
                stats["shadow_verdicts"] += 1
            except Exception:
                stats["errors"] += 1

    ws.on_resolved = handle_resolved_shadow
    # resolution-only + all markets: NO asset_ids -> subscribe to all; the
    # service only dispatches market_resolved here (on_price/on_trade unset),
    # so this is the settlement trickle, NOT the price firehose.
    try:
        await ws.run()
    except asyncio.CancelledError:
        pass
    logger.info("Polymarket WS SHADOW consumer exiting: %s", stats)
    return stats
