# RULING 036 — Two defects, two left edges: a sweep reports per defect, never one blended number

date: 2026-08-12
author: Alex
via: 339T sequencing, RATIFIED as the season sweep's frame
issues: #1779 · #1798 · #1796

> **The 2026-05-22 match-window widening governs ABSORPTION. The March–April misdating belongs to
> #1798's binding defect, which is older and unrelated. The sweep reports per-defect, per-edge —
> never one blended number.**

## What produced it

339S dated the absorption defect precisely. `_MATCH_WINDOW` was `timedelta(hours=4)` until
`49da8ceb` (2026-05-22, *"Prevent future duplicate events: ±28h match window + closest-by-time"*)
widened it to 28h — wider than the 24h between consecutive games of a series, so game two
name-matched game one and was absorbed instead of created.

The census corroborated the date without being told it. MISDATED per chunk reads
`17 · 0 · 22 · 22 · 19 · 19 · 15`, and the **zero is the last full chunk before the widening**;
the step change begins in the chunk containing 05-22 and never returns.

So 2026-05-22 is the left edge — **for absorption**. The trap is that it looks like the left edge
for everything. It is not: the 03-25 → 04-15 chunk carries **123 re-key and 120 team-miswired
findings with the 4h window in force**. That damage is the team-binding defect, it is older, and a
single 05-22 left edge would silently truncate all of it out of the sweep.

## Why one number would have been wrong in both directions at once

A blended figure understates and overstates simultaneously, which is worse than either alone
because the errors hide each other:

- Applied as one edge at 05-22, the sweep **misses** the March–April binding damage entirely.
- Applied as one edge at season start, the absorption figure **absorbs** binding damage into a
  defect it did not cause, and the 05-22 signal — the cleanest causal evidence in the whole
  census, a literal zero in the pre-widening chunk — disappears into the average.

The same discipline earned its keep immediately downstream. 339T's settlement-contamination census
found 128 outcomes whose grade recomputes differently against truth, and splitting them by defect
showed **only 3 are adjudicable today**: the other 125 sit on events that are *also* re-key
impostors, so the "truth" paired with them is the truth of the game whose id they *wear*. One
blended "128 wrong grades" would have been a re-grade list that was confidently wrong about a
different game — precisely the gotcha #21 damage class, arriving with impeccable-looking evidence.

## How to apply

- Before choosing a sweep's left edge, ask **how many defects are in the population**. A left edge
  is per-defect. If you cannot name which defect an edge belongs to, you do not yet have an edge.
- Report per defect and per edge. Provide the union only as an explicitly-labelled union, and
  never as the headline.
- A causal signal visible in the chunking (a clean zero, a step change that never returns) is
  evidence about a *specific* defect. Blending destroys it, and it does not come back.
- Related: [030](030-census-runs-before-the-staged-work.md) — the census re-decides the brief;
  [035](035-a-lookup-must-never-throw.md) — the duplicate-id half of the same population, which
  likewise turned out not to be one league's problem.
