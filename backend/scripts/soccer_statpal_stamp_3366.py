#!/usr/bin/env python3
"""The D51 rails for soccer's first StatPal stamp (#3366, D50 step 4).

    heroku run:detached -a <app> python3 scripts/soccer_statpal_stamp_3366.py plan
    heroku run:detached -a <app> python3 scripts/soccer_statpal_stamp_3366.py backup
    heroku run:detached -a <app> python3 scripts/soccer_statpal_stamp_3366.py apply
    heroku run:detached -a <app> python3 scripts/soccer_statpal_stamp_3366.py restore \\
        --identity <backup identity> --apply

``stamp_soccer_statpal_fixtures`` defaults to ``apply=False`` and has no beat
entry, so nothing has ever written a soccer link. D51 says the owning lane may
make that first write **unattended** on exactly two conditions: a backup is
taken first, and a one-command restore ships with it. This file is both, plus
the two reads either side, because splitting them across four files would let an
operator take the third step without the first.

WHY EVERY SUBCOMMAND BANKS ITS RESULT
═════════════════════════════════════
``heroku run:detached`` returns no stdout — gotcha #48 — so a run that only
printed would be a run nobody can read, and "it returned" is not "it worked"
(gotcha #53). Each subcommand therefore writes a ``durable_state_snapshots`` row
and prints the same thing, so the receipt survives the dyno and is readable from
the sandbox with one ``db-query``:

    SELECT identity, generated_at, payload->>'verdict'
      FROM durable_state_snapshots
     WHERE identity LIKE 'authority:soccer_statpal_stamp:%'
     ORDER BY generated_at DESC

THE BACKUP IS A PRE-IMAGE, NOT A PLAN
═════════════════════════════════════
It records what every soccer row's ``statpal_fixture_id`` **held**, and which
soccer StatPal anchors **existed**, over a window generously wider than any the
pass can reach. Deliberately not "the rows the plan says it will stamp": the
boards roll, so a plan taken at 07:40Z and applied at 07:55Z is a plan about a
slightly different afternoon (CERT-846's ``STATPAL_ID_MOVED``). A pre-image over
a superset cannot drift out from under the apply, because it does not depend on
what the boards said at all.

The window is fixed rather than derived: the pass reads ``matches/daily``
offsets 1-3 plus live and widens by ``CANDIDATE_SLACK``, so everything it can
touch sits inside ``now - 2d .. now + 7d`` with days to spare. Deriving it would
mean reading the boards to size the backup, which is the drift this avoids.

WHAT THE RESTORE PUTS BACK, AND WHAT IT REFUSES TO
══════════════════════════════════════════════════
Both halves of the write, because ``_write_link`` writes both and a restore that
cleared only the column would leave an anchor naming an event that no longer
claims the fixture — a state neither the stamper nor the registry can reach on
its own, and one that reads as a real correspondence to every future caller.

It refuses two rows on purpose, and both refusals are the success case:

  * ``COLUMN_MOVED_ON`` — the column no longer holds what the apply wrote.
    Something else has set it since. Dragging it back to a value that is now two
    edits old would make the undo cause the corruption it exists to reverse.
  * ``NOT_OURS`` — a soccer StatPal anchor that was already on file when the
    backup was taken. The apply did not write it, so the undo does not delete
    it. A restore that reports these is reading its pre-image, not ignoring it.

A restore is written in ONE transaction and committed once. The apply cannot be
— ``stamp_v1_statpal_fixtures`` commits per row (gotcha #13) — which is exactly
why the backup has to be a separate, already-committed write rather than a
receipt staged alongside the data (the CERT-851 shape does not apply here).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: One identity per invocation, timestamped, never replaced — the opposite of
#: the authority ledger's one-row-per-sport fold. A backup that a later backup
#: overwrote would be an undo record for a write nobody can now name.
BACKUP_IDENTITY_PREFIX = "authority:soccer_statpal_stamp:backup"
PLAN_IDENTITY_PREFIX = "authority:soccer_statpal_stamp:plan"
APPLY_IDENTITY_PREFIX = "authority:soccer_statpal_stamp:apply"
RESTORE_IDENTITY_PREFIX = "authority:soccer_statpal_stamp:restore"

SCHEMA_VERSION = "soccer-statpal-stamp-3366-1"

#: Our `sports.key` vocabulary for soccer is ~40 keys and grows per league, so
#: the pre-image selects by prefix exactly as `_candidates` does. The `%` rides
#: in the bind and is never interpolated (gotcha #45).
SPORT_KEY_PREFIX = "soccer%"

#: Wider than anything the pass can reach: offsets 1-3 of `matches/daily` end
#: inside 3 days, live is today, and `CANDIDATE_SLACK` widens by hours, not
#: days. Sized so the backup does not have to be re-taken if the board layout
#: changes; if it ever does need to grow, grow it here and say so in the note.
PREIMAGE_BEFORE = timedelta(days=2)
PREIMAGE_AFTER = timedelta(days=7)

#: An apply on a backup older than this is refused. Not a safety property of the
#: pre-image — a pre-image does not go stale, it goes INCOMPLETE: a row that
#: entered the window after the backup was taken is a row the restore cannot
#: see, and the longer the gap the more of them there are.
BACKUP_MAX_AGE = timedelta(minutes=45)

#: Refuse rather than bank a payload nobody has sized. The measured population
#: is ~108 rows in the write window; a superset three orders of magnitude larger
#: than that means the query is wrong, not that soccer grew.
PREIMAGE_MAX_ROWS = 20000

#: `statpal_id_space("soccer")` returns `soccer`, so every anchor this pass
#: writes is `soccer:<fallback_id_3>`. Asserted at runtime against the helper
#: rather than trusted, so a future id-space rule cannot silently orphan the
#: undo (D55 is exactly the rule that changed once already).
ANCHOR_SOURCE = "statpal"
ANCHOR_SOURCE_ID_PREFIX = "soccer:"

PREIMAGE_ROWS_SQL = """
SELECT e.id, e.statpal_fixture_id
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key LIKE :sport_key
   AND e.commence_time >= :window_start
   AND e.commence_time <= :window_end
