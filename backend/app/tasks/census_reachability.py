"""CAL-P012 (#1544) — count the reachability tiers CAL-P011 named.

Alex's ruling (2026-08-08) says the purged cohort must be visible *with its own
count*. CAL-P011 shipped the tier contract with the count `unavailable`, because
the population sits outside the coverage CTE chain and an unbounded aggregate
over ``futures_outcomes`` times out — a bare ``COUNT(*)`` on that table does not
return. This module supplies the count the honest way.

WHY A ROW-BOUNDED WINDOW AND NOT AN ID-WIDTH ONE. This distinction is the whole
design, and getting it wrong is not hypothetical — the first cut of this module
did. Measured against production, 2026-08-08:

    FIXED ID-WIDTH (20 M ids per window) — walked 12 windows over the id space:
        windows 1-3, 9, 10, 12   returned in ~7 s
        windows 4-8, 11          **STATEMENT TIMEOUT**

    ROW-BOUNDED (LIMIT n rows per window), aimed at id 60 M — inside the exact
    dense region that timed out above:
        scan = 200 K rows   bounds 2.58 s + tiers 5.16 s   (188,099 resolved)
        scan = 500 K rows   bounds 1.25 s + tiers 7.24 s   (470,744 resolved)

Outcome ids are NOT uniformly dense: a 20 M-id window is a few thousand rows in
one region and millions in another, so any fixed id width is simultaneously
wasteful at one end of the table and fatal at the other. ``LIMIT :scan`` makes
every window cost about the same regardless of where it lands, which is why
``_BOUNDS_SQL`` selects a fixed number of ROWS and derives ``(lo, hi)`` from
them rather than the reverse.

``DEFAULT_SCAN`` is therefore a ROW count, not an id span. Conflating the two is
the specific bug that measurement caught.

Bounded works; unbounded does not, at any phrasing — a bare ``COUNT(*)`` on
``futures_outcomes`` does not return. This follows ``census_winner_fields``
rather than inventing a second walking convention. **Do not "simplify" this into
a single aggregate** — it will pass review, pass tests against a small fixture
DB, and then time out against production, which is precisely how the CAL-P011
blocker came to exist.

ONE DEFINITION OF PURGED. The retention horizon comes from
``kalshi_retention.PROVABLY_PURGED_AGE_DAYS`` (CAL-P008, measured + dated), never
from a hand-rolled interval here — gotcha #35's whole lesson is that a range
written in prose cannot be consumed by a predicate, and a second copy of the
number is the same failure with extra steps.

ONE DEFINITION OF PRICED. The priced test mirrors ``coverage_universe`` in
``precompute_calibration`` exactly (``opening_probability IS NOT NULL AND > 0 AND
< 1``). If the two ever drift, the hinge in
``build_reachability_bridge`` diverges and the census says so. That divergence is
the check doing its job; resist the urge to "fix" it by loosening the hinge.
"""

from __future__ import annotations

from sqlalchemy import text

from app.utils.calibration_coverage_bridge import (
    PRICED_TIER,
    REACHABILITY_TIER_KEYS,
)
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

#: Outcome ROWS walked per call — NOT a span of ids (see the module docstring;
#: conflating the two produced timeouts in the table's dense regions). 500 K
#: measured at ~8.5 s end-to-end inside the densest region, which leaves room
#: under both the 20 s statement timeout and the 30 s router wall.
DEFAULT_SCAN = 500_000
MAX_SCAN = 2_000_000

#: Per-window statement timeout — fail this window fast rather than hold the
#: router wall open and return an H12 carrying no evidence.
_WINDOW_TIMEOUT = "20s"

#: Mirrors ``coverage_universe``. Kept as one string so the two cannot drift by
#: a stray edit to one branch of a copy-pasted predicate.
_PRICED = (
    "fo.opening_probability IS NOT NULL "
    "AND fo.opening_probability > 0 AND fo.opening_probability < 1"
)

_BOUNDS_SQL = """
    SELECT MIN(id) AS lo, MAX(id) AS hi, COUNT(*) AS n
    FROM (SELECT id FROM futures_outcomes WHERE id > :cursor
          ORDER BY id ASC LIMIT :scan) w
"""

