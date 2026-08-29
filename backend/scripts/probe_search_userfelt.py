#!/usr/bin/env python3
"""Measure and DECOMPOSE what a user feels on `/api/events/search`.

WHY A SECOND PROBE AND NOT A `--path` FLAG ON THE TYPEAHEAD ONE.

`probe_typeahead_userfelt.py` answers ONE question — is this read warm or cold —
because `/typeahead` is a cache-fronted surface where the only interesting fact
is whether the cache had the term. `/api/events/search` is not that shape. It
has no single warm/cold bit to report: it is a **sum of nine measured stages**
that the route will hand you itself via `?debug_timing=1`, and the whole point
of LAT-P085 item 3 is *where the milliseconds go*, not *how many there are*.

Bolting a path flag onto the typeahead probe would have produced a file whose
headline field (`verdict: warm|cold`) is meaningless for half its callers. So
this one records the stage vector as a first-class column and treats the wall
clock as the thing that must RECONCILE against it, not the thing being reported
alone.

Three disciplines carried over verbatim, because they were each bought with a
withdrawn headline:

* **gotcha #53** — `http_code` and `bytes` travel with every sample. A 500 in
  4 ms and a cache hit in 4 ms are the same number and not the same fact. Any
  non-200 is `error`; a 200 with a zero-length body is `empty`; neither is ever
  folded into a latency percentile.
* **The unexplained residual is REPORTED, never absorbed.** `residual_ms =
  wall - total_ms` is transport + JSON serialisation + framework overhead. It is
  written to every row so that a server-side win which does not move the wall is
  visible as a shrinking numerator against a fixed floor, rather than looking
  like a measurement error.
* **The term set travels with the measurement.** `--terms-from file` requires
  `--terms-file`; the default set is the eight LAT-P084 headline terms, mirrored
  here so the search series and the typeahead series are comparable term-for-term.

USAGE
    python3 scripts/probe_search_userfelt.py --rounds 6 --spacing 60 \\
        --out /tmp/search.jsonl --label LAT-P085-baseline
    python3 scripts/probe_search_userfelt.py --summarize /tmp/search.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

#: The LAT-P084 typeahead headline set, mirrored so the two series line up.
HEADLINE_TERMS = (
    "masters winner",
    "stanley cup",
    "world series",
    "nba champion",
    "world cup",
    "red sox",
    "celtics",
    "yankees",
)

#: Stage labels emitted by `search_events()`'s `_mark()` calls, in route order.
#: Listed explicitly so a stage that DISAPPEARS from the response is visible as a
#: missing key rather than silently dropping out of the sum (`event_odds_query`
#: is conditional — it is absent when no event page rows were found).
STAGE_ORDER = (
    "event_count",
    "event_page",
    "event_odds_query",
    "event_odds_aggregate",
    "event_gei",
    "event_teams",
    "futures",
    "futures_format_concepts",
    "teams",
)


def probe_one(base: str, term: str, timeout: float) -> dict:
    qs = urllib.parse.urlencode({"q": term, "debug_timing": "1"})
    url = f"{base.rstrip('/')}/api/events/search?{qs}"
    row: dict = {"term": term, "url_path": "/api/events/search"}
    # LAT-P118: this probe writes one `search_query_logs` row per call and that
    # table elects the 40 warm slots. `X-Bainluck-Origin` stops the vote WITHOUT
    # touching the response cache — which `?debug_timing=1` above does not, and
    # which is why the flag already on this URL was never enough.
    req = urllib.request.Request(url, headers={"X-Bainluck-Origin": "harness"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            row["http_code"] = resp.getcode()
    except urllib.error.HTTPError as e:  # a status IS the answer, not an exception
        body = b""
        row["http_code"] = e.code
        row["error"] = f"HTTPError {e.code}"
    except Exception as e:  # noqa: BLE001 - transport failure, recorded not raised
        body = b""
        row["http_code"] = None
        row["error"] = f"{type(e).__name__}: {e}"
    row["wall_s"] = round(time.perf_counter() - t0, 6)
    row["bytes"] = len(body)

    if row.get("http_code") != 200:
        row["verdict"] = "error"
        return row
    if not body:
        row["verdict"] = "empty"  # gotcha #53: an empty 200 is a shape, not a fact
        return row

    try:
        d = json.loads(body)
    except Exception as e:  # noqa: BLE001
        row["verdict"] = "error"
        row["error"] = f"json: {e}"
        return row

    dt = d.get("debug_timing") or {}
    row["verdict"] = "ok" if dt else "no_debug_timing"
    row["total_ms"] = dt.get("total_ms")
    row["stages"] = {k: dt.get(k) for k in STAGE_ORDER if k in dt}
    row["missing_stages"] = [k for k in STAGE_ORDER if k not in dt]
    if row["total_ms"] is not None:
        row["residual_ms"] = round(row["wall_s"] * 1000 - row["total_ms"], 1)
    row["n_events"] = len(d.get("results") or [])
    row["n_futures"] = len(d.get("futures") or [])
    row["n_teams"] = len(d.get("teams") or [])
    row["degraded"] = d.get("degraded")
    return row


def summarize(path: str) -> int:
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        print("NO ROWS")
        return 1

    ok = [r for r in rows if r.get("verdict") == "ok"]
    bad = [r for r in rows if r.get("verdict") != "ok"]
    print(f"samples={len(rows)}  ok={len(ok)}  non-ok={len(bad)}")
    for r in bad:
        print(f"  NON-OK {r['term']!r} verdict={r.get('verdict')} "
              f"http={r.get('http_code')} err={r.get('error')}")
    if not ok:
        return 1

    walls = sorted(r["wall_s"] * 1000 for r in ok)
    totals = sorted(r["total_ms"] for r in ok if r.get("total_ms") is not None)
    resid = sorted(r["residual_ms"] for r in ok if r.get("residual_ms") is not None)

    def pct(xs, p):
        if not xs:
            return None
        k = min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1))))
        return round(xs[k], 1)

    print(f"\nWALL ms   p50={pct(walls,50)}  p90={pct(walls,90)}  "
          f"p95={pct(walls,95)}  max={round(max(walls),1)}")
    print(f"SERVER ms p50={pct(totals,50)}  p90={pct(totals,90)}  max={max(totals)}")
    print(f"RESIDUAL  p50={pct(resid,50)}  (transport + JSON serialisation)")
    print(f"\nBAR: <500 ms wall.  over_bar={sum(1 for w in walls if w >= 500)}/{len(walls)} "
          f"({100.0*sum(1 for w in walls if w>=500)/len(walls):.1f}%)")

    print("\nSTAGE ATTRIBUTION (ms, over ok samples; share of SERVER total)")
    grand = sum(totals) or 1
    agg: dict[str, list[int]] = {}
    for r in ok:
        for k, v in (r.get("stages") or {}).items():
            if v is not None:
                agg.setdefault(k, []).append(v)
    ordered = sorted(agg.items(), key=lambda kv: -sum(kv[1]))
    print(f"  {'stage':26} {'n':>4} {'p50':>7} {'p90':>7} {'max':>7} {'sum':>9} {'share':>7}")
    for k, vs in ordered:
        vs_s = sorted(vs)
        print(f"  {k:26} {len(vs):>4} {pct(vs_s,50):>7} {pct(vs_s,90):>7} "
              f"{max(vs):>7} {sum(vs):>9} {100.0*sum(vs)/grand:>6.1f}%")

    print("\nPER-TERM (wall p50 ms / server p50 ms / futures p50 ms)")
    by_term: dict[str, list[dict]] = {}
    for r in ok:
        by_term.setdefault(r["term"], []).append(r)
    for term, rs in sorted(by_term.items(),
                           key=lambda kv: -statistics.median(x["wall_s"] for x in kv[1])):
        w = sorted(x["wall_s"] * 1000 for x in rs)
        s = sorted(x["total_ms"] for x in rs if x.get("total_ms") is not None)
        f = sorted((x.get("stages") or {}).get("futures", 0) for x in rs)
        print(f"  {term:20} n={len(rs):>3}  {pct(w,50):>8}  {pct(s,50):>8}  {pct(f,50):>8}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("BAINLUCK_API",
                                                     "https://api.bainluck.com"))
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--spacing", type=float, default=60.0,
                    help="seconds between rounds")
    ap.add_argument("--timeout", type=float, default=40.0)
    ap.add_argument("--terms-from", default="headline", choices=("headline", "file"))
    ap.add_argument("--terms-file", default=None)
    ap.add_argument("--label", default="search-userfelt")
    ap.add_argument("--out", default=None)
    ap.add_argument("--summarize", default=None,
                    help="summarise an existing jsonl instead of probing")
    args = ap.parse_args()

    if args.summarize:
        return summarize(args.summarize)
    if not args.out:
        ap.error("--out is required unless --summarize is given")

    if args.terms_from == "file":
        if not args.terms_file:
            ap.error("--terms-from file requires --terms-file")
        with open(args.terms_file) as fh:
            terms = [ln.strip() for ln in fh if ln.strip()]
    else:
        terms = list(HEADLINE_TERMS)

    with open(args.out, "a") as fh:
        for rnd in range(1, args.rounds + 1):
            for term in terms:
                row = probe_one(args.base, term, args.timeout)
                row.update(round=rnd, label=args.label, terms_from=args.terms_from,
                           ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                print(f"r{rnd} {row['term']:20} {row.get('verdict'):>4} "
                      f"wall={row['wall_s']*1000:8.1f}ms server={row.get('total_ms')}"
                      f" futures={(row.get('stages') or {}).get('futures')}",
                      flush=True)
            if rnd < args.rounds:
                time.sleep(args.spacing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
