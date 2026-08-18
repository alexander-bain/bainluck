# RULING 082 — Consistency is the requirement; a specimen's constant is not

date: 2026-08-18
author: Alex
issues: #1894

## The ruling

When a figure is **displayed**, **enforced**, and **derived** in three places, the requirement is
that all three agree. It is **not** that any of them equals a number written down earlier.

The R4 ceiling fix is **ACCEPTED AS SHIPPED**, including its flagged deviation. Queue 363 reported
that the fix makes a standing 5,500/day specimen read FALSE, and offered a one-line revert in
`discard_ceiling_reading` to restore the conservative reading. The offer is **declined**. The
specimen's constant was wrong; the fix is right.

**C-CERT-SENTRY-R5 certifies the three-way equality — displayed == enforced == current-cycle
derivation — and certifies nothing about the value.** A round that reports "the ceiling is now
X, not the 5,500 we expected" and shows the three agreeing is a PASS.

## Why

A ceiling derived from a plan is not a ceiling (queue 363's own title). Once the derivation moved
to the current cycle, every figure downstream of it moved with it — correctly. The 5,500 was a
snapshot of an older derivation that had been transcribed into a specimen, and a transcribed number
outlives the reasoning that produced it. That is what makes it dangerous: it keeps asserting, in a
test, a claim nobody is re-deriving.

The failure mode this ruling forecloses is the tempting one. A specimen goes red; the cheapest way
to green is a one-line change to the code that made it red; the specimen is now satisfied and the
system is now inconsistent, with a test standing over it saying otherwise. **The revert was
available, it was one line, and it would have re-broken the property the queue was opened to fix.**

This is the same shape as ruling 072 — a fixture that agrees with the bug IS the bug — arriving
from the other side: here the fixture agreed with an *obsolete* truth, which is harder to see
because it was never wrong when it was written.

## What this does NOT license

It does not license moving a number to make a test pass. The direction matters: the derivation
changed for a reason that was argued and ratified, and the specimen was then found to disagree.
A constant may be retired **by** a ratified change in derivation. It may not be retired to avoid
one.

And a specimen that goes stale this way is not simply deleted — it is **re-derived**, so the
surface keeps a specimen. An unreplaced deletion is how a class stops being watched.
