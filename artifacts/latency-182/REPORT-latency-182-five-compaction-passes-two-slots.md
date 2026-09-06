# latency/182 — the search box stops going cold every morning

**PILLAR: DISCOVER. SHIP: the search box stops going cold every morning.**

Written 2026-09-06, session start 08:03Z / 01:03 PT (PT = local `date` minus 3h, notice 24,
verified with `TZ=America/Los_Angeles date`).

Branch `program/latency-247-the-search-box-stops-going-cold-at-dawn`, PR **#3483**,
issue **#3480**. Two commits: the LAT-P242 rider (#3466), then the stagger.

---

## 1. The one paragraph

`worker-background` is Standard-1X `--concurrency=2`. Six of its beats declare a
`soft_time_limit` of half an hour or more, and five of them could be resident at the same
time. `warm-typeahead` publishes onto that same pool every 10s with `expires: 120`, so a
fire that cannot reach a slot inside two minutes is discarded — and through the window
every one of them was. The 65s response TTL lapsed, and the head of the search box went
cold. The fix moves five beats so that no two long-hold beats can be resident, changing no
cadence, no `kwargs` and no queue, and adds a guard that re-derives the whole table from
the live schedule so it cannot rot.

## 2. What was measured, and how

### 2.1 The collision — enumerated, not eyeballed

The directive said to enumerate the fire times rather than read the cron by eye, and it was
right to: `crontab(minute=30, hour="*/6")` and `crontab(minute=45, hour="*/6")` *look*
fifteen minutes apart, and are — but both tasks declare a 3600s hold, so "fifteen minutes
apart" is the reason they collide, not the reason they do not.

Read from celery's **own parsed field sets** (already expanded from the `"*/6"` string, so
a mis-read of cron syntax cannot enter), against each task's **declared** soft limit:

| UTC | entry | task | declared soft limit |
|---|---|---|---|
| 06:30 | `collapse-odds-snapshots-daily` | `collapse_snapshots` | 1700s |
| 06:30 | `turbo-collapse-futures` | `turbo_collapse_futures` | 3600s |
| 06:35 | `collapse-winprob-snapshots-daily` | `collapse_snapshots` | 1700s |
| 06:40 | `collapse-futures-snapshots-daily` | `collapse_snapshots` | 1700s |
| 06:45 | `turbo-collapse-odds` | `turbo_collapse_odds` | 3600s |
| 06:55 | `precompute-bookmaker-calibration` | — | 1800s |

**Worst case: six long-hold residents at 06:55Z against two slots. 168 overlapping
window-pairs in any 7-day span.** `00:45 / 12:45 / 18:45` put the two `turbo` grinders on
both slots three more times a day.

The sixth beat was not in the directive's table and is the one that matters for anyone
re-deriving this: **`precompute-bookmaker-calibration` (soft 1800, :55 of 0/6/12/18) is
also a long-hold `background` beat**, and its window sits *inside* `turbo-collapse-futures`'
old one at every one of its four daily fires. Scoping the check to "the compaction beats"
would have missed it. That is why the guard is derived by **threshold**, not by name.

The codebase already stated the consequence, in its own words, at
`app/tasks/__init__.py` above `turbo_collapse_futures`: they "may hold **half the
background pool for a full hour**, four times a day", and they "fire :30 and :45 of the
same hours, so a long pair can hold BOTH slots simultaneously — a scheduled, total
background outage window with nothing else able to run." Nothing enforced it, so it stayed
true. **A comment is not a guard.**

### 2.2 The user-visible half — measured on production, at a quiet hour

`/api/admin/typeahead-warmer/last`, 2026-09-06 07:35–08:02Z. This is a window with **no
compaction resident**, so it is the floor rather than the outage:

| pass (UTC) | warmer period | head terms expired (of 40) |
|---|---|---|
| 07:38:49 | 118.5s | **40** |
| 07:43:43 | 116.2s | **40** |
| 07:53:47 | 166.9s | **40** |
| 07:58:37 | 91.4s | **40** |
| typical | ~40s | 2 |

