# RULING 017 — Any session that pushes master holds the integrator lock

date: 2026-08-10
author: Alex
via: Fable, ratified
issues: #1621
supersedes: nothing — COMPLETES the single-writer invariant

**DO NOT REMOVE (CI-guarded).**

> **ANY session pushing master must hold `LANE-integrator.lock` — `/triage` included.**
>
> The lock is not the Integrator's private bookkeeping. It is the master-write lock, and holding
> it is what makes you the writer, whoever you are.

## Named failure

**`a75c8870` was pushed to master mid-INT-031, with no lock held.**

A legacy `/triage` lane did it, entirely in good faith: its own command file has always said
"execute the approved queue through push/deploy". Nothing warned it, and nothing warned me — I
found out by fetching and seeing a commit I had not written.

## Why the invariant was incomplete, not merely violated

The 2026-08-09 ruling says *"exactly ONE integrator session; only it pushes master."* Everything
built to enforce it — the lock, the heartbeat, the pid test — was scoped to **the lane called
integrator**. So the enforcement asked *"are you the second Integrator?"* when the question that
matters is *"is anyone else writing master right now?"*

A legacy lane pushing was invisible to all of it, because it never claimed to be an integrator and
never read the file.

**A lock named after a role protects the role. A lock named after the resource protects the
resource.** This one guards `master`, so anything that writes `master` takes it.

## What this costs the other lanes — deliberately little

It is not "only the Integrator may push." It is "whoever pushes, holds the lock while pushing."
A `/triage` lane finishing a queue takes the lock, pushes, releases. Ruling 013 makes that cheap:
an explicit `RELEASED` frees it immediately, no waiting on a pid.

The rule is deliberately about the ACT, not the identity — identity is what let this through.

## Why it was harmless this time, and why that is not reassurance

`a75c8870` collided with nothing; my branch rebased cleanly and CI stayed green. That is luck, not
design. Had it landed between my gate run and my push, I would have pushed a tree I never tested
— and the push would have fast-forwarded cleanly, because git cannot know that my gates ran
against a different base. **The gates prove something about the commit you tested, not about the
commit you push**, and only the lock closes that gap.
