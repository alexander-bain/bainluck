#!/usr/bin/env python3
"""Red-first gate for the `futures` search-arm index lever (LAT-P088 item 2).

READ THIS FIRST: THE LEVER IS NOT AN FTS INDEX
----------------------------------------------
LAT-P088's directive named the next lever "futures FTS", on the strength of
LAT-P087's decomposition: `futures` is 44.8% of the feed's server total and
59.3% of `/api/events/search`. The percentages are right. **The instrument named
to move them is wrong, in two independent ways, and both were measured before a
line of this file was written.**

**1. The feed half cannot be reached by any index on text.** The feed's
`futures` stage is `market_load` + `scoring_loop` (`routes/feed.py:6520`,
`:7429`). `market_load` is `SELECT FuturesMarket WHERE id IN (<ids>)` with eager
loads -- an integer primary-key lookup with **no text predicate of any kind**.
`scoring_loop` is a pure-Python per-market loop that issues no SQL at all. There
is no tsquery, no ILIKE, and no `to_tsvector` anywhere in either. 44.8% of the
feed is real, and it is 44.8% of something an FTS index cannot touch. Naming a
single lever for two costs that share only a WORD is how a queue spends a cycle
on the wrong half.

**2. The search half already has the FTS predicate, and it is already free.**
The `futures` name arm does carry
`to_tsvector('english', coalesce(name,'')) @@ websearch_to_tsquery(...)`, ANDed
with the trigram ILIKE (see `events.py:3049`, and note the comment there records
FTS being REMOVED from recall in #993 and later re-added as a precision filter).
Measured in production 2026-08-25 on `world series`, EXPLAIN ANALYZE of the arm
compiled from the live ORM:

    Bitmap Heap Scan on futures_markets   131.3 ms   rows=16
      Filter = (... to_tsvector(...) @@ 'world' AND to_tsvector(...) @@ 'seri')
      Rows Removed by Filter = 0                      <-- ZERO

The FTS predicate is evaluated on **16 rows** and removes **none of them**. An
index serving it would save the cost of two `to_tsvector` calls on sixteen rows.
That is not a lever; it is a rounding error. (The `numnode(...)=0 OR ...` wrapper
does fold away at plan time, so indexability was not the obstacle -- the
predicate simply has nothing left to do by the time it runs.)

WHAT THE MEASUREMENT ACTUALLY FOUND
-----------------------------------
The same plan, one node up:

    BitmapAnd                                         130.4 ms
      Bitmap Index Scan ix_futures_name_trgm           25.7 ms  rows=315
      Bitmap Index Scan ix_futures_markets_status     104.5 ms  rows=71,368

A low-selectivity btree bitmap on `status='open'`, built at 71,368 rows so it can
be ANDed against a trigram bitmap that already returned 315. It cannot remove a
row the trigram scan did not already have.

**That node is 80% of THIS term's name arm -- and it is NOT the general case.
Checked, rather than generalised from one plan.** Across 14 probed terms the
planner adds the status bitmap for only 4 of them:

    SUBJECT (status bitmap present)      bystander (absent)
    champion       752.3 ms              presidential election  184.5 ms
    winner         353.7 ms              world cup              145.2 ms
    election       157.6 ms              president               92.5 ms
    world series    23.8 ms              government shutdown     53.9 ms
                                         best actor / nba champion / best
                                         picture / stanley cup / super bowl /
                                         fed chair                1.7-23.9 ms

The subjects are the SLOWEST terms in the set, and they are plausible real user
queries. But on `champion` the status bitmap is only 22.2 ms of 400 ms, so
"80% of the arm" is a fact about `world series` and would have been a false
generalisation. The DEFECT the two shapes share is one level down:

    %winner% matches 42,336 rows in futures_markets.
    3,483 of them (8.2%) are status='open'.

`futures_markets` is 858,938 rows, of which 71,368 (8.3%) are open. **Every
futures search trigram bitmap is built over the whole corpus, while only ~8% of
what it returns can ever appear in a result.** On `champion` the BitmapOr returns
70,711 rows and the heap scan emits 3,794. That ~12x of discarded work is paid
three times over -- in the bitmap scan, in the BitmapAnd against `status`, and in
the heap recheck -- and for the four subject terms a fourth time in a
71,368-row btree bitmap that exists only to perform the discard.

This is not one query's bad luck. Production counters agree, independently of
any probe of mine (`pg_stat_user_indexes`, read 2026-08-25):

    ix_futures_markets_status   774,030 scans   50,433,836,336 tuples read

50.4 **billion** tuples -- the highest tuple-read of any index on either futures
table, at **65,155 rows per scan**, which reproduces the 71,368 above.

THE SPEC THIS GATES
-------------------
`docs/audits/latency/lat-p088-futures-open-trgm-index-spec.md` -- ONE attended
`CREATE INDEX CONCURRENTLY`, run by hand outside Alembic (ruling 131; gotcha #31
forbids CONCURRENTLY in a migration):

    CREATE INDEX CONCURRENTLY ix_futures_name_trgm_open
        ON futures_markets USING gin (name gin_trgm_ops)
        WHERE status = 'open';

A partial trigram GIN. It attacks all three payments of the same discard at
once: the index holds only open rows, so the bitmap it returns is ~12x smaller;
`status='open'` in the index predicate is implied by the query's own
`status='open'`, so the planner satisfies that clause FROM the index and has no
reason to build the 71,368-row btree bitmap at all; and the heap recheck shrinks
with the bitmap. The application is UNMODIFIED -- there is nothing to build in code, so the only buildable half of
"build it red-first" is this gate. The pattern is already established in this
schema (`ix_fm_feed_open_sports`, `ix_fm_feed_open_timely`,
`ix_fm_feed_open_volume` are all `WHERE status='open'` partials).

Sizing, from `pg_class` rather than from hope: `futures_markets` is 858,938 rows
/ 985 MB, of which 71,368 (8.3%) are open. `ix_futures_name_trgm` is 182 MB, so
the partial is expected near ~15-20 MB. The write tax is paid only on open rows.

    source ~/.claude/.env
    python3 backend/scripts/gate_futures_open_trgm_index.py --label before
    # ... Alex runs the attended psql block ...
    python3 backend/scripts/gate_futures_open_trgm_index.py --label after

Exit 0 = GREEN. Exit 1 = RED. **Any other exit is the harness failing to run,
not a verdict** (gotcha #54 as amended: 1 is a result, everything else is a
story about the harness). Never read a non-1 non-zero as "the index is bad".

WHY THE BUDGET IS A RATIO, AND WHAT THE CONTROL IS
--------------------------------------------------
An absolute millisecond threshold is not usable here, and this lane has the
receipts twice over: LAT-P087 found the teams gate's `exec_ms < 50` PASSING on a
completely unindexed database under a 5.9x load swing, and found the feed wall
p50 unable to see #2143 under a 94.1 ms swing between two runs of one instrument.

So the budget is `median(name_arm) / median(outcome_arm)`, both measured in the
SAME interleaved batch, seconds apart.

**AND THE THRESHOLD IS RELATIVE TO THE RECORDED BEFORE, NOT A CONSTANT.** This
is the correction the first draft of this very file needed, caught by running it:
with a hardcoded `ratio <= 0.25`, the term `super bowl` **PASSED the budget with
no index in production at all** (ratio 0.095, because its name arm is 1.7 ms and
the control is 18.3 ms). A constant cannot distinguish "the index worked" from
"this term was always cheap" -- which is LAT-P087's teams finding arriving on the
lane's own next gate, one cycle later, in the same shape.

The criterion is therefore, PER TERM, `collapse = ratio_after / ratio_before`,
with the before read from the recorded baseline JSON; the budget passes when
`median(collapse) <= 0.5`. A no-op reproduces the before ratio, so every collapse
is 1.0 and it fails BY CONSTRUCTION -- there is no value of the underlying
milliseconds at which doing nothing passes. The 0.5 factor is deliberately
conservative against a mechanism worth ~12x: it leaves room for floor effects on
terms like `super bowl` that have almost nothing left to win, and for the
control's own share of the ratio.

**The collapse is PER TERM and only then pooled** -- the third draft's bug, also
caught by running it. A median of raw milliseconds pooled ACROSS terms is
meaningless here, because the control's own level differs by ~100x between terms:
in one interleaved batch `champion`'s control ran 4,343.8 ms and `election`'s ran
67.4 ms. The outcome arm is a different query for every term, with its own
selectivity, so pooling raw times hands the verdict to whichever term happens to
have the largest control. The control is CPU-matched in TIME (it absorbs the same
ambient excursion, measured seconds apart), never in LEVEL -- so it is only
comparable against ITSELF, on the same term.

Two further criteria exist because a faster plan is not automatically a better
one:
 * **non-regression**, per term: no term's ratio may exceed 1.5x its own
   recorded before. A new index changes the planner's choices globally, and a
   term that got slower must not be hidden inside a pooled median that improved.
 * **subject shape**, per term: the terms that HAD the `status` bitmap must no
   longer have it. Which terms those are is read from the baseline, not
   hardcoded, so the classification is measured rather than asserted.

   That distinction earned itself immediately. `world series` built the status
   bitmap during the 14-term probe above and did NOT build it in the `before` run
   an hour later -- same query, same database, different plan, because the
   planner's cost estimate for a 71,368-row bitmap sits near the tipping point
   and moves with the cache state it is costed against. Had the four subjects
   been written into a constant, the `after` run would have demanded a shape
   change on a term that no longer had the shape, and reported a RED about the
   planner's mood. The baseline is the authority; the table above is a dated
   observation, not a specification.

The **outcome arm is the control**, and it is CPU-matched by construction:
 * same operator class -- `gin_trgm_ops` bitmap index scan + heap recheck;
 * same instant -- interleaved per round, so an excursion lands on both;
 * same tail -- both arms carry the identical `ts_rank_cd` ORDER BY over
   `to_tsvector(name)`, so that CPU appears on both sides and largely cancels;
 * **and the DDL cannot serve it.** The outcome arm reaches `futures_markets`
   only by primary key; its trigram work is on `futures_outcomes.name`, a
   different table, which this index does not touch.

That last clause is what makes it a control rather than a second copy of the
subject. `--arm outcome` in `explain_search_arm.py` additionally strips the
`CASE WHEN name ILIKE ...` tier from the control's ORDER BY, because leaving the
subject's own predicate inside the control is the failure LAT-P087 already made
once with a `count(*) WHERE id > 0` that stayed flat through the very excursion
it existed to absorb. A control only cancels the noise it shares.

The SQL is COMPILED FROM THE LIVE ORM via `explain_search_arm.build_futures_arm`
-- the same helpers `search_events()` uses -- never hand-pasted. If the route's
predicate changes, this gate's SQL changes with it and the shape check fails
honestly. A hand-copied blob would keep passing against an index the route no
longer matches. That is not hypothetical: LAT-P086 caught exactly that in
LAT-P085's proposed altnames DDL (`::text` vs `CAST(... AS VARCHAR)`).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
REPO = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

import explain_search_arm as ESA  # noqa: E402  (needs the sys.path above)

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")

#: The one index the attended DDL creates.
EXPECTED_INDEX = "ix_futures_name_trgm_open"

#: The index whose 71,368-row bitmap the partial index exists to REMOVE. Its
#: presence in the name-arm plan is a FAIL after the DDL: it means the planner
#: still needs a separate `status='open'` bitmap, i.e. it is not satisfying that
#: clause from the partial index, i.e. the index is not doing its job even if it
#: appears in the plan alongside.
FORBIDDEN_INDEX = "ix_futures_markets_status"

#: Terms with a real outcome arm (so the control exists), chosen from a 14-term
#: probe to cover BOTH measured plan shapes rather than whichever came to mind:
#: the four that build the `status` bitmap and four that do not. Single common
#: words and multi-word phrases both appear, because they take different code
#: paths in `search_events()` (`len(terms) > 1` branches the whole predicate).
TERMS = (
    # measured SUBJECTS -- status bitmap present 2026-08-25
    "world series",
    "champion",
    "winner",
    "election",
    # measured bystanders -- trigram scan only; the partial index still shrinks
    # their bitmap ~12x, so they are gated for non-regression, not for a win
    "world cup",
    "presidential election",
    "super bowl",
    "best picture",
)

#: Budget ceiling on `median_over_terms(ratio_after / ratio_before)`. RELATIVE,
#: so a no-op scores 1.0 and fails by construction.
#:
#: THIS MUST NEVER BECOME AN ABSOLUTE MILLISECOND OR RATIO CONSTANT. Two drafts
#: of this file were wrong in that exact direction: a hardcoded `ratio <= 0.25`
#: passed `super bowl` with no index in production at all, and a pooled median of
#: raw milliseconds was decided by whichever term had the oddest control.
#: `tests/test_gate_futures_open_trgm_index.py` fails on a reintroduced `*_MS`
#: threshold, because the lane has now made this mistake three times.
MEDIAN_COLLAPSE_FACTOR = 0.5

#: Per-term ceiling as a multiple of that term's OWN recorded before ratio. A
#: pooled win must not conceal a term the new index made slower.
PER_TERM_REGRESSION_FACTOR = 1.5

#: Rounds per term. Interleaved name/outcome within each round.
DEFAULT_ROUNDS = 5

AUDIT_DIR = os.path.join(REPO, "docs", "audits", "latency")
BASELINE = os.path.join(AUDIT_DIR, "lat-p088-futures-open-trgm-red.json")


class DbQueryFailed(Exception):
    """A db-query round trip that failed for a REPORTABLE reason.

    Raised only by `_post(..., fatal=False)`. Everything else still exits 2,
    because a harness that cannot run must not produce a verdict.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _post(sql: str, *, analyze: bool, timeout_ms: int = 25000, fatal: bool = True) -> dict:
    """One `/api/admin/db-query` round trip.

    Deliberately does NOT swallow failures into an empty return: a refused query
    and an empty result must not arrive in the same shape (gotcha #53), or a gate
    that never ran reads as a gate that found nothing.
    """
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        sys.exit(2)
    body: dict = {"sql": sql}
    if analyze:
        # `timeout_ms` is honoured ONLY alongside `explain: true`; sending it on
        # the plain row path 400s the request. That is how LAT-P087's first gate
        # run exited 2 -- recorded here so it is not rediscovered.
        body["explain"] = True
        body["analyze"] = True
        body["timeout_ms"] = timeout_ms
    request = urllib.request.Request(
        f"{API}/api/admin/db-query",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        if not fatal:
            reason = "statement_timeout" if "statement_timeout" in detail else f"http_{exc.code}"
            raise DbQueryFailed(reason) from exc
        print(f"ERROR: db-query HTTP {exc.code}: {detail}", file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError as exc:
        if not fatal:
            raise DbQueryFailed("unreachable") from exc
        print(f"ERROR: db-query unreachable: {exc}", file=sys.stderr)
        sys.exit(2)


def _exec_ms(payload: dict) -> float:
    blob = json.dumps(payload.get("plan"))
    match = re.search(r'"Execution Time":\s*([0-9.]+)', blob)
    if not match:
        print("ERROR: no Execution Time in plan -- analyze did not run", file=sys.stderr)
        sys.exit(2)
    return float(match.group(1))


def _bitmap_index_scans(payload: dict) -> set[str]:
    """Index names under a `Bitmap Index Scan` node."""
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

    walk(payload.get("plan"))
    return found


def _sql_for(term: str, arm: str) -> str:
    stmt, _terms, _expanded, _n = ESA.build_futures_arm(term, arm)
    return ESA.compile_sql(stmt)


def per_term_collapses(terms: dict) -> dict[str, float]:
    """`ratio_after / ratio_before`, per term. 1.0 means nothing changed.

    A free function, not inline in `main()`, precisely so the no-op-fails
    property is testable without a network: see
    `tests/test_gate_futures_open_trgm_index.py`. Two drafts of this gate were
    wrong about this arithmetic and both were caught by running it against
    production rather than by reading it, which is one time too many.

    Terms with no recorded before are omitted rather than defaulted -- a missing
    baseline entry must not contribute a flattering 1.0, nor a passing 0.0.
    """
    return {
        term: round(t["ratio"] / t["before_ratio"], 4)
        for term, t in terms.items()
        if t.get("before_ratio")
    }


def budget_verdict(terms: dict) -> tuple[bool, dict[str, float], str]:
    """(passed, per-term collapses, human note) for an `after` run."""
    collapses = per_term_collapses(terms)
    if not collapses:
        return False, {}, "no before ratios in the baseline -- cannot compute a collapse"
    median_collapse = statistics.median(collapses.values())
    return (
        median_collapse <= MEDIAN_COLLAPSE_FACTOR,
        collapses,
        f"median per-term collapse {median_collapse:.4f} vs ceiling "
        f"{MEDIAN_COLLAPSE_FACTOR} (1.0 = no change); per term {collapses}",
    )


def _ids_for(term: str) -> list[int] | str:
    """The FULL production arm's id set -- the semantics check's subject.

    Returns a sorted id list, or the STRING reason it could not be read. A
    timeout is recorded as a distinct value rather than as an empty list,
    because "no rows" and "could not ask" must not arrive in the same shape
    (gotcha #53). `champion` and `winner` genuinely exceed the endpoint's 10 s
    row-path timeout today -- which is itself the finding that the route sheds
    the futures stage on these terms (`events.py:2920`), not a harness bug.
    """
    try:
        payload = _post(_sql_for(term, "all"), analyze=False, fatal=False)
    except DbQueryFailed as exc:
        return f"UNREAD:{exc.reason}"
    rows = payload.get("rows") or []
    return sorted(int(r[0]) for r in rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Red-first gate for ix_futures_name_trgm_open")
    ap.add_argument("--label", required=True, choices=("before", "after"))
    ap.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    ap.add_argument("--out", default=None, help="write the full JSON record here")
    args = ap.parse_args()

    print(f"gate_futures_open_trgm_index --label {args.label} rounds={args.rounds}")
    print(f"expected index: {EXPECTED_INDEX}   forbidden: {FORBIDDEN_INDEX}")
    print(
        f"budget: median per-term (ratio_after / ratio_before) <= {MEDIAN_COLLAPSE_FACTOR} "
        f"(relative, so a no-op cannot pass)\n"
    )

    baseline: dict = {}
    if args.label == "after":
        if not os.path.exists(BASELINE):
            print(
                f"ERROR: no baseline at {BASELINE} -- run --label before first",
                file=sys.stderr,
            )
            return 2
        with open(BASELINE) as fh:
            baseline = json.load(fh)

    record: dict = {
        "label": args.label,
        "rounds": args.rounds,
        "expected_index": EXPECTED_INDEX,
        "forbidden_index": FORBIDDEN_INDEX,
        "median_collapse_factor": MEDIAN_COLLAPSE_FACTOR,
        "per_term_regression_factor": PER_TERM_REGRESSION_FACTOR,
        "terms": {},
    }

    # --- SHAPE + BUDGET, interleaved per round -------------------------------
    for term in TERMS:
        name_sql = _sql_for(term, "name")
        ctrl_sql = _sql_for(term, "outcome")
        name_ms: list[float] = []
        ctrl_ms: list[float] = []
        seen_indexes: set[str] = set()
        for _ in range(args.rounds):
            # Interleaved, name first, so a load excursion lands on both arms
            # within the same second rather than on one arm's whole run.
            p_name = _post(name_sql, analyze=True)
            name_ms.append(_exec_ms(p_name))
            seen_indexes |= _bitmap_index_scans(p_name)
            p_ctrl = _post(ctrl_sql, analyze=True)
            ctrl_ms.append(_exec_ms(p_ctrl))

        n_med = statistics.median(name_ms)
        c_med = statistics.median(ctrl_ms)
        ratio = n_med / c_med if c_med else float("inf")

        base_term = (baseline.get("terms") or {}).get(term) or {}
        was_subject = FORBIDDEN_INDEX in (base_term.get("name_arm_indexes") or [])
        before_ratio = base_term.get("ratio")

        # SHAPE. On a `before` run the expected index does not exist, so this is
        # RED by construction -- that is what red-first means. On an `after` run
        # the partial index must be CHOSEN for every term, and must have replaced
        # the status bitmap for the terms that measurably had one.
        shape_ok = EXPECTED_INDEX in seen_indexes
        if was_subject and FORBIDDEN_INDEX in seen_indexes:
            shape_ok = False

        # NON-REGRESSION, per term, against its own recorded before.
        regression_ok = True
        if before_ratio:
            regression_ok = ratio <= before_ratio * PER_TERM_REGRESSION_FACTOR

        record["terms"][term] = {
            "name_ms": name_ms,
            "ctrl_ms": ctrl_ms,
            "name_median_ms": round(n_med, 1),
            "ctrl_median_ms": round(c_med, 1),
            "ratio": round(ratio, 3),
            "name_arm_indexes": sorted(seen_indexes),
            "was_subject": was_subject,
            "before_ratio": before_ratio,
            "shape_ok": shape_ok,
            "regression_ok": regression_ok,
        }
        role = "SUBJ" if (was_subject or FORBIDDEN_INDEX in seen_indexes) else "byst"
        print(
            f"  {term:<22} {role} name={n_med:7.1f}ms ctrl={c_med:7.1f}ms "
            f"ratio={ratio:6.3f}  shape={'PASS' if shape_ok else 'FAIL'}  "
            f"noregr={'PASS' if regression_ok else 'FAIL'}  idx={sorted(seen_indexes)}"
        )

    # --- SEMANTICS -----------------------------------------------------------
    # The index must not change WHICH markets the arm returns. Recorded on
    # `before`, compared on `after`. A speedup that changes recall is a bug
    # wearing a benchmark's clothes.
    ids_now = {term: _ids_for(term) for term in TERMS}
    record["ids"] = ids_now
    semantics_ok = True
    semantics_note = ""
    if args.label == "before":
        semantics_note = "recorded (no baseline to compare on a before run)"
    else:
        base_ids = baseline.get("ids") or {}
        comparable = [
            t
            for t in TERMS
            if not isinstance(base_ids.get(t), str) and not isinstance(ids_now[t], str)
        ]
        unread_now = [t for t in TERMS if isinstance(ids_now[t], str)]
        unread_before = [t for t in TERMS if isinstance(base_ids.get(t), str)]
        newly_unread = sorted(set(unread_now) - set(unread_before))
        changed = [t for t in comparable if base_ids.get(t) != ids_now[t]]
        if changed:
            semantics_ok = False
            semantics_note = f"id set CHANGED for {changed}"
        elif newly_unread:
            # A term that was readable before and is not now got SLOWER past the
            # endpoint's timeout. That is a regression, not an unknown.
            semantics_ok = False
            semantics_note = f"newly UNREADABLE (slower past the timeout): {newly_unread}"
        elif not comparable:
            semantics_ok = False
            semantics_note = "NO term was comparable -- semantics unproven, not passed"
        else:
            semantics_note = (
                f"{len(comparable)}/{len(TERMS)} id sets identical to the recorded "
                f"before; unread in BOTH runs (excluded, not passed): {unread_before}"
            )
    record["semantics_ok"] = semantics_ok
    record["semantics_note"] = semantics_note
    print(f"\n  semantics: {'PASS' if semantics_ok else 'FAIL'} -- {semantics_note}")

    # --- BUDGET: median of PER-TERM PAIRED collapses -------------------------
    # NOT a pooled median of raw milliseconds. That was the second draft's bug,
    # caught by running it: the control's own level differs by ~100x between
    # terms (`champion` ctrl 4,343 ms vs `election` ctrl 67 ms, same batch),
    # because the outcome arm is a different query per term with its own
    # selectivity. A median pooled across terms is therefore dominated by
    # whichever term has the largest control, and means nothing.
    #
    # The control is CPU-matched in TIME (it absorbs the same ambient excursion,
    # interleaved seconds apart), NOT in level. So it is only valid compared
    # against ITSELF on the same term: `collapse = ratio_after / ratio_before`,
    # per term, then take the median of those. A no-op yields 1.0 on every term
    # and fails; there is no arithmetic path by which doing nothing passes.
    if args.label == "before":
        budget_ok = False
        collapses = {}
        budget_note = (
            "per-term ratios RECORDED as the before; a before run has nothing to "
            "beat, so the budget is RED by construction"
        )
    else:
        budget_ok, collapses, budget_note = budget_verdict(record["terms"])
        if collapses:
            record["median_collapse"] = round(statistics.median(collapses.values()), 4)
    record["per_term_collapse"] = collapses
    record["budget_ok"] = budget_ok
    record["budget_note"] = budget_note
    print(f"  budget:    {'PASS' if budget_ok else 'FAIL'} -- {budget_note}")

    shape_all = all(t["shape_ok"] for t in record["terms"].values())
    regr_all = all(t["regression_ok"] for t in record["terms"].values())
    green = shape_all and budget_ok and regr_all and semantics_ok
    record["verdict"] = "GREEN" if green else "RED"

    out = args.out or (
        BASELINE if args.label == "before"
        else os.path.join(AUDIT_DIR, "lat-p088-futures-open-trgm-after.json")
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(record, fh, indent=2)

    n_terms = len(TERMS)
    print(
        f"\nSHAPE {sum(t['shape_ok'] for t in record['terms'].values())}/{n_terms}  "
        f"NO-REGRESSION {sum(t['regression_ok'] for t in record['terms'].values())}/{n_terms}  "
        f"BUDGET {'1/1' if budget_ok else '0/1'}  "
        f"SEMANTICS {'1/1' if semantics_ok else '0/1'}"
    )
    print(f"VERDICT: {record['verdict']}   (written to {out})")
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
