"""#1229 — repair the inverted-completed_at class (data-repair lane).

Invariant (gotcha #46): ``completed_at >= commence_time``. A violation means an
earlier game's completion data merged onto the wrong event — the doubleheader /
cross-merge class (#190/#1229, gotcha #32). The read-side was healed and the bulk
439-row backfill ran in Queue #191; this script is the reusable owed repair for
the residual/recurrent rows the Flow Sentinel's ``resolved_state`` flow flags.

The repair (gotcha #22 — use the last REAL source snapshot, never a backend
processing timestamp): for each inverted event, set ``completed_at`` to the latest
``captured_at`` across its win-prob + odds snapshots that is **at or after**
``commence_time``. That is the honest game-end signal and, by construction, clears
the inversion. If an event has NO post-commence snapshot at all, we CANNOT derive a
correct completed_at from data on hand — we leave it untouched and print it for
forensic follow-up (never guess a timestamp, never null a real settled event).

    #1229's specific find (ops-lane / Flow Sentinel fingerprint 6c21fdce2a3c):
    event 15175872 (baseball_mlb, Yankees vs Pirates 2026-07-22 game 2, commence
    23:05Z) carried completed_at 2026-07-22 20:20:33 — a stat_model snapshot that
    belongs to game 1 (17:05Z). Its last post-commence real snapshot is ESPN at
    2026-07-23 00:00:05, which is the correct completed_at.

Dry-run by default (prints the full ledger + would-do values). Pass --apply to
commit. Idempotent: after a clean run the census is 0, so a re-run is a no-op.

    python3 scripts/repair_inverted_completed_at.py            # dry-run ledger
    python3 scripts/repair_inverted_completed_at.py --apply    # commit the repair

Heroku one-off (gotcha #48 — non-detached run does not execute in the sandbox;
PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`):
    heroku run:detached "python scripts/repair_inverted_completed_at.py --apply" -a bainluck
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Every event whose completion timestamp precedes its start — the invariant break.
_LEDGER_SQL = """
    SELECT e.id AS event_id, e.status AS ev_status, e.commence_time, e.completed_at,
           e.home_score, e.away_score, s.key AS sport_key,
           EXTRACT(EPOCH FROM (e.commence_time - e.completed_at)) / 3600.0 AS inversion_hours,
           (SELECT MAX(w.captured_at) FROM win_prob_snapshots w
              WHERE w.event_id = e.id AND w.captured_at >= e.commence_time) AS last_wp_snap,
           (SELECT MAX(o.captured_at) FROM odds_snapshots o
              WHERE o.event_id = e.id AND o.captured_at >= e.commence_time) AS last_odds_snap
    FROM events e
    LEFT JOIN sports s ON s.id = e.sport_id
    WHERE e.completed_at IS NOT NULL
      AND e.commence_time IS NOT NULL
      AND e.completed_at < e.commence_time
    ORDER BY e.id
"""

_FIX_SQL = """
    UPDATE events SET completed_at = :new_completed_at
    WHERE id = :event_id
"""

_CENSUS_SQL = """
    SELECT COUNT(*) AS inverted
    FROM events
    WHERE completed_at IS NOT NULL
      AND commence_time IS NOT NULL
      AND completed_at < commence_time
"""


async def repair(session, apply: bool) -> dict:
    """Session-taking core (used by both the CLI and POST /api/admin/repairs/
    inverted-events, Queue #247 Item 5). Does all work on ``session``; commits
    only when ``apply``. Returns a JSON-serializable before/after census."""
    from sqlalchemy import text

    s = session
    rows = (await s.execute(text(_LEDGER_SQL))).all()
    before = (await s.execute(text(_CENSUS_SQL))).one().inverted

    fixable: list[tuple[int, object]] = []
    unfixable: list[int] = []
    ledger: list[dict] = []
    for r in rows:
        candidates = [t for t in (r.last_wp_snap, r.last_odds_snap) if t is not None]
        new_completed = max(candidates) if candidates else None
        if new_completed:
            fixable.append((r.event_id, new_completed))
        else:
            unfixable.append(r.event_id)
        ledger.append({
            "event_id": r.event_id, "sport_key": r.sport_key, "status": r.ev_status,
            "commence_time": r.commence_time.isoformat() if r.commence_time else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "inversion_hours": round(float(r.inversion_hours), 2) if r.inversion_hours is not None else None,
            "new_completed_at": new_completed.isoformat() if new_completed else None,
            "action": "fix" if new_completed else "skip_no_snapshot",
        })

    fixed = 0
    if apply and fixable:
        for event_id, new_completed in fixable:
            fixed += (await s.execute(
                text(_FIX_SQL),
                {"event_id": event_id, "new_completed_at": new_completed},
            )).rowcount or 0
        await s.commit()

    after = (await s.execute(text(_CENSUS_SQL))).one().inverted
    return {
        "repair": "inverted-events",
        "applied": bool(apply),
        "before": before,
        "fixable": len(fixable),
        "unfixable": len(unfixable),
        "unfixable_event_ids": unfixable,
        "fixed": fixed,
        "after": after,
        "ledger": ledger,
    }


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        rows = (await s.execute(text(_LEDGER_SQL))).all()

        print(f"=== #1229 inverted-completed_at ledger: {len(rows)} event(s) ===")
        fixable: list[tuple[int, object]] = []
        unfixable: list[int] = []
        for r in rows:
            # Prefer the later of the two real post-commence snapshot sources.
            candidates = [t for t in (r.last_wp_snap, r.last_odds_snap) if t is not None]
            new_completed = max(candidates) if candidates else None
            tag = "FIX" if new_completed else "NO-SNAP (skip — forensic)"
            print(f"  event {r.event_id} [{r.sport_key}] {r.ev_status} "
                  f"commence={r.commence_time} completed={r.completed_at} "
                  f"(inverted {r.inversion_hours:.1f}h) score={r.home_score}-{r.away_score} "
                  f"→ {tag}"
                  + (f" new_completed_at={new_completed}" if new_completed else ""))
            if new_completed:
                fixable.append((r.event_id, new_completed))
            else:
                unfixable.append(r.event_id)

        if not rows:
            print("\nNothing to repair — census already 0 (idempotent no-op).")
            return

        print(f"\nSummary: {len(fixable)} fixable (real post-commence snapshot found), "
              f"{len(unfixable)} un-fixable from data on hand"
              + (f" {unfixable}" if unfixable else "") + ".")

        if not apply:
            print(f"\nDRY-RUN — pass --apply to reset completed_at on {len(fixable)} "
                  f"event(s) to their last real post-commence snapshot. No writes made.")
            return

        fixed = 0
        for event_id, new_completed in fixable:
            fixed += (await s.execute(
                text(_FIX_SQL),
                {"event_id": event_id, "new_completed_at": new_completed},
            )).rowcount or 0
        await s.commit()
        print(f"\nCOMMITTED: reset completed_at on {fixed} event(s).")

        census = (await s.execute(text(_CENSUS_SQL))).one()
        print(f"POST-REPAIR CENSUS: {census.inverted} inverted event(s) (target: "
              f"{len(unfixable)} — only the un-fixable no-snapshot rows may remain).")
        if census.inverted == len(unfixable):
            print("✅ #1229 census clean (all snapshot-derivable inversions repaired).")
        else:
            print("⚠️  unexpected residual — investigate before closing #1229.")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
