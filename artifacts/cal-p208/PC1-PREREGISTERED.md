# PC-1 — pre-registered, CAL-P208, written 2026-09-01 ~21:58Z

**Subject:** CERT-697 / CAL-P205 layer 1 — "the staged cursor keys off the emitted statement".
**Merged:** `c1397139` (integrator's sanctioned merge train).
**Deployed:** Heroku **v3981**, `c1397139`, **2026-09-01T21:48:31Z**.
**Written BEFORE the first post-deploy beat (22:15:00Z). Nothing below is an observation.**

## Why this beat is a clean test

The release landed in the **idle gap**: last cursor write 21:21:26Z, ledger converged 21:33:53Z,
deploy 21:48:31Z, next beat 22:15:00Z (`crontab(minute=15)`, `backend/app/tasks/__init__.py:4892`).
**No in-flight unit was killed**, so `P199-3`'s ~16%-of-beats-die-to-a-mid-beat-release confound
does not apply to this observation.

## The precondition, measured (not assumed)

The cursor on disk carries `input_fingerprint = e2040f90154fae876f0fb65f5abf74c3` — the **WIDE**
digest, which is exactly what `precompute_calibration.py` passes as
`legacy_input_fingerprint=runner.fingerprint`. It also carries `schema=calibration-staged-futures/v1`,
`task=precompute_calibration_main`, `unit_key=vm_id`, `population_version=q268`, and a non-null
`accumulator` — so the five checks that precede the fingerprint branch all pass, and control
reaches the CAL-P205 branch rather than short-circuiting above it.

## PREDICTION (pass condition)

At the beat starting **22:15:00Z**, converging ~22:33Z:

1. `staged:cursor_reason:legacy_fingerprint_accepted` is present in `payload->'stages'`, and
   `staged:cursor_reason:resumable` is **absent** — the two are mutually exclusive by construction:
   `REASON_LEGACY_FINGERPRINT_ACCEPTED if legacy_accepted else (REASON_RESUMABLE if resumable ...)`
   (`calibration_staged_futures.py:1821-1823` @ `c1397139`).
2. **NEGATIVE CONTROL — the load-bearing arm.** The cursor row's
   `jsonb_array_length(committed_units)` is **≥ 70** and **NOT 0**. Baseline 70/128 at generation
   `1788297300187`.
3. The cursor's stamped `input_fingerprint` **changes** from `e2040f90154fae876f0fb65f5abf74c3`
   to exactly **`78143607db6fd8116af5fadeffef6799`** — the self-draining re-stamp.

   *Computed locally before the beat, not guessed.* `git diff HEAD c1397139` on
   `precompute_calibration.py` touches `_main_futures_sql`, `CALIBRATION_POPULATION_VERSION` and
   `REPRESENTATIVE_TIE_AUTHORITY` **only inside the new function's own body/docstring** — all three
   symbols are byte-unchanged — so the worktree can reproduce the deployed digest:
   `input_fingerprint("staged-unit/v1", "q268", "canonical-outcome-id/v1", md5(_main_futures_sql(frozen=True)))`
   over an 81,990-char statement ⇒ `78143607db6fd8116af5fadeffef6799`.
   **The two digests differ**, which is the precondition for the cutover branch being reached at
   all; had they collided, `resumable` would fire and the cutover would be untestable.
   `population_version` `q268` also matches the cursor, so `REASON_POPULATION_VERSION` cannot fire.
4. At the **23:15Z** beat, the token reverts to `staged:cursor_reason:resumable` and never returns
   to `legacy_fingerprint_accepted` for this cursor.

## FALSIFIER

`staged:cursor_reason:input_fingerprint_changed` **and** `committed_units` = 0 ⇒ the deploy that
shipped the fix for wiping the bank wiped the bank. **Registered as a fail.**

## 🔴 THE RUBRIC HOLE I AM RECORDING BEFORE I GRADE (this is finding P208-1)

The conveyor's PC-1 rubric names **three** tokens. The deployed code can emit **fifteen**
(14 constants + a dynamic `envelope_{status}`). Classified by what they do to the bank:

| token | action | bank |
|---|---|---|
| `legacy_fingerprint_accepted` | RESUME | **kept** ← predicted |
| `resumable` | RESUME | **kept** |
| `nothing_banked` | FRESH | nothing to keep |
| `lease_held_by_other` | REFUSE | kept, beat stands down — 🔴 **records NO token at all** (P204) |
| `absent` | FRESH | nothing there |
| `input_fingerprint_changed` | INVALIDATE | **WIPED** ← the named falsifier |
| `malformed` | INVALIDATE | **WIPED** |
| `schema_mismatch` | INVALIDATE | **WIPED** |
| `task_mismatch` | INVALIDATE | **WIPED** |
| `unit_key_mismatch` | INVALIDATE | **WIPED** |
| `population_version_changed` | INVALIDATE | **WIPED** |
| `malformed_units` | INVALIDATE | **WIPED** (two sites) |
| `unencoded_units` | INVALIDATE | **WIPED** |
| `unfolded_units` | INVALIDATE | **WIPED** |
| `read_failed` | INVALIDATE | **WIPED** |
| `envelope_{status}` | INVALIDATE | **WIPED** (dynamic token) |

> **Eleven distinct tokens wipe the bank. The rubric names ONE of them = 9.1%.**

So a wipe arriving via `schema_mismatch`, `read_failed` or `envelope_*` would show bank = 0 under a
token the rubric cannot interpret, and a session grading on the token list alone could read a real
wipe as "falsifier did not fire ⇒ PASS". **This is why arm 2 (the negative control on
`committed_units`) is the load-bearing arm and the token is diagnostic, not decisive.** The
conveyor was right to include the negative control; its token list is the incomplete part.

**Grading rule adopted for this session, stated in advance:** PASS requires arm 2 (bank not wiped)
**and** arm 1 (the token is one of the three bank-keeping tokens). Any of the eleven wipe tokens ⇒
FAIL regardless of which one. `lease_held_by_other` ⇒ **UNGRADED, retry next beat** (no token is
written, and the beat did no work).
