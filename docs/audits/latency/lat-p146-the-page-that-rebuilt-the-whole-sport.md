# LAT-P146 — the page that rebuilt the whole sport

**Pillar:** FORMATTING / DISCOVER (the event-concept page — one tap from search).
**Ship:** *The US Open page stops taking twenty seconds, and its alias slug stops
returning an error page.*

Issue: **#2323**, filed this cycle, left open.

---

## 1. How it was found

The standing coldpath ranking, taken from `/api/admin/latency-slow-events?limit=500`
(the >5 s ring, 500/500 used, oldest 6.1 days, newest 57 min) on production
`944c466e`, 2026-08-30 11:29 UTC:

| n | p50 ms | max ms | Σ s | n(24h) | Σ s(24h) | path | banked fix? |
|--:|-------:|-------:|----:|-------:|---------:|------|---|
| 117 | 6,953 | 30,607 | 1,101 | 13 | 179 | `/api/feed` | LAT-P141 (`-126`) |
| 58 | 14,480 | 25,807 | 892 | 51 | 802 | `/api/playoffs/{league_slug}` | — but the ux stack holds `routes/playoffs.py` |
| 60 | 8,771 | 36,272 | 881 | 42 | 448 | `/api/events/{event_id}/related-futures` | LAT-P144 (`-129`) |
| 99 | 6,640 | 10,260 | 730 | 72 | 570 | `/api/events/typeahead` | LAT-P143 (`-128`) |
| **23** | **14,822** | **28,164** | **393** | **9** | **160** | **`/api/event/{key}`** | **— this queue** |
| 34 | 12,077 | 19,234 | 381 | 33 | 371 | `/api/teams/{identifier}/prop-families` | LAT-P145 (`-130`) |
| 31 | 9,369 | 20,033 | 340 | 0 | 0 | `/api/events/search` | LAT-P139/P140, **merged** — and the 24 h column is now zero |

`/api/playoffs` is still not this queue's subject and the reason is now
**measured** rather than assumed: `git merge-tree` against `origin/program/ux-122`
… `ux-131` shows `backend/app/routes/playoffs.py` **already conflicting with
master**, on every one of them. It stays parked as P145-5.

`/api/event/{key}` is the top un-banked path. It is also the only one in the
table whose worst case is not slowness but an **error page**.

## 2. The signature

The 23 slow requests are not one population. Read with the ring's own columns:

```
when (PT)              ms   db_ms  app_ms   q     maxq   router_q
08-29 06:25:01     14,100   9,315   4,786  56    5,635        1.9
08-29 06:25:01     14,104  10,465   3,639  56    4,783        3.0     <- same second
08-29 06:25:20     14,352  14,292      60   2   14,225        2.8     <- a DIFFERENT shape
08-29 06:25:20     14,501  14,267     233   2   14,195        1.5
08-29 21:43:14     17,509  14,153   3,356  54    6,891        1.6
08-29 21:43:41     27,108  23,623   3,485  54   16,627        2.4
08-29 21:43:58     16,199  12,904   3,295  54    9,027        2.4
08-29 21:44:27     28,103  24,906   3,197  54   16,292        2.3
08-26 01:26:03     13,804   9,638   4,165  63    7,866   19,769.6     <- the loop, queued
```

Three facts fall out of that table before any code is read.

**`q ≈ 52-63` is the tennis adapter.** 23,101 markets divided by SQLAlchemy's
500-id `selectinload` batch is 46 batched queries, plus the population scan and
the history join.

**They arrive in bursts.** Four requests inside 75 seconds on 08-29 21:43, two
pairs inside 20 seconds on 08-29 06:25, two in the same second on 08-27 11:28.
A cold build has no single-flight, so a burst pays the whole cost once per
reader.

**`router_queue_ms` reaches 19,769 ms.** The blast radius is not confined to this
route: a build holding the loop for 3-16 s of Python queues everything behind it.

## 3. Reproduced live

Every registered concept key that production search will emit, timed on
`944c466e`, 2026-08-30 11:0x UTC, with the route's own timing header:

```
event:awards:oscars                              0.37 s   q=0   (served warm)
event:cycling:vuelta-2026                        0.37 s   q=0   (served warm)
event:golf:the-masters                           0.60 s   q=0   (served warm)
event:soccer:world-cup-2026                      0.49 s   q=0   (served warm)
event:awards:grammys                             6.24 s   q=3   maxq=5,837
event:tennis:us-open-women-s-singles-winner     19.30 s   q=52  db=15,139  app=3,499  maxq=13,006
event:tennis:us-open-men-s-singles-winner       22.05 s   q=52  db=17,984  app=3,034  maxq=15,563
event:tennis:2026-men-s-us-open-winner-tennis   30.26 s   ⛔ H12 — Heroku's error page
```

