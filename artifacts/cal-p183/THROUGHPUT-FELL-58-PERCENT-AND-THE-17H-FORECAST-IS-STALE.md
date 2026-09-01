# CAL-P183 — the rebuild's throughput fell 58% on 08-31, and the 17-hour figure this lane put in front of Alex is measured on a regime that no longer exists

**Session:** CAL-P183, 2026-09-01 ~09:20–10:0xZ / ~02:20 am PT.
**Instrument:** `GET /api/admin/calibration-beat-gauges?full=true`, 168 beats. Artifact stamp
`2026-09-01T08:45:21Z` — **unchanged for a fourth consecutive session** (Trap 8, now chronic).
**Source:** `backend/app/tasks/precompute_calibration.py` at `2f28aa30`.
**Nothing was built, nothing was pushed, nothing was deployed.** D-G's default (a) freeze binds
this lane; there was no code to ship.

---

## 0. THE PARAGRAPH

**The staged rebuild banks 5 units per beat. Six days ago it banked 12.** The collapse is not
gradual and not noisy: in the 24 beats before the CERT-531 deploy the build attempted 12 units and
banked **12**, with **zero** cancellations; in all **26 beats since** it attempts 7 and banks
exactly **5**, cancelling exactly **2**, with zero variance. The cause of the *attempt* count is
arithmetic — the mean unit cost roughly doubled (96s → 186s), and a ~22.5-minute beat window
divided by the unit cost is how many units fit (22.5·60/96 = 14, 22.5·60/186 = 7.3). The
consequence is the number that matters: **a 128-unit generation that used to take ~11 beats now
takes ~26.** So the "~17 h median" that CAL-P181 derived from seven completed cycles — and that
this lane then put in front of Alex in **D-G** and in front of lane1 in note **072** — is a median
over a regime that ended at `08-31T05:32Z`. **For the rebuild running right now the honest number
is ~25–26 hours, and the "~26 h" that P181 corrected away was closer to right.**

**And the cost of getting that wrong was paid last night.** The rebuild killed at `07:31Z` stood at
**119 units after 23.9 hours** and needed **one more beat** to reach 124 — inside the measured
122–127 completion band. It was killed by **this lane's own CERT-657 merge**, and its replacement
was killed 50 minutes later by **this lane's own CERT-662 merge**.

---

## 1. WHAT I VERIFIED THAT WAS PREVIOUSLY ONLY ARGUED

### 1a. The fingerprint is source-only — now MEASURED, not read off a docstring

CAL-P182's handoff told lane1 that "cohort migrations cannot move the calibration fingerprint — a
property of *what is hashed* (source text), not of how many rows move"
(`runner-inbox/lane1/070-NOTICE-q493-is-calibration-safe.md`). That was an argument from the
docstring. I tested it by computing `_main_input_fingerprint()` at three revisions and matching each
against an observed beat:

| revision | computed fingerprint | observed in beat |
|---|---|---|
| `855b7569` (CERT-531, calibration-119) | `75faaed682d914dc96ecb43786f7137c` | beats 142–165, `08-31T06:37Z` → `09-01T06:31Z` |
| `8258395c` (CERT-657) | `af47b8e008735df09a2dcdb189033539` | beat 166, `09-01T07:31Z` |
| `2f28aa30` (CERT-662, current HEAD) | `e2040f90154fae876f0fb65f5abf74c3` | beat 167, `09-01T08:31Z` (live) |

Three for three. **🟢 lane1's Q493 reply stands, and it is now backed by measurement.** Q493
(`d297f948` → merge `3ab15b20`, deployed `07:43Z`) touched only `backend/app/tasks/polymarket.py`
and one test file — nothing the digest hashes — and correctly moved nothing.

### 1b. Both of 09-01's fingerprint changes were THIS LANE's own merges

`af47b8e0` ← CERT-657 merged `76b2b454` at `06:18Z`. `e2040f90` ← CERT-662 merged `2aac5843` at
`07:08Z`. Fifty minutes apart. The handoff's Item 5 §9 already says "the merge is the reset"; what
was not recorded is **what those two merges cost**, which is §2.

---

## 2. 🔴 THE REBUILD DIED ONE BEAT SHORT

The `75faaed6` generation ran from `08-31T06:37Z` to `09-01T06:31Z` — **23.9 hours, 24 beats** —
banking exactly 5 units per beat, reaching **119**.

The measured completion band (peak bank immediately before the reset-to-zero that serves 128) over
seven completed cycles is **122 · 123 · 123 · 124 · 126 · 127 · 122**. At 5 units/beat the next beat
(`07:31Z`) would have taken it to **124 — inside that band**.

**CERT-657 deployed into that hour.** The bank went to 5.

This is not a new argument for D-G; it is the *strongest available* one, and D-G does not currently
contain it. D-G today says only "tonight it was wiped twice in 62 minutes". It should say: *the
thing the freeze protects got to 93% and died with one beat to go.*

---

