# CAL-P126 — 16-CAL, sized on the whole curve, and what it does to 1.89

**This is `0-PHANTOM` option (a) MEASURE FIRST, which is the written default in
`YOUR-TURN.md` and Alex has not answered. Nothing was fixed, nothing shipped, no
ruling-009 exception taken. `precompute_calibration.py` is untouched;
`git diff origin/master -- backend/app frontend` is empty on this branch.**

CAL-P125 found that `deduped` — the CTE the producer's own docstring calls *"the
final published population"* — publishes the same outcome more than once, on two
cells, and isolated the cause to `vm_stats` grouping by five columns while
`ranked_outcomes` joins `clean_vms` on two. It could not say how big it was
anywhere else, because the only instrument that could see it cost a Stage A
roster read per cell.

This measures the whole curve.

---

## 0. The answer, and the four things that changed

**The curve flatters itself: `1.89 → 2.31` on the closing line, `1.54 → 1.62` on
the opening price, from de-duplicating 53.5% of the headline population. Nine of
the ten probability bands get worse. The direction was the same on all twelve
cells measured.** §4 is the arithmetic; §5 is what is still unmeasured and why no
extrapolation is offered.

And four things that were not known this morning:

1. **The curve's clean half is bigger than expected, and it is PROVED clean, not
   sampled.** 70 of the curve's 103 futures cells cannot carry a phantom row at
   all. Every cell was scanned; none timed out.
2. **`mutually_exclusive` is the only column that fans out — on all 103 cells.**
   CAL-P125 isolated it on one unit of one cell, which under lesson 1 was a
   hypothesis. It is now a measurement over 848,222 resolved markets.
3. **The published headline is computed over the futures half ONLY** — 776,022
   of 913,851 outcomes — and the futures half is exactly the half that carries
   the defect. There is no dilution from a clean 15%. This was not known before
   today and it is the reason a per-cell delta translates into a headline delta
   at close to full strength.
4. **The duplicate copies of an outcome AGREE** — same bucket, same price, same
   `is_winner`, same `price_moved` — on every cell measured exactly so far. That
   was an open question CAL-P125 flagged and could not answer, and the answer is
   the good one: de-duplication is a pure RE-WEIGHTING, not a re-pricing.

---

## 1. Scope, stated rather than inferred

`futures_markets` holds three sources and the curve serves seven:

| source | resolved markets | published outcomes | carries 16-CAL? |
|---|--:|--:|---|
| `polymarket` | 602,303 | 306,412 | yes |
| `kalshi` | 245,604 | 469,574 | yes |
| `datagolf` | 315 | 36 | yes (scanned clean) |
| `odds_api_bookmaker` | — | 96,026 | **no — different chain** |
| `odds_api` | — | 16,688 | **no** |
| `odds_api_totals` | — | 12,705 | **no** |
| `odds_api_spreads` | — | 12,410 | **no** |

