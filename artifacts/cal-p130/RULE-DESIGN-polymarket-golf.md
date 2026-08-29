# CAL-P130 — rank 12, `polymarket/golf`: no exclusion rule exists, and the reason is that a hundred golfers are each shown a coin-flip to finish top five

**Pillar: TRUTH. Ship: the calibration page stops carrying a golf cell it cannot fix
by exclusion — and names, with a number and a control, the twelve golf markets where
the product tells a user that every player in the field is about 48% to finish in the
top five.**

Status: **diagnosed on the producer's own chain, folded over FIFTEEN partitions
(fourteen inherited + one built for this cell), holdout-split, exhaustively searched,
NO RULE BANKED.** Nothing here changes a published row;
`git diff origin/master -- backend/app frontend` is empty on this branch.

| | |
|---|---|
| board rank | 12 of 20 queued (live scorecard, 2026-08-29) |
| published cell | `polymarket/golf` — ECE **5.45** pp, n **6,463**, gap **+3.92** |
| class / bar | B_exchange_contest / **3.0** pp |
| excess | **+2.45** pp = **15,834** excess-outcomes |
| board σ | 3.9 (row grain) |
| **measured σ** | **2.44** (cluster bootstrap) — ESTABLISHED, thinnest margin on the board |
| curve | `2026-08-29T00:36:47Z`, population `q268` |

---

## 0. The three cheap checks first

**Can the rail reach the cell?** Yes, tightly.

| | exact rail | payload | Δ |
|---|---|---|--:|
| `polymarket/golf` | 6,443 / 5.39 / +3.82 | 6,463 / 5.45 / +3.92 | **−0.31%** rows, −0.06 ECE |

`calibration_cluster_spread` reads **LOW** — 43 `group_id` clusters over 3,690 markets,
1.6% in a wide cluster, max spread 2.4M ids. Id-range chunking is close to harmless
here, so every number below is on a rail whose one approximation was measured rather
than assumed (lesson 3).

**Is the cell established?** Yes, but only just, and this is the thinnest margin on the
board. From the CAL-P128 σ ledger (do NOT re-measure — lesson 4):

```
polymarket/golf — 6,443 rows / 115 clusters / 56.03 rows per cluster

  se_row        0.62 pp      sigma_row        3.84   <- what the board prints
  se_market     4.66 pp      (perfect-corr bound)
  se_bootstrap  0.98 pp      sigma_bootstrap  2.44   <- MEASURED
  bootstrap ECE 95% interval [3.77, 7.58]      variance ratio vs board 2.47
```

σ 2.44 clears `SIGMA_GATE` 2.0 and the bootstrap interval's **lower bound 3.77 is above
the 3.0 bar**, so unlike `kalshi/golf` (CAL-P127, σ 1.42, interval straddling the bar)
this cell really is broken and the 15,834 excess figure means what it says.

**Is the cell's name evidence of what is in it?** Mostly, with the usual exception
(lesson 5). 296 multi-leg field markets — `To Make the Cut` 158, `Winner` 39,
`Top 20` / `Top 10` / `Top 5` 33 each — plus ~90 single-player binaries shaped
*"Will Tommy Fleetwood finish in the Top 5 at the 2026 U.S. Open?"*. The contamination
is small and logged so the next reader does not re-discover it: a LIV Golf contract
question, a **rodeo** team-roping market, and *"Will 'Thief in the night' be said during
the Valorant Masters London 2026 Grand Finals?"*.

---

## 1. Fourteen inherited partitions, and every one of them refuses

Lesson 7: *"no rule found" and "no rule exists" are different claims, and the second is
cheap.* `calibration_rule_search` was run over every partition the rail carries with
**no retention floor at all** (`--min-rows 1 --min-share 0`), so these are exhaustive
statements about the whole 2^k lattice.

| partition | arms | under the 3.0 bar | best, and what it costs |
|---|--:|--:|---|
| `market_type` | 3 | **0** | NO RULE EXISTS |
| `price_moved` | 2 | **0** | NO RULE EXISTS — both arms over the bar (4.88 / 7.27) |
| `cpdrift` | 5 | **0** | NO RULE EXISTS |
| `pairtype` | 3 | **0** | NO RULE EXISTS |
| `policy2` | 3 | **0** | NO RULE EXISTS |
| `age` | 1 | **0** | **degenerate** — 100% `z_no_snapshot` |
| `pair` | 1 | **0** | **degenerate** — 100% `z_not_ou_pair` |
| `ladder` | 1 | **0** | **degenerate** — 0 O/U families in the whole cell |
| `golfround` | 1 | **0** | **degenerate** — built for Kalshi tickers, blind here |
| `shape` | 4 | 2 | 2.71, deleting **72.7%** |
| `pairsum` | 4 | 2 | 1.15, deleting **81.6%** |
| `policy` | 4 | 2 | 1.15, deleting **81.6%** |
| `sumband` | 8 | 18 | 0.30, deleting **82.0%**; best retention 64.1% deleted |
| `series` | 115 | — | **refused over `MAX_CLASSES` (22)** |

