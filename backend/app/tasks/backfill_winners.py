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
import re
from datetime import datetime, timezone

from sqlalchemy import select, update, text, func

from app.models import FuturesMarket, FuturesOutcome
from app.tasks.base import get_task_session
from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES_SQL,
    GUESS_FAMILY_SOURCES_SQL,
    OVERWRITABLE_WINNER_SOURCES_SQL,
    SINGLE_WINNER_GUESS_SOURCES_SQL,
)

logger = logging.getLogger(__name__)


async def _backfill_kalshi_winners(limit: int = 2000, dry_run: bool = False):
    """Fetch settled Kalshi events by ticker and set is_winner from settlement data.

    Uses targeted GET /events/{ticker} lookups instead of paginating all settled
    events. Much more efficient — O(markets needing backfill) not O(all settled).
    """
    import asyncio
    from app.services.kalshi_api import KalshiAPIService

    stats = {
        "tickers_queried": 0,
        "events_found": 0,
        "winners_set": 0,
        "losers_set": 0,
        "not_found": 0,
        "no_result": 0,
        "api_miss": 0,
        "errors": [],
    }

    from app.tasks.redis_state import get_redis_client

    _rc = get_redis_client()
    _cursor_key = "bainluck:kalshi_winner_backfill_cursor"
    _raw = _rc.get(_cursor_key)
    _last_cursor = _raw.decode() if isinstance(_raw, bytes) else (_raw or "")

    async with get_task_session() as session:
        needs_backfill = await session.execute(
            text("""
                SELECT fm.external_id
                FROM futures_markets fm
                WHERE fm.source = 'kalshi'
                  AND fm.status = 'resolved'
                  AND fm.external_id > :cursor
                  AND EXISTS (
                      SELECT 1 FROM futures_outcomes fo
                      WHERE fo.market_id = fm.id
                        AND COALESCE(fo.resolution_source, '') NOT IN """ + AUTHORITATIVE_SOURCES_SQL + """
                  )
                GROUP BY fm.external_id
                ORDER BY fm.external_id ASC
                LIMIT :limit
            """),
            {"limit": limit, "cursor": _last_cursor},
        )
        tickers = [r[0] for r in needs_backfill.all()]

    if tickers:
        _rc.setex(_cursor_key, 86400 * 14, tickers[-1])
    elif _last_cursor:
        _rc.delete(_cursor_key)
        logger.info("Kalshi winner backfill: cursor wrapped, will restart next run")

    if not tickers:
        logger.info("Kalshi winner backfill: nothing to do")
        return stats

    logger.info("Kalshi winner backfill: %d tickers to look up", len(tickers))

    service = KalshiAPIService()
    try:
        sem = asyncio.Semaphore(5)

        async def _fetch(ticker):
            async with sem:
                return ticker, await service.get_event(ticker)

        batch_size = 100
        for batch_start in range(0, len(tickers), batch_size):
            batch = tickers[batch_start : batch_start + batch_size]
            results = await asyncio.gather(*[_fetch(t) for t in batch])

            async with get_task_session() as session:
                for event_ticker, event_data in results:
                    stats["tickers_queried"] += 1

                    if not event_data:
                        stats["api_miss"] += 1
                        continue

                    stats["events_found"] += 1
                    nested = event_data.get("markets") or []

                    if not nested:
                        stats.setdefault("no_markets", 0)
                        stats["no_markets"] += 1

                    api_tickers = {
                        m.get("ticker", "") for m in nested if m.get("ticker")
                    }
                    db_result = await session.execute(
                        text("""
                            SELECT fo.external_id, fo.resolution_source
                            FROM futures_outcomes fo
                            JOIN futures_markets fm ON fo.market_id = fm.id
                            WHERE fm.source = 'kalshi'
                              AND fm.external_id = :event_ticker
                              AND COALESCE(fo.resolution_source, '') NOT IN """ + AUTHORITATIVE_SOURCES_SQL + """
                            LIMIT 5
                        """),
                        {"event_ticker": event_ticker},
                    )
                    unresolved = db_result.all()
                    if unresolved:
                        for ur in unresolved:
                            if ur[0] not in api_tickers:
                                mismatches = stats.setdefault("ticker_mismatches", [])
                                if len(mismatches) < 10:
                                    mismatches.append(
                                        {
                                            "event_ticker": event_ticker,
                                            "db_outcome_ext_id": ur[0],
                                            "db_resolution_source": ur[1],
                                            "api_tickers": list(api_tickers)[:3],
                                        }
                                    )

                    # For events with no API markets, try to resolve from
                    # current_probability directly (the data is in our DB)
                    if not nested:
                        resolve_r = await session.execute(
                            text("""
                                WITH market_check AS (
                                    SELECT fm.id AS market_id
                                    FROM futures_markets fm
                                    JOIN futures_outcomes fo ON fo.market_id = fm.id
                                    WHERE fm.source = 'kalshi'
                                      AND fm.external_id = :event_ticker
                                      AND fm.status = 'resolved'
                                    GROUP BY fm.id
                                    HAVING SUM(CASE WHEN fo.is_winner
                                               AND fo.resolution_source NOT IN
                                                   """ + OVERWRITABLE_WINNER_SOURCES_SQL + """
                                               THEN 1 ELSE 0 END) = 0
                                       AND COUNT(*) FILTER (
                                           WHERE fo.current_probability >= 0.95
                                              OR fo.current_probability <= 0.05
                                       ) = COUNT(*)
                                       AND COUNT(*) >= 1
                                )
                                UPDATE futures_outcomes fo
                                SET is_winner = (fo.current_probability >= 0.95),
                                    resolution_source = 'clean_resolution',
                                    last_updated = NOW()
                                FROM market_check mc
                                WHERE fo.market_id = mc.market_id
                                  AND fo.current_probability IS NOT NULL
                                RETURNING fo.is_winner
                            """),
                            {"event_ticker": event_ticker},
                        )
                        fallback_rows = resolve_r.all()
                        for r in fallback_rows:
                            if r[0]:
                                stats["winners_set"] += 1
                            else:
                                stats["losers_set"] += 1

                    for market_data in nested:
                        ticker = market_data.get("ticker", "")
                        result = market_data.get("result")

                        if not ticker:
                            continue
                        if result is None:
                            stats["no_result"] += 1
                            continue

                        is_winner = result == "yes"

                        if not dry_run:
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
                                .values(
                                    is_winner=is_winner,
                                    resolution_source="api_settlement",
                                    last_updated=func.now(),
                                )
                            )
                            if updated.rowcount > 0:
                                if is_winner:
                                    stats["winners_set"] += updated.rowcount
                                else:
                                    stats["losers_set"] += updated.rowcount
                            else:
                                stats["not_found"] += 1
                                samples = stats.setdefault("not_found_samples", [])
                                if len(samples) < 5:
                                    samples.append(
                                        {
                                            "event_ticker": event_ticker,
                                            "market_ticker": ticker,
                                            "result": result,
                                        }
                                    )

                if not dry_run:
                    await session.commit()

            logger.info(
                "Kalshi backfill: %d/%d tickers, %d found, %d winners, %d losers",
                min(batch_start + batch_size, len(tickers)),
                len(tickers),
                stats["events_found"],
                stats["winners_set"],
                stats["losers_set"],
            )

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Kalshi winner backfill error: %s", e)
    finally:
        await service.close()

    logger.info(
        "Kalshi winner backfill: %d queried, %d found, %d api_miss, "
        "%d winners, %d losers, %d not_found, %d errors",
        stats["tickers_queried"],
        stats["events_found"],
        stats["api_miss"],
        stats["winners_set"],
        stats["losers_set"],
        stats["not_found"],
        len(stats["errors"]),
    )
    return stats


async def _backfill_kalshi_winners_targeted(limit: int = 2000):
    """Resolve Kalshi outcomes by looking up SPECIFIC event tickers that need work.

    Instead of paginating ALL settled markets (millions of pages), queries
    the DB for event tickers with pass2_guess outcomes, then looks up each
    via GET /markets?event_ticker=X&status=settled to get the result field.
    O(events needing work) not O(all settled events).
    """
    import asyncio
    from app.services.kalshi_api import KalshiAPIService
    from app.tasks.redis_state import get_redis_client

    _rc = get_redis_client()
    _cursor_key = "bainluck:kalshi_targeted_cursor"
    _raw = _rc.get(_cursor_key)
    _last_cursor = _raw.decode() if isinstance(_raw, bytes) else (_raw or "")

    stats = {
        "tickers_queried": 0,
        "markets_found": 0,
        "winners_set": 0,
        "losers_set": 0,
        "api_empty": 0,
        "errors": [],
    }

    async with get_task_session() as session:
        result = await session.execute(
            text("""
                SELECT DISTINCT fm.external_id
                FROM futures_markets fm
                JOIN futures_outcomes fo ON fo.market_id = fm.id
                WHERE fm.source = 'kalshi'
                  AND fm.status = 'resolved'
                  AND fm.external_id > :cursor
                  AND fo.resolution_source IN """ + OVERWRITABLE_WINNER_SOURCES_SQL + """
                ORDER BY fm.external_id ASC
                LIMIT :limit
            """),
            {"cursor": _last_cursor, "limit": limit},
        )
        event_tickers = [r[0] for r in result.all()]

    if not event_tickers:
        if _last_cursor:
            _rc.delete(_cursor_key)
            logger.info("Kalshi targeted backfill: cursor wrapped")
        return stats

    _rc.setex(_cursor_key, 86400 * 14, event_tickers[-1])
    logger.info(
        "Kalshi targeted backfill: %d event tickers to look up", len(event_tickers)
    )

    service = KalshiAPIService()
    try:
        sem = asyncio.Semaphore(5)

        async def _fetch_markets(event_ticker):
            async with sem:
                try:
                    markets, _ = await service.get_markets(
                        status="settled",
                        event_ticker=event_ticker,
                        limit=100,
                    )
                    return event_ticker, markets
                except Exception:
                    return event_ticker, []

        batch_size = 100
        for batch_start in range(0, len(event_tickers), batch_size):
            batch = event_tickers[batch_start : batch_start + batch_size]
            results = await asyncio.gather(*[_fetch_markets(t) for t in batch])

            yes_tickers = []
            no_tickers = []
            for event_ticker, markets in results:
                stats["tickers_queried"] += 1
                if not markets:
                    stats["api_empty"] += 1
                    continue
                stats["markets_found"] += len(markets)
                for mkt in markets:
                    ticker = mkt.get("ticker", "")
                    result_val = mkt.get("result")
                    if not ticker or result_val is None:
                        continue
                    if result_val == "yes":
                        yes_tickers.append(ticker)
                    else:
                        no_tickers.append(ticker)

            if yes_tickers or no_tickers:
                async with get_task_session() as session:
                    if yes_tickers:
                        r = await session.execute(
                            text("""
                                UPDATE futures_outcomes fo
                                SET is_winner = true, resolution_source = 'api_settlement', last_updated = NOW()
                                FROM futures_markets fm
                                WHERE fo.market_id = fm.id
                                  AND fm.source = 'kalshi'
                                  AND fo.external_id = ANY(:tickers)
                                  AND COALESCE(fo.resolution_source, '') NOT IN """ + AUTHORITATIVE_SOURCES_SQL + """
                            """),
                            {"tickers": yes_tickers},
                        )
                        stats["winners_set"] += r.rowcount
                    if no_tickers:
                        r = await session.execute(
                            text("""
                                UPDATE futures_outcomes fo
                                SET is_winner = false, resolution_source = 'api_settlement', last_updated = NOW()
                                FROM futures_markets fm
                                WHERE fo.market_id = fm.id
                                  AND fm.source = 'kalshi'
                                  AND fo.external_id = ANY(:tickers)
                                  AND COALESCE(fo.resolution_source, '') NOT IN """ + AUTHORITATIVE_SOURCES_SQL + """
                            """),
                            {"tickers": no_tickers},
                        )
                        stats["losers_set"] += r.rowcount
                    await session.commit()

            logger.info(
                "Kalshi targeted: %d/%d tickers, %d markets, %d winners, %d losers, %d empty",
                min(batch_start + batch_size, len(event_tickers)),
                len(event_tickers),
                stats["markets_found"],
                stats["winners_set"],
                stats["losers_set"],
                stats["api_empty"],
            )
    except Exception as e:
        stats["errors"].append(str(e)[:200])
    finally:
        await service.close()

    return stats


