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

Usage
-----
    python3 scripts/clock_sweep.py tests/test_feed_phantom_midpoint_suppression.py
    python3 scripts/clock_sweep.py tests/foo.py --at 2026-08-11T00:00 --offsets -8,0,8

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
_BOOTSTRAP = r'''
import datetime as _dt, sys

_FAKE = _dt.datetime.fromisoformat({fake!r})
_real = _dt.datetime


class _FakeDateTime(_real):
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

import pytest
sys.exit(pytest.main({args!r}))
'''


def _points(at: datetime, offsets: list[float]) -> list[datetime]:
    return [at + timedelta(hours=o) for o in offsets]


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

    failures = []
    for inst in instants:
        code = _BOOTSTRAP.format(
            fake=inst.isoformat(), args=["-q", "--no-header", "-p", "no:cacheprovider", args.target]
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
        summary = tail[-1] if tail else "(no output)"
        ok = proc.returncode == 0
        if not ok:
            failures.append((inst, summary))
        print(f"{inst:%Y-%m-%d %H:%M} UTC   {'PASS' if ok else 'FAIL'}   {summary}")

    print("-" * 64)
    if failures:
        print(f"{len(failures)}/{len(instants)} points FAILED — the target reads the clock.")
        return 1
    print(f"all {len(instants)} points green — invariant to wall-clock time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