## 3. THE THROUGHPUT REGRESSION

All figures are medians over full beats (truncated beats with <3 units attempted excluded).

| regime | first beat | attempted/beat | **banked/beat** | cancelled/beat | mean unit | worst (completed) |
|---|---|---:|---:|---:|---:|---:|
| `b1820040`, final 24 beats | 08-30T09:43Z | 12.0 | **12.0** | 0.0 | 96.4 s | 161.2 s |
| `b1820040`, whole generation (132) | 08-25T18:32Z | 7.0 | 7.0 | 0.0 | 137.4 s | 261.2 s |
| `75faaed6` (24 beats) | **08-31T06:37Z** | 7.0 | **5.0** | **2.0** | 185.6 s | 118.1 s |
| `af47b8e0` + `e2040f90` (current) | 09-01T07:31Z | 7.0 | **5.0** | **2.0** | 136.4 s | 52.9 s |

**The regime boundary is exactly the `b1820040` → `75faaed6` fingerprint boundary**, which §1a pins
to the **CERT-531 / calibration-119 deploy** (`6043c1c0`, `08-31T05:32:57Z`).

Two things to hold apart:

- **The attempt count is explained.** The beat admits units until one will not fit the window
  (`_unit_fits_in_window`, `:4378`). Mean unit cost doubled, so half as many fit. 22.5·60/96 = 14;
  22.5·60/186 = 7.3. Observed: 12 → 7. That is arithmetic, not a bug.
- **The 2 cancellations per beat are NOT explained**, and they are perfectly stable across 26
  consecutive beats. That is a measurement-lane question (§6) — but §3a sharpens it a long way.

### 3a. 🆕 The measurement P182 parked is ALREADY BEING RECORDED — it is just not sampled

