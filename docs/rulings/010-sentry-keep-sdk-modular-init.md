# RULING 010 — Sentry: keep the SDK, spike a modular init

date: 2026-08-09
author: Alex
via: Fable, ratified
issues: #1501

**DO NOT REMOVE (CI-guarded).**

> **Keep the Sentry SDK.** The work is a **one-session modular-init spike**: errors captured from
> **first paint**, and **drop client-side replay and tracing**.
>
> **Ranked after** the three UX cycle-39 items — P038 repair, browser event-page pack, #1625 golf
> membership.

## What "keep the SDK" settles

Removing it was on the table because the client bundle cost is real and the error rail has been
unreliable. Ruled out: the answer to a heavy default init is a narrower init, not no
observability. Deleting the SDK trades a measurable page-weight win for an unmeasurable
blindness, and this product has already been burned by exactly that trade — see below.

## The three parts, and why each is specified

- **Modular init.** The default bundle carries replay, tracing and error capture together. Only
  the third is load-bearing here.
- **Errors from first paint.** The window a lazy init leaves open is precisely the window where
  the errors worth catching happen: hydration, first data fetch, the first render of a card. An
  error rail that starts late is well-behaved on a metric nobody reads and absent for the
  incident.
- **Drop client replay and tracing.** They are the weight, and neither is currently feeding a
  decision anyone makes.

## Why "spike", and why one session

The unknown is whether the SDK's modular entry points can guarantee first-paint capture without
dragging the rest back in. That is a question with an experimental answer, so it is scoped as a
spike with a session cap rather than a queue with a deliverable. If it does not converge in a
session, the finding is the output.

## The failure this is defending against — already lived, twice

**The error rail has been dark while looking green.** The 5K/month error quota was exhausted on
2026-07-28, so errors stopped being accepted while performance events kept flowing: the dashboard
stayed populated and the errors were simply gone. Separately, a 7-day outcome split read **zero
errors accepted against 422,692 spans accepted** — the rail was blind, not clean.

That is the same shape as ruling 004's calibration incident: a monitoring surface that is up, and
green, and not watching the thing that matters. Dropping tracing and keeping errors is the same
correction in a second place — **spend the budget on the signal that changes a decision**, and be
honest that a quiet error channel might mean nothing is broken or might mean nothing is arriving.

## Ranking

Behind all three UX items, deliberately. Every one of them is a defect a visitor can see; this is
a rail that watches for defects. Fixing what is broken outranks improving how we would learn it
was broken — but only just, and only because the three ahead of it are small.
