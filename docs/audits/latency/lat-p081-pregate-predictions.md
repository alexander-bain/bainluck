# LAT-P081 — PREDICTIONS, recorded BEFORE the time gates

**Written and committed 2026-08-22 ~06:45 PDT. Gate 1 opens 09:08 PDT; gate 2 opens ~10:07 PDT.**

The git commit timestamp is the guarantee that these predate the reads. They exist so that the
gated reads are a **test of a model** rather than a description of a number — a read that can only
be described afterwards cannot be wrong, and this program has spent five windows learning what an
unfalsifiable read costs.

Every prediction below is derived from the pre-gate reconnaissance at 06:1x–06:3x PDT against
production `a13239f1` / v3884, which is recorded in the same commit series. Where a prediction is
uncertain, it says so and says what it turns on.

---

## GATE 1 — item 2, the ruling-110 re-grade (not before 09:08 PDT)

| # | prediction | basis | confidence |
|---|---|---|---|
| 1 | `counters_clear_the_move` flips **true** | `ROUTING_CHANGE_AT_EPOCH` 2026-08-21 09:08:40 + `RUN_COUNTER_WINDOW_S` 86,400 s | certain (arithmetic) |
| 2 | falsifier top-level verdict stays **REVERT** | `precompute_calibration_main` still degrades; the CAL-P078 step is permanent, not transient | high |
| 3 | **P3 FAILED**, coverage **2/7** on the mirror and **1/7** on the live endpoint | the #2071 censoring fix is unmerged, so only the mirror admits `precompute_backfill_winners_status` | high |
| 4 | `precompute_calibration_main` ratio ≈ **6.0×** (was 6.007 pre-gate) | regime B is stable at p50 ≈ 1263 s against a pinned 214.7 s | high |
| 5 | `precompute_backfill_winners_status` = **`hold`** ≈ 1.11×, `observed_clip_rate` ≈ 0.38 | pre-gate mirror read | high |
| 6 | 🔴 **P4 FAILS** — `flat_or_fell` on **both** movers | #2110: raw 20 and 32 compared against pinned 31 and 45 | **high, and it is WRONG** — see below |
| 7 | **P5 stays PRE_HORIZON** | `compute_fair_fight_comparison` and `precompute_source_intelligence` hold 3 post-move samples each against `MIN_POST_MOVE_SAMPLES` 8, accruing ~1 per 7 h (they fire 4×/day); 8 is not reached until ~2026-08-23 | high |
| 8 | `grade_ruling_110.py` exits **1**, not 2 | `revert_obliged` keys off P5 == `REVERT`, and P5 will be `PRE_HORIZON` | high |
| 9 | the two `no_new_runs` beats stay `no_new_runs` | #2110 comment 2 — the defect is unfixed, and both are `pre_horizon` in truth anyway | high |

### The one that matters, stated as a falsifiable claim

**Prediction 6 is a prediction that the instrument will be wrong**, and it is the sharpest thing
this window can be tested on:

> The falsifier will grade **P4 FAILED**. The truth is that P4 **PASSED**: normalised to a rate
> against each mover's own `successes_window_s` and compared to the **schedule** — which needs no
> counter baseline at all — `backfill_market_shapes` is at **103 %** of its 72 scheduled fires and
> `precompute_backfill_progress` at **107 %** of its 96, up from the pinned **43 %** and **47 %**.

If P4 grades `rose` at 09:08, this analysis is wrong and #2110 should be closed as invalid.
If it grades `flat_or_fell`, the false negative is confirmed live.

---

## GATE 2 — item 3, the P4-tail like-for-like (not before ~10:07 PDT)

| # | prediction | basis | confidence |
|---|---|---|---|
| 10 | verdict **`NOT_REFUTED`**, never "improved" | the grader is built so `improved` is not an available verdict (ruling 075) | certain (by construction) |
| 11 | ring reads **n = 32, `post_fix=32, pre_fix=0, unknown=0`** | ring A at 06:22 was already 32/0/0 | high |
| 12 | ring span will again be **~1.2–1.4 h**, NOT ~18 h | ring A: `span_s` 4537.1 = 1.26 h at `ring_max` 32 | high |
| 13 | wall **max lands 45–62 s**, under the 65 s TTL, `over_ttl = 0` | ring A max 55.400 s; four historical maxima 42.6 / 53.92 / 61.282 / 66.365 | medium |
| 14 | **`MEASURED_WALL_MAX_S` does NOT move** | it may only move UP, and only on a max above the pinned 66.365 s | high |
| 15 | the four disjoint rings **A/B/C/D will disagree on their maxima by ≥ 5 s** | each is 32 samples of one ~76-minute slice, not 32 independent draws from the tail | medium — this is the real test |

### The methodological claim gate 2 is really testing

The directive gates item 3 on "≥18 h since 16:07 Friday, so the ring is fully post-fix". **The
ring's own span refutes the premise of that gate, favourably**: at 1.26 h wide it has turned over
roughly **fourteen times** since 16:07 Friday and was fully post-fix by about 17:20 that afternoon.
The extra wait bought no additional post-fix purity, because there was none left to buy.

What it did not buy — and what the tail clause actually needs — is **independence**. Thirty-two
samples spanning 76 minutes are 32 samples of one traffic slice. So this window banks four
disjoint rings (A 06:22, B 07:50, C 09:15, D at the gate) and reports whether their maxima agree.
That is not a substitute for the directed read; it is the grader's **own** stated criterion for the
read meaning more, quoted from its output:

> "What would make it mean more: **a second independent fully-post-fix ring at the same depth
> agreeing**, or a wall bound that is derived rather than sampled."

If the four maxima cluster tightly, the sampled max is more trustworthy than ruling 075 assumes.
If they scatter, that is direct evidence for why `MEASURED_WALL_MAX_S` has been raised four times,
and the correct conclusion is that a **derived** bound is the only way out — which is the finding,
not a failure of the read.
