# RULING 076 — planner cost ranks PLANS FOR ONE STATEMENT; across two different statements it is not a comparison, and a gate built on one authorised a 4.8× regression with a green certificate

date: 2026-08-17
author: Fable
issues: #1866, #1545, #1913

## The ruling — Fable's clause, verbatim

Issued in the FABLE DIRECTIVE of 2026-08-17, on the LAT-P061 acceptance:

> The withdrawn flip is the program's best decision this week: a gate that compares planner cost
> across two different statements ranked them backwards, and only the stopwatch caught it. Bank
> that gate defect.

## The specimen

`docs/audits/latency/lat-p058-golf-index-spec.md` **step 5.3** is the gate that authorises flipping
`GOLF_IDENTITY_SPLIT_SCAN`. It has two conditions, and one of them is sound:

| condition | kind | verdict |
|---|---|---|
| both `UNION` branches plan as `Index Only Scan` | **plan SHAPE**, within one statement | sound, necessary |
| `UNION` total cost < the `OR`'s **128,191.5** | **cost MAGNITUDE**, across two statements | **not a comparison at all** |

LAT-P061 ran it. Both conditions passed, the second by a landslide: the `UNION` planned at
**4,361.77**. Then the lane took a stopwatch to it — 11 `EXPLAIN ANALYZE` executions, the last 8
alternating `OR`/`UNION` so warm-cache drift could not favour either side:

| | planner cost | warm median runtime | shared buffers |
|---|---|---|---|
| `OR` (live, post-index, `BitmapOr`) | **12,243.92** | **≈18.4 ms** | 1.00× |
| `UNION` (the pending flip) | **4,361.77** | **≈88.2 ms** | **2.45×** |

**The gate said the `UNION` was 2.81× cheaper. The stopwatch said it was 4.79× dearer.** The gate
ranked the two statements backwards by a factor of **13.5×** (4.79 ÷ 0.356) — and by **141×** against
the stale 128,191.5 bar the gate actually quotes, which was the *pre-index* `OR`'s cost and had been
superseded by the very DDL the flip was waiting on.

94 of the `UNION`'s 98 ms is its own `HashAggregate` — the de-duplication `UNION` performs and `OR`
never pays. **That work is real, it is the whole regression, and the planner priced it at nearly
nothing.**

Had LAT-P061 followed the runbook as written, it would have flipped the flag, recorded a green gate,
and shipped a 4.8× slowdown on the golf identity prefilter. The gate would have been the evidence.

## Why the number cannot do the job asked of it

`total cost` is in **arbitrary planner units** calibrated by `seq_page_cost`, `random_page_cost`,
`cpu_tuple_cost` and friends. Its one contract is **ordinal, and scoped to a single statement**: of
the plans the planner enumerated *for this statement*, the lowest-cost one is the one it will run.
Nothing in that contract survives being carried across a statement boundary:

- **The estimates come from different row-count paths.** The `OR`'s `BitmapOr` estimate and the
  `UNION`'s two-branch-plus-aggregate estimate are built from different selectivity products against
  the same statistics; there is no reason for their *errors* to be equal, and the gate's arithmetic
  silently assumes they are.
- **Cost does not model the cache.** Both statements here read the same pages; the `OR` finds them
  resident and the `UNION` re-reads 2.45× as many. `random_page_cost` is a constant, so the planner
  charges an identical price for a buffer hit and a disk read.
- **A statement can be cheaper AND slower**, which is exactly what happened: fewer estimated units,
  more actual work, because the `HashAggregate`'s real cost is memory-and-CPU shaped and the model
  is page-shaped.

Two shapes, two models, one scale — and a difference on that scale carries no information about
which one finishes first.

## The obligation

**A gate that authorises replacing statement A with statement B is graded on MEASURED, PAIRED,
ALTERNATING runtimes on production data. Plan shape is necessary and never sufficient. A cost
number may appear as corroboration; it may not be the criterion.**

Concretely, for any query-rewrite flip:

1. **Shape first, as a precondition** — the right indexes, the right scan types, no surprise nodes.
   A wrong shape fails immediately and cheaply.
2. **Then the stopwatch, ALTERNATING** — A/B/A/B on the live database, ≥8 executions after
   warm-up, medians reported with the spread. Alternating is not decoration: a sequential
   all-A-then-all-B run hands the second arm a cache the first arm loaded.
3. **Report buffers alongside time** — `EXPLAIN (ANALYZE, BUFFERS)`. Time tells you what happened
   today; buffers tell you what will happen when the pool is under pressure.
4. **A bar quoted from an earlier window is re-measured, never re-quoted** (ruling 069). Step 5.3's
   128,191.5 was already three months of table growth and one index build out of date at the moment
   it was read.

## The second obligation, which is what the disposition is for

**Measured-worse code behind a permanently-off flag is not a rollback path. It is a trap.**

`golf_identity_select(split=True)` is now known-slower, is unreachable in production, and is fully
tested — which is precisely what makes it dangerous: the next reader finds a maintained,
green-tested, documented alternative shape behind a one-line config flip, and the measurement that
refused it lives in a report they have no reason to open. **The flag reads as an unfinished
migration, not as a closed experiment.**

So a refused rewrite is **deleted, not parked**. The record of why lives in the ruling and the audit
doc; the code does not stay behind as an invitation. Removal of `GOLF_IDENTITY_SPLIT_SCAN`, the
`UNION` branch and its tests is filed as its own scoped item rather than smuggled into an unrelated
queue.

## Application

- Any flag whose ON position has been **measured worse** is scheduled for deletion in the same
  window the measurement lands. "Leave it, it is off" is how a trap is set.
- Any runbook step whose criterion is a planner-cost comparison across statements is a **defect in
  the runbook**, and is rewritten to the four-step form above before it is handed to anybody.
- `EXPLAIN`-derived numbers may gate **shape**. They may never gate **speed**.

## Sibling rulings

- **050** — register the prediction before the read. Step 5.3 was a registered criterion, and the
  reason this was caught rather than argued is that the lane measured anyway.
- **069** — the ledger is a floor, not an oracle; measure, never quote. The 128,191.5 bar is a
  quoted number that had already moved.
- **074** — a green pass names the work it did. Same family, one level up: there an instrument
  reported success for work it never performed; here a gate reported an advantage that ran backwards.
- **071**, **072**, and gotchas **#49 / #53 / #54 / #124 / #135** — the instruments-that-lie taxonomy.
  This is its planner-statistics member: *"Total Cost ≠ runtime until act+loops say so"* was already
  a note in the db-query memory; it is now a ruling because a runbook shipped that ignored it.
