"""Honest percentile math for the admin latency rail (#1500).

Pure functions, no I/O — the estimator and the minimum-sample rule are the two
things that made ``/api/admin/latency-stats`` report green through exactly the
tail it exists to measure, so they live here where they can be pinned by
fixtures.

The failure being fixed
-----------------------
The old estimator was ``idx = int(pct / 100 * (n - 1))``. At small n that index
collapses onto a LOW-order sample:

===  =========  =============================================
 n   p95 index  what was actually returned
===  =========  =============================================
 1   0          the only sample
 2   0          the **minimum**
 3   1          the median
10   8          the 9th of 10 (≈p90)
===  =========  =============================================

Production proof (Ops r324): ``/api/events/typeahead`` reported
``n=2 p50=1.2 p95=1.2 p99=1.2 max=12869.3`` — a p99 of 1.2 ms on an endpoint
whose slowest sample in the window was 12.9 seconds.

The fix has two halves, and both are needed:

1. **Nearest-rank** — ``ceil(pct/100 * n) - 1``, the standard definition, which
   can never resolve below its own rank.
2. **A minimum-sample rule** — nearest-rank at n=2 is *arithmetically* correct
   but still not a p95: two samples cannot describe a 95th percentile. Below
   ``min_samples_for(pct)`` the answer is ``None`` (unavailable), never a
   number. A missing measurement must read as UNKNOWN, not as a value.
"""

from __future__ import annotations

import json
import math
from typing import Optional, Sequence

# Absolute floor: one sample can describe no percentile but its own value.
_ABSOLUTE_MIN = 2


def min_samples_for(pct: float) -> int:
    """Smallest n at which ``pct`` is meaningful.

    A percentile is only meaningful once at least one sample can sit strictly
    above it — i.e. ``n >= 100 / (100 - pct)``. That yields p50→2, p90→10,
    p95→20, p99→100: the same thresholds a statistician would demand, derived
    rather than hand-picked.
    """
    if pct <= 0:
        return 1
    if pct >= 100:
        return _ABSOLUTE_MIN
    return max(_ABSOLUTE_MIN, math.ceil(100.0 / (100.0 - pct)))


def percentile_nearest_rank(data: Sequence[float], pct: float) -> Optional[float]:
    """Nearest-rank percentile of an ASCENDING-sorted ``data``.

    Returns ``None`` for an empty sequence. Does NOT apply the minimum-sample
    rule — that is a reporting policy and lives in :func:`percentile_or_none`,
    so the raw estimator stays independently testable.
    """
    n = len(data)
    if n == 0:
        return None
    idx = math.ceil(pct / 100.0 * n) - 1
    idx = max(0, min(n - 1, idx))
    return float(data[idx])


def percentile_or_none(data: Sequence[float], pct: float) -> Optional[float]:
    """Nearest-rank percentile, or ``None`` when n is too small to support it."""
    if len(data) < min_samples_for(pct):
        return None
    value = percentile_nearest_rank(data, pct)
    return None if value is None else round(value, 1)


def summarize(data: Sequence[float]) -> dict:
    """Percentile summary for one already-collected sample population.

    Always reports ``n`` beside the percentiles, and reports each percentile's
    own ``min_samples`` requirement so a ``null`` is self-explaining rather than
    looking like a broken field.
    """
    ordered = sorted(float(x) for x in data)
    n = len(ordered)
    summary = {
        "n": n,
        "p50_ms": percentile_or_none(ordered, 50),
        "p95_ms": percentile_or_none(ordered, 95),
        "p99_ms": percentile_or_none(ordered, 99),
        "min_samples": {
            "p50": min_samples_for(50),
            "p95": min_samples_for(95),
            "p99": min_samples_for(99),
        },
    }
    if n:
        summary["max_ms"] = round(ordered[-1], 1)
        summary["min_ms"] = round(ordered[0], 1)
    else:
        summary["max_ms"] = None
        summary["min_ms"] = None
    return summary


