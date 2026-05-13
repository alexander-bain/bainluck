"""
Backfill is_winner on FuturesOutcome from settlement data.

Risk mitigations:
1. Incremental: only processes markets where is_winner is still default (false) and
   no outcome has is_winner=true. Skips already-backfilled markets.
2. Batched Kalshi fetch: processes 200 events at a time, commits per batch. No
   loading 130K events into memory. Caps at configurable limit per run.
3. Dry-run first: logs what WOULD change without writing, to verify ticker matching.
4. Ticker mismatch logging: tracks not-found tickers so we can see the pattern.
5. Polymarket uses current_probability but only on fully-resolved markets (all
   outcomes at 0 or 1). This IS the settlement price, not an inference.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update, text, func

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)


async def _backfill_kalshi_winners(limit: int = 2000, dry_run: bool = False):
    """Fetch settled Kalshi events and set is_winner on matching outcomes.

    Args:
        limit: Max events to process per run (pagination safety).
        dry_run: If True, log what would change without writing.
    """
    from app.services.kalshi_api import KalshiAPIService
    from app.models import FuturesMarket, FuturesOutcome

    stats = {
        "events_fetched": 0, "events_processed": 0,
        "winners_set": 0, "losers_set": 0, "already_set": 0,
        "not_found": 0, "no_result": 0, "errors": [],
        "sample_not_found": [],
    }

    # First: find which Kalshi markets still need is_winner backfilled.
    # A market needs backfill if it's resolved AND no outcome has is_winner=true.
    async with get_task_session() as session:
        needs_backfill = await session.execute(
            text("""
                SELECT fm.external_id
                FROM futures_markets fm
                WHERE fm.source = 'kalshi'
                  AND fm.status = 'resolved'
                  AND NOT EXISTS (
                      SELECT 1 FROM futures_outcomes fo
                      WHERE fo.market_id = fm.id AND fo.is_winner = true
                  )
                LIMIT :limit
            """),
            {"limit": limit},
        )
        tickers_needing_backfill = {r[0] for r in needs_backfill.all()}

    if not tickers_needing_backfill:
        logger.info("Kalshi winner backfill: no markets need backfill")
        stats["already_set"] = -1  # sentinel: everything already done
        return stats

    logger.info("Kalshi winner backfill: %d markets need backfill", len(tickers_needing_backfill))

    service = KalshiAPIService()
    try:
        cursor = None
        events_remaining = limit

        while events_remaining > 0:
            batch_size = min(200, events_remaining)
            try:
                events, cursor = await service.get_events(
                    status="settled", with_nested_markets=True,
                    limit=batch_size, cursor=cursor,
                )
            except Exception as e:
                stats["errors"].append(f"API fetch error: {e}")
                logger.error("Kalshi API fetch failed: %s", e)
                break

            if not events:
                break

            stats["events_fetched"] += len(events)
            events_remaining -= len(events)

            # Process this batch
            async with get_task_session() as session:
                for event_data in events:
                    event_ticker = event_data.get("event_ticker", "")

                    # Skip events we don't need to backfill
                    if event_ticker not in tickers_needing_backfill:
                        stats["already_set"] += 1
                        continue

                    nested = event_data.get("markets") or []
                    stats["events_processed"] += 1

                    for market_data in nested:
                        ticker = market_data.get("ticker", "")
                        result = market_data.get("result")

                        if not ticker:
                            continue
                        if result is None:
                            stats["no_result"] += 1
                            continue

                        is_winner = result == "yes"

                        if dry_run:
                            # Just check if we'd find a match
                            match = await session.execute(
                                select(func.count()).select_from(FuturesOutcome).where(
                                    FuturesOutcome.external_id == ticker,
                                    FuturesOutcome.market_id.in_(
                                        select(FuturesMarket.id).where(
                                            FuturesMarket.source == "kalshi",
                                            FuturesMarket.external_id == event_ticker,
                                        )
                                    ),
                                )
                            )
                            count = match.scalar()
                            if count > 0:
                                if is_winner:
                                    stats["winners_set"] += count
                                else:
                                    stats["losers_set"] += count
                            else:
                                stats["not_found"] += 1
                                if len(stats["sample_not_found"]) < 20:
                                    stats["sample_not_found"].append({
                                        "event": event_ticker,
                                        "ticker": ticker,
                                        "result": result,
                                    })
                        else:
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
                                if len(stats["sample_not_found"]) < 20:
                                    stats["sample_not_found"].append({
                                        "event": event_ticker,
                                        "ticker": ticker,
                                        "result": result,
                                    })

                    # Mark resolved
                    if not dry_run:
                        await session.execute(
                            update(FuturesMarket)
                            .where(
                                FuturesMarket.source == "kalshi",
                                FuturesMarket.external_id == event_ticker,
                                FuturesMarket.status != "resolved",
                            )
                            .values(status="resolved")
                        )

                # Commit per batch (not per event, not all at once)
                if not dry_run:
                    await session.commit()

            logger.info(
                "Kalshi backfill batch: fetched %d, processed %d so far",
                len(events), stats["events_processed"],
            )

            if not cursor:
                break

    except Exception as e:
        stats["errors"].append(f"Top-level: {str(e)}")
        logger.error("Kalshi winner backfill top-level error: %s", e)
    finally:
        await service.close()

    mode = "DRY RUN" if dry_run else "LIVE"
    logger.info(
        "Kalshi winner backfill [%s]: %d fetched, %d processed, %d winners, "
        "%d losers, %d not_found, %d no_result, %d already_set, %d errors",
        mode, stats["events_fetched"], stats["events_processed"],
        stats["winners_set"], stats["losers_set"],
        stats["not_found"], stats["no_result"],
        stats["already_set"], len(stats["errors"]),
    )
    if stats["sample_not_found"]:
        logger.info("Sample not-found tickers: %s", stats["sample_not_found"][:5])

    return stats


async def _backfill_polymarket_winners():
    """Set is_winner on Polymarket outcomes from settlement prices.

    For resolved Polymarket markets, current_probability IS the settlement
    price (updated to 1.0/0.0 when the market resolves). Only processes
    markets where ALL outcomes have cleanly resolved (near 0 or 1).
    """
    stats = {"winners_set": 0, "losers_set": 0, "errors": []}

    try:
        async with get_task_session() as session:
            # Only process markets where:
            # 1. Market is resolved
            # 2. No outcome already has is_winner=true (skip already-backfilled)
            # 3. All outcomes have current_probability near 0 or 1 (clean resolution)
            result = await session.execute(
                text("""
                    WITH cleanly_resolved AS (
                        SELECT fm.id AS market_id
                        FROM futures_markets fm
                        JOIN futures_outcomes fo ON fo.market_id = fm.id
                        WHERE fm.source = 'polymarket'
                          AND fm.status = 'resolved'
                        GROUP BY fm.id
                        HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                           AND COUNT(*) FILTER (
                               WHERE fo.current_probability >= 0.95
                                  OR fo.current_probability <= 0.05
                           ) = COUNT(*)
                    )
                    UPDATE futures_outcomes fo
                    SET is_winner = (fo.current_probability >= 0.95)
                    FROM cleanly_resolved cr
                    WHERE fo.market_id = cr.market_id
                      AND fo.current_probability IS NOT NULL
                    RETURNING fo.is_winner
                """)
            )
            rows = result.all()
            stats["winners_set"] = sum(1 for r in rows if r[0])
            stats["losers_set"] = sum(1 for r in rows if not r[0])

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Polymarket winner backfill error: %s", e)

    logger.info(
        "Polymarket winner backfill: %d winners, %d losers, %d errors",
        stats["winners_set"], stats["losers_set"], len(stats["errors"]),
    )
    return stats


async def _backfill_from_current_probability():
    """Set is_winner from current_probability for ALL sources.

    For cleanly-resolved markets (all outcomes at 0 or 1), current_probability
    IS the settlement price. Works for Kalshi, Polymarket, DataGolf, odds_api.
    """
    stats = {"winners_set": 0, "losers_set": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    WITH cleanly_resolved AS (
                        SELECT fm.id AS market_id
                        FROM futures_markets fm
                        JOIN futures_outcomes fo ON fo.market_id = fm.id
                        WHERE fm.status = 'resolved'
                        GROUP BY fm.id
                        HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                           AND COUNT(*) FILTER (
                               WHERE fo.current_probability >= 0.95
                                  OR fo.current_probability <= 0.05
                           ) = COUNT(*)
                           AND COUNT(*) >= 1
                    )
                    UPDATE futures_outcomes fo
                    SET is_winner = (fo.current_probability >= 0.95)
                    FROM cleanly_resolved cr
                    WHERE fo.market_id = cr.market_id
                      AND fo.current_probability IS NOT NULL
                    RETURNING fo.is_winner
                """)
            )
            rows = result.all()
            stats["winners_set"] = sum(1 for r in rows if r[0])
            stats["losers_set"] = sum(1 for r in rows if not r[0])
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Current-probability winner backfill error: %s", e)

    logger.info(
        "Current-probability winner backfill: %d winners, %d losers, %d errors",
        stats["winners_set"], stats["losers_set"], len(stats["errors"]),
    )
    return stats


