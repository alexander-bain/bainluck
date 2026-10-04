"""Publish committed sportsbook/model probability writes to the existing stream.

#8761: these producers used to change REST/history while an open page waited for
an unrelated venue tick. Buffer only their exact UPDATE RETURNING snapshots;
savepoint releases are not commits and Redis never sees rolled-back prices.

#4971: with ``PROBABILITY_PUBLICATION_RECORDING`` on, ``before_commit`` also
records each event's final committed bag inside the same transaction
(``probability_publication``). Pending entries carry the write's observation.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

from sqlalchemy import (
    case,
    cast,
    event as sa_event,
    func,
    inspect,
    literal,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm.attributes import set_committed_value

from app.models.models import Event
from app.tasks.live_blend_refresh import atomic_stamp_expression
from app.utils.aggregation import compute_aggregate_probability
from app.utils.live_push import build_frame, publish_frame

logger = logging.getLogger(__name__)
_PENDING = "nonvenue_probability_pending"
_READY = "nonvenue_probability_committed"
_HOOKS = "nonvenue_probability_hooks"
NONVENUE_SOURCES = frozenset({"betting", "stat_model", "mlb", "espn"})


def _frame_is_sent(frame) -> bool:
    return frame["status"] == "live" and frame["source_value"] is not None


def _before_commit(session):
    # Savepoint releases fire before_commit too; only the outer COMMIT counts.
    if session.in_nested_transaction():
        return
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


_PRIOR_WRITE_PROBE_SQL = (
    "SELECT coalesce(pg_xact_status((((pg_current_xact_id()::text::bigint >> 32)"
    " << 32) | xmin::text::bigint)::text::xid8) = 'in progress', false)"
    " FROM events WHERE id = :id"
)


async def _probe_prior_txn_row_write(session, event_id):
    """#4971: had THIS transaction already modified the row before this write?

    Asked only for the first tracked write of an event in a transaction, and
    only while recording is on. A row version visible to us whose ``xmin`` is
    still in progress can only be our own write, top-level or savepoint. False
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
    pending = session.sync_session.info.get(_PENDING, [])
    if any(frame["event_id"] == event_id for _, frame, _, _, _ in pending):
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
):
    """Atomically replace/remove one allowed source and queue its returned blend.

    ``None`` removes a source under the caller's existing refusal policy and
    cancels any earlier queued event frame; consumers do not yet support source
    removal messages. Extra metadata is inert top-level data (currently
    sportsbook count); extra values
    retain the ESPN writer's own id/fallback columns. ``evidence`` is the
    producer's own eligibility record for this write (#4971); it is kept only
    in the publication row, never in the bag. No commit happens here.
    """
    if source not in NONVENUE_SOURCES:
        raise ValueError(f"not a nonvenue probability source: {source}")
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
    at = sources[source]["updated_at"] if value is not None else removed_at.isoformat()
    shim = SimpleNamespace(
        win_probability_sources=sources,
        status=status,
        espn_win_prob_home=espn,
        opening_home_probability=opening,
    )
    _queue(
        session,
        build_frame(
            event_id=event.id,
            probability=compute_aggregate_probability(shim, status),
            source=source,
            source_value=value,
            updated_at=at,
            status=status,
            rev=rev,
        ),
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
    return sources


async def publish_committed_nonvenue_frames(session):
    """Drain only outer-commit-confirmed frames. Fanout cannot undo a DB write."""
    info = getattr(session, "info", None)
    if not isinstance(info, dict):
        return
    frames = info.pop(_READY, [])
    if not frames:
        return
    redis = None
    try:
        from app.tasks.redis_state import get_async_redis_client

        redis = get_async_redis_client()
        async with asyncio.timeout(5):
            for frame in frames:
                if not await publish_frame(redis, frame):
                    logger.warning(
                        "nonvenue live frame not sent: event=%s source=%s",
                        frame["event_id"],
                        frame["source"],
                    )
    except Exception:
        logger.warning(
            "nonvenue live fanout failed for %s committed frames",
            len(frames),
            exc_info=True,
        )
    finally:
        if redis is not None:
            try:
                await redis.aclose()
            except Exception:
                logger.debug("nonvenue Redis close failed", exc_info=True)
