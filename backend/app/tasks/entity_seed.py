"""#171 — Celery execution rails for the entity-registry seeds.

The A1 person fold-in (#1020) and the A2 Polymarket matchup title-backfill
(#1021) shipped as one-off scripts meant for ``heroku run``. From the sandboxed
crank ``heroku run`` returns EPERM, so the seeds never executed in production and
the MMA cross-source cutover (#1024) stayed on its pre-seed baseline. These task
impls wrap the SAME service/util functions the scripts call so the admin trigger
endpoints can enqueue them — no human terminal required (removes the
"needs-a-human-terminal" class permanently).

Both are additive + idempotent: already-folded persons are skipped via
``external_ref`` and matchup rows are only written where ``matchup_title`` is
missing, so a re-trigger RESUMES rather than duplicating, and a
``SoftTimeLimitExceeded`` mid-run leaves the committed per-batch progress intact.

Results are surfaced two ways: the task return value (readable via
``GET /api/admin/audit/task/{task_id}``) and a ``seed_diag:*`` marker row on the
``entities`` table readable via ``POST /api/admin/db-query`` — Heroku one-off
dyno stdout is unreachable from the sandboxed CLI, and the async result backend
can be flaky, so the DB marker is the durable proof of counts.
"""
import json
import traceback
from collections import defaultdict

from app.tasks.base import get_task_session

_PAGE = 5000


async def _write_seed_marker(session, ref: str, payload: dict) -> None:
    """Persist a run result into a ``seed_diag`` marker row on ``entities``.

    Uses a dedicated ``seed_diag`` kind so it never collides with real entities;
    merges into ``entity_metadata`` via a Core ``||`` JSONB merge (gotcha #4 — no
    ORM attribute assignment for JSONB). Runs its own committed transaction so it
    survives even when the seed itself raised (caller rolls back first)."""
    from sqlalchemy import cast, func, literal, select, update
    from sqlalchemy.dialects.postgresql import JSONB

    from app.models.models import Entity

    existing = (
        await session.execute(
            select(Entity.id).where(Entity.external_ref == ref)
        )
    ).scalar_one_or_none()
    md = {"payload": json.dumps(payload, default=str)[:9000]}
    if existing:
        await session.execute(
            update(Entity)
            .where(Entity.id == existing)
            .values(
                entity_metadata=func.coalesce(
                    Entity.entity_metadata, cast(literal("{}"), JSONB)
                ).op("||")(cast(literal(json.dumps(md)), JSONB))
            )
        )
    else:
        session.add(
            Entity(
                kind="seed_diag",
                canonical_name=ref.split(":", 1)[-1],
                external_ref=ref,
                entity_metadata=md,
            )
        )
    await session.commit()


async def seed_entity_registry_impl(persons_only: bool = True) -> dict:
    """Run the A1 fold-in seed (persons by default; teams/competitions if asked).

    Mirrors ``scripts/seed_entity_registry.py`` but in-worker. ``commit_each`` is
    always True here (never one huge transaction that can OOM/time out a worker),
    so partial progress persists across a soft-time-limit overrun."""
    from app.services.entity_registry import (
        canonicalize_entities,
        registry_counts,
        seed_competitions_from_sports,
        seed_from_teams,
        seed_persons_from_events,
        seed_persons_from_futures_fields,
    )

    async with get_task_session() as session:
        before = await registry_counts(session)
        result: dict = {"persons_only": persons_only, "before": before}
        try:
            if not persons_only:
                result["competitions"] = await seed_competitions_from_sports(session)
                result["teams"] = await seed_from_teams(session)
            result["persons_events"] = await seed_persons_from_events(
                session, commit_each=True
            )
            result["persons_futures"] = await seed_persons_from_futures_fields(
                session, commit_each=True
            )
            await session.commit()
            # The seed re-creates one entity per sport_key by design (homonym
            # safety), so it re-inflates the same-family dups every run. Collapse
            # them right after so the registry stays canonical (idempotent — a
            # clean registry yields 0 merges). #175 Item 1.
            result["canonicalize"] = await canonicalize_entities(session)
            result["after"] = await registry_counts(session)
            result["ok"] = True
        except Exception:
            # commit_each already persisted prior batches; roll back the failed
            # statement so the marker write below runs in a clean transaction,
            # then re-raise so Celery records the overrun/failure.
            await session.rollback()
            result["ok"] = False
            result["error"] = traceback.format_exc()[-4000:]
            await _write_seed_marker(session, "seed_diag:persons", result)
            raise
        await _write_seed_marker(session, "seed_diag:persons", result)
        return result


