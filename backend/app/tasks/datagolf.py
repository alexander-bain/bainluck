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

# Tours to poll (PGA is primary; extend as needed)
POLL_TOURS = ["pga"]


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

                    # Find the current/next event (first with a future or ongoing date)
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    current_event = None
                    for t in schedule:
                        if t.end_date and t.end_date >= now_str:
                            current_event = t
                            break

                    if not current_event:
                        logger.info("DataGolf: no upcoming event for tour=%s", tour)
                        stats["debug"][tour] = f"no_upcoming_event (schedule_count={len(schedule)}, now={now_str})"
                        if schedule:
                            stats["debug"][f"{tour}_last_end_date"] = schedule[-1].end_date
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
                            if prob is None or prob <= 0:
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
                        continue

                    # Set live flag with 30-min TTL
                    r.set(f"{LIVE_KEY_PREFIX}:{tour}", "1", ex=1800)
                    stats["live_events"] += 1

                    # Find existing DataGolf markets for this tour
                    market_result = await session.execute(
                        select(FuturesMarket).where(
                            FuturesMarket.source == "datagolf",
                            FuturesMarket.external_id.like(f"datagolf:{tour}:%"),
                            FuturesMarket.status == "open",
                        )
                    )
                    markets = market_result.scalars().all()

                    if not markets:
                        logger.info("DataGolf live: no markets found for tour=%s, run hourly poll first", tour)
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

                        # Update outcomes + write snapshots
                        for player in players:
                            prob = _get_prob(player, market_type)
                            if prob is None or prob <= 0:
                                continue

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
