"""
Prediction market → Event matching task.

Periodically scans futures_markets from Kalshi and Polymarket to:
1. Detect game-level binary markets (moneyline-style outcomes)
2. Match them to Event records by team name + commence_time
3. Auto-create Event records when The Odds API doesn't cover a sport (e.g., Olympics)
4. Write win_prob_snapshots so they appear as trend lines on OddsChart

Runs after Kalshi (:45) and Polymarket (:15) polling to pick up fresh data.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, or_, and_, func, delete
from sqlalchemy.orm import joinedload

from app.tasks.base import get_task_session
from app.utils.prediction_market_matching import (
    is_game_level_market,
    is_kalshi_game_ticker,
    _KALSHI_GAME_TICKER_PREFIXES,
    get_sport_prefix_from_ticker,
    _TICKER_TO_SPORT_PREFIX,
    extract_matchup,
    extract_matchup_with_ticker_fallback,
    extract_teams_from_ticker,
    extract_game_date_from_ticker,
    extract_ticker_fragments,
    _score_fragment_match,
    match_teams_to_event,
    find_moneyline_outcome,
    _fuzzy_team_match,
    _SPORT_CATEGORY_TO_KEY_PREFIX,
    MAX_TIME_DELTA,
    MAX_PAST_GAME_DELTA,
)

logger = logging.getLogger(__name__)


# SQL LIKE patterns for Kalshi game tickers (e.g., "kxnbagame%")
# Used to directly query game-level markets without scanning all markets.
_KALSHI_TICKER_LIKE_PATTERNS = [f"{prefix}%" for prefix in _KALSHI_GAME_TICKER_PREFIXES]


async def _match_prediction_markets(limit: int = 500):
    """
    Match game-level prediction markets to events and write win_prob_snapshots.

    Two phases:
    1. Link: Find unlinked game-level markets and match to events (set event_id)
    2. Snapshot: For all linked markets, write current probability to win_prob_snapshots
    """
    from app.models.models import (
        FuturesMarket, FuturesOutcome, Event, Sport, WinProbSnapshot,
    )
    from app.tasks.snapshots import _create_or_update_win_prob_snapshot

    stats = {
        "markets_scanned": 0,
        "newly_linked": 0,
        "snapshots_written": 0,
        "snapshots_deduped": 0,
        "orphaned_snapshots_deleted": 0,
        "errors": [],
        # Funnel stats: track where markets drop off
        "funnel": {
            "total_unlinked": 0,
            "not_game_level": 0,
            "no_matchup_extracted": 0,
            "game_level_detected": 0,
            "no_event_found": 0,
            "linked": 0,
            "sample_game_level_no_event": [],  # Sample of game-level markets that couldn't match
            "sample_not_game_level": [],  # Sample of markets that weren't detected as game-level
        },
    }

    now = datetime.now(timezone.utc)
    # Track newly linked Polymarket markets for price history backfill
    polymarket_backfill_queue = []

    async with get_task_session() as session:
        # ── Phase 1: Link unlinked game-level markets ────────────────────
        #
        # Two-pass strategy:
        # Pass 1 (targeted): Directly query Kalshi markets with game ticker
        #   patterns (KXNBAGAME%, KXNFLGAME%, etc.) — guaranteed game-level,
        #   no limit needed since there are relatively few.
        # Pass 2 (general): Scan remaining unlinked markets with a limit,
        #   using name-based pattern matching to detect Polymarket game
        #   markets and any Kalshi markets with non-standard tickers.

        # ── Pass 1: Targeted Kalshi game ticker scan (no limit) ──────────
        ticker_conditions = [
            func.lower(FuturesMarket.external_id).like(pattern)
            for pattern in _KALSHI_TICKER_LIKE_PATTERNS
        ]
        ticker_result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source == "kalshi",
                FuturesMarket.event_id.is_(None),
                or_(*ticker_conditions),
            )
        )
        ticker_markets = ticker_result.scalars().all()
        stats["funnel"]["ticker_scan_count"] = len(ticker_markets)

        # Track IDs already processed so Pass 2 doesn't re-scan
        processed_ids = set()

        for market in ticker_markets:
            processed_ids.add(market.id)
            stats["markets_scanned"] += 1
            stats["funnel"]["game_level_detected"] += 1

            # Try name-based extraction first, then ticker abbreviation parsing
            matchup = extract_matchup_with_ticker_fallback(
                market.name, external_id=market.external_id,
            )

            # Extract game date from ticker — Kalshi commence_time is the
            # market RESOLUTION date (often weeks after the game), not the
            # actual game date. The ticker embeds the real date.
            ticker_game_date = extract_game_date_from_ticker(market.external_id)

            if matchup:
                # Team-name based matching (either from name or ticker)
                matched_event = await _find_matching_event(
                    session, matchup, market, now,
                    game_date_override=ticker_game_date,
                )
                if matched_event and matchup.format_type == "ticker_parsed":
                    stats["funnel"].setdefault("ticker_abbrev_linked", 0)
                    stats["funnel"]["ticker_abbrev_linked"] += 1
            else:
                # Last resort: sport + time matching for truly unrecognizable markets
                matched_event = await _find_event_by_sport_and_time(
                    session, market, now,
                    game_date_override=ticker_game_date,
                )
                if matched_event:
                    stats["funnel"].setdefault("sport_time_fallback_linked", 0)
                    stats["funnel"]["sport_time_fallback_linked"] += 1

            if matched_event:
                market.event_id = matched_event["event_id"]
                stats["newly_linked"] += 1
                stats["funnel"]["linked"] += 1
                logger.info(
                    "Linked %s market '%s' → event %d (%s vs %s) [ticker=%s]",
                    market.source, market.name, matched_event["event_id"],
                    matched_event["home_team"], matched_event["away_team"],
                    market.external_id,
                )
            else:
                # No existing event found — try auto-creating one.
                # This handles sports The Odds API doesn't cover (e.g., Olympics).
                if matchup and matchup.team_b:
                    auto_event = await _create_event_from_prediction_market(
                        session, matchup, market, now,
                    )
                    if auto_event:
                        market.event_id = auto_event["event_id"]
                        stats["newly_linked"] += 1
                        stats["funnel"]["linked"] += 1
                        stats["funnel"].setdefault("auto_created_events", 0)
                        stats["funnel"]["auto_created_events"] += 1
                    else:
                        if not matchup:
                            stats["funnel"]["no_matchup_extracted"] += 1
                        stats["funnel"]["no_event_found"] += 1
                        if len(stats["funnel"]["sample_game_level_no_event"]) < 10:
                            stats["funnel"]["sample_game_level_no_event"].append(
                                {
                                    "source": market.source,
                                    "name": market.name,
                                    "team_a": matchup.team_a if matchup else None,
                                    "team_b": matchup.team_b if matchup else None,
                                    "commence_time": market.commence_time.isoformat() if market.commence_time else None,
                                    "external_id": market.external_id,
                                }
                            )
                else:
                    if not matchup:
                        stats["funnel"]["no_matchup_extracted"] += 1
                    stats["funnel"]["no_event_found"] += 1
                    if len(stats["funnel"]["sample_game_level_no_event"]) < 10:
                        stats["funnel"]["sample_game_level_no_event"].append(
                            {
                                "source": market.source,
                                "name": market.name,
                                "team_a": matchup.team_a if matchup else None,
                                "team_b": matchup.team_b if matchup else None,
                                "commence_time": market.commence_time.isoformat() if market.commence_time else None,
                                "external_id": market.external_id,
                            }
                        )

        # ── Pass 2: General scan for non-ticker game markets ─────────────
        # Catches Polymarket game markets and any Kalshi markets with
        # non-standard tickers (e.g., esports like KXLOLGAME).
        #
        # Two sub-queries to maximize coverage of game-level markets:
        # 2a: Markets with matchup name patterns (contains "vs." / "vs ")
        #     — these are almost certainly game-level. Full budget.
        # 2b: Remaining markets (catches unusual naming).
        #     — small budget for edge cases.
        #
        # Without this split, 13,000+ Polymarket markets (politics, crypto,
        # weather, etc.) compete for 500 scan slots and crowd out game
        # markets like "Celtics vs. Lakers".

        _matchup_base_where = [
            FuturesMarket.source.in_(["kalshi", "polymarket"]),
            FuturesMarket.event_id.is_(None),
            FuturesMarket.status == "open",
        ]
        _matchup_name_filter = or_(
            FuturesMarket.name.ilike("% vs.%"),
            FuturesMarket.name.ilike("% vs %"),
            FuturesMarket.name.ilike("% – %"),  # en-dash matchups
        )

        # Pass 2a: matchup-patterned markets (prioritized)
        matchup_result = await session.execute(
            select(FuturesMarket)
            .where(*_matchup_base_where, _matchup_name_filter)
            .order_by(FuturesMarket.updated_at.desc())
            .limit(limit)
        )
        matchup_markets = matchup_result.scalars().all()

        # Pass 2b: remaining non-matchup markets (edge cases, small budget)
        remaining_budget = max(0, limit // 5)  # 20% of budget for edge cases
        remaining_markets = []
        if remaining_budget > 0:
            remaining_result = await session.execute(
                select(FuturesMarket)
                .where(*_matchup_base_where, ~_matchup_name_filter)
                .order_by(FuturesMarket.updated_at.desc())
                .limit(remaining_budget)
            )
            remaining_markets = remaining_result.scalars().all()

        unlinked_markets = matchup_markets + remaining_markets
        stats["funnel"]["total_unlinked"] = len(unlinked_markets) + len(ticker_markets)
        stats["funnel"]["general_scan_count"] = len(unlinked_markets)
        stats["funnel"]["matchup_scan_count"] = len(matchup_markets)
        stats["funnel"]["remaining_scan_count"] = len(remaining_markets)

        for market in unlinked_markets:
            # Skip markets already processed in Pass 1
            if market.id in processed_ids:
                continue

            stats["markets_scanned"] += 1

            # Check if market name looks like a game-level matchup.
            # Note: we do NOT gate on outcome count here. Polymarket bundles
            # moneyline + spread + totals under one game event, so a game
            # like "Celtics vs. Warriors" can have 3-5+ outcomes. The name
            # pattern is the reliable signal, not outcome count.
            #
            # For Kalshi, we also check the external_id (event ticker) for
            # reliable game-level detection: "KXNBAGAME-..." is always a game.
            if not is_game_level_market(
                market.name, market.category,
                external_id=market.external_id,
            ):
                stats["funnel"]["not_game_level"] += 1
                if len(stats["funnel"]["sample_not_game_level"]) < 10:
                    stats["funnel"]["sample_not_game_level"].append(
                        {"source": market.source, "name": market.name,
                         "external_id": market.external_id}
                    )
                continue

            # Extract matchup info (with ticker fallback for Kalshi)
            matchup = extract_matchup_with_ticker_fallback(
                market.name, external_id=market.external_id,
            )
            if not matchup:
                stats["funnel"]["no_matchup_extracted"] += 1
                continue

            stats["funnel"]["game_level_detected"] += 1

            # For Kalshi markets in Pass 2, extract game date from ticker
            # (commence_time is resolution date, not game date)
            pass2_game_date = extract_game_date_from_ticker(market.external_id) if market.source == "kalshi" else None

            # Find candidate events by team name matching
            # Search for events where either team matches either market team
            matched_event = await _find_matching_event(
                session, matchup, market, now,
                game_date_override=pass2_game_date,
            )

            if matched_event:
                market.event_id = matched_event["event_id"]
                stats["newly_linked"] += 1
                stats["funnel"]["linked"] += 1
                logger.info(
                    "Linked %s market '%s' → event %d (%s vs %s) [yes_is_home=%s]",
                    market.source, market.name, matched_event["event_id"],
                    matched_event["home_team"], matched_event["away_team"],
                    matched_event["yes_is_home"],
                )
                # Queue Polymarket markets for price history backfill
                if market.source == "polymarket":
                    polymarket_backfill_queue.append(
                        (market.id, matched_event["event_id"])
                    )
            else:
                # No existing event — try auto-creating for sports not in The Odds API
                if matchup.team_b:
                    auto_event = await _create_event_from_prediction_market(
                        session, matchup, market, now,
                    )
                    if auto_event:
                        market.event_id = auto_event["event_id"]
                        stats["newly_linked"] += 1
                        stats["funnel"]["linked"] += 1
                        stats["funnel"].setdefault("auto_created_events", 0)
                        stats["funnel"]["auto_created_events"] += 1
                        if market.source == "polymarket":
                            polymarket_backfill_queue.append(
                                (market.id, auto_event["event_id"])
                            )
                    else:
                        stats["funnel"]["no_event_found"] += 1
                        if len(stats["funnel"]["sample_game_level_no_event"]) < 10:
                            stats["funnel"]["sample_game_level_no_event"].append(
                                {
                                    "source": market.source,
                                    "name": market.name,
                                    "team_a": matchup.team_a,
                                    "team_b": matchup.team_b,
                                    "commence_time": market.commence_time.isoformat() if market.commence_time else None,
                                    "external_id": market.external_id,
                                }
                            )
                else:
                    stats["funnel"]["no_event_found"] += 1
                    if len(stats["funnel"]["sample_game_level_no_event"]) < 10:
                        stats["funnel"]["sample_game_level_no_event"].append(
                            {
                                "source": market.source,
                                "name": market.name,
                                "team_a": matchup.team_a,
                                "team_b": matchup.team_b,
                                "commence_time": market.commence_time.isoformat() if market.commence_time else None,
                                "external_id": market.external_id,
                            }
                        )

        # ── Phase 1.5: Fix stale and mislinked markets ────────────────────
        # Scan ALL linked markets for two problems:
        # (a) Stale: linked to completed/closed events — try to find the next game
        # (b) Mislinked: teams don't both match the linked event (e.g.,
        #     "Pistons vs. Bulls" linked to "Georgia Southern vs South Florida Bulls"
        #     because "Bulls" substring-matched but "Pistons" didn't)
        stats["funnel"].setdefault("stale_relinked", 0)
        stats["funnel"].setdefault("mislink_fixed", 0)

        all_linked_result = await session.execute(
            select(FuturesMarket, Event)
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.event_id.isnot(None),
            )
            .limit(1000)
        )
        all_linked_rows = all_linked_result.all()

        for market, linked_event in all_linked_rows:
            try:
                if not is_game_level_market(
                    market.name, market.category,
                    external_id=market.external_id,
                ):
                    continue

                matchup = extract_matchup_with_ticker_fallback(
                    market.name, external_id=market.external_id,
                )
                if not matchup or not matchup.team_b:
                    continue

                # Verify both teams actually match the linked event
                a_matches = (
                    _fuzzy_team_match(matchup.team_a, linked_event.home_team_name)
                    or _fuzzy_team_match(matchup.team_a, linked_event.away_team_name)
                )
                b_matches = (
                    _fuzzy_team_match(matchup.team_b, linked_event.home_team_name)
                    or _fuzzy_team_match(matchup.team_b, linked_event.away_team_name)
                )
                teams_match = a_matches and b_matches
                is_finished = linked_event.status in ("completed", "closed")

                # Skip if teams match AND event is still active — correctly linked
                if teams_match and not is_finished:
                    continue

                # Need to re-link: either teams don't match or event is finished
                ticker_game_date = extract_game_date_from_ticker(market.external_id) if market.source == "kalshi" else None

                better_match = await _find_matching_event(
                    session, matchup, market, now,
                    game_date_override=ticker_game_date,
                )

                if better_match and better_match["event_id"] != linked_event.id:
                    logger.info(
                        "Re-linking %s '%s' from %s event %d (%s vs %s) → event %d (%s vs %s)",
                        market.source, market.name,
                        "mislinked" if not teams_match else "completed",
                        linked_event.id, linked_event.home_team_name, linked_event.away_team_name,
                        better_match["event_id"],
                        better_match["home_team"], better_match["away_team"],
                    )
                    # Delete orphaned snapshots from the old (wrong) event
                    if not teams_match:
                        del_result = await session.execute(
                            delete(WinProbSnapshot).where(
                                WinProbSnapshot.event_id == linked_event.id,
                                WinProbSnapshot.source == market.source,
                            )
                        )
                        stats["orphaned_snapshots_deleted"] += del_result.rowcount
                    market.event_id = better_match["event_id"]
                    if not teams_match:
                        stats["funnel"]["mislink_fixed"] += 1
                    else:
                        stats["funnel"]["stale_relinked"] += 1
                elif not teams_match:
                    # Teams don't match and no better event found — unlink to prevent wrong data
                    logger.info(
                        "Unlinking %s '%s' from mismatched event %d (%s vs %s) — no better match",
                        market.source, market.name, linked_event.id,
                        linked_event.home_team_name, linked_event.away_team_name,
                    )
                    # Delete orphaned snapshots from the mislinked event
                    del_result = await session.execute(
                        delete(WinProbSnapshot).where(
                            WinProbSnapshot.event_id == linked_event.id,
                            WinProbSnapshot.source == market.source,
                        )
                    )
                    stats["orphaned_snapshots_deleted"] += del_result.rowcount
                    market.event_id = None
                    stats["funnel"]["mislink_fixed"] += 1
            except Exception as e:
                logger.debug("Error checking link for market %d: %s", market.id, e)
                continue

        await session.commit()

        # ── Phase 2: Write win_prob_snapshots for all linked markets ─────

        # Find all linked prediction markets (including newly linked ones)
        # Include "open" and recently-resolved markets so we capture final prices
        linked_result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.event_id.isnot(None),
            )
        )
        linked_markets = linked_result.scalars().all()

        for market in linked_markets:
            try:
                # Load the event to determine home/away mapping
                event_result = await session.execute(
                    select(Event).where(Event.id == market.event_id)
                )
                event = event_result.scalar_one_or_none()
                if not event:
                    continue

                # Skip completed events that finished long ago (> 6 hours)
                # to avoid writing stale snapshots
                if event.status in ("completed", "closed"):
                    if event.commence_time:
                        hours_since = (now - event.commence_time).total_seconds() / 3600
                        if hours_since > 12:
                            continue

                # Re-extract matchup to determine team mapping
                # Uses ticker fallback for generic-named Kalshi markets
                matchup = extract_matchup_with_ticker_fallback(
                    market.name, external_id=market.external_id,
                )
                if not matchup:
                    continue

                # Get ALL outcomes for this market (game events may have
                # moneyline + spread + totals bundled together)
                outcome_result = await session.execute(
                    select(FuturesOutcome)
                    .where(FuturesOutcome.market_id == market.id)
                    .order_by(FuturesOutcome.rank)
                )
                all_outcomes = outcome_result.scalars().all()
                if not all_outcomes:
                    continue

                # Find the moneyline outcome by matching team names
                ml_result = find_moneyline_outcome(
                    all_outcomes, matchup,
                    event.home_team_name, event.away_team_name,
                )
                if not ml_result:
                    continue

                outcome, yes_is_home = ml_result
                yes_prob = float(outcome.current_probability)

                # Convert prediction market probability to home/away
                if yes_is_home:
                    home_prob = yes_prob
                else:
                    home_prob = 1.0 - yes_prob
                away_prob = 1.0 - home_prob

                # Write to win_prob_snapshots with deduplication
                source_key = market.source  # "kalshi" or "polymarket"
                snapshot, is_new = await _create_or_update_win_prob_snapshot(
                    session,
                    event_id=market.event_id,
                    source=source_key,
                    home_win_probability=round(home_prob, 4),
                    away_win_probability=round(away_prob, 4),
                    game_state={
                        "market_name": market.name,
                        "market_id": market.id,
                        "outcome_name": outcome.name,
                        "yes_probability": yes_prob,
                        "yes_bid": float(outcome.current_yes_bid) if outcome.current_yes_bid else None,
                        "yes_ask": float(outcome.current_yes_ask) if outcome.current_yes_ask else None,
                    },
                )

                if is_new:
                    session.add(snapshot)
                    stats["snapshots_written"] += 1
                else:
                    stats["snapshots_deduped"] += 1

            except Exception as e:
                stats["errors"].append(f"market {market.id}: {str(e)}")
                continue

        await session.commit()

    # ── Phase 3: Backfill Polymarket price history for newly linked markets ──
    # Runs outside the main DB session to avoid holding transactions open
    # during API calls. Each backfill is independent and idempotent.
    if polymarket_backfill_queue:
        stats["funnel"]["polymarket_backfills_queued"] = len(polymarket_backfill_queue)
        for market_id, event_id in polymarket_backfill_queue:
            try:
                backfill_stats = await _backfill_polymarket_win_prob_history(
                    market_id, event_id,
                )
                stats["funnel"].setdefault("polymarket_backfill_snapshots", 0)
                stats["funnel"]["polymarket_backfill_snapshots"] += (
                    backfill_stats.get("snapshots_created", 0)
                )
            except Exception as e:
                stats["errors"].append(f"backfill_{market_id}: {str(e)[:100]}")

    logger.info(
        "Prediction market matching: scanned=%d, linked=%d, "
        "snapshots_written=%d, deduped=%d, errors=%d",
        stats["markets_scanned"], stats["newly_linked"],
        stats["snapshots_written"], stats["snapshots_deduped"],
        len(stats["errors"]),
    )
    return stats


async def _find_matching_event(session, matchup, market, now, game_date_override=None):
    """
    Find an Event that matches the given matchup and market.

    Two-pass strategy:
    1. Time-windowed search: ±48h around game date (from ticker or market.commence_time)
    2. Broad fallback: If no time-windowed match AND we have both team names,
       search scheduled/live events without time restriction. This handles
       Polymarket markets (commence_time = market creation date, not game date)
       and Kalshi markets without parseable ticker dates.

    Args:
        game_date_override: If provided, use this as the reference time instead
            of market.commence_time. Critical for Kalshi game markets where
            commence_time is the market resolution date (weeks after the game),
            not the actual game date.
    """
    from app.models.models import Event, Sport

    # Build team name search patterns
    teams_to_search = [matchup.team_a]
    if matchup.team_b:
        teams_to_search.append(matchup.team_b)

    # Create ILIKE conditions for team names
    ilike_conditions = []
    for team in teams_to_search:
        pattern = f"%{_escape_like(team)}%"
        ilike_conditions.append(Event.home_team_name.ilike(pattern))
        ilike_conditions.append(Event.away_team_name.ilike(pattern))

    # Also restrict: don't match events that started more than 6 hours ago
    # (unless they're still live)
    past_cutoff = now - MAX_PAST_GAME_DELTA

    # ── Pass 1: Time-windowed search ──────────────────────────────────
    reference_time = game_date_override or market.commence_time or now
    time_start = reference_time - MAX_TIME_DELTA
    time_end = reference_time + MAX_TIME_DELTA

    event_result = await session.execute(
        select(Event)
        .options(joinedload(Event.sport))
        .where(
            or_(*ilike_conditions),
            Event.commence_time.between(time_start, time_end),
            or_(
                Event.status.in_(["scheduled", "live"]),
                Event.commence_time >= past_cutoff,
            ),
        )
        .order_by(Event.commence_time)
        .limit(20)
    )
    candidates = event_result.scalars().unique().all()

    result = _score_candidates(candidates, matchup, market, now, game_date_override)
    if result:
        return result

    # ── Pass 2: Broad fallback (no time window) ──────────────────────
    # Only when we have BOTH team names (strong signal) and Pass 1 found nothing.
    # This handles Polymarket (commence_time = market creation date) and
    # Kalshi markets without parseable ticker dates.
    # Restrict to scheduled/live events within ±14 days of now to avoid
    # matching ancient or far-future events.
    if matchup.team_b:
        broad_start = now - timedelta(days=1)  # Allow games that started today
        broad_end = now + timedelta(days=14)   # Up to 2 weeks ahead

        event_result = await session.execute(
            select(Event)
            .options(joinedload(Event.sport))
            .where(
                or_(*ilike_conditions),
                Event.commence_time.between(broad_start, broad_end),
                Event.status.in_(["scheduled", "live"]),
            )
            .order_by(Event.commence_time)
            .limit(20)
        )
        broad_candidates = event_result.scalars().unique().all()

        result = _score_candidates(broad_candidates, matchup, market, now, game_date_override)
        if result:
            logger.info(
                "Broad fallback matched %s '%s' → event %d (time window bypass)",
                market.source, market.name, result["event_id"],
            )
            return result

    return None


def _score_candidates(candidates, matchup, market, now, game_date_override=None):
    """Score candidate events and return the best match (or None)."""
    if not candidates:
        return None

    best_match = None
    best_score = -1

    for event in candidates:
        # When we have both team names, REQUIRE both to fuzzy-match the event.
        # Prevents false positives like "Thunder vs. Pistons" matching
        # "Bulls vs. Pistons" (Thunder ≠ Bulls), or "Pistons vs. Bulls"
        # matching "Georgia Southern Eagles vs South Florida Bulls"
        # (Pistons ≠ Georgia Southern Eagles).
        if matchup.team_b:
            a_matches = (
                _fuzzy_team_match(matchup.team_a, event.home_team_name)
                or _fuzzy_team_match(matchup.team_a, event.away_team_name)
            )
            b_matches = (
                _fuzzy_team_match(matchup.team_b, event.home_team_name)
                or _fuzzy_team_match(matchup.team_b, event.away_team_name)
            )
            if not (a_matches and b_matches):
                continue

        # Check team name matching (determine yes/no home/away mapping)
        team_match = match_teams_to_event(
            matchup,
            event.home_team_name,
            event.away_team_name,
        )
        if not team_match:
            continue

        # For "Will X win?" with only one team, verify the market team
        # actually matches an event team
        if matchup.format_type == "will_win" and not matchup.team_b:
            if not (
                _fuzzy_team_match(matchup.team_a, event.home_team_name)
                or _fuzzy_team_match(matchup.team_a, event.away_team_name)
            ):
                continue

        # Score: prefer closer to now + live games
        score = 0

        # Time proximity to now (max 10 points, closer = higher)
        ref = game_date_override or now
        if event.commence_time:
            delta_hours = abs(
                (event.commence_time - ref).total_seconds()
            ) / 3600
            score += max(0, 10 - delta_hours / 4)  # Gradual decay over ~40h

        # Live games get a bonus
        if event.status == "live":
            score += 5
        elif event.status == "scheduled":
            score += 3

        # Both teams verified matching (gate above ensures this when team_b exists)
        if matchup.team_b:
            score += 10

        # Sport match bonus: prefer events in the same sport as the market.
        # Uses ticker-based sport prefix (most specific, Kalshi only) first,
        # then falls back to llm_sport_category (both Kalshi and Polymarket).
        sport_prefix = get_sport_prefix_from_ticker(market.external_id) if market.external_id else None
        if not sport_prefix and market.llm_sport_category:
            sport_prefix = _SPORT_CATEGORY_TO_KEY_PREFIX.get(market.llm_sport_category)
        if sport_prefix and event.sport and event.sport.key:
            if event.sport.key.startswith(sport_prefix):
                score += 5  # Same sport — prefer over cross-sport matches

        if score > best_score:
            best_score = score
            best_match = {
                "event_id": event.id,
                "home_team": event.home_team_name,
                "away_team": event.away_team_name,
                "yes_is_home": team_match["yes_is_home"],
                "score": score,
            }

    return best_match


async def _find_event_by_sport_and_time(session, market, now, game_date_override=None):
    """
    Fallback matching for ticker-detected markets with generic names.

    When extract_matchup() fails (e.g., market name is "Professional Basketball
    Game"), we use the Kalshi ticker to determine the sport and search for
    events by sport_key + commence_time proximity.

    Returns a match if EXACTLY ONE event matches (unambiguous), or uses
    ticker fragment matching to disambiguate when multiple candidates exist
    (critical for NCAAB/NCAAF where dozens of games happen per day).

    Returns the same dict format as _find_matching_event, with
    yes_is_home=True as default (will be corrected if outcome names
    match team names in Phase 2).
    """
    from app.models.models import Event, Sport

    # Determine sport from ticker
    sport_prefix = get_sport_prefix_from_ticker(market.external_id)
    if not sport_prefix:
        return None

    # Use game_date_override (from ticker) if available — Kalshi commence_time
    # is the market RESOLUTION date (often weeks after the game), not the
    # actual game date.
    # Tighten to ±3h when we have a ticker game date (more precise)
    reference_time = game_date_override or market.commence_time
    if not reference_time:
        return None

    window_hours = 3 if game_date_override else 6
    time_start = reference_time - timedelta(hours=window_hours)
    time_end = reference_time + timedelta(hours=window_hours)

    # Query events by sport and time
    # Event has sport_id (FK), Sport has key (e.g., "basketball_nba")
    event_result = await session.execute(
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .where(
            Sport.key.like(f"{sport_prefix}%"),
            Event.commence_time.between(time_start, time_end),
        )
        .order_by(Event.commence_time)
        .limit(20)
    )
    candidates = event_result.scalars().all()

    if len(candidates) == 1:
        # Unambiguous match — exactly one event in that sport + time window
        event = candidates[0]
        logger.info(
            "Sport+time fallback matched %s '%s' → event %d (%s vs %s)",
            market.external_id, market.name, event.id,
            event.home_team_name, event.away_team_name,
        )
        return {
            "event_id": event.id,
            "home_team": event.home_team_name,
            "away_team": event.away_team_name,
            # Default to True — Phase 2 will determine correct mapping
            # from outcome names or bid/ask data
            "yes_is_home": True,
        }

    if len(candidates) > 1:
        # Try ticker fragment matching to disambiguate
        fragments = extract_ticker_fragments(market.external_id)
        if fragments:
            abbrev_a, abbrev_b, _ = fragments
            best_event = None
            best_score = 0
            for event in candidates:
                score = _score_fragment_match(
                    abbrev_a, abbrev_b,
                    event.home_team_name, event.away_team_name,
                )
                if score > best_score:
                    best_score = score
                    best_event = event
            if best_score >= 2 and best_event:
                logger.info(
                    "Fragment-matched %s → event %d (%s vs %s) [fragments=%s/%s, score=%d]",
                    market.external_id, best_event.id,
                    best_event.home_team_name, best_event.away_team_name,
                    abbrev_a, abbrev_b, best_score,
                )
                return {
                    "event_id": best_event.id,
                    "home_team": best_event.home_team_name,
                    "away_team": best_event.away_team_name,
                    "yes_is_home": True,
                }

        logger.debug(
            "Sport+time fallback found %d candidates for %s (ambiguous, skipping)",
            len(candidates), market.external_id,
        )

    return None


def _escape_like(s: str) -> str:
    """Escape special characters for ILIKE patterns."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# =============================================================================
# Auto-create Events from Prediction Markets
# =============================================================================

# Sport key → human-readable name for auto-created sports
_SPORT_KEY_NAMES: dict[str, tuple[str, str]] = {
    "icehockey_olympics": ("Ice Hockey - Olympics", "Ice Hockey"),
    "basketball_olympics": ("Basketball - Olympics", "Basketball"),
    "soccer_olympics": ("Soccer - Olympics", "Soccer"),
    "fieldhockey_olympics": ("Field Hockey - Olympics", "Field Hockey"),
    "curling_olympics": ("Curling - Olympics", "Curling"),
}


async def _create_event_from_prediction_market(session, matchup, market, now):
    """
    Auto-create an Event when a game-level prediction market has no matching Event.

    This handles sports that The Odds API doesn't cover (e.g., Olympics).
    The prediction market itself becomes the primary data source for the event.

    Returns the same dict format as _find_matching_event, or None if creation fails.
    """
    from app.models.models import Event, Sport, Team
    from app.utils.prediction_market_matching import (
        match_teams_to_event, _strip_sport_name_prefix, _strip_championship_suffix,
    )

    if not matchup or not matchup.team_a:
        return None

    # Clean team names: strip sport name prefixes ("Ice Hockey USA" → "USA")
    # and championship suffixes that may leak through ("Canada Medal" → "Canada")
    team_a = _strip_championship_suffix(_strip_sport_name_prefix(matchup.team_a.strip())).strip()
    team_b = _strip_championship_suffix(_strip_sport_name_prefix((matchup.team_b or "").strip())).strip()
    if not team_a or not team_b:
        return None

    # Determine sport key from ticker or category
    sport_key = get_sport_prefix_from_ticker(market.external_id) if market.external_id else None
    if not sport_key and market.llm_sport_category:
        cat_prefix = _SPORT_CATEGORY_TO_KEY_PREFIX.get(market.llm_sport_category)
        if cat_prefix:
            sport_key = f"{cat_prefix}_other"

    if not sport_key:
        logger.debug(
            "Cannot auto-create event for '%s' — no sport key determinable",
            market.name,
        )
        return None

    # Check if we already have an event with these teams (avoid duplicates)
    pattern_a = f"%{_escape_like(team_a)}%"
    pattern_b = f"%{_escape_like(team_b)}%"
    existing_result = await session.execute(
        select(Event).where(
            or_(
                and_(
                    Event.home_team_name.ilike(pattern_a),
                    Event.away_team_name.ilike(pattern_b),
                ),
                and_(
                    Event.home_team_name.ilike(pattern_b),
                    Event.away_team_name.ilike(pattern_a),
                ),
            ),
            Event.status.in_(["scheduled", "live"]),
        ).limit(1)
    )
    if existing_result.scalar_one_or_none():
        logger.debug("Event already exists for '%s vs %s', skipping auto-create", team_a, team_b)
        return None

    # Get or create Sport record
    sport_result = await session.execute(
        select(Sport).where(Sport.key == sport_key)
    )
    sport = sport_result.scalar_one_or_none()
    if not sport:
        sport_info = _SPORT_KEY_NAMES.get(sport_key, (sport_key, sport_key.split("_")[0].title()))
        sport = Sport(
            key=sport_key,
            name=sport_info[0],
            group=sport_info[1],
            active=True,
        )
        session.add(sport)
        await session.flush()  # Get the ID

    # Determine commence_time: use market's commence_time if reasonable,
    # otherwise use now (the market is probably live)
    commence_time = market.commence_time
    if not commence_time or abs((commence_time - now).total_seconds()) > 86400 * 30:
        # commence_time is missing or >30 days away (likely resolution date) — use now
        commence_time = now

    # Determine status from commence_time, not market status.
    # Prediction markets are "open" for trading weeks before game start,
    # so market.status is not a reliable indicator of whether the game is live.
    status = "live" if commence_time <= now else "scheduled"

    # Create a unique external_id from the prediction market
    external_id = f"pm_{market.source}_{market.external_id}"

    # Create the Event
    event = Event(
        sport_id=sport.id,
        external_id=external_id,
        home_team_name=team_a,
        away_team_name=team_b,
        commence_time=commence_time,
        status=status,
    )
    session.add(event)
    await session.flush()  # Get the event ID

    # Determine yes_is_home mapping
    team_match = match_teams_to_event(matchup, team_a, team_b)
    yes_is_home = team_match["yes_is_home"] if team_match else True

    logger.info(
        "Auto-created event %d for %s market '%s': %s vs %s [sport=%s, status=%s]",
        event.id, market.source, market.name,
        team_a, team_b, sport_key, status,
    )

    return {
        "event_id": event.id,
        "home_team": team_a,
        "away_team": team_b,
        "yes_is_home": yes_is_home,
        "auto_created": True,
    }


# =============================================================================
# Live Game Price Polling
# =============================================================================

async def _poll_live_prediction_market_prices():
    """
    Fast-poll current prices for prediction markets linked to LIVE events.

    Unlike the full Kalshi/Polymarket polling tasks (which run hourly and scan
    the entire catalog), this task is targeted: it only fetches prices for
    markets already linked to events that are currently live. This enables
    2-minute polling frequency without hitting rate limits.

    For Kalshi: Fetches market data via the /markets endpoint filtered by
    event_ticker to get fresh yes_bid/yes_ask.

    For Polymarket: Fetches event data from the Gamma API to get current
    outcomePrices (one call per event).

    After updating FuturesOutcome.current_probability, writes win_prob_snapshots
    so the OddsChart trend line updates in near-real-time.
    """
    import asyncio
    import json

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.models import (
        FuturesMarket, FuturesOutcome, Event, WinProbSnapshot,
    )
    from app.tasks.snapshots import _create_or_update_win_prob_snapshot
    from app.utils.odds_math import probability_to_american

    stats = {
        "live_events": 0,
        "linked_markets": 0,
        "kalshi_fetched": 0,
        "polymarket_fetched": 0,
        "outcomes_updated": 0,
        "snapshots_written": 0,
        "snapshots_deduped": 0,
        "errors": [],
    }

    now = datetime.now(timezone.utc)

    async with get_task_session() as session:
        # Find all linked prediction markets where the event is currently live
        result = await session.execute(
            select(FuturesMarket, Event)
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.event_id.isnot(None),
                Event.status == "live",
            )
        )
        rows = result.all()

        if not rows:
            logger.debug("No live-linked prediction markets to poll")
            return stats

        live_event_ids = set()
        kalshi_markets = []
        polymarket_markets = []

        for market, event in rows:
            live_event_ids.add(event.id)
            if market.source == "kalshi":
                kalshi_markets.append((market, event))
            else:
                polymarket_markets.append((market, event))

        stats["live_events"] = len(live_event_ids)
        stats["linked_markets"] = len(rows)

        # ── Fetch Kalshi prices ────────────────────────────────────────
        if kalshi_markets:
            from app.services.kalshi_api import KalshiAPIService
            service = KalshiAPIService()
            try:
                for market, event in kalshi_markets:
                    try:
                        # Kalshi external_id is the event ticker
                        markets_data, _ = await service.get_markets(
                            event_ticker=market.external_id,
                            status=None,  # Get all statuses
                            limit=10,
                        )
                        stats["kalshi_fetched"] += 1

                        # Update outcomes with fresh prices
                        for mkt_data in markets_data:
                            yes_bid = mkt_data.get("yes_bid")
                            yes_ask = mkt_data.get("yes_ask")
                            last_price = mkt_data.get("last_price")

                            # Kalshi prices are in cents (0-100)
                            if yes_bid is not None:
                                yes_bid = yes_bid / 100.0
                            if yes_ask is not None:
                                yes_ask = yes_ask / 100.0
                            if last_price is not None:
                                last_price = last_price / 100.0

                            # Prefer last_price (actual traded price) over
                            # bid/ask midpoint. The midpoint oscillates wildly
                            # when the spread widens/narrows on illiquid markets,
                            # creating a jagged chart line that doesn't reflect
                            # real probability changes.
                            if last_price is not None and 0 < last_price < 1:
                                prob = last_price
                            elif yes_bid is not None and yes_ask is not None:
                                prob = (yes_bid + yes_ask) / 2
                            else:
                                continue

                            if prob <= 0 or prob >= 1:
                                continue

                            # Find matching outcome by ticker
                            ticker = mkt_data.get("ticker", "")
                            outcome_result = await session.execute(
                                select(FuturesOutcome)
                                .where(
                                    FuturesOutcome.market_id == market.id,
                                    FuturesOutcome.external_id == ticker,
                                )
                            )
                            outcome = outcome_result.scalar_one_or_none()

                            if not outcome:
                                # Try matching by market_id alone if only one outcome
                                outcome_result = await session.execute(
                                    select(FuturesOutcome)
                                    .where(FuturesOutcome.market_id == market.id)
                                    .limit(2)
                                )
                                outcomes = outcome_result.scalars().all()
                                if len(outcomes) == 1:
                                    outcome = outcomes[0]
                                else:
                                    continue

                            # Update outcome probability
                            outcome.current_probability = prob
                            outcome.current_yes_bid = yes_bid
                            outcome.current_yes_ask = yes_ask
                            american = probability_to_american(prob) if 0 < prob < 1 else None
                            outcome.current_american_odds = american
                            outcome.last_updated = now
                            stats["outcomes_updated"] += 1

                        # Rate limit between Kalshi requests
                        await asyncio.sleep(0.3)

                    except Exception as e:
                        stats["errors"].append(f"kalshi_{market.external_id}: {str(e)[:100]}")

            finally:
                await service.close()

        # ── Fetch Polymarket prices ────────────────────────────────────
        if polymarket_markets:
            from app.services.polymarket_api import PolymarketAPIService
            poly_service = PolymarketAPIService()
            try:
                # Group by external_id (Polymarket event ID) to avoid duplicate fetches
                seen_events = {}
                for market, event in polymarket_markets:
                    if market.external_id in seen_events:
                        continue

                    try:
                        event_data = await poly_service.get_event_by_id(market.external_id)
                        stats["polymarket_fetched"] += 1

                        if not event_data:
                            continue

                        seen_events[market.external_id] = event_data

                        # Parse markets from event data
                        poly_markets = event_data.get("markets", [])
                        if not poly_markets:
                            continue

                        for pm in poly_markets:
                            condition_id = pm.get("conditionId", "")

                            # Parse outcomePrices and outcomes (both stringified JSON arrays)
                            prices_raw = pm.get("outcomePrices", "[]")
                            outcomes_raw = pm.get("outcomes", "[]")
                            try:
                                prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                                outcomes_names = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
                            except (json.JSONDecodeError, TypeError):
                                continue

                            if not prices:
                                continue

                            # Find matching outcome by condition_id
                            outcome_result = await session.execute(
                                select(FuturesOutcome)
                                .where(
                                    FuturesOutcome.market_id == market.id,
                                    FuturesOutcome.external_id == condition_id,
                                )
                            )
                            outcome = outcome_result.scalar_one_or_none()
                            if not outcome:
                                continue

                            # Determine the correct price for this outcome.
                            #
                            # Polymarket outcomePrices is parallel to outcomes:
                            #   outcomes: ["Team A", "Team B"]  →  prices: [0.6, 0.4]
                            #
                            # For NegRisk events, each sub-market has outcomes
                            # ["Yes", "No"] where prices[0] = "Yes" probability
                            # for that specific team. prices[0] is always correct.
                            #
                            # For non-NegRisk binary markets with team-name outcomes
                            # (e.g., outcomes: ["Warriors", "Celtics"]), prices[0]
                            # corresponds to the FIRST listed team, not necessarily
                            # the team our outcome record represents. We must match
                            # by name to get the right price.
                            prob = float(prices[0])  # default

                            if (
                                len(outcomes_names) >= 2
                                and len(prices) >= 2
                                and outcome.name
                                and outcomes_names[0].lower().strip() not in ("yes", "no", "")
                            ):
                                # Non-generic outcome names — find which price
                                # index corresponds to this outcome's team
                                outcome_name_lower = outcome.name.lower().strip()
                                for idx, oname in enumerate(outcomes_names):
                                    if idx < len(prices) and _fuzzy_team_match(
                                        outcome_name_lower, oname
                                    ):
                                        prob = float(prices[idx])
                                        break

                            if prob <= 0 or prob >= 1:
                                continue

                            # Update outcome probability
                            outcome.current_probability = prob
                            american = probability_to_american(prob) if 0 < prob < 1 else None
                            outcome.current_american_odds = american

                            # Parse bid/ask if available
                            best_bid = pm.get("bestBid")
                            best_ask = pm.get("bestAsk")
                            if best_bid is not None:
                                outcome.current_yes_bid = float(best_bid)
                            if best_ask is not None:
                                outcome.current_yes_ask = float(best_ask)

                            outcome.last_updated = now
                            stats["outcomes_updated"] += 1

                        # Rate limit between Polymarket requests
                        await asyncio.sleep(0.3)

                    except Exception as e:
                        stats["errors"].append(f"polymarket_{market.external_id}: {str(e)[:100]}")

            finally:
                await poly_service.close()

        # ── Write win_prob_snapshots for all live linked markets ───────
        # Re-query to pick up freshly-updated probabilities
        for market, event in rows:
            try:
                # Uses ticker fallback for generic-named Kalshi markets
                matchup = extract_matchup_with_ticker_fallback(
                    market.name, external_id=market.external_id,
                )
                if not matchup:
                    continue

                # Get outcomes for this market
                outcome_result = await session.execute(
                    select(FuturesOutcome)
                    .where(FuturesOutcome.market_id == market.id)
                    .order_by(FuturesOutcome.rank)
                )
                all_outcomes = outcome_result.scalars().all()
                if not all_outcomes:
                    continue

                # Find moneyline outcome and determine home/away mapping
                ml_result = find_moneyline_outcome(
                    all_outcomes, matchup,
                    event.home_team_name, event.away_team_name,
                )
                if not ml_result:
                    continue

                outcome, yes_is_home = ml_result
                yes_prob = float(outcome.current_probability)

                if yes_is_home:
                    home_prob = yes_prob
                else:
                    home_prob = 1.0 - yes_prob
                away_prob = 1.0 - home_prob

                # Write snapshot with deduplication
                snapshot, is_new = await _create_or_update_win_prob_snapshot(
                    session,
                    event_id=event.id,
                    source=market.source,
                    home_win_probability=round(home_prob, 4),
                    away_win_probability=round(away_prob, 4),
                    game_state={
                        "market_name": market.name,
                        "market_id": market.id,
                        "outcome_name": outcome.name,
                        "yes_probability": yes_prob,
                        "yes_bid": float(outcome.current_yes_bid) if outcome.current_yes_bid else None,
                        "yes_ask": float(outcome.current_yes_ask) if outcome.current_yes_ask else None,
                        "poll_type": "live_fast",
                    },
                )

                if is_new:
                    session.add(snapshot)
                    stats["snapshots_written"] += 1
                else:
                    stats["snapshots_deduped"] += 1

            except Exception as e:
                stats["errors"].append(f"snapshot_{market.id}: {str(e)[:100]}")

        await session.commit()

    logger.info(
        "Live prediction market poll: events=%d, markets=%d, "
        "kalshi=%d, polymarket=%d, outcomes=%d, snapshots=%d (deduped=%d)",
        stats["live_events"], stats["linked_markets"],
        stats["kalshi_fetched"], stats["polymarket_fetched"],
        stats["outcomes_updated"], stats["snapshots_written"],
        stats["snapshots_deduped"],
    )
    return stats


