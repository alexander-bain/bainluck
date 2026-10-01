"""#6317 — candidate-first rollover for the /calibration main artifact.

WHY THIS EXISTS. A population-version bump used to be a dark window by
construction. The route expected the version in the code it ran
(``CALIBRATION_POPULATION_VERSION``), and every cached copy carried the version
of the artifact last built. So deploying q272 to the web before a q272 artifact
existed made the live q271 artifact ``wrong_version`` at every tier. Both
builds also published to ONE durable identity (``calibration:main``) and ONE
unversioned Redis pair. Publishing q272 first would therefore have replaced the
artifact q271 readers were still being served. Reversing the deploy order
fixes neither half.

THE MODEL — one coherent rule, not a mix:

* **Every version has its own namespace** (:func:`namespace_for`). The legacy
  shared keys belong to :data:`LEGACY_NAMESPACE_VERSION` alone; every later
  version writes ``calibration:main:<version>`` and its own Redis pair. No
  version ever writes another version's keys, so a reader holding a slightly
  stale selection can never read bytes of a version it did not expect.
* **One durable record names the ACTIVE namespace** (:data:`SELECTION_IDENTITY`),
  and the route serves only that. Its absence means the legacy incumbent —
  never "the newest version" and never "the version in this code".
* **Version keys are overwritten, not immutable.** A later complete,
  publish-gated build of the SAME active version advances that namespace's key
  in the ordinary way. The selection pins the activated generation as a
  MINIMUM admissible generation, never an exact one, so a routine hourly
  publish can never read as a wrong-generation outage.
* **Activation is one short transaction** (:func:`activate_candidate`). It
  locks the selection row, re-reads the incumbent artifact under ``FOR SHARE``
  (so a concurrent incumbent publisher waits rather than moving the baseline
  under the check), re-runs the artifact-only gate against that row, confirms
  the staged candidate row is the one the build wrote, and compare-and-swaps
  the selection on the generation actually read. Candidate compute stays
  outside it. A ``cas-miss`` is NOT activation, whatever the independent
  snapshot write's ``superseded`` means elsewhere.

Durable is the truth and Redis is an accelerator, here as everywhere in this
pipeline: the selection's Redis copy is written only after the durable commit,
carries a short TTL so a failed refresh cannot pin readers for long, and is
re-written from durable on every build.

The predicate fingerprint is PINNED as provenance (which method was accepted at
activation) and is re-checked between the staged row and the build that wrote
it. It is not required to stay equal for later same-version publishes. The
publish gate already judges a same-version predicate move (strict band, #1955).
Hash equality here would turn every non-bump predicate edit into an outage.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: The durable record that names the active artifact.
SELECTION_IDENTITY = "calibration:active_selection"
SELECTION_SCHEMA = "calibration-active-selection/v1"

#: The selection's accelerator. Bounded TTL on purpose: every build re-writes it
#: from durable, and if the post-activation write fails the old copy is deleted
#: (and in any case expires), so readers fall back to the durable record instead
#: of following an old selection for the life of the key.
SELECTION_REDIS_KEY = "bainluck:calibration:active_selection"
SELECTION_REDIS_TTL_S = 3900  # one hourly beat + margin; every build re-writes it

#: How long a route process may reuse a selection it resolved.
SELECTION_PROCESS_TTL_S = 60.0

#: The version the legacy shared keys hold. Permanent: q271 is the last version
#: that ever writes them, and every later version has its own namespace.
LEGACY_NAMESPACE_VERSION = "q271"
LEGACY_IDENTITY = "calibration:main"
LEGACY_MAIN_KEY = "bainluck:calibration:main"
LEGACY_LAST_GOOD_KEY = "bainluck:calibration:main:last_good"

_VERSION_RE = re.compile(r"^q[0-9]{3,4}$")

#: Selection origins.
ORIGIN_DEFAULT = "default"  # no record yet: the legacy incumbent, in memory only
ORIGIN_BOOTSTRAP = "bootstrap"  # recorded FROM a verified legacy incumbent
ORIGIN_ACTIVATION = "activation"  # a gated candidate was promoted

#: Selection read statuses.
READ_OK = "ok"
READ_MISSING = "missing"
READ_MALFORMED = "malformed"
READ_UNAVAILABLE = "unavailable"

#: Activation outcomes. Only ``activated`` changes what readers see.
ACTIVATED = "activated"
NOT_ACTIVATED = "not_activated"


@dataclass(frozen=True)
class Namespace:
    """Where one population version's main artifact lives."""

    version: str
    identity: str
    main_key: str
    last_good_key: str


