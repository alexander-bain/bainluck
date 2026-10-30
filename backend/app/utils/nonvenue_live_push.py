"""Publish committed sportsbook/model probability writes to the existing stream.

#8761: these producers used to change REST/history while an open page waited for
an unrelated venue tick. Buffer only their exact UPDATE RETURNING snapshots;
savepoint releases are not commits and Redis never sees rolled-back prices.

#4971: with ``PROBABILITY_PUBLICATION_RECORDING`` on, ``before_commit`` also
records each event's final committed bag inside the same transaction
(``probability_publication``). Pending entries carry the write's observation.

#10090: with ``NONVENUE_TRACE_EVENTS`` armed, a traced event's writes are
receipted in this process's log from RETURNING through COMMIT to the Redis
reply (`app.utils.nonvenue_trace`), and a COMMIT carrying one re-reads that
row once (`_read_committing_rows`). Disarmed, each hook is a ``None`` check.

#10090 field 3 (always on, log only): every committed LIVE frame these writers
publish is credited in one ``writer-receipt`` line, the delivery receipt's
``stamps=`` item ``rev@stamped_at@recv@recv@sources@first_new_recv``. ``recv``
is when the producer received its input (the odds poll's listing), ``-`` if it
did not say. ``first_new_recv`` is that ``recv`` when the write changed the
blend: the committed bag's aggregate against the same bag with each written
source's prior entry put back, both computed at COMMIT. ``-`` when it did not;
``?`` when the prior entry or the receipt instant is unknown here (an unmapped
event, a producer that does not time its fetch). The comparison is against the
stored bag, not against a venue preview another process may be showing.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace

from sqlalchemy import (
    case,
    cast,
    event as sa_event,
    func,
    inspect,
    literal,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm.attributes import set_committed_value

from app.models.models import Event
from app.tasks.live_blend_refresh import atomic_stamp_expression
from app.utils.aggregation import compute_aggregate_probability
from app.utils.live_push import build_frame, publish_frame
from app.utils.nonvenue_trace import nonvenue_trace

logger = logging.getLogger(__name__)
_PENDING = "nonvenue_probability_pending"
_READY = "nonvenue_probability_committed"
_HOOKS = "nonvenue_probability_hooks"
_CLIENT_SCOPE = "nonvenue_probability_client_scope"
_RECEIPTS = "nonvenue_probability_receipts"
NONVENUE_SOURCES = frozenset({"betting", "stat_model", "mlb", "espn"})
#: #10090 field 3: one line per committed live frame (module doc).
WRITER_RECEIPT_FORMAT = "nonvenue_live_push[%s]: writer-receipt writer=%s event=%s stamps=%s"
_ABSENT = object()  # the source had no entry before this transaction wrote it
_UNKNOWN = object()  # what it had is not known to this process


def _iso(wall):
    if wall is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(wall, timezone.utc).isoformat(timespec="milliseconds")


def _note_receipt(sync, event_id, source, previous, row, received_at):
    """Keep what this transaction's receipt needs: each written source's entry
    before the transaction's FIRST write of it, the newest committed row, and
    the newest receipt instant. Never raises."""
    try:
        context = sync.info.setdefault(_RECEIPTS, {}).setdefault(
            event_id, {"priors": {}, "received_at": None, "row": None},
        )
        if source not in context["priors"]:
            context["priors"][source] = (
                previous.get(source, _ABSENT) if isinstance(previous, dict) else _UNKNOWN
            )
        if received_at is not None:
            context["received_at"] = max(received_at, context["received_at"] or received_at)
        context["row"] = row
    except Exception:
        logger.warning("nonvenue writer receipt not noted", exc_info=True)


def _first_new_recv(context) -> str:
    priors = context["priors"]
    sources, status, espn, opening = context["row"]
    if not isinstance(sources, dict) or any(p is _UNKNOWN for p in priors.values()):
        return "?"
    before = dict(sources)
    for name, prior in priors.items():
        if prior is _ABSENT:
            before.pop(name, None)
        else:
            before[name] = prior

    def blend(bag):
        value = compute_aggregate_probability(SimpleNamespace(
            win_probability_sources=bag, status=status,
            espn_win_prob_home=espn, opening_home_probability=opening,
        ), status)
        return None if value is None else float(value)

    after, prior_value = blend(sources), blend(before)
    if after is None or (prior_value is not None and abs(after - prior_value) <= 1e-9):
        return "-"
    return _iso(context["received_at"]) or "?"


def _log_writer_receipts(latest, receipts) -> None:
    for event_id, frame in latest.items():
        context = receipts.get(event_id)
        if context is None or context["row"] is None or not _frame_is_sent(frame):
            continue
        try:
            recv = _iso(context["received_at"]) or "-"
            rev = (frame.get("rev") or {}).get(str(event_id))
            writer = "+".join(sorted(context["priors"]))
            logger.info(WRITER_RECEIPT_FORMAT, writer, writer, event_id, "@".join((
                "-" if rev is None else str(rev), str(frame["updated_at"]), recv, recv,
                str(len(context["priors"])), _first_new_recv(context),
            )))
        except Exception:
            logger.warning("nonvenue writer receipt failed for event %s", event_id,
                           exc_info=True)


def _frame_is_sent(frame) -> bool:
    return frame["status"] == "live" and frame["source_value"] is not None


def _before_commit(session):
    # Savepoint releases fire before_commit too; only the outer COMMIT counts.
    if session.in_nested_transaction():
        return
    trace = nonvenue_trace()
    if trace is not None:
        trace.commit_started(session.info.get(_PENDING, ()), _frame_is_sent,
                             read=lambda ids: _read_committing_rows(session, ids))
    from app.utils.probability_publication import (
        record_committing_publications,
        recording_enabled,
    )

    if not recording_enabled():
        return
    pending = session.info.get(_PENDING, [])
    if not pending:
        return
    latest = {frame["event_id"]: frame for _, frame, _, _, _ in pending}
    queued = {
        event_id: (frame if _frame_is_sent(frame) else None)
        for event_id, frame in latest.items()
    }
    record_committing_publications(
        session,
        [
            (frame["event_id"], observation, queued[frame["event_id"]])
            for _, frame, _, _, observation in pending
        ],
    )


def _after_commit(session):
    if session.in_nested_transaction():
        return
    pending = session.info.pop(_PENDING, [])
    # One event may change twice in a transaction (ESPN followed by stat_model).
    # Only its last kept snapshot should reach a reader.
    latest = {frame["event_id"]: frame for _, frame, _, _, _ in pending}
    # Current consumers interpret a null source_value as the blended p, which
    # would resurrect a removed source as a fabricated quote. Keep removal as
    # a tombstone through coalescing, then suppress it: an earlier quote in the
    # same transaction must not escape after its source was removed.
    session.info.setdefault(_READY, []).extend(
        frame for frame in latest.values() if _frame_is_sent(frame)
    )
    receipts = session.info.pop(_RECEIPTS, None)
    if receipts:
        _log_writer_receipts(latest, receipts)
    trace = nonvenue_trace()
    if trace is not None:
        trace.committed(pending, latest, _frame_is_sent)


def _after_rollback(session, transaction):
    def belongs_to(tx):
        while tx is not None:
            if tx is transaction:
                return True
            tx = tx.parent
        return False

    pending = session.info.get(_PENDING, [])
    rolled_back = [entry for entry in pending if belongs_to(entry[0])]
    for _, _, event, previous, _ in reversed(rolled_back):
        if event is not None:
            set_committed_value(event, "win_probability_sources", previous)
    session.info[_PENDING] = [entry for entry in pending if not belongs_to(entry[0])]
    receipts = session.info.get(_RECEIPTS)
    if receipts:
        # A rolled-back write is credited nowhere; a later one starts afresh.
        alive: dict = {}
        for _, frame, _, _, _ in session.info[_PENDING]:
            alive.setdefault(frame["event_id"], set()).add(frame.get("source"))
        for event_id in list(receipts):
            priors = receipts[event_id]["priors"]
            for name in [n for n in priors if n not in alive.get(event_id, ())]:
                del priors[name]
            if not priors:
                del receipts[event_id]
    trace = nonvenue_trace()
    if trace is not None:
        trace.rolled_back(transaction, rolled_back)


def _committing_rows_query(event_ids):
    return select(
        Event.id,
        Event.win_probability_sources_rev,
        Event.win_probability_sources,
        Event.status,
        Event.espn_win_prob_home,
        Event.opening_home_probability,
    ).where(Event.id.in_(event_ids))


def _read_committing_rows(session, event_ids):
    """#10090, armed only: the traced events' rows as this COMMIT will store them.

    Called by `nonvenue_trace` from the outer ``before_commit``, once per
    COMMIT that carries a traced event, never when disarmed. Our UPDATE holds
    each row's lock until COMMIT, so no other transaction can change it; what
    this transaction still can change after this read is its own pending ORM
    state, which SQLAlchemy flushes AFTER ``before_commit``: an Event with that
    id in ``new``/``dirty``/``deleted`` is reported as ``orm_pending``. The
    read runs in its own SAVEPOINT, so a failed SELECT costs only the receipt.
    Returns ``{event_id: {rev, sources, status, espn_win_prob_home,
    opening_home_probability, orm_pending}}``; a vanished row is absent.
    """
    ids = sorted(event_ids)

    def row_id(obj):
        key = inspect(obj).key
        return key[1][0] if key else obj.__dict__.get("id")

    flushing = {
        row_id(obj)
        for obj in (*session.new, *session.dirty, *session.deleted)
        if isinstance(obj, Event)
    }
    connection = session.connection()
    with connection.begin_nested():
        rows = connection.execute(_committing_rows_query(ids)).all()
    return {
        event_id: dict(rev=rev, sources=sources, status=status,
                       espn_win_prob_home=espn, opening_home_probability=opening,
                       orm_pending=event_id in flushing)
        for event_id, rev, sources, status, espn, opening in rows
    }


_PRIOR_WRITE_PROBE_SQL = (
    "SELECT coalesce(pg_xact_status((((pg_current_xact_id()::text::bigint >> 32)"
    " << 32) | xmin::text::bigint)::text::xid8) = 'in progress', false)"
    " FROM events WHERE id = :id"
)


async def _probe_prior_txn_row_write(session, event_id):
    """#4971: had THIS transaction already modified the row before this write?

    Asked only for the first tracked write of an event in a transaction, and
    only while recording is on. A row version visible to us whose ``xmin`` is
    still in progress can only be our own write, top-level or savepoint. Pending
    ORM state is flushed first (see below). False
    therefore proves the bag this write starts from is the committed one. True
    means an earlier write in this transaction, which this path did not see,
    touched the row. Whether it touched the bag is not known.

    ``xmin`` is 32 bits and is placed in the current epoch. After a
    wraparound, an ancient frozen row can alias to another live transaction,
    which reads True (conservative), or to a future xid, which makes
    ``pg_xact_status`` raise. The probe therefore runs in its own SAVEPOINT. An
    error yields None ("not established"), and the price write is untouched.
    """
    from app.utils.probability_publication import recording_enabled

    if not recording_enabled():
        return None
    sync = session.sync_session
    pending = sync.info.get(_PENDING, [])
    if any(frame["event_id"] == event_id for _, frame, _, _, _ in pending):
        return None
    # The Core probe bypasses autoflush, but the UPDATE below does not: pending
    # ORM state would land between them, unseen. Flush it first, which is
    # exactly what that UPDATE's autoflush does a moment later. With autoflush
    # off, pending state flushes at some later point we cannot place, so a
    # session with any pending state is not established.
    if sync.autoflush:
        await session.flush()
    elif sync.new or sync.dirty or sync.deleted:
        return None
    connection = await session.connection()
    try:
        async with connection.begin_nested():
            return (
                await connection.execute(text(_PRIOR_WRITE_PROBE_SQL), {"id": event_id})
            ).scalar()
    except Exception:
        logger.warning(
            "prior-write probe failed for event %s; coverage not established",
            event_id,
            exc_info=True,
        )
        return None


def _queue(session, frame, event, previous, observation):
    sync = session.sync_session
    if not sync.info.get(_HOOKS):
        sa_event.listen(sync, "before_commit", _before_commit)
        sa_event.listen(sync, "after_commit", _after_commit)
        sa_event.listen(sync, "after_soft_rollback", _after_rollback)
        sync.info[_HOOKS] = True
    transaction = sync.get_nested_transaction() or sync.get_transaction()
    if transaction is None:
        raise RuntimeError("a probability frame requires its writing transaction")
    sync.info.setdefault(_PENDING, []).append(
        (transaction, frame, event, previous, observation)
    )


async def write_nonvenue_probability(
    session,
    event,
    source: str,
    value: float | None,
    *,
    metadata=None,
    values=None,
    evidence=None,
    trace_inputs=None,
    received_at=None,
):
    """Atomically replace/remove one allowed source and queue its returned blend.

    ``None`` removes a source under the caller's existing refusal policy and
    cancels any earlier queued event frame; consumers do not yet support source
    removal messages. Extra metadata is inert top-level data (currently
    sportsbook count); extra values
    retain the ESPN writer's own id/fallback columns. ``evidence`` is the
    producer's own eligibility record for this write (#4971); it is kept only
    in the publication row, never in the bag. No commit happens here.
    ``trace_inputs`` (#10090) is the producer's own input/version witness, a
    dict or a zero-argument callable; it is read only for a traced event and
    reaches nothing but `nonvenue_trace`. ``received_at`` (#10090) is when the
    producer received its input, epoch seconds; it reaches only the writer
    receipt (module doc).
    """
    if source not in NONVENUE_SOURCES:
        raise ValueError(f"not a nonvenue probability source: {source}")
    trace = nonvenue_trace()
    seam = None if trace is None else trace.seam_entered(
        event.id, transaction=session.sync_session.get_transaction(), source=source,
        value=value, evidence=evidence, metadata_keys=sorted(metadata or {}),
        prior=(event.__dict__.get("win_probability_sources")
               if inspect(event, raiseerr=False) is not None else None),
        inputs=trace_inputs,
    )
    try:
        return await _write(session, event, source, value, metadata, values, evidence,
                            trace, seam, received_at)
    except BaseException as exc:
        if seam is not None:
            trace.write_failed(seam, exc)
        raise


async def _write(session, event, source, value, metadata, values, evidence, trace, seam,
                 received_at=None):
    prior_txn_row_write = await _probe_prior_txn_row_write(session, event.id)
    # Literal source dispatch keeps the existing writer/eligibility scanner
    # able to verify every mint. This entry point never accepts venue sources.
    if source == "betting":
        expression = atomic_stamp_expression("betting", value)
    elif source == "stat_model":
        expression = atomic_stamp_expression("stat_model", value)
    elif source == "mlb":
        expression = atomic_stamp_expression("mlb", value)
    else:
        expression = atomic_stamp_expression("espn", value)
    if value is None:
        # Preserve every concurrent sibling when a source goes below its floor.
        column = Event.win_probability_sources
        expression = case(
            (func.jsonb_typeof(column) == "object", column),
            else_=cast(literal("{}"), JSONB),
        ).op("-")(source)
    if metadata:
        import json

        expression = expression.concat(cast(literal(json.dumps(metadata)), JSONB))
    fields = dict(values or {})
    row = (
        await session.execute(
            update(Event)
            .where(Event.id == event.id)
            .values(win_probability_sources=expression, **fields)
            .returning(
                Event.win_probability_sources,
                Event.status,
                Event.espn_win_prob_home,
                Event.opening_home_probability,
                func.clock_timestamp().label("removed_at"),
                Event.win_probability_sources_rev,
            )
            .execution_options(synchronize_session=False)
        )
    ).first()
    if row is None:
        if seam is not None:
            trace.missing_row(seam)
        return None
    sources, status, espn, opening, removed_at, rev = row
    # Mirror a Core update without marking the JSONB dirty: a later autoflush
    # must not overwrite an intervening venue write with this private copy.
    mapped = event if inspect(event, raiseerr=False) is not None else None
    previous = (
        event.__dict__.get("win_probability_sources") if mapped is not None else None
    )
    if mapped is not None:
        set_committed_value(event, "win_probability_sources", sources)
    _note_receipt(session.sync_session, event.id, source,
                  previous if mapped is not None else _UNKNOWN,
                  (sources, status, espn, opening), received_at)
    at = sources[source]["updated_at"] if value is not None else removed_at.isoformat()
    shim = SimpleNamespace(
        win_probability_sources=sources,
        status=status,
        espn_win_prob_home=espn,
        opening_home_probability=opening,
    )
    frame = build_frame(
        event_id=event.id,
        probability=compute_aggregate_probability(shim, status),
        source=source,
        source_value=value,
        updated_at=at,
        status=status,
        rev=rev,
    )
    _queue(
        session,
        frame,
        mapped,
        previous,
        {
            "source": source,
            "value": value,
            "removed": value is None,
            "rev": rev,
            "stamped_at": at,
            "returned_sources": sources,
            "metadata_keys": sorted(metadata or {}),
            "prior_txn_row_write": prior_txn_row_write,
            "evidence": evidence,
        },
    )
    if seam is not None:
        trace.written(
            seam, frame, transaction=session.sync_session.get_transaction(), rev=rev,
            stamped_at=at, sources=sources, status=status, espn=espn, opening=opening,
            prior_txn_row_write=prior_txn_row_write,
        )
    return sources


async def _close_publication_client(client):
    if client is not None:
        try:
            await client.aclose()
        except Exception:
            logger.debug("nonvenue Redis close failed", exc_info=True)


@asynccontextmanager
async def nonvenue_publication_scope(session):
    """Own one lazy Redis client until this task session has finished draining.

    Per-game commits keep immediate publication but reuse the connection.
    Nothing is shared across task sessions or their event loops. Sessions
    that never publish allocate no client.
    """
    info = session.info
    if _CLIENT_SCOPE in info:
        raise RuntimeError("nonvenue publication scope already owned")
    holder = {"client": None}
    info[_CLIENT_SCOPE] = holder
    try:
        yield
    finally:
        info.pop(_CLIENT_SCOPE, None)
        await _close_publication_client(holder["client"])


async def publish_committed_nonvenue_frames(session):
    """Drain only outer-commit-confirmed frames. Fanout cannot undo a DB write."""
    info = getattr(session, "info", None)
    if not isinstance(info, dict):
        return
    frames = info.pop(_READY, [])
    if not frames:
        return
    redis = None
    holder = info.get(_CLIENT_SCOPE)
    trace = nonvenue_trace()
    aborted = "CANCELLED"  # what an unfinished traced frame reads if no except ran
    try:
        from app.tasks.redis_state import get_async_redis_client

        if holder is None:
            redis = get_async_redis_client()
        else:
            if holder["client"] is None:
                holder["client"] = get_async_redis_client()
            redis = holder["client"]
        async with asyncio.timeout(5):
            for frame in frames:
                token = None if trace is None else trace.publish_started(frame)
                sent = await publish_frame(redis, frame)
                if token is not None:
                    trace.published(token, sent)
                if not sent:
                    logger.warning(
                        "nonvenue live frame not sent: event=%s source=%s",
                        frame["event_id"],
                        frame["source"],
                    )
        aborted = None
    except Exception as exc:
        aborted = "TIMEOUT" if isinstance(exc, TimeoutError) else "ERROR"
        logger.warning(
            "nonvenue live fanout failed for %s committed frames",
            len(frames),
            exc_info=True,
        )
    finally:
        if trace is not None and aborted is not None:
            trace.publish_closed(frames, aborted)
        if holder is None:
            await _close_publication_client(redis)
