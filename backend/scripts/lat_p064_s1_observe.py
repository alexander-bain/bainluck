#!/usr/bin/env python3
"""LAT-P064 S1 — probe-free observation of the typeahead warmer.

LAT-P063 measured two multi-minute holes in the warmer's pass cadence (286.6 s,
169.2 s) and graded rows 1 and 2 of the LAT-P060 exit block as HALT on their
strength. Both holes overlapped that window's own ``/typeahead`` probe runs, so
the reading has a live confound: the observation may have caused the thing it
observed.

S1 removes the confound. Sample ``/api/admin/task-metrics?task=warm_typeahead``
every ``--interval`` seconds for ``--minutes``, issuing **no** ``/typeahead``
traffic of our own, and record every distinct pass the warmer reports.

Registered prediction (LAT-P064 Item 0): >=1 hole > 120 s recurs.
HALT: zero holes in 60 probe-free minutes => the stalls are observation-induced,
LAT-P063's rows 1 and 2 must be WITHDRAWN in writing.

Three instrument guards, each for a failure this lane has actually hit:

1. **A failed sample is not a hole.** A throttled or errored request that parses
   as ``None`` would read as "the warmer said nothing", i.e. as a stall. Every
   sample records ``ok``; gaps in *sampling* are reported separately from gaps
   in *passes*, and any hole overlapping a sampling gap is flagged
   ``sampling_gap_overlap`` rather than counted clean (gotcha #53: an empty
   response is a response shape, not an absence).
2. **S2 rides along.** ``starts_24h`` is captured on every sample, so "did the
   scheduler keep firing through the hole" is answerable without a second run:
   advancing starts through a silent stretch means a *recording* defect, not a
   scheduling one.
3. **Our own polling is load** (LAT-P063 hazard 4). The interval is recorded in
   the artifact so the read carries its own observation cost.

Output is JSONL: one ``sample`` record per HTTP call (thin), one ``pass`` record
per newly-observed warmer pass (fat), and a final ``summary`` record.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _fetch(url: str, token: str, timeout: float) -> tuple[bool, Any, str]:
    """Return (ok, payload, note). ok=False NEVER yields a usable payload."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.status != 200:
                return False, None, f"http_{resp.status}"
            try:
                return True, json.loads(raw), ""
            except json.JSONDecodeError:
                # A 200 that is not JSON is a throttle/error page. Never a fact.
                return False, None, "non_json_200"
    except urllib.error.HTTPError as exc:
        return False, None, f"http_{exc.code}"
    except Exception as exc:  # noqa: BLE001 - the note carries the class
        return False, None, f"{type(exc).__name__}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=65.0)
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument(
        "--sibling",
        action="append",
        default=[],
        help="additional task name to sample every 10th tick (S3 correlation)",
    )
    args = ap.parse_args()

    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        print("BAINLUCK_API / ADMIN_TOKEN must be set", file=sys.stderr)
        return 2

    url = f"{api}/api/admin/task-metrics?task=warm_typeahead"
    started = _now()
    deadline = started + args.minutes * 60.0

    seen_pass_keys: set[str] = set()
    passes: list[dict[str, Any]] = []
    samples_ok = 0
    samples_bad = 0
    bad_notes: dict[str, int] = {}
    # Wall-clock instants of successful samples, for the sampling-gap guard.
    ok_instants: list[float] = []

    tick = 0
    with open(args.out, "w", buffering=1) as fh:
        fh.write(
            json.dumps(
                {
                    "record": "header",
                    "experiment": "LAT-P064 S1 probe-free warmer observation",
                    "started_at": _iso(started),
                    "planned_minutes": args.minutes,
                    "interval_s": args.interval,
                    "url": url,
                    "prediction": ">=1 hole > 120 s recurs",
                    "halt": "zero holes in 60 probe-free minutes => LAT-P063 rows 1-2 WITHDRAWN",
                    "probe_free": "this process issues NO /typeahead traffic",
                }
            )
            + "\n"
        )

        while _now() < deadline:
            tick += 1
            t = _now()
            ok, payload, note = _fetch(url, token, args.timeout)
            if ok and isinstance(payload, dict):
                samples_ok += 1
                ok_instants.append(t)
                summary = payload.get("last_result_summary") or {}
                if isinstance(summary, str):
                    try:
                        summary = json.loads(summary)
                    except json.JSONDecodeError:
                        summary = {}
                key = "|".join(
                    str(payload.get(f))
                    for f in ("last_started_at", "last_success_at", "last_duration_ms")
                )
                fh.write(
                    json.dumps(
                        {
                            "record": "sample",
                            "t": _iso(t),
                            "ok": True,
                            "starts_24h": payload.get("starts_24h"),
                            "successes_24h": payload.get("successes_24h"),
                            "failures_24h": payload.get("failures_24h"),
                            "hard_kills_24h": payload.get("hard_kills_24h"),
                            "last_started_at": payload.get("last_started_at"),
                            "last_success_at": payload.get("last_success_at"),
                            "pass_key_new": key not in seen_pass_keys,
                        }
                    )
                    + "\n"
                )
                if key not in seen_pass_keys:
                    seen_pass_keys.add(key)
                    rec = {
                        "record": "pass",
                        "observed_at": _iso(t),
                        "observed_mono": round(t - started, 3),
                        "last_started_at": payload.get("last_started_at"),
                        "last_success_at": payload.get("last_success_at"),
                        "last_duration_ms": payload.get("last_duration_ms"),
                        "starts_24h": payload.get("starts_24h"),
                        "successes_24h": payload.get("successes_24h"),
                        "hard_kills_24h": payload.get("hard_kills_24h"),
                        "health": payload.get("health"),
                        "summary": summary,
                    }
                    passes.append(rec)
                    fh.write(json.dumps(rec) + "\n")
            else:
                samples_bad += 1
                bad_notes[note] = bad_notes.get(note, 0) + 1
                fh.write(
                    json.dumps(
                        {"record": "sample", "t": _iso(t), "ok": False, "note": note}
                    )
                    + "\n"
                )

            if args.sibling and tick % 10 == 0:
                for name in args.sibling:
                    s_ok, s_payload, s_note = _fetch(
                        f"{api}/api/admin/task-metrics?task={name}", token, args.timeout
                    )
                    fh.write(
                        json.dumps(
                            {
                                "record": "sibling",
                                "t": _iso(_now()),
                                "task": name,
                                "ok": s_ok,
                                "note": s_note,
                                "last_started_at": (s_payload or {}).get(
                                    "last_started_at"
                                )
                                if s_ok
                                else None,
                                "last_duration_ms": (s_payload or {}).get(
                                    "last_duration_ms"
                                )
                                if s_ok
                                else None,
                                "starts_24h": (s_payload or {}).get("starts_24h")
                                if s_ok
                                else None,
                            }
                        )
                        + "\n"
                    )

            sleep_for = args.interval - (_now() - t)
            if sleep_for > 0:
                time.sleep(sleep_for)

        # ---- analysis -------------------------------------------------------
        # Sampling gaps: consecutive OK samples further apart than 3x interval.
        gaps: list[tuple[float, float]] = []
        for a, b in zip(ok_instants, ok_instants[1:]):
            if b - a > max(3 * args.interval, 15.0):
                gaps.append((a, b))

        holes: list[dict[str, Any]] = []
        for prev, cur in zip(passes, passes[1:]):
            # Interval between passes, measured on the warmer's OWN clock where
            # available (last_started_at), falling back to observation time.
            gap_s = None
            basis = "observed"
            try:
                p = datetime.fromisoformat(str(prev["last_started_at"]))
                c = datetime.fromisoformat(str(cur["last_started_at"]))
                gap_s = (c - p).total_seconds()
                basis = "last_started_at"
            except Exception:  # noqa: BLE001
                gap_s = cur["observed_mono"] - prev["observed_mono"]
            overlaps_sampling_gap = any(
                not (
                    g_end < started + prev["observed_mono"]
                    or g_start > started + cur["observed_mono"]
                )
                for g_start, g_end in gaps
            )
            holes.append(
                {
                    "from": prev["last_started_at"],
                    "to": cur["last_started_at"],
                    "gap_s": round(gap_s, 3) if gap_s is not None else None,
                    "basis": basis,
                    "starts_24h_delta": (cur.get("starts_24h") or 0)
                    - (prev.get("starts_24h") or 0),
                    "successes_24h_delta": (cur.get("successes_24h") or 0)
                    - (prev.get("successes_24h") or 0),
                    "sampling_gap_overlap": overlaps_sampling_gap,
                }
            )

        big = [
            h
            for h in holes
            if h["gap_s"] is not None
            and h["gap_s"] > 120.0
            and not h["sampling_gap_overlap"]
        ]
        tainted = [
            h
            for h in holes
            if h["gap_s"] is not None and h["gap_s"] > 120.0 and h["sampling_gap_overlap"]
        ]
        clean_gaps = [
            h["gap_s"] for h in holes if h["gap_s"] is not None and not h["sampling_gap_overlap"]
        ]
        clean_gaps_sorted = sorted(clean_gaps)

        summary_rec = {
            "record": "summary",
            "started_at": _iso(started),
            "ended_at": _iso(_now()),
            "duration_min": round((_now() - started) / 60.0, 2),
            "interval_s": args.interval,
            "samples_ok": samples_ok,
            "samples_bad": samples_bad,
            "bad_notes": bad_notes,
            "sampling_gaps": [
                {"from": _iso(a), "to": _iso(b), "gap_s": round(b - a, 1)}
                for a, b in gaps
            ],
            "distinct_passes": len(passes),
            "inter_pass_gaps_s": clean_gaps_sorted,
            "gap_max_s": clean_gaps_sorted[-1] if clean_gaps_sorted else None,
            "gap_median_s": (
                clean_gaps_sorted[len(clean_gaps_sorted) // 2]
                if clean_gaps_sorted
                else None
            ),
            "holes_over_120s_clean": big,
            "holes_over_120s_tainted_by_sampling_gap": tainted,
            "verdict": (
                "PREDICTION CONFIRMED - hole > 120 s recurred probe-free"
                if big
                else "HALT CANDIDATE - zero clean holes > 120 s"
            ),
            "holes": holes,
        }
        fh.write(json.dumps(summary_rec) + "\n")

    print(json.dumps({k: v for k, v in summary_rec.items() if k != "holes"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
