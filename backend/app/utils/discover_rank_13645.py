"""#13645 Ranking proposal: Alex's cold-read six downranks + family rules.

Takes a captured slate candidate list and applies the #13645 family rules:
1. Exclude weekly single-stock price ladders (`asset_price_level`, R2) and enforce
   one-per-ticker deduplication (`story:equity_ticker:*`).
2. Downrank non-U.S. central bank & non-U.S. GDP markets (`non_us_macro_downrank`, -20).
3. Downrank minor-conference championship berth singles (`minor_conf_title_berth`, -20).
4. Fold Yemen/Houthi/Red Sea markets into `story:middle_east_conflict` and downrank
   narrow tactical conflict specifics (`regional_conflict_operational`, -15).
5. Move ``roundup:tomorrows-highs`` (and forecast weather roundups) outside seats 1..10.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from app.utils.discover_opening_mix import is_opening_weather_excluded_roundup
from app.utils.feed_market_quality import (
    classify_market_quality,
    quality_score_adjustment,
)

_OPENING_TEN = 10
# Decision 408 proposal weights used for offline replay & pair p13645 while the
# live scoring constants in `feed_market_quality` ship at 0 awaiting ruling.
_PROPOSED_REPLAY_DOWNRANK_SHIFTS = {
    "non_us_macro_downrank": 20,
    "minor_conf_title_berth": 20,
    "regional_conflict_operational": 15,
}


def _served_pos(candidate: Mapping[str, Any]) -> float:
    pos = candidate.get("served_position")
    return float(pos) if isinstance(pos, (int, float)) else math.inf


def _is_tomorrows_highs_candidate(candidate: Mapping[str, Any]) -> bool:
    card = candidate.get("card")
    if isinstance(card, Mapping) and is_opening_weather_excluded_roundup(card):
        return True
    key = str(candidate.get("item_key") or "").strip().lower()
    container = str(candidate.get("container") or "").strip().lower()
    return "tomorrows-highs" in key or "tomorrows-highs" in container


def _baseline_quality(candidate: Mapping[str, Any]):
    card = candidate.get("card")
    data = card.get("data") if isinstance(card, Mapping) else None
    if not isinstance(data, Mapping):
        return None
    card_type = str(card.get("type") or "").lower()
    if card_type != "futures":
        return None
    name = str(data.get("name") or candidate.get("title") or "")
    cat = data.get("llm_sport_category") or candidate.get("category")
    outcomes = [
        str(o.get("name") or "")
        for o in (data.get("top_outcomes") or ())
        if isinstance(o, Mapping)
    ]
    return classify_market_quality(
        name,
        sport_category=str(cat) if cat else None,
        outcome_names=outcomes,
        external_id=str(data.get("external_id") or "") or None,
        persisted_story_key=str(data.get("story_key") or "") or None,
    )


def rank_13645_downranks(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Rank slate candidates with the #13645 family downranks & opening-weather exclusion."""
    ordered = sorted((dict(c) for c in candidates), key=_served_pos)
    if not ordered:
        return []

    n_total = len(ordered)
    seen_tickers: set[str] = set()
    has_mideast_bundle = any(
        "story:middle_east_conflict" in str(c.get("item_key") or "")
        or "story:middle_east_conflict" in str(c.get("container") or "")
        for c in ordered
    )

    scored: list[tuple[tuple[int, float, float], dict[str, Any]]] = []
    for idx, cand in enumerate(ordered):
        base_rank = _served_pos(cand)
        if not math.isfinite(base_rank):
            base_rank = float(n_total + idx + 1)

        q = _baseline_quality(cand)
        tier = 0  # 0 = normal/active, 1 = excluded/folded out
        effective_pos = base_rank

        if q is not None:
            if q.quality_class == "suppress" or "asset_price_level" in q.reasons:
                tier = 1
                effective_pos = base_rank + 100.0
            else:
                adj = quality_score_adjustment(q)
                shift = max(
                    abs(min(0, adj)),
                    sum(
                        weight
                        for reason, weight in _PROPOSED_REPLAY_DOWNRANK_SHIFTS.items()
                        if reason in q.reasons
                    ),
                )
                if shift > 0:
                    effective_pos = base_rank + shift

            if q.story_key and q.story_key.startswith("story:equity_ticker:"):
                if q.story_key in seen_tickers:
                    tier = 1
                    effective_pos += 150.0
                seen_tickers.add(q.story_key)

            if (
                q.story_key == "story:middle_east_conflict"
                and "regional_conflict_operational" in q.reasons
                and has_mideast_bundle
            ):
                effective_pos = max(effective_pos, base_rank + 25.0)

        if _is_tomorrows_highs_candidate(cand) and base_rank <= _OPENING_TEN:
            # Displace opening-seat tomorrow's highs cleanly outside seats 1..10.
            effective_pos = float(_OPENING_TEN + 11.0)

        scored.append(((tier, effective_pos, base_rank), cand))

    scored.sort(key=lambda pair: pair[0])
    result = [cand for _, cand in scored]

    # Hard guarantee: tomorrow's highs never sits in seats 1..10 when deeper cards exist.
    if len(result) > _OPENING_TEN:
        opening_weather = [c for c in result[:_OPENING_TEN] if _is_tomorrows_highs_candidate(c)]
        if opening_weather:
            non_weather_rest = [c for c in result[_OPENING_TEN:] if not _is_tomorrows_highs_candidate(c)]
            if non_weather_rest:
                top_ten = [c for c in result[:_OPENING_TEN] if not _is_tomorrows_highs_candidate(c)]
                needed = _OPENING_TEN - len(top_ten)
                promoted = non_weather_rest[:needed]
                remaining = non_weather_rest[needed:]
                return top_ten + promoted + opening_weather + remaining

    return result
