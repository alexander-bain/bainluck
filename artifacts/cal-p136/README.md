# CAL-P136 — the Polymarket O/U book, reached at last, and refused anyway

Published number at session start and end: **1.88 pp** (`generated_at`
`2026-08-29T23:35:53Z`, `q268`, 925,400 outcomes). Trend **↓** from 1.89, and
unchanged across this session — the producer published once more before this
queue opened and not again during it.

CAL-P135 fixed the NAME grammar and a sign inversion inside it, then measured
that `--by mono` still reached **none** of the ~52k O/U-shaped markets on four
Polymarket sports cells. It named two remaining blockers and parked them as a
package (its README §4). This queue built the package, measured it on all four
cells, and **did not bank a rule** — for reasons §4 gives with numbers.

Ships in `61620737`'s successor commit; the frozen file is untouched.

---

## 1. What was built

**(a) The PRICE site — `proposition_price` in `app/utils/ladder_monotonicity.py`.**
Every caller priced a rung with a leg literally named `yes`. Polymarket's
two-sided totals book has none; it prices `Over` and `Under`. The function
returns `(price, reason)` and is deliberately narrow, because `Over` and `Under`
price OPPOSITE claims and substituting the wrong one inverts the law's sign
exactly as reading the `Under` half of the compound did:

* a `yes` leg always wins — changing that would silently re-base every shipped cell;
* `over` substitutes ONLY on a market carrying BOTH legs (proof of the two-sided
  shape) AND whose name parses as the `parse_over_under` compound;
* everything else yields no price and a **named refusal**: `no_leg`,
  `half_pair`, `not_ou_named`, `no_name`.

`ladder_report(price_key=None)` resolves the leg itself and publishes the
refusal tally as `census["price_legs"]`, next to the verdict, per lesson 22.

