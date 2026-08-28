# LAT-P101 — the live Sports tab stops going cold once a minute (#2236)

**Pre-registration.** Written before any post-deploy measurement exists and
frozen here so the grade cannot be chosen after the numbers arrive.

⚠️ **Honest scope of this pre-registration, stated first.** LAT-P100's
pre-registration was written *before a line of the build*. This one was not —
the mechanism in #2236 is fully diagnosed in the issue, the fix followed
directly from it, and the build was done before this file. What is genuinely
frozen here is the **post-deploy prediction and its bars**, which is the part
that can be gamed after the fact. The build cannot be, because it is in the
diff. Calling this a full pre-registration would be claiming a discipline that
was not exercised.

---

## 1. The ship, in user-visible terms

**A person who opens the Sports tab while a game is in progress no longer waits
seconds for it, once a minute, at random.**

That is the whole thing. Not "the pre-warm covers live shapes" — that is the
means. The user-visible fact is that the tab currently has a 60-second cycle in
which somebody eats a full cold rebuild, and whoever that somebody is sees a
spinner for **2.5–4.0 seconds** on a tab that otherwise paints in **0.3 s**.

## 2. The mechanism, restated so the bars below make sense

Two changes shipped 2026-08-27, both correct:

* **#2216 / q412r** (master `b71e2c0d`, v3910) — a feed payload containing a
  live card is capped at `ttl 30 / stale 60`. Past 60 s it is REBUILT, not
  served older. Serving a 330 s-old live score was the bug; this is the fix.
* **LAT-P099** (master `e4c87d52`, v3911) — enrolls the native Sports shape in
  `FEED_PREWARM_SHAPES`, hosted inside the every-**120 s**
  `precompute_discover_candidate_base` beat.

`120 > 60`. The key dies a full minute before its next chance to be refreshed,
so the warm rail structurally cannot keep a live shape warm — and it reports
success on every pass, because it genuinely does warm the key. It just warms one
that is already gone by the time it matters.

**Nothing in the codebase compared those two numbers.** The 60 lives in
`app/utils/feed_cache.py`; the 120 lived in `app/tasks/__init__.py`'s beat
schedule. Neither was expressed in terms of the other, so neither author could
have been warned. That, and not the sawtooth, is the defect class.

## 3. Baseline, measured on the deployed slug BEFORE the fix

Slug `56dbbfa5` (current master, contains both halves), uptime > 900 s so
outside the post-deploy window. Anonymous `GET /api/feed`, no `x-session-id`.
Raw capture: `lat-p101-2236-prefix-sawtooth.txt`, taken with
`backend/scripts/measure_live_feed_sawtooth.py`.

**6 minutes, 10 s interval, 31 samples per shape. 31 of 31 live on both.**

| shape | live | **MISS** | warm p50 | cold misses (ms) | max score age |
|---|---|---|---|---|---|
| `limit=50&mode=sports` | 31/31 | **4/31** | 608 ms | 2,606 · 2,768 · 3,513 · **4,558** | 56.5 s |
| `limit=20&mode=sports` | 31/31 | **4/31** | 382 ms | 895 · 1,108 · 1,892 · **2,315** | 58.6 s |

Every sample carried `cache.live: true`, `ttl_seconds: 30`,
`stale_ttl_seconds: 60`, so #2216's ceiling is firing exactly as designed and
this is a measurement of a live-containing payload, not of a quiet night. The
`max_age` of **56.5 / 58.6 s** is the ceiling being reached, sample after
sample — the key is not being refreshed, it is running out.

**One user in roughly eight waits 2.6–4.6 seconds for a tab that serves everyone
else in 0.4 s.** Read the cycle directly in the raw capture: `hit → hit →
stale_hit → stale_hit → stale_hit(56.5 s) → **miss (3,513 ms)** → hit`, repeating.

⚠️ **The cold number is 2–3x worse than #2236 recorded** (the issue measured
1.0–1.5 s, 14.4 s once). Not a contradiction — a different hour with different
DB buffer state, and the issue's own first sample was 14.4 s. Both are in the
record; the prediction below grades on the *presence of misses*, not on their
duration, precisely because the duration is the number that moves with
conditions nobody controls.

