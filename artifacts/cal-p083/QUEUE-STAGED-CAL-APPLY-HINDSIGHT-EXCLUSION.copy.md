# Calibration Queue (STAGED, ATTENDED) — CAL-APPLY-HINDSIGHT-EXCLUSION

status: staged_gated   # NOT approved. Do not promote until §1's conjunction is CLOSED.
queue_id: "CAL-APPLY-HINDSIGHT-EXCLUSION"
staged: 2026-08-21 PT
staged_by: calibration lane, window `pid:59456-cal-p083`, on Fable's CAL-P083 directive item 3
  ("assemble the APPLY as its own attended queue item — exclusion CTE per the scoped 009
  exception GO file, exclusion-symmetry reconciliation in the same window, page renders
  accounted. Do not fold it into a tail.")
authority: ruling **103**; grant `GO-CAL-P078-HINDSIGHT-EXCLUSION-EXCEPTION.md` (ruling 009
  exception, addressee = calibration lane ONLY, ruling 033)
parent_issue: 1145
migration_slot: none
beat_schedule_change: false
attended: **YES — this queue is not runnable headless.** It moves the frozen file, wipes the
  rebuild bank, and its verification spans ~17 hours of degraded serving.

---

## 0. Why this is its own queue and not a tail

The apply is three coupled changes (a CTE, a symmetry reconciliation, and a page-render account)
whose blast radius is the published curve, and it invalidates every banked unit the moment it
deploys. A tail item shares a window's remaining attention with whatever came before it. This one
needs the whole window, and the deploy rider in §6 needs a window that is not racing anything.

---

## 1. THE GATE — a conjunction. One box open means NO APPLY.

The GO file names three. Fable's CAL-P083 directive adds the promotion as a fourth and fifth
independent reading. All five, current as of 2026-08-21 07:5x PDT:

1. ☐ **`C-APPLY-PRE-WHICHPRICE-R2` GREEN** on its four named attacks (pack §8.3, verbatim).
   GREEN on three of four is a BLOCK.
   **STATUS: NOT RUN.** It sits in `CODEX-NEXT.md`, `status: approved`, unconsumed. R1's verdict
   was **BLOCK** and it was upheld — R2 certifies the AMENDED premise, so its GREEN is not a
   formality.

   🔶 **AND IT IS STARVING, NOT BLOCKED — a distinction worth acting on.** It is SAFE:
   `CODEX-NEXT.md` is byte-for-byte unchanged since 2026-08-20 15:23, so CAL-P082's two-condition
   fix is holding across rotations. But lane4 step 4 promotes the NEXT slot only when
   `CODEX-QUEUE.md` reaches `done`, and Fable/Alex have been hand-staging directly INTO
   `CODEX-QUEUE.md`, which bypasses the promotion path entirely. `CODEX-QUEUE.md` rotated **twice
   inside CAL-P083's own window** (`C-SEN-2-R2` → `C-DELETE-RAIL-PRE-R2`), and WHICHPRICE-R2 was
   passed over both times. **It will not drain on its own.** Someone must hand-stage it into
   `CODEX-QUEUE.md`. The queue whose GREEN releases the 1.77 apply should probably not be the one
   waiting on an opportunistic drain.
2. ☑ **`program/calibration-74` DEPLOYED — VERIFIED ON PRODUCTION 2026-08-21, not on a merge SHA.**
   `GET /api/calibration` carries the `staged` block (`measured: true`, `staged_at`,
   `units_banked`, `units_drifted`, `frozen_over_drift`, `rebuild_units_*`), and
   `frontend/lib/calibrationStaleness.ts` is present. The page can describe its own inputs, so
   the apply is gradeable (#2007).
3. ☑ **`GO-CAL-P078-HINDSIGHT-EXCLUSION-EXCEPTION.md` exists.**
4. ☑ **THE PROMOTION HAPPENED AND IS QUOTED** — generation **`1787315424367`**,
   2026-08-21 12:30:24 UTC (05:30:24 PDT). Bound **100.0000pp → 0.5000pp**, the tight floor.
   Attribution measured: `served_at` 1787250149 → 1787315330.
   Evidence: `artifacts/cal-p083/ARTIFACT-CAL-P083-ITEM1-BOUND-DESCENT.json`.
5. ☐ **A GATE-0 TWIN VERDICT TAKEN INSIDE THE TROUGH.** See §2 — this is a NEW gate that the
   CAL-P083 measurement forces, and it is currently unmet.

---

## 2. ⚠️ THE BOUND IS A SAWTOOTH WITH A ONE-BEAT TROUGH — this constrains WHEN, not whether

CAL-P083 measured the bound across the promotion and two beats after it:

```
  11:36:17Z  100.0000pp   served drift 128/128
  12:30:24Z    0.5000pp   served drift   0/128   <- promotion, tight floor
  13:35:43Z   85.9375pp   served drift 110/128
  14:38:15Z  100.0000pp   served drift 128/128   <- fully re-saturated
```

110 of 128 served units drifted within ~65 minutes of promotion; all 128 within ~130. **So a
tight-bounded Gate 0 agreement verdict is only obtainable in the beat immediately following a
promotion — a window roughly one beat wide, recurring about once per 16 beats.**

Consequences this queue must respect:

* A Gate 0 twin run outside the trough returns a verdict bounded at ~86–100pp, which is not a
  meaningful agreement claim and must not be quoted as one.
## 2b. 🔴 THE GATE-0 TWIN RAIL IS BROKEN — MEASURED 2026-08-21, AND IT BLOCKS GATE 5

Trough timing is the second problem. The first is that the twin **cannot produce a verdict at
all.** A run enqueued 2026-08-21 13:57Z banked this artifact at 14:03:02Z:

```
  verdict            = unmeasurable
  terminal           = failed
  fold_duration_s    = 241.18        <- against timeout_ms = 240000
  db_rows            = 0
  db_cells           = 0
  unmeasurable_reason= QueryCanceledError: canceling statement due to statement timeout
```

**The DB-direct fold consumes its entire 240 s budget and is cancelled by the statement
timeout.** It did not fail early — it ran out. Same class as **#2052** (the 22.5-minute beat
cancelled on the `market_info` CTE); the twin folds that same population.

The worker's guards behaved correctly throughout: `db_rows <= 0` did NOT present as perfect
agreement, it went `unmeasurable` and banked `complete=False`. **The instrument was honest. It
just could not be heard** — see the endpoint defect below.

**Gate 5 cannot be met until the fold fits its budget.** Filed as **#2076** (P1, `needs-agent`),
cross-linked to #2052. It is on the critical path of the 1.77 apply. Options, none costed: raise
the fold's own `statement_timeout` above the 240 s worker budget (they are **not the same knob** —
the inner one binds first); narrow the fold to the cells actually compared; or fold incrementally
across beats the way the rebuild already stages its 128 units. Not an item this queue absorbs
silently.

