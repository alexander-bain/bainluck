"""Queue 340 — ``events.statpal_fixture_id = ''`` → NULL (data-repair lane).

THE DEFECT. ``''`` and NULL both mean "we have no StatPal id for this event", but
they are not interchangeable to the database:

* only NULL is exempt from a unique index, so 8,272 rows sharing the literal value
  ``''`` make ``statpal_fixture_id`` structurally un-uniqueable;
* only NULL compares correctly — ``COUNT(statpal_fixture_id)`` and every
  ``statpal_fixture_id IS NOT NULL`` predicate counts a blank as a real linkage.
  Three live surfaces read exactly that way and are therefore over-reporting
  StatPal coverage today: ``app/tasks/data_quality_watchdog.py`` (the Tier-1
  coverage query), ``app/routes/admin_source_health.py`` (``"statpal"``), and the
  ``COUNT(e.statpal_fixture_id)`` linkage tiles in ``app/utils/admin_dashboard.py``
  / ``app/routes/admin_matching.py``.

So "do we have a StatPal id?" currently depends on which of two spellings of
absence a given row happens to carry. That is the bug.

WHY THE WRITE IS SAFE. Every code path that CONSUMES the column tests it for
truthiness, not for NULL-ness, so ``''`` and NULL are already indistinguishable to
them and this repair changes no behaviour there:

    event_registry._attach_claim   ``if not event.statpal_fixture_id:``  (overwrites)
    statpal_sync._get_statpal_id   ``if ... and event.statpal_fixture_id:`` (falls
                                   back to the ``win_probability_sources`` JSONB
                                   mirror, which this repair does not touch)

Only the ``IS NOT NULL`` / ``COUNT()`` readers change — and they change from wrong
to right.

NO LIVE PRODUCER (verified two ways, 2026-08-12):

  1. Measured on production — all 8,272 blank rows were created
     ``2026-02-22 03:04:59Z`` → ``2026-03-04 05:06:12Z``. A bounded historical
     cohort that stopped five months ago.
  2. Read in the tree — both ``_set_statpal_id`` call sites (``statpal_sync.py``
     :194 and :769) are guarded by ``if fixture.fixture_id and ...``, and
     ``_attach_claim`` only assigns ``claim.source_id``. No path can emit ``''``
     today, so this repair is a one-shot, not a recurring sweep.

THE EXACT-MATCH GATE (queue 339S's discipline). ``apply`` is refused unless the
LIVE before-census blank count equals ``expected_blank`` — measured on production
five minutes before this was written, hence the 8,272 default. A drifted census
means the population you measured is not the population you are about to write, and
the correct response is to re-measure, not to write anyway. The refusal is a
verdict in the result dict, never an exception: an operator must be able to read
the observed count and re-invoke with it.

    A DEADLINE-STOPPED RUN THEREFORE NEEDS AN EXPLICIT RESUME. Once a partial run
    commits, the live blank count is below 8,272 and the gate will (correctly)
    refuse the next call. Re-invoke with ``expected_blank=<the ``before.blank``
    the last response reported>``. That friction is the point.

OUT OF SCOPE — THE 8 DUPLICATE REAL IDS. Eight real ``statpal_fixture_id`` values
are carried by two events each (16 rows): ``1027790``, ``1027792``, ``1329190539``,
``1329190569``, ``1329200227``, ``627215``, ``637968``, ``637987``. This repair
REPORTS them (with their event ids, so the follow-up is a lookup and not a
re-investigation) and touches none of them. Clearing a duplicate pair means
deciding which of two events is the real fixture and what happens to the other's
data — attended, by-name work, and NOT this repair's job. Until it is done,
``statpal_fixture_id`` still cannot carry a unique index even after every blank is
NULLed.

D51 — THE BACKUP AND THE ONE-COMMAND RESTORE. Alex's D51(b) lets the owning lane
apply a data repair UNATTENDED only if it writes a backup first and ships a
one-command restore. This rail had a correct write and neither of those, which is
why 8,272 rows sat behind a finished repair for three weeks.

The backup cannot be re-derived after the fact at any price: once a blank row is
NULL it is indistinguishable from the 220,348 rows that were always NULL. So the
receipt is the only surviving record of which rows a run changed, and it is
written BEFORE the first write (empty), then extended and CO-COMMITTED with each
batch. The invariant is exact and is what a partial run rests on:

    at every instant, the durable record names exactly the rows committed as
    NULL — never more, never fewer

    POST /api/admin/repairs/statpal-blank-ids?apply=false   # dry-run census
    POST /api/admin/repairs/statpal-blank-ids?apply=true    # commit
    POST /api/admin/repairs/statpal-blank-ids?apply=true&expected_blank=3272  # resume
    POST /api/admin/repairs/statpal-blank-ids?undo_identity=<id>              # dry-run
    POST /api/admin/repairs/statpal-blank-ids?undo_identity=<id>&apply=true   # restore

    python3 scripts/repair_statpal_fixture_id_blanks.py            # dry-run
    python3 scripts/repair_statpal_fixture_id_blanks.py --apply
    python3 scripts/repair_statpal_fixture_id_blanks.py --restore <identity> --apply

Heroku one-off (gotcha #48 — a non-detached run does not execute in the sandbox;
PROJECT_PATH=backend puts scripts at /app, so NO ``cd backend``). Prefer the
endpoint: it is self-verifying and this script's census is not visible from a
detached dyno's (empty) stdout.
"""
import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# The measured production blank count (2026-08-12). The gate's default, and the
# only value that lets an unqualified ``apply=true`` write.
EXPECTED_BLANK_COUNT = 8272

