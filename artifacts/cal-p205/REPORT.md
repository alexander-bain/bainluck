# CAL-P205 (#2052) — layer 1 is BUILT: the staged cursor keys off the emitted statement

**Session:** 2026-09-01, ~12:5x → ~14:0x PT. **Inbox:** `974` (conveyor, P203-staged) + 🔴 **`975`**
(Fable-5, 12:59 PT, found by the mandatory `ls`, unconsumed at session start).
**Branch:** `program/calibration-205-the-staged-cursor-keys-off-the-emitted-statement` off
`b5c59f38`. **Nothing merged. Nothing deployed. `985` honoured in full.**

---

## 0. THE ONE PARAGRAPH

`975` told this lane to build the ruled freeze-lift batch (D5 · D21 · D22 · D13-per-market · D12)
as one deploy-unit branch. **It is already built, merged AND deployed** — P204 measured that and
left the finding *uncommitted on one disk*; I rescued it (`64515d39`) and reproduced it
independently by a different instrument. So `975`'s literal payload is a no-op, and its standing
instruction — *"keep making full progress on branch while the drain runs"* — was applied to the work
that actually remains: **layer 1 of `artifacts/cal-p190/DESIGN-THE-REBUILD-SURVIVES-A-DEPLOY.md`,
which `920` rules ships FIRST as the rider on the next calibration ship.** It is built, on a clean
branch off current master, with 26 focused tests green and the wide fingerprint pinned unmoved.

---

## 1. 🔴 `975` IS ANSWERED BY MEASUREMENT — AND P204 HAD ALREADY ANSWERED IT

P204's `artifacts/cal-p204/REPORT.md` §7 was **modified but never committed**. Gotcha #52; the
conveyor's ITEM 4 warns about exactly this ("P190 rescued thirteen sessions' artifacts that existed
on one disk only"). Banked verbatim as `64515d39` on `program/calibration-190-…`, pushed.

P204's evidence: all five D-item cert subjects are ancestors of `origin/master`; Heroku **v3980 =
`Deploy b5c59f38`**, `HEROKU_SLUG_COMMIT` byte-identical to `origin/master`.

**CAL-P205 reproduced the conclusion by an instrument P204 did not use, and it is stronger for the
deployment half** — because a slug commit says what was *released*, not what the *running dyno is
executing*:

| step | measured |
|---|---|
| live `input_fingerprint`, written by the running production dyno at 19:38:34Z | `e2040f90154fae876f0fb65f5abf74c3` |
| `_main_input_fingerprint()` computed locally at master HEAD | `e2040f90154fae876f0fb65f5abf74c3` |
| every commit in the D-batch moves that digest | conveyor ITEM 3 / the digest's own docstring |

⇒ **production is running master's calibration code, batch included.**
🔴 **Counterfactual arm** (the P203 lesson — an arm that fails if the status quo would also have
been right): had the batch *not* been deployed, the dyno would be running pre-batch code and the two
digests would differ. They do not.
⚠️ **Honest limit:** the fingerprint covers ONE file. It proves `precompute_calibration.py` is at
master's version; the `master HEAD == the deployed release commit` fact is what carries the rest.

Content, not just ancestry (a merged commit can be reverted later — `dd2b22da` did exactly that to
ux-168 this week): **120/120 green** across `…crypto_cell_exclusion_d12`,
`…bookmaker_reader_refusal_d21`, `…soft_stage_d22`, `…lost_losses_12cal` run against master's app
code; D5's `deduped` CTE live; D13's repair visible at `precompute_calibration.py:3321` —
**"🔴 THERE IS NO `ungraded_lone_claims = 0` CONJUNCT"**, which is CERT-531's fix.

⚠️ **A pointer trap worth recording.** `origin/program/calibration-119` — the batch's own branch
name — now points at `8258395c`, which is **calibration-168's** head (merge commit `76b2b454` names
it as such). Reading that ref answers a question about a *different* branch. The batch's real head
is local `4d8373c6`, and it is NOT an ancestor of master; its content landed by other routes. Naive
ancestry on the branch NAME would have said "merged" for the wrong reason.

---

## 2. WHAT I BUILT — LAYER 1, AND ONLY LAYER 1

Design §3. `decode_staged_cursor` stops keying the STAGED CURSOR off four functions' source text and
keys it off **the statement its units actually ran**.

