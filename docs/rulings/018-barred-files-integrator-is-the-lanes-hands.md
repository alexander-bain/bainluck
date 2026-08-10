# RULING 018 — A barred file makes the Integrator the lane's HANDS, never a second author

date: 2026-08-10
author: Alex
via: Fable, ratified
issues: #1107 · #1545

**DO NOT REMOVE (CI-guarded).**

> When work needs a file barred to program lanes, **the lane authors the change and the Integrator
> applies it.** The Integrator is the lane's hands for that hunk. It **never** becomes a second
> author of the same work.

## Named failure

**LAT-P021 was built twice, and one of the two was deleted.**

The work needed `backend/app/tasks/__init__.py`, which lanes cannot touch, so it was routed to the
Integrator — who implemented a warmer, a beat entry and a settled-envelope TTL, and shipped them
(`f78b8a6d`). The latency lane implemented LAT-P021 too, on a branch cut from `faae7a48` — before
that commit existed. Neither could see the other. The lane's version was better and not close
(stale-while-revalidate with single-flight, generation-2 envelopes, config-driven keys, 727 lines
of tests), so the Integrator's was removed wholesale in `0faf5abe`.

Two implementations, one thrown away, and a merge that would have left **two warmers racing on the
same four keys** if anyone had merged both.

## The structural cause, which is the point

Nobody was careless. The work was routed to the Integrator by **file ownership** while the same
work was ranked to the lane by **issue ownership**. Two correct routing rules, two different
answers, no place they met.

**A barred file is an access-control fact. It is not a transfer of authorship.** Reading it as one
silently reassigns the work — and the lane that still owns the issue keeps building, because
nothing told it otherwise.

## How it works instead

1. The lane writes the change, in its own branch, including tests — even for the barred file.
2. It declares the barred hunk in its handoff: which file, which lines, why.
3. The Integrator **applies** it, reviews it as it reviews everything, and merges. If it disagrees,
   it bounces the hunk back with a reason. It does not rewrite it into its own design.
4. The Integrator's own commit for that hunk credits the lane's queue id, so `git log` shows the
   author, not the applier.

## The one thing the Integrator must do before writing any barred-file code

**Check whether the lane is already building it.** In this case the branch existed and the queue
was staged; a single `git log program/latency-*` would have shown it. That check is cheap and it is
now the rule.

## Why "never a second author" rather than "coordinate better"

Coordination is what failed. Both parties behaved correctly under their own rule, and there was no
shared surface where the duplicate would have been visible. Making the Integrator structurally
incapable of being an author for barred work removes the failure rather than asking two lanes to
remember each other.
