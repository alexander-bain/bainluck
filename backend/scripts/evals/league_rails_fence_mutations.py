#!/usr/bin/env python3
"""RED-prove `tests/test_league_rails_query_plan.py` — LAT-P110, #2260.

A guard that has never been seen to fail is a guard nobody has tested. This
harness applies each mutation ALONE from a `cp` backup, runs the suite, requires
it to go RED, then restores and **sha256-verifies the restore** before the next
one — because a mutation that silently fails to revert turns every later result
into a lie (memory: a mutation must prove it applied).

Two ways this harness refuses rather than reporting a kill:

* a needle that does not appear EXACTLY ONCE in its file is an UNAPPLIED
  mutation, not a kill — the source moved and the harness is measuring nothing;
* a restore whose sha256 does not match the pristine copy aborts the whole run.

The per-mutant `cp`/sha256 loop is this harness's own bookkeeping and is NOT the
crash guard. That is `_mutation_guard.guarded_targets`, wrapped around the whole
run: `try/finally` does not survive SIGTERM (Python's default disposition
terminates without raising), which is how a mutant rode `bcdcd95f` into a branch
for a full cycle. `tests/test_mutation_guard.py` pins both halves, and its
`test_every_on_disk_harness_is_guarded` is what caught this file for opting out
— on the first full-suite run of the branch that added it.

Run from `backend/`:  python3 scripts/evals/league_rails_fence_mutations.py
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
ROUTE = BACKEND / "app" / "routes" / "league_futures.py"
SUITE = "tests/test_league_rails_query_plan.py"

#: (id, file, needle, replacement, why this must kill)
MUTANTS: list[tuple[str, Path, str, str, str]] = [
    (
        "M1-fence-removed",
        ROUTE,
        '        .offset(literal_column("0"))\n        .subquery()',
        "        .subquery()",
        "the whole fix: without OFFSET 0 the planner walks ix_events_commence_time",
    ),
    (
        "M2-fence-is-a-bind",
        ROUTE,
        '.offset(literal_column("0"))',
        ".offset(0)",
        "fences identically but emits OFFSET $1 — not the statement measured",
    ),
    (
        "M3-order-by-pushed-inside",
        ROUTE,
        "    fenced_event = aliased(Event, inner)\n    return (\n        select(fenced_event)\n        .order_by(fenced_event.commence_time.desc())",
        "    fenced_event = aliased(Event, inner)\n    return (\n        select(fenced_event)\n        .order_by(Event.commence_time.desc())",
        "sorting on the base table instead of the subquery re-correlates the two",
    ),
    (
        "M4-sibling-fenced-too",
        ROUTE,
        '        .order_by(\n            case((Event.status == "live", 0), else_=1),\n            Event.commence_time.asc(),\n        )',
        '        .offset(literal_column("0"))\n        .order_by(\n            case((Event.status == "live", 0), else_=1),\n            Event.commence_time.asc(),\n        )',
        "tidying the two rails into a matching pair undoes a measurement",
    ),
    (
        "M5-route-keeps-an-inline-copy",
        ROUTE,
        "        _results_q = recent_results_query(sport_key, now)",
        "        _results_q = (\n"
        "            select(Event)\n"
        "            .join(Sport, Sport.id == Event.sport_id)\n"
        "            .where(\n"
        "                Sport.key == sport_key,\n"
        '                Event.status.in_(["completed", "closed"]),\n'
        "                Event.commence_time >= now - timedelta(days=RESULTS_LOOKBACK_DAYS),\n"
        "            )\n"
        "            .order_by(Event.commence_time.desc())\n"
        "            .limit(RESULTS_LIMIT + 1)\n"
        "        )",
        "the exact pre-fix statement, back in the route while the helper stays right",
    ),
    (
        "M6-lookback-window-changed",
        ROUTE,
        "Event.commence_time >= now - timedelta(days=RESULTS_LOOKBACK_DAYS),",
        "Event.commence_time >= now - timedelta(days=7),",
        "the fence must not be cover for a quietly narrowed rail",
    ),
    (
        "M7-statuses-copy-pasted",
        ROUTE,
        'Event.status.in_(["completed", "closed"]),',
        'Event.status.in_(["live", "scheduled"]),',
        "a copy-paste between the two builders",
    ),
    (
        "M8-cap-dropped",
        ROUTE,
        ".limit(RESULTS_LIMIT + 1)",
        ".limit(RESULTS_LIMIT)",
        "the +1 is what makes the cap DECLARED rather than a silent truncation",
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
    tmp = Path(tempfile.mkdtemp(prefix="lat-p110-"))
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
                print(f"  KILLED    {mutant_id:<30} — {why}")
            elif code == 0:
                survived.append((mutant_id, "suite stayed GREEN"))
                print(f"  SURVIVED  {mutant_id:<30} — {why}")
            else:
                # gotcha #124: 1 is a result, anything else is a story about the
                # harness. A collection error is not a kill.
                unapplied.append(
                    (mutant_id, f"pytest exit {code} — harness, not verdict")
                )
                print(f"  HARNESS   {mutant_id:<30} exit {code}\n{tail}")

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
    """The crash guard, outside the per-mutant bookkeeping.

    `_main`'s own `cp` + sha256 loop restores after each mutant and is the thing
    that keeps mutant N from contaminating mutant N+1. It cannot help if the
    process is killed mid-mutation, because its `finally` never runs under
    SIGTERM. `guarded_targets` registers a signal handler and an on-disk
    manifest so the next run — or `python3 scripts/evals/_mutation_guard.py
    --recover` — puts the file back.
    """
    with guarded_targets([ROUTE], "/tmp/lat_p110_fence_guard_backups", "league_rails_fence"):
        return _main()


if __name__ == "__main__":
    raise SystemExit(main())
