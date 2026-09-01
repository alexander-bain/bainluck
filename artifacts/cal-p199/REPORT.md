# CAL-P199 (#2052) — a cancelled phase records no reason, by construction

**Session 2026-09-01, ~11:2x–11:4x PT. Read-only: no `app/` edit, no deploy, no merge, no worktree.**
D-G's stated default (a) = freeze was acted on. Two new harnesses, both exit 0, both run from any cwd.

---

## 0. The one-paragraph version

**The beat moved for the first time in five sessions — 50 → 55 of 128 units banked, no publish — and
it did not stop at any fence.** It stopped 67,258 ms short of its own unit bound and 784,786 ms short
of its window, recording **none** of the module's four named stop-reasons. The reason it recorded
nothing is a **falsy-empty-string test**: `PhaseRunner.abort` stores the dying phase's reason as
`str(exc)[:200]`; `PhaseLedger.fail` keeps `detail or None`; `PhaseRecord.as_payload` emits the key
only `if self.detail`. `str(asyncio.CancelledError())` is `''` — and `CancelledError` is exactly the
type `classify_failure` maps to status `cancelled`. **The status that most needs a reason is the only
one guaranteed not to have one.** This is a **sixth** instance of the falsy class the conveyor
recorded as CLOSED: CAL-P198-3's sweep passed over both of these modules because it looked for
numeric falsy defaults only. Separately, the deploy-kill census over 168 captured beats came back
**NEGATIVE** on the general claim — beats survive a mid-beat release 16 of 19 times — and that
negative is reported here as the result, not buried.

---

## 1. What the live beat actually did — reconciled to 13 ms

Ledger row `calibration:main:phase_ledger`, `updated_at 2026-09-01T18:24:55.805978Z`
(the previous four sessions all read the same unmoved `17:31:46.517193Z` row).

| quantity | value | source |
|---|--:|---|
| task start | `18:15:00.6Z` | `updated_at − elapsed_ms` |
| `elapsed_ms` | 595,214 | top level |
| `read:futures_generation` | 27,297 | `stages` |
| units completed | 5 | `staged:units_completed_this_beat` |
| cost of a completed unit | 52,423 | `staged:unit_ms_mean_completed` |
| completed unit time | 262,115 | 5 × 52,423 |
| unit 6 admitted at task-elapsed | **308,705** | derived, see below |
| unit 6's own fence | **353,754** | `staged:unit_bound_ms:futures` |
| window left when unit 6 started | 1,071,295 | `staged:unit_bound_headroom_ms:futures` + fence |
| unit 6 ran for | **286,496** | `read:futures_unit` 548,611 − 262,115 |
| task end | 595,201 vs 595,214 | **13 ms residual** |

**Both fence formulas reproduce exactly.**

* Unit fence: `max(ring) × 1.5 − 30,000` = `255,836 × 1.5 − 30,000` = **353,754** ✅ (ring =
  `payload->'unit_worst_history'`, 13 entries). The conveyor's fence model is confirmed a fourth time.
* Window: `remaining_ms = (soft_limit_ms − cleanup_margin_ms) − elapsed` = `1,500,000 − 120,000 −
  elapsed` = `1,380,000 − elapsed`. Headroom `717,541 = 1,071,295 − 353,754` ⇒ elapsed 308,705,
  which is `262,115 + 27,297 + ~19,293` of overhead. ✅

### 1a. 🔴 It matched none of the four exits

`stages` contains **no** `staged:window_stop:deadline`, **no** `staged:window_stop:unit_too_large`,
**no** `staged:window_stop:units_cancelling`, **no** `staged:units_cancelled`, and **no**
`staged:window_left_ms`. Every stop-recorder in `precompute_calibration.py:4620-4719` is silent, yet
`payload->'phases'[0].status == 'cancelled'`.

**This is a tenth cancellation and it sits 67,258 ms from its bound.** The conveyor's standing claim
— *"NINE cancellations across FOUR fence levels, every one dead inside 531 ms of its own bound"* —
now reads **nine of ten**. A future session grading this beat against that envelope would mis-file it
as a fence event. 127× outside the stated envelope.

