# RULING 035 — A lookup must never throw; and an interim tie-break carries its own expiry

date: 2026-08-12
author: Alex
via: 339T sequencing, ruled as mechanics rather than taste
issues: #1779 · #1798

> **`_find_by_source_id` must never throw.** Among rows sharing a provider id, prefer the row
> **whose date matches the incoming claim** — the cascade's own verification criterion — then the
> row with the **most provider bindings**. **Log every duplicate hit** and **append the id to the
> dedup worklist.**
>
> **This is an interim rule and it has an expiry written into it.** Once the RE-KEY sweep clears
> the duplicates, a **unique partial index on (provider, source_id)** makes the throw impossible
> by construction, and the tie-break ladder above becomes dead code to be deleted — not kept
> "just in case".

## What produced it

Step 1 of the event-matching cascade calls `scalar_one_or_none()`
(`backend/app/services/event_registry.py:253`). That raises `MultipleResultsFound` when two rows
share an `espn_id`. 339S's census found duplicates existed season-wide in MLB — so the FIRST step
of the cascade was throwing, in production, for those games, on every poll.

The failure mode is quiet in the worst way. A throw at step 1 does not return "not found" and fall
through to step 3; it aborts the claim. The row is neither matched nor created, and the next
poll does the same thing again. 339S suspected this of contributing to the Aug 12 rows never being
created properly.

## Why the ruling is mechanics, not taste

Which row a duplicate lookup returns *looks* like a judgment call, which is why 339S deliberately
did not fix it — it was scoped to the ruled disqualification, and changing lookup semantics on a
guess is how a matching layer acquires a second personality.

But there is no taste in it once the question is asked precisely: **the cascade already has a
criterion for whether a candidate is the right game — the date.** Step 3 uses it. Preferring the
date-matching row is not a new opinion; it is applying the existing one at step 1. Most-provider-
bindings breaks the remaining tie toward the row that more sources have already agreed on, which
is the row a merge would have kept anyway.

## The expiry is the load-bearing half

An interim rule with no expiry becomes permanent by default, and this codebase has the receipts:
gotcha #35's undated "~2-3 months" retention prose was cited by three separate recovery rails and
every one of them still ground purged markets, because **a predicate cannot consume a range
written in prose**. The same shape applies here. A tie-break ladder that survives after the index
lands is a second answer to a question that now has exactly one, and the next reader cannot tell
which is authoritative.

So the index is not a follow-up. It is **part of this ruling**, and it is an acceptance criterion
of the sweep that clears the duplicates.

## What the measurement changed about the index (339T, 2026-08-12)

The census that this ruling ordered found the index is **not a one-liner**, and the ruling is
recorded here with those corrections rather than with its original assumption:

1. **There is no `(provider, source_id)` pair to index.** Provider ids live in three separate
   columns — `external_id` (odds_api), `statpal_fixture_id` (statpal), `espn_id` (espn), per
   `_SOURCE_ID_COLUMN`. The ruling therefore means **three partial unique indexes**, not one.
2. **`espn_id` duplicates are not an MLB problem.** 183 duplicate values across 405 rows in 12
   leagues; MLB in-season is 30 values / 64 rows of that. **NCAA Baseball alone is 123 values /
   280 rows.** An MLB-scoped sweep clears about a sixth of what the index needs cleared.
3. **`statpal_fixture_id` cannot take `WHERE ... IS NOT NULL`.** 8,272 rows carry the **empty
   string**, written during one ingestion week (2026-02-28 → 03-07). `''` is not NULL, so that
   predicate admits 8,272 colliding values. Normalise `''` → NULL first, or predicate on
   `IS NOT NULL AND <> ''`. There are also 8 genuine statpal duplicate pairs.
4. **`external_id` has zero duplicates** and can be indexed today.
5. **Ordering is not optional**: the sweep must clear duplicates *before* the index is created, or
   creation fails on the existing violations. And per gotcha #31, `CREATE INDEX CONCURRENTLY` must
   never go in the Alembic chain — it hangs Heroku's ~5-minute release phase and took the site
   down in May.

## How to apply

- Never let a cascade step raise on data that is merely duplicated. Duplication is a condition to
  report, not an exception to propagate.
- When you write an interim rule, write its expiry in the same breath, and put the thing that
  retires it in someone's acceptance criteria. An interim rule whose retirement is unowned is a
  permanent rule that nobody agreed to.
- Related: [030](030-census-runs-before-the-staged-work.md) — the census ran first here too, and
  again re-decided the work: the index this ruling ordered turned out to be three indexes, one of
  which is blocked by a sentinel value nobody knew was there.
