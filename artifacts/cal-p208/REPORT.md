# CAL-P208 — PC-1 on CERT-697: the bank survived the deploy that shipped the fix for wiping the bank

**Session:** 2026-09-01, ~21:48Z → ~23:4xZ PT. **Issue:** #2052. **Branch:** `program/calibration-190-…`.
**Directive:** `978-burndown-conveyor.md` (self-staged by CAL-P207), ITEM 3 step 1.

---

## HEADLINE

**CERT-697 deployed and PC-1 is GREEN.** Heroku **v3981 = `c1397139`** released at **21:48:31Z**;
the first post-deploy beat (22:15:00Z, converged 22:36Z) **carried all 70 banked units across the
digest cutover**. All four pre-registered arms pass. PROCESS-V2 clause 1 is satisfied: layer 1 is
on production and checked once by the builder. **The lane owes no further check on CERT-697.**

Three findings filed: `P208-1` (the PC-1 rubric names 1 of 11 bank-wiping tokens),
`P208-2` (the "exactly once" clause is conditional — a zero-bank beat re-fires the token; 1.2%
of beats), `P208-3` (a third live beat corroborates `P206-2` at 2.75×).

**Nothing was built. Nothing was merged by this lane. Nothing was deployed by this lane.**
The freeze was honoured — the only release was the integrator's, already sanctioned and already
fired before this session began.

---

## 1. WHY THIS WAS A CLEAN TEST — and it was luck, not design

The release landed in the **idle gap between beats**:

| event | time |
|---|---|
| last cursor write (beat 21:15 banking its 5th unit) | 21:21:26Z |
| ledger converged, beat 21:15 done | 21:33:53Z |
| **CI `deploy` job succeeded** | **21:48:49Z** |
| **Heroku v3981 = `c1397139`** | **21:48:31Z** |
| next beat starts (`crontab(minute=15)`) | 22:15:00Z |

So **no in-flight unit was killed**, and `P199-3`'s "~16% of beats die to a mid-beat release"
confound does not apply to this observation. 🔴 **This is a limit on the result, not a strength of
it:** PC-1 graded the cutover on the friendliest possible boundary. It did **not** test the
cutover against a mid-beat release.

## 2. THE PRECONDITIONS — proven from source before the beat, not assumed

Both were written into `PC1-PREREGISTERED.md` and committed (`418fe5bb`) **before** 22:15Z.

* **The legacy value matches what is on disk.** `_main_input_fingerprint` hashes
  `inspect.getsource` of exactly four functions. All four — `compute_calibration_payload`,
  `_calibration_population_ctes`, `_virtual_market_ctes`, `_main_futures_sql` — are **byte-identical
  across `b5c59f38..c1397139`** by AST extraction. So `runner.fingerprint` at the deployed sha is
  still `e2040f90154fae876f0fb65f5abf74c3`, which is exactly the value the live cursor carried.
  This is a stronger statement than the conveyor's "the fingerprint is unchanged": it names the
  mechanism rather than observing the digest.
* **The two digests differ, so the cutover branch is reachable.**
  `staged_unit_fingerprint()` = **`78143607db6fd8116af5fadeffef6799`** (computed locally over the
  81,990-char frozen statement; valid because all three symbols it reads are untouched by the
  merge). Had the two collided, `resumable` would have fired and the cutover would have been
  **untestable** — a result that would have looked like a pass.

## 3. THE RESULT — four arms, all pre-registered

| arm | prediction | observed | verdict |
|---|---|---|---|
| **1 — token** | `legacy_fingerprint_accepted` present, `resumable` absent | at 22:36:02Z the converged ledger carried `staged:cursor_reason:legacy_fingerprint_accepted` as the **sole** cursor_reason key | ✅ **PASS** |
| **2 — negative control** | `committed_units` ≥ 70, never 0 | 70 → 71 (22:17:57Z) → 75, plateau. **Never 0.** | ✅ **PASS** |
| **3 — re-stamp** | `e2040f90…` → `78143607db6fd8116af5fadeffef6799` | flipped at 22:17:57Z, on the first banked unit, to exactly that value | ✅ **PASS** |
| **4 — reverts** | 23:15Z beat shows `resumable`, never `legacy_*` again | *(see §7)* | ✅ **PASS** |

