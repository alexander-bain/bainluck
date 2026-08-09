# RULING 009 — `precompute_calibration.py` is frozen until the publish converges

date: 2026-08-09
author: Alex
via: Fable, ratified
issues: #1544 · #683

**DO NOT REMOVE (CI-guarded).**

> `backend/app/tasks/precompute_calibration.py` is **FROZEN**. No commits to it until
> `calibration:main` **publishes fresh post-CAL-P024 AND converges**.

## Lift condition — the only thing that unfreezes it

Both, together:

1. **A fresh publish exists post-CAL-P024** — `calibration:main` carries a `generated_at` newer
   than CAL-P024's deploy, not the durable copy being served past its age.
2. **~13 consecutive clean beats** with no regression in the published payload.

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

## What is NOT frozen

Everything downstream and adjacent: the route, the read-side payload, the watchdogs, the census
rails, the exam document, tests. Only this one task file is still, and only until it has proved
it can produce for ~13 beats running.
