#!/usr/bin/env python3
"""CAL-P112 — a FULL-FIDELITY replica of one published cell, and its rule bench.

``calibration_cell_shape_fold.py`` is a shape CENSUS: it scales to a
100,000-row cell but stops before dedup, so its row count runs high. This is
the other half — for a cell small enough to page out at outcome granularity
(roughly <= 6,000 candidate rows) it applies the published predicate all the
way through ``deduped``, so a candidate exclusion rule can be benched against a
population that reproduces the payload.

Measured on 2026-08-28 for ``kalshi/tech``:

    replica  n=1,218  ECE 10.75  gap -8.97
    payload  n=1,193  ECE 11.10  gap -9.49

2.1% high on n, 0.35 pp low on ECE. The residual is the two approximations this
file cannot avoid from a single cell's slice and does not hide:

* **vm_id cardinality is computed within the slice.** ``virtual_market`` groups
  a market with its siblings when its ``group_id`` or ``event_id`` carries >= 3
  markets IN THE SAME SOURCE — siblings in another category are invisible here,
  so a market that is grouped in production can read ungrouped here and take
  the ``rn = 1`` branch instead of the multi branch.
* **Source-inapplicable filters are omitted** (poly placeholder / never-traded,
  soccer 2-way, draw authority, golf placeholder, weather wide spread, void).
  Each is either source- or category-gated away from the target cell.

**Every number this file produces must be printed beside the payload's own for
the same cell.** A replica that is not shown to reproduce is a parallel rail
wearing the published curve's name, which is the CAL-P108 finding exactly.

WHAT THE BENCH IS FOR
-----------------------
``--rule`` scores a candidate exclusion the way the loop in
``CALIBRATION-SCORECARD.md`` §9 needs it scored: the cohort it drops, the cell
it leaves, and — the part that is usually skipped — the SAME split on an
out-of-sample half, so a rule that only fits the half it was designed on says
so before it is built. The holdout splits on ``market_id``, which is monotone
with market creation, so NEW is genuinely later data.

Usage::

    python3 backend/scripts/calibration_cell_replica.py \\
        --source kalshi --category tech --rule bundle_multiwin --holdout
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.resolution_authority import (  # noqa: E402
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES,
)

ELIGIBLE_SQL = "(" + ",".join(f"'{s}'" for s in sorted(CALIBRATION_TRUTH_ELIGIBLE_SOURCES)) + ")"
ROW_CAP = 1000

#: Mirrors ``precompute_calibration._KALSHI_PROP_THRESHOLD_RE`` /
#: ``KALSHI_PROP_THRESHOLD_DEGENERATE_BAND`` / ``EXCLUSIVITY_PROVED_RELATIONS``.
#: Imported by value rather than from the module because the module is the
#: frozen file and this script must not import it into a read path that could
#: later be mistaken for a write into it.
PROP_THRESHOLD_RE = re.compile(r"^.+:\s*\d+\+\s*$")
PROP_THRESHOLD_BAND = 0.90
PROVED_RELATIONS = frozenset({"competitors", "exclusive_ranges"})
MEX_SUM_THRESHOLD = 1.15


def db_query(sql: str, limit: int = ROW_CAP, retries: int = 5) -> dict:
    base = os.environ["BAINLUCK_API"].rstrip("/")
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            f"{base}/api/admin/db-query", data=body,
            headers={"Authorization": "Bearer " + os.environ["ADMIN_TOKEN"],
                     "Content-Type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=180).read().decode())
        except urllib.error.HTTPError as e:
            last = e.read().decode()[:300]
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"db-query failed after {retries} attempts: {last}")


def load_cell(source: str, category: str) -> tuple[list, dict]:
    """Page out every candidate outcome of the cell, plus its markets' shape."""
    outcomes, last = [], 0
    while True:
        r = db_query(f"""
SELECT fo.id, fo.market_id, left(fo.name, 80) AS oname,
   COALESCE(fo.calibration_probability, fo.opening_probability) AS cp,
   fo.opening_probability AS op,
   CASE WHEN fo.is_winner THEN 1 ELSE 0 END AS win,
   CASE WHEN EXISTS (SELECT 1 FROM futures_odds_snapshots fos
                     WHERE fos.outcome_id = fo.id
                       AND (fos.yes_bid > 0 OR fos.last_price > 0))
        THEN 1 ELSE 0 END AS liquid
FROM futures_outcomes fo
JOIN futures_markets fm ON fm.id = fo.market_id
WHERE fm.source = '{source}' AND fm.llm_sport_category = '{category}'
  AND fm.status = 'resolved' AND fo.id > {last}
  AND fo.opening_probability IS NOT NULL
  AND fo.opening_probability > 0 AND fo.opening_probability < 1
  AND fo.resolution_source IN {ELIGIBLE_SQL}
ORDER BY fo.id""")
        outcomes += r["rows"]
        if r["row_count"] < ROW_CAP:
            break
        last = r["rows"][-1][0]

    ids = ",".join(str(i) for i in sorted({o[1] for o in outcomes}))
    markets, seen = {}, 0
    while seen < len(ids.split(",")):
        r = db_query(f"""
SELECT fm.id, fm.market_type, fm.mutually_exclusive, fm.group_id, fm.event_id,
   fm.market_metadata->'shape'->>'exhaustive' AS sh_ex,
   fm.market_metadata->'shape'->>'expected_winners' AS sh_ew,
   fm.market_metadata->'shape'->>'outcome_relation' AS sh_rel,
   (SELECT COUNT(*) FROM futures_outcomes x WHERE x.market_id = fm.id) AS n_all,
   (SELECT COUNT(*) FROM futures_outcomes x
     WHERE x.market_id = fm.id AND x.is_winner) AS w_all
FROM futures_markets fm WHERE fm.id IN ({ids}) AND fm.id > {seen}
ORDER BY fm.id""")
        for row in r["rows"]:
            markets[row[0]] = dict(zip(
                ["id", "mt", "mex", "gid", "eid", "sh_ex", "sh_ew", "sh_rel",
                 "n_all", "w_all"], row))
        if r["row_count"] < ROW_CAP:
            break
        seen = r["rows"][-1][0]
    return outcomes, markets


