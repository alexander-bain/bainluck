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
    _expand_team_search_terms,
    _SPORT_CATEGORY_TO_KEY_PREFIX,
    MAX_TIME_DELTA,
    MAX_PAST_GAME_DELTA,
)

logger = logging.getLogger(__name__)


def _derive_sport_category(external_id: str | None) -> str | None:
    """Derive llm_sport_category from a Kalshi ticker's sport key.

    Maps ticker → sport_key → LLM category prefix. Returns None for
    non-Kalshi or unparseable tickers.
    """
    if not external_id:
        return None
    from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY
    sport_key = get_sport_prefix_from_ticker(external_id)
    if not sport_key:
        return None
    prefix = sport_key.split("_")[0]
    return SPORT_PREFIX_TO_LLM_CATEGORY.get(prefix)


def _set_market_sport_fields(market, matched_event: dict) -> None:
    """Propagate sport_id and fix llm_sport_category on a newly linked market."""
    if matched_event.get("sport_id"):
        market.sport_id = matched_event["sport_id"]
    ticker_category = _derive_sport_category(market.external_id)
    if ticker_category and market.llm_sport_category != ticker_category:
        market.llm_sport_category = ticker_category


async def _register_market_team_identities(session, event_id, matchup, market):
    """Register team identities after a successful market→event link.

    When a prediction market is linked to an event, we know the team names
    from both sources. Register these mappings so future lookups are instant.
    """
    from app.models.models import Event
    from app.services.team_identity import team_identity_service

    # Must eager-load sport to avoid lazy-load in async context
    event_result = await session.execute(
        select(Event)
        .options(joinedload(Event.sport))
        .where(Event.id == event_id)
    )
    event = event_result.scalar_one_or_none()
    if not event or not event.sport:
        return

    sport_key = event.sport.key if event.sport else ""
    source = market.source  # "kalshi" or "polymarket"

    # Register the event's team names with the identity service
    if event.home_team_id and event.home_team_name:
        await team_identity_service.register_team_identity(
            session, event.home_team_id, source, sport_key,
            source_name=matchup.team_a if matchup else event.home_team_name,
        )
    if event.away_team_id and event.away_team_name:
        await team_identity_service.register_team_identity(
            session, event.away_team_id, source, sport_key,
            source_name=matchup.team_b if matchup else event.away_team_name,
        )

# ── Consensus inversion detection ─────────────────────────────────────────────
# Prediction market data sometimes gets stored with inverted home/away mapping
# due to outcome-order mismatches or matchup parsing errors. This threshold
# detects probable inversions by comparing against the sportsbook consensus.
# If the prediction market home_prob and (1 - home_prob) are compared to
# consensus, and the FLIPPED version is closer, we flip it.

INVERSION_THRESHOLD = 0.30  # 30% — if flipping brings it 30%+ closer to consensus