⚠️ Note the compounding: the fold does not merely need to FINISH, it needs to finish **inside the
one-beat trough** described above. A 240 s fold in a ~60 min window is fine; a fold that needs an
unbounded retry loop is not.

### Endpoint defect found and FIXED in CAL-P083 (`backend/app/routes/admin_cohort.py`)

`GET /api/admin/calibration-twin/last` answered `{"measured": false, "reason":
"artifact_unreadable: malformed"}` over that 195 KB artifact. The chain:
`unmeasurable` → banked `complete=False` (correct — never serve a non-verdict as a verdict) →
the envelope reader types the row `malformed` → the endpoint returned the bare status and dropped
the body. **The one endpoint whose job is to explain a failed gate run reported the least
informative fact available about it** — gotcha #53's shape, inside the instrument written to
avoid it, which is how it survived three queues.

Fixed: an INCOMPLETE envelope's diagnosis is now recovered under `failed_run`, with
`envelope_error_class` naming why. A CHECKSUM-TORN or WRONG-VERSION envelope is still NOT mined —
bytes that fail their own checksum cannot describe themselves. `measured` stays `False` and
`verdict` is never lifted to the top level, so a timed-out fold cannot read as an agreement.
**This fix ships on `program/calibration-80` and must be DEPLOYED before this queue runs**, or
Item 0 below is unanswerable.

