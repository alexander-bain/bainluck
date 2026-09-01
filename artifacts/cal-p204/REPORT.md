# CAL-P204 — the one cursor outcome that stands the beat down is the one the ledger cannot name

**Session:** CAL-P204, 2026-09-01 ~12:5x–13:2x PT
**Branch:** `program/calibration-190-the-rebuild-survives-a-deploy`
**Harness:** `artifacts/cal-p204/refuse_branch_records_nothing.py` — four arms across two axes,
exit 0, runs from any cwd (proved from `/tmp`).
**Touched in `app/`:** nothing. Read-only session.

---

## 0. Opening state (all four checks run first, as ITEM 3 requires)

| check | result |
|---|---|
| inbox `ls` | only `974-…running` — no new Fable directive. Re-checked at close. |
| fingerprint predictor | `e2040f90154fae876f0fb65f5abf74c3` — **unchanged, 39th session** |
| `origin/master` | `b5c59f38…` — **empty diff, FIFTH quiet session.** `985` honoured |
| `/api/calibration` `generated_at` | **`2026-08-31T04:37:36Z` ⇒ still 08-31 ⇒ FREEZE ON** |
| `TOP-PRODUCT-DEFECTS.md` | unchanged: item 12 DIAGNOSED (not built), item 21 lane1's. **No calibration build item open** |
| DataGolf discriminator (P185's) | **0 rows — quiescent** (P185–P189, P199, P202–P204) |

**Both bank-bearing rows (ITEM 1b), read together — CONVERGED:**

| row | updated_at | generation | bank | terminal |
|---|---|---|---|---|
| `…:staged_futures` | 19:24:13.320Z | `1788290163654` | **60** | `partial` |
| `…:phase_ledger` | 19:38:34.407Z | `1788290163654` | copy `60` | `cancelled` |

Generations AGREE ⇒ converged, ledger copy current. Bank **60/128**, unmoved since P203.
Live ledger's cursor keys: `staged:cursor_resume: 0`, `staged:cursor_reason:resumable: 0` — the
current beat resumed cleanly.

---

## 1. The finding

`_run_staged_futures` (`precompute_calibration.py:4476`) decodes the durable cursor into one of
**four** actions and records which one fired:

```python
4573    if action == REFUSE:
4574        # Another beat holds an unexpired lease on this generation. …
4577        logger.info("calibration staged futures: cursor held by another run — standing down")
4578        return None                                  # <-- returns HERE
4579    runner.ledger.record_stage(f"staged:cursor_{action}", 0)
4585    runner.ledger.record_stage(f"staged:cursor_reason:{reason}", 0)
```

**The record statement is six lines below the return.** `staged:cursor_refuse` and
`staged:cursor_reason:lease_held` are therefore **strings that can never be written**. Of the four
documented actions, the three benign-to-recoverable ones (`fresh`, `resume`, `invalidate`) are
recordable; the one where the beat **does no work at all** is not.

This is the module's own stated doctrine, inverted. `_record_staged_rate`'s docstring, same file
family: *"Every branch below either records a number or records WHY it could not (ruling 075, second
clause). None of them records nothing."* And `decode_staged_cursor_detailed`'s docstring, on why
CAL-P024 added the reason token at all: *"the action alone is not diagnostic."* For REFUSE, not even
the action is written.

### The consequence chain (each step verified in source)

1. Decode → `REFUSE`, when `held_by and held_by != owner and lease_expires_at > now`
   (`calibration_staged_futures.py:1649-1655`).
2. `return None` — **nothing recorded**.
3. Caller (`:4995`) turns `None` into
   `raise StagedFuturesIncomplete("futures generation incomplete — units banked, nothing published")`
   — **the identical exception and message a productive-but-partial beat raises.**
