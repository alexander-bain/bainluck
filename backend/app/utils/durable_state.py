"""One typed, versioned envelope for state that must outlive Redis (Queue 298).

C117 confirmed #1512 in committed code: every artifact we call a "survivor" —
calibration's ``main`` AND its ``main:last_good``, all seven sentinel verdict
families, task metrics, the composed ops evidence — lives in the SAME 50MB
``allkeys-lru`` Redis. A 7-day TTL is not durability when the eviction policy
throws the key out at 49.5/50MB, and a fresh web dyno has no process cache to
fall back to. The result Alex sees: ``/calibration`` fails to load, and six
``/last`` rails say ``no_run_cached`` hours after a healthy beat.

This module is the contract half of the fix. It is PURE — no Redis, no database,
no clock it does not accept, no framework — so the whole failure matrix is
table-driven testable (that is what ``scripts/evals/durable_state_survival_contract.py``
does, 34 cases). The storage half lives in ``app.services.durable_snapshots``.

The rules, all of which C117's oracle pins:

* **Durable-first publication.** A candidate is written to the durable substrate
  BEFORE the volatile accelerators. A volatile copy that is ahead of the durable
  one is a TORN publication, not a fresher answer.
* **Prior last-good is never destroyed** by a failed, incomplete, or cancelled
  run. Publication is replace-if-newer, never delete-then-write.
* **Redis and process memory are accelerators only.** Process memory may serve a
  WARM process; it can never be the durability story for a fresh one.
* **Untrustworthy is UNKNOWN.** Missing, malformed, wrong-version, stale, or
  unreadable state is typed — never a null, never ordinary no-data, never a
  zero, never GREEN, never "current".
* **Task success requires the durable write.** A run whose required durable
  publication failed must not report success, or filing and closure evidence
  will cite a run that saved nothing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# --- Read states (mirror app.utils.health_reads where they overlap) ----------

OK = "ok"
MISSING = "missing"
MALFORMED = "malformed"
WRONG_TYPE = "wrong_type"
WRONG_VERSION = "wrong_version"
STALE = "stale"
UNAVAILABLE = "unavailable"

#: Where a served payload actually came from.
SOURCE_VOLATILE = "volatile"
SOURCE_DURABLE = "durable"
SOURCE_PROCESS = "process"
SOURCE_UNAVAILABLE = "unavailable"

#: The verdict for state we cannot vouch for. Never a colour, never a number.
UNKNOWN = "UNKNOWN"

# Contract violations. These are stable strings — they appear in admin payloads
# and in the C117 corpus, so renaming one is a contract change.
ERR_VOLATILE_AHEAD = "VOLATILE_AHEAD_OF_DURABLE"
ERR_FRESH_USES_PROCESS = "FRESH_PROCESS_USES_PROCESS_MEMORY"
ERR_INCOMPLETE_WRITES_DURABLE = "INCOMPLETE_COMPUTE_WRITES_DURABLE"
ERR_VOLATILE_WITHOUT_DURABLE = "VOLATILE_PUBLISHED_WITHOUT_DURABLE"
ERR_CANCELLED_PUBLISHED = "CANCELLED_RUN_PUBLISHED"
ERR_PRIOR_DESTROYED = "PRIOR_LAST_GOOD_DESTROYED"
ERR_CHECKED_ZERO_GREEN = "CHECKED_ZERO_GREEN"
ERR_COMPOSITE_ERASES = "MIXED_COMPOSITE_ERASES_PROVENANCE"
ERR_POISON_WIPES = "POISON_WIPES_HEALTHY_STATE"

#: Envelope format version. Bump only when the ENVELOPE shape changes — the
#: payload's own contract version (e.g. calibration's ``population_version``)
#: travels separately in :attr:`DurableEnvelope.schema_version`.
ENVELOPE_FORMAT = "durable-state/v1"

#: Default age bound for a durable artifact, matching the 7d last_good TTL the
#: calibration publisher already used. Per-family overrides are explicit.
DEFAULT_MAX_AGE_S = 604800


def canonical_json(payload: Any) -> str:
    """Stable serialization — the checksum must not move when dict order does."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def checksum_payload(payload: Any) -> str:
    """Content address of a payload body. Detects a torn or truncated write that
    still happens to be syntactically valid JSON."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def generation_for(generated_at: datetime) -> int:
    """Monotonic generation from the build's own stamp (epoch milliseconds).

    Deliberately derived rather than counted: a counter needs its own durable
    row and a race-free increment, while the producer already has the one fact
    that orders builds. Two publishes inside the same millisecond collide to the
    same generation, which the contract treats as a duplicate (idempotent
    republish), not as a conflict.
    """
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    return int(generated_at.timestamp() * 1000)


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_generated_at_field(
    payload: Any, *, field_name: str = "generated_at", default_now: bool = True
) -> Optional[datetime]:
    """The build stamp a payload carries, so the generation follows the artifact.

    Sentinel scorecards and the calibration payload both stamp themselves; using
    that stamp (rather than "now at write time") keeps the generation stable
    across a retry of the SAME artifact.
    """
    stamp = _parse_dt(payload.get(field_name)) if isinstance(payload, dict) else None
    if stamp is None and default_now:
        return datetime.now(timezone.utc)
    return stamp


@dataclass(frozen=True)
class DurableEnvelope:
    """One versioned, checksummed artifact plus everything needed to judge it."""

    identity: str
    schema_version: str
    generation: int
    generated_at: datetime
    payload: Any
    checksum: str
    complete: bool = True
    source: str = "unknown"

    @classmethod
    def build(
        cls,
        *,
        identity: str,
        schema_version: str,
        payload: Any,
        generated_at: Optional[datetime] = None,
        complete: bool = True,
        source: str = "unknown",
        generation: Optional[int] = None,
    ) -> "DurableEnvelope":
        stamp = generated_at or datetime.now(timezone.utc)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return cls(
            identity=identity,
            schema_version=schema_version,
            generation=generation if generation is not None else generation_for(stamp),
            generated_at=stamp,
            payload=payload,
            checksum=checksum_payload(payload),
            complete=complete,
            source=source,
        )

    def provenance(self, *, served_from: str, now: Optional[datetime] = None) -> dict:
        """The additive block every migrated surface exposes.

        Callers merge this under a ``provenance`` key; it never replaces or
        reshapes an existing response field.
        """
        reference = now or datetime.now(timezone.utc)
        return {
            "source": served_from,
            "identity": self.identity,
            "schema_version": self.schema_version,
            "generation": self.generation,
            "generated_at": self.generated_at.isoformat(),
            "age_s": round((reference - self.generated_at).total_seconds(), 1),
            "complete": self.complete,
            "dated": served_from in (SOURCE_DURABLE, SOURCE_PROCESS),
            "envelope_format": ENVELOPE_FORMAT,
        }


@dataclass(frozen=True)
class EnvelopeRead:
    """One classified attempt to read an envelope from one tier."""

    status: str
    tier: str
    envelope: Optional[DurableEnvelope] = None
    error_class: Optional[str] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == OK

    @property
    def missing(self) -> bool:
        return self.status == MISSING

    @property
    def unavailable(self) -> bool:
        return self.status == UNAVAILABLE

    @property
    def generation(self) -> int:
        return self.envelope.generation if self.envelope else -1

    def as_status(self, **extra: Any) -> dict:
        """Composite-safe: says WHY, never masquerades as data."""
        out: dict = {"status": self.status, "tier": self.tier}
        if self.error_class:
            out["error_class"] = self.error_class
        if self.error:
            out["error"] = self.error
        out.update(extra)
        return out


def failed_read(tier: str, exc: BaseException, *, status: str = UNAVAILABLE) -> EnvelopeRead:
    """Classify an exception without leaking the host or credentials."""
    from app.utils.health_reads import redact

    return EnvelopeRead(
        status=status, tier=tier, error_class=exc.__class__.__name__, error=redact(exc)
    )


def decode_envelope(
    raw: Any,
    *,
    tier: str,
    expected_version: Optional[str],
    max_age_s: float = DEFAULT_MAX_AGE_S,
    now: Optional[datetime] = None,
) -> EnvelopeRead:
    """Turn a stored envelope dict into a typed, TRUSTWORTHY-or-not read.

    The order matters: shape, then checksum, then version, then completeness,
    then age. A wrong-version artifact is reported as such rather than as
    "malformed", because the operator response differs — one is a deploy skew,
    the other is corruption.
    """
    if raw is None:
        return EnvelopeRead(status=MISSING, tier=tier)
    if not isinstance(raw, dict):
        return EnvelopeRead(
            status=WRONG_TYPE,
            tier=tier,
            error_class="TypeError",
            error=f"expected dict envelope, got {type(raw).__name__}",
        )

    identity = raw.get("identity")
    schema_version = raw.get("schema_version")
    payload = raw.get("payload")
    stored_checksum = raw.get("checksum")
    generated_at = _parse_dt(raw.get("generated_at"))
    generation = raw.get("generation")

    if not isinstance(identity, str) or not isinstance(schema_version, str):
        return EnvelopeRead(
            status=MALFORMED, tier=tier, error_class="ValueError",
            error="envelope is missing identity or schema_version",
        )
    if generated_at is None:
        return EnvelopeRead(
            status=MALFORMED, tier=tier, error_class="ValueError",
            error="generated_at is missing or unparseable",
        )
    if not isinstance(generation, int):
        return EnvelopeRead(
            status=MALFORMED, tier=tier, error_class="ValueError",
            error="generation is missing or not an integer",
        )
    if not isinstance(stored_checksum, str) or checksum_payload(payload) != stored_checksum:
        # A body that does not match its own checksum is a torn/truncated write.
        # It may parse perfectly; that is exactly why the checksum exists.
        return EnvelopeRead(
            status=MALFORMED, tier=tier, error_class="ChecksumMismatch",
            error="payload checksum does not match the stored envelope",
        )

    complete = bool(raw.get("complete", False))
    envelope = DurableEnvelope(
        identity=identity,
        schema_version=schema_version,
        generation=generation,
        generated_at=generated_at,
        payload=payload,
        checksum=stored_checksum,
        complete=complete,
        source=str(raw.get("source") or "unknown"),
    )

    if expected_version is not None and schema_version != expected_version:
        return EnvelopeRead(
            status=WRONG_VERSION, tier=tier, envelope=envelope,
            error_class="VersionMismatch",
            error=f"schema_version {schema_version!r} != expected {expected_version!r}",
        )
    if not complete:
        return EnvelopeRead(
            status=MALFORMED, tier=tier, envelope=envelope,
            error_class="IncompleteArtifact",
            error="envelope is marked incomplete",
        )

    reference = now or datetime.now(timezone.utc)
    age_s = (reference - generated_at).total_seconds()
    # NEGATIVE age is rejected, not clamped: a payload stamped in the future is
    # clock skew, and serving it as "fresh" is the dishonesty this queue ends.
    if age_s < 0 or age_s > max_age_s:
        return EnvelopeRead(
            status=STALE, tier=tier, envelope=envelope,
            error_class="AgeBound",
            error=f"age {round(age_s, 1)}s outside [0, {max_age_s}]",
        )

    return EnvelopeRead(status=OK, tier=tier, envelope=envelope)


@dataclass(frozen=True)
class Resolution:
    """Which tier may serve, and every contract violation seen getting there."""

    source: str
    envelope: Optional[DurableEnvelope]
    errors: list[str] = field(default_factory=list)

    @property
    def servable(self) -> bool:
        return self.source != SOURCE_UNAVAILABLE and self.envelope is not None

    def health(self, payload_verdict: str, *, checked: Optional[int] = None) -> str:
        """The verdict a surface may show.

        ``checked == 0`` can never pass as a real verdict: a sentinel that
        examined nothing is UNKNOWN, not GREEN. Neither can any resolution that
        recorded a contract violation.
        """
        if not self.servable or self.errors or checked == 0:
            return UNKNOWN
        return payload_verdict


def resolve(
    *,
    volatile: EnvelopeRead,
    durable: EnvelopeRead,
    process: EnvelopeRead,
    fresh_process: bool,
) -> Resolution:
    """Pick the tier that may serve, per the C117 precedence.

    Durable is the authority. Volatile is allowed to serve only when it is valid
    and NOT ahead of durable — because "ahead" cannot happen under durable-first
    publication, so it means we caught a torn pair, and the safe reading is the
    durable one plus a loud contract violation.
    """
    errors: list[str] = []
    v_ok, d_ok = volatile.ok, durable.ok
    # Process memory is an accelerator. On a fresh process there is nothing in
    # it to trust, and a warm-looking value there must never stand in for
    # cross-process durability.
    p_ok = process.ok and not fresh_process

    if v_ok and d_ok and volatile.generation > durable.generation:
        errors.append(ERR_VOLATILE_AHEAD)
        source, chosen = SOURCE_DURABLE, durable.envelope
    elif d_ok and (not v_ok or durable.generation > volatile.generation):
        source, chosen = SOURCE_DURABLE, durable.envelope
    elif v_ok:
        source, chosen = SOURCE_VOLATILE, volatile.envelope
    elif d_ok:
        source, chosen = SOURCE_DURABLE, durable.envelope
    elif p_ok:
        source, chosen = SOURCE_PROCESS, process.envelope
    else:
        source, chosen = SOURCE_UNAVAILABLE, None

    if fresh_process and source == SOURCE_PROCESS:
        errors.append(ERR_FRESH_USES_PROCESS)
        source, chosen = SOURCE_UNAVAILABLE, None

    return Resolution(source=source, envelope=chosen, errors=errors)


@dataclass(frozen=True)
class PublicationOutcome:
    """Whether a producer run may report success, and why not if it may not."""

    success: bool
    errors: list[str] = field(default_factory=list)
    stages: dict = field(default_factory=dict)

    def raise_if_failed(self, label: str) -> None:
        if not self.success:
            raise RuntimeError(
                f"{label}: durable publication did not succeed "
                f"({', '.join(self.errors) or 'unknown reason'}; stages={self.stages}) "
                f"— prior last-good preserved"
            )


def evaluate_publication(
    *,
    compute_complete: bool,
    durable_write: str,
    volatile_write: str,
    cancelled: bool = False,
    prior_last_good_preserved: bool = True,
    torn: bool = False,
    stages: Optional[dict] = None,
) -> PublicationOutcome:
    """Judge one publication attempt. ``*_write`` is ok/error/not_attempted.

    This is what stops a run from reporting success while having saved nothing —
    the specific defect C117 found in every sentinel producer, all of which
    swallow a failed SETEX and return normally, so ``_tracked_run`` records a
    healthy run and Review/Verify evidence cites it.
    """
    errors: list[str] = []
    if not compute_complete and durable_write != "not_attempted":
        errors.append(ERR_INCOMPLETE_WRITES_DURABLE)
    if durable_write != "ok" and volatile_write == "ok":
        errors.append(ERR_VOLATILE_WITHOUT_DURABLE)
    if cancelled and volatile_write != "not_attempted":
        errors.append(ERR_CANCELLED_PUBLISHED)
    if prior_last_good_preserved is not True:
        errors.append(ERR_PRIOR_DESTROYED)
    if torn:
        errors.append(ERR_VOLATILE_AHEAD)

    success = (
        compute_complete
        and durable_write == "ok"
        and not cancelled
        and ERR_VOLATILE_AHEAD not in errors
    )
    return PublicationOutcome(success=success, errors=errors, stages=stages or {})


def unavailable_status(
    identity: str,
    *,
    reads: dict[str, EnvelopeRead],
    detail: str = "no trustworthy snapshot in any tier",
) -> dict:
    """The typed UNKNOWN body a rail returns instead of null / 503 / no-data."""
    return {
        "status": "unavailable",
        "health": UNKNOWN,
        "identity": identity,
        "detail": detail,
        "tiers": {name: read.as_status() for name, read in reads.items()},
    }
