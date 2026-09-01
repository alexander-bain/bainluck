#!/usr/bin/env python3
"""Turn timebomb CANDIDATES into VERDICTS by moving the clock.

`scripts/timebomb_census.py` reads source and over-reports on purpose: it cannot
see a bound that lives in the product code a test calls. This is the oracle that
settles it, and it settles it the only way a claim about time can be settled —
by running the tests at a different time and seeing whether they change their
minds.

    a test that passes NOW and fails at a FUTURE instant, with no code change,
    is a scheduled outage with a stack trace.

Method
------
One pytest process per clock point over the whole candidate set, so the set,
the ordering and the environment are identical and the only variable is the
faked instant. Per-test outcomes are compared point to point:

    PASS now, FAIL later   -> BOMB          (the class this exists to find)
    FAIL now               -> ALREADY RED   (not ours; reported, never hidden)
    PASS at every point    -> CLOCK-INVARIANT

The clock patch is imported from ``clock_sweep`` rather than copied. That module
is on its fifth repair and carries a metaclass that keeps ``isinstance`` honest
(#2396) — a second, drifting copy of it here would be the same bug with a new
name.

🔴 THE SELF-CHECK IS NOT OPTIONAL. ``clock_sweep`` refuses to draw a conclusion
from a harness it has not proved sound at that instant, and so does this: if the
clock did not move, every point is really the real clock and "invariant at 12
points" is a vacuous green.

Usage
-----
    python3 scripts/timebomb_confirm.py --from-file /tmp/candidates.txt
    python3 scripts/timebomb_confirm.py tests/test_a.py tests/test_b.py
    python3 scripts/timebomb_confirm.py --from-file c.txt --offsets 1,7,31,180,400
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from clock_sweep import _PATCH, _PYTEST_EXIT, _SELF_CHECK_TAIL  # noqa: E402

# pytest's terse output. `-q --tb=no -rf` prints one `FAILED <nodeid>` per
# failure and one `ERROR <nodeid>` per collection/setup error; both are outcomes
# that differ between clocks and both must be captured, because a fixture that
# raises at import time never reaches a test and would otherwise read as absent.
_OUTCOME = re.compile(r"^(FAILED|ERROR)\s+(\S+)", re.MULTILINE)

_PYTEST_TAIL = r"""
import sys
import pytest
sys.exit(pytest.main({args!r}))
"""

# 🔴 WHY THIS EXISTS: `clock_sweep`'s patch moves `datetime` and leaves
# `time.time()` reading the REAL clock. That is fine for its own job — finding a
# target that branches on the hour — but it is NOT a faithful simulation of "the
# calendar advanced", and used as a verdict oracle it MANUFACTURES FINDINGS.
#
# Measured, this exact case: `tests/test_admin_state_rails.py` stamps a cache
# envelope with `time.time() * 1000` and the reader ages it against
# `datetime.now()`. Move only `datetime` and the envelope instantly looks 400
# days old, the rail reports `direct` instead of `fresh`, and the test goes red —
# at a real future date it would pass, because both clocks would have moved.
# A split clock is a state no calendar ever reaches.
#
# So the VERDICT runs on a clock where every entry point agrees. The broad sweep
# may over-report; this is what decides. `time.monotonic` is deliberately NOT
# patched: it is a duration source, nothing dates anything with it, and asyncio's
# timeouts are built on it.
_PATCH_TIME = r'''
import time as _time

_FAKE_TS = _FAKE.timestamp()
_time.time = lambda: _FAKE_TS
_time.time_ns = lambda: int(_FAKE_TS * 1_000_000_000)
'''

# The self-check for the consistent clock: both entry points moved, and they
# AGREE. Two clocks that both moved to different instants is the same split-clock
# fault wearing a disguise.
_TIME_SELF_CHECK = r'''
import time as _t
from datetime import datetime as _d, timezone as _tz

_want = _d.fromisoformat({fake!r})
_seen = _d.fromtimestamp(_t.time(), tz=_tz.utc)
if abs((_seen - _want.astimezone(_tz.utc)).total_seconds()) > 1:
    print("SELF-CHECK: time.time() did not move: %s but asked for %s" % (_seen, _want))
    sys.exit(1)
if abs(_t.time_ns() / 1e9 - _t.time()) > 1:
    print("SELF-CHECK: time.time_ns() disagrees with time.time()")
    sys.exit(1)
'''


def _patch_for(instant: datetime, whole_clock: bool) -> str:
    src = _PATCH.format(fake=instant.isoformat())
    if whole_clock:
        src += _PATCH_TIME
    return src


def _self_check(instant: datetime, whole_clock: bool) -> list[str]:
    """Prove the clock moved and datetimes are still datetimes, at THIS instant."""
    src = _patch_for(instant, whole_clock)
    if whole_clock:
        # Ordered before the borrowed check so a split clock is named as a split
        # clock rather than surfacing later as a mystery target failure.
        src += "import sys\n" + _TIME_SELF_CHECK.format(fake=instant.isoformat())
    src += _SELF_CHECK_TAIL.format(fake=instant.isoformat())
    proc = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True)
    if proc.returncode == 0:
        return []
    problems = [ln for ln in proc.stdout.splitlines() if ln.startswith("SELF-CHECK:")]
    return problems or [f"self-check exited {proc.returncode}: {proc.stderr.strip()[:300]}"]


def _run(targets: list[str], instant: datetime | None, extra: list[str],
         whole_clock: bool = False) -> dict:
    """Run the candidate set once. `instant=None` means the real clock."""
    args = ["-q", "--tb=no", "-rf", "-p", "no:cacheprovider", *extra, *targets]
    body = "" if instant is None else _patch_for(instant, whole_clock)
    src = body + _PYTEST_TAIL.format(args=args)
    proc = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True)
    label, meaning = _PYTEST_EXIT.get(
        proc.returncode, ("FAULT", f"unexpected exit {proc.returncode}")
    )
    out = proc.stdout + proc.stderr
    return {
        "exit": proc.returncode,
        "label": label,
        "meaning": meaning,
        # 🔴 Only exit 0 and 1 are readable outcomes (gotcha #54 / CERT-625).
        # Anything else means the run did not complete, and a partial failure
        # list from an interrupted run would read as "these and no others".
        "readable": proc.returncode in (0, 1),
        "failed": sorted({m.group(2) for m in _OUTCOME.finditer(out)}),
        "summary": out.strip().splitlines()[-1] if out.strip() else "",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("targets", nargs="*")
    p.add_argument("--from-file", help="file with one pytest target per line")
    p.add_argument(
        "--offsets",
        default="1,32,190,400",
        help="days into the future to test (default straddles the 30d bound, "
        "a half year, and a year boundary)",
    )
    p.add_argument("--json", help="write the full result here")
    p.add_argument("--pytest-arg", action="append", default=[], dest="extra")
    p.add_argument(
        "--whole-clock",
        action="store_true",
        help="also move `time.time()`, so every clock entry point agrees. REQUIRED "
        "for a verdict: moving `datetime` alone is a state no calendar reaches and "
        "it manufactures failures in tests that stamp with `time.time()`.",
    )
    a = p.parse_args()

    targets = list(a.targets)
    if a.from_file:
        targets += [
            ln.strip()
            for ln in pathlib.Path(a.from_file).read_text().splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
    if not targets:
        print("no targets", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc).replace(microsecond=0)
    # 🔴 OFFSET ZERO IS A CONTROL, NOT A DATA POINT, and it is not optional.
    #
    # Both patches FREEZE the clock rather than advancing it. A test that needs
    # time to PASS — a rate-limit window resetting, a TTL expiring, an elapsed-ms
    # assertion — fails under a frozen clock at any instant, including this one.
    # Measured: `tests/test_rate_limit.py::test_fixed_window_resets_after_boundary`
    # reads as a bomb at +32d and +400d, and it is nothing of the kind.
    #
    # A date bomb is green before its date and red after. A freeze artifact is
    # red at +0 too, where the faked clock IS the real clock and the only thing
    # that changed is that time stopped. So every failure is checked against +0
    # and anything red there is reported as an ARTIFACT rather than counted.
    points = [now] + [now + timedelta(days=float(d)) for d in a.offsets.split(",")]

    print(f"{len(targets)} targets · baseline at the real clock, then {len(points)} future points\n  clock: {'WHOLE (datetime + time.time)' if a.whole_clock else 'datetime only — CANDIDATES, not a verdict'}")

    # --- Baseline. A target already red now cannot be shown to be a bomb. -----
    base = _run(targets, None, a.extra, a.whole_clock)
    print(f"  baseline           exit {base['exit']} {base['label']}: {base['summary']}")
    if not base["readable"]:
        print("\n🔴 HARNESS FAULT: the baseline run did not complete. No conclusion drawn.")
        print(f"   {base['meaning']}")
        return 2
    already_red = set(base["failed"])
    if already_red:
        print(f"  {len(already_red)} test(s) already failing at the real clock — excluded, listed below")

    bombs: dict[str, list[str]] = {}
    frozen_clock_artifacts: set[str] = set()
    faults: list[str] = []
    # The control is points[0] BY POSITION, not by value. `--offsets 0,32` makes
    # a later point compare equal to `now`, and a value test would treat that
    # requested point as a second control and silently drop it from the run.
    for index, point in enumerate(points):
        problems = _self_check(point, a.whole_clock)
        if problems:
            faults.append(f"{point.date()}: " + "; ".join(problems))
            print(f"  {point.date()}  🔴 HARNESS FAULT — {problems[0]}")
            continue
        res = _run(targets, point, a.extra, a.whole_clock)
        if not res["readable"]:
            faults.append(f"{point.date()}: exit {res['exit']} — {res['meaning']}")
            print(f"  {point.date()}  🔴 HARNESS FAULT exit {res['exit']} — {res['meaning']}")
            continue
        new = sorted(set(res["failed"]) - already_red)
        if index == 0:
            # The control point. Anything red here is red because the clock is
            # STOPPED, not because it moved — see the comment on `points`.
            frozen_clock_artifacts = set(new)
            print(
                f"  {'+0d (control)':>17}  exit {res['exit']} {res['label']}: "
                f"{len(new)} frozen-clock artifact(s)"
            )
            continue
        new = [n for n in new if n not in frozen_clock_artifacts]
        print(
            f"  +{(point - now).days:>4}d {point.date()}  exit {res['exit']} "
            f"{res['label']}: {len(new)} NEW failure(s)"
        )
        for nodeid in new:
            bombs.setdefault(nodeid, []).append(point.date().isoformat())

    print()
    print("=" * 78)
    if faults:
        # Loud, and never rolled into the count. A point that did not run is not
        # a point that found nothing (gotcha #53).
        print(f"🔴 {len(faults)} clock point(s) DID NOT RUN — the verdict below covers the rest:")
        for f in faults:
            print(f"    {f}")
    # 🔴 THE THIRD ARTIFACT CLASS, AND THE ONLY ONE NO CONTROL CAN SETTLE.
    #
    # An in-process clock patch does not cross a process boundary, and it never
    # reaches the KERNEL. A test that shells out, or that writes an mtime with
    # `os.utime` and lets the subject read it back, is comparing a faked clock
    # against a real one — a state no calendar produces.
    #
    # Measured: `tests/test_claim_lane_lock.py` spawns `scripts/claim_lane_lock.py`
    # and backdates lock mtimes. The child sees the real clock, the parent stamps
    # with the fake one, and four tests read as bombs at +32d. They are not: every
    # interval in that file is relative (`time.time() - 7200`) and it holds no
    # absolute date at all.
    #
    # This CANNOT be resolved by running it differently, so it is not counted and
    # not dismissed either — it is handed back for a human to read. Silently
    # counting it inflates the number; silently dropping it hides a real bomb if
    # one ever lands in such a file.
    undecidable: dict[str, list[str]] = {}
    for nodeid in list(bombs):
        path = pathlib.Path(nodeid.split("::")[0])
        try:
            text = path.read_text()
        except OSError:
            continue
        if "subprocess" in text or "os.utime" in text:
            undecidable.setdefault(str(path), []).append(nodeid)
            del bombs[nodeid]

    by_file: dict[str, list[str]] = {}
    for nodeid in bombs:
        by_file.setdefault(nodeid.split("::")[0], []).append(nodeid)
    print(f"BOMBS: {len(bombs)} test(s) in {len(by_file)} file(s) pass now and fail later")
    for path in sorted(by_file):
        print(f"  {path}")
        for nodeid in sorted(by_file[path]):
            print(f"      {nodeid.split('::', 1)[-1]}   first red: {bombs[nodeid][0]}")
    if undecidable:
        print(
            f"\n🔴 UNDECIDABLE BY THIS METHOD ({sum(len(v) for v in undecidable.values())} "
            "test(s)) — the target spawns a subprocess or\nstamps an mtime, so the fake clock "
            "does not reach every clock it consults. READ THESE;\nno amount of re-running "
            "settles them:"
        )
        for path, ids in sorted(undecidable.items()):
            print(f"  {path}  ({len(ids)} test(s))")
    if frozen_clock_artifacts:
        # Excluded from the count, never from the output. A reader who is not
        # told these exist will find them again the hard way, which is how this
        # control came to be written.
        print(
            f"\nFROZEN-CLOCK ARTIFACTS ({len(frozen_clock_artifacts)}) — red at +0d, so they "
            "need time to PASS,\nnot a different date. Not bombs; excluded from the count:"
        )
        for nodeid in sorted(frozen_clock_artifacts):
            print(f"  {nodeid}")
    if already_red:
        print(f"\nALREADY RED at the real clock ({len(already_red)}) — not this class, not hidden:")
        for nodeid in sorted(already_red):
            print(f"  {nodeid}")

    if a.json:
        pathlib.Path(a.json).write_text(
            json.dumps(
                {
                    "targets": len(targets),
                    "baseline_failed": sorted(already_red),
                    "bombs": bombs,
                    "faults": faults,
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
