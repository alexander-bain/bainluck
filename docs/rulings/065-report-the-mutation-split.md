# RULING 065 — Report the mutation split, never the flattering aggregate

date: 2026-08-14
author: Alex
issues: #993 #1545

## The ruling

When part of a mutation set **cannot be scored in the environment that ran it**, the lane reports
the **split** — which mutants were killed, where, and which are still **owed** to a run that has
not happened yet.

Never a single aggregate that quietly excludes what did not run.

The ratified form, from LAT-P053:

> **"M3–M5 killed offline with control green; M1/M2/M6 owed to CI"**

is worth more than **"8/8 killed"**, and the second one would have been false.

## What is actually being banked: the declined temptation

The arithmetic is the small part. LAT-P053 **named, in its own report, that it could have written
`8/8` and been believed** — the mutants were real, the intent was real, and no reader outside that
window could have checked. It declined.

Alex put that on the record as the reason the lane's numbers carry weight:

> *"The temptation you named and declined goes in the record as the reason the numbers from this
> lane are believed."*

So the subject of this ruling is not mutation testing. It is that **a measurement lane's
credibility is a balance it spends every single time it rounds a gap up to a clean number** — and
that the spending is invisible at the moment it happens, which is why it needs a standing rule
rather than good intentions.

## "Owed" is a state with an addressee

This is the load-bearing half, and it is what separates an honest split from a hedge.

* **`M1/M2/M6 owed to CI`** names a *creditor*, a *venue*, and a *date*: the next CI run over the
  branch settles it, and the next window can be asked whether it collected.
* **`8/8 killed`** is owed to nobody. It can never be collected, never be falsified, and never
  appear on a subsequent window's slate.

A caveat that does not create a future obligation is decoration. If a lane writes "owed", the
report must say **to whom** and **what event discharges it**.

## Why the sandbox case is the common case, not an edge case

The specimen that produced this ruling is the fourth consecutive one in which planning mutations
*before* trusting the tests changed the outcome (gotcha #131) — and the first where planning's
payoff was discovering that the target **could not be scored in the sandbox at all**. There is no
local Postgres here; 29 real-PG tests skip locally and have done for 23 cycles.

An environment that cannot run part of a suite is the **normal** condition of this repo, not a
temporary defect. A reporting standard that only works when everything runs is a reporting standard
that will be violated in the majority of windows.

## Siblings

* [049](049-a-criterion-that-cannot-fail-is-not-evidence.md) — forbids a criterion that cannot fail.
* [050](050-a-control-that-cannot-fail-is-not-a-control.md) — requires the null read be taken at all.
* **065 closes the last refuge**: reporting a number whose denominator silently excludes what never
  executed. 049 guards the criterion, 050 guards the reading, 065 guards the *denominator*.
* [056](056-unmeasured-is-not-ineffective.md) — the same distinction one level up: unmeasured is a
  fact about the instrument, never a fact about the change.
