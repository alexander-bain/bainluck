#!/usr/bin/env python3
"""Deploy proof for a latency fix, read from `pg_stat_statements` — LAT-P097.

WHY THIS EXISTS. The lane's own instrument for grading a feed fix is the #1459
slow-event ring (`GET /api/admin/latency-slow-events`), and LAT-P095 showed it
cannot grade a deploy on the day of the deploy: it admits only requests above
5,000 ms, `/api/feed` cache-miss inter-arrival is p50 272 s / p90 10,344 s, and
LAT-P097 measured **3 post-deploy misses against 164 pre-deploy** four hours
after two releases. Worse, the admission threshold makes the sample
*survivorship-biased in the direction of the claim*: a miss that the fix makes
faster than 5 s leaves the population silently, so a working fix and a broken
instrument produce the same empty cohort.

`pg_stat_statements` has neither problem. Every execution is counted, on every
dyno, whatever the request took. Two snapshots N minutes apart give a windowed
`calls` / `mean_exec_time` / `shared_blks_hit` per statement, and PostgreSQL 17's
`stats_since` dates a fingerprint's FIRST execution — which is the deploy proof
proper: a statement whose `stats_since` falls seconds after a release is a
statement that release put into production.

WHAT A FAMILY IS. A SQLAlchemy statement built with an `IN`-list of variable
length fingerprints DIFFERENTLY for each length, so one logical statement is
spread over dozens of `queryid`s. Grading by single `queryid` therefore reads a
slice of the truth. Each family below is an ILIKE predicate over `query`, and
the snapshot sums `calls` and `total_exec_time` across every fingerprint that
matches, so the window mean is the call-weighted one.

READ THE ZERO CAREFULLY (gotcha #53). Δcalls = 0 for a retired family is the
result this script exists to show — but it has a second cause: the family was
never called in the window because nothing exercised the path. The verdict lines
below therefore pair every retired family with its replacement, and a
retired-family zero is reported as PROVEN only when the replacement is non-zero
in the same window. A window in which neither ran is `NO_TRAFFIC`, never a pass.

TWO INSTRUMENT DEFECTS FOUND BY THE FIRST A/B WINDOW, and fixed here.

  1. **The snapshot matched its own family.** A family predicate is an ILIKE
     over `query`, and this database does NOT normalise the string constants in
     `query ILIKE '%canonical_source_universe%'` — so the snapshot's own SELECT
     lands in `pg_stat_statements` carrying the literal, and the NEXT snapshot
     counts it as a call of the family it is measuring. Measured: the A->B
     window reported `82_new` +13, of which 1 was the instrument. Every
     predicate now carries `AND query NOT ILIKE '%pg_stat_statements%'`, which
     no application statement can satisfy.

  2. **`82_old` was over-broad and would have printed UNPROVEN.** The retired
     shape `count(DISTINCT source) ... WHERE canonical_market_key IN (...)` has
     a SECOND live caller that `-82` never claimed to change:
     `app/tasks/precompute_interestingness.py:191`, a Celery task off the
     request path. It ran once at 2026-08-27 00:21:15Z, 604.6 ms, 3,509
     buffers, inside the A->B window. The two are separable by their result
     label — the feed path writes `AS source_count`, the task writes `AS cnt` —
     so the retired family is now the feed variant only, and the task variant is
     carried as an UNGRADED sibling: visible in the table, named in the report,
     and unable to flip a verdict it is not part of.

CAVEATS THAT BOUND EVERY NUMBER THIS PRINTS, and are printed with them:
  * `pg_stat_statements` sits near its 5,000-entry cap on this database
    (4,962 measured 2026-08-27), so a low-traffic fingerprint can be EVICTED
    between the two snapshots. An evicted entry's `calls` RESETS, which shows up
    as a negative delta; those are reported as `EVICTED`, not as a number.
  * Errored statements are never recorded at all, so a statement that times out
    is invisible here (memory: the same caveat bounds every reading in this
    program).
  * `mean_exec_time` is database execution time. It excludes the app-side work
    the stage timer in the ring includes, so the two rails do not have to agree
    in absolute terms — only in direction and rough magnitude.

USAGE
    source ~/.claude/.env
    python3 backend/scripts/deploy_proof_stage_statements.py --snapshot a.json
    # ... wait; the longer the window the tighter the means ...
    python3 backend/scripts/deploy_proof_stage_statements.py --snapshot b.json
    python3 backend/scripts/deploy_proof_stage_statements.py --diff a.json b.json

Exit codes (gotcha #54 — read the VALUE): 0 = the diff ran and every graded
family reached a verdict. 1 = at least one family is UNPROVEN or NO_TRAFFIC.
Anything else is the harness failing, not a verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# --------------------------------------------------------------------------
# The families. Each entry is (key, human label, ILIKE predicate over `query`).
#
# `retired_by` names the family that REPLACED this one, and is what makes a
# Δcalls = 0 readable: zero is a pass only when the replacement ran.
#
# `ungraded: True` marks a family that is measured and printed but takes no part
# in any verdict — the surviving off-path sibling of a retired statement. It is
# here so the shape's remaining cost is visible rather than quietly dropped out
# of the family when the predicate is tightened.
# --------------------------------------------------------------------------

#: No application statement contains this token; every statement issued by this
#: script does. See defect 1 in the module docstring.
SELF_EXCLUDE = "%pg_stat_statements%"

FAMILIES: dict[str, dict] = {
    # LAT-P093 / `-82` — futures.canonical_counts.
    #
    # The result label is what separates the retired request-path statement from
    # the Celery task that shares its shape: `feed.py` labels the aggregate
    # `source_count`, `precompute_interestingness.py` labels it `cnt`.
    "82_old": {
        "label": "-82 OLD  count(DISTINCT source) GROUP BY key  [feed path]",
        "ilike": [
            "%count(distinct(futures_markets.source)) AS source_count%",
            "%futures_markets.canonical_market_key IN%",
        ],
        "retired_by": "82_new",
    },
    "82_sibling_task": {
        "label": "-82 SIBLING  same shape in precompute_interestingness [task]",
        "ilike": [
            "%count(distinct(futures_markets.source)) AS cnt%",
            "%futures_markets.canonical_market_key IN%",
        ],
        "ungraded": True,
    },
    "82_new": {
        "label": "-82 NEW  recursive source universe + EXISTS skip scan",
        "ilike": ["%canonical_source_universe%"],
        "replaces": "82_old",
    },
    # LAT-P094 / `-83` — the concept tier's open-market reads.
    "83_old_ufc": {
        "label": "-83 OLD  ufc lister, llm_sport_category = $1",
        "ilike": [
            "%SELECT futures_markets.id, futures_markets.external_id, "
            "futures_markets.name, futures_markets.commence_time, "
            "futures_markets.market_metadata %",
            "%futures_markets.llm_sport_category = %",
        ],
        "retired_by": "83_new",
    },
    "83_old_f1": {
        "label": "-83 OLD  f1 lister, llm_sport_category = $1",
        "ilike": [
            "%SELECT futures_markets.id, futures_markets.name, "
            "futures_markets.status, futures_markets.resolution_date %",
            "%futures_markets.llm_sport_category = %",
        ],
        "retired_by": "83_new",
    },
    "83_old_cycling": {
        "label": "-83 OLD  cycling lister, llm_sport_category = $1",
        "ilike": [
            "%SELECT futures_markets.name, futures_markets.status, "
            "futures_markets.resolution_date %",
            "%futures_markets.llm_sport_category = %",
        ],
        "retired_by": "83_new",
    },
    "83_new": {
        "label": "-83 NEW  prefetch_open_markets, llm_sport_category IN (...)",
        "ilike": [
            "%futures_markets.llm_sport_category, futures_markets.id, "
            "futures_markets.external_id%",
            "%futures_markets.llm_sport_category IN %",
        ],
        "replaces": "83_old_ufc",
    },
}

# The releases whose `stats_since` these families should sit against. Written
# down so the proof states which deploy it is grading, rather than inferring it.
RELEASES = {
    "82_new": ("v3903", "af9c3ffb", "2026-08-26T20:32:05Z"),
    "83_new": ("v3905", "d2169e1d", "2026-08-26T22:12:40Z"),
}

SELECT_COLUMNS = (
    "coalesce(sum(calls), 0) AS calls, "
    "coalesce(sum(total_exec_time), 0) AS total_ms, "
    "coalesce(sum(shared_blks_hit), 0) AS blks, "
    "count(*) AS fingerprints, "
    "min(stats_since)::text AS first_seen, "
    "max(stats_since)::text AS last_new_fingerprint"
)


def _db_query(sql: str) -> dict:
    """One read through the admin read-only SQL endpoint.

    No `timeout_ms`: the endpoint accepts it only alongside `explain: true` and
    400s otherwise. These are aggregates over a 5,000-row in-memory view and
    measured at ~50 ms, so the server default is not a constraint here.
    """
    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        print(
            "BAINLUCK_API / ADMIN_TOKEN missing — `source ~/.claude/.env` first.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    body = json.dumps({"sql": sql, "limit": 50}).encode()
    req = urllib.request.Request(
        f"{api}/api/admin/db-query",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # a refusal carries a reason; print it
        print(f"db-query HTTP {exc.code}: {exc.read()[:400]!r}", file=sys.stderr)
        raise SystemExit(2) from exc


def snapshot() -> dict:
    """One reading of every family, plus the entry count that bounds it."""
    cap = _db_query("SELECT count(*) AS n FROM pg_stat_statements")
    entries = cap["rows"][0][0]
    now = _db_query("SELECT now()::text AS now")["rows"][0][0]

    out: dict = {
        "taken_at": now,
        "pg_stat_statements_entries": entries,
        "families": {},
    }
    for key, fam in FAMILIES.items():
        where = " AND ".join(
            "query ILIKE '" + pat.replace("'", "''") + "'" for pat in fam["ilike"]
        )
        # Defect 1: without this the script counts its own reads as calls of the
        # family it is reading.
        where += " AND query NOT ILIKE '" + SELF_EXCLUDE + "'"
        # `toplevel` is not filtered: these statements run inside the request,
        # not inside a function, and filtering it would silently drop a row if
        # that ever stopped being true.
        row = _db_query(
            f"SELECT {SELECT_COLUMNS} FROM pg_stat_statements WHERE {where}"
        )["rows"][0]
        # Per-fingerprint detail, not just the aggregate. A family's
        # `min(stats_since)` is NOT automatically the deploy date: this lane runs
        # ad-hoc A/B probes through `db-query` while measuring, and those land in
        # the same view under their own `queryid` with an earlier timestamp. The
        # `-82` family carries exactly such a probe (19:23:28Z, 71 minutes before
        # v3903). Listing every fingerprint makes the lane's own contamination
        # readable instead of silently pulling the family's first-seen backwards.
        detail = _db_query(
            "SELECT queryid, calls, stats_since::text "
            f"FROM pg_stat_statements WHERE {where} ORDER BY stats_since"
        )["rows"]
        out["families"][key] = {
            "label": fam["label"],
            "calls": int(row[0]),
            "total_ms": float(row[1]),
            "blks": int(row[2]),
            "fingerprints": int(row[3]),
            "first_seen": row[4],
            "last_new_fingerprint": row[5],
            "by_fingerprint": [
                {"queryid": d[0], "calls": int(d[1]), "stats_since": d[2]}
                for d in detail
            ],
        }
    return out


def _fmt(v: float | None, nd: int = 1) -> str:
    return "—" if v is None else f"{v:,.{nd}f}"


def diff(a: dict, b: dict) -> int:
    print(f"# Deploy proof — pg_stat_statements window")
    print(f"snapshot A : {a['taken_at']}   ({a['pg_stat_statements_entries']} entries)")
    print(f"snapshot B : {b['taken_at']}   ({b['pg_stat_statements_entries']} entries)")
    print()

    windowed: dict[str, dict] = {}
    for key in FAMILIES:
        # A snapshot taken before a family was defined simply has no row for it.
        # That is "not measured", which must not read as "measured zero".
        if key not in a["families"] or key not in b["families"]:
            windowed[key] = {
                "calls": 0, "evicted": False, "mean_ms": None,
                "blks_per_call": None, "first_seen": "NOT IN BOTH SNAPSHOTS",
                "fingerprints": 0, "unmeasured": True,
            }
            continue
        fa, fb = a["families"][key], b["families"][key]
        d_calls = fb["calls"] - fa["calls"]
        evicted = d_calls < 0
        d_ms = fb["total_ms"] - fa["total_ms"]
        d_blks = fb["blks"] - fa["blks"]
        windowed[key] = {
            "calls": d_calls,
            "evicted": evicted,
            "mean_ms": (d_ms / d_calls) if d_calls > 0 else None,
            "blks_per_call": (d_blks / d_calls) if d_calls > 0 else None,
            "first_seen": fb["first_seen"],
            "fingerprints": fb["fingerprints"],
        }

    print(f"{'family':58s} {'Δcalls':>8s} {'mean ms':>10s} {'blks/call':>11s}  first seen")
    for key, fam in FAMILIES.items():
        w = windowed[key]
        flag = "  EVICTED" if w["evicted"] else ""
        print(
            f"{fam['label']:58s} {w['calls']:>8,d} {_fmt(w['mean_ms']):>10s} "
            f"{_fmt(w['blks_per_call'], 0):>11s}  {w['first_seen']}{flag}"
        )
    print()

    exit_code = 0
    for key, fam in FAMILIES.items():
        if "replaces" not in fam:
            continue
        new = windowed[key]
        olds = {k: windowed[k] for k, f in FAMILIES.items() if f.get("retired_by") == key}
        old_calls = sum(o["calls"] for o in olds.values() if not o["evicted"])
        any_evicted = any(o["evicted"] for o in olds.values())
        any_unmeasured = any(o.get("unmeasured") for o in olds.values()) or new.get(
            "unmeasured"
        )

        rel = RELEASES.get(key)
        print(f"## {fam['label']}")
        if rel:
            print(f"   release      : {rel[0]} ({rel[1]}) at {rel[2]}")
            # A family added after snapshot A was taken has no row in it.
            # Printing a KeyError traceback in place of a verdict would make the
            # harness failure look like a measurement failure (gotcha #54).
            _fa = a["families"].get(key)
            print(f"   first seen   : "
                  f"{_fa['first_seen'] if _fa else 'NOT IN SNAPSHOT A'}")
        print(f"   Δcalls new   : {new['calls']:,d}")
        print(f"   Δcalls retired: {old_calls:,d} across {len(olds)} families"
              + ("  (one or more EVICTED — see above)" if any_evicted else ""))
        if any_unmeasured:
            print("   VERDICT      : UNMEASURED — one side of this pair is absent "
                  "from a snapshot (family added after it was taken). Re-snapshot "
                  "both ends; do not read the zero.")
            exit_code = 1
        elif new["calls"] <= 0:
            print("   VERDICT      : NO_TRAFFIC — the new path did not run in this "
                  "window. Not a pass; widen the window.")
            exit_code = 1
        elif old_calls > 0:
            print(f"   VERDICT      : UNPROVEN — the retired path ran {old_calls:,d} "
                  "times in a window where the new path also ran. Either the deploy "
                  "is partial, or the ILIKE family is over-broad.")
            exit_code = 1
        else:
            print(f"   VERDICT      : PROVEN — the retired path ran 0 times while the "
                  f"new path ran {new['calls']:,d} times. Window mean "
                  f"{_fmt(new['mean_ms'])} ms, {_fmt(new['blks_per_call'], 0)} "
                  "buffers/call.")
        print()

    for key, fam in FAMILIES.items():
        if not fam.get("ungraded"):
            continue
        w = windowed[key]
        print(f"## {fam['label']}   (UNGRADED — takes part in no verdict)")
        if w.get("unmeasured"):
            print("   not present in both snapshots.")
        elif w["calls"] > 0:
            print(f"   Δcalls {w['calls']:,d}, window mean {_fmt(w['mean_ms'])} ms, "
                  f"{_fmt(w['blks_per_call'], 0)} buffers/call. The retired shape "
                  "SURVIVES here, off the request path.")
        else:
            print("   Δcalls 0 in this window — the sibling did not run. Not a "
                  "statement about whether it still exists.")
        print()

    print("Caveats, restated because they bound every number above: "
          "pg_stat_statements is near its 5,000-entry cap so a quiet fingerprint "
          "can be evicted mid-window; errored statements are never recorded, so a "
          "timing-out statement is invisible; and these are DATABASE times, not "
          "the app-side stage timings the slow-event ring reports.")
    return exit_code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", metavar="OUT.json", help="take a snapshot")
    ap.add_argument("--diff", nargs=2, metavar=("A.json", "B.json"))
    args = ap.parse_args()

    if args.snapshot:
        snap = snapshot()
        with open(args.snapshot, "w") as fh:
            json.dump(snap, fh, indent=2)
        print(f"snapshot written: {args.snapshot}  ({snap['taken_at']})")
        for key, fam in snap["families"].items():
            print(
                f"  {fam['label']:58s} calls={fam['calls']:>9,d} "
                f"fingerprints={fam['fingerprints']:>3d} first={fam['first_seen']}"
            )
        return 0

    if args.diff:
        with open(args.diff[0]) as fh:
            a = json.load(fh)
        with open(args.diff[1]) as fh:
            b = json.load(fh)
        return diff(a, b)

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