```python
def staged_unit_fingerprint() -> str:
    return input_fingerprint(
        "staged-unit/v1",
        CALIBRATION_POPULATION_VERSION,      # declaration, not in the statement
        REPRESENTATIVE_TIE_AUTHORITY,        # disclosure, not in the statement
        hashlib.md5(_main_futures_sql(frozen=True).encode()).hexdigest(),
    )
```

Three production files, **+134 / −10**:

* `precompute_calibration.py` — the new digest, and `_run_staged_futures` passes it as
  `input_fingerprint` with `runner.fingerprint` (the wide digest) as `legacy_input_fingerprint`;
* `calibration_staged_futures.py` — `REASON_LEGACY_FINGERPRINT_ACCEPTED` and the scoped acceptance;
* `calibration_main_build.py` — the parameter threaded through `load_staged_cursor`.

🔴 **THE WIDE DIGEST IS UNMOVED — `e2040f90154fae876f0fb65f5abf74c3`, verified after every edit.**
None of the four hashed functions was touched. This is the cutover's whole safety argument: the
deploy that ships layer 1 must not itself wipe the bank it exists to protect.

**Self-draining, by construction rather than by a cleanup task.** The decoder already returns
`input_fingerprint=expected_input_fingerprint` on the resume path, so an accepted legacy cursor is
re-stamped narrow by the next `save_staged_cursor`; the branch cannot fire twice for one cursor, and
can be deleted one generation later.

### 2.1 🔴 I re-derived the design's coverage table, and it was six values out of date

Design §3 measured **six** hand-added values. CAL-P168 has since added **six more** and nobody
re-derived the claim — and layer 1's correctness depends on it entirely: a hashed value the emitted
statement does *not* carry would be a **blind input** in the narrow digest, i.e. the exact hole the
change exists to close, reopened by the change itself.

Measured by mutation (mutate → re-emit → compare), all twelve:

| covered by the statement (10) | NOT covered (2) |
|---|---|
| `COVERAGE_CENSUS_ENABLED`, `NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS`, `MEX_NORMALIZE_THRESHOLD`, `PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS`, **+ the six CAL-P168 values** (`…HALF_SPIKE_EXACT_VALUE`, `PAIR_SUM_TOLERANCE`, `…NAME_PATTERN`, `…BAND_LO`, `…BAND_HI`, `…FORCED_DRIFT_MIN`) | `CALIBRATION_POPULATION_VERSION`, `REPRESENTATIVE_TIE_AUTHORITY` |

The two uncovered ones are hashed **by name** in the new digest. Result: **no blind input.** The
table is pinned in both directions, so a value that *starts* or *stops* shaping the SQL reds rather
than silently moving the coverage claim.

---

## 3. GATES

| gate | result |
|---|---|
| `test_staged_rebuild_survives_a_deploy.py` (4 CAL-P190 pins + 22 CAL-P205) | **26/26 green** |
| calibration/staged/fingerprint slice, `-k "calibration or staged or fingerprint"` | **3,025 passed / 23 skipped**, one failure found and fixed (below) |
| D-item suites vs master app code (§1) | **120/120** |
| `ruff check` on all four changed files | **clean** |
| wide-fingerprint pin | **`e2040f90…` unmoved** |
| full backend suite | see §3.2 |

⚠️ **`black --check` fails on all three production files — and it fails on `origin/master` too.**
Neither `black` nor `ruff` appears in `.github/workflows/ci.yml`; black is **not** a gate here.
Running it would reformat whole files (memory: *black reformats the WHOLE file*) and could
**reformat a hashed function and move the fingerprint**. Deliberately not run.

**The one real failure, and it was a genuine catch.**
`tests/evals/test_calibration_fingerprint_derived_map.py::test_generated_map_matches_real_source`
went red: the frozen map records, per fingerprint input, **which functions use it**. Adding
`staged_unit_fingerprint` legitimately moved two rows — `CALIBRATION_POPULATION_VERSION` and
`REPRESENTATIVE_TIE_AUTHORITY` each gained `staged_unit_fingerprint` in `used_in`. I diffed the map
semantically *before* regenerating (no inputs added, none removed, no coverage class changed — only
`used_in` and `source_sha256`), then regenerated via
`python3 -m scripts.evals.calibration_fingerprint_derived_map`. **6/6 green after.** Regenerating a
fixture without first proving *what* moved is how a real regression gets laundered into a diff.

### 3.2 Full backend suite — GREEN

