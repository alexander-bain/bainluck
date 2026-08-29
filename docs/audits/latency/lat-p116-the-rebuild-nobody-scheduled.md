# LAT-P116 — The rebuild nobody scheduled, and the three candidates disproved to find it

**Queue:** LAT-P116 (cycle 88) · identity `LAT-P116-20260829-w17464`
**Ran from:** Fable's runner directive `runner-inbox/latency/021-coldpath-conveyor.md`, under Alex's
standing authorization.
**Pillar:** DISCOVER (search is the fifth tab and the surface ruling 137's row 5 grades).
**Ship:** *an obscure search stops randomly taking half a second longer because two caches expired.*
**Branch:** `program/latency-101`, cut from CURRENT master `606bd84b`. **Issue #2272** filed.

---

## 0. The needle, first, because the directive asks for it first

```
NEEDLE: latency 19 ms @ 2026-08-29T04:37:27Z
DIAG:   latency-build REFUSED — only 2 of 7 member paths produced a cold sample (floor 4);
        only 2 of 3 graded surfaces went cold (missing: Discover open)
```

Taken on slug `606bd84b`, uptime past the post-deploy window, `--label LAT-P116-open`, canonical
depth. **This is an option-c reading** (Alex 2026-08-28, ruling 127's series break): the NEEDLE is
every served sample, the cold-only statistic is DIAG and is report-only.

⚠️ **The runner directive still names option b.** The directive was staged before the ruling landed;
the harness in the tree is option c and the harness is the authority. Flagged here rather than
silently reconciled — LAT-P115 flagged the same drift and it has not been repaired upstream.

🔴 **The single most useful line in that reading is not the needle.** It is the member table:

| surface | member | n | cold | cold % | cold p50 |
|---|---|---|---|---|---|
| Discover open | discover_native | 5 | 0 | 0 % | — |
| | discover_web | 5 | 0 | 0 % | — |
| tab loads | sports_native | 5 | 0 | 0 % | — |
| | sports_web | 5 | 0 | 0 % | — |
| | search_trending | 5 | 0 | 0 % | — |
| | my_stuff_stats | 5 | 5 | 100 % | 19.0 |
| **cold search** | **search_cold** | **6** | **6** | **100 %** | **206.0** |

**Cold search is the only member of the graded pool that a warmer does not reach, and it is 10x the
next slowest.** Six of seven paths never went cold at all. That is why this cycle worked on search
and not on the feed, and it is a stronger argument than the needle number itself.

**And it is why the needle will not move on this ship, which is stated up front rather than
discovered by a reader.** The needle is the MEDIAN of seven per-path p50s. `search_cold` is the
maximum of that set, not the median, so halving it moves the published number by zero. The ship is
real and the statistic is blind to it. Ruling 137 anticipated exactly this by keeping cold search
in the opening headline set as its own row — that row is where this lands.

### The close reading, and what it demonstrates about the instrument

```
NEEDLE: latency 19 ms @ 2026-08-29T05:19:28Z      (unchanged from open)
DIAG:   latency-build REFUSED — 2/7 cold members, 2/3 surfaces (unchanged)
```

Same slug `606bd84b` (uptime 1,366 s at open, 3,903 s at close). **This branch is not deployed, so
neither reading measures it** — both describe master.

🔴 **`search_cold` moved 206.0 ms → 532.0 ms (max 1,728 ms) on IDENTICAL CODE, 42 minutes apart,
and the needle did not move by one millisecond.** A 2.6x swing on the one member that is reliably
cold, fully absorbed by a median over seven. That is not a criticism of option c — the equal-weighted
form exists precisely because a raw pool moved 25 % on sample mix alone (ruling 127) — but it is the
sharpest available demonstration that **this lane's headline number cannot see the surface this lane
is working on.** Recorded here so a future reader does not read `19 → 19` as "nothing happened".

Per ruling 127, the 206 and 532 figures are the same instrument on the same slug and ARE comparable
with each other; neither is comparable with any pre-option-c cold number.

---

## 1. What ships

`_load_ei_percentiles` and `_build_team_lookup` (`backend/app/routes/events.py`) are process-global
caches with a **300 s TTL and nothing that rebuilds them**. Every five minutes, in every worker
process, the next request to arrive pays the whole build inline.

Measured on slug `606bd84b` via `?debug_timing=1`, two independent cold reads landing on the two
`WEB_CONCURRENCY=2` workers seconds apart (`randers` then `empoli`):

| stage | cold | warm |
|---|---|---|
| `event_gei` (`_load_ei_percentiles`) | **216 ms / 276 ms** | 0 ms |
| `event_teams` (`_build_team_lookup`) | **424 ms / 342 ms** | 0 ms |

against a **157 ms p50 total build** for the same request over the frozen 12-term `obscure` set. The
rebuild is roughly **four times the entire rest of the request**.

🔴 **It was never the same user twice, which is why it never looked like a slow endpoint.** A p50
over a term set cannot see it; a p99 attributes it to the term rather than to the clock. It only
became visible because the two workers happened to be cold in the same second and the third call
onward showed `0 ms` for both stages.

🔴 **The team half is expensive because a docstring was stale by 19x.** It said "the teams table is
small (~500 rows)". Measured: `teams` holds **9,577 rows, 1,592 of them ESPN-enriched**, and every
one of those is loaded, snapshotted, and run through the alternate-names ambiguity dedup. The
comment is corrected in the same commit, with the measurement in it, because the wrong number is
what stopped anyone suspecting the cost.

**Blast radius is wider than search:** `_load_gei_percentiles` is called from four sites — the
search route and three event-detail routes.

### The fix, and why it is serve-stale and not a warmer

Past the TTL the **stale value is returned immediately** and the rebuild runs behind the response on
its own session.

A warmer is a second schedule that can silently stop — LAT-P115 shipped one and had to prove its
producer still ran, and found `update_max_movement` was absent from the task-metrics rail while
doing so. Serve-stale has **no schedule to fail**: the rebuild is triggered *by* the request that
would otherwise have paid for it, and if a rebuild never happens the only consequence is that the
next request tries again. Staleness is free on this data's own terms — the percentiles "change only
when recalculate is triggered" and team colours "change very rarely", both quoted from the functions
being fixed.

🔴 **It fails closed in two places, on purpose.**

1. **An empty cache still blocks.** A first request in a fresh process has no stale value to serve,
   and returning `{}` there ships a search with no logos rather than a slow one — a wrong answer,
   not a fast one.
2. **Past `_STALE_SERVE_CEILING` (5x TTL = 25 min) the caller blocks again.** A refresher that fails
   forever must degrade into the *old slow behaviour*, never into silently serving hour-old data
   with no signal. That is the whole difference between this and `TTL * 10`.

Both cache paths now shape their rows through **one extractor** (`_shape_ei_percentiles`,
`_shape_team_lookup`), extracted rather than copied, so the refresh-behind value and the blocking
value cannot drift by a key. That is LAT-P115's `build_and_cache_movers` lesson applied before it
could bite: a warmed payload differing from the served one by one key is a wrong answer served fast.

---

## 2. Three candidates were measured and disproved first, and the disproofs are the finding

The queue head named **P115-4** — cold search's outcome arm, "NOW UNBLOCKED" after `-96` merged.
That was the right place to look and the wrong thing to fix. Verified first that `-95` … `-99` are
all ancestors of `origin/master` (`merge-base --is-ancestor`, per branch), so LAT-P111's skip is
genuinely live.

### (a) The outcome arm is real, is 60 % of the build, and is DDL-bound — not code-bound

Across the frozen 12-term `obscure` set on `606bd84b`, `futures` is **59.9 % of the cold-search
build** (p50 88 ms of 157 ms), the largest bucket by 4x. LAT-P111's skip fires on **7 of 12** terms;
on the other 5 the arm runs.

`EXPLAIN (ANALYZE, BUFFERS)` on the outcome candidate set for `randers`: **173.1 ms of 174.5 ms** is
the `ix_futures_outcomes_name_trgm` bitmap index scan, **1,467 index blocks** to yield 170 rows. And
what does that buy the user?

| term | outcome-arm markets (open) | already matched by the NAME arm | **marginal** |
|---|---|---|---|
| `randers` | 2 | 1 | **1** |
| `empoli` | 3 | 3 | **0** |

🔴 **THE LAW, and it is the transferable part of this cycle.** A `pg_trgm` GIN scan's cost is set by
the term's **commonest trigram, not by its selectivity**. Measured on the bare subquery:

| term | rows | index blocks | index scan |
|---|---|---|---|
| `zzqxqz` | 0 | 64 | 2.8 ms |
| `bochum` | 155 | 104 | **1.7 ms** |
| `cagliari` | 415 | 243 | 53.6 ms |
| `randers` | 170 | **1,467** | **316.2 ms** |

`randers` costs **186x the blocks of `bochum` while returning fewer rows**, because `and`, `der` and
`ers` are everywhere in outcome names and GIN must walk each posting list. This kills the obvious
fix: **no static skip heuristic can be sound**, because cost is uncorrelated with everything the
route can see before running the query. It also kills a time-bound as a *ship* — an aborted
statement still pays the time it spent, so a 120 ms bound saves 53 ms on the one term it fires on.

The permanent fix is the parked index (**P111-1** / **P115-1**), which is DDL and is blocked by
ruling 080. **Re-parked with these numbers**, which are the strongest case for it yet made.

### (b) The `OFFSET 0` optimization fence — disproved, and it would have shipped as a win

The tier-1 arm's plan does a `BitmapAnd` against `ix_futures_markets_status` that reads **69,875
rows / 956 blocks / 31-34 ms to eliminate almost nothing** — it is ANDed against a 404-row trigram
bitmap. An `OFFSET 0` fence removes it: blocks **1,162 → 339**.

**A 3.4x block reduction, and it is slower.** Five interleaved repeats per term:

| term | current p50 | current blocks | fenced p50 | fenced blocks |
|---|---|---|---|---|
| `lecce` | 46.3 ms | 1,162 | **15.4 ms** | 339 |
| `cagliari` | **10.4 ms** | 713 | 23.1 ms | 469 |
| `verona` | **7.1 ms** | 537 | 19.3 ms | 399 |

It wins on one term and loses on two, because the fence forces heap fetches of *all* trigram
candidates instead of letting the BitmapAnd prune first. **Blocks went down in all three and time
went up in two.** Had this shipped on the block number — which is the number that looks principled —
two thirds of the measured terms would have got slower. Disproved, not deferred.

### (c) `total_results` and the eager `selectinload` — both cleared

`event_count` is 12.1 % of the build and exists only to fill `pagination.total_results`. It is
**used**: `frontend/app/search/page.tsx:400,419,505` renders it as the Games section count. Not a
candidate.

The window query's `selectinload(FuturesMarket.outcomes)` looked like it could be loading hundreds of
outcome rows per search. Measured: **18-81 rows** for the top-20 markets across four terms. Not a
candidate.

---

## 3. Gates

| gate | result |
|---|---|
| full suite | **21,206 passed / 0 failed / 124 skipped / 61 xfailed**, ONE run (854.76 s), **EXIT CODE 0 READ BY VALUE** |
| collect reconciliation | 21,206 + 124 + 61 = **21,391 = collected, exactly**. Master **21,380 → 21,391 (+11)**, measured on BOTH sides (master collected in a throwaway worktree, not inferred), and `test_search_cache_refresh_behind.py` collects exactly 11 |
| mutation battery | **10/10 killed** (`cache_refresh_behind_mutations.py`) |
| mutation residue | **CLEAN exit 0** — 158 needles, 420 broad checks |
| ruff | **ZERO NEW** — finding set diffed against master's own copy, byte-identical (46 = 46) |
| smoke (`test_startup.py`) | 4 passed, exit 0 |
| migration slot | **none** — no DDL, no index, no schema change |
| beat schedule change | **FALSE** — touches no beat file, adds no Celery task |
| config vars | none |

🔴 **TWO MUTANTS SURVIVED THE FIRST BATTERY AND BOTH WERE REAL HOLES IN THE TESTS.**

- **M3 (drop the ceiling) survived** because the ceiling test computed its age as
  `_EI_CACHE_TTL * _STALE_SERVE_CEILING + 1` — it read the very constant it existed to pin, so
  raising the ceiling to a billion raised the test's own age to match. *A pin computed from the
  thing it pins is not a pin.* Repaired with a literal `1501` plus an explicit assertion on the two
  constants, so a deliberate change fails visibly instead of quietly widening what the test permits.
- **M7 (serve an empty cache as stale) survived** because the test left `_ei_cache_time = 0`, making
  the computed age the **machine's uptime**. On any host up longer than 25 minutes the mutant fell
  through the ceiling into the blocking build and the test passed for a reason unrelated to the
  code — gotcha #44, an anchor that depends on the clock is not an anchor. Repaired by pinning the
  timestamp to `now`, so emptiness is the only thing that can route to the blocking path.

**Repaired by fixing the assertions, not by deleting the mutants** (LAT-P115's M7 rule).

🔴 **THE FIRST COMPLETED FULL SUITE WENT RED ON TWO GUARDS AND BOTH WERE MINE.** `2 failed, 21,204
passed` — recorded here rather than folded away, because what they caught is the useful part.

1. **`test_mutation_guard::test_every_on_disk_harness_is_guarded`.** The new battery mutates
   `events.py` with only a `try/finally`, which does not survive a SIGTERM — a killed run leaves a
   mutant sitting in the tree. Wired to the shared `guarded_targets` primitive (manifest +
   `--recover`) like every other on-disk harness. **That guard exists exactly to stop a new harness
   quietly opting out, and it worked on this one's first full-suite run.**
2. **`test_team_cache_detachment::test_the_next_requests_recover_through_the_real_feed_reader`** —
   the #2107 guard. This change moves *which session* rebuilds the team cache, so the test's
   scaffolding (hand a session to the caller, expect a rebuild) was asserting on a rebuild that no
   longer runs there. **Repointed at the real path rather than relaxed**, and the guard comes out
   stronger: the rebuild now happens in a background task whose session closes the moment it
   finishes, so if `_shape_team_lookup` ever stopped snapshotting inside the `async with`, every
   cached row would be detached **by construction** rather than only after a rollback. Both original
   arms survive — the hazard is still proven live on the rebuilt rows, the served requests still
   survive it — plus a new assertion that the caller is served the stale value instead of blocking,
   which is the ship itself.

   ⚠️ A bare `AsyncMock` cannot stand in for `async with async_session_maker()`: its `__aenter__`
   returns a *different* auto-created mock, so the rebuild raised `'coroutine' object has no
   attribute 'all'`, the handler logged it and left the cache intact — **correct behaviour that
   looks exactly like a rebuild that never happened**. A real async-CM stand-in makes that
   impossible to mistake for the feature.

⚠️ **An earlier full-suite run was stopped at 8 % on purpose.** A stale `#2271` reference was still in
the source — #2271 had been taken by the calibration lane between drafting and committing — and a
green number from a tree nobody will push is a gate proving something about the wrong commit.
Re-taken rather than reported.

⚠️ **A guard run nearly read as a pass on a stale file.** `cd backend && pytest ... > /tmp/g1.txt`
was issued from a shell already inside `backend/`; the `cd` failed, `&&` short-circuited, pytest
never ran, and `tail` printed a *previous cycle's* content — `test_futures_movers_warm_p115.py`,
15 passed. The exit code was 1 and that is the only thing that caught it. Gotcha #54, in the exact
shape it warns about: the harness failed and the output looked like a verdict.

⚠️ **Pre-existing on master, not mine:** the residue scan reports 2 needle DRIFTs in
`typeahead_warmer_mutations` (M4, M6) against `app/tasks/typeahead_warmer.py`, a file this branch
does not touch. Non-fatal (drift scores NOT-APPLIED, never a false kill). This is the standing red
parked as **P115-3**.

---

## 4. Parked

| id | item |
|---|---|
| **P116-1** | `CREATE INDEX ON futures_outcomes (market_id) INCLUDE (name)` — the P111-1 / P115-1 index. DDL, ruling 080. **Fifth index this lane has parked**, and §2(a)'s 186x table is the strongest case yet: no code fix can be sound while cost is uncorrelated with selectivity. |
| **P116-2** | An FTS index on `futures_markets.name`. The word test recomputes `to_tsvector('english', name)` per candidate row at runtime — 404-476 rows on the measured terms. DDL. |
| **P116-3** | The planner picks the `ix_futures_markets_status` BitmapAnd inconsistently and it is always wrong when picked (§2b). The cure is statistics (`ALTER TABLE … SET STATISTICS`), not SQL — DDL, and the `OFFSET 0` workaround is disproved. |
| **P116-4** | `?debug_timing=1` on `/api/events/search` still writes a `search_query_logs` row. `/typeahead` suppresses its analytics write on the same flag (`events.py:4508`); `/search` has no equivalent. Inherited **P115-2**, re-confirmed, and this cycle's own probes are in that table. |
| **P116-5** | `_STALE_SERVE_CEILING` breaches are logged but not counted. If the refresher ever fails persistently the symptom is "search got slow again", with nothing on the task-metrics rail to say why. A counter belongs here — parked rather than taken, because an un-consumed metric is the thing CLAUDE.md forbids queuing. |
| **P116-6** | The runner directive's needle definition (option b) contradicts the harness in the tree (option c, ruling 127). Second cycle to flag it. Needs a directive edit, which is not this lane's to make. |

**Rulings banked:** NONE (next free **138**). **Gotchas:** NONE — the `pg_trgm`-commonest-trigram law
in §2(a) is a candidate, but it belongs beside the existing catalogue entry about the alnum run
rather than as a new number, and this lane does not renumber that catalogue.

---

## 5. Post-deploy verification owed (#2272)

`program/latency-101` is not deployed at the time of writing; production is on `606bd84b`. After it
reaches a release:

Sample `?debug_timing=1` across the frozen `obscure` term set continuously for **>10 minutes** — two
full TTL expiries — and confirm `event_gei` and `event_teams` never exceed single-digit ms on either
worker. The pre-fix control is in §1: those stages read 216/276 ms and 424/342 ms on the two workers
of slug `606bd84b`. **A single sample is not enough**: the whole defect is that the cost lands on one
request in several hundred, so the check has to span an expiry, not a moment.
