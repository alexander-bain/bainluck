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

from app.models import FuturesMarket, FuturesOutcome
from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)


async def _backfill_kalshi_winners(limit: int = 2000, dry_run: bool = False):
    """Fetch settled Kalshi events by ticker and set is_winner from settlement data.

    Uses targeted GET /events/{ticker} lookups instead of paginating all settled
    events. Much more efficient — O(markets needing backfill) not O(all settled).
    """
    import asyncio
    from app.services.kalshi_api import KalshiAPIService

    stats = {
        "tickers_queried": 0, "events_found": 0,
        "winners_set": 0, "losers_set": 0,
        "not_found": 0, "no_result": 0, "api_miss": 0,
        "errors": [],
    }

    async with get_task_session() as session:
        needs_backfill = await session.execute(
            text("""
                SELECT DISTINCT fm.external_id
                FROM futures_markets fm
                WHERE fm.source = 'kalshi'
                  AND fm.status = 'resolved'
                  AND NOT EXISTS (
                      SELECT 1 FROM futures_outcomes fo
                      WHERE fo.market_id = fm.id AND fo.is_winner = true
                  )
                  AND EXISTS (
                      SELECT 1 FROM futures_outcomes fo
                      WHERE fo.market_id = fm.id
                        AND fo.current_probability > 0.10
                  )
                LIMIT :limit
            """),
            {"limit": limit},
        )
        tickers = [r[0] for r in needs_backfill.all()]

    if not tickers:
        logger.info("Kalshi winner backfill: nothing to do")
        return stats

    logger.info("Kalshi winner backfill: %d tickers to look up", len(tickers))

    service = KalshiAPIService()
    try:
        batch_size = 50
        for batch_start in range(0, len(tickers), batch_size):
            batch = tickers[batch_start:batch_start + batch_size]

            async with get_task_session() as session:
                for event_ticker in batch:
                    stats["tickers_queried"] += 1
                    event_data = await service.get_event(event_ticker)

                    if not event_data:
                        stats["api_miss"] += 1
                        continue

                    stats["events_found"] += 1
                    nested = event_data.get("markets") or []

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
                                .values(is_winner=is_winner)
                            )
                            if updated.rowcount > 0:
                                if is_winner:
                                    stats["winners_set"] += updated.rowcount
                                else:
                                    stats["losers_set"] += updated.rowcount
                            else:
                                stats["not_found"] += 1

                if not dry_run:
                    await session.commit()

            logger.info(
                "Kalshi backfill: %d/%d tickers, %d found, %d winners, %d losers",
                min(batch_start + batch_size, len(tickers)), len(tickers),
                stats["events_found"], stats["winners_set"], stats["losers_set"],
            )
            await asyncio.sleep(0.2)

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Kalshi winner backfill error: %s", e)
    finally:
        await service.close()

    logger.info(
        "Kalshi winner backfill: %d queried, %d found, %d api_miss, "
        "%d winners, %d losers, %d not_found, %d errors",
        stats["tickers_queried"], stats["events_found"], stats["api_miss"],
        stats["winners_set"], stats["losers_set"],
        stats["not_found"], len(stats["errors"]),
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
    # Skip: head-to-head, round leaders, playoff, cut line, winning score
    return None


async def _resolve_kalshi_golf_from_datagolf():
    """Resolve Kalshi golf markets using DataGolf leaderboard results.

    Reuses existing cross-source matching from routes/golf.py:
    - _normalize_tournament() for tournament matching
    - _match_key() for player name matching
    - _datagolf_check_placement() for position → is_winner
    """
    from app.routes.golf import _normalize_tournament, _match_key

    stats = {"matched_tournaments": 0, "resolved_outcomes": 0,
             "no_tournament_match": 0, "no_player_match": 0,
             "skipped_type": 0, "errors": []}

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
                      AND external_id LIKE '%:win'
                """)
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
            kalshi_result = await session.execute(
                text("""
                    SELECT fm.id, fm.name, fm.external_id
                    FROM futures_markets fm
                    WHERE fm.source = 'kalshi'
                      AND fm.status = 'resolved'
                      AND fm.llm_sport_category = 'golf'
                """)
            )
            kalshi_markets = kalshi_result.all()

            for row in kalshi_markets:
                # Determine market type from name (external_id is the market
                # name for Kalshi golf, not a ticker prefix)
                market_type = _detect_golf_market_type(row.name or row.external_id or "")
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
                    text("SELECT id, name FROM futures_outcomes WHERE market_id = :mid"),
                    {"mid": row.id},
                )

                for out in outcomes.all():
                    key = _match_key(out.name or "")
                    pos_str = player_positions.get(key)

                    if pos_str is None:
                        if can_infer_absent:
                            won = False
                        else:
                            stats["no_player_match"] += 1
                            continue
                    else:
                        if market_type == "h2h":
                            stats["skipped_type"] += 1
                            continue
                        won = _datagolf_check_placement(pos_str, market_type)
                        if won is None:
                            continue

                    await session.execute(
                        text("UPDATE futures_outcomes SET is_winner = :won WHERE id = :oid"),
                        {"won": won, "oid": out.id},
                    )
                    stats["resolved_outcomes"] += 1

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Golf cross-ref error: %s", e)

    logger.info(
        "Golf cross-ref: %d tournaments matched, %d outcomes resolved, "
        "%d no_tournament, %d no_player, %d skipped_type, %d errors",
        stats["matched_tournaments"], stats["resolved_outcomes"],
        stats["no_tournament_match"], stats["no_player_match"],
        stats["skipped_type"], len(stats["errors"]),
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
            result = await session.execute(
                text("""
                    SELECT fm.id AS market_id, fm.name AS market_name,
                           fm.external_id AS ticker,
                           e.home_team, e.away_team,
                           e.home_score, e.away_score,
                           COUNT(fo.id) AS n_outcomes
                    FROM futures_markets fm
                    JOIN events e ON e.id = fm.event_id
                    JOIN futures_outcomes fo ON fo.market_id = fm.id
                    WHERE fm.source = 'kalshi'
                      AND fm.status = 'resolved'
                      AND e.status IN ('completed', 'closed')
                      AND e.home_score IS NOT NULL
                      AND e.away_score IS NOT NULL
                      AND fo.current_probability IS NOT NULL
                    GROUP BY fm.id, fm.name, fm.external_id,
                             e.home_team, e.away_team,
                             e.home_score, e.away_score
                    HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                    LIMIT 10000
                """)
            )
            markets = result.all()

            for row in markets:
                ticker_lower = (row.ticker or "").lower()

                # BTTS: both teams to score
                if "btts" in ticker_lower:
                    btts_yes = row.home_score > 0 and row.away_score > 0
                    await session.execute(
                        text("""
                            UPDATE futures_outcomes SET is_winner = :won
                            WHERE market_id = :mid
                        """),
                        {"won": btts_yes, "mid": row.market_id},
                    )
                    stats["btts"] += 1
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

                home_tokens = set(row.home_team.lower().split()) if row.home_team else set()
                away_tokens = set(row.away_team.lower().split()) if row.away_team else set()

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
                        text("UPDATE futures_outcomes SET is_winner = :won WHERE id = :oid"),
                        {"won": won, "oid": out.id},
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
        stats["moneyline"], stats["btts"], stats["skipped"], len(stats["errors"]),
    )
    return stats


import re

_SPREAD_RE = re.compile(
    r"(.+?) wins(?: the 1H)? by over (\d+\.?\d*)\s+(?:points|runs|goals)",
    re.IGNORECASE,
)
_TOTAL_RE = re.compile(
    r"Over (\d+\.?\d*)\s+(?:1H\s+)?(?:points|runs|goals)\s+scored",
    re.IGNORECASE,
)

_FIRST_HALF_PERIODS = {
    "q1", "q2", "1q", "2q", "1st", "2nd", "1st half", "first half",
    "1h", "top 1st", "bot 1st", "top 2nd", "bot 2nd", "top 3rd",
    "bot 3rd", "top 4th", "bot 4th", "top 5th", "bot 5th",
    "1st period", "2nd period",
}


async def _resolve_kalshi_spread_total_from_scores():
    """Resolve Kalshi spread and total markets from actual game scores.

    Handles both full-game and 1H markets:
    - Full-game spreads: "{team} wins by over N points" → check final margin
    - Full-game totals: "Over N points scored" → check final total
    - 1H spreads: "{team} wins the 1H by over N points" → reconstruct
      halftime score from scoring_plays
    - 1H totals: "Over N 1H points scored" → same
    """
    stats = {"spread": 0, "total": 0, "h1_spread": 0, "h1_total": 0,
             "no_plays": 0, "no_parse": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    SELECT fm.id AS market_id, fm.external_id AS ticker,
                           e.id AS event_id,
                           e.home_team, e.away_team,
                           e.home_score, e.away_score
                    FROM futures_markets fm
                    JOIN events e ON e.id = fm.event_id
                    JOIN futures_outcomes fo ON fo.market_id = fm.id
                    WHERE fm.source = 'kalshi'
                      AND fm.status = 'resolved'
                      AND e.status IN ('completed', 'closed')
                      AND e.home_score IS NOT NULL
                      AND e.away_score IS NOT NULL
                      AND fo.current_probability IS NOT NULL
                    GROUP BY fm.id, fm.external_id, e.id,
                             e.home_team, e.away_team,
                             e.home_score, e.away_score
                    HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                       AND COUNT(*) = 1
                    LIMIT 10000
                """)
            )
            markets = result.all()

            for row in markets:
                ticker_lower = (row.ticker or "").lower()
                is_1h = "1h" in ticker_lower or "1half" in ticker_lower

                # Get the single outcome's name
                out = await session.execute(
                    text("SELECT id, name FROM futures_outcomes WHERE market_id = :mid LIMIT 1"),
                    {"mid": row.market_id},
                )
                outcome = out.first()
                if not outcome or not outcome.name:
                    stats["no_parse"] += 1
                    continue

                name = outcome.name

                # Try spread pattern
                sm = _SPREAD_RE.search(name)
                if sm:
                    team_name = sm.group(1).strip()
                    line = float(sm.group(2))

                    if is_1h:
                        h1_scores = await _get_halftime_score(session, row.event_id)
                        if h1_scores is None:
                            stats["no_plays"] += 1
                            continue
                        h1_home, h1_away = h1_scores
                    else:
                        h1_home, h1_away = row.home_score, row.away_score

                    # Determine which team the spread is for
                    home_tokens = set(row.home_team.lower().split()) if row.home_team else set()
                    away_tokens = set(row.away_team.lower().split()) if row.away_team else set()
                    team_tokens = set(team_name.lower().split())

                    if team_tokens & home_tokens:
                        margin = h1_home - h1_away
                    elif team_tokens & away_tokens:
                        margin = h1_away - h1_home
                    else:
                        stats["no_parse"] += 1
                        continue

                    won = margin > line
                    await session.execute(
                        text("UPDATE futures_outcomes SET is_winner = :won WHERE id = :oid"),
                        {"won": won, "oid": outcome.id},
                    )
                    if is_1h:
                        stats["h1_spread"] += 1
                    else:
                        stats["spread"] += 1
                    continue

                # Try total pattern
                tm = _TOTAL_RE.search(name)
                if tm:
                    line = float(tm.group(1))

                    if is_1h:
                        h1_scores = await _get_halftime_score(session, row.event_id)
                        if h1_scores is None:
                            stats["no_plays"] += 1
                            continue
                        total = h1_scores[0] + h1_scores[1]
                    else:
                        total = row.home_score + row.away_score

                    won = total > line
                    await session.execute(
                        text("UPDATE futures_outcomes SET is_winner = :won WHERE id = :oid"),
                        {"won": won, "oid": outcome.id},
                    )
                    if is_1h:
                        stats["h1_total"] += 1
                    else:
                        stats["total"] += 1
                    continue

                stats["no_parse"] += 1

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Kalshi spread/total resolution error: %s", e)

    resolved = stats["spread"] + stats["total"] + stats["h1_spread"] + stats["h1_total"]
    logger.info(
        "Kalshi spread/total resolution: %d resolved (spread=%d, total=%d, "
        "h1_spread=%d, h1_total=%d), %d no_plays, %d no_parse, %d errors",
        resolved, stats["spread"], stats["total"],
        stats["h1_spread"], stats["h1_total"],
        stats["no_plays"], stats["no_parse"], len(stats["errors"]),
    )
    return stats


