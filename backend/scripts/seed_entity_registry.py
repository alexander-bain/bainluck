#!/usr/bin/env python3
"""A1 (#1020) — Seed the entity registry from teams + sports (fold-in).

Idempotent + additive: creates ``competition`` entities from ``sports`` and
``team`` entities (plus typed aliases) from ``teams`` / ``team_identity_mapping``.
NEVER writes to teams / team_identity_mapping, so existing team matching cannot
regress (the L1-L4 audit is the guard). Safe to re-run — already-folded rows are
skipped via ``source_team_id`` / ``sport_id``.

Usage:
    heroku run --app bainluck python3 backend/scripts/seed_entity_registry.py
    # dry-run projection (no writes):
    heroku run --app bainluck python3 backend/scripts/seed_entity_registry.py --dry-run
"""
import argparse
import asyncio
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.database import async_session_maker  # noqa: E402
from app.services.entity_registry import (  # noqa: E402
    registry_counts,
    seed_competitions_from_sports,
    seed_from_teams,
    seed_persons_from_events,
    seed_persons_from_futures_fields,
)


async def _write_marker(payload: dict) -> None:
    """Persist a run result/error into a marker row readable via /admin/db-query
    (Heroku one-off dyno stdout is not reachable from the sandboxed CLI). Uses a
    dedicated ``seed_diag`` entity kind so it never collides with real entities;
    cleaned up after the run is verified."""
    from sqlalchemy import cast, func, literal, select, update
    from sqlalchemy.dialects.postgresql import JSONB

    from app.models.models import Entity

    async with async_session_maker() as s:
        existing = (
            await s.execute(
                select(Entity.id).where(Entity.external_ref == "seed_diag:persons")
            )
        ).scalar_one_or_none()
        md = {"payload": json.dumps(payload)[:9000]}
        if existing:
            await s.execute(
                update(Entity)
                .where(Entity.id == existing)
                .values(
                    entity_metadata=func.coalesce(
                        Entity.entity_metadata, cast(literal("{}"), JSONB)
                    ).op("||")(cast(literal(json.dumps(md)), JSONB))
                )
            )
        else:
            s.add(
                Entity(
                    kind="seed_diag",
                    canonical_name="persons",
                    external_ref="seed_diag:persons",
                    entity_metadata=md,
                )
            )
        await s.commit()


async def _run(dry_run: bool, persons_only: bool) -> None:
    async with async_session_maker() as session:
        before = await registry_counts(session)
        print(f"Before: {before}")

        if not persons_only:
            comp = await seed_competitions_from_sports(session)
            print(f"Competitions: {comp}")
            teams = await seed_from_teams(session)
            print(f"Teams: {teams}")

        # A1 person fold-in — fighters/players (events) + golf/driver fields (futures).
        # Commit per batch on a real run so a large fold-in persists incrementally
        # (never one huge transaction that can time out / OOM a one-off dyno).
        persons_ev = await seed_persons_from_events(session, commit_each=not dry_run)
        print(f"Persons (events):  {persons_ev}")
        persons_fx = await seed_persons_from_futures_fields(session, commit_each=not dry_run)
        print(f"Persons (futures): {persons_fx}")

        if dry_run:
            await session.rollback()
            print("DRY RUN — rolled back, no writes committed.")
            return

        await session.commit()
        after = await registry_counts(session)
        print(f"After:  {after}")
        return {"events": persons_ev, "futures": persons_fx, "after": after}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Seed then roll back — print projected counts without committing.",
    )
    parser.add_argument(
        "--persons-only",
        action="store_true",
        help="Only run the person fold-in (skip the already-seeded teams/competitions).",
    )
    args = parser.parse_args()

    async def _main() -> None:
        try:
            result = await _run(args.dry_run, args.persons_only)
            if not args.dry_run:
                await _write_marker({"ok": True, "result": result})
        except Exception:  # surface via marker since dyno stdout is unreachable
            tb = traceback.format_exc()
            print(tb)
            if not args.dry_run:
                await _write_marker({"ok": False, "error": tb[-6000:]})
            raise

    asyncio.run(_main())


if __name__ == "__main__":
    main()
