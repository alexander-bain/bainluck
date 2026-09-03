"""Did a matcher pass ever actually run? A durable, monotone answer (#2803).

WHY THIS EXISTS, WHICH IS A CORRECTION. ``GET /api/admin/match-receipts``
published ``coverage.backlog_pass_has_run`` derived from a ``GROUP BY phase``
over ``market_match_receipts``. That is not an "ever ran" fact and it cannot be
made into one: the receipt table is ONE MUTABLE ROW PER MARKET
(``market_id`` is unique, ``models.py``), and the upsert overwrites ``phase``
on every later attempt (``match_receipts.py``: ``"phase": stmt.excluded.phase``).
So the sequence

    Pass 3 runs and labels N markets ``pass3_backlog``
    -> Pass 1/2 later re-attempt those same open unlinked markets
    -> every ``pass3_backlog`` label is overwritten
    -> the endpoint reports ``backlog_pass_has_run: false``

reports that nothing is driving the coverage number down *after the thing that
drives it down has run*. An admin acting on that false negative goes looking for
a broken beat that is working. CERT-819 blocked the first version for exactly
this, and it was right.

THE FIX IS A DIFFERENT SUBSTRATE, NOT A BETTER QUERY. A run is a fact about a
RUN, so it cannot be stored on the entities the run touched — anything keyed by
market inherits the market's mutability. It goes in
``durable_state_snapshots`` (``DurableStateSnapshot``), the existing
cross-process durable store built for last-good state that must outlive Redis
(#1512): no migration, no new table, and a Redis key would have been the same
bug in a new place, because that store is a shared 100 MB LRU and an evicted
"ever" bit silently reverts to false.

MONOTONE BY CONSTRUCTION, three ways:

* ONE IDENTITY PER PHASE (``matcher:pass_run:pass3_backlog``). No read-modify-
  write, so no merge can drop another phase's entry, and Pass 1/2 physically
  cannot touch Pass 3's row — that is the property CERT-819 asked to be guarded.
* ``publish_snapshot``'s generation guard is ``<=``, so a delayed writer holding
  an older generation matches the conflict, fails the predicate and writes
  nothing.
* Nothing deletes these rows. ``publish_snapshot`` is an upsert with no delete
  path, so once true, true.

AND IT REFUSES TO GUESS. ``read_pass_run`` distinguishes "genuinely never
published" (False) from "the database did not answer" (None/unknown). A
coverage flag that says ``false`` because a read timed out is the original bug
with a different cause, so the unknown case is a third value and is published
as one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.durable_state import DurableEnvelope

logger = logging.getLogger(__name__)

#: Payload contract version. Bump when the payload keys below change shape; a
#: reader asking for v1 then classifies an older/newer row as ``wrong_version``
#: rather than silently misreading it.
PASS_RUN_SCHEMA_VERSION = "matcher-pass-run/v1"

#: Provenance stamped on the row, so an operator reading
#: ``durable_state_snapshots`` directly can see who wrote it.
PASS_RUN_SOURCE = "match_prediction_markets"

_IDENTITY_PREFIX = "matcher:pass_run:"

#: A run does not stop being a run because it was a while ago. Age is published
#: as ``last_run_age_s`` for the reader to judge; it must never demote the row to
#: ``stale`` and turn "ran in July" into "never ran".
_NO_AGE_BOUND = float("inf")


def pass_run_identity(phase: str) -> str:
    """The durable identity for one matcher pass.

    One per phase deliberately — see the module docstring's monotonicity note.
    """
    return f"{_IDENTITY_PREFIX}{phase}"


@dataclass(frozen=True)
class PassRunFact:
    """What we can honestly say about whether ``phase`` has ever run.

    ``has_run`` is deliberately tri-state. ``None`` means the durable store did
    not answer, which is NOT the same claim as "never ran" and must not be
    published as one.
    """

    phase: str
    has_run: Optional[bool]
    status: str
    last_run_at: Optional[datetime] = None
    rows_attempted: Optional[int] = None
    eligible_total: Optional[int] = None
    error_class: Optional[str] = None

    def age_s(self, now: Optional[datetime] = None) -> Optional[float]:
        if self.last_run_at is None:
            return None
        reference = now or datetime.now(timezone.utc)
        return round((reference - self.last_run_at).total_seconds(), 1)

    def as_dict(self, now: Optional[datetime] = None) -> dict:
        """The published block. ``has_run`` may be ``null``; ``status`` says why."""
        return {
            "phase": self.phase,
            "has_run": self.has_run,
            "status": self.status,
            "last_run_at": (
                self.last_run_at.isoformat() if self.last_run_at else None
            ),
            "last_run_age_s": self.age_s(now),
            "rows_attempted": self.rows_attempted,
            "eligible_total": self.eligible_total,
            "error_class": self.error_class,
            "note": (
                "Durable and monotone: read from durable_state_snapshots, one "
                "identity per pass, so a later Pass 1/2 attempt overwriting the "
                "receipt's phase label cannot unmake it. has_run null means the "
                "durable store did not answer — that is not 'never ran'."
            ),
        }


def build_pass_run_envelope(
    *,
    phase: str,
    ran_at: datetime,
    rows_attempted: int,
    eligible_total: Optional[int] = None,
) -> DurableEnvelope:
    """The envelope a completed pass publishes. Pure, so the shape is testable."""
    if ran_at.tzinfo is None:
        ran_at = ran_at.replace(tzinfo=timezone.utc)
    return DurableEnvelope.build(
        identity=pass_run_identity(phase),
        schema_version=PASS_RUN_SCHEMA_VERSION,
        generated_at=ran_at,
        source=PASS_RUN_SOURCE,
        payload={
            "phase": phase,
            "last_run_at": ran_at.isoformat(),
            "rows_attempted": int(rows_attempted),
            "eligible_total": (
                None if eligible_total is None else int(eligible_total)
            ),
        },
    )


async def record_pass_run(
    *,
    phase: str,
    ran_at: datetime,
    rows_attempted: int,
    eligible_total: Optional[int] = None,
) -> dict:
    """Record that ``phase`` ran. Never raises, never fails the matcher.

    ON ITS OWN SESSION. ``publish_snapshot`` commits, and the matcher commits
    per market on purpose (gotcha #13); borrowing its session to write a
    telemetry row would commit whatever that session was holding. The standalone
    variant exists for exactly this and keeps the durable write independent of
    the caller's transaction state.

    THIS IS A RECORD, NOT A CONSTRAINT — the same rule the receipts themselves
    live under. A durable store that is down must degrade the *reporting* of the
    backlog pass, never the backlog pass, so every failure returns a stage dict
    and none of them propagate.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone

    envelope = build_pass_run_envelope(
        phase=phase,
        ran_at=ran_at,
        rows_attempted=rows_attempted,
        eligible_total=eligible_total,
    )
    try:
        return await publish_snapshot_standalone(envelope)
    except Exception as exc:  # noqa: BLE001 — reporting must never break matching
        logger.warning("could not record the %s pass run: %s", phase, exc)
        return {
            "status": "error",
            "identity": envelope.identity,
            "error_class": exc.__class__.__name__,
            "error": str(exc)[:200],
        }


def _payload_int(payload: Any, key: str) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def read_pass_run(
    db: AsyncSession, phase: str, *, now: Optional[datetime] = None
) -> PassRunFact:
    """Has ``phase`` ever run? Tri-state, and it says which state and why."""
    from app.services.durable_snapshots import read_snapshot

    try:
        read = await read_snapshot(
            db,
            pass_run_identity(phase),
            expected_version=PASS_RUN_SCHEMA_VERSION,
            max_age_s=_NO_AGE_BOUND,
            now=now,
        )
    except Exception as exc:  # noqa: BLE001 — an admin read must not 500 on this
        logger.warning("could not read the %s pass run: %s", phase, exc)
        return PassRunFact(
            phase=phase,
            has_run=None,
            status="unavailable",
            error_class=exc.__class__.__name__,
        )

    if read.missing:
        # The one case that is genuinely a "no": the row was never written.
        return PassRunFact(phase=phase, has_run=False, status=read.status)

    if not read.ok or read.envelope is None:
        # unavailable / malformed / wrong_version / wrong_type. We do not know,
        # and "we do not know" is not "it never ran".
        return PassRunFact(
            phase=phase,
            has_run=None,
            status=read.status,
            error_class=read.error_class,
        )

    payload = read.envelope.payload
    return PassRunFact(
        phase=phase,
        has_run=True,
        status=read.status,
        last_run_at=read.envelope.generated_at,
        rows_attempted=_payload_int(payload, "rows_attempted"),
        eligible_total=_payload_int(payload, "eligible_total"),
    )
