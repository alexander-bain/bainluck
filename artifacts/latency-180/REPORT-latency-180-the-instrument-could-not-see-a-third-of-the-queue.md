# latency/180 — the queue IS saturated, and the instrument that says otherwise cannot see a third of it

**PILLAR: DISCOVER. SHIP: four of the search box's own warmed head terms stop being permanently cold.**

Written 2026-09-06 ~04:00am PT (11:00Z; PT = local `date` minus 3h, notice 24, verified with
`TZ=America/Los_Angeles date`).

---

## TL;DR

1. **THE SHIP — #3399 / PR #3441 / `160bc335`.** `typeahead_search` had one degraded flag set from
   two places that lose very different things, and the cache write was gated on it. A term whose
   *bonus* outcome-name arm sheds was therefore **permanently uncacheable**: rebuilt ~88 times an
   hour, counted each time as the warmer's own `no_write` DEFECT, never once served warm. Measured
   **5/5 vs 0/5 across 35 production trials** — the shed is a property of the term, so there was no
   fuller answer being protected. `sta`, `stan`, `ben` and `red` cost **4–8 seconds on every
   keystroke, forever**. `red` is a prefix of `red sox`.
2. **ITEM 1: the priced total says 0.84x, and the priced total is wrong low.** 6,064
   worker-seconds/hour against 7,200. But **32 of 110 background beats cannot be priced at all** —
   they never call `_tracked_run`, so no duration exists for them at any rate. A direct `inspect`
   read says what that omission is worth: **both background slots are busy in 10 of 11 samples
   (91%), with 2 more tasks prefetched and waiting in every single sample**, and the single largest
   occupant is `collapse_snapshots` — **an unlabelled beat my model priced at zero.**
3. **🔴 I PUBLISHED THE OPPOSITE CONCLUSION TO MYSELF AN HOUR EARLIER AND IT WAS WRONG.** A
   reconstructed occupancy timeline said 69.1% utilisation with free slots during the warmer's
   holes, which looked like a clean refutation of ITEM 1's premise. It was the instrument's blind
   spot: that timeline is built from `recent_durations_*`, which exists only for labelled tasks. An
   absent observation rendered as an observed absence — gotcha #53, committed by me, caught only
   because I went and looked at what was actually running.
4. **The mechanism, end to end and now consistent.** Long, largely *invisible* tasks hold both
   slots for minutes → `warm_typeahead` messages queue up (18 observed at once) → `expires: 120`
   discards them before a slot frees → the warmer's own skip counters sit **frozen for 201 seconds**
   while `matched_emitted` shows the beat publishing at its full 10s cadence → period stretches to
   200–616s → the head is cold **38.5%** of the time.
5. **`heavy` is refuted as the destination** — 0.91x on the same corrected basis, *more* loaded than
   the queue it would relieve.
