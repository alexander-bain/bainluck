#!/usr/bin/env python3
"""CAL-P121 — score a published cell's sigma on INDEPENDENT observations.

Ruling 134 note: this is a read-only instrument. It writes nothing, it imports
the frozen ``precompute_calibration`` chain rather than re-implementing it, and
``git diff origin/master -- backend/app/`` is empty on the branch that carries
it.

WHY THIS FILE EXISTS
--------------------
``calibration_scorecard.cell_se_pp(n) = 50/sqrt(n)`` feeds a cell's PUBLISHED
ROW COUNT into a binomial standard error, and ``SIGMA_GATE = 2.0`` decides from
it whether a cell is real work or noise. That is correct exactly when one row is
one independent forecast. On this board it repeatedly is not:

* CAL-P120 measured ``odds_api_bookmaker`` publishing one GAME as 5.8-17.8
  bookmaker rows carrying a BYTE-IDENTICAL outcome. Six board cells fell out of
  the queue.
* CAL-P114 3a noted ``kalshi/economics``'s 28,613 rows carry roughly 2,507
  markets of information, so criterion 3 read 7.8 sigma where the market count
  reads about 2.3. It was flagged for Alex and never wired.

Those are the SAME defect and CAL-P120's rail cannot answer the second one,
because its correction is a DEDUP: bookmaker rows are copies, so collapsing them
is exact. A Kalshi threshold ladder is not a copy. ``KXGOLDH-26AUG2815`` publishes
"gold above $3,340", "above $3,350", "above $3,360" as separate rungs with
DIFFERENT prices and DIFFERENT outcomes, all determined by one gold print. They
are correlated, not duplicated, and there is no grain at which they collapse
without inventing a price.

So the honest instrument is not a dedup, it is a CLUSTER BOOTSTRAP: resample the
MARKETS with replacement, recompute the cell's own ECE on each resample, and
read the spread. That measures the correlation instead of assuming a value for
it, and it degenerates to the right answers at both ends -- if rungs are
independent it reproduces the row-grain sigma, if they are perfectly correlated
it reproduces the market-count sigma.

WHAT IT PRINTS, AND WHY THREE NUMBERS AND NOT ONE
-------------------------------------------------
============  =====================================================
sigma_row     ``(ECE - bar) / (50/sqrt(n_rows))`` -- THE BOARD'S OWN
              NUMBER, reproduced so the correction is checkable
              against the table it corrects.
sigma_market  ``(ECE - bar) / (50/sqrt(n_markets))`` -- the
              perfect-within-market-correlation BOUND, which is the
              basis CAL-P114 3a quoted. Pessimistic by construction.
sigma_boot    ``(ECE - bar) / SE_cluster_bootstrap`` -- the MEASURED
              one, and the one a verdict should be read off.
============  =====================================================

Printing only the third would hide whether the correction is doing anything;
printing only the second repeats CAL-P114's unmeasured assumption with more
decimal places. The verdict line uses ``sigma_boot`` and says so.

THE RAIL IS NOT RE-IMPLEMENTED, IT IS EXTENDED BY ONE DIMENSION
---------------------------------------------------------------
Every SQL statement here is built by ``calibration_cell_exact.cell_sql`` and
executed by ``calibration_cell_exact.sweep`` -- the chunking, the split-on-
timeout recursion, the comment stripping and the payload self-check are that
file's, unmodified. This file adds ONE entry to its ``DIMENSIONS`` table,
``marketid``, whose key expression is ``d.market_id``. That is deliberate and it
is the whole reason the numbers below can be read against 6b/6c/6g: a
re-implementation would inherit an unmeasured drift between this bench and the
curve, which is the exact failure ``calibration_cell_exact`` was built to end.

A guard test asserts the registration is additive -- that every dimension the
rail shipped with is still present and still bound to the same expression.

THE BOOTSTRAP, STATED SO IT CAN BE ARGUED WITH
----------------------------------------------
Draw ``K`` markets with replacement from the cell's ``K`` markets, pool their
per-decile ``(n, winners, sum_price)`` triples, and fold the pooled bins with
``calibration_cell_exact.fold`` -- the producer's own ECE arithmetic, not a
paraphrase of it. Repeat ``--boot`` times. ``SE`` is the sample standard
deviation of the resampled ECEs.

Two properties a reader should hold this to:

1. **The point estimate does not move.** This instrument does not re-grade, re-
   price or re-bucket anything; ``ece`` on its output is the rail's own ``--by
   none`` value. If a cell's ECE changes here, something is wrong.
2. **It is seeded.** ``--seed`` defaults to 20260829 so two runs of the same
   cell on the same payload print the same SE. An unseeded bootstrap that moves
   a cell across ``SIGMA_GATE`` between runs is not a measurement.

Usage::

    python3 backend/scripts/calibration_cluster_sigma.py \\
        --source kalshi --category crypto --out artifacts/cal-p121/sigma.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calibration_cell_exact as cce  # noqa: E402
import calibration_scorecard as cs  # noqa: E402

#: The dimension this file adds to the rail's table. One published row's
#: cluster is its MARKET: on Kalshi that is one event ticker (one hour of gold,
#: one settlement of an index) whose rungs share a single realised outcome.
MARKETID_DIMENSION = ("d.market_id::text", "", "")

#: Registered at import so the guard test can assert it without running a sweep.
cce.DIMENSIONS.setdefault("marketid", MARKETID_DIMENSION)

#: Default resample count. 2,000 puts the Monte-Carlo error on the SE itself at
#: roughly 1.6% (1/sqrt(2*B)), which is an order of magnitude below the
#: correction this instrument exists to measure.
DEFAULT_BOOT = 2000

#: Fixed so the verdict is reproducible. See the module docstring.
DEFAULT_SEED = 20260829


def cluster_bins(by_key: dict) -> list[dict[int, dict]]:
    """One entry per market: ``{decile -> {n, w, sp}}``.

    The rail returns ``by_key[market_id][bucket] = {n, w, sp}`` already, so this
    is a shape change and not an aggregation -- no row is combined with a row it
    was not already combined with.
    """
    return [dict(bb) for bb in by_key.values()]


def bootstrap_ece(
    clusters: list[dict[int, dict]], boot: int, seed: int
) -> tuple[list[float], float]:
    """Cluster bootstrap of the cell's ECE. Returns (samples, SE in pp)."""
    rng = random.Random(seed)
    k = len(clusters)
    samples: list[float] = []
    for _ in range(boot):
        pooled: dict[int, dict] = defaultdict(lambda: {"n": 0, "w": 0, "sp": 0.0})
        for _ in range(k):
            for b, v in clusters[rng.randrange(k)].items():
                p = pooled[b]
                p["n"] += v["n"]
                p["w"] += v["w"]
                p["sp"] += v["sp"]
        _, ece, _ = cce.fold(pooled)
        if ece is not None:
            samples.append(ece)
    if len(samples) < 2:
        return samples, float("nan")
    mean = sum(samples) / len(samples)
    var = sum((s - mean) ** 2 for s in samples) / (len(samples) - 1)
    return samples, math.sqrt(var)


