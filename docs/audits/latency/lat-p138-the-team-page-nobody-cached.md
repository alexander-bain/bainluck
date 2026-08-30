# LAT-P138 — the team page nobody cached

**Cycle 76, 2026-08-29/30 PT. Pillar: DISCOVER. Issue #1249 (its follow-up half).**

**Ship:** tapping a team from search stops taking up to seventeen seconds to show its props.

---

## 1. The audit ranking, and what lost

Every number below is a FIRST TOUCH per path, production `64b7a034`, server time from
`x-timing-split`, one request each, paced to stay inside the 60/min limit. The population was
chosen before anything was measured: **the global Browse nav** — the destinations one tap from
every page — plus the surfaces the four highest product priorities name.

| candidate | measured | population | verdict |
|---|---:|---|---|
| the five hub pages (`mma` `boxing` `golf` `tennis` `esports`) | 24-83 ms, **q=0** | all 5 | ❌ warm, every one |
| politics · entertainment · economics | 21-29 ms, **q=0** | all 3 | ❌ the hourly precompute is doing its job |
| `/api/feed/tag-counts` | 386 ms, db=349, no cache | 1 | ❌ **P136-2, re-measured, still parked** — `/categories` is still not in the nav |
| `/api/calibration` | 180 ms | 1 | ❌ inside its 1h cache |
| `/api/events/search?q=` | 189-531 ms, db-dominated | 6 distinct terms | ❌ the largest needle member, but heavily worked (P118/P135) and the cold tail is unbounded by construction |
| `/api/events/{id}` · `/history` · `/game-markets` · `/team-progression` | 44 / 2,424 / 537 / 122 ms | 1 event, 4 paths | ❌ the 2.4 s chart is real and is **parked P138-1** |
| `/api/teams/{slug}` | 1,917 ms | 1 | ❌ real, and one twentieth of the ship below |
| **`/api/teams/{slug}/prop-families`** | **2,627-16,797 ms** | **7 teams** | ✅ **shipped** |

## 2. The finding

`/sport/{sport}/{league}/team/{team}` fires three requests on mount. The slowest is
`prop-families`, and it has no response cache of any kind:

| team | first touch | db | max single query |
|---|---:|---:|---:|
| kansas-city-chiefs | **16,797 ms** | 16,758 | 9,293 |
| boston-red-sox | 10,962 | 10,489 | 7,818 |
| los-angeles-dodgers | 9,448 | 9,280 | 6,220 |
| dallas-cowboys | 8,756 | 8,583 | 6,331 |
| new-york-yankees | 7,518 | 7,464 | 4,863 |
| los-angeles-lakers | 2,910 | 2,867 | 2,219 |
| boston-celtics | 2,627 | 2,564 | 1,584 |

🔴 **THE "WARM" READING IS BUFFER WARMING, NOT CACHING.** Three consecutive Chiefs reads:
**16,797 → 11,342 → 3,992 ms**. Nothing is stored between them; Postgres is keeping the GIN
posting lists resident and letting them go again. The fourth reader an hour later pays the first
number.

🔴 **AND THE COST IS 41 PROBES, 35 OF WHICH MATCH NOTHING.** `EXPLAIN (ANALYZE)` on the Chiefs'
own patterns, run through `db-query`:

```
fk branch            1.5 ms    Index Scan, 32 rows
outcome-name branch  13,107 ms BitmapOr of 41 Bitmap Index Scans, 96 rows
market-name branch    2,990 ms BitmapOr of 41 Bitmap Index Scans, 76 rows
```

Individual probes cost 14-883 ms each and **35 of the 41 returned zero rows**. The driver is
pattern count, and pattern count is the roster: 41 patterns 13.4 s, the same query's first 10
patterns 2.2 s. Only **367 of 9,625 teams have a roster at all**, so this is a bounded population,
and it is exactly the population a person searches for.

#1249 closed this endpoint's *timeout* in July (12.5 s → "<2 s warm, 3-4 s cold"). What it left is
the residual its own closing comment named — "the first-hit-per-team cold call is 3-4 s … a
per-team precompute would flatten the cold tail if desired" — and five weeks later that residual
reads 16.8 s.