async def _backfill_kalshi_winners_via_markets(limit: int = 10000):
    """Resolve Kalshi outcomes by paginating the markets API directly.

    The per-event API returns empty markets for old events. The markets
    API (GET /markets?status=settled) returns all settled markets with
    result fields. Paginates with cursor persistence, 1000 markets/page,
    and batch-updates outcomes. Much faster than the per-event approach
    for the 48K outcomes the per-event API can't reach.
    """
    import asyncio
    from app.services.kalshi_api import KalshiAPIService
    from app.tasks.redis_state import get_redis_client

    _rc = get_redis_client()
    _cursor_key = "bainluck:kalshi_markets_winner_cursor"
    _raw = _rc.get(_cursor_key)
    cursor = _raw.decode() if isinstance(_raw, bytes) else (_raw or None)

    stats = {
        "pages": 0,
        "markets_scanned": 0,
        "winners_set": 0,
        "losers_set": 0,
        "no_result": 0,
        "errors": [],
    }

    service = KalshiAPIService()
    try:
        total_resolved = 0
        for _ in range(limit // 1000 + 1):
            try:
                markets, cursor = await service.get_markets(
                    status="settled",
                    limit=1000,
                    cursor=cursor,
                )
            except Exception as e:
                stats["errors"].append(str(e)[:200])
                break

            stats["pages"] += 1
            if not markets:
                _rc.delete(_cursor_key)
                break

            yes_tickers = []
            no_tickers = []
            for mkt in markets:
                stats["markets_scanned"] += 1
                ticker = mkt.get("ticker", "")
                result = mkt.get("result")
                if not ticker:
                    continue
                if result is None:
                    stats["no_result"] += 1
                    continue
                if result == "yes":
                    yes_tickers.append(ticker)
                else:
                    no_tickers.append(ticker)

            if yes_tickers or no_tickers:
                async with get_task_session() as session:
                    if yes_tickers:
                        r = await session.execute(
                            text("""
                                UPDATE futures_outcomes fo
                                SET is_winner = true,
                                    resolution_source = 'api_settlement',
                                    last_updated = NOW()
                                FROM futures_markets fm
                                WHERE fo.market_id = fm.id
                                  AND fm.source = 'kalshi'
                                  AND fo.external_id = ANY(:tickers)
                                  AND COALESCE(fo.resolution_source, '') NOT IN """ + AUTHORITATIVE_SOURCES_SQL + """
                            """),
                            {"tickers": yes_tickers},
                        )
                        stats["winners_set"] += r.rowcount

                    if no_tickers:
                        r = await session.execute(
                            text("""
                                UPDATE futures_outcomes fo
                                SET is_winner = false,
                                    resolution_source = 'api_settlement',
                                    last_updated = NOW()
                                FROM futures_markets fm
                                WHERE fo.market_id = fm.id
                                  AND fm.source = 'kalshi'
                                  AND fo.external_id = ANY(:tickers)
                                  AND COALESCE(fo.resolution_source, '') NOT IN """ + AUTHORITATIVE_SOURCES_SQL + """
                            """),
                            {"tickers": no_tickers},
                        )
                        stats["losers_set"] += r.rowcount

                    await session.commit()
                    total_resolved += stats["winners_set"] + stats["losers_set"]

            if cursor:
                _rc.setex(_cursor_key, 86400 * 14, cursor)
            else:
                _rc.delete(_cursor_key)
                break

            await asyncio.sleep(0.3)

    except Exception as e:
        stats["errors"].append(str(e)[:200])
    finally:
        await service.close()

    logger.info(
        "Kalshi markets backfill: %d pages, %d scanned, %d winners, %d losers",
        stats["pages"],
        stats["markets_scanned"],
        stats["winners_set"],
        stats["losers_set"],
    )
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
            # 2. No outcome already has authoritative is_winner (skip api_settlement etc.)
            #    Pass2_guess winners are treated as unresolved so clean data can overwrite
            # 3. All outcomes have current_probability near 0 or 1 (clean resolution)
            result = await session.execute(text("""
                    WITH cleanly_resolved AS (
                        SELECT fm.id AS market_id
                        FROM futures_markets fm
                        JOIN futures_outcomes fo ON fo.market_id = fm.id
                        WHERE fm.source = 'polymarket'
                          AND fm.status = 'resolved'
                        GROUP BY fm.id
                        HAVING SUM(CASE WHEN fo.is_winner
                                   AND fo.resolution_source NOT IN
                                       """ + OVERWRITABLE_WINNER_SOURCES_SQL + """
                                   THEN 1 ELSE 0 END) = 0
                           AND COUNT(*) FILTER (
                               WHERE fo.current_probability >= 0.95
                                  OR fo.current_probability <= 0.05
                           ) = COUNT(*)
                    )
                    UPDATE futures_outcomes fo
                    SET is_winner = (fo.current_probability >= 0.95),
                        resolution_source = 'clean_resolution',
                        last_updated = NOW()
                    FROM cleanly_resolved cr
                    WHERE fo.market_id = cr.market_id
                      AND fo.current_probability IS NOT NULL
                    RETURNING fo.is_winner
                """))
            rows = result.all()
            stats["winners_set"] = sum(1 for r in rows if r[0])
            stats["losers_set"] = sum(1 for r in rows if not r[0])

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Polymarket winner backfill error: %s", e)

    logger.info(
        "Polymarket winner backfill: %d winners, %d losers, %d errors",
        stats["winners_set"],
        stats["losers_set"],
        len(stats["errors"]),
    )
    return stats


def _detect_golf_market_type(name: str) -> str | None:
    """Detect golf market type from market name or external_id."""
    lower = name.lower()
    if re.search(r"winner|champion(?!ship)", lower):
        return "win"
    if "top 5" in lower or "top five" in lower:
        return "top_5"
    if "top 10" in lower or "top ten" in lower:
        return "top_10"
    if "top 20" in lower or "top twenty" in lower:
        return "top_20"
    if re.search(r"make.*cut|to make the cut", lower):
        return "make_cut"
    if re.search(r"head.to.head|h2h|matchup.*vs|vs\.", lower):
        return "h2h"
    return None


async def _resolve_kalshi_golf_from_datagolf():
    """Resolve Kalshi golf markets using DataGolf leaderboard results.

    Reuses existing cross-source matching from routes/golf.py:
    - _normalize_tournament() for tournament matching
    - _match_key() for player name matching
    - _datagolf_check_placement() for position → is_winner
    """
    from app.routes.golf import _normalize_tournament, _match_key

    stats = {
        "matched_tournaments": 0,
        "resolved_outcomes": 0,
        "no_tournament_match": 0,
        "no_player_match": 0,
        "skipped_type": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            # 1. Build tournament → leaderboard lookup from DataGolf
            dg_result = await session.execute(
                text("""
                    SELECT name, market_metadata
                    FROM futures_markets
                    WHERE source = 'datagolf'
                      AND status = 'resolved'
                      AND market_metadata IS NOT NULL
                      AND external_id LIKE :pattern
                """),
                {"pattern": "%:win"},
            )
            tournament_leaderboards: dict[str, list] = {}
            for row in dg_result.all():
                metadata = row.market_metadata or {}
                leaderboard = metadata.get("leaderboard")
                if not leaderboard:
                    continue
                key = _normalize_tournament(row.name)
                if key != "other":
                    tournament_leaderboards[key] = leaderboard

            if not tournament_leaderboards:
                logger.info("Golf cross-ref: no DataGolf tournaments with leaderboards")
                return stats

            logger.info(
                "Golf cross-ref: %d DataGolf tournaments available",
                len(tournament_leaderboards),
            )

            # 2. Find stuck Kalshi golf markets (including ones with WRONG is_winner
            # from Pass 2's arbitrary pick — use max(current_prob) < 0.90 as signal)
            kalshi_result = await session.execute(text("""
                    SELECT fm.id, fm.name, fm.external_id
                    FROM futures_markets fm
                    WHERE fm.source = 'kalshi'
                      AND fm.status = 'resolved'
                      AND fm.llm_sport_category = 'golf'
                """))
            kalshi_markets = kalshi_result.all()

            for row in kalshi_markets:
                # Determine market type from name (external_id is the market
                # name for Kalshi golf, not a ticker prefix)
                market_type = _detect_golf_market_type(
                    row.name or row.external_id or ""
                )
                if not market_type:
                    stats["skipped_type"] += 1
                    continue

                # Match tournament
                tournament_key = _normalize_tournament(row.name)
                leaderboard = tournament_leaderboards.get(tournament_key)
                if not leaderboard:
                    stats["no_tournament_match"] += 1
                    continue

                stats["matched_tournaments"] += 1

                # Build player lookup: match_key → position
                player_positions: dict[str, str] = {}
                for entry in leaderboard:
                    pname = entry.get("name", "")
                    pos = entry.get("position")
                    if pname and pos is not None:
                        player_positions[_match_key(pname)] = str(pos)

                can_infer_absent = market_type in ("win", "top_5", "top_10", "top_20")

                # Get outcomes and resolve
                outcomes = await session.execute(
                    text(
                        "SELECT id, name FROM futures_outcomes WHERE market_id = :mid"
                    ),
                    {"mid": row.id},
                )

                all_outcomes = outcomes.all()

                if market_type == "h2h" and len(all_outcomes) == 2:
                    # H2H: compare the two players' positions
                    positions = []
                    for out in all_outcomes:
                        key = _match_key(out.name or "")
                        pos_str = player_positions.get(key)
                        if pos_str is None:
                            break
                        numeric = pos_str.strip().upper().lstrip("T")
                        try:
                            positions.append((out.id, int(numeric)))
                        except ValueError:
                            break
                    if len(positions) == 2:
                        winner_id = min(positions, key=lambda x: x[1])[0]
                        for oid, _ in positions:
                            await session.execute(
                                text(
                                    "UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'game_score', last_updated = NOW() WHERE id = :oid"
                                ),
                                {"won": oid == winner_id, "oid": oid},
                            )
                            stats["resolved_outcomes"] += 1
                    else:
                        stats["no_player_match"] += 2
                    continue

                for out in all_outcomes:
                    key = _match_key(out.name or "")
                    pos_str = player_positions.get(key)

                    if pos_str is None:
                        if can_infer_absent:
                            won = False
                        else:
                            stats["no_player_match"] += 1
                            continue
                    else:
                        won = _datagolf_check_placement(pos_str, market_type)
                        if won is None:
                            continue

                    await session.execute(
                        text(
                            "UPDATE futures_outcomes SET is_winner = :won, resolution_source = :src, last_updated = NOW() WHERE id = :oid"
                        ),
                        {"won": won, "oid": out.id, "src": "leaderboard"},
                    )
                    stats["resolved_outcomes"] += 1

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Golf cross-ref error: %s", e)

    logger.info(
        "Golf cross-ref: %d tournaments matched, %d outcomes resolved, "
        "%d no_tournament, %d no_player, %d skipped_type, %d errors",
        stats["matched_tournaments"],
        stats["resolved_outcomes"],
        stats["no_tournament_match"],
        stats["no_player_match"],
        stats["skipped_type"],
        len(stats["errors"]),
    )
    return stats


# ---------------------------------------------------------------------------
# Regex for extracting round number from H2H / 3-ball market names
# e.g., "1st Round Head-to-Head: ..." → round 1
#        "3rd Round 3-Ball: ..." → round 3
# ---------------------------------------------------------------------------
_ROUND_RE = re.compile(
    r"(?:(\d)(?:st|nd|rd|th)\s+round)",
    re.I,
)


async def _resolve_golf_matchups_from_datagolf():
    """Resolve Kalshi H2H and 3-ball golf markets using DataGolf matchup data.

    The DataGolf historical-odds/matchups endpoint returns actual bet outcomes
    (bet_outcome_numeric: 1=won, 0=lost, -1=push) for head-to-head and 3-ball
    matchups. Each row contains player_name, opponent(s), and the outcome.

    Pipeline:
    1. Find unresolved Kalshi golf markets with H2H or 3-ball in the name
    2. Group them by tournament using _normalize_tournament()
    3. For each tournament, find the DataGolf event_id from existing DataGolf markets
    4. One API call per tournament per book to get matchup data
    5. Match Kalshi outcomes to DataGolf matchup rows using _match_key()
    6. Resolve is_winner from bet_outcome_numeric

    Efficiency: groups all markets by tournament FIRST, one API call per
    tournament, batch DB updates per tournament.
    """
    import asyncio
    from app.routes.golf import _normalize_tournament, _match_key
    from app.services.datagolf_api import DataGolfAPIService, normalize_player_name

    stats = {
        "markets_found": 0,
        "tournaments_grouped": 0,
        "tournaments_with_dg": 0,
        "api_calls": 0,
        "outcomes_resolved": 0,
        "winners_set": 0,
        "losers_set": 0,
        "pushes": 0,
        "no_dg_event": 0,
        "no_matchup_data": 0,
        "no_player_match": 0,
        "errors": [],
    }

    try:
        # Step 1: Find unresolved Kalshi golf H2H and 3-ball markets
        async with get_task_session() as session:
            result = await session.execute(text("""
                    SELECT fm.id, fm.name, fm.external_id, fm.event_id
                    FROM futures_markets fm
                    WHERE fm.source = 'kalshi'
                      AND fm.status = 'resolved'
                      AND fm.llm_sport_category = 'golf'
                      AND (
                          LOWER(fm.name) LIKE '%head-to-head%'
                          OR LOWER(fm.name) LIKE '%head to head%'
                          OR LOWER(fm.name) LIKE '%h2h%'
                          OR LOWER(fm.name) LIKE '%3-ball%'
                          OR LOWER(fm.name) LIKE '%3 ball%'
                          OR LOWER(fm.name) LIKE '%3ball%'
                          OR LOWER(fm.name) LIKE '%matchup%vs%'
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM futures_outcomes fo
                          WHERE fo.market_id = fm.id
                            AND fo.resolution_source = 'datagolf_matchup'
                      )
                """))
            markets = result.all()

        if not markets:
            logger.info(
                "Golf matchup resolution: nothing to do (0 unresolved H2H/3-ball markets)"
            )
            return stats

        stats["markets_found"] = len(markets)
        logger.info(
            "Golf matchup resolution: %d unresolved H2H/3-ball markets", len(markets)
        )

        # Step 2: Group markets by tournament
        tournament_markets: dict[str, list] = {}
        for row in markets:
            tourn_key = _normalize_tournament(row.name or "")
            tournament_markets.setdefault(tourn_key, []).append(row)

        stats["tournaments_grouped"] = len(tournament_markets)
        logger.info(
            "Golf matchup resolution: grouped into %d tournaments",
            len(tournament_markets),
        )

        # Step 3: Build tournament_key → DataGolf (tour, event_id) lookup
        # from existing resolved DataGolf winner markets in our DB
        async with get_task_session() as session:
            dg_result = await session.execute(
                text("""
                    SELECT fm.name, fm.external_id
                    FROM futures_markets fm
                    WHERE fm.source = 'datagolf'
                      AND fm.status = 'resolved'
                      AND fm.external_id LIKE :pattern
                """),
                {"pattern": "datagolf:%:%:win"},
            )
            dg_markets = dg_result.all()

        # Map tournament_key → (tour, event_id)
        tourn_to_dg: dict[str, tuple[str, str]] = {}
        for dg_row in dg_markets:
            dg_tourn_key = _normalize_tournament(dg_row.name or "")
            if dg_tourn_key == "other":
                continue
            # Parse external_id: "datagolf:pga:123:win"
            parts = dg_row.external_id.split(":")
            if len(parts) >= 4:
                tourn_to_dg[dg_tourn_key] = (parts[1], parts[2])  # (tour, event_id)

        # Step 4: For each tournament, fetch matchup data and resolve
        service = DataGolfAPIService()
        try:
            books_to_try = ["pinnacle", "bet365", "fanduel", "betmgm"]

            for tourn_key, tourn_market_rows in tournament_markets.items():
                dg_info = tourn_to_dg.get(tourn_key)
                if not dg_info:
                    stats["no_dg_event"] += len(tourn_market_rows)
                    continue

                tour, event_id = dg_info
                stats["tournaments_with_dg"] += 1

                # Fetch matchup data — try multiple books until we get data
                matchup_rows = None
                for book in books_to_try:
                    raw_rows = await service.get_historical_matchups(
                        tour=tour,
                        event_id=event_id,
                        book=book,
                    )
                    stats["api_calls"] += 1
                    await asyncio.sleep(0.2)

                    if raw_rows:
                        # Filter to rows that have settlement outcomes
                        settled = [
                            r
                            for r in raw_rows
                            if r.get("bet_outcome_numeric") is not None
                            or r.get("bet_outcome") is not None
                        ]
                        if settled:
                            matchup_rows = settled
                            break

                if not matchup_rows:
                    stats["no_matchup_data"] += 1
                    continue

                # Build a lookup: (player_match_key, opponent_match_key) → outcome
                # Also track round numbers for round-specific matchups
                # DataGolf matchup rows typically contain:
                #   player_name, matchup_opponent (or opponent_name),
                #   bet_outcome_numeric (1=won, 0=lost, -1=push),
                #   round_num (for round-specific matchups)
                matchup_outcomes: dict[tuple, dict] = {}
                for mrow in matchup_rows:
                    player_name = normalize_player_name(mrow.get("player_name", ""))
                    # Try multiple field names for opponent
                    opponent_name = normalize_player_name(
                        mrow.get("matchup_opponent", "")
                        or mrow.get("opponent_name", "")
                        or mrow.get("opponent", "")
                    )
                    if not player_name or not opponent_name:
                        continue

                    player_key = _match_key(player_name)
                    opponent_key = _match_key(opponent_name)
                    if not player_key or not opponent_key:
                        continue

                    outcome_val = mrow.get("bet_outcome_numeric")
                    if outcome_val is None:
                        outcome_val = mrow.get("bet_outcome")
                    if outcome_val is None:
                        continue

                    try:
                        outcome_numeric = float(outcome_val)
                    except (ValueError, TypeError):
                        continue

                    round_num = mrow.get("round_num") or mrow.get("round")

                    # Key: (player, opponent, round_or_None)
                    lookup_key = (player_key, opponent_key, round_num)
                    matchup_outcomes[lookup_key] = {
                        "outcome": outcome_numeric,
                        "player": player_name,
                        "opponent": opponent_name,
                    }
                    # Also store without round for fallback
                    fallback_key = (player_key, opponent_key, None)
                    if fallback_key not in matchup_outcomes:
                        matchup_outcomes[fallback_key] = {
                            "outcome": outcome_numeric,
                            "player": player_name,
                            "opponent": opponent_name,
                        }

                if not matchup_outcomes:
                    stats["no_matchup_data"] += 1
                    continue

                # Resolve each market in this tournament
                async with get_task_session() as session:
                    for market_row in tourn_market_rows:
                        market_name = market_row.name or ""
                        market_type = _detect_golf_market_type(market_name)

                        # Extract round number from market name if present
                        round_match = _ROUND_RE.search(market_name)
                        market_round = (
                            int(round_match.group(1)) if round_match else None
                        )

                        # Load outcomes for this market
                        outcomes_result = await session.execute(
                            text("""
                                SELECT fo.id, fo.name, fo.is_winner
                                FROM futures_outcomes fo
                                WHERE fo.market_id = :mid
                            """),
                            {"mid": market_row.id},
                        )
                        outcomes = outcomes_result.all()

                        if market_type == "h2h" and len(outcomes) == 2:
                            # H2H: match two players against each other
                            o1, o2 = outcomes
                            k1 = _match_key(o1.name or "")
                            k2 = _match_key(o2.name or "")
                            if not k1 or not k2:
                                stats["no_player_match"] += 2
                                continue

                            # Look up (player1 vs player2) with round specificity
                            result_data = matchup_outcomes.get(
                                (k1, k2, market_round)
                            ) or matchup_outcomes.get((k1, k2, None))
                            if result_data:
                                outcome_num = result_data["outcome"]
                                if outcome_num == -1:
                                    # Push — both are losers (tie)
                                    stats["pushes"] += 1
                                    continue
                                o1_won = outcome_num == 1
                            else:
                                # Try reverse: player2 vs player1
                                result_data_rev = matchup_outcomes.get(
                                    (k2, k1, market_round)
                                ) or matchup_outcomes.get((k2, k1, None))
                                if result_data_rev:
                                    outcome_num = result_data_rev["outcome"]
                                    if outcome_num == -1:
                                        stats["pushes"] += 1
                                        continue
                                    o1_won = outcome_num == 0  # Reversed
                                else:
                                    stats["no_player_match"] += 2
                                    continue

                            # Set is_winner on both outcomes
                            for oid, won in [(o1.id, o1_won), (o2.id, not o1_won)]:
                                await session.execute(
                                    text("""
                                        UPDATE futures_outcomes
                                        SET is_winner = :won,
                                            resolution_source = 'datagolf_matchup',
                                            last_updated = NOW()
                                        WHERE id = :oid
                                    """),
                                    {"won": won, "oid": oid},
                                )
                                stats["outcomes_resolved"] += 1
                                if won:
                                    stats["winners_set"] += 1
                                else:
                                    stats["losers_set"] += 1

                        elif market_type == "3ball" and len(outcomes) == 3:
                            # 3-ball: three players, resolve each independently
                            # Find matchup outcomes for all pairwise combinations
                            # among the three players
                            outcome_keys = []
                            for o in outcomes:
                                k = _match_key(o.name or "")
                                outcome_keys.append((o.id, k, o.name))

                            if any(not k for _, k, _ in outcome_keys):
                                stats["no_player_match"] += 3
                                continue

                            # For 3-ball, DataGolf may have individual matchup
                            # rows per pair. The overall winner is the player
                            # who won the most pairwise matchups (or the one
                            # who beat both others). Try to find at least one
                            # pair resolved.
                            pair_results: dict[str, int] = {}  # player_key → wins
                            for _, pk, _ in outcome_keys:
                                pair_results[pk] = 0

                            found_any = False
                            for i, (_, ki, _) in enumerate(outcome_keys):
                                for j, (_, kj, _) in enumerate(outcome_keys):
                                    if i >= j:
                                        continue
                                    result_data = matchup_outcomes.get(
                                        (ki, kj, market_round)
                                    ) or matchup_outcomes.get((ki, kj, None))
                                    if result_data:
                                        outcome_num = result_data["outcome"]
                                        if outcome_num == 1:
                                            pair_results[ki] += 1
                                        elif outcome_num == 0:
                                            pair_results[kj] += 1
                                        found_any = True
                                    else:
                                        # Try reverse
                                        result_data_rev = matchup_outcomes.get(
                                            (kj, ki, market_round)
                                        ) or matchup_outcomes.get((kj, ki, None))
                                        if result_data_rev:
                                            outcome_num = result_data_rev["outcome"]
                                            if outcome_num == 1:
                                                pair_results[kj] += 1
                                            elif outcome_num == 0:
                                                pair_results[ki] += 1
                                            found_any = True

                            if not found_any:
                                stats["no_player_match"] += 3
                                continue

                            # Winner is the player with most pairwise wins
                            max_wins = max(pair_results.values())
                            if max_wins == 0:
                                stats["pushes"] += 1
                                continue

                            # Exactly one player should have the most wins
                            winners = [
                                k for k, v in pair_results.items() if v == max_wins
                            ]

                            for oid, pk, _ in outcome_keys:
                                won = pk in winners and len(winners) == 1
                                await session.execute(
                                    text("""
                                        UPDATE futures_outcomes
                                        SET is_winner = :won,
                                            resolution_source = 'datagolf_matchup',
                                            last_updated = NOW()
                                        WHERE id = :oid
                                    """),
                                    {"won": won, "oid": oid},
                                )
                                stats["outcomes_resolved"] += 1
                                if won:
                                    stats["winners_set"] += 1
                                else:
                                    stats["losers_set"] += 1

                        else:
                            # Unknown type or unexpected outcome count
                            continue

                    # Set event_id on matched markets for display on event pages
                    # Find any golf event associated with this tournament
                    event_result = await session.execute(
                        text("""
                            SELECT DISTINCT fm.event_id
                            FROM futures_markets fm
                            WHERE fm.source = 'datagolf'
                              AND fm.external_id LIKE :prefix
                              AND fm.event_id IS NOT NULL
                            LIMIT 1
                        """),
                        {"prefix": f"datagolf:{tour}:{event_id}:%"},
                    )
                    event_row = event_result.first()
                    if event_row and event_row.event_id:
                        for market_row in tourn_market_rows:
                            if market_row.event_id is None:
                                await session.execute(
                                    text("""
                                        UPDATE futures_markets
                                        SET event_id = :eid
                                        WHERE id = :mid AND event_id IS NULL
                                    """),
                                    {"eid": event_row.event_id, "mid": market_row.id},
                                )

                    await session.commit()

        finally:
            await service.close()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Golf matchup resolution error: %s", e)

    logger.info(
        "Golf matchup resolution: %d markets found, %d tournaments (%d with DG data), "
        "%d API calls, %d outcomes resolved (%d winners, %d losers, %d pushes), "
        "%d no_dg_event, %d no_matchup_data, %d no_player_match, %d errors",
        stats["markets_found"],
        stats["tournaments_grouped"],
        stats["tournaments_with_dg"],
        stats["api_calls"],
        stats["outcomes_resolved"],
        stats["winners_set"],
        stats["losers_set"],
        stats["pushes"],
        stats["no_dg_event"],
        stats["no_matchup_data"],
        stats["no_player_match"],
        len(stats["errors"]),
    )
    return stats


async def _resolve_kalshi_from_scores():
    """Resolve Kalshi game markets from actual Event scores.

    For Kalshi markets linked to Events (via event_id) where the Kalshi
    API has purged the settlement data, uses the game score to determine
    winners. Handles:
    - Moneyline (2 outcomes per team): match outcome name to home/away
    - BTTS (ticker contains 'btts'): both scores > 0
    - Single-outcome moneyline ("Yes"): use ticker team abbreviation
    """
    stats = {"moneyline": 0, "btts": 0, "skipped": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(text("""
                    SELECT fm.id AS market_id, fm.name AS market_name,
                           fm.external_id AS ticker,
                           e.home_team_name, e.away_team_name,
                           e.home_score, e.away_score,
                           COUNT(fo.id) AS n_outcomes
                    FROM futures_markets fm
                    JOIN events e ON e.id = fm.event_id
                    JOIN futures_outcomes fo ON fo.market_id = fm.id
                    WHERE fm.status = 'resolved'
                      AND e.status IN ('completed', 'closed')
                      AND e.home_score IS NOT NULL
                      AND e.away_score IS NOT NULL
                      AND fo.current_probability IS NOT NULL
                    GROUP BY fm.id, fm.name, fm.external_id,
                             e.home_team_name, e.away_team_name,
                             e.home_score, e.away_score
                    HAVING SUM(CASE WHEN fo.is_winner
                               AND fo.resolution_source NOT IN
                                   """ + OVERWRITABLE_WINNER_SOURCES_SQL + """
                               THEN 1 ELSE 0 END) = 0
                    LIMIT 100000
                """))
            markets = result.all()

            # Commit incrementally so a long run drains the full backlog (was
            # starved by a 10K row cap vs ~41K selectable, #907) and partial
            # progress survives a timeout/error instead of rolling back the
            # whole batch (gotcha #6). Check is at the top of the loop so the
            # body's many `continue` paths can't skip it.
            for i, row in enumerate(markets):
                if i and i % 500 == 0:
                    await session.commit()
                ticker_lower = (row.ticker or "").lower()

                # BTTS: both teams to score
                if "btts" in ticker_lower:
                    btts_yes = row.home_score > 0 and row.away_score > 0
                    await session.execute(
                        text("""
                            UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'game_score', last_updated = NOW()
                            WHERE market_id = :mid
                        """),
                        {"won": btts_yes, "mid": row.market_id},
                    )
                    stats["btts"] += 1
                    continue

                # Skip non-moneyline market types — these are handled by
                # the spread/total/player prop resolvers. Half/period WINNER
                # markets (1hwinner/2hwinner) must be skipped too: this branch
                # resolves from FINAL game scores, but a half/period winner needs
                # the HALFTIME/period score (handled by the spread/total resolver's
                # team-name fallback via _get_halftime_score). Without this guard,
                # once box-score backfill populates final scores, a team that won
                # the game but lost the 1st half would be mis-resolved as the 1H
                # winner — corrupting calibration (#816, gotcha #21).
                _non_ml = (
                    "total",
                    "spread",
                    "pts",
                    "reb",
                    "ast",
                    "3pt",
                    "blk",
                    "stl",
                    "hrr",
                    "hit",
                    "tb",
                    "ks",
                    "hr",
                    "rfi",
                    "f5",
                    "mention",
                    "1htotal",
                    "1hspread",
                    "1hwinner",
                    "2htotal",
                    "2hspread",
                    "2hwinner",
                )
                if any(t in ticker_lower for t in _non_ml):
                    stats["skipped"] += 1
                    continue

                # Moneyline: need distinct scores (no ties)
                if row.home_score == row.away_score:
                    stats["skipped"] += 1
                    continue

                # Only handle 2-outcome markets (team vs team)
                if row.n_outcomes != 2:
                    stats["skipped"] += 1
                    continue

                home_won = row.home_score > row.away_score

                outcomes = await session.execute(
                    text("""
                        SELECT id, name FROM futures_outcomes
                        WHERE market_id = :mid ORDER BY id
                    """),
                    {"mid": row.market_id},
                )
                outs = outcomes.all()
                if len(outs) != 2:
                    stats["skipped"] += 1
                    continue

                home_tokens = (
                    set(row.home_team_name.lower().split())
                    if row.home_team_name
                    else set()
                )
                away_tokens = (
                    set(row.away_team_name.lower().split())
                    if row.away_team_name
                    else set()
                )

                resolved_any = False
                for out in outs:
                    name_lower = (out.name or "").lower()
                    name_tokens = set(name_lower.split())

                    is_home = bool(home_tokens & name_tokens)
                    is_away = bool(away_tokens & name_tokens)

                    if is_home and not is_away:
                        won = home_won
                    elif is_away and not is_home:
                        won = not home_won
                    else:
                        continue

                    await session.execute(
                        text(
                            "UPDATE futures_outcomes SET is_winner = :won, resolution_source = :src, last_updated = NOW() WHERE id = :oid"
                        ),
                        {"won": won, "oid": out.id, "src": "game_score"},
                    )
                    resolved_any = True

                if resolved_any:
                    stats["moneyline"] += 1
                else:
                    stats["skipped"] += 1

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Kalshi score resolution error: %s", e)

    total = stats["moneyline"] + stats["btts"]
    logger.info(
        "Kalshi score resolution: %d moneyline, %d btts, %d skipped, %d errors",
        stats["moneyline"],
        stats["btts"],
        stats["skipped"],
        len(stats["errors"]),
    )
    return stats


_SPREAD_RE = re.compile(
    r"(.+?) wins(?: the 1H)? by over (\d+\.?\d*)\s+(?:points|runs|goals)",
    re.IGNORECASE,
)
_TOTAL_RE = re.compile(
    r"^(?P<dir>Over|Under)\s+(\d+\.?\d*)\s+(?:1H\s+)?(?:2H\s+)?(?:team\s+)?(?:total\s+)?(?:points|runs|goals|maps|rounds|kills)(?:\s+scored)?$",
    re.IGNORECASE,
)

_FIRST_HALF_PERIODS = {
    "q1",
    "q2",
    "1q",
    "2q",
    "1st",
    "2nd",
    "1st half",
    "first half",
    "1h",
    "top 1st",
    "bot 1st",
    "top 2nd",
    "bot 2nd",
    "top 3rd",
    "bot 3rd",
    "top 4th",
    "bot 4th",
    "top 5th",
    "bot 5th",
    "1st period",
    "2nd period",
}


def _decide_three_way_winner(outcome_names, home_team_name, away_team_name,
                             h_score, a_score):
    """Decide is_winner per outcome for a 3-outcome Team/Team/Tie winner market.

    Used for markets like KXNCAAMB1HWINNER which carry three outcomes
    (Home team / Away team / Tie); the 2-outcome team-name fallback skips them.

    h_score/a_score are home/away scores (half-time scores for 1H markets).
    Returns a {index: bool} map aligned to ``outcome_names`` order, or ``None``
    when the outcomes are not a clean Team/Team/Tie triple or scores are missing.
    """
    if len(outcome_names) != 3 or h_score is None or a_score is None:
        return None
    home_tokens = set((home_team_name or "").lower().split())
    away_tokens = set((away_team_name or "").lower().split())
    kinds = []
    for nm in outcome_names:
        n = (nm or "").lower().strip()
        toks = set(n.split())
        is_home = bool(toks & home_tokens) and not bool(toks & away_tokens)
        is_away = bool(toks & away_tokens) and not bool(toks & home_tokens)
        if is_home and not is_away:
            kinds.append("home")
        elif is_away and not is_home:
            kinds.append("away")
        elif n in ("tie", "draw"):
            kinds.append("tie")
        else:
            return None
    if set(kinds) != {"home", "away", "tie"}:
        return None
    if h_score > a_score:
        winner = "home"
    elif a_score > h_score:
        winner = "away"
    else:
        winner = "tie"
    return {i: (kinds[i] == winner) for i in range(3)}


def _spread_outcome_is_winner(
    outcome_name, home_team_name, away_team_name, home_score, away_score
):
    """#939: grade ONE "{team} wins by over N" spread outcome independently.

    NHL/NBA spread markets carry several such outcomes (home@1.5, home@2.5,
    away@1.5, away@2.5) that are NOT a complementary Yes/No pair (gotchas #17,
    #23). Each wins iff its OWN named team's actual margin exceeds its OWN line.
    A loss yields a negative margin, which never exceeds a positive line, so
    ``margin > line`` correctly encodes "named team won AND covered".

    Returns True/False, or None when the name isn't a spread outcome or the
    named team can't be matched to either side (caller should skip).
    """
    sm = _SPREAD_RE.search(outcome_name or "")
    if not sm:
        return None
    if home_score is None or away_score is None:
        return None
    team_name = sm.group(1).strip()
    line = float(sm.group(2))
    # Normalize for matching: strips diacritics ("Montréal" -> "montreal") and
    # periods ("St. Louis" -> "st louis"). Without this, accented event names
    # never token-match the ASCII Kalshi outcome name and the outcome was left
    # at its old (inverted) value (#939: ~17 Montréal rows stayed wrong).
    from app.utils.name_normalization import normalize_team_name
    home_tokens = set(normalize_team_name(home_team_name or "").split())
    away_tokens = set(normalize_team_name(away_team_name or "").split())
    team_tokens = set(normalize_team_name(team_name).split())
    if team_tokens & home_tokens:
        margin = home_score - away_score
    elif team_tokens & away_tokens:
        margin = away_score - home_score
    else:
        return None
    return margin > line


def _total_outcome_is_winner(outcome_name, home_score, away_score):
    """#945: grade ONE "Over/Under N ... scored" total outcome from the final score.

    total = home + away; "Over N" wins iff total > N, "Under N" iff total < N
    (gotcha #17: Kalshi threshold outcomes are OVER probabilities unless the name
    starts with "Under"/equals "No" — _TOTAL_RE captures the direction). Returns
    True/False, or None if the name isn't a total outcome or scores are missing
    (caller skips).
    """
    if home_score is None or away_score is None:
        return None
    tm = _TOTAL_RE.search(outcome_name or "")
    if not tm:
        return None
    direction = tm.group("dir").lower()
    line = float(tm.group(2))
    total = home_score + away_score
    return total > line if direction == "over" else total < line


# #140: Polymarket decomposes game totals into markets named "{A} vs. {B}: O/U N"
# whose two outcomes are literally "Over"/"Under" — the LINE lives in the MARKET
# name, not the outcome name (unlike Kalshi, so _TOTAL_RE above can't reach it).
# The strict "...: O/U N$" suffix isolates FULL-GAME team totals (total = home +
# away). Anything with a qualifier between the colon and "O/U" is deliberately
# NOT matched: "1H O/U" (halftime, needs reconstructed score), player props
# ("Points/Rebounds O/U"), tennis "Match/Set Games O/U" (games/sets, not our
# home+away score). The colon-immediately-before-O/U anchor is the discriminator
# (gotcha #21: never guess an ambiguous line/scope).
_POLY_TOTAL_MARKET_RE = re.compile(r":\s*o/u\s*(\d+\.?\d*)\s*$", re.IGNORECASE)


def _poly_total_line(market_name):
    """#140: parse the O/U line from a Polymarket full-game total market name.

    Returns the line as a float for the strict "{A} vs. {B}: O/U N" full-game
    pattern, or None to skip (unparseable, or a scoped/prop/period total whose
    line or scope we must not guess).
    """
    m = _POLY_TOTAL_MARKET_RE.search(market_name or "")
    return float(m.group(1)) if m else None


async def _resolve_polymarket_total_from_scores(limit: int = 20000):
    """#140: grade ungraded Polymarket full-game Over/Under totals from scores.

    The ungraded cohort (ops OPS-475 census on #997: 18,985 resolved Polymarket
    markets with an Over/Under pair where NO side is is_winner=True) is #137's
    residual "resolution completeness" hypothesis — not model bias. 90% are
    game-linked with final scores already in our DB, so this resolution is
    deterministic and needs NO Gamma API: it is immune to the #985 rate-limit
    AND to Gamma's retention window (even aged>60d markets are saved because the
    score is local, not perishable).

    Grades ONLY the strict "{A} vs. {B}: O/U N" full-game pattern against the
    linked completed/closed event's total (home + away): "Over" wins iff
    total > line, "Under" iff total < line. total == line (a push, only possible
    on an integer line) and unparseable/scoped names are SKIPPED (gotcha #21).
    Writes is_winner + resolution_source='poly_total_score' via Core UPDATE,
    per-batch commits (#13) so partial progress survives a timeout (gotcha #6).
    Idempotent: once a side is set True the market's BOOL_OR excludes it next run.
    """
    stats = {"graded": 0, "push_skip": 0, "no_parse": 0, "errors": []}
    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    SELECT m.id AS market_id, m.name AS market_name,
                           e.home_score, e.away_score
                    FROM futures_markets m
                    JOIN events e ON e.id = m.event_id
                    JOIN futures_outcomes u ON u.market_id = m.id
                    WHERE m.source = 'polymarket'
                      AND m.status = 'resolved'
                      AND e.status IN ('completed', 'closed')
                      AND e.home_score IS NOT NULL
                      AND e.away_score IS NOT NULL
                    GROUP BY m.id, m.name, e.home_score, e.away_score
                    HAVING BOOL_OR(u.is_winner) IS NOT TRUE
                       AND COUNT(*) FILTER (
                           WHERE u.name ILIKE 'over%' OR u.name ILIKE 'under%') > 0
                    LIMIT :lim
                """),
                {"lim": limit},
            )
            markets = result.all()

            for i, row in enumerate(markets):
                if i and i % 500 == 0:
                    await session.commit()
                line = _poly_total_line(row.market_name)
                if line is None:
                    stats["no_parse"] += 1
                    continue
                total = row.home_score + row.away_score
                if total == line:
                    # push — only possible on an integer line; never guess
                    stats["push_skip"] += 1
                    continue
                out = await session.execute(
                    text("SELECT id, name FROM futures_outcomes WHERE market_id = :mid"),
                    {"mid": row.market_id},
                )
                graded_any = False
                for oc in out.all():
                    nm = (oc.name or "").strip().lower()
                    if nm.startswith("over"):
                        won = total > line
                    elif nm.startswith("under"):
                        won = total < line
                    else:
                        continue
                    await session.execute(
                        text(
                            "UPDATE futures_outcomes SET is_winner = :won, "
                            "resolution_source = 'poly_total_score', "
                            "last_updated = NOW() WHERE id = :oid"
                        ),
                        {"won": won, "oid": oc.id},
                    )
                    graded_any = True
                if graded_any:
                    stats["graded"] += 1
            await session.commit()
        logger.info(
            "Polymarket total score resolution (#140): graded %d markets, "
            "%d push-skip, %d no-parse",
            stats["graded"],
            stats["push_skip"],
            stats["no_parse"],
        )
    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Polymarket total score resolution error: %s", e)
    return stats


async def _resolve_kalshi_spread_total_from_scores():
    """Resolve Kalshi spread and total markets from actual game scores.

    Handles both full-game and 1H markets:
    - Full-game spreads: "{team} wins by over N points" → check final margin
    - Full-game totals: "Over N points scored" → check final total
    - 1H spreads: "{team} wins the 1H by over N points" → reconstruct
      halftime score from scoring_plays
    - 1H totals: "Over N 1H points scored" → same
    """
    stats = {
        "spread": 0,
        "total": 0,
        "h1_spread": 0,
        "h1_total": 0,
        "no_plays": 0,
        "no_parse": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            result = await session.execute(text("""
                    SELECT fm.id AS market_id, fm.external_id AS ticker,
                           fm.name AS market_name,
                           e.id AS event_id,
                           e.home_team_name, e.away_team_name,
                           e.home_score, e.away_score
                    FROM futures_markets fm
                    JOIN events e ON e.id = fm.event_id
                    JOIN futures_outcomes fo ON fo.market_id = fm.id
                    WHERE fm.status = 'resolved'
                      AND e.status IN ('completed', 'closed')
                      AND e.home_score IS NOT NULL
                      AND e.away_score IS NOT NULL
                      AND fo.current_probability IS NOT NULL
                    GROUP BY fm.id, fm.external_id, fm.name, e.id,
                             e.home_team_name, e.away_team_name,
                             e.home_score, e.away_score
                    HAVING SUM(CASE WHEN fo.is_winner
                               AND fo.resolution_source NOT IN
                                   """ + OVERWRITABLE_WINNER_SOURCES_SQL + """
                               THEN 1 ELSE 0 END) = 0
                    LIMIT 100000
                """))
            markets = result.all()

            # Commit incrementally so a long run drains the full backlog (was
            # starved by a 10K row cap vs ~41K selectable, #907) and partial
            # progress survives a timeout/error instead of rolling back the
            # whole batch (gotcha #6). Check is at the top of the loop so the
            # body's many `continue` paths can't skip it.
            for i, row in enumerate(markets):
                if i and i % 500 == 0:
                    await session.commit()
                ticker_lower = (row.ticker or "").lower()
                is_1h = "1h" in ticker_lower or "1half" in ticker_lower

                # Get all outcomes for this market
                out = await session.execute(
                    text(
                        "SELECT id, name FROM futures_outcomes WHERE market_id = :mid"
                    ),
                    {"mid": row.market_id},
                )
                outcomes_list = out.all()
                if not outcomes_list:
                    stats["no_parse"] += 1
                    continue

                # Team total: "{Team} over N points scored" in any outcome name
                resolved_team_total = False
                for oc in outcomes_list:
                    # #947: this greedy regex also matches SPREAD outcomes
                    # ("Carolina wins by over 1.5 goals" → team="Carolina wins by"),
                    # grading a spread by the team's RAW score instead of the MARGIN
                    # and shadowing the correct per-outcome spread branch below
                    # (the spread inverter the #944 re-grade band-aided). Skip any
                    # spread-pattern name so it falls through to the spread branch.
                    if _SPREAD_RE.search(oc.name or ""):
                        continue
                    _tt_re = re.match(
                        r"(.+?)\s+over\s+(\d+\.?\d*)\s+(?:points|runs|goals)",
                        oc.name or "",
                        re.IGNORECASE,
                    )
                    if _tt_re:
                        team_name = _tt_re.group(1).strip()
                        line = float(_tt_re.group(2))
                        home_tokens = (
                            set(row.home_team_name.lower().split())
                            if row.home_team_name
                            else set()
                        )
                        away_tokens = (
                            set(row.away_team_name.lower().split())
                            if row.away_team_name
                            else set()
                        )
                        team_tokens = set(team_name.lower().split())

                        team_score = None
                        if team_tokens & home_tokens:
                            team_score = row.home_score
                        elif team_tokens & away_tokens:
                            team_score = row.away_score

                        if team_score is not None:
                            over = team_score > line
                            for oc2 in outcomes_list:
                                is_over_outcome = bool(
                                    re.match(
                                        r".+\s+over\s+", oc2.name or "", re.IGNORECASE
                                    )
                                )
                                won = over if is_over_outcome else not over
                                await session.execute(
                                    text(
                                        "UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'game_score', last_updated = NOW() WHERE id = :oid"
                                    ),
                                    {"won": won, "oid": oc2.id},
                                )
                            stats["total"] += 1
                            resolved_team_total = True
                            break
                if resolved_team_total:
                    continue

                # For spread/total parsing, try each outcome until one matches
                resolved_st = False
                for outcome in outcomes_list:
                    name = outcome.name or ""

                    # Try spread pattern.
                    #
                    # #939: NHL/NBA spread markets carry MULTIPLE independent
                    # "{team} wins by over N" outcomes (e.g. home@1.5, home@2.5,
                    # away@1.5, away@2.5) — they are NOT a complementary Yes/No
                    # pair (gotchas #17, #23). Each outcome wins iff THAT named
                    # team's actual margin exceeds ITS OWN line. The old code
                    # resolved only the first matching outcome, blindly flipped
                    # every sibling to `not won`, and broke — so whole markets
                    # landed all-True or all-False by insertion order (KXNHLSPREAD
                    # game_score: pred 25% but actual 72%). Resolve each outcome
                    # on its own terms; never flip siblings, never break.
                    sm = _SPREAD_RE.search(name)
                    if sm:
                        if is_1h:
                            h1_scores = await _get_halftime_score(session, row.event_id)
                            if h1_scores is None:
                                stats["no_plays"] += 1
                                resolved_st = True
                                break
                            h_for_spread, a_for_spread = h1_scores
                        else:
                            h_for_spread, a_for_spread = row.home_score, row.away_score

                        # Grade THIS outcome on its own named team + line.
                        won = _spread_outcome_is_winner(
                            name,
                            row.home_team_name,
                            row.away_team_name,
                            h_for_spread,
                            a_for_spread,
                        )
                        if won is None:
                            continue
                        await session.execute(
                            text(
                                "UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'game_score', last_updated = NOW() WHERE id = :oid"
                            ),
                            {"won": won, "oid": outcome.id},
                        )
                        stats["h1_spread" if is_1h else "spread"] += 1
                        resolved_st = True
                        continue

                    # Try total pattern — grade THIS outcome INDEPENDENTLY.
                    #
                    # #947: multi-line totals ("Over 5.5", "Over 6.5", "Under 5.5",
                    # ...) are independent binaries, NOT a complementary pair (same
                    # as spreads, #939). The old code computed `won` for the first
                    # matching outcome and flipped every sibling via
                    # `oc_won = won if oc.id == outcome.id else not won` (the
                    # `is_over` it computed was dead code), so on re-pull it
                    # INVERTED multi-line totals — the total inverter the #945
                    # re-grade band-aided. Grade each outcome on its own
                    # Over/Under + line vs the real total; never flip siblings.
                    if _TOTAL_RE.search(name):
                        if is_1h:
                            h1_scores = await _get_halftime_score(session, row.event_id)
                            if h1_scores is None:
                                stats["no_plays"] += 1
                                resolved_st = True
                                break
                            h_for_total, a_for_total = h1_scores
                        else:
                            h_for_total, a_for_total = row.home_score, row.away_score

                        won = _total_outcome_is_winner(name, h_for_total, a_for_total)
                        if won is None:
                            continue
                        await session.execute(
                            text(
                                "UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'game_score', last_updated = NOW() WHERE id = :oid"
                            ),
                            {"won": won, "oid": outcome.id},
                        )
                        stats["h1_total" if is_1h else "total"] += 1
                        resolved_st = True
                        continue

                # Fallback: team-name-only outcomes on 2-outcome markets
                # (e.g., "Penn" on KXNCAAMBGAME, "California" on KXNCAAMB1HWINNER)
                if not resolved_st and len(outcomes_list) == 2:
                    home_tokens = (
                        set(row.home_team_name.lower().split())
                        if row.home_team_name
                        else set()
                    )
                    away_tokens = (
                        set(row.away_team_name.lower().split())
                        if row.away_team_name
                        else set()
                    )

                    if is_1h:
                        h1_scores = await _get_halftime_score(session, row.event_id)
                        if h1_scores:
                            h_score, a_score = h1_scores
                        else:
                            h_score, a_score = None, None
                    else:
                        h_score, a_score = row.home_score, row.away_score

                    if (
                        h_score is not None
                        and a_score is not None
                        and h_score != a_score
                    ):
                        home_won = h_score > a_score
                        for oc in outcomes_list:
                            oc_tokens = set((oc.name or "").lower().split())
                            is_home = bool(oc_tokens & home_tokens) and not bool(
                                oc_tokens & away_tokens
                            )
                            is_away = bool(oc_tokens & away_tokens) and not bool(
                                oc_tokens & home_tokens
                            )
                            if is_home:
                                won = home_won
                            elif is_away:
                                won = not home_won
                            else:
                                continue
                            await session.execute(
                                text(
                                    "UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'game_score', last_updated = NOW() WHERE id = :oid"
                                ),
                                {"won": won, "oid": oc.id},
                            )
                            resolved_st = True
                        if resolved_st:
                            stats["spread"] += 1

                # Fallback: 3-outcome winner markets with a Tie (Team A / Team B / Tie)
                # e.g. KXNCAAMB1HWINNER has 3 outcomes, so the len==2 fallback above
                # skips it entirely and these sit at pass2_guess. Resolve from
                # (half-time, for 1H) scores including the tie case. Purely additive —
                # the 2-outcome path is untouched.
                if not resolved_st and len(outcomes_list) == 3:
                    if is_1h:
                        h1_scores = await _get_halftime_score(session, row.event_id)
                        h_score, a_score = h1_scores if h1_scores else (None, None)
                    else:
                        h_score, a_score = row.home_score, row.away_score

                    decision = _decide_three_way_winner(
                        [oc.name for oc in outcomes_list],
                        row.home_team_name,
                        row.away_team_name,
                        h_score,
                        a_score,
                    )
                    if decision is not None:
                        for idx, oc in enumerate(outcomes_list):
                            await session.execute(
                                text(
                                    "UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'game_score', last_updated = NOW() WHERE id = :oid"
                                ),
                                {"won": decision[idx], "oid": oc.id},
                            )
                        resolved_st = True
                        stats["spread"] += 1

                if not resolved_st:
                    stats["no_parse"] += 1

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Kalshi spread/total resolution error: %s", e)

    resolved = stats["spread"] + stats["total"] + stats["h1_spread"] + stats["h1_total"]
    logger.info(
        "Kalshi spread/total resolution: %d resolved (spread=%d, total=%d, "
        "h1_spread=%d, h1_total=%d), %d no_plays, %d no_parse, %d errors",
        resolved,
        stats["spread"],
        stats["total"],
        stats["h1_spread"],
        stats["h1_total"],
        stats["no_plays"],
        stats["no_parse"],
        len(stats["errors"]),
    )
    return stats


async def _regrade_golf_extra_winners():
    """#938: Clear stale settlement_sync EXTRA winners on golf field markets.

    settlement_sync set is_winner=(current_probability>=0.95) for ALL golf
    outcomes; on illiquid multi-candidate fields the "price" is a stale one-
    sided YES-ask (candidates frozen at 99% with no bid/trade), so it promoted
    bogus extra winners ON TOP of DataGolf's correct winner(s). The settlement_
    sync block in _backfill_all_winners now guards against this AND re-grades,
    but that block lives deep in the 14-min pipeline and is starved before it
    runs (same #898 starvation that forced authoritative resolution to the top).
    Running the idempotent re-grade here, in the fast resolve_winners task,
    guarantees it executes.

    Flips ONLY settlement_sync extras to False, and only on markets that retain
    an authoritative (leaderboard/api/datagolf/score) winner — never the
    authoritative winner itself, never winner-less (gotcha #21: no bulk reset).
    Write-on-change; scoped to the golf field cohort (no broad in-memory pull,
    #899 OOM caution).
    """
    stats = {"cleared": 0, "errors": []}
    try:
        async with get_task_session() as session:
            r = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET is_winner = false, last_updated = NOW()
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'kalshi'
                      AND fm.llm_sport_category = 'golf'
                      AND fm.status = 'resolved'
                      AND fo.is_winner = true
                      AND fo.resolution_source = 'settlement_sync'
                      AND EXISTS (
                          SELECT 1 FROM futures_outcomes fo2
                          WHERE fo2.market_id = fm.id
                            AND fo2.is_winner = true
                            -- #845 batch 3: bespoke golf "a real authoritative/
                            -- deterministic winner exists" set — intentionally
                            -- NOT the full authority tier (golf never resolves via
                            -- box_score/scoring_plays/clob_*), so it is kept
                            -- context-specific rather than force-fit to the
                            -- ladder. Dropped the dead 'datagolf' source (never
                            -- written — resolution_source uses datagolf_settlement
                            -- / datagolf_matchup; verified absent from prod).
                            AND fo2.resolution_source IN
                                ('leaderboard', 'api_settlement',
                                 'datagolf_matchup', 'game_score')
                      )
                """))
            stats["cleared"] = r.rowcount
            await session.commit()
        if stats["cleared"]:
            logger.info(
                "Golf extra-winner re-grade (#938): cleared %d stale settlement_sync winners",
                stats["cleared"],
            )
    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Golf extra-winner re-grade error: %s", e)
    return stats


async def _regrade_kalshi_nhl_spread_inversions():
    """#939: One-shot, idempotent re-grade of NHL spread outcomes left inverted
    by the OLD complementary spread resolver.

    The prior logic resolved only the first matching "{team} wins by over N"
    outcome, flipped every sibling to ``not won``, and broke — so whole
    KXNHLSPREAD markets were marked all-True or all-False by insertion order
    (game_score cohort: predicted 25% but actual win rate ~72%). The resolver
    is now fixed to grade each outcome independently, but the already-resolved
    rows are pinned True/False and the main resolver's HAVING clause skips any
    market that still holds a game_score ``is_winner=True`` — so they never get
    re-pulled. This corrects them directly.

    Each outcome wins iff the named team's actual margin exceeds ITS OWN line.
    Scoped to the Kalshi NHL/NBA/MLB SPREAD game_score cohort and write-on-change.
    (#944: broadened from NHL-only — the #939 complementary-flip fix shipped the
    generic resolver but only NHL got this targeted re-grade, so NBA/MLB spread
    game_score stayed inverted ~63-72%; the main resolver's HAVING clause skips
    already-resolved markets, so they were never re-pulled. This also re-resolves
    markets whose event_id was corrected by the #944 relink against the now-right
    game.) resolution_source stays ``game_score`` — re-resolve from authoritative
    scores in place, never a bare ``is_winner`` reset (gotcha #21, #899 cohort scope).
    """
    stats = {"checked": 0, "flipped": 0, "errors": []}
    try:
        async with get_task_session() as session:
            rows = await session.execute(text("""
                SELECT fo.id AS oid, fo.name AS oc_name, fo.is_winner AS cur,
                       e.home_team_name AS home, e.away_team_name AS away,
                       e.home_score AS hs, e.away_score AS as_
                FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                JOIN events e ON e.id = fm.event_id
                WHERE fm.source = 'kalshi'
                  AND fm.external_id ~ '^KX(NHL|NBA|MLB)SPREAD'
                  AND fo.resolution_source = 'game_score'
                  AND e.home_score IS NOT NULL
                  AND e.away_score IS NOT NULL
            """))
            for r in rows.all():
                stats["checked"] += 1
                won = _spread_outcome_is_winner(
                    r.oc_name, r.home, r.away, r.hs, r.as_
                )
                if won is None:
                    continue
                # write-on-change: skip rows already on the correct side
                if r.cur is not None and bool(r.cur) == won:
                    continue
                await session.execute(
                    text(
                        "UPDATE futures_outcomes SET is_winner = :won, last_updated = NOW() WHERE id = :oid"
                    ),
                    {"won": won, "oid": r.oid},
                )
                stats["flipped"] += 1
            await session.commit()
        if stats["flipped"]:
            logger.info(
                "NHL spread inversion re-grade (#939): flipped %d of %d game_score outcomes",
                stats["flipped"],
                stats["checked"],
            )
    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("NHL spread inversion re-grade error: %s", e)
    return stats


async def _regrade_kalshi_total_inversions():
    """#945: idempotent re-grade of Kalshi NHL/NBA/MLB TOTAL game_score outcomes
    that are stale/inverted vs the linked event's final score.

    Mirrors the spread re-grade (#939/#944). Kalshi TOTAL game_score `is_winner`
    was set by the old complementary-flip bug and/or against pre-#944-relink
    events, and the spread/total resolver's HAVING clause skips already-resolved
    markets so these were never re-pulled (2026-06-17: KXMLBTOTAL 67.9%,
    KXNBATOTAL 67.4%, KXNHLTOTAL 49.7% disagree vs final scores; the #755 re-null
    regex excludes plain "TOTAL", so #944's relink did not churn them). #944 has
    already corrected the event links, so recomputing from the linked event's
    home+away total is sound.

    "Over/Under N scored" wins per gotcha #17 (OVER unless Under/No). Write-on-
    change; resolution_source STAYS game_score; never a bare reset (gotcha #21).
    Bounded to the KXxxxTOTAL game_score cohort (#899). Runs in resolve_winners
    (the fast every-2h path) so it forward-fixes and is idempotent. Do NOT trigger
    the broad backfill_winners to refresh — its #755 re-null churns the cohort.
    """
    stats = {"checked": 0, "flipped": 0, "errors": []}
    try:
        async with get_task_session() as session:
            rows = await session.execute(text("""
                SELECT fo.id AS oid, fo.name AS oc_name, fo.is_winner AS cur,
                       e.home_score AS hs, e.away_score AS as_
                FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                JOIN events e ON e.id = fm.event_id
                WHERE fm.source = 'kalshi'
                  AND fm.external_id ~ '^KX(NHL|NBA|MLB)TOTAL'
                  AND fo.resolution_source = 'game_score'
                  AND e.home_score IS NOT NULL
                  AND e.away_score IS NOT NULL
            """))
            for r in rows.all():
                stats["checked"] += 1
                won = _total_outcome_is_winner(r.oc_name, r.hs, r.as_)
                if won is None:
                    continue
                # write-on-change: skip rows already on the correct side
                if r.cur is not None and bool(r.cur) == won:
                    continue
                await session.execute(
                    text(
                        "UPDATE futures_outcomes SET is_winner = :won, last_updated = NOW() WHERE id = :oid"
                    ),
                    {"won": won, "oid": r.oid},
                )
                stats["flipped"] += 1
            await session.commit()
        if stats["flipped"]:
            logger.info(
                "Kalshi TOTAL inversion re-grade (#945): flipped %d of %d game_score outcomes",
                stats["flipped"],
                stats["checked"],
            )
    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Kalshi TOTAL inversion re-grade error: %s", e)
    return stats


async def _regrade_polymarket_under_signflip():
    """#137 Item 1: fix the Polymarket "Under"/"No" sign-flip class.

    The decomposed-game-market writer (polymarket.py) stamped the OVER/YES side's
    probability as the Under/No outcome's opening_probability, and wrote no
    snapshot for the Under side, so calibration_probability (which falls back to
    opening_probability) inherited the wrong side. Signature: the Under/No
    outcome's cp equals its Over/Yes sibling's cp (both hold the over prob)
    instead of summing to ~1.

    Verified in prod (2026-07-08): 26,756 such poly outcomes, cp==over sibling,
    winning only ~25% (graded subset ~54% ≈ balanced — the low aggregate is a
    separate under-grading gap, NOT touched here per gotcha #21). The Under's
    current_probability already holds the correct value (1 - over), confirming
    the flip is right.

    Fix: flip BOTH calibration_probability and opening_probability to 1 - value
    (flipping only cp would spuriously flip price_moved to TRUE, since it compares
    cp vs opening). The Over/Yes sibling is already correct, so flipping only the
    Under/No side restores sum≈1.

    Safe + idempotent: only touches rows whose cp still equals the over sibling's
    (the bug state); after the flip cp no longer matches, so a re-run is a no-op.
    Excludes the both-sides=1.0 class (handled by the opening-artifact repair) and
    the tiny 0.49–0.51 band (near-50/50, ~0 impact, the only oscillation risk).
    """
    stats = {"cp_flipped": 0, "errors": []}
    try:
        async with get_task_session() as session:
            result = await session.execute(text("""
                UPDATE futures_outcomes u
                SET calibration_probability = 1.0 - u.calibration_probability,
                    opening_probability = CASE
                        WHEN u.opening_probability IS NOT NULL
                             AND u.opening_probability > 0.001
                             AND u.opening_probability < 0.999
                        THEN 1.0 - u.opening_probability
                        ELSE u.opening_probability
                    END,
                    last_updated = NOW()
                FROM futures_markets m
                WHERE u.market_id = m.id
                  AND m.source = 'polymarket'
                  AND (u.name ILIKE 'under%' OR u.name = 'No')
                  AND u.calibration_probability IS NOT NULL
                  AND u.calibration_probability > 0.001
                  AND u.calibration_probability < 0.999
                  AND (u.calibration_probability < 0.49
                       OR u.calibration_probability > 0.51)
                  AND EXISTS (
                      SELECT 1 FROM futures_outcomes o
                      WHERE o.market_id = u.market_id
                        AND o.id <> u.id
                        AND (o.name ILIKE 'over%' OR o.name = 'Yes')
                        AND o.calibration_probability IS NOT NULL
                        AND ABS(u.calibration_probability
                                - o.calibration_probability) < 0.02
                  )
            """))
            await session.commit()
            stats["cp_flipped"] = result.rowcount
        if stats["cp_flipped"]:
            logger.info(
                "Polymarket Under sign-flip re-grade (#137): flipped %d outcomes",
                stats["cp_flipped"],
            )
    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Polymarket Under sign-flip re-grade error: %s", e)
    return stats


async def _unresolve_datagolf_premature():
    """#137 Item 2a: un-resolve DataGolf markets resolved before their event.

    A live-completion heuristic / schedule glitch flipped some DataGolf markets to
    status='resolved' and copied opening_probability into calibration_probability
    (cp=1.0) while the tournament's resolution_date is still in the FUTURE and no
    authoritative resolution_source was ever attached. Verified in prod
    (2026-07-08): 230 outcomes across 10 markets, all is_winner=false.

    These were never validly resolved, so reverting is correct (NOT a bulk reset
    of real winners — gotcha #21). Revert the market to 'open' and null the bogus
    calibration_probability so it leaves the calibration curve until the event
    actually resolves. is_winner is left as-is (already false; we never guess).
    """
    stats = {"markets_reopened": 0, "cp_nulled": 0, "errors": []}
    try:
        async with get_task_session() as session:
            null_res = await session.execute(text("""
                UPDATE futures_outcomes fo
                SET calibration_probability = NULL, last_updated = NOW()
                FROM futures_markets fm
                WHERE fo.market_id = fm.id
                  AND fm.source = 'datagolf'
                  AND fm.status = 'resolved'
                  AND fm.resolution_date > NOW()
                  AND fo.resolution_source IS NULL
                  AND fo.calibration_probability IS NOT NULL
            """))
            mkt_res = await session.execute(text("""
                UPDATE futures_markets fm
                SET status = 'open'
                WHERE fm.source = 'datagolf'
                  AND fm.status = 'resolved'
                  AND fm.resolution_date > NOW()
                  AND EXISTS (
                      SELECT 1 FROM futures_outcomes fo
                      WHERE fo.market_id = fm.id
                        AND fo.resolution_source IS NULL
                  )
            """))
            await session.commit()
            stats["cp_nulled"] = null_res.rowcount
            stats["markets_reopened"] = mkt_res.rowcount
        if stats["cp_nulled"] or stats["markets_reopened"]:
            logger.info(
                "DataGolf premature un-resolve (#137): reopened %d markets, "
                "nulled %d cp",
                stats["markets_reopened"],
                stats["cp_nulled"],
            )
    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("DataGolf premature un-resolve error: %s", e)
    return stats


async def _null_impossible_both_sides_openings():
    """#137 Item 2b: null impossible both-sides=1.0 binary openings.

    A binary market cannot have BOTH outcomes open at probability 1.0 — that is a
    corrupt/settled-placeholder capture (the same poly writer bug, now fixed at
    source with a 0<prob<1 opening guard). Verified in prod (2026-07-08): 19,653
    such binaries = 39,306 outcomes. Leaving them poisons both the calibration
    curve (adj_opening = COALESCE(cp, opening) = 1.0) and the price_moved
    dimension.

    Null opening_probability (+ its odds/source) on every outcome of a both-1.0
    binary. Also null calibration_probability where it is likewise an impossible
    1.0 — otherwise nulling only the opening would flip price_moved to TRUE
    (cp NOT NULL vs opening NULL) and keep an impossible certain price in the
    curve. Real sub-1.0 closing lines (a tiny tail) are kept.
    """
    stats = {"openings_nulled": 0, "cp_nulled": 0, "errors": []}
    try:
        async with get_task_session() as session:
            # Null impossible-certain cp FIRST, while openings still = 1.0 so the
            # both-1.0 binaries are still identifiable. Any cp>=0.999 in such a
            # binary is impossible and would trip price_moved once its opening is
            # nulled below.
            cp_res = await session.execute(text("""
                UPDATE futures_outcomes fo
                SET calibration_probability = NULL, last_updated = NOW()
                WHERE fo.calibration_probability >= 0.999
                  AND fo.market_id IN (
                      SELECT market_id FROM futures_outcomes
                      GROUP BY market_id
                      HAVING COUNT(*) = 2
                         AND SUM(CASE WHEN opening_probability >= 0.999
                                      THEN 1 ELSE 0 END) = 2
                  )
            """))
            # Then null the impossible both-1.0 openings themselves.
            open_res = await session.execute(text("""
                UPDATE futures_outcomes fo
                SET opening_probability = NULL,
                    opening_american_odds = NULL,
                    opening_captured_at = NULL,
                    opening_source = NULL,
                    last_updated = NOW()
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.market_id IN (
                      SELECT market_id FROM futures_outcomes
                      GROUP BY market_id
                      HAVING COUNT(*) = 2
                         AND SUM(CASE WHEN opening_probability >= 0.999
                                      THEN 1 ELSE 0 END) = 2
                  )
            """))
            await session.commit()
            stats["cp_nulled"] = cp_res.rowcount
            stats["openings_nulled"] = open_res.rowcount
        if stats["openings_nulled"] or stats["cp_nulled"]:
            logger.info(
                "Impossible both-1.0 opening repair (#137): nulled %d openings, "
                "%d cp",
                stats["openings_nulled"],
                stats["cp_nulled"],
            )
    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Impossible both-1.0 opening repair error: %s", e)
    return stats


async def _correct_both_winner_guess_side():
    """#997: demote the GUESS side of a both-winner mutually-exclusive binary.

    A mutually-exclusive 2-outcome market (moneyline, set-winner, head-to-head)
    can have exactly ONE winner. Verified in prod (2026-07-09): 580 outcomes sit
    in such markets where BOTH outcomes are is_winner=true — one graded by an
    authoritative source (clean_resolution / game_score) and the other by a
    tier-0 guess (pass2_guess). The guess wrongly stood as a co-winner, poisoning
    calibration (two winners summing >1). Examples: "Missouri at Arkansas"
    (game_score=Missouri, pass2_guess=Arkansas both won), tennis Set-1 winners.

    Fix (authority ladder, #845): flip the guess side to is_winner=false when its
    sibling is a strictly-higher-authority winner. A guess must never overwrite
    or co-exist with a non-guess resolution (#754 poison guard). We do NOT assert
    a NEW winner (the authoritative side already IS the winner) and we do NOT
    touch resolution_source — only the wrong is_winner flag flips, so the write
    is minimal and idempotent (once is_winner=false the row no longer matches).

    Deliberately narrow — the guess side is SINGLE_WINNER_GUESS_SOURCES
    (pass3_threshold EXCLUDED: cumulative-threshold ladders like "Over 3.5 maps"
    + "Over 4.5 maps" are LEGITIMATELY both-YES). The sibling must be a non-guess
    (GUESS_FAMILY_SOURCES excluded, incl. pass3_threshold) winner, so both-guess
    and both-authoritative both-winner markets are left for evidence review, never
    guessed at (gotcha #21). mutually_exclusive=false ladders are skipped too.
    """
    stats = {"flipped": 0, "candidates": 0, "batches": 0, "errors": []}
    try:
        # Read-side FIRST: identify the guess-side winner outcomes to demote. The
        # heavy correlated predicate (two self-subqueries over futures_outcomes)
        # runs ONCE here as a ~3s read, NOT re-planned per-row inside a long-held
        # UPDATE. The original single monolithic UPDATE evaluated the correlated
        # subqueries while acquiring row locks (contending with the live poller)
        # and ran >120s every cycle, tripping the task soft_time_limit before it
        # could commit — so it NEVER once flipped a row in prod (#997/#157). We
        # never assert a NEW winner (the authoritative sibling already IS the
        # winner) and never touch resolution_source (#754 poison guard); only the
        # wrong is_winner flag flips, so the write is minimal and idempotent.
        async with get_task_session() as session:
            rows = await session.execute(text("""
                SELECT u.id
                FROM futures_outcomes u
                JOIN futures_markets m ON u.market_id = m.id
                WHERE m.mutually_exclusive = true
                  AND u.is_winner = true
                  AND u.resolution_source IN """ + SINGLE_WINNER_GUESS_SOURCES_SQL + """
                  AND (SELECT COUNT(*) FROM futures_outcomes c
                       WHERE c.market_id = u.market_id) = 2
                  AND EXISTS (
                      SELECT 1 FROM futures_outcomes o
                      WHERE o.market_id = u.market_id
                        AND o.id <> u.id
                        AND o.is_winner = true
                        AND o.resolution_source IS NOT NULL
                        AND o.resolution_source NOT IN """ + GUESS_FAMILY_SOURCES_SQL + """
                  )
            """))
            ids = [r[0] for r in rows.fetchall()]
        stats["candidates"] = len(ids)

        # Write-side: tiny id-keyed UPDATEs committed per batch, so partial
        # progress persists and no single statement holds locks long enough to
        # trip the soft limit (bounds the longest uninterrupted op — mirrors the
        # gotcha #13 per-market commit pattern). Idempotent: a row already
        # is_winner=false won't rematch on the next cycle.
        BATCH = 200
        for i in range(0, len(ids), BATCH):
            chunk = ids[i:i + BATCH]
            async with get_task_session() as session:
                result = await session.execute(
                    text(
                        "UPDATE futures_outcomes SET is_winner = false, "
                        "last_updated = NOW() "
                        "WHERE id = ANY(:ids) AND is_winner = true"
                    ),
                    {"ids": chunk},
                )
                await session.commit()
                stats["flipped"] += result.rowcount
            stats["batches"] += 1
        if stats["flipped"]:
            logger.info(
                "Both-winner guess-side correction (#997): flipped %d guess "
                "outcomes to loser across %d batches",
                stats["flipped"], stats["batches"],
            )
    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Both-winner guess-side correction error: %s", e)
    return stats


async def _get_halftime_score(session, event_id: int):
    """Reconstruct halftime score from scoring_plays or box_score_data period scores."""
    result = await session.execute(
        text("""
            SELECT home_score, away_score
            FROM scoring_plays
            WHERE event_id = :eid
              AND LOWER(period) = ANY(:periods)
            ORDER BY captured_at DESC
            LIMIT 1
        """),
        {"eid": event_id, "periods": list(_FIRST_HALF_PERIODS)},
    )
    row = result.first()
    if row:
        return (row.home_score, row.away_score)

    from app.models.models import Event as _Evt
    evt_result = await session.execute(
        select(_Evt.box_score_data).where(_Evt.id == event_id)
    )
    box = evt_result.scalar_one_or_none()
    if box and isinstance(box, dict):
        h_periods = box.get("home_period_scores", [])
        a_periods = box.get("away_period_scores", [])
        # Require >=2 periods so period[0] is a genuinely COMPLETED first half,
        # not a single in-progress/malformed linescore (#816). A finished 2-half
        # game has >=2 entries ([H1, H2, ...OT]); OT periods don't move index 0.
        if len(h_periods) >= 2 and len(a_periods) >= 2:
            return (h_periods[0], a_periods[0])

    return None


_PROP_TICKER_TO_STAT = {
    "kxnbapts": "points",
    "kxnbaast": "assists",
    "kxnbareb": "rebounds",
    "kxnbablk": "blocks",
    "kxnbastl": "steals",
    "kxnba3pt": "three pointers",
    "kxnhlgoal": "goals",
    "kxnhlanygoal": "goals",
    "kxnhlast": "assists",
    "kxnhlsaves": "saves",
    "kxmlbhit": "hits",
    "kxmlbhr": "home runs",
    "kxmlbks": "strikeouts",
    "kxnba2d": "double doubles",
}

_PROP_RE = re.compile(r"^(.+?):\s*(\d+)\+\s*$")


def _normalize_player_name(name: str) -> str:
    from app.utils.name_normalization import strip_diacritics

    n = strip_diacritics(name).lower().strip()
    n = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)\s*$", "", n, flags=re.IGNORECASE)
    n = n.replace(".", "").replace("'", "").replace("'", "")
    return " ".join(n.split())


_COMBO_STATS = {
    "kxnbapa": ["points", "assists"],
    "kxnbapr": ["points", "rebounds"],
    "kxnbapra": ["points", "rebounds", "assists"],
    "kxnbara": ["rebounds", "assists"],
    # NHL points = goals + assists. ESPN box scores store goals and assists
    # separately and have NO "points" field, so mapping kxnhlpts to a singular
    # "points" stat always returned 0 -> every points prop graded a loser (#937).
    "kxnhlpts": ["goals", "assists"],
}


async def _resolve_kalshi_player_props_from_boxscore():
    """Resolve Kalshi player prop markets from ESPN box score data.

    Single-query fetch of all markets + outcomes + box scores, then
    processes in Python. No per-market DB round-trips.
    """
    stats = {"resolved": 0, "no_player": 0, "no_parse": 0, "errors": []}

    all_prop_prefixes = list(_PROP_TICKER_TO_STAT.keys()) + list(_COMBO_STATS.keys())

    try:
        async with get_task_session() as session:
            # #899: do NOT join e.box_score_data onto every outcome row. The box
            # score JSONB (all players' stats) was re-deserialized per outcome and
            # result.all() held every copy at once → OOM on the 200MB worker child
            # (the id()-keyed cache below couldn't dedup distinct deserialized
            # objects). That OOM forced the #937 re-grade to stay scoped to
            # kxnhlpts. Fetch the SMALL outcome rows here (no JSONB), then load each
            # event's box score ONCE in bounded batches so peak memory is
            # O(batch of events), not O(all outcomes x JSONB) — letting #937 broaden
            # the re-grade beyond kxnhlpts without re-introducing the OOM.
            result = await session.execute(
                text("""
                    SELECT fo.id AS outcome_id, fo.name AS outcome_name,
                           fm.external_id AS ticker, fo.is_winner AS cur_winner,
                           e.id AS event_id
                    FROM futures_outcomes fo
                    JOIN futures_markets fm ON fm.id = fo.market_id
                    JOIN events e ON e.id = fm.event_id
                    WHERE fm.status = 'resolved'
                      AND e.box_score_data IS NOT NULL
                      AND (fo.resolution_source IS NULL
                           OR fo.resolution_source IN
                               """ + OVERWRITABLE_WINNER_SOURCES_SQL + """
                           -- #937: re-process ALL already box_score-resolved prop
                           -- outcomes (was scoped to kxnhlpts only to dodge the #899
                           -- OOM — now fixed, so the broadened set is memory-safe).
                           -- Catches the same class of historical mis-grades beyond
                           -- NHL points (reproduced under-marking: hockey ~38pp,
                           -- baseball ~21pp). Every _PROP_TICKER_TO_STAT mapping is
                           -- verified against the authoritative ESPN stat-key map
                           -- (services/espn_api.py: H->hits, HR->home runs,
                           -- SO->strikeouts, G->goals, A->assists, ...), and the
                           -- write is idempotent (only flips when the box_score
                           -- verdict CHANGES, gotcha #21-safe). Re-grade reads the
                           -- event's OWN box score by player+stat — not an event
                           -- linkage, so no #942/#14 commence_time-collapse risk.
                           OR fo.resolution_source = 'box_score')
                      AND LOWER(fm.external_id) LIKE ANY(:prefixes)
                    ORDER BY e.id
                    LIMIT 50000
                """),
                {"prefixes": [p + "%" for p in all_prop_prefixes]},
            )
            from collections import defaultdict as _defaultdict
            rows = result.all()  # small now — no box_score JSONB
            by_event: dict = _defaultdict(list)
            for row in rows:
                by_event[row.event_id].append(row)

            winner_ids = []
            loser_ids = []
            event_ids = list(by_event.keys())
            _BS_BATCH = 100  # events per box_score load — bounds peak RSS (#899)
            for _i in range(0, len(event_ids), _BS_BATCH):
                batch_ids = event_ids[_i:_i + _BS_BATCH]
                bs_result = await session.execute(
                    text("SELECT id, box_score_data FROM events WHERE id = ANY(:ids)"),
                    {"ids": batch_ids},
                )
                # parse each event's box score ONCE, keyed by event_id
                bs_map: dict = {}
                for bs_row in bs_result.all():
                    raw_bs = bs_row.box_score_data or {}
                    raw_players = (
                        raw_bs.get("players", raw_bs)
                        if isinstance(raw_bs, dict)
                        else {}
                    )
                    bs_map[bs_row.id] = {
                        _normalize_player_name(k): v for k, v in raw_players.items()
                    }

                for ev_id in batch_ids:
                    norm_box = bs_map.get(ev_id)
                    if not norm_box:
                        continue
                    for row in by_event[ev_id]:
                        ticker_lower = (row.ticker or "").lower()

                        stat_name = None
                        combo_stats = None
                        for prefix, stat in _PROP_TICKER_TO_STAT.items():
                            if ticker_lower.startswith(prefix):
                                stat_name = stat
                                break
                        if not stat_name:
                            for prefix, stat_list in _COMBO_STATS.items():
                                if ticker_lower.startswith(prefix):
                                    combo_stats = stat_list
                                    break
                        if not stat_name and not combo_stats:
                            continue

                        m = _PROP_RE.match(row.outcome_name or "")
                        if m:
                            player_name = m.group(1).strip()
                            threshold = int(m.group(2))
                        elif stat_name in ("double doubles", "triple doubles"):
                            player_name = (row.outcome_name or "").strip()
                            threshold = 1
                        else:
                            stats["no_parse"] += 1
                            continue

                        player_norm = _normalize_player_name(player_name)
                        player_stats = norm_box.get(player_norm)

                        if player_stats is None and "," in player_name:
                            parts = player_name.split(",", 1)
                            flipped_norm = _normalize_player_name(
                                f"{parts[1].strip()} {parts[0].strip()}"
                            )
                            player_stats = norm_box.get(flipped_norm)

                        if player_stats is None:
                            stats["no_player"] += 1
                            continue

                        if combo_stats:
                            actual = sum(player_stats.get(s, 0) for s in combo_stats)
                        else:
                            actual = player_stats.get(stat_name, 0)

                        if actual is None:
                            stats["no_player"] += 1
                            continue

                        verdict = actual >= threshold
                        # Skip rows already correct (idempotent re-grade): only write
                        # when the authoritative verdict differs from the stored value
                        # — avoids re-touching already-correct box_score rows every
                        # cycle while letting a mapping fix flip mis-resolved ones.
                        if row.cur_winner is not None and bool(row.cur_winner) == verdict:
                            continue
                        if verdict:
                            winner_ids.append(row.outcome_id)
                        else:
                            loser_ids.append(row.outcome_id)

                bs_map.clear()  # release this batch's box scores before the next

            if winner_ids:
                await session.execute(
                    text(
                        "UPDATE futures_outcomes SET is_winner = true, resolution_source = 'box_score', last_updated = NOW() WHERE id = ANY(:ids)"
                    ),
                    {"ids": winner_ids},
                )
            if loser_ids:
                await session.execute(
                    text(
                        "UPDATE futures_outcomes SET is_winner = false, resolution_source = 'box_score', last_updated = NOW() WHERE id = ANY(:ids)"
                    ),
                    {"ids": loser_ids},
                )
            stats["resolved"] = len(winner_ids) + len(loser_ids)
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Player prop resolution error: %s", e)

    logger.info(
        "Player prop resolution: %d resolved, %d no_player, %d no_parse, %d errors",
        stats["resolved"],
        stats["no_player"],
        stats["no_parse"],
        len(stats["errors"]),
    )
    return stats


def _total_bases_verdict(hits: int, hr: int, threshold: int) -> bool | None:
    """Resolve a 'total bases >= threshold' outcome from hits + HR alone.

    ESPN gives hits (H) and home runs (R, a subset of hits) but not
    doubles/triples, so exact total bases is unknown. It is bounded by:
        TB_min = H + 3*R   (non-HR hits all singles)
        TB_max = 3*H + R   (non-HR hits all triples)
    Returns True (certain winner), False (certain loser), or None
    (indeterminate — leave unresolved).
    """
    tb_min = hits + 3 * hr
    tb_max = 3 * hits + hr
    if tb_max < threshold:
        return False
    if tb_min >= threshold:
        return True
    return None


async def _resolve_kalshi_total_bases_from_boxscore():
    """Resolve Kalshi MLB total-bases (KXMLBTB) props by deterministic bounds.

    ESPN box scores give hits + home runs but NOT doubles/triples, so exact
    total bases can't be computed (#802). But total bases is bounded by what we
    DO have: with H hits and R home runs (HR are a subset of hits),

        TB_min = H + 3*R   (every non-HR hit is a single)
        TB_max = 3*H + R   (every non-HR hit is a triple)

    For a "Player: N+" outcome (TB >= N):
      * TB_max < N  -> certain LOSER  (even the best case can't reach N)
      * TB_min >= N -> certain WINNER (even the worst case reaches N)
      * otherwise   -> indeterminate, leave unresolved.

    This safely resolves the determinable fraction of the 861 KXMLBTB outcomes
    (e.g. 0-hit games are certain losers for any N>=1; multi-hit/HR games are
    certain winners for low N) without doubles/triples. Marked
    resolution_source='box_score_bound' so it's auditable as a bound, not exact.
    """
    stats = {"resolved": 0, "no_player": 0, "no_parse": 0, "indeterminate": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    SELECT fo.id AS outcome_id, fo.name AS outcome_name,
                           e.box_score_data
                    FROM futures_outcomes fo
                    JOIN futures_markets fm ON fm.id = fo.market_id
                    JOIN events e ON e.id = fm.event_id
                    WHERE fm.status = 'resolved'
                      AND e.box_score_data IS NOT NULL
                      AND fo.is_winner IS NULL
                      AND LOWER(fm.external_id) LIKE 'kxmlbtb%'
                    ORDER BY fm.id
                    LIMIT 50000
                """),
            )
            rows = result.all()

            winner_ids = []
            loser_ids = []
            _bs_cache = {}
            for row in rows:
                m = _PROP_RE.match(row.outcome_name or "")
                if not m:
                    stats["no_parse"] += 1
                    continue
                player_name = m.group(1).strip()
                threshold = int(m.group(2))

                bs_id = id(row.box_score_data)
                if bs_id not in _bs_cache:
                    raw_bs = row.box_score_data or {}
                    raw_players = (
                        raw_bs.get("players", raw_bs)
                        if isinstance(raw_bs, dict)
                        else {}
                    )
                    _bs_cache[bs_id] = {
                        _normalize_player_name(k): v for k, v in raw_players.items()
                    }
                norm_box = _bs_cache[bs_id]

                player_norm = _normalize_player_name(player_name)
                player_stats = norm_box.get(player_norm)
                if player_stats is None and "," in player_name:
                    parts = player_name.split(",", 1)
                    player_stats = norm_box.get(
                        _normalize_player_name(f"{parts[1].strip()} {parts[0].strip()}")
                    )
                if player_stats is None:
                    stats["no_player"] += 1
                    continue

                hits = player_stats.get("hits") or 0
                hr = player_stats.get("home runs") or 0
                verdict = _total_bases_verdict(hits, hr, threshold)

                if verdict is False:
                    loser_ids.append(row.outcome_id)
                elif verdict is True:
                    winner_ids.append(row.outcome_id)
                else:
                    stats["indeterminate"] += 1

            if winner_ids:
                await session.execute(
                    text(
                        "UPDATE futures_outcomes SET is_winner = true, resolution_source = 'box_score_bound', last_updated = NOW() WHERE id = ANY(:ids)"
                    ),
                    {"ids": winner_ids},
                )
            if loser_ids:
                await session.execute(
                    text(
                        "UPDATE futures_outcomes SET is_winner = false, resolution_source = 'box_score_bound', last_updated = NOW() WHERE id = ANY(:ids)"
                    ),
                    {"ids": loser_ids},
                )
            stats["resolved"] = len(winner_ids) + len(loser_ids)
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Total-bases bound resolution error: %s", e)

    logger.info(
        "Total-bases bound resolution: %d resolved, %d indeterminate, %d no_player, %d no_parse, %d errors",
        stats["resolved"],
        stats["indeterminate"],
        stats["no_player"],
        stats["no_parse"],
        len(stats["errors"]),
    )
    return stats


async def _resolve_kalshi_period_props():
    """Resolve Kalshi 1H/2H/quarter/F5 markets from scoring_plays data.

    Reconstructs period scores from the scoring_plays table and applies
    winner/spread/total logic for the specific period.
    """
    stats = {"resolved": 0, "no_plays": 0, "no_parse": 0, "errors": []}

    _period_map = {
        "1h": {"q1", "q2", "1q", "2q", "1st", "2nd", "1st half", "first half", "1h"},
        "2h": {
            "q3",
            "q4",
            "3q",
            "4q",
            "3rd",
            "4th",
            "2nd half",
            "second half",
            "2h",
            "ot",
        },
        "1q": {"q1", "1q", "1st"},
        "2q": {"q2", "2q", "2nd"},
        "3q": {"q3", "3q", "3rd"},
        "4q": {"q4", "4q", "4th"},
    }

    try:
        async with get_task_session() as session:
            result = await session.execute(text("""
                    SELECT fm.id AS market_id, fm.external_id AS ticker,
                           fm.name AS market_name,
                           e.id AS event_id,
                           e.home_team_name, e.away_team_name,
                           e.home_score AS final_home, e.away_score AS final_away
                    FROM futures_markets fm
                    JOIN events e ON e.id = fm.event_id
                    JOIN futures_outcomes fo ON fo.market_id = fm.id
                    WHERE fm.status = 'resolved'
                      AND e.status IN ('completed', 'closed')
                      AND e.home_score IS NOT NULL
                      AND EXISTS (SELECT 1 FROM scoring_plays sp WHERE sp.event_id = e.id)
                    GROUP BY fm.id, fm.external_id, fm.name,
                             e.id, e.home_team_name, e.away_team_name,
                             e.home_score, e.away_score
                    HAVING SUM(CASE WHEN fo.is_winner
                               AND fo.resolution_source NOT IN
                                   """ + OVERWRITABLE_WINNER_SOURCES_SQL + """
                               THEN 1 ELSE 0 END) = 0
                       AND COUNT(*) = 1
                    LIMIT 5000
                """))
            markets = result.all()

            for row in markets:
                ticker_lower = (row.ticker or "").lower()

                # Detect period from ticker
                period_key = None
                for pk in ("1h", "2h", "1q", "2q", "3q", "4q"):
                    if pk in ticker_lower:
                        period_key = pk
                        break
                if ticker_lower.startswith("kxmlbf5"):
                    period_key = "f5"

                if not period_key:
                    continue

                # Get period score from scoring_plays
                if period_key == "f5":
                    plays = await session.execute(
                        text("""
                            SELECT home_score, away_score FROM scoring_plays
                            WHERE event_id = :eid
                              AND LOWER(period) SIMILAR TO '%(inning [1-5]|top [1-5]|bot [1-5]|[1-5]th)%'
                            ORDER BY captured_at DESC LIMIT 1
                        """),
                        {"eid": row.event_id},
                    )
                else:
                    periods = _period_map.get(period_key, set())
                    if not periods:
                        continue
                    plays = await session.execute(
                        text("""
                            SELECT home_score, away_score FROM scoring_plays
                            WHERE event_id = :eid
                              AND LOWER(period) = ANY(:periods)
                            ORDER BY captured_at DESC LIMIT 1
                        """),
                        {"eid": row.event_id, "periods": list(periods)},
                    )

                play_row = plays.first()
                if not play_row:
                    stats["no_plays"] += 1
                    continue

                period_home = play_row.home_score
                period_away = play_row.away_score

                # For 2H: subtract halftime from final
                if period_key == "2h":
                    h1_plays = await _get_halftime_score(session, row.event_id)
                    if h1_plays:
                        period_home = row.final_home - h1_plays[0]
                        period_away = row.final_away - h1_plays[1]
                    else:
                        stats["no_plays"] += 1
                        continue

                # Get the outcome and parse its name
                out = await session.execute(
                    text(
                        "SELECT id, name FROM futures_outcomes WHERE market_id = :mid LIMIT 1"
                    ),
                    {"mid": row.market_id},
                )
                outcome = out.first()
                if not outcome or not outcome.name:
                    stats["no_parse"] += 1
                    continue

                # Try spread pattern
                sm = _SPREAD_RE.search(outcome.name)
                if sm:
                    team_name = sm.group(1).strip()
                    line = float(sm.group(2))
                    home_tokens = (
                        set(row.home_team_name.lower().split())
                        if row.home_team_name
                        else set()
                    )
                    away_tokens = (
                        set(row.away_team_name.lower().split())
                        if row.away_team_name
                        else set()
                    )
                    team_tokens = set(team_name.lower().split())
                    if team_tokens & home_tokens:
                        margin = period_home - period_away
                    elif team_tokens & away_tokens:
                        margin = period_away - period_home
                    else:
                        stats["no_parse"] += 1
                        continue
                    won = margin > line
                    await session.execute(
                        text(
                            "UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'scoring_plays', last_updated = NOW() WHERE id = :oid"
                        ),
                        {"won": won, "oid": outcome.id},
                    )
                    stats["resolved"] += 1
                    continue

                # Try total pattern
                tm = _TOTAL_RE.search(outcome.name)
                if tm:
                    direction = tm.group("dir").lower()
                    line = float(tm.group(2))
                    total = period_home + period_away
                    won = total > line if direction == "over" else total < line
                    await session.execute(
                        text(
                            "UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'scoring_plays', last_updated = NOW() WHERE id = :oid"
                        ),
                        {"won": won, "oid": outcome.id},
                    )
                    stats["resolved"] += 1
                    continue

                stats["no_parse"] += 1

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Period prop resolution error: %s", e)

    logger.info(
        "Period prop resolution: %d resolved, %d no_plays, %d no_parse, %d errors",
        stats["resolved"],
        stats["no_plays"],
        stats["no_parse"],
        len(stats["errors"]),
    )
    return stats


async def _resolve_golf_from_historical_outrights():
    """Resolve DataGolf golf outcomes using historical outrights settlement data.

    Uses the DataGolf historical-odds/outrights API which returns actual
    bet outcomes (bet_outcome_numeric: 1=won, 0=lost) for each player in
    markets: win, top_5, top_10, top_20, make_cut.

    This is MORE authoritative than leaderboard inference because it uses
    the sportsbook's own settlement — no position parsing or cut-line guessing.

    Processes all tours (pga, euro, kft, liv, opp, alt) and years 2025-2026.
    """
    import asyncio
    from app.services.datagolf_api import DataGolfAPIService

    stats = {
        "events_checked": 0,
        "api_calls": 0,
        "outcomes_resolved": 0,
        "winners_set": 0,
        "losers_set": 0,
        "no_match": 0,
        "skipped_no_db_markets": 0,
        "errors": [],
    }

    # Short-circuit: check if any unresolved DataGolf outcomes exist
    async with get_task_session() as session:
        unresolved_count = await session.execute(text("""
                SELECT COUNT(*) FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                WHERE fm.source = 'datagolf'
                  AND fm.status = 'resolved'
                  AND COALESCE(fo.resolution_source, '') NOT IN
                      ('datagolf_settlement', 'api_settlement')
            """))
        if unresolved_count.scalar() == 0:
            logger.info("Golf outrights settlement: nothing to do (all resolved)")
            return stats

    service = DataGolfAPIService()
    try:
        tours = ["pga", "euro", "kft", "liv", "opp", "alt"]
        market_types = ["win", "top_5", "top_10", "top_20", "make_cut"]
        # For make_cut, also try "mc" as an alternate code
        make_cut_codes = ["make_cut", "mc"]
        # Books to try for make_cut (not all books carry all markets)
        books_to_try = ["pinnacle", "bet365", "fanduel", "betmgm"]
        years = [2026, 2025]

        for tour in tours:
            # Get event list for this tour
            event_list = await service.get_event_list(tour=tour)
            stats["api_calls"] += 1
            await asyncio.sleep(0.2)

            if not event_list:
                continue

            # Filter to relevant years
            relevant_events = []
            for ev in event_list:
                cal_year = ev.get("calendar_year") or ev.get("year")
                if cal_year and int(cal_year) in years:
                    relevant_events.append(ev)

            for event_data in relevant_events:
                event_id = str(event_data.get("event_id", ""))
                cal_year = event_data.get("calendar_year") or event_data.get("year")
                if not event_id:
                    continue

                stats["events_checked"] += 1

                # Check if we have DB markets for this event
                async with get_task_session() as session:
                    db_check = await session.execute(
                        text("""
                            SELECT COUNT(*) FROM futures_markets
                            WHERE source = 'datagolf'
                              AND external_id LIKE :prefix
                              AND status = 'resolved'
                        """),
                        {"prefix": f"datagolf:{tour}:{event_id}:%"},
                    )
                    if db_check.scalar() == 0:
                        stats["skipped_no_db_markets"] += 1
                        continue

                # Fetch outrights for each market type
                for market_type in market_types:
                    codes_to_try = (
                        make_cut_codes if market_type == "make_cut" else [market_type]
                    )

                    settlement_data = None
                    for code in codes_to_try:
                        books = books_to_try
                        for book in books:
                            rows = await service.get_historical_outrights(
                                tour=tour,
                                event_id=event_id,
                                year=int(cal_year) if cal_year else None,
                                market=code,
                                book=book,
                            )
                            stats["api_calls"] += 1
                            await asyncio.sleep(0.2)

                            if rows:
                                # Filter to rows that have bet_outcome_numeric
                                settled = [
                                    r
                                    for r in rows
                                    if r.get("bet_outcome_numeric") is not None
                                    or r.get("bet_outcome") is not None
                                ]
                                if settled:
                                    settlement_data = settled
                                    break
                        if settlement_data:
                            break

                    if not settlement_data:
                        continue

                    # Build dg_id → outcome lookup
                    dg_outcomes: dict[str, bool] = {}
                    for row in settlement_data:
                        dg_id = row.get("dg_id")
                        if dg_id is None:
                            continue
                        # bet_outcome_numeric: 1=won, 0=lost
                        outcome_val = row.get("bet_outcome_numeric")
                        if outcome_val is None:
                            outcome_val = row.get("bet_outcome")
                        if outcome_val is None:
                            continue
                        try:
                            won = int(float(outcome_val)) == 1
                        except (ValueError, TypeError):
                            continue
                        dg_outcomes[str(dg_id)] = won

                    if not dg_outcomes:
                        continue

                    # Match against DB outcomes
                    market_ext = f"datagolf:{tour}:{event_id}:{market_type}"
                    async with get_task_session() as session:
                        # Load all outcomes for this market at once
                        outcomes_result = await session.execute(
                            text("""
                                SELECT fo.id, fo.external_id
                                FROM futures_outcomes fo
                                JOIN futures_markets fm ON fm.id = fo.market_id
                                WHERE fm.source = 'datagolf'
                                  AND fm.external_id = :ext
                                  AND fm.status = 'resolved'
                                  AND COALESCE(fo.resolution_source, '') NOT IN
                                      ('datagolf_settlement', 'api_settlement')
                            """),
                            {"ext": market_ext},
                        )
                        db_outcomes = outcomes_result.all()

                        updated_any = False
                        for db_out in db_outcomes:
                            ext_id = db_out.external_id or ""
                            if not ext_id.startswith("dg_"):
                                continue
                            dg_id = ext_id[3:]

                            won = dg_outcomes.get(dg_id)
                            if won is None:
                                stats["no_match"] += 1
                                continue

                            await session.execute(
                                text("""
                                    UPDATE futures_outcomes
                                    SET is_winner = :won,
                                        resolution_source = 'datagolf_settlement',
                                        last_updated = NOW()
                                    WHERE id = :oid
                                """),
                                {"won": won, "oid": db_out.id},
                            )
                            stats["outcomes_resolved"] += 1
                            if won:
                                stats["winners_set"] += 1
                            else:
                                stats["losers_set"] += 1
                            updated_any = True

                        if updated_any:
                            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Golf outrights settlement error: %s", e)
    finally:
        await service.close()

    logger.info(
        "Golf outrights settlement: %d events checked, %d API calls, "
        "%d outcomes resolved (%d winners, %d losers), "
        "%d no_match, %d skipped, %d errors",
        stats["events_checked"],
        stats["api_calls"],
        stats["outcomes_resolved"],
        stats["winners_set"],
        stats["losers_set"],
        stats["no_match"],
        stats["skipped_no_db_markets"],
        len(stats["errors"]),
    )
    return stats


async def _backfill_datagolf_leaderboards():
    """Re-fetch full leaderboards for resolved DataGolf markets with truncated data.

    Prior to commit 137344d5, _poll_datagolf_live() truncated leaderboards to
    50 players (leaderboard[:50]). The cut line is typically ~65-70, so 20+
    players who made the cut and 50+ who missed it were never stored. This
    causes _backfill_datagolf_winners() to incorrectly infer absent players
    as losers for make_cut markets.

    This function:
    1. Finds resolved DataGolf "win" markets with leaderboards of exactly 50
       entries (the truncation signature)
    2. Re-fetches the full field from DataGolf's historical-raw-data/rounds
    3. Updates market_metadata.leaderboard on ALL market types for that event

    Only needs to run until all truncated leaderboards are fixed; after that
    it short-circuits (no API calls).
    """
    import asyncio
    import json as _json
    from app.services.datagolf_api import DataGolfAPIService

    stats = {
        "markets_checked": 0,
        "events_refetched": 0,
        "markets_updated": 0,
        "already_full": 0,
        "api_miss": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            # Find "win" markets with exactly 50-entry leaderboards (truncation signature).
            # We check win markets because all market types for the same event share
            # the same leaderboard, and win markets always have the full field.
            result = await session.execute(
                text("""
                    SELECT fm.id, fm.external_id, fm.market_metadata
                    FROM futures_markets fm
                    WHERE fm.source = 'datagolf'
                      AND fm.status = 'resolved'
                      AND fm.market_metadata IS NOT NULL
                      AND fm.external_id LIKE :win_suffix
                      AND jsonb_array_length(
                          COALESCE(fm.market_metadata->'leaderboard', '[]'::jsonb)
                      ) = 50
                """),
                {"win_suffix": "%:win"},
            )
            truncated_markets = result.all()

        if not truncated_markets:
            logger.info(
                "DataGolf leaderboard backfill: no truncated leaderboards found"
            )
            return stats

        logger.info(
            "DataGolf leaderboard backfill: %d win markets with truncated leaderboards",
            len(truncated_markets),
        )

        service = DataGolfAPIService()
        try:
            for row in truncated_markets:
                stats["markets_checked"] += 1
                ext_id = row.external_id  # "datagolf:pga:123:win"

                # Extract tour and event_id from external_id
                parts = ext_id.split(":")
                if len(parts) < 4:
                    stats["errors"].append(f"Bad external_id: {ext_id}")
                    continue

                tour = parts[1]
                event_id = parts[2]

                # Try to determine the year from commence_time or metadata
                # DataGolf events use calendar year
                year = None
                async with get_task_session() as session:
                    ct_result = await session.execute(
                        text("""
                            SELECT EXTRACT(YEAR FROM commence_time)::int
                            FROM futures_markets
                            WHERE id = :mid AND commence_time IS NOT NULL
                        """),
                        {"mid": row.id},
                    )
                    ct_row = ct_result.first()
                    if ct_row and ct_row[0]:
                        year = ct_row[0]

                # Fetch full historical results from DataGolf API
                historical = await service.get_historical_results(
                    tour=tour,
                    event_id=event_id,
                    year=year,
                )

                if not historical or len(historical) <= 50:
                    stats["api_miss"] += 1
                    logger.info(
                        "DataGolf leaderboard backfill: no/insufficient historical data for %s (got %d)",
                        ext_id,
                        len(historical) if historical else 0,
                    )
                    await asyncio.sleep(0.5)
                    continue

                stats["events_refetched"] += 1

                # Build the updated leaderboard in the same format as _poll_datagolf_live
                full_leaderboard = []
                for player in historical:
                    entry = {
                        "dg_id": player.get("dg_id"),
                        "name": player.get("name", ""),
                        "position": player.get("position"),
                        "total_score": player.get("total_score"),
                    }
                    full_leaderboard.append(entry)

                # Update ALL market types for this event (win, top_5, top_10, top_20, make_cut)
                event_prefix = f"datagolf:{tour}:{event_id}:"
                async with get_task_session() as session:
                    sibling_result = await session.execute(
                        text("""
                            SELECT id, external_id, market_metadata
                            FROM futures_markets
                            WHERE source = 'datagolf'
                              AND external_id LIKE :prefix
                              AND market_metadata IS NOT NULL
                        """),
                        {"prefix": f"{event_prefix}%"},
                    )
                    siblings = sibling_result.all()

                    for sib in siblings:
                        sib_meta = dict(sib.market_metadata or {})
                        sib_meta["leaderboard"] = full_leaderboard
                        await session.execute(
                            text("""
                                UPDATE futures_markets
                                SET market_metadata = CAST(:meta AS jsonb)
                                WHERE id = :mid
                            """),
                            {"meta": _json.dumps(sib_meta), "mid": sib.id},
                        )
                        stats["markets_updated"] += 1

                    await session.commit()

                logger.info(
                    "DataGolf leaderboard backfill: updated %s with %d players (was 50)",
                    ext_id,
                    len(full_leaderboard),
                )

                await asyncio.sleep(0.5)  # Respect DataGolf rate limits

        finally:
            await service.close()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("DataGolf leaderboard backfill error: %s", e)

    logger.info(
        "DataGolf leaderboard backfill: %d checked, %d events refetched, "
        "%d markets updated, %d already_full, %d api_miss, %d errors",
        stats["markets_checked"],
        stats["events_refetched"],
        stats["markets_updated"],
        stats["already_full"],
        stats["api_miss"],
        len(stats["errors"]),
    )
    return stats


# #994 recover-first source: DNP outcomes whose player IS in the authoritative
# full field are real losses that re-enter the calibration curve (NOT in
# VOID_RESOLUTION_SOURCES). Kept distinct so the recovery is fully reversible and
# retag1 can be taught to leave it alone. is_winner is NEVER touched (gotcha #21).
DATAGOLF_PLAYED_LOST_SOURCE = "datagolf_played_lost"


async def _recover_datagolf_participation(limit: int = 150, deadline: float | None = None):
    """#994 recover-first: reclassify wrongly-VOIDed DataGolf losers.

    Phase 0g's retags mark every loser absent from the STORED (often partial)
    leaderboard as ``did_not_play``, which precompute VOID-excludes — but a
    partial leaderboard deletes players who PLAYED and finished low (certain
    losses), so only losers ever leave the denominator → the datagolf curve
    floats above the diagonal (survivorship; ops round-85 Q1-Q4 confirmed:
    DNP-excluded 55/66/73 vs DNP-restored 28/37/42, yet blanket-restore
    undershoots because some DNPs — e.g. Hatton at Houston — genuinely sat out).

    The authoritative fix: for each resolved DataGolf market with DNP outcomes,
    fetch the FULL field via the historical API and split the DNP cohort:
      * player's dg_id IS in the field  → played-and-lost → resolution_source =
        'datagolf_played_lost' (re-enters the curve as a real loss).
      * player's dg_id NOT in the field → true DNP/WD → stays voided.
      * API returns nothing (event not found) → mark the whole market a recovery
        residual so precompute can symmetrically exclude it (winners AND losers),
        never a one-sided restore.
    Bounded + resumable (Redis cursor by external_id) + quota-polite. Idempotent:
    retag1 is taught to skip 'datagolf_played_lost', so a re-run re-checks only
    the still-DNP tail. NEVER mutates is_winner (gotcha #21).
    """
    import asyncio
    import json as _json
    from app.services.datagolf_api import DataGolfAPIService
    from app.tasks.redis_state import get_redis_client

    stats = {
        "markets_checked": 0,
        "played_lost_recovered": 0,
        "true_dnp_kept": 0,
        "residual_markets": 0,
        "api_miss": 0,
        "errors": [],
    }

    _rc = get_redis_client()
    _cursor_key = "bainluck:datagolf_recovery_cursor"
    _raw = _rc.get(_cursor_key)
    cursor = _raw.decode() if isinstance(_raw, bytes) else (_raw or "")

    try:
        async with get_task_session() as session:
            # Resolved DataGolf markets that still carry did_not_play outcomes and
            # have a parseable datagolf:<tour>:<event>:<type> external_id.
            rows = (await session.execute(
                text("""
                    SELECT fm.id, fm.external_id,
                           EXTRACT(YEAR FROM COALESCE(fm.commence_time,
                                                      fm.resolution_date))::int AS yr
                    FROM futures_markets fm
                    WHERE fm.source = 'datagolf'
                      AND fm.status = 'resolved'
                      AND fm.external_id LIKE 'datagolf:%:%:%'
                      AND fm.external_id > :cursor
                      AND EXISTS (
                          SELECT 1 FROM futures_outcomes fo
                          WHERE fo.market_id = fm.id
                            AND fo.resolution_source = 'did_not_play'
                            AND fo.is_winner = false
                      )
                    ORDER BY fm.external_id
                    LIMIT :limit
                """),
                {"cursor": cursor, "limit": limit},
            )).all()

        if not rows:
            # Wrapped the whole cohort — restart from the head next run.
            if cursor:
                _rc.delete(_cursor_key)
                logger.info("DataGolf recovery: cursor wrapped, restarts next run")
            return stats

        service = DataGolfAPIService()
        _last_processed = cursor  # advance the cursor even past error markets
        _rate_limited = False
        try:
            for row in rows:
                if deadline is not None:
                    import time as _t
                    if _t.monotonic() >= deadline:
                        logger.info("DataGolf recovery: deadline hit after %d markets",
                                    stats["markets_checked"])
                        break
                stats["markets_checked"] += 1
                ext_id = row.external_id  # datagolf:pga:123:win
                # Advance the cursor for every outcome EXCEPT a 429 (transient) —
                # success, residual, no-match, and deterministic 400s are all
                # "handled". 429 sets this False and stops the run to resume here.
                _advance = True
                # #994: isolate each market — a single bad row (e.g. tour='alt'
                # → DataGolf 400, which get_historical_results re-raises per
                # gotcha #36) must NOT abort the batch or wedge the cursor on the
                # first bad market forever. Skip + advance.
                try:
                    parts = ext_id.split(":")
                    if len(parts) < 4:
                        continue
                    tour, event_id = parts[1], parts[2]

                    # #994: pace BEFORE every request. DataGolf caps at 45 req/min;
                    # the pacing MUST wrap error paths too — invalid-tour (400) and
                    # other raised calls skip an after-the-call sleep, so 24 rapid
                    # 400s blew the cap and tripped a 429 mid-run. Sleeping before
                    # the call paces every request regardless of outcome (1.5s =
                    # 40/min, under the cap).
                    await asyncio.sleep(1.5)
                    historical = await service.get_historical_results(
                        tour=tour, event_id=event_id, year=row.yr,
                    )

                    if not historical:
                        # Event genuinely not found → residual; symmetric-exclude.
                        stats["api_miss"] += 1
                        async with get_task_session() as session:
                            _meta = await session.execute(
                                text("SELECT market_metadata FROM futures_markets WHERE id = :mid"),
                                {"mid": row.id},
                            )
                            _m = dict(_meta.scalar() or {})
                            if not _m.get("datagolf_recovery_residual"):
                                _m["datagolf_recovery_residual"] = True
                                await session.execute(
                                    text("UPDATE futures_markets SET market_metadata = CAST(:meta AS jsonb) WHERE id = :mid"),
                                    {"meta": _json.dumps(_m), "mid": row.id},
                                )
                                await session.commit()
                                stats["residual_markets"] += 1
                        continue

                    played_dg_ids = [
                        str(p["dg_id"]) for p in historical if p.get("dg_id") is not None
                    ]
                    if not played_dg_ids:
                        continue

                    async with get_task_session() as session:
                        # Played-and-lost: dg_id (external_id[4:]) in the field.
                        r_played = await session.execute(
                            text("""
                                UPDATE futures_outcomes fo
                                SET resolution_source = :src
                                FROM futures_markets fm
                                WHERE fo.market_id = fm.id AND fm.id = :mid
                                  AND fo.resolution_source = 'did_not_play'
                                  AND fo.is_winner = false
                                  AND SUBSTRING(fo.external_id FROM 4) = ANY(:ids)
                            """),
                            {"src": DATAGOLF_PLAYED_LOST_SOURCE, "mid": row.id, "ids": played_dg_ids},
                        )
                        await session.commit()
                        stats["played_lost_recovered"] += r_played.rowcount
                    _advance = True  # processed cleanly → move cursor past it
                except Exception as _me:
                    _resp = getattr(_me, "response", None)
                    _status = getattr(_resp, "status_code", None)
                    if _status == 429:
                        # Rate limited — STOP the run and do NOT advance past this
                        # market, so the next run resumes here (transient; the
                        # 1.5s pacing should keep us under the cap normally).
                        stats["errors"].append(f"{ext_id}: rate_limited_429_stopping")
                        logger.warning(
                            "DataGolf recovery: 429 at %s — stopping run, will "
                            "resume here next run", ext_id,
                        )
                        _rate_limited = True
                        _advance = False  # resume at THIS market next run
                        break
                    # Deterministic error (e.g. 400 'invalid tour' for tour=alt):
                    # the market can never be verified via this endpoint → mark it
                    # a residual so precompute symmetrically excludes it, and
                    # advance the cursor.
                    _detail = type(_me).__name__
                    if _resp is not None:
                        try:
                            _detail += f" {_status}: {_resp.text[:150]}"
                        except Exception:
                            pass
                    else:
                        _detail += f": {str(_me)[:150]}"
                    stats["errors"].append(f"{ext_id}: {_detail}")
                    logger.warning("DataGolf recovery: skipping %s (%s)", ext_id, _me)
                    try:
                        async with get_task_session() as session:
                            _meta = await session.execute(
                                text("SELECT market_metadata FROM futures_markets WHERE id = :mid"),
                                {"mid": row.id},
                            )
                            _m = dict(_meta.scalar() or {})
                            if not _m.get("datagolf_recovery_residual"):
                                _m["datagolf_recovery_residual"] = True
                                await session.execute(
                                    text("UPDATE futures_markets SET market_metadata = CAST(:meta AS jsonb) WHERE id = :mid"),
                                    {"meta": _json.dumps(_m), "mid": row.id},
                                )
                                await session.commit()
                                stats["residual_markets"] += 1
                    except Exception:
                        pass
                    _advance = True
                finally:
                    # Advance the resume point only when we handled this market
                    # (success or deterministic skip) — NOT on a 429 stop.
                    if _advance:
                        _last_processed = ext_id
        finally:
            await service.close()
            # Persist resume point (last market attempted, success or skip).
            if _last_processed:
                _rc.setex(_cursor_key, 86400 * 14, _last_processed)

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("DataGolf recovery error: %s", e)

    logger.info(
        "DataGolf recovery: %d markets, %d played_lost recovered, %d residual, %d api_miss",
        stats["markets_checked"], stats["played_lost_recovered"],
        stats["residual_markets"], stats["api_miss"],
    )
    return stats


async def _backfill_datagolf_winners():
    """Resolve DataGolf placement markets from actual leaderboard results.

    DataGolf markets (make_cut, top_5, top_10, top_20, win) store model
    predictions in current_probability, NOT settlement prices. The generic
    Pass 3 (independent thresholds) incorrectly treats these as settlements.

    This function uses the leaderboard stored in market_metadata to
    determine actual placement results and set is_winner correctly.
    """
    stats = {
        "markets_processed": 0,
        "winners_set": 0,
        "losers_set": 0,
        "no_leaderboard": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            result = await session.execute(text("""
                    SELECT fm.id, fm.external_id, fm.market_metadata
                    FROM futures_markets fm
                    WHERE fm.source = 'datagolf'
                      AND fm.status = 'resolved'
                      AND fm.market_metadata IS NOT NULL
                """))
            markets = result.all()

            for row in markets:
                stats["markets_processed"] += 1
                metadata = row.market_metadata or {}
                leaderboard = metadata.get("leaderboard")
                if not leaderboard:
                    stats["no_leaderboard"] += 1
                    continue

                # Determine market type from external_id: "datagolf:pga:123:win"
                market_type = row.external_id.rsplit(":", 1)[-1]

                # Build dg_id → position lookup from leaderboard
                pos_by_dg = {}
                for entry in leaderboard:
                    dg_id = entry.get("dg_id")
                    pos_raw = entry.get("position")
                    if dg_id is not None and pos_raw is not None:
                        pos_by_dg[str(dg_id)] = str(pos_raw)

                # Get all outcomes for this market
                outcomes = await session.execute(
                    text("""
                        SELECT id, external_id FROM futures_outcomes
                        WHERE market_id = :mid
                    """),
                    {"mid": row.id},
                )

                # Anyone NOT in a COMPLETE leaderboard was never in the field
                # and is definitively a loser for win/top_N markets.
                #
                # For make_cut: only infer absent = missed-cut when the
                # leaderboard is large enough to contain the full field
                # (typically 120-160 players). Truncated leaderboards
                # (e.g., 50 entries from the old polling code) omit
                # players ranked 51+ who actually MADE the cut, so
                # can_infer_absent would mark them as losers incorrectly.
                # The 100-player threshold safely distinguishes full
                # fields from truncated snapshots.
                leaderboard_size = len(leaderboard)
                if market_type == "make_cut":
                    can_infer_absent = leaderboard_size >= 100
                else:
                    can_infer_absent = market_type in (
                        "win",
                        "top_5",
                        "top_10",
                        "top_20",
                    )

                for out_row in outcomes.all():
                    ext = out_row.external_id or ""
                    if not ext.startswith("dg_"):
                        continue
                    dg_id = ext[3:]

                    pos_str = pos_by_dg.get(dg_id)
                    res_source = "leaderboard"
                    if pos_str is None:
                        if can_infer_absent:
                            won = False
                            res_source = "did_not_play"
                        else:
                            continue
                    else:
                        upper = pos_str.strip().upper()
                        if upper in ("WD", "DNS", "W/D"):
                            res_source = "withdrew"
                        won = _datagolf_check_placement(pos_str, market_type)
                    if won is None:
                        continue

                    await session.execute(
                        text("""
                            UPDATE futures_outcomes SET is_winner = :won, resolution_source = :src, last_updated = NOW()
                            WHERE id = :oid
                        """),
                        {"won": won, "src": res_source, "oid": out_row.id},
                    )
                    if won:
                        stats["winners_set"] += 1
                    else:
                        stats["losers_set"] += 1

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("DataGolf winner backfill error: %s", e)

    logger.info(
        "DataGolf winner backfill: %d markets, %d winners, %d losers, "
        "%d no_leaderboard, %d errors",
        stats["markets_processed"],
        stats["winners_set"],
        stats["losers_set"],
        stats["no_leaderboard"],
        len(stats["errors"]),
    )
    return stats


def _datagolf_check_placement(pos_str: str, market_type: str) -> bool | None:
    """Determine if a player achieved the placement based on leaderboard position."""
    pos_str = pos_str.strip()

    # Non-numeric positions: CUT, MC, WD, DQ, DNS
    cut_statuses = {"CUT", "MC", "MDF", "WD", "DQ", "DNS", "W/D"}
    if pos_str.upper() in cut_statuses:
        if market_type == "make_cut":
            return False
        # For win/top_N, a cut player definitely didn't place
        return False

    # Parse numeric position — handle ties like "T5", "T12"
    numeric_str = pos_str.upper().lstrip("T")
    try:
        pos = int(numeric_str)
    except ValueError:
        return None  # Can't parse position

    thresholds = {"win": 1, "top_5": 5, "top_10": 10, "top_20": 20}
    threshold = thresholds.get(market_type)
    if threshold is not None:
        return pos <= threshold

    if market_type == "make_cut":
        return True  # Has a numeric position = made the cut

    return None


async def _backfill_from_current_probability():
    """Set is_winner from current_probability for ALL sources.

    Three passes:
    1. Clean resolution: all outcomes at >=0.95 or <=0.05 (existing logic)
    2. Mutually-exclusive markets: probability sum near 1.0, max-prob outcome wins
    3. Independent thresholds: probability sum >> 1.0, each outcome > 0.50 wins
    """
    stats = {
        "clean_winners": 0,
        "clean_losers": 0,
        "mutex_winners": 0,
        "mutex_losers": 0,
        "threshold_winners": 0,
        "threshold_losers": 0,
        "all_losers_set": 0,
        "single_winners": 0,
        "single_losers": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            # Pass 1: Clean resolution (all at 0 or 1)
            result = await session.execute(text("""
                    WITH cleanly_resolved AS (
                        SELECT fm.id AS market_id
                        FROM futures_markets fm
                        JOIN futures_outcomes fo ON fo.market_id = fm.id
                        WHERE fm.status = 'resolved'
                        GROUP BY fm.id
                        HAVING SUM(CASE WHEN fo.is_winner
                                   AND fo.resolution_source NOT IN
                                       """ + OVERWRITABLE_WINNER_SOURCES_SQL + """
                                   THEN 1 ELSE 0 END) = 0
                           AND COUNT(*) FILTER (
                               WHERE fo.current_probability >= 0.95
                                  OR fo.current_probability <= 0.05
                           ) = COUNT(*)
                           AND COUNT(*) >= 1
                    )
                    UPDATE futures_outcomes fo
                    SET is_winner = (fo.current_probability >= 0.95),
                        resolution_source = 'clean_resolution',
                        last_updated = NOW()
                    FROM cleanly_resolved cr
                    WHERE fo.market_id = cr.market_id
                      AND fo.current_probability IS NOT NULL
                    RETURNING fo.is_winner
                """))
            rows = result.all()
            stats["clean_winners"] = sum(1 for r in rows if r[0])
            stats["clean_losers"] = sum(1 for r in rows if not r[0])
            await session.commit()

            # Passes 2-3 DISABLED — guessing from midrange current_probability
            # has a ~19% error rate (3,865 Kalshi + 2,205 Polymarket wrong
            # winners as of June 4). Wrong guesses actively corrupt calibration.
            # Markets without authoritative settlement data stay unresolved
            # (is_winner=NULL) and are excluded from calibration, which is
            # better than including wrong data. See #754.

            # Pass 4: All-losers markets — every outcome at <= 0.10
            # The winning outcome isn't in our DB; mark existing as losers
            result4 = await session.execute(text("""
                    WITH all_loser_markets AS (
                        SELECT fm.id AS market_id
                        FROM futures_markets fm
                        JOIN futures_outcomes fo ON fo.market_id = fm.id
                        WHERE fm.status = 'resolved'
                          AND fo.current_probability IS NOT NULL
                        GROUP BY fm.id
                        HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                           AND MAX(fo.current_probability) <= 0.10
                           AND COUNT(*) >= 1
                        LIMIT 50000
                    )
                    UPDATE futures_outcomes fo
                    SET is_winner = false,
                        resolution_source = 'all_losers',
                        last_updated = NOW()
                    FROM all_loser_markets al
                    WHERE fo.market_id = al.market_id
                    RETURNING 1
                """))
            stats["all_losers_set"] = result4.rowcount
            await session.commit()

            # Passes 5-7 DISABLED — same reason as Passes 2-3. See #754.

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Current-probability winner backfill error: %s", e)

    total_w = stats["clean_winners"]
    total_l = stats["clean_losers"] + stats["all_losers_set"]
    logger.info(
        "Current-probability winner backfill: %d winners (clean=%d), "
        "%d losers (clean=%d, all_losers=%d), %d errors",
        total_w,
        stats["clean_winners"],
        total_l,
        stats["clean_losers"],
        stats["all_losers_set"],
        len(stats["errors"]),
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
            result = await session.execute(text("""
                    UPDATE futures_markets
                    SET group_id = 'polymarket:' || COALESCE(
                        market_metadata->>'polymarket_event_id',
                        external_id
                    )
                    WHERE source = 'polymarket'
                      AND group_id IS NULL
                """))
            stats["updated"] = result.rowcount
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Polymarket group_id backfill error: %s", e)

    logger.info(
        "Polymarket group_id backfill: %d markets updated, %d errors",
        stats["updated"],
        len(stats["errors"]),
    )
    return stats


async def _backfill_kalshi_group_ids():
    """Set group_id on Kalshi markets from external_id (= event_ticker)."""
    stats = {"updated": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(text("""
                    UPDATE futures_markets
                    SET group_id = 'kalshi:' || external_id
                    WHERE source = 'kalshi'
                      AND group_id IS NULL
                """))
            stats["updated"] = result.rowcount
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Kalshi group_id backfill error: %s", e)

    logger.info(
        "Kalshi group_id backfill: %d markets updated, %d errors",
        stats["updated"],
        len(stats["errors"]),
    )
    return stats


async def _null_untradeable_openings():
    """Null out opening_probability AND calibration_probability on outcomes
    with insufficient trading activity.

    Three passes:
    - Pass 1: outcomes with ZERO snapshots (never tracked)
    - Pass 2: outcomes with ≤ 2 snapshots where calibration_probability
      still equals opening_probability (briefly polled but no real price
      discovery)
    - Pass 3: outcomes with ≤ 5 snapshots where price never moved more
      than 2pp from opening (polled but no meaningful price discovery —
      catches Kalshi economics/weather with thin trading)

    Setting opening_probability to NULL excludes from calibration via the
    existing IS NOT NULL filter. Also nulls calibration_probability to
    prevent stale values from a prior backfill run.
    """
    stats = {
        "nulled_zero_snap": 0,
        "nulled_low_snap": 0,
        "nulled_no_movement": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            result = await session.execute(text("""
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
                          LIMIT 100000
                      )
                """))
            stats["nulled_zero_snap"] = result.rowcount

            result2 = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET opening_probability = NULL
                    WHERE fo.opening_probability IS NOT NULL
                      AND fo.calibration_probability IS NOT NULL
                      AND fo.calibration_probability = fo.opening_probability
                      AND (
                          SELECT COUNT(*) FROM futures_odds_snapshots fos
                          WHERE fos.outcome_id = fo.id
                      ) <= 2
                      AND fo.id IN (
                          SELECT fo2.id
                          FROM futures_outcomes fo2
                          JOIN futures_markets fm ON fm.id = fo2.market_id
                          WHERE fm.status = 'resolved'
                            AND fo2.opening_probability IS NOT NULL
                            AND fo2.calibration_probability IS NOT NULL
                            AND fo2.calibration_probability = fo2.opening_probability
                          LIMIT 50000
                      )
                """))
            stats["nulled_low_snap"] = result2.rowcount

            # Pass 3: outcomes with ≤5 snapshots where max-min spread < 2pp
            result3 = await session.execute(text("""
                    WITH candidates AS (
                        SELECT fo.id
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fm.id = fo.market_id
                        WHERE fm.status = 'resolved'
                          AND fo.opening_probability IS NOT NULL
                          AND fo.calibration_probability IS NOT NULL
                          AND fo.calibration_probability = fo.opening_probability
                        LIMIT 50000
                    ),
                    snap_stats AS (
                        SELECT c.id AS outcome_id,
                               COUNT(*) AS snap_count,
                               MAX(fos.probability) - MIN(fos.probability) AS price_spread
                        FROM candidates c
                        JOIN futures_odds_snapshots fos ON fos.outcome_id = c.id
                        GROUP BY c.id
                        HAVING COUNT(*) <= 5
                           AND MAX(fos.probability) - MIN(fos.probability) < 0.02
                    )
                    UPDATE futures_outcomes fo
                    SET opening_probability = NULL
                    FROM snap_stats ss
                    WHERE fo.id = ss.outcome_id
                """))
            stats["nulled_no_movement"] = result3.rowcount

            # Pass 4a: outcomes in tournament WINNER markets (50+) with high opening
            result4a = await session.execute(text("""
                    WITH big_winner_markets AS (
                        SELECT fm.id AS market_id
                        FROM futures_markets fm
                        JOIN futures_outcomes fo ON fo.market_id = fm.id
                        WHERE fm.status = 'resolved'
                          AND LOWER(fm.name) NOT LIKE '%cut%'
                          AND LOWER(fm.name) NOT LIKE '%top 5%'
                          AND LOWER(fm.name) NOT LIKE '%top 10%'
                          AND LOWER(fm.name) NOT LIKE '%top 20%'
                        GROUP BY fm.id
                        HAVING COUNT(*) >= 50
                    )
                    UPDATE futures_outcomes fo
                    SET opening_probability = NULL
                    FROM big_winner_markets bm
                    WHERE fo.market_id = bm.market_id
                      AND fo.opening_probability > 0.50
                """))

            # Pass 4b: outcomes with very few snapshots AND high opening.
            # These are ask-price corruptions: yes_ask=0.99 stored as opening
            # on illiquid markets. Real predictions have multiple snapshots
            # from repeated polling. "LeBron: 8+ points" at 95% with 20
            # snapshots is legitimate; "Dort: 6+ assists" at 99% with 1
            # snapshot is the ask price.
            result4b = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET opening_probability = NULL
                    WHERE fo.id IN (
                        SELECT fo2.id
                        FROM futures_outcomes fo2
                        JOIN futures_markets fm ON fm.id = fo2.market_id
                        WHERE fm.status = 'resolved'
                          AND fo2.opening_probability >= 0.90
                          AND (SELECT COUNT(*) FROM futures_odds_snapshots fos
                               WHERE fos.outcome_id = fo2.id) <= 2
                        LIMIT 100000
                    )
                """))
            stats["nulled_ask_price"] = (result4a.rowcount or 0) + (
                result4b.rowcount or 0
            )

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Null untradeable openings error: %s", e)

    logger.info(
        "Null untradeable openings: %d zero-snap, %d low-snap, %d no-movement, "
        "%d ask-price, %d errors",
        stats["nulled_zero_snap"],
        stats["nulled_low_snap"],
        stats["nulled_no_movement"],
        stats.get("nulled_ask_price", 0),
        len(stats["errors"]),
    )
    return stats


async def _backfill_polymarket_group_ids_from_api():
    """Fetch resolved Polymarket events from Gamma API to fix group_id.

    For events with 2+ markets, sets the same group_id on all matching
    FuturesMarket rows. This catches multi-outcome events where each
    candidate is a separate Polymarket event that our DB-only backfill
    can't group.

    Short-circuits if no null group_ids remain (fast DB check).
    """
    import asyncio
    from app.services.polymarket_api import PolymarketAPIService

    stats = {
        "events_fetched": 0,
        "events_with_markets": 0,
        "markets_updated": 0,
        "zero_update_pages": 0,
        "errors": [],
    }

    # Fast short-circuit: skip API pagination if no null group_ids
    async with get_task_session() as session:
        null_count = await session.execute(text("""
                SELECT COUNT(*) FROM futures_markets
                WHERE source = 'polymarket' AND status = 'resolved' AND group_id IS NULL
            """))
        if null_count.scalar() == 0:
            logger.info("Polymarket API group_id backfill: skipped (0 null group_ids)")
            stats["markets_updated"] = -1
            return stats

    service = PolymarketAPIService()
    try:
        offset = 0
        max_events = 200000

        while stats["events_fetched"] < max_events:
            try:
                events_data = await service.get_events(
                    active=False,
                    closed=True,
                    limit=100,
                    offset=offset,
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
        stats["events_fetched"],
        stats["events_with_markets"],
        stats["markets_updated"],
        len(stats["errors"]),
    )
    return stats


async def _backfill_polymarket_winners_from_api(limit: int = 500):
    """Phase 3: Fetch settlement prices from Polymarket Gamma API.

    For stuck Polymarket markets where current_probability didn't reach
    settlement extremes (0/1) OR where all outcomes are near-zero (the
    winning outcome's settlement price was never synced), fetches the
    event from the Gamma API and uses outcomePrices for resolution.

    Handles three market shapes:
    - NegRisk parent markets (external_id = event_id): iterate all API
      sub-markets, match each by condition_id against DB outcomes
    - Decomposed sub-markets (external_id = condition_id): direct lookup
    - Sub-market game props (outcome external_id = condition_id + _yes/_no)

    Uses GET /events/{event_id} (which returns settlement prices) and
    matches conditions by condition_id. The /markets/{id} endpoint does
    NOT accept condition_ids as path params.
    """
    import asyncio
    import json as _json
    from app.services.polymarket_api import PolymarketAPIService

    stats = {
        "markets_checked": 0,
        "winners_set": 0,
        "losers_set": 0,
        "prices_synced": 0,
        "api_miss": 0,
        "not_settled": 0,
        "no_match": 0,
        "errors": [],
    }

    # Resume from where last run left off
    from app.tasks.redis_state import get_redis_client

    _rc = get_redis_client()
    _offset_key = "bainluck:pm_winner_backfill_offset"
    _last_max_id = int(_rc.get(_offset_key) or 0)

    async with get_task_session() as session:
        stuck = await session.execute(
            text("""
                SELECT fm.id, fm.external_id, fm.group_type,
                       fm.market_metadata->>'polymarket_event_id' AS poly_event_id
                FROM futures_markets fm
                JOIN futures_outcomes fo ON fo.market_id = fm.id
                WHERE fm.source = 'polymarket'
                  AND fm.status = 'resolved'
                  AND fm.id > :last_id
                GROUP BY fm.id
                HAVING BOOL_OR(
                    COALESCE(fo.resolution_source, '') NOT IN ('api_settlement', 'clean_resolution')
                )
                ORDER BY fm.id ASC
                LIMIT :limit
            """),
            {"limit": limit, "last_id": _last_max_id},
        )
        markets = stuck.all()

    if not markets:
        # Wrapped around — reset cursor for next run
        _rc.delete(_offset_key)
        logger.info("Polymarket API winner backfill: nothing to do (reset cursor)")
        return stats

    # Save cursor for next run
    max_id = max(row.id for row in markets)
    _rc.setex(_offset_key, 86400 * 7, str(max_id))

    # Separate markets by lookup strategy:
    # - With poly_event_id: group by event for batch event lookup
    # - Without: look up each market individually by condition_id
    by_event: dict[str, list] = {}
    by_condition: list = []
    for row in markets:
        if row.poly_event_id:
            by_event.setdefault(row.poly_event_id, []).append(row)
        else:
            by_condition.append(row)

    logger.info(
        "Polymarket API winner backfill: %d by event (%d events), %d by condition",
        sum(len(v) for v in by_event.values()),
        len(by_event),
        len(by_condition),
    )

    import time as _time

    _t0 = _time.monotonic()
    _MAX_RUNTIME = 420  # 7 min (resolve_winners has 9 min soft limit)

    # Dead-CID cache: skip condition_ids that returned a definitive 404 before.
    _dead_key = "bainluck:poly_dead_cids"
    # #985: one-time purge of the polluted dead set. The old _fetch_market cached
    # 429 rate-limits (and any error) as "dead" (gotcha #36), so real markets —
    # incl. flagship ones (2024 US Presidential, $286M US×Iran ceasefire) — were
    # wrongly marked dead and skipped forever. Purge once after this fix so they
    # get re-fetched; genuine 404s are re-added correctly by the 404-only
    # classification below.
    _purge_flag = "bainluck:poly_dead_purged_v2"
    if not _rc.get(_purge_flag):
        _purged = _rc.delete(_dead_key)
        _rc.setex(_purge_flag, 86400 * 30, "1")
        logger.info(
            "Polymarket dead-cid set PURGED once (#985 429-pollution fix; key existed=%s)",
            _purged,
        )
    dead_cids = _rc.smembers(_dead_key)
    dead_cids = {c.decode() if isinstance(c, bytes) else c for c in dead_cids}

    service = PolymarketAPIService()
    try:
        # --- Phase A: Condition-ID lookups (concurrent) ---
        # #985: low concurrency — re-fetching the (now un-skipped) backlog at
        # semaphore-10 saturated Gamma's rate limit (a verify run hit 6000/6000
        # 429). Throttle to a gentle, sustainable rate so fetches succeed.
        sem = asyncio.Semaphore(3)

        async def _fetch_market(cid):
            # #985: returns (cid, data_or_None, definitive). definitive=True means
            # the API gave an authoritative answer — a market dict, or a true 404
            # (None). definitive=False means transient (429/error/timeout): the
            # caller must NOT cache it dead (gotcha #36); retry it next run.
            async with sem:
                for _attempt in range(3):
                    try:
                        return cid, await service.get_market_by_condition(str(cid)), True
                    except Exception as e:
                        if "429" in str(e) or "rate" in str(e).lower():
                            await asyncio.sleep(min(5 * (_attempt + 1), 20))  # #985: harder backoff
                            continue
                        return cid, None, False  # non-429 transient — not definitive
                return cid, None, False  # 429-exhausted — not definitive, retry next run

        alive_conditions = [r for r in by_condition if r.external_id not in dead_cids]
        stats["skipped_dead"] = len(by_condition) - len(alive_conditions)

        for batch_start in range(0, len(alive_conditions), 200):
            if _time.monotonic() - _t0 > _MAX_RUNTIME:
                break
            batch = alive_conditions[batch_start : batch_start + 200]
            results = await asyncio.gather(
                *[_fetch_market(r.external_id) for r in batch]
            )
            # #985 circuit-breaker: if Gamma is throttling us (most of the batch
            # 429'd), STOP the run — these are not dead, they retry next run.
            # Prevents the 6000/6000 rate_limited burn that makes zero progress
            # and only deepens the throttle. The drain resumes (cursor) next run.
            _batch_rl = sum(1 for _c, _md, _df in results if _md is None and not _df)
            if results and _batch_rl >= 0.8 * len(results):
                stats["rate_limited"] = stats.get("rate_limited", 0) + _batch_rl
                stats["throttled_stop"] = True
                logger.warning(
                    "Polymarket resolver: Gamma throttling (%d/%d 429 in batch) — "
                    "stopping run early; resumes next run", _batch_rl, len(results),
                )
                break

            async with get_task_session() as session:
                for cid, market_data, definitive in results:
                    stats["markets_checked"] += 1
                    if market_data is None:
                        if definitive:
                            # genuine 404 — safe to cache dead
                            stats["api_miss"] += 1
                            _rc.sadd(_dead_key, cid)
                        else:
                            # transient (429/error) — DO NOT mark dead; retry next run
                            stats["rate_limited"] = stats.get("rate_limited", 0) + 1
                        continue

                    prices_raw = (
                        market_data.get("outcomePrices")
                        or market_data.get("outcome_prices")
                        or []
                    )
                    if isinstance(prices_raw, str):
                        try:
                            prices_raw = _json.loads(prices_raw)
                        except (ValueError, TypeError):
                            prices_raw = []
                    try:
                        prices = [float(p) for p in prices_raw]
                    except (ValueError, TypeError):
                        prices = []

                    if not prices or len(prices) < 2:
                        stats["not_settled"] += 1
                        continue

                    if max(prices) < 0.90 or min(prices) > 0.10:
                        stats["not_settled"] += 1
                        continue

                    yes_won = prices[0] >= 0.90
                    stats["prices_synced"] += 1

                    r_w = await session.execute(
                        text("""
                            UPDATE futures_outcomes
                            SET current_probability = :price,
                                is_winner = :won,
                                resolution_source = 'api_settlement',
                                last_updated = NOW()
                            WHERE external_id = :cid
                              AND COALESCE(resolution_source, '') NOT IN """ + AUTHORITATIVE_SOURCES_SQL + """
                        """),
                        {"price": prices[0], "won": yes_won, "cid": cid},
                    )
                    if r_w.rowcount > 0:
                        stats[
                            "winners_set" if yes_won else "losers_set"
                        ] += r_w.rowcount

                    # Also resolve the _no counterpart
                    no_cid = f"{cid}_no"
                    r_n = await session.execute(
                        text("""
                            UPDATE futures_outcomes
                            SET current_probability = :price,
                                is_winner = :won,
                                resolution_source = 'api_settlement',
                                last_updated = NOW()
                            WHERE external_id = :cid
                              AND COALESCE(resolution_source, '') NOT IN """ + AUTHORITATIVE_SOURCES_SQL + """
                        """),
                        {
                            "price": (
                                prices[1] if len(prices) > 1 else (1.0 - prices[0])
                            ),
                            "won": not yes_won,
                            "cid": no_cid,
                        },
                    )
                    if r_n.rowcount > 0:
                        stats[
                            "losers_set" if yes_won else "winners_set"
                        ] += r_n.rowcount

                await session.commit()

        # Set TTL on dead CIDs cache
        _rc.expire(_dead_key, 86400 * 7)

        # --- Phase B: Event-ID lookups (original logic) ---
        event_ids = list(by_event.keys())
        batch_size = 200
        for batch_start in range(0, len(event_ids), batch_size):
            if _time.monotonic() - _t0 > _MAX_RUNTIME:
                logger.info(
                    "Polymarket API backfill: time limit, stopping after %d/%d events",
                    batch_start,
                    len(event_ids),
                )
                break
            batch = event_ids[batch_start : batch_start + batch_size]

            async with get_task_session() as session:
                for event_id in batch:
                    try:
                        event_data = await service.get_event_by_id(str(event_id))
                    except Exception as e:
                        if "429" in str(e) or "rate" in str(e).lower():
                            await asyncio.sleep(2)
                        event_data = None
                    if not event_data:
                        for row in by_event[event_id]:
                            stats["markets_checked"] += 1
                            stats["api_miss"] += 1
                        continue

                    api_markets = event_data.get("markets") or []
                    # Index by condition_id for fast lookup
                    by_cond = {}
                    for m in api_markets:
                        cid = m.get("conditionId") or m.get("condition_id") or ""
                        if cid:
                            by_cond[str(cid)] = m

                    for row in by_event[event_id]:
                        stats["markets_checked"] += 1
                        condition_id = row.external_id
                        is_negrisk = row.group_type == "negrisk"

                        # NegRisk parent markets: external_id = event_id.
                        # Must iterate ALL API sub-markets and match each
                        # condition_id against DB outcomes on this market.
                        if is_negrisk or (
                            condition_id == event_id and len(api_markets) > 1
                        ):
                            market_resolved = False
                            for m in api_markets:
                                m_cid = str(
                                    m.get("conditionId") or m.get("condition_id") or ""
                                )
                                if not m_cid:
                                    continue

                                m_prices_raw = (
                                    m.get("outcomePrices")
                                    or m.get("outcome_prices")
                                    or []
                                )
                                if isinstance(m_prices_raw, str):
                                    try:
                                        m_prices_raw = _json.loads(m_prices_raw)
                                    except (ValueError, TypeError):
                                        m_prices_raw = []
                                try:
                                    m_prices = [float(p) for p in m_prices_raw]
                                except (ValueError, TypeError):
                                    m_prices = []

                                if not m_prices:
                                    continue

                                settlement_price = m_prices[0]
                                is_winner = settlement_price >= 0.90

                                # Sync settlement price to current_probability
                                price_r = await session.execute(
                                    text("""
                                        UPDATE futures_outcomes
                                        SET current_probability = :price
                                        WHERE market_id = :mid
                                          AND external_id = :cid
                                          AND (current_probability IS NULL
                                               OR ABS(current_probability - :price) > 0.001)
                                    """),
                                    {
                                        "price": settlement_price,
                                        "mid": row.id,
                                        "cid": m_cid,
                                    },
                                )
                                stats["prices_synced"] += price_r.rowcount

                                # Set is_winner
                                r = await session.execute(
                                    update(FuturesOutcome)
                                    .where(
                                        FuturesOutcome.market_id == row.id,
                                        FuturesOutcome.external_id == m_cid,
                                    )
                                    .values(
                                        is_winner=is_winner,
                                        resolution_source="api_settlement",
                                        last_updated=func.now(),
                                    )
                                )
                                if r.rowcount > 0:
                                    market_resolved = True
                                    if is_winner:
                                        stats["winners_set"] += r.rowcount
                                    else:
                                        stats["losers_set"] += r.rowcount

                            if not market_resolved:
                                stats["no_match"] += 1
                            continue

                        # For decomposed sub-markets: external_id = condition_id
                        market_data = by_cond.get(condition_id)

                        # For parent markets: external_id = event_id, try first condition
                        if (
                            not market_data
                            and condition_id == event_id
                            and len(api_markets) == 1
                        ):
                            market_data = api_markets[0]

                        if not market_data:
                            stats["no_match"] += 1
                            continue

                        prices_raw = (
                            market_data.get("outcomePrices")
                            or market_data.get("outcome_prices")
                            or []
                        )
                        if isinstance(prices_raw, str):
                            try:
                                prices_raw = _json.loads(prices_raw)
                            except (ValueError, TypeError):
                                prices_raw = []

                        try:
                            prices = [float(p) for p in prices_raw]
                        except (ValueError, TypeError):
                            prices = []

                        if len(prices) < 2:
                            stats["not_settled"] += 1
                            continue

                        if max(prices) < 0.90 or min(prices) > 0.10:
                            stats["not_settled"] += 1
                            continue

                        # Determine winner from settlement prices
                        yes_won = prices[0] >= 0.90
                        cid = (
                            market_data.get("conditionId")
                            or market_data.get("condition_id")
                            or condition_id
                        )

                        # Sync settlement price to current_probability
                        await session.execute(
                            text("""
                                UPDATE futures_outcomes
                                SET current_probability = :price
                                WHERE market_id = :mid
                                  AND external_id = :cid
                                  AND (current_probability IS NULL
                                       OR ABS(current_probability - :price) > 0.001)
                            """),
                            {"price": prices[0], "mid": row.id, "cid": cid},
                        )

                        # Try bare condition_id first (NegRisk + single-market),
                        # then _yes/_no suffix (sub-market game props)
                        r_bare = await session.execute(
                            update(FuturesOutcome)
                            .where(
                                FuturesOutcome.market_id == row.id,
                                FuturesOutcome.external_id == cid,
                            )
                            .values(
                                is_winner=yes_won,
                                resolution_source="api_settlement",
                                last_updated=func.now(),
                            )
                        )

                        if r_bare.rowcount > 0:
                            if yes_won:
                                stats["winners_set"] += r_bare.rowcount
                            else:
                                stats["losers_set"] += r_bare.rowcount
                        else:
                            # Sub-market game props: outcomes have _yes/_no suffix
                            r1 = await session.execute(
                                update(FuturesOutcome)
                                .where(
                                    FuturesOutcome.market_id == row.id,
                                    FuturesOutcome.external_id == f"{cid}_yes",
                                )
                                .values(
                                    is_winner=yes_won,
                                    resolution_source="api_settlement",
                                    last_updated=func.now(),
                                )
                            )
                            r2 = await session.execute(
                                update(FuturesOutcome)
                                .where(
                                    FuturesOutcome.market_id == row.id,
                                    FuturesOutcome.external_id == f"{cid}_no",
                                )
                                .values(
                                    is_winner=(not yes_won),
                                    resolution_source="api_settlement",
                                    last_updated=func.now(),
                                )
                            )
                            if r1.rowcount + r2.rowcount > 0:
                                if yes_won:
                                    stats["winners_set"] += r1.rowcount
                                    stats["losers_set"] += r2.rowcount
                                else:
                                    stats["losers_set"] += r1.rowcount
                                    stats["winners_set"] += r2.rowcount

                await session.commit()

            logger.info(
                "Polymarket API backfill: %d/%d events, %d winners, %d losers, "
                "%d prices_synced, %d miss",
                min(batch_start + batch_size, len(event_ids)),
                len(event_ids),
                stats["winners_set"],
                stats["losers_set"],
                stats["prices_synced"],
                stats["api_miss"],
            )
            await asyncio.sleep(0.3)

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Polymarket API winner backfill error: %s", e)
    finally:
        await service.close()

    logger.info(
        "Polymarket API winner backfill: %d checked, %d winners, %d losers, "
        "%d prices_synced, %d api_miss, %d no_match, %d not_settled, %d errors",
        stats["markets_checked"],
        stats["winners_set"],
        stats["losers_set"],
        stats["prices_synced"],
        stats["api_miss"],
        stats["no_match"],
        stats["not_settled"],
        len(stats["errors"]),
    )
    return stats


async def _resolve_winners_only(limit: int = 2000):
    """Dedicated winner resolution from authoritative sources only.

    Runs independently from the full _backfill_all_winners pipeline,
    which spends most of its 14-min budget on calibration prices,
    DataGolf leaderboards, commence_time fixes, and other non-resolution
    work. This function focuses solely on setting is_winner from:
    - Moneyline repair (re-null misresolved non-moneyline)
    - Score-based resolution (moneyline, BTTS, spreads, totals, player props)
    - Kalshi per-event API settlement
    - Kalshi markets API settlement (for old events with empty per-event responses)
    - Polymarket API settlement
    - Clean resolution (pass2_guess → clean_resolution upgrade)
    - Pass 1 clean resolution (current_probability at extremes)
    """
    import time as _t

    _start = _t.monotonic()
    stats = {}

    # #991: resolve_winners intermittently busts its 540s soft limit — the
    # cumulative phases (esp. poly_api limit=5000 + kalshi_markets limit=10000,
    # aggravated by aged backlog rows) occasionally overrun. Add an overall
    # deadline with margin: the forward-resolution phases (score/props) run first
    # and always, and the heavy backlog-draining phases early-return before the
    # wall so partial progress persists (each phase already commits). Scheduling
    # only — no re-grades (gotcha #21). Same class as #107/#969/#984.
    _DEADLINE_S = 450.0  # 90s margin under soft_time_limit=540

    def _over_budget():
        return _t.monotonic() - _start > _DEADLINE_S

    def _budget_exit(reason):
        stats["deadline_hit"] = reason
        stats["duration_seconds"] = round(_t.monotonic() - _start, 1)
        return stats

    # Phase 0: Fix stale scheduled events
    # 13,524 events stuck in 'scheduled' despite being completed.
    # Transitioning to 'closed' makes them eligible for ESPN ID matching,
    # score backfill, and score-based winner resolution.
    try:
        async with get_task_session() as session:
            r = await session.execute(text("""
                    UPDATE events
                    SET status = 'closed'
                    WHERE status = 'scheduled'
                      AND commence_time < NOW() - INTERVAL '2 days'
                """))
            stats["stale_scheduled_fixed"] = r.rowcount
            await session.commit()
    except Exception as e:
        stats["stale_fix_error"] = str(e)[:200]

    # Phase 0b: Backfill ESPN IDs + scores for newly-eligible events
    # The stale fix above may have unlocked thousands of events that
    # now qualify for ESPN matching and score fetching.
    try:
        from app.tasks.espn_sync import _backfill_espn_ids, _backfill_box_scores

        espn_id_stats = await _backfill_espn_ids(limit=500)
        stats["espn_ids_matched"] = espn_id_stats.get("events_matched", 0)

        box_stats = await _backfill_box_scores(limit=200, priority_calibration=True)
        stats["box_scores_fetched"] = box_stats.get("fetched", 0)
    except Exception as e:
        stats["espn_backfill_error"] = str(e)[:200]

    # Moneyline repair
    try:
        async with get_task_session() as session:
            r = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET is_winner = NULL, resolution_source = NULL
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'kalshi'
                      AND fo.resolution_source = 'game_score'
                      AND fm.external_id ~* '(teamtotal|spread|pts|reb|ast|3pt|blk|stl|hrr|hit|tb|ks|1hwinner|2hwinner|1htotal|2htotal|1hspread|mention|rfi|f5)'
                """))
            stats["ml_repair"] = r.rowcount
            await session.commit()
    except Exception as e:
        stats["ml_repair_error"] = str(e)[:200]

    # Phase 0c: Link unlinked Kalshi game markets to events
    # Uses market NAME ("Kansas at Arizona: Total Points") to extract team
    # names, plus ticker date parsing. Covers NCAAB, NBA, NHL, MLB.
    try:
        import re as _re
        from app.utils.prediction_market_matching import extract_game_date_from_ticker
        from datetime import timedelta

        _MATCHUP_RE = _re.compile(
            r"^(.+?)\s+(?:at|vs\.?|v)\s+(.+?)(?:\s*:\s*.+)?$", _re.IGNORECASE
        )

        async with get_task_session() as session:
            unlinked = await session.execute(
                text("""
                    SELECT fm.id, fm.external_id, fm.name
                    FROM futures_markets fm
                    WHERE fm.source = 'kalshi'
                      AND fm.event_id IS NULL
                      AND EXISTS (
                          SELECT 1 FROM futures_outcomes fo
                          WHERE fo.market_id = fm.id
                            AND fo.resolution_source = 'pass2_guess'
                      )
                      AND fm.name LIKE '%at%:%'
                    LIMIT 1000
                """),
            )
            markets_to_link = unlinked.all()

            linked = 0
            for mkt in markets_to_link:
                game_date = extract_game_date_from_ticker(mkt.external_id)
                if not game_date:
                    continue

                m = _MATCHUP_RE.match(mkt.name or "")
                if not m:
                    continue

                team_a = m.group(1).strip()
                team_b = m.group(2).strip()
                if len(team_a) < 2 or len(team_b) < 2:
                    continue

                match = await session.execute(
                    text("""
                        SELECT e.id FROM events e
                        WHERE e.commence_time BETWEEN :start AND :end
                          AND e.status IN ('completed', 'closed')
                          AND (
                              (LOWER(e.home_team_name) LIKE :ta AND LOWER(e.away_team_name) LIKE :tb)
                              OR (LOWER(e.home_team_name) LIKE :tb AND LOWER(e.away_team_name) LIKE :ta)
                          )
                        ORDER BY ABS(EXTRACT(EPOCH FROM e.commence_time - :date))
                        LIMIT 1
                    """),
                    {
                        "start": game_date - timedelta(hours=28),
                        "end": game_date + timedelta(hours=28),
                        "ta": f"%{team_a.lower()}%",
                        "tb": f"%{team_b.lower()}%",
                        "date": game_date,
                    },
                )
                event_row = match.first()
                if event_row:
                    await session.execute(
                        text(
                            "UPDATE futures_markets SET event_id = :eid WHERE id = :mid"
                        ),
                        {"eid": event_row[0], "mid": mkt.id},
                    )
                    linked += 1

            await session.commit()
            stats["kalshi_linked"] = linked
            stats["kalshi_link_candidates"] = len(markets_to_link)
    except Exception as e:
        stats["kalshi_link_error"] = str(e)[:200]

    # Score-based resolution
    score_stats = await _resolve_kalshi_from_scores()
    spread_total_stats = await _resolve_kalshi_spread_total_from_scores()
    # #140: grade the ungraded Polymarket full-game Over/Under cohort from the
    # linked event's final score (deterministic, no Gamma API — #137 residual
    # resolution-completeness gap, not model bias).
    poly_total_stats = await _resolve_polymarket_total_from_scores()
    stats["poly_total_score"] = {
        "graded": poly_total_stats.get("graded", 0),
        "push_skip": poly_total_stats.get("push_skip", 0),
        "no_parse": poly_total_stats.get("no_parse", 0),
    }
    # #939: correct NHL spread outcomes pinned True/False by the old
    # complementary resolver (the fixed resolver above can't reach them — the
    # HAVING clause skips markets that still hold a game_score is_winner=True).
    nhl_spread_regrade_stats = await _regrade_kalshi_nhl_spread_inversions()
    stats["nhl_spread_regrade"] = {
        "checked": nhl_spread_regrade_stats.get("checked", 0),
        "flipped": nhl_spread_regrade_stats.get("flipped", 0),
    }
    # #945: re-grade Kalshi TOTAL game_score (same HAVING-skip staleness as the
    # spread cohort; never re-pulled). Idempotent + write-on-change.
    total_regrade_stats = await _regrade_kalshi_total_inversions()
    stats["total_regrade"] = {
        "checked": total_regrade_stats.get("checked", 0),
        "flipped": total_regrade_stats.get("flipped", 0),
    }
    # #938: clear stale settlement_sync extra winners on golf field markets here
    # (the settlement_sync block in _backfill_all_winners is starved before it
    # runs — #898). Idempotent + write-on-change.
    golf_extra_winner_stats = await _regrade_golf_extra_winners()
    stats["golf_extra_winner_regrade"] = {
        "cleared": golf_extra_winner_stats.get("cleared", 0),
    }
    player_prop_stats = await _resolve_kalshi_player_props_from_boxscore()
    total_bases_stats = await _resolve_kalshi_total_bases_from_boxscore()
    period_prop_stats = await _resolve_kalshi_period_props()
    stats["score"] = {
        "moneyline": score_stats.get("moneyline", 0),
        "btts": score_stats.get("btts", 0),
        "total": spread_total_stats.get("total", 0),
        "player_props": player_prop_stats.get("resolved", 0),
        "total_bases": total_bases_stats.get("resolved", 0),
    }

    # #991: forward score-resolution done — stop before the heavy backlog
    # drainers (poly_api/kalshi_markets) if we're near the wall.
    if _over_budget():
        return _budget_exit("before_polymarket_api")

    # Polymarket API settlement (concurrent condition_id lookups)
    poly_api_stats = await _backfill_polymarket_winners_from_api(limit=5000)
    stats["polymarket_api"] = {
        "winners": poly_api_stats.get("winners_set", 0),
        "losers": poly_api_stats.get("losers_set", 0),
        "api_miss": poly_api_stats.get("api_miss", 0),
        "prices_synced": poly_api_stats.get("prices_synced", 0),
        "skipped_dead": poly_api_stats.get("skipped_dead", 0),
    }

    # Kalshi settled events — lean winner-only scan (no snapshots/volume)
    try:
        import asyncio as _asyncio
        from app.services.kalshi_api import KalshiAPIService
        from app.tasks.redis_state import get_redis_client

        _rc2 = get_redis_client()
        _kalshi_start = _t.monotonic()
        _KALSHI_BUDGET_SECONDS = 180

        # Dynamically discover series with unresolved outcomes instead of
        # a hardcoded list. Sorted by count DESC so the biggest gaps get
        # scanned first within the time budget.
        async with get_task_session() as _ds:
            _sr = await _ds.execute(text("""
                SELECT REGEXP_REPLACE(fm.external_id, '-.*', '') AS series,
                       COUNT(*) AS n
                FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                WHERE fm.source = 'kalshi'
                  AND fm.status = 'resolved'
                  AND fm.external_id ~ '^KX'
                  AND NOT EXISTS (
                      SELECT 1 FROM futures_outcomes fo2
                      WHERE fo2.market_id = fo.market_id AND fo2.is_winner = true
                  )
                GROUP BY 1
                HAVING COUNT(*) >= 10
                ORDER BY 2 DESC
                LIMIT 80
            """))
            _top_series = [r[0] for r in _sr.all()]
        logger.info("resolve_winners: discovered %d series with unresolved outcomes", len(_top_series))
        settled_stats = {"pages": 0, "resolved": 0, "series_scanned": 0}
        service2 = KalshiAPIService()
        try:
            for series in _top_series:
                if _t.monotonic() - _kalshi_start > _KALSHI_BUDGET_SECONDS:
                    break
                settled_stats["series_scanned"] += 1
                ck = f"bainluck:settled_cursor:{series}"
                cursor = _rc2.get(ck)
                if cursor:
                    cursor = cursor.decode() if isinstance(cursor, bytes) else cursor
                empty_pages = 0
                for _ in range(100):
                    try:
                        events, cursor = await service2.get_events(
                            status="settled",
                            series_ticker=series,
                            with_nested_markets=True,
                            limit=200,
                            cursor=cursor,
                        )
                    except Exception:
                        break
                    settled_stats["pages"] += 1
                    if not events:
                        break
                    yes_t, no_t = [], []
                    for ev in events:
                        for mkt in ev.get("markets") or []:
                            tk = mkt.get("ticker", "")
                            rs = mkt.get("result")
                            if tk and rs is not None:
                                (yes_t if rs == "yes" else no_t).append(tk)
                    page_resolved = 0
                    async with get_task_session() as sess:
                        if yes_t:
                            r = await sess.execute(
                                text("""
                                UPDATE futures_outcomes SET is_winner=true, resolution_source='api_settlement', last_updated=NOW()
                                WHERE external_id=ANY(:t) AND (resolution_source IS NULL OR resolution_source IN """ + OVERWRITABLE_WINNER_SOURCES_SQL + """)
                            """),
                                {"t": yes_t},
                            )
                            page_resolved += r.rowcount
                        if no_t:
                            r = await sess.execute(
                                text("""
                                UPDATE futures_outcomes SET is_winner=false, resolution_source='api_settlement', last_updated=NOW()
                                WHERE external_id=ANY(:t) AND (resolution_source IS NULL OR resolution_source IN """ + OVERWRITABLE_WINNER_SOURCES_SQL + """)
                            """),
                                {"t": no_t},
                            )
                            page_resolved += r.rowcount
                        await sess.commit()
                    settled_stats["resolved"] += page_resolved
                    if page_resolved == 0:
                        empty_pages += 1
                    else:
                        empty_pages = 0
                    if not cursor:
                        _rc2.delete(ck)
                        break
                    if empty_pages >= 3:
                        _rc2.setex(ck, 86400 * 7, cursor)
                        break
                    _rc2.setex(ck, 86400 * 7, cursor)
                    await _asyncio.sleep(0.1)
        finally:
            await service2.close()
        stats["kalshi_settled_lean"] = settled_stats
    except Exception as e:
        stats["kalshi_settled_error"] = str(e)[:200]

    # #991: skip the 10K-limit kalshi markets pagination if near the wall.
    if _over_budget():
        return _budget_exit("before_kalshi_markets")

    # Kalshi markets API pagination
    kalshi_markets_stats = await _backfill_kalshi_winners_via_markets(limit=10000)
    stats["kalshi_markets"] = {
        "winners": kalshi_markets_stats.get("winners_set", 0),
        "losers": kalshi_markets_stats.get("losers_set", 0),
        "pages": kalshi_markets_stats.get("pages", 0),
    }

    # #991: last budget gate before the clean-resolution + upgrade tail.
    if _over_budget():
        return _budget_exit("before_clean_resolution")

    # Clean resolution (Pass 1 only)
    prob_stats = await _backfill_from_current_probability()
    stats["clean_resolution"] = {
        "winners": prob_stats.get("clean_winners", 0),
        "losers": prob_stats.get("clean_losers", 0),
    }

    # Phase 2b: upgrade pass2_guess LOSERS → clean_resolution
    # Only upgrade losers (is_winner=false) at extremes — these are
    # unambiguously correct. Winners at extremes might be wrong guesses
    # that happened to have high probability; leave them for authoritative
    # resolution (game_score, api_settlement).
    try:
        async with get_task_session() as session:
            r = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET resolution_source = 'clean_resolution'
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.status = 'resolved'
                      AND fo.resolution_source = 'pass2_guess'
                      AND fo.is_winner = false
                      AND fo.current_probability <= 0.05
                """))
            stats["guess_upgraded"] = r.rowcount
            await session.commit()
    except Exception as e:
        stats["guess_upgrade_error"] = str(e)[:200]

    stats["duration_seconds"] = round(_t.monotonic() - _start, 1)
    return stats


async def _backfill_all_winners(dry_run: bool = False, limit: int = 5000):
    """Run all winner backfill tasks."""
    import time as _t
    import gc

    _phase_times = {}
    _pipeline_start = _t.monotonic()

    def _persist_phase_timing(running):
        # #898: persist per-phase timing to Redis at every boundary so the
        # SoftTimeLimitExceeded culprit phase is observable WITHOUT Heroku-log
        # access (the task dies before its end-of-run summary emits, and the
        # logger.info lines are unreadable from the executor sandbox / EPERM).
        # The celery dashboard surfaces this key. `running` is the in-flight
        # phase — the one consuming budget when the task dies. Best-effort;
        # never breaks the task.
        try:
            import json as _json
            from datetime import datetime as _dt, timezone as _tz
            from app.tasks.redis_state import get_redis_client

            completed = {
                k: v for k, v in _phase_times.items()
                if isinstance(v, (int, float)) and k != running
            }
            get_redis_client().setex(
                "bainluck:backfill_phase_timing",
                86400,
                _json.dumps({
                    "updated_at": _dt.now(_tz.utc).isoformat(),
                    "cumulative_s": round(_t.monotonic() - _pipeline_start, 1),
                    "running_phase": running,
                    "completed": completed,
                    "soft_time_limit_s": 840,
                }),
            )
        except Exception:
            pass

    def _start_phase(name):
        _phase_times[name] = _t.monotonic()
        # #898: log per-phase timing in REAL TIME. The task dies at the 840s
        # soft_time_limit inside a late phase, so the end-of-task _phase_times
        # summary (return dict) never emits — making the budget-consuming phase
        # invisible. Logging at each boundary means the LAST "START" with no
        # matching "END" before SoftTimeLimitExceeded names the culprit phase.
        logger.info(
            "backfill phase START %s (cum %.1fs)",
            name,
            _t.monotonic() - _pipeline_start,
        )
        _persist_phase_timing(running=name)

    def _end_phase(name):
        if name in _phase_times:
            elapsed = _t.monotonic() - _phase_times[name]
            _phase_times[name] = round(elapsed, 1)
            logger.info(
                "backfill phase END %s: %.1fs (cum %.1fs)",
                name,
                elapsed,
                _t.monotonic() - _pipeline_start,
            )
            _persist_phase_timing(running=None)

    def _mark(name):
        # #898: lightweight running-phase marker for the UNWRAPPED maintenance
        # tail (link_props onward). The 03:45Z instrumented cycle proved the task
        # gets through resolution+API (~500s, incl. kalshi_api 254.7s) and dies in
        # this tail — but `running_phase` was stuck at "link_props" because nothing
        # after it was marked. These checkpoints update running_phase so the next
        # scheduled cycle's dashboard pinpoints which maintenance phase consumes
        # the remaining budget. No control-flow change; best-effort.
        logger.info("backfill phase MARK %s (cum %.1fs)", name, _t.monotonic() - _pipeline_start)
        _persist_phase_timing(running=name)

    # #898 TIME-BUDGET GUARD: the task dies at the 840s soft_time_limit deep in
    # the maintenance tail (09:45Z cycle: ~447s resolution+API, then candlestick/
    # trade backfills overran from ~489s to the wall). When a SoftTimeLimitExceeded
    # fires mid-phase the WHOLE cycle aborts and nothing after persists. This guard
    # lets the task RETURN SUCCESS before the wall: at the later heavy checkpoints,
    # if remaining budget is under the safety margin, return a partial result so the
    # cycle COMPLETES (resolution already ran first + committed) and the skipped
    # maintenance resumes next cycle (those phases are idempotent / process the
    # still-missing set). Bounded-downside: never worse than the current full abort.
    _SOFT_LIMIT_S = 840
    # #898 (Queue #94): margin raised 120 -> 240 so the effective budget is
    # ~600s (840 - 240), leaving comfortable headroom under the 840s soft limit
    # AND the 900s hard limit. With margin 120 the effective budget was ~720s,
    # which the rotating maintenance tail (candlestick/trades + polymarket_api,
    # 131-449s) could still overrun before a guard fired. 600s guarantees the
    # early-return wins the race against SoftTimeLimitExceeded.
    # #991 (Queue #117): raised 240 -> 300 after the loop regressed to busting
    # 840s again (5 fails/24h; last good run 802.4s = only 38s headroom). The
    # winner-resolution block below (kalshi_markets_api limit=20000 +
    # polymarket_api limit=10000, the latter Gamma-throttled) previously ran with
    # NO budget guard, so a slow run overran the wall before the drain guards.
    # 300 (effective budget ~540s) + the new pre-phase guards on those two heavy
    # drainers keep the early-return ahead of SoftTimeLimitExceeded.
    _BUDGET_MARGIN_S = 300

    def _budget_left():
        return _SOFT_LIMIT_S - (_t.monotonic() - _pipeline_start)

    def _partial_result(stopped_before):
        logger.warning(
            "backfill TIME-BUDGET GUARD: returning partial result before %s "
            "(%.0fs elapsed, %.0fs left); remaining maintenance resumes next cycle",
            stopped_before,
            _t.monotonic() - _pipeline_start,
            _budget_left(),
        )
        return {
            "status": "partial_budget_guard",
            "stopped_before": stopped_before,
            "pipeline_elapsed_s": round(_t.monotonic() - _pipeline_start, 1),
            "phase_times": {
                k: v for k, v in _phase_times.items()
                if isinstance(v, (int, float)) and v < 100000
            },
        }

    # ========================================================================
    # AUTHORITATIVE WINNER RESOLUTION — RUNS FIRST (see issue #898)
    #
    # The expensive pre-API maintenance phases (calibration prices touching
    # ~450K rows, DataGolf 429-throttled fetches) were consuming the entire
    # 840s soft_time_limit BEFORE the Kalshi/Polymarket winner-resolution
    # phases ran, so the task SoftTimeLimitExceeded'd on every run since
    # 2026-06-08 and resolved ZERO Kalshi winners for days. Winner resolution
    # is the task's primary purpose, so it MUST run before any maintenance
    # work and is no longer at the mercy of upstream-phase timing.
    # ========================================================================
    _start_phase("score_resolution")
    score_stats = await _resolve_kalshi_from_scores()
    spread_total_stats = await _resolve_kalshi_spread_total_from_scores()
    # #140: grade ungraded Polymarket full-game Over/Under from linked scores.
    poly_total_stats = await _resolve_polymarket_total_from_scores()
    player_prop_stats = await _resolve_kalshi_player_props_from_boxscore()
    total_bases_stats = await _resolve_kalshi_total_bases_from_boxscore()
    period_prop_stats = await _resolve_kalshi_period_props()
    _end_phase("score_resolution")

    # Authoritative API settlement — run BEFORE probability passes so API
    # results take priority over arbitrary Pass 2 picks.
    _start_phase("kalshi_api")
    kalshi_stats = await _backfill_kalshi_winners(limit=limit, dry_run=dry_run)
    _end_phase("kalshi_api")
    # #991: score_resolution + kalshi_api (the core forward resolution) have run.
    # Guard the heavy backlog drainers so a slow one can't overrun the 840s wall
    # before the drain guards below ever get a turn (early-return; idempotent
    # phases resume next cycle).
    if _budget_left() < _BUDGET_MARGIN_S:
        return _partial_result("kalshi_markets_api")
    _start_phase("kalshi_markets_api")
    kalshi_markets_stats = await _backfill_kalshi_winners_via_markets(limit=20000)
    _end_phase("kalshi_markets_api")
    if _budget_left() < _BUDGET_MARGIN_S:
        return _partial_result("polymarket_api")
    _start_phase("polymarket_api")
    poly_api_stats = await _backfill_polymarket_winners_from_api(limit=10000)
    _end_phase("polymarket_api")

    # Set is_winner from current_probability (all sources, fast). Only
    # handles markets not already resolved by API settlement above.
    prob_stats = await _backfill_from_current_probability()

    # Upgrade pass2_guess LOSERS → clean_resolution where current_probability
    # reached settlement extreme. Only losers — winners at extremes might be
    # wrong guesses.
    guess_upgrade_stats = {"upgraded": 0, "errors": []}
    try:
        async with get_task_session() as session:
            r = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET resolution_source = 'clean_resolution'
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.status = 'resolved'
                      AND fo.resolution_source = 'pass2_guess'
                      AND fo.is_winner = false
                      AND fo.current_probability <= 0.05
                """))
            guess_upgrade_stats["upgraded"] = r.rowcount
            await session.commit()
            if r.rowcount > 0:
                logger.info(
                    "pass2_guess upgrade: %d outcomes → clean_resolution", r.rowcount
                )
    except Exception as e:
        guess_upgrade_stats["errors"].append(str(e))

    _winner_resolution_elapsed = round(_t.monotonic() - _pipeline_start, 1)
    logger.info(
        "Winner resolution complete in %.1fs (kalshi_api winners=%d losers=%d, "
        "kalshi_markets winners=%d losers=%d, poly winners=%d losers=%d)",
        _winner_resolution_elapsed,
        kalshi_stats.get("winners_set", 0),
        kalshi_stats.get("losers_set", 0),
        kalshi_markets_stats.get("winners_set", 0),
        kalshi_markets_stats.get("losers_set", 0),
        poly_api_stats.get("winners_set", 0),
        poly_api_stats.get("losers_set", 0),
    )

    # The authoritative-resolution phases above fetch and materialize tens of
    # thousands of Kalshi/Polymarket API objects (limits 20K + 10K + 5K). Those
    # references would otherwise persist for the rest of this ~14-min task and
    # stack on top of the maintenance phases' memory, pushing the 512MB
    # worker-background dyno (concurrency=2) into an R14/R15 OOM mid-cycle
    # (#899). Release them before maintenance begins. gc here is the same
    # "free between heavy phases" pattern used by the volume/trade backfills.
    gc.collect()

    # Phase 0-fix-categories: DataGolf markets must always be golf.
    # LLM enrichment sometimes reclassifies them (e.g. "Volvo China Open"
    # ended up as hockey, adding 3K+ golf outcomes to hockey calibration).
    try:
        async with get_task_session() as session:
            fix_cat = await session.execute(text("""
                    UPDATE futures_markets
                    SET llm_sport_category = 'golf'
                    WHERE source = 'datagolf'
                      AND llm_sport_category != 'golf'
                """))
            if fix_cat.rowcount > 0:
                await session.commit()
                logger.info(
                    "Fixed %d DataGolf markets to golf category", fix_cat.rowcount
                )
    except Exception as e:
        logger.warning("DataGolf category fix failed: %s", e)

    _end_phase("fix_categories")

    # Phase 0-link-props: Link sports prop markets to their parent game events.
    _start_phase("link_props")
    # Must run BEFORE commence_time fixes and calibration price computation so
    # that newly linked markets get authoritative Event commence_time via Part A.
    # This is the primary fix for hockey calibration (19.6pp → ~3pp MCE).
    link_props_stats = {"total_linked": 0, "errors": []}
    try:
        from app.tasks.kalshi import _link_sports_props_to_events

        link_props_stats = await _link_sports_props_to_events()
    except Exception as e:
        link_props_stats["errors"].append(str(e))
        logger.warning("Link sports props failed: %s", e)

    # #898: close the link_props timer. Without this _end_phase, _phase_times
    # ["link_props"] kept its raw monotonic START value (~1.79M s ≈ 20 days on
    # the dashboard) — a corrupt entry that made the phase map untrustworthy. Now
    # it records real elapsed. Logging/measurement-only; no control-flow change.
    _end_phase("link_props")

    # #898 (Queue #94): the candlestick + trade-history backfills below are the
    # phases the rotating "killer" most often busts the 840s wall inside (they
    # run BEFORE the first existing guard at bookmaker_closing, so the task died
    # here before any guard could fire). Guard them: if resolution + the earlier
    # maintenance already consumed the budget, early-return so the cycle COMPLETES
    # (resolution ran first + committed; these backfills are idempotent/resumable).
    # #107: run the calibration DRAIN (bookmaker calibration → closing lines →
    # calibration_probability) BEFORE candlestick_trades. candlestick is the
    # heavy budget consumer; when it ran first the drain was starved on heavy
    # cycles and never updated cal_prob (kalshi MCE actively worsened 2.02→3.10).
    # Running the drain first guarantees it executes every cycle; candlestick now
    # enriches snapshots for the NEXT cycle's drain (eventually consistent).
    if _budget_left() < _BUDGET_MARGIN_S:
        return _partial_result("bookmaker_closing")
    _mark("bookmaker_closing")
    bookmaker_stats = await _precompute_bookmaker_calibration()
    closing_stats = await _backfill_closing_lines()

    if _budget_left() < _BUDGET_MARGIN_S:
        return _partial_result("calibration_prices")
    _mark("calibration_prices")
    cal_price_stats = await _compute_calibration_prices()

    # #137 calibration-integrity repairs — run AFTER cal-price sets cp so we
    # correct the freshly-computed values. All three are cheap set-based UPDATEs
    # and idempotent (forward-fix each cycle):
    #   Item 1  poly Under sign-flip (cp/opening flipped to the correct side)
    #   Item 2a datagolf premature resolution (un-resolve, null bogus cp)
    #   Item 2b impossible both-sides=1.0 openings (null opening + impossible cp)
    _mark("calibration_integrity_137")
    poly_under_stats = await _regrade_polymarket_under_signflip()
    datagolf_premature_stats = await _unresolve_datagolf_premature()
    both_ones_stats = await _null_impossible_both_sides_openings()
    # #997: demote the guess side of both-winner mutually-exclusive binaries.
    # Like its siblings above it is budget-guarded out on heavy cycles, so it
    # ALSO runs as a dedicated beat (correct_both_winner_guess_side).
    both_winner_stats = await _correct_both_winner_guess_side()

    if _budget_left() < _BUDGET_MARGIN_S:
        return _partial_result("candlestick_trades")
    _mark("candlestick_trades")
    # Phase 0-candlestick: Backfill hourly snapshots from Kalshi for sparse outcomes.
    # Must run BEFORE calibration price computation so Part A has richer data.
    candlestick_stats = {"snapshots_created": 0, "errors": []}
    try:
        from app.tasks.kalshi import _backfill_candlestick_snapshots

        # #898: bounded per-cycle — the 09:45Z cycle proved candlestick+trade
        # backfills (limit=500) overran from ~489s to the 840s wall (~351s, the
        # single budget consumer). They're resumable (process series/outcomes
        # still missing cal_prob/snapshots each cycle), so a smaller per-cycle
        # limit drains over more cycles while letting each cycle COMPLETE.
        # #107: pass the cycle deadline so the inner loop early-returns BEFORE the
        # soft wall (the between-unit guard above can't stop a single long call).
        candlestick_stats = await _backfill_candlestick_snapshots(
            limit=100, deadline=_pipeline_start + _SOFT_LIMIT_S - _BUDGET_MARGIN_S
        )
    except Exception as e:
        candlestick_stats["errors"].append(str(e))
        logger.warning("Candlestick backfill failed: %s", e)

    # #898 (Queue #94): re-check the budget after candlestick ran — the trade
    # history backfill is the other half of the wall-busting block. Early-return
    # here too rather than entering it with no headroom.
    if _budget_left() < _BUDGET_MARGIN_S:
        return _partial_result("trades")
    # Phase 0-trades: Backfill snapshots from Kalshi trade history for outcomes
    # missing calibration_probability. Creates real traded-price snapshots that
    # our 2-hour polling missed. Must run BEFORE calibration price computation.
    trade_stats = {"snapshots_created": 0, "errors": []}
    try:
        from app.tasks.kalshi import _backfill_trade_history

        trade_stats = await _backfill_trade_history(
            limit=100, deadline=_pipeline_start + _SOFT_LIMIT_S - _BUDGET_MARGIN_S
        )
    except Exception as e:
        trade_stats["errors"].append(str(e))
        logger.warning("Trade history backfill failed: %s", e)

    # Candlestick + trade-history backfills above pull API response payloads
    # into memory; release them before the calibration/DataGolf phases (#899).
    gc.collect()

    # Phase 0-pre: Fix commence_time for golf + hockey (DB-only, no API calls).
    # Must run BEFORE calibration price computation so closing lines use correct dates.
    commence_stats = {"golf": 0, "hockey": 0, "golf_error": None, "hockey_error": None}
    from app.tasks.kalshi import _fix_golf_commence_times, _fix_hockey_commence_times

    try:
        commence_stats["golf"] = await _fix_golf_commence_times()
    except Exception as e:
        commence_stats["golf_error"] = str(e)
        logger.warning("Golf commence_time fix failed: %s", e)
    try:
        commence_stats["hockey"] = await _fix_hockey_commence_times()
    except Exception as e:
        commence_stats["hockey_error"] = str(e)
        logger.warning("Hockey commence_time fix failed: %s", e)

    _mark("group_ids")
    # Phase 0a: Backfill Polymarket group_id (no API, fast)
    group_stats = await _backfill_polymarket_group_ids()

    # Phase 0b: Backfill Kalshi group_id (no API, fast)
    kalshi_group_stats = await _backfill_kalshi_group_ids()

    # Phase 0c: DISABLED — the untradeable filter was nulling opening_probability
    # on outcomes the backfill pipeline is trying to recover, causing calibration
    # to regress every run (bugs #7, #8, #12). One-time cleanup that became an
    # ongoing regression source.
    no_snap_stats = {
        "nulled_zero_snap": 0,
        "nulled_low_snap": 0,
        "nulled_no_movement": 0,
    }

    # Phase 0c-repair: Restore opening_probability from first snapshot for
    # outcomes with null opening but real snapshot data. Uses DISTINCT ON
    # for bulk performance instead of correlated subqueries.
    _mark("retro_repair_tagging")
    repair_stats = {"restored": 0, "errors": []}
    try:
        for _ in range(5):
            async with get_task_session() as session:
                r = await session.execute(text("""
                        WITH first_snaps AS (
                            SELECT fo2.id AS outcome_id, snap.probability
                            FROM futures_outcomes fo2
                            JOIN futures_markets fm ON fm.id = fo2.market_id
                            CROSS JOIN LATERAL (
                                SELECT fos.probability
                                FROM futures_odds_snapshots fos
                                WHERE fos.outcome_id = fo2.id
                                  AND fos.probability > 0 AND fos.probability < 1
                                ORDER BY fos.captured_at ASC
                                LIMIT 1
                            ) snap
                            WHERE fm.status = 'resolved'
                              AND fo2.opening_probability IS NULL
                            LIMIT 100000
                        )
                        UPDATE futures_outcomes fo
                        SET opening_probability = fs.probability,
                            opening_source = 'first_snapshot'
                        FROM first_snaps fs
                        WHERE fo.id = fs.outcome_id
                    """))
                await session.commit()
                if r.rowcount == 0:
                    break
                repair_stats["restored"] += r.rowcount
    except Exception as e:
        repair_stats["errors"].append(str(e))

    # Phase 0c-retrotag: Tag resolution_source on pre-existing outcomes.
    # Runs in batches of 50K (proven to work within statement timeout).
    retro_stats = {"tagged": 0, "errors": []}
    try:
        for _ in range(5):
            async with get_task_session() as session:
                r = await session.execute(text("""
                        UPDATE futures_outcomes fo
                        SET resolution_source = 'clean_resolution'
                        WHERE fo.id IN (
                            SELECT fo2.id FROM futures_outcomes fo2
                            JOIN futures_markets fm ON fo2.market_id = fm.id
                            WHERE fm.status = 'resolved'
                              AND fo2.resolution_source IS NULL
                              AND fo2.current_probability IS NOT NULL
                              AND (fo2.current_probability >= 0.95
                                   OR fo2.current_probability <= 0.05)
                            LIMIT 50000
                        )
                    """))
                await session.commit()
                if r.rowcount == 0:
                    break
                retro_stats["tagged"] += r.rowcount
                logger.info("Retro-tagging: %d tagged this batch", r.rowcount)
    except Exception as e:
        retro_stats["errors"].append(str(e))
        logger.error("Retro-tagging error: %s", e)

    # Phase 0c-retrotag2: Tag remaining untagged outcomes with midrange
    # current_probability as pass2_guess (they were resolved by Pass 2's
    # arbitrary pick from stale probabilities, not from authoritative data).
    # Also tag NULL-source LOSER outcomes as 'pass2_loser' to stop them
    # from being scanned on every cycle (88K+ outcomes were NULL-source
    # with is_winner=false, never matching retrotag2 but still scanned).
    retro2_stats = {"tagged": 0, "losers_tagged": 0, "errors": []}
    try:
        for _ in range(3):
            async with get_task_session() as session:
                r = await session.execute(text("""
                        UPDATE futures_outcomes fo
                        SET resolution_source = 'pass2_guess'
                        WHERE fo.id IN (
                            SELECT fo2.id FROM futures_outcomes fo2
                            JOIN futures_markets fm ON fo2.market_id = fm.id
                            WHERE fm.status = 'resolved'
                              AND fo2.resolution_source IS NULL
                              AND fo2.is_winner = true
                              AND (fo2.current_probability IS NULL
                                   OR (fo2.current_probability > 0.05
                                       AND fo2.current_probability < 0.95))
                            LIMIT 50000
                        )
                    """))
                await session.commit()
                if r.rowcount == 0:
                    break
                retro2_stats["tagged"] += r.rowcount
                logger.info("Retro-tagging pass2_guess: %d tagged", r.rowcount)

        # Tag NULL-source losers so they stop being scanned
        for _ in range(5):
            async with get_task_session() as session:
                r = await session.execute(text("""
                        UPDATE futures_outcomes fo
                        SET resolution_source = 'pass2_loser'
                        WHERE fo.id IN (
                            SELECT fo2.id FROM futures_outcomes fo2
                            JOIN futures_markets fm ON fo2.market_id = fm.id
                            WHERE fm.status = 'resolved'
                              AND fo2.resolution_source IS NULL
                              AND fo2.is_winner = false
                            LIMIT 100000
                        )
                    """))
                await session.commit()
                if r.rowcount == 0:
                    break
                retro2_stats["losers_tagged"] += r.rowcount
    except Exception as e:
        retro2_stats["errors"].append(str(e))

    # #107: the bookmaker_closing / closing_lines / calibration_prices drain was
    # moved AHEAD of candlestick_trades (see above) so the calibration drain runs
    # FIRST every cycle — even when candlestick later exhausts the budget. (Old
    # position here starved the drain on heavy cycles → kalshi MCE worsened.)

    if _budget_left() < _BUDGET_MARGIN_S:
        return _partial_result("polymarket_group_api")
    _mark("polymarket_group_api")
    # Phase 0f: Backfill group_id from Polymarket Gamma API (resolved events)
    api_group_stats = await _backfill_polymarket_group_ids_from_api()

    if _budget_left() < _BUDGET_MARGIN_S:
        return _partial_result("datagolf_settlement")
    _mark("datagolf_settlement")
    # Phase 0g-settlement: Resolve DataGolf outcomes from historical outrights
    # settlement data. Uses bet_outcome_numeric (1=won, 0=lost) which is more
    # authoritative than leaderboard inference. Must run BEFORE leaderboard
    # resolution so settlement data takes priority.
    dg_settlement_stats = await _resolve_golf_from_historical_outrights()

    # Phase 0g-pre: Re-fetch full leaderboards for resolved DataGolf markets
    # that still have truncated (50-player) leaderboards from the old code.
    # Must run BEFORE _backfill_datagolf_winners() so the resolution logic
    # has the full field to work with.
    dg_leaderboard_stats = await _backfill_datagolf_leaderboards()

    # Phase 0g-fix: Null out is_winner on make_cut outcomes that were
    # incorrectly resolved from truncated leaderboards. Players ranked 51-70
    # who actually made the cut were marked as losers. Re-nulling lets
    # Phase 0g re-resolve them correctly with the full leaderboard.
    dg_makecut_fix_stats = {"nulled": 0, "errors": []}
    try:
        async with get_task_session() as session:
            r = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET is_winner = NULL, resolution_source = NULL
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'datagolf'
                      AND fm.status = 'resolved'
                      AND fm.external_id LIKE '%:make_cut'
                      AND fo.is_winner = false
                      AND fo.resolution_source = 'leaderboard'
                      AND jsonb_array_length(
                          COALESCE(fm.market_metadata->'leaderboard', '[]'::jsonb)
                      ) < 100
                """))
            dg_makecut_fix_stats["nulled"] = r.rowcount
            await session.commit()
            if r.rowcount > 0:
                logger.info(
                    "Golf make_cut fix: nulled %d wrongly-resolved outcomes", r.rowcount
                )
    except Exception as e:
        dg_makecut_fix_stats["errors"].append(str(e))

    # Phase 0g-retag: Mark DataGolf losers not on leaderboard as did_not_play.
    # These are players DataGolf predicted but who never competed. Their
    # is_winner=false is correct but they shouldn't be in calibration.
    try:
        async with get_task_session() as session:
            retag = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET resolution_source = 'did_not_play'
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'datagolf'
                      AND fm.status = 'resolved'
                      AND fo.is_winner = false
                      AND COALESCE(fo.resolution_source, '') NOT IN
                          ('did_not_play', 'withdrew', 'datagolf_played_lost')
                      AND fm.market_metadata IS NOT NULL
                      AND fm.market_metadata->'leaderboard' IS NOT NULL
                      AND jsonb_typeof(fm.market_metadata->'leaderboard') = 'array'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM jsonb_array_elements(fm.market_metadata->'leaderboard') AS lb
                          WHERE lb->>'dg_id' = SUBSTRING(fo.external_id FROM 4)
                      )
                """))
            if retag.rowcount > 0:
                await session.commit()
                logger.info(
                    "DataGolf retag: %d outcomes → did_not_play", retag.rowcount
                )
    except Exception as e:
        logger.warning("DataGolf retag failed: %s", e)

    # Phase 0g-retag2: For DataGolf markets WITHOUT a leaderboard, tag all
    # non-authoritative losers as did_not_play. Without leaderboard data we
    # can't verify who actually played. Resolution sources like 'all_losers'
    # and 'pass2_loser' are guesses — not verified against results.
    try:
        async with get_task_session() as session:
            retag2 = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET resolution_source = 'did_not_play'
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'datagolf'
                      AND fm.status = 'resolved'
                      AND fo.is_winner = false
                      AND fo.resolution_source IN ('all_losers', 'pass2_loser')
                """))
            if retag2.rowcount > 0:
                await session.commit()
                logger.info(
                    "DataGolf retag2: %d non-authoritative losers → did_not_play",
                    retag2.rowcount,
                )
    except Exception as e:
        logger.warning("DataGolf retag2 failed: %s", e)

    # #994 recover-first: the retags above VOID every loser absent from the STORED
    # (often partial) leaderboard, deleting players who PLAYED and lost →
    # datagolf survivorship. The recovery that reclassifies them back into the
    # curve ('datagolf_played_lost') runs as its OWN beat task
    # (recover_datagolf_participation), NOT here: this backfill pipeline is
    # budget-starved (the kalshi_api phase routinely eats the ~773s soft limit
    # before Phase 0g is even reached), so a phase call would rarely execute. The
    # dedicated task is decoupled + reliably drains the ~17K DNP cohort. retag1
    # above already skips 'datagolf_played_lost' so it can't re-clobber recovered
    # rows on the next cycle.

    # Phase 0-no-pregame: Tag outcomes where we have trade snapshots but ALL
    # are post-game → proven zero pre-game trading. These outcomes have extreme
    # cal_prob (fell back to opening at 0.90+) and snapshots created by the trade
    # backfill, but none before commence_time.
    # Requires: (a) at least 1 snapshot exists (trade data was fetched)
    #           (b) zero snapshots before commence_time
    #           (c) cal_prob = extreme opening (Part A couldn't find pre-game data)
    try:
        async with get_task_session() as session:
            npt = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET resolution_source = 'no_pregame_trading'
                    FROM futures_markets fm
                    LEFT JOIN events e ON e.id = fm.event_id
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'kalshi'
                      AND fm.status = 'resolved'
                      AND fo.is_winner = false
                      AND fo.calibration_probability = fo.opening_probability
                      AND (fo.opening_probability >= 0.90 OR fo.opening_probability <= 0.10)
                      AND COALESCE(fo.resolution_source, '') NOT IN
                          ('no_pregame_trading', 'did_not_play', 'withdrew')
                      AND COALESCE(e.commence_time, fm.commence_time) IS NOT NULL
                      AND EXISTS (
                          SELECT 1 FROM futures_odds_snapshots fos
                          WHERE fos.outcome_id = fo.id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM futures_odds_snapshots fos
                          WHERE fos.outcome_id = fo.id
                            AND fos.captured_at < COALESCE(e.commence_time, fm.commence_time)
                      )
                """))
            if npt.rowcount > 0:
                await session.commit()
                logger.info("No-pregame-trading: %d outcomes tagged", npt.rowcount)
    except Exception as e:
        logger.warning("No-pregame-trading tag failed: %s", e)

    # DataGolf leaderboard backfill above materializes full leaderboards
    # (100+ players each) across many resolved markets; release before the
    # remaining resolution passes (#899).
    gc.collect()

    if _budget_left() < _BUDGET_MARGIN_S:
        return _partial_result("datagolf_winners")
    _mark("datagolf_winners")
    # Phase 0g: DataGolf resolution from leaderboard (must run BEFORE generic
    # passes so Pass 3 doesn't overwrite with incorrect model-prediction logic)
    datagolf_stats = await _backfill_datagolf_winners()

    # Phase 0h: Kalshi golf cross-reference — uses DataGolf leaderboard to
    # resolve Kalshi golf markets where the API has purged settlement data.
    # Reuses _normalize_tournament() and _match_key() from routes/golf.py.
    golf_cross_stats = await _resolve_kalshi_golf_from_datagolf()

    # Phase 0g-matchups: Resolve Kalshi H2H and 3-ball golf markets using
    # DataGolf historical matchup data. Uses actual bet outcomes instead of
    # leaderboard position inference. Must run AFTER Phase 0h so leaderboard-
    # based resolution handles winner/top_N/make_cut first, and this handles
    # the 386 remaining H2H/3-ball markets.
    if _budget_left() < _BUDGET_MARGIN_S:
        return _partial_result("golf_matchups")
    _mark("golf_matchups")
    golf_matchup_stats = await _resolve_golf_matchups_from_datagolf()

    # Phase 0i: Sync is_winner from settled current_probability for golf.
    # Golf outcomes with current_prob at extremes have correct settlement
    # values, but is_winner was corrupted by the reset. Trust the settlement.
    golf_sync_stats = {"synced": 0, "errors": []}
    try:
        async with get_task_session() as session:
            r = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET is_winner = (fo.current_probability >= 0.95), resolution_source = 'settlement_sync', last_updated = NOW()
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'kalshi'
                      AND fm.llm_sport_category = 'golf'
                      AND fm.status = 'resolved'
                      AND fo.current_probability IS NOT NULL
                      AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
                      AND fo.is_winner != (fo.current_probability >= 0.95)
                      -- #938: settlement_sync trusts current_probability, but on
                      -- illiquid multi-candidate golf fields that "price" is a stale
                      -- one-sided YES-ask (e.g. 4 candidates frozen at 99% with no
                      -- bid and no trade — not a real settlement signal). It must NOT
                      -- promote a NEW winner on a market that already has an
                      -- authoritative leaderboard/API/score winner, which clobbered
                      -- DataGolf's single correct winner with stale extras (e.g. one
                      -- R3-leader market with 5 "winners"). Confirming a LOSER
                      -- (<=0.05) is always safe.
                      AND (
                          fo.current_probability <= 0.05
                          OR NOT EXISTS (
                              SELECT 1 FROM futures_outcomes fo2
                              WHERE fo2.market_id = fm.id
                                AND fo2.is_winner = true
                                AND fo2.resolution_source IN
                                    ('leaderboard', 'api_settlement', 'datagolf',
                                     'datagolf_matchup', 'game_score')
                          )
                      )
                """))
            golf_sync_stats["synced"] = r.rowcount

            # #938 re-grade: remove the stale settlement_sync EXTRA winners that
            # were already written on top of an authoritative winner. Flip only
            # the settlement_sync extras to False; never touch the authoritative
            # winner itself (gotcha #21 — no bulk reset, the leaderboard/API/score
            # winner stays). Scoped to golf fields that have an authoritative
            # winner, so a market is never left winner-less.
            regrade = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET is_winner = false, last_updated = NOW()
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'kalshi'
                      AND fm.llm_sport_category = 'golf'
                      AND fm.status = 'resolved'
                      AND fo.is_winner = true
                      AND fo.resolution_source = 'settlement_sync'
                      AND EXISTS (
                          SELECT 1 FROM futures_outcomes fo2
                          WHERE fo2.market_id = fm.id
                            AND fo2.is_winner = true
                            -- #845 batch 3: bespoke golf "a real authoritative/
                            -- deterministic winner exists" set — intentionally
                            -- NOT the full authority tier (golf never resolves via
                            -- box_score/scoring_plays/clob_*), so it is kept
                            -- context-specific rather than force-fit to the
                            -- ladder. Dropped the dead 'datagolf' source (never
                            -- written — resolution_source uses datagolf_settlement
                            -- / datagolf_matchup; verified absent from prod).
                            AND fo2.resolution_source IN
                                ('leaderboard', 'api_settlement',
                                 'datagolf_matchup', 'game_score')
                      )
                """))
            golf_sync_stats["regraded_extra_winners"] = regrade.rowcount
            await session.commit()
            if regrade.rowcount:
                logger.info(
                    "Golf settlement_sync re-grade (#938): cleared %d stale extra winners",
                    regrade.rowcount,
                )
    except Exception as e:
        golf_sync_stats["errors"].append(str(e))

    # Phase 1a-repair: Re-null outcomes on non-moneyline markets that were
    # incorrectly resolved by the moneyline resolver as game-winner markets.
    # See #755. The moneyline resolver processed team totals, spreads, and
    # props, setting is_winner based on who won the game instead of the
    # market-specific logic (margin, team score, player stats). Re-nulling
    # lets the correct resolvers (spread/total/player props) fix them.
    ml_repair_stats = {"nulled": 0, "errors": []}
    try:
        async with get_task_session() as session:
            r = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET is_winner = NULL, resolution_source = NULL
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'kalshi'
                      AND fo.resolution_source = 'game_score'
                      AND fm.external_id ~* '(teamtotal|spread|pts|reb|ast|3pt|blk|stl|hrr|hit|tb|ks|1hwinner|2hwinner|1htotal|2htotal|1hspread|mention|rfi|f5)'
                """))
            ml_repair_stats["nulled"] = r.rowcount
            await session.commit()
            if r.rowcount > 0:
                logger.info(
                    "Moneyline misresolution repair: nulled %d outcomes", r.rowcount
                )
    except Exception as e:
        ml_repair_stats["errors"].append(str(e))

    _pre_api_elapsed = round(_t.monotonic() - _pipeline_start, 1)
    logger.info("Backfill phases 0-0i complete in %.1fs", _pre_api_elapsed)

    # NOTE (#898): Authoritative winner resolution (score-based, Kalshi API,
    # Kalshi markets API, Polymarket API, current_probability, pass2_guess
    # loser upgrade) now runs at the TOP of this function, before the
    # expensive calibration/DataGolf maintenance phases above. It used to run
    # here, last, and was starved to zero by the 840s soft time limit.

    return {
        "link_sports_props": link_props_stats,
        "ml_misresolution_repair": ml_repair_stats,
        "guess_upgrade": guess_upgrade_stats,
        "retro_tagging": retro_stats,
        "retro_guess_tagging": retro2_stats,
        "commence_time_fixes": commence_stats,
        "polymarket_group_id": group_stats,
        "kalshi_group_id": kalshi_group_stats,
        "null_untradeable": no_snap_stats,
        "opening_repair": repair_stats,
        "closing_lines": closing_stats,
        "calibration_prices": cal_price_stats,
        "poly_under_signflip": poly_under_stats,
        "datagolf_premature_unresolve": datagolf_premature_stats,
        "impossible_both_ones": both_ones_stats,
        "both_winner_guess_flip": both_winner_stats,
        "polymarket_api_group_id": api_group_stats,
        "datagolf_settlement": dg_settlement_stats,
        "datagolf_leaderboard_backfill": dg_leaderboard_stats,
        "datagolf": datagolf_stats,
        "golf_cross_reference": golf_cross_stats,
        "golf_matchup_resolution": golf_matchup_stats,
        "golf_settlement_sync": golf_sync_stats,
        "kalshi_score_resolution": score_stats,
        "kalshi_spread_total_resolution": spread_total_stats,
        "polymarket_total_score_resolution": poly_total_stats,
        "kalshi_player_props": player_prop_stats,
        "kalshi_period_props": period_prop_stats,
        "from_probability": prob_stats,
        "kalshi_api": kalshi_stats,
        "kalshi_markets_api": kalshi_markets_stats,
        "polymarket_api": poly_api_stats,
        "bookmaker_calibration": bookmaker_stats,
        "phase_times_seconds": {
            "pre_api_phases": _pre_api_elapsed,
            **{k: v for k, v in _phase_times.items() if isinstance(v, (int, float))},
            "total": round(_t.monotonic() - _pipeline_start, 1),
        },
    }


async def _precompute_bookmaker_calibration():
    """Precompute per-bookmaker moneyline calibration and cache in Redis.

    Each bookmaker's closing moneyline (last pre-game snapshot) paired with
    the game outcome. Resolution is free (home_score > away_score). Devigged
    via home_prob / (home_prob + away_prob). Results stored as aggregated
    calibration buckets in Redis for the calibration endpoint to read.
    """
    import json as _json
    from app.tasks.redis_state import get_redis_client

    stats = {"bookmakers": 0, "data_points": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(text("""
                    WITH eligible_events AS (
                        SELECT e.id, e.commence_time, e.home_score, e.away_score,
                               s.key AS category
                        FROM events e
                        JOIN sports s ON s.id = e.sport_id
                        WHERE e.status IN ('completed', 'closed')
                          AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
                          AND e.home_score != e.away_score
                          AND e.commence_time IS NOT NULL
                    ),
                    event_bookmakers AS (
                        SELECT DISTINCT ee.id AS event_id, ee.commence_time,
                               ee.home_score, ee.away_score, ee.category,
                               os.bookmaker
                        FROM eligible_events ee
                        JOIN odds_snapshots os ON os.event_id = ee.id
                        WHERE os.captured_at < ee.commence_time
                          AND os.home_win_probability IS NOT NULL
                    )
                    SELECT
                        LEAST(FLOOR(prob * 10)::int, 9) AS bucket_idx,
                        category,
                        COUNT(*) AS n,
                        SUM(CASE WHEN won THEN 1 ELSE 0 END) AS winners,
                        AVG(prob) AS avg_prob,
                        SUM(prob::float) AS sum_prob,
                        SUM((prob::float - CASE WHEN won THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
                    FROM (
                        SELECT
                            cl.home_win_probability::float
                            / NULLIF(cl.home_win_probability::float + cl.away_win_probability::float, 0)
                            AS prob,
                            (eb.home_score > eb.away_score) AS won,
                            eb.category
                        FROM event_bookmakers eb
                        CROSS JOIN LATERAL (
                            SELECT os.home_win_probability, os.away_win_probability
                            FROM odds_snapshots os
                            WHERE os.event_id = eb.event_id
                              AND os.bookmaker = eb.bookmaker
                              AND os.captured_at < eb.commence_time
                              AND os.home_win_probability IS NOT NULL
                              AND os.away_win_probability IS NOT NULL
                              AND os.home_win_probability > 0
                              AND os.away_win_probability > 0
                            ORDER BY os.captured_at DESC
                            LIMIT 1
                        ) cl
                    ) outcomes
                    WHERE prob > 0.01 AND prob < 0.99
                    GROUP BY bucket_idx, category
                    ORDER BY bucket_idx, category
                """))
            rows = result.all()

            buckets = []
            for r in rows:
                buckets.append(
                    {
                        "bucket_idx": r.bucket_idx,
                        "source": "odds_api_bookmaker",
                        "category": r.category,
                        "price_moved": None,
                        "n": r.n,
                        "winners": r.winners,
                        "avg_prob": float(r.avg_prob),
                        "sum_prob": float(r.sum_prob),
                        "sum_sq_err": float(r.sum_sq_err),
                    }
                )
                stats["data_points"] += r.n

            # Store in Redis (expires in 24h, refreshed every 6h)
            try:
                redis_client = get_redis_client()
                redis_client.setex(
                    "bainluck:bookmaker_calibration",
                    86400,
                    _json.dumps(buckets),
                )
                stats["bookmakers"] = len(set(r.category for r in rows))
            except Exception as e:
                stats["errors"].append(f"Redis: {e}")

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Bookmaker calibration precomputation error: %s", e)

    logger.info(
        "Bookmaker calibration: %d data points across %d sports, %d errors",
        stats["data_points"],
        stats["bookmakers"],
        len(stats["errors"]),
    )
    return stats


async def _compute_calibration_prices():
    """Pre-compute calibration_probability on resolved outcomes.

    Uses the RIGHT price for calibration based on market type:
    - Part A: Event-linked markets → last snapshot before the EVENT's commence_time
      (real pre-game/tournament closing line from the events table, not the
      market's commence_time which is often the listing or resolution date)
    - Part A2: Non-event markets with commence_time (golf) → last snapshot before
      the MARKET's commence_time (pre-tournament closing line). Without this,
      golf markets fall through to Part B which uses opening_captured_at and
      grabs a stale price from when the market first opened (weeks before R1).
    - Part B: Non-event markets without commence_time → first snapshot ≥1h after
      opening (settled price)
    - Part C: Event-linked outcomes still at opening_probability → last non-extreme
      snapshot before event start (rescue for sparse-snapshot event-linked markets)
    - Fallback: opening_probability

    Part C is intentionally restricted to event-linked markets. For non-event
    markets (elections, economics, entertainment), opening_probability is the
    honest calibration price — Part C would grab settlement prices and pretend
    they were predictions.

    Uses compound index (outcome_id, captured_at) for fast DISTINCT ON.
    """
    stats = {
        "reset": 0,
        "with_commence": 0,
        "without_commence": 0,
        "rescued": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            stats["reset"] = 0

            # One-time remediation: NULL calibration_probability on golf and
            # hockey outcomes so Parts A/A2 recompute them. These sports had
            # inverted calibration curves in the 70-100% range because
            # commence_time inaccuracies caused mid-event prices to be used
            # as closing lines. The sanity check (Part A-sanity below) will
            # prevent the same problem from recurring.
            from datetime import date

            if date.today() <= date(2026, 6, 12):
                reset_gh = await session.execute(text("""
                        UPDATE futures_outcomes fo
                        SET calibration_probability = NULL
                        FROM futures_markets fm
                        WHERE fo.market_id = fm.id
                          AND fm.source = 'kalshi'
                          AND fm.status = 'resolved'
                          AND fm.llm_sport_category IN ('golf', 'hockey')
                          AND fo.calibration_probability IS NOT NULL
                    """))
                stats["reset_golf_hockey"] = reset_gh.rowcount
                if reset_gh.rowcount > 0:
                    await session.commit()
                    logger.info(
                        "Reset %d golf/hockey cal_probs for recomputation",
                        reset_gh.rowcount,
                    )
            else:
                stats["reset_golf_hockey"] = 0

            # Part A: Event-linked markets — real pre-event closing line
            # Batched at 100K. Pure SQL, no Python memory risk.
            # LATERAL subquery does one index seek per outcome via
            # idx_fos_outcome_captured(outcome_id, captured_at) instead
            # of DISTINCT ON which joins then sorts the full result set.
            # ORDER BY commence_time DESC so recent games are processed first.
            part_a_total = 0
            for _ in range(20):
                result_a = await session.execute(text("""
                        WITH needs_cal AS (
                            SELECT fo.id AS outcome_id, e.commence_time,
                                   fo.opening_probability
                            FROM futures_outcomes fo
                            JOIN futures_markets fm ON fm.id = fo.market_id
                            JOIN events e ON e.id = fm.event_id
                            WHERE fm.status = 'resolved'
                              AND fo.calibration_probability IS NULL
                              AND e.commence_time IS NOT NULL
                            ORDER BY e.commence_time DESC
                            LIMIT 100000
                        )
                        UPDATE futures_outcomes fo
                        SET calibration_probability = COALESCE(
                            closing.probability, nc.opening_probability
                        )
                        FROM needs_cal nc
                        LEFT JOIN LATERAL (
                            SELECT fos.probability
                            FROM futures_odds_snapshots fos
                            WHERE fos.outcome_id = nc.outcome_id
                              AND fos.captured_at < nc.commence_time
                              AND fos.probability > 0 AND fos.probability < 1
                            ORDER BY fos.captured_at DESC
                            LIMIT 1
                        ) closing ON true
                        WHERE fo.id = nc.outcome_id
                          AND COALESCE(closing.probability, nc.opening_probability) IS NOT NULL
                    """))
                await session.commit()
                part_a_total += result_a.rowcount
                if result_a.rowcount == 0:
                    break
                logger.info(
                    "Calibration Part A: batch processed %d (total %d)",
                    result_a.rowcount,
                    part_a_total,
                )
            stats["with_commence"] = part_a_total

            # Part A1-dg: DataGolf outcomes — opening_probability IS the calibration
            # price (model prediction, not a market price). No snapshot lookup needed.
            # #137 guard: never stamp a calibration price on a market whose
            # resolution_date is still in the future — that's a premature/glitch
            # resolution (gotcha #21, never guess). Requires the event to have
            # actually resolved (resolution_date <= now, falling back to
            # commence_time when resolution_date is missing).
            dg_result = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET calibration_probability = fo.opening_probability
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'datagolf'
                      AND fm.status = 'resolved'
                      AND fo.calibration_probability IS NULL
                      AND fo.opening_probability IS NOT NULL
                      AND COALESCE(fm.resolution_date, fm.commence_time) <= NOW()
                """))
            await session.commit()
            stats["datagolf_direct"] = dg_result.rowcount

            # Part A2: Non-event markets with commence_time on the market itself.
            # Kalshi/DataGolf golf markets have event_id IS NULL but DO have
            # commence_time (adjusted by _fix_golf_commence_times). Part A
            # skips them because it JOINs events. Part B uses opening_captured_at
            # which grabs the first-ever price rather than the closing line.
            #
            # This part uses fm.commence_time to get the real pre-tournament
            # closing line — the last snapshot before the tournament starts.
            # Without this, calibration uses a stale price from when the market
            # first opened (potentially weeks before the tournament).
            #
            # One-time reset: null calibration_probability on outcomes that
            # were previously set by Part B (stale opening-day price) so
            # Part A2 can recompute with the proper closing line.
            reset_a2 = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET calibration_probability = NULL
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.status = 'resolved'
                      AND fm.event_id IS NULL
                      AND fm.commence_time IS NOT NULL
                      AND fm.source != 'datagolf'
                      AND fo.calibration_probability IS NOT NULL
                      AND fo.calibration_probability = fo.opening_probability
                      AND fo.opening_probability IS NOT NULL
                """))
            await session.commit()
            stats["reset_a2"] = reset_a2.rowcount
            if reset_a2.rowcount > 0:
                logger.info("Calibration Part A2 reset: %d outcomes", reset_a2.rowcount)

            part_a2_total = 0
            for _ in range(20):
                result_a2 = await session.execute(text("""
                        WITH needs_cal AS (
                            SELECT fo.id AS outcome_id, fm.commence_time,
                                   fo.opening_probability
                            FROM futures_outcomes fo
                            JOIN futures_markets fm ON fm.id = fo.market_id
                            WHERE fm.status = 'resolved'
                              AND fo.calibration_probability IS NULL
                              AND fm.commence_time IS NOT NULL
                              AND (fm.event_id IS NULL)
                            ORDER BY fm.commence_time DESC
                            LIMIT 100000
                        )
                        UPDATE futures_outcomes fo
                        SET calibration_probability = COALESCE(
                            closing.probability, nc.opening_probability
                        )
                        FROM needs_cal nc
                        LEFT JOIN LATERAL (
                            SELECT fos.probability
                            FROM futures_odds_snapshots fos
                            WHERE fos.outcome_id = nc.outcome_id
                              AND fos.captured_at < nc.commence_time
                              AND fos.probability > 0 AND fos.probability < 1
                            ORDER BY fos.captured_at DESC
                            LIMIT 1
                        ) closing ON true
                        WHERE fo.id = nc.outcome_id
                          AND COALESCE(closing.probability, nc.opening_probability) IS NOT NULL
                    """))
                await session.commit()
                part_a2_total += result_a2.rowcount
                if result_a2.rowcount == 0:
                    break
                logger.info(
                    "Calibration Part A2: batch processed %d (total %d)",
                    result_a2.rowcount,
                    part_a2_total,
                )
            stats["with_market_commence"] = part_a2_total

            # Part A-sanity: Revert calibration_probability to opening_probability
            # when the computed value diverges too far from opening, indicating
            # that commence_time was wrong and the "closing line" was actually an
            # in-play price. This primarily affects:
            #   - Golf: commence_time heuristic (close_time - 4.5 days) can be
            #     inaccurate when DataGolf schedule isn't available, grabbing
            #     mid-tournament prices
            #   - Hockey: unlinked markets with ticker-derived commence_time that
            # No arbitrary sanity check — if calibration is off, we need to
            # find and fix the specific miscalculation (wrong commence_time,
            # wrong snapshot selection, etc.), not paper over it with filters.
            stats["sanity_reverted"] = 0

            # Part B: Non-event markets WITHOUT commence_time — settled price
            # or opening fallback. These are non-golf futures (elections,
            # economics, etc.) that have no tournament start date.
            # Batched at 100K. LATERAL subquery for efficient index seeks.
            part_b_total = 0
            for _ in range(20):
                result_b = await session.execute(text("""
                        WITH needs_cal AS (
                            SELECT fo.id AS outcome_id, fo.opening_captured_at,
                                   fo.opening_probability
                            FROM futures_outcomes fo
                            JOIN futures_markets fm ON fm.id = fo.market_id
                            LEFT JOIN events e ON e.id = fm.event_id
                            WHERE fm.status = 'resolved'
                              AND fo.calibration_probability IS NULL
                              AND (fm.event_id IS NULL OR e.commence_time IS NULL)
                            LIMIT 100000
                        )
                        UPDATE futures_outcomes fo
                        SET calibration_probability = COALESCE(
                            settled.probability, nc.opening_probability
                        )
                        FROM needs_cal nc
                        LEFT JOIN LATERAL (
                            SELECT fos.probability
                            FROM futures_odds_snapshots fos
                            WHERE fos.outcome_id = nc.outcome_id
                              AND nc.opening_captured_at IS NOT NULL
                              AND fos.captured_at >= nc.opening_captured_at + INTERVAL '1 hour'
                              AND fos.probability > 0 AND fos.probability < 1
                            ORDER BY fos.captured_at ASC
                            LIMIT 1
                        ) settled ON true
                        WHERE fo.id = nc.outcome_id
                          AND COALESCE(settled.probability, nc.opening_probability) IS NOT NULL
                    """))
                await session.commit()
                part_b_total += result_b.rowcount
                if result_b.rowcount == 0:
                    break
                logger.info(
                    "Calibration Part B: batch processed %d (total %d)",
                    result_b.rowcount,
                    part_b_total,
                )
            stats["without_commence"] = part_b_total

            # Part C: Rescue EVENT-LINKED outcomes where Part A fell back to
            # opening_probability (no pre-event snapshots existed).
            # Uses the last non-extreme snapshot BEFORE event start.
            # Restricted to event-linked markets only — for non-event markets,
            # opening_probability is the correct calibration price.
            rescued_total = 0
            for _ in range(100):
                result_c = await session.execute(text("""
                        WITH stuck AS (
                            SELECT fo.id AS outcome_id, fo.opening_probability,
                                   e.commence_time
                            FROM futures_outcomes fo
                            JOIN futures_markets fm ON fm.id = fo.market_id
                            JOIN events e ON e.id = fm.event_id
                            WHERE fm.status = 'resolved'
                              AND fm.event_id IS NOT NULL
                              AND e.commence_time IS NOT NULL
                              AND fo.calibration_probability IS NOT NULL
                              AND fo.opening_probability IS NOT NULL
                              AND fo.calibration_probability = fo.opening_probability
                            LIMIT 2000
                        )
                        UPDATE futures_outcomes fo
                        SET calibration_probability = ls.probability
                        FROM stuck s
                        LEFT JOIN LATERAL (
                            SELECT fos.probability
                            FROM futures_odds_snapshots fos
                            WHERE fos.outcome_id = s.outcome_id
                              AND fos.captured_at < s.commence_time
                              AND fos.probability > 0 AND fos.probability < 1
                            ORDER BY fos.captured_at DESC
                            LIMIT 1
                        ) ls ON true
                        WHERE fo.id = s.outcome_id
                          AND ls.probability IS NOT NULL
                          AND ls.probability != s.opening_probability
                    """))
                await session.commit()
                if result_c.rowcount == 0:
                    break
                rescued_total += result_c.rowcount
            stats["rescued"] = rescued_total

            await session.commit()

            # Part D: Null calibration_probability for extreme untradeable tails.
            # Outcomes with ≤2 snapshots at extreme prices (≥0.95 or ≤0.05)
            # where calibration fell back to opening are illiquid threshold
            # tails (e.g. "Player: 3+ Goals" at 0.99 with 1 snapshot).
            illiquid_result = await session.execute(text("""
                    UPDATE futures_outcomes fo
                    SET calibration_probability = NULL
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.status = 'resolved'
                      AND fo.calibration_probability IS NOT NULL
                      AND fo.opening_probability IS NOT NULL
                      AND (fo.opening_probability >= 0.95 OR fo.opening_probability <= 0.05)
                      AND fo.calibration_probability = fo.opening_probability
                      AND NOT EXISTS (
                          SELECT 1 FROM futures_odds_snapshots fos
                          WHERE fos.outcome_id = fo.id
                          LIMIT 3 OFFSET 2
                      )
                """))
            stats["illiquid_tails_nulled"] = illiquid_result.rowcount
            if illiquid_result.rowcount > 0:
                await session.commit()
                logger.info(
                    "Part D: nulled %d untradeable outcomes from calibration",
                    illiquid_result.rowcount,
                )

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Compute calibration prices error: %s", e)

    logger.info(
        "Calibration prices: reset=%d, reset_golf_hockey=%d, event_linked=%d, "
        "non_event=%d, rescued=%d, sanity_reverted=%d, illiquid=%d, errors=%d",
        stats["reset"],
        stats.get("reset_golf_hockey", 0),
        stats["with_commence"],
        stats["without_commence"],
        stats["rescued"],
        stats.get("sanity_reverted", 0),
        stats.get("illiquid_tails_nulled", 0),
        len(stats["errors"]),
    )
    return stats


async def _backfill_closing_lines():
    """Pre-compute closing line probabilities on completed events.

    For each completed event that has odds_snapshots before commence_time,
    finds the last snapshot and stores it as closing_home/away_probability.
    Runs in batches to stay within Celery time limits.
    """
    stats = {"updated": 0, "closing_spreads": 0, "closing_totals": 0, "errors": []}

    try:
        async with get_task_session() as session:
            # Only process events that don't already have closing_home_probability
            # and have both commence_time and scores. Process in batches of 5000.
            result = await session.execute(text("""
                    WITH events_needing_closing AS (
                        SELECT e.id, e.commence_time
                        FROM events e
                        WHERE e.status IN ('completed', 'closed')
                          AND e.closing_home_probability IS NULL
                          AND e.commence_time IS NOT NULL
                          AND e.home_score IS NOT NULL
                          AND e.away_score IS NOT NULL
                        LIMIT 5000
                    )
                    UPDATE events e
                    SET closing_home_probability = cl.home_win_probability,
                        closing_away_probability = 1.0 - cl.home_win_probability
                    FROM events_needing_closing enc
                    LEFT JOIN LATERAL (
                        SELECT os.home_win_probability
                        FROM odds_snapshots os
                        WHERE os.event_id = enc.id
                          AND os.captured_at < enc.commence_time
                          AND os.home_win_probability IS NOT NULL
                          AND os.home_win_probability > 0
                          AND os.home_win_probability < 1
                        ORDER BY os.captured_at DESC
                        LIMIT 1
                    ) cl ON true
                    WHERE e.id = enc.id
                      AND cl.home_win_probability IS NOT NULL
                """))
            stats["updated"] = result.rowcount
            await session.commit()

            # Backfill closing spreads — last snapshot before commence_time
            # with a non-null home_spread.
            spread_result = await session.execute(text("""
                    WITH events_needing_spread AS (
                        SELECT e.id, e.commence_time
                        FROM events e
                        WHERE e.status IN ('completed', 'closed')
                          AND e.closing_home_spread IS NULL
                          AND e.commence_time IS NOT NULL
                          AND e.home_score IS NOT NULL
                        LIMIT 5000
                    )
                    UPDATE events e
                    SET closing_home_spread = cs.home_spread,
                        closing_home_spread_odds = cs.home_spread_odds,
                        closing_away_spread_odds = cs.away_spread_odds
                    FROM events_needing_spread ens
                    LEFT JOIN LATERAL (
                        SELECT os.home_spread, os.home_spread_odds,
                               os.away_spread_odds
                        FROM odds_snapshots os
                        WHERE os.event_id = ens.id
                          AND os.captured_at < ens.commence_time
                          AND os.home_spread IS NOT NULL
                        ORDER BY os.captured_at DESC
                        LIMIT 1
                    ) cs ON true
                    WHERE e.id = ens.id
                      AND cs.home_spread IS NOT NULL
                """))
            stats["closing_spreads"] = spread_result.rowcount
            await session.commit()

            # Backfill closing totals — last snapshot before commence_time
            # with a non-null over_under.
            totals_result = await session.execute(text("""
                    WITH events_needing_totals AS (
                        SELECT e.id, e.commence_time
                        FROM events e
                        WHERE e.status IN ('completed', 'closed')
                          AND e.closing_over_under IS NULL
                          AND e.commence_time IS NOT NULL
                          AND e.home_score IS NOT NULL
                        LIMIT 5000
                    )
                    UPDATE events e
                    SET closing_over_under = ct.over_under,
                        closing_over_odds = ct.over_odds,
                        closing_under_odds = ct.under_odds
                    FROM events_needing_totals ent
                    LEFT JOIN LATERAL (
                        SELECT os.over_under, os.over_odds, os.under_odds
                        FROM odds_snapshots os
                        WHERE os.event_id = ent.id
                          AND os.captured_at < ent.commence_time
                          AND os.over_under IS NOT NULL
                        ORDER BY os.captured_at DESC
                        LIMIT 1
                    ) ct ON true
                    WHERE e.id = ent.id
                      AND ct.over_under IS NOT NULL
                """))
            stats["closing_totals"] = totals_result.rowcount
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Closing line backfill error: %s", e)

    logger.info(
        "Closing line backfill: %d probabilities, %d spreads, %d totals updated, %d errors",
        stats["updated"],
        stats["closing_spreads"],
        stats["closing_totals"],
        len(stats["errors"]),
    )
    return stats
