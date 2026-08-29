# RULE DESIGN — `polymarket/soccer` (rank 4): **REFUSED**

**CAL-P118, 2026-08-29.** Measured on the producer's own CTE chain, holdout-split.
**The cell's named mechanism was folded against the published cell for the first time and it makes
the cell WORSE.** Nothing is banked for rank 4. This document exists so that nobody spends another
cycle building it.

| | |
|---|---|
| cell | `polymarket/soccer`, class **B**, bar **3.0 pp** |
| board position | **rank 4 of 20**, 44,857 excess-outcomes on the `2026-08-28T20:37:41Z` curve |
| payload | n=106,803 · ECE **3.42** · gap **+2.16** (unchanged on the `23:35:51Z` curve) |
| exact rail, control | n=101,401 · ECE **2.89** · gap **+1.76** — the rail is **−5.06%** on rows and **−0.53 pp** on ECE, see §1 |
| the named mechanism | O/U ladder coherence, `app/utils/ladder_coherence.py` (CAL-P106/107), branch-only on `program/calibration-99` |
| the board's prediction | **−0.28 pp** (§7 of the scorecard), an arithmetic upper bound with a stated realistic band of −0.1 to −0.3 pp |
| **measured** | **+0.03 pp** — 2.89 → **2.92**. Wrong in **sign**, not in magnitude |
| holdout | OLD 4.86 → **4.99** · NEW 2.01 → **2.22** — **worse on both halves**, and on every variant tried |
| verdict | **REFUSED.** Rank 4 keeps its 44,857 excess-outcomes and loses its ✅ |

---

## 0. The one-line result

The rule is sound, its predicate is well-built, and it identifies a genuinely mis-priced class —
**3,989 published outcomes at ECE 9.57 against a cell at 2.89.** Removing them raises the cell's
ECE, because in **7 of 10 buckets the class's error has the opposite sign to the rest of the
cell** and was partially cancelling it. §3 has the table.

That is the same shape §2 of the scorecard names as the program's central hazard — *a cell's
headline is a cancellation, not a description* — arriving from the other direction. A class can be
the worst-calibrated thing in a cell and still be load-bearing for the cell's number.

---

## 1. Read this before any number below: the rail does not reproduce this cell

Two independent folds of the control population, ~90 minutes apart:

| fold | n | ECE | gap |
|---|--:|--:|--:|
| `--by none`, finished 23:25Z | 101,650 | 2.90 | +1.79 |
| `--by ladder`, finished 00:56Z | 101,401 | 2.89 | +1.76 |
| **payload** (`23:35:51Z`, q268) | **106,803** | **3.42** | **+2.16** |

**−5.06% on rows and −0.53 pp on ECE.** CAL-P114 measured ±1.22% on four cells and CAL-P117 read
−5.65% to −6.03% on `polymarket/baseball` with the ECEs still agreeing to 0.11 pp. Here the ECE
disagreement is **5x CAL-P117's worst**, and it points the wrong way for comfort: **the rail says
this cell is already under its bar at 2.89 while the payload says it is over at 3.42.**

So **no absolute level in this document is a published number.** What is claimed is a **delta
inside one population** — the same rows, folded with and without one class — and that comparison
does not depend on the rail reproducing the payload. Where the two would disagree is if the
missing 5.06% were concentrated in the ladder classes; §5 bounds that.

### 🔴 CAL-P117's stated cause for the shortfall is DISPROVEN

P117-3 parked it as *"`virtual_market` groups over `group_id`/`event_id` clusters that do not
respect `llm_sport_category`, so scoping the chain to one category breaks groups that hold in
production."* That is checkable directly, and it is false. Measured on the densest id band of this
cell (`57,000,000 ≤ id < 58,000,000`, 57,062 soccer markets, 42,637 with an event):

| test | groups / events | grouped source-wide | grouped with the category conjunct | **mis-sized** |
|---|--:|--:|--:|--:|
| `group_id` clusters holding a soccer market | 7,484 | 1,712 | 1,712 | **0** |
| `event_id` clusters holding a soccer market | 2,103 | 1,148 | 1,148 | **0** |