def build(outcomes: list, markets: dict, source: str, category: str) -> list:
    """Apply the published predicate from ``ranked_outcomes`` through ``deduped``."""
    gsize, esize = defaultdict(int), defaultdict(int)
    for m in markets.values():
        if m["gid"]:
            gsize[m["gid"]] += 1
        if m["eid"]:
            esize[m["eid"]] += 1

    rows = []
    for oid, mid, oname, cp, op, win, liquid in outcomes:
        m = markets[mid]
        if m["gid"] and gsize[m["gid"]] >= 3:
            vm, grouped = "g:" + m["gid"], True
        elif m["eid"] and esize[m["eid"]] >= 3:
            vm, grouped = "e:" + str(m["eid"]), True
        else:
            vm, grouped = "m:" + str(mid), False
        rows.append(dict(oid=oid, mid=mid, name=oname or "", cp=float(cp),
                         op=float(op), win=win, liquid=liquid, vm=vm,
                         grouped=grouped, mt=m["mt"], n_all=m["n_all"],
                         w_all=m["w_all"]))

    elig = defaultdict(int)
    for r in rows:
        elig[r["vm"]] += 1

    proved, cpsum = set(), defaultdict(float)
    for r in rows:
        if r["liquid"]:
            cpsum[r["mid"]] += r["cp"]
    for mid, m in markets.items():
        if (m["mt"] == "field" and m["sh_ex"] == "true" and m["sh_ew"] == "1"
                and m["sh_rel"] in PROVED_RELATIONS and m["w_all"] == 1):
            proved.add(mid)

    liquid_members = defaultdict(int)
    for r in rows:
        if r["liquid"]:
            liquid_members[r["mid"]] += 1

    for r in rows:
        m = markets[r["mid"]]
        r["elig"] = elig[r["vm"]]
        r["is_multi"] = r["grouped"] or r["elig"] >= 3
        r["cp_sum"] = cpsum[r["mid"]]
        r["x_liquid"] = (source == "kalshi" and not r["liquid"])
        r["x_prop"] = (source == "kalshi"
                       and bool(PROP_THRESHOLD_RE.match(r["name"]))
                       and (category == "hockey" or r["cp"] >= PROP_THRESHOLD_BAND))
        r["x_nowin"] = (m["n_all"] >= 2 and m["w_all"] == 0)
        r["x_malf"] = bool(m["mex"]) and m["n_all"] == 2 and m["w_all"] != 1
        r["x_orphan"] = (m["mt"] == "field" and m["n_all"] <= 1)
        r["x_bundle"] = (category == "esports" and m["n_all"] >= 3 and m["w_all"] >= 2)

    def per_outcome_ok(r):
        return not (r["x_liquid"] or r["x_prop"] or r["x_nowin"] or r["x_malf"]
                    or r["x_orphan"] or r["x_bundle"])

    surv, survwin = defaultdict(int), defaultdict(int)
    for r in rows:
        if per_outcome_ok(r):
            surv[r["mid"]] += 1
            survwin[r["mid"]] += r["win"]

    for r in rows:
        mid = r["mid"]
        candidate = mid in proved and liquid_members[mid] >= 3
        if candidate and r["cp_sum"] > MEX_SUM_THRESHOLD:
            complete = (surv[mid] == liquid_members[mid] and survwin[mid] >= 1)
            r["is_mex_norm"] = complete
            r["is_field_incomplete"] = not complete
            r["adj"] = r["cp"] / r["cp_sum"] if complete else r["cp"]
        else:
            r["is_mex_norm"] = False
            r["is_field_incomplete"] = False
            r["adj"] = r["cp"]

    byvm = defaultdict(list)
    for r in rows:
        byvm[r["vm"]].append(r)
    for rs in byvm.values():
        for i, r in enumerate(sorted(rs, key=lambda x: (abs(x["op"] - 0.5), x["oid"])), 1):
            r["rn"] = i

    modecount = defaultdict(int)
    for r in rows:
        if (r["is_multi"] and r["elig"] >= 3 and r["liquid"]
                and not r["is_mex_norm"] and not r["is_field_incomplete"]):
            modecount[(r["vm"], round(r["adj"], 6))] += 1
    mode = {k for k, c in modecount.items() if c > max(elig[k[0]] * 0.5, 2)}

    published = []
    for r in rows:
        if not per_outcome_ok(r) or r["is_field_incomplete"]:
            continue
        if r["is_mex_norm"]:
            keep = True
        elif r["is_multi"]:
            keep = (0.005 < r["adj"] < 0.98) and (r["vm"], round(r["adj"], 6)) not in mode
        else:
            keep = (r["rn"] == 1)
        if keep:
            published.append(r)
    return published


