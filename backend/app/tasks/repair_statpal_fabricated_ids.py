"""#2963 — clear the 48 ``events.statpal_fixture_id`` values we INVENTED.

    POST /api/admin/repairs/statpal-fabricated-ids                         # derive
    POST /api/admin/repairs/statpal-fabricated-ids?apply=true&plan_hash=…  # commit
    POST /api/admin/repairs/statpal-fabricated-ids?apply=true&undo_identity=…  # undo

THE DEFECT. ``sync_statpal_live_scores`` used to fall back to
``f"statpal_live_{home}_{away}"`` when StatPal's live payload carried no
``contestid``, and that string was written into ``events.statpal_fixture_id`` —
a column whose whole job is to hold *StatPal's* id for the fixture. The producer
is closed (CERT-2081, live at ``1ff13c40``; the counters read 0). **The rows it
already wrote are still there**, and this rail is what removes them.

Measured on production 2026-09-06 15:35Z, and every number here is a reading:

* **48 rows**, 48 DISTINCT values, all ``americanfootball_nfl``, games
  2026-08-13 → 2026-08-29, 47 ``completed`` + 1 ``closed``. None is live.
* The 48 are exactly the rows the column-shape predicate finds: grouping every
  non-blank non-digit ``statpal_fixture_id`` over production returns **one**
  bucket, the ``statpal_live_`` prefix, and nothing else. So the *shape* rule and
  the *prefix* rule do not disagree today — but this rail uses the shape rule,
  because that is the rule the thing it serves already uses (below).

WHAT IT UNBLOCKS, WHICH IS THE ONLY REASON IT RUNS. ``stamp_nfl_statpal_fixtures``
classifies one of our rows ``POLLUTED`` when the column holds a value that is not
a StatPal id, and **refuses to write**: ``SET_FIXTURE_ID`` is guarded
``AND statpal_fixture_id IS NULL``. So each of these 48 rows is a game whose real
StatPal id we already know — the ``polluted_column`` receipts carry it — sitting
unstamped behind a string we made up. Clearing the column is what lets the
stamper put the real id in. The falsifiable prediction, banked before the apply:
NFL ``anchors.polluted_column`` **48 → 0**, ``anchored`` **247 → ~295**,
``pct_of_both`` **76.95 → 91.90** — not "~100", which is what this docstring said
until the arithmetic was checked: 295 of the 321 games both sides list is 91.9%,
because 26 of them have never had a StatPal id to stamp at all.

**SCORED (2026-09-06 16:22Z apply, read back at 16:37Z).** ``polluted_column``
**0** as predicted; ``anchored`` **293**, ``pct_of_both`` **91.28** — two rows
short, and the two are the finding. Events ``15196980`` and ``15196982`` carry a
midnight kickoff a full day before the real one, so they miss the stamper's
one-hour ``MATCH_WINDOW`` by 24 and 25 hours. Filed as **#3601**
(``matching-symptom``, linked #2693), owned by the matching lane. The NFL
agreement row had been reporting ``schedule.wrong_day = 2`` for days and this
lane had written that it gated nothing; it gates exactly these two.

ONE PREDICATE, NOT TWO. The population is ``not is_statpal_contest_id(value)``,
**imported** from ``stamp_nfl_statpal_fixtures`` rather than restated as a SQL
regex. A regex here would be a second copy of a rule that already exists, free to
drift from it — and the day it drifted, this rail would clear rows the classifier
still calls linked, or leave rows it calls polluted. The SQL selects candidates
(non-NULL, non-blank: 3,277 rows today, index-served) and Python decides. That
also means the write can never outrun the classifier: every value this rail
clears is a value the stamper is refusing to write over.

WHY A SIBLING OF ``statpal-blank-ids`` AND NOT A PARAMETER ON IT. That rail's
restore writes back a single CONSTANT — ``SET statpal_fixture_id = ''`` — because
every row it backed up held the same value. **These 48 rows each hold a DIFFERENT
string**, so the undo payload must carry ``(event_id, prior_value)`` pairs and the
restore must write per row. That is a different undo SCHEMA, not a different
predicate, which is why parameterising the blanks rail is the wrong shape.

A CONTENT ADDRESS, NOT A COUNT. The blanks rail gates its apply on an exact
population COUNT, which is right when every row in the population is
interchangeable. Here they are not: a cardinality gate cannot tell "the 48 rows
you reviewed" from "48 different rows". So the apply is bound to a ``plan_hash``
over the ``(event_id, fabricated_id)`` pairs themselves — the shape
``authority-id-collisions`` uses, for the same reason.

WHY THE WRITE IS SAFE, verified in the tree rather than assumed:

* **It cannot delete a row, and that is enforced rather than observed.**
  ``prune_unanchored_duplicates.ANCHOR_COLUMNS`` is ``("external_id", "espn_id",
  "statpal_fixture_id")`` and ``_anchor_predicate`` requires **all three** NULL.
  All 48 rows carry an ``espn_id`` today (measured) — but a measurement is a
  reading of the past, so the write itself carries ``AND (espn_id IS NOT NULL OR
  external_id IS NOT NULL)`` and a row that has lost its last other anchor since
  the review is refused ``WOULD_ORPHAN_ROW`` instead of cleared.
* **Every consumer already treats these values as absence.** They are not StatPal
  ids, so nothing that dereferences one can succeed; ``_get_statpal_id`` falls
  back to the ``win_probability_sources`` JSONB mirror, which this rail does not
  touch.
* **The compare is IN the write.** ``WHERE id = :event_id AND statpal_fixture_id
  = :fabricated`` — a row something else moved between the review and the run is
  counted ``STATPAL_ID_MOVED`` and never written, so it also never enters the
  receipt.

D51 — THE BACKUP AND THE ONE-COMMAND RESTORE. Alex's D51(b) lets the owning lane
apply a repair unattended *provided* it writes a backup first and ships a
one-command restore. The receipt is the only surviving copy of what these rows
held: once cleared, a repaired row is indistinguishable from the 229,034 that
were always NULL. So the record is written (empty) BEFORE the first write and
CO-COMMITTED with each row, which buys the exact invariant the sibling rails
carry:

    at every instant, the durable record names exactly the rows committed as
    NULL — never more, never fewer

    python3 scripts/restore_statpal_fabricated_ids.py --identity <id> --apply

WHAT THE RESTORE WILL DECLINE TO DO, and it is the *success* case. Between the
apply and a restore, ``stamp_nfl_statpal_fixtures`` will give these rows their
REAL StatPal id — that is the entire point of clearing them. Writing the invented
string back over a real id would be the undo causing the corruption it exists to
reverse, so a row that no longer holds NULL is reported
``STATPAL_ID_REOCCUPIED`` and left alone. A restore that reports 48 of these is
not a broken restore; it is a repair that worked.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from app.tasks.stamp_nfl_statpal_fixtures import is_statpal_contest_id

logger = logging.getLogger(__name__)

ISSUE = "#2963"

#: Durable identity of the reviewed plan. ONE slot, so a stale artifact fails
#: loudly rather than being found lying around and applied.
PLAN_IDENTITY = "repair:statpal_fabricated_ids:apply_plan"
PLAN_SCHEMA = "statpal-fabricated-ids-plan/v1"

#: A plan going stale is a safety feature — it forces a re-read of a population
#: that may have moved. (An UNDO record's max age is the opposite; see below.)
PLAN_MAX_AGE_S = 24 * 3600

REASON_PLAN_REQUIRED = "PLAN_HASH_REQUIRED"
REASON_PLAN_MISSING = "PLAN_MISSING"
REASON_PLAN_MISMATCH = "PLAN_HASH_MISMATCH"
REASON_PLAN_CORRUPT = "PLAN_CORRUPT"
#: "The read failed right now" — a THIRD reading, never folded into MISSING. An
#: operator told the plan is missing stops looking for it, which is the wrong
#: move when it is there and the read fell over.
REASON_PLAN_UNREADABLE = "PLAN_UNREADABLE"

UNDO_IDENTITY_PREFIX = "repair:statpal_fabricated_ids:undo"
UNDO_SCHEMA = "statpal-fabricated-ids-undo/v1"

#: The record's owner token lives under this key and the store refuses a
#: replacement by anyone else (CERT-856 on the sibling rail). One apply, one
#: receipt.
UNDO_OWNER_KEY = "invocation"

#: An undo must outlive the incident that needs it, not the day.
UNDO_MAX_AGE_S = 365 * 86400

REASON_UNDO_UNWRITTEN = "UNDO_NOT_PERSISTED"
REASON_UNDO_MISSING = "UNDO_MISSING"
REASON_UNDO_CORRUPT = "UNDO_CORRUPT"
REASON_UNDO_UNREADABLE = "UNDO_UNREADABLE"
REASON_UNDO_RECEIPT_FAILED = "UNDO_RECEIPT_FAILED"

#: Per-row apply outcomes. Closed set (ruling 054: every row reaches a NAMED
#: verdict). ``CLEARED`` is in the receipt; the other two never are, because
#: this apply did not write those rows.
#:
#: ``WOULD_ORPHAN_ROW`` is the one that is not about concurrency: the row holds
#: no ``espn_id`` and no ``external_id``, so clearing the third anchor column
#: would make it deletable by ``prune_unanchored_duplicates``. Refused per row
#: and named, never folded into ``STATPAL_ID_MOVED`` — one says somebody else
#: moved the value, the other says we declined to write.
APPLY_OUTCOMES = ("CLEARED", "STATPAL_ID_MOVED", "WOULD_ORPHAN_ROW")

#: Per-row restore outcomes. ``STATPAL_ID_REOCCUPIED`` is not a failure — it is
#: the restore declining to overwrite a REAL id the stamper has since written,
#: which is the outcome clearing the column was for.
UNDO_OUTCOMES = ("RESTORED", "STATPAL_ID_REOCCUPIED")

#: Candidates, not the population. Every row whose column holds SOMETHING; which
#: of them is fabricated is decided in Python by the classifier's own predicate.
#: Index-served by ``ix_events_statpal_fixture_id``; 3,277 rows on production.
CANDIDATE_SQL = text(
    """
    SELECT e.id, e.statpal_fixture_id, s.key AS sport,
           e.home_team_name, e.away_team_name, e.commence_time,
           e.status, e.espn_id, e.external_id
      FROM events e
      JOIN sports s ON s.id = e.sport_id
     WHERE e.statpal_fixture_id IS NOT NULL
       AND e.statpal_fixture_id <> ''
     ORDER BY e.id
    """
)

#: ONE census definition, used for both the before- and after- reading, so the
#: proof and the plan can never be computed over different populations. The
#: ``fabricated`` figure is deliberately NOT computed here — SQL cannot ask
#: ``is_statpal_contest_id`` — so this counts the shapes it can count and the
#: fabricated count is carried alongside from the Python pass.
CENSUS_SQL = text(
    """
    SELECT count(*) FILTER (WHERE statpal_fixture_id IS NOT NULL
                              AND statpal_fixture_id <> '')  AS linked,
           count(*) FILTER (WHERE statpal_fixture_id = '')   AS blank,
           count(*) FILTER (WHERE statpal_fixture_id IS NULL) AS nulls,
           count(*)                                           AS total
      FROM events
    """
)

CLEAR_SQL = text(
    # The compare is IN the write. `RETURNING` so a zero-rowcount row is
    # distinguishable from a row that was never attempted.
    #
    # The anchor clause is IN the write too, and it is live rather than read off
    # the plan. `prune_unanchored_duplicates` deletes a row whose external_id,
    # espn_id AND statpal_fixture_id are all NULL, so clearing the third column
    # of a row that holds neither of the others would hand that row to the
    # pruner — this repair would have caused a deletion. No such row exists
    # today (all 48 carry an espn_id, measured), and the plan reports any that
    # appear; this clause is what makes it true at WRITE time rather than at
    # review time, because a row can lose its espn_id in between.
    """
    UPDATE events SET statpal_fixture_id = NULL
     WHERE id = :event_id AND statpal_fixture_id = :fabricated
       AND (espn_id IS NOT NULL OR external_id IS NOT NULL)
 RETURNING id
    """
)

#: Why a clear wrote nothing. Asked ONLY on the zero-rowcount path, so the two
#: refusals are never conflated: a row somebody else moved and a row we declined
#: to strip of its last anchor need different responses from an operator.
CLEAR_MISS_SQL = text(
    """
    SELECT statpal_fixture_id, espn_id, external_id
      FROM events
     WHERE id = :event_id
    """
)

RESTORE_SQL = text(
    # The undo's compare is `IS NULL` rather than the prior value: the only row
    # an undo may touch is one this repair left blank. A row the stamper has
    # since given a REAL StatPal id wears a current truth, and putting an
    # invented string back over it would be the undo causing the corruption it
    # exists to reverse.
    """
    UPDATE events SET statpal_fixture_id = :prior
     WHERE id = :event_id AND statpal_fixture_id IS NULL
 RETURNING id
    """
)


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None


def is_fabricated(value: Any) -> bool:
    """Is this column value one we invented rather than one StatPal gave us?

    The single place this rail decides membership, and it decides it by ASKING
    ``stamp_nfl_statpal_fixtures.is_statpal_contest_id`` — the same function
    whose ``False`` makes the stamper classify a row ``POLLUTED`` and refuse to
    write it. Two copies of that rule could disagree; there is one.

    A NULL or blank column is NOT fabricated. It is absence, it is already what
    this repair produces, and ``statpal-blank-ids`` owns the blank half.
    """
    if value is None:
        return False
    token = str(value).strip()
    if not token:
        return False
    return not is_statpal_contest_id(token)


def plan_hash_for(rows: list[dict[str, Any]]) -> str:
    """Content address of the work list, and of nothing else.

    Over the ``(event_id, fabricated_id)`` PAIRS — not the census, not the
    clock, not the matchup labels. Two derives that select the same work must
    produce the same hash, or a reviewer who re-ran the dry run to look again
    would be handed a hash that refuses the plan they already read.

    The VALUE is in the hash, not just the id, and that is the difference
    between this gate and a count: a row whose fabricated string changed under
    the review is a different row to write, and the hash has to say so.
    """
    canonical = json.dumps(
        [
            {
                "event_id": int(r["event_id"]),
                "fabricated_id": str(r["fabricated_id"]),
            }
            for r in rows
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def new_undo_invocation() -> str:
    """A fresh token for ONE apply. Never derived from the work it is about.

    CERT-856 on the sibling rail: the clock and the plan hash are the two things
    a concurrent apply has an identical copy of, so an identity built from them
    alone is the SAME identity in both runs, and the second run's empty receipt
    silently replaced the first's real one. The token is the one thing two
    concurrent runs cannot agree on, and it is both the identity's salt and the
    record's owner.
    """
    return uuid.uuid4().hex[:12]


def undo_identity_for(plan_hash: str, *, at: datetime, invocation: str) -> str:
    """One identity per INVOCATION, carrying the stamp, the plan and the token.

    ``invocation`` is required rather than defaulted because the record's owner
    must be that same token; a default would let a caller build an identity
    nobody owns, which is an identity the store cannot protect.
    """
    at_utc = at.astimezone(timezone.utc)
    stamp = f"{at_utc.strftime('%Y%m%dT%H%M%S')}.{at_utc.microsecond // 1000:03d}Z"
    return f"{UNDO_IDENTITY_PREFIX}:{stamp}:{str(plan_hash)[:12]}:{invocation}"


def restore_command(identity: str) -> str:
    """The one command D51 requires, with this run's own identity baked in."""
    return (
        "python3 scripts/restore_statpal_fabricated_ids.py "
        f"--identity {identity} --apply"
    )


