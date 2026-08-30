"""CAL-P141 — reconcile the two instruments that both claim to measure duplication.

WHY THIS EXISTS
---------------
The board has TWO instruments that both answer "how many of this cell's rows are
duplicates?", they have never been compared, and they disagree by up to 36%:

* **payload basis** — ``backend/scripts/calibration_phantom_curve.py --cell``
  (CAL-P126, twelve cells; CAL-P141 added ``polymarket/hockey``). Verified
  internally consistent: for every cell ``sum(bucket.n_ship) == published_rows``
  and ``sum(bucket.n_dedup) == distinct_outcomes``, exactly.
* **replica basis** — ``artifacts/cal-p139/inflation-census.py`` (CAL-P139), and
  its exact sibling ``outcome-grain-fold.py``. Both read the producer's
  ``_calibration_population_ctes`` replica. Stated purpose: triage — *"it gives
  the INFLATION, which is the number that says whether the ECE fold is worth 11
  minutes."*

🔴 **They are not two attempts at one number. They are one number over two
different populations, and nothing on either side says so.** The proof is in the
data and the instrument re-checks it every run: the payload-basis
``published_rows`` equals the census's own ``payload_n`` to +0.000% on the two
cells with no population drift between the runs, while the census's
``rows_published`` — the replica — is short by 0 to 36% depending on the cell.

So "the cheap one is a lower bound on the exact one" is the wrong frame. The
cheap one is exact about a population that is not the one the curve publishes.

WHICH BASIS ANSWERS WHICH QUESTION
----------------------------------
``alex-inbox/calibration-911`` §3 asks for the per-cell duplication **of the
published curve** — its whole argument is that ``total_outcomes: 925,446`` on the
public page "is not a count of outcomes". That is a payload-basis question, and
only the payload-basis instrument answers it. 911 §5 item 1 nominates the census
to extend §3; the census cannot, however long it runs.

The reason this was invisible: on ``polymarket/baseball`` — the one cell 911
folded — the two bases nearly coincide (replica is short 9.2%), so 911's fold
(1.651×) and the census (1.654×) agree to 0.15% and both look right. On
``polymarket/basketball`` the replica is short 35.8% and the census reads 1.13
where the payload is 1.77. Same instrument, no warning either way.

THE TWO DISCREPANCY MODES
-------------------------
``REPLICA_SHORT`` — distinct agree, the replica holds FEWER rows than the payload.
    The population-basis gap above, and the dominant mode. Note what it implies:
    the replica is short only on DUPLICATE rows, because outcome coverage stays at
    1.00. This is the correction to CAL-P128's ``coverage 0.641`` — that figure is
    a row coverage, and it was read as the rail being unable to see the cell.

``DISTINCT_INFLATED`` — rows agree, the census reports MORE distinct outcomes.
    A genuine census artifact, and the one its own docstring predicts: chunking on
    ``fm.id`` can drop an identity group below the ``>= 3`` threshold, collapsing
    its ``vm_id`` to the per-market ``m:`` arm, which has one identity and
    therefore no duplication. Splitting a duplicate group manufactures distinct
    outcomes. Only ``kalshi/baseball`` shows it, and it is the largest cell — most
    chunk boundaries, most groups split.

THE TRIAGE-SAFETY TEST, AND WHY IT IS THE EXIT CODE
---------------------------------------------------
A lower bound is still useful for triage IF it preserves the ORDER of the cells —
"measure the worst one first" survives a uniform under-statement. So the test that
matters is not the size of the error, it is whether the cheap ranking agrees with
the exact ranking. Every discordant pair is a cell the cheap instrument would send
to the back of a queue the exact instrument puts at the front.

``EXIT 4`` when any pair is discordant. That is the instrument reporting itself
unfit for its stated purpose, which is the only way a triage tool can fail safely.

Usage::

    python3 artifacts/cal-p141/reconcile-duplication.py
    python3 artifacts/cal-p141/reconcile-duplication.py --json out.json
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))

# Exact measurements live wherever a session banked them. cal-p126 ran twelve;
# later sessions add cells in their own directories under the same schema.
EXACT_GLOBS = ["artifacts/cal-p126/cell-*.json", "artifacts/cal-p14*/cell-*.json"]
CHEAP_PATH = "artifacts/cal-p139/inflation-census.json"

# A cell's population grows continuously as markets resolve into it, so the two
# instruments never see byte-identical inputs. Past this much drift the cells are
# not the same measurement and the comparison is withdrawn rather than caveated.
MAX_POPULATION_DRIFT_PCT = 5.0

# Below this the two agree to within their own noise; naming a mode would be
# reading a rounding difference as a mechanism.
AGREE_PCT = 2.0


def load_exact() -> dict:
    out = {}
    for pattern in EXACT_GLOBS:
        for path in sorted(glob.glob(os.path.join(REPO, pattern))):
            with open(path) as fh:
                d = json.load(fh)
            if "published_rows" not in d or "distinct_outcomes" not in d:
                continue
            # Trust the file only if it reproduces its own headline from its own
            # buckets. CAL-P126's twelve all do; a partial or interrupted write
            # would not, and would otherwise be silently treated as reference.
            buckets = d.get("buckets") or []
            if buckets:
                n_ship = sum(b["n_ship"] for b in buckets)
                n_dedup = sum(b["n_dedup"] for b in buckets)
                if (round(n_ship) != d["published_rows"]
                        or round(n_dedup) != d["distinct_outcomes"]):
                    print(f"  ⚠️  SKIPPING {d['cell']} ({os.path.basename(path)}): "
                          f"buckets sum to {n_ship:,.0f}/{n_dedup:,.0f} but the "
                          f"headline says {d['published_rows']:,}/"
                          f"{d['distinct_outcomes']:,} — not self-consistent, so "
                          f"it is not reference-grade.", file=sys.stderr)
                    continue
            out[d["cell"]] = d
    return out


def classify(row_drift_pct: float, distinct_drift_pct: float) -> str:
    rows_agree = abs(row_drift_pct) < AGREE_PCT
    distinct_agree = abs(distinct_drift_pct) < AGREE_PCT
    if rows_agree and distinct_agree:
        return "AGREE"
    if rows_agree and distinct_drift_pct > 0:
        return "DISTINCT_INFLATED"
    if distinct_agree and row_drift_pct < 0:
        return "REPLICA_SHORT"
    return "BOTH"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="write the reconciliation to this path")
    args = ap.parse_args(argv)

    exact = load_exact()
    with open(os.path.join(REPO, CHEAP_PATH)) as fh:
        cheap = json.load(fh)

    both = sorted(set(exact) & set(cheap))
    print("CAL-P141 RECONCILER — the cheap duplication census against the exact one")
    print(f"  exact cells on file: {len(exact)}   cheap cells on file: {len(cheap)}"
          f"   overlapping: {len(both)}")
    if not both:
        print("  no overlap — nothing to reconcile.")
        return 0

    rows, withdrawn = [], []
    for cell in both:
        e, c = exact[cell], cheap[cell]
        e_rows, e_dist = e["published_rows"], e["distinct_outcomes"]
        # The cheap run's OWN view of the payload is `payload_n`; its replica row
        # count is `rows_published`. Population drift is payload-vs-payload; the
        # row shortfall is replica-vs-payload. Conflating them is the whole bug
        # this instrument exists to separate.
        drift_pct = (c["payload_n"] - e_rows) / e_rows * 100
        if abs(drift_pct) > MAX_POPULATION_DRIFT_PCT:
            withdrawn.append((cell, drift_pct))
            continue
        row_drift = (c["rows_published"] - e_rows) / e_rows * 100
        dist_drift = (c["distinct_outcomes"] - e_dist) / e_dist * 100
        rows.append({
            "cell": cell,
            "population_drift_pct": round(drift_pct, 3),
            "exact_rows": e_rows,
            "exact_distinct": e_dist,
            "exact_inflation": round(e_rows / e_dist, 4),
            "cheap_rows": c["rows_published"],
            "cheap_distinct": c["distinct_outcomes"],
            "cheap_inflation": c["inflation"],
            "row_drift_pct": round(row_drift, 3),
            "distinct_drift_pct": round(dist_drift, 3),
            "mode": classify(row_drift, dist_drift),
            # The correction that matters for 20-CAL/21-CAL: the "coverage" the
            # board reads is a ROW coverage. Outcome coverage is the one that says
            # whether the rail can see the cell at all.
            "row_coverage": round(c["rows_published"] / e_rows, 4),
            "outcome_coverage": round(c["distinct_outcomes"] / e_dist, 4),
        })

    # The basis proof, re-checked every run rather than asserted once in prose:
    # if the payload-basis instrument's row count stops matching the census's own
    # view of the payload, the two are no longer differing only by population and
    # every reading below needs redoing.
    exact_pop = [r for r in rows if abs(r["population_drift_pct"]) < 0.001]
    print(f"\n  BASIS PROOF — on {len(exact_pop)} cell(s) with zero population drift, the "
          f"payload-basis\n  instrument's row count equals the census's own payload_n exactly:")
    for r in exact_pop:
        print(f"    {r['cell']:24} exact rows {r['exact_rows']:>9,}  ==  census payload_n "
              f"(drift {r['population_drift_pct']:+.3f}%)   replica holds {r['cheap_rows']:,}")

    print(f"\n  {'cell':24} {'payload':>8} {'replica':>8} {'basis gap':>10}  "
          f"{'rowcov':>7} {'outcov':>7}  mode")
    for r in sorted(rows, key=lambda r: -r["exact_inflation"]):
        gap = (1 - r["cheap_inflation"] / r["exact_inflation"]) * 100
        print(f"  {r['cell']:24} {r['exact_inflation']:8.4f} "
              f"{r['cheap_inflation']:8.4f} {gap:9.1f}%  "
              f"{r['row_coverage']:7.4f} {r['outcome_coverage']:7.4f}  {r['mode']}")

    for cell, d in withdrawn:
        print(f"  {cell:24} WITHDRAWN — population drifted {d:+.2f}% between the "
              f"two runs (cap {MAX_POPULATION_DRIFT_PCT}%)")

    # --- the triage-safety test -------------------------------------------------
    discordant = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            de = a["exact_inflation"] - b["exact_inflation"]
            dc = a["cheap_inflation"] - b["cheap_inflation"]
            if de * dc < 0:
                discordant.append((a["cell"], b["cell"]))

    npairs = len(rows) * (len(rows) - 1) // 2
    print(f"\n  ORDERING: {len(discordant)}/{npairs} ranked pairs discordant between the "
          f"two bases")
    for a, b in discordant:
        print(f"    🔴 {a} vs {b} — the replica basis orders these backwards")

    out = {
        "cells": rows,
        "withdrawn": [{"cell": c, "population_drift_pct": round(d, 3)}
                      for c, d in withdrawn],
        "discordant_pairs": [list(p) for p in discordant],
        "pairs_compared": npairs,
        "triage_safe": not discordant,
    }
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(out, fh, indent=1)

    if discordant:
        print("\n  🔴 EXIT 4 — the replica basis does not preserve the payload "
              "basis's ordering, so it cannot pick which cell to fold next and it "
              "cannot extend calibration-911 §3. Both numbers are correct; they "
              "are correct about different populations.")
        return 4
    print("\n  EXIT 0 — the two bases agree on ordering on the cells measured so "
          "far. Re-run when a cell is added; one discordant pair is enough to "
          "withdraw the replica basis from triage again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
