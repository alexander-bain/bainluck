#!/usr/bin/env python3
"""#2879 / D55 — retire the digit-derived StatPal anchor keys, reversibly.

WHAT THIS DOES
--------------
`event_provider_anchors` holds StatPal `game` anchors under two shapes:

    legacy   s6:354453              (written before D55; the digit rule)
    D55      baseball_mlb:354453    (written after; the sport rule)

Production on 2026-09-03 held **91 rows, all `s6:`, all `baseball_mlb`, ids
354453-364938**. This script rewrites each legacy `source_id` to the D55 shape
using the sport its own event is in — which is the only sport it can honestly
be, because `find_event_by_anchor` has always refused to resolve an anchor
across sports (`#2213`).

Backup first, in the same transaction, into a real table. Then re-key. Then
print the one-line restore. `--rollback` runs that restore.

APPLIED IN PRODUCTION 2026-09-06 ~20:5xZ — READ THIS BEFORE RUNNING IT AGAIN
-----------------------------------------------------------------------------
`--apply` has run. Measured before (db-query, reproducing SELECT_LEGACY's plan):
94 legacy rows, all `s6:`, all `baseball_mlb` — 29 REKEY_ONE, 65
DELETE_SUPERSEDED, **0 collisions**. Measured after: **zero** legacy-shaped rows;
`baseball_mlb:` anchors 107 -> 136 (+29, with 65 removed). Backup table
`event_provider_anchors_backup_2879` holds all 94 verbatim.

A second `--apply` is harmless — it selects zero rows and `CREATE TABLE IF NOT
EXISTS` deliberately does not refresh the snapshot that predates every change —
but it is also pointless, and the reason to say so here is `--rollback`: the
undo is still live and still correct, and it restores 94 rows in a shape that
`find_event_by_anchor` NO LONGER READS. The legacy branch, the two-shape
predicate and `statpal_legacy_source_id` were deleted in the same commit as this
note. So a rollback today is a data undo, not a behaviour undo: it puts the rows
back where an audit can see them, and it does NOT make them resolve again. Undo
the code with the code.

DO NOT RUN THIS BEFORE lane1's `event_registry.py` CHANGE IS LIVE
------------------------------------------------------------------
This is the whole of the sequencing and it is not optional:

    1. the D55 key change            (this lane; ships accepting a sport)
    2. `event_registry.py` passes    `sport_key=identity.sport_key`  <- lane1
    3. THIS SCRIPT

Between 1 and 2 the registry still derives the legacy key. Re-keying the rows
first would leave every caller looking for `s6:354453` while the row says
`baseball_mlb:354453`, and the StatPal anchor channel would go dark for MLB —
the `NO_ANCHOR_CHANNEL` state ruling 048's amendment forbids walking into on
purpose. Run step 3 only after `/api/health` reports a commit containing step 2.

After step 2 the writer creates the D55 row itself, so by the time this runs the
usual case is a legacy row sitting BESIDE a correct one. That is why the
re-key is written as "rewrite, unless the target already exists, in which case
delete the legacy row" — both branches converge on one row per fixture, and
neither can create the duplicate the unique index would reject anyway.

THE RAIL
--------
TCP 5432 egress is blocked from an agent sandbox, so `pg:psql` cannot reach the
database. A detached one-off dyno runs inside Heroku's network:

    heroku run:detached -a bainluck -- python3 scripts/rekey_statpal_anchors_2879.py
    heroku run:detached -a bainluck -- python3 scripts/rekey_statpal_anchors_2879.py --apply
    heroku run:detached -a bainluck -- python3 scripts/rekey_statpal_anchors_2879.py --rollback

Default is a DRY RUN: it prints exactly what it would change and writes nothing.
Scripts live at `/app`, not `/app/backend` — a `cd backend &&` prefix silently
no-ops. Verify by census afterwards (the `--report` output, or a db-query), never
by the dyno's stdout: a non-detached `heroku run` does not execute at all in the
sandbox (gotcha #48), and an empty stdout is not evidence of anything.

REVERSIBILITY (D51)
-------------------
`--apply` creates `event_provider_anchors_backup_2879` holding every row it is
about to touch, verbatim, including `id`. The backup table is left in place
afterwards on purpose: a backup deleted at the end of the run is a backup that
exists only while nothing has gone wrong yet.

**`--apply` writes in two shapes, so `--rollback` undoes two shapes.** It
rewrites a `source_id` (REKEY_ONE) *and* it deletes a row (DELETE_SUPERSEDED),
and the second of those is the usual case once step 2 is live. The first
version of this script restored only the first shape — an UPDATE keyed on
`a.id = b.id`, which cannot resurrect a row that is not there. It reported
"restored 0" and the deleted legacy row was gone for good (CERT-847). Rollback
now runs both arms, in that order, and says out loud if a reinsert lost rows to
a reused primary key rather than reporting a clean undo it did not perform.

The round trip is executed, not argued:
`backend/tests/integration/test_rekey_statpal_anchors_real_postgres.py` seeds
the dual-row case against a real PostgreSQL, applies, and rolls back — the
legacy row comes back verbatim and the qualified row is left standing.
"""