The last line is the ship. The US Open is being played right now, it is one tap
from search, and **one of the two slugs search emits for it does not return a
page at all.**

The payload it is trying to build: 33 competitors and **1,307 children** (169
matchups by entrant, 1,138 props by token), 429 KB.

## 4. The mechanism, and what it is not

`TennisEventAdapter.build_event` asks for the whole sport:

```python
select(FuturesMarket)
  .options(selectinload(FuturesMarket.outcomes))
  .where(llm_sport_category == "tennis",
         or_(status == "open",
             and_(status.in_(("resolved","closed","settled")),
                  resolution_date >= now - 30 days)))
```

Measured on production, that population is:

| | rows |
|---|---:|
| markets | **23,101** |
| — of them open | 1,653 |
| — of them resolved in the last 30 days | 21,448 |
| outcomes loaded with them | **50,842** |
| markets actually rendered | 1,308 (1,307 children + the winner field) |

**About 94% of the load is never read.** And of the resolved arm, 21,361 of
21,378 are individual `X vs Y` match markets — a month of world tennis, ATP, WTA
and Challenger, fetched to answer a question about one draw.

`EXPLAIN (ANALYZE, BUFFERS)` on the population predicate:

```
Seq Scan on futures_markets
  rows emitted 23,101, Rows Removed by Filter 891,784
  Shared Hit 44,204  Read 81,933   (126,137 blocks)
  Shared I/O Read Time 7,275 ms
  Execution Time 8,399 ms
```

**This is not a missing `WHERE`.** It is a 1,664 MB table with no index covering
the predicate, and the fix is not available from inside the route:

* `ix_fm_open_category` — `btree (llm_sport_category) WHERE status = 'open'` —
  covers the OPEN half. **That arm alone measures 568 ms** (bitmap index scan,
  1,653 rows, 1,413 blocks).
* the RESOLVED half has no index, and the two plausible existing ones are
  **worse, and were measured rather than assumed**:

  ```
  resolved + name ILIKE '%winner%' OR '%champion%'   ->  21,124 ms
      BitmapOr over ix_futures_name_trgm: 63,325 candidate rows,
      then 33,756 heap blocks to filter them down to 2,374
  ```

  LAT-P116's clause holds here verbatim: a `pg_trgm` GIN scan's cost is set by
  the term's commonest trigram, not by its selectivity. `winner` is a common
  trigram.

An index on `(llm_sport_category, resolution_date) WHERE status <> 'open'` would
delete the scan. It is a `CREATE INDEX CONCURRENTLY` on a hot 1,664 MB table —
gotcha #31 and ruling 080 condition 2 make it an **Alex action**, and nine index
requests are already parked in
`MIGRATION-SLOT-REQUEST-LATENCY-2026-08-29.md`. **The lane does not take a slot.**
Appended there as **P146-1**, at the bottom, no answer needed this week.

## 5. What changed

Given the scan cannot be removed, what is fixed is **how often it is paid** and
**what is loaded alongside it**.

### 5.1 The arms are split, and only the slow one is shared

The resolved arm is identical for every tennis key — the same rows answer the US
Open, the women's draw and every alias slug — and it is the slowest-changing half
of the population, because a row only enters it when a market resolves. So it is
fetched once per `RESOLVED_TTL_SECONDS` (300) and shared, with a 24 h mirror
behind it.

The OPEN arm — the live half, where a new match appears and a status flips — is
**read fresh on every build**, off its own index, for 568 ms.

Two properties make the shared half safe, and both are pinned by guards and
attacked by mutants:

* **Strict superset, never a substitute for the predicate.** The cached query
  widens the window by `CUTOFF_SLACK_SECONDS` (the 24 h mirror + 1 h), and the
  caller's exact `resolution_date >= cutoff` is re-applied in Python on every
  read. A stale cache can therefore only ever be MISSING a row that resolved in
  the last few minutes; it can never serve a row that has aged out. **The two
  failure directions are not symmetric and only one of them is admitted.**
* **Identity only.** The cached rows carry id, name, status, `resolution_date`,
  `group_id`, source and volume. **No price and no grade is ever read from
  them** — every outcome is loaded from the database in the request that renders
  it.