Nine partitions cannot reach the bar by deleting anything at all, four of those because
they are degenerate on this cell. Four more reach it only by deleting 64–82%.

**Four of the degeneracies are findings, not gaps.** `age` is 100% `z_no_snapshot` —
this cell has **no snapshot data at any age**, so the capture-timing discriminator that
CAL-P127 refuted on `kalshi/golf` by measuring seven arms cannot even be posed here.
`golfround` is 100% one class because it reads Kalshi ticker structure (`R[0-9]`,
`TOP[0-9]+$`) off `external_id`, and Polymarket's `external_id` is a `0x…`
`condition_id`. That is also why `series` explodes to 115 unrollupable hash arms: unlike
Kalshi's `KXSPOTIFY*` families (CAL-P129-1), **Polymarket series have no family prefix to
roll up**, so the parked family-rollup idea does not rescue this cell.

### The four that "pass" all pass the same wrong way

```
sumband                 n    share    ECE     gap
bundle|e_sum_gt_15   3517    54.6%   6.42   +4.72
field1|a_sum_le_1.15 1160    18.0%   0.30   -0.04   <- the clean control
bundle|d_sum_5_15     955    14.8%   5.61   +2.42
field1|e_sum_gt_15    396     6.1%  10.33  +10.33
field1|d_sum_5_15     200     3.1%   3.88   +3.88
binary|b_sum_1.15_2   192     3.0%  23.96   -0.06
```

