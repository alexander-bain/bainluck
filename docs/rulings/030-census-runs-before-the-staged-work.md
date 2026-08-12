# RULING 030 — The census runs BEFORE the staged work, and may re-decide it

date: 2026-08-12
author: Fable
via: cycle-64 acceptance, ratified
issues: #1546 · #1741 · #1742 · #1776

> **On the UX program, the entity census runs FIRST — before the staged queue is executed — and
> its output is allowed to replace the queue that was staged. That ordering is the expected
> shape of a cycle, not a nicety.**

## What produced it

UX-P064 was staged as a page queue. The census ran first, and it found that **118 of 118 upcoming
games across all 29 leagues carried no win probability** — including a live MLB game holding five
sources. The rail the product exists to show had never shown a number, on the "check tonight's
league" path, and the frontend was exonerated by its own correct null-handling: it was rendering
exactly what it was handed.

The same run found the second-order defect. The instrument that should have said so was
**measuring the wrong column** — recomputing a tier over `sections` while the routes declared
their own over a documented superset (T3 0 vs 6, T0 0 vs 3). Three cycles of findings had been
read off that column, and the games amendment had contributed **zero to every tier since it
shipped** without anyone being able to see it.

Neither finding was reachable from the staged brief. Both were one command away from the
instrument.

## Why this becomes standing, rather than "nice catch"

It is now the **fourth consecutive cycle** in which running the instrument first changed what the
cycle did — cycles 61, 62, 63 and 64. A practice that re-decides the work four times in a row is
not luck, and it is not the lane being clever. It is the ordinary consequence of a fact about this
codebase: **the staged brief is written from what someone believed the surface looked like, and
the census is written from what the surface actually returns.** When those disagree, the brief is
the one that is wrong, every time so far.

The corollary matters as much as the rule: a census that comes back **byte-identical** to the
last one is itself a finding (cycle 63 — the refusal to move was the bug, a 24h mirror that
scheduled nothing to replace it). Read the output; never file it.

## The obligations that come with it

1. **Warm before you conclude.** After #1767 a cold key still serves the mirror on the first read;
   the second is correct. A single-pass sweep re-measures yesterday and looks authoritative doing
   it. `--class competition` on 2026-08-12 read `stale` on all five rows.
2. **A histogram is a snapshot with a date on it.** Tiers are season-aware and are supposed to
   move; an undated number becomes a permanent claim.
3. **A decision scheduled against census numbers is void if the instrument was wrong.** Spec §11's
   threshold call was queued against the artifact column and is **re-scheduled** to the declared
   one, after the owed warmed re-run lands post-deploy. Do not re-present superseded numbers to
   Alex; say the decision is waiting on a measurement, and name the measurement.
