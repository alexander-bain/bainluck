"""The nested ladder's TRUTH law, which is stronger than its price law.

CAL-P133 proved a PRICE law on nested ladders: where one rung's event contains
the next one's, the published prices must be ordered the same way. That law has
a defence available to it — "the market really was priced like that" — which is
why it is a calibration finding and not a bug report.

The same containment argues something with no defence at all. If a market's legs
are cumulative thresholds ``above X`` over one quantity, then the realized value
V decides every leg at once::

    is_winner(above X)  ==  (V > X)

so sorted by X ascending, ``is_winner`` can only be ``True … True False … False``.
A ``False`` at a low rung followed by a ``True`` at a higher one is not a
mispricing and not a modelling disagreement: **at least one of those two legs is
graded wrong**, and no fact about the world can make both correct. The curve is
scoring those rows against a label that cannot be right.

This script measures that law on the raw cell, and splits the population the one
way that decides what the finding IS:

  * **authoritative** ladders — every leg carries a resolution_source in
    :data:`AUTHORITATIVE`. A reversal here is a defect in data we call settled.
  * **guess-containing** ladders — at least one leg was graded by a pass-2 guess.
    A reversal here indicts the guesser, not the settlement feed.

If reversals sit almost entirely in the second group, the law has measured the
guessing pipeline against pure logic — a falsification test the resolution work
has never had. If they sit in the first, the settlement feed itself is wrong.
Either way the split is the answer and the pooled number is not (lesson 14).

⚠️ Everything printed here is a RAW-CELL count. The published population is a
different and much smaller thing and only ``calibration_cell_exact.py`` can
measure it — lesson 19, which cost CAL-P133 a whole rule design's worth of
nearly-written prose.

Reads the row cache left by ``kalshi-outcome-ladder-census.py``; run that first.
"""
import collections
import gzip
import json
import os
import re
import sys

#: Sources that claim to KNOW the result, as opposed to inferring it. The split
#: this list draws is the entire experiment, so it is stated as data rather than
#: buried in a predicate.
AUTHORITATIVE = {"api_settlement", "clean_resolution", "kalshi_api", "settlement"}

SCALE = {"k": 1e3, "m": 1e6, "b": 1e9, "bn": 1e9, "t": 1e12}
PRE_RE = re.compile(r"^\s*(?:above|over|at least)\s+\$?\s*"
                    r"(?P<val>\d[\d,]*(?:\.\d+)?)\s?(?P<unit>bn|[kmbt])?\s*%?\s*$", re.I)
POST_RE = re.compile(r"^\s*\$?\s*(?P<val>\d[\d,]*(?:\.\d+)?)\s?(?P<unit>bn|[kmbt])?\s*%?\s*"
                     r"or\s+(?:above|higher|more|greater)\s*$", re.I)
PLUS_RE = re.compile(r"^\s*\$?\s*(?P<val>\d[\d,]*(?:\.\d+)?)\s?(?P<unit>bn|[kmbt])?\s*\+\s*$", re.I)


def cumulative_rung(leg):
    for rx in (PRE_RE, POST_RE, PLUS_RE):
        m = rx.match(leg or "")
        if m:
            v = float(m.group("val").replace(",", ""))
            if m.group("unit"):
                v *= SCALE[m.group("unit").lower()]
            return v
    return None


def truth_reversals(order, truth):
    """Consecutive rungs where a LOWER threshold lost and a HIGHER one won."""
    return [(a, b) for a, b in zip(order, order[1:])
            if truth[a] is False and truth[b] is True]


