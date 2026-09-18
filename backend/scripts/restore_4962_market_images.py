"""#4962 — the one-command undo for `repair_4962_market_image_repick.py` (D51).

Puts every backed-up row's `image_url` / `image_width` / `image_height` back
exactly as `--backup` found them.

    python3 scripts/restore_4962_market_images.py            # dry run
    python3 scripts/restore_4962_market_images.py --apply

A row the corrected enricher has ALREADY re-picked is restored too — the undo's
job is to return the column to its pre-repair value, and deciding that a new
photograph is better is not a decision a rollback gets to make. Run it, then
re-clear if that is what you wanted.

`--apply` refuses off `bainluck` for the same reason the repair does, and reads
a missing backup table as "nothing to restore" rather than crashing.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.tasks.base import get_task_session  # noqa: E402

BACKUP_TABLE = "backup_4962_market_images"
PRODUCER_APP = "bainluck"


async def run(args) -> int:
    async with get_task_session() as session:
        exists = bool(
            (
                await session.execute(
                    text(f"SELECT to_regclass('public.{BACKUP_TABLE}') IS NOT NULL")
                )
            ).scalar()
        )
        if not exists:
            print(f"{BACKUP_TABLE} does not exist — nothing was ever backed up, so nothing to restore.")
            return 0

        rows = (
            await session.execute(
                text(
                    "SELECT b.id, b.image_url AS backed_up, f.image_url AS current "
                    f"FROM {BACKUP_TABLE} b JOIN futures_markets f ON f.id = b.id ORDER BY b.id"
                )
            )
        ).all()
        print(f"=== {len(rows)} backed-up row(s) ===")
        for row in rows:
            state = "unchanged" if row.current == row.backed_up else "WOULD CHANGE"
            print(f"  {row.id}  {state}\n      now     : {row.current}\n      restore : {row.backed_up}")

        if not args.apply:
            print("\n=== dry run === nothing written.")
            return 0

        app = os.environ.get("HEROKU_APP_NAME")
        if app != PRODUCER_APP:
            where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
            print(f"\nREFUSING --apply: this is {where}, not '{PRODUCER_APP}'.")
            return 2

        result = await session.execute(
            text(
                "UPDATE futures_markets f SET image_url = b.image_url, "
                "image_width = b.image_width, image_height = b.image_height "
                f"FROM {BACKUP_TABLE} b WHERE b.id = f.id"
            )
        )
        await session.commit()
        print(f"\n=== apply === restored {result.rowcount} row(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the backed-up values back")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