def namespace_for(version: str) -> Namespace:
    """The keys ``version`` publishes to. Pure, and the only derivation."""
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        raise ValueError(f"not a population version: {version!r}")
    if version == LEGACY_NAMESPACE_VERSION:
        return Namespace(version, LEGACY_IDENTITY, LEGACY_MAIN_KEY, LEGACY_LAST_GOOD_KEY)
    return Namespace(
        version,
        f"calibration:main:{version}",
        f"bainluck:calibration:main:{version}",
        f"bainluck:calibration:main:{version}:last_good",
    )


@dataclass(frozen=True)
class ActiveSelection:
    """Which artifact the page serves, and the oldest generation it may serve."""

    version: str
    min_generation: int
    origin: str
    predicate_fingerprint: Optional[str] = None
    selected_at: Optional[str] = None
    #: What was active before this record (activation only), for the audit trail.
    replaced: Optional[dict] = None
    #: The durable record's own generation; ``None`` for the in-memory default.
    record_generation: Optional[int] = None

    @property
    def namespace(self) -> Namespace:
        return namespace_for(self.version)

    def admits_generation(self, generation: Optional[int]) -> bool:
        """May an artifact of this generation be served under this selection?"""
        if self.min_generation <= 0:
            return True
        return isinstance(generation, int) and generation >= self.min_generation

    def admits_payload(self, payload: Any) -> bool:
        """The same floor, applied to a Redis copy via its own build stamp."""
        if self.min_generation <= 0:
            return True
        return self.admits_generation(payload_generation(payload))

    def to_payload(self) -> dict:
        ns = self.namespace
        return {
            "active_version": self.version,
            "artifact_identity": ns.identity,
            "redis_main_key": ns.main_key,
            "redis_last_good_key": ns.last_good_key,
            "min_generation": int(self.min_generation),
            "origin": self.origin,
            "predicate_fingerprint": self.predicate_fingerprint,
            "selected_at": self.selected_at,
            "replaced": self.replaced,
        }


def default_selection() -> ActiveSelection:
    """No record yet: the legacy incumbent, with no generation floor."""
    return ActiveSelection(
        version=LEGACY_NAMESPACE_VERSION, min_generation=0, origin=ORIGIN_DEFAULT
    )


def payload_generation(payload: Any) -> Optional[int]:
    """The generation a payload's own ``generated_at`` derives (as the producer's)."""
    from app.utils.durable_state import generation_for, parse_generated_at_field

    stamp = parse_generated_at_field(payload, default_now=False)
    return generation_for(stamp) if stamp is not None else None