async def _backfill_polymarket_win_prob_history(
    market_id: int,
    event_id: int,
    fidelity: int = 30,
    interval: str = "max",
):
    """
    Backfill win_prob_snapshots from Polymarket's CLOB price history.

    When a Polymarket market is first linked to an event, we only have
    the current price. This function fetches the full price history from
    the CLOB API and writes it as win_prob_snapshots, giving us a complete
    trend line from market creation onward.

    Args:
        market_id: FuturesMarket.id (our internal ID)
        event_id: Event.id to write snapshots against
        fidelity: Price data granularity in minutes (30 = every half hour)
        interval: Time range ('1h', '6h', '1d', '1w', 'max')
    """
    import asyncio
    import json

    from app.models.models import (
        FuturesMarket, FuturesOutcome, Event, WinProbSnapshot,
    )

    stats = {
        "snapshots_created": 0,
        "errors": [],
    }

    async with get_task_session() as session:
        # Load market and event
        market = await session.get(FuturesMarket, market_id)
        event = await session.get(Event, event_id)
        if not market or not event:
            stats["errors"].append("market or event not found")
            return stats
        if market.source != "polymarket":
            stats["errors"].append("not a polymarket market")
            return stats

        # Extract matchup and find moneyline outcome
        matchup = extract_matchup_with_ticker_fallback(
            market.name, external_id=market.external_id,
        )
        if not matchup:
            stats["errors"].append("no matchup extracted")
            return stats

        outcome_result = await session.execute(
            select(FuturesOutcome)
            .where(FuturesOutcome.market_id == market.id)
            .order_by(FuturesOutcome.rank)
        )
        all_outcomes = outcome_result.scalars().all()
        if not all_outcomes:
            stats["errors"].append("no outcomes")
            return stats

        ml_result = find_moneyline_outcome(
            all_outcomes, matchup,
            event.home_team_name, event.away_team_name,
        )
        if not ml_result:
            stats["errors"].append("no moneyline outcome found")
            return stats

        outcome, yes_is_home = ml_result
        moneyline_condition_id = outcome.external_id

        # Fetch the Polymarket event to get clobTokenIds
        from app.services.polymarket_api import PolymarketAPIService
        service = PolymarketAPIService()
        try:
            event_data = await service.get_event_by_id(market.external_id)
            if not event_data:
                stats["errors"].append("failed to fetch polymarket event")
                return stats

            # Find the clobTokenId for our moneyline outcome's conditionId
            token_id = None
            for pm in event_data.get("markets", []):
                if pm.get("conditionId") == moneyline_condition_id:
                    clob_ids_raw = pm.get("clobTokenIds", "[]")
                    try:
                        if isinstance(clob_ids_raw, str):
                            clob_ids = json.loads(clob_ids_raw)
                        else:
                            clob_ids = clob_ids_raw
                    except (json.JSONDecodeError, TypeError):
                        clob_ids = []
                    if clob_ids:
                        token_id = clob_ids[0]  # First token = "Yes" side
                    break

            if not token_id:
                stats["errors"].append(
                    f"no clobTokenId for conditionId {moneyline_condition_id}"
                )
                return stats

            # Fetch price history
            history = await service.get_prices_history(
                token_id=token_id,
                interval=interval,
                fidelity=fidelity,
            )
            if not history:
                stats["errors"].append("empty price history")
                return stats

            logger.info(
                "Backfilling %d Polymarket price points for market %d → event %d",
                len(history), market_id, event_id,
            )

            # Write win_prob_snapshots from price history
            for point in history:
                ts = point.get("t")
                price = point.get("p")
                if ts is None or price is None:
                    continue

                yes_prob = float(price)
                if yes_prob <= 0 or yes_prob >= 1:
                    continue

                if yes_is_home:
                    home_prob = yes_prob
                else:
                    home_prob = 1.0 - yes_prob
                away_prob = 1.0 - home_prob

                captured_at = datetime.fromtimestamp(ts, tz=timezone.utc)

                snapshot = WinProbSnapshot(
                    event_id=event_id,
                    source="polymarket",
                    home_win_probability=round(home_prob, 4),
                    away_win_probability=round(away_prob, 4),
                    captured_at=captured_at,
                    game_state={
                        "market_id": market_id,
                        "backfill": True,
                    },
                )
                session.add(snapshot)
                stats["snapshots_created"] += 1

            await session.commit()

        finally:
            await service.close()

    logger.info(
        "Polymarket win_prob backfill: market=%d event=%d snapshots=%d errors=%d",
        market_id, event_id, stats["snapshots_created"], len(stats["errors"]),
    )
    return stats
