# RULING 036 — Assigned STATE beats inferred, and inference may only ever add settledness

date: 2026-08-12
author: Alex
via: UX-P067 acceptance, ruling 2 — banked by UX-P068
issues: #1803 · #1546

> **(a) When an event declares its own status, that declaration is the authority. A surface may
> not decide whether something is over by reasoning about its parts while the whole has already
> said so.**
>
> **(b) Part-level inference is MONOTONE: it may only ever make a thing look MORE settled, never
> less. It is OR-ed in, never substituted.**
>
> **(c) The mid-event case gets its own regression test, because that is when the sharp edge cuts
> a live reader rather than an archive.**

## What produced it

`/event/golf/the-masters` showed **"Round 3 Leader: McIlroy 80%, Young 11%"** — a live, moving
ladder — under a SETTLED banner, on a tournament that finished **2026-04-12**, with chart copy
underneath promising the prices would refresh every 1–2 hours.

The mechanism is worth stating precisely, because the shape recurs. Round completion was inferred
from a **cross-sibling ceiling**: the highest round whose own *leader market* had graded. That
inference is **self-referential** — only round N's own leader can mark round N over — and The
Masters carries no Round 4 Leader market at all. So the ceiling pinned at 2 and round 3 became
**permanently unreachable**. No amount of waiting, re-polling or backfilling could raise it,
because the signal that would settle round 3 is precisely the signal that does not exist.

Meanwhile `event.status == "settled"` and `end_date 2026-04-12` sat in the same payload, assigned,
authoritative, and **never consulted**.

## Why it is ruling 031 again, and why it still needed its own ruling

Ruling 031 established assigned-beats-inferred for **identity** — what a thing IS. This is the
same disease one field over: **what STATE a thing is in**. Both are facts the system already
holds and then declines to read in favour of a guess assembled from neighbours.

It earns a separate number because the failure mode differs in a way that matters operationally.
A wrong identity is wrong immediately and visibly — the US Open page served Cincinnati. A wrong
state is **wrong forever and looks fine**: nothing errors, the page renders, the numbers are real
numbers, and the only tell is a date the reader has to know to check. It does not self-heal, and
no alarm fires, so it survives exactly as long as nobody looks.

## Why (b) is the load-bearing clause

The tempting fix is to widen the inference — teach the ceiling more ways to conclude a round is
over. **Widening the inference is how the bug got here.** Every widening adds a way to be wrong in
BOTH directions, and one of those directions is genuinely expensive: suppressing a round that is
actually in play hides a real, moving number from a reader watching the tournament. Showing a
stale price is bad; withholding a live one is worse.

So the terminal case comes from the assigned status and is combined with `max()` / `or`, never a
replacement. That makes the guarantee **structural rather than promised**: an event in play has
the flag False, the expression is bit-for-bit the inference it always was, and the dangerous
direction is not merely unintended but unrepresentable. A reviewer can confirm it by reading one
operator instead of re-deriving a case analysis.

## Why (c) is not optional

The archive case is the one that gets found — someone opens an old page and the numbers are
absurd. The mid-event case is the one that gets *broken by the fix* and never noticed, because it
requires the event to be live at the moment somebody looks. It needs a named test that pins the
live behaviour, or the next person to widen the terminal case will quietly buy the archive at the
cost of the live path.

## The census clause this arrived with

#1803 was filed scoped to golf, because golf is where it was measured. Under ruling 030 the lane
censused the class before scoping the fix, and found a **second reachable production specimen** in
a completely unrelated mechanism: `event:ufc:26aug08` (card status `settled`, fought 2026-08-09)
rendered two live ladders because combat infers settledness from **price convergence**
(`>=0.97 or <=0.03`), and a fight that finished at a coin-flip never converges. A third adapter
(cycling) shares the defect latently.

Three different inferences — a sibling ceiling, a price threshold, an own-grade check — one shared
omission. **The doctrine is the class; the ticket was one specimen of it.** When a surface infers
a state the event already declares, assume the class and go looking.
