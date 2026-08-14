# RULING 060 — Never grow a graded cohort in place

date: 2026-08-14
author: Alex
issues: #993 #1861 #1545

## The ruling

A graded cohort is a **denominator**. Growing it silently voids every read ever taken against it.

So: a new probe class ships in a **separate split** — `canary` — and enters the graded set only at
a **deliberate, announced re-baseline** that re-states the prior numbers on the new denominator.

Never by addition into the live split. Never "just to get a bigger n."

## Why this is a ruling and not a preference

The failure mode is that **nothing breaks**. Adding six probes to a 46-probe registry does not
error, does not turn a gate red, and does not announce itself in a diff review — it produces a new
number that *looks like* the old numbers and is silently incomparable to all of them.

Every row of the §5 ledger in `docs/search-scoring-spec.md` reads `NN/44`. That 44 is load-bearing:
it is what makes `38/44` on v3806 comparable to `38/44` on v3807, which is the entire basis for the
attribution model this program runs on. Move it once, without a re-baseline, and every prior row
becomes a number whose meaning you have to reconstruct from commit archaeology — assuming anyone
notices it moved at all.

A measurement defect committed in the name of fixing one is still a measurement defect. It is
worse, in fact, because it arrives wearing the clothes of rigor.

## The occasion

#1861 established that the 46 probes could not grade an outcome-evidence change: `-44` (#1843)
shipped a real ranking change alone as v3807 and moved **zero** probes, with byte-identical
per-probe dispositions against v3806.

The fix required **new probes** — that is what an instrument's blind spot costs to close. And the
only obvious way to add them was into `--split test`, the graded cohort.

LAT-P052 declined, and shipped the OUTCOME-EVIDENCE class into `canary` instead, leaving
`--split test` at exactly 46 probes / 44 graded. This ruling ratifies that decision and generalises
it past the one case.

## The mechanism worth preserving — conditional uniformity

The insight that made `-44`'s null read explicable rather than merely disappointing:

**#1843's lift is conditionally uniform, and the rival set decides.** In four of five specimens,
*every* candidate gains MC4 together — so the relative order is unchanged and **top-1 structurally
cannot move**. The change was real, the metric was blind to it, and the blindness was not bad luck:
it was a property of the class.

`club kid` is the exception and the **existence proof** — found, not predicted. A rival displays it
at outcome rank 3 of 17, inside its own top-3 cut, so that rival already had MC4 and did not move
while the others did. Top-1 moves. Had the class been built from prediction alone, that specimen
would not be in it.

Alex, ratifying: *"the conditional-uniformity insight is exactly why #1861 said 'unmeasured,' and
now the instrument exists."*

## What a deliberate re-baseline looks like

Not forbidden — **scheduled, announced, and paid for**:

1. The canary class has been shown to discriminate the change class it was built for.
2. The re-baseline is its own act, not a rider on a ranking change.
3. Every prior number in the ledger is **re-stated on the new denominator**, or the ledger is
   explicitly sectioned at the boundary with both denominators named.
4. The boundary is written into `docs/search-scoring-spec.md` §5 where a reader meets it, not only
   into a handoff nobody re-reads.

Until all four are done, `canary` grades nothing that the ledger cites.

## Siblings

* [056](056-unmeasured-is-not-ineffective.md) — the sibling this is deliberately **not** merged
  into. 056 governs how a null read is **written down**; 060 governs what you may do to the
  **instrument** that produced it. Same window, same occasion, two different obligations.
* [049](049-a-criterion-that-cannot-fail-is-not-evidence.md) — an instrument that cannot fail, and
  a denominator that quietly moves, are the same disease at two sites.
* [050](050-a-control-that-cannot-fail-is-not-a-control.md) — the null read is taken; this says the
  cohort it is taken against holds still.
* [052](052-measure-the-instruction-before-you-obey-it.md) — measure the instrument, including when
  the instrument is your own probe set.
