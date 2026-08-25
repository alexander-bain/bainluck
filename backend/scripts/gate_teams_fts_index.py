#!/usr/bin/env python3
"""Red-first gate for the `teams` FTS index lever (LAT-P085 item 3, corrected LAT-P087).

WHAT THIS GATES
---------------
`docs/audits/latency/lat-p086-teams-fts-index-spec.md` asks Alex to run three
`CREATE INDEX CONCURRENTLY` statements by hand, attended, outside Alembic
(ruling 131 — index DDL with no code half does not belong in the release phase;
gotcha #31). The application is UNMODIFIED: there is nothing to build in code,
so the only buildable half of "build it now with a red-first gate" is the gate.

This script is that gate. It is RED today (no index exists) and must turn GREEN
on the same command, unedited, after the DDL runs. Run it BEFORE the batch to
record the red, and AFTER to record the green:

    source ~/.claude/.env
    python3 backend/scripts/gate_teams_fts_index.py --label before
    # ... Alex runs the attended psql block ...
    python3 backend/scripts/gate_teams_fts_index.py --label after

Exit 0 = GREEN (all criteria pass). Exit 1 = RED. Any other exit is the harness
failing to run, not a verdict (gotcha #54's amendment) — never read a non-1
non-zero as "the index is bad".

WHY THE PRE-REGISTERED BUDGET CRITERION WAS REPLACED
----------------------------------------------------
LAT-P085 pre-registered three criteria, of which the second was **"exec_ms < 50
on all four RED terms"**, banked against a measured red of 386-485 ms. Measured
2026-08-24, with NO index present anywhere in production:

    yankees 46.6ms   celtics 54.3ms   red sox ~50ms   world cup ~47ms

The absolute criterion **already passes on a no-op.** Had the DDL been graded
against it, three hand-run `CREATE INDEX CONCURRENTLY` statements would have
been declared a success by a gate that a completely unindexed database also
passes. That is the worst failure mode a gate has: it does not report a wrong
number, it reports a correct number about the wrong thing.

The reason is not a code change (`git diff b5c2a750..ea07f81e` touches only
typeahead `_record_trending`, #2117) and not a data change. It is LOAD. The
predicate is a sequential scan whose cost is per-row `to_tsvector` CPU, and the
database host's CPU contention swings it by ~6x within a single minute:

    fts_ms:  61.7  60.4  57.9  63.3  340.9  323.6      (5.9x spread)

A threshold in absolute milliseconds against a number that moves 5.9x on its own
is a coin flip. Both of LAT-P085's numbers were honest readings of a quantity
that does not hold still, and 71 days of `pg_stat_statements` agrees with
neither: 3,161 calls at mean 106.2 ms (sd 84.6) and 838 at mean 230.5 (sd 166.6).

THE REPLACEMENT: A CPU-MATCHED CONTROL RATIO
--------------------------------------------
The budget is now a ratio against a control measured IN THE SAME BATCH, seconds
apart, on the same table:

    control = to_tsvector('english', coalesce(slug,'')) @@ websearch_to_tsquery(...)

`slug` is deliberately NOT one of the three indexed columns, so the DDL cannot
serve the control. It is the same shape of work — a full scan of `teams`
building one tsvector per row — so it absorbs the same CPU contention. Measured
across the 5.9x excursion above, the ratio held:

    ratio:   0.87  1.09  1.24  1.30  1.31  1.31      (1.5x spread)

A plain `count(*) WHERE id > 0` control does NOT work and was rejected: it stays
flat at ~5.5 ms through the same excursion, because it is dominated by fixed
overhead rather than per-row CPU. A control only cancels the noise it shares.

Post-index the FTS arm becomes a bitmap index scan over a handful of rows while
the control still scans all ~9,240, so the ratio should collapse by an order of
magnitude. The threshold is 0.25 — a 4x+ collapse from today's ~1.1, with room
on both sides that no plausible load excursion crosses.

THE PRIMARY CRITERION IS STILL THE PLAN SHAPE
----------------------------------------------
A ratio is a budget; it is not proof the planner USES the index. Criterion 1 is
unchanged from LAT-P085/LAT-P086 and remains the one that cannot be faked by
timing: `BitmapOr` over **three** `Bitmap Index Scan` nodes, one per
`ix_teams_fts_{name,abbrev,altnames}`. Two of three is a FAIL, because a
structurally-mismatched expression index builds valid and is silently never
used — which is exactly what LAT-P086 caught in LAT-P085's proposed altnames
DDL (`::text` vs the route's `CAST(... AS VARCHAR)`).

That is also why the SQL here is COMPILED FROM THE LIVE ORM via
`_build_team_search_filter`, never hand-copied. If the route's cast changes, this
gate's SQL changes with it and the shape check fails honestly. A hand-pasted
predicate would keep passing against an index the route no longer matches.
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from app.models.models import Team
from app.routes.events import _build_team_search_filter, _SEARCH_TS_CONFIG_SQL

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")

#: The three indexes the attended DDL creates. All three must appear in the plan.
EXPECTED_INDEXES = (
    "ix_teams_fts_name",
    "ix_teams_fts_abbrev",
    "ix_teams_fts_altnames",
)

#: Ratio of FTS exec time to the CPU-matched control. Today ~1.1 (both full
#: scans). Post-index expected ~0.05. See module docstring for why absolute
#: milliseconds were rejected.
RATIO_THRESHOLD = 0.25

BASELINE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "audits",
    "latency",
    "lat-p085-teams-red.json",
)


def _post(sql: str, *, analyze: bool, timeout_ms: int = 25000) -> dict:
    """One `/api/admin/db-query` round trip. Raises on transport failure.

    Deliberately does NOT swallow errors into a None/empty return: an empty
    result and a refused query must not arrive in the same shape (gotcha #53),
    or a gate that never ran reads as a gate that found nothing.
    """
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        sys.exit(2)
    # `timeout_ms` is rejected on the plain row path — the endpoint only honours
    # it alongside `explain: true`. Sending it unconditionally 400s the semantics
    # read, which is how the first run of this gate exited 2.
    body = {"sql": sql}
    if analyze:
        body["explain"] = True
        body["analyze"] = True
        body["timeout_ms"] = timeout_ms
    request = urllib.request.Request(
        f"{API}/api/admin/db-query",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        print(f"ERROR: db-query HTTP {exc.code}: {detail}", file=sys.stderr)
        sys.exit(2)


def _exec_ms(plan_payload: dict) -> float:
    """Pull `Execution Time` out of an EXPLAIN(FORMAT JSON, ANALYZE) payload."""
    blob = json.dumps(plan_payload.get("plan"))
    match = re.search(r'"Execution Time":\s*([0-9.]+)', blob)
    if not match:
        print("ERROR: no Execution Time in plan — analyze did not run", file=sys.stderr)
        sys.exit(2)
    return float(match.group(1))


def _index_scans(plan_payload: dict) -> set[str]:
    """Index names appearing under a `Bitmap Index Scan` node in the plan."""
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        if node.get("Node Type") == "Bitmap Index Scan" and node.get("Index Name"):
            found.add(node["Index Name"])
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value)

    walk(plan_payload.get("plan"))
    return found


def _has_bitmap_or(plan_payload: dict) -> bool:
    return '"Node Type": "BitmapOr"' in json.dumps(plan_payload.get("plan"))


def _literal(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _fts_sql(term: str) -> str:
    """The REAL route predicate, compiled from the ORM — never hand-copied."""
    return _literal(select(func.count()).select_from(Team).where(_build_team_search_filter(term)))


def _ids_sql(term: str) -> str:
    return _literal(select(Team.id).where(_build_team_search_filter(term)).order_by(Team.id))


def _control_sql(term: str) -> str:
    """CPU-matched control on a column the DDL does not index.

    Same work shape (one tsvector per row over all of `teams`), so it absorbs
    the same host CPU contention; unservable by `ix_teams_fts_*`, so it does not
    move when the DDL lands.
    """
    predicate = func.to_tsvector(
        _SEARCH_TS_CONFIG_SQL, func.coalesce(Team.slug, "")
    ).op("@@")(func.websearch_to_tsquery(_SEARCH_TS_CONFIG_SQL, term))
    return _literal(select(func.count()).select_from(Team).where(predicate))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="unlabelled", help="before | after | free text")
    parser.add_argument("--rounds", type=int, default=3, help="interleaved rounds per term")
    parser.add_argument("--out", help="write the full result JSON here")
    parser.add_argument(
        "--skip-semantics",
        action="store_true",
        help="skip the id-set comparison (timing/shape only)",
    )
    args = parser.parse_args()

    with open(BASELINE) as handle:
        baseline = json.load(handle)
    terms = list(baseline)

    print(f"gate_teams_fts_index  label={args.label}  terms={len(terms)}  rounds={args.rounds}")
    print(f"  ratio threshold <= {RATIO_THRESHOLD}   expected indexes: {', '.join(EXPECTED_INDEXES)}")
    print()

    results: dict[str, dict] = {}
    shape_fail: list[str] = []
    budget_fail: list[str] = []
    semantics_fail: list[str] = []

    for term in terms:
        fts_sql, ctrl_sql = _fts_sql(term), _control_sql(term)
        fts_ms: list[float] = []
        ctrl_ms: list[float] = []
        indexes: set[str] = set()
        bitmap_or = False

        # Interleave FTS and control so a load excursion lands on BOTH, which is
        # the whole point of the control. Measuring all FTS then all control
        # would let a spike hit one and not the other.
        for _ in range(args.rounds):
            fts_plan = _post(fts_sql, analyze=True)
            fts_ms.append(_exec_ms(fts_plan))
            indexes |= _index_scans(fts_plan)
            bitmap_or = bitmap_or or _has_bitmap_or(fts_plan)
            ctrl_ms.append(_exec_ms(_post(ctrl_sql, analyze=True)))
            time.sleep(0.5)

        fts_med = sorted(fts_ms)[len(fts_ms) // 2]
        ctrl_med = sorted(ctrl_ms)[len(ctrl_ms) // 2]
        ratio = fts_med / ctrl_med if ctrl_med else float("inf")

        missing = [name for name in EXPECTED_INDEXES if name not in indexes]
        shape_ok = bitmap_or and not missing
        budget_ok = ratio <= RATIO_THRESHOLD

        semantics_ok = True
        got_ids: list[int] = []
        if not args.skip_semantics:
            rows = _post(_ids_sql(term), analyze=False).get("rows") or []
            got_ids = sorted(int(row[0]) for row in rows)
            semantics_ok = got_ids == sorted(baseline[term]["ids"])

        if not shape_ok:
            shape_fail.append(term)
        if not budget_ok:
            budget_fail.append(term)
        if not semantics_ok:
            semantics_fail.append(term)

        results[term] = {
            "fts_ms": fts_ms,
            "ctrl_ms": ctrl_ms,
            "fts_median_ms": round(fts_med, 1),
            "ctrl_median_ms": round(ctrl_med, 1),
            "ratio": round(ratio, 3),
            "bitmap_or": bitmap_or,
            "indexes_used": sorted(indexes),
            "indexes_missing": missing,
            "shape_ok": shape_ok,
            "budget_ok": budget_ok,
            "semantics_ok": semantics_ok,
            "ids": got_ids,
        }

        flag = "PASS" if (shape_ok and budget_ok and semantics_ok) else "FAIL"
        print(
            f"  {term:<16} fts={fts_med:7.1f}ms ctrl={ctrl_med:7.1f}ms "
            f"ratio={ratio:5.2f}  shape={'ok' if shape_ok else 'MISSING:' + ','.join(missing) or 'no BitmapOr'}  "
            f"sem={'ok' if semantics_ok else 'DRIFT'}  {flag}"
        )

    green = not (shape_fail or budget_fail or semantics_fail)
    print()
    print(f"  criterion 1 SHAPE      : {'PASS' if not shape_fail else 'FAIL on ' + ', '.join(shape_fail)}")
    print(f"  criterion 2 BUDGET     : {'PASS' if not budget_fail else 'FAIL on ' + ', '.join(budget_fail)}")
    print(f"  criterion 3 SEMANTICS  : {'PASS' if not semantics_fail else 'FAIL on ' + ', '.join(semantics_fail)}")
    print()
    print(f"VERDICT: {'GREEN' if green else 'RED'}")

    if args.out:
        with open(args.out, "w") as handle:
            json.dump(
                {
                    "label": args.label,
                    "verdict": "GREEN" if green else "RED",
                    "ratio_threshold": RATIO_THRESHOLD,
                    "expected_indexes": list(EXPECTED_INDEXES),
                    "terms": results,
                },
                handle,
                indent=1,
            )
        print(f"wrote {args.out}")

    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
