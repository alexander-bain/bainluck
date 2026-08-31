#!/usr/bin/env python3
"""CAL-P142 — the row path's wall time is not a property of the cell, and the
exact-fold instrument treats it as if it were.

WHAT HAPPENED
-------------
`calibration_phantom_curve.py --cell --source polymarket --category soccer`
ran 35 of 64 Stage A residues fine (106,613 roster rows, 1,494 s) and then died:

    RuntimeError: Stage A residue 547 mod 524288 irreducible at depth 13 —
    the roster read cannot be chunked small enough for the row path

That sentence says *one residue holds too many rows to fit under the row cap*.
The residue is unremarkable — 2,694 rows across 541 vm_ids, and while that is
over `ROW_CAP` (1,000) and so must split, it is nowhere near unsplittable.

🔴 **I FIRST CONCLUDED THE WRONG THING AND THIS FILE IS THE CORRECTION.**
One pass of the probe below said `polymarket/soccer` had a ~7 s per-query floor
against every other cell's ~2-3 s, including cells 1.6x larger, and that read as
a clean size-independent per-cell signal. Three more passes destroyed it:

    pass   soccer                 kalshi/baseball        hockey
    1      6.1 / 4.2 / 4.9 s      3.3 / 2.4 / 2.1 s      3.3 / 2.1 / 2.2 s
    2      3.9 / 3.6 / 10.3 s     TIMEOUT / 6.4 / 2.5 s  2.9 / 4.5 / 2.5 s
    3      4.4 / 3.1 / 3.1 s      TIMEOUT x3             1.9 / 1.9 / 7.0 s
    4      8.2 / 3.7 / 3.7 s      2.0 / 1.5 / 1.5 s      1.7 / 1.6 / 1.7 s

Same query, same residue, minutes apart: 1.5 s to over 10 s. `kalshi/baseball`
timed out three times out of three in pass 3 and ran in 2.0 s in pass 4 — and it
is a cell CAL-P126 already folded successfully end to end. **The variance is not
about the cell.** It is production load, and it swamps whatever per-cell
component exists. My first table was noise with a story attached.

(This is CAL-P141's lesson arriving on the next session: it compared two
duplication numbers without checking what population each counted; I compared
five wall times without checking what else varied between them. Neither is a
reading error — both are a missing control.)

WHAT IS ACTUALLY TRUE
---------------------
1. **The row path's cap is a hard 10 s.** `timeout_ms` is accepted *only* with
   `explain: true` — the row path returns HTTP 400
   ``"`timeout_ms` is only supported with `explain: true`"``. There is no budget
   to raise. Measured, not quoted from prose.
2. **Any residue query can exceed it at any time, for any cell**, per the table
   above.
3. 🔴 **`_read_hash_chunk` has no retry, and converts a transient timeout into a
   permanent verdict.** Its docstring is explicit that this is deliberate:

       Truncation and statement-timeout are the same fact wearing two faces —
       the residue class is too big — and only one of them is loud. Both split.

   For truncation that is right: halving a residue halves its rows, so the split
   converges. For a *load* timeout it is wrong in a specific way — halving the
   residue does not make the database less busy, so both halves are just as
   likely to time out, and the recursion doubles the query count at every level
   until it hits the depth-12 cap and raises. One unlucky second becomes an
   exponential cascade and then an error message about row counts.

4. Therefore `polymarket/soccer` is **not** established as unmeasurable. It is
   established as *not yet measured*, on a rail that fails non-deterministically
   and reports the failure as if it were structural.

CONFIRMED BY RE-RUN — the failure moves
---------------------------------------
Point 3 predicts that a second identical run should die at a *different*
residue, since nothing about any particular residue is the cause. It does:

    run 1   died at residue 547    mod 524288  ->  547    mod 64 = 35
            after completing 35 of 64 residues (106,613 roster rows, 1,494 s)
    run 2   died at residue 131101 mod 524288  ->  131101 mod 64 = 29
            after completing 30 of 64 residues

Same cell, same partition, same code, ~40 minutes apart, two different
"irreducible" residues. The decisive detail: **residue 29 completed cleanly in
run 1** — it is one of the 35 that went through — and then run 2 declared that
same residue irreducible. A residue that reads fine once is not irreducible.
(Run 2 died before reaching residue 35, so it says nothing either way about run
1's accused residue; the asymmetry is because Stage A walks residues in order.)

**The word in the error message is wrong**, and a reader who trusts it will go
looking for a fat identity group that does not exist. Run 1's accused residue,
35 mod 64, holds 2,694 rows across 541 vm_ids — over `ROW_CAP` so it must split,
but entirely ordinary.

The fix is a retry with backoff before the split, so that a load blip costs a
second instead of an exponential cascade and a false structural verdict. That is
a change to `calibration_whole_vm_fold.py`, which this session did not make: the
lane is frozen and the fix is somebody's call, not a measurement's.

WHAT THIS SCRIPT IS FOR
-----------------------
It measures the wall-time distribution of an (almost) empty residue —
`stage_a_sql(..., n=524288, k)`, which returns 0-2 rows, so its time is the
population CTE's cost and nothing else — across cells and across repeats. Use it
to answer "is the row path healthy enough right now to attempt an exact fold?",
which is a question about the *moment*, not about the cell.

**Run it more than once.** A single pass told me the opposite of the truth.

EXITS
-----
0  no probe exceeded the cap and the slowest left at least MARGIN_S of headroom
5  at least one probe timed out or came within MARGIN_S of the cap — the row
   path is loaded right now; an exact fold attempted in this window will
   probably die somewhere unpredictable and blame a residue for it

    python3 artifacts/cal-p142/floor-cost.py
    python3 artifacts/cal-p142/floor-cost.py --passes 4 --json out.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

#: The row path's hard ceiling. Not a config value anywhere — `timeout_ms` is
#: refused on the row path (explain-only), so this is the server default and
#: there is no knob. Measured, not quoted from prose.
ROW_PATH_CAP_S = 10.0

#: Headroom below which a probe counts as "the rail is loaded". Observed spread
#: is 1.5 s to >10 s on the SAME query, so this is a liveness threshold for the
#: moment, not a property of any cell.
MARGIN_S = 3.5

#: A modulus wide enough that a residue class is empty or holds a couple of
#: vm_ids, so the query's wall time is the CTE preamble and nothing else.
EMPTY_MODULUS = 524288
PROBE_RESIDUES = (547, 548, 512)

DEFAULT_CELLS = [
    "polymarket/soccer",
    "polymarket/baseball",
    "polymarket/basketball",
    "polymarket/hockey",
    "kalshi/baseball",
]


def _load():
    spec = importlib.util.spec_from_file_location(
        "wvf", ROOT / "backend" / "scripts" / "calibration_whole_vm_fold.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def probe(wvf, source: str, category: str) -> list[dict]:
    """One rep per residue. A timeout IS an observation, not a failed one."""
    cce = wvf.cce
    reps = []
    for k in PROBE_RESIDUES:
        sql = wvf.stage_a_sql(source, category, EMPTY_MODULUS, k)
        t0 = time.time()
        try:
            r = cce.db_query(sql, limit=cce.ROW_CAP)
            reps.append({"k": k, "secs": round(time.time() - t0, 2),
                         "rows": r["row_count"], "timeout": False})
        except cce.QueryTimeout:
            reps.append({"k": k, "secs": round(time.time() - t0, 2),
                         "rows": None, "timeout": True})
    return reps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", nargs="*", default=DEFAULT_CELLS)
    ap.add_argument("--passes", type=int, default=1,
                    help="repeat the whole sweep; ONE PASS IS NOT ENOUGH")
    ap.add_argument("--json")
    args = ap.parse_args()

    wvf = _load()
    print("CAL-P142 ROW-PATH LIVENESS — wall time of an empty residue, by cell")
    print(f"  hard cap {ROW_PATH_CAP_S:.0f}s (timeout_ms is explain-only), "
          f"loaded under {MARGIN_S:.1f}s headroom")
    print("  the same query has measured 1.5s and >10s minutes apart — read the "
          "SPREAD, not any one number")
    print()

    observations, hot = [], []
    for p in range(1, args.passes + 1):
        if args.passes > 1:
            print(f"  --- pass {p} ---")
        print("  %-24s %9s  %s" % ("cell", "slowest", "reps"))
        for spec in args.cells:
            source, _, category = spec.partition("/")
            reps = probe(wvf, source, category)
            observations.append({"pass": p, "cell": spec, "reps": reps})
            timed_out = any(r["timeout"] for r in reps)
            clean = [r["secs"] for r in reps if not r["timeout"]]
            slowest = ROW_PATH_CAP_S if timed_out else max(clean)
            loaded = timed_out or (ROW_PATH_CAP_S - slowest) < MARGIN_S
            if loaded:
                hot.append((p, spec, "TIMEOUT" if timed_out
                            else "%.1fs" % slowest))
            shown = " ".join("TIMEOUT" if r["timeout"] else "%.1fs" % r["secs"]
                             for r in reps)
            print("  %-24s %8s%s  %s%s"
                  % (spec, "%.1fs" % slowest, ">" if timed_out else " ",
                     shown, " 🔴" if loaded else ""))
        print()

    if hot:
        print("  🔴 EXIT 5 — the row path was loaded on "
              f"{len(hot)} of {len(observations)} cell-passes:")
        for p, spec, s in hot:
            print(f"       pass {p}  {spec}  slowest {s}")
        print("     An exact fold attempted now will likely die at whichever "
              "residue happens to be unlucky, and _read_hash_chunk will report "
              "it as 'irreducible' — a claim about row counts, for a failure "
              "that is about load. Re-run the fold rather than believing it.")
    else:
        print("  EXIT 0 — every probe had room under the cap on every pass.")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"cap_s": ROW_PATH_CAP_S, "margin_s": MARGIN_S,
             "observations": observations,
             "loaded_cell_passes": [{"pass": p, "cell": c, "slowest": s}
                                    for p, c, s in hot]}, indent=2))
    return 5 if hot else 0


if __name__ == "__main__":
    sys.exit(main())
