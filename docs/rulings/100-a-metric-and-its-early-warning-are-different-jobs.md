# RULING 100 — A metric and its early warning are different jobs, and both are reported

date: 2026-08-19
author: Fable
issues: #1958

Issued on UX-P104 (cycle 101) directive (b), closing the question ruling 098
opened and deliberately did not answer.

## The case

Ruling 098 established that `boring-rate@20` had two windows measuring two
different twenties — the SERVED page a visitor scrolls, and the futures-only
list produced by filtering the payload to `type == "futures"` first — and that
neither may stand in for the other. What it did not do is say **which one the
metric targets.**

That gap is not academic. Cycle 100 exited with two defensible numbers for the
same named metric on the same day:

```
SERVED window        0/40 slots   = 0.00%    (the floor doing its job)
futures-only window  6/100 cards  = 6.00%    (pooled, 5 distinct builds, 2 days)
```

Both correct about their own window. With no assigned role, a reader picks one —
and which one they pick decides whether #1958 is closed or open. A cycle was
spent on that question rather than on the feed.

## The ruling

**`boring-rate@20` targets the SERVED window.** What users see is the product
truth. A metric that grades a page nobody scrolls is grading a data structure.
`enforce_first_page_quality_floor` is its control, and on the served window the
number is 0.00%.

**The futures-only rate is RETAINED as the SUPPLY metric.** Not demoted, not
deprecated, not a footnote. It measures **the pool the floor must screen**,
which makes it the early warning for pages the floor cannot save.

**Both numbers, every audit, named windows and named roles.**

## Why the supply number cannot just be dropped

Because a floor working hard and a floor with nothing to do **read identically
on the served number.** Both print 0.00%.

The two diverge only on the input. If the supply rate climbs from 6% to 30%
while the served rate holds at 0.00%, the floor is absorbing a worsening pool —
and it is absorbing it with a fixed budget of twenty slots. The first page it
cannot save is the first page anyone hears about, and by then the trend that
predicted it has been invisible for weeks.

So the general clause: **a control's grade and its input's grade answer
different questions, and reporting only the grade that is green hides the day
the input starts moving faster than the control can absorb.**

## Why this is not a new doctrine clause

The general sentence above is a specialisation of doctrine clause 14 — *two
measurements never computed side by side have not been compared* — which is
already banked and already on master. Clause 14 says put both numbers in one
place; this ruling says which is which. A second clause restating the first is
the duplication clause 14 exists to prevent, so the obligation lives here and
cites there.

## The obligation, and where it is discharged

Naming the windows was ruling 098's requirement and shipped in cycle 100.
Naming the **roles** is this ruling's, because a reader who cannot tell the
target from the early warning will treat one of the two numbers as noise — which
is the same failure as printing one of them.

| instrument | prints |
|---|---|
| `backend/scripts/audit_feed_quality.py` | `boring-rate@20 [SERVED — the target]` then `[SUPPLY — the pool the floor screens]` |
| `backend/scripts/census_boring_rate.py` | SERVED first (the target), SUPPLY second (the early warning) |
| `backend/scripts/boring_rate_across_days.py` | both, each carrying its role |

`backend/tests/test_boring_rate_across_days.py` asserts on the **roles**, not on
the prose around them, so the wording can be improved without the guard
dissolving and without it pinning a sentence nobody meant to freeze.

## What this does to #1958

The issue's headline metric now reads **0.00% on its target window**, which is
the bar. It stays open on the supply side, where the standing offender is a
regional-election class handled separately in the same cycle — see the admission
decision in `backend/tests/test_feed_regional_election_admission_1958.py`.

## Scope

`boring-rate@20` and the two windows it is counted on. It does not touch
`ladder/bucket-rate@20`, `duplicate-family-rate@20` or
`explanation-coverage@20`, which are still counted the way they always were —
those need the same treatment and have not had it, and pretending otherwise
would be the "renamed into its replacement" failure ruling 098 already refused.
