#!/usr/bin/env python3
"""The D51 rails for soccer's first StatPal stamp (#3366, D50 step 4).

    heroku run:detached -a <app> python3 scripts/soccer_statpal_stamp_3366.py plan
    heroku run:detached -a <app> python3 scripts/soccer_statpal_stamp_3366.py backup
    heroku run:detached -a <app> python3 scripts/soccer_statpal_stamp_3366.py apply
    heroku run:detached -a <app> python3 scripts/soccer_statpal_stamp_3366.py restore \\
        --identity <apply run id> --apply

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

AND WHY THAT RECEIPT IS THE ONLY ONE — THIS DOES NOT SHOW UP IN TASK HEALTH
═══════════════════════════════════════════════════════════════════════════
It calls ``_run_stamp_soccer_statpal_fixtures`` directly rather than through the
celery task, so ``_tracked_run`` never sees it: no success counter moves, no
verdict is classified, nothing appears against ``stamp_soccer_statpal_fixtures``
in the task metrics. **That is deliberate and it is the honest side of the
trade.** Soccer has no beat entry, so those counters answer "is the schedule
being kept?" for a schedule that does not exist; an operator-run apply recorded
against them would put a single ad-hoc run into a cadence series and make the
one number they publish mean two different things. The receipt above is
therefore the whole record of this run, which is why every subcommand writes one
whether it changed anything or not.

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

WHAT THE RESTORE PUTS BACK, AND HOW IT KNOWS WHAT IS ITS TO PUT BACK
════════════════════════════════════════════════════════════════════
Both halves of the write, because ``_write_link`` writes both and a restore that
undid only one would leave an anchor naming an event that no longer claims the
fixture — or a column claiming a fixture no anchor records — states neither the
stamper nor the registry can reach on its own, and ones that read as a real
correspondence to every future caller.

**Ownership comes from the apply's own manifest, never from the pre-image**
(CERT-2207). The first version of this script derived it: a column empty in the
backup and populated now was assumed to be ours. That is wrong for the whole
population that enters the window during the ``BACKUP_MAX_AGE`` gap. Normal
ingestion creates soccer rows continuously; the apply selects its candidates
live, so it can stamp a row the backup never saw. Under the derived rule that
row's column was classified ``outside_backup`` and left populated while its
anchor — equally absent from the pre-image — was classified deletable. The undo
produced exactly the orphan this file exists to prevent.

So the writer records what it wrote, in the same transaction as the write:

  * ``StampRun.committed_writes`` — appended after each per-row commit, naming
    the event, the fixture, the anchor's ``source_id``, and which of the two
    halves this pass actually wrote. Banked with the apply receipt.
  * ``claim_context->>'apply_run_id'`` — the same invocation id, written INTO
    each anchor by ``record_anchor``'s INSERT. This is the durable half: it
    survives a process that dies before it can bank anything, and it cannot
    attach to an anchor the run did not insert, because ``record_anchor`` never
    writes ``claim_context`` on the conflict path.

The restore takes the union and CAS-guards both halves — a column is cleared
only if it still holds exactly what the manifest says was written, an anchor
deleted only on its exact ``(source, source_id, event_id)`` triple. So a row
another writer has touched since is reported and left alone rather than dragged
back to a value that is now two edits old.

**AND THE ATTRIBUTION IS AN UNDOABLE WRITE TOO** (CERT-2216). A column-only row
keeps its anchor, so clearing the column leaves ``column_write_run_id`` behind,
describing a value that no longer exists. The invariant that makes the whole
mechanism work — *the key names the run whose column value is standing* — needs
both ends: the writer replaces a stale key when it wins the NULL-column update,
and the restore takes its own key back off when it clears the column. With only
the first half the second apply is undoable but the anchor lies; with only the
second half a column cleared by anything other than this restore leaves the next
apply unattributable, and a process loss then buries a committed write for good.

Three reports, and all three are the success case:

  * ``column_moved_on`` — the column no longer holds what the apply wrote.
  * ``anchor_already_gone`` — the anchor was removed between apply and restore.
  * ``unbanked_anchors`` — attributed in the table but absent from the banked
    manifest, i.e. the apply died mid-flight. These ARE restored; the count is
    how an operator learns the receipt is short.

THE BACKUP IS STILL TAKEN, AND IS NO LONGER THE UNDO
════════════════════════════════════════════════════
D51 requires it and ``cmd_apply`` still refuses without a fresh one. Its job is
now the one a pre-image is actually good at: a coarse, human-readable record of
what the window held before, for the case where the manifest mechanism itself is
what failed. It is not consulted to decide ownership, because that is the
inference this repair removes.

A restore is written in ONE transaction and committed once. The apply cannot be
— ``stamp_v1_statpal_fixtures`` commits per row (gotcha #13) — which is exactly
why attribution has to ride along with each row's own commit.
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

#: Refuse rather than bank a payload nobody has sized. **Measured on production
#: 2026-09-07 07:48Z: this window holds 1,347 soccer rows, of which 0 carry a
#: `statpal_fixture_id`** — against ~108 rows in the write window the plan pass
#: can actually reach. So the bound is ~15x the real superset, and a pass that
#: trips it has a wrong query, not a big Saturday.
PREIMAGE_MAX_ROWS = 20000

#: `statpal_id_space("soccer")` returns `soccer`, so every anchor this pass
#: writes is `soccer:<fallback_id_3>`. Asserted at runtime against the helper
#: rather than trusted, so a future id-space rule cannot silently orphan the
#: undo (D55 is exactly the rule that changed once already).
#:
#: **Measured 2026-09-07 07:49Z: the `statpal`/`soccer:` namespace holds 0 rows**
#: — StatPal anchors exist only under `americanfootball_nfl` (293), `tennis`
#: (237), `baseball_mlb` (150), `basketball_nba` (41) and `icehockey_nhl` (27).
#: The two `soccer_other` anchors on file are `kalshi`, a different `source`,
#: and the filter below never reaches them. So the first apply inserts into an
#: empty namespace on BOTH halves, and the undo's delete set is exact by
#: construction rather than by a timestamp.
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

#: Every anchor this invocation INSERTED, straight from the table. The durable
#: half of the attribution: `record_anchor` writes `claim_context` on the INSERT
#: and never on the conflict path, so a row matching this run id is one this run
#: created. `column_was_already_set` is how the two write paths are told apart —
#: `_write_anchor_only` sets it, `_write_link` does not — which is what says
#: whether a column write rides with this anchor.
#: Every anchor this run is attributed on, by either of the two keys the writer
#: uses, with the flag that says which (CERT-2211).
#:
#: `apply_run_id`        — this run INSERTED the anchor. Clear the column, delete
#:                         the anchor.
#: `column_write_run_id` — this run wrote the column onto an anchor that was
#:                         already on file (`record_anchor` CONFIRMED it). Clear
#:                         the column and LEAVE THE ANCHOR: deleting it would
#:                         remove a correspondence this run did not create, which
#:                         is the orphan in the other direction.
#:
#: `anchor_is_ours` is computed here rather than inferred downstream because the
#: incumbent's own `claim_context` belongs to whoever wrote it — it may well
#: carry `column_was_already_set` from an earlier anchor-only pass, and reading
#: that as if this run had written it is how the column would be left behind.
ATTRIBUTED_ANCHORS_SQL = """
SELECT event_id, source_id,
       claim_context->>'column_was_already_set' AS column_was_already_set,
       (claim_context->>'apply_run_id' = :run_id) AS anchor_is_ours
  FROM event_provider_anchors
 WHERE source = :source
   AND source_id LIKE :source_id_prefix
   AND (claim_context->>'apply_run_id' = :run_id
        OR claim_context->>'column_write_run_id' = :run_id)
