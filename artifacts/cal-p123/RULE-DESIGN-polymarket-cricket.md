# CAL-P123 — `polymarket/cricket` (rank 10): NO RULE EXISTS

**Verdict: REFUSED, and this time the refusal is exhaustive rather than a judgment call.**
Two independent partitions of the cell were searched *completely* — every one of the 127 non-empty
subsets of its name families, and all 1,844 subsets of its shape × price-sum classes retaining at
least 300 rows. **Not one of the 1,971 candidate exclusion rules brings the cell under the 3.0 pp
bar.** The best rule that exists on either partition lands at **4.96 pp while deleting 29% of the
cell**; the best on the family partition lands at **5.45 pp while deleting 76% of it**.

This is not "we did not find a rule." It is "the rule is not there," and the search that says so is
enumerable and re-runnable.

---

## 1. The cell, and the three cheap checks first

| | n | ECE | gap |
|---|--:|--:|--:|
| exact replica (producer's own chain) | 3,246 | 8.15 | −4.67 |
| published payload | 3,252 | 8.11 | −4.61 |
| **delta** | **−6 (−0.18%)** | **+0.04** | **−0.06** |

Curve `q268`, generated `2026-08-29T00:36:47Z`.

**Lesson 3 did not bite, and that is itself worth recording.** The standing budget for this rail on
Polymarket is *"5–6% short"* — measured −5.06% on soccer and −5.7% on baseball. On cricket it
reproduces to **−0.18%**, tighter than most of its Kalshi runs. The shortfall is therefore **not a
property of the source**; it is a property of particular cells, and a queue that discounts a
Polymarket claim by 5% on principle will now be wrong by 5% on this one. *Budget for the shortfall;
do not assume it.*

**Lesson 5, `--by series`: the instrument could not answer, and the reason is the finding.**
`SERIES_EXPR` is `SPLIT_PART(fm2.external_id, '-', 1)`. On Kalshi that is the series ticker — the
unit a rule can name. On Polymarket it is the numeric Gamma event id, so the fold returned **1,148
classes, 1,086 of them one row.** A dimension that resolves to one row per class is the row list
with extra steps. This is why rank 10 sat "diagnosed, no rule built" for twenty days: **the rail
had no way to name a Polymarket market family.** `calibration_family_fold.py` (new, 27 guards)
exists to close that, and section 3 is the first table it produced.

**Lesson 4, `calibration_cluster_sigma`, 2,000 resamples, seeded:**

```
3,246 rows / 1,086 markets / 2.99 rows per market
  row grain (the board today)         SE 0.878   sigma 5.87
  market grain (perfect-corr bound)   SE 1.517   sigma 3.39
  cluster bootstrap (MEASURED)        SE 0.607   sigma 8.48
  bootstrap ECE 95% interval [7.39, 9.74] pp     design effect 0.48
```

**ESTABLISHED at 8.48σ** — the highest measured σ of any cell folded on this rail, with a bootstrap
lower bound of 7.39 pp against a 3.0 bar. The cell is real; the question was only ever what to do
about it.

Design effect **0.48** is a *fourth* distinct value (1.79 / 0.76 / 0.76 / 0.48). Four cells, four
answers, in both directions. The recommendation already with Alex — report `effective_n` and
`design_effect` as a pair, do not redefine the denominator — keeps accumulating cases.

---

## 2. What the standing structural rule does here, and why it is not enough

`--by sumband` (shape × published-price-sum), the cross RULE E turns on:

| class | n | share | ECE | gap |
|---|--:|--:|--:|--:|
| `field1\|a_sum_le_1.15` | 2,098 | 64.6% | **5.75** | +0.58 |
| `bundle\|c_sum_2_5` | 461 | 14.2% | 22.35 | −21.39 |
| `bundle\|b_sum_1.15_2` | 203 | 6.3% | 23.96 | −23.78 |
| `field1\|c_sum_2_5` | 140 | 4.3% | 13.45 | +13.21 |
| `bundle\|a_sum_le_1.15` | 123 | 3.8% | 26.61 | −24.49 |
| `field1\|b_sum_1.15_2` | 70 | 2.2% | 15.83 | +13.79 |
| `binary\|b_sum_1.15_2` | 60 | 1.8% | 17.33 | −0.07 |
| `binary\|a_sum_le_1.15` | 50 | 1.5% | 14.28 | −5.32 |
| `single\|a_sum_le_1.15` | 29 | 0.9% | 42.00 | −42.00 |
| `binary\|c_sum_2_5` | 8 | 0.2% | 34.87 | +12.12 |
| `single\|b_sum_1.15_2` | 4 | 0.1% | 20.75 | −20.75 |

RULE E's structural test (published prices sum > 1.15 ⇒ not a partition) removes 946 rows. **The
cell does not move**, because the clean remainder it hands back — a genuine partition that realized
exactly one winner, 64.6% of the cell — **is itself at 5.75 pp, nearly twice the bar.**

That is the whole shape of this cell in one line: **its control fails.** Every exclusion rule is an
argument that the rows it keeps are the good ones. Here there are no good ones to keep.

---

## 3. The family fold — the new dimension, and the answer

Polymarket puts the market family in the text after the last `` - `` of the name:

```
T20 Series Hong Kong vs Kuwait: Hong Kong, China vs Kuwait - Most Sixes
~~~~~~~~~~~~~ series ~~~~~~~~~~~ ~~~~~~~~ fixture ~~~~~~~~   ~ family ~
```

`--by family`, with the row-balanced holdout at `market_id 22658573` (1,622 OLD / 1,624 NEW; split
point taken from `cluster_rows` per lesson 2, not from the bare median market id):

| family | n | share | ECE | gap | OLD ECE | NEW ECE |
|---|--:|--:|--:|--:|--:|--:|
| `z_no_dash_suffix` | 1,124 | 34.6% | 14.65 | −12.36 | 14.34 | 15.42 |
| `Toss Match Double` | 693 | 21.3% | 5.88 | +0.05 | 6.69 | 6.68 |
| `Team Top Batter` | 676 | 20.8% | 7.11 | −0.33 | 6.58 | 7.94 |
| `Most Sixes` | 625 | 19.3% | 6.89 | −0.49 | 7.09 | 7.14 |
| `Completed match?` | 55 | 1.7% | 19.33 | −12.75 | — | 19.33 |
| `Who wins the toss?` | 48 | 1.5% | 8.06 | +8.06 | — | 8.06 |
| `More Markets` | 25 | 0.8% | 35.12 | −18.20 | 47.24 | 29.41 |

**Every family fails the bar, pooled and on both holdout halves.** The best family in the cell is
`Toss Match Double` at 5.88 pp — and it is 5.88 on a cell where the bar is 3.0, 6.69 on OLD and
6.68 on NEW. The refusal is not a small-sample artifact; it is the same answer three times.

Note the two regimes side by side. `Toss Match Double`, `Team Top Batter` and `Most Sixes` — 61.4%
of the cell between them — carry gaps of **+0.05, −0.33, −0.49**: prices that are right on average
and wrong bucket by bucket. That is **two-sided error, the honest kind**, and it is invisible to
every gap-driven fold this lane runs. It is the same signature CAL-P122 parked as CAL-P122-2.

### The exhaustive search

All 127 non-empty subsets, pooled (`artifacts/cal-p123/holdout-family.json`):

```
subsets under the 3.0 bar:  0 of 127

best 4:
  ECE=5.45  n=766   keep = More Markets, Toss Match Double, Who wins the toss?
  ECE=5.48  n=741   keep = Toss Match Double, Who wins the toss?
  ECE=5.88  n=693   keep = Toss Match Double
  ECE=5.92  n=718   keep = More Markets, Toss Match Double
best retaining >= half the cell:
  ECE=6.36  n=2067  keep = everything except z_no_dash_suffix and Completed match?
```

The global optimum over the family partition deletes **76.4% of the cell to land at 1.8x the bar.**

All 1,844 shape × price-sum subsets retaining ≥300 rows (`holdout-sumband.json`) — a partition with
opposite-signed arms, so pooled cancellation was possible and was searched for:

```
subsets under the 3.0 bar:  0 of 1,844
best:  ECE=4.96  n=2,298  keep = field1|a_sum_le_1.15, field1|c_sum_2_5, binary|b_sum_1.15_2
```

**4.96 pp is the best exclusion rule that exists for this cell on either partition.** It is 1.65x
the bar, it is not a rule anyone can state in a sentence a reader would accept, and it would have
to be disclosed.

---

## 4. What the error actually is — two mechanisms, both named, neither removable

### 4a. Undifferentiated containers — 10.4% of the cell

Polymarket serves a game event as nested sub-markets keyed by `condition_id` (gotcha #18). When
they are flattened into one `futures_market` without being decomposed, the container's name is
copied onto every outcome:

```
market   Indian Premier League: Rajasthan Royals vs Sunrisers Hyderabad
outcome  Indian Premier League: Rajasthan Royals vs Sunrisers Hyderab   0.565  lose
outcome  Indian Premier League: Rajasthan Royals vs Sunrisers Hyderab   0.495  WIN
outcome  Indian Premier League: Rajasthan Royals vs Sunrisers Hyderab   0.595  lose
```

Three prices summing to 1.655, three identical labels, and **nothing in the row says which side
each price is for.** That is not a mispriced market — it is a market with no readable claim, and it
is on the calibration curve as three forecasts.

`--by outcomenames` (new dimension; `COUNT(DISTINCT name)` per market, not a truncation-length test):

| class | n | share | ECE | gap |
|---|--:|--:|--:|--:|
| `c_distinct` | 2,821 | 86.9% | **7.33** | −2.93 |
| `a_undifferentiated` | 337 | 10.4% | 17.93 | −16.56 |
| `b_partly_duplicated` | 55 | 1.7% | 18.00 | −0.20 |
| `d_lone_outcome` | 33 | 1.0% | 39.42 | −39.42 |

The defect is real, one-sided and worth fixing **in the writer**. It is not the cell's mechanism:
removing all 425 affected rows leaves 2,821 rows at **7.33**, still 2.4x the bar.

### 4b. The rest is Polymarket being wrong — 86.9% of the cell at 7.33

After the bundles, the undifferentiated containers, the lone claims and the duplicated labels are
all removed, what remains is 2,821 rows of ordinary, well-formed, partition-priced cricket markets
whose prices sum to one, whose outcomes are distinctly named, whose gap is −2.93 — and whose
bucket-by-bucket error is 7.33 pp.

**No population defect explains that. It is forecast error at the venue.** `polymarket/cricket` is
the first cell on this board where the evidence says the *market* is miscalibrated rather than our
pipeline, and it is why no exclusion rule exists: you cannot exclude your way out of a cell whose
clean core is the problem.

---

## 5. 🔴 The 12-CAL defect is NOT Kalshi-specific — measured here on Polymarket

`d_lone_outcome` — the ungrouped single-outcome markets, `market_type = 'unshaped'`, the `single`
shape class; three folds, the same 33 rows:

```
lone-claim class: n=33  winners=33  losers=0  mean price 0.6058

bucket 3 (30-40%):  2 rows,  2 winners
bucket 4 (40-50%):  6 rows,  6 winners
bucket 5 (50-60%): 13 rows, 13 winners
bucket 6 (60-70%):  3 rows,  3 winners
bucket 7 (70-80%):  4 rows,  4 winners
bucket 8 (80-90%):  1 row,   1 winner
bucket 9 (90-100%): 4 rows,  4 winners
```

**Every bucket is 100% winners, from the 30s up.** That is not a forecast record — it is a filter.
It is exactly the defect CAL-P122 found on `kalshi/entertainment` (395/395), and finding it here
settles a question that document could not: **`clean_vms.has_winner >= 1` is evaluated over the
virtual market and is source-agnostic.** An ungrouped single-outcome market publishes if and only
if it won, on Kalshi *and* on Polymarket. 12-CAL is a curve-wide defect, not a Kalshi quirk.

**It does not change this cell's verdict, and the bound is worth stating rather than assuming.** At
33 rows / 1.0%, restoring the dropped losses moves the cell within **[7.5, 9.0] pp** under the most
extreme assumptions in either direction — nowhere near 3.0. Lesson 6's hazard is that a *passing*
rule can fail on the corrected population; here there is no passing rule to invalidate. The exact
census is parked (CAL-P123-1) rather than run, because it is a ~90-minute single-threaded
Polymarket sweep that cannot change any verdict in this document.

---

## 6. What is owed

**14-CAL (new, Alex):** `polymarket/cricket` is 8.15 pp against a 3.0 bar, ESTABLISHED at 8.48σ,
and **exhaustively proven to admit no exclusion rule.** It is 16,618 excess-outcomes — rank 10 of
20. Three options, (a) recommended:

- **(a) Rule it a DISCLOSED KNOWN-BAD cell and leave every row on the curve.** Nothing is hidden,
  the headline carries the error honestly, and the page gains a second, truthful category of cell:
  *"we measured this and the venue is wrong"*, distinct from *"we excluded this because our
  pipeline mangled it."* Costs 0.00 pp on the headline and adds a row to the disclosure surface.
- **(b) Exclude the whole cell with disclosure.** Buys the headline ~0.2 pp; costs a whole sport,
  and sets the precedent that a cell we cannot repair is a cell we delete. This lane has ruled
  twice that an exclusion needs a *stated cause that is true*; "the venue is bad at cricket" is
  true but it is not a population defect, and every prior exclusion on this board was.
- **(c) Take the 4.96 pp rule.** Not recommended and recorded only so the option is on the page: it
  deletes 29% of the cell, still fails the bar, and cannot be stated in a sentence.

**12-CAL, evidence appended:** the lone-claim filter fires on Polymarket too. Section 5.

**CAL-P123-1 (parked):** the exact missing-loser census on `polymarket/cricket`'s 33-row lone-claim
class. Bounded above as immaterial to this verdict; run it when the board re-measures after 12-CAL
is decided, not before.

**CAL-P123-2 (parked):** the two-sided error in `Toss Match Double` / `Team Top Batter` /
`Most Sixes` — 1,994 rows, 61.4% of the cell, gaps of +0.05 / −0.33 / −0.49 against ECEs of
5.88 / 7.11 / 6.89. Same class of thing as CAL-P122-2 and now on a second source. **Two cells on
two venues now say the same thing: the residual error on this board, after every population defect
is removed, is two-sided bucket error that no gap-driven fold can see.** That is a measurement-lane
question about what instrument this board is missing, and it is bigger than either cell.

---

## 7. Reproduce

```bash
source ~/.claude/.env
python3 backend/scripts/calibration_cell_exact.py    --source polymarket --category cricket --by sumband \
        --holdout-at 22658573 --out artifacts/cal-p123/holdout-sumband.json
python3 backend/scripts/calibration_family_fold.py   --source polymarket --category cricket --by family \
        --holdout-at 22658573 --out artifacts/cal-p123/holdout-family.json
python3 backend/scripts/calibration_family_fold.py   --source polymarket --category cricket --by outcomenames
python3 backend/scripts/calibration_cluster_sigma.py --source polymarket --category cricket \
        --out artifacts/cal-p123/sigma-polymarket-cricket.json
```

Each fold is 70–150 s. The σ run is ~145 s plus the bootstrap. Guards:
`backend/tests/test_calibration_family_fold_p123.py`, 27 tests.
