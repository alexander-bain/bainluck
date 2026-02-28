"""
Sport sync and event discovery tasks.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

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


async def _find_statpal_event_for_odds_api(
    session, sport_id: int, home_team: str, away_team: str,
    commence_time: datetime
) -> Optional[Event]:
    """Find a StatPal-created event that matches an Odds API event.

    Only matches events that:
    1. Have no external_id (StatPal-created, not yet linked to Odds API)
    2. Are in the same sport
    3. Have matching team names (fuzzy)
    4. Are within 6 hours of the Odds API commence_time
    """
    from app.services.team_identity import normalize_name

    window = timedelta(hours=6)
    result = await session.execute(
        select(Event).where(
            Event.sport_id == sport_id,
            Event.external_id.is_(None),
            Event.commence_time.between(
                commence_time - window, commence_time + window
            ),
        ).limit(20)
    )
    candidates = result.scalars().all()

    home_norm = normalize_name(home_team)
    away_norm = normalize_name(away_team)

    for candidate in candidates:
        c_home = normalize_name(candidate.home_team_name)
        c_away = normalize_name(candidate.away_team_name)

        # Check normal orientation
        home_match = _names_match(home_norm, c_home)
        away_match = _names_match(away_norm, c_away)
        if home_match and away_match:
            return candidate

        # Check swapped home/away
        home_as_away = _names_match(home_norm, c_away)
        away_as_home = _names_match(away_norm, c_home)
        if home_as_away and away_as_home:
            return candidate

    return None


def _names_match(a: str, b: str) -> bool:
    """Check if two normalized team names match via containment or last-word."""
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        return True
    # Last-word (mascot) match
    a_parts = a.split()
    b_parts = b.split()
    if a_parts and b_parts and len(a_parts[-1]) >= 4 and a_parts[-1] == b_parts[-1]:
        return True
    return False


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
        total_statpal_attached = 0
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

                    # Record quota from response headers
                    if service.last_requests_remaining is not None:
                        from app.tasks.redis_state import record_odds_api_quota
                        record_odds_api_quota(
                            service.last_requests_remaining,
                            service.last_requests_used or 0,
                            "discover_events",
                        )

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

                        # Check if a StatPal-created event matches this Odds API event
                        statpal_event = await _find_statpal_event_for_odds_api(
                            session, sport.id,
                            event_data["home_team"], event_data["away_team"],
                            commence_time,
                        )

                        if statpal_event:
                            # Attach Odds API external_id to existing StatPal event
                            statpal_event.external_id = event_data["id"]
                            statpal_event.home_team_name = event_data["home_team"]
                            statpal_event.away_team_name = event_data["away_team"]
                            statpal_event.status = event_status
                            # Only overwrite commence_time if StatPal didn't set it
                            if statpal_event.commence_time_source != "statpal":
                                statpal_event.commence_time = commence_time
                            event_id = statpal_event.id
                            total_statpal_attached += 1
                            logger.info(
                                f"Attached Odds API {event_data['id']} to StatPal "
                                f"event {event_id} ({event_data['home_team']} vs "
                                f"{event_data['away_team']})"
                            )

                            # Register Odds API identities for the attached event
                            from app.services.team_identity import team_identity_service
                            if statpal_event.home_team_id:
                                await team_identity_service.register_team_identity(
                                    session, statpal_event.home_team_id,
                                    "odds_api", sport_key,
                                    source_name=event_data["home_team"],
                                )
                            if statpal_event.away_team_id:
                                await team_identity_service.register_team_identity(
                                    session, statpal_event.away_team_id,
                                    "odds_api", sport_key,
                                    source_name=event_data["away_team"],
                                )
                        else:
                            # Normal upsert (no StatPal match found)
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
                            new_team = Team(
                                name=team_name,
                                sport_id=sport.id,
                            )
                            session.add(new_team)
                        if new_team_names:
                            await session.flush()  # Get IDs for identity registration

                            # Register Odds API identities for newly created teams
                            from app.services.team_identity import team_identity_service
                            for team_name in new_team_names:
                                # Look up the team we just created
                                team_result = await session.execute(
                                    select(Team).where(
                                        Team.name == team_name,
                                        Team.sport_id == sport.id,
                                    )
                                )
                                new_team_obj = team_result.scalar_one_or_none()
                                if new_team_obj:
                                    await team_identity_service.register_team_identity(
                                        session, new_team_obj.id, "odds_api", sport_key,
                                        source_name=team_name,
                                    )

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
            "statpal_attached": total_statpal_attached,
        }
    finally:
        await service.close()
