"""WHY does the package condemn 28-70% of the Polymarket O/U book? (CAL-P136-2)

CAL-P136 reached the book and then refused to bank a rule, for two reasons it
could not choose between: the condemnation rate is far too high to be a
concentrated defect (lesson 18), and the id-median holdout is unstable on two
cells of four (lesson 2). It parked the diagnosis with two hypotheses:

  (a) the rungs of a family are priced at different TIMES;
  (b) ``COALESCE(calibration_probability, opening_probability)`` mixes two ERAS
      inside one family.

(b) is (a) with a mechanism and a column, and it is the cheap one. This script
tests it. ``pull_eras.py`` selects the two COALESCE branches separately, so
every rung now carries the answer to "where did this price come from", and the
question becomes arithmetic rather than speculation.

FOUR THINGS ARE MEASURED, and they are deliberately different KINDS of evidence:

  1. **The composition.** How much of the book takes each branch — over the
     whole cell and over the population arm D actually ladders. Lesson 19: a
     cell census is not the laddered population's census, and the two differ
     here by construction, so both are printed.
  2. **The association.** Condemnation rate for era-PURE families against
     era-MIXED ones. This is the test of (b): if mixing is the mechanism, mixed
     families condemn and pure ones do not.
  3. **The counterfactual.** Arm D re-run over a book priced from ONE branch
     only, twice. This removes era mixing by construction rather than by
     correlation, and it is the half of the evidence that association cannot
     supply. ⚠️ The single-branch book is a SMALLER population, so the two arms
     are compared on the drop RATE of what each one ladders, never on counts.
  4. **The holdout.** Both of the above on each half of the id range, because
     the instability in CAL-P136's holdout is the thing most in need of an
     explanation and a diagnosis that does not survive its own split is not one.

🔴 WHAT WOULD MAKE THIS A BANKABLE RULE, stated before the numbers are seen:
"exclude era-mixed families" is landable only if mixing is BOTH strongly
associated with condemnation AND a small share of the book — that is exactly
lesson 18's concentration test, and a mechanism that explains the violations by
implicating most of the book has explained them without fixing anything. The
script prints ``concentration`` for precisely this judgement, and it prints it
whichever way it comes out.

⚠️ Hypothesis (a) in its general form needs an as-of per rung. The CAL branch
has none, ``opening_captured_at`` covers only the OPEN branch, and
``price_changed_at`` is populated forward (#2024) so NULL means "not observed",
not "never moved". ``as_of_reach`` sizes that ceiling honestly and the script
declines to infer a time spread where it has none — a measurement ceiling is
not a measurement (lesson 21).

Usage:  python3 artifacts/cal-p137/era-fold.py [category ...]
"""
import collections
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from app.utils.ladder_monotonicity import (  # noqa: E402
    CONTEXT_SEP,
    ambiguous_families,
    condemned_families,
    ladder_report,
    monotonicity_violations,
    proposition_price,
    read_name_ladders,
)

from pull_eras import (  # noqa: E402
    CAL, CAL_EQ_OPEN, OPEN, as_dicts, legs_per_name, verify_against_p136,
)

HERE = os.path.dirname(os.path.abspath(__file__))

#: The Polymarket ladder identity, as ``MONO_CONTEXT_COLUMN`` names it and as
#: CAL-P136's arm D used it. Kalshi's ``group_id`` is one-per-market and would
#: annihilate the partition; this script is Polymarket-only for that reason.
CONTEXT = "group_id"

LEGS = ("yes", "over", "under")

#: A family's era class is the SET of branches its rungs came from, so the arms
#: are discovered rather than declared. Three branch labels give at most three
#: pure classes and four mixed ones — near lesson 11's limit, which is why the
#: two-arm ``pure``/``mixed`` roll-up below carries the actual decision and the
#: full partition is published as the detail behind it.
MIXED = "mixed"


def branch_of_priced_leg(row):
    """Which COALESCE branch produced the price ``proposition_price`` returns.

    ``None`` when no price was found, which is the same population
    ``ladder_report`` drops before any grammar runs.
    """
    price, reason = proposition_price(row)
    if price is None:
        return None
    return row.get(f"{reason}_branch")


