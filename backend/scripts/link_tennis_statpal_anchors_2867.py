#!/usr/bin/env python3
"""#2867 / D59 step 4 — give our US Open rows the StatPal id of their match.

WHAT THIS DOES, AND WHAT IT IS FOR
----------------------------------
D59 says a live tennis card's whole score line — sets, games, points, server —
comes from StatPal when the match is linked and from ESPN when it is not, never
mixed. **"Linked" had no representation.** On 2026-09-03 all 30,115 tennis rows
in `events` carried `statpal_fixture_id IS NULL` and the anchor table held zero
StatPal tennis rows, so "is this match linked?" had exactly one answer and the
live lane had nothing to branch on.

This script writes the link for the matches already played or listed, from the
sweep the measurement bus banked as `ARTIFACT-M-20260903-I-map.csv` (vendored
beside this file as `data/statpal_tennis_map_20260903.csv`). It is the PAST. The
forward matcher — the task that links each new fixture as StatPal publishes it —
is separate, because a one-time apply and a recurring task fail in different
ways and a script that does both hides which one broke.

**It does not re-derive the map.** Alex's 4:20pm instruction on 2026-09-03 was
explicit: the bus derived it, this lane applies it. Re-deriving would mean two
matchers disagreeing about one population with no way to say which was right.

TWO WRITES PER LINK, NOT ONE, AND THE SECOND IS NOT OPTIONAL
-------------------------------------------------------------
Each applied row writes BOTH:

    events.statpal_fixture_id  = '2631673'
    event_provider_anchors     = ('statpal', 'tennis:2631673', 'game') -> event

Writing only the anchor would stamp something that does nothing.
`anchor_channel.anchor_is_current` (CERT-410 [P1]) treats a StatPal anchor as a
*copy* of `events.statpal_fixture_id` and refuses any anchor whose column no
longer agrees with it — so an anchor row over a NULL column reads as STALE on
every lookup, logs a warning, and resolves nothing. That is the "built, tested,
deployed and stamped nothing" outcome `statpal_anchor_key`'s own docstring warns
about, arrived at from a different direction.

Writing only the column would leave the correspondence invisible to ruling 048's
drain clause, which reads the anchor table and not the column.

WHY THE QUALIFIER IS `tennis:` AND NOT `tennis_atp_us_open:`
--------------------------------------------------------------
Full argument on `provider_anchor_keys.statpal_id_space`. In one line: StatPal
numbers all of tennis in one sequence and we split the same matches over ~30
`sports.key` values, so qualifying by our key would write two different anchor
keys for one match and the `COLLISION` that proves two of our rows are one game
would never fire.

WHAT IT REFUSES TO DO
---------------------
The whole run aborts, before any write, if the selected rows are not 1:1 in both
directions. That check is not ceremony: the banked map holds 221 rows against
only 212 distinct events, and every one of the 9 collisions pairs a `low`
token-fallback guess against a `high`/`medium` match. At the default
`--confidence high,medium` the 204 selected rows are 1:1 both ways with zero
collisions, which is why LOW is excluded by default and why Alex's addendum says
LOW waits for a second signal (tournament + round agreeing).

Per row, it refuses and reports rather than writing when:

  * the event is gone, or is not a tennis event;
  * the event's `espn_id` disagrees with the map's — the map carries ESPN's id as
    its own corroborating witness, and a disagreement means the row moved under
    the sweep;
  * the event already holds a DIFFERENT `statpal_fixture_id`;
  * another event already holds this fixture id, or an anchor for this key
    already names a different event.

A refusal is printed with its reason and counted. The run still commits the rows
that passed: 204 independent one-row facts, and one bad row is not a reason to
withhold 203 good ones.

THE RAIL
--------
TCP 5432 egress is blocked from an agent sandbox, so this runs on a dyno:

    heroku run:detached -a bainluck -- python3 scripts/link_tennis_statpal_anchors_2867.py
    heroku run:detached -a bainluck -- python3 scripts/link_tennis_statpal_anchors_2867.py --apply
    heroku run:detached -a bainluck -- python3 scripts/link_tennis_statpal_anchors_2867.py --rollback

Default is a DRY RUN. Scripts live at `/app`, not `/app/backend` — a `cd backend`
prefix silently no-ops. Verify by census (`--report`, or a db-query), never by
the dyno's stdout: a non-detached `heroku run` does not execute at all in the
sandbox (gotcha #48) and an empty stdout is evidence of nothing (gotcha #53).

REVERSIBILITY (D51)
-------------------
`--apply` writes a ledger table, `statpal_tennis_link_backup_2867`, BEFORE its
first mutation, holding for every row it is about to touch: the event id, the
`statpal_fixture_id` that was there (normally NULL), the anchor `source_id` it
is about to claim, and whether an anchor row for that key already existed.

That last flag is what makes the undo exact rather than approximate. Both of
this script's write shapes are reversed, each only where this run performed it:

    UPDATE events -> restore the previous `statpal_fixture_id` verbatim
    INSERT anchor -> delete ONLY the keys the ledger says were not there before

An anchor that predated this run is left standing, because deleting it would be
a change, not an undo. The one-line restore is printed at the end of every
`--apply` and is what `--rollback` runs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

LEDGER_TABLE = "statpal_tennis_link_backup_2867"

#: The banked sweep, vendored so the dyno can read it. `.claude/handoff/` is not
#: deployed, so a `--map` pointing there works locally and finds nothing on
#: Heroku — which would apply zero rows and report a clean run.
DEFAULT_MAP = Path(__file__).resolve().parent / "data" / "statpal_tennis_map_20260903.csv"

#: Alex's addendum, 2026-09-03: HIGH + MEDIUM now, LOW only after a second
#: signal. Expressed as a default rather than a hard-coded filter so that the
#: second signal, when it exists, is a flag and not a new script.
DEFAULT_CONFIDENCE = "high,medium"

SOURCE = "statpal"
ID_KIND = "game"

CREATE_LEDGER = f"""
CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
    event_id integer PRIMARY KEY,
    statpal_fixture_id_before varchar,
    statpal_fixture_id_after varchar NOT NULL,
    anchor_source_id varchar NOT NULL,
    anchor_existed_before boolean NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""

