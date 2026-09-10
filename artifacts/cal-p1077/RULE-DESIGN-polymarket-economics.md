# CAL-P1077 — rank 5, `polymarket/economics`: the mechanism is real, its size is not measurable tonight, and the cell does not close either way

**Pillar: TRUTH. Ship: the accuracy page stops reporting an 85%-winning forecast on
a family of daily questions whose own answer is a coin flip.**

Status: **mechanism CONFIRMED on the producer's own chain. Effect size WITHHELD —
the arm was being written while it was folded. The one conclusion that survived
three repetitions is that removing the arm leaves the cell OVER BAR, and it survived
the CERT-2428 refold onto the whole-virtual-market rail too (§0b: 3.78 → 3.80
against a 3.0 bar, twice, on a byte-identical roster). NO RULE SHIPPED:** both
remedies touch Alex's D13 ruling and the truth authority.
This subject writes no production code: `git diff origin/master -- backend/app
frontend` is empty on this branch, whose commits touch only `backend/scripts`,
`backend/tests` and `artifacts/`. CAL-P1078's frontend commit was SPLIT OFF onto
its own branch off clean master under CERT-2436's required repair
`1078-SPLIT-BLOCKED-P1077-FROM-READER-SHIP`, so the reader ship is not gated on
this measurement.

| | |
|---|---|
| board rank | 5 of 11 queued (live scorecard, 2026-09-09) |
| published cell | `polymarket/economics` — ECE **4.28** pp, n **9,779**, gap **−0.35** |
| class / bar | C / **3.0** pp |
| curve | `2026-09-09T19:16:15Z`, population `q269` |
| handed over by | `ARTIFACT-M-20260909-SUBCOHORT-polymarket-economics-unshaped.md` |

---

## 0. 🔴 READ THIS BEFORE ANY NUMBER BELOW — the population moved while it was folded

Three folds of the same cell with the same code, ~20 minutes apart:

| run | replica n | vs payload | `z_not_lone` | `a_lone_api_settlement` |
|---|--:|--:|---|---|
| 1 | 9,791 | +0.12% | **9,224 / 3.78 / +1.55** | 567 / 39.00 / −38.95 |
| 2 | 9,965 | +1.90% | **9,224 / 3.78 / +1.55** | 741 / 18.68 / −18.59 |
| 3 | 10,051 | +2.78% | **9,224 / 3.78 / +1.55** | 827 / 11.55 / −11.42 |

`z_not_lone` returned **byte-identical** three times. The lone arm gained ~130
rows per run and its ECE fell by more than half, twice. That is not drift and it is
not the instrument: something is grading single-outcome polymarket markets right
now. `GET /api/admin/backfill-winners/status` reads `polymarket needs_backfill:
269,639` against `orphan_size_1: 101,501` — a six-figure backlog of exactly this
shape, worked by a 6-hourly task.

**So the arm's n and its ECE are provisional and must not be quoted.** The rail folds
the LIVE database against a payload frozen at 19:16Z; its fidelity degraded from
+0.12% to +2.78% across the three runs, and its self-check is what made that
visible rather than averaging it away.

**Two things do survive**, and everything this document concludes rests only on them:

1. **`z_not_lone` = 9,224 / ECE 3.78 / gap +1.55, three times.** So the cell with the
   whole lone-claim arm removed sits at **3.78 pp against a 3.0 bar. It does not
   close.** The handoff predicted `4.28 → ~0.5–1.0`; that is refuted by a number
   that did not move.
