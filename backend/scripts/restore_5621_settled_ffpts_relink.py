"""#5621 residual — the D51(b) undo for `repair_5621_settled_ffpts_relink.py`.

D51 = B(b) (Alex, 2026-09-03): a data repair that writes a backup first and ships
a one-command restore may be applied UNATTENDED by the owning lane. This file is
that one command, and the permission is conditional on it working:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/restore_5621_settled_ffpts_relink.py --apply

WHAT IT PUTS BACK. `futures_markets.event_id`, from
:data:`~repair_5621_settled_ffpts_relink.BACKUP_TABLE`, for the two markets the
repair linked — which restores them to NULL, the state authority's after-check
measured on 2026-09-17. That column is the only thing the repair ever wrote: no
outcome moved, no price, no grade, no event row, nothing was deleted. So there is
no ordering problem, no FK to satisfy, and the 27 `futures_outcomes` rows are
untouched by both directions.

WHAT IT WILL NOT DO. Overwrite a row that has been linked AGAIN since. Each
restore is guarded on the row still carrying the event id the repair wrote;
anything else is reported `DIVERGED` and left alone. An undo that stomps a later,
unrelated decision is not an undo — and here the later decision would most likely
be the matcher finally doing its job, which is the outcome everyone wants.

Nor will it invent a target: a market with no backup row is `NO_BACKUP`, not
"set it to NULL and hope".

Idempotent and re-runnable: the guard makes a second run a no-op, and a partial
restore followed by a full one converges.

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

from repair_5621_settled_ffpts_relink import (  # noqa: E402
    BACKUP_TABLE,
    EXPECTED,
    PRODUCER_APP,
    wrong_app_refusal,
)

__all__ = ["BACKUP_TABLE", "EXPECTED", "PRODUCER_APP", "main", "run"]

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
        print("=== #5621 residual — restore KXNFLFFPTS event_id ===")

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

        market_ids = [mid for mid, *_rest in EXPECTED.values()]
        rows = (
            await session.execute(
                text(
                    "SELECT f.id, f.external_id, f.event_id AS now_eid, "
                    "       b.event_id AS was_eid, "
                    "       (b.id IS NULL) AS unbacked "
                    "  FROM futures_markets f "
                    f"  LEFT JOIN {BACKUP_TABLE} b ON b.id = f.id "
                    " WHERE f.id = ANY(:ids) "
                    " ORDER BY f.external_id"
                ),
                {"ids": market_ids},
            )
        ).all()

        plans: list[tuple[int, int | None]] = []
        for r in rows:
            if r.unbacked:
                verdict, detail = NO_BACKUP, "no backup row — not touched"
            elif r.now_eid == r.was_eid:
                verdict, detail = ALREADY_BACK, f"already {r.was_eid}"
            elif r.now_eid == EXPECTED.get(r.external_id, (None, None))[1]:
                verdict = RESTORE
                detail = f"{r.now_eid} -> {r.was_eid}"
                plans.append((r.id, r.was_eid))
            else:
                # Not NULL, and not the value the repair wrote: something else
                # linked this row. Most likely the matcher, which is the outcome
                # the repair existed to reach — never undone by this script.
                verdict = DIVERGED
                detail = (
                    f"carries {r.now_eid}, which this repair did not write "
                    "— left alone"
                )
            print(f"  {r.external_id:<26} {verdict:<13} {detail}")

        print(f"  restorable={len(plans)}")

        if not args.apply:
            print("\nDRY RUN — nothing written.")
            return 0

        if not plans:
            print("\nNothing to restore (no-op).")
            return 0

        restored = 0
        for mid, was_eid in plans:
            # Guarded on the current value being the one the repair wrote, so a
            # row that moves between the plan and the write is skipped, not
            # stomped.
            result = await session.execute(
                text(
                    "UPDATE futures_markets SET event_id = :was "
                    "WHERE id = :mid AND event_id = :now"
                ),
                {
                    "was": was_eid,
                    "mid": mid,
                    "now": next(e for m, e, *_r in EXPECTED.values() if m == mid),
                },
            )
            restored += result.rowcount

        await session.commit()
        print(f"\nRESTORED: {restored} market(s) put back. No child row written.")
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
