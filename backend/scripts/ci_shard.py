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

# HOW MANY UNMEASURED FILES IS "STALE" — A COUNT, NOT A RATIO (#3497).
#
# This was `STALE_HINTS_COVERAGE_PCT = 90.0` and it took master red twice in five
# days (2026-09-06 and 2026-09-11), each time on no branch's change. A ratio
# cannot work here: adding a test file raises the denominator and leaves the
# numerator frozen, so coverage falls on every push and the numerator only moves
# when a human runs `--record`. The metric therefore decays monotonically and the
# repo grows into the threshold on whichever push happens to be in the slot.
#
# Both crossings read 89.90%. That is the tell — it does not wander, it sits just
# above the floor and steps through, because the crossing is an artifact of where
# the denominator landed rather than a statement about the hints. Measured: 134
# unmeasured files at the first crossing, 167 at the second, with the suite going
# 1,335 -> 1,654 files in five days (~60 new test files a day, and ~1,080 -> 1,654
# since 2026-09-01 at the same rate).
#
# So the guard now counts UNMEASURED FILES. That number means the same thing at
# any suite size: how many files are being packed at DEFAULT_WEIGHT instead of a
# measurement. It still rises as files are added, but a crossing now says
# "nobody has refreshed in N days" instead of "the suite grew".
#
# WHY THE HARD LIMIT IS GENEROUS AND THE WARNING IS TIGHT. The two errors are not
# symmetric. Being too loose costs WALL CLOCK on one CI shard — `--verify` proves
# the partition stays total and disjoint whatever the weights say, so correctness
# is never at stake. Being too tight reds master for EVERY lane at once: on
# 2026-09-11 that was ~62 minutes with `deploy` skipped, production pinned an hour
# behind, and three lanes independently building the same one-file repair. The
# expensive failure is the false red, so the hard limit sits where only genuine
# neglect reaches it (~10 days of total silence at the measured rate) and the
# warning fires early enough to make refreshing a scheduled chore instead of an
# emergency.
STALE_HINTS_WARN_UNMEASURED = 150
STALE_HINTS_MAX_UNMEASURED = 600


# A GitHub Actions log line is never bare, and the parser below is line-anchored.
#
# #3497: the failing guard told the reader to run `--record <log>` on "a CI run's
# logs" — the only log a lane can actually obtain — and that command exited 1 on
# it, every time. `^([0-9.]+)s` cannot match a line beginning with a timestamp:
# `[0-9.]+` eats `2026` and then wants an `s`. Zero lines matched, so `--record`
# took its own "no duration lines found" branch and sent the reader off to
# re-check `--durations=0`, which had been correct all along. It survived because
# it reads as operator error rather than a defect. Two lanes hit it independently
# on 2026-09-11 and both worked around it by hand.
#
# Two prefix shapes reach a lane, and both are handled:
#   zip artifact      "2026-09-11T11:49:57.5647990Z 1.23s call tests/x.py::T::t"
#   gh run view --log "job\tstep\t2026-09-11T11:49:57.5647990Z 1.23s call ..."
# Some runners also emit a UTF-8 BOM on the first line of a step.
_LOG_LINE_PREFIX = re.compile(r"^(?:[^\t]*\t)*\d{4}-\d{2}-\d{2}T[\d:.]+Z\s+")


def hint_coverage(files: list[str], weights: dict) -> tuple[int, int]:
    """`(measured, unmeasured)` for these files against these weights."""
    measured = sum(1 for f in files if f in weights)
    return measured, len(files) - measured


def hints_are_stale(unmeasured: int) -> bool:
    """THE staleness verdict. One function so two callers cannot drift apart.

    The pytest guard and `--verify` used to each compute this inline against a
    shared constant, which is a convention rather than a guarantee. It is a
    function now so the #3497 property — the verdict depends on the number of
    unmeasured files and NOT on the size of the suite — has one place to be true
    and one place to be tested.
    """
    return unmeasured > STALE_HINTS_MAX_UNMEASURED


def hints_need_refresh(unmeasured: int) -> bool:
    """The earlier, warn-only threshold. Crossing this is a chore, not a failure."""
    return unmeasured > STALE_HINTS_WARN_UNMEASURED


