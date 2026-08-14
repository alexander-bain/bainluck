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
