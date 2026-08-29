# LAT-P115 — the strip nobody warmed, and the two candidates that were disproved first

**Cycle 87 · 2026-08-28/29 PDT · identity `LAT-P115-20260828-w37753` · branch
`program/latency-100`**

Ran from Fable's runner directive
(`.claude/handoff/runner-inbox/latency/020-coldpath-conveyor.md`), staged under Alex's
standing authorization. Lane lock claimed via `scripts/claim_lane_lock.py` — **exit 0,
prior owner explicitly RELEASED, no takeover and no MALFORMED repair.**

---

## 1. What shipped

**The iOS Futures tab's "Biggest Movers" strip stops being cold on essentially every
open** (#2270).

`FuturesListView.swift:51` calls `loadMovers()` on appear, which issues
`GET /api/futures/movers?hours=24&limit=10`. The route caches for **60 s** and there is
**no warmer**. On a site with no steady traffic the window is almost always expired, so
the strip is cold nearly every time anyone opens the tab.

Measured on production slug `b8ee7e14`, 2026-08-29 — two independent cold hits about ten
minutes apart, each followed by warm reads inside the minute:

```
/api/futures/movers?hours=24&limit=10   srv=1404 ms   <- cold
/api/futures/movers?limit=10            srv=  20 ms   <- warm
... four further paired passes           srv=16-24 ms
```

LAT-P108 (#2254) took the cold build from 11,129 ms to sub-second. **What it left behind
is that almost nobody gets the warm read** — it fixed the build and never gave it a
producer.

### Where the cold second actually goes

`EXPLAIN (ANALYZE, BUFFERS)` on the emitted statement, production, same day:

```
Limit                                    1,421.6 ms
  Sort                                   1,421.6 ms
    Nested Loop                          1,416.0 ms
      Nested Loop                          772.9 ms
        Aggregate                          763.9 ms
          Limit                            761.9 ms
            Sort                           761.9 ms
              Index Scan futures_markets   704.8 ms   rows=30,133  blocks=30,048
      Index Scan futures_outcomes            1.6 ms   loops=400
```

**54 % of the request is choosing the pool.** `ORDER BY max_movement_24h DESC LIMIT 400`
has no index to walk, so every open/active market with a non-null `max_movement_24h` —
30,133 rows, one heap block each — is read and sorted to keep 400. That is exactly the
scaling LAT-P108's own note recorded when it measured pool 200 → 627 ms and
2500 → 2,833 ms; the pool sort was always the residual, and this is the first cycle to
put a number on it.

### The fix, and why it is the producer and not a new beat

`update_max_movement` already runs every 10 minutes and already computes
`MAX(ABS(probability_change_24h))` per market — **it is the task that decides this
ranking.** The answer cannot change faster than its own input, so the producer publishes
it now, as its last act, after the commit and inside its own guard.

Riding an existing beat means **no new beat entry**: the two ledger constants
(`BACKGROUND_INTERVAL_FLOOR`, `BACKGROUND_BEAT_COUNT`) that have conflicted on several
consecutive integration cycles are untouched, and `beat_schedule_change` is FALSE. No
config var, no DDL, no route behaviour change.

🔴 **A separate 40 s `realtime` beat was the other candidate and was refused with its
reason.** LAT-P112 measured `background` delivering p50 138-152 s against a declared
120 s (max 2,511 s) while `realtime` held p50 40 s against a declared 40 s — so a
punctual rail exists. It is refused because the payload is only as fresh as
`update_max_movement`, which is itself on `background` every 10 minutes: a 40 s warmer
would rebuild identical bytes ~15 times per change and put a 762 ms pool sort on the
realtime queue to do it. Riding the producer costs one build per change, which is the
number of builds the data justifies.

### The extraction is the point, not a tidy-up

`build_and_cache_movers` and `movers_cache_key` were **extracted** from the route body
rather than re-implemented in the warmer. A warmed payload that differs from the served
one by a single key is a wrong answer served fast, to the only client that exists, with
the cache hiding it. `timeframe_hours` alone is strip-unsafe in shipped iOS
(`Models/SearchModels.swift:146` types it non-optional) — a second copy of that dict is
one refactor away from omitting it and throwing on decode for every build in the wild.

A side effect worth naming: the inlined version referenced `redis` at write time even
when `get_redis_client()` had raised, so a Redis outage produced a `NameError` swallowed
by its own bare `except`. The extracted form passes `None` and skips the write.

### Deliberately NOT taken

`CREATE INDEX ON futures_markets (max_movement_24h DESC) WHERE status IN
('open','active')` is the permanent form and would take the 762 ms to roughly nothing.
It is DDL, the slot is integrator-owned (ruling 080), and this lane has parked three such
requests already (P109-1, P110-1, P111-1). **REQUESTED on #2270 and parked as P115-1, not
taken.** Parking a fourth index is not a ship, so this queue shipped the half it owns.

---

## 2. Two candidates were disproved before this one, and the disproofs are the finding

The directive says take the next cold-path win. The instrument named cold search for the
third cycle running, and the board named a dead endpoint. Both were run down and both
were refused — with reasons, not with silence.

### 2a. Cold search: real, and it belonged to an unmerged branch

The opening needle put `search_cold` at **399.5 ms against 12.0 ms** for the only other
member that went cold — 33×, and the slowest member for the third consecutive cycle.
Per-stage attribution over eight fresh obscure terms (`?debug_timing=1`, which bypasses
the cache in both directions) put it in the `futures` stage on **8 of 8**, 64-74 % of
server time:

```
kaiserslautern  srv=242 ms  futures=171     randers     srv=413 ms  futures=306
sanfrecce       srv=129 ms  futures= 81     heidenheim  srv=382 ms  futures=290
empoli          srv=112 ms  futures= 78     elfsborg    srv=209 ms  futures=113
bochum          srv=116 ms  futures= 76     cagliari    srv=964 ms  futures=687
```

`EXPLAIN (ANALYZE, BUFFERS)` on the `randers` window query found the outcome arm costing
**220 ms of 274 ms to contribute two markets**:

```
Bitmap Index Scan ix_futures_outcomes_name_trgm  210.2 ms  rows=170  blocks=1,850
Bitmap Index Scan ix_futures_name_trgm            51.5 ms  rows=304  blocks=  338
```

🔴 **That arm is LAT-P111's, unmerged on `-96` at the time.** Its skip fires when the
tier≤1 arms fill a 20-row window — measured per term on production: `cagliari` **61**
name-arm rows (skip fires), `randers` **15** and `empoli` **17** (it does not). So the
finding is real and partially uncovered, but building on it meant re-doing LAT-P111
inside a second branch claiming the same surface. **Refused for the same reason LAT-P114
refused P113-1: contention, not merit.**

🔴 **And the GIN sawtooth was checked rather than assumed.** LAT-P109's flush beat is
firing — 69 successes/24 h, terminal `complete`, 7/7 indexes — so the 210 ms is largely
genuine tree cost, not a pending list. Worth recording: the last pass still cleaned
**198 pages** off `ix_futures_outcomes_name_trgm`, against a task whose own docstring
names `pages_cleaned = 0` as the steady state it is trying to reach.

### 2b. `/api/events/search/trending` returns `[]` — and it is RIGHT to

The route sweep found `/api/events/search/trending` returning **15 bytes**,
`{"trending":[]}`, with real consumers on both platforms: web hides the whole block
(`SearchBar.tsx:394`), iOS falls back to "Explore" instead of "Trending"
(`SearchView.swift:357`). It looked exactly like LAT-P114's dead-Categories-page ship, and
the handler has two nested `except → []`, which is gotcha #53's shape — an error and "no
traffic" are the same response.

The obvious fix is a fallback to `db:search_query_logs:30d`, the source `resolve_head`
already blends. **The measurement killed it.** 449 rows in the last 24 h, newest four
minutes old — and every one of them is a harness probe:

```
cremonese 42 · sandhagen 40 · osasuna 40 · brentford 39 · zeltweg 39 · pyrenees 39
kaiserslautern 23 · randers 20 · sanfrecce 19 · empoli 19 · bochum 18 · heidenheim 17
```

The second row is **this session's own attribution probe**, timestamped 03:45. There is no
human search traffic at all, so the empty window is honest, and a 30-day fallback would
have shipped **"Trending: kaiserslautern, randers, empoli"** to users — worse than blank,
on a surface that currently degrades gracefully. Disproved, not deferred.

🔴 **A real finding fell out of it: `debug_timing=1` suppresses the trending zset vote but
NOT the `search_query_logs` write.** The contamination budget of #1866 / LAT-P097-P098
covers one of the two sinks. Every measurement probe this lane runs — including the
needle's own — is polluting the 30-day log that `resolve_head` blends 24 of 40 head slots
from. Parked P115-2; it is a measurement-integrity fix, not a user-visible ship.

---

## 3. Gates

| Gate | Result |
|---|---|
| Full suite | **21,211 passed / 0 failed** / 124 skipped / 61 xfailed, ONE run (854.73 s), **exit code 0 read by VALUE** |
| `--collect-only` | master **21,380 → 21,396 (+16, exact)**, measured on BOTH sides |
| Mutation battery | **7/7 killed**, exit 0 |
| Residue scan | **CLEAN**, exit 0, 155 needles, 714 broad checks |
| ruff | **ZERO NEW** — finding set byte-identical to master's own copy, diffed not counted |
| black | new files formatted; pre-existing files untouched (master's copies are not black-clean) |
| Smoke (`test_startup.py`) | 4 passed |

### 3.1 The suite

**21,211 passed · 0 failed · 124 skipped · 61 xfailed · 854.73 s · ONE run · EXIT CODE 0,
read by VALUE** (gotcha #54 — `1` is a result, everything else is a story about the
harness), on code tree `ef4cfc90`.

It reconciles with the collect exactly: **21,211 + 124 + 61 = 21,396 = collected**.

An earlier run of the same suite was **stopped at 8 % on purpose**. It had been launched
before the rebase, so it was measuring a tree built on `b8ee7e14` — not the tree this
branch ships. Letting it finish would have produced a real, green, irrelevant number, and
quoting it would have been a gate proving something about a commit that was never pushed.
It was re-taken rather than reported.

### 3.2 M7 SURVIVED the first battery, and the survivor WAS the finding

Six of seven mutants died on the first run. **M7 — `PER_SHAPE_TIMEOUT_SECONDS` raised from
30 to 100,000 — survived**, because nothing in the guard file pinned the inner-operation
bound to anything at all. That is not theoretical: `update_max_movement` carries
`soft_time_limit=120`, and a warm that can outlast it converts a slow cache write into a
SIGKILL of the column update — recorded as `no_data` rather than as a failure, so the task
that maintains `max_movement_24h` would stop running and nothing would say so.

Repaired by adding the missing assertion, which reads the caller's budget **off the task
object** rather than writing 120 down a second time. 7/7 on re-run. The mutant was not
deleted and the bound was not loosened.

### 3.3 A genuinely RED guard, and the gate was right

LAT-P108's `test_the_route_actually_uses_the_builder_and_the_clamp` went red on the first
run: it asserts the route body names `_build_movers_query(`, and the extraction moved that
call one hop down into `build_and_cache_movers`. **The intent — "a helper-only guard stays
green when the caller stops calling it" — is exactly right and still needed.** It was
repaired by following the indirection (the route must call the builder, the builder must
use the pooled arm, and the clamp must still precede the key mint), not by dropping the
assertion.

### 3.4 The residue scan's first CLEAN was a narrowed denominator

The first default-mode run printed `✅ CLEAN` — over **`78 literals x 0 files` and 0
pairwise checks**, because the scan diffs *committed* changes against `origin/master` and
mine were still in the working tree. The scanner's own docstring refuses exactly this
("never let a narrowed denominator print as a full one") and it caught itself. Re-run
after committing: 7 files, 546 checks, then 714 after the rebase. **The `✅` was not the
evidence; the file count was.**

### 3.5 `--all-tracked` is red on master, and identically so on this branch

`scan_mutation_residue.py --all-tracked` exits **1** with 4 residue candidates and 2
harness drifts. Every one of them reproduces on a clean `origin/master` worktree, byte for
byte — so this branch introduces none. Needle count 106 → 113 (+7, exactly this cycle's
mutants) and targets 12 → 13 (+1). Recorded because recent cycles have reported "residue
scan clean" from the default mode, which examines only changed files; the whole-tree mode
has a standing red that nobody owns. Parked P115-3.

---

## 4. Ordering — master moved under this branch, and the check caught it

🔴 **All five open latency branches merged DURING this session.** `origin/master` went
**`b8ee7e14` → `606bd84b`**, and `-95`/`-96`/`-97`/`-98`/`-99` are all confirmed ancestors
— verified with `git fetch` + `merge-base --is-ancestor` per branch at close, not assumed.
**`program/latency-100` is now the only unmerged latency branch.**

It was caught the hard way, which is worth writing down. The pairwise ordering table
against the five branches returned **exit 1, different trees in both orders, for `-95`
only** — a real conflict, and the other four exiting 0 with identical trees proved the
harness was working rather than word-splitting (the failure that bit two consecutive
cycles). Chasing that conflict is what surfaced the merge base of `origin/master` and
`-95` being `-95`'s own head — i.e. it had already landed. **The opening ancestry read,
taken ninety minutes earlier, said all five were open, and it was simply out of date.**
Thirteenth cycle in this lane where re-deriving at close was the difference.

The branch was **rebased onto `606bd84b`**, resolving one conflict in
`scan_mutation_residue.py`'s `SHAPES` dict by **keeping both sides**. The new entry was
placed at its alphabetical position rather than at the head of the dict: six consecutive
latency branches have now collided on the two lines directly under
`admin_auth_gate_mutations`, because that is where an append lands when nobody looks.

Rebase fidelity was verified rather than trusted — the per-file diffstat before and after
is identical except `scan_mutation_residue.py` (1 → 6 lines, the extra five being the
comment explaining the placement). Pre-rebase head `be1ab0a7` was anchored on a named
branch first (gotcha #154).

**Final state:** `program/latency-100` @ (head at close), base `origin/master` @
`606bd84b`. merge-tree exit **0**, tree **`74974a9a`**, 0 conflicts; HEAD **not** an
ancestor. `migration_slot: none` · `beat_schedule_change: FALSE` · no config var · no DDL
· backend only.

---

## 5. What the needle says, and what it cannot say

**Opening read: REFUSED** — 2 of 7 member paths cold against a floor of 4, 2 of 3
surfaces (missing Discover open), on slug `b8ee7e14`. The same five paths
(`discover_native`, `discover_web`, `sports_native`, `sports_web`, `search_trending`)
produced no cold sample, for the same structural reason P114-3 recorded: **they are warm,
because the warmer rail works, and the needle discards warm samples by construction.**
Seventh-ish consecutive refusal; a fifth data point on Alex's open DECIDE.

🔴 **This ship is one the needle cannot see, and the reason is precise rather than
convenient.** `/api/futures/movers` is not in the needle's declared pool at all — the pool
is seven frozen member paths and this is not one of them. So the correct bar for this ship
is not a needle delta but the endpoint's own cold/warm split after deploy: the strip
should stop producing a ~1.4 s cold read at all, because the 60 s window it currently
misses is replaced by a 30-minute one the producer refreshes every 10.

### 5.1 The closing read — and why it is NOT a series with the opening one

**NEEDLE: latency 24 ms @ 2026-08-29T04:11:44Z** — 7/7 member paths served, slug
`b8ee7e14`, uptime 4,399 s. `DIAG: latency-build REFUSED` (2 of 7 cold, floor 4).

🔴 **The instrument changed under this session, and the two reads are not comparable.**
The opening read ran the **option-b** harness (equal-weighted cold p50) and REFUSED. The
closing read ran the **option-c** harness — Alex's 2026-08-28 ruling, implemented by
LAT-P110 on `-95`, which **merged mid-session** and brought 300 changed lines of
`needle_latency.py` into this branch at the rebase. Under option c the NEEDLE is what a
brand-new install WAITS over every served sample and the cold-only statistic is demoted to
`DIAG`, which is why one refused and the other published. Quoting `refused -> 24 ms` as a
delta would be a delta of instruments (ruling 127), so it is not quoted as one.

Worth stating plainly: the runner directive names the **option-b** definition, and the
instrument now in master implements **option c**. The ruling is later than the directive
and the harness follows the ruling, so this cycle reports the option-c line and flags the
divergence rather than quietly picking one.

**Neither read measures this branch.** Production is still on `b8ee7e14`; master had moved
to `606bd84b` and had not deployed at close, so nothing in this session's needle readings
reflects either the five branches that merged or this one.

The member number worth carrying forward: `search_cold` p50 **399.5 ms** at open,
**234.5 ms** at close — same slug, same terms, so that spread is composition and warmth,
not a fix landing.

---

## 6. Parked

* **P115-1** — the index that makes this permanent (`futures_markets (max_movement_24h
  DESC) WHERE status IN ('open','active')`). DDL, ruling 080, requested on #2270.
* **P115-2** — `debug_timing=1` suppresses the trending zset vote but not the
  `search_query_logs` write, so every probe this lane runs pollutes the 30-day source
  `resolve_head` blends 24/40 head slots from.
* **P115-3** — `scan_mutation_residue.py --all-tracked` has a standing red on master
  (4 residue candidates, 2 harness drifts, including P114-4's two).
* **P115-4** — cold search's outcome arm: 220 ms of 274 ms for two markets on terms where
  LAT-P111's skip cannot fire (`randers` 15 tier≤1 rows, `empoli` 17, against a window of
  20). Now unblocked — `-96` has merged.
* **P115-5** — `ix_futures_outcomes_name_trgm` still yields ~198 pages per flush against a
  task whose stated steady state is 0.
* **P115-6** — `/api/oscars` 9,571 ms and `/api/futures/browse` cold, both still
  consumerless (re-confirmed, unchanged from P108-2/P108-3); `/api/march-madness/mens`
  still HTTP 500 and `fetchMarchMadness` has **no caller**, which closes the last third of
  P108-4 as "not a ship" rather than leaving it undiagnosed.
