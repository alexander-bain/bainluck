# READY — program/calibration-83

status: ready_for_integration
branch: program/calibration-83
base: 95d2b53a        # `program/calibration-82`'s head — this branch STACKS on it
master_at_build: a13239f1
queue: CAL-P086A
window: pid:54109-cal-p086a
date: 2026-08-21

head_is_this_file: |
  This token cannot contain its own SHA; the commit that writes it is the branch tip.
  **`git log --oneline 95d2b53a..HEAD` is the authority** — take the head from the ref,
  never from this file (the `-82` token's own re-stamp lesson).

## ⚠️ STACK ORDER — MERGE `-82` FIRST

    origin/master a13239f1
      └── program/calibration-82  @ 95d2b53a   (CAL-P085/P086, READY-calibration-82.md)
            └── program/calibration-83 @ HEAD  (CAL-P086A — THIS BRANCH)

Per PROGRAM-LANES invariant 2 as amended 2026-08-07 (*a lane never waits for integration*).
`-83` was branched from `-82`'s unmerged head, so its `origin/master...HEAD` diff CONTAINS
`-82`'s 10 files. **That is expected, not a scope leak.** CAL-P086A's own change set is the
8 files listed below, all in `95d2b53a..HEAD`.

A bounce of `-82` pauses `-83`'s merge and nothing else. If `-82` is merged first, `-83`
fast-forwards cleanly: `git merge-tree --write-tree origin/master HEAD` → **exit 0, zero
conflicts**, measured this window.

commits: 4 (+1 for this token)
  59f98924  item 1 — Gamma cursor advances after the work    2 files
  d3d730a8  item 2 — winner-proof gate on resolved-writes    4 files
  708b75d6  item 3 — CLOB never_graded writer DESIGN SKETCH  1 file
  da1762f7  bank gotcha 153                                  1 file

files: 8
files_under_backend_app: 4
  backend/app/utils/resolved_write_gate.py    # NEW, PURE — imports only __future__,
                                              # dataclasses, datetime. No session, no I/O.
  backend/app/tasks/backfill_winners.py       # cursor decision + completion ledger
  backend/app/tasks/futures.py                # _mark_resolved_impl records its reason
  backend/app/tasks/polymarket.py             # _sync_polymarket_resolved_status, per-row CASE
tests: 2 new files (test_gamma_cursor_after_work_p086a.py,
                    test_resolved_write_winner_proof_p086a.py)
docs: docs/gotchas-reference.md (gotcha 153),
      docs/clob-never-graded-forward-writer-sketch.md (NEW — design only)

migration_slot: none          # explicit. No Alembic revision. `market_metadata` is an
                              # existing JSONB column; the gate writes into it with `||`.
beat_schedule_change: false   # explicit. No task added, removed or rescheduled. The item-3
                              # sketch NAMES a future beat entry and does not create one.
frontend: 0 files
ios: 0 files
production_access: NONE       # code-only cycle; zero credentialed calls, zero taint spent.
apply_staging_touched: NO     # PROGRAM-CALIBRATION-QUEUE.md's CAL-P086 apply spec is
                              # byte-untouched; the claim block is a pure insertion above it.

## Gates run at this head

    tests/test_gamma_cursor_after_work_p086a.py        11 passed   EXIT 0
    tests/test_resolved_write_winner_proof_p086a.py    19 passed   EXIT 0
    codex's named regression set                      289 passed   EXIT 0
      (test_backfill_winners, test_poly_gamma_condition_id_lookup,
       test_wimbledon_both_winner_167, test_backfill_winners_poly_api_deadline,
       test_clob_never_graded_cohort, test_pm_market_ownership, test_clob_resolve)
    -k "polymarket or mark_resolved or resolved_status or futures or
        backfill_winners or clob or winner"          2203 passed, 4 skipped   EXIT 0
    tests/test_gotcha_numbering.py                      3 passed   EXIT 0
    tests/test_startup.py                               4 passed   EXIT 0
    FULL BACKEND SUITE     18,662 passed, 95 skipped, 61 xfailed, 0 FAILED   EXIT 0
                           (748.32 s; run at the final head)
    git merge-tree --write-tree origin/master HEAD               EXIT 0, 0 conflicts

Exit codes read for their VALUE, not merely for non-zero (gotcha #54's amendment): one run
returned **4** — a pytest usage error from the wrong cwd, i.e. a gate that never ran — and was
re-run rather than recorded.

## rollback

**Reverting IS safe and DOES change behaviour — say both.**

- `da1762f7` (gotcha 153) and `708b75d6` (sketch) are docs; reverting changes no served byte.
- `59f98924` (cursor) reverting restores the pre-advance, i.e. re-opens the skip. Safe
  mechanically, and it puts back the defect.
- `d3d730a8` (gate) reverting stops the `resolution_gate` stamp being written. Rows already
  stamped keep their stamp — `||` is additive and nothing reads the key yet, so there is no
  consumer to strand. **No data migration is needed in either direction.**

The gate deliberately does NOT change which rows become `resolved`; it changes what is
recorded alongside. Resolved-row COUNTS should be unchanged post-deploy — see the report's
expected deploy checks, which name that as the falsifier.

## What this branch does NOT claim

- It does not drain the 305,660-market winner gap. It stops two of the mechanisms that grow it.
- Item 3 is a **sketch**: no task, no beat, no licence.
- Codex's stronger [P0] fix-sketch ("stop the generic clock task resolving prediction-market
  sources") is **NOT implemented** — flagged for Alex in the report as a ruling, not a repair.
