# RULING 128 — A gate is bounded in BOTH directions or in neither: the per-consumer ceiling is approved as instrument work

date: 2026-08-24
author: Fable (LAT-P084 item 2, pasted and reviewed by Alex)
issues: #2116
supersedes:

## The ruling, verbatim

> **RULING: the per-consumer ceiling is APPROVED as instrument work — it unblocks the
> named decision "when does a user-facing regression revert" (your 67×→~5× residual with
> no inversion is exactly the gap). Build it so floors and ceilings come from the same
> measured consumer classification, capped both directions.**

## What it approves, and why this one passes the instrument test

Ruling 127 clause (2) forbids instrument work that unblocks nothing: *"the test is 'without
this, X cannot be decided' for an X someone is waiting on."* This ruling names the X —
**when does a user-facing regression revert** — and that is not a hypothetical. Ruling 126
measured the answer and refused to accept it: `precompute_calibration_main`, the one beat a
public page waits on, needed **+297.0 s** to trip revert while `precompute_source_intelligence`,
which no user ever waits on, tripped at **+6.1 s**. The materiality floor fixed the *sign* of
that (67.9x → 4.95x) and could not fix the *direction* — the user-facing beat was still the
LEAST sensitive one on the panel, because a floor is a MINIMUM and a ratio still governs
above it. Ruling 126 stated the residual rather than claiming it fixed, and said explicitly
that inverting it "needs a per-consumer CEILING, which TIGHTENS revert and is therefore a
decision about ruling 110's grant that a lane must not make inside the window that produced
the reading a floor suppresses." That is the decision this ruling makes. The lane was right
not to make it; this is the authority it was waiting on.

## THE GENERAL CLAUSE: one classification, two bounds

*Floors and ceilings come from the same measured consumer classification, capped both
directions.* The clause that survives deleting this case is the second half: **a gate bounded
in one direction is not a looser version of a gate bounded in both — it is a gate whose
sensitivity ranking is set by something other than consequence.** A floor alone says "ignore
effects too small to matter" and leaves the large end to whatever the ratio happens to
produce; a ceiling alone says "act on effects this large" and leaves the small end to noise.
Only both together let the instrument's sensitivity be a *statement about the consumer*
rather than an artefact of the subject's own baseline. And they must come from ONE table:
two independently-authored classifications drift, and the first symptom of drift is a band
with a hole in it, where a delta is simultaneously too small for the floor and too small for
the ceiling and therefore ungraded in a direction nobody declared.

## What was built (#2116, LAT-P084 item 2)

`CONSUMER_CEILING_S` in `app/utils/heavy_routing_falsifier.py`, keyed identically to
ruling 126's `CONSUMER_FLOOR_S` — a test asserts the key sets are equal, so the two bounds
cannot drift apart — and **the bands TILE**: each class's ceiling IS the next looser class's
floor.

| consumer | floor (126) | ceiling (128) | band |
|---|---|---|---|
| `user_page` | 30 s | 60 s | [30, 60] |
| `operator_panel` | 60 s | 120 s | [60, 120] |
| `no_reader` | 120 s | 240 s | [120, 240] |

Tiling is the design, not a coincidence of numbers: it means no absolute delta falls between
two classes' bands, and the *only* thing that decides how many seconds of regression a beat
is allowed is which class consumes it. The applied trip point is
`min(max(p50 × ratio, p50 + floor), p50 + ceiling)`.

Four guards, mirror images of ruling 126's three, because a ceiling is a way to make a gate
LOUDER and this program has now come close to minting a gate that cannot go red AND one that
cannot go green:

1. **The ceiling is capped by the censor**, exactly as the floor is — it can never by itself
   make a beat ungradeable, and `ceiling_capped_by_censor` is printed when it binds.
2. **The applied ceiling can never fall below the applied floor** — a test asserts it over
   every production pin, so the cap in (1) cannot invert the two bounds.
3. **`ceiling_exceeded` reads a SIGNED delta.** `delta >= ceiling`, never `abs(delta)`. An
   `abs()` here is the classic way a tightened gate starts reverting on improvements; a
   -400 s improvement grades `hold` and a test pins that.
4. **The ceiling arm is a NAMED verdict**, reported with `ratio_exceeded=False` and a reason
   that says in words that the ratio did not fire — so a revert driven by the ceiling can
   never be mistaken in a panel for a revert driven by the ratio.

## The measurement, over the seven live production pins

| instrument | spread across pins | where `user_page` sits |
|---|---|---|
| ratio only (pre-126) | 67.9x | **worst** (+297.0 s) |
| + materiality floor (126) | 4.95x | **worst** (+296.95 s) |
| + per-consumer ceiling (128) | **2.00x** | **joint-best** (+60.0 s) |

The inversion ruling 126 could not perform has been performed: the beat a user waits on is
now the joint-most-sensitive subject on the panel, and it got there by declaring a bound in
seconds rather than by tuning a multiple. Applied trip deltas per beat: `calibration_main`
+60.0 (user_page), `fair_fight` +60.0, `source_intelligence` +60.0, `backfill_status` +69.6,
`snapshot_coverage` +107.9, `time_horizon` +120.0.

Red-first gate: `backend/tests/test_falsifier_consumer_ceiling.py`, 13 tests, written
against symbols that did not exist and recorded honestly at **exit 2** (a collection error,
per gotcha #54's amendment — `1` is a result, everything else is a story about the harness),
then green. 96 tests pass across all four falsifier suites.

## What this does NOT do

It does not re-open ruling 110's grant or its four-step revert; only the definition of "degrades
measurably" moves, in the same narrow way ruling 126 moved it. It does not touch #2071's
observation-side censor — the ceiling gates the same predicate the floor gates and stops where
the censor takes over. And it does not, by itself, revert anything: at the time of writing the
re-graded panel still reads HOLD, which is the correct state for an instrument whose job is to
be *able* to go red for the right reason.
