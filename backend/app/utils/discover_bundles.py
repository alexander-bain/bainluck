"""Server-side composition for Discover comparison bundles."""

from __future__ import annotations

import re
from typing import Any

from app.utils.feed_market_quality import _story_key as compute_story_key

PUBLIC_COMPARISON_BUNDLE_THEMES = {
    "ipo_valuation",
    "commodity_ranges",
    "rotten_tomatoes_scores",
    "weather_distributions",
}

# Theme-grouping Phase 1, slice 1 (geopolitics archetype). These are the
# existing geopolitics story_keys (see feed_market_quality._story_key); a feed
# that scatters N same-conflict markets across separate cards is folded into ONE
# expandable theme bundle instead. Clean display labels per key.
GEOPOLITICS_STORY_KEYS = {
    "story:middle_east_conflict": "Middle East",
    "story:russia_ukraine": "Russia–Ukraine",
}

_THEME_TITLES = {
    "ipo_valuation": "IPO valuation ranges",
    "commodity_ranges": "Commodity price ranges",
    "rotten_tomatoes_scores": "Rotten Tomatoes score ranges",
    "weather_distributions": "Weather ranges",
}

_THEME_REASONS = {
    "ipo_valuation": "Compare valuation range probabilities across IPO markets.",
    "commodity_ranges": "Compare price range probabilities across commodity markets.",
    "rotten_tomatoes_scores": "Compare score range probabilities across entertainment markets.",
    "weather_distributions": "Compare forecast range probabilities across weather markets.",
}


def _futures_data(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("type") != "futures":
        return {}
    data = item.get("data")
    return data if isinstance(data, dict) else {}


def _discover_card(data: dict[str, Any]) -> dict[str, Any]:
    card = data.get("discover_card")
    return card if isinstance(card, dict) else {}


def _theme_for_item(item: dict[str, Any]) -> str | None:
    data = _futures_data(item)
    card = _discover_card(data)
    theme = card.get("comparison_theme")
    if theme not in PUBLIC_COMPARISON_BUNDLE_THEMES:
        return None
    if not card.get("bundle_candidate"):
        return None
    if card.get("suggested_format") != "threshold_heatmap":
        return None
    if card.get("public_source_disagreement"):
        return None
    points = card.get("threshold_points") or []
    if len(points) < 2:
        return None
    return str(theme)


def _market_entity_name(name: str, theme: str) -> str:
    compact = re.sub(r"\s+", " ", name or "").strip()
    compact = compact.rstrip("?")
    if theme == "ipo_valuation":
        compact = re.sub(r"\bClosing Market Cap\b", "", compact, flags=re.I)
        compact = re.sub(r"\bIPO\b.*$", "IPO", compact, flags=re.I)
    elif theme == "commodity_ranges":
        compact = re.sub(r"^Will\s+", "", compact, flags=re.I)
        compact = re.sub(r"\b(hit|be|close|settle|end)\b.*$", "", compact, flags=re.I)
    elif theme == "rotten_tomatoes_scores":
        compact = re.sub(r"\bRotten Tomatoes\b", "RT", compact, flags=re.I)
        compact = re.sub(r"\bscore\b", "", compact, flags=re.I)
    elif theme == "weather_distributions":
        compact = re.sub(r"\bon .*$", "", compact, flags=re.I)
    return compact.strip() or name


def _item_id(item: dict[str, Any]) -> str:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    return f"{item.get('type')}:{data.get('id')}"


def _bundle_id(theme: str, items: list[dict[str, Any]]) -> str:
    ids = "-".join(str((_futures_data(item)).get("id")) for item in items)
    return f"comparison:{theme}:{ids}"


def _bundle_subtitle(theme: str, count: int) -> str:
    if theme == "ipo_valuation":
        return f"{count} IPO markets compared by valuation range"
    if theme == "commodity_ranges":
        return f"{count} commodity markets compared by price range"
    if theme == "rotten_tomatoes_scores":
        return f"{count} score markets compared by threshold"
    if theme == "weather_distributions":
        return f"{count} weather markets compared by range"
    return f"{count} markets compared"


def _public_member_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if not key.startswith("_")
        and key
        not in {
            "personalization_trace",
            "_review_decision",
            "_review_decision_scope",
            "_review_decision_scope_key",
            "_review_decision_penalty",
        }
    }


