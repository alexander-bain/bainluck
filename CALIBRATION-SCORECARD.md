# CALIBRATION SCORECARD

## 🎯 THE NEEDLE: **29 / 49 cells at bar** — `2026-08-28T20:37:41Z`

*Cells at bar = material cells (n ≥ 1,000) NOT queued, scored against the bars Alex ratified on
2026-08-28: **A 2.5 pp / B 3.0 pp / C 3.0 pp** (§1b). **FIXED = 49/49 AND Alex's eyeball on the
calibration page confirming it is up to standard.** His sign-off is the final gate, not the number
alone. Series starts here.*

**Published curve: 1.89 pp** (`mce_closing_line`, CI [0.87, 1.98]) — **🟡 → FLAT-TO-WORSE over 30 days.**
1.23 pp (2026-07-24) → 1.88 pp (2026-08-20) → 1.90 pp (2026-08-27) → 1.90 pp (2026-08-28 `17:33Z`)
→ **1.89 pp (2026-08-28 `20:37Z`)**. The last point is the first DOWN move this page has recorded
— queued excess-outcomes 480,342 → **455,783** on the old flat bar — and it is **drift, not
progress**: nothing has shipped into the producer since 2026-08-13. See §3.

*Re-run: `python3 backend/scripts/calibration_scorecard.py --live --record --markdown`.
Everything on this page is folded from the payload `https://api.bainluck.com/api/calibration`
actually serves. There is not a single holdout, sample, or parallel-rail number on it.*

> **CAL-P110, 2026-08-28 — this instrument was not on `master`.** §9 step 1 says *"re-run after
> every calibration deploy"*, and until today that was unexecutable by anyone but this branch:
> `backend/scripts/calibration_scorecard.py` and this page existed only on
> `program/calibration-99`, which cannot merge (842 lines in a frozen file). CAL-P108 is **new
> files only** — zero `backend/app/` lines — so it is re-cut freeze-clean onto
> `program/calibration-111` and merges without engaging ruling 009. **A measurement rail trapped
> behind the thing it measures is the §4 finding wearing an instrument's coat.**

> **CAL-P111, 2026-08-28 16:40Z — the freeze's lift condition is amended and #2248 is closed.**
> Alex ruled #2248's option 1 by MC: ruling 009 clause 2 changes shape from *~13 CONSECUTIVE clean
> beats* to **22 of the last 24**, with the baseline moving from CAL-P024 to the deploy carrying the
> CAL-P109/P110 phase-budget repair. Blocker 3 is no longer a deadlock — it is a countdown that
> starts when that deploy lands. **No number on this page moved, and the payload's `generated_at`
> is still `15:34:39Z`, so no datapoint was banked** — a ruling is not a publish, and recording one
> would be the exact fake `--record` exists to prevent. Full reasoning, both probabilities, and why
> 22/24 rather than 21/24: the amendment in `docs/rulings/009-precompute-calibration-freeze.md`
> and §5b below.

> **CAL-P112, 2026-08-28 — the countdown started, and the two cancelling cells have designs.**
> `program/calibration-110` + `-111` merged and deployed as **Heroku v3921 (`9ae282a7`) at
> `2026-08-28T18:55:19Z`**, which is the ruling-009 baseline: read it with
> `calibration_freeze_score.py --baseline-at 2026-08-28T18:55:19Z` (right now **0/24,
> WINDOW_NOT_FULL** — the ring holds 168 observations and every one of them is pre-baseline).
> Three things banked, none of them touching the frozen file: the **per-cohort threshold table**
> for Alex's ratification (§1b), and **ready-to-land rule designs for `polymarket/esports` and
> `kalshi/tech`** (§6a) — the ±cancellation pair from §2, which turn out to be **one structural
> defect pointing in two directions**. Published number **1.90 pp, unmoved**; a fifth datapoint was
> banked because the curve genuinely regenerated (`17:33:03Z`), not because anything was fixed.

> **CAL-P114, 2026-08-28 — rank 2 is designed, and the rail it needed did not exist.** The gates
> are still shut: the freeze score reads **1 post-baseline beat, WINDOW_NOT_FULL**, so this is a
> pre-build queue, not a landing one. Three things banked, none touching the frozen file.
> **`calibration_cell_exact.py`** folds a cell through the producer's OWN CTE chain — imported,
> not re-implemented — and reproduces four cells to ±1.22% on n with ECE and gap identical at two
> decimals; it exists because the CAL-P112 census reads `kalshi/economics` at **+4.27 gap against
> the payload's −0.47**, and *ranked that cell's sub-classes anyway*, producing a monotone
> price-staleness "mechanism" the exact rail **reverses**. **`kalshi/economics`** (rank 2, 65,524
> excess-outcomes) is the third and largest instance of CAL-P112's non-partition-bundle defect —
> 99.7% cumulative index ladders, one market publishing 76 rungs at a price sum of 72.48 — and
> rules E+E2+E3 take it **5.29 → 2.61 pp, PASS, with 1,641 rows still above the materiality
> floor**: the first cell on this board whose fix leaves it passing rather than absent. And the
> measurement **forces one correction on CAL-P112's banked design** — the bundle allowlist must be
> keyed on `(source, category)`, because category-only scoping fixes rank 2 and takes
> `polymarket/economics` from 3.91 to **17.75**. CAL-P112's parked `polymarket/tech` debt is
> discharged in passing (and its predicted direction was wrong). Published number **1.89 pp**,
> down 0.01 on population drift with nothing shipped — recorded as drift, in §3.

> **CAL-P115, 2026-08-28 — the ratified bar is WIRED, and the two instruments now agree by
> construction.** CAL-P114 closed with the ratification on the page and the flat 3.0 pp still in
> the code, and said so out loud: *"ratified-but-still-rendering-the-old-bar is the
> prose-thresholds-rot failure this program keeps paying for."* It is closed. `GAME_CATEGORIES`,
> the three classes, `CLASS_BARS_PP` and `classify()` moved **down into
> `calibration_scorecard.py`** — the instrument that publishes this page — and
> `calibration_threshold_table.py` now IMPORTS them instead of owning them. **§1, §3 and §6 below
> are re-rendered at the ratified bars on the same `20:37Z` curve**, so the change is a threshold
> change and nothing else: 30/49 → **29/49**, 19 → **20** queued, 455,783 → **478,677**
> excess-outcomes, and the single cell that moves is `odds_api_bookmaker/icehockey_nhl`, exactly as
> CAL-P112 predicted and CAL-P114 restated. Three properties are now pinned by tests rather than by
> prose: the bars are **imported, not re-declared** (`is`, not `==` — an equal copy drifts on the
> next edit); the table **cross-checks itself against the scorecard on every run** and exits 1 on
> disagreement; and the **NEEDLE is emitted from the scorecard's own counts**, so the line Fable
> copies and this page's DONE verdict cannot come apart. Mutation-checked: reverting one line to
> the flat bar reds **6 tests across both suites**. Nothing in `backend/app/` was touched, so
> ruling 009 is not engaged and no number here is a deploy claim.

> **CAL-P116, 2026-08-28 — the queue's ship was ALREADY LANDED, and the countdown has spent half
> its miss budget.** This queue was staged to amend ruling 009's lift condition *where lanes read
> it*, on the premise that `docs/rulings/009-precompute-calibration-freeze.md` still said
> *"~13 consecutive clean beats"*. **It does not, and had not since CAL-P111.** The amendment is on
> `master` (`5ad6f851`), deployed in v3921, indexed in `docs/PRODUCT-BRAIN.md`, executable as
> `calibration_freeze_score.py`, and **#2248 was already CLOSED** at `18:55:14Z` citing it. Both
> required probabilities are documented (**5.6 × 10⁻⁶** at the broken 0.472 rate, **0.884** at a
> healthy 0.95). Nothing was re-amended: re-deriving a landed ruling would have produced a second
> conflicting text of a decided condition, which is the failure the single-file ruling layout
> exists to prevent. Verified rather than assumed — the doc, the index line, the closed issue, and
> `263 passed` across the freeze-score, PRODUCT-BRAIN, doctrine-clause, gotcha-numbering and
> startup gates (RULING-CLAIMS digest `33fee2691a40`, 121 claims, 0 deviations). **The one live
> finding is the countdown**: at `21:42Z` the freeze score reads **1/2 clean, 1 of 2 allowed misses
> already charged** with 22 beats still to come (§5b). Published number **1.89 pp, unmoved** on the
> same `20:37:41Z` curve — no datapoint banked, because nothing regenerated and nothing shipped.

> **CAL-P117, 2026-08-28 — rank 1 is designed, its inherited mechanism was not the mechanism, and
> the countdown's budget is spent.** The gates are still shut (`WINDOW_NOT_FULL`), so this is a
> pre-build queue. Two things banked, neither touching the frozen file. **`polymarket/baseball`**
> (rank 1, 78,782 excess-outcomes — the largest cell on the board) is designed to a **PASS**: rule
> **K′ takes it 4.71 → 2.71 pp on both holdout halves**, and the board's four designed cells now
> carry **45.6% of all queued excess-outcomes**. The finding that mattered is that **the two
> mechanisms this cell was carried on are worth −0.53 pp and are the wrong ones** — they were
> diagnosed on a subcohort that is 3.1% of the published cell, 98% of what they remove is in the
> OLD half, and rank 1's live defect is a *writer* that replaces a real prop price with a
> manufactured coin flip inside 36-leg `Player Props` containers (`corr(published, opening)` 0.677
> vs 0.897; 6.2x more legs published at ~0.50 than opened there). **The pooled ECE and the holdout
> disagreed four separate times and the holdout was right every time** — the best pooled policy in
> the document (2.16) leaves the OLD half at 5.13. §6c. And the **freeze countdown has spent its
> whole miss budget at 3 beats** (1/3 clean, 2 of 2 misses charged, 21 to come): this window can now
> only be satisfied by 21 consecutive clean beats, which is 1.4 × 10⁻⁷ at the pre-fix rate. Both
> misses read `not_attempted` — the beat never reached its gate. §5b. Published number **1.89 pp,
> unmoved** on the same `20:37:41Z` curve; no datapoint banked, because nothing regenerated and
> nothing shipped.
>
> **Then Alex ruled rank 2 mid-session** (queue 017, option **b**): `kalshi/economics` is
> **APPROVED WITH DISCLOSURE** — the ladders leave the curve *and* the removed rows are named and
> counted on the page. First of the four banked designs to have its decision taken. Because the
> exclusion and its disclosure are one deliverable and only one of them is behind the freeze, **the
> page half was built here and is green**: the new `nonexclusive_bundle_filter` block renders
> nothing until the backend key exists, and 6 mutation-checked tests hold the per-cell counts and
> the clause that stops a smaller curve being read as a fixed one. §6d.

> **CAL-P118, 2026-08-29 — the flagship rule was measured against the published cell and it makes
> the cell WORSE.** The gates are still shut (`WINDOW_NOT_FULL`), so this is a pre-build queue.
> `polymarket/soccer` (rank 4, 44,857 excess-outcomes) is the cell §7 named as *"the first test of
> the loop"* and predicted at **−0.28 pp**, *"the largest published improvement this program would
> have made since 2026-08-01."* Folded through the producer's own chain with the shipped predicate
> imported rather than restated, it is **+0.03 pp — wrong in sign — and worse on both holdout
> halves and on every variant tried** (§6e). The mechanism is real: 3,989 published outcomes at ECE
> **9.57** against a cell at 2.89. It cannot be removed, because in **7 of 10 buckets its error has
> the opposite sign to the rest of the cell** and was cancelling it. **Rank 4 loses its ✅ and §7 is
> rewritten rather than annotated.** Two structural findings came out of the same fold. First,
> **81,291 condemned markets produce 3,989 published outcomes** — an O/U ladder *is* a `group_id`
> cluster, so `virtual_market` had already collapsed it and the rule's reach into the curve is 7.4%
> of the cell, not the 100% a subcohort implies. Second, **CAL-P117's stated cause for the exact
> rail's row shortfall is disproven** (0 of 7,484 group clusters and 0 of 2,103 event clusters
> change size under the category conjunct; 1 of 92,771 markets is demoted by chunking) and the
> payload's own `staged` block names the real one: the curve is a mosaic of **128 units banked at
> `20:35:54Z` of which 109 have drifted**, republished under `frozen_over_drift`. That is also why
> the number is flat — **the `23:35:51Z` beat publishes the same `20:35:54Z` population as the
> `20:37:41Z` beat.** §6e and CAL-P118-1. Published number **1.89 pp, FLAT**, on a genuinely new
> curve (`23:35:51Z`, q268) carrying the same staged generation.

> **CAL-P119, 2026-08-29 — the second cell is RULED, and its exclusion is the first one on this
> board that is designed to end.** Alex ruled `polymarket/baseball` (rank 1, the largest cell on the
> board): **EXCLUDE NOW + FIX WRITER**. The miswritten Player-Props rows leave the published curve
> with the same named, counted disclosure as `kalshi/economics` — **rank 1 crosses off, 4.71 →
> 2.71 pp, cell stays material** — and the writer that produced their prices is being repaired in
> parallel by lane1 queue 022. **The pair is now decided: ~5.7% of the published curve, ruled as a
> pair rather than as two separate 3%s**, which is what §6c asked for. 🔴 **The two exclusions are
> not the same kind and the page must not flatten them.** Rank 2's rows were *never forecasts of a
> single question* — structural, permanent. Rank 1's rows are **real questions whose published price
> our own writer manufactured** (a leg quoted 0.0355 published at 0.5005) while the market's quote
> stayed intact — so its exclusion is **TEMPORARY BY DESIGN: when the writer is repaired the rows
> return and the exclusion empties itself.** The disclosure surface gained one field for exactly
> that (`temporary_by_cell`, keyed per cell, valued with the condition that ENDS the exclusion),
> it is **empty for rank 2 deliberately**, and it is rendered from the payload so the sentence
> disappears on its own when the backend stops emitting the cell. §6f. Published number **1.89 pp,
> FLAT** — a fourth beat (`00:36:47Z`) on the *same* `20:35:54Z` staged population, now
> **`units_drifted` 128 of 128**, so CAL-P118's finding did not merely hold, it completed.

---

## 0. Why this page exists, and what it replaces

Alex, 2026-08-27: *"We haven't made any tangible progress on calibration in months, if anything
it's regressed... I'd strongly prefer to get to a point where calibration is just FIXED."*

That sentence is now **measured, and it is correct.** The measurement is in §4.

Every calibration instrument this program has built until now measures a *different population
than the one users see*:

| instrument | what it folds | is it the published curve? |
|---|---|---|
| `fold_cohort_cell_eligible.py` → the 21-cell board in `artifacts/subcohort2/SUBCOHORT_DIAGNOSIS.md` | `source='polymarket'` only, `market_type IN (quantity, container_member)`, 11 leagues, applying **1 of the curve's 13 live exclusion filters** | **No** |
| `calibration_published_twin.py` | the real published predicate — the right idea | **In principle yes; in practice no.** Last production run 2026-08-25 died on a statement timeout at 241 s against a 240 s budget, and has never returned a measured verdict |
| **`calibration_scorecard.py` (this page)** | the served payload's own `buckets`, pooled to the published cell | **Yes, by construction** |

The board is not wrong — it is a real measurement of a real population. But it is not the page, and
a cell can be fixed on it without one published number moving. That is what happened (§4).

