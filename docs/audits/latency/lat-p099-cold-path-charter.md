# LAT-P099 — the cold-path charter, PRE-REGISTERED

**Cycle:** LAT-P099 · **Date:** 2026-08-27 · **Identity:** `LAT-P099-20260827`
**Directive:** Alex 2026-08-26, authored in Alex's Fable session and delivered through the lane
runner Alex launched under his standing authorization.
**Ship this serves:** a person opening the app — any tab of it — sees content instead of a
spinner, the first time, without having been lucky enough to arrive while a cache was warm.

**Status of this file: FROZEN BEFORE MEASUREMENT.** It is committed before the first number is
taken, and the bars in it are not editable by the cycle that then fails them. That is the whole
point: the program has twice been saved by a bar it could not move afterwards (LAT-P096's
red-first gate, ruling 136's blast window) and once been embarrassed by a methodology change that
manufactured a 2.2× win (LAT-P097's salt).

---

## 0. The ruling this implements

> "stop bragging about warm searches — a tiny fraction of searches will be warm. What matters
> most: Discover load time, the load time of the other tabs, and COLD search load. That's what a
> user experiences in volume."
> — Alex, 2026-08-26

The charter it amends is `docs/PRD.md`'s latency charter (Alex, 2026-08-24) and ruling 127, both
of which name **`feed p50` and `typeahead p50`** as the two numbers that open every report. Those
two numbers are warm-led. `feed p50` has been reported at 16–20 ms for three cycles while the
thing under it — the miss — cost 3.2–4.1 s. Every one of those reports was true and none of them
described what a person felt.

**What changes:** the headline. **What does not change:** the instrument discipline — ruling 127's
census-counts-the-observer protocol, the contamination declarations, the frozen term set, the
materiality floors, the falsifier panel. This amendment points the instruments at a different
number; it does not loosen any of them.

---

## 1. The new headline metric set

Every latency report from LAT-P099 onward opens with this table and nothing before it.

| # | metric | surface | what it is |
|---|---|---|---|
| 1 | **Discover first-load p50** | native + web | server time for the request that gates first paint |
| 2 | **Sports first-load p50** | native + web | same |
| 3 | **Browse first-load p50** | native + web | same |
| 4 | **My Stuff first-load p50** | native | same |
| 5 | **cold search p50** | `/api/events/search`, `/api/events/typeahead` | first touch, never-asked term |

Alex's directive names four cold paths and lists "Discover / the other tabs / cold search". The
native tab bar (`Views/MainTabView.swift:19-52`) has **five** tabs — Discover, Sports, Browse,
**Search**, My Stuff — so the four tab first-loads plus cold search is five rows, and Search is
both the fifth tab and the surface row 5 grades. Recorded here so nobody later reads a
five-row table as scope creep.

**Warm numbers are demoted, not deleted.** `feed p50 warm` and `typeahead p50 warm` keep being
measured by `done_bar_snapshot.py` and keep their series — a series is worthless if it is
re-baselined mid-flight — but they move below the fold and may never open a report or lead a
claim again. A warm win is supporting evidence for "we did not regress the good case".

---

## 2. What "first load" means, defined before it is measured

**A first load is the request a tab issues when a person opens it on an install the server has
never served.** Three properties:

1. **A fresh principal per sample.** The feed cache key is per-principal
   (`feed_cache.feed_response_cache_key` → `u:<id>` / `s:<uuid>` / `anon`) and the native client
   mints one persistent `x-session-id` per install (`APIClient.swift:162`). A prober that reuses
   a session id measures its own second request. Every sample mints a new UUID — which is exactly
   a new install's first open, not a synthetic cache-buster.

   It is also **not a cache poison**, which is what makes it repeatable: the LAT-P089
   inert-principal share (`routes/feed.py:2224`) lets a fresh session *read* the anonymous entry
   and deliberately republishes only to the private key. A fresh-session sample can hit what the
   warmer left and can never extend it.

2. **Cache state is read, never assumed.** `X-Feed-Cache` carries the route's own status. It is
   recorded per sample and the split is printed under every p50. Ruling 127's clause stands
   verbatim: *a p50 over mixed cache states is a statement about the hit rate.*

   **The discipline runs the opposite way from `done_bar_snapshot.py`, deliberately.** That
   script DISCARDS warm samples to protect a cold median. This one KEEPS them, because the
   user-volume question is "what does opening this tab cost", and a tab that is warm 90 % of the
   time genuinely is fast 90 % of the time. Both are printed — `p50_all` leads, `p50_cold` sits
   beside it — and neither may stand alone.

3. **Server time, not wall time.** The sandbox transport floor to Heroku is ~246 ms p50 against
   tab loads that can be 20 ms. `x-response-time` is the API's own number; wall is recorded only
   so the floor stays visible.

### A tab is a request SET, and only one member gates the paint

Sports issues three requests, My Stuff two, Discover two. Summing them overstates the wait;
reporting only the main one hides a sibling that can hang. So each request carries a `blocking`
flag **taken from the client's own control flow**, the headline is the blocking member, and the
full set is printed beneath it.

| tab | blocking | also issued on first appear |
|---|---|---|
| Discover | `/api/feed?limit=50&offset=0&event_pct=0.15` (native) · `limit=20` (web) | `/api/predictions/resolutions` — uncached |
| Sports | `/api/feed?limit=50&offset=0&mode=sports` (native) · `limit=20` (web) | `/api/feed?limit=200&include_futures=false` · `/api/futures/grouped-feed?limit=20` — no server cache |
| Browse | **nothing** | **nothing** |
| Search | `/api/events/search/trending` | typeahead / search on keystroke |
| My Stuff | `/api/predictions/stats` — fires **signed out**, uncached | `/api/feed?…my_teams_only=true` (auth only) · `/api/me/team-futures` |

### Two honest holes, declared before they can be papered over

**Browse costs nothing and that is a source fact, not a measurement.**
`Views/LeaguesView.swift:55-78` renders static league/category arrays and calls only
`AnalyticsService.trackScreen`; the web Browse is a link dropdown with no route of its own
(`components/BottomNav.tsx:56`). The network call in `LeagueGridViewModel` belongs to a
drilled-in league page. Browse is therefore reported as **NO SERVER DEPENDENCY**, asserted from
source and pinned by a test — **never as "0 ms measured"**. A request that is never issued has no
latency, and printing a zero as though an instrument produced it would be this program's own
favourite mistake for the fourth time.

**My Stuff's authenticated feed is NOT MEASURABLE from this sandbox.** `my_teams_only=true`
without a user returns an empty `requires_auth` body with no cache header
(`routes/feed.py:2049-2069`) — a different code path that exits before the work starts, so an
anonymous probe of it is not a floor. This sandbox holds `ADMIN_TOKEN`, an admin secret, not a
user session JWT, and there is no read-only way to mint one. The probe is still issued and
recorded as `requires_auth`, so a later reader can see it was checked rather than assumed.

What is known structurally gets printed instead of a fake number: the key is `u:<id>`, the TTL is
30 s (`FEED_RESPONSE_TTL_MY_TEAMS_SECONDS`), and nothing pre-warms it — `FEED_PREWARM_SHAPES` has
no my-teams entry and could not have one, since the content depends on which teams that person
follows. What a **signed-out** person waits for on that tab is measurable and is measured:
`/api/predictions/stats`, unconditional and uncached.

---

## 3. The bars, and where each one comes from

Every bar is **inherited**, not invented. A cycle that picks its own bar has graded itself.

| bar | value | derivation |
|---|---:|---|
| **tab first-load p50** | **≤ 1,000 ms** | Inherited verbatim from the charter's existing `FEED_MISS_P50_BAR_MS = 1000`, which `done_bar_snapshot.py` reads off `docs/PRD.md`'s "37.5 % of loads miss at ~4.1 s". Same surface, same unit — a tab does not get a softer bar than the feed already had. It also lands on the flow threshold (~1 s is where a wait stops feeling like a response), which is why 1,000 was defensible for the feed in the first place. |
| **cold `/api/events/search` p50** | **≤ 1,000 ms** | Same bar, same reasoning: a results page is a page load, not a keystroke. |
| **cold `/api/events/typeahead` p50** | **≤ 500 ms** | UNCHANGED from the charter. Keystroke path. The one number this program has published a series for keeps its bar. |
| **hard ceiling, per sample** | **≤ 6,000 ms** | `DiscoverViewModel.retryBudget = 6` (`DiscoverViewModel.swift:216`) — a non-retryable client deadline past which the native client gives up and paints disk last-good. Graded on the **max**, not the median, because one sample over it is a user-visible failure that a median hides. |

**Nothing here is a target the lane chose.** If a number lands just over a bar, the bar does not
move; the report says NOT MET and names the margin.

---

## 4. The instrument

`backend/scripts/cold_path_snapshot.py`, exit 0 = every bar MET, 1 = measured and NOT MET,
anything else = the harness failed (gotcha #54).

- **Round-robin, not block-sequential.** A dyno restart, a heavy beat or a slow database minute
  lands on whichever path is running; a blocked run attributes the whole transient to one tab.
  Round-robin does not remove the noise, it stops it being mistaken for a finding about one
  surface.
- **The term sets are IMPORTED from `done_bar_snapshot.py`, not re-typed.** A delta against a
  different term set is not a delta, and a copied list drifts on its first edit with nobody
  seeing it.
- **Typeahead probes run with `?debug_timing=1`** (`_suppress_trending_write` → zero votes into
  `search:trending:24h`). That flag also bypasses the response cache, so the number is a cold
  BUILD and reads **~2.2× low** against a true first touch (measured, LAT-P097). It is labelled
  on every line and is not comparable to the voting-mode series.
- **`/api/events/search` is opt-in** (`--with-search`) because it writes `search_query_logs`, the
  table #1916 exists to clean.
- **Ruling 127's organic-first protocol is enforced by the instrument**, not by memory: the
  script refuses to print a clean contamination block unless `--stats-before` names the
  `latency-stats` read taken *before* any probe. Every `/api/feed` request this script makes
  lands in that always-sampled window.

---

## 5. What this cycle will then do, stated before the numbers exist

Build the single largest reduction the baseline table exposes, under the lane's standing
boundaries: no `feed_cache.py` keying/TTL edits (#2216 owns them), no beat-schedule edits, no
unattended DDL (ruling 131 — index DDL rides Alex's attended `psql` batch), and a guard test for
the class of every fix.

If the table exposes nothing worth a session, the else branch is the same one LAT-P095 and
LAT-P097 took: say so, in one line, with the arithmetic that rules it out.