def percentile(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--width", type=int, default=cce.DEFAULT_WIDTH)
    ap.add_argument("--boot", type=int, default=DEFAULT_BOOT)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out")
    args = ap.parse_args()

    t0 = time.time()
    by_key, _ = cce.sweep(args.source, args.category, "marketid", args.width)
    took = time.time() - t0

    pooled = cce.pool(by_key)
    n, ece, gap = cce.fold(pooled)
    pn, pece, pgap, meta = cce.payload_cell(args.source, args.category)

    klass = cs.classify(args.source, args.category)
    bar = cs.CLASS_BARS_PP[klass]
    excess = (ece or 0.0) - bar

    clusters = cluster_bins(by_key)
    k = len(clusters)
    rows_per_cluster = n / k if k else float("nan")

    se_row = cs.cell_se_pp(n)
    se_market = cs.cell_se_pp(k)
    samples, se_boot = bootstrap_ece(clusters, args.boot, args.seed)

    sig_row = excess / se_row if se_row else None
    sig_market = excess / se_market if se_market else None
    sig_boot = excess / se_boot if se_boot and se_boot == se_boot else None

    print(
        f"{args.source}/{args.category}   (cluster sigma, {took:.0f}s sweep, "
        f"{args.boot} resamples, seed {args.seed})"
    )
    print(
        f"  curve generated {meta['generated_at']}  "
        f"population {meta['population_version']}"
    )
    print()
    print("  SELF-CHECK — the producer's own chain against the payload it produced")
    print(f"    {'exact replica':<16} n={n:>7}  ECE={ece:>6}  gap={gap:>+7}")
    print(f"    {'payload':<16} n={pn:>7}  ECE={pece:>6}  gap={pgap:>+7}")
    if pn:
        print(
            f"    {'delta':<16} n={n - pn:>+7} ({(n - pn) / pn * 100:+.2f}%)  "
            f"ECE={(ece or 0) - (pece or 0):+.2f}  "
            f"gap={(gap or 0) - (pgap or 0):+.2f}"
        )
    print()
    print("  CLUSTERS — one published row's independent unit is its MARKET")
    print(f"    published rows        {n:>8}")
    print(f"    distinct markets      {k:>8}")
    print(f"    rows per market       {rows_per_cluster:>8.2f}")
    print()
    print(
        f"  SIGMA — class {klass}, bar {bar} pp, ECE {ece} pp, excess {excess:+.2f} pp"
    )
    print(f"    {'basis':<34} {'SE pp':>8} {'sigma':>8}")
    print(f"    {'row grain (the board today)':<34} {se_row:>8.3f} " f"{sig_row:>8.2f}")
    print(
        f"    {'market grain (perfect-corr bound)':<34} {se_market:>8.3f} "
        f"{sig_market:>8.2f}"
    )
    print(
        f"    {'cluster bootstrap (MEASURED)':<34} {se_boot:>8.3f} " f"{sig_boot:>8.2f}"
    )
    print()
    lo, hi = percentile(samples, 0.025), percentile(samples, 0.975)
    print(f"    bootstrap ECE 95% interval  [{lo:.2f}, {hi:.2f}] pp")
    print(
        f"    design effect (SE_boot/SE_row)^2  "
        f"{(se_boot / se_row) ** 2 if se_row else float('nan'):.2f}"
    )
    print()
    established = sig_boot is not None and sig_boot >= cs.SIGMA_GATE
    print(
        f"  VERDICT  {'ESTABLISHED' if established else 'NOT ESTABLISHED'} "
        f"— measured sigma {sig_boot:.2f} against SIGMA_GATE {cs.SIGMA_GATE}"
    )
    if established and sig_row and sig_boot < sig_row:
        print(
            f"           the board reads {sig_row:.2f}; the cell survives the "
            f"correction with margin to spare"
        )
    elif not established:
        print(
            f"           the board reads {sig_row:.2f} on the same ECE — the "
            f"cell is over its bar on the point estimate and this sample "
            f"cannot distinguish it from the bar"
        )

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump(
                {
                    "source": args.source,
                    "category": args.category,
                    "seconds": round(took, 1),
                    "boot": args.boot,
                    "seed": args.seed,
                    "payload": {"n": pn, "ece": pece, "gap": pgap, **meta},
                    "exact": {"n": n, "ece": ece, "gap": gap},
                    "klass": klass,
                    "bar": bar,
                    "excess": round(excess, 2),
                    "clusters": k,
                    "rows_per_cluster": round(rows_per_cluster, 3),
                    "se": {"row": se_row, "market": se_market, "bootstrap": se_boot},
                    "sigma": {
                        "row": sig_row,
                        "market": sig_market,
                        "bootstrap": sig_boot,
                    },
                    "bootstrap_ci": [lo, hi],
                    "sigma_gate": cs.SIGMA_GATE,
                    "established": established,
                    # The cluster census itself, so the artifact can be checked
                    # rather than believed — and so a holdout split point for this
                    # cell can be read off the PUBLISHED population instead of
                    # estimated from the raw table, which on a cell the producer
                    # drops 80% of is a different population wearing its name.
                    "cluster_rows": {
                        str(k_): sum(v["n"] for v in bb.values())
                        for k_, bb in by_key.items()
                    },
                },
                fh,
                indent=2,
            )
        print(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
