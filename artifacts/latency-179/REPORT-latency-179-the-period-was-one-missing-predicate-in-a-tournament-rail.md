# latency/179 — the period was one missing predicate, in a task nobody was looking at

**PILLAR: DISCOVER. SHIP: the search box stops being cold 43% of the time.**

Written 2026-09-05 9:30pm PT (2026-09-06 04:30Z; PT = local `date` minus 3h, notice 24, verified
with `TZ=America/Los_Angeles date`).

---

## TL;DR

1. **178's ship landed.** CERT-2008 was GREEN with the token granted and exact-SHA CI paid, and it
   had not been merged. Merged as `76b0d811`, deployed, production-checked: the `red sox` cache-miss
   path returns **HTTP 200 on 3 of 3** where it returned **500 on 2 of 3**. The warmer's own ring
   corroborates independently — passes reporting a timeout went **94% → 0%**.
2. **ITEM 1's proposed lever is refuted, and the real one is measured.** The directive asked for
   priority ordering — "move front-page warm-ups ahead of lower-value jobs". The warm-ups are not
   behind lower-value jobs. **One task, `tournament_price_refresh`, holds a background slot through
   50.7% of the warmer's dead time**, and it does so because two per-market statements omit the
   leading column of the only index that covers what they probe. **5,458 ms → 0.059 ms.**
3. **Shipped as #3402, CERT-2012 GREEN, merged `4a098fe3`, live and re-measured.** Two predicates, a
   corrected docstring, and a class guard proved RED-first by mutation in both directions.
4. **The ship itself is NOT delivered, and that is measured too.** The task is 31.8x faster and its
   share of the dead time fell 50.7% -> 6.4%, but the warmer's dead-second share did not move:
   `warm_event_concepts` took the freed slot (25.6% -> 47.9%). Relieving one contributor in an
   oversubscribed queue reallocates the wait. See POST-DEPLOY below.

---

## ITEM 0 — the ship that was in flight

The directive said "if it has not merged, do not rebuild it and do not touch the branch". It had
not. CERT-2008 was GREEN + TOKEN GRANTED at `0bae83f3`, with an append-only follow-up row recording
the exact-SHA CI condition paid, and **no superseding row** (notices 13 and 18 both checked).

Merged `--no-ff` so the certified sha stays in history verbatim and the ledger grep keeps matching
what is on master — rather than rebasing, which would have changed the sha the token names.

| gate | result |
|---|---|
| merge preview vs current master | clean (`git merge-tree`, exit 0) |
| pinned tests + startup smoke on the merged tree | 22 passed |
| typeahead / search-adjacent suites | 641 passed, 6 skipped |
| push rides only my merge | 2 commits, both mine |

**Production check (PROCESS-V2 rule 3), cache-MISS path:**

| query | before (178) | after |
|---|---|---|
| `red sox` miss path | HTTP 500 on 2 of 3, ~10.3s | — |
| `boston red sox` | — | 200, 5.42s, 7 suggestions |
| `red sox world series` | — | 200, 4.73s, 2 suggestions |
| `the red sox` | — | 200, 4.99s, 7 suggestions |

**BUILT → SHIPPED.** Still ~5s: that is ITEM 4 (recall), deliberately not bundled.

---

## ITEM 1 — the measurement, and what it refuted

### (a) The loss is entirely before delivery, and the instrument the last session wanted now exists

Differenced over 11 minutes: `warm_typeahead` **+22 starts / +22 deliveries / +21 terminals**,
`self_gated_fires` 0. Equality eliminates self-gating, post-delivery loss and own-backlog in one
measurement. 66 fires expected at the 10s beat, 22 delivered — **33%**.