# First match wins, mirroring the REACHABILITY_TIERS partition order. The CASE is
# written out rather than generated so the SQL reads as the contract does.
_TIERS_SQL = f"""
    SELECT
        COUNT(*) AS resolved_outcomes,
        COUNT(*) FILTER (WHERE {_PRICED}) AS priced_in_coverage,
        COUNT(*) FILTER (
            WHERE NOT ({_PRICED})
              AND fm.resolution_date IS NOT NULL
              AND fm.resolution_date < NOW() - make_interval(days => :purge_days)
        ) AS unpriced_provably_purged,
        COUNT(*) FILTER (
            WHERE NOT ({_PRICED})
              AND fm.resolution_date IS NOT NULL
              AND fm.resolution_date >= NOW() - make_interval(days => :purge_days)
        ) AS unpriced_recoverable,
        COUNT(*) FILTER (
            WHERE NOT ({_PRICED})
              AND fm.resolution_date IS NULL
        ) AS unpriced_unknown_age
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fo.id >= :lo AND fo.id <= :hi
      AND fm.status = 'resolved'
"""


def merge_windows(windows: list[dict]) -> dict[str, int]:
    """Sum per-window tier counts into one partition.

    Pure so the arithmetic is testable without a database. Every key in
    :data:`REACHABILITY_TIER_KEYS` is present even when no window reported it —
    a checked zero, which is a different claim from "unmeasured" and is exactly
    the distinction the bridge contract preserves.
    """
    totals = {key: 0 for key in REACHABILITY_TIER_KEYS}
    for w in windows:
        for key in REACHABILITY_TIER_KEYS:
            totals[key] += int(w.get(key) or 0)
    return totals


def is_complete_walk(windows: list[dict]) -> bool:
    """True only when the walk reached the end of the id space.

    A PARTIAL walk must never be published as a total. Its counts are real but
    its denominator is not the population, and a number that looks like a total
    while covering 60% of the rows is worse than no number at all — it is the
    same "an empty 200 is not an absence" error (gotcha #51) wearing a total's
    clothing.
    """
    return bool(windows) and bool(windows[-1].get("exhausted"))


