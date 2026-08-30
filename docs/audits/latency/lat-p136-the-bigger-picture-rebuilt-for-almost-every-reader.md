# LAT-P136 — the Bigger Picture rebuilt for almost every reader

**Pillar: DISCOVER. Ship: tapping a game stops making you wait about six seconds for what the game
means for the season** (#1587, closing LAT-P127's parked **P127-2**) — the event detail page, the
third product priority, the surface Alex's pre-game ritual test is about.

Branch `program/latency-122`, **rebased onto `origin/master` `64b7a034`** (cut from `fe5ec72c`; see
the rebase note under Gates). `migration_slot: none`,
`beat_schedule_change: FALSE`, no config var, **no DDL**, backend only, **zero frontend files, zero
ios files**. Five files + this doc.

---

## The number, taken before anything was written

`GET /api/events/{id}/related-futures`, production `fe5ec72c`, 2026-08-29. **Ten DISTINCT events
taken off the live Discover feed**, first touch each, `x-timing-split` server time:

| | ms |
|---|---:|
| samples, sorted | 1,441 · 2,924 · 4,255 · 5,488 · 5,572 · 6,210 · 7,426 · 8,619 · 8,736 · 8,807 |
| **p50** | **5,891** |
| max | 8,807 |
| `db` share | **96–99 %** of every one |
| queries | 14–16 · `maxq` 639–7,641 ms |

🔴 **These are not tail samples.** Every one of them is the FIRST request for a game that was on the
Discover feed at that moment — which is exactly the request a person makes by tapping a card. The
sampling rule was "take the event ids the feed is serving right now, touch each once", chosen before
any number came back, precisely so the population could not be curated after the fact.

**The one-event read that would have been wrong.** Probing a single event id ten times in a row
returns 6–11 ms after the first call, and an early pass of exactly that shape read `10 ms / 2,949 ms
/ 9 ms` and looked like a flaky endpoint. It is not flaky and it is not warm: repeating one id is
measuring the cache this ship is about, not the experience it costs. **The population is events, not
requests.**

---

## Why a person pays it, and it is not the build

The tier's only cache was, in full:

```python
_related_futures_cache: dict[int, tuple[float, str, dict]] = {}
_RELATED_FUTURES_LIVE_TTL = 60
_RELATED_FUTURES_MAX_SIZE = 30
```

**A process-global dict of thirty entries** — the same shape LAT-P121 replaced for `/game-markets`
one door up the same file, and the shape P122-6 warned must be MEASURED rather than assumed. Three
properties, each independently a reason almost nobody gets a hit:

* **Per PROCESS.** `WEB_CONCURRENCY=2` puts two Uvicorn workers on every dyno and there is more than
  one dyno, so a warm entry is visible to a fraction of requests even for a game everyone is
  watching.
* **Thirty entries**, evicted oldest-first, for a site whose feed shows dozens of games at once.
* **It dies with the process** — every deploy, every dyno cycle.

And the part that actually costs the wait: **no mirror.** A miss had never had anything to serve
except a full rebuild.

🟢 **P122-6's rule was applied, not skipped.** That parked entry ruled `_event_detail_cache` OUT by
measurement — same defective shape, 13–35 ms cold, "converting this tier would ADD a round trip to
save ~15 ms" — and its general clause is *a cache with the defective SHAPE is not automatically a
cache with a user-visible COST.* So this tier was measured first and only then written. 13 ms is not
a ship; **5,891 ms is.**

---

## What changed

An L1 / L2 / mirror ladder over the shared `event_concept_cache` slot layout — **third customer of
`cache_keys`** after #1651 and LAT-P121:

```
L1   in-memory dict  — same process, same 60 s rule. KEPT: faster than a Redis
                       round trip, and it was never the defect.
L2   Redis primary   — SHARED across every worker and dyno. This is the ship.
L2s  Redis mirror    — served while young enough for the STATUS, with exactly
                       one rebuild scheduled behind it.
     build           — what every reader used to do.
```

### 🔴 The mirror's age ceiling is IMPORTED, not chosen

This payload carries `box_score`, `game_period`, `game_clock` and `event_status`. An over-old mirror
of a LIVE game is a formatting lie of exactly the kind the FORMATTING pillar exists to stop,
arriving through a latency fix.

The sibling tier **on the same page** already settled how old a mirror of a live game may be, and
its own docstring says two disagreeing ceilings in one route would be a coin flip about which one a
reader gets. So this tier does not pick a third number — `stale_serve_ceiling_seconds` delegates to
`game_markets_cache`. **The event detail page has ONE mirror-age law and both of its tiers obey it.**

That is deliberately not the same as sharing the fresh TTL, and the guard pins the difference in
both directions:

| | question it answers | this tier | sibling |
|---|---|---:|---:|
| mirror-age ceiling | how stale may a READER's copy be — a PAGE-level question | shared | shared |
| fresh TTL (live) | how often does this TIER rebuild | 60 s | 30 s |

60 s is `_RELATED_FUTURES_LIVE_TTL` carried across verbatim. **This ship changes who can see a
cached copy and what a miss costs — never how fresh the content is.**

### Two behaviours carried across rather than newly decided

* **The four `empty` exits are still not published.** The old dict was written only at the bottom of
  the build, so those exits have never been cached; the build now returns a `cacheable` flag and the
  policy honours it. Publishing them would make an event whose futures have not been ingested yet
  answer "no futures" for a TTL after they appear — **a content change smuggled inside a latency
  change.**
* **A rebuild behind a stale serve that comes back `empty` leaves the mirror alone**, the same rule
  a FAILED rebuild already followed. Degrade to slow, never to wrong.

### One behaviour CHANGED, and it is a bug fix

`debug=1` skipped the cache READ (`if not debug and event_id in _related_futures_cache`) but its
write at the bottom of the build was **unconditional** — so a debug call published a
`_debug`-carrying payload into the tier that normal readers then got, for up to a TTL. It now
bypasses in both directions, which is LAT-P050 / LAT-P054's rule for the typeahead cache applied
here. Found while writing the ladder, pinned by
`test_debug_bypasses_the_cache_in_BOTH_directions`.

### What is NOT done, named so it is a decision

* **The build is not made faster.** `maxq` ranged **639–7,641 ms** across the ten samples, so it is
  not one query on every event — which is a reason to size it per event shape rather than optimise
  the first plan that looks expensive (LAT-P128's own lesson, from the 21.9× optimisation of
  something nobody was waiting on). **Parked as P136-1.**
* **No warmer.** Serve-stale needs no schedule to fail (LAT-P116): the rebuild is triggered BY the
  request that would otherwise have paid for it.
* **No negative caching**, for the sibling's reason: a 404 here means the event id does not exist.

---

## Gates — every exit code read by value (gotcha #54)

| gate | result |
|---|---|
All of these are the re-run on the **REBASED** tree (`64b7a034`); the pre-rebase readings are not
quoted.

| gate | result |
|---|---|
| guards `test_related_futures_shared_cache_lat_p136.py` | **46 passed, exit 0** |
| red-first on unmodified master `64b7a034` (module copied in) | **12 failed / 34 passed, exit 1** |
| battery `related_futures_shared_cache_mutations` | **13/13 killed, 0 survived, 0 harness, exit 0** |
| LAT-P135's battery, re-run on this tree | **8 killed / 1 survived AS DECLARED / 0 not-applied, exit 0** |
| `test_mutation_guard.py` | **9 passed, exit 0** |
| `scan_mutation_residue.py` **on the commit** | **CLEAN, exit 0** — 302 needles, Pass B **5 changed files / 1,105 pairwise checks** |
| the twins `test_typeahead_fuzzy_index_lat_p135` + `test_search_latency_contract` + `test_game_markets_shared_cache` | **151 passed, exit 0** |
| smoke `tests/test_startup.py` | **4 passed, exit 0** |
| ruff, superset of changed files | **40 → 40** — three new files contribute **zero** findings |
| frontend gates | **NOT RUN LOCALLY — zero `frontend/` and zero `ios/` diff.** Stated, not fudged; CI runs both |
| full backend suite | see the READY token — run on the FINAL rebased tree |

⚠️ **THE BRANCH WAS REBASED MID-CYCLE AND EVERY GATE RE-RUN ON THE REBASED TREE.** Cut from
`fe5ec72c`; master advanced to `64b7a034` while the second full-suite run was in flight, and that
move merged **LAT-P135 — which edits BOTH files this ship shares with it**:
`app/routes/events.py` and `scripts/evals/scan_mutation_residue.py`. Different regions in both
(P135 edits the fuzzy fallback and `DISK_FREE`; this edits the related-futures tier ~5,000 lines
below, and `SHAPES`), and the rebase was conflict-free with both changes verifiably present
afterwards — `op("%")` still in `events.py`, `typeahead_fuzzy_index_mutations` still in `DISK_FREE`.
**The in-flight suite was KILLED, NOT QUOTED**, and P135's own battery and guard suite were re-run
on this tree rather than assumed. The ruff baseline moved 41 → 40 because P135's fix retired an
`F401`; the delta is still zero.

⚠️ **THE FIRST FULL SUITE RUN IS DISCARDED, AND ITS ONE FAILURE WAS MINE.** It came back
`1 failed / 22,675 passed` on `test_mutation_guard.py::test_no_mutant_is_sitting_in_a_harness_target_right_now`.
**It was NOT the cross-worktree `/tmp` artifact that fails 1-in-21,739 naming another worktree's
path** — and the availability of that excuse is exactly why the cause was read rather than assumed.
Pass B flagged **this branch's own harness** holding two literals that are
`game_markets_shared_cache_mutations`' M6 and M4 replacements byte-for-byte, with the sibling's
needles (which name `game_markets`) absent. The two harnesses guard the same ladder over two tiers,
so their natural spellings collide.

🔴 **AND THE PRE-COMMIT RESIDUE SCAN WAS GREEN FOR THE WRONG REASON.** Pass B sweeps files
**CHANGED vs `origin/master`**, so on an uncommitted tree it swept **zero** files and printed a clean
line over a scope that structurally could not contain the finding. **The only residue scan worth
quoting is the one taken ON THE COMMIT** — LAT-P135 wrote that down and this cycle re-learned it. The
line in the table above is that one; the earlier green is recorded here rather than deleted.

**The fix is not a workaround.** Pass B's premise is that a file holding replacement R also holds
needle N, which is what distinguishes a harness from a mutant somebody pasted; quoting the sibling's
needles here would satisfy the letter and destroy the premise. M1 drops the parentheses (identical
semantics, different bytes) and M4 deletes the `if` scaffolding outright rather than neutering it —
the better mutant anyway, and at 11 stripped characters it falls under `MIN_LITERAL` and is cleared
by Pass A instead. Battery re-run after the reshape: **13/13, exit 0.**

**Red-first, in two forms, because the first one is not a verdict.** Run against pristine master the
file exits **2** on a collection error — the module under test does not exist there, which is honest
but tells you nothing about the route. Copying the new module in and re-running isolates the ladder:
**12 failed / 34 passed**, every route-ladder cell red and every pure-module cell green. The second
form is the one quoted above; the first is recorded because `1` is a result and everything else is a
story about the harness.

---

## The survivor, and the check it bought

**Battery mutant M6 — "watermark over the season markets only, series and props drop out" —
SURVIVED the first run.** Not because the mutation was wrong, but because the claim it attacks lives
~900 lines into a function no unit test can execute without a database, so **every behavioural test
in the file patches the build and none of them could see it.**

Per LAT-P115's rule the survivor is the finding and the fix is the missing assertion, not a deleted
mutant. `test_the_BUILD_hands_back_all_three_market_id_lists` reads the function's own final
`return` out of the AST and asserts which names it hands over.

🔴 **`fn.body[-1]`, not `ast.walk(...)[-1]`** — walk is unordered *and* descends into the build's
several nested helpers, so "the last `Return` it yields" is an arbitrary one of theirs. The first
draft did exactly that and failed on an inner function's `return False`. **A substring test could
not have done this job either**: all three list names appear in the `_debug` block eight lines
above.

**M2 was reported as HARNESS, not counted as a kill,** on its first form: `    if not cacheable:`
appears twice (the route policy and the refresh-behind), and an anchor that matches twice is a
harness bug, never a verdict.

The battery carries **two targets in one table** — the route ladder and the policy module — because
the defect being pinned is that the two halves have to AGREE. A battery that could mutate only one
of them could not tell a broken ladder from a broken policy.

---

## Ruled out by measurement this cycle, banked so nobody re-derives them

🟢 **`/api/futures/browse` — the worst raw number of the day, and NOT a ship.** 5,305 ms wall on
`?limit=20`. It has **no caller in any component**: `browseFutures` exists in `frontend/lib/api.ts`
and nothing imports it. P122-2's parked "derive `has_more` from a `limit + 1` fetch" is also **partly
stale** — the double `COUNT(*)` it was written about is already gone, replaced by
`count(*) OVER ()` riding the sort's own scan.

🟢 **`/api/events?limit=20` reads 18,151 → 6,531 → ~950 ms and is not a user shape.** The only
caller, `/sports/[key]`, always passes `sport=<key>&days=14`; measured on that shape it is 129 ms
(nfl) / 300 ms (epl) / 2,213 ms cold, 382 ms warm (mlb). **A population the product never asks for
is not a latency finding.**

🟢 **`/api/futures/grouped-feed?limit=50` cold-builds in 8,552 ms — and `limit=50` is a key nobody
requests.** iOS pins `groupedFeedLimit = 20` and the prewarmer declares "the two real shapes". The
real shape is 9–17 ms.

🟢 **The `chi` typeahead cliff did not reproduce.** INT-155 measured `q=chi` at 10.27–10.30 s on five
consecutive passes — the `_TYPEAHEAD_DEADLINE_MS` wall firing every time, never caching. Re-measured
this cycle: **297 ms served, and 3,315 ms on a forced cold build with `futures_query` 3,154 ms of
it** — the known LAT-P096 un-indexed `to_tsvector` scan, which is **DDL and already banked**. The
permanent-cliff premise is not currently true; the ask in
`alex-inbox/latency-003` is unchanged and unaffected.

🟡 **`/api/feed/tag-counts` has NO cache at all** — 445–1,025 ms server-side on every call, and
`/categories` re-fetches it every 60 s via SWR while the tab is open. Its futures half is the same
predicate `futures_categories_cache` already caches for the twin surface. **Parked as P136-2, not
shipped**: `/categories` is not in the Browse nav (reachable only by breadcrumb from
`/categories/[slug]` and by direct URL), so a guaranteed ~700 ms on a low-traffic page loses to a
p50 5,891 ms on the event page. It is a small, clean fix for a cycle that has nothing bigger.

🟡 **`ncaa-basketball`'s grid warm ERRORS** — `QueryCanceledError: canceling statement due to
statement timeout` at 21.2 s in the 22:25 UTC precompute pass, on the `teams` query. The live page
serves in 45 ms today off an earlier successful warm, so no reader is currently hurt, but a warmer
that cannot complete is a cliff waiting for its cache to expire. **Parked as P136-3** — it belongs
with LAT-P131/P132's grid work, not inside a cycle about a different tier.

---

## What is owed after deploy

**Nothing post-deploy is claimed. This lane does not deploy.**

1. Re-run the ten-event first-touch sweep. **The FIRST touch of each event should be unchanged** —
   this ship does not make the build faster. **The SECOND touch, from a fresh principal, should fall
   from ~6 s to tens of milliseconds**, which is the whole ship, and it is the reading that
   distinguishes "the shared slot works" from "I got lucky with a worker".
2. Confirm the served body carries `cache.availability` and that a mirror read reports `stale_ok`.
   A payload with no envelope means the encode-before-store path is silently disabled —
   `write_payload` swallows its own failures.
3. **Confirm `debug=1` no longer publishes.** `GET .../related-futures?debug=1`, then a normal
   `GET`, then check the normal body has no `_debug`. One pair of calls.
4. Do not expect any charter row to move. This tier is not on the cold-path charter.

---

## The needle, and why this cycle publishes two reads

**`NEEDLE: latency 19 ms`** (was 18 ms at LAT-P135) — **and this ship cannot have moved it.** Nothing
was deployed; the slug is `fe5ec72c` on both reads, and `/api/events/{id}/related-futures` is not a
member of the needle pool at all.

🔴 **The first read of this session was 42 ms, and it is printed rather than dropped.** Taken at
23:41:57Z it read **42 ms**; a stability check three minutes later on the identical slug read
**19 ms**. The whole move is one member path:

| path | r1 (23:41:57Z) | r2 (23:45:09Z) |
|---|---:|---:|
| discover_native | 71 | 106 |
| discover_web | 20 | 19 |
| sports_native | 50 | 39 |
| sports_web | 17 | 13 |
| search_trending | 20 | 18 |
| **my_stuff_stats** | **42** | **14** |
| search_cold | 421 | 286 |
| **NEEDLE (median of 7)** | **42** | **19** |

`my_stuff_stats` is the pool's **only genuinely uncached member** (`/api/predictions/stats`, no
server cache, fires even signed out), and it sits at the median position. So the published number
tracks one DB-bound endpoint's minute-to-minute variance more than it tracks the product, and a
single read can be 2.2× another taken three minutes later on identical code. **Parked as P136-4**;
the metric changes only by Alex ruling, so this is a measurement note, not a change.

The second read is published as the close because it is the last one taken, not because it is the
lower one — the stability check was launched on seeing a 2.3× jump on undeployed code, before its
result was known.

`DIAG: latency-build` **REFUSED** on both reads — only 2 of 7 member paths went cold (floor 4) and
Discover open never did. A null is not a fast number, and per ruling 127 a DIAG refusal does not
suppress the NEEDLE.

Report: `.claude/handoff/REPORT-LAT-P136.md`