`r_starts_equals_deliveries_localises_loss_before_delivery` records that there was **no emit-side
counter** and that this was filed as LAT-P238-EMIT-SIDE-COUNTER. **There is one now.**
`schedule-adherence` carries `matched_emitted` / `matched_delivered` / `undelivered_fraction` /
`bucket_attribution` per task. For `warm_typeahead`: 58–60 emitted per 600s bucket (exactly the 10s
cadence — the beat is healthy) against 4–8 delivered, `undelivered_fraction` 0.86–0.93,
`bucket_attribution: broker_or_worker`. The memory has been corrected.

### (b) The ring, unioned across a 64.5-minute window

Ring reads return only the last 32 passes, so a single read cannot see an hour. Unioning records by
their own `at` stamp across 24 sampler ticks reconstructs one long ring — **40 distinct passes over
3,870s**:

```
period_s   p50  42.8   p95 299.8   max 456.7
wall_s     p50  36.3   p95  52.7   max  57.2
DEAD (period beyond the 65s TTL)   1,477s of 3,870s = 38.2%   in 13 of 40 passes
```

**The p50 is already at its structural floor** (30s min-period gate + 36.3s wall ⇒ ~40s is the best
achievable). The defect is entirely the tail. That is worth stating because it rules out a whole
family of fixes: nothing that shaves the median helps.

### (c) Attribution, not inference — and the refutation

`recent_durations_at` + `recent_durations_ms` give each task's last 50 runs as real occupancy
intervals `[end − duration, end]`. Overlaying those on the ring's own holes:

| overlap | share of dead time | task |
|---|---|---|
| **654s** | **50.7%** | `tournament_price_refresh` |
| 330s | 25.6% | `warm_event_concepts` |
| 182s | 14.1% | `warm_prop_families` |
| 125s | 9.7% | `precompute_discover_candidate_base` |
| 118s | 9.2% | `backfill_polymarket_history` |

`tournament_price_refresh` is in **all four of the longest holes** (excess 204s, 168s, 392s, 235s =
999 of the 1,290 dead seconds in that window).

**🔴 THE DIRECTIVE'S LEVER DOES NOT WORK, AND THE MEASUREMENT SAYS WHY.** Fable-5 directive 176 item
(4) — "move front-page warm-ups ahead of lower-value jobs in the general lane's ordering (priority
queues, if the broker supports it)" — was carried into this queue as ITEM 1's fix. Three separate
findings kill it:

1. **Celery does not preempt.** With `worker_prefetch_multiplier=1` and 2 slots, once a 189s task
   has *started*, no priority reorders it out of the slot. Priority orders the *waiting* queue; the
   hole is caused by an already-running task.
2. **The warm-ups are the majority of the arrivals.** The audit's own number — `warm_typeahead` 24 +
   `warm_search_head` 13 = 77% of a 48-deep queue — was read as the warm-ups being starved by
   others. It means the opposite: putting them first mostly puts them ahead of *each other*.
3. **Redis priority would require demoting ~50 beats**, because kombu's Redis transport makes 0 the
   highest priority and unset *is* 0. That is a large, starvation-risky change to buy an effect the
   first two points already refute.

### (d) A cost model that was wrong twice before it was right

Worth recording, because both errors are the same shape as rule (mm) and I made them in sequence:

| model | `warm_typeahead` cost | verdict |
|---|---|---|
| `p95 × scheduled fires/hr` | 4.92 slots | **wrong** — prices every fire, but most lock-skip |
| `p95 × realised delivery rate` | 6,380 wsec/hr (1.77 slots) | **wrong** — p95 is not the mean |
| `mean × realised delivery rate` | **2,242 wsec/hr (0.62 slots)** | usable |

The duration distribution is **bimodal**: p50 **0.1s** (the lock-skip path) against a mean of 17.3s
and a p95 of 45.3s. The first model over-counted by 8×, the second by 2.8×. Had I stopped at either,
I would have "found" that the warmer was its own problem and built the wrong fix.

---

## THE SHIP — #3402, PR #3406, sha `b9a8fd70`, CERT-2012 staged

### The defect