The relationship is clean and one-directional: **whenever the warmer's period crosses ~90s,
the entire 40-term head is cold.** Four times in 26 minutes, at 1am Pacific. Ring-level:
`passes_with_loss: 32` of 32, `expired.total: 273`, `period_s` p95 **116.2s** against a 65s
`response_cache_ttl_s`.

A cold head term costs **1094.5ms with 710 shared read blocks** against **27.1ms with 0** —
numbers already recorded in the `warm-typeahead` beat entry, not re-derived here.

`turbo_collapse_odds` on production today: `last_started_at` **06:46:42Z**,
`last_success_at` **07:11:34Z** — one beat holding one of two slots for **24.9 minutes**,
starting inside the window this ship removes.

### 2.3 Why staggering and not a topology change

179's rule (tt): relieving one contributor in an oversubscribed queue reallocates the wait.
This is not that move. It removes a **scheduling coincidence**, which is provably better at
*any* utilisation and therefore does not depend on first knowing the total. That is exactly
why it can ship before the demand instrument is live, and why the instrument can ride it
rather than gate it.

A third slot is a dyno purchase — `background`'s two slots are a **memory** bound
(2 × 200MB + ~100MB ≈ 512MB Standard-1X exactly) — and is Alex's call, not proposed here.

## 3. The change

Five beats move. Every cadence, every `kwargs` and every queue is preserved.
`precompute-bookmaker-calibration` is scheduled **around**, never moved: its :55 slot is
load-bearing for the hourly `precompute-calibration-main` (:15) that consumes its key, and
that file is the calibration lane's under D45.

```
00:55–01:25  precompute-bookmaker-calibration   (unchanged)
01:40–02:40  turbo-collapse-futures             (was :30 of 0,6,12,18)
03:30–04:30  turbo-collapse-odds                (was :45 of 0,6,12,18)
04:40–05:08  collapse-odds-snapshots-daily      (was 06:30)
05:15–05:43  collapse-winprob-snapshots-daily   (was 06:35)
05:50–06:18  collapse-futures-snapshots-daily   (was 06:40)
```

Zero overlaps over 7 days, swept across five fixed anchors spanning a year.

## 4. The guard, and why it cannot rot

`backend/tests/test_lat_p243_compaction_stagger_3480.py` (29 tests) plus
`residency_overlaps` / `long_hold_beats` / `crontab_fire_times` in
`app/utils/schedule_adherence.py`, beside LAT-P242's `beat_queues`.

- **It transcribes no time.** Both the guarded set and the windows are re-derived from the
  live `beat_schedule` and each task's declared `soft_time_limit`.
- **It is derived by threshold, not by name** (`LONG_HOLD_SOFT_LIMIT_S = 1200`). The actual
  distribution has the long holds at 1700/1800/3600 and the next beat below at 900, so 1200
  separates two populations with margin either side rather than cutting a cluster. A new
  background beat declaring a long hold is covered the moment it is added.
- **The window is the declared limit, never a sampled duration.** A bound taken from a
  measured maximum has been refuted twice in this program by the next sample; a declared
  limit cannot be, because exceeding it is what the limit prevents.
- **An unenumerable schedule returns `None`, not `[]`,** and is reported as a hole. `[]`
  would read as "never overlaps", which is the one answer that is certainly wrong for a
  beat nobody can enumerate.

**Non-vacuity is tested, not asserted.** The detector is fed the exact parent schedule at
`e34a6ce8` and required to find it (≥100 pairs, three named pairs, and the six-deep
06:55Z pile-up), and separately an injected two-beat overlap.

| gate | result |
|---|---|
| subject guard on head | **29/29 pass** |
| subject guard against the exact parent schedule | **fails 5/29** |
| mutation battery on the new derivation | **13/13 killed** |
| consumers of touched symbols | **585 green** |
| files / alembic / frontend | 3 / none / none |

The mutation battery found two real gaps and one of its own: `min(e_a, e_b) -> e_a`
survived because every fixture pair declared the *same* soft limit, so the two expressions
agreed by construction — the r_guard_rederives shape. Both closed; see the second commit.

