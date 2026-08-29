# CAL-P127 — `kalshi/golf` (rank 9)

Read `RULE-DESIGN-kalshi-golf.md`. Verdict: **NO RULE BANKED**, cell recommended OFF
the queued board as UNESTABLISHED (measured σ 1.42 vs gate 2.0).

## Regenerating

Everything here is read-only output of committed instruments. `source ~/.claude/.env`
in the SAME command or the scripts exit 2 (gotcha #124).

```bash
# the finding
python3 backend/scripts/calibration_cluster_sigma.py --source kalshi --category golf \
    --out artifacts/cal-p127/sigma-kalshi-golf.json

# the folds (~2 min each; the payload fetch now survives the 60/min throttle)
for d in none series shape sumband cpdrift price_moved market_type age pairsum; do
  python3 backend/scripts/calibration_cell_exact.py --source kalshi --category golf \
      --by $d --out artifacts/cal-p127/exact-kalshi-golf-$d.json
done

# the partition this queue added, split on the cell's own row-median market_id
python3 backend/scripts/calibration_cell_exact.py --source kalshi --category golf \
    --by golfround --holdout-at 26515295 \
    --out artifacts/cal-p127/exact-kalshi-golf-golfround.json

# the exhaustive refusals (local, no network)
python3 backend/scripts/calibration_rule_search.py \
    --in artifacts/cal-p127/exact-kalshi-golf-<dim>.json --bar 3.0 --min-rows 1 --min-share 0
```

`rulesearch-sumband.json` is **not committed** — it is the full 4,095-subset lattice at
1 MB, and its two load-bearing lines (582 under the bar; best 2.43 deleting 40.0%) are in
§2 of the design doc. Regenerate with the command above if you need the rest.

`score_subset.py` scores ONE named subset, for the arms a human can justify rather than
the arms that minimise ECE. It imports the searcher's pooling and restates none of it.