INSERT_LEDGER = f"""
INSERT INTO {LEDGER_TABLE}
       (event_id, statpal_fixture_id_before, statpal_fixture_id_after,
        anchor_source_id, anchor_existed_before)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (event_id) DO NOTHING
"""

#: Every precondition the event row can answer, plus the one that asks whether
#: some OTHER row of ours already claims this StatPal match.
#:
#: `other_event_with_fixture` is a correlated subquery rather than a filter so
#: that the row still comes back and can be REPORTED as refused — a precondition
#: that removes the row from the result set is a precondition whose failures are
#: invisible.
INSPECT_EVENT = """
SELECT e.id,
       s.key                       AS sport_key,
       e.espn_id,
       e.statpal_fixture_id,
       (SELECT o.id FROM events o
         WHERE o.statpal_fixture_id = %(fixture_id)s AND o.id <> e.id
         LIMIT 1)                  AS other_event_with_fixture
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE e.id = %(event_id)s
"""

#: The last precondition, asked separately because its parameter — the anchor
#: `source_id` — is not known until the event's sport has been read.
INSPECT_ANCHOR = """
SELECT a.event_id FROM event_provider_anchors a
 WHERE a.source = %(source)s AND a.source_id = %(source_id)s
   AND a.id_kind = %(id_kind)s
 LIMIT 1
"""

SET_FIXTURE_ID = """
UPDATE events
   SET statpal_fixture_id = %(fixture_id)s
 WHERE id = %(event_id)s
   AND (statpal_fixture_id IS NULL OR statpal_fixture_id = %(fixture_id)s)
"""

INSERT_ANCHOR = """
INSERT INTO event_provider_anchors
       (event_id, source, source_id, id_kind, claim_context)
VALUES (%(event_id)s, %(source)s, %(source_id)s, %(id_kind)s, %(claim_context)s)
ON CONFLICT DO NOTHING
"""

#: Rollback arm 1 — the column goes back to whatever was there, verbatim,
#: and ONLY where it still holds the value this run wrote. A row whose fixture
#: id has since changed was changed by someone else, and an undo that overwrites
#: a later writer is not an undo.
RESTORE_FIXTURE_ID = f"""
UPDATE events e
   SET statpal_fixture_id = b.statpal_fixture_id_before
  FROM {LEDGER_TABLE} b
 WHERE e.id = b.event_id
   AND e.statpal_fixture_id = b.statpal_fixture_id_after
"""

