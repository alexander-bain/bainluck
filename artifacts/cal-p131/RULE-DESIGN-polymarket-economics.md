# CAL-P131 — rank 15, `polymarket/economics`: no exclusion rule exists, and on the way to finding that out the curve was caught publishing 508 outcomes that could not have been anything but winners

**Pillar: TRUTH. Ship: the calibration page stops carrying an economics cell it cannot fix
by exclusion — and names, with a control, the 508 rows the curve admits only because they
won, and the eleven-band S&P market that tells a user both tails of the same distribution
are 40%.**

Status: **diagnosed on the producer's own chain, folded over SIXTEEN partitions
(fifteen inherited + one built for this cell), holdout-split, exhaustively searched,
NO RULE BANKED.** Nothing here changes a published row;
`git diff origin/master...HEAD -- backend/app frontend` is empty on this branch.

| | |
|---|---|
| board rank | 15 of 20 queued (live scorecard, 2026-08-29) |
| published cell | `polymarket/economics` — ECE **3.90** pp, n **12,882**, gap **+0.14** |
| class / bar | C_exchange_standalone / **3.0** pp |
| excess | **+0.90** pp = **11,594** excess-outcomes — the *smallest* excess on the queue |
| board σ | 2.0 (row grain) |
| **measured σ** | **2.07** (cluster bootstrap) — ESTABLISHED, and the thinnest margin of any cell now on the board |
| curve | `2026-08-29T00:36:47Z`, population `q268` |

---

## 0. The three cheap checks first

**Can the rail reach the cell?** Yes, tightly.

| | exact rail | payload | Δ |
|---|---|---|--:|
| `polymarket/economics` | 12,700 / 3.89 / −0.28 | 12,882 / 3.90 / +0.14 | **−1.41%** rows, −0.01 ECE |

`calibration_cluster_spread` reads **MODERATE** — 1,176 `group_id` clusters over 12,705
markets, **11.2%** in a cluster wider than the chunk, max spread 55.2M ids. The verdict
predicts a single-digit row shortfall and the fold delivered 1.41%, so the one
approximation on this rail was measured before the numbers were read (lesson 3).

⚠️ The **gap** does not reproduce as tightly as the ECE: −0.28 against +0.14. ECE is the
graded quantity and it agrees to 0.01, but no claim below rests on the sign of the gap of
the *whole cell* — every gap quoted below is a gap of a CLASS, computed inside the fold.

**Is the cell established?** Yes, and by less than any other cell now queued. From the
CAL-P128 σ ledger (do NOT re-measure — lesson 4):

```
polymarket/economics — 12,952 rows / 1,700 clusters / 7.62 rows per cluster

  se_row        0.4393 pp    sigma_row        2.071   <- what the board prints
  se_market     1.2127 pp    (perfect-corr bound)
  se_bootstrap  0.4394 pp    sigma_bootstrap  2.071   <- MEASURED
  bootstrap ECE 95% interval [3.30, 5.04]      variance ratio vs board 1.00
```

σ 2.071 clears `SIGMA_GATE` 2.0 by **0.07**, and the bootstrap interval's lower bound
**3.30 is above the 3.0 bar**, so the cell really is broken. It is also the one cell on the
board where the row-grain estimate the scorecard prints was *right* — variance ratio 1.00,
because 7.6 rows per cluster with weak within-cluster correlation is close to independence.
The queue's warning was that a fold moving the population slightly could drop it out of
ESTABLISHED; the fold moved it by 1.41% of rows and 0.01 ECE, which moves σ by less than
the margin. **It stays established.**

**Is the cell's name evidence of what is in it?** Here, unusually, yes (lesson 5). 18,504
raw markets, and the contamination is negligible — equity closes, index closes, commodity
strikes, Fed/CPI questions, earnings beats, tariff and court questions. What the *name*
does not tell you is the SHAPE, and the shape is the whole story:

```
raw market_type   container_member 11,474 · unshaped 4,437 · quantity 1,657 · field 932 · duel 4
raw name grammar  11,083 of 18,504 markets carry exactly one "$<strike>" in the title,
                  forming 1,575 families of which 11,000 markets sit in a family of >= 3
```

