#!/usr/bin/env python3
"""Poll the anonymous live-containing feed shapes and print the cache sawtooth (#2236).

The instrument for one specific claim: **does a live-containing `/api/feed`
payload ever fall out of the cache entirely, forcing a user to pay a cold
build?** Everything it prints exists to separate that from the two states it is
easily confused with.

* `X-Feed-Cache` alone cannot answer it. `hit` and `stale_hit` are both cache
  serves and both fine; only `miss` is the defect. But a `miss` also happens
  once at process start and once after every release, so a single `miss` proves
  nothing — the claim is about a REPEATING hole, which is why this samples over
  multiple ceiling-widths rather than taking n=3.
* `cache.built_at` (CERT-409) is the age of the SCORE, not of the copy, so
  `age_s` here is the number #2216's ceiling actually bounds. A payload served
  at `age_s > 60` with `live: true` would be a ceiling violation; a payload
  REBUILT at `age_s ~ 0` right after a 60s-old one is the #2236 sawtooth.
* `cache.live` is printed on every row because the whole interaction only
  applies to live-containing payloads. A run taken when nothing is live shows
  ttl 60/300 and proves nothing about the fix either way — so the summary
  refuses to grade a run in which no sample was live.

Usage:
    python3 backend/scripts/measure_live_feed_sawtooth.py [--minutes 5]
                                                          [--interval 10]
                                                          [--out FILE]

Reads `BAINLUCK_API` from the environment (falls back to production). Sends no
`x-session-id`, deliberately: the anonymous key is the one the warmer publishes
and the one a first-time visitor reads.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

DEFAULT_API = "https://api.bainluck.com"

#: The two real anonymous first-paint sports shapes. Native is `limit=50`
#: (`APIClient.fetchFeed`'s default), web is `limit=20` (`FEED_PAGE_LIMIT`).
#: Both were measured live-containing and both showed the sawtooth, so both are
#: sampled — a fix that covered only the shape it was reported against is the
#: LAT-P099 defect, and this program has now paid for it twice.
SHAPES = (
    ("sports_native", "limit=50&mode=sports&offset=0"),
    ("sports_web", "limit=20&mode=sports&offset=0"),
)


def _sample(api: str, query: str, timeout: float) -> dict:
    started = time.monotonic()
    req = urllib.request.Request(f"{api}/api/feed?{query}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            header = resp.headers.get("X-Feed-Cache", "")
    except Exception as exc:  # noqa: BLE001 — a timeout IS a datapoint here
        return {"ms": round((time.monotonic() - started) * 1000), "error": str(exc)[:80]}
    ms = round((time.monotonic() - started) * 1000)
    try:
        cache = (json.loads(raw) or {}).get("cache") or {}
    except Exception:  # noqa: BLE001
        cache = {}
    built_at = cache.get("built_at")
    return {
        "ms": ms,
        "status": header or cache.get("status") or "none",
        "live": cache.get("live"),
        "ttl": cache.get("ttl_seconds"),
        "stale_ttl": cache.get("stale_ttl_seconds"),
        "age_s": round(time.time() - built_at, 1) if built_at else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=5.0)
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--timeout", type=float, default=45.0)
    ap.add_argument("--api", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import os

    api = args.api or os.environ.get("BAINLUCK_API") or DEFAULT_API
    sink = open(args.out, "w") if args.out else sys.stdout

    def emit(line: str) -> None:
        print(line, file=sink, flush=True)

    try:
        with urllib.request.urlopen(f"{api}/api/health", timeout=15) as resp:
            health = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        health = {"error": str(exc)[:80]}
    emit(f"# api={api} commit={health.get('commit')} uptime_s={health.get('uptime_seconds')}")
    emit(f"# started_utc={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    # A read inside the post-deploy window is not evidence — the caches are
    # empty for reasons that have nothing to do with the beat under test.
    if isinstance(health.get("uptime_seconds"), (int, float)) and health["uptime_seconds"] < 300:
        emit("# ⚠️ uptime < 300s — post-deploy window, this run is NOT evidence")
    emit("# t_s\tshape\tms\tstatus\tlive\tttl\tstale\tage_s")

    t0 = time.monotonic()
    rows: list[tuple[str, dict]] = []
    while time.monotonic() - t0 < args.minutes * 60:
        for label, query in SHAPES:
            s = _sample(api, query, args.timeout)
            rows.append((label, s))
            emit(
                f"{round(time.monotonic() - t0)}\t{label}\t{s['ms']}\t"
                f"{s.get('status', 'ERROR')}\t{s.get('live')}\t{s.get('ttl')}\t"
                f"{s.get('stale_ttl')}\t{s.get('age_s')}\t{s.get('error', '')}"
            )
        time.sleep(args.interval)

    emit("")
    emit("# --- summary ---------------------------------------------------")
    for label, _ in SHAPES:
        mine = [s for lbl, s in rows if lbl == label]
        served = [s for s in mine if "error" not in s]
        misses = [s for s in served if s.get("status") == "miss"]
        live = [s for s in served if s.get("live") is True]
        ages = [s["age_s"] for s in served if s.get("age_s") is not None]
        ms_warm = sorted(s["ms"] for s in served if s.get("status") != "miss")
        ms_cold = sorted(s["ms"] for s in misses)
        emit(
            f"# {label}: n={len(mine)} live={len(live)}/{len(served)} "
            f"MISS={len(misses)}/{len(served)} "
            f"warm_p50={ms_warm[len(ms_warm)//2] if ms_warm else '-'}ms "
            f"cold={ms_cold or '-'} "
            f"max_age={max(ages) if ages else '-'}s"
        )
        if not live:
            emit(
                f"# {label}: ⚠️ NO SAMPLE WAS LIVE — this run grades nothing about "
                "#2236 in either direction"
            )
    if sink is not sys.stdout:
        sink.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
