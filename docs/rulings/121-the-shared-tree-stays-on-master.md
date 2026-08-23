# RULING 121 — The shared tree stays on master; branch work lives in worktrees

date: 2026-08-14
author: Alex
issues: #1575

`~/bainluck` is checked out on `master`. Always. It is not a workspace — it is the reference tree
every lane reads, and its branch is part of the contract.

Three places, and nothing else:

- **`~/bainluck`** — always on `master`. Reads, greps, censuses, `.claude/handoff/` writes. Never a
  lane branch, never a commit that belongs to a queue.
- **Per-queue worktrees** — `.claude/worktrees/<name>` or `/tmp/<queue>`. ALL branch work. One
  worktree per queue, created off `origin/master`, removed when the queue is done.
- **The Integrator's dedicated detached worktree** — `/private/tmp/int067-master` is adopted as the
  standard shape. **All master-writes happen there**, in a tree that exists for nothing else, held
  under `LANE-integrator.lock` (ruling 017).

## Two mirror incidents, both on 2026-08-14, both in the same tree, minutes apart

They are worth stating as a pair, because between them they cover the entire failure surface — a
lane branch's work landing on master, and a master-write landing on a lane branch.

**A — branch work committed onto master.** Queue 352's `#1801-R5` implementation, 11 files and
~650 lines, was written in `~/bainluck` while it sat on `master`, and committed there as
`f23cd218`. It was then rescued by pointing `lane1/q352` at the commit and `reset`-ing master back
to `origin/master`. It worked. It worked because the commit already existed when the reset ran —
had the reset come first, this is #1575 again, and #1575 is the incident where nine files of
unstaged work were destroyed with no recovery. The margin here was ordering, not design.

**B — a master-write committed onto a lane branch.** The `program/calibration-50` merge was
performed while the same tree was checked out on `lane1/q352`, producing `4852f46c`. That commit is
contained in **no branch** — it is reachable only from the reflog. The merge was redone correctly as
`d59c9374`. Nothing was lost, and nothing said anything either: an orphaned merge commit is
invisible until someone goes looking for why the work is not on master.

A is the dangerous one and B is the loud one, and the same tree produced both inside one window.

## The amendment: `-C` pins the DIRECTORY, not the BRANCH

Gotcha #51 has been amended twice, each time widening *which verbs* need `git -C <path>`. Both of
today's incidents would have satisfied it completely. `-C ~/bainluck` was the correct directory
both times. The tree was simply on the wrong branch.

So `-C` answers *where am I writing*, and has never answered *what am I writing onto*. It cannot:
a path does not carry a ref. The discipline that closes the second question is not a flag on the
command — it is the invariant that a given tree is only ever on one branch, so the tree you name
determines the ref you get. That is the whole reason `~/bainluck` is pinned to `master` and
master-writes are exiled to a tree that holds nothing else.

**Before any `commit`, `merge`, or `reset` in a shared tree, the branch is part of what you check —
not just the path.** `git -C <path> rev-parse --abbrev-ref HEAD` is one call and it is the call
neither incident made.