def main():
    src, cat = sys.argv[1], sys.argv[2]
    cache = f"artifacts/cal-p134/rows-{src}-{cat}.json.gz"
    if not os.path.exists(cache):
        raise SystemExit(f"no row cache at {cache} — run the outcome-ladder census first")
    with gzip.open(cache, "rt") as fh:
        rows = json.load(fh)

    mkts = collections.defaultdict(lambda: {"name": None, "type": None, "legs": []})
    for mid, mname, mtype, oname, price, win, rsrc in rows:
        m = mkts[mid]
        m["name"], m["type"] = mname, mtype
        m["legs"].append((oname, price, win, rsrc))

    c = collections.Counter()
    bad_auth, bad_guess, impossible_price = [], [], []
    for mid, m in mkts.items():
        parsed = [(cumulative_rung(o), p, w, s) for o, p, w, s in m["legs"]]
        if not parsed or any(v is None for v, _, _, _ in parsed):
            continue                                   # not an all-cumulative market
        vals = [v for v, _, _, _ in parsed]
        if len(set(vals)) != len(vals):
            continue                                   # duplicate rung: key groups two ladders
        graded = [(v, p, w, s) for v, p, w, s in parsed if s]
        if len(graded) < 2:
            c["ladders_under_two_graded_legs"] += 1
            continue
        c["ladders_testable_truth"] += 1
        c["legs_testable_truth"] += len(graded)
        order = sorted(v for v, _, _, _ in graded)
        truth = {v: bool(w) for v, _, w, _ in graded}
        rev = truth_reversals(order, truth)
        all_auth = all(s in AUTHORITATIVE for _, _, _, s in graded)
        band = "auth" if all_auth else "guess"
        c[f"ladders_{band}"] += 1
        c[f"legs_{band}"] += len(graded)
        c[f"truth_pairs_{band}"] += len(order) - 1
        c[f"truth_reversal_pairs_{band}"] += len(rev)
        if rev:
            c[f"ladders_truth_broken_{band}"] += 1
            c[f"legs_truth_broken_{band}"] += len(graded)
            (bad_auth if all_auth else bad_guess).append(
                (mid, m["name"], m["type"], len(graded), rev))

        # The price law, measured ONLY where the truth law holds and every leg is
        # authoritative — so a price reversal here cannot be blamed on grading.
        if all_auth and not rev:
            priced = {v: float(p) for v, p, _, _ in graded if p is not None}
            po = sorted(priced)
            if len(po) >= 2:
                c["ladders_price_testable_clean_truth"] += 1
                vio = [(a, b) for a, b in zip(po, po[1:]) if priced[b] > priced[a]]
                c["price_pairs_clean_truth"] += len(po) - 1
                c["price_reversal_pairs_clean_truth"] += len(vio)
                if vio:
                    c["ladders_price_broken_clean_truth"] += 1
                    c["legs_price_broken_clean_truth"] += len(graded)
                # The rows that hurt the curve most: an easy rung priced at a
                # long shot that then WON, inside a ladder whose truth is sound.
                for v, p, w, s in graded:
                    if p is None:
                        continue
                    p = float(p)
                    if w and p <= 0.05:
                        c["rows_longshot_winner"] += 1
                        impossible_price.append((mid, m["name"], v, p, True))
                    elif (not w) and p >= 0.95:
                        c["rows_lock_loser"] += 1
                        impossible_price.append((mid, m["name"], v, p, False))

    print(f"\n=== {src}/{cat} — TRUTH monotonicity on cumulative ladders (RAW CELL) ===")
    for k in ("ladders_under_two_graded_legs", "ladders_testable_truth",
              "legs_testable_truth",
              "ladders_auth", "legs_auth", "truth_pairs_auth",
              "truth_reversal_pairs_auth", "ladders_truth_broken_auth",
              "legs_truth_broken_auth",
              "ladders_guess", "legs_guess", "truth_pairs_guess",
              "truth_reversal_pairs_guess", "ladders_truth_broken_guess",
              "legs_truth_broken_guess"):
        print(f"  {k:38s} {c[k]}")
    for band in ("auth", "guess"):
        n = c[f"ladders_{band}"]
        if n:
            print(f"  TRUTH-BROKEN SHARE [{band:5s}] "
                  f"{c[f'ladders_truth_broken_{band}'] / n * 100:5.1f}% of ladders  "
                  f"({c[f'legs_truth_broken_{band}']} legs)")

    print(f"\n  --- price law, restricted to authoritative + truth-coherent ladders ---")
    for k in ("ladders_price_testable_clean_truth", "price_pairs_clean_truth",
              "price_reversal_pairs_clean_truth", "ladders_price_broken_clean_truth",
              "legs_price_broken_clean_truth", "rows_longshot_winner",
              "rows_lock_loser"):
        print(f"  {k:38s} {c[k]}")
    n = c["ladders_price_testable_clean_truth"]
    if n:
        print(f"  PRICE-BROKEN SHARE {c['ladders_price_broken_clean_truth'] / n * 100:5.1f}% "
              f"of clean-truth ladders")

    for label, bad in (("AUTHORITATIVE", bad_auth), ("GUESS-CONTAINING", bad_guess)):
        print(f"\n  worst {label} truth reversals:")
        bad.sort(key=lambda r: -len(r[4]))
        for mid, nm, mt, nlegs, rev in bad[:8]:
            a, b = rev[0]
            print(f"    {mid} [{mt}] {str(nm)[:60]!r}  {len(rev)} reversals / {nlegs} legs")
            print(f"        above {a:g} graded LOST  but  above {b:g} graded WON")

    print(f"\n  longshot winners / lock losers inside clean ladders (worst 10):")
    impossible_price.sort(key=lambda r: (r[3] if r[4] else 1 - r[3]))
    for mid, nm, v, p, w in impossible_price[:10]:
        print(f"    {mid} {str(nm)[:52]!r}  above {v:g} @ {p:.3f} -> "
              f"{'WON' if w else 'LOST'}")

    out = {"cell": f"{src}/{cat}", "census": dict(c),
           "truth_broken_auth_ids": [r[0] for r in bad_auth],
           "truth_broken_guess_ids": [r[0] for r in bad_guess]}
    p = f"artifacts/cal-p134/truth-monotonicity-{src}-{cat}.json"
    json.dump(out, open(p, "w"), indent=1)
    print(f"\n  wrote {p}")


if __name__ == "__main__":
    main()
