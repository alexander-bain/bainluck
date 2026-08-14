# RULING 054 — A column default is not an observation, and removing one is a CORRECTION, declared and counted

date: 2026-08-14
author: Fable
issues: #678, #1544, #1586

The largest finding of the week, and it was not a bug in a predicate — it was
**fabricated data being counted as evidence by every aggregate that touched it.**

## What was found

`futures_outcomes.is_winner` is a Boolean with a column DEFAULT of `False`. So a
row with `status = 'resolved'` and **no `resolution_source` at all** — nothing
graded it, no authority recorded anything — is read by every downstream
aggregate as a **confident LOSS**.

Measured 2026-08-14: **~398,136 of ~1,961,984 outcomes, about 20.3%.** (Approximate
by construction: the figures are EXPLAIN ANALYZE row counts because an exact
`COUNT(*)` exceeds the db-query ceiling, and they are never to be presented as
exact.)

## Why it is worse than missing data

Missing data widens an interval. **Fabricated data narrows it around a wrong
centre**, and it does so in the direction that hides the defect. The lane's
specimen makes it concrete: 400 rated outcomes priced at 0.05 that really won 15%
of the time is a 10pp break — RED, loudly. Add 600 ungraded rows counted as
losses and the same cohort reports a **1pp gap and renders GREEN**. The defect did
not shrink; the fabrication buried it.

This plausibly explains a large share of the category-chart disasters Alex has
been reporting, and that connection is the reason this ruling exists rather than
a fix note.

## The rule

> **A column default is not an observation. Any aggregate over graded outcomes
> must be keyed on the PROVENANCE that says a grade happened, never on the graded
> value itself; rows with no provenance are EXCLUDED, and the exclusion is
> COUNTED and reported alongside the result.**

Excluding silently would trade one lie for another. Twelve thousand declared
unknowns beat twelve thousand silent inclusions; four hundred thousand more so.

## The metric will move, and that is the correction

The first sentinel run after deploy will move **every** cohort MCE, because the
population narrows underneath it.

> **That movement is CORRECTION, not regression. It is declared in advance, the
> excluded count is reported with it, and nobody re-opens it as a defect.**

The rule generalises: whenever a fix removes fabricated rows from a measured
population, the resulting metric shift is announced BEFORE the run with its cause
and its count. A metric that moves without that announcement is indistinguishable
from a regression, and someone will spend a cycle proving it is not.

## The exceptions registry earned itself on day one

The registry of deliberate exclusions was built with an unmatched-entry report
attached, and that report immediately caught **its own author's** wrong ticker
guess: an entry excluded in prose was still rating **42,184 outcomes**. An
exclusion list that cannot tell you which of its entries matched nothing is a
list of intentions. This is ratified as the shape: **every registry of exclusions
ships with a report of entries that matched nothing.**
