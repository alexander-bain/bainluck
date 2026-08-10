# RULING 012 — Measured UX attention satisfies the every-cycle UX tier

date: 2026-08-09
author: Alex
via: Fable, ratified
issues: #1546

**DO NOT REMOVE (CI-guarded).**

> The every-cycle UX tier is satisfied by **measured UX attention** — an audit plus routed
> findings **with evidence** — **when no UX-owned defect earns its slot under usage-weighted
> ordering.**
>
> The tier is not satisfied by shipping something merely because the tier exists.

## Named failure

**Forced low-value fixes**, as recorded in **UX-P039's own report.** The lane looked, found
nothing that deserved the slot on merit, and shipped anyway — because "every cycle does UX" was
being read as "every cycle ships a UX change."

That the lane diagnosed this in its own report is the reason it becomes a ruling rather than a
note. A lane reporting "what I shipped this cycle was not worth shipping" is expensive, honest
information, and the correct response is to change the rule that compelled it.

## Why a standing cadence needs this clause

Any every-cycle commitment eventually meets a cycle with nothing worth doing. At that point the
commitment either admits an empty-handed pass or it manufactures work — and manufactured work is
strictly worse than no work: it consumes the slot, adds diff and regression surface to the most
user-visible code in the product, and *reports as success*, so the cadence looks healthy while
producing nothing. The metric survives; the user gets churn.

**Usage-weighted ordering is what makes "nothing earned it" a legitimate finding** rather than an
excuse. The lane is not asserting a preference; it is applying the standing priority rule and
reporting the result.

## What "measured attention" must contain

Not a claim that the lane looked. Three things:

1. **An audit that was actually run** — named surfaces, named method.
2. **Routed findings** — anything real becomes an issue on the board, not a paragraph in a report.
3. **Evidence** — the measurement, so a reader can tell "we looked and it is fine" from "we did
   not look."

Those two states are indistinguishable in prose and trivially distinguishable with a number. That
distinction is the entire load-bearing content of this ruling: **an empty-handed cycle is
reportable, but only with the evidence that makes it a finding.** Without it, this becomes a
licence to skip, which is the failure mode in the opposite direction.

## Relationship to the other cadence rulings

Same family as ruling 004 (one product-visible SLO per program) and the standing *nothing >
unhelpful*. All three say a version of: **a process that measures its own activity will always
report success.** 004 fixes it by making the measure product-visible; this one fixes it by making
"no change" a legitimate, evidenced outcome.
