#!/usr/bin/env python3
"""Partition the backend test suite across CI shards — totally and disjointly.

Queue 312, Item 1. `backend-tests` was 8m23s of a 9m31s merge-to-deploy path, so
splitting it is the entire wall-clock prize. No new dependency: no pytest-xdist,
no pytest-split (see the queue's premise P5).

WHY THIS IS AN ENUMERATE-AND-ASSIGN PARTITION, NOT A SET OF PATH GLOBS
----------------------------------------------------------------------
The obvious way to shard in a matrix is to give each leg a glob:

    shard 1: pytest tests/integration
    shard 2: pytest tests/test_a*.py
    ...

That design has one failure mode and it is silent: a test file matched by NO
glob is never run, by anyone, and the suite goes green having tested less. The
signal — a green check — is identical to the healthy case. Nothing in CI can
tell you it happened, and it stays true until someone notices a bug that a
deleted test used to catch.

So this script never matches; it ENUMERATES the collected files and assigns each
one to exactly one shard. Totality and disjointness are then properties of the
function rather than properties of a hand-maintained pattern list, and a new
test file joins a shard automatically the day it is added.

The residual risk is that the *enumeration* disagrees with what pytest itself
would collect. That is what `--verify` exists for: it asks pytest for the
authoritative list and diffs it against ours. See the `shard-completeness` job.

BALANCE
-------
Assignment is longest-processing-time-first (LPT) greedy bin-packing against
measured per-file durations in `ci_shard_durations.json`. LPT is within 4/3 of
optimal, which is far inside the noise of a GitHub runner. Files with no
recorded duration get `DEFAULT_WEIGHT` so a newly-added file is never free and
never dominant; refresh the JSON with `--record` after a `--durations=0` run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TESTS_DIR = BACKEND / "tests"
DURATIONS_FILE = Path(__file__).resolve().parent / "ci_shard_durations.json"

# Seconds assumed for a test file we have no measurement for. Deliberately a bit
# above the median so an unmeasured newcomer is packed early (LPT places the
# biggest items first, where balance is decided) rather than dumped into
# whichever bin happens to be last.
DEFAULT_WEIGHT = 2.0


def discover_test_files() -> list[str]:
    """Every `test_*.py` under tests/, as posix paths relative to backend/.

    Mirrors pytest's default `python_files = test_*.py`. `--verify` proves this
    agrees with pytest rather than assuming it.
    """
    found = [
        p.relative_to(BACKEND).as_posix()
        for p in TESTS_DIR.rglob("test_*.py")
        if "__pycache__" not in p.parts
    ]
    return sorted(found)


def load_durations() -> dict[str, float]:
    if not DURATIONS_FILE.exists():
        return {}
    try:
        with DURATIONS_FILE.open() as fh:
            return {k: float(v) for k, v in json.load(fh).get("files", {}).items()}
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        # Never fail the build over a corrupt balance hint. Balance is an
        # optimisation; correctness of the partition does not depend on it.
        print(f"::warning::could not read {DURATIONS_FILE.name} ({exc}) — using equal weights")
        return {}


def partition(files: list[str], shards: int) -> list[list[str]]:
    """LPT greedy bin-packing. Deterministic: same inputs, same output, anywhere.

    Ties break on the filename so two runners computing this independently
    always agree — a shard that disagreed with its siblings about who owns a
    file would either double-run it or skip it.
    """
    weights = load_durations()
    ordered = sorted(files, key=lambda f: (-weights.get(f, DEFAULT_WEIGHT), f))
    bins: list[list[str]] = [[] for _ in range(shards)]
    loads = [0.0] * shards
    for f in ordered:
        i = loads.index(min(loads))
        bins[i].append(f)
        loads[i] += weights.get(f, DEFAULT_WEIGHT)
    return [sorted(b) for b in bins]


def pytest_collected_files() -> tuple[list[str], str]:
    """Ask pytest which files it would actually collect. The authority.

    Uses `--collect-only -q`, whose output lines are `path::test_name[params]`.
    A collection ERROR here is itself a failure worth reporting: it means some
    file cannot even be imported, which a path-glob shard would have hidden.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q",
         # `-o addopts=` clears pytest.ini's `addopts = -v --tb=short`. Without it the
         # ini's -v cancels our -q, verbosity lands at 0, and --collect-only prints the
         # <Dir>/<Module> TREE instead of node ids — so this parser silently found zero
         # tests and the census reported an empty suite. Found the first time it ran.
         "-o", "addopts=", "-p", "no:cacheprovider"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    files: set[str] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("="):
            continue
        m = re.match(r"^(tests/[^:\s]+\.py)::", line)
        if m:
            files.add(m.group(1))
    return sorted(files), proc.stdout[-4000:] + proc.stderr[-4000:]


