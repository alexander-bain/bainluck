# LAT-P062 — the warmer fix, graded on a settled pool; and the tail prediction that was right for a reason we can now see

**Window:** latency lane cycle 34, `pid:21675`, 2026-08-17 ~12:55–1x:xx PDT.
**Branch:** `program/latency-57`, cut fresh from `origin/master` `1eb968ee`.
**Deployed at read time:** `/api/health` `commit = 1eb968ee`, Heroku **v3829**, released **12:30:40 PDT**.
**Flag:** `GOLF_IDENTITY_SPLIT_SCAN` — **empty**, re-read at Phase 0. The `OR` is live and stays.
**Settled pool:** every read below is **≥ 25 minutes** past the release, not the 10–12 minutes
LAT-P061's preliminary addendum had. The warm-up shadow is out.

---

## §1 — Item 0: the registered prediction, GRADED

Registered at `c3d94136` **before** the code (`lat-p060-warmer-arithmetic.md` §3/§8), with §8.1's
amended row 4′ (dated before any post-fix read existed). Two probe runs, ruling 064.

| # | prediction | HALT | measured | verdict |
|---|---|---|---|---|
| **1** | `excluded_pre_warmed` **≥ 20 of 24** (ceiling 24) | **≤ 14** | **16 of 24** and **19 of 24**, mean **17.5** | ❌ **FAIL — no halt** |
| **2** | `seconds_wall` **≤ 15 s**, then ≤ 6 s | **> 30 s** | **36.14 / 31.27** s (summaries) · pass band min 27.4 / median 30.9 / **max 38.1** s | 🔴 **HALT** |
| **3** | lock skips **25 → 0** per ~50 beats (graded vs the concurrent pre-fix **12**) | any skip | **23** and **19** per 50 | ❌ **FAIL** |
| **4′** | `rebuilt > 0` on every `terminal: complete` pass | any `rebuilt == 0` | **`rebuilt: 40, fresh: 0`** on **5 of 5** observed passes | ✅ **PASS** |

**Row 1 in context, because a FAIL here is still the largest movement this program has measured on
#1866.** The pre-fix duty cycle is stable at **~10.5 of 24 across six runs and three windows**
(14,7 · 14,8 · 13,8,4). Post-fix is **17.5 of 24**. That is **44% → 73% warm**, a real and
reproducible gain — and it is short of the ≥20 bar, which is what the bar was for.

**Row 2 is the halt, and it is exactly what the directive read it as.** Every settled reading is
above 30 s. The prediction is not merely missed; the model behind it is wrong, and §2 says how.

### The per-round shape, which is not noise

| run | round 0 | round 1 | round 2 | cold queries |
|---|---|---|---|---|
| 1 (13:03 PDT) | 6/8 | 8/8 | **2/8** | `celtics` `yankees` `bruins` `world cup` `masters` `election` |
| 2 (13:09 PDT) | 6/8 | 7/8 | 6/8 | `world cup` `masters` (×2), `red sox` (×1) |

