"""The publish gate's baseline of last resort: durable history, not just Redis (#1768).

The gate decides "is this the first publish ever?" by looking for a prior
artifact. Until now it looked in exactly two places, both Redis:
``calibration:main`` (2h TTL) and ``calibration:main:last_good`` (7d TTL). Once
an outage runs longer than seven days BOTH keys are gone, and an ordinary
recovery becomes indistinguishable from a true cold start — so ``first_publish``
short-circuits the population-drift, category-collapse and tier-inversion rules
and the recovery publishes unexamined.

That is not hypothetical. On 2026-08-11 a 9.7-day producer outage ended with a
build replacing 652,407 outcomes with 703,980 (**+7.91%**) under an unchanged
``q267`` population version. The ±5% guard would have rejected it. It never ran,
because the baseline it compares against had aged out *during the very outage
the publish was recovering from*. **The longer the outage — i.e. the more
suspect the recovery — the more certain it is that the guard has lost the
ability to scrutinise it.**

This module supplies the missing third place to look. The publisher writes a
durable row (``durable_state_snapshots``) BEFORE either Redis key and it has no
TTL, so at gate time that row still holds the PREVIOUS generation. Reading it
without the serving-age cutoff turns "I found nothing" into a question with
three distinct answers instead of one:

``cold_start``
    The durable store answered and there is genuinely no prior row. This is the
    only provable cold start, and the only case that may keep the permissive
    path — refusing it would leave the page permanently dark, which is the
    failure the permissive path exists to prevent.
``found``
    A prior generation exists and is readable. Compare against it.
``indeterminate``
    Something is there, or we cannot tell — a torn row, an unreadable store, a
    timeout. A prior generation may well exist, so granting first-publish
    semantics here would be inventing a fact from an absence.

Gotcha #53 is the whole shape of this bug: an absent baseline and a
never-existed baseline returned the same answer, and the code inferred the
emptier reading. The three-way status is the second signal that disambiguates
them.

Refusing on ``indeterminate`` costs nothing that was not already lost: when the
durable store is unreachable the publisher's own durable write fails too, and
``_publish_calibration_main`` already skips the Redis accelerators in that case
so that volatile can never lead durable. A publish was never going to happen on
a broken durable store; this just makes the gate say so before the build does.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

#: The durable identity ``precompute_calibration`` publishes the main payload
#: under. Kept as a literal rather than imported from the task module: that
#: module is under ruling 009's freeze, and a read-side utility must not make
#: itself un-importable by depending on a file nobody may touch.
DURABLE_IDENTITY = "calibration:main"

#: Whole-probe bound, in seconds. Comfortably above the durable read's own
#: ``statement_timeout`` so an ordinary slow read still returns a real answer,
#: and far below the beat's deadline so a wedged store costs one probe rather
#: than the window. A timeout is ``indeterminate``, never ``cold_start``.
PROBE_TIMEOUT_S = 25.0

#: A prior generation exists and is readable — compare against it.
FOUND = "found"
#: The durable store answered "no such row". The only provable cold start.
COLD_START = "cold_start"
#: We cannot prove either way. Never treated as a cold start.
INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class BaselineProbe:
    """What durable history says about a prior published generation."""

    status: str
    payload: Any = None
    detail: str = ""
    #: The raw ``EnvelopeRead`` status, kept so a rejection can name the real
    #: cause (``malformed`` reads very differently from ``unavailable``).
    envelope_status: Optional[str] = None
    generated_at: Optional[str] = None


async def _read_durable_envelope():
    """Read the durable calibration envelope with NO serving-age cutoff.

    ``SERVE_MAX_AGE_S`` exists to stop an ancient snapshot being *served* as the
    current curve. It has no business deciding whether a prior generation
    EXISTED: an artifact too old to show a reader is still perfectly good
    evidence that this build is not the first one. Passing ``inf`` is the whole
    point of this function — with the default bound, a long outage would expire
    the durable answer exactly as it expired the Redis one, and we would have
    rebuilt the bug one layer down.
    """
    from app.services.durable_snapshots import read_snapshot_standalone

    return await read_snapshot_standalone(DURABLE_IDENTITY, max_age_s=float("inf"))


def _read_in_new_loop(timeout_s: float):
    """Run the async durable read from a synchronous caller, bounded.

    ``evaluate_publish`` is sync and is called from inside a running event loop,
    so neither ``await`` nor ``asyncio.run`` is available at the call site. A
    worker thread with its own loop is safe here specifically because
    ``get_task_session`` builds a FRESH engine per call, bound to the current
    loop — the "attached to a different loop" hazard that makes this pattern
    wrong in most of this codebase does not apply to it.

    The executor is shut down with ``wait=False`` on purpose: if the probe times
    out, the point is to stop waiting. Blocking on the very thread we just gave
    up on would convert a bounded probe into an unbounded one.
    """
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="cal-baseline-probe"
    )
    try:
        future = executor.submit(lambda: asyncio.run(_read_durable_envelope()))
        return future.result(timeout=timeout_s)
    finally:
        executor.shutdown(wait=False)


def probe_durable_baseline(
    *,
    reader: Optional[Callable[[], Any]] = None,
    timeout_s: float = PROBE_TIMEOUT_S,
) -> BaselineProbe:
    """Ask durable history whether a prior published generation exists.

    ``reader`` is the injection seam: tests supply a callable returning an
    ``EnvelopeRead`` (or raising) so the decision table can be exercised without
    a database. Production passes nothing and gets the bounded threaded read.
    """
    read = reader if reader is not None else (lambda: _read_in_new_loop(timeout_s))

    try:
        envelope_read = read()
    except concurrent.futures.TimeoutError:
        logger.warning(
            "calibration gate: durable baseline probe timed out after %ss — "
            "treating as INDETERMINATE, not as a cold start",
            timeout_s,
        )
        return BaselineProbe(
            INDETERMINATE,
            detail=f"durable baseline probe timed out after {timeout_s}s",
        )
    except Exception as exc:  # noqa: BLE001 — any failure is "cannot tell"
        logger.warning("calibration gate: durable baseline probe failed: %s", exc)
        return BaselineProbe(
            INDETERMINATE,
            detail=f"durable baseline probe raised {type(exc).__name__}: {exc}"[:300],
        )

    status = getattr(envelope_read, "status", None)
    error = getattr(envelope_read, "error", None)

    if status == "missing":
        # The store answered, and the answer was "no row". This is the ONLY
        # reading that proves a true cold start.
        return BaselineProbe(
            COLD_START,
            detail="durable history holds no prior calibration:main generation",
            envelope_status=status,
        )

    if status == "ok":
        envelope = getattr(envelope_read, "envelope", None)
        payload = getattr(envelope, "payload", None)
        generated_at = getattr(envelope, "generated_at", None)
        if isinstance(payload, dict):
            return BaselineProbe(
                FOUND,
                payload=payload,
                detail="prior generation recovered from durable history",
                envelope_status=status,
                generated_at=str(generated_at) if generated_at is not None else None,
            )
        # A row that decodes but carries a non-object body is a prior generation
        # we cannot compare against — which is a reason to stop, not to wave on.
        return BaselineProbe(
            INDETERMINATE,
            detail=(
                "durable calibration:main decoded OK but its payload is "
                f"{type(payload).__name__}, not a JSON object"
            ),
            envelope_status=status,
        )

    return BaselineProbe(
        INDETERMINATE,
        detail=(
            f"durable calibration:main read returned {status!r}"
            + (f": {error}" if error else "")
        )[:300],
        envelope_status=status if isinstance(status, str) else None,
    )
