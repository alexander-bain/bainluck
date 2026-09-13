#!/usr/bin/env python3
"""#5401 — fold ONE cell by ``opening_source`` through the PRODUCER'S OWN chain.

WHY THIS EXISTS. #5401 measured that ``futures_outcomes.opening_source`` splits
high-confidence Kalshi legs into a well-calibrated cohort (``bid_ask_midpoint``,
90-99% at a mean price of ~0.96) and two fallback cohorts that are not
(``first_snapshot`` and no recorded basis at all, 0.1-61%). Every number in that
issue is measured on the RAW resolved-legs population.

The published calibration population is a PIPELINE, not a ``WHERE`` clause —
``kalshi/golf`` runs 73,970 -> 38,252 -> 34,774 -> 31,296 -> 22,074 — and
several of the legs #5401 names are already removed by ``is_golf_placeholder``,
the liquidity gate, or the representative rules before they can reach a reader.
So the raw deficit CANNOT be quoted at a cell, and the repair's expected
population move CANNOT be declared, until the same split is taken INSIDE the
serving window. That is this file's whole job.

It is the CAL-P114 instrument pointed at a different question: it calls
``_calibration_population_ctes()`` from the producer, appends the ``deduped``
precedence ladder as a CASE (borrowed verbatim from
``fold_dedup_verdict_cell.py``), and groups the result by opening basis rather
than by leg side. ``kept_*`` verdicts are the arm a reader sees.

Read the ``kept`` rows and nothing else when sizing the repair: an excluded leg
is already not in the curve, and counting it would over-state the ship.

Usage::

    python3 backend/scripts/calibration_fold_opening_source.py \\
        --source kalshi --category golf \\
        --out artifacts/cal-p1118/opening-source-kalshi-golf.json

CHUNKING IS NOT NEUTRAL — READ THIS BEFORE TRUSTING A NUMBER FROM HERE.
``event_sizes`` (and ``group_sizes``) are computed INSIDE ``market_info_extra``,
so an event whose markets straddle an ``fm.id`` chunk boundary is counted short,
its ``event_size >= 3`` test flips, and its markets drop out of their grouped
``vm_id`` into singletons — changing ``is_grouped``, ``vm_stats``,
``field_completeness`` and the ``deduped`` ladder, i.e. changing which rows the
fold believes are published. Measured on Kalshi 2026-09-12: 4,553 of 13,782
event-groups of size >= 3 span more than 100k ids and 1,288 span more than 1M
(max span 58.7M), so the default 1M width splits them by construction, and
adaptive splitting on timeout makes the answer depend on where the timeouts
happened. Per-CELL folds are usually safe from this (a small category's events
rarely straddle), but a SOURCE-WIDE number must not be taken with this
instrument — use ``calibration_population_move_5401.py``, which partitions on
the ``event_id`` VALUE so an event can never be split.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks.precompute_calibration import (  # noqa: E402
    _calibration_population_ctes,
)

from calibration_cell_exact import (  # noqa: E402
    _strip_sql_comments,
    db_query,
)
from fold_dedup_verdict_cell import VERDICT_CASE  # noqa: E402

#: The band #5401 is about. A fallback-priced leg below this is not the defect —
#: the claim is specifically that near-certainty is being published off no book.
HIGH_BAND = 0.80

#: The two ways to cut the cell, and the reason there are two.
#:
#: ``provenance`` groups by ``futures_outcomes.opening_source`` — the column that
#: FOUND the cohort (CAL-P1118 F1). It is a write-path artifact, though: an
#: untagged leg is one the INSERT arm never named, not one priced badly on
#: purpose, and two readings of the tag were refuted by measurement (F4).
#:
#: ``writer_bar`` groups by whether the leg EVER had a snapshot meeting the
#: Kalshi poller's own opening-write condition (``app/tasks/kalshi.py``,
#: ``has_real_trading``). That is a claim about the row rather than about our
#: bookkeeping — *the curve must not publish an opening the writer itself would
#: have refused to record* — and on ``kalshi/golf`` it captures 85% of the miss
#: for less than half the population move (F6b). Keep both: the provenance cut
#: is how the cohort is located, the writer bar is what a repair may key on.
SPLITS = ("provenance", "writer_bar")

#: `app/tasks/kalshi.py` `has_real_trading`, transcribed. Keep the two in sync:
#: `tests/test_opening_source_named_5401.py` asserts this string still matches
#: the writer's own literals, so a poller that moves its bar breaks the test
#: rather than silently re-scoping every measurement taken with this script.
WRITER_BAR_EXISTS = """EXISTS (
        SELECT 1 FROM futures_odds_snapshots fos
        WHERE fos.outcome_id = ro.outcome_id
          AND fos.yes_bid > 0
          AND fos.yes_ask IS NOT NULL
          AND (fos.yes_ask - fos.yes_bid) < 0.50)"""

SPLIT_SQL = {
    "provenance": "COALESCE(fo2.opening_source, '(none)')",
    "writer_bar": (
        f"CASE WHEN {WRITER_BAR_EXISTS}\n"
        "            THEN 'meets_writer_bar' ELSE 'below_writer_bar' END"
    ),
}

#: ``--max-id``'s old default was the literal ``60_097_325``, measured once and
#: then left to rot: by 2026-09-12 it excluded 47,767 of 316,132 Kalshi markets
#: — 15.1% of the source, including 99% of the ``other`` category — and a sweep
#: at defaults reported the short answer with no sign that anything was missing.
#: A bound over a table that only grows has to be READ, not remembered.
def measured_max_id(source: str) -> int:
    """One past the highest ``futures_markets.id`` this source currently has."""
    res = db_query(
        f"SELECT MAX(id) AS hi FROM futures_markets WHERE source = '{source}'"
    )
    rows = res.get("rows") or []
    if not rows or rows[0][0] is None:
        raise RuntimeError(f"no futures_markets rows for source={source!r}")
    return int(rows[0][0]) + 1



#: ``--category`` value that folds EVERY category of the source in one pass and
#: carries the category as a result column. A repair keyed on a source-wide
#: predicate — the writer bar is one — cannot be sized on the cell that motivated
#: it: the same rule runs on every other cell of that source, and the question
#: "does it damage a cell that is currently healthy?" is only answerable across
#: all of them. One pass also gives the source-wide population move a
#: ``CALIBRATION_POPULATION_DECLARATION`` needs.
ALL_CATEGORIES = "all"


def cell_sql(source: str, category: str, lo: int, hi: int,
             split: str = "provenance") -> str:
    every = category == ALL_CATEGORIES
    category_filter = (
        "" if every
        else f"AND COALESCE(fm.llm_sport_category, 'uncategorized') "
             f"= '{category}' "
    )
    pop = _calibration_population_ctes(
        market_info_extra=(
            f"AND fm.source = '{source}' "
            + category_filter
            + f"AND fm.id >= {lo} AND fm.id < {hi}"
        )
    )
    # `normalized` carries the cell's category as `ro.category` (it comes down
    # from the `cv` join), so folding every category needs no extra join.
    category_select = "ro.category" if every else f"'{category}'"
    return _strip_sql_comments(
        "WITH " + pop + f"""