## 5. Filed, not fixed

**#3481 — `turbo_collapse_futures` reads all 195.6M rows of a 52 GB table to choose 5,000
partitions.** The directive said to check the defect class before rescheduling, on the
grounds that if the work is cheap the collision stops mattering. It is not cheap, and the
reason is worth the paragraph:

```
Limit               Total Cost 9,024,690
  Sort / Unique / Incremental Sort / Aggregate x2
        Hash Join                             rows 114,986,799
          Seq Scan futures_odds_snapshots     (parallel, 114,986,799 rows)
```

against **20,422** for the `odds` sibling and **19,163** for `winprob`, whose discovery
query is the same shape *without* the `ORDER BY priority`. The prioritisation — added
deliberately and for a good reason — makes the `LIMIT` unpushable, so the limit buys
nothing and the whole table is read. **442× its own sibling.** The per-partition collapse
is fine; `idx_fos_outcome_captured` and `ix_odds_snap_evt_bk_time` cover it. This is
entirely the discovery step.

It is a bigger win than the stagger and it is a separate ship: it changes which rows a
destructive pass selects, over a 52 GB table, and the cheap candidate shape leans on an
early stop that needs an `ANALYZE` read before anyone believes it. **#3480 does not depend
on it and does not claim it.** Whoever takes #3481 should re-measure the window afterwards
rather than assume the two compose.

**#3364** — cross-linked, not claimed. `warm_search_head` (`expires: 20`) and
`precompute_discover_candidate_base` (`expires: 120`) both publish onto the same pool and
both read "0 delivered". The stagger removes the largest single cause of the delivery
latency their bounds are compared against, so #3364 should be re-measured after this
deploys: a still-zero count then becomes evidence about the bound rather than about the
outage. The generalisation — *an `expires` bound must be compared against delivery latency,
not against the task's own wall* — belongs in `_EXPIRING_WARMER_BEATS` and is the natural
next ship.

## 6. What is still owed on this ship

**The catching proof CERT-2038 demanded** — "a saturated-queue before/after showing
`warm_typeahead` delivered before 120s expiry and representative `sta`/`red` requests
returning cached answers within the ship's latency bound".

The warmer ring holds 32 passes spanning ~26 minutes, so today's 06:30Z window was already
unrecoverable when this session started at 08:03Z. A sampler is therefore running to
capture the **next** one from the outside:

- `.lat182-sampler.sh` → `.lat182-warmer-samples.jsonl` (untracked, in the latency
  worktree), started 08:04Z, running to **15:10Z**, one sample every ~5 minutes.
- Each sample carries the full warmer ring, `task-metrics` for
  `turbo_collapse_futures` / `turbo_collapse_odds` / `warm_typeahead`, and **four real
  `/api/events/typeahead` requests** (`sta` and `red`, twice each) with `time_total`.
- **BEFORE** = the 12:30Z + 12:45Z window, where the two `turbo` grinders hold both slots
  under the parent schedule.
- **AFTER** = 13:40Z, the first fire under the new schedule if this lands before then —
  `turbo-collapse-futures` alone, with the second slot free.

That is a paired comparison about an hour apart on the same day, which is a better control
than a day-over-day read. **Read the file before presenting this ship.** If it deploys
after 13:40Z, the next clean AFTER is 15:30Z (`turbo-collapse-odds` alone), then 19:40Z.

## 6b. A live reproduction of 180's baseline, taken as this ship's control

Not a finding — 180 banked these numbers at `9dc0fd0e` and `2b6e82ac`'s message already
names the mechanism. Recorded here because it is the **control** that keeps this ship's
claim honest, and because it was still true five hours later.

Production, 08:24Z, one second between calls, `time_connect` < 1ms on every line:

