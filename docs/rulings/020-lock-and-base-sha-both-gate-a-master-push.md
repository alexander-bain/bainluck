# RULING 020 — A master push needs BOTH the lock and base-SHA equality; a HELD lock never yields to a claim

date: 2026-08-10
author: Alex
via: Fable, ratified
issues: #1621
amends: ruling 017 (does not supersede it — 017 stands and this completes it)

**DO NOT REMOVE (CI-guarded).**

> **(a) Pushing master requires TWO things, not one: you hold `LANE-integrator.lock`, AND
> `origin/master` is still the exact SHA your gates ran against.**
>
> **(b) Claiming a lock whose status is `HELD` by a LIVE pid must FAIL. Never overwrite it.**

## Named failure

**Queue 309 overwrote INT-033's held claim.**

INT-033 held the lock and spent ~15 minutes running gates against `3ae6db4f`. Inside that window
Queue 309 took the lock, pushed `d9c526ad`, and released — INT-033's `HELD` claim was overwritten
while it was still true.

What refused the bad push was **not the lock**. It was the pre-push `git fetch` and the question
"is `origin/master` still the SHA I gated against?" Had INT-033 trusted the lock alone, it would
have pushed a tree it never tested, and git would have fast-forwarded it cleanly — because git
cannot know the gates ran on a different base.

## (a) Why the lock is necessary and NOT sufficient

Ruling 017 closed "is anyone else writing master right now?" That is a question about **sequence**,
and the lock answers it well.

It does not answer the other question: **"is the tree I tested the tree I am about to ship?"** Those
come apart the moment anything lands between your gate run and your push — which is precisely what
a long gate run invites. 017's own closing line already said it: *the gates prove something about
the commit you tested, not about the commit you push.* It named the gap and then guarded only one
side of it.

So both checks, every push, and they are not redundant:

| Check | Protects | Fails when |
|---|---|---|
| lock held by me | the **sequence** — one writer at a time | another lane is mid-push |
| `origin/master` == my gated base | the **gates** — tested tree == shipped tree | the base moved under me |

A green gate run against a stale base is the more dangerous of the two failures, because it looks
exactly like a good one. **If the base moved: rebase and re-gate. Never push on the old evidence.**

## (b) Why a claim must fail rather than overwrite

The lock file was a *declaration*, not a *mutex*. Any writer could set `status: HELD` with its own
pid over a claim that was still valid, and nothing in the write path so much as read the previous
value.

That is not a discipline problem. A protocol whose only protection is "everyone remembers to look
first" has no protection, and Queue 309 was obeying ruling 017 correctly when it did this — it was
told to take the lock, so it took it. The rule told it to acquire and never told it acquisition
could be refused.

**Claiming is now a test, not an assignment**, and it composes with the state table ruling 013
already established:

```
read the lock:
  status HELD + owner pid ALIVE + not me  -> REFUSE. You are the second writer. Stop and say so.
  status HELD + owner pid DEAD            -> FREE. Record the takeover, then claim.
  status RELEASED / free (any pid)        -> FREE. Claim.
```

Only the first row changes: it used to be advice and is now a refusal.

Note what this does NOT do: it does not make the lock sufficient. Even a correctly refused-when-held
lock would not have caught the base moving, because the base can move via a lane that pushed before
you claimed. (a) and (b) guard different failures and neither substitutes for the other.

## Why this ordering, for whoever writes the enforcement

Check the lock BEFORE gating (cheap, and it stops you wasting a gate run), and check base-SHA
equality IMMEDIATELY before pushing (that is the only moment its answer is still true). Re-read the
lock at that moment too — that is when INT-033 discovered it had been overwritten.

## What it costs

Nothing in the common case. An uncontended claim reads a `RELEASED` file and proceeds, exactly as
before. The cost lands only where it should: on the second writer, who now stops instead of
silently winning.
