"""Roster sync task — fetches player rosters from ESPN + MLB Stats API.

Uses ESPN's undocumented roster endpoints as the primary source for all sports
except baseball (which uses the MLB Stats API). Team matching is via the
`Team.espn_id` column already populated by the ESPN sync task.

Stores player names in Team.roster_players as a JSONB list, e.g.:
    ["Jayson Tatum", "Jaylen Brown", "Derrick White", ...]
These names are used by the related-futures endpoint to match player outcomes
(MVP, DPOY, ROY, etc.) to the correct team.

Replaces the former SportsDataIO-powered roster sync ($50-75/mo) with free APIs.
"""

import asyncio
import logging
import unicodedata
from typing import Optional

from sqlalchemy import select, update

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

# Sports to sync rosters for.
# ESPN covers all of these via the roster endpoint.
# Baseball uses MLB Stats API instead (more reliable for MLB).
ROSTER_SPORTS = [
    "basketball_nba",
    "americanfootball_nfl",
    "icehockey_nhl",
    "baseball_mlb",          # Uses MLB Stats API
    "basketball_ncaab",      # College — NEW (SportsDataIO couldn't do this)
    "americanfootball_ncaaf", # College — NEW
    "basketball_wnba",
    "soccer_usa_mls",
]


_EXTRA_TRANSLITERATIONS = str.maketrans({
    "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L",
    "æ": "ae", "Æ": "AE",
})


def _strip_diacritics(s: str) -> str:
    """Remove accent marks and transliterate special letters."""
    s = s.translate(_EXTRA_TRANSLITERATIONS)
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _player_names_with_ascii(name: str) -> list[str]:
    """Return a list containing the name and its ASCII variant (if different)."""
    names = [name]
    ascii_name = _strip_diacritics(name)
    if ascii_name != name:
        names.append(ascii_name)
    return names


async def _sync_rosters(sport_key: Optional[str] = None) -> dict:
    """Sync player rosters from ESPN + MLB Stats API.

    Args:
        sport_key: Our sport key (e.g., "basketball_nba"). If None, syncs all supported sports.

    Returns:
        Summary dict with update counts and details per sport.
    """
    if sport_key:
        sport_keys = [sport_key]
    else:
        sport_keys = list(ROSTER_SPORTS)

    total_updated = 0
    total_players = 0
    total_skipped = 0
    details = []

    async with get_task_session() as session:
        from app.models import Sport, Team

        for our_key in sport_keys:
            if our_key not in ROSTER_SPORTS:
                details.append({"sport": our_key, "status": "unsupported_sport"})
                continue

            # Look up our Sport record
            sport_result = await session.execute(
                select(Sport.id).where(Sport.key == our_key)
            )
            sport_row = sport_result.first()
            if not sport_row:
                details.append({"sport": our_key, "status": "sport_not_found"})
                continue
            sport_id = sport_row.id

            logger.info(f"Syncing rosters for {our_key}")

            if our_key == "baseball_mlb":
                sport_detail = await _sync_mlb_rosters(session, Team, sport_id)
            else:
                sport_detail = await _sync_espn_rosters(
                    session, Team, sport_id, our_key
                )

            sport_detail["sport"] = our_key
            details.append(sport_detail)
            total_updated += sport_detail.get("teams_updated", 0)
            total_players += sport_detail.get("players_synced", 0)
            total_skipped += sport_detail.get("teams_skipped_no_espn_id", 0)

    return {
        "teams_updated": total_updated,
        "total_player_names": total_players,
        "teams_skipped_no_espn_id": total_skipped,
        "sports": details,
    }


