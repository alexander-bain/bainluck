#!/usr/bin/env python3
"""Measure where ONE staged-futures unit spends its time, against production.

CAL-P039. Read-only. No DB credentials and no local Postgres — every statement
goes through the admin ``POST /api/admin/db-query`` endpoint, which is
SELECT-only and refuses operational functions.

WHY THIS EXISTS
---------------
CAL-P038 handed off *"each of the 128 chunks pays a full 3.3M-row seq scan of
``futures_outcomes``"* as THE convergence blocker, with two candidate fixes that
were both frozen (change unit identity, or restructure the population CTE
chain). The number was right and the conclusion was one level too coarse, and
nobody could re-check it without rebuilding the whole probe by hand. So:

  * the finding is now a script, and
  * it prints a DATE, because "the plan flips between 3,000 and 3,500
    markets/unit" is the kind of claim that rots (gotcha #35's lesson applied to
    a query plan rather than to a retention window).

WHAT IT MEASURES (three probes, each an EXPLAIN ANALYZE with act/loops shown —
a plan-cost delta is NOT a runtime delta until the nodes say they ran, which is
CAL-P035's standing rule and the reason this script never prints Total Cost as
if it were time):

  1. ``vm_stats`` as production plans it. ``virtual_market`` is referenced 7
     times in the real chunk SQL, so PG12+ auto-materializes it; a CTE Scan
     carries no index and no ordering, so the planner's choices for
     ``futures_outcomes JOIN <CTE>`` collapse to hash+seqscan vs N blind index
     lookups, and it costs the seq scan lower. Reproduced here WITHOUT the
     ``AS MATERIALIZED`` keyword — a second reference does it — because the
     endpoint's EXECUTE allowlist false-positives on ``MATERIALIZED (``
     (CAL-P036 unowned item 4, still open).

  2. The same aggregate with a redundant ``fo.market_id = ANY(:roster)``.
     Redundant BY CONSTRUCTION: under ``frozen=True`` ``market_info`` is scoped
     by exactly that array, ``virtual_market`` derives from ``market_info``, so
     ``fo.market_id = vm.market_id`` already implies membership. It changes no
     row -- it is a planner hint spelled as a predicate. The script asserts the
     two variants agree on group count and joined-row count, so a future change
     that breaks the redundancy fails here rather than silently re-shaping the
     population.

  3. The correlated ``futures_odds_snapshots`` EXISTS lookups (the liquidity /
     never-traded evidence), run twice. Pass 1 is cold, pass 2 is warm. This is
     the probe that reframes the whole diagnosis: the per-unit cost is
     dominated by BUFFER-CACHE STATE, not by the shape of any one query, and
     the seq scan in probe 1 is the largest single cache-eviction event in the
     beat -- it reads the entire table, 128 times per walk.

USAGE
-----
    source ~/.claude/.env
    python3 backend/scripts/probe_chunk_unit_plan.py            # default 5302
    python3 backend/scripts/probe_chunk_unit_plan.py --markets 3000
    python3 backend/scripts/probe_chunk_unit_plan.py --json > /tmp/probe.json

Needs ``BAINLUCK_API`` and ``ADMIN_TOKEN`` in the environment. Never writes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

#: Production's staged unit size as measured 2026-08-11 (CAL-P038 recorded
#: 5,302 markets/unit while the PLANNER's own chunker flips between 3,000 and
#: 3,500). Overridable, because the whole point is that this number moves.
DEFAULT_MARKETS_PER_UNIT = 5302

#: Mirrored from ``app.utils.resolution_authority``. Deliberately a literal:
#: this script must run without importing the frozen task module (ruling 009),
#: and CAL-P031 proved that importing to read a value is how the fingerprint
#: guard got bypassed. If these drift, probe 3's row count drifts with them and
#: the script says so rather than quietly measuring a different population.
TRUTH_ELIGIBLE_SOURCES = (
    "api_settlement", "box_score", "box_score_bound", "clob_authoritative",
    "clob_field_repair", "clob_never_graded", "clob_ordinal",
    "datagolf_matchup", "datagolf_played_lost", "datagolf_settlement",
    "date_passed", "game_score", "leaderboard", "poly_total_score",
    "scoring_plays",
)

STATEMENT_TIMEOUT_MS = 25_000


class ProbeError(RuntimeError):
    pass


def _post(api: str, token: str, body: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        f"{api.rstrip('/')}/api/admin/db-query",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        # The endpoint's refusals are BY NAME and are worth surfacing verbatim:
        # every one this probe hit was a guardrail false positive on syntax
        # (``AS t(...)`` read as a function call), not a real safety stop.
        raise ProbeError(f"HTTP {exc.code}: {detail}") from None


def _analyze(api: str, token: str, sql: str) -> dict:
    out = _post(api, token, {
        "sql": sql, "explain": True, "analyze": True,
        "timeout_ms": STATEMENT_TIMEOUT_MS,
    })
    if "plan" not in out:
        raise ProbeError(json.dumps(out)[:400])
    return out["plan"][0]


def _rows(api: str, token: str, sql: str, limit: int = 1) -> list:
    out = _post(api, token, {"sql": sql, "limit": limit})
    if "rows" not in out:
        raise ProbeError(json.dumps(out)[:400])
    return out["rows"]


def _walk(node: dict, depth: int = 0, acc: list | None = None) -> list:
    acc = [] if acc is None else acc
    acc.append((depth, node))
    for child in node.get("Plans", []):
        _walk(child, depth + 1, acc)
    return acc


def _render(plan: dict) -> str:
    lines = []
    for depth, n in _walk(plan["Plan"]):
        bits = [n["Node Type"]]
        if n.get("Relation Name"):
            bits.append(n["Relation Name"])
        if n.get("Index Name"):
            bits.append(f"idx={n['Index Name']}")
        lines.append(
            "    " + "  " * depth + " ".join(bits)
            + f"  act={n.get('Actual Rows')} loops={n.get('Actual Loops')}"
            + f" t={n.get('Actual Total Time')}ms"
        )
    return "\n".join(lines)


def _scan_of(plan: dict, relation: str) -> tuple[str, int, float] | None:
    """The (node type, actual rows, actual total time) of a scan on ``relation``."""
    for _depth, n in _walk(plan["Plan"]):
        if n.get("Relation Name") == relation and n["Node Type"].endswith("Scan"):
            return (n["Node Type"], n.get("Actual Rows"), n.get("Actual Total Time"))
    return None


def _subplan_total(plan: dict) -> float:
    """Summed self-time of correlated SubPlan scans (per-row lookups)."""
    total = 0.0
    for _depth, n in _walk(plan["Plan"]):
        if n.get("Parent Relationship") == "SubPlan":
            total += (n.get("Actual Total Time") or 0.0) * (n.get("Actual Loops") or 1)
    return total


def _roster(api: str, token: str, n_markets: int) -> list[int]:
    # string_agg, NOT one row per id: the endpoint silently truncates at 1,000
    # rows, so a 5,302-id roster read row-wise would come back a fifth of the
    # size it claimed to be and every downstream number would be wrong.
    rows = _rows(api, token, (
        "SELECT string_agg(id::text, ',') AS ids FROM ("
        f"SELECT id FROM futures_markets WHERE status = 'resolved' ORDER BY id LIMIT {int(n_markets)}"
        ") t"
    ))
    raw = rows[0][0]
    if not raw:
        raise ProbeError("no resolved futures_markets — cannot build a roster")
    return [int(x) for x in raw.split(",")]


def _arr(ids: list[int]) -> str:
    return "ARRAY[%s]::bigint[]" % ",".join(str(i) for i in ids)


def _vm_stats_sql(ids: list[int], *, pushdown: bool) -> str:
    arr = _arr(ids)
    extra = f"\n    AND fo.market_id = ANY({arr})" if pushdown else ""
    # The trailing UNION ALL is the SECOND reference to virtual_market. It is
    # what forces PG12+ to materialize the CTE, which is the only reason
    # production seq-scans here at all. Remove it and the planner inlines the
    # CTE, picks an index nested loop, and the defect disappears from the
    # measurement while remaining live in production.
    return f"""SELECT * FROM (
WITH mi AS (
  SELECT fm.id AS market_id, fm.source,
         COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
         fm.mutually_exclusive
  FROM futures_markets fm
  WHERE fm.status = 'resolved' AND fm.id = ANY({arr})
),
virtual_market AS (
  SELECT mi.market_id, mi.source, mi.category, mi.mutually_exclusive,
         'g:' || ((mi.market_id / 3))::text AS vm_id,
         true AS is_grouped
  FROM mi
),
vm_stats AS (
  SELECT vm.vm_id, vm.source, vm.category, vm.is_grouped, vm.mutually_exclusive,
         COUNT(DISTINCT vm.market_id) AS market_count,
         COUNT(*) AS total_outcomes,
         COUNT(*) FILTER (WHERE fo.is_winner = true) AS has_winner,
         COUNT(*) FILTER (WHERE fo.opening_probability IS NOT NULL
                            AND fo.opening_probability > 0
                            AND fo.opening_probability < 1) AS eligible
  FROM virtual_market vm
  JOIN futures_outcomes fo ON fo.market_id = vm.market_id{extra}
  GROUP BY vm.vm_id, vm.source, vm.category, vm.is_grouped, vm.mutually_exclusive
)
SELECT count(*)::numeric AS a, sum(total_outcomes)::numeric AS b, sum(eligible)::numeric AS c
FROM vm_stats
UNION ALL SELECT count(*)::numeric, 0::numeric, 0::numeric FROM virtual_market) q"""


def _exists_sql(ids: list[int], *, with_exists: bool) -> str:
    arr = _arr(ids)
    srcs = ", ".join(f"'{s}'" for s in TRUTH_ELIGIBLE_SOURCES)
    if with_exists:
        # count(*) FILTER, not a projected boolean: with a bare count(*) the
        # planner elides the EXISTS expressions entirely and the probe reports
        # a 40x speed-up that is really the subqueries not running.
        select = """count(*) FILTER (WHERE EXISTS (
             SELECT 1 FROM futures_odds_snapshots fos
             WHERE fos.outcome_id = fo.id
               AND (fos.yes_bid > 0 OR fos.last_price > 0))) AS liquid_n,
         count(*) FILTER (WHERE NOT EXISTS (
             SELECT 1 FROM futures_odds_snapshots fos2
             WHERE fos2.outcome_id = fo.id AND fos2.last_price > 0)) AS never_traded_n"""
    else:
        select = "count(*) AS liquid_n, count(*) AS never_traded_n"
    return f"""SELECT {select}
  FROM futures_outcomes fo
  WHERE fo.market_id = ANY({arr})
    AND fo.opening_probability IS NOT NULL
    AND fo.opening_probability > 0 AND fo.opening_probability < 1
    AND fo.resolution_source IN ({srcs})"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--markets", type=int, default=DEFAULT_MARKETS_PER_UNIT,
                    help=f"markets per unit (default {DEFAULT_MARKETS_PER_UNIT})")
    ap.add_argument("--units", type=int, default=128,
                    help="units per walk, for the extrapolation (default 128)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--verbose", action="store_true", help="print full plan trees")
    args = ap.parse_args(argv)

    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        print("BAINLUCK_API and ADMIN_TOKEN must be set (source ~/.claude/.env)",
              file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result: dict = {"measured_at": stamp, "markets_per_unit": args.markets,
                    "units_per_walk": args.units}

    ids = _roster(api, token, args.markets)
    result["roster_size"] = len(ids)
    if len(ids) < args.markets:
        print(f"NOTE: only {len(ids)} resolved markets available "
              f"(asked {args.markets}) — numbers scale with the roster.",
              file=sys.stderr)

    # -- probes 1 + 2 ------------------------------------------------------
    plan_a = _analyze(api, token, _vm_stats_sql(ids, pushdown=False))
    plan_b = _analyze(api, token, _vm_stats_sql(ids, pushdown=True))
    scan_a = _scan_of(plan_a, "futures_outcomes")
    scan_b = _scan_of(plan_b, "futures_outcomes")
    exec_a = plan_a.get("Execution Time")
    exec_b = plan_b.get("Execution Time")
    result["vm_stats"] = {
        "current": {"scan": scan_a, "execution_ms": exec_a},
        "pushdown": {"scan": scan_b, "execution_ms": exec_b},
        "speedup": round(exec_a / exec_b, 2) if exec_b else None,
    }

    # Row-identity check. Both variants must agree, or the predicate is NOT
    # redundant and the whole argument for it collapses.
    agg_a = _rows(api, token, _vm_stats_sql(ids, pushdown=False), limit=5)
    agg_b = _rows(api, token, _vm_stats_sql(ids, pushdown=True), limit=5)
    identical = agg_a == agg_b
    result["row_identity"] = {"identical": identical,
                              "current": agg_a, "pushdown": agg_b}

    # -- probe 3 -----------------------------------------------------------
    cold_warm = []
    for label in ("cold", "warm"):
        base = _analyze(api, token, _exists_sql(ids, with_exists=False))
        withx = _analyze(api, token, _exists_sql(ids, with_exists=True))
        cold_warm.append({
            "pass": label,
            "baseline_ms": base.get("Execution Time"),
            "with_exists_ms": withx.get("Execution Time"),
            "attributable_ms": round(
                (withx.get("Execution Time") or 0) - (base.get("Execution Time") or 0), 1),
            "subplan_self_ms": round(_subplan_total(withx), 1),
        })
    result["correlated_exists"] = cold_warm

    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if identical else 1

    w = args.units
    print(f"\n=== staged-futures unit cost — measured {stamp} ===")
    print(f"roster {len(ids)} markets/unit · extrapolating over {w} units/walk\n")
    print("PROBE 1/2 — vm_stats, production shape vs redundant roster predicate")
    print(f"  current : {scan_a[0]:<12} act={scan_a[1]:>9}  scan={scan_a[2]}ms  "
          f"total={exec_a}ms")
    print(f"  pushdown: {scan_b[0]:<12} act={scan_b[1]:>9}  scan={scan_b[2]}ms  "
          f"total={exec_b}ms")
    if exec_a and exec_b:
        print(f"  speed-up: {exec_a / exec_b:.1f}x   "
              f"per walk: {(exec_a - exec_b) * w / 1000:.0f} s saved")
    print(f"  row identity: {'IDENTICAL' if identical else '*** DIVERGED ***'}")
    if not identical:
        print("    the predicate is NOT redundant on this data — do not apply it")
        print(f"    current : {agg_a}\n    pushdown: {agg_b}")
    print("\nPROBE 3 — correlated futures_odds_snapshots EXISTS, cold vs warm")
    for row in cold_warm:
        print(f"  {row['pass']:<5}: baseline={row['baseline_ms']}ms  "
              f"with_exists={row['with_exists_ms']}ms  "
              f"attributable={row['attributable_ms']}ms")
    if len(cold_warm) == 2 and cold_warm[1]["attributable_ms"]:
        ratio = cold_warm[0]["attributable_ms"] / cold_warm[1]["attributable_ms"]
        print(f"  cold/warm ratio: {ratio:.0f}x — per-unit cost is dominated by")
        print("  BUFFER-CACHE STATE, and probe 1's seq scan reads the entire")
        print(f"  table {w} times per walk, which is what keeps it cold.")
    if args.verbose:
        print("\n--- plan: current ---\n" + _render(plan_a))
        print("\n--- plan: pushdown ---\n" + _render(plan_b))
    print()
    return 0 if identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
