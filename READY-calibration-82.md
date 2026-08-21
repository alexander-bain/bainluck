# READY — program/calibration-82

status: ready_for_integration
branch: program/calibration-82
base: a13239f1        # master at rebase time; `git log --oneline a13239f1..HEAD` is the authority
head: 2c429334        # superseded by this re-stamp's own commit — see `head_is_this_file` below
queue: CAL-P085 (re-stamped by CAL-P086)
window: pid:32260-cal-p086   # re-stamp; the branch was built by pid:17386-cal-p085
date: 2026-08-21

head_is_this_file: |
  This token cannot contain its own SHA. The commit that re-stamps it is the branch tip.
  **`git log --oneline a13239f1..HEAD` is the authority**, always, and a reader who wants the
  head should take it from the ref, not from this file. The previous version of this token
  quoted `work_work_head_orig: fd0ff2ab...` as though it were current; that object is a
  PRE-REBASE commit **unreachable from every ref in the repo** (`git log --all` finds it zero
  times). It is named here only so the next reader does not go looking for it.

## ⚠️ WHY THIS TOKEN WAS RE-STAMPED (Fable addendum, CAL-P086)

The previous version misdescribed the branch it certifies, in the direction that flatters it.
Ruling 113 — *a merge offer is a branch with a green gate, not a file* — cuts both ways: the
file must describe the branch that exists, because the Integrator's risk call is made from it.

| field | was | is |
|---|---|---|
| `files_under_backend_app` | **1** — "a PURE module" | **2** — one pure module **and one grading task** |
| `rollback` | "Reverting cannot change a served byte" | **STRUCK — false.** See `rollback` below |
| `work_work_head_orig` | `fd0ff2ab` | unreachable pre-rebase object; removed |

Two earlier drifts (`commits: 2`, `files: 8`) were already corrected by the `2c429334` refresh
and are recorded here only so the correction history is one story rather than two.

commits: 8          # 4 substantive + 4 token commits (this update is the 4th token commit)
commits_substantive: 4
  b29edb44  whole-market fold        7 files
  ba7a6772  durability round 2       2 files
  973c304f  #2076 result             1 file  (artifact re-write)
  bb1cce05  gotcha 152               1 file  (docs/gotchas-reference.md — CAL-P086)
  # 1527abd9, 2c429334, e93ec165 and this one are READY-token commits: that file only.
files: 10           # UNCHANGED by CAL-P086 — gotchas-reference.md was already among the 10
files_under_backend_app: 2
  backend/app/utils/calibration_price_provenance.py   # PURE — verified: imports only
                                                      # __future__ + typing; no session, no
                                                      # I/O, no clock. Sole non-test consumer
                                                      # is backend/scripts/measure_price_provenance.py
  backend/app/tasks/repair_pm_never_graded.py         # ⚠️ A GRADING TASK THAT WRITES.
                                                      # Reachable from
                                                      # app/routes/admin_repairs.py:243 (census,
                                                      # read-only) and :267 (`pm-never-graded`,
                                                      # the WRITE half). See `rollback`.
migration_slot: none
beat_schedule_change: false   # VERIFIED: `tasks/__init__.py` is not in the branch diff, and
                              # `repair_pm_never_graded` appears nowhere in it. The task is
                              # ATTENDED-ONLY by its own module contract.
frontend_files: 0
ios_files: 0
precompute_calibration_py: UNTOUCHED — ruling 009 holds, the exception stays UNSPENT

stack_order: |
  ✅ **NONE — `-82` STANDS ALONE.** `-81` merged mid-window as `81187ae4` (master `a13239f1`,
  deployed), so the stack this token originally declared is gone. `-82` was REBASED onto
  `a13239f1`; one conflict, `docs/gotchas-reference.md` (the shared append region), resolved
  keep-both with gotcha 149 UNCHANGED — still the first free number counted in the merged tree.