async def census(
    session,
    apply: bool = False,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """Walk one bounded outcome-id window and count the reachability tiers.

    ``limit``   outcome ids to walk in this call.
    ``offset``  outcome-id cursor, exclusive. Pass the returned ``next_offset``
                to continue; omit to start at the beginning.
    ``apply``   ignored; this census never writes.
    """
    scan = min(int(limit or DEFAULT_SCAN), MAX_SCAN)
    cursor = int(offset) if offset is not None else 0

    await session.execute(text(f"SET LOCAL statement_timeout = '{_WINDOW_TIMEOUT}'"))

    bounds = (
        await session.execute(text(_BOUNDS_SQL), {"cursor": cursor, "scan": scan})
    ).mappings().first()

    lo, hi, walked = bounds["lo"], bounds["hi"], int(bounds["n"] or 0)

    if not walked:
        # End of the id space. Exhausted with zero rows is a COMPLETE walk of an
        # empty tail, not a failure — the caller needs that to stop looping.
        return {
            "census": "reachability-tiers",
            "ids_walked": 0,
            "window": None,
            "next_offset": None,
            "exhausted": True,
            "purge_horizon_days": PROVABLY_PURGED_AGE_DAYS,
            **{key: 0 for key in REACHABILITY_TIER_KEYS},
        }

    row = (
        await session.execute(
            text(_TIERS_SQL),
            {"lo": lo, "hi": hi, "purge_days": PROVABLY_PURGED_AGE_DAYS},
        )
    ).mappings().first()

    counts = {key: int(row[key] or 0) for key in REACHABILITY_TIER_KEYS}

    # The window is a partition too: the four tiers must account for every
    # resolved row the window saw. A mismatch means the CASE stopped being a
    # partition, and is reported rather than silently absorbed.
    resolved = int(row["resolved_outcomes"] or 0)
    summed = sum(counts.values())

    return {
        "census": "reachability-tiers",
        "ids_walked": walked,
        "window": {"lo": lo, "hi": hi},
        "next_offset": hi,
        "exhausted": walked < scan,
        "purge_horizon_days": PROVABLY_PURGED_AGE_DAYS,
        "resolved_outcomes": resolved,
        "partition_ok": summed == resolved,
        "partition_residual": resolved - summed,
        **counts,
    }


#: Redis key holding the last COMPLETE walk's totals. Only a complete,
#: reconciled walk is ever written here, so a reader never has to ask whether
#: what it found is a total or a fragment.
PUBLISHED_KEY = "calibration:reachability_census"

#: The published total goes stale rather than silently ageing: markets settle
#: and cross the horizon continuously, so a month-old count is a wrong count.
PUBLISHED_TTL_SECONDS = 60 * 60 * 30  # 30h — survives a missed daily refresh, not a missed week


def read_published_counts(redis_client) -> dict[str, int] | None:
    """The cached totals, or None. Never raises into a caller's critical path.

    Fail-open by design: a missing, unreadable, malformed or partial cache all
    return None, which routes the payload to the explicit ``unavailable``
    section. The one thing this must never do is hand back a number it cannot
    stand behind — ``precompute`` is on the critical path for the whole
    calibration payload and must not fail because a supporting census did.
    """
    import json

    if redis_client is None:
        return None
    try:
        raw = redis_client.get(PUBLISHED_KEY)
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    counts = data.get("counts")
    if not isinstance(counts, dict):
        return None
    # Every tier must be present and an honest int, or the cache is not a total.
    out: dict[str, int] = {}
    for key in REACHABILITY_TIER_KEYS:
        v = counts.get(key)
        if not isinstance(v, int) or isinstance(v, bool):
            return None
        out[key] = v
    return out


def tier_counts_for_bridge(windows: list[dict]) -> dict[str, int] | None:
    """The mapping ``build_coverage_census`` wants, or None if not publishable.

    Fail-closed on a partial walk and on any window whose own partition did not
    reconcile. ``None`` routes the payload to the explicit ``unavailable``
    section, which is the honest answer; a partial total is not.
    """
    if not is_complete_walk(windows):
        return None
    if any(w.get("partition_ok") is False for w in windows):
        return None
    totals = merge_windows(windows)
    # Sanity: the terminal tier cannot exceed the whole.
    if totals[PRICED_TIER] > sum(totals.values()):
        return None
    return totals


async def publish_full_census(session, redis_client=None) -> dict:
    """Walk the WHOLE id space, then publish the totals — all or nothing.

    Deliberately NOT wired to a beat (Invariant 6: a beat edit is a declared,
    serialized Integrator review). It is invocable so an operator or a future
    scheduled task can refresh the number; until something calls it, the payload
    keeps saying ``unavailable``, which is the honest state rather than a stale
    one.

    Publishes only on a COMPLETE, reconciled walk. A partial walk returns its
    partial counts to the caller for inspection but writes nothing.
    """
    import json

    windows: list[dict] = []
    cursor: int | None = 0
    # Hard bound so a cursor that stops advancing cannot spin forever. The
    # measured population needs ~11 windows; 200 is a runaway backstop, not a
    # budget anyone should reach.
    for _ in range(200):
        w = await census(session, offset=cursor)
        windows.append(w)
        if w.get("exhausted"):
            break
        nxt = w.get("next_offset")
        if nxt is None or (cursor is not None and int(nxt) <= int(cursor)):
            break  # cursor stuck — stop rather than loop
        cursor = int(nxt)

    counts = tier_counts_for_bridge(windows)
    published = False
    if counts is not None and redis_client is not None:
        try:
            redis_client.setex(
                PUBLISHED_KEY,
                PUBLISHED_TTL_SECONDS,
                json.dumps({"counts": counts, "horizon_days": PROVABLY_PURGED_AGE_DAYS}),
            )
            published = True
        except Exception:
            published = False

    return {
        "census": "reachability-tiers-full",
        "windows": len(windows),
        "complete": is_complete_walk(windows),
        "published": published,
        "counts": counts if counts is not None else merge_windows(windows),
        "publishable": counts is not None,
    }
