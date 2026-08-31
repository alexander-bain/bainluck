"""CAL-P139 — the published curve at OUTCOME grain, so multiplicity is visible.

WHY THIS EXISTS
---------------
Every fold this lane has ever run keys on something COARSER than an outcome —
``market_id`` (CAL-P138), a family, a ladder rung, a price band. A coarser key
sums ``COUNT(*)`` inside itself, so a population that emits the same outcome
twice is indistinguishable from one that emits it once with double the weight.
Both read as ``n``.

CAL-P139 keyed a probe on ``market_id || outcome_id`` for an unrelated reason
(CAL-P138-1 wanted to know WHICH LEG published) and 96 outcomes in a 6,100-id
window of ``polymarket/baseball`` came back as 192 rows — **every one of them
exactly twice**.

THE MECHANISM, WHICH IS RULING 125 WITH THE SIGN REVERSED
----------------------------------------------------------
``vm_stats`` groups by FIVE columns::

    GROUP BY vm.vm_id, vm.source, vm.category, vm.is_grouped, vm.mutually_exclusive

``ranked_outcomes`` joins it back on TWO::

    JOIN clean_vms cv ON cv.vm_id = vm.vm_id AND cv.source = vm.source

So when one virtual market's member markets disagree on ``category``,
``is_grouped`` or ``mutually_exclusive``, ``clean_vms`` holds one row per
variant and the join emits **every outcome of that virtual market once per
variant**. Ruling 125 named this class for a join that DELETES rows ("a join
whose key is coarser than the identity of the rows it can eliminate silently
picks a winner across a dimension nobody declared"); this is the same defect
multiplying instead of deleting, three CTEs earlier in the same chain.

It is not rare. A raw-table census over ``futures_markets`` — no CTE chain
involved — finds **18,363 of 18,378** groups with >=3 resolved markets carry
mixed identity attributes, covering **259,859 of 259,925** markets. The driver
is the ordinary Polymarket event shape: one ``field`` market with
``mutually_exclusive = false`` sitting beside ~37 ``quantity`` markets with
``mutually_exclusive = true``.

WHAT THIS SCRIPT MEASURES
-------------------------
Per cell, on the producer's own chain through ``calibration_cell_exact``:

* the multiplicity histogram of published outcomes (1x, 2x, 3x, ...);
* the cell's published ``n``/ECE/gap as the curve computes it;
* the same three **deduplicated** — each distinct outcome counted once — which
  is what the cell would read if the join carried its identity.

⚠️ THE CHUNKING UNDERSTATES, IT CANNOT OVERSTATE. ``calibration_cell_exact``
restricts ``market_info`` to an id range, which can drop a group below the
``>= 3`` threshold and collapse its ``vm_id`` to the per-market ``m:`` arm — and
a single-market vm has one identity and therefore no duplication. So a chunked
replica loses duplicates it should have; it never invents them. Every number
below is a FLOOR.

Usage::

    source ~/.claude/.env && python3 artifacts/cal-p139/outcome-grain-fold.py baseball
"""
import collections
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend", "scripts"))

import calibration_cell_exact as cce  # noqa: E402

#: Outcome grain, plus the two columns CAL-P138-1 asked for: the leg's name and
#: whether the producer's ``rn`` tie-break was arbitrary. ``rn_distance_rank``
#: is a RANK, so two legs equidistant from 0.5 share it and ``fo.id`` decided
#: which one published.
KEY = ("d.market_id::text || '|' || d.outcome_id::text || '|' || "
       "d.rn_distance_rank::text || '|' || COALESCE(d.outcome_name, '')")

cce.DIMENSIONS["outcome"] = (KEY, "", "")


def _cache(source, cat):
    return os.path.join(HERE, f"outcomegrain-{source}-{cat}.json")


