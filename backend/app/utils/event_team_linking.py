"""Strict, same-sport event -> team FK linking (#13144).

Resolves ``Event.home_team_id`` and ``Event.away_team_id`` against ``Team`` rows
within the event's own ``sport_id`` using exact canonical name equivalence only
(case, punctuation, ASCII diacritics, and standard whole-word spelling
expansions such as ``St`` -> ``State`` after the first word, ``Mt`` -> ``Mount``,
``Ft`` -> ``Fort``, and cardinal letters).

Design invariants:
- **Strictly same-sport:** a ``basketball_ncaab`` team row can never bind a
  ``basketball_wncaab`` event.
- **No fuzzy / token-overlap scoring:** namesake schools (Michigan vs Michigan
  State, Oregon vs Oregon State, Texas vs Texas A&M, Miami vs Miami (OH),
  Loyola Chicago vs Loyola Maryland) and numbered reserve sides (Columbus Crew 2
  vs Columbus Crew) always refuse.
- **No ``alternate_names`` reads:** avoids #8353 borrowed-alias contamination.
- **Unique-only resolution:** if two distinct ``Team`` rows in the same sport
  collapse to the same key, the key is marked ambiguous and refused (``NULL``).
- **Write-gated by ``accept_team_binding``:** every proposed FK passes #1918's
  write-time invariant before assignment, and existing non-NULL FKs are never
  overwritten.
- **Upcoming-first windowing:** catch-up passes filter to
  ``commence_time >= now - lookback`` ordered ``commence_time ASC`` so old
  historical rows cannot starve upcoming slates behind a row limit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import or_ as sql_or
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.team_binding_invariant import (
    accept_team_binding,
    event_team_names_equivalent,
    expand_event_team_key,
    normalize_event_team_key,
)

__all__ = [
    "SportTeamIndex",
    "build_sport_team_index",
    "event_team_names_equivalent",
    "expand_event_team_key",
    "link_event_sides_from_index",
    "link_unlinked_events_for_sport",
    "link_unlinked_upcoming_events",
    "normalize_event_team_key",
    "resolve_event_team",
    "resolve_team_ids_for_new_event",
]


@dataclass
class SportTeamIndex:
    """Unique-only same-sport lookup from canonical name key to ``Team``."""

    sport_id: int
    by_basic: dict[str, Any] = field(default_factory=dict)
    by_expanded: dict[str, Any] = field(default_factory=dict)


def _register_unique(mapping: dict[str, Any], key: str, team: Any) -> None:
    if not key:
        return
    if key not in mapping:
        mapping[key] = team
        return
    existing = mapping[key]
    if existing is None:
        return
    if getattr(existing, "id", None) != getattr(team, "id", None):
        mapping[key] = None


def build_sport_team_index(sport_id: int, teams: Iterable[Any]) -> SportTeamIndex:
    """Build a strict unique-only index for one ``sport_id``."""
    index = SportTeamIndex(sport_id=sport_id)
    for team in teams:
        if getattr(team, "sport_id", None) != sport_id:
            continue
        team_name = getattr(team, "name", None)
        if not team_name:
            continue
        _register_unique(index.by_basic, normalize_event_team_key(team_name), team)
        _register_unique(index.by_expanded, expand_event_team_key(team_name), team)
    return index


def resolve_event_team(
    team_name: Optional[str],
    index: SportTeamIndex,
    *,
    side: str,
    event_sport_id: int,
    source: str,
    event_id: Optional[int] = None,
    stats: Optional[dict] = None,
) -> Optional[Any]:
    """Resolve one event team name against ``index``, gated by ``accept_team_binding``."""
    if not team_name or index.sport_id != event_sport_id:
        return None

    basic = normalize_event_team_key(team_name)
    if not basic:
        return None

    candidate = None
    if basic in index.by_basic:
        # Ambiguous basic key (None sentinel) fails closed immediately.
        candidate = index.by_basic[basic]
    else:
        expanded = expand_event_team_key(basic)
        if expanded in index.by_expanded:
            candidate = index.by_expanded[expanded]

    if candidate is None:
        return None

    if not accept_team_binding(
        side=side,
        row_name=team_name,
        team=candidate,
        event_sport_id=event_sport_id,
        source=source,
        event_id=event_id,
        stats=stats,
    ):
        return None
    return candidate


def link_event_sides_from_index(
    event: Any,
    index: SportTeamIndex,
    *,
    source: str,
    stats: Optional[dict] = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Fill NULL ``home_team_id`` / ``away_team_id`` on ``event`` from ``index``.

    Never overwrites a populated team FK. When ``dry_run=True`` no attributes
    are mutated and the returned list describes the planned assignments.
    """
    links: list[dict[str, Any]] = []
    event_sport_id = getattr(event, "sport_id", None)
    if event_sport_id is None:
        return links

    for side, id_attr, name_attr in (
        ("home", "home_team_id", "home_team_name"),
        ("away", "away_team_id", "away_team_name"),
    ):
        if getattr(event, id_attr, None) is not None:
            continue
        row_name = getattr(event, name_attr, None)
        matched = resolve_event_team(
            row_name,
            index,
            side=side,
            event_sport_id=event_sport_id,
            source=source,
            event_id=getattr(event, "id", None),
            stats=stats,
        )
        if matched is None:
            continue
        matched_id = getattr(matched, "id", None)
        if matched_id is None:
            continue
        if not dry_run:
            setattr(event, id_attr, matched_id)
        links.append(
            {
                "event_id": getattr(event, "id", None),
                "sport_id": event_sport_id,
                "side": side,
                "event_team_name": row_name,
                "team_id": matched_id,
                "team_name": getattr(matched, "name", None),
            }
        )
    return links


