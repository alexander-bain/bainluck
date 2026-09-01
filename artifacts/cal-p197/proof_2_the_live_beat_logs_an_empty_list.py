#!/usr/bin/env python3
"""CAL-P197 PROOF 2 (behavioural) — on the LIVE stuck beat the log line names nobody.

Runs from any cwd; bootstraps ``backend/`` onto sys.path itself. Exit 0 = held.
Touches no database: it replays the production ledger snapshot captured to
``live-ledger-phases.json`` beside this file, through the real ``PhaseLedger``.

Claims proved here:
  A. The captured snapshot is the live beat: terminal ``cancelled``, exactly one
     phase in a floor status (``futures``), the rest never started.
  B. Replayed through the real ledger, ``completed_required`` is EMPTY -- so the
     production log line renders ``in phase group []``: it accuses nobody.
  C. ``failed_phase`` on the same ledger returns ``futures`` -- the ledger knew.
  D. The degenerate case is strictly worse than the CAL-P109 specimen. There the
     line named the wrong phase; here it names none, and an operator reading it
     learns nothing at all about where 1,005s went.
"""

from __future__ import annotations

import json
import pathlib
import sys


def repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for p in [here, *here.parents]:
        if (p / "backend" / "app" / "utils" / "calibration_phase_ledger.py").exists():
            return p
    raise SystemExit("FATAL: could not locate repo root from %s" % here)


ROOT = repo_root()
sys.path.insert(0, str(ROOT / "backend"))

from app.utils.calibration_phase_ledger import (  # noqa: E402
    FLOOR_STATUSES,
    PhaseLedger,
    derive_plan,
)

SNAP = json.loads((pathlib.Path(__file__).resolve().parent / "live-ledger-phases.json").read_text())

# The exact format string at backend/app/tasks/precompute_calibration.py:7019.
LOG_FMT = "calibration main build ended %s after %dms in phase group %s: %s"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (("\n          " + detail) if detail else ""))
    if not ok:
        failures.append(label)


print("CAL-P197 PROOF 2 — the live beat's failure log names nobody")
print("repo root: %s" % ROOT)
print("snapshot : identity=%s updated_at=%s" % (SNAP["identity"], SNAP["updated_at"]))
print("           fingerprint=%s terminal=%s\n" % (SNAP["input_fingerprint"], SNAP["terminal"]))

# ---- A ---------------------------------------------------------------------
print("A. the snapshot is the live stuck beat")
floor = [p["name"] for p in SNAP["phases"] if p["status"] in FLOOR_STATUSES]
pending = [p["name"] for p in SNAP["phases"] if p["status"] == "pending"]
for p in SNAP["phases"]:
    print("          %-24s %-10s %10d ms" % (p["name"], p["status"], p["duration_ms"]))
check("terminal is 'cancelled'", SNAP["terminal"] == "cancelled")
check("exactly one phase is in a floor status", len(floor) == 1, "floor phases: %s" % floor)
check("that phase is 'futures'", floor == ["futures"])
check("every other phase never started", len(pending) == len(SNAP["phases"]) - 1,
      "pending: %s" % pending)

# ---- B & C: replay through the REAL ledger ---------------------------------
print("\nB/C. replay the snapshot through the real PhaseLedger")
ledger = PhaseLedger(
    plan=derive_plan({}),
    population_version="v1",
    owner="cal-p197-proof",
    generation=1,
    input_fingerprint=SNAP["input_fingerprint"],
)
# Reproduce the beat: futures ran and was cancelled; nothing else ever began.
futures = next(p for p in SNAP["phases"] if p["name"] == "futures")
ledger.begin("futures", now_ms=0)
ledger.close_open_phase(
    now_ms=futures["duration_ms"], status=futures["status"], detail="staged futures incomplete"
)

replayed = {n: ledger.records[n].status for n in ledger.order}
print("          replayed statuses: %s" % replayed)
check("replay reproduces the captured futures status",
      ledger.records["futures"].status == futures["status"])
check("replay reproduces the captured futures duration",
      ledger.records["futures"].duration_ms == futures["duration_ms"],
      "got %s, captured %s" % (ledger.records["futures"].duration_ms, futures["duration_ms"]))

completed = list(ledger.completed_required)
failed = ledger.failed_phase
rendered = LOG_FMT % ("cancelled", futures["duration_ms"], completed, "StagedFuturesIncomplete(...)")

print("\n          WHAT PRODUCTION LOGS TODAY (arg = completed_required):")
print("            %s" % rendered)
print("\n          WHAT THE LEDGER ALREADY KNOWS (failed_phase):")
print("            %r" % failed)

check("completed_required is empty", completed == [], "got %r" % completed)
check("the rendered log line contains 'in phase group []'", "in phase group []" in rendered)
check("the rendered log line never mentions 'futures'", "futures" not in rendered)
check("failed_phase names 'futures'", failed == "futures", "got %r" % failed)

# ---- D ---------------------------------------------------------------------
print("\nD. this is the degenerate case, worse than the CAL-P109 specimen")
# CAL-P109's specimen: futures completed, sports was cancelled.
spec = PhaseLedger(
    plan=derive_plan({}), population_version="v1", owner="cal-p197-proof",
    generation=1, input_fingerprint="fp",
)
spec.begin("futures", now_ms=0)
spec.complete("futures", now_ms=1_100_000)
spec.begin("sports", now_ms=1_100_000)
spec.close_open_phase(now_ms=1_103_500, status="timeout", detail="read:events")
spec_line = LOG_FMT % ("timeout", 1_103_500, list(spec.completed_required), "QueryCanceled(...)")
print("          P109 specimen  : %s" % spec_line)
print("          P109 truth     : %r" % spec.failed_phase)
check("the P109 specimen still mis-names the phase (wrong name)",
      "['futures']" in spec_line and spec.failed_phase == "sports")
check("the live beat is the degenerate form (no name at all)",
      completed == [] and failed is not None)

print("\n" + "=" * 78)
if failures:
    print("PROOF 2 FAILED — %d claim(s) did not hold:" % len(failures))
    for f in failures:
        print("  - %s" % f)
    sys.exit(1)
print("PROOF 2 HELD — the live beat's failure log renders 'in phase group []'")
print("               while the ledger has named 'futures' the whole time.")
sys.exit(0)