def fold(cat, source="polymarket", width=1_000_000):
    path = _cache(source, cat)
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    t0 = time.time()
    by_key, _ = cce.sweep(source, cat, "outcome", width)
    n, ece, gap = cce.fold(cce.pool(by_key))
    pn, pece, pgap, meta = cce.payload_cell(source, cat)
    out = {
        "cell": f"{source}/{cat}",
        "self_check": {
            "exact": {"n": n, "ece": ece, "gap": gap},
            "payload": {"n": pn, "ece": pece, "gap": pgap, **meta},
            "delta_n": n - pn,
            "delta_n_pct": round((n - pn) / pn * 100, 3) if pn else None,
            "seconds": round(time.time() - t0, 1),
        },
        "by_key": {str(k): {str(b): v for b, v in bb.items()}
                   for k, bb in by_key.items()},
    }
    with open(path, "w") as fh:
        json.dump(out, fh)
    return out


def analyse(d):
    by_key = d["by_key"]
    mult = collections.Counter()
    dedup_bins = {}
    raw_bins = {}
    published_n = 0
    for k, bb in by_key.items():
        # One outcome's rows can only land in ONE bucket (same price), so the
        # multiplicity is the total n across its buckets. Asserted, not assumed:
        # a key spanning two buckets would mean two DIFFERENT prices under one
        # outcome id, which is a different finding and must not be averaged in.
        m = sum(v["n"] for v in bb.values())
        buckets = list(bb)
        if len(buckets) != 1:
            mult["MULTI_BUCKET"] += 1
            continue
        mult[m] += 1
        b = buckets[0]
        v = bb[b]
        published_n += v["n"]
        slot = raw_bins.setdefault(b, {"n": 0, "w": 0, "sp": 0.0})
        slot["n"] += v["n"]
        slot["w"] += v["w"]
        slot["sp"] += v["sp"]
        one = dedup_bins.setdefault(b, {"n": 0, "w": 0, "sp": 0.0})
        one["n"] += 1
        one["w"] += v["w"] // m if m else v["w"]
        one["sp"] += v["sp"] / m if m else v["sp"]
    return mult, raw_bins, dedup_bins, published_n


def main(argv):
    cats = argv or ["polymarket/baseball"]
    report = {}
    for spec in cats:
        source, _, cat = spec.rpartition("/")
        source = source or "polymarket"
        print(f"\n=== {source}/{cat}", flush=True)
        d = fold(cat, source)
        sc = d["self_check"]
        print(f"  curve {sc['payload']['generated_at']}  population "
              f"{sc['payload']['population_version']}")
        print(f"  self-check   exact n={sc['exact']['n']} ECE={sc['exact']['ece']}"
              f"   payload n={sc['payload']['n']} ECE={sc['payload']['ece']}"
              f"   delta {sc['delta_n']:+} ({sc['delta_n_pct']:+}%)")
        mult, raw, ded, pub = analyse(d)
        distinct = sum(v for k, v in mult.items() if k != "MULTI_BUCKET")
        print(f"  distinct outcomes {distinct}   published rows {pub}"
              f"   inflation {pub / distinct:.4f}x" if distinct else "  no rows")
        print("  multiplicity: " + "  ".join(
            f"{k}x={v}" for k, v in sorted(
                ((k, v) for k, v in mult.items() if k != "MULTI_BUCKET"))))
        if mult.get("MULTI_BUCKET"):
            print(f"  ⚠️ {mult['MULTI_BUCKET']} outcome ids span >1 bucket "
                  "— excluded from both folds, reported not absorbed")
        rn, rece, rgap = cce.fold(raw)
        dn, dece, dgap = cce.fold(ded)
        print(f"  AS PUBLISHED   n={rn:>7}  ECE={rece:>6}  gap={rgap:>+7}")
        print(f"  DEDUPLICATED   n={dn:>7}  ECE={dece:>6}  gap={dgap:>+7}")
        print(f"  MOVE           n={dn - rn:>+7}  ECE={round(dece - rece, 2):>+6}"
              f"  gap={round(dgap - rgap, 2):>+7}")
        report[f"{source}/{cat}"] = {
            "self_check": sc,
            "distinct_outcomes": distinct,
            "published_rows": pub,
            "inflation": round(pub / distinct, 4) if distinct else None,
            "multiplicity": {str(k): v for k, v in mult.items()},
            "as_published": {"n": rn, "ece": rece, "gap": rgap},
            "deduplicated": {"n": dn, "ece": dece, "gap": dgap},
        }
    with open(os.path.join(HERE, "outcome-grain.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
