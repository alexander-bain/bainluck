# RULING 122 — Four rounds inside one design is a design question, not a merge cadence

date: 2026-08-23
author: Fable (directive 2026-08-23, pasted and reviewed by Alex)
issues: #2020, #2091

**Tranche A is PARKED.** No round 5 until a premise-first design one-pager — owned by
`lane4`, **no code** — survives review. The two attended applies stay **HELD
indefinitely**: track their age in the CHAIN HELD table, and **stop escalating**.

## What is being parked, and what is not

Parked: the 60,889-row prune's **rail**, and the loop that has been rebuilding it.

Not parked, and not re-quoted here either: the **census**. The 2,565 / 60,889
partition reproduced three times and that half stands on its own. It is also 3 days
old and must be re-derived at fire time rather than carried — proving a gate is not
proving a subject.

Also unchanged: this lane cannot fire the applies regardless
(`ADMIN_TOKEN_DESTRUCTIVE` is absent here and present on the dyno, queue 315's
ruling). The park is not a workaround for an access limit. It is a decision about a
design.

## Why: the two failures point in opposite directions

Four consecutive certification rounds returned BLOCK — R1, R2, R3, R4 — and three of
them landed on the same defect class one layer in. The shape is clearer stated as a
pair than as a count:

* **The allowlist deleted rows it should have kept.** `PARENT_SUBSTANCE_COLUMNS` was
  a 9-field enumeration of what counts as substance, and R3 found a distinct-game
  candidate whose only observation was `opening_home_spread=-1.5` being DELETED.
* **The denylist keeps every row, including the ones it exists to delete.** R4 found
  that `event_tags` is parent-substance under deny-by-default while *every candidate
  row must carry* `provenance:unanchored` — so the population is **mathematically
  empty**, `deletable=0`, and all 31 batches are a permanent `no_work`.

**Both were green.** That is the finding. A design whose two opposite corrections
both pass their own suites is not being narrowed by successive rounds; it is being
demonstrated to be under-specified. Window 389 predicted the first half of this in
writing — *"a fourth round that lengthens the allowlist is the same move again"* —
and adopting the denylist answered the prediction and produced the mirror failure.
Five threshold-moves inside one design have now produced five specimen classes.

## And the green was over SQL PostgreSQL cannot execute

R4's other P1: the new `discover_interactions` / `discover_review_decisions` guards
emit `varchar = integer`. The 111-test suite was green over it because the fakes
assert that table names appear in the SQL string and never ask a database to
type-check it (gotcha #122). So the assurance the rounds were accumulating was not
weak — parts of it were **not assurance at all**, and no number of further rounds
inside the same harness distinguishes the two.

The self-oracular defect R3 named also RECURRED in R4: the schema-minus-denylist
oracle subtracts the production denylist, so a denylist entry cannot be adjudicated
by the test that reads it.

## The general clause

**When successive certified rounds inside one design each move a threshold and each
produce a new specimen class, the open question is the design, and the next artifact
owed is a premise document — not another round.** A round is cheap to authorize and
feels like progress because something always changes; that is exactly why the count
of rounds is a poor signal and the *shape* of their failures is a good one. Two
corrections that fail in opposite directions bound the truth between them and locate
it in neither.

Corollary, and the reason the applies are held *indefinitely* rather than gated:
**an age that is escalating against a question nobody is answering is noise.** The
383 row escalated at age 5, was answered with a rebuild, blocked, and escalated
again at 6. Re-escalating it a third time would report urgency to a lane that has
already done the only thing urgency asks for. Track the age so the item cannot go
quiet; stop treating the age as a prompt to rebuild.

## What unparks it

A design one-pager that states, before any code:

1. what a row's **substance** IS — the model, not its current enumeration;
2. how that model is **oracled independently** of the production constant that
   implements it, so an omitted field cannot vanish from implementation and oracle
   together;
3. how the guards are **type-checked against a real PostgreSQL**, given that the
   fakes demonstrably cannot;
4. what the **keeper rule** does about game-market children (#2057: 17/17 duplicate
   games carry markets on ONE copy only), since a row presenting `linked_copies == 1`
   can still be the wrong keeper.

Retired, not merely stale: R4's quoted **1,230 withheld / 59,659 deletable** price.
It is the old ten-FK census, and the tables v4 added had no FK to `events.id` at all.
Do not re-quote it.
