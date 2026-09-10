"""#4586 — re-point open markets stranded on VOIDED phantom events onto the real fixture.

WHAT A READER LOSES TODAY. Tonight's NFL opener (New England @ Seattle, event
14780138, live while this was written) shows 54 Kalshi markets and no Polymarket
price. Its Polymarket moneyline sits on event 15185336 and its "Highest Scoring
Quarter" on 15304895, and both of those are `status='voided'`. A voided event is
not merely mis-filed: `/api/events/{id}` answers **410** for a retired status
(`routes/events.py:9599`, lane1/132) and every list surface excludes it by
allowlist. The market is unreachable by any reader, from any surface, forever —
because `event_id IS NOT NULL` means the matcher never looks at it again
(gotcha #15).

THE POPULATION, measured on production 2026-09-10 ~02:00Z:

  * 304 open markets are attached to `voided` events;
  * **304 of 304** sit on id-less, ESPN-less, venue-minted rows (264 polymarket,
    40 kalshi_occurrence). **Zero** sit on a genuinely cancelled real fixture.
    That is what makes this repair safe — there is no legitimate case to protect,
    so the gate below is not choosing between two kinds of truth;
  * 178 are re-pointable with proof, onto 80 distinct real events;
  * the newest phantom cohort is the week of 2026-08-31 — **no new strandings in
    9 days**, so this is a bounded backlog and not a bailing operation.

WHY THEY ARE STRANDED. `futures_markets.commence_time` is not the kickoff for a
Polymarket row; it is roughly the row's own ingest moment. Over the 25,347
Polymarket markets linked to ESPN-anchored events in the last 60 days it lands
within 60s of the true event start **0 times**, while `resolution_date` does so
17,990 times (71%) and is never NULL. The matcher date-links on the fabricated
field, refuses, and `_create_event_from_prediction_market` mints a phantom
stamped with the same fabricated time; something later voids the phantom and the
market is stranded on it.

  ⚠️ That partly refutes a sentence shipped in `auto_create_time_is_invented`'s
  docstring (#4242): *"the row we decline to write was never going to carry the
  game's real time either."* For Polymarket it was in `resolution_date` all
  along. The guard's BEHAVIOUR is still right; only that clause of its reasoning
  is wrong. Teaching the matcher to date-link on `resolution_date` is the
  prevention half and is filed separately — it is core-matcher work behind #2693.

═══ THE GATE — notice 40: venue structure first, then a SECOND independent signal

A market is re-pointed only when BOTH hold, against exactly one candidate:

  1. `resolution_date` equals the candidate's `commence_time` EXACTLY; and
  2. the market name contains the last token of BOTH the candidate's team names,
     on a WORD BOUNDARY (`\\y`), each token >= 3 characters.

The candidate must be ESPN-anchored and not itself `voided`/`merged`.

NEITHER SIGNAL ALONE IS SUFFICIENT, AND THE MEASUREMENT SAYS SO. Time alone
yields 279 markets with a candidate but only **70** unambiguous — shared kickoff
slots put 209 into ties, and picking by row order would be a coin flip dressed as
a resolution. Adding the name agreement gives **178 markets, 178 of them
unambiguous: zero ties**. The conjunction is perfectly discriminating on this
population, which is the whole argument for using two signals rather than one.

The word boundary is not decoration either: a bare `ILIKE '%'||token||'%'` also
returns 178 here, so it costs nothing today, and it is the difference between
matching "Sox" and matching it inside a longer word (the `%yank%` / `Mayank`
class of defect). Ship the predicate that cannot break, not the one that happens
not to be broken by today's rows.

Orientation-independent BY CONSTRUCTION: both names must appear, in either
order. Polymarket writes "Away vs. Home" and we store home-first, so an
orientation-sensitive gate would refuse the entire population.

WHY `resolve_market_born_duplicate` CANNOT DO THIS. Its refusal 5 is "the row
holds no markets of its own", and these rows are refused precisely BECAUSE they
still hold the stranded market. That is a deadlock, not an oversight: the
resolver is built to read a husk that has already been drained, and something
has to do the draining. This script is that something.

═══ WHAT IT WRITES

One column: `futures_markets.event_id`, for the market ids the PLAN returned —
never a re-derived predicate. The plan's own list drives the UPDATE, so the rows
moved are exactly the rows reported (paraphrasing the predicate into the write
is how a repair moves a different set than the one it printed).

Every move also appends an immutable `market_link_changes` row through
`MatchReceipt.supersede()` + `flush_receipts()` — actor `admin_repair`, phase
`admin_repair`, carrying `previous_event_id`. Never a raw UPDATE: a link change
this script cannot explain afterwards is a link change nobody can audit.

D51: `--apply` REFUSES until `--backup` has copied every in-scope row, and the
undo is one command:

    python3 scripts/restore_4586_stranded_voided_event_markets.py --apply

    python3 scripts/repair_4586_stranded_voided_event_markets.py            # plan only
    python3 scripts/repair_4586_stranded_voided_event_markets.py --backup   # copy + reconcile
    python3 scripts/repair_4586_stranded_voided_event_markets.py --apply --limit 10
    python3 scripts/repair_4586_stranded_voided_event_markets.py --apply

Heroku one-off (gotcha #48 — a non-detached run returns empty stdout that reads
like success; PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`):

    heroku run:detached -a bainluck \\
      "python3 scripts/repair_4586_stranded_voided_event_markets.py --backup"
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_TABLE = "bak_4586_futures_markets"
#: What the repair DID, as opposed to what the rows WERE. See `SQL["man_create"]`.
MANIFEST_TABLE = "bak_4586_repair_manifest"

# The stranded population. Deliberately keyed on what makes the row unreachable
# (`events.status = 'voided'`) AND on the phantom provenance (no external_id, no
# espn_id) — NOT on `commence_time_source`, so a phantom minted by a venue we
# have not met yet is still in scope. A real cancelled fixture carries an
# espn_id and is excluded by construction; zero of today's 304 are one.
_STRANDED = """
    e.status = 'voided'
    AND fm.status = 'open'
    AND e.external_id IS NULL
    AND e.espn_id IS NULL