4. Terminal → `save_phase_ledger` → `_record_staged_convergence` (`calibration_main_build.py:1688`),
   which reads the cursor row **with no owner and no generation predicate** — only `read.ok`,
   `envelope is not None`, `isinstance(payload, dict)`, `isinstance(committed, list)` — and publishes
   **nine gauges** off it: `units_banked`, `units_drifted`, `units_drift_checkable`,
   `units_drift_uncheckable`, `served_units`, `served_drifted`, `served_drift_uncheckable`,
   `served_at`, `units_partition`.
5. So the stood-down beat's ledger reports **the other owner's bank** as its own state, with
   `units_this_beat: 0`, terminal `partial`, and no cursor key.

**Net: a beat that did nothing because another run held the lease is indistinguishable, in the
ledger, from a beat that ran and simply banked nothing new.**

### Why the read in step 4 is the asymmetry, not just a shortcut

The *same module* reads the *same row* 100 lines earlier and validates six predicates —
schema, task, population version, input fingerprint, malformed shape, and foreign-owner lease —
routing to `FRESH` / `INVALIDATE` / `REFUSE` / `RESUME` (`calibration_main_build.py:1283-1305` →
`decode_staged_cursor_detailed`). The convergence reader validates none of them.
`STATE_MAX_AGE_S = 14 * 86400` — a **14-day** age bound, so age filters nothing either.

---

## 2. The arms

Per the five-part control discipline (P199–P203), all four pass; detector reported TRUSTWORTHY.

| arm | axis | result |
|---|---|---|
| **A** positive control | can the detector emit RECORDABLE? | **PASS** — `FRESH, INVALIDATE, RESUME` |
| **B** **counterfactual** | delete the early return on the AST, re-run | **PASS** — flips to **4/4** recordable, `REFUSE` flipped |
| **C** sibling control | the *other* `action == REFUSE` handler in the same file | **PASS** — `_precompute_calibration_main:6991` **does** write durably (`save_phase_ledger`, `terminal: "overlap_refused"`, `checkpoint_action`) |
| **D** empirical | 168 consecutive production beats | `cursor_resume` 156/168; `fresh` 0; `invalidate` 0; `refuse` **0** |

**ARM B is the one that matters** and it is the arm P203 said to add: it fails if the status quo
would also have been right. **ARM C is the strongest evidence** — the codebase demonstrably knows
this event must be recorded durably, and does so at the checkpoint level, twelve hundred lines away,
for the identical concept ("another owner holds the lease").

**POPULATION + COVERAGE:** the population is *the cursor decode actions*, enumerated **from source**
(`calibration_phase_ledger.py:208-211`), not hardcoded. **4 of 4 classified = 100.0%.** The noun in
the marker ("action") is the noun the instrument enumerated (Q11).

---

## 3. What this does NOT show — the honest limits

* 🔴 **No wrong published number.** Same as P202/P203: the publication gate is
  `is_complete(cursor, chunks)` and reads the CURSOR, not the ledger. **OPERATOR-visible only.**
* 🔴 **I cannot say how often this has fired — and neither can anyone else.** `staged:cursor_refuse`
  is 0/168, but `fresh` and `invalidate` are *also* 0/168, so absence is not evidence (ARM D's own
  note). By construction the marker cannot appear. **The frequency of this event is unmeasurable
  from the rail built to measure it.** That is the finding, not a gap in it.
* 🟢 **Reachability under the normal schedule is LOW, and I measured it rather than assuming.**
  `precompute_calibration_main` is hourly at :15. Over the 168-beat ring: median inter-beat gap
  **60.1 min**, minimum **44.1 min**, and **0 of 167 gaps fall under the 31-minute lease**
  (`LEASE_S = HARD_LIMIT_MS/1000 + 300 = 1,860 s`). Schedule alone does not reach it.
* ⚠️ **It is reachable when an EXTRA beat starts inside a prior beat's lease** — an attended manual
  relaunch, which is exactly what `985` has Alex doing. `owner = f"{socket.gethostname()}:{os.getpid()}"`
  (`calibration_main_build.py:280`), so **every Heroku release guarantees a different owner**, and the
  killed run's lease survives up to 31 min past its last unit commit.
