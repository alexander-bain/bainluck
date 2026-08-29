# CAL-P121 — rank 6, `kalshi/crypto`: the cell is 99.5% metal

**Pillar: TRUTH. Ship: the calibration page stops publishing an accuracy score for a
category this product deliberately does not carry.**

Status: **designed, benched on the producer's own chain, holdout-split, NOT BUILT, worth
0.00 pp today.** Banked for freeze-lift day. Nothing in this document changes a published
row; `git diff origin/master -- backend/app/ frontend/` is empty on this branch.

| | |
|---|---|
| board rank | 6 of 14 (corrected board, CAL-P120 §6g) |
| published cell | `kalshi/crypto` — ECE **7.60** pp, n **4,565**, gap **+1.84** |
| class / bar | C_exchange_standalone / **3.0** pp |
| excess | **+4.60** pp = **20,999** excess-outcomes |
| curve | `2026-08-29T00:36:47Z`, population `q268` |

---

## 0. The two cheap checks first, because CAL-P120 paid for them

**Can the rail reach the cell?** Yes, and better than it has reached anything else on this
board. `futures_markets` holds 255,104 `kalshi` rows, so `calibration_cell_exact` — which
folds the `futures_markets`-rooted chain — is in its own domain here.

| cell | exact rail | payload | Δn |
|---|---|---|--:|
| **`kalshi/crypto`** | **4,566 / 7.61 / +1.83** | 4,565 / 7.60 / +1.84 | **+0.02%** |
| `kalshi/economics` (CAL-P114) | 28,738 / 5.29 / −0.47 | 28,613 / 5.29 / −0.47 | +0.55% |
| `polymarket/soccer` (CAL-P118) | — | — | −5.06% |
| `polymarket/baseball` (CAL-P117) | — | — | −5.7% |

+0.02% is the tightest reproduction the futures-rooted rail has achieved. Every number
below is on that rail.

**Is the cell's σ a claim about independent observations?** This is CAL-P120's lesson 4 and
it is the check that took six cells off this board. Here it needed an instrument that did
not exist, because CAL-P120's correction does not transfer — see §1.

---

## 1. The σ correction, measured — and it does NOT rescue this cell

CAL-P120 corrected `odds_api_bookmaker` by **dedup**: eighteen bookmaker rows carry one
byte-identical outcome, so collapsing them is exact. A Kalshi threshold ladder is not a
copy. `KXGOLDH-26AUG0210` publishes "gold above $3,340", "above $3,350", "above $3,360" as
separate rungs at *different prices* with *different outcomes*, all settled by one gold
print. They are **correlated, not duplicated**, and there is no grain at which they
collapse without inventing a price.

So the correction has to *measure* the correlation instead of assuming a value for it:
**`backend/scripts/calibration_cluster_sigma.py`** (new file, read-only, 41 guards / 10 mutations)
resamples the cell's **markets** with replacement and recomputes the cell's own ECE on each
resample, 2,000 times, seeded. It adds exactly one dimension (`marketid`) to the proven
rail's table and re-implements nothing — a guard test asserts the registration is additive
and rebinds none of the rail's own dimensions.

```
kalshi/crypto — 4,566 published rows / 625 distinct markets / 7.31 rows per market

  basis                                 SE pp    sigma
  row grain (the board today)           0.740     6.23
  market grain (perfect-corr bound)     2.000     2.31
  cluster bootstrap (MEASURED)          0.645     7.14

  bootstrap ECE 95% interval  [6.51, 9.04] pp      design effect  0.76
```

**The cell is ESTABLISHED and it is not close.** The bootstrap's own 95% interval has a
lower bound of **6.51 pp against a 3.0 pp bar** — the cell clears its bar without reference
to any standard-error convention at all. It also clears on the pessimistic
perfect-correlation bound (2.31σ). This is the opposite of CAL-P120's six cells, and the
difference is measured rather than asserted.

### 🔴 The finding this hands back to Alex: criterion 3's error has no fixed direction

CAL-P114 §3a flagged that `50/√n` **overstates** significance on bundle-dominated cells and
estimated `kalshi/economics` at "about 2.3σ" by substituting the market count for `n`. That
flag is still open (PARKED CAL-P114-3, and CAL-P120-2 is the same defect). Measured on both
cells:

