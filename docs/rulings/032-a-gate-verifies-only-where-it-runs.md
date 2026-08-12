# RULING 032 — A gate verifies only where it runs: a branch is evidence, master is verification

date: 2026-08-11
author: Alex
issues: #1643, #1544

**A gate existing on a branch is evidence. A gate running on master is verification.** An exam item,
an acceptance criterion, or any other claim that rests on automation goes green when that automation
has EXECUTED on a merged master head — and the proof is the master CI run ID, quoted where the claim
is made.

Issued on CAL-P043, which repaired the calibration cross-surface parity gate and correctly declined
to mark `docs/CALIBRATION-EXIT-EXAM.md` item 5 green while the repair sat on `program/calibration-40`.
That restraint was right, and this ruling is the bar it was reaching for, written down so the next
lane does not have to re-derive it: item 5 goes green when a master run of
`calibrationSurfaceParity` exists, and the run ID goes in the item.

## The WHY

The failure this prevents is not a gate that is *wrong*. It is a gate that is *absent from the thing
everyone else builds on*, while a document says the thing it checks is checked.

Three ways a branch-only gate silently fails to be a gate, all of them ordinary:

1. **It never merges.** The branch is bounced, superseded, or quietly abandoned. The claim it backed
   stays green on the scoreboard, sourced to a test that exists in no tree anybody runs.
2. **It merges but does not run.** A workflow path filter, a test-plan omission, a jest
   `testPathIgnorePatterns`, a `node --test` glob that never reaches a new directory — the file is on
   master and executes nowhere. Compiling is not running; being present is not being invoked.
3. **It merges, runs, and fails on the integrated base.** Gates prove something about the tree they
   ran on. A branch's green was measured against its own base, and other lanes have landed since.
   This is the same fact ruling 020 encodes for pushes and gotcha #47 for commits, applied to
   claims: *the tree you tested is not automatically the tree you shipped.*

What makes this worth a ruling rather than a habit is #1643 itself. The vacuous parity test **was**
on master, **did** run, and **was** green for weeks — while comparing a fixture to constants sitting
beside it in the same file. A gate that runs and proves nothing is the expensive failure; a gate that
proves something but has not run yet is the cheap one. Both are cured by the same discipline —
demand the execution, then demand it on the base that ships — and a lane that has just been burned by
the first should not be granted the second on trust.

## What this does NOT say

- It does not require production deployment. Executing on a merged master head is the bar. A
  user-visible claim may separately need production proof (the standing proof-not-code rule); that is
  a different requirement, not this one.
- It does not devalue branch gates. Running gates on a branch is how a queue certifies, and CAL-P043's
  branch evidence — 86 native tests executed, 417 contract tests, ten mutations killed — is exactly
  what a lane owes. The ruling governs when a CLAIM flips to green, not when work is done.
- It does not make rendered or photographic evidence worthless. CAL-P026's side-by-side renders stay
  in the exam as evidence. What they cannot be is the *guard*: a proof that needs a person to look at
  it gets looked at once.

## How to satisfy it

Quote the run: `https://github.com/alexander-bain/bainluck/actions/runs/<id>`, on a master commit,
with the gate's name visible in that run's job output. One line, next to the claim it makes green.
