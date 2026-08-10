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
3. **Exact pid match for "held by me."** `owner_pid == $$`, integer-equal. Not "looks like my
   window", not "the tree suggests I am the latency lane", not a name comparison.

## The addendum, and why it is separate

**Identity is TESTED, never narrated.** Failure 3 is not a locking bug — the lock worked fine. It
is a lane deciding *who it was* from context and then acting with that authority.

Every other guard here assumes the question "am I the owner?" has a cheap true answer. `$$` is that
answer. A window that describes itself as INT-036 has asserted something; a window whose `$$`
equals `owner_pid` has proven it. **Only the second may write.**

This is the same distinction the base-SHA check draws in ruling 020(a): the lock is a claim about
the world, the `ps`/`$$` test is the world. Prefer the world.

## Deletion is part of the ruling

Hand-rolled claim logic is **deleted**, not deprecated. A second path that still works is a second
path that still gets used — under time pressure, by the lane that does not know the primitive
exists yet. If a caller needs something the primitive does not do, extend the primitive.