async def resolve_team_ids_for_new_event(
    session: AsyncSession,
    *,
    sport_id: int,
    home_team_name: Optional[str],
    away_team_name: Optional[str],
    source: str = "event_registry",
    stats: Optional[dict] = None,
) -> tuple[Optional[int], Optional[int]]:
    """Resolve ``(home_team_id, away_team_id)`` for a newly created event."""
    from app.models import Team

    result = await session.execute(select(Team).where(Team.sport_id == sport_id))
    teams = list(result.scalars().all())
    if not teams:
        return None, None
    index = build_sport_team_index(sport_id, teams)
    home_team = resolve_event_team(
        home_team_name,
        index,
        side="home",
        event_sport_id=sport_id,
        source=source,
        stats=stats,
    )
    away_team = resolve_event_team(
        away_team_name,
        index,
        side="away",
        event_sport_id=sport_id,
        source=source,
        stats=stats,
    )
    return (
        getattr(home_team, "id", None) if home_team is not None else None,
        getattr(away_team, "id", None) if away_team is not None else None,
    )


async def link_unlinked_events_for_sport(
    session: AsyncSession,
    *,
    sport_id: int,
    now: Optional[datetime] = None,
    lookback_days: int = 1,
    horizon_days: Optional[int] = None,
    limit: int = 500,
    source: str = "sports_poll",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Link upcoming unlinked event sides for one ``sport_id`` in start-time order.

    Filters to ``Event.commence_time >= now - lookback_days`` (and optionally
    ``<= now + horizon_days``) ordered ``Event.commence_time ASC`` so upcoming
    slates are never starved behind old historical unlinked rows.
    """
    from app.models import Event, Team

    ref_now = now or datetime.now(timezone.utc)
    cutoff = ref_now - timedelta(days=lookback_days)

    teams_res = await session.execute(select(Team).where(Team.sport_id == sport_id))
    teams = list(teams_res.scalars().all())
    stats: dict[str, Any] = {
        "sport_id": sport_id,
        "events_scanned": 0,
        "sides_linked": 0,
        "dry_run": dry_run,
        "planned_links": [],
    }
    if not teams:
        return stats

    index = build_sport_team_index(sport_id, teams)

    filters = [
        Event.sport_id == sport_id,
        Event.commence_time >= cutoff,
        sql_or(Event.home_team_id.is_(None), Event.away_team_id.is_(None)),
    ]
    if horizon_days is not None:
        filters.append(Event.commence_time <= ref_now + timedelta(days=horizon_days))

    events_res = await session.execute(
        select(Event)
        .where(*filters)
        .order_by(Event.commence_time.asc())
        .limit(limit)
        .execution_options(populate_existing=True)
    )
    events = list(events_res.scalars().all())
    stats["events_scanned"] = len(events)

    for evt in events:
        links = link_event_sides_from_index(
            evt, index, source=source, stats=stats, dry_run=dry_run
        )
        stats["sides_linked"] += len(links)
        if dry_run:
            stats["planned_links"].extend(links)

    return stats


async def link_unlinked_upcoming_events(
    session: AsyncSession,
    *,
    now: Optional[datetime] = None,
    lookback_days: int = 1,
    horizon_days: int = 7,
    limit_per_sport: int = 500,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Dry-run-first upcoming event team linker across all sports (#13144).

    Defaults to ``dry_run=True`` so callers inspect the exact per-sport ledger
    before any production write is ever authorized.
    """
    from app.models import Event

    ref_now = now or datetime.now(timezone.utc)
    cutoff = ref_now - timedelta(days=lookback_days)
    horizon = ref_now + timedelta(days=horizon_days)

    sport_ids_res = await session.execute(
        select(Event.sport_id)
        .where(
            Event.commence_time >= cutoff,
            Event.commence_time <= horizon,
            sql_or(Event.home_team_id.is_(None), Event.away_team_id.is_(None)),
        )
        .distinct()
    )
    sport_ids = [sid for sid in sport_ids_res.scalars().all() if sid is not None]

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "sports_scanned": len(sport_ids),
        "events_scanned": 0,
        "sides_linked": 0,
        "by_sport": {},
        "planned_links": [],
    }
    for sid in sorted(sport_ids):
        sport_stats = await link_unlinked_events_for_sport(
            session,
            sport_id=sid,
            now=ref_now,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
            limit=limit_per_sport,
            source="upcoming_event_linker",
            dry_run=dry_run,
        )
        summary["events_scanned"] += sport_stats["events_scanned"]
        summary["sides_linked"] += sport_stats["sides_linked"]
        summary["by_sport"][sid] = {
            "events_scanned": sport_stats["events_scanned"],
            "sides_linked": sport_stats["sides_linked"],
        }
        if dry_run:
            summary["planned_links"].extend(sport_stats["planned_links"])

    return summary
