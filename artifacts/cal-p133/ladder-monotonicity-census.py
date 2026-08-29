#!/usr/bin/env python3
"""Census the nested-ladder monotonicity law over one cell's outcome rows.

Produces every number quoted in ``app/utils/ladder_monotonicity``'s docstring,
so no figure in that module is a claim without a named producer — the CAL-P105
defect this lane keeps paying for.

INPUT is the flat outcome-row dump this script does NOT pull, because a census
and a fold must never load production at the same time. Produce it first with
a chunked, split-on-cap pull of::

    fm.id, fm.market_type, fm.name, fo.name,
    COALESCE(fo.calibration_probability, fo.opening_probability),
    fo.is_winner, fo.resolution_source

⚠️ ``is_winner`` is present in the dump and is NEVER read here. It is carried so
one dump can serve both this census and an outcome-side check later; the
leakage guard lives in ``tests/test_ladder_monotonicity.py``, which asserts the
module has no outcome read site at all.

    python3 artifacts/cal-p133/ladder-monotonicity-census.py <rows.json> <label> [out.json]
"""
from __future__ import annotations

import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from app.utils.ladder_monotonicity import (  # noqa: E402
    DEC,
    INC,
    flat_pairs,
    ladder_report,
    monotonicity_violations,
    name_rungs,
    outcome_ladder,
    read_name_ladders,
)

# Column order of the dump.
MID, MTYPE, MNAME, ONAME, PRICE, IS_WINNER, RES_SRC = range(7)


def name_site(rows: list) -> dict:
    """One row per market: its name and its YES-leg price."""
    yes: dict = {}
    meta: dict = {}
    for r in rows:
        meta[r[MID]] = (r[MNAME], r[MTYPE])
        if str(r[ONAME] or "").strip().lower() == "yes" and r[PRICE] is not None:
            yes[r[MID]] = float(r[PRICE])
    recs = [{"market_id": mid, "name": meta[mid][0], "yes_price": yes.get(mid)}
            for mid in meta]
    report = ladder_report(recs)

    ladders = read_name_ladders(recs)
    multi = {k: v for k, v in ladders.items() if len(v["rungs"]) >= 2}
    worst = sorted(
        ((k, v, monotonicity_violations(v["rungs"], k[1])) for k, v in multi.items()),
        key=lambda t: -len(t[2]))
    report["census"]["markets_with_a_yes_price"] = len(yes)
    report["census"]["by_direction"] = dict(
        collections.Counter(k[1] for k in multi))
    report["worst_families"] = [
        {"key": k[0], "direction": k[1], "rungs": len(v["rungs"]),
         "violations": len(viol), "flat_pairs": len(flat_pairs(v["rungs"])),
         "prices": [[val, v["rungs"][val]] for val in sorted(v["rungs"])]}
        for k, v, viol in worst[:12] if viol]
    return report


def outcome_site(rows: list) -> dict:
    """Markets whose OWN outcome list is an all-``+`` cumulative ladder."""
    bym: dict = collections.defaultdict(list)
    for r in rows:
        bym[r[MID]].append(r)

    ladders, violating, flat, examined = {}, [], 0, 0
    plus_but_mixed = 0
    for mid, rs in bym.items():
        outs = [{"name": r[ONAME], "price": r[PRICE]} for r in rs]
        rungs = outcome_ladder(outs)
        if rungs is None:
            from app.utils.ladder_monotonicity import parse_plus_bracket
            if any(parse_plus_bracket(str(o["name"])) for o in outs):
                plus_but_mixed += 1
            continue
        examined += 1
        ladders[mid] = rungs
        viol = monotonicity_violations(rungs, DEC)
        flat += len(flat_pairs(rungs))
        if viol:
            violating.append({
                "market_id": mid, "name": rs[0][MNAME],
                "market_type": rs[0][MTYPE],
                "violations": len(viol),
                "prices": [[v, rungs[v]] for v in sorted(rungs)]})
    return {
        "markets_all_plus_cumulative": examined,
        "markets_with_a_plus_leg_but_mixed": plus_but_mixed,
        "markets_violating": len(violating),
        "violating_pairs": sum(v["violations"] for v in violating),
        "flat_pairs": flat,
        "violating_detail": sorted(
            violating, key=lambda v: -v["violations"])[:20],
    }


def main() -> None:
    src, label = sys.argv[1], sys.argv[2]
    dest = sys.argv[3] if len(sys.argv) > 3 else None
    rows = json.load(open(src))

    ns = name_site(rows)
    os_ = outcome_site(rows)
    out = {"label": label, "outcome_rows": len(rows),
           "markets": len({r[MID] for r in rows}),
           "name_site": ns, "outcome_site": os_}

    c = ns["census"]
    print(f"=== {label} ===")
    print(f"  outcome rows {len(rows)}   markets {out['markets']}"
          f"   with a YES price {c['markets_with_a_yes_price']}")
    print("  -- NAME site (rung in the market name, price = YES leg)")
    print(f"     families {c['families']}  multi-rung {c['families_multi_rung']} "
          f"{c['by_direction']}  singleton {c['families_singleton']}")
    print(f"     ambiguous {c['families_ambiguous']}  "
          f"untestable-duplicate-only {c['families_untestable_duplicate_only']}")
    print(f"     CONDEMNED families {c['families_condemned']}   "
          f"violating pairs {c['violating_pairs']}   flat pairs {c['flat_pairs']}")
    total = c["markets_drop"] + c["markets_ambiguous"] + c["markets_coherent"]
    print(f"     markets  drop {c['markets_drop']}  ambiguous {c['markets_ambiguous']}"
          f"  coherent {c['markets_coherent']}   (in a testable ladder: {total})")
    print("  -- OUTCOME site (whole ladder inside one market, all-'+' legs)")
    print(f"     all-plus cumulative {os_['markets_all_plus_cumulative']}   "
          f"has a '+' leg but mixed {os_['markets_with_a_plus_leg_but_mixed']}")
    print(f"     VIOLATING markets {os_['markets_violating']}   "
          f"pairs {os_['violating_pairs']}   flat pairs {os_['flat_pairs']}")

    if ns["worst_families"]:
        print("\n  worst NAME-site families:")
        for f in ns["worst_families"][:6]:
            print(f"    [{f['direction']}] {f['violations']}v/{f['rungs']}r "
                  f":: {f['key'][:74]}")
    if os_["violating_detail"]:
        print("\n  worst OUTCOME-site markets:")
        for v in os_["violating_detail"][:6]:
            print(f"    {v['market_id']} {v['violations']}v :: {str(v['name'])[:60]}")
            print(f"        {[[f'{a:g}', b] for a, b in v['prices']]}")

    if dest:
        # The id sets are the rule's PARTITION, not a summary, so they are
        # written out sorted rather than dropped — a later fold has to be able
        # to reproduce the exact arm each market landed in without re-running
        # the census against a production database that has moved on.
        for arm in ("drop", "ambiguous", "coherent"):
            ns[arm] = sorted(ns[arm])
        json.dump(out, open(dest, "w"), indent=1)
        print(f"\n  -> {dest}")


if __name__ == "__main__":
    main()
