#!/usr/bin/env python3
"""CAL-P086B (#2076) — ask the PLANNER whether source-chunking can work.

The question, stated exactly
----------------------------
``app/tasks/calibration_published_twin_worker.py``'s header declines to ship
#2076's option 2/3 (chunk the fold by ``source``) on a stated premise:

    "several CTEs are referenced more than once; Postgres materialises those
     rather than inlining them, so a ``WHERE d.source = ...`` on the final
     SELECT may not push down at all — in which case seven chunks each pay the
     FULL population cost and the fix makes it seven times worse."

That premise was **never measured**. This script measures it, plan-only, and it
separates two things the premise runs together:

* **TAIL** — the predicate on the final ``SELECT ... FROM deduped d``. This is
  the shape the header describes, and it is the one that has to push *through*
  six materialised CTEs.
* **ROOT** — the predicate injected into ``market_info``'s own ``WHERE``, the
  single base CTE every other CTE descends from. Nothing has to push anywhere;
  the population is simply smaller from the first scan.

Those are different fixes with different answers, and #2076's options 2/3 do not
distinguish them. If TAIL is refuted and ROOT holds, "chunking is 7x worse" is
true of the shape nobody should build and false of the shape they should.

How to run
----------
    source ~/.claude/.env
    python3 scripts/explain_twin_fold_pushdown.py            # all variants
    python3 scripts/explain_twin_fold_pushdown.py --source kalshi
    python3 scripts/explain_twin_fold_pushdown.py --out /tmp/artifact.json

Read-only in the strictest sense available: ``explain: true`` **without**
``analyze``, which the rail composes as ``EXPLAIN (FORMAT JSON)`` and does not
execute. It cannot time out, cannot write, and cannot contend with the hourly
producer — which is the entire reason the premise is answerable during a deploy
freeze while a real fold run is not.

⚠️ **Planner cost is not runtime.** CAL-P085 measured this fold's cost model
understating it by **>= 2.35x** (one calibration point, ``market_info``
130,576 -> 5,347.6 ms, extrapolating to 576 s against a measured floor of
901.96 s). So a cost RATIO between two plans of the same query shape is the
usable signal here, and an absolute cost is not a duration. Every number this
script prints is a cost; none of them is a second.
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

#: The seven chunks a source-partitioned fold would run, with the bucket counts
#: CAL-P084 recorded. Order is descending by bucket count.
SOURCES: tuple[str, ...] = (
    "kalshi",
    "polymarket",
    "odds_api",
    "odds_api_bookmaker",
    "odds_api_totals",
    "odds_api_spreads",
    "datagolf",
)

#: The exact line the ROOT injection anchors on, inside ``market_info``.
ROOT_ANCHOR = "WHERE fm.status = 'resolved'"


def build_sql() -> str:
    """The stripped, single-statement copy of the frozen fold."""
    from app.utils.calibration_published_twin import published_population_fold_sql

    sql = strip_sql_comments(published_population_fold_sql())
    seps = count_statement_separators(sql)
    if seps:
        raise SystemExit(
            f"stripped copy still carries {seps} semicolon(s) — the read rail "
            "will refuse it as multi-statement; fix the stripper, do not send it"
        )
    return sql


def tail_filtered(sql: str, source: str) -> str:
    """The naive chunk: predicate on the final SELECT over ``deduped``."""
    needle = "FROM deduped d\n"
    if sql.count(needle) != 1:
        raise SystemExit("could not locate the fold tail's FROM clause")
    return sql.replace(needle, f"FROM deduped d\nWHERE d.source = '{source}'\n")


def root_filtered(sql: str, source: str) -> str:
    """The real chunk: predicate inside ``market_info``, the base CTE."""
    if sql.count(ROOT_ANCHOR) != 1:
        raise SystemExit(
            f"could not locate the unique root anchor {ROOT_ANCHOR!r} — the "
            "frozen builder changed; re-read it before trusting this script"
        )
    return sql.replace(ROOT_ANCHOR, f"{ROOT_ANCHOR}\n                  AND fm.source = '{source}'")


def explain(sql: str, *, api: str, token: str, timeout_s: float = 120.0) -> dict:
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
    except urllib.error.HTTPError as exc:  # recorded, never swallowed
        return {"http_error": exc.code, "body": exc.read().decode()[:2000]}
    except Exception as exc:  # noqa: BLE001
        return {"client_error": f"{type(exc).__name__}: {exc}"}


def walk(node: dict, depth: int = 0):
    yield depth, node
    for child in node.get("Plans", []) or []:
        yield from walk(child, depth + 1)


def summarize(result: dict) -> dict:
    """Total cost, plus the CTE nodes and the biggest self-cost contributors."""
    if "plan" not in result:
        return {"error": result}
    root = result["plan"][0]["Plan"]
    total = root.get("Total Cost")

    ctes: list[dict] = []
    biggest: list[tuple[float, str]] = []
    node_count = 0
    sort_mb = 0.0
    for _depth, node in walk(root):
        node_count += 1
        child_cost = sum((c.get("Total Cost") or 0.0) for c in (node.get("Plans") or []))
        self_cost = (node.get("Total Cost") or 0.0) - child_cost
        label = node.get("Node Type", "?")
        for key in ("CTE Name", "Relation Name", "Index Name", "Subplan Name"):
            if node.get(key):
                label = f"{label}[{node[key]}]"
                break
        biggest.append((self_cost, label))
        if node.get("Node Type") == "CTE Scan" or node.get("Parent Relationship") == "InitPlan":
            pass
        if node.get("Subplan Name", "").startswith("CTE "):
            ctes.append(
                {
                    "cte": node["Subplan Name"][4:],
                    "total_cost": node.get("Total Cost"),
                    "plan_rows": node.get("Plan Rows"),
                }
            )
        if node.get("Sort Space Used"):
            sort_mb = max(sort_mb, node["Sort Space Used"] / 1024.0)

    biggest.sort(reverse=True)
    return {
        "total_cost": total,
        "plan_rows": root.get("Plan Rows"),
        "node_count": node_count,
        "duration_ms": result.get("duration_ms"),
        "truncated": result.get("truncated"),
        "materialized_ctes": ctes,
        "top_self_cost": [
            {"self_cost": round(c, 1), "node": lbl, "pct": None} for c, lbl in biggest[:8]
        ],
    }


def cte_reference_counts(sql: str) -> dict[str, int]:
    """How many times each CTE is REFERENCED. >1 means PG materialises it."""
    import re

    names = re.findall(r"([a-z_][a-z_0-9]*)\s+AS\s*\(", sql)
    out: dict[str, int] = {}
    for name in names:
        # references = total occurrences minus the one definition site
        out[name] = len(re.findall(rf"\b{name}\b", sql)) - 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="kalshi", help="the chunk to measure")
    ap.add_argument(
        "--all-sources",
        action="store_true",
        help="ROOT-filter every one of the seven chunks and report the SUM and the MAX. "
        "The SUM answers 'is chunking cheaper overall'; the MAX answers 'does any one "
        "chunk fit the budget', and only the second is what #2076 is blocked on.",
    )
    ap.add_argument("--out", default=None, help="write the artifact JSON here")
    ap.add_argument("--dump-sql", default=None, help="write the stripped SQL here and exit")
    args = ap.parse_args()

    sql = build_sql()
    if args.dump_sql:
        with open(args.dump_sql, "w") as fh:
            fh.write(sql)
        print(f"wrote {len(sql)} chars to {args.dump_sql}")
        return 0

    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        raise SystemExit("source ~/.claude/.env first (BAINLUCK_API, ADMIN_TOKEN)")

    variants = {
        "V0_baseline": sql,
        f"V1_tail_{args.source}": tail_filtered(sql, args.source),
        f"V2_root_{args.source}": root_filtered(sql, args.source),
    }
    if args.all_sources:
        for src in SOURCES:
            variants[f"V2_root_{src}"] = root_filtered(sql, src)

    artifact: dict = {
        "issue": 2076,
        "window": "CAL-P086B",
        "question": "does a source predicate reduce the fold's planned cost, and where must it go",
        "caveat": "planner cost, not runtime; CAL-P085 measured >=2.35x understatement on this fold",
        "cte_reference_counts": cte_reference_counts(sql),
        "sql_chars": len(sql),
        "variants": {},
    }

    for name, variant_sql in variants.items():
        res = explain(variant_sql, api=api, token=token)
        summary = summarize(res)
        summary["sql_fingerprint"] = res.get("sql_fingerprint")
        artifact["variants"][name] = summary
        print(f"--- {name}: total_cost={summary.get('total_cost')} "
              f"rows={summary.get('plan_rows')} nodes={summary.get('node_count')} "
              f"explain_ms={summary.get('duration_ms')}")

    base = artifact["variants"]["V0_baseline"].get("total_cost")
    verdict: dict = {"baseline_total_cost": base}
    for name, summary in artifact["variants"].items():
        if name == "V0_baseline" or not base or not summary.get("total_cost"):
            continue
        ratio = summary["total_cost"] / base
        verdict[name] = {
            "ratio_vs_baseline": round(ratio, 4),
            "seven_chunk_cost_multiple": round(ratio * len(SOURCES), 3),
        }
    if args.all_sources and base:
        chunk_costs = {
            src: artifact["variants"][f"V2_root_{src}"].get("total_cost") for src in SOURCES
        }
        measured = {k: v for k, v in chunk_costs.items() if v}
        verdict["root_chunks"] = {
            "per_source_cost": measured,
            "unmeasured": [k for k, v in chunk_costs.items() if not v],
            "sum_cost": round(sum(measured.values()), 1),
            "sum_ratio_vs_baseline": round(sum(measured.values()) / base, 4),
            "max_chunk": max(measured, key=measured.get) if measured else None,
            "max_chunk_ratio_vs_baseline": (
                round(max(measured.values()) / base, 4) if measured else None
            ),
        }
    artifact["verdict"] = verdict
    print(json.dumps(verdict, indent=2))

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(artifact, fh, indent=2)
        print(f"artifact -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
