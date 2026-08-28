# LAT-P110 — the quiet league tab, and a needle member that was never warm

Queue: RUNNER DIRECTIVE, latency lane, `runner-inbox/latency/015-coldpath-conveyor.md`.
Branch: `program/latency-95`, cut from `origin/master` @ `67e2585c`. Issue: **#2260**.
Identity `LAT-P110-20260828-w12697`.

Two things happened this cycle and only one of them was the ship.

**The ship:** opening a league tab that nobody has opened today cost **4,649 ms**, because
the RECENT RESULTS rail read every event in a fourteen-day window looking for one league's
own. Fixed, guarded, RED-proven 8/8.

**The other thing:** the needle refused for a third consecutive read, and the reason is
not the one the last two cycles filed. Its cold-search member has been returning **HTTP
429** and the harness has been scoring the throttle as a **warm 2 ms search**. That is
LAT-P109's parked P109-6 — "cause NOT established" — established.

---

## 0. The cold path, first (ruling 137)

Taken on production slug `67e2585c`, uptime 2,115 s, `LAT-P110-mid`,
`backend/scripts/needle_latency.py` at the canonical defaults.

| surface | member | graded | cold | p50 cold |
|---|---|---|---|---|
| Discover open | `discover_native` | 5 | 0 | — |
| | `discover_web` | 5 | 0 | — |
| tab loads | `sports_native` | 5 | 0 | — |
| | `sports_web` | 5 | 0 | — |
| | `search_trending` | 5 | 0 | — |
| | `my_stuff_stats` | 5 | 5 | **11.0 ms** |
| cold search | `search_cold` | 6 | 0 | — *(all six were 429 — §5)* |

**REFUSED**: 1 of 7 cold members against a floor of 4; 1 of 3 graded surfaces. The floors
did their job — the arithmetic would otherwise have published **11 ms**.

And the surface this queue actually shipped on is not in that pool at all. The league tab
is not a needle member, so the fix below moves nothing in the line. Said plainly rather
than smuggled: **this cycle's ship is invisible to this lane's headline number.** That is a
fact about the pool's membership, which is a frozen literal and changes only by an explicit
edit — not something to fix by editing it mid-cycle to include the thing that just got
faster.

---

## 1. The ship — `americanfootball_cfl` took 4.6 seconds to list seven games

A cold sweep of all 29 registered leagues, fresh `x-session-id` per request, server time
from `x-response-time`:

```
americanfootball_cfl      4,649 ms   fresh      <- full miss
basketball_nba            3,716 ms   fresh      <- full miss (earlier pass)
icehockey_nhl             1,590 ms   fresh      <- full miss (earlier pass)
basketball_ncaab            945 ms   fresh
americanfootball_ncaaf      813 ms   fresh
...
mma_mixed_martial_arts       27 ms   fresh      <- primary hit
baseball_mlb                 38 ms   fresh      <- primary hit
```