def cmd_list(args: argparse.Namespace) -> int:
    files = discover_test_files()
    bins = partition(files, args.of)
    print(" ".join(bins[args.shard - 1]))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Prove the partition is total and disjoint against pytest's own collection.

    Item 1.4. Without this, Item 1's failure mode is invisible and permanent.
    """
    ours = discover_test_files()
    bins = partition(ours, args.of)

    failures: list[str] = []

    # 1. Disjoint + total with respect to our own enumeration.
    union: list[str] = [f for b in bins for f in b]
    if len(union) != len(set(union)):
        dupes = sorted({f for f in union if union.count(f) > 1})
        failures.append(f"files assigned to more than one shard (would run twice): {dupes}")
    if set(union) != set(ours):
        missing = sorted(set(ours) - set(union))
        failures.append(f"files in no shard at all (would never run): {missing}")

    # 2. Our enumeration vs pytest's. This is the half that catches a file we
    #    failed to see — the whole reason this check is not just arithmetic.
    collected, raw = pytest_collected_files()
    if not collected:
        failures.append(
            "pytest --collect-only returned no test files. Collection itself is broken; "
            f"refusing to certify a partition over an empty set.\n--- pytest output ---\n{raw}"
        )
    else:
        unseen = sorted(set(collected) - set(ours))
        phantom = sorted(set(ours) - set(collected))
        if unseen:
            failures.append(
                "pytest collects these files but the shard partition never saw them, so no "
                f"shard runs them: {unseen}"
            )
        if phantom:
            # Not fatal on its own: a file with zero test functions is collected
            # by neither, and an all-skipped file still appears. Report it so it
            # cannot quietly become the first case of real drift.
            print(
                "::warning::assigned to a shard but contributing no collected tests "
                f"(empty or fully-skipped?): {phantom}"
            )

    loads = [
        round(sum(load_durations().get(f, DEFAULT_WEIGHT) for f in b), 1) for b in bins
    ]
    print(f"shards={args.of} files={len(ours)} collected={len(collected)} est_seconds={loads}")
    if loads and min(loads) > 0:
        skew = (max(loads) - min(loads)) / min(loads) * 100
        print(f"estimated shard skew: {skew:.1f}% (slowest vs fastest)")

    if failures:
        for f in failures:
            print(f"::error::shard completeness check FAILED — {f}")
        print(
            "\nThe shard partition does not cover the suite. Do NOT dismiss this as a "
            "tooling problem: it means CI is reporting green over tests it did not run."
        )
        return 1

    print("shard partition is total and disjoint, and matches pytest's collection.")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    """Rebuild the balance hints from a `pytest --durations=0` log.

    Sums every per-test duration back onto its file. Read from a file or stdin:
        python -m pytest tests/ -q --durations=0 | python scripts/ci_shard.py --record -

    ⚠️ THE PRINTED LINES ARE NOT THE WHOLE RUNTIME. pytest suppresses durations
    below 0.005s and says so only in a parenthetical:

        (37332 durations < 0.005s hidden.  Use -vv to show these durations.)

    On the 2026-08-10 measurement that was 37,332 hidden entries against a 439.8s
    total — up to ~40% of the wall-clock invisible in the lines this parser can
    see. Summing only the printed lines would therefore rate a file of 500 fast
    unit tests at ~0s and pack it as if it were free, which is exactly the sort
    of quiet mis-weighting that makes one shard the new long pole.

    So each file's weight is its measured seconds PLUS an estimate for its
    unprinted tests: (tests collected in that file - tests printed for it) × the
    expected value of a sub-threshold test, ~0.0025s. The collection census comes
    from pytest itself.
    """
    text = sys.stdin.read() if args.record == "-" else Path(args.record).read_text()
    per_file: dict[str, float] = {}
    printed_count: dict[str, int] = {}
    # e.g. "1.23s call     tests/test_x.py::TestY::test_z"
    pat = re.compile(r"^([0-9.]+)s\s+(?:call|setup|teardown)\s+(tests/[^:\s]+\.py)::")
    for line in text.splitlines():
        m = pat.match(line.strip())
        if m:
            per_file[m.group(2)] = per_file.get(m.group(2), 0.0) + float(m.group(1))
            printed_count[m.group(2)] = printed_count.get(m.group(2), 0) + 1
    if not per_file:
        print("::error::no `Ns call tests/...` duration lines found — was --durations=0 used?")
        return 1

    # Census the suite so files whose tests were all below the print threshold
    # still get a non-trivial weight.
    print("collecting test counts per file to account for sub-threshold durations...")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q",
         # `-o addopts=` clears pytest.ini's `addopts = -v --tb=short`. Without it the
         # ini's -v cancels our -q, verbosity lands at 0, and --collect-only prints the
         # <Dir>/<Module> TREE instead of node ids — so this parser silently found zero
         # tests and the census reported an empty suite. Found the first time it ran.
         "-o", "addopts=", "-p", "no:cacheprovider"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    n_tests: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        m = re.match(r"^(tests/[^:\s]+\.py)::", line.strip())
        if m:
            n_tests[m.group(1)] = n_tests.get(m.group(1), 0) + 1
    if n_tests:
        HIDDEN_EV = 0.0025  # expected seconds for a test pytest declined to print
        for f, total in n_tests.items():
            # printed_count counts phases (call/setup/teardown), so it can exceed
            # the test count; clamp so a well-instrumented file is never inflated.
            hidden = max(0, total - printed_count.get(f, 0))
            per_file[f] = per_file.get(f, 0.0) + hidden * HIDDEN_EV
        est = sum(per_file.values())
        print(f"  census: {len(n_tests)} files, {sum(n_tests.values())} tests; weighted total {est:.1f}s")
    else:
        print("::warning::collection census empty — weights use printed durations only")
    DURATIONS_FILE.write_text(
        json.dumps(
            {
                "_comment": (
                    "Per-file backend test seconds, summed over call+setup+teardown from a "
                    "`pytest --durations=0` run. Balance hints for scripts/ci_shard.py ONLY — "
                    "correctness of the partition does not depend on these being current. "
                    "Refresh: python scripts/ci_shard.py --record <log>"
                ),
                "files": {k: round(v, 3) for k, v in sorted(per_file.items())},
            },
            indent=2,
        )
        + "\n"
    )
    total = sum(per_file.values())
    print(f"recorded {len(per_file)} files, {total:.1f}s total → {DURATIONS_FILE.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--of", type=int, default=int(os.environ.get("SHARD_TOTAL", 4)), help="number of shards")
    ap.add_argument("--shard", type=int, help="1-based shard index; prints that shard's files")
    ap.add_argument("--verify", action="store_true", help="assert the partition is total and disjoint")
    ap.add_argument("--record", metavar="LOG", help="rebuild duration hints from a --durations=0 log ('-' for stdin)")
    args = ap.parse_args()

    if args.of < 1:
        print("::error::--of must be >= 1")
        return 2
    if args.record:
        return cmd_record(args)
    if args.verify:
        return cmd_verify(args)
    if args.shard:
        if not 1 <= args.shard <= args.of:
            print(f"::error::--shard {args.shard} out of range 1..{args.of}")
            return 2
        return cmd_list(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
