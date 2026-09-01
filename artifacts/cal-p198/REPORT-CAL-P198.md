# CAL-P198 — the beat ETA has no term for cancelled units, and no correlation with the throughput it predicts

**Session:** 2026-09-01, ~11:4x–12:2x PT · **Branch:** `program/calibration-190-the-rebuild-survives-a-deploy`
**Directive:** `968-burndown-conveyor.md` · **Issue:** #2052
**Nothing was deployed, merged, or edited under `app/` or `frontend/`.** D-G default (a) = freeze acted on.

---

## 0. One paragraph

The standing job had nothing ruled-and-unbuilt, so this session ran the two oldest unrun items in
the question bank. The **falsy-zero sweep** on the four remaining calibration modules came back
**NEGATIVE** with a passing control — that question is now closed. The **no-production-consumer
census** on the three modules P197 did not reach returned one minor dead wrapper. But the sharp
find came from question 1 aimed at its strongest unaimed target, the `floors` ring, which led into
the beat projection: **`_record_staged_rate` computes the beat's observed throughput, records it as
a gauge, and never uses it; the ETA it then computes divides the whole unit window by the cost of a
unit that *completes*, with no term anywhere for the time consumed by units that are cancelled.**
CAL-P071's own docstring, attached to the sibling projection, names this exact defect — *"observed
throughput is not an input to it… an ETA that cannot fall as the build slows is not an estimate, it
is a constant wearing one"* — and CAL-P071 fixed only the other half (the divisor). Measured over
165 captured production beats the ETA's implied rate correlates with actual throughput at
**r = −0.016**. On the live stuck beat, cancelled units consume **73.8%** of the unit stage
(707,686 of 958,892 ms, reconciling to 19 ms) and the projection models none of it.

---

## 1. State (measured this session)

