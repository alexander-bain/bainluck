"""Does fixing the PRICE site and the FAMILY KEY reach the Polymarket O/U book?

CAL-P135 measured that ``--by mono`` reaches none of the 51,931 O/U-shaped
markets on four Polymarket sports cells, and named three independent
blindnesses. It fixed one (the grammar, and the sign inversion hiding inside
it) and parked the other two as a package, because landing the family-key fix
WITHOUT the sign fix condemns the ladders that are behaving correctly.

This script measures the package. Four arms over the same rows, so the two
fixes can be attributed separately rather than jointly asserted:

  A  ``shipped``    yes leg, bare name key          — the CAL-P135 baseline
  B  ``price``      proposition leg, bare name key  — the price site alone
  C  ``identity``   yes leg, event-scoped key       — the family key alone
  D  ``package``    proposition leg, scoped key     — what CAL-P136 wires up

Every arm calls ``ladder_report`` from the shipped module. This file contains
no law, no grammar and no family key of its own; the only thing it adds is the
choice of arm and the reconciliation between them.

🔴 ARM C IS RUN TO BE REPORTED, NOT TO BE PROPOSED. It is the combination
CAL-P135 warned about, and printing what it does to the condemned count is the
evidence that the two fixes are one package.

Also answers CAL-P135-2, which was parked with a hypothesis and no test: 68.6%
of esports O/U rung pairs carried an identical price. ``over + under`` is the
arithmetic handle nobody had — a real two-sided pair sums to ~1, and a leg pair
that does NOT is not a price at all.

⚠️ Lesson 19: these are RAW-CELL counts. Whether any of it survives into the
published population is a question only the exact rail can answer, and this
script deliberately does not guess.

Usage:  python3 artifacts/cal-p136/ou-book-fold.py [category ...]
"""
import collections
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from app.utils.ladder_monotonicity import (  # noqa: E402
    ladder_report,
    monotonicity_violations,
    proposition_price,
    read_name_ladders,
)

from pull_rows import as_dicts  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

#: The Polymarket ladder identity, as ``MONO_CONTEXT_COLUMN`` names it.
CONTEXT = "group_id"


def arm(rows, *, price_key, context_key):
    """One arm's verdict, straight from the shipped report."""
    rep = ladder_report(rows, price_key=price_key, context_key=context_key)
    c = rep["census"]
    return {
        "families": c["families"],
        "families_multi_rung": c["families_multi_rung"],
        "families_ambiguous": c["families_ambiguous"],
        "families_condemned": c["families_condemned"],
        "violating_pairs": c["violating_pairs"],
        "flat_pairs": c["flat_pairs"],
        "markets_priced": sum(v for k, v in c["price_legs"].items()
                              if k in ("yes", "over")) or None,
        "price_legs": c["price_legs"],
        "markets_drop": c["markets_drop"],
        "markets_ambiguous": c["markets_ambiguous"],
        "markets_coherent": c["markets_coherent"],
        "_drop": rep["drop"],
    }


#: A leg pair sitting exactly on the coin flip. Measured across three cells
#: before this constant existed: 58.2% of soccer's two-legged markets, 43.5% of
#: esports', 5.4% of baseball's — and 99.4%/91.5% of them sum to 1.00, so they
#: are arithmetically coherent prices rather than the placeholder junk CAL-P135
#: hypothesised. That is precisely what makes them dangerous to a ladder law: a
#: rung parked on 0.50 is not on the ladder's curve, so a family MIXING coin
#: flips with real prices violates monotonicity for a reason that has nothing to
#: do with the ladder being mispriced.
COIN_FLIP = 0.5


def is_coin_flip(row):
    """True when both legs are exactly the coin flip."""
    o, u = row.get("over_price"), row.get("under_price")
    return (o is not None and u is not None
            and float(o) == COIN_FLIP and float(u) == COIN_FLIP)


def manufactured_share(rows):
    """How much of the UNSCOPED verdict is an artifact of the key.

    A condemned family that spans more than one Polymarket event was never one
    ladder, so its "reversal" is a comparison of one match's price against
    another's. This is the number that decides whether the unscoped arm's output
    can be read at all.
    """
    priced = []
    for r in rows:
        price, _ = proposition_price(r)
        if price is not None:
            priced.append({**r, "p": price})
    lad = read_name_ladders(priced, price_key="p")
    amb = {k for k, v in lad.items() if v["duplicate_values"]}
    elig = {k: v for k, v in lad.items()
            if len(v["rungs"]) >= 2 and k not in amb}
    ident = {r["market_id"]: r[CONTEXT] for r in priced}

    def spans(key):
        return {ident[m] for m in lad[key]["member_ids"] if m in ident}

    cond = {k for k in elig if monotonicity_violations(elig[k]["rungs"], k[1])}
    cond_multi = {k for k in cond if len(spans(k)) > 1}
    viol = sum(len(monotonicity_violations(v["rungs"], k[1]))
               for k, v in elig.items())
    viol_multi = sum(len(monotonicity_violations(elig[k]["rungs"], k[1]))
                     for k in cond_multi)
    widest = max((len(spans(k)) for k in elig), default=0)
    return {
        "eligible_families": len(elig),
        "condemned_families": len(cond),
        "condemned_spanning_multi_event": len(cond_multi),
        "condemned_spanning_multi_event_pct": round(
            100.0 * len(cond_multi) / max(1, len(cond)), 1),
        "violating_pairs": viol,
        "violating_pairs_from_multi_event": viol_multi,
        "violating_pairs_from_multi_event_pct": round(
            100.0 * viol_multi / max(1, viol), 1),
        "widest_family_events_spanned": widest,
    }


