# RULING 109 — A READY token is void while its branch contains a never-merge ancestor

date: 2026-08-20
author: Fable
issues: #2002, #1621

## The ruling

**A `status: ready_for_integration` token is VOID for as long as its branch contains a
never-merge commit in its history.** Not deprioritised, not merge-later, not
merge-carefully — void. The branch re-earns ready only by being **rebuilt without the
ancestor**, and the token is rewritten at that point like any other fresh certification.

Naming a HEAD never-merge retires that head and **nothing else**. Ancestry travels. Every
branch that contains the head inherits the refusal whether or not anyone noticed it did,
because a merge takes the whole history, not the tip.

And the enforcement is not a longer list. **The containment check is COMPUTED in the
Phase-0 sweep** — the ancestry of every never-merge head is tested against every candidate
branch, every cycle, before anything is merged. A never-merge list that a human consults
is a list a human forgets.

## The hole this closes, measured

INT-092 ruled two codex heads never-merge: `codex-adhoc/prov-core` (`bf15491a`) and
`codex-adhoc/provenance-r5` (`e0319997`). Both were dropped from the ready set. Both
tokens carry `never_merge: true`. That was correct, and it was not enough.

`codex-adhoc/provenance` @ `02cd7ad8` was still advertising `status: ready_for_integration`
— and it is an **ancestor of** never-merge `provenance-r5`. Four further live ready tokens
contain it:

| branch | head | contains `02cd7ad8` |
|---|---|---|
| `codex-adhoc/provenance` | `02cd7ad8` | itself |
| `codex-adhoc/coldfeed` | `fa8021ea` | yes |
| `codex-adhoc/ingestion-audit` | `575819cb` | yes |
| `codex-adhoc/perf-r2` | `c1c83dff` | yes |
| `codex-adhoc/perf1974` | `3a0a8bb2` | yes |

`codex-adhoc/provenance-r4` (`b6745146`) contains it too and carries no token at all, so it
is invisible to the sweep from the other direction.

Note where the constraint actually lives, because this is the whole lesson: **it does not
run through either head INT-092 named.** Neither `prov-core` nor `provenance-r5` is
contained by anything. The contaminating ancestor is the one that was left marked ready.
Retiring the two visible heads removed two branches and zero risk.

## What it costs, and why "carefully" is not an option

Each of those four presents as an artifacts-only branch. Its three-dot diff against master
carries six files it never advertises, including:

```
backend/alembic/versions/add_disc_interactions_provenance.py
```

`git merge-tree --write-tree origin/master <branch>` exits **1** on all five, and the single
conflict is that migration. Production `alembic_version` is already at
`add_disc_int_provenance` — the revision **has run** and can never run again, so the edit
can never be applied. This is not a conflict to resolve; it is a branch that cannot be
merged in any form that preserves the tree.

## Why the token, and not just the branch

The token is the Integrator's work queue. A void branch with a green token is worse than a
branch with no token: it consumes a review slot, it reads as certified, and its certification
is *true about the diff and false about the history*. The tokens for all five are marked void
**with the reason written in the file**, so the next reader learns the shape rather than
re-deriving it.

This is ruling 017 one level up. There, gates prove something about the commit you tested,
not the commit you push. Here, a token proves something about a diff, and the thing being
merged is a **branch** — which is its entire history, including the part nobody read.

## Obligations

1. A never-merge designation names a head; its **closure** is every branch containing that
   head, and the closure is computed, never remembered.
2. A ready token over a branch inside that closure is **void on discovery**, and marked void
   in the file with the reason and the offending ancestor named.
3. Void is not a hold. The branch does not wait for the closure to lift — it is **rebuilt
   without the ancestor** or it never merges.
4. Phase 0 runs the containment check before any merge decision, and reports it. An unchecked
   cycle reports the check as UNRUN, never as clean — an absent comparison is not evidence of
   health (gotcha #53).

## The check is a set intersection, not an ancestry test

Worth stating, because the first implementation of it in this very cycle got it wrong and
the live run is what caught it.

`is-ancestor(never_merge_head, candidate)` asks whether the candidate is **downstream** of
the retired head. Run against the real bus it returned **clean for all five contaminated
branches** — because the poison is not `provenance-r5`, it is `02cd7ad8` sitting *upstream*
of four branches that never touched `provenance-r5` at all.

Reversing it does not work either. `origin/master` is an ancestor of `provenance-r5`, so
"is an ancestor of a never-merge head" marks the entire repository void.

What is actually forbidden is the never-merge lineage **minus what is already shipped**:

```
closure   = git rev-list origin/master..<never-merge head>   (union over all heads)
VOID      ⟺  git rev-list origin/master..<candidate>  ∩  closure  ≠  ∅
```

Master's commits fall out by construction. On the bus at INT-094 the closure is 6 commits;
the five void branches each share exactly `02cd7ad8` and `ccce417f`, and the report names
those SHAs so the finding can be checked rather than believed.

Implemented as `scripts/sweep_ready_tokens.py`. Computed, not remembered.