async def canonicalize_entities_impl(dry_run: bool = False) -> dict:
    """Collapse same-family duplicate entities (#175 Item 1) in-worker.

    Wraps :func:`entity_registry.canonicalize_entities` so the merge can run
    on-demand without a full re-seed (the seed also calls it at the end). Additive
    + census-gated + idempotent — see the service docstring. Writes a
    ``seed_diag:canonicalize`` marker for durable proof of counts."""
    from app.services.entity_registry import canonicalize_entities, registry_counts

    async with get_task_session() as session:
        before = await registry_counts(session)
        result: dict = {"before": before, "dry_run": dry_run}
        try:
            result["canonicalize"] = await canonicalize_entities(
                session, dry_run=dry_run
            )
            result["after"] = await registry_counts(session)
            result["ok"] = True
        except Exception:
            await session.rollback()
            result["ok"] = False
            result["error"] = traceback.format_exc()[-4000:]
            await _write_seed_marker(session, "seed_diag:canonicalize", result)
            raise
        await _write_seed_marker(session, "seed_diag:canonicalize", result)
        return result


async def backfill_polymarket_matchups_impl(all_groups: bool = False) -> dict:
    """Backfill ``matchup_title`` onto Polymarket game sub-markets.

    Mirrors ``scripts/backfill_polymarket_matchups.py`` in-worker: recovers the
    "A vs. B" matchup from a sibling row in the SAME Polymarket group (never from
    the event) so the resolution engine can read both participants. Idempotent —
    only writes where ``matchup_title`` is missing. Scoped to LINKED poly markets
    by default (the rows the win-prob blend + shadow audit measure)."""
    from sqlalchemy import cast, func, literal, select, update
    from sqlalchemy.dialects.postgresql import JSONB

    from app.models.models import FuturesMarket
    from app.utils.polymarket_matchup_backfill import (
        group_matchup,
        needs_matchup_backfill,
    )

    linked_only = not all_groups
    async with get_task_session() as session:
        rows: list[dict] = []
        offset = 0
        while True:
            stmt = (
                select(
                    FuturesMarket.id,
                    FuturesMarket.name,
                    FuturesMarket.group_id,
                    FuturesMarket.market_metadata["polymarket_event_id"].astext,
                    FuturesMarket.market_metadata["matchup_title"].astext,
                )
                .where(FuturesMarket.source == "polymarket")
                .order_by(FuturesMarket.id)
                .offset(offset)
                .limit(_PAGE)
            )
            if linked_only:
                stmt = stmt.where(FuturesMarket.event_id.isnot(None))
            batch = (await session.execute(stmt)).all()
            if not batch:
                break
            offset += _PAGE
            for mid, name, group_id, poly_ev, matchup_title in batch:
                gk = group_id or (f"polymarket:{poly_ev}" if poly_ev else None)
                if not gk:
                    continue
                rows.append(
                    {"id": mid, "name": name, "gk": gk, "matchup_title": matchup_title}
                )

        by_group: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_group[r["gk"]].append(r)

        game_groups = 0
        to_update: list[tuple[int, str]] = []
        for members in by_group.values():
            matchup = group_matchup(m["name"] for m in members)
            if not matchup:
                continue  # not a game group — no sibling names a matchup
            game_groups += 1
            for m in members:
                if needs_matchup_backfill(m["name"], m["matchup_title"]):
                    to_update.append((m["id"], matchup))

        empty = cast(literal("{}"), JSONB)
        applied = 0
        for mid, mt in to_update:
            merged = func.coalesce(FuturesMarket.market_metadata, empty).op("||")(
                func.jsonb_build_object("matchup_title", mt)
            )
            await session.execute(
                update(FuturesMarket)
                .where(FuturesMarket.id == mid)
                .values(market_metadata=merged)
            )
            applied += 1
            if applied % 2000 == 0:
                await session.commit()
        await session.commit()

        result = {
            "ok": True,
            "linked_only": linked_only,
            "rows_scanned": len(rows),
            "game_groups": game_groups,
            "needed": len(to_update),
            "applied": applied,
        }
        await _write_seed_marker(session, "seed_diag:poly_matchups", result)
        return result