from __future__ import annotations

import argparse
import os
import sys

BACKUP_TABLE = "event_provider_anchors_backup_2879"

#: Every legacy StatPal `game` anchor, with the sport key its own event is in.
#: `sports.key` is the same vocabulary `EventIdentity.sport_key` uses, which is
#: what makes the rewritten value identical to what the writer will produce.
SELECT_LEGACY = """
SELECT a.id, a.source_id, s.key AS sport_key, a.event_id
  FROM event_provider_anchors a
  JOIN events e ON e.id = a.event_id
  JOIN sports s ON s.id = e.sport_id
 WHERE a.source = 'statpal'
   AND a.id_kind = 'game'
   AND (a.source_id LIKE 's6:%' OR a.source_id LIKE 's10:%')
 ORDER BY a.id
"""

CREATE_BACKUP = f"""
CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} AS
SELECT a.* FROM event_provider_anchors a
 WHERE a.source = 'statpal'
   AND a.id_kind = 'game'
   AND (a.source_id LIKE 's6:%' OR a.source_id LIKE 's10:%')
"""

#: Rewrite when the D55 key is free.
REKEY_ONE = """
UPDATE event_provider_anchors
   SET source_id = %s
 WHERE id = %s
   AND NOT EXISTS (
       SELECT 1 FROM event_provider_anchors b
        WHERE b.source = 'statpal' AND b.id_kind = 'game'
          AND b.source_id = %s
   )
"""

#: Drop the legacy row when the writer has already created the D55 one for the
#: SAME event. Scoped to the same event on purpose: two rows naming two
#: different events is a genuine collision and this script has no business
#: resolving it — it is left standing and reported.
DELETE_SUPERSEDED = """
DELETE FROM event_provider_anchors a
 WHERE a.id = %s
   AND EXISTS (
       SELECT 1 FROM event_provider_anchors b
        WHERE b.source = 'statpal' AND b.id_kind = 'game'
          AND b.source_id = %s
          AND b.event_id = a.event_id
   )
"""

#: Rollback, arm 1 of 2 — the rows `REKEY_ONE` moved are still there, so their
#: `source_id` goes back by id.
#:
#: `id` alone is NOT enough to identify them. `id` is a reusable BIGSERIAL and a
#: row deleted by `DELETE_SUPERSEDED` frees one; if anything writes an anchor
#: afterwards it can be handed that key, and an UPDATE matching on `a.id = b.id`
#: alone would then stamp a stranger's row with a StatPal `source_id` — silently
#: corrupting a row it was never asked to touch, in the name of restoring one.
#: So the row must still LOOK like the one that was backed up: same provider,
#: same id kind, same event. A row that does not is left alone and shows up in
#: the reinsert arm's shortfall instead, where it is reported.
RESTORE = f"""
UPDATE event_provider_anchors a
   SET source_id = b.source_id
  FROM {BACKUP_TABLE} b
 WHERE a.id = b.id
   AND a.source = b.source
   AND a.id_kind = b.id_kind
   AND a.event_id = b.event_id
   AND a.source_id <> b.source_id
"""

