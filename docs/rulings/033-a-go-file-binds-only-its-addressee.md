# RULING 033 — A GO file binds only its addressee

date: 2026-08-12
author: Alex
issues: #1621

**Every `GO-*.md` carries an `addressee:` line naming the ONE lane it instructs. A window that is
not the addressee treats the file as read-only context: it may read it, cite it, and reason from
it, but it must not execute it.**

The addressee line is mandatory in new GO files. A GO file with no `addressee:` is addressed to
nobody and instructs nobody — read it as context and, if the instruction looks live and unowned,
ask for it to be re-issued with an addressee rather than adopting it.

## Why

A GO file is an approval, and an approval is always an approval *of someone to do something*. The
old files dropped the someone, so every window that read one had to infer whether the work was
theirs — and the honest inference from an approved, unexecuted queue is "this is live work nobody
has picked up", which is precisely the reasoning that makes two lanes pick it up.

**Named failure: the integrator/triage collision on `GO-FABLE-20260812.md`.** That file is a
triage-window brief — restore Queue 333 to the slot, re-park the grooming queue as 338, execute
333 then 338, write the standing codex backlog. It says `status: approved` and it names no
addressee. An Integrator window reading it at Phase 0 sees an approved, unexecuted, in-scope-
looking instruction set sitting in the shared handoff directory, and nothing in the file says it
is not for them. Both lanes had a good-faith claim on it. Two lanes executing one queue is the
collision the entire lane-lock system exists to prevent, and the lock does not prevent this one,
because the lock protects a *worktree and the master branch* — it says nothing about who owns an
instruction.

Note the asymmetry that makes this worth a ruling rather than a convention: the lane lock fails
LOUDLY (a second claimant sees `HELD` and stops), while an unaddressed GO file fails SILENTLY —
both lanes proceed, each believing it is the only one, and the duplication surfaces later as
conflicting edits or as one lane's work mysteriously already done.

## How to apply it

1. **Writing a GO file:** the second line is `addressee: <lane>` — `integrator`, `lane1`, `ops`,
   `codex`, `ux`, `calibration`, `latency`. One lane. If two lanes genuinely need instructions,
   write two files; a GO file addressed to two lanes has reinvented the problem.
2. **Reading a GO file that is not addressed to you:** it is context. Cite it, honour rulings
   recorded inside it, and do not execute its work items — not even the ones that look unowned,
   stale, or cheap. "It looked abandoned" is the collision, not the exception to it.
3. **Standing GO files** (`GO-INTEGRATOR-STANDING.md`) carry the addressee in the name and in the
   line; they remain binding on their addressee across windows until superseded.
4. **A GO file addressed to you does not expire silently.** If you cannot execute it, say so in
   your report and leave it; do not consume it.

Sibling of ruling 015 (a hold must be written where the lane actually reads) and ruling 028 (a
hold is DECLARED, never implied by silence). All three are the same shape: an instruction's
*audience* is part of the instruction, and leaving it to inference reliably produces the wrong
number of executors — sometimes zero, sometimes two.