"""

# The two independent signals, as ONE text used by both the plan and the census
# so they can never drift apart. `\\y` is a Postgres word boundary; the >= 3
# length floor keeps a degenerate one- or two-letter token from matching
# everything (a two-character token is exactly the class that looks safe and is
# not).
_AGREES = r"""
    e2.espn_id IS NOT NULL
    AND e2.status NOT IN ('voided', 'merged')
    AND e2.commence_time = fm.resolution_date
    AND length(substring(e2.home_team_name from '([^ ]+)$')) >= 3
    AND length(substring(e2.away_team_name from '([^ ]+)$')) >= 3
    AND fm.name ~* ('\y' || substring(e2.home_team_name from '([^ ]+)$') || '\y')
    AND fm.name ~* ('\y' || substring(e2.away_team_name from '([^ ]+)$') || '\y')
"""

# One row per re-pointable market. `HAVING count(*) = 1` is the ambiguity
# refusal and it is load-bearing: it is the clause that turns "a candidate
# exists" into "the candidate is known". A market with two agreeing candidates
# is REPORTED and left alone, never resolved by min(id).
_PLAN_SQL = f"""
SELECT fm.id                       AS market_id,
       fm.event_id                 AS old_event_id,
       min(e2.id)                  AS new_event_id,
       min(fm.name)                AS market_name,
       min(fm.source)              AS source,
       min(fm.external_id)         AS market_external_id,
       count(*)                    AS candidates
  FROM futures_markets fm
  JOIN events e ON e.id = fm.event_id
  JOIN events e2 ON {_AGREES}
 WHERE {_STRANDED}
 GROUP BY fm.id, fm.event_id
HAVING count(*) = 1
 ORDER BY fm.id
"""

# The out-of-scope half, printed so the follow-up starts from a number rather
# than from "there were some others".
_RESIDUAL_SQL = f"""
WITH stranded AS (
    SELECT fm.id, fm.resolution_date
      FROM futures_markets fm JOIN events e ON e.id = fm.event_id
     WHERE {_STRANDED}
),
resolvable AS (
    SELECT fm.id
      FROM futures_markets fm
      JOIN events e ON e.id = fm.event_id
      JOIN events e2 ON {_AGREES}
     WHERE {_STRANDED}
     GROUP BY fm.id
    HAVING count(*) = 1
)
SELECT (SELECT count(*) FROM stranded)                                   AS stranded_total,
       (SELECT count(*) FROM resolvable)                                 AS resolvable,
       (SELECT count(*) FROM stranded WHERE resolution_date IS NULL)     AS no_resolution_date
