#!/usr/bin/env python3
"""Red-first gate for the `events` FTS index lever (LAT-P275 step 1, #4140).

WHAT THIS GATES
---------------
`docs/audits/latency/lat-p275-events-fts-index-spec.md` asks Alex to run two
`CREATE INDEX CONCURRENTLY` statements by hand, attended, outside Alembic
(ruling 131 — index DDL with no code half does not belong in the release phase;
gotcha #31). The application is UNMODIFIED: there is nothing to build in code,
so the only buildable half of "build it now with a red-first gate" is the gate.

This script is that gate. It is RED today (no FTS index exists on `events` —
verified against `pg_indexes` on production 2026-09-08, 21 indexes, zero
containing `to_tsvector`) and must turn GREEN on the same command, unedited,
after the DDL runs:

    source ~/.claude/.env
    python3 backend/scripts/gate_events_fts_index.py --label before
    # ... Alex runs the attended psql block ...
    python3 backend/scripts/gate_events_fts_index.py --label after

Exit 0 = GREEN (all criteria pass). Exit 1 = RED. Any other exit is the harness
failing to run, not a verdict (gotcha #54's amendment) — never read a non-1
non-zero as "the index is bad".

WHAT IS ACTUALLY SLOW, AND WHY AN INDEX IS THE FIX
--------------------------------------------------
`typeahead_search` builds its event predicate as

    event_team_filter = or_(fts_event_f, ilike_event_filter)      # routes/events.py

where `fts_event_f` is `_fts_filter(home_team_name) OR _fts_filter(away_team_name)`.
The ILIKE half is servable by the trigram GINs; the FTS half is servable by
nothing, so the planner abandons the GINs for the whole OR and sequentially
scans `events`. Measured for #4140 on `yank`: **127-263 ms with 234,575 rows
removed by the filter**, where the arm could answer in ~2 ms.

Note what the index does NOT do: it does not change recall. On a mid-word
prefix like `yank`, `websearch_to_tsquery('english','yank')` does not match the
lexeme `yanke`, so the FTS half returns **zero rows** — it is pure cost today.
The index turns "seq scan everything to find nothing" into "index scan, find
nothing". Criterion 3 pins that: the id set must not move.

That is measured, not argued. The RED capture on 2026-09-08 read:

    yank 0 rows   celt 0 rows   dodg 0 rows        <- mid-word: pure cost
    yankees 301   celtics 185   red sox 326        <- whole word: real recall

which is also why deleting the FTS half is NOT the cheap fix it looks like: the
same six terms show the half earning 301/185/326 rows on whole words that the
substring half does not reach by stemming. Both halves are load-bearing
(LAT-P096 measured the same for the futures twin). The gate holds both kinds of
term for exactly this reason.

The absolute milliseconds below are NOT #4140's 127-263 ms and are not meant to
be: this gate times `count(*)` over the whole predicate under EXPLAIN ANALYZE on
a ~437%-bloated table, where #4140 timed the arm inside the real LIMITed query.
Two honest numbers about two different quantities — which is the other reason
the verdict rides on the ratio and the plan shape, not on a millisecond budget.

🔴 THE TRAP THIS GATE EXISTS TO NOT FALL INTO
----------------------------------------------
`to_tsvector(x)` and `to_tsvector('english', x)` ARE DIFFERENT FUNCTIONS, and
only the two-arg form can use a two-arg expression index. LAT-P274 burned a
cycle and handed another lane a **270x-wrong** number because a hand-written
probe dropped the config argument and therefore read as "the index does
nothing". The teams gate disagreed with that probe and was right, *because* it
compiled from the ORM.

So this gate NEVER hand-writes the predicate. It calls the route's own
`_fts_filter`, which sources its config from the route's own
`_SEARCH_TS_CONFIG_SQL`. If the route's config or its `coalesce` changes, this
gate's SQL changes with it and the shape check fails honestly. The index
expression must match `to_tsvector('english', coalesce(col, ''))` EXACTLY,
coalesce included — an index on the bare column builds fine and is silently
never used.

`_fts_filter` is the real helper, but `fts_event_f` itself is assembled inline
in `typeahead_search` rather than behind a builder, so the two disjuncts are
re-assembled here. That is deliberate and it is the ONE hand-written thing in
this file: it reproduces the no-sport-alias case, which is the ordinary mid-word
keystroke this ship is about. If the arm ever gains a module-level builder,
re-point `_fts_sql` at it and delete `_event_fts_predicate`.

WHY THE BUDGET IS A RATIO AND NOT MILLISECONDS
-----------------------------------------------
Copied wholesale from `gate_teams_fts_index.py`, whose docstring carries the
measurement: an absolute-ms threshold **already passed on a no-op**, because the
host's CPU contention swings a seq scan ~6x within a single minute. A threshold
in absolute milliseconds against a number that moves 5.9x on its own is a coin
flip. The budget here is a ratio against a control measured IN THE SAME BATCH,
interleaved, on the same table:

    control = to_tsvector('english', coalesce(home_team_normalized,'')) @@ ...

`home_team_normalized` is deliberately NOT one of the two indexed columns, so
the DDL cannot serve the control, and it is the same shape of work (one tsvector
per row over all of `events`), so it absorbs the same contention. A plain
`count(*)` control does NOT work and was rejected upstream: it is dominated by
fixed overhead, and a control only cancels the noise it shares.

AND THE PRIMARY CRITERION IS STILL THE PLAN SHAPE
--------------------------------------------------
A ratio is a budget; it is not proof the planner USES the index. Criterion 1 is
the one that cannot be faked by timing: a `BitmapOr` over **both**
`ix_events_fts_home` and `ix_events_fts_away`. One of two is a FAIL, because a
structurally-mismatched expression index builds valid and is silently never
used — exactly what LAT-P086 caught in LAT-P085's proposed altnames DDL.
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

from sqlalchemy import func, or_, select
from sqlalchemy.dialects import postgresql

from app.models.models import Event
from app.routes.events import _fts_filter, _SEARCH_TS_CONFIG_SQL

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")

#: The two indexes the attended DDL creates. BOTH must appear in the plan.
EXPECTED_INDEXES = (
    "ix_events_fts_home",
    "ix_events_fts_away",
)

#: Ratio of FTS exec time to the CPU-matched control. MEASURED RED 2026-09-08,
#: 3 interleaved rounds x 6 terms: **8.67 - 12.60**, median 11.0. Both sides are
#: full scans of `events`, but the FTS arm builds TWO tsvectors per row (home OR
#: away) against the control's one, and `home_team_normalized` is the shorter
#: text, so the ratio sits near 11 rather than near 2 — the control cancels host
#: CPU noise, it was never meant to equal the arm.
#:
#: Post-index the FTS arm becomes a bitmap index scan over a handful of rows
#: while the control still scans all ~234k, so the ratio should collapse by two
#: orders of magnitude (~0.01). The 0.25 threshold therefore has ~44x of
#: headroom below today's red and ~25x above the expected green: no plausible
#: load excursion crosses it in either direction.
RATIO_THRESHOLD = 0.25

BASELINE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "audits",
    "latency",
    "lat-p275-events-red.json",
)

#: Mid-word prefixes are the keystrokes that stall (#4140's `yank`); whole words
#: are where the FTS half actually earns its recall ("Yankee ..." for `yankees`,
#: which substring does not match). The gate must hold BOTH, because the cheap
#: way to make this arm fast is to delete the FTS half, and that is forbidden.
DEFAULT_TERMS = (
    "yank",
    "yankees",
    "celt",
    "celtics",
    "red sox",
    "dodg",
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
    # read, which is how the first run of the teams gate exited 2.
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


def _seq_scans(plan_payload: dict) -> int:
    return json.dumps(plan_payload.get("plan")).count('"Node Type": "Seq Scan"')


def _literal(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _event_fts_predicate(term: str):
    """`fts_event_f` for the no-sport-alias case, from the route's own helper.

    The disjunction is re-assembled (see the module docstring); the PREDICATE is
    not — `_fts_filter` supplies both the `'english'` config and the `coalesce`,
    which are the two things a hand-written probe gets wrong.
    """
    return or_(
        _fts_filter(Event.home_team_name, term),
        _fts_filter(Event.away_team_name, term),
    )


def _fts_sql(term: str) -> str:
    return _literal(select(func.count()).select_from(Event).where(_event_fts_predicate(term)))


def _ids_sql(term: str) -> str:
    return _literal(select(Event.id).where(_event_fts_predicate(term)).order_by(Event.id))


def _control_sql(term: str) -> str:
    """CPU-matched control on a column the DDL does not index.

    Same work shape (one tsvector per row over all of `events`), so it absorbs
    the same host CPU contention; unservable by `ix_events_fts_*`, so it does
    not move when the DDL lands.
    """
    predicate = func.to_tsvector(
        _SEARCH_TS_CONFIG_SQL, func.coalesce(Event.home_team_normalized, "")
    ).op("@@")(func.websearch_to_tsquery(_SEARCH_TS_CONFIG_SQL, term))
    return _literal(select(func.count()).select_from(Event).where(predicate))


def _capture(terms: list[str]) -> int:
    """Write the RED baseline: the id set each term returns TODAY, pre-index.

    Criterion 3 compares against this, so it is what proves the index changed
    only the cost and not the answer.
    """
    baseline: dict[str, dict] = {}
    for term in terms:
        rows = _post(_ids_sql(term), analyze=False).get("rows") or []
        ids = sorted(int(row[0]) for row in rows)
        baseline[term] = {"ids": ids, "n": len(ids)}
        print(f"  {term:<12} n={len(ids)}")
    with open(BASELINE, "w") as handle:
        json.dump(baseline, handle, indent=1)
    print(f"wrote {BASELINE}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="unlabelled", help="before | after | free text")
    parser.add_argument("--rounds", type=int, default=3, help="interleaved rounds per term")
    parser.add_argument("--out", help="write the full result JSON here")
    parser.add_argument(
        "--capture",
        action="store_true",
        help="(re)write the RED id-set baseline instead of grading",
    )
    parser.add_argument(
        "--skip-semantics",
        action="store_true",
        help="skip the id-set comparison (timing/shape only)",
    )
    args = parser.parse_args()

    if args.capture:
        print("capturing RED baseline for gate_events_fts_index")
        return _capture(list(DEFAULT_TERMS))

    with open(BASELINE) as handle:
        baseline = json.load(handle)
    terms = list(baseline)

    print(f"gate_events_fts_index  label={args.label}  terms={len(terms)}  rounds={args.rounds}")
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
        seq_scans = 0

        # Interleave FTS and control so a load excursion lands on BOTH, which is
        # the whole point of the control. Measuring all FTS then all control
        # would let a spike hit one and not the other.
        for _ in range(args.rounds):
            fts_plan = _post(fts_sql, analyze=True)
            fts_ms.append(_exec_ms(fts_plan))
            indexes |= _index_scans(fts_plan)
            bitmap_or = bitmap_or or _has_bitmap_or(fts_plan)
            seq_scans = max(seq_scans, _seq_scans(fts_plan))
            ctrl_ms.append(_exec_ms(_post(ctrl_sql, analyze=True)))
            time.sleep(0.5)

        fts_med = sorted(fts_ms)[len(fts_ms) // 2]
        ctrl_med = sorted(ctrl_ms)[len(ctrl_ms) // 2]
        ratio = fts_med / ctrl_med if ctrl_med else float("inf")

        missing = [name for name in EXPECTED_INDEXES if name not in indexes]
        shape_ok = bitmap_or and not missing and seq_scans == 0
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
            "seq_scans": seq_scans,
            "indexes_used": sorted(indexes),
            "indexes_missing": missing,
            "shape_ok": shape_ok,
            "budget_ok": budget_ok,
            "semantics_ok": semantics_ok,
            "n_ids": len(got_ids),
        }

        flag = "PASS" if (shape_ok and budget_ok and semantics_ok) else "FAIL"
        shape_note = "ok" if shape_ok else (
            ("MISSING:" + ",".join(missing)) if missing
            else ("seq_scan" if seq_scans else "no BitmapOr")
        )
        print(
            f"  {term:<12} fts={fts_med:8.1f}ms ctrl={ctrl_med:8.1f}ms "
            f"ratio={ratio:5.2f}  shape={shape_note}  "
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
