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
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, or_, and_, func, delete, case, update, text
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
    feeds_win_prob_blend,
    is_combat_fight_ticker,
    _fuzzy_team_match,
    _expand_team_search_terms,
    _SPORT_CATEGORY_TO_KEY_PREFIX,
    MAX_TIME_DELTA,
    MAX_PAST_GAME_DELTA,
)

logger = logging.getLogger(__name__)

# #195: how far ahead of commence the live poller pins THE SCRIPT pregame mark.
# The poll already covers scheduled events within +3h; the mark is captured only
# in the final window before (or after) commence so it reflects the settled
# pregame consensus rather than a stale hours-out price.
_PREGAME_MARK_LEAD_MINUTES = 15


@dataclass(frozen=True)
class _LinkedMarketRef:
    """Scalar copy of a linked market/event row.

    Phase 2 commits and rolls back per market. SQLAlchemy expires ORM instances
    on rollback, and reading an expired async ORM attribute can raise
    MissingGreenlet. Keep only scalar values in the long-running Phase 2 loop.
    """

    market_id: int
    source: str
    external_id: str | None
    name: str
    event_id: int
    event_commence_time: datetime | None
    home_team_name: str | None
    away_team_name: str | None

    @property
    def is_game_winner(self) -> bool:
        # A5 (#1024): a two-sided winner line — team-sport …game OR a combat
        # fight winner (kxufcfight/kxboxing) — so the fight-winner is preferred
        # over its card's props when picking the group's primary market.
        return feeds_win_prob_blend(self.external_id)


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

# ── Duplicate linkage guard ──────────────────────────────────────────────────
# Prevents multiple Kalshi game markets from DIFFERENT games being linked to
# the same event. This is the root cause of sawtooth oscillation: e.g.,
# "Washington vs Loyola Marymount Game 1" and "Game 2" both linked to one
# event, producing alternating probabilities in win_prob_snapshots.


async def _check_duplicate_kalshi_linkage(
    session, event_id: int, market, ticker_game_date,
) -> bool:
    """Check if linking this Kalshi market would create a multi-game conflict.

    Returns True if the link should PROCEED (no conflict), False to SKIP.

    Conflict detection: if the event already has a Kalshi game market linked
    with a different ticker date, this is a different game and should NOT be
    linked to the same event.
    """
    from app.models.models import FuturesMarket

    if market.source != "kalshi":
        return True  # Only guard Kalshi markets

    ext = (market.external_id or "").lower()
    prefix = ext.split("-")[0] if "-" in ext else ext
    if not prefix.endswith("game"):
        return True  # Only guard game-level markets

    # Find existing Kalshi game markets already linked to this event
    existing_result = await session.execute(
        select(FuturesMarket.id, FuturesMarket.external_id, FuturesMarket.name)
        .where(
            FuturesMarket.event_id == event_id,
            FuturesMarket.source == "kalshi",
            FuturesMarket.id != market.id,
        )
    )
    existing = existing_result.all()
    if not existing:
        return True  # No existing Kalshi markets — safe to link

    # Check if any existing market is a game market with a different date
    for row in existing:
        existing_ext = (row.external_id or "").lower()
        existing_prefix = existing_ext.split("-")[0] if "-" in existing_ext else existing_ext
        if not existing_prefix.endswith("game"):
            continue  # Skip non-game markets (props, totals, etc.)

        # Both are game markets — compare ticker dates
        existing_date = extract_game_date_from_ticker(row.external_id)
        if ticker_game_date and existing_date:
            # If dates differ by more than 4 hours, these are different games
            td1 = ticker_game_date if ticker_game_date.tzinfo else ticker_game_date.replace(tzinfo=timezone.utc)
            td2 = existing_date if existing_date.tzinfo else existing_date.replace(tzinfo=timezone.utc)
            if abs((td1 - td2).total_seconds()) > 4 * 3600:
                logger.warning(
                    "Duplicate linkage blocked: market %s (date=%s) vs existing market %d '%s' (date=%s) on event %d",
                    market.external_id, td1.date(), row.id, row.external_id, td2.date(), event_id,
                )
                return False  # Different game — do NOT link

        # Same date or unparseable — compare full tickers.
        # If external_ids are different but same prefix, they might be
        # different games on the same day (Game 1 vs Game 2 in a tournament).
        # The ticker suffix after the date encodes teams, so if tickers differ
        # significantly, it's a different matchup or game number.
        if market.external_id and row.external_id:
            if market.external_id.lower() == row.external_id.lower():
                continue  # Same market (duplicate) — safe
            # Different tickers — could be dual market (Team A win? + Team B win?)
            # or truly different games. Dual markets have the same date+teams portion
            # but that's already handled by the devig averaging. For safety, allow
            # the link — the Phase 2 devig logic will handle dual markets correctly.

    return True  # No conflicts detected


# ── Consensus inversion detection ─────────────────────────────────────────────
# Prediction market data sometimes gets stored with inverted home/away mapping
# due to outcome-order mismatches or matchup parsing errors. This threshold
# detects probable inversions by comparing against the sportsbook consensus.
# If the prediction market home_prob and (1 - home_prob) are compared to
# consensus, and the FLIPPED version is closer, we flip it.

INVERSION_THRESHOLD = 0.30  # 30% — if flipping brings it 30%+ closer to consensus

# Peer-consensus fallback (#1112): when the sportsbook consensus is ambiguous
# (~0.5) or missing — the mid-game case where the only OddsSnapshot is a stale
# pregame line — consult already-written INDEPENDENT live sources on the event.
# These sources derive from the game itself, not the prediction-market linkage,
# so they cannot share the yes_is_home orientation bug we are guarding against.
# Kalshi/polymarket are excluded: they can carry the SAME inversion.
_PEER_CONSENSUS_SOURCES = ("stat_model", "mlb", "espn", "betting")
_PEER_EXTREME_HI = 0.80
_PEER_EXTREME_LO = 0.20
_PEER_MIN_VOTES = 2  # require >=2 extreme peers agreeing before we trust them


def _peer_consensus_side(win_probability_sources: dict, exclude_source: str):
    """Return 'home' / 'away' if >=2 independent live peers are extreme and
    unanimous on a side, else None. Peers on opposite extremes cancel to None."""
    if not win_probability_sources:
        return None
    home_votes = 0
    away_votes = 0
    for ps in _PEER_CONSENSUS_SOURCES:
        if ps == exclude_source:
            continue
        pv = win_probability_sources.get(ps)
        if pv is None:
            continue
        try:
            pv = float(pv)
        except (TypeError, ValueError):
            continue
        if pv >= _PEER_EXTREME_HI:
            home_votes += 1
        elif pv <= _PEER_EXTREME_LO:
            away_votes += 1
    if home_votes >= _PEER_MIN_VOTES and away_votes == 0:
        return "home"
    if away_votes >= _PEER_MIN_VOTES and home_votes == 0:
        return "away"
    return None


