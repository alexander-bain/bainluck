"""#6919 — close the settled Polymarket markets the forward-only rail can never reach.

WHAT A READER SEES. A baseball game that finished on 2026-09-18 stops being
listed among the questions still being asked. It is NOT that the reader finally
sees the answer: LOOKed at 19:1xZ, `/events/15310215` already renders "Settled"
with a complete win-probability curve ending `Dragons 100% — Hawks 0%`. The game
page tells the truth today. What is wrong is the stored `status='open'`, which
keeps a decided market inside every population keyed on "still open". This is a
data-hygiene drain with a bounded, named population — not a p1 visible bug, and
it is sized accordingly.

WHY A SCRIPT AND NOT ANOTHER RAIL FIX. `tournament_price_refresh`'s settlement
close (#6919 arm three, `c0ee7c85c`, live on `bainluck-heavy` v49 18:58:50Z) is
FORWARD-ONLY BY CONSTRUCTION. Its candidate pool requires at least one WRITABLE
(ungraded) leg, so the instant a market's last leg is graded the market leaves
the population and no later pass revisits it. A market whose legs were all
graded by a pass running the OLD code is therefore stranded permanently: the
fixed rail is structurally incapable of seeing it. #6919 names this "a separate
attended repair" and this is it.

═══ THE POPULATION, measured on production 2026-09-18 19:3xZ

Arm three's own structural gate, minus its condition restriction — polymarket,
`status <> 'resolved'`, has legs, and NO leg with `resolution_source IS NULL` —
returns **7 rows**. Five are the stranded baseball markets #6919 names. Two are
not, and they are the entire reason this script has a second gate:

  id        tier legs winners resolution_date  venue
  60755454   5    1     1     2026-09-25       closed, 1/1 children closed  DRAIN
  60755456   5    1     1     2026-09-25       closed, 1/1 children closed  DRAIN
  60755459   5    1     1     2026-09-25       closed, 1/1 children closed  DRAIN
  60755466   5    1     1     2026-09-25       closed, 1/1 children closed  DRAIN
  60755468   5    1     1     2026-09-25       closed, 1/1 children closed  DRAIN
    128775   2    7     0     2027-01-01       OPEN, 4/5 children closed    REFUSE
  16634605   2   49     0     2026-12-31       OPEN, 0/49 children closed   REFUSE

🛑 A DRAIN KEYED ON THE STRUCTURAL PREDICATE ALONE RETIRES TWO LIVE TIER-2
LADDERS. `128775` is "Will Russia enter Pokrovskoe by...?" — its February,
March, April and May sub-deadlines have each passed and graded No, so every leg
we hold carries a `resolution_source`, while the December 31 leg is still
TRADING AT 0.17 and the event resolves 2027-01-01. `16634605` is "Next Prime
Minister of Romania?" — 49 candidate legs, every one graded, ZERO winners, and
the venue has closed NONE of them (Grindeanu 0.2215). Both pass
`NOT EXISTS (resolution_source IS NULL)` cleanly. This is the same class of
damage as the 389 markets arm three's guard was measured to prevent, only
smaller and far harder to see, because the guard that stops the big version
reports these two as safe.

So "every leg has been graded" is NOT "the question has been answered", and this
script does not treat it as such. That predicate selects candidates; it never
decides one.

═══ THE GATE — notice 40's shape: the venue's own structure first, then a
    SECOND independent signal. A row drains only when BOTH agree.

  1. THE VENUE SAYS CLOSED. The market's `external_id` is re-asked at
     `gamma-api.polymarket.com/events/{id}` and must come back `closed: true`
     WITH at least one child market and EVERY child `closed: true`. Notice 26:
     "does the venue still list this as open" is answered against the venue's
     own API, never from our mirror — our mirror is the thing under repair.

     `active` is NOT the discriminator and reading it as one would drain all
     seven: all 7 candidates are `active: true`, including both refusals.
     Only `closed` separates them.

     A partially-closed event is a REFUSAL, not a rounding error — 4/5 is
     exactly Pokrovskoe, a live question wearing four settled sub-deadlines.

  2. THE MARKET HAS A WINNER. At least one leg with `is_winner IS TRUE`.
     Cheap, local, and it needs no network, so it still holds when the venue is
     unreachable. It is also the clause that protects a DOWNSTREAM reader rather
     than this one: `status='resolved'` is calibration's population gate, so a
     zero-winner family admitted here does not merely look wrong on a page, it
     enters the accuracy curve as a question nobody won. A venue voids a family
     by resolving every bucket "No", and that shape must never be drained by a
     script whose whole justification is tidiness.

  ⚠️ `is_winner` is nullable-default-False, so it can only ever be read the way
  it is read here — as a positive test for TRUE. It may never be used to decide
  that a leg is UNGRADED; that is `resolution_source IS NULL`'s job and the two
  are not interchangeable. Arm three's comment makes the same point about the
  same column for the same reason.

  ⚠️ DISAGREEMENT IS A REFUSAL, NOT A TIE-BREAK. If the venue says closed and
  the row has no winner, or the row has a winner and the venue says open, the
  market is reported under `disagreed` and left alone. Two signals exist to
  catch the case neither sees alone; resolving their conflict by preferring one
  would throw away the only warning this script can generate. On today's
  population they agree 7 for 7 — 5 yes, 2 no — so this branch costs nothing
  today and is the only thing standing between a future population and a silent
  wrong close.

  ⚠️ FAIL CLOSED ON ANYTHING UNVERIFIABLE. A non-numeric `external_id` (a 64-hex
  condition, i.e. the sub-market half of the pair arm three describes) is NOT
  addressable at `/events/{id}`, and `/markets?condition_ids=` omits closed
  markets unless `&closed=true` — a door that answers `[]` for "settled", which
  is also what it answers for "no such condition" (gotcha #53: one body, two
  meanings). Disambiguating that needs a second call, and a settlement writer is
  the last place to ship a venue path nobody has run. So such a row is REFUSED
  BY NAME under `unverifiable` and appears in the plan saying so.

  THE POPULATION IS LIVE AND THIS BRANCH IS NOT HYPOTHETICAL. It was written
  against zero specimens at 19:4xZ; by 19:5xZ one had arrived — `13791198`
  "Trump eliminates capital gains tax", 2 legs, 1 winner, `resolution_date`
  2025-12-31, keyed `0x3e685c84…`. It is plausibly drainable and it is NOT
  drained, because "plausibly" is not the standard this script holds. Building
  the condition door is a follow-up with its own live verification, not a thing
  to bolt on mid-flight; the specimen is banked for it.

═══ WHAT IT WRITES

Two columns, on the ids THE PLAN RETURNED — never a re-derived predicate.
Paraphrasing the gate into the write is how a repair moves a different set than
the one it printed, so the plan's own list drives the UPDATE:

    status     'open' -> 'resolved'
    settled_at COALESCE(settled_at, now)     (+ updated_at)

The UPDATE compare-and-swaps on the status the plan saw, so if any rail closed
the row between the plan and the write this no-ops instead of overwriting a
fresher decision. `sync_polymarket_resolved_status` and the CLOB websocket both
close rows; the CAS is what makes this script safe to run beside them.

D51(b): `--apply` REFUSES until `--backup` has copied every in-scope row and the
reconciliation comes back exact. The undo is one command:

    python3 scripts/restore_6919_stranded_settled_polymarket_markets.py --apply

Notice 47(c): the backup tables are created at RUNTIME and only when a person
invokes this, on one named app — runtime DDL, attended invocation only. Nothing
here goes near `backend/alembic/versions/**`, so it is NOT migration-class and
does not execute as a consequence of merge or release.

    python3 scripts/repair_6919_stranded_settled_polymarket_markets.py          # plan only
    python3 scripts/repair_6919_stranded_settled_polymarket_markets.py --backup
    python3 scripts/repair_6919_stranded_settled_polymarket_markets.py --apply

Heroku one-off (gotcha #48 — a non-detached run returns empty stdout that reads
like success; PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`):

    heroku run:detached -a bainluck-heavy \\
      "python3 scripts/repair_6919_stranded_settled_polymarket_markets.py --backup"
"""
import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: The one app this may write from. The heavy app owns the rail whose blind spot
#: this drains, so the repair and the code it completes run in the same place.
PRODUCER_APP = "bainluck-heavy"

