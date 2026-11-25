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


def quote_source_mark(
    inputs: Iterable[Mapping[str, Any]],
    *,
    method: str | None = None,
    allow_unpriced: bool = False,
) -> dict:
    """Describe admitted prices in stable venue order, once per venue.

    Multiple admitted legs from one venue are represented by that venue's mean
    and oldest observation. This is the existing prop mean, not a new vote or
    a change to the displayed number. A missing leg/price refuses the entire
    claim; it cannot silently turn a two-input number into a one-source mark.

    ``allow_unpriced`` stays ``False`` for every caller except three-way away
    and draw source marks (#13269 / 196-A), where a contributing venue that
    does not carry its own away or draw price must be named with
    ``probability: None`` rather than shown a worked-out figure.
    """
    by_source: dict[str, list[dict]] = {}
    for item in inputs:
        key = item.get("key")
        key = "betting" if key == "odds_api" else key
        raw_prob = item.get("probability")
        if key not in SOURCE_NAMES:
            return no_source_mark("source_evidence_incomplete")
        if raw_prob is None:
            if not allow_unpriced:
                return no_source_mark("source_evidence_incomplete")
            probability = None
        else:
            probability = _probability(raw_prob)
            if probability is None:
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
        if any(leg["probability"] is None for leg in legs):
            merged_prob = None
        else:
            merged_prob = round(
                sum(leg["probability"] for leg in legs) / len(legs), 6
            )
        source = {
            "key": key,
            "name": SOURCE_NAMES[key],
            "probability": merged_prob,
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
    mark = {"state": "single" if len(sources) == 1 else "blend", "sources": sources}
    if len(sources) > 1 and method is not None:
        mark["method"] = method
    return mark


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


def fold_prop_source_marks(marks: Iterable[Mapping[str, Any] | None]) -> dict:
    """Preserve an identical proved grade when duplicate prop rows are folded."""
    entries = list(marks)
    if entries and all(isinstance(mark, Mapping) for mark in entries):
        first = entries[0]
        settled = first.get("settled")
        if (
            first.get("state") == "settled"
            and isinstance(settled, Mapping)
            and settled.get("result") in {"Won", "Lost"}
            and all(mark == first for mark in entries)
        ):
            return {"state": "settled", "sources": [], "settled": dict(settled)}
        if all(mark.get("state") in {"single", "blend"} for mark in entries):
            return quote_source_mark(
                source for mark in entries for source in mark.get("sources", [])
            )
    return no_source_mark("source_evidence_incomplete")


def source_mark_on_axis(mark: dict | None, *, inverted: bool) -> dict:
    """Reorient already selected prices when a reader prints the other side."""
    if not mark:
        return no_source_mark("source_evidence_incomplete")
    if not inverted or mark.get("state") not in {"single", "blend"}:
        return mark
    return {
        **mark,
        "sources": [
            {**source, "probability": round(1 - source["probability"], 6)}
            for source in mark["sources"]
        ],
    }


def cap_source_mark(row: dict) -> None:
    """Keep the rung's own evidence and any independent official result."""
    mark = row.get("source_mark") or no_source_mark("source_evidence_incomplete")
    row["source_evidence"] = list(mark.get("sources", []))
    if mark.get("state") != "settled":
        row["source_mark"] = no_source_mark("monotonic_conflict")


def headline_source_marks(
    event: Any,
    hero: Any,
    selected_inputs: Iterable[tuple[str, float]],
    *,
    observations: Mapping[str, Any] | None = None,
    method: str | None = None,
    away_available: bool = True,
    three_way_probs: tuple[float, float, float] | None = None,
    books_three_way: tuple[float, float] | None = None,
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

    return blended_source_marks(
        event,
        selected_inputs,
        observations=observations,
        method=method,
        away_available=away_available,
        three_way_probs=three_way_probs,
        books_three_way=books_three_way,
    )


def _own_three_way_side_price(
    bag: Any,
    key: str,
    home_probability: float,
    side: str,
    *,
    books_three_way: tuple[float, float] | None = None,
) -> float | None:
    """Return ``key``'s own away or draw probability, or ``None`` if unheld (#13269).

    Never synthesizes a venue's away or draw price from ``(1 - home)`` or from
    another source's ratio (196-A). Reads each venue's own stamped
    ``away_value``/``draw_value`` bound to ``home_probability`` and timestamp;
    for ``"betting"`` only, also accepts Sportsbooks' own live ``odds_snapshots``
    consensus ``books_three_way = (books_home, books_away)`` when it matches
    ``home_probability``.
    """
    from app.utils.aggregation import extract_source_three_way_side

    stamped = extract_source_three_way_side(bag, key, home_probability, side)
    if stamped is not None:
        return stamped
    if key == "betting" and books_three_way is not None:
        bh, ba = books_three_way
        if (
            isinstance(bh, (int, float))
            and isinstance(ba, (int, float))
            and not isinstance(bh, bool)
            and not isinstance(ba, bool)
            and 0.0 < bh < 1.0
            and 0.0 < ba < 1.0
            and (bh + ba) < 0.99
            and abs(float(bh) - float(home_probability)) <= 0.02
        ):
            if side == "away":
                return round(float(ba), 6)
            return round(1.0 - float(bh) - float(ba), 6)
    return None


def three_way_side_source_mark(
    event: Any,
    selected_inputs: Iterable[tuple[str, float]],
    *,
    side: str,
    observations: Mapping[str, Any] | None = None,
    method: str | None = None,
    books_three_way: tuple[float, float] | None = None,
) -> dict:
    """Honest three-way source mark for ``side`` (``"away"`` or ``"draw"``) (#13269).

    Each contributing source shows its own ``side`` price where held on the
    same reading as its home price, and ``probability: None`` (venue named
    without a price) where not held. Never works out a figure for a venue.
    """
    if side not in ("away", "draw"):
        raise ValueError(f"three_way_side_source_mark side must be 'away' or 'draw', got {side!r}")
    selected = list(selected_inputs)
    bag = getattr(event, "win_probability_sources", None)
    count = bag.get("betting_book_count") if isinstance(bag, dict) else None
    if observations is None:
        from app.utils.aggregation import source_price_read_time

        clocks = {
            key: source_price_read_time(bag, key, value)
            for key, value in selected
        }
    else:
        clocks = observations

    return quote_source_mark(
        (
            {
                "key": key,
                "probability": _own_three_way_side_price(
                    bag,
                    key,
                    probability,
                    side,
                    books_three_way=books_three_way,
                ),
                "observed_at": clocks.get(key),
                "count": count if key == "betting" else None,
            }
            for key, probability in selected
        ),
        method=method,
        allow_unpriced=True,
    )


def blended_source_marks(
    event: Any,
    selected_inputs: Iterable[tuple[str, float]],
    *,
    observations: Mapping[str, Any] | None = None,
    method: str | None = None,
    away_available: bool = True,
    three_way_probs: tuple[float, float, float] | None = None,
    books_three_way: tuple[float, float] | None = None,
) -> tuple[dict, dict]:
    """Orient the selected quote inputs for each team.

    On a two-way sport the away leg is ``1 - p_home``. On a three-way
    (draw-priced) sport (``three_way_probs`` present), ``away_source_mark``
    shows each contributing source's OWN away price where held and names the
    source with ``probability: None`` where unheld — never a worked-out figure
    (#13269 / 196-A).
    """
    selected = list(selected_inputs)
    bag = getattr(event, "win_probability_sources", None)
    count = bag.get("betting_book_count") if isinstance(bag, dict) else None
    if observations is None:
        from app.utils.aggregation import source_price_read_time

        clocks = {
            key: source_price_read_time(bag, key, value)
            for key, value in selected
        }
    else:
        clocks = observations

    home_mark = quote_source_mark(
        (
            {
                "key": key,
                "probability": probability,
                "observed_at": clocks.get(key),
                "count": count if key == "betting" else None,
            }
            for key, probability in selected
        ),
        method=method,
    )
    if not away_available:
        return home_mark, no_source_mark("away_unavailable")
    if three_way_probs is not None:
        away_mark = three_way_side_source_mark(
            event,
            selected,
            side="away",
            observations=clocks,
            method=method,
            books_three_way=books_three_way,
        )
        return home_mark, away_mark

    away_mark = quote_source_mark(
        (
            {
                "key": key,
                "probability": 1 - probability,
                "observed_at": clocks.get(key),
                "count": count if key == "betting" else None,
            }
            for key, probability in selected
        ),
        method=method,
    )
    return home_mark, away_mark