`_write_refreshed_prices` loops per returned market and issues two statements keyed on
`futures_markets.external_id` alone. The only index covering that column is the composite
`uq_futures_source_external (source, external_id)`. A probe omitting the **leading** column still
*uses* that index — the planner picks it and the node even reads `Index Scan` — but it cannot seek.
It scans the whole thing.

`EXPLAIN (ANALYZE, BUFFERS)` on production, same row, same plan shape:

| form | exec | shared blocks read |
|---|---|---|
| `WHERE external_id = :cid` (what the loop runs) | **5,458.591 ms** | **31,160** |
| `WHERE source = 'polymarket' AND external_id = :cid` | **0.059 ms** | **2** |

`markets_returned` 95 → 190 such statements against `last_duration_ms` **188,869** = **994 ms
each**. The arithmetic closes; this is essentially the whole of the task's cost.

### Why it was invisible

The module docstring says the task is **"cheap … ~420 Polymarket markets, which is 11 batched
requests"**. The 11 Gamma calls *are* cheap. The 190 full index scans behind them are not, and
nothing in the file said so. Three lines above it in the beat schedule, its sibling
`refresh_stale_futures_prices` is pinned to `heavy` with the note that a multi-minute beat "does not
share [background], it closes it". This task was that beat and did not know.

The docstring is corrected in the file rather than edited out, because the sentence is the one a
reader will write again: **a cost claim about the remote call is not a cost claim about the task.**

### Not a narrowing

Measured, not argued: `GROUP BY source` over the **518,851** rows with `external_id LIKE '0x%'`
returns exactly one row — `polymarket`. True by construction too: the register is
`registered_polymarket_conditions`. The predicate cannot exclude a row the old form matched.

### The guard is the class

`test_lat_p240_tournament_refresh_index_seek_3402.py`, four tests: non-vacuity; **every** statement
this rail emits against `external_id` also constrains `source`; `source` is bound to `polymarket`
(a text-only check would pass on `source == 'kalshi'` — a perfect seek that matches nothing, which
is a latency fix turned into a silent no-op rail); and the writes are unchanged.

**RED-first by mutation, both directions.** Removing either predicate → exit 1, with
`test_every_external_id_probe_supplies_the_leading_column` the **named killer both times** — the
intended control, not a bystander (`r_mutant_killed_by_the_wrong_tests_means_a_dead_control`).

Gates: new guard 4 passed; adjacent suites 161 passed; startup clean.

---

## ITEM 2 — `sta` and `ben` (#3399), NOT done

Confirmed as still live in the ring's `last_result_summary`, not investigated further. It is a
genuine defect worth its own session; I did not open it because ITEM 1's answer turned out to be a
buildable ship and PROCESS-V2 caps WIP at two.

---

## ITEM 3 — the audit's list, updated by measurement

**(2) `precompute_discover_candidate_base`** — verdict `missing`, ratio 0.25, mean 67.8s. It is 9.7%
of the dead time. Real, unclaimed.

**(3) tournament-prices and event-concepts** — **the tournament-prices half is this queue's ship,
and the answer was not the cadence.** The directive asked "is the cadence above the rate the output
changes?" It is a fair question and it was the wrong one: the task did not need to run less often,
it needed to stop costing 189s. Cutting the cadence would have halved a cost that should never have
existed and left the plan defect in place. **`warm_event_concepts` (25.6% of dead time, 767 wsec/hr,
mean 68.2s) is untouched and is the obvious next subject** — and it should be checked for the same
class of defect before its cadence is touched.

**(5) Realtime, top three by realised worker-seconds/hour** (rate × p95, an upper bound):

| wsec/hr | share | task |
|---|---|---|
| 7,404 | 29.2% | `poll_datagolf_inplay` |
| 7,368 | 29.0% | `poll_all_odds` |
| 4,651 | 18.3% | `sync_espn_live_events` |

Realtime demands ~25,378 wsec/hr against 14,400 capacity = **1.76×**. `poll_all_odds` is the live
lane's, as the directive says. **These are p95-based and therefore upper bounds** — after what
happened in (d) above, nobody should size a fix off them without re-pricing on means first.

