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
    """
    parts = member.split(":")
    if len(parts) < 2:
        return None
    try:
        latency = float(parts[1])
    except (TypeError, ValueError):
        return None
    bucket = parts[2] if len(parts) > 2 and parts[2] else "none"
    return latency, bucket