### The instrument proves itself before it reports

`/api/calibration` ships a `buckets` array *and* its own pre-aggregated `by_category` / `by_source`
cells. The script re-derives the second from the first and **refuses to print anything if they
disagree**. Today: **34/34 `by_category` and 7/7 `by_source` cells reproduced exactly**, on both
ECE and n.

That check is the whole warrant for this page, and it earned its keep on the first run: the
published fold pools `(source, category, price_moved, bucket_idx)` rows into **10 bins per cell**
before taking the error. Folding at bucket-row granularity instead — the obvious first
implementation — got **34 of 34 cells wrong, every one high** (soccer 2.80 → 3.91, hockey
0.95 → 2.32). A silently-inflated scorecard is worse than no scorecard.

---

## 1. DONE — the finish line, in one table

*Each threshold is one line in `backend/scripts/calibration_scorecard.py`; changing one re-renders
this page. **Criterion 1 was ratified by Alex, MC, 2026-08-28** — the rest still stand as proposed.*

| # | criterion | threshold | rationale |
|---|---|---|---|
| 1 | **Per-cell bar** ✅ RATIFIED | published cell ECE ≤ its **cohort's** bar — **A 2.5 / B 3.0 / C 3.0 pp** (§1b) | 3.0 pp is reader actionability: a market published at 60% lands 57–63%, inside what a person can act on. It is also the bar the program already ranked against for four weeks (`n × (ece − 3)`), so banked mechanisms stay comparable to their own history. Class A is held tighter for the one *structural* reason available — an `odds_api*` price is a devigged consensus of many books, so its idiosyncratic quoting error is smaller by construction. |
| 2 | **Materiality floor** | cells with **n ≥ 1,000** outcomes | The payload's **own** floor — `min_category_outcomes: 1000` is what the curve already uses to decide a category is big enough to publish. Scorecard scope and page scope are then the same set. Cost: 49 of 287 cells clear it and they carry **95.6% of all published outcomes**. |
| 3 | **Significance gate** | excess over bar ≥ **2.0σ**, σ = `50/√n` pp | The program's own board found the defect this prevents: *"15 of the 21 are under 3σ, and three are under 1σ."* On today's payload it cuts the material over-bar list from 32 cells to **20**, so it is doing real work. |
| 4 | **Overall headline** | `mce_closing_line` ≤ **2.0 pp** | **A regression guard, not a goal.** Set where the curve already sits, because the honest finding is that the headline was never the problem — see §2. |
| 5 | **The curve must be live** | `availability: "ok"`, `producer.stalled: false` | A number nobody can refresh is not a published number. **Currently RED** — see §5. |

> **FIXED** is a **conjunction of a measurement and a human**:
>
> 1. criteria 1–3 satisfied on **every material cell**, with 4 and 5 green, **on the published
>    curve**, holding across two consecutive producer beats — i.e. **49/49 cells at bar**; AND
> 2. **Alex eyeballs the calibration PAGE and confirms it is up to standard.** *(Added with the
>    2026-08-28 ratification, §1b.)* **His sign-off is the final gate, not the number alone.**
>
> The scorecard reports clause 1 and calls it `done`, never `fixed`, because no script can
> evaluate clause 2. Clause 2 also puts **the page's presentability in scope as cells land** — it
> is not a thing to start caring about at 48/49.

**Today: NOT DONE. 20 material cells are over bar and established. 29/49 cells at bar.**

## 1b. The per-cohort bar — ✅ RATIFIED (Alex, MC, 2026-08-28 ~1:15pm PT)

> **Alex ratified the table as proposed: A 2.5 pp / B 3.0 pp / C 3.0 pp**, and added a clause that
> is now part of the definition of DONE:
>
> > **At 49/49, Alex eyeballs the calibration PAGE and confirms it is up to standard. His
> > sign-off is the final gate, not the number alone.**
>
> So the finish line is a conjunction: every material cell at its class's bar **AND** a human
> looking at the page. Two consequences the lane has to carry from here: **the needle series
> starts at 29/49**, and **the page's presentability is in scope as cells land** — source
> attribution by venue name is ALLOWED there, per amended ruling 141.
>
> ⚠️ *Bookkeeping, recorded rather than assumed: **`docs/rulings/141-*.md` does not exist** — the
> ledger tops out at 137 on this branch and on `origin/master` (checked 2026-08-28). The
> permission itself is not in doubt; it is in Alex's ratification text above, which is the
> operative wording. What is missing is the filed ruling the text cites, so anyone following the
> citation lands on nothing. Not blocking — no cells have landed and the calibration page is a
> deliberate comparison surface either way — but it should be filed before the first venue name
> is put on the page on its authority.*

Criterion 1 above declares **one** bar for every cell; this table replaces it per cohort. Full
argument, derivation and side-by-side: **`artifacts/cal-p112/THRESHOLD-TABLE-PROPOSAL.md`**.
Re-render with `python3 backend/scripts/calibration_threshold_table.py --live --markdown`.

> ✅ **WIRED — CAL-P115, 2026-08-28.** CAL-P114 shipped the ratification as prose with the flat
> 3.0 pp still in the code, and flagged the gap in the section it affected rather than leaving it
> latent. It is now closed. The classes, `CLASS_BARS_PP` and `classify()` live in
> **`calibration_scorecard.py`** — the instrument that publishes this page — and
> `calibration_threshold_table.py` imports them. **§1, §3 and §6 are the ratified numbers.**
>
> | | cells at bar | queued | queued excess-outcomes |
> |---|--:|--:|--:|
> | incumbent flat 3.0 — retired 2026-08-28 | 30/49 | 19 | 455,783 |
> | **RATIFIED 2.5 / 3.0 / 3.0 — live, and what this page renders** | **29/49** | **20** | **478,677** |
>
> Same `20:37Z` curve on both rows, so the delta is a threshold change and nothing else. The one
> cell that moves is `odds_api_bookmaker/icehockey_nhl` (3.89 pp on 8,658 — 1.65σ over the flat
> bar, **2.6σ over class A's**), exactly as CAL-P112 predicted. **`kalshi/economics` is class C, so
> its bar stays 3.0 and CAL-P114's design (§6b) is unaffected.**
>
> Three properties are held by tests now, not by prose. The bars are **imported, never
> re-declared** — pinned with `is` rather than `==`, because an equal copy passes an equality check
> and drifts on the next edit. The threshold table **cross-checks itself against the scorecard on
> every run** (counts *and* the queued cell SET) and exits 1 on disagreement. And the **NEEDLE is
> emitted from the scorecard's own counts**, so the line Fable copies into YOUR-TURN cannot come
> apart from this page's DONE verdict. Reverting one line to the flat bar reds 6 tests across both
> suites — checked, not assumed.

| class | what a cell in it is | **bar** | derivation |
|---|---|--:|---|
| **A** `A_multibook_consensus` | every `odds_api*` cell | **2.5 pp** | the price is a devigged consensus of MANY bookmakers — an average of independent estimates, so its idiosyncratic quoting error is structurally smaller than one thin order book's. Structural, fixed in advance, does not move as cells improve. These cells also carry the game cards. |
| **B** `B_exchange_contest` | Kalshi/Polymarket on a scheduled contest | **3.0 pp** | reader actionability: 3 pp means a 60% market lands 57–63%. A property of what a person does with the number, not of the venue. |
| **C** `C_exchange_standalone` | Kalshi/Polymarket, standalone / long-horizon | **3.0 pp** | **no loosening.** Thin books and distant settlement raise the VARIANCE the σ gate already prices; they do not license a larger BIAS — and the class's own cells prove 3.0 reachable (`polymarket/weather` **1.64** on 24,333, `kalshi/politics` **2.12** on 7,302 — `20:37Z` curve). |

**Per class, on the `20:37Z` curve** — `python3 backend/scripts/calibration_threshold_table.py --live --markdown`:

| class | bar pp | material cells | at bar | queued | outcomes |
|---|--:|--:|--:|--:|--:|
| `A_multibook_consensus` | **2.5** | 18 | 12 | **6** | 104,984 |
| `B_exchange_contest` | **3.0** | 20 | 12 | **8** | 653,418 |
| `C_exchange_standalone` | **3.0** | 11 | 5 | **6** | 115,734 |

**The finish line barely moves, and that is the point:** the ratification closes a hole where the
most-averaged, most-read class was held to the same bar as a thin exchange book. It explicitly
REFUSES the quantile derivation ("the bar is the class's p25") because a bar that moves whenever a
cell improves is not a finish line — the derivation has to come from outside today's measurement,
and only two such quantities were available (reader actionability, estimator averaging).

> **Criterion 6, proposed with it — NOT ratified.** A cell whose published population is dominated
> by non-partition bundle rows is queued for a **population** fix, not scored as a calibration
> failure — evidence-gated per cohort on the census the payload already publishes. Without it the
> two worst cells on the board (§6a) get worked as calibration problems, which is a cycle each and
> moves nothing. Alex's 2026-08-28 MC ruled the *bars*; this clause is still awaiting one.

---

## 2. The headline is not the problem — dispersion is

`mce_closing_line` is **1.89 pp**, already inside criterion 4. It is also close to meaningless as a
progress measure, and this is the single most important thing on this page:

**it is a pooled average over 287 cells whose errors point in opposite directions and cancel.**

*(`2026-08-28T20:37Z` curve, same reading as §3 and §6.)*

- `polymarket/esports` over-predicts by **+6.02 pp**
- `kalshi/tech` under-predicts by **−9.35 pp**
- `kalshi/football` under-predicts by **−3.97 pp**
- pooled, the page reports **1.89 pp**, as though all three were fine

A program steered by the headline can move cells in both directions forever and report a flat
number. **Publishing one headline as the definition of done is the exact move that let this
program report progress for months without a user-visible cell improving.** Criteria 1–3 are
per-cell for that reason.

---

## 3. The scorecard — today

*Scored at the **ratified** bars — A 2.5 / B 3.0 / C 3.0 pp (§1b), live in the code since CAL-P115.*

| | |
|---|---|
| curve generated | `2026-08-28T20:37:41Z`, population `q268` |
| published outcomes | **913,849** across **287** cells |
| headline `mce_closing_line` | **1.89 pp** (CI 0.87–1.98) — criterion 4 **PASS** |
| material cells (n ≥ 1,000) | **49**, carrying 874,136 outcomes (95.7%) |
| **🎯 CELLS AT BAR** | **29 / 49** |
| **over bar AND established (QUEUED)** | **20** cells, **478,677 excess-outcomes** |
| over bar, not established | 12 cells |
| under bar (pass) | 17 cells |
| exempt (n < 1,000) | 238 cells |
| `availability` | **stale**, but `producer_stalled: false`, `beats_missed: 0` — see the §5 amendment: this reading is a coin flip on when you look, not a verdict |
| self-check | `by_category: 34/34` and `by_source: 7/7` cells reproduced exactly |
| **DONE (measured half)** | **NO** — and FIXED additionally needs Alex's eyeball at 49/49 (§1) |

`excess-outcomes` = `(ECE − the cell's own class bar) × n`. It ranks the queue, because a 22 pp
cell over 118 rows and a 0.5 pp cell over 100,000 are not the same repair job. **Since the
ratification the multiplier is not one constant** — a class-A cell's excess is measured from 2.5,
so the queue's ranking mixes two bars and every row in §6 prints the bar that judged it.

### Time series — the whole history that exists

> ⚠️ **The bar column is load-bearing: this series changes UNITS on 2026-08-28.** Every point up to
> and including `20:37Z (P114)` was scored against a flat 3.0 pp; from the ratification onward the
> bar is per-cohort (§1b). **Queued counts are not comparable across that line** — the last two
> rows are the SAME curve measured twice, once under each definition, which is the only honest way
> to carry the discontinuity. `--record` banks the thresholds with every datapoint from now on, so
> a future reader cannot mistake a threshold change for a movement.

| date | bar | headline | population | queued cells | queued excess-outcomes | cells at bar | source |
|---|---|---:|---|---:|---:|---:|---|
| 2026-07-24 | flat 3.0 | **1.23 pp** | pre-`q268` | — | — | — | `docs/audits/calibration-robustness-2026-07.md`, live reading, headline only |
| 2026-08-20 | flat 3.0 | **1.88 pp** | `q268` | 17 | 436,754 | 32/49 | banked payload `artifacts/cal-p080/samples/cal-20260820T174018Z.json`, re-folded by this script |
| 2026-08-27 | flat 3.0 | **1.90 pp** | `q268` | 19 | 477,794 | 30/49 | live |
| 2026-08-28 `13:35Z` | flat 3.0 | **1.90 pp** | `q268` | **19** | **480,342** | 30/49 | live |
| 2026-08-28 `15:34Z` | flat 3.0 | **1.90 pp** | `q268` | **19** | **480,342** | 30/49 | live (CAL-P110) |
| 2026-08-28 `17:33Z` | flat 3.0 | **1.90 pp** | `q268` | **19** | **480,342** | 30/49 | live (CAL-P112) — banked, the curve really did regenerate |
| 2026-08-28 `20:37Z` | flat 3.0 | **1.89 pp** | `q268` | **19** | **455,783** | 30/49 | live (CAL-P114) — **the first DOWN move in the series** |
| **2026-08-28 `20:37Z`** | **A2.5/B3.0/C3.0** | **1.89 pp** | `q268` | **20** | **478,677** | **29/49** | **live (CAL-P115) — same curve, ratified bars. THE NEEDLE SERIES STARTS HERE.** |

> **The 20:37Z point is the first improvement this page has ever recorded, and it is not a win.**
> Headline 1.90 → **1.89**, queued excess-outcomes 480,342 → **455,783 (−24,559, −5.1%)**, queued
> cells flat at 19. **Nothing shipped into the producer between 17:33Z and 20:37Z** — the freeze
> is still on and no rule has been merged since 2026-08-13 — so this is population drift in the
> same class as the +0.02 pp drift of 08-20 → 08-27, pointing the other way. The population grew
> by 18,623 outcomes over the same three hours. It is recorded because the curve genuinely
> regenerated, and it is labelled drift because **a page that banks drift as progress is the
> thing this page was built to stop.** The board also reshuffled: `kalshi/economics` passed
> `polymarket/esports` into rank 2, `kalshi/football` left the queue, and
> `polymarket/economics` entered it at rank 13. *(Those ranks are the flat-bar board; on the
> ratified bars — §6 — the same reading orders `polymarket/economics` at 15 and adds
> `odds_api_bookmaker/icehockey_nhl` at 13.)*

**Five points is the entire published-curve history this repo holds, and that is itself a
finding.** Nobody ever banked the served payload on a schedule, so "did the last three months
improve the numbers users see?" was structurally unanswerable until today. `--record` fixes that
permanently: every run appends to `artifacts/calibration-scorecard/history.jsonl`, keyed on the
payload's own `generated_at` (never the wall clock — the producer stalls, and on 2026-08-20
fourteen hourly samples all carried the *same* `generated_at`, which would otherwise have drawn a
fourteen-point flat line out of one measurement).

**Reading the trend honestly:**

- **07-24 → 08-27 (+0.67 pp) is NOT clean.** Nine exclusion filters landed between those dates. A
  curve that excludes more junk and reports a *higher* error may be more honest, not worse. This
  comparison cannot separate the two, and is quoted here only because it is what "the last month"
  literally shows.
