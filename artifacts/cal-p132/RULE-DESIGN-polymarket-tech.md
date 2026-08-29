# CAL-P132 — `polymarket/tech` (board rank 19)

**VERDICT: REFUSED.** Seventeen partitions — sixteen inherited, one built for this
cell — every one searched exhaustively over its whole `2^k` lattice with
`--min-rows 1 --min-share 0`. **Zero subsets clear the 3.0 bar on the worst half at
any retention, including retentions that delete 99% of the cell.** The best
leakage-free result anywhere on the cell is **3.12 pooled / 4.66 worst-half** at 66.3%
retention (`policy` / `pairsum`); the best result including the two leaky dimensions is
**3.13 / 4.36** (`sumband`, 65.3% retention).

This is the **fourth consecutive refusal** — kalshi/entertainment (CAL-P129, holdout),
polymarket/golf (CAL-P130, retention), polymarket/economics (CAL-P131, no structural
handle), and now this one. It is also the **last unbanked, established, unworked cell
on the queue**: every other queued cell is either banked, refused, held behind an
unanswered Alex question, or an `odds_api_bookmaker` cell that CAL-P120 §6g turned off.
See §7.

Curve `2026-08-29T00:36:47Z`, population `q268`. Exact rail: **n 2,738 / ECE 5.00 /
gap −1.02** against the payload's **2,779 / 4.91 / −0.85** (−1.48% rows, +0.09 ECE,
−0.17 gap). σ 2.38 against the 2.0 gate, bootstrap CI [3.77, 7.15] — established, and
by a wider margin than rank 15 was.

---

## 1. What is actually in this cell

`polymarket/tech` is not a tech cell in the way the board's other **[C]** cells are.
Pulling all 2,973 raw markets by name (`raw-cell-names.json`, recursive split-on-cap so
the 1,000-row cap cannot truncate it):

| class | markets | share |
|---|--:|--:|
| **podcast / keynote word bingo** — *"What will Jensen Huang say during the NVIDIA GTC Keynote?"*, *"What will be said on the next All-In Podcast?"* | **867** | **29.2%** |
| App Store chart position — *"#1 Free App in the US Apple App Store on February 20?"* | 163 | 5.5% |
| **not technology at all** — *"10.0 or above earthquake before 2027?"*, *"Measles cases in U.S. by February 28?"*, *"Named storm forms before hurricane season?"* | 101 | 3.4% |

Nearly a third of the category the calibration board scores as "tech" is novelty word
bingo, and a hundred markets in it are seismology, epidemiology and weather. The
misclassification is a **DISCOVER/FORMATTING** defect independent of calibration and is
routed separately (§6, `alex-inbox/calibration-904`).

The published cell folds by shape as:

```
  field                 2226   81.3%    ECE  5.37   gap  -1.87
  container_member       347   12.7%         10.53       +3.35
  quantity               150    5.5%          7.82       +2.43
  duel                     9    0.3%         41.83       +3.28
  unshaped                 6    0.2%         33.75      -33.75
```

**The CAL-P131 one-legged-market check was run FIRST and it comes back small here.**
`unshaped` is 6 rows at a −33.75 gap — the same defect as rank 15's 508-row class, in
miniature, and immaterial to this cell. That check cost 75 seconds and it is worth
running on every cell; on this one it correctly said "not that".

---

## 2. Every partition, and what each one refused with

All folds run with `--holdout-at 32127295` — a **50.0 / 50.0** row split derived by
halving published rows in `cluster_rows` from `artifacts/cal-p128/sigma-polymarket-tech.json`.
That is the cleanest split the lane has produced.

**Baseline, `--by none`: pooled 5.00, OLD half 5.61, NEW half 5.98.** Unlike rank 15 —
where the OLD half already passed at 2.72 and only NEW was broken — **both halves of
this cell fail**, and they fail by almost the same amount. Any rule has to work twice.