def two_sided_arithmetic(rows):
    """CAL-P135-2. Is a flat O/U rung pair a price, or a placeholder?

    A real two-sided book sums to about one. The hypothesis parked by CAL-P135
    was that the 68.6% flat rate is placeholder pricing; ``over + under`` tests
    it without needing an outcome, and the split below is the whole answer.
    """
    pairs = [(float(r["over_price"]), float(r["under_price"])) for r in rows
             if r["over_price"] is not None and r["under_price"] is not None]
    if not pairs:
        return {"markets_with_both_legs": 0}
    equal = [(o, u) for o, u in pairs if o == u]
    unequal = [(o, u) for o, u in pairs if o != u]

    def sums(ps):
        return [round(o + u, 6) for o, u in ps]

    def summarise(ps):
        if not ps:
            return {"n": 0}
        s = sums(ps)
        return {
            "n": len(ps),
            "sum_median": round(statistics.median(s), 4),
            "sum_within_1pct_of_one": sum(1 for v in s if abs(v - 1.0) <= 0.01),
            "sum_within_1pct_pct": round(
                100.0 * sum(1 for v in s if abs(v - 1.0) <= 0.01) / len(s), 1),
        }

    return {
        "markets_with_both_legs": len(pairs),
        "legs_equal": summarise(equal),
        "legs_unequal": summarise(unequal),
        "equal_share_pct": round(100.0 * len(equal) / len(pairs), 1),
    }


def holdout(rows, split_id):
    """The package arm on each half of the cell, split at the id median.

    Lesson 2: believe the holdout over the pooled number. This predicate is a
    function of names and prices only, so a split tests STABILITY rather than
    leakage — which is the claim being made and the only one this arm supports.
    """
    out = {}
    for half, subset in (("early", [r for r in rows if r["market_id"] < split_id]),
                         ("late", [r for r in rows if r["market_id"] >= split_id])):
        a = arm(subset, price_key=None, context_key=CONTEXT)
        a.pop("_drop")
        n = max(1, a["markets_drop"] + a["markets_ambiguous"] + a["markets_coherent"])
        a["rows"] = len(subset)
        a["drop_rate_of_laddered_pct"] = round(100.0 * a["markets_drop"] / n, 2)
        out[half] = a
    return out


def census(cat):
    rows = as_dicts(cat)
    ids = sorted(r["market_id"] for r in rows)
    split_id = ids[len(ids) // 2] if ids else 0

    arms = {}
    for label, price_key, context_key in (
            ("A_shipped", "yes_price", None),
            ("B_price_site", None, None),
            ("C_identity_only", "yes_price", CONTEXT),
            ("D_package", None, CONTEXT)):
        arms[label] = arm(rows, price_key=price_key, context_key=context_key)

    # Arm E is a DIAGNOSTIC, not a proposal. The package's condemnation rate
    # came out at 25-56% of the laddered book on every cell, which is far too
    # high to be "these ladders are mispriced" and is the shape of a law being
    # applied to rows it does not govern. Dropping the exact coin flips is the
    # cheapest test of the obvious candidate; if the rate collapses, the finding
    # is about 0.50 rungs rather than about monotonicity.
    live = [r for r in rows if not is_coin_flip(r)]
    arms["E_package_no_coin_flip"] = arm(live, price_key=None, context_key=CONTEXT)
    arms["E_package_no_coin_flip"]["markets_excluded_as_coin_flip"] = (
        len(rows) - len(live))

    # What the package condemns that the shipped arm never saw, and vice versa.
    a_drop, d_drop = arms["A_shipped"]["_drop"], arms["D_package"]["_drop"]
    reconcile = {
        "dropped_by_shipped_only": len(a_drop - d_drop),
        "dropped_by_package_only": len(d_drop - a_drop),
        "dropped_by_both": len(a_drop & d_drop),
    }
    for a in arms.values():
        a.pop("_drop")

    legs = collections.Counter()
    for r in rows:
        legs[proposition_price(r)[1]] += 1

    return {
        "category": cat,
        "markets_total": len(rows),
        "price_site": dict(legs),
        "arms": arms,
        "reconcile_shipped_vs_package": reconcile,
        "manufactured_by_the_unscoped_key": manufactured_share(rows),
        "two_sided_arithmetic": two_sided_arithmetic(rows),
        "holdout_at": split_id,
        "holdout": holdout(rows, split_id),
    }


if __name__ == "__main__":
    cats = sys.argv[1:] or ["baseball", "esports", "soccer", "basketball"]
    # One file per cell, merged into the combined artifact on every run, so a
    # cell whose rows are not cached yet does not wipe the ones that are.
    for cat in cats:
        print(f"=== polymarket/{cat}", file=sys.stderr, flush=True)
        result = census(cat)
        with open(os.path.join(HERE, f"ou-book-fold-{cat}.json"), "w") as fh:
            json.dump(result, fh, indent=2)
        print(json.dumps(result, indent=2), flush=True)
    merged = {}
    for name in sorted(os.listdir(HERE)):
        if name.startswith("ou-book-fold-") and name.endswith(".json"):
            with open(os.path.join(HERE, name)) as fh:
                merged[name[len("ou-book-fold-"):-len(".json")]] = json.load(fh)
    with open(os.path.join(HERE, "ou-book-fold.json"), "w") as fh:
        json.dump(merged, fh, indent=2)
    print("FOLD COMPLETE", flush=True)