**This is a cell of THRESHOLD LADDERS** — *"Will Apple (AAPL) close above $255 / $260 /
$265 … on August 5?"*, *"S&P 500 (SPY) closes above $X on August N?"*, *"How high will the
10-year Treasury yield go by March 31?"* — in two physical forms: one strike per market
(`container_member`), and one market with a rung per outcome (`quantity` / `field`).

---

## 1. Fifteen inherited partitions, and every one of them refuses

Lesson 7: *"no rule found" and "no rule exists" are different claims, and the second is
cheap.* `calibration_rule_search` was run over every partition the rail carries with **no
retention floor at all** (`--min-rows 1 --min-share 0`), so these are exhaustive statements
about the whole 2^k lattice, not a few arms tried by hand.

| partition | arms | under the 3.0 bar | best pooled / worst-half, and what it costs |
|---|--:|--:|---|
| `market_type` | 4 | **0** | 3.26 / **3.91**, dropping 4.0% |
| `pairtype` | 4 | **0** | 3.26 / **3.91**, dropping 4.0% (identical — see below) |
| `sumband` | 14 | **0** | 2.98 / **3.75**, dropping **65.1%** |
| `pairsum` | 5 | **0** | 3.52 / 4.21, dropping 8.3% |
| `policy` | 5 | **0** | 3.52 / 4.21, dropping 8.3% (identical to `pairsum`) |
| `cpdrift` | 5 | **0** | 3.93 / 6.10 |
| `policy2` | 3 | **0** | 3.93 / 6.12 |
| `age` | 3 | **0** | 3.88 / 6.15 — **near-degenerate**, 99.85% `z_no_snapshot` |
| `price_moved` | 2 | **0** | 3.89 / 6.15 — both arms over the bar (4.20 / 4.98) |
| `pair` | 1 | **0** | **degenerate** — 100% `z_not_ou_pair` |
| `slotratio` | 1 | **0** | **degenerate** — 100% `z_no_declared_n` |
| `ladder` | 1 | **0** | **degenerate** — **0** O/U markets scanned in the whole cell |
| `shape` | — | — | subsumed by `sumband` (its prefix) and disqualified on leakage |
| `series` | 1,658 | — | refused over `MAX_CLASSES` (22) |
| `golfround` | — | — | not run: reads Kalshi golf ticker structure, meaningless here |

### The four degeneracies are measurements, not gaps — do not re-run them

* **`pair` is 100% `z_not_ou_pair`.** There is not one Over/Under two-leg market in the
  published cell. Everything CAL-P117 and CAL-P100 built for `polymarket/baseball` is
  inapplicable, and `pairtype` / `pairsum` / `policy` therefore collapse to `market_type`
  and `sumband` respectively — which is exactly what their numbers show, to the row.
* **`slotratio` is 100% `z_no_declared_n`.** CAL-P130's golf grammar ("… Top 10" → 10) does
  not occur once. A ladder declares no slot count anywhere in its market name. **This
  degeneracy is the argument for the dimension built in §2.**
* **`ladder` scanned ZERO O/U markets.** `app.utils.ladder_coherence` keys on a literal
  `O/U <number>` in the name. Polymarket writes its rungs as `$255` or `above $255`, so the
  shipped ladder-coherence predicate is structurally blind to a cell that is *nothing but
  ladders*. **That is a finding about the predicate, not about the cell** — same family as
  CAL-P130's drift-blindness (CAL-P130-3): a checker keyed on one spelling reports an
  all-clear on a population written in another (lesson 16).
* **`age` is 99.85% `z_no_snapshot`.** CAL-P127's capture-timing discriminator cannot be
  posed here either — 19 rows of 12,700 carry a snapshot.

### `series` explodes for the reason CAL-P130 already recorded

1,658 arms, one per `0x…` condition_id, because Polymarket's `external_id` is a condition
id and rolls up to nothing. `MAX_CLASSES` refuses rather than sampling, which is correct: a
sampled search reporting "0 under the bar" is a false all-clear (lesson 11). **CAL-P129-1's
family-rollup idea does not rescue this cell either, and that is now two Polymarket cells
where it has been checked and failed.**

### 🔴 And every subset that *approaches* the bar is disqualified before its number is read

