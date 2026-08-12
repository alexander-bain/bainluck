# RULING 034 — The poll sweeps by branch and confirms by content; the ready token is advisory

date: 2026-08-12
author: Alex
issues: #1621

**The Integrator's readiness poll is: sweep `program/*` and `lane1/*` BY BRANCH, then confirm each
candidate BY CONTENT. The `status: ready_for_integration` token is advisory — it promotes a branch
into the candidate set, it never decides that work is or is not ready. `git branch --merged` is
never used at all.**

This amends ruling 028, which made readiness a literal token. That ruling stands as a rule for
LANES — write the canonical token, declare a hold explicitly. What this ruling changes is what the
INTEGRATOR may conclude from the token's absence: nothing.

## Why the token cannot be the poll

**Five dialects appeared in a single day**, each of which the canonical `^ *status: ready_for_integration`
grep silently misses:

1. `status: READY — <prose>` — no token at all
2. `- **status:** ready_for_integration` — a leading bullet defeats `^ *status:`
3. `verdict: **READY FOR INTEGRATOR.**` — no `status:` key
4. `status: **ready_for_integration**` — bolded value, so the bytes are not the token
5. *(no `status:` key anywhere in the entry)* — the report entry opens `verdict: **PASS**`

A **sixth** was found while writing this ruling: `PROGRAM-UX-REPORT.md`'s UX-P065 entry has no
`status:` key, and UX-P065 was discoverable only because its *queue* file happened to carry one.
Dialect 4 appeared AFTER ruling 028 was written and merged, which is the decisive datum: the rule
was correct, published, and did not stop the drift, because the poll's correctness depends on
every lane's formatting forever and a miss is invisible on both sides.

The failure is silent and one-directional. An unmatchable entry IS a quietly skipped entry, and
nothing anywhere reports "I found nothing because I could not parse it." Across recent cycles,
more merges were found by sweeping branches or by Alex naming one than by the poll.

## Why content, and not `git cherry` alone

`git cherry origin/master <branch>` is the right instrument and a **filter, not a verdict**:

- A `-` (patch-id present upstream) is trustworthy — skip it.
- A `+` (patch-id absent upstream) is a CANDIDATE, not a fact. **Any commit that was ever merged
  through a conflict resolution has a detached patch-id and reports `+` forever.** INT-027 found 3
  of its 15 candidates were false positives — already on master verbatim — and minted a fourth
  while resolving one.

Confirm a `+` by grepping a distinctive ADDED line of its diff against `origin/master`. If the line
is already there verbatim, the commit is spent.

**The counter-data matters as much as the failure, because it names the discriminator.** On
2026-08-12, across the *ready-set* branches, `git cherry` produced **zero** false positives — every
`+` was confirmed genuinely new by content. That is not luck and not a low error rate: none of those
branches had been through a conflict resolution.

**And in the same cycle, widening the sweep to older branches produced one immediately.**
`program/latency-18` (LAT-P021, 2026-08-09) reports `+ de03854f` — yet
`backend/app/tasks/event_concept_warmer.py`, `backend/app/utils/event_concept_cache.py` and
`backend/app/config/event_concept_warm_keys.py` are all PRESENT on master, `build_and_cache` is
defined there, and `event_concept_warmer` is wired into `tasks/__init__.py`. The work landed; the
patch-id detached when it was merged through a conflict.

The two readings together settle the rule: **the false-positive risk is a property of the commit's
HISTORY, not a random defect in the tool.** A branch that rebased cleanly can be trusted quickly; a
branch whose commits were conflict-merged reports `+` forever and must be content-checked every
time. Ask "was this ever conflict-merged?" before deciding how much scrutiny a `+` deserves — and
note the trap in the pairing above: a clean sweep of recent branches invites you to generalise that
cherry is reliable, exactly when the older, more-merged branches are the ones it lies about.

**`git branch --merged` is barred outright.** It answers by ancestry, and a rebase-merge workflow
destroys ancestry by construction: it reports merged work as unmerged and would have the Integrator
re-merge landed commits.

## The consequence lanes must keep paying for

Sweeping by branch is a backstop, not absolution. The ready-set is still the Integrator's work
queue, and it is only cheap if it is TRUE — so the post-merge obligation to flip a queue entry to
`merged` with its landing SHA is unchanged and remains part of the merge, not bookkeeping for later.
INT-034 found the ready grep returning 15 entries of which 0 were real; this cycle found 6 more
spent entries still advertising ready. Drift in that file makes a genuinely-ready lane invisible
inside a list of false positives — the branch sweep is what stops that being fatal, not a reason to
tolerate it.

## The poll, stated

1. Sweep every `program/*` and `lane1/*` head: `git cherry origin/master <branch> | grep -c '^+'`.
2. For each nonzero branch, content-confirm at least one `+` commit against `origin/master`.
3. Read the queue/report entries for HOLDS (`codex_premerge:`) and for scope — a hold is declared,
   never implied (ruling 028).
4. A branch with genuine new content and no declared hold is ready, **whatever token it carries or
   fails to carry.**
5. Never conclude "nothing is ready" from a grep. Conclude it from a branch sweep.
