# LAT-P154 — the phase that spent the whole budget

**Queue:** `runner-inbox/latency/043-score-resolution-cost.md`, staged by Fable 2026-08-30 ~11:45am PT.
**Pillar:** TRUTH-enabling performance. **Issue:** #1887. **Branch:** `program/latency-154`.

---

## Ship

**A settled Polymarket prop stops publishing a coin flip.** *Xavier Edwards: Home Runs O/U 1.5*
is quoted **0.0105** by Polymarket and published by us at **0.5005**. lane1/q436 built the fix,
INT-170 merged it to master on 2026-08-30, and it has never once executed — `backfill_winners`
returns before it reaches `_compute_calibration_prices()`.

This queue removes the first of the two things standing in front of it, and **measures the
second**, which turns out to be bigger. Read "Ship bar: not met, and here is the number" before
banking anything.

Second ship, unplanned and real: **241 settled Polymarket Over/Under markets become gradable.**
The resolver that grades them has been returning a full page of markets it can never grade —
see §3.

---

## 1. The 397 seconds, split

`GET /api/admin/task-metrics?task=backfill_winners`, read 2026-08-30 ~19:0xZ, last run
`2026-08-30T15:54:13Z`:

```
status            partial_budget_guard
stopped_before    prob_and_datagolf
pipeline_elapsed  553.6 s
phase_times       score_resolution 397.0 | kalshi_api 100.6 | kalshi_markets_api 11.4 | polymarket_api 44.5
```

`score_resolution` is **six resolvers behind one timer**, so the phase map could only ever say
"397.0". Which of the six owned it took a read-only probe on a one-off dyno with
`statement_timeout = 0` (`/tmp` scripts, results via `bainluck:latp154_*` →
`GET /api/admin/redis-read`). 2026-08-30 19:25Z:

| # | resolver | statement | s | rows |
|---|---|---|--:|--:|
| 1 | `_resolve_kalshi_from_scores` | candidate scan | **71.9** | 91,776 |
| 2 | `_resolve_kalshi_spread_total_from_scores` | candidate scan — **byte-identical predicate** | **46.5** | 91,776 |
| 2 | ″ | per-market `WHERE market_id = :mid`, projected from a 300 sample @ 1.114 ms | **102.2** | 91,776 round trips |
| 3 | `_resolve_polymarket_total_from_scores` | candidate scan | **56.2** | 20,000 — **all 20,000 unparseable** |
| 4 | `_resolve_kalshi_player_props_from_boxscore` | outcome scan | **44.7** | 50,000 |
| 4 | ″ | the batched box-score load everyone worried about | 0.41 | 460 events |
| 5 | `_resolve_kalshi_total_bases_from_boxscore` | outcome scan | **17.9** | **0** |
| 6 | `_resolve_kalshi_period_props` | candidate scan | 0.02 | 0 |
| | | **sum** | **339.8** | |

339.8 of 397.0. The 57 s residual is resolver 1's own per-market loop (59,047 markets at the
same 1.114 ms projects to 65.8 s, so the real task's round trips are somewhat faster than the
probe's) plus every Python pass and every UPDATE.

Three of those lines are work the task has been redoing every six hours since it was written,
and two of them return nothing at all.

## 2. What changed

**One candidate scan, not two.** Resolvers 1 and 2 issue statements identical in FROM, WHERE
and HAVING; only the projection differs. The first now hands its rows to the second.

Reuse is exact, not approximate, and the reason matters more than the saving. A market leaves
that candidate set only by acquiring an outcome that is `is_winner AND resolution_source NOT IN
(overwritable)`. Resolver 1's only writes stamp `'game_score'`, which is not overwritable. So
the markets it set a **True** on are *precisely* the ones the second scan would have dropped —
and it hands them over as `locked_market_ids`. Two edges the guards pin down:

* a BTTS **"no"** writes only `False`, so the market stays selectable — locking it would
  silently drop work;
* a moneyline market where only the losing side's name matches also writes only `False`.

**One outcome round trip per block, not per market.** `_prefetch_outcomes()` loads
`(market_id, id, name)` for 2,000 markets at a time, id-ordered.

**The Polymarket O/U name anchor moves into SQL** — see §3.

