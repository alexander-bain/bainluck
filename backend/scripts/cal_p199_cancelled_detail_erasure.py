#!/usr/bin/env python3
"""CAL-P199 (#2052): a cancelled phase loses its reason, by construction.

THE CLAIM. ``PhaseRunner.abort`` records the dying phase's reason as
``str(exc)[:200]``. ``PhaseLedger.fail`` then stores ``detail or None``, and
``PhaseRecord.as_payload`` emits the key only ``if self.detail``. Both are falsy
tests on a STRING. The one exception type that stringifies to ``''`` is
``asyncio.CancelledError`` — and that is precisely the type
``classify_failure`` maps to status ``cancelled``.

So the status that most needs a reason is the only one guaranteed not to carry
one, and the ledger renders "the beat ended as designed" and "the beat was
killed from outside" as the same three characters.

WHY IT MATTERS AND IS NOT COSMETIC. ``StagedFuturesIncomplete`` — the designed,
healthy end of a staged beat — ALSO maps to ``cancelled``, and it DOES carry a
message. So ``detail`` is the only field in the whole ledger that separates the
two, and it is exactly the field the falsy test erases.

This is a SIXTH instance of the falsy-zero class the burn-down conveyor recorded
as CLOSED. CAL-P198-3's sweep closed four modules NEGATIVE — including both
modules touched here — because it looked for numeric falsy defaults only. An
empty string is falsy too.

CONTROL ARMS (CAL-P198's lesson: a sweep that returns "clean" is worthless until
it reproduces a known hit). Three, all required:
  * CONTROL+ A: ``StagedFuturesIncomplete("...")`` also classifies ``cancelled``
    and MUST retain its detail. Proves the harness can see a detail when one
    exists, so the absence in the claim arm is the defect and not the harness.
  * CONTROL+ B: a generic exception with a message classifies ``failed`` and
    MUST retain its detail. Proves the erasure is specific to the empty string,
    not to ``fail()`` in general.
  * CONTROL- : ``CancelledError("a reason")`` — a cancellation that DOES carry a
    message — MUST retain it. Proves the bug is the falsy test, not the type.

Read-only. Touches no database. Runs from any cwd.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.tasks.calibration_main_build import (  # noqa: E402
    PhaseRunner,
    StagedFuturesIncomplete,
)
from app.utils.calibration_phase_ledger import PhaseLedger  # noqa: E402

PHASE = "futures"


class _StubPlan:
    """Just enough plan for PhaseLedger.__init__; budgets are irrelevant here."""

    def by_name(self, name):  # noqa: D102
        return None


class _StubRunner:
    """A real PhaseLedger behind the real PhaseRunner.abort."""

    def __init__(self) -> None:
        self.ledger = PhaseLedger(
            plan=_StubPlan(),
            population_version="p199",
            owner="cal-p199",
            generation=1,
            input_fingerprint="deadbeef",
            phases=(PHASE,),
        )
        self.ledger.begin(PHASE, now_ms=0)

    def elapsed_ms(self) -> int:
        return 1000

    # the two real methods under test, bound to this stub
    classify_failure = PhaseRunner.classify_failure
    abort = PhaseRunner.abort


def probe(exc: BaseException) -> tuple[str, object, bool]:
    """Return (status, stored detail, whether as_payload emitted the key)."""
    r = _StubRunner()
    status = r.abort(exc)
    record = r.ledger.records[PHASE]
    return status, record.detail, "detail" in record.as_payload()


def main() -> int:
    failures: list[str] = []

    print(f"str(asyncio.CancelledError()) = {str(asyncio.CancelledError())!r}  "
          f"falsy={not str(asyncio.CancelledError())}")
    print()

    # ---- THE CLAIM --------------------------------------------------------
    status, detail, emitted = probe(asyncio.CancelledError())
    print(f"CLAIM     CancelledError()                 -> status={status!r} "
          f"detail={detail!r} emitted={emitted}")
    if not (status == "cancelled" and detail is None and not emitted):
        failures.append("CLAIM did not reproduce — CancelledError kept a detail")

    # ---- CONTROL+ A -------------------------------------------------------
    msg = "futures generation incomplete — units banked, nothing published"
    status, detail, emitted = probe(StagedFuturesIncomplete(msg))
    print(f"CONTROL+A StagedFuturesIncomplete(msg)     -> status={status!r} "
          f"detail={str(detail)[:40]!r}... emitted={emitted}")
    if not (status == "cancelled" and detail == msg and emitted):
        failures.append("CONTROL+A FAILED — harness cannot see a detail that exists")

    # ---- CONTROL+ B -------------------------------------------------------
    status, detail, emitted = probe(RuntimeError("a real failure"))
    print(f"CONTROL+B RuntimeError('a real failure')   -> status={status!r} "
          f"detail={detail!r} emitted={emitted}")
    if not (status == "failed" and detail == "a real failure" and emitted):
        failures.append("CONTROL+B FAILED — fail() drops details generally")

    # ---- CONTROL- ---------------------------------------------------------
    status, detail, emitted = probe(asyncio.CancelledError("a reason"))
    print(f"CONTROL-  CancelledError('a reason')       -> status={status!r} "
          f"detail={detail!r} emitted={emitted}")
    if not (status == "cancelled" and detail == "a reason" and emitted):
        failures.append("CONTROL- FAILED — the type, not the empty string, is the cause")

    print()
    print("The two arms that matter are CLAIM and CONTROL+A: both end status")
    print("'cancelled', one is the designed end of a healthy beat and one is an")
    print("external kill, and only one of them says so.")
    print()
    if failures:
        for f in failures:
            print("FAIL:", f)
        return 1
    print("CONFIRMED: status 'cancelled' from a bare CancelledError records no reason,")
    print("and is indistinguishable in the ledger from the healthy staged end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
