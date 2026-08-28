# CALIBRATION SCORECARD

**Published curve: 1.90 pp** (`mce_closing_line`, CI [0.87, 1.97]) — **🟡 → FLAT-TO-WORSE over 30 days.**
1.23 pp (2026-07-24) → 1.88 pp (2026-08-20) → 1.90 pp (2026-08-27) → **1.90 pp (2026-08-28)**. Zero
improvement in the window. The headline is flat to two decimal places; the queue underneath it is
not — queued excess-outcomes went 436,754 → 477,794 → **480,342**.

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

*Proposed with rationale; **Alex ratifies by MC**. Each threshold is one line in
`backend/scripts/calibration_scorecard.py`; changing one re-renders this page.*

| # | criterion | threshold | rationale |
|---|---|---|---|
| 1 | **Per-cell bar** | published cell ECE ≤ **3.0 pp** | The bar the program has already ranked against for four weeks (`n × (ece − 3)`), so every banked mechanism stays comparable to its own history. Independently defensible: 3 pp means a market published at 60% lands 57–63%, inside what a reader can act on. |
| 2 | **Materiality floor** | cells with **n ≥ 1,000** outcomes | The payload's **own** floor — `min_category_outcomes: 1000` is what the curve already uses to decide a category is big enough to publish. Scorecard scope and page scope are then the same set. Cost: 49 of 287 cells clear it and they carry **95.6% of all published outcomes**. |
| 3 | **Significance gate** | excess over bar ≥ **2.0σ**, σ = `50/√n` pp | The program's own board found the defect this prevents: *"15 of the 21 are under 3σ, and three are under 1σ."* On today's payload this cuts the material over-bar list from 30 cells to **19**, so it is doing real work. |
| 4 | **Overall headline** | `mce_closing_line` ≤ **2.0 pp** | **A regression guard, not a goal.** Set where the curve already sits, because the honest finding is that the headline was never the problem — see §2. |
| 5 | **The curve must be live** | `availability: "ok"`, `producer.stalled: false` | A number nobody can refresh is not a published number. **Currently RED** — see §5. |

> **FIXED** = criteria 1–3 satisfied on **every material cell**, with 4 and 5 green, **on the
> published curve**, holding across two consecutive producer beats.

**Today: NOT DONE. 19 material cells are over bar and established.**

---

## 2. The headline is not the problem — dispersion is

`mce_closing_line` is **1.90 pp**, already inside criterion 4. It is also close to meaningless as a
progress measure, and this is the single most important thing on this page:

**it is a pooled average over 287 cells whose errors point in opposite directions and cancel.**

- `polymarket/esports` over-predicts by **+6.50 pp**
- `kalshi/tech` under-predicts by **−9.49 pp**
- `kalshi/football` under-predicts by **−5.16 pp**
- pooled, the page reports **1.90 pp**, as though all three were fine

A program steered by the headline can move cells in both directions forever and report a flat
number. **Publishing one headline as the definition of done is the exact move that let this
program report progress for months without a user-visible cell improving.** Criteria 1–3 are
per-cell for that reason.

---

## 3. The scorecard — today

| | |
|---|---|
| curve generated | `2026-08-28T13:35:35Z`, population `q268` |
| published outcomes | **895,226** across **288** cells |
| headline `mce_closing_line` | **1.90 pp** (CI 0.87–1.97) — criterion 4 **PASS** |
| material cells (n ≥ 1,000) | **49**, carrying 855,612 outcomes (95.6%) |
| **over bar AND established (QUEUED)** | **19** cells, **480,342 excess-outcomes** |
| over bar, not established | 11 cells |
| under bar (pass) | 19 cells |
| exempt (n < 1,000) | 239 cells |
| `availability` | **stale**, but `producer_stalled: false`, `beats_missed: 0` — see the §5 amendment: this reading is a coin flip on when you look, not a verdict |
| self-check | `by_category: 34/34` and `by_source: 7/7` cells reproduced exactly |
| **DONE** | **NO** |

`excess-outcomes` = `(ECE − 3.0) × n`. It ranks the queue, because a 22 pp cell over 118 rows and a
0.5 pp cell over 100,000 are not the same repair job.

### Time series — the whole history that exists

