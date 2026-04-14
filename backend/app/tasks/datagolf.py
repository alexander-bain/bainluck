"""
DataGolf prediction model polling tasks.

Two task implementations:
1. _poll_datagolf_markets() — hourly: schedule + pre-tournament preds → FuturesMarket/Outcome/Snapshot
2. _poll_datagolf_live() — every 5 min (Redis-gated): in-play probabilities + leaderboard metadata

Data flow:
  DataGolf /preds/in-play
    → FuturesMarket (source="datagolf", external_id="datagolf:pga:{event_id}:win")
      → FuturesOutcome (external_id="dg_{dg_id}", name="Scottie Scheffler")
        → FuturesOddsSnapshot (bookmaker="datagolf_model", probability=0.15)
    → FuturesMarket.market_metadata.leaderboard (pos, score, round, thru per player)
    → FuturesMarket.market_metadata.round_history (round transition timestamps)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

# Market types we create per tournament
MARKET_TYPES = [
    ("win", "championship"),
    ("top_5", "placement"),
    ("top_10", "placement"),
    ("top_20", "placement"),
    ("make_cut", "make_cut"),
]

# Redis key prefix for live tournament detection
LIVE_KEY_PREFIX = "bainluck:datagolf:live"

# Tours to poll — all tours that DataGolf covers
POLL_TOURS = ["pga", "euro", "kft", "opp", "alt"]


def _external_id(tour: str, event_id: str, market_type: str) -> str:
    """Build deterministic external_id for DataGolf FuturesMarket."""
    return f"datagolf:{tour}:{event_id}:{market_type}"


async def _poll_datagolf_markets() -> dict:
    """Hourly task: sync schedule + pre-tournament predictions."""
    from app.services.datagolf_api import DataGolfAPIService
    from app.models.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot

    service = DataGolfAPIService()
    stats = {"tours_polled": 0, "markets_upserted": 0, "outcomes_upserted": 0, "snapshots_written": 0, "debug": {}}

    try:
        async with get_task_session() as session:
            for tour in POLL_TOURS:
                try:
                    # 1. Fetch schedule
                    schedule = await service.get_schedule(tour=tour)
                    if not schedule:
                        logger.info("DataGolf: no schedule for tour=%s", tour)
                        stats["debug"][tour] = "no_schedule"
                        continue

                    # Find the current/next event (first non-completed event)
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    current_event = None
                    for t in schedule:
                        # Prefer status-based detection (API provides "completed" etc.)
                        if t.status and t.status != "completed":
                            current_event = t
                            break
                        # Fallback: check computed end_date
                        if t.end_date and t.end_date >= now_str:
                            current_event = t
                            break

                    if not current_event:
                        logger.info("DataGolf: no upcoming event for tour=%s", tour)
                        stats["debug"][tour] = f"no_upcoming_event (schedule_count={len(schedule)}, now={now_str})"
                        if schedule:
                            stats["debug"][f"{tour}_last_end_date"] = schedule[-1].end_date
                            stats["debug"][f"{tour}_first_start_date"] = schedule[0].start_date
                            # Sample first event for diagnosis
                            stats["debug"][f"{tour}_sample"] = {
                                "name": schedule[0].event_name,
                                "start": schedule[0].start_date,
                                "end": schedule[0].end_date,
                                "id": schedule[0].event_id,
                            }
                        continue

                    stats["debug"][f"{tour}_event"] = f"{current_event.event_name} ({current_event.event_id})"

                    # 2. Fetch pre-tournament predictions
                    players = await service.get_pre_tournament(tour=tour)
                    if not players:
                        logger.info("DataGolf: no pre-tournament data for tour=%s", tour)
                        stats["debug"][tour] = "no_pre_tournament_data"
                        continue

                    # 3. Upsert FuturesMarket + FuturesOutcome + Snapshot per market type
                    for market_type, category in MARKET_TYPES:
                        ext_id = _external_id(tour, current_event.event_id, market_type)
                        market_name = f"{current_event.event_name} - {_market_label(market_type)}"

                        # Upsert market
                        result = await session.execute(
                            select(FuturesMarket).where(
                                FuturesMarket.source == "datagolf",
                                FuturesMarket.external_id == ext_id,
                            )
                        )
                        market = result.scalar_one_or_none()

                        if not market:
                            market = FuturesMarket(
                                source="datagolf",
                                external_id=ext_id,
                                name=market_name,
                                category=category,
                                llm_sport_category="golf",
                                status="open",
                                mutually_exclusive=(market_type == "win"),
                            )
                            # Parse dates
                            if current_event.start_date:
                                try:
                                    market.commence_time = datetime.strptime(
                                        current_event.start_date, "%Y-%m-%d"
                                    ).replace(tzinfo=timezone.utc)
                                except ValueError:
                                    pass
                            if current_event.end_date:
                                try:
                                    market.resolution_date = datetime.strptime(
                                        current_event.end_date, "%Y-%m-%d"
                                    ).replace(tzinfo=timezone.utc)
                                except ValueError:
                                    pass
                            session.add(market)
                            await session.flush()
                        else:
                            market.name = market_name  # Update name if changed

                        stats["markets_upserted"] += 1

                        # Initialize metadata if needed
                        if not market.market_metadata:
                            market.market_metadata = {}

                        # Store event info in metadata
                        market.market_metadata = {
                            **market.market_metadata,
                            "datagolf_event_id": current_event.event_id,
                            "course": current_event.course,
                            "tour": tour,
                        }

                        # Upsert outcomes + snapshots
                        now = datetime.now(timezone.utc)
                        for player in players:
                            prob = _get_prob(player, market_type)
                            if prob is None:
                                continue

                            outcome_ext_id = f"dg_{player.dg_id}"

                            # Upsert outcome
                            out_result = await session.execute(
                                select(FuturesOutcome).where(
                                    FuturesOutcome.market_id == market.id,
                                    FuturesOutcome.external_id == outcome_ext_id,
                                )
                            )
                            outcome = out_result.scalar_one_or_none()

                            if not outcome:
                                outcome = FuturesOutcome(
                                    market_id=market.id,
                                    external_id=outcome_ext_id,
                                    name=player.player_name,
                                    current_probability=prob,
                                )
                                session.add(outcome)
                                await session.flush()
                            else:
                                outcome.name = player.player_name
                                outcome.current_probability = prob
                                outcome.last_updated = now

                            stats["outcomes_upserted"] += 1

                            # Write-time dedup: check if last snapshot has same value
                            last_snap = await session.execute(
                                select(FuturesOddsSnapshot)
                                .where(
                                    FuturesOddsSnapshot.outcome_id == outcome.id,
                                    FuturesOddsSnapshot.bookmaker == "datagolf_model",
                                )
                                .order_by(FuturesOddsSnapshot.captured_at.desc())
                                .limit(1)
                            )
                            existing_snap = last_snap.scalar_one_or_none()

                            if existing_snap and abs(float(existing_snap.probability) - prob) < 0.0001:
                                existing_snap.reading_count += 1
                                existing_snap.valid_until = now
                            else:
                                if existing_snap:
                                    existing_snap.valid_until = now
                                snap = FuturesOddsSnapshot(
                                    outcome_id=outcome.id,
                                    bookmaker="datagolf_model",
                                    probability=prob,
                                    captured_at=now,
                                    reading_count=1,
                                )
                                session.add(snap)
                                stats["snapshots_written"] += 1

                        # Null out stale outcomes: any outcome on this market
                        # that isn't in the fresh player set has withdrawn or
                        # was never in the field. Setting current_probability
                        # to None removes them from the aggregated response —
                        # the /golf route skips None outcomes. This is what
                        # prevents e.g. Anthony Kim from lingering in the
                        # Masters winner odds after DataGolf stops returning
                        # him.
                        fresh_ext_ids = {f"dg_{p.dg_id}" for p in players}
                        stale_result = await session.execute(
                            select(FuturesOutcome).where(
                                FuturesOutcome.market_id == market.id,
                                FuturesOutcome.current_probability.isnot(None),
                                ~FuturesOutcome.external_id.in_(fresh_ext_ids),
                            )
                        )
                        stale_nulled = 0
                        for stale in stale_result.scalars().all():
                            stale.current_probability = None
                            stale.last_updated = now
                            stale_nulled += 1
                        if stale_nulled:
                            logger.info(
                                "DataGolf pre-tournament: nulled %d stale outcomes on market %s",
                                stale_nulled, market.id,
                            )

                    stats["tours_polled"] += 1

                except Exception as e:
                    logger.error("DataGolf poll error for tour=%s: %s", tour, e)
                    stats["debug"][f"{tour}_error"] = str(e)[:300]
                    continue

    finally:
        await service.close()

    logger.info("DataGolf poll complete: %s", stats)
    return stats


async def _poll_datagolf_live() -> dict:
    """Every-5-min task: fetch in-play probabilities and update leaderboard metadata."""
    from app.services.datagolf_api import DataGolfAPIService
    from app.models.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
    from app.tasks.redis_state import get_redis_client

    service = DataGolfAPIService()
    stats = {"tours_polled": 0, "live_events": 0, "snapshots_written": 0, "skipped": 0}

    try:
        r = get_redis_client()

        async with get_task_session() as session:
            for tour in POLL_TOURS:
                try:
                    players = await service.get_in_play(tour=tour)
                    if not players:
                        # No live event — clear live flag
                        r.delete(f"{LIVE_KEY_PREFIX}:{tour}")
                        stats["skipped"] += 1
                        logger.debug("DataGolf live %s: no in-play data returned", tour)
                        continue

                    # Set live flag with 30-min TTL
                    r.set(f"{LIVE_KEY_PREFIX}:{tour}", "1", ex=1800)
                    stats["live_events"] += 1
                    stats[f"{tour}_players"] = len(players)

                    # Find existing DataGolf markets for this tour.
                    # Don't filter by status — if DataGolf API returns in-play data,
                    # we should update regardless of whether another source (Kalshi)
                    # has already resolved/closed its version of the market.
                    market_result = await session.execute(
                        select(FuturesMarket).where(
                            FuturesMarket.source == "datagolf",
                            FuturesMarket.external_id.like(f"datagolf:{tour}:%"),
                        )
                    )
                    markets = market_result.scalars().all()
                    stats[f"{tour}_markets"] = len(markets)
                    if markets:
                        stats[f"{tour}_market_statuses"] = list({m.status for m in markets})

                    if not markets:
                        # Auto-create markets from schedule + in-play data
                        logger.info("DataGolf live: no markets for tour=%s, auto-creating from schedule", tour)
                        stats["markets_created"] = 0
                        try:
                            schedule = await service.get_schedule(tour=tour)
                            current_event = None
                            for t in schedule:
                                if t.status and t.status != "completed":
                                    current_event = t
                                    break
                            if current_event:
                                for market_type, category in MARKET_TYPES:
                                    ext_id = _external_id(tour, current_event.event_id, market_type)
                                    market_name = f"{current_event.event_name} - {_market_label(market_type)}"
                                    market = FuturesMarket(
                                        source="datagolf",
                                        external_id=ext_id,
                                        name=market_name,
                                        category=category,
                                        llm_sport_category="golf",
                                        status="open",
                                        mutually_exclusive=(market_type == "win"),
                                        market_metadata={
                                            "datagolf_event_id": current_event.event_id,
                                            "course": current_event.course,
                                            "tour": tour,
                                        },
                                    )
                                    if current_event.start_date:
                                        try:
                                            market.commence_time = datetime.strptime(
                                                current_event.start_date, "%Y-%m-%d"
                                            ).replace(tzinfo=timezone.utc)
                                        except ValueError:
                                            pass
                                    if current_event.end_date:
                                        try:
                                            market.resolution_date = datetime.strptime(
                                                current_event.end_date, "%Y-%m-%d"
                                            ).replace(tzinfo=timezone.utc)
                                        except ValueError:
                                            pass
                                    session.add(market)
                                    stats["markets_created"] += 1
                                await session.flush()
                                # Re-query to get the newly created markets
                                market_result = await session.execute(
                                    select(FuturesMarket).where(
                                        FuturesMarket.source == "datagolf",
                                        FuturesMarket.external_id.like(f"datagolf:{tour}:%"),
                                        FuturesMarket.status == "open",
                                    )
                                )
                                markets = market_result.scalars().all()
                            else:
                                logger.info("DataGolf live: no current event in schedule for tour=%s", tour)
                                continue
                        except Exception as create_exc:
                            logger.error("DataGolf live: market creation failed for tour=%s: %s", tour, create_exc)
                            continue

                    now = datetime.now(timezone.utc)

                    # Detect round transitions for round_history metadata
                    current_round = players[0].current_round if players else None

                    for market in markets:
                        market_type = market.external_id.rsplit(":", 1)[-1]  # "win", "top_5", etc.

                        # Update round_history in metadata
                        if current_round and market.market_metadata:
                            round_history = market.market_metadata.get("round_history", [])
                            if not round_history or round_history[-1].get("round") != current_round:
                                round_history.append({
                                    "round": current_round,
                                    "timestamp": now.isoformat(),
                                    "label": f"R{current_round}",
                                })
                                market.market_metadata = {**market.market_metadata, "round_history": round_history}

                        # Build leaderboard from in-play data
                        leaderboard = []
                        for player in players:
                            entry = {
                                "dg_id": player.dg_id,
                                "name": player.player_name,
                                "position": player.position,
                                "total_score": player.total_score,
                                "today_score": player.today_score,
                                "thru": player.thru,
                                "current_round": player.current_round,
                            }
                            leaderboard.append(entry)

                        market.market_metadata = {
                            **(market.market_metadata or {}),
                            "leaderboard": leaderboard[:50],  # Top 50 for metadata size
                        }

                        # Update outcomes + write snapshots.
                        # Allow prob=0.0 (eliminated) and prob=1.0 (winner) — these are
                        # valid final-round states. Only skip if prob is truly unavailable.
                        players_written = 0
                        players_skipped_none = 0
                        for player in players:
                            prob = _get_prob(player, market_type)
                            if prob is None:
                                players_skipped_none += 1
                                continue
                            players_written += 1

                            outcome_ext_id = f"dg_{player.dg_id}"

                            out_result = await session.execute(
                                select(FuturesOutcome).where(
                                    FuturesOutcome.market_id == market.id,
                                    FuturesOutcome.external_id == outcome_ext_id,
                                )
                            )
                            outcome = out_result.scalar_one_or_none()

                            if not outcome:
                                outcome = FuturesOutcome(
                                    market_id=market.id,
                                    external_id=outcome_ext_id,
                                    name=player.player_name,
                                    current_probability=prob,
                                )
                                session.add(outcome)
                                await session.flush()
                            else:
                                outcome.current_probability = prob
                                outcome.last_updated = now

                            # Write-time dedup
                            last_snap = await session.execute(
                                select(FuturesOddsSnapshot)
                                .where(
                                    FuturesOddsSnapshot.outcome_id == outcome.id,
                                    FuturesOddsSnapshot.bookmaker == "datagolf_model",
                                )
                                .order_by(FuturesOddsSnapshot.captured_at.desc())
                                .limit(1)
                            )
                            existing_snap = last_snap.scalar_one_or_none()

                            if existing_snap and abs(float(existing_snap.probability) - prob) < 0.0001:
                                existing_snap.reading_count += 1
                                existing_snap.valid_until = now
                            else:
                                if existing_snap:
                                    existing_snap.valid_until = now
                                snap = FuturesOddsSnapshot(
                                    outcome_id=outcome.id,
                                    bookmaker="datagolf_model",
                                    probability=prob,
                                    captured_at=now,
                                    reading_count=1,
                                )
                                session.add(snap)
                                stats["snapshots_written"] += 1

                        if players_written > 0 or players_skipped_none > 0:
                            logger.info(
                                "DataGolf live %s market %s: %d players written, %d skipped (None prob)",
                                tour, market_type, players_written, players_skipped_none,
                            )

                        # Null out stale outcomes not in the current in-play
                        # field. See pre-tournament poll above for rationale.
                        fresh_ext_ids = {f"dg_{p.dg_id}" for p in players}
                        stale_result = await session.execute(
                            select(FuturesOutcome).where(
                                FuturesOutcome.market_id == market.id,
                                FuturesOutcome.current_probability.isnot(None),
                                ~FuturesOutcome.external_id.in_(fresh_ext_ids),
                            )
                        )
                        stale_nulled = 0
                        for stale in stale_result.scalars().all():
                            stale.current_probability = None
                            stale.last_updated = now
                            stale_nulled += 1
                        if stale_nulled:
                            logger.info(
                                "DataGolf live: nulled %d stale outcomes on market %s",
                                stale_nulled, market.id,
                            )

                    stats["tours_polled"] += 1

                except Exception as e:
                    logger.error("DataGolf live poll error for tour=%s: %s", tour, e)
                    continue

    finally:
        await service.close()

    logger.info("DataGolf live poll complete: %s", stats)
    return stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _market_label(market_type: str) -> str:
    """Human-readable label for a market type."""
    labels = {
        "win": "Winner",
        "top_5": "Top 5 Finish",
        "top_10": "Top 10 Finish",
        "top_20": "Top 20 Finish",
        "make_cut": "Make the Cut",
    }
    return labels.get(market_type, market_type.title())


def _get_prob(player, market_type: str) -> Optional[float]:
    """Extract the probability for a market type from a DataGolfPlayer."""
    mapping = {
        "win": player.win,
        "top_5": player.top_5,
        "top_10": player.top_10,
        "top_20": player.top_20,
        "make_cut": player.make_cut,
    }
    return mapping.get(market_type)


# ---------------------------------------------------------------------------
# Start-of-day leaderboard snapshot
# ---------------------------------------------------------------------------

async def _snapshot_leaderboard() -> dict:
    """Snapshot current leaderboard positions + probabilities for "today" deltas.

    Called once per day at ~6am ET (10/11 UTC). For each active tour with a
    live event, stores the full leaderboard in golf_leaderboard_snapshots so
    the /leaderboard endpoint can compute position_change and win_prob_change.
    """
    from app.services.datagolf_api import DataGolfAPIService
    from app.models.models import GolfLeaderboardSnapshot
    from app.tasks.redis_state import get_redis_client

    service = DataGolfAPIService()
    stats = {"tours_checked": 0, "snapshots_created": 0, "skipped": 0}

    try:
        r = get_redis_client()

        async with get_task_session() as session:
            for tour in POLL_TOURS:
                stats["tours_checked"] += 1

                # Only snapshot tours with a live event
                is_live = r.get(f"{LIVE_KEY_PREFIX}:{tour}")
                if not is_live:
                    stats["skipped"] += 1
                    continue

                try:
                    players, info = await service.get_in_play_with_info(tour)
                    if not players:
                        stats["skipped"] += 1
                        continue

                    # Build snapshot data
                    now = datetime.now(timezone.utc)
                    snapshot_data = []
                    for p in players:
                        snapshot_data.append({
                            "player_name": p.player_name,
                            "dg_id": p.dg_id,
                            "position": p.position,
                            "total_score": p.total_score,
                            "today_score": p.today_score,
                            "thru": p.thru,
                            "current_round": p.current_round,
                            "win_prob": round(p.win * 100, 1) if p.win else 0.0,
                            "top_5_prob": round(p.top_5 * 100, 1) if p.top_5 else None,
                            "top_10_prob": round(p.top_10 * 100, 1) if p.top_10 else None,
                        })

                    # Use today's date (in ET) for the snapshot_date
                    # ET is UTC-5 in winter, UTC-4 in summer
                    from zoneinfo import ZoneInfo
                    et_now = now.astimezone(ZoneInfo("America/New_York"))
                    snapshot_date = et_now.replace(hour=0, minute=0, second=0, microsecond=0)

                    # Check if we already have a snapshot for today
                    from sqlalchemy import select as sa_select
                    existing = await session.execute(
                        sa_select(GolfLeaderboardSnapshot).where(
                            GolfLeaderboardSnapshot.tour == tour,
                            GolfLeaderboardSnapshot.snapshot_date == snapshot_date,
                            GolfLeaderboardSnapshot.snapshot_type == "start_of_day",
                        )
                    )
                    if existing.scalar_one_or_none():
                        logger.info("Leaderboard snapshot already exists for tour=%s date=%s", tour, snapshot_date.date())
                        continue

                    snap = GolfLeaderboardSnapshot(
                        tour=tour,
                        event_name=info.get("event_name", "Unknown"),
                        snapshot_date=snapshot_date,
                        snapshot_type="start_of_day",
                        data=snapshot_data,
                    )
                    session.add(snap)
                    await session.flush()
                    stats["snapshots_created"] += 1
                    logger.info(
                        "Leaderboard snapshot created: tour=%s event=%s players=%d",
                        tour, info.get("event_name"), len(snapshot_data),
                    )

                except Exception as e:
                    logger.error("Leaderboard snapshot error for tour=%s: %s", tour, e)
                    continue

    finally:
        await service.close()

    logger.info("Leaderboard snapshot complete: %s", stats)
    return stats