* 🔴 **A tempting hypothesis, CHECKED AND NOT SUPPORTABLE.** P203 recorded Alex's stated relaunch at
  18:51Z but the generation that actually started at 19:16:03Z — an unexplained 25-minute gap that a
  silent REFUSE would fit exactly. **I could not test it.** `phase_ledger` is a single last-write-wins
  row; the 19:38:34Z write destroyed whatever was there. **Neither confirmed nor rejected — do not
  repeat it as though it were established.**
* ⚠️ The `logger.info` at :4577 does emit. Logs are not the durable rail, are retention-bounded, and
  `heroku logs` is EPERM-blocked in this sandbox.
* 🔴 **Do not build a fix.** Ruling 134 / clause 6 — this is a fold's call. The change is ~2 lines
  (record before returning, or hoist the record above the guard) and it touches
  `precompute_calibration.py`, which is **frozen under ruling 009** and under a **hard deploy freeze**
  under `985`. Parked, not queued.

---

## 4. Secondary observations (filed, low severity)

* **`P204-2`** — the beat gauge sampler's `OPERATIONAL_GAUGES`
  (`calibration_beat_gauge_sampler.py:168-177`) allowlists **`staged:cursor_resume` only**. Even
  `invalidate` and `fresh`, which *are* recordable, are never captured into a banked beat row, so an
  analyst replaying banked rows sees "resumed / didn't resume" and cannot tell which non-resume
  outcome occurred. ⚠️ Mitigating: that tuple's own docstring says it is "the sampler's own
  editorial choice … forgetting one costs a column in a report, not the replayability of the row."
  **Self-described as best-effort — one line, not a headline.**
* **`P204-3`** — `_record_staged_convergence`'s read carries **no owner and no generation predicate**
  while its sibling 100 lines up validates six. Distinct from `P203-1`: that one was about the
  ledger row's *write cadence*; this is about the *absence of an ownership predicate on the read*.
  Note the docstring does say "where the staged build actually IS", so a global reading is arguably
  intended — the defect is that the ledger stamps its own `generation` at top level beside it, so
  ITEM 1b's own query invites reading a possibly-foreign bank as this generation's.

---

## 5. Question-bank result

**Q12** ("does this instruction name where the value is PRODUCED, or where it is COPIED TO?") pointed
at ITEM 2's vocabulary table. Grepping all 41 `record_gauge` call sites answered the literal question
quickly — nine of the ledger's `staged:*` gauges fan out from **one** durable read in
`_record_staged_convergence`, so they share P203-1's cadence exactly and none is independently stale.
**That is a NEGATIVE result for Q12's literal form: no second `units_banked`.**

The find came from the adjacent question the grep exposed — *which branches reach the recorder at
all* — i.e. **Q7** ("the docstring and the guard disagree — which does the CALLER believe?"), now
**five for five**. ⚠️ Worth recording honestly: **Q12 as posed by P203 returned nothing**; the
twenty-third consecutive find came from a question the conveyor did not name.

---

## 6. Filed

`P204-1` (headline), `P204-2`, `P204-3` → `.claude/handoff/PARKED-MEASUREMENTS.md`. On #2052.
**All OPERATOR-visible; none belongs on `TOP-PRODUCT-DEFECTS.md`.** No `YOUR-TURN.md` edit (lanes
may not). Nothing merged, nothing deployed, nothing in `app/` or `frontend/` touched.

---

## 7. 🔴 DIRECTIVE `975` — ANSWERED BY MEASUREMENT: THE BATCH IS ALREADY BUILT, MERGED **AND DEPLOYED**

`975-freeze-parallel-branch-work.md` landed **mid-session** (the second `ls` caught it — P196/P199
precedent) and asks this lane to *"BUILD the ruled freeze-lift batch on its branch: D5 dedup + D21 +
D22 + D13 per-market + D12 crypto tuple, as ONE deploy-unit branch … rebase … stage the cert."*

**I did not build it, because it already shipped.** Verified, not assumed:

| D item (ruling, `RULINGS-BATCH-2026-08-30.md`) | evidence it is on master | on prod? |
|---|---|---|
| **D5** one-join dedup | CERT-504 **GREEN** @ `bd76c953` — **ancestor of master**. `deduped` CTE live at `precompute_calibration.py:2777-2788` | ✅ |
| **D21** reader fix (absent key → named refusal) | same subject `bd76c953`; CERT-485/497/502 blocked it, **CERT-504 GREEN** closed it | ✅ |
| **D22** diagnostics stops blocking publish | CERT-485: *"D22, D13 and D12 are clean on their reviewed deltas"*; `PHASE_DIAGNOSTICS` in `RESUMABLE_PHASES` (`calibration_phase_ledger.py:89`) | ✅ |
| **D12** crypto cell | `("kalshi", "crypto")` exclusion tuple at `precompute_calibration.py:1362`; commit `6be79cd0` *"rank 6 was already done"* | ✅ |
| **D13 per-market** (Alex's ~2:15pm addendum) | CERT-514 **BLOCKED** `70518c0d`; **resolved** by `3432dd4f` *"a graded claim stopped waiting on its ungraded neighbour, because the refusal moved down a grain"*. Live: `:3321` carries the comment **"🔴 THERE IS NO `ungraded_lone_claims = 0` CONJUNCT"** beside `:3364 OR graded_lone_claims >= 1` | ✅ |

**Ancestry, run rather than inferred:** `bd76c953`, `7b401286`, `70518c0d`, `5a2b38a5`, `8258395c`
are **all `git merge-base --is-ancestor` TRUE against `origin/master`**. Only `4d8373c6` is not — and
it is CERT-638's superseded pre-rebase subject, replaced by `8258395c`, which *is* on master.

**And it is on PRODUCTION.** `heroku releases -a bainluck` → **v3980, `Deploy b5c59f38`, 11:24:38 PT**
— and `HEROKU_SLUG_COMMIT = b5c59f38fd1847ccb503f7ea2ad7f1f4a055c5d8`, **byte-identical to current
`origin/master`**. (That release is the 11:24 deploy `985` names as the one that killed the drain.)
This satisfies PROCESS-V2 clause 1 — *done = on production, checked once by the builder.*

**Unmerged-branch sweep** (memory: *"sweep unmerged BRANCHES on your issue"*): every
`origin/program/calibration-*` and calibration-adjacent ref carrying `backend/app`/`frontend`
changes is `calibration-94`, `-96`, `-99` — **all far older than the 119/155/158 batch lineage** and
none of them the freeze-lift work. `calibration-158` and `calibration-190` are test/docs only.
**No branch holds ruled-and-unbuilt freeze-lift code.**

### What I did about it (clause 7 — acted, did not ask)

* 🔴 **Did NOT build a duplicate branch.** Re-implementing merged, deployed code would create a
  second deploy-unit for work that already exists.
* 🔴 **Did NOT stage a cert.** There is no unmerged subject to grade; a cert against already-merged,
  already-deployed code is a false cert and would burn a lane4 slot. Author-never-certifies also
  applies.
* 🟢 **Did the check `975`'s real goal implies.** Its stated aim is *"when the curve publishes, this
  branch should be sitting GREEN and ready so the freeze-lift merge is minutes, not hours."* The
  measured answer is stronger than that: **the freeze-lift merge is a NO-OP — zero minutes.** Nothing
  is queued behind the freeze. What remains is not a build and not a merge: it is the drain
  (`run.6462`) completing a generation so the curve republishes.
* ⚠️ **This means `985`'s freeze currently gates nothing this lane owns.** Still honoured in full —
  I merged nothing, deployed nothing, and touched no `app/` file.

⚠️ **Limit of this claim.** I verified the five D items are *present on master and deployed*. I did
**not** re-verify each one behaves correctly in production — the curve has not republished since
`2026-08-31T04:37:36Z`, so their effect on the published payload is **not yet observable**. That is
the drain's job, and grading it is ITEM 3 step 3's pre-registered work, not something a build lane
should pre-empt.