def parse_selection(
    payload: Any, *, record_generation: Optional[int] = None
) -> Optional[ActiveSelection]:
    """Typed validation. ``None`` for anything not exactly a selection we wrote.

    Every stored key must agree with :func:`namespace_for` of the stored
    version, so a record can never point a version at another version's keys.
    """
    if not isinstance(payload, dict):
        return None
    version = payload.get("active_version")
    try:
        ns = namespace_for(version)
    except ValueError:
        return None
    if (
        payload.get("artifact_identity") != ns.identity
        or payload.get("redis_main_key") != ns.main_key
        or payload.get("redis_last_good_key") != ns.last_good_key
    ):
        return None
    min_generation = payload.get("min_generation")
    if isinstance(min_generation, bool) or not isinstance(min_generation, int):
        return None
    if min_generation < 0:
        return None
    origin = payload.get("origin")
    if origin not in (ORIGIN_BOOTSTRAP, ORIGIN_ACTIVATION):
        return None
    fingerprint = payload.get("predicate_fingerprint")
    if fingerprint is not None and not isinstance(fingerprint, str):
        return None
    replaced = payload.get("replaced")
    if replaced is not None and not isinstance(replaced, dict):
        return None
    return ActiveSelection(
        version=version,
        min_generation=min_generation,
        origin=origin,
        predicate_fingerprint=fingerprint,
        selected_at=payload.get("selected_at") if isinstance(payload.get("selected_at"), str) else None,
        replaced=replaced,
        record_generation=record_generation,
    )


@dataclass(frozen=True)
class SelectionRead:
    """One classified read of the durable selection record."""

    status: str
    selection: Optional[ActiveSelection] = None
    #: The record's generation as read — the CAS ``expected_generation``.
    generation: Optional[int] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == READ_OK


def classify_selection_envelope(read: Any) -> SelectionRead:
    """Turn an ``EnvelopeRead`` of :data:`SELECTION_IDENTITY` into a SelectionRead."""
    status = getattr(read, "status", None)
    if status == "missing":
        return SelectionRead(status=READ_MISSING)
    if status == "unavailable":
        return SelectionRead(status=READ_UNAVAILABLE, error=getattr(read, "error", None))
    envelope = getattr(read, "envelope", None)
    if status != "ok" or envelope is None:
        return SelectionRead(
            status=READ_MALFORMED,
            generation=getattr(envelope, "generation", None),
            error=getattr(read, "error", None) or f"envelope {status}",
        )
    selection = parse_selection(envelope.payload, record_generation=envelope.generation)
    if selection is None:
        return SelectionRead(
            status=READ_MALFORMED,
            generation=envelope.generation,
            error="selection payload failed validation",
        )
    return SelectionRead(status=READ_OK, selection=selection, generation=envelope.generation)


async def read_active_selection(db) -> SelectionRead:
    """The durable selection, classified. Never raises."""
    from app.services.durable_snapshots import read_snapshot

    try:
        read = await read_snapshot(
            db, SELECTION_IDENTITY, expected_version=SELECTION_SCHEMA, max_age_s=float("inf")
        )
    except Exception as exc:  # noqa: BLE001 — classified, never raised
        return SelectionRead(status=READ_UNAVAILABLE, error=str(exc)[:200])
    return classify_selection_envelope(read)


async def read_active_selection_standalone() -> SelectionRead:
    """:func:`read_active_selection` on its own task session."""
    from app.tasks.base import get_task_session

    try:
        async with get_task_session() as db:
            return await read_active_selection(db)
    except Exception as exc:  # noqa: BLE001
        return SelectionRead(status=READ_UNAVAILABLE, error=str(exc)[:200])


def selection_envelope(selection: ActiveSelection, *, now: Optional[datetime] = None):
    """The durable envelope for a selection record."""
    from app.utils.durable_state import DurableEnvelope

    stamp = now or datetime.now(timezone.utc)
    return DurableEnvelope.build(
        identity=SELECTION_IDENTITY,
        schema_version=SELECTION_SCHEMA,
        payload=selection.to_payload(),
        generated_at=stamp,
        source="precompute_calibration",
    )


def accelerate_selection(rc, selection: ActiveSelection, record_generation: int) -> str:
    """Write the selection's Redis copy. Call ONLY after the durable commit."""
    body = dict(selection.to_payload())
    body["record_generation"] = int(record_generation)
    try:
        rc.set(SELECTION_REDIS_KEY, json.dumps(body), ex=SELECTION_REDIS_TTL_S)
        return "ok"
    except Exception as exc:  # noqa: BLE001 — accelerator only; durable is the truth
        logger.warning("calibration selection: Redis accelerator SET failed: %s", exc)
    try:
        # A copy we could not replace must not outlive the record it described.
        rc.delete(SELECTION_REDIS_KEY)
        return "error_deleted"
    except Exception:  # noqa: BLE001
        return "error"


