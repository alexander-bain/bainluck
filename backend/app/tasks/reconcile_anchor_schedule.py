"""Dereference each anchor BY ID and reconcile the kickoff it names. #2693/#2697.

WHO DECIDES is not in this file.  ``app/utils/anchor_schedule`` holds the whole
rule and the argument for it; this module is the plumbing — which rows to ask
about, how to ask ESPN, and how to write the answer down.  The read-only
``scripts/audit_anchor_schedule.py`` runs the identical module against
production, so a dry run and this rail cannot drift.

═══ WHY THIS RAIL EXISTS AT ALL — THE BLIND SPOT ═══

Every other ESPN pass is driven by **today's scoreboard**: it fetches the slate
for the current date and visits the rows whose anchor (or teams) appear on it.
A row anchored to a game three months out appears on no slate we fetch, so it
is visited by nothing.  ``sync_scheduled_events`` already carries the right
suspicion for this class — it refuses a start-time correction that is beyond
the same-game window and logs *"the espn_id on this row points at a different
game (#1947)"* — and that refusal is unreachable for exactly the rows that need
it most.

So this rail inverts the direction of the question.  Instead of "who on today's
board matches this row?", it asks "**what game is this row's anchor?**", one
``summary?event=<id>`` call per row.  That is the only way the December anchor
on a September row is ever seen.

═══ WHAT IT WRITES, AND THE THREE THINGS IT WILL NOT ═══

One column, plus its provenance: ``commence_time`` and
``commence_time_source``.  Not the status, not the scores, not
``completed_at``, and it never deletes or merges a row (ruling 079) — a start
time that disagrees with the authority is a start-time defect, and a rail that
starts fixing adjacent things is how a repair becomes an incident.

It also will not write when the teams disagree with the anchor.  That is a
different defect (the anchor is wrong, not the clock) and it belongs to
``authority-id-collisions``; the verdict is reported so the two rails can be
read together.

THE APPLY IS ATTENDED; THE REPORT IS NOT (#2853).  ``apply`` defaults to False
and a write still needs a person: the population it moves is small, the moves
are large (98 days in the charter case), and a reviewer should see the plan.

But that argument is about *writing*, and until #2853 it was being used to keep
the rail from *looking*.  A rail that only runs when asked catches a December
anchor on a September row exactly when somebody thinks to ask — which, for
#2804, was days after a fan could already see the wrong kickoff.  So the
read-only half now runs nightly (``app.tasks.anchor_schedule_sentinel``), pages
the window under a budget, and files what it finds; the plan it produces is
still the reviewer's to apply.

═══ IT IS REVERSIBLE, AND THAT IS WHAT MAKES IT UNATTENDED-ELIGIBLE ═══

D51: a data repair may be applied without Alex watching *provided* it backs up
first and ships a one-command restore.  Until 2026-09-03 this rail had neither,
which is why the two known Week-1 NFL moves sat unapplied while the fixtures
they would fix were on the site.  Now every apply writes its own dated record
before it moves a single row (:data:`UNDO_IDENTITY_PREFIX`), refuses outright if
that record cannot be persisted, and prints a filled-in restore line:

    python3 scripts/restore_anchor_schedule_moves.py --identity <id> --apply

**The record receipts what was MOVED, not what was planned** — the lesson
CERT-846 taught the sibling drain one file over.  A planned move whose row
changed under us is reported ``stale``, writes nothing, and must not appear in
anything a restore replays.

**The restore's compare is in its write, and here it can be exact.**  The drain
next door writes ``NULL``, a value every writer produces identically, so its
undo can only ask "is this row still blank?".  This rail writes a *specific*
timestamp, so its restore asks the far stronger question — "does this row still
wear the clock WE wrote?" — and a row that anything else has touched since is
reported ``CLOCK_MOVED_ON`` and left alone.

ATTENDED ONLY for its plan; the apply itself is now D51-eligible.  Nothing
above changes what #2853 wired: the nightly beat runs the READ, never the write.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time as _time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select, update

from app.utils.anchor_schedule import (
    AUTHORITY_MOVES_US,
    AnchoredRow,
    SCHEDULE_VERDICTS,
    schedule_decision,
    summarize_decisions,
)
from app.utils.espn_tennis_anchor import SETTLED_STATUSES

logger = logging.getLogger(__name__)

#: Rows are read forward from a little before now. A row whose own start is in
#: the past and which never settled is a different defect (#2772, the stale
#: ghost) and moving its clock would not make it a game again; a day of slack
#: keeps a fixture that started an hour ago inside the window without opening
#: the rail onto history.
DEFAULT_LOOKBACK = timedelta(days=1)

#: How far ahead to look. A season, not a slate — the whole point is that the
#: defect hides at horizons no scoreboard pass reaches.
DEFAULT_HORIZON = timedelta(days=120)

#: One ESPN call per row, so the bound is a *wall-clock* bound before it is
#: anything else — and the wall clock that matters is Heroku's 30-second router
#: timeout, because the only caller today is an admin endpoint.
#:
#: Re-measured 2026-09-04 against production (#2953), because the first number
#: here was wrong by 3x and the bound built on it could not be reached: a timed
#: sweep of the NFL window returned 10 rows in 5.66s, 20 in 11.52s and 40 in
#: 23.32s — **~0.59s per** ``summary?event=`` **call**, near-zero fixed cost, not
#: the ~0.2s this comment used to claim. So the old 100 was ~59s of ESPN against
#: a 30-second router: every caller who omitted ``limit`` got a bare Heroku error
#: page with no ``reason`` and no ``correlation_id``, and on ``apply`` it was the
#: worst shape a destructive endpoint can have — killed *after* the writes.
#:
#: 25 is ~15s, which leaves the other half of the router window for the count
#: query, the writes, the undo record and the JSON.
#:
#: THIS NUMBER IS NOT THE SAFETY. It is the ordinary page size; the safety is
#: :data:`EXAMINE_BUDGET_SECONDS`, which stops the loop on the clock no matter
#: what ``limit`` a caller passes. A row count can only ever be a guess at a
#: duration — that guess is exactly what #2953 was.
#:
#: It is SMALLER THAN THE POPULATION and that is the point of ``eligible``:
#: the window held 685 anchored rows that day (239 NFL alone), so even an
#: unfiltered run at any router-safe limit sees a minority of them. Scope with
#: ``sport`` rather than raising this. See :func:`_count_eligible` for why the
#: shortfall is reported rather than left for the reader to notice.
DEFAULT_LIMIT = 25

#: The bound that actually holds, and the reason ``limit`` no longer has to.
#:
#: ``reconcile`` spends its wall clock one ESPN call at a time, so it can check
#: the clock between calls and stop. 18s of fetching leaves ~12s of the 30-second
#: router window for everything that is not fetching. A caller who passes
#: ``limit=500`` now gets a truncated page and a cursor instead of an H12.
#:
#: Stopping early is NOT an error and not a silent shortfall: the rows the
#: deadline cut off were never asked about, so they are dropped from this call's
#: population entirely — ``examined`` counts only rows that got an answer, and
#: ``next_cursor`` points at the last one that did. See ``stopped_by``.
EXAMINE_BUDGET_SECONDS = 18.0

#: What separates the two halves of a cursor. A kickoff renders as ISO-8601,
#: which already contains ``-``, ``:`` and ``+``; ``|`` appears in none of them.
CURSOR_SEPARATOR = "|"

#: Sports whose anchors this rail cannot dereference, so asking costs a call and
#: buys nothing (#2852).
#:
#: Measured 2026-09-03: of 46 in-window US Open rows, a 20-row sample returned
#: ``no_answer`` 20/20. ESPN's tennis anchors are not ``summary?event=`` ids in
#: the shape ``_fetch_record`` dereferences, so every tennis row is a guaranteed
#: miss. Left in, they are not merely wasteful — they are *misreading*: a page
#: that is entirely tennis terminates ``authority_dark``, which is the rail's
#: word for an ESPN outage, and a nightly sentinel that cries outage every night
#: is one nobody reads.
#:
#: This is an exclusion from the POPULATION, not a filter on the report, so
#: ``eligible`` never counts a row the rail would refuse to ask about. Two
#: definitions of "eligible" is how a census comes to disagree with itself.
EXCLUDED_SPORT_KEYS = frozenset({"tennis_atp", "tennis_wta"})

# ═══ THE UNDO RECORD (D51) ═══
#
# One dated identity per apply, never reused and never rotated. The sibling
# drain's `PLAN_IDENTITY` was a single slot and its undo therefore lasted only
# until the next slice was planned; the rule learned there is that a plan going
# stale is a safety feature while an undo going stale is the loss of the only
# proof a repair can be taken back.
UNDO_IDENTITY_PREFIX = "repair:anchor_schedule:undo"
UNDO_SCHEMA = "anchor-schedule-undo/v1"

#: The payload key holding the token of the invocation that owns the record.
#: The durable store will only let that invocation replace it (CERT-856).
UNDO_OWNER_KEY = "invocation"

#: An undo must outlive the incident that needs it, not the day.
UNDO_MAX_AGE_S = 365 * 86400

REASON_UNDO_UNWRITTEN = "UNDO_NOT_PERSISTED"
#: The receipt could not be committed WITH the moves, so the moves were rolled
#: back. Distinct from UNDO_NOT_PERSISTED, which fires before anything is
#: written at all: this one says a batch was attempted and abandoned intact.
REASON_UNDO_UNRECEIPTED = "UNDO_RECEIPT_NOT_COMMITTED"
REASON_UNDO_MISSING = "UNDO_MISSING"
REASON_UNDO_CORRUPT = "UNDO_CORRUPT"
REASON_UNDO_UNREADABLE = "UNDO_UNREADABLE"

#: Per-row restore outcomes. Closed set. ``CLOCK_MOVED_ON`` is not a failure —
#: it is the restore declining to overwrite a clock that is no longer the one
#: this rail wrote, and it is named so a reader can tell "put back 2 of 2" from
#: "put back 1 and left 1 alone".
RESTORE_OUTCOMES = ("REVERTED", "CLOCK_MOVED_ON")


def encode_cursor(commence_time: datetime, event_id: int) -> str:
    """Name the last row a page examined, so the next page can start after it.

    The cursor is **both** sort keys, because ``commence_time`` alone does not
    identify a row: the NFL slate puts twelve fixtures on the same 17:00
    kickoff, and a cursor that carried only the clock would either re-examine
    all twelve or skip the ones it had not reached. That is the same class of
    bug as an OFFSET over a moving population, arrived at from the other side.
    """
    return f"{commence_time.isoformat()}{CURSOR_SEPARATOR}{event_id}"


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    """Read a cursor back, or raise ``ValueError`` naming what was wrong.

    A malformed cursor is refused rather than ignored. Ignoring it would
    silently restart the sweep at the oldest row, and the caller — a script
    looping until ``next_cursor`` is None — would loop over page one forever
    while every page reported a healthy census.
    """
    moment, separator, event_id = str(cursor).rpartition(CURSOR_SEPARATOR)
    if not separator or not moment:
        raise ValueError(
            f"cursor must be '<iso8601>{CURSOR_SEPARATOR}<event_id>', got {cursor!r}"
        )
    try:
        parsed = datetime.fromisoformat(moment)
    except ValueError:
        raise ValueError(f"cursor kickoff {moment!r} is not ISO-8601") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        return parsed, int(event_id)
    except ValueError:
        raise ValueError(f"cursor event id {event_id!r} is not an integer") from None


def _after_cursor(cursor: Optional[str]):
    """The keyset predicate: strictly after ``(commence_time, event_id)``.

    Keyset rather than OFFSET, and the reason is gotcha #41. This window's
    floor is ``now - lookback``, so it MOVES between one page and the next: a
    fixture that has since kicked off drops out from underneath, every later
    row shifts down by one, and an OFFSET would step straight over a row that
    was never examined. A keyset cursor names a position in the ordering rather
    than a count from the start, so rows leaving the floor cannot displace it.

    Written as the expanded ``a > t OR (a = t AND b > i)`` rather than a row
    comparison ``(a, b) > (t, i)``. The two are the same predicate; the expanded
    form is the one the read-only twin can also write into plain SQL, and the
    two rails agreeing is worth more here than the tidier syntax.
    """
    from app.models.models import Event

    if not cursor:
        return ()
    moment, event_id = decode_cursor(cursor)
    return (
        or_(
            Event.commence_time > moment,
            and_(Event.commence_time == moment, Event.id > event_id),
        ),
    )


def _window(
    *,
    lookback: timedelta,
    horizon: timedelta,
    now: Optional[datetime] = None,
):
    """The predicates that define "an anchored row this rail may consider".

    One definition, used by both the count and the fetch. Two copies of a
    population filter is how a census comes to disagree with the thing it is
    counting.
    """
    from app.models.models import Event

    now = now or datetime.now(timezone.utc)
    return (
        Event.espn_id.isnot(None),
        Event.completed_at.is_(None),
        Event.status.notin_(tuple(SETTLED_STATUSES)),
        Event.commence_time >= now - lookback,
        Event.commence_time < now + horizon,
    )


async def _count_eligible(
    session,
    *,
    sport: Optional[str],
    lookback: timedelta,
    horizon: timedelta,
    now: Optional[datetime] = None,
    cursor: Optional[str] = None,
    exclude_sports: frozenset[str] = frozenset(),
) -> int:
    """How many rows the window holds, ignoring ``limit``.

    ``examined`` alone cannot tell a complete pass from a truncated one: a run
    that saw all 34 rows and a run that saw the first 200 of 685 both report a
    number and both look finished. That is gotcha #53 in its second form —
    not an empty answer read as health, but a *partial* one. So the shortfall
    is measured and named, and a truncated run may not terminate ``complete``.

    With ``cursor`` set this counts the rows AT OR AFTER that position, which
    is what ``remaining`` means. Called both ways on every paged run: without
    the cursor it is ``eligible``, the whole window, whose meaning must not
    drift because a caller started paging.
    """
    from app.models.models import Event, Sport

    query = (
        select(func.count())
        .select_from(Event)
        .join(Sport, Sport.id == Event.sport_id)
        .where(*_window(lookback=lookback, horizon=horizon, now=now))
        .where(*_after_cursor(cursor))
    )
    if sport:
        query = query.where(Sport.key == sport)
    if exclude_sports:
        query = query.where(Sport.key.notin_(tuple(exclude_sports)))
    return int((await session.execute(query)).scalar() or 0)


async def _load_rows(
    session,
    *,
    sport: Optional[str],
    limit: int,
    lookback: timedelta,
    horizon: timedelta,
    now: Optional[datetime] = None,
    cursor: Optional[str] = None,
    exclude_sports: frozenset[str] = frozenset(),
) -> list[AnchoredRow]:
    """The anchored, unfinished, near-future rows — oldest kickoff first.

    Oldest-first is the ordering that matters here: the rows closest to
    kickoff are the ones a user is about to see, and a truncated run should
    have spent its budget on them (gotcha #41 asks what the ordering starts on;
    this population does not expire, so a floor is enough and a ceiling is not
    needed).

    **The ordering carries ``Event.id`` as a tiebreaker and that is load-bearing
    now that a cursor exists.** ``commence_time`` is not unique — an NFL Sunday
    puts a dozen fixtures on one 17:00 kickoff — so ``ORDER BY commence_time``
    alone leaves the order within a tie up to the plan. Two pages either side of
    such a tie could then repeat rows or step over them, and the skipped row is
    invisible: it is simply never examined, and the sweep reports a clean census
    of the rows it did see.
    """
    from app.models.models import Event, Sport

    query = (
        select(
            Event.id,
            Event.espn_id,
            Event.commence_time,
            Event.home_team_name,
            Event.away_team_name,
            Event.status,
            Event.completed_at,
            Event.commence_time_source,
            Sport.key,
        )
        .join(Sport, Sport.id == Event.sport_id)
        .where(*_window(lookback=lookback, horizon=horizon, now=now))
        .where(*_after_cursor(cursor))
        .order_by(Event.commence_time, Event.id)
        .limit(limit)
    )
    if sport:
        query = query.where(Sport.key == sport)
    if exclude_sports:
        query = query.where(Sport.key.notin_(tuple(exclude_sports)))

    result = await session.execute(query)
    return [
        AnchoredRow(
            event_id=row.id,
            sport_key=row.key,
            home_team_name=row.home_team_name or "",
            away_team_name=row.away_team_name or "",
            espn_id=str(row.espn_id),
            commence_time=row.commence_time,
            status=row.status,
            completed_at=row.completed_at,
            commence_time_source=row.commence_time_source,
        )
        # Scalars, not ORM rows: this loop commits per move, and a live ORM
        # object does not survive that boundary (gotcha #6).
        for row in result.all()
    ]


async def _apply_move(session, decision) -> bool:
    """Write one move, and prove it landed on the row we decided about.

    The ``espn_id`` and ``commence_time`` in the WHERE clause are the compare:
    they are the two facts the decision was made from, so a row whose anchor or
    clock moved since the read is skipped rather than overwritten. ``rowcount``
    0 is therefore a real finding — the plan was stale — and not a silent pass.
    """
    from app.models.models import Event

    result = await session.execute(
        update(Event)
        .where(
            Event.id == decision.event_id,
            Event.espn_id == decision.espn_id,
            Event.commence_time == decision.ours,
        )
        .values(**decision.write)
    )
    return bool(result.rowcount)


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None


def undo_row_for(decision, row) -> dict[str, Any]:
    """One planned move -> the shape the record and the restore both read.

    ``before`` and ``after`` carry EVERY key in ``decision.write``, read off the
    row rather than assumed: this rail writes two columns today and a third
    would otherwise be moved with no way back. ``after`` is what makes the
    restore's compare exact — a row that does not still wear these values is a
    row something else has touched since.
    """
    before: dict[str, Any] = {}
    for column in decision.write:
        before[column] = _iso(getattr(row, column, None))
    return {
        "event_id": int(decision.event_id),
        "espn_id": str(decision.espn_id),
        "sport": row.sport_key,
        "matchup": f"{row.home_team_name} v {row.away_team_name}",
        "before": before,
        "after": {k: _iso(v) for k, v in decision.write.items()},
    }


def new_undo_invocation() -> str:
    """A fresh token for ONE apply. Never derived from the work it is about.

    CERT-856: everything an apply knows about itself — the clock, the plan, the
    move set — is shared with the apply running beside it, so an identity built
    only from those is the SAME identity, and the second apply's empty receipt
    replaced the first one's real one. The token is the one thing two concurrent
    applies cannot agree on.
    """
    return uuid.uuid4().hex[:12]


def undo_identity_for(
    rows: list[dict[str, Any]], *, at: datetime, invocation: str
) -> str:
    """A one-per-INVOCATION identity, salted by what the apply is about to do.

    Three parts, each answering a question that gets asked: the timestamp for
    "what did I run at 4pm", the digest for "which run moved these rows", and
    the invocation token for "which of the two runs that started together".

    The token is not decoration. Before CERT-856 this was second-resolution plus
    the digest, on the reasoning that two applies of the same moves in one
    second are the same write twice — which is true of the WRITE and false of
    the RECORD: the second run finds the clocks already moved, receipts nothing,
    and its empty record replaced the first run's populated one at the shared
    identity. Reproduced exactly, and the restore then reverted nothing.

    ``invocation`` is required rather than defaulted because the record's owner
    must be the SAME token (:data:`UNDO_OWNER_KEY`); a default here would let a
    caller build an identity nobody owns and lose the store's refusal with it.
    """
    stamp = at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S")
    stamp = f"{stamp}.{at.astimezone(timezone.utc).microsecond // 1000:03d}Z"
    digest = hashlib.sha256(
        json.dumps(
            [[r["event_id"], r["after"]] for r in rows], sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()[:12]
    return f"{UNDO_IDENTITY_PREFIX}:{stamp}:{digest}:{invocation}"


def undo_payload(
    *,
    taken_at: datetime,
    sport: Optional[str],
    planned: list[dict[str, Any]],
    receipted: list[dict[str, Any]],
    complete: bool,
    invocation: str,
) -> dict[str, Any]:
    """``rows`` is the RECEIPT; ``rows_planned`` is the intent.

    Same split, and the same reason, as the sibling drain after CERT-846: a
    record built from the plan offers to reverse moves that never happened.
    Deliberately NOT shared code with that rail — the two differ in exactly the
    place that matters (its compare can only ask "still blank?", this one asks
    "still the value we wrote?"), and one helper spanning both would have to
    lose that difference to fit.
    """
    return {
        "issue": "#2693",
        "rail": "reconcile_anchor_schedule",
        "taken_at": taken_at.isoformat(),
        "sport": sport,
        # WHOSE record this is. The durable store reads this key and refuses a
        # replacement from anyone else (CERT-856), so it is not a label — it is
        # the thing that keeps a concurrent apply from erasing this receipt.
        UNDO_OWNER_KEY: invocation,
        # THE RECEIPT — moves whose UPDATE matched a row. A planned move that
        # came back `stale` is not here, and that absence is the point.
        "rows": list(receipted),
        # The intent, kept for forensics and never replayed.
        "rows_planned": list(planned),
        "receipt_complete": complete,
    }


def _undo_envelope(identity: str, payload: dict[str, Any]):
    from app.utils.durable_state import DurableEnvelope

    return DurableEnvelope.build(
        identity=identity,
        schema_version=UNDO_SCHEMA,
        payload=payload,
        complete=True,
        source="repair:anchor-schedule:undo",
    )


def _undo_owner(payload: dict[str, Any]) -> Optional[str]:
    """The invocation token this record belongs to, or ``None``.

    ``None`` is never written. A record with no owner is one the store cannot
    protect, so building one is a bug, not a degraded mode.
    """
    owner = payload.get(UNDO_OWNER_KEY)
    return str(owner) if owner else None


def _classify_undo_write(identity: str, status: Optional[str]) -> tuple[bool, str]:
    """One reading of a durable stage dict, shared by both write paths."""
    if status == "ok":
        return True, "ok"
    if status == "occupied":
        return False, (
            f"undo persist OCCUPIED: identity {identity} already holds a record "
            f"written by a DIFFERENT invocation and was left untouched; that "
            f"record is somebody else's receipt and this apply has none"
        )
    if status == "superseded":
        return False, (
            f"undo persist SUPERSEDED: identity {identity} already holds a newer "
            f"row, so the record on file is not this apply's"
        )
    return False, f"undo persist rejected: {status}"


async def _save_undo(identity: str, payload: dict[str, Any]) -> tuple[bool, str]:
    """Persist one apply's record. ``superseded`` and ``occupied`` are FAILURES.

    A plan may count ``superseded`` a success — it means a good copy of a NEWER
    plan is on disk, so the durability contract holds. For an undo it is the
    opposite: the row at that identity holds somebody else's content, so the
    record on file is not this apply's, and accepting it would hand an operator
    a restore that puts back the wrong clocks. ``occupied`` (CERT-856) is the
    same failure caught one step earlier — the store declined to overwrite the
    other apply's receipt rather than reporting the loss afterwards.
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
    # inside it — same reason as `_read_undo` next door.
    envelope = _undo_envelope(identity, payload)
    try:
        result = await _publish(envelope, owner_key=UNDO_OWNER_KEY, owner=owner)
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        logger.warning("anchor-schedule undo persist raised: %s", type(exc).__name__)
        return False, f"undo persist raised: {type(exc).__name__}"
    return _classify_undo_write(identity, result.get("status"))