Every passing subset clears the bar by deleting `bundle|*` — 69% of the cell. **This is
the move CAL-P127 already ruled structurally wrong and it is wrong here for the same
reason.** RULE E treats a market whose published prices sum past 1.15 as "not a
partition, whatever it happened to realize". In golf that is backwards: *"will player X
finish top 10"* is an **independent binary**, and a hundred of them priced against ten
slots legitimately sum to ten (gotcha #23). Deleting them deletes the category.

Two things in that table are worth carrying forward. `field1|a_sum_le_1.15` at **ECE
0.30** is CAL-P129's clean control reproducing exactly on a second venue and a second
category. And the `field1` arms rise monotonically with the price sum — 0.30 → 3.88 →
10.33 — which is CAL-P129's entertainment dose-response, replicated.

---

## 2. The partition this session built, because `sumband` measures the wrong quantity

`sumband` bands the raw sum against constants that assume a coherent market sums to ~1.
For an N-slot golf field the coherent sum is **N**, so the scale-free statement of the
defect is the **ratio** `msum / N` — and a golf field market declares its own N in its
own name.

**`slotratio`** (new dimension, 26 guards) bands that ratio. Two properties make it
different in kind from its neighbours:

1. **🔴 It is leakage-free.** `shape` and `sumband` branch on `sh.mw` — how many outcomes
   actually WON. That is fine for diagnosis and fatal for a shipping exclusion rule,
   which would then be selecting resolved markets by their resolution. `slotratio` reads
   only `fm2.name` and the published prices, both known before a winner exists.
   `test_the_expression_never_reads_a_realized_winner` is the guard that pins this.
2. **Its bands were fixed before the fold ran** — 1/4, 3/4, 4/3, 4, symmetric in log
   space around 1, so the banding can see an under-sum as readily as an over-sum
   (lesson 13).

```
slotratio                n   share     ECE      gap
d_ratio_1.33_4        3204   49.7%    3.31    +2.88
c_ratio_coherent      1160   18.0%    3.71    -0.93
e_ratio_gt_4          1085   16.8%   13.61   +13.41   <-
z_no_declared_n        794   12.3%    7.35    +1.01
z_cut_no_declared_n    140    2.2%   12.30    +1.57
b_ratio_0.25_0.75       60    0.9%   19.26   +14.87
a_ratio_lt_0.25          0    0.0%      —        —
```

> **The 1,160 in `c_ratio_coherent` and the 1,160 in `sumband`'s `field1|a_sum_le_1.15`
> are DIFFERENT ROW SETS and the match is a coincidence.** Their bucket vectors differ
> completely (`{0: 772, 1: 188, 2: 74, …}` against `{0: 1152, 1: 6, …}`) and their ECEs
> are 3.71 and 0.30. Recorded because two identical counts one table apart read as a
> copy-paste bug, and checking cost one command.

**And the symmetric banding found an asymmetric cell — which is itself the measurement.**
Raw markets under-sum badly: *"Puerto Rico Open Top 10"* publishes a sum of **0.50**
against ten declared slots, a ratio of 0.05. But in the **published** population
`a_ratio_lt_0.25` holds **zero rows**. The low tail is filtered out before the curve sees
it, so on this cell the defect really is one-directional — a fact about the published
population rather than an assumption baked into the bands (lesson 6).

### It still refuses — and it is the informative refusal

```
SUBSETS UNDER THE BAR: 0 of 63     NO RULE EXISTS

   ECE       n   dropped  keep
  3.03    4364   2079 (32.3%)  c_ratio_coherent, d_ratio_1.33_4
   3.2    4504   1939 (30.1%)  + z_cut_no_declared_n
  3.31    3204   3239 (50.3%)  d_ratio_1.33_4
```

The structurally correct, leakage-free dimension gets **closer than anything else on the
board** — 3.03 while retaining 67.7%, against `sumband`'s best-retention pass at 64.1%
*deleted* — and still cannot cross 3.0. That is the strongest available statement that
this cell is not excludable: the one partition that asks the right question, with the
mass kept rather than deleted, lands 0.03 pp short.

---

## 3. The holdout kills it properly (lesson 2)

Split at `market_id 22743356`, the point that halves the cell **by published rows**
(3,081 OLD / 3,362 NEW — a 47.8/52.2 split) read off `cluster_rows` in
`sigma-polymarket-golf.json`. `--holdout-at` inserts the id as a chunk edge
(`calibration_cell_exact.py:776`), so neither half is contaminated.

```
slotratio, scored on the WORSE half

   ECE  worst½       n   dropped  keep
  3.43    4.06    1300   5143 (79.8%)  c_ratio_coherent, z_cut_no_declared_n
  3.71    4.79    1160   5283 (82.0%)  c_ratio_coherent
  3.52    5.86    5158   1285 (19.9%)  c_ratio_coherent, d_ratio_1.33_4, z_no_declared_n
```

**The pooled 3.03 winner does not appear in the top twelve by worst half.** Best worst-half
is **4.06** against a 3.0 bar. The pooled best was an overfit and the holdout says so —
the third cell in four sessions where it changed the answer.

The reversal that drives it is worth naming (lesson 12): `d_ratio_1.33_4` reads **9.81
OLD → 1.15 NEW**, a near-total repair across the split, while `c_ratio_coherent` flips
sign (+1.53 → −4.79). A subset resting on those two arms is resting on a composition that
moved.

**`sumband` fails differently, and the distinction matters.** Unlike CAL-P129's
entertainment (33 subsets → 0 under the holdout), polymarket/golf's 18 sumband subsets
mostly SURVIVE — 12 of 255 still clear the bar on the worse half. They fail the
**retention floor** instead: every survivor deletes 72.7–82.0%. Same verdict, different
failure mode, and a session that only ran the holdout would have mis-attributed it.

---

## 4. 🔴 What the cell produced instead: twelve markets, a dose-response, and a control

`e_ratio_gt_4` is **1,085 rows / 16.8% of the cell / ECE 13.61 / gap +13.41**. `|gap| ==
ECE` to two decimals, so it is entirely one-directional over-prediction. It reproduces on
both holdout halves and is **worse in the NEW half**: OLD 11.87 (+11.63) → **NEW 19.01
(+16.45)**. This is live and getting worse, not a historical artifact.

Twelve markets carry it. Each is a full tournament field:

| market | legs | published sum | declared slots | ratio |
|---|--:|--:|--:|--:|
| Texas Children's Houston Open **Winner** | 101 | 29.07 | 1 | **29.1×** |
| Korn Ferry: Pinnacle Bank Championship **Winner** | 142 | 21.86 | 1 | **21.9×** |
| Texas Children's Houston Open Top 5 | 100 | 47.18 | 5 | 9.4× |
| Valero Texas Open Top 5 | 100 | 45.61 | 5 | 9.1× |
| Wyndham Championship Winner | 95 | 9.56 | 1 | 9.6× |
| Puerto Rico Open Winner | 100 | 8.87 | 1 | 8.9× |
| FedEx Cup Playoffs: Winner | 31 | 8.67 | 1 | 8.7× |
| Korn Ferry: AdventHealth Championship Winner | 98 | 8.52 | 1 | 8.5× |
| Texas Children's Houston Open Top 10 | 100 | 48.35 | 10 | 4.8× |
| Valero Texas Open Top 10 | 100 | 46.78 | 10 | 4.7× |
| Charles Schwab Challenge Top 5 | 100 | 24.48 | 5 | 4.9× |
| The Masters Top 5 | 91 | 20.38 | 5 | 4.1× |

**The user-visible statement.** *Korn Ferry Tour: Pinnacle Bank Championship Winner*
lists **142 players and shows each of them at about 49.7%** to win the tournament. The
Houston Open's top-5 market shows a hundred players at about 48% each to finish top five,
where five of them can.

### The control is what makes this a defect rather than a disagreement

Same shape, same 100 legs, same weekend structure:

| tournament | Top 5 | Top 10 | Top 20 |
|---|--:|--:|--:|
| **U.S. Open** (mean published price) | **0.049** | **0.088** | **0.148** |
| Texas Children's Houston Open | 0.478 | 0.477 | 0.483 |
| Valero Texas Open | 0.481 | 0.483 | 0.475 |

The U.S. Open is **exactly right** — 5/100, 10/100, 20/100. The other two are flat ~0.48
across the entire field. This is not a model that disagrees; it is a market where a
number was never written and something else was shown instead.

### 🔴 Why the existing detector is blind to it, and this is the reusable part

`cpdrift`'s `a_forced_to_half` arm — CAL-P117's coin-flip class, which memory records as
live on Kalshi entertainment and golf — found only **37 rows** here. It requires
`calibration_probability ∈ [0.45, 0.55]` **AND** `|calibration − opening| > 0.25`, i.e.
a price that *moved to* a half.

These prices did not move to a half. They were **published at a half from the open**:

```
                                        avg_open   avg_cal   sd_open
Houston Open Top 5    (100 legs)           0.478     0.472     0.095
Houston Open Top 10   (100 legs)           0.477     0.483     0.103
Valero Texas Open Top 5                    0.481     0.456     0.091
U.S. Open Top 5  (control)                 0.049     0.049     0.041
```

**A drift-based placeholder detector is structurally blind to a placeholder that was
never anything else.** Any repair keyed on movement will miss this entire class, on every
venue. That is the sentence worth keeping from this session.

---

## 5. Verdict, and what is owed

**`polymarket/golf` REFUSES. No rule banked. The board's five banked designs stand at
five** (239,384 excess-outcomes), unchanged.

The cell is genuinely broken — σ 2.44, interval lower bound 3.77 above the bar — and it
cannot be excluded into compliance by any of fifteen partitions, including one built
specifically to ask the structurally correct question without leakage. Its 15,834 excess
outcomes are a **writer** problem, not a curve-population problem, and the fix belongs to
the lane that writes prices, not to an exclusion rule.

**Routed to the writer lane (alex-inbox 902), joining CAL-P129's entertainment finding.**
The two are the same defect at different N: a field of candidates whose published prices
are incoherent with the number of slots the field offers. CAL-P129 measured N=1 on Kalshi;
this measures general N on Polymarket. Both are gotcha #23 / issue #1012.

### What a reviewer should push on

1. **The slot count is parsed from a market title, and titles change.** The guard suite
   pins anchoring and the whole-digit-run capture, and the 90 single-player binaries stay
   out of the banded arms only because their names end in `?`. If Polymarket renames
   *"… Top 5"* to *"… (Top 5)"*, `z_no_declared_n` grows silently and the arms shrink. The
   dimension is a measurement instrument, not a shipping predicate, so this is a
   diagnosis-quality risk rather than a production one — but a rule built on it later must
   not inherit the title dependency without re-checking it.
2. **`z_no_declared_n` is 12.3% at ECE 7.35 and is not diagnosed.** It is the
   single-player binaries plus the contamination. It is over the bar and this session did
   not take it apart.
3. **`z_cut_no_declared_n` is 158 markets — the largest family in the cell — and is
   deliberately unbanded.** Deriving the cut size from the realized field would be
   leakage; deriving it from tour rules is possible and was not attempted.
4. **The regex guards model POSIX with Python's `re` after an explicit translation.** The
   shipped expression was also run server-side against production and parsed the twelve
   markets above correctly, which is the evidence the unit tests cannot supply.

### Parked

- **CAL-P130-1** — `z_no_declared_n` (794 rows, ECE 7.35) is undiagnosed on this cell.
- **CAL-P130-2** — a cut-size source (tour rules, not the realized field) would make the
  158 cut markets bandable and is the largest unmeasured family in the cell.
- **CAL-P130-3** — **the drift-blindness generalization**: every placeholder detector in
  this repo keys on movement, so every one is blind to a price published at the
  placeholder value. Worth a board-wide sweep in its own right, and it is a stronger
  version of CAL-P129-2.
