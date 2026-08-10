# RULING 022 — One shared lock-claim primitive; hand-rolled claim logic is deleted

date: 2026-08-10
author: Alex
via: Fable, ratified
issues: #1621
completes: ruling 020(b) — 020 said a claim must FAIL against a live holder; this says there is
  exactly ONE piece of code allowed to decide that, and every lane calls it

**DO NOT REMOVE (CI-guarded).**

> **A single shared lock-claim primitive: READ → `ps` → WRITE, as one guarded step. Every lane and
> the Integrator consume it. All hand-rolled claim logic is DELETED.**
>
> **Addendum: "held by me" requires `owner_pid == $$`, an EXACT match. Identity is TESTED, never
> narrated.**

## Named failures

**1. Queue 309 overwrote INT-033's held claim.** Mid-gate-run, in good faith, obeying ruling 017's
instruction to take the lock. Nothing told it that taking could be refused.

**2. INT-035's regex-claim near-miss — and it was written by the author of 020(b), hours later.**
Its Phase-0 claim script pattern-matched `^status: RELEASED` and appended a `HELD` log line without
ever reading the current value. The lock was `HELD` by a live Queue 310. The authoritative
`status:`/`pid:` fields survived **only because the pattern found no RELEASED line to replace** — a
different file layout and it would have been Queue 309 all over again.

**3. A fresh latency window self-identified as INT-036 from ambient tree state.** It had not
claimed anything. It inferred an identity from what the working tree looked like, then proceeded as
that identity.

## Why 020(b) was not enough

020(b) stated the rule correctly and left every lane to implement it. Three independent
implementations, three different failure modes, within two days. The rule was never the problem.

**A rule that must be re-implemented per caller is re-derived per caller, and one of them will get
it wrong.** Failure 2 proves this at the limit: even perfect knowledge of the rule does not survive
a hurried re-implementation, because the mistake is not in the understanding, it is in the code
written at 2am to do a thing that felt mechanical.

So the correction is not more emphasis. It is removing the opportunity: one implementation,
consumed everywhere, and no second path to a claim.

## What the primitive must do

```
claim(lock_path, me_pid):
    READ   the current status and owner_pid           # never assume, never regex-past
    TEST   status == HELD and ps(owner_pid) and owner_pid != me_pid  -> REFUSE
    WRITE  only after the test passes, as the same guarded step
```

Three properties, each earned by one of the failures above:

1. **Read before write, always.** A substitution is not a test (failure 2). A regex that does not
   match is indistinguishable from a lock that is free, and both silently proceed to the write.
2. **`ps` decides, per ruling 008.** Not the heartbeat, which drifted in both directions.
3. **Exact pid match for "held by me."** Integer-equal against the SESSION pid. Not "looks like my
   window", not "the tree suggests I am the latency lane", not a name comparison.

   ⚠️ **CORRECTION, 2026-08-10, same day: this clause first said `owner_pid == $$`. That is WRONG
   for a Claude Code window and would never have matched.** Every Bash tool call runs in a **fresh
   subshell**, so `$$` is a different number on every invocation and never equals the long-lived
   session process. A lane testing `owner_pid == $$` can neither confirm nor refute its own
   identity — it would refuse its own valid lock and then "recover" by overwriting it, turning the
   guard into precisely the failure it exists to prevent.

   **Resolve identity by walking `ppid` up to the `native/claude` ancestor** — that process outlives
   every subshell and is the thing a lock owner actually IS. Implemented as `session_pid()` in the
   primitive.

   Caught by the LAT-P026 window reviewing this ruling, which is the review working. Recorded rather
   than quietly patched, because the failure mode is instructive: **a spec written in shell shorthand
   smuggled in an assumption about process lifetime that was false for every caller it governs.**
   The rule was right; the expression of it was not executable.

## The addendum, and why it is separate

**Identity is TESTED, never narrated.** Failure 3 is not a locking bug — the lock worked fine. It
is a lane deciding *who it was* from context and then acting with that authority.

Every other guard here assumes the question "am I the owner?" has a cheap true answer. `$$` is that
answer. A window that describes itself as INT-036 has asserted something; a window whose `$$`
equals `owner_pid` has proven it. **Only the second may write.**

This is the same distinction the base-SHA check draws in ruling 020(a): the lock is a claim about
the world, the `ps`/`$$` test is the world. Prefer the world.

## The primitive — `scripts/claim_lane_lock.py` (INT-037, 2026-08-10)

```
python3 scripts/claim_lane_lock.py check   .claude/handoff/LANE-<lane>.lock
python3 scripts/claim_lane_lock.py claim   .claude/handoff/LANE-<lane>.lock --queue "INT-0NN"
python3 scripts/claim_lane_lock.py release .claude/handoff/LANE-<lane>.lock
```

Exit `0` acquired/released/free · `1` **REFUSED** (held by a live other) · `2` malformed lock.
**A refusal is a normal outcome, not an error to retry past.**

It encodes every state the rulings define, and each row is exercised by a test:

| lock state | outcome | ruling |
|---|---|---|
| `RELEASED` / `free`, any pid | claimable | 013 (+ extension) |
| `HELD`, owner pid **dead** | claimable, takeover recorded | 008 |
| `HELD`, owner pid **alive**, not me | **REFUSED, exit 1** | 020(b) |
| `HELD`, owner is me | re-claim allowed | 022 addendum |
| malformed | exit 2, **no write** | this ruling |

The last row matters as much as the third: INT-035's regex failed to match and *proceeded to write
anyway*, so "I could not understand this lock" must be a refusal, never a fall-through.

## Deletion is part of the ruling

Hand-rolled claim logic is **deleted**, not deprecated. A second path that still works is a second
path that still gets used — under time pressure, by the lane that does not know the primitive
exists yet. If a caller needs something the primitive does not do, extend the primitive.