"""

#: The current value of every column the restore might clear, keyed by event.
#: Read by id rather than by re-running the window query: the manifest already
#: names the rows, and a window re-read would re-introduce the population drift
#: this repair exists to remove.
COLUMNS_NOW_SQL = """
SELECT id, statpal_fixture_id
  FROM events
 WHERE id = ANY(:event_ids)
"""

#: Who the anchors the manifest names are attributed to NOW, by either key. The
#: value CAS cannot tell a re-apply from an un-restored write, because a
#: re-apply writes the SAME fixture id back into the same column: `statpal_
#: fixture_id = :written` matches, and a stale undo line would clear a value it
#: does not own. The run ids can tell them apart, which is why they are read
#: here and not only in `ATTRIBUTED_ANCHORS_SQL` (CERT-2216).
ANCHORS_NOW_SQL = """
SELECT event_id, source_id,
       claim_context->>'apply_run_id' AS apply_run_id,
       claim_context->>'column_write_run_id' AS column_write_run_id
  FROM event_provider_anchors
 WHERE source = :source
   AND source_id = ANY(:source_ids)
"""

#: The CAS. `statpal_fixture_id = :written` is the whole guard: if another writer
#: has changed the column since the apply, this touches no row and the restore
#: reports it rather than overwriting a newer value with an older one.
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

#: Take this run's `column_write_run_id` back off an incumbent whose column we
#: just cleared (CERT-2216). Only for the column-only rows: where the anchor is
#: ours the DELETE above removes the whole row and there is nothing to unsay.
#:
#: The writer no longer refuses to replace a stale key, so this is not what makes
#: the re-apply case correct — `ATTRIBUTE_COLUMN_WRITE`'s EXISTS is. This is the
#: other half of the same invariant: **`column_write_run_id` names the run whose
#: column value is standing.** Once the column is NULL again the key is a false
#: statement about a durable row — it would keep re-appearing in this run's
#: `unbanked_anchors` forever, and it tells the next reader of that anchor that a
#: write nobody can point at once happened here.
#:
#: CAS'd on our own run id, so it can only ever remove what this run wrote: if a
#: later apply has already replaced the key, that apply's column write is the one
#: standing and this statement touches nothing.
CLEAR_COLUMN_ATTRIBUTION_SQL = """
UPDATE event_provider_anchors
   SET claim_context = claim_context - 'column_write_run_id'
 WHERE source = :source
   AND source_id = :source_id
   AND event_id = :event_id
   AND claim_context->>'column_write_run_id' = :run_id
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
                # Deliberately NOT an undo line. The undo replays the apply's
                # manifest, so it cannot be named until the apply has run and
                # printed its own run id (CERT-2207). A backup that advertised
                # an undo command would be advertising a restore of 0 rows.
                "next": "python3 scripts/soccer_statpal_stamp_3366.py apply",
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
    """The first write. Refuses unless a fresh, readable backup is on file.

    The receipt is banked under the SAME string that stamped every anchor, so
    `restore --identity <that string>` reaches both the manifest and the rows —
    one id an operator can copy out of one line of output.
    """
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

    run_id = f"{APPLY_IDENTITY_PREFIX}:{_stamp(now)}"
    result = await _run_stamp_soccer_statpal_fixtures(apply=True, apply_run_id=run_id)
    manifest = result.get("committed_write_receipts") or []
    undo = (
        "python3 scripts/soccer_statpal_stamp_3366.py restore "
        f"--identity {run_id} --apply"
    )
    receipt = {
        "verdict": "APPLIED",
        "apply_run_id": run_id,
        "backup_identity": identity,
        "manifest": manifest,
        "manifest_rows": len(manifest),
        "undo_command": undo,
        "result": result,
    }
    status = await _bank(receipt, run_id, now)
    print(json.dumps({"banked": status, **receipt}, indent=2, default=str))
    if status not in ("ok", "superseded"):
        # The writes are already durable — per-row commits (gotcha #13) — so
        # this is not a failed apply, it is an apply whose receipt is missing.
        # Say so loudly and point at the half that does not depend on it: every
        # anchor carries `run_id`, so the undo still reaches them.
        print(
            f"\nWARNING: the manifest did NOT bank ({status}). The writes stand.\n"
            f"The undo still works — every anchor this run inserted carries the\n"
            f"run id in its claim_context, and restore reads those directly:\n"
            f"  {undo}\n"
            f"Expect a non-zero `unbanked_anchors` count; that is this receipt\n"
            f"being missing, not a second defect."
        )
        return 1
    return 0


