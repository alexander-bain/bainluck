# CAL-P130 — `polymarket/golf` (rank 12), the conveyor's sixth cell

**Verdict: REFUSED. No rule banked.** The board's five banked designs stand at five.

Full write-up: [`RULE-DESIGN-polymarket-golf.md`](RULE-DESIGN-polymarket-golf.md).

## What is in here

| file | what it is |
|---|---|
| `RULE-DESIGN-polymarket-golf.md` | the diagnosis, the refusal, and the writer defect |
| `spread-polymarket-golf.json` | `calibration_cluster_spread` — LOW risk, run BEFORE the folds (lesson 3) |
| `exact-polymarket-golf-<dim>.json` | 15 folds on the producer's own chain |
| `exact-polymarket-golf-slotratio-holdout.json` | the new dimension, holdout-split at `market_id 22743356` |
| `exact-polymarket-golf-sumband-holdout.json` | the same for the partition the queue named |
| `rules-<dim>.json` | 15 exhaustive lattice searches, `--min-rows 1 --min-share 0` |
| `rules-slotratio-holdout.json` / `rules-sumband-holdout.json` | the same, ranked by the WORSE half |

## The dimension this session added to the rail

`calibration_cell_exact.py --by slotratio` — bands a market's published price sum against
the slot count its own NAME declares (`… Winner` → 1, `… Top 10` → 10), rather than
against a constant. 26 guards in
`backend/tests/test_calibration_cell_exact_p130_slotratio.py`.

**The guard to keep if the others are ever trimmed** is
`test_the_expression_never_reads_a_realized_winner`. `shape` and `sumband` branch on how
many outcomes actually won, which is fine for diagnosis and is leakage in a shipping
exclusion rule. `slotratio` reads only the market name and the published prices.

## Reproducing

```bash
source ~/.claude/.env
python3 backend/scripts/calibration_cell_exact.py \
    --source polymarket --category golf --by slotratio \
    --holdout-at 22743356 --out /tmp/slotratio.json
python3 backend/scripts/calibration_rule_search.py \
    --in /tmp/slotratio.json --bar 3.0 --min-rows 1 --min-share 0
```

Each fold is ~60–120 s. Run the board from the **repo root** (CAL-P129, lesson 15). Do not
run a fold and a census concurrently — heavy folds load production.

## The three things worth carrying to the next cell

1. **`sumband` measures the wrong quantity on any multi-slot field** (gotcha #23). The
   generalisation is the ratio to the declared slot count, and it is leakage-free.
2. **A refusal can fail two different ways.** `slotratio` fails on the HOLDOUT (pooled
   3.03 → worst-half 4.06). `sumband` survives the holdout and fails on RETENTION (every
   survivor deletes 72.7–82%). A session that ran only one check would have named the
   wrong cause.
3. **Every placeholder detector in this repo keys on MOVEMENT, so every one is blind to a
   price published at the placeholder value from the open.** Parked as CAL-P130-3; it is a
   stronger version of CAL-P129-2.
