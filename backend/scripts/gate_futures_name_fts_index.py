#!/usr/bin/env python3
"""Red-first gate for the `futures_markets.name` FTS index lever (LAT-P096, #1866).

WHAT THIS GATES
---------------
`docs/audits/latency/lat-p096-futures-name-fts-index-spec.md` asks Alex to run
one `CREATE INDEX CONCURRENTLY` by hand, attended, outside Alembic (ruling 131 —
index DDL with no code half does not belong in the release phase; gotcha #31).

The application half of LAT-P096 is already shipped and is NOT what this grades:
`_build_futures_name_filter` gives the arm one definition, and
`tests/test_futures_name_filter_arms.py` pins that both of its halves survive.
Neither changes a single plan. The measured win is entirely in the DDL, so the
only buildable half of "build it now with a red-first gate" is the gate.

    source ~/.claude/.env
    python3 backend/scripts/gate_futures_name_fts_index.py --label before
    # ... Alex runs the attended psql block ...
    python3 backend/scripts/gate_futures_name_fts_index.py --label after

Exit 0 = GREEN (all criteria pass). Exit 1 = RED. **Any other exit is the
harness failing to run, not a verdict** (gotcha #54 as amended) — never read a
non-1 non-zero as "the index is bad".

WHAT IS BROKEN, MEASURED ON PRODUCTION 2026-08-26
-------------------------------------------------
`/api/events/typeahead` spends 89-91% of a cold request inside `futures_query`
(`?debug_timing=1`: 3,628/3,991, 3,510/3,913, 3,665/4,113 ms). The dominant
clause is the futures NAME arm, `FTS(name) OR name ILIKE '%q%'`, and there is no
FTS expression index on `futures_markets.name`. For `werder`:

    ILIKE alone     27.8 ms   Bitmap Index Scan (ix_futures_name_trgm),    904 buffers
    FTS alone      742.7 ms   Index Scan, 49,551 rows removed by filter, 27,483 buffers
    the OR         870.4 ms   Index Scan, 49,557 rows removed,           27,483 buffers

Two defects, one cause. The FTS half is unindexed, so it scans every open market
computing one tsvector per row; and because it is OR'd inline, it also DEFEATS
`ix_futures_name_trgm`, which already exists and serves the ILIKE half alone in
27.8 ms. An FTS expression index lets the planner `BitmapOr` the two GINs and
recovers both.

WHY THE FTS HALF IS NOT SIMPLY DELETED
--------------------------------------
Because a production recall census says it carries rows (open markets, ten
terms): champions 405 -> 598 (+193), relegation 53 -> 116 (+63), chiefs 25 -> 30,
election 2,365 -> 2,370; and werder, schalke, winner, trump, fed, mvp all +0.
Six of ten gain nothing, which is exactly why deleting it survives a spot check
and loses 193 open markets on a head query. Full reasoning:
`tests/test_futures_name_filter_arms.py`.

WHY THE BUDGET IS A RATIO AND NOT MILLISECONDS
-----------------------------------------------
The same reason `gate_teams_fts_index.py` was rewritten: this predicate's cost is
per-row `to_tsvector` CPU, and the database host's contention swings it several
fold within minutes. Measured here while setting the threshold, three interleaved
rounds over three terms:

    arm_ms:   4552.7 3627.7 4736.9 1871.3 790.9 772.9 997.8 4737.4 4843.9   (6.3x spread)
    ratio:       2.66   3.27   2.81   4.88  3.26  3.59  4.05   3.13   3.30   (1.8x spread)

A threshold in absolute milliseconds against a quantity that moves 6.3x on its
own is a coin flip. The ratio held through the whole excursion.

THE CONTROL
-----------
    control = to_tsvector('english', coalesce(external_id,'')) @@ websearch_to_tsquery(...)

Same table, same shape of work (one tsvector per open market), on a column the
DDL does not index — so it absorbs the same CPU contention and does NOT move
when the index lands. A `count(*)` control was rejected for the teams gate and is
rejected here for the same reason: it is dominated by fixed overhead, so it
cancels none of the noise it is supposed to cancel.

THE PRIMARY CRITERION IS THE PLAN SHAPE
---------------------------------------
A ratio is a budget; it is not proof the planner USES the index. Criterion 1
requires a `BitmapOr` over BOTH `ix_futures_name_fts_open` AND
`ix_futures_name_trgm`. Requiring both is deliberate and load-bearing: the whole
thesis is that the OR currently defeats the trigram index, so an "after" plan
that uses only the new FTS index has taken half the win and left the ILIKE half
still scanning. That is a RED, and it should be, because it is a different
outcome than the one the spec predicts — see the spec's "if this happens" note.

The SQL is COMPILED FROM THE LIVE ORM via `_build_futures_name_filter`, never
hand-copied. If the route's predicate changes, this gate's SQL changes with it
and the shape check fails honestly. A hand-pasted predicate would keep passing
against an index the route no longer matches — the exact failure LAT-P086 caught
in the teams DDL (`::text` vs `CAST(... AS VARCHAR)`).

SEMANTICS ARE CHECKED BY SERVER-SIDE SIGNATURE, NOT BY ROW EXTRACTION
----------------------------------------------------------------------
`winner` matches thousands of open markets and `/api/admin/db-query` silently
truncates at 1,000 rows. Pulling ids and comparing lists would compare the first
1,000 of each and report agreement it never checked. The gate compares
`count(*)` plus `md5(string_agg(id::text, ',' ORDER BY id))` computed IN the
database, which is cap-proof.

⚠️ AMENDED 2026-08-29: THE COMPARAND IS A FORCED SCAN, NOT THE FROZEN BASELINE.
Criterion 3 originally compared today's digest against one recorded by
`--write-baseline`. Run three days later it reported DRIFT on 8 of 10 terms and
every one was an artefact: the graded predicate contains **`now()`**, and the
open-market population churns continuously, so `winner` had legitimately moved
3,530 -> 4,762 rows. A frozen digest over a clock-dependent population is
gotcha #44's anchor-that-branches-on-the-clock, and it fails for every reason
except the one it is watching for.

It now compares the INDEXED answer against a FORCED-SCAN answer taken at the
SAME INSTANT (`_ground_truth_sql`). That is the actual claim an expression index
makes — change the plan, never the rows — and churn can neither forge agreement
nor fake a difference, because neither read is frozen. Strictly harder than the
old check, and it holds on any date.

WHAT THE INDEX ACTUALLY DID, MEASURED 2026-08-29 AFTER ALEX RAN THE DDL
------------------------------------------------------------------------
GREEN on shape/budget for 9 of 10 terms, and the win is large: `werder`
4,722 -> 5.7 ms, `mvp` 6,527 -> 4.1 ms, all under a BitmapOr over both GINs.
Cold typeahead p50 on the charter instrument fell 3,251 -> 674.5 ms.

RED on `winner`, and it is a REAL finding rather than noise: the planner used
NEITHER GIN, taking `ix_futures_markets_status` and scanning all 55,102 open
rows. The rule, established across twelve terms, is that the flat status scan
has a FIXED cost (37,715) which a broad BitmapOr's union exceeds — so the
planner abandons both indexes whenever EITHER half of the OR is estimated
non-selective. Row count is not the trigger: `chicago` (220 rows) falls back
while `yan` (311 rows) does not.

That residual is a CODE fix and it shipped as LAT-P140: the two halves now enter
`/typeahead`'s existing UNION as separate arms, so each is costed on its own
selectivity (`chi` 1,250 -> 22.9 ms, identical rows). This gate still grades the
OR form, which is correct — the OR remains the definition of the arm and other
callers use it. A RED on a high-frequency term here means "the OR still cannot
be trusted on the hot path", which is true and is why the UNION split exists.
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

from sqlalchemy import Text, and_, cast, func, literal_column, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import aggregate_order_by

from app.models.models import FuturesMarket
from app.routes.events import (
    _SEARCH_TS_CONFIG_SQL,
    _build_expanded_ilike,
    _build_futures_name_filter,
)

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")

#: Both must appear under a BitmapOr. See "THE PRIMARY CRITERION" above for why
#: the pre-existing trigram index is required and not merely tolerated.
EXPECTED_INDEXES = ("ix_futures_name_fts_open", "ix_futures_name_trgm")

#: Ratio of arm exec time to the CPU-matched control.
#:
#: RED, as recorded by `--write-baseline` on 2026-08-26 over all ten terms:
#: median 3.41, range **1.02 - 4.76**. Post-index the arm becomes a bitmap scan
#: over a handful of rows while the control still scans every open market, so
#: ~0.02-0.12 is expected — better than an order of magnitude of headroom.
#:
#: ⚠️ The honest margin is NOT the median. `fed` read 1.02 (arm 1,746.3 ms against
#: a control that happened to be slow at 1,710.1 ms), so the threshold sits only
#: 1.28x below the tightest observed red, not the ~3x the other nine suggest. The
#: threshold is kept at 0.80 rather than loosened, because the predicted post-DDL
#: value is ~0.05 and a bar that a no-op could clear is the one failure a gate
#: must never have (`gate_teams_fts_index.py` was rewritten for exactly that).
#: But if an "after" run lands between 0.80 and 1.02 on a single term, read it as
#: NOISE ON A THIN MARGIN and re-run with more rounds — do not report a 1.0 as a
#: near-miss win.
RATIO_THRESHOLD = 0.80

#: Pre-registered terms. Deliberately mixed, and the mix is the lesson from
#: LAT-P088: the futures TRIGRAM gate passed its shape check and failed its
#: budget purely on high-frequency words, because trigram selectivity dies on
#: common terms. So the set carries both classes explicitly, and a GREEN that
#: holds only on rare terms cannot happen quietly.
TERMS: tuple[tuple[str, str], ...] = (
    # (term, class) — `recall` = the FTS half measurably adds rows
    ("champions", "recall/common"),
    ("relegation", "recall"),
    ("chiefs", "recall"),
    ("election", "recall/common"),
    ("winner", "high-frequency"),
    ("trump", "high-frequency"),
    ("fed", "high-frequency"),
    ("werder", "rare"),
    ("schalke", "rare"),
    ("mvp", "rare"),
)

BASELINE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "audits",
    "latency",
    "lat-p096-futures-name-fts-red.json",
)


def _post(sql: str, *, analyze: bool, timeout_ms: int = 30000) -> dict:
    """One `/api/admin/db-query` round trip. Exits 2 on transport failure.

    Deliberately does NOT swallow errors into an empty return: an empty result
    and a refused query must not arrive in the same shape (gotcha #53), or a
    gate that never ran reads as a gate that found nothing.

    `timeout_ms` is rejected on the plain row path — the endpoint honours it only
    alongside `explain: true`. Sending it unconditionally 400s the read.
    """
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        sys.exit(2)
    body: dict = {"sql": sql}
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
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        print(f"ERROR: db-query HTTP {exc.code}: {detail}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: db-query transport failure: {exc}", file=sys.stderr)
        sys.exit(2)


def _exec_ms(payload: dict) -> float:
    blob = json.dumps(payload.get("plan"))
    match = re.search(r'"Execution Time":\s*([0-9.]+)', blob)
    if not match:
        print("ERROR: no Execution Time in plan — analyze did not run", file=sys.stderr)
        sys.exit(2)
    return float(match.group(1))


def _index_scans(payload: dict) -> set[str]:
    """Index names under any *Index Scan node (bitmap or plain)."""
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        if "Index Scan" in str(node.get("Node Type", "")) and node.get("Index Name"):
            found.add(node["Index Name"])
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value)

    walk(payload.get("plan"))
    return found


def _has_bitmap_or(payload: dict) -> bool:
    return '"Node Type": "BitmapOr"' in json.dumps(payload.get("plan"))


def _literal(stmt) -> str:
    """Compile to literal SQL for the raw `/api/admin/db-query` text channel.

    `paramstyle="named"` is not cosmetic. The default pyformat dialect escapes
    every literal `%` to `%%` for the DBAPI, and this SQL is sent as raw text
    that no driver will un-escape — so `ILIKE '%%werder%%'` would go to the
    server looking for two literal percent signs and match NOTHING. The gate
    would then record an empty signature as its baseline and report agreement
    forever after. Caught while recording the first red.
    """
    return str(
        stmt.compile(
            dialect=postgresql.dialect(paramstyle="named"),
            compile_kwargs={"literal_binds": True},
        )
    )


def _open_now():
    """The open-market predicate the route ANDs onto every futures arm."""
    return and_(
        FuturesMarket.status == "open",
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= func.now(),
        ),
    )


def _arm(term: str):
    """The REAL route predicate, compiled from the ORM — never hand-copied."""
    ilike = _build_expanded_ilike(FuturesMarket.name, term, None)
    return _build_futures_name_filter(ilike, term)


def _arm_sql(term: str) -> str:
    return _literal(
        select(func.count()).select_from(FuturesMarket).where(_arm(term), _open_now())
    )


def _control_sql(term: str) -> str:
    """CPU-matched control on a column the DDL does not index."""
    predicate = func.to_tsvector(
        _SEARCH_TS_CONFIG_SQL, func.coalesce(FuturesMarket.external_id, "")
    ).op("@@")(func.websearch_to_tsquery(_SEARCH_TS_CONFIG_SQL, term))
    return _literal(
        select(func.count()).select_from(FuturesMarket).where(predicate, _open_now())
    )


def _signature_sql(term: str) -> str:
    """count + md5 of the ORDER-BY-id id set, computed server-side (cap-proof).

    `aggregate_order_by` rather than a string patch: the ORDER BY inside
    `string_agg` is what makes the digest stable, so it has to be part of the
    expression the compiler builds, not a substitution applied to its output.
    """
    # `string_agg(expr, ',' ORDER BY id)` — the ORDER BY belongs on the LAST
    # argument. Attaching it to the first compiles to
    # `string_agg(expr ORDER BY id, ',')`, which Postgres rejects as
    # `undefined_function` rather than reordering it for you.
    delimiter = aggregate_order_by(literal_column("','"), FuturesMarket.id.asc())
    return _literal(
        select(
            func.count().label("n"),
            func.md5(
                func.string_agg(cast(FuturesMarket.id, Text), delimiter)
            ).label("sig"),
        )
        .select_from(FuturesMarket)
        .where(_arm(term), _open_now())
    )


def _ground_truth_sql(term: str) -> str:
    """The SAME logical row set, by a predicate NEITHER index can serve.

    ``|| ''`` is a no-op on the value and a wrecking ball to expression matching:
    `to_tsvector(..., coalesce(name,'') || '')` no longer matches
    `ix_futures_name_fts_open`'s indexed expression, and `(name || '') ILIKE ...`
    no longer matches `ix_futures_name_trgm`. So this compiles to a forced scan
    computing the answer from the heap, which is the ground truth the indexed
    path must agree with.

    Built by string surgery on the compiled arm rather than through the ORM on
    purpose: the point is to produce SQL the planner treats as DIFFERENT while a
    reader can see it is logically THE SAME. Going through `_arm()` again would
    just rebuild the indexable form.
    """
    sql = _signature_sql(term)
    sql = sql.replace(
        "to_tsvector('english', coalesce(futures_markets.name, ''))",
        "to_tsvector('english', coalesce(futures_markets.name, '') || '')",
    )
    sql = sql.replace(
        "futures_markets.name ILIKE", "(futures_markets.name || '') ILIKE"
    )
    return sql


def _signature(term: str) -> dict:
    """Count + id digest by the INDEXED path and by a forced scan, same instant.

    ⚠️ WHY THIS NO LONGER GRADES AGAINST THE FROZEN BASELINE. It used to, and on
    2026-08-29 that produced a RED on 8 of 10 terms which was entirely an
    artefact. The graded predicate is `status = 'open' AND (resolution_date IS
    NULL OR resolution_date >= now())` — it contains **`now()`**, and the open
    market population churns continuously (ingest every 1-2 h, settlement
    continuous). Three days after `--write-baseline`, `winner` had moved
    3,530 -> 4,762 rows and `schalke` 34 -> 53. A frozen id digest over a
    clock-dependent population cannot survive its own baseline, so criterion 3
    was guaranteed to fail for any reason EXCEPT the one it was watching for.
    That is gotcha #44's shape — an anchor that branches on the clock — and a
    criterion that always fails is exactly as useless as one that always passes.

    The replacement tests the real claim, and tests it STRICTLY HARDER: an
    expression index must change PLANS and never ROWS, so the indexed answer and
    a forced-scan answer taken at the SAME INSTANT over the SAME population must
    agree exactly. Churn cannot forge agreement (both reads see it) and cannot
    fake a difference (neither is frozen). Verified in production the day the
    index landed: `werder` n=38, `champions` n=596 and `winner` n=4,762 all
    matched digest-for-digest.

    Still server-side `count(*)` + `md5(string_agg(...))`, for the original
    reason: `winner` matches thousands of rows and `/api/admin/db-query`
    truncates at 1,000, so pulling ids would compare the first 1,000 of each and
    report an agreement it never checked.
    """
    rows = _post(_signature_sql(term), analyze=False).get("rows") or []
    if not rows:
        print(f"ERROR: signature read returned no rows for {term!r}", file=sys.stderr)
        sys.exit(2)
    truth = _post(_ground_truth_sql(term), analyze=False).get("rows") or []
    if not truth:
        print(f"ERROR: ground-truth read returned no rows for {term!r}", file=sys.stderr)
        sys.exit(2)
    return {
        "n": rows[0][0],
        "sig": rows[0][1],
        "ground_truth_n": truth[0][0],
        "ground_truth_sig": truth[0][1],
        "agrees_with_forced_scan": (rows[0][0] == truth[0][0] and rows[0][1] == truth[0][1]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="unlabelled", help="before | after | free text")
    parser.add_argument("--rounds", type=int, default=3, help="interleaved rounds per term")
    parser.add_argument("--out", help="write the full result JSON here")
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="record today's signatures as the RED baseline (run once, before the DDL)",
    )
    parser.add_argument(
        "--skip-semantics", action="store_true", help="timing/shape only"
    )
    args = parser.parse_args()

    # The baseline is no longer REQUIRED — criterion 3 grades against a
    # same-instant forced scan (see `_signature`). It is still read when present,
    # because the row-count delta against it is the cheapest available read on
    # how much the open-market population moved since the red was recorded, and
    # that is the context a reader needs to interpret everything else. Reported,
    # never graded: grading it is what made the 2026-08-29 run a false RED.
    baseline: dict = {}
    if not args.write_baseline and os.path.exists(BASELINE):
        with open(BASELINE) as handle:
            baseline = json.load(handle)["terms"]

    print(f"gate_futures_name_fts_index  label={args.label}  terms={len(TERMS)}  rounds={args.rounds}")
    print(f"  ratio threshold <= {RATIO_THRESHOLD}   expected indexes: {', '.join(EXPECTED_INDEXES)}")
    print()

    results: dict[str, dict] = {}
    shape_fail: list[str] = []
    budget_fail: list[str] = []
    semantics_fail: list[str] = []

    for term, klass in TERMS:
        arm_sql, ctrl_sql = _arm_sql(term), _control_sql(term)
        arm_ms: list[float] = []
        ctrl_ms: list[float] = []
        indexes: set[str] = set()
        bitmap_or = False

        # Interleave arm and control so a load excursion lands on BOTH — that is
        # the entire purpose of the control.
        for _ in range(args.rounds):
            plan = _post(arm_sql, analyze=True)
            arm_ms.append(_exec_ms(plan))
            indexes |= _index_scans(plan)
            bitmap_or = bitmap_or or _has_bitmap_or(plan)
            ctrl_ms.append(_exec_ms(_post(ctrl_sql, analyze=True)))
            time.sleep(0.5)

        arm_med = sorted(arm_ms)[len(arm_ms) // 2]
        ctrl_med = sorted(ctrl_ms)[len(ctrl_ms) // 2]
        ratio = arm_med / ctrl_med if ctrl_med else float("inf")

        missing = [name for name in EXPECTED_INDEXES if name not in indexes]
        shape_ok = bitmap_or and not missing
        budget_ok = ratio <= RATIO_THRESHOLD

        semantics_ok = True
        signature: dict = {}
        if not args.skip_semantics:
            signature = _signature(term)
            if not args.write_baseline:
                # Same instant, same population, indexed vs forced scan. See
                # `_signature` for why the frozen baseline is no longer the
                # comparand (it graded a clock-dependent population).
                semantics_ok = signature["agrees_with_forced_scan"]

        if not shape_ok:
            shape_fail.append(term)
        if not budget_ok:
            budget_fail.append(term)
        if not semantics_ok:
            semantics_fail.append(term)

        results[term] = {
            "class": klass,
            "arm_ms": arm_ms,
            "ctrl_ms": ctrl_ms,
            "arm_median_ms": round(arm_med, 1),
            "ctrl_median_ms": round(ctrl_med, 1),
            "ratio": round(ratio, 3),
            "bitmap_or": bitmap_or,
            "indexes_used": sorted(indexes),
            "indexes_missing": missing,
            "shape_ok": shape_ok,
            "budget_ok": budget_ok,
            "semantics_ok": semantics_ok,
            "signature": signature,
        }

        flag = "PASS" if (shape_ok and budget_ok and semantics_ok) else "FAIL"
        shape_note = "ok" if shape_ok else ("MISSING:" + ",".join(missing) if missing else "no BitmapOr")
        # Population drift is REPORTED, never graded — it is context for reading
        # the row, not a verdict about the index.
        drift = ""
        if signature and term in baseline:
            delta = signature["n"] - baseline[term]["signature"]["n"]
            drift = f" pop{delta:+d}" if delta else " pop=0"
        print(
            f"  {term:<12} {klass:<16} arm={arm_med:8.1f}ms ctrl={ctrl_med:8.1f}ms "
            f"ratio={ratio:6.2f}  shape={shape_note:<34} "
            f"sem={'ok' if semantics_ok else 'ROWS CHANGED'}{drift}  {flag}"
        )

    if args.write_baseline:
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w") as handle:
            json.dump({"label": args.label, "terms": results}, handle, indent=1)
        print()
        print(f"wrote RED baseline {BASELINE}")
        print("VERDICT: BASELINE RECORDED (not a pass/fail run)")
        return 0

    green = not (shape_fail or budget_fail or semantics_fail)
    print()
    print(f"  criterion 1 SHAPE     : {'PASS' if not shape_fail else 'FAIL on ' + ', '.join(shape_fail)}")
    print(f"  criterion 2 BUDGET    : {'PASS' if not budget_fail else 'FAIL on ' + ', '.join(budget_fail)}")
    print(f"  criterion 3 SEMANTICS : {'PASS' if not semantics_fail else 'FAIL on ' + ', '.join(semantics_fail)}")
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
