# LAT-P110 — the quiet league tab, and a needle member that was never warm

Queue: RUNNER DIRECTIVE, latency lane, `runner-inbox/latency/015-coldpath-conveyor.md`.
Branch: `program/latency-95`, cut from `origin/master` @ `67e2585c`. Issue: **#2260**.
Identity `LAT-P110-20260828-w12697`.

Three things happened this cycle and only one of them was the ship.

**The ship:** opening a league tab that nobody has opened today cost **4,649 ms**, because
the RECENT RESULTS rail read every event in a fourteen-day window looking for one league's
own. Fixed, guarded, RED-proven 8/8.

**The second thing:** the needle refused for a third consecutive read, and the reason is
not the one the last two cycles filed. Its cold-search member has been returning **HTTP
429** and the harness has been scoring the throttle as a **warm 2 ms search**. That is
LAT-P109's parked P109-6 — "cause NOT established" — established.

**The third thing arrived mid-session and outranked the other two.** Fable staged
`runner-inbox/latency/015-needle-v3-ruling.md` — **Alex's option-c ruling** on the needle
after the warmer victory. The needle now publishes. §11.

---

## 0. The cold path, first (ruling 137)

Three reads this cycle, all on production slug `67e2585c`, all
`backend/scripts/needle_latency.py` at the canonical defaults (`--n 5 --n-search 6`), spaced
by roughly an hour. The closing one, `LAT-P110-close` at uptime 3,312 s, **taken with the
grader fixed** (§5):

| surface | member | graded | cold | p50 cold |
|---|---|---|---|---|
| Discover open | `discover_native` | 5 | 0 | — |
| | `discover_web` | 5 | 0 | — |
| tab loads | `sports_native` | 5 | 0 | — |
| | `sports_web` | 5 | 0 | — |
| | `search_trending` | 5 | 0 | — |
| | `my_stuff_stats` | 5 | 5 | **12.0 ms** |
| cold search | `search_cold` | **0** | 0 | — 🔴 **6× HTTP 429, refused by the server** |

**REFUSED**: 1 of 7 cold members against a floor of 4; 1 of 3 graded surfaces. The floors
did their job — the arithmetic would otherwise have published **12 ms**.

That `search_cold` row is what changed. On the two earlier reads it said `graded: 6` and
those six samples were counted as warm 2 ms searches. It now says `graded: 0`, and the run
prints why:

```
🔴 search_cold was REFUSED BY THE SERVER, not warm — 6x HTTP 429. This surface was
   UNMEASURABLE this run; that is a different fact from 'it was fast'.
```

The refusal itself is unchanged — the floors rejected all three reads either way. What
changed is that the run no longer reports a surface as measured when it was not.

**The three reads, for the record:** `baseline` 1/7 (uptime 789 s), `mid` 1/7 (2,115 s),
`close` 1/7 (3,312 s). The pool is equally warm at thirteen minutes and at fifty-five
minutes after a deploy, so "the slug is young" is not the explanation — checked, because it
is the explanation a reader would reach for.

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

**Fixed in this branch** (`backend/scripts/cold_path_snapshot.py`, `needle_latency.py`): a
non-200 or a transport failure classes **`rejected`**, is excluded from `graded`, and is
counted by status. The needle now prints

```
   🔴 search_cold was REFUSED BY THE SERVER, not warm — 6x HTTP 429. This surface was
      UNMEASURABLE this run; that is a different fact from 'it was fast'.
   🔴 RATE LIMITED: 1 member(s) — search_cold. ... A latency lane running EXPLAINs from the
      same IP throttles its own harness (parked P110-4 — pacing needs a ruling, not a patch).
```

instead of filing the member beside the genuinely warm ones. The timing fields are **kept,
not dropped**: the 2 ms IS what the limiter took, and discarding it would hide the throttle
as thoroughly as mis-grading it did. This changes only what the instrument **refuses** — no
served request is measured differently — so the series is unaffected.