#: Rollback arm 2 — delete only the anchors this run created. `anchor_existed_
#: before` is the whole of the distinction: a key that was already in the table
#: when the apply ran is somebody else's row and stays.
DELETE_CREATED_ANCHORS = f"""
DELETE FROM event_provider_anchors a
 USING {LEDGER_TABLE} b
 WHERE a.source = %s
   AND a.id_kind = %s
   AND a.source_id = b.anchor_source_id
   AND a.event_id = b.event_id
   AND b.anchor_existed_before = false
"""

#: The POST-CONDITION, not a rowcount. Asks "is anything this run wrote still
#: there?" after both arms. Two zero rowcounts and no error is exactly what a
#: partial restore looks like (CERT-847), so the answer has to be read from the
#: data rather than inferred from the writes.
COUNT_UNRESTORED = f"""
SELECT count(*) FROM {LEDGER_TABLE} b
 WHERE EXISTS (SELECT 1 FROM events e
                WHERE e.id = b.event_id
                  AND e.statpal_fixture_id IS NOT DISTINCT FROM b.statpal_fixture_id_after
                  AND b.statpal_fixture_id_after IS DISTINCT FROM b.statpal_fixture_id_before)
    OR (b.anchor_existed_before = false
        AND EXISTS (SELECT 1 FROM event_provider_anchors a
                     WHERE a.source = 'statpal' AND a.id_kind = 'game'
                       AND a.source_id = b.anchor_source_id))
"""

#: The OTHER thing the post-condition cannot say, and it is not a failure.
#:
#: `RESTORE_FIXTURE_ID` deliberately refuses to touch a row whose fixture id has
#: changed since the apply — overwriting a later writer is not an undo. But that
#: row is then neither restored nor still-applied, so counting only the two
#: states above would report a clean undo over a row that never went back. It is
#: reported on its own line so the operator sees it and decides.
COUNT_MOVED_ON = f"""
SELECT count(*) FROM {LEDGER_TABLE} b
 WHERE EXISTS (SELECT 1 FROM events e
                WHERE e.id = b.event_id
                  AND e.statpal_fixture_id IS DISTINCT FROM b.statpal_fixture_id_after
                  AND e.statpal_fixture_id IS DISTINCT FROM b.statpal_fixture_id_before)
"""

LEDGER_EXISTS = "SELECT to_regclass(%s) IS NOT NULL"

#: The measurement Alex asked for, computed in the database rather than by
#: counting the script's own writes. A script that reports its own rowcount as
#: coverage cannot tell "I wrote 204 rows" from "204 rows are linked".
CENSUS = """
SELECT s.key,
       count(*)                                                     AS rows,
       count(e.statpal_fixture_id)                                  AS with_fixture_id,
       count(a.event_id)                                            AS with_anchor
  FROM events e
  JOIN sports s ON s.id = e.sport_id
  LEFT JOIN event_provider_anchors a
         ON a.event_id = e.id AND a.source = 'statpal' AND a.id_kind = 'game'
 WHERE s.key LIKE 'tennis%us_open'
 GROUP BY 1 ORDER BY 1
"""
# NB single `%`, not `%%`. `cur.execute(CENSUS)` passes no parameters, and
# psycopg2 only interpolates when it is given some — a doubled `%` would be sent
# to the server verbatim and the LIKE would match nothing, reporting 0% coverage
# on a table that had just been filled.


class MapError(RuntimeError):
    """The map itself is unusable. Nothing is written and nothing is guessed."""


