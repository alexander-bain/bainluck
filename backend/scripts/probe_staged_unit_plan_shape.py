#!/usr/bin/env python3
"""EXPLAIN (plan only) the REAL staged-futures unit statement against production.

CAL-P1340, for #6868. Read-only and **it does not execute**: the body is
``{"explain": true}`` with no ``analyze``, so PostgreSQL plans the statement and
returns the tree. Nothing is written, nothing is scanned.

WHY A SECOND PLAN PROBE
-----------------------
``probe_chunk_unit_plan.py`` (CAL-P039) probes hand-written *sub-statements* of
the unit with ``EXPLAIN ANALYZE``, which EXECUTES. It answers "what does this
shape cost"; it cannot answer "what shape did production actually get", because
the statement it runs is not the one the beat runs.

#6868's decisive read is the other question — the SHAPE of the real
``_main_futures_sql(frozen=True)``:

    is ``identity_disputed_markets`` still emitted as its own CTE node with
    ``market_info`` as an InitPlan beneath it, or has it returned to an
    inner-side ``CTE Scan`` under ``ranked_outcomes``?

``app/utils/market_identity.py::identity_quarantine_ctes`` documents the first
instance (2026-09-15) and says in as many words that the guard must read the
BUILT PLAN rather than the ``AS MATERIALIZED`` keyword, because a second
consumer of an upstream link can re-inline a different part of the chain. This
script is that read.

TWO THINGS THAT MAKE THE NAIVE VERSION FAIL
-------------------------------------------
1. **The statement carries 41 semicolons, all inside ``--`` comments.** The
   admin db-query guard splits statements without understanding SQL comments, so
   the unedited text comes back "Multi-statement queries not allowed" — which
   reads as a broken query rather than as punctuation. ``strip_sql_comments``
   removes line comments (quote-aware) before sending. Comments do not affect
   planning, so the plan is the production plan.

2. **The roster must be a literal array or the estimates are fiction.** The real
   statement binds three arrays into ``unnest``. PostgreSQL's unnest support
   function reads the length off a *Const* array; hand it a subquery and the
   planner falls back to its 100-row default and can choose a different shape
   than production ever sees. So the ids are interpolated as
   ``ARRAY[...]::bigint[]`` at the real unit size. The vm_id / is_grouped values
   are synthesised — the planner sees only the array LENGTH, never the contents
   — and the script says so rather than pretending they came from a generation.

USAGE
-----
    source ~/.claude/.env
    python3 backend/scripts/probe_staged_unit_plan_shape.py
    python3 backend/scripts/probe_staged_unit_plan_shape.py --markets 8755
    python3 backend/scripts/probe_staged_unit_plan_shape.py --json > /tmp/plan.json

Needs ``BAINLUCK_API`` and ``ADMIN_TOKEN``. Never writes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

import os as _bl_os
import sys as _bl_sys

_bl_sys.path.insert(0, _bl_os.path.dirname(_bl_os.path.dirname(_bl_os.path.abspath(__file__))))

from app.tasks.precompute_calibration import (  # noqa: E402
    VM_ROSTER_IS_GROUPED_PARAM,
    VM_ROSTER_MARKET_IDS_PARAM,
    VM_ROSTER_VM_IDS_PARAM,
    _main_futures_sql,
)
from app.utils.agent_origin import tagged  # noqa: E402
from app.utils.market_identity import (  # noqa: E402
    IDENTITY_DISPUTED_CTE,
    IDENTITY_PARSED_CTE,
    IDENTITY_TOKEN_CTE,
)

#: CAL-P038 measured 5,302 markets/unit on a 128-way partition. The population
#: has grown since and the partition is now being refined (#8073), so this is a
#: default to override, not a fact. The script prints it beside the plan.
DEFAULT_MARKETS_PER_UNIT = 5302

STATEMENT_TIMEOUT_MS = 25_000


class ProbeError(RuntimeError):
    pass


def strip_sql_comments(sql: str) -> str:
    """Drop ``--`` line comments, leaving string literals alone.

    Quote-aware because the chain embeds regexes and month names in single
    quotes; a blind ``re.sub(r'--.*$')`` would cut a literal in half and turn a
    planning question into a syntax error.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    in_single = in_double = False
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if in_single:
            out.append(ch)
            if ch == "'":
                if nxt == "'":
                    out.append(nxt)
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        if in_double:
            out.append(ch)
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "'":
            in_single = True
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            out.append(ch)
            i += 1
            continue
        if ch == "-" and nxt == "-":
            while i < n and sql[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    # Collapse the blank lines the comment strip leaves behind so the artifact
    # is readable when somebody prints the statement to check it.
    return re.sub(r"\n[ \t]*\n+", "\n", "".join(out))


def _post(api: str, token: str, body: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        f"{api.rstrip('/')}/api/admin/db-query",
        data=json.dumps(body).encode(),
        headers=tagged(
            f"{api.rstrip('/')}/api/admin/db-query",
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        ),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise ProbeError(f"HTTP {exc.code}: {exc.read().decode()[:600]}") from None


def _rows(api: str, token: str, sql: str, limit: int = 1) -> list:
    out = _post(api, token, {"sql": sql, "limit": limit})
    if "rows" not in out:
        raise ProbeError(json.dumps(out)[:400])
    return out["rows"]


def _roster(api: str, token: str, n_markets: int) -> list[int]:
    # string_agg, NOT one row per id: the endpoint truncates at its row limit,
    # so a 5,302-id roster read row-wise comes back a fraction of the size it
    # claims to be and the plan is then planned for the wrong unit.
    rows = _rows(
        api,
        token,
        "SELECT string_agg(id::text, ',') AS ids FROM ("
        "SELECT id FROM futures_markets WHERE status = 'resolved' "
        f"ORDER BY id LIMIT {int(n_markets)}) t",
    )
    raw = rows[0][0]
    if not raw:
        raise ProbeError("no resolved futures_markets — cannot build a roster")
    return [int(x) for x in raw.split(",")]


def build_statement(ids: list[int]) -> str:
    """The real unit statement with its three roster params bound as literals."""
    sql = strip_sql_comments(_main_futures_sql(frozen=True))
    mids = "ARRAY[%s]" % ",".join(str(i) for i in ids)
    # Contents are irrelevant to the plan (the planner reads the array LENGTH off
    # the Const and nothing else), so these are synthesised rather than read from
    # a generation the beat has already consumed.
    vmids = "ARRAY[%s]" % ",".join("'v%d'" % i for i in range(len(ids)))
    grouped = "ARRAY[%s]" % ",".join("false" for _ in ids)
    for param, literal in (
        (VM_ROSTER_MARKET_IDS_PARAM, mids),
        (VM_ROSTER_VM_IDS_PARAM, vmids),
        (VM_ROSTER_IS_GROUPED_PARAM, grouped),
    ):
        needle = f":{param}"
        if needle not in sql:
            raise ProbeError(f"param {needle} not present in the rendered statement")
        sql = sql.replace(needle, literal)
    leftover = re.findall(r"(?<![:\w]):([a-zA-Z_][a-zA-Z0-9_]*)", sql)
    # `[[:space:]]` inside a POSIX regex class is not a bind parameter.
    leftover = [p for p in leftover if p not in {"space", "digit", "alpha", "alnum"}]
    if leftover:
        raise ProbeError(f"unbound params remain: {sorted(set(leftover))}")
    return sql


def _walk(node: dict, depth: int = 0, acc: list | None = None) -> list:
    acc = [] if acc is None else acc
    acc.append((depth, node))
    for child in node.get("Plans", []):
        _walk(child, depth + 1, acc)
    return acc


def _label(n: dict) -> str:
    bits = [n["Node Type"]]
    for key in ("CTE Name", "Relation Name", "Subplan Name", "Index Name"):
        if n.get(key):
            bits.append(f"{key.split()[0].lower()}={n[key]}")
    if n.get("Parent Relationship"):
        bits.append(f"rel={n['Parent Relationship']}")
    return " ".join(bits)


#: The quarantine predicate, identified by two fragments of the predicate itself
#: rather than by a node type — WHICH node carries it is the whole question.
#: Same marks the #6275 CI gate uses, deliberately.
PREDICATE_MARKS = ("America/New_York", "substring")


def shape_verdict(plan: dict) -> dict:
    """Answer #6868's question off the built plan, not off the keyword.

    🪤 AN INNER-SIDE ``CTE Scan`` IS NOT THE DEFECT, AND READING IT AS ONE IS THE
    EASY MISTAKE. The healthy plan has one: ``ranked_outcomes`` joins the
    quarantine on the inner side of a nested loop, and with the chain
    materialised that scan reads a small tuplestore of market ids. What #6275
    actually was is an inner-side ``CTE Scan`` **on ``market_info``** carrying the
    regex-and-date predicate in its ``Filter`` — every outer row re-deriving the
    regex over every market in the chunk. So the discriminator is the RELATION the
    inner scan reads and where the PREDICATE sits, never the presence of a scan.
    """
    nodes = _walk(plan["Plan"])
    disputed_cte_node = None
    consumer_scans: list[dict] = []
    rescans_market_info: list[dict] = []
    token_or_parsed_scans: list[dict] = []
    for depth, n in nodes:
        if n.get("Subplan Name", "").endswith(f"CTE {IDENTITY_DISPUTED_CTE}"):
            disputed_cte_node = {"depth": depth, "node": _label(n)}
        if n["Node Type"] == "CTE Scan" and n.get("CTE Name") == IDENTITY_DISPUTED_CTE:
            consumer_scans.append(
                {"depth": depth, "node": _label(n), "filter": n.get("Filter")}
            )
        # The defect: the predicate itself, on the inner side, over `market_info`.
        body = json.dumps({k: v for k, v in n.items() if k != "Plans"})
        if all(mark in body for mark in PREDICATE_MARKS):
            if (
                n["Node Type"] == "CTE Scan"
                and n.get("CTE Name") == "market_info"
                and n.get("Parent Relationship") == "Inner"
            ):
                rescans_market_info.append({"depth": depth, "node": _label(n)})
        if n.get("CTE Name") in {IDENTITY_TOKEN_CTE, IDENTITY_PARSED_CTE}:
            token_or_parsed_scans.append({"depth": depth, "node": _label(n)})
    healthy = disputed_cte_node is not None and not rescans_market_info
    return {
        "materialised_as_own_cte_node": disputed_cte_node is not None,
        "disputed_cte_node": disputed_cte_node,
        "consumer_cte_scans_of_the_materialised_set": consumer_scans,
        "inner_side_rescans_of_market_info": rescans_market_info,
        "token_parsed_cte_scans": token_or_parsed_scans,
        "verdict": (
            "MATERIALISED — own CTE node, and no inner-side rescan of market_info"
            if healthy
            else "INLINED OR RESCANNED — the #6275 shape is back"
        ),
    }


def costliest(plan: dict, k: int = 15) -> list[dict]:
    """The k nodes with the largest SELF cost (total minus children's totals)."""
    rows = []
    for depth, n in _walk(plan["Plan"]):
        child_total = sum(c.get("Total Cost", 0.0) for c in n.get("Plans", []))
        rows.append(
            {
                "self_cost": round(n.get("Total Cost", 0.0) - child_total, 1),
                "total_cost": round(n.get("Total Cost", 0.0), 1),
                "plan_rows": n.get("Plan Rows"),
                "depth": depth,
                "node": _label(n),
            }
        )
    rows.sort(key=lambda r: r["self_cost"], reverse=True)
    return rows[:k]


def cte_estimates(plan: dict) -> dict:
    """Each CTE's estimated row count, which is what #6868 turned out to be about.

    The shape read below answers "is #6275 back" (it is not). This answers the
    question that actually moved: does the planner believe the unit holds the
    markets it holds. Compare ``market_info`` against ``markets_in_roster`` — a
    clause the planner cannot estimate (an ``IS NULL`` on a jsonb subscript is
    charged ``DEFAULT_UNK_SEL`` = 0.005) shows up here as a 100x+ collapse and
    nowhere else, and it makes the ROOT COST go DOWN, so no cost watcher sees it.
    """
    out = {}
    for _depth, n in _walk(plan["Plan"]):
        name = n.get("Subplan Name") or ""
        if name.startswith("CTE "):
            out[name[4:]] = n.get("Plan Rows")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--markets", type=int, default=DEFAULT_MARKETS_PER_UNIT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--print-sql", metavar="PATH", help="write the sent statement here")
    args = ap.parse_args(argv)

    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        print("BAINLUCK_API / ADMIN_TOKEN not set — `source ~/.claude/.env`", file=sys.stderr)
        return 2

    taken = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ids = _roster(api, token, args.markets)
    sql = build_statement(ids)
    if args.print_sql:
        with open(args.print_sql, "w") as fh:
            fh.write(sql)

    out = _post(
        api,
        token,
        {"sql": sql, "explain": True, "timeout_ms": STATEMENT_TIMEOUT_MS},
    )
    if out.get("plan") is None:
        # 🪤 The endpoint answers 200 with `plan: null` + `truncated: true` when the
        # serialized tree passes `response_cap_bytes` (262,144). That reads exactly
        # like "the plan came back empty". It is a SIZE refusal, and the size is
        # driven by the roster literal, which PostgreSQL echoes into `Filter` /
        # `Output` on every node that references it — so the cure is a smaller
        # roster, not a longer timeout.
        raise ProbeError(
            "no plan returned: "
            + json.dumps({k: v for k, v in out.items() if k != "plan"})[:400]
            + "  → re-run with a smaller --markets"
        )
    plan = out["plan"][0]

    report = {
        "probe": "CAL-P1340 staged unit plan SHAPE (plan only, no execution)",
        "taken_utc": taken,
        "markets_in_roster": len(ids),
        "statement_chars": len(sql),
        "planning_time_ms": plan.get("Planning Time"),
        "root_total_cost": plan["Plan"].get("Total Cost"),
        "shape": shape_verdict(plan),
        "cte_plan_rows": cte_estimates(plan),
        "costliest_nodes": costliest(plan),
    }
    if args.json:
        json.dump({"report": report, "plan": plan}, sys.stdout, indent=2)
        print()
        return 0

    print(f"# {report['probe']}")
    print(f"# taken {taken} · roster {len(ids)} markets · statement {len(sql):,} chars")
    print(f"# planning {plan.get('Planning Time')} ms · root total cost {plan['Plan'].get('Total Cost')}")
    print()
    print("SHAPE (#6868's decisive read)")
    print(f"  {report['shape']['verdict']}")
    for key in (
        "disputed_cte_node",
        "inner_side_rescans_of_market_info",
        "consumer_cte_scans_of_the_materialised_set",
    ):
        print(f"  {key}: {json.dumps(report['shape'][key])}")
    print()
    print(f"CTE ROW ESTIMATES (roster is {len(ids)} markets — market_info far below that is #6868)")
    for name, est in report["cte_plan_rows"].items():
        print(f"  {est!s:>10}  {name}")
    print()
    print("COSTLIEST NODES BY SELF COST (estimates — a cost is not a runtime)")
    for r in report["costliest_nodes"]:
        print(f"  {r['self_cost']:>14,.1f}  rows={r['plan_rows']:<12} d{r['depth']:<3} {r['node']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ProbeError as exc:
        print(f"PROBE FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