async def _sync_espn_rosters(session, Team, sport_id: int, sport_key: str) -> dict:
    """Sync rosters for a sport using ESPN's roster endpoint.

    Queries all Teams with espn_id set for this sport, fetches each roster
    from ESPN, and writes to Team.roster_players.
    """
    from app.services.espn_api import get_espn_service

    espn = get_espn_service()

    # Get all teams with ESPN IDs for this sport
    result = await session.execute(
        select(Team).where(
            Team.sport_id == sport_id,
            Team.espn_id.isnot(None),
        )
    )
    teams = result.scalars().all()

    if not teams:
        logger.warning(f"  {sport_key}: no teams with espn_id found")
        return {"teams_updated": 0, "teams_skipped_no_espn_id": 0, "status": "no_teams_with_espn_id"}

    # Count teams without ESPN IDs (for reporting)
    total_result = await session.execute(
        select(Team.id).where(Team.sport_id == sport_id)
    )
    total_teams = len(total_result.all())
    skipped = total_teams - len(teams)

    updated = 0
    empty_rosters = 0
    total_player_names = 0

    for team in teams:
        roster = await espn.get_team_roster(sport_key, team.espn_id)

        if not roster:
            # Write empty list to clear stale data
            await session.execute(
                update(Team)
                .where(Team.id == team.id)
                .values(roster_players=[])
            )
            empty_rosters += 1
            logger.debug(f"  {team.name}: empty roster from ESPN")
            continue

        # Extract player names with ASCII variants + metadata
        all_entries: list = []
        seen_names = set()
        for player in roster:
            name = player["name"]
            if name in seen_names:
                continue
            seen_names.add(name)

            # Store rich dict for players with ESPN metadata
            entry: dict = {"name": name}
            if player.get("position"):
                entry["position"] = player["position"]
            if player.get("espn_id"):
                entry["espn_id"] = player["espn_id"]
            if player.get("headshot"):
                entry["headshot"] = player["headshot"]
            all_entries.append(entry)

            # Also store plain ASCII variant string for ILIKE matching
            ascii_name = _strip_diacritics(name)
            if ascii_name != name and ascii_name not in seen_names:
                seen_names.add(ascii_name)
                all_entries.append(ascii_name)

        # Sort dicts by name, strings alphabetically
        all_entries.sort(key=lambda x: x["name"] if isinstance(x, dict) else x)

        await session.execute(
            update(Team)
            .where(Team.id == team.id)
            .values(roster_players=all_entries)
        )
        updated += 1
        total_player_names += len(all_entries)

        # Rate limit between roster fetches
        await asyncio.sleep(0.3)

    logger.info(
        f"  {sport_key}: updated {updated}/{len(teams)} teams, "
        f"{total_player_names} player names, {empty_rosters} empty rosters, "
        f"{skipped} teams skipped (no espn_id)"
    )

    return {
        "teams_updated": updated,
        "teams_with_espn_id": len(teams),
        "teams_skipped_no_espn_id": skipped,
        "empty_rosters": empty_rosters,
        "players_synced": total_player_names,
    }


async def _sync_mlb_rosters(session, Team, sport_id: int) -> dict:
    """Sync MLB rosters using the MLB Stats API.

    Fetches all MLB teams from the API, matches to our DB teams by name,
    then fetches and stores each roster.
    """
    from app.services.mlb_api import MLBAPIService

    service = MLBAPIService()
    try:
        return await _sync_mlb_rosters_impl(session, Team, sport_id, service)
    finally:
        await service.close()


async def _sync_mlb_rosters_impl(session, Team, sport_id: int, service) -> dict:
    """Implementation of MLB roster sync."""
    mlb_teams = await service.get_teams()
    if not mlb_teams:
        logger.warning("  baseball_mlb: MLB Stats API returned no teams")
        return {"teams_updated": 0, "status": "no_mlb_teams"}

    # Get all our MLB teams from the DB
    result = await session.execute(
        select(Team).where(Team.sport_id == sport_id)
    )
    db_teams = result.scalars().all()

    # Build lookup by name (lowercased) for matching
    db_teams_by_name = {}
    for t in db_teams:
        db_teams_by_name[t.name.lower()] = t
        # Also index by short name (e.g., "Yankees" from "New York Yankees")
        parts = t.name.split()
        if len(parts) >= 2:
            db_teams_by_name[parts[-1].lower()] = t

    updated = 0
    unmatched_mlb = []
    total_player_names = 0

    for mlb_team in mlb_teams:
        mlb_name = mlb_team.get("name", "")
        mlb_id = mlb_team.get("id")
        if not mlb_name or not mlb_id:
            continue

        # Name-based matching (simple, reliable)
        db_team = db_teams_by_name.get(mlb_name.lower())
        if not db_team:
            # Try suffix match (e.g., "Yankees" matches "New York Yankees")
            mlb_parts = mlb_name.split()
            if len(mlb_parts) >= 2:
                db_team = db_teams_by_name.get(mlb_parts[-1].lower())

        if not db_team:
            unmatched_mlb.append(mlb_name)
            continue

        # Fetch roster
        player_names = await service.get_team_roster(mlb_id)

        # Add ASCII variants
        all_names = []
        for name in player_names:
            all_names.extend(_player_names_with_ascii(name))

        unique_names = sorted(set(all_names))

        if unique_names:
            await session.execute(
                update(Team)
                .where(Team.id == db_team.id)
                .values(roster_players=unique_names)
            )
            updated += 1
            total_player_names += len(unique_names)
            logger.info(f"  MLB: {mlb_name} → team_id={db_team.id}, {len(unique_names)} players")
        else:
            logger.warning(f"  MLB: {mlb_name} → empty roster from API")

        # Rate limit
        await asyncio.sleep(0.3)

    # Explicit flush to ensure updates are visible before context manager commit
    await session.flush()

    logger.info(
        f"  baseball_mlb: updated {updated}/{len(mlb_teams)} teams, "
        f"{total_player_names} player names"
    )

    result = {
        "teams_updated": updated,
        "mlb_teams_in_api": len(mlb_teams),
        "players_synced": total_player_names,
    }
    if unmatched_mlb:
        result["unmatched_mlb_teams"] = unmatched_mlb
        logger.warning(f"  baseball_mlb: {len(unmatched_mlb)} unmatched: {unmatched_mlb}")

    return result
