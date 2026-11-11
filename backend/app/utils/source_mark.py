"""Server-owned provenance for a displayed probability (#12581).

Callers pass the inputs their calculation actually admitted. This module does
not pick sources, reconstruct a blend, or borrow polling/publication clocks.
An unknown observation stays null; a refused number keeps its reason.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from app.utils.latest_observation import blended_observed_at

SOURCE_NAMES = {
    "kalshi": "Kalshi",
    "polymarket": "Polymarket",
    "betting": "Sportsbooks",
    "espn": "ESPN",
    "stat_model": "Bain Luck Model",
    "mlb": "MLB",
    "datagolf": "DataGolf",
}
_SOURCE_ORDER = {key: index for index, key in enumerate(SOURCE_NAMES)}


def _probability(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and 0 <= value <= 1 else None


def observation_stamp(value: Any) -> str | None:
    """An explicit observation, never a fallback to now or a row touch stamp."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def no_source_mark(reason: str) -> dict:
    return {"state": "none", "sources": [], "reason": reason}


def quote_source_mark(inputs: Iterable[Mapping[str, Any]]) -> dict:
    """Describe admitted prices in stable venue order, once per venue.

    Multiple admitted legs from one venue are represented by that venue's mean
    and oldest observation. This is the existing prop mean, not a new vote or
    a change to the displayed number. A missing leg/price refuses the entire
    claim; it cannot silently turn a two-input number into a one-source mark.
    """
    by_source: dict[str, list[dict]] = {}
    for item in inputs:
        key = item.get("key")
        key = "betting" if key == "odds_api" else key
        probability = _probability(item.get("probability"))
        if key not in SOURCE_NAMES or probability is None:
            return no_source_mark("source_evidence_incomplete")
        by_source.setdefault(key, []).append(
            {
                "probability": probability,
                "observed_at": observation_stamp(item.get("observed_at")),
                "count": item.get("count"),
            }
        )
    if not by_source:
        return no_source_mark("no_contributing_source")

    sources = []
    for key in sorted(by_source, key=_SOURCE_ORDER.__getitem__):
        legs = by_source[key]
        stamp = blended_observed_at(leg["observed_at"] for leg in legs)
        source = {
            "key": key,
            "name": SOURCE_NAMES[key],
            "probability": round(
                sum(leg["probability"] for leg in legs) / len(legs), 6
            ),
            "observed_at": stamp,
        }
        if stamp is None:
            source["reason"] = "observation_unknown"
        counts = [leg["count"] for leg in legs]
        if key == "betting" and all(type(c) is int and c > 0 for c in counts):
            # Repeated consensus inputs are not additional sportsbooks.
            if len(set(counts)) == 1:
                source["count"] = counts[0]
        sources.append(source)
    return {"state": "blend", "sources": sources}


def settled_source_mark(source: str | None, result: str, at: Any = None) -> dict:
    return {
        "state": "settled",
        "sources": [],
        "settled": {
            "source": source if isinstance(source, str) else None,
            "result": result,
            "at": observation_stamp(at),
        },
    }


def source_mark_on_axis(mark: dict | None, *, inverted: bool) -> dict:
    """Reorient already selected prices when a reader prints the other side."""
    if not mark:
        return no_source_mark("source_evidence_incomplete")
    if not inverted or mark.get("state") != "blend":
        return mark
    return {
        **mark,
        "sources": [
            {**source, "probability": round(1 - source["probability"], 6)}
            for source in mark["sources"]
        ],
    }


def cap_source_mark(row: dict) -> None:
    """Keep a capped rung's own evidence; never credit its donor's quote."""
    mark = row.get("source_mark") or no_source_mark("source_evidence_incomplete")
    row["source_evidence"] = list(mark.get("sources", []))
    row["source_mark"] = no_source_mark("monotonic_conflict")


def headline_source_marks(
    event: Any,
    hero: Any,
    selected_inputs: Iterable[tuple[str, float]],
    *,
    observations: Mapping[str, Any] | None = None,
    away_available: bool = True,
) -> tuple[dict, dict]:
    """Both axes from the hero's trace; no client complements or source guesses.

    ``observations`` may only contain clocks bound to these selected prices.
    In particular JSONB updated_at/observed_basis are not accepted implicitly:
    one is also written at publication, the other may be a generic poll touch.
    """
    if hero is None:
        return no_source_mark("no_probability"), no_source_mark("no_probability")
    if hero.source == "settled":
        source = getattr(event, "score_source", None)
        at = getattr(event, "completed_at", None)
        if hero.settled_result == "draw":
            home = away = "Draw"
        elif hero.home_probability == 1:
            home, away = "Won", "Lost"
        else:
            home, away = "Lost", "Won"
        return settled_source_mark(source, home, at), settled_source_mark(
            source, away, at
        )
    if hero.source != "blend":
        reason = "opening_only" if hero.source == "opening" else "final_unresolved"
        return no_source_mark(reason), no_source_mark(reason)

    selected = list(selected_inputs)
    bag = getattr(event, "win_probability_sources", None)
    count = bag.get("betting_book_count") if isinstance(bag, dict) else None
    clocks = observations or {}

    def mark(away: bool) -> dict:
        return quote_source_mark(
            {
                "key": key,
                "probability": 1 - probability if away else probability,
                "observed_at": clocks.get(key),
                "count": count if key == "betting" else None,
            }
            for key, probability in selected
        )

    return mark(False), (
        mark(True) if away_available else no_source_mark("away_unavailable")
    )
