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
import sys
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
        persons_ev = await seed_persons_from_events(session)
        print(f"Persons (events):  {persons_ev}")
        persons_fx = await seed_persons_from_futures_fields(session)
        print(f"Persons (futures): {persons_fx}")

        if dry_run:
            await session.rollback()
            print("DRY RUN — rolled back, no writes committed.")
            return

        await session.commit()
        after = await registry_counts(session)
        print(f"After:  {after}")


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
    asyncio.run(_run(args.dry_run, args.persons_only))


if __name__ == "__main__":
    main()
