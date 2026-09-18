"""#6919 — the one-command undo for `repair_6919_stranded_settled_polymarket_markets.py` (D51).

Re-opens every market **this repair closed and that is still exactly as the
repair left it**. Nothing else is touched: the repair writes two columns, so the
restore writes those two columns back.

    python3 scripts/restore_6919_stranded_settled_polymarket_markets.py          # plan only
    python3 scripts/restore_6919_stranded_settled_polymarket_markets.py --apply  # undo

    heroku run:detached -a bainluck-heavy \\
      "python3 scripts/restore_6919_stranded_settled_polymarket_markets.py --apply"

IT RESTORES FROM THE MANIFEST, NOT FROM THE BACKUP, AND THE DIFFERENCE IS THE
WHOLE POINT. The backup table is a full row snapshot: it records what each
market WAS and cannot record that THIS script is what changed it. Restoring from
it means asking "does this row differ from its backup?" — which is true for a
market this repair closed AND for one that
`sync_polymarket_resolved_status` or the CLOB websocket closed legitimately
afterwards. Both of those rails close Polymarket rows on their own schedule, so
that is not a hypothetical: an undo built on the snapshot would re-open a
correctly-settled market it never touched. (CERT-2439 blocked #4586's restore
for exactly this; the lesson is inherited here rather than re-learned.)

So the manifest — written by the repair, one row per market whose forward
compare-and-swap actually LANDED — is the authority, and this restore
compare-and-swaps on both halves of what the repair wrote:
`status = 'resolved'` AND `settled_at` still equal to the stamp the repair
recorded. A market that has moved on since is REPORTED AND LEFT ALONE. That is
not a failure and not a no-op: it is the undo declining to overwrite a newer
decision, which is the only correct thing it can do.

Restoring `settled_at` to its recorded prior value matters as much as the
status. The repair's write is `COALESCE(settled_at, :now)`, so for a row that
already carried a stamp the repair changed nothing there and the manifest's
`old_settled_at` equals `set_settled_at` — putting it back is then a no-op by
construction. For the stranded population, which carries NULL, it is the
difference between a genuine undo and a row left wearing a settlement time for a
settlement that has been withdrawn.

Leaves the backup and manifest tables in place: a restore that destroys the only
record of the pre-repair state cannot be run twice, and the second run is the
one you need when the first was interrupted.
"""
import argparse
import asyncio
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PRODUCER_APP = "bainluck-heavy"
BAK_TABLE = "bak_6919_futures_markets"
MANIFEST_TABLE = "bak_6919_repair_manifest"

#: Every market this repair closed, beside what the live row says NOW. Reported
#: in full rather than filtered in SQL, so the rows that will be LEFT ALONE are
#: visible in the plan instead of silently absent from it.
_PLAN_SQL = f"""
SELECT m.market_id,
       m.old_status,
       m.old_settled_at,
       m.set_settled_at,
       m.applied_at,
       f.status      AS current_status,
       f.settled_at  AS current_settled_at,
       f.name
  FROM {MANIFEST_TABLE} m
  JOIN futures_markets f ON f.id = m.market_id
 ORDER BY m.market_id
"""

SQL = {
    "man_exists": f"SELECT to_regclass('{MANIFEST_TABLE}') IS NOT NULL",
    # Both halves of the repair's write are in the CAS. Status alone would be
    # too loose: another rail can close the row to the same 'resolved' with its
    # own stamp, and re-opening that is precisely what this guard is for.
    # `IS NOT DISTINCT FROM` because the stamp may legitimately be NULL.
    "reopen": "UPDATE futures_markets "
              "   SET status = :old_status, "
              "       settled_at = :old_settled_at, "
              "       updated_at = NOW() "
              " WHERE id = :mid "
              "   AND status = 'resolved' "
              "   AND settled_at IS NOT DISTINCT FROM :set_settled_at",
    "man_drop_row": f"DELETE FROM {MANIFEST_TABLE} WHERE market_id = :mid",
}


def wrong_app_refusal(args) -> Optional[str]:
    """Why this invocation may not WRITE, or None if it may. Notice 47(c)."""
    if not args.apply:
        return None
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. Re-run with "
        f"`heroku run:detached -a {PRODUCER_APP} "
        f"\"python3 scripts/{os.path.basename(__file__)} --apply\"`."
    )


async def run(args) -> int:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        exists = bool(
            (await session.execute(text(SQL["man_exists"]))).scalar_one()
        )
        if not exists:
            print(f"No {MANIFEST_TABLE}: this repair has never applied anything "
                  f"on this database, so there is nothing to undo.")
            return 0

        rows = (await session.execute(text(_PLAN_SQL))).fetchall()
        print(f"#6919 RESTORE — markets this repair closed: {len(rows)}")
        if not rows:
            print("  Manifest is empty. Nothing to undo.")
            return 0

        will, wont = [], []
        for r in rows:
            moved = (r.current_status != "resolved"
                     or r.current_settled_at != r.set_settled_at)
            (wont if moved else will).append(r)
            mark = "LEAVE " if moved else "REOPEN"
            print(f"  {mark} {r.market_id:>10}  now status={r.current_status!r} "
                  f"settled_at={r.current_settled_at}  "
                  f"(repair set {r.set_settled_at}, was {r.old_status!r}/"
                  f"{r.old_settled_at})  {(r.name or '')[:38]}")

        if wont:
            print(f"\n  {len(wont)} market(s) have moved since the repair and "
                  f"will be LEFT ALONE — the undo does not overwrite a newer "
                  f"decision.")

        if not args.apply:
            print(f"\nPLAN ONLY. Would re-open {len(will)} market(s): "
                  f"{[int(r.market_id) for r in will]}")
            return 0

        reopened, declined = 0, []
        for r in rows:
            res = await session.execute(
                text(SQL["reopen"]),
                {"mid": int(r.market_id), "old_status": r.old_status,
                 "old_settled_at": r.old_settled_at,
                 "set_settled_at": r.set_settled_at},
            )
            if res.rowcount:
                # The manifest describes the move currently IN FORCE. Once it is
                # undone the entry is spent, and leaving it would let a second
                # restore re-open a market a later repair legitimately closed.
                await session.execute(text(SQL["man_drop_row"]),
                                      {"mid": int(r.market_id)})
                reopened += 1
            else:
                declined.append(int(r.market_id))
        await session.commit()

        print(f"\nRESTORED. Re-opened {reopened} market(s).")
        if declined:
            print(f"  CAS declined {len(declined)} (moved since the repair, "
                  f"manifest rows kept): {declined}")
        print(f"  {BAK_TABLE} and {MANIFEST_TABLE} left in place on purpose.")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="re-open the markets this repair closed")
    args = ap.parse_args()

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
