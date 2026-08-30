#!/usr/bin/env python3
"""CAL-P143 — exercise the D22 mechanism against the PATCHED producer, without
writing to the frozen file.

Same shape as ``verify-12cal-suite.py``: patch scratch copies under /tmp, import
them under their own module names, and run the assertions. Three things are
checked, and only the first is a text check:

1.  both patched files compile;
2.  ``_build_truth_evidence`` reports UNOBSERVED for a census that did not run,
    and does NOT report a clean contract on no evidence — the actual defect the
    naive fix (``truth_by_class = {}``) would introduce;
3.  ``PhaseRunner.soft_stage`` swallows a raising body, rolls the savepoint
    back, names the stage in ``degraded_stages``, and — the part that matters —
    leaves the caller able to keep using the session.

Run from ``backend/``::

    python3 ../artifacts/cal-p143/verify-d22.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import py_compile
import subprocess
import sys
import types

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
BACKEND = REPO / "backend"
SCRATCH = pathlib.Path("/tmp/cal-p143-d22-verify")

sys.path.insert(0, str(BACKEND))

FILES = (
    "backend/app/tasks/precompute_calibration.py",
    "backend/app/tasks/calibration_main_build.py",
)


def build_scratch() -> None:
    for rel in FILES:
        dst = SCRATCH / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((REPO / rel).read_bytes())
    r = subprocess.run(
        ["patch", "-p1", "--batch", "--silent",
         "-i", str(HERE / "d22-diagnostics-nonblocking.patch")],
        cwd=SCRATCH, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"FATAL: D22 patch did not apply:\n{r.stderr}")


def load(rel: str, name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRATCH / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeSavepoint:
    def __init__(self, log):
        self.log = log

    async def rollback(self):
        self.log.append("rollback")

    async def commit(self):
        self.log.append("commit")


class _FakeSession:
    """Just enough session to prove the savepoint discipline."""

    def __init__(self):
        self.log: list[str] = []

    async def begin_nested(self):
        self.log.append("begin_nested")
        return _FakeSavepoint(self.log)


def main() -> int:
    build_scratch()
    ok = True

    for rel in FILES:
        py_compile.compile(str(SCRATCH / rel), doraise=True)
    print(f"  compiles: {len(FILES)}/{len(FILES)} patched files")

    prod = load(FILES[0], "precompute_calibration_d22")
    run = load(FILES[1], "calibration_main_build_d22")

    common = dict(mex_normalized_markets=7, mex_published_markets=7,
                  published_outcomes=100, published_questions=50)

    # --- the census DID run, clean ----------------------------------------
    good = prod._build_truth_evidence(
        {"eligible": {"outcomes": 10, "markets": 2}}, **common)
    if not (good["census_observed"] is True
            and good["contract_ok"] is True
            and good["contract_status"] == "ok"):
        ok = False
        print(f"  🔴 a clean observed census does not read as ok: {good['contract_status']}")
    else:
        print("  observed + clean  -> contract_ok True,  status 'ok'")

    # --- the census DID run and found an unknown source --------------------
    bad = prod._build_truth_evidence(
        {"unknown": {"outcomes": 3, "markets": 1}}, **common)
    if not (bad["census_observed"] is True and bad["contract_ok"] is False
            and bad["contract_status"] == "violated"):
        ok = False
        print("  🔴 a real violation no longer reads as one")
    else:
        print("  observed + violation -> contract_ok False, status 'violated'")

    # --- the census did NOT run -------------------------------------------
    deg = prod._build_truth_evidence(None, **common)
    if deg["census_observed"] is not False or deg["contract_status"] != "unobserved":
        ok = False
        print("  🔴 an unobserved census is not reported as unobserved")
    elif deg["contract_ok"] is not None:
        ok = False
        print(f"  🔴 unobserved reports contract_ok={deg['contract_ok']!r} — a "
              "reader would take it for a verdict")
    else:
        print("  unobserved       -> contract_ok None,  status 'unobserved'")

    # --- unobserved, but the partition invariant DID break -----------------
    both = prod._build_truth_evidence(
        None, mex_normalized_markets=7, mex_published_markets=9,
        published_outcomes=100, published_questions=50)
    if both["contract_ok"] is not False or both["contract_status"] != "violated":
        ok = False
        print(f"  🔴 a violation found on a degraded beat reads as "
              f"{both['contract_status']!r} — it must outrank 'unobserved'")
    else:
        print("  unobserved + real violation -> contract_ok False, "
              "status 'violated' (a violation outranks a missing census)")

    # The naive alternative, stated so the choice is visible: an empty dict
    # would have produced contract_ok True on zero evidence.
    naive = prod._build_truth_evidence({}, **common)
    if naive["contract_ok"] is not True:
        print("  (note: the empty-dict path no longer reads clean either)")
    else:
        print("  the rejected alternative ({} instead of None) would have read "
              "contract_ok=True on no evidence — which is why None is used")

    # --- soft_stage ---------------------------------------------------------
    async def exercise() -> None:
        nonlocal ok
        runner = run.PhaseRunner.__new__(run.PhaseRunner)
        runner.degraded_stages = []
        runner.ledger = None

        import contextlib as _c

        @_c.contextmanager
        def _stage(name):  # the timing wrapper is not what is under test
            yield
        runner.stage = _stage

        db = _FakeSession()
        async with runner.soft_stage(db, "read:truth_census") as soft:
            raise RuntimeError("canceling statement due to statement timeout")
        if not soft.failed:
            ok = False
            print("  🔴 soft_stage did not mark the outcome failed")
        elif db.log != ["begin_nested", "rollback"]:
            ok = False
            print(f"  🔴 savepoint discipline wrong: {db.log}")
        elif runner.degraded_stages != ["read:truth_census"]:
            ok = False
            print(f"  🔴 degradation not named: {runner.degraded_stages}")
        else:
            print("  soft_stage: raising body -> swallowed, rolled back, named")

        db2 = _FakeSession()
        async with runner.soft_stage(db2, "read:date_range") as soft2:
            pass
        if soft2.failed or db2.log != ["begin_nested", "commit"]:
            ok = False
            print(f"  🔴 the happy path is not clean: {db2.log}")
        else:
            print("  soft_stage: clean body   -> committed, not degraded")

    asyncio.run(exercise())

    print("VERDICT: " + ("D22 PRE-BUILD VERIFIED" if ok else "🔴 D22 PRE-BUILD BROKEN"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
