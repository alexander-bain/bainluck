# LAT-P143 — the keystroke that answered without the markets

**Pillar: DISCOVER / MATCHING (Search — product priority #4, Instant Answers).**
**Ship: typing a team name in Search stops taking ten seconds to answer without the markets.**

Branch `program/latency-128`, base `944c466e`. Issue **#1866**.

---

## 1. TL;DR

* **`typeahead futures TIMED OUT` fired 43 times in the last 24 hours** on production, against
  9 times in the eleven days before that. The terms are `yan`, `sta`, `chi`, `stan`, `win`,
  `winner`, `lakers`, `mas`, `cel`, `bai`, `open`, `red sox`, `yankees`, `masters winner` — the
  prefixes a person types on the way to a real query.
* **Every one of those requests took 10.03–10.26 s and answered with no futures at all.** Not a
  slow answer: a wrong one, arriving slowly.
* **The cost is ONE arm**, and the GIN index is not the problem. For `q=yan` the trigram index
  produces 31,081 candidates in **63 ms**; the **heap fetch of 24,806 `futures_outcomes` rows
  costs 18,424 blocks and 6,115 ms** — and **97 % of those rows belong to CLOSED markets** and
  are discarded by the very next join. 24,806 rows read, 413 kept.
* **Two code-only cures were tried on production and both are disproved.** Written into the
  source so the next cycle does not re-derive them.
* **What cured it was neither**: giving the arm the page's own `ORDER BY` and `LIMIT`, which lets
  the planner terminate early. **`win` 13,801 ms → 477 ms. `yan` 5,771 ms → 520 ms.** Rows
  unchanged, and provably so.
* **D3 is graded in §6 after never having been graded**, which unblocks LAT-P063's Option D read
  path — and names the two things that still block it, neither of which was known.

---

## 2. How I picked it — the ranking, taken organically before anything was probed

Ruling 127: the organic read comes first. `GET /api/admin/latency-stats` at 07:50 UTC, then
`GET /api/admin/latency-slow-events?limit=500` — a **six-day ring of every production request
over 5 seconds, with per-stage attribution**, which is a far better ranking instrument than any
probe I could have fired and which this lane had not used for ranking before.

| # | path | slow events (6 d / 24 h) | verdict |
|---|---|---|---|
| 1 | `/api/feed` | 127 / 26 | **banked** — LAT-P141 on `-126`, awaiting the Integrator |
| 2 | **`/api/events/typeahead`** | **99 / 76** | ✅ **TAKEN** |
| 3 | `/api/playoffs/{league_slug}` | 58 / 53 | LAT-P129's surface; a single 08-29 14h burst, then nothing |
| 4 | `/api/events/{event_id}/related-futures` | 52 / 34 | LAT-P136's surface; real, and parked as **P143-2** |
| 5 | `/api/teams/{identifier}/prop-families` | 31 / 30 | **banked** — LAT-P138, merged; the 12,07x ms cluster is its own declared budget firing |
| 6 | `/api/events/search` | 31 / 0 | **banked** — LAT-P139 + LAT-P140, deployed 23:23 PT |

`/api/futures/browse` — last cycle's subject — contributed **3** events in six days. The
conveyor asked for the highest-impact path with no banked fix, and after the top of the board
was cleared of banked work, typeahead was the answer by a factor of two.

### The shape that made it legible, and the instrument gap that had hidden it

Splitting the 99 typeahead events by attribution produced two populations, and they are not two
degrees of the same thing:

```
APP-shaped   n=26   ms in [10,029.9 , 10,259.6]   app_ms 9.3-10.1 s, db_ms 74-660 ms
DB-shaped    n=73   ms in [ 5,025.7 ,  9,581.8]   db_ms dominant
```

Every APP-shaped sample is pinned inside a 230 ms band at exactly the 10 s request deadline, and
**no DB-shaped sample ever exceeds it**. That is a hard wall, not a distribution.

🔴 **The APP-shaped samples are DB time that the instrument cannot see, and this is a real gap
in the rail rather than a fact about the product.** `db_ms` is `Σ` over
`after_cursor_execute`, and SQLAlchemy does not fire `after_cursor_execute` when the cursor
raises — so **a statement killed by `statement_timeout` contributes ZERO to `db_ms` and its
entire duration lands in `app_ms`.** For twelve days the ring reported the typeahead deadline
blowouts as *application* time on a route whose defect is a query.

`request_timing.py` already computes `unfinished_queries` for exactly this case, and
`latency_stats.py` does not persist it into the ring (it copies five fields and that is not one
of them). Parked as **P143-1**: one field, and it is the field that makes this class readable.

---

## 3. The defect

`/api/events/typeahead`'s futures stage UNIONs several arms. One of them is the outcome-name
arm — "open markets having an outcome whose name contains the typed substring".

Production, `EXPLAIN (ANALYZE, BUFFERS)`, `q=yan`:

```
Aggregate                                            3,571.9 ms
  Bitmap Heap Scan futures_outcomes   rows=24,806    3,566.1 ms   hit=10,495 read=7,797
    Bitmap Index Scan
      ix_futures_outcomes_name_trgm   rows=31,006       57.5 ms   hit=1     read=135
```

The index does its job in 57 ms. The 3.5 s is the heap, and `futures_outcomes` is
**3,869,246 rows / 3,478 MB**. Joined to open markets the 24,806 rows collapse to **413
markets** — because only **55,138 of 914,497** markets are open. **97 % of the heap fetch is
thrown away.**

The same plan measured **282 ms warm and 6,115 ms cold** — a **22× cold/warm spread**, which is
why the same term is 0.8 s one minute and over the deadline the next. LAT-P063 had already
named the mechanism: the typeahead trigram surface is 688.6 MB against a 1 GiB `shared_buffers`
shared with every other query in the product, so its pages are evicted continuously.

And `win` is worse than `yan`, because `win` is inside `Winner`:

```
q=win    61,862 blocks    13,989 ms
```

The request deadline is 10 s. `win` cannot be served, ever, cold.

---

## 4. Two code-only cures, disproved on production

Both are recorded in `events.py` beside the constant, because the value of a disproof is
entirely in whether the next reader finds it.

**(a) Push the open-market filter below the heap fetch.** If Postgres could intersect the
trigram bitmap with a bitmap of "outcomes of open markets", the heap fetch would drop from
24,806 rows to the ~710 that survive. Rewritten four ways — `IN`-subquery, correlated `EXISTS`,
inner join, and an explicit `market_id IN (<open ids>)` — **the planner keeps the full
24,806-row Bitmap Heap Scan in every form** and hash-joins afterwards. It has no cheap bitmap
for membership of a 55,138-element set. Measured, not reasoned:

```
D_semijoin_inner   Bitmap Heap Scan futures_outcomes rows=24,806  18,424 blocks  7,399 ms
```

**(b) Narrow by id range.** `market_id >= :min_open_id` would be a sound, indexable narrowing
*if* open markets clustered at the high end of the id space. They do not:
**`min(id)` over open markets is `1`**, against `max(id)` 59,814,124. Dead.

These are why **P116-1** has been parked for five cycles behind a migration slot, and this queue
confirms that conclusion independently rather than overturning it.

---

## 5. What actually worked, and it was a surprise

Pulled out of the UNION and run as its own statement, the arm can carry the ordering the final
page applies anyway. That makes early termination profitable, and the planner stops
materialising the match set: it walks `futures_markets` in `(market_tier, volume)` order and
probes `futures_outcomes` per candidate until it has 20.

Same statement, `ORDER BY` + `LIMIT` the only difference:

| term | blocks OLD → NEW | time OLD → NEW | |
|---|---|---|---|
| `win` | 273,637 → **35,199** | 13,801 ms → **477 ms** | **29×** |
| `yan` | 47,819 → **30,476** | 5,771 ms → **520 ms** | **11×** |
| `cremonese` | 1,196 → **834** | 241 ms → **16.6 ms** | **14.5×** |
| `zzqx` (no match) | 15 → 18 | 6.6 ms → **0.25 ms** | |

🔴 **It does not trade the tail for the head.** The choice is cost-based, so on the rare terms
the planner *keeps* the bitmap plan and simply pays less for it — `cremonese` and `zzqx` still
show a Bitmap Heap Scan in the new plan. **No term measured got slower, in blocks or in time.**

### Why the rows are the same rows

The caller UNIONs every arm and takes the top `_TYPEAHEAD_FUTURES_POOL` of the union by
`(market_tier ASC NULLS LAST, volume DESC NULLS LAST)`. The arm now applies **that same ordering
and that same limit** to itself. Any market the arm drops therefore has
`_TYPEAHEAD_FUTURES_POOL` markets *from that same arm* ordered ahead of it, all of which are in
the union — so it could not have reached the union's top `_TYPEAHEAD_FUTURES_POOL` either. The
final page is identical.

That proof holds **only while the two limits are the same number**, so they are the same NAME,
and a mutant that turns either back into a literal is killed.

The pre-existing tie underdetermination is unchanged and deliberately not fixed:
`(market_tier, volume)` is not a total order, so which of a set of tied rows survives any cut is
already arbitrary. That is **P140-2**, it is a ranking change, and it does not ride a latency
queue — LAT-P002 was reverted for exactly that.

### The 2-second bound is the safety net, not the fix

The arm also gets its own `statement_timeout`, the smaller of 2,000 ms and whatever is left of
the request deadline. After the plan flip it should essentially never fire; it exists because a
planner choice is not a guarantee and statistics drift. When it does fire, **only this arm
sheds** — the dropdown keeps its market-name, ticker and alias futures instead of losing the
whole futures stage, and it loses them in 2 s instead of 10.

2,000 ms because the worst measured *healthy* cost after the flip is 520 ms, ~4× headroom.
LAT-P002 was reverted for a bound that fired on healthy queries.

---

## 6. D3, graded — LAT-P063's Option D read path

LAT-P063 built `typeahead_index`: one narrow searchable row per entity, so the working set fits
in the pool. Its docstring, and the model's, both say the same thing:

> NOTHING READS THIS TABLE YET… D3 says "> 350 MB ⇒ the sizing model is wrong; re-derive
> **before building the read path**", and D3 cannot be measured until the table exists and is
> populated in production. **The read path is the next queue, after D3 grades.**

The table has been live and populated since **2026-08-18**. **D3 had never been graded.** So the
declared next queue has been blocked for twelve days on a measurement nobody took. Taken here,
because it unblocks a named ship rather than because it is interesting:

| | measured | D3 bar |
|---|---|---|
| `typeahead_index` total | **169 MB** (101 MB heap + 68 MB index) | target < 200 MB, **HALT > 350 MB** |
| rows | 533,845 | sketch ~380k |

**D3 PASSES**, and passes the tighter target too, not merely the halt bar.

And the mechanism works. A full sequential scan of the table — no index on `search_text` exists
— measured on production:

```
q=yan         12,977 blocks   617 ms  (first touch, all 12,977 read from disk)
q=win         12,977 blocks   243 ms  (0 read — resident)
q=cremonese   12,977 blocks   211 ms  (0 read — resident)
```

**Constant blocks, constant time, and after the first touch the table is resident** — which is
Option D's entire thesis, confirmed. Against `win`'s 13,989 ms on the live surface that is
**56×**, and the constant cost is worth more than the ratio: LAT-P116's finding that "cost is
uncorrelated with anything the route can see beforehand" stops mattering when the cost does not
vary.

🔴 **But the read path is still not buildable, for two reasons neither of which was known, and
both of which are more useful than the grade.**

1. **The projection has no parent key.** `typeahead_index` rows for `futures_outcome` carry
   `entity_id` = the OUTCOME id. The arm needs the MARKET id. Recovering it means a PK lookup
   per match — 41,558 of them for `win` — which gives the cost straight back. A `market_id` (or
   generic parent-key) column is schema, and schema is a migration slot.
2. **The builder has never completed a pass over `futures_outcome`.** Source truth is
   **204,913** outcomes of open markets; the index holds **198,834** active (97.0 %). Worse than
   the 3 % gap, `refreshed_at` says **111,568 of those 198,834 rows — 56 % — have not been
   re-verified since 2026-08-18**, the initial build. The sentinel reports
   `terminal: 'failed'`. You cannot read from a second copy of truth whose own detector is red.

Both parked (**P143-3**, **P143-4**). The read path is closer than it was — its gate is green and
its mechanism is confirmed at 56× — and it now has a blocker list instead of an unmeasured halt.

---

## 7. What this ship does NOT do

* **It does not make the outcome arm cheap.** It makes the planner stop doing the expensive
  thing. The 3,478 MB trigram surface is untouched and **P116-1** is still the durable fix.
* **It does not fix `/api/futures`,** which threw a **35,979 ms** request at 00:05 PT (max query
  19,993 ms) immediately before a run of typeahead deadline blowouts. Contention is a plausible
  amplifier for this whole class and it is not measured. Parked **P143-5**, MEASUREMENT lane.
* **It changes no ranking.** The stable tiebreak that would make the top-20 deterministic is
  still P140-2, still unshipped, and still not a latency queue's call.

---

## 8. Parked

**P143-1** `unfinished_queries` is computed by `request_timing.py` and dropped by
`latency_stats.py` before it reaches the slow-event ring — which is why a statement-timeout
blowout reads as application time. One field; it is what makes this defect class legible.

**P143-2** `/api/events/{event_id}/related-futures` — 34 events over 5 s in 24 h, max 36,272 ms,
db-dominated, 13-17 queries per request. LAT-P136's surface, and the next candidate on the
ranking in §2.

**P143-3** `typeahead_index` needs a parent-key column before its read path can serve the
outcome arm. Schema ⇒ migration slot.

**P143-4** the `typeahead_index` builder has not completed a `futures_outcome` pass in twelve
days and its sentinel reports `terminal: 'failed'`. Blocks the read path independently of
P143-3, and it is a live correctness risk for a table that is about to be read.

**P143-5** the `/api/futures` 36 s request and the contention question. MEASUREMENT lane.

Carried unchanged: **P142-1**…**P142-4**, **P141-1**…**P141-6**, **P140-1** (`alex-inbox/latency-006`),
**P140-2**, **P140-3**, **P129-1**…**P129-5**, and **P116-1**, whose disproofs this queue added to
rather than resolved.

---

## 9. Contamination declared

* Organic `latency-stats` + `latency-slow-events` read **first**, before any probe (ruling 127).
* ~14 `db-query` `EXPLAIN ANALYZE` statements against `futures_outcomes`, `futures_markets` and
  `typeahead_index`. Read-only; they warm buffer pages, which is why every claim above is
  reported in **blocks** as well as milliseconds and why cold/warm pairs are labelled.
* 4 `/api/events/typeahead` requests with `X-Bainluck-Origin: harness` and `debug_timing=1`
  (no trending vote, no cache write in either direction).
* Sentry: 3 issue reads. No writes.
