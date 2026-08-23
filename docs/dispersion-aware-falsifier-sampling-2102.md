# #2102 — `precompute_calibration_main`, and why `MIN_POST_MOVE_SAMPLES` is dispersion-blind

**Status: EVIDENCE AND PROPOSED RULE ONLY. Nothing here is implemented.** Fable's directive of
2026-08-22 (item 4) asks for the characterization and the draft; it says explicitly *"no fix
without its own gate"*. This document is the draft. It changes no behaviour.

Measured by LAT-P081, 2026-08-22 06:1x–06:3x PDT, against production `a13239f1` / Heroku v3884.
Source: `GET /api/admin/celery/task-metrics/precompute_calibration_main` (one read, HTTP 200).

---

## PART 1 — WHY THAT BEAT IS FAILING, AND IT IS NOT THE ROUTING

### 1.1 The ring is not "bimodal". It is a dated STEP CHANGE.

LAT-P080B described the 50-deep ring as bimodal, and on the evidence available that night it was
the right reading. With the per-sample stamps sorted, the sharper truth is visible: this is not a
mixture of two modes drawn at random, it is **one regime followed by another, with a boundary**.

```
08-20 04:17   142.9    fast          ring is 50 deep and spans 49.4 h
08-20 05:18   183.3    fast          (08-20 04:17 -> 08-22 05:40 PDT)
08-20 06:17   163.2    fast
08-20 07:18    97.4    fast
08-20 08:17   165.0    fast
08-20 09:16    78.6    fast
08-20 10:17   163.5    fast     <=== LAST FAST RUN
------------------------------------- the step
08-20 11:37  1351.5    SLOW     <=== FIRST SLOW RUN
08-20 12:35  1150.4    SLOW
   ... 41 more, all SLOW except two stragglers (08-20 13:17, 08-21 10:19)
08-22 05:40  1407.0    SLOW
```

| arm | n | min | p50 | p95 | max | max / soft-limit |
|---|---|---|---|---|---|---|
| **REGIME A** (pre 08-20 11:00) | 7 | 78.6 s | **163.2 s** | 183.3 s | 183.3 s | 12.2 % |
| **REGIME B** (post) | 43 | 140.2 s | **1263.3 s** | 1399.9 s | 1407.0 s | 93.8 % |
| last 24 h of ring | 24 | 164.1 s | 1276.4 s | 1404.0 s | 1407.0 s | 93.8 % |

**The step is 7.74×.**

### 1.2 The boundary is 2026-08-20 ~11:15 PDT — 21.5 h BEFORE the routing move

`recent_durations_at` is the **completion** time, not the start. Verified arithmetically rather
than assumed: on a fixed cadence, consecutive completion stamps sit
`60 min + (durationₙ − durationₙ₋₁)` apart, and the two largest gaps predict exactly —
`163.5 s → 1351.5 s` predicts 79.8 min and measures **79.8 min**; `1277.8 s → 924.0 s` predicts
54.1 min and measures **54.1 min**.

The beat is `crontab 15 * * * *` (hourly at :15), `options={'queue': 'heavy'}`. So:

* last fast run **started** 10:17:43 − 163.5 s = **10:15:00**
* first slow run **started** 11:37:31 − 1351.5 s = **11:14:59**

⇒ the change landed **between 10:15 and 11:15 PDT on 2026-08-20**.

`ROUTING_CHANGE_AT_EPOCH` is **2026-08-21 09:08:40 PDT** (v3882). The step therefore **predates
the routing move by 21.5 hours**. Exactly one release sits inside the 10:15–11:15 window:

```
v3874   Deploy 724fd22c   2026/08/20 10:45:57 -0700
```

### 1.3 The cause is CAL-P078, and the effect is INTENDED

`v3874` carries CAL-P078, including commit `c5bb293c`, *"the bank stops being frozen — a rolling
re-stage with a retained serving bank"* (#2007 item 2, #1544). Its own message states the before
and the after:

> "`is_complete` was `planned == committed` over SLOT keys; every slot is planned every beat; so
> once 128 slots were banked it was True FOREVER. The frozen loop skips any unit the cursor
> already `has()`, so **`units_this_beat` went to 0 and stayed there** […] The rolling rebuild
> **re-stages every unit**."

That is the whole explanation, and it is arithmetically confirmed in the live payload's phase
ledger:

```
staged:units_this_beat   8          read:futures_unit   1,130,264 ms
staged:unit_ms_mean    141,283 ms   8 x 141,283       = 1,130,264 ms   <-- exact
elapsed_ms           1,310,118 ms   => the unit work is 86% of the whole run
```

**Before v3874 the beat did zero units and finished in ~163 s. After v3874 it does ~8 units at
~141 s each and finishes in ~1,263 s.** The beat did not regress. It started doing the work it
was always supposed to do, and the previous number was a measurement of a bug.

### 1.4 The failure model is exact: a run above ~90 % of the soft limit fails

`soft_time_limit` is 1,500 s (`hard` 1,560 s), and the run plans per-phase budgets from measured
input, deriving a `statement_timeout_ms` per phase. A run that arrives at a late phase behind
schedule gets a shortened statement timeout and **cancels its own statement**:

