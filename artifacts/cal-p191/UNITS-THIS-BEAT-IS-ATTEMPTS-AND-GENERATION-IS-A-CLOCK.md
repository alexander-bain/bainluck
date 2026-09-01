# CAL-P191 — `staged:units_this_beat` publishes ATTEMPTS, and `generation` is a clock

**Session:** CAL-P191, 2026-09-01, ~09:40–10:1x am PT / ~16:40–17:1xZ
**Issue:** #2052 · **Branch:** `program/calibration-190-the-rebuild-survives-a-deploy` (continued)
**Guards:** `backend/tests/test_units_this_beat_is_attempts_p191.py` — 8 tests, 1.02 s, green
**Under D-G:** test-only + artifacts. `_main_input_fingerprint()` re-verified `e2040f90154fae876f0fb65f5abf74c3` after the change. Inert.

---

## 0. Headline

Two modules write the ledger key `staged:units_this_beat`, meaning two different things, into the
same dict, and **the later writer wins silently**. The published number is **units the beat
STARTED**, not units it banked. On the live `16:32:11Z` beat that is **7, not 5**.

The overwrite is deliberate and load-bearing. The **change of definition that rode along is not**,
and no test has ever observed it, because the suite exercises each writer alone and the two readings
coincide on any beat that does not cancel a unit. Since the fence work, every beat cancels.

Separately: **`generation`** — the last untested quotable gauge on CAL-P190's list — **is a
wall-clock reading in epoch milliseconds**, minted fresh every beat. It cannot detect a rebuild
restart in either direction, and it reads exactly like the counter that could. **That list is now
exhausted.**

---

## 1. The mechanism

`app/utils/calibration_phase_ledger.py`:

| method | line | write rule | store |
|---|--:|---|---|
| `record_stage(name, duration_ms)` | 1230 | `stages[name] += ms`, `stage_counts[name] += 1` | `stages` |
| `record_gauge(name, value)` | 1301 | `stages[name] = value` | **`stages` — the same dict** |

`record_gauge`'s own docstring says so: *"Same store, so everything that already reads `stages` keeps
working; different write rule."* That is correct and intended. The consequence nobody wrote down is
that **a key written by both APIs publishes whichever ran last, with no trace of the other.**

## 2. The two writers

| writer | file:line | value | what it counts |
|---|---|---|---|
| frozen (ruling 009) | `precompute_calibration.py:4446` | `record_stage(..., ran_this_beat)` | **banked** — `ran_this_beat` increments only after `runner.commit(db)` **and** `save_staged_cursor` succeed (`:4732-4734`) |
| replacement | `calibration_main_build.py:1561` | `record_gauge(..., stage_counts["read:futures_unit"])` | **attempts** — `runner.stage("read:futures_unit")` records on every exit of the unit stage, exceptional ones included |