def undo_row_for(plan_row: dict[str, Any]) -> dict[str, Any]:
    """One plan row -> the shape the undo record and the restore both read.

    ``prior_statpal_fixture_id`` is the whole reason this rail exists separately
    from ``statpal-blank-ids``: it is PER ROW. The blanks rail states its prior
    value once for 8,272 rows because they all held ``''``; here all 48 differ,
    so the record carries 48 of them and the restore writes each one back to its
    own id.
    """
    return {
        "event_id": int(plan_row["event_id"]),
        "prior_statpal_fixture_id": str(plan_row["fabricated_id"]),
        "sport": plan_row.get("sport"),
        "matchup": plan_row.get("matchup"),
    }


def undo_payload(
    *,
    plan_hash: str,
    taken_at: datetime,
    planned: list[dict[str, Any]],
    receipted: list[dict[str, Any]],
    complete: bool,
    invocation: str,
) -> dict[str, Any]:
    """The record a restore reads. ``rows`` is the RECEIPT; ``rows_planned`` is intent."""
    return {
        "issue": ISSUE,
        "repair": "statpal-fabricated-ids",
        "plan_hash": str(plan_hash),
        "taken_at": taken_at.isoformat(),
        # WHOSE record this is. The durable store reads this key and refuses a
        # replacement from anyone else, so it is not a label — it is what keeps
        # a concurrent apply from erasing this receipt.
        UNDO_OWNER_KEY: invocation,
        # THE RECEIPT — rows whose clear returned an id AND committed. A planned
        # row that turned out STATPAL_ID_MOVED is not here, and that absence is
        # the point: an undo may only put back a value it can prove this apply
        # took away.
        "rows": list(receipted),
        # The intent, kept for forensics and never replayed (CERT-846: replaying
        # the PLAN put a value back onto a row the apply never wrote).
        "rows_planned": list(planned),
        "receipt_complete": bool(complete),
        "restore_command": restore_command(
            undo_identity_for(str(plan_hash), at=taken_at, invocation=invocation)
        ),
        "restore_note": (
            "Writes each row's own prior string back, and ONLY where the row "
            "still holds NULL. A row the stamper has since given a real StatPal "
            "id is refused and reported STATPAL_ID_REOCCUPIED — undoing this "
            "repair must not destroy the linkage the repair itself made reachable."
        ),
    }