**Not one cluster changes size when the category conjunct is applied.** Polymarket's group and
event clusters are single-category in this cell. The category scope is exonerated.

Nor is it the id chunking, which the producer's own docstring warns about in these words —
*"group and event sizes are counted over `market_info`, so re-deriving them from a FILTERED
`market_info` silently changes them"* (`_virtual_market_ctes`). Counted the same way, over 1,000,000-id
chunk boundaries: **0 of 51,290 group-grouped soccer markets are demoted below the ≥3 gate by
chunking, and 1 of 41,481 on the event path.**

### What the payload says the cause is, in its own `staged` block

```
generated_at  2026-08-28T23:35:51Z      staged_at        2026-08-28T20:35:54Z
units_banked  128                       units_drifted    109        (of 128 checkable)
units_this_beat 6                       frozen_over_drift true
rolling_restage true
```

**The published curve is not an instantaneous read of the database.** It is a mosaic of 128 staged
units, banked at `20:35:54Z`, of which **109 have since drifted**, republished at `23:35:51Z` with
`frozen_over_drift` holding the bank. The exact rail is a single live read taken three hours later.
Two things follow, and the second one is the more important:

1. **The rail and the payload cannot agree except by luck**, and the disagreement should grow with
   the age of the staged generation — which is exactly what the two folds above show in miniature
   (101,650 at 23:25Z, 101,401 at 00:56Z, on a payload that did not move).
2. **The published number cannot move while `frozen_over_drift` holds.** The `23:35:51Z` beat and
   the `20:37:41Z` beat publish the *same* `20:35:54Z` population, which is why this cell reads
   106,803 / 3.42 on both and why the headline is 1.89 pp on both. The flatness is structural.

**The instrument this program owes itself is not a `--scope-check`.** It is a **staged-generation
replay** — fold the cell as of `staged.staged_at`, against the same banked units, the way
`frozen_vm_roster` already lets the producer replay one coherent generation over chunks. Parked as
CAL-P118-1 with that spec, and P117-3 is superseded rather than deleted.

---

## 2. What the mechanism actually reaches

The shipped predicate, run over the whole cell in one pre-pass (so no family's verdict depends on
where a chunk boundary fell — §6):

| | |
|---|--:|
| markets carrying an `O/U <line>` rung | 107,089 |
| … usable (rung parsed, Over price present) | 106,736 |
| ladder families | 32,772 |
| … of one rung, never condemned (ruling 105) | 2,069 |
| … ambiguous — the key demonstrably groups two ladders | 236 |
| … **condemned** | **23,501 (71.7%)** |
| markets condemned | **81,291 (76.2%)** |

Then the number that changes the question:

| class | published outcomes | share of cell | ECE | gap |
|---|--:|--:|--:|--:|
| `z_not_a_ladder` | 93,881 | **92.6%** | 3.11 | +1.81 |
| `a_drop_incoherent` | 3,989 | 3.9% | **9.57** | +2.47 |
| `c_ladder_coherent` | 3,361 | 3.3% | 1.73 | −0.07 |
| `b_ambiguous_kept` | 170 | 0.2% | **16.24** | −5.86 |

**81,291 condemned markets produce 3,989 published outcomes.** The ladder rule's reach into the
published curve is **7.4% of the cell**, not the 100% a subcohort measurement implies — because an
O/U ladder is precisely a `group_id` cluster, `virtual_market` collapses it to one virtual
question, and `deduped` keeps one representative. **The producer has already deduplicated away most
of what this rule was built to delete.**

CAL-P106 measured 5,708 legs of `soccer/quantity`. The published cell contains **7,520 ladder
outcomes in total**. The two populations are of similar size and the published one is *the whole
ladder population of the cell* — so the subcohort was never a 5% sample of the ladders. It was a
different slice of a population the curve barely admits.

