"""Storage half of the Queue 298 durable-state boundary (#1512).

``app.utils.durable_state`` holds the CONTRACT (pure, table-driven testable).
This module is the only thing that touches the substrate: PostgreSQL, which
C117 established is the sole already-provisioned cross-process durable store —
no generic state table, repository adapter, or object-store dependency existed,
and the domain JSONB tables must not be repurposed.

Two operations, both fail-honest:

* :func:`publish_snapshot` — atomic, generation-guarded replace. One statement,
  no delete, so the prior last-good survives every failure mode.
* :func:`read_snapshot` — returns a typed :class:`EnvelopeRead`, never raises at
  the caller, and never lets a database problem look like "never ran".

Latency note: these rows are single-key primary-key lookups of a payload that is
already bounded (the calibration build is the largest at a few hundred KB), and
the read sits BEHIND the Redis/process accelerators on the hot path — it is only
paid when the fast tiers have already failed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.durable_state import (
    DEFAULT_MAX_AGE_S,
    DurableEnvelope,
    EnvelopeRead,
    canonical_json,
    decode_envelope,
    failed_read,
)

logger = logging.getLogger(__name__)

TIER_DURABLE = "durable"

# Bound the durable read so a wedged database can never hold the public page the
# way an unbounded Redis call used to (gotcha #39's lesson, applied to the new
# substrate). Deliberately short: this tier exists to answer fast or get out of
# the way of the next one.
DURABLE_READ_TIMEOUT_MS = 2000
DURABLE_WRITE_TIMEOUT_MS = 5000


_UPSERT_SQL = text(
    """
    INSERT INTO durable_state_snapshots
        (identity, schema_version, generation, generated_at, payload,
         checksum, complete, source, updated_at)
    VALUES
        (:identity, :schema_version, :generation, :generated_at,
         CAST(:payload AS jsonb), :checksum, :complete, :source, NOW())
    ON CONFLICT (identity) DO UPDATE SET
        schema_version = EXCLUDED.schema_version,
        generation     = EXCLUDED.generation,
        generated_at   = EXCLUDED.generated_at,
        payload        = EXCLUDED.payload,
        checksum       = EXCLUDED.checksum,
        complete       = EXCLUDED.complete,
        source         = EXCLUDED.source,
        updated_at     = NOW()
    WHERE durable_state_snapshots.generation <= EXCLUDED.generation
    RETURNING generation
    """
)
# ^ The WHERE on DO UPDATE is the whole atomicity story. A concurrent or delayed
# writer carrying an OLDER generation matches the conflict, fails the predicate,
# and writes nothing — the newer good copy stays. ``<=`` (not ``<``) keeps an
# idempotent republish of the same generation working, which retries need.
# CAST(:payload AS jsonb) rather than ``:payload::jsonb``: asyncpg drops a bind
# param immediately followed by a ``::`` cast.

_SELECT_SQL = text(
    """
    SELECT identity, schema_version, generation, generated_at,
           payload, checksum, complete, source
    FROM durable_state_snapshots
    WHERE identity = :identity
    """
)


async def publish_snapshot(db: AsyncSession, envelope: DurableEnvelope) -> dict:
    """Atomically replace ``envelope.identity`` if ours is the newer generation.

    Returns a stage dict — ``{"status": "ok"|"superseded"|"error", ...}``.
    ``superseded`` means a newer generation already sits there: the durability
    requirement IS satisfied (a good copy exists), so it counts as success for
    the publication contract; it is reported distinctly so an operator can see
    a writer racing behind.

    Never raises: the caller decides what a failed durable write means for task
    success via ``durable_state.evaluate_publication``.
    """
    try:
        await db.execute(
            text(f"SET LOCAL statement_timeout = {DURABLE_WRITE_TIMEOUT_MS}")
        )
        result = await db.execute(
            _UPSERT_SQL,
            {
                "identity": envelope.identity,
                "schema_version": envelope.schema_version,
                "generation": envelope.generation,
                "generated_at": envelope.generated_at,
                "payload": canonical_json(envelope.payload),
                "checksum": envelope.checksum,
                "complete": envelope.complete,
                "source": envelope.source,
            },
        )
        written = result.scalar_one_or_none()
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — classified for the caller, not swallowed
        logger.warning(
            "durable publish failed for %s (generation %s): %s",
            envelope.identity, envelope.generation, exc,
        )
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001 — rollback failure must not mask the cause
            pass
        return {
            "status": "error",
            "identity": envelope.identity,
            "generation": envelope.generation,
            "error_class": exc.__class__.__name__,
            "error": str(exc)[:200],
        }

    if written is None:
        return {
            "status": "superseded",
            "identity": envelope.identity,
            "generation": envelope.generation,
        }
    return {
        "status": "ok",
        "identity": envelope.identity,
        "generation": envelope.generation,
    }


async def publish_snapshot_standalone(envelope: DurableEnvelope) -> dict:
    """:func:`publish_snapshot` on its own short-lived task session.

    The sentinel producers persist their scorecard at the very end of a long
    async run, well after any request/session scope; giving each one its own
    bounded session keeps the durable write independent of whatever state the
    producer's own session is in.
    """
    from app.tasks.base import get_task_session

    try:
        async with get_task_session() as db:
            return await publish_snapshot(db, envelope)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "durable publish could not open a session for %s: %s", envelope.identity, exc
        )
        return {
            "status": "error",
            "identity": envelope.identity,
            "generation": envelope.generation,
            "error_class": exc.__class__.__name__,
            "error": str(exc)[:200],
        }


async def read_snapshot(
    db: AsyncSession,
    identity: str,
    *,
    expected_version: Optional[str] = None,
    max_age_s: float = DEFAULT_MAX_AGE_S,
    now: Optional[datetime] = None,
) -> EnvelopeRead:
    """Read + classify the durable envelope for ``identity``.

    A database failure is ``unavailable`` (UNKNOWN), an absent row is
    ``missing`` ("genuinely never published"), and a row that fails checksum,
    version, completeness, or the age bound is typed as such. Only ``ok`` may be
    served.
    """
    try:
        await db.execute(
            text(f"SET LOCAL statement_timeout = {DURABLE_READ_TIMEOUT_MS}")
        )
        row = (await db.execute(_SELECT_SQL, {"identity": identity})).mappings().first()
    except Exception as exc:  # noqa: BLE001
        return failed_read(TIER_DURABLE, exc)

    if row is None:
        return EnvelopeRead(status="missing", tier=TIER_DURABLE)

    generated_at = row["generated_at"]
    if isinstance(generated_at, datetime) and generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    raw: dict[str, Any] = {
        "identity": row["identity"],
        "schema_version": row["schema_version"],
        "generation": int(row["generation"]),
        "generated_at": generated_at,
        "payload": row["payload"],
        "checksum": row["checksum"],
        "complete": bool(row["complete"]),
        "source": row["source"],
    }
    return decode_envelope(
        raw,
        tier=TIER_DURABLE,
        expected_version=expected_version,
        max_age_s=max_age_s,
        now=now,
    )


async def read_snapshot_standalone(
    identity: str,
    *,
    expected_version: Optional[str] = None,
    max_age_s: float = DEFAULT_MAX_AGE_S,
) -> EnvelopeRead:
    """:func:`read_snapshot` on its own session, for callers outside a request."""
    from app.tasks.base import get_task_session

    try:
        async with get_task_session() as db:
            return await read_snapshot(
                db, identity, expected_version=expected_version, max_age_s=max_age_s
            )
    except Exception as exc:  # noqa: BLE001
        return failed_read(TIER_DURABLE, exc)


# --- Sentinel evidence -------------------------------------------------------
#
# Every sentinel persisted its scorecard the same way: one 14-day Redis SETEX
# inside a try/except that logged and moved on. On a 49.5/50MB allkeys-lru
# instance the TTL is irrelevant — LRU evicts the key — and because the write
# failure was swallowed, `_tracked_run` recorded a healthy run whose evidence no
# longer existed. Both halves are fixed here, once, for every family.

#: Envelope version for sentinel scorecards. Bump when the scorecard contract
#: changes in a way an older reader must refuse.
SENTINEL_SCHEMA_VERSION = "v1"

#: Sentinel evidence is expected to persist between runs (daily/weekly beats) and
#: is only ever served as explicitly-dated last-known state, so it gets a longer
#: bound than the hourly calibration payload.
SENTINEL_MAX_AGE_S = 30 * 86400

SENTINEL_REDIS_TTL_S = 14 * 86400


async def publish_sentinel_evidence(
    *,
    identity: str,
    redis_key: str,
    stats: dict,
    source: str,
    ttl_s: int = SENTINEL_REDIS_TTL_S,
) -> dict:
    """Durable-first persistence of one sentinel scorecard.

    Writes the durable row, and only then the Redis accelerator — so the volatile
    copy can never lead the durable one. Returns a stage dict; the caller decides
    whether the run may report success (it may not, if the durable write failed).
    """
    import json as _json

    from app.utils.durable_state import DurableEnvelope, parse_generated_at_field

    envelope = DurableEnvelope.build(
        identity=identity,
        schema_version=SENTINEL_SCHEMA_VERSION,
        payload=_json.loads(_json.dumps(stats, default=str)),
        generated_at=parse_generated_at_field(stats),
        source=source,
    )
    durable = await publish_snapshot_standalone(envelope)
    stages: dict = {
        "durable": durable["status"],
        "durable_generation": envelope.generation,
        "identity": identity,
    }
    if durable.get("error"):
        stages["durable_error"] = durable["error"]

    if durable["status"] in ("ok", "superseded"):
        try:
            from app.tasks.redis_state import get_redis_client

            get_redis_client().setex(
                redis_key, ttl_s, _json.dumps(envelope.payload, default=str)
            )
            stages["volatile"] = "ok"
        except Exception as exc:  # noqa: BLE001 — accelerator only, never fatal
            stages["volatile"] = "error"
            stages["volatile_error"] = str(exc)[:200]
            logger.warning("%s: Redis accelerator write failed: %s", identity, exc)
    else:
        # Skipping the accelerator is deliberate: a volatile copy with no durable
        # backing is a torn pair, which readers must distrust anyway.
        stages["volatile"] = "not_attempted"
        logger.error(
            "%s: durable evidence write FAILED (%s) — run cannot report success",
            identity, durable.get("error") or durable["status"],
        )
    return stages


async def read_sentinel_evidence(
    db: AsyncSession,
    *,
    identity: str,
    redis_key: str,
    max_age_s: float = SENTINEL_MAX_AGE_S,
) -> Optional[dict]:
    """Read one sentinel's evidence across both tiers, fail-honest.

    Returns the stored scorecard verbatim (so every existing consumer of these
    rails is unaffected) with an additive ``provenance`` block, or ``None`` when
    neither tier holds anything trustworthy — in which case the caller keeps its
    existing typed classification.

    The win this delivers: when Redis has EVICTED the scorecard (the #1512
    observation — 49.5/50MB, allkeys-lru) or cannot be read at all, the retained
    durable verdict is served with an explicit dated provenance block instead of
    the rail claiming the sentinel never ran.
    """
    from app.utils import health_reads
    from app.utils.durable_state import (
        MISSING,
        UNKNOWN,
        DurableEnvelope,
        EnvelopeRead,
        SOURCE_DURABLE,
        SOURCE_VOLATILE,
        checksum_payload,
        resolve,
    )

    # Volatile tier: the raw scorecard as the sentinels have always written it.
    raw = health_reads.read_json_key(redis_key)
    if raw.ok:
        payload = raw.value
        stamp = _parse_stats_stamp(payload)
        volatile = EnvelopeRead(
            status="ok" if stamp else MISSING,
            tier="volatile",
            envelope=(
                DurableEnvelope(
                    identity=identity,
                    schema_version=SENTINEL_SCHEMA_VERSION,
                    generation=int(stamp.timestamp() * 1000),
                    generated_at=stamp,
                    payload=payload,
                    checksum=checksum_payload(payload),
                    complete=True,
                    source="redis",
                )
                if stamp
                else None
            ),
        )
    elif raw.missing:
        volatile = EnvelopeRead(status=MISSING, tier="volatile")
    else:
        volatile = EnvelopeRead(
            status="unavailable" if raw.unavailable else "malformed",
            tier="volatile",
            error_class=raw.error_class,
            error=raw.error,
        )

    durable = await read_snapshot(
        db, identity, expected_version=SENTINEL_SCHEMA_VERSION, max_age_s=max_age_s
    )

    resolution = resolve(
        volatile=volatile,
        durable=durable,
        process=EnvelopeRead(status=MISSING, tier="process"),
        # A web dyno is not the process that produced this; it never has a warm
        # copy to claim, so process memory is never the durability story here.
        fresh_process=True,
    )

    reads = {"volatile": volatile, "durable": durable}
    if not resolution.servable:
        # Nothing trustworthy in either tier. Return None so the caller applies
        # its existing classification (bounded 503 for a dependency loss,
        # ``no_run_cached`` for a genuine absence) — this tier only ever ADDS a
        # retained answer, it never redefines what "no answer" means.
        return None

    body = dict(resolution.envelope.payload) if isinstance(resolution.envelope.payload, dict) else {
        "value": resolution.envelope.payload
    }
    body["provenance"] = resolution.envelope.provenance(served_from=resolution.source)
    body["provenance"]["tiers"] = {k: r.as_status() for k, r in reads.items()}
    if resolution.errors:
        # A torn pair still serves the durable copy, but it must say so.
        body["provenance"]["contract_errors"] = resolution.errors
        body["provenance"]["health"] = UNKNOWN
    if resolution.source == SOURCE_DURABLE and volatile.missing:
        body["provenance"]["note"] = (
            "served from the durable store — the Redis copy is absent (evicted or "
            "never written); this is last-known state, not a fresh run"
        )
    elif resolution.source == SOURCE_VOLATILE:
        body["provenance"]["note"] = "served from the Redis accelerator"
    return body


def _parse_stats_stamp(payload: Any):
    """A sentinel scorecard's own ``generated_at``, or None."""
    from app.utils.durable_state import parse_generated_at_field

    if not isinstance(payload, dict):
        return None
    try:
        return parse_generated_at_field(payload, default_now=False)
    except Exception:  # noqa: BLE001
        return None