def single_branch(rows, which, *, drop_fallback_signature=False):
    """The same rows, priced from ONE branch of the coalesce only.

    Rewrites the ``*_price`` columns rather than the law, so
    ``proposition_price`` applies its own unchanged rules to the narrowed book —
    including refusing a market that keeps an ``over`` leg but loses its
    ``under`` twin, which is the correct reading of a one-branch book rather
    than an artifact to be worked around.

    ``drop_fallback_signature`` additionally removes every leg whose
    ``calibration_probability`` equals its ``opening_probability``
    (:data:`~pull_eras.CAL_EQ_OPEN`). Narrowing to the CAL column is not the
    same as narrowing to the calibration ERA, because the writer's Fallback
    copies the opening price into that column; this is the arm that tells the
    two apart.
    """
    out = []
    for r in rows:
        row = dict(r)
        for leg in LEGS:
            keep = not (drop_fallback_signature
                        and r.get(f"{leg}_branch") == CAL_EQ_OPEN)
            row[f"{leg}_price"] = r.get(f"{leg}_{which}") if keep else None
        out.append(row)
    return out


def drop_rate(rep):
    """Drop as a share of what this arm LADDERS, the only cross-arm comparable."""
    c = rep["census"]
    laddered = c["markets_drop"] + c["markets_ambiguous"] + c["markets_coherent"]
    return {
        "laddered": laddered,
        "markets_drop": c["markets_drop"],
        "markets_ambiguous": c["markets_ambiguous"],
        "markets_coherent": c["markets_coherent"],
        "drop_rate_of_laddered_pct": round(100.0 * c["markets_drop"] / max(1, laddered), 2),
        "families_condemned": c["families_condemned"],
        "families_multi_rung": c["families_multi_rung"],
        "families_ambiguous": c["families_ambiguous"],
        "price_legs": c["price_legs"],
    }


def era_association(rows):
    """Condemnation rate for era-PURE families against era-MIXED ones.

    The families are the ones arm D builds — proposition price, event-scoped key
    — and eligibility is arm D's own: at least two rungs, and not ambiguous.
    Ambiguous families are excluded here for the same reason
    :func:`condemned_families` excludes them: the premise "these rungs are one
    ladder" is already disproven, so their era composition decides nothing.
    """
    priced = []
    for r in rows:
        price, _ = proposition_price(r)
        if price is None:
            continue
        priced.append({**r, "_p": price, "_branch": branch_of_priced_leg(r)})
    by_id = {r["market_id"]: r for r in priced}

    lad = read_name_ladders(priced, price_key="_p", context_key=CONTEXT)
    amb = ambiguous_families(lad)
    cond = condemned_families(lad)
    eligible = [k for k, v in lad.items() if len(v["rungs"]) >= 2 and k not in amb]

    def branches_of(key):
        seen = {by_id[m]["_branch"] for m in lad[key]["member_ids"] if m in by_id}
        seen.discard(None)
        return seen

    def new():
        return {"families": 0, "condemned": 0, "violating_pairs": 0, "markets": 0}

    tally = collections.defaultdict(new)
    rollup = collections.defaultdict(new)
    for key in eligible:
        seen = branches_of(key)
        label = "+".join(sorted(seen)) if seen else "unpriced"
        for row in (tally[label], rollup[MIXED if len(seen) > 1 else "pure"]):
            row["families"] += 1
            row["markets"] += len(lad[key]["member_ids"])
            if key in cond:
                row["condemned"] += 1
                row["violating_pairs"] += len(
                    monotonicity_violations(lad[key]["rungs"], key[1]))
    for row in list(tally.values()) + list(rollup.values()):
        row["condemn_rate_pct"] = round(
            100.0 * row["condemned"] / max(1, row["families"]), 2)

    n_elig = max(1, len(eligible))
    n_cond = max(1, sum(v["condemned"] for v in rollup.values()))
    mixed = rollup.get(MIXED, new())
    return {
        "eligible_families": len(eligible),
        "by_branch_set": {k: dict(v) for k, v in sorted(tally.items())},
        "pure_vs_mixed": {k: dict(v) for k, v in sorted(rollup.items())},
        # Lesson 18's test, computed rather than eyeballed. A rule excluding
        # era-mixed families is worth banking only when the guilty share is high
        # AND the exposed share is low; both halves are printed because either
        # one alone reads as a result and is not one.
        "concentration": {
            "condemned_that_are_mixed_pct": round(
                100.0 * mixed["condemned"] / n_cond, 1),
            "eligible_that_are_mixed_pct": round(
                100.0 * mixed["families"] / n_elig, 1),
        },
    }


