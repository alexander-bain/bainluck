# RULING 062 — A branch bases where its dependency lives, and disjointness is measured at content level

date: 2026-08-14
author: Alex
issues: #1865

## Part 1 — the base

When stacking a queue onto its lane's own unmerged head would require
**re-creating a module that exists only on master**, the branch bases on
**master** instead.

The successor-branch default (invariant 2, amended 2026-08-07) is a rule about
**not waiting for integration**. It was never a rule about inheriting a base
that lacks your dependency. Read the other way it produces exactly two bad
outcomes, and a lane will pick one of them under time pressure:

- build against a module that is not there, or
- **re-create the module on the branch** — which is gotcha 134 committed by the
  very queue that banks gotcha 134.

Named specimen: `program/ux-64` needed `lib/calibrationProviders.ts`, which
landed on master as CAL-P050 (`91ae8c8e`) and does not exist on the ux-63 base.
Branching from `origin/master` was **the right paranoia**.

Second specimen, one cycle later and in the opposite direction:
`program/ux-65` needed the CURRENT `backend/tests/test_product_brain_integrity.py`,
which is blob `d1696282` on master and blob `7480632d` on ux-60/-61/-62/-63 —
the stack carries a **stale copy** of the only file that queue edits. Same rule,
same answer. The test is not "is master newer"; it is **"where does my
dependency live"**, and it is answered by measuring blobs, not by preference.

## Part 2 — the disjointness measurement

**`merge-tree`'s conflict COUNT is not a disjointness measurement when two
branches have distant merge bases.** It re-reports every difference between the
stack and master, so it reports conflicts that are not conflicts between the two
lanes at all.

A lane declaring a branch independent therefore **enumerates the regions each
side edits and shows they do not intersect** — which is why the Integrator can
take it without archaeology. Asserting disjointness is worth nothing; the
Integrator cannot check an assertion without redoing the work.

Named specimen: `merge-tree program/ux-63 program/ux-64` reports **five**
conflicts. Measured at content level: ux-63 does not touch the By Source region,
ux-64 does not touch any of ux-63's regions, and the only true overlap is an
import block where each adds a **different** module — keep both. Five reported,
**zero real**.

## Sibling

Gotcha 134 (*a premise census must read the world it will merge into*) governs
what you **read** before claiming. This ruling governs where you **branch** after
reading, and what you must **measure** before calling the result independent.