# Rows per committed batch. ``events`` is a hot table and a single 8,272-row
# UPDATE holds row locks against the live pollers for its whole duration
# (memory: heroku one-off events-table lock contention). Bounded id-RANGE
# batches with a commit each keep every lock window short and leave partial
# progress durable. A module constant, not a param, so it cannot be dialled
# off mid-run.
BATCH_SIZE = 1000

# One uninterrupted op here is a single ~1,000-row indexed UPDATE (measured
# census cost on the same table: 172ms), so the reserve bounds the longest
# single op, not just the loop boundary (memory: budget guard inner-op).
_DEADLINE_SECONDS = 22.0
_BATCH_RESERVE_SECONDS = 5.0

# ONE census definition, used for both the before- and after- reading, so the
# gate and the proof can never be computed over different populations.
_CENSUS_SQL = """
    SELECT COUNT(*) FILTER (WHERE statpal_fixture_id = '')        AS blank,
           COUNT(*) FILTER (WHERE statpal_fixture_id IS NULL)     AS nulls,
           COUNT(*) FILTER (WHERE statpal_fixture_id IS NOT NULL
                              AND statpal_fixture_id <> '')       AS real,
           COUNT(*)                                               AS total
    FROM events
"""

# The blank ids, ordered, so the batches are contiguous id ranges. Served from
# ix_events_statpal_fixture_id — it never scans the table.
_BLANK_IDS_SQL = """
    SELECT id FROM events WHERE statpal_fixture_id = '' ORDER BY id
"""

# Bounded by an id RANGE rather than ``id = ANY(:ids)``: an array-bound UPDATE on
# this table has rolled back silently before (memory: events-table lock
# contention). The predicate is repeated so the write can only ever touch blanks,
# even if a row inside the range changed between the SELECT and the UPDATE.
#
# ``RETURNING id`` is the undo record's whole basis and is not decoration. The
# bound is a RANGE, so ``(lo, hi)`` spans ids this write never touched, and the
# repeated ``= ''`` predicate is exactly what makes it so: the coarse range is
# safe for the WRITE and useless as a RECEIPT. A restore driven off the range
# would set ``''`` onto rows that were never blank — CERT-846's finding on the
# sibling rail, where an undo built from the PLAN put an id back onto a row the
# apply never wrote. The ids the database says it changed are the only honest
# answer, and they arrive in the same statement, so no second read can drift.
_NULL_BATCH_SQL = """
    UPDATE events
       SET statpal_fixture_id = NULL
     WHERE id >= :lo AND id <= :hi
       AND statpal_fixture_id = ''
 RETURNING id
"""

# Reported, never touched. Real (non-blank) values carried by more than one event.
_DUPLICATES_SQL = """
    SELECT statpal_fixture_id AS value,
           ARRAY_AGG(id ORDER BY id) AS event_ids,
           COUNT(*) AS rows
    FROM events
    WHERE statpal_fixture_id IS NOT NULL AND statpal_fixture_id <> ''
    GROUP BY 1
    HAVING COUNT(*) > 1
    ORDER BY 1
"""


# ═══ THE UNDO RECORD (D51) ═══
#
# D51(b) lets the owning lane apply a data repair UNATTENDED only when it writes
# a backup first and ships a one-command restore. This rail had neither, which is
# why 8,272 rows sat un-drained behind a correct repair: the write was ready and
# the reversal was not.
#
# WHAT A BACKUP HAS TO BE HERE. After the write, a repaired row is
# indistinguishable from the 220,348 rows that were always NULL — the population
# cannot be re-derived from the table afterwards at any price. So the receipt is
# not a convenience, it is the only surviving copy of which rows this run
# changed, and it has to be durable before the row it describes is committed.
#
# THE RECEIPT IS CUMULATIVE AND CO-COMMITTED. Each batch stages the full set of
# ids nulled SO FAR into the caller's open transaction and commits both together
# (CERT-851's shape on the sibling rail). The invariant that buys:
#
#     at every instant, the durable record names exactly the rows that are
#     committed as NULL — never more, never fewer
#
# A record written before the batch would claim rows that may roll back; one
# written after leaves a durable row nothing claims. Staging it beside the write
# removes the window instead of choosing which side of it to fall on. A
# deadline-stopped run therefore needs no reconciliation: its last commit carried
# its own complete receipt.
UNDO_IDENTITY_PREFIX = "repair:statpal_fixture_id_blanks:undo"
UNDO_SCHEMA = "statpal-blank-ids-undo/v1"