`P182-1` says the question to answer is *"are the same `chunk.key`s cancelling every beat (a
permanently-too-big partition, fixable by re-chunking) or different ones each beat (#2052's wall)?"*
and treats it as a beat that has to be instrumented.

**It does not.** `precompute_calibration.py:4694` already records
`staged:unit_cancelled:{chunk.key}` — the cancelling chunk **named**, with its cost — on every
cancellation, alongside `staged:unit_cancelled_after_ms` (`:4693`) and `staged:prior_unit_ms`
(`:4615`). None of the three appear in the artifact, for the reason `P182-2` gives: the
hand-maintained `OPERATIONAL_GAUGES` allowlist in `calibration_beat_gauge_sampler.py:167-177` does
not list them. **P182-1 and P182-2 are the same fix.** The measurement collapses from "instrument a
beat" to "add three names to a tuple" — still calibration source, so still frozen under D-G, but it
should ride the next calibration deploy rather than being planned as fieldwork.

### 3b. 🟡 HYPOTHESIS with a named discriminator — two permanently-blocked keys at the head

The loop iterates `chunks` in fixed order, skipping only what the cursor already holds
(`:4621-4623`), and a cancelled unit is **not** cursor-advanced. The source says so explicitly at
`:4700-4706`: *"a unit that cancels reproducibly is the FIRST one every later beat attempts."*

That predicts precisely what the data shows: **2 permanently-blocked keys are re-attempted at the
head of every beat, cancel at their own statement timeout (≥348 s each, §3), and then 5 good units
bank before the window closes.** `done` advances exactly 5, forever, with zero variance — which is
otherwise a very strange thing for a timeout-driven failure to do.

If true it has a consequence nobody has priced: **the generation can never bank more than 126 of
128**, and whether that still clears the 122–127 completion band decides whether the current rebuild
publishes *at all*. The observed band tolerates 122, so it probably does — but "probably" is doing
real work in that sentence.

🔬 **Discriminator, and it is free once the three gauges above are sampled:** if the same two
`chunk.key`s appear in `staged:unit_cancelled:*` on consecutive beats ⇒ blocked partition,
re-chunking is a real ship. If the keys rotate ⇒ it is #2052's wall and stays there. **Do not build
either fix on this hypothesis until the keys have been read.**

### The cancelled units are a heavier population, and they can be priced

Using P182's identity — `mean × attempted` = total unit-time, `worst × completed` caps the completed
share — on the live beat: total = 137.5 s × 7 = 962 s; completed ≤ 5 × 53.1 s = 266 s; therefore the
**2 cancelled units cost ≥ 696 s between them, ≥ 348 s each**. A completed unit costs ≤ 53 s. **A
cancelled unit is at least 6.5× a completed one, and the pair burns ≥72% of the beat's unit-time** —
which is exactly the ~72% P182 measured, now with the population named.

Note the diagnostic in the table: **`unit_ms_worst` went DOWN (161 s → 53 s) while `unit_ms_mean`
went UP (96 s → 186 s).** A max falling while the mean rises is only possible across two
populations, and it is the cleanest signature yet of P182's finding.

---

## 4. 🔴 THE CORRECTED ETA — AND IT IS PAST THE CEILING THIS LANE PUBLISHED

Measured inputs: beat cadence **median 60.0 min** (n=167), current rate **5.0 units/beat** (26
consecutive beats, zero variance), completion band **122–127**.

Current generation `e2040f90` began `09-01T08:31:38Z` at bank 5.

| target | beats needed | ETA |
|---|---:|---|
| 122 (band floor) | 25 | **09-02T08:30Z** |
| 127 (band ceiling) | 26 | **09-02T09:30Z** |

Publication is completion + ~1 beat ⇒ **a fresh curve is visible 09-02T09:30–10:30Z**, if and only
if nobody deploys calibration source.

| | says | actual |
|---|---|---|
| CAL-P181 / handoff | expected `09-02T00:30–02:00Z`, **ceiling `09-02T08:00Z`** | — |
| CAL-P183 (measured) | — | **expected `09-02T08:30–09:30Z`** |

**The handoff's ceiling is below this session's expected value.** P181's 17 h was a correct median
of seven *historical* cycles and an incorrect *forecast*, because every one of those cycles ran at
7–12 units/beat and the build has run at 5 since `08-31T05:32Z`.

---

## 5. GAUGE INTERROGATION — the question that keeps paying (P181's)

Two more gauges do not mean what their names say; one hypothesis I formed was tested and **rejected**.

- 🆕 **`staged:window_left_ms` is not "time left in the window".** It is recorded at exactly one
  site — `precompute_calibration.py:4634`, inside the `break` branch of the window-fit check. It
  appears on 117/168 beats overall and, in the last 26 beats, on **only the 2 beats that ran 6 units
  instead of 7**. Its **absence is a finding, not missing data**: absence means the beat ended
  because it ran out of *units to attempt within the fit rule*, presence means the *window* ended it.
  Reading absence as "no data" inverts it (gotcha #53's shape, again).
- 🆕 **`staged:units_drift_checkable` is the PREVIOUS beat's bank**, and
  `checkable + uncheckable = units_banked` identically on all 168 beats. So "uncheckable" means
  "banked this beat, nothing to compare against yet" — not "drift we cannot detect". The handoff's
  note that it "reads 100% every beat" is true only on a generation's **first** beat. Drift *is*
  checked on 145/168 beats and `units_drifted` is frequently large (up to 116). **Not a lying gauge
  — I checked and it holds.**
- ✅ **`staged:cursor_resume`** reads 0 on every beat inside a generation and is absent on each
  generation's first beat. Uninformative, but honest.
- ✅ **P182's Trap 13 confirmed and its remedy validated.** `staged:units_cancelled` is present on
  only **38/168** beats; the prescribed derivation `units_this_beat − units_completed_this_beat`
  agrees **exactly** with it on every beat where both exist.
- 🔴 **REJECTED HYPOTHESIS — do not re-form it.** I hypothesised a *tightening ratchet*: the
  per-unit statement timeout is set from `worst_unit_ms` (`:4651-4653`), which is updated **only on
  the success path** (`:4741`), so a unit too expensive to finish can never raise the bound that
  would let it finish. The mechanism is real in the source, but **the data disproves the
  consequence**: within the `75faaed6` generation `unit_ms_worst` oscillates freely — 124, 108, 116,
  112, 127, 132, 122, 126, 118, 115, 111, 135, **250**, 146, 84, 76, 80, 49, 137, 179, 93, 159, 87 —
  rising to 250 s and falling again. It does **not** monotonically tighten. The bound is not
  ratcheting the build down. Whatever fixes the 2-per-beat cancellation, it is not this.

---

## 6. WHAT I DID NOT DO, AND WHY

- **Did not build a fix.** The 2-cancellations-per-beat question is a design question against
  #2052's wall and needs a fold — ruling 134. Parked as `P183-1`.
- **Did not attribute the cancellation onset to CERT-531's *content*.** The fingerprint boundary is
  CERT-531 with certainty; the *cancellation* is only coincident with it. Three other things
  deployed in the same hour (`54ef5b1a` LAT-P161 Polymarket poll, `f68c3ba1`/`f438aaab` LAT-P159).
  Naming a culprit would be a guess.
- **Did not deploy.** D-G default (a) is freeze and it binds this lane.
- **Did not write an eighteenth paragraph about the unchanged published curve.** It is still
  `2026-08-31T04:37:36Z`, mce 1.86, RULE E's four keys absent. Explained; carried; not re-derived.

---

## 7. FALSIFIER FOR THE NEXT SESSION — one line, and it is cheap

Everything in §4 rests on "5 units/beat holds". **The `09:31Z` beat had not landed when I closed.**

> If the `09-01T09:31Z` beat shows `units_banked` **10** under fingerprint `e2040f90…`, the rate
> holds and §4's ETA stands.
> If it shows **>10**, the regression has lifted on its own and §4's ETA is too pessimistic — say so
> and re-derive.
> If the fingerprint has moved again, a fifth reset happened and the whole clock restarts.