| date | headline | population | queued cells | queued excess-outcomes | source |
|---|---:|---|---:|---:|---|
| 2026-07-24 | **1.23 pp** | pre-`q268` | — | — | `docs/audits/calibration-robustness-2026-07.md`, live reading, headline only |
| 2026-08-20 | **1.88 pp** | `q268` | 17 | 436,754 | banked payload `artifacts/cal-p080/samples/cal-20260820T174018Z.json`, re-folded by this script |
| 2026-08-27 | **1.90 pp** | `q268` | 19 | 477,794 | live |
| 2026-08-28 `13:35Z` | **1.90 pp** | `q268` | **19** | **480,342** | live |
| **2026-08-28 `15:34Z`** | **1.90 pp** | `q268` | **19** | **480,342** | live (CAL-P110) |

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

**🛑 BLOCKER 3 — and this one is a DEADLOCK, not a bug.** `docs/rulings/009` freezes
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

> ⚠️ **One unresolved tension, flagged rather than resolved:** `program/calibration-99` nonetheless
> carries **842 changed lines** in that frozen file (CAL-P099/P100). Either the freeze is being
> worked under escalations that were not recorded here, or it is being treated as lapsed. Both
> cannot be right, and a lane should not be the one to decide which — **this needs an Alex ruling
> before the merge in §9 step 2.**

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

**`program/calibration-110` @ `a611347d`, `ready_for_integration`.** CAL-P109 was unshippable for a
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

## 6. The inventory — every queued cell, ordered by excess

19 cells. Status uses the directive's rule: **not deployed and re-measured = ZERO.**

| # | published cell | ECE | n | gap | excess | σ | excess-outcomes | mechanism known? | status |
|--:|---|--:|--:|--:|--:|--:|--:|---|---|
| 1 | `polymarket/baseball` | 4.99 | 41,587 | +3.25 | +1.99 | 8.1 | 82,758 | ✅ two named (0.5000 placeholder pair; published-pair incoherence) | **ZERO** — both branch-only |
| 2 | `polymarket/esports` | 8.08 | 13,156 | +6.50 | +5.08 | 11.7 | 66,832 | ⚠️ partial — `esports_multi_bundle_filter` **live since 07-11** and the cell is still 8.08 | **shipped, insufficient** |
| 3 | `kalshi/economics` | 5.29 | 28,582 | −0.47 | +2.29 | 7.7 | 65,453 | ❌ none | **not started** |
| 4 | `polymarket/soccer` | 3.53 | 102,491 | +2.34 | +0.53 | 3.4 | 54,320 | ✅ O/U ladder coherence (CAL-P106/107) | **ZERO** — branch-only, unwired |
| 5 | `odds_api_bookmaker/basketball_nba` | 5.18 | 10,186 | +1.03 | +2.18 | 4.4 | 22,205 | ❌ none | **not started** |
| 6 | `kalshi/crypto` | 7.85 | 4,541 | +2.12 | +4.85 | 6.5 | 22,024 | ❌ none | **not started** |
| 7 | `kalshi/entertainment` | 5.23 | 8,331 | +1.03 | +2.23 | 4.1 | 18,578 | ⚠️ partial (exit-exam item 3: settlement-timing rival UNKNOWN) | **not started** |
| 8 | `kalshi/football` | 5.26 | 7,577 | −5.16 | +2.26 | 3.9 | 17,124 | ❌ none | **not started** |
| 9 | `odds_api_bookmaker/baseball_mlb_preseason` | 8.24 | 3,253 | −7.67 | +5.24 | 6.0 | 17,046 | ❌ none | **not started** |
| 10 | `kalshi/golf` | 3.83 | 20,440 | +3.66 | +0.83 | 2.4 | 16,965 | ⚠️ `golf_placeholder_filter` live since 07-09 | **shipped, insufficient** |
| 11 | `polymarket/basketball` | 4.25 | 13,132 | +2.97 | +1.25 | 2.9 | 16,415 | ❌ none | **not started** |
| 12 | `polymarket/cricket` | 8.02 | 3,218 | −4.47 | +5.02 | 5.7 | 16,154 | ✅ diagnosed 2026-08-09 (exit-exam item 3) | **diagnosed, no rule built** |
| 13 | `polymarket/golf` | 5.53 | 6,366 | +3.98 | +2.53 | 4.0 | 16,106 | ⚠️ as #10 | **shipped, insufficient** |
| 14 | `odds_api_bookmaker/basketball_wncaab` | 6.05 | 3,382 | −0.35 | +3.05 | 3.5 | 10,315 | ❌ none | **not started** |
| 15 | `polymarket/hockey` | 7.36 | 2,281 | +0.66 | +4.36 | 4.2 | 9,945 | ❌ none | **not started** |
| 16 | `kalshi/tech` | 11.10 | 1,193 | −9.49 | +8.10 | 5.6 | 9,663 | ❌ none — **worst ECE on the board** | **not started** |
| 17 | `polymarket/tech` | 5.28 | 2,634 | −1.31 | +2.28 | 2.3 | 6,006 | ❌ none | **not started** |
| 18 | `odds_api_bookmaker/basketball_wnba` | 4.81 | 3,135 | −0.07 | +1.81 | 2.0 | 5,674 | ❌ none | **not started** |
| 19 | `odds_api_bookmaker/basketball_euroleague` | 5.39 | 1,762 | −4.53 | +2.39 | 2.0 | 4,211 | ❌ none | **not started** |