### 1b. 286,496 ms went into the term P198-1 proved is KEPT

That dead unit's time is accumulated into `read:futures_unit` regardless. Per CAL-P198-1, `usable_ms`
subtracts only NON-unit overhead, so **52.2% of this beat's unit stage is time that banked nothing
and is modelled as usable**. The gauge duly reports `staged:beats_to_publish = 3` while 73 units
remain and the beat banked 5 — **~15 beats, a 5× over-claim**, on a fresh specimen, exactly the
direction P198-1's r = −0.016 / 68% / 33× population result predicts.

---

## 2. 🔴 THE FINDING — `P199-1`, the sixth falsy instance

```
calibration_main_build.py:579-581   abort() -> close_open_phase(..., detail=str(exc)[:200])
calibration_phase_ledger.py:1360    fail()  -> record.detail = detail or None      # falsy STRING
calibration_phase_ledger.py:1128    as_payload() -> if self.detail: payload["detail"] = ...
calibration_main_build.py:570-571   classify_failure(): CancelledError -> CANCELLED
```

`str(asyncio.CancelledError())` is `''`. Both tests are truthiness tests on a string, so the reason
is erased and then the key is omitted entirely — and under gotcha #53 an absent key reads as *fine*.

**Why this is not cosmetic.** `StagedFuturesIncomplete` — the *designed, healthy* end of a staged
beat ("units banked, nothing published", `precompute_calibration.py:5002`) — **also** classifies as
`cancelled`, and it **does** carry a message. So `detail` is the only field anywhere in the ledger
that separates *"the beat ended as designed"* from *"the beat was killed from outside"*, and it is
precisely the field the falsy test destroys. The two render identically as `status: 'cancelled'`.

**The live row proves the path taken.** The futures phase has no `detail` key. Per CONTROL+A below,
a `StagedFuturesIncomplete` end *would* have carried its 60-character message. It did not — so this
beat did not end the designed way.

### 2a. The harness — `backend/scripts/cal_p199_cancelled_detail_erasure.py`, exit 0

```
str(asyncio.CancelledError()) = ''  falsy=True

CLAIM     CancelledError()                 -> status='cancelled' detail=None       emitted=False
CONTROL+A StagedFuturesIncomplete(msg)     -> status='cancelled' detail='futures…' emitted=True
CONTROL+B RuntimeError('a real failure')   -> status='failed'    detail='a real…'  emitted=True
CONTROL-  CancelledError('a reason')       -> status='cancelled' detail='a reason' emitted=True
```

Three control arms, all required to pass. **CONTROL+A is the one that matters**: it proves the
harness can see a detail when one exists, so the absence in the CLAIM arm is the defect and not the
instrument. **CONTROL-** proves the cause is the empty string and not the exception type. It calls
the real `PhaseRunner.abort`, `PhaseLedger.fail` and `PhaseRecord.as_payload` — no reimplementation.

### 2b. 🔴 The class the conveyor closed was not closed

The burn-down conveyor records the falsy-zero ledger as **five instances, question CLOSED**, on the
strength of CAL-P198-3's sweep of four modules coming back NEGATIVE with a passing control. Both
files above are inside that sweep. It missed this because **its notion of falsy was numeric**. This
is CAL-P198's own control-arm lesson recurring one session later, in the sharper form: *a control arm
validates the detector only against the class of hit the control encodes.* P198-3's control was
`P193-1`, a numeric `or None`; nothing in it could have surfaced a string.

**Do not re-open the numeric sweep — it is genuinely done. Re-open the falsy question for
non-numeric types**: empty string, empty list, empty dict, `datetime` never being falsy but `0`
timestamps being so.

---

## 3. The deploy census — reported NEGATIVE

