# LAT-P137 — the census with no producer

**Ship:** opening Search stops making you wait a second and a half for the category grid.
**Pillar:** DISCOVER. **Branch:** `program/latency-123`, cut from `origin/master` `64b7a034`.
**Issue:** #1587 (the shared-cache family; this closes the producer half LAT-P122 named and did not take).
`migration_slot: none` · `beat_schedule_change: **TRUE**` · no config var · no DDL · backend only.

---

## 1. What was picked, and the four candidates that lost

The conveyor says: the highest-impact cold/slow **user-visible** path from my own audit ranking that
has no banked fix yet. Everything below was measured on production `fe5ec72c` on 2026-08-30 before
a line was written, first touch per member of the stated population, `x-timing-split` server time.

| candidate | measured (server) | population | verdict |
|---|---:|---|---|
| Discover cold build (`/api/feed?limit=20&event_pct=0.15`) | **11,155 ms** | 1 cold sample of 5 in the needle run | ❌ **not this cycle** — a prewarm rail already owns it and the sample is a rare uncovered expiry, not a standing cost. Parked P137-1 |
| `/api/events/{id}/game-markets` | p50 **595**, max 1,282 ms over 10 distinct events | event page | ❌ already cached (LAT-P121); what remains is one cold build per event, and there are dozens |
| `/api/leagues/{sport_key}` | p50 ~**200**, max 1,309 ms over **all 29** registered leagues | league pages | ❌ cached with a 24 h mirror; 15 of 29 built cold, none over 1.4 s. Parked P137-2 |
| `/api/futures/browse?category=X&limit=20` | p50 **112**, max 878 ms over 14 categories | Search → tap a tile | ❌ **and it corrects LAT-P136:** that cycle ruled `/api/futures/browse` out as having "no UI caller" after grepping `browseFutures`. The caller is `fetchFuturesBrowse`, in `CategoryBrowser`. The endpoint IS user-visible — the 5,305 ms P136 measured was the no-category shape, which nothing asks for. On the shape the product asks for it is fine |
| **`/api/futures/categories`** | **1,365 ms** then **2,775 ms** cold, 24-30 ms warm | Search landing, gates the whole grid | ✅ **shipped** |

Two of those losers are worth more than their row. `/api/futures/movers` at `limit=20` read
**1,991 ms** and is not in the table at all: shipped iOS asks `limit=10`, which LAT-P115 warmed, so
the slow number belongs to a shape no client requests. And `/api/feed/tag-counts` read **555-579 ms
with no cache of any kind** on both touches — it stays parked as P136-2 for the reason P136 parked
it, which this cycle re-checked rather than inherited: `/categories` is still not in the nav.

## 2. The finding

`GET /api/futures/categories` is the first thing `/search` asks for. `frontend/app/search/page.tsx:355`
renders `CategoryBrowser`; `components/CategoryBrowser.tsx:70` calls `fetchFuturesCategories()` on
mount; until it answers the page is eight pulsing skeletons.

LAT-P122 measured that census at 1,585.9 ms and 1,365.1 ms on two consecutive reads, found the cause
(39,014 shared blocks — ~305 MB of buffer traffic — to produce 42 rows, because the two negated
`ILIKE`s are unindexable), and gave the tier a shared Redis slot plus a 24 h age-bounded mirror.
**It gave the tier no producer.** Nothing on the fleet rebuilds the census; only a reader does.

So the cost did not go away, it became conditional — and the condition is one nobody watches:

```
fresh TTL              300 s      a reader gets `live`
stale serve ceiling  1,500 s      a reader gets the mirror in ~28 ms, one rebuild behind it
past 1,500 s                      the reader BLOCKS and rebuilds: 1,365 ms
```

Measured this session, production `fe5ec72c`:

