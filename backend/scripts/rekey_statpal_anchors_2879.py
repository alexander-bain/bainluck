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
about to touch, verbatim, including `id`. `--rollback` restores `source_id` from
it by `id` and reports the count. The backup table is left in place afterwards
on purpose: a backup deleted at the end of the run is a backup that exists only
while nothing has gone wrong yet.
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

RESTORE = f"""
UPDATE event_provider_anchors a
   SET source_id = b.source_id
  FROM {BACKUP_TABLE} b
 WHERE a.id = b.id AND a.source_id <> b.source_id
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
        cur.execute(RESTORE)
        restored = cur.rowcount or 0
        conn.commit()
        print(f"[rollback] restored {restored} source_id values from {BACKUP_TABLE}")
        _census(cur, "after")
        return 0

    cur.execute(SELECT_LEGACY)
    legacy = cur.fetchall()
    print(f"[plan] {len(legacy)} legacy statpal game anchors")

    if args.apply:
        # BEFORE the first write, in the same transaction as the writes, so
        # there is no state in which rows have moved and the backup has not.
        # `IF NOT EXISTS` makes a re-run safe and deliberately does NOT refresh
        # an existing backup: the first run's snapshot is the one that predates
        # every change, and overwriting it with a half-migrated copy is how a
        # backup stops being an undo.
        cur.execute(CREATE_BACKUP)
        cur.execute(f"SELECT count(*) FROM {BACKUP_TABLE}")
        print(f"[backup] {BACKUP_TABLE} holds {cur.fetchone()[0]} rows")

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

        if not args.apply:
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

    if not args.apply:
        conn.rollback()
        print("[dry-run] nothing written. Re-run with --apply.")
        return 0

    conn.commit()
    print(
        f"[apply] re-keyed {rekeyed}, deleted {superseded} superseded legacy rows, "
        f"skipped {skipped}"
    )
    _census(cur, "after")
    print(
        "[undo]  heroku run:detached -a bainluck -- python3 "
        "scripts/rekey_statpal_anchors_2879.py --rollback"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
