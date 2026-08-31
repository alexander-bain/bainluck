#!/usr/bin/env python3
"""CAL-P122 — the losers the published curve never sees, and whether they exist.

Ruling 134 note: this is a READ-ONLY instrument. It writes nothing, it imports
the frozen ``precompute_calibration`` population chain rather than
re-implementing it, and ``git diff origin/master -- backend/app/ frontend/`` is
empty on the branch that carries it.

WHY THIS FILE EXISTS
--------------------
CAL-P112 named a class it called the **winner-only single capture** and banked
**RULE E2** to exclude it:

    453 markets, 453 outcomes, 453 winners -- a win rate of 1.000 at an average
    published price of 0.59. ``orphan_partition_markets`` deliberately does not
    catch this ("a standalone Yes/No claim with one outcome is a complete,
    scoreable prediction"), and that reasoning is right in general and false
    here: a population that is 100% winners is not a set of Yes/No claims being
    scored, it is one-sided capture.

E2 rides the ``(source, category)`` allowlist Alex ruled on 2026-08-28, so it
lands on every cell that allowlist admits. **Its premise is a claim about the
CAPTURE, and nobody has ever measured the capture.** "100% winners" is equally
consistent with a second explanation the census could not see: the losers were
captured, graded by an authoritative source, and then removed by a filter.

There is a filter that does exactly that, and it is one line::

    clean_vms AS (
        SELECT * FROM vm_stats
        WHERE eligible >= 1
          AND has_winner >= 1          -- <- this one
    ),

``has_winner`` is counted over the VIRTUAL MARKET. For a market grouped with
siblings, one winner anywhere in the group carries the whole group, so its
losers publish normally. For a **lone claim** -- an ungrouped market whose
virtual market is itself and which captured exactly one outcome -- there is
nobody else to carry it, so the row publishes if and only if it WON.

That is not what the producer says it does. Queue 299's own rung-1 predicate
carves the class out on purpose::

    def market_has_no_winner_authority(n_outcomes, n_winners):
        # A 1-outcome market is judged by market_is_orphan_partition instead
        # (a lone Yes/No claim that legitimately resolved No is not an
        # authority failure).
        return n_outcomes >= 2 and n_winners == 0

and ``orphan_partition_markets`` then declines to catch it too (it requires
``market_type = 'field'``). Both carve-outs are unreachable for a lone claim:
``clean_vms`` already deleted the row, three CTEs earlier, on a gate that
predates Queue 299 entirely (#691, 2026-05-28).

WHAT THIS MEASURES, AND WHY IT IS TWO POPULATIONS AND NOT ONE
--------------------------------------------------------------
Every row this instrument reports satisfies **every published eligibility
condition except the vm-level winner gate**: opening price in (0, 1), a
resolution source on the calibration-truth allowlist, and the Kalshi bid/trade
evidence predicate. It then splits them, because only one half is a defect:

``B_lone_claim``
    ``graded_lone_claims >= 1 AND ungraded_lone_claims = 0``. A variant holding
    at least one member market with exactly one captured outcome graded a LOSS
    by an authoritative source, and none that nothing ever graded. Queue 299
    says to publish those. ``clean_vms`` dropped them. **This is the uniquely
    dropped population and the one E2's premise is about.**

    🔴 CAL-P155 RESTATED THIS CLASS. It used to read ``market_count = 1 AND
    total_outcomes = 1`` -- a statement about the VARIANT, which counted two
    lone claims sharing one variant as ``market_count = 2`` and put them in
    ``A_also_no_winner`` beside genuine unknown truth. Alex ruled the arm
    per-MARKET (option A, alex-inbox/calibration-919), so the class is now what
    the producer actually admits.

``A_also_no_winner``
    everything else in the gate's shadow -- a virtual market of >=2 outcomes
    that graded nobody. Queue 299 rung 1 (``no_winner_markets``) removes these
    on purpose and calls them UNKNOWN truth, correctly: with ``is_winner``
    defaulting to False, an all-loser multi-outcome market is indistinguishable
    from an ungraded one. **Reported so the total cannot be mistaken for the
    defect**, never counted as one.

The split is the whole point. A census that printed one number here would say
"the gate drops 2,054 rows in this cell" when the defensible claim is 432.

THE COUNTERFACTUAL IS EXACT FOR THE SOLITARY HALF — AND CAL-P155 SPLIT THE CLASS
--------------------------------------------------------------------------------
A restored ``B_lone_claim`` row in a variant that holds ONLY it has a fully
determined path through the rest of the chain, reasoned to the end rather than
simulated:

* ``is_multi`` is ``is_grouped OR eligible >= 3``; both are false for a variant
  of one ungrouped market, so the row takes ``deduped``'s ``ELSE ro.rn = 1``
  branch.
* ``rn`` partitions by ``vm_id`` and the vm holds exactly one row, so ``rn = 1``.
* ``is_mex_normalized`` needs ``survivor_n >= 3``, so it is false and
  ``adj_opening_probability`` is the raw curve price ``COALESCE(cp, opening)``.

So that row publishes, at that price, in that bucket, as a loss. The restored
fold below adds it with ``w = 0`` and is the producer's arithmetic, not a model
of it.

🔴 **IT IS NOT EXACT FOR THE CO-LOCATED HALF, AND THAT HALF ONLY EXISTS AFTER
CAL-P155.** Two lone claims can share a variant only when the variant is ``g:``
or ``e:``, and those have ``is_grouped = true`` by construction — so
``is_multi`` is TRUE and the row takes the multi branch instead
(``adj > 0.005 AND adj < 0.98`` and not at the variant's mode price) rather than
``rn = 1``. Those three conditions can each remove a restored row. **The
restored fold is therefore an UPPER BOUND on the co-located half**, in the same
direction as the chunking bound below, and a reader must not read it as the
published count. The exact figure comes from the chain itself
(``artifacts/cal-p155/``), never from this reconstruction.

THE ONE APPROXIMATION, AND ITS DIRECTION IS KNOWN
-------------------------------------------------
The sweep is chunked on ``fm.id`` (the row path's hard 10 s budget, gotcha #53),
and ``virtual_market``'s grouping is evaluated inside a chunk. A market that
production groups with a sibling in another chunk can read UNGROUPED here --
so the class this instrument counts can only ever be over-populated, never
under-populated, by chunking. **The census is an upper bound and the bound
points one way.** ``--edge-check`` re-runs the whole sweep at half the width
and prints both totals rather than describing the risk.

Usage::

    python3 backend/scripts/calibration_missing_loser_census.py \\
        --source kalshi --category entertainment \\
        --out artifacts/cal-p122/missing-losers.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calibration_cell_exact as cce  # noqa: E402

from app.tasks.precompute_calibration import (  # noqa: E402
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
    _calibration_population_ctes,
    kalshi_liquidity_exists_sql,
)

#: The two arms of the gate's shadow. Ordered so ``B_lone_claim`` -- the one a
#: reader must not conflate with the total -- sorts last in the census table and
#: is printed with its own verdict line.
ARM_LONE = "B_lone_claim"
ARM_OTHER = "A_also_no_winner"

#: The producer text this instrument's whole premise rests on. A guard test
#: asserts it is still in the frozen file: if the gate is ever repaired, this
#: script is measuring a defect that no longer exists and must say so loudly
#: rather than print a zero (gotcha #53 -- an empty answer is a response shape).
CLEAN_VMS_GATE_FRAGMENT = "OR (graded_lone_claims >= 1"

#: CAL-P143 (12-CAL / D13): the gate was REPAIRED, so the fragment above pins
#: the repaired predicate and the guard that used to prove the defect exists now
#: proves it is gone. Pinned as a pair on purpose: a partial revert that restores
#: the bare gate while leaving the new comment block behind would satisfy a
#: presence-only check. The retired text must be ABSENT.
CLEAN_VMS_GATE_RETIRED = "WHERE eligible >= 1\n                  AND has_winner >= 1"

#: What the instrument MEANS after the repair. ``B_lone_claim`` was the
#: population the producer dropped; it is now the population the producer
#: publishes, so the census reads as a RECONCILIATION (dropped should be 0) and
#: its verdict line inverts. Stated as a constant so the report text and the
#: guard cannot drift apart.
CENSUS_MODE_AFTER_REPAIR = "reconciliation"

#: The repaired gate's restored arm, as the producer spells it. Pinned here so
#: the pure mirror below and the SQL cannot drift apart silently.
#:
#: CAL-P155 / D13 option A (Alex 2026-08-30): the arm went PER MARKET. It used
#: to read ``market_count = 1 AND total_outcomes = 1 AND graded >= 1``, which is
#: a statement about the VARIANT and therefore refused two lone claims that
#: merely shared one. This instrument's premise is the arm, so the mirror moves
#: with it or the census starts measuring a boundary the producer does not have.
RESTORED_ARM_SQL = (
    "OR (graded_lone_claims >= 1\n                            "
    "AND ungraded_lone_claims = 0)"
)


def lone_claim_is_restorable(graded_lone_claims: int,
                             ungraded_lone_claims: int) -> bool:
    """The repaired gate's second arm, as a pure function.

    The SQL is the authority; this is its mirror, so the boundary can be tested
    without a database and so :func:`classify_vm` and the producer can be held
    to the SAME boundary by one assertion instead of two readings of two
    languages.

    Both arguments are PER-MARKET counts over the variant's members, and the
    second one is the conjunct that keeps a row nothing ever graded out of the
    published curve: "not a winner" is not "a loss" (gotcha #21). It is
    fail-closed — an ungraded lone claim beside a graded one refuses the whole
    variant rather than publishing unknown truth next to a real loss.
    """
    return graded_lone_claims >= 1 and ungraded_lone_claims == 0


def classify_vm(graded_lone_claims: int, ungraded_lone_claims: int) -> str:
    """Which arm of the gate's shadow a dropped virtual market falls in.

    Pure, so the class boundary is testable without production. A lone claim is
    a MEMBER MARKET carrying exactly one captured outcome; a variant holding at
    least one that is graded, and none that is not, is the class the producer
    now publishes. Anything else in the gate's shadow is a multi-outcome market
    that graded nobody, which Queue 299 rung 1 removes on its own account and
    which this instrument must never report as the defect.
    """
    if lone_claim_is_restorable(graded_lone_claims, ungraded_lone_claims):
        return ARM_LONE
    return ARM_OTHER


def dropped_sql(source: str, category: str, lo: int, hi: int) -> str:
    """Rows the vm-level winner gate removes, by arm and bucket.

    Built on ``_calibration_population_ctes`` -- the producer's own chain -- and
    reading ``vm_stats``, which is the CTE ``clean_vms`` filters. Selecting from
    ``vm_stats`` instead of ``clean_vms`` IS the counterfactual: it is the same
    population one predicate earlier.
    """
    pop = _calibration_population_ctes(
        market_info_extra=(
            f"AND fm.source = '{source}' "
            f"AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}' "
            f"AND fm.id >= {lo} AND fm.id < {hi}"
        )
    )
    return cce._strip_sql_comments(
        "WITH " + pop + f"""
SELECT vs.graded_lone_claims AS glc,
       vs.ungraded_lone_claims AS ulc,
       LEAST(FLOOR(COALESCE(fo.calibration_probability,
                            fo.opening_probability) * 10)::int, 9) AS b,
       COUNT(*) AS n,
       ROUND(SUM(COALESCE(fo.calibration_probability,
                          fo.opening_probability))::numeric, 6) AS sp,
       SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS w
FROM vm_stats vs
JOIN virtual_market vm ON vm.vm_id = vs.vm_id AND vm.source = vs.source
JOIN futures_outcomes fo ON fo.market_id = vm.market_id
WHERE vs.eligible >= 1
  AND vs.has_winner = 0
  AND fo.opening_probability IS NOT NULL
  AND fo.opening_probability > 0 AND fo.opening_probability < 1
  AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
  AND {kalshi_liquidity_exists_sql(source="vm.source")}
GROUP BY 1, 2, 3""")


def kept_lone_sql(source: str, category: str, lo: int, hi: int) -> str:
    """The PUBLISHED half of the lone-claim class, from ``deduped``.

    The comparison the premise needs is not "how many losers are missing" but
    "what does the class look like with and without them", so the kept half has
    to come from the same chain and the same run.
    """
    pop = _calibration_population_ctes(
        market_info_extra=(
            f"AND fm.source = '{source}' "
            f"AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}' "
            f"AND fm.id >= {lo} AND fm.id < {hi}"
        )
    )
    return cce._strip_sql_comments(
        "WITH " + pop + """
SELECT LEAST(FLOOR(d.adj_opening_probability * 10)::int, 9) AS b,
       COUNT(*) AS n,
       SUM(CASE WHEN d.is_winner THEN 1 ELSE 0 END) AS w,
       ROUND(SUM(d.adj_opening_probability)::numeric, 6) AS sp
FROM deduped d
JOIN vm_stats vs ON vs.vm_id = d.vm_id AND vs.source = d.source
WHERE vs.graded_lone_claims >= 1 AND vs.ungraded_lone_claims = 0
GROUP BY 1""")


def _collect(builder, source: str, category: str, lo: int, hi: int,
             depth: int = 0) -> list:
    """One id range, splitting on BOTH failure modes of the row path.

    Mirrors ``calibration_cell_exact.collect``: a truncated answer and a
    statement timeout are the same bug -- the range is too big -- and only one
    of them is loud. Neither is ever retried at the same size.
    """
    sql = builder(source, category, lo, hi)
    if len(sql) > cce.MAX_SQL_CHARS:
        return _split(builder, source, category, lo, hi, depth,
                      "over the SQL length cap")
    try:
        r = cce.db_query(sql, limit=cce.ROW_CAP)
    except cce.QueryTimeout:
        return _split(builder, source, category, lo, hi, depth, "timing out")
    if r["row_count"] >= cce.ROW_CAP:
        return _split(builder, source, category, lo, hi, depth, "truncated")
    return r["rows"]


def _split(builder, source: str, category: str, lo: int, hi: int,
           depth: int, why: str) -> list:
    if depth > 18 or hi - lo <= 1:
        raise RuntimeError(f"chunk {lo}-{hi} still {why} at depth {depth}")
    mid = lo + (hi - lo) // 2
    return (_collect(builder, source, category, lo, mid, depth + 1)
            + _collect(builder, source, category, mid, hi, depth + 1))


def _bins():
    return defaultdict(lambda: {"n": 0, "w": 0, "sp": 0.0})


def add(bins: dict, b: int, n: int, w: int, sp: float) -> None:
    """Accumulate one (bucket, n, winners, sum-price) row.

    The bucket key is coerced to ``int`` here and nowhere else. The rail's own
    sweep keys its bins on the integer the row path returns, and these bins are
    pooled WITH the rail's in :func:`merge_bins` -- a ``"5"`` next to a ``5``
    would silently become two price bands and fold as if the cell had twice the
    buckets and half the mass in each.
    """
    v = bins[int(b)]
    v["n"] += int(n)
    v["w"] += int(w)
    v["sp"] += float(sp)


def merge_bins(*maps: dict) -> dict:
    """Pool any number of bucket->{n,w,sp} maps into a fresh one.

    Bucket maps are additive because a bucket is a price band, not a sample --
    which is why the restored folds below are the producer's own arithmetic on
    the producer's own bins rather than a second sweep with a second predicate.
    Never mutates an input: the same ``kept`` map is pooled twice below, and an
    in-place merge would make the second reading depend on the first.
    """
    out = _bins()
    for m in maps:
        for b, v in m.items():
            t = out[int(b)]
            t["n"] += v["n"]
            t["w"] += v["w"]
            t["sp"] += v["sp"]
    return out


def sweep(source: str, category: str, width: int,
          holdout_at: int | None = None) -> dict:
    rng = cce.db_query(
        f"SELECT MIN(id) AS lo, MAX(id) AS hi FROM futures_markets "
        f"WHERE source = '{source}'", limit=5)
    lo, hi = rng["rows"][0]

    edges, e = [], lo
    while e <= hi:
        edges.append(e)
        e = min(e + width, hi + 1)
    edges.append(hi + 1)
    if holdout_at and lo < holdout_at <= hi:
        edges = sorted(set(edges) | {holdout_at})

    dropped = {ARM_LONE: _bins(), ARM_OTHER: _bins()}
    kept_lone = _bins()
    halves = {h: {"dropped_lone": _bins(), "kept_lone": _bins()}
              for h in ("OLD", "NEW")}
    t0 = time.time()
    for i in range(len(edges) - 1):
        rlo, rhi = edges[i], edges[i + 1]
        half = None if not holdout_at else ("OLD" if rlo < holdout_at else "NEW")
        print(f"    [{i + 1}/{len(edges) - 1}] ids {rlo}-{rhi} "
              f"({time.time() - t0:.0f}s elapsed)", file=sys.stderr, flush=True)

        for glc, ulc, b, n, sp, w in _collect(dropped_sql, source, category,
                                              rlo, rhi):
            arm = classify_vm(int(glc), int(ulc))
            add(dropped[arm], int(b), int(n), int(w), float(sp))
            if half and arm == ARM_LONE:
                add(halves[half]["dropped_lone"], int(b), int(n), int(w),
                    float(sp))

        for b, n, w, sp in _collect(kept_lone_sql, source, category, rlo, rhi):
            add(kept_lone, int(b), int(n), int(w), float(sp))
            if half:
                add(halves[half]["kept_lone"], int(b), int(n), int(w),
                    float(sp))

    return {"dropped": {k: dict(v) for k, v in dropped.items()},
            "kept_lone": dict(kept_lone),
            "halves": {h: {k: dict(v) for k, v in d.items()}
                       for h, d in halves.items()},
            "seconds": round(time.time() - t0, 1)}


def _line(label: str, bins: dict) -> str:
    n, ece, gap = cce.fold(bins)
    if not n:
        return f"    {label:<34} {'-':>7} {'-':>8} {'-':>8}"
    w = sum(v["w"] for v in bins.values())
    return (f"    {label:<34} {n:>7} {ece:>8} {gap:>+8} "
            f"{w / n * 100:>7.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--width", type=int, default=cce.DEFAULT_WIDTH)
    ap.add_argument("--holdout-at", type=int, default=None,
                    help="a market_id; report the lone-claim class OLD (< id) "
                         "and NEW (>= id) separately")
    ap.add_argument("--edge-check", action="store_true",
                    help="re-run at half the chunk width and print both "
                         "lone-claim totals, so the chunking's known-direction "
                         "over-count is measured rather than described")
    ap.add_argument("--out")
    args = ap.parse_args()

    res = sweep(args.source, args.category, args.width, args.holdout_at)
    cell_by_key, _ = cce.sweep(args.source, args.category, "none", args.width)
    cell = cce.pool(cell_by_key)
    n, ece, gap = cce.fold(cell)
    pn, pece, pgap, meta = cce.payload_cell(args.source, args.category)

    lone = res["dropped"][ARM_LONE]
    other = res["dropped"][ARM_OTHER]
    kept = res["kept_lone"]

    print(f"{args.source}/{args.category}   (missing-loser census, "
          f"width {args.width}, {res['seconds']:.0f}s)")
    print(f"  curve generated {meta['generated_at']}  "
          f"population {meta['population_version']}")
    print()
    print("  SELF-CHECK — the producer's own chain against the payload it produced")
    print(f"    {'exact replica':<16} n={n:>7}  ECE={ece:>6}  gap={gap:>+7}")
    print(f"    {'payload':<16} n={pn:>7}  ECE={pece:>6}  gap={pgap:>+7}")
    if pn:
        print(f"    {'delta':<16} n={n - pn:>+7} ({(n - pn) / pn * 100:+.2f}%)  "
              f"ECE={ece - pece:+.2f}  gap={gap - pgap:+.2f}")
    print()
    print("  THE GATE'S SHADOW — every row below is eligible on every published")
    print("  condition except clean_vms' vm-level `has_winner >= 1`")
    print(f"    {'arm':<34} {'n':>7} {'ECE':>8} {'gap':>8} {'winrate':>8}")
    print(_line(f"{ARM_OTHER} (rung 1 owns these)", other))
    print(_line(f"{ARM_LONE} (UNIQUELY dropped)", lone))
    print()
    print("  THE LONE-CLAIM CLASS, published vs whole")
    print(f"    {'population':<34} {'n':>7} {'ECE':>8} {'gap':>8} {'winrate':>8}")
    print(_line("published today (winners only)", kept))
    print(_line("with its losers restored", merge_bins(kept, lone)))
    print()
    print("  THE CELL")
    print(f"    {'population':<34} {'n':>7} {'ECE':>8} {'gap':>8} {'winrate':>8}")
    print(_line("published today", cell))
    print(_line("with lone-claim losers restored", merge_bins(cell, lone)))
    print()

    ln, _, _ = cce.fold(lone)
    kn, _, _ = cce.fold(kept)
    if not ln and kn:
        print("  VERDICT  NO MISSING LOSERS — this cell's lone-claim class is")
        print("           genuinely one-sided capture, and E2's premise holds here.")
    elif not ln and not kn:
        print("  VERDICT  NO LONE-CLAIM CLASS — the gate cannot reach this cell.")
    else:
        print(f"  VERDICT  {ln} ELIGIBLE LOSERS ARE BEING DROPPED — this cell's")
        print(f"           lone-claim class is {kn}/{kn + ln} winners, not "
              f"{kn}/{kn}. The capture is")
        print("           two-sided; the POPULATION FILTER is one-sided.")

    if args.holdout_at:
        print()
        print(f"  HOLDOUT on market_id {args.holdout_at}")
        for h in ("OLD", "NEW"):
            print(f"    {h}")
            print(_line("  published (winners only)",
                        res["halves"][h]["kept_lone"]))
            print(_line("  losers dropped", res["halves"][h]["dropped_lone"]))

    if args.edge_check:
        print()
        alt = sweep(args.source, args.category, max(1, args.width // 2))
        an, _, _ = cce.fold(alt["dropped"][ARM_LONE])
        print(f"  EDGE CHECK  width {args.width}: {ln} lone-claim rows | "
              f"width {args.width // 2}: {an}")
        if an != ln:
            print("              THE CHUNKING IS DOING SOMETHING — the census is "
                  "an upper bound and this says by how much.")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({
            "source": args.source, "category": args.category,
            "payload": {"n": pn, "ece": pece, "gap": pgap, **meta},
            "exact": {"n": n, "ece": ece, "gap": gap},
            "cell_bins": {k: v for k, v in cell.items()},
            **res,
        }, indent=1, default=int))
        print(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
