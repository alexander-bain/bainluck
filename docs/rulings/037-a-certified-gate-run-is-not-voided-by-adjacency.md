# RULING 037 — A certified gate run is not voided to resolve a textual adjacency

date: 2026-08-12
author: Alex
via: UX-P067 acceptance, ruling 1 — RATIFIED as precedent; banked by UX-P068
issues: #1621 · #1546

> **A lane does not rebase — and thereby rewrite a commit whose five gates are green — in order
> to resolve a conflict that is textual adjacency rather than semantic overlap. The lane states
> the conflict and its resolution in the handoff; the Integrator resolves it at merge, where that
> authority already lives.**

## What produced it

`program/ux-52` (UX-P066) amended gotcha **#124** in place. Master's LAT-P042 appended a new
gotcha **#125** two lines below it. Different numbers, different content, no semantic overlap
whatsoever — but the same tail region of one file, so `git merge-tree` exits 1.

UX-P067 declined to rebase, recorded the conflict, named the resolution (**KEEP BOTH**), and
handed it over. Alex ratified that call and named it the right precedent.

## Why rebasing would have been the worse choice

Rebasing rewrites `4c491eaf`. That commit's certification — backend 13,683 / build / typecheck /
jest / e2e, all green — was earned **on that tree**. Ruling 017 already says the quiet part:
*gates prove something about the commit you tested, not the commit you push.* Rewriting the commit
discards the proof and obliges a full re-run.

So the trade is: **void a certified five-gate run to fix two adjacent lines of prose.** That
inverts the cost of certification — it makes being certified *early* a liability, because every
subsequent unrelated push to a shared docs file would force a re-certification. A lane that
learned that lesson would rationally delay its gates until the last possible moment, which is
precisely when they are least useful.

## The distinction that governs

- **Textual adjacency** — two edits near each other in one file, neither depending on the other,
  no shared meaning. The merge is mechanical and the resolution can be stated in one line.
  → **State it. Do not rebase.**
- **Semantic overlap** — the two changes touch the same behaviour, and merging them requires
  deciding which is right. → **Rebase and re-certify.** No amount of stating resolves it, because
  the resolution is a judgement about code, and the gates on the merged tree are the evidence.

The test is not "does `merge-tree` exit 1". It exits 1 for both. The test is whether resolving it
requires a **decision about behaviour** or only about **layout**.

## What the lane owes when it declines to rebase

Not silence. The handoff must carry:

1. that `merge-tree` exits non-zero, and **which branch actually owns the conflict** — a stacked
   branch inherits its parent's conflict and will otherwise be blamed for it;
2. the exact file and the two competing hunks;
3. **the resolution**, stated as an instruction (here: keep master's new #125 and ux-52's
   rewritten #124), not as a description of the problem;
4. the base the gates were actually run on.

With those four, the Integrator merges without re-deriving anything. Without them, "do not rebase"
is just an unreported conflict.

## The structural note this arrived with

Rulings stopped colliding when ruling 001 gave each one its own file. Gotchas did not get that
treatment, so every lane still edits the tail of one `docs/gotchas-reference.md` — which is what
manufactured this adjacency in the first place. Alex has routed the per-file split of
`docs/gotchas-reference.md` to the triage chain as a plumbing queue (same shape as
`docs/rulings/`, CI-guarded in both directions). **This ruling governs the general case and
outlives that fix**, since one shared append region is not the only way two lanes can land near
each other.