- **08-20 → 08-27 IS clean** — same `population_version` `q268`, same predicate, 7 days apart. It
  is the only apples-to-apples reading available, and it says:

| | 08-20 | 08-27 | Δ |
|---|---:|---:|---|
| headline | 1.88 | 1.90 | **+0.02 pp worse** |
| queued cells | 17 | 19 | **+2 worse** |
| queued excess-outcomes | 436,754 | 477,794 | **+41,040 (+9.4%) worse** |

Not a regression to panic over — but on the one window where the measurement is sound, **the
published curve did not improve, it drifted slightly backward.**

**08-27 → 08-28 (one day, same `q268`)** continues in the same direction and adds nothing to the
argument except that it has not turned: headline flat at 1.90, queued cells flat at 19, queued
excess-outcomes **477,794 → 480,342 (+2,548)**. Two of the queued cells moved on their own —
`kalshi/football` 5.26 → 5.51 and `polymarket/tech` 5.28 → 5.40 — which is drift in the underlying
population, not the effect of any merge. Nothing shipped into the producer between these readings.

---

## 4. Why: 40 merges, zero published movement

This is Alex's sentence, measured. Two facts, both independently checkable:

**Fact 1 — the calibration lane merges constantly.** 45 `program/calibration-*` merges into master
since 2026-08-01; **40 since 2026-08-13.**

**Fact 2 — the last time a rule changed the published population was 2026-08-13**, and the last
*substantive* batch was **2026-08-01**. Dated from master by first appearance in
`precompute_calibration.py`:

| filter live on the curve | landed |
|---|---|
| `liquidity_filter` | 2026-06-25 |
| `heuristic_filter` | 2026-07-06 |
| `golf_placeholder_filter`, `malformed_binary_filter`, `poly_placeholder_filter` | 2026-07-09 |
| `esports_multi_bundle_filter`, `soccer_2way_filter` | 2026-07-11 |
| `kalshi_prop_threshold_filter` | 2026-07-12 |
| `weather_wide_spread_filter` | 2026-07-13 |
| `draw_authority_filter`, `no_winner_filter`, `orphan_partition_filter` | 2026-08-01 |
| `void_filter` (datagolf-only, small) | 2026-08-13 |

**40 merges in 14 days, and not one of them changed what publishes.** The merged work was
instruments, censuses, workers, samplers, gates, and folds — measurement machinery. Diagnosis is
not the bottleneck and has not been for weeks; **the conversion from diagnosis to a deployed
exclusion is.** That is the whole finding, and it is the thing the new loop (§6) exists to fix.

### The unmerged rules, and what they are worth today: ZERO

Per the directive — *a rule that is not deployed and re-measured counts as ZERO.* Verified against
`origin/master`, not asserted:

| rule | built | certed | on master? | wired into the producer? | published delta |
|---|---|---|---|---|---|
| half-spike pair exclusion (CAL-P099) | ✅ | ✅ | ❌ **0 occurrences of `is_half_spike_pair` on master** (21 on this branch) | branch only | **0.00 pp** |
| published-pair coherence (CAL-P100) | ✅ | ✅ | ❌ **0 occurrences of `is_published_pair_incoherent` on master** | branch only | **0.00 pp** |
| O/U ladder coherence (CAL-P106/107) | ✅ | ✅ | ❌ `backend/app/utils/ladder_coherence.py` **absent from master** | ❌ **not referenced by `precompute_calibration.py` at all** | **0.00 pp** |

All three sit on `program/calibration-99` (11 commits, CAL-P099 → CAL-P107, unmerged). The ladder
rule is the furthest from publishing: it is not merged *and* nothing calls it.

---

## 5. Two blockers that must clear before the loop can run at all