Raw output banked in `full-suite.txt` beside this report, with the `PYTEST EXIT CODE` line captured
per gotcha #124 (never pipe a gate; read the exit code's VALUE).

| run | result | exit |
|---|---|---|
| `tests/ --ignore=tests/integration` | **23,917 passed**, 21 skipped, 61 xfailed — 7m11s | **0** |
| `tests/integration` | **1,715 passed**, 137 skipped — 13m21s | **0** |
| **combined** | **25,632 passed / 0 failed**, 158 skipped, 61 xfailed | — |

`grep -cE '^(FAILED|ERROR)'` over both logs = **0**.

⚠️ **Why it is split, stated because a split gate invites suspicion.** `tests/integration` is
I/O-bound on this box: a single `tests/` run sat at 10% after 20 minutes at ~1% CPU (another lane
held a concurrent full pytest run and a `tsc --noEmit` census, load ~6.8). Run apart, the two halves
complete in 7 and 13 minutes. **The split changes which processes the tests run in, not which tests
run** — the union is the same collection `tests/` would have collected, and the integration half is
the slow part that a combined run was already reaching last.

---

## 4. STATE FOR THE NEXT SESSION

* **Freeze `985`: STILL ON.** `/api/calibration` `generated_at` = `2026-08-31T04:37:36Z`,
  `availability: stale`. The date is the signal — **not** `beats_to_publish` (P198-1, P203-3), not
  `served_drifted` (P196-1).
* **Master: `b5c59f38`, held still for a FIFTH session.** Empty diff. Run it yourself anyway.
* **Fingerprint: `e2040f90154fae876f0fb65f5abf74c3`** — thirty-ninth session unchanged, re-verified
  at session end.
* **The drain is MOVING and the two-row read (ITEM 1b) is what shows it:**

  | time | generation | bank | ledger copy |
  |---|---|---|---|
  | 19:38:34Z | `1788290163654` | 60 | 60 |
  | **20:23:41Z** | **`1788293786268`** | **65** | 65 (written 20:38:56Z) |

  **+5 units/beat, ~61 min/beat, converged at 65/128.** 63 units to go ⇒ **~12–13 more beats**. Both
  rows agreed at both samples; no in-flight beat was hidden this session.
* **P185's discriminator: 0 rows** (datagolf non-golf). Quiescent — P185–P189, P199, P202–P205.
* **WIP = 2** (`calibration-190` artifacts/tests, `calibration-205` the ship). At the PROCESS-V2
  clause-2 limit. **Do not open a third.**

---

## 5. WHAT I DID NOT DO

* **Did not merge or deploy anything.** `985` forbids the master merge; branch pushes trigger no
  Heroku release.
* **Did not run `black`** — §3.
* **Did not build layers 2 or 3.** `920`/the conveyor rule layer 1 ONLY. Layer 2 (pinned SQL per
  generation) and layer 3 (additive census column) stay unbuilt and unqueued.
* **Did not touch `YOUR-TURN.md`** — lanes may not.
* **Did not add to `TOP-PRODUCT-DEFECTS.md`** — build lanes do not add items. Re-read it this
  session: item 12 (DIAGNOSED, not built) and item 21 (lane1's) remain the only calibration entries;
  **no calibration-lane build item is open.**
* **Did not answer P202's successor question** (does a stale `bucket_idx` move a published bucket).
  Measurement lane, ruling 134.

---

## 6. PRE-REGISTERED, AND THIS IS THE ONE TO WATCH

Design §6 falsifier **#2**: *"the cutover costs zero banked units. Falsified by a single
`REASON_INPUT_FINGERPRINT` on the beat immediately after the layer-1 deploy."*

**On the first beat after this merges, read `payload->'stage_counts'` for
`staged:cursor_reason:*`:**

* `staged:cursor_reason:legacy_fingerprint_accepted` **exactly once**, then
  `…:resumable` thereafter ⇒ **the cutover worked**;
* `staged:cursor_reason:input_fingerprint_changed` ⇒ **falsified**, and it cost the bank —
  the one outcome this change exists to prevent.

⚠️ **Falsifier #1 (~1 wipe absorbed per 4–5 calibration-source deploys) cannot be graded for weeks**
and must not be reported as confirmed by a green cert. ⚠️ And per `P199-3`, a deploy kills a beat
only **16%** of the time and costs the in-flight unit (~5 min), not the bank — **size this ship off
that number, not off the slogan.**
