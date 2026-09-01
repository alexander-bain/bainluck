#!/usr/bin/env python3
"""Name the DAY a confirmed timebomb goes off.

`timebomb_confirm.py` answers "is this a bomb". This answers the question that
actually schedules the work: **when**. A test whose fuse burns out in nine days
and one that expires in 2027 are the same class and nowhere near the same
urgency, and without a date the whole list reads as equally not-yet-urgent —
which is how the last one sat green for thirty days.

Bisects the first future day at which the target fails, on the WHOLE clock
(`datetime` and `time.time` both moved — see `timebomb_confirm._PATCH_TIME` for
why a split clock lies). Single-file targets run in seconds, so a bisect over a
two-year horizon costs about ten runs.

🔴 A NEGATIVE RESULT IS NOT "SAFE". `--horizon` bounds the search, and a bomb
with a longer fuse reports `beyond horizon`, never `clean`. Absence of evidence
inside a window you chose is not evidence of absence (gotcha #53).

Usage
-----
    python3 scripts/timebomb_fuse.py tests/test_a.py tests/test_b.py
    python3 scripts/timebomb_fuse.py tests/test_a.py --horizon 1200
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from timebomb_confirm import _PYTEST_TAIL, _patch_for, _self_check  # noqa: E402


def _fails_at(target: str, instant: datetime) -> bool | None:
    """True = red, False = green, None = the run did not complete (no conclusion)."""
    args = ["-q", "--tb=no", "-p", "no:cacheprovider", target]
    src = _patch_for(instant, True) + _PYTEST_TAIL.format(args=args)
    proc = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True)
    if proc.returncode == 1:
        return True
    if proc.returncode == 0:
        return False
    return None  # gotcha #54: every other code is a story about the harness


def fuse(target: str, horizon: int) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)

    problems = _self_check(now + timedelta(days=horizon), True)
    if problems:
        return {"target": target, "verdict": "HARNESS FAULT", "detail": problems[0]}

    if _fails_at(target, now) is not False:
        return {"target": target, "verdict": "not green today — nothing to date"}
    if _fails_at(target, now + timedelta(days=horizon)) is not True:
        return {
            "target": target,
            "verdict": f"no failure within {horizon}d — NOT proven safe, only "
            "unexploded inside the horizon searched",
        }

    lo, hi = 0, horizon  # green at lo, red at hi
    while hi - lo > 1:
        mid = (lo + hi) // 2
        red = _fails_at(target, now + timedelta(days=mid))
        if red is None:
            return {"target": target, "verdict": "HARNESS FAULT", "detail": f"at +{mid}d"}
        if red:
            hi = mid
        else:
            lo = mid
    return {
        "target": target,
        "verdict": "BOMB",
        "days": hi,
        "date": (now + timedelta(days=hi)).date().isoformat(),
        "last_green": (now + timedelta(days=lo)).date().isoformat(),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("targets", nargs="+")
    p.add_argument("--horizon", type=int, default=800)
    a = p.parse_args()

    rows = [fuse(t, a.horizon) for t in a.targets]
    rows.sort(key=lambda r: r.get("days", 10**9))
    width = max(len(r["target"]) for r in rows)
    for r in rows:
        if r["verdict"] == "BOMB":
            print(f"{r['target']:<{width}}  goes red {r['date']}  (+{r['days']}d)")
        else:
            print(f"{r['target']:<{width}}  {r['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