* **Item 0 of this queue is to run the twin and read a real diagnosis**, then fix the fold budget,
  then schedule the verdict run against the next promotion beat.

---

## 3. THE APPLY — exactly one CTE, nothing else moves

Per the GO file, inside `backend/app/tasks/precompute_calibration.py`'s
`_calibration_population_ctes`:

```
capture_class(fo, fm) = 'after_resolution'
    WHEN fm.resolution_date IS NOT NULL AND fo.opening_captured_at > fm.resolution_date
```

**Excluding WHOLE MARKETS, not legs.** `opening_captured_at` is per-outcome and `resolution_date`
is per-market, so the naive per-leg predicate splits a field and breaks sum-to-1. Measured: **101
mixed markets in 464,777 (0.0217%)**; they are excluded whole, winners and losers together.

Required properties, restated as acceptance criteria:

* **READ-SIDE ONLY.** No write to `is_winner`, `calibration_probability` or `opening_probability`
  (gotcha #21). Rows keep provenance and stop entering the curve.
* **Nothing else in the frozen file moves.** Not a refactor passing through, not a second
  predicate sharing the edit, not a comment reflow beyond the CTE's own block.
* **`population_version` BUMPED** (`precompute_calibration.py:109` — "bump when
  `_calibration_population_ctes` changes materially"). Current `q268`. The publish gate's ±5%
  population / 20% per-category drift guard must be told this drift is INTENTIONAL, exactly as
  Queue 299 did — otherwise the gate reads the apply as a collapse and blocks it.
* **`_main_input_fingerprint()` MOVES.** That is the expected consequence and the accepted cost.
  It is not a licence for a second cause to move it. Record the before/after fingerprint in the
  report (`b65faaacdc240b3b256934fcad528db1` is the value on master as of 2026-08-21).
* **REVERSIBLE IN ONE COMMIT.** State the revert SHA in the report BEFORE the apply merges.

---

## 4. EXCLUSION-SYMMETRY RECONCILIATION — same window, not a follow-up

The payload's `exclusion_symmetry` block currently documents a **residual asymmetry that this
apply must not silently widen**: Kalshi excludes never-traded outcomes in **all price bands**;
Polymarket excludes them only in the **0.45–0.55 placeholder band**, so `poly_never_traded_in_curve`
is still counted.

The hindsight exclusion is a THIRD exclusion landing on the same population. In the same window:

1. Re-run the exclusion-symmetry census AFTER the apply and reconcile it against the pre-apply
   figures. Both numbers in the report, side by side.
2. Assert the hindsight exclusion is **source-symmetric** — it keys on
   `resolution_date`/`opening_captured_at`, which are source-independent, so it MUST NOT fall
   disproportionately on one source. Measure it; do not argue it. A per-source split that
   surprises you is a finding, not a rounding error.
3. `exclusion_symmetry.note` must be UPDATED to name the new exclusion. A symmetry block that
   describes two of three exclusions is worse than none — it reads as complete.

Closing the poly never-traded asymmetry remains a **separate Alex-gated decision** and is NOT
authorized here.

---

## 5. PAGE RENDERS ACCOUNTED

The apply degrades `/api/calibration` for ~17 hours (§6). Every surface that reads it must be
accounted for BEFORE the deploy — named, and its degraded state described:

* `/calibration` (the page) — ECE metric, buckets, "Does Trading Activity Matter?" section.
* `frontend/lib/calibrationStaleness.ts` — the staleness copy the page renders from the `staged`
  block. **This is the surface that makes the degradation honest rather than broken**, and it is
  the reason gate 2 exists. Verify it renders the degraded state correctly, with a real payload,
  before the apply — not after.
* The iOS/macOS Calibration entry point (sidebar, per CLAUDE.md) — confirm it degrades to the
  same honest copy and does not render an empty or stale-but-confident curve.
* `calibration_coverage_census` — currently `status: unavailable`,
  `reason: census_disabled_pending_futures_phase_budget`. It is already honest-empty; confirm the
  apply does not flip it to a confident zero.
* Admin: `GET /api/admin/backfill-winners/status`, the cockpit calibration tile.

Acceptance: a rendered capture of `/calibration` in the degraded state, via the browser-audit
rail or local CDP. Not a description of one.

---

## 6. ⚠️ THE ACCEPTED COST IS ~3× WHAT THE GO FILE STATES — RE-PRICED, NOT RE-ARGUED

The GO file says the rebuild restarts from zero and the curve degrades **"~5-6 beats at the
measured rate"**. That estimate is stale. CAL-P083 measured a full cycle:

```
  108 units banked across 15 observed beats, 15.0 h wall
  units_this_beat: [7,5,8,8,11,8,7,9,10,7,7,6,7,9,6]   mean 7.67, min 5, max 11
  FROM ZERO at 7.67 u/beat -> 16.7 beats  (~17 h at the hourly cadence)
  range: ~12 h at the best observed rate, ~26 h at the worst
```

Plus one **missed beat** was observed inside that window (07:39:45Z → 09:33:09Z, no ~08:3x beat),
which the estimate above does not include.

**Alex accepted "a curve that is honestly degraded for six hours." The real exposure is ~17
hours, plausibly 26.** The trade's REASONING is unchanged and still looks right — 9.3% phantom
rows is wrong every hour it serves, and bounded honest degradation beats unbounded wrongness. But
the number he accepted was wrong by ~3×, and re-consenting to the corrected number is his call,
not this lane's. **Do not run this queue until Alex has seen ~17 h.**

### Deploy-window rider (from the GO file, unchanged and load-bearing)

After the deploy carrying this apply, **HOLD further deploys until one beat completes
uninterrupted.** The Integrator enforces it and states it in its report. A rebuild restarted by a
mid-beat deploy is a rebuild that never finishes — ruling 009's named failure arriving through
the door the exception opened. Note the teardown history: `last_failure_type` = `"SystemExit"` at
+16 s / +24 s / +35 s after releases, so a deploy landing mid-beat is the NORM, not the tail case.

---

## 7. What this queue does NOT authorize

* Any re-grade, any write to `is_winner`, any bulk reset (gotcha #21).
* Any change to the INGEST that created these rows (fix-forward, filed separately; it does
  nothing for the 35,976 rows already in the curve).
* Any second predicate, in this CTE or beside it, however obviously correct.
* Closing the Polymarket never-traded asymmetry.
* Any other lane touching `precompute_calibration.py`. Ruling 033.

---

## 8. Item order when this is promoted

0. Prove the Gate 0 twin rail writes an artifact at all (§2). If it does not, that is the queue's
   first finding and the apply waits.
1. Pre-apply capture: fingerprint, `population_version`, exclusion-symmetry census, per-source
   hindsight split, `/calibration` render.
2. The CTE + `population_version` bump + publish-gate intentional-drift declaration.
3. Focused gates, then full backend suite.
4. Report the revert SHA. THEN hand to the Integrator with the deploy rider quoted.
5. Post-deploy: watch one beat complete uninterrupted; then the ~17 h reconvergence, sampled with
   `scripts/sample_calibration_beats.py` + `scripts/grade_bound_descent.py`.
6. On the FIRST promotion after reconvergence: run the twin inside the trough. That is the
   apply's real verdict, and it arrives ~17 h after the deploy, not with it.
