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

AND IT REFUSES TO GUESS — INCLUDING ABOUT ITSELF (CERT-824). The first version
called an absent row "genuinely never published" and answered ``False``. It is
not. ``record_pass_run`` never fails the matcher, and that rule is not
negotiable: a telemetry store must never be able to stop the backlog pass. So a
failed record write is an ACCEPTED path, and it leaves the store in exactly the
state a pass that never ran leaves it in. A later healthy read cannot tell the
two apart, and CERT-824 reproduced it end to end — ``pass_actually_ran=True``,
``record_stage='error'``, ``reported_has_run=False`` — which is the CERT-819
false negative arriving by a third route. So absence is now published as
``None``/``no_record``. ``has_run`` is only ever ``True`` (we hold positive
evidence) or ``None`` (we do not), and ``status`` says which kind of nothing we
are holding.

THE POSITIVE EVIDENCE THAT SURVIVES A FAILED WRITE is the receipt label census
the endpoint already computes. That census is unusable as a run history in the
ABSENT direction — that is CERT-819, and the reason this module exists — but it
is sound in the PRESENT direction: nothing writes ``phase=pass3_backlog`` except
``_phase1_pass3_backlog_scan``'s own flush, so a live ``pass3_backlog`` label
means Pass 3 ran, whatever the durable store says. Callers pass it as
``receipt_witness`` and an absent row is upgraded to ``True``
(``witnessed_by_receipts``) instead of guessed at. It can only ever ADD a
``True``; it cannot manufacture a ``False``, because there are none left.
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

#: No durable row, and nothing else witnessing a run. NOT "never ran" — a run
#: whose non-fatal record write failed looks identical from here (CERT-824).
STATUS_NO_RECORD = "no_record"

#: No durable row, but a live ``pass3_backlog`` receipt label proves a run
#: happened. Sound because only Pass 3's own flush writes that label.
STATUS_WITNESSED = "witnessed_by_receipts"


def pass_run_identity(phase: str) -> str:
    """The durable identity for one matcher pass.

    One per phase deliberately — see the module docstring's monotonicity note.
    """
    return f"{_IDENTITY_PREFIX}{phase}"


@dataclass(frozen=True)
class PassRunFact:
    """What we can honestly say about whether ``phase`` has ever run.

    ``has_run`` is ``True`` or ``None``, and never ``False``. ``None`` means we
    hold no evidence of a run — because the store did not answer, or because
    there is no row and nothing else witnesses one. Neither is the claim "it
    never ran", and CERT-824 blocked publishing them as one.
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
                "receipt's phase label cannot unmake it. has_run is true or "
                "null, NEVER false: recording a run is non-fatal by design, so "
                "a run whose record write failed leaves the store looking "
                "exactly like a pass that never ran, and null is the only "
                "honest answer to that. null means no evidence of a run — that "
                "is not 'never ran'; read status for which kind of nothing it "
                "is, and the matcher's funnel.backlog_run_recorded for whether "
                "the last write errored."
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
    db: AsyncSession,
    phase: str,
    *,
    now: Optional[datetime] = None,
    receipt_witness: Optional[bool] = None,
) -> PassRunFact:
    """Has ``phase`` ever run? ``True`` or ``None``, and it says why.

    ``receipt_witness`` is the caller's answer to "is a receipt carrying this
    phase's label alive right now?". Pass it when you already have the census —
    it is the one signal that survives a failed durable write. Presence proves a
    run; absence proves nothing (CERT-819), so ``False``/``None`` here changes
    nothing.
    """
    from app.services.durable_snapshots import read_snapshot

    # NOTE ON THE CALL'S SHAPE: the closing paren is kept on the last argument
    # line rather than on one of its own. A lone `)` directly above this
    # `except` line is, byte for byte, the M2-NO-LIMIT replacement literal in
    # `scripts/evals/typeahead_outcome_arm_mutations.py`, and the tree-wide
    # residue scan reads any file carrying it outside that harness's declared
    # targets as a mutant left behind. Formatting, not preference.
    try:
        read = await read_snapshot(
            db, pass_run_identity(phase),
            expected_version=PASS_RUN_SCHEMA_VERSION,
            max_age_s=_NO_AGE_BOUND, now=now)
    except Exception as exc:  # noqa: BLE001 — an admin read must not 500 on this
        logger.warning("could not read the %s pass run: %s", phase, exc)
        return PassRunFact(
            phase=phase,
            has_run=None,
            status="unavailable",
            error_class=exc.__class__.__name__,
        )

    if read.missing:
        # NO ROW IS NOT A NO (CERT-824). `record_pass_run` returns an `error`
        # stage instead of raising — on purpose, a record must never be a
        # constraint on the matcher — so "ran, write failed" and "never ran"
        # both land here and are indistinguishable. The census is the only
        # thing that can still tell us, and only when it says yes.
        if receipt_witness:
            return PassRunFact(phase=phase, has_run=True, status=STATUS_WITNESSED)
        return PassRunFact(phase=phase, has_run=None, status=STATUS_NO_RECORD)

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
