# `pooled-label-options` — the pooled-category display choice (#2108, item 2)

```bash
tools/pooled-label-options/run.sh                       # curl production, then render
CAL_PAYLOAD=/tmp/cal.json tools/.../run.sh --no-fetch   # render a saved payload
```

Writes a one-pager to `$OPTIONS_OUT` (default `/tmp/pooled-label-options.md`). A rendered
copy is committed here as **`one-pager-2026-08-23.md`** — that is the artifact for Alex.

**Mocks only.** This changes nothing the page reads. Which option ships is Alex's ruling
(Fable directive, UX-P120 item 2: *"Pooled-category display is a TASTE call — Alex's, not
ours."*).

## Why the copy is generated instead of typed

#2108 exists because a hand-written census — "exactly **2 of 128** rows pool" — was quoted
as fact in a source comment for a cycle, and every number in it was wrong. A hand-typed
mock of a sentence that is *derived from data* is the same mistake at one remove: the
sentence in the document and the sentence the code would emit become two things that can
disagree, and only one of them ships.

So every string in the one-pager is produced by running the real functions —
`normalizeCat`, `aggregateBuckets`, `cohortFilterFor`, `ece`, and for option C the page's
own `describeCategoryPopulation` — against the live payload.

## The three options, by axis

Four ECEs are reachable for a pooled row. The page renders the one that is on none of them:

| axis | reading |
|---|---|
| A | server key only, ALL rows — **what `by_category` publishes** |
| B | server key only, cohort filter |
| C | pooled keys, ALL rows |
| D | pooled keys, cohort filter — **what the page renders today** |

| | directive's wording | renders | reconstructible by a reader? |
|---|---|---|---|
| **A** | cohort value with a pooled label | axis B | yes — filter `price_moved != false`, one key |
| **B** | published value with a label | axis A | yes — it *is* the published number |
| **C** | keep pooling, name the fold | axis D | only if the fold is listed, which is the change |

The option labels are prose and can be read two ways; the axis letters cannot. That is why
the generator prints both.

## What the numbers say (2026-08-23 payload)

- 15 rendered rows, **6** of them pool. `soccer` folds **55** payload categories, of which
  **1** is published.
- **Option A costs 131,996 of 435,126 outcomes (30%)** across the six rows — the leagues
  stop counting toward their own sport. That is the decisive number.
- **Option B** matches the API byte for byte but makes this one table all-resolved while
  every other figure on the page is traded-only.
- **Option C** keeps the largest sample and recomputes nothing, but does not scale: soccer's
  55-member enumeration is a wall of text, and capping it means the disclosure is once again
  not fully checkable.

## `2108-disclosure-fix.patch`

The prepared fix for all three #2108 defects, held here because
`frontend/lib/calibrationPopulation.ts`, `frontend/app/calibration/page.tsx` and
`frontend/__tests__/lib/calibrationPopulation.test.ts` are all **barred** while
`ux-102..106` are unmerged (UX-P120's write gate: `origin/master` must contain `ux-106`).

It is **tested, not proposed**. Applied to this tree and gated:

| gate | result |
|---|---|
| `git apply --check` | exit 0 |
| `npm run build` (ESLint) | exit 0 |
| `npm run typecheck` | exit 0 — **70 errors, baseline 70**, zero new |
| `npx jest` (full) | exit 0 — **3,137 passed**, 0 failed |
| calibration subset | 319/319 |
| `tools/calibration-divergence/run.sh` | exit 0, report **byte-identical** to the pre-patch run |

That last row is the point, and it is the directive's named gate: the fix is
**disclosure-only and moves no measured number**.

The patch is a plain unified diff against `program/ux-106`. Apply with
`git apply tools/pooled-label-options/2108-disclosure-fix.patch` once the drain lands, then
re-run the divergence sweep.

### What it changes

1. **Defect 1** — the header census. "exactly 2 of 128 rows pool" → the measured
   136 raw / 58 normalized / 7 pooling keys / 6 rendered, dated, with an explicit note not
   to restate a census as a constant. Between 08-22 and 08-23 tennis went from 3 to 4
   published members with no code change, which is the argument for deriving it.
2. **Defect 2** — the section sentence's fraction. The numerator now counts pooled rows
   over `categoryMetrics` (the RENDERED rows) instead of over every normalized key, so both
   halves come from one population. "7 of 15" → **6 of 15**, and hovering all fifteen rows
   now finds six. A `data-total-rows` attribute is added so the rail can grade the pair.
3. **Defect 3** — the word "published". Members are split into those the API actually
   publishes and those it does not, and only the first group is called published. The
   enumeration is capped at 4 with the count always stated (soccer: 55 → "1 published in
   `by_category` (soccer) and 54 not published (… and 50 more)").

Two existing tests asserted the old, false wording (`"pools the published categories"`) and
were **re-anchored to the property, not relaxed** — they now assert the published/unpublished
split exists and that no member is miscounted as published.
