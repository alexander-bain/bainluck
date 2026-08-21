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

## ⚠️ AMENDED BY RULING 013 (same day) — `RELEASED` frees a lock regardless of pid

Read as written, this ruling answers only *"is the owner still there?"*. It cannot answer *"is the
owner still WORKING?"* — a live process that has finished, or gone idle, or is waiting on a human
is indistinguishable from one mid-merge. The cycle-39 UX window sat **alive but idle for four
hours**, and under a literal reading of the rule above its lock would have held **permanently**.

Ruling 013 adds the missing state: **an explicit `RELEASED` frees the lock regardless of pid
liveness; `ps` governs only locks claiming `HELD`.**

| lock says | pid | verdict |
|---|---|---|
| `RELEASED` | alive | FREE |
| `RELEASED` | dead | FREE |
| `HELD` | alive | HELD — do not proceed |
| `HELD` | dead | FREE — abandoned, record the takeover |

This does not reopen what 008 closed: the thing 008 killed was a *derived, drifting* signal (a
timestamp). `RELEASED` is a deliberate written act by the only party with standing to make it.
**Consequence: releasing is now load-bearing, not courtesy** — step 3 above calls it courtesy on
the grounds that a dead pid already reads as free. Under 013 that is no longer sufficient: an
alive-but-finished lane that forgets to release blocks its own successor.

## ⚠️ AMENDED 2026-08-21 (Fable, via INT-108) — a takeover needs a dead pid **AND** stale activity

> **Takeover requires `owner_pid` DEAD *and* the lock's heartbeat/activity stale beyond its own
> interval. A dead pid with FRESH activity is `MALFORMED-INVESTIGATE`, never a takeover.**

### Why the pid alone stopped being enough

`ps -p <pid>` is a perfect test of *whether that pid is alive*. It is not a test of whether the
lock names the **right** pid. `owner_pid` is a hand-written field in a text file — unvalidated
input — and the rule above reads it as though it were a measurement.

**The charter case, found 2026-08-21:** `LANE-lane1.lock` sat at `status: HELD` with
`owner_pid: 38410`, a pid that was dead. Lane1 was *alive and shipping* — queue 389 landed two
commits during the very window that read the file. Applied literally, this ruling says: dead pid,
therefore FREE, therefore take the lane. The correct answer was to take nothing and go find out
why a live lane's lock named a dead process. Three stale nonce lines and an `owner_identity` left
over from q386 were sitting in the same file, which is what a stale pid usually travels with.

The failure this closes is not the mirror of the ones 008 closed. Those were about a *signal that
drifts*. This is about a *field that lies* — and the discipline fix ("keep `owner_pid` accurate")
is the same discipline fix that failed twice already in this ruling's own history.

### This does NOT restore the timestamp as an oracle — it is a VETO, never a grant

008's core holding stands untouched: **a heartbeat may never, on its own, make a lock takeable.**
The amendment only lets it *refuse*. Read the two drift directions against the new rule:

| drift | what it does to the clock | verdict under this amendment |
|---|---|---|
| **ahead-drift** (future stamp) | staleness reads "fresh forever" | **refuses** the takeover → fails CLOSED. The 008 failure was that this admitted a second writer to master; as a veto it can only block one. |
| **behind-drift** (stamp not refreshed during a long gate run) | staleness reads "abandoned" | **never consulted** — the pid is alive, so the pid test has already said HELD and stopped. |

Neither drift direction can admit a second writer, which was 008's whole purpose. The clock is now
strictly a second lock on the same door: both keys turn, or nobody enters.

### The updated table

| lock says | pid | activity | verdict |
|---|---|---|---|
| `RELEASED` / `free` | any | any | FREE (ruling 013) |
| `HELD` | alive | any | HELD — you are the second lane, do not proceed |
| `HELD` | dead | **stale** beyond its own interval | FREE — abandoned, record the takeover |
| `HELD` | dead | **fresh** | 🔴 **MALFORMED-INVESTIGATE** — take nothing, say so loudly |

"Its own interval" means the interval that lock's lane actually stamps at, not a global constant —
a lane heartbeating every 10 minutes is stale at 30, a lane running a 40-minute gate is not.
State the interval in the heartbeat so the reader is not guessing.

### MALFORMED must be loud, not quiet

Per ruling 071 a malformed lock reads as HELD, so the safe direction is already the default. The
requirement here is the *noise*: a lane that finds one says so in its report and does not silently
route around it. This is the same family as ruling 115's status-less READY token — a field that
fails to parse is not a quieter request, it is silence, and silence gets waited on forever.

### Enforcement

1. **Every lock re-stamps `owner_pid` at each heartbeat.** A pid written once at claim and never
   refreshed is exactly the unvalidated field this amendment distrusts. Re-stamping makes the
   heartbeat and the lock cross-checkable: if they disagree, that is MALFORMED too.
2. **The sweep flags dead-pid-fresh-heartbeat locks as MALFORMED**, by name, rather than reporting
   them FREE.
3. 🔴 **A live defect in the primitive, found while banking this:**
   `scripts/claim_lane_lock.py claim` rewrites `status`, `owner_identity` and `owner_pid` but
   leaves **`nonce`, `owner_started` and `claimed_at`** carrying the *previous* owner's values.
   `owner_started` is the only defence against a **recycled pid** — the strong identity check is
   `ps -o lstart` against it — so after a takeover the file pairs a live pid with a dead process's
   start time, and a successor doing that check is entitled to declare MALFORMED and take a live
   lane. A partial re-stamp manufactures the exact condition this amendment is about. Ruling 022
   made this the single implementation, so it is one fix in one place.

## The one thing this rule cannot see

A pid alive on **another machine**, or a lane whose process has hung rather than exited. Both are
out of scope today: every lane runs on the same host, and a hung owner still holds the lock,
which is the safe direction. If lanes ever run across hosts, this ruling needs a successor —
recorded here so the gap is inherited rather than rediscovered.
