"""#2000 — the D51(b) undo for `repair_2000_1h_relink.py`.

D51 = B(b) (Alex, 2026-09-03): a data repair that writes a backup first and ships
a one-command restore may be applied UNATTENDED by the owning lane. This file is
that one command, and the permission is conditional on it working:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/restore_2000_1h_relink.py --apply

WHAT IT PUTS BACK. `futures_markets.event_id` for market 15207269, from
:data:`~repair_2000_1h_relink.BACKUP_TABLE` — which restores it to 15011303, the
mislink the repair moved it off. That column is the only thing the repair ever
wrote: no outcome moved, no price, no grade, no event row, nothing was deleted.
So there is no ordering problem, no FK to satisfy, and the three
`futures_outcomes` rows are untouched by both directions.

⚠️ WHAT RESTORING MEANS HERE, SAID PLAINLY. Unlike the sibling undo (#5621),
whose restore put a row back to NULL, this one puts a row back onto a **wrong
event** — it re-creates the defect #2000 describes, where the Aug 26 Real
Sociedad v Real Betis page serves a May 9 first-half market graded with the other
fixture's result. That is the correct behaviour for an undo and it is the whole
point of D51's backup-first bargain, but it means this script is a rollback of a
TRUTH repair, not a cleanup. Run it because the repair went wrong, not because
the repair is finished.

WHAT IT WILL NOT DO. Overwrite a row that has moved again since. The restore is
guarded on the row still carrying the event id the repair wrote (14623338);
anything else is reported `DIVERGED` and left alone. An undo that stomps a later,
unrelated decision is not an undo.

Nor will it invent a value: a market with no backup row is `NO_BACKUP`, not
"guess what it used to be".

Idempotent and re-runnable: the guard makes a second run a no-op.

`--apply` is required. Without it this prints exactly what it would put back.

The backup table is NOT Alembic-managed. `alembic revision --autogenerate` will
propose DROPping it — expected, and to be deleted from the generated migration
rather than accepted. Drop it deliberately once the repair is trusted and this
undo is no longer wanted.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# …and this script's OWN directory, so the sibling import below resolves however
# the file is loaded. Running `python3 scripts/restore_….py` puts `scripts/` on
# the path for free; importing the file by its path (the guard test does) does
# not, and the difference is an ImportError nobody sees until CI.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from repair_2000_1h_relink import (  # noqa: E402
    BACKUP_TABLE,
    FROM_EVENT_ID,
    MARKET_ID,
    PRODUCER_APP,
    TICKER,
    TO_EVENT_ID,
    wrong_app_refusal,
)

__all__ = [
    "BACKUP_TABLE",
    "MARKET_ID",
    "PRODUCER_APP",
    "main",
    "run",
]

#: Verdicts.
RESTORE = "RESTORE"
ALREADY_BACK = "ALREADY_BACK"
DIVERGED = "DIVERGED"
NO_BACKUP = "NO_BACKUP"


def _session_factory():
    """The app's real async session factory — see the repair script's copy.

    Behind a named function so a test can substitute it AND prove the real one
    resolves. That matters more in an undo than in a repair: D51 permits an
    unattended production write BECAUSE a one-command undo exists, so an undo
    that cannot start retroactively removes the permission the repair ran under.
    """
    from app.services.database import async_session_maker

    return async_session_maker


async def run(args) -> int:
    from sqlalchemy import text

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    session_factory = _session_factory()

    async with session_factory() as session:
        print("=== #2000 — restore the first-half market's original event_id ===")

        # The table may not exist — the repair was never applied, or the backup
        # has been dropped. `to_regclass` says so without raising.
        if not bool(
            (
                await session.execute(
                    text(f"SELECT to_regclass('public.{BACKUP_TABLE}') IS NOT NULL")
                )
            ).scalar()
        ):
            print(
                f"  no {BACKUP_TABLE} — nothing was ever backed up here, so there "
                "is nothing to restore. (If the repair HAS been applied, its "
                "backup table has been dropped and this undo cannot run.)"
            )
            return 0

        row = (
            await session.execute(
                text(
                    "SELECT f.id, f.external_id, f.event_id AS now_eid, "
                    "       b.event_id AS was_eid, "
                    "       (b.id IS NULL) AS unbacked "
                    "  FROM futures_markets f "
                    f"  LEFT JOIN {BACKUP_TABLE} b ON b.id = f.id "
                    " WHERE f.id = :mid"
                ),
                {"mid": MARKET_ID},
            )
        ).first()

        if row is None:
            print(f"  market {MARKET_ID} no longer exists — nothing to restore.")
            return 0

        plan: tuple[int, int | None] | None = None
        if row.unbacked:
            verdict, detail = NO_BACKUP, "no backup row — not touched"
        elif row.now_eid == row.was_eid:
            verdict, detail = ALREADY_BACK, f"already {row.was_eid}"
        elif row.now_eid == TO_EVENT_ID:
            verdict = RESTORE
            detail = f"{row.now_eid} -> {row.was_eid} (re-creates the #2000 mislink)"
            plan = (row.id, row.was_eid)
        else:
            # Not the value the repair wrote: something else linked this row.
            # Never undone by this script.
            verdict = DIVERGED
            detail = (
                f"carries {row.now_eid}, which this repair did not write — left alone"
            )

        print(f"  {row.external_id:<26} {verdict:<13} {detail}")
        print(f"  restorable={1 if plan else 0}")

        if not args.apply:
            print("\nDRY RUN — nothing written.")
            return 0

        if not plan:
            print("\nNothing to restore (no-op).")
            return 0

        mid, was_eid = plan
        # Guarded on the current value being the one the repair wrote, so a row
        # that moves between the plan and the write is skipped, not stomped.
        result = await session.execute(
            text(
                "UPDATE futures_markets SET event_id = :was "
                "WHERE id = :mid AND external_id = :ticker AND event_id = :now"
            ),
            {"was": was_eid, "mid": mid, "ticker": TICKER, "now": TO_EVENT_ID},
        )
        if result.rowcount != 1:
            await session.rollback()
            print(
                f"\nREFUSING: the guarded UPDATE matched {result.rowcount} rows, "
                "not 1. The row changed between the plan and the write. Nothing "
                "was committed."
            )
            return 2

        await session.commit()
        print(
            f"\nRESTORED: market {mid} put back to {was_eid} "
            f"(expected {FROM_EVENT_ID}). No child row written."
        )
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--apply", action="store_true", help="write the restore (default: dry run)"
    )
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