"""

SQL = {
    # LIKE copies columns and types but NOT the foreign keys — a backup that
    # cascaded with its source would be no backup at all.
    "bak_create": f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} "
                  f"(LIKE futures_markets INCLUDING DEFAULTS)",
    "bak_index": f"CREATE UNIQUE INDEX IF NOT EXISTS {BAK_TABLE}_pk "
                 f"ON {BAK_TABLE} (id)",
    "bak_copy": f"INSERT INTO {BAK_TABLE} SELECT s.* FROM futures_markets s "
                f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    "bak_missing": f"SELECT count(*) FROM futures_markets s "
                   f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                   f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    # Driven by the plan's own ids. `event_id = :old` is a compare-and-swap: if
    # anything moved the market between the plan and the write, this no-ops
    # rather than overwriting a fresher decision with a stale one.
    "repoint": "UPDATE futures_markets SET event_id = :new, updated_at = NOW() "
               "WHERE id = :mid AND event_id = :old",
    # THE MANIFEST — CERT-2439's required repair,
    # `4586-RESTORE-CAS-PRESERVES-LATER-RELINKS`.
    #
    # The backup table holds a full row snapshot, which records where each
    # market CAME FROM. It cannot record where this repair PUT it, and the
    # restore needs both: without the target it can only ask "does this row
    # differ from its backup?", which is true both for a row this repair moved
    # AND for a row the live matcher moved after the backup was taken. The
    # restore then reverts the matcher's newer, legitimate decision back onto
    # the voided phantom — an undo that stomps a write it never made.
    #
    # So the manifest is a statement about ACTIONS, not about rows: one entry
    # per market whose forward compare-and-swap actually succeeded, written in
    # the same transaction as the move itself. A market the CAS declined gets
    # no entry and is therefore invisible to the restore, which is precisely
    # the property the block was raised on. It also makes `--limit` exact for
    # free: a partial run leaves a manifest describing only its own half.
    "man_create": f"CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} ("
                  f"  market_id        integer PRIMARY KEY,"
                  f"  old_event_id     integer NOT NULL,"
                  f"  target_event_id  integer NOT NULL,"
                  f"  applied_at       timestamptz NOT NULL DEFAULT NOW())",
    # A market can legitimately be repaired, restored and repaired again. The
    # manifest describes the move that is currently in force, so the later row
    # replaces the earlier one rather than being dropped — `DO NOTHING` would
    # leave the restore CASing against a target that is two moves stale.
    "man_record": f"INSERT INTO {MANIFEST_TABLE} "
                  f"(market_id, old_event_id, target_event_id, applied_at) "
                  f"VALUES (:mid, :old, :new, :now) "
                  f"ON CONFLICT (market_id) DO UPDATE SET "
                  f"  old_event_id = EXCLUDED.old_event_id,"
                  f"  target_event_id = EXCLUDED.target_event_id,"
                  f"  applied_at = EXCLUDED.applied_at",
}


def backup_is_exact(recon) -> bool:
    """The D51 gate: every in-scope row has a backup row, and something was checked.

    `all()` over an empty mapping is True, so the emptiness test is not
    decoration — without it a reconciliation that inspected nothing reads as a
    clean pass and `--apply` proceeds with no undo (gotcha #53).
    """
    return bool(recon) and all(n == 0 for n in recon.values())


def plan_is_unambiguous(rows) -> bool:
    """Every planned move names exactly one candidate.

    `HAVING count(*) = 1` already guarantees this in SQL. Re-asserting it in
    Python is cheap and catches the one thing the SQL cannot: somebody widening
    the HAVING later and not noticing that the write side never re-checked.
    """
    return all(r.candidates == 1 for r in rows)


async def backup(session, market_ids):
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    await session.execute(text(SQL["bak_index"]))
    await session.execute(text(SQL["bak_copy"]), {"ids": market_ids})
    await session.commit()


async def reconcile_backup(session, market_ids) -> dict:
    from sqlalchemy import text

    missing = (
        await session.execute(text(SQL["bak_missing"]), {"ids": market_ids})
    ).scalar_one()
    return {"futures_markets": int(missing)}


async def run(args) -> None:
    from sqlalchemy import text

    from app.tasks.base import get_task_session
    from app.utils.match_receipts import (
        ACTOR_ADMIN_REPAIR,
        PHASE_ADMIN_REPAIR,
        MatchReceipt,
        flush_receipts,
    )
    from datetime import datetime, timezone

    async with get_task_session() as s:
        rows = (await s.execute(text(_PLAN_SQL))).all()
        residual = (await s.execute(text(_RESIDUAL_SQL))).one()

        print(f"=== #4586 stranded-market plan: {len(rows)} re-pointable markets ===")
        print(f"{'market':>10} {'from':>10} {'to':>10} {'source':>11} | name")
        targets = set()
        for r in rows:
            targets.add(r.new_event_id)
            print(f"{r.market_id:>10} {r.old_event_id:>10} {r.new_event_id:>10} "
                  f"{str(r.source):>11} | {(r.market_name or '')[:52]}")

        print(f"\nSummary: {len(rows)} markets → {len(targets)} distinct real events.")
        print(f"  stranded open markets in total : {residual.stranded_total}")
        print(f"  re-pointable with proof        : {residual.resolvable}")
        print(f"  left alone (no single proof)   : "
              f"{residual.stranded_total - residual.resolvable}")
        print(f"  of those, no resolution_date   : {residual.no_resolution_date}")

        if not rows:
            print("\nNothing to repair — plan is empty (idempotent no-op).")
            return

        if not plan_is_unambiguous(rows):
            print("\n❌ REFUSING — a planned move names more than one candidate.")
            return

        market_ids = [int(r.market_id) for r in rows]

        if args.backup:
            print(f"\n=== backup: copying {len(market_ids)} futures_markets rows "
                  f"into {BAK_TABLE} ===")
            await backup(s, market_ids)

        recon = await reconcile_backup(s, market_ids)
        print("\n=== backup reconciliation (in-scope rows with no backup row) ===")
        for tbl, n in recon.items():
            print(f"  {tbl}: {n}")
        clean = backup_is_exact(recon)

        if not args.apply:
            print("\nDRY-RUN — no writes. Pass --backup to copy, then --apply to "
                  "re-point. Undo: restore_4586_stranded_voided_event_markets.py --apply")
            return

        if not clean:
            print(f"\n❌ REFUSING TO APPLY — the backup is not exact. Run --backup "
                  f"first; {BAK_TABLE} must hold every in-scope row.")
            return

        doable = rows[: args.limit] if args.limit else rows
        print(f"\n=== applying {len(doable)} of {len(rows)} ===")

        # Same transaction as the moves below, so the manifest and the writes it
        # describes commit together or not at all. A manifest that could survive
        # a rolled-back move would send the restore CASing against a target
        # nothing was ever put on.
        await s.execute(text(SQL["man_create"]))

        now = datetime.now(timezone.utc)
        receipts, moved = [], 0
        for r in doable:
            res = await s.execute(text(SQL["repoint"]), {
                "mid": int(r.market_id),
                "old": int(r.old_event_id),
                "new": int(r.new_event_id),
            })
            if (res.rowcount or 0) == 0:
                # The compare-and-swap declined: something moved the market
                # between plan and write. Report it, never force it — and write
                # NO manifest row, so the restore cannot later revert a move
                # this repair did not make (CERT-2439).
                print(f"  ⚠️  {r.market_id}: link moved since the plan — skipped")
                continue
            await s.execute(text(SQL["man_record"]), {
                "mid": int(r.market_id),
                "old": int(r.old_event_id),
                "new": int(r.new_event_id),
                "now": now,
            })
            moved += 1
            receipts.append(
                MatchReceipt(
                    market_id=int(r.market_id),
                    source=r.source,
                    external_id=r.market_external_id,
                    market_name=r.market_name,
                    phase=PHASE_ADMIN_REPAIR,
                    attempted_at=now,
                ).supersede(
                    int(r.old_event_id),
                    int(r.new_event_id),
                    actor=ACTOR_ADMIN_REPAIR,
                    issue="4586",
                    gate="resolution_date == commence_time + both team tokens",
                )
            )

        written = await flush_receipts(s, receipts)
        await s.commit()
        print(f"\nCOMMITTED: re-pointed {moved} markets, wrote {written} receipts, "
              f"recorded {moved} manifest rows in {MANIFEST_TABLE}.")
        print(f"Undo: restore_4586_stranded_voided_event_markets.py --apply "
              f"(reverts only these {moved}, and only while they are still on "
              f"the target this repair put them on).")

        after = (await s.execute(text(_RESIDUAL_SQL))).one()
        print(f"POST-REPAIR: {after.stranded_total} stranded open markets remain, "
              f"{after.resolvable} still re-pointable (target: 0 re-pointable "
              f"after a full run).")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true",
                   help=f"copy in-scope futures_markets rows into {BAK_TABLE}")
    p.add_argument("--apply", action="store_true",
                   help="re-point the markets (refuses unless the backup reconciles)")
    p.add_argument("--limit", type=int, default=0,
                   help="apply only the first N moves (0 = all)")
    asyncio.run(run(p.parse_args()))
