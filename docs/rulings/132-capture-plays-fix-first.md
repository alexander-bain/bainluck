# RULING 132 — Capture plays FIX-FIRST: a salvage batch run through a known-broken planner spends the thing it is trying to save

date: 2026-08-24
author: Alex (banked by lane1, Q405 addendum 2)
issues: #2077, #2174, #2175
supersedes:

---

## The ruling

The settlement-truth capture program does **not** run salvage batches while a defect in its
planner is known and unfixed. The order is: fix → cert → full RUN. Specifically, as ruled tonight:
no salvage batches on 2026-08-24; the #2175 livelock fix plus the pre-staged **CERT-399 acceptance
(G1–G7)** in `.claude/handoff/CERT-QUEUE.md`, then a **full RUN on 2026-08-25**.

Build to those gates. They are what the work is certified against — not a set of criteria written
after the fix, by the lane that wrote the fix.

## Why — the arithmetic that makes "get some of it while we can" wrong

The instinct under a deadline is to bank partial progress: the capture wall is 2026-08-28, rows are
expiring, so run *something* tonight and fix the planner after. That instinct is correct for most
deadlines and wrong for this one, because of what the capture program spends.

A sweep's budget is not money and not time. It is **probe attempts against rows that expire**, and
an attempt spent on the wrong row is not merely wasted — it is subtracted from the rows that could
still have answered. So a batch run through a broken planner is not "some progress"; it is a
transfer of budget from the rows that would have been saved to the rows the planner happens to
prefer. Two measured defects made that transfer concrete:

- the **`ambiguous_empty` livelock** (#2175) re-asked rows that had already said they could not
  answer, at the head of the terminal ordering, so the head of the queue was reserved for the
  guaranteed non-answers;
- the **`overdue` starvation** found while folding in the retention measurement, where the cohort
  with the least life left sorted **last** and a binding budget never reached it at all.

Run tonight and the sweep spends its attempts on those two populations. The rows lost are not
recoverable by a later, better sweep, because retention is the whole reason for the deadline.

## The second reason, which outlives the deadline

A salvage batch also destroys the evidence that the fix worked.

After a broken run, the population has changed: probe histories are written, dispositions recorded,
`attempts` counters incremented. The next sweep's planner then reads a state that the previous
sweep's *bug* produced. A cert asked afterwards whether the ordering is correct cannot separate "the
fix works" from "the population was already churned in a way that makes the fix look effective."
The pre-fix measurement is gone, and it cannot be re-taken.

So fix-first is not only about saving rows. It is about keeping the run *gradable*. This is
ruling 050's shape — a control that cannot fail is not a control — applied to a population instead
of a metric: once you have mutated the thing you were going to measure, the measurement is not
pending, it is lost.

## Binds

- **No capture sweep and no salvage batch runs while a filed planner defect is unfixed.** Filed and
  diagnosed is enough; it does not need to be reproduced in production first.
- **The acceptance criteria are the pre-staged ones.** CERT-399's G1–G7 were written by the cert
  window before the fix existed. The fix is built to them; the author does not get to restate them.
  Author-never-certifies covers who runs the cert; this covers who writes the ruler.
- **The RUN is gated on cert GREEN, not on the calendar.** If 2026-08-25 arrives with the cert not
  green, the RUN does not proceed on the strength of the date. The date is a plan; the gate is the
  condition.
- **The sequence after GREEN belongs to whoever holds it** — fresh census → Alex's attended
  kill-mid-batch demo → RUN. A lane that fixes the planner does not thereby acquire the authority
  to fire the sweep.
- **A deadline is a reason to fix faster, never a reason to run broken.** If the wall genuinely
  cannot be met fix-first, that is an escalation to Alex about the wall, not a licence to spend the
  budget badly. Moving the date is reversible; spending the attempts is not.

## What this does NOT say

It does not forbid **read-only** work under a known defect. Censuses, probes, planner rehearsals and
anything that mutates nothing remain available and are in fact how you earn the fix — the
`overdue` starvation was found by exactly such a rehearsal. The bar is on spending the budget and
mutating the population, not on looking.

It also does not generalise to every deadline. The clause is about work whose **budget is drawn from
an expiring population**. Where a retry is free and the population is stable, partial progress under
a known bug is often correct, and this ruling has nothing to say about it. The qualifying test is:
*does a wasted attempt reduce the attempts available to the rows that could still succeed?* If yes,
fix first.

## General form

**Where the budget is drawn from an expiring population, a wasted attempt is not zero — it is
negative, and it is charged to the rows you were trying to save. Work in that regime plays
fix-first, and it plays against criteria written before the fix.**