def merge_manifest(manifest, attributed) -> list[dict]:
    """The banked manifest, completed by what the table itself attributes.

    ``attributed`` is ``(event_id, source_id, column_was_already_set,
    anchor_is_ours)`` for every anchor this run is attributed on, by either key.
    Each one the manifest already lists is a duplicate; each one it does not is a
    write the apply committed but never got to bank, and it is reconstructed here
    rather than dropped — a row nobody can name is a row nobody can undo.

    The reconstruction is exact and needs no receipt: the anchor's ``source_id``
    is ``soccer:<fixture_id>``, which is the value the column write used, and the
    two attribution keys say which halves this run wrote. Both are recoverable
    from the anchor alone, which is why the anchor is where the run id lives.

    ``anchor_is_ours`` false is the CERT-2211 case — the anchor was already on
    file and only the column is this run's. ``column_written`` is then True
    unconditionally: the sole reason such a row is attributed at all is that
    ``_write_link`` committed a column write against it, and the incumbent's own
    ``column_was_already_set`` is a different writer's note about a different
    pass. Reading that flag here is what would leave the column behind.
    """
    merged = list(manifest or [])
    seen = {(str(e.get("event_id")), e.get("anchor_source_id")) for e in merged}
    for event_id, source_id, column_was_already_set, anchor_is_ours in attributed or ():
        if (str(event_id), source_id) in seen:
            continue
        merged.append(
            {
                "event_id": event_id,
                # `soccer:1043639` -> `1043639`; the column never holds the
                # namespace, only the id.
                "fixture_id": str(source_id).split(":", 1)[-1],
                "anchor_source_id": source_id,
                "column_written": (
                    (column_was_already_set is None) if anchor_is_ours else True
                ),
                "anchor_written": bool(anchor_is_ours),
                "unbanked": True,
            }
        )
    return merged