def active_namespace_sync(rc) -> Namespace:
    """For synchronous out-of-request readers (admin views): the selection's
    Redis copy, else the legacy namespace. No database work."""
    try:
        raw = rc.get(SELECTION_REDIS_KEY)
        parsed = parse_selection(json.loads(raw)) if raw else None
        if parsed is not None:
            return parsed.namespace
    except Exception:  # noqa: BLE001
        pass
    return default_selection().namespace


async def resolve_namespace_for_worker(*, deadline_ms: int = 5000) -> tuple[Namespace, str]:
    """For async workers that grade the PUBLISHED artifact (the twin): the
    active namespace and where it came from — Redis copy, durable record, or
    the legacy default when neither can be read. Never raises."""
    from app.utils import request_cache as _rc

    try:
        rc = await _rc.get_shared_async_redis()
        res = await _rc.bounded_redis_call(
            lambda: rc.get(SELECTION_REDIS_KEY), deadline_ms=deadline_ms
        )
        if res.is_ok and res.value:
            parsed = parse_selection(json.loads(res.value))
            if parsed is not None:
                return parsed.namespace, "redis"
    except Exception:  # noqa: BLE001
        pass
    read = await read_active_selection_standalone()
    if read.ok:
        return read.selection.namespace, "durable"
    return default_selection().namespace, f"default_{read.status}"


def candidate_first_protection_problems(current_version: str, outgoing_version: str) -> list[str]:
    """Why a candidate-first rollover from ``outgoing`` to ``current`` would NOT
    keep the page lit — empty when it would. Pure; the rollover guards call it.

    Three facts carry the whole claim: the two versions publish to disjoint
    keys (so staging the new one cannot replace the old one); with no selection
    record the route serves the outgoing version (so deploying the reader first
    changes nothing); and the outgoing version is the legacy incumbent the
    bootstrap records (the only one a missing record can mean).
    """
    problems: list[str] = []
    try:
        cur, out = namespace_for(current_version), namespace_for(outgoing_version)
    except ValueError as exc:
        return [str(exc)]
    if current_version == outgoing_version:
        problems.append("a rollover needs two versions")
    shared = {cur.identity, cur.main_key, cur.last_good_key} & {
        out.identity, out.main_key, out.last_good_key
    }
    if shared:
        problems.append(f"{current_version} and {outgoing_version} share keys: {sorted(shared)}")
    if default_selection().version != outgoing_version:
        problems.append(
            f"with no selection record the route serves {default_selection().version!r}, "
            f"not the outgoing {outgoing_version!r}"
        )
    return problems


# --- Producer: bootstrap and activation --------------------------------------

_LOCK_SELECT_SQL = {
    "update": text(
        "SELECT identity, schema_version, generation, generated_at, payload, "
        "checksum, complete, source FROM durable_state_snapshots "
        "WHERE identity = :identity FOR UPDATE"
    ),
    "share": text(
        "SELECT identity, schema_version, generation, generated_at, payload, "
        "checksum, complete, source FROM durable_state_snapshots "
        "WHERE identity = :identity FOR SHARE"
    ),
}

#: Bound for the whole activation transaction's statements.
ACTIVATION_STATEMENT_TIMEOUT_MS = 10000


