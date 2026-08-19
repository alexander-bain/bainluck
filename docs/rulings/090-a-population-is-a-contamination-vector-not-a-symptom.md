# RULING 090 — A population is a contamination vector, not a symptom

date: 2026-08-19
author: Fable
issues: #1981 · #1979 · #1947

**A cleanup population is defined by the VECTOR that contaminated it, never by the symptom it
presents. Rows that look the same and were broken by different writers are two populations,
and grafting the odd ones onto a reviewed object as "exceptions" destroys the review.**

## Why

Three of #1981's eight flapping rows carry a *correct* `espn_id`; they are contaminated purely
through `external_id`. They present identically to #1947's rows — same flap, same wrong final,
same 300-second cadence — and the tempting move is to add them to #1947's already-reviewed
`espn_id` repair plan as three exceptions.

That move is what this ruling forbids, for two reasons.

**The repair would not fit.** #1947's plan writes `espn_id`. On these three rows `espn_id` is
already right, so the write is a no-op that reports success — a repair whose green is
indistinguishable from having done nothing (gotcha #53's shape, in the apply direction).

**And the review would be destroyed.** A reviewed population is an object with an address: Alex
approved *those rows*, and the address is the promise that what he read is what the apply
writes. Rows added after review are rows nobody approved, travelling under an approval that
covers their neighbours. An exception grafted onto a reviewed object silently converts a
specific approval into a general one.

So: same symptom, different vector, different population, its own census, its own address, its
own MC. Two small reviewed objects beat one large object with a footnote.

## Charter case

Queue 370 found the eight-row flapper population and flagged the three `external_id`-only rows
**for population assignment rather than silently folding them in** — the correct instinct, and
queue 371 ruled it: they join #1981's cleanup population, not #1947's.