#: Rollback, arm 2 of 2 — and the arm that was missing (CERT-847).
#:
#: `DELETE_SUPERSEDED` removes a row. An UPDATE keyed on `a.id = b.id` cannot
#: bring a deleted row back: there is no `a`. So `--rollback` reported
#: "restored 0" and left the legacy row gone forever, on the branch that the
#: docstring calls the USUAL case after step 2. A backup that only reverses one
#: of two write shapes is not an undo, and D51's unattended grant is written
#: against a restore that actually restores.
#:
#: Verbatim, including `id` and `first_seen_at` — a reinsert that lets the
#: server re-default those is a new row wearing the old one's clothes, and the
#: next audit cannot tell the restore from a rewrite. `claim_context` is JSONB
#: and copies as-is.
#:
#: `ON CONFLICT DO NOTHING` covers the one case a reinsert can legitimately
#: lose: the primary key was reused by a row written after the apply. The
#: caller compares the count against the number missing and says so out loud
#: rather than reporting a clean restore it did not perform.
REINSERT_DELETED = f"""
INSERT INTO event_provider_anchors
       (id, event_id, source, source_id, id_kind, first_seen_at, claim_context)
SELECT b.id, b.event_id, b.source, b.source_id, b.id_kind, b.first_seen_at,
       b.claim_context
  FROM {BACKUP_TABLE} b
 WHERE NOT EXISTS (
       SELECT 1 FROM event_provider_anchors a WHERE a.id = b.id
   )
ON CONFLICT DO NOTHING
"""

#: The POST-CONDITION, not a rowcount: how many backed-up rows are still not
#: present verbatim once both arms have run.
#:
#: Counting rowcounts cannot answer this. In the reused-key case the restore
#: correctly declines to touch a stranger's row and the reinsert correctly
#: declines to overwrite it — two zero rowcounts, no error, and a row that is
#: gone for good. Only asking "is every backed-up row back?" catches it, so
#: that is what the caller asks, after the writes, and it is what decides
#: whether the run reports an undo or a partial restore.
COUNT_UNRESTORED = f"""
SELECT count(*) FROM {BACKUP_TABLE} b
 WHERE NOT EXISTS (
       SELECT 1 FROM event_provider_anchors a
        WHERE a.id = b.id
          AND a.event_id = b.event_id
          AND a.source = b.source
          AND a.source_id = b.source_id
          AND a.id_kind = b.id_kind
   )
"""

#: The backup table only exists after an `--apply`. Rolling back without one is
#: a caller error, and it must not read as "nothing needed restoring".
BACKUP_EXISTS = """
SELECT to_regclass(%s) IS NOT NULL
"""

CENSUS = """
SELECT CASE
         WHEN source_id LIKE 's6:%' OR source_id LIKE 's10:%' THEN 'legacy'
         ELSE 'sport-qualified'
       END AS shape,
       count(*)
  FROM event_provider_anchors
 WHERE source = 'statpal' AND id_kind = 'game'
 GROUP BY 1 ORDER BY 1
"""


def _connect():
    import psycopg2

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is unset — this must run on a Heroku dyno.")
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres://", "postgresql://", 1
    )
    conn = psycopg2.connect(url, sslmode="require")
    conn.autocommit = False
    return conn


def _census(cur, label: str) -> None:
    cur.execute(CENSUS)
    rows = cur.fetchall()
    if not rows:
        print(f"[{label}] no statpal game anchors at all")
        return
    for shape, n in rows:
        print(f"[{label}] {shape}: {n}")


def rollback_rekey(cur) -> dict:
    """Undo an `--apply`, both write shapes. Returns what it did.

    Does not commit — the caller owns the transaction, which is what lets a
    test drive the same statements the dyno runs.

    Order matters and is not arbitrary: RESTORE first, then REINSERT. RESTORE
    moves the re-keyed rows back to their legacy `source_id`, which frees the
    D55 key; only then can a reinsert of a legacy row be certain the unique
    index `(source, source_id, id_kind)` has room for it. Reinserting first
    would be safe today, because a deleted row's key was legacy-shaped and
    nothing else holds it — but that is a property of the current data, not of
    the statements, and the ordering that does not depend on it costs nothing.
    """
    cur.execute(BACKUP_EXISTS, (BACKUP_TABLE,))
    row = cur.fetchone()
    if not row or not row[0]:
        raise SystemExit(
            f"{BACKUP_TABLE} does not exist — there is nothing to roll back to. "
            f"An --apply creates it; a rollback without one would report a "
            f"successful restore of zero rows."
        )

    cur.execute(RESTORE)
    restored = cur.rowcount or 0

    cur.execute(REINSERT_DELETED)
    reinserted = cur.rowcount or 0

    # Asked AFTER both writes, and it is the only claim worth making: every
    # backed-up row is present verbatim, or it is not.
    cur.execute(COUNT_UNRESTORED)
    unrestored = cur.fetchone()[0]

    return {
        "restored": restored,
        "reinserted": reinserted,
        "unrestored": unrestored,
    }


