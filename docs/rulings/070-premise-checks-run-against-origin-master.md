# RULING 070 — Premise-checks run against origin/master, never your own base

date: 2026-08-15
author: Alex
issues: #1884, #1887, #1888
context: issued on the queue-357 acceptance, ratifying all three of its premise corrections.

## The ruling

**A queue's premise is a claim about the WORLD. Verify it against a freshly-fetched
`origin/master` — never against the tree you happen to be standing on.**

`git fetch` in the same turn as the check, then read the premise off `origin/master`
(`git show origin/master:<path>`, `git ls-tree origin/master`, `git log origin/master`). Your
working base is a *snapshot of master from whenever you cut it*, and every hour it ages it becomes
a more confident liar.

This binds every premise gate: the Process-v3 gate on a chain-promoted queue, ruling 068's
re-anchor of a premise-waiting item, a codex certification's bound, and any report line of the form
"X does not exist" or "Y never landed".

## Why — the failure is DIRECTIONAL, and that is what makes it dangerous

A stale base does not produce random errors. It produces **one specific error, every time: work
that has landed reads as missing.** Never the reverse. So the false report is always
`PREMISE-BROKEN` / `not found` / `still owed` — and every one of those has a well-worn response
that consumes real effort: re-do the work, re-file the issue, escalate the block, hold the row.

**Named failure, same window as this ruling.** A calibration lane reported that the rulings
directory *"stops at 047."* True of its base. False of `origin/master`, which carried **069** —
twenty-two rulings, including four that had merged in the preceding two days. Nothing in that lane
was wrong except where it looked. Had it acted on the reading it would have claimed an occupied
number, which is exactly the collision ruling 069 exists to prevent — reached from the other end.

The 357 window found three more of the same shape and corrected all three by re-reading master.
That is the acceptance this ruling ratifies.

## Why the obvious defence does not work

*"I'll just rebase first"* is not equivalent, for two reasons:

1. **Rebasing is a write.** It changes patch-ids, and a conflict resolved during it detaches the
   commit's identity permanently — the failure `git cherry` keeps re-reporting as new work
   (ruling 001's whole subject). A read should never require a write.
2. **Rebasing to fix a red gate is separately forbidden.** PR CI already runs the merge ref, so a
   stale base's failures are invisible there and rebasing to "fix" them changes what was tested.

Reading `origin/master` costs one fetch and mutates nothing. There is no case where the rebase is
the cheaper answer to *"is this premise still true?"*.

## The corollary that is easy to miss

**A premise check that comes back CONFIRMED off a stale base is not confirmed either** — it is
unverified, and it happens to agree. The direction of the error means stale-base confirmations are
usually right, which is precisely why they are never noticed and why the habit survives. Both
readings are invalid; only one of them is embarrassing.

## Sibling rulings

- **068** — a premise-waiting item is re-anchored at every run start. 068 says *when* to re-check;
  070 says *against what*. A re-anchor performed against a stale base satisfies 068 and still
  produces the wrong answer.
- **069** — the ledger is a floor, not an oracle: read master to see what EXISTS, read the ledger
  to see what is HELD. 070 is the same instinct generalised past ruling numbers to every premise.
- **053 / gotcha #47** — a sibling lane's fresh commit is invisible until you fetch.
