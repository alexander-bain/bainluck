# RULING 001 — Ruling appends become one file per ruling

date: 2026-08-09
author: Fable
issues: #1621

**DO NOT REMOVE (CI-guarded).**

> A new ruling is a NEW FILE at `docs/rulings/NNN-<slug>.md`, plus ONE index line in
> `docs/PRODUCT-BRAIN.md`. Appending ruling prose to the body of PRODUCT-BRAIN is retired.
> Everything already in PRODUCT-BRAIN stays where it is.

## The named failure: keep-both patch-id detachment

`docs/PRODUCT-BRAIN.md` was append-only into one shared region, so two lanes that each banked a
ruling on the same day both appended at the same place. Git cannot auto-merge that: it is a
conflict, and the only correct resolution is **keep both, in some order**. Which means the merged
commit is not byte-identical to the commit that was written.

**A commit that was merged through a conflict resolution has a different patch-id from the
original forever.** `git cherry origin/master <branch>` compares patch-ids. So that commit reports
`+` — "not upstream" — permanently, on every future cycle, for the rest of the branch's life.

INT-027 found **three** of these in a single cycle: UX `b0ad31d7` and `8e046686`, and CAL-P015
`aef2f57c`. All three were fully on master. All three were reported as new work. Each had to be
disproved by hand, by grepping a distinctive line of its diff against `origin/master`, before it
could be safely skipped.

**The class is self-perpetuating, which is what forced the fix.** In the same cycle that
diagnosed it, CAL-P021 conflicted against Alex's same-day Integrator single-writer ruling, was
resolved keep-both, and thereby minted a fourth permanent false positive. Every docs-banking
cycle grew the set. Left alone, the Integrator's cheapest correctness check decays until it
reports mostly noise — and the failure mode of a noisy check is that someone eventually trusts it
and merges a duplicate ruling into the product's judgment document.

## Why a directory fixes it

Two lanes banking two rulings now write two different filenames. **There is no shared region, so
there is no conflict, so no patch-id is detached and `git cherry` keeps telling the truth.**

## What this deliberately does NOT claim

The index line in PRODUCT-BRAIN is still a shared-file edit and can still conflict. This ruling
does not pretend otherwise. It changes what a conflict *costs*:

| | before | after |
|---|---|---|
| what conflicts | 60–90 lines of ratified prose | one line |
| how it is resolved | read both, judge, compose | keep both, sort by number |
| can content be lost | yes, silently | no — the test fails if a file loses its line |
| patch-id detached | on the ruling itself | on a one-line bookkeeping commit |

A detached patch-id on an index line is cheap to disprove: one grep for a filename. A detached
patch-id on a ruling means re-reading prose to decide whether it is already banked.

## Enforcement

`backend/tests/test_product_brain_integrity.py` asserts index ↔ files consistency in both
directions: every ruling file has exactly one index line, every index line points at a file that
exists, numbers are unique, the heading number matches the filename, and the index stays sorted.
A ruling that is filed but never indexed fails CI, and so does an index line whose file was
deleted.

The existing CI marker strings are untouched. This ruling adds guards; it removes none.
