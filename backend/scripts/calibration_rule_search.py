#!/usr/bin/env python3
"""CAL-P125 — score EVERY exclusion rule a folded partition admits.

Ruling 134 note: read-only, and it does not even reach production — it reads
the ``--out`` JSON a fold already wrote. No network, no database, no writes
beyond its own ``--out``.

WHY THIS FILE EXISTS
--------------------
CAL-P123's lesson 7: *"NO RULE FOUND" and "NO RULE EXISTS" are different claims,
and the second one is cheap.* Once a cell is folded, every subset of that
partition can be scored in plain Python in under a second — so a cell should
never be refused on "I tried a few arms and none worked". Cricket was refused on
**1,971 candidate rules, zero under the bar**, and that refusal is durable in a
way a judgment call is not.

That search was written ad-hoc inside one session and thrown away. This is the
same search as an instrument, so the NEXT cell costs a command rather than an
afternoon — and so that two cells refused a month apart were refused by the same
arithmetic.

WHY POOLED, AND WHY IT CANNOT BE INFERRED FROM THE CLASS TABLE
----------------------------------------------------------------
A fold prints each class's own ECE, and the obvious move is to drop the classes
with big numbers. **That does not work, and the reason is the whole point of
this file.** ECE is ``sum |winrate_b - meanprice_b| * n_b / n`` over BUCKETS, so
two classes with large opposite-signed errors in the same bucket partly CANCEL
when pooled. Dropping one of them can therefore make the cell WORSE. On cricket
the best subset over the shape x price-sum partition kept three arms whose
individual ECEs were 1.31, 16.68 and 10.6 — not the three smallest.

So every subset is re-pooled bucket by bucket from ``{n, w, sp}`` and rescored.
No arithmetic is done on the class ECEs at all.

THE HOLDOUT IS NOT OPTIONAL (lesson 2)
----------------------------------------
An exhaustive search over ``2^k`` subsets is an exhaustive search for an
OVERFIT. With ``--holdout`` the same subset is scored on both halves and the
report ranks by the WORSE half, because a rule that passes pooled and fails on
NEW is a rule that has learned the OLD half. A fold run with ``--holdout-at``
writes the halves into its JSON and this reads them automatically.

Usage::

    python3 backend/scripts/calibration_rule_search.py \\
        --in artifacts/cal-p125/whole-vm-basketball-sumband.json --bar 3.0
"""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

#: Above this many classes the powerset stops being a search and starts being a
#: way to run out of memory: 2^22 is 4.2M subsets. Refused BY NUMBER rather than
#: silently sampled — a sampled search that reports "0 under the bar" is the
#: false all-clear this whole lane exists to avoid (gotcha #53).
MAX_CLASSES = 22


def load_partition(path: str) -> tuple[dict, dict | None]:
    """``{class: {bucket: {n, w, sp}}}`` from either rail's ``--out`` JSON.

    ``calibration_cell_exact`` and ``calibration_whole_vm_fold`` write the same
    ``by_key`` / ``halves`` shape deliberately, so a rule benched on one rail can
    be re-benched on the other without touching this file.
    """
    blob = json.loads(Path(path).read_text())
    if "by_key" not in blob:
        raise SystemExit(
            f"{path} has no 'by_key' — is it a fold --out file? "
            f"(keys: {sorted(blob)[:8]})")
    return blob["by_key"], blob.get("halves")


def score(by_key: dict, keep) -> tuple[int, float | None, float | None]:
    """Pooled n / ECE / gap over the kept classes.

    Buckets are merged BEFORE the absolute value is taken. Taking it per class
    and averaging would forbid the cancellation that is the only reason a
    multi-arm rule can beat its best single arm.
    """
    bins: dict[str, dict] = {}
    for k in keep:
        for b, v in by_key[k].items():
            t = bins.setdefault(b, {"n": 0, "w": 0, "sp": 0.0})
            t["n"] += v["n"]
            t["w"] += v["w"]
            t["sp"] += v["sp"]
    n = sum(v["n"] for v in bins.values())
    if not n:
        return 0, None, None
    ece = sum(abs(v["w"] / v["n"] - v["sp"] / v["n"]) * v["n"]
              for v in bins.values()) / n * 100
    gap = sum(v["sp"] - v["w"] for v in bins.values()) / n * 100
    return n, round(ece, 2), round(gap, 2)


def subsets(classes: list[str], min_arms: int = 1):
    """Every non-empty subset, smallest first.

    Enumerated by SIZE rather than by bitmask so that ties in the report are
    broken toward the rule with fewer arms — a two-arm rule and a five-arm rule
    at the same ECE are not equally shippable, because every arm is a sentence
    a reader has to accept.
    """
    for r in range(min_arms, len(classes) + 1):
        yield from combinations(classes, r)


