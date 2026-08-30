#!/usr/bin/env python3
"""LAT-P147 (#2328) mutation battery for the top-1 observation loader.

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible way a later edit breaks this — and the
edits this ship is most exposed to are the ones that look like TIDYING, because
**every one of them leaves the answer correct and changes only the plan**. No
route test, no contract test and no eyeball catches those. A measurement does,
and these assertions are the measurement's standing deputy.

The three this battery exists for:

  * **M1 — dropping `captured_at IS NOT NULL`.** The predicate looks redundant
    next to an `ORDER BY ... DESC`, and in SQLite it would be. In PostgreSQL
    `DESC` is `NULLS FIRST`, so a single NULL-`captured_at` row makes its whole
    outcome report `None` where `max()` reported a real time. It is the one way
    this rewrite is not answer-identical.
  * **M2 — "fixing" M1's risk with `NULLS LAST`.** Answer-identical and **19x
    slower** (124 ms -> 2,408 ms; 3,503 -> 177,719 buffer blocks, measured on
    production 2026-08-30). The clause does not match the index's ordering, so
    each probe becomes a Sort over the whole group — the aggregate's cost back
    again, and nothing goes red.
  * **M7 — putting the aggregate back.** `max() ... GROUP BY` is the shorter,
    more familiar spelling. It read 342,059 rows to return 514.

Mutations are applied to the real source files, the suite is run to completion,
and the files are restored — SERIALLY. Never concurrently, and never while
another pytest is in flight: `inspect.getsource` re-reads the file mid-run and a
source edit under a running suite produces phantom failures that read as real
reds.

The `try/finally` in `_main()` restores on an exception; it does NOT survive a
SIGTERM or SIGKILL. `guarded_targets` is the shared primitive that closes that
window (manifest + `--recover`).

Run:  python3 backend/scripts/evals/latest_observation_mutations.py
Exit: 0 = every mutant killed. 1 = at least one survived. Anything else is the
      harness failing, not a verdict (gotcha #54).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _mutation_guard import guarded_targets  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
LOADER = ROOT / "app" / "utils" / "latest_observation.py"
ROUTE = ROOT / "app" / "routes" / "tournaments.py"
SUITE = ROOT / "tests" / "test_latest_observation_lat_p147.py"
ROUTE_SUITE = ROOT / "tests" / "integration" / "test_route_tournaments.py"

#: (id, description, target, old, new). `old` must appear EXACTLY once in
#: `target` — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill.
#:
#: 🔴 Needles and replacements are spelled CONTIGUOUSLY and verbatim. An escaped
#: needle is absent from the file by construction, so the residue scanner reads
#: the harness as holding a replacement with no needle and goes red on itself
#: (`tennis_population_mutations` lost two rounds to exactly this).
MUTANTS: list[tuple[str, str, pathlib.Path, str, str]] = [
    (
        "M1",
        "drop the NULL-captured_at predicate — a NULL row wins its own group under DESC",
        LOADER,
        "            FuturesOddsSnapshot.captured_at.isnot(None),\n"
        "        )\n"
        "        .order_by(FuturesOddsSnapshot.captured_at.desc())",
        "        )\n        .order_by(FuturesOddsSnapshot.captured_at.desc())",
    ),
    (
        "M2",
        "order NULLS LAST — answer-identical, 19x slower, and nothing goes red",
        LOADER,
        "        .order_by(FuturesOddsSnapshot.captured_at.desc())",
        "        .order_by(FuturesOddsSnapshot.captured_at.desc().nullslast())",
    ),
    (
        "M3",
        "order ascending — the OLDEST observation, reported as the newest",
        LOADER,
        "        .order_by(FuturesOddsSnapshot.captured_at.desc())",
        "        .order_by(FuturesOddsSnapshot.captured_at.asc())",
    ),
    (
        "M4",
        "order by the wrong column — the highest id, not the latest time",
        LOADER,
        "        .order_by(FuturesOddsSnapshot.captured_at.desc())",
        "        .order_by(FuturesOddsSnapshot.outcome_id.desc())",
    ),
    (
        "M5",
        "take two rows per outcome — it stops being a top-1 probe",
        LOADER,
        # 🔴 RE-POINTED OFF "DELETE THE LIMIT", AND THE RESIDUE SCAN IS WHY.
        # That form's needle spanned two lines, so it could only be written with
        # a `\n` escape — which makes it ABSENT FROM THIS FILE by construction —
        # while its replacement was the surviving line, present verbatim as M2's
        # needle. Pass B reads that as a file holding a replacement with no
        # needle and goes red on the harness. Both halves are now single-line
        # and under Pass B's 24-char coincidence floor, and `.limit(2)` is the
        # better mutant anyway: a scalar subquery returning two rows is an error
        # in PostgreSQL, not merely a slower plan.
        ".limit(1)",
        ".limit(2)",
    ),
    (
        "M6",
        "drop the priced predicate — an unpriced row becomes an observation",
        LOADER,
        "            FuturesOddsSnapshot.probability.isnot(None),\n",
        "",
    ),
    (
        "M7",
        "put the aggregate back — 342,059 rows read to return 514",
        LOADER,
        "        .order_by(FuturesOddsSnapshot.captured_at.desc())\n"
        "        .limit(1)\n"
        "        .correlate(FuturesOutcome)",
        "        .group_by(FuturesOddsSnapshot.outcome_id)\n"
        "        .correlate(FuturesOutcome)",
    ),
    (
        "M8",
        "switch correlation off — the subquery grows its own FROM and cross-joins",
        LOADER,
        "        .correlate(FuturesOutcome)",
        "        .correlate(None)",
    ),
    (
        "M9",
        "keep the unobserved outcomes — present with None instead of absent",
        LOADER,
        "    return {row.id: row.observed_at for row in rows if row.observed_at is not None}",
        "    return {row.id: row.observed_at for row in rows}",
    ),
    (
        "M10",
        "key the mapping by the time instead of the outcome",
        LOADER,
        "    return {row.id: row.observed_at for row in rows if row.observed_at is not None}",
        "    return {row.observed_at: row.id for row in rows if row.observed_at is not None}",
    ),
    (
        "M11",
        "do not materialise the ids — a generator is always truthy and empties on first read",
        LOADER,
        "    ids = list(outcome_ids)\n    if not ids:",
        "    ids = outcome_ids\n    if not ids:",
    ),
    (
        "M12",
        "drop the empty short-circuit — no ids issues a query for the whole table",
        LOADER,
        "    if not ids:\n        return {}\n",
        "",
    ),
    (
        "M13",
        "drop the outer id bound — one index probe per outcome in the table",
        LOADER,
        "            ).where(FuturesOutcome.id.in_(ids))",
        "            )",
    ),
    (
        "M14",
        "stop loading freshness at all — every price reports never-observed",
        ROUTE,
        "    observed_by_id = await load_latest_observed_at(session, outcome_ids)",
        "    observed_by_id = {}",
    ),
    (
        "M15",
        "ask the loader about nothing — the call is present and answers nothing",
        ROUTE,
        "    observed_by_id = await load_latest_observed_at(session, outcome_ids)",
        "    observed_by_id = await load_latest_observed_at(session, [])",
    ),
]


def _run_suite() -> int:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(SUITE),
            str(ROUTE_SUITE),
            "-q",
            "--no-header",
            "-x",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    with guarded_targets(
        [LOADER, ROUTE],
        "/tmp/lat_p147_latest_observation_guard_backups",
        "latest_observation",
    ):
        return _main()


def _main() -> int:
    originals = {path: path.read_text() for path in (LOADER, ROUTE)}

    baseline = _run_suite()
    if baseline != 0:
        print(
            f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
            "Nothing below is a verdict."
        )
        return 2
    # The DENOMINATOR before the first verdict: a run that prints only its kills
    # reads as a clean sweep over whatever survived the edit.
    print(
        f"baseline: suite GREEN on the unmutated tree "
        f"({len(MUTANTS)} mutants queued across {len(originals)} targets)\n"
    )

    killed, survived, broken = [], [], []
    try:
        for mid, desc, target, old, new in MUTANTS:
            original = originals[target]
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times in {target.name}"))
                print(
                    f"{mid:4} HARNESS  {desc}\n"
                    f"     anchor matched {n} times in {target.name} — not a verdict"
                )
                continue
            target.write_text(original.replace(old, new, 1))
            rc = _run_suite()
            target.write_text(original)  # restore before anything else runs
            if rc == 0:
                survived.append((mid, desc))
                print(f"{mid:4} SURVIVED {desc}")
            elif rc == 1:
                killed.append(mid)
                print(f"{mid:4} killed   {desc}")
            else:
                broken.append((mid, f"pytest exit {rc}"))
                print(
                    f"{mid:4} HARNESS  {desc}\n"
                    f"     pytest exit {rc} — the gate never ran"
                )
    finally:
        for path, text in originals.items():
            path.write_text(text)

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed, {len(survived)} survived, "
        f"{len(broken)} harness failures"
    )
    for mid, desc in survived:
        print(f"  SURVIVED {mid}: {desc}")
    for mid, why in broken:
        print(f"  HARNESS  {mid}: {why}")
    if broken:
        return 2
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