def _plan_envelope(payload: dict[str, Any]):
    from app.utils.durable_state import DurableEnvelope

    return DurableEnvelope.build(
        identity=PLAN_IDENTITY,
        schema_version=PLAN_SCHEMA,
        payload=payload,
        complete=True,
        source="repair:statpal-fabricated-ids",
    )


def _undo_envelope(identity: str, payload: dict[str, Any]):
    from app.utils.durable_state import DurableEnvelope

    return DurableEnvelope.build(
        identity=identity,
        schema_version=UNDO_SCHEMA,
        payload=payload,
        # ALWAYS True, and the distinction is the whole point: the envelope's
        # ``complete`` is a property of the ARTIFACT ("this record was fully
        # written and may be trusted"), while ``payload["receipt_complete"]`` is
        # a property of the RUN ("every row was reached"). CERT-1979 blocked the
        # sibling rail for conflating them: ``decode_envelope`` types any
        # ``complete=False`` envelope as MALFORMED, so a stopped run's receipt
        # became unreadable — the reversal was unreachable for exactly the runs
        # most likely to need it.
        complete=True,
        source="repair:statpal-fabricated-ids:undo",
    )


def _undo_owner(payload: dict[str, Any]) -> Optional[str]:
    """The invocation token this record belongs to, or ``None``.

    ``None`` is never written. A record with no owner is one the store cannot
    protect, so building one is a bug, not a degraded mode.
    """
    owner = payload.get(UNDO_OWNER_KEY)
    return str(owner) if owner else None