```
last_verdict        thrown
last_failure_type   DBAPIError
last_error          asyncpg.exceptions.QueryCanceledError:
                    canceling statement due to statement timeout
                    [SQL: SELECT CASE WHEN fo.resolution_source IS NULL THEN 'missing' ... ]
```

Counted over the ring, matched to each counter's OWN window (they differ — see 1.5):

| window | runs in ring | runs > 90 % of soft limit | reported |
|---|---|---|---|
| `failures_window` = 16.48 h | 17 | **8** | `failures_24h` = **8** |
| `successes_window` = 15.54 h | 16 | 7 → 16 − 7 = **9** cool | `successes_24h` = **9** |

Both sides land exactly. **A run that crosses ~90 % of the soft limit fails; a run below it
succeeds.** Headroom on the worst run in the last 24 h is **93.0 s (6.2 %)**, and **8 of 24 runs
(33 %)** are above the 90 % line.

The code's own design note is already exceeded — `app/tasks/__init__.py:558` reserves for
"`precompute_calibration_main` at :15 can run to 19 min" (1,140 s). It now reaches 1,407 s.

> **Hypothesis for the owning lane, not a finding.** This has the shape of gotcha #140 (the
> calibration lane's own): *a phase budget computed from COMPLETIONS is a cap the cancelled runs
> can never raise.* If cancelled runs do not feed the measured input, the futures budget cannot
> grow to fit the work the re-stage added. Stated as a lead because verifying it means reading
> the budget planner's input set, which is calibration's file and not this lane's to touch.

### 1.5 Two instrument caveats, recorded because they will mislead the next reader

1. **`successes_24h` / `failures_24h` / `incompletes_24h` do NOT share a window.** They carry
   `successes_window_s` 55,937 (15.54 h), `failures_window_s` 59,334 (16.48 h),
   `incompletes_window_s` 71,520 (19.87 h). "24h" is the field's **label**, not its span — the
   #2072 defect one instrument over. Any ratio built by dividing one by another is wrong.
   LAT-P080B's "failing 3 runs in 5" came from `2/3` read as if co-windowed; the honest current
   figure is 8 failures over 16.48 h.
2. **The ring includes thrown runs.** `last_duration_ms` 1,406,953 is the ring's max (1,407.0 s),
   and `last_verdict` is `thrown`. So the top of the distribution IS the failures — which is why
   the failure model in 1.4 is computable from durations alone.

### 1.6 🔴 The consequence for ruling 110: one of its seven baselines measures a bug

`PRE_MOVE_BASELINE` pins `precompute_calibration_main` at:

```
p50_s 214.7   p95_s 1302.1   max_s 1357.2   samples 50   successes_24h 21   failures_24h 1
```

**That baseline straddles the step, and the pinned numbers prove it without any other evidence.**
A median of 214.7 s is a regime-A value; a p95 of 1302.1 s and a max of 1357.2 s are regime-B
values. For both to hold over one 50-sample ring, between 5 % and 50 % of those samples — between
3 and 24 of them — were already in the slow regime when the baseline was pinned. Its own
`successes_24h 21 / failures_24h 1` likewise describes a beat that was still 95 % healthy, against
today's 9/17.

So the pinned p50 is **not a stale number that a longer horizon will vindicate.** It is a
mixture statistic taken across a regime boundary, and it will read ≈6× against every future
observation of the working beat, forever, no matter how many samples accumulate.

Two remedies exist and this document recommends neither, because the falsifier is ruling 110's
instrument and re-pinning it is a decision, not a repair:

* **RE-PIN** the baseline from regime B, and say in the note that the pre-CAL-P078 number
  measured a frozen loop; or
* **EXCLUDE** the beat from the graded set with `censored`-style honesty until it is re-pinned —
  an exclusion never certifies safety, which is why #2071 chose that direction.

**What must NOT happen is the third option: leaving it in and reading its 6× as a routing
effect.** That is the reading ruling 119 has just voided once by hand.

---

## PART 2 — THE PROPOSED RULE: `MIN_POST_MOVE_SAMPLES` IS THE WRONG SHAPE

### 2.1 The defect

```python
MIN_POST_MOVE_SAMPLES = 8
```

chosen as *"the point at which the median is not one observation wearing a statistic's name"*.
That is a judgement about **sample count**, made without reference to **any beat's dispersion**.

A flat count buys wildly different amounts of resolution depending on the distribution under it.
On a tight unimodal beat, 8 samples pin a median tightly and 8 is generous. On
`precompute_calibration_main` — whose observed values span 78.6 s to 1,407.0 s with an empty gap
between 205 s and 924 s — nine samples buy **no resolution at all**, because the median is not
estimating a location, it is reporting which side of the gap the majority happens to sit on and
jumping discontinuously as the mix crosses 50 %.

This is #2071 one level up. #2071 was *a percentile pinned at a clamp*; this is *a median on a
mixture*. In both the number is arithmetically correct and carries no information about the
quantity being graded.

