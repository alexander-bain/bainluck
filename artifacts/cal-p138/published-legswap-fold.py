"""CAL-P138 — CAL-P137's leg-swap class, folded through the PUBLISHED curve.

CAL-P137 found that a large slice of the Polymarket O/U book is condemned by the
monotonicity law because our stored prices are on the wrong leg, and then said
plainly that it could not weigh the finding against anything: every number in it
is a RAW-CELL count, and lesson 19 says a cell census is not a published-
population census. It parked the sizing as CAL-P137-1 and the composition of the
families no leg swap can fix as CAL-P137-3.

This is both, on one instrument. The partition comes from
:mod:`legswap_classes`, entirely offline from CAL-P137's cached rows; the
population comes from ``_calibration_population_ctes`` — the producer's own
chain, imported from the frozen file rather than re-implemented — through
``calibration_cell_exact``'s existing chunking, splitting, self-check and
payload-comparison machinery. No shipped file is touched.

WHY THE DIMENSION IS ``market_id`` AND NOT THE ARMS, WHICH IS NOT A STYLE CHOICE
---------------------------------------------------------------------------------
The obvious build is a per-chunk dimension carrying the arms as id arrays, the
way ``mono_dim`` and ``truth_dim`` do. Measured, that shape does not fit here:
eight arms over ``polymarket/baseball`` renders **58,230 characters** of SQL at
the default 1M chunk width against a 60,000-character cap, so almost every chunk
splits on LENGTH before it is even sent, and the one chunk measured took 26 s for
250,000 ids — roughly 1.7 hours per cell, for one fixed partition.

Folding on ``d.market_id`` instead costs one small static dimension, needs no
arrays at all, and moves EVERY arm question offline: the arms, the holdout, the
flip counterfactual and CAL-P137-3's composition all become re-reads of one
cached fold rather than another production sweep each. The population is
identical either way — same chain, same chunking, same ``deduped`` — and the
proof of that is the self-check this file prints at the top of every run: the
pooled market-grain fold against ``payload_cell``, which is exactly the check
``calibration_cell_exact`` was built around.

🔴 WHY ECE AND NOT GAP IS THE READING HERE, AND IT IS NOT A PREFERENCE.
A leg-assignment defect moves a price from ``p`` to ``1 - p``. Read the
producer: ``deduped``'s binary branch is ``ELSE ro.rn = 1``, and ``rn`` orders by
``ABS(fo.opening_probability - 0.5)`` — so a two-sided market publishes exactly
ONE leg, and for a pair summing to one the two legs are EQUIDISTANT from 0.5 and
the tie falls to ``fo.id``. Which half of a swapped pair reaches the curve is
therefore arbitrary, and across many markets the signed error cancels: gap is
close to blind to this defect by construction. ECE is not — it is computed per
bucket, and a swapped pair puts a loser in bucket 9 and a winner in bucket 0. A
reader who scans the gap column here will conclude the class is fine.

🔴 THE ARM ASSIGNMENT IS LEAKAGE-FREE; THE READING OF IT IS NOT A RULE.
Nothing in :mod:`legswap_classes` touches ``is_winner`` — it sees names and
prices only. That makes the partition legal as a rule predicate, and this file
still proposes no rule, for CAL-P137 §7's reason: an exclusion here would buy a
calibration cell by deleting the evidence of a defect that is also wrong on the
event page, the card and the blend. What the fold decides is whether the defect
is worth REPAIRING — which needs its size on the published population, which is
the number nobody has had.

⚠️ TWO SEAMS, NAMED RATHER THAN SMOOTHED.
1. The partition is computed on ``COALESCE(calibration_probability,
   opening_probability)`` — CAL-P136's and CAL-P137's price. The fold reports
   ``adj_opening_probability``, which is that same coalesce after the producer's
   field normalization. On a two-sided O/U market the two should be equal (an
   O/U pair is not a ``mex_field`` candidate), but that is an expectation and
   not a measurement, so ``mean_p`` is printed per arm next to the partition's
   own price so a divergence is visible rather than absorbed.
2. The partition is computed from a cache pulled at CAL-P137's clock. Rows
   created since then land in ``z_not_in_a_ladder`` regardless of their shape.
   ``verify_against_p136`` measured that drift at 43 rows in 190,198 on the
   largest cell; it is reported again here as ``cache_age_rows`` rather than
   assumed to have stayed small.

Usage::

    source ~/.claude/.env && python3 artifacts/cal-p138/published-legswap-fold.py \\
        baseball soccer
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend", "scripts"))

import calibration_cell_exact as cce  # noqa: E402

import legswap_classes as LC  # noqa: E402
from pull_eras import verify_against_p136  # noqa: E402

#: The market-grain dimension. Registered into ``calibration_cell_exact``'s own
#: table rather than copied out of it, so the chunking, the split-on-cap, the
#: split-on-timeout and the payload self-check are all the shipped instrument's
#: and this file owns none of them.
cce.DIMENSIONS["marketid"] = ("d.market_id::text", "", "")

#: The holdout edges the σ-sweep measured (``artifacts/calibration-scorecard/
#: measured-sigma.json``), one per cell: the market_id at which each cell's
#: CLUSTER rows are half spent. Lesson 2 — always split the holdout, and believe
#: it over the pooled number. Quoted rather than recomputed because the sweep is
#: done and the notes say not to re-run it. Applied OFFLINE here: the fold is
#: keyed by market_id, so the split costs nothing and needs no second sweep.
HOLDOUT_AT = {
    "baseball": 57023900,
    "basketball": 20566980,
    "esports": 34192633,
    "soccer": 56866845,
}

#: Where the market-grain fold is cached. The sweep is the only production cost
#: in this queue and every arm question is a re-read of it, so it is cached the
#: way ``pull_eras`` caches its rows: re-analysis after the first run is free.
def _cache_path(cat):
    return os.path.join(HERE, f"published-marketgrain-{cat}.json")


def market_grain_fold(cat, width):
    """``market_id -> {bucket: {n, w, sp}}`` over the published cell, cached.

    Also returns the payload self-check, which is the only thing standing
    between this and a parallel rail wearing the published curve's name.
    """
    path = _cache_path(cat)
    if os.path.exists(path):
        with open(path) as fh:
            d = json.load(fh)
        return ({int(k): {int(b): v for b, v in bb.items()}
                 for k, bb in d["by_market"].items()}, d["self_check"])

    t0 = time.time()
    by_key, _ = cce.sweep("polymarket", cat, "marketid", width)
    n, ece, gap = cce.fold(cce.pool(by_key))
    pn, pece, pgap, meta = cce.payload_cell("polymarket", cat)
    self_check = {
        "exact": {"n": n, "ece": ece, "gap": gap},
        "payload": {"n": pn, "ece": pece, "gap": pgap, **meta},
        "delta_n": n - pn,
        "delta_n_pct": round((n - pn) / pn * 100, 3) if pn else None,
        "seconds": round(time.time() - t0, 1),
    }
    by_market = {int(k): {int(b): v for b, v in bb.items()}
                 for k, bb in by_key.items()}
    with open(path, "w") as fh:
        json.dump({"self_check": self_check,
                   "by_market": {str(k): {str(b): v for b, v in bb.items()}
                                 for k, bb in by_market.items()}}, fh)
    return by_market, self_check


def _stats(bins):
    """``n / ECE / gap / mean_p / realized / ECE-if-every-price-were-flipped``.

    ``fold`` is the shipped one. ``ece_if_flipped`` is the counterfactual the
    leg-swap claim actually makes: if these rows' prices are on the wrong leg,
    the realized rate tracks ``1 - p`` and the flipped ECE is the SMALLER of the
    two. It is computed per bucket for the same reason the real ECE is — a
    signed average cancels this defect by construction.
    """
    n, ece, gap = cce.fold(bins)
    if not n:
        return None
    sp = sum(v["sp"] for v in bins.values())
    w = sum(v["w"] for v in bins.values())
    flip = sum(abs(v["w"] / v["n"] - (1 - v["sp"] / v["n"])) * v["n"]
               for v in bins.values()) / n * 100
    return {"n": n, "ece": ece, "gap": gap,
            "mean_p": round(sp / n, 4), "realized": round(w / n, 4),
            "ece_if_flipped": round(flip, 2)}


def _merge(by_market, ids):
    out = {}
    for mid in ids:
        for b, v in by_market.get(mid, {}).items():
            slot = out.setdefault(b, {"n": 0, "w": 0, "sp": 0.0})
            slot["n"] += v["n"]
            slot["w"] += v["w"]
            slot["sp"] += v["sp"]
    return out


def fold_cell(cat, width):
    print(f"\n=== polymarket/{cat}", flush=True)
    check = LC.self_check(cat)
    part = LC.classify(cat)
    arms = part["arms"]
    census = part["census"]
    drift = verify_against_p136(cat)

    print("  PARTITION — offline, from CAL-P137's cached rows")
    for k, v in census.items():
        print(f"    {k:<44} {v}")
    print(f"    {'min_flips agrees with era-fold._min_flips':<44} "
          f"{check['families_checked']} families, "
          f"{check['cost_disagreements']} disagreements")
    print()

    by_market, sc = market_grain_fold(cat, width)
    print(f"  curve generated {sc['payload']['generated_at']}  "
          f"population {sc['payload']['population_version']}")
    print("  SELF-CHECK — the producer's own chain against the payload it produced")
    print(f"    {'exact replica':<16} n={sc['exact']['n']:>7}  "
          f"ECE={sc['exact']['ece']:>6}  gap={sc['exact']['gap']:>+7}")
    print(f"    {'payload':<16} n={sc['payload']['n']:>7}  "
          f"ECE={sc['payload']['ece']:>6}  gap={sc['payload']['gap']:>+7}")
    print(f"    {'delta':<16} n={sc['delta_n']:>+7} ({sc['delta_n_pct']:+}%)")
    print()

    claimed = set().union(*arms.values()) if arms else set()
    published = set(by_market)
    total_n = sum(v["n"] for bb in by_market.values() for v in bb.values())

    print(f"  {'arm':<20} {'markets':>8} {'published':>10} {'reach%':>7} "
          f"{'n':>7} {'share':>7} {'ECE':>7} {'gap':>8} "
          f"{'mean_p':>7} {'realized':>9} {'ECE_flip':>9}")
    out_arms = {}
    for arm in list(LC.ARMS) + ["z_not_in_a_ladder"]:
        ids = (published - claimed) if arm == "z_not_in_a_ladder" else arms[arm]
        reached = ids & published
        st = _stats(_merge(by_market, reached))
        out_arms[arm] = {"markets_in_cell": len(ids),
                         "markets_published": len(reached),
                         "reach_pct": round(100.0 * len(reached) / len(ids), 1)
                         if ids else None, **(st or {"n": 0})}
        if not st:
            print(f"  {arm:<20} {len(ids):>8} {len(reached):>10} "
                  f"{'—':>7} {0:>7}")
            continue
        print(f"  {arm:<20} {len(ids):>8} {len(reached):>10} "
              f"{out_arms[arm]['reach_pct']:>6.1f}% {st['n']:>7} "
              f"{st['n'] / total_n * 100:>6.1f}% {st['ece']:>7} {st['gap']:>+8} "
              f"{st['mean_p']:>7.4f} {st['realized']:>9.4f} "
              f"{st['ece_if_flipped']:>9.2f}")
    print()

    edge = HOLDOUT_AT.get(cat)
    holdout = {}
    if edge:
        print(f"  HOLDOUT on market_id {edge}")
        for half, keep in (("OLD", lambda i: i < edge), ("NEW", lambda i: i >= edge)):
            holdout[half] = {}
            print(f"    {half}")
            for arm in list(LC.ARMS) + ["z_not_in_a_ladder"]:
                ids = (published - claimed) if arm == "z_not_in_a_ladder" else arms[arm]
                st = _stats(_merge(by_market, {i for i in ids & published if keep(i)}))
                if not st:
                    continue
                holdout[half][arm] = st
                print(f"      {arm:<20} {st['n']:>7} {st['ece']:>7} "
                      f"{st['gap']:>+8} {st['ece_if_flipped']:>9.2f}")
        print()

    return {
        "cell": f"polymarket/{cat}",
        "partition": census,
        "min_flips_self_check": check,
        "cache_age_rows": drift,
        "population_self_check": sc,
        "published_markets_in_cell": len(published),
        "arms": out_arms,
        "holdout_at": edge,
        "holdout": holdout,
    }


if __name__ == "__main__":
    cats = [a for a in sys.argv[1:] if not a.startswith("--")]
    for cat in cats or ["baseball"]:
        out = fold_cell(cat, cce.DEFAULT_WIDTH)
        with open(os.path.join(HERE, f"published-legswap-{cat}.json"), "w") as fh:
            json.dump(out, fh, indent=2)
    merged = {}
    for name in sorted(os.listdir(HERE)):
        if name.startswith("published-legswap-") and name.endswith(".json"):
            with open(os.path.join(HERE, name)) as fh:
                merged[name[len("published-legswap-"):-len(".json")]] = json.load(fh)
    with open(os.path.join(HERE, "published-legswap.json"), "w") as fh:
        json.dump(merged, fh, indent=2)
    print("FOLD COMPLETE", flush=True)
