# READY — program/calibration-82

status: ready_for_integration
branch: program/calibration-82
work_work_head_orig: fd0ff2ab2b212e966036387473280bacbbfecd4f   # the CAL-P085 commit — all 7 files
base: 57da34602e9c29f7bd3d3ea1a0fbb21b86a51577       # = program/calibration-81 head
# NOTE: this token was written before two later commits and before a REBASE, so the SHAs above
# are the post-rebase ones and this file is NOT the tip. `git log --oneline a13239f1..HEAD` is
# the authority — 5 commits (this token refresh is the 5th). Stated this way rather than quoting a SHA the token cannot contain.
queue: CAL-P085
window: pid:17386-cal-p085
date: 2026-08-21

stack_order: |
  ✅ **NONE — `-82` STANDS ALONE.** `-81` merged mid-window as `81187ae4` (master `a13239f1`,
  deployed), so the stack this token originally declared is gone. `-82` was REBASED onto
  `a13239f1`; one conflict, `docs/gotchas-reference.md` (the shared append region), resolved
  keep-both with gotcha 149 UNCHANGED — still the first free number counted in the merged tree.

commits: 5   # whole-market fold · READY token · durability round 2 · #2076 result · this refresh
files: 10
files_under_backend_app: 1   # app/utils/calibration_price_provenance.py — a PURE module
migration_slot: none
beat_schedule_change: false  # tasks/__init__.py untouched on -82; the beat entry is -81's
frontend_files: 0
ios_files: 0
precompute_calibration_py: UNTOUCHED — ruling 009 holds, the exception stays UNSPENT

gates:
  full_backend_suite: 18632 passed / 0 failed / 95 skipped / 61 xfailed — PYTEST EXIT CODE 0
                      at the FINAL head 973c304f (729.43 s; log truncated first, no pipe)
  delta_reconciles:   CAL-P084's 17,821 no longer applies — the rebase moved the base 122
                      commits across four lanes. CAL-P085's own two new files collect
                      EXACTLY 60 (43 + 17), measured with --collect-only.
  p085_suite:         43 passed — EXIT CODE 0
  durability_p085:    17 passed — EXIT CODE 0 (all 17 RED before the fix)
  codex_53:           53 passed, UNCHANGED (durability_p081 + halt_p076 + base)
  p077_suite:         41 passed, unchanged — EXIT CODE 0
  gotcha_numbering:   3 passed — EXIT CODE 0
  merge_tree:         git merge-tree --write-tree origin/master program/calibration-82
                      -> exit 0, 0 conflicts (re-run AFTER the rebase, against a13239f1)

headline: |
  #2087 CLOSED-PENDING-CERT. The hindsight-exclusion headline now measures the WHOLE-MARKET
  policy ruling 103 actually authorises: **3.7226 pp -> 1.7422 pp**, 34,366 of 372,293 rows
  (9.231%), 49/49 cells, 0 unmeasured, 113 statement fingerprints, not sampled.
  **Granularity correction −0.0012 pp** — inside Fable's ±0.05 pp band, so Alex's existing
  re-consent covers it. Ruling 103 carries AMENDMENT 2; `C-APPLY-PRE-WHICHPRICE-R3` staged.
  R2's BLOCK was right AND the number survives it — and it was NOT small for the comparators
  (D +3.42 pp, B +0.21 pp), so "recompute the proposed policy" would have been the wrong repair.

rollback: |
  `git revert fd0ff2ab`. Genuinely free: the only backend/app file is a PURE module (no session,
  no I/O, no clock) whose sole consumer is an operator-run script. Not a task, not a route, not
  on the beat schedule. Reverting cannot change a served byte.

deploy_checks: |
  None specific to -82. No migration, no beat entry, no route, no task. `population_version`
  unmoved and `precompute_calibration.py` untouched, so `/api/calibration` must be UNCHANGED
  after this deploy — if it changes, that is a finding about something else.

second_item: |
  **Durability round 2** (Fable addendum) — C-APPLY-PRE-1912-R3-R2's BLOCK closed red-first.
  `_save_obligation` and `_save_plan` now after-read through the readers a RETRY / the APPLY
  use. A census test asserts publisher-call count == after-read count (4 == 4), so the SIXTH
  call site fails a test instead of waiting for a cert. Restaged as
  `CODEX-PENDING-C-APPLY-PRE-1912-R3-R3.md` — **PENDING, not staged**: NEXT holds
  `C-APPLY-PRE-WHICHPRICE-R3` and README §3 clause 3b forbids overtaking a release gate
  without Alex. Both queues are release gates. One rotation frees the slot.

2076_answered: |
  **1,350 s was consumed too.** fold_duration_s 1351.95 / db_rows 0 / terminal failed, on the
  now-live raised ceiling. 240 -> 241.18, 900 -> 901.96, 1350 -> 1351.95: the fold has never
  finished, only ever been cancelled. 1_350_000 ms is the ceiling of the task shape, so
  option 1 is DEAD and option 2 was refuted from the plan. #2076 is now structural.

owed: |
  R3's verdict AND R3-R3's; #2059's 15-cell / 481-row enumeration as an artifact; a decision on
  #2076's option 3 (narrow at market_info) vs 4 (attack ranked_outcomes), either needing a
  scoped 009 exception. Gate 5 unmoved — and now known to need a structural fix, not a number.
