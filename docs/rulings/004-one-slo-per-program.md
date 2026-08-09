# RULING 004 — One SLO per program

date: 2026-08-09
author: Alex
via: Fable, from the over-engineering audit
issues: #1544 · #1545 · #1546

**DO NOT REMOVE (CI-guarded).**

> Each program declares **exactly one product-visible SLO**. The Monday scoreboard reports them.
> Diagnostic rails **feed these verdicts and never publish competing ones**.

## Named failure

**The calibration incident: seven rails watching, and the published page was dark for days.**

Every rail was working. Each measured something real. Not one of them measured the only thing a
user could perceive — *is the page up and is the number current* — so seven green signals
coexisted with a dark surface, and the dark surface was found by a person.

## Why "exactly one", and why product-visible

Monitoring accretes. Each incident adds a rail, no incident removes one, and the count grows
until "all green" means nothing because no one can hold seven meanings at once. A single
product-visible SLO cannot be satisfied by internal health: it is the user's experience or it is
not the SLO.

The second clause is what stops the drift returning. Diagnostic rails are not banned — they are
demoted to **inputs**. A rail may make the SLO red; it may not publish its own competing verdict.
That is the difference between seven detectors feeding one answer and seven answers nobody
reconciles.

Related and deliberately not merged with this: *a rail is not shipped until it has been invoked
post-deploy*. That rule makes a rail real. This one makes it accountable to something a user
would notice.
