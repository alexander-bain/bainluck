"""Walk the deployed overlap-trading census to exhaustion and fix N.

CAL-P030 (#1544), exam item 1. The census rail (``app/tasks/census_overlap_trading``,
CAL-P027) is bounded PER WINDOW by design and returns a ``next_offset``; nothing
shipped with it walks that cursor to the end. Its first real walk therefore had
to hand-roll a driver, and the second one would have hand-rolled it again — so
this is that driver, with the adaptive policy living in the census module beside
the rail rather than in a temp file beside the operator.

Read-only end to end. The rail never writes and accepts-and-ignores ``apply``;
this script never passes it. Needs ``ADMIN_TOKEN`` + ``BAINLUCK_API``
(``source ~/.claude/.env``).

    python3 backend/scripts/walk_overlap_census.py                  # full walk
    python3 backend/scripts/walk_overlap_census.py --offset 1234567  # resume
    python3 backend/scripts/walk_overlap_census.py --report-only     # re-fold

**A partial walk is reported as partial and never as an N** — see
:func:`is_complete_walk`. That is the whole discipline this script exists to
enforce: the exam says "N is measured, not chosen", and a threshold fixed
against a prefix of the id space is a choice wearing a measurement's clothing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import requests  # noqa: E402

from app.tasks.census_overlap_trading import (  # noqa: E402
    MOVE_BANDS,
    VOLUME_STATES,
    WALK_SCAN_MIN,
    WALK_SCAN_START,
    is_complete_walk,
    merge_windows,
    next_scan,
    precision_for_threshold,
    with_rates,
)

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")
TOKEN = os.environ.get("ADMIN_TOKEN", "")
ENDPOINT = "/api/admin/repairs/overlap-trading-census"

#: Density floors N is reported at. Reporting one floor would hide that the
#: answer moves with it — which this walk found that it does.
MIN_DENSITIES = (2, 5, 10)


def _one_window(scan: int, cursor: int, timeout_s: int) -> tuple[bool, object, float]:
    """One bounded window. Returns ``(ok, payload_or_error, seconds)``."""
    t0 = time.time()
    try:
        resp = requests.post(
            f"{API}{ENDPOINT}",
            params={"limit": scan, "offset": cursor},
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        return False, f"transport: {exc}", time.time() - t0
    dt = time.time() - t0
    if resp.status_code != 200:
        # The rail's own per-window statement timeout surfaces here as a 500.
        # That is a hot window, not a broken rail, and the caller shrinks.
        return False, f"HTTP {resp.status_code}: {resp.text[:160]}", dt
    return True, resp.json()["result"], dt


def walk(out_path: str, start_offset: int, timeout_s: int) -> int:
    cursor = start_offset
    scan = WALK_SCAN_START
    windows = rows = eligible = hot = 0
    t_start = time.time()

    # Append on resume, truncate on a fresh start: folding two different walks
    # of overlapping id ranges would double-count, and the double-count would
    # look like a larger population rather than like a mistake.
    mode = "a" if start_offset else "w"
    with open(out_path, mode):
        pass

    print(f"START offset={cursor} scan={scan} -> {out_path}", flush=True)
    while True:
        ok, payload, dt = _one_window(scan, cursor, timeout_s)

        if not ok:
            hot += 1
            if scan <= WALK_SCAN_MIN:
                print(f"FATAL cursor={cursor} irreducible at scan={scan}: {payload}",
                      file=sys.stderr)
                print("ABORT — walk is INCOMPLETE. Do not fold this as a population.",
                      file=sys.stderr)
                return 1
            scan = next_scan(scan, seconds=dt, timed_out=True)
            print(f"  hot window {dt:.1f}s -> scan={scan}, retry SAME cursor={cursor}",
                  flush=True)
            continue

        with open(out_path, "a") as fh:
            fh.write(json.dumps(payload) + "\n")
        windows += 1
        rows += payload["rows_walked"]
        eligible += payload.get("eligible_rows_in_window") or 0

        if payload["rows_walked"] == 0 or payload["exhausted"]:
            print(f"EXHAUSTED after {windows} windows · {rows:,} rows · "
                  f"{eligible:,} eligible · {hot} hot windows · "
                  f"{time.time() - t_start:.0f}s", flush=True)
            return 0

        cursor = payload["next_offset"]
        if windows % 25 == 0:
            print(f"  w={windows} cursor={cursor} rows={rows:,} eligible={eligible:,} "
                  f"scan={scan} last={dt:.1f}s elapsed={time.time() - t_start:.0f}s",
                  flush=True)
        scan = next_scan(scan, seconds=dt, timed_out=False)


def report(out_path: str) -> int:
    windows = [json.loads(line) for line in open(out_path) if line.strip()]
    if not windows:
        print("no windows to fold", file=sys.stderr)
        return 1
    complete = is_complete_walk(windows)
    rows = sum(w["rows_walked"] for w in windows)
    merged = merge_windows(windows)
    rated = with_rates(merged)
    total = sum(r["n"] for r in rated)

    print(f"\nwindows={len(windows)} rows_walked={rows:,} "
          f"cohorts={len(rated)} eligible={total:,}")
    print(f"COMPLETE WALK: {complete}")
    if not complete:
        print("!! PARTIAL — the figures below describe a PREFIX of the id space.")
        print("!! Do not publish an N from this. Resume with --offset "
              f"{windows[-1]['next_offset']}.")

    print("\n=== volume_state (three-valued; 'absent' is NOT 'zero') ===")
    by_vs: dict[str, int] = {}
    for r in rated:
        by_vs[r["volume_state"]] = by_vs.get(r["volume_state"], 0) + r["n"]
    for v in VOLUME_STATES:
        n = by_vs.get(v, 0)
        print(f"  {v:9s} {n:>12,}  {(100.0 * n / total if total else 0):5.2f}%")

    print("\n=== N — precision/recall of '>= n moves' predicting volume > 0 ===")
    for md in MIN_DENSITIES:
        print(f"\n  -- min_density={md} --")
        print(f"  {'N':>4} {'precision':>10} {'recall':>9} {'support':>12}")
        for _label, lo, _hi in MOVE_BANDS:
            if lo == 0:
                continue
            res = precision_for_threshold(merged, lo, min_density=md)
            if not res.get("supported"):
                print(f"  {lo:>4} {'—':>10} {'—':>9} {'—':>12}   "
                      f"UNSUPPORTED: {res.get('reason')}")
                continue
            print(f"  {lo:>4} {res['precision']:>10.4f} {res['recall']:>9.4f} "
                  f"{res['support']:>12,}")

    print("\n=== volume coverage by source ===")
    per: dict[str, dict] = {}
    for r in rated:
        s = per.setdefault(r["source"], {"n": 0, "vol": 0})
        s["n"] += r["n"]
        if r["volume_state"] != "absent":
            s["vol"] += r["n"]
    for src, s in sorted(per.items(), key=lambda kv: -kv[1]["n"]):
        print(f"  {src:22s} n={s['n']:>10,}  volume present "
              f"{(100.0 * s['vol'] / s['n'] if s['n'] else 0):5.2f}%")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="/tmp/overlap_census_windows.jsonl")
    ap.add_argument("--offset", type=int, default=0, help="resume cursor")
    ap.add_argument("--timeout", type=int, default=90, help="per-request seconds")
    ap.add_argument("--report-only", action="store_true",
                    help="fold an existing --out without walking")
    args = ap.parse_args()

    if args.report_only:
        return report(args.out)
    if not TOKEN:
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2
    rc = walk(args.out, args.offset, args.timeout)
    report(args.out)
    return rc


if __name__ == "__main__":
    sys.exit(main())
