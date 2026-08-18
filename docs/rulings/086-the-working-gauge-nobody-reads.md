# RULING 086 — The working gauge nobody reads is the same as no gauge

date: 2026-08-18
author: Fable (LAT-P068 directive)
issues: #1501 #1545 #1609

## The ruling

**A correct, tested instrument with no reader is not an instrument.** It counts as ABSENT in every
account of what this system can see, and a window that owes a read may not discharge the debt by
noting that the gauge exists.

Three obligations follow, and they are the whole ruling:

1. **Wiring a gauge to a surface someone already reads is part of building it.** An instrument
   whose only consumer is its own unit test is unfinished, not finished-and-unused.
2. **When a read is owed and the obvious gauge cannot answer it, check for a second gauge before
   owing it again.** "Owed" is a claim that the number is unreachable. Make that claim only after
   looking.
3. **A gauge wired on an unmerged branch is not yet a reader.** The debt closes on the *read*, not
   on the commit that would enable it.

## Why — the occasion, and it is embarrassing in a specific and useful way

There are two hard-kill counters in this tree, and only one of them works.

| | `task-metrics.hard_kills_24h` | `get_hard_kill_census()` |
|---|---|---|
| written by | `_tracked_run`, **a helper the task body elects to call** | celery's `task_prerun` / `task_postrun` signals |
| coverage | blind to **30 of 117** beat-scheduled tasks, and blind to any child killed before it reaches the helper | every execution of every task, no cooperation required |
| tested | — | `tests/test_task_lifecycle_hard_kills_1501.py` |
| production consumers, 2026-06-24 → 2026-08-18 | many | **ZERO** |

`redis_state` had already written the diagnosis in its own comment: *"a compensating instrument
that starts below the failure boundary is not a compensating instrument."* The counter that starts
below the boundary is the one everybody read. The counter that starts above it was built by #1501
item 2 **for exactly this reason**, tested, and then left unreachable from outside the process.

**Eight consecutive latency windows carried `hard_kills_24h` forward as an owed read.** Each of the
eight recorded the debt honestly. Not one of them asked whether a *different* gauge could answer the
question, and the answer had been sitting in `redis_state.py` the entire time, one import away,
with a passing test.

The eighth window (LAT-P067) finally wired the census into `/api/admin/ops-snapshot`. And that is
where clause 3 comes from, because **the read is still owed as this ruling is written**: the wiring
rides `program/latency-60`, which has not merged, so production's `ops-snapshot` still returns
`celery: {queue_depths, task_health}` and no `hard_kills` key at all. A gauge one merge away from
being readable is exactly as informative as a gauge that does not exist.

## The aphorism

> **The working gauge nobody reads is the same as no gauge.**

Alex had already stated the general case one level up, twelve lines away in `sentry_filter`, about a
counter of discarded events:

> *"A discard counter nobody can read is the same defect one level up."*

This ruling is that sentence promoted from a comment about one counter to a standing obligation
about all of them.

## Why it is doctrine and not a note

Because the failure is **self-concealing**, which is the property that earns permanence. A broken
gauge announces itself: somebody reads it, the number is wrong, the bug is found. An *unread* gauge
produces no signal of any kind — not a wrong number, not an error, not a gap. The only trace it
leaves is a debt entry in a handoff file, which reads as diligence.

So the honesty of the eight windows is the point, not an excuse. Every one of them did the right
visible thing. The system still went two months with its only sound hard-kill instrument dark,
because "we owe this read" and "this read is impossible" render identically in a report, and nobody
was obliged to tell them apart. That is the same shape as gotcha #53 — an empty response and an
absent one reading the same — moved up from the wire to the instrument shelf.

## What this does not say

It does not say build fewer instruments, and it does not say every gauge needs a dashboard tile. A
gauge read by a sentinel, a test that asserts on a live value, or a documented one-line curl in the
runbook all count as readers. The bar is that **some named consumer outside the instrument's own
test suite reads it on a cadence somebody could describe.**

It also does not license deleting an unread gauge instead of wiring it. `get_hard_kill_census()` was
right and its neighbour was wrong; the remedy was a reader, never a removal. Clause 2 exists so the
*next* eight windows check the shelf before declaring a number unreachable — the cost here was not
eight duplicated notes, it was two months of not knowing which tasks were being killed.

## How to apply it

- Owing a read? Grep for a second instrument first. Record what you checked, not just what failed.
- Shipping an instrument? Name its consumer in the same commit. "Tested" is not "read".
- Discharging an instrumentation issue? It closes on a **production read**, per
  `feedback_issue_closure_proof` — not on the merge, and certainly not on the branch.
