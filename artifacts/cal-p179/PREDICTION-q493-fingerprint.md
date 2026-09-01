# CAL-P179 — registered prediction: does Q493 flip the calibration input fingerprint?

**Registered 2026-09-01T08:02Z / 01:02 am PT, BEFORE the deciding observation.**
Origin: directive `944` Item 6, carried from lane1's notice `943`. Item 6 said *"Register the
observation; do not build anything on it."* This file is that registration and nothing else.

## Why this is worth registering

`944` Item 2 established that the calibration page is frozen because a fingerprint change discards
the staged artifact, `served_at` goes absent, and every beat cancels before the gate. The rebuild
needs **26.8 h** at the post-#2052 rate of **4.77 u/h**; the natural fingerprint interval is
**24.90 h**. It loses by ~1.9 h, every cycle, and has done so for 168 beats / 10 resets / peak 127.

Q493 migrates ~105k rows between the `tennis` and `table_tennis` **calibration cohorts**.
`llm_sport_category` is a cohort key. If that column feeds the calibration `input_fingerprint`, then
Q493 forces a fingerprint change ~23.8 h EARLY — a reset on top of a reset — and the page stays
frozen for another full cycle for a reason that has nothing to do with #2052's wall.

## Pre-state — all measured at 2026-09-01T07:59Z, none inherited

| fact | value | source |
|---|---|---|
| last beat before Q493 deploy | `2026-09-01T07:31:29.579149Z` | `calibration-beat-gauges?full=true` |
| `input_fingerprint` at that beat | **`af47b8e008735df09a2dcdb189033539`** | same |
| `staged:units_banked` | **5** / 128 planned | same |
| `units_this_beat` / `completed_this_beat` | 7 / 5 | same |
| outcome | `gate: not_evaluated`, `published: false` | same |
| endpoint artifact age | `artifact_generated_at 2026-09-01T07:45:00.325441Z` (14 min; trap 8 respected) | same |
| published curve | `generated_at 2026-08-31T04:37:36Z`, `mce_closing_line 1.86` | `GET /api/calibration` |
| RULE E's four keys | still **ABSENT** | same |
| Q493 sha | `3ab15b20` (merge of lane1 `d297f948`, CERT-663) | `git log origin/master` |
| **Q493 deploy** | **Heroku `bainluck` v3972 `Deploy 3ab15b20`, 2026-09-01T07:55:05Z** | `heroku releases` |

**The deploy landed 23m36s AFTER the last beat.** So the beat due at **~08:31Z** is the first one
that reads post-Q493 data. That is the deciding observation. Nothing before it can grade this.

