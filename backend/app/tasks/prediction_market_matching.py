"""
Prediction market → Event matching task.

Periodically scans futures_markets from Kalshi and Polymarket to:
1. Detect game-level binary markets (moneyline-style outcomes)
2. Match them to Event records by team name + commence_time
3. Write win_prob_snapshots so they appear as trend lines on OddsChart

Runs after Kalshi (:45) and Polymarket (:15) polling to pick up fresh data.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, or_, and_, func

from app.tasks.base import get_task_session
from app.utils.prediction_market_matching import (
    is_game_level_market,
    is_kalshi_game_ticker,
    _KALSHI_GAME_TICKER_PREFIXES,
    get_sport_prefix_from_ticker,
    extract_matchup,
    extract_matchup_with_ticker_fallback,
    extract_teams_from_ticker,
    extract_game_date_from_ticker,
    match_teams_to_event,
    find_moneyline_outcome,
    _fuzzy_team_match,
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
        unlinked_result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.event_id.is_(None),
                FuturesMarket.status == "open",
            )
            .order_by(FuturesMarket.updated_at.desc())
            .limit(limit)
        )
        unlinked_markets = unlinked_result.scalars().all()
        stats["funnel"]["total_unlinked"] = len(unlinked_markets) + len(ticker_markets)
        stats["funnel"]["general_scan_count"] = len(unlinked_markets)

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

    Strategy:
    1. Search events by team name ILIKE matching
    2. Filter by commence_time proximity
    3. Prefer events in the same sport category
    4. Return the best match or None

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

    # Time window: events starting within ±48 hours of reference time.
    # For Kalshi game tickers, use the game date from the ticker (not
    # market.commence_time, which is the resolution date weeks later).
    reference_time = game_date_override or market.commence_time or now
    time_start = reference_time - MAX_TIME_DELTA
    time_end = reference_time + MAX_TIME_DELTA

    # Also restrict: don't match events that started more than 6 hours ago
    # (unless they're still live)
    past_cutoff = now - MAX_PAST_GAME_DELTA

    # Query candidate events
    event_result = await session.execute(
        select(Event)
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
    candidates = event_result.scalars().all()

    if not candidates:
        return None

    # Score each candidate
    best_match = None
    best_score = -1

    for event in candidates:
        # Check team name matching
        team_match = match_teams_to_event(
            matchup,
            event.home_team_name,
            event.away_team_name,
        )
        if not team_match:
            continue

        # For "Will X win?" with only one team, verify the other team too
        # by checking that at least one market team matches an event team
        if matchup.format_type == "will_win" and not matchup.team_b:
            # Single-team format — must match one event team
            if not (
                _fuzzy_team_match(matchup.team_a, event.home_team_name)
                or _fuzzy_team_match(matchup.team_a, event.away_team_name)
            ):
                continue

        # Score: prefer closer commence_time + same sport + live games
        score = 0

        # Time proximity (max 10 points, closer = higher)
        if event.commence_time and market.commence_time:
            delta_hours = abs(
                (event.commence_time - market.commence_time).total_seconds()
            ) / 3600
            score += max(0, 10 - delta_hours)
        elif event.commence_time:
            delta_hours = abs(
                (event.commence_time - now).total_seconds()
            ) / 3600
            score += max(0, 5 - delta_hours / 10)

        # Live games get a bonus
        if event.status == "live":
            score += 5
        elif event.status == "scheduled":
            score += 3

        # Both teams matched (not just one) get a bonus
        if matchup.team_b:
            other = matchup.team_b if matchup.yes_team == matchup.team_a else matchup.team_a
            if (
                _fuzzy_team_match(other, event.home_team_name)
                or _fuzzy_team_match(other, event.away_team_name)
            ):
                score += 10  # Both teams matched — very strong signal

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

    Only returns a match if EXACTLY ONE event matches (unambiguous).
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
    # Search ±6 hours (tighter than the usual ±48h since we have no team names)
    reference_time = game_date_override or market.commence_time
    if not reference_time:
        return None

    time_start = reference_time - timedelta(hours=6)
    time_end = reference_time + timedelta(hours=6)

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
        .limit(5)
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
        logger.debug(
            "Sport+time fallback found %d candidates for %s (ambiguous, skipping)",
            len(candidates), market.external_id,
        )

    return None


def _escape_like(s: str) -> str:
    """Escape special characters for ILIKE patterns."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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

                            # Calculate probability from mid-market
                            if yes_bid is not None and yes_ask is not None:
                                prob = (yes_bid + yes_ask) / 2
                            elif last_price is not None:
                                prob = last_price
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

                            # Parse outcomePrices (stringified JSON array)
                            prices_raw = pm.get("outcomePrices", "[]")
                            try:
                                prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                            except (json.JSONDecodeError, TypeError):
                                continue

                            if not prices:
                                continue

                            prob = float(prices[0])
                            if prob <= 0 or prob >= 1:
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
