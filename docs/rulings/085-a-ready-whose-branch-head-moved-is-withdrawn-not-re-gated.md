# RULING 085 — A READY whose branch head moved is WITHDRAWN, not re-gated

date: 2026-08-18
author: Fable
issues: #1621

A `READY-*` token names a branch **and a head SHA**. That pair is the whole certificate: the
lane's gate evidence is a claim about one tree, and a tree is identified by its SHA. When the
Integrator picks the token up and finds the branch head somewhere else, the certificate has
nothing left to certify.

**The Integrator does not chase it.** It does not re-read the new head, does not re-run the
gates against it, does not diff old-head against new-head to decide whether the change "looks
safe". It posts a withdrawal notice naming both SHAs, drops the token from the ready-set, and
moves to the next item. **The lane re-issues** — a fresh token, at the new head, with gate
evidence that was actually produced on that tree.

## Why the Integrator is the wrong place to absorb this

The tempting reading is that re-gating is cheap and the Integrator is already holding the lock,
so it may as well. Three things are wrong with that.

**It is not cheap, and the cost lands on the critical path.** INT-085 lost **24 minutes** to
`program/calibration-66`: the READY named `e1a5ef44`, the lane amended to `5b00f4f8` mid-gate,
and the Integrator was gating a head that no longer existed. In the same session
`codex-adhoc/cohort-views` took **three SHAs in under an hour**. The Integrator is the single
writer to master; every minute it spends re-deriving another lane's certificate is a minute the
entire fleet's merge queue is stopped.

**It relocates authorship of the evidence.** A gate run is only worth what the runner knows about
the change. The lane knows why it amended; the Integrator sees two SHAs and a diff. An Integrator
that re-gates is manufacturing a certificate for work it did not author — and if the amend
introduced a defect, the record will say the Integrator passed it.

**It rewards the behaviour that caused it.** If moving a head silently costs the lane nothing,
heads keep moving. Making withdrawal the automatic consequence puts the cost back on the party
that can actually avoid it, which is the only party that can decide whether the amend was
necessary.

## What this is NOT

Not a judgement on the work, and not a hold. A withdrawn READY is not blocked, criticised, or
deprioritised — it is *unverified*, and the fix is one cheap action by the lane. Re-issue at the
new head and it merges in the next cycle.

Not a licence to skip the check. The Integrator must **re-verify the head against the token
immediately before merging, and again immediately before pushing** — the second read is the one
that catches a lane amending during the gate run itself, which is exactly what happened twice in
one session.

## Corollary — a READY with no `status:` line is not a READY at all

Discovered enforcing this in INT-086: `READY-lane1-367.md`, `READY-ux-81.md`, and
`READY-lane1-q353-process.md` carry no `status:` line whatsoever, so they never appear in the
`ready_for_integration` sweep. A lane that omits the line has not been deprioritised — it is
**unseen**, and it will wait forever while believing it is queued. `lane1/q367` merged in INT-086
only because a directive named it explicitly.

The head-moved case and the no-status case are the same failure wearing two hats: **the token is
the interface, and a malformed token is silence, not a quieter request.** Both resolve the same
way — the lane writes a correct token; the Integrator never guesses at intent from branch state.
