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
                SELECT fm.external_id
                FROM futures_markets fm
                WHERE fm.source = 'kalshi'
                  AND fm.status = 'resolved'
                  AND (fm.resolution_date >= NOW() - INTERVAL '60 days'
                       OR fm.commence_time >= NOW() - INTERVAL '60 days')
                  AND EXISTS (
                      SELECT 1 FROM futures_outcomes fo
                      WHERE fo.market_id = fm.id
                        AND COALESCE(fo.resolution_source, '') != 'api_settlement'
                  )
                GROUP BY fm.external_id
                ORDER BY MAX(COALESCE(fm.resolution_date, fm.commence_time)) DESC NULLS LAST
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
                                .values(is_winner=is_winner, resolution_source="api_settlement")
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
                    SET is_winner = (fo.current_probability >= 0.95),
                        resolution_source = 'clean_resolution'
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
                                text("UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'game_score' WHERE id = :oid"),
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
                        text("UPDATE futures_outcomes SET is_winner = :won, resolution_source = :src WHERE id = :oid"),
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
        stats["matched_tournaments"], stats["resolved_outcomes"],
        stats["no_tournament_match"], stats["no_player_match"],
        stats["skipped_type"], len(stats["errors"]),
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
        "markets_found": 0, "tournaments_grouped": 0,
        "tournaments_with_dg": 0, "api_calls": 0,
        "outcomes_resolved": 0, "winners_set": 0, "losers_set": 0,
        "pushes": 0, "no_dg_event": 0, "no_matchup_data": 0,
        "no_player_match": 0, "errors": [],
    }

    try:
        # Step 1: Find unresolved Kalshi golf H2H and 3-ball markets
        async with get_task_session() as session:
            result = await session.execute(
                text("""
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
                """)
            )
            markets = result.all()

        if not markets:
            logger.info("Golf matchup resolution: nothing to do (0 unresolved H2H/3-ball markets)")
            return stats

        stats["markets_found"] = len(markets)
        logger.info("Golf matchup resolution: %d unresolved H2H/3-ball markets", len(markets))

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
            books_to_try = ["pinnacle", "bet365", "fanduel", "betmgm", "datagolf"]

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
                            r for r in raw_rows
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
                        market_round = int(round_match.group(1)) if round_match else None

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
                            result_data = (
                                matchup_outcomes.get((k1, k2, market_round))
                                or matchup_outcomes.get((k1, k2, None))
                            )
                            if result_data:
                                outcome_num = result_data["outcome"]
                                if outcome_num == -1:
                                    # Push — both are losers (tie)
                                    stats["pushes"] += 1
                                    continue
                                o1_won = outcome_num == 1
                            else:
                                # Try reverse: player2 vs player1
                                result_data_rev = (
                                    matchup_outcomes.get((k2, k1, market_round))
                                    or matchup_outcomes.get((k2, k1, None))
                                )
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
                                            resolution_source = 'datagolf_matchup'
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
                                    result_data = (
                                        matchup_outcomes.get((ki, kj, market_round))
                                        or matchup_outcomes.get((ki, kj, None))
                                    )
                                    if result_data:
                                        outcome_num = result_data["outcome"]
                                        if outcome_num == 1:
                                            pair_results[ki] += 1
                                        elif outcome_num == 0:
                                            pair_results[kj] += 1
                                        found_any = True
                                    else:
                                        # Try reverse
                                        result_data_rev = (
                                            matchup_outcomes.get((kj, ki, market_round))
                                            or matchup_outcomes.get((kj, ki, None))
                                        )
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
                            winners = [k for k, v in pair_results.items() if v == max_wins]

                            for oid, pk, _ in outcome_keys:
                                won = pk in winners and len(winners) == 1
                                await session.execute(
                                    text("""
                                        UPDATE futures_outcomes
                                        SET is_winner = :won,
                                            resolution_source = 'datagolf_matchup'
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
        stats["markets_found"], stats["tournaments_grouped"],
        stats["tournaments_with_dg"], stats["api_calls"],
        stats["outcomes_resolved"], stats["winners_set"], stats["losers_set"],
        stats["pushes"],
        stats["no_dg_event"], stats["no_matchup_data"],
        stats["no_player_match"], len(stats["errors"]),
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
                    WHERE fm.status = 'resolved'
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
                            UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'game_score'
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
                        text("UPDATE futures_outcomes SET is_winner = :won, resolution_source = :src WHERE id = :oid"),
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
        stats["moneyline"], stats["btts"], stats["skipped"], len(stats["errors"]),
    )
    return stats


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
                    WHERE fm.status = 'resolved'
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
                        text("UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'game_score' WHERE id = :oid"),
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


_PROP_TICKER_TO_STAT = {
    "kxnbapts": "points", "kxnbaast": "assists", "kxnbareb": "rebounds",
    "kxnbablk": "blocks", "kxnbastl": "steals", "kxnba3pt": "three pointers",
    "kxnhlgoal": "goals", "kxnhlanygoal": "goals", "kxnhlpts": "points",
    "kxnhlast": "assists", "kxnhlsaves": "saves",
    "kxmlbhit": "hits", "kxmlbhr": "home runs", "kxmlbks": "strikeouts",
}

_PROP_RE = re.compile(r"^(.+?):\s*(\d+)\+\s*$")

_COMBO_STATS = {
    "kxnbapa": ["points", "assists"],
    "kxnbapr": ["points", "rebounds"],
    "kxnbapra": ["points", "rebounds", "assists"],
    "kxnbara": ["rebounds", "assists"],
}


async def _resolve_kalshi_player_props_from_boxscore():
    """Resolve Kalshi player prop markets from ESPN box score data.

    Single-query fetch of all markets + outcomes + box scores, then
    processes in Python. No per-market DB round-trips.
    """
    stats = {"resolved": 0, "no_player": 0, "no_parse": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    SELECT fo.id AS outcome_id, fo.name AS outcome_name,
                           fm.external_id AS ticker, e.box_score_data
                    FROM futures_outcomes fo
                    JOIN futures_markets fm ON fm.id = fo.market_id
                    JOIN events e ON e.id = fm.event_id
                    WHERE fm.status = 'resolved'
                      AND e.box_score_data IS NOT NULL
                      AND fo.is_winner = false
                      AND NOT EXISTS (
                          SELECT 1 FROM futures_outcomes fo2
                          WHERE fo2.market_id = fm.id AND fo2.is_winner = true
                      )
                    LIMIT 10000
                """)
            )
            rows = result.all()

            updates = []
            for row in rows:
                ticker_lower = (row.ticker or "").lower()
                box_score = row.box_score_data or {}

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
                if not m:
                    stats["no_parse"] += 1
                    continue

                player_name = m.group(1).strip()
                threshold = int(m.group(2))

                player_stats = None
                for bs_name, bs_stats in box_score.items():
                    if bs_name.lower() == player_name.lower():
                        player_stats = bs_stats
                        break

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

                updates.append((row.outcome_id, actual >= threshold))

            # Batch update
            for oid, won in updates:
                await session.execute(
                    text("UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'box_score' WHERE id = :oid"),
                    {"won": won, "oid": oid},
                )
            stats["resolved"] = len(updates)
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Player prop resolution error: %s", e)

    logger.info(
        "Player prop resolution: %d resolved, %d no_player, %d no_parse, %d errors",
        stats["resolved"], stats["no_player"], stats["no_parse"],
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
        "2h": {"q3", "q4", "3q", "4q", "3rd", "4th", "2nd half", "second half", "2h", "ot"},
        "1q": {"q1", "1q", "1st"},
        "2q": {"q2", "2q", "2nd"},
        "3q": {"q3", "3q", "3rd"},
        "4q": {"q4", "4q", "4th"},
    }

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    SELECT fm.id AS market_id, fm.external_id AS ticker,
                           fm.name AS market_name,
                           e.id AS event_id,
                           e.home_score AS final_home, e.away_score AS final_away
                    FROM futures_markets fm
                    JOIN events e ON e.id = fm.event_id
                    JOIN futures_outcomes fo ON fo.market_id = fm.id
                    WHERE fm.status = 'resolved'
                      AND e.status IN ('completed', 'closed')
                      AND e.home_score IS NOT NULL
                      AND EXISTS (SELECT 1 FROM scoring_plays sp WHERE sp.event_id = e.id)
                    GROUP BY fm.id, fm.external_id, fm.name,
                             e.id, e.home_score, e.away_score
                    HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                       AND COUNT(*) = 1
                    LIMIT 5000
                """)
            )
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
                              AND LOWER(period) IN :periods
                            ORDER BY captured_at DESC LIMIT 1
                        """),
                        {"eid": row.event_id, "periods": tuple(periods)},
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
                    text("SELECT id, name FROM futures_outcomes WHERE market_id = :mid LIMIT 1"),
                    {"mid": row.market_id},
                )
                outcome = out.first()
                if not outcome or not outcome.name:
                    stats["no_parse"] += 1
                    continue

                # Try spread pattern
                sm = _SPREAD_RE.search(outcome.name)
                if sm:
                    line = float(sm.group(2))
                    won = (period_home - period_away) > line or (period_away - period_home) > line
                    await session.execute(
                        text("UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'scoring_plays' WHERE id = :oid"),
                        {"won": won, "oid": outcome.id},
                    )
                    stats["resolved"] += 1
                    continue

                # Try total pattern
                tm = _TOTAL_RE.search(outcome.name)
                if tm:
                    line = float(tm.group(1))
                    won = (period_home + period_away) > line
                    await session.execute(
                        text("UPDATE futures_outcomes SET is_winner = :won WHERE id = :oid"),
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
        stats["resolved"], stats["no_plays"], stats["no_parse"],
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
        "events_checked": 0, "api_calls": 0,
        "outcomes_resolved": 0, "winners_set": 0, "losers_set": 0,
        "no_match": 0, "skipped_no_db_markets": 0,
        "errors": [],
    }

    # Short-circuit: check if any unresolved DataGolf outcomes exist
    async with get_task_session() as session:
        unresolved_count = await session.execute(
            text("""
                SELECT COUNT(*) FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                WHERE fm.source = 'datagolf'
                  AND fm.status = 'resolved'
                  AND COALESCE(fo.resolution_source, '') NOT IN
                      ('datagolf_settlement', 'api_settlement')
            """)
        )
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
        books_to_try = ["datagolf", "pinnacle", "bet365", "fanduel", "betmgm"]
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
                    codes_to_try = make_cut_codes if market_type == "make_cut" else [market_type]

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
                                    r for r in rows
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
                                        resolution_source = 'datagolf_settlement'
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
        stats["events_checked"], stats["api_calls"],
        stats["outcomes_resolved"], stats["winners_set"], stats["losers_set"],
        stats["no_match"], stats["skipped_no_db_markets"],
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

    stats = {"markets_checked": 0, "events_refetched": 0, "markets_updated": 0,
             "already_full": 0, "api_miss": 0, "errors": []}

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
            logger.info("DataGolf leaderboard backfill: no truncated leaderboards found")
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
                    tour=tour, event_id=event_id, year=year,
                )

                if not historical or len(historical) <= 50:
                    stats["api_miss"] += 1
                    logger.info(
                        "DataGolf leaderboard backfill: no/insufficient historical data for %s (got %d)",
                        ext_id, len(historical) if historical else 0,
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
                                SET market_metadata = :meta::jsonb
                                WHERE id = :mid
                            """),
                            {"meta": _json.dumps(sib_meta), "mid": sib.id},
                        )
                        stats["markets_updated"] += 1

                    await session.commit()

                logger.info(
                    "DataGolf leaderboard backfill: updated %s with %d players (was 50)",
                    ext_id, len(full_leaderboard),
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
        stats["markets_checked"], stats["events_refetched"],
        stats["markets_updated"], stats["already_full"],
        stats["api_miss"], len(stats["errors"]),
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
                            UPDATE futures_outcomes SET is_winner = :won, resolution_source = 'leaderboard'
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
                    SET is_winner = (fo.current_probability >= 0.95),
                        resolution_source = 'clean_resolution'
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
                    SET is_winner = (r.rn = 1),
                        resolution_source = 'pass2_guess'
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
                    SET is_winner = (fo.current_probability > 0.50),
                        resolution_source = 'pass3_threshold'
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
                    SET is_winner = false,
                        resolution_source = 'all_losers'
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
                    SET is_winner = (fo.current_probability > 0.50),
                        resolution_source = 'pass3_threshold'
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

            # Pass 6: Binary markets (2 outcomes) where current_probability
            # didn't reach clean extremes but one side is clearly higher.
            # Settled Kalshi binary markets (overtime, BTTS, home runs)
            # often have prices like 0.45/0.55 — not clean enough for Pass 1
            # but the higher-probability outcome won. Use > 0.50 threshold.
            result6 = await session.execute(
                text("""
                    WITH binary_unresolved AS (
                        SELECT fm.id AS market_id
                        FROM futures_markets fm
                        JOIN futures_outcomes fo ON fo.market_id = fm.id
                        WHERE fm.status = 'resolved'
                          AND fo.current_probability IS NOT NULL
                        GROUP BY fm.id
                        HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                           AND COUNT(*) = 2
                           AND MAX(fo.current_probability) BETWEEN 0.10 AND 0.95
                           AND MAX(fo.current_probability) != MIN(fo.current_probability)
                        LIMIT 50000
                    )
                    UPDATE futures_outcomes fo
                    SET is_winner = (fo.current_probability > 0.50),
                        resolution_source = 'binary_higher_wins'
                    FROM binary_unresolved bu
                    WHERE fo.market_id = bu.market_id
                      AND fo.current_probability IS NOT NULL
                    RETURNING fo.is_winner
                """)
            )
            rows6 = result6.all()
            stats["binary_winners"] = sum(1 for r in rows6 if r[0])
            stats["binary_losers"] = sum(1 for r in rows6 if not r[0])
            await session.commit()

            # Pass 7: Multi-outcome markets (3+ outcomes) where the highest-
            # probability outcome is the winner. For resolved markets with
            # midrange prices, pick the outcome with max current_probability.
            result7 = await session.execute(
                text("""
                    WITH multi_unresolved AS (
                        SELECT fm.id AS market_id,
                               MAX(fo.current_probability) AS max_prob
                        FROM futures_markets fm
                        JOIN futures_outcomes fo ON fo.market_id = fm.id
                        WHERE fm.status = 'resolved'
                          AND fo.current_probability IS NOT NULL
                        GROUP BY fm.id
                        HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                           AND COUNT(*) >= 3
                           AND MAX(fo.current_probability) > 0.10
                        LIMIT 50000
                    )
                    UPDATE futures_outcomes fo
                    SET is_winner = (fo.current_probability = mu.max_prob),
                        resolution_source = 'multi_max_prob'
                    FROM multi_unresolved mu
                    WHERE fo.market_id = mu.market_id
                      AND fo.current_probability IS NOT NULL
                    RETURNING fo.is_winner
                """)
            )
            rows7 = result7.all()
            stats["multi_winners"] = sum(1 for r in rows7 if r[0])
            stats["multi_losers"] = sum(1 for r in rows7 if not r[0])
            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Current-probability winner backfill error: %s", e)

    total_w = (stats["clean_winners"] + stats["mutex_winners"] + stats["threshold_winners"]
               + stats["single_winners"] + stats.get("binary_winners", 0) + stats.get("multi_winners", 0))
    total_l = (stats["clean_losers"] + stats["mutex_losers"] + stats["threshold_losers"]
               + stats["all_losers_set"] + stats["single_losers"]
               + stats.get("binary_losers", 0) + stats.get("multi_losers", 0))
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
                """)
            )
            stats["nulled_zero_snap"] = result.rowcount

            result2 = await session.execute(
                text("""
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
                    SET opening_probability = NULL
                    FROM snap_stats ss
                    WHERE fo.id = ss.outcome_id
                """)
            )
            stats["nulled_no_movement"] = result3.rowcount

            # Pass 4a: outcomes in tournament WINNER markets (50+) with high opening
            result4a = await session.execute(
                text("""
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
                """)
            )

            # Pass 4b: outcomes with very few snapshots AND high opening.
            # These are ask-price corruptions: yes_ask=0.99 stored as opening
            # on illiquid markets. Real predictions have multiple snapshots
            # from repeated polling. "LeBron: 8+ points" at 95% with 20
            # snapshots is legitimate; "Dort: 6+ assists" at 99% with 1
            # snapshot is the ask price.
            result4b = await session.execute(
                text("""
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
                """)
            )
            stats["nulled_ask_price"] = (result4a.rowcount or 0) + (result4b.rowcount or 0)

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error("Null untradeable openings error: %s", e)

    logger.info(
        "Null untradeable openings: %d zero-snap, %d low-snap, %d no-movement, "
        "%d ask-price, %d errors",
        stats["nulled_zero_snap"], stats["nulled_low_snap"],
        stats["nulled_no_movement"], stats.get("nulled_ask_price", 0),
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
        "markets_checked": 0, "winners_set": 0, "losers_set": 0,
        "prices_synced": 0,
        "api_miss": 0, "not_settled": 0, "no_match": 0, "errors": [],
    }

    async with get_task_session() as session:
        # Find stuck markets: either midrange prices (0.05-0.95) OR all-losers
        # (max <= 0.10, meaning the winning outcome's price was never synced).
        stuck = await session.execute(
            text("""
                SELECT fm.id, fm.external_id, fm.group_type,
                       fm.market_metadata->>'polymarket_event_id' AS poly_event_id
                FROM futures_markets fm
                JOIN futures_outcomes fo ON fo.market_id = fm.id
                WHERE fm.source = 'polymarket'
                  AND fm.status = 'resolved'
                GROUP BY fm.id
                HAVING (
                    SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                    AND (
                        MAX(fo.current_probability) BETWEEN 0.05 AND 0.95
                        OR MAX(fo.current_probability) <= 0.10
                    )
                ) OR (
                    BOOL_OR(COALESCE(fo.resolution_source, '') NOT IN ('api_settlement', 'clean_resolution'))
                )
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
                        is_negrisk = row.group_type == "negrisk"

                        # NegRisk parent markets: external_id = event_id.
                        # Must iterate ALL API sub-markets and match each
                        # condition_id against DB outcomes on this market.
                        if is_negrisk or (condition_id == event_id and len(api_markets) > 1):
                            market_resolved = False
                            for m in api_markets:
                                m_cid = str(m.get("conditionId") or m.get("condition_id") or "")
                                if not m_cid:
                                    continue

                                m_prices_raw = m.get("outcomePrices") or m.get("outcome_prices") or []
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
                                    {"price": settlement_price, "mid": row.id, "cid": m_cid},
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
                            .values(is_winner=yes_won, resolution_source="api_settlement")
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
                                .values(is_winner=yes_won, resolution_source="api_settlement")
                            )
                            r2 = await session.execute(
                                update(FuturesOutcome)
                                .where(
                                    FuturesOutcome.market_id == row.id,
                                    FuturesOutcome.external_id == f"{cid}_no",
                                )
                                .values(is_winner=(not yes_won), resolution_source="api_settlement")
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
                min(batch_start + batch_size, len(event_ids)), len(event_ids),
                stats["winners_set"], stats["losers_set"],
                stats["prices_synced"], stats["api_miss"],
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
        stats["markets_checked"], stats["winners_set"], stats["losers_set"],
        stats["prices_synced"],
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

    # Phase 0c: DISABLED — the untradeable filter was nulling opening_probability
    # on outcomes the backfill pipeline is trying to recover, causing calibration
    # to regress every run (bugs #7, #8, #12). One-time cleanup that became an
    # ongoing regression source.
    no_snap_stats = {"nulled_zero_snap": 0, "nulled_low_snap": 0, "nulled_no_movement": 0}

    # Phase 0c-repair: Restore opening_probability from first snapshot for
    # outcomes with null opening but real snapshot data. Uses DISTINCT ON
    # for bulk performance instead of correlated subqueries.
    repair_stats = {"restored": 0, "errors": []}
    try:
        for _ in range(5):
            async with get_task_session() as session:
                r = await session.execute(
                    text("""
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
                    """)
                )
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
                r = await session.execute(
                    text("""
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
                    """)
                )
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
    retro2_stats = {"tagged": 0, "errors": []}
    try:
        for _ in range(3):
            async with get_task_session() as session:
                r = await session.execute(
                    text("""
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
                    """)
                )
                await session.commit()
                if r.rowcount == 0:
                    break
                retro2_stats["tagged"] += r.rowcount
                logger.info("Retro-tagging pass2_guess: %d tagged", r.rowcount)
    except Exception as e:
        retro2_stats["errors"].append(str(e))

    # Phase 0c-bookmaker: Precompute per-bookmaker calibration into Redis.
    # Moved early because it's a one-shot DB query + Redis write.
    bookmaker_stats = await _precompute_bookmaker_calibration()

    # Phase 0d: Pre-compute closing lines on events (no API, uses odds_snapshots)
    closing_stats = await _backfill_closing_lines()

    # Phase 0e: Pre-compute calibration_probability (closing line or settled price)
    cal_price_stats = await _compute_calibration_prices()

    # Phase 0f: Backfill group_id from Polymarket Gamma API (resolved events)
    api_group_stats = await _backfill_polymarket_group_ids_from_api()

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
            r = await session.execute(
                text("""
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
                """)
            )
            dg_makecut_fix_stats["nulled"] = r.rowcount
            await session.commit()
            if r.rowcount > 0:
                logger.info("Golf make_cut fix: nulled %d wrongly-resolved outcomes", r.rowcount)
    except Exception as e:
        dg_makecut_fix_stats["errors"].append(str(e))

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
    golf_matchup_stats = await _resolve_golf_matchups_from_datagolf()

    # Phase 0i: Sync is_winner from settled current_probability for golf.
    # Golf outcomes with current_prob at extremes have correct settlement
    # values, but is_winner was corrupted by the reset. Trust the settlement.
    golf_sync_stats = {"synced": 0, "errors": []}
    try:
        async with get_task_session() as session:
            r = await session.execute(
                text("""
                    UPDATE futures_outcomes fo
                    SET is_winner = (fo.current_probability >= 0.95), resolution_source = 'settlement_sync'
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.source = 'kalshi'
                      AND fm.llm_sport_category = 'golf'
                      AND fm.status = 'resolved'
                      AND fo.current_probability IS NOT NULL
                      AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
                      AND fo.is_winner != (fo.current_probability >= 0.95)
                """)
            )
            golf_sync_stats["synced"] = r.rowcount
            await session.commit()
    except Exception as e:
        golf_sync_stats["errors"].append(str(e))

    # Phase 1a: Kalshi score-based resolution for game markets linked to
    # Events. Resolves moneyline/BTTS/spreads/totals/1H props from actual
    # game scores even when the Kalshi API has purged the market data.
    score_stats = await _resolve_kalshi_from_scores()
    spread_total_stats = await _resolve_kalshi_spread_total_from_scores()
    player_prop_stats = await _resolve_kalshi_player_props_from_boxscore()
    period_prop_stats = await _resolve_kalshi_period_props()

    # Phase 1b: Authoritative API settlement data — run BEFORE probability
    # passes so API results take priority over arbitrary Pass 2 picks.
    kalshi_stats = await _backfill_kalshi_winners(limit=limit, dry_run=dry_run)
    poly_api_stats = await _backfill_polymarket_winners_from_api(limit=5000)

    # Phase 2: Set is_winner from current_probability (all sources, fast)
    # Only handles markets not already resolved by API settlement above.
    prob_stats = await _backfill_from_current_probability()

    return {
        "retro_tagging": retro_stats,
        "retro_guess_tagging": retro2_stats,
        "commence_time_fixes": commence_stats,
        "polymarket_group_id": group_stats,
        "kalshi_group_id": kalshi_group_stats,
        "null_untradeable": no_snap_stats,
        "opening_repair": repair_stats,
        "closing_lines": closing_stats,
        "calibration_prices": cal_price_stats,
        "polymarket_api_group_id": api_group_stats,
        "datagolf_settlement": dg_settlement_stats,
        "datagolf_leaderboard_backfill": dg_leaderboard_stats,
        "datagolf": datagolf_stats,
        "golf_cross_reference": golf_cross_stats,
        "golf_matchup_resolution": golf_matchup_stats,
        "golf_settlement_sync": golf_sync_stats,
        "kalshi_score_resolution": score_stats,
        "kalshi_spread_total_resolution": spread_total_stats,
        "kalshi_player_props": player_prop_stats,
        "kalshi_period_props": period_prop_stats,
        "from_probability": prob_stats,
        "kalshi_api": kalshi_stats,
        "polymarket_api": poly_api_stats,
        "bookmaker_calibration": bookmaker_stats,
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
            result = await session.execute(
                text("""
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
                """)
            )
            rows = result.all()

            buckets = []
            for r in rows:
                buckets.append({
                    "bucket_idx": r.bucket_idx,
                    "source": "odds_api_bookmaker",
                    "category": r.category,
                    "price_moved": None,
                    "n": r.n,
                    "winners": r.winners,
                    "avg_prob": float(r.avg_prob),
                    "sum_prob": float(r.sum_prob),
                    "sum_sq_err": float(r.sum_sq_err),
                })
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
        stats["data_points"], stats["bookmakers"], len(stats["errors"]),
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
    stats = {"reset": 0, "with_commence": 0, "without_commence": 0, "rescued": 0, "errors": []}

    try:
        async with get_task_session() as session:
            stats["reset"] = 0

            # Part A: Event-linked markets — real pre-event closing line
            # Batched at 100K. Pure SQL, no Python memory risk.
            # LATERAL subquery does one index seek per outcome via
            # idx_fos_outcome_captured(outcome_id, captured_at) instead
            # of DISTINCT ON which joins then sorts the full result set.
            # ORDER BY commence_time DESC so recent games are processed first.
            part_a_total = 0
            for _ in range(20):
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
                    """)
                )
                await session.commit()
                part_a_total += result_a.rowcount
                if result_a.rowcount == 0:
                    break
                logger.info("Calibration Part A: batch processed %d (total %d)", result_a.rowcount, part_a_total)
            stats["with_commence"] = part_a_total

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
            reset_a2 = await session.execute(
                text("""
                    UPDATE futures_outcomes fo
                    SET calibration_probability = NULL
                    FROM futures_markets fm
                    WHERE fo.market_id = fm.id
                      AND fm.status = 'resolved'
                      AND fm.event_id IS NULL
                      AND fm.commence_time IS NOT NULL
                      AND fo.calibration_probability IS NOT NULL
                      AND fo.calibration_probability = fo.opening_probability
                      AND fo.opening_probability IS NOT NULL
                """)
            )
            await session.commit()
            stats["reset_a2"] = reset_a2.rowcount
            if reset_a2.rowcount > 0:
                logger.info("Calibration Part A2 reset: %d outcomes", reset_a2.rowcount)

            part_a2_total = 0
            for _ in range(20):
                result_a2 = await session.execute(
                    text("""
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
                    """)
                )
                await session.commit()
                part_a2_total += result_a2.rowcount
                if result_a2.rowcount == 0:
                    break
                logger.info("Calibration Part A2: batch processed %d (total %d)", result_a2.rowcount, part_a2_total)
            stats["with_market_commence"] = part_a2_total

            # Part B: Non-event markets WITHOUT commence_time — settled price
            # or opening fallback. These are non-golf futures (elections,
            # economics, etc.) that have no tournament start date.
            # Batched at 100K. LATERAL subquery for efficient index seeks.
            part_b_total = 0
            for _ in range(20):
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
                    """)
                )
                await session.commit()
                part_b_total += result_b.rowcount
                if result_b.rowcount == 0:
                    break
                logger.info("Calibration Part B: batch processed %d (total %d)", result_b.rowcount, part_b_total)
            stats["without_commence"] = part_b_total

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
                        )
                        UPDATE futures_outcomes fo
                        SET calibration_probability = ls.probability
                        FROM stuck s
                        LEFT JOIN LATERAL (
                            SELECT fos.probability
                            FROM futures_odds_snapshots fos
                            WHERE fos.outcome_id = s.outcome_id
                              AND fos.probability > 0 AND fos.probability < 1
                            ORDER BY fos.captured_at DESC
                            LIMIT 1
                        ) ls ON true
                        WHERE fo.id = s.outcome_id
                          AND ls.probability IS NOT NULL
                          AND ls.probability != s.opening_probability
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
