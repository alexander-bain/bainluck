"""Roster sync task — fetches player rosters from SportsDataIO and stores on Team records.

Player names are stored in Team.roster_players as a JSONB list, e.g.:
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
    """Sync player rosters from SportsDataIO to Team.roster_players.

    Args:
        sport_key: Our sport key (e.g., "basketball_nba"). If None, syncs all supported sports.

    Returns:
        Summary dict with teams_updated count and details.
    """
    service = SportsDataIOService()
    try:
        return await _sync_rosters_impl(service, sport_key)
    finally:
        await service.close()


async def _sync_rosters_impl(service: SportsDataIOService, sport_key: Optional[str]) -> dict:
    """Implementation of roster sync."""
    if not service.api_key:
        return {"error": "SPORTSDATA_API_KEY not configured"}

    # Determine which sports to sync
    if sport_key:
        sport_keys = [sport_key]
    else:
        sport_keys = list(SPORTSDATA_SPORT_MAPPING.keys())

    total_updated = 0
    total_players = 0
    details = []

    async with get_task_session() as session:
        for our_key in sport_keys:
            sd_sport = service.get_sportsdata_sport(our_key)
            if not sd_sport:
                continue

            logger.info(f"Syncing rosters for {our_key} (SportsDataIO: {sd_sport})")

            # Fetch all active players for this sport
            players = await service.fetch_all_players(sd_sport)
            if not players:
                details.append({"sport": our_key, "status": "no_data"})
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

            # Look up our Sport record to scope team matching
            from app.models import Sport
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

            # Update each team's roster_players
            from app.models import Team
            sport_updated = 0
            unmatched = []
            for abbrev, player_names in team_players.items():
                # Deduplicate and sort
                unique_names = sorted(set(player_names))

                # Try 1: Match by abbreviation + sport
                team_result = await session.execute(
                    select(Team.id).where(
                        Team.abbreviation == abbrev,
                        Team.sport_id == sport_id,
                    )
                )
                team_row = team_result.first()

                # Try 2: Static name map (hardcoded SportsDataIO abbrev → team name)
                if not team_row and abbrev in name_map:
                    team_result = await session.execute(
                        select(Team.id).where(
                            Team.name == name_map[abbrev],
                            Team.sport_id == sport_id,
                        )
                    )
                    team_row = team_result.first()

                if not team_row:
                    unmatched.append(abbrev)
                    continue

                await session.execute(
                    update(Team)
                    .where(Team.id == team_row.id)
                    .values(roster_players=unique_names)
                )
                sport_updated += 1
                total_players += len(unique_names)

            total_updated += sport_updated
            sport_detail = {
                "sport": our_key,
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
        "teams_updated": total_updated,
        "total_player_names": total_players,
        "sports": details,
    }