**Both box-score resolvers read their event ids first.** `e.box_score_data IS NOT NULL` inline
made the planner drive off a **seq scan of `futures_markets`** (917K rows / 1.6 GB) to apply a
ticker prefix. Reading the 7,692 box-score event ids first and binding them as `= ANY` turns
both into nested loops on `ix_futures_markets_event_id`.

**And the phase stops being one number.** Each resolver is timed and reported as
`score_resolution_sub_s` on **both** exit paths — including `partial_budget_guard`, which is
the path every recent run has taken.

### Measured, same rail, same data (19:32Z and 19:38Z)

| line | before | after |
|---|--:|--:|
| candidate scan | 46.5 s x2 | **30.9 s x1** |
| outcome fetch, resolver 1 | ~59,047 round trips | **1.6 s** (46 queries) |
| outcome fetch, resolver 2 | 102.2 s / 91,776 round trips | **1.6 s** (46 queries, same 264,810 rows) |
| polymarket O/U scan | 56.2 s | **18.1 s** |
| player props | 44.7 s | **0.3 + 2.7 s** |
| total bases | 17.9 s | **0.3 + 5.8 s** |
| period props | 0.02 s | 0.02 s |
| **phase statement cost** | **339.8 s** | **61.3 s** |

Two honesties about that table. The 71.9 s in §1 was a cold first read of the same statement
the 46.5 s row measured warm; the claim here is not "the scan got faster", it is "one execution
of it was deleted". And 61.3 s is statement time on the probe rail — the phase also spends
Python and UPDATE time the probe does not run, so the phase itself should land near **70–110 s**,
not 61. The task-level number is owed after deploy and is not claimed here.

## 3. The polymarket resolver was grading nothing, and that is a TRUTH bug

`_resolve_polymarket_total_from_scores` returned its full `LIMIT 20000`, and `_poly_total_line`
rejected **all 20,000**. An unparseable market can never be graded, so it can never leave the
ungraded set: the same permanent residue came back every cycle, saturated the limit, and starved
every gradable market behind it — for 56.2 s a time.

The name anchor is now in the statement, and it is **strictly looser** than the grader's regex
(`:\s*o/u\s*(\d+\.?\d*)\s*$`): anything the grader parses contains `:\s*o/u`, so the SQL can only
drop rows the loop already skipped. Verified rather than argued — over the 49,497 resolved
Polymarket markets the grader's regex accepts, the prefilter drops **0**. The Python parse stays
the authority.

