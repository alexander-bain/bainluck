# RULING 024 — The post-publish window is ONE combined invalidation event

date: 2026-08-10
author: Alex
via: Fable, ratified
issues: #1544
relates: ruling 009 (the precompute freeze), ruling 011 (well-traded, as amended to two tiers)

**DO NOT REMOVE (CI-guarded).**

> **When the first fresh publish lands and ruling 009's freeze lifts, four changes apply as a
> SINGLE generation change. One rebuild, not three.**
>
> **(a)** fingerprint coverage fix — CAL-P031's blocked fix, **all 43 inputs, cross-module included**
> **(b)** ruling 011's **two-tier** well-traded (the move-count rung is dropped)
> **(c)** cricket + entertainment exclusions
> **(d)** `CALIBRATION_POPULATION_VERSION` bump + **published before/after census**

## Why one event and not three

Each of (a)–(c) changes the population or the truth the curve is computed over. Shipped separately,
each one invalidates the last, so three rebuilds produce three incomparable curves and **no before/
after census means anything** — the (d) census can only be read against a single, known boundary.

Batching is normally the wrong instinct; here the coupling is real. These are not three features
that happen to be ready together, they are three edits to the same denominator.

## Named failure — the freeze was accidentally load-bearing

**3 of 43 fingerprint inputs were covered, and that survived only because a throughput freeze
happened to be stopping rebuilds.**

Nothing detected the gap. Nothing was going to: coverage was never asserted, and the one condition
that would have exposed it — an actual rebuild — was blocked for an unrelated reason. The freeze
existed to protect throughput and was silently doing correctness work nobody had assigned it.

**So the freeze lifting is the moment the defect becomes live**, which is exactly why (a) must be in
the same event as the lift rather than scheduled after it. A protection you did not know you had is
one you cannot notice losing.

Two things follow, worth stating because they generalise past calibration:

1. **An invariant that holds only because something unrelated is broken is not holding.** When you
   fix the unrelated thing, you ship the defect. Ask what the outage was covering before you end it.
2. **Coverage must be asserted, not inferred.** 3/43 read as fine for the same reason an absent
   ledger stage reads as fine (gotcha #53) — nobody was counting, so nothing said "40 missing".

## The order is fixed, and (d) is not paperwork

The version bump and the published per-cohort before/after counts are what make the event legible
afterwards. Without them the curve simply changes one day, and the next person to ask "why did ECE
move?" has no boundary to compare across. Shipping (a)–(c) and deferring (d) would leave the change
unauditable in exactly the way the exclusion rules were written to prevent.

## What rides now vs. what waits

**The AST ratchet guard rides NOW** — it is a guard, it changes no output, and it makes the coverage
gap unrepresentable going forward.

**The fingerprint FIX waits for the window.** Merge order for the branches is **calibration-27 →
calibration-28**, as declared.
