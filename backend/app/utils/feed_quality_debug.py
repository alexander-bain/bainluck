"""Shared Discover feed quality diagnostics.

Used by both the production audit script and the admin debug endpoint so the
numbers shown in-browser match the CLI output.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.feed_market_quality import (
    classify_market_quality,
    editorial_archetype,
    has_specific_explanation,
)

_NUMBER_RE = re.compile(r"[-+]?\$?\d+(?:,\d{3})*(?:\.\d+)?%?")
_GAME_MARKET_RE = re.compile(
    r"("
    r"\bvs\.?\b|"
    r"\bspread:|"
    r"\bo/u\b|"
    r"\bover/under\b|"
    r"\bmoneyline\b|"
    r"\bbo3\b|"
    r"\bmap \d\b"
    r")",
    re.IGNORECASE,
)
_HIGH_VALUE_ARCHETYPES = {
    "world_event",
    "breaking_news",
    "tech_frontier",
    "macro_signal",
    "culture_moment",
    "health_weather_risk",
    "sports_story",
    "sports_drama",
    "company_drama",
    "big_name",
    "absurd_but_real",
}

_FUN_ARCHETYPES = {
    "culture_moment",
    "weird_news",
    "absurd_but_real",
    "big_name",
    "sports_drama",
}

_STALE_ROOT_CAUSES = {
    "closed": {
        "code": "closed_market",
        "label": "Market is closed or resolved",
        "recommended_action": "No ranking fix; remove or settle the stale market source row.",
    },
    "not_open": {
        "code": "market_not_open",
        "label": "Market is no longer open",
        "recommended_action": "No ranking fix; verify source status sync if this still appears in Discover.",
    },
    "past_resolution": {
        "code": "past_resolution_date",
        "label": "Resolution date is in the past",
        "recommended_action": "Check settlement/backfill tasks if the source still marks this market open.",
    },
    "stale_updated_at": {
        "code": "no_recent_market_update",
        "label": "No recent market update",
        "recommended_action": "Check source polling and live-price refresh for this market.",
    },
    "stale_no_movement": {
        "code": "stale_without_movement",
        "label": "No recent price movement",
        "recommended_action": "Keep suppressed unless this market has strong editorial value despite low movement.",
    },
    "all_outcomes_settled": {
        "code": "settled_outcomes",
        "label": "All outcomes look settled",
        "recommended_action": "Check settlement/backfill tasks if the exchange has not formally closed it.",
    },
    "effectively_resolved": {
        "code": "effectively_resolved",
        "label": "Leader probability is effectively resolved",
        "recommended_action": "Keep suppressed unless there is fresh reversal movement.",
    },
    "soft_settled_binary": {
        "code": "soft_settled_binary",
        "label": "Binary sports market appears decided",
        "recommended_action": "Check whether the sports market should be settled or excluded from Discover.",
    },
    "completed_old": {
        "code": "completed_event",
        "label": "Event completed too long ago",
        "recommended_action": "Check event status freshness if this completed game still appears in Discover.",
    },
}


def stale_root_cause_for_reason(reason: str | None) -> dict[str, str] | None:
    """Return a stable admin-facing root-cause label for a stale-card reason."""
    if not reason:
        return None
    cause = _STALE_ROOT_CAUSES.get(reason)
    if cause:
        return {"reason": reason, **cause}
    return {
        "reason": reason,
        "code": "unknown_stale_reason",
        "label": "Unknown stale-card reason",
        "recommended_action": "Inspect source status, resolution date, and refresh timestamps.",
    }


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def diagnose_stale_card_root_cause(
    item: dict[str, Any],
    *,
    now: datetime | None = None,
    stale_no_movement_days: float = 2,
) -> dict[str, str] | None:
    """Explain obvious stale-card causes from fields already present in debug payloads."""
    now = now or datetime.now(timezone.utc)
    data = item.get("data") or {}
    item_type = item.get("type")

    if item_type == "futures":
        status = data.get("status")
        if status in ("closed", "resolved"):
            return stale_root_cause_for_reason("closed")
        if status and status != "open":
            return stale_root_cause_for_reason("not_open")

        resolution_date = _parse_datetime(data.get("resolution_date"))
        if resolution_date and resolution_date < now:
            return stale_root_cause_for_reason("past_resolution")

        updated_at = _parse_datetime(data.get("updated_at"))
        if updated_at and (now - updated_at).total_seconds() / 86400 > stale_no_movement_days:
            return stale_root_cause_for_reason("stale_updated_at")

    if item_type == "event":
        status = data.get("status")
        commence_time = _parse_datetime(data.get("commence_time"))
        if (
            status in ("completed", "closed")
            and commence_time
            and (now - commence_time).total_seconds() > 8 * 3600
        ):
            return stale_root_cause_for_reason("completed_old")

    return None


def _normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _display_context_text(item: dict[str, Any]) -> str:
    data = item.get("data") or {}
    return (
        item.get("context_summary")
        or item.get("headline")
        or item.get("reason")
        or data.get("hook_description")
        or ""
    ).strip()


def _snippet_quality_issues(name: str, context: str) -> list[str]:
    """Flag feed snippets that are present but weak on-card copy."""
    if not context:
        return ["missing"]

    issues: list[str] = []
    compact = " ".join(context.split())
    if len(compact) > 180:
        issues.append("too_long")

    name_tokens = _normalized_words(name)
    context_tokens = _normalized_words(compact)
    if name_tokens and context_tokens:
        prefix_len = min(len(name_tokens), 8)
        if context_tokens[:prefix_len] == name_tokens[:prefix_len]:
            issues.append("repeats_title")

    lower = compact.lower()
    if re.search(r"\bresolving (soon|this month)\b", lower) and not re.search(r"\d", compact):
        issues.append("generic_resolution")
    if len(context_tokens) > 18 and not re.search(r"\d|up|down|new favorite|tracked by|leads at|movement|source", lower):
        issues.append("no_concrete_signal")
    return issues


def load_default_ground_truth_items() -> list[dict[str, Any]]:
    """Load local curated Kalshi/Polymarket examples when present."""
    root = Path(__file__).resolve().parents[2]
    items: list[dict[str, Any]] = []
    for source, rel in (
        ("polymarket", "scripts/polymarket_browse_ground_truth.json"),
        ("kalshi", "scripts/kalshi_ground_truth.json"),
    ):
        path = root / rel
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        for item in data:
            name = (item.get("market_name") or "").strip()
            if not item.get("trending") or not name:
                continue
            items.append({
                "source": source,
                "category": item.get("category") or "?",
                "name": name,
                "probability": item.get("probability"),
                "sub_page": item.get("sub_page"),
            })
    return items


def load_default_ground_truth_names() -> set[str]:
    """Load local Kalshi/Polymarket ground-truth market names when present."""
    return {_normalize_match_name(item["name"]) for item in load_default_ground_truth_items()}


def matches_ground_truth(name: str, ground_truth: set[str]) -> bool:
    """Return whether a market name matches a curated ground-truth story."""
    lower = _normalize_match_name(name)
    if lower in ground_truth:
        return True
    return any(_names_match(lower, gt) for gt in ground_truth)


def _names_match(a: str, b: str) -> bool:
    left = _normalize_match_name(a)
    right = _normalize_match_name(b)
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    if _equivalent_recession_story(left, right):
        return True

    stopwords = {
        "will", "the", "to", "of", "in", "on", "by", "at", "for", "and",
        "or", "win", "wins", "winner", "advance", "make", "reach",
    }
    left_tokens = {token for token in left.split() if token not in stopwords}
    right_tokens = {token for token in right.split() if token not in stopwords}
    if len(left_tokens) < 3 or len(right_tokens) < 3:
        return False
    overlap = left_tokens & right_tokens
    return len(overlap) >= 3 and len(overlap) / min(len(left_tokens), len(right_tokens)) >= 0.6


def _equivalent_recession_story(left: str, right: str) -> bool:
    """Treat common recession phrasings as the same audit story."""
    if "recession" not in left or "recession" not in right:
        return False
    current_year_terms = {"2026", "this year", "end of 2026"}
    return any(term in left for term in current_year_terms) and any(
        term in right for term in current_year_terms
    )


def _normalize_match_name(name: str) -> str:
    """Normalize superficial punctuation differences for ground-truth matching."""
    compact_initials = re.sub(r"\b([a-z])\.([a-z])\.", r"\1\2", name.lower())
    return " ".join(re.findall(r"[a-z0-9]+", compact_initials))


def _ground_truth_probably_resolved(probability: str | None) -> bool:
    if not probability:
        return False
    vals: list[float] = []
    for match in _NUMBER_RE.findall(probability):
        cleaned = match.replace("$", "").replace(",", "").replace("%", "")
        try:
            vals.append(float(cleaned))
        except ValueError:
            continue
    return len(vals) >= 2 and all(v <= 5 or v >= 95 for v in vals)


def _triage_missing_ground_truth(
    *,
    name: str,
    quality_class: str,
    archetype: str,
    story_key: str | None,
    feed_story_keys: set[str],
    feed_archetypes: set[str],
) -> tuple[str, str]:
    """Classify why a curated item is missing from the current feed page."""
    if _GAME_MARKET_RE.search(name):
        return (
            "game_market_noise",
            "Ignore for Discover ranking unless this belongs on an event detail page or game-market module.",
        )

    if story_key and story_key in feed_story_keys:
        return (
            "already_represented_by_sibling_story",
            "No immediate ranking fix; consider better cross-source/story grouping if this exact variant matters.",
        )

    if quality_class == "low_quality":
        return (
            "quality_filter_too_harsh",
            "Review the quality classifier if this item is genuinely editorial despite bucket/metric signals.",
        )

    if quality_class == "compelling" or archetype in _HIGH_VALUE_ARCHETYPES:
        return (
            "candidate_recall_gap",
            "Trace whether this market enters the feed candidate pools; if not, add a targeted pool or source mapping.",
        )

    if archetype in feed_archetypes:
        return (
            "ranking_too_low",
            "Likely present in the broader market universe but loses to stronger same-texture cards; tune scoring only if this class should rise.",
        )

    return (
        "ranking_too_low",
        "Inspect score inputs and category mapping before adding a new pool.",
    )


def find_missing_ground_truth_items(
    diagnosed: list[dict[str, Any]],
    ground_truth_items: list[dict[str, Any]],
    *,
    limit: int = 80,
) -> list[dict[str, Any]]:
    """Find curated examples that are not present in the diagnosed feed page."""
    feed_names = [item.get("name") or "" for item in diagnosed]
    feed_story_keys = {
        item["story_key"] for item in diagnosed
        if item.get("story_key")
    }
    feed_archetypes = {
        item["archetype"] for item in diagnosed
        if item.get("archetype")
    }
    seen: set[str] = set()
    missing: list[dict[str, Any]] = []

    for item in ground_truth_items:
        name = (item.get("name") or "").strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        if _ground_truth_probably_resolved(item.get("probability")):
            continue
        if any(_names_match(name, feed_name) for feed_name in feed_names):
            continue

        quality = classify_market_quality(
            market_name=name,
            sport_category=item.get("category"),
        )
        if quality.quality_class == "suppress":
            continue
        archetype = editorial_archetype(name, item.get("category"))
        triage_bucket, recommended_action = _triage_missing_ground_truth(
            name=name,
            quality_class=quality.quality_class,
            archetype=archetype,
            story_key=quality.story_key,
            feed_story_keys=feed_story_keys,
            feed_archetypes=feed_archetypes,
        )

        missing.append({
            "name": name,
            "source": item.get("source") or "?",
            "category": item.get("category") or "?",
            "probability": item.get("probability"),
            "email_subject": item.get("email_subject"),
            "hook": item.get("hook"),
            "interestingness": item.get("interestingness"),
            "timeliness": item.get("timeliness"),
            "shareability": item.get("shareability"),
            "quality_class": quality.quality_class,
            "archetype": archetype,
            "reasons": quality.reasons,
            "family_key": quality.family_key,
            "story_key": quality.story_key,
            "triage_bucket": triage_bucket,
            "recommended_action": recommended_action,
        })
        if len(missing) >= limit:
            break

    return missing


def summarize_missing_ground_truth_db_trace(
    missing_item: dict[str, Any],
    matches: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Explain whether a missing curated story exists in stored markets."""
    now = now or datetime.now(timezone.utc)
    if not matches:
        return {
            "trace_status": "no_db_match",
            "trace_summary": "No similar FuturesMarket row found by name search.",
            "recommended_action": "Check ingestion/source naming before tuning ranking.",
            "matches": [],
        }

    summarized_matches: list[dict[str, Any]] = []
    eligible_matches: list[dict[str, Any]] = []
    blocked_reasons: Counter[str] = Counter()

    for match in matches:
        reasons: list[str] = []
        name = match.get("name") or ""
        resolution = match.get("resolution_date")
        if isinstance(resolution, str):
            try:
                resolution = datetime.fromisoformat(resolution.replace("Z", "+00:00"))
            except ValueError:
                resolution = None
        if resolution and resolution.tzinfo is None:
            resolution = resolution.replace(tzinfo=timezone.utc)

        if match.get("status") != "open":
            reasons.append("not_open")
        if match.get("event_id") is not None:
            reasons.append("event_linked_game_market")
        if resolution and resolution < now:
            reasons.append("past_resolution")
        if re.search(r"\bvs\.?\b", name, re.IGNORECASE):
            reasons.append("game_name_filtered")

        summarized = {
            "id": match.get("id"),
            "name": name,
            "source": match.get("source"),
            "status": match.get("status"),
            "category": match.get("llm_sport_category"),
            "market_tier": match.get("market_tier"),
            "volume_24h": match.get("volume_24h"),
            "resolution_date": match.get("resolution_date"),
            "has_hook": bool(match.get("hook_description")),
            "has_image": bool(match.get("image_url")),
            "blocked_reasons": reasons,
        }
        summarized_matches.append(summarized)

        if reasons:
            blocked_reasons.update(reasons)
        else:
            eligible_matches.append(summarized)

    if eligible_matches:
        return {
            "trace_status": "eligible_but_not_top_50",
            "trace_summary": "A similar open market exists and appears feed-eligible, but did not rank into this diagnostic page.",
            "recommended_action": "Inspect score inputs, canonical deduping, and candidate-pool ordering for the matched market.",
            "matches": summarized_matches,
        }

    top_reason = blocked_reasons.most_common(1)[0][0] if blocked_reasons else "unknown_blocker"
    action_by_reason = {
        "not_open": "No ranking fix; source marks the market non-open.",
        "event_linked_game_market": "No Discover ranking fix; this belongs in game/event market surfaces.",
        "past_resolution": "No ranking fix; stale/resolved market should stay out of Discover.",
        "game_name_filtered": "No Discover ranking fix unless game-market cards become a deliberate feed format.",
    }
    return {
        "trace_status": f"blocked:{top_reason}",
        "trace_summary": f"Similar market found, but blocked by {top_reason}.",
        "recommended_action": action_by_reason.get(top_reason, "Inspect the matched market eligibility flags."),
        "matches": summarized_matches,
    }


