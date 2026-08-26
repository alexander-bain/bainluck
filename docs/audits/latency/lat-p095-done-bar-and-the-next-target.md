# LAT-P095 — the done-bar math, and why the next target is not the feed

**Cycle:** LAT-P095 · **Date:** 2026-08-26 · **Identity:** `LAT-P095-20260826-w58397`
**Directive:** Fable 2026-08-26, pasted and reviewed by Alex. Three items.
**Production state while measuring:** `origin/master` = `af9c3ffb` = Heroku **v3903**
(released 13:32:05 PDT), `/api/health` commit `af9c3ffb`. **LAT-P093 (`-82`) is LIVE.
LAT-P094 (`-83`) is NOT** — it is an unmerged branch. Every number below is stated against
that state, never against a modelled deploy.

**Boundary respected:** `feed_cache.py` was NOT edited. #2216 (lane1) owns keying/TTL.
**No code changed this cycle. No load was generated against `/api/feed`.**

---

## 0. The headline, in one table

| number | value | verdict |
|---|---:|---|
| **feed p50, warm** (`x-response-time`, n=6) | **18 ms** | ✅ clears — matches the PRD's 16 ms baseline |
| **typeahead p50, warm** (n=8) | **26 ms** | ✅ |
| **typeahead p50, FIRST TOUCH** (n=8 never-asked terms) | **3,816 ms** | 🔴 **does not clear** |
| the statement inside it | `futures_query`, **90–95 %** of every cold build | named |
| its production cost, 73-day window | **514,687 calls · 353.3 hours · 2,470.9 ms weighted mean · 30,302 buffers/call** | the largest DB consumer measured in this program |

**THE DONE-BAR IS NOT MET.** The lane keeps its standing slot. The failing half is
**typeahead**, not the feed — and after two cycles of feed surgery that is the finding that
matters, because it redirects the program.

---

## 1. Item 2, first half — the ring, and why it could not grade anything

`GET /api/admin/latency-slow-events?limit=500&min_ms=0`, read 2026-08-26 21:07:15Z.
`ring_used 500/500`, `unparseable 0`. **165 `/api/feed` `miss` events.** A read of
already-recorded events; this lane generated no load.

🔴 **The ring has produced ZERO `/api/feed` misses since 11:36:41Z — 9.5 hours — and zero
since either of today's two deploys** (v3902 20:04:21Z, v3903 20:32:05Z). The newest event of
*any* path is 20:28:12Z, four minutes before v3903.

So the cohort is **byte-for-byte the pre-deploy population LAT-P094 read at 20:07Z** (166 then,
165 now — one aged out). It cannot grade `-82`, it cannot grade `-83`, and a re-read tomorrow
may not either: feed-miss inter-arrival is **p50 272.3 s, p90 10,344.5 s, max 39,261.5 s**, and
36 of 164 gaps already exceed 39 minutes. The instrument is not broken; it is sparse, and the
ring's own `threshold_ms = 5000` means a miss that gets *faster* leaves the sample silently.

That is stated first because everything in §2 is therefore a **modelled** post-fix ranking, not
a measured one.

### The stage table as it stands (pre-`-83`, n=165, total p50 7,314.2 ms)

| stage | n | p50 ms | max ms |
|---|---:|---:|---:|
| `futures` (parent) | 161 | 3,987.5 | 21,969.0 |
| `concepts` | 160 | 1,447.3 | 16,439.0 |
| `futures.canonical_counts` | 143 | 1,338.4 | 15,848.3 |
| `events` | 164 | 1,208.6 | 8,201.5 |
| `futures.market_load` | 154 | 1,039.3 | 7,519.9 |
| `futures.scoring_loop` | 149 | 297.4 | 667.9 |

### Modelled with both fixes applied

`canonical_counts` × (166.4/1,667.1) per LAT-P093's measured A/B; `concepts` − 656.1 ms per
LAT-P094's. `futures.UNATTRIBUTED` is the parent minus its named children — time inside the
futures stage that **no timer names**.

| leaf stage | n | p50 ms |
|---|---:|---:|
| **`events`** | 164 | **1,208.6** |
| `futures.market_load` | 154 | 1,039.3 |
| `futures.UNATTRIBUTED` | 161 | 905.9 |
| `concepts` (residual) | 160 | 791.2 |
| `futures.scoring_loop` | 149 | 297.4 |
| `futures.canonical_counts` (residual) | 143 | 133.6 |

**`events` is the next-biggest stage**, and it is dominant in **63 of 165** misses — more than
any other. On the ring's own arithmetic it looks exactly like the last two sessions' target.

---

## 2. Item 2, second half — `events` is NOT worth a session, and here is the proof

LAT-P093 and LAT-P094 both worked because one statement was doing something absurd. `events`
has no such statement. It makes exactly three DB round trips (`get_statpal_end_time` is pure;
`queries: 21` per miss rules out an N+1), and all three were measured on production today:

| statement | measured | production mean (`pg_stat_statements`) |
|---|---:|---:|
| the `#2065` candidate query | **6.0 ms** (`EXPLAIN ANALYZE`, 653 window rows → 211 admitted) | 128.6 ms / 4,395 calls |
| the `win_prob_snapshots` fallback | **34.3 ms** (400 ids) | 32.3 ms / 28,714 calls |
| `_get_championship_probabilities` | **356.6 ms** | **552.8 ms / 13,820 calls** |

**~400 ms warm against a 1,208.6 ms stage p50.** The stage is flat across the clock
(p50 1,014–1,598 ms at every UTC hour with n ≥ 8), so slate size is not the driver either.

### The one real defect inside it, and why it is still third-order

`_get_championship_probabilities` does have the family pathology:

```
Aggregate rows=400
  Nested Loop rows=332 loops=2 time=220.1 hit=54,544
    Bitmap Heap Scan futures_outcomes rows=6,238 loops=2 time=72.9 hit=4,611
      Bitmap Index Scan ix_futures_outcomes_team_id rows=17,176 time=2.2
    Index Scan futures_markets rows=0 loops=12,475 time=0.022 hit=49,933  FILTER=1
```

**12,475 index probes into `futures_markets` for 1,428 distinct markets, to keep 664 rows and
emit 400.** An 8.7× redundant probe; 49,933 of the 54,551 buffers are the probes.

Four shapes measured on production, same session, warm:

| shape | ms | plan |
|---|---:|---|
| A — current | 360.4 | nested loop, 12,475 probes |
| B — `IN (SELECT id FROM futures_markets …)` | 368.9 | planner picks the same plan |
| **C — join through `DISTINCT market_id`** | **231.4** | probes deduped |
| D — `= ANY(ARRAY(…))` | — | refused by the `analyze` allowlist |

Best available: **1.56×**, ~130 ms warm. It also executes on only ~22 % of `_score_events`
calls (a 5-minute process-global cache absorbs the rest), and driving from the markets instead
is worse — no index carries `(market_tier, status)`, so that side costs the same 50,749-row
`ix_futures_markets_status` scan `concepts` was just rescued from.

**Verdict: ~198 ms of production mean on ~22 % of cold builds ≈ 2.7 % of a p50 miss.** That is
the same tier as LAT-P094's own parked index (~7 %), which the last cycle declined to build.
Building it here would be off-directive: the instruction was to build *if the stage is worth a
session*, and it is not.

`futures.market_load` (1,039.3 ms) is next and is a pkey `IN`-list plus a `selectinload` — it
loads what the feed renders, proportional to output, with no scan pathology.
`futures.UNATTRIBUTED` (905.9 ms) is the honest unknown, and finding it is instrument work,
which under the LANE ROLES rule is not this lane's to do unprompted.

**So the remaining feed stages are small, and the else branch fires.**

---

## 3. Item 2, the else branch — the done-bar math

Measured from this sandbox against v3903, 40+ minutes post-release (well clear of the
post-deploy window that reads as a false regression). Server-side times are the API's own
`x-response-time` / `x-timing-split` headers, **not** wall time — the sandbox's network floor to
Heroku is 246.4 ms p50 (`/api/health`, n=6) and would otherwise swamp every number here.

### Feed — ✅ CLEARS

```
/api/feed?limit=20 , n=6:  26 17 18 17 18 16 ms   ->  p50 = 18 ms
x-timing-split: wall=14.1..23.6; db=0.0; app=14.1..23.6; q=0
```

**18 ms p50 warm**, `db=0.0`, zero queries. The PRD's first honest measurement was 16 ms warm.
Two years of this program's work is intact and the warm path is not the problem.

### Typeahead — 🔴 DOES NOT CLEAR

Eight never-asked terms, first touch, then an immediate second touch:

| term | first touch | second touch |
|---|---:|---:|
| `celtics` | 29 ms *(already warm)* | 28 ms |
| `ballon` | 1,540 ms | 27 ms |
| `wimbledon` | 3,151 ms | 25 ms |
| `nvidia earnings` | 3,735 ms | 27 ms |
| `tour de france` | 3,897 ms | 27 ms |
| `senate runoff` | 4,039 ms | 25 ms |
| `emmy` | 4,050 ms | 25 ms |
| `hurricane` | 4,562 ms | 24 ms |
| **p50** | **3,816 ms** | **26 ms** |

The two modes are 147× apart and the cache TTL is **45 seconds**. A user typing a term nobody
asked in the last three-quarters of a minute waits ~4 s for the dropdown.

An earlier pass over eight *plausible* terms measured `chiefs` 3,988 ms, `trump` 7,386 ms and
`open` 10,058 ms server-side on first touch — and `open` was **still 8,679 ms on the second
touch**, i.e. it had already re-expired.

### It is one statement

`?debug_timing=1` bypasses the cache in both directions, so it reads a genuine cold build:

| term | total_ms | **futures_query** | teams_query | events_query | everything else |
|---|---:|---:|---:|---:|---:|
| `wimbledon` | 1,732 | **1,557 (90 %)** | 106 | 64 | 5 |
| `hurricane` | 1,113 | **1,043 (94 %)** | 43 | 23 | 4 |
| `emmy` | 1,065 | **1,007 (95 %)** | 40 | 14 | 4 |
| `oscars` | 1,051 | **990 (94 %)** | 41 | 15 | 4 |

(These totals sit below the 3,816 ms p50 above because the shared buffers were warmed by the
earlier probes and no cache write is paid. The *proportion* is what this table is for, and it
does not move: 90–95 %, every term.)

`x-timing-split` on the cold header runs agrees from the other side —
`db=4,500.9` of `wall=4,561.6` for `hurricane`, with a single worst query at 4,323.9 ms. It is
one query, it is 95 % of the answer, and it is the reason the done bar fails.

### What that statement costs the database

`pg_stat_statements`, 26 fingerprints matching the typeahead futures shape (identified by its
distinctive `ORDER BY market_tier ASC NULLS LAST, volume DESC NULLS LAST LIMIT $n`), over the
73-day window since 2026-06-14:

```
calls        514,687
total        353.3 HOURS of database time
weighted mean  2,470.9 ms
buffers        30,302 shared hits per call  (~237 MB) — to return at most 20 markets
```

For scale: the statement LAT-P093 killed was *38 % of all database time on a feed miss*. This
one is the largest single consumer this program has measured anywhere, and it sits on the
keystroke path.

⚠️ Caveats, because they bound the claim: `pg_stat_statements` is near its 5,000-entry cap so
this may under-count evicted siblings, errored statements are never recorded (a timing-out
typeahead is invisible), and the 26 fingerprints are the `/typeahead` shape — the `/search`
futures query at `events.py:3434` is a near-twin and some fingerprints may belong to it.

### The cheap partial lever, sized

Repeat-gap distribution over 1,172 consecutive same-term pairs in `search_query_logs`, 14 days:

| cache TTL | share of repeats that could hit |
|---|---:|
| **45 s (today)** | **26.0 %** |
| 300 s | 38.1 % (**+12.1 pp**) |
| 900 s | 39.1 % (+1.0 pp) |

Raising the TTL to 300 s buys 12 points of warm rate; going past it buys nothing — the curve
flattens hard, which is a genuine stopping point rather than a guess. But **74 % of requests are
cold at any TTL**, so this is a partial lever and the query rewrite is the real fix.
⚠️ `search_query_logs` is `/search` traffic and is 23.6 % gold-sentinel per #1916; sentinel
traffic is *periodic*, which biases gap distributions. Treat this as a proxy, not typeahead's
own distribution. **Recommended, not done** — a TTL is a staleness decision.

---

## 4. Item 3 — the parked index spec's precondition P1

**One line, as asked: P1 now reads differently and it RETIRES the spec.**

P1 requires `concepts` to be **≥ 800 ms p50 AND in the top three stages**. Modelled post-`-83`
it is **791.2 ms** — 8.8 ms under the floor — and **4th**, behind `events` (1,208.6),
`futures.market_load` (1,039.3) and `futures.UNATTRIBUTED` (905.9).

Both clauses fail, so the DDL does not run, and the spec says in its own text that this outcome
"is a pass for this spec, not a failure of it."

Two honesty notes that belong with the verdict:

- **The retire rests on the rank clause, not the p50 clause.** 791.2 vs 800 is an 8.8 ms margin
  on a number produced by subtracting a flat 656.1 ms from every sample — far inside the model's
  error. The rank clause has a 114.7 ms margin and is the one carrying the verdict.
- **It is a projection, not a measurement, and cannot be confirmed until `-83` is deployed** and
  the ring has collected post-deploy misses. Per §1 that is not a matter of waiting minutes.

`docs/audits/latency/lat-p094-open-category-index-gate-spec.md` is marked RETIRED-PENDING-CONFIRM
rather than deleted: if the post-`-83` measurement lands above 800 ms and back in the top three,
P1 passes and the spec is live again unchanged. That is what a frozen bar is for.

---

## 5. What the next session should do

1. **`futures_query` on `/api/events/typeahead`** (#1866) — 90–95 % of a cold build, 3,816 ms
   p50, 353.3 hours of database time. It already carries LAT-P007's UNION-not-OR rewrite, so
   this is a real session's work and not a one-liner. It is the named ship.
2. **Decide the typeahead cache TTL** (45 s → 300 s, +12.1 pp warm rate). Fable's call.
3. **#1916 / `SEARCH_HEAD_WARM_ENABLED`** — see §6 of the report. Today's numbers make the
   recommendation stronger, not weaker.
4. Not the feed. The feed's warm p50 is 18 ms and its remaining cold stages are third-order.
