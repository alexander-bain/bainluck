# CAL-P1137 — the q269 → q270 population move, measured

Receipt for `CALIBRATION_POPULATION_DECLARATION` on the q270 bump. Sibling of
`artifacts/cal-p1121/`, which measured the writer bar alone; this one measures the
SHIPPED predicate — writer bar (#5401) **and** the threshold-ladder collapse (#5305) —
because the declaration has to bound what actually deploys, not one half of it.

## The numbers

| arm | Kalshi published outcomes | when |
|---|---:|---|
| master semantics (`--arm baseline`, CAL-P1121) | **399,618** | 2026-09-12, earlier |
| q270 semantics (`--arm repaired`, this file) | **306,369** | 2026-09-12 22:40Z → 00:13Z |

1,129 chunks, **0 irreducible**, 5,587s. Event-atomic throughout: chunk ranges are
half-open on the `event_id` VALUE, so no event group is ever split and `event_sizes`
is never counted short.

The two arms are hours apart and the table grew between them (live `by_source` Kalshi
n went 396,160 → 401,282), so the move is stated twice:

```
against the baseline AS MEASURED           93,249 rows = 11.68% of 798,292
against the baseline carried forward       98,416 rows = 12.33% of 798,292
  on the rig's own +0.87% offset
DECLARED                                   12.0%, tolerance 5.0  ->  band 7.0% .. 17.0%
```

`798,292` is the live `total_outcomes` at 2026-09-12T22:44:48Z (`generated_at`
22:16:25Z, `population_version` q269).

## What the ladder contributes, and why it is small

CAL-P1121 measured the writer bar alone at 94,134 rows / 12.04%. Against the
drift-corrected baseline this arm removes 98,416, so the ladder collapse takes roughly
**3,000 published Kalshi rows** on top of the bar.

That is not the arm failing to bite. Its raw candidate cohort is large — 8,256 lone
Kalshi `quantity` markets whose own resolutions show more than one winner, 118,184
rungs, 109,928 suppressible — but almost all of those rungs are already refused
upstream by the esports-bundle rung, the non-partition multi pool, or the multi arm's
own `0.005 < p < 0.98` band. What the collapse removes is what survived every one of
those and was still the same question counted twice.

## Polymarket is bounded, not folded

The rig is Kalshi-scoped (the writer bar is a Kalshi rule by construction), but the
ladder arm is source-agnostic. The whole raw Polymarket cohort is **1,149 markets /
6,422 suppressible rungs** across the entire table before the population pipeline
whittles it — at most 0.8pp of the published population and in practice far less.
That is inside the declared tolerance by an order of magnitude, and folding it would
have cost a second 93-minute source-wide sweep to move the declaration by a rounding
error. Stated here rather than left as an unexamined gap.

## Reproducing

```
source ~/.claude/.env
python3 backend/scripts/calibration_population_move_5401.py \
    --arm repaired --boundaries artifacts/cal-p1121/boundaries.json \
    --out artifacts/cal-p1137/population-q270-both.json
```

The `--arm baseline` control belongs to CAL-P1121 and is not re-run here; its own
README says why it is believed (the stale `--max-id`, the event-atomic chunking, and
the second-order `field_completeness` drop the naive fold cannot express).
