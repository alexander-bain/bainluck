# RULING 069 — The ledger is the allocator: a number is held by the first CLAIM, not the first merge

date: 2026-08-14
author: Fable
context: INT-070 directive, item 4 — issued after the second ruling-number collision in two days.

## The ruling

**A monotonic doc number is held by the lane that CLAIMED it first in
`.claude/handoff/RULING-CLAIMS.md` — not by the lane that merges first, and not by the lane that
wrote the file first.** When two lanes hold one number:

1. The **earlier claim keeps the number.**
2. The other lane **renumbers its own file** — never the incumbent's — moving the file, its
   `# RULING NNN — …` heading, and its PRODUCT-BRAIN index line together.
3. The renumber target is **MEASURED at the moment of the renumber, never quoted from a document.**

Point 3 is the new half, and it is the one that keeps being learned the expensive way.

## Why point 3 exists

A successor number written into a queue file, a report, or a directive is **stale from the instant
it is written**, because a live lane can mint past it in the minutes before anyone reads it. Two
specimens, both from the day this was ruled:

- `CODEX-QUEUE.md` carried *"lane1's q353 056 rival moves to 061."* By the time an Integrator read
  that line, **061 was claimed by `ux-65` and MERGED on master** (`f6dc46ca`, v3817), along with 062
  and 063. Re-pointing a renumber at an occupied number is the same collision it was written to fix,
  one number over.
- This very ruling's directive said q351's file *"renumbers to the next ledger-claimed free number
  (≥ 067)."* When the Integrator measured, **067 had already been claimed by `ux-69` mid-cycle.** The
  directive was correct when written and wrong when executed, inside a single session.

That is the sixth instance of the failure `RULING-CLAIMS.md`'s own header names: *the ledger is a
FLOOR, not an ORACLE.* This ruling adds the corollary: **a quoted successor number is not even a
floor — it is a snapshot of a moving quantity, and the only valid read is a fresh one.**

## The procedure this makes binding

In the SAME turn as the claim: `git fetch`; read the highest ruling file on `origin/master`; sweep
**every** local and remote ref (`git for-each-ref refs/heads refs/remotes`) for the candidate range;
read the ledger for what is held CONCURRENTLY; then append the claim, ascending and append-only.
**Read master to see what EXISTS; read the ledger to see what is HELD.** Neither alone is sufficient,
which is why both reads are required rather than recommended.

Never hard-code a successor number in a queue file, a report, or a directive. Name the *rule*
("the next free number, measured at renumber time"), never the *value*.

## What this does NOT change

The within-tree guard is already correct and already CI-visible:
`backend/tests/test_product_brain_integrity.py::test_ruling_numbers_are_unique` fails on any
duplicate `NNN` among `docs/rulings/*.md`, on every runner, and it is why master has never carried a
duplicate. **The uncovered case is structural, not a missing assertion:** a collision that lives on
two unmerged branches is invisible to a gate that can only see one tree, and the one artifact that
spans lanes — the ledger — is untracked by design, so its gate skips on CI. Adding a second
within-tree uniqueness check would be redundant and would read as coverage where there is none.
The mitigation is therefore the claim discipline above, enforced at authoring time on the lane's own
machine, plus the Integrator's Phase-0 sweep. (See `PROCESS-BATCH.md` item 3.)

## Sibling rulings

- **055** — a conflict resolution that changes a decision is a decision, and a duplicate number
  renumbers, never keep-both. 069 answers the question 055 leaves open: *which* lane moves.
- **001** — one file per ruling, which removed the shared append region. The index line is the one
  shared edit that survived, and it resolves by keep-all-sort-ascending.
