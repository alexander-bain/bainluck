"""Deterministic Discover card rendering classification.

This module decides what shape a Discover futures card *could* take without
changing ranking. The frontend can use this as a stable contract for native
cards, while admin/debug views can audit whether the feed is full of cards that
need heatmaps, bundles, distributions, timelines, or recap treatment.
"""

from __future__ import annotations

import re
from typing import Any

from app.utils.market_grouping import extract_threshold

_IPO_RE = re.compile(r"\b(ipo|initial public offering|market cap|valuation)\b", re.I)
_COMMODITY_RE = re.compile(
    r"\b(gold|xauusd|oil|wti|brent|natural gas|silver|copper|wheat|corn|soybean)\b",
    re.I,
)
_ROTTEN_TOMATOES_RE = re.compile(r"\b(rotten tomatoes|rt score|tomatometer)\b", re.I)
_MACRO_RANGE_RE = re.compile(
    r"\b(cpi|ppi|fed|rate cuts?|gdp|unemployment|consumer confidence|s&p|nasdaq|dow)\b",
    re.I,
)
_WEATHER_RANGE_RE = re.compile(
    r"\b(temperature|high temp|low temp|rainfall|snowfall|hurricane|landfall)\b",
    re.I,
)
_SPORTS_BRACKET_RE = re.compile(
    r"\b(playoff|finals?|champion|championship|world cup|stanley cup|super bowl|"
    r"wimbledon|french open|us open|australian open)\b",
    re.I,
)
_COMPACT_VALUE_RE = re.compile(
    r"(\$?)\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*([kmbt])?\b",
    re.I,
)