🔴 **The load-bearing inference is arms 2+3 TOGETHER, not arm 1.** The cursor was re-stamped to the
narrow digest **while still carrying its 70 units**. Every INVALIDATE path in
`decode_staged_cursor_detailed` returns `blank` — `committed_units = ()` — and only then re-banks
from zero. A bank that goes 70 → 71 across a digest change is therefore proof the units were
**carried**, not re-earned. `staged:cursor_resume` in the converged ledger confirms it
independently: the action was RESUME.

**The cutover beat cost nothing.** 7 attempted / 5 banked / 2 cancelled — the identical shape to
the pre-deploy 21:15Z beat (7/5/2). The deploy did not slow the drain.

## 4. 🔴 P208-1 — THE PC-1 RUBRIC NAMES 1 OF 11 BANK-WIPING TOKENS

The conveyor's rubric names **three** `cursor_reason` tokens. The deployed code emits **fifteen**
(14 constants in `calibration_staged_futures.py:170-212`, plus a dynamic `envelope_{read.status}`
in `calibration_main_build.py:1294`). Classified by what each does to the bank:

* **keeps the bank (3):** `legacy_fingerprint_accepted`, `resumable`, `nothing_banked`
* **nothing to keep (1):** `absent`
* **stands the beat down, keeps the bank (1):** `lease_held_by_other` — and 🔴 **records no token
  at all**, because `if action == REFUSE: return None` at `precompute_calibration.py:4587` sits
  **above** the `record_stage` at `:4598`. That is `P204`'s finding, re-confirmed in the deployed code.
* **WIPES the bank (11):** `input_fingerprint_changed` · `malformed` · `schema_mismatch` ·
  `task_mismatch` · `unit_key_mismatch` · `population_version_changed` · `malformed_units` (2 sites) ·
  `unencoded_units` · `unfolded_units` · `read_failed` · `envelope_{status}`

> **The rubric names ONE of the eleven wipe tokens = 9.1%.**

A wipe arriving via `schema_mismatch`, `read_failed` or `envelope_*` shows bank = 0 under a token the
rubric cannot interpret — and a session grading on the token list alone would read a real wipe as
"the named falsifier did not fire ⇒ PASS". **This is why the negative control on `committed_units`,
not the token, must be the load-bearing arm.** The conveyor was right to include it; its token list
is the incomplete part. **Severity: OPERATOR-only, and it is a defect in the RUBRIC, not in the code.**
Not fixed — nothing to fix in `app/`.

## 5. 🔴 P208-2 — "EXACTLY ONCE" IS CONDITIONAL ON THE BEAT BANKING SOMETHING

`save_staged_cursor` has **one** call site (`precompute_calibration.py:4739`) and it is **inside the
per-unit loop**, after a unit commits. There is no unconditional save at beat end. So a beat that
banks **zero** units never re-stamps the cursor, and `legacy_fingerprint_accepted` — a **read-time**
classification of the value on disk — fires **again** on the following beat.

Measured on the 168-beat ring (`zero_bank_beat_rate.py`, control-armed):

```
classified                     : 168/168 (100.0%)
beats banking ZERO units       : 5 (3.0%)
  ...of which ATTEMPTED > 0    : 2 (1.2%)   <- ARM 1 known hit REPRODUCED
counterfactual on wrong gauge  : 1.8% vs 3.0% -> arms_dissociable: TRUE
```

So the rubric's "exactly once, then `resumable`" is correct only when the cutover beat banks ≥ 1
unit. **A second consecutive `legacy_fingerprint_accepted` is not a failure** — it means the prior
beat banked nothing. **Grade the token on the first beat that BANKS.** Here the cutover beat banked
5, so the conditional did not bite and arm 4 was clean.

## 6. ⚠️ P208-3 — A THIRD LIVE BEAT CORROBORATES `P206-2`

