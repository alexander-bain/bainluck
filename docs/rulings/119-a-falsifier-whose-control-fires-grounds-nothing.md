# RULING 119 — The routing is HELD: a falsifier whose control fires grounds nothing

date: 2026-08-22
author: Fable (directive 2026-08-22, pasted and reviewed by Alex)
issues: #1609, #1545, #2102, #2071

Ruling 110 granted the `heavy` queue a scoped two-task exception on one condition: if any
watched calibration beat's latency degrades measurably after the move, **the routing reverts in
the same window that reads it**. On 2026-08-21 at 18:09 PDT, at a 9.0 h horizon,
`GET /api/admin/heavy-move/falsifier` read **REVERT**.

**The routing is HELD. The revert obligation is discharged WITHOUT reverting, because the read is
UNATTRIBUTABLE.** This ruling records the three grounds and, more importantly, records what it
does *not* establish.

---

## The read that obliged a revert

```
falsifier verdict : REVERT     horizon 9.0 h since the routing change
P3  FAILED       1/7 beats gradeable, 2 pre-horizon, 2 CENSORED, 2 NOT RUN
P4  PRE_HORIZON  (24h counters do not clear the move until ~09:08 PDT 2026-08-22)
P5  PRE_HORIZON
degraded: precompute_calibration_main — p50 1273.8s vs pinned 214.7s = 5.93x, ring 18% post-move
```

A single beat, graded on nine post-move samples, against a baseline whose own p50→p95 spread is
six-fold.

## Ground 1 — 🔴 THE CONTROL FIRES

The same 50-deep ring splits into a pre-move and a post-move arm, each sample carrying its own
timestamp. The **pre-move** arm reads:

```
PRE-move   n=41  min  78.6  p50  391.2  p95 1356.7  max 1397.8
POST-move  n= 9  min 164.1  p50 1273.8  p95 1404.0  max 1404.0
```

**p50 391.2 s against the pinned baseline of 214.7 s is 1.82×** — over the very same `1.25×`
`DEGRADE_P50_RATIO` that produced the REVERT.

A shift visible in samples that **predate** the move cannot have been caused by the move. The
instrument is reporting a difference between the pinned baseline and *everything since*,
including the part of "since" that is untreated. That is not an effect of the treatment; it is an
unexplained shift that the treatment happens to sit inside.

This is the program's own standard applied symmetrically. LAT-P079 credited #1866's gain
**only** because its in-head control did not move. A lane that requires a still control to accept
a favourable result and waives it for an unfavourable one is not measuring — it is choosing.

## Ground 2 — a p50 on a bimodal distribution is a mode-selector, not a location

The full ring:

```
21 samples in    78 –  205 s
 1 sample  at   391.2 s
28 samples in   924 – 1404 s
```

There is essentially nothing between 205 s and 924 s. A median over this does not estimate a
central tendency; it reports **which mode currently holds the majority**, and it jumps
discontinuously the instant the mix crosses 50 %. Eight of the nine post-move samples landed in
the slow mode. That is a statement about the mix, not about a slowdown.

A `1.25×` ratio threshold cannot discriminate anything on a distribution whose two modes are an
order of magnitude apart. The threshold is not wrong; it is being asked a question it has no
resolution to answer.

## Ground 3 — coverage was ONE beat of seven, miscounted as THREE

`grade_ruling_110.py` excluded only `(pre_horizon, censored)` from the gradeable set. Two beats
with **zero runs in 24 h** were therefore counted as coverage, and the verdict line printed
"3/7 beats gradeable" over a read in which exactly **one** beat produced a ratio.

**`no_new_runs` is not coverage.** A beat that has not run has not been observed; it is the
purest form of "we learned nothing", and it cannot be evidence in either direction. This is
gotcha #53 one level in — an empty result and a null result reaching the reader as the same
number — and it is the same defect `grade_ruling_110.py` was written to avoid, committed by the
grader itself. Fixed in `3f91b941`.

## Supporting, and deliberately not load-bearing

The observed 1273.8 s sits **inside the baseline's own range**: below its pinned p95 of 1302.1 s
and its pinned max of 1357.2 s. This is offered as context, not as a ground, because "within the
prior range" is a weak claim on a distribution this wide — it would also be true of a genuine
regression that had not yet exceeded the historical worst case.

---

## 🔴 WHAT THIS RULING DOES NOT DO

It **voids one reading**. It does not certify the routing.

* **It does not say the routing is safe.** It says this particular REVERT cannot be attributed to
  the routing. A HOLD granted on an unattributable REVERT is not a HOLD earned on a clean read,
  and nothing here converts one into the other.
* **It does not grade P4 or P5.** Both were `PRE_HORIZON` for a structural reason:
  `RUN_COUNTER_WINDOW_S` is 86,400 s and `ROUTING_CHANGE_AT_EPOCH` is 2026-08-21 09:08:40 PDT, so
  the 24 h run counters do not contain post-move runs only until **09:08 PDT on 2026-08-22**. The
  directive time-gates the re-grade to that boundary rather than treating this ruling as the
  answer.
* **The falsifier stays armed and the grant stays conditional.** Ruling 110 is not amended. A
  future REVERT on a read whose control is still is a revert.

## The defect this read exposed: `MIN_POST_MOVE_SAMPLES` is dispersion-blind

`MIN_POST_MOVE_SAMPLES = 8` was chosen as "the point at which the median is not one observation
wearing a statistic's name". That is a judgement about *sample count* made without reference to
**any beat's dispersion**. It met a distribution it was never sized for: on a bimodal ring with
an order of magnitude between the modes, nine samples buy no resolution at all, while on a tight
unimodal beat eight would be generous.

This is the same class as #2071 one level up — **grading on a statistic the distribution does not
support**. #2071 was a percentile pinned at a clamp; this is a median on a mixture. In both cases
the number is arithmetically correct and carries no information about the thing being graded.

A dispersion-aware replacement is **drafted as evidence-and-proposal only** under this
directive's item 4. It ships behind its own gate. Nothing about it rides on this ruling.

## Separately real, and NOT the routing's: #2102

`precompute_calibration_main` reads `successes_24h=2, failures_24h=3` — **failing three runs in
five**, near a 1500 s soft limit with a 1404 s max. This is a genuine problem. It is also visible
in the **pre-move** arm, so it is not the routing's, and it is filed as its own concern (#2102)
rather than being allowed to ride along as evidence against ruling 110's grant.

---

## The general clause — OFFERED, NOT CLAIMED

> **A falsifier whose control fires grounds nothing.** A treatment reading and a control reading
> that move together are one unexplained shift, not one attributable effect, and the correct
> output is **VOID** — not a verdict in either direction.

Offered rather than banked as doctrine, on row 110's precedent: this is a read/analysis window,
a doctrine clause is a second monotonic series with its own conflict region, and the directive
did not ask for one. Flagged to Fable in `PROGRAM-LATENCY-REPORT.md` to claim or decline.

It is **distinct from doctrine clause 18**, which says the control cells are the falsifier and
should be attacked first. Clause 18 tells you to look; this tells you what follows when what you
find is that they moved too — which is nothing, in both directions. The failure mode it guards is
specific and asymmetric: an unattributable reading is usually acted on when it is *unfavourable*,
because acting looks like caution. Reverting a grant on a void reading is not caution. It spends
a real capability to buy a false sense of having responded, and it teaches the next reader that
the instrument's output is a suggestion.
