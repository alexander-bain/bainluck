# RULING 126 — A ratio with no absolute floor is sharpest where it matters least

date: 2026-08-23
author: Fable (LAT-P083 directive item 1, pasted and reviewed by Alex)
issue: 2116

**Issued:** Fable, 2026-08-23, LAT-P083 directive item 1 (pasted and reviewed by Alex).
**Decides:** #2116 — the ruling-110 REVERT decision.
**Verdict:** **DO NOT REVERT.** Execute option **B** of the three costed in #2116: give
`DEGRADE_P50_RATIO` a materiality floor in absolute seconds, scaled by what consumes the beat.
Then re-grade under the floored instrument and post the verdict either way.
**Amends:** ruling 110 (the falsifier's degradation predicate). Ruling 110's grant, its four-step
revert, and its falsifier all stand unchanged. Only the definition of *"degrades measurably"* moves.

---

## The ruling, in Fable's words

> Attribution is necessary but not sufficient. +4.4s of p50 on a background beat, with a FALLING
> p95, at n=8, is not material — and an instrument whose ratio has no absolute floor converts
> noise-scale effects into REVERT verdicts (+4.4s here grades identically to +297s on a beat a
> page waits on).

## The general clause

**A pure ratio makes an instrument's sensitivity inversely proportional to the magnitude of what
it watches.** Wherever a threshold is expressed only as a multiple, the absolute effect required
to trip it scales with the subject's own baseline — so the *smallest* subject is the *most*
sensitive, and the ranking of sensitivities is the exact reverse of the ranking of consequence
whenever consequence tracks magnitude. A ratio is the right shape for a subject near its limit and
the wrong shape for one far from it, and a set of subjects spanning two orders of magnitude needs
both terms.

Measured on this instrument, before the fix:

| beat | pinned p50 | absolute delta that fires REVERT |
|---|---|---|
| `precompute_source_intelligence` | 17.5 s | **+4.4 s** |
| `compute_fair_fight_comparison` | 147.8 s | +37 s |
| `precompute_calibration_main` — *the one beat a user-facing page waits on* | 1187.8 s | **+297 s** |

**67× more sensitive to the beat that matters least.**

## Why attribution was not enough

Ruling 119 voided the previous REVERT because the falsifier's control fired. LAT-P082 applied that
test first and it did **not** fire here: the pre-move control arm read 17.5 s against the pinned
17.5 s — **1.00×**, as clean as a control gets. On ruling 119's own standard the reading was
attributable, and the mechanism had been predicted in the module's own header.

That is the point this ruling banks. **Attribution answers "is this real?"; it does not answer "is
this worth acting on?"** An instrument that only asks the first question will act on every real
effect regardless of size, and every sufficiently sensitive instrument finds real effects. The
counter-evidence LAT-P082 stated so it could be refused — every post-move sample inside the
pre-move envelope, a **falling** p95 (32.6 → 31.0 s), n = 8, and ~9 s absolute on a beat that runs
four times a day — is not an argument that the effect is fake. It is an argument that the effect is
**small**, and the old predicate had no way to say so.

## The floor is scaled by the CONSUMER, and the classification is measured

Fable's words were *"absolute seconds, scaled by what consumes the beat"*. The scaling is a
measured classification, not a taste dial. Every baseline now declares `consumer` and cites in
`consumer_note` where the consumer was found, in the shape ruling 123 established for `regime`: a
field the endpoint prints and a test enforces.

| class | floor | argument | beats (measured 2026-08-23 by enumerating every frontend caller of each beat's serving route) |
|---|---|---|---|
| `user_page` | **30 s** | a public page renders the artefact, so a delay reaches a visitor by pushing back when fresh data lands. Served from a cache the page reads (`/api/calibration`, 1 h), so 30 s is under 1 % of the visitor's own staleness window | `precompute_calibration_main` **only** — `frontend/lib/api.ts:2118` from the public `/calibration` page |
| `operator_panel` | **60 s** | the reader is an operator on a human clock; a sub-minute shift in when a multi-hour precompute lands is not observable to them | `precompute_source_intelligence`, `compute_fair_fight_comparison`, `precompute_backfill_winners_status` — all rendered only under `/admin` |
| `no_reader` | **120 s** | nothing renders it, so only schedule and clamp pressure can hurt — and **both are gated elsewhere**: P4 grades schedule, the observation-side censor grades the clamp | `compute_time_horizon_calibration` (public route, **zero** frontend callers), `snapshot_coverage_metrics`, `compute_calibration_prices` |

**#2116's beat is an `operator_panel` beat.** `precompute_source_intelligence` fills
`bainluck:source_intelligence`, which is rendered by exactly one file:
`frontend/app/admin/source-intelligence/page.tsx`. Nine seconds of median on a four-times-a-day
precompute is invisible to the only human who reads it.

## Three guards, because a floor is a way to make a gate quieter

This program has twice come close to minting a gate that cannot go red — LAT-P079's staged
`samples == 0 ⇒ INCONCLUSIVE` would have been never-false. So the floor ships with its own limits:

1. **A ratio trip under the floor grades `immaterial`, a NAMED state**, printed, counted, and
   carried into the panel's top-level reason. It is never folded into `hold`. *The one thing a
   floor must not buy is silence.*
2. **The floor gates the RATIO only.** #2071's observation-side censor is untouched: a newly
   saturated beat is `censored` whatever its absolute delta. The loudest fact the panel can hold
   cannot be talked out of it by a floor.
3. **The floor is CAPPED** at the point the censor takes over, so it can never by itself make a
   beat ungradeable. It binds on exactly one beat (`snapshot_coverage_metrics`: 120 s declared,
   107.9 s applied) and `floor_capped_by_censor` says so on the panel.

## The re-grade Fable ordered

Run against **live production task-metrics** through `scripts/falsifier_offline_mirror.py`
(production was `81380151` / v3885, which carries neither ruling 123's re-pin nor #2110's fixes,
so the live endpoint still reports the old verdict):

```
BEFORE (deployed instrument):  REVERT — precompute_source_intelligence 23.571s vs 17.5s = 1.347x
AFTER  (floored instrument):   HOLD   — ... `immaterial`: +6.1s against a 60s floor
```

Full re-graded panel, 53.8 h horizon, `counters_clear_the_move: true`:

| beat | verdict | consumer | base | obs | ratio | delta | floor | trips at |
|---|---|---|---|---|---|---|---|---|
| `precompute_calibration_main` | hold | user_page | 1187.8 | 1296.6 | 1.092 | +108.8 | 30 | 1484.8 |
| `compute_calibration_prices` | censored | no_reader | 538.2 | — | — | — | — | 672.8 |
| `compute_time_horizon_calibration` | hold | no_reader | 302.0 | 301.4 | 0.998 | −0.6 | 120 | 422.0 |
| `compute_fair_fight_comparison` | hold | operator_panel | 147.8 | 159.6 | 1.080 | +11.8 | 60 | 207.8 |
| **`precompute_source_intelligence`** | **immaterial** | operator_panel | 17.5 | 23.6 | **1.347** | **+6.1** | **60** | **77.5** |
| `snapshot_coverage_metrics` | pre_horizon | no_reader | 480.1 | 480.1 | — | — | — | 600.1 |
| `precompute_backfill_winners_status` | hold | operator_panel | 518.4 | 541.0 | 1.044 | +22.6 | 60 | 648.0 |

**The routing is HELD.** Ruling 110's exception stands, and its falsifier stays armed with a
predicate that can now distinguish a noise-scale effect from a page-scale one.

## The residual, stated rather than claimed fixed

The floor is a **minimum**, so the ratio still governs slow beats. The spread of absolute seconds
required to fire a REVERT narrows from **67× to ~5×** — it does **not invert**. The beat a page
waits on still needs the largest absolute move.

That is survivable for a reason that is now executable rather than argued:
`precompute_calibration_main`'s ratio trip (1.25 × 1187.8 = 1484.8 s) is **above** its own censor
point (0.98 × 1500 = 1470 s), so a real degradation there surfaces as **saturation** before it
could ever surface as a ratio. The user-facing beat is watched by the censor, not by the ratio, and
it was already.

**Inverting the residual needs a per-consumer CEILING as well** — degrade a `user_page` beat on
absolute seconds regardless of ratio. That **tightens** REVERT, which is a decision about ruling
110's grant, and this lane does not get to make it inside the window that produced the reading a
floor suppresses. Named here and in #2116 as the un-taken second half; Fable's and Alex's call.

## Evidence

* `backend/app/utils/heavy_routing_falsifier.py` — `CONSUMER_FLOOR_S`, `BeatBaseline.consumer`,
  `materiality_floor_s`, `degrade_trips_at_s`, the `immaterial` verdict, `beat_payload`.
* `backend/tests/test_falsifier_materiality_floor_2116.py` — 14 tests. **Red-first: 5 failed /
  EXIT 1 on behaviour before the grade change, green after.** The control
  (`test_the_floor_can_still_fire_a_revert`) is green on **both** sides.
* Five pre-existing "the falsifier can go red" guards degraded their victim by a *multiple* of the
  pinned p50, which on a 17.5 s beat is under the new floor — they would have quietly begun
  asserting the opposite of their own names. All now derive the number from `degrade_trips_at_s`
  through one helper.
* A drift caught during the change itself: the route and `scripts/falsifier_offline_mirror.py`
  each hand-built the per-beat JSON block, and the mirror emitted `null` for all six new fields on
  its first run **while being read as the authoritative re-grade**. One producer now, with a guard.
