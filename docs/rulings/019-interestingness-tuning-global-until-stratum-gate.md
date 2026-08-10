# RULING 019 — Interestingness tuning is GLOBAL-ONLY until a stratum clears the gate on BOTH sides

date: 2026-08-10
author: Alex
via: Fable, ratified
issues: #1550 · #1534

**DO NOT REMOVE (CI-guarded).**

> **Interestingness tuning is GLOBAL-ONLY until a category clears `LABEL_STRATUM_GATE = 50` in
> BOTH the train partition AND the temporal holdout. Per-category overrides are parked.**
>
> **Thin-strata labeling batches are a standing Alex offer, never a gate.**

## Why both sides, and not just "50 labels"

A category can clear 50 labels in aggregate and still hold ~zero in the holdout. Fit a per-category
override on that and it is trained on history and validated on nothing — which is exactly Codex
C216's train-on-your-own-test-set defect, just sliced thinner and harder to see. A gate that binds
on one side does not bind.

Slicing also multiplies the tie problem C216 found. Per-category top-K on a thin stratum is mostly
ties, and a tie-break that touches the label manufactures precision out of nothing (measured on a
40-row tied slate: **0.5 reported against a true base rate of 0.25**). The fewer labels in a
stratum, the larger the lie.

## What "global-only" permits

Tune the global weight vector against the whole labelled population, under the temporal holdout and
the claim envelope. That is the only tuning that ships. Per-category base scores stay where they
are; no new per-category override mechanism gets built while this ruling stands — building the
mechanism is how it starts getting used.

## The offer is not a blocker

If a stratum is thin, the answer is **"tune globally now"**, never **"wait for labels"**. Alex's
on-demand grading batches are a standing offer that anyone may take up, and taking it up must never
become a precondition for shipping. This is ruling 014's four-cycle debt pattern, named in advance:
a measurement obligation that never wins a ranking against the feature it gates. Global tuning is
always available, so the gate can never be the reason nothing ships.

## The measured state on the day this was banked (2026-08-10)

Queue 308 pulled the entire labelled corpus from
`GET /api/admin/ranking-judgments/eval-export`. It is worth writing down, because it makes the
ruling concrete rather than hypothetical:

- **24 rows total.** Not 24 in 30 days — 24 in existence (`days=90` and `days=365` return the
  identical payload; `days=30` returns zero).
- All 24 observed inside **one ~26-hour window**, 2026-05-24T16:04Z → 2026-05-25T18:18Z, on one
  surface (`native_discover`).
- Under the binary policy: **1 positive** (`love`), 20 negatives (`kill` 16 + `bad` 4), 3 excluded
  (`fine`).
- Largest single stratum: baseball, **n=7**. The gate is 50.

So no category clears the gate on either side, and — more decisively — **no temporal cutoff exists
that yields two usable partitions**, because every label sits in one sitting. Run against real
data, the fitter correctly returns `INSUFFICIENT_EVIDENCE / HOLDOUT_TOO_SMALL`.

**Ruling 016's entry ticket therefore cannot currently be paid, and the blocker is labeling volume,
not tooling.** The tooling now refuses honestly, which is the part Queue 308 could fix. The rest is
labels.

## Related

- Ruling 016 — the entry ticket: no interestingness claim without the temporal holdout.
- Ruling 014 — the four-cycle debt pattern this ruling's "never a gate" clause is guarding against.
- `LABEL_STRATUM_GATE` — `backend/app/utils/discover_label_eval_runs.py`.
- `eval_metadata["holdout_readiness"]` — every persisted eval run now records whether a holdout was
  constructible at all, so this cannot quietly stop being true.
