# RULING 014 — Verification infrastructure inherits the usage weight of what it verifies

date: 2026-08-09
author: Alex
via: Fable, ratified
issues: #1546 · #1598

**DO NOT REMOVE (CI-guarded).**

> Infrastructure that produces **rendered proof** inherits the **usage weight of the shipped fixes
> it verifies.** The browser event-page pack carries the combined weight of **four unscreenshotted
> event-page fixes**, and therefore **qualifies as a tier on its own.**

## Named failure

**Four consecutive cycles of compounding screenshot debt that the staging gate structurally could
not pay.**

Not a lane forgetting. The gate ranks work by usage weight, a verification rail has no usage
weight of its own, so it lost every ranking to whatever user-facing fix was next — **every cycle,
by construction.** Each cycle then shipped another event-page fix with no rendered evidence, and
the debt grew by one. A rule that produces the same wrong answer four times running is not being
misapplied; it is missing a term.

## The missing term

A verification rail is not a thing users touch, so scoring it on its own traffic scores it at
zero — forever. But **what it verifies is exactly as user-facing as the fixes themselves**, and an
unverified fix is not a shipped fix: this repo's own standing rule is that *a rail is not shipped
until it has been invoked post-deploy*, and the same logic reaches the fixes. Four event-page fixes
with no rendered proof are four claims, not four improvements.

So the rail inherits. It is not being granted an exemption from usage weighting — **it is being
scored correctly for the first time**, at the weight of the work whose truth depends on it.

## Why the debt compounds rather than accumulates

Ordinary debt is additive. This kind multiplies, because each unverified fix also **erodes
confidence in the ones before it**: with no rendered evidence anywhere, a regression appearing at
cycle 4 cannot be attributed to cycle 4. The whole unscreenshotted window becomes suspect at once,
and paying it off later costs more than the four screenshots would have.

That is the argument for "a tier on its own" rather than "rank it higher": at a high-enough debt
it stops competing with feature work on the same axis, because it is what makes the feature work
*legible*.

## Scope, so this does not become a licence

This is not "all infrastructure is exempt from usage weighting." Three conditions:

1. It produces **rendered proof** — an artifact a human can look at — not merely a passing test.
2. It verifies **specific shipped fixes**, nameable and countable. The weight is inherited from
   those, so the list IS the score.
3. The debt is **real and measured** — four fixes, named, none screenshotted. Speculative future
   coverage inherits nothing.

Fails any of the three and it ranks on its own merits like anything else.