| thing | value |
|---|---|
| input fingerprint | `e2040f90154fae876f0fb65f5abf74c3` — **unchanged, 33rd session**, re-verified at session end |
| published curve `generated_at` | `2026-08-31T04:37:36Z` — **unchanged, 33rd session** |
| `availability` | `stale` (P196-2: structurally unreachable otherwise) |
| ledger `updated_at` | `2026-09-01 17:31:46.517193+00` — **unmoved for a 4th session** |
| `units_banked` / planned | 50 / 128 · `units_completed_this_beat` 5 · `units_cancelled` 2 |
| `beats_to_publish` | 3 · `terminal` cancelled · `served_units` 0 · `served_at` absent |
| `origin/master` | 🔴 **MOVED** `9fc73a59` → **`60c81cab`** (UX merge, CERT-682) |
| calibration files in that move | **zero** — `git diff --name-only bcabbf2e origin/master \| grep -i calib` empty, exit 1. ALL-CLEAR |
| Alex's drain | **still not run** as of ~12:2x PT |
| board (`TOP-PRODUCT-DEFECTS.md`) | no open calibration-lane build item (item 12 DIAGNOSED-not-built, item 21 lane1's) |

⚠️ **Master has now moved on two consecutive sessions.** `967` asserted it had not and was wrong;
`968` caught it. Run the diff yourself — it is one command and it moves under you.

---

## 2. `P198-1` — the ETA has no cancelled-unit term *(the finding)*

### 2.1 The mechanism

`backend/app/tasks/calibration_main_build.py`, `_record_staged_rate`:

```python
completed_units = runner.ledger.stage_completed_count(STAGED_UNIT_STAGE)   # = 5 live
runner.ledger.record_gauge("staged:units_completed_this_beat", completed_units)   # :1571
...
window_ms = runner.ledger.remaining_ms(elapsed_ms=0)
fixed_ms  = max(0.0, runner.elapsed_ms() - runner.ledger.stages.get(STAGED_UNIT_STAGE, 0))  # :1594
usable_ms = max(0.0, window_ms - fixed_ms)                                                  # :1595
per_beat  = usable_ms / projection_mean if projection_mean > 0 else 0.0                     # :1617
```

Two things are true of those five lines together:

1. **`completed_units` — the observed throughput — is read exactly once, to be written to a gauge**
   (proof 1 §A: its only `ast.Load` is line 1571, inside the `record_gauge` call). It is not an
   input to `per_beat`.
2. **`fixed_ms` subtracts only the NON-unit overhead.** It is `elapsed − stages[read:futures_unit]`,
   and `read:futures_unit` accumulates over *attempts*, so the time burned by units that were
   cancelled sits **inside** the term that is *kept* as usable. `usable_ms` therefore asserts that
   every remaining millisecond of the unit window will be spent on units that complete.

The divisor `projection_mean` is `unit_ms_mean_completed` — the cost of a unit that *finishes*.
So the model is *window ÷ cost-of-a-success*, with no factor for the success rate.

The sibling projection `PhasePlan.unit_projection` (`calibration_phase_ledger.py:584`) has the
identical blindness with different terms: `per_beat = budget_ms // unit_ms`. Neither projection
references any cancellation quantity anywhere (proof 1 §B/§C — searched `cancel`, `cancelled`,
`units_cancelled`, `unit_cancelled`, `abandoned`, `truncated`).

### 2.2 The docstring already says this

`unit_projection`'s docstring is CAL-P071's, and it names **two** failure modes:

> *"It failed in the dangerous direction twice over. Optimistic, and **immovable**: three consecutive
> beats banked 2, 1 and 0 units while the estimate sat at 13 throughout, **because observed
> throughput is not an input to it**. An ETA that cannot fall as the build slows is not an estimate,
> it is a constant wearing one."*

CAL-P071's actual change was the **divisor** — `max_phase_ms` → `budget.unit_ms` against the phase's
own `budget_ms`. That addresses "optimistic". **"Immovable" was left standing**, in the very function
the docstring is attached to: `unit_projection` still reads only the cumulative `units_done`, never a
per-beat completion count (proof 1 §D, all four claims PASS).

This is the P197-1 shape at one remove. P197-1 was *a fix that was never wired*. This is *a
two-part diagnosis where one part was fixed, the other was written down in the same docstring, and
the docstring now reads as though both were.*

### 2.3 Measured — 165 captured production beats (reusing CAL-P118's ring, nothing re-collected)

`beats_to_publish = ceil(remaining / per_beat)`, so the asserted rate is recoverable from the
captured pair as `implied = (128 − units_banked) / beats_to_publish`. The `ceil` makes
`implied ≤ per_beat`, so **every optimism figure below is a lower bound.**

| | value |
|---|---|
| implied units/beat | mean 8.3 · med 8.0 · range **4 → 33** |
| actual units/beat | mean 7.1 · med 7.0 · range 0 → 14 |
| **Pearson r(implied, actual)** | **−0.016** |
| beats where the ETA over-claimed | **113/165 = 68%** |
| optimism ratio | med 1.07× · mean 1.43× · **max 33.0×** |

**r = −0.016 is the empirical form of the docstring's own indictment.** The ETA's spread is 8× while
the throughput it predicts sits in a narrow band; the two are uncorrelated. The median error is
small only because throughput happened to be *stable* across that window — not because the model
tracks it.

### 2.4 The error is regime-dependent, and the live beat is in the bad regime

Of 16 captured beats that recorded a cancellation, the two with **two** cancellations are the two
worst in the whole ring:

| generated_at | cancelled | actual banked | ETA implied | ratio |
|---|--:|--:|--:|--:|
| **2026-08-28T05:20:45** | **2** | **1** | **33.0** | **33.0×** |
| 2026-08-22T23:40:37 | 2 | 5 | 13.5 | 2.7× |
| *(14 single-cancellation beats)* | 1 | 4–9 | 4.0–12.8 | 0.7×–1.6× |

**The live stuck beat has the same signature: 2 cancelled, 5 completed.** Its arithmetic reconciles
exactly (proof 2 §D):

```
2 cancelled units          707,686 ms   (353,842 + 353,844, each at its fence)
5 completed x 50,245 ms    251,225 ms
                         ------------
reconstructed              958,911 ms
read:futures_unit          958,892 ms   delta 19 ms
```

**73.8% of the unit stage banked nothing, and the projection models 0% of it.** The honest cost per
*banked* unit this beat is **191,778 ms — 3.8× the 50,245 ms the model uses.**

This matters in the direction that hurts: the ETA is least informative exactly when a build is in
trouble, which is exactly when an operator reads it. `beats_to_publish: 3` has been on the board
while the curve has not moved for 33 sessions.

### 2.5 Scope limits, stated honestly

- **This is OPERATOR-visible, not user-visible.** No user reads `beats_to_publish`. It does not
  belong on `TOP-PRODUCT-DEFECTS.md`.
- **It is not the cause of the stall.** The rebuild is stuck because `futures` cannot fit
  (the fence + P195's idleness); a correct ETA would have *reported* the stall sooner, not prevented
  it. The claim is a blind estimator, not a broken build.
- **The 1.07× median is a healthy-regime number.** I am not claiming the ETA is badly wrong on
  average — I am claiming it is *uncorrelated*, and that its error concentrates in the cancellation
  regime.
- **`staged:unit_ms_mean_completed` is absent from all 168 ring beats** (CAL-P067 postdates that
  capture), so §2.3's ring analysis uses the implied-rate reconstruction rather than the recorded
  divisor. §2.4's live reconciliation is the direct measurement.
- **Adjacent but distinct from the existing parks.** `P194-1` is the falsy-zero fallback in this
  same function (`:1613/1615`) and is about *which mean* is used; this is about a term that is in
  *neither* mean. `P196-1` is drift intervals. `P197-1` is the failure log. None of them touches the
  numerator.

### 2.6 Cost — fingerprint-free

Both fix sites (`calibration_main_build.py`, `calibration_phase_ledger.py`) are in **different
modules entirely** from `precompute_calibration.py`, so they cannot be inside any of the four
hashed functions (`compute_calibration_payload` 4917–6285, `_calibration_population_ctes`
2729–3780, `_virtual_market_ctes` 2607–2692, `_main_futures_sql` 4099–4347). **Zero rebuild cost,
no staged-cursor reset** (P194's correction). This unblocks nothing — ruling 009 still freezes the
module and D-G still freezes the deploy. Only the price is known.

**Decision owed to a fold, not a build lane (ruling 134).** Not fixed here.

---

## 3. `P198-2` — `load_phase_history` is tested and never wired *(minor)*

`calibration_main_build.py:1141`. One definition, **one** reference in the entire repo
(`backend/tests/test_calibration_phase_ledger.py:340`), **zero** in production — not even in its own
module. It is a two-value view over `load_phase_carryover`, and its docstring says it is *"kept for
callers that merge the rolling windows and have no use for the unit description."* **There are no
such callers.** Production uses `load_phase_carryover` directly (`:1694`) and via
`load_phase_measurements` (`:1130`).

Dead convenience wrapper with a docstring asserting a constituency that does not exist. Consequence
is nil — nothing is broken and nothing renders wrong. Recorded, not inflated.

---

## 4. Questions run to exhaustion this session

### 4.1 The falsy-zero sweep — **NEGATIVE, closed**

The oldest unrun item in the bank. Swept the four remaining calibration task modules
(`calibration_beat_gauge_sampler`, `calibration_graded_share`, `calibration_published_twin_worker`,
`calibration_sentinel`) with an AST detector for numeric values taken in a truth context.

**Control arm first**, and it earned its keep: the detector initially **missed P193-1**
(`stage_ok_maxima.get(name, 0) or None`) because it did not treat `.get(k, <numeric default>)` as
numeric. Fixed — *the numeric default is the proof the caller expects a number*. Both known hits
(P193-1 and P194-1's two sites) now reproduce, so the low yield is real rather than vacuous.

**9 candidate sites across the four modules, all cleared:**

| site | why it is not a falsy zero |
|---|---|
| `beat_gauge_sampler:385/386/387/390/392`, `graded_share:174`, `sentinel:1088` | list emptiness — for a list, "zero" and "absent" genuinely coincide |
| `graded_share:237` | `pages_failed` — omitting the clause on 0 is the intended render |
| `sentinel:851` | `not res or not res.total` — `res.total` is a `COUNT(*)` guarding a division; `None` on an empty cohort is correct |

**The falsy-zero ledger stays at five instances. This question is spent** — do not re-run it on
these four modules.

### 4.2 The no-production-consumer census — one minor hit

P197's §E widened on two axes, both deliberate: it scanned **class methods only** (these modules
expose mostly module-level functions, so a method-only scan would have returned a vacuous zero) and
**`backend/app` only**, which collapses two different states. Split into **ORPHAN** (no reference in
app *or* tests) and **TEST-ONLY** (tested, never referenced by production) — the latter being
exactly the P197-1 shape.

Control: `failed_phase` still surfaces, now correctly in **TEST-ONLY** rather than ORPHAN (P197
called it an orphan because it scanned app only; its guard does reference it). The taxonomy working,
not a regression.

Result across the three targets — 88 public members scanned, **0 orphans, 1 test-only**
(`load_phase_history`, §3). **This question is spent on these three modules.**

---

## 5. Artifacts

`artifacts/cal-p198/` — all four run from any cwd (verified from `/tmp`), all exit 0:

| file | what |
|---|---|
| `proof_1_the_eta_has_no_cancelled_unit_term.py` | static, 13 claims, exit 0 |
| `proof_2_the_eta_does_not_track_throughput.py` | empirical over the 165-beat ring + live reconciliation, exit 0 |
| `sweep_falsy_zero_four_modules.py` + `sweep-falsy-zero-output.txt` | the negative sweep, control PASS |
| `census_no_production_consumer.py` + `census-output.txt` | the widened orphan/test-only census, control PASS |

No new probe worktrees. No DB writes. Two read-only `db-query` calls total.