gates: |
  ⚠️ **THE SUITE WAS RUN AT `973c304f`, NOT AT THIS HEAD.** Everything committed since is
  **docs or this token** — `bb1cce05` adds one line to `docs/gotchas-reference.md`, and the
  rest touch `READY-calibration-82.md` only. **Zero executable bytes have changed since the
  suite ran**, so the 18,632 below remains the truth about this branch's code; I am naming the
  commit rather than implying the tip.
  ✅ `gotcha_numbering` WAS re-run at `bb1cce05`, after the new entry: **3 passed, EXIT CODE 0.**

  full_backend_suite: 18632 passed / 0 failed / 95 skipped / 61 xfailed — PYTEST EXIT CODE 0
                      at 973c304f (729.43 s; redirected to a log, not piped — gotcha #54)
  p085_suite:         43 passed — EXIT CODE 0
  durability_p085:    17 passed — EXIT CODE 0 (all 17 RED before the fix)
  codex_53:           53 passed, UNCHANGED (durability_p081 + halt_p076 + base)
  p077_suite:         41 passed, unchanged — EXIT CODE 0
  gotcha_numbering:   3 passed — EXIT CODE 0 (re-run at bb1cce05 with gotcha 152 in place)
  ⚠️ gotcha_numbers:  this branch now carries TWO — **149** and **152**. 152 is NOT 150:
                      master's ceiling is 148, but `program/ux-103` and `program/ux-104`
                      already bank 150 AND 151 without claiming them in `RULING-CLAIMS.md`.
                      Swept every local + remote ref; 152/153/154 have holders_found = 0.
                      Recorded in the ledger so the next claimant's arithmetic is right.
  merge_tree:         git merge-tree --write-tree origin/master program/calibration-82
                      -> exit 0, 0 conflicts (re-run AFTER the rebase, against a13239f1)
  delta_reconciles:   CAL-P084's 17,821 no longer applies — the rebase moved the base 122
                      commits across four lanes. CAL-P085's two new test files collect
                      EXACTLY 60 (43 + 17), measured with --collect-only.

headline: |
  #2087 CLOSED-PENDING-CERT. The hindsight-exclusion headline now measures the WHOLE-MARKET
  policy ruling 103 actually authorises: **3.7226 pp -> 1.7422 pp**, 34,366 of 372,293 rows
  (9.231%), 49/49 cells, 0 unmeasured, 113 statement fingerprints, not sampled.
  **Granularity correction −0.0012 pp** — inside Fable's ±0.05 pp band, so Alex's existing
  re-consent covers it. Ruling 103 carries AMENDMENT 2; `C-APPLY-PRE-WHICHPRICE-R3` staged.
  R2's BLOCK was right AND the number survives it — and it was NOT small for the comparators
  (D +3.42 pp, B +0.21 pp), so "recompute the proposed policy" would have been the wrong repair.

rollback: |
  **NOT free, and the previous wording of this field was FALSE.** It read: *"the only
  backend/app file is a PURE module … Reverting cannot change a served byte."* Both halves
  were wrong. The second is the dangerous one, because a rollback field is read under time
  pressure by someone deciding whether they may revert without thinking.

  **The free half.** `git revert b29edb44` — pure module, operator-run script, two artifacts,
  ruling 103, one gotcha line. Nothing executable outside an operator's own shell. Genuinely free.

  **The half that is not free.** `git revert ba7a6772` touches
  `app/tasks/repair_pm_never_graded.py`, which writes `resolution_source='clob_never_graded'`
  and crowns outcomes, and is reachable from `POST /api/admin/repairs/pm-never-graded`
  (`app/routes/admin_repairs.py:267`; the endpoint is `_check_admin_secret`-gated at :416).

  What is TRUE, stated precisely, because it is the part the old sentence was groping for:
  **no user-facing byte moves either way.** The task is ATTENDED-ONLY by module contract
  (*"never wire this to a beat"*), `tasks/__init__.py` is untouched, and no user-serving route
  imports it. `/api/calibration` and every rendered surface are unaffected by this branch and
  by its revert.

  What reverting DOES do: **it re-opens the CAL-P081 hole.** `ba7a6772` makes `_save_obligation`
  and `_save_plan` after-read through `_load_obligation` / `_load_plan` — the readers a RETRY
  and the APPLY actually use — instead of trusting the publisher's acknowledgement. Codex proved
  the pre-change path reachable: a store-nothing publisher answering `superseded` let the REAL
  apply commit **4 UPDATEs, 4 commits, `success: true`, `obligation_persisted: true`** against an
  EMPTY store. A revert restores exactly that, silently.

  So: **if `ba7a6772` is reverted, the `pm-never-graded` apply must not be run until it is
  re-landed.** That is a rollback condition, not a footnote.

  Commands (`fd0ff2ab`, named by the old field, is unreachable from every ref — `git revert
  fd0ff2ab` will not do what its author meant):
    whole branch        `git revert --no-commit 973c304f ba7a6772 b29edb44`
    free half only      `git revert b29edb44`
    durability half     `git revert ba7a6772`   ⚠️ re-opens the CAL-P081 hole — see above

deploy_checks: |
  No migration, no beat entry, no route, no user-facing task. `population_version` unmoved and
  `precompute_calibration.py` untouched, so **`/api/calibration` must be UNCHANGED** after this
  deploy — if it changes, that is a finding about something else, not about `-82`.
  ⚠️ Post-deploy, `/api/calibration` 503s for 1–4 min after EVERY release and self-heals; that
  is the known window, not a regression. Take the check on a warm second pass.

second_item: |
  **Durability round 2** (Fable addendum) — C-APPLY-PRE-1912-R3-R2's BLOCK closed red-first.
  A census test asserts publisher-call count == after-read count (4 == 4), so the SIXTH call
  site fails a test instead of waiting for a cert. Restaged as
  `CODEX-PENDING-C-APPLY-PRE-1912-R3-R3.md`.
  🟢 **UNBLOCKED BY THE CAL-P086 DIRECTIVE (Alex, 2026-08-21):** the slot question is RULED —
  **WHICHPRICE-R3 first, R3-R3 immediately after**, both arming on the same merge. R3-R3 is to
  be staged into the slot the rotation frees. Clause 3b's Alex-authority is what sequences two
  approved release gates, so this no longer waits on an interactive answer.

2076_answered: |
  **1,350 s was consumed too.** `fold_duration_s 1351.95` / `db_rows 0` / terminal failed, on
  the now-live raised ceiling. 240 -> 241.18, 900 -> 901.96, 1350 -> 1351.95: the fold has never
  finished, only ever been cancelled. 1_350_000 ms is the ceiling of the task shape, so option 1
  is DEAD and option 2 was refuted from the plan (6 CTEs, all InitPlan-materialised, referenced
  2–8 times: 7 source chunks re-run all 6). #2076 is STRUCTURAL.
  🟢 **ACCEPTED BY ALEX (CAL-P086 directive):** the structural verdict stands and the structural
  repair is **PARKED AS A STAGED SUCCESSOR** with the query-plan evidence attached. **It does not
  gate the apply.** Parked on the board 2026-08-21 —
  `github.com/alexander-bain/bainluck/issues/2076#issuecomment-5374968309` carries the three-budget
  table, the per-CTE cost/reference table, the chunking refutation, and the caveat against sizing
  option 3 or 4 from planner cost (the model understates this fold by ≥1.57×, my own extrapolation
  by ≥2.35×). `in-progress` removed; **the card still wants the `Parked` column** — `claim_issue.py`
  has no such choice, so a human or the Integrator must move it.

owed: |
  R3's verdict AND R3-R3's; #2059's 15-cell / 481-row enumeration as an artifact; the #2076
  structural repair (parked successor, option 3 narrow-at-`market_info` vs option 4
  attack-`ranked_outcomes`, either needing a scoped 009 exception). Gate 5 unmoved — and now
  known to need a structural fix, not a number.
