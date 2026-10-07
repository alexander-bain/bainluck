"""Serialize a bounded ActivityKit page and bank its fair cursor in PostgreSQL.

The transaction advisory lock cannot expire halfway through a page or survive a
crashed database connection. The cursor uses the existing durable snapshot store,
not evictable Redis. Delivery commits independently: a crash before checkpoint
commit may revisit a page, and the existing delivery worker fences that replay.
"""

import asyncio
from dataclasses import asdict
import re

from sqlalchemy import text

from app.services.activitykit_runtime import RuntimePolicy, run_activitykit_page
from app.services.durable_snapshots import read_snapshot, publish_snapshot_in_txn
from app.tasks.task_checkpoint import advisory_lock_key
from app.utils.durable_state import DurableEnvelope

IDENTITY = "activitykit:runtime-cursor"
SCHEMA = "activitykit-runtime/v1"
TASK = "activitykit_runtime"


async def run_serialized_page(
    engine,
    sessions,
    adapter,
    worker,
    transport,
    provider_token,
    *,
    policy=RuntimePolicy()
):
    if not policy.enabled:
        return {"status": "disabled", "terminal": "skipped"}
    phase = "checkpoint_read"
    summary = {}
    try:
        # Extra time is for bounded lock/read/checkpoint operations, not more
        # delivery. The page retains its own independent run and item deadlines.
        async with asyncio.timeout(policy.run_seconds + 15):
            async with engine.begin() as conn:
                acquired = (
                    await conn.execute(
                        text("SELECT pg_try_advisory_xact_lock(:key)"),
                        {"key": advisory_lock_key(TASK)},
                    )
                ).scalar_one()
                if not acquired:
                    return {"status": "busy", "terminal": "skipped"}
                read = await read_snapshot(
                    conn, IDENTITY, expected_version=SCHEMA, max_age_s=float("inf")
                )
                if read.status == "missing":
                    after, generation = "", 0
                elif read.ok and read.envelope is not None:
                    after = read.envelope.payload.get("after")
                    generation = read.envelope.generation
                    if not isinstance(after, str) or (
                        after and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", after)
                    ):
                        raise ValueError("Invalid cursor")
                else:
                    # Unreadable/malformed is never treated as an empty store.
                    raise ValueError("Unavailable cursor")
                phase = "delivery"
                result = await run_activitykit_page(
                    sessions,
                    adapter,
                    worker,
                    transport,
                    provider_token,
                    policy=policy,
                    after=after,
                )
                summary = asdict(result)
                summary.pop("next_cursor")  # No registration identity in task logs.
                phase = "checkpoint_write"
                envelope = DurableEnvelope.build(
                    identity=IDENTITY,
                    schema_version=SCHEMA,
                    # Increment under the lock; wall-clock rollback must not
                    # prevent a later fair cursor from being committed.
                    generation=generation + 1,
                    payload={"after": result.next_cursor, "page_status": result.status},
                    source=TASK,
                )
                write = await publish_snapshot_in_txn(conn, envelope)
                if write.get("status") != "ok":
                    raise ValueError("Cursor did not commit")
            # Do not report durability until engine.begin has actually committed.
            summary["checkpoint_committed"] = True
            summary["terminal"] = (
                "complete" if result.status == "complete" else "partial"
            )
            return summary
    except asyncio.CancelledError:
        raise
    except Exception:
        # SQL/transport exceptions can contain credentials. Only fixed status
        # text and counts leave this boundary; no false success after commit loss.
        return {
            **summary,
            "status": phase + "_failed",
            "terminal": "failed",
            "checkpoint_committed": False,
        }
