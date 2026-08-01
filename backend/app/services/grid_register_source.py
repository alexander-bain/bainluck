"""Build grid-register identities from current source inventory (Queue 295).

Shared by the one-time generator (``scripts/generate_grid_register.py``) and the
daily drift sentinel (``app/tasks/grid_register_sentinel.py``) so that "what the
sources say right now" is computed exactly one way. If the generator and the
sentinel disagreed about the inventory, every run would report phantom drift.

Nothing here reads or writes probabilities — it resolves *identity* only.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FuturesMarket, FuturesOutcome, Team
from app.utils.grid_register import ALLOWED_SOURCES, SCHEMA_VERSION
from app.utils.name_normalization import normalize_team_name
from app.utils.resolution_authority import can_write_winner

logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def load_candidate_markets(session: AsyncSession, config) -> list[tuple]:
    """Return ``[(market, stage_or_None), ...]`` using the grid's existing gating.

    Reuses ``routes/playoffs.py``'s own league/season/column filters so the
    register starts from precisely the market population the grid sees today.
    The register makes the per-cell *choice* explicit; it does not change which
    markets were eligible to be chosen from.
    """
    from app.routes.playoffs import (
        _extract_season_max_year,
        _is_future_season_market,
        _is_past_season_market,
        _market_passes_league_filter,
        _match_market_to_column,
    )

    conditions = [FuturesMarket.external_id.ilike(f"{sk}%") for sk in config.sport_keys]
    for pfx in (config.external_id_prefixes or []):
        conditions.append(FuturesMarket.external_id.ilike(f"{pfx}%"))
    conditions.append(FuturesMarket.llm_sport_category == config.sport_category)

    result = await session.execute(
        select(FuturesMarket).where(
            and_(
                or_(*conditions),
                FuturesMarket.status.in_(("open", "closed", "resolved")),
            )
        )
    )
    markets = [
        m for m in result.scalars().unique().all()
        if _market_passes_league_filter(m.name or "", m.external_id or "", config)
    ]

    max_year = _extract_season_max_year(config.season_pattern)
    if max_year:
        markets = [
            m for m in markets
            if not _is_future_season_market(m.name or "", max_year)
            and not _is_past_season_market(m.name or "", max_year)
        ]

    return [(m, _match_market_to_column(m, config)) for m in markets]


async def canonical_entities(session: AsyncSession) -> dict[str, tuple[str, str]]:
    """``normalized alias -> (entity_key, display name)`` from the Team table.

    Canonical identity comes from ``teams``, not from outcome text — resolving
    "Oklahoma City" and "Oklahoma City Thunder" to one row is the entire point.
    An alias claimed by two different teams is DROPPED rather than arbitrated:
    an ambiguous alias must produce an unresolved report, never a coin flip.
    """
    result = await session.execute(select(Team))
    index: dict[str, tuple[str, str]] = {}
    collisions: set[str] = set()

    for team in result.scalars().all():
        if not team.name:
            continue
        key = normalize_team_name(team.name)
        if not key:
            continue
        aliases = {key}
        parts = team.name.split()
        if parts:
            aliases.add(normalize_team_name(parts[-1]))
        abbreviation = getattr(team, "abbreviation", None)
        if abbreviation:
            aliases.add(normalize_team_name(abbreviation))
        for alt in (getattr(team, "alternate_names", None) or []):
            if isinstance(alt, str) and alt.strip():
                aliases.add(normalize_team_name(alt))

        for alias in aliases:
            if not alias:
                continue
            existing = index.get(alias)
            if existing and existing[0] != key:
                collisions.add(alias)
                continue
            index[alias] = (key, team.name)

    for alias in collisions:
        index.pop(alias, None)
    if collisions:
        logger.info("Grid register: dropped %d colliding team aliases", len(collisions))
    return index


def resolve_entity(
    outcome_name: str,
    entities: dict[str, tuple[str, str]],
) -> tuple[str, str] | None:
    """Resolve an outcome name to one canonical entity, or ``None`` if unclear."""
    norm = normalize_team_name(outcome_name or "")
    if not norm:
        return None
    if norm in entities:
        return entities[norm]
    # Unique containment only. Two candidates is an ambiguity to report.
    hits = {
        value for alias, value in entities.items()
        if alias.startswith(norm + " ") or norm.startswith(alias + " ")
    }
    if len(hits) == 1:
        return next(iter(hits))
    return None


async def build_candidates(
    session: AsyncSession,
    config,
) -> tuple[list[dict], list[dict]]:
    """Observe current inventory as register-shaped candidate rows.

    Returns ``(candidates, unresolved)``. Each candidate carries the fields the
    drift comparison needs: stage, entity, source, season, market/outcome ids,
    external id, status, and terminal result.
    """
    matched = await load_candidate_markets(session, config)
    entities = await canonical_entities(session)

    market_ids = [m.id for m, stage in matched if stage]
    outcomes: dict[int, list[FuturesOutcome]] = defaultdict(list)
    if market_ids:
        res = await session.execute(
            select(FuturesOutcome).where(FuturesOutcome.market_id.in_(market_ids))
        )
        for row in res.scalars().all():
            outcomes[row.market_id].append(row)

    candidates: list[dict] = []
    unresolved: list[dict] = []
    for market, stage in matched:
        if not stage or market.source not in ALLOWED_SOURCES:
            continue
        for outcome in outcomes.get(market.id, ()):
            resolved = resolve_entity(outcome.name, entities)
            if resolved is None:
                unresolved.append({
                    "reason": "entity_unresolved",
                    "stage": stage,
                    "source": market.source,
                    "market_id": market.id,
                    "outcome_id": outcome.id,
                    "outcome_name": outcome.name,
                    "market_name": market.name,
                })
                continue
            entity_key, entity_name = resolved
            graded = outcome.is_winner is not None

            # An ``is_winner`` value only means "settled" if something was
            # ENTITLED to write it. Reading the bare column conflates a real
            # settlement with an unattributed grade, and production is full of
            # the latter: on 2026-08-01 all 61 outcomes of the two LIVE "MLB
            # World Series Champion 2026" markets carried is_winner=False with
            # resolution_source=NULL (authority tier -1) on status='open'. Trusting
            # that column would have written "eliminated" into every MLB cell of a
            # season still being played — a fabricated result on the serving path,
            # which is the one outcome worse than a missing cell.
            #
            # ``can_write_winner`` is the ladder's own predicate for this exact
            # invariant (#845), so the register cannot drift from it: a grade
            # counts on a resolved/closed market, or on any market when an
            # authoritative external settlement asserted it. That second clause is
            # what keeps gotcha #33 working — Kalshi markets that settle but stay
            # status='open' still read as settled, because api_settlement is tier 3.
            if not graded and market.status == "resolved":
                # A settled market whose outcome was never graded has no honest
                # status: it is not live, and calling it "eliminated" invents a
                # result. Report it instead of publishing a guess.
                unresolved.append({
                    "reason": "settled_market_ungraded",
                    "stage": stage,
                    "source": market.source,
                    "market_id": market.id,
                    "outcome_id": outcome.id,
                    "outcome_name": outcome.name,
                    "market_name": market.name,
                })
                continue

            settled = graded and can_write_winner(market.status, outcome.resolution_source)
            candidates.append({
                "stage": stage,
                "entity_key": entity_key,
                "entity_name": entity_name,
                "source": market.source,
                "season": config.season_pattern,
                "market_id": market.id,
                "outcome_id": outcome.id,
                "external_id": market.external_id,
                "market_name": market.name,
                "status": "settled" if settled else "live",
                "terminal_result": (
                    ("won" if outcome.is_winner else "eliminated") if settled else None
                ),
            })

    return candidates, unresolved


def candidates_to_register(
    candidates: list[dict],
    unresolved: list[dict],
    config,
    *,
    version: int = 1,
    supersedes_version: int | None = None,
    observed_at: str | None = None,
) -> tuple[dict[str, Any], list[dict]]:
    """Fold observed candidates into a register, reporting every ambiguity.

    A cell with two candidates from the same source is NOT arbitrated — the old
    "keep the lowest probability" tiebreak was a heuristic standing in for a
    decision. It becomes an unresolved question instead.
    """
    observed = observed_at or now_iso()
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in candidates:
        grouped[(row["stage"], row["entity_key"], row["source"])].append(row)

    ambiguities = list(unresolved)
    entries: list[dict] = []
    for (stage, entity_key, source), rows in sorted(grouped.items()):
        if len(rows) > 1:
            ambiguities.append({
                "reason": "multiple_candidates",
                "stage": stage,
                "entity_key": entity_key,
                "source": source,
                "candidates": [
                    {k: r.get(k) for k in
                     ("market_id", "outcome_id", "market_name", "external_id")}
                    for r in rows
                ],
            })
            continue

        row = rows[0]
        entry = {
            "stage": stage,
            "entity_key": entity_key,
            "entity_name": row["entity_name"],
            "source": source,
            "status": row["status"],
            "market_id": row["market_id"],
            "outcome_id": row["outcome_id"],
            "external_id": row["external_id"],
            "evidence": {
                "kind": "generated_from_source_inventory",
                "observed_at": observed,
                "market_name": row.get("market_name"),
            },
        }
        if row["status"] == "settled":
            entry["terminal_result"] = row["terminal_result"]
        entries.append(entry)

    register: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "league": config.slug,
        "season": config.season_pattern,
        "version": version,
        "generated_at": observed,
        "entries": entries,
    }
    if supersedes_version is not None:
        register["supersedes_version"] = supersedes_version
    return register, ambiguities


async def generate_register(session: AsyncSession, config, **kwargs):
    """Convenience: observe inventory and fold it into a register."""
    candidates, unresolved = await build_candidates(session, config)
    return candidates_to_register(candidates, unresolved, config, **kwargs)