def _compact_value_thresholds(label: str) -> list[tuple[float, str, str]]:
    """Parse compact finance/range labels such as "$1.5T-$2.0T"."""
    values: list[tuple[float, str, str]] = []
    for match in _COMPACT_VALUE_RE.finditer(label):
        dollar, raw_value, suffix = match.groups()
        value = float(raw_value.replace(",", ""))
        multiplier = {
            "k": 1_000,
            "m": 1_000_000,
            "b": 1_000_000_000,
            "t": 1_000_000_000_000,
        }.get((suffix or "").lower(), 1)
        if not dollar and not suffix and 2020 <= value <= 2099:
            continue
        unit = f"{dollar}{(suffix or '').upper()}".strip()
        values.append((value * multiplier, unit, "exact"))
    return values


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _threshold_points(
    *,
    name: str,
    outcomes: list[dict[str, Any]],
    outcome_count: int | None,
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []

    for outcome in outcomes:
        outcome_name = _clean_text(outcome.get("name"))
        extracted = extract_threshold(outcome_name)
        extracted_values = (
            [extracted] if extracted else _compact_value_thresholds(outcome_name)
        )
        for value, unit, direction in extracted_values:
            points.append(
                {
                    "source": "outcome",
                    "label": outcome_name,
                    "value": value,
                    "unit": unit,
                    "direction": direction,
                    "probability": (
                        outcome.get("probability")
                        if outcome.get("probability") is not None
                        else outcome.get("current_probability")
                    ),
                }
            )

    if not points:
        extracted = extract_threshold(name)
        extracted_values = [extracted] if extracted else _compact_value_thresholds(name)
        for value, unit, direction in extracted_values:
            points.append(
                {
                    "source": "market_name",
                    "label": name,
                    "value": value,
                    "unit": unit,
                    "direction": direction,
                    "probability": None,
                }
            )

    if len(points) == 1 and (outcome_count or 0) >= 3:
        points[0]["needs_sibling_markets"] = True

    return points


def _has_recent_movement(outcomes: list[dict[str, Any]]) -> bool:
    for outcome in outcomes:
        movement = outcome.get("movement")
        if movement is None:
            movement = outcome.get("probability_change_24h")
        try:
            if movement is not None and abs(float(movement)) >= 0.02:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _distribution_outcomes(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for outcome in outcomes[:8]:
        label = _clean_text(outcome.get("name") or outcome.get("label"))
        if not label:
            continue
        rows.append(
            {
                "label": label,
                "probability": (
                    outcome.get("probability")
                    if outcome.get("probability") is not None
                    else outcome.get("current_probability")
                ),
                "movement": (
                    outcome.get("movement")
                    if outcome.get("movement") is not None
                    else outcome.get("probability_change_24h")
                ),
            }
        )
    return rows


def _comparison_theme(name: str, category: str | None) -> str | None:
    # This is broader than the public bundle allowlist. Some themes, especially
    # macro ranges and sports paths, are useful admin/archetype signals but too
    # broad to collapse publicly without stronger backend grouping evidence.
    category_lower = (category or "").lower()
    if _IPO_RE.search(name):
        return "ipo_valuation"
    if _ROTTEN_TOMATOES_RE.search(name):
        return "rotten_tomatoes_scores"
    if _COMMODITY_RE.search(name):
        return "commodity_ranges"
    if _MACRO_RANGE_RE.search(name) or category_lower == "economics":
        return "macro_ranges"
    if _WEATHER_RANGE_RE.search(name) or category_lower == "weather":
        return "weather_distributions"
    if _SPORTS_BRACKET_RE.search(name):
        return "sports_paths"
    return None


def classify_discover_card_archetype(
    *,
    name: str | None,
    category: str | None = None,
    outcomes: list[dict[str, Any]] | None = None,
    outcome_count: int | None = None,
    source_count: int | None = None,
    sources: list[str] | None = None,
    group_id: str | None = None,
    group_type: str | None = None,
    canonical_market_key: str | None = None,
    discover_llm: dict[str, Any] | None = None,
    resolved: bool = False,
    status: str | None = None,
) -> dict[str, Any]:
    """Return frontend/admin rendering metadata for a Discover futures market.

    Source disagreement is deliberately classified as QA-only. It should help
    us find stale/thin/badly grouped markets, not become a public card format.
    """

    market_name = _clean_text(name)
    outcome_rows = outcomes or []
    count = outcome_count if outcome_count is not None else len(outcome_rows)
    threshold_points = _threshold_points(
        name=market_name,
        outcomes=outcome_rows,
        outcome_count=count,
    )
    distribution_outcomes = _distribution_outcomes(outcome_rows)
    comparison_theme = _comparison_theme(market_name, category)

    suggested_format = "binary_probability"
    reasons: list[str] = []

    if resolved or status == "resolved":
        suggested_format = "resolution_recap"
        reasons.append("resolved_market")
    elif threshold_points and (
        len(threshold_points) >= 2
        or bool(comparison_theme)
        or bool(group_id)
        or bool(canonical_market_key)
    ):
        suggested_format = "threshold_heatmap"
        reasons.append("threshold_values")
    elif count >= 4:
        suggested_format = "outcome_distribution"
        reasons.append("multi_outcome_distribution")
    elif _has_recent_movement(outcome_rows):
        suggested_format = "probability_timeline"
        reasons.append("recent_movement")

    llm_axes = []
    if discover_llm:
        raw_axes = discover_llm.get("comparison_axes") or []
        if isinstance(raw_axes, list):
            llm_axes = [str(axis) for axis in raw_axes if axis]

    bundle_candidate = bool(
        comparison_theme
        or group_type in {"threshold", "progression", "canonical"}
        or llm_axes
    )
    if bundle_candidate:
        reasons.append("bundle_candidate")

    qa_signals: list[str] = []
    if (source_count or 0) > 1 or (sources and len(set(sources)) > 1):
        qa_signals.append("multi_source_consistency_check")

    return {
        "suggested_format": suggested_format,
        "bundle_candidate": bundle_candidate,
        "comparison_theme": comparison_theme,
        "threshold_points": threshold_points[:12],
        "distribution_outcomes": distribution_outcomes,
        "remaining_outcome_count": max(0, count - len(distribution_outcomes)),
        "qa_signals": qa_signals,
        "public_source_disagreement": False,
        "reasons": reasons,
    }