def _classify_undo_write(identity: str, status: Optional[str]) -> tuple[bool, str]:
    """One reading of a durable stage dict, shared by both write paths.

    ``superseded`` and ``occupied`` are FAILURES here. For a snapshot whose
    identity names a THING, a newer copy winning is correct; for a receipt whose
    identity names an EVENT, it means the record on file is not this apply's,
    and accepting it hands an operator a restore that puts back the wrong rows.
    """
    if status == "ok":
        return True, "ok"
    if status == "occupied":
        return False, (
            f"undo persist OCCUPIED: {identity} already holds a record written "
            f"by a DIFFERENT invocation and was left untouched; that record is "
            f"somebody else's receipt and this apply has none"
        )
    if status == "superseded":
        return False, (
            f"undo persist SUPERSEDED: {identity} already holds a newer row, so "
            f"the record on file is not this apply's"
        )
    return False, f"undo persist rejected: {status}"


async def _save_plan(payload: dict[str, Any]) -> tuple[bool, str]:
    """Persist to the durable snapshot rail — not Redis.

    A SETEX on an allkeys-lru instance can be evicted, and an operator who
    cannot be handed a hash must be TOLD so, because the next thing they will do
    is try to apply.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone

    try:
        result = await publish_snapshot_standalone(_plan_envelope(payload))
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        logger.warning("%s plan persist raised: %s", ISSUE, type(exc).__name__)
        return False, f"persist raised: {type(exc).__name__}"
    ok = result.get("status") in ("ok", "superseded")
    return ok, "ok" if ok else f"persist rejected: {result.get('status')}"


async def _read_plan() -> tuple[Optional[dict[str, Any]], str]:
    """``(payload, reason)`` — a raise is "I could not read", never "not there"."""
    from app.services.durable_snapshots import read_snapshot_standalone

    read = read_snapshot_standalone(
        PLAN_IDENTITY, expected_version=PLAN_SCHEMA, max_age_s=PLAN_MAX_AGE_S
    )
    try:
        got = await read
    except Exception as exc:  # noqa: BLE001 — a raise is UNREADABLE, not MISSING
        logger.warning("%s plan read raised: %s", ISSUE, type(exc).__name__)
        return None, REASON_PLAN_UNREADABLE
    if not got.ok or got.envelope is None:
        return None, REASON_PLAN_MISSING
    payload = got.envelope.payload
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        return None, REASON_PLAN_CORRUPT
    return payload, "ok"


async def _save_undo(identity: str, payload: dict[str, Any]) -> tuple[bool, str]:
    """Persist one apply's undo record on its own connection.

    Used at the two moments with no data write pending — the empty record before
    the first clear, and the seal after the last.
    """
    from app.services.durable_snapshots import (
        publish_owned_snapshot_standalone as _publish,
    )

    owner = _undo_owner(payload)
    if owner is None:
        return False, (
            f"undo persist REFUSED: the record for {identity} carries no "
            f"{UNDO_OWNER_KEY}, so the store could not protect it from a "
            f"concurrent apply"
        )
    # Envelope built outside the `try` so the awaited call is the only thing
    # inside it — same reason as `_read_undo` below.
    envelope = _undo_envelope(identity, payload)
    try:
        result = await _publish(envelope, owner_key=UNDO_OWNER_KEY, owner=owner)
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        logger.warning("%s undo persist raised: %s", ISSUE, type(exc).__name__)
        return False, f"undo persist raised: {type(exc).__name__}"
    return _classify_undo_write(identity, result.get("status"))


async def _save_undo_co_commit(
    session, identity: str, payload: dict[str, Any]
) -> tuple[bool, str]:
    """Stage the receipt in the caller's OPEN transaction and commit both.

    ``_save_undo`` writes on its own connection, so it can only run before or
    after the data write, and either order is a lie waiting for a crash: before,
    the record claims rows that may roll back; after, a durable clear may have no
    record. Staging the receipt beside the write and committing once removes the
    window rather than choosing which side of it to fall on (CERT-851).

    Anything short of ``ok`` rolls the transaction back, which takes the data
    write with it — nothing written and nothing claimed is the only state that
    needs no reconciliation.
    """
    from app.services.durable_snapshots import publish_owned_snapshot_in_txn

    owner = _undo_owner(payload)
    if owner is None:
        await session.rollback()
        return False, (
            f"undo persist REFUSED: the record for {identity} carries no "
            f"{UNDO_OWNER_KEY}; write rolled back"
        )
    try:
        stage = await publish_owned_snapshot_in_txn(
            session,
            _undo_envelope(identity, payload),
            owner_key=UNDO_OWNER_KEY,
            owner=owner,
        )
        status = stage.get("status")
        if status != "ok":
            await session.rollback()
            ok, note = _classify_undo_write(identity, status)
            return ok, f"{note}; write rolled back"
        await session.commit()
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        logger.warning("%s undo co-commit raised: %s", ISSUE, type(exc).__name__)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001 — rollback failure must not mask the cause
            pass
        return False, f"undo co-commit raised: {type(exc).__name__}"
    return True, "ok"


async def _read_undo(identity: str) -> tuple[Optional[dict[str, Any]], str]:
    """``(payload, reason)`` — a raise is "I could not read", never "not there"."""
    from app.services.durable_snapshots import read_snapshot_standalone

    read = read_snapshot_standalone(
        identity, expected_version=UNDO_SCHEMA, max_age_s=UNDO_MAX_AGE_S
    )
    try:
        got = await read
    except Exception as exc:  # noqa: BLE001 — a raise is UNREADABLE, not MISSING
        logger.warning("%s undo read raised: %s", ISSUE, type(exc).__name__)
        return None, REASON_UNDO_UNREADABLE
    if not got.ok or got.envelope is None:
        return None, REASON_UNDO_MISSING
    payload = got.envelope.payload
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        return None, REASON_UNDO_CORRUPT
    return payload, "ok"


async def _census(session) -> dict[str, int]:
    row = (await session.execute(CENSUS_SQL)).first()
    return {
        "linked": int(row.linked),
        "blank": int(row.blank),
        "nulls": int(row.nulls),
        "total": int(row.total),
    }


def plan_rows_from_candidates(candidates: list[Any]) -> list[dict[str, Any]]:
    """Candidate rows -> the plan, keeping only the fabricated ones. Pure.

    Separated from the query so the membership contract is testable without a
    database, and so the ONE call to :func:`is_fabricated` is in one place.
    """
    rows: list[dict[str, Any]] = []
    for c in candidates:
        value = c.statpal_fixture_id
        if not is_fabricated(value):
            continue
        rows.append({
            "event_id": int(c.id),
            "fabricated_id": str(value),
            "sport": c.sport,
            "matchup": f"{c.home_team_name} v {c.away_team_name}",
            "commence_time": _iso(c.commence_time),
            "status": c.status,
            # Recorded so a reader can see for themselves that clearing this
            # column cannot make the row anchor-free: `prune_unanchored_
            # duplicates` needs external_id, espn_id AND statpal_fixture_id all
            # NULL, and these two are printed for every row in the plan.
            "espn_id": c.espn_id,
            "external_id": c.external_id,
        })
    return rows


async def _derive(session, limit: Optional[int] = None) -> dict[str, Any]:
    before = await _census(session)
    candidates = (await session.execute(CANDIDATE_SQL)).all()
    rows = plan_rows_from_candidates(candidates)
    truncated = False
    if limit is not None and len(rows) > limit:
        rows = rows[:limit]
        truncated = True

    by_sport: dict[str, int] = {}
    anchor_free_after: list[int] = []
    for r in rows:
        by_sport[str(r["sport"])] = by_sport.get(str(r["sport"]), 0) + 1
        if not r["espn_id"] and not r["external_id"]:
            # Would hold all three anchor columns NULL after the clear. None
            # exist today. This list is the REVIEW-time reading; the write's own
            # anchor clause is what actually refuses such a row, so a row that
            # loses its espn_id after this plan is read is still refused
            # (reported WOULD_ORPHAN_ROW by the apply) rather than cleared.
            anchor_free_after.append(r["event_id"])

    digest = plan_hash_for(rows)
    saved, note = await _save_plan({
        "issue": ISSUE,
        "plan_hash": digest,
        "rows": rows,
        "before": before,
        "candidates_scanned": len(candidates),
    })

    return {
        "issue": ISSUE,
        "apply": False,
        "plan_hash": digest if saved else None,
        "plan_persisted": saved,
        "plan_note": note,
        "before": before,
        "candidates_scanned": len(candidates),
        "rows_planned": len(rows),
        "rows_truncated": truncated,
        "by_sport": dict(sorted(by_sport.items())),
        # Named rather than summed away. A row here would lose its last anchor
        # to this write and become eligible for the duplicate pruner; the apply
        # refuses the whole plan rather than clearing it.
        "would_become_anchor_free": anchor_free_after,
        "rows": rows,
        "note": (
            "Nothing was written. Re-run with ?apply=true&plan_hash=<plan_hash> "
            f"to clear exactly these {len(rows)} row(s). Membership is decided by "
            "stamp_nfl_statpal_fixtures.is_statpal_contest_id — the same predicate "
            "that makes the stamper call a row POLLUTED and refuse to write it — "
            "so every value listed here is one the stamper is currently refusing "
            "to overwrite with the real StatPal id."
        ),
    }


async def _apply(session, plan_hash: Optional[str]) -> dict[str, Any]:
    if not plan_hash:
        return {
            "issue": ISSUE, "apply": True, "refused": True,
            "reason_codes": [REASON_PLAN_REQUIRED],
            "note": (
                "An apply is bound to the plan a human read. Run ?apply=false "
                "first and present the plan_hash it returns."
            ),
        }

    stored, reason = await _read_plan()
    if stored is None:
        return {
            "issue": ISSUE, "apply": True, "refused": True,
            "reason_codes": [reason],
            "note": (
                "MISSING means no plan is persisted (or it aged out); UNREADABLE "
                "means the read failed right now; CORRUPT means one is there and "
                "cannot be trusted — do not re-derive to route around it, read it."
            ),
        }
    if str(stored.get("plan_hash")) != str(plan_hash):
        return {
            "issue": ISSUE, "apply": True, "refused": True,
            "reason_codes": [REASON_PLAN_MISMATCH],
            "presented": plan_hash,
            "stored": stored.get("plan_hash"),
            "note": "The persisted plan is not the one presented. Re-derive and re-read.",
        }

    before = await _census(session)

    # ── BACKUP BEFORE WRITE (D51) ────────────────────────────────────────────
    # Not one row is cleared until this apply's own dated undo record is on
    # disk. The order is the whole point: a backup written afterwards is a
    # backup that does not exist for exactly the run that crashed halfway. And
    # here it is the ONLY copy — a cleared row is indistinguishable from the
    # 229,034 that were always NULL, so the population cannot be re-derived from
    # the table at any price once the write lands.
    undo_at = datetime.now(timezone.utc)
    undo_invocation = new_undo_invocation()
    undo_identity = undo_identity_for(
        str(plan_hash), at=undo_at, invocation=undo_invocation
    )
    planned_rows = [undo_row_for(r) for r in stored["rows"]]

    def _record(receipted: list[dict[str, Any]], *, complete: bool) -> dict[str, Any]:
        return undo_payload(
            plan_hash=str(plan_hash),
            taken_at=undo_at,
            planned=planned_rows,
            receipted=receipted,
            complete=complete,
            invocation=undo_invocation,
        )

    # The record exists before the first write with an EMPTY receipt: at this
    # instant the true answer to "what has this apply cleared" is "nothing", and
    # a backup that claims otherwise is CERT-846's defect.
    undo_saved, undo_note = await _save_undo(undo_identity, _record([], complete=False))
    if not undo_saved:
        return {
            "issue": ISSUE, "apply": True, "refused": True,
            "reason_codes": [REASON_UNDO_UNWRITTEN],
            "undo_identity": undo_identity,
            "undo_note": undo_note,
            "rows_in_plan": len(stored["rows"]),
            "cleared": 0,
            "note": (
                "NOTHING WAS WRITTEN. The undo record for this apply could not be "
                "persisted, and a clear that cannot be taken back is not a repair "
                "this rail performs unattended (D51). These values exist nowhere "
                "else once cleared. Fix the durable snapshot write and re-present "
                "the same plan_hash."
            ),
        }

    cleared: list[int] = []
    receipted: list[dict[str, Any]] = []
    moved: list[dict[str, Any]] = []
    refused_rows: list[dict[str, Any]] = []
    receipt_failure: Optional[str] = None

    for row, undo_row in zip(stored["rows"], planned_rows):
        event_id = int(row["event_id"])
        fabricated = str(row["fabricated_id"])
        result = (await session.execute(
            CLEAR_SQL, {"event_id": event_id, "fabricated": fabricated}
        )).first()
        if result is None:
            # NOT a silent success, and NOT a row the undo may speak for. Ask
            # the row WHY before naming the verdict — two different conditions
            # produce the same zero rowcount, and only one of them is about
            # concurrency.
            miss = (await session.execute(
                CLEAR_MISS_SQL, {"event_id": event_id}
            )).first()
            if (
                miss is not None
                and str(miss.statpal_fixture_id or "") == fabricated
                and miss.espn_id is None
                and miss.external_id is None
            ):
                # The value is still the reviewed one; the anchor clause is what
                # refused. Clearing it would leave all three anchor columns NULL
                # and hand the row to `prune_unanchored_duplicates`.
                refused_rows.append({
                    "event_id": event_id,
                    "statpal_fixture_id": fabricated,
                    "reason_code": "WOULD_ORPHAN_ROW",
                })
                logger.warning(
                    "%s REFUSED to clear event %s: it holds no espn_id and no "
                    "external_id, so clearing statpal_fixture_id would make it "
                    "deletable by the duplicate pruner",
                    ISSUE, event_id,
                )
                continue
            # The column no longer holds the value that was reviewed: the
            # stamper got there first, or a sibling apply already cleared it.
            # Either way this apply did not write it, so it never enters the
            # receipt.
            moved.append({
                "event_id": event_id,
                "expected_statpal_fixture_id": fabricated,
                "observed_statpal_fixture_id": (
                    miss.statpal_fixture_id if miss is not None else None
                ),
                "reason_code": "STATPAL_ID_MOVED",
            })
            continue
        # Said out loud before the commit, so the row is traceable from the log
        # even if the process dies between the UPDATE and the commit — and the
        # prior value is IN the line, because it exists nowhere else.
        logger.info(
            "%s clearing event %s (prior statpal_fixture_id %r) under undo %s",
            ISSUE, event_id, fabricated, undo_identity,
        )
        # CO-COMMIT, per row (CERT-851). `events` is hot, so this is one commit
        # per row, the same posture Phase 2 matching takes (gotcha #13).
        candidate = receipted + [undo_row]
        ok, note = await _save_undo_co_commit(
            session, undo_identity, _record(candidate, complete=False)
        )
        if not ok:
            # The rollback inside the helper took this row's UPDATE with it, so
            # nothing was cleared and there is nothing to reconcile — the apply
            # simply stops short of the rows it has not reached.
            receipt_failure = note
            logger.warning(
                "%s receipt write failed at event %s after %s row(s); that clear "
                "was rolled back and the apply stops: %s",
                ISSUE, event_id, len(receipted), note,
            )
            break
        cleared.append(event_id)
        receipted = candidate

    # Seals the record: a reader can now tell a finished apply from one that
    # stopped part-way. A failure here costs the SEAL and nothing else — every
    # row cleared was co-committed with the receipt naming it, so an unsealed
    # record is still a complete and exact list of what landed.
    sealed, seal_note = await _save_undo(
        undo_identity, _record(receipted, complete=receipt_failure is None)
    )

    after = await _census(session)
    return {
        "issue": ISSUE,
        "apply": True,
        "plan_hash": plan_hash,
        "before": before,
        "after": after,
        "rows_in_plan": len(stored["rows"]),
        "cleared": len(cleared),
        "moved": moved,
        # Empty on every run this rail expects to make. A non-empty list is the
        # anchor guard firing, and it is a finding: something stripped that row's
        # espn_id between the review and the write.
        "refused": refused_rows,
        # The number to compare against `cleared`, and the reason this rail can
        # call itself reversible. Since the receipt is co-committed they cannot
        # disagree — a row enters both lists in one transaction or neither — but
        # both are printed, because the day they DO disagree is the day the
        # invariant broke and an operator needs to see it rather than be handed
        # one reassuring number.
        "rows_receipted": len(receipted),
        "receipt_complete": receipt_failure is None and sealed,
        **(
            {"reason_codes": [REASON_UNDO_RECEIPT_FAILED], "receipt_note": receipt_failure}
            if receipt_failure
            else {}
        ),
        **({"seal_note": seal_note} if not sealed else {}),
        "undo_identity": undo_identity,
        "undo_command": restore_command(undo_identity),
        "note": (
            f"linked {before['linked']} -> {after['linked']}; NULL "
            f"{before['nulls']} -> {after['nulls']}. Reversible: the "
            f"{len(receipted)} row(s) this apply actually cleared are receipted "
            f"in its OWN dated record {undo_identity}, with each row's own prior "
            f"string — one identity per invocation, and the store refuses a "
            f"replacement from any other invocation. The {len(moved)} "
            f"STATPAL_ID_MOVED row(s) are NOT in it: this apply did not clear "
            f"them, so the restore must not put their values back. Expect "
            f"stamp_nfl_statpal_fixtures to fill these rows with the REAL "
            f"StatPal id on its next pass — that is the ship, and it also means "
            f"a later restore will correctly refuse them."
            + (
                f" {len(refused_rows)} row(s) were REFUSED as WOULD_ORPHAN_ROW: "
                f"they hold no espn_id and no external_id, so clearing this "
                f"column would have made them deletable by the duplicate pruner. "
                f"Nothing was written to them. Give them an anchor first."
                if refused_rows
                else ""
            )
            + (
                f" WARNING: the apply STOPPED after {len(receipted)} row(s) "
                f"because a receipt could not be written ({receipt_failure}). "
                f"The row it failed on was rolled back with its receipt and was "
                f"NOT cleared; the rows named above are still exactly reversible, "
                f"and the rest of the plan was not run."
                if receipt_failure
                else ""
            )
        ),
    }


async def _undo(session, undo_identity: str, apply: bool) -> dict[str, Any]:
    """Put back exactly the strings one apply cleared. Dry-run unless ``apply``.

    It replays the RECEIPT, never the plan (CERT-846): ``rows`` is what the apply
    proved it cleared, ``rows_planned`` is what it set out to do, and the
    difference is read here only to report it.
    """
    stored, reason = await _read_undo(undo_identity)
    if stored is None:
        return {
            "issue": ISSUE, "undo": True, "apply": apply, "refused": True,
            "undo_identity": undo_identity,
            "reason_codes": [reason],
            "note": (
                "MISSING means no undo record is stored under that identity; "
                "UNREADABLE means the read failed right now; CORRUPT means one is "
                "there and cannot be trusted. Do not re-derive to route around it "
                "— these values exist nowhere else."
            ),
        }

    rows = stored["rows"]
    planned = stored.get("rows_planned")
    n_planned = len(planned) if isinstance(planned, list) else None
    not_cleared = (n_planned - len(rows)) if n_planned is not None else None
    incomplete = stored.get("receipt_complete") is False
    scope = (
        f"This record receipts {len(rows)} row(s) actually cleared"
        + (f" of {n_planned} planned" if n_planned is not None else "")
        + ". Only receipted rows are ever restored."
        + (
            f" {not_cleared} planned row(s) were not cleared by that apply "
            f"(STATPAL_ID_MOVED) and their values are deliberately NOT put back."
            if not_cleared
            else ""
        )
        + (
            " The record is NOT sealed: that apply stopped part-way, so it may "
            "have cleared one further row than it receipted — check the logs for "
            "the identity before assuming the table is fully reversed."
            if incomplete
            else ""
        )
    )
    before = await _census(session)
    if not apply:
        return {
            "issue": ISSUE, "undo": True, "apply": False,
            "undo_identity": undo_identity,
            "plan_hash": stored.get("plan_hash"),
            "taken_at": stored.get("taken_at"),
            "before": before,
            "rows_in_record": len(rows),
            "rows_planned_in_record": n_planned,
            "receipt_complete": stored.get("receipt_complete"),
            "rows": rows,
            "note": (
                f"Nothing was written. Re-run with apply=true to put these "
                f"{len(rows)} value(s) back. A row the stamper has since given a "
                f"REAL StatPal id is reported STATPAL_ID_REOCCUPIED and left "
                f"alone. " + scope
            ),
        }

    restored: list[int] = []
    reoccupied: list[dict[str, Any]] = []
    for row in rows:
        event_id = int(row["event_id"])
        prior = str(row["prior_statpal_fixture_id"])
        result = (await session.execute(
            RESTORE_SQL, {"event_id": event_id, "prior": prior}
        )).first()
        if result is None:
            reoccupied.append({
                "event_id": event_id,
                "prior_statpal_fixture_id": prior,
                "reason_code": "STATPAL_ID_REOCCUPIED",
            })
            continue
        restored.append(event_id)
        # Same per-row commit posture as the apply — `events` is hot.
        await session.commit()

    after = await _census(session)
    return {
        "issue": ISSUE, "undo": True, "apply": True,
        "undo_identity": undo_identity,
        "plan_hash": stored.get("plan_hash"),
        "before": before,
        "after": after,
        "rows_in_record": len(rows),
        "rows_planned_in_record": n_planned,
        "receipt_complete": stored.get("receipt_complete"),
        "restored": len(restored),
        "reoccupied": reoccupied,
        "note": (
            f"linked {before['linked']} -> {after['linked']}. Putting these "
            f"strings back RE-CREATES the pollution the apply removed — that is "
            f"what an undo is — so stamp_nfl_statpal_fixtures will go back to "
            f"classifying those rows POLLUTED and refusing to stamp them. Rows "
            f"reported STATPAL_ID_REOCCUPIED already carry a REAL StatPal id and "
            f"were left alone; a restore that reports many of those is a repair "
            f"that worked, not a restore that failed. " + scope
        ),
    }


async def repair(
    session,
    apply: bool = False,
    plan_hash: Optional[str] = None,
    limit: Optional[int] = None,
    undo_identity: Optional[str] = None,
) -> dict[str, Any]:
    """Clear ``events.statpal_fixture_id`` values this codebase invented (#2963).

    Args:
        apply: False (default) derives and persists a plan, writing nothing.
            True consumes one and writes.
        plan_hash: content address of the reviewed dry run. REQUIRED on apply —
            a count gate cannot tell 48 rows from 48 DIFFERENT rows.
        limit: bound the PLAN to N rows, for a staged first apply.
        undo_identity: put one earlier apply's values BACK. Takes precedence
            over every other argument — an undo is never also a derive — and is
            itself dry-run unless ``apply`` is true.
    """
    if undo_identity:
        return await _undo(session, undo_identity, apply)
    if apply:
        return await _apply(session, plan_hash)
    return await _derive(session, limit)
