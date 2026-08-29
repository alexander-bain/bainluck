# CAL-P128 — σ-sweep of the working board

Read `FINDING-sigma-sweep.md`. Headline: **all fourteen working cells measured.
Ten established, TWO refuted, two undecidable.** The refusals are `kalshi/golf`
(already known, 17-CAL) and — new, and the largest result here —
**`polymarket/soccer`**, the board's rank 4 at 44,857 excess-outcomes, measured
σ 0.87 against the board's 2.75.

The measurements are committed as a ledger the board reads, not as prose:
`artifacts/calibration-scorecard/measured-sigma.json`.

## Regenerating

`source ~/.claude/.env` in the SAME command or the scripts exit 2 (gotcha #124).

```bash
# the sweep — ~1-11 min per cell, seeded, sequential on purpose (the rail
# spends its budget on db-query chunks and will hit the 60/min throttle if two
# run at once)
bash artifacts/cal-p128/run-sigma-sweep.sh

# fold the artifacts into the committed ledger
python3 backend/scripts/calibration_sigma_ledger.py \
    --build artifacts/cal-p12*/sigma-*.json --show

# the board, with the measured column
python3 backend/scripts/calibration_scorecard.py --live --markdown
```

`run-sigma-sweep.sh` skips a cell whose JSON already exists, so re-running it is
how a transient failure is retried — `polymarket/esports` died once on a
`RemoteDisconnected` mid-sweep and was picked up by a second pass.

Budget: eleven cells took 1-11 minutes each. `polymarket/esports` took ~25 min on
a loaded database and `polymarket/soccer` ~40 min (106,803 rows over 14,897
markets). Run the sweep sequentially — two concurrent sweeps put avoidable load on
production Postgres, and the throttle is not what makes it slow.

## Files

| file | what it is |
|---|---|
| `FINDING-sigma-sweep.md` | the write-up, the table, and what is owed to Alex |
| `sigma-<source>-<category>.json` | one `calibration_cluster_sigma` run per cell |
| `log-<source>-<category>.txt` | its chunk-by-chunk sweep log |
| `run-sigma-sweep.sh` | the driver |

`kalshi/golf`'s measurement is CAL-P127's and lives in `artifacts/cal-p127/`; the
ledger build globs both directories.

## Two things that cost time here

- **The measured σ is on the EXACT rail's ECE; the board's is on the PAYLOAD's.**
  They differ (golf 3.84 vs 3.88) because the rail's id-range sweep and the
  published fold do not select identically. The ledger stores both and
  `validate()` re-checks against the rail's, which is what the bootstrap actually
  divided by. The first draft conflated them and the validator caught it on its
  first run.
- **Coverage before conclusions.** `n_exact / n_payload` is stored per cell. Two
  cells are outside ±10% and neither is allowed to decide anything. On
  `polymarket/basketball` (0.641) the *payload* is the inflated side — CAL-P126
  measured it 43.44% phantom — so "the rail under-counts" would have been exactly
  backwards.