## 3. The fix

**(a) `ILIKE ANY (ARRAY[...])` instead of an N-way `OR` of `ILIKE`.** The same predicate by
definition, and the same rows in measurement — 96 and 76 for the Chiefs on both spellings — but
Postgres plans it as one index scan with a ScalarArrayOp rather than a 41-way `BitmapOr`. Four
paired trials, interleaved so buffer warming could not pick the winner:

| | OR (today) | ANY (shipped) |
|---|---:|---:|
| outcome branch, round 1 | 8,201 ms | **4,821 ms** |
| outcome branch, round 2 | 7,019 | **4,759** |
| market branch, round 1 | 6,733 | **6,218** |
| market branch, round 2 | 4,831 | **1,837** |

⚠️ **THE CAVEAT, STATED RATHER THAN BURIED.** `db-query` takes no parameters, so both arms of that
table rendered their patterns as SQL LITERALS. The route BINDS them — as it already did for the
`OR` form — so both spellings depend on Postgres choosing a custom plan; a generic plan could not
use the trigram index for either. Production demonstrably chooses one today (the `OR` form's plan
IS the trigram BitmapOr above). The post-deploy first touch on this endpoint is the falsifier.

**(b) The cache tier the route never had.** Adopted, not invented: same
`utils/event_concept_cache` policy `routes/hub.py` adopted — 15-minute primary, 24 h mirror,
single-flight background revalidate, envelope stamped on the way out. Keyed on the **resolved team
id and the cap**, never on the URL identifier: slug, integer id and #1204's legacy slugs are three
spellings of one team, and keying on the identifier would give it three entries and leave the two a
producer did not warm permanently cold.

**A degraded build is never stored.** The statement-timeout path returns an empty `families` list,
and empty-because-it-timed-out is indistinguishable from empty-because-there-are-none once it is
bytes in Redis. It is served (an empty section beats a 500) and dropped.

**(c) A producer — `warm-prop-families`, `*/6h` at :43, `background`.** This is where the tier
departs from the hub's, and the hub module argues the opposite in as many words: no scheduled
warmer, because stale-while-revalidate keeps hubs warm off real traffic and a beat would race the
route's lock. LAT-P137 measured that assumption on a sibling tier and it did not hold — across 32
minutes every rebuild of `/api/futures/categories` was the measuring session's own probe. The two
arguments are reconciled by SIZE: a hub rebuild is 2.7 s at worst across five hubs; this is
2.6-16.8 s across 82. The race is closed by taking the SAME single-flight lock the route takes, so
a pass arriving while a reader's rebuild is in flight dispatches nothing for that team.

