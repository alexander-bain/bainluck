"""#4962 — bounded undo for the two pinned image repairs (D51).

Restore only the named identities, while their image and dimensions are still
NULL, from a captured backup of the known bad photo. Never overwrite a re-pick.
Other backup-table rows are ignored; --ids may only narrow the pinned scope.
Every write compares the identity and exact backup again, and any mismatch
rolls back the whole batch. Dry run is the default; --apply requires bainluck.

    python3 scripts/restore_4962_market_images.py
    python3 scripts/restore_4962_market_images.py --apply

This is conservative rollback, not an immutable repair receipt: NULL columns
alone cannot establish which writer cleared them. Attended operation must still
confirm the repair invocation. Re-picked rows require a separate reviewed repair.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.tasks.base import get_task_session  # noqa: E402
from scripts.repair_4962_market_image_repick import (  # noqa: E402
    BACKUP_TABLE,
    CAPTURED_COLUMNS,
    PRODUCER_APP,
    _parse_ids,
    is_filed_bad_image,
    lock_captured_image_and_backup,
)


def eligible_restore(row) -> bool:
    return is_filed_bad_image(row) and all(
        getattr(row, column) is None
        for column in ("current_image", "current_width", "current_height")
    )


async def restore_captured_rows(session, rows) -> bool:
    """Restore an unchanged snapshot only; refuse the entire batch on drift."""
    for row in sorted(rows, key=lambda item: item.id):
        if not eligible_restore(row):
            await session.rollback()
            print(
                f"REFUSING: row {row.id} is not a pinned, still-cleared repair; batch rolled back."
            )
            return False
        if not await lock_captured_image_and_backup(session, row, cleared=True):
            await session.rollback()
            print(
                f"REFUSING: row {row.id} or backup changed; ALL restores rolled back."
            )
            return False
        result = await session.execute(
            text(
                "UPDATE futures_markets AS f SET image_url = :image_url, "
                "image_width = :image_width, image_height = :image_height "
                "WHERE f.id = :id AND f.name IS NOT DISTINCT FROM :name "
                "AND f.llm_sport_category IS NOT DISTINCT FROM :llm_sport_category "
                "AND f.status IS NOT DISTINCT FROM :status "
                "AND f.image_url IS NULL AND f.image_width IS NULL AND f.image_height IS NULL "
                f"AND EXISTS (SELECT 1 FROM {BACKUP_TABLE} b WHERE b.id = f.id "
                "AND b.image_url IS NOT DISTINCT FROM :image_url "
                "AND b.image_width IS NOT DISTINCT FROM :image_width "
                "AND b.image_height IS NOT DISTINCT FROM :image_height)"
            ),
            {column: getattr(row, column) for column in CAPTURED_COLUMNS},
        )
        if result.rowcount != 1:
            await session.rollback()
            print(
                f"REFUSING: row {row.id} or backup changed; ALL restores rolled back."
            )
            return False
    return True


async def run(args) -> int:
    try:
        ids = _parse_ids(args.ids)
    except ValueError as invalid_scope:
        print(f"REFUSING: {invalid_scope}")
        return 2
    if args.apply and os.environ.get("HEROKU_APP_NAME") != PRODUCER_APP:
        print(f"REFUSING --apply: must run on '{PRODUCER_APP}'.")
        return 2
    async with get_task_session() as session:
        exists = (
            await session.execute(
                text(f"SELECT to_regclass('public.{BACKUP_TABLE}') IS NOT NULL")
            )
        ).scalar()
        if not exists:
            print(f"{BACKUP_TABLE} does not exist — nothing to restore.")
            return 0
        rows = (
            await session.execute(
                text(
                    "SELECT f.id, f.name, f.llm_sport_category, f.status, "
                    "b.image_url, b.image_width, b.image_height, "
                    "f.image_url AS current_image, f.image_width AS current_width, "
                    "f.image_height AS current_height "
                    f"FROM {BACKUP_TABLE} b JOIN futures_markets f ON f.id = b.id "
                    f"WHERE f.id IN ({', '.join(str(i) for i in ids)}) ORDER BY f.id"
                )
            )
        ).all()
        for row in rows:
            state = (
                "WOULD RESTORE"
                if eligible_restore(row)
                else "REFUSE changed identity/image/backup"
            )
            print(
                f"  {row.id}: {state}; now={row.current_image!r}; backup={row.image_url!r}"
            )
        if not args.apply:
            print("=== dry run === nothing written.")
            return 0
        if len(rows) != len(ids):
            print("REFUSING: requested identity or backup missing. Nothing restored.")
            return 2
        if not await restore_captured_rows(session, rows):
            return 2
        await session.commit()
        print(f"=== apply === restored {len(rows)} pinned row(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="restore still-cleared pinned rows"
    )
    parser.add_argument(
        "--ids", help="subset of the two pinned #4962 IDs; widening refused"
    )
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
