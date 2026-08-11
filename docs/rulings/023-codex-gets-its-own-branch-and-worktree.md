# RULING 023 — Codex gets a dedicated branch and worktree; shared-tree passengers become unrepresentable

date: 2026-08-10
author: Alex
via: Fable, ratified
issues: #1621

**DO NOT REMOVE (CI-guarded).**

> **Codex works on a dedicated branch in its own worktree. It never commits into the shared master
> tree. A passenger commit stops being something the Integrator has to catch, because it stops
> being something that can exist.**

## Named failure — a pattern, not an accident

**Four codex passenger commits in two Integrator cycles**, all in `~/bainluck`, all riding local
`master` ahead of `origin/master` where the Integrator was working:

| commit | when | caught by |
|---|---|---|
| `780a7a5e` | before INT-034's commit | `git log origin/master..HEAD` |
| `02fd07a4` | **during INT-034's rebase** | the rebase itself — it is what produced the "unstaged changes" error |
| `bc564cb0` | before INT-035's push | `git log origin/master..HEAD` |
| (one more, consumed) | INT-035 | — |

Every one was disjoint, every one was preserved under a `preserve/*` branch, and **none was pushed**
— because codex's own queue says `push: never`. So the catching worked. That is exactly why this is
a ruling and not an incident report: **the defence worked four times and it should not have had to
work once.**

`02fd07a4` is the one that settles it. It landed *inside* another lane's rebase. The Integrator's
protections are `git log origin/master..HEAD` at Phase 0 and the base-SHA check at push — both are
point-in-time reads, and a commit that appears between them is caught by neither by design. It was
caught by the rebase erroring, which is luck wearing the costume of a control.

## Why isolation rather than more discipline

The alternative is asking codex to remember not to commit in the shared tree. That is the same
shape as the lock-claim problem (ruling 022): a rule re-applied by hand, per occasion, by whoever
is working late.

**Codex is a cross-cutting audit/eval service and never a pusher.** Nothing about its role requires
it to be in the tree the Integrator pushes from. Give it its own worktree and its work becomes:

* **impossible to ride a push** — different branch, so `origin/master..HEAD` in the master tree
  cannot contain it;
* **impossible to interrupt a rebase** — different working directory, so it cannot dirty a tree
  another lane is mid-operation on;
* **still fully reviewable and mergeable** — via the normal ready-queue path, like every other lane.

The Integrator stops spending a Phase-0 step on it, and `preserve/*` branches stop accumulating as
the residue of a structural problem.

## What changes

1. **Codex runs in its own worktree on its own branch.**

   ⚠️ **AMENDED 2026-08-10 (INT-039) — the location in the original text was wrong and is now
   corrected.** This clause first said "under the `~/bainluck-dev/` container like the program
   slots". That container turned out to be **unreachable**: a Codex session's sandbox cannot write
   `~/bainluck-dev/`, and the Integrator cannot create the directory either (`Operation not
   permitted`, retested across two cycles). INT-038 shipped the branch half of this ruling and had
   to leave the worktree half undone for exactly that reason.

   **The canonical location is `~/bainluck/.claude/worktrees/codex`, on branch `codex/main`** —
   inside the repo, which every lane can write. It exists and is live.

   Recorded as an amendment rather than a silent edit because the wrong path was *quoted from this
   file* into `CODEX-LANE.md`, into an Integrator handoff, and into a one-command ask to Alex that
   could never have worked. A location is the load-bearing part of an isolation ruling: the
   principle survived, but for one cycle the ruling was unexecutable, and anyone reading the
   original text would have reproduced the same dead end.
2. **`AGENTS.md` updated** — the codex session-start protocol names the worktree, and the "never
   commit in `~/bainluck`" rule is stated where a codex session actually reads it.
3. **The review queue updated** — codex work reaches master through the ready-set, reviewed, not by
   being adjacent to somebody else's push.
4. **Existing `preserve/codex-*` branches** are dispositioned (merge or drop) rather than left as
   permanent parking.

## The general form, worth keeping

**When a defence has to work repeatedly against the same class of event, fix the thing that
generates the events.** Four catches in two days is not a well-guarded system; it is a system
telling you where its structural fault is, in the only language it has.
