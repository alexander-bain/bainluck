"""Committed market invalidations; REST owns prices, normalization and results.

Producers queue only successful UPDATE RETURNING rows inside their transaction,
then drain with their existing Redis client after the session commits. A released
savepoint is not a commit. This module opens no database or Redis connection.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from redis.exceptions import ResponseError
from sqlalchemy import event as sa_event

logger = logging.getLogger(__name__)
SOURCES = frozenset({"kalshi", "polymarket"})
_PENDING = "market_quote_pending"
_READY = "market_quote_committed"
_HOOKS = "market_quote_hooks"
_PUBLISH_BATCH_SIZE = 32


def market_channel(market_id: int) -> str:
    return f"live:market:{market_id}"


def _timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError("a stored observation timestamp is required")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _positive_id(value: Any) -> bool:
    return type(value) is int and value > 0


def _change(*, market_id, source, outcome_observed_at, terminal, updated_at):
    if not _positive_id(market_id) or source not in SOURCES:
        raise ValueError("a market id and supported venue are required")
    if type(terminal) is not bool:
        raise ValueError("terminal must be an assigned market result")
    observations = {}
    for oid, stamp in outcome_observed_at.items():
        if not _positive_id(oid):
            raise ValueError("outcome ids must be positive integers")
        observations[str(oid)] = _timestamp(stamp).isoformat()
    stamps = [_timestamp(stamp) for stamp in observations.values()]
    if updated_at is not None:
        stamps.append(_timestamp(updated_at))
    if not stamps or (not terminal and not observations):
        raise ValueError("a quote needs returned outcome observations")
    return {
        "market_id": market_id,
        "source": source,
        "outcome_ids": sorted(map(int, observations)),
        "outcome_observed_at": observations,
        "updated_at": max(stamps).isoformat(),
        "terminal": terminal,
        "invalidation": True,
    }


def _coalesce(changes):
    latest = {}
    for change in changes:
        key = (change["market_id"], change["source"])
        previous = latest.get(key)
        if previous is None:
            latest[key] = dict(
                change, outcome_observed_at=dict(change["outcome_observed_at"])
            )
            continue
        observations = previous["outcome_observed_at"]
        for oid, stamp in change["outcome_observed_at"].items():
            if oid not in observations or _timestamp(stamp) > _timestamp(
                observations[oid]
            ):
                observations[oid] = stamp
        previous["outcome_ids"] = sorted(map(int, observations))
        previous["updated_at"] = max(previous["updated_at"], change["updated_at"])
        previous["terminal"] = previous["terminal"] or change["terminal"]
    return list(latest.values())


def _after_commit(session):
    if session.in_nested_transaction():
        return
    pending = session.info.pop(_PENDING, [])
    session.info.setdefault(_READY, []).extend(
        _coalesce(change for _, change in pending)
    )


def _after_rollback(session, transaction):
    def belongs_to(tx):
        while tx is not None:
            if tx is transaction:
                return True
            tx = tx.parent
        return False

    session.info[_PENDING] = [
        entry for entry in session.info.get(_PENDING, []) if not belongs_to(entry[0])
    ]


def queue_market_change(
    session,
    *,
    market_id: int,
    source: str,
    outcome_observed_at: Mapping[int, datetime | str],
    terminal: bool = False,
    updated_at: datetime | str | None = None,
) -> None:
    """Stage only rows the writer's UPDATE RETURNING actually changed.

    Observation stamps are returned ``FuturesOutcome.last_updated`` values, not
    receipt time. For a market-only settlement, pass no outcomes and its returned
    ``FuturesMarket.updated_at`` as ``updated_at``. Never derive ``terminal`` from
    a sports phase, a price, or a single losing member of an open field.
    """
    change = _change(
        market_id=market_id,
        source=source,
        outcome_observed_at=outcome_observed_at,
        terminal=terminal,
        updated_at=updated_at,
    )
    sync = session.sync_session
    transaction = sync.get_nested_transaction() or sync.get_transaction()
    if transaction is None:
        raise RuntimeError("a market change requires its writing transaction")
    if not sync.info.get(_HOOKS):
        sa_event.listen(sync, "after_commit", _after_commit)
        sa_event.listen(sync, "after_soft_rollback", _after_rollback)
        sync.info[_HOOKS] = True
    sync.info.setdefault(_PENDING, []).append((transaction, change))


async def _checkout(pool):
    """A pooled connection on every redis-py our ``>=5.0.1`` floor admits.

    5.3 deprecated ``get_connection``'s ``command_name`` (it warns on every call
    and is slated for removal); 5.0.x requires it. Calling without arguments
    first means a future removal cannot silently stop every publication. A
    missing-argument ``TypeError`` is raised at call binding, before anything
    is checked out, so the fallback never leaks a connection.
    """
    try:
        return await pool.get_connection()
    except TypeError:
        return await pool.get_connection("PUBLISH")


async def publish_committed_market_changes(session, redis_client) -> int:
    """Drain outer-commit-confirmed changes using a caller-owned Redis client.

    Returns the number of published market signals. No listeners is successful
    publication, not delivery proof. Failures are logged and never undo or retry
    a committed database write; clients recover through REST on reconnect.
    """
    changes = _coalesce(session.info.pop(_READY, []))
    if not changes:
        return 0
    sent = 0
    try:
        async with asyncio.timeout(5):
            pool = redis_client.connection_pool
            connection = await _checkout(pool)
            try:
                for start in range(0, len(changes), _PUBLISH_BATCH_SIZE):
                    batch = changes[start : start + _PUBLISH_BATCH_SIZE]
                    commands = []
                    for change in batch:
                        frame = dict(
                            change, published_at=datetime.now(timezone.utc).isoformat()
                        )
                        commands.append(
                            (
                                "PUBLISH",
                                market_channel(frame["market_id"]),
                                json.dumps(frame),
                            )
                        )
                    # Send the whole bounded batch before awaiting any replies.
                    # Use the caller's pool without Pipeline.execute's automatic
                    # transport retry: an unanswered publish may already have run.
                    await connection.send_packed_command(
                        connection.pack_commands(commands)
                    )
                    for change in batch:
                        try:
                            reply = await connection.read_response()
                        except ResponseError:
                            # A command error still consumes its reply. Drain
                            # the remaining replies so healthy siblings survive.
                            logger.warning(
                                "market quote publish failed: market=%s",
                                change["market_id"],
                                exc_info=True,
                            )
                            continue
                        if type(reply) is not int or reply < 0:
                            raise ValueError("invalid Redis PUBLISH acknowledgment")
                        sent += 1  # Zero listeners is a successful publication.
            except BaseException:
                # Timeout/cancellation/transport failure can leave unread replies.
                # Never return that socket to the shared pool in a reusable state.
                await connection.disconnect()
                raise
            finally:
                await pool.release(connection)
    except Exception:
        logger.warning(
            "market quote publication incomplete: sent=%s queued=%s",
            sent,
            len(changes),
            exc_info=True,
        )
    return sent


def parse_market_frame(raw: Any) -> dict | None:
    """Refuse malformed frames before a shared-loop subscriber touches them."""
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            return None
        frame = json.loads(raw)
        if not isinstance(frame, dict) or frame.get("invalidation") is not True:
            return None
        observations = frame["outcome_observed_at"]
        ids = frame["outcome_ids"]
        if not isinstance(observations, dict) or not isinstance(ids, list):
            return None
        if not all(_positive_id(oid) for oid in ids) or len(ids) != len(set(ids)):
            return None
        if set(observations) != {str(oid) for oid in ids}:
            return None
        parsed = _change(
            market_id=frame["market_id"],
            source=frame["source"],
            outcome_observed_at={
                int(oid): stamp for oid, stamp in observations.items()
            },
            terminal=frame["terminal"],
            updated_at=_timestamp(frame["updated_at"]),
        )
        parsed["published_at"] = _timestamp(frame["published_at"]).isoformat()
        return parsed
    except (KeyError, TypeError, ValueError, OverflowError, UnicodeError):
        return None