The four `odds_api*` sources publish **137,829 outcomes, 15.1% of the curve**,
through a chain that has no `clean_vms` in it. Scanning them returns zero rows,
and zero rows is a response shape, not an absence (gotcha #53) — so the scan
names them as OUT OF SCOPE and the guard suite pins the list.

**And they are out of scope for the headline too, which is the new part.**
`price_moved` is NULL on 890 of the served payload's 1,963 buckets, carrying
**exactly 137,829 outcomes — those four sources to the row.** The producer's
`_cohort_mce` compares `b.get("price_moved") != pred`, so a NULL bucket joins
*neither* the closing-line cohort nor the opening-price one.

> **`mce_closing_line = 1.89` and `mce_opening_price = 1.54` are averages over
> the futures half and nothing else.**

That is worth stating twice because the intuition it replaces is the comforting
one. A defect confined to 84.9% of the rows sounds like it gets diluted by the
other 15.1%; it does not, because the other 15.1% is not in the number.

*(This was found the expensive way and the guard suite records it: the
reproduction in `calibration_phantom_curve.py` was first written as
`bool(b.get("price_moved")) != pred`, which sweeps all 890 NULL buckets into the
`False` cohort and reports `mce_opening_price` as **1.06** instead of 1.54 — a
clean, plausible, well-formed table that is wrong by half a point. The test that
caught it reproduces the SERVED headline from the SERVED buckets, which is the
only check that could have.)*

---

## 2. The free scan — which cells CANNOT be phantom

`clean_vms` is `vm_stats` filtered, and a filter cannot create a grain. So a
virtual question whose markets all agree on `(category, is_grouped,
mutually_exclusive)` yields at most one `clean_vms` row and **cannot** fan out,
whatever the filter does. Counting those combinations needs only
`virtual_market` — where Stage A already stops — so a cell costs one query of a
few seconds instead of a fold.

The asymmetry is the point: **a clean scan is a proof, a dirty scan is only a
queue position.**

```
SCAN — 103 cells over 3 futures sources (848,222 resolved markets)

  PROVABLY CLEAN cells                 70  (47,370 markets)
  cells where phantom is possible      33  (800,852 markets)
  cells that could not be scanned       0  (0 markets)
```

Full per-cell table: `artifacts/cal-p126/scan.json`.

### 2a. It is `mutually_exclusive`, everywhere, and nothing else

The scan counts the three grouped-but-not-joined columns separately, because
CAL-P125's isolation was one unit of one cell and lesson 1 says that is a
hypothesis until the rail scores it. Over all 103 cells:

| fanning column | cells where it fans |
|---|--:|
| `mutually_exclusive` | **33** |
| `category` | **0** |
| `is_grouped` | **0** |

and `multi_vms == mex_vms` **exactly**, cell by cell. The hypothesis is now a
whole-curve measurement, and the fix surface is one column rather than three.

### 2b. THE SCAN SIZES NOTHING — a correction this report had to make to itself

The scan's first output reported a `max_phantom_pct` per dirty cell. **It was not
a bound, it has been removed, and the exact folds beat BOTH of its replacements
too:**

| cell | questions that fan out | markets inside those questions | **actual phantom rows** |
|---|--:|--:|--:|
| `kalshi/hockey` | 25.21% | 67.32% | **47.08%** |
| `kalshi/basketball` | 5.19% | **35.39%** | **43.11%** ← beats both |
| `polymarket/basketball` | 13.22% | 81.67% | **43.44%** |
| `polymarket/cricket` | 16.87% | 43.00% | **12.85%** |

Three of four exceed the question-level rate. `kalshi/basketball` exceeds the
market-weighted one as well — which killed this report's second attempt at a
ceiling, three cells after it killed the first.

**So: the scan says WHETHER, never HOW MUCH.** Both percentages are coverage
figures and both are published under names that say only what they count. The
one exact claim is untouched, and it is the one the scan exists for:
`combos == 1` ⇒ **zero phantom, proved.**

The reason neither works is itself a finding rather than an arithmetic slip:

> **The virtual questions that fan out are systematically the big ones — and
> "big" is not the same measure as "many markets".**

A question carries two `mutually_exclusive` values precisely when it bundles
claims of different shapes — a game group holding a moneyline and a player prop
— and that is also what makes it large. On `polymarket/basketball`, 13.2% of the
questions hold 81.7% of the markets. On `kalshi/basketball`, **5.2% of the
questions hold 35.4% of the markets and account for 43.1% of the published
rows**: the fanning questions carry more outcomes per market than average *and*
fan to higher multiplicity, and neither of those is visible before the fold.

*(CAL-P124's lesson 8 — "a warning that fires is not a warning that sized it" —
read the right way round, twice. The instrument fired correctly both times and
this report mis-stated the size on its first pass and then mis-stated the
direction of the error on its second. The measured column is the only one worth
reading.)*

### 2c. Cells that matter to the board, and which side they landed on

The five banked designs and the conveyor's next named cell:

| board rank | cell | scan verdict |
|--:|---|---|
| 1 | `polymarket/baseball` | phantom possible — 51.5% of questions, **95.6% of markets** |
| 2 | `kalshi/economics` | **PROVABLY CLEAN** |
| 3 | `polymarket/esports` | phantom possible — 45.1% of questions, **92.8% of markets** |
| 6 | `kalshi/crypto` | **PROVABLY CLEAN** |
| 8 | `kalshi/golf` | **PROVABLY CLEAN** |
| 17 | `kalshi/tech` | **PROVABLY CLEAN** |

**Four of the six need no re-bench at all** — their populations never counted a
row twice, so CAL-P125's "all five were benched on the phantom-inflated
population" is now three-of-five reduced to two: ranks 1 and 3. And
`kalshi/golf`, the conveyor's next named cell, is clean, so its rank-8 excess
figure means what it says.

---

## 3. The exact cells

`--cell` re-measures each published bucket twice — as shipped, and with each
outcome worth exactly 1 — on the whole-vm rail's frozen roster, so a virtual
question is never split. (Splitting one would split its own duplicate copies
apart and report the phantom as absent; the instrument raises by name rather
than approximating.)

**Both cells CAL-P125 measured reproduce to the row, on a different tail:**

| cell | published rows | distinct outcomes | phantom | CAL-P125 said |
|---|--:|--:|--:|---|
| `polymarket/basketball` | 13,116 | 7,419 | **43.44%** | 43.44% ✓ |
| `polymarket/cricket` | 3,252 | 2,834 | **12.85%** | 12.85% ✓ |

That is an independent cross-check of the new instrument against the existing
`calibration_whole_vm_fold.py --phantom`, and it is worth having: lesson 9 says a
self-check proves the rail and not the population, so a second rail agreeing on
the *population's* self-contradiction is the strongest evidence available that
the contradiction is real and not an artifact of how it is counted.

### 3a. The copies agree — and that closes CAL-P125's open question

CAL-P125 could not say whether de-duplication was safe to model as a
re-weighting, because the `clean_vms` rows that produce the copies carry
different `eligible` aggregates and `eligible` is read downstream by
`mode_prices` and the field-completeness gate. Two copies of one outcome could
in principle be published at two prices, in two buckets, on two sides of
`price_moved`.

The instrument does not assume. It counts every disagreement:

| cell | copies at 2 buckets | at 2 prices | at 2 winner values | at 2 `price_moved` |
|---|--:|--:|--:|--:|
| `polymarket/basketball` | 0 | 0 | 0 | 0 |
| `polymarket/cricket` | 0 | 0 | 0 | 0 |

**Zero on every axis.** So a phantom row is an exact copy, de-duplication moves
weights and never prices, and the headline delta below is arithmetic rather than
a model.

*(Had any of these been non-zero it would have been a second and worse finding —
the curve publishing one outcome at two prices — which is precisely why they are
counted rather than argued away.)*

---

## 4. What it does to the published number

The served payload publishes every bucket it aggregated, so its headline is
reproducible from its own body — verified exactly, `1.89` and `1.54` both to the
published digit. That is what makes a partial answer honest: a cell measured
today can be substituted into the served aggregate without re-measuring the
other 102, and the number that comes out is the number the page would show if
only that cell were de-duplicated.

**The substitution is a RATIO, not a replacement.** The rail reproduces a cell to
within a fraction of a percent, not exactly (CAL-P125: −0.14% on basketball,
+0.00% on cricket), and scaling the payload's own bucket by the rail's
`dedup / ship` ratio cancels any per-bucket factor common to both measurements —
which is what the rail's shortfall is. Substituting absolute numbers would report
rail error as phantom damage.

`winners` scales on the **winner** ratio, not the row ratio. A bucket whose
duplicated rows are disproportionately winners moves its actual rate, and that
movement is the entire mechanism by which de-duplication can change a
calibration error rather than just an `n`.

### 4a. Coverage of the headline population

| | outcomes | share of the headline |
|---|--:|--:|
| headline cohorts total (`price_moved` not NULL) | 776,022 | 100% |
| in **provably clean** cells | 93,803 | **12.1%** |
| in phantom-possible cells | 682,219 | 87.9% |

### 4b. The delta

<!-- CAL-P126-RESULTS -->

Every cell below was measured exactly, on the whole-vm rail, over every unit of the cell.

| cell | headline weight | published rows | distinct outcomes | **phantom** | copies agree |
|---|--:|--:|--:|--:|:--:|
| `kalshi/baseball` | 169,090 (21.8%) | 169,425 | 99,084 | **41.52%** | yes |
| `kalshi/basketball` | 110,758 (14.3%) | 109,702 | 62,407 | **43.11%** | yes |
| `kalshi/hockey` | 33,145 (4.3%) | 32,946 | 17,435 | **47.08%** | yes |
| `polymarket/weather` | 24,333 (3.1%) | 25,739 | 25,648 | **0.35%** | yes |
| `kalshi/soccer` | 21,951 (2.8%) | 23,388 | 20,559 | **12.1%** | yes |
| `polymarket/basketball` | 13,135 (1.7%) | 13,116 | 7,419 | **43.44%** | yes |
| `polymarket/economics` | 12,882 (1.7%) | 12,989 | 8,327 | **35.89%** | yes |
| `kalshi/football` | 9,384 (1.2%) | 10,357 | 8,815 | **14.89%** | yes |
| `polymarket/politics` | 6,500 (0.8%) | 6,296 | 4,612 | **26.75%** | yes |
| `polymarket/golf` | 6,463 (0.8%) | 6,443 | 4,308 | **33.14%** | yes |
| `polymarket/entertainment` | 4,132 (0.5%) | 4,147 | 3,019 | **27.2%** | yes |
| `polymarket/cricket` | 3,252 (0.4%) | 3,252 | 2,834 | **12.85%** | yes |
| **total measured** | **415,025 (53.5%)** | **417,800** | **264,467** | **36.70%** | |

**65.6% of the headline population is now settled** — 12.1% proved clean by the scan and 53.5% measured exactly. The rest is unmeasured, not clean (§5).

### The headline

| | closing line | opening price |
|---|--:|--:|
| published `/api/calibration` | **1.89** | **1.54** |
| reproduced from its own buckets | 1.89 | 1.54 |
| with the measured cells de-duplicated | **2.31** | **1.62** |
| **delta** | **+0.42** | **+0.08** |

240 of the payload's 1963 published buckets were substituted; 153,420 phantom rows were removed from a curve of 913,851.

### Where the move comes from

The headline is an unweighted mean over these ten rows, so it matters whether a move is one bucket or all of them.

| bucket | n now | n de-duplicated | \|err\| now | \|err\| dedup | move |
|--:|--:|--:|--:|--:|--:|
| 0 | 85,691 | 75,222 | 0.779 | 0.849 | **+0.070** |
| 1 | 50,720 | 38,054 | 0.240 | 0.548 | **+0.308** |
| 2 | 46,841 | 34,095 | 1.082 | 1.883 | **+0.802** |
| 3 | 43,728 | 32,419 | 2.226 | 2.920 | **+0.694** |
| 4 | 49,641 | 37,789 | 5.698 | 6.741 | **+1.043** |
| 5 | 44,444 | 33,638 | 1.453 | 1.900 | **+0.447** |
| 6 | 27,637 | 19,240 | 2.864 | 3.207 | **+0.343** |
| 7 | 24,779 | 16,804 | 3.303 | 3.447 | **+0.144** |
| 8 | 18,887 | 13,272 | 1.062 | 1.605 | **+0.543** |
| 9 | 16,175 | 13,647 | 0.155 | 0.026 | **-0.128** |

**9 of the 10 buckets get worse.** The move is not one bucket's artifact.

---

## 5. What is still unmeasured, said out loud

The remaining phantom-possible cells are unmeasured, **not clean, and not
bounded** — §2b is the reason, and it is worth restating because it is the
easiest mistake to make with `scan.json` open. Both of its percentages are
coverage figures. Neither bounds the phantom row rate in either direction:
`kalshi/hockey` looked like 25% of questions and came in at **47%** of rows;
`kalshi/basketball` looked like 35% of markets and came in at **43%**.

**No unmeasured cell may be assumed small because its coverage looks small.**

`polymarket/soccer` is the single largest unmeasured contributor at 106,803
headline outcomes (13.8%), with 24.2% of its questions and 83.6% of its markets
inside fanning questions. It is also the most expensive: 191,301 resolved
markets, and Stage A is charged per market at roughly 21 ms — call it 70 minutes
before a single bucket is read.

---

## 6. The recommendation — CHANGED, from (a) measure to (b) fix

`0-PHANTOM` offered three options and recommended **(a) MEASURE FIRST**. That was
the right recommendation when nobody could say whether the defect mattered.
It is now answered, so the recommendation in the item has been rewritten to
**(b) FIX IT**, and the reasoning is worth stating plainly because it is a
reversal:

* **The thing (a) existed to find out is found out.** Four tenths of a point on
  the headline from half the rows, nine of ten bands worse, and the direction the
  same on all twelve cells. That is not a rounding issue and further measurement
  will not change what kind of thing it is.
* **The fix is one join**, not three columns and not a rewrite — `mutually_exclusive`
  is the only fanning column on all 103 cells.
* **There is a regression control ready.** `polymarket/cricket` reproduces the
  published cell exactly (+0.00%) on the whole-vm rail, and the CAL-P125 guard
  suite already pins the fan-out deliberately, so fixing it fails a test by name
  and carries the re-measure instruction.
* **The falsifier window is already lost this cycle** — 3 of 18 clean, 9
  reachable against the 22 of 24 needed — so a fix that restarts it costs less
  this week than any other week.

**None of that is a freeze exception, and this session did not take one.** Ruling
009 freezes commits to `precompute_calibration.py`; every mode in this report is
read-only and the frozen file is imported, never edited. The exception is Alex's
to grant and the item says so.

**If he says nothing, the standing default remains (a):** keep folding cells,
biggest first, starting with `polymarket/soccer`. §5 is the queue.