"""

PREIMAGE_ANCHORS_SQL = """
SELECT event_id, source_id
  FROM event_provider_anchors
 WHERE source = :source
   AND source_id LIKE :source_id_prefix
"""

CLEAR_COLUMN_SQL = """
UPDATE events
   SET statpal_fixture_id = NULL
 WHERE id = :event_id
   AND statpal_fixture_id = :written
"""

DELETE_ANCHOR_SQL = """
DELETE FROM event_provider_anchors
 WHERE source = :source
   AND source_id = :source_id
   AND event_id = :event_id
"""

LIST_SQL = """
SELECT identity, generated_at, payload->>'verdict' AS verdict
  FROM durable_state_snapshots
 WHERE identity LIKE :prefix
 ORDER BY generated_at DESC
 LIMIT 50
"""


def _stamp(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%SZ")


def _assert_namespace() -> None:
    """The undo's selection rule and the writer's key rule must be one rule.

    `statpal_id_space` special-cases tennis and passes everything else through,
    so soccer's space is the literal `soccer` — but that is a property of a
    function that has already been rewritten once (D55), and an undo keyed on a
    stale prefix silently restores nothing. Cheap to check, so it is checked.
    """
    from app.utils.provider_anchor_keys import SOURCE_STATPAL, statpal_id_space

    space = statpal_id_space("soccer")
    expected = ANCHOR_SOURCE_ID_PREFIX.rstrip(":")
    if space != expected or SOURCE_STATPAL != ANCHOR_SOURCE:
        raise SystemExit(
            f"REFUSED: this script's undo selects `{ANCHOR_SOURCE}` / "
            f"`{ANCHOR_SOURCE_ID_PREFIX}%`, but the writer now keys soccer as "
            f"`{SOURCE_STATPAL}` / `{space}:%`. Fix the constants together or "
            f"the restore will match nothing."
        )


async def _bank(payload: dict, identity: str, now: datetime) -> str:
    """Write one receipt. Its status is part of the printed output, not a log."""
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    stage = await publish_snapshot_standalone(
        DurableEnvelope.build(
            identity=identity,
            schema_version=SCHEMA_VERSION,
            payload=payload,
            generated_at=now,
            source="scripts/soccer_statpal_stamp_3366.py",
        )
    )
    return str(stage.get("status"))


async def _read_preimage(session, now: datetime) -> dict:
    from sqlalchemy import text

    start = now - PREIMAGE_BEFORE
    end = now + PREIMAGE_AFTER
    rows = (
        await session.execute(
            text(PREIMAGE_ROWS_SQL),
            {
                "sport_key": SPORT_KEY_PREFIX,
                "window_start": start,
                "window_end": end,
            },
        )
    ).fetchall()
    if len(rows) > PREIMAGE_MAX_ROWS:
        raise SystemExit(
            f"REFUSED: the pre-image selected {len(rows)} rows, over the "
            f"{PREIMAGE_MAX_ROWS} bound. That is a wrong query, not a big "
            f"Saturday — read it before raising the bound."
        )
    anchors = (
        await session.execute(
            text(PREIMAGE_ANCHORS_SQL),
            {
                "source": ANCHOR_SOURCE,
                "source_id_prefix": f"{ANCHOR_SOURCE_ID_PREFIX}%",
            },
        )
    ).fetchall()
    # Keys are strings because a JSONB object cannot hold integer keys and a
    # round-trip that silently stringifies them is a diff nobody can read.
    return {
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "sport_key_prefix": SPORT_KEY_PREFIX,
        "columns": {str(r[0]): r[1] for r in rows},
        "anchors": sorted({f"{r[0]}|{r[1]}" for r in anchors}),
        "rows": len(rows),
        "already_linked": sum(1 for r in rows if r[1] is not None),
        "anchors_on_file": len(anchors),
    }


async def cmd_plan(now: datetime) -> int:
    """Run the pass with `apply=False` and bank its whole receipt.

    The counts this prints are the ones the first apply is judged against: 80
    STAMP / 0 ambiguous / 0 contradictions / 0 polluted / 0 foreign-id-space,
    measured 2026-09-07 over 108 rows. **The denominator is expected to move**
    — the boards roll daily — so a different row count is not a finding. A
    non-zero ambiguous, contradiction, polluted or foreign count IS one, and so
    is any column that is not empty where the plan says STAMP.
    """
    from app.tasks.stamp_v1_statpal_fixtures import (
        _run_stamp_soccer_statpal_fixtures,
    )

    result = await _run_stamp_soccer_statpal_fixtures(apply=False)
    payload = {"verdict": "PLAN", "result": result}
    status = await _bank(payload, f"{PLAN_IDENTITY_PREFIX}:{_stamp(now)}", now)
    print(json.dumps({"banked": status, **payload}, indent=2, default=str))
    return 0


async def cmd_backup(now: datetime) -> int:
    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        preimage = await _read_preimage(session, now)

    identity = f"{BACKUP_IDENTITY_PREFIX}:{_stamp(now)}"
    payload = {"verdict": "BACKUP", "taken_at": now.isoformat(), **preimage}
    status = await _bank(payload, identity, now)
    if status not in ("ok", "superseded"):
        print(json.dumps({"banked": status, "identity": identity}, indent=2))
        print("REFUSED: the backup did not land. Do NOT apply.")
        return 1
    print(
        json.dumps(
            {
                "banked": status,
                "identity": identity,
                "rows": preimage["rows"],
                "already_linked": preimage["already_linked"],
                "anchors_on_file": preimage["anchors_on_file"],
                "undo_command": (
                    "python3 scripts/soccer_statpal_stamp_3366.py restore "
                    f"--identity {identity} --apply"
                ),
            },
            indent=2,
        )
    )
    return 0


async def _latest_backup(session, now: datetime):
    """The freshest backup, and why it is or is not usable."""
    from sqlalchemy import text

    from app.services.durable_snapshots import read_snapshot

    row = (
        (
            await session.execute(
                text(LIST_SQL), {"prefix": f"{BACKUP_IDENTITY_PREFIX}%"}
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None, None, "no backup has ever been taken"
    identity = row["identity"]
    # `read_snapshot` re-checks the checksum, so a corrupted backup refuses here
    # rather than restoring garbage later.
    got = await read_snapshot(session, identity, expected_version=SCHEMA_VERSION)
    if not got.ok:
        return identity, None, f"backup {identity} reads {got.status}"
    taken_at = got.envelope.generated_at
    age = now - taken_at
    if age > BACKUP_MAX_AGE:
        return (
            identity,
            None,
            f"backup {identity} is {int(age.total_seconds())}s old, over the "
            f"{int(BACKUP_MAX_AGE.total_seconds())}s bound — take a fresh one",
        )
    return identity, got.envelope.payload, None


async def cmd_apply(now: datetime) -> int:
    """The first write. Refuses unless a fresh, readable backup is on file."""
    from app.tasks.base import get_task_session
    from app.tasks.stamp_v1_statpal_fixtures import (
        _run_stamp_soccer_statpal_fixtures,
    )

    async with get_task_session() as session:
        identity, payload, why = await _latest_backup(session, now)
    if payload is None:
        print(json.dumps({"verdict": "REFUSED", "reason": why}, indent=2))
        print("Take one first:  python3 scripts/soccer_statpal_stamp_3366.py backup")
        return 1

    result = await _run_stamp_soccer_statpal_fixtures(apply=True)
    receipt = {
        "verdict": "APPLIED",
        "backup_identity": identity,
        "undo_command": (
            "python3 scripts/soccer_statpal_stamp_3366.py restore "
            f"--identity {identity} --apply"
        ),
        "result": result,
    }
    status = await _bank(receipt, f"{APPLY_IDENTITY_PREFIX}:{_stamp(now)}", now)
    print(json.dumps({"banked": status, **receipt}, indent=2, default=str))
    return 0


def plan_restore(preimage: dict, rows, anchors) -> dict:
    """What one apply wrote, derived from the pre-image and the state now.

    Pure, so the undo can be replayed over ``db-query`` rows before anybody runs
    it against production — the same pre-flight that caught a circular pre-check
    on the last repair this lane inherited.

    ``rows`` are ``(event_id, statpal_fixture_id)`` as they stand now; ``anchors``
    are ``(event_id, source_id)`` for every soccer StatPal anchor now on file.

    THE TEST FOR "OURS" IS THE PRE-IMAGE, NOT THE VALUE. A column is ours to
    clear only if the pre-image recorded it EMPTY and it is populated now, and
    that is the whole test — because ``SET_FIXTURE_ID`` is guarded by ``IS NULL``
    and therefore the apply provably could not have written anywhere else. A row
    the pre-image did not record at all is a row that entered the window after
    the backup: also not ours, and reported rather than silently skipped, since a
    non-zero count there means the backup was taken too long before the apply.
    """
    before_columns = preimage.get("columns") or {}
    before_anchors = set(preimage.get("anchors") or [])

    to_clear, unseen = [], []
    for event_id, current in rows:
        key = str(event_id)
        if key not in before_columns:
            if current is not None:
                unseen.append({"event_id": event_id, "holds": current})
            continue
        if before_columns[key] is not None or current is None:
            continue
        to_clear.append({"event_id": event_id, "written": current})

    to_delete, not_ours = [], []
    for event_id, source_id in anchors:
        key = f"{event_id}|{source_id}"
        if key in before_anchors:
            not_ours.append(key)
        else:
            to_delete.append({"event_id": event_id, "source_id": source_id})

    return {
        "to_clear": to_clear,
        "to_delete": to_delete,
        "not_ours": not_ours,
        "outside_backup": unseen,
    }


async def cmd_restore(identity: str, apply: bool, now: datetime) -> int:
    from sqlalchemy import text

    from app.services.durable_snapshots import read_snapshot
    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        got = await read_snapshot(
            session, identity, expected_version=SCHEMA_VERSION, max_age_s=float("inf")
        )
        if not got.ok:
            print(
                json.dumps(
                    {"verdict": "REFUSED", "identity": identity, "read": got.status},
                    indent=2,
                )
            )
            return 1
        preimage = got.envelope.payload

        rows = (
            await session.execute(
                text(PREIMAGE_ROWS_SQL),
                {
                    "sport_key": preimage["sport_key_prefix"],
                    "window_start": preimage["window_start"],
                    "window_end": preimage["window_end"],
                },
            )
        ).fetchall()
        anchors = (
            await session.execute(
                text(PREIMAGE_ANCHORS_SQL),
                {
                    "source": ANCHOR_SOURCE,
                    "source_id_prefix": f"{ANCHOR_SOURCE_ID_PREFIX}%",
                },
            )
        ).fetchall()

        plan_result = plan_restore(preimage, rows, anchors)
        to_clear = plan_result["to_clear"]
        to_delete = plan_result["to_delete"]
        not_ours = plan_result["not_ours"]
        moved_on: list[dict] = []

        if not apply:
            plan = {
                "verdict": "RESTORE_DRY_RUN",
                "identity": identity,
                "taken_at": preimage.get("taken_at"),
                "would_clear_columns": len(to_clear),
                "would_delete_anchors": len(to_delete),
                "left_alone_not_ours": len(not_ours),
                "outside_backup": len(plan_result["outside_backup"]),
                "sample": to_clear[:10],
            }
            await _bank(plan, f"{RESTORE_IDENTITY_PREFIX}:{_stamp(now)}", now)
            print(json.dumps(plan, indent=2, default=str))
            print("\nNothing written. Re-run with --apply to put these back.")
            return 0

        cleared = 0
        for row in to_clear:
            result = await session.execute(
                text(CLEAR_COLUMN_SQL),
                {"event_id": row["event_id"], "written": row["written"]},
            )
            if result.rowcount or 0:
                cleared += 1
            else:
                moved_on.append(row)
        deleted = 0
        for row in to_delete:
            result = await session.execute(
                text(DELETE_ANCHOR_SQL),
                {
                    "source": ANCHOR_SOURCE,
                    "source_id": row["source_id"],
                    "event_id": row["event_id"],
                },
            )
            deleted += result.rowcount or 0
        # One transaction: a restore that cleared columns and then failed to
        # delete anchors would leave the exact orphan state it exists to prevent.
        await session.commit()

    receipt = {
        "verdict": "RESTORED",
        "identity": identity,
        "columns_cleared": cleared,
        "anchors_deleted": deleted,
        "column_moved_on": len(moved_on),
        "left_alone_not_ours": len(not_ours),
        "outside_backup": len(plan_result["outside_backup"]),
    }
    await _bank(receipt, f"{RESTORE_IDENTITY_PREFIX}:{_stamp(now)}", now)
    print(json.dumps(receipt, indent=2, default=str))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="D51 rails for soccer's first StatPal stamp (#3366).",
        epilog="Every subcommand banks its receipt; detached runs print nothing.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan", help="run the pass with apply=False and bank the receipt")
    sub.add_parser("backup", help="bank the pre-image the restore replays")
    sub.add_parser("apply", help="the first write; refuses without a fresh backup")
    restore = sub.add_parser("restore", help="put back exactly what one apply wrote")
    restore.add_argument("--identity", required=True, help="the backup to replay")
    restore.add_argument("--apply", action="store_true", help="actually write")
    args = ap.parse_args()

    _assert_namespace()
    now = datetime.now(timezone.utc)
    if args.cmd == "plan":
        return asyncio.run(cmd_plan(now))
    if args.cmd == "backup":
        return asyncio.run(cmd_backup(now))
    if args.cmd == "apply":
        return asyncio.run(cmd_apply(now))
    return asyncio.run(cmd_restore(args.identity, args.apply, now))


if __name__ == "__main__":
    raise SystemExit(main())
