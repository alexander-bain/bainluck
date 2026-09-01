#!/usr/bin/env python3
"""Run a pytest target under a sweep of FAKE wall clocks.

Why this exists
---------------
``tests/test_feed_phantom_midpoint_suppression.py`` went red for half of every
day, twice, in opposite windows, and each fix was verified by running the suite
— at one time of day. A suite that branches on the clock is green or red
depending on when you look at it, so "it passes" is not evidence unless you say
*when*, and the only way to say "at every when" is to move the clock.

This harness moves it. Each point runs the target in a fresh subprocess whose
``datetime.datetime.now``/``utcnow``/``today`` report the requested instant,
installed before the application is imported. A target that reads no clock is
invariant across every point; one that does will fail at some of them, and the
failing points tell you where its boundary sits.

The harness grades itself first (#2396)
---------------------------------------
Every run begins with a self-check at every point, and the sweep does not run
at all unless it passes. The self-check proves BOTH that the clock actually
moved AND that faking it did not change what a datetime *is* — because a fault
in the patch produces red that is indistinguishable from a finding about the
target. This tool spent eleven cycles reporting ``5 failed, 12 passed`` at all
12 points, identically before and after a real repair, on a fixture that passes
17/17 at the real clock; the cause was the patch, not the target. A harness
that cannot fail loudly about itself is not an instrument.

Exit codes: ``0`` invariant · ``1`` the target reads the clock · ``2`` HARNESS
FAULT, no conclusion drawn about the target.

Usage
-----
    python3 scripts/clock_sweep.py tests/test_feed_phantom_midpoint_suppression.py
    python3 scripts/clock_sweep.py tests/foo.py --at 2026-08-11T00:00 --offsets -8,0,8
    python3 scripts/clock_sweep.py tests/foo.py --self-check-only

Default sweep: -8h / -2h / 0 / +2h / +8h around BOTH 00:00 and 12:00 UTC (the
two boundaries a day-anchored fixture can straddle), plus two far-future points
that catch a fixture whose own content expires with the calendar.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone

# Installed inside the child, before pytest or the app is imported.
#
# #2396 — WHY THE METACLASS. Swapping ``datetime.datetime`` for a plain
# SUBCLASS silently breaks every ``isinstance(value, datetime)`` in the tree:
# a genuine datetime — one from Postgres, from ``fromisoformat``, from
# arithmetic, or even from this harness's own ``now()`` — is not an instance of
# the subclass, so type checks start answering "no" and their callers report
# perfectly good values as missing or unparseable. That is a fault in the
# HARNESS, it does not depend on the faked instant, and it is indistinguishable
# from a finding about the target: the sweep reported 5 failed / 12 passed
# identically at all 12 points on a fixture that passes 17/17 at the real
# clock, and reported it identically before and after a real repair.
# ``__instancecheck__`` keeps type identity answering about the real class so
# only the CLOCK moves. ``_self_check_problems`` below proves it still holds.
_PATCH = r'''
import datetime as _dt, sys

_FAKE = _dt.datetime.fromisoformat({fake!r})
_real = _dt.datetime


class _FakeMeta(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _real)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, _real)


class _FakeDateTime(_real, metaclass=_FakeMeta):
    @classmethod
    def now(cls, tz=None):
        return _FAKE.astimezone(tz) if tz is not None else _FAKE.replace(tzinfo=None)

    @classmethod
    def utcnow(cls):
        return _FAKE.replace(tzinfo=None)

    @classmethod
    def today(cls):
        return _FAKE.replace(tzinfo=None)


_dt.datetime = _FakeDateTime
'''

# Self-contained on purpose: CERT-625's baseline runs this WITHOUT ``_PATCH`` in
# front of it, so it cannot borrow that block's ``import sys``.
_PYTEST_TAIL = r'''
import sys
import pytest
sys.exit(pytest.main({args!r}))
'''

# The self-check runs under the SAME patch the sweep uses, in a bare
# interpreter (no pytest, no app import), and asserts two things that must both
# hold or the sweep cannot be read:
#
#   1. the clock actually MOVED — otherwise every assertion below passes
#      vacuously against the real clock and a no-op harness self-certifies;
#   2. the patch did not change what a datetime IS — the #2396 fault.
#
# A harness that cannot see its own breakage reports absence of evidence as
# evidence of absence (gotcha #53), which is exactly how this tool spent
# eleven cycles reporting a false FAIL as a finding.
_SELF_CHECK_TAIL = r'''
from datetime import datetime, timedelta, timezone

expected = datetime.fromisoformat({fake!r})
problems = []

seen = datetime.now(timezone.utc)
if abs((seen - expected).total_seconds()) > 1:
    problems.append("clock did not move: now()=%s but asked for %s" % (seen, expected))
if datetime.utcnow().replace(tzinfo=timezone.utc) != expected.astimezone(timezone.utc):
    problems.append("utcnow() disagrees with now()")

for label, value in (
    ("now()", seen),
    ("utcnow()", datetime.utcnow()),
    ("today()", datetime.today()),
    ("fromisoformat()", expected),
    ("now() - timedelta", seen - timedelta(hours=6)),
):
    if not isinstance(value, datetime):
        problems.append("isinstance(%s, datetime) is False — the patch broke type identity" % label)

for p in problems:
    print("SELF-CHECK: " + p)
sys.exit(1 if problems else 0)
'''


# CERT-625 — pytest's exit code is not a boolean, and reading it as one is how
# this tool produced its SECOND false conclusion. Only `1` means "tests ran and
# some failed"; every other nonzero value is a story about the harness (gotcha
# #54). Before this, a nonexistent target (exit 4) and a throwaway `assert False`
# with no clock import anywhere both printed "the target reads the clock".
_PYTEST_EXIT = {
    0: ("PASS", "all tests passed"),
    1: ("FAIL", "tests ran and some failed"),
    2: ("FAULT", "pytest was INTERRUPTED — the run did not complete"),
    3: ("FAULT", "pytest INTERNAL ERROR"),
    4: ("FAULT", "pytest USAGE ERROR — the target is probably not a valid file/nodeid"),
    5: ("FAULT", "pytest collected NO TESTS — the target matches nothing"),
}


def _classify(returncode: int) -> tuple[str, str]:
    """Map a pytest exit code to (verdict, why).

    ``PASS``/``FAIL`` are results about the target. ``FAULT`` is a statement
    about the run itself, and a FAULT anywhere must stop the sweep from drawing
    any conclusion at all.
    """
    return _PYTEST_EXIT.get(returncode, ("FAULT", f"unrecognised pytest exit code {returncode}"))


def _run_target(target: str, patch: str = "") -> tuple[int, str]:
    """Run ``target`` under pytest, optionally clock-patched. -> (code, summary)."""
    code = patch + _PYTEST_TAIL.format(
        args=["-q", "--no-header", "-p", "no:cacheprovider", target]
    )
    proc = _run(code)
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    summary = tail[-1] if tail else "(no output)"
    if not tail and proc.stderr.strip():
        summary = proc.stderr.strip().splitlines()[-1]
    return proc.returncode, summary


def _points(at: datetime, offsets: list[float]) -> list[datetime]:
    return [at + timedelta(hours=o) for o in offsets]


def _run(source: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True
    )


def _self_check_problems(instant: datetime) -> list[str]:
    """Return what the harness itself got wrong at ``instant`` ([] when sound).

    A non-empty list means the sweep's own clock patch is faulty, so nothing it
    reports about a target can be believed — the failures would be the tool's,
    not the target's.
    """
    iso = instant.isoformat()
    proc = _run(_PATCH.format(fake=iso) + _SELF_CHECK_TAIL.format(fake=iso))
    if proc.returncode == 0:
        return []
    problems = [
        ln.split("SELF-CHECK: ", 1)[1]
        for ln in proc.stdout.splitlines()
        if ln.startswith("SELF-CHECK: ")
    ]
    # A crash before any assertion could print is itself a harness fault, and
    # must not read as "no problems found".
    return problems or [
        f"self-check exited {proc.returncode} without reporting; "
        f"stderr tail: {(proc.stderr.strip().splitlines() or ['(none)'])[-1]}"
    ]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("target", help="pytest target (file, dir, or nodeid)")
    p.add_argument(
        "--at",
        action="append",
        default=None,
        help="ISO instant to sweep around (repeatable). Default: today 00:00 and 12:00 UTC.",
    )
    p.add_argument("--offsets", default="-8,-2,0,2,8", help="comma-separated hours")
    p.add_argument(
        "--no-future",
        action="store_true",
        help="skip the far-future points (which catch calendar-expiring fixtures)",
    )
    p.add_argument(
        "--self-check-only",
        action="store_true",
        help="verify the harness at every point and exit without running the target",
    )
    args = p.parse_args()

    offsets = [float(x) for x in args.offsets.split(",") if x.strip()]
    if args.at:
        anchors = [datetime.fromisoformat(a).replace(tzinfo=timezone.utc) for a in args.at]
    else:
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        anchors = [today, today + timedelta(hours=12)]

    instants = [pt for a in anchors for pt in _points(a, offsets)]
    if not args.no_future:
        instants += [
            instants[0] + timedelta(days=90),
            instants[0] + timedelta(days=400),
        ]

    print(f"target : {args.target}")
    print(f"points : {len(instants)}   (real clock now {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)")
    print("-" * 64)

    # The harness grades itself BEFORE it grades anything else. Without this the
    # tool's FAIL has no baseline: a broken patch and a clock-dependent target
    # produce the same red, and #2396 is eleven cycles of exactly that.
    broken = [(inst, _self_check_problems(inst)) for inst in instants]
    broken = [(inst, probs) for inst, probs in broken if probs]
    if broken:
        print(f"HARNESS FAULT — the clock patch is unsound at {len(broken)}/{len(instants)} points.")
        seen: set[str] = set()
        for inst, problems in broken:
            for problem in problems:
                if problem not in seen:
                    seen.add(problem)
                    print(f"  {inst:%Y-%m-%d %H:%M} UTC   {problem}")
        print("-" * 64)
        print(
            f"NO CONCLUSION about {args.target} — the sweep did not run. "
            "Fix the harness first; a red here would have been the tool's, not the target's."
        )
        return 2
    print(f"self-check: {len(instants)}/{len(instants)} points sound "
          "(clock moves, datetime type identity intact)")

    if args.self_check_only:
        print("-" * 64)
        print("self-check only — target not run.")
        return 0
    print("-" * 64)

    # CERT-625 — THE BASELINE. The self-check proves the CLOCK is sound; it says
    # nothing about the TARGET. A target that is simply broken fails at every
    # faked point too, and "failed everywhere" is indistinguishable from clock
    # dependence without a control. So run it once UNPATCHED, at the real clock,
    # first. Only a target that is green here can have a red attributed to the
    # clock — and this is also where an invalid target or a typo'd nodeid is
    # caught, before twelve subprocesses report it as a finding.
    base_code, base_summary = _run_target(args.target)
    base_verdict, base_why = _classify(base_code)
    print(f"baseline (real clock)   {base_verdict}   {base_summary}")

    if base_verdict == "FAULT":
        print("-" * 64)
        print(f"HARNESS FAULT — {base_why} (pytest exit {base_code}).")
        print(
            f"NO CONCLUSION about {args.target} — the sweep did not run. "
            "This is a statement about the run, not about the target's clock use."
        )
        return 2

    if base_verdict == "FAIL":
        print("-" * 64)
        print(f"{args.target} is ALREADY RED at the real clock.")
        print(
            "NO CONCLUSION about wall-clock dependence — a target that fails "
            "before the clock is touched will fail at every faked point too, and "
            "that red would be the target's existing breakage, not a time bomb. "
            "Fix it green first, then sweep."
        )
        return 2

    print("-" * 64)

    failures = []
    faults = []
    for inst in instants:
        code, summary = _run_target(args.target, _PATCH.format(fake=inst.isoformat()))
        verdict, why = _classify(code)
        if verdict == "FAIL":
            failures.append((inst, summary))
        elif verdict == "FAULT":
            faults.append((inst, code, why))
        print(f"{inst:%Y-%m-%d %H:%M} UTC   {verdict:<5}  {summary}")

    print("-" * 64)

    # A single unreadable point poisons the whole sweep: the target may well read
    # the clock, but this run cannot say so.
    if faults:
        print(f"HARNESS FAULT — {len(faults)}/{len(instants)} points did not produce a test result.")
        for inst, code, why in faults:
            print(f"  {inst:%Y-%m-%d %H:%M} UTC   pytest exit {code} — {why}")
        print(
            f"NO CONCLUSION about {args.target}. The target was green at the real "
            "clock, so these are the run's failures, not the target's."
        )
        return 2

    if failures:
        # Earned three ways: the self-check proved only the clock moved, the
        # baseline proved the target is otherwise green, and every point below
        # returned a real pytest result rather than a harness story.
        print(f"{len(failures)}/{len(instants)} points FAILED — the target reads the clock.")
        return 1
    print(f"all {len(instants)} points green — invariant to wall-clock time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