async def _check_and_fix_inversion(
    session, event_id: int, home_prob: float, source: str,
) -> float:
    """
    Compare prediction market home_prob against sportsbook consensus.
    If the probability appears inverted (flipping it brings it much closer
    to consensus), return the flipped value. Otherwise return as-is.

    This catches systematic inversions from yes_is_home mismatches,
    outcome-order bugs, and matchup parsing errors.

    Two independent checks:
      1. Sportsbook consensus (primary): flip if flipping lands far closer to
         the latest/opening OddsSnapshot line.
      2. Peer consensus (#1112 fallback): when the sportsbook line is ambiguous
         (~0.5) or missing — the mid-game stale-pregame case where check (1)
         cannot fire — flip when this source is the extreme MIRROR of >=2
         unanimous, independent live peers (stat_model/mlb/espn/betting).
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

    # Primary check: sportsbook consensus (only when it is reliable, i.e. extreme
    # enough to disambiguate a flip).
    if consensus is not None and 0.01 < consensus < 0.99:
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

    # Fallback check: peer consensus (#1112). Only meaningful when THIS source is
    # itself extreme — a mirror is an extreme value on the wrong side. This never
    # fires pregame (peers are not extreme until the game decides).
    if home_prob <= _PEER_EXTREME_LO or home_prob >= _PEER_EXTREME_HI:
        peer_side = _peer_consensus_side(
            event.win_probability_sources or {}, exclude_source=source,
        )
        if peer_side == "home" and home_prob <= _PEER_EXTREME_LO:
            logger.warning(
                "Peer-consensus inversion for event %d source=%s: raw=%.3f is the "
                "mirror of >=2 unanimous home-extreme peers. Using flipped value.",
                event_id, source, home_prob,
            )
            return 1.0 - home_prob
        if peer_side == "away" and home_prob >= _PEER_EXTREME_HI:
            logger.warning(
                "Peer-consensus inversion for event %d source=%s: raw=%.3f is the "
                "mirror of >=2 unanimous away-extreme peers. Using flipped value.",
                event_id, source, home_prob,
            )
            return 1.0 - home_prob

    return home_prob


# SQL LIKE patterns for Kalshi game tickers (e.g., "kxnbagame%")
# Used to directly query game-level markets without scanning all markets.
_KALSHI_TICKER_LIKE_PATTERNS = [f"{prefix}%" for prefix in _KALSHI_GAME_TICKER_PREFIXES]


async def _try_link_market(
    session, market, matchup, matched_event, stats: dict,
    ticker_game_date, now: datetime, polymarket_backfill_queue: list,
) -> None:
    """Link a matched market to its event, or auto-create an event if needed."""
    from app.models.models import FuturesMarket

    if matched_event:
        if not await _check_duplicate_kalshi_linkage(
            session, matched_event["event_id"], market, ticker_game_date,
        ):
            stats["funnel"].setdefault("duplicate_linkage_blocked", 0)
            stats["funnel"]["duplicate_linkage_blocked"] += 1
            matched_event = None

    if matched_event:
        market.event_id = matched_event["event_id"]
        _set_market_sport_fields(market, matched_event)
        stats["newly_linked"] += 1
        stats["funnel"]["linked"] += 1
        logger.info(
            "Linked %s market '%s' -> event %d (%s vs %s)",
            market.source, market.name, matched_event["event_id"],
            matched_event["home_team"], matched_event["away_team"],
        )
        await _register_market_team_identities(
            session, matched_event["event_id"], matchup, market,
        )
        if market.group_id and market.source == "polymarket":
            from sqlalchemy import text as _text
            await session.execute(_text("""
                UPDATE futures_markets
                SET event_id = :eid
                WHERE group_id = :gid
                  AND group_type = 'polymarket_sub_market'
                  AND (event_id IS NULL OR event_id != :eid)
            """), {"eid": matched_event["event_id"], "gid": market.group_id})
        if market.source == "polymarket":
            polymarket_backfill_queue.append(
                (market.id, matched_event["event_id"])
            )
        return

    # No existing event — try auto-creating
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
            if market.source == "polymarket":
                polymarket_backfill_queue.append(
                    (market.id, auto_event["event_id"])
                )
            return

    # Record failure
    if not matchup:
        stats["funnel"]["no_matchup_extracted"] += 1
    stats["funnel"]["no_event_found"] += 1
    if len(stats["funnel"]["sample_game_level_no_event"]) < 10:
        stats["funnel"]["sample_game_level_no_event"].append({
            "source": market.source,
            "name": market.name,
            "team_a": matchup.team_a if matchup else None,
            "team_b": matchup.team_b if matchup else None,
            "commence_time": market.commence_time.isoformat() if market.commence_time else None,
            "external_id": market.external_id,
        })


async def _phase1_pass1_ticker_scan(
    session, stats: dict, now: datetime,
    polymarket_backfill_queue: list, _time_remaining,
) -> set[int]:
    """Phase 1 Pass 1: scan Kalshi markets with known game ticker patterns."""
    from app.models.models import FuturesMarket

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
        .order_by(FuturesMarket.updated_at.desc())
    )
    ticker_markets = ticker_result.scalars().all()
    stats["funnel"]["ticker_scan_count"] = len(ticker_markets)

    processed_ids = set()
    for market in ticker_markets:
        if _time_remaining() < 120:
            logger.info("Phase 1 Pass 1 time budget exhausted after %d/%d ticker markets",
                        stats["markets_scanned"], len(ticker_markets))
            break
        processed_ids.add(market.id)
        stats["markets_scanned"] += 1
        stats["funnel"]["game_level_detected"] += 1

        matchup = extract_matchup_with_ticker_fallback(
            market.name, external_id=market.external_id,
        )

        ticker_sport = get_sport_prefix_from_ticker(market.external_id)
        if ticker_sport:
            stats["funnel"].setdefault("sport_key_extracted", 0)
            stats["funnel"]["sport_key_extracted"] += 1
        else:
            stats["funnel"].setdefault("sport_key_extraction_failed", 0)
            stats["funnel"]["sport_key_extraction_failed"] += 1

        ticker_game_date = extract_game_date_from_ticker(market.external_id)

        if matchup:
            matched_event = await _find_matching_event(
                session, matchup, market, now,
                game_date_override=ticker_game_date,
            )
            if matched_event and matchup.format_type == "ticker_parsed":
                stats["funnel"].setdefault("ticker_abbrev_linked", 0)
                stats["funnel"]["ticker_abbrev_linked"] += 1
        else:
            matched_event = await _find_event_by_sport_and_time(
                session, market, now,
                game_date_override=ticker_game_date,
            )
            if matched_event:
                stats["funnel"].setdefault("sport_time_fallback_linked", 0)
                stats["funnel"]["sport_time_fallback_linked"] += 1

        try:
            await _try_link_market(
                session, market, matchup, matched_event, stats,
                ticker_game_date, now, polymarket_backfill_queue,
            )
        except Exception as e:
            if "deadlock" in str(e).lower():
                stats["funnel"].setdefault("phase1_deadlocks", 0)
                stats["funnel"]["phase1_deadlocks"] += 1
            else:
                stats["errors"].append(f"pass1 market {market.id}: {str(e)[:100]}")
            try:
                await session.rollback()
            except Exception:
                pass

    return processed_ids


async def _phase1_pass2_general_scan(
    session, stats: dict, now: datetime, limit: int,
    processed_ids: set[int], polymarket_backfill_queue: list,
    _time_remaining,
) -> None:
    """Phase 1 Pass 2: scan non-ticker game markets (Polymarket + edge cases)."""
    from app.models.models import FuturesMarket

    _matchup_base_where = [
        FuturesMarket.source.in_(["kalshi", "polymarket"]),
        FuturesMarket.event_id.is_(None),
        FuturesMarket.status == "open",
    ]
    _matchup_name_filter = or_(
        FuturesMarket.name.ilike("% vs.%"),
        FuturesMarket.name.ilike("% vs %"),
        FuturesMarket.name.ilike("% – %"),
    )

    matchup_result = await session.execute(
        select(FuturesMarket)
        .where(*_matchup_base_where, _matchup_name_filter)
        .order_by(FuturesMarket.updated_at.desc())
        .limit(limit)
    )
    matchup_markets = matchup_result.scalars().all()

    remaining_budget = max(0, limit // 5)
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
    stats["funnel"]["general_scan_count"] = len(unlinked_markets)
    stats["funnel"]["matchup_scan_count"] = len(matchup_markets)
    stats["funnel"]["remaining_scan_count"] = len(remaining_markets)

    for market in unlinked_markets:
        if _time_remaining() < 120:
            logger.info("Phase 1 Pass 2 time budget exhausted after %d markets scanned",
                        stats["markets_scanned"])
            break
        if market.id in processed_ids:
            continue

        stats["markets_scanned"] += 1

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

        matchup = extract_matchup_with_ticker_fallback(
            market.name, external_id=market.external_id,
        )
        if not matchup:
            stats["funnel"]["no_matchup_extracted"] += 1
            continue

        stats["funnel"]["game_level_detected"] += 1
        pass2_game_date = (
            extract_game_date_from_ticker(market.external_id)
            if market.source == "kalshi" else None
        )

        matched_event = await _find_matching_event(
            session, matchup, market, now,
            game_date_override=pass2_game_date,
        )

        try:
            await _try_link_market(
                session, market, matchup, matched_event, stats,
                pass2_game_date, now, polymarket_backfill_queue,
            )
        except Exception as e:
            if "deadlock" in str(e).lower():
                stats["funnel"].setdefault("phase1_deadlocks", 0)
                stats["funnel"]["phase1_deadlocks"] += 1
            else:
                stats["errors"].append(f"pass2 market {market.id}: {str(e)[:100]}")
            try:
                await session.rollback()
            except Exception:
                pass


async def _relink_collapsed_game_markets(session) -> int:
    """#944: re-link Kalshi multi-game-series GAME markets that collapsed onto
    the LAST game's event.

    Kalshi ``commence_time`` is the resolution/close date (gotcha #14), so every
    game in a series shares one commence_time and the registry's structured
    match collapses all of that series' game markets onto the last game's event
    (e.g. 7 MIN-COL ``KXNHLSPREAD`` games all linked to the single May-14 event).
    The real game date lives in the TICKER (``KXNHLSPREAD-26MAY03MINCOL`` ->
    May 3); the currently-linked event already has the correct TEAMS (right
    matchup, wrong date), so we find the event with the same team-set — either
    home/away orientation, since Kalshi ticker order differs from our home/away
    (gotchas #16/#32) — on the ticker date and move ``event_id`` +
    ``commence_time`` there. Completed/closed events are eligible (gotcha #32),
    closest-by-ticker-date tiebreaker.

    Idempotent + write-on-change (so this ALSO serves as the forward-fix on each
    matching run — cheap no-op once clean). It moves ONLY ``event_id`` and the
    derived ``commence_time`` — it NEVER touches ``is_winner`` /
    ``calibration_probability`` (those live on futures_outcomes; the stored
    Kalshi settlements are correct, only the link was wrong — gotcha #21).
    Bounded to the game-market cohort (no broad in-memory pull, gotcha #899).
    """
    try:
        r = await session.execute(text(r"""
            WITH mislinked AS (
                SELECT fm.id AS mid, fm.event_id AS cur_eid,
                       to_date(substring(fm.external_id from '^KX[A-Z]+-(\d{2}[A-Z]{3}\d{2})'),'YYMONDD') AS tdate,
                       cur.home_team_name AS h, cur.away_team_name AS a
                FROM futures_markets fm
                JOIN events cur ON cur.id = fm.event_id
                WHERE fm.source = 'kalshi'
                  AND fm.external_id ~ '^KX(NHL|NBA|MLB)(SPREAD|TOTAL|GAME|MONEYLINE)'
                  AND substring(fm.external_id from '^KX[A-Z]+-(\d{2}[A-Z]{3}\d{2})') IS NOT NULL
                  AND ABS(cur.commence_time::date - to_date(substring(fm.external_id from '^KX[A-Z]+-(\d{2}[A-Z]{3}\d{2})'),'YYMONDD')) > 1
            )
            UPDATE futures_markets fm
            SET event_id = tgt.id, commence_time = tgt.commence_time, updated_at = NOW()
            FROM mislinked ml
            JOIN LATERAL (
                SELECT e2.id, e2.commence_time
                FROM events e2
                WHERE ((e2.home_team_name = ml.h AND e2.away_team_name = ml.a)
                    OR (e2.home_team_name = ml.a AND e2.away_team_name = ml.h))
                  AND e2.commence_time::date BETWEEN ml.tdate - 1 AND ml.tdate + 1
                  AND e2.id <> ml.cur_eid
                  AND e2.status IN ('scheduled','live','completed','closed')
                ORDER BY ABS(e2.commence_time::date - ml.tdate), e2.id
                LIMIT 1
            ) tgt ON true
            WHERE fm.id = ml.mid AND fm.event_id <> tgt.id
        """))
        n = r.rowcount or 0
        await session.commit()
        if n:
            logger.info(
                "Relink collapsed game markets (#944): moved %d markets to correct-date events", n
            )
        return n
    except Exception as e:
        logger.error("Relink collapsed game markets error: %s", e)
        return 0


async def _phase15_revalidate(
    session, stats: dict, now: datetime, _time_remaining,
) -> None:
    """Phase 1.5: fix stale and mislinked markets."""
    from app.models.models import FuturesMarket, Event, WinProbSnapshot

    stats["funnel"].setdefault("stale_relinked", 0)
    stats["funnel"].setdefault("mislink_fixed", 0)
    stats["funnel"].setdefault("phase15_skipped_budget", False)
    stats["funnel"].setdefault("phase15_checked", 0)

    if _time_remaining() < 120:
        logger.info("Skipping Phase 1.5 — only %.0fs remaining", _time_remaining())
        stats["funnel"]["phase15_skipped_budget"] = True
        return

    all_linked_result = await session.execute(
        select(FuturesMarket, Event)
        .join(Event, FuturesMarket.event_id == Event.id)
        .where(
            FuturesMarket.source.in_(["kalshi", "polymarket"]),
            FuturesMarket.event_id.isnot(None),
            FuturesMarket.status == "open",
        )
        .order_by(
            case(
                (Event.status.in_(["completed", "closed"]), 0),
                (Event.external_id.is_(None), 1),
                else_=2,
            ),
            FuturesMarket.updated_at.desc(),
        )
        .limit(1000)
    )
    all_linked_rows = all_linked_result.all()

    for market, linked_event in all_linked_rows:
        if _time_remaining() < 60:
            logger.info("Phase 1.5 time budget exhausted after %d/%d markets",
                        stats["funnel"]["phase15_checked"], len(all_linked_rows))
            break
        stats["funnel"]["phase15_checked"] += 1
        try:
            # Backfill sport_id from event if missing
            if market.sport_id is None and linked_event.sport_id:
                market.sport_id = linked_event.sport_id
                stats["funnel"].setdefault("sport_id_backfilled", 0)
                stats["funnel"]["sport_id_backfilled"] += 1

            ticker_cat = _derive_sport_category(market.external_id)
            if ticker_cat and market.llm_sport_category != ticker_cat:
                market.llm_sport_category = ticker_cat
                stats["funnel"].setdefault("sport_category_fixed", 0)
                stats["funnel"]["sport_category_fixed"] += 1

            if not is_game_level_market(
                market.name, market.category, external_id=market.external_id,
            ):
                continue

            matchup = extract_matchup_with_ticker_fallback(
                market.name, external_id=market.external_id,
            )
            if not matchup or not matchup.team_b:
                continue

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
            is_auto_created = (
                linked_event.external_id
                and str(linked_event.external_id).startswith("pm_")
            )

            # Cross-sport mislinkage detection: if the market's sport (from
            # ticker or llm_sport_category) doesn't match the event's sport,
            # treat it as a mislink even if team names match. This catches
            # cases like baseball "Royals" linked to cricket "Rajasthan Royals".
            sport_mismatch = False
            market_sport = get_sport_prefix_from_ticker(market.external_id) if market.external_id else None
            if not market_sport and market.llm_sport_category:
                market_sport = _SPORT_CATEGORY_TO_KEY_PREFIX.get(market.llm_sport_category)
            if market_sport and linked_event.sport_id:
                from app.models.models import Sport as _Sport
                event_sport_result = await session.execute(
                    select(_Sport.key).where(_Sport.id == linked_event.sport_id)
                )
                event_sport_key = event_sport_result.scalar_one_or_none()
                if event_sport_key and not event_sport_key.startswith(market_sport):
                    sport_mismatch = True
                    logger.info(
                        "Cross-sport mislinkage detected: %s market '%s' (sport=%s) "
                        "linked to %s event %d",
                        market.source, market.name, market_sport,
                        event_sport_key, linked_event.id,
                    )

            if teams_match and not is_finished and not is_auto_created and not sport_mismatch:
                continue

            reason = (
                "auto_created" if is_auto_created
                else "cross_sport" if sport_mismatch
                else "mislinked" if not teams_match
                else "completed"
            )
            ticker_game_date = (
                extract_game_date_from_ticker(market.external_id)
                if market.source == "kalshi" else None
            )

            better_match = await _find_matching_event(
                session, matchup, market, now,
                game_date_override=ticker_game_date,
            )

            if better_match and better_match["event_id"] != linked_event.id:
                logger.info(
                    "Re-linking %s '%s' from %s event %d -> event %d",
                    market.source, market.name, reason,
                    linked_event.id, better_match["event_id"],
                )
                if is_auto_created or not teams_match or sport_mismatch:
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
                elif not teams_match or sport_mismatch:
                    stats["funnel"]["mislink_fixed"] += 1
                else:
                    stats["funnel"]["stale_relinked"] += 1
            elif is_auto_created:
                pass
            elif not teams_match or sport_mismatch:
                logger.info(
                    "Unlinking %s '%s' from mismatched event %d — no better match (reason=%s)",
                    market.source, market.name, linked_event.id, reason,
                )
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
        "funnel": {
            "total_unlinked": 0,
            "not_game_level": 0,
            "no_matchup_extracted": 0,
            "game_level_detected": 0,
            "no_event_found": 0,
            "linked": 0,
            "sample_game_level_no_event": [],
            "sample_not_game_level": [],
        },
    }

    import time as _time
    _task_start = _time.monotonic()
    _TIME_BUDGET_SECONDS = 780

    def _time_remaining() -> float:
        return _TIME_BUDGET_SECONDS - (_time.monotonic() - _task_start)

    now = datetime.now(timezone.utc)
    polymarket_backfill_queue = []

    async with get_task_session() as session:
        # Phase 1, Pass 1: Kalshi ticker scan
        logger.info("Phase 1 starting — %.0fs budget remaining", _time_remaining())
        processed_ids = await _phase1_pass1_ticker_scan(
            session, stats, now, polymarket_backfill_queue, _time_remaining,
        )

        # Phase 1, Pass 2: General scan
        stats["funnel"]["total_unlinked"] = (
            stats["funnel"].get("ticker_scan_count", 0)
        )
        await _phase1_pass2_general_scan(
            session, stats, now, limit, processed_ids,
            polymarket_backfill_queue, _time_remaining,
        )
        stats["funnel"]["total_unlinked"] += stats["funnel"].get("general_scan_count", 0)

        # Phase 1.5: Re-validate linked markets
        logger.info("Phase 1 done (%d scanned, %d linked) — %.0fs remaining",
                    stats["markets_scanned"], stats["newly_linked"], _time_remaining())
        await _phase15_revalidate(session, stats, now, _time_remaining)

        await session.commit()

        # #944: correct Kalshi game markets that collapsed onto the last game's
        # event (commence_time = resolution date). Idempotent + write-on-change,
        # so this is both the forward-fix and the one-shot historical relink.
        stats["funnel"]["game_markets_relinked"] = await _relink_collapsed_game_markets(session)

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
                    or_(
                        Event.status.in_(["scheduled", "live"]),
                        and_(
                            Event.status.in_(["completed", "closed"]),
                            Event.commence_time >= now - timedelta(hours=24),
                        ),
                    ),
                )
            )
            linked_rows = linked_result.all()

        # DEDUP: Kalshi creates separate binary markets per team outcome
        # (e.g., "Celtics win?" and "76ers win?" for the same game). If both
        # are linked to the same event, we want to AVERAGE their implied
        # home probabilities to cancel out vig. Pick a primary market for
        # processing (matchup extraction, ticker validation), and store all
        # sibling markets for probability averaging.
        linked_refs = [
            _LinkedMarketRef(
                market_id=market.id,
                source=market.source,
                external_id=market.external_id,
                name=market.name,
                event_id=event.id,
                event_commence_time=event.commence_time,
                home_team_name=event.home_team_name,
                away_team_name=event.away_team_name,
            )
            for market, event in linked_rows
        ]

        all_per_event_source: dict[tuple[int, str], list[_LinkedMarketRef]] = {}
        for market_ref in linked_refs:
            key = (market_ref.event_id, market_ref.source)
            if key not in all_per_event_source:
                all_per_event_source[key] = []
            all_per_event_source[key].append(market_ref)

        # ── Wrong-game detection: unlink Kalshi game markets whose ticker
        # date is far from the event's commence_time. Only for traditional
        # sports (NBA/NHL/MLB/NFL) where each game is a distinct event.
        # NOT for esports — tournament events legitimately span multiple days.
        _WRONG_GAME_PREFIXES = frozenset({
            "kxnbagame", "kxnhlgame", "kxmlbgame", "kxnflgame",
            "kxwnbagame", "kxmlsgame", "kxsoccergame", "kxsocgame",
        })
        stats["funnel"].setdefault("phase2_multi_game_unlinked", 0)
        for key, group in list(all_per_event_source.items()):
            if key[1] != "kalshi" or not group:
                continue

            ev_ref = group[0]
            if not ev_ref.event_commence_time:
                continue
            ec = ev_ref.event_commence_time if ev_ref.event_commence_time.tzinfo else ev_ref.event_commence_time.replace(tzinfo=timezone.utc)

            for m in list(group):
                ext = (m.external_id or "").lower()
                prefix = ext.split("-")[0] if "-" in ext else ext
                if prefix not in _WRONG_GAME_PREFIXES:
                    continue
                td = extract_game_date_from_ticker(m.external_id)
                if not td:
                    continue
                d = td if td.tzinfo else td.replace(tzinfo=timezone.utc)
                diff_hours = abs((d - ec).total_seconds()) / 3600
                if diff_hours > 30:
                    logger.warning(
                        "Phase 2 wrong-game unlink: %s (date=%s) is %.0fh from event %d (date=%s) — unlinking",
                        m.external_id, d.date(), diff_hours, ev_ref.event_id, ec.date(),
                    )
                    await session.execute(
                        update(FuturesMarket)
                        .where(FuturesMarket.id == m.market_id)
                        .values(event_id=None)
                    )
                    stats["funnel"]["phase2_multi_game_unlinked"] += 1
                    group[:] = [gm for gm in group if gm.market_id != m.market_id]

            await session.commit()

        # Pick the primary market per group: prefer game-winner, then lowest id.
        # Without this, a prop market with a lower id shadows the game-winner
        # and no win_prob_snapshots are written for Kalshi.
        best_per_event_source: dict[tuple[int, str], _LinkedMarketRef] = {}
        for key, group in all_per_event_source.items():
            if not group:
                continue  # Group emptied by multi-game unlink
            primary = group[0]
            for market_ref in group[1:]:
                if market_ref.is_game_winner and not primary.is_game_winner:
                    primary = market_ref
                elif primary.is_game_winner == market_ref.is_game_winner and market_ref.market_id < primary.market_id:
                    primary = market_ref
            best_per_event_source[key] = primary

        stats["phase2_markets_raw"] = len(linked_rows)
        stats["phase2_markets_deduped"] = len(best_per_event_source)

        phase2_processed = 0
        phase2_skipped_not_ml = 0
        for market in best_per_event_source.values():
            if _time_remaining() < 60:
                logger.info("Phase 2 time budget exhausted after %d/%d markets", phase2_processed, len(linked_rows))
                break
            phase2_processed += 1
            try:
                # Only write win_prob_snapshots for moneyline/game-winner
                # markets. Props (spread, total, player stats, overtime,
                # half winner) are correctly linked for display but should
                # not contribute to the probability time-series.
                if market.source == "kalshi" and market.external_id:
                    if not feeds_win_prob_blend(market.external_id):
                        phase2_skipped_not_ml += 1
                        continue

                    # Validate ticker date matches event date. Colorado plays
                    # Cincinnati on Apr 28 AND Apr 29 — both games' markets
                    # match by team name. If the ticker date doesn't match the
                    # event's commence_time, this market is linked to the wrong
                    # event. Unlink it rather than writing bad data.
                    #
                    # Combat fights are exempt: they are disambiguated by fighter
                    # names (no same-card double-header), and their date-only
                    # ticker (e.g. 26JUL11) legitimately sits up to ~28h from the
                    # event's UTC commence (gotcha #14 — Kalshi close-time ≠ start),
                    # which the ±18h date-only threshold would wrongly unlink.
                    ticker_date = extract_game_date_from_ticker(market.external_id)
                    if (
                        ticker_date
                        and market.event_commence_time
                        and not is_combat_fight_ticker(market.external_id)
                    ):
                        _td = ticker_date if ticker_date.tzinfo else ticker_date.replace(tzinfo=timezone.utc)
                        _ec = market.event_commence_time if market.event_commence_time.tzinfo else market.event_commence_time.replace(tzinfo=timezone.utc)
                        # Use tight threshold when HHMM was parsed (non-midnight),
                        # loose threshold for date-only tickers.
                        # ±3h separates double-headers (~5h apart); ±18h for date-only.
                        _max_diff = 3 * 3600 if (_td.hour or _td.minute) else 18 * 3600
                        if abs((_td - _ec).total_seconds()) > _max_diff:
                            logger.warning(
                                "Phase 2 date mismatch: %s ticker=%s event=%s (diff=%.0fh) — unlinking",
                                market.external_id, _td.date(), _ec.date(),
                                abs((_td - _ec).total_seconds()) / 3600,
                            )
                            await session.execute(
                                update(FuturesMarket)
                                .where(FuturesMarket.id == market.market_id)
                                .values(event_id=None)
                            )
                            await session.commit()
                            stats["funnel"].setdefault("phase2_date_unlinked", 0)
                            stats["funnel"]["phase2_date_unlinked"] += 1
                            continue

                matchup = extract_matchup_with_ticker_fallback(
                    market.name, external_id=market.external_id,
                )
                if not matchup:
                    continue

                outcome_result = await session.execute(
                    select(FuturesOutcome)
                    .where(FuturesOutcome.market_id == market.market_id)
                    .order_by(FuturesOutcome.rank)
                )
                all_outcomes = outcome_result.scalars().all()
                if not all_outcomes:
                    continue

                ml_result = find_moneyline_outcome(
                    all_outcomes, matchup,
                    market.home_team_name, market.away_team_name,
                )
                if not ml_result:
                    continue

                outcome, yes_is_home = ml_result
                yes_prob = float(outcome.current_probability)

                if yes_is_home:
                    home_prob = yes_prob
                else:
                    home_prob = 1.0 - yes_prob

                # Devig: if dual markets exist (e.g., "Celtics win?" +
                # "76ers win?"), average both sides to cancel vig.
                es_key = (market.event_id, market.source)
                siblings = all_per_event_source.get(es_key, [])
                if len(siblings) == 2:
                    home_probs = [home_prob]
                    for sib_market in siblings:
                        if sib_market.market_id == market.market_id:
                            continue
                        sib_outcomes_result = await session.execute(
                            select(FuturesOutcome)
                            .where(FuturesOutcome.market_id == sib_market.market_id)
                            .order_by(FuturesOutcome.rank)
                        )
                        sib_outcomes = sib_outcomes_result.scalars().all()
                        if sib_outcomes:
                            sib_ml = find_moneyline_outcome(
                                sib_outcomes, matchup,
                                market.home_team_name, market.away_team_name,
                            )
                            if sib_ml:
                                sib_outcome, sib_yes_is_home = sib_ml
                                sib_prob = float(sib_outcome.current_probability)
                                sib_home = sib_prob if sib_yes_is_home else 1.0 - sib_prob
                                home_probs.append(sib_home)
                    if len(home_probs) == 2:
                        home_prob = sum(home_probs) / 2.0

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
                        "market_id": market.market_id,
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
                    await session.rollback()
                    stats["errors"].append(f"market {market.market_id}: {err_str[:100]}")
                continue

    stats["phase2_skipped_not_moneyline"] = phase2_skipped_not_ml

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
    # the game), so we use the ticker-extracted game date when available.
    # When the ticker date includes HHMM (non-midnight), use a tight ±3h
    # window. This correctly distinguishes double-header games (same teams,
    # same day, ~5h apart — e.g., 1:40 PM and 7:10 PM). Without HHMM,
    # use an asymmetric window: -6h to +30h. Ticker dates are US calendar
    # dates stored as UTC midnight, but US evening games (7-11 PM ET) fall
    # on the NEXT UTC day (00:00-04:00 UTC). A symmetric ±18h missed these.
    reference_time = game_date_override or market.commence_time or now
    if game_date_override:
        has_time = game_date_override.hour != 0 or game_date_override.minute != 0
        if has_time:
            time_start = reference_time - timedelta(hours=3)
            time_end = reference_time + timedelta(hours=3)
        else:
            time_start = reference_time - timedelta(hours=6)
            time_end = reference_time + timedelta(hours=30)
    elif market.source == "kalshi":
        time_delta = timedelta(days=7)
        time_start = reference_time - time_delta
        time_end = reference_time + time_delta
    else:
        time_delta = MAX_TIME_DELTA
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

    # Compute sport prefix once (depends only on market, not on candidates).
    # Ticker-derived prefix (Kalshi) is most reliable. Falls back to
    # llm_sport_category (Polymarket and Kalshi without parseable ticker).
    ticker_sport_prefix = get_sport_prefix_from_ticker(market.external_id) if market.external_id else None
    sport_prefix = ticker_sport_prefix
    if not sport_prefix and market.llm_sport_category:
        sport_prefix = _SPORT_CATEGORY_TO_KEY_PREFIX.get(market.llm_sport_category)

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

        # Prefer Odds API events (external_id set) over auto-created ones
        if event.external_id:
            score += 8

        # Sport validation: hard-reject events from the wrong sport.
        # Both ticker and llm_sport_category are hard rejects — city-name
        # collisions (Boston/New York) and generic team names (Royals/Indians)
        # cause cross-sport mismatches if we only use soft scoring.
        if sport_prefix and event.sport and event.sport.key:
            if not event.sport.key.startswith(sport_prefix):
                continue  # Wrong sport — skip this candidate
            score += 5  # Same sport confirmed
        elif not sport_prefix:
            score -= 5  # No sport validation — penalize to prefer validated matches

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

    # When we have no sport prefix (no ticker sport, no llm_sport_category),
    # require a higher confidence threshold to prevent cross-sport mismatches.
    # A score of 21 requires: both teams match (+10) + close time (+~10) +
    # scheduled (+3), preventing generic team names like "Royals" or "Indians"
    # from matching across cricket/baseball.
    if best_match and not sport_prefix and best_match.get("score", 0) < 21:
        logger.info(
            "Rejecting low-confidence match (score=%d, no sport prefix) for %s",
            best_match["score"], market.external_id,
        )
        return None

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

    if game_date_override:
        # Tight window when HHMM is available; wider for date-only tickers
        has_time = game_date_override.hour != 0 or game_date_override.minute != 0
        window_hours = 3 if has_time else 18
    elif market.source == "kalshi":
        window_hours = 48  # Kalshi commence_time is resolution date, very imprecise
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


async def _resolve_combat_opponent(session, external_id, known_fighter, sport_key):
    """Recover a combat bout's OPPONENT from the entity registry via the ticker.

    #175 Item 2 — the fighter-abbrev grammar fix. A UFC/boxing fight-winner
    market names only ONE competitor, so a matchup parsed from it degenerates to
    "Saint-Denis vs Saint-Denis". The ticker (``KXUFCFIGHT-26JUL11SAIPIM``)
    carries BOTH fighter abbrevs; given the one fighter we already know
    ("Benoit Saint-Denis"), the OTHER abbrev ("pim") resolves to the opponent
    ("Paddy Pimblett") against the seeded person registry (18.6K persons, surname
    aliases).

    Honest-unknown contract — the crux of the fix: it NEVER guesses and NEVER
    returns the known fighter again. It returns a name only when
      1. exactly one ticker abbrev is a surname-prefix of the known fighter (so we
         know which side is the opponent), AND
      2. the OTHER abbrev resolves to EXACTLY ONE distinct combat person whose
         surname it prefixes, who isn't the known fighter.
    Any ambiguity (0 or >1 matches, can't tell which side is known) -> None, so
    the caller creates no event rather than a duplicate-person degenerate.
    """
    from app.utils.prediction_market_matching import combat_fighter_abbrevs
    from app.utils.event_matcher import player_key

    abbrevs = combat_fighter_abbrevs(external_id)
    if not abbrevs:
        return None
    known_key = player_key(known_fighter)
    if not known_key:
        return None

    # Which abbrev is the known fighter, which is the opponent? Exactly one must
    # prefix the known surname — otherwise we can't tell the sides apart.
    a, b = abbrevs
    a_is_known = known_key.startswith(a)
    b_is_known = known_key.startswith(b)
    if a_is_known and not b_is_known:
        opp_abbrev = b
    elif b_is_known and not a_is_known:
        opp_abbrev = a
    else:
        return None  # ambiguous (neither or both prefix the known fighter)
    if len(opp_abbrev) < 2:
        return None

    # Resolve the opponent abbrev against the registry: a combat-sport person
    # whose surname starts with the abbrev, distinct from the known fighter.
    from sqlalchemy import func, select
    from app.models.models import Entity, EntityAlias
    from app.services.entity_registry import KIND_PERSON

    family = (sport_key or "").split("_")[0].lower()
    stmt = (
        select(func.distinct(Entity.canonical_name))
        .join(EntityAlias, EntityAlias.entity_id == Entity.id)
        .where(
            Entity.kind == KIND_PERSON,
            EntityAlias.alias_type == "common_name",  # the surname alias
            EntityAlias.alias_norm.like(f"{_escape_like(opp_abbrev)}%", escape="\\"),
        )
    )
    if family:
        stmt = stmt.where(func.lower(Entity.sport_key).like(f"{_escape_like(family)}%", escape="\\"))
    names = [
        n for n in (await session.execute(stmt.limit(5))).scalars().all()
        if player_key(n) != known_key
    ]
    if len(names) == 1:
        return names[0]
    return None  # 0 or ambiguous — honest unknown, no guess


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

    # Determine sport key from ticker or category
    sport_key = get_sport_prefix_from_ticker(market.external_id) if market.external_id else None

    # #175 Item 2 — combat degenerate guard. A fight-winner market names only ONE
    # competitor, so a matchup parsed from it degenerates to "Saint-Denis vs
    # Saint-Denis". Recover the real opponent from the ticker+registry; if we
    # can't (honest unknown), create NO event rather than a duplicate-person one.
    from app.utils.name_normalization import names_match as _names_match
    if team_a and (not team_b or _names_match(team_a, team_b)):
        opponent = await _resolve_combat_opponent(
            session, market.external_id, team_a, sport_key
        )
        if opponent and not _names_match(team_a, opponent):
            team_b = opponent
        else:
            logger.debug(
                "Skipping auto-create for '%s' — degenerate combat matchup "
                "(one fighter, opponent unresolved): %s",
                market.name, team_a,
            )
            return None

    if not team_a or not team_b:
        return None
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
    try:
        event, was_created = await find_or_create_event(session, identity)
    except ValueError as e:
        logger.warning(
            "Cannot auto-create event for '%s' — %s",
            market.name, e,
        )
        return None

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
        FuturesMarket, FuturesOddsSnapshot, FuturesOutcome, Event, WinProbSnapshot,
    )
    from app.tasks.snapshots import _create_or_update_win_prob_snapshot
    from app.utils.odds_math import probability_to_american

    stats = {
        "live_events": 0,
        "linked_markets": 0,
        "kalshi_fetched": 0,
        "polymarket_fetched": 0,
        "outcomes_updated": 0,
        "futures_snapshots_written": 0,
        "snapshots_written": 0,
        "snapshots_deduped": 0,
        "pregame_marks_written": 0,
        "errors": [],
    }

    now = datetime.now(timezone.utc)

    async with get_task_session() as session:
        # Find linked prediction markets where the event is live OR starting
        # within 3 hours. Pre-game prop prices undergo price discovery in the
        # hours before game time — polling only live events misses this entirely
        # and leaves props with 1-2 snapshots from the 2h full-poll interval.
        from datetime import timedelta
        upcoming_cutoff = now + timedelta(hours=3)
        result = await session.execute(
            select(FuturesMarket, Event)
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.event_id.isnot(None),
                or_(
                    Event.status == "live",
                    and_(
                        Event.status == "scheduled",
                        Event.commence_time.isnot(None),
                        Event.commence_time <= upcoming_cutoff,
                        Event.commence_time > now,
                    ),
                ),
            )
        )
        rows = result.all()

        if not rows:
            logger.debug("No live or upcoming linked prediction markets to poll")
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

                            # Write FuturesOddsSnapshot for chart history
                            await session.execute(
                                pg_insert(FuturesOddsSnapshot).values(
                                    outcome_id=outcome.id,
                                    bookmaker="kalshi",
                                    probability=prob,
                                    american_odds=american,
                                    yes_bid=yes_bid,
                                    yes_ask=yes_ask,
                                    last_price=last_price,
                                    captured_at=now,
                                )
                            )
                            stats["futures_snapshots_written"] += 1

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

                            # Write FuturesOddsSnapshot for chart history
                            best_bid_val = float(best_bid) if best_bid is not None else None
                            best_ask_val = float(best_ask) if best_ask is not None else None
                            ltp_val = float(ltp) if ltp is not None else None
                            await session.execute(
                                pg_insert(FuturesOddsSnapshot).values(
                                    outcome_id=outcome.id,
                                    bookmaker="polymarket",
                                    probability=prob,
                                    american_odds=american,
                                    yes_bid=best_bid_val,
                                    yes_ask=best_ask_val,
                                    last_price=ltp_val,
                                    captured_at=now,
                                )
                            )
                            stats["futures_snapshots_written"] += 1

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
        # (e.g., "Celtics win?" and "76ers win?" for the same game). Both
        # are linked to the same event. We pick a primary market for
        # processing but AVERAGE both sides to cancel vig when computing
        # the home probability.
        all_per_event_source_live: dict[tuple[int, str], list[tuple]] = {}
        for market, event in rows:
            key = (event.id, market.source)
            if key not in all_per_event_source_live:
                all_per_event_source_live[key] = []
            all_per_event_source_live[key].append((market, event))

        def _is_game_winner_market(m) -> bool:
            if m.source != "kalshi" or not m.external_id:
                return False
            return feeds_win_prob_blend(m.external_id)

        best_per_event_source: dict[tuple[int, str], tuple] = {}
        for key, group in all_per_event_source_live.items():
            primary = group[0]
            for market, event in group[1:]:
                pri_is_gw = _is_game_winner_market(primary[0])
                cur_is_gw = _is_game_winner_market(market)
                if cur_is_gw and not pri_is_gw:
                    primary = (market, event)
                elif pri_is_gw == cur_is_gw and market.id < primary[0].id:
                    primary = (market, event)
            best_per_event_source[key] = primary

        for market, event in best_per_event_source.values():
            try:
                # Only write snapshots for moneyline/game-winner markets
                # (team-sport …game + combat fight winners; props excluded).
                if market.source == "kalshi" and market.external_id:
                    if not feeds_win_prob_blend(market.external_id):
                        continue

                # Uses ticker fallback for generic-named Kalshi markets
                matchup = extract_matchup_with_ticker_fallback(
                    market.name, external_id=market.external_id,
                )
                if not matchup:
                    continue

                # Use batch-loaded outcomes (loaded at line ~1346)
                all_outcomes = sorted(
                    outcomes_by_market.get(market.id, []),
                    key=lambda o: o.rank or 999,
                )
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

                # Devig: average both dual markets to cancel vig
                es_key = (event.id, market.source)
                siblings = all_per_event_source_live.get(es_key, [])
                if len(siblings) == 2:
                    home_probs = [home_prob]
                    for sib_market, sib_event in siblings:
                        if sib_market.id == market.id:
                            continue
                        sib_outcomes = sorted(
                            outcomes_by_market.get(sib_market.id, []),
                            key=lambda o: o.rank or 999,
                        )
                        if sib_outcomes:
                            sib_ml = find_moneyline_outcome(
                                sib_outcomes, matchup,
                                event.home_team_name, event.away_team_name,
                            )
                            if sib_ml:
                                sib_outcome, sib_yes_is_home = sib_ml
                                sib_prob = float(sib_outcome.current_probability)
                                sib_home = sib_prob if sib_yes_is_home else 1.0 - sib_prob
                                home_probs.append(sib_home)
                    if len(home_probs) == 2:
                        home_prob = sum(home_probs) / 2.0

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

        # ── #195: pregame-mark pinning (THE SCRIPT baseline for props) ────
        # At/just-before commence, snapshot each linked market's current
        # per-outcome probabilities into market_metadata["pregame_mark"], the
        # divergence baseline the event page renders as THE SCRIPT (pregame
        # expectation) vs THE DIVERGENCE (live movement). Piggybacks on the
        # existing poll loop — no new scan (the rows/outcomes are already loaded
        # and freshly re-priced above). Idempotent: the first mark per market is
        # captured and never overwritten (Python skip + a NOT jsonb_exists SQL
        # guard for the concurrent-poll case). Core JSONB merge (gotcha #4) via
        # CAST to dodge the asyncpg ':param::jsonb' bind trap, preserving any
        # existing keys (shape, discover_llm, ...).
        pregame_cutoff = now + timedelta(minutes=_PREGAME_MARK_LEAD_MINUTES)
        for market, event in rows:
            commence = event.commence_time
            if commence is None:
                continue
            # Fire once the game is inside the final lead window or has started —
            # this captures the settled pregame consensus, not a stale opening.
            if commence > pregame_cutoff:
                continue
            existing_meta = market.market_metadata or {}
            if isinstance(existing_meta, dict) and "pregame_mark" in existing_meta:
                continue
            outcome_probs = {}
            for o in outcomes_by_market.get(market.id, []):
                if o.current_probability is not None:
                    outcome_probs[str(o.id)] = round(float(o.current_probability), 6)
            if not outcome_probs:
                continue
            mark_payload = {
                "captured_at": now.isoformat(),
                "commence_time": commence.isoformat(),
                "outcomes": outcome_probs,
            }
            try:
                await session.execute(
                    text(
                        "UPDATE futures_markets SET market_metadata = "
                        "COALESCE(market_metadata, '{}'::jsonb) "
                        "|| jsonb_build_object('pregame_mark', CAST(:mark AS jsonb)) "
                        "WHERE id = :id "
                        "AND NOT jsonb_exists("
                        "COALESCE(market_metadata, '{}'::jsonb), 'pregame_mark')"
                    ),
                    {"mark": json.dumps(mark_payload), "id": market.id},
                )
                stats["pregame_marks_written"] += 1
            except Exception as e:
                stats["errors"].append(f"pregame_mark_{market.id}: {str(e)[:100]}")

        await session.commit()

    logger.info(
        "Live prediction market poll: events=%d, markets=%d, "
        "kalshi=%d, polymarket=%d, outcomes=%d, "
        "futures_snaps=%d, wp_snaps=%d (deduped=%d)",
        stats["live_events"], stats["linked_markets"],
        stats["kalshi_fetched"], stats["polymarket_fetched"],
        stats["outcomes_updated"], stats["futures_snapshots_written"],
        stats["snapshots_written"], stats["snapshots_deduped"],
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


async def _backfill_historical_links(batch_size: int = 100):
    """Link past-game Kalshi AND Polymarket markets to their (now closed) events.

    The live matching task skips closed/completed events (past_cutoff filter).
    This backfill removes that filter to link markets for games that already
    happened. Idempotent: marks failed attempts in market_metadata so we
    don't re-check the same markets every run.

    Handles both sources:
    - Kalshi: ticker-based game detection + ticker date for time window
    - Polymarket: name-based game detection + commence_time for time window
    """
    from app.models.models import FuturesMarket, Event
    from sqlalchemy import text as _text, update as _update

    stats = {
        "scanned": 0, "linked": 0, "no_match": 0, "errors": [],
        "by_source": {"kalshi": {"scanned": 0, "linked": 0}, "polymarket": {"scanned": 0, "linked": 0}},
    }
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=48)

    async with get_task_session() as session:
        # ── Kalshi: ticker-prefix detection ──
        ticker_conditions = [
            func.lower(FuturesMarket.external_id).like(f"{p}%")
            for p in _KALSHI_GAME_TICKER_PREFIXES
        ]
        kalshi_result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source == "kalshi",
                FuturesMarket.event_id.is_(None),
                or_(*ticker_conditions),
                or_(
                    FuturesMarket.market_metadata.is_(None),
                    ~FuturesMarket.market_metadata.has_key("backfill_link_failed"),
                ),
                FuturesMarket.commence_time < cutoff,
            )
            .order_by(FuturesMarket.commence_time.asc())
            .limit(batch_size)
        )
        kalshi_markets = kalshi_result.scalars().all()

        # ── Polymarket: fetch candidates, filter through is_game_level_market() in Python ──
        _SUPPORTED_SPORT_CATS = [
            "basketball", "baseball", "hockey", "soccer", "football",
            "tennis", "mma", "rugby", "lacrosse", "cricket",
        ]
        poly_result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source == "polymarket",
                FuturesMarket.event_id.is_(None),
                FuturesMarket.llm_sport_category.in_(_SUPPORTED_SPORT_CATS),
                or_(
                    FuturesMarket.market_metadata.is_(None),
                    ~FuturesMarket.market_metadata.has_key("backfill_link_failed"),
                ),
                FuturesMarket.commence_time < cutoff,
            )
            .order_by(FuturesMarket.commence_time.asc())
            .limit(batch_size * 3)
        )
        poly_candidates = poly_result.scalars().all()
        poly_markets = [
            m for m in poly_candidates
            if is_game_level_market(m.name, m.category, external_id=m.external_id)
        ][:batch_size]

        all_markets = kalshi_markets + poly_markets

        for market in all_markets:
            stats["scanned"] += 1
            src = market.source
            stats["by_source"][src]["scanned"] += 1
            try:
                matchup = extract_matchup_with_ticker_fallback(
                    market.name, external_id=market.external_id,
                )
                if not matchup or not matchup.team_b:
                    await _mark_backfill_failed(session, market)
                    stats["no_match"] += 1
                    continue

                # Determine time reference: Kalshi uses ticker date, Polymarket uses commence_time
                if src == "kalshi":
                    ref_time = extract_game_date_from_ticker(market.external_id)
                    if not ref_time:
                        await _mark_backfill_failed(session, market)
                        stats["no_match"] += 1
                        continue
                    if ref_time.tzinfo is None:
                        ref_time = ref_time.replace(tzinfo=timezone.utc)
                else:
                    ref_time = market.commence_time
                    if not ref_time:
                        await _mark_backfill_failed(session, market)
                        stats["no_match"] += 1
                        continue
                    if ref_time.tzinfo is None:
                        ref_time = ref_time.replace(tzinfo=timezone.utc)

                matched = await _find_historical_event(
                    session, matchup, market, ref_time,
                )
                if matched:
                    eid = matched["event_id"]
                    await session.execute(
                        _update(FuturesMarket)
                        .where(FuturesMarket.id == market.id)
                        .values(event_id=eid)
                    )
                    stats["linked"] += 1
                    stats["by_source"][src]["linked"] += 1
                    logger.info(
                        "Backfill linked %s %s → event %d (%s vs %s)",
                        src, market.external_id or market.name[:40],
                        eid, matched["home_team"], matched["away_team"],
                    )
                    if market.group_id and src == "polymarket":
                        from sqlalchemy import text as _sql_text
                        await session.execute(_sql_text("""
                            UPDATE futures_markets
                            SET event_id = :eid
                            WHERE group_id = :gid
                              AND group_type = 'polymarket_sub_market'
                              AND (event_id IS NULL OR event_id != :eid)
                        """), {"eid": eid, "gid": market.group_id})
                else:
                    await _mark_backfill_failed(session, market)
                    stats["no_match"] += 1

                if stats["scanned"] % 20 == 0:
                    await session.commit()

            except Exception as e:
                logger.error("Backfill error for %s: %s", market.external_id or market.id, e)
                stats["errors"].append(str(e))

        await session.commit()

    logger.info(
        "Historical link backfill: scanned=%d linked=%d no_match=%d errors=%d",
        stats["scanned"], stats["linked"], stats["no_match"], len(stats["errors"]),
    )
    return stats


async def _mark_backfill_failed(session, market):
    """Mark a market as attempted-and-failed so we skip it next run."""
    from app.models.models import FuturesMarket
    from sqlalchemy import update

    meta = dict(market.market_metadata) if market.market_metadata else {}
    meta["backfill_link_failed"] = True
    await session.execute(
        update(FuturesMarket)
        .where(FuturesMarket.id == market.id)
        .values(market_metadata=meta)
    )


async def _find_historical_event(session, matchup, market, ref_time):
    """Like _find_matching_event but without status/past_cutoff filters.

    Args:
        ref_time: For Kalshi = ticker-extracted game date (precise).
                  For Polymarket = commence_time (approximate, wider window).
    """
    from app.models.models import Event

    teams_to_search = [matchup.team_a]
    if matchup.team_b:
        teams_to_search.append(matchup.team_b)

    ilike_conditions = []
    for team in teams_to_search:
        for search_term in _expand_team_search_terms(team):
            pattern = f"%{_escape_like(search_term)}%"
            ilike_conditions.append(Event.home_team_name.ilike(pattern))
            ilike_conditions.append(Event.away_team_name.ilike(pattern))

    if market.source == "kalshi":
        time_start = ref_time - timedelta(hours=6)
        time_end = ref_time + timedelta(hours=30)
    else:
        time_start = ref_time - timedelta(hours=48)
        time_end = ref_time + timedelta(hours=48)

    event_result = await session.execute(
        select(Event)
        .options(joinedload(Event.sport))
        .where(
            or_(*ilike_conditions),
            Event.commence_time.between(time_start, time_end),
        )
        .order_by(Event.commence_time)
        .limit(20)
    )
    candidates = event_result.scalars().unique().all()

    result = _score_candidates(candidates, matchup, market, ref_time, ref_time)
    if result and result.get("score", 0) < 15:
        logger.debug(
            "Backfill rejecting low-confidence match (score=%d) for %s",
            result["score"], market.external_id or market.name[:40],
        )
        return None
    return result
