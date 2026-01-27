"""
Celery tasks for background odds polling.

This module sets up periodic tasks to:
1. Fetch odds from The Odds API
2. Store events and snapshots in the database
3. Calculate probabilities
"""

import asyncio
import os
from datetime import datetime, timezone

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.services.database import async_session_maker
from app.services.odds_api import OddsAPIService
from app.models import Sport, Event, OddsSnapshot
from app.utils.odds_math import moneyline_to_probability, project_scores

# Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "odds_tracker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minute timeout
    worker_prefetch_multiplier=1,
)

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "poll-odds-every-5-minutes": {
        "task": "app.tasks.poll_all_odds",
        "schedule": 300.0,  # Every 5 minutes
    },
    "sync-sports-hourly": {
        "task": "app.tasks.sync_sports",
        "schedule": crontab(minute=0),  # Every hour
    },
}


def run_async(coro):
    """Helper to run async code in sync context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3)
def sync_sports(self):
    """
    Sync available sports from The Odds API to database.

    This creates/updates Sport records for each sport
    returned by the API.
    """
    try:
        return run_async(_sync_sports())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


async def _sync_sports():
    """Async implementation of sync_sports."""
    service = OddsAPIService()

    try:
        sports_data = await service.get_sports()

        async with async_session_maker() as session:
            synced = 0
            for sport in sports_data:
                if not sport.get("active", False):
                    continue

                # Upsert sport
                stmt = insert(Sport).values(
                    key=sport["key"],
                    name=sport["title"],
                    group=sport.get("group"),
                    active=True,
                ).on_conflict_do_update(
                    index_elements=["key"],
                    set_={
                        "name": sport["title"],
                        "group": sport.get("group"),
                        "active": True,
                    }
                )
                await session.execute(stmt)
                synced += 1

            await session.commit()

        return {"synced": synced}
    finally:
        await service.close()


@celery_app.task(bind=True, max_retries=3)
def poll_all_odds(self):
    """
    Poll odds for all configured sports.

    This fetches current odds from The Odds API and stores
    them as OddsSnapshot records.
    """
    try:
        return run_async(_poll_all_odds())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


async def _poll_all_odds():
    """Async implementation of poll_all_odds."""
    service = OddsAPIService()

    try:
        total_events = 0
        total_snapshots = 0

        async with async_session_maker() as session:
            # Get active sports from database
            result = await session.execute(
                select(Sport).where(Sport.active == True)
            )
            sports = result.scalars().all()

            # If no sports in DB, use default list
            sport_keys = [s.key for s in sports] if sports else OddsAPIService.SPORTS

            for sport_key in sport_keys:
                try:
                    events_data = await service.get_odds(sport_key)

                    for event_data in events_data:
                        # Get or create sport
                        sport_result = await session.execute(
                            select(Sport).where(Sport.key == sport_key)
                        )
                        sport = sport_result.scalar_one_or_none()

                        if not sport:
                            # Create sport on the fly
                            sport = Sport(
                                key=sport_key,
                                name=sport_key.replace("_", " ").title(),
                                active=True,
                            )
                            session.add(sport)
                            await session.flush()

                        # Upsert event
                        commence_time = datetime.fromisoformat(
                            event_data["commence_time"].replace("Z", "+00:00")
                        )

                        stmt = insert(Event).values(
                            external_id=event_data["id"],
                            sport_id=sport.id,
                            home_team_name=event_data["home_team"],
                            away_team_name=event_data["away_team"],
                            commence_time=commence_time,
                            status="scheduled" if commence_time > datetime.now(timezone.utc) else "live",
                        ).on_conflict_do_update(
                            index_elements=["external_id"],
                            set_={
                                "home_team_name": event_data["home_team"],
                                "away_team_name": event_data["away_team"],
                                "commence_time": commence_time,
                            }
                        ).returning(Event.id)

                        result = await session.execute(stmt)
                        event_id = result.scalar_one()
                        total_events += 1

                        # Create odds snapshots
                        for bookmaker in event_data.get("bookmakers", []):
                            snapshot = await _create_snapshot(
                                event_id,
                                bookmaker,
                                event_data
                            )
                            session.add(snapshot)
                            total_snapshots += 1

                except Exception as e:
                    print(f"Error polling {sport_key}: {e}")
                    continue

            await session.commit()

        return {
            "events": total_events,
            "snapshots": total_snapshots,
            "sports": len(sport_keys),
        }
    finally:
        await service.close()


async def _create_snapshot(
    event_id: int,
    bookmaker: dict,
    event_data: dict
) -> OddsSnapshot:
    """Create an OddsSnapshot from API data."""
    snapshot = OddsSnapshot(
        event_id=event_id,
        bookmaker=bookmaker["key"],
        captured_at=datetime.now(timezone.utc),
    )

    # Parse markets
    for market in bookmaker.get("markets", []):
        market_key = market["key"]
        outcomes = {o["name"]: o for o in market["outcomes"]}
        home_team = event_data["home_team"]
        away_team = event_data["away_team"]

        if market_key == "h2h":
            home_outcome = outcomes.get(home_team, {})
            away_outcome = outcomes.get(away_team, {})
            snapshot.home_moneyline = home_outcome.get("price")
            snapshot.away_moneyline = away_outcome.get("price")

            # Calculate probabilities
            if snapshot.home_moneyline and snapshot.away_moneyline:
                home_prob, away_prob = moneyline_to_probability(
                    snapshot.home_moneyline,
                    snapshot.away_moneyline,
                )
                snapshot.home_win_probability = round(home_prob, 4)
                snapshot.away_win_probability = round(away_prob, 4)

        elif market_key == "spreads":
            home_outcome = outcomes.get(home_team, {})
            away_outcome = outcomes.get(away_team, {})
            snapshot.home_spread = home_outcome.get("point")
            snapshot.home_spread_odds = home_outcome.get("price")
            snapshot.away_spread_odds = away_outcome.get("price")

        elif market_key == "totals":
            over_outcome = outcomes.get("Over", {})
            under_outcome = outcomes.get("Under", {})
            snapshot.over_under = over_outcome.get("point")
            snapshot.over_odds = over_outcome.get("price")
            snapshot.under_odds = under_outcome.get("price")

    # Calculate projected scores if we have the data
    if (snapshot.home_win_probability and snapshot.over_under):
        home_score, away_score = project_scores(
            float(snapshot.home_win_probability),
            float(snapshot.over_under),
        )
        snapshot.projected_home_score = home_score
        snapshot.projected_away_score = away_score

    return snapshot


@celery_app.task(bind=True)
def poll_sport_odds(self, sport_key: str):
    """
    Poll odds for a single sport.

    Useful for manual triggering or prioritizing specific sports.
    """
    return run_async(_poll_sport_odds(sport_key))


async def _poll_sport_odds(sport_key: str):
    """Async implementation of poll_sport_odds."""
    service = OddsAPIService()

    try:
        events_data = await service.get_odds(sport_key)

        async with async_session_maker() as session:
            # Get or create sport
            result = await session.execute(
                select(Sport).where(Sport.key == sport_key)
            )
            sport = result.scalar_one_or_none()

            if not sport:
                sport = Sport(
                    key=sport_key,
                    name=sport_key.replace("_", " ").title(),
                    active=True,
                )
                session.add(sport)
                await session.flush()

            total_snapshots = 0

            for event_data in events_data:
                commence_time = datetime.fromisoformat(
                    event_data["commence_time"].replace("Z", "+00:00")
                )

                stmt = insert(Event).values(
                    external_id=event_data["id"],
                    sport_id=sport.id,
                    home_team_name=event_data["home_team"],
                    away_team_name=event_data["away_team"],
                    commence_time=commence_time,
                    status="scheduled" if commence_time > datetime.now(timezone.utc) else "live",
                ).on_conflict_do_update(
                    index_elements=["external_id"],
                    set_={
                        "home_team_name": event_data["home_team"],
                        "away_team_name": event_data["away_team"],
                        "commence_time": commence_time,
                    }
                ).returning(Event.id)

                result = await session.execute(stmt)
                event_id = result.scalar_one()

                for bookmaker in event_data.get("bookmakers", []):
                    snapshot = await _create_snapshot(event_id, bookmaker, event_data)
                    session.add(snapshot)
                    total_snapshots += 1

            await session.commit()

        return {
            "sport": sport_key,
            "events": len(events_data),
            "snapshots": total_snapshots,
        }
    finally:
        await service.close()