> **The lesson CAL-P117 wrote down, confirmed on a second cell and by a different route.** Rank 1's
> banked mechanisms were diagnosed on 3.1% of their cell and were worth −0.53 pp. Rank 4's was
> diagnosed on a cohort the curve dedups away, and is worth **+0.03 pp**. In both cases the board's
> ✅ described a real defect in a population the published curve does not contain.

---

## 3. Why removing the worst class makes the cell worse

Per bucket, the dropped class against everything else:

| bin | drop n | drop err | rest n | rest err | |
|--:|--:|--:|--:|--:|---|
| 0 | 118 | **+16.15** | 26,747 | −0.26 | ← opposite |
| 1 | 289 | **+9.52** | 12,754 | −1.32 | ← opposite |
| 2 | 325 | **+2.82** | 12,891 | −3.25 | ← opposite |
| 3 | 325 | −8.58 | 12,244 | −3.13 | |
| 4 | 748 | −23.64 | 11,363 | −7.34 | |
| 5 | 1,157 | **+5.22** | 8,535 | −4.61 | ← opposite |
| 6 | 305 | +8.40 | 4,480 | +6.11 | |
| 7 | 351 | **−3.78** | 3,983 | +4.56 | ← opposite |
| 8 | 262 | **−4.96** | 2,596 | +3.17 | ← opposite |
| 9 | 109 | **−8.43** | 1,819 | +2.35 | ← opposite |

*err = win rate − mean published price, in pp.*

**Seven of ten buckets.** The templated ladder is over-priced at the bottom of the book and
under-priced at the top; the rest of the cell is the mirror image. Pooled per-bin, they cancel.
Delete one side and the other stands up.

This is not an argument that the ladders are correctly priced — bin 0 alone is a class published at
6.7% that wins 22.9% of the time. It is an argument that **ECE on a pooled cell cannot grade a
row-dropping rule**, which is doctrine 18's clause arriving as a positive result instead of a
warning.

---

## 4. Every variant, and both halves of the holdout

Bar 3.0; σ = 50/√n.

| policy | n | ECE | (ECE−3)/σ | OLD | NEW | |
|---|--:|--:|--:|--:|--:|---|
| **control** | 101,401 | **2.89** | −0.73 | 4.86 | 2.01 | |
| A — drop incoherent ladders (*the shipped rule*) | 97,412 | **2.92** | −0.48 | **4.99** | **2.22** | 🔴 worse on both halves |
| A+B — also drop the ambiguous families | 97,242 | 2.95 | −0.29 | **5.00** | **2.23** | 🔴 worse still |
| A+B+C — drop every ladder row in the cell | 93,881 | **3.11** | +0.70 | **5.20** | **2.30** | 🔴 pushes the rail's cell **over the bar** |

There is no threshold to tune and no arm to drop: **the monotone ordering runs the wrong way.** The
more of the ladder population the rule removes, the worse the cell gets, on the pooled number and
on each half independently. CAL-P117 recorded four policies that passed pooled and failed a half;
this is the first that fails everything at once, which at least makes it cheap to refuse.

### The rule's own fail-safe keeps the worst class in the cell

`b_ambiguous_kept` — 170 outcomes at **ECE 16.24**, the worst-calibrated class on this board — is
kept *by design*: the family key groups two ladders, the rule's premise is disproven there, and
`incoherent_families` fails toward keeping (the esports key-collapse guard). That is the right
behaviour and it is worth naming, because it is 236 families' worth of a key that does not identify
a single ladder, and it splits **57 OLD @ 8.38 / 113 NEW @ 20.21** — it is *growing*.

---

## 5. What this document does NOT claim

1. **That the rail's missing 5.06% is not in the ladder classes.** It is bounded, not excluded: the
   ladder classes are 7.4% of the rail's rows, so for the shortfall to overturn a +0.03 pp sign it
   would have to be almost entirely ladder rows *and* carry the opposite bias to the ladder rows
   the rail did see. The rail's two independent control folds agree to 249 rows and 0.01 pp, so
   whatever it is missing, it is missing it stably.