BAK_TABLE = "bak_6919_futures_markets"
#: What the repair DID, as opposed to what the rows WERE. The backup is a full
#: row snapshot and records where each market CAME FROM; it cannot record that
#: THIS script is what closed it. Restoring from the snapshot alone would ask
#: "does this row differ from its backup?", which is also true of a row another
#: rail closed legitimately after the backup was taken — and the undo would then
#: re-open a market nobody here touched. So the manifest records ACTIONS: one
#: row per market whose forward CAS actually landed. (CERT-2439's finding on
#: #4586, which cost that repair a block; inherited rather than re-learned.)
MANIFEST_TABLE = "bak_6919_repair_manifest"

GAMMA = "https://gamma-api.polymarket.com"
#: Pause between venue calls. Polymarket's Gamma limiter is real.
VENUE_PAUSE = 0.35
VENUE_TIMEOUT = 20

#: Arm three's structural gate, minus the condition restriction that makes the
#: rail forward-only. Held as ONE text used by both the plan and the census so
#: the two can never drift apart.
#:
#: `status <> 'resolved'` rather than `status = 'open'` deliberately: it mirrors
#: the rail's own wording, and it is the only form that can see a row parked in
#: some third status. Today all 7 are 'open'.
_CANDIDATE_SQL = """
SELECT fm.id,
       fm.status,
       fm.market_tier,
       fm.event_id,
       fm.external_id,
       fm.name,
       fm.resolution_date,
       fm.settled_at,
       (SELECT count(*) FROM futures_outcomes fo
         WHERE fo.market_id = fm.id)                       AS legs,
       (SELECT count(*) FROM futures_outcomes fo
         WHERE fo.market_id = fm.id AND fo.is_winner IS TRUE) AS winners
  FROM futures_markets fm
 WHERE fm.source = 'polymarket'
   AND fm.status <> 'resolved'
   AND EXISTS (SELECT 1 FROM futures_outcomes fo
                WHERE fo.market_id = fm.id)
   AND NOT EXISTS (SELECT 1 FROM futures_outcomes fo2
                    WHERE fo2.market_id = fm.id
                      AND fo2.resolution_source IS NULL)
 ORDER BY fm.id
"""

