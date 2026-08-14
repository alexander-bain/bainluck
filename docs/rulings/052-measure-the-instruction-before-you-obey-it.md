# RULING 052 — Measure the instruction before you obey it

date: 2026-08-14
author: Alex
issues: #993 #1545

## The ruling

A queue's literal steps are a **claim about what will work**, not a contract to execute blind.
Before obeying a step, measure whether it can do what its own queue says it is for.

When the letter turns out to be measurably impossible:

1. **Measure it, and record the measurement** — the impossibility is a finding, not an excuse.
2. **Ship what the PAYOFF SENTENCE requires.** That sentence is the done contract; the steps were
   one route to it, written before anyone had the measurement.
3. **Say plainly which words you did not execute, and why.** A deviation stated is a deviation
   reviewable; a deviation quietly absorbed into a green diff is indistinguishable from compliance.

That is not a licence to improvise around inconvenient instructions. It is bounded by the
measurement: the step must be *shown* not to work, in the report, with the evidence that shows it.

## Why — the occasion

LAT-P050 was instructed to re-derive the offline harness's floor by capturing production with the
evidence echo. It measured first, and found the endpoint **strips the aliases before responding**,
so the capture the instruction asked for could not contain the evidence the re-derivation needed.
The flag it was told to pass did not exist on the deployed server.

Executing the letter anyway was available, and would have produced: a green diff, an unchanged
**30/44**, and a **fourth consecutive cycle of confident wrong numbers** — each one harder to
retract than the last, because each arrives with a passing gate attached.

Instead it shipped the echo the payoff sentence required, proved by measurement that better
field-mapping alone recovers *nothing*, and stated that the re-derived floor is **owed** rather than
approximating it. Approximating it is the exact error the queue existed to end.

## The second half — an instrument that commits the defect it grades

The same window withdrew its own harness's "**quote it as a floor**" docstring claim.

The harness re-ranked production's response, from which `typeahead_search` has already stripped the
team aliases it ranked on. So the instrument **withheld evidence from the scorer** — and the fixes
it was grading were, in substance, *withheld-evidence fixes*. It committed the defect it was
measuring, against the corrections for that defect, and reported the result as a lower bound.

An instrument in that position has no business calling itself a floor. Saying so plainly, in the
docstring, is not self-flagellation and it is not optional:

> **It is the reason the 38/44 that followed is trustworthy.**

A number is only as good as the reader's ability to know what it is a number *about*. An instrument
that has publicly stated its own failure mode can be believed on the runs where that mode does not
apply. One that has not, cannot — and every number it ever produced stays retroactively in doubt.

## What this does NOT license

- Skipping a step because it looks unnecessary. The trigger is a **measurement**, not a judgment.
- Substituting a different deliverable. The payoff sentence is the contract; the lane still owes it.
- Silence. A deviation that is not in the report did not happen honestly, whatever its merits.

## Relation to the neighbours

- **049** (an acceptance criterion that cannot fail is not evidence) and **050** (a control that
  cannot fail is not a control) both police *instruments that cannot return bad news*. This one
  polices the **instruction layer above them**: a step that cannot return bad news either, because
  it cannot run at all, and reports green for having been attempted.
- **046** (a stacked change is measured on its own deploy) is what makes the cost concrete. Under
  046 a wrong number is not merely wrong, it is *unattributable* — and unattributable numbers are
  permanent, because the intermediate state cannot be observed twice.
