"""One-time backfill of team_identity_mapping from existing data.

Populates the mapping table from:
1. ESPN IDs on Team records
2. Team primary names (as odds_api source)
3. Team alternate_names (as odds_api source)
4. Team abbreviations
5. Kalshi ticker abbreviations from prediction_market_matching._KALSHI_TEAM_ABBREVS
"""

import logging
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.tasks.base import get_task_session
from app.models.models import Team, TeamIdentityMapping, Sport

logger = logging.getLogger(__name__)


async def _register_mapping(
    session: AsyncSession,
    team_id: int,
    source: str,
    sport_key: str,
    *,
    source_id: Optional[str] = None,
    source_name: Optional[str] = None,
    source_abbreviation: Optional[str] = None,
) -> bool:
    """Register a single mapping, returns True if inserted/updated."""
    if not source_id and not source_name:
        return False

    values = {
        "team_id": team_id,
        "source": source,
        "sport_key": sport_key,
        "source_id": source_id,
        "source_name": source_name,
        "source_abbreviation": source_abbreviation,
        "updated_at": func.now(),
    }

    try:
        if source_id:
            stmt = pg_insert(TeamIdentityMapping).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["source", "source_id", "sport_key"],
                index_where=TeamIdentityMapping.source_id.isnot(None),
                set_={
                    "team_id": stmt.excluded.team_id,
                    "source_name": stmt.excluded.source_name,
                    "source_abbreviation": stmt.excluded.source_abbreviation,
                    "updated_at": func.now(),
                },
            )
            await session.execute(stmt)
        elif source_name:
            stmt = pg_insert(TeamIdentityMapping).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["source", "source_name", "sport_key"],
                index_where=TeamIdentityMapping.source_name.isnot(None),
                set_={
                    "team_id": stmt.excluded.team_id,
                    "source_abbreviation": stmt.excluded.source_abbreviation,
                    "updated_at": func.now(),
                },
            )
            await session.execute(stmt)
        return True
    except Exception as e:
        logger.warning("Failed to register mapping team_id=%s source=%s: %s", team_id, source, e)
        return False


async def _backfill_team_identities() -> dict:
    """One-time backfill of team_identity_mapping from existing data.

    Returns a summary dict with counts.
    """
    stats = {
        "espn_mappings": 0,
        "primary_name_mappings": 0,
        "alternate_name_mappings": 0,
        "abbreviation_mappings": 0,
        "kalshi_abbrev_mappings": 0,
        "teams_processed": 0,
        "errors": 0,
    }

    async with get_task_session() as session:
        # Build sport_id → sport_key lookup
        sport_result = await session.execute(select(Sport.id, Sport.key))
        sport_key_map = {row[0]: row[1] for row in sport_result.all()}

        # Load all teams
        team_result = await session.execute(
            select(Team).order_by(Team.id)
        )
        teams = team_result.scalars().all()

        for team in teams:
            sport_key = sport_key_map.get(team.sport_id, "")
            stats["teams_processed"] += 1

            # 1. ESPN ID mapping
            if team.espn_id:
                ok = await _register_mapping(
                    session, team.id, "espn", sport_key,
                    source_id=team.espn_id,
                    source_name=team.name,
                    source_abbreviation=team.abbreviation,
                )
                if ok:
                    stats["espn_mappings"] += 1

            # 2. Primary name as odds_api source
            ok = await _register_mapping(
                session, team.id, "odds_api", sport_key,
                source_name=team.name,
                source_abbreviation=team.abbreviation,
            )
            if ok:
                stats["primary_name_mappings"] += 1

            # 3. Alternate names as odds_api source
            for alt_name in (team.alternate_names or []):
                if alt_name and alt_name != team.name:
                    ok = await _register_mapping(
                        session, team.id, "odds_api", sport_key,
                        source_name=str(alt_name),
                    )
                    if ok:
                        stats["alternate_name_mappings"] += 1

            # 4. Abbreviation mapping
            if team.abbreviation:
                ok = await _register_mapping(
                    session, team.id, "odds_api", sport_key,
                    source_abbreviation=team.abbreviation,
                    source_name=team.abbreviation,
                )
                if ok:
                    stats["abbreviation_mappings"] += 1

            # Commit every 50 teams to avoid large transactions
            if stats["teams_processed"] % 50 == 0:
                await session.commit()

        # 5. Seed Kalshi abbreviation mappings
        try:
            from app.utils.prediction_market_matching import _KALSHI_TEAM_ABBREVS
            from app.services.team_identity import normalize_name

            for abbrev, team_fragment in _KALSHI_TEAM_ABBREVS.items():
                # Find a matching team by name fragment
                for team in teams:
                    team_norm = normalize_name(team.name)
                    frag_norm = normalize_name(team_fragment)
                    if not frag_norm:
                        continue

                    # Check if the fragment matches the team name
                    matched = False
                    if frag_norm == team_norm:
                        matched = True
                    elif len(frag_norm) >= 4 and (frag_norm in team_norm or team_norm in frag_norm):
                        matched = True
                    else:
                        # Last-word match (mascot)
                        name_parts = team_norm.split()
                        if len(name_parts) > 1 and frag_norm == name_parts[-1] and len(frag_norm) >= 4:
                            matched = True

                    if matched:
                        sport_key = sport_key_map.get(team.sport_id, "")
                        ok = await _register_mapping(
                            session, team.id, "kalshi", sport_key,
                            source_abbreviation=abbrev,
                            source_name=team_fragment,
                        )
                        if ok:
                            stats["kalshi_abbrev_mappings"] += 1
                        break  # Only match first team found

        except ImportError:
            logger.warning("Could not import _KALSHI_TEAM_ABBREVS for Kalshi backfill")

        await session.commit()

    logger.info("Team identity backfill complete: %s", stats)
    return stats
