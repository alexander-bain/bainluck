#!/usr/bin/env python3
"""How old is each win-probability source on a LIVE game, right now?

Queue 067's instrument. The claim this queue makes is about cadence, so the
measurement has to be a DISTRIBUTION over repeated samples of the same live
game — a mean hides the thing that matters, which is how long a source can go
without saying anything. Before and after must be run with the same tool, so
the tool is a file, not a shell one-liner someone retypes.

    python3 scripts/measure_live_source_age.py --samples 44 --interval 5
    python3 scripts/measure_live_source_age.py --event 15298071 --samples 60

Reads `GET /api/events?status=live` (needs `BAINLUCK_API`; no auth required) and
ages every source's `updated_at` against the wall clock at fetch. Prints one
table per event:

    source       n    min_s    p50_s    p90_s     max_s   value_changes

`value_changes` is there so a flat age column cannot be mistaken for a working
source: a reading that is re-stamped every cycle and never moves is a live
source on a quiet game; a reading that never moves AND never re-stamps is a
source that stopped.

Caveat worth stating in any cert that uses this: `?status=live` selects on the
stored status. A game in a rain delay is still `live` here and its game state is
genuinely frozen, so a window that lands inside a stoppage measures the
stoppage, not the cadence. Print --show-samples and look at whether the SCORE
moved before drawing a cadence conclusion.
"""

import argparse
import json
import os
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone


def _percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    idx = min(int(q * len(ordered)), len(ordered) - 1)
    return ordered[idx]


def _parse_stamp(raw):
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def fetch(base):
    url = f"{base.rstrip('/')}/api/events?status=live"
    with urllib.request.urlopen(url, timeout=20) as resp:
        payload = json.loads(resp.read().decode())
    fetched_at = datetime.now(timezone.utc)
    events = payload if isinstance(payload, list) else payload.get("events", [])
    return fetched_at, events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=44)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--event", type=int, action="append", default=None,
                    help="restrict to these event ids (repeatable)")
    ap.add_argument("--base", default=os.environ.get("BAINLUCK_API",
                                                     "https://api.bainluck.com"))
    ap.add_argument("--show-samples", action="store_true")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    # event_id -> source -> list of (age_seconds, value)
    seen: dict = {}
    labels: dict = {}
    scores: dict = {}

    for i in range(args.samples):
        try:
            fetched_at, events = fetch(args.base)
        except Exception as e:                      # a dropped sample is a sample
            print(f"[{i}] fetch failed: {e}", file=sys.stderr)
            time.sleep(args.interval)
            continue

        for ev in events:
            eid = ev.get("id")
            if args.event and eid not in args.event:
                continue
            labels[eid] = f'{ev.get("away_team")} @ {ev.get("home_team")}'
            scores.setdefault(eid, []).append(
                (ev.get("away_score"), ev.get("home_score"))
            )
            for source, entry in (ev.get("win_probability_sources") or {}).items():
                if not isinstance(entry, dict) or "value" not in entry:
                    continue
                stamp = _parse_stamp(entry.get("updated_at"))
                age = (fetched_at - stamp).total_seconds() if stamp else None
                seen.setdefault(eid, {}).setdefault(source, []).append(
                    (age, entry.get("value"))
                )
            if args.show_samples:
                print(f'[{i}] {eid} {ev.get("away_score")}-{ev.get("home_score")} '
                      + " ".join(
                          f'{s}={(e or {}).get("value")}'
                          for s, e in sorted(
                              (ev.get("win_probability_sources") or {}).items()
                          )
                          if isinstance(e, dict)
                      ))
        if i < args.samples - 1:
            time.sleep(args.interval)

    out = {}
    for eid, sources in sorted(seen.items()):
        score_moves = len({s for s in scores.get(eid, [])})
        print(f"\n=== event {eid}  {labels.get(eid)}  "
              f"(distinct scores across the window: {score_moves})")
        print(f'{"source":<12}{"n":>4}{"min_s":>9}{"p50_s":>9}'
              f'{"p90_s":>9}{"max_s":>10}{"value_changes":>15}')
        rows = {}
        for source, samples in sorted(sources.items()):
            ages = [a for a, _ in samples if a is not None]
            values = [v for _, v in samples]
            changes = sum(
                1 for a, b in zip(values, values[1:]) if a != b
            )
            if not ages:
                print(f"{source:<12}{len(samples):>4}{'  (never stamped)':>41}")
                rows[source] = {"n": len(samples), "unstamped": True,
                                "value_changes": changes}
                continue
            row = {
                "n": len(ages),
                "min_s": round(min(ages), 1),
                "p50_s": round(statistics.median(ages), 1),
                "p90_s": round(_percentile(ages, 0.9), 1),
                "max_s": round(max(ages), 1),
                "value_changes": changes,
            }
            rows[source] = row
            print(f'{source:<12}{row["n"]:>4}{row["min_s"]:>9.1f}'
                  f'{row["p50_s"]:>9.1f}{row["p90_s"]:>9.1f}'
                  f'{row["max_s"]:>10.1f}{row["value_changes"]:>15}')
        out[eid] = {"label": labels.get(eid), "distinct_scores": score_moves,
                    "sources": rows}

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(
                {"base": args.base, "samples": args.samples,
                 "interval_s": args.interval, "events": out},
                fh, indent=2,
            )
        print(f"\nwrote {args.json_out}")

    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