> **AMENDED 2026-08-28 (CAL-P109, #2045) — Blocker 1 was mis-named, and the wrong name is why it
> kept "clearing" on its own.** The producer is not stalled. It is **flapping**, and the distinction
> changes what has to be fixed. Measured from `calibration:beat_gauge_history`, 164 beats:
> **77 complete, 61 failed, 26 cancelled — a per-beat publish rate of 0.4695.** It publishes about
> half the time, which is why `calibration_publish_age` (which fires on two consecutive misses)
> fired on 08-25, 08-26 and 08-27 and then went quiet each time with nobody fixing anything. Any
> reading of `producer.stalled` is a coin flip on when you looked: at 13:35Z today it published,
> and the scorecard run below records `producer_stalled: false, beats_missed: 0` — while the
> underlying defect was entirely unfixed. **Root cause, deployed fix and evidence: see §5a.**

**🛑 BLOCKER 1 (as first written) — the producer is stalled.** `producer.stalled: true`,
`beats_missed: 6`, `availability: "stale"`, `cache.reason: "main_key_absent"`,
`staged.frozen_over_drift: true`. The curve on the site was generated at 16:33Z and has not
refreshed in ~6 hours against a 1 h interval.

This is not a side note — **it makes the directive's loop unexecutable.** "MERGE → DEPLOY →
re-measure the published curve" cannot produce a delta if the published curve does not rebuild. A
rule could ship perfectly today and the scorecard would read identically tomorrow, which reads as
"the rule did nothing" and is indistinguishable from it. It also silently corrupts the trend line:
the 2026-08-20 sample shows the same freeze (14 hourly samples, one `generated_at`).

**🛑 BLOCKER 2 — the published-curve twin cannot run.** `GET /admin/calibration-twin/last` returns
`measured: false`, last artifact 2026-08-25, `QueryCanceledError: canceling statement due to
statement timeout` after 241 s against a 240 s budget. The twin is the only rail that can score a
*candidate* rule against the published population **before** merging it — i.e. the only way to
predict a published delta instead of discovering it afterward. Without it, every rule is shipped
blind and §6's step 4 is a coin flip.

> **🔓 BLOCKER 3 IS ANSWERED — CAL-P111, 2026-08-28.** Alex ruled #2248 by MC: **amend the lift
> condition, do not simply lift it.** Clause 2 is now **22 of the last 24 beats publish cleanly**,
> measured from the deploy carrying the CAL-P109/P110 phase-budget repair. Everything below is
> preserved as written because it is the diagnosis the ruling was made on; the deadlock it describes
> is real and is now broken from the other end. **The freeze is still ON** — the amendment changed
> the condition's shape, not its status. §5b carries the numbers.

**🛑 BLOCKER 3 (as first written) — and this one is a DEADLOCK, not a bug.** `docs/rulings/009` freezes
`backend/app/tasks/precompute_calibration.py` — the file every exclusion rule must ship into — and
names exactly one lift condition:

> *a fresh publish post-CAL-P024 **AND** ~13 consecutive clean beats with no regression.*

**The producer has missed 6 beats and is stalled.** It cannot produce 13 consecutive clean beats,
so the freeze cannot lift, so no rule can ship into the producer, so the published curve cannot
move. Ruling 011 is queued behind the same condition. No lift is recorded anywhere in `docs/`.

> **AMENDED 2026-08-28 (CAL-P109) — the deadlock is now MEASURED, and it is worse than "stalled"
> implied.** A stalled producer is a thing you notice and fix. A producer at a 0.4695 publish rate
> looks healthy every other hour and never lifts the freeze, because the lift condition is a
> *conjunction over 13 beats*:
>
> | | |
> |---|---:|
> | per-beat publish rate (164 beats) | **0.4695** |
> | longest clean run actually observed | **9** |
> | run-length histogram | 1×11, 2×9, 3×2, 4×2, 5×2, 7×1, 8×1, 9×1 |
> | P(13 consecutive) at this rate | **5.4 × 10⁻⁵** — 1 in 18,561 attempts |
> | at ~24 beats/day, expected wait | **~2 years** |
>
> Ruling 009's lift condition has therefore never been satisfiable in practice, and no amount of
> waiting would have satisfied it. **This — not a shortage of diagnosis — is the mechanism behind
> §4's "40 merges, zero published movement".** The lane could not ship into the producer because
> the freeze could not lift, and the freeze could not lift because the producer lost half its
> beats to a one-second budget error. Raising the publish rate is the *precondition* for §4's
> finding to stop reproducing itself, which is why CAL-P109 outranked every cell in §6.

This is the mechanism behind §4. The lane has not been idle — it has been merging everything it is
*allowed* to merge (instruments, censuses, workers, samplers, all in unfrozen modules), because the
one file that changes what publishes is sealed by a condition only a healthy producer can satisfy.
**40 merges and no published movement is what a program looks like when it is working around a
deadlock instead of breaking it.**

> ~~⚠️ **One unresolved tension, flagged rather than resolved:**~~ **RESOLVED — CAL-P111,
> 2026-08-28.** `program/calibration-99` carries **842 changed lines** in that frozen file
> (CAL-P099/P100). The question was whether the freeze was being worked under unrecorded escalations
> or treated as lapsed. **Neither.** Alex declined #2248's option 3: the 842 lines are *not*
> retroactively sanctioned. They are unmerged work against a frozen file, they become mergeable when
> the amended condition is met and the lift is recorded, and not before. The freeze was never lapsed
> and no undocumented escalation is ratified after the fact.

*This scorecard works around Blockers 1 and 2 — it reads the served payload, so it needs neither.
It cannot work around Blocker 3.*

---

## 5a. Blocker 1, diagnosed and fixed — CAL-P109 (#2045)

**The beat was dying in `sports`, and the log said `futures`.**

`derive_plan` budgets each phase at `max(observed) × 1.5`. When the declared total overruns the
window it scales **every** phase by the same factor. `futures` alone declares more than the whole
window (~1.95M ms of 1.38M), so the factor landed at **0.617** — and the four phases that did not
cause the overrun were each cut to ~62% of their own worst measured completion. From production's
ledger, generation `1787924136928`:

| phase | budget | stmt timeout | slowest completion | floor ring (durations at which it was CANCELLED) |
|---|---:|---:|---:|---|
| `sports` | 3,391 ms | **3,052 ms** | 3,661 ms | **ten entries, 3,137–4,180 ms** |
| `diagnostics` | 174,535 ms | 157,082 ms | 188,401 ms | 4,512–116,002 ms |
| `aggregate` | 87 ms | 79 ms | 94 ms | — |
| `serialize_gate_publish` | 531 ms | 478 ms | 574 ms | 1,817–3,732 ms |

Sports was bounded **below every duration at which it had already been cancelled.** Its
`read:events` query — the ground-truth moneyline scan over `events` — hits that bound on any
ordinary-slow beat, Postgres cancels the statement, and the whole beat dies, discarding a `futures`
phase that had already completed. Over about one second.

**The fix charges the overrun to the one phase that can pay it.** `futures` runs a unit loop that
asks `_unit_fits_in_window` before each unit and stops between them with everything banked — a
smaller budget costs it *units*, and the next beat resumes from the cursor. Every other phase is
one statement, or a fixed sequence of them, with no partial credit. So the inelastic phases keep
their measured budgets (sports 3,391 → **5,492**, a 4,943 ms bound, clear of its whole floor ring)
and futures absorbs the cut (1,192,139 → 1,090,904, about **0.66 of a unit per beat**). Nothing is
invented and nothing is scaled up.

**The second defect is why this took two investigations.** The failure log read
`"ended timeout after 1111181ms in phase group ['futures']"` — and the list it printed there was
`completed_required`, *the phases that finished*. Every beat that got through futures and died in
sports accused futures by name, in the first line anyone reads. Both this session and the previous
one opened on the futures budget because of it. Fixed by `PhaseLedger.failed_phase`.

**Status: committed to `program/calibration-99` (CAL-P109), NOT deployed.** Per this page's own
rule, an undeployed fix is worth **zero** until re-measured — so Blocker 1 stays 🛑 and criterion 5
stays RED on this run. What changes on deploy is testable in advance and stated here so it can be
checked rather than narrated: **the publish rate should rise from 0.4695, and the sports-cancellation
signature should leave Sentry** (`app.tasks.precompute_calibration_main`, 15 events / 24 h against
~12.7 expected failures/day — i.e. it dominates the failure population). If the rate does not move,
this diagnosis is wrong and §5a should be struck.

### 5a.1 — CAL-P110: the fix is re-cut so it does not need the freeze lifted

**`program/calibration-110` @ `a611347d` — MERGED as `3200b840` and DEPLOYED in Heroku v3921,
2026-08-28T18:55:19Z (CAL-P112 records the baseline in §5b).** CAL-P109 was unshippable for a
reason that had nothing to do with the repair: it sat on `program/calibration-99`, behind 842 lines
of CAL-P099/P100 in the frozen file. **The repair itself does not live there** — this page said so
above, and CAL-P110 acts on it. Two files, one under `backend/app/`, and
`git diff origin/master -- backend/app/tasks/precompute_calibration.py` is **empty**. Ruling 009 is
not engaged, so no ruling is owed before merging. The 13-line `logger.error` improvement is dropped
with the frozen file and is a one-commit follow-up once the freeze question is answered; the
fingerprint fixture, which tracks that file's `source_sha256`, correctly stays at master's
`1f9acd47`.

Gates: **20,537 passed / 112 skipped / 61 xfailed / 0 failed** (full backend suite, 14:05);
2,095 / 16 / 0 focused; `ruff` EXIT 0; merge-tree EXIT 0, zero conflict markers.

This is the shape the deadlock actually had. Ruling 009's lift condition needs 13 consecutive clean
beats, which a 0.47-rate producer reaches with probability 5.4 × 10⁻⁵ — so waiting for the freeze
to lift before fixing the producer was waiting for the producer to fix itself. **Shipping the half
that needs no ruling is what breaks that, and it was available the whole time.**

### 5a.2 — the gate-refusal class is REAL, BOUNDED, and already over

CAL-P109 noted that `serialize_gate_publish`'s floor ring is gate REJECTIONS rather than timeouts,
and left the phase on its measured budget. That call is now confirmed **and bounded**, which is the
part that was not known. All 166 beats in `calibration:beat_gauge_history`:

| terminal | gate | n | first | last |
|---|---|--:|---|---|
| complete | pass | 79 | 08-21T19:39Z | 08-28T15:34Z |
| failed | `not_evaluated` | 38 | 08-21T20:42Z | 08-28T12:33Z |
| cancelled | `not_evaluated` | 26 | 08-21T18:37Z | 08-28T01:21Z |
| failed | **`refuse`** | 23 | 08-24T07:44Z | **08-25T12:36Z** |

The refusal class cost 23 beats and **has not recurred in the ~75 beats since 08-25T12:36Z**. Per
day since: 08-26 `13 pass / 11 not_evaluated / 0 refuse`, 08-27 `14 / 10 / 0`, 08-28 `7 / 9 / 0`.
**Every beat lost today dies before the gate is evaluated** — precisely the population CAL-P110
addresses. A rule that fired 23 times over two days and never again is a closed second question,
not the live one, and it should not be worked ahead of the class that is still taking half of every
day's beats.

Confirmed independently of the ledger, from production's own exception — Sentry `BAINLUCK-132`,
latest event `2026-08-28T12:33:31Z`, `transaction = app.tasks.precompute_calibration_main`: the
cancelled statement is the `FROM events WHERE status IN ('completed','closed')` scan over
`closing_home_probability` / `closing_away_probability`. That is the `sports` phase's `read:events`,
named by the diagnosis and reached by a different route. Both Sentry issues last fired at
12:33:31Z, matching the last failed beat exactly.

**Pre-deploy baselines, banked so the falsifier can be read rather than argued:**

| signal | 08-26 | 08-27 | 08-28 |
|---|--:|--:|--:|
| beats published / total | 13/24 | 14/24 | 7/16 |
| `BAINLUCK-Y8` (build-ended-timeout) | 11 | 10 | 9 |
| `BAINLUCK-132` (`QueryCanceledError`) | 0 | 7 | 6 |

72 h per-beat publish rate: **34/72 = 0.472.** Note that `BAINLUCK-Y8`'s *title* will keep reading
`phase group ['futures']` after the deploy, because the log-wording fix went with the frozen file —
**judge it by count, not by wording.**

### Criterion 5 is RED for TWO independent reasons, and only one of them is the producer

Worth separating, because fixing the producer will **not** turn criterion 5 green on its own.
Criterion 5 reads `availability: "ok"` **and** `producer.stalled: false`. Today's run returns
`producer_stalled: false, beats_missed: 0` — and `availability: "stale"` anyway.

That word does not come from the producer. `availability_floor`
(`app/utils/calibration_staged_disclosure.py:300`) downgrades to `stale` whenever the staged
futures disclosure reports `frozen_over_drift`, which it does today: all 128 served units have
drifted and the rolling restage is in flight at ~85/128. The served bank is frozen until the
rebuild completes and promotes — roughly 7–8 more beats of futures progress, which accrues even on
beats that later fail (the 12:33Z failure banked 7 units with `bank_advanced_this_beat: true`).

Two consequences the loop has to plan around:

1. **Criterion 5 cannot go green until the restage promotes**, however healthy the producer is. If
   the intent of criterion 5 was "the curve is live", the staged-drift floor is a second,
   unrelated gate riding on the same word, and criterion 5 should probably be split. **Flagged for
   Alex — this page does not get to redefine its own finish line.**
2. **CAL-P109 slightly slows that promotion** — futures drops ~0.66 of a unit per beat — while
   roughly doubling the share of beats that publish. That is the intended trade and it is worth
   naming: the restage arrives a beat or so later, and about twice as many beats survive to serve
   it.

> ⚠️ **Freeze exposure, flagged not resolved.** CAL-P109's log fix touches
> `backend/app/tasks/precompute_calibration.py` — the file ruling 009 freezes — by 7 lines, all of
> them a `logger.error` message and its comment, with no behavioural change. That is additive to
> the 842 lines this branch already changes in that file, which §5 already escalated for an Alex
> ruling. It is called out again here rather than folded in quietly: **the budget fix itself lives
> entirely in `calibration_phase_ledger.py` and does not need the frozen file**, so if Alex holds
> the freeze strictly, the log change can be dropped without losing the repair.

---

## 5b. Blocker 3, ruled — CAL-P111 (#2248): the lift condition is 22 of the last 24

**Alex ruled #2248's option 1 by MC: amend the condition, do not simply lift it.** Ruling 009's
intent stands unchanged — *a known-good producer version runs undisturbed long enough to prove it
converges* — and so does the freeze. What changed is the shape of the measurement.

> **~13 CONSECUTIVE clean beats  →  22 OF THE LAST 24 beats publish cleanly**

Read it with `python3 backend/scripts/calibration_freeze_score.py` (CAL-P111, new file, freeze-clean).
Prose thresholds rot — this program has the receipts — so the condition is a predicate now.

### The two probabilities the amendment is required to state

Measured off `calibration:beat_gauge_history`, **166 beats**, 2026-08-21T18:37Z → 2026-08-28T15:34Z:
79 `complete/pass`, 38 `failed/not_evaluated`, 26 `cancelled/not_evaluated`, 23 `failed/refuse`.
**Publish rate 0.476.** Longest clean run **9**. Best 24-beat window **19/24**.

| publish rate | P(22 of 24) per window | expected wait |
|---|---:|---:|
| **0.472 — the broken pre-fix rate** | **5.6 × 10⁻⁶** (1 in 179,000) | ~20 years |
| 0.85 | 0.280 | 2.0 days |
| 0.90 | 0.564 | 1.3 days |
| **0.95 — a healthy producer** | **0.884** | **1.0 days** |

### The shape change buys DISCRIMINATION, not speed — and this page says so

At a healthy 0.95 rate the *original* condition actually closes faster (0.79 d vs 1.04 d). Anyone
reporting the amendment as "the freeze can now lift sooner" has it backwards. What it buys is
measured under a clustering-aware moving-block bootstrap of the real pre-fix sequence — 90-day
horizon, 3,000 trials, block lengths 12/24/36:

| condition | P(ever satisfied by the BROKEN producer in 90 days) |
|---|---|
| 13-consecutive (original) | **0.27 – 0.59** |
| 20-of-24 | 0.99 – 1.00 |
| 21-of-24 | 0.48 – 0.70 |
| **22-of-24 (chosen)** | **0.006 – 0.105** |
| 23-of-24 | 0.000 |

**A streak counter is a poor test of a rate**, because clustered misses leave long clean stretches
behind them — which is why the consecutive form was 5–45× *easier* for the producer this freeze
exists to exclude. 22 is the first value the measured pre-fix process does not reach; 23 was
rejected in the other direction (3.7 days at a 0.85 rate, one dyno-cycle pair of misses costs a
whole day) as re-creating a softer deadlock. M = 24 is one day of the hourly beat, so the condition
reads without arithmetic: **one full day in which the producer lost at most two beats.**

### This page's own number is corrected

**§5's "P(13 consecutive) = 5.4 × 10⁻⁵ — 1 in 18,561 — ~2 years of waiting" is an i.i.d. artifact**,
and so is the copy of it in #2248. The deadlock is real — the producer never did reach 13 in the
measured week — but its mechanism is *the observed rate*, not an astronomically small probability.
Corrected here rather than quietly dropped, because the amendment's own figures were derived the
same way and would inherit the same error unstated. This does not change Alex's decision; it changes
what the next lane is allowed to quote.

### Freeze score today, and what starts the countdown

```
RULING 009 FREEZE SCORE — 22 of the last 24
  9/24 clean   (15 misses; 2 allowed)
  ......#..#.#...#.#..####   <- oldest ... newest
  window   2026-08-27T17:35Z -> 2026-08-28T16:35Z          VERDICT  NOT_MET
```

**All 24 must post-date the baseline**, so the freeze cannot lift sooner than ~24 h after the
CAL-P109/P110 deploy, by construction — and the score above is pre-baseline, i.e. a measurement of
the broken producer, not a verdict. Whoever integrates `program/calibration-110` records the release
SHA and version here; that is the instant the window starts filling.

### 🟢 THE BASELINE IS RECORDED — the countdown is running (CAL-P112, 2026-08-28)

| | |
|---|---|
| release | **Heroku v3921**, `Deploy 9ae282a7` |
| deployed at | **2026-08-28T18:55:19Z** (11:55:19 PT) — this is the baseline instant |
| what it carries | `program/calibration-110` (`a611347d`, the phase-budget repair) **and** `program/calibration-111` (`5ad6f851`, this scorecard rail + the amendment), merged as `3200b840` then `9ae282a7` |
| read it with | `python3 backend/scripts/calibration_freeze_score.py --baseline-at 2026-08-28T18:55:19Z` |

```
RULING 009 FREEZE SCORE — 22 of the last 24
  0/0 clean so far (window 24)   (0 misses; 2 allowed)
  ring     168 observations, 168 excluded as pre-baseline
  VERDICT  WINDOW_NOT_FULL
```

**Earliest possible lift is ~2026-08-29T19:00Z (12:00 PT)**, and only if at least 22 of the first 24
post-baseline beats publish. The pre-baseline ring stands at 10/24 clean, which is a measurement of
the producer CAL-P110 was built to fix and carries no weight against the condition.

#### Re-read 2026-08-28 `21:42Z` (14:42 PT) — CAL-P116: **half the miss budget is spent at 2 beats**

```
RULING 009 FREEZE SCORE — 22 of the last 24
  1/2 clean so far (window 24)   (1 misses; 2 allowed)
  .#   <- oldest ... newest
  window   2026-08-28T19:40:52Z -> 2026-08-28T20:37:42Z
  ring     168 observations, 166 excluded as pre-baseline
  VERDICT  WINDOW_NOT_FULL
           only 2 post-baseline beats exist; the freeze cannot lift before 24 of them do
           (best still reachable: 23/24)
```

Two post-baseline beats exist and **one of the two budgeted misses is already charged.** That is not
yet a verdict — 23/24 is still reachable and a single early miss is exactly the unrelated-failure
case the amendment budgeted for, which is the whole reason the condition is a count and not a
streak. It is recorded because the number is the one thing a count-in-window gives that a streak
cannot (amendment, reason 2: *it is observable before it completes*), and because **the next miss
ends this window** — after a second, the earliest possible lift moves out by however long it takes
the ring to roll the misses off, not to 2026-08-29T19:00Z.

Read it, do not re-derive it:
`python3 backend/scripts/calibration_freeze_score.py --baseline-at 2026-08-28T18:55:19Z`.

**The falsifier is now live and must be read before anything is claimed** (§5a.2): the 72 h per-beat
publish rate has to rise from **0.472**, and the `sports` cancellation signature
(`BAINLUCK-132`, `QueryCanceledError` on the `FROM events WHERE status IN ('completed','closed')`
scan) has to leave Sentry. `BAINLUCK-Y8`'s title will keep saying `phase group ['futures']` because
the log-wording fix went with the frozen file — **judge it by count, not by wording.**

#### 🔴 Re-read 2026-08-28 `22:0xZ` (~15:00 PT) — CAL-P117: **the budget is SPENT at 3 beats**

```
RULING 009 FREEZE SCORE — 22 of the last 24
  1/3 clean so far (window 24)   (2 misses; 2 allowed)
  .#.   <- oldest ... newest
  window   2026-08-28T19:40:52Z -> 2026-08-28T21:33:47Z
  ring     168 observations, 165 excluded as pre-baseline
  VERDICT  WINDOW_NOT_FULL
           only 3 post-baseline beats exist; the freeze cannot lift before 24 of them do
           (best still reachable: 22/24)
```

CAL-P116 wrote *"the next miss ends this window"*. **It arrived at the next beat.** Both budgeted
misses are charged with **21 beats still to come**, so `reachable_if_all_remaining_clean` has fallen
to exactly **22/24**: this window can now only be satisfied if **every one of the remaining 21 beats
publishes cleanly**, with no margin of any kind.

| | |
|---|---|
| P(21 consecutive clean) at the pre-fix rate **0.472** | **1.4 × 10⁻⁷** |
| P(21 consecutive clean) at the prior-24 h rate **0.417** | **1.1 × 10⁻⁸** |
| P(21 consecutive clean) at a healthy **0.95** | **0.34** |

**So the honest reading is that the first window is, in practice, already lost, and the countdown
now depends on the ring rolling** — which is exactly the behaviour the count-in-window form was
chosen for and the streak form would have hidden. Nothing about the amendment is wrong; what this
measures is the *producer*.

**And the producer is the thing to look at, because both misses have the same shape:**

| beat | terminal | outcome |
|---|---|---|
| `19:40:52Z` | `failed` | `gate: not_evaluated`, `durable/volatile: not_attempted`, `published: false` |
| `20:37:42Z` | `complete` | `gate: pass`, `published: true` — this is the curve the whole page folds |
| `21:33:47Z` | `failed` | `gate: not_evaluated`, `durable/volatile: not_attempted`, `published: false` |

`not_attempted` on both halves means the beat **never reached the gate** — the phase-budget
starvation signature, not a gate refusal. Per-beat clean rate by era, off the same ring:

| era | beats | clean | rate |
|---|--:|--:|--:|
| 2026-08-21 22:35Z → 08-27 18:28Z | 141 | 69 | **0.489** |
| the 24 h before the baseline | 24 | 10 | **0.417** |
| **post-v3921** | **3** | **1** | 0.333 |

> ⚠️ **Three beats is not a measurement of a rate, and this page will not pretend otherwise.** The
> post-deploy figure is stated as a count, not as a refutation of CAL-P109's repair. What IS
> established at n=3 is the *budget*, which is a count and not a rate: it is spent. **The falsifier
> re-measure (§5a.2) is now the highest-value read on this page** — it needs ~24 more beats, i.e.
> roughly 2026-08-29 19:00Z, and until then no one should either claim the repair worked or claim
> it failed. `availability` on the served payload reads **`stale`** right now (`age_s` 7,262
> against a 3,600 s interval, `beats_missed` 2, `stalled: false`), so **criterion 5 is RED on the
> very payload every number on this page is folded from.**

#### Re-read 2026-08-29 `00:0xZ` (~17:00 PT) — CAL-P118: **five beats, and the ring must roll**

```
RULING 009 FREEZE SCORE — 22 of the last 24
  2/5 clean so far (window 24)   (3 misses; 2 allowed)
  .#.,#   <- oldest ... newest   (',' = cancelled)
  window   2026-08-28T19:40:52Z -> 2026-08-28T23:35:52Z
  ring     168 observations, 163 excluded as pre-baseline
  VERDICT  WINDOW_NOT_FULL   (best still reachable: 21/24)
```

CAL-P117 called the first window lost in practice. **It is now lost arithmetically**:
`reachable_if_all_remaining_clean` has fallen to **21**, below the required 22, so no sequence of
future beats can satisfy this window. The countdown depends entirely on the ring rolling the three
misses off, which needs 24 further post-baseline beats — **no earlier than ~2026-08-29 22:40Z**, and
that is a floor, not a forecast.

| beat | terminal | outcome |
|---|---|---|
| `21:33:47Z` | `failed` | `gate: not_evaluated`, `not_attempted` |
| `22:20:23Z` | **`cancelled`** | `gate: not_evaluated`, `not_attempted` — **a terminal state neither prior read has seen** |
| `23:35:52Z` | `complete` | `gate: pass`, `published: true` — the curve §6e folds |

**`cancelled` is new and it is not the starvation signature.** The three prior misses read `failed`;
this one was revoked or killed. Whether it is `task_time_limit` (a hard SIGKILL, untracked — the
`project_celery_sigkill_untracked` class) or a deliberate revoke is not established here and is not
this lane's to establish. It is recorded because **the falsifier due after ~19:00Z Saturday is a live
REVERT trigger, and a second failure mode inside the post-deploy window changes what that falsifier
is measuring.** Post-v3921 the count is **2 clean of 5** (0.489 over 141 pre-baseline beats). Five
beats is still not a rate.

> 🔴 **And the two clean beats published the SAME population.** `23:35:51Z` (q268) and `20:37:41Z`
> both carry `staged.staged_at = 20:35:54Z`, `units_banked 128`, **`units_drifted 109`**,
> `frozen_over_drift: true`, `rolling_restage: true`. Every cell reads identically across the two
> beats and the headline is 1.89 pp on both. **A clean beat is not a fresh measurement while
> `frozen_over_drift` holds the bank** — the freeze score counts publishes, which is what ruling 009
> asks of it, but this page must not bank a datapoint for a beat that republished a three-hour-old
> generation. It did not. See §6e.

#### Re-read 2026-08-29 `00:4xZ` (~17:4x PT) — CAL-P119: **six beats, two clean in a row, and the bank is now fully drifted**

```
RULING 009 FREEZE SCORE — 22 of the last 24
  3/6 clean so far (window 24)   (3 misses; 2 allowed)
  .#..##   <- oldest ... newest   ('#' = clean, '.' = miss)
  window   2026-08-28T19:40:52Z -> 2026-08-29T00:36:48Z
  ring     168 observations, 162 excluded as pre-baseline
  VERDICT  WINDOW_NOT_FULL   (best still reachable: 21/24)
```

**The ring rolled by exactly one** — 163 pre-baseline exclusions became 162 against a fixed 168
observations, which is the mechanic CAL-P118 said the countdown now depends on entirely. Nothing
else moved: 3 misses against 2 allowed, `reachable_if_all_remaining_clean` still **21**, still below
the required 22, so **this window remains arithmetically lost** and the earliest lift is still the
ring rolling all three misses off, no sooner than **~2026-08-29 22:40Z**.

Two clean beats in a row (`23:35:51Z`, `00:36:47Z`) is the best run since the baseline. **Post-v3921
is 3 clean of 6.** Six beats is still not a rate, and this page does not report one.

*One transcription note, because the freeze score is a live REVERT trigger and its output must not
drift silently: CAL-P118 recorded the `22:20:23Z` beat as `,` (`cancelled`) and this read renders
that position `.`. Both count as a miss and no number above changes, but the two reads disagree on
the glyph and the disagreement is recorded rather than reconciled by choosing one.*

> 🔴 **The fourth beat republished the same population again, and the bank is now fully drifted.**
> `00:36:47Z` carries `staged.staged_at = 20:35:54Z`, `units_banked 128`, **`units_drifted` 128 —
> all 128 of them, up from 109** — `frozen_over_drift: true`, `rolling_restage: true`,
> `units_this_beat 6`. The headline is **1.89 pp** on all four beats because all four publish the
> **same `20:35:54Z` generation**. CAL-P118's structural finding did not merely hold; it completed:
> **there is now no unit in the published curve that has not drifted from the database it claims to
> describe.** `availability` still reads `"stale"`, so **criterion 5 is still RED.** No datapoint is
> banked for this beat either.

---

## 6. The inventory — every queued cell, ordered by excess

**20 cells**, on the `2026-08-28T20:37:41Z` curve at the **ratified per-cohort bars** (§1b). Status
uses the directive's rule: **not deployed and re-measured = ZERO.** Re-render with
`python3 backend/scripts/calibration_scorecard.py --live --markdown`.

> **What the ratification changed here, and what it did not.** The board grew by exactly one row —
> `odds_api_bookmaker/icehockey_nhl`, which was over the flat bar but unestablished at 1.65σ and is
> **2.6σ over class A's 2.5**. Every other row is the same cell it was; the class-A rows' *excess*
> and *rank* moved because their excess is now measured from 2.5, which is why five of the six A
> cells rose in the order. **No cell got worse and none was newly discovered** — the board is
> counting the same errors against a bar that finally distinguishes a devigged twelve-book
> consensus from a thin single-venue book. The `bar` column is printed on every row for that
> reason: at two different bars, a bare "excess" is not checkable.
>
> *Vintage: the whole table is one reading. Previous editions of this section carried a `13:35Z`
> body under a `20:37Z` header with the drift described in prose; it is re-rendered rather than
> annotated. Nothing has shipped into the producer since 2026-08-13, so every movement between
> readings on this page is population drift.*

| # | published cell | cls | ECE | n | gap | bar | excess | σ | excess-outcomes | mechanism known? | status |
|--:|---|:-:|--:|--:|--:|--:|--:|--:|--:|---|---|
| 1 | `polymarket/baseball` | B | 4.80 | 43,768 | +3.03 | 3.0 | +1.80 | 7.5 | 78,782 | ✅ **named, designed AND RULED (CAL-P117 §6c, Alex 2026-08-28 "EXCLUDE NOW + FIX WRITER")** — 54.4% is `Player Props` containers whose published price is a manufactured coin flip. K′ → **2.71 pp PASS**, 17,827 rows. Exclusion is **TEMPORARY BY DESIGN**, §6f | **ZERO** — ruled, unbuilt (disclosure surface BUILT, §6f) |
| 2 | `kalshi/economics` | C | 5.29 | 28,613 | −0.47 | 3.0 | +2.29 | 7.8 | 65,524 | ✅ **named, designed AND RULED (CAL-P114 §6b, Alex 2026-08-28 option b)** — 99.7% cumulative index ladders; rules E+E2+E3 → 2.61 pp PASS, **approved with disclosure** | **ZERO** — ruled, unbuilt (disclosure surface BUILT, §6d) |
| 3 | `polymarket/esports` | B | 7.59 | 14,053 | +6.02 | 3.0 | +4.59 | 10.9 | 64,503 | ✅ **named and designed (CAL-P112, §6a; re-checked on the exact rail, CAL-P114)** — the 1-winner tail `esports_multi_bundle_filter` cannot reach | **ZERO** — designed, unbuilt |
| 4 | `polymarket/soccer` | B | 3.42 | 106,803 | +2.16 | 3.0 | +0.42 | 2.8 | 44,857 | ❌ **none — the named mechanism was measured on the published cell and REFUSED (CAL-P118, §6e)**; O/U ladder coherence reaches 7.4% of the cell and moves it **+0.03 pp, worse on both holdout halves** | **ZERO** — and no longer designed |
| 5 | `odds_api_bookmaker/basketball_nba` | A | 5.18 | 10,186 | +1.03 | **2.5** | +2.68 | 5.4 | 27,298 | ❌ none | **not started** |
| 6 | `kalshi/crypto` | C | 7.60 | 4,565 | +1.84 | 3.0 | +4.60 | 6.2 | 20,999 | ❌ none | **not started** |
| 7 | `odds_api_bookmaker/baseball_mlb_preseason` | A | 8.24 | 3,253 | −7.67 | **2.5** | +5.74 | 6.5 | 18,672 | ❌ none | **not started** |
| 8 | `kalshi/entertainment` | C | 5.21 | 8,355 | +1.07 | 3.0 | +2.21 | 4.0 | 18,465 | ⚠️ partial (exit-exam item 3: settlement-timing rival UNKNOWN) | **not started** |
| 9 | `kalshi/golf` | B | 3.88 | 20,500 | +3.72 | 3.0 | +0.88 | 2.5 | 18,040 | ⚠️ `golf_placeholder_filter` live since 07-09 | **shipped, insufficient** |
| 10 | `polymarket/cricket` | B | 8.11 | 3,252 | −4.61 | 3.0 | +5.11 | 5.8 | 16,618 | ✅ diagnosed 2026-08-09 (exit-exam item 3) | **diagnosed, no rule built** |
| 11 | `polymarket/basketball` | B | 4.24 | 13,135 | +2.96 | 3.0 | +1.24 | 2.8 | 16,287 | ❌ none | **not started** |
| 12 | `polymarket/golf` | B | 5.45 | 6,463 | +3.92 | 3.0 | +2.45 | 3.9 | 15,834 | ⚠️ as #9 | **shipped, insufficient** |
| 13 | `odds_api_bookmaker/icehockey_nhl` | A | 3.89 | 8,658 | +3.04 | **2.5** | +1.39 | 2.6 | 12,035 | ❌ none | **NEW — entered on the ratified class-A bar** |
| 14 | `odds_api_bookmaker/basketball_wncaab` | A | 6.05 | 3,382 | −0.35 | **2.5** | +3.55 | 4.1 | 12,006 | ❌ none | **not started** |
| 15 | `polymarket/economics` | C | 3.90 | 12,882 | +0.14 | 3.0 | +0.90 | 2.0 | 11,594 | ⚠️ CAL-P114 measured it as the cell RULE T breaks if the bundle allowlist is keyed on category alone (3.91 → 17.75) | **not started** |
| 16 | `polymarket/hockey` | B | 7.36 | 2,281 | +0.66 | 3.0 | +4.36 | 4.2 | 9,945 | ❌ none | **not started** |
| 17 | `kalshi/tech` | C | 10.96 | 1,203 | −9.35 | 3.0 | +7.96 | 5.5 | 9,576 | ✅ **named and designed (CAL-P112, §6a)** — 79% cumulative-threshold ladder rows | **ZERO** — designed, unbuilt |
| 18 | `odds_api_bookmaker/basketball_wnba` | A | 4.81 | 3,135 | −0.07 | **2.5** | +2.31 | 2.6 | 7,242 | ❌ none | **not started** |
| 19 | `polymarket/tech` | C | 4.91 | 2,779 | −0.85 | 3.0 | +1.91 | 2.0 | 5,308 | ✅ measured on the exact rail (CAL-P114) — RULE T moves it 5.04 → 4.80, **refused**: 707 rows, below the materiality floor | **measured, rule refused** |
| 20 | `odds_api_bookmaker/basketball_euroleague` | A | 5.39 | 1,762 | −4.53 | **2.5** | +2.89 | 2.4 | 5,092 | ❌ none | **not started** |

By source: **polymarket 9 cells / 263,728** · **odds_api_bookmaker 6 / 82,345** · **kalshi 5 / 132,604**.

**Scoreboard: 0 of 20 cells crossed off. 2 are RULED and landable (ranks 1 and 2) and 2 more are
designed but unruled (ranks 3 and 17) — all four worth 0.00 pp today. 3 have a shipped rule that did
not clear the cell. 2 have a measured rule that was refused. 10 have no rule at all.** Those four
cells carry **218,385 of the board's 478,677 excess-outcomes, 45.6%**, and every one of them lands
the day the freeze lifts.

> **CAL-P118 moved rank 4 out of the designed column, and that is the second time a ✅ on this table
> has not survived contact with its own cell.** Rank 1's two mechanisms were worth −0.53 pp
> (CAL-P117); rank 4's is worth **+0.03 pp and is refused** (§6e). Both were diagnosed on a
> subcohort. **The `mechanism known?` column is now only trustworthy where the row says which rail
> scored it**, and the two remaining unscored ✅ rows are ranks 3 and 17 — designed on
> `calibration_cell_replica` and re-checked on the exact rail by CAL-P114, which is a weaker
> guarantee than rank 1's and rank 2's direct folds. Rank 3 is a Polymarket cell and is the largest
> exposure left on this board.

> **CAL-P119 changed what the `crossed off?` column will have to mean.** Rank 1 is ruled and will
> cross off at 2.71 pp — but **its exclusion is temporary by design** (§6f), so the rows it removes
> are expected back once lane1 queue 022 repairs the writer. **A cell crossed off behind a temporary
> exclusion is not a cell that is done.** When the rows return this cell must be re-scored, and this
> table needs to survive that without quietly keeping a ✅ it no longer earns. **Rank 1's row is
> therefore the first on this board that carries a scheduled re-open**, and nobody may read the
> board's eventual "1 of 20 crossed off" as 1 of 20 permanently solved.

### 12 material cells are over bar but NOT established — do not work these

At the ratified bars, with each cell's own bar in brackets:

`odds_api_bookmaker/basketball_ncaab` 2.55 [2.5] (0.2σ, n=26,365) · `kalshi/weather` 3.17 [3.0]
(0.4σ) · `kalshi/football` 3.97 [3.0] (1.9σ) · `odds_api_bookmaker/baseball_ncaa` 3.32 [2.5]
(1.5σ) · `polymarket/politics` 3.74 [3.0] (1.2σ) · `kalshi/motorsports` 3.82 [3.0] (1.1σ) ·
`polymarket/entertainment` 4.44 [3.0] (1.9σ) · `odds_api/basketball_ncaab` 2.84 [2.5] (0.4σ) ·
`kalshi/mma` 3.13 [3.0] (0.1σ) · `odds_api/basketball_nba` 4.16 [2.5] (1.1σ) ·
`odds_api_spreads/baseball_mlb` 3.01 [2.5] (0.3σ) · `odds_api_totals/baseball_mlb` 3.16 [2.5] (0.4σ).

They are over the bar on the point estimate and none is distinguishable from it. They want another
few thousand outcomes, not a mechanism.

**The ratification moved exactly three cells across this list, measured on the same curve:**
`odds_api_bookmaker/icehockey_nhl` left it for the queue, and
`odds_api_bookmaker/basketball_ncaab` (2.55) and `odds_api/basketball_ncaab` (2.84) entered it from
PASS — class-A cells sitting between 2.5 and 3.0 that the flat bar could not see at all. That is
the whole delta: **19 → 17 pass, 11 → 12 unestablished, 19 → 20 queued.** The first of those two is
the largest cell on this list (n=26,365) and, at 0.2σ over its bar, the one most likely to
graduate to the queue on volume alone. Watch it; do not work it.

---

## 6a. Two cells, pre-built — CAL-P112 (ranks 3 and 17 on the ratified board)

Designed, benched against a replica that reproduces the payload, and **holdout-validated on data
the rule was not designed on**. Not built, not merged, **worth 0.00 pp today** — banked so that
freeze-lift day is a merge, not a cold start. Full documents:
`artifacts/cal-p112/RULE-DESIGN-polymarket-esports.md` and
`artifacts/cal-p112/RULE-DESIGN-kalshi-tech.md`.

### They are ONE defect. §2's cancellation pair, mechanised.

`polymarket/esports` over-predicts by **+6.50** and `kalshi/tech` under-predicts by **−9.49**, and
the pooled headline reads 1.90 as though both were fine. Measured, they are the same structure:

**A non-partition bundle — independent binaries packed into one market** (a 40-rung cumulative
"Price of NVIDIA H200 compute" ladder; a whole esports match flattened into one market). The rungs
are published at their own one-sided prices, so the market's price sum is 3–33 rather than 1.

- realize **many** winners → winners exceed published mass → **under-prediction** (`kalshi/tech`,
  where the class is 79% of the cell by n and reads gap **−11.32**)
- realize **one** winner → published mass exceeds winners → **over-prediction**
  (`polymarket/esports`, where the class reads gap **+27.04**)

`esports_multi_bundle_filter` already excludes this shape — but only in **esports**, and only when
the market **happened** to resolve with ≥2 winners. Both limits are why the cells survive it.

### The rules, and their measured effect

| cell | rule | instrument, before *(payload for the same cell)* | after | published prediction |
|---|---|---|---|---|
| `kalshi/tech` | **T** — the bundle exclusion's category scope becomes an evidence-gated allowlist (`{esports, tech}`), gated on `nonexclusive_bundle_census` (tech: bundle 8.27 vs remainder 6.08) | full-predicate **replica** 1,218 / **10.75** / −8.97 *(payload 1,193 / 11.10 / −9.49)* | 260 / **3.80** / −0.30 | 11.10 → ~3.8, **9,663 → 0 excess-outcomes**; the cell then falls under the 1,000-row floor |
| `polymarket/esports` | **E** — the bundle test becomes STRUCTURAL: `≥2 winners` **OR** published price sum > 1.15, and never a proved-exclusive field. Plus **E2** (winner-only single capture: 453 rows, **453/453 winners**) and **E3** (`malformed_binaries` stops requiring the default-true `mutually_exclusive` column: 116 rows, both sides graded winners) | pre-dedup **shape census** 14,121 / **6.81** / +5.57 *(payload 13,156 / 8.08 / +6.50)* | 9,522 / **3.02** / −0.85 | 8.08 → **3.0–4.3 pp**, **66,832 → 0–11,400 excess-outcomes** |

*Two instruments, both new-file-only and both banked:
`backend/scripts/calibration_cell_replica.py` runs the published predicate through `deduped` for a
cell small enough to page out at outcome granularity; `backend/scripts/calibration_cell_shape_fold.py`
is a pre-dedup shape census that scales to a 100,000-row cell and therefore runs high on n. Each
prints its own number beside the payload's, every run.*

Holdout (split on `market_id`, monotone with creation, rule never re-fitted):

| cell | target class, OLD half | target class, NEW half | surviving core, OLD → NEW |
|---|---|---|---|
| `kalshi/tech` | 596 rows @ ECE **13.55** | 362 rows @ ECE **13.57** | gap −0.91 → +0.54 |
| `polymarket/esports` | 2,818 rows @ ECE **27.95** / gap +27.87 | 1,212 rows @ ECE **25.10** / gap +25.10 | ECE 2.97 → **3.23**, gap −0.90 → −0.80 |

### Three things a reader must not skip

1. 🔴 **T and E ship TOGETHER or a cell gets worked twice.** T is a *category* allowlist, so it also
   acts on `polymarket/tech`, where the bundle class is the *better* half: stripping only the
   ≥2-winner realizations leaves the 1-winner tail at **14.73 pp** and the census-level fold moves
   **8.04 → 12.62, i.e. worse**. Symmetrically, shipping **E alone** on `polymarket/esports` takes
   the gap from +5.57 to **−3.01** — it reverses the sign rather than halving the error, because E2
   and E3 were partially cancelling E's class.
2. ⚠️ **`polymarket/tech` is UNMEASURED, not estimated.** Neither instrument reproduces that cell —
   the shape census reads 2,080 / 8.04 / **+5.10** against the payload's 2,657 / 5.40 / **−1.78**,
   22% short on n and the **wrong sign** on the gap. Landing T owes one measurement first. Parked,
   not dropped.
3. **Neither rule "fixes" its cell in the sense a reader would assume.** `kalshi/tech` leaves the
   queue with 260 rows — below the materiality floor — and `polymarket/esports` lands at ~3.0 pp,
   *at* the bar rather than under it (0.04σ). Both are the correct outcome for rows that were never
   scoreable forecasts of one question, and both are said here rather than discovered after deploy.

---

## 6b. Rank 2 pre-built, and the instrument that had to exist first — CAL-P114

Full document: **`artifacts/cal-p114/RULE-DESIGN-kalshi-economics.md`**. Designed, benched,
holdout-validated, **not built, worth 0.00 pp today.**

### The instrument: `calibration_cell_exact.py` — the producer's own chain, not a re-implementation

CAL-P112 shipped two rails and this queue could not use either. The shape census reads
`kalshi/economics` at **69,653 / 4.65 / +4.27** against the payload's **28,613 / 5.29 / −0.47** —
2.4x the rows and the **wrong sign**; the replica caps at ~6,000 candidate rows and this cell has
69,653. So the third rail does not re-implement the predicate at all: it **imports
`_calibration_population_ctes()` from `precompute_calibration` and appends a `GROUP BY`**, scoped
to one cell through the chain's own documented `market_info_extra` hook and chunked on `fm.id`.
Reading the frozen file is not committing to it; `git diff origin/master -- backend/app/` is
empty on this branch.

It reproduces every cell it has been pointed at, and prints its number beside the payload's on
every run:

| cell | exact rail | payload | Δn |
|---|---|---|--:|
| `kalshi/economics` | 28,738 / **5.29** / **−0.47** | 28,613 / 5.29 / −0.47 | +0.55% |
| `polymarket/economics` | 12,952 / **3.91** / −0.04 | 12,882 / 3.90 / +0.14 | +0.54% |
| `kalshi/tech` | 1,208 / **11.01** / −9.40 | 1,203 / 10.96 / −9.35 | +0.42% |
| `polymarket/tech` | 2,745 / **5.04** / −1.09 | 2,779 / 4.91 / −0.85 | −1.22% |

`--edge-check` re-runs the whole sweep at half the chunk width: **identical n, ECE and gap**, so
the chunking is not doing the work.

> 🔴 **The census did not merely fail to reproduce — it produced a confident false mechanism.**
> Folded by price-capture age, the census says error rises monotonically with staleness (2.86 at
> <15 min → 10.52 at >7 d), which is a clean, shippable story. The exact rail **reverses it**:
> the freshest bucket is the **worst** (8.81) and the stalest the **best** (3.81). Same
> dimension, same day, opposite conclusion. **A rail that has not been shown to reproduce a cell
> will still rank that cell's sub-classes, and the ranking will look like a mechanism.**

### The cell: `kalshi/economics` is mis-populated, not miscalibrated

99.7% of it is cumulative intraday index and commodity ladders — `KXNASDAQ100U`, `KXINXU`,
`KXDJI` — published as N independent rungs. `KXDJI-26JUL2814`: **76 outcomes, 76 winners,
published price sum 72.48**; the median KXDJI market is 35 rungs / 24.5 winners / **sum 21.66**.
86.3% is `bundle_multiwin` and the 13.4% `field_1win` remainder is *the same ladders on a day the
index landed on one rung* — sorted by published price sum it runs **2.61 → 4.09 → 15.67 →
30.75**, and only the `sum ≤ 1.15` slice is a forecast of one question.

| policy | n | ECE | gap | excess-outcomes | |
|---|--:|--:|--:|--:|---|
| A_today (control) | 28,738 | 5.29 | −0.47 | 65,810 | |
| B — RULE T alone | 3,944 | **5.73** | +5.73 | 10,767 | 🔴 **worse than doing nothing** |
| C — RULE E | 1,722 | 3.00 | +0.24 | 0 | exactly at the bar |
| **D — E + E2 + E3** | **1,641** | **2.61** | +1.74 | **0** | **PASS, and still above the floor** |

Holdout on `market_id` 12,000,000, never re-fitted: OLD 9,338 @ 6.55 → **441 @ 3.31**; NEW
19,400 @ 4.69 → **1,200 @ 2.75**. Both halves improve by a large margin, and **the survivor sits
AT the bar rather than under it** — the honest claim is 2.6–3.3 pp, not "fixed forever".

**This is the first cell on the board whose rule leaves it PASSING and MATERIAL** — `kalshi/tech`
(183 rows) and `polymarket/tech` (707) both fall below the 1,000 floor and become absences.

### 🔴 The correction CAL-P114 forces on CAL-P112's banked design

`esports_multi_bundles` filters on `mrs.category` and **not on source**, and RULE T inherits that
shape. Measured, category-only scoping is wrong:

| cell | today | B — T only | C — E | D | verdict |
|---|--:|--:|--:|--:|---|
| `kalshi/economics` | 5.29 | 5.73 | 3.00 | **2.61 (1,641)** | **ADMIT** |
| `polymarket/economics` | 3.91 | 7.01 | **17.75** | 5.10 (457) | **REFUSE** |
| `kalshi/tech` | 11.01 | 4.65 | 7.24 | 4.53 (183) | admit → absence |
| `polymarket/tech` | 5.04 | 4.80 | 4.48 | 3.90 (707) | **REFUSE** |

**The allowlist must be keyed on `(source, category)`.** One extra column in a tuple is the
difference between crossing `kalshi/economics` (rank 2) off and silently deleting
`polymarket/economics` (rank 15).

Two further corrections, both from the same rail:

* **RULE T's evidence gate (bundle worse than remainder) REFUSES the cell the rule fixes.** On
  `kalshi/economics` it reads bundle **5.67** vs remainder **6.48** — bundle is *better* —
  because the remainder is not a control, it is the same ladders. And **dominance does not
  discriminate either**: `kalshi/economics` is 94.0% non-partition and `polymarket/economics` is
  91.4%, and they sit on opposite sides of the decision. **The admission gate is the BENCH**, per
  pair, recorded in a design document. A threshold that cannot separate 94.0 from 91.4 is not a
  threshold (ruling 124).
* **CAL-P112's parked `polymarket/tech` debt is DISCHARGED, and its direction was wrong.** That
  queue predicted T alone moves the cell *"8.04 → 12.62, i.e. worse"* off the census. On the
  published population it moves **5.04 → 4.80 — marginally better.** The cell is still refused,
  but for the measured reason (it falls below the floor), and the old reason should not be
  quoted again.

### `polymarket/esports` re-checked on the exact rail — CAL-P112's design is CONFIRMED

Run because that cell was designed on the same census that misled this one. It holds. Exact rail
**14,169 / 7.17 / +5.79** vs payload **14,053 / 7.59 / +6.02**. CAL-P112 predicted
*"8.08 → 3.0–4.3 pp, 66,832 → 0–11,400 excess-outcomes"*; measured on the published population,
**RULE E alone gives 3.29 pp and 3,371** — inside the band. Two additions the census could not
see: there is **no `bundle` class in published esports at all** (the live filter since 2026-07-11
already removes it, so the whole residual is the 1-winner tail RULE E targets — confirmed rather
than assumed); and **E2 makes the cell worse, 3.29 → 3.70, and should still ship**, because the
219 rows it removes had gap **−40.35** and were *cancelling* a real +0.57 over-prediction. Per §2,
an ECE that rises because two real errors stopped hiding each other is the more honest number.
Holdout on this cell is weak and says so — `polymarket/esports` is recent, so OLD holds 5.4% of it.

### Also parked, not dropped

`backfill_winners.py:7495-7506` — Part B names its subquery `settled` and orders
`captured_at ASC LIMIT 1`, taking the **first** snapshot an hour after the market opened, while
Parts A, A2 and C all order `DESC`. It is not this cell's defect (100% of `kalshi/economics` is
Part A2's population), but "the first price after open" being called a closing line is a real
question for whichever cells Part B does own. Appended to `PARKED-MEASUREMENTS.md`.

### 3a's σ note, flagged for the threshold table

Criterion 3 gates on `σ = 50/√n` with `n` = published **rows**. A ladder's rungs are near-perfectly
correlated, so this cell's 28,613 rows carry roughly **2,507 markets** of independent
information: the gate reads **7.8σ** where the market count would read about **2.3σ**. The cell is
established either way. It is recorded because criterion 3 overstates significance on exactly the
bundle-dominated cells criterion 6 was proposed for. **Flagged for Alex with the threshold table
— this page does not get to redefine its own finish line.**

> **Still open after the 2026-08-28 MC.** Alex's ratification ruled the *bars* (criterion 1). It
> said nothing about criterion 3's denominator or about criterion 6, and neither was silently
> carried by it. Both are still awaiting a ruling and neither is wired.

---

## 6c. RANK 1 pre-built — CAL-P117, and the two banked mechanisms were not it

Full document: **`artifacts/cal-p117/RULE-DESIGN-polymarket-baseball.md`**. Designed, benched on
the producer's own chain, holdout-validated, **not built, worth 0.00 pp today.**

### The premise this queue inherited was wrong, and the measurement says how

The board carried `polymarket/baseball` as *"✅ two named mechanisms, both branch-only"* — CAL-P094's
0.5000 placeholder pair and CAL-P100's published-pair incoherence. Both are real. Both were
diagnosed on the **subcohort board's** `baseball/quantity` cell (n=6,778), which is **3.1% of the
published cell**, and CAL-P100 shipped its arm on `program/calibration-99` saying so out loud:
**"NO ECE CLAIM ... this ships with its delta unmeasured."**

Measured on the published cell, together they are worth **−0.53 pp** and leave it at 4.16, failing
its 3.0 bar. They are a **historical residue**: of the 1,284 rows they remove, **1,258 are in the
OLD holdout half and 26 in the NEW.** The forward writer guard CAL-P094 named is already shipped and
the census shows it working.

### Rank 1's live mechanism: the writer replaces a real price with a coin flip

**54.4% of the published cell is `... - Player Props` containers** — 36–38 independent player
binaries packed into one market at a published price sum of 15–19. Market `56675315`
(*Miami Marlins vs. Houston Astros - Player Props*), `opening_probability` → published
`calibration_probability`: Yordan Alvarez HR O/U 1.5 **0.0355 → 0.5005**; Xavier Edwards HR O/U 1.5
**0.0110 → 0.5005**; Jose Altuve HR O/U 0.5 **0.0850 → 0.5050**. The opening column is a coherent
monotone prop ladder. The published column is a spray of near-0.50 values that carries no
relationship to it — and `adj_opening_probability` is `COALESCE(calibration_probability,
opening_probability)`, so the curve publishes the spray (gotcha #144 / ruling 103).

Cell-wide on ids 56–57M: inside these containers `corr(published, opening)` is **0.677** against
**0.897** outside, and **242 legs publish inside [0.45, 0.55] where only 39 opened there — a 6.2x
manufacture of coin flips** on a class whose realized base rate is 0.18. Folded as a row-level
ladder, the signature is unmistakable: **1,915 rows forced into [0.45, 0.55] from an open >0.25
away read ECE 44.36 with gap +44.36** (one-directional), while the control — rows that moved just as
far but landed elsewhere — reads 12.62 with a two-sided −2.92. Ordinary line movement and a
placeholder overwrite are distinguishable.

### 🔴 RULE E is REFUSED here, and the sum ladder is not monotone

| policy | n | ECE | verdict |
|---|--:|--:|---|
| control | 41,247 | 4.69 | |
| **RULE E** (keep only published sum ≤ 1.15) | 8,153 | **9.02** | 🔴 nearly doubles the error |
| extend `esports_multi_bundle_filter` to `(polymarket, baseball)` | 11,788 | **8.35** | 🔴 worse |

Sum band ≤1.15 / 1.15–2 / 2–5 / 5–15 / >15 reads **9.02 / 5.44 / 2.28 / 5.77 / 13.00**. The
best-calibrated class in the cell is one that is *not* a partition and the worst is the one that
looks most like one. **Third cell, third confirmation that the allowlist is per `(source,
category)` and never by family resemblance.**

### The design, and the four times the holdout refused what the pooled number admitted

**K′ = R1 (half-spike pair) + R2 (published-pair incoherence) + R3 (Player Props container with
published sum > 1.15, RULE E's own constant) + M1 (row forced into [0.45, 0.55] from >0.25 away).**

| policy | n | ECE | (ECE−3)/σ | OLD | NEW | |
|---|--:|--:|--:|--:|--:|---|
| control | 41,127 | 4.71 | +6.94 | 6.83 | 4.96 | |
| R1+R2 — *the two banked mechanisms* | 39,878 | 4.19 | +4.75 | 5.71 | 4.97 | fails |
| R1+R2+M1 | 37,971 | **2.16** | −3.27 | **5.13** | 2.00 | 🔴 best pooled ECE on the page; OLD fails |
| R1+R2+R3 restricted to sum > 15 | 36,448 | 2.94 | — | **4.12** | **3.48** | 🔴 passes pooled, fails BOTH halves |
| R1+R2+R3, all props | 17,523 | 2.86 | — | 2.95 | **3.10** | 🔴 NEW over the bar |
| R1+R2+R3+M1+M2 | 17,542 | 2.85 | −0.40 | **3.06** | 2.62 | 🔴 M2 pushes OLD back over |
| **K′ — R1+R2+R3+M1** | **17,827** | **2.71** | **−0.77** | **2.90** | **2.63** | ✅ **PASS on both halves** |

Every arm is load-bearing and **R2 is the clearest case**: worth −0.11 pp alone, and dropping it
from the conjunction puts the cell back over the bar at 3.10. CAL-P112's *"T and E ship together"*
on a different cell.

> **The pooled column and the holdout point at different rules, four separate times, and the
> holdout is right every time.** `R1+R2+M1` produces the best pooled ECE in the whole document
> (2.16) and leaves the OLD half at 5.13, because M1 is a *forward* signature — 1,525 of its 1,739
> in-container rows are in the NEW half. A reader shown only the pooled column would ship the one
> policy here that fixes nothing about the back catalogue.

**Rank 1 crosses off: 78,782 excess-outcomes → 0**, and the cell survives **PASSING and MATERIAL** at
17,827 rows (≈18,900 scaled to the payload, 18x the floor) — the second cell on this board to do so.
Honest edge: 2.71 against a 3.0 bar is **0.77σ under it**, a pass and not a comfortable one.

### 🔴 What it costs, and it is Alex's call

K′ removes **56.7% of the cell ≈ 2.7% of the entire published curve** (913,849 outcomes). With
`kalshi/economics`'s ~3.0% also banked, **two queued rules now propose removing ≈5.7% of the
published curve between them, and they should be ruled together** — a reader who accepts each 3% in
isolation has not been shown the 6%. Same footing as ruling 103's 9.3%. **Owed to Alex.**

### 🔴 The instrument's own finding: the exact rail is 5.7% short on this cell

Five folds of the control cell read **41,127–41,294** against the payload's 43,768 — a stable
**−5.65% to −6.03%**, 5x the ±1.22% CAL-P114 recorded on four cells. `--edge-check` at half the
chunk width moved n by **35 rows (0.08%)** and ECE by 0.01, so **chunking is not the cause and the
edge check cannot see the cause**: it is the *cell scope*. `market_info_extra` restricts
`market_info` to one `(source, category)` and Polymarket's `virtual_market` grouping is built over
`group_id`/`event_id` clusters that do not respect `llm_sport_category`. The ECEs agree with the
payload to 0.11 pp and the class shares are sound; the absolute row counts are 5.7% low, which is
stated wherever a row count decides something. **`calibration_cell_exact.py` owes a `--scope-check`
that folds the cell with and without the category conjunct, the way `--edge-check` folds it at two
widths.** Parked.

---

## 6d. The first cell rule Alex has RULED — and the disclosure ships with it

**Alex, 2026-08-28, on `kalshi/economics` (rank 2): option (b), APPROVED WITH DISCLOSURE.**

> *the correlated intraday index-ladder rungs stop entering the published curve (5.29 → 2.61pp,
> cell stays material and PASSES), AND the removed rows are disclosed on the page as a named,
> counted exclusion exactly like the other 13 filters — "nobody later reads the smaller curve as a
> fixed one."*

This is the first of the four banked designs to have its Alex-decision taken, and it changes rank
2's status from *designed* to **landable**. It still ships nothing today: the predicate lives in the
frozen file and waits for ruling 009's amended lift.

**The exclusion and its disclosure are ONE deliverable.** A release that lands the filter without
the page copy has executed half the ruling, and the half it dropped is the half that protects the
reader — so the disclosure half was built first, on the side of the fence that is not frozen:

| half | where | status |
|---|---|---|
| the predicate | `precompute_calibration.py` — promote the existing `is_nonexclusive_bundle` census flag to a **gate**, allowlisted on `(source, category)`, seeded `{(kalshi, economics)}` | **waiting on the freeze.** Never with T alone: T without E takes this cell 5.29 → 5.73, *worse than doing nothing* |
| the payload | new key **`nonexclusive_bundle_filter`** `{applies_to, rule, excluded, included?, excluded_by_cell}` — a NEW key, so the live `esports_multi_bundle_filter` contract does not change under existing consumers | spec'd, §9.1 of the rule doc |
| **the page** | `frontend/app/calibration/page.tsx`, in the exclusions list between `esports_multi_bundle_filter` and `exclusion_symmetry` | ✅ **BUILT and green on this branch** |

The page half is gated on `excluded > 0` exactly like the four filters above it, so it renders
**nothing** until the backend key exists — which is what makes it safe to ship ahead of the rule
rather than a release behind it. Three clauses, each pinned by a test because each is a clause of
the ruling: the rule text and total from the payload; the **per-cell counts** (the allowlist is
per-cell, so one total would hide which cell shrank); and the sentence that stops the smaller curve
being read as a better one — *"the error on these cells fell because rows that were never forecasts
of a single question stopped being counted, not because our prices got better."*
`calibrationNonexclusiveBundleDisclosure.test.tsx`, 6 tests, mutation-checked: softening that
closing clause reds it, and so does breaking the count binding.

> ⚠️ ~~**The ruling covers 3.0%, not 5.7%.**~~ **↻ CLOSED the same evening — the pair was ruled.**
> `polymarket/baseball`'s rule (§6c) removes a further ~2.7% on the same argument, and this box
> asked for the two to be put to Alex together rather than one 3% at a time. They were: **CAL-P119,
> "EXCLUDE NOW + FIX WRITER"**, §6f. Rank 1 did inherit `nonexclusive_bundle_filter` rather than
> needing a second key, so the prediction that *"the mechanism generalises, not the ruling"* holds —
> **with one correction that matters.** The two exclusions are **not the same kind**: rank 2's rows
> were never forecasts of a single question (permanent), rank 1's are real questions our own writer
> mis-priced (**temporary by design**). The surface gained `temporary_by_cell` for exactly that, and
> **it is empty for this cell deliberately** — nothing here promises rank 2's rows come back.

---

## 6e. RANK 4, measured and REFUSED — CAL-P118

Full document: `artifacts/cal-p118/RULE-DESIGN-polymarket-soccer.md`. Machine-readable:
`artifacts/cal-p118/ladder-rule-verdict.json`, `exact-polymarket-soccer-ladder.json`,
`exact-polymarket-soccer-none.json`.

`polymarket/soccer` is the cell §7 built this program's flagship prediction on. It has now been
folded through the producer's own CTE chain, with the shipped predicate
(`app/utils/ladder_coherence.py`) **imported rather than restated**, and the prediction is wrong in
sign.

| policy | n | ECE | (ECE−3)/σ | OLD | NEW | |
|---|--:|--:|--:|--:|--:|---|
| **control** (exact rail) | 101,401 | **2.89** | −0.73 | 4.86 | 2.01 | |
| **A — the shipped rule**: drop every rung of an incoherent ladder | 97,412 | **2.92** | −0.48 | **4.99** | **2.22** | 🔴 worse on both halves |
| A+B — also drop the ambiguous families | 97,242 | 2.95 | −0.29 | 5.00 | 2.23 | 🔴 worse still |
| A+B+C — drop every ladder row in the cell | 93,881 | **3.11** | +0.70 | 5.20 | 2.30 | 🔴 pushes the rail's cell over its bar |

**The ordering is monotone the wrong way.** There is no threshold to tune and no arm to drop: the
more of the ladder population the rule removes, the worse the cell gets — pooled, and on each
holdout half independently. §7's predicted −0.28 pp is measured at **+0.03 pp**.

### The mechanism is real. That is not the same as being removable.

| class | published outcomes | share | ECE | gap |
|---|--:|--:|--:|--:|
| `z_not_a_ladder` | 93,881 | **92.6%** | 3.11 | +1.81 |
| `a_drop_incoherent` | 3,989 | 3.9% | **9.57** | +2.47 |
| `c_ladder_coherent` | 3,361 | 3.3% | 1.73 | −0.07 |
| `b_ambiguous_kept` | 170 | 0.2% | **16.24** | −5.86 |

The condemned class is three times the cell's ECE and the coherent class is well under it, so the
predicate separates exactly what it claims to. It still cannot be deleted: **in 7 of 10 buckets the
condemned class's error has the opposite sign to the rest of the cell.** At bin 0 it is published at
6.7% and wins 22.9% (+16.15 pp) against a remainder at −0.26; at bin 9 it is −8.43 against +2.35.
Pooled per-bin they cancel. Remove one side and the other stands up.

> **This is §2's cancellation, one level down.** §2 says a cell's headline can be a cancellation
> rather than a description. §6e says a *class inside a cell* can be too — and that
> **ECE on a pooled cell cannot grade a row-dropping rule.** Doctrine 18 arrives here as a positive
> result rather than a warning. Any future rule on this board that removes rows owes this per-bin
> table, not just a before/after ECE.

### 81,291 condemned markets produce 3,989 published outcomes

The pre-pass runs the shipped predicate over the whole cell in one sweep: **107,089 markets carry an
`O/U` rung, 32,772 ladder families, 23,501 of them condemned, 81,291 markets condemned.** Those
81,291 markets contribute **3,989 rows** to the curve.

The reason is structural and it generalises: **an O/U ladder is a `group_id` cluster**, so
`virtual_market` assigns the whole ladder one virtual question and `deduped` keeps one
representative. *The producer had already collapsed the population this rule was built to delete.*
CAL-P106 measured 5,708 legs of `soccer/quantity`; the published cell contains 7,520 ladder outcomes
in total. The subcohort was never a sample of the cell — it was a different slice of a population
the curve barely admits.

**Second cell in two queues where a ✅ described a real defect in a population the published curve
does not contain.** Rank 1: −0.53 pp. Rank 4: +0.03 pp.

### The rule's own fail-safe keeps the worst-calibrated class on this board

`b_ambiguous_kept` is 170 outcomes at **ECE 16.24** — kept deliberately, because the family key
groups two ladders there, the rule's premise is disproven, and `incoherent_families` fails toward
keeping (the guard that stopped an esports key-collapse condemning 231 markets as one family). The
behaviour is right. What is worth watching is that it splits **57 OLD @ 8.38 / 113 NEW @ 20.21** —
the ambiguous population is growing, and it is a key that does not identify a single ladder.

### 🔴 The rail does not reproduce this cell, and CAL-P117's explanation is disproven

Two control folds ~90 minutes apart read **101,650 / 2.90 / +1.79** and **101,401 / 2.89 / +1.76**
against the payload's **106,803 / 3.42 / +2.16** — **−5.06% on rows and −0.53 pp on ECE**, five
times CAL-P117's worst ECE disagreement, and pointing the wrong way for comfort: *the rail says this
cell already passes.* Every level in §6e is therefore a within-rail delta, never a published number.

P117-3 blamed the cell scope. Measured on the densest id band (`57M ≤ id < 58M`, 57,062 soccer
markets): **0 of 7,484 group clusters and 0 of 2,103 event clusters change size** when the
`llm_sport_category` conjunct is applied, and **0 of 51,290 group-grouped markets** (1 of 41,481 on
the event path) are demoted below the ≥3 gate by 1,000,000-id chunking. The scope is exonerated and
so is the chunking.

The payload names the real candidate in its own `staged` block: `staged_at 20:35:54Z`,
**`units_banked 128`, `units_drifted 109`, `frozen_over_drift true`, `rolling_restage true`**. The
published curve is a mosaic of units banked three hours before the beat that published it; the exact
rail is one live read taken later still. **They cannot agree except by luck.** The owed instrument is
not a `--scope-check` — it is a **staged-generation replay**, the way `frozen_vm_roster` already lets
the producer replay one coherent generation across chunks. **CAL-P118-1**, and P117-3 is superseded.

> **The same fact explains the flat headline.** The `23:35:51Z` beat and the `20:37:41Z` beat publish
> the *same* `20:35:54Z` staged population — which is why this cell reads 106,803 / 3.42 on both and
> why the number is 1.89 pp on both. While `frozen_over_drift` holds the bank, **a new beat is not a
> new measurement**, and this page must not record one as a datapoint.

### The instrument

`--by ladder` on `calibration_cell_exact.py`, plus `ladder_coherence.py` and its 48 tests carried
onto this branch as **byte-identical copies** of `program/calibration-99` (`git diff` against that
branch is empty for both paths). The module is unwired — nothing in `backend/app` imports it — so it
changes no published row, and `precompute_calibration.py` is untouched, so ruling 009 is not engaged.

Two properties are load-bearing and both are pinned by tests. **The predicate is imported, never
restated** — `incoherent_families` and its four helpers are asserted by identity, and the script is
forbidden a rung pattern of its own; the module's own docstring says its SQL rendering is UNPROVEN
against its Python and that measurement must be driven from the Python side, so the verdict is
computed in Python and only the answer, a set of market ids, is pushed back into SQL. **The verdict
is computed before the chunking, not inside it** — a ladder family's markets are not id-contiguous,
and a family evaluated on a partial rung set is *systematically more coherent* than the whole one,
so chunk-local evaluation would silently under-condemn in one direction. 25 guards, 7 mutations,
7 reds.

---

## 6f. The second cell RULED — and the first exclusion designed to END — CAL-P119

**Alex, 2026-08-28, on `polymarket/baseball` (rank 1): EXCLUDE NOW + FIX WRITER.**

> *Option (b) EXTENDS to `polymarket/baseball`: the miswritten Player-Props rows leave the published
> curve with the same named, counted on-page disclosure as `kalshi/economics` (rank 1 crosses off,
> 4.71 → 2.71pp, cell stays material). The writer bug is being chased by lane1 (queue 022) — your
> exclusion is explicitly TEMPORARY-BY-DESIGN: when the writer is repaired the rows return and the
> exclusion empties itself; write that into the rule doc and the disclosure copy so the page never
> claims those rows are gone forever.*

Full document: **`artifacts/cal-p117/RULE-DESIGN-polymarket-baseball.md` §9**. Rank 1 moves from
*designed* to **landable**; it ships nothing today, because K′ lives in the frozen file and waits
for ruling 009's amended lift.

**§6c's open ask is closed.** It said the two rules *"should be ruled together — a reader who
accepts each 3% in isolation has not been shown the 6%."* They were. **~5.7% of the published curve
is now approved for removal across two ruled rules**, decided as a pair.

### 🔴 Two cells, one filter, two different reasons — and the difference is the reader's

| | `kalshi/economics` (rank 2) | `polymarket/baseball` (rank 1) |
|---|---|---|
| what is wrong | **the rows.** An intraday index ladder's rungs were never competing answers to one question, at a price sum of 15–72 | **the price we wrote.** A real prop question, quoted **0.0355** by the market, published at **0.5005** by our own writer |
| the market's own quote | there is no single quote to be right about | **intact** — `opening_probability` is a coherent monotone prop ladder; only `calibration_probability` is a spray |
| kind | structural | our defect |
| ends | **never** | **when lane1 queue 022 repairs the writer** |

**The honest sentence for rank 1 is not "these rows are ineligible". It is "we do not currently have
a price for these rows that is ours to publish."** ~2.7% of the curve is being set aside because
*we* got it wrong, not because the market did — and a page that does not say so has written off
~24,000 real forecasts on our own defect with no way back.

### The exclusion must empty itself, and that is a design constraint, not a hope

1. **`('polymarket','baseball')` in the allowlist is expected to be REMOVED.** It is a hold on a
   cell while a named defect elsewhere is repaired, not permanent scope.
2. **The rows return as good data** — not deleted, not regraded. When the writer publishes the
   market's quote again, K′'s M1 arm stops matching, R3 stops carrying them, and the payload count
   falls on its own.
3. **The disclosure is rendered from the payload, never hard-coded**, so the sentence disappears
   when the backend stops emitting the cell. A hard-coded "baseball is temporary" line would still
   be on the page a year after the fix — *the same lie in the other direction.*
4. 🔴 **The falsifier.** If the writer fix lands and this exclusion does **not** empty, the §6c
   diagnosis was wrong and **the exclusion is re-argued from scratch, not extended.** An exclusion
   that outlives its stated cause has no stated cause.

> **What will NOT come back, stated so the promise stays checkable.** R1 and R2 are the *historical
> residue* of the same family — **1,258 of their 1,284 rows are in the OLD holdout half**. Fixing a
> writer forward does not un-write the back catalogue, so R1 and R2 are expected to stay and only
> the M1/R3 population returns. **"The exclusion empties itself" means the temporary part empties**,
> and the per-cell count is what will say by how much. Nobody should promise it reaches zero before
> it is measured.

### The scope is shared. The predicate behind each entry is not.

Rank 1 joins rank 2's `(source, category)` allowlist and rank 2's payload key — but **not** rank
2's test. Extending `is_nonexclusive_bundle` to this cell is **refused by measurement** (8.35), and
RULE E alone is **9.02** against a 4.69 control (§6c). The allowlist is a list of cells that have
each earned an exclusion on their own evidence; it is not a family resemblance.

### The half that is not frozen is BUILT

| half | where | status |
|---|---|---|
| the predicate | `precompute_calibration.py` — **K′ = R1 + R2 + R3 + M1**, allowlist gaining `('polymarket','baseball')` | **waiting on the freeze.** Never with M2 (pushes OLD back over at 3.06), never with R3 restricted to sum > 15 (passes pooled, fails BOTH halves) |
| the payload | the **same** `nonexclusive_bundle_filter`, plus new **`temporary_by_cell`** — keyed `"<source>/<category>"`, valued with **the condition that ends the exclusion**, so the page can name it without knowing it | spec'd, rule doc §9.4 |
| **the page** | `frontend/app/calibration/page.tsx`, in the **same list item** as rank 2's | ✅ **BUILT and green on this branch** |

One filter, one bullet — so a reader who meets *"3.9% of the curve was removed"* meets *"and part of
that is coming back"* in the same breath rather than two bullets later. Gated on the map being
present **and non-empty**, so a payload carrying only `kalshi/economics` renders **no** claim that
anything returns: the ruling that approved rank 2 said no such thing.

`calibrationNonexclusiveBundleDisclosure.test.tsx` `describe` **CAL-P119**, 7 tests, **6 mutations /
6 reds**: dropping the *"gone for good"* promise reds it; dropping the *rows re-enter the curve*
promise reds it; hard-coding the cell name instead of binding to the payload reds it; removing the
non-empty gate reds it; blurring *"the price was wrong"* into a generic *"temporarily excluded"*
reds it; weakening the type reds it.

### 🔴 This hides the defect from the curve. It does not fix it.

**lane1 queue 022 owns the writer**, and its item 1 is the question this lane cannot answer: **is
that writer feeding user-facing probabilities anywhere — event pages, props sections — or only the
calibration pipeline's copy?** If it is user-facing it is a **P0 and it outranks everything here**:
this exclusion would then be cleaning our *measurement* of a defect still being shown to users.
Nothing in §6f should be read as repairing anything. It stops the curve reporting our writer's error
as the market's miscalibration, deliberately and disclosed.

Queue 022's item 3 is the return path — *"the excluded rows return as good data and CAL's exclusion
empties itself."* **That report is the trigger to remove the allowlist entry and re-score the cell.**

---

## 7. ~~The first test of the loop~~ — the prediction, and the measurement that refuted it

The directive names the soccer/quantity ladder rule as the first cell driven through
rule → cert → **MERGE → DEPLOY → re-measure**. Steps 1–2 are done. Step 3 has not started. Here is
what steps 4–5 will yield, computed in advance so the result can be checked against a prediction
rather than narrated afterward:

CAL-P106 measured, on its own truth-eligible cohort: 5,708 legs @ 8.53 pp → keeps 2,322 @ 3.76 pp,
so it removes **3,386 legs carrying 11.80 pp of average error**. Against the published cell
(3.53 pp on 102,491):

```
(102,491 × 3.53 − 3,386 × 11.80) / (102,491 − 3,386) = 3.25 pp
```

> **Predicted published delta: −0.28 pp (3.53 → 3.25). This is an UPPER BOUND** — it assumes every
> one of those legs survives all 13 published filters and reaches the curve, and it treats ECE as
> additive across bins when re-binning will absorb some of it. The realistic band is **−0.1 to
> −0.3 pp**.

**The cell needs −0.53 pp to reach the bar. The flagship rule delivers at most −0.28 pp.**
`polymarket/soccer` stays over bar after its own named mechanism ships. That is not an argument
against shipping it — a −0.28 pp move on 102,491 outcomes is the largest published improvement this
program would have made since 2026-08-01. It is an argument against expecting one rule to close one
cell, and it is why §8's estimate assumes ~1.5 rules per cell.

*This prediction is exactly what Blocker 2 (the broken twin) should have produced by measurement
instead of arithmetic. Record the measured delta here when it lands.*

### 🔴 IT LANDED, 2026-08-29, and the prediction is wrong in SIGN — CAL-P118

**Measured: +0.03 pp (2.89 → 2.92 on the exact rail), and worse on both holdout halves.** Not
−0.28, not −0.1, not zero. The rule is **REFUSED** and rank 4 is back to no mechanism. §6e carries
the fold, the per-bin cancellation table, and the four policy variants; the full document is
`artifacts/cal-p118/RULE-DESIGN-polymarket-soccer.md`.

**The prediction was made in good faith and flagged as an upper bound. Three things it could not
have known, and each is a rule for the next one:**

1. **The arithmetic assumed the excluded legs reach the curve.** 81,291 condemned markets produce
   **3,989** published outcomes, because an O/U ladder is a `group_id` cluster and `virtual_market`
   had already collapsed it to one representative. The rule's reach is **7.4% of the cell**, and the
   arithmetic implicitly assumed ~100%.
2. **The arithmetic treated ECE as additive across bins, and said so.** That is the assumption that
   broke: in **7 of 10 buckets** the condemned class's error runs opposite to the rest of the cell
   and was cancelling it. A high-ECE class can be load-bearing for a low-ECE pooled number.
3. **The cohort was not a sample of the cell.** CAL-P106's 5,708 legs of `soccer/quantity` and the
   cell's 7,520 ladder outcomes are almost the same size — the subcohort was a *different slice* of
   a population the curve barely admits, not 5% of the published one.

> **The general clause, and it now has two cases.** *A cell's inherited mechanism is a hypothesis
> until the exact rail scores it on the published population, and the score can come back with the
> wrong sign, not merely a smaller magnitude.* CAL-P117 measured rank 1's two mechanisms at −0.53 pp
> against a claim of "the mechanism"; CAL-P118 measured rank 4's at +0.03 pp against a claim of
> −0.28. **Neither error was in the diagnosis. Both were in the extrapolation from a subcohort to
> the curve.** Candidate for `docs/doctrine.md` once a third case lands or Alex rules it.

---

## 8. Finish date — plainly

**Basis.** **20 queued cells** (was 19; the ratified class-A bar added one — §1b). Historical rate
at which a rule actually changed the published population: **13 filters between 2026-06-25 and
2026-08-13 = one per 3.8 days.** Recent rate: **two publish-changing events in 26 days.** Last 14
days: **zero.** Conversion assumption: **~1.5 rules per cell**, evidenced by §7 (the soccer rule
falls short of its own cell) and by three cells that already have a shipped rule and remain over
bar.

> 🔴 **CAL-P118 gives the conversion assumption its first measured datapoint and it is worse than
> assumed.** §7's evidence for ~1.5 rules per cell was that the soccer rule *falls short of* its
> cell. Measured, it does not fall short — **it goes backwards, and the cell loses its mechanism
> entirely.** Two of the four cells whose named mechanism has now been scored against the published
> curve came back at −0.53 pp (rank 1, still failing) and **+0.03 pp (rank 4, refused)**. On that
> evidence ~1.5 rules per cell is optimistic, and the honest statement is that **the conversion rate
> from "named mechanism" to "published movement" is not yet known to be greater than zero** — the
> program has never observed one. The re-estimate is not owed today; it is owed at the first
> published movement, which is the only measurement that can settle it.

| scenario | assumption | finish |
|---|---|---|
| **Current trajectory** | last-14-day rate (0 published changes) continues | **Never.** The queue does not converge. |
| **Realistic** | June–July cadence restored this week (3.8 d/rule), 1.5 rules/cell | 20 × 1.5 × 3.8 ≈ **114 days → late December 2026** |
| **Optimistic** | cadence restored *and* 1 rule clears 1 cell | 20 × 3.8 ≈ **76 days → mid-November 2026** |

> **The ratification pushed the date out by ~6 days, and that is the correct behaviour.** A finish
> line that gets nearer when you tighten it would not be a finish line. This is also the cheapest
> possible demonstration that the bar is load-bearing rather than decorative.

> **Stated plainly: mid-December 2026, and only if the merge-to-publish conversion is restored this
> week. On the rate actually demonstrated over the last fortnight, the finish line is not reachable
> at all — the program would keep merging and the published numbers would keep not moving.**

The estimate is governed almost entirely by one variable, and it is **not diagnosis throughput** —
the queue already has more named mechanisms than it can ship. It is the deadlock in §5:
**a stalled producer (Blocker 1) cannot satisfy ruling 009's 13-clean-beat lift condition
(Blocker 3), so the file every rule must ship into stays sealed.**

Unstalling the producer and clearing the freeze is worth more to this date than every new
diagnosis combined. Until then the "current trajectory" row is the operative one, and it says
**never**.

> **CAL-P112 update — the deploy has happened; the RE-MEASUREMENT has not.** Blocker 3 is ruled
> (§5b) and Blocker 1's repair is now DEPLOYED (v3921, 2026-08-28T18:55:19Z). This page's own rule
> is that a fix is worth zero until it is re-measured, and the falsifier cannot be read for ~24 h,
> so **"current trajectory" remains the operative row today.** What changed is that the wait is now
> a clock rather than a condition nobody could reach. The first honest re-estimate is owed once the
> freeze score has 24 post-baseline beats — from ~2026-08-29T19:00Z — and it turns on one number:
> whether the 72 h publish rate has risen from 0.472.
>
> **What is no longer a variable:** diagnosis for the next two cells. CAL-P112 banked designs for
> `polymarket/esports` and `kalshi/tech` (§6a), so the queue's conversion bottleneck on
> freeze-lift day is merge and
> deploy capacity, not analysis.

---

## 9. The loop, from now on

Per the directive, per cell: **rule → cert → MERGE → DEPLOY → re-measure the published curve → the
delta goes on the scorecard. A cell is crossed off only when the published number moved.**

1. Re-run `calibration_scorecard.py --live --record` **after every calibration deploy**. It banks a
   datapoint keyed on `(the curve's own generated_at, the class bars it was scored at)`, so the
   trend cannot be faked by re-running — and a threshold change cannot be mistaken for a movement.
2. A queue that ends without a published delta reports **ZERO**, and says so in its own headline.
3. Every calibration report opens with the §0 line: the published number and its trend arrow, and
   **ends with the NEEDLE line** — `NEEDLE: calibration <at-bar>/49 cells-at-bar @ <ISO>` — printed
   by the scorecard itself, never hand-typed. Fable copies it; it is not re-derived.
4. **Page presentability is in scope from now on, not from 48/49.** Alex's sign-off on the
   calibration page is half of FIXED (§1), so a cell landing is not finished when the number moves
   — it is finished when the page still reads well with it moved.

**Immediate next actions, in order. Note that the first three are all unblocking work, not
diagnosis — that is the point.**

0. ~~**Wire the ratified per-cohort bar** (CAL-P114's item 0 for the next queue).~~ **DONE —
   CAL-P115, 2026-08-28.** The bars, the classes and `classify()` moved into
   `calibration_scorecard.py`; the threshold table imports them and cross-checks itself against the
   scorecard on every run; the NEEDLE comes off the scorecard's counts; the history key now
   includes the bars. §1, §3, §6 and §8 are re-rendered. New-files-and-scripts only — no
   `backend/app/` lines, so ruling 009 is untouched and nothing here is a deploy claim.
1. ~~**Unstall the producer** (Blocker 1).~~ ~~Merge and deploy CAL-P110.~~ **DEPLOYED —
   Heroku v3921 (`9ae282a7`), 2026-08-28T18:55:19Z, carrying `program/calibration-110` AND
   `-111`.** Blocker 1 stays 🛑 until the falsifier in §5a.2 is *read*: the 72 h per-beat publish
   rate must rise from **0.472** and the `sports` cancellation (`BAINLUCK-132`) must leave Sentry.
   Not re-measured = worth zero. **First honest read is due ~2026-08-29T19:00Z**, when the first
   24 post-baseline beats exist — the same instant the freeze window can first be scored (§5b).
2. ~~**Get an Alex ruling on the ruling-009 freeze** (Blocker 3) — filed as #2248 (`needs-user`).~~
   **ANSWERED — CAL-P111, 2026-08-28. Alex ruled option 1 by MC; #2248 is CLOSED.** Clause 2 is now
   **22 of the last 24 beats publish cleanly**, baseline = the CAL-P109/P110 deploy. Option 3 was
   declined, so the 842 frozen-file lines on `program/calibration-99` are **not** retroactively
   sanctioned. The lane is no longer blocked on a decision — it is blocked on a **countdown that
   cannot start until step 1 deploys**. Read the score with
   `python3 backend/scripts/calibration_freeze_score.py --baseline-at <deploy instant>`; numbers,
   both probabilities, and why 22/24 rather than 21/24 are in §5b.

   The measurement that makes it urgent: `_calibration_population_ctes` is defined at
   `precompute_calibration.py:1692` and all 26 `_filter` references live in that same file, so
   **there is no route around it — every exclusion rule must edit the frozen file.** Ruling 009's
   lift condition needs 13 *consecutive* clean beats, which at the measured 0.472 rate has
   probability 5.4 × 10⁻⁵ (~2 years of waiting). CAL-P110 raises that rate but does not by itself
   make 13-consecutive reachable, which is why the ruling is owed either way.
3. **Merge `program/calibration-99`** — 11 commits, three built-and-certed rules currently worth
   0.00 pp — once the amended condition is MET and the lift is recorded. (2) is answered; the
   blocker is now the countdown, not a decision.
   **3b. Land the CAL-P112 designs (§6a) in the same window** — `polymarket/esports` (rank 3,
   64,503 excess-outcomes) and `kalshi/tech` (rank 17, worst ECE) are diagnosed, benched and
   holdout-validated, and their rules edit the same frozen file. Landing them with `-99` is one
   deploy for five rules instead of two deploys for two. Read RULE T's §6 first: **T and E must
   ship together**, and T owes a `polymarket/tech` measurement before merge.
4. **Wire `ladder_coherence` into `_calibration_population_ctes`.** It is the only one of the three
   that nothing calls, so merging alone still yields 0.00 pp for `polymarket/soccer`.
5. Deploy, re-measure, and record the `polymarket/soccer` delta against the −0.28 pp prediction
   in §7. **This is the first cell to be crossed off by a published number in this program's
   history** — and per §7 it will move the cell without clearing it, which is the expected result,
   not a failure.
6. **Fix the twin** (Blocker 2) so the *next* rule's delta is predicted by measurement rather than
   by the arithmetic in §7.

---

*Generated by `backend/scripts/calibration_scorecard.py` · full JSON:
`artifacts/cal-p108/scorecard-live.json` · history:
`artifacts/calibration-scorecard/history.jsonl`*
