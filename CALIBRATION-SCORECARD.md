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

**The falsifier is now live and must be read before anything is claimed** (§5a.2): the 72 h per-beat
publish rate has to rise from **0.472**, and the `sports` cancellation signature
(`BAINLUCK-132`, `QueryCanceledError` on the `FROM events WHERE status IN ('completed','closed')`
scan) has to leave Sentry. `BAINLUCK-Y8`'s title will keep saying `phase group ['futures']` because
the log-wording fix went with the frozen file — **judge it by count, not by wording.**

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
| 1 | `polymarket/baseball` | B | 4.80 | 43,768 | +3.03 | 3.0 | +1.80 | 7.5 | 78,782 | ✅ two named (0.5000 placeholder pair; published-pair incoherence) | **ZERO** — both branch-only |
| 2 | `kalshi/economics` | C | 5.29 | 28,613 | −0.47 | 3.0 | +2.29 | 7.8 | 65,524 | ✅ **named and designed (CAL-P114, §6b)** — 99.7% cumulative index ladders; rules E+E2+E3 → 2.61 pp PASS | **ZERO** — designed, unbuilt |
| 3 | `polymarket/esports` | B | 7.59 | 14,053 | +6.02 | 3.0 | +4.59 | 10.9 | 64,503 | ✅ **named and designed (CAL-P112, §6a; re-checked on the exact rail, CAL-P114)** — the 1-winner tail `esports_multi_bundle_filter` cannot reach | **ZERO** — designed, unbuilt |
| 4 | `polymarket/soccer` | B | 3.42 | 106,803 | +2.16 | 3.0 | +0.42 | 2.8 | 44,857 | ✅ O/U ladder coherence (CAL-P106/107) | **ZERO** — branch-only, unwired |
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

**Scoreboard: 0 of 20 cells crossed off. 2 have a built rule and 3 more a designed one (all worth
0.00 pp today). 3 have a shipped rule that did not clear the cell. 1 has a measured rule that was
refused. 11 have no rule at all.**

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

## 7. The first test of the loop: `polymarket/soccer` — and it does not clear its cell

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

---

## 8. Finish date — plainly

**Basis.** **20 queued cells** (was 19; the ratified class-A bar added one — §1b). Historical rate
at which a rule actually changed the published population: **13 filters between 2026-06-25 and
2026-08-13 = one per 3.8 days.** Recent rate: **two publish-changing events in 26 days.** Last 14
days: **zero.** Conversion assumption: **~1.5 rules per cell**, evidenced by §7 (the soccer rule
falls short of its own cell) and by three cells that already have a shipped rule and remain over
bar.

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
