#!/usr/bin/env python3
"""RED-prove `tests/test_cold_path_rejected_samples.py` — LAT-P110, #2260.

Four ways to put the rate limiter back into the medians, each applied ALONE from
a `cp` backup, each required to turn the suite RED, each sha256-verified
restored before the next.

Two refusals rather than false kills:

* a needle that does not appear EXACTLY ONCE is an UNAPPLIED mutation, not a
  kill — the source moved and this harness is measuring nothing;
* a restore that does not match the pristine sha256 aborts the run.

And the crash guard is `_mutation_guard.guarded_targets`, not the `cp` loop:
`try/finally` does not survive SIGTERM, which is how a mutant once rode a
commit into a branch for a full cycle. See `tests/test_mutation_guard.py`.

Run from `backend/`:
    python3 scripts/evals/cold_path_rejected_sample_mutations.py
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _mutation_guard import guarded_targets  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]
SNAPSHOT = BACKEND / "scripts" / "cold_path_snapshot.py"
SUITE = "tests/test_cold_path_rejected_samples.py"

#: (id, file, needle, replacement, why this must kill)
MUTANTS: list[tuple[str, Path, str, str, str]] = [
    (
        "R1-status-code-unchecked",
        SNAPSHOT,
        '    http = sample.get("http")\n    if http is not None and http != 200:\n        return REJECTED\n',
        "",
        "the defect itself: a 429 falls through to the query-count branch and grades warm",
    ),
    (
        "R2-transport-failure-unchecked",
        SNAPSHOT,
        '    if sample.get("error") is not None:\n        return REJECTED\n',
        "",
        "a timed-out request has no http at all and would grade unknown, then vanish quietly",
    ),
    (
        "R3-graded-filter-loosened",
        SNAPSHOT,
        '        r for r in rows if r.get("server_ms") is not None and r.get("class") != REJECTED\n',
        '        r for r in rows if r.get("server_ms") is not None\n',
        "the classifier is right but the summary lets the 429s back into n_graded",
    ),
    (
        "R4-rejections-not-counted",
        SNAPSHOT,
        '        if r.get("class") != REJECTED:\n            continue',
        "        if True:\n            continue",
        "a silent exclusion is as bad as a wrong inclusion — the throttle must be LOUD",
    ),
    (
        "R5-a-200-treated-as-rejected",
        SNAPSHOT,
        "if http is not None and http != 200:",
        "if http is not None:",
        "the other direction: over-rejecting would empty every median and read as a refusal",
    ),
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_suite() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q", "--no-header", "-x"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout[-1200:]


def _main() -> int:
    baseline_code, baseline_tail = _run_suite()
    if baseline_code != 0:
        print("ABORT: the suite is not GREEN before mutating.")
        print(baseline_tail)
        return 2
    print(f"baseline GREEN (exit {baseline_code})\n")

    pristine: dict[Path, tuple[Path, str]] = {}
    tmp = Path(tempfile.mkdtemp(prefix="lat-p110-cps-"))
    for _, path, _, _, _ in MUTANTS:
        if path not in pristine:
            backup = tmp / path.name
            shutil.copy2(path, backup)
            pristine[path] = (backup, _sha(path))

    killed: list[str] = []
    survived: list[tuple[str, str]] = []
    unapplied: list[tuple[str, str]] = []

    try:
        for mutant_id, path, needle, replacement, why in MUTANTS:
            original = path.read_text()
            hits = original.count(needle)
            if hits != 1:
                unapplied.append(
                    (mutant_id, f"needle appears {hits} times, expected 1")
                )
                print(f"  UNAPPLIED {mutant_id}: needle x{hits}")
                continue

            path.write_text(original.replace(needle, replacement, 1))
            assert path.read_text() != original, f"{mutant_id}: write was a no-op"

            code, tail = _run_suite()
            if code == 1:
                killed.append(mutant_id)
                print(f"  KILLED    {mutant_id:<32} — {why}")
            elif code == 0:
                survived.append((mutant_id, "suite stayed GREEN"))
                print(f"  SURVIVED  {mutant_id:<32} — {why}")
            else:
                # gotcha #124: 1 is a result, anything else is a story about the
                # harness. A collection error is not a kill.
                unapplied.append(
                    (mutant_id, f"pytest exit {code} — harness, not verdict")
                )
                print(f"  HARNESS   {mutant_id:<32} exit {code}\n{tail}")

            backup, sha = pristine[path]
            shutil.copy2(backup, path)
            if _sha(path) != sha:
                print(f"FATAL: restore of {path} did not match sha256 — aborting.")
                return 3
    finally:
        for path, (backup, sha) in pristine.items():
            shutil.copy2(backup, path)
            if _sha(path) != sha:
                print(f"FATAL: final restore of {path} mismatched sha256.")
                return 3
        shutil.rmtree(tmp, ignore_errors=True)

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed · {len(survived)} survived · "
        f"{len(unapplied)} unapplied"
    )
    for mid, why in survived + unapplied:
        print(f"  ! {mid}: {why}")

    final_code, final_tail = _run_suite()
    print(f"post-restore suite exit {final_code}")
    if final_code != 0:
        print(final_tail)
        return 3
    return 0 if not survived and not unapplied else 1


def main() -> int:
    with guarded_targets(
        [SNAPSHOT], "/tmp/lat_p110_cps_guard_backups", "cold_path_rejected_sample"
    ):
        return _main()


if __name__ == "__main__":
    raise SystemExit(main())