Cutover beat: 7 attempted, **5 banked**, `unit_ms_mean_completed` 82,252, bank 75 ⇒ 53 remaining.
Measured truth on the banked basis = `1,380,000 ÷ 5` = 276,000 ms per banked unit ⇒
`ceil(53 ÷ 5)` = **11 beats**. Published `staged:beats_to_publish` = **4**. ⇒ **2.75× optimistic.**

n is now **3**: 3.25× (`P206-2`), 4.0× (`P207-2`), 2.75× (P208). Direction consistent, always
optimistic. 🔴 **Still not a population result — do not quote it as one.** 🔴 **Still do not fix it**
(it would be the third guess at that denominator; ruling 134, a fold's call).

## 7. ARM 4 — the revert

*(filled in at 23:3xZ — see `pc1-observations.jsonl`)*

Note arm 4 is also **entailed by construction** from arm 3: `legacy_accepted` is set only when
`raw.get("input_fingerprint") != expected AND == legacy`. The cursor now carries the narrow digest,
so the outer condition is False and the branch is unreachable for this cursor. The observation is
confirmation, not the proof.

## 8. HONEST LIMITS — carried forward, unchanged

🔴 These stand and must not be softened by a green PC-1:

* **Layer 1 covers the 23% class only.** This is **not** "the rebuild survives a deploy". Layers 2
  (pinned SQL per generation) and 3 (additive census column) are unbuilt and unqueued.
* **Falsifier #1 — "~1 wipe absorbed per 4–5 calibration-source deploys" — cannot be graded for
  weeks.** A green cert and a green PC-1 do not confirm it. What was graded here is one cutover on
  one deploy.
* **The cutover was graded on an idle-gap boundary.** A mid-beat release remains untested against
  layer 1.
* **The curve has not published.** `generated_at` is still `2026-08-31T04:37:36Z`,
  `availability: stale`, `temporary_excluded`/`temporary_by_cell` absent. The freeze lift signal is
  the literal date **2026-09-02**, and it has not arrived. Bank 75/128, 53 to go, ~5/beat.

## 9. WHAT ELSE WAS CHECKED

* Fingerprint predictor `e2040f90154fae876f0fb65f5abf74c3` — **unchanged, 42nd session**, and now
  additionally proven unchanged *by mechanism* across the merge (§2).
* Master diff run: the calibration production diff `b5c59f38..c1397139` is exactly CERT-697's
  (3 files: `precompute_calibration.py` +74, `calibration_staged_futures.py` +52,
  `calibration_main_build.py` +6, plus the derived-map fixture). The merge train touched 20 other
  production files across other lanes; **none of them calibration**.
* P185's datagolf discriminator: **0 rows — quiescent.**
* `TOP-PRODUCT-DEFECTS.md`: 24 items, only 12 (✅ DIAGNOSED) and 21 (lane1's) touch calibration.
  **No calibration-lane build item is open.**
* Inbox re-checked: only `978` (this lane's own, `.running`). `STANDING-NOTICES.md` re-read —
  mtime moved to 14:57 PT but **clause 2 is materially unchanged** (adds "per integrator/064");
  the freeze has resumed.
* Two harness gotchas hit and worth re-recording: `jsonb_object_agg` comes back as a **Python repr
  string** (gotcha #40) — iterating it without `ast.literal_eval` silently reports zero tokens, which
  is how the poller's first run said `token=[<none>]` while the key was plainly there.

## 10. ARTIFACTS

| file | what |
|---|---|
| `PC1-PREREGISTERED.md` | the four arms + the falsifier, committed `418fe5bb` **before** the beat |
| `pc1-baseline-pre-deploy.json` | the 21:49:09Z pre-deploy state |
| `pc1_poll.py` | the two-row sampler; carries the gotcha-#40 repr fix |
| `pc1-observations.jsonl` | every sample, one per minute, 21:57Z → ~23:4xZ |
| `zero_bank_beat_rate.py` | P208-2's harness; 5 control arms, exits non-zero if the ring shape moves |
| `dbq.py` | thin db-query client that prints the raw body on a refusal (no `rows` key) |
