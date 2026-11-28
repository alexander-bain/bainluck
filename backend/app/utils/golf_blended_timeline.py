"""#13426 — Blended, field-normalized probability timeline for golf tournaments.

Keeps every point on a golf tournament chart in the exact same probability
measure as the tournament's headline / current number (and its Pregame cutoff):
per-source readings in force at each bucket close pass through the shared
``_build_one_tournament`` pipeline (placeholder filter, legacy >1.5 rescale,
DataGolf invitee gate, equal-weighted source mean, and full-field normalization).

Timestamp & bucket convention (matches ``/api/futures/{id}/probability-timeline``):
- Each emitted point is stamped with its bucket's **start** (``bucket_at.isoformat()``)
  in UTC and carries the blended, field-normalized probability computed from the
  latest reading in force for each outcome strictly before bucket close
  (``captured_at < eval_at``).

Production safeguards:
- Pure-Python worker function accepts only detached dataclasses/dicts so it runs
  safely off the asyncio event loop via ``asyncio.to_thread``.
- Both ``hours`` and ``range=full`` enforce a single 90-day SQL/window ceiling
  (``GOLF_TIMELINE_FULL_MAX_DAYS = 90`` / ``GOLF_TIMELINE_FULL_MAX_HOURS = 2160``)
  anchored to the tournament's own readings (not the wall clock on completed events).
- Once play starts, buckets during play stay at 15-minute resolution (``900s``);
  coarsening applies only to pre-tee history.
- Responses are cached per ``(slug, top, hours, range)`` in a bounded in-process
  LRU + shared Redis, and closed historical buckets are memoized in-process across
  live refreshes so each 2-minute tick evaluates only newly touched buckets.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import math
import struct
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping, Sequence

from app.utils import request_cache as _rc

logger = logging.getLogger(__name__)

GOLF_TIMELINE_FULL_MAX_DAYS = 90
GOLF_TIMELINE_FULL_MAX_HOURS = GOLF_TIMELINE_FULL_MAX_DAYS * 24  # 2160h
GOLF_TIMELINE_MAX_BUCKETS = 240
GOLF_TIMELINE_PLAY_BUCKET_SECONDS = 900
GOLF_TIMELINE_PRE_TEE_MAX_BUCKETS = 120
GOLF_TIMELINE_MAX_PLAY_DAYS = 7

GOLF_TIMELINE_CACHE_PREFIX = "bainluck:golf:prob-timeline:v2:"
GOLF_TIMELINE_CACHE_TTL_LIVE_S = 120
GOLF_TIMELINE_CACHE_TTL_IDLE_S = 600
GOLF_TIMELINE_L0_MAX_ENTRIES = 16
GOLF_TIMELINE_CLOSED_BUCKETS_MAX_TOURNAMENTS = 4
GOLF_TIMELINE_CLOSED_BUCKETS_TTL_S = 3600


@dataclass(frozen=True)
class SnapshotReading:
    outcome_id: int
    captured_at: datetime
    valid_until: datetime | None
    probability: float | None
    yes_bid: float | None
    yes_ask: float | None


@dataclass(frozen=True)
class DetachedOutcome:
    id: int
    external_id: str | None
    name: str
    current_probability: float | None
    current_yes_bid: float | None
    current_yes_ask: float | None
    opening_probability: float | None = None
    probability_change_24h: float | None = None
    is_winner: bool | None = None
    resolution_source: str | None = None


@dataclass(frozen=True)
class DetachedMarket:
    id: int
    name: str
    source: str | None
    external_id: str | None
    commence_time: datetime | None
    resolution_date: datetime | None
    status: str | None
    llm_sport_category: str | None
    market_tier: int | None
    market_metadata: dict[str, Any] | None
    mutually_exclusive: bool | None
    outcomes: tuple[DetachedOutcome, ...]


def detach_winner_market(market: Any) -> DetachedMarket:
    """Copy a SQLAlchemy/SimpleNamespace winner market into an off-thread struct.

    Strips present-day movement/winner state on outcomes so historical bucket
    evaluation can never borrow present-day values.
    """
    raw_meta = getattr(market, "market_metadata", None)
    meta_copy = copy.deepcopy(dict(raw_meta)) if isinstance(raw_meta, Mapping) else None
    detached_outcomes = tuple(
        DetachedOutcome(
            id=int(o.id),
            external_id=getattr(o, "external_id", None),
            name=str(getattr(o, "name", "") or ""),
            current_probability=(
                float(o.current_probability)
                if getattr(o, "current_probability", None) is not None
                else None
            ),
            current_yes_bid=(
                float(o.current_yes_bid)
                if getattr(o, "current_yes_bid", None) is not None
                else None
            ),
            current_yes_ask=(
                float(o.current_yes_ask)
                if getattr(o, "current_yes_ask", None) is not None
                else None
            ),
        )
        for o in (getattr(market, "outcomes", None) or ())
    )
    return DetachedMarket(
        id=int(market.id),
        name=str(getattr(market, "name", "") or ""),
        source=getattr(market, "source", None),
        external_id=getattr(market, "external_id", None),
        commence_time=getattr(market, "commence_time", None),
        resolution_date=getattr(market, "resolution_date", None),
        status=getattr(market, "status", None),
        llm_sport_category=getattr(market, "llm_sport_category", None),
        market_tier=getattr(market, "market_tier", None),
        market_metadata=meta_copy,
        mutually_exclusive=getattr(market, "mutually_exclusive", None),
        outcomes=detached_outcomes,
    )


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_field_normalized(entry: dict | None) -> bool:
    golfers = (entry or {}).get("_all_golfers") or (entry or {}).get("golfers") or []
    return bool(golfers) and all("rendered_percent" in g for g in golfers)


def history_fetch_floor(
    now: datetime,
    *,
    hours: int,
    full_range: bool,
    max_reading_age: timedelta,
    full_max_days: int = GOLF_TIMELINE_FULL_MAX_DAYS,
) -> datetime:
    """Hard SQL lower bound on snapshot reads (one 90-day ceiling for both paths)."""
    ref_now = _ensure_utc(now)
    clamped_hours = max(1, min(int(hours), full_max_days * 24))
    lookback = timedelta(days=full_max_days) if full_range else timedelta(hours=clamped_hours)
    return ref_now - lookback - max_reading_age


def choose_bucket_seconds(
    span_seconds: float,
    *,
    started: bool,
    max_buckets: int = GOLF_TIMELINE_MAX_BUCKETS,
) -> int:
    """Pick bucket width: 15m live / 60m pre-tournament, widening if >max_buckets."""
    base = 900 if started else 3600
    if span_seconds <= 0 or max_buckets <= 0:
        return base
    if (span_seconds / base) <= max_buckets:
        return base
    step = base
    needed = math.ceil(span_seconds / max_buckets)
    return max(base, int(math.ceil(needed / step) * step))


def _timeline_cache_key(
    slug: str,
    *,
    top: int,
    hours: int,
    history_range: str | None,
) -> str:
    range_norm = (history_range or "").strip().lower() or "hours"
    clamped_hours = max(1, min(int(hours), GOLF_TIMELINE_FULL_MAX_HOURS))
    digest = hashlib.sha256(
        f"{slug.strip().lower()}|top={int(top)}|hours={clamped_hours}|range={range_norm}".encode("utf-8")
    ).hexdigest()[:24]
    return f"{GOLF_TIMELINE_CACHE_PREFIX}{digest}"


ClosedBucketEntry = tuple[bytes, tuple[tuple[str, float], ...] | None, float, int]

_l0_timeline_cache: "OrderedDict[str, tuple[float, str]]" = OrderedDict()
_l0_closed_buckets_cache: "OrderedDict[str, tuple[float, dict[tuple[int, int], ClosedBucketEntry]]]" = OrderedDict()


def reset_timeline_cache_for_tests() -> None:
    _l0_timeline_cache.clear()
    _l0_closed_buckets_cache.clear()


def closed_bucket_cache_key(
    slug: str,
    market_ids: Sequence[int],
    current_normalized: bool,
) -> str:
    ids_part = ",".join(str(int(mid)) for mid in sorted(market_ids))
    digest = hashlib.sha256(
        f"{slug.strip().lower()}|norm={int(bool(current_normalized))}|mkts={ids_part}".encode("utf-8")
    ).hexdigest()[:24]
    return f"closed:{digest}"


def get_closed_bucket_cache(
    cache_key: str,
) -> dict[tuple[int, int], ClosedBucketEntry]:
    hit = _l0_closed_buckets_cache.get(cache_key)
    if hit is None:
        return {}
    expires_mono, entries = hit
    if time.monotonic() >= expires_mono:
        _l0_closed_buckets_cache.pop(cache_key, None)
        return {}
    _l0_closed_buckets_cache.move_to_end(cache_key)
    return dict(entries)


def put_closed_bucket_cache(
    cache_key: str,
    entries: Mapping[tuple[int, int], ClosedBucketEntry],
    *,
    ttl_s: int = GOLF_TIMELINE_CLOSED_BUCKETS_TTL_S,
) -> None:
    if not entries:
        return
    if cache_key in _l0_closed_buckets_cache:
        _l0_closed_buckets_cache.pop(cache_key, None)
    while len(_l0_closed_buckets_cache) >= GOLF_TIMELINE_CLOSED_BUCKETS_MAX_TOURNAMENTS:
        _l0_closed_buckets_cache.popitem(last=False)
    _l0_closed_buckets_cache[cache_key] = (
        time.monotonic() + ttl_s,
        dict(entries),
    )


def _snaps_signature(
    snaps_as_of: Mapping[int, tuple[float | None, float | None, float | None]],
) -> bytes:
    """Fast content digest of ``snaps_as_of`` so unchanged/cached buckets skip rebuild."""
    h = hashlib.blake2b(digest_size=16)
    packer = struct.Struct("!qBddd")
    for oid in sorted(snaps_as_of):
        prob, bid, ask = snaps_as_of[oid]
        flags = (
            (1 if prob is not None else 0)
            | (2 if bid is not None else 0)
            | (4 if ask is not None else 0)
        )
        h.update(
            packer.pack(
                int(oid),
                flags,
                0.0 if prob is None else float(prob),
                0.0 if bid is None else float(bid),
                0.0 if ask is None else float(ask),
            )
        )
    return h.digest()


def _l0_get(key: str) -> dict | None:
    hit = _l0_timeline_cache.get(key)
    if hit is None:
        return None
    expires_mono, raw_json = hit
    if time.monotonic() >= expires_mono:
        _l0_timeline_cache.pop(key, None)
        return None
    _l0_timeline_cache.move_to_end(key)
    try:
        return json.loads(raw_json)
    except Exception:
        _l0_timeline_cache.pop(key, None)
        return None


def _l0_set(key: str, payload: dict, *, ttl_s: int) -> None:
    try:
        raw_json = json.dumps(payload, default=str)
    except Exception:
        return
    if key in _l0_timeline_cache:
        _l0_timeline_cache.pop(key, None)
    while len(_l0_timeline_cache) >= GOLF_TIMELINE_L0_MAX_ENTRIES:
        _l0_timeline_cache.popitem(last=False)
    _l0_timeline_cache[key] = (time.monotonic() + ttl_s, raw_json)


async def get_or_build_cached_timeline(
    slug: str,
    *,
    top: int,
    hours: int,
    history_range: str | None,
    builder: Callable[[], Awaitable[tuple[dict, bool]]],
) -> tuple[dict, str]:
    """Serve per-(slug, params) cached timeline across L0 LRU -> Redis -> singleflight.

    ``builder`` returns ``(payload_dict, is_live)``.
    """
    key = _timeline_cache_key(slug, top=top, hours=hours, history_range=history_range)

    l0_hit = _l0_get(key)
    if l0_hit is not None:
        return l0_hit, "l0_hit"

    redis_client = None
    try:
        redis_client = await _rc.get_shared_async_redis()
    except Exception:
        redis_client = None

    if redis_client is not None:
        r_res = await _rc.bounded_redis_call(lambda: redis_client.get(key))
        if r_res.is_ok and r_res.value is not None:
            raw = r_res.value.decode("utf-8") if isinstance(r_res.value, (bytes, bytearray)) else r_res.value
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    _l0_set(key, parsed, ttl_s=GOLF_TIMELINE_CACHE_TTL_LIVE_S)
                    return parsed, "redis_hit"
            except Exception:
                pass

    is_leader, fut = _rc.begin_build(key)
    if not is_leader:
        try:
            payload = await asyncio.wait_for(asyncio.shield(fut), timeout=20.0)
            return copy.deepcopy(payload), "coalesced_hit"
        except Exception:
            pass

    leader_fut = fut if is_leader else None
    try:
        payload, is_live = await builder()
        ttl_s = GOLF_TIMELINE_CACHE_TTL_LIVE_S if is_live else GOLF_TIMELINE_CACHE_TTL_IDLE_S
        _l0_set(key, payload, ttl_s=ttl_s)
        if redis_client is not None:
            raw = json.dumps(payload, default=str)
            await _rc.bounded_redis_call(
                lambda: redis_client.set(key, raw, ex=ttl_s),
                treat_none_as_miss=False,
            )
        if leader_fut is not None:
            _rc.finish_build(key, leader_fut, result=payload)
        return payload, "miss_built"
    except BaseException as exc:
        if leader_fut is not None:
            _rc.finish_build(key, leader_fut, exc=exc)
        raise


def _extract_bucket_pairs(
    hist_entry: dict | None,
    *,
    current_normalized: bool,
    match_key_fn: Callable[[str], str],
) -> tuple[tuple[tuple[str, float], ...] | None, float, int]:
    """Extract compact match-key pairs and Field overflow from one bucket evaluation."""
    if not hist_entry:
        return None, 0.0, 0
    if current_normalized and not _is_field_normalized(hist_entry):
        return None, 0.0, 0
    hist_golfers = hist_entry.get("_all_golfers") or hist_entry.get("golfers") or []
    pairs = tuple(
        (match_key_fn(g.get("name") or ""), float(g["probability"]))
        for g in hist_golfers
        if g.get("probability") is not None
    )
    overflow = sum(
        float(ov["probability"])
        for ov in (hist_entry.get("overflow_outcomes") or [])
        if ov.get("probability") is not None
    )
    return pairs, overflow, len(hist_golfers)


def _plan_eval_points(
    window_snaps: Sequence[SnapshotReading],
    *,
    cutoff: datetime,
    series_end: datetime,
    commence_time: datetime | None,
    is_live: bool,
    pre_tee_max_buckets: int,
    max_buckets: int,
) -> tuple[list[tuple[datetime, datetime]], int]:
    """Build ordered ``(bucket_at, eval_at)`` half-open intervals.

    Once play starts, buckets during play remain fixed at 15-minute resolution
    (``900s``); coarsening applies strictly to pre-tee history.
    """
    play_start: datetime | None = None
    if commence_time is not None and _ensure_utc(commence_time) <= series_end:
        play_start = max(
            _ensure_utc(commence_time),
            series_end - timedelta(days=GOLF_TIMELINE_MAX_PLAY_DAYS),
        )
    elif is_live and window_snaps:
        play_start = max(cutoff, series_end - timedelta(days=4))

    if play_start is None:
        effective_start = max(cutoff, window_snaps[0].captured_at) if window_snaps else cutoff
        span_seconds = max(0.0, (series_end - effective_start).total_seconds())
        bucket_seconds = choose_bucket_seconds(
            span_seconds, started=False, max_buckets=max_buckets
        )
        ordered_bks = sorted(
            {(int(s.captured_at.timestamp()) // bucket_seconds) * bucket_seconds for s in window_snaps}
        )
        if len(ordered_bks) > max_buckets:
            ordered_bks = ordered_bks[-max_buckets:]
        eval_points = [
            (
                datetime.fromtimestamp(bk, tz=timezone.utc),
                datetime.fromtimestamp(bk + bucket_seconds, tz=timezone.utc),
            )
            for bk in ordered_bks
        ]
        return eval_points, bucket_seconds

    pre_snaps = [s for s in window_snaps if s.captured_at < play_start]
    play_snaps = [s for s in window_snaps if s.captured_at >= play_start]

    play_bks = sorted(
        {
            (int(s.captured_at.timestamp()) // GOLF_TIMELINE_PLAY_BUCKET_SECONDS)
            * GOLF_TIMELINE_PLAY_BUCKET_SECONDS
            for s in play_snaps
        }
    )
    play_points = [
        (
            datetime.fromtimestamp(bk, tz=timezone.utc),
            datetime.fromtimestamp(bk + GOLF_TIMELINE_PLAY_BUCKET_SECONDS, tz=timezone.utc),
        )
        for bk in play_bks
    ]
    first_play_bucket_at = play_points[0][0] if play_points else play_start

    pre_points: list[tuple[datetime, datetime]] = []
    pre_step = 3600
    if pre_snaps:
        pre_span = max(0.0, (play_start - pre_snaps[0].captured_at).total_seconds())
        pre_step = choose_bucket_seconds(
            pre_span, started=False, max_buckets=pre_tee_max_buckets
        )
        pre_bks = sorted({(int(s.captured_at.timestamp()) // pre_step) * pre_step for s in pre_snaps})
        for bk in pre_bks:
            b_at = datetime.fromtimestamp(bk, tz=timezone.utc)
            if b_at >= first_play_bucket_at:
                continue
            e_at = min(
                b_at + timedelta(seconds=pre_step),
                first_play_bucket_at,
                play_start,
            )
            pre_points.append((b_at, e_at))

    bucket_seconds = GOLF_TIMELINE_PLAY_BUCKET_SECONDS if (play_points or is_live) else pre_step
    return pre_points + play_points, bucket_seconds


def build_golf_blended_timeline(
    tourn_key: str,
    winner_markets: Sequence[DetachedMarket | Any],
    current_entry: Mapping[str, Any],
    snapshots: Sequence[SnapshotReading],
    *,
    build_entry: Callable[[str, list, dict], dict | None],
    match_key_fn: Callable[[str], str],
    top: int = 10,
    hours: int = 168,
    full_range: bool = False,
    commence_time: datetime | None = None,
    is_live: bool = False,
    max_reading_age: timedelta = timedelta(hours=48),
    full_max_days: int = GOLF_TIMELINE_FULL_MAX_DAYS,
    max_buckets: int = GOLF_TIMELINE_MAX_BUCKETS,
    pre_tee_max_buckets: int = GOLF_TIMELINE_PRE_TEE_MAX_BUCKETS,
    closed_bucket_cache: dict[tuple[int, int], ClosedBucketEntry] | None = None,
    build_stats: dict[str, int] | None = None,
    now: datetime | None = None,
) -> dict:
    """Build a ``ProbabilityTimelineResponse``-shaped blended golf history.

    Pure Python over detached data — safe to run inside ``asyncio.to_thread``.

    Timestamp convention (matching ``/api/futures/{id}/probability-timeline``):
    each point in ``timeline`` is stamped with its bucket's **start**
    (``bucket_at.isoformat()``) and carries the blended, field-normalized
    probabilities of the latest in-force readings strictly before bucket close
    (``[bucket_at, eval_at)``).

    Window bounds and bucket widths anchor to the tournament's own readings
    (``series_end = valid_snaps[-1].captured_at`` when snapshots exist), so a
    finished tournament returns the exact same timeline regardless of how many
    days later it is opened.
    """
    ref_now = _ensure_utc(now or datetime.now(timezone.utc))
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
            if s.probability is not None and _ensure_utc(s.captured_at) <= ref_now
        ),
        key=lambda s: s.captured_at,
    )

    series_end = valid_snaps[-1].captured_at if valid_snaps else ref_now
    effective_hours = max(1, min(int(hours), full_max_days * 24))
    full_floor = series_end - timedelta(days=full_max_days)

    if full_range:
        in_window_snaps = [s for s in valid_snaps if full_floor <= s.captured_at <= series_end]
        if in_window_snaps:
            cutoff = max(full_floor, in_window_snaps[0].captured_at)
            actual_hours = max(
                1,
                min(full_max_days * 24, int((series_end - cutoff).total_seconds() // 3600) + 1),
            )
        else:
            cutoff = full_floor
            actual_hours = effective_hours
    else:
        actual_hours = effective_hours
        cutoff = series_end - timedelta(hours=effective_hours)

    window_snaps = [s for s in valid_snaps if cutoff <= s.captured_at <= series_end]
    eval_points, bucket_seconds = _plan_eval_points(
        window_snaps,
        cutoff=cutoff,
        series_end=series_end,
        commence_time=commence_time,
        is_live=is_live,
        pre_tee_max_buckets=pre_tee_max_buckets,
        max_buckets=max_buckets,
    )

    current_golfers = list(current_entry.get("_all_golfers") or current_entry.get("golfers") or [])
    top_golfers = current_golfers[:top]
    top_name_by_key: dict[str, str] = {}
    for g in top_golfers:
        mk = match_key_fn(g.get("name") or "")
        if mk:
            top_name_by_key[mk] = g["name"]

    current_normalized = _is_field_normalized(dict(current_entry))

    timeline: list[dict] = []
    evaluated_count = 0
    reused_count = 0
    if winner_markets and eval_points and current_golfers:
        active: dict[int, tuple[tuple[float | None, float | None, float | None], datetime]] = {}
        snap_idx = 0
        total_snaps = len(valid_snaps)
        market_list = list(winner_markets)
        prev_sig: bytes | None = None
        prev_pairs: tuple[tuple[str, float], ...] | None = None
        prev_overflow = 0.0
        prev_hist_count = 0

        for bucket_at, eval_at in eval_points:
            while snap_idx < total_snaps and valid_snaps[snap_idx].captured_at < eval_at:
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

            sig = _snaps_signature(snaps_as_of)
            cache_slot = (int(bucket_at.timestamp()), int(eval_at.timestamp()))
            cached = closed_bucket_cache.get(cache_slot) if closed_bucket_cache is not None else None
            if cached is not None and cached[0] == sig:
                pairs, overflow, hist_count = cached[1], cached[2], cached[3]
                reused_count += 1
            elif prev_sig is not None and sig == prev_sig:
                pairs, overflow, hist_count = prev_pairs, prev_overflow, prev_hist_count
                reused_count += 1
            else:
                hist_entry = build_entry(tourn_key, market_list, snaps_as_of)
                evaluated_count += 1
                pairs, overflow, hist_count = _extract_bucket_pairs(
                    hist_entry,
                    current_normalized=current_normalized,
                    match_key_fn=match_key_fn,
                )

            prev_sig = sig
            prev_pairs = pairs
            prev_overflow = overflow
            prev_hist_count = hist_count
            if closed_bucket_cache is not None and eval_at <= ref_now:
                closed_bucket_cache[cache_slot] = (sig, pairs, overflow, hist_count)

            if pairs is None:
                continue

            outcomes_map: dict[str, float] = {}
            field_prob = overflow
            for mk, prob in pairs:
                canonical = top_name_by_key.get(mk)
                if canonical is not None:
                    outcomes_map[canonical] = round(prob, 6)
                else:
                    field_prob += prob

            if len(current_golfers) > top and (field_prob > 0 or len(top_name_by_key) < hist_count):
                outcomes_map["Field"] = round(min(field_prob, 1.0), 6)

            if outcomes_map:
                timeline.append({
                    "timestamp": bucket_at.isoformat(),
                    "outcomes": outcomes_map,
                })

    if build_stats is not None:
        build_stats["evaluated"] = evaluated_count
        build_stats["reused"] = reused_count
        build_stats["total_buckets"] = len(eval_points)

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
        "hours": effective_hours,
        "actual_hours": actual_hours,
        "top": top,
        "bucket_seconds": bucket_seconds,
        "coverage_hours": coverage_hours,
        "observation_times": observation_times,
        "timeline": timeline,
        "outcomes": outcomes_meta,
    }
