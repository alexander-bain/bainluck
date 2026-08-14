# RULING 066 — A deferred read owes a receipt, not an assertion

date: 2026-08-14
author: Alex
issues: #993 #1545

## The ruling

A lane that declines to take an **owed measurement** must produce the **artifact that proves the
deferral was forced** — not a sentence explaining why it was reasonable.

The receipt is what converts *"we did not do it"* from an excuse into evidence.

## The specimen

The exact-fidelity re-derivation was owed for **four consecutive windows**. The fourth declining
window did not merely argue that it had to wait for `-46`. Its producer **reported
`evidence_fidelity: legacy` on both v3812 reads** — a machine-checkable fact, emitted by the
instrument itself, establishing that the endpoint was not yet echoing `_evidence` and that no
exact-fidelity rerank was therefore possible.

Alex:

> *"`evidence_fidelity: legacy` on both v3812 reads PROVES the re-derivation must wait for `-46`,
> rather than asserting it. Fourth window declining, correctly, with evidence."*

## Why a deferral needs a rule when other decisions do not

**A deferral is the one decision that leaves no diff.**

Ship something wrong and there is a commit to find, a test to fail, a read to grade. Decline to
measure and there is *nothing at all* — no artifact, no line in a file, no entry in a ledger. The
absence is indistinguishable from the work never having been owed.

So the only structural defence against a lane that defers indefinitely out of convenience is a
standing requirement that **each deferral emit a falsifiable artifact with a named exit
condition**. Four windows of "we'll do it when `-46` lands" is a lane managing its debt. Four
windows of "not yet, still blocked" with no receipt is a lane that has quietly stopped owing it.

## The receipt works in both directions

The exit condition fired. `-46` merged and deployed as **v3813** at 11:40 PDT; the producer's
fidelity flipped `legacy` → `exact` on the very first capture of the next window; and LAT-P054 paid
the debt in its first hour, before anything else on its slate.

That is the other half of the property: a receipt with a named exit condition **tells the next
window when to collect**. A prose excuse does not, which is how a debt becomes permanent without
anyone deciding that it should.

## What counts as a receipt

Not every apology is an artifact. A receipt must be:

1. **Emitted by the instrument, not by the lane.** `evidence_fidelity: legacy` is the producer's own
   verdict about its own capture. A lane writing "fidelity was insufficient" is an assertion.
2. **Falsifiable at the time it is written.** A reader with the artifact can check it.
3. **Carrying a named exit condition.** *Which* deploy, *which* run, *which* event discharges it.

## Siblings

* [046](046-a-stacked-change-is-measured-on-its-own-deploy.md) — 046 says **when** a read is owed;
  066 says what the lane must produce on the days it cannot take one.
* [064](064-the-sandwich-is-permanent-doctrine.md) — the protocol whose steps generate these debts.
* [065](065-report-the-mutation-split.md) — the same "owed is a state with an addressee" principle,
  applied to a partially-runnable gate rather than to a deferred read.
* [049](049-a-criterion-that-cannot-fail-is-not-evidence.md) — a deferral with no receipt is a
  criterion that cannot fail.