def parse_sample_member(member: str) -> Optional[tuple[float, str]]:
    """Parse a latency sorted-set member into ``(latency_ms, cache_bucket)``.

    Member format is ``"{timestamp}:{latency_ms}[:{cache_bucket}]"``. The
    two-field form is the legacy shape written before #1500 and still present in
    the rolling window for up to an hour after deploy, so it must parse rather
    than be dropped — dropping it would silently shrink n right when the new
    percentiles are being validated. Returns ``None`` for an unparseable member.

    Non-finite guard (r329 finding B1, ``production-unmeasured``): bare
    ``float()`` happily accepts ``"nan"`` and ``"inf"``. The current writer
    cannot produce either — ``duration_ms`` comes from ``perf_counter()`` — but
    if one ever entered, the blast radius is the WHOLE rail, not one bad row: a
    NaN makes ``sorted()`` ordering undefined (silently wrong p50/max) and an
    inf raises in Starlette's ``json.dumps(allow_nan=False)`` at render time,
    turning every endpoint's numbers into an opaque 500.
    """
    parts = member.split(":")
    if len(parts) < 2:
        return None
    try:
        latency = float(parts[1])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(latency):
        return None
    bucket = parts[2] if len(parts) > 2 and parts[2] else "none"
    return latency, bucket


# ---------------------------------------------------------------------------
# Slow-event forensics (#1459 / LAT-P011)
# ---------------------------------------------------------------------------
#
# Why this exists, in one paragraph, because three queues paid for its absence:
#
# The rail above answers "how slow was /api/feed in the last hour". It cannot
# answer "WHY was that one request slow", because it keeps only
# ``timestamp:latency:cache_bucket`` — no stage attribution — for 60 minutes.
# So LAT-P008, LAT-P009 and LAT-P011 each hand-ran a spaced benchmark in a
# single window and each got a DIFFERENT answer: 2 spikes in 23 (9%), 6 in 59
# (10%), and then 1 in 345 (0.3%) over a full clock hour. At 0.3% the queue's
# own acceptance bar of "capture >=8 spikes" needs ~2,700 hand-fired requests.
# The tail is episodic, so catching it by hand is a matter of luck, and three
# refuted hypotheses is what luck bought.
#
# A tail event already carries its own explanation: ``X-Feed-Stages`` names the
# per-stage cost, and the middleware sees it on the way out. Persisting the
# slow ones into a small bounded ring turns "sit and re-run the benchmark until
# the tail happens" into a read. The ring is deliberately tiny — Redis here is
# Premium-0 / 50 MB / allkeys-lru at ~62%, where an oversized working set evicts
# COLD keys regardless of TTL (r320 lost the grid-sentinel verdict that way).

# Default threshold. 5s is the same boundary the middleware already used for its
# slow-request RSS log, so this adds a record where a warning already fired.
SLOW_EVENT_MS_DEFAULT = 5000

# Ring size. ~500 records x ~300 B is ~150 KB against a 50 MB instance.
SLOW_EVENT_MAX_DEFAULT = 500

# Hard cap on the persisted stage string. The header is ours, but a bounded
# writer is the difference between a rounding error and an eviction event.
_STAGES_MAX_CHARS = 400
_PATH_MAX_CHARS = 120


def dominant_stage(stages: str) -> Optional[tuple[str, float]]:
    """The most expensive TOP-LEVEL stage in an ``X-Feed-Stages`` string.

    Format is ``"futures=3941.24,concepts=3543.46,futures.market_load=1623.38"``.
    Sub-stages are dotted (``futures.market_load``) and are *already counted
    inside* their parent, so including them would double-count and can crown a
    child over its own parent. Only undotted names compete.

    Returns ``(name, ms)``, or ``None`` when nothing parses — an unparseable
    string must read as "no attribution", never as a fabricated stage.
    """
    best: Optional[tuple[str, float]] = None
    for part in (stages or "").split(","):
        name, _, raw = part.partition("=")
        name = name.strip()
        if not name or "." in name:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        if best is None or value > best[1]:
            best = (name, value)
    return best


