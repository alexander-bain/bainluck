"""A1 (#1020) — Universal identity-graph registry: read path + fold-in seeding.

Layer 0 of the universal-matching plan (``strategy_universal_matching_and_surfaces.md``).
This module owns two things:

1. **The read path** — ``normalize_alias`` + ``resolve_alias``/``resolve_aliases``:
   "resolve a market mention -> an :class:`Entity`" as an indexed O(1) lookup.
   The grammar adapters (A2) and the resolution engine (A4) consume this.
2. **The fold-in seed** — ``seed_from_teams`` / ``seed_competitions_from_sports``:
   populate the registry from the existing ``teams``/``sports`` tables as the
   ``team`` and ``competition`` kinds. It is **additive and idempotent** — it
   NEVER writes to ``teams`` / ``team_identity_mapping``, so existing team
   matching cannot regress (the L1-L4 audit is the guard). ``source_team_id``
   bridges a team entity back to its legacy row for the transition.

The seed writes ``alias_norm`` via the SAME ``normalize_alias`` the read path
uses — that identity is the whole point (a raw-SQL seed would diverge on
diacritics unless the ``unaccent`` extension were guaranteed, which it is not),
so seeding lives here in Python, not in the migration.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Entity,
    EntityAlias,
    Event,
    FuturesMarket,
    FuturesOutcome,
    Sport,
    Team,
    TeamIdentityMapping,
)
from app.utils.event_matcher import player_key
from app.utils.name_normalization import strip_diacritics

logger = logging.getLogger(__name__)

# Entity kinds (kept as constants so callers never pass a typo'd string).
KIND_TEAM = "team"
KIND_PERSON = "person"
KIND_EVENT_CONCEPT = "event_concept"
KIND_COMPETITION = "competition"
ENTITY_KINDS = frozenset({KIND_TEAM, KIND_PERSON, KIND_EVENT_CONCEPT, KIND_COMPETITION})

# Alias types (typed provenance — see EntityAlias docstring).
ALIAS_CANONICAL = "canonical"
ALIAS_COMMON_NAME = "common_name"
ALIAS_ABBREVIATION = "abbreviation"
ALIAS_SOURCE_NAME = "source_name"
ALIAS_TICKER_TOKEN = "ticker_token"

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_WS = re.compile(r"\s+")


def normalize_alias(name: str | None) -> str:
    """Canonical normalization for alias matching.

    Strips diacritics, lowercases, replaces every run of non-alphanumeric
    characters with a single space, and collapses whitespace. Deterministic and
    dependency-free so the seed and the read path produce byte-identical keys.

    Examples:
        "St. Louis Cardinals"   -> "st louis cardinals"
        "Viktor Hovland"        -> "viktor hovland"
        "L.A. Lakers"           -> "l a lakers"
    """
    if not name:
        return ""
    n = strip_diacritics(name).lower()
    n = _NON_ALNUM.sub(" ", n)
    return _WS.sub(" ", n).strip()


# ---------------------------------------------------------------------------
# Read path — resolve a mention to an entity
# ---------------------------------------------------------------------------
async def resolve_alias(
    session: AsyncSession,
    alias: str,
    *,
    kind: Optional[str] = None,
    sport_key: Optional[str] = None,
) -> Optional[Entity]:
    """Resolve a single free-text mention to its :class:`Entity`, or ``None``.

    Matches on the normalized alias. ``kind`` / ``sport_key`` narrow the search
    when the caller already knows the domain (e.g. an NBA ticker → team). When
    multiple entities share a normalized alias, the highest alias-confidence,
    then entity-confidence, wins — deterministic tie-break by entity id.
    """
    norm = normalize_alias(alias)
    if not norm:
        return None

    stmt = (
        select(Entity)
        .join(EntityAlias, EntityAlias.entity_id == Entity.id)
        .where(EntityAlias.alias_norm == norm)
    )
    if kind:
        stmt = stmt.where(Entity.kind == kind)
    if sport_key:
        stmt = stmt.where(Entity.sport_key == sport_key)
    stmt = stmt.order_by(
        EntityAlias.confidence.desc().nullslast(),
        Entity.confidence.desc().nullslast(),
        Entity.id.asc(),
    ).limit(1)

    result = await session.execute(stmt)
    return result.scalars().first()


async def resolve_aliases(
    session: AsyncSession,
    aliases: Iterable[str],
    *,
    kind: Optional[str] = None,
    sport_key: Optional[str] = None,
) -> dict[str, Entity]:
    """Batch variant of :func:`resolve_alias`.

    Returns a map of the ORIGINAL alias string -> resolved :class:`Entity` for
    every input that resolved (unresolved inputs are simply absent). One query.
    """
    wanted = {a: normalize_alias(a) for a in aliases}
    norms = {n for n in wanted.values() if n}
    if not norms:
        return {}

    stmt = (
        select(EntityAlias.alias_norm, EntityAlias.confidence, Entity)
        .join(EntityAlias, EntityAlias.entity_id == Entity.id)
        .where(EntityAlias.alias_norm.in_(norms))
    )
    if kind:
        stmt = stmt.where(Entity.kind == kind)
    if sport_key:
        stmt = stmt.where(Entity.sport_key == sport_key)

    # Best match per normalized alias (highest alias then entity confidence).
    best: dict[str, tuple[float, float, int, Entity]] = {}
    for norm, alias_conf, entity in await session.execute(stmt):
        ac = float(alias_conf) if alias_conf is not None else 1.0
        ec = float(entity.confidence) if entity.confidence is not None else 1.0
        key = (ac, ec, -entity.id)
        cur = best.get(norm)
        if cur is None or key > cur[:3]:
            best[norm] = (ac, ec, -entity.id, entity)

    out: dict[str, Entity] = {}
    for original, norm in wanted.items():
        hit = best.get(norm)
        if hit:
            out[original] = hit[3]
    return out


# ---------------------------------------------------------------------------
# Write helpers — used by the seed and (later) the A2 grammar adapters
# ---------------------------------------------------------------------------
async def add_alias(
    session: AsyncSession,
    entity_id: int,
    alias: str,
    alias_type: str,
    *,
    source: Optional[str] = None,
    confidence: float = 1.0,
) -> bool:
    """Idempotently attach a typed alias to an entity. Returns True if inserted.

    Uses ``ON CONFLICT DO NOTHING`` on the (entity, norm, type, source) unique
    constraint so re-seeding / re-annotating never duplicates or errors.
    """
    norm = normalize_alias(alias)
    if not norm:
        return False
    stmt = (
        pg_insert(EntityAlias)
        .values(
            entity_id=entity_id,
            alias=alias[:300],
            alias_norm=norm[:300],
            alias_type=alias_type,
            source=source,
            confidence=confidence,
        )
        .on_conflict_do_nothing(constraint="uq_entity_alias_norm_type_source")
    )
    result = await session.execute(stmt)
    return bool(result.rowcount)


# ---------------------------------------------------------------------------
# Fold-in seed — teams + competitions (additive, idempotent, non-destructive)
# ---------------------------------------------------------------------------
async def seed_competitions_from_sports(session: AsyncSession) -> dict[str, int]:
    """Seed one ``competition`` entity per row in ``sports`` (league/tour).

    Idempotent: skips sports that already have a competition entity (matched by
    ``sport_id``). Commits are the caller's responsibility.
    """
    stats = {"created": 0, "aliases": 0, "skipped": 0}
    existing = set(
        (
            await session.execute(
                select(Entity.sport_id).where(Entity.kind == KIND_COMPETITION)
            )
        )
        .scalars()
        .all()
    )
    sports = (await session.execute(select(Sport))).scalars().all()
    for sport in sports:
        if sport.id in existing:
            stats["skipped"] += 1
            continue
        entity = Entity(
            kind=KIND_COMPETITION,
            canonical_name=sport.name,
            sport_id=sport.id,
            sport_key=sport.key,
            entity_metadata={"group": sport.group, "active": sport.active},
        )
        session.add(entity)
        await session.flush()
        stats["created"] += 1
        for value, atype in ((sport.name, ALIAS_CANONICAL), (sport.key, ALIAS_SOURCE_NAME)):
            if value and await add_alias(
                session, entity.id, value, atype, source="seed_sports"
            ):
                stats["aliases"] += 1
    return stats


async def seed_from_teams(
    session: AsyncSession, *, batch_size: int = 500
) -> dict[str, int]:
    """Fold the ``teams`` table into the registry as ``team`` entities.

    For every team without an entity yet (matched by ``source_team_id``), create
    a ``team`` entity and typed aliases from: the team name (canonical), the
    abbreviation, every ``alternate_names`` array element (common_name), and
    every distinct ``team_identity_mapping.source_name`` (source_name, tagged
    with the originating source). Additive and idempotent — ``teams`` and
    ``team_identity_mapping`` are read-only here, so existing team matching is
    untouched.
    """
    stats = {"created": 0, "aliases": 0, "skipped": 0}

    # Sport id -> key, so team entities carry a denormalized sport_key.
    sport_keys = {
        sid: skey
        for sid, skey in await session.execute(select(Sport.id, Sport.key))
    }
    already = set(
        (
            await session.execute(
                select(Entity.source_team_id).where(
                    Entity.kind == KIND_TEAM, Entity.source_team_id.isnot(None)
                )
            )
        )
        .scalars()
        .all()
    )

    offset = 0
    while True:
        teams = (
            (
                await session.execute(
                    select(Team).order_by(Team.id).offset(offset).limit(batch_size)
                )
            )
            .scalars()
            .all()
        )
        if not teams:
            break
        offset += batch_size

        for team in teams:
            if team.id in already:
                stats["skipped"] += 1
                continue
            entity = Entity(
                kind=KIND_TEAM,
                canonical_name=team.name,
                slug=team.slug,
                sport_id=team.sport_id,
                sport_key=sport_keys.get(team.sport_id),
                source_team_id=team.id,
                entity_metadata={
                    "abbreviation": team.abbreviation,
                    "espn_id": team.espn_id,
                    "location": team.location,
                },
            )
            session.add(entity)
            await session.flush()
            stats["created"] += 1

            # Aliases: canonical name, abbreviation, alternate names.
            if await add_alias(
                session, entity.id, team.name, ALIAS_CANONICAL, source="seed_teams"
            ):
                stats["aliases"] += 1
            if team.abbreviation and await add_alias(
                session,
                entity.id,
                team.abbreviation,
                ALIAS_ABBREVIATION,
                source="seed_teams",
            ):
                stats["aliases"] += 1
            alt = team.alternate_names
            if isinstance(alt, list):
                for name in alt:
                    if isinstance(name, str) and await add_alias(
                        session, entity.id, name, ALIAS_COMMON_NAME, source="seed_teams"
                    ):
                        stats["aliases"] += 1

        await session.flush()

    # team_identity_mapping.source_name -> source_name aliases, tagged by source.
    tim_rows = await session.execute(
        select(
            TeamIdentityMapping.team_id,
            TeamIdentityMapping.source,
            TeamIdentityMapping.source_name,
        ).where(TeamIdentityMapping.source_name.isnot(None))
    )
    team_to_entity = {
        stid: eid
        for eid, stid in await session.execute(
            select(Entity.id, Entity.source_team_id).where(
                Entity.kind == KIND_TEAM, Entity.source_team_id.isnot(None)
            )
        )
    }
    for team_id, source, source_name in tim_rows:
        entity_id = team_to_entity.get(team_id)
        if not entity_id or not source_name:
            continue
        if await add_alias(
            session,
            entity_id,
            source_name,
            ALIAS_SOURCE_NAME,
            source=source or "team_identity_mapping",
        ):
            stats["aliases"] += 1

    return stats


# ---------------------------------------------------------------------------
# Person fold-in seed — fighters / players / golfers / drivers (A1 "person" kind)
# ---------------------------------------------------------------------------
# Individual (non-team) sports: the two "teams" on an event ARE the two people,
# and a futures field's outcomes ARE the competitors. Matched loosely (prefix or
# substring) because sport keys vary (mma_mixed_martial_arts, tennis_atp, golf_*).
_PERSON_SPORT_PREFIXES = (
    "mma", "boxing", "tennis", "golf", "motorsport", "formula", "nascar",
    "cycling", "ufc", "atp", "wta", "pga", "liv",
)

# Field placeholders that are not people — never seed these as person entities.
_NON_PERSON_FIELD_NAMES = frozenset({
    "yes", "no", "the field", "field", "other", "none", "no winner", "draw",
    "tie", "over", "under", "any other", "no other", "another player",
})


def _is_person_sport_key(key: Optional[str]) -> bool:
    k = (key or "").lower()
    return any(k.startswith(p) or p in k for p in _PERSON_SPORT_PREFIXES)


def _person_ref(sport_key: Optional[str], norm: str) -> str:
    """Stable dedup anchor for a person entity: ``person:<sport_key>:<norm>``.

    Bucketed by sport_key so a golfer and a footballer named "John Smith" stay
    distinct, and a re-run skips already-seeded persons idempotently.
    """
    return f"person:{(sport_key or '').lower()}:{norm}"[:200]


async def _upsert_person(
    session: AsyncSession,
    *,
    name: str,
    sport_id: Optional[int],
    sport_key: Optional[str],
    existing_refs: set[str],
    source: str,
) -> tuple[int, int]:
    """Create one ``person`` entity + canonical & surname aliases if new.

    Returns ``(entities_created, aliases_created)``. Idempotent via
    ``existing_refs`` (the set of person ``external_ref``s seen so far — mutated
    in place). The surname alias (``player_key`` — the SAME key the engine's
    entrant-set / signature machinery uses) is what bridges a market that names a
    competitor by surname only ("Abdullayev") to an event that carries the full
    name ("Tahir Abdullayev"). It is deliberately lower-confidence than the
    canonical alias so a full-name match always outranks a bare-surname collision.
    """
    norm = normalize_alias(name)
    if not norm or norm in _NON_PERSON_FIELD_NAMES or len(norm) < 3:
        return (0, 0)
    ref = _person_ref(sport_key, norm)
    if ref in existing_refs:
        return (0, 0)
    existing_refs.add(ref)

    entity = Entity(
        kind=KIND_PERSON,
        canonical_name=name.strip()[:300],
        sport_id=sport_id,
        sport_key=sport_key,
        external_ref=ref,
        confidence=0.9,
        entity_metadata={"seed_source": source},
    )
    session.add(entity)
    await session.flush()

    aliases = 0
    if await add_alias(
        session, entity.id, name, ALIAS_CANONICAL, source=source, confidence=1.0
    ):
        aliases += 1
    surname = player_key(name)
    if surname and surname != norm and await add_alias(
        session, entity.id, surname, ALIAS_COMMON_NAME, source=source, confidence=0.6
    ):
        aliases += 1
    return (1, aliases)


async def _existing_person_refs(session: AsyncSession) -> set[str]:
    return set(
        (
            await session.execute(
                select(Entity.external_ref).where(
                    Entity.kind == KIND_PERSON, Entity.external_ref.isnot(None)
                )
            )
        )
        .scalars()
        .all()
    )


async def seed_persons_from_events(
    session: AsyncSession, *, batch_size: int = 1000, commit_each: bool = False
) -> dict[str, int]:
    """Fold individual-sport EVENTS into the registry as ``person`` entities.

    For an event in an individual sport (MMA/boxing/tennis/motorsport), the
    ``home_team_name`` / ``away_team_name`` ARE the two competitors (people), not
    teams. Create a person entity + canonical & surname aliases per distinct
    ``(sport_key, name)``. Additive & idempotent (persons matched by
    ``external_ref``); reads ``events`` / ``sports`` only — never writes them, so
    existing team/event matching cannot regress.

    ``commit_each`` commits per batch so a very large fold-in persists
    incrementally (never one multi-hundred-thousand-row transaction that can time
    out or OOM a dyno) and a re-run resumes via the idempotency guard. Left False
    for the dry-run path, which rolls the whole session back.
    """
    stats = {"created": 0, "aliases": 0, "events_scanned": 0}
    existing_refs = await _existing_person_refs(session)

    person_sports = {
        sid: skey
        for sid, skey in await session.execute(select(Sport.id, Sport.key))
        if _is_person_sport_key(skey)
    }
    if not person_sports:
        return stats
    sport_ids = list(person_sports.keys())

    offset = 0
    while True:
        rows = (
            await session.execute(
                select(
                    Event.sport_id, Event.home_team_name, Event.away_team_name
                )
                .where(Event.sport_id.in_(sport_ids))
                .order_by(Event.id)
                .offset(offset)
                .limit(batch_size)
            )
        ).all()
        if not rows:
            break
        offset += batch_size
        for sport_id, home, away in rows:
            stats["events_scanned"] += 1
            skey = person_sports.get(sport_id)
            for name in (home, away):
                if not isinstance(name, str) or not name.strip():
                    continue
                c, a = await _upsert_person(
                    session,
                    name=name,
                    sport_id=sport_id,
                    sport_key=skey,
                    existing_refs=existing_refs,
                    source="seed_persons_events",
                )
                stats["created"] += c
                stats["aliases"] += a
        await (session.commit() if commit_each else session.flush())
    return stats


async def seed_persons_from_futures_fields(
    session: AsyncSession,
    *,
    batch_size: int = 2000,
    categories: tuple[str, ...] = ("golf", "motorsports"),
    commit_each: bool = False,
) -> dict[str, int]:
    """Fold person entrant-FIELDS from futures outcomes into ``person`` entities.

    Scoped to categories whose outcomes are unambiguously people: golf winner /
    make-cut / matchup fields and motorsport driver fields. (Tennis persons come
    from ``seed_persons_from_events``; award nominees are intentionally deferred —
    a Best-Actor nominee vs a Best-Picture title needs per-market typing, not a
    blanket fold-in.) Additive & idempotent; reads ``futures_*`` only.
    ``commit_each`` commits per batch (see :func:`seed_persons_from_events`).
    """
    stats = {"created": 0, "aliases": 0, "outcomes_scanned": 0}
    existing_refs = await _existing_person_refs(session)

    offset = 0
    while True:
        rows = (
            await session.execute(
                select(FuturesOutcome.name, FuturesMarket.llm_sport_category)
                .join(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
                .where(FuturesMarket.llm_sport_category.in_(list(categories)))
                .order_by(FuturesOutcome.id)
                .offset(offset)
                .limit(batch_size)
            )
        ).all()
        if not rows:
            break
        offset += batch_size
        for name, category in rows:
            stats["outcomes_scanned"] += 1
            if not isinstance(name, str) or not name.strip():
                continue
            c, a = await _upsert_person(
                session,
                name=name,
                sport_id=None,
                sport_key=category,
                existing_refs=existing_refs,
                source="seed_persons_futures",
            )
            stats["created"] += c
            stats["aliases"] += a
        await (session.commit() if commit_each else session.flush())
    return stats


async def registry_counts(session: AsyncSession) -> dict[str, int]:
    """Return quick coverage counts for reporting / audit ("registry queryable")."""
    by_kind = {
        kind: count
        for kind, count in await session.execute(
            select(Entity.kind, func.count()).group_by(Entity.kind)
        )
    }
    total_aliases = (
        await session.execute(select(func.count()).select_from(EntityAlias))
    ).scalar_one()
    return {
        "entities_total": sum(by_kind.values()),
        "aliases_total": int(total_aliases),
        **{f"kind_{k}": v for k, v in by_kind.items()},
    }
