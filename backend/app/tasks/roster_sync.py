"""Roster and team sync task — fetches teams and player rosters from SportsDataIO.

Two sync phases per sport:
1. Team sync: Ensures all pro teams exist in the `teams` table with city/location data.
   Creates missing teams from SportsDataIO's AllTeams endpoint. Backfills location on
   existing teams if missing.
2. Roster sync: Stores player names in Team.roster_players as a JSONB list, e.g.:
   ["Jayson Tatum", "Jaylen Brown", "Derrick White", ...]
   These names are used by the related-futures endpoint to match player outcomes
   (MVP, DPOY, ROY, etc.) to the correct team.
"""

import logging
from typing import Optional

from sqlalchemy import select, update

from app.tasks.base import get_task_session
from app.services.sportsdata_api import (
    SportsDataIOService,
    SPORTSDATA_SPORT_MAPPING,
    SPORTSDATA_ABBREV_TO_NAME,
)

logger = logging.getLogger(__name__)


async def _sync_rosters(sport_key: Optional[str] = None) -> dict:
    """Sync teams and player rosters from SportsDataIO.

    Args:
        sport_key: Our sport key (e.g., "basketball_nba"). If None, syncs all supported sports.

    Returns:
        Summary dict with teams_created, teams_updated count and details.
    """
    service = SportsDataIOService()
    try:
        return await _sync_rosters_impl(service, sport_key)
    finally:
        await service.close()