def apply_rekey(cur, *, dry_run: bool = False) -> dict:
    """Re-key every legacy StatPal game anchor. Returns what it did.

    Does not commit; see `rollback_rekey`.
    """
    if not dry_run:
        # BEFORE the first write, in the same transaction as the writes, so
        # there is no state in which rows have moved and the backup has not.
        # `IF NOT EXISTS` makes a re-run safe and deliberately does NOT refresh
        # an existing backup: the first run's snapshot is the one that predates
        # every change, and overwriting it with a half-migrated copy is how a
        # backup stops being an undo.
        cur.execute(CREATE_BACKUP)
        cur.execute(f"SELECT count(*) FROM {BACKUP_TABLE}")
        print(f"[backup] {BACKUP_TABLE} holds {cur.fetchone()[0]} rows")

    cur.execute(SELECT_LEGACY)
    legacy = cur.fetchall()
    print(f"[plan] {len(legacy)} legacy statpal game anchors")

    rekeyed = superseded = skipped = 0
    for anchor_id, source_id, sport_key, event_id in legacy:
        if not sport_key or ":" in sport_key:
            # The key function refuses a qualifier it cannot split back apart,
            # so this script must too — writing one here would produce a row
            # `anchor_is_current` can never corroborate.
            print(
                f"[skip] anchor {anchor_id} (event {event_id}): unusable sport "
                f"key {sport_key!r}"
            )
            skipped += 1
            continue
        bare = source_id.split(":", 1)[1]
        target = f"{sport_key}:{bare}"

        if dry_run:
            print(f"[dry-run] {source_id} -> {target}  (event {event_id})")
            continue

        cur.execute(REKEY_ONE, (target, anchor_id, target))
        if cur.rowcount:
            rekeyed += 1
            continue
        cur.execute(DELETE_SUPERSEDED, (anchor_id, target))
        if cur.rowcount:
            superseded += 1
        else:
            # The target exists and names a DIFFERENT event. That is a real
            # collision and resolving it is the duplicate-drain's job, not this
            # script's. Leave both rows and say so.
            print(
                f"[collision] anchor {anchor_id} (event {event_id}): {target} "
                f"already names another event — left untouched, needs a human"
            )
            skipped += 1

    return {
        "planned": len(legacy),
        "rekeyed": rekeyed,
        "superseded": superseded,
        "skipped": skipped,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--apply", action="store_true", help="write (default is a dry run)"
    )
    ap.add_argument(
        "--rollback",
        action="store_true",
        help=f"restore source_id from {BACKUP_TABLE}",
    )
    ap.add_argument(
        "--report", action="store_true", help="census only, change nothing"
    )
    args = ap.parse_args()

    conn = _connect()
    cur = conn.cursor()

    _census(cur, "before")
    if args.report:
        conn.rollback()
        return 0

    if args.rollback:
        done = rollback_rekey(cur)
        conn.commit()
        print(
            f"[rollback] restored {done['restored']} source_id values and "
            f"reinserted {done['reinserted']} deleted rows from {BACKUP_TABLE}"
        )
        if done["unrestored"]:
            # Said out loud, not buried in a count. Almost always this means a
            # freed primary key was reused after the apply, so the row cannot
            # go back where it was. The operator is holding a partial restore.
            print(
                f"[rollback] WARNING: {done['unrestored']} backed-up row(s) are "
                f"still NOT present verbatim — most likely their primary keys "
                f"were reused after the apply. This is a PARTIAL restore. Do "
                f"not treat it as an undo; the rows are in {BACKUP_TABLE}."
            )
        else:
            print("[rollback] every backed-up row is present verbatim.")
        _census(cur, "after")
        return 0

    done = apply_rekey(cur, dry_run=not args.apply)

    if not args.apply:
        conn.rollback()
        print("[dry-run] nothing written. Re-run with --apply.")
        return 0

    conn.commit()
    print(
        f"[apply] re-keyed {done['rekeyed']}, deleted {done['superseded']} "
        f"superseded legacy rows, skipped {done['skipped']}"
    )
    _census(cur, "after")
    print(
        "[undo]  heroku run:detached -a bainluck -- python3 "
        "scripts/rekey_statpal_anchors_2879.py --rollback"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
