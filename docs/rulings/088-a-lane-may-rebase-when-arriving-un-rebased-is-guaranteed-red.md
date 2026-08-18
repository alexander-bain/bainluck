# RULING 088 — A lane may rebase when arriving un-rebased is guaranteed-red

date: 2026-08-18
author: Fable
issues: #1609, #1621

⚠️ **Fable's directive named this ruling `087`. `087` was already claimed by `ux` earlier the
same day** (*an exclusion is only safe where a mutation can red it*, banked on `program/ux-83`).
Per the ledger's own rule the lane that claims SECOND moves, so this is **088**. See "The number"
below — the collision is itself a specimen of the thing ruling 085's corollary warns about.

## The ruling

Rule 4 reserves rebasing to the Integrator. **A lane may rebase its own branch anyway — when
arriving un-rebased is *guaranteed* red — provided all three of the following hold:**

1. **The exception is documented in the report.** Not mentioned; documented, with the reason it
   was forced.
2. **The gates re-run green on the new base.** Evidence produced before the rebase certifies a
   tree that no longer exists.
3. **Both the old and the new base are named.** A base SHA is half of what makes gate evidence
   mean anything; a rebase that hides which tree was tested destroys the other half.

**This is the pattern now, not a pardon.** A lane that meets the three conditions is following
the rule, not being forgiven for breaking it.

## Why — the exception exists because the alternative is worse for the Integrator, not easier for the lane

Rule 4 exists because the Integrator is the single writer to master, and a fleet of lanes each
rebasing on their own schedule makes the merge order unknowable. That reasoning is sound and is
unchanged for the ordinary case.

It stops being sound in one specific situation: when the lane can *prove*, before handing over,
that the branch cannot merge green. Then "do not rebase" does not preserve the Integrator's
control — it spends the Integrator's cycle discovering a conflict the lane already knew about.
The Integrator is the critical path; every minute it spends re-deriving a lane's certificate is a
minute nothing merges (ruling 085's cost argument, applied one step earlier).

**The charter case, LAT-P068 (`program/latency-61`):** `program/latency-60` merged *mid-window*
and master moved `522caea4` → `75c32aa2`, producing two independent guaranteed-reds:

- **A ruling-number collision.** The branch was cut when master's highest ruling was `077` and
  banked its own as `078`. Master banked `078`–`083` and `085` in the interim.
- **A `MINIMUM_BANKED_RULINGS` conflict.** HEAD said 81, the branch said 75, and — this is the
  part that makes it un-resolvable by the Integrator alone — **neither number is the merged
  truth.** The correct value, 82, is arrived at only by COUNTING `docs/rulings/[0-9][0-9][0-9]-*.md`
  in the merged tree (#1910). An Integrator resolving `ours`/`theirs` picks wrong either way.

Both were resolved by the lane, the documented way, and the lane named both bases and re-ran the
full suite (16,547 passed / 0 failed, exit 0) on the new one.

## The boundary — what this does NOT authorise

**"Guaranteed-red" means demonstrated, not anticipated.** The test is a runnable one:
`git merge-tree --write-tree origin/master HEAD` reporting conflicts, or a named collision in a
shared append region, or a constant whose merged value is neither side's. A lane that rebases
because master "has moved a lot" and it feels safer is outside this ruling.

**One rebase, not a chase.** LAT-P068 declined a second rebase when master moved again to
`342b5a79`, and instead re-checked only the two conditions that forced the first, then stated
plainly: *"Do not read my green suite as green on `342b5a79`; it is green on `75c32aa2`."* That is
the correct shape. Chasing master turns a lane into a second Integrator, which is the outcome
rule 4 exists to prevent.

**Base drift is disclosed, never absorbed.** If master moves after the gates run, say so and name
the SHA. **Gates prove something about the commit you TESTED, not the commit you push** — the
sentence ruling 017 was banked on, and the reason condition 3 is not bookkeeping.

## The number — a second specimen of ruling 085's corollary, one day later

Fable's directive named this ruling `087` in good faith. `087` had been claimed by `ux` earlier
the same day, from a live window, and the collision was invisible from the ruling FILES alone —
master's highest file is `085`, so `087` looks free to anyone checking `docs/rulings/`.

That is precisely the hole INT-086 fell into 24 hours earlier and wrote up on the `085` ledger
line: **`test_every_ruling_file_at_or_above_the_ledger_floor_is_claimed` asks whether a number is
claimed by ANYONE, not whether it is claimed by YOU**, so riding another lane's standing claim
reads as compliance and the collision only surfaces when that lane merges.

**A ruling number issued in a directive is a proposal, not an allocation.** The ledger is the
allocator (ruling 069); master is only the floor. Claimed here after a `git fetch` in the same
turn: `origin/master` `8db839e7`, highest ruling file on master `085`, **all 408 local and remote
refs swept** for `docs/rulings/087-`, `088-`, `089-` — the only holders anywhere are
`program/ux-83` and `program/ux-84`, both at `087`. **Nothing anywhere holds 088.**

## Sibling rulings

- **085** — a READY whose branch head moved is withdrawn, not re-gated. Same underlying economics:
  the certificate names a tree, and the Integrator's time is the scarce resource.
- **069** — the ledger is the allocator, master is only the floor.
- **017** — gates prove something about the commit you tested, not the commit you push.
