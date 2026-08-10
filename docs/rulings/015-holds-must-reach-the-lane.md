# RULING 015 — A hold must be written where the lane actually reads

date: 2026-08-09
author: Alex
via: Fable, ratified
issues: #1546 · #1631

**DO NOT REMOVE (CI-guarded).**

> When the Integrator records a **HOLD** or a **mandatory-order item** against a lane's branch, it
> **MUST also write it as ITEM 0 in that lane's own staging inputs** — the lock-file candidate list
> or the queue header, whichever the lane provably reads at staging time.

## Named failure

**The C229 repair: ordered twice, skipped twice — while recorded in three places the lane does not
consult.**

It was in `INTEGRATOR-QUEUE.md`, in a board comment on #1631, and in the integrator's cycle report.
All three correct, all three current, none of them read by the UX lane when it self-stages. The
lane opened `LANE-ux.lock`, read its own ranked candidate list, saw the event-page pack at (1), and
staged that — twice, entirely reasonably. **The instruction and the reader never met.**

## Why this is the Integrator's obligation and not the lane's

The tempting fix is "lanes should check the integrator queue before staging." That is a rule
requiring a lane to remember to look somewhere it has no other reason to open, and it would fail
the same way this did — the fifth time, quietly.

**The party who knows the hold exists is the party who must deliver it.** Under CONTINUOUS LANES
the lane self-stages from its own file; that file is the delivery address. Writing the hold
anywhere else is publishing to an audience that isn't there.

The general form: **a broadcast is not a delivery.** Recording an instruction in three canonical
places proves diligence and changes nothing. What matters is whether it appears in the one file
the recipient provably opens at the moment they decide.

## Item 0, specifically

Not "mentioned in the file." **Item 0** — above the ranked candidates, before anything the lane
would weigh. A hold is not a candidate competing on merit; it is a precondition. Put it where it
cannot be ranked against alternatives, because under usage weighting a repair will lose to a
feature every time (which is ruling 014's failure in a second costume).

## The Integrator's own indictment, recorded because it is the point

This ruling exists because **I did exactly this**: recorded the `ux-23` hold in the integrator
queue, in a board comment, and in a cycle report, and considered it delivered. It was not. The
lane staged past it twice, and the second time it stacked `ux-24` on the unrepaired base — which
is how a communication failure became a merge-order hazard.

A hold that does not reach the lane is not a hold. It is a note about a hold.