def fold(rs: list) -> tuple[int, float | None, float | None]:
    bins = defaultdict(lambda: {"n": 0, "w": 0, "sp": 0.0})
    for r in rs:
        b = bins[min(9, int(r["adj"] * 10))]
        b["n"] += 1
        b["w"] += r["win"]
        b["sp"] += r["adj"]
    n = sum(b["n"] for b in bins.values())
    if not n:
        return 0, None, None
    ece = sum(abs(b["w"] / b["n"] - b["sp"] / b["n"]) * b["n"] for b in bins.values()) / n * 100
    gap = sum(b["sp"] - b["w"] for b in bins.values()) / n * 100
    return n, round(ece, 2), round(gap, 2)


def shape_class(r: dict) -> str:
    if r["w_all"] == 0:
        return "void_0win"
    if r["n_all"] >= 3 and r["w_all"] >= 2:
        return "bundle_multiwin"
    if r["n_all"] >= 3 and r["w_all"] == 1:
        return "field_1win"
    if r["n_all"] == 2:
        return "binary_1win" if r["w_all"] == 1 else "binary_other"
    return "single"


RULES = {
    # The SHIPPED esports test, category-extended. Realization-based.
    "bundle_multiwin": lambda r: r["n_all"] >= 3 and r["w_all"] >= 2,
    # Realization-independent: a partition sums to ~1, a bundle to N x p.
    "nonpartition_sum": lambda r: (r["n_all"] >= 3
                                   and r["cp_sum"] > MEX_SUM_THRESHOLD),
    "single_capture": lambda r: r["n_all"] == 1,
    "binary_other": lambda r: r["n_all"] == 2 and r["w_all"] != 1,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--rule", action="append", default=[],
                    help=f"one or more of {sorted(RULES)}; applied cumulatively")
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()

    outcomes, markets = load_cell(args.source, args.category)
    published = build(outcomes, markets, args.source, args.category)
    n, e, g = fold(published)
    print(f"{args.source}/{args.category}  candidates={len(outcomes)} "
          f"markets={len(markets)}")
    print(f"  REPLICA of the published cell : n={n} ECE={e} gap={g}")
    print("  >>> compare with the payload's own n/ECE/gap for this cell <<<")

    print("\n  by shape class:")
    groups = defaultdict(list)
    for r in published:
        groups[shape_class(r)].append(r)
    for k, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        kn, ke, kg = fold(rs)
        print(f"    {k:18s} n={kn:6d} ECE={ke:6.2f} gap={kg:+7.2f}")

    result = {"source": args.source, "category": args.category,
              "replica": {"n": n, "ece": e, "gap": g},
              "by_class": {k: dict(zip(("n", "ece", "gap"), fold(v)))
                           for k, v in groups.items()},
              "rules": {}}

    if args.rule:
        preds = [RULES[name] for name in args.rule]
        drop = lambda r: any(p(r) for p in preds)  # noqa: E731
        kept = [r for r in published if not drop(r)]
        gone = [r for r in published if drop(r)]
        print(f"\n  RULE {'+'.join(args.rule)}")
        print(f"    drops    n={fold(gone)[0]:6d} ECE={fold(gone)[1]} gap={fold(gone)[2]}")
        print(f"    leaves   n={fold(kept)[0]:6d} ECE={fold(kept)[1]} gap={fold(kept)[2]}")
        result["rules"]["+".join(args.rule)] = {
            "dropped": dict(zip(("n", "ece", "gap"), fold(gone))),
            "kept": dict(zip(("n", "ece", "gap"), fold(kept)))}

        if args.holdout:
            mids = sorted({r["mid"] for r in published})
            cut = mids[len(mids) // 2]
            print(f"\n    HOLDOUT on market_id, cut={cut}")
            for label, sel in (("OLD ", lambda r: r["mid"] < cut),
                               ("NEW ", lambda r: r["mid"] >= cut)):
                sub = [r for r in published if sel(r)]
                k = [r for r in sub if not drop(r)]
                d = [r for r in sub if drop(r)]
                print(f"      {label} before {fold(sub)}  dropped {fold(d)}  after {fold(k)}")
                result["rules"]["+".join(args.rule)][label.strip()] = {
                    "before": dict(zip(("n", "ece", "gap"), fold(sub))),
                    "dropped": dict(zip(("n", "ece", "gap"), fold(d))),
                    "after": dict(zip(("n", "ece", "gap"), fold(k)))}

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
