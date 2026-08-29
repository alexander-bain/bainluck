# artifacts/cal-p131 — `polymarket/economics` (board rank 15)

Read **`RULE-DESIGN-polymarket-economics.md`** first; it carries every number and the
reasoning. This file says only what each artifact is, so a later reader does not re-run
something that is already answered.

Curve: `2026-08-29T00:36:47Z`, population `q268`. Exact rail: n 12,700 / ECE 3.89 /
gap −0.28 against the payload's 12,882 / 3.90 / +0.14 (−1.41% rows, −0.01 ECE).

**Verdict: REFUSED.** Sixteen partitions, exhaustively searched with no retention floor
(`--min-rows 1 --min-share 0`). Zero subsets clear the 3.0 bar on the worst half at any
usable retention.

## Folds — `calibration_cell_exact.py --source polymarket --category economics`

All run with `--holdout-at 32676761` (a 49.9 / 50.1 row split derived from `cluster_rows`
in `artifacts/cal-p128/sigma-polymarket-economics.json`), so every artifact carries the
pooled table AND both halves. `--by none` is the self-check only and has no holdout.

| file | arms | note |
|---|--:|---|
| `exact-…-none.json` | 1 | self-check |
| `exact-…-market_type.json` | 4 | leakage-free; best inherited rule (3.26 / 3.91 at 96% retention) |
| `exact-…-sumband.json` | 14 | best pooled (2.98) but **leaky** (`sh.mw`) and deletes 65.1% |
| `exact-…-bandratio.json` | 8 | **built this session** — see below |
| `exact-…-cpdrift.json` | 5 | placeholder class is 64 rows here |
| `exact-…-price_moved.json` | 2 | both arms over the bar |
| `exact-…-pairtype.json` | 4 | collapses to `market_type` — the cell has no O/U pairs |
| `exact-…-pairsum.json` | 5 | collapses to `sumband` for the same reason |
| `exact-…-policy.json` | 5 | identical to `pairsum`, to the row |
| `exact-…-policy2.json` | 3 | |
| `exact-…-age.json` | 3 | near-degenerate — 99.85% `z_no_snapshot` |
| `exact-…-pair.json` | 1 | **degenerate** — 100% `z_not_ou_pair` |
| `exact-…-slotratio.json` | 1 | **degenerate** — 100% `z_no_declared_n` (CAL-P130's golf grammar does not occur) |
| `exact-…-ladder.json` | 1 | **degenerate** — census scanned **0** O/U markets. See CAL-P131-2 |
| `exact-…-series.json` | 1,658 | one arm per `0x…` condition id; `rules-series.json` was refused over `MAX_CLASSES` |

`golfround` was not run: it reads Kalshi golf ticker structure off `external_id` and is
meaningless on a Polymarket cell (CAL-P130 established this).

## Rule searches — `calibration_rule_search.py --bar 3.0 --min-rows 1 --min-share 0`

`rules-<dim>.json` for every fold above. `rules-ladder.json`, `rules-pair.json` and
`rules-slotratio.json` are single-arm refusals. `rules-series.json` does not exist —
the search refuses 1,658 classes rather than sampling.

## Other

* `spread-polymarket-economics.json` — `calibration_cluster_spread`, verdict **MODERATE**
  (1,176 `group_id` clusters, 11.2% wider than the chunk). Predicts the single-digit
  shortfall the fold delivered.

## What this session added to the rail

`calibration_cell_exact.py --by bandratio` — the DECLARED-PARTITION price sum, and the
second leakage-free dimension on the rail after CAL-P130's `slotratio`. It reads the
market's OUTCOME names for a band grammar (`<x`, `a-b`, `>y`), requires both open tails
before it will band anything, and divides nothing it did not find declared. 62 guards in
`backend/tests/test_calibration_cell_exact_p131_bandratio.py`; registered in
`SHIPPED_DIMENSIONS` in `test_calibration_cluster_sigma_p121.py` in the same commit,
which is the third time that entry has been needed and the first time it was not
discovered by a red sibling suite.

## Do not re-run

* The four degeneracies (`pair`, `slotratio`, `ladder`, `age`) — they are measurements.
* The σ measurement — read `artifacts/calibration-scorecard/measured-sigma.json`.
* The `single`/`unshaped` all-winner census — §4 of the design doc has it, with the
  raw-population control (3,844 markets, 52.7% base rate).