| dimension | arms | best worst-half | leak-free | note |
|---|--:|--:|:--:|---|
| `sumband` | 12 | **4.36** (65.3% ret.) | ✗ `sh.mw` | best anywhere; 0 of **4,095** subsets under the bar |
| `policy` / `pairsum` | 5 | **4.66** (66.3% ret.) | ✓ | best leakage-free result on the cell |
| `shape` | 5 | 4.86 (28.4% ret.) | ✗ `sh.mw` | |
| **`twin`** | 5 | **5.10** (27.3% ret.) | ✓ | **built this session — see §4** |
| `market_type` / `pairtype` | 5 | 5.97 (99.8% ret.) | ✓ | the 81.3% `field` arm fails both halves |
| `price_moved` | 2 | 5.52 | ✓ | see §3 — this is the important negative |
| `cpdrift` | 5 | 5.98 | ✓ | only "pass" is 8 rows at 99.7% deleted — not a rule |
| `policy2` | 3 | 5.98 | ✓ | 99.7% in one arm |
| `bandratio` | 1 | 5.98 | ✓ | **degenerate** — 100% `z_not_a_partition` |
| `slotratio` | 1 | 5.98 | ✓ | **degenerate** — 100% `z_no_declared_n` |
| `age` | 1 | 5.98 | ✓ | **degenerate** — 100% `z_no_snapshot` |
| `ladder` | 1 | 5.98 | ✓ | **degenerate** — 100% `z_not_a_ladder` |
| `pair` | 1 | 5.98 | ✓ | **degenerate** — 100% `z_not_ou_pair` |
| `golfround` | 1 | 5.98 | ✓ | **degenerate** — 100% `tourney|other` |
| `series` | **289** | — | ✓ | **refused over `MAX_CLASSES` (22)** |

