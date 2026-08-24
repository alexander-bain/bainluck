#!/usr/bin/env python3
"""Reduce an `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` plan to SELF-time per node.

WHY THIS EXISTS.

`Actual Total Time` on a plan node is INCLUSIVE of its children, so reading a
plan top-down and quoting the biggest number attributes the whole query to its
root every single time. Three latency cycles have quoted a node's inclusive
time as if it were that node's cost. The arithmetic that makes a plan
decomposable is:

    self_ms = actual_total_time * actual_loops - sum(child inclusive ms)

and that subtraction is the entire content of this file. It is written down as
a script rather than done by eye because "where do the milliseconds go" is the
question LAT-P085 was asked, and an answer derived by eye is not re-runnable.

Loops matter: a node inside a nested loop reports PER-LOOP time. A node at
0.9 ms x 900 loops is 810 ms and looks like nothing in the raw JSON.

Reads the db-query rail's response envelope (`{"plan": [...]}`) or a bare
`EXPLAIN` array, from a file or stdin.

USAGE
    python3 scripts/summarize_pg_plan.py /tmp/plan.json
    python3 scripts/summarize_pg_plan.py /tmp/plan.json --top 15
"""

from __future__ import annotations

import argparse
import json
import sys


def _label(node: dict) -> str:
    bits = [node.get("Node Type", "?")]
    if node.get("Relation Name"):
        bits.append(node["Relation Name"])
    if node.get("Index Name"):
        bits.append(f"[{node['Index Name']}]")
    if node.get("Alias") and node.get("Alias") != node.get("Relation Name"):
        bits.append(f"as {node['Alias']}")
    if node.get("Subplan Name"):
        bits.append(f"({node['Subplan Name']})")
    return " ".join(bits)


def walk(node: dict, depth: int, out: list) -> float:
    """Append (depth, label, self_ms, incl_ms, rows, loops, node) and return inclusive ms."""
    loops = node.get("Actual Loops", 1) or 1
    incl = (node.get("Actual Total Time") or 0.0) * loops
    children = list(node.get("Plans") or [])
    child_incl = 0.0
    child_records: list = []
    for child in children:
        child_incl += walk(child, depth + 1, child_records)
    self_ms = incl - child_incl
    out.append({
        "depth": depth,
        "label": _label(node),
        "self_ms": self_ms,
        "incl_ms": incl,
        "rows": (node.get("Actual Rows") or 0) * loops,
        "loops": loops,
        "blocks": (node.get("Shared Hit Blocks") or 0) + (node.get("Shared Read Blocks") or 0),
        "filter": node.get("Filter") or node.get("Index Cond") or node.get("Recheck Cond") or "",
        "removed": node.get("Rows Removed by Filter"),
    })
    out.extend(child_records)
    return incl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="-")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    raw = sys.stdin.read() if args.path == "-" else open(args.path).read()
    doc = json.loads(raw)
    envelope = doc if isinstance(doc, dict) else {}
    plan_arr = envelope.get("plan", doc)
    if isinstance(plan_arr, list):
        root = plan_arr[0]["Plan"]
        exec_ms = plan_arr[0].get("Execution Time")
        plan_ms = plan_arr[0].get("Planning Time")
    else:
        root = plan_arr["Plan"]
        exec_ms = plan_arr.get("Execution Time")
        plan_ms = plan_arr.get("Planning Time")

    records: list = []
    total_incl = walk(root, 0, records)

    print(f"fingerprint={envelope.get('sql_fingerprint')}  "
          f"rail_duration_ms={envelope.get('duration_ms')}")
    print(f"planning_ms={plan_ms}  execution_ms={exec_ms}  root_inclusive_ms={total_incl:.1f}")
    print(f"\nTREE (self ms = own work, children subtracted)")
    for r in records:
        pad = "  " * r["depth"]
        rem = f" -{r['removed']} filtered" if r["removed"] else ""
        print(f"  {r['self_ms']:8.1f} self {r['incl_ms']:9.1f} incl "
              f"{r['rows']:>8} rows x{r['loops']:<5} {r['blocks']:>7} blk  "
              f"{pad}{r['label']}{rem}")

    print(f"\nTOP {args.top} BY SELF TIME  (share of execution)")
    denom = exec_ms or total_incl or 1.0
    for r in sorted(records, key=lambda x: -x["self_ms"])[:args.top]:
        print(f"  {r['self_ms']:8.1f} ms  {100.0*r['self_ms']/denom:5.1f}%  "
              f"{r['blocks']:>7} blk  x{r['loops']:<5} {r['label']}")
        if r["filter"]:
            print(f"             cond: {r['filter'][:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