6. **Two live monitoring bugs filed** (#3444 label-map, #3440 settled concepts), and two published
   measurements are void because of the first.

---

## ITEM 0 — 179's ship, independently re-confirmed

Not asked for, but it falls out of the data. `tournament_price_refresh` holds **24s of a 55-minute
window (1.2%)**, down from the 50.7%-of-dead-time it held before #3402. Its duration series shows
the step in the clear: four samples at 5.9–9.5s after 05:11Z against 165–240s for the 46 before it.

---

## ITEM 1 — the total, and the correction that matters more than the total

### (a) The number the brief asked for

`background` is **2 slots** (`Procfile: --concurrency=2`, one dyno, confirmed on `heroku ps`) =
**7,200 worker-seconds/hour**.

| queue | slots | capacity | arm A (deliveries / own window) | arm B (starts / own window) | ratio |
|---|---|---|---|---|---|
| **background** | 2 | 7,200 | **6,064** | 5,417 | **0.84x** — *a floor, see (b)* |
| **heavy** | 2 | 7,200 | **6,516** | 5,622 | **0.91x** |
| realtime | 4 | 14,400 | instrument broken — ITEM 4 | | |

Two independently-derived rate arms agreeing within 12%, after three instrument corrections that
each moved the answer by more than the answer's own precision (see "The instruments").

### (b) 🔴 The total is a FLOOR, and the gap it leaves is not small

**32 of 110 background beats are unpriced.** They never call `_tracked_run`, so they have no
duration under any label — no mean, no p50, nothing to multiply a rate by. Their combined delivery
rate is ~21/hr. They are a floor on the total, **not a zero**, and I reported them as such from the
first pass. What I did *not* do until late was ask what they were worth.

At a mild 60s mean apiece they add ~1,260 wsec/hr and put background at **1.02x**. Two of them —
`collapse_snapshots` and `merge_duplicate_events` — turn out to be among the largest occupants of
the queue.

### (c) 🔴 THE CORRECTION: my occupancy sweep was blind, and it said "free slots"

I built an occupancy timeline from `recent_durations_at` + `recent_durations_ms` for every
background beat, unioned across snapshots by each run's own `(label, end)` key. It said:

```
55.2-minute window, 186 runs across 80 background tasks
  0 slots busy   9.2%   |  measured utilisation 69.1% of 2 slots
  1 slot  busy  43.4%   |  contiguous BOTH-BUSY: n=107, p50 5.9s, p95 39.7s, max 98.7s
  2 slots busy  47.4%   |  intervals longer than the 65s TTL: 2, totalling 5.2% of the window
```

Set against the warmer's ring over 81 minutes — **dead 38.5%, in 17 of 65 passes** — that reads as
a seven-to-one mismatch, and hole by hole the sweep put slot use at 43–98% with several holes
apparently running on a free slot. The 616-second hole read **43%**.

I wrote that up as "the holes are not slot starvation; topology is not the lever". **It was wrong.**

`recent_durations_*` exists only for tasks that call `_tracked_run`. The 32 unlabelled beats
contribute exactly zero to a reconstructed timeline, as does anything dispatched outside the beat
schedule. So the sweep cannot report a busy slot it cannot see, and it renders that as an idle one.

**The direct read, taken inside a live hole** (`/api/admin/celery/inspect`, `_cache: {cached:
false}`):

> `worker-background` active: `merge_degenerate_combat_events`, `refresh_hub` — **both slots busy.**

`merge_degenerate_combat_events` is on the unpriced list. `refresh_hub` is not a beat entry at all.
**Neither is visible to the sweep**, and between them they were holding the entire queue.

Sampled properly, over 9 minutes, identifying the background worker per sample (its uuid changes on
a restart or a max-memory child recycle, and a fixed uuid silently drops every later sample):

```
11 samples identified the background worker across 2 distinct worker uuids
  BOTH slots busy:  10/11 = 91%
  one slot busy:     1/11 =  9%
  reserved (prefetched, waiting): 2 in EVERY sample

occupancy by task (share of samples):
   45.5%  collapse_snapshots          <-- UNLABELLED, priced at ZERO by the model
   36.4%  turbo_collapse_futures          (mean 942.7s — a 16-minute grinder)
   36.4%  discover_events                 (mispriced 4x low by #3444)
   18.2%  warm_typeahead
   18.2%  enrich_snippet_angles
    9.1%  merge_duplicate_events      <-- UNLABELLED, priced at ZERO by the model
```

**The background queue is saturated essentially all of the time, and the biggest single occupant is
a task the demand model scored as costing nothing.**

### (d) The mechanism, end to end

Everything now agrees:

1. Long tasks — one 942s grinder plus at least two unlabelled beats — hold **both** slots, 91% of
   sampled time, with 2 more always prefetched behind them.
2. `warm_typeahead` fires every 10s and its messages queue: **18 of them** at the oldest end of a
   33-deep queue in a single census, with `warm_search_head` behind them at 9.
3. `expires: 120` discards each one before a slot frees.
4. **The warmer's skip counters therefore sit completely frozen** — `{lock: 40279, min_period:
   44752}` unchanged for **201 seconds**, `last_outcome_age_s` climbing 228 → 244, while
   `read_at_epoch` advanced on every call (so not a cached endpoint). Nothing is delivered, so
   there is nothing to skip. This is the third of the three outcomes I set out for this test, and
   it is the one that says the loss is above the worker.
5. Meanwhile `matched_emitted: 60` per 600s bucket — **the beat is publishing at exactly its 10s
   cadence** — against `matched_delivered: 20`. `warm_search_head`, on `expires: 20`, reads
   `matched_emitted: 30 / matched_delivered: 1`, `undelivered_fraction 0.967`, verdict `missing`.
6. Period stretches to 191–616s, the 65s response TTL lapses, and the warmed head is cold **38.5%**
   of the time.

### (e) What this means for topology

- **`heavy` is not the destination.** 0.91x against background's 0.84x floor; it is the more loaded
  lane, and D45's standing concern (every master merge cycles `worker-heavy` and kills a running
  calibration beat) is a second reason.
- **The blocker on any topology decision is the instrumentation gap, not the arithmetic.** You
  cannot size a move when the largest occupant of the queue is priced at zero. Labelling the 32 is
  the prerequisite, and it is mechanical.
- **The two named grinders are the obvious first candidates once they can be priced:**
  `turbo_collapse_futures` (mean 942.7s) and `collapse_snapshots` (unlabelled, 45.5% of samples).
  Both are collapse/compaction work with no reader waiting on them, which is the profile
  `refresh_stale_futures_prices` had when it was pinned to `heavy` with the note that a multi-minute
  beat "does not share [background], it closes it".
- **`expires` is worth revisiting but is NOT the root cause.** Raising it would convert discarded
  fires into queued ones behind the same blocked slots. 179's own comment on that constant already
  says a shortened queue is not a returned slot.

---

## ITEM 2 — THE SHIP (#3399, PR #3441, sha `160bc335`)

### The defect

`typeahead_search` had ONE degraded flag, `_ta_degraded`, set from two places:

- `events.py:6089` — the **bonus outcome-NAME arm** shedding. The route's own log line: the dropdown
  "is answering without its outcome-name matches, but WITH its market name, ticker and alias
  matches."
- `events.py:6152` — the **futures query timing out**. The whole futures stage is gone.

`if not _ta_degraded and not debug_evidence and not debug_timing:` gates the `setex`, so the first
case made an entry permanently uncacheable.

### Why this is not the case LAT-P007 was written for

LAT-P007's premise is that a fuller answer exists and a transient is displacing it. Measured on
production, `debug_timing=1` so every probe is a real miss-path build, **5 trials per term**:

| term | shed | arm ms | total ms |
|---|---|---|---|
| `sta` | **5/5** | 2032, 2038, 2026, 2014, 2042 | 5034–7845 |
| `stan` | **5/5** | 2054, 5648, 2034, 2026, 2034 | 4214–7860 |
| `ben` | **5/5** | 2021, 2045, 2030, 2032, 2021 | 5133–6733 |
| `red` | **5/5** | 2264, 2007, 2203, 2120, 2043 | 5931–7243 |
| `stanley cup` | 0/5 | 71, 134, 96, 71, 102 | 1408–1741 |
| `carlos` | 0/5 | 798, 726, 1154, 519, 1235 | 2196–3701 |
| `alc` | 0/5 | 567–1286 | 2264–3883 |

**5/5 or 0/5, never in between, across 35 trials.** A separate 3-trial sweep of all 40 warmed head
terms found 0/3 on every term in it. Shedders pin at the 2,000 ms bound every time; non-shedders
finish 15–28x inside it.

The cause is already in this file, one lane over: `red` costs 11,660 ms against `sox`'s 39.6 ms
because its trigrams are extractable but **not selective**. Selectivity lives in the data, not in
the string — which is why this is bimodal and why no static term rule can predict it.

### The product call, stated rather than decided silently

The directive asked for this explicitly. **Should a degraded body be cached?**

**Futures-stage timeout: no, unchanged.** That branch loses a whole stage, a fuller answer does
exist, and pinning the thin one is exactly LAT-P007's sticky-wrong-answer.

**Outcome-arm shed: yes**, because the rule protects nothing there. The same request run again sheds
again, so there is no fuller answer to displace; the rule's only effect was that the user waited 4–8
seconds for the identical incomplete body they would have got instantly.

**The residual cost, stated:** a term that normally completes but sheds *once* now has its thinner
body pinned until the next completing request overwrites it — bounded by the warmer's own pass
(~40s) for a head term, by the 65s TTL otherwise. Zero such transients in 35 trials, but *not
observed* is not *cannot happen*. So both shed states are now reported by name on `debug_timing`
(`outcome_arm_shed`, `degraded`) rather than inferred by substring-matching stage labels — which
silently answers "no" the day a label is renamed — and the shed remains a `logger.error` carrying
the term.

### The guard

`test_lat_p241_outcome_arm_shed_is_cacheable_3399.py`, 14 tests, **AST not substring**: a 1,000-line
function's flags cannot be pinned by `in src` when the comment block beside them names both flags
repeatedly. `TestTheGuardIsArmed` fails if any locator stops finding its node, so a rename cannot
turn the suite green by making it vacuous.

**RED-first by mutation in three directions**, each killed by its intended named control:

| mutant | named killer |
|---|---|
| arm shed sets `_ta_degraded` again (the original bug) | `test_the_arm_shed_does_not_mark_the_answer_degraded` |
| cache gate reads the bonus flag | `test_the_gate_does_not_read_the_bonus_flag` |
| futures-stage timeout downgraded to the bonus flag (the dangerous inverse) | `test_the_futures_stage_timeout_still_marks_the_answer_degraded` |

**Two standing mutation needles drifted and CI caught it** (`test_mutation_guard.py`, shard 4).
`M20` was mechanical. `M17-SHED-ANSWER-IS-CACHED` had to be **re-aimed**: it flipped the arm-shed
branch because that branch used to set `_ta_degraded`, and the defect it *names* now lives on the
futures-stage timeout. Leaving it where it was would have made it assert a superseded ruling
forever. A first draft of the re-aim inserted the flip four lines above the branch's own assignment,
which overwrote it — a no-op mutant reporting itself as a SURVIVOR, precisely the false negative the
harness exists to prevent. Battery re-run after re-targeting: **23/23 killed, 0 survived, 0 harness
failures.**

Gates: new guard 14 passed; typeahead + search-cache + search-latency suites 624 passed, 6 skipped;
`test_startup.py` 4 passed; mutation residue scan 26 passed, 0 drifted.

### Two corrections to #3399 as filed

1. **The pair is not fixed.** It is whichever short prefixes are in the head. The directive saw
   `['sta','ben']`; live during this session it read `['stan','sta']`; `red` sheds too.
2. **`no_writes` is far harder to observe than the issue implies.** `last_result_summary` is
   overwritten by *every* run including the lock/min_period skips, which are the overwhelming
   majority (40,254 + 44,721 cumulative). A read at a random moment almost always shows a SKIPPED
   pass with `no_writes: []` — which reads exactly like "no defect". I recorded `[]` on 14
   consecutive sampler ticks and nearly reported the defect as already fixed.

---

## ITEM 3 — the class 179 did not bundle

Swept globally rather than site by site, using `pg_stat_statements` **differenced** rather than read.
Both of 179's suspects are dead statements:

| statement | lifetime calls | calls in the delta window |
|---|---|---|
| `UPDATE futures_markets SET volume_24h=... WHERE external_id = $3` | 155,371 | **0** |
| `SELECT futures_outcomes.market_id ... WHERE name ILIKE $1` | 294,924 | **0** |

The first is 179's own fix landing — the statement still sits near the top of the lifetime ranking
carrying the full signature of the bug (278 ms, 15,084 buffers for a single-row update) and has not
been called since. **135 of the top 200 statements by lifetime total did not move at all.**

The remaining seven `external_id ==` sites are unchanged and still one-shot or low-frequency; none
appears in the live delta. `admin_matching.py` remains **D35/D39 — file, do not fix**, linked #2693.
**`LAT-P240-PREDICATE-SEMANTICS-GUARD` is still owed** and is not addressed here.

---

## ITEM 4 — realtime: the numbers were void, and now we know why (#3444)

179 gave `poll_all_odds` 7,368 wsec/hr (29.0% of realtime). My first pass gave 13,565 — 0.94x of the
whole queue for one task. **Both are wrong for the same reason**, and it is a live monitoring bug.

`bainluck:task_metrics:label_map` maps celery name → label and is **single-valued**. A task calling
`_tracked_run` under more than one label overwrites its own entry every run and keeps whichever ran
last. An AST sweep finds exactly two:

| task | labels written | map names | its own mean | the named label's mean | error |
|---|---|---|---|---|---|
| `poll_all_odds` | `poll_odds`, `datagolf_live` | **`datagolf_live`** | 35.0s | 116.4s | **3.3x over** |
| `discover_events` | `discover_events`, `enrich_taxonomy_llm`, `poll_datagolf`, `update_event_tags` | **`enrich_taxonomy_llm`** | 183.1s | 45.6s | **4.0x under** |

So `/api/admin/celery/schedule-adherence` grades `poll_all_odds` — verdict `overruns` — on a
piggybacked DataGolf sub-poll's p95, and `discover_events` on something a quarter its length. Both
errors point the wrong way for triage, and `discover_events` is one of the three largest background
occupants in the `inspect` sample.

Repriced on the right label **and** the right rate arm (`poll_all_odds` is delivered 116.5/hr but
only *runs* when its single-flight lease and `should_poll_now()` both admit it, so **starts, 48.4/hr,
is the rate for the work**):

| component | rate | mean | wsec/hr |
|---|---|---|---|
| `poll_odds` | 48.4/hr | 35.0s | **1,694** |
| `datagolf_live` (5-min gated, same slot) | 9.22/hr | 116.4s | **1,073** |
| what the mis-mapped join produced | 116.5/hr | 116.4s | 13,565 |

Also observed: on one `inspect` read, `worker-realtime` had **all 4 slots active** with 0 reserved.

**`poll_all_odds` stays the live lane's** — not claimed. **M-20260905-A must not be re-run until
#3444 lands**, or it will re-derive the same wrong number. **D67 is not ready to go back to Alex.**

---

## ITEM 5 — the parked branch

**CERT-1988 untouched.** PR #3377 not merged, not re-staged, header not rewritten. Still parked at
`PARKED-MEASUREMENTS.md:8917`. This queue built on a fresh branch off master, so
`program/latency-242-…`'s commits are not dragged along.

---

## Also filed — #3440, settled concepts

`warm_event_concepts` spends **38s of every 5 minutes** rebuilding four golf majors that settled
7–21 weeks ago. `WARM_CONCEPT_KEYS` is a static tuple of four golf slugs warmed unconditionally,
year-round; all four 2026 majors ended between 2026-04-12 and 2026-07-19.

`GET /api/event/{key}` captured five times over 22 minutes, spanning **3–4 distinct rebuilds** per
key (`cache.created_at` advances), hashing everything but the `cache` block:

| concept | rebuilds observed | distinct bodies |
|---|---|---|
| the-open-championship | 3 | **1** |
| the-masters | 3 | **1** |
| u-s-open | 3 | **1** |
| pga-championship | 4 | **1** |

Byte-identical every time; The Open's `primary` is a graded winner at probability 1.0. Cost: 38s ×
11.20 runs/hr = **426 wsec/hr = 5.9% of the whole background queue**, and 38s of contiguous slot
occupancy every 5 minutes — on a queue now measured as saturated 91% of the time.

---

## The instruments — five traps, and one of them I fell all the way into

**Trap 1 — the join is not the name.** The metrics hash is keyed by a LABEL written inside
`_tracked_run`, not the celery task name; only **53 of 148** labels equal their task's short name.
Guessing produces `status: no_data` for all 138 tasks, which reads like "nothing is instrumented".

**Trap 2 — a cumulative counter is not a rate, three times in one session.**
`starts_24h` NAMES 24 hours and holds 0–24 of them (`tournament_price_refresh`'s `starts_window_s`
is **14,478s**); dividing by 24h under-reported it 6x and made both queue totals read ~2.3x low
across ~34 rows. `pg_stat_statements` was last reset **5 days 11 hours** ago, so its ranking ranks
history — 135 of its top 200 had not been called at all. `recent_durations_ms` is the last 50 runs,
23 minutes for a 131/hr task and 24 hours for a daily one, so it straddles deploys.

**Trap 3 — a change-point scan cannot tell a step from a bimodal distribution.** Step detection
added to fix trap 2 promptly "found" a step in `warm_typeahead` (0→17s at newest 45/50) which is a
run of lock-skips. A real step has two TIGHT populations; both sides must have CV < 0.6 before the
split is believed.

**Trap 4 — a coverage bound belongs to one ring at one read, not to the union.** Unioning three
snapshots of `warm_typeahead` yields ~70 distinct runs, so a `len >= 50` saturation test on the
UNION finds it unsaturated and stretches the occupancy window to 182 minutes — eight times what that
ring can see. `warm_typeahead` then scored 8.7% of a window in which it truly occupies 44.6%.

**Trap 5 — 🔴 THE ONE THAT PRODUCED A WRONG CONCLUSION.** After fixing traps 1–4 the occupancy
sweep was internally consistent, cross-checked against the demand model, and *still wrong*, because
every one of those fixes was about reading the instrument correctly and none of them asked **what
the instrument cannot see at all**. `recent_durations_*` covers labelled tasks; 32 background beats
have no label; the sweep reports their occupancy as zero, which is indistinguishable from idle. I
had *already written down* that those 32 were "a floor on the total, not a zero" in the demand
model, and then failed to carry the same caveat across to the occupancy model built from the same
source. The refutation cost one `inspect` call.

---

## Rules carried forward

168 (a)–(g), 170 (b)–(e), 171 (b)–(e), 173 (f)–(i), 174 (j)–(m), 175 (n)–(x), 176 (y)–(dd),
177 (ee)–(kk), 178 (ll)–(oo), 179 (pp)–(uu) hold. 180 adds:

**(vv) An occupancy timeline reconstructed from per-task instrumentation reports UNINSTRUMENTED
work as IDLE, and idle is the one reading that licences a wrong conclusion.** 32 of 110 background
beats never call `_tracked_run`; the sweep therefore showed free slots during holes when both slots
were held by exactly those tasks. Before believing a resource is free, ask what fraction of its
consumers the instrument can see, and **cross-check against a direct read of what is running** —
`inspect` costs one call and is not derived from the same source. The caveat you write in one model
does not travel to the next model you build from the same data.

**(ww) A DEAD SHARE and a BLOCKED SHARE are different measurements, and a large gap between them is
a claim about the INSTRUMENT before it is a claim about the system.** 38.5% dead against 5.2%
blocked looked like proof the beat was not waiting for a slot. The right reading was that the
blocked figure was under-counted. When two measurements of one mechanism disagree by 7x, suspect
coverage before mechanism.

**(xx) A single-valued map from a thing that can happen twice silently keeps the last writer.**
`label_map` is celery-name → label, written inside `_tracked_run`; two tasks call it under several
labels, so the health surface grades them on another task's durations (3.3x over, 4.0x under).
AST-walk the instrumentation call sites and assert each registered unit writes exactly one key.
Nothing about the wrong mapping looks wrong from outside, because legitimate renames dominate.

**(yy) A summary field overwritten by every run — including the SKIPS — is unobservable at a random
moment.** `last_result_summary.no_writes` reads `[]` on ~85,000 skip passes for every real pass, so
14 consecutive samples of a live defect all said "clean". Sample faster than the work path and
filter on the terminal, or the field's normal reading is the no-op's.

**(zz) Frozen counters are a POSITIVE result, and the cheapest one available.** The warmer counts
why it declines to start (`{lock, min_period}`). Differencing them across a hole gives three
distinct diagnoses; both frozen for 201 seconds while the emit-side counter showed the beat
publishing at full cadence localised the loss above the worker in a single 15-second poll, after an
hour of occupancy modelling had pointed the wrong way. Always pair it with a freshness control —
`read_at_epoch` advancing proves the endpoint is not simply memoised.

**(aaa) Re-aiming a drifted mutation needle is a semantic act, not a text edit.** When a ship
deliberately changes a branch's behaviour, the mutant pinned to that branch must move to whichever
branch still carries its MEANING, or it will assert a superseded ruling forever. And check the
re-aim actually mutates: a flip inserted upstream of the assignment it targets is overwritten, and
reports itself as a survivor — a false missing-assertion in the oracle.

---

## Next: `NEXT-DIRECTIVE-latency-181.md` in this directory.
