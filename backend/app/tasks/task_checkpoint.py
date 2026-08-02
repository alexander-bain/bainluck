"""Runtime half of the Queue 300 resumability contract (#1513).

``app.utils.task_resumability`` holds the RULES (pure, corpus-graded). This
module is the only thing that touches a substrate, and it deliberately picks
PostgreSQL for both halves:

* **The checkpoint** goes in ``durable_state_snapshots`` (Queue 298's store),
  not Redis. Redis on this project is a 50MB ``allkeys-lru`` instance running at
  ~97% of maxmemory — a checkpoint key there is not "persisted with a TTL", it
  is a key waiting to be evicted, and an evicted checkpoint silently restarts a
  sweep from zero while every metric still says the task succeeded. That is the
  precise failure Queue 298 removed from the sentinels; repeating it here would
  be calling more Redis durability, which Queue 300's gate forbids.
* **The overlap lock** is a PostgreSQL advisory lock on the run's own session.
  It cannot be evicted, and it is released automatically when the session
  closes — including on SIGKILL, which a Redis ``SET NX EX`` lock survives as a
  stale lock that blocks the next beat.

One wrinkle worth naming: the durable envelope's ``complete`` flag means "this
record is a whole record", not "the sweep it describes finished" — a read of an
``complete=False`` envelope is classified MALFORMED by the C117 decoder. So a
checkpoint is always written ``complete=True`` and carries the sweep's real
terminal state inside its payload, where the resumability contract grades it.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.durable_state import DurableEnvelope
from app.utils.task_resumability import (
    CHECKPOINT_SCHEMA,
    Checkpoint,
    decode_checkpoint,
    new_checkpoint,
)

logger = logging.getLogger(__name__)

#: A checkpoint older than this is not resumed. A sweep that has not advanced in
#: a fortnight is not a sweep in progress, it is a fossil of one.
CHECKPOINT_MAX_AGE_S = 14 * 86400

CHECKPOINT_WRITE_TIMEOUT_MS = 5000


def checkpoint_identity(task: str) -> str:
    return f"task_checkpoint:{task}"


def advisory_lock_key(task: str) -> int:
    """Stable signed-64-bit advisory-lock key for a task name.

    Derived from the name rather than assigned from a registry so a new
    resumable task cannot forget to reserve one, and so two deploys of the same
    task always agree.
    """
    digest = hashlib.sha256(f"bainluck:task_lock:{task}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


async def try_acquire_overlap_lock(session: AsyncSession, task: str) -> bool:
    """Take the run lock for ``task`` on this session, or report we did not.

    Returns ``False`` rather than raising when another beat already owns the
    lock: the correct behaviour for an overlapping beat is to do nothing and
    say so, not to run a second sweep against the same cursor. A failure to
    even ask (a wedged database) also returns ``False`` — if we cannot prove we
    are the only writer, we are not allowed to write.
    """
    try:
        row = await session.execute(
            text("SELECT pg_try_advisory_lock(:key) AS acquired"),
            {"key": advisory_lock_key(task)},
        )
        return bool(row.scalar())
    except Exception as exc:  # noqa: BLE001 — never let the lock probe kill the beat
        logger.warning("overlap lock probe failed for %s: %s", task, exc)
        return False


async def release_overlap_lock(session: AsyncSession, task: str) -> None:
    """Best-effort explicit release. The session close would do it anyway."""
    try:
        await session.execute(
            text("SELECT pg_advisory_unlock(:key)"), {"key": advisory_lock_key(task)}
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("overlap lock release failed for %s: %s", task, exc)


async def load_checkpoint(task: str, version: str) -> tuple[Checkpoint, str]:
    """Read the durable checkpoint and classify it (fresh / resume / invalidate).

    Any read problem at all yields a fresh checkpoint. Restarting a sweep is
    merely expensive; resuming a checkpoint we cannot vouch for skips work
    while reporting it done.
    """
    from app.services.durable_snapshots import read_snapshot_standalone

    read = await read_snapshot_standalone(
        checkpoint_identity(task),
        expected_version=CHECKPOINT_SCHEMA,
        max_age_s=CHECKPOINT_MAX_AGE_S,
    )
    if not read.ok or read.envelope is None:
        if read.status not in ("missing",):
            logger.info(
                "checkpoint for %s not resumable (%s) — starting fresh",
                task,
                read.status,
            )
        return new_checkpoint(task, version), (
            "fresh" if read.status == "missing" else "invalidate"
        )
    return decode_checkpoint(read.envelope.payload, task=task, expected_version=version)


async def save_checkpoint(
    task: str,
    checkpoint: Checkpoint,
    *,
    terminal: str,
    extra: Optional[dict[str, Any]] = None,
) -> bool:
    """Persist the checkpoint. Returns whether the durable generation committed.

    The caller must only treat a chunk as durably recorded when this returns
    ``True`` — that boolean is what feeds ``durable_generation_committed`` in
    the contract row, and therefore what decides whether a run is allowed to
    publish anything.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone

    payload = checkpoint.as_payload()
    payload["terminal"] = terminal
    if extra:
        payload.update(extra)

    result = await publish_snapshot_standalone(
        DurableEnvelope.build(
            identity=checkpoint_identity(task),
            schema_version=CHECKPOINT_SCHEMA,
            payload=payload,
            # The RECORD is whole; the sweep's own state is `terminal` above.
            complete=True,
            source=task,
        )
    )
    ok = result.get("status") in ("ok", "superseded")
    if not ok:
        logger.warning("checkpoint persist failed for %s: %s", task, result)
    return ok


async def clear_checkpoint(task: str, version: str) -> bool:
    """Reset the cursor to zero after a complete sweep.

    Deliberately a write of a zeroed checkpoint rather than a DELETE: the
    durable store's whole atomicity story is a generation-guarded upsert with
    no delete path, so the next sweep reads an explicit "start at 0" under the
    current version instead of an absence it would have to interpret.
    """
    return await save_checkpoint(
        task, new_checkpoint(task, version), terminal="complete", extra={"cleared": True}
    )