`/api/leagues/{sport_key}` is a stale-while-revalidate cache: `LEAGUE_PRIMARY_TTL` 300 s,
`LEAGUE_STALE_TTL` 86,400 s, with a single-flight background rebuild on every stale hit
(#1767). The synchronous build runs only when **both** slots miss — which is precisely the
league nobody has opened for twenty-four hours.

**So the cost is anti-correlated with traffic.** The busy leagues are always warm and never
pay it. The person who opens the CFL tab is, structurally, the person who waits.

Consumers are real: iOS `Services/APIClient.swift:929` and web `frontend/lib/api.ts:1595`.

---

## 2. It is not the futures query, and that was checked before it was blamed

`build_league` issues exactly three statements. The obvious suspect — a 200-row
`selectinload` over `futures_markets` with six leading-`%` ILIKEs — is **7.1 ms** for CFL:

```
Limit  rows=0  t=7.109ms  blk=2,924
  Sort
    Bitmap Heap Scan futures_markets  rows=0  t=7.095ms
```

The upcoming-games rail is **4.4 ms / 52 blocks**. Everything left is the results rail.

---

## 3. The cause: an ORDER BY the planner could serve, and a LIMIT it believed

```sql
SELECT events.* FROM events JOIN sports ON sports.id = events.sport_id
WHERE sports.key = 'americanfootball_cfl'
  AND events.status IN ('completed','closed')
  AND events.commence_time >= now() - interval '14 days'
ORDER BY events.commence_time DESC LIMIT 9
```

`EXPLAIN (ANALYZE, BUFFERS)`:

```
Limit                       rows=7   t=4,923.138 ms  blk=39,577
  Nested Loop
    Index Scan events       rows=60,447  t=4,888.866 ms  blk=39,574
    Materialize
      Index Scan sports     rows=1   t=0.022 ms
```

`ix_events_commence_time` already produces the requested order, so the planner walks it and
expects the LIMIT to stop it after nine rows. For a league that played yesterday it does.
For a league that did not, **nothing stops it but the fourteen-day window** — it reads all
60,447 events in that window to find seven.

There is no `(sport_id, commence_time)` index. `events` carries `ix_events_sport_id` and
`ix_events_status_commence` as separate btrees, so the selective column and the ordered
column cannot be served by one scan.

### Why it is not "just the CFL"

Eight leagues, `EXPLAIN (ANALYZE, BUFFERS)` on the **exact statement the ORM emits** —
generated with `literal_binds` from the real query object, not hand-written. Blocks, not
milliseconds: wall time swung 4,923 → 605 ms on the *identical* 39,605-block plan as the
buffer cache warmed, so a ms-only claim here would be a claim about the cache.

| league | flat blocks | fenced blocks | rows |
|---|---:|---:|---:|
| `americanfootball_cfl` | 41,495 | **204** | 7 |
| `basketball_wncaab` | 41,731 | **205** | 0 |
| `soccer_epl` | 41,731 | **219** | 11 |
| `baseball_ncaa` | 41,731 | **329** | 0 |
| `basketball_ncaab` | 41,707 | **208** | 0 |
| `americanfootball_nfl` | 13,975 | **292** | 14 |
| `baseball_mlb` | 4,062 | **427** | 14 |
| `tennis_atp` | 3,824 | **429** | 14 |
| **total** | **230,256** | **2,313** | |

**~325 MB of buffer traffic per cold league open — and three of the eight spend it to
return zero rows.** Every league improves or holds. None regresses.

---

## 4. The fix, and the two things it deliberately is not

`OFFSET 0` on the inner filter; ORDER BY and LIMIT outside it. PostgreSQL's
`is_simple_subquery()` refuses to pull up any subquery carrying a limit or offset node —
the check is on the node's **presence**, not its value — so the filter runs to completion
before the sort and the planner reaches for `ix_events_sport_id`.

Row counts were **asserted identical** between the two forms on all eight leagues, in the
same harness that produced the block counts. Same rows, same order, same LIMIT.

Three decisions worth naming, because each of them was measured rather than assumed:

**It is a literal `0`, not `.offset(0)`.** A bind renders `OFFSET $1`, which fences exactly
as well — but then the statement in production is not the statement in the table above, and
the evidence stops being about the code. Guarded.

**The sibling upcoming-games query is NOT fenced.** Its ORDER BY leads with a
`CASE WHEN status = 'live'`, so no index can serve the ordering and the planner already
collects-and-sorts; there is no pushdown to prevent. Fencing it measured **strictly worse**
— `basketball_ncaab` 56 → 5,130 blocks. A fence is a claim about one plan, not a house
style. Both queries moved to named builders (`upcoming_games_query`,
`recent_results_query`) specifically so that asymmetry is a documented, tested decision
rather than an accident of layout that a later tidy-up would "fix".

**Resolving `sport_id` first was tried and rejected.** Equality on a constant `sport_id`
also unsticks CFL (39,605 → 57 blocks) but leaves five leagues on the old plan
(`basketball_ncaab` 40,565, `soccer_epl` 40,565, `baseball_ncaa` 40,565), and it costs an
extra round trip. The fence fixes all of them and keeps the join. A guard asserts
`build_league` still issues exactly **three** statements, so that round trip cannot creep
back in later.

### The permanent form, REQUESTED and not taken

`CREATE INDEX ON events (sport_id, commence_time DESC)` turns this into a nine-row index
scan and would make the fence unnecessary. It is DDL, so the migration slot is the
Integrator's under **ruling 080** — requested on #2260, never taken. Gotcha #31 also binds
(no `CREATE INDEX CONCURRENTLY` in Alembic; Heroku's release phase times out around five
minutes). The fence ships now and costs nothing if the index lands later.

### The unbounded inner set, declared rather than discovered

The fenced subquery has no LIMIT, by necessity: bounding it correctly would need an ORDER
BY, which is the pushdown the fence exists to prevent. The bound is the fourteen-day
window, and it was measured rather than reasoned about — across all 29 registered leagues
the largest inner set is `tennis_atp` at **470 rows** (`baseball_mlb` 206, `soccer_epl` 11).
All 60,445 completed/closed events in the window belong to *all* sports; no single league
approaches it.

---

## 5. 🔴 The needle's cold-search member was never warm. It was throttled.

LAT-P109 parked **P109-6**: "the needle's cold-search member went 6/6 WARM at 2–4 ms …
Cause NOT established." It is established, and it is an instrument defect.

Every one of those samples is an **HTTP 429**:

```json
{"path": "/api/events/search?q=kaiserslautern", "http": 429, "server_ms": 3.0,
 "queries": 0, "class": "warm"}
```

`cold_path_snapshot._classify()` reads `X-Feed-Cache`, and failing that falls back to the
query count: `return "cold" if q > 0 else "warm"`. **It never looks at `http`.** A
rate-limit rejection carries no cache header, executes zero queries and answers in 2–3 ms
with a real `x-response-time`, so it is graded — as a warm search. The API's limit is
60/minute per IP and a canonical run issues ~68 requests, with the searches last.

Audited across every needle artifact still on disk:

| run | cold-search samples | cold members | published |
|---|---|---|---|
| `LAT-P107` | 6 × **200**, cold | 6/7 | **939.5 ms** |
| `LAT-P109-open` | 6 × **200**, cold | 2/7 | refused |
| `LAT-P109-close` | 6 × **429** → "warm" | 1/7 | refused |
| `LAT-P110-baseline` | 6 × **429** → "warm" | 1/7 | refused |
| `LAT-P110-mid` | 6 × **429** → "warm" | 1/7 | refused |

**The published series (882 → 873 → 940 → 1273) is NOT contaminated** — every run that
produced a number did so on real 200s. Checked, not assumed; that is why the table is here
rather than a sentence saying it is fine.

What the defect did cost is the diagnosis. Three of the last four refusals were read as
"the pool went warm", and for the cold-search member that reading was wrong: the surface
did not go warm, it went **unmeasurable**, and those are different findings with different
owners. One is Alex's DECIDE item about prewarm; the other is a bug in this lane's own
instrument.

It is also self-inflicted in a way worth naming: a latency lane spends its session issuing
`db-query` EXPLAINs and route probes from the same IP, so the harness is throttled *because*
the lane is working. This session put a 29-league sweep and ~60 EXPLAINs through production
before the needle ran.

**Fixed in this branch** (`backend/scripts/cold_path_snapshot.py`): a non-200 sample is
classed `error`, is excluded from `graded`, and is reported by count and status so a
throttled run is loud rather than silent. The needle prints `THROTTLED` for a member whose
samples were all rejected, instead of dropping it into the same bucket as a member that was
genuinely warm. This changes only what the instrument **refuses** — no served request is
measured differently — so the series is unaffected.

**Not fixed, and parked:** pacing the harness under 60/min, or retrying a 429 after
`Retry-After`. Either would restore cold search as a measurable surface, and either is an
instrument change of the kind ruling 127 says must not be smuggled into a series. It wants
its own decision.

---

## 6. Gates

- **Full suite** — see §6a. `EXIT CODE` read BY VALUE (gotcha #124).
- **New guards**: `backend/tests/test_league_rails_query_plan.py`, **14 tests**.
- **RED-proven 8/8** by `backend/scripts/evals/league_rails_fence_mutations.py`: each
  mutation applied alone from a `cp` backup, the suite required to exit **1** (not merely
  non-zero — an exit 2 collection error is recorded as HARNESS, not as a kill), and the
  file **sha256-verified restored** before the next.

  ```
  M1-fence-removed              M5-route-keeps-an-inline-copy
  M2-fence-is-a-bind            M6-lookback-window-changed
  M3-order-by-pushed-inside     M7-statuses-copy-pasted
  M4-sibling-fenced-too         M8-cap-dropped
  8/8 killed · 0 survived · 0 unapplied · post-restore suite exit 0
  ```

  M5 is the one that matters most: it puts the **exact pre-fix statement** back into
  `build_league` while leaving `recent_results_query` correct. A guard suite that only
  compiles the helper stays green through that (memory: a plant must hit the render).
- **Related suites, before the full run**: 178 passed, exit 0, across `test_startup`,
  `test_league_games_rail_probability`, `test_entity_page_tiers`,
  `test_entity_tier_histogram_reads_declared`, `test_hub_cache_swr`,
  `test_team_cache_detachment`, `integration/test_route_league_revalidation`,
  `integration/test_league_futures_dedup_identity`, `integration/test_route_hub`,
  `integration/test_futures_compare_removed`.
- **ruff: ZERO NEW.** The three F401 in `app/routes/league_futures.py` (`and_`, `func`,
  `FuturesOutcome`) are pre-existing — verified by running ruff against **master's own copy**
  of the file, not by assertion. Both new files clean.
- **black**: both new files clean. `app/routes/league_futures.py` deliberately NOT run
  through black — master's copy is not black-clean and reformatting it would turn a 30-line
  fix into a whole-file diff.

---

## 7. Contamination, declared

- **This session refreshed every league's 24-hour mirror.** The 29-league cold sweep wrote
  `bainluck:league:<key>` and `…:stale` for all of them, so the natural full-miss population
  is suppressed until roughly **2026-08-29 23:00Z**. A post-deploy check that goes looking
  for a naturally cold league before then will find none and must not read that as the fix
  working. Use the EXPLAIN check instead — it does not need a cold cache.
- ~60 `EXPLAIN (ANALYZE)` statements and ~90 route probes through production, all reads.
  `EXPLAIN ANALYZE` executes; every statement was a `SELECT` over `events`/`sports`/
  `futures_markets`, no writes.
- The needle run writes one `search_query_logs` row per cold-search sample (#1916) — six
  per run, three runs. All six were 429s and reached no logging.

---

## 8. Post-deploy checks OWED to the first window after this reaches a release

1. **The EXPLAIN, on three quiet leagues.** `americanfootball_cfl`, `basketball_ncaab`,
   `baseball_ncaa` via `/api/admin/db-query` with `explain: true, analyze: true`, using the
   statement the route now compiles. The scan must name **`ix_events_sport_id`** and total
   blocks must stay in the **hundreds**. Quote the blocks, not the ms.
2. **A cold league open, after 2026-08-29 23:00Z**, when the mirrors this session refreshed
   have expired. `americanfootball_cfl` should be well under a second on a full miss.
3. **`recent_results` must still be populated.** `soccer_epl` returned 11 rows before and
   after; a fix that quietly emptied the rail would look like a speedup.
4. **The three statements.** `build_league` must still issue exactly three — a fourth means
   somebody re-introduced the `sport_id`-resolving round trip the fence exists to avoid.

---

## 9. Parked

Filed to `PARKED-MEASUREMENTS.md` as **P110-1 … P110-5**. Two are worth naming here:

**P110-2 — `/api/feed/tag-counts` returns HTTP 500 and it breaks a real page.** LAT-P108
parked this as "undiagnosed" and as reliability's territory. It is still 500ing, and it has
a consumer that the parked note did not name: `frontend/app/categories/page.tsx:26` renders
`ErrorState("Failed to load categories")`. Both of the route's own statements are fast when
run directly (566 ms and 120 ms via `db-query`), so it is **not** the timeout its shape
suggests, and the response body is Starlette's plain-text `Internal Server Error` rather
than FastAPI's JSON — an unhandled exception, not a handled failure. Diagnosis not
attempted; this cycle already had a ship.

**P110-3 — `/api/events/discover` 503s with `greenlet_spawn has not been called`.** A lazy
load in an async context. No frontend or iOS consumer found, so it breaks no page today.

---

## 10. The needle

```
NEEDLE: latency REFUSED @ 2026-08-28T23:07:45Z — 1/7 cold members against a floor of 4,
1/3 graded surfaces. Series 882 -> 873 -> 940 -> 1273 -> refused -> refused -> refused.
Without the floors this read would have published 11 ms. NEW THIS CYCLE: one of the six
missing members was never warm — `search_cold` was 6/6 HTTP 429 and the harness graded the
throttle as a warm 2 ms search (§5, now fixed). The published series is not contaminated;
the last three refusals were partly mis-diagnosed.
```
