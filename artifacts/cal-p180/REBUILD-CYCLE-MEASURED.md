# CAL-P180 — the rebuild cycle, measured: it FINISHES, and a reset to 0 is a SUCCESS

**Session:** CAL-P180, 2026-09-01 08:56–09:20Z / 01:56–02:20 am PT
**Instrument:** `GET /api/admin/calibration-beat-gauges?full=true`,
artifact `artifact_generated_at 2026-09-01T08:45:21.377128Z`, 168 observations
spanning `2026-08-25T08:35:37Z` → `2026-09-01T08:31:38Z`.
**Nothing here is inherited.** Every number is computed from that one artifact,
plus two source-level checks in the worktree.

---

## 0. THE HEADLINE — this corrects CAL-P178/P179 and the record on #2052

The record currently says the rebuild *"has hit 127/128 once and reset **11** times"* and is
*"structurally unable to finish while calibration code ships."*

**Measured: it finished SEVEN times in the last five days.** A bank reset to 0 under an
**unchanged** fingerprint is not a failure — it is the rebuild **completing and installing a
fresh artifact**. On every one of those beats `staged:served_units` goes to **128**,
`staged:served_at` becomes **present**, and the gate is actually evaluated.

| what a bank drop means | count in window | evidence |
|---|--:|---|
| **rebuild COMPLETED** (same fp, artifact installed) | **7** | `served_units 0→128`, `served_at` present, gate evaluated, 5 of 7 `gate: pass` + `published: true` |
| **rebuild WIPED** (fp changed = a deploy) | **3** | `served_at` absent, `gate: not_evaluated`, `published: false` |

So the mechanism is not broken and never was. **66 of the 168 beats published.** What is broken
is narrower and far more tractable: the last **two consecutive** rebuild cycles were each killed
by a deploy, and that is the whole of the 27.9-hour outage.

---

## 1. `units_planned: 128` IS A PLAN, NOT A FINISH LINE

Every completed cycle finished **below** 128. Observed completion banks:

```
123 · 122 · 123 · 124 · 127 · 122 · 126        (mean 123.9, range 122–127)
```

This matters because every prior write-up graded progress as `N/128` and read 119, 126, 127 as
*near-misses*. They were not near-misses — **122 is enough**. The correct completion predicate is
`beats_to_publish == 0`, or equivalently `served_units` flipping to 128; it is **never** `bank == 128`.

🔴 **Do not describe the bank as "N/128 needed".** It overstates the remaining distance by up to 6
units (>1 hour) and it is why a run that was one beat from done got read as six units short.

---

## 2. THE RUN THAT DIED AT THE FINISH LINE

Segment `75faaed682d9`, 24 beats, `2026-08-31T06:37:31Z` → `2026-09-01T06:31:41Z`:

```
06:37:31   5        BTP 9
07:50:43  10  (+5)  BTP 9
...        dead-steady +5 every beat, 22 consecutive beats ...
04:19:20 109  (+4)  BTP 1
05:37:30 114  (+5)  BTP 1
06:31:41 119  (+5)  BTP 1     <-- last beat before the wipe
07:31:29   5              <-- fingerprint af47b8e0…, bank wiped
```

Climbed **5 → 119 (+114) in 23.9 h** over 24 beats — **4.96 units/beat, 4.77 units/h**, with a
variance of exactly one unit across the entire run.

**It was one beat from finishing.** Its own gauge printed `beats_to_publish: 1` for the final
three beats, and prior cycles completed at 122–127 — the next beat would have banked ~124 and
installed the artifact. It died at 07:31:29Z because a deploy moved the fingerprint.

---

## 3. ~26 HOURS IS NO LONGER AN EXTRAPOLATION

D-G's honest caveat was *"~26 h is an extrapolation from the current ~5 units/beat, not a measured
full run."* **It is now measured**, three independent ways, and they agree:

| method | full-cycle estimate |
|---|--:|
| measured rate 4.77 units/h × 124 units to completion | **26.0 h** |
| the `75faaed6` run: 23.9 h to reach BTP 1, +1 beat | **~24.9 h** |
| 7 completed cycles over the 131-h `b18200401ebc` segment | **~18.7 h mean** |

**A fresh rebuild needs 24–26 h of deployed-source stability.** The historical mean is faster
(18.7 h) because earlier cycles ran at a higher units/beat; 24–26 h is the correct planning figure
at today's rate, and it is the conservative end.

---

## 4. THE CLOCK IS RUNNING CLEAN RIGHT NOW — verified from source

- `origin/master` = `3ab15b2053b8dfdba34ad9fd6307490222d6817b`.
- `backend/app/tasks/precompute_calibration.py` is **byte-identical** (sha256 `f8ab05f1a2ebb984…`)
  across `2f28aa30` / `2aac5843` / `3ab15b20` / `origin/master`. Only `3807f8a1` differs
  (`ed5895a8084ef601…`).
- Executed the predictor at the worktree HEAD:
  `_main_input_fingerprint()` → **`e2040f90154fae876f0fb65f5abf74c3`**, which is **exactly** the
  live beat's fingerprint at `08:31:38Z`.

⇒ **No reset is baked in.** Nothing already merged will wipe the current rebuild. The run that
started at `08:31:38Z` with bank 5 will complete at roughly **`2026-09-02T08–10Z`** *if and only
if nobody deploys `precompute_calibration.py` before then.*

This is the cheap predictive check and it should be run every session:

```bash
cd backend && python3 -c "from app.tasks import precompute_calibration as pc; print(pc._main_input_fingerprint())"
```

Differs from the live beat's fingerprint ⇒ a reset is already queued behind the next deploy and
the current rebuild is doomed; you know it now instead of 25 h from now.

---

## 5. WHAT THIS DOES TO D-G

It strengthens it and removes its caveat. The ask was *"freeze calibration-source deploys ~26 h
and the page unfreezes itself."* The objection a reader could have raised — *"you've never seen it
finish, you're extrapolating"* — is now dead: **it finished seven times in five days**, and the
only two cycles that failed are the two that a deploy interrupted.

The cost of (b) *keep shipping* is now quantified: at today's rate a calibration-source deploy
destroys up to **~26 hours** and up to **~127 units** of completed compute, and it does so
silently — `gate: not_evaluated`, no drift flag, no alert.

**Not started on this lane's authority.** D-G binds lane1 too and remains Alex's call. This
session deployed nothing and pushed no code, consistent with the unanswered default (a).

---

## 6. STANDING CORRECTIONS FOR THE NEXT SESSION

| previously recorded | measured here |
|---|---|
| "11 resets" | **10 bank drops** in the window — **7 are completions**, only **3** are fp wipes |
| "hit 127/128 once", peak framing | completion happens at **122–127**; `128` is a plan, not a threshold |
| "structurally unable to finish while calibration code ships" | it **finished 7×**; two consecutive cycles were interrupted, which is the entire outage |
| "~26 h is an extrapolation" | **measured**: 4.77 units/h, 23.9 h to BTP 1, 24–26 h full cycle |

**Unchanged and still true:** `served_at_absent` is what blocks the page; the bank was never the
publish trigger; the two dead hypotheses (100% drift, staleness) stay dead; the gauge artifact can
be up to ~14 min blind, so read `artifact_generated_at` first.
