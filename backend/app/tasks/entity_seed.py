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


# #12042: the matchup backfill walks Polymarket groups in `group_id` order, a
# bounded batch at a time, and stops on a time budget. It used to load every
# Polymarket row (1.72M on Nov 11) into one Python list through OFFSET pages and
# then group them in memory; on the 512 MB background worker it was killed (R15)
# mid-run and logged no success in three days. Every row has a `group_id`
# (0 NULL on Nov 11), so the walk reaches every group. The cursor persists in
# Redis, so a run that stops on the budget resumes where it stopped.
_MATCHUP_GROUPS_PER_BATCH = 500
_MATCHUP_RUN_SECONDS = 600
_MATCHUP_CURSOR_KEY = "bainluck:poly_matchups:group_cursor"
_MATCHUP_CURSOR_TTL_S = 7 * 86400


def plan_matchup_updates(members: list[dict]) -> tuple[int, list[tuple[int, str]]]:
    """(game groups, [(market id, matchup title)]) for one batch of group members.

    The same rule as before: a group is a game group when a sibling's name parses
    as "A vs. B", and each member whose own name doesn't parse and that has no
    title yet gets the group's matchup."""
    from app.utils.polymarket_matchup_backfill import (
        group_matchup,
        needs_matchup_backfill,
    )

    by_group: dict[str, list[dict]] = defaultdict(list)
    for m in members:
        by_group[m["group_id"]].append(m)
    game_groups = 0
    to_update: list[tuple[int, str]] = []
    for group in by_group.values():
        matchup = group_matchup(m["name"] for m in group)
        if not matchup:
            continue  # not a game group — no sibling names a matchup
        game_groups += 1
        for m in group:
            if needs_matchup_backfill(m["name"], m["matchup_title"]):
                to_update.append((m["id"], matchup))
    return game_groups, to_update


_APPLY_MATCHUPS_SQL = """
    UPDATE futures_markets fm
    SET market_metadata = COALESCE(fm.market_metadata, '{}'::jsonb)
                          || jsonb_build_object('matchup_title', v.title)
    FROM unnest(CAST(:ids AS bigint[]), CAST(:titles AS text[])) AS v(id, title)
    WHERE fm.id = v.id
      AND COALESCE(fm.market_metadata->>'matchup_title', '') = ''
"""


def _monotonic() -> float:
    import time

    return time.monotonic()


async def backfill_polymarket_matchups_impl(
    all_groups: bool = False,
    *,
    groups_per_batch: int = _MATCHUP_GROUPS_PER_BATCH,
    max_seconds: float = _MATCHUP_RUN_SECONDS,
) -> dict:
    """Backfill ``matchup_title`` onto Polymarket game sub-markets.

    Mirrors ``scripts/backfill_polymarket_matchups.py`` in-worker: recovers the
    "A vs. B" matchup from a sibling row in the SAME Polymarket group (never from
    the event) so the resolution engine can read both participants. Idempotent —
    only writes where ``matchup_title`` is missing. Scoped to LINKED poly markets
    by default (the rows the win-prob blend + shadow audit measure).

    Bounded (#12042): one batch is at most ``groups_per_batch`` groups, written
    with one UPDATE and committed; the run stops after ``max_seconds`` and the
    next run resumes from the saved ``group_id``. ``complete`` says whether this
    run reached the last group (the cursor then resets for the next pass)."""
    from sqlalchemy import select, text

    from app.models.models import FuturesMarket
    from app.tasks.redis_state import get_redis_client

    linked_only = not all_groups
    cursor_key = f"{_MATCHUP_CURSOR_KEY}:{'linked' if linked_only else 'all'}"
    try:
        rc = get_redis_client()
        raw = rc.get(cursor_key)
        after = (raw.decode() if isinstance(raw, bytes) else raw) or ""
    except Exception:
        rc, after = None, ""
    started_after = after

    started = _monotonic()
    batches = rows_scanned = groups_scanned = game_groups = needed = applied = 0
    complete = False
    async with get_task_session(statement_timeout_ms=60_000) as session:
        while _monotonic() - started < max_seconds:
            gstmt = (
                select(FuturesMarket.group_id)
                .where(FuturesMarket.source == "polymarket")
                .where(FuturesMarket.group_id > after)
                .distinct()
                .order_by(FuturesMarket.group_id)
                .limit(groups_per_batch)
            )
            if linked_only:
                gstmt = gstmt.where(FuturesMarket.event_id.isnot(None))
            group_ids = [g for (g,) in (await session.execute(gstmt)).all()]
            if not group_ids:
                complete = True
                break

            # Id order, as the old reader had: when two sibling names of equal
            # length both parse, `group_matchup` keeps the first, so the lower id
            # must come first or the stored title can change between runs.
            mstmt = (
                select(
                    FuturesMarket.id,
                    FuturesMarket.name,
                    FuturesMarket.group_id,
                    FuturesMarket.market_metadata["matchup_title"].astext,
                )
                .where(
                    FuturesMarket.source == "polymarket",
                    FuturesMarket.group_id.in_(group_ids),
                )
                .order_by(FuturesMarket.id)
            )
            if linked_only:
                mstmt = mstmt.where(FuturesMarket.event_id.isnot(None))
            members = [
                {"id": mid, "name": name, "group_id": gid, "matchup_title": mt}
                for mid, name, gid, mt in (await session.execute(mstmt)).all()
            ]
            batch_games, to_update = plan_matchup_updates(members)
            if to_update:
                res = await session.execute(
                    text(_APPLY_MATCHUPS_SQL),
                    {
                        "ids": [mid for mid, _ in to_update],
                        "titles": [title for _, title in to_update],
                    },
                )
                applied += res.rowcount or 0
            await session.commit()

            batches += 1
            rows_scanned += len(members)
            groups_scanned += len(group_ids)
            game_groups += batch_games
            needed += len(to_update)
            after = group_ids[-1]
            if rc is not None:
                try:
                    rc.setex(cursor_key, _MATCHUP_CURSOR_TTL_S, after)
                except Exception:
                    pass  # a lost cursor only means the next run starts over
            if len(group_ids) < groups_per_batch:
                complete = True
                break

        if complete and rc is not None:
            try:
                rc.delete(cursor_key)
            except Exception:
                pass  # the next run then finds no groups past the cursor and resets

        result = {
            "ok": True,
            "linked_only": linked_only,
            "complete": complete,
            "started_after": started_after,
            "stopped_after": after,
            "batches": batches,
            "groups_scanned": groups_scanned,
            "rows_scanned": rows_scanned,
            "game_groups": game_groups,
            "needed": needed,
            "applied": applied,
            "seconds": round(_monotonic() - started, 1),
        }
        await _write_seed_marker(session, "seed_diag:poly_matchups", result)
        return result