async def _locked_read(db, identity: str, *, lock: str, expected_version: Optional[str]):
    """Read one row under a row lock and decode it (no age bound)."""
    from app.utils.durable_state import EnvelopeRead, decode_envelope

    row = (
        await db.execute(_LOCK_SELECT_SQL[lock], {"identity": identity})
    ).mappings().first()
    if row is None:
        return EnvelopeRead(status="missing", tier="durable")
    generated_at = row["generated_at"]
    if isinstance(generated_at, datetime) and generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    return decode_envelope(
        {
            "identity": row["identity"],
            "schema_version": row["schema_version"],
            "generation": int(row["generation"]),
            "generated_at": generated_at,
            "payload": row["payload"],
            "checksum": row["checksum"],
            "complete": bool(row["complete"]),
            "source": row["source"],
        },
        tier="durable",
        expected_version=expected_version,
        max_age_s=float("inf"),
    )


def _not_activated(reason: str, **extra: Any) -> dict:
    return {"status": NOT_ACTIVATED, "reason": reason, **extra}


async def bootstrap_selection(*, legacy_read: Any, now: Optional[datetime] = None) -> dict:
    """Record the verified legacy incumbent as the active selection.

    Only ever from a legacy read that is ``ok`` under the legacy version, and
    only by CREATE (``expected_generation=None``), so a simultaneous creator —
    an activation that got there first, or another bootstrap — is never
    overwritten. The incumbent's generation becomes the floor, so its own
    artifact time and version are what keep serving.
    """
    from app.services.durable_snapshots import publish_cas_snapshot_standalone

    envelope = getattr(legacy_read, "envelope", None)
    if getattr(legacy_read, "status", None) != "ok" or envelope is None:
        return {"status": "refused", "reason": f"legacy incumbent not verified ({getattr(legacy_read, 'status', None)})"}
    payload = envelope.payload if isinstance(envelope.payload, dict) else {}
    if payload.get("population_version") != LEGACY_NAMESPACE_VERSION:
        return {"status": "refused", "reason": "legacy payload does not carry the legacy version"}
    selection = ActiveSelection(
        version=LEGACY_NAMESPACE_VERSION,
        min_generation=int(envelope.generation),
        origin=ORIGIN_BOOTSTRAP,
        predicate_fingerprint=payload.get("population_predicate_fingerprint"),
        selected_at=(now or datetime.now(timezone.utc)).isoformat(),
    )
    sel_env = selection_envelope(selection, now=now)
    stage = await publish_cas_snapshot_standalone(sel_env, expected_generation=None)
    return {"status": stage.get("status"), "selection": selection, "generation": sel_env.generation}


async def resolve_for_build(*, now: Optional[datetime] = None) -> SelectionRead:
    """The selection a build is judged against: ``ok``, ``missing`` (a true
    cold start — no record AND no legacy artifact) or a failure the caller must
    fail closed on.

    A missing record with a legacy artifact present is bootstrapped from that
    incumbent (verified under the legacy version, created only if absent) and
    re-read, so the build always proceeds from a durable record when one can
    exist.
    """
    from app.services.durable_snapshots import read_snapshot_standalone

    read = await read_active_selection_standalone()
    if read.status != READ_MISSING:
        return read
    legacy = await read_snapshot_standalone(
        LEGACY_IDENTITY, expected_version=LEGACY_NAMESPACE_VERSION, max_age_s=float("inf")
    )
    if getattr(legacy, "status", None) == "missing":
        return read
    boot = await bootstrap_selection(legacy_read=legacy, now=now)
    if boot.get("status") not in ("ok", "cas-miss"):
        return SelectionRead(
            status=READ_UNAVAILABLE,
            error=f"bootstrap {boot.get('status')}: {boot.get('reason') or boot.get('error') or ''}"[:200],
        )
    return await read_active_selection_standalone()


