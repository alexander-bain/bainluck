# RULING 009 — `precompute_calibration.py` is frozen until the publish converges

date: 2026-08-09
author: Alex
via: Fable, ratified
issues: #1544 · #683

**DO NOT REMOVE (CI-guarded).**

> `backend/app/tasks/precompute_calibration.py` is **FROZEN**. No commits to it until
> `calibration:main` **publishes fresh post-CAL-P024 AND converges**.

## Lift condition — the only thing that unfreezes it

> 🔴 **CLAUSE 2 IS SUPERSEDED. The live condition is `22 of the last 24` — see the
> [2026-08-28 amendment](#amendment-2026-08-28-alex-mc-2248--the-lift-condition-is-n-of-last-m-and-nm-is-22-of-24)
> below.** Clause 1 and everything else in this ruling stand unchanged. The original clause 2 is
> kept verbatim because the amendment is an argument about its *shape*, and an argument whose
> subject has been edited away cannot be checked.

Both, together:

1. **A fresh publish exists post-CAL-P024** — `calibration:main` carries a `generated_at` newer
   than CAL-P024's deploy, not the durable copy being served past its age.
2. ~~**~13 consecutive clean beats** with no regression in the published payload.~~ **SUPERSEDED
   2026-08-28 — see the amendment.**

Whoever observes both **writes the numbers into the calibration report and says the freeze is
lifted in the same entry.** The freeze does not expire on its own, and it is not lifted by a
lane's judgment that things look fine — it is lifted by the two observations, recorded.

While frozen, a change that genuinely cannot wait is an **Alex escalation**, not a lane call.

## Named failure

**1.8 commits per day against a file that needs uninterrupted convergence.**

Convergence is measured across consecutive beats. Every deploy to this file restarts the count —
so a cadence of nearly two commits a day means the ~13-beat window **could never close**, no
matter how correct each individual commit was. The lane was working hard on exactly the file
whose stillness was the precondition for the outcome it wanted.

## Why a freeze rather than "be careful"

This is a case where individual and aggregate correctness come apart. Each commit was reviewed,
tested, and an improvement. The harm was the *rate* — an emergent property no single change
could be blamed for, so no single review could catch it. A reviewer asking "is this change good?"
gets the right answer every time and the wrong outcome in aggregate.

Only a rule about the file, rather than about any change to it, can see that.

## The corollary the calibration lane already learned the hard way

**DEPLOYING IS NOT PUBLISHING.** Every read-side improvement since 2026-08-02 was invisible until
a publish succeeded, and several were reported as "payoff owed post-deploy" on work that
deploying could never deliver. That is the same mistake in a different coat: shipping to a
pipeline that is not producing, and counting the ship. The freeze forces the question in the
right order — *is it publishing yet?* — before any more work is aimed at the file.

## CAL-P024 is the BASELINE, not a violation

> **SUPERSEDED as to WHICH commit, 2026-08-28.** The baseline is now the deploy carrying the
> CAL-P109/P110 phase-budget repair. Every argument below about what a baseline is FOR still
> governs, unchanged — see the amendment.

CAL-P024 touches this file. That is not an exception grudgingly granted — **it is the commit the
~13-beat count is measured FROM.** The freeze exists so that a known-good producer version can run
undisturbed long enough to prove it converges; that requires a version to start from, and
CAL-P024 is it. Commits *after* the baseline are what restart the count.

Stated explicitly because a freeze with an unstated baseline gets read either as "nothing may
land, including the thing being measured" (nothing ever starts) or as "each new commit is the new
baseline" (nothing ever finishes).

## The successor is already written

Ruling 011 (well-traded = volume-when-present) is staged NOW as the freeze-lift successor queue,
so the moment the lift condition is met the work executes rather than begins. Zero days between
the freeze lifting and the first thing worth publishing through the unfrozen pipeline.

## What is NOT frozen

Everything downstream and adjacent: the route, the read-side payload, the watchdogs, the census
rails, the exam document, tests. Only this one task file is still, and only until it has proved
it can produce ~~for ~13 beats running~~ **for 22 of 24 beats (amended 2026-08-28)**.

---

## AMENDMENT 2026-08-28 (Alex, MC; #2248) — the lift condition is N-of-last-M, and N/M is 22 of 24

date: 2026-08-28
author: Alex (MC, on #2248)
via: Fable → calibration lane (CAL-P111)
issues: #2248 · #1544

**Alex ruled option 1 of #2248: amend the condition, do not simply lift it.** The intent of ruling
009 — *a known-good producer version runs undisturbed long enough to prove it converges* — is
unchanged and is not up for re-litigation. What is replaced is the **shape of the measurement**.

### The new clause 2

> **22 of the last 24 beats publish cleanly**, with no regression in the published payload.

Stated so it can be executed rather than interpreted:

1. **Clean** = one observation in `calibration:beat_gauge_history` whose `outcome.published` is
   `true` — equivalently `terminal == "complete"` **and** `outcome.gate == "pass"`. Nothing else
   counts as clean; a `cancelled` or `not_evaluated` beat is a miss, whatever caused it.
2. **The last 24** = the 24 most recent observations in that ring, in `generation` order. Beats are
   not sampled, filtered or excused — the beat that died because someone deployed an unrelated
   service is a miss and is charged to the budget.
3. **All 24 must post-date the baseline** (below). The freeze therefore cannot lift sooner than 24
   beats — about one day — after the baseline deploy, by construction.
4. **No regression** = at the window's closing beat, `python3 backend/scripts/calibration_scorecard.py
   --live` reports `self_check.ok: true` and `headline_pass: true` (criterion 4, `mce_closing_line`
   ≤ 2.0 pp). One command, one verdict, no adjudication.
5. Read it with `python3 backend/scripts/calibration_freeze_score.py`, which prints the score and
   the verdict. **A predicate cannot consume a threshold written in prose** (gotcha #35), and the
   next lane must not have to re-derive this from the ruling.

Clause 1 (a fresh publish exists post-baseline) is unchanged and is implied by any satisfying
window, but stays stated because the two say different things: clause 1 is *the pipeline produced*,
clause 2 is *it kept producing*.

### The baseline moves to the phase-budget repair

CAL-P024 was the baseline for the original count. **The baseline for the amended count is the
deploy carrying the CAL-P109/P110 phase-budget repair** (`program/calibration-110`) — the change
that raises the publish rate. Beats before that deploy are pre-fix and do not enter the window.
Whoever integrates it records the release SHA and version in the calibration report; that is the
instant the 24-beat window starts filling.

Everything the original said about the baseline still governs: commits *after* it restart the
count, and the count is measured from a version that was allowed to land in order to be measured.

### Why the shape had to change, and what the change is actually worth

Not because 13-consecutive is hard for a healthy producer — measured, it is not. On an i.i.d.
model at a 0.95 publish rate the original condition closes in **0.79 days**; the amended one closes
in **1.04 days**. At 0.90 it is 1.22 d vs 1.31 d. **The amendment does not buy speed at a healthy
rate, and any report claiming it does is wrong.**

It buys three things the consecutive form cannot give:

1. **It discriminates the broken producer far harder.** Under a clustering-aware moving-block
   bootstrap of the *actual* 166-beat pre-fix record (below), a producer behaving exactly as the
   broken one did would satisfy **13-consecutive with probability 0.27–0.59 inside 90 days**, and
   **22-of-24 with probability 0.006–0.105**. The consecutive form is 5–45× *easier* for the
   producer this freeze exists to exclude, because clustered misses leave long clean stretches
   behind them. A streak counter is a poor test of a rate.
2. **It is observable before it completes.** A streak reports nothing until it finishes and
   silently discards its evidence on any miss. A count-in-window has a *score* at every instant —
   `19/24` — which can go on the scorecard every day, so "how close is the freeze to lifting?" stops
   being unanswerable.
3. **It prices an unrelated miss instead of being defeated by one.** A dyno cycle, a Redis
   failover, a deploy of a neighbouring task: each resets a streak to zero while saying nothing
   about convergence. Here each costs one of two budgeted misses.

### The numbers, both directions — measured, not assumed

**Pre-fix record.** `calibration:beat_gauge_history`, **166 beats**, 2026-08-21T18:37Z →
2026-08-28T15:34Z: 79 `complete/pass`, 38 `failed/not_evaluated`, 26 `cancelled/not_evaluated`,
23 `failed/refuse`. **Per-beat publish rate 0.476** (72 h: 35/72 = 0.486; #2248 quoted 0.472).
Longest clean run **9**. Best 24-beat window **19/24** (opening 2026-08-23T00:40Z). *Neither the
original condition nor the amended one was met anywhere in that week.*

**Per-window probability, i.i.d. binomial:**

| publish rate | P(22 of 24) | E[wait] | — | P(13 consecutive) | E[wait] |
|---|---:|---:|---|---:|---:|
| **0.472 — the broken pre-fix rate** | **5.6 × 10⁻⁶** (1 in 179,000) | ~20 years | | 5.8 × 10⁻⁵ | ~1,367 days |
| 0.85 | 0.280 | 2.0 days | | — | 2.0 days |
| 0.90 | 0.564 | 1.3 days | | — | 1.2 days |
| **0.95 — a healthy producer** | **0.884** | **1.0 days** | | — | 0.8 days |

**The two numbers the amendment is required to state: 5.6 × 10⁻⁶ per window at the broken rate,
0.884 per window at a healthy 0.95 rate.** Comfortably reachable in a day when the producer works;
effectively unreachable while it loses half its beats.

**Clustering correction — and it corrects this program's own published figure.** The i.i.d. model
is wrong about the real process, which is bursty (whole good days at 0.79, whole bad days at 0.17).
Moving-block bootstrap over the measured 166-beat sequence, 90-day horizon, 3,000 trials, block
lengths 12/24/36:

| condition | P(ever satisfied by the BROKEN producer in 90 days) |
|---|---|
| 13-consecutive (original) | **0.27 – 0.59** |
| 20-of-24 | 0.99 – 1.00 |
| 21-of-24 | 0.48 – 0.70 |
| **22-of-24 (chosen)** | **0.006 – 0.105** |
| 23-of-24 | 0.000 |

> **#2248's "P = 5.4 × 10⁻⁵, 1 in 18,561, ~2 years" is an i.i.d. artifact and is hereby corrected.**
> The deadlock it describes is real — the producer never did reach 13 in the measured week — but the
> mechanism is *the observed rate*, not an astronomically small probability. Nothing in Alex's
> decision turns on the correction; it is recorded because the amendment's own numbers were derived
> the same way and would inherit the same error unstated.

### Why 22, and not 21 or 20

**Because 21 and 20 are reachable by the producer this freeze exists to exclude.** That is the
whole reason, and it is empirical rather than aesthetic: the broken producer's best measured day was
19/24, and windows straddling two good days reach 20–21 routinely in bootstrap. 22 is the first
value the measured pre-fix process does not reach. 23-of-24 was rejected in the other direction — at
a 0.85 rate it takes 3.7 days and a single pair of misses from one dyno cycle costs a whole day, so
it re-creates a softer version of the deadlock being repaired.

**Why M = 24:** it is exactly one day of the hourly beat (`precompute-calibration-main` is
`crontab(minute=15)`), so the condition reads in plain English — *one full day in which the producer
lost at most two beats* — and needs no arithmetic to check.

### What this amendment does NOT do

- **It does not sanction the 842 lines already written into the frozen file on
  `program/calibration-99`.** #2248's option 3 was not taken. Those commits are unmerged work
  against a frozen file; they become mergeable when the amended condition is met and the lift is
  recorded, and not before. The tension flagged in `CALIBRATION-SCORECARD.md` §5 is resolved that
  way: the freeze was never lapsed, and no undocumented escalation is being ratified after the fact.
- **It does not lift the freeze.** Ruling 009 is live. The lift still requires the two observations,
  observed and written into the calibration report in the same entry.
- **It does not weaken the escalation path.** While frozen, a change that genuinely cannot wait is
  still an Alex escalation, not a lane call.
- **It does not change the reliability bar or cert tiering** (ruling 133).
