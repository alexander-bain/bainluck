"""Aggregate boring-rate@20 census — the one UX-P101 owed and refused to fake.

WHY A CENSUS AND NOT A RUN. `audit_feed_quality.py` reports one read. Cycle 98
proved a single card leaving the top-20 window is not a rate, so #1958 stayed
open. A rate needs a POPULATION of independent reads, and on this feed
"independent" is a measured property, not an assumption:

  - `/api/feed` caches for 60 s (`cache.ttl_seconds`) with a 300 s stale
    window, so two reads a minute apart are routinely ONE build read twice.
    Spacing alone does not fix this and the cache LABEL does not either: the
    observed statuses are `miss`, `hit` AND `stale_hit`, and a filter written
    against `hit` silently counts every `stale_hit` as a fresh sample. This
    script therefore establishes independence by CONTENT — it fingerprints the
    ordered top-20 and counts each distinct build once, whatever the label
    claims. A cache header is the server's story about a read; the cards are
    the read.
  - The feed can answer 200 while DEGRADED (`degraded_reason`). On
    2026-08-18 the default feed returned `futures_timeout` and served 25
    concept/tournament cards with ZERO futures — and the audit script printed
    `boring-rate@20: 0/20` over that empty population and exited 0.

That last line is the whole reason this file exists. A rate over nothing reads
as perfect, which is gotcha #53 wearing a percentage: the emptier reading was
taken as the better fact. Every number below therefore carries its own
denominator, and a read whose population is short of the window is reported as
SHORT, never averaged in silently.

Read-only. Public endpoint. No key.

Usage:
    python3 backend/scripts/census_boring_rate.py --reads 12 --spacing 70
    CENSUS_OUT=/tmp/census.json python3 backend/scripts/census_boring_rate.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.feed_quality_debug import (  # noqa: E402
    build_feed_quality_debug,
    load_default_ground_truth_items,
)

TOP_N = 20
BORING_CLASSES = ("low_quality", "suppress")


def _read(client: httpx.Client, url: str, params: dict) -> dict:
    """One read, with its own provenance attached. Never raises on a bad read."""
    stamp = datetime.now(timezone.utc).isoformat()
    try:
        resp = client.get(url, params=params, timeout=45)
    except Exception as exc:  # noqa: BLE001 - a failed read IS a sample
        return {"at": stamp, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if resp.status_code != 200:
        return {
            "at": stamp,
            "ok": False,
            "http": resp.status_code,
            "body_head": resp.text[:200],
        }
    payload = resp.json()
    cache = payload.get("cache") or {}
    return {
        "at": stamp,
        "ok": True,
        "http": 200,
        "cache_status": cache.get("status"),
        "degraded_reason": payload.get("degraded_reason"),
        "build_quality": payload.get("build_quality"),
        "payload": payload,
    }


def _classify(payload: dict, ground_truth_items: list[dict]) -> dict:
    items = [i for i in payload.get("items", []) if i.get("type") == "futures"]
    debug = build_feed_quality_debug(
        items, ground_truth_items=ground_truth_items, top_n=TOP_N
    )
    classified = debug["items"]
    window = classified[:TOP_N]
    boring = [c for c in window if c["quality_class"] in BORING_CLASSES]
    # Independence by content. Two reads that produced the same ordered window
    # are one build, whatever `cache.status` said about them.
    fingerprint = hashlib.sha256(
        "|".join(str(c.get("market_id") or c.get("name")) for c in window).encode()
    ).hexdigest()[:16]
    return {
        "futures_returned": len(items),
        "window_fingerprint": fingerprint,
        # THE DENOMINATOR IS THE POINT. `boring_count / window_size`, never
        # `boring_count / 20` — a 3-card page scoring 0 is not a 0% boring rate.
        "window_size": len(window),
        "boring_count": len(boring),
        "short_window": len(window) < TOP_N,
        "boring": [
            {
                "rank": c.get("rank"),
                "name": c.get("name"),
                "quality_class": c.get("quality_class"),
                "reasons": c.get("reasons"),
            }
            for c in boring
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reads", type=int, default=12)
    ap.add_argument(
        "--spacing",
        type=float,
        default=70.0,
        help="seconds between reads; must exceed the feed's cache TTL (60 s)",
    )
    ap.add_argument("--base-url", default="https://api.bainluck.com/api/feed")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    ground_truth_items = load_default_ground_truth_items()

    futures_params = {
        "limit": str(args.limit),
        "include_events": "false",
        "include_futures": "true",
    }
    default_params = {"limit": str(args.limit)}

    samples: list[dict] = []
    default_reads: list[dict] = []

    with httpx.Client() as client:
        for n in range(args.reads):
            if n:
                time.sleep(args.spacing)
            # The DEFAULT feed first — this is the shape a real visitor gets, and
            # its degrade rate is a user-facing number the futures-only probe
            # cannot see.
            d = _read(client, args.base_url, default_params)
            d.pop("payload", None) if not d.get("ok") else None
            if d.get("ok"):
                p = d.pop("payload")
                types: dict[str, int] = {}
                for i in p.get("items", []):
                    types[i.get("type") or "?"] = types.get(i.get("type") or "?", 0) + 1
                d["item_count"] = len(p.get("items", []))
                d["type_counts"] = types
            default_reads.append(d)

            time.sleep(2)

            r = _read(client, args.base_url, futures_params)
            if r.get("ok"):
                r.update(_classify(r.pop("payload"), ground_truth_items))
            samples.append(r)
            print(
                f"[{n + 1}/{args.reads}] futures ok={r.get('ok')} "
                f"cache={r.get('cache_status')} degraded={r.get('degraded_reason')} "
                f"n={r.get('futures_returned')} boring={r.get('boring_count')}"
                f"  |  default ok={d.get('ok')} http={d.get('http')} "
                f"degraded={d.get('degraded_reason')} "
                f"types={d.get('type_counts')}",
                flush=True,
            )

    # ---- aggregate, with every exclusion NAMED rather than silently dropped
    failed = [s for s in samples if not s.get("ok")]
    degraded = [s for s in samples if s.get("ok") and s.get("degraded_reason")]
    short = [s for s in samples if s.get("ok") and s.get("short_window")]

    counted: list[dict] = []
    seen_builds: set[str] = set()
    repeats = 0
    for s in samples:
        if not s.get("ok") or s.get("degraded_reason") or s.get("short_window"):
            continue
        fp = s.get("window_fingerprint")
        if fp in seen_builds:
            repeats += 1
            continue
        seen_builds.add(fp)
        counted.append(s)

    boring_total = sum(s["boring_count"] for s in counted)
    window_total = sum(s["window_size"] for s in counted)

    default_ok = [d for d in default_reads if d.get("ok")]
    default_degraded = [d for d in default_ok if d.get("degraded_reason")]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "reads_attempted": args.reads,
        "spacing_seconds": args.spacing,
        "excluded": {
            "failed_reads": len(failed),
            "degraded_reads": len(degraded),
            "repeat_builds": repeats,
            "short_windows": len(short),
        },
        "counted_reads": len(counted),
        "distinct_builds": len(seen_builds),
        "cache_status_distribution": {
            st: sum(1 for s in samples if s.get("cache_status") == st)
            for st in sorted({s.get("cache_status") for s in samples if s.get("ok")})
        },
        "cards_graded": window_total,
        "boring_cards": boring_total,
        "boring_rate_at_20": (
            None if window_total == 0 else round(boring_total / window_total, 4)
        ),
        "per_read_boring_counts": [s["boring_count"] for s in counted],
        "reads_with_zero_boring": sum(1 for s in counted if s["boring_count"] == 0),
        "distinct_boring_cards": sorted(
            {b["name"] for s in counted for b in s["boring"]}
        ),
        "default_feed": {
            "reads_attempted": len(default_reads),
            "reads_ok": len(default_ok),
            "http_status_distribution": {
                str(d.get("http") or d.get("error")): sum(
                    1 for x in default_reads
                    if (x.get("http") or x.get("error")) == (d.get("http") or d.get("error"))
                )
                for d in default_reads
            },
            "degraded": len(default_degraded),
            "degrade_reasons": sorted(
                {d.get("degraded_reason") for d in default_degraded if d.get("degraded_reason")}
            ),
        },
    }

    print()
    print("=" * 72)
    if window_total == 0:
        # The vacuity refusal, stated out loud. A census with nothing in it is
        # not a clean census.
        print("BORING-RATE@20: NOT MEASURABLE — zero cards graded across all reads.")
        print("This is a FAILED census, not a passing one.")
    else:
        print(
            f"BORING-RATE@20 (aggregate): {boring_total}/{window_total} cards "
            f"= {100 * boring_total / window_total:.2f}% "
            f"over {len(counted)} independent reads"
        )
    print(f"excluded: {summary['excluded']}")
    print(f"default-feed degrade rate: {len(default_degraded)}/{len(default_ok)} "
          f"{summary['default_feed']['degrade_reasons']}")
    if summary["distinct_boring_cards"]:
        print("distinct boring cards:")
        for name in summary["distinct_boring_cards"]:
            print(f"  - {name}")

    out = os.getenv("CENSUS_OUT")
    if out:
        Path(out).write_text(
            json.dumps({"summary": summary, "samples": samples,
                        "default_reads": default_reads}, indent=2)
        )
        print(f"\nwrote {out}")

    return 0 if window_total else 1


if __name__ == "__main__":
    raise SystemExit(main())
