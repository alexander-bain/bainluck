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

Exit codes (#8835 — the scheduled advisory reads these, so they are a contract)
-------------------------------------------------------------------------------
``0`` no bomb and every point ran · ``1`` at least one BOMB (a real finding
about the targets, named by test id and fake instant) · ``2`` HARNESS FAULT and
no bomb — some point did not produce a readable result, so "no bomb" was not
earned. Bombs outrank faults in the exit code because a bomb found at a point
that DID run is true whatever happened at another point; the faults are still
listed separately in the output and the ``--json``, never folded into the count.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from clock_sweep import _PATCH, _PYTEST_EXIT, _SELF_CHECK_TAIL  # noqa: E402

# pytest's terse output. `-q --tb=no -rfE` prints one `FAILED <nodeid>` per
# failure and one `ERROR <nodeid>` per setup error; both are outcomes that
# differ between clocks and both must be captured, because a fixture that raises
# never reaches a test and would otherwise read as absent.
#
# #8835 — the flag was `-rf`, which REPLACES pytest's default `fE` and drops the
# ERROR lines this regex was written to catch: a fixture that expired inside its
# own setup exited 1 with nothing to name. `_run` now also refuses to read an
# exit 1 that names no test (see there).
_OUTCOME = re.compile(r"^(FAILED|ERROR)\s+(\S+)", re.MULTILINE)

#: Per-subprocess wall-clock ceilings. A hung point is a HARNESS FAULT, never a
#: silent stall: the scheduled job's own timeout would kill the whole run and
#: turn one slow point into no evidence at all.
DEFAULT_POINT_TIMEOUT_S = 600
SELF_CHECK_TIMEOUT_S = 60

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
    try:
        proc = subprocess.run(
            [sys.executable, "-c", src], capture_output=True, text=True,
            timeout=SELF_CHECK_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return [f"self-check did not finish within {SELF_CHECK_TIMEOUT_S}s"]
    if proc.returncode == 0:
        return []
    problems = [ln for ln in proc.stdout.splitlines() if ln.startswith("SELF-CHECK:")]
    return problems or [f"self-check exited {proc.returncode}: {proc.stderr.strip()[:300]}"]


def _run(targets: list[str], instant: datetime | None, extra: list[str],
         whole_clock: bool = False,
         timeout_s: float = DEFAULT_POINT_TIMEOUT_S) -> dict:
    """Run the candidate set once. `instant=None` means the real clock."""
    args = ["-q", "--tb=no", "-rfE", "-p", "no:cacheprovider", *extra, *targets]
    body = "" if instant is None else _patch_for(instant, whole_clock)
    src = body + _PYTEST_TAIL.format(args=args)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", src], capture_output=True, text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {
            "exit": None,
            "label": "FAULT",
            "meaning": f"TIMED OUT after {timeout_s:g}s — the point never finished",
            "readable": False,
            "failed": [],
            "summary": "",
            "elapsed_s": round(time.monotonic() - started, 1),
        }
    label, meaning = _PYTEST_EXIT.get(
        proc.returncode, ("FAULT", f"unexpected exit {proc.returncode}")
    )
    out = proc.stdout + proc.stderr
    failed = sorted({m.group(2) for m in _OUTCOME.finditer(out)})
    # 🔴 Only exit 0 and 1 are readable outcomes (gotcha #54 / CERT-625).
    # Anything else means the run did not complete, and a partial failure list
    # from an interrupted run would read as "these and no others".
    readable = proc.returncode in (0, 1)
    if proc.returncode == 1 and not failed:
        # A red run that names no test cannot be compared point to point: read
        # as-is it is "red, and nothing new failed", i.e. a silent pass (#8835).
        readable = False
        label, meaning = "FAULT", "pytest exited 1 but named no FAILED/ERROR test"
    return {
        "exit": proc.returncode,
        "label": label,
        "meaning": meaning,
        "readable": readable,
        "failed": failed,
        "summary": out.strip().splitlines()[-1] if out.strip() else "",
        "elapsed_s": round(time.monotonic() - started, 1),
    }


def render_summary(result: dict) -> str:
    """Markdown for a CI job summary: bombs, harness faults and the rest, apart.

    Built from the ``--json`` payload only, so what a reader sees in the job
    page is exactly what the retained artifact says.
    """
    lines = [f"## Expiring-fixture check — {result['verdict']}", ""]
    lines.append(
        f"Real clock `{result['real_now']}` · {result['targets']} target file(s) · "
        f"offsets (days) `{result['offsets']}` · clock "
        f"{'WHOLE' if result['whole_clock'] else 'datetime only (candidates, not a verdict)'} · "
        f"elapsed {result['elapsed_s']}s"
    )
    lines.append("")
    bombs = result["bombs"]
    lines.append(f"### Bombs — tests that pass now and fail at a later fake date ({len(bombs)})")
    if bombs:
        lines.append("| test | first red at fake instant (UTC) |")
        lines.append("|---|---|")
        for nodeid in sorted(bombs):
            lines.append(f"| `{nodeid}` | `{bombs[nodeid][0]}` |")
    else:
        lines.append("none")
    lines.append("")
    faults = result["faults"]
    lines.append(f"### Harness faults — points that produced no readable result ({len(faults)})")
    lines.append(
        "These are statements about the RUN, not about any test. A point listed "
        "here was not checked, so no bomb there is not evidence of none."
    )
    if faults:
        lines.extend(f"- {f}" for f in faults)
    else:
        lines.append("none")
    for key, title in (
        ("undecidable", "Undecidable by this method (subprocess/mtime) — read by hand"),
        ("frozen_clock_artifacts", "Frozen-clock artifacts — red at +0d too, not bombs"),
        ("baseline_failed", "Already red at the real clock — not this class"),
    ):
        items = result.get(key) or []
        if items:
            lines += ["", f"### {title} ({len(items)})"]
            lines.extend(f"- `{i}`" for i in items)
    lines += ["", "### Points", "| fake instant (UTC) | result | elapsed |", "|---|---|---|"]
    for pt in result["points"]:
        lines.append(f"| `{pt['instant']}` | {pt['label']} {pt['note']} | {pt['elapsed_s']}s |")
    return "\n".join(lines) + "\n"


def _offsets(raw: str) -> str:
    """argparse type: reject a malformed ``--offsets`` as a USAGE error (exit 2).

    Left to ``float()`` inside ``main`` it raised, and an uncaught exception
    exits 1 — the code that means BOMB (#8835).
    """
    try:
        values = [float(x) for x in raw.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a comma-separated list of days: {raw!r}")
    if not values or any(v <= 0 for v in values):
        raise argparse.ArgumentTypeError(f"offsets must be positive days: {raw!r}")
    return raw


def _emit(result: dict, json_path: str | None, summary_path: str | None) -> int:
    """Write the retained record and the job summary; return the exit code.

    Every exit path goes through here — including a baseline that never ran —
    so a scheduled run always leaves a record that names what happened.
    """
    if result["bombs"]:
        result["verdict"], code = "BOMB", 1
    elif result["faults"]:
        result["verdict"], code = "HARNESS FAULT", 2
    else:
        result["verdict"], code = "CLEAN", 0
    result["exit_code"] = code
    result["elapsed_s"] = round(time.monotonic() - result.pop("_started"), 1)
    if json_path:
        pathlib.Path(json_path).write_text(json.dumps(result, indent=2))
    if summary_path:
        with open(summary_path, "a") as fh:
            fh.write(render_summary(result))
    return code


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("targets", nargs="*")
    p.add_argument("--from-file", help="file with one pytest target per line")
    p.add_argument(
        "--offsets",
        type=_offsets,
        default="1,32,190,400",
        help="days into the future to test (default straddles the 30d bound, "
        "a half year, and a year boundary)",
    )
    p.add_argument("--json", help="write the full result here")
    p.add_argument(
        "--summary",
        help="append a markdown summary here (e.g. $GITHUB_STEP_SUMMARY)",
    )
    p.add_argument(
        "--timeout-per-point",
        type=float,
        default=DEFAULT_POINT_TIMEOUT_S,
        help="seconds one pytest run may take before its point is a HARNESS FAULT",
    )
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

    result: dict = {
        "_started": time.monotonic(),
        "real_now": now.isoformat(),
        "targets": len(targets),
        "target_list": targets,
        "offsets": a.offsets,
        "whole_clock": a.whole_clock,
        "timeout_per_point_s": a.timeout_per_point,
        "baseline": None,
        "points": [],
        "bombs": {},
        "faults": [],
        "undecidable": [],
        "frozen_clock_artifacts": [],
        "baseline_failed": [],
    }

    print(f"{len(targets)} targets · baseline at the real clock, then {len(points)} future points\n  clock: {'WHOLE (datetime + time.time)' if a.whole_clock else 'datetime only — CANDIDATES, not a verdict'}")

    # --- Baseline. A target already red now cannot be shown to be a bomb. -----
    base = _run(targets, None, a.extra, a.whole_clock, a.timeout_per_point)
    result["baseline"] = {k: base[k] for k in ("exit", "label", "summary", "elapsed_s")}
    print(f"  baseline           exit {base['exit']} {base['label']}: {base['summary']}")
    if not base["readable"]:
        print("\n🔴 HARNESS FAULT: the baseline run did not complete. No conclusion drawn.")
        print(f"   {base['meaning']}")
        result["faults"].append(f"baseline (real clock): exit {base['exit']} — {base['meaning']}")
        return _emit(result, a.json, a.summary)
    already_red = set(base["failed"])
    result["baseline_failed"] = sorted(already_red)
    if already_red:
        print(f"  {len(already_red)} test(s) already failing at the real clock — excluded, listed below")

    bombs: dict[str, list[str]] = result["bombs"]
    frozen_clock_artifacts: set[str] = set()
    faults: list[str] = result["faults"]
    # The control is points[0] BY POSITION, not by value. `--offsets 0,32` makes
    # a later point compare equal to `now`, and a value test would treat that
    # requested point as a second control and silently drop it from the run.
    for index, point in enumerate(points):
        stamp = point.isoformat()
        label = "+0d (control)" if index == 0 else f"+{(point - now).total_seconds() / 86400:g}d"
        problems = _self_check(point, a.whole_clock)
        if problems:
            faults.append(f"{stamp} ({label}): " + "; ".join(problems))
            result["points"].append(
                {"instant": stamp, "label": "FAULT", "note": "self-check failed", "elapsed_s": 0}
            )
            print(f"  {stamp}  🔴 HARNESS FAULT — {problems[0]}")
            continue
        res = _run(targets, point, a.extra, a.whole_clock, a.timeout_per_point)
        record = {"instant": stamp, "label": res["label"], "note": "", "elapsed_s": res["elapsed_s"]}
        result["points"].append(record)
        if not res["readable"]:
            faults.append(f"{stamp} ({label}): exit {res['exit']} — {res['meaning']}")
            record["note"] = res["meaning"]
            print(f"  {stamp}  🔴 HARNESS FAULT exit {res['exit']} — {res['meaning']}")
            continue
        new = sorted(set(res["failed"]) - already_red)
        if index == 0:
            # The control point. Anything red here is red because the clock is
            # STOPPED, not because it moved — see the comment on `points`.
            frozen_clock_artifacts = set(new)
            record["note"] = f"control: {len(new)} frozen-clock artifact(s)"
            print(
                f"  {label:>17}  exit {res['exit']} {res['label']}: "
                f"{len(new)} frozen-clock artifact(s)"
            )
            continue
        new = [n for n in new if n not in frozen_clock_artifacts]
        record["note"] = f"{len(new)} new failure(s)"
        print(
            f"  {label:>8} {stamp}  exit {res['exit']} "
            f"{res['label']}: {len(new)} NEW failure(s)"
        )
        for nodeid in new:
            bombs.setdefault(nodeid, []).append(stamp)

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
    result["undecidable"] = sorted(n for ids in undecidable.values() for n in ids)
    result["frozen_clock_artifacts"] = sorted(frozen_clock_artifacts)

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

    return _emit(result, a.json, a.summary)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 — a crash must never read as exit 1 (BOMB)
        import traceback

        traceback.print_exc()
        print("\n🔴 HARNESS FAULT: timebomb_confirm itself crashed. No conclusion drawn.")
        raise SystemExit(2)
