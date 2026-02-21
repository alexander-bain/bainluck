"""
Sport sync and event discovery tasks.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func, case
from sqlalchemy.dialects.postgresql import insert

from app.models import Sport, Event, OddsSnapshot, Team
from app.services.odds_api import OddsAPIService
from app.tasks.base import get_task_session, run_async

logger = logging.getLogger(__name__)


async def _sync_sports():
    """Async implementation of sync_sports."""
    service = OddsAPIService()

    try:
        sports_data = await service.get_sports()

        async with get_task_session() as session:
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


async def _discover_events():
    """
    Async implementation of discover_events.

    Polls ALL active sports (not just those with upcoming events) to discover
    new games. This ensures NCAA basketball, etc. get picked up even if they
    currently have no events in the database.
    """
    from app.tasks.odds_polling import _create_or_update_snapshot

    service = OddsAPIService()

    try:
        total_events = 0
        total_new_events = 0
        total_new_teams = 0
        sports_polled = 0

        async with get_task_session() as session:
            # Get ALL active sports (not filtering by existing events)
            result = await session.execute(
                select(Sport).where(Sport.active == True)
            )
            sports = result.scalars().all()

            for sport in sports:
                sport_key = sport.key

                try:
                    # Fetch odds for this sport
                    events_data = await service.get_odds(sport_key)
                    sports_polled += 1

                    # Collect all team names from this sport's events
                    all_team_names: set[str] = set()

                    for event_data in events_data:
                        commence_time = datetime.fromisoformat(
                            event_data["commence_time"].replace("Z", "+00:00")
                        )

                        # Determine event status
                        now = datetime.now(timezone.utc)
                        if commence_time <= now:
                            event_status = "live"
                        else:
                            event_status = "scheduled"

                        # Upsert event
                        stmt = insert(Event).values(
                            external_id=event_data["id"],
                            sport_id=sport.id,
                            home_team_name=event_data["home_team"],
                            away_team_name=event_data["away_team"],
                            commence_time=commence_time,
                            status=event_status,
                        ).on_conflict_do_update(
                            index_elements=["external_id"],
                            set_={
                                "home_team_name": event_data["home_team"],
                                "away_team_name": event_data["away_team"],
                                # Don't overwrite commence_time — The Odds API occasionally
                                # returns local times as UTC. ESPN sync corrects these.
                                "status": case(
                                    (Event.status == "scheduled", event_status),
                                    else_=Event.status
                                ),
                            }
                        ).returning(Event.id)

                        result = await session.execute(stmt)
                        event_id = result.scalar_one()
                        total_events += 1

                        # Track team names for auto-creation below
                        all_team_names.add(event_data["home_team"])
                        all_team_names.add(event_data["away_team"])

                        # Check if this was a new event (simple heuristic)
                        # If the event has no snapshots, it's likely new
                        snapshot_check = await session.execute(
                            select(func.count(OddsSnapshot.id))
                            .where(OddsSnapshot.event_id == event_id)
                        )
                        if snapshot_check.scalar() == 0:
                            total_new_events += 1

                        # Also save odds snapshots for this event
                        # This ensures events discovered have odds data immediately
                        for bookmaker in event_data.get("bookmakers", []):
                            snapshot, is_new = await _create_or_update_snapshot(
                                session,
                                event_id,
                                bookmaker,
                                event_data
                            )
                            if is_new:
                                session.add(snapshot)

                    # Auto-create Team records for any teams not yet in the DB.
                    # This ensures college teams (Harvard, Brown, Stanford, etc.)
                    # get Team records even without ESPN scoreboard matching.
                    if all_team_names:
                        existing_result = await session.execute(
                            select(Team.name).where(
                                Team.sport_id == sport.id,
                                Team.name.in_(all_team_names),
                            )
                        )
                        existing_team_names = {
                            row[0] for row in existing_result.all()
                        }
                        new_team_names = all_team_names - existing_team_names
                        for team_name in new_team_names:
                            session.add(Team(
                                name=team_name,
                                sport_id=sport.id,
                            ))
                        if new_team_names:
                            total_new_teams += len(new_team_names)
                            logger.info(
                                f"Auto-created {len(new_team_names)} Team "
                                f"records for {sport_key}"
                            )

                except Exception as e:
                    # Log but continue with other sports
                    print(f"Error discovering events for {sport_key}: {e}")
                    continue

            await session.commit()

        return {
            "sports_polled": sports_polled,
            "events_found": total_events,
            "new_events": total_new_events,
            "new_teams": total_new_teams,
        }
    finally:
        await service.close()