**Six degeneracies, all measurements — do not re-run them.** CAL-P131's `bandratio` finds
no band grammar here (this cell's legs are phrases and app names, not `<$6,400`);
`slotratio` finds no declared slot count; `ladder` and `pair` find no O/U markets at all;
`age` finds no snapshot; `golfround` is Kalshi ticker structure and is meaningless on a
Polymarket cell, exactly as CAL-P130 established.

`series` = **289 arms**, one per Polymarket event id, refused over `MAX_CLASSES`. This is
the **third** Polymarket cell on which CAL-P129-1's family-rollup idea has now been
checked and failed for the same reason. `twin` (§4) is the answer to that specific
failure: it is `series` collapsed onto the one property of a group that is a claim about
the product rather than about one event.

---

## 3. Why it refuses: a monotone compression that no subset can remove

The whole-cell bucket table is not noise. It is smooth and it is monotone:

```
  bucket      n   win rate   mean price      gap
  0.0-0.1   717     0.035        0.051     -1.57
  0.1-0.2   282     0.160        0.143     +1.67
  0.2-0.3   224     0.192        0.251     -5.93
  0.3-0.4   205     0.215        0.344    -12.94
  0.4-0.5   255     0.431        0.445     -1.36
  0.5-0.6   255     0.627        0.533     +9.45
  0.6-0.7   203     0.724        0.647     +7.71
  0.7-0.8   227     0.855        0.747    +10.76
  0.8-0.9   187     0.888        0.853     +3.46
  0.9-1.0   183     0.973        0.934     +3.91
```

Longshots lose more often than we show; favourites win more often than we show. The
published price is **compressed toward 0.5**. Fitting `logit(win) = a + b·logit(price)`
on the dominant `field` arm gives **b = 1.262**, and it holds across the split:
**b = 1.296 on OLD, b = 1.212 on NEW.** `container_member` is worse at **b = 1.703**.
(`recalibration-slope.py` in this directory reproduces every number below.)

**This is why the lattice is empty.** An exclusion rule removes a subset of rows. A
distortion that is present at *every price level* of the arm holding 81.3% of the cell
cannot be removed by deleting rows unless you delete the arm — and deleting the arm
leaves 18.7% of the cell reading 4.4 to 5.1. The 4,095-subset `sumband` search is the
empirical proof; the bucket table above is the reason.

### 3a. It is NOT the stale-opening-price fallback — the one hypothesis worth killing

The obvious mechanism is gotcha #144 / ruling 103: the curve scores
`COALESCE(calibration_probability, opening_probability)`, so rows where
`calibration_probability` is NULL are scored on a raw opening quote that the market
later moved away from. A stale opening quote is exactly the sort of thing that reads as
under-confident.

**It is not that.** `--by price_moved` splits the cell on whether the published price
differs from the opening quote at all, and the two arms have **the same slope**:

```
  unmoved   n=1865   ECE 5.15   b = 1.222
  moved     n= 873   ECE 5.01   b = 1.267
```

Rows where the price demonstrably *did* move carry the compression just as strongly as
rows where it did not. The fallback is not the mechanism, and the fallback hypothesis
should not be re-opened on this cell without new evidence.

### 3b. And recalibration does not rescue it either

Fitting the two parameters on the OLD half and applying them to the NEW half — a real
holdout test, not a fit reported as a result:

| arm | NEW ECE | NEW ECE after recalibration fitted on OLD |
|---|--:|--:|
| `field` | 6.77 | **5.20** |
| `container_member` | 9.66 | 8.59 |
| `quantity` | 9.49 | 7.46 |

A perfect one-parameter slope correction leaves the dominant arm at **5.20**, still 73%
over the bar. So the compression is real, stable and holdout-reproducible — **and it is
not the whole story.** The cell carries substantial non-monotone error on top of it.
Nothing here supports "fix the slope and the cell passes", and this section exists so
that claim is not made later on the strength of §3 alone.

---

## 4. What CAL-P132 built: `--by twin`, the third leakage-free dimension on the rail

### The gap it fills

Polymarket publishes a word-bingo event **twice, at two grains**. Group
`polymarket:555948` carries a 22-leg `field` — *"What will Tim Cook say at Apple WWDC
2026 on June 8th?"* — **and** fourteen separate `container_member` binaries — *"Will Tim
Cook say 'Siri' during the Apple WWDC 2026 event on June 8th?"*. Same phrase list, asked
twice, both ingested, both scored by the curve.

No dimension on the rail could see this. `market_type` separates the two grains but
cannot tell a twinned field from a lone one, so the control and the suspect pooled into
a single 81.3% arm. `series` keys on the group and produced 289 unsearchable arms.

`twin` labels each row with **the composition of its group** (`a_twinned` = the group
holds both a field and container members; `b_field_only`; `c_members_only`; `d_no_grain`;
`z_ungrouped`) **crossed with the row's own grain** (`|f` field, `|m` member, `|o`
other). The cross is the whole point and it is CAL-P131's `|full` / `|part` rule applied
a second time: label the group without labelling the grain and the two grains of a
twinned group pool, so a defect in one is diluted by the other.

### Two design decisions worth keeping

**The group census is deliberately not chunk-scoped.** The rail chunks on `fm.id`, and
the WWDC field and its fourteen binaries need not land in the same chunk. `grpcomp`
filters to the groups a chunk touches and then counts *every* market in each of those
groups straight off `futures_markets`. A chunk-scoped census would make twin-ness a
property of where the boundary fell — a twinned field reading `b_field_only`, i.e.
landing in the **control** arm, and the fold printing a clean table about it. That is
gotcha #53 in its usual costume, and it is guarded
(`test_the_group_census_counts_the_whole_group_not_the_chunk`).

**It reads nothing that a resolution touches.** `market_type` comes from
`app.utils.market_shape` (outcome structure, leg names, group membership) and `group_id`
is ingestion metadata. Unlike `shape` and `sumband`, which branch on `sh.mw`, a rule
keyed on `twin` is evaluable before any outcome exists. **27 guards**,
`backend/tests/test_calibration_cell_exact_p132_twin.py`, and `twin` was added to
`SHIPPED_DIMENSIONS` in `test_calibration_cluster_sigma_p121.py` **in the same commit** —
fourth dimension in a row to need that, and the note now says so in the manifest.

### It refused too — and, as on rank 15, the control is the part to keep