🔴 **THE PERIOD IS DERIVED, NOT CHOSEN.** The mirror is `STALE_TTL` (24 h) and the reader's cost
when it lapses is the whole table in §2, so the period is `STALE_TTL // 4` — three missed
deliveries of headroom on the `background` rail LAT-P112 measured at p50 138-152 s against a
declared 120 s. The guard asserts the DERIVATION, so tightening the mirror tightens the cadence
instead of leaving a literal behind in another file (#2236).

**The reachable set, declared:** teams with a non-empty roster AND a fixture in
`[-1d, +14d]` — **82 of 9,625** on 2026-08-30, hard-capped at 200 with the truncation REPORTED
(no silent caps). The 285 rostered teams with no near fixture keep the route's own
stale-while-revalidate; the 9,258 rosterless teams were never slow (one pattern, not 41).

**Not done, each a decision:** the trigram probes are not made individually cheaper (that wants a
GIN tsvector index — DDL, `CONCURRENTLY`, an attended psql session, gotcha #31); the 40-pattern
roster cap is not touched, and §6 records what it costs; `/api/teams/{slug}` itself (1,917 ms) is
not cached.

## 4. Gates — every exit code read by value (gotcha #54)

| gate | result |
|---|---|
| guards `test_prop_families_cache_lat_p138.py` | **37 passed, exit 0** |
| red-first, pristine master | **35 failed / 1 passed, exit 1** — the one pass is `_MAX_ROSTER_PATTERNS == 40`, an invariant master already holds |
| battery `prop_families_cache_mutations` | **23/23 killed, 0 survived, 0 harness, exit 0** |
| `test_mutation_guard.py` (incl. the residue scan) | **9 passed, exit 0** |
| siblings (wiring · beat budget · sweep cofire · prop-family contract · startup) | **177 passed, exit 0** |
| full backend suite | see §7 |
| frontend gates | **NOT RUN — zero `frontend/`, zero `ios/` diff.** Stated, not fudged; CI runs both |

## 5. Two things went wrong, and what caught each

⚠️ **THE FIRST RESIDUE SCAN WENT RED ON MY OWN HARNESS, TWICE OVER, AND BOTH ARE KNOWN CLASSES.**
`M6`'s needle was spelled as two implicitly-concatenated fragments, so its one-line replacement
appeared in the harness while the needle did not — Pass B's `repl present, needle absent` rule
exactly, which LAT-P135 wrote down and LAT-P136 and LAT-P137 each re-learned. And `M7`'s
replacement was `CACHE_PREFIX = "bainluck:event_concept:"`, which is
`game_markets_shared_cache_mutations:M13`'s replacement byte-for-byte — LAT-P136's finding,
arriving again. Fixed by spelling the needle and by re-targeting the collision namespace, **not**
by narrowing the scan.

⚠️ **A GUARD ASSERTED THE RENDERER'S ESCAPING, NOT THE ROUTE'S.** The LIKE-escaping guard read
`literal_binds`-rendered SQL, where `%` is doubled for the driver's paramstyle, so it was asserting
`%%100\\%%`. It now reads the BOUND VALUE. A guard that passes for a reason the code does not own
is a guard that will pass after the code stops being right.

⚠️ **MASTER MOVED MID-CYCLE.** The branch was cut from `64b7a034`; `origin/master` was `b7a7bbd0`
by the time the gates ran (LAT-P136 merged). Rebased, one conflict — LAT-P136 registered
`related_futures_shared_cache_mutations` at the same alphabetical position in the residue
scanner's `SHAPES`. Both entries kept, in sorted order. **Every gate quoted above was run on the
REBASED tree**; the pre-rebase runs are not quoted.

## 6. Parked, with evidence

* **P138-1 — the event page's chart costs 2.4 seconds.** `/api/events/{id}/history?hours=48` read
  **2,424 ms** (db 2,349, one query 2,260) on the first NFL event probed, against 44 ms for the
  event itself. Priority #3's own surface. One event is not a population — the measurement is the
  same first-touch sweep over ~10 events across leagues and horizons, plus which query dominates.
* **P138-2 — the 40-pattern roster cap silently drops the players people search for.** The Chiefs
  carry **65** roster names; `_MAX_ROSTER_PATTERNS` keeps the first 40 in roster order, which is
  alphabetical — so Mahomes, Kelce, Rice and Worthy are cut and Chukwuebuka Godrick is kept. This
  is a FORMATTING/TRUTH defect surfaced by a latency audit, not a latency defect, and raising the
  cap makes the endpoint slower. It wants the reverse index in P138-3, not a bigger number.
* **P138-3 — one corpus scan instead of 367 × 82 probes.** The whole cost here is per-team probing
  of a shared corpus. A background sweep that scans the prop-shaped population ONCE and matches it
  against every team's roster in memory would make all 9,625 teams instant, not just the 82 warmed
  ones. Sized, not built: `1.87M` outcome rows and `441K` markets in the base population,
  `~14,000` roster names across the 367 rostered teams.
* **P138-4 — is the bind-form plan the literal-form plan?** §3's caveat, as a measurement: the same
  A/B taken through the ROUTE (which binds) rather than through `db-query` (which cannot), first
  touch per team before and after deploy.

## 7. The needle

```
open   NEEDLE: latency 23 ms @ 2026-08-30T02:05:13Z    DIAG: REFUSED (2 of 7 members cold, floor 4)
```

The close is in the report. Nothing in this branch is deployed, and
`/api/teams/{slug}/prop-families` is **not a member of the needle pool** — no reading of the needle
can move because of this ship, in either direction, until it lands.
