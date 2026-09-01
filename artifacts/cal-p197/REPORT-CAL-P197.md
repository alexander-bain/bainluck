# CAL-P197 — CAL-P109's fix was built, documented and tested, and never wired to the line it fixed

**Session:** 2026-09-01, ~10:57–11:2x am PT. Lane: calibration (build). Branch:
`program/calibration-190-the-rebuild-survives-a-deploy`. **Nothing shipped, nothing merged, nothing
deployed, no source file edited.** D-G's stated default **(a) = freeze** was acted on.

---

## 0. One paragraph

**Nothing changed in production. One park, and it is the sharpest one in this run so far because it
is not a gauge-semantics subtlety — it is a fix that was never connected.** CAL-P109 (#2045)
diagnosed that the build's failure log printed `completed_required` — *the phases that FINISHED* —
under the label `"in phase group"`, so a beat that died in `sports` accused `futures` by name and
sent two investigations to the wrong budget. The fix built the right accessor,
`PhaseLedger.failed_phase`, gave it a 21-line docstring narrating the incident, and guarded it with
a test class literally named `TestTheFailureLogNamesTheRightPhase`. **The log line was never
changed.** `precompute_calibration.py:7019` still passes `list(runner.ledger.completed_required)`.
`failed_phase` has **zero references anywhere** — not in another module, not in its own module, not
in any emitted payload; of 45 public members of the ledger module it is the **only** one with no
consumer at all. And on the **live stuck beat**, `completed_required` is empty, so the line renders
`in phase group []` — the degenerate form of the same bug, naming nobody, on the exact rebuild that
has been under investigation for thirty-one sessions, while the ledger has held `'futures'` the
whole time.

---

## 1. What was checked before any of that (the standing job)

| check | result |
|---|---|
| Inbox `ls` | `967-burndown-conveyor.md.running` is this file. **No `968` collision.** `980` already consumed. |
| PROCESS-V2 | Read. Clause 2: this lane holds **ONE** unmerged branch — within limit. Clause 3: branch **not** self-merge eligible (no cert ever staged, P190–P197) **and** `960` D-G names it. Clause 8 obeyed below. |
| `TOP-PRODUCT-DEFECTS.md` (clause 8) | Read from `/Users/bain/bainluck/.claude/handoff/` (**not** repo root — worktree/CWD trap). Only calibration lines are **item 12** (`[calibration/lane1]`, DIAGNOSED) and **item 21** (lane1's). **No calibration-lane build item is open.** |
| Input fingerprint | `e2040f90154fae876f0fb65f5abf74c3` — **unchanged, thirty-second session.** Re-verified at session end after an import-heavy probe. |
| `origin/master` | 🔴 **MOVED**, `bcabbf2e` → **`9fc73a59`**. One commit: `Revert "Merge program/ux-174-…(CERT-676)"`. 6 files, **zero calibration files**. `git diff --name-only bcabbf2e origin/master \| grep -i calib` ⇒ empty, exit 1. **ALL-CLEAR for this lane.** |
| Phase ledger | `updated_at 2026-09-01T17:31:46.517193Z` — **the same row P196 read. The beat did not move.** `units_banked 50`/128, `units_completed_this_beat 5`, `units_cancelled 2`, `beats_to_publish 3`, `served_units 0`, `served_at` absent, `terminal cancelled`. |
| Published curve | Unchanged. No publish to grade ⇒ ITEM 3 step 3 not entered; P185 discriminator not re-run (directive: run it before grading a publish, not hourly). |
| Board work | Ranks 1/2/3/6 all built, merged, deployed. **Nothing both ruled and unbuilt.** |

So: an idle build board under a standing freeze ⇒ ITEM 3 step 5, re-read.

---

## 2. Which question was aimed, and where it landed

The directive's **oldest unrun item** was *"which of the 24 top-level ledger keys has NO reader?"*,
with the warning that `unit_costs`, `carried`, `completed_required`, `checkpoint_action`,
`population_version` "are quoted by nobody in fifteen directives."

**That phrasing is not the question.** "Quoted by no directive" is a fact about the directives;
`unit_costs` and `population_version` both have many code readers. Run against **code** instead, and
widened from the 24 payload keys to every public member of the ledger module, it lands immediately.

It is simultaneously a hit for two live questions in the bank:

* **Q1 — "what, exactly, does this guard compare, and what is therefore NOT in it?"** → **8 for 8.**
  The guard compares `ledger.failed_phase` against an expected phase name. What is *not* in it: the
  logger call. **New reach: previous instances were guards over tests, runtime paths and a pure
  utility. This one is a guard whose NAME is the claim, over a producer, while the consumer it is
  named for goes untested.**
* **Q7 — "the docstring and the guard disagree; which does the CALLER believe?"** → **3 for 3, with
  a twist: there is no caller at all.** The docstring is addressed to a consumer that was never
  written.

---

## 3. `P197-1` — the finding

### 3.1 The log line is unchanged

`backend/app/tasks/precompute_calibration.py:7018-7021`:

```python
logger.error(
    "calibration main build ended %s after %dms in phase group %s: %s",
    status, runner.elapsed_ms(), list(runner.ledger.completed_required), exc,
)
```

`"in phase group"` occurs **exactly once** in `backend/app`. Its argument is
`completed_required` — byte-for-byte the construct CAL-P109 diagnosed.

### 3.2 The correct accessor exists and is dead

`backend/app/utils/calibration_phase_ledger.py:1391-1413`. Its docstring is the incident report:

> *"The build's own failure log read `"ended timeout after 1111181ms in phase group ['futures']"` —
> and the list it printed there was `completed_required`, i.e. the phases that FINISHED. … Two
> separate investigations of #2045 opened on the futures budget because of it."*

**Reference census (PROOF 1, claims A and E):**

* Zero references in `backend/app` outside its own def span.
* Zero references inside its own module outside its own body.
* Emitted in **no** payload — not `phase_ledger_row`, not any `as_payload`, and it is not one of the
  24 top-level ledger keys (`completed_required` **is**; `failed_phase` is not).
* Of **45** public members of the ledger module, **exactly one** has no consumer anywhere:
  `PhaseLedger.failed_phase`.

That last point is what makes it decisive rather than suggestive. Five other members have no
*cross-module* reader — `phase_feasibility`, `feasible_phases`, `unit_projection`, `declared_ms`,
`slack_target` — but every one of them is consumed **in-module**, feeding `as_payload` or a sibling
predicate (`phase_feasibility` at lines 545 and 578; `feasible_phases` at 710; `unit_projection` at
675; `declared_ms` at 692/699; `slack_target` at 698). They are internal machinery, not dead.
`failed_phase` is the only true orphan.

### 3.3 The guard is named for the consumer and tests only the producer

`backend/tests/test_calibration_elastic_budget_p109.py:303-342`,
`class TestTheFailureLogNamesTheRightPhase`. Its own docstring restates the log-line bug. Its two
tests then assert `ledger.failed_phase == PHASE_SPORTS` and `ledger.failed_phase is None`.

The class never references `"in phase group"`, never imports `precompute_calibration`, and never
uses `caplog`. **The failure log does not name the right phase; the class asserting that it does has
been green the whole time.**

### 3.4 Live: the degenerate case, on the beat everyone is watching

Production ledger, captured this session to `live-ledger-phases.json`
(`updated_at 2026-09-01T17:31:46.517193Z`, `terminal cancelled`, fingerprint
`e2040f90…`):

| phase | status | duration |
|---|---|--:|
| `futures` | **cancelled** | 1,005,585 ms |
| `sports` | pending | 0 |
| `diagnostics` | pending | 0 |
| `aggregate` | pending | 0 |
| `serialize_gate_publish` | pending | 0 |

Nothing completed, so `completed_required` is **empty**. Replayed through the real `PhaseLedger`
(PROOF 2), the production format string renders:

```
calibration main build ended cancelled after 1005585ms in phase group []: StagedFuturesIncomplete(...)
```

**`in phase group []`.** It accuses nobody. `ledger.failed_phase` on the same ledger returns
`'futures'`.

This is strictly worse than the CAL-P109 specimen, which at least printed *a* name (the wrong one).
An operator reading today's line learns nothing about where 1,005 seconds went — on the rebuild that
has been the subject of thirty-one consecutive sessions.

⚠️ **Honest scope limit.** This lane already knows from other evidence that `futures` is the phase
that dies, so **the bad log line did not cause the current investigation to go wrong.** The claim is
that the diagnostic surface is empty and the fix for it was built and left unconnected — not that
anyone was actually misled this month.

### 3.5 Price: zero rebuild cost

The fix site is inside `_precompute_calibration_main` (lines 6936-7150), which is **not** one of the
four functions the input fingerprint hashes (`compute_calibration_payload`,
`_calibration_population_ctes`, `_virtual_market_ctes`, `_main_futures_sql` — none contains line
7019). Consistent with P194's cost correction: **changing it moves no fingerprint and needs no
resetting deploy.**

🔴 **This unblocks nothing.** Ruling 009 still freezes the module and D-G still freezes the deploy.
Only the price is established.

### 3.6 The shape of the fix, for whoever eventually folds it

Not built, not proposed for this lane. Recorded so the park is actionable:

* Pass `runner.ledger.failed_phase` to the log line, and relabel — `"in phase group %s"` is the
  wrong noun for a single phase name.
* Keep `completed_required` in the line if wanted, under its own honest label.
* Handle `failed_phase is None` explicitly: the docstring is emphatic that a run which died between
  phases has no failing phase and *"naming the nearest one anyway is how the original line came to
  be wrong."*
* Add `failed_phase` to the emitted ledger payload — today the only way to recover the dying phase
  from the durable row is to read the per-phase `phases` records and filter on status by hand, which
  is what this session did.
* Extend the guard so it asserts on the **rendered log line**, not the accessor.

---

## 4. What was NOT done, and why

* **Nothing merged.** Branch is not self-merge eligible under PROCESS-V2 clause 3 (no cert ever
  staged for it, P190–P197) and `960` D-G names it explicitly. Author-never-certifies stands.
* **Nothing deployed, no `app/` or `frontend/` edit.** D-G default (a).
* **No fix built** for `P197-1`. It sits in a ruling-009-frozen module, and under ruling 134 the
  call is a fold's.
* **No board item added.** Build lanes do not add to `TOP-PRODUCT-DEFECTS.md`.
* **P185 discriminator not re-run** — no publish to grade. **Eighth** consecutive session skipping
  it; still no scheduled trigger fired.
* **No new Alex-ask**, no `YOUR-TURN.md` edit (PROCESS-V2 clause 7).

---

## 5. Reproduction

Both run from any cwd and bootstrap the repo themselves; both exited **0** when run from `/tmp`.

```
python3 artifacts/cal-p197/proof_1_failed_phase_has_no_reader.py
python3 artifacts/cal-p197/proof_2_the_live_beat_logs_an_empty_list.py
```

`proof_2` touches no database — it replays `live-ledger-phases.json` (captured this session) through
the real `PhaseLedger`.

---

## 6. Files

| file | what |
|---|---|
| `REPORT-CAL-P197.md` | this |
| `proof_1_failed_phase_has_no_reader.py` | static: 5 claim groups, exit 0 |
| `proof_2_the_live_beat_logs_an_empty_list.py` | behavioural replay of the live beat, exit 0 |
| `live-ledger-phases.json` | production ledger phase records, `updated_at 17:31:46.517193Z` |
