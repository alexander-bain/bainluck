# LAT-P063 — the beat fix graded: three rows PASS, two HALT, and both HALTs name the same replacement mechanism the prediction already guessed

**Window:** latency lane cycle 35, `pid:12080`, 2026-08-17 ~15:11–1x:xx PDT.
**Branch:** `program/latency-58`, cut **fresh** from `origin/master` `29639b78` (`-57` merged as
`29639b78`, so the successor did not stack).
**Deployed at read time:** `/api/health` `commit = 29639b78`, Heroku **v3830**, released **14:33:17 PDT**.
**Settled pool:** first read at **15:15 PDT — 42 minutes** past the release, well past ruling 064's
25-minute bar. LAT-P061 lost a grade to the warm-up shadow; this window did not go near it.
**Flag:** `GOLF_IDENTITY_SPLIT_SCAN` — **empty**, re-read at Phase 0 and deleted in code this window (#1917).

**Field-set check, the instruction that has now worked three times:** `last_result_summary` carried
`period_s`, `expired`, `skip_reason` **and** `min_period_s` on the first read. `-57` is deployed and
Item 0 runs. (Had they been absent I would have graded nothing.)

---

## §1 — Item 0: the prediction registered at `661cc05f`, GRADED

Registered **before** the code at `054ee677`, verbatim in `lat-p062-warmer-graded.md` §3. Not
re-derived; run as written. **Four** head probe runs rather than two (ruling 064 asks for two; the
second landed inside an outage I could name, so I took two more on a recovered pool and report all
four rather than discarding the inconvenient one).

| # | prediction | HALT | measured | verdict |
|---|---|---|---|---|
| **1** | `excluded_pre_warmed` **≥ 20 of 24**, mean of two runs | **≤ 16 HALTS** | **20 · 4 · 14 · 23**; mean(first two) **12.0**, mean(all four) **15.2** | 🔴 **HALT** |
| **2** | `period_s` **p95 < 45 s** over ≥ 40 passes | **any `period_s` > 60 s HALTS** | n=20 passes; p50 **38.1 s**, **p95 175.0 s**, max **286.6 s**; three over 60 s | 🔴 **HALT** |
| **3** | `seconds_wall` **unchanged, 27–39 s**, median within ±15 % of 30.9 s | **> 45 s** | pre-sweep median **32.2 s** (**+4.2 %**), range 29.4–42.6 s | ✅ **PASS** |
| **4** | `fresh` stays 0; `expired` **> 0 → 0** | **`expired > 0` on any pass with `period_s < 45`** | **ZERO** such passes, 20/20. `expired > 0` on 8 passes, **every one of them with `period_s > 45`** | ✅ **PASS — and it is the cleanest result in the set** |
| **5** | tail control p50 within **+25 %** of 2,053 ms | **> +50 % HALTS** | **1,796.6 ms, −12.5 %** (improved). Bootstrap 95 % CI **[−46.5 %, +41.2 %]**; **1.36 %** of resamples reach the halt | ✅ **PASS** |

> ⚠️ **A p50 convention trap I hit while grading row 5, recorded because it would have silently
> inverted the result.** The registered bar quotes **2,053 ms**. The LAT-P062 artifact's own
> `summary.miss_total.server.p50` field says **2,227.2 ms** for the same 24 rows. Neither is wrong:
> `probe_typeahead_segments.py`'s `_pctl` takes the **nearest rank** (`ordered[round(p·(n−1))]`),
> while the doc's table was computed with an **averaging median**. On an even n they differ by ~8 %.
> Comparing my run's `_pctl` p50 (1,816.6) against the doc's averaged bar (2,053.3) would have mixed
> conventions and quietly borrowed ~8 % of improvement I did not measure.
>
> **Graded like-for-like on the bar's own convention** (averaging median): **2,053.3 → 1,796.6,
> −12.5 %**. Under the *other* convention applied consistently to both: **2,227.2 → 1,816.6,
> −18.4 %** (CI [−47.7 %, +41.3 %], 1.44 % of resamples reaching the halt). **The row passes either
> way**, which is the only reason this is a footnote rather than a finding — but the next window
> should quote the artifact field, not the prose number. Ruling 069's principle one level down: a
> re-quoted bar needs its *derivation* carried with it, not just its value.

### Row 4 is the one to read first, because it validates the model rather than the change

The prediction said `expired > 0` should appear **only** when a pass period exceeds the 45 s TTL.
Across 20 passes that is **exactly** what happened — 8 passes carried expired entries and every one
of them had `period_s > 45`; not one pass under 45 s lost an entry. The TTL model is not
approximately right, it is right. That matters more than any single latency number here, because
every remaining decision in this program (the W-sweep's ship bound, Option D's sizing) is derived
from that model.

A bonus the window did not plan: **the `fresh` branch fired for the first time ever** — `fresh: 4` at
15:26:33 and `fresh: 3` at 15:35:13, both immediately after *my own probe* had warmed entries the
warmer then found alive. LAT-P062 could only prove `fresh: 0` on 5/5 and argue from arithmetic that
no reachable operating point exists. Now we have the positive control: the branch works, and it is
unreachable **by the warmer's own cadence** precisely as the `T < 45 − P` arithmetic said. The
constant is inert; the code is not dead.

### Row 1 HALTS on the number — and decomposes into a clean natural experiment

The four runs are not noise. Each one lines up with whether the warmer was *running* during it:

| run | window (PDT) | warmer state during the run | `excluded_pre_warmed` |
|---|---|---|---|
| 1 | 15:15:20 → 15:18:02 | healthy: passes at :14:55 :15:21 :15:52 :16:25 :17:00 | **20 / 24 (83 %)** |
| 2 | 15:18:02 → 15:21:12 | **entirely inside a 286.6 s hole** — no pass started at all | **4 / 24 (17 %)** |
| 3 | 15:25:49 → 15:28:41 | first third inside a 169.2 s hole, then healthy | **14 / 24 (58 %)** |
| 4 | 15:28:41 → 15:31:17 | healthy: passes at :28:21 :28:56 :29:30 … | **23 / 24 (96 %)** |

**Head warmth tracks warmer availability almost perfectly, and nothing else.** In the regime the beat
change actually governs, the bar is *met*: runs 1 and 4 average **21.5 of 24**, above the ≥ 20
prediction, against a stable pre-fix baseline of **~10.5** across six runs and three windows and
LAT-P062's post-first-fix **17.5**. That is **44 % → 73 % → 90 %** in the healthy regime.

The mean still halts, and it should. The prediction was written about the warmer as users experience
it, not about its good minutes.

### Row 2 HALTS, and its HALT text is CORRECT

Row 2's halt reads: *"the bistable stretch survived a 3× shorter beat, so it is not the beat."*
Both halves of that need separating, because only one is true:

- **The `{30, 60}` quantisation is GONE.** Not one period landed between 45 s and 60 s. The steady
  state is 32–38 s where the model predicted `{30, 40}`, and the mechanism is now visible in the
  data: with a 10 s beat the tick that lands while the lock is held is *queued*, not lost, so it
  starts the instant the pass ends and the floor admits it — `period ≈ max(wall, 30)`. The beat fix
  did exactly what it was designed to do.
- **The stalls survived.** Two holes in 15 minutes of pre-sweep observation — **286.6 s** and
  **169.2 s** — each followed by a pass finding **39** and **35** of 40 entries already dead. These
  are not new: LAT-P062's `P...P...P` stretches were the same phenomenon presenting as ~105 s gaps at
  the 30 s beat. **A shorter beat cannot fix a period no beat is being serviced in.**

So the cadence was **a** mechanism — it lifted the healthy-regime duty cycle from 73 % to 90 % — and
availability is now the **binding** one. Row 1's HALT text called this in advance: *"the `P...P...`
stretches are worker-queue latency and the fix is scheduling, not cadence."* The measurement supports
that reading, and it is the next thing to fix.

### What I could NOT establish, stated rather than guessed

**The stall mechanism is unattributed.** No dyno restarted (all five up since 14:33:39, the v3830
release). `heroku logs` is **EPERM-blocked from this sandbox** — a new sandbox limit worth recording
alongside the blocked 5432 egress — so the worker logs that would settle it are unreachable from
here. Candidates I can neither confirm nor exclude: realtime-worker saturation by sibling tasks
(`--concurrency=4`, `poll_live_prediction_markets` every 2 min), a hung invocation holding the
`_LOCK_TTL_SECONDS = 120` lock, or Celery losing prefetched ticks on a child recycle.

🔴 **A CORRECTION I owe, because I nearly filed the opposite.** Mid-window I read `hard_kills_24h`
going **1 → 2** and was about to report the program's first attributable hard kill, coincident with
the first hole. It is not one: the counter is a **rolling 24 h window** and I subsequently watched it
oscillate 2 → 1 → 2 → 1 with no task running. **A rising rolling counter is not an event.** The
`hard_kills_24h` reading remains **non-attributable**, exactly as it was in LAT-P061 and LAT-P062 —
and the clean-24 h read is still owed and still not takeable until **after 14:33 PDT 2026-08-18**
(v3830's release + 24 h; the bar moved when master merged, which is itself worth noting — *every
deploy resets this obligation*, so "read it on a clean 24 h" is a promise the lane keeps breaking
through no fault of its own).

### ⚠️ Self-inflicted load, isolated rather than buried

From **15:29:19** my own W-sweep ran a one-off dyno hammering the same database. The warmer degraded
visibly and I am not counting it against the fix:

| window | n | period p50 | period p95 | wall p50 | wall max |
|---|---|---|---|---|---|
| **pre-sweep** (probe load only) — **the grading window** | 13 | 34.3 s | 216.1 s | **32.2 s** | 42.6 s |
| during my W-sweep | 7 | 45.4 s | 69.8 s | 44.7 s | 57.0 s |

Row 3 is graded on the pre-sweep median (32.2 s). Had I graded the whole window I would have reported
a 44.7 s median and blamed the beat for my own experiment. Row 2's p95 is reported on the full set
because both large holes are pre-sweep and excluding the sweep would flatter it.

---

## §2 — The verdict the directive asked for: does the read clear Row-2's HALT?

**No. Row-2's HALT stands, and it should not be argued away.** Three periods over 60 s, p95 of 175 s,
and two multi-minute windows in which the head was entirely cold are not a passing cadence.

But the halt's *consequence* is not "revert the beat", and row 5 is why. The directive was explicit
that row 5 is not decoration — if the shorter beat had bought head duty at the tail's expense, the
correct response was to revert. **It did not:** the tail control came in at **1,796.6 ms against
2,053.3 ms, a 12.5 % improvement**, with only 1.36 % of 20,000 bootstrap resamples reaching the +50 %
halt. The load floor held. The change costs the tail nothing measurable and lifts the healthy-regime
head from 73 % to 90 %.

**Recommendation: keep the beat change; open the stall as its own defect.** Reverting would give back
a measured gain to address a defect the revert does not touch — the stalls predate the change.

---

## §3 — Registered prediction for what comes next (ruling 050)

Written now, before the work, so the next window grades rather than narrates.

**The claim:** the stalls are **worker availability**, not the warmer. If so, `warm_typeahead`'s own
`starts_24h` will show the gaps as *missing starts* rather than as skips — the beat fired and no
worker took the task.

| # | prediction | HALT |
|---|---|---|
| **S1** | Over a ≥ 60-minute probe-free observation, **≥ 1 hole > 120 s** recurs with no probe load at all | **zero holes in 60 probe-free minutes** ⇒ the stalls are induced by *observation* — my own probes — and the entire §1 row-1/row-2 reading is instrument artefact and must be withdrawn |
| **S2** | During a hole, `starts_24h` **does not advance** (the beat's task never starts) | `starts_24h` advancing through a hole ⇒ tasks ARE starting and returning without recording a pass — a *recording* defect, not a scheduling one, and a different fix |
| **S3** | Holes correlate with sibling realtime-task activity, not with warmer wall time | no correlation ⇒ look at the lock (`_LOCK_TTL_SECONDS = 120`) before the queue |

**S1 is the one that can embarrass this window and is deliberately first.** Both holes overlapped
probe runs. Run 1 also overlapped a probe run and showed no hole, which is why I did not attribute
them to probing — but that is one counter-example, not a control, and a probe-free hour is cheap.

---

## §4 — `hard_kills_24h`, restated as an obligation rather than a number

Read **2 · 1 · 2 · 1** across this window. **Non-attributable, and now understood to be
non-attributable for a structural reason rather than a scheduling accident:** it is a rolling 24 h
counter and the 24 h window has spanned a deploy in every window that has ever read it. v3830
released 14:33 PDT 2026-08-17, so the earliest clean read is **after 14:33 PDT 2026-08-18** — and any
merge before then moves the bar again. `soft_time_limit = 100` against a measured max pass of 42.6 s
(pre-sweep) remains adequate.
