# RULING 045 — Monotonicity protects the DIRECTION, never the INPUT: the term you add must be assigned, not merely available

date: 2026-08-12
author: program-ux lane (UX-P069) — **AMENDS ruling 036. Flagged to Alex for ratification, not self-certified.**
via: applying ruling 036 across the remaining adapters after Alex's 2026-08-12 ratification made it "the standing shape for every settledness path"
issues: #1812 · #1803 · #1546

> **(a) Ruling 036's `or`/`max()` guarantees only that a new term cannot REMOVE settledness. It
> says nothing about whether the term is TRUE. A monotone fix fed a wrong input is still wrong —
> and it is wrong in a new way the original inference was not.**
>
> **(b) So a term admitted as "assigned state" must be genuinely assigned. If it is itself derived
> from the inference it is meant to override, OR-ing it in chains two inferences and calls the
> result authority.**
>
> **(c) A parent's settlement transfers to its children only where the parent is ATOMIC IN TIME.
> Where children resolve independently, the child consults its own assigned state and nothing
> else.**

## What produced it

Alex ratified 036 on 2026-08-12 and named monotone-inference-under-assigned-state the standing
shape for **every** settledness path. Making "every" true meant applying it to the adapters
UX-P068 had not reached. The census found the defective line — `lead_prob >= 0.97 or lead_prob
<= 0.03`, byte-identical — in three more: tennis, awards, election.

The mechanical fix suggested by the two already-converted adapters is *"OR in `event_status`"*.
Applied to awards and election it is **wrong**, and the way it is wrong is the ruling.

In both of those adapters `event_status` is **itself computed from the same price convergence**
(`event_awards.py`, the `marquee_top >= _WON_PRICE_THRESHOLD` arm; `event_election.py`, the same).
Passing it as the assigned term satisfies every property 036 asks for — it is OR-ed, never
substituted, and the result is provably monotone — while being a second helping of the very
inference the ruling exists to demote.

And it does not merely fail to help. It introduces a **new** defect the original code did not
have: one runaway favourite crossing 0.97 in the marquee category would mark **every other
category settled** while they are genuinely undecided. The old code could leave a decided question
looking live; the "fixed" code would have made undecided questions look decided. That is the
expensive direction — the one 036(b) was written to make unrepresentable — arriving through the
**input** while the operator stayed innocent.

## Why 036 did not already cover this

036 is a statement about an operator. Read as a checklist it is fully satisfiable by a wrong
program: *is the term OR-ed in? yes. is in-play bit-identical? yes. is it monotone? yes.* All three
hold for the awards mistake above. The property being guaranteed is real and it is simply not the
property anyone cared about — nobody ever feared the operator, they feared being wrong about
whether the thing was over.

This is the same shape as gotcha #128, banked the same day: a check can be structurally impeccable
and still verify nothing. **A guarantee about form is not a guarantee about content**, and the more
convincing the form, the less anyone re-reads the content.

## (c), and why an election is the exception that names the rule

The question "may the parent settle the child?" has a crisp answer: **only if the parent is atomic
in time.**

| domain | atomic? | term |
|---|---|---|
| fight card | yes — one night, one venue | card status |
| golf tournament | yes — the field finishes together | tournament status |
| grand tour | yes — the race concludes | race status |
| tennis draw | yes — a concluded slam means every match was played | tournament status **+** the match's own |
| ceremony | yes — every category is awarded that evening | ceremony graded **+** the category's own |
| **election** | **no** | **the race's own status/grade, and nothing else** |

Races are decided independently and runoffs run weeks past election night, so a called marquee
race says nothing about a down-ballot one. Give election the parent term and a contested House
race renders settled because a Senate race was called.

The general form: **a container settles its contents only when the container is an EVENT. When it
is merely a collection, it settles nothing.** Worth asking of any future adapter before wiring the
parent in, because the two look identical in the payload — both are a parent with children — and
only the real-world referent tells you which one you have.

## What this costs, deliberately

Each adapter now supplies its own explicitly-named assigned term rather than a uniform
`event_status`. That is more code and less symmetry, and it is the point: the asymmetry is real, so
a uniform fix could only have been uniform by being wrong somewhere. The guard is mechanical rather
than remembered — `tests/test_settledness_authority.py` asserts by source inspection that no
adapter passes a price-derived term, and that awards' graded term is captured **before** the
price-crown block writes `won = True` onto a merely-converged leader.