async def activate_candidate(
    *,
    candidate_version: str,
    candidate_generation: int,
    predicate_fingerprint: Optional[str],
    expected: SelectionRead,
    recheck: Callable[[Optional[dict]], tuple[bool, str]],
    now: Optional[datetime] = None,
    session_factory: Optional[Callable[[], Any]] = None,
) -> dict:
    """Promote a staged, gated candidate to active — or report why not.

    ``expected`` is the selection the build was gated against: ``ok`` (an
    incumbent exists) or ``missing`` with no legacy row either (a true cold
    start). ``recheck(incumbent_payload)`` is the existing artifact-only gate,
    re-run here against the incumbent row as it stands under the lock;
    ``None`` is passed only on a cold start.

    Every early exit rolls back and leaves the selection exactly as it was.
    """
    from app.services.durable_snapshots import publish_cas_snapshot_in_txn

    if session_factory is None:
        from app.tasks.base import get_task_session as session_factory  # noqa: N813

    candidate_ns = namespace_for(candidate_version)
    if expected.status == READ_OK and expected.selection is not None:
        if expected.selection.version == candidate_version:
            return _not_activated("candidate_already_active")
        incumbent_ns: Optional[Namespace] = expected.selection.namespace
    elif expected.status == READ_MISSING:
        incumbent_ns = None
    else:
        return _not_activated(f"selection_{expected.status}")

    try:
        async with session_factory() as db:
            await db.execute(
                text(f"SET LOCAL statement_timeout = {ACTIVATION_STATEMENT_TIMEOUT_MS}")
            )

            async def _abort(reason: str, **extra: Any) -> dict:
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                return _not_activated(reason, **extra)

            # 1. The selection must still be the one the build was judged against.
            current = classify_selection_envelope(
                await _locked_read(
                    db, SELECTION_IDENTITY, lock="update", expected_version=SELECTION_SCHEMA
                )
            )
            if current.status != expected.status or current.generation != expected.generation:
                return await _abort(
                    "selection_moved",
                    expected_generation=expected.generation,
                    found_generation=current.generation,
                )

            # 2. The incumbent as it stands NOW, locked against its own publisher.
            incumbent_payload: Optional[dict] = None
            if incumbent_ns is not None:
                inc = await _locked_read(
                    db, incumbent_ns.identity, lock="share",
                    expected_version=incumbent_ns.version,
                )
                if not inc.ok or not expected.selection.admits_generation(inc.generation):
                    return await _abort("incumbent_unreadable", incumbent_status=inc.status)
                incumbent_payload = inc.envelope.payload
            else:
                # Cold start: "nothing is active" must still be true.
                legacy = await _locked_read(db, LEGACY_IDENTITY, lock="share", expected_version=None)
                if not legacy.missing:
                    return await _abort("incumbent_appeared")

            ok, why = recheck(incumbent_payload)
            if not ok:
                return await _abort("gate_refused_on_recheck", detail=why)

            # 3. The staged candidate must be exactly the row this build wrote.
            cand = await _locked_read(
                db, candidate_ns.identity, lock="share", expected_version=candidate_version
            )
            if not cand.ok:
                return await _abort("candidate_unreadable", candidate_status=cand.status)
            if cand.generation != candidate_generation:
                return await _abort(
                    "candidate_moved",
                    staged_generation=candidate_generation,
                    found_generation=cand.generation,
                )
            cand_payload = cand.envelope.payload if isinstance(cand.envelope.payload, dict) else {}
            if cand_payload.get("population_version") != candidate_version:
                return await _abort("candidate_version_mismatch")
            if cand_payload.get("population_predicate_fingerprint") != predicate_fingerprint:
                return await _abort("candidate_predicate_mismatch")

            # 4. Compare-and-swap on the generation actually read.
            stamp = now or datetime.now(timezone.utc)
            replaced = (
                {
                    "version": expected.selection.version,
                    "min_generation": expected.selection.min_generation,
                    "record_generation": expected.generation,
                }
                if expected.selection is not None
                else None
            )
            selection = ActiveSelection(
                version=candidate_version,
                min_generation=int(candidate_generation),
                origin=ORIGIN_ACTIVATION,
                predicate_fingerprint=predicate_fingerprint,
                selected_at=stamp.isoformat(),
                replaced=replaced,
            )
            sel_env = selection_envelope(selection, now=stamp)
            if expected.generation is not None and sel_env.generation <= expected.generation:
                # Generations are wall-clock ms; never let a skewed clock write a
                # record that orders BEFORE the one it replaces.
                from dataclasses import replace as _replace

                sel_env = _replace(sel_env, generation=int(expected.generation) + 1)
            stage = await publish_cas_snapshot_in_txn(
                db, sel_env, expected_generation=expected.generation
            )
            if stage.get("status") != "ok":
                return await _abort(
                    "cas_miss" if stage.get("status") == "cas-miss" else "cas_error",
                    stage=stage.get("status"),
                    error=stage.get("error"),
                )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — a failed activation preserves the incumbent
        logger.warning("calibration activation failed before commit: %s", exc)
        return _not_activated("activation_error", error=str(exc)[:200])

    return {
        "status": ACTIVATED,
        "selection": selection,
        "generation": sel_env.generation,
    }