2. **The arm is badly calibrated even at its best observed reading** (11.55 pp
   against the cell's 3.78). The mechanism is real; only its size is unknown.

**And the direction of the movement is itself a finding.** The arm's error is
*falling* as rows land. The rows arriving now are far better calibrated than the
ones already there, which means at least part of the winner-selection below is a
**grading LAG** — losses that have not been written yet — and not only a permanent
censoring. That distinction decides the remedy, and it is why no rule ships tonight.

---

## 0b. 🔴 CERT-2428 REPAIR — re-folded on the whole-virtual-market rail. THE CONCLUSION HOLDS.

Everything in §0 and below was measured with `calibration_cell_exact`'s `sweep()`,
which partitions on raw `futures_markets.id` ranges and **re-derives
`group_sizes` / `event_sizes` inside every slice**. CERT-2428 blocked this document
for it, and correctly: that rail reproduced 8,426 of `polymarket/basketball`'s
13,135 published rows (**−35.85%**), and it does not merely lose rows — it
re-assigns markets between the very classes `loneclaim` names. Repeating a fold on
that rail proves the returned partition is stable, not that it is the published one.

Re-folded on `backend/scripts/calibration_whole_vm_fold.py`, which freezes the
virtual-market generation ONCE for the whole cell and replays it through the
producer's own `plan_units` so a `vm_id` is never split. **Twice, 21.7 minutes
apart, on a roster that was byte-identical between the folds** (18,538 rows,
sha256 `dbad1e24e2edfad8` both times, 0 markets entered, 0 left —
`whole-vm-roster-identity.json`):

| | whole-vm fold 1 | whole-vm fold 2 | id-range (blocked) | payload |
|---|---|---|---|---|
| replica | 10,090 / 3.81 / +0.51 | 10,090 / 3.81 / +0.51 | 9,965 / 4.10 / +0.05 | 9,779 / 4.28 / −0.35 |
| vs payload | +3.18% | +3.18% | +1.90% | — |
| **`z_not_lone`** | **9,262 / 3.80 / +1.56** | **9,262 / 3.80 / +1.56** | 9,224 / 3.78 / +1.55 | — |
| `a_lone_api_settlement` | 828 / 11.44 / −11.31 | 828 / 11.44 / −11.31 | 741 / 18.68 / −18.59 | — |

**The load-bearing number survives the rail change: 3.78 → 3.80, against a 3.0 bar.
The cell still does not close, and Alex's lettered decision in §4 stands exactly as
written.** The lone arm reads 828 / 11.44 on the correct rail, which is where the
id-range rail's third run (827 / 11.55) had already arrived — so §0's "the arm is
being written while it is folded" was a true reading of a backlog that has since
drained: the roster no longer moves at all between folds.

### What this does NOT license

The two rails agreeing here is a measurement about these two cells, not a
rehabilitation of the id-range rail. It is not even predictable from the shape of
the cell. Reading the frozen rosters offline against `sweep()`'s own slices
(width 1,000,000, origin `MIN(id)` per SOURCE — 112,847 for polymarket, 171 for
kalshi), **112 of economics' 1,181 grouped virtual questions (9.5%), carrying 1,741
of its 18,538 markets, straddle a slice boundary** and would have been re-derived
under a different identity by the blocked rail — and hockey, where the two rails
agree to within ONE row, straddles at **93.4%**. The exposure was real in both
cells, largest in the cell that moved least, and the fold came back the same
anyway. Nobody can know that in advance, which is the whole reason the refold was
required rather than argued about. Banked as
`id-range-rail-exposure.json`, which also reads **`kalshi/golf` at ZERO** — every
one of its 3,450 markets sits in a group whose markets share a single slice, so
CAL-P1078's golf arm table is not exposed to this defect at all.

---

## 1. What the family is

Every row in the arm is a daily Polymarket binary — "Gold (XAUUSD) Up or Down on
August N?" — with **one captured outcome, named `Yes`, priced ~0.50**. One market per
day, each with its own `group_id`, so there is no family key to group them by.

`b_lone_<other source>` came back **empty**. That arm exists to separate "the defect
is LONENESS" from "the defect is the CHANNEL", and there is no third arm to compare
against because every published lone claim in this cell is `api_settlement`-graded.
Within this cell the two hypotheses are not separable; §3 separates them from outside
it.

---

## 2. The censoring, as of one snapshot

All graded lone claims in the `%up or down%` family, by grading source — a single
read at 2026-09-09 ~23:30Z, subject to §0 (fp `84ce728bd355f039`):

| source | truth class | n | winners | win rate | mean price |
|---|---|--:|--:|--:|--:|
| `all_losers` | terminal — **INELIGIBLE** | 1,371 | 0 | **0.0%** | 0.449 |
| `clean_resolution` | price-derived — **INELIGIBLE** | 949 | 949 | **100.0%** | 0.566 |
| `api_settlement` | authoritative — **ELIGIBLE** | 726 | 617 | **85.0%** | 0.535 |
| `pass3_threshold` | guess — ineligible | 7 | 4 | 57.1% | 0.532 |
| `pass2_loser` | terminal — ineligible | 6 | 0 | 0.0% | 0.495 |
| (ungraded) | — | 53 | 0 | — | 0.530 |
| **pooled** | | **3,112** | **1,570** | **50.45%** | |

**The pooled family wins 50.45%.** "Up or Down" is a coin flip and the pool says so
to two decimals — the check that makes the pool trustworthy and the eligible slice
suspect. The prices are fine. The *sample* is not:

* the days it went **down** are recorded, `is_winner = false`, under `all_losers` — a
  source the calibration allowlist refuses;
* the days it went **up** reach the page through `api_settlement`;
* `clean_resolution` is refused correctly — it is price-derived, and it is 100%
  winners here, which is what price-derived grading of a settled market looks like.

Nothing here is a pricing defect, a placeholder, or a shape defect. It is a censored
sample, and we did the censoring.

---

## 3. The split is winner-selecting well beyond this cell

Every lone claim in the database (exactly one captured outcome, eligible price band,
graded), one snapshot, same caveat as §0:

| truth class | n | winners | win rate | mean price | over-realization |
|---|--:|--:|--:|--:|--:|
| **ELIGIBLE** (`api_settlement` 9,393 · `game_score` 182 · `box_score` 1) | 9,576 | 5,807 | **60.6%** | 0.517 | **+8.9 pp** |
| **INELIGIBLE** (terminal + guess + price-derived) | 10,569 | 3,159 | **29.9%** | 0.431 | **−13.2 pp** |
| **pooled** | **20,145** | **8,966** | **44.5%** | 0.472 | **−2.2 pp** |

Pooled, lone claims are calibrated to within 2.2 pp. Split on truth eligibility, one
half reads +8.9 and the other −13.2. `api_settlement` is 98.1% of the eligible half,
so this is one channel's behaviour and not an average over many.

### Why no per-row structural rule exists

Three candidate discriminators, all refuted:

* **the channel** — "lone + `api_settlement`" is not a poisoned class. Over the 68
  (source, category) cells it reaches: `polymarket/table_tennis` 96.0% won at 0.660
  and `kalshi/soccer` 81.5% at 0.557, but `kalshi/esports` 59.1% at 0.582
  (calibrated) and `kalshi/entertainment` 44.3% at 0.591 — biased the **other way**.
  A blanket rule would delete calibrated rows to fix biased ones.
* **the leg name** — `generic_yes` vs a named leg separates nothing: polymarket
  named-leg 72.4% @0.575, polymarket `Yes` 57.4% @0.384, kalshi `Yes` 59.0% @0.545,
  kalshi named-leg 55.6% @0.525 (fp `3bf76e378ab7d755`).
* **the family** — each daily market carries its own `group_id`, so the
  one-sidedness test that would work has nothing to group on short of a name regex,
  and standing notice 40 rules a title match a candidate, never a membership test.

The defect is a property of a population, not of a row. A rule keyed on the observed
error would be a fit to the error — the overfit lesson this lane banked twice already
(CAL-P127, CAL-P130).

---

## 4. The decision — and why the default is the one that ADDS rows

Both remedies change what the published curve calls truth, so neither is a builder's
call. They are opposite in direction:

**A — exclude the censored slice.** Drop published lone claims whose loss channel is
ineligible. It makes the number honest by deleting the evidence, it works *against*
D13 (Alex ruled option A on 2026-08-30 precisely so a lone claim "publishes whether it
won or lost"), and §0 now argues against it directly: an arm whose error halves twice
in forty minutes is partly a queue, and you do not fix a queue by deleting its head.

**B — admit the loss we already recorded.** For a market with **exactly one captured
outcome**, `all_losers` does not mean "void" — it means *that one claim lost*, and the
row carries `is_winner = false` to say so. It is deterministic and it is not
price-derived. Admitting it for lone claims only restores the ~50% base rate, **adds**
~1,400 scored questions in this family alone, and finishes what D13 started rather
than reversing it.

**B is the recommended default.** Three things must be settled before it ships, none
of which was in this session's scope:

1. whether `all_losers` on a lone claim can ever mean *cancelled/void* rather than
   *lost* — if it can, B scores a void as a loss (gotcha #21's territory);
2. `no_winner_markets` removes markets grading nobody a winner three CTEs later, so B
   is two changes, and the second must be scoped to lone claims or it re-admits every
   void in the database;
3. **the backlog in §0 must drain first, or be measured as it drains.** If the arm's
   error keeps falling as the 269,639-row polymarket backfill completes, part of what
   §2 and §3 measure is a lag that fixes itself, and shipping either remedy against a
   moving population would credit the remedy with the backfill's work.

`clean_resolution` stays refused under both: price-derived, 100% winners here, and
admitting it would be circular.

---

## 5. What this session banks

* `--by loneclaim` and `--by pubband` on the producer's own chain, with a
  mutation-tested guard (`tests/test_calibration_cell_exact_p1077_dims.py`, 12 tests;
  8 mutations run, 8 as expected, control green before and after).
* The one stable correction: **the lone-claim arm's removal leaves 3.78 pp, over
  bar.** The cell does not close on this mechanism.
* The refutation of `polymarket/hockey`'s mechanism — see
  `RULE-DESIGN-polymarket-hockey.md`.
* 🔴 **A standing caveat for the whole seven-mechanism queue:** the exact rail folds
  the LIVE database against a frozen payload, so it is only trustworthy while the
  population is quiet. Tonight it was not, and two cells' fidelity degraded from
  ~0.1% to +2.8% and +5.6% inside an hour. **Every remaining cell must be folded
  twice, at least twenty minutes apart, and only figures that repeat may be quoted.**
