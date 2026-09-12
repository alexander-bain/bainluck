#!/usr/bin/env python3
"""#5401 — measure the chunk boundaries ``calibration_population_move_5401`` uses.

WHY BOUNDARIES ARE MEASURED AND NOT GUESSED, AND WHY BY OUTCOMES.

The population CTEs have a cost cliff rather than a cost curve: a chunk either
answers in 1-2s or blows the 10s ``statement_timeout`` outright, and a timeout
costs its full wall clock and yields nothing. So the sweep is only as fast as
its boundaries are even, and evenness has to be measured in the unit that drives
the cost.

That unit is OUTCOMES, not markets. Cutting Kalshi into equal-MARKET chunks
(``ntile`` over ``futures_markets``) still death-spiralled: around
``event_id`` 12,080,xxx sit events carrying 16-17 markets and 200-315 outcomes
EACH, so a chunk holding its fair share of markets held many times its share of
outcomes, timed out, and split — 5 chunks yielding 170 rows in 54s. Weighting by
``COUNT(*)`` over ``futures_outcomes`` removes that skew at the source.

EVENT-ATOMICITY IS THE HARD CONSTRAINT. ``event_sizes`` is computed inside the
chunk filter, so an event split across two chunks is counted short, its
``event_size >= 3`` test flips, and its markets fall out of their grouped
``vm_id`` — changing which rows the measurement believes are published. Every
boundary here is therefore an ``event_id`` VALUE (markets carrying one) or an
``fm.id`` value among markets carrying NO ``event_id`` (which are ``m:``
singletons and cannot be split). Accumulating whole events into buckets, rather
than slicing a row-ordered list, is what makes that hold.

A chunk is capped on TWO axes, because outcome mass is not the only cost
driver: see :data:`MAX_KEY_WIDTH`. A 9.2M-wide span holding 138 markets timed
out repeatedly — in a sparse id region it is the WIDTH that flips the planner
off the index, whatever the mass says.

The top bound is deliberately open-ended so markets ingested after this
measurement are counted rather than silently dropped — the stale-``--max-id``
defect (47,767 Kalshi markets, 15.1% of the source) that motivated this file.

Usage::

    python3 backend/scripts/calibration_population_boundaries_5401.py \\
        --target-outcomes 2000 --out artifacts/cal-p1121/boundaries.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calibration_cell_exact import db_query  # noqa: E402

#: Above every real key, so the last chunk stays open-ended.
OPEN_TOP = 2_000_000_000

#: Outcome mass is not the only cost driver, and capping it alone is not enough.
#: MEASURED 2026-09-12: the chunk ``noev(34280187, 43517892]`` holds **138
#: markets** — nothing, by outcome mass, which is why the cumulative bucketing
#: put one boundary across the whole of it — and it TIMED OUT anyway, then again
#: through six levels of halving. Kalshi's id space has a ~18M-wide near-hole
#: between ~34M and ~52.7M, and a range that wide flips the planner off the
#: index and onto a scan regardless of how few rows it selects.
#:
#: So a chunk is bounded on BOTH axes: at most ``--target-outcomes`` of mass and
#: at most this much key width. Splitting a sparse span costs nothing (the extra
#: chunks return in milliseconds) whereas letting one through costs a full
#: statement timeout per halving, so this is deliberately well under the width
#: at which the flip was observed.
MAX_KEY_WIDTH = 2_000_000


def _cap_width(bounds: list[int], max_width: int) -> list[int]:
    """Subdivide any span wider than ``max_width`` into equal pieces.

    Operates on the boundary VALUES, so it cannot break event-atomicity: an
    event lives at a single ``event_id``, and inserting more cut points between
    two existing ones never puts one event on both sides of a cut.

    The open-ended top span is exempt -- capping it would emit a thousand empty
    chunks above the highest real key for no gain.
    """
    out: list[int] = [bounds[0]]
    for lo, hi in zip(bounds, bounds[1:]):
        if hi != OPEN_TOP and (hi - lo) > max_width:
            pieces = -(-(hi - lo) // max_width)  # ceil
            step = (hi - lo) // pieces
            out.extend(lo + step * i for i in range(1, pieces))
        out.append(hi)
    return out


_BOUNDS_SQL = """
WITH oc AS (
    SELECT {key} AS k, COUNT(*) AS w
    FROM futures_markets fm
    JOIN futures_outcomes fo ON fo.market_id = fm.id
    WHERE fm.source = 'kalshi' AND {scope}
    GROUP BY 1
),
c AS (
    SELECT k, SUM(w) OVER (ORDER BY k) AS cum FROM oc
)
-- `cum` is NUMERIC (Postgres SUM over bigint widens), so a bare `cum / target`
-- is FRACTIONAL division and buckets almost every event on its own -- which
-- surfaces only as the 1,000-row cap, i.e. as a silently truncated key space.
-- The ::bigint cast is what makes this integer division.
SELECT MAX(k) AS hi FROM c GROUP BY (cum::bigint / {target}) ORDER BY 1
"""


def _bounds(key: str, scope: str, target: int, floor: int) -> list[int]:
    sql = _BOUNDS_SQL.format(key=key, scope=scope, target=target)
    res = db_query(sql, limit=1000)
    rows = res.get("rows") or []
    # gotcha: the row cap is 1,000 and a capped answer is silently short -- here
    # it would silently TRUNCATE the sweep's key space, which is the same class
    # of defect as the stale --max-id this file exists to retire.
    if len(rows) >= 1000:
        raise RuntimeError(f"{key}: hit the 1,000-row cap -- raise --target-outcomes")
    vals = sorted({int(r[0]) for r in rows})
    if not vals:
        raise RuntimeError(f"{key}: no boundaries returned")
    # `floor` sits one BELOW the smallest real key because every range is
    # half-open on the value as (lo, hi]; the largest measured key is dropped in
    # favour of OPEN_TOP so late arrivals fall in the last chunk.
    return [floor] + vals[:-1] + [OPEN_TOP]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target-outcomes", type=int, default=2000)
    ap.add_argument("--max-key-width", type=int, default=MAX_KEY_WIDTH)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    ev = _cap_width(
        _bounds("fm.event_id", "fm.event_id IS NOT NULL", args.target_outcomes, 0),
        args.max_key_width,
    )
    nu = _cap_width(
        _bounds("fm.id", "fm.event_id IS NULL", args.target_outcomes, 0),
        args.max_key_width,
    )

    for name, v in (("event_id", ev), ("null_event_id", nu)):
        if v != sorted(v) or len(set(v)) != len(v):
            raise RuntimeError(f"{name}: bounds not strictly increasing")
        widest = max((hi - lo for lo, hi in zip(v, v[1:]) if hi != OPEN_TOP), default=0)
        if widest > args.max_key_width:
            raise RuntimeError(f"{name}: a {widest:,}-wide span survived the cap")

    out = {
        "_method": (
            "Cumulative-outcome bucketing over futures_markets JOIN "
            "futures_outcomes WHERE source='kalshi', target "
            f"{args.target_outcomes} outcomes per chunk. Bounds are KEY VALUES "
            "and ranges are half-open (lo, hi], so every market of an event "
            "lands in exactly one chunk and event_sizes is never counted short. "
            "Weighted by OUTCOMES, not markets: outcome density per event "
            "varies ~20x and is what drives the cost cliff."
        ),
        "target_outcomes": args.target_outcomes,
        "max_key_width": args.max_key_width,
        "event_id_bounds": ev,
        "null_event_id_bounds": nu,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n")
    print(
        f"event chunks: {len(ev) - 1}   event-less chunks: {len(nu) - 1}   "
        f"total: {len(ev) + len(nu) - 2}"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