| cell | rows | markets | rows/mkt | σ_row (board) | σ_market (bound) | **σ measured** | design effect |
|---|--:|--:|--:|--:|--:|--:|--:|
| `kalshi/economics` | 29,046 | 2,032 | 14.29 | 7.60 | 2.01 | **5.68** | **1.79** |
| `kalshi/crypto` | 4,566 | 625 | 7.31 | 6.23 | 2.31 | **7.14** | **0.76** |

> **Why `kalshi/economics` reads 29,046 / 5.23 here and 28,738 / 5.29 in §6b.** Both are the same
> rail on the same cell; the difference is **population drift** between CAL-P114's sweep and this
> one (+1.51% against the current payload's 28,613, where CAL-P114 measured +0.55%). Nothing has
> shipped into the producer since 2026-08-13, so the cell has simply grown. The σ conclusion is not
> sensitive to it: at CAL-P114's own n and ECE the design effect and the ordering are unchanged.

Two things a reader must not skip:

1. **CAL-P114 §3a's estimate was pessimistic by 2.5x** — it predicted ~2.3σ on
   `kalshi/economics` and the measured answer is 5.68σ. Its *direction* was right on that
   cell (design effect 1.79 > 1, the clustering really does inflate the variance) but the
   *magnitude* it quoted came from assuming perfect within-market correlation, which is a
   bound and not a measurement.
2. **On `kalshi/crypto` the direction REVERSES.** Design effect **0.76 < 1**: the board's
   `50/√n` is *conservative* here, not anti-conservative. `cell_se_pp` is the maximum-variance
   (p = 0.5) binomial SE, and this cell's mass sits in the 0–10% and 90–100% deciles where
   the real variance is far lower. That conservatism outweighs the clustering.

**So `50/√n` is wrong in both directions and which one dominates is a per-cell empirical
fact.** No single re-definition of criterion 3's denominator is correct — substituting the
market count would have wrongly demoted `kalshi/economics` from 7.60σ to 2.01σ (a hair over
the gate) and would have understated `kalshi/crypto`. **Neither cell changes verdict**, which
is the reassuring half: the gate has so far been robust to its own bad denominator. The
recommendation is in §7.

---

## 2. The cell is 99.5% metals, and exactly ONE row of it is cryptocurrency

Folded by Kalshi series ticker — the market family, which is the unit a rule can name:

| series | n | share | ECE | gap | what it is |
|---|--:|--:|--:|--:|---|
| `KXSILVERH` | 1,619 | 35.5% | 9.23 | +0.54 | silver price, hourly |
| `KXGOLDH` | 1,520 | 33.3% | 12.61 | +1.93 | gold price, hourly |
| `KXGOLDD` | 481 | 10.5% | 4.72 | +3.18 | gold price, daily |
| `KXSILVERD` | 346 | 7.6% | 4.46 | +1.13 | silver price, daily |
| `KXGOLDW` | 273 | 6.0% | 6.09 | +5.41 | gold price, weekly |
| `KXSILVERW` | 109 | 2.4% | 13.18 | +11.76 | silver price, weekly |
| `KXGOLDMON` | 105 | 2.3% | 11.55 | +8.52 | gold price, monthly |
| `KXLITHIUMW` | 50 | 1.1% | 25.57 | −17.53 | lithium price, weekly |
| `KXNICKELW` | 40 | 0.9% | 15.79 | −2.74 | nickel price, weekly |
| `KXCOINBASE` | 14 | 0.3% | 11.25 | +5.75 | a company metric |
| `KXPERSONMENTION` | 6 | 0.1% | 25.58 | −6.42 | what someone says on a call |
| `KXSILVER15M` | 2 | 0.0% | 20.75 | −20.75 | silver price, 15-minute |
| `KXHYPE15M` | 1 | 0.0% | 50.00 | −50.00 | **the only cryptocurrency row in the cell** |

**97.6% is gold and silver** (4,455 of 4,566 rows). Add `KXLITHIUMW` and `KXNICKELW` and it is
**99.5% metals** (4,545 rows). Of the 21 rows left, 14 are a company metric about a crypto
*exchange* (`KXCOINBASE`), 6 are earnings-call quotes, and **exactly one row — 0.02% of the cell —
is a cryptocurrency price market**: `KXHYPE15M`, *"HYPE Up or Down — 15 minutes"* (Hyperliquid),
which reads ECE 50.00 on its single row.

> ⚠️ **The first draft of this document said "not one cryptocurrency market", and that was wrong
> by one row.** It is corrected here rather than softened, because the one row is not a rounding
> detail: it is the proof that the ingest skip below is *leaky*, not absolute. The claim the design
> rests on is unchanged and is a share claim, not an absolute one — **99.5% of a cell named `crypto`
> is metal.**

**And there is barely meant to be one.** `app/tasks/kalshi.py:654-658` skips crypto at ingest by
design — *"Skip crypto markets entirely — they consume DB space without providing value to
users"* — and the same guard sits on the gap-creation path at `:3668`. The skip fires on the
category assigned **at ingest**, and this whole cohort arrived as `other`, so it never fired: that
is how 4,545 metals markets AND one Hyperliquid contract are all sitting behind a label that says
`crypto`. A published `kalshi/crypto` calibration row is, 99.98% of the time, a row about
something else.

### The writer, named

The raw cohort (3,922 markets, all `id ≥ 48,000,171`, first seen 2026-07-08) carries
`category = 'other'` in every row, which is what `_categorize_kalshi_market` returns for
these: no ticker prefix matches (`KXGOLDH` → `None`), no name rule matches
(`categorize_by_rules("Gold price on August 02, 2026 at 10:00 PM EDT?")` → `None`), and
Kalshi's own category is not one this codebase maps. They were ingested as `other` — which
is why the crypto skip did not fire — and **relabelled `crypto` afterwards** by the LLM pass
in `app/tasks/futures.py` (`recategorize_other_futures`, phases 3 and 4).

The reason it reaches for `crypto` is in the vocabulary it is given.
`app/services/llm.py:248` `SPORT_CATEGORIES` has 31 entries. It has `crypto`. It has
`economics`. **It has no `commodities`.** Asked to file "Gold price on August 02, 2026 at
10:00 PM EDT?" into a list with no correct bucket, the model picks the nearest
asset-price-ticker attractor. That is a predictable failure of the vocabulary, not a random
model error, and it is the same shape as the motorsports misclassification: the fix is to
classify **positively**, not to add another exclusion.

### 🔴 HAZARD — there is a live admin button that would delete this data

`app/tasks/retention.py:299` `_cleanup_crypto_impl` deletes `futures_odds_snapshots`,
`futures_outcomes` and `futures_markets` **`WHERE llm_sport_category = 'crypto'`**, exposed
at `app/routes/admin_data_quality.py:306`. It is not on the beat schedule (which is why
these 3,922 rows are still alive), so it fires only when a human presses it.

**Its predicate is exactly the label that is wrong.** Pressing it to "clean up rank 6" would
permanently destroy 3,922 gold, silver, palladium, copper, lithium and nickel markets and
all their price history — a legitimate commodities corpus — because an LLM called them
crypto. **Nobody may treat that button as a fix for this cell**, and if the relabel in §5
ships, that task's predicate has to be re-derived before it is ever run again.

---

## 3. The shape: 99.9% of the cell is a non-partition bundle

| class | n | share | ECE | gap |
|---|--:|--:|--:|--:|
| `bundle_multiwin` | 4,563 | 99.9% | 7.59 | +1.85 |
| `single` | 3 | 0.1% | 30.50 | −30.50 |

This is a more extreme version of rank 2. `kalshi/economics` was 86.3% `bundle_multiwin`;
this cell has essentially nothing else. Crossed with the published price sum — the
structural test RULE E turns on:

| class | n | share | ECE | gap |
|---|--:|--:|--:|--:|
| `bundle` \| sum 5–15 | 2,058 | 45.1% | 6.98 | +3.12 |
| `bundle` \| sum 2–5 | 1,332 | 29.2% | 9.32 | −0.17 |
| `bundle` \| sum > 15 | 477 | 10.4% | 6.31 | +2.72 |
| `bundle` \| sum ≤ 1.15 | 404 | 8.8% | **11.68** | +4.43 |
| `bundle` \| sum 1.15–2 | 292 | 6.4% | 12.66 | −2.89 |
| `single` \| sum ≤ 1.15 | 3 | 0.1% | 30.50 | −30.50 |

**91.1% of the cell sits in markets whose published prices sum to more than 1.15** — a
median gold ladder publishes 5 to 15 units of probability mass across its rungs, which is
what a cumulative threshold ladder does and is not a distribution over one question.

**The `sum ≤ 1.15` slice is the WORST class, not the clean control**, and that is the
opposite of `kalshi/economics`, where the residual sorted 2.61 → 4.09 → 15.67 → 30.75 by
price sum and only the `≤ 1.15` slice was a forecast of one question. Those 404 rows sum to
~1 *and realized two or more winners*, which a partition cannot do. That is a grading
question, not a pricing one, and it is named in §6 rather than folded into the rule.

### The rival mechanism this board would otherwise have inherited

`polymarket/soccer`'s O/U ladder-coherence predicate (`app.utils.ladder_coherence`) reaches
**zero rows here**: the pre-pass scanned the whole cell and found **0 markets** matching
`name ~ 'O/U[[:space:]]+[0-9]'`, so `--by ladder` reports 100% `z_not_a_ladder`. Kalshi
threshold ladders are named `"Gold price on <date> at <time>"`, not `"O/U 3340.5"`. Checked
rather than assumed, per CAL-P118's lesson.

---

## 3b. Two more mechanisms are present, and the rule hides both

The bundle shape is not the only thing wrong with this cell. Two further folds were run
because §6b's warning — *a rail that has not been shown to reproduce a cell will still rank
its sub-classes, and the ranking will look like a mechanism* — cuts the other way too: a
rail that DOES reproduce a cell can still be pointed at only one hypothesis.

### The price this curve calls a closing line is usually older than the market

`--by age` — how stale the last snapshot before the market's own close is:

| capture age before close | n | share | ECE | gap |
|---|--:|--:|--:|--:|
| 1 h – 4 h | 3,008 | **65.9%** | **10.21** | +1.28 |
| 1 d – 7 d | 672 | 14.7% | 6.58 | +5.28 |
| 4 h – 1 d | 525 | 11.5% | **4.23** | +0.52 |
| no snapshot at all | 228 | 5.0% | 15.23 | −1.64 |
| > 7 d | 64 | 1.4% | 15.17 | +13.19 |
| < 15 min | 63 | 1.4% | 9.90 | +3.64 |
| 15 min – 1 h | 6 | 0.1% | 25.58 | −6.42 |

**`poll_kalshi_markets` runs `crontab(minute=45, hour="*/2")` — every two hours.** Two thirds
of this cell is `KXGOLDH` / `KXSILVERH`: **hourly** markets. A two-hour poll cannot see a
one-hour market's closing price, and often cannot see the market at all while it is open —
which is what the 1 h – 4 h bucket holding 65.9% of the cell is saying. For those rows the
"closing line" is a quote from a different hour of a different gold price.

The same cut by series horizon, gold and silver only, holding asset and shape constant:

| horizon | series | n | ECE |
|---|---|--:|--:|
| hourly | `KXGOLDH`, `KXSILVERH` | 3,139 | **10.87** |
| daily | `KXGOLDD`, `KXSILVERD` | 827 | **4.61** |
| weekly | `KXGOLDW`, `KXSILVERW` | 382 | 8.11 |
| monthly | `KXGOLDMON` | 105 | 11.55 |

⚠️ **Supported, NOT established, and this document will not upgrade it.** The hourly class is
2.4x worse than the daily one on the same asset with the same ladder shape, which is what the
capture story predicts. But **the age fold is not monotone** — 4 h – 1 d (4.23) is *better*
than 1 h – 4 h (10.21) and the freshest bucket (9.90, n=63) is worse than both — and the
weekly/monthly rungs break the horizon ordering on small samples. That is exactly the shape
CAL-P114 caught the shape census inventing on `kalshi/economics`, and being on the exact rail
does not make a non-monotone ladder into a mechanism. **Parked, not claimed:
PARKED CAL-P121-2 — short-horizon Kalshi series against a 2-hour poll.** It is not
metals-specific and it is a candidate mechanism for every short-lived Kalshi series on the
board.

### 3.7% of the cell is rank 1's coin-flip writer defect, on a different source

`--by cpdrift` — how far the published price was moved from the opening quote, and whether it
was moved *to* a coin flip:

| class | n | share | ECE | gap |
|---|--:|--:|--:|--:|
| `d_normal` | 3,236 | 70.9% | **5.42** | +1.13 |
| `c_moved_elsewhere` | 740 | 16.2% | **22.78** | +11.37 |
| `z_no_cp_fallback` | 383 | 8.4% | 2.38 | +2.31 |
| `a_forced_to_half` | 170 | 3.7% | **36.32** | −25.34 |
| `b_pulled_to_half` | 37 | 0.8% | 20.14 | −8.14 |

`a_forced_to_half` is CAL-P117's finding — a published price replaced by a manufactured
0.50 — **and it is here, on Kalshi, at 36.32 pp.** It is 3.7% of this cell rather than 54%
of it, so it is not this cell's driver, but it is the first evidence on this board that the
coin-flip class is **not confined to Polymarket "Player Props" containers**. Lane1's
writer-repair queue (§6f) should be told this cohort exists.

**And the residual has no healthy core.** `d_normal` — 70.9% of the cell, price not moved to
a half, not moved far, snapshot present — still reads **5.42 pp against a 3.0 bar**. There is
no subset of this cell that passes.

### What that means for the rule, stated plainly

Three defects are co-present: the rows are not a partition (§3), their closing line is
usually from the wrong hour (§3b), and 3.7% of them were overwritten with a coin flip. **RULE
C removes all three at once, because it removes 99.9% of the cell.** Two of the three are
*ours*, not the venue's. That is an argument for filing them, which §6 and §7 do — it is not
an argument for keeping rows in a published mean over questions when they were never a mean
over questions. But nobody may read rank 6 crossing off as "the metals ladders are now
priced well".

---

## 4. RULE C, and what it actually does

**RULE C — the ruled non-exclusive-bundle allowlist (§6b/§6d, Alex 2026-08-28 option b)
gains `(kalshi, crypto)`.** No new predicate, no new threshold, no new payload key: this is
one tuple added to a gate Alex has already ruled on, and it inherits the
`nonexclusive_bundle_filter` disclosure surface that is already built and green on
`program/calibration-115`.

Its measured effect, read off the disjoint `shape × sumband` classes above (the rule's
predicate *is* the class definition, so this is arithmetic on the fold, not a second
estimate):

| policy | n | ECE | verdict |
|---|--:|--:|---|
| A_today (control) | 4,566 | 7.61 | +4.61 over bar, 20,999 excess-outcomes |
| **C — allowlist add** | **3** | 30.50 | **removes 4,563 rows; cell becomes an absence** |

Both arms of the ruled gate — the realization test (`≥ 2 winners`) and RULE E's structural
test (`published sum > 1.15`) — condemn the same 4,563 rows, because every `sum ≤ 1.15` row
in this cell also realized two or more winners. **There is no version of this rule that
leaves a material cell behind.**

**So RULE C does not fix rank 6. It deletes it.** That is said here rather than discovered
after deploy, and it is the same outcome §6a already accepted for `kalshi/tech` (260 rows →
absence) — but at 4,563 rows it is seventeen times larger and it needs Alex's eyes.

### Why deleting is nevertheless the right answer for the CURVE

A gold-price ladder rung is a real Kalshi price on a real binary question, and this document
will not claim otherwise. What it is not is **a forecast that belongs in a mean over
questions**: 625 markets contribute 4,566 rows, so one gold print is counted 7.31 times, and
the rungs of one ladder are near-deterministically related (if gold is above $3,360 it is
above $3,350). Publishing them as independent rows tells a reader of the calibration page
that we made 4,565 forecasts about crypto. We made ~625 forecasts about the price of metal, and
one about Hyperliquid.

**Both halves of that sentence are wrong on the page today, and RULE C fixes the first one
only.** The second is §5.

---

## 5. RULE C is half a fix — the label is the other half

CAL-P119's precedent applies exactly: **EXCLUDE NOW + FIX WRITER**.

| half | where | kind |
|---|---|---|
| **C — exclude** | `precompute_calibration.py`, one tuple on the allowlist | **PERMANENT** — these rows are ladders and stay ladders |
| **L — relabel** | `app/services/llm.py:248` `SPORT_CATEGORIES` gains `commodities`; the metals series are classified positively rather than left to an LLM with no correct bucket | writer fix, separate lane |

Unlike rank 1's exclusion, **C is not temporary by design** — nothing here promises these
rows come back, and `temporary_by_cell` stays empty for this cell.

### 🔴 The correction L forces on C, and it generalises past this cell

§6b's conclusion was *"the allowlist must be keyed on `(source, category)`"*, and that is
still right about the polymarket/kalshi split it was derived from. This cell adds the
missing clause:

> **A cohort-scoped exclusion keyed on a label is switched off by the day someone repairs
> the label.** If L ships and the metals move to `kalshi/commodities`, an allowlist holding
> `(kalshi, crypto)` stops reaching them, `kalshi/crypto` becomes an empty absence, and
> **rank 6 reappears under a new name at 7.6 pp with no rule attached** — a cell crossed off
> that un-crosses itself silently.

Two things follow, and both are cheap:

1. **C and L must ship with the allowlist seeded for BOTH names** — `(kalshi, crypto)` and
   `(kalshi, commodities)` — whichever lands first. The second tuple costs nothing while the
   cell it names does not exist.
2. **A guard test, not a promise.** Specified in §8: a test that fails when any `kalshi`
   cell over its bar is more than 95% `bundle_multiwin` and is not on the allowlist. That
   turns "remember to move the tuple" into a red build.

---

## 6. Holdout — and it does not reverse

Split on `market_id 57,542,638`, which is the **published cell's own median** and not the raw
table's: this cell's producer predicate drops 82% of the raw cohort, so a split point
estimated from `futures_markets` would have cut a different population wearing the same name.
The point is read off `cluster_rows` in `sigma-kalshi-crypto.json` — 2,278 rows OLD, 2,288
NEW, a 49.9 / 50.1 split. The id is a chunk edge, so neither half is contaminated. The rule
was never re-fitted on either half; there is nothing to fit, since RULE C's predicate is
Alex's already-ruled one.

| | n | ECE | gap | survives RULE C |
|---|--:|--:|--:|--:|
| pooled cell | 4,566 | 7.61 | +1.83 | 3 rows |
| **OLD** (< 57,542,638) | 2,278 | **6.46** | +3.73 | **1 row** |
| **NEW** (≥ 57,542,638) | 2,288 | **10.73** | −0.06 | **2 rows** |

Three readings, and the second is the one CAL-P120's lesson 2 exists for:

1. **No sign reversal and no rescue.** Both halves are far over the 3.0 bar, and the later
   half is **worse** (10.73). On rank 5 the halves reversed the sign of the gap and killed
   the cell; here they agree, and they agree with the pooled number's verdict.
2. **Every single class, in both halves, is over the bar.** OLD's best class reads 6.80 and
   NEW's best reads 9.59 (`--by sumband`); on `--by cpdrift` the only class under 3.0 in
   either half is `z_no_cp_fallback` (136 / 247 rows, 2.05 / 2.57). **There is no slice of
   this cell, on data the rule was not designed on, that a narrower rule could have kept.**
   That is what makes "the rule deletes the cell" a finding rather than a blunt instrument.
3. **The pooled 7.61 is partly cancellation between the halves** — both halves individually
   read worse than the pooled cell does, because their per-decile deviations point in
   opposite directions and the pooled fold nets them. §2 of the scorecard again, inside one
   cell.

The coin-flip class of §3b holds on both halves and is **growing**: `a_forced_to_half` runs
68 rows @ 31.91 OLD → **102 rows @ 39.26 NEW**, and `c_moved_elsewhere` runs 15.55 → 29.84.
Whatever is overwriting these prices is doing it more, not less.

⚠️ One thing the fallback says that this lane did not expect. `z_no_cp_fallback` — the rows
where `calibration_probability` is NULL and the curve falls back to `opening_probability`
(gotcha #144 / ruling 103) — is the **best-calibrated class in the cell**, 2.38 pp, under the
bar, on both halves. On this cell the price we went and computed is worse than the price we
never touched. Noted, not diagnosed; it is consistent with §3b's capture story and it is part
of PARKED CAL-P121-2.

### The 404 rows the rule condemns for the wrong reason

`bundle | sum ≤ 1.15` — 404 rows, **ECE 11.68, the worst class in the cell** — are markets
whose published prices sum to a coherent ~1 and which then graded **two or more winners**. A
partition cannot do that. RULE C removes them, but it removes them under the bundle
predicate, and they are not bundles: they look like a **grading** defect, not a pricing one.

The rule is not adjusted for this — 404 rows is 8.8% of a cell that is going to zero either
way, and inventing a second predicate to catch them separately would be a threshold that
cannot separate anything (ruling 124). It is **parked**, because the same shape on a cell
that is *not* being excluded would be a live scoring bug:
**PARKED CAL-P121-1 — Kalshi markets that publish a coherent price sum and grade multiple
winners.**

---

## 7. What is owed to Alex

1. **RULE C's cost, in his currency — and there are three options, not one.** Ranks 1 + 2
   were ruled at ~5.7% of the published curve. C adds **4,563 rows = 0.50%**, taking the
   disclosed-exclusion total to **~6.2%**. The cell does not survive at 3 rows, so the
   board's eventual "crossed off" count gains a row that is an *absence*, exactly like
   `kalshi/tech`.

   | option | what a reader sees | what it costs |
   |---|---|---|
   | **(a) RULE C, recommended** | the `crypto` row leaves the calibration page; 4,563 rows join the named, counted `nonexclusive_bundle_filter` disclosure | one tuple; ships the day the freeze lifts; **hides two of our own defects** (§3b), which is why they are filed in §7.3 rather than left implicit |
   | (b) do nothing | the page keeps a `crypto` accuracy score made of gold and silver | rank 6 stays on the board at 7.60 pp forever — no narrower rule exists (§6.2) |
   | (c) score the ladder, not the rung | one row per ladder instead of 7.31; the cell stays material and becomes a real measurement of whether we price metals well | a **producer redesign** behind the freeze, and it needs a scoring definition for a distribution-valued forecast that nobody has ruled. Not a tuple. Named because it is the only option that ends with a *true* number for this cohort rather than an absence |

   This lane recommends **(a) now and (c) as a candidate for the measurement lane later**,
   because (a) is already-ruled machinery and (c) is a program.
2. **Criterion 3 (PARKED CAL-P114-3) and criterion 6 (PARKED CAL-P120-2), answered
   together with numbers.** §1's table is the answer, and the recommendation is
   **do not redefine the denominator — report the pair.** Substituting the market count
   would demote `kalshi/economics` to 2.01σ (a hair over the gate) on an assumption the
   measurement refutes. The proposal is that `calibration_scorecard` gain an
   `effective_n` / `design_effect` column **fed by this instrument** on the cells that are
   already queued, rather than a new formula applied blind to all 287. That is a measurement
   lane job under ruling 134 and it is not staged here.
3. **Two defects of ours that RULE C would hide, filed rather than folded into it.**
   **PARKED CAL-P121-2** — short-horizon Kalshi series against a two-hour poll (§3b): 65.9%
   of this cell's closing lines are 1–4 h stale on *hourly* markets, and this is not
   metals-specific. **Lane1's writer-repair queue** should be told that CAL-P117's
   coin-flip class exists on Kalshi too — 170 rows at 36.32 pp here, growing 68 → 102 across
   the holdout split.
4. **The `cleanup_crypto` hazard in §2.** This needs no ruling, but it needs to not be
   pressed. If Alex wants it made safe rather than remembered, that is a one-line predicate
   change in a lane that owns `retention.py`.
5. **The relabel L is not this lane's to ship.** It touches `SPORT_CATEGORIES`, which steers
   Discover, the category pages and cross-source matching, not just this curve. Named here,
   filed, not queued.

---

## 8. What lands on freeze-lift day

| deliverable | file | state |
|---|---|---|
| RULE C — one tuple on the allowlist | `precompute_calibration.py` | **waiting on the freeze** |
| the disclosure surface | `frontend/app/calibration/page.tsx` | ✅ already BUILT (§6d), gated on `excluded > 0` — renders nothing until the backend key exists |
| per-cell count in the payload | `nonexclusive_bundle_filter.excluded_by_cell` | spec'd in §9.1 of the CAL-P114 doc; C adds one entry |
| the anti-relabel guard | new test: no `kalshi` cell over its bar may be >95% `bundle_multiwin` and off the allowlist | **spec'd here, not built** — it asserts against a live payload and belongs with the rule |
| the instrument | `backend/scripts/calibration_cluster_sigma.py` + **41 guards, 10 mutations / 10 reds** | ✅ **BUILT and green on this branch** |
