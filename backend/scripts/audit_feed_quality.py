"""Audit Discover feed quality.

Fetches the futures-only feed, classifies top items with the same quality
utility used by the feed route, and reports precision-oriented metrics.

Usage:
    python3 backend/scripts/audit_feed_quality.py
    FEED_AUDIT_URL=http://localhost:8000/api/feed python3 backend/scripts/audit_feed_quality.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.feed_market_quality import (  # noqa: E402
    classify_market_quality,
    has_specific_explanation,
)


def _load_ground_truth_names() -> set[str]:
    names: set[str] = set()
    for rel in (
        "scripts/polymarket_browse_ground_truth.json",
        "scripts/kalshi_ground_truth.json",
    ):
        path = ROOT / rel
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        for item in data:
            if item.get("trending") and item.get("market_name"):
                names.add(item["market_name"].lower().strip())
    return names


def _matches_ground_truth(name: str, ground_truth: set[str]) -> bool:
    lower = name.lower().strip()
    if lower in ground_truth:
        return True
    return any(lower in gt or gt in lower for gt in ground_truth)


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

    ground_truth = _load_ground_truth_names()
    classified: list[dict] = []
    for idx, item in enumerate(items, start=1):
        data = item.get("data") or {}
        outcomes = data.get("top_outcomes") or []
        quality = classify_market_quality(
            market_name=data.get("name"),
            sport_category=data.get("llm_sport_category"),
            outcome_names=[o.get("name") for o in outcomes if o.get("name")],
        )
        hook = data.get("hook_description")
        headline = item.get("headline")
        explanation_ok = has_specific_explanation(
            hook_description=hook,
            headline=headline,
            quality=quality,
        )
        classified.append({
            "rank": idx,
            "score": item.get("score"),
            "name": data.get("name") or "",
            "category": data.get("llm_sport_category") or "?",
            "source": data.get("source") or "?",
            "headline": item.get("headline"),
            "reason": item.get("reason"),
            "hook": bool(hook),
            "explanation_ok": explanation_ok,
            "quality_class": quality.quality_class,
            "family_key": quality.family_key,
            "ladder": quality.is_ladder_or_bucket,
            "reasons": quality.reasons,
            "ground_truth": _matches_ground_truth(data.get("name") or "", ground_truth),
        })

    c20 = classified[:20]
    boring20 = [c for c in c20 if c["quality_class"] in ("low_quality", "suppress")]
    ladder20 = [c for c in c20 if c["ladder"]]
    family_counts = Counter(c["family_key"] for c in c20)
    duplicate_families = {k: v for k, v in family_counts.items() if v > 1}
    explanation_ok = [c for c in c20 if c["explanation_ok"]]
    gt50 = [c for c in classified[:50] if c["ground_truth"]]
    cats = Counter(c["category"] for c in c20)

    print("DISCOVER FEED QUALITY AUDIT")
    print("=" * 72)
    print(f"URL: {base_url}")
    print(f"Items: {len(classified)}")
    print()
    print(f"boring-rate@20:          {len(boring20)}/20")
    print(f"ladder/bucket-rate@20:   {len(ladder20)}/20")
    print(f"duplicate-family-rate@20:{sum(duplicate_families.values())}/20")
    print(f"explanation-coverage@20: {len(explanation_ok)}/20")
    print(f"ground-truth-hit@50:     {len(gt50)}/50")
    print(f"category distribution@20:{dict(cats.most_common())}")
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
            print(f"     why={c['headline'] or c['reason']}")

    if boring20 or duplicate_families:
        print()
        print("LIKELY FIX TARGETS")
        print("-" * 72)
        for c in boring20[:10]:
            print(f"boring #{c['rank']:02d}: {c['name']} ({','.join(c['reasons'])})")
        for family, count in duplicate_families.items():
            print(f"duplicate family x{count}: {family}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
