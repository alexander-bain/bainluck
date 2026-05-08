"""Shared Discover feed quality diagnostics.

Used by both the production audit script and the admin debug endpoint so the
numbers shown in-browser match the CLI output.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.utils.feed_market_quality import (
    classify_market_quality,
    editorial_archetype,
    has_specific_explanation,
)


def load_default_ground_truth_names() -> set[str]:
    """Load local Kalshi/Polymarket ground-truth market names when present."""
    root = Path(__file__).resolve().parents[2]
    names: set[str] = set()
    for rel in (
        "scripts/polymarket_browse_ground_truth.json",
        "scripts/kalshi_ground_truth.json",
    ):
        path = root / rel
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


def matches_ground_truth(name: str, ground_truth: set[str]) -> bool:
    """Return whether a market name matches a curated ground-truth story."""
    lower = name.lower().strip()
    if lower in ground_truth:
        return True
    return any(lower in gt or gt in lower for gt in ground_truth)


def diagnose_feed_items(
    items: list[dict[str, Any]],
    *,
    ground_truth: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build per-card diagnostics for feed items.

    Futures cards get full quality diagnostics. Event cards are included with a
    lightweight sports-story classification so mixed feeds remain readable.
    """
    ground_truth = ground_truth or set()
    diagnosed: list[dict[str, Any]] = []

    for idx, item in enumerate(items, start=1):
        data = item.get("data") or {}
        item_type = item.get("type")
        name = data.get("name") or data.get("title") or ""

        if item_type == "event":
            home = data.get("home_team") or ""
            away = data.get("away_team") or ""
            name = f"{away} at {home}".strip() or name
            category = data.get("sport_name") or data.get("sport") or "sports"
            diagnosed.append(
                {
                    "rank": idx,
                    "type": item_type,
                    "id": data.get("id"),
                    "score": item.get("score"),
                    "name": name,
                    "category": category,
                    "archetype": "sports_story",
                    "source": "event",
                    "headline": item.get("headline"),
                    "reason": item.get("reason"),
                    "hook": False,
                    "image": bool(data.get("home_team_data") or data.get("away_team_data")),
                    "explanation_ok": bool(item.get("headline") or item.get("reason")),
                    "quality_class": "normal",
                    "family_key": f"event:{data.get('id') or name.lower()}",
                    "story_key": None,
                    "ladder": False,
                    "reasons": [],
                    "ground_truth": False,
                }
            )
            continue

        outcomes = data.get("top_outcomes") or []
        category = data.get("llm_sport_category") or data.get("sport_name") or data.get("sport") or "?"
        quality = classify_market_quality(
            market_name=name,
            sport_category=category,
            outcome_names=[o.get("name") for o in outcomes if o.get("name")],
        )
        hook = data.get("hook_description")
        headline = item.get("headline")
        explanation_ok = has_specific_explanation(
            hook_description=hook,
            headline=headline,
            quality=quality,
        )

        diagnosed.append(
            {
                "rank": idx,
                "type": item_type,
                "id": data.get("id"),
                "score": item.get("score"),
                "name": name,
                "category": category,
                "archetype": editorial_archetype(name, category),
                "source": data.get("source") or "?",
                "headline": headline,
                "reason": item.get("reason"),
                "hook": bool(hook),
                "image": bool(data.get("image_url")),
                "explanation_ok": explanation_ok,
                "quality_class": quality.quality_class,
                "family_key": quality.family_key,
                "story_key": quality.story_key,
                "ladder": quality.is_ladder_or_bucket,
                "reasons": quality.reasons,
                "ground_truth": matches_ground_truth(name, ground_truth),
            }
        )

    return diagnosed


def summarize_feed_diagnostics(
    diagnosed: list[dict[str, Any]],
    *,
    top_n: int = 20,
) -> dict[str, Any]:
    """Calculate the headline Discover quality metrics for diagnosed items."""
    top = diagnosed[:top_n]
    top10 = diagnosed[:10]
    boring = [c for c in top if c["quality_class"] in ("low_quality", "suppress")]
    ladder = [c for c in top if c["ladder"]]
    family_counts = Counter(c["family_key"] for c in top)
    duplicate_families = {k: v for k, v in family_counts.items() if v > 1}
    explanation_ok = [c for c in top if c["explanation_ok"]]
    ground_truth_50 = [c for c in diagnosed[:50] if c["ground_truth"]]
    categories = Counter(c["category"] for c in top)
    archetypes = Counter(c["archetype"] for c in top)

    positive_targets = {
        "world_event": any(c["archetype"] == "world_event" for c in top),
        "tech_frontier": any(c["archetype"] == "tech_frontier" for c in top),
        "macro_signal": any(c["archetype"] == "macro_signal" for c in top),
        "culture_moment": any(c["archetype"] == "culture_moment" for c in top),
        "health_weather_risk": any(c["archetype"] == "health_weather_risk" for c in top),
        "sports_story": any(c["archetype"] == "sports_story" for c in top),
    }
    top10_non_politics = [
        c for c in top10
        if c["category"] not in {"politics", "geopolitics"}
    ]
    top10_fun = [
        c for c in top10
        if c["archetype"] in {"culture_moment", "weird_news", "sports_story"}
    ]
    strict_targets = {
        "top10_non_politics_geopolitics>=4": len(top10_non_politics) >= 4,
        "top10_has_fun_item": bool(top10_fun),
        "top20_world_event<=4": archetypes.get("world_event", 0) <= 4,
        "top20_has_weird_news": archetypes.get("weird_news", 0) >= 1,
        "top20_max_category<=5": max(categories.values(), default=0) <= 5,
    }

    return {
        "items": len(diagnosed),
        "top_n": top_n,
        "boring_count": len(boring),
        "ladder_count": len(ladder),
        "duplicate_family_count": sum(duplicate_families.values()),
        "duplicate_families": duplicate_families,
        "explanation_ok_count": len(explanation_ok),
        "ground_truth_hit_count_50": len(ground_truth_50),
        "positive_archetype_hits": sum(1 for hit in positive_targets.values() if hit),
        "positive_targets_total": len(positive_targets),
        "strict_variety_hits": sum(1 for hit in strict_targets.values() if hit),
        "strict_targets_total": len(strict_targets),
        "category_spread": len(categories),
        "max_category_count": max(categories.values(), default=0),
        "category_distribution": dict(categories.most_common()),
        "archetype_distribution": dict(archetypes.most_common()),
        "positive_targets": positive_targets,
        "strict_targets": strict_targets,
    }


def build_feed_quality_debug(
    items: list[dict[str, Any]],
    *,
    ground_truth: set[str] | None = None,
    top_n: int = 20,
) -> dict[str, Any]:
    """Return summary and per-item diagnostics for a feed response."""
    diagnosed = diagnose_feed_items(items, ground_truth=ground_truth)
    return {
        "summary": summarize_feed_diagnostics(diagnosed, top_n=top_n),
        "items": diagnosed,
    }
