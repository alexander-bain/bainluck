"""#4586 — the one-command undo for `repair_4586_stranded_voided_event_markets.py` (D51).

Puts `futures_markets.event_id` back for every market **this repair moved and
that is still where the repair put it**. Nothing else is touched: the repair
writes exactly one column, so the restore writes exactly one column back.

    python3 scripts/restore_4586_stranded_voided_event_markets.py            # plan only
    python3 scripts/restore_4586_stranded_voided_event_markets.py --apply    # undo

    heroku run:detached -a bainluck \\
      "python3 scripts/restore_4586_stranded_voided_event_markets.py --apply"

IT RESTORES FROM THE MANIFEST, NOT FROM THE BACKUP, AND THE DIFFERENCE IS THE
WHOLE OF CERT-2439. The backup table is a full row snapshot: it records where
each market CAME FROM and cannot record where this repair PUT it. Restoring from
it means asking "does this row differ from its backup?" — which is true for a
row this repair moved AND for a row the live matcher relinked after the backup
was taken, including one the forward compare-and-swap correctly SKIPPED for
exactly that reason. The old form reverted both, so a market the repair never
touched was dragged back onto the voided phantom by its own undo.

Reproduced against the exact predicate before the fix: market 1 at target 20
(backup 10) and market 2 independently relinked to 30 (backup 11) restored to
`[(1, 10), (2, 11)]`; the required answer is `[(1, 10), (2, 30)]`.

So the manifest — written by the repair, one row per SUCCESSFUL move — is the
authority, and the restore compare-and-swaps on `event_id = target_event_id`. A
market that has moved on since the repair is REPORTED AND LEFT ALONE. It is not
a failure and not a no-op: it is the undo declining to overwrite a newer
decision, which is the only correct thing it can do.

THE REVERSE RECEIPT IS WRITTEN HERE, AND IT USED TO SAY IT WAS NOT.
`market_link_changes` is an append-only history of what happened; the repair
moving a link and the restore moving it back are two things that happened, and
deleting the first would make the table lie about the past to make the present
look tidy (the property LINKLOSS-03 exists to prevent). This file's docstring
used to say "a restore appends its own rows on the next matcher pass" — that was
FALSE, and CERT-2439 caught it: gotcha #15 says an already-linked market is
never time-window re-matched, so no later pass would ever visit these rows and
the history would go on claiming the repair target forever. The restore now
appends its own `admin_repair` receipt, and only for a market whose
compare-and-swap actually landed — a receipt for a write that did not happen
turns the audit trail into fiction.

Leaves the backup and manifest tables in place: a restore that destroys the only
copy of the pre-repair state cannot be run twice, and the second run is the one
you need when the first was interrupted.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_TABLE = "bak_4586_futures_markets"
MANIFEST_TABLE = "bak_4586_repair_manifest"

#: Every market this repair moved, with what the live row says NOW. Reported in
#: full rather than filtered in SQL, so the rows that will be LEFT ALONE are
#: visible in the plan instead of silently absent from it.
_PLAN_SQL = f"""
SELECT m.market_id,
       m.old_event_id,
       m.target_event_id,
       f.event_id AS current_event_id,
       f.source,
       f.external_id,
       f.name
  FROM {MANIFEST_TABLE} m
  JOIN futures_markets f ON f.id = m.market_id
 ORDER BY m.market_id
"""

#: The compare-and-swap. `event_id = :target` is the clause CERT-2439 required:
#: it restores a row only while it is still where the repair left it.
#: `:target <> :old` cannot happen from a real manifest row, but the guard costs
#: nothing and stops a hand-edited manifest turning this into a no-op that
#: reports success.
_RESTORE_SQL = """
UPDATE futures_markets
   SET event_id = :old, updated_at = NOW()
 WHERE id = :mid AND event_id = :target
