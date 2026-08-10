# DISCOVER EXIT EXAM

The Discover program's certification record. Modeled on `docs/CALIBRATION-EXIT-EXAM.md`: each
numbered item is a thing that must be demonstrably true before the program can be called done, and
each carries the measurement that proves it rather than an assertion that it was handled.

Created 2026-08-10 by Queue 308 to hold Annex A. The numbered scoreboard is not yet written — the
first Discover arc (ruling 016) has not started.

---

## Annex A — pre-arc interestingness baseline

**measured:** 2026-08-10, Queue 308, post-tie-fix, **no fitting**
**source:** `GET /api/admin/ranking-judgments/eval-export` (admin-authed, reviewer emails hashed)
**purpose:** the number future interestingness claims are measured against

### Verdict: NO BASELINE MEASURABLE

Not a tooling failure and not a hedge. There is not enough labelled data for a baseline to mean
anything, and the specific reason matters more than the number would have.

### The corpus, in full

| Fact | Value |
|------|-------|
| Total labelled rows **in existence** | **24** |
| `days=30` | 0 rows |
| `days=90` | 24 rows |
| `days=365` | 24 rows — identical payload, so 24 is the whole corpus |
| Label observation window | 2026-05-24T16:04:58Z → 2026-05-25T18:18:28Z (**one ~26-hour sitting**, 77 days before measurement) |
| Surface | `native_discover` (single) |
| Positives (`love`) | **1** |
| Negatives (`kill` 16 + `bad` 4) | 20 |
| Excluded (`fine`, neutral) | 3 |
| Usable under the binary policy | 21 |
| Largest category stratum | baseball, n=7 (`LABEL_STRATUM_GATE` is 50) |

Categories: baseball 7, politics 5, geopolitics 4, basketball 4, motorsports 1, hockey 1, golf 1,
soccer 1.

### Why no cutoff rescues it

A temporal holdout partitions on **label observation time**. Every label here sits inside one
26-hour session, so any cutoff puts the single positive on exactly one side and leaves the other
one-class — which the fitter must refuse. There is no date that produces two usable partitions.
This is a property of *when the labelling happened*, not of the split logic.

Measured, cutoff at `2026-05-25T00:00:00Z`:

```
train:    n=3   hash=cdc214fc8816252a
holdout:  n=18  hash=ce8220f2c75a8501
dropped (no timestamp): 0
baseline p@20:  0.0556        candidate p@20: 0.0556
delta:    0.0 points (floor 2.0)
VERDICT:  INSUFFICIENT_EVIDENCE
reasons:  HOLDOUT_TOO_SMALL
```

The 0.0556 is 1 positive in 18 rows. It is arithmetic, not a measurement of ranking quality — there
is no ranking signal in a set with one positive.

### What this means

**Ruling 016's entry ticket cannot be paid with existing data.** *"No interestingness claim without
the temporal holdout"* — and no holdout is constructible. So the first Discover arc is gated on
**labeling volume, not on code**.

Queue 308 fixed the half that was fixable: the evaluator no longer breaks ties with the answer key
(it was reporting **0.5 against a true base rate of 0.25** on a tied slate), the cutoff exists, and
the fitter now refuses out loud instead of printing a confident recommendation. What remains is
labels.

Worth stating plainly: the interestingness blend has been live in production at 20% weight against
weights that were never calibrated on labelled data, and the corpus that would validate it is 24
rows from one afternoon in May.

### What would move this

Not a code change. A labelling batch that (a) spans more than one session, and (b) carries enough
positives to survive a split — the standing Alex offer in ruling 019, which is an offer and never a
gate. Until then, global-only tuning per ruling 019.

**No claim is attached to this annex.** It is the floor future claims are compared against, and
right now the floor is "not yet measurable".