SQL = {
    # LIKE copies columns and types but NOT the foreign keys — a backup that
    # cascaded with its source would be no backup at all.
    "bak_create": f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} "
                  f"(LIKE futures_markets INCLUDING DEFAULTS)",
    "bak_index": f"CREATE UNIQUE INDEX IF NOT EXISTS {BAK_TABLE}_pk "
                 f"ON {BAK_TABLE} (id)",
    "bak_copy": f"INSERT INTO {BAK_TABLE} SELECT s.* FROM futures_markets s "
                f"WHERE s.id = ANY(CAST(:ids AS bigint[])) "
                f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    "bak_missing": f"SELECT count(*) FROM futures_markets s "
                   f"WHERE s.id = ANY(CAST(:ids AS bigint[])) "
                   f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    "bak_exists": f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL",
    "man_create": f"CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} ("
                  f"  market_id     bigint PRIMARY KEY,"
                  f"  old_status    text NOT NULL,"
                  f"  old_settled_at timestamptz,"
                  f"  set_settled_at timestamptz NOT NULL,"
                  f"  applied_at    timestamptz NOT NULL DEFAULT NOW())",
    # A market can legitimately be drained, restored and drained again, so the
    # later row replaces the earlier one. `DO NOTHING` would leave the restore
    # compare-and-swapping against a stamp two moves stale.
    "man_record": f"INSERT INTO {MANIFEST_TABLE} "
                  f"(market_id, old_status, old_settled_at, set_settled_at) "
                  f"VALUES (:mid, :old_status, :old_settled_at, :set_settled_at) "
                  f"ON CONFLICT (market_id) DO UPDATE SET "
                  f"  old_status = EXCLUDED.old_status,"
                  f"  old_settled_at = EXCLUDED.old_settled_at,"
                  f"  set_settled_at = EXCLUDED.set_settled_at,"
                  f"  applied_at = NOW()",
    # Driven by the plan's own ids, and compare-and-swapped on the status the
    # plan SAW. RETURNING hands back the settled_at that actually landed, which
    # is what the restore CASes against — deriving it afterwards would be a
    # guess about a COALESCE.
    "close": "UPDATE futures_markets "
             "   SET status = 'resolved', "
             "       settled_at = COALESCE(settled_at, :now), "
             "       updated_at = :now "
             " WHERE id = :mid AND status = :old_status "
             " RETURNING settled_at",
}


