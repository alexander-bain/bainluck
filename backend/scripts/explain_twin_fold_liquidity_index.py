#!/usr/bin/env python3
"""CAL-P092 (Alex interjection 2026-08-24) — find the twin fold's BINDING node.

Why this exists
---------------
``run.2917`` — the attended ``measure_published_twin.py --bank`` at the
5,400 s one-off ceiling — did not finish. Its durable artifact records
``fold_duration_s 5402.0``, ``QueryCanceledError``, ``db_rows 0``. That
**refutes CAL-P086B's premise by execution**: the wall is not Celery's
``soft_time_limit``, it is the query's own cost. Chunking is already closed
(#2076 options 1/2/3, CAL-P086B), so the remaining route is QUERY COST.

This script is plan-only. It sends ``{"explain": true}`` **without**
``analyze``, which the read rail composes as ``EXPLAIN (FORMAT JSON)`` and
**does not execute**. It therefore cannot time out, cannot write, and cannot
contend with the producer — the only way to interrogate a query that has never
once run to completion.

What it reports
---------------
1. **The binding node**, by self cost (total cost minus children's total cost),
   plus every correlated ``SubPlan`` with its relation, index, index condition
   and residual ``Filter``. The residual filter is the whole story: a filter on
   an index scan is a HEAP FETCH PER CANDIDATE ROW.
2. **A projected cost delta** for the proposed partial index, derived from two
   further plan-only reads of rewritten variants:

   * ``proxy`` — the liquidity ``EXISTS`` with its ``AND (...)`` residual
     REMOVED. This is exactly what the planner sees once a partial index
     carries that predicate: same subplan shape, same correlation, same
     ``outcome_id`` index condition, **no Filter**. It is a slightly
     CONSERVATIVE proxy, because the real partial index is smaller than the
     full one it stands in for.
   * ``floor`` — the ``EXISTS`` replaced by ``TRUE`` entirely. Not achievable
     and not proposed; it bounds how much of the plan's cost is attributable to
     the predicate at all, and it moves row estimates downstream, so it is a
     bound and not a projection.

⚠️ **Planner cost is not runtime, and this script never converts one into the
other.** CAL-P085 measured this fold's cost model understating real time by
``>= 2.35x``. A cost RATIO between two plans of the same query shape is the
usable signal; an absolute cost is not a second. Every number printed here is a
cost. The one duration reported is the EXPLAIN's own round trip.

Usage
-----
    source ~/.claude/.env
    python3 scripts/explain_twin_fold_liquidity_index.py
    python3 scripts/explain_twin_fold_liquidity_index.py --out /tmp/art.json

Exit codes: 0 report produced · 1 a read failed or an anchor did not match.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.sql_comment_strip import (  # noqa: E402
    count_statement_separators,
    strip_sql_comments,
)

#: The six sites carrying the full bid-or-trade evidence predicate
#: (``kalshi_liquidity_exists_sql``, ``precompute_calibration.py:436``).
LIQUIDITY_EXISTS = (
    "EXISTS (\n"
    "        SELECT 1 FROM futures_odds_snapshots fos\n"
    "        WHERE fos.outcome_id = fo.id\n"
    "          AND (fos.yes_bid > 0 OR fos.last_price > 0))"
)

#: The seventh site: the weather wide-spread guard, TRADE evidence only.
#: Its predicate ``last_price > 0`` IMPLIES the disjunction above, which is why
#: one partial index can serve both — see the DDL note in the report.
WIDE_SPREAD_EXISTS = (
    "EXISTS (\n"
    "        SELECT 1 FROM futures_odds_snapshots fos\n"
    "        WHERE fos.outcome_id = fo.id AND fos.last_price > 0)"
)

#: What the two sites look like once the predicate lives in an index predicate:
#: the residual Filter is gone and the scan is the correlation alone.
INDEXED_EXISTS = (
    "EXISTS (\n"
    "        SELECT 1 FROM futures_odds_snapshots fos\n"
    "        WHERE fos.outcome_id = fo.id)"
)

EXPECTED_SITES = 7


def build_variants() -> dict[str, str]:
    from app.utils.calibration_published_twin import published_population_fold_sql

    base = strip_sql_comments(published_population_fold_sql())
    seps = count_statement_separators(base)
    if seps:
        raise SystemExit(
            f"stripped copy still carries {seps} semicolon(s) — the rail will "
            "refuse it as multi-statement; fix the stripper, do not send it"
        )

    n_full = base.count(LIQUIDITY_EXISTS)
    n_wide = base.count(WIDE_SPREAD_EXISTS)
    if n_full + n_wide != EXPECTED_SITES:
        raise SystemExit(
            f"expected {EXPECTED_SITES} liquidity EXISTS sites, matched "
            f"{n_full} full + {n_wide} wide-spread. The population builder "
            "changed shape — re-read it before trusting any projection, "
            "because a proxy that silently rewrites FEWER sites than the "
            "baseline contains understates the delta and looks conservative."
        )

    proxy_a = base.replace(LIQUIDITY_EXISTS, INDEXED_EXISTS).replace(
        WIDE_SPREAD_EXISTS, INDEXED_EXISTS
    )
    # Candidate B carries no ``last_price`` key column, so the wide-spread site
    # keeps a residual recheck. Leaving that site verbatim scans the FULL index
    # rather than B's liquid-only subset, which makes this variant PESSIMISTIC
    # for B by roughly the liquid fraction — the right direction to be wrong in.
    proxy_b = base.replace(LIQUIDITY_EXISTS, INDEXED_EXISTS)
    floor = base.replace(LIQUIDITY_EXISTS, "TRUE").replace(WIDE_SPREAD_EXISTS, "TRUE")
    return {
        "baseline": base,
        "proxy_a": proxy_a,
        "proxy_b": proxy_b,
        "floor": floor,
        "_sites": (n_full, n_wide),
    }


def explain(sql: str, *, api: str, token: str, timeout_s: float = 180.0) -> dict:
    req = urllib.request.Request(
        f"{api}/api/admin/db-query",
        data=json.dumps({"sql": sql, "explain": True}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return {"http_error": exc.code, "body": exc.read().decode()[:2000]}
    except Exception as exc:  # noqa: BLE001
        return {"client_error": f"{type(exc).__name__}: {exc}"}


def walk(node: dict, depth: int = 0):
    yield depth, node
    for child in node.get("Plans") or []:
        yield from walk(child, depth + 1)


def summarize(result: dict) -> dict:
    if "plan" not in result:
        return {"error": result}
    root = result["plan"][0]["Plan"]

    nodes: list[dict] = []
    subplans: list[dict] = []
    for depth, node in walk(root):
        child = sum((c.get("Total Cost") or 0.0) for c in (node.get("Plans") or []))
        self_cost = (node.get("Total Cost") or 0.0) - child
        label = node.get("Node Type", "?")
        for key in ("Subplan Name", "CTE Name", "Relation Name", "Index Name"):
            if node.get(key):
                label = f"{label}[{node[key]}]"
                break
        nodes.append({"self_cost": round(self_cost, 1), "depth": depth, "node": label})
        if node.get("Parent Relationship") == "SubPlan":
            subplans.append(
                {
                    "name": node.get("Subplan Name"),
                    "node_type": node.get("Node Type"),
                    "relation": node.get("Relation Name"),
                    "index": node.get("Index Name"),
                    "total_cost": node.get("Total Cost"),
                    "plan_rows": node.get("Plan Rows"),
                    "index_cond": node.get("Index Cond"),
                    "filter": node.get("Filter"),
                }
            )
    nodes.sort(key=lambda d: -d["self_cost"])
    return {
        "total_cost": root.get("Total Cost"),
        "plan_rows": root.get("Plan Rows"),
        "explain_duration_ms": result.get("duration_ms"),
        "truncated": result.get("truncated"),
        "sql_fingerprint": result.get("sql_fingerprint"),
        "top_self_cost": nodes[:10],
        "correlated_subplans": subplans,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        print("source ~/.claude/.env first (BAINLUCK_API, ADMIN_TOKEN)", file=sys.stderr)
        return 1

    variants = build_variants()
    n_full, n_wide = variants.pop("_sites")
    out: dict = {
        "sites": {"full_predicate": n_full, "wide_spread_only": n_wide},
        "variants": {},
    }

    for label in ("baseline", "proxy_a", "proxy_b", "floor"):
        summary = summarize(explain(variants[label], api=api, token=token))
        out["variants"][label] = summary
        if "error" in summary:
            print(f"{label}: FAILED {summary['error']}", file=sys.stderr)
            return 1
        print(
            f"{label:9s} total_cost={summary['total_cost']:>14,.1f}  "
            f"rows={summary['plan_rows']}  explain_ms={summary['explain_duration_ms']}"
        )

    base_c = out["variants"]["baseline"]["total_cost"]
    floor_c = out["variants"]["floor"]["total_cost"]
    recoverable = base_c - floor_c
    out["projection"] = {
        "baseline_cost": base_c,
        "absolute_floor_cost_predicate_removed": floor_c,
        "recoverable_cost": round(recoverable, 1),
        "candidates": {},
        "caveat": (
            "Planner cost, not runtime. CAL-P085 measured this fold's cost model "
            "understating real time by >= 2.35x. The RATIO is the signal; neither "
            "number is a second. The floor variant also removes the subplans "
            "entirely, so it bounds rather than projects."
        ),
    }
    for cand, label in (("A", "proxy_a"), ("B", "proxy_b")):
        c = out["variants"][label]["total_cost"]
        out["projection"]["candidates"][cand] = {
            "projected_cost": c,
            "ratio_vs_baseline": round(c / base_c, 4),
            "reduction_pct": round(100.0 * (1 - c / base_c), 2),
            "share_of_recoverable_captured": round((base_c - c) / recoverable, 4),
        }
        print(
            "candidate {}: {:.4f}x baseline  ({:.2f}% cost reduction)  "
            "captures {:.1f}% of the recoverable".format(
                cand,
                out["projection"]["candidates"][cand]["ratio_vs_baseline"],
                out["projection"]["candidates"][cand]["reduction_pct"],
                100 * out["projection"]["candidates"][cand]["share_of_recoverable_captured"],
            )
        )
    print("floor: {:.4f}x baseline (not achievable, not proposed)".format(floor_c / base_c))

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(out, fh, indent=2, sort_keys=True)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