2. **That the ladder predicate is wrong.** Nothing here disputes `ladder_coherence.py`. Its
   arithmetic contradiction is real, its rung-profile separation is real, its guards are good, and
   its 48 guard tests pass unchanged on this branch. What is refuted is the *published-curve value*
   of shipping it — the claim in §7 of the scorecard, which was arithmetic.
3. **That `soccer/quantity` was mis-measured.** CAL-P106's 8.53 → 3.76 on its own cohort is not
   contradicted. That cohort is not this cell.
4. **That rank 4 has no mechanism.** It has no *found* one. 92.6% of the cell is
   `z_not_a_ladder` at 3.11 pp, and the OLD/NEW split there is violent — **57,747 @ 5.20 / +4.35
   against 36,134 @ 2.30 / −2.25, opposite-signed gaps.** That is where the cell's error lives and
   it is untouched. A `--by sumband` fold is the next read.

---

## 6. The instrument, and the one thing it had to get right

`--by ladder` is new on `calibration_cell_exact.py`. Two properties are load-bearing:

**The predicate is imported, never restated.** `incoherent_families`, `ambiguous_families`,
`read_ladders`, `ladder_family_key` and `parse_ou_line` are the module's own objects, asserted by
identity (`is`), and the script is forbidden a rung pattern of its own. The module itself says its
SQL rendering is UNPROVEN against its Python and that measurement must be driven from the Python
side until a whole-population differential exists — so the verdict is computed in Python and only
the *answer*, a set of market ids, is pushed back into SQL.

**The verdict is computed before the chunking, not inside it.** A ladder family is a set of markets
sharing a name modulo the rung, and nothing makes their ids contiguous. A verdict computed inside a
1M-id chunk would be a verdict on whichever rungs fell on that side of the boundary — and a partial
ladder is *systematically more coherent* than the whole one, because the violating pair may be the
one that got cut. That error is silent and one-directional and it makes a rule look smaller than it
is. The pre-pass sweeps the cell once at its own width; each fold chunk then receives only the ids
inside its own range.

25 guard tests, 7 mutations, 7 reds — including "fold ambiguous into coherent", "condemn only the
violating rungs instead of the family", "read `opening_probability` instead of the published
coalesce", and "let the dimension run with no pre-pass" (which silently reports that the rule found
nothing at all).

`ladder_coherence.py` and its 48 tests were brought onto this branch as **byte-identical copies** of
`program/calibration-99` (`git diff` against that branch is empty for both paths). The module is
unwired — nothing in `backend/app` imports it — so it changes no published row, and
`precompute_calibration.py` is untouched, so ruling 009 is not engaged.

---

## 7. Consequences for the board

- **Rank 4 loses its ✅.** `polymarket/soccer` is *"❌ none — the named mechanism was measured and
  refused"*, and its 44,857 excess-outcomes stay on the board.
- **§7 of the scorecard is wrong and must be re-written, not annotated.** "The first test of the
  loop" predicted −0.28 pp and called it *"the largest published improvement this program would
  have made since 2026-08-01."* It is +0.03 pp. The prediction was honestly made and honestly
  flagged as an upper bound; the failure is that it was arithmetic on a subcohort, which is the
  precise thing CAL-P117 had already been burned by one cycle earlier.
- **§8's conversion assumption gets its first real datapoint, and it is worse than assumed.** The
  estimate uses ~1.5 rules per cell, evidenced partly by "the soccer rule falls short of its own
  cell". It does not fall short of its cell; it goes backwards. One of four cells with a named
  mechanism has now had that mechanism scored against the published curve twice — rank 1 (−0.53 pp,
  cell still failing) and rank 4 (+0.03 pp, refused).
- **Ranks 3 and 17 are now the exposure.** `polymarket/esports` and `kalshi/tech` were designed on
  `calibration_cell_replica` and re-checked on the exact rail (CAL-P114). Rank 2 was designed on the
  exact rail directly. Rank 1 was re-measured by CAL-P117. **Rank 3's re-check is the one to look at
  hardest**, because it is a Polymarket cell and it is the largest un-re-derived design left.