def plan_restore(
    manifest, columns_now, anchors_now, attributions_now=None, run_id=None
) -> dict:
    """Exactly what one apply committed, from that apply's own manifest.

    Pure, so the undo can be replayed over ``db-query`` rows before anybody runs
    it against production — the same pre-flight that caught a circular pre-check
    on the last repair this lane inherited.

    ``manifest`` is `merge_manifest`'s output. ``columns_now`` maps
    ``str(event_id) -> statpal_fixture_id`` as it stands now; ``anchors_now`` is
    the set of ``"<event_id>|<source_id>"`` currently on file;
    ``attributions_now`` maps that same key to the set of run ids the anchor
    currently carries, under either attribution key.

    THE TEST FOR "OURS" IS THE MANIFEST, AND THE TEST FOR "STILL OURS" IS THE
    VALUE. Nothing outside the manifest is ever touched, however it looks —
    which is what makes a foreign writer's row safe, and what makes a row that
    entered the window after the backup restorable. Inside the manifest, each
    half is checked against the state now, so an undo that arrives after someone
    else has edited the row reports instead of writing.

    EXCEPT THAT THE VALUE CANNOT SEE A RE-APPLY (CERT-2216). Apply A, restore A,
    apply B: B writes the SAME fixture id back into the same column, so
    ``statpal_fixture_id = :written`` matches and A's stale undo line clears a
    value A does not own — and where A had inserted the anchor, deletes B's
    anchor too. The value CAS is blind to this because nothing about the value
    changed; only the run ids can tell the two states apart. So an anchor that
    now attributes this correspondence to some OTHER run, and to no run of ours,
    is reported as ``reattributed`` and both halves are skipped. An anchor
    carrying no attribution at all is not a contradiction — that is the ordinary
    pre-repair and foreign-writer shape — and falls through to the value CAS as
    before.

    ``to_unattribute`` is the third, smaller list: the column-only rows whose
    column this restore is about to clear. Their anchor stays — it was never
    ours — so its ``column_write_run_id`` has to be taken back off by hand, or
    the anchor goes on claiming a write whose value no longer exists. It is a
    strict subset of ``to_clear``: a column we decline to clear is a write still
    standing, and its attribution is still true.
    """
    to_clear, to_delete, to_unattribute = [], [], []
    column_moved_on, anchor_already_gone, unbanked = [], [], []
    reattributed = []

    for entry in manifest or ():
        event_id = entry.get("event_id")
        if entry.get("unbanked"):
            unbanked.append(
                {"event_id": event_id, "source_id": entry.get("anchor_source_id")}
            )

        anchor_key = f"{event_id}|{entry.get('anchor_source_id')}"
        holders = (attributions_now or {}).get(anchor_key) or set()
        if run_id is not None and holders and run_id not in holders:
            # Somebody else's write is standing on this correspondence now.
            # Neither half is ours to undo, whatever the column happens to hold.
            reattributed.append(
                {
                    "event_id": event_id,
                    "source_id": entry.get("anchor_source_id"),
                    "attributed_to": sorted(holders),
                }
            )
            continue

        if entry.get("column_written"):
            written = entry.get("fixture_id")
            if columns_now.get(str(event_id)) == written:
                to_clear.append({"event_id": event_id, "written": written})
                if not entry.get("anchor_written"):
                    # A column-only row: the anchor survives the undo, so its
                    # `column_write_run_id` has to be unsaid separately or it
                    # outlives the value it describes (CERT-2216).
                    to_unattribute.append(
                        {
                            "event_id": event_id,
                            "source_id": entry.get("anchor_source_id"),
                        }
                    )
            else:
                column_moved_on.append(
                    {
                        "event_id": event_id,
                        "written": written,
                        "holds": columns_now.get(str(event_id)),
                    }
                )

        if entry.get("anchor_written"):
            source_id = entry.get("anchor_source_id")
            if f"{event_id}|{source_id}" in anchors_now:
                to_delete.append({"event_id": event_id, "source_id": source_id})
            else:
                anchor_already_gone.append(
                    {"event_id": event_id, "source_id": source_id}
                )

    return {
        "to_clear": to_clear,
        "to_delete": to_delete,
        "to_unattribute": to_unattribute,
        "column_moved_on": column_moved_on,
        "anchor_already_gone": anchor_already_gone,
        "unbanked_anchors": unbanked,
        "reattributed": reattributed,
    }


