# CAL-P129 — `kalshi/entertainment`: refused for exclusion, and the reason is a writer defect

**Cell:** `kalshi/entertainment` — rank 8, 18,465 excess-outcomes, bar 3.0 pp
**Verdict:** **NO EXCLUSION RULE EXISTS.** Twelve partitions searched exhaustively with no
retention floor; the only subsets that reach the bar pooled all fail the holdout.
**What IS established:** the cell's error is concentrated in *one-winner fields whose published
prices sum to far more than one*, monotone in how far over one they sum, in the same direction on
both holdout halves, and getting worse over time. That is a **pricing defect in what we publish**,
not a population to exclude from the curve.

---

## 1. The cell reproduces, so the refusal is about the cell and not the instrument

```
exact replica    n=8480   ECE=5.10   gap=+0.85
payload          n=8355   ECE=5.21   gap=+1.07
delta            n=+125 (+1.50%)     ECE=-0.11  gap=-0.22
```

Coverage 1.015 — inside `COVERAGE_BAND`, so the rail and the payload are describing the same
population and their ratio means something (CAL-P128 lesson 14). The measured cluster-bootstrap
σ is **4.52** against `SIGMA_GATE = 2.0`, so the cell is **ESTABLISHED**: unlike `kalshi/golf`
(17-CAL) and `polymarket/soccer` (19-CAL), this cell really is broken. It just cannot be *excluded*
into compliance.

`gap` is `Σ(price − win)/n × 100`, so **positive gap = over-prediction**. That sign is load-bearing
below and is read off the producer's own expression (`calibration_cell_exact.py:810`), not assumed.

## 2. The exhaustive refusal — twelve partitions, no retention floor

`calibration_rule_search.py --min-rows 1 --min-share 0` on every dimension the rail carries
(CAL-P123 lesson 7: *"no rule found" and "no rule exists" are different claims*).

| partition | classes | subsets | under bar (pooled) | note |
|---|--:|--:|--:|---|
| `shape` | 5 | 31 | **0** | NO RULE EXISTS |
| `cpdrift` | 5 | 31 | **0** | NO RULE EXISTS |
| `price_moved` | 2 | 3 | **0** | NO RULE EXISTS |
| `policy` | 4 | 15 | **0** | NO RULE EXISTS |
| `policy2` | 3 | 7 | **0** | NO RULE EXISTS |
| `ladder` | 1 | 1 | **0** | degenerate — cell is 100% `z_not_a_ladder` |
| `pair` | 1 | 1 | **0** | degenerate — cell is 100% `z_not_ou_pair` |
| `market_type` | 5 | 31 | 1 | keeps **9 rows** (99.9% deleted) — not a rule |
| `pairtype` | 5 | 31 | 1 | the same 9 rows; `pairtype` collapses onto `market_type` here |
| `age` | 7 | 127 | 8 | every one deletes **79–83%** of the cell |
| `sumband` | 10 | 1023 | 33 | every one deletes **58–71%** of the cell |
| `series` | 177 | 2^177 | **REFUSED** | over `MAX_CLASSES` (22) — a sampled search reporting zero is a false all-clear |

🔴 **And with the holdout applied, `sumband`'s 33 become 0 of 1023.** Split at the cell's own
row-median chunk edge `market_id 29,000,171` (OLD 6,840 rows / NEW 1,640):

```
   ECE  worst½       n   dropped  keep
  2.49    3.09    5375   3105 (36.6%)  bundle|a, bundle|b, bundle|d, field1|a
  2.53    3.17    5469   3011 (35.5%)  + binary|a
  2.78    3.25    5179   3301 (38.9%)  ...
```

The best worst-half is **3.09 against a 3.0 bar**. CAL-P127 lesson 2 — believe the holdout over the
pooled number — and this is the second cell in three sessions where it changed the answer.

⚠️ The split is 80/20, not 50/50: the median was taken over all 5,443 `kalshi/entertainment`
markets, which is not the median over *published* rows. That makes NEW a small half, so its arm
figures are noisier — it does not weaken the refusal (a rule failing on a small half is still
failing) but it would weaken a *pass*, and no pass is claimed.

## 3. What is actually wrong: the price sum contradicts the market's own shape

`sumband` crosses shape with the price sum, and the `field1` arms are monotone:

| arm | n | ECE | gap | reading |
|---|--:|--:|--:|---|
| `field1\|a_sum_le_1.15` | 2,423 | **1.67** | +0.23 | coherent — the **best arm in the cell** |
| `field1\|b_sum_1.15_2` | 574 | 9.21 | +8.63 | |
| `field1\|c_sum_2_5` | 499 | 25.21 | +25.21 | |
| `field1\|d_sum_5_15` | 155 | **47.87** | +47.87 | |