Fingerprint history corroborating the 24.90 h interval (P178's number, re-measured not re-derived):

- `2026-08-31T06:37:31Z` → `75faaed682d9`, bank reset to 5
- `2026-09-01T07:31:29Z` → `af47b8e008…`, bank reset to 5 (from 119/128)

## The prediction

**At the first beat after `2026-09-01T07:55:05Z` (expected ~08:31Z), `input_fingerprint` will move
off `af47b8e008735df09a2dcdb189033539` and `staged:units_banked` will read ~5 rather than ~10.**

Stated as a cost: Q493 spends a full rebuild cycle. The page cannot republish before ~09-02T10Z at
the earliest, and on the standing arithmetic it will not republish then either.

## The falsifier — pre-authorised, no judgement call at grading time

**FALSIFIED if `input_fingerprint` is still `af47b8e008735df09a2dcdb189033539` at the first
post-deploy beat AND `staged:units_banked` has advanced (≈10, i.e. 5 + one beat's units).**

That outcome is the *informative* one: it proves `llm_sport_category` is **not** in the fingerprint
input, which means cohort migrations are free with respect to the publish outage, and it narrows
what the fingerprint actually keys on — a fact #2052 currently lacks.

Three guards against grading this wrong:

1. **Read `artifact_generated_at` first** (trap 8). If it has not advanced past `07:45:00Z` the
   endpoint is serving a pre-built artifact and I have observed nothing. Re-read, do not grade.
2. **A missing beat is not a falsification.** If no beat with `generated_at > 07:31:29Z` exists, the
   observation has not happened yet. Wait or hand it forward; do not score it.
3. **Do not grade on the bank alone** (CAL-P169(a)). The bank is the in-flight rebuild, not the
   serveable artifact. The fingerprint is the claim here; the bank is corroboration only.

## AMENDMENT — 2026-09-01T08:09Z, written BEFORE the deciding beat

Verified at `08:09:13Z` that the newest beat was still `07:31:29Z` (poll log, three consecutive
reads). So this amendment is genuinely pre-observation, not a retrofit.

**I read the source instead of waiting to infer, and the claim above is now decidable on code.**

`_main_input_fingerprint()` — `backend/app/tasks/precompute_calibration.py:6514-6631` — hashes
**deployed Python source text and module constants only**. It opens no session, runs no query, hashes
no timestamp and no row count:

```python
source = (inspect.getsource(compute_calibration_payload)
        + inspect.getsource(_calibration_population_ctes)
        + inspect.getsource(_virtual_market_ctes)
        + inspect.getsource(_main_futures_sql))
return input_fingerprint(CALIBRATION_POPULATION_VERSION, REPRESENTATIVE_TIE_AUTHORITY, …, source)
```

It is called at `:6982` *before* a db handle exists. The second, data-derived digest
(`generation_fingerprint`, `calibration_staged_futures.py:595-626`) projects only
`market_id, source, vm_id, is_grouped` — **`category` is not in it**.

### Consequence 1 — the Q493 claim is FALSIFIED, deterministically, by two independent routes

1. **By data:** the fingerprint has no data input at all, so a ~105k-row `UPDATE` of
   `llm_sport_category` cannot move it. Neither digest projects `category`.
2. **By code:** `git show --stat d297f948` = `backend/app/tasks/polymarket.py` + one test file.
   **Q493 does not touch `precompute_calibration.py`.** It cannot move a source hash it does not
   modify.

Item 6's prediction — *"if the fingerprint moves off `af47b8e008` shortly after Q493 deploys"* —
rests on a premise that is false. Cohort migrations are **free** with respect to the publish outage.
That is the informative branch of my own falsifier, reached before the observation rather than after.

### Consequence 2 — the confound, and the real mover: it is OUR OWN SHIP

The ~08:31Z beat sits downstream of **two** deploys, not one:

| release | sha | at | touches hashed source? |
|---|---|---|---|
| v3971 | `2aac5843` (RULE E, ours) | 07:39:54Z | **YES — 591 insertions to `precompute_calibration.py`** |
| v3972 | `3ab15b20` (Q493, lane1) | 07:55:05Z | no |

`git diff 3807f8a1 2aac5843 -- backend/app/tasks/precompute_calibration.py` adds six constants that
`_main_input_fingerprint` hashes **by name**: `PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS`,
`PLAYER_PROPS_HALF_SPIKE_EXACT_VALUE`, `PLAYER_PROPS_NAME_PATTERN`,
`PLAYER_PROPS_MIDPOINT_BAND_LO/_HI`, `PLAYER_PROPS_FORCED_DRIFT_MIN` — plus the bodies of hashed
functions.

**So the fingerprint WILL move at the first beat after 07:39:54Z, and the cause is RULE E, not
Q493.** Had I graded on the naked observation I would have scored my own prediction CONFIRMED for
entirely the wrong reason — the exact failure mode `944` Item 2 records ("the mechanism was right;
the unstated assumption was wrong"). **Attribution here is not optional; the two deploys are 15
minutes apart and only one is capable of moving the digest.**

### Amended prediction — registered now, graded on the same beat

**A.** `input_fingerprint` ≠ `af47b8e008735df09a2dcdb189033539` at the first beat after `07:39:54Z`.
**Attributed to v3971 (RULE E), not Q493.** Falsifier: the digest is unchanged ⇒ my reading of
`_main_input_fingerprint`'s coverage is wrong and must be reported as such.
**B.** `staged:units_banked` resets to ~5 rather than advancing to ~10.
**C.** Q493 contributes **nothing** to either. Unfalsifiable in isolation on this beat (it is
confounded by v3971); it is carried by the source reading above, which does not need the beat.

### VERIFICATION — the model is reproduced from source, not inferred (08:11Z, still pre-beat)

`_main_input_fingerprint()` is a pure function of source, so I executed it at both shas rather than
reasoning about it. Confirmed at `08:10:43Z` that the newest beat was still `07:31:29Z`.

```
pre-RULE-E   3807f8a1  ->  af47b8e008735df09a2dcdb189033539   <-- EXACTLY the live fingerprint
deployed     3ab15b20  ->  e2040f90154fae876f0fb65f5abf74c3
```

The pre-RULE-E source **reproduces the live digest bit-for-bit**. That is the whole model closed:
the fingerprint is the deployed calibration source, and nothing else.

`precompute_calibration.py` is byte-identical across our branch and both deploys —
sha256 `f8ab05f1a2ebb984ea4d1f0ddc3c0fd2272fe4fa042dcbcc26e8c7401ae44157` at `2f28aa30`, `2aac5843`
**and** `3ab15b20`; `ed5895a8…` at `3807f8a1`. Q493 did not perturb the file, which is the code-side
proof that it cannot perturb the digest.

**Amended prediction A, now exact:** the first beat after `07:39:54Z` will report
`input_fingerprint = e2040f90154fae876f0fb65f5abf74c3`.

Not "will change" — that value. A different non-`af47b8e0` value falsifies my account of what is
hashed just as surely as no change would, and I will report it as such.

### Consequence 3 — 🔴 the finding that actually matters for #2052

`944` framed the blocker as a **24.90 h fingerprint interval** racing a **26.8 h rebuild** — a fixed
cycle the rebuild narrowly loses to. **That framing is wrong, and it is optimistic.** There is no
cycle. The fingerprint moves *whenever a deploy changes calibration source*, so the "interval" is
just this repo's calibration-touching deploy cadence, which is not a constant and is not bounded
below by anything. The rebuild needs **26.8 uninterrupted hours**; master took **four** deploys in
the last five hours alone (v3969–v3972).

**The publish outage is therefore structural, not marginal.** It is not "losing by ~1.9 h" — it is
that the repo cannot stay off calibration source for 26.8 h while this lane and lane1 are shipping
into it. Shrinking the gap by 1.9 h fixes nothing; the fix has to be either the #2052 wall (rebuild
faster) or carry-across-fingerprint (stop discarding banked units on a source change).

And the sharpest form of it: **RULE E — the ship six directives were waiting on — is itself the
event that re-arms the trap.** Merging it reset the bank to 0 and bought another ≥26.8 h of frozen
page. That is not an argument against having merged it; it is the reason the merge could never have
been the unblock, which `944` Item 5 #9 already retired on other evidence and this now explains
mechanically.

## GRADED — 2026-09-01T08:48Z, on the beat at `08:31:38.330866Z`

Observed with `artifact_generated_at 2026-09-01T08:45:21Z` (trap-8 guard satisfied: the artifact
advanced past `07:45:00Z`, so this is a real observation, not a stale re-read).

| claim | predicted | observed | verdict |
|---|---|---|---|
| **A** `input_fingerprint` at first beat after 07:39:54Z | `e2040f90154fae876f0fb65f5abf74c3` | `e2040f90154fae876f0fb65f5abf74c3` | ✅ **CONFIRMED, exact** |
| **B** bank resets rather than advancing to ~10 | ~5 | **5** / 128 planned | ✅ CONFIRMED |
| **C** Q493 contributes nothing | — | carried by source proof, not by this beat | ✅ upheld |
| **Item 6's original claim** (Q493 moves the fp) | — | fp moved, but **not attributable to Q493** | 🔴 **FALSIFIED** |

Outcome unchanged: `gate: not_evaluated`, `published: false`, `served_units: 0`. New gauge sighted:
`staged:beats_to_publish = 5`. Cost per unit `unit_ms_mean 137476` (137.5 s) — flat, consistent with
`944`'s 116–162 s and with #2052 being the limiter.

**Item 6's prediction is FALSIFIED and I am recording it as falsified even though the fingerprint
did move.** Moving is not the claim; moving *because of Q493* was. The digest that appeared is the
one computed from **our own RULE E source at 08:11Z, twenty minutes before the beat printed it** —
so the cause is v3971, and Q493's contribution is nil. Grading this CONFIRMED on the naked
observation would have been the single easiest error available today.

### 🔴 The decisive number: the last two fingerprint changes were **62 minutes** apart

- `2026-09-01T07:31:29Z` → `af47b8e008…` (from v3970-era source)
- `2026-09-01T08:31:38Z` → `e2040f90154f…` (from v3971 RULE E)

`944` recorded a **24.90 h** fingerprint interval and built the whole "loses by ~1.9 h" account on
it. **Two consecutive beats just changed it twice, 62 minutes apart.** There is no interval. The
24.90 h figure was two samples of a deploy cadence mistaken for a period.

**The rebuild needs ~26 h of uninterrupted deployed-source stability. It has never had it, and on
this evidence it will not get it while two lanes ship calibration code.** In 169 beats it has reached
127/128 once and been reset 11 times. That is the root cause of the frozen page, stated correctly for
the first time.

## POST-GRADE NOTE — lane1's amendment to `944`, received 2026-09-01 ~09:2xZ

Recorded for provenance only. **It changes no verdict in this file** and asks nothing of this lane.

Lane1 watched a second `:15` beat: the 09:15Z beat touched 26 rows, **all 26 already on `tennis`**,
and **0 of the 283 still on `table_tennis`**. The check predicate is unmoved at `283 / 61` an hour
later. So the stuck cohort's observed migration rate is **zero, not slow** — the poller re-visits the
same small set and never reaches the rest. The one-off move (44 rows, 08:15Z) is the whole of it
until **Q495** runs, and Q495 is built (`58aa4680`, PR #2500, CERT-664 staged) but **has never been
run**; its first run is `apply=false` and it will be graded before any apply.

Two consequences for this file:

1. **The `~105k rows` figure in "Why this is worth registering" is superseded.** It was inherited
   framing from `943`/`944`, never a measurement of mine. The realised move was **44 rows**. This
   does not touch the grade: Consequence 1 falsified the Q493→fingerprint link by two routes that are
   both independent of row count — the digest has **no data input at all**, and Q493 does not modify
   `precompute_calibration.py`. A 105k-row move and a 44-row move are equally incapable of moving a
   source hash. If anything the amendment makes the point cheaper to state.
2. **Consequence 3 is untouched.** "There is no fingerprint interval; the digest moves on
   calibration-source deploys" is a claim about deploy cadence, not about cohorts. Cohort stability
   neither supports nor threatens it.

Standing items carried, not acted on: stamp sha + UTC on every reading (Q495 will move things when it
lands); Setka must not move (`945534` = `table_tennis` 4); name the predicate on every Polymarket
figure — the narrow query, the broad marker set and the whole cohort are three populations. The
backfill is lane1's; this lane queues nothing.

## What this is NOT

- Not a build. Item 6 forbids building on it and nothing here is queued.
- Not a re-derivation of `944` Item 2, which is graded FALSIFIED and filed on #2052.
- Not a re-run of the refusal question, which `944` rules off the critical path.
- Not lane1's production check for Q493 — that is theirs. This is only the calibration-side
  side-effect that Item 6 asked this lane to watch for.