async def _sync_rosters_impl(service: SportsDataIOService, sport_key: Optional[str]) -> dict:
    """Implementation of team + roster sync."""
    if not service.api_key:
        return {"error": "SPORTSDATA_API_KEY not configured"}

    # Determine which sports to sync
    if sport_key:
        sport_keys = [sport_key]
    else:
        sport_keys = list(SPORTSDATA_SPORT_MAPPING.keys())

    total_updated = 0
    total_players = 0
    total_teams_created = 0
    total_teams_backfilled = 0
    details = []

    async with get_task_session() as session:
        from app.models import Sport, Team

        for our_key in sport_keys:
            sd_sport = service.get_sportsdata_sport(our_key)
            if not sd_sport:
                continue

            logger.info(f"Syncing teams and rosters for {our_key} (SportsDataIO: {sd_sport})")

            # Look up our Sport record to scope team matching
            sport_result = await session.execute(
                select(Sport.id).where(Sport.key == our_key)
            )
            sport_row = sport_result.first()
            if not sport_row:
                details.append({"sport": our_key, "status": "sport_not_found"})
                continue
            sport_id = sport_row.id

            # Static name map for this sport (SportsDataIO abbrev → our team name)
            name_map = SPORTSDATA_ABBREV_TO_NAME.get(sd_sport, {})

            # =================================================================
            # Phase 1: Team sync — ensure all pro teams exist
            # =================================================================
            # Also builds sd_abbrev → team_id mapping for Phase 2 roster sync.
            # This bridges the abbreviation gap: ESPN sets Team.abbreviation
            # which may differ from SportsDataIO abbreviations (e.g., WSH vs WAS).
            teams_created = 0
            teams_backfilled = 0
            sd_abbrev_to_team_id: dict[str, int] = {}
            sd_teams = await service.fetch_teams(sd_sport)

            for sd_team in sd_teams:
                abbrev = sd_team.get("key", "")
                full_name = sd_team.get("full_name", "")
                city = sd_team.get("city", "")

                if not abbrev or not full_name:
                    continue

                # Try to find existing team by abbreviation
                team_result = await session.execute(
                    select(Team).where(
                        Team.abbreviation == abbrev,
                        Team.sport_id == sport_id,
                    )
                )
                existing_team = team_result.scalar_one_or_none()

                # Try by name map if abbreviation didn't match
                if not existing_team and abbrev in name_map:
                    team_result = await session.execute(
                        select(Team).where(
                            Team.name == name_map[abbrev],
                            Team.sport_id == sport_id,
                        )
                    )
                    existing_team = team_result.scalar_one_or_none()

                # Try by full_name (SportsDataIO might use different abbreviation)
                if not existing_team:
                    team_result = await session.execute(
                        select(Team).where(
                            Team.name == full_name,
                            Team.sport_id == sport_id,
                        )
                    )
                    existing_team = team_result.scalar_one_or_none()

                # Try by ILIKE on name_map value (handles minor formatting diffs
                # like "St. Louis" vs "St Louis")
                if not existing_team and abbrev in name_map:
                    mapped_name = name_map[abbrev]
                    team_result = await session.execute(
                        select(Team).where(
                            Team.name.ilike(f"%{mapped_name}%"),
                            Team.sport_id == sport_id,
                        )
                    )
                    existing_team = team_result.scalar_one_or_none()

                if existing_team:
                    sd_abbrev_to_team_id[abbrev] = existing_team.id
                    # Backfill location if missing
                    if not existing_team.location and city:
                        await session.execute(
                            update(Team)
                            .where(Team.id == existing_team.id)
                            .values(location=city)
                        )
                        teams_backfilled += 1
                        logger.info(f"  Backfilled location for {existing_team.name}: {city}")
                    # Backfill abbreviation if missing
                    if not existing_team.abbreviation and abbrev:
                        await session.execute(
                            update(Team)
                            .where(Team.id == existing_team.id)
                            .values(abbreviation=abbrev)
                        )
                else:
                    # Create new Team record from SportsDataIO data
                    new_team = Team(
                        name=full_name,
                        abbreviation=abbrev,
                        location=city,
                        sport_id=sport_id,
                    )
                    session.add(new_team)
                    await session.flush()
                    sd_abbrev_to_team_id[abbrev] = new_team.id
                    teams_created += 1
                    logger.info(f"  Created Team: {full_name} ({abbrev}) in {city}")

            total_teams_created += teams_created
            total_teams_backfilled += teams_backfilled

            if teams_created > 0 or teams_backfilled > 0:
                logger.info(
                    f"  {our_key} team sync: {teams_created} created, "
                    f"{teams_backfilled} locations backfilled"
                )
            logger.info(
                f"  {our_key} Phase 1: resolved {len(sd_abbrev_to_team_id)}/{len(sd_teams)} "
                f"SportsDataIO teams to DB records"
            )

            # =================================================================
            # Phase 2: Roster sync — update player names
            # =================================================================
            players = await service.fetch_all_players(sd_sport)
            if not players:
                details.append({
                    "sport": our_key,
                    "teams_created": teams_created,
                    "teams_backfilled": teams_backfilled,
                    "status": "no_player_data",
                })
                continue

            # Group players by team abbreviation
            team_players: dict[str, list[str]] = {}
            for p in players:
                abbrev = p["team_abbrev"]
                # Use both full name and ASCII variant for matching coverage
                names = {p["name"]}
                if p.get("ascii_name") and p["ascii_name"] != p["name"]:
                    names.add(p["ascii_name"])
                team_players.setdefault(abbrev, []).extend(names)

            # Update each team's roster_players
            sport_updated = 0
            unmatched = []
            for abbrev, player_names in team_players.items():
                # Deduplicate and sort
                unique_names = sorted(set(player_names))

                # Try 1: Use Phase 1 mapping (bridges ESPN/SportsDataIO abbrev gap)
                team_id = sd_abbrev_to_team_id.get(abbrev)

                # Try 2: Match by abbreviation + sport (fallback for teams
                # not in Phase 1 fetch, e.g., expansion teams or data gaps)
                if not team_id:
                    team_result = await session.execute(
                        select(Team.id).where(
                            Team.abbreviation == abbrev,
                            Team.sport_id == sport_id,
                        )
                    )
                    team_row = team_result.first()
                    team_id = team_row[0] if team_row else None

                # Try 3: Static name map (hardcoded SportsDataIO abbrev → team name)
                if not team_id and abbrev in name_map:
                    team_result = await session.execute(
                        select(Team.id).where(
                            Team.name == name_map[abbrev],
                            Team.sport_id == sport_id,
                        )
                    )
                    team_row = team_result.first()
                    team_id = team_row[0] if team_row else None

                # Try 4: Create Team record if we have a name mapping but no DB record
                # (This should rarely trigger now that Phase 1 creates teams upfront)
                if not team_id and abbrev in name_map:
                    new_team = Team(
                        name=name_map[abbrev],
                        abbreviation=abbrev,
                        sport_id=sport_id,
                    )
                    session.add(new_team)
                    await session.flush()
                    team_id = new_team.id
                    logger.info(f"  Created new Team record: {name_map[abbrev]} ({abbrev})")

                if not team_id:
                    unmatched.append(abbrev)
                    continue

                await session.execute(
                    update(Team)
                    .where(Team.id == team_id)
                    .values(roster_players=unique_names)
                )
                sport_updated += 1
                total_players += len(unique_names)

            total_updated += sport_updated
            sport_detail = {
                "sport": our_key,
                "teams_created": teams_created,
                "teams_backfilled": teams_backfilled,
                "teams_updated": sport_updated,
                "total_teams_in_api": len(team_players),
                "players_synced": sum(len(v) for v in team_players.values()),
            }
            if unmatched:
                sport_detail["unmatched_abbreviations"] = unmatched
                logger.warning(f"  {our_key}: {len(unmatched)} unmatched teams: {unmatched}")
            details.append(sport_detail)
            logger.info(
                f"  {our_key}: updated {sport_updated}/{len(team_players)} teams, "
                f"{sum(len(v) for v in team_players.values())} player names"
            )

    return {
        "teams_created": total_teams_created,
        "teams_backfilled": total_teams_backfilled,
        "teams_updated": total_updated,
        "total_player_names": total_players,
        "sports": details,
    }