# --- Route: resolve the selection ---------------------------------------------

_route_cache: dict = {"selection": None, "resolved_at": 0.0, "source": None}
#: The last selection this process VERIFIED from a store (never the default).
_last_verified: dict = {"selection": None}


def _reset_route_cache_for_tests() -> None:
    _route_cache.update(selection=None, resolved_at=0.0, source=None)
    _last_verified["selection"] = None


async def resolve_for_route(db, *, now: Optional[float] = None) -> tuple[ActiveSelection, str]:
    """The selection a request serves, and where it came from. Never raises.

    Order: process (≤ :data:`SELECTION_PROCESS_TTL_S`) → Redis accelerator →
    durable record → the last selection this process verified → the legacy
    default. Read-only: the route never writes any of these stores.

    ``missing`` everywhere means no rollover has started, so the legacy
    incumbent is the answer. Unknown or malformed fails closed to the last
    VERIFIED active selection, and only to the default when this process has
    never verified one. The default is the legacy incumbent and carries its own
    version, never an unactivated candidate.
    """
    from app.utils import request_cache as _rc

    t = time.monotonic() if now is None else now
    cached = _route_cache.get("selection")
    if cached is not None and t - _route_cache.get("resolved_at", 0.0) < SELECTION_PROCESS_TTL_S:
        return cached, "process"

    def _keep(selection: ActiveSelection, source: str) -> tuple[ActiveSelection, str]:
        _route_cache.update(selection=selection, resolved_at=t, source=source)
        if selection.origin != ORIGIN_DEFAULT:
            _last_verified["selection"] = selection
        return selection, source

    try:
        rc = await _rc.get_shared_async_redis()
        res = await _rc.bounded_redis_call(lambda: rc.get(SELECTION_REDIS_KEY))
        if res.is_ok and res.value:
            raw = json.loads(res.value)
            rec_gen = raw.get("record_generation") if isinstance(raw, dict) else None
            parsed = parse_selection(raw, record_generation=rec_gen if isinstance(rec_gen, int) else None)
            if parsed is not None:
                return _keep(parsed, "redis")
            logger.warning("calibration selection: Redis copy failed validation — reading durable")
    except Exception:  # noqa: BLE001 — accelerator only
        logger.warning("calibration selection: Redis read failed — reading durable", exc_info=True)

    durable = await read_active_selection(db)
    if durable.ok:
        return _keep(durable.selection, "durable")
    if durable.status == READ_MISSING:
        return _keep(default_selection(), "default_no_record")

    logger.warning(
        "calibration selection: durable record %s (%s) — failing closed to the "
        "last verified selection", durable.status, durable.error,
    )
    verified = _last_verified.get("selection")
    if verified is not None:
        # Not re-cached: an unreadable record is re-tried on the next request.
        return verified, f"last_verified_after_{durable.status}"
    return default_selection(), f"default_after_{durable.status}"