#: Magnitude buckets for :func:`violation_shape`, in probability points. A
#: reversal of a tick is a different object from a reversal of twenty points,
#: and pooling them is what lets a 28-70% condemnation rate look like one thing.
MAGNITUDE_BUCKETS = ((0.005, "<=0.5pp"), (0.02, "0.5-2pp"), (0.05, "2-5pp"),
                     (0.10, "5-10pp"), (1.01, ">10pp"))


def violation_shape(rows):
    """HOW BIG are the reversals, and on families of what SIZE?

    The remaining explanation for a 28-70% condemnation rate, once era (b) and
    timing (a) are dead, is that the law is being asked to referee NOISE. A
    two-rung family is condemned by a single strictly-wrong pair, so a family
    whose two rungs sit a tick apart on either side of the same number will be
    condemned about half the time by coin-flip alone — and the O/U book is
    dense with adjacent lines priced within a point of each other.

    Two measurements decide it, and they are printed together because either
    alone can be argued away:

      * ``by_rung_count`` — if the condemned population is overwhelmingly
        two-rung families, the rate is a statement about how short the ladders
        are, not about how wrong they are;
      * ``by_magnitude`` — the size of the price reversal in each violating
        pair. A real mispricing shows a wide reversal. A book that is merely
        being over-measured shows a spike at the smallest bucket.

    🔴 A MAGNITUDE FLOOR WOULD BE A THRESHOLD, AND CAL-P136 ALREADY REFUSED ONE.
    This arm exists to size the shape, not to propose that the floor be tuned
    until the rate looks acceptable. What it can legitimately support is the
    opposite claim: that the population under the floor is noise the law should
    never have been pointed at. Which of the two it is, the numbers below decide.
    """
    priced = []
    for r in rows:
        price, _ = proposition_price(r)
        if price is not None:
            priced.append({**r, "_p": price})
    lad = read_name_ladders(priced, price_key="_p", context_key=CONTEXT)
    amb = ambiguous_families(lad)
    cond = condemned_families(lad)
    eligible = [k for k, v in lad.items() if len(v["rungs"]) >= 2 and k not in amb]

    size = collections.defaultdict(lambda: {"families": 0, "condemned": 0})
    mag = collections.defaultdict(int)
    worst_per_family = []
    for key in eligible:
        n = len(lad[key]["rungs"])
        label = str(n) if n < 5 else "5+"
        size[label]["families"] += 1
        if key not in cond:
            continue
        size[label]["condemned"] += 1
        gaps = [abs(hp - lp) for _, lp, _, hp
                in monotonicity_violations(lad[key]["rungs"], key[1])]
        worst_per_family.append(max(gaps))
        for gap in gaps:
            for edge, name in MAGNITUDE_BUCKETS:
                if gap <= edge:
                    break
            mag[name] += 1
    for row in size.values():
        row["condemn_rate_pct"] = round(
            100.0 * row["condemned"] / max(1, row["families"]), 2)

    total_pairs = max(1, sum(mag.values()))
    worst_per_family.sort()
    return {
        "eligible_families": len(eligible),
        "condemned_families": len(worst_per_family),
        "by_rung_count": {k: dict(size[k]) for k in sorted(size)},
        "by_magnitude": {name: {"pairs": mag[name],
                                "pct": round(100.0 * mag[name] / total_pairs, 1)}
                         for _, name in MAGNITUDE_BUCKETS if name in mag},
        "worst_reversal_per_condemned_family": {
            "median_pp": round(100 * worst_per_family[len(worst_per_family) // 2], 2)
            if worst_per_family else None,
            "p90_pp": round(100 * worst_per_family[int(0.9 * len(worst_per_family))], 2)
            if worst_per_family else None,
        },
    }


#: How close ``over + under`` must sit to one before the pair counts as a real
#: two-sided price. CAL-P136 measured this band on the same book (99.4% of
#: soccer's equal pairs, 91.5% of esports'), so it is inherited rather than
#: invented here.
SUM_TOLERANCE = 0.01


def _min_flips(values, direction):
    """Fewest rungs that must be read as ``1 - p`` for the family to obey the law.

    Exact, not greedy. Each rung has two candidate prices — the one stored, and
    the one the OPPOSITE leg would give — so the cheapest legal assignment is a
    two-state dynamic program over the rungs in ascending value order. Returns
    ``None`` when no assignment satisfies the law, which is a real answer and
    not a zero: it means the family is broken in a way a leg swap cannot explain.
    """
    ok = ((lambda prev, cur: cur <= prev) if direction == "dec"
          else (lambda prev, cur: cur >= prev))
    reachable = [(values[0], 0), (1.0 - values[0], 1)]
    for price in values[1:]:
        nxt = []
        for cand, cost in ((price, 0), (1.0 - price, 1)):
            feasible = [c for v, c in reachable if ok(v, cand)]
            if feasible:
                nxt.append((cand, cost + min(feasible)))
        if not nxt:
            return None
        reachable = nxt
    return min(cost for _, cost in reachable)


def leg_swap_test(rows):
    """🔴 Are the condemned ladders MISPRICED, or are their LEGS SWAPPED?

    This is the question the worst examples force, and it is the one that
    decides whether CAL-P136's refusal was reading a bad book or a bad ROW.
    ``Jordan Walker: Home Runs O/U 0.5`` is priced 0.20 and ``O/U 1.5`` is
    priced 0.989. As Over prices those are impossible — a player cannot be less
    likely to hit one home run than two. As an Over and an UNDER they are
    unremarkable: ``1 - 0.989`` is 0.011, exactly the P(2+) that 0.20 implies.

    So the test is not "how wrong is the price" but "how many rungs would have
    to be read from the other leg for the family to obey the law", and
    :func:`_min_flips` answers it exactly. The distribution is the evidence:

      * a spike at ONE flip means a per-market leg-assignment defect — a data
        bug in the writer, which the monotonicity law is correctly detecting;
      * a flat spread across many flips means the prices are simply noisy and
        the swap story is a coincidence;
      * ``no_assignment`` families are broken in some third way and are counted
        rather than absorbed into either reading.

    ``flip_matches_the_other_leg_pct`` is the corroboration, and it is the part
    that makes this more than curve-fitting: ``1 - over`` is only literally the
    Under price when the pair sums to one. Where it does, "flip this rung"
    and "read this market's other leg" are the SAME operation, and the swap
    stops being an inference about arithmetic and becomes a claim about a
    specific column in a specific row.

    ⚠️ THIS ARM PROPOSES NO RULE. A leg-assignment defect is repaired by fixing
    the rows, not by excluding them from the curve; an exclusion rule here would
    delete the evidence of a bug that is also wrong everywhere else the price is
    read. What it changes is WHICH pillar owns the finding.
    """
    priced = []
    for r in rows:
        price, reason = proposition_price(r)
        if price is not None:
            priced.append({**r, "_p": price, "_leg": reason})
    by_id = {r["market_id"]: r for r in priced}
    lad = read_name_ladders(priced, price_key="_p", context_key=CONTEXT)
    amb = ambiguous_families(lad)
    cond = condemned_families(lad) - amb

    hist = collections.Counter()
    no_assignment = 0
    one_flip_families = 0
    sum_checked = sum_ok = 0
    for key in cond:
        rungs = lad[key]["rungs"]
        values = [rungs[v] for v in sorted(rungs)]
        flips = _min_flips(values, key[1])
        if flips is None:
            no_assignment += 1
            continue
        hist[flips if flips < 4 else "4+"] += 1
        if flips == 1:
            one_flip_families += 1
        # Corroboration: on this family's markets, is ``1 - over`` actually the
        # stored Under? Counted per MARKET rather than per family so a large
        # family cannot outvote the rest.
        for mid in lad[key]["member_ids"]:
            row = by_id.get(mid)
            if not row or row["_leg"] != "over":
                continue
            over, under = row.get("over_price"), row.get("under_price")
            if over is None or under is None:
                continue
            sum_checked += 1
            if abs(float(over) + float(under) - 1.0) <= SUM_TOLERANCE:
                sum_ok += 1

    total = max(1, sum(hist.values()) + no_assignment)
    return {
        "condemned_families": len(cond),
        "min_flips_histogram": {str(k): hist[k] for k in sorted(hist, key=str)},
        "no_assignment_fixes_it": no_assignment,
        "one_flip_share_of_condemned_pct": round(100.0 * one_flip_families / total, 1),
        "flip_matches_the_other_leg_pct": round(100.0 * sum_ok / max(1, sum_checked), 1),
        "over_under_pairs_checked": sum_checked,
    }


#: A price this close to a boundary is a SETTLEMENT, not a forecast. The book
#: writes 0.001/0.9995 as well as 0.01/0.99, so the test is a band rather than
#: an equality; widening it further would start swallowing genuine longshots,
#: and ``near_boundary_but_not_settled`` counts what the band leaves out so the
#: choice is auditable rather than asserted.
SETTLED_LO, SETTLED_HI = 0.01, 0.99


def settled_step_test(rows):
    """🔴 Is a SETTLED O/U ladder even arithmetically possible?

    This is the test the worst examples demand, and it needs no threshold, no
    holdout and no opinion about the law. Once a game is over there is exactly
    one total T, and the whole ladder's truth is decided by it: every line below
    T settles Over=1, every line above settles Over=0. A settled O/U ladder is
    therefore a STEP FUNCTION — a run of ones followed by a run of zeros — and
    that is a fact about arithmetic rather than a pricing convention anyone can
    disagree with.

    So a settled family that reads 209.5→0.99, 210.5→0.01, 212.5→0.99 is not a
    mispriced ladder and not a stale one. It is asserting that the game's total
    was simultaneously above 212.5 and below 210.5. **No T exists.** The rows
    are wrong, and the monotonicity law was only ever the messenger.

    Reported in three parts, because they carry different weight:

      * ``all_settled`` families, where the step test is exact and decisive;
      * of those, how many admit NO consistent total (``contradictory``);
      * ``partly_settled`` families, where at least one rung is a live price and
        the step test does not apply — sized, and then left alone rather than
        judged by a test that does not govern them.

    ⚠️ The direction is read off the family key, never assumed. A ``dec`` family
    prices the Over (falls as the line rises) and an ``inc`` family the Under;
    inverting that assumption is precisely the sign error CAL-P135 spent a
    session removing, and hard-coding it here would reintroduce it one level up.
    """
    priced = []
    for r in rows:
        price, _ = proposition_price(r)
        if price is not None:
            priced.append({**r, "_p": price})
    lad = read_name_ladders(priced, price_key="_p", context_key=CONTEXT)
    amb = ambiguous_families(lad)
    cond = condemned_families(lad)
    eligible = [k for k, v in lad.items() if len(v["rungs"]) >= 2 and k not in amb]

    def settled(p):
        return p <= SETTLED_LO or p >= SETTLED_HI

    by_mix = collections.defaultdict(lambda: {"families": 0, "condemned": 0})
    out = {"eligible_families": len(eligible), "contradictory": 0,
           "contradictory_and_condemned": 0,
           "near_boundary_but_not_settled": 0}
    for key in eligible:
        rungs = lad[key]["rungs"]
        vals = [rungs[v] for v in sorted(rungs)]
        out["near_boundary_but_not_settled"] += sum(
            1 for p in vals if not settled(p) and (p <= 0.05 or p >= 0.95))
        n_settled = sum(1 for p in vals if settled(p))
        mix = ("all_live" if n_settled == 0
               else "all_settled" if n_settled == len(vals)
               else "mixed_settlement")
        by_mix[mix]["families"] += 1
        if key in cond:
            by_mix[mix]["condemned"] += 1
        if mix != "all_settled":
            continue
        # A step function: ones then zeros for ``dec``, zeros then ones for
        # ``inc``. Any later rung contradicting an earlier one means no total T
        # can satisfy the whole family.
        highs = [p >= SETTLED_HI for p in vals]
        ok = (highs == sorted(highs, reverse=True) if key[1] == "dec"
              else highs == sorted(highs))
        if not ok:
            out["contradictory"] += 1
            if key in cond:
                out["contradictory_and_condemned"] += 1
    for row in by_mix.values():
        row["condemn_rate_pct"] = round(
            100.0 * row["condemned"] / max(1, row["families"]), 2)
    n_cond = max(1, sum(v["condemned"] for v in by_mix.values()))
    n_elig = max(1, len(eligible))
    mixed = by_mix["mixed_settlement"]
    out["by_settlement_mix"] = {k: dict(by_mix[k]) for k in sorted(by_mix)}
    # Lesson 18 again, on the class the worst examples actually pointed at. A
    # family holding BOTH a settled rung and a live one is asserting two
    # different moments at once, and the two shares below decide whether
    # excluding it is a concentrated fix or another disagreement with the book.
    out["concentration"] = {
        "condemned_that_are_mixed_settlement_pct": round(
            100.0 * mixed["condemned"] / n_cond, 1),
        "eligible_that_are_mixed_settlement_pct": round(
            100.0 * mixed["families"] / n_elig, 1),
    }
    out["contradictory_share_of_all_settled_pct"] = round(
        100.0 * out["contradictory"] / max(1, by_mix["all_settled"]["families"]), 1)
    return out


#: How many condemned families :func:`worst_examples` writes out in full.
#: Enough to see a pattern, few enough that a reader actually reads them.
EXAMPLE_COUNT = 12


def worst_examples(rows):
    """The condemned families with the WIDEST reversals, written out in full.

    Every arm above is a rate. A rate cannot answer the question the rates
    raise — whether a "family" is one ladder at all — and after CAL-P136's
    lesson 23 that question has no guard left standing: scoping the key drove
    ``families_ambiguous`` to zero on every cell, so ``duplicate_values`` no
    longer catches a key that over-groups, and the entire correctness of every
    condemnation now rests on ``group_id`` being the right identity.

    So this arm prints the evidence a human has to look at: for the widest
    reversals, every member market's name and price under one key. If the names
    describe one proposition at different lines, the book really is reversed by
    that much. If they describe different propositions, the key is wrong and
    every rate above is measuring the key rather than the book.

    Sorted by reversal size on purpose: the widest cases are where a
    mis-grouping is most visible, and they are also the cases a rule would
    delete first.
    """
    priced = []
    for r in rows:
        price, _ = proposition_price(r)
        if price is not None:
            priced.append({**r, "_p": price})
    by_id = {r["market_id"]: r for r in priced}
    lad = read_name_ladders(priced, price_key="_p", context_key=CONTEXT)
    amb = ambiguous_families(lad)
    ranked = []
    for key in condemned_families(lad):
        if key in amb:
            continue
        pairs = monotonicity_violations(lad[key]["rungs"], key[1])
        ranked.append((max(abs(hp - lp) for _, lp, _, hp in pairs), key, pairs))
    ranked.sort(key=lambda t: -t[0])

    out = []
    for gap, key, pairs in ranked[:EXAMPLE_COUNT]:
        members = [by_id[m] for m in lad[key]["member_ids"] if m in by_id]
        blanked, direction = key
        out.append({
            "worst_reversal_pp": round(100 * gap, 2),
            "direction": direction,
            "family_key": blanked.replace(CONTEXT_SEP, "  ||  "),
            "distinct_group_ids": len({m["group_id"] for m in members}),
            "distinct_event_ids": len({m["event_id"] for m in members}),
            "rungs": {str(k): v for k, v in sorted(lad[key]["rungs"].items())},
            "members": [{"market_id": m["market_id"], "name": m["name"],
                         "price": m["_p"], "branch": m.get("over_branch")
                         or m.get("yes_branch")}
                        for m in sorted(members, key=lambda m: m["market_id"])],
        })
    return out


#: Spread buckets for :func:`as_of_spread`, in hours. A ladder written in one
#: sitting lands in the first; a family whose rungs were captured days apart is
#: the shape hypothesis (a) describes.
SPREAD_BUCKETS = ((1, "<1h"), (24, "1h-1d"), (24 * 7, "1d-7d"),
                  (float("inf"), ">7d"))

#: Branches whose price IS the opening price, and therefore whose as-of is
#: ``opening_captured_at``. :data:`~pull_eras.CAL_EQ_OPEN` qualifies BECAUSE of
#: the writer's Fallback: the value in the calibration column is the opening
#: value, so the opening capture time dates it.
DATED_BRANCHES = (OPEN, CAL_EQ_OPEN)


def as_of_spread(rows):
    """Hypothesis (a), on the sub-book where the rungs' as-of is actually KNOWN.

    CAL-P136 parked (a) as needing the price-history table, on the ground that
    ``futures_outcomes`` has no as-of. That is true of the CAL branch and false
    of the rest: where the price is an OPENING price — the ``open`` branch, and
    the ``cal_eq_open`` rows the writer's Fallback filled from it —
    ``opening_captured_at`` dates the exact number the law compared.

    So this arm restricts to families where EVERY rung is dated, measures the
    wall-clock spread between the earliest and latest rung, and reports the
    condemnation rate per spread bucket. If (a) is the mechanism, the rate
    climbs with the spread; if it is flat, families whose rungs were written
    seconds apart are condemned as often as families written a week apart and
    (a) is dead on this sub-book.

    ⚠️ IT IS A SUB-BOOK, NOT THE BOOK (lesson 19, and lesson 6 in both
    directions). ``dated_families`` against ``eligible_families`` is printed so
    nobody reads this arm as a statement about the cell.
    """
    priced = []
    for r in rows:
        price, reason = proposition_price(r)
        if price is None:
            continue
        priced.append({**r, "_p": price,
                       "_branch": r.get(f"{reason}_branch"),
                       "_at": r.get(f"{reason}_open_at")})
    by_id = {r["market_id"]: r for r in priced}
    lad = read_name_ladders(priced, price_key="_p", context_key=CONTEXT)
    amb = ambiguous_families(lad)
    cond = condemned_families(lad)
    eligible = [k for k, v in lad.items() if len(v["rungs"]) >= 2 and k not in amb]

    tally = collections.defaultdict(lambda: {"families": 0, "condemned": 0})
    dated = 0
    for key in eligible:
        members = [by_id[m] for m in lad[key]["member_ids"] if m in by_id]
        if not all(m["_branch"] in DATED_BRANCHES and m["_at"] for m in members):
            continue
        dated += 1
        stamps = sorted(datetime.fromisoformat(m["_at"]) for m in members)
        hours = (stamps[-1] - stamps[0]).total_seconds() / 3600.0
        for edge, label in SPREAD_BUCKETS:
            if hours < edge:
                break
        tally[label]["families"] += 1
        if key in cond:
            tally[label]["condemned"] += 1
    for row in tally.values():
        row["condemn_rate_pct"] = round(
            100.0 * row["condemned"] / max(1, row["families"]), 2)
    return {
        "eligible_families": len(eligible),
        "dated_families": dated,
        "dated_share_of_eligible_pct": round(
            100.0 * dated / max(1, len(eligible)), 1),
        "by_rung_as_of_spread": {label: dict(tally[label])
                                 for _, label in SPREAD_BUCKETS
                                 if label in tally},
    }


def as_of_reach(rows):
    """How far hypothesis (a) can be answered AT ALL from this table.

    Coverage first, spread second, and the spread only where coverage allows it.
    Reporting a median day-spread computed over the 2% of rows that carry a
    stamp would be a statement about that 2% wearing the whole cell's name.
    """
    have = collections.Counter()
    priced = 0
    for r in rows:
        price, reason = proposition_price(r)
        if price is None:
            continue
        priced += 1
        for stamp in ("open_at", "changed_at"):
            if r.get(f"{reason}_{stamp}") is not None:
                have[stamp] += 1
    return {
        "priced_markets": priced,
        "priced_leg_has_opening_captured_at": have["open_at"],
        "priced_leg_has_price_changed_at": have["changed_at"],
        "opening_captured_at_coverage_pct": round(
            100.0 * have["open_at"] / max(1, priced), 2),
        "price_changed_at_coverage_pct": round(
            100.0 * have["changed_at"] / max(1, priced), 2),
        "note": ("the CAL branch carries no as-of at all; where coverage is ~0 "
                 "hypothesis (a) is UNANSWERABLE from futures_outcomes and needs "
                 "the price-history table (lesson 21)"),
    }


def composition(rows):
    """Which branch the book takes, whole-cell and over the laddered population."""
    whole = collections.Counter()
    for r in rows:
        for leg in LEGS:
            whole[f"{leg}:{r.get(f'{leg}_branch') or 'none'}"] += 1
    priced_leg = collections.Counter()
    for r in rows:
        b = branch_of_priced_leg(r)
        if b is not None:
            priced_leg[b] += 1
    both = sum(1 for r in rows
               if r.get("over_cal") is not None and r.get("over_open") is not None)
    return {
        "markets": len(rows),
        "legs_by_branch": dict(sorted(whole.items())),
        "priced_leg_branch": dict(sorted(priced_leg.items())),
        "over_leg_carries_BOTH_branches": both,
    }


def census(cat):
    rows = as_dicts(cat)
    ids = sorted(r["market_id"] for r in rows)
    split = ids[len(ids) // 2] if ids else 0

    arms = {
        # The reproduction of CAL-P136 arm D from THESE rows. If it does not
        # match the published table, the two sessions are not measuring the same
        # thing and nothing below is readable (lesson 14).
        "D_package_coalesce": drop_rate(
            ladder_report(rows, price_key=None, context_key=CONTEXT)),
        "F_cal_branch_only": drop_rate(
            ladder_report(single_branch(rows, CAL), price_key=None,
                          context_key=CONTEXT)),
        "G_open_branch_only": drop_rate(
            ladder_report(single_branch(rows, OPEN), price_key=None,
                          context_key=CONTEXT)),
        # The calibration ERA rather than the calibration COLUMN — arm F minus
        # the rows the writer's Fallback filled from the opening price.
        "H_cal_era_only": drop_rate(
            ladder_report(single_branch(rows, CAL, drop_fallback_signature=True),
                          price_key=None, context_key=CONTEXT)),
    }

    holdout = {}
    for half, subset in (("early", [r for r in rows if r["market_id"] < split]),
                         ("late", [r for r in rows if r["market_id"] >= split])):
        holdout[half] = {
            "rows": len(subset),
            "D_package_coalesce": drop_rate(
                ladder_report(subset, price_key=None, context_key=CONTEXT)),
            "H_cal_era_only": drop_rate(
                ladder_report(
                    single_branch(subset, CAL, drop_fallback_signature=True),
                    price_key=None, context_key=CONTEXT)),
            "era_association": era_association(subset),
        }

    return {
        "category": cat,
        "population_check_vs_cal_p136": verify_against_p136(cat),
        "markets_with_more_than_one_leg_of_a_name": legs_per_name(cat),
        "composition": composition(rows),
        "arms": arms,
        "era_association": era_association(rows),
        "as_of_reach": as_of_reach(rows),
        "as_of_spread": as_of_spread(rows),
        "violation_shape": violation_shape(rows),
        "settled_step_test": settled_step_test(rows),
        "leg_swap_test": leg_swap_test(rows),
        # Printed LAST because it is the only arm a reader is expected to read
        # rather than scan, and the rates above are what send them to it.
        "worst_examples": worst_examples(rows),
        "holdout_at": split,
        "holdout": holdout,
    }


if __name__ == "__main__":
    cats = sys.argv[1:] or ["baseball", "basketball", "esports", "soccer"]
    for cat in cats:
        print(f"=== polymarket/{cat}", file=sys.stderr, flush=True)
        result = census(cat)
        with open(os.path.join(HERE, f"era-fold-{cat}.json"), "w") as fh:
            json.dump(result, fh, indent=2)
        print(json.dumps(result, indent=2), flush=True)
    merged = {}
    for name in sorted(os.listdir(HERE)):
        if name.startswith("era-fold-") and name.endswith(".json"):
            with open(os.path.join(HERE, name)) as fh:
                merged[name[len("era-fold-"):-len(".json")]] = json.load(fh)
    with open(os.path.join(HERE, "era-fold.json"), "w") as fh:
        json.dump(merged, fh, indent=2)
    print("FOLD COMPLETE", flush=True)