async def _save_undo_co_commit(
    session, identity: str, payload: dict[str, Any]
) -> tuple[bool, str]:
    """Stage the receipt in the caller's OPEN transaction and commit both.

    The answer to CERT-851 on this rail. ``_save_undo`` writes on its own
    session, so sealing the receipt could only happen before the moves committed
    (claiming moves the database might still discard) or after (leaving a whole
    committed BATCH with an empty record). Staging the receipt beside the moves
    and committing once removes the choice: the moves and the list of them land
    together or not at all.

    Anything short of ``ok`` rolls the transaction back, which takes every move
    in the batch with it. That is the D51 posture stated plainly — a schedule
    move that cannot be taken back is not a move this rail makes unattended.

    Since CERT-856 the stage is also OWNED: only the invocation that wrote the
    record may replace it, so a concurrent apply landing on the same identity is
    refused here (``occupied``) and rolled back, rather than quietly replacing a
    receipt somebody else is relying on.
    """
    from app.services.durable_snapshots import publish_owned_snapshot_in_txn

    owner = _undo_owner(payload)
    if owner is None:
        await session.rollback()
        return False, (
            f"undo persist REFUSED: the record for {identity} carries no "
            f"{UNDO_OWNER_KEY}; moves rolled back"
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
            return ok, f"{note}; moves rolled back"
        await session.commit()
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        logger.warning(
            "anchor-schedule undo co-commit raised: %s", type(exc).__name__
        )
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001 — rollback failure must not mask the cause
            pass
        return False, f"undo co-commit raised: {type(exc).__name__}"
    return True, "ok"


async def _read_undo(identity: str) -> tuple[Optional[dict[str, Any]], str]:
    """``(payload, reason)`` — a raise is "I could not read", never "not there"."""
    from app.services.durable_snapshots import read_snapshot_standalone

    # Built outside the `try` so the awaited call is the only thing inside it.
    # Not style: the residue scanner's Pass B sweeps changed files for other
    # harnesses' replacement literals, and the obvious
    # `) / except Exception as exc:  # noqa: BLE001` shape collides with one.
    read = read_snapshot_standalone(
        identity, expected_version=UNDO_SCHEMA, max_age_s=UNDO_MAX_AGE_S
    )
    try:
        got = await read
    except Exception as exc:  # noqa: BLE001 — a raise is UNREADABLE, not MISSING
        logger.warning("anchor-schedule undo read raised: %s", type(exc).__name__)
        return None, REASON_UNDO_UNREADABLE
    if not got.ok or got.envelope is None:
        return None, REASON_UNDO_MISSING
    payload = got.envelope.payload
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        return None, REASON_UNDO_CORRUPT
    return payload, "ok"


def _parse_written(value: Any) -> Any:
    """A recorded column value back into something comparable to the column.

    Timestamps round-tripped through JSON are ISO strings; everything else this
    rail writes (``commence_time_source``) is already a scalar.
    """
    if not isinstance(value, str):
        return value
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _revert_move(session, row: dict[str, Any]) -> bool:
    """Put one row's clock back, and only if it still wears the one we wrote.

    The compare is IN the write and it names the value THIS RAIL set. That is
    the whole safety argument for restoring unattended: a row that ingest, a
    sibling apply, or a human has moved since does not match, ``rowcount`` is 0,
    and it is reported ``CLOCK_MOVED_ON`` rather than dragged backwards.
    """
    from app.models.models import Event

    after = row.get("after") or {}
    before = row.get("before") or {}
    result = await session.execute(
        update(Event)
        .where(
            Event.id == int(row["event_id"]),
            Event.espn_id == str(row["espn_id"]),
            *[
                getattr(Event, column) == _parse_written(value)
                for column, value in sorted(after.items())
            ],
        )
        .values(**{c: _parse_written(v) for c, v in before.items()})
    )
    return bool(result.rowcount)


async def restore(session, undo_identity: str, apply: bool = False) -> dict[str, Any]:
    """Put back exactly the clocks one apply moved. Dry-run unless ``apply``.

    The mirror of the apply, with the same two properties: it acts on a stored
    record rather than a re-derivation, and its compare is in the write. It
    replays the RECEIPT — the moves that landed — and never ``rows_planned``.
    """
    stored, reason = await _read_undo(undo_identity)
    if stored is None:
        return {
            "measured": True, "terminal": "refused", "restore": True,
            "applied": apply,
            "undo_identity": undo_identity,
            "reason_codes": [reason],
            "reason": (
                "MISSING means no record is stored under that identity; "
                "UNREADABLE means the read failed right now; CORRUPT means one "
                "is there and cannot be trusted. Do not re-derive around it."
            ),
        }

    rows = stored["rows"]
    planned = stored.get("rows_planned")
    n_planned = len(planned) if isinstance(planned, list) else None
    if not apply:
        return {
            "measured": True, "terminal": "plan_only", "restore": True,
            "applied": False,
            "undo_identity": undo_identity,
            "taken_at": stored.get("taken_at"),
            "rows_in_record": len(rows),
            "rows_planned_in_record": n_planned,
            "receipt_complete": stored.get("receipt_complete"),
            "rows": rows,
            "reason": (
                f"Nothing was written. Re-run with apply=true to put these "
                f"{len(rows)} clock(s) back. Only moves that LANDED are in this "
                f"record; a row whose clock has changed since is reported "
                f"CLOCK_MOVED_ON and left alone."
            ),
        }

    reverted, moved_on = 0, []
    for row in rows:
        if await _revert_move(session, row):
            reverted += 1
            logger.info(
                "anchor-schedule restore: event %s clock put back to %s",
                row.get("event_id"), (row.get("before") or {}).get("commence_time"),
            )
        else:
            moved_on.append({
                "event_id": row.get("event_id"),
                "expected_commence_time": (row.get("after") or {}).get("commence_time"),
                "reason_code": "CLOCK_MOVED_ON",
            })
    await session.commit()

    return {
        "measured": True,
        # A restore that put nothing back because every row moved on did its job
        # and must not claim it reversed the apply.
        "terminal": "complete" if reverted == len(rows) else "partial",
        "restore": True,
        "applied": True,
        "undo_identity": undo_identity,
        "rows_in_record": len(rows),
        "rows_planned_in_record": n_planned,
        "reverted": reverted,
        "moved_on": moved_on,
        "reason": (
            f"put {reverted} of {len(rows)} clock(s) back; "
            f"{len(moved_on)} had moved on since the apply and were left alone"
        ),
    }


async def reconcile(
    session,
    *,
    apply: bool = False,
    limit: int = DEFAULT_LIMIT,
    sport: Optional[str] = None,
    lookback: timedelta = DEFAULT_LOOKBACK,
    horizon: timedelta = DEFAULT_HORIZON,
    cursor: Optional[str] = None,
    exclude_sports: frozenset[str] = frozenset(),
    budget_seconds: float = EXAMINE_BUDGET_SECONDS,
) -> dict[str, Any]:
    """Ask the authority about every anchored near-future row's kickoff.

    Returns a summary carrying an explicit ``terminal`` so ``task_verdict`` can
    read it, and a run that finds nothing to move reports ``no_work`` with the
    verdict census that explains the zero — "it returned" is not "it worked"
    (gotcha #53), and a rail that cannot tell a healthy population from an
    authority outage is a rail that reports health during an outage.

    ═══ PAGING, AND THE ONE WORD A PAGE MAY NOT SAY ═══

    ``limit`` is a router-timeout bound well under the population (25 against
    685), so an unattended sweep is necessarily several calls. ``next_cursor``
    makes them *consecutive* instead of each restarting at the oldest row; pass
    it back as ``cursor`` until it comes back ``None``.

    ``budget_seconds`` is the wall clock that actually ends a page, and its
    default is sized for **the HTTP caller**, which is the only one facing a
    30-second router. A caller that is NOT behind a router — the nightly
    sentinel runs in a Celery worker with its own 300s deadline — must say so by
    passing its own, or it silently inherits a bound built for somebody else's
    constraint and pages a third as far as it could. Both defaults on this
    function describe the admin endpoint; batch callers declare their own.

    Three counts, and they are three different questions:

    ``eligible``   the whole window, ignoring both cursor and limit. Its
                   meaning is unchanged by paging — deliberately, because it is
                   what a reviewer compares ``examined`` against.
    ``remaining``  the rows at or after the cursor. Equal to ``eligible`` on the
                   first page, which is why ``truncated`` keeps its old value
                   on every call that does not page.
    ``examined``   what THIS call looked at.

    **``truncated`` is ``eligible > examined`` OR carrying a cursor at all, and
    that is what stops a page from reporting an all-clear.** The second half is
    not redundant. It is tempting to argue that a cursor has rows behind it by
    construction and so ``examined`` is always short of ``eligible`` — but
    ``eligible`` is recounted against ``now`` on every call, while the cursor
    was minted against an earlier one. Rows the cursor skipped can age out
    through the moving ``now - lookback`` floor between two calls of the same
    sweep, and then ``eligible`` no longer counts them: a resumed cursor over a
    one-row current tail measures ``eligible == examined == 1`` and the count
    comparison alone would hand it ``no_work``. So cursor presence decides the
    terminal directly rather than being inferred from a count that does not
    remember it. ``no_work`` and ``complete`` remain reachable only from a
    single unpaged call that saw the entire window, which is the only situation
    in which either is true. Whether a *sweep* finished is the driver's finding
    to report, not any one page's; ``has_more`` is what the driver loops on.

    This is the same rule the empty-page branch above already applies with
    ``bool(cursor)``; the two branches agree because it is one rule, not two.
    """
    from app.services.espn_api import get_espn_service
    from app.tasks.repair_authority_id_collisions import _fetch_record

    eligible = await _count_eligible(
        session,
        sport=sport,
        lookback=lookback,
        horizon=horizon,
        exclude_sports=exclude_sports,
    )
    remaining = (
        eligible
        if not cursor
        else await _count_eligible(
            session,
            sport=sport,
            lookback=lookback,
            horizon=horizon,
            cursor=cursor,
            exclude_sports=exclude_sports,
        )
    )
    rows = await _load_rows(
        session,
        sport=sport,
        limit=limit,
        lookback=lookback,
        horizon=horizon,
        cursor=cursor,
        exclude_sports=exclude_sports,
    )
    if not rows:
        return {
            "measured": True,
            # A cursor that has run off the end of the window is the NORMAL way
            # a sweep stops, not an empty population — so it may not borrow the
            # word for one. `no_work` here would tell a driver that the whole
            # window was clean when all it learned is that it reached the end.
            "terminal": "no_work" if not cursor else "partial",
            "reason": (
                "no anchored, unfinished rows inside the window"
                if not cursor
                else "the cursor is past the last row in the window"
            ),
            "applied": apply,
            "eligible": eligible,
            "remaining": remaining,
            "truncated": bool(cursor),
            "has_more": False,
            "next_cursor": None,
            # Served on this path too so the key never reads as "this payload
            # predates the field": a page with no rows examined nothing, and
            # nothing is not the same discovery as "the clock stopped me".
            "stopped_by": None,
            **summarize_decisions([]),
        }

    service = get_espn_service()
    decisions = []
    stopped_by: Optional[str] = None
    started_at = _time.monotonic()
    for row in rows:
        record = await _fetch_record(service, [row.sport_key], row.espn_id)
        decisions.append(schedule_decision(row, record))
        # Checked AFTER the append, so a call always carries at least one
        # answered row: `rows[-1]` below is what builds `next_cursor`, and a
        # page that examined nothing would have no cursor to hand its
        # successor and would loop the driver forever on the same page.
        if _time.monotonic() - started_at >= budget_seconds:
            stopped_by = "budget"
            break

    # The tail the deadline cut off was never asked about. Trimming `rows` to
    # the answered prefix is what keeps that honest downstream WITHOUT touching
    # any of the reporting below: `examined` comes from `decisions`, `truncated`
    # and `has_more` compare it against `eligible`/`remaining`, and `next_cursor`
    # is built from `rows[-1]`. Leave `rows` at full length and every one of
    # those silently counts rows nobody looked at — the un-examined tail would
    # be reported as agreeing, and the cursor would skip it for good.
    # Did the deadline actually leave rows on the table, or did it trip on the
    # very last one? Recorded BEFORE the trim, because after it the two cases
    # are indistinguishable and only the first one owes the caller a cursor.
    budget_cut_tail = stopped_by == "budget" and len(decisions) < len(rows)
    if stopped_by is not None:
        rows = rows[: len(decisions)]

    summary = summarize_decisions(decisions)
    moved, stale = 0, 0
    undo_identity: Optional[str] = None
    receipted: list[dict[str, Any]] = []
    if apply:
        rows_by_id = {row.event_id: row for row in rows}
        movers = [d for d in decisions if d.verdict == AUTHORITY_MOVES_US]
        planned = [undo_row_for(d, rows_by_id[d.event_id]) for d in movers]

        # ── BACKUP BEFORE WRITE (D51) ────────────────────────────────────────
        # Not one clock is moved until this apply's own dated record is on disk.
        # The order is the whole point: a backup written afterwards is a backup
        # that does not exist for exactly the run that died halfway. The receipt
        # starts EMPTY because at this instant nothing has moved, and a record
        # that claims otherwise is the defect CERT-846 found next door.
        if movers:
            undo_at = datetime.now(timezone.utc)
            # ONE token for this apply, in the identity AND in the record. The
            # identity keeps a concurrent apply from choosing the same slot; the
            # record's copy keeps the store from letting it write there anyway.
            undo_invocation = new_undo_invocation()
            undo_identity = undo_identity_for(
                planned, at=undo_at, invocation=undo_invocation
            )

            def _record(rows_receipted, *, complete):
                return undo_payload(
                    taken_at=undo_at, sport=sport, planned=planned,
                    receipted=rows_receipted, complete=complete,
                    invocation=undo_invocation,
                )

            saved, note = await _save_undo(undo_identity, _record([], complete=False))
            if not saved:
                return {
                    "measured": True,
                    "terminal": "refused",
                    "applied": True,
                    "moved": 0,
                    "stale": 0,
                    "reason_codes": [REASON_UNDO_UNWRITTEN],
                    "undo_identity": undo_identity,
                    "undo_note": note,
                    "eligible": eligible,
                    "remaining": remaining,
                    "reason": (
                        "NOTHING WAS WRITTEN. The undo record for this apply could "
                        "not be persisted, and a schedule move that cannot be taken "
                        "back is not a repair this rail performs unattended (D51). "
                        "Fix the durable snapshot write and re-run."
                    ),
                    **summary,
                }

        for decision, planned_row in zip(movers, planned):
            if await _apply_move(session, decision):
                moved += 1
                receipted.append(planned_row)
                logger.info(
                    "anchor-schedule: event %d moved %s -> %s (%.1f days) on "
                    "authority %s",
                    decision.event_id,
                    decision.ours,
                    decision.theirs,
                    (decision.delta_seconds or 0) / 86400.0,
                    decision.espn_id,
                )
            else:
                # NOT a silent pass, and NOT a row the record may speak for.
                # Nothing was written to it, so a restore must not offer to put
                # a clock back on it.
                stale += 1
                logger.warning(
                    "anchor-schedule: event %d NOT moved — its anchor or clock "
                    "changed since the read (plan stale)",
                    decision.event_id,
                )

        if undo_identity is not None:
            # CO-COMMIT the receipt with the batch (CERT-851). Neither order of
            # two separate transactions is safe here: sealing first claims moves
            # the database might still discard, and sealing after leaves a
            # window in which the WHOLE batch is durable and its record is
            # empty. One transaction carries both, so the receipt is a statement
            # about exactly the rows that landed — never fewer, never more.
            sealed, seal_note = await _save_undo_co_commit(
                session, undo_identity, _record(receipted, complete=True)
            )
            if not sealed:
                # The rollback took every move with it. Nothing is on the
                # clocks, so the honest report is that this apply moved nothing
                # — not a `complete` carrying a receipt that does not exist.
                logger.warning(
                    "anchor-schedule: the receipt could not be co-committed (%s); "
                    "all %d move(s) in this batch were rolled back under %s",
                    seal_note, moved, undo_identity,
                )
                return {
                    "measured": True,
                    "terminal": "refused",
                    "applied": True,
                    "moved": 0,
                    "stale": stale,
                    "reason_codes": [REASON_UNDO_UNRECEIPTED],
                    "undo_identity": undo_identity,
                    "undo_note": seal_note,
                    "rows_receipted": 0,
                    "eligible": eligible,
                    "remaining": remaining,
                    "reason": (
                        "NOTHING WAS WRITTEN. The receipt for these moves could "
                        "not be committed alongside them, so the whole batch was "
                        "rolled back rather than left on the clocks with no way "
                        "back (D51). No restore is needed and none is offered. "
                        "Fix the durable snapshot write and re-run."
                    ),
                    **summary,
                }

    pending = summary["by_verdict"][AUTHORITY_MOVES_US]
    # A cursored call did not see the window: it deliberately skipped everything
    # before the cursor, whether or not `eligible` still counts those rows now.
    # `eligible` is recounted against a moving `now`, so it is not a record of
    # what this call skipped and cannot be asked to stand in for one.
    truncated = bool(cursor) or eligible > summary["examined"] or budget_cut_tail
    # `has_more` is about the CURSOR's tail; `truncated` is about the whole
    # window. On the last page of a sweep they disagree — nothing follows, yet
    # this call still saw a minority of the window — and both readings are true.
    #
    # `budget_cut_tail` is ORed in rather than left to the comparison because
    # `remaining` is a COUNT taken separately from the rows: when the deadline
    # cuts a page short we have direct evidence of an un-examined row in hand,
    # and that evidence must outrank a count that could be stale by a settle.
    # Without it a short page can report `has_more: false`, hand back no cursor,
    # and the sweep abandons its tail while every field looks healthy.
    has_more = remaining > summary["examined"] or budget_cut_tail
    last = rows[-1]
    next_cursor = encode_cursor(last.commence_time, last.event_id) if has_more else None
    # An authority that answered for nothing is not a clean population. The
    # terminal has to be able to say so, or a dark ESPN reads as "all agree".
    if summary["by_verdict"]["no_answer"] == summary["examined"]:
        terminal = "authority_dark"
    elif truncated:
        # A run that did not see the whole window has not finished, whatever it
        # found in the part it saw — and "no_work" would be the worst of the
        # three readings, because it is the one that sounds like an all-clear.
        # `partial` is chosen over a new word so `task_verdict` keeps reading it
        # as PARTIAL rather than UNKNOWN.
        terminal = "partial"
    elif not pending:
        terminal = "no_work"
    elif apply:
        terminal = "complete" if not stale else "partial"
    else:
        terminal = "plan_only"

    return {
        "measured": True,
        "terminal": terminal,
        "applied": apply,
        "moved": moved,
        "stale": stale,
        "eligible": eligible,
        "remaining": remaining,
        "truncated": truncated,
        "has_more": has_more,
        "next_cursor": next_cursor,
        # Why this page is the length it is. `None` means the page ran to its
        # `limit` normally; "budget" means the clock ended it early and the
        # short `examined` is the deadline working, not the population thinning.
        # Named to match the sibling driver's vocabulary in
        # `anchor_schedule_sentinel`, which already reports `stopped_by`.
        "stopped_by": stopped_by,
        # The undo is quoted as an IDENTITY and a runnable line, not as a
        # reassurance. An operator who has to go and find out how to reverse a
        # write does not have a reversible write. Absent on a dry run and on an
        # apply that had nothing to move, because neither wrote anything.
        **(
            {
                "undo_identity": undo_identity,
                "rows_receipted": len(receipted),
                "undo_command": (
                    f"python3 scripts/restore_anchor_schedule_moves.py "
                    f"--identity {undo_identity} --apply"
                ),
            }
            if undo_identity
            else {}
        ),
        **summary,
    }


def summarize_for_operator(result: dict[str, Any]) -> str:
    """One line an operator can act on. Never reads a dark authority as clean.

    ``examined`` is printed against ``eligible`` because the two differ far more
    often than they look like they should — the default limit is 200 and the
    window held 685 rows the day this was measured. A reviewer who is told only
    the first number will read a truncated pass as the whole story.

    A truncated call has two different remedies and printing the wrong one
    wastes the reader's next command: mid-sweep the answer is the cursor, and on
    the last page there is no remedy at all because nothing is left to see. So
    the advice is chosen on ``has_more``, not on ``truncated``.

    **A result with no ``has_more`` at all keeps the pre-paging wording.** An
    absent key is not a ``False`` one, and reading it as False would print "this
    page ends the window" — the one sentence that says a sweep is finished — on
    a summary that never measured whether it was. That is gotcha #53 in the
    shape this module keeps meeting: a missing signal answered as a definite no.
    """
    unknown = object()
    if not result.get("measured"):
        return f"UNMEASURED — {result.get('reason')}"
    if result.get("restore"):
        # A restore has no verdicts, no window and no cursor, and the reconcile
        # wording below would print `examined=None moved=0 stale=0` over a run
        # that had just put two clocks back — every number in it false, and
        # `moved=0` false in the direction that reads as "nothing happened".
        if result.get("terminal") == "refused":
            return (
                f"REFUSED — {', '.join(result.get('reason_codes') or ['unknown'])}: "
                f"{result.get('reason')}"
            )
        n_rows = result.get("rows_in_record", 0)
        if not result.get("applied"):
            return (
                f"plan_only: would revert {n_rows} move(s) from "
                f"{result.get('undo_identity')} — nothing written"
            )
        return (
            f"{result.get('terminal')}: reverted={result.get('reverted', 0)}/{n_rows} "
            f"moved_on={len(result.get('moved_on') or [])} · "
            f"{result.get('undo_identity')}"
        )
    verdicts = result.get("by_verdict") or {}
    counts = " ".join(f"{name}={verdicts.get(name, 0)}" for name in SCHEDULE_VERDICTS)
    examined = result.get("examined")
    eligible = result.get("eligible")
    reach = (
        f"examined={examined}/{eligible}"
        if eligible is not None
        else f"examined={examined}"
    )
    has_more = result.get("has_more", unknown)
    # A page the CLOCK ended is not a page `limit` ended, and the two have
    # opposite remedies. Saying "raise limit" to someone whose page stopped at
    # 18 seconds sends them to make the next one time out — the precise mistake
    # this function's docstring warns about, now reachable for a second reason.
    on_budget = result.get("stopped_by") == "budget"
    if has_more is True:
        reach += (
            f" MORE ({result.get('remaining', 0) - (examined or 0)} after this page; "
            f"pass cursor={result.get('next_cursor')})"
        )
        if on_budget:
            # Deliberately does not contain the phrase "raise limit" even to
            # negate it: this line is read in a hurry off a terminal, and a
            # skimmed negation is the advice.
            reach += (
                " [ended on the time budget — page again; a bigger page will not help]"
            )
    elif result.get("truncated"):
        if on_budget:
            reach += " BUDGET (this page ended on the clock, not on limit)"
        else:
            reach += (
                " TAIL (this page ends the window; earlier pages hold the rest)"
                if has_more is False
                else f" TRUNCATED (raise limit above {eligible} to see the rest)"
            )
    return (
        f"{result.get('terminal')}: {reach} "
        f"moved={result.get('moved', 0)} stale={result.get('stale', 0)} · {counts}"
    )