Cost of the shared half, measured on a synthetic 21,378-row payload of the real
shape: **3.06 MB**, orjson decode 7.6 ms, row construction 6.2 ms, window filter
0.3 ms — **14.1 ms** plus one Redis round trip, against 8,399-15,563 ms.

### 5.1a The store was measured, and it changed the layout

The first draft copied the envelope tier's slot layout — a short-TTL primary and
a 24 h mirror, the same bytes in both. Then the store itself was measured rather
than assumed:

```
$ heroku redis:info --app bainluck
Plan:              Premium 1
Maxmemory:         100 MB
Maxmemory Policy:  allkeys-lru
```

**One instance, 100 MB, `allkeys-lru`, and it is the same instance the Celery
broker runs on.** Two copies of a 3.06 MB payload is **6.1% of the whole store**,
evicted against everything else in it. A latency fix that quietly starts evicting
queue keys is not a latency fix.

So the two slots are split by ROLE instead of by copy: the payload lives **once**
under the 24 h TTL, and freshness is a separate marker holding one byte. Marker
present → serve; marker gone, payload present → serve and refresh behind it.
Exactly the same three states, half the memory, and one state fewer to go wrong —
the two copies can no longer disagree, because there are not two copies.

Then compressed. zlib level 1, measured on the same fixture: **3.06 MB → 1.13 MB
(36.8%), 14 ms to compress, 2.2 ms to decompress.** Level 6 buys three more
percentage points for three times the compress time, which is the wrong trade for
a value written by a background refresh and read on a page build. Real market
names repeat far more than that fixture's random ones did — the same players
appear across hundreds of match markets — so 36.8% is the pessimistic figure.

**6.12 MB → 1.13 MB: from 6.1% of the store to 1.1%.** A payload written by an
older build with no compression header still reads, so the deploy that changes
the encoding does not hand the scan back to every tennis key at once.

### 5.2 A TTL expiry serves the mirror

Sharing on a 300 s TTL still leaves **one reader every five minutes** paying the
whole scan, and a plain TTL expiry is the overwhelmingly common cache event.
LAT-P021 settled this for the envelope one layer up. Same shape here: a miss with
a mirror serves the mirror and puts exactly one rebuild behind it, single-flight
across the fleet via `serve_stale_and_refresh`'s shared Redis lock — reused from
`event_concept_cache` rather than copied, because ruling 005 makes that module
the policy home and LAT-P121 already found a route-local copy being ignored forty
lines from the tier that needed it.

The mirror is served **only when a rebuild actually started**. When nothing can
run behind it the code falls through to the synchronous scan, because serving a
mirror with nothing behind it is serve-stale-forever.

### 5.3 Outcomes are loaded for what is rendered

Association reads a NAME or a `group_id` — `market_in_event`, the container
inheritance and `shares_tournament` all do — so the children are identified
before a price is needed. Two loads replace 46:

* the winner CANDIDATES, via `winner_candidate_ids`;
* the ASSOCIATED CHILDREN, in one query.

Measured on production for the real US Open child set (1,308 ids):

```
Bitmap Heap Scan on futures_outcomes using ix_futures_outcomes_market_id
  3,492 rows, 1,945 blocks, Execution Time 300 ms
```

**300 ms for 3,492 rows**, against ~2,400 ms of batched queries for 50,842.

`winner_candidate_ids` is a **superset by construction**: `select_winner_field`
calls its count callable in exactly two places, both behind the same name-only
tests, so the ids it can reach are knowable before an outcome is loaded.
`select_winner_field` itself is **untouched** — it is #1793's identity function
and rewriting it to fit a latency fix is the trade its own docstring forbids.

## 6. What a reader gets

Every component below is production-measured; the totals are the sum of measured
parts, and are labelled as such rather than as a post-deploy read.

| | before | after (shared arm warm) |
|---|---:|---:|
| population, resolved arm | 8,399-15,563 ms **every build** | ~16 ms unpack + one Redis GET |
| population, open arm | (inside the scan above) | 568 ms |
| outcomes | ~2,400 ms, ~46 queries, 50,842 rows | **300 ms**, 1 query, 3,492 rows |
| queries | **52** | **4** |
| measured route wall | **21,018 ms** (30,260 ms on the alias) | — |

And the frequency changes, which is the part that matters:

* **before** — every cold build of every tennis key pays the scan. The ring's
  bursts are four of them inside 75 seconds.
* **after** — the scan is paid **once, by whoever builds a tennis page first**.
  After that a background task pays it, with nobody waiting.