**(b) The IDENTITY-scoped family key — `context_key` / `scoped_key`.**
`blanked_key` alone collapses context-free sub-market names ("Games Total: O/U
2.5") across unrelated matches. `read_name_ladders` and `ladder_report` now take
an optional `context_key`; left `None`, every key is byte-identical to
pre-CAL-P136 behaviour.

**(c) The rail — `MONO_CONTEXT_COLUMN` in `calibration_cell_exact.py`.**
🔴 **The identity is a per-SOURCE fact and the two sources are opposite.**

| source | `group_id` | markets per group | verdict |
|---|---|---|---|
| polymarket | `polymarket:{event.id}` | 3.08 (tech), 3.25 (economics), 100% coverage on all four sports cells | a real identity |
| kalshi | `kalshi:KXAAAGASD-26MAY25` — the market's own ticker | **1.00** (342/342 economics, 3,983/3,983 crypto) | **not an identity** |

Scoping by `group_id` on Kalshi does not refine the partition, it **destroys**
it: every family becomes a singleton, no singleton is condemnable (ruling 105),
and the cell reports CLEAN. So the column is a table keyed by source, not a flag
an operator remembers to set, and `mono_context` **refuses** an unlisted source
rather than defaulting. Guarded by
`test_a_one_value_per_row_identity_annihilates_the_book`, which reproduces the
annihilation on Kalshi's shape.

135 → **155 guards** in `test_ladder_monotonicity.py`; every market name copied
from a real censused market. Middle gate `-k "calibration or bookmaker or
ladder"`: 2,944 → **2,964 passed** in 131 s.

---

## 2. The measurement — four arms, so the two fixes are attributable separately

`artifacts/cal-p136/ou-book-fold.py`, raw cells, rows cached by `pull_rows.py`.
"reach" = markets the instrument places in ANY family (drop + ambiguous +
coherent); "drop%" is of reach.

| cell | arm A shipped | arm B price only | arm C identity only | arm D **package** |
|---|---|---|---|---|
| baseball | reach 2 | 26,494 · 1.2% | 2 | **24,953 · 28.9%** |
| basketball | 6 | 5,467 · 25.9% | 6 | **2,452 · 69.7%** |
| esports | 17,909 · 0.0% | 22,203 · 0.0% | 15,816 · 58.9% | **16,718 · 56.2%** |
| soccer | 9 | 98,620 · 27.0% | 9 | **98,582 · 27.6%** |

**Each cell was blocked by a DIFFERENT member of the package, and that is the
argument that it is one package.** Baseball, soccer and basketball are blocked
at the price site — arm C alone moves nothing, because with only a `yes` leg
there was almost nothing to key. Esports is the mirror image: it has 78,959 yes
legs and only 4,294 over legs, so arm B moves nothing and the identity key is
the whole fix. Neither member alone reaches all four cells.

Total reach across the four cells: **17,926 → 142,705 markets.**

**The unscoped key was manufacturing findings, on exactly the cells where the
names are context-free.** Condemned families spanning more than one event:
baseball **52.9%**, basketball **21.7%**, soccer 0.0%, esports 0.0%. On baseball
the majority of the unscoped arm's output was a comparison of one game's price
against another's. Scoping is load-bearing where it matters and inert where it
does not.

---

## 3. CAL-P135-2 — answered, and REFUTED twice

The parked hypothesis was that the unexplained flat rate on esports O/U ladders
is placeholder pricing. Both halves are dead:

* **The flat pairs are arithmetically coherent prices, not placeholders.**
  `over + under` sums to ~1.00 for equal-leg markets on soccer (**99.4%** within
  1%) and esports (**91.5%**) — *more* consistent than the unequal-leg
  population (89.3% / 80.3%). They are exact 0.50/0.50 coin flips.
  ⚠️ Basketball is the exception and runs the other way: only **8.9%** of its
  equal pairs sum to ~1, so basketball's flat pairs really are incoherent. One
  cell's answer is not the book's (lesson 5).
* **The coin flips are not what drives the condemnations.** Arm E re-runs the
  package with every exact-0.50/0.50 market excluded. The drop rate barely
  moves: baseball 28.9 → 28.9, basketball 69.7 → 68.6, esports 56.2 → 57.6,
  soccer 27.6 → 27.5.

Coin-flip share of two-legged markets: soccer 58.2%, esports 43.5%, basketball
33.7%, baseball 5.4%. That is a large writer-class finding in its own right —
the coin-flip class the hand-off notes track on three cells now has four more
candidates — but it is **not** the explanation for the ladder violations.

---

## 4. 🔴 NO RULE IS BANKED. Still five.

The instrument now reaches the book. The rule it produces is not landable, on
two independent grounds, and neither is a detail that a threshold fixes:

1. **The condemnation rate is 28–70% of the laddered population** (baseball
   28.9%, soccer 27.6%, esports 56.2%, basketball 69.7%). An exclusion rule
   deletes a concentrated defect (lesson 18). A rule that deletes a third to
   two-thirds of a book is not finding a defect in the book, it is disagreeing
   with it, and doctrine has no route for that.
2. **The holdout is unstable on two of four cells.** Split at each cell's id
   median, package arm, drop rate of the laddered population:

   | cell | early | late | |
   |---|---|---|---|
   | baseball | 48.08% | 18.24% | **2.6× — unstable** |
   | basketball | 55.70% | 81.75% | **reverses upward — unstable** |
   | esports | 55.19% | 53.55% | stable |
   | soccer | 32.44% | 25.02% | stable-ish |

   Lesson 2 says believe the holdout over the pooled number. Two cells fail it.

**A third hazard, new, and it is the price of the fix.** `families_ambiguous`
goes to **0 on every cell** once the key is scoped. The `duplicate_values` guard
— the thing that made the collapsed key survivable, and the thing CAL-P135's
lesson 22 was written about — now catches nothing, because within one event the
same line does not repeat. The correctness of every condemnation therefore rests
**entirely** on `group_id` being the right identity, with no second line of
defence. Fixing the key did not just improve the partition; it removed the
safety net that was compensating for the key.

So the package ships as **instrument repair**, and the rule question is open.

---

## 5. CAL-P134-2 — closed with a negative

`--by truth` needs cumulative-threshold OUTCOME legs. Measured across the whole
leg vocabulary of all four cells (`truth-site-negative.json`), the share of leg
rows parsing as a cumulative threshold is:

| cell | distinct legs | leg rows | cumulative rows | share |
|---|---|---|---|---|
| baseball | 2,355 | 57,869 | 14 | 0.024% |
| esports | 3,675 | 39,334 | 6 | 0.015% |
| soccer | 3,317 | 11,943 | 73 | 0.611% |
| basketball | 2,558 | 51,375 | 20 | 0.039% |

The arm is empty, as CAL-P135 predicted. **CAL-P134-2 is RETIRED**, with the
negative recorded rather than the item silently dropped.

**⚠️ It surfaced a THIRD site nobody has looked at.** Soccer's top leg names
include `1st half o/u 0.5`, `1st half o/u 1.5`, `1st half o/u 2.5` (89 rows
each) — an O/U ladder written **inside one market's outcome list**, which is
neither the name site nor the cumulative truth site. Parked as **CAL-P136-1**.

---

## 6. Files

| file | what |
|---|---|
| `pull_rows.py` | cached row pull, all three price legs + both identity columns |
| `legs-polymarket-*.json.gz` | the cached rows (gitignored) |
| `ou-book-fold.py` | the five-arm fold, the manufactured share, the arithmetic check, the holdout |
| `ou-book-fold.json` (+ per-cell) | its output |
| `truth-site-negative.json` | the CAL-P134-2 leg vocabulary census |

Re-running the analysis after the first pull is free; the pull is ~25 minutes of
production load for all four cells.
