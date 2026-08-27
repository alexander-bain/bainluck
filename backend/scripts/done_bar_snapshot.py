#!/usr/bin/env python3
"""The latency charter's done-bar, as one repeatable snapshot — LAT-P097.

THE BAR IS NOT THIS SCRIPT'S TO CHOOSE. `docs/PRD.md` §"latency charter" (Alex
ruling 2026-08-24) says the program is graded on two user-facing numbers that
open every report — **feed p50 and typeahead p50, with deltas per cycle** — and
that the standing target is **the feed miss share and cost** (37.5 % at ~4.1 s at
the first honest measurement). This script measures exactly those and nothing
else, so a cycle cannot quietly re-pick the number it reports.

FOUR MEASUREMENTS, and why each is taken the way it is:

1. `feed_warm` — `GET /api/feed?limit=20` × n, **server-side** `x-response-time`.
   Wall time is not usable: this sandbox's network floor to Heroku is ~246 ms p50
   against a warm feed of ~18 ms, so wall time would report the network.

2. `feed_by_cache` — read out of `GET /api/admin/latency-stats`, NOT generated.
   This is the only rail that carries the **miss share**, because it sees real
   traffic's cache buckets. A client cannot measure a miss share by asking: every
   request it makes warms the thing it is trying to catch cold.

3. `typeahead_warm` — a term asked twice, the SECOND touch timed, × n.

4. `typeahead_cold` — n never-asked terms, FIRST touch. This is the half that
   fails the bar, and it is 147× the warm number, so reporting a blended
   typeahead p50 would hide the entire finding behind the cache hit rate.

🔴 THIS SCRIPT'S FIRST CONTAMINATION BUDGET WAS WRONG, AND IT DID REAL HARM.
Kept in full, because the arithmetic is the lesson.

The original claim was: `/api/events/typeahead` votes into `search:trending:24h`
on the cache-miss path, "the head cut sits near 65 votes over 30 days and these
terms get one each", therefore no head membership can move. **That budget was
priced against the wrong distribution.** 65 is the cut in `search_query_logs`,
a 30-day table. This script writes to `search:trending:24h`, a 24-HOUR zset whose
rank 2 sat at **9**. `resolve_head` blends both at ~20 slots each, so a probe
needs SINGLE-DIGIT votes to buy a warm slot.

Measured two hours after the first run, on `GET /api/events/search/trending`:

    celtics         62   <- the only real user traffic in the top five
    emmy             9   <- this script's probe
    wimbledon        8   <- this script's probe
    hurricane        8   <- this script's probe
    tour de france   6   <- this script's probe

**Four of the top five.** The head is a fixed 40 slots, so each probe term held
a slot a real user's term did not, and the displaced term paid the full ~4 s cold
build. `emmy` was still serving `q=0` five hours after its last touch against a
65 s TTL — the signature of a term the warmer had adopted and was rebuilding
every ~37 s.

⇒ **A contamination budget priced against a distribution you READ instead of the
one you WRITE to is not a budget.** Generalised: name the exact key your
instrument mutates, and read that key's rank-2 score, not a related table's.

THE FIX, and why cold probes now default to `?debug_timing=1`. The route sets
`_suppress_trending_write` for debug calls (LAT-P097/P098, #1866), so a debug
probe casts no vote at all. That is a strictly better trade than a budget:
0 votes rather than a small number argued to be safe.
⚠️ IT IS NOT FREE, AND THE OFFSET IS LARGE — 2.2x, MEASURED, NOT "SLIGHTLY".
`debug_timing` bypasses the response cache in BOTH directions, so it returns the
cold BUILD without the cache write the real first touch also pays. Same slug,
same seven `p095` terms, same session:

    voting mode (true first touch)   p50 3,530 ms   7/7 graded
    debug mode  (cold build)         p50 1,597 ms   7/7 graded

That is the SALT MISTAKE IN A NEW COSTUME — a methodology change that
manufactures a 2.2x improvement — and it is why the delta-vs-baseline line below
is printed ONLY in voting mode. LAT-P095's published 3,816 ms was a true first
touch; subtracting a debug-mode number from it would report a 2,219 ms win that
is entirely the flag. The two modes are separate series and are never mixed.

Use debug mode for: routine cycle tracking, any run with a large n, anything
where the harm of voting outweighs the need for the headline number.
Use `--voting-probes` for: the published headline, at the smallest n that will
carry it.

WHY THE COLD TERMS ARE NOT SALTED, and how a cache hit is caught instead.
The typeahead response cache TTL is 45 s, so a term anything touched in the last
three-quarters of a minute measures the cache and not the build. The obvious
guard — append a per-run salt so the term is guaranteed novel — is WRONG and was
measured wrong before being removed: `kaiserslautern LAT-P097-A` is a TWO-token
query, and the second token ANDs into `_expanded_tsquery`, making the search more
selective and the plan cheaper. Salted terms measured a first-touch p50 of
1,458 ms in the same session that the bare token `werder` measured 3,192 ms. The
salt was reporting a 2.2× win that was purely its own artefact.

So terms are bare, and the cache is detected rather than avoided. `x-timing-split`
carries `q=<query count>`: a genuine cold build reports `q=8; db=3125.3`, a cache
hit reports `q=0; db=0.0`. Any probe returning `q=0` is DISCARDED from the cold
p50 and counted in `cold_discarded_cache_hits` — never silently averaged in,
because a cache hit in a cold sample drags the median toward the answer the
measurement wants.

Exit codes (gotcha #54 — read the VALUE): 0 = every bar measured and MET.
1 = measured and NOT MET. Anything else is the harness failing, not a verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------
# The bars. Sourced, not invented — see the module docstring.
# --------------------------------------------------------------------------

#: `docs/PRD.md`: "feed p50 16ms warm" was the first honest measurement. The bar
#: is "does not regress off that baseline", expressed with headroom.
FEED_WARM_BAR_MS = 50.0

#: The warm typeahead has measured 24–28 ms across three cycles.
TYPEAHEAD_WARM_BAR_MS = 100.0

#: The failing half. A dropdown that a person waits on is a keystroke-path
#: surface; 500 ms is the threshold at which a suggestion list stops feeling
#: like it is responding to typing. LAT-P095 measured 3,816 ms.
TYPEAHEAD_COLD_BAR_MS = 500.0

#: `docs/PRD.md`: "37.5% of loads miss at ~4.1s — the miss share/cost is the
#: standing target". Both halves have to come down for the target to be met.
FEED_MISS_SHARE_BAR = 0.375
FEED_MISS_P50_BAR_MS = 1000.0

#: TWO term sets, and the default is the CONTINUITY one.
#:
#: The charter grades the program on "feed p50 and typeahead p50 with deltas per
#: cycle", and a delta against a different term set is not a delta. `p095` is the
#: exact set LAT-P095 measured at a 3,816 ms first-touch p50, so every future run
#: is comparable to the number the program already published. Changing this set
#: silently re-baselines the headline; measured, that is not a small effect —
#: `obscure` below returns 1,725 ms on the same slug in the same session, a 2.0x
#: "improvement" that is entirely the term list.
#:
#: `obscure` exists for `--voting-probes` runs, where contamination is real
#: again. It is NOT a safe-because-obscure list: `emmy`, `wimbledon`, `hurricane`
#: and `tour de france` from the `p095` set took ranks 2–5 of
#: `search:trending:24h` on 8 votes or fewer, and a second-tier football club
#: would have done the same — rank 2 sat at 9. The earlier version of this
#: comment claimed "a head cut near 65 votes over 30 days" made one vote per
#: cycle unreachable; that was the wrong distribution and it is corrected in the
#: module docstring. `obscure` buys terms whose displacement costs a real user
#: less, not terms that cannot displace.
TERM_SETS: dict[str, list[str]] = {
    "p095": [
        "ballon",
        "wimbledon",
        "nvidia earnings",
        "tour de france",
        "senate runoff",
        "emmy",
        "hurricane",
    ],
    "obscure": [
        "kaiserslautern",
        "sanfrecce",
        "empoli",
        "randers",
        "bochum",
        "heidenheim",
        "elfsborg",
        "cagliari",
        "genoa",
        "udinese",
        "lecce",
        "verona",
    ],
}

#: LAT-P095's published first-touch p50 over the `p095` set, for the delta line.
P095_BASELINE_COLD_P50_MS = 3816.0

WARM_TERM = "celtics"


def _get(path: str, *, token: str | None = None) -> tuple[int, dict, float]:
    """One GET. Returns (status, headers, wall_ms)."""
    api = os.environ["BAINLUCK_API"]
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(f"{api}{path}", headers=headers)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
            return resp.status, dict(resp.headers), (time.monotonic() - t0) * 1000
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), (time.monotonic() - t0) * 1000


def _server_ms(headers: dict) -> float | None:
    """The API's own `x-response-time`, in ms. None if the header is absent.

    Absent is NOT zero and is not silently dropped: a missing header means the
    middleware did not run, which is a different fact from a fast request.
    """
    raw = headers.get("x-response-time") or headers.get("X-Response-Time")
    if not raw:
        return None
    raw = raw.strip().lower()
    try:
        if raw.endswith("ms"):
            return float(raw[:-2])
        if raw.endswith("s"):
            return float(raw[:-1]) * 1000
        return float(raw)
    except ValueError:
        return None


def _split_queries(headers: dict) -> int | None:
    """`q=<n>` out of `x-timing-split`, the cache-status signal.

    A cold build reports `q=8; db=3125.3`; a cache hit reports `q=0; db=0.0`.
    Returns None when the header is absent — which is "cannot tell", a different
    fact from "zero queries", and the caller treats it as ungradeable.
    """
    raw = headers.get("x-timing-split") or headers.get("X-Timing-Split")
    if not raw:
        return None
    for part in raw.split(";"):
        k, _, v = part.strip().partition("=")
        if k == "q":
            try:
                return int(float(v))
            except ValueError:
                return None
    return None


def _p50(vals: list[float]) -> float | None:
    return statistics.median(vals) if vals else None


def _fmt(v: float | None, nd: int = 1) -> str:
    return "—" if v is None else f"{v:,.{nd}f}"


def measure(n_feed: int, n_warm: int, n_cold: int, salt: str, offset: int,
            term_set: str, voting_probes: bool) -> dict:
    token = os.environ["ADMIN_TOKEN"]
    out: dict = {"salt": salt, "requests_issued": 0, "trending_votes_cast": 0}

    # --- 0. Which slug is being graded, and is it warm? -------------------
    _, _, _ = _get("/api/health")
    status, headers, _ = _get("/api/health")
    api = os.environ["BAINLUCK_API"]
    with urllib.request.urlopen(f"{api}/api/health", timeout=30) as resp:
        health = json.loads(resp.read())
    out["commit"] = health.get("commit")
    out["uptime_seconds"] = health.get("uptime_seconds")
    out["warm_slug"] = (health.get("uptime_seconds") or 0) > 300
    out["requests_issued"] += 3

    # --- 1. feed warm, server-side ---------------------------------------
    feed = []
    for _ in range(n_feed):
        _, h, _ = _get("/api/feed?limit=20")
        ms = _server_ms(h)
        if ms is not None:
            feed.append(ms)
        out["requests_issued"] += 1
    out["feed_warm_ms"] = feed
    out["feed_warm_p50"] = _p50(feed)

    # --- 2. feed miss share + miss cost, READ not generated ---------------
    api = os.environ["BAINLUCK_API"]
    req = urllib.request.Request(
        f"{api}/api/admin/latency-stats?top=30",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        stats = json.loads(resp.read())
    row = next(
        (e for e in stats.get("endpoints", []) if e["endpoint"] == "/api/feed"), None
    )
    if row:
        buckets = row.get("by_cache_status", {})
        miss = buckets.get("miss", {})
        total = row.get("n") or 0
        out["feed_stats"] = {
            "window": stats.get("window"),
            "generated_at": stats.get("generated_at"),
            "n": total,
            "oldest_sample_age_s": row.get("newest_sample_age_s"),
            "span_s": row.get("oldest_sample_age_s"),
            "buckets": {k: v.get("n") for k, v in buckets.items()},
            "miss_n": miss.get("n"),
            "miss_p50_ms": miss.get("p50_ms"),
            "miss_max_ms": miss.get("max_ms"),
            "miss_share": (miss.get("n") / total) if total else None,
        }
    else:
        out["feed_stats"] = None

    # --- 3. typeahead warm (second touch) ---------------------------------
    warm = []
    for _ in range(n_warm):
        _get(f"/api/events/typeahead?q={WARM_TERM}")  # prime
        _, h, _ = _get(f"/api/events/typeahead?q={WARM_TERM}")
        ms = _server_ms(h)
        if ms is not None:
            warm.append(ms)
        out["requests_issued"] += 2
    out["typeahead_warm_ms"] = warm
    out["typeahead_warm_p50"] = _p50(warm)

    # --- 4. typeahead cold (first touch, bare token, cache-hits discarded) -
    cold: list[dict] = []
    discarded: list[dict] = []
    terms = TERM_SETS[term_set]
    out["term_set"] = term_set
    # `debug_timing=1` suppresses the trending vote (see the module docstring's
    # contamination section). It is the default because 0 votes beats a budget.
    suffix = "" if voting_probes else "&debug_timing=1"
    out["voting_probes"] = voting_probes
    for term in terms[offset : offset + n_cold]:
        _, h, _ = _get(
            f"/api/events/typeahead?q={urllib.request.quote(term)}{suffix}"
        )
        ms = _server_ms(h)
        nq = _split_queries(h)
        out["requests_issued"] += 1
        if ms is None:
            continue
        sample = {"term": term, "ms": ms, "queries": nq}
        # `q=0` means the response came from the cache. It is not a cold build
        # and must not sit in a cold median. `q=None` means the header was
        # absent — also not gradeable, and also not silently kept.
        if nq is None or nq == 0:
            discarded.append(sample)
        else:
            cold.append(sample)
            if voting_probes:
                out["trending_votes_cast"] += 1
    out["typeahead_cold"] = cold
    out["typeahead_cold_discarded"] = discarded
    out["typeahead_cold_p50"] = _p50([c["ms"] for c in cold])

    return out


def report(snap: dict, prev: dict | None) -> int:
    def delta(now: float | None, key: str) -> str:
        if prev is None or now is None or prev.get(key) is None:
            return ""
        d = now - prev[key]
        return f"  (Δ {d:+,.1f} ms vs {prev['salt']})"

    print("# The latency charter's two numbers — LAT-P097 done-bar snapshot")
    print(f"slug        : {snap['commit']}  uptime {snap['uptime_seconds']}s  "
          f"warm={snap['warm_slug']}")
    print(f"run label   : {snap['salt']}")
    print()

    rows = [
        ("feed p50, warm", snap["feed_warm_p50"], FEED_WARM_BAR_MS, "feed_warm_p50"),
        ("typeahead p50, warm", snap["typeahead_warm_p50"], TYPEAHEAD_WARM_BAR_MS,
         "typeahead_warm_p50"),
        ("typeahead p50, FIRST TOUCH", snap["typeahead_cold_p50"],
         TYPEAHEAD_COLD_BAR_MS, "typeahead_cold_p50"),
    ]
    met = True
    print(f"{'number':30s} {'value':>12s} {'bar':>10s}  verdict")
    for label, val, bar, key in rows:
        if val is None:
            verdict, ok = "UNMEASURED", False
        else:
            ok = val <= bar
            verdict = "MET" if ok else "NOT MET"
        met = met and ok
        print(f"{label:30s} {_fmt(val):>12s} {_fmt(bar, 0):>10s}  {verdict}"
              f"{delta(val, key)}")

    fs = snap.get("feed_stats")
    print()
    print("## the standing target — feed miss share and cost (PRD: 37.5 % at ~4.1 s)")
    if not fs or not fs.get("miss_n"):
        print("   UNMEASURED — no `miss` bucket in the latency-stats window.")
        met = False
    else:
        share, p50 = fs["miss_share"], fs["miss_p50_ms"]
        share_ok = share is not None and share <= FEED_MISS_SHARE_BAR
        p50_ok = p50 is not None and p50 <= FEED_MISS_P50_BAR_MS
        met = met and share_ok and p50_ok
        print(f"   window       : {fs['window']}, spanning {_fmt(fs['span_s'], 0)} s, "
              f"n={fs['n']}  buckets={fs['buckets']}")
        print(f"   miss share   : {share:.1%} (n={fs['miss_n']})  bar ≤ "
              f"{FEED_MISS_SHARE_BAR:.1%}  {'MET' if share_ok else 'NOT MET'}")
        print(f"   miss p50     : {_fmt(p50)} ms  (max {_fmt(fs['miss_max_ms'])} ms)  "
              f"bar ≤ {_fmt(FEED_MISS_P50_BAR_MS, 0)} ms  "
              f"{'MET' if p50_ok else 'NOT MET'}")
        if (fs["n"] or 0) < 20:
            print("   ⚠️  n < 20 — this window cannot carry a p95 and its p50 is a "
                  "small-sample median. Report it as such; do not call a move a trend.")

    print()
    if snap.get("typeahead_cold"):
        print(f"## first-touch detail — term set `{snap.get('term_set')}` "
          "(graded samples: x-timing-split q > 0)")
        for c in sorted(snap["typeahead_cold"], key=lambda c: c["ms"]):
            print(f"   {c['term']:22s} {c['ms']:>9,.1f} ms   q={c['queries']}")
    for c in snap.get("typeahead_cold_discarded") or []:
        print(f"   DISCARDED (cache hit, not a cold build): {c['term']} "
              f"{c['ms']:,.1f} ms q={c['queries']}")

    if (
        snap.get("term_set") == "p095"
        and snap.get("typeahead_cold_p50") is not None
        and snap.get("voting_probes")
    ):
        d = snap["typeahead_cold_p50"] - P095_BASELINE_COLD_P50_MS
        print()
        print(f"## delta vs the published baseline (LAT-P095, same term set, "
              f"same voting mode): "
              f"{d:+,.1f} ms  ({snap['typeahead_cold_p50']:,.1f} vs "
              f"{P095_BASELINE_COLD_P50_MS:,.1f})")

    elif snap.get("term_set") == "p095" and not snap.get("voting_probes"):
        print()
        print("## delta vs the published baseline: WITHHELD — this run is in "
              "debug (non-voting) mode and LAT-P095's 3,816 ms is a true first "
              "touch. The two series are 2.2x apart and must not be subtracted.")

    print()
    print(f"## VERDICT: THE DONE BAR IS {'MET' if met else 'NOT MET'}")
    print()
    mode = ("TRUE FIRST TOUCH (voting)" if snap.get("voting_probes")
            else "cold build via debug_timing — NON-VOTING, and reads ~2.2x LOW "
            "vs a true first touch. Not comparable to a voting-mode series.")
    print(f"Cold-probe mode: {mode}")
    print(f"Contamination declared: {snap['requests_issued']} requests issued by this "
          f"run, of which {snap['trending_votes_cast']} were cold `/typeahead` misses "
          "that each cast one vote into `search:trending:24h` (#1916's head source). "
          "The feed miss share above was READ from latency-stats, not generated — but "
          f"the {len(snap.get('feed_warm_ms') or [])} `/api/feed` requests this run "
          "made are warm hits and are inside that window's denominator.")
    return 0 if met else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", required=True, help="run label; salts the cold terms")
    ap.add_argument("--n-feed", type=int, default=6)
    ap.add_argument("--n-warm", type=int, default=6)
    ap.add_argument("--n-cold", type=int, default=8)
    ap.add_argument("--voting-probes", action="store_true",
                    help="measure the TRUE first touch instead of the cold "
                         "build — costs one trending vote per probe; read the "
                         "module docstring before using it")
    ap.add_argument("--term-set", choices=sorted(TERM_SETS), default="p095",
                    help="p095 = the continuity set the program has published "
                         "against; obscure = lower head contamination")
    ap.add_argument("--term-offset", type=int, default=0,
                    help="slice the term set from here, so a re-run does not "
                         "re-measure a term the previous run just warmed")
    ap.add_argument("--out", help="write the raw snapshot JSON here")
    ap.add_argument("--prev", help="a previous snapshot JSON, for deltas")
    args = ap.parse_args()

    if not os.environ.get("BAINLUCK_API") or not os.environ.get("ADMIN_TOKEN"):
        print("source ~/.claude/.env first", file=sys.stderr)
        return 2

    snap = measure(args.n_feed, args.n_warm, args.n_cold, args.label,
                   args.term_offset, args.term_set, args.voting_probes)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(snap, fh, indent=2)
    prev = None
    if args.prev:
        with open(args.prev) as fh:
            prev = json.load(fh)
    return report(snap, prev)


if __name__ == "__main__":
    raise SystemExit(main())