async def _check_and_fix_inversion(
    session, event_id: int, home_prob: float, source: str,
) -> float:
    """
    Compare prediction market home_prob against sportsbook consensus.
    If the probability appears inverted (flipping it brings it much closer
    to consensus), return the flipped value. Otherwise return as-is.

    This catches systematic inversions from yes_is_home mismatches,
    outcome-order bugs, and matchup parsing errors.
    """
    from app.models.models import Event, OddsSnapshot

    event = await session.get(Event, event_id)
    if not event:
        return home_prob

    # Get sportsbook consensus: latest odds snapshot first, opening odds as fallback
    consensus = None

    # Try latest odds snapshot (most accurate for live/recent games)
    latest_snap = await session.execute(
        select(OddsSnapshot.home_win_probability)
        .where(
            OddsSnapshot.event_id == event_id,
            OddsSnapshot.home_win_probability.isnot(None),
        )
        .order_by(OddsSnapshot.captured_at.desc())
        .limit(1)
    )
    snap_prob = latest_snap.scalar_one_or_none()
    if snap_prob is not None:
        consensus = float(snap_prob)

    # Fallback to opening odds (always available, set pre-game)
    if consensus is None and event.opening_home_probability is not None:
        consensus = float(event.opening_home_probability)

    if consensus is None or consensus <= 0.01 or consensus >= 0.99:
        return home_prob  # No reliable consensus to compare against

    # Compare: is the raw or flipped version closer to consensus?
    raw_diff = abs(home_prob - consensus)
    flipped = 1.0 - home_prob
    flipped_diff = abs(flipped - consensus)

    # Only flip if: (a) flipping brings it significantly closer, and
    # (b) the raw value is far enough from consensus to be suspicious
    if raw_diff > INVERSION_THRESHOLD and flipped_diff < raw_diff * 0.5:
        logger.warning(
            "Inversion detected for event %d source=%s: "
            "raw=%.3f consensus=%.3f flipped=%.3f (raw_diff=%.3f > %.2f, "
            "flipped_diff=%.3f). Using flipped value.",
            event_id, source, home_prob, consensus, flipped,
            raw_diff, INVERSION_THRESHOLD, flipped_diff,
        )
        return flipped

    return home_prob


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

    import time as _time
    _task_start = _time.monotonic()
    _TIME_BUDGET_SECONDS = 780  # Leave 60s buffer before the 840s soft limit

    def _time_remaining() -> float:
        return _TIME_BUDGET_SECONDS - (_time.monotonic() - _task_start)

    now = datetime.now(timezone.utc)
    # Track newly linked Polymarket markets for price history backfill
    polymarket_backfill_queue = []

    async with get_task_session() as session:
        # ── Phase 1: Link unlinked game-level markets ────────────────────
        logger.info("Phase 1 starting — %.0fs budget remaining", _time_remaining())
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
            if _time_remaining() < 120:
                logger.info("Phase 1 Pass 1 time budget exhausted after %d/%d ticker markets", stats["markets_scanned"], len(ticker_markets))
                break
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
                _set_market_sport_fields(market, matched_event)
                stats["newly_linked"] += 1
                stats["funnel"]["linked"] += 1
                logger.info(
                    "Linked %s market '%s' → event %d (%s vs %s) [ticker=%s]",
                    market.source, market.name, matched_event["event_id"],
                    matched_event["home_team"], matched_event["away_team"],
                    market.external_id,
                )
                await _register_market_team_identities(
                    session, matched_event["event_id"], matchup, market,
                )
                # Propagate event_id to Polymarket sub-markets in the same group
                if market.group_id and market.source == "polymarket":
                    from sqlalchemy import text as _text
                    await session.execute(_text("""
                        UPDATE futures_markets
                        SET event_id = :eid
                        WHERE group_id = :gid
                          AND group_type = 'polymarket_sub_market'
                          AND (event_id IS NULL OR event_id != :eid)
                    """), {"eid": matched_event["event_id"], "gid": market.group_id})
            else:
                # No existing event found — try auto-creating one.
                # This handles sports The Odds API doesn't cover (e.g., Olympics).
                if matchup and matchup.team_b:
                    auto_event = await _create_event_from_prediction_market(
                        session, matchup, market, now,
                    )
                    if auto_event:
                        market.event_id = auto_event["event_id"]
                        _set_market_sport_fields(market, auto_event)
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
            if _time_remaining() < 120:
                logger.info("Phase 1 Pass 2 time budget exhausted after %d markets scanned", stats["markets_scanned"])
                break
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
                _set_market_sport_fields(market, matched_event)
                stats["newly_linked"] += 1
                stats["funnel"]["linked"] += 1
                logger.info(
                    "Linked %s market '%s' → event %d (%s vs %s) [yes_is_home=%s]",
                    market.source, market.name, matched_event["event_id"],
                    matched_event["home_team"], matched_event["away_team"],
                    matched_event["yes_is_home"],
                )
                await _register_market_team_identities(
                    session, matched_event["event_id"], matchup, market,
                )
                # Propagate event_id to Polymarket sub-markets in the same group
                if market.group_id and market.source == "polymarket":
                    from sqlalchemy import text as _text
                    await session.execute(_text("""
                        UPDATE futures_markets
                        SET event_id = :eid
                        WHERE group_id = :gid
                          AND group_type = 'polymarket_sub_market'
                          AND (event_id IS NULL OR event_id != :eid)
                    """), {"eid": matched_event["event_id"], "gid": market.group_id})
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
                        _set_market_sport_fields(market, auto_event)
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
        logger.info("Phase 1 done (%d scanned, %d linked) — %.0fs remaining", stats["markets_scanned"], stats["newly_linked"], _time_remaining())
        # Scan ALL linked markets for two problems:
        # (a) Stale: linked to completed/closed events — try to find the next game
        # (b) Mislinked: teams don't both match the linked event (e.g.,
        #     "Pistons vs. Bulls" linked to "Georgia Southern vs South Florida Bulls"
        #     because "Bulls" substring-matched but "Pistons" didn't)
        #
        # Time-budgeted: skip if running low on time (most expensive phase)
        stats["funnel"].setdefault("stale_relinked", 0)
        stats["funnel"].setdefault("mislink_fixed", 0)
        stats["funnel"].setdefault("phase15_skipped_budget", False)
        stats["funnel"].setdefault("phase15_checked", 0)

        _skip_phase15 = _time_remaining() < 120
        if _skip_phase15:
            logger.info("Skipping Phase 1.5 — only %.0fs remaining", _time_remaining())
            stats["funnel"]["phase15_skipped_budget"] = True

        all_linked_rows = []
        if not _skip_phase15:
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
            # Time budget check inside the loop
            if _time_remaining() < 60:
                logger.info("Phase 1.5 time budget exhausted after %d/%d markets", stats["funnel"]["phase15_checked"], len(all_linked_rows))
                break
            stats["funnel"]["phase15_checked"] += 1
            try:
                # Backfill sport_id from event if missing on market
                if market.sport_id is None and linked_event.sport_id:
                    market.sport_id = linked_event.sport_id
                    stats["funnel"].setdefault("sport_id_backfilled", 0)
                    stats["funnel"]["sport_id_backfilled"] += 1

                # Fix wrong llm_sport_category from ticker
                ticker_cat = _derive_sport_category(market.external_id)
                if ticker_cat and market.llm_sport_category != ticker_cat:
                    market.llm_sport_category = ticker_cat
                    stats["funnel"].setdefault("sport_category_fixed", 0)
                    stats["funnel"]["sport_category_fixed"] += 1

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

                # Check if linked to an auto-created prediction market event
                # (external_id starts with "pm_"). These should be re-linked to
                # real Odds API events when available.
                is_auto_created = (
                    linked_event.external_id
                    and str(linked_event.external_id).startswith("pm_")
                )

                # Skip if teams match AND event is still active AND not auto-created
                if teams_match and not is_finished and not is_auto_created:
                    continue

                # Need to re-link: teams don't match, event finished, or auto-created
                reason = (
                    "auto_created" if is_auto_created
                    else "mislinked" if not teams_match
                    else "completed"
                )
                ticker_game_date = extract_game_date_from_ticker(market.external_id) if market.source == "kalshi" else None

                better_match = await _find_matching_event(
                    session, matchup, market, now,
                    game_date_override=ticker_game_date,
                )

                if better_match and better_match["event_id"] != linked_event.id:
                    logger.info(
                        "Re-linking %s '%s' from %s event %d (%s vs %s) → event %d (%s vs %s)",
                        market.source, market.name, reason,
                        linked_event.id, linked_event.home_team_name, linked_event.away_team_name,
                        better_match["event_id"],
                        better_match["home_team"], better_match["away_team"],
                    )
                    # Move snapshots from auto-created event to real event
                    if is_auto_created or not teams_match:
                        del_result = await session.execute(
                            delete(WinProbSnapshot).where(
                                WinProbSnapshot.event_id == linked_event.id,
                                WinProbSnapshot.source == market.source,
                            )
                        )
                        stats["orphaned_snapshots_deleted"] += del_result.rowcount
                    market.event_id = better_match["event_id"]
                    _set_market_sport_fields(market, better_match)
                    if market.group_id and market.source == "polymarket":
                        from sqlalchemy import text as _text
                        await session.execute(_text("""
                            UPDATE futures_markets
                            SET event_id = :eid
                            WHERE group_id = :gid
                              AND group_type = 'polymarket_sub_market'
                              AND (event_id IS NULL OR event_id != :eid)
                        """), {"eid": better_match["event_id"], "gid": market.group_id})
                    if is_auto_created:
                        stats["funnel"].setdefault("auto_created_relinked", 0)
                        stats["funnel"]["auto_created_relinked"] += 1
                    elif not teams_match:
                        stats["funnel"]["mislink_fixed"] += 1
                    else:
                        stats["funnel"]["stale_relinked"] += 1
                elif is_auto_created:
                    # Auto-created but no better match — keep as-is for now
                    pass
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

        # ── Phase 2: Write win_prob_snapshots for active linked markets ────
        #
        # Only process markets linked to scheduled/live events.
        # Completed/closed events are excluded — prediction market prices
        # after game end are stale and stretch the OddsChart past the real
        # game boundary (the "prediction market bleed" bug, 0t-1).
        #
        # Time-budgeted: skip if running low on time
        stats["funnel"].setdefault("phase2_skipped_budget", False)
        linked_rows = []
        if _time_remaining() < 60:
            logger.info("Skipping Phase 2 — only %.0fs remaining", _time_remaining())
            stats["funnel"]["phase2_skipped_budget"] = True
        else:
            linked_result = await session.execute(
                select(FuturesMarket, Event)
                .join(Event, FuturesMarket.event_id == Event.id)
                .where(
                    FuturesMarket.source.in_(["kalshi", "polymarket"]),
                    FuturesMarket.event_id.isnot(None),
                    Event.status.in_(["scheduled", "live"]),
                )
            )
            linked_rows = linked_result.all()

        phase2_processed = 0
        for market, event in linked_rows:
            if _time_remaining() < 60:
                logger.info("Phase 2 time budget exhausted after %d/%d markets", phase2_processed, len(linked_rows))
                break
            phase2_processed += 1
            try:
                matchup = extract_matchup_with_ticker_fallback(
                    market.name, external_id=market.external_id,
                )
                if not matchup:
                    continue

                outcome_result = await session.execute(
                    select(FuturesOutcome)
                    .where(FuturesOutcome.market_id == market.id)
                    .order_by(FuturesOutcome.rank)
                )
                all_outcomes = outcome_result.scalars().all()
                if not all_outcomes:
                    continue

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

                home_prob = await _check_and_fix_inversion(
                    session, market.event_id, home_prob, market.source,
                )
                away_prob = 1.0 - home_prob

                source_key = market.source
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

                from sqlalchemy import update as _sql_upd
                _pm_r = await session.execute(
                    select(Event.win_probability_sources).where(Event.id == market.event_id)
                )
                _pm_wps = _pm_r.scalar_one_or_none() or {}
                _pm_wps[source_key] = round(home_prob, 4)
                await session.execute(
                    _sql_upd(Event)
                    .where(Event.id == market.event_id)
                    .values(win_probability_sources=_pm_wps)
                )

                # Commit per-market to avoid deadlocks with live polling task
                await session.commit()

            except Exception as e:
                err_str = str(e)
                if "deadlock" in err_str.lower():
                    await session.rollback()
                    stats["funnel"].setdefault("phase2_deadlocks", 0)
                    stats["funnel"]["phase2_deadlocks"] += 1
                else:
                    stats["errors"].append(f"market {market.id}: {err_str[:100]}")
                continue

    # ── Phase 3: Backfill Polymarket price history for newly linked markets ──
    # Runs outside the main DB session to avoid holding transactions open
    # during API calls. Each backfill is independent and idempotent.
    if polymarket_backfill_queue:
        if _time_remaining() < 60:
            logger.info("Skipping Phase 3 — only %.0fs remaining", _time_remaining())
            stats["funnel"]["polymarket_backfills_skipped_budget"] = True
        else:
            stats["funnel"]["polymarket_backfills_queued"] = len(polymarket_backfill_queue)
            for market_id, event_id in polymarket_backfill_queue:
                if _time_remaining() < 30:
                    logger.info("Phase 3 time budget exhausted after %d/%d backfills",
                                stats["funnel"].get("polymarket_backfill_snapshots", 0),
                                len(polymarket_backfill_queue))
                    break
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
        "snapshots_written=%d, deduped=%d, errors=%d, %.0fs remaining",
        stats["markets_scanned"], stats["newly_linked"],
        stats["snapshots_written"], stats["snapshots_deduped"],
        len(stats["errors"]), _time_remaining(),
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

    # Create ILIKE conditions for team names.
    # _expand_team_search_terms produces multiple patterns for abbreviated
    # names (e.g., "WSH Capitals" → ["WSH Capitals", "Capitals"]) so that
    # ILIKE '%Capitals%' matches "Washington Capitals" in the events table.
    ilike_conditions = []
    for team in teams_to_search:
        for search_term in _expand_team_search_terms(team):
            pattern = f"%{_escape_like(search_term)}%"
            ilike_conditions.append(Event.home_team_name.ilike(pattern))
            ilike_conditions.append(Event.away_team_name.ilike(pattern))

    # Also restrict: don't match events that started more than 6 hours ago
    # (unless they're still live)
    past_cutoff = now - MAX_PAST_GAME_DELTA

    # ── Pass 1: Time-windowed search ──────────────────────────────────
    # Kalshi commence_time is the market RESOLUTION date (often weeks after
    # the game), so we use a wider window when matching by ticker-extracted
    # game date. Polymarket dates are closer to actual game time.
    reference_time = game_date_override or market.commence_time or now
    time_delta = timedelta(days=7) if market.source == "kalshi" else MAX_TIME_DELTA
    time_start = reference_time - time_delta
    time_end = reference_time + time_delta

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
            external_id=market.external_id or "",
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
                "sport_id": event.sport_id,
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

    if game_date_override and market.source == "kalshi":
        window_hours = 48
    elif game_date_override:
        window_hours = 3
    else:
        window_hours = 6
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
            "yes_is_home": True,
            "sport_id": event.sport_id,
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
                    "sport_id": best_event.sport_id,
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

    # NEVER auto-create events for major sports covered by The Odds API.
    # These sports always have events from the Odds API; auto-creating from
    # prediction markets causes duplicates with wrong commence_times
    # (Kalshi uses market resolution date, not game date).
    _ODDS_API_COVERED_PREFIXES = (
        "basketball_nba", "basketball_ncaab", "basketball_wnba",
        "americanfootball_nfl", "americanfootball_ncaaf",
        "baseball_mlb", "icehockey_nhl",
        "soccer_usa_mls",
    )
    if any(sport_key.startswith(prefix) for prefix in _ODDS_API_COVERED_PREFIXES):
        logger.debug(
            "Skipping auto-create for '%s' — sport %s is covered by The Odds API",
            market.name, sport_key,
        )
        return None

    # ── Unified event matching via Event Registry ──
    # Determine commence_time: use market's commence_time if reasonable,
    # otherwise use now (the market is probably live)
    commence_time = market.commence_time
    if not commence_time or abs((commence_time - now).total_seconds()) > 86400 * 30:
        commence_time = now

    status = "live" if commence_time <= now else "scheduled"
    external_id = f"pm_{market.source}_{market.external_id}"

    from app.services.event_registry import (
        find_or_create_event, EventIdentity, EventClaim,
    )
    identity = EventIdentity(
        sport_key=sport_key,
        home_team_name=team_a,
        away_team_name=team_b,
        commence_time=commence_time,
        claim=EventClaim(market.source, external_id),
        status=status,
    )
    event, was_created = await find_or_create_event(session, identity)

    # Determine yes_is_home mapping
    team_match = match_teams_to_event(matchup, team_a, team_b, external_id=external_id)
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

        # Batch-load all outcomes for linked markets to avoid N+1
        all_market_ids = [market.id for market, event in rows]
        outcome_lookup = {}
        outcomes_by_market = {}
        if all_market_ids:
            outcomes_result = await session.execute(
                select(FuturesOutcome).where(FuturesOutcome.market_id.in_(all_market_ids))
            )
            for o in outcomes_result.scalars().all():
                if o.external_id:
                    outcome_lookup[(o.market_id, o.external_id)] = o
                outcomes_by_market.setdefault(o.market_id, []).append(o)

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

                            # Find matching outcome by ticker (batch-loaded)
                            ticker = mkt_data.get("ticker", "")
                            outcome = outcome_lookup.get((market.id, ticker))

                            if not outcome:
                                market_outcomes = outcomes_by_market.get(market.id, [])
                                if len(market_outcomes) == 1:
                                    outcome = market_outcomes[0]
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

                            # Find matching outcome by condition_id (batch-loaded)
                            outcome = outcome_lookup.get((market.id, condition_id))
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
                            ltp = pm.get("lastTradePrice")
                            best_bid = pm.get("bestBid")
                            best_ask = pm.get("bestAsk")

                            # Skip entirely if no trading activity — stale price from
                            # hours/days ago is worse than no data.
                            if ltp is None and (best_bid is None or float(best_bid) == 0):
                                continue

                            prob = float(prices[0])  # default: outcomePrices midpoint

                            # Prefer lastTradePrice when bid/ask spread is wide (>15pp).
                            # During blowouts, the order book becomes illiquid and the
                            # midpoint is meaningless (e.g., bid=0.34 ask=0.43 → mid=0.385
                            # but the game is effectively over).
                            if (ltp is not None
                                and best_bid is not None and best_ask is not None):
                                spread = abs(float(best_ask) - float(best_bid))
                                if spread > 0.15 and 0 < float(ltp) < 1:
                                    prob = float(ltp)

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
        # Re-query to pick up freshly-updated probabilities.
        #
        # DEDUP: Kalshi creates separate binary markets per team outcome
        # (e.g., "Celtics win?" and "76ers win?" for the same game). If both
        # are linked to the same event, processing both would write conflicting
        # probabilities to win_probability_sources["kalshi"], causing oscillation
        # (80% → 20% → 80%) on the chart.  Fix: pick ONE market per (event, source).
        # Prefer the market whose moneyline outcome maps to yes_is_home=True
        # (direct probability, no inversion — less error-prone).
        best_per_event_source: dict[tuple[int, str], tuple] = {}
        for market, event in rows:
            key = (event.id, market.source)
            if key not in best_per_event_source:
                best_per_event_source[key] = (market, event)
            else:
                # If we already have one, prefer the market with more outcomes
                # (more outcomes = more likely to be the primary matchup market)
                existing_market = best_per_event_source[key][0]
                existing_count = len(outcomes_by_market.get(existing_market.id, []))
                new_count = len(outcomes_by_market.get(market.id, []))
                if new_count > existing_count:
                    best_per_event_source[key] = (market, event)

        for market, event in best_per_event_source.values():
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

                # Cross-check against sportsbook consensus to catch inversions
                home_prob = await _check_and_fix_inversion(
                    session, event.id, home_prob, market.source,
                )
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

                # Write to win_probability_sources on the event
                from sqlalchemy import update as _sql_upd2
                _pm_r2 = await session.execute(
                    select(Event.win_probability_sources).where(Event.id == event.id)
                )
                _pm_wps2 = _pm_r2.scalar_one_or_none() or {}
                _pm_wps2[market.source] = round(home_prob, 4)
                await session.execute(
                    _sql_upd2(Event)
                    .where(Event.id == event.id)
                    .values(win_probability_sources=_pm_wps2)
                )

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

            # Check for inversion against sportsbook consensus ONCE before
            # writing the entire history (avoids N queries in the loop).
            # Use a mid-history sample point to determine if we need to flip.
            sample_idx = len(history) // 2
            sample_price = history[sample_idx].get("p") if history else None
            needs_flip = False
            if sample_price is not None:
                sample_yes = float(sample_price)
                if 0 < sample_yes < 1:
                    if yes_is_home:
                        sample_home = sample_yes
                    else:
                        sample_home = 1.0 - sample_yes
                    checked = await _check_and_fix_inversion(
                        session, event_id, sample_home, "polymarket",
                    )
                    needs_flip = abs(checked - sample_home) > 0.01

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

                # Apply inversion fix if detected from sample
                if needs_flip:
                    home_prob = 1.0 - home_prob
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
