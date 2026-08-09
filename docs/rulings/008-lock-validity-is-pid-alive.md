# RULING 008 — Lock validity is the owner pid being alive

date: 2026-08-09
author: Alex
via: Fable, ratified
issues: #1621

**DO NOT REMOVE (CI-guarded).**

> A lane lock is valid **if and only if its owner pid is alive.** `ps -p <pid>` is the whole test.
>
> **Heartbeat timestamps are ADVISORY ONLY.** A heartbeat never decides whether a lock holds. It
> may not fail the lane open, and it may not fail the lane closed, on its own.

## Named failures

- **Seven rule-1 deviations** — seven separate times a lane proceeded past a lock it should have
  respected, or respected one it should not have.
- **Ahead-drift ×2** — a heartbeat stamped in the future. `now - heartbeat` goes negative, every
  staleness comparison reads "fresh forever", and the lane **fails OPEN**: a second writer starts
  against a lock that will never look stale.
- **Behind-drift ×1** — a heartbeat stamped late or never re-stamped during a long green gate run.
  The lane **fails CLOSED**: a live, correct owner is declared abandoned and its work is taken.

## Why the timestamp had to be demoted rather than fixed

Every previous attempt tightened the *discipline* around the timestamp — stamp at each phase
boundary, read from `date` and never estimate, never future-date. The discipline is good advice
and it kept being violated anyway, in **both directions**, which is the tell: the mechanism was
asking a human-written string to carry a safety property.

A timestamp is a claim about liveness. `ps -p <pid>` is liveness. When a claim and the fact
disagree, the fact should win, and the only way to guarantee that is to stop letting the claim
decide anything.

Note the asymmetry this removes. Under a staleness rule, the two drift directions have very
different costs — behind-drift steals a live lane's work, ahead-drift admits a second writer to
master — and the rule silently picks a side depending on which way a human's clock slipped.
**Neither failure is available to a rule that never reads the clock.**

## What the heartbeat is still for

It stays, and it is still stamped. It answers *what is that pid doing and since when* — which
phase, which queue, which SHA. That is genuinely useful for a human reading the directory or for
a report reconstructing a cycle. It is diagnostics, not a gate.

## How a lane applies it

1. **Take the lock:** write `status: HELD`, your window nonce, and your real pid from
   `ps -o lstart`.
2. **Check a lock:** `ps -p <owner_pid>`. Alive → the lock holds; you are the second lane; **do
   not proceed.** Empty → the owner is gone; record the takeover and claim. **Do not consult the
   heartbeat to break the tie** — there is no tie.
3. **Release on exit,** including a BLOCKED exit. A lane that exits without releasing leaves a
   dead pid, which the rule reads correctly as free — releasing is courtesy that makes the
   directory readable, not the safety mechanism.

## The one thing this rule cannot see

A pid alive on **another machine**, or a lane whose process has hung rather than exited. Both are
out of scope today: every lane runs on the same host, and a hung owner still holds the lock,
which is the safe direction. If lanes ever run across hosts, this ruling needs a successor —
recorded here so the gap is inherited rather than rediscovered.
