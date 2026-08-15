# RULING 067 — A `@State` defect is extracted into a value and pinned against its old self

date: 2026-08-14
author: Fable
issues: #1773, #1848

Ratified on the UX-P081 (cycle 78) acceptance: *"The `DiscoverSwipeState`
extraction with a pinned-old-behaviour reference test is the house standard for
`@State` bugs from now on."*

## The standard

A SwiftUI view-state defect is closed by **three** artifacts, not one:

**1. EXTRACT THE STATE MACHINE WHOLE**, into a pure `nonisolated` value type that
imports no SwiftUI and owns no view. `DiscoverSwipeState` is the specimen: an
axis latch, an offset, a commit flag, and the transitions between them, lifted
out of a `View` body where the only way to check a transition was to read the
body and imagine it running.

**2. UNIT-TEST THE FIXED BEHAVIOUR** against that value.

**3. PIN THE OLD BEHAVIOUR IN A REFERENCE TEST** — reproduce the shipped-broken
state machine **verbatim**, next to the fix, and assert what it *did*. Name it
`testLegacy…` so nobody mistakes it for a contract.

## Why the third one is the ruling

The first two are ordinary good practice and would have been done anyway. The
third is the part that keeps being skipped, and it is the part that pays.

A `@State` bug is **invisible in a diff**. Nothing about `offset == 0` in a gate
condition looks wrong; it looks like a guard. The reviewer cannot see the defect
because the defect is a *history* — a sequence of transitions the code permits —
and a diff shows a snapshot. A reference test is the only artifact that makes
the history readable: it states, in executable form, "the shipped code reached
this state and then accepted nothing further."

That converts three things at once:

- **the bug report into a fixture** — `testLegacyStateIsPermanentlyDeadAfterOneCommit`
  is #1773's second symptom, in code, forever;
- **the fix into a falsifiable claim** — the two tests differ, so the diff between
  them IS the behaviour change, and a reviewer reads a behaviour instead of
  auditing a guard condition;
- **a regression into an impossibility** — reintroducing the old logic reddens a
  test whose name says exactly what went wrong.

## The distinction from gotcha 130 — they look identical and are opposites

Gotcha 130 forbids a test that asserts defective behaviour, because such a test
**locks the defect in**: an honest fix has to break a passing test, and the
reflex is to revert the fix.

This ruling **requires** a test that asserts defective behaviour.

The two are compatible because the roles are opposite, and the role is the whole
distinction:

|  | gotcha 130 | ruling 067 |
|---|---|---|
| the defect is asserted as | the **contract** | the **control** |
| it sits | alone, describing what the system should do | beside the fixed test, describing what the system *used to* do |
| an honest fix | reddens it | leaves it green |

The test to apply is the one gotcha 130 already gives: **read the assertion as a
sentence and ask whether you would sign it as a product claim.** "A card accepts
no further swipe after the first" is not signable — so it may only appear under a
`Legacy` name, next to the assertion that replaced it. If deleting the fix would
leave the pinned test *passing and alone*, it has become a 130 violation and must
go.

## Scope — wider than `@State`, on the UX-P082 specimen

Extended the same day by the cycle that received this ruling, because the class
turned out not to be about SwiftUI at all.

`#1773`'s remaining symptom ("none of these cards show probabilities") resolved
to `DiscoverViewModel.renderable` — the fail-closed empty-envelope predicate from
L2-215/#1486 — being wired into **both initial-load paths and neither pagination
path**. Page 1 was filtered; every page after it was not. No view state involved,
and the same three artifacts apply unchanged: the predicate already existed as a
pure static function, the fixed path is unit-tested, and
`testLegacyPaginationAdmittedEveryEnvelope` reproduces the shipped dedup-only
line verbatim and asserts that it admitted all four items where one was
renderable.

So the trigger is not the `@State` keyword. It is:

> **a behaviour that only appears in a SEQUENCE — a second call, a second page, a
> second swipe — and therefore cannot be seen in the line that causes it.**

`@State` is the commonest source of those because view state survives across
renders invisibly. A predicate applied on one code path and not its sibling is
the same shape: both defects are a *divergence over time or over path* that no
snapshot of either side reveals.

## What this does not require

Not every bug needs a pinned control. The standard applies where the old
behaviour is **hard to describe in prose** — where the report ("swipe doesn't
work", "no probabilities") and the cause (an axis latch gated on a stale offset;
a filter missing from one of three call sites) are separated by enough
mechanism that the sentence connecting them is the thing worth keeping.
