"""#13426 — Blended, field-normalized probability timeline for golf tournaments.

Keeps every point on a golf tournament chart in the exact same probability
measure as the tournament's headline / current number (and its Pregame cutoff):
per-source readings in force at each bucket close pass through the shared
``_build_one_tournament`` pipeline (placeholder filter, legacy >1.5 rescale,
DataGolf invitee gate, equal-weighted source mean, and full-field normalization).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Sequence


@dataclass(frozen=True)
class SnapshotReading:
    outcome_id: int
    captured_at: datetime
    valid_until: datetime | None
    probability: float | None
    yes_bid: float | None
    yes_ask: float | None


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_field_normalized(entry: dict | None) -> bool:
    golfers = (entry or {}).get("_all_golfers") or (entry or {}).get("golfers") or []
    return bool(golfers) and all("rendered_percent" in g for g in golfers)


def build_golf_blended_timeline(
    tourn_key: str,
    winner_markets: Sequence[Any],
    current_entry: dict,
    snapshots: Sequence[SnapshotReading],
    *,
    build_entry: Callable[[str, list], dict | None],
    match_key_fn: Callable[[str], str],
    top: int = 10,
    hours: int = 168,
    full_range: bool = False,
    commence_time: datetime | None = None,
    is_live: bool = False,
    max_reading_age: timedelta = timedelta(hours=48),
    now: datetime | None = None,
) -> dict:
    """Build a ``ProbabilityTimelineResponse``-shaped blended golf history."""
    ref_now = _ensure_utc(now or datetime.now(timezone.utc))
    started = is_live or (
        commence_time is not None and _ensure_utc(commence_time) <= ref_now
    )
    bucket_seconds = 900 if started else 3600

    valid_snaps = sorted(
        (
            SnapshotReading(
                outcome_id=s.outcome_id,
                captured_at=_ensure_utc(s.captured_at),
                valid_until=_ensure_utc(s.valid_until) if s.valid_until is not None else None,
                probability=float(s.probability) if s.probability is not None else None,
                yes_bid=float(s.yes_bid) if s.yes_bid is not None else None,
                yes_ask=float(s.yes_ask) if s.yes_ask is not None else None,
            )
            for s in snapshots
            if s.probability is not None
        ),
        key=lambda s: s.captured_at,
    )

    if full_range and valid_snaps:
        earliest = valid_snaps[0].captured_at
        cutoff = earliest
        actual_hours = max(1, int((ref_now - earliest).total_seconds() // 3600) + 1)
    else:
        actual_hours = hours
        cutoff = ref_now - timedelta(hours=hours)

    current_golfers = list(current_entry.get("_all_golfers") or current_entry.get("golfers") or [])
    top_golfers = current_golfers[:top]
    top_name_by_key: dict[str, str] = {}
    for g in top_golfers:
        mk = match_key_fn(g.get("name") or "")
        if mk:
            top_name_by_key[mk] = g["name"]

    current_normalized = _is_field_normalized(current_entry)

    # Identify bucket closes where at least one snapshot landed inside the window.
    bucket_keys: set[int] = set()
    for s in valid_snaps:
        if s.captured_at < cutoff or s.captured_at > ref_now:
            continue
        bk = (int(s.captured_at.timestamp()) // bucket_seconds) * bucket_seconds
        bucket_keys.add(bk)

    timeline: list[dict] = []
    if winner_markets and bucket_keys and current_golfers:
        active: dict[int, tuple[tuple[float | None, float | None, float | None], datetime]] = {}
        snap_idx = 0
        total_snaps = len(valid_snaps)

        eval_points: list[tuple[datetime, datetime]] = []
        for bk in sorted(bucket_keys):
            bucket_at = datetime.fromtimestamp(bk, tz=timezone.utc)
            bucket_end = min(ref_now, bucket_at + timedelta(seconds=bucket_seconds))
            eval_points.append((bucket_at, bucket_end))

        for bucket_at, eval_at in eval_points:
            while snap_idx < total_snaps and valid_snaps[snap_idx].captured_at <= eval_at:
                s = valid_snaps[snap_idx]
                fresh_until = s.valid_until or s.captured_at
                active[s.outcome_id] = (
                    (s.probability, s.yes_bid, s.yes_ask),
                    fresh_until,
                )
                snap_idx += 1

            floor_at = eval_at - max_reading_age
            snaps_as_of = {
                oid: tuple_val
                for oid, (tuple_val, fresh_until) in active.items()
                if fresh_until >= floor_at
            }
            if not snaps_as_of:
                continue

            hist_entry = build_entry(tourn_key, winner_markets, snaps_as_of)
            if not hist_entry:
                continue
            if current_normalized and not _is_field_normalized(hist_entry):
                continue

            outcomes_map: dict[str, float] = {}
            field_prob = 0.0
            hist_golfers = hist_entry.get("_all_golfers") or hist_entry.get("golfers") or []
            for g in hist_golfers:
                prob = g.get("probability")
                if prob is None:
                    continue
                mk = match_key_fn(g.get("name") or "")
                canonical = top_name_by_key.get(mk)
                if canonical is not None:
                    outcomes_map[canonical] = round(float(prob), 6)
                else:
                    field_prob += float(prob)
            for ov in hist_entry.get("overflow_outcomes") or []:
                prob = ov.get("probability")
                if prob is not None:
                    field_prob += float(prob)

            if len(current_golfers) > top and (field_prob > 0 or len(top_name_by_key) < len(hist_golfers)):
                outcomes_map["Field"] = round(min(field_prob, 1.0), 6)

            if outcomes_map:
                timeline.append({
                    "timestamp": bucket_at.isoformat(),
                    "outcomes": outcomes_map,
                })

    outcomes_meta: list[dict] = []
    for idx, g in enumerate(top_golfers, start=1):
        outcomes_meta.append({
            "id": idx,
            "name": g["name"],
            "current_probability": round(float(g["probability"]), 6) if g.get("probability") is not None else None,
            "rank": idx,
            "probability_change_24h": round(float(g["movement_24h"]), 4) if g.get("movement_24h") is not None else None,
            "opening_probability": round(float(g["opening_probability"]), 4) if g.get("opening_probability") is not None else None,
        })
    if len(current_golfers) > top:
        field_current = sum(float(g.get("probability") or 0.0) for g in current_golfers[top:])
        outcomes_meta.append({
            "id": None,
            "name": "Field",
            "current_probability": round(min(field_current, 1.0), 6),
        })

    sources = sorted(set(current_entry.get("market_sources") or []))
    market_ids = list(current_entry.get("market_ids") or [])
    coverage_hours: float | None = None
    observation_times: int | None = len(timeline) if timeline else None
    if len(timeline) >= 2:
        t0 = datetime.fromisoformat(timeline[0]["timestamp"])
        t1 = datetime.fromisoformat(timeline[-1]["timestamp"])
        coverage_hours = round(max(0.0, (t1 - t0).total_seconds() / 3600.0), 2)
    elif len(timeline) == 1:
        coverage_hours = 0.0

    return {
        "market_id": market_ids[0] if market_ids else 0,
        "market_name": f"{current_entry.get('name', tourn_key)} - Winner",
        "sport_category": "golf",
        "source": "blend" if len(sources) > 1 else (sources[0] if sources else "blend"),
        "sources": sources,
        "hours": hours,
        "actual_hours": actual_hours,
        "top": top,
        "bucket_seconds": bucket_seconds,
        "coverage_hours": coverage_hours,
        "observation_times": observation_times,
        "timeline": timeline,
        "outcomes": outcomes_meta,
    }