---

## ITEM 4 / ITEM 5 — unchanged

ITEM 4 (serving `red sox` its headline market) is recall, not latency, and is noted on #3394 with
the measured 5s that motivates it. ITEM 5: CERT-1988 remains BLOCKED and PARKED; PR #3377 untouched;
`program/latency-242-…` not built on. This queue's branch is fresh off master, as 178's was.

---

## POST-DEPLOY — the fix is confirmed, the ship is not, and both are reported

Merged `4a098fe3`, live, re-measured the same night.

**Confirmed, directly:**

| | before | after |
|---|---|---|
| `tournament_price_refresh` `last_duration_ms` | 188,869 ms | **5,935 ms** (31.8x) |
| its share of the warmer's dead time | 50.7% | **6.4%** |
| outcomes per market (the no-narrowing control) | 1.642 | 1.647 |
| terminal / errors | complete / `[]` | complete / `[]` |

The 5,935 ms sample is the minimum of a 50-run ring in which every other entry predates the merge.
The outcomes-per-market ratio answers the graded follow-up `LAT-P240-PREDICATE-SEMANTICS-GUARD`
empirically — a narrowing predicate would have moved it — though as evidence, not as a guard, so
the follow-up still stands.

**Not confirmed — the dead-second share did not fall:**

| window | passes | period p50 | period p95 | dead share |
|---|---|---|---|---|
| before | 45 / 4,284s | 42.8s | 268.5s | **37.3%** |
| after (unioned, 49.7 min) | 46 / 2,983s | 40.2s | 231.1s | **43.7%** |
| after (single ring read, 36.5 min) | 32 / 2,192s | — | — | **31.0%** |

**`warm_event_concepts` walked into the vacated slot: 25.6% -> 47.9% of dead time, without getting
one second slower.** The holes did not close; they changed owner.

That is the honest verdict on this queue's ship. #3402 was right and is closed on its own terms — a
31.8x regression, a real plan defect, and a comment that lied for weeks, all fixed. It is a
necessary part of the ship and it is not sufficient, and I should not have implied a single-task fix
would deliver a queue-level outcome. The remaining work is a total, not a ranking: bring `background`
under 7,200 worker-seconds/hour. Directive 180 is rewritten around that.

Two confounds, stated: at least two master merges deployed inside the after-window (each cycles the
background worker), and `red sox` timeouts went to **0 of 46 passes** in the same window, so the
warmer's own budget changed too.

---

## Rules added by 179

**(pp) An "Index Scan" node is not evidence of a seek.** Postgres will use a composite index for a
probe that omits its leading column, and the plan node looks identical to the fast case. The tells
are in the numbers beside it: `Total Cost` 33,064 for one expected row, and `Shared Read Blocks`
31,160. Read the cost and the buffers, never the node type.

**(qq) A cost claim about a remote call is not a cost claim about the task.** "11 batched requests"
was true and was load-bearing for a wrong conclusion for weeks. When a comment prices a task, check
whether it priced the I/O or the work — and if there is a per-item loop between them, that is where
the time is.

**(rr) Price a queue on realised rate × MEAN, and check whether the distribution is bimodal first.**
A gated task's durations are two populations — the skip path and the work path — and every
percentile of the union is a fiction. `warm_typeahead` reads p50 0.1s / mean 17.3s / p95 45.3s. I
built two wrong cost models before this one and both pointed at the wrong task.

**(ss) A directive's proposed FIX is a snapshot too, not just its measurements.** Rule (ll) extended:
178 learned that a directive's account of what has been measured can be stale. 179 adds that its
account of what will *work* can be wrong on facts the measurement then produces. Priority ordering
was free, reversible, and refuted. Measure first, then choose the lever — do not implement the lever
the directive named because it named it.

---

## Idle rule

Next directive written to the runner inbox as `180-…`. Nothing in this queue ends with a question.
