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
#:
#: 🔴 **A FALLBACK, NOT THE DEFAULT PATH — and LAT-P083 measured why.** This
#: constant is an absolute wall time, so it silently encodes an assumption about
#: WHERE THE PROBER STANDS. Measured 2026-08-23 from the agent sandbox, ten
#: requests to `/api/events/search/trending` (one Redis read, a tiny payload):
#: **p50 0.226 s, min 0.216, max 0.235**, with `time_connect` ~0.0002 s — i.e.
#: the whole of it is time-to-first-byte through the egress proxy, and none of
#: it is the server.
#:
#: **0.150 s is BELOW that floor, so from this vantage point the probe could
#: never return `warm` and cold-share was pinned at 100 % by construction** — a
#: gate that cannot go green, which is the same defect class as LAT-P079's
#: staged `samples == 0 => INCONCLUSIVE` with the sign flipped. Eight readings
#: at 0.220 s — at the floor, and therefore certainly cache hits — were graded
#: `cold` in this cycle's first pass.
#:
#: So the threshold is now DERIVED per run by `--calibrate` (the default), and
#: this constant survives only for `--warm-threshold`-explicit runs and for the
#: tests. The charter's "measured the same way each time" is satisfied by
#: deriving it, not by fixing it: a constant would report different cold-shares
#: from CI, a laptop and this sandbox for identical server behaviour.
DEFAULT_WARM_THRESHOLD_S = 0.150

#: The endpoint the calibration pass times. It must be (a) cheap server-side, so
#: what it measures is transport rather than work, and (b) something we are
#: already allowed to hammer. `/api/events/search/trending` is a single Redis
#: read behind a public GET.
CALIBRATION_URL_PATH = "/api/events/search/trending"
CALIBRATION_SAMPLES = 8

#: How much SERVER time a genuine `/typeahead` cache hit is allowed on top of
#: the measured transport floor. The warm path is ~13 ms of server work, so 100
#: ms is four-times generous — deliberately, because the quantity being
#: separated is not close: a warm read lands at the floor and a cold one at
#: 1.0-1.8 s, so this threshold has ~4x of margin on both sides and its exact
#: placement changes no verdict.
WARM_SERVER_BUDGET_S = 0.100


def classify(http_code: int, nbytes: int, elapsed_s: float, warm_s: float) -> str:
    """Three-plus states, never two. An error is not a fast warm read."""
    if http_code != 200:
        return "error"
    if nbytes <= 0:
        return "empty"
    if elapsed_s < IMPLAUSIBLY_FAST_S:
        return "implausible"
    return "warm" if elapsed_s < warm_s else "cold"


def measure_transport_floor(base: str, timeout_s: float) -> dict:
    """Time a deliberately cheap endpoint, so the warm threshold can be DERIVED.

    Returns `{"floor_p50_s", "samples", "raw"}`, or raises. The caller must
    refuse to classify if this cannot be measured — an unknown floor means an
    unknown threshold, and defaulting to a constant is how the 0.150 s wall came
    to be applied from a vantage point with a 0.226 s floor.
    """
    import statistics

    url = base.rstrip("/") + CALIBRATION_URL_PATH
    raw = []
    for _ in range(CALIBRATION_SAMPLES):
        started = time.time()
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            resp.read()
            if resp.getcode() != 200:
                raise RuntimeError(f"calibration endpoint returned {resp.getcode()}")
        raw.append(round(time.time() - started, 4))
    return {
        "floor_p50_s": round(statistics.median(raw), 4),
        "floor_min_s": min(raw),
        "samples": len(raw),
        "raw": raw,
        "url": url,
    }