# ---------------------------------------------------------------------------
# The venue half
# ---------------------------------------------------------------------------

def venue_event(external_id: str) -> dict[str, Any]:
    """Ask Gamma about one event id. Never raises; a failure is a REFUSAL.

    Returns a verdict dict, always with `reachable` and `reason`. An exception
    here must not abort a plan over seven rows, and — more importantly — an
    unreachable venue must never read as permission. Every failure path lands on
    `reachable: False`, which `is_drainable` treats as "do not drain" (gotcha
    #53: an empty or failed read is a response shape, not an absence of doubt).
    """
    if not (external_id or "").isdigit():
        return {"reachable": False,
                "reason": "unverifiable: external_id is not a numeric Gamma "
                          "event id, and /events/{id} cannot address it"}
    # Notice 39: every outbound call site states who made it, through the one
    # helper — a second answer to "should this be tagged?" is a second thing to
    # drift. Gamma is a third-party host, so `tagged()` correctly attaches no
    # origin header and returns `{}` for a bare call.
    #
    # 🪤 WHICH IS WHY THE USER-AGENT IS PASSED THROUGH IT, NOT AROUND IT.
    # `tagged(url)` alone leaves urllib to send its default `Python-urllib/3.x`,
    # and Gamma answers that **403 Forbidden** — measured, every event id. The
    # two-argument form MERGES, so the agent tag rule and a UA the venue will
    # actually serve are not in competition. The failure was invisible to the CI
    # guard (which reads the call site, not the response) and visible only by
    # running the call: it degraded every row to `reachable: False`, i.e. to a
    # blanket refusal. Fail-closed, so it could not have drained anything wrong
    # — but it would have drained nothing at all.
    from app.utils.agent_origin import tagged

    url = f"{GAMMA}/events/{external_id}"
    try:
        req = urllib.request.Request(
            url, headers=tagged(url, {"User-Agent": "bainluck-repair-6919"})
        )
        with urllib.request.urlopen(req, timeout=VENUE_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {"reachable": False, "reason": f"venue call failed: {exc!r}"}

    try:
        ev = json.loads(body)
    except json.JSONDecodeError:
        return {"reachable": False,
                "reason": f"venue returned non-JSON: {body[:120]!r}"}
    if not isinstance(ev, dict) or "title" not in ev:
        return {"reachable": False,
                "reason": f"venue returned no event: {str(ev)[:120]!r}"}

    children = ev.get("markets") or []
    closed_kids = sum(1 for m in children if m.get("closed"))
    return {
        "reachable": True,
        "title": ev.get("title"),
        "event_closed": bool(ev.get("closed")),
        # Recorded but deliberately NOT part of the gate: all 7 candidates are
        # active:true, both refusals included, so gating on it drains everything.
        "event_active": bool(ev.get("active")),
        "end_date": ev.get("endDate"),
        "children": len(children),
        "children_closed": closed_kids,
        "reason": "",
    }


def venue_says_settled(v: dict[str, Any]) -> bool:
    """The venue's own verdict: this event is over and so is every part of it."""
    return bool(
        v.get("reachable")
        and v.get("event_closed") is True
        and v.get("children", 0) > 0
        and v.get("children_closed") == v.get("children")
    )


def classify(row, v: dict[str, Any]) -> tuple[str, str]:
    """(bucket, reason) for one candidate. The only place the gate is decided.

    Buckets: `drain` · `disagreed` · `refused`. There is no fourth, and no
    bucket that means "probably fine".
    """
    venue_ok = venue_says_settled(v)
    has_winner = int(row.winners or 0) > 0

    # Reachability is asked FIRST, and the order is the point. An unreachable
    # venue has not disagreed with anything — it has said nothing — and filing
    # that as `disagreed` tells the operator to go read two conflicting signals
    # when the real instruction is "retry the venue". Both buckets refuse to
    # drain, so this is about what the report MEANS, not about safety.
    if not v.get("reachable"):
        return "refused", v.get("reason", "venue unreachable")

    if venue_ok and has_winner:
        return "drain", ""
    if venue_ok != has_winner:
        return "disagreed", (
            f"venue says settled={venue_ok} but winners={row.winners} "
            f"(is_winner IS TRUE count). Two signals disagree — left alone on "
            f"purpose; a tie-break here would discard the warning."
        )
    return "refused", (
        f"venue still lists this as open: event_closed={v.get('event_closed')}, "
        f"{v.get('children_closed')}/{v.get('children')} child markets closed"
    )


# ---------------------------------------------------------------------------
# The database half
# ---------------------------------------------------------------------------

def backup_is_exact(recon: dict) -> bool:
    """The D51 gate: every in-scope row has a backup, and something was checked.

    `all()` over an empty mapping is True, so the emptiness test is not
    decoration — without it a reconciliation that inspected nothing reads as a
    clean pass and `--apply` proceeds with no undo (gotcha #53).
    """
    return bool(recon) and all(n == 0 for n in recon.values())


def wrong_app_refusal(args) -> Optional[str]:
    """Why this invocation may not WRITE, or None if it may.

    A dry run only reads, so it runs anywhere. A write must be the attended
    invocation notice 47(c) describes, and the only thing distinguishing an
    attended `heroku run:detached` from a laptop holding production credentials
    is which dyno it is on. `HEROKU_APP_NAME` is populated by the
    `runtime-dyno-metadata` lab, enabled on both apps; unset means not a dyno at
    all, which is precisely the case this gate exists to stop, so it refuses too
    rather than falling through.
    """
    if not (args.apply or args.backup):
        return None
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. This script "
        f"creates its backup tables at runtime and rewrites settlement state, so "
        f"the invocation IS the attended step (standing notice 47(c)) and it "
        f"happens on one named app. Re-run with `heroku run:detached -a "
        f"{PRODUCER_APP} \"python3 scripts/{os.path.basename(__file__)} ...\"`."
    )


