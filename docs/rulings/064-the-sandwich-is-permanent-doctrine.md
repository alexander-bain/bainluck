# RULING 064 — The sandwich is permanent doctrine for this program

date: 2026-08-14
author: Alex
issues: #993 #1545

## The ruling

Every ranking change this program ships is measured by the **sandwich**:

1. a read taken **before**, on its own deploy;
2. the change deployed **alone** (ruling 046);
3. a read taken **after**, **twice**, with cache state recorded;
4. against a **control that was armed before the change shipped** (ruling 050).

This is now **permanent doctrine for the latency program**, not a practice the lane may re-derive
each cycle from first principles.

## Why it is doctrine now, and was not before

Because it has **paid three times, in three different ways**. One payout is a technique. Three
payouts in three distinct failure classes is a property of the method.

**1. A hidden bug.** `search_offline_rerank.py` hand-rolled `Evidence(name=display_name, kind=kind)`
— **two of six fields** — off the typeahead *response*. But the response is deliberately not the
evidence: `typeahead_search` pops `_derived`, `_aliases` and `_outcome_names` before returning,
because a 40-outcome market would ship 40 strings per keystroke. The instrument had been modelling
a different server for four cycles, and it took the idempotence half of the sandwich to see it —
re-ranking the scorer's own output destroyed five passes, every one a **team**, every one
`MC0 → MC1` on aliases the wire never carried.

**2. An inverted attribution.** `us open` was counted among #1839's five casualties when the
`+11±1 → 39–41` band was drawn. It has **no tennis resolver** among the four `_detect_query_*`
sites, so it never had a query-derived twin for #1839's guard to block, and `-43` could not
possibly have fixed it. The `-43` projection missed by 1 not because of noise but because **one
probe had been attributed to the wrong mechanism**. Only a per-probe read on an isolated deploy can
surface that; an aggregate cannot.

**3. A confirmed control.** `-45` deployed alone as **v3812** and returned **38/44, MRR
0.8695652, 0 of 46 dispositions differing, `regression: 0`** — identical to v3806 and v3807 to
seven decimal places, across two genuinely distinct captures.

Alex, on what the third payout buys:

> *"The attribution model is now VALIDATED, not assumed, and every future ranking merge inherits
> that confidence."*

## The cost is the ruling

Three consecutive windows kept a control **armed** — declining to spend it, declining to
approximate it, carrying the debt in the handoff — so that when it finally fired it would mean
something. A control spent early is a control that proves nothing.

That patience is the expensive part, and it is exactly the part a lane under time pressure will
drop first. Writing the protocol down as doctrine is what makes the cost non-negotiable rather
than a judgement call re-litigated every cycle.

## What this does NOT license

A clean control is **not** a general licence. Ruling 050 attaches a HALT to a **declared** null
prediction, and the declaration must be made **before** the read. The v3812 control is **spent**:
it may not be re-armed, and it may not be cited as evidence that some later change also moves
nothing. The next change predicted to move nothing needs its own declaration, its own deploy, and
its own read.

## Siblings

* [046](046-a-stacked-change-is-measured-on-its-own-deploy.md) — the deploy-isolation half. Without
  it, step 2 collapses and nothing is attributable.
* [050](050-a-control-that-cannot-fail-is-not-a-control.md) — the armed-control half, and the HALT.
* [049](049-a-criterion-that-cannot-fail-is-not-evidence.md) — the same disease at the criterion
  site rather than the measurement site.
* [060](060-never-grow-a-graded-cohort-in-place.md) — the sandwich is only meaningful while the
  denominator holds still.
* [066](066-a-deferred-read-owes-a-receipt.md) — what the lane owes on the windows when the
  sandwich cannot be completed.
