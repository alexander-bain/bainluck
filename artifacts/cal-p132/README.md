# artifacts/cal-p132 — `polymarket/tech` (board rank 19)

Read **`RULE-DESIGN-polymarket-tech.md`** first; it carries every number and the
reasoning. This file says only what each artifact is, so a later reader does not re-run
something that is already answered.

Curve `2026-08-29T00:36:47Z`, population `q268`. Exact rail: **n 2,738 / ECE 5.00 /
gap −1.02** against the payload's **2,779 / 4.91 / −0.85** (−1.48% rows).

**Verdict: REFUSED.** Seventeen partitions, exhaustively searched with no retention
floor (`--min-rows 1 --min-share 0`). Zero subsets clear the 3.0 bar on the worst half
at any retention. Fourth consecutive refusal, and rank 19 was the last unworked cell on
the queue — see `RULE-DESIGN` §7.

## Folds — `calibration_cell_exact.py --source polymarket --category tech`

All run with `--holdout-at 32127295` (a **50.0 / 50.0** row split derived from
`cluster_rows` in `artifacts/cal-p128/sigma-polymarket-tech.json` — the cleanest in the
lane), so every artifact carries the pooled table AND both halves.

| file | arms | note |
|---|--:|---|
| `exact-…-none.json` | 1 | baseline + self-check. **Both halves fail**: OLD 5.61, NEW 5.98 |
| `exact-…-twin.json` | 5 | **built this session** — see below |
| `exact-…-sumband.json` | 12 | best worst-half anywhere (4.36) but **leaky** (`sh.mw`); 0 of **4,095** subsets pass |
| `exact-…-policy.json` | 5 | best **leakage-free** result (4.66 worst-half at 66.3% retention) |
| `exact-…-pairsum.json` | 5 | identical to `policy`, to the row — the cell has no O/U pairs |
| `exact-…-shape.json` | 5 | leaky; `field_1win` is 28.3% at 4.98 worst-half |
| `exact-…-market_type.json` | 5 | leakage-free; the 81.3% `field` arm fails BOTH halves |
| `exact-…-pairtype.json` | 5 | collapses to `market_type` |
| `exact-…-price_moved.json` | 2 | **the important negative** — both arms carry the same slope, so the stale-opening-price fallback is NOT the mechanism |
| `exact-…-cpdrift.json` | 5 | placeholder classes are 8 rows here |
| `exact-…-policy2.json` | 3 | 99.7% in one arm |
| `exact-…-bandratio.json` | 1 | **degenerate** — 100% `z_not_a_partition` (CAL-P131's band grammar does not occur) |
| `exact-…-slotratio.json` | 1 | **degenerate** — 100% `z_no_declared_n` |
| `exact-…-age.json` | 1 | **degenerate** — 100% `z_no_snapshot` |
| `exact-…-ladder.json` | 1 | **degenerate** — 100% `z_not_a_ladder` |
| `exact-…-pair.json` | 1 | **degenerate** — 100% `z_not_ou_pair` |
| `exact-…-golfround.json` | 1 | **degenerate** — 100% `tourney|other`. Run only to record it; CAL-P130 established it is meaningless on a Polymarket cell |
| `exact-…-series.json` | **289** | one arm per Polymarket event id. `rules-series.json` does not exist — the search refuses 289 classes rather than sampling |

⚠️ The `twin` fold's self-check reads **2,734 / 5.08** where every other fold reads
**2,738 / 5.00**. Its extra join makes chunks heavier, so the recursive split-on-timeout
lands differently and `virtual_market`'s grouping test sees a slightly different partial
cluster. That is the documented chunking approximation, four rows wide, and it does not
move any conclusion here. Do not read it as two populations.

## Rule searches — `calibration_rule_search.py --bar 3.0 --min-rows 1 --min-share 0`

`rules-<dim>.json` for every fold above. `rules-bandratio.json`, `rules-slotratio.json`,
`rules-age.json`, `rules-ladder.json`, `rules-pair.json` and `rules-golfround.json` are
single-arm refusals.

## Built this session — `--by twin`

The two-grain redundancy dimension: does this row's `group_id` publish the same question
BOTH as a `field` and as a shelf of `container_member` binaries, and which grain is this
row? Leakage-free (`market_type` + `group_id`; no resolution input). **27 guards** in
`backend/tests/test_calibration_cell_exact_p132_twin.py`, and `twin` registered in
`SHIPPED_DIMENSIONS` in `test_calibration_cluster_sigma_p121.py` in the **same commit**.

It refused (0 of 31), and the **control** is the part to keep:

```
  a_twinned|f       1530   56.0%   ECE  6.99    <- same question, published twice
  b_field_only|f     696   25.5%        4.64    <- CONTROL: same grain, published once
```

Holds in both halves (9.80 vs 5.59 OLD, 8.03 vs 3.37 NEW). And it is **not** the
compression of §3 — the control has the steeper slope and the lower ECE.

## Other

* `recalibration-slope.py` — fits `logit(win) = a + b·logit(price)` per arm on bucket
  aggregates and runs the fit-on-OLD / apply-to-NEW holdout test. Reproduces every
  slope and every recalibrated ECE quoted in `RULE-DESIGN` §3 and §4.
  Usage: `python3 artifacts/cal-p132/recalibration-slope.py <fold.json> <label>`.
* `raw-cell-names.json` — all **2,973** raw `polymarket/tech` markets (id, name,
  market_type), pulled by recursive split-on-cap so the 1,000-row cap cannot truncate
  it. The source for the 29.2% word-bingo figure.
* `spread-polymarket-tech.txt` — `calibration_cluster_spread`, verdict **MODERATE**
  (260 `group_id` clusters, 26.6% wider than the chunk). Predicted a single-digit
  shortfall; the fold delivered **−1.48%**.
* `scorecard-q268.txt` — the board this session ran from.
* `freeze-score-session-start.txt` — ruling 009 gate at session start: **3/24 clean,
  21 misses, `NOT_MET`**.
* `sweep.log` — the full 17-fold sweep, verbatim.

## Do not re-run

The six degeneracies. The σ-sweep (read `artifacts/calibration-scorecard/measured-sigma.json`).
The `price_moved` slope comparison — it is the answer to "is this the stale-opening-price
fallback", and the answer is no.
