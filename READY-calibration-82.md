# READY — program/calibration-82

status: ready_for_integration
branch: program/calibration-82
work_head: fd0ff2ab2b212e966036387473280bacbbfecd4f   # the CAL-P085 commit — all 7 files
base: 57da34602e9c29f7bd3d3ea1a0fbb21b86a51577       # = program/calibration-81 head
# NOTE: the branch TIP is the commit that adds this token, one above `work_head`. Stated this
# way rather than quoting a SHA the token cannot contain: a self-referential head is either
# wrong or stale the moment it is written. `git log --oneline base..tip` is 2 commits.
queue: CAL-P085
window: pid:17386-cal-p085
date: 2026-08-21

stack_order: |
  🔗 **-81 FIRST, THEN -82.** `-81` is UNMERGED (3 commits on origin/master `dee32eee`);
  `-82` contains `-81` entire. `-81` also carries the 1_350_000 ms twin ceiling that #2076's
  next measurement is blocked on, so merging it is what unblocks the follow-up.

commits: 2   # the CAL-P085 commit + this token
files: 8   # 7 in the work commit + this token
files_under_backend_app: 1   # app/utils/calibration_price_provenance.py — a PURE module
migration_slot: none
beat_schedule_change: false  # tasks/__init__.py untouched on -82; the beat entry is -81's
frontend_files: 0
ios_files: 0
precompute_calibration_py: UNTOUCHED — ruling 009 holds, the exception stays UNSPENT

gates:
  full_backend_suite: 17864 passed / 0 failed / 66 skipped / 3 xfailed — PYTEST EXIT CODE 0
                      (run twice: 693.86 s, 696.95 s; log truncated first, no pipe)
  delta_reconciles:   CAL-P084's 17,821 + 43 new = 17,864 exactly
  p085_suite:         43 passed — EXIT CODE 0
  p077_suite:         41 passed, unchanged — EXIT CODE 0
  gotcha_numbering:   3 passed — EXIT CODE 0
  merge_tree:         git merge-tree --write-tree origin/master program/calibration-82
                      -> exit 0, 0 conflicts (against dee32eee)

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

owed: |
  R3's verdict (Gate B is PENDING, not GREEN); the 1,350 s twin run once -81 deploys (#2076);
  #2059's full 15-cell / 481-row enumeration as an artifact; Gate 5 unmoved.
