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


async def _null_untradeable_openings():
    """Null out opening_probability on outcomes with no snapshot data.

    If an outcome has zero futures_odds_snapshots, it was created but
    never actively tracked — its opening_probability is a placeholder,
    not a real market signal. Setting it to NULL excludes it from
    calibration via the existing IS NOT NULL filter.
    """
    stats = {"nulled": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    UPDATE futures_outcomes fo
                    SET opening_probability = NULL
                    WHERE fo.opening_probability IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM futures_odds_snapshots fos
                          WHERE fos.outcome_id = fo.id
                      )
                      AND fo.id IN (
                          SELECT fo2.id
                          FROM futures_outcomes fo2
                          JOIN futures_markets fm ON fm.id = fo2.market_id
                          WHERE fm.status = 'resolved'
                            AND fo2.opening_probability IS NOT NULL
                          LIMIT 10000
                      )
                """)
            )
            stats["nulled"] = result.rowcount
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Null untradeable openings error: %s", e)

    logger.info(
        "Null untradeable openings: %d outcomes nulled, %d errors",
        stats["nulled"], len(stats["errors"]),
    )
    return stats


async def _backfill_polymarket_group_ids_from_api():
    """Fetch resolved Polymarket events from Gamma API to fix group_id.

    For events with 2+ markets, sets the same group_id on all matching
    FuturesMarket rows. This catches multi-outcome events where each
    candidate is a separate Polymarket event that our DB-only backfill
    can't group.
    """
    import asyncio
    from app.services.polymarket_api import PolymarketAPIService

    stats = {"events_fetched": 0, "events_with_markets": 0,
             "markets_updated": 0, "zero_update_pages": 0, "errors": []}

    service = PolymarketAPIService()
    try:
        offset = 0
        max_events = 200000

        while stats["events_fetched"] < max_events:
            try:
                events_data = await service.get_events(
                    active=False, closed=True,
                    limit=100, offset=offset,
                )
            except Exception as e:
                stats["errors"].append(f"API page {offset}: {e}")
                break

            if not events_data:
                break

            stats["events_fetched"] += len(events_data)

            page_updates = 0
            async with get_task_session() as session:
                for event_data in events_data:
                    event_id = str(event_data.get("id", ""))
                    markets = event_data.get("markets") or []

                    if not event_id or len(markets) < 2:
                        continue

                    stats["events_with_markets"] += 1
                    group_id = f"polymarket:{event_id}"

                    match_ids = [event_id]
                    for m in markets:
                        cid = m.get("conditionId") or m.get("condition_id")
                        if cid:
                            match_ids.append(str(cid))

                    result = await session.execute(
                        text("""
                            UPDATE futures_markets
                            SET group_id = :group_id
                            WHERE source = 'polymarket'
                              AND external_id = ANY(:ids)
                              AND (group_id IS NULL OR group_id != :group_id)
                        """),
                        {"group_id": group_id, "ids": match_ids},
                    )
                    page_updates += result.rowcount
                    stats["markets_updated"] += result.rowcount

                await session.commit()

            offset += len(events_data)
            if len(events_data) < 100:
                break

            if page_updates == 0:
                stats["zero_update_pages"] += 1
                if stats["zero_update_pages"] >= 50:
                    break
            else:
                stats["zero_update_pages"] = 0

            await asyncio.sleep(0.3)

    except Exception as e:
        stats["errors"].append(f"Top-level: {e}")
        logger.error("Polymarket API group_id backfill error: %s", e)
    finally:
        await service.close()

    logger.info(
        "Polymarket API group_id backfill: %d events fetched, %d with 2+ markets, "
        "%d markets updated, %d errors",
        stats["events_fetched"], stats["events_with_markets"],
        stats["markets_updated"], len(stats["errors"]),
    )
    return stats


async def _backfill_all_winners(dry_run: bool = False, limit: int = 2000):
    """Run all winner backfill tasks."""
    # Phase 0a: Backfill Polymarket group_id (no API, fast)
    group_stats = await _backfill_polymarket_group_ids()

    # Phase 0b: Backfill Kalshi group_id (no API, fast)
    kalshi_group_stats = await _backfill_kalshi_group_ids()

    # Phase 0c: Null out opening_probability on outcomes with no snapshots
    # (placeholder prices with no trading activity — not real predictions)
    no_snap_stats = await _null_untradeable_openings()

    # Phase 0d: Pre-compute closing lines on events (no API, uses odds_snapshots)
    closing_stats = await _backfill_closing_lines()

    # Phase 0e: Pre-compute calibration_probability (closing line or settled price)
    cal_price_stats = await _compute_calibration_prices()

    # Phase 0f: Backfill group_id from Polymarket Gamma API (resolved events)
    api_group_stats = await _backfill_polymarket_group_ids_from_api()

    # Phase 1: Set is_winner from current_probability (all sources, fast)
    prob_stats = await _backfill_from_current_probability()

    # Phase 2: Kalshi API settlement data (fills in markets that didn't
    # fully resolve their probabilities)
    kalshi_stats = await _backfill_kalshi_winners(limit=limit, dry_run=dry_run)

    return {
        "polymarket_group_id": group_stats,
        "kalshi_group_id": kalshi_group_stats,
        "null_untradeable": no_snap_stats,
        "closing_lines": closing_stats,
        "calibration_prices": cal_price_stats,
        "polymarket_api_group_id": api_group_stats,
        "from_probability": prob_stats,
        "kalshi_api": kalshi_stats,
    }


async def _compute_calibration_prices():
    """Pre-compute calibration_probability on resolved outcomes.

    Uses the RIGHT price for calibration based on market type:
    - Markets WITH commence_time: last snapshot before event starts (closing line)
    - Markets WITHOUT commence_time: first snapshot ≥1h after opening (settled price)
    - Fallback: opening_probability

    Only processes outcomes where calibration_probability is NULL.
    Uses compound index (outcome_id, captured_at) for fast DISTINCT ON.
    """
    stats = {"with_commence": 0, "without_commence": 0, "fallback": 0, "errors": []}

    try:
        async with get_task_session() as session:
            # Part A: Markets WITH commence_time
            # Uses closing line (last snapshot before event start) when available,
            # falls back to opening_probability to avoid poison rows blocking batches
            result_a = await session.execute(
                text("""
                    WITH needs_cal AS (
                        SELECT fo.id AS outcome_id, fm.commence_time,
                               fo.opening_probability
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fm.id = fo.market_id
                        WHERE fm.status = 'resolved'
                          AND fo.calibration_probability IS NULL
                          AND fm.commence_time IS NOT NULL
                        LIMIT 200000
                    ),
                    closing AS (
                        SELECT DISTINCT ON (nc.outcome_id)
                            nc.outcome_id,
                            fos.probability
                        FROM needs_cal nc
                        JOIN futures_odds_snapshots fos ON fos.outcome_id = nc.outcome_id
                        WHERE fos.captured_at < nc.commence_time
                          AND fos.probability > 0 AND fos.probability < 1
                        ORDER BY nc.outcome_id, fos.captured_at DESC
                    ),
                    final_price AS (
                        SELECT nc.outcome_id,
                               COALESCE(cl.probability, nc.opening_probability) AS cal_prob
                        FROM needs_cal nc
                        LEFT JOIN closing cl ON cl.outcome_id = nc.outcome_id
                    )
                    UPDATE futures_outcomes fo
                    SET calibration_probability = fp.cal_prob
                    FROM final_price fp
                    WHERE fo.id = fp.outcome_id
                      AND fp.cal_prob IS NOT NULL
                """)
            )
            stats["with_commence"] = result_a.rowcount

            # Part B: Markets WITHOUT commence_time
            # Uses settled price (first snapshot >=1h after opening),
            # falls back to opening_probability
            result_b = await session.execute(
                text("""
                    WITH needs_cal AS (
                        SELECT fo.id AS outcome_id, fo.opening_captured_at,
                               fo.opening_probability
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fm.id = fo.market_id
                        WHERE fm.status = 'resolved'
                          AND fo.calibration_probability IS NULL
                          AND fm.commence_time IS NULL
                        LIMIT 200000
                    ),
                    settled AS (
                        SELECT DISTINCT ON (nc.outcome_id)
                            nc.outcome_id,
                            fos.probability
                        FROM needs_cal nc
                        JOIN futures_odds_snapshots fos ON fos.outcome_id = nc.outcome_id
                        WHERE nc.opening_captured_at IS NOT NULL
                          AND fos.captured_at >= nc.opening_captured_at + INTERVAL '1 hour'
                          AND fos.probability > 0 AND fos.probability < 1
                        ORDER BY nc.outcome_id, fos.captured_at ASC
                    ),
                    final_price AS (
                        SELECT nc.outcome_id,
                               COALESCE(st.probability, nc.opening_probability) AS cal_prob
                        FROM needs_cal nc
                        LEFT JOIN settled st ON st.outcome_id = nc.outcome_id
                    )
                    UPDATE futures_outcomes fo
                    SET calibration_probability = fp.cal_prob
                    FROM final_price fp
                    WHERE fo.id = fp.outcome_id
                      AND fp.cal_prob IS NOT NULL
                """)
            )
            stats["without_commence"] = result_b.rowcount

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Compute calibration prices error: %s", e)

    logger.info(
        "Calibration prices: %d with commence_time, %d without, %d fallback, %d errors",
        stats["with_commence"], stats["without_commence"],
        stats["fallback"], len(stats["errors"]),
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
