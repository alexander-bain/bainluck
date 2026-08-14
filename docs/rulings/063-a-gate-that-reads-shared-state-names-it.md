# RULING 063 — A gate that reads shared mutable state names what it read, and fails only on ambiguity that could change its verdict

date: 2026-08-14
author: Alex
issues: #1865

A local gate whose verdict depends on an **untracked file another live lane is
editing** — RED then GREEN inside one window, CI blind to both — is a
**shared-mutable-state instrument**. The fix looks like the worktree invariant
did: **structural, not procedural.**

The worktree invariant did not tell people to be careful about their working
directory. It made the target **explicit in the command** (`git -C <path>`), so
the invisible dependency became visible in the artifact itself. Apply the same
move here.

## The three requirements

**1. Parse for MEANING, not punctuation.** A shared prose ledger written by six
lanes accretes decoration — bold, backticks, bracketed provenance. A parser that
rejects a line whose meaning is unambiguous does not enforce a format; it
**manufactures failures at a steady rate**, and every one of them lands on a
lane that did not write the line.

**2. A partial parse must BURN, never VANISH.** An unreadable field may not
silently delete the fact its own line asserts. When the status token failed, the
whole line was dropped and its **number** went with it — so a claimed number read
as unclaimed and the gate accused an innocent, already-merged file. The number
and the status are independent facts.

**3. NAME THE SNAPSHOT.** Every verdict — pass **and** fail — states the path,
mtime and digest of the state it consumed. "It was green" must be a falsifiable
claim about an identified object, not about a moment. A failing gate can carry
its own provenance in the message; a passing one prints nothing, and a pass was
exactly the claim that turned out to be unfalsifiable.

## And the operational rule the three reduce to

> **A gate fails the run only when the ambiguity it found could change THIS
> run's verdict.**

Ambiguity on state the lane does not own, that changes no answer here, is
**reported and not fatal**. Without this, any lane can red every other lane's
suite with a typo in a shared untracked file, and the reddened lane cannot tell
that from a defect in its own branch.

## Named failure

2026-08-14. `backend/tests/test_product_brain_integrity.py`'s ledger gate failed
two tests in **every worktree on the machine**, naming
`docs/rulings/048-an-id-less-claim-never-absorbs.md` — a file merged into master
hours earlier and untouched by the branch under test. Cause: INT-068, holding the
master-write lock, annotated `.claude/handoff/RULING-CLAIMS.md` while merging
048/049/051, writing the status field as ``— **MERGED `a06bf5e5`** (INT-068, …) —``
against a parser that required a bare lowercase token.

INT-068 then fixed it independently, mid-run. The same gate answered **GREEN**
minutes later with **no action from the lane that had gone red**.

Both halves are the defect. Trust the first answer and you spend a window
chasing someone else's formatting. Trust only the second and you never learn the
ledger was malformed at all. **CI saw neither state** — `.claude/` is gitignored,
so the gate skips cleanly on a runner.

## What may NOT be done about it

- **Do not commit the ledger.** A tracked copy is one append region edited by
  every lane — the exact conflict class ruling 001 split `docs/rulings/` apart to
  kill.
- **Do not make it a CI gate.** It cannot be one, and its value is that it fires
  at authoring time, which is *earlier* than CI.
- **Do not delete the gate.** It catches a real and expensive class (two lanes
  writing different rulings at the same number, invisible to both until the
  second merge).

The instrument stays where it is. What changes is that it reads for meaning,
burns rather than vanishes, names its snapshot, and fails only on ambiguity it
actually needs resolved.

## Scope

Stated for gates generally, not for this one file. Any instrument reading
`.claude/handoff/**`, another worktree's tree, or any shared untracked state is
in scope. The obvious next specimen is the **GOTCHAS** series in the same ledger:
same file, same class, and it has not failed yet.