def search(by_key: dict, halves: dict | None, bar: float,
           min_rows: int, min_share: float) -> dict:
    classes = sorted(by_key)
    if len(classes) > MAX_CLASSES:
        raise SystemExit(
            f"{len(classes)} classes = 2^{len(classes)} subsets. Refusing rather "
            f"than sampling: a sampled search reporting '0 under the bar' is a "
            f"false all-clear. Fold on a coarser dimension, or raise "
            f"MAX_CLASSES ({MAX_CLASSES}) deliberately.")

    total_n, total_ece, total_gap = score(by_key, classes)
    floor = max(min_rows, int(total_n * min_share))

    rows = []
    for keep in subsets(classes):
        n, ece, gap = score(by_key, keep)
        if n < floor:
            continue
        rec = {"keep": list(keep), "n": n, "ece": ece, "gap": gap,
               "dropped": total_n - n,
               "dropped_pct": round((total_n - n) / total_n * 100, 1)}
        if halves:
            for h in ("OLD", "NEW"):
                hk = [k for k in keep if k in halves.get(h, {})]
                hn, hece, hgap = score(halves[h], hk) if hk else (0, None, None)
                rec[h] = {"n": hn, "ece": hece, "gap": hgap}
            both = [rec[h]["ece"] for h in ("OLD", "NEW") if rec[h]["ece"] is not None]
            # Ranked on the WORSE half. An exhaustive search over 2^k subsets is
            # an exhaustive search for an overfit, and the pooled number is the
            # one it overfits.
            rec["worst_half"] = max(both) if both else None
        rows.append(rec)

    key = (lambda r: (r["worst_half"] if r.get("worst_half") is not None else r["ece"],
                      len(r["keep"])))
    rows.sort(key=key)
    passing = [r for r in rows
               if (r["worst_half"] if r.get("worst_half") is not None else r["ece"]) < bar]
    return {"classes": classes, "total": {"n": total_n, "ece": total_ece,
                                          "gap": total_gap},
            "bar": bar, "floor_rows": floor, "searched": len(rows),
            "passing": passing, "ranked": rows}


def render(res: dict, top: int) -> None:
    t = res["total"]
    print(f"  cell as published   n={t['n']}  ECE={t['ece']}  gap={t['gap']:+}")
    print(f"  bar {res['bar']}   {len(res['classes'])} classes   "
          f"{res['searched']} subsets retaining >= {res['floor_rows']} rows")
    print()
    n_pass = len(res["passing"])
    print(f"  SUBSETS UNDER THE BAR: {n_pass} of {res['searched']}")
    print()
    has_half = bool(res["ranked"]) and res["ranked"][0].get("worst_half") is not None
    head = f"  {'ECE':>6} {'worst½':>7} {'n':>7} {'dropped':>9}  keep" if has_half \
        else f"  {'ECE':>6} {'n':>7} {'dropped':>9}  keep"
    print(head)
    for r in res["ranked"][:top]:
        keep = ", ".join(r["keep"])
        if len(keep) > 90:
            keep = keep[:87] + "..."
        if has_half:
            print(f"  {r['ece']:>6} {r['worst_half']:>7} {r['n']:>7} "
                  f"{r['dropped']:>6} ({r['dropped_pct']:>4.1f}%)  {keep}")
        else:
            print(f"  {r['ece']:>6} {r['n']:>7} "
                  f"{r['dropped']:>6} ({r['dropped_pct']:>4.1f}%)  {keep}")
    print()
    if not n_pass:
        # The claim this instrument exists to license, stated only when it has
        # actually been earned.
        print("  NO RULE EXISTS over this partition — every subset retaining "
              f">= {res['floor_rows']} rows is at or over the bar.")
        print("  Per CAL-P123 lesson 7 this is a claim about ONE partition. Run "
              "it on a second,")
        print("  differently-shaped one before recording a refusal: pooling can "
              "cancel opposite-signed arms.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", required=True,
                    help="a fold --out JSON (either rail)")
    ap.add_argument("--bar", type=float, default=3.0)
    ap.add_argument("--min-rows", type=int, default=300,
                    help="ignore subsets retaining fewer rows than this — a "
                         "rule that deletes the cell is not a rule")
    ap.add_argument("--min-share", type=float, default=0.0,
                    help="same, as a fraction of the cell (the binding one wins)")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--out")
    args = ap.parse_args()

    by_key, halves = load_partition(args.inp)
    print(f"{args.inp}")
    print()
    res = search(by_key, halves, args.bar, args.min_rows, args.min_share)
    render(res, args.top)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        # The full ranking, not only the winners: a reviewer's first question is
        # "how close was the next one", and a file holding only passes cannot
        # answer it.
        Path(args.out).write_text(json.dumps(res))
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