```
00:41:37Z   wall=1365.4; db=1330.7; app=34.7;  q=1    <- mirror over the ceiling: a READER built it
00:50:08Z   wall=28.0;   db=0.0;    app=28.0;  q=0    <- created_at 00:41:37   live
00:50:11Z   wall=23.8;   db=0.0;    app=23.8;  q=0    <- created_at 00:41:37   live
01:03:20Z   wall=28.5;   db=0.0;    app=28.5;  q=0    <- created_at 00:50:11   stale_ok
01:13:20Z   wall=30.4;   db=0.0;    app=30.4;  q=0    <- created_at 01:03:27   stale_ok
01:38:44Z   wall=2775.4; db=2636.5; app=138.8; q=1    <- SEVENTEEN SECONDS past the ceiling
```

🔴 **THE LAST ROW IS THE MECHANISM, TIMED TO THE SECOND.** The previous build published at
`01:13:27`; `stale_serve_ceiling_seconds()` is 1,500 s, so the mirror stopped being servable at
`01:38:27`. A reader arriving at `01:38:44` — **17 seconds later** — blocked and rebuilt, and paid
**2,775 ms**, twice the first cold reading. Nothing about the endpoint changed between 01:13 and
01:38 except the clock. This is not a cold-start artifact, a deploy artifact or a tail sample: it is
the tier's designed behaviour with no producer behind it, and it is reproducible on demand by simply
not visiting `/search` for 25 minutes.

The three fast reads are the finding as much as the slow one: **one person paid 1.4 s so the next
few got 28 ms**, and nothing was scheduled to pay it instead of them. The 00:41 read establishes
that on this site the gap does open — the mirror was already past 1,500 s at the first probe of the
session, so no organic visitor had built the census in the preceding 25 minutes.

🔴 **THE OBSERVER RESETS THE CLOCK, AND THAT IS WHY THERE IS ONLY ONE COLD READING.** Every read of
this endpoint either serves the mirror and schedules a rebuild, or builds. Both republish. So
sampling "is it cold?" repeatedly is impossible: the second sample measures the first sample's
refresh. `created_at` above moves 00:41:37 → 00:50:11 across two of my own probes and nothing else.
A second cold observation costs 25 minutes of not touching it, and §6 records the one this session
had time to take.

## 3. The fix

`warm-futures-categories`: every 5 minutes, on `background`, calling
`routes.futures._rebuild_futures_categories` — the same zero-argument coroutine the route's own
serve-stale path dispatches. Same predicate, same payload, same keys, same TTLs. What changes is who
runs the scan.

🔴 **THE PERIOD IS DERIVED FROM THE TIER'S OWN CEILING, NOT CHOSEN.**
`warm_period_seconds() = stale_serve_ceiling_seconds() // (MISSED_DELIVERY_ALLOWANCE + 1)`.
A literal 300 beside a 1,500 in another file is exactly #2236 — a 120 in one place and a 60 in
another with nothing comparing them, leaving a payload uncovered for a full minute of every two.
The ceiling is a **freshness** contract (these counts are printed to the reader as "6,581" beside
Politics), so a later queue may well tighten it; when it does, this cadence follows it down instead
of quietly becoming too slow. The guard asserts the derivation, asserts that tightening the ceiling
tightens the period, and asserts the result is a whole number of minutes that divides an hour —
because the beat spells `*/N` and a seven-minute period would fire at :00…:56 and leave a
thirteen-minute hole that no assertion on the number alone would catch.

**Four missed deliveries, not one.** `background` is the queue LAT-P112 measured delivering p50
138-152 s against a declared 120 s. A period sized to survive exactly one late delivery is a period
sized to fail on that rail. Four is what the allowance buys at a 25-minute ceiling.

**A pass that published nothing reads `failed`, never green.** `write()` reports that a client took
the bytes, never that Redis kept them, so the task reads the census BACK and compares `created_at`
with what it saw before the build. `complete` requires a timestamp this run put there — the two
zeros a warmer confuses ("the build returned" vs "the next reader is covered") are different rows in
the summary. It is enrolled in `ENFORCED_TASKS` at birth (#1884), in the same change that gives it a
beat, because a warmer's failure is invisible from the surface it protects: the route answers 200
either way, just 1,365 ms instead of 28 ms, to whoever happens to arrive after the ceiling.

**What it does not do**, named so each is a decision: it does not make the statement faster (the
scan is still the scan, and no DDL is taken); it does not extend the mirror's serve ceiling (a
"latency fix" that served older counts would be shipping a formatting lie); it does not touch
`/api/feed/tag-counts`, whose futures half is the same predicate family with no cache at all — that
surface needs a cache before it needs a producer, and it is a different ship.

