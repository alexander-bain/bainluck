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

_CAS_CREATE_SQL = text(
    """
    INSERT INTO durable_state_snapshots
        (identity, schema_version, generation, generated_at, payload,
         checksum, complete, source, updated_at)
    VALUES
        (:identity, :schema_version, :generation, :generated_at,
         CAST(:payload AS jsonb), :checksum, :complete, :source, NOW())
    ON CONFLICT (identity) DO NOTHING
    RETURNING generation
    """
)
# ^ The `expected_generation is None` arm: the caller read `missing`, so it is
# creating the row. If somebody created it first, DO NOTHING returns no row and
# the caller is told `cas-miss` — it must re-read, because the fold it built on
# "there is nothing here" is now wrong.

_CAS_UPSERT_SQL = text(
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
    WHERE durable_state_snapshots.generation = :expected_generation
    RETURNING generation
    """
)
# ^ COMPARE-AND-SWAP (CERT-955). `_UPSERT_SQL`'s `stored <= EXCLUDED` answers
# "is my copy at least as new as yours", which is right for a snapshot every
# writer builds identically — the freshest wins and an idempotent republish of
# the same generation still lands.
#
# It is WRONG for a read-modify-write. Two writers that both read generation `g`
# both propose `g+1`; the first lands, and the second passes `stored <=
# proposed` on EQUALITY, returns `ok`, and overwrites a fold it never read. The
# day the first writer added is gone and both callers were told they succeeded.
#
# The predicate here is equality against the generation the caller ACTUALLY
# READ, so exactly one of those two writers commits and the other is told
# `cas-miss` and must re-read. `:expected_generation` is the read's generation,
# never the proposed one — passing the proposed value restores the bug in a form
# that still reads like a CAS.

#: A CAS write that did not land because the row moved under the caller. Not
#: `superseded` (which means "a good copy of this same thing is already there"):
#: a read-modify-write's loser has NOT been stored by anybody, and its caller has
#: to fold again.
STATUS_CAS_MISS = "cas-miss"


_SELECT_SQL = text(
    """
    SELECT identity, schema_version, generation, generated_at,
           payload, checksum, complete, source
    FROM durable_state_snapshots
    WHERE identity = :identity
    """
)

_OWNED_UPSERT_SQL = text(
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
      AND durable_state_snapshots.payload ->> :owner_key = :owner
    RETURNING generation
    """
)
# ^ CREATE-WITHOUT-OVERWRITE (CERT-856). The generation guard alone answers
# "is my copy newer" — the right question for a snapshot whose identity names a
# THING (one calibration bank, one sentinel scorecard), where every writer is
# producing the same thing and the freshest wins. It is the wrong question for a
# record whose identity names an EVENT: two applies that collide on one identity
# are not two versions of one receipt, they are two different receipts, and
# letting the later one win destroys the earlier one's only proof of what it did.
#
# The extra predicate says a row may only be replaced by the invocation that
# WROTE it. An absent conflicting row is created (the INSERT arm, no predicate);
# a row belonging to somebody else — or to nobody, because it predates owners —
# fails ``payload ->> :owner_key = :owner`` (NULL is not equal to anything) and
# is left exactly as it stands. Fail-closed by construction: the way to lose the
# guard is to delete it, not to forget a case.

_SELECT_OWNER_SQL = text(
    """
    SELECT generation, payload ->> :owner_key AS owner
    FROM durable_state_snapshots
    WHERE identity = :identity
    """
)

#: A write refused because the identity already holds SOMEBODY ELSE'S record.
#: Deliberately not folded into ``superseded``: superseded means "a good copy of
#: this same thing is already there, durability is satisfied", and occupied means
#: the exact opposite — your record was not stored and the one on file is not
#: about your run.
STATUS_OCCUPIED = "occupied"