def load_map(path: Path, confidences: set[str]) -> list[dict]:
    """The selected rows, or raise. The 1:1 check lives here, before any DB call.

    Both directions are checked. One StatPal match claiming two of our events is
    a matcher bug; two StatPal matches claiming one of our events is the shape
    the banked map actually contains (9 of them, all LOW-vs-better), and it is
    the reason `--confidence` defaults to excluding LOW.
    """
    if not path.exists():
        raise MapError(f"map not found: {path}")

    with path.open(newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("statpal_id")]

    required = {"statpal_id", "our_event_id", "espn_id", "confidence"}
    missing = required - set(rows[0].keys() if rows else ())
    if missing:
        raise MapError(f"map is missing columns {sorted(missing)}: {path}")

    selected = [r for r in rows if r["confidence"].strip().lower() in confidences]
    if not selected:
        raise MapError(
            f"no rows at confidence {sorted(confidences)} in {path} "
            f"({len(rows)} rows read)"
        )

    by_event: dict[str, list[str]] = {}
    by_fixture: dict[str, list[str]] = {}
    for r in selected:
        by_event.setdefault(r["our_event_id"], []).append(r["statpal_id"])
        by_fixture.setdefault(r["statpal_id"], []).append(r["our_event_id"])

    ambiguous_events = {k: v for k, v in by_event.items() if len(v) > 1}
    ambiguous_fixtures = {k: v for k, v in by_fixture.items() if len(v) > 1}
    if ambiguous_events or ambiguous_fixtures:
        raise MapError(
            "the selected rows are not 1:1 — refusing to write any of them. "
            f"events claimed by >1 fixture: {ambiguous_events}; "
            f"fixtures claiming >1 event: {ambiguous_fixtures}"
        )

    return selected


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
        print(f"[{label}] no US Open tennis rows at all")
        return
    tot = linked = 0
    for key, n, with_fixture, with_anchor in rows:
        print(
            f"[{label}] {key}: {n} rows, {with_fixture} with statpal_fixture_id, "
            f"{with_anchor} with a statpal anchor"
        )
        tot += n
        linked += with_anchor
    pct = (linked * 100.0 / tot) if tot else 0.0
    print(f"[{label}] US Open main draw linked: {linked}/{tot} = {pct:.1f}%")


def plan(cur, rows: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]:
    """Split the selected rows into (writable, refused-with-reason).

    Reads only. Every refusal carries the value that caused it, because "12
    rows refused" is not a finding and "12 rows refused, all `espn_id`
    disagreement, here are the ids" is.
    """
    from app.utils.provider_anchor_keys import statpal_anchor_key, statpal_id_space

    writable: list[dict] = []
    refused: list[tuple[dict, str]] = []

    for r in rows:
        event_id = int(r["our_event_id"])
        fixture_id = r["statpal_id"].strip()

        cur.execute(
            INSPECT_EVENT, {"event_id": event_id, "fixture_id": fixture_id}
        )
        row = cur.fetchone()
        if row is None:
            refused.append((r, "event does not exist"))
            continue
        _, sport_key, espn_id, current_fixture, other_event = row

        id_space = statpal_id_space(sport_key)
        if id_space != "tennis":
            refused.append((r, f"event is {sport_key!r}, not a tennis event"))
            continue

        key = statpal_anchor_key(fixture_id, id_space)
        if key is None:
            refused.append((r, f"fixture id {fixture_id!r} yields no anchor key"))
            continue

        cur.execute(
            INSPECT_ANCHOR,
            {
                "source": key.source,
                "source_id": key.source_id,
                "id_kind": key.id_kind,
            },
        )
        anchor_row = cur.fetchone()
        anchor_event = anchor_row[0] if anchor_row else None

        map_espn = (r.get("espn_id") or "").strip()
        if map_espn and str(espn_id or "").strip() != map_espn:
            refused.append(
                (r, f"espn_id disagrees: map says {map_espn}, row holds {espn_id!r}")
            )
            continue
        if current_fixture and str(current_fixture).strip() != fixture_id:
            refused.append(
                (r, f"event already holds statpal_fixture_id {current_fixture!r}")
            )
            continue
        if other_event is not None:
            refused.append((r, f"event {other_event} already holds this fixture id"))
            continue
        if anchor_event is not None and int(anchor_event) != event_id:
            refused.append(
                (r, f"anchor {key.source_id} already names event {anchor_event}")
            )
            continue

        writable.append(
            {
                "event_id": event_id,
                "fixture_id": fixture_id,
                "source_id": key.source_id,
                "sport_key": sport_key,
                "fixture_id_before": current_fixture,
                "anchor_existed_before": anchor_event is not None,
                "confidence": r["confidence"],
                "method": r.get("method", ""),
            }
        )

    return writable, refused