async def _get_halftime_score(session, event_id: int):
    """Reconstruct halftime score from scoring_plays."""
    result = await session.execute(
        text("""
            SELECT home_score, away_score
            FROM scoring_plays
            WHERE event_id = :eid
              AND LOWER(period) IN :periods
            ORDER BY captured_at DESC
            LIMIT 1
        """),
        {"eid": event_id, "periods": tuple(_FIRST_HALF_PERIODS)},
    )
    row = result.first()
    if row:
        return (row.home_score, row.away_score)
    return None


async def _backfill_datagolf_winners():
    """Resolve DataGolf placement markets from actual leaderboard results.

    DataGolf markets (make_cut, top_5, top_10, top_20, win) store model
    predictions in current_probability, NOT settlement prices. The generic
    Pass 3 (independent thresholds) incorrectly treats these as settlements.

    This function uses the leaderboard stored in market_metadata to
    determine actual placement results and set is_winner correctly.
    """
    stats = {"markets_processed": 0, "winners_set": 0, "losers_set": 0,
             "no_leaderboard": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    SELECT fm.id, fm.external_id, fm.market_metadata
                    FROM futures_markets fm
                    WHERE fm.source = 'datagolf'
                      AND fm.status = 'resolved'
                      AND fm.market_metadata IS NOT NULL
                """)
            )
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

                # For win/top_5/top_10/top_20: anyone NOT in the top-50
                # leaderboard is definitively a loser (position > 50).
                # For make_cut: can't determine (cut line is ~70, beyond top 50).
                can_infer_absent = market_type in ("win", "top_5", "top_10", "top_20")

                for out_row in outcomes.all():
                    ext = out_row.external_id or ""
                    if not ext.startswith("dg_"):
                        continue
                    dg_id = ext[3:]

                    pos_str = pos_by_dg.get(dg_id)
                    if pos_str is None:
                        if can_infer_absent:
                            won = False
                        else:
                            continue
                    else:
                        won = _datagolf_check_placement(pos_str, market_type)
                    if won is None:
                        continue

                    await session.execute(
                        text("""
                            UPDATE futures_outcomes SET is_winner = :won
                            WHERE id = :oid
                        """),
                        {"won": won, "oid": out_row.id},
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
        stats["markets_processed"], stats["winners_set"], stats["losers_set"],
        stats["no_leaderboard"], len(stats["errors"]),
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
        "clean_winners": 0, "clean_losers": 0,
        "mutex_winners": 0, "mutex_losers": 0,
        "threshold_winners": 0, "threshold_losers": 0,
        "all_losers_set": 0,
        "single_winners": 0, "single_losers": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            # Pass 1: Clean resolution (all at 0 or 1)
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
            stats["clean_winners"] = sum(1 for r in rows if r[0])
            stats["clean_losers"] = sum(1 for r in rows if not r[0])
            await session.commit()

            # Pass 2: Mutually-exclusive markets (prob sum 0.5-1.5)
            # Max-probability outcome is the winner.
            result2 = await session.execute(
                text("""
                    WITH stuck_markets AS (
                        SELECT fm.id AS market_id,
                               SUM(fo.current_probability) AS prob_sum,
                               MAX(fo.current_probability) AS max_prob,
                               COUNT(*) AS n_outcomes
                        FROM futures_markets fm
                        JOIN futures_outcomes fo ON fo.market_id = fm.id
                        WHERE fm.status = 'resolved'
                          AND fo.current_probability IS NOT NULL
                        GROUP BY fm.id
                        HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                           AND SUM(fo.current_probability) BETWEEN 0.5 AND 1.5
                           AND MAX(fo.current_probability) > 0.05
                           AND COUNT(*) >= 2
                        LIMIT 50000
                    ),
                    ranked AS (
                        SELECT fo.id AS outcome_id, fo.market_id,
                               fo.current_probability,
                               sm.max_prob,
                               ROW_NUMBER() OVER (
                                   PARTITION BY fo.market_id
                                   ORDER BY fo.current_probability DESC
                               ) AS rn
                        FROM futures_outcomes fo
                        JOIN stuck_markets sm ON sm.market_id = fo.market_id
                        WHERE fo.current_probability IS NOT NULL
                    )
                    UPDATE futures_outcomes fo
                    SET is_winner = (r.rn = 1)
                    FROM ranked r
                    WHERE fo.id = r.outcome_id
                    RETURNING fo.is_winner
                """)
            )
            rows2 = result2.all()
            stats["mutex_winners"] = sum(1 for r in rows2 if r[0])
            stats["mutex_losers"] = sum(1 for r in rows2 if not r[0])
            await session.commit()

            # Pass 3: Independent threshold markets (prob sum > 1.5)
            # Each outcome decided independently: > 0.50 = winner, < 0.50 = loser
            result3 = await session.execute(
                text("""
                    WITH threshold_markets AS (
                        SELECT fm.id AS market_id
                        FROM futures_markets fm
                        JOIN futures_outcomes fo ON fo.market_id = fm.id
                        WHERE fm.status = 'resolved'
                          AND fo.current_probability IS NOT NULL
                          AND fm.source != 'datagolf'
                        GROUP BY fm.id
                        HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                           AND SUM(fo.current_probability) > 1.5
                           AND COUNT(*) >= 2
                        LIMIT 50000
                    )
                    UPDATE futures_outcomes fo
                    SET is_winner = (fo.current_probability > 0.50)
                    FROM threshold_markets tm
                    WHERE fo.market_id = tm.market_id
                      AND fo.current_probability IS NOT NULL
                      AND fo.current_probability != 0.50
                    RETURNING fo.is_winner
                """)
            )
            rows3 = result3.all()
            stats["threshold_winners"] = sum(1 for r in rows3 if r[0])
            stats["threshold_losers"] = sum(1 for r in rows3 if not r[0])
            await session.commit()

            # Pass 4: All-losers markets — every outcome at <= 0.10
            # The winning outcome isn't in our DB; mark existing as losers
            result4 = await session.execute(
                text("""
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
                    SET is_winner = false
                    FROM all_loser_markets al
                    WHERE fo.market_id = al.market_id
                    RETURNING 1
                """)
            )
            stats["all_losers_set"] = result4.rowcount
            await session.commit()

            # Pass 5: Single-outcome binary markets (e.g., "Over 2.5 maps")
            # These have exactly 1 outcome, so passes 2-3 skip them (need >= 2).
            # If the probability clearly moved away from 0.50, resolve based on direction.
            result5 = await session.execute(
                text("""
                    WITH single_outcome AS (
                        SELECT fm.id AS market_id
                        FROM futures_markets fm
                        JOIN futures_outcomes fo ON fo.market_id = fm.id
                        WHERE fm.status = 'resolved'
                          AND fo.current_probability IS NOT NULL
                        GROUP BY fm.id
                        HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                           AND COUNT(*) = 1
                           AND MAX(fo.current_probability) != 0.50
                        LIMIT 50000
                    )
                    UPDATE futures_outcomes fo
                    SET is_winner = (fo.current_probability > 0.50)
                    FROM single_outcome so
                    WHERE fo.market_id = so.market_id
                      AND fo.current_probability IS NOT NULL
                    RETURNING fo.is_winner
                """)
            )
            rows5 = result5.all()
            stats["single_winners"] = sum(1 for r in rows5 if r[0])
            stats["single_losers"] = sum(1 for r in rows5 if not r[0])
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Current-probability winner backfill error: %s", e)

    total_w = stats["clean_winners"] + stats["mutex_winners"] + stats["threshold_winners"] + stats["single_winners"]
    total_l = (stats["clean_losers"] + stats["mutex_losers"] + stats["threshold_losers"]
               + stats["all_losers_set"] + stats["single_losers"])
    logger.info(
        "Current-probability winner backfill: %d winners (clean=%d, mutex=%d, threshold=%d, single=%d), "
        "%d losers (clean=%d, mutex=%d, threshold=%d, all_losers=%d, single=%d), %d errors",
        total_w, stats["clean_winners"], stats["mutex_winners"], stats["threshold_winners"],
        stats["single_winners"],
        total_l, stats["clean_losers"], stats["mutex_losers"], stats["threshold_losers"],
        stats["all_losers_set"], stats["single_losers"], len(stats["errors"]),
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
    stats = {"nulled_zero_snap": 0, "nulled_low_snap": 0, "nulled_no_movement": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    UPDATE futures_outcomes fo
                    SET opening_probability = NULL,
                        calibration_probability = NULL
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
                """)
            )
            stats["nulled_zero_snap"] = result.rowcount

            result2 = await session.execute(
                text("""
                    UPDATE futures_outcomes fo
                    SET opening_probability = NULL,
                        calibration_probability = NULL
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
                """)
            )
            stats["nulled_low_snap"] = result2.rowcount

            # Pass 3: outcomes with ≤5 snapshots where max-min spread < 2pp
            result3 = await session.execute(
                text("""
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
                    SET opening_probability = NULL,
                        calibration_probability = NULL
                    FROM snap_stats ss
                    WHERE fo.id = ss.outcome_id
                """)
            )
            stats["nulled_no_movement"] = result3.rowcount

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Null untradeable openings error: %s", e)

    logger.info(
        "Null untradeable openings: %d zero-snap, %d low-snap, %d no-movement, %d errors",
        stats["nulled_zero_snap"], stats["nulled_low_snap"],
        stats["nulled_no_movement"], len(stats["errors"]),
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

    stats = {"events_fetched": 0, "events_with_markets": 0,
             "markets_updated": 0, "zero_update_pages": 0, "errors": []}

    # Fast short-circuit: skip API pagination if no null group_ids
    async with get_task_session() as session:
        null_count = await session.execute(
            text("""
                SELECT COUNT(*) FROM futures_markets
                WHERE source = 'polymarket' AND status = 'resolved' AND group_id IS NULL
            """)
        )
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


async def _backfill_polymarket_winners_from_api(limit: int = 500):
    """Phase 3: Fetch settlement prices from Polymarket Gamma API.

    For stuck Polymarket markets where current_probability didn't reach
    settlement extremes (0/1), fetches the event from the Gamma API and
    uses outcome_prices for resolution. Sets is_winner directly.

    Uses GET /events/{event_id} (which returns settlement prices) and
    matches conditions by condition_id. The /markets/{id} endpoint does
    NOT accept condition_ids as path params.
    """
    import asyncio
    import json as _json
    from app.services.polymarket_api import PolymarketAPIService

    stats = {
        "markets_checked": 0, "winners_set": 0, "losers_set": 0,
        "api_miss": 0, "not_settled": 0, "no_match": 0, "errors": [],
    }

    async with get_task_session() as session:
        stuck = await session.execute(
            text("""
                SELECT fm.id, fm.external_id,
                       fm.market_metadata->>'polymarket_event_id' AS poly_event_id
                FROM futures_markets fm
                JOIN futures_outcomes fo ON fo.market_id = fm.id
                WHERE fm.source = 'polymarket'
                  AND fm.status = 'resolved'
                  AND fo.current_probability IS NOT NULL
                GROUP BY fm.id
                HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                   AND MAX(fo.current_probability) BETWEEN 0.05 AND 0.95
                LIMIT :limit
            """),
            {"limit": limit},
        )
        markets = stuck.all()

    if not markets:
        logger.info("Polymarket API winner backfill: nothing to do")
        return stats

    # Group by event_id to avoid duplicate API calls for sibling sub-markets
    by_event: dict[str, list] = {}
    for row in markets:
        eid = row.poly_event_id or row.external_id
        by_event.setdefault(eid, []).append(row)

    logger.info(
        "Polymarket API winner backfill: %d markets across %d events",
        len(markets), len(by_event),
    )

    service = PolymarketAPIService()
    try:
        event_ids = list(by_event.keys())
        batch_size = 50
        for batch_start in range(0, len(event_ids), batch_size):
            batch = event_ids[batch_start:batch_start + batch_size]

            async with get_task_session() as session:
                for event_id in batch:
                    event_data = await service.get_event_by_id(str(event_id))
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

                        # For decomposed sub-markets: external_id = condition_id
                        market_data = by_cond.get(condition_id)

                        # For parent markets: external_id = event_id, try first condition
                        if not market_data and condition_id == event_id and len(api_markets) == 1:
                            market_data = api_markets[0]

                        if not market_data:
                            stats["no_match"] += 1
                            continue

                        prices_raw = market_data.get("outcomePrices") or market_data.get("outcome_prices") or []
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
                        cid = market_data.get("conditionId") or market_data.get("condition_id") or condition_id
                        yes_ext = f"{cid}_yes"
                        no_ext = f"{cid}_no"

                        r1 = await session.execute(
                            update(FuturesOutcome)
                            .where(
                                FuturesOutcome.market_id == row.id,
                                FuturesOutcome.external_id == yes_ext,
                            )
                            .values(is_winner=yes_won)
                        )
                        r2 = await session.execute(
                            update(FuturesOutcome)
                            .where(
                                FuturesOutcome.market_id == row.id,
                                FuturesOutcome.external_id == no_ext,
                            )
                            .values(is_winner=(not yes_won))
                        )

                        updated = r1.rowcount + r2.rowcount
                        if updated > 0:
                            if yes_won:
                                stats["winners_set"] += r1.rowcount
                                stats["losers_set"] += r2.rowcount
                            else:
                                stats["losers_set"] += r1.rowcount
                                stats["winners_set"] += r2.rowcount

                await session.commit()

            logger.info(
                "Polymarket API backfill: %d/%d events, %d winners, %d losers, %d miss",
                min(batch_start + batch_size, len(event_ids)), len(event_ids),
                stats["winners_set"], stats["losers_set"], stats["api_miss"],
            )
            await asyncio.sleep(0.3)

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Polymarket API winner backfill error: %s", e)
    finally:
        await service.close()

    logger.info(
        "Polymarket API winner backfill: %d checked, %d winners, %d losers, "
        "%d api_miss, %d no_match, %d not_settled, %d errors",
        stats["markets_checked"], stats["winners_set"], stats["losers_set"],
        stats["api_miss"], stats["no_match"], stats["not_settled"],
        len(stats["errors"]),
    )
    return stats


async def _backfill_all_winners(dry_run: bool = False, limit: int = 5000):
    """Run all winner backfill tasks."""
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

    # Phase 0g: DataGolf resolution from leaderboard (must run BEFORE generic
    # passes so Pass 3 doesn't overwrite with incorrect model-prediction logic)
    datagolf_stats = await _backfill_datagolf_winners()

    # Phase 0h: Kalshi golf cross-reference — uses DataGolf leaderboard to
    # resolve Kalshi golf markets where the API has purged settlement data.
    # Reuses _normalize_tournament() and _match_key() from routes/golf.py.
    golf_cross_stats = await _resolve_kalshi_golf_from_datagolf()

    # Phase 1a: Kalshi score-based resolution for game markets linked to
    # Events. Resolves moneyline/BTTS/spreads/totals/1H props from actual
    # game scores even when the Kalshi API has purged the market data.
    score_stats = await _resolve_kalshi_from_scores()
    spread_total_stats = await _resolve_kalshi_spread_total_from_scores()

    # Phase 1b: Authoritative API settlement data — run BEFORE probability
    # passes so API results take priority over arbitrary Pass 2 picks.
    kalshi_stats = await _backfill_kalshi_winners(limit=limit, dry_run=dry_run)
    poly_api_stats = await _backfill_polymarket_winners_from_api(limit=2000)

    # Phase 2: Set is_winner from current_probability (all sources, fast)
    # Only handles markets not already resolved by API settlement above.
    prob_stats = await _backfill_from_current_probability()

    return {
        "commence_time_fixes": commence_stats,
        "polymarket_group_id": group_stats,
        "kalshi_group_id": kalshi_group_stats,
        "null_untradeable": no_snap_stats,
        "closing_lines": closing_stats,
        "calibration_prices": cal_price_stats,
        "polymarket_api_group_id": api_group_stats,
        "datagolf": datagolf_stats,
        "golf_cross_reference": golf_cross_stats,
        "kalshi_score_resolution": score_stats,
        "kalshi_spread_total_resolution": spread_total_stats,
        "from_probability": prob_stats,
        "kalshi_api": kalshi_stats,
        "polymarket_api": poly_api_stats,
    }


async def _compute_calibration_prices():
    """Pre-compute calibration_probability on resolved outcomes.

    Uses the RIGHT price for calibration based on market type:
    - Part A: Event-linked markets → last snapshot before the EVENT's commence_time
      (real pre-game/tournament closing line from the events table, not the
      market's commence_time which is often the listing or resolution date)
    - Part B: Non-event markets → first snapshot ≥1h after opening (settled price)
    - Part C: Event-linked outcomes still at opening_probability → last non-extreme
      snapshot before event start (rescue for sparse-snapshot event-linked markets)
    - Fallback: opening_probability

    Part C is intentionally restricted to event-linked markets. For non-event
    markets (elections, economics, entertainment), opening_probability is the
    honest calibration price — Part C would grab settlement prices and pretend
    they were predictions.

    Uses compound index (outcome_id, captured_at) for fast DISTINCT ON.
    """
    stats = {"reset": 0, "with_commence": 0, "without_commence": 0, "rescued": 0, "errors": []}

    try:
        async with get_task_session() as session:
            # Reset: NULL out calibration_probability on non-event markets
            # where old Part C set it to a near-settlement value. This lets
            # Part B reprocess them with the honest opening/settled price.
            reset_result = await session.execute(
                text("""
                    UPDATE futures_outcomes fo
                    SET calibration_probability = NULL
                    FROM futures_markets fm
                    WHERE fm.id = fo.market_id
                      AND fm.status = 'resolved'
                      AND fm.event_id IS NULL
                      AND fo.calibration_probability IS NOT NULL
                      AND fo.opening_probability IS NOT NULL
                      AND fo.calibration_probability != fo.opening_probability
                      AND (fo.calibration_probability < 0.02
                           OR fo.calibration_probability > 0.98)
                """)
            )
            stats["reset"] = reset_result.rowcount
            if stats["reset"] > 0:
                logger.info("Reset %d bad calibration prices on non-event markets",
                            stats["reset"])
                await session.commit()

            # Also reset event-linked markets so Part A reprocesses with
            # events.commence_time instead of the old fm.commence_time logic.
            reset_event_result = await session.execute(
                text("""
                    UPDATE futures_outcomes fo
                    SET calibration_probability = NULL
                    FROM futures_markets fm
                    WHERE fm.id = fo.market_id
                      AND fm.status = 'resolved'
                      AND fm.event_id IS NOT NULL
                      AND fo.calibration_probability IS NOT NULL
                      AND fo.opening_probability IS NOT NULL
                      AND (fo.calibration_probability < 0.02
                           OR fo.calibration_probability > 0.98)
                """)
            )
            stats["reset"] += reset_event_result.rowcount
            if reset_event_result.rowcount > 0:
                logger.info("Reset %d bad calibration prices on event-linked markets",
                            reset_event_result.rowcount)
                await session.commit()

            # Part A: Event-linked markets — real pre-event closing line
            # Uses events.commence_time (the actual game/tournament start) instead
            # of futures_markets.commence_time (which is the listing or resolution
            # date on Kalshi/Polymarket). Falls back to opening_probability when
            # no pre-event snapshot exists.
            result_a = await session.execute(
                text("""
                    WITH needs_cal AS (
                        SELECT fo.id AS outcome_id, e.commence_time,
                               fo.opening_probability
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fm.id = fo.market_id
                        JOIN events e ON e.id = fm.event_id
                        WHERE fm.status = 'resolved'
                          AND fo.calibration_probability IS NULL
                          AND fm.event_id IS NOT NULL
                          AND e.commence_time IS NOT NULL
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

            # Part B: Non-event markets (no event_id or no event commence_time)
            # Uses settled price (first snapshot >=1h after opening),
            # falls back to opening_probability. This is the honest
            # calibration price for elections, economics, entertainment,
            # weather — markets without a verifiable event start time.
            result_b = await session.execute(
                text("""
                    WITH needs_cal AS (
                        SELECT fo.id AS outcome_id, fo.opening_captured_at,
                               fo.opening_probability
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fm.id = fo.market_id
                        LEFT JOIN events e ON e.id = fm.event_id
                        WHERE fm.status = 'resolved'
                          AND fo.calibration_probability IS NULL
                          AND (fm.event_id IS NULL OR e.commence_time IS NULL)
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

            # Part C: Rescue EVENT-LINKED outcomes where Part A fell back to
            # opening_probability (no pre-event snapshots existed).
            # Uses the last non-extreme snapshot before event start.
            # Restricted to event-linked markets only — for non-event markets,
            # opening_probability is the correct calibration price.
            rescued_total = 0
            for _ in range(100):
                result_c = await session.execute(
                    text("""
                        WITH stuck AS (
                            SELECT fo.id AS outcome_id, fo.opening_probability
                            FROM futures_outcomes fo
                            JOIN futures_markets fm ON fm.id = fo.market_id
                            WHERE fm.status = 'resolved'
                              AND fm.event_id IS NOT NULL
                              AND fo.calibration_probability IS NOT NULL
                              AND fo.opening_probability IS NOT NULL
                              AND fo.calibration_probability = fo.opening_probability
                            LIMIT 2000
                        ),
                        last_snap AS (
                            SELECT DISTINCT ON (s.outcome_id)
                                s.outcome_id,
                                fos.probability
                            FROM stuck s
                            JOIN futures_odds_snapshots fos ON fos.outcome_id = s.outcome_id
                            WHERE fos.probability > 0 AND fos.probability < 1
                            ORDER BY s.outcome_id, fos.captured_at DESC
                        )
                        UPDATE futures_outcomes fo
                        SET calibration_probability = ls.probability
                        FROM last_snap ls
                        WHERE fo.id = ls.outcome_id
                          AND ls.probability != fo.opening_probability
                    """)
                )
                await session.commit()
                if result_c.rowcount == 0:
                    break
                rescued_total += result_c.rowcount
            stats["rescued"] = rescued_total

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Compute calibration prices error: %s", e)

    logger.info(
        "Calibration prices: reset=%d, event_linked=%d, non_event=%d, rescued=%d, errors=%d",
        stats["reset"], stats["with_commence"], stats["without_commence"],
        stats["rescued"], len(stats["errors"]),
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
            result = await session.execute(
                text("""
                    WITH events_needing_closing AS (
                        SELECT e.id, e.commence_time
                        FROM events e
                        WHERE e.status IN ('completed', 'closed')
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

            # Backfill closing spreads — last snapshot before commence_time
            # with a non-null home_spread.
            spread_result = await session.execute(
                text("""
                    WITH events_needing_spread AS (
                        SELECT e.id, e.commence_time
                        FROM events e
                        WHERE e.status IN ('completed', 'closed')
                          AND e.closing_home_spread IS NULL
                          AND e.commence_time IS NOT NULL
                          AND e.home_score IS NOT NULL
                        LIMIT 5000
                    ),
                    closing_spread AS (
                        SELECT DISTINCT ON (ens.id)
                            ens.id AS event_id,
                            os.home_spread,
                            os.home_spread_odds,
                            os.away_spread_odds
                        FROM events_needing_spread ens
                        JOIN odds_snapshots os ON os.event_id = ens.id
                        WHERE os.captured_at < ens.commence_time
                          AND os.home_spread IS NOT NULL
                        ORDER BY ens.id, os.captured_at DESC
                    )
                    UPDATE events e
                    SET closing_home_spread = cs.home_spread,
                        closing_home_spread_odds = cs.home_spread_odds,
                        closing_away_spread_odds = cs.away_spread_odds
                    FROM closing_spread cs
                    WHERE e.id = cs.event_id
                """)
            )
            stats["closing_spreads"] = spread_result.rowcount
            await session.commit()

            # Backfill closing totals — last snapshot before commence_time
            # with a non-null over_under.
            totals_result = await session.execute(
                text("""
                    WITH events_needing_totals AS (
                        SELECT e.id, e.commence_time
                        FROM events e
                        WHERE e.status IN ('completed', 'closed')
                          AND e.closing_over_under IS NULL
                          AND e.commence_time IS NOT NULL
                          AND e.home_score IS NOT NULL
                        LIMIT 5000
                    ),
                    closing_total AS (
                        SELECT DISTINCT ON (ent.id)
                            ent.id AS event_id,
                            os.over_under,
                            os.over_odds,
                            os.under_odds
                        FROM events_needing_totals ent
                        JOIN odds_snapshots os ON os.event_id = ent.id
                        WHERE os.captured_at < ent.commence_time
                          AND os.over_under IS NOT NULL
                        ORDER BY ent.id, os.captured_at DESC
                    )
                    UPDATE events e
                    SET closing_over_under = ct.over_under,
                        closing_over_odds = ct.over_odds,
                        closing_under_odds = ct.under_odds
                    FROM closing_total ct
                    WHERE e.id = ct.event_id
                """)
            )
            stats["closing_totals"] = totals_result.rowcount
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Closing line backfill error: %s", e)

    logger.info(
        "Closing line backfill: %d probabilities, %d spreads, %d totals updated, %d errors",
        stats["updated"], stats["closing_spreads"], stats["closing_totals"],
        len(stats["errors"]),
    )
    return stats
