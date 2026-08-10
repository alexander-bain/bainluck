# RULING 013 — An explicit RELEASED frees a lock, regardless of pid liveness

date: 2026-08-09
author: Alex
via: Fable, ratified
issues: #1621
supersedes: nothing — AMENDS ruling 008

**DO NOT REMOVE (CI-guarded).**

> An explicit **`RELEASED`** frees a lane lock **regardless of whether the owner pid is alive.**
> **Pid-liveness governs only locks that claim `HELD`.**

## Named failure

**The cycle-39 UX window: alive but idle for four hours.** Under a literal reading of ruling 008 —
*validity is the owner pid being alive* — that lock would have held **permanently**, blocking the
lane for as long as the terminal stayed open. Nobody would have been at fault and nothing would
have moved.

## Why 008 needed this and not a rewrite

Ruling 008 replaced a clock with a fact, and that was right: a heartbeat is a *claim* about
liveness and `ps` is liveness. But it answered only one of the two questions a lock is asked.

- *"Is the owner still there?"* — `ps` answers this, and only `ps` should.
- *"Is the owner still WORKING?"* — `ps` cannot answer this at all. A live process that has
  finished, or gone idle, or is waiting on a human, is indistinguishable from one mid-merge.

008 conflated them, so the safe direction on the first question became a permanent stall on the
second. **A lane that has finished must be able to SAY so, and saying so must be believed** —
because the owner is the only party that knows.

## The two-state rule, stated so neither half can be misread

| lock says | pid | verdict |
|---|---|---|
| `RELEASED` | alive | **FREE** — the owner said it is done, and it is the authority on that |
| `RELEASED` | dead | **FREE** |
| `free` | alive | **FREE** — same as `RELEASED` (see below) |
| `free` | dead | **FREE** |
| `HELD` | alive | **HELD** — do not proceed |
| `HELD` | dead | **FREE** — abandoned; record the takeover and claim |

Only the `HELD` rows consult `ps`. That is the whole amendment.

### `status: free` with a live pid — the case LAT-P020 found undefined

Real lock files in this repo say **`status: free`**, not `RELEASED` — `LANE-ux.lock` used `free`
for its entire history. So the table as first written did not cover the most common state in the
directory, and a lane meeting `free` beside a live pid had to guess: is `free` a release, or is it
a stale default from before the owner claimed?

**Ruled: `free` carries RELEASED semantics.** It is an explicit written value, the same deliberate
act by the same authority, differing only in spelling. The lane is free.

Prefer `RELEASED` in new writes — it says *someone decided this* where `free` could be read as
*nobody set this* — but **never treat `free` as ambiguous.** An undefined case in a lock protocol
resolves to whatever the reader guesses, and half of them will guess the blocking direction, which
is the four-hour stall this ruling exists to prevent.

**A state a real file is actually in is not an edge case.** It only looked like one because the
table was written from the vocabulary of the ruling rather than from the vocabulary of the files.

## Why this does not reopen the door 008 closed

The failure 008 killed was a **timestamp** deciding a lock — a derived, drifting, silently-wrong
signal that failed open on ahead-drift and closed on behind-drift. `RELEASED` is not a derived
signal. It is a **deliberate, explicit, written act by the owner**, and the owner is the one party
with standing to make it.

The remaining exposure is a lane that releases and then keeps working. That is a lane breaking its
own word, which no lock design prevents and which is loud when it happens — categorically unlike
a clock quietly being eight minutes fast.

**Corollary: releasing is now load-bearing, not courtesy.** Ruling 008 called release "courtesy
that makes the directory legible" because a dead pid already read as free. Under 013 an
alive-but-finished lane that forgets to release **blocks its own successor**. Release on exit,
including a BLOCKED exit.
