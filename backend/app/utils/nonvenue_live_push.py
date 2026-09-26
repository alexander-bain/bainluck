"""Publish committed sportsbook/model probability writes to the existing stream.

#8761: these producers used to change REST/history while an open page waited for
an unrelated venue tick. Buffer only their exact UPDATE RETURNING snapshots;
savepoint releases are not commits and Redis never sees rolled-back prices.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

from sqlalchemy import case, cast, event as sa_event, func, inspect, literal, update
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


def _after_commit(session):
    if session.in_nested_transaction():
        return
    pending = session.info.pop(_PENDING, [])
    # One event may change twice in a transaction (ESPN followed by stat_model).
    # Only its last kept snapshot should reach a reader.
    latest = {frame["event_id"]: frame for _, frame, _, _ in pending}
    session.info.setdefault(_READY, []).extend(
        frame for frame in latest.values() if frame["status"] == "live"
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
    for _, _, event, previous in reversed(rolled_back):
        if event is not None:
            set_committed_value(event, "win_probability_sources", previous)
    session.info[_PENDING] = [entry for entry in pending if not belongs_to(entry[0])]


def _queue(session, frame, event, previous):
    sync = session.sync_session
    if not sync.info.get(_HOOKS):
        sa_event.listen(sync, "after_commit", _after_commit)
        sa_event.listen(sync, "after_soft_rollback", _after_rollback)
        sync.info[_HOOKS] = True
    transaction = sync.get_nested_transaction() or sync.get_transaction()
    if transaction is None:
        raise RuntimeError("a probability frame requires its writing transaction")
    sync.info.setdefault(_PENDING, []).append((transaction, frame, event, previous))


async def write_nonvenue_probability(
    session,
    event,
    source: str,
    value: float | None,
    *,
    metadata=None,
    values=None,
):
    """Atomically replace/remove one allowed source and queue its returned blend.

    ``None`` removes a source under the caller's existing refusal policy. Extra
    metadata is inert top-level data (currently sportsbook count); extra values
    retain the ESPN writer's own id/fallback columns. No commit happens here.
    """
    if source not in NONVENUE_SOURCES:
        raise ValueError(f"not a nonvenue probability source: {source}")
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
            )
            .execution_options(synchronize_session=False)
        )
    ).first()
    if row is None:
        return None
    sources, status, espn, opening, removed_at = row
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
        ),
        mapped,
        previous,
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
