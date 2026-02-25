"""Canonical team identity resolution.

Single service for resolving team identities across all data sources.
Replaces ad-hoc team name matching scattered across espn_sync, statpal_sync,
prediction_market_matching, team_linking, and events.py.

Resolution priority:
1. Exact match on team_identity_mapping by (source, source_id, sport_key)
2. Exact match on team_identity_mapping by (source, source_name, sport_key)
3. Fuzzy name match on team_identity_mapping.source_name (any source)
4. Fuzzy name match on teams.name / teams.alternate_names
5. Return None

Auto-registration: when fuzzy matching succeeds, the mapping is registered
so subsequent lookups are O(1).
"""

import unicodedata
import logging
from typing import Optional

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.models import Team, TeamIdentityMapping

logger = logging.getLogger(__name__)


# =============================================================================
# Name normalization (canonical copy — replaces copies in team_linking.py
# and espn_sync.py)
# =============================================================================

# Apostrophe/quote variants to unify
_APOSTROPHE_CHARS = ("\u2018", "\u2019", "\u02BB", "\u02BC", "\u0060", "\u00B4", "\u2032")


def normalize_name(name: str) -> str:
    """Normalize team name for matching.

    NFD decomposition + accent stripping + apostrophe unification + lowercase.
    Consolidates the copies in team_linking.py and espn_sync.py.
    """
    nfkd = unicodedata.normalize("NFD", name)
    stripped = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    for ch in _APOSTROPHE_CHARS:
        stripped = stripped.replace(ch, "'")
    return stripped.lower().strip()


def _fuzzy_score(candidate: str, target: str) -> int:
    """Score how well ``candidate`` matches ``target`` (both pre-normalized).

    Returns 0 for no match, higher is better.
    - Exact match: 100
    - Containment (long strings only): 60
    - Last-word match (mascot): 40
    - No match: 0
    """
    if not candidate or not target:
        return 0

    # Exact match
    if candidate == target:
        return 100

    # Containment — only if both long enough to avoid "LA" false positives
    if len(candidate) >= 4 and len(target) >= 4:
        if candidate in target or target in candidate:
            return 60

    # Last-word match (mascot): "Lakers" == last word of "Los Angeles Lakers"
    target_parts = target.split()
    candidate_parts = candidate.split()
    if len(target_parts) > 1 and len(candidate_parts) == 1:
        if candidate == target_parts[-1] and len(candidate) >= 4:
            return 40
    if len(candidate_parts) > 1 and len(target_parts) == 1:
        if target == candidate_parts[-1] and len(target) >= 4:
            return 40

    return 0


# =============================================================================
# TeamIdentityService
# =============================================================================

