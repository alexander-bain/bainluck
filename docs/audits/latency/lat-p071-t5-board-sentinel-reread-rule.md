# LAT-P071 — the T5 re-read rule for `board_sentinel`, REGISTERED BEFORE LOOKING AGAIN

**Written 2026-08-19T07:52Z. The re-read happens at 08:18Z and not before.**

## What the 07:51:11Z read returned

| task | queue | beat | started | delay | rubric |
|---|---|---|---|---|---|
| `mlb_schedule_coverage` | heavy | 07:05 | 07:05:02.165Z | 0.0 min | **PASS** (succeeded 07:05:03.263Z, 1,077 ms) |
| `flow_sentinel` | heavy | 07:10 | 07:10:00.061Z | 0.0 min | **PASS** (succeeded 07:11:57.983Z, 117,905 ms) |
| `grid_sentinel` | heavy | 07:25 | 07:39:01.480Z | **14.0 min** | **PASS** (succeeded 07:39:04.895Z, 3,391 ms) |
| `horizon_sentinel` | heavy | 07:40 | 07:41:08.102Z | 1.1 min | **PASS** (succeeded 07:41:08.471Z, 349 ms) |
| `settled_concept_sentinel` | heavy | 07:45 | 07:50:57.197Z | 6.0 min | **PASS** (succeeded 07:50:57.388Z, 174 ms) |
| `board_sentinel` | heavy | **07:50** | — | — | **NOT YET** |
| `calibration_sentinel` | — | weekly Mon 06:20 | — | — | **EXCLUDED** (§2, cadence-ineligible) |

## Why `board_sentinel` is NOT graded MISSING at 07:51

The literal rubric (§6 step 3) says: no start inside the horizon → branch C = MISSING. Applied at
07:51:11Z that returns MISSING, because `board_sentinel`'s newest start is 2026-08-18T07:50:00Z —
before the horizon even opened at 17:01Z.

**Applying it would be the exact error the protocol was written to prevent.** §2 of that document
says the read opens at 07:50Z "because that is the last of the seven beats to fire — a read before
it would score a task red for not having run yet." That reasoning is right and its clock time is
one minute too tight: **07:50Z is when `board_sentinel` FIRES, not when it can be expected to have
STARTED**, and this program has spent three windows measuring how far those two things separate.

Three facts make the premature reading indefensible:

1. **T5's own claim is "late, never missing."** A beat 71 seconds past its fire is late. Grading it
   missing refutes T5 on the detector's impatience rather than on the system's behaviour.
2. **The horizon does not close until 17:01Z.** Branch C asks whether a start falls inside the
   horizon; nine hours of it remain.
3. **Its five siblings, on the same morning, on the same queue, were late by 0.0 / 0.0 / 14.0 / 1.1
   / 6.0 minutes.** A 71-second read sits below every non-zero one of them.

Note also that `settled_concept_sentinel` started at **07:50:57Z** — *after* `board_sentinel`'s fire,
on a 2-slot heavy pool. `board_sentinel`'s message being behind it is the expected topology, not a
fault.

## THE RULE, fixed now

> **Re-read `board_sentinel` at 08:18Z** = its 07:50 fire **+ 2 × the worst delay measured across
> its five same-morning, same-queue siblings** (2 × 14.0 min = 28 min).
>
> * a terminal or start stamp inside the horizon at that point → **PASS**, and T5 is **6/6**;
> * still nothing → **branch C = MISSING**, T5 is **REFUTED at 5/6**, and the standing remedy is
>   **heavy concurrency 2 → 3**, *not* reverting the three tasks to `background`.

The 2× multiplier is LAT-P070's stopping-rule shape reused deliberately (it used 1.5 × the worst
measured delay to decide how long to stay open on `turbo_collapse`). The multiplier is registered
here, before the observation, so it cannot be chosen afterwards to produce a preferred verdict.

**A release landing between 07:50Z and 08:18Z is a §5 confound and must be recorded by name.** None
had landed as of 07:50Z: v3857 (`f2ac1657`) at 05:43:49Z is the most recent, well clear of the
07:05–07:50Z beat run.

## Not part of T5, recorded because it is a real observation

`calibration_sentinel` returned `no_data` on this read, having returned a full metrics row at
05:24Z. It is EXCLUDED from T5 either way (weekly, cadence-ineligible), so this changes no verdict —
but a metrics row that disappears between two reads four hours apart is worth someone's attention,
and the likely cause is the identifier mismatch in #1800 or a counter TTL expiring under it
(doctrine clause 11).