async def _backfill_polymarket_group_ids():
    """Set group_id on Polymarket markets from metadata or external_id.

    Uses data already in the DB — no API calls. Only sets group_id where
    currently NULL. Sub-markets already have group_id from insertion
    (group_type='polymarket_sub_market'), so this only affects parent markets.
    """
    stats = {"updated": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    UPDATE futures_markets
                    SET group_id = 'polymarket:' || COALESCE(
                        market_metadata->>'polymarket_event_id',
                        external_id
                    )
                    WHERE source = 'polymarket'
                      AND group_id IS NULL
                """)
            )
            stats["updated"] = result.rowcount
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Polymarket group_id backfill error: %s", e)

    logger.info(
        "Polymarket group_id backfill: %d markets updated, %d errors",
        stats["updated"], len(stats["errors"]),
    )
    return stats


async def _backfill_kalshi_group_ids():
    """Set group_id on Kalshi markets from external_id (= event_ticker)."""
    stats = {"updated": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    UPDATE futures_markets
                    SET group_id = 'kalshi:' || external_id
                    WHERE source = 'kalshi'
                      AND group_id IS NULL
                """)
            )
            stats["updated"] = result.rowcount
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Kalshi group_id backfill error: %s", e)

    logger.info(
        "Kalshi group_id backfill: %d markets updated, %d errors",
        stats["updated"], len(stats["errors"]),
    )
    return stats