```
/api/health                          #1 0.135s   #2 0.369s    <- network is fine
/api/events/typeahead?q=stanley cup  #1 2.027s   #2 0.152s    <- caching WORKS
/api/events/typeahead?q=red sox      #1 4.320s   #2 0.146s    <- caching WORKS
/api/events/typeahead?q=sta          #1 7.424s   #2 8.081s    <- never caches
/api/events/typeahead?q=red          #1 7.868s   #2 6.690s    <- never caches
```

`/api/admin/task-metrics?task=warm_typeahead` at 08:40Z names the same two terms from the
inside: `terminal: partial`, `completed: 38 / total: 40`, `timeouts: []`, `errors: []`,
**`no_writes: ['sta', 'red']`** — the warmer's own DEFECT category, on every single pass.

**Why this matters to #3480 specifically: it is the thing this ship does NOT fix, and a
grader who checks `sta` will correctly find nothing changed.** Short prefixes are cold
because the route never writes them (#3399, CERT-2037, GREEN with exact-sha CI since
07:51Z, still unmerged at 08:40Z). #3480 is about the *warmer* being able to reach a worker
slot at all. Two different halves of one symptom, on two different shas, and conflating
them would let either one take credit for the other's evidence.

## 7. Carried over, not done

- **#3399 / CERT-2037 has still not landed.** `9dc0fd0e63de5665235287206fc52297646c2396`,
  GREEN with exact-sha CI `completed/success` (run `34019461018`), notice-13 grep passes, no
  supersedes row, PR #3441 MERGEABLE, no alembic. The integrator holds
  `LANE-integrator.lock` (pid 71476, alive, INTEGRATOR-228) and 181's pre-checked note is in
  their inbox. Not merged from here: merging into a held lock is the CERT-793-class race.
  **Its post-deploy check is still owed** — `GET /api/events/typeahead?q=sta` twice ~2s
  apart, the second a warm hit where both used to be 5–8s; if it is not warm, check
  `last_outcome.head` first, since the ring truncates that list to 12 while the task-metrics
  summary carries all 40.
- **ITEM 3 guard debt is untouched.** `TYPEAHEAD-SHED-RUNTIME-CACHE-CONTRACT` and
  `LAT-P240-PREDICATE-SEMANTICS-GUARD` both still owed; 181's notes on why the first is hard
  (three test files drive `typeahead_search` with `db=None` and never reach the MISS path;
  the debug flags' declared defaults are `Query(...)` markers and are **truthy** outside
  FastAPI) stand and were not re-derived.

## 8. Rules this queue adds

**(hhh) A comment that names a failure is not a guard against it.** The consequence fixed
here was written out in full, in the codebase's own words, directly above the task that
caused it — "a scheduled, total background outage window with nothing else able to run" —
and it stayed true for as long as the comment did. Prose that describes a hazard costs
nothing to keep accurate and buys nothing when it is; the moment you can write the sentence,
you can usually write the assertion.

**(iii) Scope a co-residency check by THRESHOLD, never by the family you came for.** The
investigation was handed "five compaction beats". The set that actually shares the pool is
six, and the sixth belongs to another lane, sits inside the biggest offender's window at
all four of its daily fires, and would never have appeared in a check scoped to tasks with
"collapse" in the name. Derive the population from the property that makes it dangerous —
here, a declared hold long enough to lose half a two-slot pool — and the members you did
not know about are covered before you learn their names.

**(jjj) An `ORDER BY` over a `LIMIT`ed scan can silently convert a bounded read into a
full-table aggregate.** `LIMIT 5000` over 195.6M rows read as a bounded pass, and the
`Node Type` was not the tell either. The tell was `Total Cost` — **9,024,690 against 20,422
for the same query shape on a sibling table**, the only difference being a two-level
`ORDER BY` that has to rank everything before it can know what the first 5,000 are. When a
prioritisation is added to a limited scan, the limit stops being a bound.

**(kkk) When every fixture in a battery declares the same value for a parameter, an
expression over that parameter is untested.** `min(e_a, e_b)` and `e_a` are the same
function when both windows are the same length, so the mutant survived against a suite that
otherwise killed twelve of thirteen. Vary the thing the expression discriminates on, or the
expression is decoration.
