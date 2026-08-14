# RULING 046 — A stacked change is measured on its OWN deploy

date: 2026-08-13
author: Alex
issues: #993, #1836, #1839

When a lane stacks branch `N+1` on an unmerged branch `N`, and a **prediction has
been ratified about `N`**, the Integrator merges and deploys **`N` alone**, the
owed read is taken against that deploy, and only then does `N+1` land — followed
by its own read.

This is a standing instruction to the Integrator, not a per-cycle request.

## WHY

**An ungradable measurement is a lost one.** Not delayed — lost. There is no
second chance to observe the intermediate state, because once both changes are on
`master` the world in which only one of them shipped no longer exists and cannot
be reconstructed.

The cost asymmetry is the whole argument. Merging `N` alone costs one extra deploy
cycle and one extra read — both cheap, both routine. Merging `N` and `N+1`
together saves that, and permanently destroys the attribution of every number the
program was pointed at. A ratified prediction that can never be graded is worse
than no prediction, because the discipline of pre-registering one was paid for and
then thrown away.

## The specimen

`program/latency-41` carried the search **scorer** (a ranking change, ruling 041).
`program/latency-42` carried the **pool fix** (a recall change) and was stacked on
top of it, so merging `-42` necessarily merged `-41` first. The ratified `+11±1`
prediction on `entity_top_1` was a claim about **the scorer alone**.

Sequenced per this ruling, `-41` merged as `1d98daff`, deployed alone in v3800, and
the read returned **32/44 against a 30/44 baseline** — a **miss** of the 39–41 band.
Because the deploy was clean, that miss was *diagnosable*: the probe-level diff
showed **+7 gained, −5 lost**, and the five losses turned out to be a dedup bug the
scorer had exposed rather than caused (#1839). A fix, 15 tests and 6 killed
mutations followed within the hour.

Had both branches landed together, the observable would have been a single net
number with two changes behind it. The +7 and the −5 would have cancelled into
noise, the dedup bug would have stayed invisible, and the honest report would have
been "we cannot say".

## First confirmed instance — the miss was worth more than the hit

**Recorded by Alex, 2026-08-13, on the LAT-P047 acceptance.** The ruling's payoff
arrived inside the same session that banked it, and it is the week's best proof
of method.

Had `-41` and `-42` shipped together, the observable would have been a single,
tidy **30 → 35**. That reads as a clean win. It would have been reported as one,
nobody would have looked further, and **#1839 would have stayed hidden** —
indefinitely, because there is no second chance to observe the intermediate
state and no reason to go looking inside a number that already met expectations.

What the sequenced deploys produced instead was a *decomposed* miss:

| component | value | what it actually was |
|---|---|---|
| gained | **+7** | the predicted victory — the Emmys false positives and the fragment wins, both dead |
| lost | **−5** | an undiagnosed regression nobody predicted |
| cause | — | first-writer-wins dedup killing the rankable twin (#1839) |

The `+7` and the `−5` would have cancelled into a plausible net. Separated, the
`−5` was diagnosable within the hour, and the fix carried 15 tests and 6 killed
mutations.

So the ruling's value is not that it protects good news. **It is that a miss
carries strictly more information than a hit, and only a clean deploy lets you
collect it.** A hit tells you the number moved as expected; a miss with
attribution tells you *which* mechanism moved it, by how much, and in which
direction — including the mechanisms nobody predicted.

> **The miss was worth more than the hit.**

Note also what this instance says about the *pre-registration*, not just the
sequencing: the `+11±1` band was wrong by 7, and the discipline still paid.
Being wrong loudly, on the record, against a fixed instrument, is what made the
decomposition worth reading. A prediction is an instrument for noticing
surprise, and it does that job whether or not it holds.

## What it does NOT mean

It does not mean a lane waits. Lanes stack freely and continue working — that is
ruling-invariant 2 as amended 2026-08-07. This governs only the **order and
grouping of merges**, and only when a ratified prediction is attached to a lower
branch in the stack.

Nor does it require the prediction to be *right*. The `-41` read missed its band by
7. A miss below the band **is a result** and is reported as one; the ruling exists
so that a miss can be told apart from a mixture.

## The rule

> A number is owed to the change that caused it. Merge the stack one deploy at a
> time whenever a prediction is attached to a branch below the top, and take the
> read before the next one lands.
