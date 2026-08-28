#!/usr/bin/env python3
"""The four cold paths a user actually walks — LAT-P099.

WHY THIS SCRIPT EXISTS, AND WHAT IT REPLACES AS THE HEADLINE.
`done_bar_snapshot.py` reports the charter's two numbers, `feed p50` and
`typeahead p50`, and it reports them WARM-FIRST because that is how the charter
was written (`docs/PRD.md`, Alex 2026-08-24). Alex's 2026-08-26 ruling retires
that framing:

    "stop bragging about warm searches — a tiny fraction of searches will be
     warm. What matters most: Discover load time, the load time of the other
     tabs, and COLD search load. That's what a user experiences in volume."

So the headline moves from *the best case the cache can produce* to *the case a
person opening the app actually gets*. A warm number is supporting evidence and
never leads. `done_bar_snapshot.py` is NOT deleted — its warm series is the
continuity record, and a series is only worth anything if nobody re-baselines it
mid-flight — but it stops being the headline instrument.

WHAT A "FIRST LOAD" IS, DEFINED ONCE, HERE, BEFORE ANY NUMBER IS TAKEN.

A first load is *the request a tab issues when a person opens it on an install
the server has never served*. Three properties, each of which the warm headline
violated:

1. **A FRESH PRINCIPAL PER SAMPLE.** The native client mints one persistent
   `x-session-id` per install (`APIClient.swift:162`, sent at :278/:339/:403)
   and the feed cache key is per-principal (`feed_cache.feed_response_cache_key`
   -> `u:<id>` / `s:<uuid>` / `anon`). A prober that reuses one session id
   measures its own second request. Every sample here mints a new UUID, which is
   *exactly* the shape of a new install's first open — not a synthetic
   cache-buster, and not something a real user never does.

   🔴 AND IT IS NOT A CACHE POISON, WHICH IS WHY IT IS SAFE TO REPEAT. The
   LAT-P089 inert-principal share (`routes/feed.py:2224`) lets a fresh session
   READ the anonymous entry, and it deliberately republishes only to the
   PRIVATE key ("the shared entry is the warmer's to publish"). So a fresh
   session sample can hit what the warmer left, can never extend it, and can
   never make the next sample look faster than a real user's.

2. **THE CACHE STATE IS READ, NEVER ASSUMED.** `X-Feed-Cache` carries the exact
   status the route took (`hit` / `stale_hit` / `shared_hit` /
   `shared_stale_hit` / `miss` / `coalesced` / `last_good` / ...). It is
   recorded on every sample and the split is printed under every p50, because
   ruling 127 already established the general form: *a p50 over mixed cache
   states is a statement about the hit rate, not about latency.*

   The difference from `done_bar_snapshot.py` is the direction of the
   discipline. That script DISCARDS warm samples to protect a cold median. This
   one KEEPS them, because the user-volume question is "what does opening this
   tab cost", and a tab that is warm 90 % of the time genuinely is fast 90 % of
   the time. Both numbers are printed: `p50_all` is the headline, `p50_cold` is
   the cost of the bad half, and neither is allowed to stand alone.

3. **SERVER TIME, NOT WALL TIME.** This sandbox's transport floor to Heroku is
   ~246 ms p50 against tab loads that can be 20 ms. Wall time from here reports
   the egress proxy. `x-response-time` is the API's own measurement; wall is
   recorded beside it only so the floor stays visible.

WHAT IS MEASURED, AND WHERE EACH SHAPE COMES FROM. Every request below is a
constant read out of a client, cited to file:line, never a shape this script
invented. The native tab bar is `Views/MainTabView.swift:19-52` — Discover,
Sports, Browse, Search, My Stuff — and it is the surface Alex's wording names.
(Note it is FIVE tabs. The directive says "Sports/Browse/My Stuff"; Search is
the fifth and is measured here as the "cold search" half of the same ruling.)

🔴 A TAB IS A REQUEST SET, NOT A REQUEST, AND ONLY ONE MEMBER GATES THE PAINT.
The Sports tab issues three requests and My Stuff two. Reporting their sum would
overstate what a person waits for; reporting only the main one would hide a
sibling that can hang. So each request carries a `blocking` flag taken from the
client's own control flow, the HEADLINE is the blocking member, and the whole
set is printed beneath it.

  Discover  BLOCKING  /api/feed?limit=50&offset=0&event_pct=0.15  (native)
                      /api/feed?limit=20&offset=0&event_pct=0.15  (web)
            after     /api/predictions/resolutions  — uncached, live DB
  Sports    BLOCKING  /api/feed?limit=50&offset=0&mode=sports     (native)
                      /api/feed?limit=20&offset=0&mode=sports     (web)
            sibling   /api/feed?limit=200&offset=0&include_futures=false
            sibling   /api/futures/grouped-feed?limit=20 — no server cache
  Search    BLOCKING  /api/events/search/trending
            typed     /api/events/typeahead?q=  ·  /api/events/search?q=
  My Stuff  BLOCKING  /api/predictions/stats — fires even SIGNED OUT, uncached
            auth-only /api/feed?...&my_teams_only=true&include_futures=false
  Browse    NOTHING

  Browse issues ZERO network requests on appear — `Views/LeaguesView.swift:55-78`
  renders static league/category arrays and calls only
  `AnalyticsService.trackScreen`; the web "Browse" is a link dropdown with no
  route of its own (`components/BottomNav.tsx:56`). The network call in
  `LeagueGridViewModel` belongs to a DRILLED-IN league page, not to the Browse
  index. This is asserted from source and pinned by a test, not probed: you
  cannot measure the latency of a request that is never issued, and printing
  "0 ms" as though it were a measurement would be this program's own favourite
  mistake for the fourth time.

🔴 MY STUFF'S AUTHENTICATED FEED CANNOT BE MEASURED FROM HERE, AND THE SCRIPT
SAYS SO RATHER THAN SUBSTITUTING A NUMBER. `my_teams_only=true` without a user
returns an empty `requires_auth` body and sets no cache header at all
(`routes/feed.py:2049-2069`) — so an anonymous probe of it is not a floor, it is
a different code path that exits before the work starts. It is still issued, and
recorded as `requires_auth`, precisely so that a later reader can see it was
checked rather than assumed. This sandbox holds `ADMIN_TOKEN`, an admin secret,
not a user session JWT, and there is no read-only way to mint one.

What IS known about that path is structural and gets printed instead of a fake
number: the key is `u:<id>`, the TTL is 30 s
(`FEED_RESPONSE_TTL_MY_TEAMS_SECONDS`), and NOTHING pre-warms it —
`FEED_PREWARM_SHAPES` has no my-teams entry and could not have one, because the
content depends on which teams that person follows. What a signed-out person
actually waits for on that tab IS measurable and IS measured:
`/api/predictions/stats`, which fires unconditionally and has no server cache.

INTERLEAVING, and why it is not decoration. Paths are sampled round-robin, not
path-by-path. A dyno restart, a heavy Celery beat or a slow database minute
lands on whichever path happens to be running, and a block-sequential run
attributes the whole transient to one tab. Round-robin spreads it across all of
them, which does not remove the noise but stops it from being mistaken for a
finding about one surface.

CONTAMINATION, declared by the script itself rather than argued in prose:

  * `/api/feed` is in `LATENCY_ALWAYS_SAMPLE`, so every request this script
    makes lands in the `latency-stats` window a later reader might quote as
    organic. The script prints its own `/api/feed` count so it can be
    subtracted. **Take the organic `latency-stats` read BEFORE running this**
    (ruling 127's protocol) — `--stats-before` records that you did.
  * `/api/events/search` writes `search_query_logs`, the table #1916 exists to
    clean. Off by default; `--with-search` opts in and the count is declared.
  * `/api/events/typeahead` votes into `search:trending:24h` on a cache miss and
    a single-digit vote can buy a slot in the warmer's 40-slot head (LAT-P097's
    contamination finding, in full in `done_bar_snapshot.py`'s docstring). This
    script therefore uses `?debug_timing=1`, which sets `_suppress_trending_write`
    -> zero votes. That flag also bypasses the response cache, so the typeahead
    number here is a COLD BUILD and reads ~2.2x low against a true first touch.
    It is labelled as such and is NOT comparable to the voting-mode series.

Exit codes (gotcha #54 — read the VALUE): 0 = every pre-registered bar measured
and MET. 1 = measured and NOT MET. Anything else is the harness failing.
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
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ONE term list for the whole program. A delta against a different term set is
# not a delta (done_bar_snapshot.py's own note), so the sets are imported rather
# than re-typed — a copy would drift on its first edit and nobody would see it.
from done_bar_snapshot import TERM_SETS  # noqa: E402

# --------------------------------------------------------------------------
# THE BARS. Pre-registered in `docs/audits/latency/lat-p099-cold-path-charter.md`
# and frozen there BEFORE the first number was taken. Inherited, not invented —
# each one is cited to something that already existed.
# --------------------------------------------------------------------------

#: Every tab's first load, server-side. INHERITED from the charter's existing
#: feed-miss bar (`FEED_MISS_P50_BAR_MS = 1000` in `done_bar_snapshot.py`, which
#: reads it off `docs/PRD.md`'s "37.5 % of loads miss at ~4.1s"). Same surface,
#: same unit, so a tab does not get a softer bar than the feed already had.
#: It also lands on the classic flow threshold (~1 s is where a wait stops
#: feeling like a response and starts feeling like a load), which is why 1,000
#: was a defensible number for the feed in the first place.
TAB_FIRST_LOAD_BAR_MS = 1000.0

#: Cold `/api/events/search`. Same bar, same reasoning: a search result page is
#: a page load, not a keystroke.
SEARCH_COLD_BAR_MS = 1000.0

#: Cold `/api/events/typeahead`. UNCHANGED from the charter — this is the
#: keystroke path and 500 ms is where a suggestion list stops feeling like it is
#: responding to typing. Kept identical so the one number this program has
#: published a series for keeps its bar.
TYPEAHEAD_COLD_BAR_MS = 500.0

#: A HARD CEILING, separate from the p50 bars and graded per-sample.
#: `DiscoverViewModel.retryBudget = 6` (`DiscoverViewModel.swift:216`) is a
#: non-retryable client deadline: past it the native client gives up and paints
#: whatever it has on disk. A single sample over this is a user-visible failure
#: even if the median is fine, so it is graded on the MAX and not averaged away.
CLIENT_DEADLINE_MS = 6000.0


class ColdPath:
    """One request a tab issues on first appear, with its client constant."""

    def __init__(
        self,
        key: str,
        tab: str,
        surface: str,
        path: str,
        provenance: str,
        *,
        blocking: bool = True,
        principal: str = "fresh_session",
        barred: bool = True,
        note: str = "",
    ) -> None:
        self.key = key
        self.tab = tab
        self.surface = surface
        self.path = path
        self.provenance = provenance
        #: True when the client's own control flow holds first paint on this
        #: response. Only blocking requests carry the tab's headline.
        self.blocking = blocking
        #: "fresh_session" mints a new x-session-id per sample (a new install);
        #: "anon" sends none (the L2-242 shared-anon contract the web uses).
        self.principal = principal
        #: Measured but does NOT vote on the verdict.
        self.barred = barred
        self.note = note


PATHS: tuple[ColdPath, ...] = (
    # ---- Discover ------------------------------------------------------
    ColdPath(
        "discover_native",
        "Discover",
        "native",
        "/api/feed?limit=50&offset=0&event_pct=0.15",
        "DiscoverView.task:1216 -> DiscoverViewModel -> "
        "fetchFeedPersistingLastGood (DiscoverViewModel.swift:1063); limit "
        "default 50 at APIClient.swift:606",
    ),
    ColdPath(
        "discover_web",
        "Discover",
        "web",
        "/api/feed?limit=20&offset=0&event_pct=0.15",
        "frontend/app/discover/page.tsx:641 initialFeedRequest(), "
        "FEED_PAGE_LIMIT=20",
        principal="anon",
    ),
    ColdPath(
        "discover_resolutions",
        "Discover",
        "both",
        "/api/predictions/resolutions",
        "DiscoverView.swift:1220 / app/discover/page.tsx:650 — no server cache",
        blocking=False,
        principal="anon",
    ),
    # ---- Sports --------------------------------------------------------
    ColdPath(
        "sports_native",
        "Sports",
        "native",
        "/api/feed?limit=50&offset=0&mode=sports",
        "FeedViewModel.fetchSportsFeed -> fetchFeed(mode:) "
        "(FeedViewModel.swift:499); gates first paint at :212",
    ),
    ColdPath(
        "sports_web",
        "Sports",
        "web",
        "/api/feed?limit=20&offset=0&mode=sports",
        "frontend/app/sports/page.tsx:92 initialFeedRequest()",
        principal="anon",
    ),
    ColdPath(
        "sports_event_backfill",
        "Sports",
        "native",
        "/api/feed?limit=200&offset=0&include_futures=false",
        "FeedViewModel.swift:284 + :507, supplementalEventLimit=200, "
        "10 s sibling deadline at :114",
        blocking=False,
    ),
    ColdPath(
        "sports_grouped",
        "Sports",
        "both",
        "/api/futures/grouped-feed?limit=20&offset=0",
        "FeedViewModel.swift:290 + :511 — no server cache found",
        blocking=False,
        principal="anon",
    ),
    # ---- My Stuff ------------------------------------------------------
    ColdPath(
        "my_stuff_stats",
        "My Stuff",
        "native",
        "/api/predictions/stats",
        "MyStuffView.task:60 — fires even when SIGNED OUT; no server cache",
        principal="anon",
    ),
    ColdPath(
        "my_stuff_feed_requires_auth",
        "My Stuff",
        "native",
        "/api/feed?limit=50&offset=0&my_teams_only=true&include_futures=false",
        "MyStuffViewModel.swift:448 — authenticated branch only",
        # Not blocking for the principal this sandbox can BE. It gates first
        # paint for a signed-in user, and that user's wait is the one number
        # this instrument cannot reach — see `note`.
        blocking=False,
        barred=False,
        note="NOT A MEASUREMENT OF THE REAL PATH. Anonymous callers get an "
        "empty `requires_auth` body with no cache header "
        "(routes/feed.py:2049-2069) — a different code path that exits before "
        "the work starts. Issued so a reader can see it was checked. The real "
        "path is keyed u:<id>, TTL 30 s, and is not pre-warmable.",
    ),
    # ---- Search --------------------------------------------------------
    ColdPath(
        "search_trending",
        "Search",
        "native",
        "/api/events/search/trending",
        "SearchView.task:156 -> SearchViewModel.loadTrending:40",
        principal="anon",
    ),
)

#: Ordered for the report. Browse is present and deliberately empty.
TABS: tuple[str, ...] = ("Discover", "Sports", "Browse", "Search", "My Stuff")


def _get(
    path: str,
    *,
    session_id: str | None = None,
    token: str | None = None,
    timeout: int = 60,
) -> dict:
    """One GET. Returns a sample dict; never raises on an HTTP error."""
    api = os.environ["BAINLUCK_API"]
    headers: dict[str, str] = {}
    if session_id:
        headers["x-session-id"] = session_id
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{api}{path}", headers=headers)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            h, status = dict(resp.headers), resp.status
    except urllib.error.HTTPError as exc:
        body, h, status = b"", dict(exc.headers or {}), exc.code
    except Exception as exc:  # transport failure is a fact, not a fast request
        return {
            "path": path,
            "http": None,
            "error": f"{type(exc).__name__}: {exc}",
            "wall_ms": (time.monotonic() - t0) * 1000,
        }
    return {
        "path": path,
        "http": status,
        "bytes": len(body),
        "wall_ms": (time.monotonic() - t0) * 1000,
        "server_ms": _server_ms(h),
        "feed_cache": _hdr(h, "x-feed-cache"),
        "feed_elapsed_ms": _float(_hdr(h, "x-feed-elapsed-ms")),
        "singleflight": _hdr(h, "x-feed-singleflight"),
        "counts": _hdr(h, "x-feed-counts"),
        "stages": _hdr(h, "x-feed-stages"),
        "timing_split": _hdr(h, "x-timing-split"),
        "queries": _split_queries(h),
    }


def _hdr(headers: dict, name: str) -> str | None:
    for k, v in headers.items():
        if k.lower() == name:
            return v
    return None


def _float(raw: str | None) -> float | None:
    try:
        return float(raw) if raw is not None else None
    except ValueError:
        return None


def _server_ms(headers: dict) -> float | None:
    """`x-response-time`, in ms. None means the middleware did not run — which
    is a different fact from a fast request and is never coerced to a number."""
    raw = _hdr(headers, "x-response-time")
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
    raw = _hdr(headers, "x-timing-split")
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


#: Cache statuses that mean the caller paid for a build. Everything else means
#: something warm answered. Listed explicitly rather than as "not hit", so a new
#: status the route grows shows up as UNKNOWN instead of being silently counted
#: as cold (or silently counted as warm, which is worse).
COLD_STATUSES = frozenset(
    {
        "miss",
        "error",
        "coalesced",
        "unavailable",
        "disabled",
        "disabled_debug",
        "disabled_reviewed_filter",
    }
)
WARM_STATUSES = frozenset(
    {"hit", "stale_hit", "shared_hit", "shared_stale_hit", "last_good"}
)


#: A sample the SERVER refused. Not a latency observation at all, and kept out
#: of the cold/warm vocabulary rather than folded into "unknown" so the report
#: can say WHY nothing was measured.
REJECTED = "rejected"


def _classify(sample: dict) -> str:
    """rejected / cold / warm / unknown.

    🔴 THE STATUS CODE IS CHECKED FIRST, AND THAT IS THE WHOLE POINT OF THIS
    FUNCTION'S FIRST BRANCH. LAT-P110, #2260.

    It used to read `X-Feed-Cache`, fall back to the query count, and never look
    at `http` at all. A **429** carries no cache header, executes zero queries
    and answers in 2–3 ms with a real `x-response-time` — so it reached
    `return "cold" if q > 0 else "warm"` and was graded as a **warm 2 ms
    search**. The API limit is 60/minute per IP and a canonical needle run
    issues ~68 requests with the six cold searches LAST, so the searches are
    exactly what gets rejected — and a latency lane throttles its own harness
    simply by doing its own `db-query` work from the same IP.

    That produced a finding, not just a wrong cell. LAT-P109 parked P109-6 —
    "the needle's cold-search member went 6/6 WARM … cause NOT established" —
    and three consecutive needle refusals were read as "the pool went warm"
    when for that member the truth was "the pool went UNMEASURABLE". Those are
    different facts with different owners. Audited across every needle artifact
    on disk: the published series (882 / 873 / 940 / 1273) is clean — every run
    that produced a number did so on real 200s — but the refusals since were
    partly mis-diagnosed.

    A rejected sample keeps its timing fields, because the 2 ms IS what the
    rate limiter took and throwing it away would hide the throttle as
    thoroughly as mis-grading it did. It is excluded from `graded` instead, and
    counted out loud (`_summarize`).
    """
    if sample.get("error") is not None:
        return REJECTED
    http = sample.get("http")
    if http is not None and http != 200:
        return REJECTED
    status = (sample.get("feed_cache") or "").strip().lower()
    if status in COLD_STATUSES:
        return "cold"
    if status in WARM_STATUSES:
        return "warm"
    if not status:
        # No X-Feed-Cache at all: a non-feed endpoint. Fall back to the query
        # count, which is the same discriminator done_bar_snapshot.py uses.
        q = sample.get("queries")
        if q is None:
            return "unknown"
        return "cold" if q > 0 else "warm"
    return "unknown"


def rejection_counts(rows: list[dict]) -> dict[str, int]:
    """`{"429": 6}` — what the server said, for the samples it refused.

    Named and exported because the needle prints it: a member that produced no
    cold sample because it was THROTTLED is a different finding from one that
    produced none because it was warm, and a run that cannot tell them apart
    files the wrong parked measurement (it did, twice).
    """
    out: dict[str, int] = {}
    for r in rows:
        if r.get("class") != REJECTED:
            continue
        key = r.get("error") or str(r.get("http"))
        out[key] = out.get(key, 0) + 1
    return out


def _p50(vals: list[float]) -> float | None:
    return statistics.median(vals) if vals else None


def _fmt(v: float | None, nd: int = 1) -> str:
    return "—" if v is None else f"{v:,.{nd}f}"


def measure(
    n: int,
    label: str,
    term_set: str,
    n_search: int,
    with_search: bool,
    stats_before: str | None,
) -> dict:
    out: dict = {
        "label": label,
        "schema": "lat-p099-cold-path/1",
        "requests": {
            "feed": 0,
            "trending": 0,
            "typeahead": 0,
            "search": 0,
            "health": 0,
        },
        "term_set": term_set,
    }

    api = os.environ["BAINLUCK_API"]
    with urllib.request.urlopen(f"{api}/api/health", timeout=30) as resp:
        health = json.loads(resp.read())
    out["requests"]["health"] += 1
    out["commit"] = health.get("commit")
    out["uptime_seconds"] = health.get("uptime_seconds")
    # A slug younger than 5 minutes reads as a regression that is really a cold
    # process (gotcha: post-deploy latency is not evidence). Recorded, not
    # silently tolerated.
    out["warm_slug"] = (health.get("uptime_seconds") or 0) > 300

    # The transport floor, so nobody reads a wall number as a server number.
    floor = []
    for _ in range(3):
        s = _get("/api/health")
        out["requests"]["health"] += 1
        if s.get("wall_ms"):
            floor.append(s["wall_ms"])
    out["transport_floor_wall_p50_ms"] = _p50(floor)

    out["stats_before"] = stats_before

    # --- the tab first loads, ROUND-ROBIN so a transient cannot be read as
    # --- a finding about whichever tab happened to be running -------------
    samples: dict[str, list[dict]] = {p.key: [] for p in PATHS}
    for i in range(n):
        for p in PATHS:
            sid = str(uuid.uuid4()) if p.principal == "fresh_session" else None
            s = _get(p.path, session_id=sid)
            bucket = "feed" if p.path.startswith("/api/feed") else "other"
            out["requests"][bucket] = out["requests"].get(bucket, 0) + 1
            s["round"] = i
            s["principal"] = p.principal
            s["class"] = _classify(s)
            samples[p.key].append(s)
    out["tab_samples"] = samples

    # --- cold typeahead: debug mode, ZERO trending votes -------------------
    terms = TERM_SETS[term_set]
    ta: list[dict] = []
    for term in terms[:n_search]:
        q = urllib.parse.quote(term)
        s = _get(f"/api/events/typeahead?q={q}&debug_timing=1")
        out["requests"]["typeahead"] += 1
        s["term"] = term
        s["class"] = _classify(s)
        ta.append(s)
    out["typeahead_cold_samples"] = ta

    # --- cold search: OPT-IN, because it writes search_query_logs ----------
    se: list[dict] = []
    if with_search:
        for term in terms[:n_search]:
            q = urllib.parse.quote(term)
            s = _get(f"/api/events/search?q={q}")
            out["requests"]["search"] += 1
            s["term"] = term
            s["class"] = _classify(s)
            se.append(s)
    out["search_cold_samples"] = se
    out["with_search"] = with_search

    return out


def _summarize(rows: list[dict]) -> dict:
    # `class != REJECTED` as well as "has a server_ms": a 429 HAS an
    # `x-response-time`, so the timing test alone let the rate limiter into
    # every median below. #2260.
    graded = [
        r for r in rows if r.get("server_ms") is not None and r.get("class") != REJECTED
    ]
    allv = [r["server_ms"] for r in graded]
    cold = [r["server_ms"] for r in graded if r["class"] == "cold"]
    warm = [r["server_ms"] for r in graded if r["class"] == "warm"]
    statuses: dict[str, int] = {}
    for r in rows:
        key = r.get("feed_cache") or (
            f"q={r.get('queries')}" if r.get("queries") is not None else "—"
        )
        statuses[key] = statuses.get(key, 0) + 1
    return {
        "n": len(rows),
        "n_graded": len(graded),
        "n_rejected": sum(1 for r in rows if r.get("class") == REJECTED),
        "rejections": rejection_counts(rows),
        "p50_all": _p50(allv),
        "max_all": max(allv) if allv else None,
        "n_cold": len(cold),
        "p50_cold": _p50(cold),
        "n_warm": len(warm),
        "p50_warm": _p50(warm),
        "cold_share": (len(cold) / len(graded)) if graded else None,
        "statuses": statuses,
        "errors": [
            r for r in rows if r.get("error") or (r.get("http") not in (200, None))
        ],
    }


def report(snap: dict) -> int:
    print("# LAT-P099 — the cold paths a user walks")
    print(
        f"slug   : {snap['commit']}  uptime {snap['uptime_seconds']}s  "
        f"warm_slug={snap['warm_slug']}"
    )
    print(f"run    : {snap['label']}   term set `{snap['term_set']}`")
    print(
        f"floor  : sandbox transport wall p50 "
        f"{_fmt(snap['transport_floor_wall_p50_ms'])} ms — every number below "
        f"is SERVER time (`x-response-time`), not wall."
    )
    if not snap["warm_slug"]:
        print(
            "⚠️  SLUG IS YOUNGER THAN 5 MINUTES. A cold process reads as a "
            "regression. Re-run."
        )
    print()

    met = True
    hard_fail: list[str] = []
    verdicts: dict[str, dict] = {}
    for p in PATHS:
        verdicts[p.key] = _summarize(snap["tab_samples"][p.key])

    print(
        "## THE HEADLINE — what gates first paint on each tab, server-side, "
        "over the real cache mix"
    )
    print(
        f"{'tab':10s} {'surface':8s} {'n':>3s} {'p50 all':>9s} "
        f"{'p50 cold':>9s} {'cold%':>6s} {'max':>9s}  bar      verdict"
    )
    for tab in TABS:
        blocking = [p for p in PATHS if p.tab == tab and p.blocking]
        if not blocking:
            print(
                f"{tab:10s} {'—':8s} {'—':>3s} {'0':>9s} {'0':>9s} "
                f"{'—':>6s} {'0':>9s}  {'n/a':<8s} NO SERVER DEPENDENCY"
            )
            continue
        for p in blocking:
            s = verdicts[p.key]
            if s["p50_all"] is None:
                verdict, ok = "UNMEASURED", False
            else:
                ok = s["p50_all"] <= TAB_FIRST_LOAD_BAR_MS
                verdict = "MET" if ok else "NOT MET"
            if p.barred:
                met = met and ok
            else:
                verdict += " (ungraded)"
            share = "—" if s["cold_share"] is None else f"{s['cold_share']:.0%}"
            print(
                f"{tab:10s} {p.surface:8s} {s['n']:>3d} "
                f"{_fmt(s['p50_all']):>9s} {_fmt(s['p50_cold']):>9s} "
                f"{share:>6s} {_fmt(s['max_all']):>9s}  "
                f"{TAB_FIRST_LOAD_BAR_MS:<8.0f} {verdict}"
            )
            if (
                p.barred
                and s["max_all"] is not None
                and s["max_all"] > CLIENT_DEADLINE_MS
            ):
                hard_fail.append(
                    f"{tab} ({p.surface}): max {s['max_all']:,.1f} ms exceeds "
                    f"the native client's non-retryable "
                    f"{CLIENT_DEADLINE_MS:,.0f} ms budget"
                )
    print(
        "   Browse: ZERO network requests on appear "
        "(Views/LeaguesView.swift:55-78 renders static arrays and calls only "
        "AnalyticsService.trackScreen; the web Browse is a link dropdown "
        "with no route). Asserted from source and pinned by a test — a "
        "request that is never issued has no latency to measure."
    )

    print()
    print("## the rest of each tab's request set — not gating, still paid")
    for tab in TABS:
        rest = [p for p in PATHS if p.tab == tab and not p.blocking]
        for p in rest:
            s = verdicts[p.key]
            print(
                f"   {tab:10s} {p.path:58s} n={s['n']:<3d} "
                f"p50 {_fmt(s['p50_all']):>9s}  max {_fmt(s['max_all']):>9s}"
            )

    print()
    print(
        "## cache-state split — the p50 above is a statement about THIS as "
        "much as about latency"
    )
    for p in PATHS:
        s = verdicts[p.key]
        print(f"   {p.tab:10s} {p.surface:8s} {p.key:30s} {s['statuses']}")

    for p in PATHS:
        if p.note:
            print()
            print(f"   ⚠️  {p.tab} — {p.key}: {p.note}")

    print()
    print("## the Search tab, typed")
    ta = _summarize(snap["typeahead_cold_samples"])
    ta_ok = ta["p50_all"] is not None and ta["p50_all"] <= TYPEAHEAD_COLD_BAR_MS
    met = met and ta_ok
    print(
        f"   typeahead COLD BUILD (debug_timing, non-voting): n={ta['n']} "
        f"p50 {_fmt(ta['p50_all'])} ms  bar {TYPEAHEAD_COLD_BAR_MS:.0f}  "
        f"{'MET' if ta_ok else 'NOT MET'}"
    )
    print(
        "      ⚠️  debug mode reads ~2.2x LOW vs a true first touch "
        "(measured, LAT-P097). Not comparable to the voting-mode series."
    )
    for r in sorted(
        snap["typeahead_cold_samples"], key=lambda r: r.get("server_ms") or 0
    ):
        print(
            f"      {r['term']:20s} {_fmt(r.get('server_ms')):>9s} ms  "
            f"q={r.get('queries')}"
        )

    if snap["with_search"]:
        se = _summarize(snap["search_cold_samples"])
        se_ok = se["p50_all"] is not None and se["p50_all"] <= SEARCH_COLD_BAR_MS
        met = met and se_ok
        print(
            f"   search COLD /api/events/search: n={se['n']} "
            f"p50 {_fmt(se['p50_all'])} ms  max {_fmt(se['max_all'])} ms  "
            f"bar {SEARCH_COLD_BAR_MS:.0f}  {'MET' if se_ok else 'NOT MET'}"
        )
        for r in sorted(
            snap["search_cold_samples"], key=lambda r: r.get("server_ms") or 0
        ):
            print(
                f"      {r['term']:20s} {_fmt(r.get('server_ms')):>9s} ms  "
                f"q={r.get('queries')}"
            )
        if se["max_all"] is not None and se["max_all"] > CLIENT_DEADLINE_MS:
            hard_fail.append(
                f"cold search: max {se['max_all']:,.1f} ms exceeds the "
                f"{CLIENT_DEADLINE_MS:,.0f} ms client budget"
            )
    else:
        print(
            "   search COLD: NOT RUN (--with-search opts in; it writes "
            "search_query_logs, the table #1916 exists to clean)"
        )
        met = False

    if hard_fail:
        print()
        print("## 🔴 HARD CEILING BREACHED — the native client gives up here")
        for h in hard_fail:
            print(f"   {h}")
        met = False

    print()
    print(f"## VERDICT: THE COLD-PATH BAR IS {'MET' if met else 'NOT MET'}")
    print()
    r = snap["requests"]
    print("## contamination declared by this run")
    print(
        f"   /api/feed              {r.get('feed', 0):>4d} requests — ALL of them "
        "land in the always-sampled `latency-stats` window. Subtract them "
        "before quoting that window as organic."
    )
    print(
        f"   other tab endpoints    {r.get('other', 0):>4d} — trending / "
        "grouped-feed / predictions, all read-only"
    )
    print(
        f"   /api/events/typeahead  {r['typeahead']:>4d} — debug_timing, "
        "0 votes into search:trending:24h"
    )
    print(
        f"   /api/events/search     {r['search']:>4d} — each writes one "
        "search_query_logs row (#1916)"
    )
    print(f"   /api/health            {r['health']:>4d}")
    if snap.get("stats_before"):
        print(
            f"   organic latency-stats read taken BEFORE this run: "
            f"{snap['stats_before']}"
        )
    else:
        print(
            "   ⚠️  no --stats-before recorded. Ruling 127 requires the "
            "organic feed census to be read FIRST; without it this run's "
            "own feed requests are inside any window later quoted."
        )
    return 0 if met else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", required=True)
    ap.add_argument(
        "--n",
        type=int,
        default=3,
        help="rounds per tab path (round-robin, not blocked)",
    )
    ap.add_argument("--n-search", type=int, default=6)
    ap.add_argument("--term-set", choices=sorted(TERM_SETS), default="obscure")
    ap.add_argument(
        "--with-search",
        action="store_true",
        help="also measure cold /api/events/search — writes "
        "search_query_logs (#1916)",
    )
    ap.add_argument(
        "--stats-before",
        help="path to the latency-stats JSON read BEFORE this run "
        "(ruling 127's organic-first protocol)",
    )
    ap.add_argument("--out")
    args = ap.parse_args()

    if not os.environ.get("BAINLUCK_API"):
        print("source ~/.claude/.env first", file=sys.stderr)
        return 2

    snap = measure(
        args.n,
        args.label,
        args.term_set,
        args.n_search,
        args.with_search,
        args.stats_before,
    )
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(snap, fh, indent=2)
    return report(snap)


if __name__ == "__main__":
    raise SystemExit(main())