Guarded by `backend/tests/test_cold_path_rejected_samples.py`, **19 tests**, whose fixtures
are the verbatim `LAT-P110-mid` samples rather than invented shapes: a hand-drawn "error
sample" would have carried no `server_ms` and the old code would have excluded it anyway,
which is exactly why the real one got through. **RED-proven 5/5** by
`scripts/evals/cold_path_rejected_sample_mutations.py`, including R5 in the other direction
— over-rejecting a 200 would empty every median and read as a refusal.

**Not fixed, and parked:** pacing the harness under 60/min, or retrying a 429 after
`Retry-After`. Either would restore cold search as a measurable surface, and either is an
instrument change of the kind ruling 127 says must not be smuggled into a series. It wants
its own decision.

---

## 6. Gates

- **Full suite** — see §6a. `EXIT CODE` read BY VALUE (gotcha #124).
- 🔴 **The first full run was GENUINELY RED, and it was right.** Three failures in
  `tests/test_mutation_guard.py`, all one finding: the new
  `league_rails_fence_mutations.py` writes to disk without `guarded_targets`, and the
  residue scanner exited **2 — CANNOT MEASURE** on a harness shape it did not know. The
  harness's own `cp` + sha256 loop is real, but it is bookkeeping *between* mutants, not a
  crash guard — `try/finally` does not run under SIGTERM, which is how a mutant once rode
  `bcdcd95f` into a branch for a full cycle. Fixed rather than explained away: the guard now
  wraps the run and the shape is registered as `("MUTANTS", 2, 3, 1)`. Scanner back to exit
  0, 119 needles across 13 targets, 0 residue. (Its two `typeahead_warmer_mutations` drift
  reports are pre-existing and are DRIFT, not residue.) This is the class of catch that only
  a full run produces, and it argues against ever calling a targeted run sufficient.
- **New guards**: `backend/tests/test_league_rails_query_plan.py` (**14 tests**) and
  `backend/tests/test_cold_path_rejected_samples.py` (**19 tests**) — 33 in total, both
  RED-proven by their own harnesses (8/8 and 5/5).
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

🔴 **Superseded by §11 within the session.** The refusal below was the last reading taken
under the cold-only definition; Alex's option-c ruling arrived afterwards and the lane's
published line is now the one in §11. Kept because it is the evidence that the cold
statistic had stopped being able to describe the product, which is the finding the ruling
acts on.

```
(superseded) NEEDLE: latency REFUSED @ 2026-08-29T00:01Z — 1/7 cold members against a floor
of 4, 1/3 graded surfaces. Series 882 -> 873 -> 940 -> 1273 -> refused x3 this cycle (789s /
2115s / 3312s after deploy, all 1/7). Without the floors this read would have published
12 ms. That statistic is now `DIAG: latency-build`.
```

**THE LINE:**

```
NEEDLE: latency 18 ms @ 2026-08-28T23:45:40Z — 7/7 member paths served, all 3 graded
surfaces, canonical depth, slug 67e2585c. FIRST POINT OF A NEW SERIES (Alex's option-c
ruling, 2026-08-28): what a brand-new install waits, whatever cache serves it. Confirmed at
20 ms two minutes later. The old cold series 882 -> 873 -> 940 -> 1273 -> refused x7 is now
DIAG: latency-build (1,201 ms this run) and must never be plotted against this one.
DIAG: latency-build 1,201 ms @ 2026-08-28T23:47:48Z
```

---

## 11. 🔴 Alex's option-c ruling, and the needle publishing again

A second directive landed mid-session (`runner-inbox/latency/015-needle-v3-ruling.md`,
staged 15:52 PT). It outranks everything above, so it was implemented before close.

### What he ruled

The warmer landed and won: five of seven member paths could no longer be driven cold, so
the cold-only statistic refused **seven reads running**. *A metric that refuses because the
product got faster is measuring the wrong thing.* Strict division, two lines, distinct
names:

| line | what it is | where it goes |
|---|---|---|
| `NEEDLE: latency <ms>` | what a brand-new install actually **waits** — ruling 137's first load, whatever cache serves it | Alex's dial, one number per lane |
| `DIAG: latency-build <ms>` | the same statistic over **cold** samples only | lane reports **only**, never the dial |

**The series breaks, and the break is declared in the output of every run** rather than left
for a reader to notice. `882 → 873 → 940 → 1273` was the cold statistic and belongs to
`DIAG` from here; the `NEEDLE` series starts fresh. The two lines carry different names
precisely so nobody can plot a point from one against the other.

Option b's lesson survives option c: **both** statistics stay equal-weighted. A test drives
a fixture where one chatty 5 ms member would drag a raw pool to 5 ms while the dial holds at
800.

### The decoupling is the load-bearing part

Under the old shape a thin cold pool returned **before the line was ever printed**. That is
mechanically how seven consecutive reads published nothing about a product that was, in
fact, fast. `DIAG` may now refuse all it likes; the needle still ships, and the exit code
follows the needle alone.

### The harness had to stop throttling itself first, and the ruling is what made that legal

§5's 429s were not incidental to this — they were **blocking**. With `search_cold`
unmeasurable, the needle's own surface-coverage floor refuses just as the cold one did, so
option c on its own would have published nothing either.

Pacing at **1.05 s/request** is the fix, and it was deliberately *not* done earlier: ruling
127 forbids a delta that is a delta of instruments, and re-pacing a live series is not a
change a lane may make on its own authority. **This ruling breaks the series on purpose,
which is exactly the moment at which the instrument change costs nothing.** A canonical run
now takes ~75 s instead of ~20 s. That is the price of measuring the surface Alex named as
the most important one.

### The readings

Production slug `67e2585c`, canonical depth:

```
NEEDLE: latency 18 ms @ 2026-08-28T23:45:40Z   7/7 members served, 3/3 surfaces
NEEDLE: latency 20 ms @ 2026-08-28T23:47:48Z   7/7, confirming read two minutes later
DIAG:   latency-build REFUSED (2/7 cold)  then  1,201 ms (4/7 cold)
```

Per-member wait on the first read:

| member | p50 wait |
|---|---:|
| `sports_native` | 72.0 ms |
| `discover_native` | 59.0 ms |
| `my_stuff_stats` | 18.0 ms |
| `discover_web` | 17.0 ms |
| `search_trending` | 17.0 ms |
| `sports_web` | 14.0 ms |
| **`search_cold`** | **683.5 ms** |

🔴 **The surface that was invisible for three cycles came back as the slowest thing in the
pool by an order of magnitude** — 683.5 ms, then 458.5 ms on the confirming read, against
14–72 ms for every tab. That is the surface Alex's ruling 137 named as what a person
experiences in volume. It is the lane's obvious next ship and the conveyor will take it.

### One honesty note on DIAG's own comparability

Pacing changes DIAG too, and in a direction that flatters it: samples a second apart give
TTLs more time to lapse, which is why the confirming read found 4 of 7 members cold where
the unpaced reads found 1. **DIAG's series therefore restarts as well** — its 1,201 ms
should not be read as a continuation of 1,273 just because the numbers sit close. Said here
because the coincidence is inviting and nobody would have checked.

### Gates on this half

`tests/test_needle_latency.py`, **13 → 20 tests**. The five that asserted the old contract
were **rewritten, not deleted** — each still pins the floor it always pinned, now on the
`DIAG` line. One of them needed its fixture rebuilt:
`test_a_healthy_pool_emits_the_spec_line` used an equal cold/warm split, under which the
served median IS the cold median, so it would have passed with either statistic wired to
either line — the one thing it exists to rule out.

A set-precedence bug was found and fixed while wiring the refusal message: on sets `-` binds
tighter than `|`, so `set(POOL) | {"cold search"} - served` evaluates as
`POOL | (X - served)` and listed every surface as missing including the two that were
served. Pinned by `test_the_needle_refusal_names_only_the_surfaces_actually_missing`.
