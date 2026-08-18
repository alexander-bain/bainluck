# RULING 087 — An exclusion is only safe where a mutation can red it

date: 2026-08-18
author: Fable
issues: #1908 · #1781 · #1600

**Every exclusion, allowlist and carve-out ships with its reddening mutation — a named,
runnable edit that widens the exclusion and turns a specific test red. An exclusion with no
such mutation is not "narrow", it is UNMEASURED, and the two are indistinguishable from the
outside.**

## Why

An exclusion is the one kind of code that gets *quieter* as it gets more wrong. Widen a
grader and it fails loudly on things it should not have failed on; widen an *exclusion* and
everything goes green — which is exactly the signal a healthy run produces. So the usual
feedback loop that keeps a predicate honest is not merely absent here, it is inverted: the
broken state is the comfortable one.

This is the same shape as gotcha #53 (an empty 200 is not an absence) one level up. There, a
response could not distinguish "nothing happened" from "this was deleted". Here, a green run
cannot distinguish "nothing was wrong" from "nothing was looked at". In both cases the fix is
not to reason harder about the predicate; it is to obtain a SECOND signal that separates the
two readings. For an exclusion, that second signal is the mutation.

The rule is deliberately about the *mutation*, not about test coverage in general. A test that
asserts an exclusion FIRES ("a third-party abort is excluded") proves only that the excluded
case is excluded. It says nothing about the population still being graded, and it stays green
when the exclusion swallows the whole world. The mutation asks the only question that matters:
**if this carve-out applied to everything, would anything notice?**

## What it requires

1. Widening the exclusion to always-apply must turn at least one test red. Not the suite as a
   whole — a NAMED test whose failure message describes the population that stopped being
   graded.
2. The mutation and its expected red are recorded with the exclusion, in the same change.
3. A count of one is a finding, not a pass mark. One sensor means one refactor away from zero.
4. The exclusion stays VISIBLE at runtime even when it is correct — excluded, not absent
   (`network.third_party_failures_not_graded` records the count and the origins). A silent
   exclusion fails this ruling even if a mutation reds it, because the run's own reader cannot
   see what was dropped.

## The charter case, and its measurement

UX-P095 shipped a third-party-abort exclusion and reported it as the cycle's one carve-out
that went out without a sensor. UX-P096 ran the mutation rather than re-reading the code, and
the premise did not survive contact: the exclusion IS covered. Widening `isThirdParty` to
`return true` reds **15** contract tests, among them "the SAME failure unflagged is still
graded — the flag is doing the work", which is precisely the named-population sensor this
ruling asks for.

Having built the harness, it was cheap to point it at every carve-out in the module rather
than only the one under suspicion. All seven have a reddening mutation
(`frontend/e2e/mutation-census.sh`, baseline 471/471 green, 2026-08-18):

| carve-out | failing tests when widened |
|---|---|
| `isThirdParty` | 15 |
| `isNavigationCancellation` | 14 |
| `allowanceIsInstrumentInduced` | 11 |
| `isFeedRequest` | 7 |
| `aftermathIsGraded` | 6 |
| `allowanceIsIntermittent` | 3 |
| `isInstrumentInduced` | **1** |

`isInstrumentInduced` is the finding. One test is clause 3's floor, not a pass: it is the
thinnest sensor on the newest carve-out, which is the combination this ruling exists to catch.

Two things follow that are worth stating plainly. First, the census is why this ruling is
banked with evidence instead of as an aspiration — "we should mutate our exclusions" is a
sentiment, and a table of seven measured reds is a standard. Second, a cycle reported a gap
that measurement then closed. The report was written in good faith and was wrong, and the
only reason anyone knows is that somebody ran the mutation instead of re-reading the
justification. That is the entire ruling in one sentence.
