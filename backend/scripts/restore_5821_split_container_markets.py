"""#5821 — the one-command undo for `repair_5821_split_container_markets.py`.

D51 is what makes that repair applicable at all: it backs up first and ships a
restore. This is the restore. It puts each moved market's `event_id` back to the
value `backup_5821_split_container_markets` recorded.

🔴 IT REVERTS THE RECEIPT, NOT THE PLAN. The backup knows what every in-scope
market pointed at; only the apply knows which compare-and-sets actually landed,
and it records that by stamping `applied_event_id` on the backup row in the same
transaction as the write. This restore touches only stamped rows, by CAS against
that stamp. A market the apply SKIPPED is left alone rather than "restored" to a
link nobody overwrote, and one some other writer has moved SINCE is reported as
drift instead of being silently rolled back.

    python3 scripts/restore_5821_split_container_markets.py           # dry run
    python3 scripts/restore_5821_split_container_markets.py --apply

    heroku run:detached -a bainluck-heavy \
        "python3 scripts/restore_5821_split_container_markets.py --apply"

🔴 THE APP GATE IS ENFORCED, NOT ASKED FOR. An undo is a production write in the
opposite direction and takes the identical gate — and it is the write most likely
to be typed in a hurry, by someone who has just decided the repair went wrong.
The refusal is the repair's own `wrong_app_refusal`, imported through the repair
this undoes, so all four programs share one gate. A dry run reads, and runs
anywhere.

WHY IT JOINS RATHER THAN LOOPS. The backup holds the prior link per market, so
the restore is one `UPDATE … FROM`. A loop would restore partially if it died
halfway; a single statement either lands or does not.

IT IS IDEMPOTENT AND IT DOES NOT DROP THE BACKUP. Running it twice writes the
same links twice, and the table is left in place deliberately — a restore that
destroys its own evidence cannot be checked afterwards.

THE NUMBERS ARE THE POINT, NOT DECORATION. `receipted` is how many links the
apply actually wrote; `restorable` is how many of those still hold exactly what
it wrote. Read them BEFORE `--apply`: `restorable` below `receipted` means
something else has moved those markets since, and the difference is the count
this undo will decline to touch.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BACKUP_TABLE = "backup_5821_split_container_markets"

from repair_5821_split_container_markets import (  # noqa: E402
    PRODUCER_APP,
    wrong_app_refusal,
)


async def run(args):
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal.replace("REFUSING to write", "REFUSING to restore"))
        print(
            f"         (the repair writes from '{PRODUCER_APP}'; its undo is a "
            "production write too, and takes the same gate)"
        )
        return 2

    async with get_task_session() as s:
        present = (
            await s.execute(
                text(f"SELECT to_regclass('public.{BACKUP_TABLE}') IS NOT NULL")
            )
        ).scalar()
        if not present:
            print(
                f"REFUSING: {BACKUP_TABLE} does not exist. There is nothing to "
                "restore from — the repair never ran with --backup on this "
                "database."
            )
            return 2

        n = (await s.execute(text(f"SELECT count(*) FROM {BACKUP_TABLE}"))).scalar()
        receipted = (
            await s.execute(
                text(
                    f"SELECT count(*) FROM {BACKUP_TABLE} "
                    "WHERE applied_event_id IS NOT NULL"
                )
            )
        ).scalar()
        restorable = (
            await s.execute(
                text(
                    f"SELECT count(*) FROM {BACKUP_TABLE} b "
                    "JOIN futures_markets m ON m.id = b.market_id "
                    "WHERE b.applied_event_id IS NOT NULL "
                    "AND m.event_id IS NOT DISTINCT FROM b.applied_event_id"
                )
            )
        ).scalar()
        print(
            f"=== #5821 split-container restore === backup holds {n} markets; "
            f"receipted (actually written by the apply) {receipted}; "
            f"restorable (still holding what the apply wrote) {restorable}"
        )
        if receipted and restorable < receipted:
            print(
                f"  NOTE: {receipted - restorable} receipted market(s) have moved "
                "since the apply. This undo will NOT touch them — reverting a "
                "link somebody else wrote is not a restore."
            )

        if not args.apply:
            print(
                f"\nDRY RUN — nothing written. --apply would restore "
                f"{restorable} market link(s)."
            )
            return 0

        result = await s.execute(
            text(
                "UPDATE futures_markets m SET event_id = b.event_id "
                f"FROM {BACKUP_TABLE} b WHERE m.id = b.market_id "
                "AND b.applied_event_id IS NOT NULL "
                "AND m.event_id IS NOT DISTINCT FROM b.applied_event_id"
            )
        )
        await s.commit()
        print(
            f"\nRESTORED {result.rowcount} market link(s) to their pre-repair "
            f"event. {receipted - result.rowcount} receipted market(s) were left "
            "alone because they no longer hold what the apply wrote."
        )
        return 0


def main():
    p = argparse.ArgumentParser(description="#5821 split-container repair undo")
    p.add_argument("--apply", action="store_true", help="write the restore")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)) or 0)


if __name__ == "__main__":
    main()