`world cup` and `masters` are cold in **4 of 6 rounds**. Both are in the head (`world cup` is trending
**#4** at 1,842). This is not membership; it is position — but the summary cannot currently say
whether a cold entry was *alive-but-under-threshold* or *already expired*, which is the instrumentation
gap §4 closes.

---

## §2 — Pricing the pass, and refuting the fix the directive proposed

### The measurement the queue asked for FIRST: the pass-period distribution

`recent_durations_ms` records every invocation; a real pass is `> 1 s`, a lock skip is `< 100 ms`.
Two reads, 15 minutes apart, on the settled pool:

| read | window | invocations | real passes | skips | **mean period** | wall min/med/max |
|---|---|---|---|---|---|---|
| A, 13:00 PDT | 1,396 s | 50 | 27 | 23 | **51.7 s** | 28.1 / 31.4 / 36.1 s |
| B, 13:15 PDT | 1,319 s | 50 | 31 | 19 | **42.5 s** | 27.4 / 30.9 / 36.2 s |

Against a **45 s** response TTL. And the sequence is the finding, not the mean — read B,
oldest → newest, `P` = real pass, `.` = lock skip:

```
PPPPPPPP.P...P...P.PPPPPPP...PPPPPPPPP.P.P...P...P
```

**The warmer is bistable.** In the `PPPPPPPPP` stretches the period is ≈ the pass wall, ~31 s, and
the duty cycle is **100 %**. In the `P...P...P` stretches one pass runs per four beats — a period
near **105 s**, against a 45 s TTL, and the head is dead for well over half of it. The mean period
of 42.5 s is *already under the TTL*; **the duty cycle fails on the VARIANCE, not on the mean.**
That distinction is the whole of what to do next, and no summary statistic shows it.

### 🔴 The directive's proposed shape is arithmetically INERT, and the measurement says so five times over

> *"the unpriced interaction (refresh-ahead rebuilds all 40 every pass) wants a staleness-aware
> rebuild (only entries older than T)"*

`_warm_one` already **is** staleness-aware: it skips as `fresh` any entry with `ttl_before >
REFRESH_AHEAD_SECONDS` (35 s). It has never skipped one. `fresh: 0` on **5 of 5** observed passes.

It cannot, and the reason is a two-line proof rather than a tuning miss. An entry is rebuilt once per
pass period `P`, so when the next pass reaches it, its remaining TTL is `45 − P` (or it is already
dead). A threshold `T` skips it only when `45 − P > T`, i.e. **`T < 45 − P`**:

| P (measured) | largest T that could ever skip anything |
|---|---|
| 42.5 s | **2.5 s** |
| 51.7 s | **negative — nothing is ever fresh** |

The shipped `T` is **35 s**. There is no reachable operating point at which it skips an entry:
with the beat at 30 s, `P ≥ 30 s`, so `T` would have to be under 15 s even in the best case.

**And lowering `T` into that range would be actively harmful**, which is the part worth stating
plainly: skipping an entry with 2.5 s of life left means it expires before the next pass reaches it.
A staleness-aware skip buys pass time by re-opening exactly the cold window refresh-ahead exists to
close. **It is not a fix here; it is the bug wearing a fix's clothes.**

`REFRESH_AHEAD_SECONDS`' own docstring states the bound it was chosen against — *"that gap is the
pass PERIOD (the 30s beat), not the period plus the duration"*. **The measured period is 42.5–51.7 s,
not 30 s.** The constant is inert and its stated justification is refuted; §4 corrects the comment
rather than the value, because the value is not what is wrong.

### What the two fixes actually cost, priced

`seconds_total` is the summed per-query time; `seconds_wall` is the pass. Read B's last summary:
`seconds_total: 124.27`, `seconds_wall: 31.27`, `concurrency: 4`, 40 rebuilds.

| | pre-fix (LAT-P060) | post-fix (this window) |
|---|---|---|
| per-rebuild time | ~0.95 s (40 in a 38 s serial pass) | **~3.1 s** (124.3 s ÷ 40) |
| pass wall | 38.0 s median | **30.9 s median** |
| **fraction of wall-clock the DB is under a warmer pass** | 38 / 95.8 = **40 %** | 31 / 42.5 = **73 %** |
| **warmer backend-equivalents** | 0.40 × 1 = **0.40** | 0.73 × 4 = **2.9** |

Production runs at ~3 ACTIVE backends. **The warmer is now roughly a second production workload,
and that was not priced.** Concurrency 4 bought **1.2× wall** and cost **3.3× per-query inflation** —
the docstring's justification (*"I/O-WAIT bound, which is the one case where concurrency overlaps
waiting instead of multiplying work"*) is not what the numbers show. 40 concurrent trigram scans
against a 1 GiB `shared_buffers` contend for the pages they are all trying to keep resident.

⚠️ **This comparison crosses a code change and an index deploy** and the pre-fix per-rebuild figure
is derived from LAT-P060's pass timings rather than measured per query. It is strong enough to
refuse "just widen the concurrency" (queue option 1) and **not** strong enough to ship a narrowing.
The paired W-sweep that would settle it is a production experiment this lane cannot run; it is
registered in §3 as the next change, not guessed at here.

---

## §3 — REGISTERED PREDICTION (ruling 050) for the change this window SHIPS

Written before the code, graded next window. The change: **beat `30.0 → 10.0` s**, plus a
`MIN_PASS_PERIOD_SECONDS = 30` floor enforced inside the task, plus pure instrumentation.

**The reasoning, so the prediction can be wrong in a legible way.** The period is
`beat × ceil(wall / beat)`: at beat 30 with wall 27–38 s it quantises to **{30, 60}** and the 60 s
arm is what kills the duty cycle. At beat 10 the same wall quantises to **{30, 40}** — both under the
45 s TTL. The floor keeps a chained pass from running more often than every 30 s, which bounds the
load increase; without it, a fast pass could halve the period and double the warmer's DB duty.

**Cost, stated in advance:** the period tightens from a 42.5–51.7 s mean to ~40 s, so warmer DB work
rises **+6 % (against read B) to +29 % (against read A)**, bounded above at +42 % by the floor.
This buys head duty cycle with tail pressure, and §5 shows the tail is already the loser of that
trade — which is why the floor is in the change and why the head size is NOT touched.

| # | prediction | pass | HALT |
|---|---|---|---|
| 1 | `excluded_pre_warmed` **≥ 20 of 24**, mean of two runs, ceiling 24 | ≥ 20 | **≤ 16 HALTS** — beat quantisation was not the mechanism; the `P...P...` stretches are worker-queue latency, not the beat grid, and the fix is scheduling, not cadence |
| 2 | **`period_s` p95 < 45 s** across a ≥ 40-pass window (the new field; this is the real criterion row 2 should always have been) | p95 < 45 | **any `period_s` > 60 s HALTS** — the bistable `P...` stretch survived a 3× shorter beat, so it is not the beat |
| 3 | `seconds_wall` **unchanged, 27–39 s** | median within ±15 % of 30.9 s | **> 45 s** ⇒ the shorter beat is adding contention rather than removing dead time |
| 4 | `fresh` stays **0**; `expired` (the new field) goes **> 0 → 0** | `expired == 0` on every complete pass | **`expired > 0` on any pass with `period_s < 45`** ⇒ the TTL is not 45 s, or the drop is not reaching the key the route reads |
| 5 | tail control p50 **does not worsen by more than 25 %** vs this window's 2,053 ms (run-1, the un-degraded arm) | within +25 % | **> +50 % HALTS** — the load floor is not holding and the change is a net loss |

**Ceiling derivation (ruling 074 clause 2), taken this window, not quoted.** Row 1's ceiling is
**24 of 24**: LAT-P060 measured head membership at **8 of 8** for this arm and observed a round-0
result of 8/8 pre-warmed, so no round is structurally excluded. Row 2's p95 is over the task's own
`period_s`, whose maximum is unbounded and whose floor is the 30 s guard — so a p95 under 45 s is
demanding, not automatic.

**Explicitly NOT predicted, and not shipped:** any change to `WARM_CONCURRENCY`, `DEFAULT_HEAD_SIZE`,
or `REFRESH_AHEAD_SECONDS`' value. The W-sweep is the next queue's body and needs a paired
production A/B; §2's 3.3×-inflation figure is a reason to run it, not a result to act on.

---

## §4 — What this window ships

1. **`period_s` and `expired` in `last_result_summary`.** The pass currently cannot say how long it
   has been since the previous one, nor whether a rebuilt entry was *alive-but-stale* or *already
   dead*. Both questions were answered this window by inference from a client probe and a duration
   histogram; both should be answered by the task. Ruling 074's obligation, applied to the
   instrument that ruling 074 was issued about.
2. **Beat `30.0 → 10.0` + `MIN_PASS_PERIOD_SECONDS = 30`.** §3.
3. **`REFRESH_AHEAD_SECONDS`' docstring corrected** — the value stays, the refuted bound goes, and
   the inertness arithmetic is written down so the next reader does not tune a knob that cannot move.
4. **Item 3 cadence hygiene** (the beat file is open anyway): `precompute-admin-link-rate` and
   `precompute-admin-matured-linkage` `*/10 → */30`, `precompute-admin-audit-all` `*/15 → */30`.
   All three cache at `ex=3600`; the writer `setex`es unconditionally, so the caches DO extend and
   the waste is the only effect (LAT-P061's premise-check). Two refreshes per TTL instead of six.
   **~20 GB/day, 0.7 % — hygiene, not a fix, and it is not reported as one.** It also removes
   background read pressure from the pool the trigram indexes are losing, which is the only reason
   it is worth folding in rather than dropping.

`beat_schedule_change: **true**` (gotcha #12).

---

## §5 — Item (b): the #1866 TAIL, graded against LAT-P058 §8

The registered row, verbatim:

> **#1866's typeahead tail — 0–15 % improvement. Explicitly NOT predicted to be fixed.**
> **> 30 % ⇒ the continuous-throughput model is wrong**, the periodic-eviction model re-opens, and
> the next window must say WHICH model it now believes.

And the reasoning attached to it: *"Step 1 alone is not predicted to fix the tail … a 21 % cut in
read volume moves pool turnover from ~12.9 s to ~16.5 s, nowhere near enough to hold 579 MB of
trigram index resident."*

### The honest twist: "both halves" resolved to DDL-ALONE

The prediction was registered against **DDL + flag flip**. The flip is **withdrawn on measurement**
(ruling 076) and will never happen. So the intervention actually delivered is the DDL alone — which
is the *smaller* half by design, and therefore a **harder** test of a prediction that says "this
will not be enough". It grades either way, which is the point.

### Client-side: the tail did not improve

Same 8-query disjoint never-warmed arm as LAT-P059, same probe, `miss` `server` segment, rows with
`pre_warmed` excluded:

| capture | n | p50 | mean | min | max |
|---|---|---|---|---|---|
| **PRE-index** — LAT-P059 tail control, 09:31 PDT 2026-08-17 | 24 | **1,878.8** | 1,891.9 | 1,093.6 | 3,569.4 |
| POST run 1 — 13:13 PDT | 24 | 2,053.3 | 2,324.2 | 919.4 | 4,223.7 |
| POST run 2 — 13:17 PDT | 16 | 4,088.1 | 3,973.2 | 2,470.6 | 6,136.5 |
| **POST combined** | 40 | **3,234.9** | 2,983.8 | 919.4 | 6,136.5 |

p50 **+72.2 %** (worse). Bootstrap over 20,000 resamples: 95 % CI **[+25.9 %, +111.7 %]**;
**0.2 %** of resamples show any improvement at all; **0.00 %** reach the 30 % improvement that
would HALT.

⚠️ **The magnitude is NOT attributable and is not claimed.** Three live confounds, all named:
run 2 alone is 2× run 1 four minutes later (the instrument's own spread exceeds any effect being
measured — LAT-P061 said the same of the head arm); the pre-index capture is 09:31 and these are
13:13/13:17, and LAT-P056 established the tail swings by hour-class; and the post-fix warmer now
occupies the database **73 % of wall-clock at concurrency 4** where the pre-index capture faced
**40 % at concurrency 1** (§2). Run 2's 8 exclusions are one entire round flagged pre-warmed by
run 1's residency, so this window's own probing is in the reading too.

### The mechanism-level read, which has none of that noise

`pg_stat_statements` delta over a fixed **868.3 s** interval (`t0` 20:05:53Z → `t1` 20:20:21Z):

| | LAT-P058 baseline (pre-index) | LAT-P062 (post-index) |
|---|---|---|
| DB-wide physical reads | **79.1 MB/s** | **34.50 MB/s** |
| golf query `184240953744049829` | 516.7 MB/call | **2.629 MB/call** |
| golf share of all physical reads | **~19 %** | **0.105 %** |

### Verdict

| row | prediction | measured | verdict |
|---|---|---|---|
| DB physical read rate | 79.1 → **~62 MB/s** (a 21 % cut) | **34.50 MB/s** — a **56 % cut** | ✅ **PASS, and beaten** (caveat: different windows/hour-classes) |
| **#1866 tail** | **0–15 % improvement; > 30 % HALTS** | **no improvement — measured worse**, CI excludes improvement | ✅ **CONFIRMED. No halt.** |

**The prediction was right, and this window can now say why rather than merely that.** Freeing
**44.6 MB/s** — more than double the relief the prediction was built on — moved the typeahead tail
**not at all**. Read bandwidth was never the binding constraint: a **578 MB** trigram footprint in a
**1 GiB** `shared_buffers` is not made resident by other queries reading less, it is made resident by
nothing else sweeping the pool. `pg_statio_all_indexes` put those indexes at a **76.5 %** hit rate,
re-reading **170.9 MB of 578 MB in under three minutes** (LAT-P061).

**Which model do I now believe?** The question was conditional on a > 30 % improvement and does not
fire. Neither model is displaced: the continuous-throughput model **survives its own strongest test**
— it predicted no tail improvement from a read-volume cut and got exactly that, from a cut 2.7×
larger than it assumed.

**And the standing conclusion is reinforced, not weakened: the tail's fix is Option D**, the dedicated
typeahead index table (`lat-p057-tail-attack-design.md`) — a small resident structure instead of a
578 MB one nothing can hold. Needs a migration slot and a staleness sentinel in scope. Its own queue,
and after this window's numbers it should be the next one.

---

## §6 — Item 1: the gold read, with its corpus-delta line (ruling 073, FIRST paired use)

Two windows owed; taken first this window per the directive. Producer against production
`1eb968ee`/v3829: **46 probes, 46 fetched, 0 failed, `evidence_fidelity: exact`.**

| | LAT-P059 (`3fce7867`) | **LAT-P062 (`1eb968ee`)** |
|---|---|---|
| pass / fail / xfail / xpass / regression | 41 / 3 / 1 / 1 / 0 | **41 / 3 / 1 / 1 / 0** |
| `entity_top_1_rate` | 0.9130434782608695 | **0.9130434782608695** |
| MRR | 0.9347826086956522 | **0.9347826086956522** |

**CORPUS-DELTA: `changed: 0`.** No probe moved disposition. `corpus_moved: 0`, `real: 0`,
`confounded: 0`, `unattributable: 0`, `new_probes: 0`, **`baseline_may_move: true`**.
`--code-changed` not passed, correctly: no ranking code shipped between the two reads.

**Reported because the ruling says report it either way** — a clean corpus-delta is exactly as much
of a result as a quarantining one, and it is the read that shows the instrument runs in anger. The
three standing failures are unchanged specimens, not new: `search-gold-ai-001` (expected entity not
even eligible, `pool_size` 7), `search-gold-inflation-001`, `search-gold-nba-finals-001`, plus the
standing `search-gold-fed-001` xpass. Exit code **1**, which is the standing fail/xpass state, not a
regression.

### ⚠️ The limit of this first paired use, stated so it is not over-read

**LAT-P059's artifact predates ruling 073 and carries NO `pool_fingerprint`** — its `details` rows
hold only `probe_key / probe_version / query_class / code / disposition / expected_rank /
reciprocal_rank`. `classify_disposition_changes` inspects fingerprints **only for probes whose
disposition moved**, and none did. So the `UNATTRIBUTABLE-NO-FINGERPRINT` path — the one the ruling
added — **was never exercised**. Today's read is clean; it is not yet proof that attribution works.

**This window's artifact is the first with fingerprints on all 46 probes**
(`capture-lat-p062-gold-read-v3829.graded.json`), so it is the comparison target that makes the NEXT
read attributable. Use it, not LAT-P059's.

**Baseline unmoved**, as the ruling requires: nothing was quarantined and nothing was re-baselined.

---

## §7 — Item 2 (c): the head's provenance, re-measured and FILED as **#1916**

Not a ranking change, per the queue and the directive. Filed as a **provenance flag at write time**,
with the issue stating in its own heading that **head tuning is BLOCKED** until it lands.

| source | contamination | measured this window |
|---|---|---|
| `search:trending:24h` | **~89 % the warmer's own echo** | warmer successes/24 h **1,842**; trending `red sox` 1,855 · `celtics` 1,845 · `yankees` 1,844 · `world cup` 1,842 · `patriots` 1,831 |
| `search_query_logs` | **23.6 % gold-sentinel (#1206)** | **848 of 3,600** rows in one 07:09–07:12 UTC minute; 212 distinct queries / 30 days |

Independent corroboration by **rate** rather than stock: over 72 minutes the top four each gained
**~140–143** votes ≈ 2/min, against ~1.15 warmer passes/min. **This window's own probe runs
contributed ~9 of those votes**, which is the thesis demonstrating itself.

⚠️ **Unresolved and load-bearing, carried into the issue:** `zincrby` is followed by `expire(86400)`
on **every** write, so `:24h` is not a rolling window and the key should be immortal under the
warmer's cadence — yet ~1,850 at ~2/min implies ~15 h of accumulation. Something resets it and
nobody knows what. A key whose retention mechanism is unidentified is not a measurement instrument.

⚠️ **Hazard this window's own change must respect, and does:** `/typeahead` votes into the zset on
the **miss path only** (`events.py:4790`), and the warmer misses every time (`rebuilt: 40`). Any
change that lets warm passes HIT would silently stop the voting and freeze the head. The beat/floor
change in §4 does not alter the drop-then-call path, so the voting is unchanged — checked before
shipping, not after.

---

## §8 — Owed, with receipts (ruling 066)

| owed | why it could not be taken | exit condition |
|---|---|---|
| **`hard_kills_24h` on a clean 24 h** | read **2**, unchanged from LAT-P061's read, over a window spanning both codebases — v3829 released 12:30:40 PDT today | re-read `task-metrics?task=warm_typeahead` at **≥ 12:30 PDT 2026-08-18**. `soft_time_limit=100` / `time_limit=115` against a measured max of 38.1 s is adequate; a rise means the shorter beat is stacking passes |
| **the W-sweep** (`WARM_CONCURRENCY` 1 / 2 / 4 paired) | requires setting a production constant and deploying, three times; this lane does not deploy | a queue with a config-var or a deploy slot. Grade on `seconds_total` **and** `seconds_wall` together — §2's whole point is that they moved in opposite directions |
| **`period_s` / `expired` in production** | shipped this window, not yet deployed | after the merge deploys, `task-metrics?task=warm_typeahead` → `last_result_summary` carries both. **Their ABSENCE means the old code is deployed and §3 does not grade** |
| **the second paired gold read** | needs a *second* fingerprinted artifact; this window produced the first | next window: `--compare-against docs/audits/latency/capture-lat-p062-gold-read-v3829.graded.json` |

---

## §9 — Gates, including the ones that did NOT run

| gate | result |
|---|---|
| **full backend suite** | **15,859 passed · 65 skipped · 3 xfailed · 0 failed** in **691.72 s**. **`PYTEST_EXIT_CODE=0`**, written into `/tmp/lat-p062-fullsuite.log` and read back **from the file** — never piped (gotcha #54), and the value is `0`, not a non-1 harness story (#124). Ran concurrently with another lane's pytest, which is why it took 11m32s rather than the usual ~11m. |
| focused: `test_typeahead_warmer.py` + `test_tasks_wiring.py` | 77 passed, `PYTEST_EXIT_CODE=0`. The wiring allowlist needed no edit — no task names were added or removed, only three schedules and one float changed. |
| focused: `test_product_brain_integrity.py` | 158 passed, `PYTEST_EXIT_CODE=0`. Ledger snapshot named per ruling 063: `digest=e43dc0e247bc`, `mtime=2026-08-17T20:14:45Z`, `claims=48`, `deviations=0`, `dropped=0`. |
| **mutation testing** | **8 of 8 caught.** Each mutation was asserted to have APPLIED before the run, and the source was verified byte-identical to its backup afterwards. |
| ruff | **zero added** — 5 findings on master for the three changed files, 4 after. All pre-existing `E402`. |
| `git log origin/master..HEAD` | checked before **every** commit (gotcha #47): only this window's own commits, no sibling passengers. |

### The eight mutations, and what each one proves

| # | mutation | caught by |
|---|---|---|
| M1 | drop the negative-delta guard in `_seconds_since_last_pass` | `test_a_future_previous_start_does_not_suppress_the_pass` — a future stamp makes the gap negative, which compares `< 30` and suppresses **every** pass forever while reporting a tidy `skipped` |
| M2 | `expired` counts every non-positive TTL (`<= 0`) instead of `== -2` | `test_expired_counts_only_a_missing_key_not_every_non_positive_ttl` — folds `-1` (no expiry) and `None` (Redis silent) into the number a duty-cycle grade rests on |
| M3 | floor-skip does not release the run-lock | `test_the_floor_releases_the_lock_it_took_to_check` — `_LOCK_TTL_SECONDS` (120 s) would wedge the warmer for 4× the floor |
| M4 | unknown `period_s` reported as `0.0` instead of `None` | `test_an_unknown_previous_start_does_not_suppress_the_pass` — zero reads as two passes starting at the same instant |
| M5 | `_record_pass_start` never called | `test_a_pass_records_its_start_so_the_next_one_can_measure_it` — every subsequent `period_s` unknown and the floor unenforceable |
| M6 | floor not enforced at all | `test_the_floor_suppresses_a_pass_that_is_too_soon` |
| M7 | beat reverted to 30 s | `test_the_pass_period_the_beat_can_produce_fits_under_the_ttl` |
| M8 | beat set to 15 s | same test — **period 45 == TTL, zero margin.** This is the mutation worth having: 15 s *looks* like a fix and is not one |

### Gates that did NOT run, named rather than implied (ruling 065)

| gate | why | addressee |
|---|---|---|
| **frontend `npm run build` / `typecheck` / `jest`** | **zero frontend files changed.** Not applicable, not skipped. | — |
| **`xcodebuild`** | **zero native files changed.** Not applicable. | — |
| **real-Postgres tests** | no local Postgres in this sandbox (`initdb` dies on `shmget`). CI-only, as always. | **Integrator** — declared owed, not implied |
| **the deployed read of `period_s` / `expired`** | this lane does not deploy. The registered prediction in §3 grades **after** the merge releases. | **LAT-P063**, with the exit condition in §8 |
| **`hard_kills_24h` on a clean 24 h** | v3829 released 12:30:40 PDT today; a clean window does not exist yet | **LAT-P063**, any read after 12:30 PDT 2026-08-18 |

⚠️ **BASE DRIFT, stated because gates prove something about the commit you TESTED.** These gates ran
on base **`1eb968ee`**. If `origin/master` has moved by the time this is integrated, do **not** read
this green suite as green on the newer tip — the Integrator rebases and re-certifies
(PROGRAM-LANES rule 2).
