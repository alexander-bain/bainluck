#!/usr/bin/env python3
"""Measure the #2143 shared-build delta on `/api/feed`, end to end from a client.

TWO PHASES, BECAUSE THEY ANSWER DIFFERENT QUESTIONS
---------------------------------------------------
**Phase A — the charter headline.** 14 sequential anonymous `GET /api/feed?limit=20`,
no session header, nothing else of this session's in flight. This is byte-for-byte the
instrument that produced the banked before (`docs/audits/latency/lat-p085-feed-clean.json`,
p50 372.0 ms, n=14) and exists so the after is a subtraction rather than a comparison of
two different measurements. Ruling 127: a census that samples every request counts the
observer, so phase A runs alone.

**Phase B — the #2143 delta itself.** Phase A cannot see the fix. A single repeated
anonymous principal is the *warm* path; #2143 shares the principal-INDEPENDENT half of a
build across *distinct* principals, so its payoff lands on the path where a second
principal would otherwise have paid a full cold build. Phase B fires bursts of distinct
`x-session-id` principals back to back and reads `X-Feed-Shared` — the response header
that names which artifacts (`concepts`, `canonical_counts`) were REUSED rather than
rebuilt.

WHY BURSTS OF THREE, NOT PAIRS
-------------------------------
The cache is deliberately **process-local**, not Redis (see the module docstring of
`app/utils/principal_independent_cache.py`). Production runs one web dyno with
`WEB_CONCURRENCY=2`, so **two worker processes** answer in rotation and a second principal
has roughly a coin-flip chance of landing on the worker that just built. A pair would
therefore report ~50% sharing even if sharing were perfect, and a reader would have no way
to tell a 50% hit rate from a half-broken cache. Bursts of three make at least one
same-worker repeat likely, and the script reports the hit rate rather than a verdict, so
the process-local ceiling stays visible in the number instead of hiding inside it.

READING THE RESULT
------------------
`shared` and `unshared` cohorts are split by the presence of `X-Feed-Shared`. The delta is
`unshared_p50 - shared_p50`. Both cohorts come from the same burst seconds apart, which is
the same same-batch-control discipline the teams-FTS gate uses — production load moves
several-fold inside a minute, and two cohorts measured at different times are not
subtractable.

A zero-length `shared` cohort is NOT "the fix does not work"; check `X-Feed-Singleflight`
and whether `FEED_SHARED_BUILD_TTL_S` is set to 0 (the kill switch) before concluding
anything. An empty result and a disabled feature must not read the same (gotcha #53).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid

DEFAULT_BASE = "https://api.bainluck.com"

#: Response headers worth keeping per sample. All are bounded, allowlisted
#: diagnostics — none carries identity.
KEEP_HEADERS = (
    "X-Feed-Shared",
    "X-Feed-Singleflight",
    "X-Feed-Count-Scope",
    "X-Feed-Counts",
    "X-Feed-Stages",
)


def _get(base: str, path: str, session_id: str | None, timeout: float) -> dict:
    request = urllib.request.Request(f"{base}{path}", method="GET")
    if session_id:
        request.add_header("x-session-id", session_id)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            elapsed = (time.perf_counter() - started) * 1000.0
            headers = {k: response.headers.get(k) for k in KEEP_HEADERS}
            try:
                items = len((json.loads(body) or {}).get("items") or [])
            except (json.JSONDecodeError, AttributeError):
                items = None
            return {
                "ms": round(elapsed, 1),
                "http": response.status,
                "bytes": len(body),
                "items": items,
                **{k.lower(): v for k, v in headers.items()},
            }
    except urllib.error.HTTPError as exc:
        return {
            "ms": round((time.perf_counter() - started) * 1000.0, 1),
            "http": exc.code,
            "bytes": 0,
            "items": None,
            "error": exc.reason,
        }
    except Exception as exc:  # transport, not a verdict
        return {
            "ms": round((time.perf_counter() - started) * 1000.0, 1),
            "http": None,
            "bytes": 0,
            "items": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _stage_total_ms(sample: dict) -> float | None:
    """Server-side total, parsed out of `X-Feed-Stages` (`name=ms,...`)."""
    raw = sample.get("x-feed-stages")
    if not raw:
        return None
    total = 0.0
    for part in raw.split(","):
        _, _, value = part.partition("=")
        try:
            total += float(value)
        except ValueError:
            continue
    return round(total, 1)


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[int(q * (len(ordered) - 1))]


def _describe(label: str, samples: list[dict]) -> dict | None:
    ok = [s for s in samples if s.get("http") == 200]
    if not ok:
        print(f"  {label:<10} NO OK SAMPLES ({len(samples)} attempted)")
        return None
    times = [s["ms"] for s in ok]
    summary = {
        "n": len(ok),
        "attempted": len(samples),
        "p50": round(statistics.median(times), 1),
        "p90": round(_percentile(times, 0.90), 1),
        "max": round(max(times), 1),
    }
    print(
        f"  {label:<10} n={summary['n']:<3} p50={summary['p50']:8.1f}ms "
        f"p90={summary['p90']:8.1f}  max={summary['max']:8.1f}"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--headline-n", type=int, default=14, help="phase A samples")
    parser.add_argument("--bursts", type=int, default=8, help="phase B bursts")
    parser.add_argument("--burst-size", type=int, default=3, help="principals per burst")
    parser.add_argument("--burst-gap", type=float, default=3.0, help="seconds between bursts")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--label", default="unlabelled")
    parser.add_argument("--out", help="write the full result JSON here")
    parser.add_argument("--skip-headline", action="store_true")
    args = parser.parse_args()

    result: dict = {"label": args.label, "base": args.base}

    if not args.skip_headline:
        print(f"phase A — charter headline, {args.headline_n} sequential anonymous requests")
        headline = []
        for i in range(args.headline_n):
            sample = _get(args.base, "/api/feed?limit=20", None, args.timeout)
            sample["i"] = i
            headline.append(sample)
            time.sleep(0.4)
        result["headline"] = headline
        result["headline_summary"] = _describe("headline", headline)
        shared_seen = sum(1 for s in headline if s.get("x-feed-shared"))
        print(f"  X-Feed-Shared present on {shared_seen}/{len(headline)} headline samples")
        print()

    print(
        f"phase B — #2143 shared build, {args.bursts} bursts x {args.burst_size} "
        f"distinct principals"
    )
    burst_samples: list[dict] = []
    for b in range(args.bursts):
        for p in range(args.burst_size):
            session_id = f"lat-p087-{uuid.uuid4().hex[:16]}"
            sample = _get(args.base, "/api/feed?limit=20", session_id, args.timeout)
            sample.update({"burst": b, "pos": p})
            burst_samples.append(sample)
        time.sleep(args.burst_gap)
    result["bursts"] = burst_samples

    ok = [s for s in burst_samples if s.get("http") == 200]
    shared = [s for s in ok if s.get("x-feed-shared")]
    unshared = [s for s in ok if not s.get("x-feed-shared")]

    print(f"  ok={len(ok)}/{len(burst_samples)}   "
          f"shared={len(shared)} ({len(shared) / max(1, len(ok)) * 100:.1f}%)   "
          f"unshared={len(unshared)}")
    shared_summary = _describe("shared", shared) if shared else None
    unshared_summary = _describe("unshared", unshared) if unshared else None

    delta = None
    if shared_summary and unshared_summary:
        delta = round(unshared_summary["p50"] - shared_summary["p50"], 1)
        pct = delta / unshared_summary["p50"] * 100 if unshared_summary["p50"] else 0.0
        print(f"\n  #2143 wall delta: {delta:+.1f} ms  ({pct:+.1f}% of the unshared p50)")
    else:
        print("\n  #2143 wall delta: NOT MEASURABLE — one cohort is empty.")
        print("  This is a shape, not a finding: check X-Feed-Singleflight and whether")
        print("  FEED_SHARED_BUILD_TTL_S is 0 (kill switch) before reading it as a failure.")

    server_shared = [v for v in (_stage_total_ms(s) for s in shared) if v is not None]
    server_unshared = [v for v in (_stage_total_ms(s) for s in unshared) if v is not None]
    server_delta = None
    if server_shared and server_unshared:
        server_delta = round(
            statistics.median(server_unshared) - statistics.median(server_shared), 1
        )
        print(
            f"  server-stage delta: {server_delta:+.1f} ms  "
            f"(unshared {statistics.median(server_unshared):.1f} -> "
            f"shared {statistics.median(server_shared):.1f})"
        )

    names = sorted({n for s in shared for n in (s.get("x-feed-shared") or "").split(",") if n})
    if names:
        print(f"  artifacts reused: {', '.join(names)}")

    result["summary"] = {
        "shared": shared_summary,
        "unshared": unshared_summary,
        "shared_share_pct": round(len(shared) / max(1, len(ok)) * 100, 1),
        "wall_delta_ms": delta,
        "server_stage_delta_ms": server_delta,
        "artifacts_reused": names,
    }

    if args.out:
        with open(args.out, "w") as handle:
            json.dump(result, handle, indent=1)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