The replacement exists for a good reason (CAL-P066 / #1680): the frozen writer sat where it was
skipped on every non-publishing beat, so production carried `read:futures_unit` as a **sum with no
divisor**. The fix put the divisor on the path that runs whatever the terminal. `precompute_calibration.py`
is frozen, so it could not be fixed where it was written — and so the old writer was left in place
rather than removed. **Both now run, and the new one lands second.**

## 3. The evidence — live ledger, `2026-09-01T16:32:11.447482Z`

From `payload->'stages'` (32 keys; `payload` itself has 24 top-level keys):

```
read:futures_unit                 989822     <- SUM of 7 stage observations
staged:units_this_beat                 7     <- ATTEMPTS (gauge writer won)
staged:units_completed_this_beat       5     <- banked
staged:units_cancelled                 2
staged:unit_ms_mean               141403     <- 989822 / 7   (attempts)
staged:unit_ms_mean_completed      56431     <- completed-only
staged:unit_cancelled:5dff80cbde54f5ce  353845
staged:unit_cancelled:cb3ac74e5a8b3f10  353838
```

Arithmetic, checked: `989822 / 7 = 141403.1` ✓ (matches `unit_ms_mean` exactly).
`(989822 − 353845 − 353838) / 5 = 56428` ≈ `56431` ✓.

**7 = 5 + 2 holds only because the attempts reading won.** Read the frozen writer at `:4446` at face
value and you would expect `units_this_beat` to be 5, making the identity read `5 = 5 + 2`. CAL-P190's
ITEM 2 quotes the identity and is right about the numbers — for a reason it does not state.

**This is one defect with P189 §5c, not two.** `read:futures_unit`'s observation count is
simultaneously the value of `units_this_beat` and the divisor of `unit_ms_mean`. P189 caught the
denominator half and told the lane to use `unit_ms_mean_completed`. The numerator half is the same
substitution and has the same fix already published beside it: **`units_completed_this_beat`.**

## 4. Why no test caught it

`tests/test_staged_rate_projection_1680.py:124` asserts `stages["staged:units_this_beat"] == 9`
after calling the **gauge writer alone** on a ledger of 9 all-completed units. Nothing in the suite
runs both writers on one ledger, and nothing runs either on a ledger containing a **non-completed**
`read:futures_unit` observation. With no cancellation the two readings are equal, so the healthy
case is structurally incapable of showing the disagreement — the guard added here pins that too
(`test_a_beat_with_no_cancellation_hides_the_disagreement`).

## 5. 🔴 Correction to the standing read protocol (CAL-P190 ITEM 1b)

ITEM 1b tells every session to read the ledger directly and calls it "the best read". It is. But it
does not say **which dict**, and the payload has two that share key names:

* **`payload->'stages'` — this is the one with the values.** 32 keys, everything the directives quote.
* **`payload->'stage_counts'` — emission counts.** `staged:units_this_beat` reads **1** there (one
  emission) beside `stages`'s **7**. `staged:units_done` reads **1** beside `stages`'s **45**.

Exactly **one** key in `stage_counts` is a quantity a reader wants: **`read:futures_unit` = 7 =
attempts this beat**. `staged:units_cancelled` reads 2 in *both* dicts, by two unrelated accidents
(the caller passes a literal `1` per cancellation, so the ms-sum and the emission count coincide).

**`stage_counts` is the trap, and its name is what makes it one** — it sounds like the dict you want
when you are counting units.

## 6. 🆕 `floors` is a SECOND carried ring, and no directive mentions it

P189 found `unit_worst_history` and called it "the one piece of carried state the sampler can never
show". There is another in the same payload. `payload->'floors'` carries a **10-entry ring per
phase**:

```
sports                 [4180, 3792, 3223, 3168, 3189, 3137, 3190, 3144, 3689, 5178]
futures                [988407, 997649, 1174354, 1049916, 1061303, 1076115, 1196611, 1163988, 1120758, 1030728]
diagnostics            [4512, 92590, 45421, 106745, 123869, 84667, 51663, 50663, 96466, 56488]
serialize_gate_publish [2011, 2386, 1892, 2186, 1131, 1190, 1243, 1025, 977, 1003]
```

The last `futures` entry (1,030,728) matches this beat's `elapsed_ms` (1,031,102) to 374 ms — the
ledger's own `unmeasured_overhead_ms`. It feeds `derive_plan(..., floors=...)` and therefore the
**`phase_bound` term of the fence model**, which is why the fence model has never seen it bind:
`futures` floors run 0.99–1.20 M ms against fences of ~0.35–0.41 M.

**Not chased further.** Recorded so the next session does not re-discover it, and parked as `P191-2`.

## 7. What is NOT claimed

* **No fix.** Choosing which writer wins changes the meaning of a gauge that five graders read. That
  is a fold's call under ruling 134, not a build lane's. The guards characterize; they do not assert
  the behaviour is correct.
* **This does not explain P189's `14:34` residual** (7 = 5 + 1 + 1 unattributed). It explains the
  *definition* — `units_this_beat` is attempts — but a beat with 7 attempts, 5 banked and only 1
  classified cancellation still has one unit that left `read:futures_unit` without banking and
  without a classified statement timeout. Every such path in `_run_staged_futures` either re-raises
  (ending the beat `thrown`) or returns before the projection is recorded. **Unresolved; parked.**
* **Nothing here bears on the fence model**, which CAL-P190 confirmed to 2 ms and which is not
  re-measured in this session.

## 8. Session state, unchanged from CAL-P190

* Fingerprint `e2040f90154fae876f0fb65f5abf74c3`, live == local predictor == ledger's
  `input_fingerprint`. **No fifth reset.**
* `origin/master` `35c50d48`, unmoved. `git diff --name-only 7d066c50 origin/master | grep -i calib`
  ⇒ empty, exit 1. **All-clear.**
* Ledger still at the `16:32:11Z` beat: banked 45/128, `served_units` 0, `published` false,
  `terminal` cancelled. Ring 11 entries, seed at index 0. **ETA `09-02T08:30–09:30Z` unchanged.**
* Published curve `generated_at 2026-08-31T04:37:36Z` — twenty-sixth session unchanged, fully
  explained.
* **D-G in force.** Nothing deployed, nothing merged.
