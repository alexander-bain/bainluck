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

from app.tasks.kalshi_ws import SUBSCRIPTION_REFRESH_SECONDS
from app.tasks.polymarket import _poly_book_is_untradeable

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

    Queue #284 Item 1: every applied winner write stamps its registered tier-3
    ``resolution_source`` (``clob_authoritative``) in the SAME UPDATE — winner and
    provenance are atomic, so a failed/partial write can never leave a graded
    outcome with a NULL source (which the authority ladder treats as tier -1,
    silently overwritable by a later guess).

    Module-level (not a closure) so the leakage contract is unit-testable.
    Returns the number of outcome winner-writes applied.
    """
    from sqlalchemy import select, update

    from app.models.models import FuturesMarket, FuturesOutcome
    from app.utils.resolution_authority import is_authoritative

    # A CLOB `market_resolved` push is the venue's own settlement delivered over
    # the socket — the same authority as the CLOB REST resolver
    # (`clob_resolve.py`). Stamp its registered tier-3 source so the winner write
    # carries audit-grade provenance, survives the authority ladder (a later
    # guess-family pass can no longer silently overwrite a NULL-source winner),
    # and is calibration-truth eligible. Do NOT invent a new source string.
    _WS_RESOLUTION_SOURCE = "clob_authoritative"

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
        # Winner AND provenance in the SAME statement (Queue #284 Item 1): an
        # atomic write means a failed/partial apply can never leave is_winner set
        # with a NULL resolution_source. Deliberately NOT setting
        # calibration_probability here (Queue #261) — no price self-grading.
        await session.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.id == oid)
            .values(is_winner=is_winner, resolution_source=_WS_RESOLUTION_SOURCE)
        )
        written += 1
    return written


async def _run_polymarket_ws_consumer():
    """Main Polymarket WebSocket consumer loop."""
    from sqlalchemy import select, update, text, or_, and_, func

    from app.models.models import (
        Event, FuturesMarket, FuturesOutcome,
    )
    from app.services.polymarket_ws import PolymarketWebSocket
    from app.tasks.base import get_task_session
    from app.tasks.live_blend_refresh import (
        LiveBlendRefresher, event_ids_for_outcomes,
    )
    from app.utils.price_change_stamp import price_changed_at_value

    ws = PolymarketWebSocket()

    # Load linked Polymarket market asset IDs
    async with get_task_session() as session:
        result = await session.execute(
            select(
                FuturesOutcome.id,
                FuturesOutcome.market_id,
                FuturesOutcome.external_id,
                FuturesMarket.external_id.label("market_ext_id"),
                FuturesMarket.event_id.label("linked_event_id"),
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
    # Q460: linked event per market, so a flushed price can re-stamp the blend.
    event_id_by_market: dict[int, int] = {}
    for outcome_id, market_id, ext_id, market_ext_id, linked_event_id in rows:
        if ext_id:
            condition_to_ids[ext_id] = (market_id, outcome_id)
        market_ids.add(market_id)
        if linked_event_id is not None:
            event_id_by_market[market_id] = linked_event_id

    # Load clob_token_ids from market_metadata
    asset_ids: list[str] = []
    asset_to_outcome: dict[str, int] = {}  # asset_id → outcome_id
    asset_to_market: dict[str, int] = {}   # asset_id → market_id
    condition_to_market: dict[str, int] = {}  # condition_id → market_id

    tokens_by_market: dict[int, list[str]] = {}

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
            tokens_by_market[mid] = [str(t) for t in tokens]

        outcome_result = await session.execute(
            select(FuturesOutcome.id, FuturesOutcome.market_id, FuturesOutcome.external_id)
            .where(FuturesOutcome.market_id.in_(list(market_ids)))
            .order_by(FuturesOutcome.id)
        )
        outcomes_by_market: dict[int, list[tuple[int, str]]] = {}
        for oid, mid, ext in outcome_result.all():
            outcomes_by_market.setdefault(mid, []).append((oid, ext or ""))

    # Q489 — WHICH outcome an asset id belongs to. Both CLOB tokens of a binary
    # (`clobTokenIds == [yesToken, noToken]`) map to the same FuturesMarket, and
    # the price handlers used to resolve every tick to `outcomes[0]` — the
    # Over/Yes leg — because this map was declared and never filled. A No-token
    # `best_bid_ask` therefore wrote P(No) into the Yes outcome, and since both
    # legs stream continuously the rendered number would oscillate between p and
    # 1-p on every tick. That is strictly worse than a stale price: a stale card
    # is wrong once, an inverted card is wrong at random.
    #
    # The pairing is positional and both sides are already ordered the same way:
    # Gamma serves `[yes, no]`, and the ingest inserts the Over/Yes outcome
    # before the Under/No one (`polymarket.py`, the sub-market loop), so ordering
    # by `FuturesOutcome.id` reproduces the token order. `zip` is deliberate — a
    # market whose outcome count disagrees with its token count maps only the
    # pairs it can prove and leaves the rest unmapped, so a shape we did not
    # anticipate drops ticks instead of writing them to the wrong leg.
    for mid, mtokens in tokens_by_market.items():
        for token, (oid, _ext) in zip(mtokens, outcomes_by_market.get(mid, [])):
            asset_to_outcome[token] = oid

    unmapped_assets = [a for a in asset_ids if a not in asset_to_outcome]

    if not asset_ids:
        logger.info("Polymarket WS: no asset IDs found in market_metadata")
        return {"status": "no_asset_ids"}

    logger.info(
        "Polymarket WS: %d asset IDs (%d markets), %d mapped to an outcome, "
        "%d unmapped (ticks dropped rather than mis-attributed)",
        len(asset_ids), len(market_ids),
        len(asset_to_outcome), len(unmapped_assets),
    )

    stats = {
        "assets_subscribed": len(asset_ids),
        # Q489: the number that says whether a tick can land on the right leg.
        # `assets_subscribed` counts what we listen to; this counts what we can
        # actually attribute, and the gap between them is the silent-loss bound.
        "assets_mapped": len(asset_to_outcome),
        "assets_unmapped": len(unmapped_assets),
        "price_updates": 0,
        "trade_updates": 0,
        "resolutions": 0,
        "errors": 0,
    }

    # Buffered price updates
    price_buffer: dict[int, float] = {}
    buffer_lock = asyncio.Lock()
    # Q460: outcome → linked event, for the blend re-stamp after each flush.
    event_id_by_outcome: dict[int, int] = {
        outcome_id: event_id_by_market[market_id]
        for market_id, outcome_id in condition_to_ids.values()
        if market_id in event_id_by_market
    }
    blend_refresher = LiveBlendRefresher("polymarket")

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
                        .values(
                            current_probability=prob,
                            # Same contract as every other price writer (#2024):
                            # a live socket owes the touch-stamp AND the
                            # change-stamp, or downstream liveness gates read a
                            # streaming row as long dead.
                            last_updated=func.now(),
                            price_changed_at=price_changed_at_value(
                                FuturesOutcome.current_probability,
                                FuturesOutcome.price_changed_at,
                                prob,
                            ),
                        )
                    )
            stats["price_updates"] += len(batch)
        except Exception:
            stats["errors"] += 1
            logger.exception("Polymarket WS: flush error")
            return

        # Q460 — THE SHIP. Carry the freshly-flushed prices through to
        # `Event.win_probability_sources`, the JSONB the card actually renders.
        await blend_refresher.refresh(
            event_ids_for_outcomes(event_id_by_outcome, batch.keys())
        )

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
            bid_f = float(best_bid)
            ask_f = float(best_ask)
        except (ValueError, TypeError):
            return

        # #1578: never stream a midpoint from a book nobody will trade inside.
        # This path matters most of the five, because it is the only one that
        # UPDATEs an outcome directly rather than going through the upsert — a
        # wide quote arriving here would overwrite a good stored price with a
        # phantom. Returning early leaves the existing value untouched; the
        # real-trade stream (handle_trade, below) is what moves an illiquid
        # market's price, which is correct.
        if _poly_book_is_untradeable(bid_f, ask_f):
            return

        prob = (bid_f + ask_f) / 2
        if prob <= 0 or prob >= 1:
            return

        # Q489: the outcome this ASSET is the book for — not "the market's first
        # outcome". `prob` here is the midpoint of THIS token's own book, so on
        # the No token it is P(No), which belongs on the No leg and nowhere else.
        outcome_id = asset_to_outcome.get(asset_id)
        if outcome_id is None:
            return

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

        # Q489: same contract as `handle_price` — a `last_trade_price` is a trade
        # in THIS token, so it grades THIS token's leg.
        outcome_id = asset_to_outcome.get(asset_id)
        if outcome_id is None:
            return

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
        # Q460: recycle on a timer so the slate is re-read — same reasoning as
        # `kalshi_ws.SUBSCRIPTION_REFRESH_SECONDS`, and the same constant, so the
        # two sockets on this dyno cannot drift to different coverage windows.
        await asyncio.wait_for(
            ws.run(asset_ids=asset_ids),
            timeout=SUBSCRIPTION_REFRESH_SECONDS,
        )
    except asyncio.TimeoutError:
        stats["status"] = "resubscribe"
    except asyncio.CancelledError:
        # Real shutdown, not the planned recycle (CERT-491) — keep it travelling
        # so the runner stops instead of relaunching. Buffer still drains below.
        raise
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
        raise  # shutdown must stop the runner, not restart it (CERT-491)
    logger.info("Polymarket WS SHADOW consumer exiting: %s", stats)
    return stats
