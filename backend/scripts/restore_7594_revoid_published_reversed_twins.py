"""#7594 — the one-command undo for the reversed-twin take-back (D51(b)).

Reads ``bak_7594_revoid_published_reversed_twins`` and puts every event it names
back on the status production held before the repair ran.

    python3 scripts/restore_7594_revoid_published_reversed_twins.py            # dry run
    python3 scripts/restore_7594_revoid_published_reversed_twins.py --apply

Heroku one-off (gotcha #48 — non-detached returns empty stdout that reads like
success; PROJECT_PATH=backend puts scripts at /app, so NO ``cd backend``):

    heroku run:detached -a bainluck \\
      "python3 scripts/restore_7594_revoid_published_reversed_twins.py --apply"

🔴 THE DRY RUN CANNOT BE PAID BEFORE THE APPLY THAT CREATES ITS RESTORE POINT.
The repair creates the bank, so before any apply this script can only report an
absent table and exit 1. That is the correct answer, not a failure — a populated
dry run is a POST-apply step.

WHAT THE UNDO DELIBERATELY DOES NOT DO
--------------------------------------
🔴 It does not restore an event that has moved on from the state the repair left
it in. The compare-and-swap is on ``status_after`` — what WE wrote — never on
"the live row differs from its backup" (#7354's rail, and CERT-3141's lesson).
On this cohort the distinction is not theoretical: these are upcoming games, and
any arm of the status machinery may legitimately move one again between the
repair and the undo. A restore keyed on difference would drag such a row back to
a status nothing currently believes.

🔴 IT DOES NOT RE-REVIVE. Putting the row back on ``scheduled`` is exactly the
state the repair took it out of, and no more: the undo never invents a status the
bank did not record, so an event banked from some other status returns to that
one rather than to a hard-coded ``scheduled``.

🔴 A RESTORE IS A PRODUCTION WRITE IN THE OPPOSITE DIRECTION and earns the same
gate as the repair. ``wrong_app_refusal`` is IMPORTED from the repair rather than
copied, so the two cannot drift apart.

It does not drop the bank. A restore that destroys its own evidence cannot be
re-run, and the repair is idempotent precisely so the pair can be exercised more
than once.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.repair_7594_revoid_published_reversed_twins import (  # noqa: E402
    BANK_TABLE,
    wrong_app_refusal,
)


async def run(args) -> int:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    async with get_task_session() as s:
        present = (
            await s.execute(
                text("SELECT to_regclass(:t) IS NOT NULL"),
                {"t": f"public.{BANK_TABLE}"},
            )
        ).scalar()
        if not present:
            print(
                f"{BANK_TABLE} does not exist: the repair has not run on this "
                "database, so there is nothing to put back."
            )
            return 1

        rows = (
            await s.execute(
                text(
                    "SELECT b.event_id, b.status_before, b.status_after, e.status "
                    f"FROM {BANK_TABLE} b JOIN events e ON e.id = b.event_id "
                    "ORDER BY b.event_id"
                )
            )
        ).all()
        print(f"{BANK_TABLE}: {len(rows)} banked rows")

        restorable = [r for r in rows if r[3] == r[2]]
        moved_on = [r for r in rows if r[3] != r[2]]

        for event_id, before, _after, _live in restorable:
            print(
                ("  restored " if args.apply else "  would restore ")
                + f"{event_id} -> {before}"
            )
        for event_id, _before, after, live in moved_on:
            print(
                f"  SKIPPED {event_id}: repair left it '{after}', it is now "
                f"'{live}' — something else owns this row."
            )

        if not args.apply:
            print(
                f"plan: {len(restorable)} would be restored, "
                f"{len(moved_on)} moved on and are left alone."
            )
            print("plan only. Re-run with --apply.")
            return 0

        # One statement, nothing but the id bound: the value written and the
        # value compared both come out of the bank by column reference, so no
        # column ever round-trips through an untyped bind (CERT-932's contract,
        # guarded by tests/test_restore_jsonb_bind_contract.py for the restores
        # that carry jsonb).
        done = (
            await s.execute(
                text(
                    f"UPDATE events e SET status = b.status_before "
                    f"FROM {BANK_TABLE} b "
                    "WHERE e.id = b.event_id AND e.status = b.status_after"
                )
            )
        ).rowcount
        await s.commit()
        print(f"done: restored {done}, left {len(rows) - done} that had moved on")
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true", help="put the statuses back")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