"""

_TABLE_EXISTS_SQL = "SELECT to_regclass(:t) IS NOT NULL"


async def run(apply: bool) -> None:
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.tasks.base import get_task_session
    from app.utils.match_receipts import (
        ACTOR_ADMIN_REPAIR,
        PHASE_ADMIN_REPAIR,
        MatchReceipt,
        flush_receipts,
    )

    async with get_task_session() as s:
        for tbl, why in (
            (MANIFEST_TABLE, "the repair never ran its --apply, so it moved "
                             "nothing and there is nothing to undo"),
            (BAK_TABLE, "the repair never ran its --backup"),
        ):
            exists = (
                await s.execute(text(_TABLE_EXISTS_SQL), {"t": tbl})
            ).scalar_one()
            if not exists:
                # Absence is not "nothing to do" — it is "this cannot be
                # answered" (gotcha #53). Saying so is the whole point.
                print(f"❌ {tbl} does not exist — {why}. This is not a clean "
                      f"no-op; investigate before assuming the data is fine.")
                return

        rows = (await s.execute(text(_PLAN_SQL))).all()
        revertible = [r for r in rows if r.current_event_id == r.target_event_id]
        moved_on = [r for r in rows if r.current_event_id != r.target_event_id]

        print(f"=== #4586 restore plan: {len(rows)} markets in the manifest ===")
        for r in revertible:
            print(f"  market {r.market_id}: {r.current_event_id} → "
                  f"{r.old_event_id}")
        if moved_on:
            # LOUD, not filtered away. These are the rows the old restore
            # clobbered; a reader has to be able to see that they were
            # considered and declined, not that they were never in scope.
            print(f"\n  ⚠️  {len(moved_on)} market(s) have moved since the "
                  f"repair and will be LEFT ALONE — restoring them would "
                  f"overwrite a newer decision this repair did not make:")
            for r in moved_on:
                print(f"      market {r.market_id}: repair put it on "
                      f"{r.target_event_id}, it is now on "
                      f"{r.current_event_id} (backup said {r.old_event_id})")

        if not revertible:
            print("\nNothing to restore — no manifest row is still on its "
                  "repair target (idempotent no-op if the undo already ran; "
                  "read the LEFT ALONE list above if it is not empty).")
            return

        if not apply:
            print(f"\nDRY-RUN — no writes. Pass --apply to put back the "
                  f"{len(revertible)} restorable market(s).")
            return

        now = datetime.now(timezone.utc)
        receipts, restored = [], 0
        for r in revertible:
            res = await s.execute(text(_RESTORE_SQL), {
                "mid": int(r.market_id),
                "old": int(r.old_event_id),
                "target": int(r.target_event_id),
            })
            if (res.rowcount or 0) == 0:
                # It moved between the plan above and this write. Same rule as
                # the forward direction: report, never force, and write NO
                # receipt for a write that did not land.
                print(f"  ⚠️  {r.market_id}: moved since the plan — skipped")
                continue
            restored += 1
            receipts.append(
                MatchReceipt(
                    market_id=int(r.market_id),
                    source=r.source,
                    external_id=r.external_id,
                    market_name=r.name,
                    phase=PHASE_ADMIN_REPAIR,
                    attempted_at=now,
                ).supersede(
                    int(r.target_event_id),
                    int(r.old_event_id),
                    actor=ACTOR_ADMIN_REPAIR,
                    issue="4586",
                    gate="restore: undo of the #4586 stranded-market repair",
                )
            )

        written = await flush_receipts(s, receipts)
        await s.commit()
        print(f"\nCOMMITTED: restored {restored} markets to their pre-repair "
              f"event_id, wrote {written} reverse receipts.")

        left = (await s.execute(text(_PLAN_SQL))).all()
        still = sum(1 for r in left if r.current_event_id == r.target_event_id)
        print(f"POST-RESTORE: {still} manifest rows are still on their repair "
              f"target (target: 0). {len(moved_on)} were left alone by design "
              f"and are not counted here.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="commit the restore")
    asyncio.run(run(p.parse_args().apply))
