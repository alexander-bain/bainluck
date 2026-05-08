"""Audit Discover feed quality.

Fetches the futures-only feed, classifies top items with the same quality
utility used by the feed route, and reports precision-oriented metrics.

Usage:
    python3 backend/scripts/audit_feed_quality.py
    FEED_AUDIT_URL=http://localhost:8000/api/feed python3 backend/scripts/audit_feed_quality.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.feed_quality_debug import (  # noqa: E402
    build_feed_quality_debug,
    load_default_ground_truth_items,
)


def main() -> int:
    base_url = os.getenv("FEED_AUDIT_URL", "https://api.bainluck.com/api/feed")
    limit = int(os.getenv("FEED_AUDIT_LIMIT", "50"))
    params = {
        "limit": str(limit),
        "include_events": "false",
        "include_futures": "true",
    }

    resp = httpx.get(base_url, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    items = [i for i in payload.get("items", []) if i.get("type") == "futures"]

    ground_truth_items = load_default_ground_truth_items()
    debug = build_feed_quality_debug(
        items,
        ground_truth_items=ground_truth_items,
        top_n=20,
    )
    classified = debug["items"]
    summary = debug["summary"]
    boring20 = [c for c in classified[:20] if c["quality_class"] in ("low_quality", "suppress")]
    duplicate_families = summary["duplicate_families"]

    print("DISCOVER FEED QUALITY AUDIT")
    print("=" * 72)
    print(f"URL: {base_url}")
    print(f"Items: {len(classified)}")
    print()
    print(f"boring-rate@20:          {summary['boring_count']}/20")
    print(f"ladder/bucket-rate@20:   {summary['ladder_count']}/20")
    print(f"duplicate-family-rate@20:{summary['duplicate_family_count']}/20")
    print(f"explanation-coverage@20: {summary['explanation_ok_count']}/20")
    print(f"ground-truth-hit@50:     {summary['ground_truth_hit_count_50']}/50")
    print(f"positive-archetypes@20:  {summary['positive_archetype_hits']}/{summary['positive_targets_total']}")
    print(f"strict-variety@20:       {summary['strict_variety_hits']}/{summary['strict_targets_total']}")
    print(f"category-spread@20:      {summary['category_spread']} categories, max={summary['max_category_count']}")
    print(f"category distribution@20:{summary['category_distribution']}")
    print(f"archetype distribution@20:{summary['archetype_distribution']}")
    print(f"positive targets@20:     {summary['positive_targets']}")
    print(f"strict targets@20:       {summary['strict_targets']}")
    print()

    print("TOP 50")
    print("-" * 72)
    for c in classified[:50]:
        flags = []
        if c["quality_class"] != "normal":
            flags.append(c["quality_class"])
        if c["ladder"]:
            flags.append("ladder")
        if c["ground_truth"]:
            flags.append("gt")
        flag_text = f" [{' '.join(flags)}]" if flags else ""
        print(
            f"#{c['rank']:02d} score={c['score']:>3} "
            f"[{c['category'][:12]:12s}] {c['name'][:84]}{flag_text}"
        )
        if c["reasons"]:
            print(f"     reasons={','.join(c['reasons'][:6])}")
        if c["headline"] or c["reason"]:
            print(f"     why={c['headline'] or c['reason']} ({c['archetype']})")

    if boring20 or duplicate_families:
        print()
        print("LIKELY FIX TARGETS")
        print("-" * 72)
        for c in boring20[:10]:
            print(f"boring #{c['rank']:02d}: {c['name']} ({','.join(c['reasons'])})")
        for family, count in duplicate_families.items():
            print(f"duplicate family x{count}: {family}")

    missing = debug.get("missing_ground_truth") or []
    if missing:
        missing_summary = debug.get("missing_ground_truth_summary") or {}
        print()
        print("MISSING GROUND TRUTH")
        print("-" * 72)
        print(f"buckets: {missing_summary.get('bucket_counts', {})}")
        for item in missing[:20]:
            print(
                f"[{item['triage_bucket']}] [{item['source']}:{item['category']}] "
                f"{item['name'][:84]} ({item['archetype']}, {item['quality_class']})"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
