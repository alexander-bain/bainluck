"""CAL-P138 — what CAL-P136's refused rule would actually do to the PUBLISHED cell.

CAL-P136 reached the Polymarket O/U book, found its monotonicity package
condemning 28-70% of what it laddered, and refused to bank a rule on the ground
that "a rule deleting a third of a book is disagreeing with the book". CAL-P137
superseded the REASON — on baseball the law is correctly reporting that our rows
are on the wrong leg — but neither queue ever priced the rule on the population
it would have shipped against. Both refusals were judgements. This turns them
into a number.

It costs nothing: the market-grain fold is already cached, so every candidate
rule below is a set difference and a re-fold, offline.

🔴 WHAT IT FINDS, AND IT IS THE OPPOSITE OF THE INTUITION THE ARM TABLE GIVES.
The condemned rows are the worst-calibrated in the cell — ECE 15.12 against the
cell's 4.68 — and dropping them makes the cell WORSE, not better. The reason is
in the gap column and doctrine 18 already names it: the condemned rows carry gap
-5.03 while the cell carries +3.25, so they were partially CANCELLING the cell's
overpricing bias, and an exclusion removes the offset along with the defect. An
exclusion rule can only remove a defect that is CONCENTRATED (lesson 18) — this
one is concentrated in ECE and anti-concentrated in gap, and the headline metric
is the gap-family one.

⚠️ NONE OF THESE ARE PROPOSED. Two of them are exclusions this queue's own
finding argues against on pillar grounds (CAL-P137 §7: repairing a TRUTH defect
by deleting it from the curve buys a calibration cell with a bug that is still
wrong on the event page). They are priced so that the refusal is a measurement
rather than an argument, which is the whole point.

Usage::

    source ~/.claude/.env && python3 artifacts/cal-p138/rule-pricing.py baseball
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend", "scripts"))

import calibration_cell_exact as cce  # noqa: E402

import legswap_classes as LC  # noqa: E402

#: The arms a rule would DROP, per candidate. Named by what the rule claims to
#: be doing, so the table reads as a list of proposals rather than of set
#: algebra — and so a reader can see that the first one is CAL-P136's package
#: and the rest are strictly smaller versions of it.
CANDIDATES = {
    "CAL-P136 package (drop every condemned family)":
        ("a_flip1_suspect", "b_flip1_sibling", "c_flip1_ambiguous",
         "d_flip2plus", "e_no_assignment"),
    "drop only the leg-swap families":
        ("a_flip1_suspect", "b_flip1_sibling"),
    "drop only the accused row":
        ("a_flip1_suspect",),
    "drop only the families no swap can fix":
        ("e_no_assignment",),
    "drop every laddered market (doctrine 18's outer bound)":
        ("a_flip1_suspect", "b_flip1_sibling", "c_flip1_ambiguous",
         "d_flip2plus", "e_no_assignment", "f_mono_ambiguous",
         "g_mono_coherent"),
}


def price(cat):
    with open(os.path.join(HERE, f"published-marketgrain-{cat}.json")) as fh:
        raw = json.load(fh)["by_market"]
    by_market = {int(k): {int(b): v for b, v in bb.items()}
                 for k, bb in raw.items()}
    arms = LC.classify(cat)["arms"]
    published = set(by_market)

    def merge(ids):
        out = {}
        for mid in ids:
            for b, v in by_market.get(mid, {}).items():
                s = out.setdefault(b, {"n": 0, "w": 0, "sp": 0.0})
                s["n"] += v["n"]
                s["w"] += v["w"]
                s["sp"] += v["sp"]
        return out

    base_n, base_ece, base_gap = cce.fold(merge(published))
    rows = []
    for label, drop_arms in CANDIDATES.items():
        drop = set().union(*(arms[a] for a in drop_arms))
        n, ece, gap = cce.fold(merge(published - drop))
        rows.append({
            "rule": label,
            "outcomes_dropped": base_n - n,
            "pct_of_cell_dropped": round(100.0 * (base_n - n) / base_n, 2),
            "ece_after": ece, "ece_delta": round(ece - base_ece, 2),
            "gap_after": gap, "gap_delta": round(gap - base_gap, 2),
        })
    return {"cell": f"polymarket/{cat}",
            "baseline": {"n": base_n, "ece": base_ece, "gap": base_gap},
            "candidates": rows}


if __name__ == "__main__":
    out = {}
    for cat in sys.argv[1:] or ["baseball"]:
        r = price(cat)
        out[cat] = r
        b = r["baseline"]
        print(f"\npolymarket/{cat}   baseline  n={b['n']}  ECE={b['ece']}  "
              f"gap={b['gap']:+}")
        print(f"  {'candidate rule':<52} {'dropped':>8} {'%cell':>7} "
              f"{'ECE':>6} {'dECE':>7} {'gap':>7} {'dgap':>7}")
        for c in r["candidates"]:
            print(f"  {c['rule']:<52} {c['outcomes_dropped']:>8} "
                  f"{c['pct_of_cell_dropped']:>6.2f}% {c['ece_after']:>6} "
                  f"{c['ece_delta']:>+7} {c['gap_after']:>+7} "
                  f"{c['gap_delta']:>+7}")
    with open(os.path.join(HERE, "rule-pricing.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    print("\nPRICING COMPLETE")