def diagnose_feed_items(
    items: list[dict[str, Any]],
    *,
    ground_truth: set[str] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Build per-card diagnostics for feed items.

    Futures cards get full quality diagnostics. Event cards are included with a
    lightweight sports-story classification so mixed feeds remain readable.
    """
    ground_truth = ground_truth or set()
    now = now or datetime.now(timezone.utc)
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
            context = _display_context_text(item)
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
                    "context": context,
                    "snippet_issues": _snippet_quality_issues(name, context),
                    "hook": False,
                    "image": bool(data.get("home_team_data") or data.get("away_team_data")),
                    "explanation_ok": bool(item.get("headline") or item.get("reason")),
                    "quality_class": "normal",
                    "family_key": f"event:{data.get('id') or name.lower()}",
                    "story_key": None,
                    "ladder": False,
                    "reasons": [],
                    "stale_root_cause": diagnose_stale_card_root_cause(item, now=now),
                    "ground_truth": False,
                    "personalization_trace": item.get("personalization_trace"),
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
        context = _display_context_text(item)
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
                "context": context,
                "snippet_issues": _snippet_quality_issues(name, context),
                "hook": bool(hook),
                "image": bool(data.get("image_url")),
                "explanation_ok": explanation_ok,
                "quality_class": quality.quality_class,
                "family_key": quality.family_key,
                "story_key": quality.story_key,
                "ladder": quality.is_ladder_or_bucket,
                "reasons": quality.reasons,
                "stale_root_cause": diagnose_stale_card_root_cause(item, now=now),
                "ground_truth": matches_ground_truth(name, ground_truth),
                "personalization_trace": item.get("personalization_trace"),
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
    snippet_issues = Counter(
        issue
        for c in top
        for issue in c.get("snippet_issues", [])
        if issue != "missing"
    )
    snippet_issue_cards = [
        c for c in top
        if any(issue != "missing" for issue in c.get("snippet_issues", []))
    ]

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
        if c["archetype"] in _FUN_ARCHETYPES
    ]
    strict_targets = {
        "top10_non_politics_geopolitics>=4": len(top10_non_politics) >= 4,
        "top10_has_fun_item": bool(top10_fun),
        "top20_world_event<=4": archetypes.get("world_event", 0) <= 4,
        "top20_has_weird_or_absurd": (
            archetypes.get("weird_news", 0) + archetypes.get("absurd_but_real", 0)
        ) >= 1,
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
        "snippet_issue_count": len(snippet_issue_cards),
        "snippet_issue_distribution": dict(snippet_issues.most_common()),
        "positive_targets": positive_targets,
        "strict_targets": strict_targets,
        "fun_market_presence_10": bool(top10_fun),
    }


def build_feed_quality_debug(
    items: list[dict[str, Any]],
    *,
    ground_truth: set[str] | None = None,
    ground_truth_items: list[dict[str, Any]] | None = None,
    top_n: int = 20,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return summary and per-item diagnostics for a feed response."""
    if ground_truth is None and ground_truth_items is not None:
        ground_truth = {_normalize_match_name(item["name"]) for item in ground_truth_items}
    diagnosed = diagnose_feed_items(items, ground_truth=ground_truth, now=now)
    missing = find_missing_ground_truth_items(
        diagnosed,
        ground_truth_items or [],
    )
    missing_bucket_counts = Counter(item["triage_bucket"] for item in missing)
    return {
        "summary": summarize_feed_diagnostics(diagnosed, top_n=top_n),
        "items": diagnosed,
        "missing_ground_truth": missing,
        "missing_ground_truth_summary": {
            "total": len(missing),
            "bucket_counts": dict(missing_bucket_counts.most_common()),
        },
    }