def build_slow_event(
    *,
    timestamp: float,
    path: str,
    duration_ms: float,
    cache_bucket: str,
    stages: Optional[str] = None,
    rss_mb: Optional[float] = None,
    split: Optional[dict] = None,
) -> str:
    """Serialise one tail observation for the slow-event ring.

    JSON rather than the colon-delimited member form used above: this record has
    optional fields and a free-text stage string, and ``parse_sample_member``
    already shows what positional parsing costs once a field becomes optional.

    ``split`` (#1917, LAT-P070) carries the router-queue / app / DB attribution
    from :mod:`app.utils.request_timing`. It rides the tail ring rather than a
    new key family for the same reason the cache bucket does — Redis here is
    Premium-0 / 50 MB / allkeys-lru — and it is what turns the tail from a
    stakeout into a read: a rare 15 s golf request records WHY it was 15 s at the
    moment it happens, instead of needing a loaded window to be re-created by
    hand. Only the attribution fields are kept; the display-only ones are not.
    """
    record = {
        "t": round(float(timestamp), 3),
        "path": (path or "")[:_PATH_MAX_CHARS],
        "ms": round(float(duration_ms), 1),
        "cache": cache_bucket or "none",
    }
    if stages:
        record["stages"] = stages[:_STAGES_MAX_CHARS]
        top = dominant_stage(record["stages"])
        if top is not None:
            record["top_stage"], record["top_stage_ms"] = top[0], round(top[1], 1)
    if rss_mb is not None and math.isfinite(rss_mb):
        record["rss_mb"] = round(float(rss_mb), 1)
    if isinstance(split, dict):
        for key in ("db_ms", "app_ms", "router_queue_ms", "queries", "max_query_ms"):
            value = split.get(key)
            # `None` means UNUSABLE and is written as such — dropping the key
            # would let a reader default it to 0 and conclude the router took no
            # time, which is gotcha #53's exact shape.
            if value is None:
                record[key] = None
                continue
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                record[key] = value
    return json.dumps(record, separators=(",", ":"), allow_nan=False)


def parse_slow_event(raw) -> Optional[dict]:
    """Parse one ring entry back into a dict, or ``None`` if it is unusable.

    Tolerates ``bytes`` (redis-py without ``decode_responses``) and refuses
    anything that is not a JSON object carrying a finite ``ms`` — a corrupt
    entry must drop out of the report rather than render as a null-filled row
    that reads like a real tail event.
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(raw, str):
        return None
    try:
        record = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    try:
        ms = float(record.get("ms"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(ms):
        return None
    record["ms"] = ms
    return record


def summarize_slow_events(records: Sequence[dict]) -> dict:
    """Aggregate the ring into the shape the next latency queue actually needs.

    Namely: how many tail events, over what wall-clock span, and **which stage
    dominated them** — the attribution the rail could not previously give, and
    the reason each prior queue had to re-run a benchmark to guess.
    """
    usable = [r for r in records if isinstance(r, dict) and "ms" in r]
    summary: dict = {"n": len(usable), "by_top_stage": {}, "by_cache": {}}
    if not usable:
        summary["oldest_ts"] = None
        summary["newest_ts"] = None
        summary["max_ms"] = None
        return summary
    times = [float(r["t"]) for r in usable if isinstance(r.get("t"), (int, float))]
    summary["oldest_ts"] = min(times) if times else None
    summary["newest_ts"] = max(times) if times else None
    summary["max_ms"] = round(max(float(r["ms"]) for r in usable), 1)
    for record in usable:
        stage = record.get("top_stage") or "unattributed"
        bucket = summary["by_top_stage"].setdefault(stage, {"n": 0, "max_ms": 0.0})
        bucket["n"] += 1
        bucket["max_ms"] = round(max(bucket["max_ms"], float(record["ms"])), 1)
        cache = record.get("cache") or "none"
        summary["by_cache"][cache] = summary["by_cache"].get(cache, 0) + 1
    return summary