By source: **polymarket 8 cells / 268,536** · **kalshi 6 / 149,807** · **odds_api_bookmaker 5 / 59,451**.

**Scoreboard: 0 of 19 cells crossed off. 2 have a built rule (both worth 0.00 pp today). 3 have a
shipped rule that did not clear the cell. 14 have no rule at all.**

### 11 material cells are over bar but NOT established — do not work these

`polymarket/economics` 3.84 (1.9σ) · `odds_api_bookmaker/icehockey_nhl` 3.89 (1.7σ) ·
`polymarket/entertainment` 4.48 (1.9σ) · `polymarket/politics` 3.75 (1.2σ) ·
`kalshi/motorsports` 3.84 (1.2σ) · `odds_api_bookmaker/baseball_ncaa` 3.32 (0.6σ) ·
`kalshi/weather` 3.17 (0.4σ) · `odds_api/basketball_nba` 4.16 (0.8σ) · `kalshi/mma` 3.13 (0.1σ) ·
`odds_api_totals/baseball_mlb` 3.16 (0.1σ) · `odds_api_spreads/baseball_mlb` 3.01 (0.0σ).

They are over the bar on the point estimate and none is distinguishable from it. They want another
few thousand outcomes, not a mechanism.

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

**Basis.** 19 queued cells. Historical rate at which a rule actually changed the published
population: **13 filters between 2026-06-25 and 2026-08-13 = one per 3.8 days.** Recent rate: **two
publish-changing events in 26 days.** Last 14 days: **zero.** Conversion assumption: **~1.5 rules
per cell**, evidenced by §7 (the soccer rule falls short of its own cell) and by three cells that
already have a shipped rule and remain over bar.

| scenario | assumption | finish |
|---|---|---|
| **Current trajectory** | last-14-day rate (0 published changes) continues | **Never.** The queue does not converge. |
| **Realistic** | June–July cadence restored this week (3.8 d/rule), 1.5 rules/cell | 19 × 1.5 × 3.8 ≈ **108 days → mid-December 2026** |
| **Optimistic** | cadence restored *and* 1 rule clears 1 cell | 19 × 3.8 ≈ **72 days → early November 2026** |

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

---

## 9. The loop, from now on

Per the directive, per cell: **rule → cert → MERGE → DEPLOY → re-measure the published curve → the
delta goes on the scorecard. A cell is crossed off only when the published number moved.**

1. Re-run `calibration_scorecard.py --live --record` **after every calibration deploy**. It banks a
   datapoint keyed on the curve's own `generated_at`, so the trend cannot be faked by re-running.
2. A queue that ends without a published delta reports **ZERO**, and says so in its own headline.
3. Every calibration report opens with the §0 line: the published number and its trend arrow.

**Immediate next actions, in order. Note that the first three are all unblocking work, not
diagnosis — that is the point.**

1. ~~**Unstall the producer** (Blocker 1).~~ **DONE as far as a lane can take it — CAL-P110
   (`program/calibration-110` @ `a611347d`) is `ready_for_integration` and needs no ruling.**
   Merge and deploy it, then read the falsifier in §5a.2: the 72 h publish rate must rise from
   **0.472** and the `sports` cancellation must leave Sentry. Not deployed = worth zero, so this
   stays 🛑 until the rate is re-measured.
   **1b. Merge `program/calibration-111`** — the scorecard rail itself, new files only, zero
   `backend/app/` lines. Without it, §9 step 1 above cannot be run by anyone off master.
2. **Get an Alex ruling on the ruling-009 freeze** (Blocker 3): lift it, formally escalate the
   pending rules through it, or confirm the 842 lines already written into the frozen file are
   sanctioned. The queue cannot ship into a file whose status is ambiguous. **This is now the
   single blocking question for the lane** — it is the only thing standing between the three
   built-and-certed rules and a published delta, and no lane may answer it for itself.
3. **Merge `program/calibration-99`** — 11 commits, three built-and-certed rules currently worth
   0.00 pp — once (2) is answered.
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