`sumband`'s best subset — 2.98 pooled — is a **leakage** rule. `sumband` splits the cell
with `sh.mw`, the realized win count (`bundle` = ≥2 winners, `field1` = exactly 1, `single`
= a one-leg market). A shipping exclusion keyed on `field1`/`bundle` would decide which
resolved markets count **by what they resolved to**. CAL-P130 made this the standing test
and it removes `sumband`, `shape`, `pairsum` and `policy` from consideration on this cell
regardless of arithmetic. It also deletes **65.1%** of the cell, so it fails the retention
test as well — both failure modes, in one subset (CAL-P130's warning: run both, always).

The two partitions that are wholly leakage-free are `market_type` (a stored column) and
`price_moved`. Their best is **3.26 pooled / 3.91 worst-half at 96% retention** — 0.26 pp
short pooled and 0.91 short on the half that matters.

---

## 2. The partition this session built, because both sum dimensions measure the wrong quantity here

### `--by bandratio`, and it is the second leakage-free dimension on the rail

`sumband` bands the published price sum against constants (1.15, 2, 5, 15) that encode one
assumption: **the market is a partition, so a coherent sum is ~1.** CAL-P130 showed that
premise is wrong for golf's independent binaries, and fixed it by dividing by a slot count
the *market name* declares. **On this cell the premise is wrong for a third reason, and
`slotratio` cannot fix it.**

A nested threshold ladder's rungs are **not mutually exclusive**. If Apple closes at $268
then "above $255", "above $260" and "above $265" all pay. So a coherent thirteen-rung
ladder's prices sum to **the expected number of rungs that hit** — anywhere in `[0, 13]`
— and there is no slot count to divide by, because the rungs are nested rather than
parallel. `sumband` reads a perfectly coherent ladder as `d_sum_5_15` and condemns
**53% of the cell for being arithmetically correct**.

**What economics declares instead is a GRAMMAR in its OUTCOME names.** A market whose legs
read

```
<$6,400   $6,400-$6,500   $6,500-$6,600  …  $7,200-$7,300   >$7,300
```

has said, in its own text, that its outcomes are mutually exclusive **and exhaustive**. That
market's prices must sum to 1, and any other sum is a defect of the market rather than a
forecast that turned out wrong. A market whose legs read `$255`, `$260`, `$265` has said no
such thing.

So `bandratio` asks two questions, both from text and published prices:

1. **Do the leg names declare an exhaustive partition?** All legs match a band grammar
   (`<x`, `>y`, or `a-b` / `a – b`), there are ≥3 of them, and **both** open tails are
   present. Anything else is `z_not_a_partition` or `z_not_exhaustive`.
2. **If so, does it sum like one?** `msum` banded at **1/4, 3/4, 4/3, 4** — the same four
   constants `slotratio` uses, so the two tables can be read against each other, and fixed
   before the fold ran (lesson 13).

🔴 **Exhaustiveness is required, not assumed.** A run of interior bands with no open tail is
mutually exclusive but not exhaustive, and its coherent sum is some unknown number below 1.
Banding it against 1 would be the dimension inventing the quantity it claims to measure —
CAL-P130 separated `To Make the Cut` for exactly this reason, and `z_not_exhaustive` is that
arm here.

🔴 **Every input is known at publish time.** Leg names and published prices. No `mw`, no
`is_winner`, no resolution column. `test_the_expression_never_reads_a_realized_winner` pins
it across the expression, the join AND the pre-CTEs, and it is the guard to keep if the
others are ever trimmed. **62 guards**, `backend/tests/test_calibration_cell_exact_p131_bandratio.py`.

**`|full` vs `|part` is a CROSS, not a gate.** A partition whose legs did not all reach the
curve publishes a sum mechanically short of 1 through no fault of its pricing. Gating those
rows out early would have hidden the rows most likely to be incoherent; folding them in
unlabelled would let a liquidity artifact read as an incoherence. §3 shows the cross earned
its place.

---

## 3. What `bandratio` measured: a control, and a defect with the same shape as CAL-P130's

```
polymarket/economics   --by bandratio      n = 12,700   ECE 3.89

  class                     n    share     ECE      gap    win rate   mean price
  z_not_a_partition     12,089   95.2%    4.05    -0.69      0.4367       0.4298
  d_sum_1.33_4|full        402    3.2%    9.83    +9.74      0.0945       0.1920
  c_sum_coherent|full       73    0.6%    4.79    +0.99      0.0959       0.1058
  c_sum_coherent|part       64    0.5%   10.13    +9.32      0.0469       0.1401
  b_sum_0.25_0.75|part      29    0.2%    8.50    +5.06      0.0690       0.1195
  z_not_exhaustive          29    0.2%    1.97    +0.31      0.1034       0.1066
  d_sum_1.33_4|part         10    0.1%   13.41    +3.40      0.1000       0.1341
  a_sum_lt_0.25|part         4    0.0%    3.28    +3.28      0.0000       0.0328
```

**Read the third and fourth rows against the second.** Among markets that declared an
exhaustive partition, the only arm that is calibrated is the one that is **both coherent and
complete**: `c_sum_coherent|full`, gap **+0.99**. Every other arm runs **+3.3 to +9.7**.
Same grammar, same shape, same price scale — the single thing that differs is whether the
declared partition sums to 1 and whether all of its legs reached the curve. **That is the
control, and it is what makes this a defect of the markets rather than a disagreement with
them.** It is also the measurement that justifies the `|full` / `|part` cross: a version of
the dimension that had gated on completeness would have reported 475 rows and never shown
that `c_sum_coherent|part` (+9.32) behaves like the over-summing arm and not like its own
`|full` sibling.

### The named example

`2383063` — **"What will S&P 500 (SPX) close at in March?"** — eleven mutually exclusive
bands, published prices summing to **1.960**, and the two open tails priced at **exactly
0.400 each**:

```
  <$6,400        0.400   <- both tails at 0.400
  $6,400-$6,500  0.110
  $6,500-$6,600  0.115   <- the winner
  $6,600-$6,700  0.125
  $6,700-$6,800  0.135
  $6,800-$6,900  0.145
  $6,900-$7,000  0.155
  $7,000-$7,100  0.155
  $7,100-$7,200  0.125
  $7,200-$7,300  0.095
  >$7,300        0.400   <- both tails at 0.400
                 -----
                 1.960     the nine interior bands sum to 1.160
```

The nine interior bands are close to sane. The two disjoint tails cannot both be 40% of the
same distribution, and they carry the entire 0.80 of excess. The user is shown a market that
says the index is 40% to finish below $6,400 **and** 40% to finish above $7,300.

⚠️ Those eleven prices are read from `futures_outcomes` directly, not from `deduped` — this
is the market as the provider carries it, quoted to make the grammar and the defect legible.
All eleven legs carry a price, so the market cannot be a `|part` row, but the exact `msum`
the fold banded it in is the producer's, not this table's.

---

## 4. 🔴🔴 The finding that outranks the rule: 508 published outcomes that could not have lost

This is not in any partition's *pass* column, because it is not a calibration failure. It is
the curve reading a population selected on the answer.

```
  market_type = 'unshaped'   (== sumband's 'single', a market with ONE published leg)

    published rows      508
    winners             508          <- n == w in EVERY price bucket, all nine of them
    win rate            1.0000
    mean price          0.5698
    ECE                 43.02        |gap| == ECE, so purely one-directional
    gap                -43.02
    OLD half   93 rows @ 41.59       NEW half  415 rows @ 43.34
```

Every one of the 508 is a winner, in every bucket, on both halves of the holdout. The
mechanism is a raw-population census away:

```
  single-leg markets in polymarket/economics (raw)   3,844
    leg named "Yes"                                  3,825
    leg graded winner                                2,027  (52.7%)
    leg graded loser                                 1,817  (47.3%)
  rows this shape contributes to the published curve      508  — and 508 of 508 are winners
```

**The raw base rate is a coin flip and the curve sees 100%.** These are two-sided questions
— *"Silver (SI) Up or Down on February 19?"*, *"Will Snowflake (SNOW) beat quarterly
earnings?"*, *"US tariff revenue up in Q4 2025?"* — whose second leg was never ingested.

The candidate mechanism, read out of the producer (read-only; the file is frozen):

```sql
-- backend/app/tasks/precompute_calibration.py:2067
clean_vms AS (
    SELECT * FROM vm_stats
    WHERE eligible >= 1
      AND has_winner >= 1
)
```

On a virtual market with two or more legs, `has_winner >= 1` is a sanity gate: you cannot
score a question nobody graded. **On a virtual market with ONE leg it is not a sanity gate
at all — it is `is_winner = true`.** The admission criterion and the outcome are the same
predicate. `no_winner_markets` (queue 299 rung 1) would have caught the losers, but it is
scoped `n_outcomes >= 2` and never sees them.

⚠️ **What is proven and what is inferred.** *Proven*, on the producer's own chain: 508
published rows, 508 winners, and 3,844 raw markets of that shape at a 52.7% base rate.
*Inferred*: that `clean_vms` is the clause responsible. A one-leg market that is grouped into
a larger virtual market could in principle lose while a sibling won; none of the 508 did,
which is consistent with the clause but not a proof of it. Naming the clause is a lead for
the lane that owns the fix, not a verdict.

**Routed to the producer/writer lane. It is the same family as CAL-P129's and CAL-P130's
findings and it is the third in a row** (#1012, gotcha #53 — "an empty 200 is not an
absence"; here, a one-sided admission is not a one-sided truth).

---

## 5. 🔴 The cell's modest headline is two large opposite-signed defects cancelling

This is why nobody has looked at rank 15 in nine sessions.

```
  sumband shape prefix      n       win rate   mean price      gap
  single                   508        1.0000       0.5698    -43.02
  field1                 1,760        0.1318       0.2758    +14.40
  bundle                 9,535        0.4375       0.4276     -0.99
  binary                   897        0.4693       0.4965     +2.72
                        ------
  whole cell            12,700        0.4368       0.4297     -0.28   ECE 3.89
```

508 rows under-priced by 43 pp and 1,760 rows over-priced by 14 pp sit in overlapping price
buckets and partly cancel, so the pooled cell reads **3.89** — a number small enough to rank
fifteenth and be left for nine sessions. **A cell's ECE is not a bound on the size of the
defects inside it** (lesson 17, below).

`field1`'s worst arm is CAL-P130's golf finding again, on a different sport and a different
source: `field1|d_sum_5_15` — 173 rows, win rate **0.110**, mean price **0.507**. A
one-winner field where thirteen mutually exclusive outcomes are each shown at about a coin
flip. That is now **three cells** carrying the same writer defect (kalshi/entertainment
N = 1, polymarket/golf general N, polymarket/economics).

---

## 6. The holdout says something different from the last two cells, and it is checked

```
  whole cell, split at market_id 32,676,761 (a 49.9 / 50.1 row split from cluster_rows)

    OLD   n = 6,335   ECE 2.72   gap +1.40     <- UNDER the 3.0 bar
    NEW   n = 6,365   ECE 6.15   gap -1.95     <- more than double the bar
```

**The old half of this cell already passes.** The entire 11,594 excess-outcomes lives in the
new half, and no subset of any of the sixteen partitions brings the worst half below **3.75**.

Lesson 14 says check the two halves are about the same population before letting the split
decide anything, and they are **not**: the published composition shifts hard across it
(`field` 48.5% → 29.5%, `unshaped` 1.5% → 6.5%, `container_member` 2.8% → 11.2%). So the
split is confounded, and the degradation had to be re-measured **like for like, inside a
single arm**:

| arm | OLD | NEW |
|---|---|---|
| `bundle\|d_sum_5_15` — the biggest arm in both halves | 3,766 @ **3.18** | 2,962 @ **5.38** |
| `bundle\|c_sum_2_5` | 901 @ 7.79 | 1,302 @ 7.86 |
| `binary\|b_sum_1.15_2` | 138 @ 6.63 | 592 @ 6.72 |
| `field1\|c_sum_2_5` | 371 @ 21.84 | 336 @ **16.96** |
| `unshaped` | 93 @ 41.59 | 415 @ 43.34 |

Two things moved and neither is composition: **the largest arm degraded 3.18 → 5.38 within
itself**, and **the all-winner class quadrupled in row count**. Everything else is flat or
improved. So "the cell broke recently" survives the composition check — it is a real
degradation in the nested-ladder population plus a growing selection artifact, not an
artifact of what the split happened to contain.

---

## 7. Verdict, and what is owed

**REFUSED.** Sixteen partitions, fifteen inherited and one built for this cell, every one of
them exhaustively searched with no retention floor. Zero subsets clear 3.0 on the worst half
at any usable retention. The two `bandratio` subsets that clear the bar retain **29 and 33
rows** — 0.2% of the cell — which is CAL-P130's "pass the wrong way" verbatim.

**Why it refuses, stated as a mechanism rather than a tally.** 95.2% of the cell is nested
threshold ladders. They are the only large class, their error is **not one-directional**
(`z_not_a_partition`: ECE 4.05, gap −0.69), and it is **worse in the new half** (6.27).
No structural, leakage-free predicate on the rail separates a well-calibrated ladder from a
badly-calibrated one, because the two are the same object priced differently — which is what
a genuine calibration failure looks like, as opposed to a population defect. The two real
population defects in this cell (§4, §5) are together 2,268 rows / 17.9%, and removing the
leakage-free half of them leaves the cell at 3.26.

**This is the third consecutive session whose cell refused** (kalshi/entertainment,
polymarket/golf, polymarket/economics). The conveyor is producing diagnoses and writer-lane
routings rather than bankable exclusions. The handoff asked that this be said to Fable if it
happened a third time, and it has; §8 says what I think it means.

### What a reviewer should push on

* **The `clean_vms` attribution is a lead, not a proof.** §4 marks the line. The measured
  facts stand without it.
* **`bandratio` reads a grammar, and a grammar is a guess about a provider's text.** It was
  written against six real markets from this cell and 62 guards, and it classifies 611 of
  12,700 published rows. If Polymarket writes bands another way, the dimension under-counts —
  and it would under-count *silently*, into `z_not_a_partition`. The honest bound is: what it
  found is a floor on the declared-partition population, not the population.
* **`d_sum_1.33_4|full` is 402 rows.** The +9.74 gap is stable across both halves (12.12 OLD
  / 5.16 NEW) but 402 rows is a thin base for a general claim about Polymarket band markets.
* **The holdout split is by market id, i.e. by time, and the composition shifts.** §6 handles
  it with a within-arm comparison; a reviewer who thinks that is not enough should say what
  would be.

### Parked

* **CAL-P131-1 — cross `market_type` with `bandratio` in one fold.** They are the only two
  leakage-free partitions on this cell and their union is the only candidate exclusion left
  unmeasured. Two separate sweeps cannot be subtracted from each other (CERT-403B); it needs
  one fold. **Predicted to still refuse** — the arms it would drop total ~1,017 rows and the
  NEW half's residue is 6.27 — but "predicted" is not "measured", and this is the one gap in
  the refusal.
* **CAL-P131-2 — `app.utils.ladder_coherence` is blind to every ladder in this cell.** It
  keys on a literal `O/U <number>`; Polymarket writes `$255` and `above $255`. The shipped
  ladder-coherence predicate scanned **zero** markets in a cell that is 95% ladders and
  reported a clean fold. Generalizing its family key to a strike ladder would give the rail
  its first monotonicity test — *P(above $255) ≥ P(above $260) ≥ …* — which is leakage-free,
  is the natural coherence law for the class, and no instrument in this repo can currently
  express it. **Highest-value unblocked item this session produced.**
* **CAL-P131-3 — why did `bundle|d_sum_5_15` go 3.18 → 5.38?** The like-for-like degradation
  in §6 is the whole reason the cell fails, and it is undiagnosed. It is a question about
  *forecast quality over time*, not about population defects, so it may have no exclusion
  answer at all — but nothing on the board is currently asking it.

---

## 8. One line for Fable

Three refusals in a row is not three failures: the three cells refused for three *different*
reasons (entertainment on the holdout, golf on retention, economics because its dominant
class is a genuine calibration failure with no structural handle), and each produced a
routable product defect the board could not otherwise see. But the conveyor's stated ship is
banked exclusion designs, and it has banked none since CAL-P128. **If the remaining queued
cells look like this one — dominated by a large, coherent, genuinely-mispriced class — then
the exclusion lattice is exhausted and the next queue should be pointed at the writer-lane
backlog these three sessions have generated, not at rank 19.**