async def backup_table_exists(session) -> bool:
    """Has anything ever been backed up?

    `backup()` is the only caller of `bak_create`, so without `--backup` the
    table does not exist and `bak_missing` — which names it in a subquery —
    raises UndefinedTable. That traceback would replace the summary a plan-only
    run exists to print, making the documented FIRST step read as a broken
    repair (#4669).
    """
    from sqlalchemy import text

    return bool((await session.execute(text(SQL["bak_exists"]))).scalar_one())


async def backup(session, ids) -> None:
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    await session.execute(text(SQL["bak_index"]))
    await session.execute(text(SQL["man_create"]))
    await session.execute(text(SQL["bak_copy"]), {"ids": ids})
    await session.commit()


async def reconcile_backup(session, ids) -> dict:
    from sqlalchemy import text

    missing = (
        await session.execute(text(SQL["bak_missing"]), {"ids": ids})
    ).scalar_one()
    return {"futures_markets": int(missing)}


async def run(args) -> int:
    import time
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        candidates = (await session.execute(text(_CANDIDATE_SQL))).fetchall()

        print(f"#6919 DRAIN — candidates under arm three's structural gate: "
              f"{len(candidates)}")
        if not candidates:
            print("  Nothing stranded. The rail has the whole population; "
                  "there is nothing for this script to do.")
            return 0

        buckets: dict[str, list] = {"drain": [], "disagreed": [], "refused": []}
        for i, row in enumerate(candidates):
            if i:
                time.sleep(VENUE_PAUSE)
            v = venue_event(row.external_id or "")
            bucket, why = classify(row, v)
            buckets[bucket].append((row, v, why))

        for bucket in ("drain", "disagreed", "refused"):
            items = buckets[bucket]
            print(f"\n── {bucket.upper()} ({len(items)})")
            for row, v, why in items:
                print(f"   {row.id:>10}  tier{row.market_tier}  legs={row.legs:<3} "
                      f"winners={row.winners}  ext={row.external_id}  "
                      f"{(row.name or '')[:44]}")
                print(f"              venue: closed={v.get('event_closed')} "
                      f"children_closed={v.get('children_closed')}/{v.get('children')} "
                      f"end={str(v.get('end_date'))[:10]}")
                if why:
                    print(f"              REASON: {why}")

        plan = [row for row, _v, _w in buckets["drain"]]
        ids = [int(r.id) for r in plan]

        if buckets["disagreed"]:
            print("\n⚠️  SIGNALS DISAGREED on "
                  f"{len(buckets['disagreed'])} market(s). They are NOT drained. "
                  "Read them before re-running — a disagreement is the warning "
                  "two gates exist to produce.")

        if not args.backup and not args.apply:
            print(f"\nPLAN ONLY. Would close {len(ids)} market(s): {ids}")
            if not await backup_table_exists(session):
                print(f"  (no {BAK_TABLE} yet — run --backup before --apply)")
            return 0

        if args.backup:
            if not ids:
                print("\nNothing to back up (plan is empty).")
                return 0
            await backup(session, ids)
            recon = await reconcile_backup(session, ids)
            print(f"\nBACKUP -> {BAK_TABLE}: reconciliation {recon}")
            if not backup_is_exact(recon):
                print("  REFUSING to call this a backup — rows are missing.")
                return 1
            print(f"  Exact for all {len(ids)} row(s). --apply is now permitted.")
            return 0

        # --apply
        if not ids:
            print("\nNothing to apply (plan is empty).")
            return 0
        if not await backup_table_exists(session):
            print(f"\nREFUSING --apply: {BAK_TABLE} does not exist. Run --backup "
                  f"first (D51: no undo, no write).")
            return 1
        recon = await reconcile_backup(session, ids)
        if not backup_is_exact(recon):
            print(f"\nREFUSING --apply: backup is not exact for this plan "
                  f"({recon}). Re-run --backup.")
            return 1

        now = datetime.now(timezone.utc)
        closed, skipped = 0, []
        for row in plan:
            res = (await session.execute(
                text(SQL["close"]),
                {"mid": int(row.id), "old_status": row.status, "now": now},
            )).fetchone()
            if res is None:
                # The CAS declined: something moved this row between the plan
                # and the write. Correct, and reported rather than retried.
                skipped.append(int(row.id))
                continue
            await session.execute(
                text(SQL["man_record"]),
                {"mid": int(row.id), "old_status": row.status,
                 "old_settled_at": row.settled_at, "set_settled_at": res[0]},
            )
            closed += 1
        await session.commit()

        print(f"\nAPPLIED. Closed {closed} market(s); manifest {MANIFEST_TABLE}.")
        if skipped:
            print(f"  CAS declined {len(skipped)} (moved since the plan): {skipped}")
        print("  Undo: python3 scripts/"
              "restore_6919_stranded_settled_polymarket_markets.py --apply")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backup", action="store_true",
                    help="copy every in-scope row to the backup table")
    ap.add_argument("--apply", action="store_true",
                    help="close the planned markets (refuses without a backup)")
    args = ap.parse_args()

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