async def publish_snapshot_in_txn(db: AsyncSession, envelope: DurableEnvelope) -> dict:
    """Stage the row in the CALLER'S open transaction. Never commits, never
    rolls back.

    Same stage dict as :func:`publish_snapshot`, and the same never-raises
    contract — the difference is only who ends the transaction. A caller that
    has just written data and needs the record of that write to be durable
    *with* it uses this and then commits ONCE: the data and its receipt then
    land together or not at all, so no crash can leave a durable change whose
    undo record is empty (CERT-851).

    The caller owns the rollback on a non-``ok`` status, because only the caller
    knows what else is in the transaction.
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
    except Exception as exc:  # noqa: BLE001 — classified for the caller, not swallowed
        logger.warning(
            "durable publish failed for %s (generation %s): %s",
            envelope.identity, envelope.generation, exc,
        )
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
    stage = await publish_snapshot_in_txn(db, envelope)
    if stage["status"] == "error":
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001 — rollback failure must not mask the cause
            pass
        return stage

    try:
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
    return stage


async def publish_owned_snapshot_in_txn(
    db: AsyncSession,
    envelope: DurableEnvelope,
    *,
    owner_key: str,
    owner: str,
) -> dict:
    """:func:`publish_snapshot_in_txn`, but only ``owner`` may replace the row.

    Same never-commits / never-rolls-back / never-raises contract. The one added
    outcome is ``occupied``: the identity already holds a record whose
    ``payload[owner_key]`` is not ``owner``, so nothing was written and the row
    on file is untouched.

    CERT-856. Two applies deriving the same identity in the same instant is not
    a hypothetical — the callers salt their identity with a per-invocation token
    now, but a receipt that can be silently replaced is one bad salt away from
    being unrestorable, and the population that would notice is "the operator
    reversing a production write". So the store refuses the replacement rather
    than the caller promising never to ask for one.
    """
    if not owner:
        # An unowned write to an owned identity cannot be told apart from a
        # legacy row on the way back in, so it is refused rather than stored.
        return {
            "status": "error",
            "identity": envelope.identity,
            "generation": envelope.generation,
            "error_class": "ValueError",
            "error": "owned publish requires a non-empty owner",
        }
    params = {
        "identity": envelope.identity,
        "schema_version": envelope.schema_version,
        "generation": envelope.generation,
        "generated_at": envelope.generated_at,
        "payload": canonical_json(envelope.payload),
        "checksum": envelope.checksum,
        "complete": envelope.complete,
        "source": envelope.source,
        "owner_key": owner_key,
        "owner": owner,
    }
    try:
        await db.execute(
            text(f"SET LOCAL statement_timeout = {DURABLE_WRITE_TIMEOUT_MS}")
        )
        result = await db.execute(_OWNED_UPSERT_SQL, params)
        written = result.scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 — classified for the caller, not swallowed
        logger.warning(
            "durable owned publish failed for %s (generation %s): %s",
            envelope.identity, envelope.generation, exc,
        )
        return {
            "status": "error",
            "identity": envelope.identity,
            "generation": envelope.generation,
            "error_class": exc.__class__.__name__,
            "error": str(exc)[:200],
        }

    if written is not None:
        return {
            "status": "ok",
            "identity": envelope.identity,
            "generation": envelope.generation,
        }

    # Nothing was written. TWO different reasons can put us here and the caller
    # gets told which: our generation lost the race (``superseded``), or the row
    # is somebody else's (``occupied``). A read that itself fails resolves to
    # ``occupied`` — "I could not establish that this record is mine" must never
    # read as "it is mine".
    stage = {
        "status": STATUS_OCCUPIED,
        "identity": envelope.identity,
        "generation": envelope.generation,
    }
    try:
        row = (
            await db.execute(
                _SELECT_OWNER_SQL,
                {"identity": envelope.identity, "owner_key": owner_key},
            )
        ).mappings().first()
    except Exception as exc:  # noqa: BLE001 — the refusal stands either way
        logger.warning(
            "durable owned publish could not classify the refusal for %s: %s",
            envelope.identity, exc,
        )
        stage["owner"] = None
        return stage
    if row is not None:
        stage["owner"] = row["owner"]
        if row["owner"] == owner:
            stage["status"] = "superseded"
    return stage


async def publish_owned_snapshot_standalone(
    envelope: DurableEnvelope, *, owner_key: str, owner: str
) -> dict:
    """:func:`publish_owned_snapshot_in_txn` on its own short-lived session."""
    from app.tasks.base import get_task_session

    try:
        async with get_task_session() as db:
            stage = await publish_owned_snapshot_in_txn(
                db, envelope, owner_key=owner_key, owner=owner
            )
            if stage["status"] == "ok":
                await db.commit()
            else:
                # Nothing of ours landed; leave the transaction clean rather
                # than committing a no-op over somebody else's record.
                await db.rollback()
            return stage
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "durable owned publish could not complete for %s: %s",
            envelope.identity, exc,
        )
        return {
            "status": "error",
            "identity": envelope.identity,
            "generation": envelope.generation,
            "error_class": exc.__class__.__name__,
            "error": str(exc)[:200],
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


async def publish_cas_snapshot(
    db: AsyncSession, envelope: DurableEnvelope, *, expected_generation: Optional[int]
) -> dict:
    """Compare-and-swap publish: land only if the row is still where we read it.

    For read-modify-write callers — the ones whose payload is a FOLD of what
    they read rather than an independent rebuild. `expected_generation` is the
    generation the caller read; `None` means it read `missing` and is creating
    the row, which then must not clobber a row somebody else created meanwhile.

    Returns the same stage dict shape as :func:`publish_snapshot`, with
    :data:`STATUS_CAS_MISS` where that one would say `superseded`.
    """
    params = {
        "identity": envelope.identity,
        "schema_version": envelope.schema_version,
        "generation": envelope.generation,
        "generated_at": envelope.generated_at,
        "payload": canonical_json(envelope.payload),
        "checksum": envelope.checksum,
        "complete": envelope.complete,
        "source": envelope.source,
    }
    sql = _CAS_CREATE_SQL if expected_generation is None else _CAS_UPSERT_SQL
    if expected_generation is not None:
        params["expected_generation"] = int(expected_generation)

    try:
        await db.execute(
            text(f"SET LOCAL statement_timeout = {DURABLE_WRITE_TIMEOUT_MS}")
        )
        result = await db.execute(sql, params)
        written = result.scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 — classified for the caller
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning(
            "durable CAS publish failed for %s (expected %s): %s",
            envelope.identity, expected_generation, exc,
        )
        return {
            "status": "error",
            "identity": envelope.identity,
            "generation": envelope.generation,
            "error_class": exc.__class__.__name__,
            "error": str(exc)[:200],
        }

    if written is None:
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {
            "status": STATUS_CAS_MISS,
            "identity": envelope.identity,
            "generation": envelope.generation,
            "expected_generation": expected_generation,
        }

    try:
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {
            "status": "error",
            "identity": envelope.identity,
            "generation": envelope.generation,
            "error_class": exc.__class__.__name__,
            "error": str(exc)[:200],
        }
    return {
        "status": "ok",
        "identity": envelope.identity,
        "generation": envelope.generation,
    }


async def publish_cas_snapshot_in_txn(
    db: AsyncSession, envelope: DurableEnvelope, *, expected_generation: Optional[int]
) -> dict:
    """Compare-and-swap, staged in the CALLER'S open transaction. Never commits,
    never rolls back.

    :func:`publish_cas_snapshot` is to this what :func:`publish_snapshot` is to
    :func:`publish_snapshot_in_txn` — same predicate, different owner of the
    transaction. A read-modify-write caller whose fold has to land in the SAME
    transaction as the rows the fold is ABOUT needs both properties at once: the
    equality predicate on the generation it actually read, and a commit only it
    can issue. The invalidation-debt ledger is that caller (CERT-1872 put the
    debt inside the row transaction; #3191 is the fold that was still a
    read-then-write).

    On :data:`STATUS_CAS_MISS` nothing was written and the row is untouched, but
    the caller's transaction is still open and may hold row mutations the fold
    was the price of — so the ROLLBACK is the caller's, because only the caller
    knows what else is in there.
    """
    params = {
        "identity": envelope.identity,
        "schema_version": envelope.schema_version,
        "generation": envelope.generation,
        "generated_at": envelope.generated_at,
        "payload": canonical_json(envelope.payload),
        "checksum": envelope.checksum,
        "complete": envelope.complete,
        "source": envelope.source,
    }
    sql = _CAS_CREATE_SQL if expected_generation is None else _CAS_UPSERT_SQL
    if expected_generation is not None:
        params["expected_generation"] = int(expected_generation)

    try:
        await db.execute(
            text(f"SET LOCAL statement_timeout = {DURABLE_WRITE_TIMEOUT_MS}")
        )
        result = await db.execute(sql, params)
        written = result.scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 — classified for the caller
        logger.warning(
            "durable in-txn CAS publish failed for %s (expected %s): %s",
            envelope.identity, expected_generation, exc,
        )
        return {
            "status": "error",
            "identity": envelope.identity,
            "generation": envelope.generation,
            "error_class": exc.__class__.__name__,
            "error": str(exc)[:200],
        }

    if written is None:
        return {
            "status": STATUS_CAS_MISS,
            "identity": envelope.identity,
            "generation": envelope.generation,
            "expected_generation": expected_generation,
        }
    return {
        "status": "ok",
        "identity": envelope.identity,
        "generation": envelope.generation,
    }


async def publish_cas_snapshot_standalone(
    envelope: DurableEnvelope, *, expected_generation: Optional[int]
) -> dict:
    """:func:`publish_cas_snapshot` on its own short-lived task session."""
    from app.tasks.base import get_task_session

    try:
        async with get_task_session() as db:
            return await publish_cas_snapshot(
                db, envelope, expected_generation=expected_generation
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "durable CAS publish could not open a session for %s: %s",
            envelope.identity, exc,
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