#: The record's owner token lives under this key, and the store refuses a
#: replacement by anyone else (CERT-856). One apply, one receipt.
UNDO_OWNER_KEY = "undo_invocation"

#: An undo must outlive the incident that needs it, not the day. A plan going
#: stale is a safety feature; an undo going stale is the loss of the only record
#: that this repair can be taken back at all.
UNDO_MAX_AGE_S = 365 * 86400

REASON_UNDO_UNWRITTEN = "UNDO_UNWRITTEN"
REASON_UNDO_LOST = "UNDO_LOST_MID_RUN"
REASON_UNDO_MISSING = "UNDO_MISSING"
REASON_UNDO_CORRUPT = "UNDO_CORRUPT"
#: "The read failed right now" — a THIRD reading, never folded into MISSING. An
#: operator told the record is missing stops looking for it, which is the wrong
#: move when it is there and the read fell over.
REASON_UNDO_UNREADABLE = "UNDO_UNREADABLE"

#: Per-row restore outcomes. Closed set. ``RELINKED`` is not a failure — it is
#: the restore declining to overwrite a fresher truth, and it is named so a
#: reader can tell "restored 8,272 of 8,272" from "restored 8,270 and left 2".
RESTORE_OUTCOMES = ("RESTORED", "RELINKED")

# Restoring writes '' back onto rows this run NULLed — and NULLing them is
# precisely what makes them visible to every forward linker (`statpal_fixture_id
# IS NULL` is the standard candidate guard). So between the apply and the
# restore, a linker may legitimately have given one of these rows a REAL StatPal
# id, and putting '' back over it would destroy a correct linkage to undo a
# repair that had already succeeded. The `IS NULL` predicate refuses exactly
# those rows; they are counted and named, never silently skipped.
_RESTORE_SQL = """
    UPDATE events
       SET statpal_fixture_id = ''
     WHERE id = ANY(:ids)
       AND statpal_fixture_id IS NULL
 RETURNING id
"""

#: Rows in the receipt that the restore refused because they no longer hold NULL.
_RESTORE_RELINKED_SQL = """
    SELECT id, statpal_fixture_id
      FROM events
     WHERE id = ANY(:ids)
       AND statpal_fixture_id IS NOT NULL
     ORDER BY id
"""


def new_undo_invocation() -> str:
    """A fresh token for ONE apply. Never derived from the work it is about.

    CERT-856 on the sibling rail: two applies starting in the same instant agree
    on the clock and on the population, so an identity built from those alone is
    the SAME identity in both runs, and the second run's receipt silently
    replaced the first's. The token is the one thing two concurrent runs cannot
    agree on, and it is both the identity's salt and the record's owner.
    """
    return uuid.uuid4().hex[:12]


def undo_identity_for(*, at: datetime, invocation: str) -> str:
    """One identity per INVOCATION, carrying the stamp and the token.

    ``invocation`` is required rather than defaulted: the record's owner must be
    this same token, and a default would let a caller build an identity nobody
    owns — which is an identity the store cannot protect.
    """
    at_utc = at.astimezone(timezone.utc)
    stamp = f"{at_utc.strftime('%Y%m%dT%H%M%S')}.{at_utc.microsecond // 1000:03d}Z"
    return f"{UNDO_IDENTITY_PREFIX}:{stamp}:{invocation}"


def restore_command(identity: str) -> str:
    """The one command D51 requires, with this run's own identity baked in."""
    return (
        "python3 scripts/repair_statpal_fixture_id_blanks.py "
        f"--restore {identity}"
    )