def apply_links(cur, writable: list[dict]) -> dict:
    """Write the ledger, then the links. Does not commit — the caller owns that.

    Ledger first, unconditionally, and in the same transaction: a backup written
    after the first mutation is a backup of a state that no longer exists.
    """
    cur.execute(CREATE_LEDGER)
    for w in writable:
        cur.execute(
            INSERT_LEDGER,
            (
                w["event_id"],
                w["fixture_id_before"],
                w["fixture_id"],
                w["source_id"],
                w["anchor_existed_before"],
            ),
        )

    updated = anchored = 0
    for w in writable:
        cur.execute(
            SET_FIXTURE_ID,
            {"event_id": w["event_id"], "fixture_id": w["fixture_id"]},
        )
        updated += cur.rowcount or 0
        cur.execute(
            INSERT_ANCHOR,
            {
                "event_id": w["event_id"],
                "source": SOURCE,
                "source_id": w["source_id"],
                "id_kind": ID_KIND,
                "claim_context": json.dumps(
                    {
                        "written_by": "link_tennis_statpal_anchors_2867",
                        "map": DEFAULT_MAP.name,
                        "confidence": w["confidence"],
                        "method": w["method"],
                        "sport_key": w["sport_key"],
                    }
                ),
            },
        )
        anchored += cur.rowcount or 0

    return {"events_updated": updated, "anchors_written": anchored}


def rollback_links(cur) -> dict:
    """Undo an `--apply`, both write shapes, and check the post-condition."""
    cur.execute(LEDGER_EXISTS, (LEDGER_TABLE,))
    row = cur.fetchone()
    if not row or not row[0]:
        raise RuntimeError(
            f"{LEDGER_TABLE} does not exist — there is no apply to roll back. "
            "This is a caller error, not an empty undo."
        )

    cur.execute(RESTORE_FIXTURE_ID)
    restored = cur.rowcount or 0
    cur.execute(DELETE_CREATED_ANCHORS, (SOURCE, ID_KIND))
    deleted = cur.rowcount or 0

    cur.execute(COUNT_UNRESTORED)
    unrestored = int(cur.fetchone()[0])
    cur.execute(COUNT_MOVED_ON)
    moved_on = int(cur.fetchone()[0])
    return {
        "fixture_ids_restored": restored,
        "anchors_deleted": deleted,
        "still_applied": unrestored,
        "moved_on": moved_on,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--rollback", action="store_true", help="undo a previous --apply")
    ap.add_argument("--report", action="store_true", help="census only, no plan")
    ap.add_argument("--map", type=Path, default=DEFAULT_MAP)
    ap.add_argument(
        "--confidence",
        default=DEFAULT_CONFIDENCE,
        help=f"comma-separated confidence levels to apply (default {DEFAULT_CONFIDENCE})",
    )
    args = ap.parse_args(argv)

    if args.apply and args.rollback:
        sys.exit("--apply and --rollback are opposites; pass one.")

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    conn = _connect()
    cur = conn.cursor()
    try:
        _census(cur, "before")
        if args.report:
            return 0

        if args.rollback:
            result = rollback_links(cur)
            conn.commit()
            print(f"[rollback] {result}")
            _census(cur, "after")
            if result["moved_on"]:
                print(
                    f"[rollback] {result['moved_on']} ledger rows hold a fixture id "
                    "this run did not write — a later writer moved them, and the "
                    "restore left them alone on purpose. Not an error; look at them."
                )
            if result["still_applied"]:
                print(
                    f"[rollback] PARTIAL — {result['still_applied']} ledger rows are "
                    "still applied. This is not a clean undo; investigate before "
                    "re-applying."
                )
                return 1
            return 0

        confidences = {c.strip().lower() for c in args.confidence.split(",") if c.strip()}
        rows = load_map(args.map, confidences)
        writable, refused = plan(cur, rows)

        print(
            f"[plan] {len(rows)} selected at confidence {sorted(confidences)}: "
            f"{len(writable)} writable, {len(refused)} refused"
        )
        for r, reason in refused:
            print(f"[refused] event {r['our_event_id']} <- {r['statpal_id']}: {reason}")

        if not args.apply:
            print("[dry-run] nothing written. Re-run with --apply.")
            return 0

        result = apply_links(cur, writable)
        conn.commit()
        print(f"[apply] {result}")
        _census(cur, "after")
        print(
            "[apply] RESTORE (D51), one line:  heroku run:detached -a bainluck -- "
            "python3 scripts/link_tennis_statpal_anchors_2867.py --rollback"
        )
        return 0
    except MapError as e:
        conn.rollback()
        print(f"[abort] {e}")
        return 2
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
