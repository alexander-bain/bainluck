"""CAL-P138 — what ARE the condemned families that no leg swap can fix?

CAL-P137 §7's second reason for proposing nothing: 571 baseball and 3,843 soccer
condemned families admit NO flip assignment, "a bulk ``1 - p`` would corrupt
them", and nobody knows what they are. It parked the question as CAL-P137-3 and
said it must be answered BEFORE any repair is proposed. This answers it, offline
and free, from the same cached rows.

THE PREDICTION THIS STARTS FROM, BECAUSE A MEASUREMENT WITH NO PREDICTION IS A
NUMBER LOOKING FOR A STORY
------------------------------------------------------------------------------
A TWO-RUNG family can always be repaired. Take ``dec``: the four readings of
``(p0, p1)`` are ``(p0,p1)``, ``(p0,1-p1)``, ``(1-p0,p1)``, ``(1-p0,1-p1)``, and
all four fail only if ``p1 > p0`` and ``1-p1 > p0`` and ``p1 > 1-p0``
simultaneously — which requires ``p1 < 1-p0`` and ``p1 > 1-p0`` at once. So
``no_assignment`` is impossible below three rungs, and :func:`anatomy` checks
that the data agrees rather than asserting it. A cell whose no-assignment class
contained a two-rung family would mean the DP and this argument disagree, and
the DP would be the thing to doubt.

THE MEASUREMENT THAT ACTUALLY SEPARATES THE POPULATIONS
---------------------------------------------------------
"No assignment exists" is a statement about an EXACT law. CAL-P137 §4 measured
that soccer's condemned families are mostly one-point disagreements (median worst
reversal 1.0pp, 59.8% of violating pairs in the 0.5-2pp band) while baseball's
and basketball's are 18-30 points. Those two things cannot both be "the same
no-assignment class", and the way to tell them apart is to ask the DP the same
question with a TOLERANCE: how much slack does each family need before a leg-swap
repair becomes legal?

A family that becomes repairable at 1pp of slack is a tick-noise family the law
should arguably never have been pointed at. A family still infeasible at 10pp is
broken in a way neither noise nor a leg swap explains, and it is the only
population that genuinely blocks a repair. :func:`tolerance_ladder` prices that,
and it is the number CAL-P137-3 was asking for.

⚠️ THE TOLERANCE IS A DIAGNOSTIC, NOT A PROPOSED LAW. Relaxing the shipped
monotonicity rule by 1-10pp would be a change to the predicate the frozen curve
reads and is not proposed here or anywhere in this queue. It is used the way a
solubility test is used — to find out what a precipitate is made of, not to
recommend adding solvent.

THE THREE STRUCTURAL READINGS IT ALSO PRICES, ALL OF THEM FALSIFIABLE
-----------------------------------------------------------------------
* **over-grouping** — the scoped family key put two propositions in one family.
  Measured as the number of distinct ``event_id``s the family's markets span,
  and it matters here more than anywhere else in this book because
  ``duplicate_values`` — the guard ``ladder_coherence`` calls load-bearing —
  fires on ZERO families under the scoped key on all four cells. Lesson 23: the
  key fix removed the guard that was compensating for the key. Nothing else is
  watching this seam.
* **settlement band** — the family is not a forecast at all, it is a settled
  ladder whose rungs sit at 0.001/0.99 and disagree by micro-variation.
* **straddling the settled band** — CAL-P137 §6's mixed-settlement mechanism,
  re-asked of THIS subpopulation rather than of the condemned set as a whole.
  ⚠️ IT IS A PRICE-BAND PROXY AND NOT CAL-P137 §6's MEASURE. §6 read each rung's
  SETTLEMENT STATUS; the cached rows carry no ``is_winner``, so what is counted
  here is a family holding both a boundary price and a mid price. The two agree
  in direction and must not be quoted as the same number.

Usage::

    python3 artifacts/cal-p138/noassign-anatomy.py [category ...]
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import legswap_classes as LC  # noqa: E402

#: Slack, in probability points, at which the leg-swap DP is re-asked. Chosen to
#: straddle the bands CAL-P137 §4 measured — its ``<=0.5pp`` / ``0.5-2pp`` bands
#: are where soccer lives and its ``>10pp`` band is where baseball does — so the
#: ladder answers "which of those two is this family" rather than producing a
#: curve that has to be interpreted.
TOLERANCES = (0.005, 0.01, 0.02, 0.05, 0.10, 0.25)

#: A price this close to a boundary is a SETTLEMENT, not a forecast. Same band
#: ``era-fold.settled_step_test`` uses, inherited rather than re-chosen.
SETTLED_LO, SETTLED_HI = 0.01, 0.99

#: 🔴 THE FLIP-INVARIANT RUNG, AND IT IS WHY THE DP HAS NO MOVE.
#: A leg swap replaces ``p`` with ``1 - p``. At ``p = 0.5`` those are the SAME
#: NUMBER, so a rung sitting on the half offers the DP no second reading and
#: cannot be used to repair anything — it is a hole in the ladder that no
#: assignment can route around. Reading the worst no-assignment families in full
#: is what surfaced it: ``Tunisia vs. Netherlands: O/U 6.5`` is stored
#: ``over=0.5, under=0.5``, sitting between rungs priced 0.085 and 0.015.
#:
#: That is the coin-flip writer class the calibration notes have tracked on
#: three other cells, found here on the O/U ladders of two more. The band is
#: half a point either side because the book writes 0.495/0.505 as well as
#: 0.5/0.5, and :func:`anatomy` counts what the band leaves out
#: (``near_half_but_outside_band``) so the width is auditable rather than
#: asserted.
HALF_BAND = 0.005

#: The sibling signature: a market whose UNDER leg carries the OVER's number.
#: This is the class ``_regrade_polymarket_under_signflip`` (#137 Item 1) already
#: repairs on the GRADING side — it fires exactly where ``cp(under) ~ cp(over)``
#: — which makes its appearance here a statement about scope rather than a new
#: suspect: the grading repair saw these rows and the PRICE was left wrong.
EQUAL_LEG_TOLERANCE = 0.005

#: How many families :func:`worst_examples` writes out in full. CAL-P137 printed
#: its worst condemned families because after lesson 23 no guard is left between
#: ``group_id`` and a verdict and a human has to look; the same argument applies
#: with more force to the class nobody has ever looked at.
N_EXAMPLES = 12


def _feasible_within(values, direction, tol):
    """Is ANY leg-swap reading of this family legal with ``tol`` of slack?

    Same two-state reachability ``min_flip_assignment`` walks, with the law's
    comparison relaxed by ``tol`` and the COST dropped — the question here is
    feasibility, not how many rungs it takes.
    """
    ok = ((lambda prev, cur: cur <= prev + tol) if direction == "dec"
          else (lambda prev, cur: cur >= prev - tol))
    reachable = [values[0], 1.0 - values[0]]
    for price in values[1:]:
        nxt = [c for c in (price, 1.0 - price)
               if any(ok(v, c) for v in reachable)]
        if not nxt:
            return False
        reachable = nxt
    return True


def _first_break(values, direction):
    """The rung index at which every reading dies, and the values around it.

    The DP fails at a specific place. Naming it turns "no assignment exists"
    from a verdict into a located defect a reader can go and look at.
    """
    ok = ((lambda prev, cur: cur <= prev) if direction == "dec"
          else (lambda prev, cur: cur >= prev))
    reachable = [values[0], 1.0 - values[0]]
    for i, price in enumerate(values[1:], start=1):
        nxt = [c for c in (price, 1.0 - price)
               if any(ok(v, c) for v in reachable)]
        if not nxt:
            return i, tuple(round(v, 4) for v in reachable), round(price, 4)
        reachable = nxt
    return None, (), None


#: How far a flip-invariant rung must sit from a sibling, IN THE DIRECTION THE
#: LAW FORBIDS, before it reads as a placeholder rather than a genuine even line.
#: A soccer total really can be a coin flip, and 0.495-0.505 is a legitimate
#: price for one; what is not legitimate is a 0.5 sitting between rungs priced
#: 0.085 and 0.015. Fifteen points is well outside CAL-P137 §4's ``5-10pp``
#: band, so a family caught by this is not caught by tick noise.
ISOLATED_HALF_GAP = 0.15


def _has_isolated_half(values, direction):
    """Is a rung on the half CONTRADICTED by a sibling, not merely sitting there?

    The flip-invariant count alone conflates two different things: a book whose
    lines are genuinely near even (soccer, where ~80% of families contain such a
    rung in EVERY class, so it discriminates nothing) and a placeholder jammed
    into a real ladder (``Tunisia vs. Netherlands: O/U 6.5`` at 0.5 between
    0.085 and 0.015). This separates them by asking whether the half rung breaks
    the law against some sibling by more than :data:`ISOLATED_HALF_GAP`.
    """
    for i, v in enumerate(values):
        if abs(v - 0.5) > HALF_BAND:
            continue
        for j, other in enumerate(values):
            if i == j:
                continue
            # ``values`` is in ascending RUNG order, so j < i is a LOWER rung.
            bad = ((v - other) if j < i else (other - v)) if direction == "dec" \
                else ((other - v) if j < i else (v - other))
            if bad > ISOLATED_HALF_GAP:
                return True
    return False


def _worst_reversal(values, direction):
    """Largest law-violating gap in the family AS STORED, in probability points."""
    worst = 0.0
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            lo, hi = values[i], values[j]
            bad = (hi - lo) if direction == "dec" else (lo - hi)
            worst = max(worst, bad)
    return round(worst * 100, 2)


def anatomy(cat):
    rows = LC.as_dicts(cat)
    priced, lad, amb, cond = LC._families(rows)
    owner = LC._rung_owner(priced)
    by_id = {r["market_id"]: r for r in priced}

    noassign, flip1 = [], []
    for key in cond:
        rungs = lad[key]["rungs"]
        ordered = sorted(rungs)
        values = [rungs[v] for v in ordered]
        cost, unique, _ = LC.min_flip_assignment(values, key[1])
        rec = {"key": key, "ordered": ordered, "values": values,
               "member_ids": [owner.get((key, v)) for v in ordered]}
        if cost is None:
            noassign.append(rec)
        elif cost == 1 and unique:
            flip1.append(rec)

    def profile(pop, label):
        rung_hist = collections.Counter(len(r["ordered"]) for r in pop)
        direction = collections.Counter(r["key"][1] for r in pop)
        events = collections.Counter()
        settled_all = settled_any = 0
        mixed_settle = 0
        both_legs = both_legs_sum1 = both_legs_equal = 0
        half_family = equal_family = isolated_half = 0
        near_half_outside = 0
        worst = []
        breaks = collections.Counter()
        for r in pop:
            ids = [m for m in r["member_ids"] if m is not None]
            evs = {by_id[m].get("event_id") for m in ids if m in by_id}
            events[len(evs)] += 1
            band = [v <= SETTLED_LO or v >= SETTLED_HI for v in r["values"]]
            if band and all(band):
                settled_all += 1
            if any(band):
                settled_any += 1
            if any(band) and not all(band):
                mixed_settle += 1
            # The flip-invariant rung: at 0.5 a leg swap is the identity, so the
            # DP has no second reading of this rung to try.
            if any(abs(v - 0.5) <= HALF_BAND for v in r["values"]):
                half_family += 1
                if _has_isolated_half(r["values"], r["key"][1]):
                    isolated_half += 1
            elif any(abs(v - 0.5) <= 0.02 for v in r["values"]):
                near_half_outside += 1
            got_equal = False
            for m in ids:
                row = by_id.get(m)
                if not row:
                    continue
                o, u = row.get("over_price"), row.get("under_price")
                if o is None or u is None:
                    continue
                both_legs += 1
                if abs(float(o) + float(u) - 1.0) <= 0.01:
                    both_legs_sum1 += 1
                if abs(float(o) - float(u)) <= EQUAL_LEG_TOLERANCE:
                    both_legs_equal += 1
                    got_equal = True
            if got_equal:
                equal_family += 1
            worst.append(_worst_reversal(r["values"], r["key"][1]))
            idx, _, _ = _first_break(r["values"], r["key"][1])
            breaks[idx if idx is not None else "none"] += 1
        worst.sort()
        n = max(1, len(pop))
        return {
            "label": label,
            "families": len(pop),
            "rung_count_histogram": dict(sorted(rung_hist.items())),
            "min_rungs": min(rung_hist) if rung_hist else None,
            "direction": dict(direction),
            "distinct_event_ids_per_family": dict(sorted(events.items())),
            "families_spanning_more_than_one_event_pct":
                round(100.0 * sum(c for k, c in events.items() if k > 1) / n, 1),
            "all_rungs_in_settled_band_pct": round(100.0 * settled_all / n, 1),
            "some_rungs_in_settled_band_pct": round(100.0 * settled_any / n, 1),
            "rungs_straddle_the_settled_price_band_pct":
                round(100.0 * mixed_settle / n, 1),
            "over_under_pairs_checked": both_legs,
            "over_plus_under_equals_one_pct":
                round(100.0 * both_legs_sum1 / max(1, both_legs), 1),
            # 🔴 The two signatures the worst examples surfaced. The first is the
            # DP-blocking one; the second is the class #137 Item 1 already
            # repairs on the grading side.
            "has_a_flip_invariant_rung_pct": round(100.0 * half_family / n, 1),
            "has_an_ISOLATED_half_rung_pct": round(100.0 * isolated_half / n, 1),
            "near_half_but_outside_band_pct":
                round(100.0 * near_half_outside / n, 1),
            "has_a_market_whose_under_equals_its_over_pct":
                round(100.0 * equal_family / n, 1),
            "over_equals_under_markets": both_legs_equal,
            "worst_reversal_pp": {
                "median": worst[len(worst) // 2] if worst else None,
                "p90": worst[int(len(worst) * 0.9)] if worst else None,
                "max": worst[-1] if worst else None,
            },
            "dp_dies_at_rung_index": dict(sorted(breaks.items(), key=lambda kv: str(kv[0]))),
        }

    ladder = {}
    for tol in TOLERANCES:
        ok = sum(1 for r in noassign
                 if _feasible_within(r["values"], r["key"][1], tol))
        ladder[f"{tol:.3f}"] = {
            "repairable_families": ok,
            "pct_of_no_assignment": round(100.0 * ok / max(1, len(noassign)), 1),
        }

    # The families still infeasible at the widest slack are the only population
    # that genuinely blocks a repair, so they are the ones printed in full.
    hard = [r for r in noassign
            if not _feasible_within(r["values"], r["key"][1], TOLERANCES[-1])]
    hard.sort(key=lambda r: -_worst_reversal(r["values"], r["key"][1]))
    examples = []
    for r in hard[:N_EXAMPLES]:
        examples.append({
            "family_key": r["key"][0],
            "direction": r["key"][1],
            "worst_reversal_pp": _worst_reversal(r["values"], r["key"][1]),
            "rungs": [
                {"value": v, "price": round(p, 4), "market_id": m,
                 "name": (by_id.get(m) or {}).get("name"),
                 "event_id": (by_id.get(m) or {}).get("event_id"),
                 "over": (by_id.get(m) or {}).get("over_price"),
                 "under": (by_id.get(m) or {}).get("under_price"),
                 "yes": (by_id.get(m) or {}).get("yes_price")}
                for v, p, m in zip(r["ordered"], r["values"], r["member_ids"])],
        })

    return {
        "cell": f"polymarket/{cat}",
        "families_condemned": len(cond),
        "families_ambiguous_kept_by_the_duplicate_guard": len(amb),
        "no_assignment": profile(noassign, "no_assignment"),
        "unique_one_flip": profile(flip1, "unique_one_flip"),
        # The subpopulation a repair would actually have to leave alone, profiled
        # on its own rather than inferred from the class that contains it — a
        # class's composition is not a bound on its worst part (lesson 17).
        "hard_infeasible": profile(hard, "still_infeasible_at_widest_slack"),
        "tolerance_ladder": ladder,
        "still_infeasible_at_widest_slack": len(hard),
        "still_infeasible_pct_of_condemned":
            round(100.0 * len(hard) / max(1, len(cond)), 1),
        "worst_examples": examples,
    }


if __name__ == "__main__":
    cats = sys.argv[1:] or ["baseball", "basketball", "esports", "soccer"]
    for cat in cats:
        print(f"=== polymarket/{cat}", file=sys.stderr, flush=True)
        out = anatomy(cat)
        with open(os.path.join(HERE, f"noassign-{cat}.json"), "w") as fh:
            json.dump(out, fh, indent=2)
        print(json.dumps(out, indent=2), flush=True)
    merged = {}
    for name in sorted(os.listdir(HERE)):
        if name.startswith("noassign-") and name.endswith(".json"):
            merged[name[len("noassign-"):-len(".json")]] = json.load(
                open(os.path.join(HERE, name)))
    with open(os.path.join(HERE, "noassign.json"), "w") as fh:
        json.dump(merged, fh, indent=2)
    print("ANATOMY COMPLETE", flush=True)