class TeamIdentityService:
    """Resolves team identities across external data sources."""

    async def resolve_team(
        self,
        session: AsyncSession,
        source: str,
        sport_key: str,
        *,
        source_id: Optional[str] = None,
        source_name: Optional[str] = None,
        source_abbreviation: Optional[str] = None,
    ) -> Optional[Team]:
        """Find our Team record for a team from any external source.

        Resolution priority:
        1. Exact match by (source, source_id, sport_key) in mapping table
        2. Exact match by (source, source_name, sport_key) in mapping table
        3. Fuzzy name match on mapping table source_name (any source)
        4. Fuzzy name match on teams.name / teams.alternate_names
        5. Return None

        When step 3 or 4 succeeds, auto-registers the mapping for future lookups.
        """
        # Step 1: Exact source_id match
        if source_id:
            team = await self._lookup_by_source_id(session, source, source_id, sport_key)
            if team:
                return team

        # Step 2: Exact source_name match
        if source_name:
            team = await self._lookup_by_source_name(session, source, source_name, sport_key)
            if team:
                return team

        # Step 3: Fuzzy match on mapping table (any source)
        name_to_match = source_name or source_abbreviation
        if name_to_match:
            team = await self._fuzzy_match_mappings(session, name_to_match, sport_key)
            if team:
                await self.register_team_identity(
                    session, team.id, source, sport_key,
                    source_id=source_id,
                    source_name=source_name,
                    source_abbreviation=source_abbreviation,
                )
                return team

        # Step 4: Fuzzy match on teams table
        if name_to_match:
            team = await self._fuzzy_match_teams(session, name_to_match, sport_key)
            if team:
                await self.register_team_identity(
                    session, team.id, source, sport_key,
                    source_id=source_id,
                    source_name=source_name,
                    source_abbreviation=source_abbreviation,
                )
                return team

        return None

    async def register_team_identity(
        self,
        session: AsyncSession,
        team_id: int,
        source: str,
        sport_key: str,
        *,
        source_id: Optional[str] = None,
        source_name: Optional[str] = None,
        source_abbreviation: Optional[str] = None,
    ) -> None:
        """Register a team identity mapping. Upserts — safe to call repeatedly."""
        if not source_id and not source_name:
            return  # Nothing to register

        # Build the values dict
        values = {
            "team_id": team_id,
            "source": source,
            "sport_key": sport_key,
            "source_id": source_id,
            "source_name": source_name,
            "source_abbreviation": source_abbreviation,
            "updated_at": func.now(),
        }

        # Use source_id-based upsert if we have source_id
        if source_id:
            stmt = pg_insert(TeamIdentityMapping).values(values)
            # ON CONFLICT on the partial unique index (source, source_id, sport_key)
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
            # Use source_name-based upsert
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

    async def resolve_from_kalshi_ticker(
        self,
        session: AsyncSession,
        ticker: str,
    ) -> tuple[Optional[Team], Optional[Team]]:
        """Extract and resolve both teams from a Kalshi game ticker.

        Uses ``extract_teams_from_ticker()`` from prediction_market_matching.py
        to parse team name fragments, then resolves each via the mapping table.
        """
        from app.utils.prediction_market_matching import extract_teams_from_ticker
        from app.utils.sport_keys import get_sport_key_from_ticker

        result = extract_teams_from_ticker(ticker)
        if not result:
            return (None, None)

        team_a_name, team_b_name = result
        sport_key = get_sport_key_from_ticker(ticker) or ""

        team_a = await self.resolve_team(
            session, "kalshi", sport_key,
            source_name=team_a_name,
        )
        team_b = await self.resolve_team(
            session, "kalshi", sport_key,
            source_name=team_b_name,
        )
        return (team_a, team_b)

    async def find_teams_for_event(
        self,
        session: AsyncSession,
        home_team_name: str,
        away_team_name: str,
        sport_key: str,
    ) -> tuple[Optional[Team], Optional[Team]]:
        """Resolve home and away teams for an event."""
        home = await self.resolve_team(
            session, "odds_api", sport_key,
            source_name=home_team_name,
        )
        away = await self.resolve_team(
            session, "odds_api", sport_key,
            source_name=away_team_name,
        )
        return (home, away)

    async def get_mappings_for_team(
        self,
        session: AsyncSession,
        team_id: int,
    ) -> list[TeamIdentityMapping]:
        """Get all identity mappings for a team (admin/debug use)."""
        result = await session.execute(
            select(TeamIdentityMapping).where(
                TeamIdentityMapping.team_id == team_id,
            ).order_by(TeamIdentityMapping.source)
        )
        return list(result.scalars().all())

    async def get_unmapped_teams(
        self,
        session: AsyncSession,
        sport_key: Optional[str] = None,
    ) -> list[Team]:
        """Find teams with no identity mappings (need attention)."""
        subq = select(TeamIdentityMapping.team_id).distinct()
        query = select(Team).where(~Team.id.in_(subq))
        if sport_key:
            from app.models.models import Sport
            sport_subq = select(Sport.id).where(Sport.key == sport_key)
            query = query.where(Team.sport_id.in_(sport_subq))
        result = await session.execute(query.order_by(Team.name).limit(200))
        return list(result.scalars().all())

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _lookup_by_source_id(
        self,
        session: AsyncSession,
        source: str,
        source_id: str,
        sport_key: str,
    ) -> Optional[Team]:
        """Step 1: exact match on (source, source_id, sport_key)."""
        result = await session.execute(
            select(Team).join(
                TeamIdentityMapping,
                TeamIdentityMapping.team_id == Team.id,
            ).where(
                TeamIdentityMapping.source == source,
                TeamIdentityMapping.source_id == source_id,
                or_(
                    TeamIdentityMapping.sport_key == sport_key,
                    TeamIdentityMapping.sport_key.is_(None),
                ),
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def _lookup_by_source_name(
        self,
        session: AsyncSession,
        source: str,
        source_name: str,
        sport_key: str,
    ) -> Optional[Team]:
        """Step 2: exact match on (source, source_name, sport_key)."""
        result = await session.execute(
            select(Team).join(
                TeamIdentityMapping,
                TeamIdentityMapping.team_id == Team.id,
            ).where(
                TeamIdentityMapping.source == source,
                TeamIdentityMapping.source_name == source_name,
                or_(
                    TeamIdentityMapping.sport_key == sport_key,
                    TeamIdentityMapping.sport_key.is_(None),
                ),
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def _fuzzy_match_mappings(
        self,
        session: AsyncSession,
        name: str,
        sport_key: str,
    ) -> Optional[Team]:
        """Step 3: fuzzy match against mapping table source_name (any source)."""
        name_norm = normalize_name(name)
        if not name_norm:
            return None

        # Get sport key prefix for sport-scoped matching
        prefix = sport_key.split("_")[0] if sport_key and "_" in sport_key else sport_key

        # Query all mappings for this sport family
        result = await session.execute(
            select(TeamIdentityMapping).where(
                TeamIdentityMapping.source_name.isnot(None),
                or_(
                    TeamIdentityMapping.sport_key == sport_key,
                    TeamIdentityMapping.sport_key.like(f"{prefix}%") if prefix else True,
                    TeamIdentityMapping.sport_key.is_(None),
                ),
            )
        )
        mappings = result.scalars().all()

        best_team_id = None
        best_score = 0

        for mapping in mappings:
            mapping_name_norm = normalize_name(mapping.source_name)
            score = _fuzzy_score(name_norm, mapping_name_norm)
            if score > best_score:
                best_score = score
                best_team_id = mapping.team_id

        if best_team_id and best_score >= 40:
            team_result = await session.execute(
                select(Team).where(Team.id == best_team_id)
            )
            return team_result.scalar_one_or_none()
        return None

    async def _fuzzy_match_teams(
        self,
        session: AsyncSession,
        name: str,
        sport_key: str,
    ) -> Optional[Team]:
        """Step 4: fuzzy match on teams.name / teams.alternate_names."""
        name_norm = normalize_name(name)
        if not name_norm:
            return None

        # Get sport key prefix for sport-scoped matching
        prefix = sport_key.split("_")[0] if sport_key and "_" in sport_key else sport_key

        # Query teams for this sport family
        from app.models.models import Sport
        query = select(Team)
        if prefix:
            query = query.join(Sport, Sport.id == Team.sport_id).where(
                Sport.key.like(f"{prefix}%")
            )
        result = await session.execute(query)
        teams = result.scalars().all()

        best_team = None
        best_score = 0

        for team in teams:
            # Score against primary name
            score = _fuzzy_score(name_norm, normalize_name(team.name))

            # Score against alternate names
            for alt in (team.alternate_names or []):
                alt_score = _fuzzy_score(name_norm, normalize_name(str(alt)))
                score = max(score, alt_score)

            if score > best_score:
                best_score = score
                best_team = team

        if best_team and best_score >= 40:
            return best_team
        return None


# Module-level singleton for convenience
team_identity_service = TeamIdentityService()
