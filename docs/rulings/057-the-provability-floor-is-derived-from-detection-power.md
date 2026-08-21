# RULING 057 — A cell's provability floor is DERIVED from detection power, never chosen

date: 2026-08-14
author: Fable
issues: #678, #1544, #1862

Ruling [049](049-a-criterion-that-cannot-fail-is-not-evidence.md) said every cell
verdict needs a test proving the cell could have come out the other way. This
ruling settles **how you know**, and ratifies the cohort sentinel's answer as the
standard for every graded surface in this repo.

## The rule

> **A cell's minimum sample size is COMPUTED from the power to detect its own
> guardrail at its own probability — not picked, not inherited, not rounded to a
> familiar number. `n >= floor` must literally BE the sentence "RED was reachable
> here", so a cell below the floor is reported as UNPROVABLE and is never called
> GREEN.**

For a 5pp guardrail at probability `p`, the floor is `z²p(1-p)/g²` — **73 at
p=0.05, 381 at p=0.45**. The floor is not a constant across a grid, because the
question is not equally hard in every cell. A single global `n >= 100` is
generous at 0.05 and negligent at 0.45, and it is negligent invisibly: the cell
renders in exactly the same colour either way.

## Why derivation and not a threshold

A chosen threshold is an assertion about statistical power that nobody checked.
It reads as rigour and carries none — and when it is too small, the failure is
silent in the worst direction: the cell says GREEN, meaning "measured and fine",
when what happened was "could not have said otherwise". That is ruling 049's
defect wearing a number instead of a predicate.

Derivation makes the claim falsifiable, and the calibration lane tested it tight
in both directions: **at `n = floor` the 95% half-width fits inside the
guardrail; at `n = floor - 1` it does not.** A floor with that pair of tests
attached is a computation. A floor without them is a preference.

## What this means for the verdict

The floor belongs **inside** the verdict rule, not beside it in a comment or a
docstring. A grid that computes a floor and then renders a three-state verdict
(RED / GREEN / UNPROVABLE) has ruling 049 built into its output; a grid that
computes a floor and renders two states has documentation. UNPROVABLE is a real
verdict and must be visible as one — an under-powered cell is a thing we do not
know, and the surface has to say so rather than defaulting to the reassuring
colour.

## Scope

Every alarm, gate, sentinel cell and acceptance box that grades a rate against a
guardrail. Where a floor already exists as a chosen constant, it is now owed a
derivation or an UNPROVABLE state — replacing it is not urgent, but defending it
as "we picked a reasonable n" is no longer an answer.
