#!/usr/bin/env python3
"""CAL-P203 -- the rebuild's live bank is in a DIFFERENT durable row than the one
the conveyor tells you to read, and the row it tells you to read is a beat-END copy.

THE QUESTION (Q8, "this pair of gauges is meant to be read TOGETHER -- sampled at
the same instant?"), turned on the pair the conveyor has been reading as one number:

    ITEM 1b of the burndown conveyor says, of ``calibration:main:phase_ledger``:
    "Check ``updated_at`` FIRST."  ITEM 3 step 1 says: "grade ... progress on
    ``units_banked``."  Both refer to the SAME durable row.

    But ``staged:units_banked`` is not measured by the ledger.  It is a COPY:

        calibration_main_build.py:1411
            runner.ledger.record_gauge("staged:units_banked", len(committed))

    ...where ``committed`` was read moments earlier out of a DIFFERENT durable row,
    ``calibration:main:staged_futures``, inside ``_record_staged_convergence()``,
    which by its own docstring runs "on EVERY terminal" -- i.e. at BEAT END.

    The source row is rewritten PER UNIT:

        precompute_calibration.py:4726
            if not await save_staged_cursor(cursor, terminal=TERMINAL_PARTIAL):

        calibration_staged_futures.py:1250 (verbatim)
            "the cursor is re-serialised in FULL after every unit (per-unit
             ``save_staged_cursor``, which is what caps a SIGKILL's cost at one unit)"

    So the two are NEVER sampled at the same instant.  The ledger's copy is stale
    for the entire duration of a beat -- and a beat is planned against
    PHASE_DEADLINE_MS = 1,380,000 ms (~23 min).

WHY IT MATTERS OPERATIONALLY.  Four consecutive conveyor sessions (P200-P202, and
this one at 19:26Z) read the ledger's ``updated_at``, found it unmoved at
2026-09-01T18:24:55Z, and recorded that the lane COULD NOT TELL whether Alex's
18:51Z attended relaunch had happened.  CAL-P202 wrote three readings and said
"this lane cannot separate them."  The staged cursor separated them in one query.

CONTROL ARMS -- four, across two axes, per the conveyor's standing rule that a
result is worthless unless it (i) reproduces a KNOWN hit, (ii) states the SHAPE of
that hit, (iii) reports the fraction of the population it classified, and (iv)
names the population in the same noun the marker will use.

  axis A -- does the instrument get the two REAL captured states right?
    A1  known-hit / positive : observation A (19:26Z) must come out DIVERGED, and
                               the ledger-only reading must come out WRONG on it.
                               This is the hit P202 missed, replayed.
    A2  negative control     : observation B (19:42Z), after the ledger caught up,
                               must come out CONVERGED.  An instrument that always
                               says DIVERGED is a broken smoke alarm, not a gauge.

  axis B -- is the result non-vacuous and honestly sourced?
    B1  distinctness         : A1 and A2 must yield DIFFERENT verdicts.  A guard
                               whose string is common to both arms is vacuous.
    B2  provenance           : every asserted number must be read out of the
                               captured JSON, and the ms-epoch generation must
                               independently reconstruct to the recorded wall
                               clock.  No number is hardcoded in an assertion.

Runs from any cwd.  Exit 0 = all arms pass.  Non-zero = an arm failed (and per
gotcha #124, only exit 1 is a RESULT; anything else is a story about the harness).
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent  # artifacts/cal-p203 -> artifacts -> repo root
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

UTC = _dt.timezone.utc

# --------------------------------------------------------------------------
# The population, named in the SAME noun the park will use.
# --------------------------------------------------------------------------
#: The durable rows that carry the staged rebuild's unit bank. This is the
#: population the marker's noun ("the bank", "units_banked") ranges over.
BANK_BEARING_ROWS = (
    "calibration:main:staged_futures",  # written PER UNIT   (the live level)
    "calibration:main:phase_ledger",    # written at BEAT END (a copy of the above)
)


class ArmFailure(AssertionError):
    """An arm did not hold. Raised, never printed-and-continued."""


# --------------------------------------------------------------------------
# Provenance: reconcile the lease constant against its DEFINITION SITE, rather
# than re-deriving the arithmetic here. P201-3's lesson: a constant that every
# consumer re-derives is a constant nobody reads.
# --------------------------------------------------------------------------
def lease_seconds_from_source() -> float:
    """LEASE_S, taken from the two source lines that define it.

    Raises rather than guessing if either line has changed shape -- a scan guard
    must raise on what it cannot parse, not report a number.
    """
    ledger_src = (BACKEND / "app/utils/calibration_phase_ledger.py").read_text()
    build_src = (BACKEND / "app/tasks/calibration_main_build.py").read_text()

    m_hard = re.search(r"^HARD_LIMIT_MS\s*=\s*([0-9_]+)", ledger_src, re.M)
    if not m_hard:
        raise ArmFailure("cannot parse HARD_LIMIT_MS from calibration_phase_ledger.py")
    hard_ms = int(m_hard.group(1).replace("_", ""))

    m_lease = re.search(
        r"^LEASE_S\s*=\s*\(HARD_LIMIT_MS\s*/\s*1000\.0\)\s*\+\s*([0-9.]+)", build_src, re.M
    )
    if not m_lease:
        raise ArmFailure(
            "LEASE_S is no longer '(HARD_LIMIT_MS / 1000.0) + <n>' in "
            "calibration_main_build.py -- refusing to report a reconciliation "
            "against a formula that has changed"
        )
    return hard_ms / 1000.0 + float(m_lease.group(1))


def _parse_ts(s: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(s)


# --------------------------------------------------------------------------
# READING 1 -- what the conveyor currently instructs (ITEM 1b + ITEM 3 step 1).
# --------------------------------------------------------------------------
def read_ledger_only(obs: dict) -> dict:
    led = obs["phase_ledger"]
    return {
        "reading": "ledger-only (the conveyor's current instruction)",
        "last_movement_at": led["updated_at"],
        "bank": led["units_banked"],
        "generation": led["generation"],
    }


# --------------------------------------------------------------------------
# READING 2 -- both bank-bearing rows, compared.
# --------------------------------------------------------------------------
def read_both_rows(obs: dict) -> dict:
    led, cur = obs["phase_ledger"], obs["staged_futures"]
    lag_s = (_parse_ts(cur["updated_at"]) - _parse_ts(led["updated_at"])).total_seconds()
    same_gen = cur["generation"] == led["generation"]
    return {
        "reading": "both bank-bearing rows",
        "verdict": "CONVERGED" if same_gen else "DIVERGED",
        "bank_now": cur["committed_units_len"],
        "bank_as_ledger_last_reported": led["units_banked"],
        "cursor_ahead_of_ledger_s": lag_s,
        "cursor_generation_utc": _dt.datetime.fromtimestamp(
            cur["generation"] / 1000.0, UTC
        ).isoformat(),
        "ledger_generation_utc": _dt.datetime.fromtimestamp(
            led["generation"] / 1000.0, UTC
        ).isoformat(),
        "lease_expires_utc": _dt.datetime.fromtimestamp(
            cur["lease_expires_at"], UTC
        ).isoformat(),
    }


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def main() -> int:
    obs_a = load("observation-A-diverged-1926Z.json")
    obs_b = load("observation-B-converged-1942Z.json")

    lease_s = lease_seconds_from_source()
    print(f"LEASE_S from source = {lease_s:.1f}s ({lease_s / 60:.1f} min)\n")

    a_both, a_led = read_both_rows(obs_a), read_ledger_only(obs_a)
    b_both, b_led = read_both_rows(obs_b), read_ledger_only(obs_b)

    print("--- observation A (2026-09-01T19:26Z, the state P202 could not read) ---")
    for k, v in a_led.items():
        print(f"    ledger-only  {k:32s} {v}")
    for k, v in a_both.items():
        print(f"    both-rows    {k:32s} {v}")
    print("\n--- observation B (2026-09-01T19:42Z, after the ledger caught up) ---")
    for k, v in b_led.items():
        print(f"    ledger-only  {k:32s} {v}")
    for k, v in b_both.items():
        print(f"    both-rows    {k:32s} {v}")

    failures: list[str] = []

    # ---------------- A1 : known hit, replayed ----------------
    try:
        if a_both["verdict"] != "DIVERGED":
            raise ArmFailure(f"A1: expected DIVERGED, got {a_both['verdict']}")
        if a_both["bank_now"] <= a_both["bank_as_ledger_last_reported"]:
            raise ArmFailure(
                "A1: the hit's SHAPE is 'the live bank is HIGHER than the ledger's "
                f"copy'; got live={a_both['bank_now']} "
                f"ledger={a_both['bank_as_ledger_last_reported']}"
            )
        if a_both["cursor_ahead_of_ledger_s"] <= 0:
            raise ArmFailure("A1: the cursor must be NEWER than the ledger in the hit")
        # the counterfactual: the conveyor's instruction gets it wrong here
        if a_led["bank"] == a_both["bank_now"]:
            raise ArmFailure(
                "A1: ledger-only would have been RIGHT -- then there is no defect"
            )
        print(
            f"\n  [A1] PASS  known hit reproduced: ledger-only reported bank="
            f"{a_led['bank']} and 'no movement since {a_led['last_movement_at'][:19]}'; "
            f"the live bank was {a_both['bank_now']} in a generation started "
            f"{a_both['cursor_generation_utc'][:19]} "
            f"({a_both['cursor_ahead_of_ledger_s'] / 60:.1f} min ahead)."
        )
    except ArmFailure as exc:
        failures.append(str(exc))
        print(f"\n  [A1] FAIL  {exc}")

    # ---------------- A2 : negative control ----------------
    try:
        if b_both["verdict"] != "CONVERGED":
            raise ArmFailure(f"A2: expected CONVERGED, got {b_both['verdict']}")
        if b_both["bank_now"] != b_both["bank_as_ledger_last_reported"]:
            raise ArmFailure(
                "A2: once the ledger catches up the two must AGREE; got "
                f"{b_both['bank_now']} vs {b_both['bank_as_ledger_last_reported']}"
            )
        print(
            f"  [A2] PASS  negative control holds: after the ledger wrote at "
            f"{obs_b['phase_ledger']['updated_at'][:19]} both rows report "
            f"{b_both['bank_now']} on generation {b_both['ledger_generation_utc'][:19]} "
            f"-- the instrument does NOT cry wolf."
        )
    except ArmFailure as exc:
        failures.append(str(exc))
        print(f"  [A2] FAIL  {exc}")

    # ---------------- B1 : distinctness ----------------
    try:
        if a_both["verdict"] == b_both["verdict"]:
            raise ArmFailure(
                "B1: both arms produced the same verdict -- the guard is vacuous"
            )
        print(
            f"  [B1] PASS  arms are distinguishable: A={a_both['verdict']} "
            f"B={b_both['verdict']}"
        )
    except ArmFailure as exc:
        failures.append(str(exc))
        print(f"  [B1] FAIL  {exc}")

    # ---------------- B2 : provenance ----------------
    try:
        for label, obs in (("A", obs_a), ("B", obs_b)):
            for row in ("phase_ledger", "staged_futures"):
                if obs[row]["identity"] not in BANK_BEARING_ROWS:
                    raise ArmFailure(
                        f"B2: {label}/{row} identity {obs[row]['identity']!r} is not "
                        "in the named population"
                    )
        # the ms-epoch generation must reconstruct to a plausible wall clock that
        # PRECEDES the row that carries it -- an independent path to the same fact
        for label, obs in (("A", obs_a), ("B", obs_b)):
            for row in ("phase_ledger", "staged_futures"):
                gen = _dt.datetime.fromtimestamp(obs[row]["generation"] / 1000.0, UTC)
                upd = _parse_ts(obs[row]["updated_at"])
                if not (gen < upd):
                    raise ArmFailure(
                        f"B2: {label}/{row} generation {gen.isoformat()} does not "
                        f"precede its own updated_at {upd.isoformat()}"
                    )
        # the lease must reconcile to the cursor write + LEASE_S, to <1s
        cur = obs_a["staged_futures"]
        expected = _parse_ts(cur["updated_at"]).timestamp() + lease_s
        drift = abs(expected - cur["lease_expires_at"])
        if drift > 1.0:
            raise ArmFailure(
                f"B2: lease does not reconcile to updated_at + LEASE_S; drift {drift:.2f}s"
            )
        print(
            f"  [B2] PASS  provenance holds: identities in population, generations "
            f"precede their rows, lease reconciles to updated_at + LEASE_S "
            f"(drift {drift:.2f}s -- so lease_expires_at is a PER-UNIT heartbeat)."
        )
    except ArmFailure as exc:
        failures.append(str(exc))
        print(f"  [B2] FAIL  {exc}")

    # ---------------- coverage, stated honestly ----------------
    print(
        f"\nCOVERAGE. Population = the {len(BANK_BEARING_ROWS)} bank-bearing durable "
        f"rows: {', '.join(BANK_BEARING_ROWS)}.\n"
        f"  Rows the conveyor's standing instruction reads : 1 of "
        f"{len(BANK_BEARING_ROWS)} (the beat-END copy)\n"
        f"  Rows this instrument reads                     : "
        f"{len(BANK_BEARING_ROWS)} of {len(BANK_BEARING_ROWS)}\n"
        "  NOT shown: that a stale ledger ever produced a wrong SHIPPED artifact. "
        "It did not -- the publish gate reads the cursor, not the ledger. The cost "
        "is to the OPERATOR reading the ledger, which is what P200-P202 paid."
    )

    if failures:
        print(f"\nFAILED {len(failures)} arm(s).")
        return 1
    print("\nAll 4 arms passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