async def _backfill_all_winners(dry_run: bool = False, limit: int = 2000):
    """Run all winner backfill tasks."""
    # Phase 0a: Backfill Polymarket group_id (no API, fast)
    group_stats = await _backfill_polymarket_group_ids()

    # Phase 0b: Backfill Kalshi group_id (no API, fast)
    kalshi_group_stats = await _backfill_kalshi_group_ids()

    # Phase 0c: Pre-compute closing lines on events (no API, uses odds_snapshots)
    closing_stats = await _backfill_closing_lines()

    # Phase 0d: Fix bad Kalshi opening prices from snapshot data
    opening_fix_stats = await _fix_kalshi_opening_prices()

    # Phase 1: Set is_winner from current_probability (all sources, fast)
    prob_stats = await _backfill_from_current_probability()

    # Phase 2: Kalshi API settlement data (fills in markets that didn't
    # fully resolve their probabilities)
    kalshi_stats = await _backfill_kalshi_winners(limit=limit, dry_run=dry_run)

    return {
        "polymarket_group_id": group_stats,
        "kalshi_group_id": kalshi_group_stats,
        "closing_lines": closing_stats,
        "fix_kalshi_openings": opening_fix_stats,
        "from_probability": prob_stats,
        "kalshi_api": kalshi_stats,
    }


