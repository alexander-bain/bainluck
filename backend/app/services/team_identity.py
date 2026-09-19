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
so subsequent lookups are O(1). That cache is why steps 3 and 4 refuse a tie
rather than break it: a guess written here is read back at step 2 as an exact
match forever after.

Both fuzzy steps score twice — first under ``_strict_name``, which keeps a
trailing initial, and only then under ``normalize_name``, which strips it as a
reserve-team suffix ("Los Angeles C" -> "los angeles"). Kalshi abbreviates a
club to city plus initial, so the strict pass is the one that can tell the
Chargers from the Rams; the loose pass stays behind it for the soccer reserve
sides it was written for.
"""

import logging
import re
from typing import Optional

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.models import Team, TeamIdentityMapping
from app.utils.name_normalization import normalize_name, normalize_team_name

logger = logging.getLogger(__name__)


# "St.Louis Cardinals" and "St. Louis Cardinals" name one club. `normalize_name`
# repairs the missing space; `normalize_team_name` does not, so the strict form
# below applies the same repair before it.
_PERIOD_WITHOUT_SPACE_RE = re.compile(r"\.([A-Za-z])")


def _strict_name(name: str) -> str:
    """Normalize for matching WITHOUT stripping a trailing single letter.

    ``normalize_name`` treats a trailing "C"/"B"/"W"/"II" as a reserve-team suffix
    — correct for "Barcelona B", ruinous for Kalshi's "Los Angeles C", where that
    letter is the only thing separating the Chargers from the Rams. This is the
    form that keeps it. Both sides of a comparison must use the same one.
    """
    if not name:
        return ""
    return normalize_team_name(_PERIOD_WITHOUT_SPACE_RE.sub(r". \1", name))


_SCORE_EXACT = 100
_SCORE_CANDIDATE_WITHIN_TARGET = 60
_SCORE_TARGET_WITHIN_CANDIDATE = 50
_SCORE_LAST_WORD = 40

# Below this a match is not trusted enough to resolve, let alone to register.
_MATCH_FLOOR = 40


def _fuzzy_score(candidate: str, target: str) -> int:
    """Score how well ``candidate`` matches ``target`` (both pre-normalized).

    Returns 0 for no match, higher is better.
    - Exact match: 100
    - Candidate contained in target: 60
    - Target contained in candidate: 50
    - Last-word match (mascot): 40
    - No match: 0

    The two containment directions score differently because they say different
    things about the candidate. "los angeles d" inside "los angeles dodgers"
    explains every character of the candidate; "los angeles" inside
    "los angeles d" leaves the one character that decides which Los Angeles club
    this is unaccounted for. Scored the same — as they were until #7188 — the
    Dodgers and the Angels (whose ``alternate_names`` carry the bare city) tied
    at 60 and the winner was whichever row the query returned first.
    """
    if not candidate or not target:
        return 0

    # Exact match
    if candidate == target:
        return _SCORE_EXACT

    # Containment — only if both long enough to avoid "LA" false positives
    if len(candidate) >= 4 and len(target) >= 4:
        if candidate in target:
            return _SCORE_CANDIDATE_WITHIN_TARGET
        if target in candidate:
            return _SCORE_TARGET_WITHIN_CANDIDATE

    # Last-word match (mascot): "Lakers" == last word of "Los Angeles Lakers"
    target_parts = target.split()
    candidate_parts = candidate.split()
    if len(target_parts) > 1 and len(candidate_parts) == 1:
        if candidate == target_parts[-1] and len(candidate) >= 4:
            return _SCORE_LAST_WORD
    if len(candidate_parts) > 1 and len(target_parts) == 1:
        if target == candidate_parts[-1] and len(target) >= 4:
            return _SCORE_LAST_WORD

    return 0


def _sole_best_team(
    scored: list[tuple[int, int]], floor: int = _MATCH_FLOOR
) -> tuple[Optional[int], bool]:
    """``(team_id, ambiguous)`` for the best score at or above ``floor``.

    ``scored`` is ``(team_id, score)`` in whatever order the query returned.
    Several entries naming the SAME team is agreement, not ambiguity — a club has
    many mapping rows and many alternate names. Two DISTINCT teams tied at the top
    is ambiguity, and the old ``score > best_score`` accumulator resolved it by
    heap order; ``resolve_team`` then wrote that guess into
    ``team_identity_mapping``, where it answered every later lookup for the name at
    score 100, before any fuzzy matching ran. A coin flip became a fact (#7188).

    Any tie between distinct teams refuses, an exact one included. Two rows
    carrying literally the same name are sometimes duplicates of one club
    ("New York R" beside "New York Rangers") and sometimes two real clubs sharing
    a city alias — the Cubs and the White Sox both answer to "Chicago" — and this
    function cannot tell them apart. Guessing is what it is here to stop; folding
    the duplicates is #2693's job.

    The second element distinguishes "nothing came close" from "several did".
    Callers must not fall back to a looser reading of an ambiguous name: the
    looser form is the one that threw away the distinguishing letter, so it turns
    a refusal into a confident wrong answer.
    """
    best_score = 0
    winners: set[int] = set()

    for team_id, score in scored:
        if score < floor:
            continue
        if score > best_score:
            best_score = score
            winners = {team_id}
        elif score == best_score:
            winners.add(team_id)

    if len(winners) == 1:
        return next(iter(winners)), False
    return None, bool(winners)


def _sole_literal_match(name: str, candidates: list[tuple[int, list[str]]]) -> Optional[int]:
    """The one team carrying ``name`` verbatim, ignoring case and outer space.

    This runs before any normalization because normalization is lossy in ways that
    matter here: ``_strict_name`` folds "St Louis Blues" and "St. Louis Blues" to
    one string, and those are two rows for one club, so the tie rule below would
    refuse a club asked for by its own exact name. A raw match is the strongest
    evidence available and only one row has it.
    """
    wanted = name.strip().casefold()
    if not wanted:
        return None
    holders = {
        team_id
        for team_id, raw_names in candidates
        if any(raw.strip().casefold() == wanted for raw in raw_names)
    }
    return next(iter(holders)) if len(holders) == 1 else None


def _resolve_scored(
    strict_scored: list[tuple[int, int]],
    loose_scored: list[tuple[int, int]],
    floor: int = _MATCH_FLOOR,
) -> Optional[int]:
    """Pick a team from the strict scores, falling back to the loose ones.

    The loose pass is a fallback for "the strict form found no purchase at all",
    never a tiebreak for "the strict form was inconclusive". ``normalize_name``
    strips the trailing initial, so for a fragment like "Los Angeles C" the loose
    form is strictly less informative than what the caller asked about: a lone
    cached row named "Los Angeles" scores 50 against the strict form and 100
    against the loose one. Consulting it whenever the strict pass fell short would
    convert exactly the ambiguity this module exists to refuse into a confident
    wrong club (CERT-3130).
    """
    best, ambiguous = _sole_best_team(strict_scored, floor)
    if best is not None:
        return best
    if ambiguous or any(score > 0 for _, score in strict_scored):
        return None

    best, _ambiguous = _sole_best_team(loose_scored, floor)
    return best


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
        name_strict = _strict_name(name)
        name_loose = normalize_name(name)
        if not name_strict and not name_loose:
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

        strict_scored: list[tuple[int, int]] = []
        loose_scored: list[tuple[int, int]] = []
        literal: list[tuple[int, list[str]]] = []

        for mapping in mappings:
            if mapping.team_id is None:
                continue
            source_name = str(mapping.source_name)
            literal.append((mapping.team_id, [source_name]))
            strict_scored.append(
                (mapping.team_id, _fuzzy_score(name_strict, _strict_name(source_name)))
            )
            loose_scored.append(
                (mapping.team_id, _fuzzy_score(name_loose, normalize_name(source_name)))
            )

        # The cache only answers on a name that accounts for the whole fragment.
        # A row named "Los Angeles" is a fact about the city, not about
        # "Los Angeles D", and letting it answer at 50 preempts step 4 — where the
        # canonical teams table would have said Dodgers (CERT-3130).
        best_team_id = _sole_literal_match(name, literal) or _resolve_scored(
            strict_scored, loose_scored, floor=_SCORE_CANDIDATE_WITHIN_TARGET
        )

        if best_team_id is not None:
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
        name_strict = _strict_name(name)
        name_loose = normalize_name(name)
        if not name_strict and not name_loose:
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

        strict_scored: list[tuple[int, int]] = []
        loose_scored: list[tuple[int, int]] = []
        literal: list[tuple[int, list[str]]] = []
        by_id: dict[int, Team] = {}

        for team in teams:
            by_id[team.id] = team
            candidate_names = [team.name] + [str(alt) for alt in (team.alternate_names or [])]
            literal.append((team.id, candidate_names))
            strict_scored.append((
                team.id,
                max(_fuzzy_score(name_strict, _strict_name(n)) for n in candidate_names),
            ))
            loose_scored.append((
                team.id,
                max(_fuzzy_score(name_loose, normalize_name(n)) for n in candidate_names),
            ))

        best_team_id = _sole_literal_match(name, literal) or _resolve_scored(
            strict_scored, loose_scored
        )

        if best_team_id is not None:
            return by_id[best_team_id]
        return None


# Module-level singleton for convenience
team_identity_service = TeamIdentityService()