def probe_once(base: str, term: str, timeout_s: float) -> dict:
    url = base.rstrip("/") + "/api/events/typeahead?" + urllib.parse.urlencode({"q": term})
    # LAT-P118: declare machine traffic so this probe stops voting in
    # `search:trending:24h`, the other half of the head the warmer elects from.
    req = urllib.request.Request(url, headers={"X-Bainluck-Origin": "harness"})
    started = time.time()
    http_code = 0
    body = b""
    err = None
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
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
    ap.add_argument(
        "--warm-threshold",
        type=float,
        default=None,
        help=(
            "absolute seconds. OMIT IT: the default is to CALIBRATE against the "
            "measured transport floor, because an absolute wall encodes where "
            "the prober stands (see DEFAULT_WARM_THRESHOLD_S)."
        ),
    )
    ap.add_argument(
        "--no-calibrate",
        action="store_true",
        help=f"skip calibration and use --warm-threshold or {DEFAULT_WARM_THRESHOLD_S}s",
    )
    ap.add_argument("--terms-from", default="floor", choices=("floor", "file"))
    ap.add_argument("--terms-file", default=None)
    ap.add_argument("--label", default="userfelt")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.terms_from == "file":
        if not args.terms_file:
            print("--terms-from file requires --terms-file", file=sys.stderr)
            return 4
        # `#` starts a comment. The frozen headline set
        # (`docs/audits/latency/headline-probe-terms.txt`) carries its own
        # provenance and its own change protocol in the file, because a term set
        # whose reasoning lives somewhere else is a term set that gets edited by
        # someone who never read the reasoning — and LAT-P076 lost a headline to
        # exactly that. Without this, every comment line would be probed as a
        # query, and each one would also VOTE in the trending counter.
        with open(args.terms_file) as fh:
            terms = [
                line.strip()
                for line in fh
                if line.strip() and not line.lstrip().startswith("#")
            ]
    else:
        terms = list(STATIC_FLOOR)

    if not terms:
        print("no terms to probe", file=sys.stderr)
        return 4

    # --- derive the warm threshold, or say plainly that we did not ----------
    calibration = None
    if args.warm_threshold is not None:
        warm_threshold = args.warm_threshold
        threshold_source = "explicit --warm-threshold"
    elif args.no_calibrate:
        warm_threshold = DEFAULT_WARM_THRESHOLD_S
        threshold_source = "constant (--no-calibrate)"
    else:
        try:
            calibration = measure_transport_floor(args.base, args.timeout)
        except Exception as exc:  # noqa: BLE001
            # EXIT 3, not a silent fall back to the constant. An unmeasurable
            # floor means an unknown threshold, and the whole point of this
            # block is that the constant is wrong from some vantage points.
            print(f"CALIBRATION FAILED: {exc}", file=sys.stderr)
            print(
                "refusing to classify warm/cold against an unverified threshold "
                "— pass --warm-threshold explicitly if you know the floor",
                file=sys.stderr,
            )
            return 3
        warm_threshold = round(
            calibration["floor_p50_s"] + WARM_SERVER_BUDGET_S, 4
        )
        threshold_source = (
            f"calibrated: floor p50 {calibration['floor_p50_s']:.3f}s"
            f" + {WARM_SERVER_BUDGET_S:.3f}s server budget"
        )
        print(
            f"CALIBRATION {calibration['url']} n={calibration['samples']} "
            f"floor_p50={calibration['floor_p50_s']:.3f}s "
            f"floor_min={calibration['floor_min_s']:.3f}s "
            f"-> warm_threshold={warm_threshold:.3f}s",
            flush=True,
        )
        if warm_threshold < DEFAULT_WARM_THRESHOLD_S:
            print(
                f"NOTE: calibrated threshold {warm_threshold:.3f}s is BELOW the "
                f"{DEFAULT_WARM_THRESHOLD_S}s constant — this vantage point is "
                "faster than the one the constant was written from.",
                flush=True,
            )

    counts: dict[str, int] = {}
    with open(args.out, "a") as out:
        for rnd in range(1, args.rounds + 1):
            for term in terms:
                rec = probe_once(args.base, term, args.timeout)
                rec["verdict"] = classify(
                    rec["http_code"], rec["bytes"], rec["time_total_s"], warm_threshold
                )
                rec["round"] = rnd
                rec["label"] = args.label
                rec["terms_from"] = args.terms_from
                rec["warm_threshold_s"] = warm_threshold
                rec["threshold_source"] = threshold_source
                rec["transport_floor_p50_s"] = (
                    calibration["floor_p50_s"] if calibration else None
                )
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
    print(
        f"\nSUMMARY label={args.label} n={total} {counts} "
        f"warm_threshold={warm_threshold:.3f}s ({threshold_source})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