def _strip_log_prefix(line: str) -> str:
    """A raw log line reduced to what pytest actually printed.

    A no-op on local `pytest --durations=0` output, so one code path serves both
    a piped local run and a downloaded Actions log.
    """
    return _LOG_LINE_PREFIX.sub("", line.lstrip("﻿").strip())


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

    weights = load_durations()
    loads = [round(sum(weights.get(f, DEFAULT_WEIGHT) for f in b), 1) for b in bins]
    print(f"shards={args.of} files={len(ours)} collected={len(collected)} est_seconds={loads}")

    # THE SKEW NUMBER IS ONLY WORTH THE WEIGHTS IT IS COMPUTED FROM, SO SAY SO.
    #
    # LPT packs against `weights` and this line then grades the packing with the
    # same `weights` — so it is not an independent check, and where a weight is
    # the DEFAULT_WEIGHT placeholder it is not a measurement at all. Both halves
    # cancel to a confident zero. Measured 2026-09-01: 599 of 1,080 files had a
    # recorded duration, and this line printed "estimated shard skew: 0.0%" for
    # a partition whose legs ran 328s / 506s / 411s / 324s on the runner — 56%
    # real skew, reported as perfect. Nothing was broken; the estimate simply had
    # nothing to see, and an estimate with nothing to see reads exactly like a
    # healthy one. That is the same shape as a green from a gate that never ran.
    #
    # So the coverage is printed next to the skew, always, and drifts loudly.
    # A WARNING and not an error, deliberately: staleness costs wall clock, never
    # correctness — the partition is total and disjoint whatever the weights say —
    # and a step that reds a legitimate push (adding a batch of test files) is a
    # step that acquires a `|| true`. The threshold sits far below normal churn:
    # at 1,080 files it takes ~108 unmeasured newcomers to trip, which is
    # staleness rather than a busy week.
    measured, unmeasured = hint_coverage(ours, weights)
    coverage = 100.0 * measured / len(ours) if ours else 0.0
    if loads and min(loads) > 0:
        skew = (max(loads) - min(loads)) / min(loads) * 100
        print(
            f"estimated shard skew: {skew:.1f}% (slowest vs fastest) — computed from "
            f"{measured}/{len(ours)} measured files ({coverage:.0f}% of the suite); "
            f"the rest are packed at the {DEFAULT_WEIGHT}s DEFAULT_WEIGHT placeholder"
        )
    if hints_need_refresh(unmeasured):
        # Deliberately still a WARNING at this level, and the pytest guard uses
        # STALE_HINTS_MAX_UNMEASURED rather than this one. The gap between the two
        # is the runway: CI says "this needs refreshing soon" for days before
        # anything can red. Crossing the warning is a chore; crossing the hard
        # limit is neglect.
        headroom = STALE_HINTS_MAX_UNMEASURED - unmeasured
        print(
            f"::warning::shard balance hints are going STALE — {unmeasured} of {len(ours)} files "
            f"have no measured duration ({coverage:.0f}% covered), so the skew above is largely "
            f"fiction and those files are packed at the {DEFAULT_WEIGHT}s placeholder. "
            f"{headroom} more unmeasured files and the guard fails "
            f"(limit {STALE_HINTS_MAX_UNMEASURED}). Refresh from a CI run's own logs: download "
            f"the four backend-tests job logs and run "
            f"`python scripts/ci_shard.py --record <concatenated.log>` — the timestamp prefix "
            f"Actions puts on every line is stripped for you."
        )

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
    for raw in text.splitlines():
        m = pat.match(_strip_log_prefix(raw))
        if m:
            per_file[m.group(2)] = per_file.get(m.group(2), 0.0) + float(m.group(1))
            printed_count[m.group(2)] = printed_count.get(m.group(2), 0) + 1
    if not per_file:
        print(
            "::error::no `Ns call tests/...` duration lines found — was --durations=0 used? "
            "(Actions timestamp/job prefixes are stripped automatically, so this really does "
            "mean the log has no per-test durations in it.)"
        )
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