async def _load_manifest(session, identity: str):
    """The apply's manifest, completed by the anchors the table attributes to it.

    Returns ``(manifest, note)``. A manifest can be empty and valid — an apply
    that matched nothing — so "no rows" is never inferred to be "wrong id"; the
    identity's SHAPE is what is checked, and only up front.
    """
    from sqlalchemy import text

    from app.services.durable_snapshots import read_snapshot

    note = None
    banked: list[dict] = []
    got = await read_snapshot(
        session, identity, expected_version=SCHEMA_VERSION, max_age_s=float("inf")
    )
    if got.ok and (got.envelope.payload or {}).get("verdict") == "APPLIED":
        banked = (got.envelope.payload or {}).get("manifest") or []
    else:
        # Not fatal. The anchors carry the run id themselves, which is the whole
        # reason it is written there — an apply that died before banking is the
        # case this path exists for.
        note = (
            f"no readable APPLY receipt at {identity} ({got.status}); "
            "restoring from the anchors' own apply_run_id alone"
        )

    attributed = (
        await session.execute(
            text(ATTRIBUTED_ANCHORS_SQL),
            {
                "source": ANCHOR_SOURCE,
                "source_id_prefix": f"{ANCHOR_SOURCE_ID_PREFIX}%",
                "run_id": identity,
            },
        )
    ).fetchall()
    return merge_manifest(banked, [tuple(r) for r in attributed]), note


async def _state_now(session, manifest):
    """Only the rows the manifest names — never a re-read of the window.

    Re-reading the window is what let population drift into the undo in the
    first place; a restore should not be able to see a row its apply never
    touched.
    """
    from sqlalchemy import text

    event_ids = sorted({int(e["event_id"]) for e in manifest if e.get("event_id")})
    source_ids = sorted(
        {e["anchor_source_id"] for e in manifest if e.get("anchor_source_id")}
    )
    if not event_ids:
        return {}, set(), {}

    rows = (
        await session.execute(text(COLUMNS_NOW_SQL), {"event_ids": event_ids})
    ).fetchall()
    anchors = (
        await session.execute(
            text(ANCHORS_NOW_SQL),
            {"source": ANCHOR_SOURCE, "source_ids": source_ids or [""]},
        )
    ).fetchall()
    return (
        {str(r[0]): r[1] for r in rows},
        {f"{r[0]}|{r[1]}" for r in anchors},
        {f"{r[0]}|{r[1]}": {run for run in (r[2], r[3]) if run} for r in anchors},
    )