SELECT {SPLIT_SQL[split]} AS opening_source,
       {VERDICT_CASE} AS verdict,
       CASE WHEN ro.adj_opening_probability >= {HIGH_BAND}
            THEN 'hi' ELSE 'lo' END AS band,
       {category_select} AS category,
       COUNT(*) AS n,
       COUNT(*) FILTER (WHERE ro.is_winner) AS won,
       ROUND(SUM(ro.adj_opening_probability)::numeric, 3) AS implied
FROM normalized ro
LEFT JOIN mode_prices mp
  ON mp.vm_id = ro.vm_id AND mp.source = ro.source
  AND mp.mode_price = ro.adj_opening_probability
JOIN futures_outcomes fo2 ON fo2.id = ro.outcome_id
GROUP BY 1, 2, 3, 4
""".strip())


def _print_per_cell_effect(out_rows: list[dict]) -> None:
    """Per-cell before/after for a source-wide writer-bar cut.

    The ratio is winners / implied winners on the PUBLISHED (``kept_*``) rows —
    the accuracy page's own number, where 1.0 is perfect and the board control
    sits at 0.982. ``after`` drops the below-bar cohort.

    Printed because a source-wide predicate has to be judged on the cells it was
    NOT written for: a rule that repairs golf and wrecks baseball is not a rule.
    """
    # category -> [n, won, implied, n_below, won_below, implied_below]
    cells: dict[str, list[float]] = defaultdict(lambda: [0, 0, 0.0, 0, 0, 0.0])
    for r in out_rows:
        if not r["verdict"].startswith("kept"):
            continue
        c = cells[r["category"]]
        c[0] += r["n"]
        c[1] += r["won"]
        c[2] += r["implied"]
        if r["opening_source"] == "below_writer_bar":
            c[3] += r["n"]
            c[4] += r["won"]
            c[5] += r["implied"]

    print(f"\n-- PER-CELL EFFECT OF THE WRITER-BAR CUT (published rows)")
    print(f"{'category':>22} {'n':>8} {'cut%':>6} {'before':>7} {'after':>7} "
          f"{'move':>7}")
    rows = []
    for cat, (n, won, implied, nb, wb, ib) in cells.items():
        if not n or not implied:
            continue
        n_after = n - nb
        implied_after = implied - ib
        before = won / implied
        after = (won - wb) / implied_after if implied_after > 0 else float("nan")
        rows.append((n, cat, n, 100.0 * nb / n, before, after,
                     after - before, n_after))
    for _, cat, n, cutpct, before, after, move, n_after in sorted(
            rows, reverse=True):
        flag = ""
        # A cell the cut MOVES AWAY from 1.0 is the damage case this table
        # exists to surface; 0.02 is a tenth of golf's own miss, not a ruling.
        if abs(after - 1.0) > abs(before - 1.0) + 0.02:
            flag = "  <-- moves AWAY from 1.0"
        print(f"{cat:>22} {int(n):>8} {cutpct:>5.1f}% {before:>7.3f} "
              f"{after:>7.3f} {move:>+7.3f}{flag}")

    tot_n = sum(c[0] for c in cells.values())
    tot_cut = sum(c[3] for c in cells.values())
    print(f"\nsource-wide published population move: "
          f"{int(tot_cut):,} of {int(tot_n):,} = "
          f"{100.0 * tot_cut / tot_n:.2f}% "
          f"(this is the number a POPULATION_DECLARATION states, and it is "
          f"the SOURCE's share -- scale it by the source's share of the whole "
          f"population before declaring it)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--width", type=int, default=1_000_000)
    ap.add_argument("--min-id", type=int, default=1)
    ap.add_argument("--max-id", type=int, default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", choices=SPLITS, default="provenance")
    args = ap.parse_args()
    if args.max_id is None:
        args.max_id = measured_max_id(args.source)
        print(f"max-id measured: {args.max_id:,}")

    stack: list[tuple[int, int]] = []
    lo = args.min_id
    while lo < args.max_id:
        hi = min(lo + args.width, args.max_id)
        stack.append((lo, hi))
        lo = hi
    stack.reverse()

    started = time.monotonic()
    # (opening_source, verdict, band, category) -> [n, won, implied]
    acc: dict[tuple[str, str, str, str], list[float]] = defaultdict(
        lambda: [0, 0, 0.0])
    chunks = 0
    irreducible = 0
    while stack:
        lo, hi = stack.pop()
        try:
            res = db_query(
                cell_sql(args.source, args.category, lo, hi, args.split))
        except Exception as exc:  # QueryTimeout and friends -> split
            if (hi - lo) <= 25:
                print(f"  [{lo}..{hi}) IRREDUCIBLE {exc}", flush=True)
                irreducible += 1
                continue
            mid = lo + (hi - lo) // 2
            stack.append((mid, hi))
            stack.append((lo, mid))
            continue
        rows = res.get("rows") or []
        # gotcha: the row cap is 1,000 and a capped answer is silently short.
        if len(rows) >= 1000:
            raise RuntimeError(f"[{lo}..{hi}) hit the 1,000-row cap")
        for opening_source, verdict, band, category, n, won, implied in rows:
            cell = acc[(opening_source, verdict, band, category)]
            cell[0] += int(n)
            cell[1] += int(won)
            cell[2] += float(implied or 0.0)
        chunks += 1
        if chunks % 10 == 0:
            print(f"  {chunks} chunks, id<{hi}, "
                  f"{time.monotonic() - started:.0f}s", flush=True)

    out_rows = [
        {"opening_source": k[0], "verdict": k[1], "band": k[2],
         "category": k[3],
         "n": int(v[0]), "won": int(v[1]), "implied": round(v[2], 2)}
        for k, v in sorted(acc.items())
    ]
    out = {
        "cell": f"{args.source}/{args.category}",
        "split": args.split,
        "high_band": HIGH_BAND,
        "elapsed_s": round(time.monotonic() - started, 1),
        "irreducible_chunks": irreducible,
        "rows": out_rows,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")

    print(f"\n{out['cell']}  split={args.split}  {out['elapsed_s']}s  "
          f"irreducible={irreducible}")
    print(f"{'basis':>18} {'band':>5} {'n':>7} {'won':>6} {'implied':>9} "
          f"{'win%':>7} {'impl%':>7}")
    for scope in ("kept", "excluded"):
        print(f"-- {scope.upper()} (verdicts {'kept_*' if scope == 'kept' else 'x*'})")
        agg: dict[tuple[str, str], list[float]] = defaultdict(
            lambda: [0, 0, 0.0])
        for r in out_rows:
            is_kept = r["verdict"].startswith("kept")
            if is_kept != (scope == "kept"):
                continue
            cell = agg[(r["opening_source"], r["band"])]
            cell[0] += r["n"]
            cell[1] += r["won"]
            cell[2] += r["implied"]
        for (basis, band), (n, won, implied) in sorted(agg.items()):
            if not n:
                continue
            print(f"{basis:>18} {band:>5} {int(n):>7} {int(won):>6} "
                  f"{implied:>9.1f} {100.0 * won / n:>6.1f}% "
                  f"{100.0 * implied / n:>6.1f}%")

    if args.category == ALL_CATEGORIES and args.split == "writer_bar":
        _print_per_cell_effect(out_rows)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
