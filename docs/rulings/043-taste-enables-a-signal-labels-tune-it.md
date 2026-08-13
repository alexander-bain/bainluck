# RULING 043 — Taste may ENABLE a signal; only labels may TUNE it

date: 2026-08-13
author: Alex
issues: #1815, #993

The interestingness blend is **ON at `interestingness:blend_weight = 0.2`**. The
**`+15` cap** (`feed.py:6618`) — the knob that would let the signal reach the
head of the feed rather than only its tail — is **DEFERRED until fresh labels
exist**.

Two decisions, and they are of different kinds on purpose:

| decision | kind | who can make it | what reverses it |
|---|---|---|---|
| turn the signal ON, at 0.2 | **taste** | Alex, from a side-by-side | taste |
| change how much it MATTERS | **quality claim** | nobody yet | new labels |

**This ruling is labeled `taste`, and the label is load-bearing.** It was issued
against a side-by-side artifact, not against a measurement of whether the new
order is *better*, because no such measurement can currently be produced: the
Discover labelled corpus is **65 pairwise labels from two reviewers, all dated
2026-05-22/23**, and the lane that built the artifact returned **`REFUSE_CLAIM`**
rather than grade the blend against it. Surfacing that refusal *before* the
ruling is what let the ruling be made honestly rather than dressed up.

## WHY

A ruling's basis is part of the ruling. A taste call recorded as if it were an
evidence call becomes, three cycles later, the citation someone uses to refuse a
change — "we measured this" — when nothing was measured. The reverse is just as
costly: a lane that will not act without evidence stalls forever on questions
evidence was never going to answer. Which one this is has to be written down.

So: enabling a signal is a product judgment about what the feed should be, and
Alex can make it from one slate. Choosing its *magnitude* is a claim that one
ordering beats another, and that is exactly what labels are for. Ruling 016
remains blocked on **labeling, not code** — the corpus is the missing input, and
building more scorer is not a substitute for it.

## What this licenses

- The weight stays at 0.2. Rollback is one call:
  `POST /api/admin/feed-config?key=interestingness:blend_weight&value=0`.
- Do **not** touch the `+15` cap, in either direction, on any weight, until a
  labelled corpus exists that can grade the result.
- A future ruling on the cap must cite labels or declare itself taste too.

## What was measured after it was executed

Enabled on production v3798 at `2026-08-13T23:01:03Z` and read back on the same
slate through the uncached feed path (deterministic across two reads on each
side). The tail-only expectation **held**: 13 of 25 positions moved, the head did
not, and the two cards that entered arrived at ranks 23 and 25.

One thing nobody predicted, recorded here because the next ruling on this signal
will be made against it: **the blend at 0.2 is a subtraction.** Cached
interestingness scores cluster near ~48–50 while the top of Discover carries base
scores of 78–98, so `base*(1-w) + i*w` deflated **19 of 23** cards by 2–12 points
and lifted none. Cards with no cached score — events, tournaments, concepts —
are exempt and rise by not falling. The `+15` cap bounds *uplift*, so at this
weight it does not bind at all. When the cap question reopens, the first question
is not "how high" but "why is the signal a subtraction".

Related: [[019-interestingness-tuning-global-until-stratum-gate]] (tuning is
global-only until a stratum clears the gate on both sides) — same instinct, one
rung further down.