### 2.2 Proposed rule, in three parts, cheapest first

**PART A — THE CONTROL GATE (ruling 119 made executable). Recommended first and alone if only one
ships.**

Before grading a beat, compare its **pre-move arm** against the pinned baseline using the same
`DEGRADE_P50_RATIO`. If the control itself has moved, the beat grades **`unattributable`** — a
new verdict alongside `censored`, `pre_horizon` and `no_new_runs`, excluded from coverage for the
same reason they are.

```
if pre_move_arm.p50 is not None and baseline.p50 is not None:
    control_ratio = pre_move_arm.p50 / baseline.p50
    if control_ratio >= DEGRADE_P50_RATIO:      # or <= 1/DEGRADE_P50_RATIO
        verdict = "unattributable"
        reason  = f"control fired: pre-move arm {control_ratio:.2f}x the pinned baseline"
```

* **Cost: nothing.** `_post_move_split` already computes the pre-move arm; today the falsifier
  simply does not look at it.
* **It would have caught this exact case automatically.** The pre-move arm read 391.2 s vs the
  pinned 214.7 s = 1.82×, over the same 1.25× threshold. The REVERT that consumed a protected
  window and a hand-written ruling would have been an `unattributable` line on a panel.
* **It is safe in the direction that matters.** `unattributable` never certifies safety; it
  refuses to speak, exactly as `censored` does.

**PART B — REPLACE THE FLAT COUNT WITH A RESOLUTION REQUIREMENT.**

Retire `MIN_POST_MOVE_SAMPLES` as a gate on **count** and replace it with a gate on **whether the
observed median is distinguishable from the threshold it is being compared against**. The
distribution-free instrument for this is the **order-statistic confidence interval for the
median**, which needs no assumption about shape — a hard requirement here, since shape is
precisely what is pathological.

For `n` sorted post-move samples, the interval `[x₍ₖ₎, x₍ₙ₊₁₋ₖ₎]` covers the true median with
probability `1 − 2·P(Binomial(n, 0.5) < k)`. Choose the largest `k` keeping coverage ≥ 95 %, then:

* grade **`degraded`** only if the interval's **lower** bound exceeds
  `baseline_p50 × DEGRADE_P50_RATIO`;
* grade **`hold`** only if the interval's **upper** bound is below it;
* otherwise grade **`underpowered`** and report the interval.

On the 9 post-move samples of this beat (164.1 … 1404.0), the 95 % interval spans essentially the
whole range and straddles the threshold ⇒ `underpowered`, never `degraded`. On a beat with a
tight ring, 8 samples give a narrow interval and grading proceeds as today. **The rule is
dispersion-aware by construction**: it is the dispersion that sets the interval's width.

`MIN_POST_MOVE_SAMPLES` survives only as a floor below which the interval is not worth computing
(n ≥ 5 gives ≥ 93.8 % coverage at k=1; below that no interval is meaningful).

**PART C — REPORT THE DISPERSION, SO THE PANEL SAYS WHY.**

Carry two derived fields per beat so an ungradeable beat explains itself rather than appearing as
a bare exclusion:

* `dispersion` — IQR / median over the full ring;
* `modality_gap` — the largest empty interval between consecutive sorted samples, as a fraction
  of the range. For this beat that is **(205 s, 924 s) ≈ 54 % of the range**, which is the single
  number that makes "a median here is a mode-selector" legible at a glance.

This is reporting only. It grades nothing, and it is the part to drop if the change needs to be
smaller.

### 2.3 What this proposal deliberately does NOT do

* **It does not loosen `DEGRADE_P50_RATIO`.** The threshold is not the problem; the statistic
  being compared against it is. Widening 1.25× would suppress this false positive and blind the
  instrument to the real regression it exists to catch.
* **It does not re-pin any baseline.** §1.6 is a decision for whoever owns ruling 110, and the
  three parts above are all valid whichever way it goes.
* **It does not touch `precompute_calibration_main`.** That beat is the calibration lane's, its
  cause is that lane's own shipped fix, and #2102's remedy — more headroom, a smaller unit batch,
  a raised soft limit, or a budget planner that counts cancelled runs — is theirs to choose.

### 2.4 The gate this would need before it ships

Stated now so the next window does not have to invent it:

1. **Red-first** on all three parts (ruling 108) — each new verdict must be proved reachable by a
   test that fails against today's module.
2. **A replay fixture built from THIS ring**, byte-pinned: 41 pre-move + 9 post-move samples with
   their real stamps, asserting today's code returns `REVERT` and the proposed code returns
   `unattributable`. Without the specimen the change is an argument; with it, it is a test.
3. **A tight-beat control fixture** proving the change does NOT make a genuinely degraded,
   low-dispersion beat ungradeable — the both-directions requirement of gotcha #43. A falsifier
   that can no longer fire is worse than one that fires wrongly.
4. **Mutation-verified**, each mutation confirmed applied on disk and then reverted — and, per
   LAT-P081's item-5 finding, run through a harness whose restore is wrapped in `try/finally`.