**The first build after a cold Redis is NOT fixed**, and that is the honest
statement of this ship's edge: it still costs the scan. The thing that removes it
is P146-1, the index, and the lane does not hold a slot.

## 6a. What it costs the store

| | |
|---|---:|
| Redis plan | premium-1, **100 MB**, `allkeys-lru`, shared with the Celery broker |
| encoded population | 3.06 MB |
| first draft (two slots, uncompressed) | 6.12 MB — **6.1% of the store** |
| shipped (one slot, zlib L1) | **1.13 MB — 1.1%** |

## 7. Three findings the gates produced

**The collision was measured, not assumed, and it changed the design.**
`program/ux-123` … `program/ux-127` all carry live `ready` tokens touching
`app/utils/event_tennis.py`, and ux-127 adds three tests to
`tests/integration/test_route_event_concept.py` that seed the adapter with
`mock_db.execute.return_value = _query_result([...])`. LAT-P145 declined a target
on this basis without measuring it; this cycle measured it both ways:

* `git merge-tree HEAD <branch>` — `event_tennis.py` **auto-merges cleanly**
  against all five, and every conflict those branches have (`routes/playoffs.py`,
  `FeedCard.tsx`) is **pre-existing against master** and identical from
  `944c466e`;
* the SEMANTIC half, which a merge-tree cannot see: the three-way merged
  `event_tennis.py` and the three-way merged test file were built in a scratch
  worktree and the tennis suites run against them — **178 passed**, with ux-127's
  three new tests individually confirmed to have RUN rather than skipped.

That gate is what forced the row reader to read its columns **by name** and made
`attach_outcomes` refuse to empty a market that already holds outcomes. Both are
independently correct — `event_concept_population`'s own docstring says a
projection that disagrees with the row loop it feeds silently mis-assigns
columns — and together they meant **not one line of an existing test file
changed**.

**The store is a resource and it had not been measured.** The layout this ship
copied from the tier above it would have taken 6% of a 100 MB LRU store shared
with the task broker — a latency fix that starts evicting queue keys. Found by
running `heroku redis:info` before believing the design, and it cost one
redesign and five more mutants. The general clause: **a cache's SIZE is part of
its contract, and the store's capacity is a measurement, not an assumption.**

**M19 survived the battery's first run and the survivor was the finding.**
Dropping the exact-slug arm from `winner_candidate_ids` changed nothing any
assertion could see, because every exact-slug market in the fixture corpus was
also reachable by the subset arm. The case that separates them is a market whose
name is entirely stopwords: `canonical_tokens("Men's Singles Winner")` is the
empty set, so no slug reaches it by subset and only its own exact slug can.
Search emits `event:tennis:{clean_slug(name)}` for any winner market, so that key
is reachable in production, and a prefetch that lost it would have resolved the
page on zero competitors. Fixed by adding the market and the assertion, not by
deleting the mutant.

## 8. Parked

* **P146-1** — the resolved-arm index. → `MIGRATION-SLOT-REQUEST-LATENCY-2026-08-29.md`.
* **P146-2** — tennis is absent from the event-concept warmer's population
  (`event_concept_population.CONCEPT_SOURCES` is ufc, f1, cycling), so no
  background pass ever pays this build on a reader's behalf, and — the same
  mechanism as #1948 — a tennis concept has no `leader`, which is the suppress
  state on both surfaces. It only becomes affordable once the build is cheap,
  which is what this ship does. → `PARKED-MEASUREMENTS.md`.
* **P146-3** — the envelope is cached under the REQUESTED slug, not the canonical
  one. `event:tennis:us-open-men-s-singles-winner` and
  `event:tennis:2026-men-s-us-open-winner-tennis` are the same tournament and
  each holds its own 429 KB payload and pays its own build. The built envelope
  already carries the canonical key, so an alias→canonical pointer written after
  the first build would collapse them. → `PARKED-MEASUREMENTS.md`.
* **P146-4** — `event:awards:grammys` is a different shape entirely: 6.2 s at
  `q=3` with a single 5,837 ms query, and the ring holds two `q=2` requests at
  14.2 s whose one query is 14,225 ms. Not diagnosed this cycle. →
  `PARKED-MEASUREMENTS.md`.
* **P146-5** — `/api/event/{key}`'s cold path has no single-flight (step 4 of
  `routes/event.py`), which is why the ring holds same-second duplicates. This
  ship removes most of the cost behind that gap rather than closing it; closing
  it means deciding what the second reader gets while the first builds, and that
  is a product question, not a latency one.