It is served by the **existing** `ix_futures_name_trgm` GIN index. No DDL, no parked index
request. *(LAT-P151's rule, paid out again: grep for the PROBLEM, not the remedy.)*

Result: 20,000 rows / **0 gradable** → 1,651 rows / **241 gradable**.

## 4. Ship bar: NOT met, and here is the number

> "the task completes both halves inside its limit on production, measured both sides"

It does not, and the reason is not this phase. Probe 4, 19:58Z, read-only, same rail — the read
halves of what sits between the fixed phase and `_compute_calibration_prices()`:

| statement | s | rows |
|---|--:|--:|
| `_backfill_datagolf_winners` driver | 0.04 | 320 |
| **`_backfill_from_current_probability` pass 1 — the `cleanly_resolved` CTE** | **274.05** | **255,407 markets** |
| the `pass2_guess` → `clean_resolution` upgrade selector | **42.19** | **0** |
| `fix_categories` selector | 0.16 | 0 |

Queue 357's 314.9 s for `prob_and_datagolf` was not stale. The arithmetic, using the estimate
above for the fixed phase:

```
score_resolution ~78 + kalshi_api 100.6 + kalshi_markets_api 11.4 + polymarket_api 44.5 = ~235 s
  guard at prob_and_datagolf needs elapsed < 540   -> PASSES for the first time
prob_and_datagolf ~320-400 (the 274 s CTE is the SELECT half of an UPDATE)  -> cum ~555-635 s
  guard at bookmaker_closing needs elapsed < 540   -> FAILS
```

So this change moves the wall from `prob_and_datagolf` to `bookmaker_closing`. That is real
progress — no run since the #991 guard shipped has *reached* `prob_and_datagolf`, so the next
run measures it in `phase_times` for the first time — but the calibration half still will not
execute, and saying otherwise would be the "it returned, so it worked" error (gotcha #53).

**The next queue, fully scoped.** That CTE aggregates every outcome of every resolved market
with no event join and no limit, and the UPDATE behind it then rewrites `is_winner`,
`resolution_source` and `last_updated` for all outcomes of 255,407 markets **every six hours,
whether or not anything changed** — `clean_resolution` is itself in `OVERWRITABLE_WINNER_SOURCES`,
so the set never shrinks. Two obvious arms, neither taken here:

1. **write-on-change** (`IS DISTINCT FROM`), the pattern the box-score resolver already uses;
2. **run the calibration drain before `prob_and_datagolf`** — #107's own reordering argument,
   applied one phase later. Cheapest thing that would meet the ship bar.

Arm 2 is a sequencing change to a TIER-1 calibration writer and I did not take it because I
could not measure whether `_backfill_closing_lines` / `_compute_calibration_prices` depend on
that cycle's freshly-set `is_winner`. That is a question for the calibration lane or Alex, not
a thing to bolt onto a cost fix. Filed rather than guessed.

## 5. Gates — CLAIMS, re-run them

| gate | claim |
|---|---|
| full backend suite | see the READY token — one run, exit code recorded there |
| new file `tests/test_score_resolution_cost_latp154.py` | **34 passed**, exit 0 |
| targeted (`test_backfill_winners` + `test_boxscore_resolver_memory` + `test_resolution_authority_038` + `test_startup` + `test_task_resumability` + `test_tasks_wiring`) | **287 passed**, exit 0 |
| `scripts/lat_p154_mutation_battery.py` | **18/18 killed, 0 survived, 0 harness failures**; target byte-identical after |
| `scripts/evals/scan_mutation_residue.py` | **CLEAN** — 451 needles, 1,368 broad checks, 0 residual mutants |
| ruff | **zero new**: 48 findings on the two touched files, **48 on `origin/master`'s own content** for the same files (extracted to a scratch tree and re-run, not stashed); the two new files pass clean |
| import smoke | `tests/test_startup.py` 4 passed |
| frontend / iOS | **not touched** |
| migration / beat schedule | none |

### The vacuity check that caught me

The first battery run had **two survivors**, both in the same place.
`test_the_prefilter_is_in_the_statement` asserted the SQL predicate against
`inspect.getsource(...)` — and the function's own **docstring quotes that predicate**, so
deleting the clause from the statement left the guard green. `M-POLY-PREFILTER-DROPPED` and
`M-POLY-PREFILTER-TOO-TIGHT` both walked straight through it.

Both are now asserted against the statement the resolver actually **executes**, captured by a
recording session; and the loose-anchor guard extracts the shipped POSIX pattern out of that
statement, translates it, and requires it to accept everything the grader parses — a semantic
check, not a string compare. Second run: 18/18.

*The tell was LAT-P152's and LAT-P153's, for the third cycle running: the check agreed with me
too easily. A guard that reads `getsource` on a function whose docstring documents the thing it
is guarding is guarding the documentation.*

## 6. Where I think I am most likely wrong

1. **Outcome ordering in resolver 2.** Its per-market fetch had no `ORDER BY`; the block
   prefetch orders by `(market_id, id)`. In practice the old plan used
   `ix_futures_outcomes_market_id`, whose heap order tracks insertion, so this should be the
   order it already had — but "should be" is the weak word in this report and resolver 2's
   team-total branch takes the FIRST matching outcome.
2. **The locked-set equivalence** is argued from `'game_score' ∉ OVERWRITABLE_WINNER_SOURCES`.
   If a future edit adds `game_score` to that list, the sharing becomes wrong silently. The
   guards pin the behaviour, not that invariant.
3. **The two-read window in the box-score resolvers.** The event-id list and the outcome scan
   are not one snapshot; a box score written in the ~0.3 s between them waits for the next
   6-hour cycle. A lag, not a loss — but it is a real change from a single-statement predicate.
4. **The 70–110 s estimate for the fixed phase** is an estimate. Only the statements were
   measured.