⚠️ **The first capture attempt is recorded rather than discarded**: it ran a
shell loop whose per-sample subprocess overhead made its `t+` column
untrustworthy against wall clock, and it was cut off at t+86 s before the hole
appeared. Its *cache states and cold timings* stand (they are read from headers
and from `cache.built_at`, not from the loop's clock); its cadence does not.
That is why the instrument was rewritten as a script.

## 4. THE FIX — the invariant, not the number

The period is now declared in `app/utils/feed_cache.py`, three lines under the
ceiling it must respect, and the arithmetic binding them is a function:

```
FEED_LIVE_REPUBLISH_PERIOD_S (40) + FEED_LIVE_REPUBLISH_BUDGET_S (20)
    <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS (60)
```

Read as a worst case: a pass fires at t=0 and publishes a payload whose stale
mirror dies at t=60; the next pass fires at t=40 and may burn its entire 20 s
budget before publishing. Even then it lands at t=60, on the boundary. The
budget term is not headroom — it is the second term of the invariant, which is
why a change to it is a change to the correctness argument.

`test_a_republish_pass_lands_before_the_previous_one_expires` fails on **every**
way of reintroducing #2236: lengthening the period, widening the budget, or
shortening the ceiling underneath both. Proven red both directions before this
file was written (§7).

The new beat `prewarm-live-feed-shapes` republishes **only the shapes the last
warm observed to be live**, through the same `_prewarm_feed_shape` the 120 s
pass uses — one writer, so the warmed key cannot drift from the read key
(LAT-P001's defect) and the live ceiling cannot be applied twice differently
(#2216's defect).

## 5. THE PREDICTION — frozen, graded post-deploy

Taken after the release reaches production, **uptime > 300 s** (a read inside
the post-deploy window is not evidence), and after at least one 120 s pass has
run so the live set is populated. Run:

```
source ~/.claude/.env
python3 backend/scripts/measure_live_feed_sawtooth.py --minutes 6 --interval 10
```

| bar | claim | grade |
|---|---|---|
| **B1** | Across a ≥ 6-minute window (≥ 6 ceiling-widths), `X-Feed-Cache: miss` occurs **0 times** on `limit=50&mode=sports` after the first sample | the ship |
| **B2** | Same, `limit=20&mode=sports` | the shape LAT-P099's lesson says must be checked too |
| **B3** | Every served sample carries `cache.live: true`, `ttl_seconds: 30`, `stale_ttl_seconds: 60` | the ceiling is still enforced — the fix must not have bought latency with staleness |
| **B4** | `max(cache.built_at age)` over the window **≤ 60 s** | #2216's actual contract, on the age of the SCORE (CERT-409), not of the copy |
| **B5** | `prewarm_live_feed_shapes` shows `starts_24h > 0` and `successes_24h > 0` in `/api/admin/celery/task-metrics` | the beat is firing at all |

**⚠️ The disqualifying condition, named in advance.** If **no sample in the
window reports `cache.live: true`**, the run grades NOTHING — in either
direction. A quiet night produces `ttl 60 / stale 300` payloads that the 120 s
pass has always covered, and a clean run of zero misses under those conditions
would be a measurement of the *old* code working as designed. The script refuses
to grade such a run and says so in its own summary. **Do not report a green from
a window with no live cards.**

**⚠️ B1 is not satisfiable by the first sample.** The very first request after a
release always misses. The bar is on the REPEATING hole, which is what #2236
is.

## 6. What would falsify the whole approach

* Misses persist at ~60 s intervals ⇒ the live set is empty when it should not
  be, i.e. `payload_contains_live_event` disagrees with what a user sees as
  live. Read `bainluck:precompute:feed_live_prewarm:last` — `live_labels: []`
  during a live game is that failure, and it is distinguishable from "the beat
  never ran" only because the idle pass writes its report too.
* Misses persist at ~120 s intervals ⇒ the new beat is not firing (check
  `starts_24h`), or its messages are being discarded by `expires`.
* `realtime` queue depth climbs above 0, or Tier 1 odds polling starts missing
  its 32 s cadence ⇒ the cost model in §7b is wrong and the beat must be
  reconsidered, not tuned. That is the one outcome that would send this back to
  option 3 in #2236 ("accept it and grade the cold path"). The lever is
  `SET discover_feed_live_prewarm:enabled 0`, which needs no deploy.

## 7. Beat cost — DECLARED, and the worst case is not small

`beat_schedule_change: **true**`. A new beat entry, `prewarm-live-feed-shapes`,
40 s period, **`realtime` queue**, `expires: 40` (one period).

### 7a. The queue is part of the correctness argument, not of the cost one

**This was going to be `background`, and that would have made the fix partially
inert.** The invariant `PERIOD + BUDGET <= 60` assumes the pass *starts* at its
period. `background` is documented in `app/tasks/__init__.py` as having
**~one effective slot for ~45 beats** ("price a new background beat against one
slot, never two"), is measured at **~90 % slot occupancy**, and its own budget
module says ordinary co-tenant bursts produce **multi-minute waits**. A pass that
starts two minutes late publishes nothing in time — the key expired and the user
already paid the cold build.

And the failure would have been silent in the #2236 way: the beat reports success
on every pass it eventually runs.

`realtime` is the queue whose stated purpose is *"high-frequency tasks driving
user-visible live game data. Never blocked by batch jobs."* That is this task,
exactly. Both routing surfaces say `realtime` (beat `options` override
`task_routes`, so agreement is not redundant), asserted by
`test_the_pass_runs_on_realtime_and_not_on_background`.

**The background census is therefore UNMOVED** — re-derived from the assembled
schedule, not by delta (#1910): explicit **57**, fall-through **45**, total
**102**. `BACKGROUND_BEAT_COUNT` is untouched.

### 7b. The cost, on the queue it actually lands on

**Modelled, not measured** — the task does not exist in production yet, so there
is nothing to read.

| regime | passes/day | builds/pass | s/build | slot_s/day | % of the 4-slot realtime pool |
|---|---|---|---|---|---|
| idle (no live cards) | 2,160 | 0 | — | **~110** (one `HGETALL` + one `SETEX`) | ~0.03 % |
| working figure: 8 h/day, 2 live shapes | 720 | 2 | ~1.2 | **~1,830** | **0.5 %** |
| all 5 feed shapes live, all day | 2,160 | 5 | ~1.2 | **~12,960** | **3.8 %** |
| pathological (every pass burns its budget) | 2,160 | — | 20 s | **43,200** | 12.5 % |

* The **declaration bar** is `slot_seconds_per_day >= 3600`. The working figure
  (~1,830) is under it; **the all-live case (~12,960) is over it by 3.6x**, which
  is why this is declared rather than waved through. `realtime` runs
  `--concurrency=4` (345,600 slot-s/day) against `background`'s effective one
  slot, so the same work is 3.8 % of the pool here and would have been ~15 % of
  one background slot.
* `pct_of_soft_limit`: worst single pass 20 s budget against a 28 s soft limit
  = **0.71**, under the 0.80 bar. Hard limit 35 s < the 40 s period, so two
  passes can never overlap — what makes an overlap lock unnecessary rather than
  merely unlikely.
* **What it displaces on `realtime`, named.** Its co-tenants are the odds and
  live-score pollers (`poll_sport_odds` 32 s Tier 1, `sync_espn_live_events`
  30 s, `poll_live_prediction_markets` 2 min). At ≤ 0.5 slots of 4 in the
  pathological case, this cannot close the queue; the quota-critical polling path
  keeps ≥ 3.5 slots in every row above. If it turns out otherwise the falsifier
  is in §6 and the remedy is the kill switch, not a tuning pass.
* **The trade, stated plainly.** This spends ≤ 3.8 % of the realtime pool to stop
  a *web dyno* from building the same payloads synchronously while a person
  waits. The work is not new; its placement is. On the worker it costs a slot; on
  the request path it costs someone 2.6–4.6 seconds.
* **NOT CLAIMED, because it is not measured:** the 2nd–5th builds within one pass
  likely reuse #2143's process-local shared concept artifact
  (`app/utils/principal_independent_cache.py`, 60 s TTL), which would put the
  all-live row well under the linear model. The model deliberately assumes no
  reuse. Whoever wants the smaller number must measure it.

The **host** beat's cost is unchanged: no target added, no budget moved,
`FEED_PREWARM_PASS_BUDGET_S` still 80 s.

## 8. Rollback

Revert the commit. Nothing outside the repo to unwind — no config var, no
migration, no schema, no index. The one new Redis key
(`bainluck:precompute:feed_prewarm:live_shapes`) expires within 300 s and
nothing else reads it. Reverting restores the 60 s sawtooth exactly; it removes
no capability and cannot corrupt anything, because the pass only ever republishes
a payload the request path would have built anyway.

Operator lever short of a revert: `SET discover_feed_live_prewarm:enabled 0` in
Redis. Deliberately a **separate** switch from `discover_feed_prewarm:enabled`,
because turning the main warm off makes every first paint cold while turning
this one off restores the pre-#2236 sawtooth and nothing worse. The pass honours
both.