## 4. Gates — every exit code read by value (gotcha #54)

| gate | result |
|---|---|
| guards `test_futures_categories_warm_lat_p137.py` | **18 passed, exit 0** |
| red-first, pristine master `64b7a034` | **exit 2**, collection error — honest, uninformative |
| red-first, master + the module copied in | **2 failed / 16 passed, exit 1** — both wiring cells red |
| battery `futures_categories_warm_mutations` | **14/14 killed, 0 survived, 0 harness, exit 0** |
| siblings (wiring, beat budget, categories cache, movers warm, startup) | **136 passed, exit 0** |
| ruff, superset of changed files | **29 → 29**; the three new files contribute **zero** |
| `scan_mutation_residue.py` on the commit | **CLEAN, exit 0** (first run red — see §5) |
| full backend suite | recorded in the report |
| frontend gates | **NOT RUN — zero `frontend/`, zero `ios/` diff.** Stated, not fudged; CI runs both |

## 5. What went wrong, and what caught it

⚠️ **BATTERY MUTANT M7 SURVIVED THE FIRST RUN, AND THE SURVIVOR REWROTE THE TEST.** M7 narrows the
warmer's read guard to `except AssertionError`, and the test that claimed to cover it — an exploding
Redis client — went on passing. The reason is worth more than the mutant: the tier's `read()` goes
through `read_slot`, which is best-effort by construction and swallows a raising client itself, so
the client could never reach this module's guard. The test was proving the tier's swallow, not this
one. Per LAT-P115's rule the survivor is the finding: the test now drives `fcc.read` directly, and
the old assertion is KEPT as a second test that writes the boundary down, so a later change removing
the tier's swallow makes that one the test that notices.

⚠️ **PASS B OF THE RESIDUE SCAN WENT RED ON THE HARNESS'S OWN FILE.** M8's replacement is a
single-line literal (`await _rebuild_futures_categories()`), so its text appears verbatim in the
harness source, while its needle was spelled as a concatenation of escaped fragments and therefore
did not. Pass B's rule is `repl present AND needle absent` — which that arrangement satisfies. Fixed
by spelling the needle as a triple-quoted literal (the `game_markets_shared_cache:M4` shape) so both
halves appear in the file, **not** by narrowing the scan. The general rule for the next author: a
single-line replacement of 24+ characters needs its needle written contiguously.

⚠️ **THE FIRST RESIDUE SCAN WAS GREEN FOR THE WRONG REASON** — run on an uncommitted tree, Pass B
sweeps files changed vs `origin/master` and swept **zero**. LAT-P135 wrote that down, LAT-P136
re-learned it, and this cycle re-learned it again: the only residue scan worth quoting is the one
taken ON THE COMMIT.

## 6. Owed after deploy

This lane does not deploy, and nothing post-deploy is claimed. Three readings the deploy owes:

1. **`/api/futures/categories` after 25+ minutes of no traffic** — the reading that distinguishes
   "the warmer runs" from "the warmer covers the gap". Pre-deploy that read is 1,365 ms; post-deploy
   it must be 24-28 ms with `availability` `live` rather than `stale_ok`, and a `created_at` no
   older than one period.
2. **The task's own verdict** — `warm_futures_categories` in the task-metrics window, `terminal:
   complete` and a moving `created_at`. Enrolment means a run that published nothing is NOT green;
   the first 24 h of that series is the proof the read-back works.
3. **The `background` queue's arrival share**, unchanged. One 1.4 s build per 5 min is ~0.46 % of a
   slot-day and is declared on `BACKGROUND_BEAT_COUNT`; the read that matters is that it did not
   move the warmer contention LAT-P075 measured on that queue.