def undo_payload(
    *,
    invocation: str,
    started_at: datetime,
    event_ids: list[int],
    complete: bool,
    expected_blank: int,
) -> dict[str, Any]:
    """The record a restore reads, and nothing it does not need.

    ``event_ids`` is THE RECEIPT — rows this apply actually NULLed, as the
    database reported them via ``RETURNING``. It is never the planned list: a
    plan is what the run set out to do, and the two differ exactly when
    something else moved a row underneath it.
    """
    identity = undo_identity_for(at=started_at, invocation=invocation)
    return {
        "schema": UNDO_SCHEMA,
        "issue": "#2963",
        "repair": "statpal-blank-ids",
        UNDO_OWNER_KEY: invocation,
        "started_at": started_at.astimezone(timezone.utc).isoformat(),
        "expected_blank": int(expected_blank),
        # The prior value is one literal for every row, so it is stated once
        # rather than repeated 8,272 times.
        "prior_value": "",
        "event_ids": [int(i) for i in event_ids],
        "rows": len(event_ids),
        "complete": bool(complete),
        "restore_command": restore_command(identity),
        "restore_note": (
            "Writes '' back onto exactly these ids, and only where the row still "
            "holds NULL. A row a linker has since given a real StatPal id is "
            "refused and reported — undoing this repair must not destroy a "
            "linkage the repair itself made reachable."
        ),
    }


def _undo_envelope(identity: str, payload: dict[str, Any], generation: int):
    from app.utils.durable_state import DurableEnvelope

    return DurableEnvelope.build(
        identity=identity,
        schema_version=UNDO_SCHEMA,
        payload=payload,
        # Strictly advancing per batch, and NOT clock-derived: the store's guard
        # is ``generation <= EXCLUDED.generation``, and two batches inside one
        # millisecond would otherwise share a generation.
        generation=generation,
        complete=bool(payload.get("complete")),
        source="repair:statpal-blank-ids:undo",
    )


def _classify_undo_write(identity: str, status: Optional[str]) -> tuple[bool, str]:
    """One reading of a durable stage dict, shared by both write paths.

    ``superseded`` and ``occupied`` are FAILURES here. For a snapshot whose
    identity names a THING, a newer copy winning is correct; for a receipt whose
    identity names an EVENT, it means the record on file is not this apply's, and
    accepting it hands an operator a restore that puts back the wrong rows.
    """
    if status == "ok":
        return True, "ok"
    if status == "occupied":
        return False, (
            f"undo persist REFUSED: {identity} is owned by another apply's "
            f"invocation, so this run's receipt was not stored"
        )
    if status == "superseded":
        return False, (
            f"undo persist REFUSED: {identity} already holds a newer generation; "
            f"this run's receipt was not stored"
        )
    return False, f"undo persist failed for {identity}: status={status!r}"


async def _stage_undo_in_txn(
    session, identity: str, payload: dict[str, Any], generation: int
) -> tuple[bool, str]:
    """Stage this receipt in the caller's OPEN transaction. Never commits."""
    from app.services.durable_snapshots import publish_owned_snapshot_in_txn

    try:
        stage = await publish_owned_snapshot_in_txn(
            session,
            _undo_envelope(identity, payload, generation),
            owner_key=UNDO_OWNER_KEY,
            owner=payload[UNDO_OWNER_KEY],
        )
    # (This comment is load bearing for `scan_mutation_residue.py` Pass B —
    # without a line here, the closing paren above plus the bare `noqa` below
    # reproduce `typeahead_outcome_arm_mutations:M2-NO-LIMIT`'s replacement
    # literal verbatim and this file reads as mutation residue. Do not delete.)
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        logger.warning("#2963 undo stage raised: %s", type(exc).__name__)
        return False, f"undo stage raised: {type(exc).__name__}"
    return _classify_undo_write(identity, stage.get("status"))


async def _save_undo_committed(
    session, identity: str, payload: dict[str, Any], generation: int
) -> tuple[bool, str]:
    """Stage a receipt on the caller's session and commit it alone.

    Used at the two moments with no data write pending — the empty record before
    the first batch, and the seal after the last. Deliberately the SAME session
    as the repair rather than a standalone one: a second connection would put
    the receipt outside the transactional world its own batches live in, and a
    failed stage there could not be cleared by the rollback that keeps this one
    usable.
    """
    ok, note = await _stage_undo_in_txn(session, identity, payload, generation)
    if not ok:
        # Postgres aborts a transaction on a failed statement, so the session is
        # unusable until it is rolled back — and the caller still has a census to
        # report.
        await session.rollback()
        return False, note
    await session.commit()
    return True, note


def _census(row) -> dict:
    return {
        "blank": int(row.blank),
        "nulls": int(row.nulls),
        "real": int(row.real),
        "total": int(row.total),
    }