async def _fix_kalshi_opening_prices():
    """Fix bad Kalshi opening_probability from placeholder bid-ask spreads.

    For Kalshi outcomes with futures_odds_snapshots, replaces
    opening_probability with the earliest snapshot that has real trading
    (yes_bid > 0 and spread < 50pp). Only updates outcomes where the
    current opening_probability differs from the corrected value by >5pp.
    """
    stats = {"fixed": 0, "checked": 0, "errors": []}

    try:
        async with get_task_session() as session:
            # Step 1: Find Kalshi outcomes that might have bad opening prices
            # (resolved markets where opening_probability was set)
            bad_candidates = await session.execute(
                text("""
                    SELECT fo.id, fo.opening_probability
                    FROM futures_outcomes fo
                    JOIN futures_markets fm ON fm.id = fo.market_id
                    WHERE fm.source = 'kalshi'
                      AND fm.status = 'resolved'
                      AND fo.opening_probability IS NOT NULL
                      AND fo.opening_probability > 0
                    LIMIT 2000
                """)
            )
            candidates = bad_candidates.all()
            stats["checked"] = len(candidates)

            # Step 2: For each candidate, find a better price from snapshots
            for outcome_id, opening_prob in candidates:
                better = await session.execute(
                    text("""
                        SELECT probability
                        FROM futures_odds_snapshots
                        WHERE outcome_id = :oid
                          AND yes_bid IS NOT NULL AND yes_bid > 0
                          AND yes_ask IS NOT NULL
                          AND (yes_ask - yes_bid) < 0.50
                          AND probability > 0 AND probability < 1
                          AND ABS(probability - :opening) > 0.05
                        ORDER BY captured_at ASC
                        LIMIT 1
                    """),
                    {"oid": outcome_id, "opening": float(opening_prob)},
                )
                row = better.first()
                if row:
                    await session.execute(
                        text("""
                            UPDATE futures_outcomes
                            SET opening_probability = :new_prob
                            WHERE id = :oid
                        """),
                        {"new_prob": float(row[0]), "oid": outcome_id},
                    )
                    stats["fixed"] += 1

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Fix Kalshi opening prices error: %s", e)

    logger.info(
        "Fix Kalshi opening prices: %d outcomes corrected, %d errors",
        stats["fixed"], len(stats["errors"]),
    )
    return stats


async def _backfill_closing_lines():
    """Pre-compute closing line probabilities on completed events.

    For each completed event that has odds_snapshots before commence_time,
    finds the last snapshot and stores it as closing_home/away_probability.
    Runs in batches to stay within Celery time limits.
    """
    stats = {"updated": 0, "errors": []}

    try:
        async with get_task_session() as session:
            # Only process events that don't already have closing_home_probability
            # and have both commence_time and scores. Process in batches of 500.
            result = await session.execute(
                text("""
                    WITH events_needing_closing AS (
                        SELECT e.id, e.commence_time
                        FROM events e
                        WHERE e.status = 'completed'
                          AND e.closing_home_probability IS NULL
                          AND e.commence_time IS NOT NULL
                          AND e.home_score IS NOT NULL
                          AND e.away_score IS NOT NULL
                        LIMIT 5000
                    ),
                    closing AS (
                        SELECT DISTINCT ON (enc.id)
                            enc.id AS event_id,
                            os.home_win_probability
                        FROM events_needing_closing enc
                        JOIN odds_snapshots os ON os.event_id = enc.id
                        WHERE os.captured_at < enc.commence_time
                          AND os.home_win_probability IS NOT NULL
                          AND os.home_win_probability > 0
                          AND os.home_win_probability < 1
                        ORDER BY enc.id, os.captured_at DESC
                    )
                    UPDATE events e
                    SET closing_home_probability = cl.home_win_probability,
                        closing_away_probability = 1.0 - cl.home_win_probability
                    FROM closing cl
                    WHERE e.id = cl.event_id
                """)
            )
            stats["updated"] = result.rowcount
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Closing line backfill error: %s", e)

    logger.info(
        "Closing line backfill: %d events updated, %d errors",
        stats["updated"], len(stats["errors"]),
    )
    return stats
