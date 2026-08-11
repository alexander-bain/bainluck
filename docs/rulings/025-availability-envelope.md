# RULING 025 — The availability envelope: substitute content must declare itself

date: 2026-08-10
author: Alex
via: Fable, ratified
issues: #1698
relates: ruling 003 (clients format, never adjudicate — this extends it)

**DO NOT REMOVE (CI-guarded).**

> Any response serving **fallback, stale, partial, or substitute** content in place of its primary
> pool MUST declare that state in the response envelope:
> **`availability ∈ {fresh, stale, degraded, empty}`**.

## The five clauses

**1. Backend declares; clients render the declared state and never infer it.**
This extends ruling 003: **rendering a state is formatting; deriving one is adjudicating.** A client
that looks at an empty array and concludes "degraded" has made a judgment call the backend was
supposed to make, and two clients will make it differently.

**2. The declaration is computed from what was SERVED, never mapped from cache-metrics vocabulary.**
The header buckets (`miss` / `hit` / `stale_hit` / `error`) are **metrics plumbing** with a different
writer and different semantics — `miss` is *fresh-but-uncached*, not `empty`. **No 1:1 mapping
exists; do not build one.** The temptation is real because the two vocabularies are the same size
and two of the words rhyme, which is exactly why this clause is written down rather than left to
judgment.

**3. Per-item exception swallows are permitted only if counted.**
Every swallow increments a served-side counter surfaced in `pool_counts.dropped`.
**A swallow that counts is detection; a swallow that doesn't is concealment.** The swallows
themselves stay — gotcha #42 exists because one bad item must not wipe a whole pass — but a pass
that silently served nine of ten items and a pass that served ten are not the same event, and until
the counter exists nothing can tell them apart.

**4. Serving a plausible substitute without declaration is a defect** regardless of how reasonable
the substitute looks (**#1698 species, Q22 census**). The plausibility is the hazard, not the
mitigation: content that looks right is precisely the substitution nobody reports.

**5. Each declared state has exactly one client rendering.** Four states, four renderings. No state
with two treatments, no two states sharing one.

## Why this is a ruling and not a queue item

Every clause above is a *general* constraint that outlives the code that occasioned it. #1698 —
anonymous `/api/feed` serving **zero futures cards against 16,861 eligible rows, reproducing every
draw** — is one instance. The instance gets fixed either way. What the instance revealed is that the
system had **no vocabulary for saying "what you are looking at is not the real thing,"** so every
substitution it made was indistinguishable from success, to the client and to us.

That is the same shape as gotcha #53 (an empty 200 is a response shape, not an absence) and gotcha
#49 (a lifetime count read as a recent one): in each, a signal that *could* mean two things was read
as the convenient one because nothing forced the distinction. This ruling forces the distinction at
the only boundary where the answer is actually known — the server that did the serving.

The acceptance test is deliberately absolute: **no code path serves substitute content without a
declared state.** Absolutes are checkable by enumeration. "Most paths declare" is not.