def batch_ranges(ids: list[int], batch_size: int = BATCH_SIZE) -> list[tuple[int, int]]:
    """Contiguous ``(lo, hi)`` id ranges covering ``ids``, ``batch_size`` ids each.

    Pure, so the batching contract is testable without a database. Inclusive on
    both ends — ``_NULL_BATCH_SQL`` uses ``>= lo AND <= hi``. Ranges may span ids
    that are NOT blank; the UPDATE's repeated ``= ''`` predicate is what keeps the
    write exact, which is why the ranges may be coarse but the rowcounts cannot be.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    return [
        (chunk[0], chunk[-1])
        for chunk in (ids[i : i + batch_size] for i in range(0, len(ids), batch_size))
    ]


async def repair(
    session,
    apply: bool,
    expected_blank: int = EXPECTED_BLANK_COUNT,
    deadline_seconds: float = _DEADLINE_SECONDS,
    undo_identity: Optional[str] = None,
) -> dict:
    """Session-taking core, shared by the CLI and
    ``POST /api/admin/repairs/statpal-blank-ids``.

    ``undo_identity`` names ONE earlier apply's receipt and puts its rows back.
    It takes precedence over every other argument — an undo is never also a
    repair — and is itself dry-run unless ``apply`` is true. Declaring it here is
    what makes the D51 restore a real runnable thing on the same rail with the
    same auth, rather than a CLI line whose output a detached one-off eats
    (gotcha #48).

    Returns the before census unconditionally, the duplicate-pair report
    unconditionally, and — when it wrote — the after census, so the response body
    is its own proof (gotcha #48/#53: "it returned" is not "it worked", and a
    zero-yield run must be loud rather than indistinguishable from a clean one).

    Writes nothing when ``apply`` is False, and nothing when the exact-match gate
    refuses. The refusal is returned, not raised.
    """
    import time

    from sqlalchemy import text

    s = session

    # An undo is never also a repair. Checked before the census so a restore
    # cannot be mistaken for a drift refusal on a population it does not read.
    if undo_identity:
        return await restore(s, undo_identity, apply=apply)

    started = time.monotonic()

    before = _census((await s.execute(text(_CENSUS_SQL))).one())
    duplicates = [
        {"value": r.value, "event_ids": list(r.event_ids), "rows": int(r.rows)}
        for r in (await s.execute(text(_DUPLICATES_SQL))).all()
    ]
    dup_ids = {i for d in duplicates for i in d["event_ids"]}

    result = {
        "repair": "statpal-blank-ids",
        "applied": False,
        "before": before,
        "expected_blank": int(expected_blank),
        "batch_size": BATCH_SIZE,
        # Out of scope, reported so the follow-up is a lookup (see module docstring).
        "duplicate_real_values": duplicates,
        "duplicate_value_count": len(duplicates),
        "duplicate_row_count": sum(d["rows"] for d in duplicates),
        "duplicates_note": (
            "REPORTED, NOT TOUCHED. Clearing a duplicate pair is attended, by-name "
            "work. statpal_fixture_id cannot carry a unique index until both the "
            "blanks are NULLed AND these pairs are resolved."
        ),
    }

    if before["blank"] == 0:
        # Idempotent no-op, said out loud rather than reported as a clean apply.
        result["terminal"] = "noop"
        result["verdict"] = "already_clean"
        result["rows_nulled"] = 0
        result["after"] = before
        return result

    if not apply:
        result["terminal"] = "noop"
        result["verdict"] = "dry_run"
        result["would_null"] = before["blank"]
        result["would_batch_count"] = -(-before["blank"] // BATCH_SIZE)
        return result

    # --- THE EXACT-MATCH GATE ------------------------------------------------
    # Apply only on an exact census match. A drifted census means the population
    # measured is not the population about to be written.
    if before["blank"] != int(expected_blank):
        result["terminal"] = "failed"
        result["verdict"] = "refused_census_drift"
        result["refused"] = True
        result["reason"] = (
            f"exact-match gate: live blank count is {before['blank']}, expected "
            f"{int(expected_blank)}. NOTHING WAS WRITTEN. Re-measure, then re-invoke "
            f"with expected_blank={before['blank']} if that count is the population "
            f"you intend to NULL."
        )
        return result

    ids = [int(r.id) for r in (await s.execute(text(_BLANK_IDS_SQL))).all()]
    # Read the module global at CALL time, not at def time, so the constant is
    # the single knob (and a test can shrink it without redefining the default).
    ranges = batch_ranges(ids, BATCH_SIZE)

    # --- BACKUP BEFORE WRITE (D51) -------------------------------------------
    # Not one row is NULLed until this apply's own receipt is on disk, EMPTY. At
    # this instant the true answer to "what has this run changed" is "nothing",
    # and a record that claims otherwise is the defect CERT-846 found on the
    # sibling rail. The order is the whole point: a backup written afterwards is
    # a backup that does not exist for exactly the run that died halfway.
    from app.utils.durable_state import generation_for

    started_at = datetime.now(timezone.utc)
    invocation = new_undo_invocation()
    identity = undo_identity_for(at=started_at, invocation=invocation)
    generation_base = generation_for(started_at)

    def _record(event_ids: list[int], *, complete: bool) -> dict:
        return undo_payload(
            invocation=invocation,
            started_at=started_at,
            event_ids=event_ids,
            complete=complete,
            expected_blank=int(expected_blank),
        )

    undo_ok, undo_note = await _save_undo_committed(
        s, identity, _record([], complete=False), generation_base
    )
    result["undo_identity"] = identity
    result["restore_command"] = restore_command(identity)
    if not undo_ok:
        result["terminal"] = "failed"
        result["verdict"] = "refused_undo_unwritten"
        result["refused"] = True
        result["reason_codes"] = [REASON_UNDO_UNWRITTEN]
        result["undo_note"] = undo_note
        result["rows_nulled"] = 0
        result["after"] = before
        result["reason"] = (
            "NOTHING WAS WRITTEN. This apply's undo record could not be stored, "
            "and the rows it would have NULLed cannot be identified again "
            "afterwards — a repaired row is indistinguishable from the 220,348 "
            "that were always NULL. Unreversible is not a state this repair may "
            f"enter unattended (D51). {undo_note}"
        )
        return result

    batches: list[dict] = []
    nulled_ids: list[int] = []
    stopped_on_deadline = False
    undo_lost: Optional[str] = None
    for ordinal, (lo, hi) in enumerate(ranges, start=1):
        if time.monotonic() - started > deadline_seconds - _BATCH_RESERVE_SECONDS:
            # Stop cleanly. Committed batches stand — each carried its own
            # receipt — and the operator resumes with the NEW blank count.
            stopped_on_deadline = True
            break
        batch_ids = [
            int(r.id)
            for r in (
                await s.execute(text(_NULL_BATCH_SQL), {"lo": lo, "hi": hi})
            ).all()
        ]
        # The receipt for this batch is the CUMULATIVE set, staged in the same
        # transaction as the write it describes and committed with it. So at
        # every instant the durable record names exactly the rows committed as
        # NULL — a crash between two batches leaves nothing to reconcile.
        staged_ok, undo_note = await _stage_undo_in_txn(
            s, identity, _record(nulled_ids + batch_ids, complete=False),
            generation_base + ordinal,
        )
        if not staged_ok:
            # This batch's write must not outlive its receipt. The rollback takes
            # the data with it, leaving nothing written and nothing claimed —
            # the only state that needs no reconciliation.
            await s.rollback()
            undo_lost = undo_note
            break
        await s.commit()
        nulled_ids.extend(batch_ids)
        batches.append({"lo": lo, "hi": hi, "rows": len(batch_ids)})

    rows_nulled = len(nulled_ids)
    after = _census((await s.execute(text(_CENSUS_SQL))).one())

    complete = (
        not stopped_on_deadline and undo_lost is None and after["blank"] == 0
    )

    # Seal the receipt: the same ids, with the run's terminal state on it. The
    # ids are already durable from the last batch commit, so a failure HERE
    # loses the flag and not the receipt — reported as its own field rather than
    # folded into the verdict, because the restore still works either way.
    sealed_ok, seal_note = await _save_undo_committed(
        s, identity,
        _record(nulled_ids, complete=complete),
        generation_base + len(ranges) + 1,
    )
    result.update({
        "applied": True,
        "terminal": "complete" if complete else "partial",
        "verdict": (
            "cleared" if complete
            else "partial_undo_lost" if undo_lost is not None
            else "partial_resume_required"
        ),
        # The receipt, and the command that reads it. Present on every applied
        # run, including a partial one — especially a partial one.
        "undo_identity": identity,
        "undo_rows": rows_nulled,
        "undo_sealed": sealed_ok,
        "undo_seal_note": seal_note,
        "restore_command": restore_command(identity),
        "batches": batches,
        "batches_planned": len(ranges),
        "batches_committed": len(batches),
        "commits": len(batches),
        "rows_nulled": rows_nulled,
        "after": after,
        "stopped_on_deadline": stopped_on_deadline,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        # The self-verification: the ONLY column that may move is blank -> nulls.
        "census_consistent": (
            after["blank"] == before["blank"] - rows_nulled
            and after["nulls"] == before["nulls"] + rows_nulled
            and after["real"] == before["real"]
            and after["total"] == before["total"]
        ),
        # The duplicate pairs carry REAL ids, so they can never be in the blank
        # id set — assert it rather than assume it, and confirm the real-id
        # population is numerically untouched.
        "duplicates_untouched": (
            dup_ids.isdisjoint(ids) and after["real"] == before["real"]
        ),
    })
    if undo_lost is not None:
        result["reason_codes"] = [REASON_UNDO_LOST]
        result["undo_note"] = undo_lost
        result["reason"] = (
            f"STOPPED after {rows_nulled} row(s). A batch's receipt could not be "
            f"stored, so that batch was rolled back and nothing beyond it was "
            f"attempted. Every committed row is on the record at "
            f"{identity}. {undo_lost}"
        )
    if not complete:
        result["resume_with_expected_blank"] = after["blank"]
    return result


async def read_undo(identity: str) -> tuple[Optional[dict], str]:
    """Read one apply's receipt. Returns ``(payload, reason)``.

    ``expected_version`` is load-bearing rather than decorative: a record of some
    other schema cannot be reinterpreted as a receipt of THIS shape, so it reads
    as missing instead of being restored from.
    """
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        got = await read_snapshot_standalone(
            identity, expected_version=UNDO_SCHEMA, max_age_s=UNDO_MAX_AGE_S
        )
    # (Load bearing for `scan_mutation_residue.py` Pass B, as above — this line
    # is what stops the paren + bare `noqa` pair reading as
    # `typeahead_outcome_arm_mutations:M2-NO-LIMIT`. Do not delete.)
    except Exception as exc:  # noqa: BLE001 — a raise is UNREADABLE, not MISSING
        logger.warning("#2963 undo read raised: %s", type(exc).__name__)
        return None, REASON_UNDO_UNREADABLE
    if got.status == "missing":
        return None, REASON_UNDO_MISSING
    if not got.ok or got.envelope is None:
        # Any other non-ok status (checksum, version, age, incomplete) is a
        # record that exists and cannot be trusted — never MISSING.
        return None, REASON_UNDO_CORRUPT
    payload = got.envelope.payload
    if not isinstance(payload, dict) or not isinstance(payload.get("event_ids"), list):
        return None, REASON_UNDO_CORRUPT
    return payload, "ok"


async def restore(session, identity: str, apply: bool = True) -> dict:
    """Put ``''`` back on exactly the rows one apply NULLed. The D51 reversal.

    Reads the receipt and nothing else — never the current blank population,
    which is a different set by construction (the apply emptied it).

    A row that no longer holds NULL is REFUSED, counted and named. Between the
    apply and the restore, a forward linker may legitimately have written a real
    StatPal id onto one of these rows — that is what NULLing them was FOR — and
    putting ``''`` back over it would destroy a correct linkage in the name of
    undoing a repair that had already done its job.
    """
    from sqlalchemy import text

    s = session
    payload, reason = await read_undo(identity)
    if payload is None:
        return {
            "repair": "statpal-blank-ids",
            "action": "restore",
            "identity": identity,
            "applied": False,
            "refused": True,
            "terminal": "failed",
            "verdict": "refused_" + reason.lower(),
            "reason_codes": [reason],
            "reason": (
                f"NOTHING WAS WRITTEN. The undo record {identity} could not be "
                f"read as a {UNDO_SCHEMA} receipt ({reason})."
            ),
            "rows_restored": 0,
        }

    ids = [int(i) for i in payload["event_ids"]]
    result = {
        "repair": "statpal-blank-ids",
        "action": "restore",
        "identity": identity,
        "receipt_rows": len(ids),
        "receipt_complete": bool(payload.get("complete")),
        "receipt_started_at": payload.get("started_at"),
        "applied": False,
        "rows_restored": 0,
    }

    # Named before the write, so the reading is the same on a dry run and on an
    # apply — the operator sees what will be refused before deciding.
    relinked = [
        {"event_id": int(r.id), "statpal_fixture_id": r.statpal_fixture_id}
        for r in (await s.execute(text(_RESTORE_RELINKED_SQL), {"ids": ids})).all()
    ] if ids else []
    result["relinked"] = relinked
    result["relinked_count"] = len(relinked)
    result["relinked_note"] = (
        "REFUSED, not restored. These rows hold a StatPal id today; the restore "
        "does not overwrite one to put '' back."
    )

    if not ids:
        result["terminal"] = "noop"
        result["verdict"] = "empty_receipt"
        result["note"] = (
            "The receipt names no rows — this apply was refused or died before "
            "its first batch committed. Nothing to restore."
        )
        return result

    if not apply:
        result["terminal"] = "noop"
        result["verdict"] = "dry_run"
        result["would_restore"] = len(ids) - len(relinked)
        return result

    restored = [
        int(r.id) for r in (await s.execute(text(_RESTORE_SQL), {"ids": ids})).all()
    ]
    await s.commit()

    result.update({
        "applied": True,
        "rows_restored": len(restored),
        "terminal": "complete" if len(restored) + len(relinked) == len(ids) else "partial",
        "verdict": "restored" if not relinked else "restored_with_refusals",
        # The two outcomes must account for every id in the receipt. When they
        # do not, a row vanished from `events` between the apply and now, and
        # that is a different incident — said out loud, not absorbed.
        "accounted": len(restored) + len(relinked) == len(ids),
    })
    if not result["accounted"]:
        result["reason"] = (
            f"{len(ids)} row(s) in the receipt, {len(restored)} restored and "
            f"{len(relinked)} refused as re-linked — the remainder are no longer "
            f"in `events` at all. Investigate before re-running."
        )
    return result


async def run_restore(identity: str, apply: bool) -> None:
    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        res = await restore(s, identity, apply=apply)

    print(f"=== statpal-blank-ids RESTORE ({'APPLY' if apply else 'DRY-RUN'}) ===")
    print(f"identity  {identity}")
    if res.get("refused"):
        print(f"\nREFUSED — {res['reason']}")
        return
    print(f"receipt   {res['receipt_rows']} row(s), complete={res['receipt_complete']}, "
          f"started {res.get('receipt_started_at')}")
    if res["relinked_count"]:
        print(f"refused   {res['relinked_count']} row(s) now hold a real StatPal id:")
        for r in res["relinked"][:20]:
            print(f"    event {r['event_id']}: {r['statpal_fixture_id']}")
        if res["relinked_count"] > 20:
            print(f"    … and {res['relinked_count'] - 20} more")
    if not apply:
        print(f"\nDRY-RUN — would restore '' onto {res.get('would_restore', 0)} row(s). "
              f"No writes made. Pass --apply to commit.")
        return
    print(f"\nRESTORED {res['rows_restored']} row(s)")
    if not res.get("accounted"):
        print(f"⚠️  {res.get('reason')}")
    elif res["terminal"] == "complete":
        print("✅ every row in the receipt is accounted for.")


async def run(apply: bool, expected_blank: int) -> None:
    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        res = await repair(s, apply, expected_blank=expected_blank)

    b = res["before"]
    print(f"=== statpal-blank-ids ({'APPLY' if apply else 'DRY-RUN'}) ===")
    print(f"BEFORE  blank={b['blank']}  nulls={b['nulls']}  real={b['real']}  "
          f"total={b['total']}")
    print(f"duplicate real values (OUT OF SCOPE, untouched): "
          f"{res['duplicate_value_count']} values / {res['duplicate_row_count']} rows")
    for d in res["duplicate_real_values"]:
        print(f"    {d['value']}: events {d['event_ids']}")

    if res.get("refused"):
        print(f"\nREFUSED — {res['reason']}")
        return
    if not apply:
        print(f"\nDRY-RUN — would NULL {res.get('would_null', 0)} row(s) in "
              f"{res.get('would_batch_count', 0)} batch(es) of {BATCH_SIZE}. "
              f"No writes made. Pass --apply to commit.")
        return

    a = res.get("after", b)
    print(f"\nCOMMITTED {res['rows_nulled']} row(s) in {res['batches_committed']} "
          f"batch(es) ({res['elapsed_seconds']}s)")
    # Printed BEFORE the census, because this is the line an operator needs if
    # the census below reads wrong.
    seal = "" if res.get("undo_sealed") else (
        "  (SEAL FAILED — the ids are durable, the terminal flag is not)"
    )
    print(f"UNDO    {res['undo_rows']} row(s) receipted at "
          f"{res['undo_identity']}{seal}")
    print(f"RESTORE {res['restore_command']}")
    if res.get("reason_codes"):
        print(f"⚠️  {res.get('reason')}")
    print(f"AFTER   blank={a['blank']}  nulls={a['nulls']}  real={a['real']}  "
          f"total={a['total']}")
    if not res["census_consistent"]:
        print("⚠️  CENSUS INCONSISTENT — blank/nulls did not move by exactly "
              "rows_nulled, or real/total changed. Investigate before re-running.")
    elif res["terminal"] == "complete":
        print("✅ every blank statpal_fixture_id is now NULL.")
    else:
        print(f"⏸  stopped early — re-run with "
              f"--expected-blank {res['resume_with_expected_blank']}")


if __name__ == "__main__":
    _expected = EXPECTED_BLANK_COUNT
    _restore_identity = None
    for i, a in enumerate(sys.argv):
        if a == "--expected-blank" and i + 1 < len(sys.argv):
            _expected = int(sys.argv[i + 1])
        if a == "--restore" and i + 1 < len(sys.argv):
            _restore_identity = sys.argv[i + 1]
    if _restore_identity:
        # Same shape as the repair: naming the identity shows you what would
        # happen, and only `--apply` writes.
        asyncio.run(run_restore(_restore_identity, "--apply" in sys.argv))
    else:
        asyncio.run(run("--apply" in sys.argv, _expected))
