#!/usr/bin/env python3
"""Measure what a USER feels typing into /typeahead — corrected for gotcha #53.

WHY THIS EXISTS AS A SCRIPT AND NOT A `curl` LOOP.

LAT-P076 reported the program's headline user-felt number as **80% cold -> 0%
cold**. LAT-P077 could not reproduce it (45% at n=60, 57% at n=275 over 5h with
no warmer-path code changed between the two builds) and WITHDREW it. Two defects
in the instrument produced that swing, and both are the same shape:

**Defect 1 — timing without status (gotcha #53 inside the probe).** The shell
loop recorded `%{time_total}` and nothing else. Seven failed reads at 3.0-5.6ms
were therefore classified as *warm*, because a failure is fast. They were caught
only because 3ms is implausible against a measured 220ms warm floor — i.e. by
luck of magnitude, not by the instrument. Four further reads hit the 30s cap and
were counted merely as "cold", which UNDERSTATES the user cost rather than
overstating it. An HTTP 500 in 4ms and a cache hit in 4ms are the same number;
they are not the same fact.

**Defect 2 — probing a list that is not the warmed set.** The five terms probed
were `_STATIC_FLOOR`, which `resolve_head` uses ONLY when both measured sources
are empty. So the number tracked *which of five fixed strings happened to be in
the trending top-40 that hour* — a head-composition measurement wearing a
warmer-health label. That is the whole 80 -> 0 -> 45 swing.

So this script records, per read:

* `http_code` — anything other than 200 is `error`, never `warm`, never `cold`
* `bytes` — a 200 with an empty body is `empty`, not a hit (#53 again: an empty
  200 is a response shape, not an absence)
* `time_total_s` — and the classification threshold is a stated argument, not a
  constant buried in a loop
* `results` — the parsed result count, so a 200-with-zero-rows is visible

and it takes `--terms-from warmed|floor|file`, so the set being probed travels
with the measurement instead of being assumed by the reader.

Usage:
    python3 scripts/probe_typeahead_userfelt.py --rounds 12 --spacing 95 \\
        --out /tmp/uf.jsonl --label t3_horizon
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

#: `app/tasks/typeahead_warmer.py::_STATIC_FLOOR`, mirrored. NOT the warmed set —
#: see the module docstring. Kept so the historical series stays comparable.
STATIC_FLOOR = (
    "world series",
    "stanley cup",
    "world cup",
    "super bowl",
    "nba champion",
)

#: Measured warm floor for `/typeahead` (LAT-P077, n=110 legitimate warm reads).
#: A read faster than this is not "very warm", it is suspicious — the script
#: flags it rather than silently crediting it.
IMPLAUSIBLY_FAST_S = 0.050

#: `/typeahead`'s own budget (#1866's title). Anything at or above this is cold.
DEFAULT_WARM_THRESHOLD_S = 0.150


def classify(http_code: int, nbytes: int, elapsed_s: float, warm_s: float) -> str:
    """Three-plus states, never two. An error is not a fast warm read."""
    if http_code != 200:
        return "error"
    if nbytes <= 0:
        return "empty"
    if elapsed_s < IMPLAUSIBLY_FAST_S:
        return "implausible"
    return "warm" if elapsed_s < warm_s else "cold"


def probe_once(base: str, term: str, timeout_s: float) -> dict:
    url = base.rstrip("/") + "/api/events/typeahead?" + urllib.parse.urlencode({"q": term})
    started = time.time()
    http_code = 0
    body = b""
    err = None
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            http_code = resp.getcode()
            body = resp.read()
    except urllib.error.HTTPError as exc:  # a real HTTP answer, just not 200
        http_code = exc.code
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001
            body = b""
        err = f"http:{exc.code}"
    except Exception as exc:  # noqa: BLE001 — timeouts, resets, DNS
        err = f"{type(exc).__name__}:{exc}"
    elapsed = time.time() - started

    results = None
    if http_code == 200 and body:
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                for key in ("results", "items", "suggestions"):
                    if isinstance(parsed.get(key), list):
                        results = len(parsed[key])
                        break
            elif isinstance(parsed, list):
                results = len(parsed)
        except Exception:  # noqa: BLE001
            results = None

    return {
        "term": term,
        "http_code": http_code,
        "bytes": len(body),
        "time_total_s": round(elapsed, 6),
        "results": results,
        "error": err,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("BAINLUCK_API", "https://api.bainluck.com"))
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--spacing", type=float, default=95.0, help="seconds between rounds")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--warm-threshold", type=float, default=DEFAULT_WARM_THRESHOLD_S)
    ap.add_argument("--terms-from", default="floor", choices=("floor", "file"))
    ap.add_argument("--terms-file", default=None)
    ap.add_argument("--label", default="userfelt")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.terms_from == "file":
        if not args.terms_file:
            print("--terms-from file requires --terms-file", file=sys.stderr)
            return 4
        with open(args.terms_file) as fh:
            terms = [line.strip() for line in fh if line.strip()]
    else:
        terms = list(STATIC_FLOOR)

    if not terms:
        print("no terms to probe", file=sys.stderr)
        return 4

    counts: dict[str, int] = {}
    with open(args.out, "a") as out:
        for rnd in range(1, args.rounds + 1):
            for term in terms:
                rec = probe_once(args.base, term, args.timeout)
                rec["verdict"] = classify(
                    rec["http_code"], rec["bytes"], rec["time_total_s"], args.warm_threshold
                )
                rec["round"] = rnd
                rec["label"] = args.label
                rec["terms_from"] = args.terms_from
                rec["warm_threshold_s"] = args.warm_threshold
                rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                counts[rec["verdict"]] = counts.get(rec["verdict"], 0) + 1
                out.write(json.dumps(rec) + "\n")
                out.flush()
                print(
                    f"r{rnd} {term!r:20} {rec['verdict']:12} "
                    f"http={rec['http_code']} bytes={rec['bytes']} "
                    f"t={rec['time_total_s']:.3f}s results={rec['results']}",
                    flush=True,
                )
            if rnd < args.rounds:
                time.sleep(args.spacing)

    total = sum(counts.values())
    print(f"\nSUMMARY label={args.label} n={total} {counts}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