```
  a_twinned|f       1530   56.0%    ECE  6.99   gap  -2.90     <- the same question, published twice
  b_field_only|f     696   25.5%         4.64        +0.40     <- CONTROL: same grain, published once
  a_twinned|m        347   12.7%        10.53        +3.35
  d_no_grain|o       110    4.0%         7.71        +2.27
  c_members_only|o    51    1.9%        16.80        +1.49
```

`a_twinned|f` and `b_field_only|f` are the **same market shape, same category, same
price scale, same grain** — the only difference is whether the event was also published
as a shelf of binaries. Twinned fields read **6.99**; fields published once read
**4.64**. It holds in both halves: **9.80 vs 5.59** on OLD, **8.03 vs 3.37** on NEW.

Rule search over the partition: **0 of 31 subsets under the bar**, best worst-half 5.10
at 27.3% retention. So `twin` does not save the cell — but it is the only dimension that
produced a clean control, and the control says something the rest of the sweep cannot.

### The finding the control makes visible, which corrected this session's own hypothesis

The natural reading of §3 plus §4 is "twinning causes the compression". **It does not.**
The slopes run the other way:

| arm | n | ECE | slope `b` | NEW ECE | after recalibration fitted on OLD |
|---|--:|--:|--:|--:|--:|
| `a_twinned|f` | 1530 | 6.99 | **1.273** | 8.03 | **6.47** |
| `b_field_only|f` | 696 | 4.64 | **1.428** | 3.37 | **1.90** |

The control has the *steeper* slope and the *lower* ECE. So there are **two independent
defects** in this cell, not one:

1. **A cell-wide compression** (`b` ≈ 1.27–1.43), present in every field arm, in both
   halves, and equally in moved and unmoved rows.
2. **A twinning penalty** that is *not* a slope effect: recalibration takes the control
   arm from 3.37 to **1.90** — comfortably passing — and leaves the twinned arm at
   **6.47**.

Publishing one question at two grains carries error that no monotone correction removes.
That is a product claim about the ingestion of grouped Polymarket events, it is
measured against a control, and it is the one durable output of this session.

---

## 5. What would have to be true for this cell to pass

Stated plainly so the next session does not re-derive it:

* **Not an exclusion.** Seventeen partitions, 4,095 subsets on the widest lattice, zero
  passes at any retention. §3 says why, structurally.
* **Not recalibration alone.** Holdout-tested; leaves the dominant arm at 5.20.
* **The twinning penalty is the only handle with a measured control**, and acting on it
  means changing what gets ingested or how grouped events are deduped — a
  producer/writer change, not a read-side exclusion, and therefore not something this
  lane can bank while ruling 009's freeze holds.

---

## 6. Routed elsewhere

* **`alex-inbox/calibration-904` (LOOK)** — 29.2% of the "tech" category is podcast and
  keynote word bingo, and 101 markets in it are earthquakes, measles and hurricanes. A
  user opening tech sees this. Independent of calibration; a DISCOVER/FORMATTING defect.
* **`alex-inbox/calibration-904` §2 (FYI for Fable)** — the fourth consecutive refusal
  and what it implies for the conveyor. See §7.

## 7. The queue is out of unworked cells

Board rank 19 was the **last** unbanked, established, unworked cell on the 20-cell queue.
Every remaining entry is one of: banked (ranks 1, 2, 3, 6, 17), refused (8, 12, 15, and
now 19), held behind an unanswered Alex question (4/19-CAL, 9/17-CAL, 10/14-CAL,
11/20-CAL, 16/21-CAL), or an `odds_api_bookmaker` cell switched off by CAL-P120 §6g
(5, 7, 13, 14, 18, 20).

**The exclusion lattice for this board is exhausted.** Four cells in a row have refused,
each for a different reason, and each has produced a real product defect instead of a
rule. The honest recommendation — recorded here and staged to Alex/Fable rather than
acted on unilaterally — is that the conveyor's premise has changed: there is no fifth
cell to pre-build, and the lane's next useful work is either landing the five banked
designs (blocked on the freeze) or building the instruments the four refusals named.
CAL-P132's successor queue is written accordingly.