def _make_bundle_item(theme: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    score = max(float(item.get("score") or 0) for item in items)
    sort_time = max(float(item.get("_sort_time") or 0) for item in items)
    title = _THEME_TITLES.get(theme, "Comparable market ranges")
    member_ids = [(_futures_data(item)).get("id") for item in items]
    entities = [
        _market_entity_name(str((_futures_data(item)).get("name") or ""), theme)
        for item in items
    ]
    return {
        "type": "bundle",
        "score": score,
        "reason": _bundle_subtitle(theme, len(items)),
        "headline": title,
        "context_summary": _THEME_REASONS.get(theme),
        "data": {
            "id": _bundle_id(theme, items),
            "title": title,
            "kind": "comparison",
            "comparison_theme": theme,
            "item_count": len(items),
            "member_ids": member_ids,
            "items": [_public_member_item(item) for item in items],
            "entities": entities,
            "debug_bundles": {
                "grouped_by": "discover_card.comparison_theme",
                "theme": theme,
                "member_ids": member_ids,
                "member_names": [(_futures_data(item)).get("name") for item in items],
                "public_source_disagreement": False,
            },
        },
        "_sort_time": sort_time,
    }


def assemble_discover_comparison_bundles(
    items: list[dict[str, Any]],
    *,
    min_items: int = 2,
    max_items_per_bundle: int = 4,
    max_bundles_per_theme: int = 1,
) -> list[dict[str, Any]]:
    """Replace safe related futures with explicit comparison bundle feed items.

    Bundles are intentionally narrow: they require deterministic card metadata,
    at least two threshold points per represented market, and a public allowlisted
    comparison theme. Source disagreement remains QA-only and is never a public
    grouping theme.
    """

    groups: dict[str, list[dict[str, Any]]] = {}
    seen_entities: dict[str, set[str]] = {}
    for item in items:
        theme = _theme_for_item(item)
        if theme is None:
            continue
        name = str(_futures_data(item).get("name") or "")
        entity = _market_entity_name(name, theme).lower()
        if not entity:
            continue
        seen_entities.setdefault(theme, set())
        if entity in seen_entities[theme]:
            continue
        seen_entities[theme].add(entity)
        groups.setdefault(theme, []).append(item)

    bundle_items_by_theme: dict[str, list[dict[str, Any]]] = {}
    represented_ids: set[str] = set()
    for theme, candidates in groups.items():
        if len(candidates) < min_items:
            continue
        top_candidates = candidates[:max_items_per_bundle]
        if len(top_candidates) < min_items:
            continue
        bundles = [_make_bundle_item(theme, top_candidates)]
        bundle_items_by_theme[theme] = bundles[:max_bundles_per_theme]
        represented_ids.update(_item_id(item) for item in top_candidates)

    if not represented_ids:
        return items

    emitted_themes: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        item_id = _item_id(item)
        if item_id not in represented_ids:
            output.append(item)
            continue
        theme = _theme_for_item(item)
        if theme is None or theme in emitted_themes:
            continue
        emitted_themes.add(theme)
        output.extend(bundle_items_by_theme.get(theme, []))

    return output


# ── Theme bundles (geopolitics archetype — Phase 1, slice 1) ──────────────────


def _geopolitics_story_key(item: dict[str, Any]) -> str | None:
    """Story key for a feed item if it belongs to a geopolitics cluster.

    Recomputed from the public market name/category (not the internal
    ``_quality_story_key``, which is popped later in the serving path) so this
    stays decoupled from feed-pipeline field lifecycle.
    """
    data = _futures_data(item)
    if not data:
        return None
    name = str(data.get("name") or "")
    if not name:
        return None
    category = data.get("llm_sport_category") or data.get("sport") or ""
    key = compute_story_key(name, str(category))
    if key in GEOPOLITICS_STORY_KEYS:
        return key
    return None


def _theme_bundle_id(story_key: str, items: list[dict[str, Any]]) -> str:
    ids = "-".join(str(_futures_data(item).get("id")) for item in items)
    return f"theme:{story_key}:{ids}"


def _make_theme_bundle_item(
    story_key: str, items: list[dict[str, Any]]
) -> dict[str, Any]:
    # Members ranked by feed score (most feed-worthy leads the mini-ranked-peek);
    # the bundle competes for ONE slot scored by its best member.
    ranked = sorted(items, key=lambda it: float(it.get("score") or 0), reverse=True)
    score = max(float(item.get("score") or 0) for item in ranked)
    sort_time = max(float(item.get("_sort_time") or 0) for item in ranked)
    label = GEOPOLITICS_STORY_KEYS[story_key]
    member_ids = [_futures_data(item).get("id") for item in ranked]
    return {
        "type": "bundle",
        "score": score,
        "reason": f"{len(ranked)} related markets",
        "headline": label,
        "data": {
            "id": _theme_bundle_id(story_key, ranked),
            "title": label,
            "kind": "theme",
            "story_key": story_key,
            "item_count": len(ranked),
            "member_ids": member_ids,
            "items": [_public_member_item(item) for item in ranked],
            "debug_bundles": {
                "grouped_by": "story_key",
                "story_key": story_key,
                "member_ids": member_ids,
                "member_names": [
                    _futures_data(item).get("name") for item in ranked
                ],
            },
        },
        "_sort_time": sort_time,
    }


def assemble_geopolitics_theme_bundles(
    items: list[dict[str, Any]],
    *,
    min_items: int = 2,
    max_items_per_bundle: int = 6,
) -> list[dict[str, Any]]:
    """Cap-and-FOLD geopolitics story clusters into one expandable theme bundle.

    Replaces the scatter (N separate same-conflict cards) with ONE ``type:bundle``
    item (``kind="theme"``) that carries the members ranked for a mini-ranked-peek
    and full expansion. The bundle takes a single feed slot scored by its best
    member. A cluster with fewer than ``min_items`` members is left untouched.

    Geopolitics-only this slice. Other archetypes (awards, prop breakdown, …) are
    separate follow-on slices. Orthogonal to the comparison-theme bundler.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        story_key = _geopolitics_story_key(item)
        if story_key is None:
            continue
        groups.setdefault(story_key, []).append(item)

    bundle_by_story: dict[str, dict[str, Any]] = {}
    represented_ids: set[str] = set()
    for story_key, members in groups.items():
        if len(members) < min_items:
            continue
        chosen = members[:max_items_per_bundle]
        if len(chosen) < min_items:
            continue
        bundle_by_story[story_key] = _make_theme_bundle_item(story_key, chosen)
        represented_ids.update(_item_id(item) for item in chosen)

    if not represented_ids:
        return items

    emitted: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        if _item_id(item) not in represented_ids:
            output.append(item)
            continue
        story_key = _geopolitics_story_key(item)
        if story_key is None or story_key in emitted:
            continue
        emitted.add(story_key)
        output.append(bundle_by_story[story_key])

    return output