The proximate cause of this beat's death is almost certainly a deploy: Heroku release **v3980
`Deploy b5c59f38` at 18:24:38Z**, ledger written **18:24:55.8Z — 17.8 s later**. That is the only
external event in the window and the beat stopped at no internal bound.

**But the general claim does not survive the population**, and that is the honest result:

`backend/scripts/cal_p199_deploy_kill_census.py` cross-references
`artifacts/cal-p118/beat-ring-full.json` (168 beats) against 400 Heroku releases.

| population | ends within 120 s of a release |
|---|--:|
| terminal ≠ complete | 3/97 = **3.1%** |
| terminal == complete (CONTROL−) | 1/71 = **1.4%** |
| separation | **+1.7 pp** |

And the decisive test:

> **Given a release landed mid-beat, the beat DIED 3 of 19 times = 16%. Sixteen of nineteen beats
> SURVIVED a mid-beat release.**

So **"a deploy kills the beat" is false as a general claim.** Of the three "killed" specimens one
terminated `complete`, so the true historical count is nearer 2 and is indistinguishable from
coincidence at n=168. The live beat is a member of a real but small minority.

**Two honest caveats, neither of which rescues the claim.** (i) Release density in the ring window
was **0.29/h** (49 releases / 168 h) against **2.0/h** in the last two hours — the ring may simply
not have been exposed. (ii) A 9.9-minute beat is not an outlier: 10 of 168 ring beats are shorter, 6
of them `cancelled`, so short-and-cancelled is ~6% of normal and cannot itself carry the inference.

**Verdict: the finding is the unrecorded exit (§2), not the deploy.** The deploy is this specimen's
likely cause; the defect is that the ledger cannot tell you that, or anything else, about why a beat
stopped. Had `detail` survived, this whole census would have been one `SELECT`.

---

## 4. Price of the fix: zero rebuild cost

The digest hashes `inspect.getsource` of four functions plus six constants, **all in
`precompute_calibration.py`** (CAL-P194's table). Both fix sites are in *different modules*:

| park | fix site | hashed? | reset? |
|---|---|---|---|
| `P199-1` | `calibration_main_build:580` + `calibration_phase_ledger:1360/1128` | no — different modules | **none** |

🔴 **This unblocks nothing.** Ruling 009 still freezes the module and D-G still freezes the deploy.
Only the price is known. It does **not** touch the group-key hazard — `category` is a data value the
digest cannot see at any line.

---

## 5. Session state

* Input fingerprint `e2040f90154fae876f0fb65f5abf74c3` — **unchanged, thirty-fourth session**,
  re-verified at session end.
* Published curve `generated_at 2026-08-31T04:37:36Z`, `availability: stale`, `temporary_excluded`
  and `temporary_by_cell` both absent. **Thirty-fourth unchanged session. Fully explained.**
* `served_units 0`, `served_at` absent, `outcome.published false` — **no publish.** Bank 50 → 55/128.
* Master moved a **third** consecutive session: `60c81cab` → `b5c59f38` (latency merge, CERT-683,
  response compression). `git diff --name-only` = `backend/app/main.py` +
  `backend/tests/test_response_compression_1636.py`. **Zero calibration files — ALL-CLEAR.**
* Branch `program/calibration-190-…` is **twelve** commits ahead, not eleven. Count it yourself.
* CAL-P185's datagolf discriminator re-run after nine skipped sessions: **0 rows — quiescent.**

## 6. Files

| file | what |
|---|---|
| `backend/scripts/cal_p199_cancelled_detail_erasure.py` | the finding, 3 control arms, exit 0 |
| `backend/scripts/cal_p199_deploy_kill_census.py` | the census, 2 control arms + window sweep, exit 0 |
| `artifacts/cal-p199/cancelled-detail-erasure.txt` | its output |
| `artifacts/cal-p199/deploy-kill-census.txt` | its output |
| `artifacts/cal-p199/live-ledger-18-24-55Z.json` | the beat this was found on |
| `artifacts/cal-p199/heroku-releases-400.json` | 400 releases, 2026-07-24 → 2026-09-01, reusable |