A `field1` is a field where **exactly one outcome won**. Its prices should sum to ~1. Where they
sum to 5–15 instead, every outcome is priced several times too high, and the over-prediction scales
with the excess — 1.67 → 9.21 → 25.21 → 47.87, with `|gap| == ECE` on the last two, meaning the
error is *entirely* one-directional. This is a dose-response, not a big number in a small bucket.

**It reproduces independently on both halves, and the NEW half is worse on every arm:**

| arm | OLD ECE (gap) | NEW ECE (gap) |
|---|--:|--:|
| `field1\|a` | 1.95 (+0.08) | 4.18 (+1.33) |
| `field1\|b` | 8.49 (+7.84) | 13.33 (+11.02) |
| `field1\|c` | 23.13 (+23.13) | 31.26 (+31.26) |
| `field1\|d` | 41.01 (+41.01) | 53.38 (+53.38) |

**The mirror confirms the mechanism rather than repeating it.** A `bundle` is multi-winner, so *its*
prices should sum well above 1 — and the one bundle arm that sums *below* 1.15 is the worst bundle
arm by 2.4×: `bundle|a_sum_le_1.15`, 181 rows, ECE **19.83**, gap **−15.34** — under-prediction,
the opposite sign. Coherent bundles run 4.96–8.40. So the defect is not "high price sums are bad";
it is **the sum disagreeing with the shape**, in whichever direction the disagreement points.

🔴 **The obvious lever is the wrong one, and this is worth remembering.** The eye goes to
`single|a_sum_le_1.15` — 396 rows at ECE **32.46**, by far the biggest per-class number. Dropping
it moves the cell **5.10 → 5.05**. Dropping the whole incoherent-`field1` block (1,228 rows, 14.5%)
moves it 5.10 → **3.99** — a real mechanism, still over the bar. ECE pools *within buckets*, so a
class's own ECE says almost nothing about what removing it does.

## 4. Which markets these are

`artifacts/cal-p129/incoherent-field-census.py` (regenerable, 13 chunks, all returned, exit 0):
**44 series, 257 markets, 3,460 outcomes.** Dominated by music-streaming and chart-position fields:

| series | markets | outcomes | avg price sum |
|---|--:|--:|--:|
| `KXSPOTSTREAMGLOBAL` | 19 | 399 | 7.87 |
| `KXSPOTIFYGLOBALD` | 27 | 376 | 6.20 |
| `KXSPOTIFY2D` | 23 | 343 | 9.53 |
| `KXBBCHARTPOSITIONSONG` | 35 | 338 | 6.46 |
| `KXSPOTIFYARTISTD` | 23 | 337 | 7.57 |
| `KXBBCHARTPOSITIONALBUM` | 30 | 268 | 6.02 |
| `KXTOPALBUM` | 1 | 18 | **17.26** |
| `KXAMERICANIDOL` | 1 | 30 | **13.26** |

Concretely: `KXSPOTSTREAMGLOBAL` runs ~21 candidates per market whose published probabilities sum
to **7.87**. Exactly one wins. So the average candidate is shown at ~**37%** where the realized rate
is **1/21 ≈ 4.8%**. A user reading our page sees seven or eight near-coin-flips for a question that
has one answer.

🔴 **This census's population is BROADER than the published cell** — it applies none of the
producer's exclusions, only `calibration_probability IS NOT NULL AND is_winner IS NOT NULL`. Its
3,460 is an upper envelope. **The published figure is the rail's 1,228 of 8,480 (14.5%)** and the
two must not be confused.

## 5. Recommendation

1. **Do not bank an exclusion rule for `kalshi/entertainment`.** Twelve partitions, holdout-clean
   refusal. It stays on the board — it is ESTABLISHED at σ 4.52 — but it is not exclusion-fixable
   and the conveyor should stop trying.
2. **Route the mechanism to the writer lane** as the same class as gotcha #23 (*independent binary
   markets need display normalization — candidate binaries can sum well over 100%*). These fields
   are ingested as independent binaries and published un-normalized. The fix is at the writer, and
   it improves the **page**, not just the curve.
3. **This partly discharges CAL-P127-2** (*incoherent one-winner `field1` fields, board-wide
   sweep*): the sweep is done for one cell and the shape is now specified well enough to run
   board-wide. `sumband` already carries it — **no new rail dimension is needed.**

## 6. What to push on

1. **"You refused on twelve partitions but `series` was never searched."** True, and it is the one
   real gap. 177 classes is over `MAX_CLASSES`; a sampled search reporting zero would be a false
   all-clear, so it was refused rather than faked. A `series`-family rollup (collapse `KXSPOTIFY*`
   to one class) would make it searchable and is the obvious next attempt — though note the census
   already shows the incoherence is spread across 44 series, so a per-series rule looks unlikely.
2. **The 80/20 holdout split.** Argued above; it can only make a refusal safer, never a pass.
3. **`gap` sign.** The whole §3 reading inverts if `gap` were `win − price`. It is read off
   `calibration_cell_exact.py:810` (`sp - w`), not inferred from the numbers.