async def cmd_restore(identity: str, apply: bool, now: datetime) -> int:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    if identity.startswith(BACKUP_IDENTITY_PREFIX):
        # The interface changed with CERT-2207 and an operator holding an old
        # undo line must not get a silent no-op: a backup identity attributes
        # nothing, so this would restore 0 rows and report success.
        print(
            json.dumps(
                {
                    "verdict": "REFUSED",
                    "identity": identity,
                    "reason": (
                        "that is a BACKUP identity. The undo replays the APPLY's "
                        "manifest, so it needs the apply run id "
                        f"(`{APPLY_IDENTITY_PREFIX}:...`) printed by `apply` as "
                        "`undo_command`."
                    ),
                },
                indent=2,
            )
        )
        return 1

    async with get_task_session() as session:
        manifest, note = await _load_manifest(session, identity)
        columns_now, anchors_now, attributions_now = await _state_now(session, manifest)
        plan_result = plan_restore(
            manifest, columns_now, anchors_now, attributions_now, identity
        )
        to_clear = plan_result["to_clear"]
        to_delete = plan_result["to_delete"]

        counts = {
            "manifest_rows": len(manifest),
            "column_moved_on": len(plan_result["column_moved_on"]),
            "anchor_already_gone": len(plan_result["anchor_already_gone"]),
            "unbanked_anchors": len(plan_result["unbanked_anchors"]),
            # Non-zero means a LATER apply owns these rows now — this undo line
            # is stale. Restore that run instead; its id is on the anchor.
            "reattributed": len(plan_result["reattributed"]),
        }

        if not apply:
            plan = {
                "verdict": "RESTORE_DRY_RUN",
                "identity": identity,
                "note": note,
                "would_clear_columns": len(to_clear),
                "would_delete_anchors": len(to_delete),
                "would_unattribute": len(plan_result["to_unattribute"]),
                **counts,
                "sample": to_clear[:10],
            }
            await _bank(plan, f"{RESTORE_IDENTITY_PREFIX}:{_stamp(now)}", now)
            print(json.dumps(plan, indent=2, default=str))
            print("\nNothing written. Re-run with --apply to put these back.")
            return 0

        cleared = 0
        cleared_ids: set = set()
        moved_on: list[dict] = []
        for row in to_clear:
            result = await session.execute(
                text(CLEAR_COLUMN_SQL),
                {"event_id": row["event_id"], "written": row["written"]},
            )
            if result.rowcount or 0:
                cleared += 1
                cleared_ids.add(str(row["event_id"]))
            else:
                # Lost a race between the read above and this write.
                moved_on.append(row)
        # Only for the columns actually cleared. A column we lost the race on is
        # a write still standing, and its attribution is still the true one.
        unattributed = 0
        for row in plan_result["to_unattribute"]:
            if str(row["event_id"]) not in cleared_ids:
                continue
            result = await session.execute(
                text(CLEAR_COLUMN_ATTRIBUTION_SQL),
                {
                    "source": ANCHOR_SOURCE,
                    "source_id": row["source_id"],
                    "event_id": row["event_id"],
                    "run_id": identity,
                },
            )
            unattributed += result.rowcount or 0
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

    counts["column_moved_on"] += len(moved_on)
    receipt = {
        "verdict": "RESTORED",
        "identity": identity,
        "note": note,
        "columns_cleared": cleared,
        "anchors_deleted": deleted,
        # Incumbent anchors this run's `column_write_run_id` came back off. Not
        # a fourth thing undone — a bookkeeping count for the anchors that
        # survive, and the number an operator compares to `columns_cleared`
        # minus `anchors_deleted` if they want to check the arithmetic.
        "attributions_cleared": unattributed,
        **counts,
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
    restore.add_argument(
        "--identity",
        required=True,
        help="the APPLY run id to undo (printed by `apply` as undo_command)",
    )
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
