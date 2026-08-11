# CALIBRATION EXIT EXAM

**Alex's ruling, 2026-08-09.** The calibration slot rotates to Discover when all seven items
below are green **with linked proof**. Alex reads this document in one sitting; his pass is the
rotation trigger. The ruling itself is banked in `docs/PRODUCT-BRAIN.md` §*THE CALIBRATION EXIT
EXAM*.

**This document is the deliverable.** A cycle that ships code and moves no item here has not
moved the lane toward rotation. Every item states what proof it needs *before* the work starts,
so no cycle can finish and then discover its evidence was unobtainable.

---

## Scoreboard

| # | Item | Status | Blocked on |
|---|---|---|---|
| 1 | Ruling 9 shipped; published count reflects volume-proven trading, both figures named | 🛑 **WALKED TO EXHAUSTION 2026-08-10 (CAL-P030) — PREMISE-BROKEN.** 381 windows, 3,275,813 rows, complete. **N must not be published: at density ≥ 10 every threshold scores BELOW the base rate** (best lift anywhere +4.0%); the overlap population is 88–96% already-traded, and polymarket has *zero* negatives. Ruling 011's tier 2 has no measured basis | **an Alex ruling** — drop tier 2, keep it as declared-unvalidated, or publish volume-proven-only (25.19%) |
| 2 | Trading-activity section led by matched-bucket comparison | 🟢 **PASSED 2026-08-10 (CAL-P030)** — merged at INT-031, deployed at `f6a40849`, and **photographed in production**: browser-audit run [`31431286342`](https://github.com/alexander-bain/bainluck/actions/runs/31431286342), manifest `result: pass`, `observed_frontend_sha` = the audited commit | — |
| 3 | Cricket + entertainment diagnosed to fix / exclusion / "genuinely bad" | 🟡 **Cricket DIAGNOSED** 2026-08-09 (confirms this document's own hypothesis). **Entertainment PARTLY diagnosed — corrected by CAL-P032:** the 0.42x single-quote lift (6.58% vs a 15.76% kalshi baseline) refutes the *single-quote-only* mechanism ONLY. **The settlement-timing rival is UNKNOWN, not refuted** — density says how many quotes, never when; adjudicating timing needs a settlement timestamp the schema does not carry | cricket: the publish (bump). entertainment: **timing is unobtainable without new capture** — it is an Alex scoping call, not pending work |
| 4 | Source graph redesigned — per-source panels | 🟢 **PASSED 2026-08-10 (CAL-P030)** — merged at INT-031, deployed at `f6a40849`, and **photographed in production**: five per-source panels on a shared 0–100 axis, each labelled n · % of curve · ECE, same run [`31431286342`](https://github.com/alexander-bain/bainluck/actions/runs/31431286342) | — |
| 5 | Native calibration surface consistent with web | 🟢 **PASSED 2026-08-09 (CAL-P026)** — rendered on both, every headline figure identical, both banner the staleness | — |
| 6 | Monitoring proven by drill — watchdog + sentinel guards observed firing | 🟢 **WATCHDOG HALF PASSED 2026-08-09** — observed firing, issue #1604 | sentinel half is plumbing #1548 |
| 7 | Backfill recovery progressing vs 786K recoverable; capture-floor re-measure ~Aug 15 | 🟡 **BASELINE ESTABLISHED 2026-08-09** — 797,871 recoverable, measured to exhaustion | a second dated measurement; ~Aug 15 |

**Four items are green** (2, 4, 5, and 6's watchdog half) — up from two, because INT-031 merged
CAL-P025/26/27 and CAL-P030 photographed the result. Item 7 has its first datapoint and needs a
second, dated ~Aug 15. Item **3 is diagnosed on its cricket half**; its entertainment timing rival is
UNKNOWN and unobtainable without new capture (see the CAL-P032 correction below).

## 🛑 THE BUILD COULD NEVER HAVE PUBLISHED — a banked unit did not survive its own round trip (CAL-P033, 2026-08-11)

**Five items on this scoreboard wait on "the publish". Every cycle since CAL-P016 has forecast it
from the unit count, and CAL-P032 corrected that to "the unit count, then a gate". Both are
downstream of something neither looked at: the completion path itself raises, and always would
have.**

`advance()` banked the driver's `Row` objects as they came back from the chunk statement. Inside the
beat that produced them that works — a `Row` is attribute-access and the merge reads it happily. But
the cursor is persisted through `durable_state.canonical_json`, which is
`json.dumps(..., default=str)`. A `Row` is not JSON-encodable, so `default=str` stringified it, and
every banked row reached Postgres as its `repr()`. Read straight off the live cursor:

    "(0, 'kalshi', 'baseball', False, False, 14, 0, Decimal('0.03071428571428571429'), ...)"

The next beat reads that back as a `str`. `decode_staged_cursor` still vouched for those units —
`list[str]` is a list, which is all its resumability filter asked — so the cursor reported
`RESUME` / `resumable` and the units counted toward the 128.

**Proven end to end, no DB, deterministic** (now `test_a_banked_unit_survives_the_durable_round_trip`):

| step | result |
|---|---|
| unit banked THIS beat → merge | ✅ `n = 14` |
| same cursor → `canonical_json` → back | resume verdict `RESUME` / `resumable` |
| resumed row type | **`str`** |
| resumed unit → merge | 🛑 **`TypeError: cannot read columns off a str`** |

Finalization is the only place those rows are touched again, and finalization needs **all 128**
units. **A beat banks ~19, so every completed build necessarily contains resumed units** — the
failure had nowhere to surface, and the completion path has therefore never run. Not once since
2026-08-02.

**Why ~8,000 backend tests missed it.** Every test hands rows from `advance()` to
`merge_futures_rows` in one process, and the multi-beat convergence test round-trips through
`as_payload()` — a **dict**, which keeps the `Row` objects alive. The destruction happens inside
`json.dumps`. **The round trip was the untested edge and it is the only edge production takes.**

**Fixed in CAL-P033**, in the unfrozen pure module: rows are encoded on the way IN, so a unit banked
this beat and a unit resumed from disk are the same type. The bug was two representations, not a
wrong one. A pre-encoding cursor is refused whole under its own reason token (`unencoded_units`) —
the banked units carry no column names and are unrecoverable, and they were worth nothing, because
the build they were feeding could not have completed.

### ⚠️ This does NOT make the page publish, and here is what is still in front of it

1. **One reset, by design.** This module is not covered by `_main_input_fingerprint`, so the guard —
   not the fingerprint — is what discards the old cursor. The walk restarts at 0.
2. **CAL-P032's publish gate is still there**, unchanged and still ~80% likely to refuse the
   candidate. It is now reachable, which it was not before.
3. **The capacity wall below is NOT fixed by this queue.**

## ✅ THE RETAINED STRUCTURE SHRANK — the cursor now banks a running total (CAL-P034, 2026-08-11)

CAL-P033 (below) handed the capacity wall forward with two exits: **shrink the retained structure**,
or move `worker-heavy` off a 512 MB Standard-1X. The second is a cost call and is Alex's. **The
first turned out to be much wider than it looked, and it is entirely inside the unfrozen pure
module.**

**Measured off the LIVE cursor at 91/128 units** (`calibration:main:staged_futures`,
`2026-08-11T03:36:23Z`) — not projected:

<!-- The first column deliberately reads "N units", not a bare "N". A bare digit
     matches the scoreboard's own row shape `| N | ` and this table would then be
     counted as five extra scoreboard rows — the false positive
     test_exit_exam_keeps_a_scoreboard_row_per_item already warns about, and which
     this section tripped on its first draft. -->

| units banked | rows retained | distinct group keys | compaction |
|---|---|---|---|
| 1 unit | 469 | 469 | 1.0x |
| 5 units | 2,364 | 866 | 2.7x |
| 10 units | 4,825 | 1,063 | 4.5x |
| 20 units | 9,899 | 1,239 | 8.0x |
| 40 units | 19,498 | 1,363 | 14.3x |
| 60 units | 29,446 | 1,507 | 19.5x |
| **91 units** | **44,272** | **1,586** | **27.9x** |

**Rows grow linearly; groups saturate.** Every unit re-states the same ~470 price bands, because a
bucket is a price band and not a question, and the merge's only act is to sum them. Total banked
bytes at 91 units = **10,622,807** → **116.7 KB/unit**, confirming CAL-P033's 118 KB/unit
independently and by a different method.

**Nothing downstream ever wanted the rows.** Their only consumer is `collect_unit_results` →
`merge_futures_rows`, which folds them immediately. The cursor was holding ~62,300 rows so that
finalization could turn them into ~1,650 — and dying before it got there.

`advance()` now folds instead of banking. On production's shape at 128 units:

| | old | folded | |
|---|---|---|---|
| cursor bytes | 18,753,197 | **134,191** | **139.8x** |
| retained rows | 62,208 | **1,200** | |
| `json.dumps` across a full walk | ~1,210 MB | **~9 MB** | the cursor is re-serialised after EVERY unit |

⚠️ **This does not turn the SLO green and does not claim to.** CAL-P032's publish gate is unchanged
and still ~80% likely to refuse the candidate. It removes the dominant *growing* term in the
retained structure; the 505 MB peak has other contributors this window did not measure, and **the
finalize spike remains unmeasured** — still CAL-P033's unowned item.

⚠️ **One reset, by design.** A pre-fold cursor is refused whole under its own token
`unfolded_units`, kept distinct from CAL-P033's `unencoded_units`. If the stack deploys together —
it is one stack — production sees `unencoded_units` once and `unfolded_units` never.

## ✅ THE WALL IS THE ROSTER, NOT THE CURSOR — the deploy ran the experiment (CAL-P035, 2026-08-11)

Three queues treated the retained cursor as the capacity wall. **Deploying CAL-P033+P034 settled it,
and the answer is no.** Both readings are beat-final, same gauge, same dyno, either side of the
deploy of `cd84f690`:

| beat | cursor bytes | units | bytes/unit | `rss:peak_mb` | `rss:at:read:futures_generation` |
|---|---|---|---|---|---|
| pre-P034, 04:15Z | 12,987,375 | 109 | 119,150 | 493 | 423 |
| post-P034, 11:15Z | 135,843 | 72 | **1,887** | **507** | 407 |

**The cursor shrank 95.6x and the peak got 14 MB WORSE.** CAL-P034 works exactly as designed — 1,887
B/unit against 119,150 confirms the fold, and 119,150 B/unit is a third independent confirmation of
CAL-P033's 118 KB and CAL-P034's 116.7 KB. **The fix is sound; the target was wrong.**

**Where the memory is, measured rather than inferred:** `rss:at:read:futures_generation` = **407 MB
of a 507 MB peak**, and that gauge is sampled at the stage boundary *after the roster read and before
`load_staged_cursor` is called*. **~80% of the peak is resident before the cursor exists.** No cursor
change can move it.

The roster is **669,383 rows** (`EXPLAIN ANALYZE` actual; the planner says 356,292 — out by 1.9x),
materialised by `.all()` into `list[Row]` and held live for the whole ~23-minute beat, although it is
dead about fifteen lines after it is read, once `gen_digest`, `chunks` and `assignment` are derived.

**The fix does not wipe the cursor**, which is what makes it unlike every other fix this lane has
found blocked. Releasing the roster lives in `_run_staged_futures`, which is **not** among
`_main_input_fingerprint`'s four hashed roots (`compute_calibration_payload`,
`_calibration_population_ctes`, `_virtual_market_ctes`, `_main_futures_sql`), so it does not move the
digest and cannot invalidate a banked unit. It is blocked **only** by ruling 009 → Alex escalation.

### ✅ Correction — beat lifetime does NOT decay with cursor size

The section below (CAL-P033) reads the two short beats as evidence that `SystemExit` arrives sooner
as the cursor grows. **Refuted.** The last ten futures-phase durations span the largest cursor this
lane ever had (13 MB) and the smallest (136 KB):

    1378744, 667348, 623476, 1370945, 1379170, 664501, 1377034, 1359253, 1373900, 1377558

Full-length beats on both sides of a 95.6x cursor change. The two short beats were something else.
Two queues have now forecast from this; it should stop here.

### ❌ A lead raised and REFUTED in the same window — the dead CTE tail

Recorded because it looks exactly like a finding. `_futures_generation_sql` selects only from
`virtual_market`, and PostgreSQL's CTE pruning is **non-transitive** (a *dead* referrer still counts),
so `ranked_outcomes` and `normalized` — 900,614 rows each — stay in the plan. Full plans at **Total
Cost 8,317,057** against **657,255** for the same statement truncated at `virtual_market`: 12.7x, for
byte-identical output. It reads as ~11 s/beat of waste.

**It is not waste.** `EXPLAIN ANALYZE` settles it in one column:

    CTE market_info           est=  333,221   act=669,383   loops=1
    CTE market_result_shape   est=3,296,652   act=      0   loops=0     <-- planned, NEVER RUN
    Planning Time 3.283 ms

PostgreSQL plans a dead CTE and never executes it; nothing scans it, so it costs planning only, and
planning is 3 ms. The docstring's *conclusion* ("costs nothing") is correct; only its mechanism
("planned away") is loose. **A detector and CI ratchet for this were built and deleted unshipped** —
they worked, and would have encoded a false premise into CI forever. **Do not rebuild them.**

> **The rule, because it cost an hour:** a plan-cost delta between two statements is **not** a runtime
> delta until `act`/`loops` say the nodes ran. `Total Cost` sums nodes that never execute.

## 🟡 THE COMPLETION PATH RUNS AT FULL SCALE — and its allocation is bounded (CAL-P035, 2026-08-11; REPAIRED after the C276 block)

CAL-P033 and CAL-P034 both left this open — *"finalization materialises every banked row at once
(~70K rows) and nobody has measured that spike; it is the one step no beat has ever reached"* — and
CAL-P034 noted that shrinking the cursor makes it *reachable*, hence more urgent.

**The completion path has now been executed at full production scale**, offline and deterministic,
over a cursor in the real post-P034 folded shape (`tests/test_calibration_completion_path_p035.py`).
It completes cleanly, and its output matches an **independently derived oracle** — expected group
keys and additive/census totals computed from the generated rows by arithmetic in the test file,
sharing no code with the merge. Every one of the 128 steps is persisted through canonical JSON and
read back through the **production** `decode_staged_cursor_detailed`.

| walk | rows in | distinct groups | cursor bytes | finalize Python allocation |
|---|---|---|---|---|
| 1 unit | 470 | 470 | 31,599 | 993,308 |
| 32 units | 15,040 | **1,650** | 116,181 | 3,564,952 |
| 128 units | 60,160 | **1,650** | 128,726 | **3,615,384** |

**What this establishes:** finalization's cost is **bounded by the group space, not the unit count**
(3.56 MB at 32 units vs 3.62 MB at 128 — +1.6% for 4x the units). That scaling property is the claim,
and it holds.

⚠️ **What it does NOT establish, and an earlier version of this section wrongly did.** These figures
are `tracemalloc`: **incremental Python allocation requested inside the traced block.** They are not
process RSS. They cannot see the interpreter, driver result buffers, allocator arenas or any C-level
allocation — and the worker's 512 MB limit is enforced against RSS. **The previous text read "~3.6 MB
= 0.7% of the 512 MB dyno … not a risk and the lane can stop carrying it", which compares a
Python-allocation figure against an RSS budget. That conclusion is withdrawn.** RSS closure on
finalization can come from exactly one place: an `rss:at:staged:finalize` reading on the first
production beat that completes. No beat has produced one since 2026-08-02.

**The harness validates itself against production:** its synthetic cursor at 128 units is **128,726
B** against the live cursor's **135,843 B**, a 6% difference — so the fixture reproduces the real
shape rather than a convenient one.

**Repair provenance (C276 block at `9afce07e`).** Three defects, all real: the oracle ran the same
finalizer on both sides, so a drop-first-output defect cancelled and the assertion still passed; the
"round trip" re-inflated the cursor by hand and never touched the production decoder, so deleting it
changed nothing observable; and the memory conclusion above. Re-proven by mutation — **7 caught**,
including the two the block named by name (merge drops its first output row; round trip removed) and
two that mutate the **decoder** to show it is genuinely on the path. One mutant is recorded as
SURVIVED and out-of-class: rewriting the test's own transition log to fake its evidence defeats any
test that keeps bookkeeping, and it mutates the test rather than the code.

## 🛑 THE BEATS ARE DYING SOONER AS THE CURSOR GROWS — measured 2026-08-11 (CAL-P033) — ⚠️ REFUTED, see the CAL-P035 correction above

CAL-P024c shipped the RSS instrument and named its own unmet done-bar: *"a measured peak RSS with
margin and a complete build succeeding on the dyno. Neither is reachable from this window — both
need this instrument deployed and one beat to run."* **It is deployed and the beats have run. The
measurement it is owed:**

| measured | value |
|---|---|
| `worker-heavy` dyno | **Standard-1X = 512 MB**, `--concurrency=2`, `--max-memory-per-child=200000` (≈195 MB) |
| worker peak RSS, 00:15Z beat | **505 MB** (`rss:at:read:futures_unit` 467, `rss:at:read:futures_generation` 409) |
| staged cursor size | **7.13 MB** JSON @ 63 units · **8.41 MB** @ 71 → **118 KB per unit**, linear |
| projected at 128 units | **≈ 15.2 MB**, re-serialised in FULL after **every** unit |

**One child of this task peaks at 505 MB on a 512 MB dyno running two children, against a per-child
cap it exceeds by 2.6x.** And the beat-final trend is monotone in the wrong direction:

| beat (all beat-final) | banked | drift | net | duration | terminal |
|---|---|---|---|---|---|
| 22:15Z | 36 | 0 | +17 | — | cancelled |
| 23:15Z | 55 | 16 | +19 | 1378 s | cancelled |
| 00:15Z | 63 | 33 | +8 | **668 s** | **SystemExit** |
| 01:15Z | 71 | 55 | +8 | **625 s** | **SystemExit** |

**Two corrections to CAL-P032's finding 2, both from source and arithmetic:**

1. **Drift is a measurement, not a destroyer.** Post-CAL-P028 `retain_planned_units` keeps a unit iff
   its key is in the plan, and the key is `(buckets, index)` — every slot of a 128-way partition is
   planned every beat, so **nothing is ever dropped**. `roster_drift` only counts. Drift rising with
   the banked count is what a pure measurement of "how many held units has the roster moved under"
   does; it has no effect on the net rate. CAL-P032 read it as destruction and derived a decay
   mechanism from it.
2. **The rate is not decaying — beat LIFETIME is.** Per unit of *beat time* the build is constant at
   **~72–80 s/unit** across every beat above (`read:futures_unit` 577 s / 8 units = 72 s). The +19 and
   the +8 are the same rate through a 1378 s window and a 625 s one. What changed is that the last two
   beats died at 10.4 and 11.1 minutes — a new terminal (`SystemExit`, exit `-241`) that CAL-P032
   recorded as unexplained, arriving **sooner as the retained cursor grows**.

**This queue does not fix the capacity wall and does not claim to.** It is handed forward with its
measurement: the honest reading is that a walk to 128 must hold a 15 MB cursor and re-serialise it
128 times on a dyno whose worker already peaks at 505/512 MB, and **the finalize step then
materialises every banked row at once** (~70K rows), which is unmeasured. Either the retained
structure shrinks or `worker-heavy` gets more memory; that second one is an ops/cost call and is
Alex's, not this lane's.

**Why it is load-bearing for ruling 024:** the combined-invalidation window's bump wipes the cursor
and takes the page dark for a full re-walk. **Beat lifetime is therefore the length of a planned
outage**, and right now it is shrinking beat over beat.

## 🛑 CONVERGING IS NOT PUBLISHING — the 128th unit does not turn the page green (CAL-P032, 2026-08-10)

**Five items on this scoreboard wait on "the publish", and every handover since CAL-P028 has forecast
it as "~N beats away" from the unit count alone. That forecast is wrong, and the gap is not small.**

Reaching 128 banked units does not publish anything. It hands a *candidate* to
`calibration_publish_gate.evaluate_publish`, which refuses a population move of more than **±5%**
against the published baseline unless `CALIBRATION_POPULATION_VERSION` is bumped. The baseline is the
**2026-08-02** payload (`total_outcomes` 652,407, `q267`); the candidate is nine days of population
growth later; the version is `q267` on both sides. **So the comparative rules apply in full, and the
measurement says they will fire.**

Measured 2026-08-10 23:5xZ from the 55 banked units in the live cursor (all 26,821 stored bucket rows
parsed — `matched == total_elems`, checked, because a silently dropped row would bias every figure):

| quantity | value |
|---|---|
| banked / planned | 55 / 128 |
| outcomes in banked units | 281,694 (kalshi 175,879 · polymarket 105,815) |
| per-unit n | mean 5,121.7, sd 961.1 |
| extrapolated futures @128 | **655,578 ± 12,576** (1 SE, finite-population corrected) |
| candidate `total_outcomes` (+ sportsbook legs carried flat) | **≈ 695,653** vs published **652,407** |
| **drift** | **+6.63%**, 95% CI [+2.85%, +10.41%] · limit **±5%** → P(reject) ≈ **0.80** |

**The extrapolation is not the weak link.** If the 55 banked units were unrepresentative, source
composition would show it: polymarket is **37.98% of banked** (SE 0.87pp) against **31.31% of
published** — z ≈ 7.6, which sampling noise cannot produce. Per source, kalshi is **−2.7%** and
polymarket **+28.4%**; a biased sample moves both together, a real backfill moves one. The known
never-graded polymarket cohort being graded into truth-eligibility is exactly that mechanism.

**A second, independent rejection path is already at the line.** Rule 3 refuses any category over
1,000 outcomes that loses more than 20% without a bump: `entertainment` is published 12,535 → est
10,051 = **−19.8%** against a −20% limit. Entertainment carries no sportsbook legs, so unlike the
sports categories that comparison is clean.

**What happens at unit 128, traced through the code rather than assumed:** the futures phase merges
and returns **without clearing the cursor**; `evaluate_publish` rejects; `_file_publish_gate_rejection`
files the deduped issue; the task **raises**. The next beat resumes at 128, skips every unit, reaches
the gate in minutes and is rejected again — **hourly, indefinitely.** Not a crash: a fast, quiet,
permanent rejection loop that looks *healthier* than today (beats stop timing out) while the page
stays exactly as dark.

**And the escape hatch is booby-trapped in both directions**, each verified in source:

1. **A bump wipes the cursor.** `resolve_staged_cursor` returns `INVALIDATE /
   population_version_changed` on a version mismatch — every banked unit dies, the walk restarts at
   zero. Same shape as CAL-P031's fingerprint trap, different key.
2. **A bump takes the page DARK.** `snapshot_verdict` refuses a `wrong_version` artifact at *both*
   serving tiers. CAL-P017's dated tier rescues `too_old`; it does not rescue `wrong_version`. This
   is the 2026-08-02 outage, and `precompute_calibration.py` already records it being tried and
   reverted the same hour.

**None of this is broken — it is designed, and the design says so.** The build module's own comment
sets out the intended sequence: land the population change under the current version, let the gate
reject and *measure* the drift, "**the gate's rejection report IS the exact-SHA census**", then bump
once reviewed. Ruling 024 now folds that bump into the single combined invalidation window. What was
lost is that this step exists at all: nine days of handovers compressed "the build converges" into
"the page publishes", and there is a gate between them.

**So the honest path to a green SLO is not ~4 beats.** It is ~4 beats to a rejection that produces
the census, then ruling 024's combined window (a frozen-file edit), then a fresh convergence with the
page dark, then a publish. **Whoever takes the next queue should expect the rejection and read its
report as the deliverable — not read it as a regression.**

**Item 1 is the one that changed shape.** Its rail was walked to exhaustion and returned a
PREMISE-BROKEN answer: the move-count predictor underlying ruling 011's tier 2 does not work, so
there is no N to ship. That is a finished measurement, not an unfinished task — but **it converts
item 1 from work into a decision, and the decision is Alex's.** It is the one item that can no
longer be closed by this lane doing anything.

**The generalisable lesson, since this lane paid for it four times over.** Items 2 and 4 sat 🟡 for a
day reading *"blocked on: rendered proof; needs the merge + the browser rail"*, and every cycle in
between re-derived that they were blocked. Both blockers had in fact cleared at INT-031 — **the
work was done and the evidence was one dispatch away.** A "blocked on" column is a claim with a
timestamp, not a standing fact; nothing recomputes it, so it decays exactly the way this program's
queue header kept decaying (five corrections, both directions). **Re-test the blocker before
believing it.** Dispatching the browser rail and reading the two screenshots cost about four
minutes and turned two items green.

---

### 🟢 THE BUILD IS CONVERGING — first confirmed forward motion since 2026-08-02 (CAL-P030, 22:31 UTC)

**This supersedes everything below it, including this document's own "it is diverging" section.**
Two consecutive beats, read from `durable_state_snapshots`:

| beat | cursor written | banked / 128 | dropped | drift |
|---|---|---|---|---|
| 14:15Z (pre-CAL-P028) | — | 20 → **19** | **16** | (the mechanism) |
| 20:15Z (CAL-P028 live) | 20:37:47Z | **19** | **1** | 0 |
| 22:15Z (INT-034 live) | 22:29:25Z | **36** | **0** | **0** |

**19 → 36 in one beat, with zero drops.** At ~17 units/beat the build reaches 128 in roughly five
to six more beats — which is CAL-P028's own "~6-7 beats" prediction, now observed rather than
projected. The lane's standing model that the publish was *waiting*, then that it was *going
backwards*, is replaced by a measured rate.

**And it is legible for the first time.** INT-034's repair of `_record_staged_convergence` is
confirmed working in production — the 22:15Z ledger carries, on a **`cancelled`** terminal (exactly
the path CAL-P028 built it for and the path that never recorded anything):

    "staged:units_banked":    36
    "staged:units_partition": 128
    "staged:units_drifted":   0

This is the first ledger in **187 consecutive failed beats** to state where the build actually is.
The prediction handed to INT-034 while its fix was in flight (`units_banked` 19+, `partition` 128,
`drifted` 0) is met.

**What is still true and must not be rounded off:** the beat is still `cancelled` at its deadline,
`plan_status` is still `infeasible`, `consecutive_failures` is **187**, and `/api/calibration` is
still serving the 2026-08-02 payload at **8.73 days**. Convergence is a rate, not a publish. **The
SLO stays RED until a beat completes all 128 units and publishes** — expected in ~5-6 beats if the
rate holds, which is the thing to check next and the first check this lane has that is worth making.

**One residual the fix cannot reach:** a **SIGKILLed** beat writes no ledger at all, because
`save_phase_ledger()` is never reached. `starts_24h 17 · failures_24h 10 · hard_kills_24h 7-8`. So
roughly 41% of beats remain invisible, and consecutive banked readings may be separated by an
unrecorded beat — **key the trend off the cursor's `generated_at`, never off beat counts.**

> **CORRECTION (CAL-P031, 2026-08-10) — "invisible" is not "lost", and the paragraph above reads as
> though it were.** `save_staged_cursor` is called **per unit**, inside the unit loop, immediately
> after that unit's own commit (`precompute_calibration.py:2995`), and the caller treats a unit as
> banked only when that durable write returns `True`. **A SIGKILLed beat therefore loses at most one
> in-flight unit, never its banked ones.** The 21:15Z beat that wrote no cursor row banked *zero* —
> it died before completing a single unit, i.e. before ever reaching the unit loop.
>
> So the remaining gap is one of **attribution** (where did a killed beat spend its 1,560 s?), not of
> **destruction**. Both are worth fixing; they imply completely different work, and the trend-read
> guidance above is unaffected and still correct.

### 🟢 THIRD CONSECUTIVE FORWARD BEAT — 55/128, and drift no longer decides (CAL-P031, 2026-08-10)

| beat | cursor written (FINAL) | banked / 128 | drift | net |
|---|---|---|---|---|
| 20:15Z | 20:37:47Z | 19 | 0 | — |
| 22:15Z | 22:29:25Z | 36 | 0 | +17 |
| 23:15Z | 23:37:45Z | **55** | **16** | **+19** |

**About four beats from a publish** at ~+18/beat. The table above projected "~5-6 beats" from 36;
this is consistent with it, not a revision.

**Drift came back at 16 and it did not matter, which is the more durable finding than "zero
drops".** The 23:15Z beat opened at 36, `retain_planned_units` dropped 16 to 20, then banked 35
fresh units to 55. Before CAL-P028 a 16-unit drop against 15 banked was net **−1**; the same drop
against 35 banked is net **+19**. CAL-P028 did not eliminate drift — it made the build faster than
drift. "Zero drops" was only ever two samples of an intermittent quantity (0, 0, 16).

⚠️ **Compare beat-final to beat-final ONLY.** The cursor is written per unit, so it advances
continuously while a beat runs. This window first read `40 @ 23:19:57Z` (mid-beat) against
`36 @ 22:31Z` (beat-final) and concluded the rate had collapsed 4x; watching the same beat to
termination gave 40 → 51 → 55. The standing advice to key trends off `generated_at` rather than
beat counts is correct but insufficient: `generated_at` says WHICH beat, never HOW FAR INTO IT.

### 🛑 THE DIGEST THAT PROTECTS THIS CONVERGENCE HAS A HOLE, IN A FILE THE FREEZE DOES NOT COVER (CAL-P031, 2026-08-10)

**Read this before touching `app/utils/resolution_authority.py`.** The build is now hours from a
publish with 36 units banked, and there is a one-line edit in an unfrozen file that silently
destroys it — or worse, silently publishes a wrong curve.

`_main_input_fingerprint` is a **wholesale cursor invalidator**: CAL-P016 removed the *roster*
digest from that role but deliberately kept the population version and the input fingerprint,
because those "change what a unit MEANS rather than which markets are in it". So the digest is the
single guarantee that a resumed generation's units were all computed against the same population.

It is built from `inspect.getsource()` over four functions. Its own docstring already records that
construction leaking twice, and states the rule: **"hashing a function's source covers that
function, never what it calls."** It leaks a third time, and this one crosses a file boundary.

`_calibration_population_ctes` interpolates `{CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}` into the
population predicate at four sites (`:1865`, `:1932`, `:1957`, `:2125`). That value is imported from
**`app/utils/resolution_authority.py`** — which **ruling 009 does not freeze.** `getsource` returns
the literal brace-name, never the expanded value.

Proven by measurement, not by reading:

    digest BEFORE              e0048938f513e814c72cb35aa8732d65
    digest AFTER value change  e0048938f513e814c72cb35aa8732d65
    MOVED?                     False
    emitted SQL changed?       True

So editing the truth-eligibility list changes which outcomes the curve is built from, the cursor is
still judged **RESUMABLE**, and units from two different populations merge into one published
payload. That is `LATE_ARRIVAL_NOT_INVALIDATED` — the exact failure the digest exists to prevent —
and gotcha #53's shape for the fourth time in this document.

**Coverage is 3 inputs out of 46 — so 43 are uncovered.** Only `CALIBRATION_POPULATION_VERSION`,
`REPRESENTATIVE_TIE_AUTHORITY` and `COVERAGE_CENSUS_ENABLED` are hashed by value. The other 43
module-level names the hashed closure reads are invisible to it, in two tiers:

| tier | count | protected by |
|---|---|---|
| **cross-module** (`resolution_authority`, `calibration_coverage_bridge`) | **5** | **nothing — live today** |
| same-module (`precompute_calibration.py`) | 38 | ruling 009's freeze **only** |

> **COUNT CORRECTION (CAL-P032).** CAL-P030 and CAL-P031 both wrote this as *"3 of 43"*, reading the
> **uncovered** count as the **total**. The lists were always right (3 covered + 5 cross-module + 38
> same-module = 46); only the sentence was wrong. The authoritative figures are now **46 total / 3
> covered / 43 uncovered**, and they come from a generated artifact rather than from prose —
> `backend/tests/evals/fixtures/calibration_fingerprint_derived_map.json`, produced by
> `scripts/evals/calibration_fingerprint_derived_map.py`, which parses the hashed roots, the
> by-value names and the whole referenced closure out of the real `_main_input_fingerprint` body.
> A hand-copied census restated in three documents drifts in exactly this way; a derived one cannot.
> Of the 43 uncovered, **21 are SQL-shaping** (interpolated into emitted SQL) and 22 are
> behaviour-or-evidence.

**The second row is the part that deserves a ruling.** Those 38 include real population predicates —
`KALSHI_LIQUIDITY_EXISTS`, `POLY_PLACEHOLDER_EXCLUDE`, `WEATHER_WIDE_SPREAD_EXCLUDE`,
`MEX_NORMALIZE_THRESHOLD`, `EXCLUSIVITY_PROVED_RELATIONS`, `DRAW_CAPABLE_CATEGORIES` — and they are
safe right now **only as a side effect** of a freeze that was imposed for throughput reasons and is
designed to lift. Ruling 009 is, accidentally, load-bearing for correctness. Nobody decided that.

**What CAL-P031 shipped, and what CAL-P032 replaced it with.** CAL-P031 shipped
`app/utils/calibration_fingerprint_coverage.py` — pure and AST-only, but with the roots, the
covered-by-value names and both uncovered tiers **typed out by hand**. CAL-P032 integrated C258's
generated map (`scripts/evals/calibration_fingerprint_derived_map.py` + its checked-in artifact) and
**deleted the hand map outright** rather than keeping it "for reference": two derivations of one fact
is how they drift, which is the defect this census exists to catch, one level up.

The ratchet is now the artifact itself. `derive_map() == frozen()` fails on **one more** input and on
**one fewer** — gotcha #10's `typecheck-baseline.json` lesson (a one-directional baseline becomes
silent headroom) obtained for free instead of hand-maintained. What survives from CAL-P031 is the
part an artifact cannot express: the characterization test proving **by value** that the live digest
does not move when `CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL` changes, paired with a non-vacuity test
proving the changed value really does reach the emitted SQL. The day the fix lands, it goes red and
forces the docs to move with it.

**What CAL-P031 deliberately did NOT ship, and why the obvious instinct is wrong here:**

> The fix is one line, in the idiom `_main_input_fingerprint` already uses for
> `COVERAGE_CENSUS_ENABLED`. **Do not apply it yet.** Two independent blockers:
> 1. ruling 009 freezes that file, and the lift condition is not met;
> 2. **applying it wipes every banked unit** — moving the digest is *by design* a wholesale
>    invalidation, so doing it mid-convergence destroys the exact progress it protects and restarts
>    a multi-hour walk.
>
> **Apply immediately AFTER a successful publish, never during a convergence.** Full note in
> `FIX_SEQUENCING_NOTE`, now in `scripts/evals/calibration_fingerprint_derived_map.py` beside the
> artifact (it moved there with the census when CAL-P032 deleted the hand map).
>
> **Superseded in scope by ruling 024 (2026-08-10):** the fix is no longer a standalone follow-up. It
> rides the ONE combined invalidation window that opens at the first fresh publish, together with
> ruling 011's two-tier well-traded, the cricket/entertainment exclusions, and the population-version
> bump plus its published before/after census. Shipped separately each invalidates the last, and the
> before/after census only means something across a single known boundary. Ruling 024 also names the
> reason the coverage gap survived undetected: **the freeze was accidentally load-bearing for
> correctness**, so the fix must land in the same event as the lift rather than after it.

### ✅ UPDATE 2026-08-10 (CAL-P030) — CAL-P028's fix landed, and the divergence STOPPED

CAL-P028 merged (`9bdbfe36`), deployed at 20:04 UTC, and its first beat ran at 20:15 UTC. Measured
on that beat, **read directly from `durable_state_snapshots` rather than from the ledger**:

| | pre-fix beat (14:15Z) | first post-fix beat (20:15Z) |
|---|---|---|
| units dropped by `retain_planned_units` | **16** of 20 | **1** |
| roster drift units | (the mechanism) | **0** |
| banked at terminal | 19 | **19** |

**The churn is gone.** The section below says the build was going backwards; as of this beat it is
no longer. It is not yet going meaningfully *forwards* either — the beat still exhausts its 1,380 s
window, `plan_status` is still `infeasible`, `consecutive_failures` is **186**, and
`/api/calibration` is **8.73 days stale**. But the mechanism that made 128 units unreachable in
principle has been removed, which is the precondition for every "blocked on the publish" item above.

**⚠️ And the instrument that should have said all this is blind.** CAL-P028's own
`_record_staged_convergence` — added precisely so a dying beat reports its position — calls
`.get("payload")` on the frozen `EnvelopeRead` dataclass returned by `read_snapshot_standalone`.
That raises `AttributeError` on every call, its deliberate best-effort `except` swallows it, and
**none of its three stages has ever been recorded**; all eight of its tests pass because every one
mocks a plain dict. The numbers above had to be read out of the durable table by hand — the exact
labour CAL-P028 existed to end, and gotcha #53 for the third time in this document.

The fix is **owned by INT-034 and in flight**, not by this lane (found independently ~15 minutes
apart; the queue lock decided it). Post-deploy, the next ledger must show
`staged:units_banked: 19`+, `staged:units_partition: 128`, `staged:units_drifted: 0`. If it shows
nothing, the fix did not take.

---

## ⛔ THE SCOREBOARD ABOVE IS NOT THE BINDING CONSTRAINT — measured 2026-08-10 (CAL-P028)

Five of the seven items are blocked on "the publish", and every cycle since 2026-08-02 has recorded
that as *waiting*. **It was not waiting. It was diverging**, and this is the first cycle that
measured it rather than projecting it.

One fully productive beat of `calibration:main`, captured end to end at a 2-minute sample interval:

| time (UTC) | committed units | event |
|---|---|---|
| 14:15:33 | 20 | beat starts |
| 14:17:19 | **4** | `retain_planned_units` drops **16 of 20** |
| 14:19 → 14:33 | 6→8→10→12→14→16→18→**19** | 15 units banked, 989 s, **65.9 s/unit** |

**Net across a beat that completed 15 units: 20 → 19. Minus one.** At 128 planned units the build
cannot finish, and no amount of waiting changes that.

Supporting state, same window:

- `generated_at` = `2026-08-02T03:23:54Z` — **8.44 d stale**, 7th consecutive rising reading.
- **181 consecutive failures**, 0 successes/24h, 9 starts, 4 hard kills, `health: critical`.
- The build's own planner reports `plan_status = **infeasible**`.
- `futures` phase floors, last 10 beats: `[448, 1352, 1373, 1362, 921, 1369, 1368, 1375, 1377, 1363]`
  s against a **1,380 s** deadline — every beat burns its whole window and is cancelled.
- **CAL-P024's `COVERAGE_CENSUS_ENABLED = False` had been live ~8.5 h and changed none of it.** The
  census was a real 10x cost and was NOT the binding constraint.

### The two corrections this forces on the lane's model

1. **Ruling 009's lift condition is unobservable by construction.** It asks for "~13 consecutive
   clean beats". Every staged beat ends `failed` — the unit loop starts a unit it cannot finish in
   the remaining window and dies on a statement timeout, or is SIGKILLed. There has been no clean
   beat since 2026-08-02 and there cannot be one under that loop. A freeze whose lift condition
   cannot occur is a freeze without an exit.
2. **The bucket count is not the dial the constant's own docstring says it is.** That docstring is
   right that convergence needs `completed/beat > invalidated/beat`, and right that it had never
   been measured. But per-unit fixed overhead is ~52 s (128 units ≈ 8,013 s against ~1,320 s
   unchunked), so completions cap near 26/beat while churn destroys ~16-19/beat. The arithmetic
   optimum near B≈170 still needs ~55 beats. **Raising it does not rescue the build.**

### What CAL-P028 changed, under an Alex ruling taken this window

Unit identity is now the **slot** (`buckets`, `index`) rather than the unit's full roster
membership, in `app/utils/calibration_staged_futures.py` — *not* the ruling-009-frozen file. Units
stop being destroyed by arrivals; the build should converge in ~6-7 beats instead of never.

Staleness is **demoted from an invalidator to a measurement**, not discarded: `member_digest` is
still computed, stored per banked unit, and compared by the new pure `roster_drift`, which counts
how many held units the roster has moved under. Bound: ~20 arrivals/hour against a ~110K roster is
~0.1% for a six-beat build, and those markets are picked up whole by the next generation. **Late
inclusion, not a wrong number — and published rather than assumed.**

And the reason this took three cycles to find is itself fixed: `staged:units_done` and
`staged:beats_to_publish` are recorded at the END of the unit loop, which a dying beat never
reaches, so they were **absent from 181 consecutive ledgers** and an absent stage reads as "fine"
(gotcha #53). `_record_staged_convergence` now writes `staged:units_banked`,
`staged:units_partition` and `staged:units_drifted` on **every** terminal, read-only and
best-effort, from the non-frozen build module.

**Still owed, and pre-declared rather than discovered:** this cycle cannot show the build
publishing. The fix runs in the heavy dyno, so its first real beat is post-merge — the CAL-P018
shape. The verification is one sampled beat showing `committed_units` climbing past 20 without a
drop, then convergence to 128.

**Nothing on this exam is now unblocked and unstarted.** Every remaining item waits on the publish
converging (1, 3, 7), on a merge plus a capture (2, 4), on elapsed time (7), or on another lane
(6's sentinel half, #1548). That is a different state from every previous cycle, and it means the
lane's throughput is no longer the binding constraint — **`calibration:main` publishing again is**,
which is CAL-P024's payoff and is sitting unmerged in the Integrator's queue.

**Updated 2026-08-09 by CAL-P027 — and the state CHANGED mid-queue, in the good direction.** Both
readings are kept, because the second one is only interpretable against the first.

At **21:39 PT** the publish was **8.05 days** stale (a sixth consecutive rising reading) and
CAL-P024 was *still unmerged*, confirmed by content rather than by a handoff file: `origin/master`
carried `COVERAGE_CENSUS_ENABLED = True`, the exact line CAL-P024 flips.

At **22:45 PT**, while this queue was in its gates, **CAL-P024 merged and deployed** — master
`ff627a39` (as CAL-P024a/b/c against #1479), `/api/health` reports `ff627a39`, and
`COVERAGE_CENSUS_ENABLED = False` is live. **So ruling 009's baseline has now landed and the
~13-beat convergence count can start for the first time.** A unit should cost ~62.6 s again rather
than ~632 s.

**What that does and does not mean.** It does not make the publish fresh — as of this writing
`generated_at` is still `2026-08-02T03:23:54Z`, and it stays that way until the build actually walks
128 units. **The lane's one product-visible SLO — `/api/calibration` serving a payload under 24h old
— is still RED**, and the next window's first job is to read whether `staged:cursor_resume` appears
with `committed_units` climbing, and whether `staged:beats_to_publish` (new in CAL-P024) names a
finite number. Ruling 009 lifts on two recorded observations, not on this merge.

**The freeze is still on.** Its lift condition is a fresh post-CAL-P024 publish *plus* ~13 clean
beats, recorded. Nothing above satisfies either half yet.

Three of the seven items still reduce to one sentence: **merge the queue.** Items 2 and 4 need the
merge plus a photograph; item 1 needs the merge plus one walk of the rail below. Item 3's cricket
fix now needs only the publish to converge. The lane has run out of work that does not route
through the Integrator or through the beat — which is the correct place for it to run out, and
worth saying plainly rather than letting a fifth diagnostic rail be invented to fill the time.

### Why items 2 and 4 were taken while the build is dark — the reason generalises

Every other unblocked item on this exam is waiting for `/api/calibration` to publish again, and
CAL-P020's report already named the pattern that creates: **deploying is not publishing.** Three
shipped read-side improvements (CAL-P011's reachability tier, CAL-P012's purged count, CAL-P014's
denominator) each recorded a payoff "owed post-deploy" that could not arrive, because a payload
change is invisible until a build succeeds.

Items 2 and 4 are the two items that escape that, and it is a property of the data rather than of
the work: **both are computable from the payload that is already published.** `buckets` is a
1,606-row array carrying `source`, `category`, `bucket_idx`, `price_moved`, `n`, `winners` and
`sum_prob` on every row, so the matched comparison and the per-source panels are re-groupings of
bytes production has already served since 2026-08-02. No backend change, no population-version
bump, no publish, and — the part that matters most right now — **no edit to
`precompute_calibration.py`**, whose hashed functions reset the staged cursor on every touch.

That last point is a lane-wide constraint CAL-P024's rate-mismatch finding implies and nobody had
written down: the build needs ~13 consecutive uninterrupted beats to converge, and the file has
taken ~1.8 commits/day for two weeks. **Until the curve publishes, work that touches the
precompute is work that prevents it from publishing.** Items 2 and 4 were the right work partly
because they are the right work, and partly because they are off that critical path.

### The one scheduling fact that governs the exam

Items **1** and **3** change what the curve plots, so each carries a
`CALIBRATION_POPULATION_VERSION` bump. Already-staged **CAL-P019** carries a third. A bump takes
`/calibration` dark until the next successful beat.

**No bump ships until the build publishes again.** As of 2026-08-09 10:54 PT the build has still
not published since **2026-08-02 03:23:54 UTC** (age 7.59d). Until `calibration:main.generated_at`
moves, **items 1, 3 and 7 cannot be evidenced at all** — their proof is a published number.

That makes CAL-P016's convergence the critical path for most of this exam.

### CAL-P016 convergence — measured 2026-08-09 10:36–10:54 PT, window `b2e4`

The staged path is **working but not yet proven to converge**, and the distinction is exact:

| fact | value |
|---|---|
| beat | hourly at **:15**, `soft_time_limit=1500s` |
| staged beats run since deploy | **exactly one** — generation `1786292100304` = 16:15:00Z |
| that beat | `read:futures_generation` 25.7s + `read:futures_unit` 626.2s → **10 units banked**, then cancelled at 726.6s |
| per-unit cost | **~62.6 s/unit**; 128 units ⇒ ~2.2h of compute ⇒ **~13 beats** |
| cursor | `terminal=partial`, 10 committed, `population_version=q267` |
| plan | **`status: infeasible`** — `floor_ms` 1,352,317 over `floor_observations: 10` |
| floors | `[1352317, 1351773, … ×9 stale monolith TIMEOUTS, 726557]` |

**Two findings, both new.**

1. **The floor is poisoned by the old regime.** Nine of the ten banked observations are
   pre-CAL-P016 monolith *timeouts* at ~22.5 min. The planner therefore still believes `futures`
   needs 22.5 minutes and marks the plan `infeasible`. It is a rolling window of 10, so it
   self-heals — but only after ~9 more staged beats push the timeouts out. `infeasible` does not
   block banking (the beat banked 10 units anyway); it is a wrong belief, not a gate.

2. **Cross-beat retention is UNOBSERVED, and it is the whole ballgame.** The ledger's
   `stages` records **`staged:cursor_invalidate`** for the one beat that has run. That is
   *expected* on the first beat — the pre-existing cursor predated the new code, and
   `input_fingerprint` hashes the SOURCE of the build functions, so a deploy necessarily
   invalidates it. But the queue's earlier "4/128 and advancing" reading was **mid-beat, not
   cross-beat**: both the 4 and the 10 belong to generation 16:15:00Z. **No second staged beat has
   yet been observed**, so nothing has yet demonstrated that a banked unit survives into the next
   beat — which is precisely what CAL-P016 changed and precisely what must hold ~13 times in a row
   for the build to publish.

**The single decisive read for this lane** is therefore the *next* beat's ledger: if `stages`
shows `staged:cursor_resume` and `committed_units` climbs 10 → ~20, CAL-P016 is converging and
the publish is ~13 beats out. If it shows `staged:cursor_invalidate` again with the count back at
~10, the build is thrashing and CAL-P016 is not done.

### ✅ THE DECISIVE READ WAS TAKEN — 2026-08-09 19:11–19:18Z, window `4a9d`. It is the second answer.

The section above set the test. **The build is thrashing, and the cause is this lane's own last
merge.**

**First, a correction to the section below it.** Window b2e4 stopped watching at **18:20Z**; the
18:15Z beat committed its first unit at **18:22:22Z** and wrote its ledger at **18:27:03Z**. So the
beat it concluded had never fired had in fact fired, two minutes after it looked away. The "~40%
fire rate" therefore rests on one confirmed miss (17:15Z, straddling the INT-024 restart) and one
mis-read. It is not established. Acting on it — `heavy` queue depth was the recommended first
place to look, and reads **0** — would have been a cycle spent on a phantom.

| question | answer |
|---|---|
| did a second staged beat run? | ✅ **yes** — generation `1786299300221` = 18:15:00Z |
| did the banked unit survive? | ❌ **NO** — `staged:cursor_invalidate` again; `committed_units` **10 → 1** |
| why? | **`input_fingerprint` moved.** CAL-P020 edited `_main_futures_sql` and `_calibration_population_ctes` — two of the four functions `_main_input_fingerprint` hashes by `inspect.getsource`. INT-024 deployed it ~17:11Z. |
| per-unit cost | 16:15Z, census OFF: **62.6 s/unit**. 18:15Z, census ON: **632 s/unit**. |

**CAL-P020 flipped `COVERAGE_CENSUS_ENABLED = True` and made every unit ~10x more expensive.** At
62.6 s/unit the 128-unit build is ~2.2 h ≈ 13 beats. At 632 s/unit it is **~22.5 h of compute**
against a ~687 s usable window per beat — **~117 more beats**, over five days of unbroken hourly
beats.

It cannot get five days. **`precompute_calibration.py` took 25 commits in the 14 days to
2026-08-09 (~1.8/day)**, and any one touching a hashed function resets the cursor to zero. **The
build's convergence time now exceeds the lane's own edit interval by an order of magnitude.** That
is a rate mismatch, not a cursor bug: CAL-P016's per-unit retention works exactly as designed and
cannot help while a unit costs ten minutes.

**Say the shape of this plainly, because it is the second occurrence.** CAL-P020 exists because
CAL-P016 had made the census unbuildable; it fixed that by making the curve unpublishable. Two
correct decisions composing into a dark surface — the same pair of switches, eight days apart,
each guarded by a rule that correctly said "do not touch the other thing".

**Fixed in CAL-P024** (`program/calibration-22`): the switch goes back off on the measured budget,
with the numbers written beside it; the switch joins the fingerprint (flipping it changed the
statement but *not* the digest, so units built under two different statements were mutually
resumable); the ledger names *which* of five causes reset the cursor; and every beat now records
`staged:beats_to_publish`, so "slow" and "never" stop looking alike.

**Still genuinely open — do not treat as answered:** the 19:15Z beat produced no ledger and no
cursor write for 23+ minutes (watched to 19:38Z), against 12 minutes for 18:15Z. So beats *are*
intermittently missing; the rate is unmeasured and the cause unknown. `heavy` queue depth is 0 and
`background` is **442** (documented threshold: 50) — the latter is an ops finding, not this lane's.

### ⚠️ Superseded — the original "beat is NOT firing hourly" reading

Kept for the record; corrected above. Observed 16:27Z → 18:20Z:

| observation | 16:36Z | 18:20Z |
|---|---|---|
| `precompute_calibration_main.failures_24h` | 10 | **10 — unchanged** |
| ledger generation | 16:15:00Z | **16:15:00Z — unchanged** |
| cursor `committed_units` / `updated_at` | 10 @ 16:26:24Z | **10 @ 16:26:24Z — unchanged** |

Read as "neither the 17:15Z nor the 18:15Z beat ran". The 18:15Z half is now known to be a
two-minute-early read. **The lesson is worth more than the datum: this lane's projections have twice
turned on a snapshot taken just before the thing it was waiting for.** A negative observation about
a periodic process needs a margin past the full period, and should say what margin it used.

---

## 1. Ruling 9 shipped; the published count reflects volume-proven trading

**Required proof:** the deployed well-traded definition reads source volume; before/after counts
**by source**; sources with no volume concept excluded; NULL published as UNKNOWN, never
"untraded"; a bumped population version; **both figures named** in the payload.

**Status: 🟡 RULED 2026-08-09 — the definition is settled; nothing is built.**

The A/B inference is **superseded and no longer load-bearing.** Alex ruled directly, and better
than either option: *"use volume when we have it, and infer volume from multiple price moves
otherwise."* Per-row, not per-source. Full text in PRODUCT-BRAIN § RULINGS 2026-08-09(b).

The published definition is an ordered ladder, each row carrying its provenance:

1. `volume_proven` — `volume` populated; traded iff `> 0`
2. `movement_inferred` — no volume, adequate observation density, `>= N` distinct price changes
3. `unknown` — neither; **published as its own count, never folded into "untraded"**

"Both figures named" = all three counts published, by source.

**Two things that make this real work rather than a predicate change:**

- **`price_moved` is not a move count.** It is `calibration_probability IS DISTINCT FROM
  opening_probability` — closed-away-from-open. A market that traded all day and returned to its
  open reads as untraded today. Tier 2 must be built fresh from `futures_odds_snapshots`
  (`outcome_id`, `probability`, `captured_at`).
- **Tier 2 is density-gated.** 3 snapshots can yield at most 2 moves however much a market traded;
  calling that untraded is gotcha #53's shape. Below the threshold: `unknown`.

**N is measured, not chosen.** On rows carrying BOTH volume and adequate snapshots, measure how
well `>= N moves` predicts `volume > 0`. That fixes N and yields a publishable precision figure.
A weak proxy is a finding to report, not a number to ship.

**Owed before staging:** the overlap census above (volume coverage by source × snapshot density ×
move counts). Read-only, one bounded rail, no ruling needed.

### The overlap census cannot be hand-measured — it needs a rail (measured 2026-08-09, window `b2e4`)

This was attempted directly and **the tier-1 half works while the tier-2 half is unreachable
through `db-query`**. Recording the measured costs so the next window does not re-derive them:

| query | window | result |
|---|---|---|
| volume coverage on the resolved priced population | 5M ids | ✅ **1.09 s** — 20,117 outcomes, 843 with `volume` (4.2%), 797 with `volume > 0` |
| population count alone, no snapshot join | 100K ids | ✅ 0.77 s |
| `LAG()` move-count over `futures_odds_snapshots` | 5M ids | ❌ statement timeout (10 s) |
| same | 500K ids | ❌ statement timeout |
| same | **100K ids** | ❌ statement timeout |
| bare `COUNT(*) FROM futures_odds_snapshots WHERE outcome_id < 100000` | 100K ids | ❌ **statement timeout** |

The last row is the decisive one: **a bare `COUNT(*)` over a 100K-id slice of
`futures_odds_snapshots` exceeds the timeout**, with `idx_fos_outcome_captured` present. Shrinking
the window does not help because the window is not the cost — the snapshot table is. This is not a
data finding and it is **not** the pre-declared PREMISE-BROKEN condition (which is about too few
rows carrying both signals); it is purely a tooling bound.

**So tier 2 is blocked on the same thing CAL-P018 was blocked on, and has the same answer:** build
it as a rail. `POST /api/admin/repairs/prop-threshold-cliff-census` exists precisely because a
population measurement that only a lucky window can run is anecdotal rather than published. The
overlap census needs the identical treatment — a bounded outcome-ROW walk returning
`(has_volume, snapshot_count, move_count)` cohorts with `next_offset`/`exhausted`.

**Early signal, one window only, do not generalise:** volume is populated on just **4.2%** of the
oldest resolved priced slice. If that rate holds across the population, tier 1 (`volume_proven`)
covers very little on its own and the ladder's weight falls almost entirely on tier 2 — which
makes measuring N *more* load-bearing, not less. One 5M-id window out of ~44 is not a population
estimate; the rail must produce the real number.

### 🛑 WALKED TO EXHAUSTION 2026-08-10 (CAL-P030) — and the answer is PREMISE-BROKEN

**N is not a number this lane may publish. The measurement says the predictor does not work.**

The rail merged at INT-031, deployed at `f6a40849`, and was walked to exhaustion for the first
time: **381 windows · 3,275,813 outcome rows · 939,570 eligible · 41 hot windows · 45 minutes**,
terminating `exhausted: true`. This is a COMPLETE walk, not a sample — `is_complete_walk()` is
true, so the figures below are the population.

CAL-P027 pre-declared the handling for this exact outcome and it is now in force: *"if too few rows
carry both volume and adequate density, N is unmeasurable, tier 2 has no basis, and exam item 1
returns to Alex as a real choice. Report and stop — **do not invent N**."* The premise broke, though
**not in the way that sentence anticipated** — and the difference matters, so it is stated plainly.

#### What actually broke

Not scarcity. **242,423** outcomes carry both a volume reading and density ≥ 2; 81,223 carry both at
density ≥ 10. There is plenty to measure with. What is missing is a **negative class**: the overlap
population is already **88.2%** `volume > 0` at density ≥ 2 and **96.2%** at density ≥ 10. There is
almost nothing for a move-count threshold to discriminate.

Scored against that base rate — the comparison that decides whether a predictor is a predictor:

| population | floor | base rate | N=1 | N=2 | N=3 | N=5 |
|---|---|---|---|---|---|---|
| all | density ≥ 2 | 0.8819 | 0.964x | **1.039x** | 1.031x | 1.052x |
| all | density ≥ 10 | 0.9619 | 0.989x | 0.992x | 0.977x | 0.967x |
| kalshi | density ≥ 2 | 0.8780 | 0.963x | **1.040x** | 1.029x | 1.049x |
| kalshi | density ≥ 10 | 0.9583 | 0.989x | 0.992x | 0.974x | 0.962x |

(lift = precision ÷ base rate; **below 1.0 means the threshold selects a set that is *less* likely
to be traded than the population it was drawn from**.)

**At density ≥ 10 — the floor where capture is most reliable — every threshold scores BELOW the base
rate.** The best lift available anywhere in the population is **+4.0%**, at kalshi/density ≥ 2/N=2,
bought at recall 0.442. A ladder rung worth +4% precision on a 12%-negative class, and negative
value on the cleaner half of the data, is not a mechanism to ship.

#### Polymarket cannot inform N at all, and that is a finding in itself

At **every** floor and **every** threshold, polymarket reads precision exactly `1.0000`. The
confusion matrix says why: at density ≥ 10, `true_negative = 0` and `false_positive = 0`. **Its
overlap population contains zero `volume = 0` rows.** A precision of 1.0 with no negatives is not a
measurement, it is an absence — gotcha #53's shape a third time in this document. Any future reader
who quotes "polymarket N=1, precision 1.0" will be quoting a vacancy.

Volume coverage at population scale, which is the underlying cause and the widest spread this exam
has recorded: **kalshi 47.33%** (n=583,408) · **polymarket 3.16%** (n=331,377) · **datagolf 0.00%**
(n=24,785). CAL-P027's caution that "one window is not a population estimate" was right; its three
sampled windows read 14.2% / 4.5% / 4.2%.

#### One CAL-P027 hypothesis confirmed dead, in the useful direction

Item 0b.3 recorded that `volume = 0` "did not appear once" across three sampled windows, and
flagged that if it held at population scale, tier 1 would never classify anything as untraded. **It
does not hold: `volume = 0` occurs 49,976 times (5.32%).** The three-valued `volume_state` the rail
insisted on — `absent` 69.49% / `zero` 5.32% / `positive` 25.19% — is what made this visible;
folding `absent` into `zero`, the error ruling 011 was written to prevent, would have reported ~75%
untraded and inverted the whole result.

#### What this returns to Alex

Ruling 011's **tier 2 (infer trading from price movement) has no measured basis** and should not be
built. Tiers 1 and 3 are untouched by this finding. The options are Alex's, not this lane's: drop
tier 2; keep it as an explicitly-unvalidated heuristic with the +4% figure published beside it; or
accept that the published count covers only volume-proven trading, which is **25.19%** of eligible
outcomes and **47.33%** of kalshi's.

**Reproduce with:** `python3 backend/scripts/walk_overlap_census.py` (CAL-P030 — read-only, adaptive
window, refuses to publish an N from a partial walk).

### ✅ RAIL BUILT — CAL-P027, 2026-08-09, `program/calibration-25`

`backend/app/tasks/census_overlap_trading.py`, registered as `overlap-trading-census` on the repair
rail. Bounded outcome-row walk, `next_offset`/`exhausted`, never writes. Per
`(source, category, volume_state, density band, move band)` it returns outcome counts, snapshot
rows, observations and distinct price moves; `precision_for_threshold()` then scores `>= N moves`
as a predictor of `volume > 0` on the overlap population. 95 tests, 12 mutations.

**Why this was the one item-1 move available.** Ruling 011 is staged as ruling 009's freeze-lift
successor *specifically so no days are lost when the freeze lifts* — but it cannot execute without
N, and N is measured, not chosen. Had the rail not existed when the freeze lifted, the lane would
have started the measurement on that day, which is the exact outcome that staging was meant to
prevent. The rail is off the frozen file entirely (it imports the truth allowlist from
`app/utils/resolution_authority.py`, its real home, not from `precompute_calibration.py`).

**Three design findings that would each have produced a plausible, publishable, wrong N.** Recorded
because the failure mode here is not a crash, it is a number that looks fine:

1. **Snapshots are per-bookmaker.** Ordering an outcome's snapshots by `captured_at` across books
   and counting changes fabricates a move at every cross-book quote difference. Counted
   `PARTITION BY (outcome_id, bookmaker)`, folded across books with **`MAX`, not `SUM`** — ruling
   011's own "strongest evidence available"; summing multiplies a market's evidence by its book
   count. (Mitigating, measured: `odds_api` holds **12** futures markets against polymarket's
   553,876 and kalshi's 191,114, so the multi-book case is rare — but rare is not absent.)
2. **DataGolf dedups at write time; nobody else does.** It increments `reading_count` on a repeated
   reading. So `COUNT(*)` is not observation density: an outcome with one row and fifty readings is
   not sparse — we looked fifty times and it never moved, which is *evidence of no trading*, the
   opposite of the unknown ruling 011 forbids reading as thinness. Density is `SUM(reading_count)`.
3. **`volume = 0` did not occur once** across three sampled windows (8,509 / 2,759 / 2,560 eligible
   outcomes) — every row carrying volume carried `volume > 0`. If that holds at population scale it
   is a finding about **ruling 011 itself**: tier 1 never classifies anything as *untraded*, only as
   proven-traded or unknown, and the ladder's entire negative side rests on tier 2. The rail counts
   the three states separately so this is published rather than assumed.

**Volume coverage is not one number** — 14.2% (recent 550K ids) · 4.5% (mid) · 4.2% (old tail, from
the row above). The exam's own "one window is not a population estimate" caveat is upheld, and the
spread is already visible at n=3.

**N IS STILL UNMEASURED, and that is the honest state.** The rail runs in the web dyno, so its first
walk is owed post-merge — the same shape as CAL-P018, whose rail shipped in one cycle and was walked
in the next. `precision_for_threshold` returns `supported: False` with a reason rather than a number
when the overlap is too thin or the threshold splits a band; per this item's pre-declared
PREMISE-BROKEN handling, that outcome returns N to Alex as a real choice. **Do not let a later
window read a refusal as a zero.**

---

## 2. Trading-activity section led by the matched-bucket comparison

**Required proof:** the rendered `/calibration` section leads with the matched-bucket comparison;
the raw cross-cohort tiles are demoted or removed. Browser evidence, not source.

**Status: 🔴 not started. Unblocked — stageable today.**

**Why the current tiles mislead, measured.** The section compares moved vs not-moved as two
aggregate cohorts. Those cohorts have different predicted-probability *distributions*, so the
difference between their headline numbers is partly composition, not partly-nothing-to-do-with
trading. Split by bucket (published payload, 2026-08-02) the picture is different and much
narrower:

| bucket (pred) | moved=False err | moved=True err |
|---|---|---|
| 0 (4%) | −0.1pp | −0.7pp |
| 3 (35%) | −0.9pp | −2.7pp |
| 4 (45%) | −1.4pp | **−5.7pp** |
| 5 (53%) | −1.6pp | −1.1pp |
| 6 (65%) | +2.3pp | +1.4pp |
| 7 (74%) | +2.3pp | +2.1pp |
| 9 (95%) | +0.6pp | −1.0pp |

Within a bucket the two are mostly within ~1–2pp of each other. The one real signal is the
**mid-band 35–50%**, where traded outcomes over-predict noticeably more than untraded ones. That
is a genuine, specific, publishable finding — and it is exactly what the cross-cohort tiles bury.

**This is the answer the section should lead with.** The work is to compute it and render it, not
to discover it.

### 🟢 PASSED — photographed in production 2026-08-10 (CAL-P030)

Merged at INT-031, deployed at `f6a40849`, and rendered. Evidence: browser-audit run
**`31431286342`**, pack `calibration`, `base_url https://www.bainluck.com`, manifest
`result: pass`, `requested_frontend_sha` == `observed_frontend_sha` == `checkout_sha` ==
`f6a40849cc47dbcdce6a717c9ff7a86d8d5199e4`, `observed_backend_sha f6a40849`, 2 journeys selected /
2 completed / 0 failed. Artifacts: `calibration.anonymous.{desktop,mobile}.terminal.png`.

**This item asked for a rendered screenshot rather than source, so here is what the screenshot
actually says** — the matched-bucket table now LEADS the section, above the two cross-cohort tiles:

| predicted | price moved | price unchanged | difference |
|---|---|---|---|
| 0–10% | −0.7pp (71,753) | −0.1pp (50,954) | −0.6pp |
| 10–20% | −0.4pp (44,860) | +0.8pp (34,042) | −1.2pp |
| 20–30% | −1.3pp (41,668) | −0.8pp (32,655) | −0.5pp |
| 30–40% | −2.7pp (37,774) | −0.9pp (28,529) | −1.8pp |
| **40–50%** | **−5.7pp** (42,067) | **−1.4pp** (33,516) | **−4.3pp** |
| 50–60% | −1.1pp (36,546) | −1.6pp (32,749) | +0.5pp |
| 60–70% | +1.4pp (23,762) | +2.3pp (17,002) | −0.9pp |
| 70–80% | +2.1pp (21,759) | +2.3pp (13,575) | −0.2pp |
| 80–90% | −0.2pp (16,121) | −1.4pp (7,784) | +1.2pp |
| 90–100% | −1.0pp (13,000) | +0.6pp (12,216) | −1.6pp |

The page states the finding in its own words: *"In 9 of 10 matched buckets the two cohorts land
within 2pp of each other. The widest matched gap is the 40-50% band … a 4.3pp difference on 75,583
outcomes. Comparing inside a bucket holds the predicted-probability mix fixed, which the two
headline figures above cannot do."*

**The demotion is real, not cosmetic.** The two whole-cohort ECE tiles (1.7pp moved / 1.0pp
unchanged) now sit BELOW under a heading "The overall split", captioned *"Because the two cohorts
differ in source, category and market-shape mix, whichever side lands lower here is an observed
ordering — not evidence that trading caused it. The table above is the version that controls for
that."* That is the exact sentence this exam item was opened to obtain.

Two honesty affordances shipped that the item did not ask for and should keep: rows where either
side is under 1,000 outcomes render greyed rather than hidden, and an unmatched bucket renders a
dash instead of silently reading as zero error.

### Superseded — the pre-photograph assessment, kept for the record

**BUILT — CAL-P025, 2026-08-09, `program/calibration-23`**

**Correction to this item's own staging note, worth stating because it changed the plan.** The
line above said "compute it server-side". That is wrong, and wrong in a way that would have been
costly: server-side means editing `precompute_calibration.py`, which resets the staged cursor
(CAL-P024) and would have pushed the publish further away in order to render a section about
honesty. The whole comparison is derivable **client-side from the published payload**, because
every bucket row already carries `bucket_idx`, `price_moved`, `n`, `winners` and `sum_prob`.

What shipped:

- `compareMatchedBuckets()` in `frontend/lib/calibrationMath.ts` — the matched roll-up, living
  beside `describeActivityComparison`, whose own comment diagnosed the composition problem
  ("C111 [P2] showed this aggregate is composition sensitive") and then correctly declined to act
  on it. This is that diagnosis treated.
- The `/calibration` trading section now **leads** with the per-bucket table; the two cross-cohort
  ECE tiles are **demoted to supporting detail under "The overall split"**, not deleted — they
  are still the honest aggregate, they were just never the headline.
- New rail hooks: `calibration-matched-buckets`, `calibration-matched-sentence`,
  `calibration-matched-row` (with `data-comparable` and `data-gap-pp` per row),
  `calibration-matched-unavailable`.

**The finding is now pinned by test against the frozen production payload**
(`__tests__/lib/calibrationMatchedBuckets.test.ts`, 23 tests), so a regression changes a number in
CI rather than quietly on the page: bucket 4 = **−5.7pp moved vs −1.4pp unchanged, a 4.3pp gap on
75,583 outcomes**, and **9 of 10 matched buckets land within 2pp of each other**. The partition
reconciles exactly — 349,310 moved + 263,022 unchanged + 40,075 not-applicable = 652,407.

Three rules the tests enforce, each proven non-vacuous by mutation:

1. **An absent side is a dash, never 0.0pp.** A bucket only one cohort reaches has no gap; showing
   "0.0" would manufacture an agreement out of missing data — gotcha #53's shape, in a table cell.
2. **Thin sides are shown but cannot carry the finding.** A 40-outcome bucket with a huge gap must
   not become the headline; the floor is the same 1,000 the curve fades dots at, and a test now
   pins the two to the same constant so the caption cannot drift from the behaviour.
3. **The sentence never claims a cause.** Same rule the aggregate comparison already holds itself
   to, asserted by regex.

**Still owed for GREEN: the rendered screenshot.** The required proof is browser evidence, and
local Chromium does not launch in an agent sandbox (confirmed again this window). The remote
`browser-audit.yml` rail grades **production**, which does not carry this branch, so the evidence
is genuinely obtainable only after the merge deploys.

---

## 3. Cricket and entertainment — a named diagnosis each

**Required proof:** per cohort, one of — a shipped fix with before/after, a documented exclusion
carrying its published count (the standing house rule), or a demonstrated "the market is
genuinely bad here". No massive-error category left unexplained.

**Status: 🟡 measured, not diagnosed.** Both were surfaced by the 2026-08-09 09:11 PT window's
analysis of the published payload.

### polymarket cricket — wECE 9.38pp, n=3,003

Worst bucket: **pred 52% → act 81%** (n=608). Under-prediction in the mid band, which is the
opposite direction to most defects in this product and therefore unlikely to be the usual
settlement-collapse artifact.

Leading hypothesis to test first: two-outcome cricket markets where the favourite is
systematically mispriced, or a resolution-source asymmetry. **Untested.**

### kalshi entertainment — wECE 5.87pp, n=9,489

Worst bucket: **pred 95% → act 70%** (n=914). A high-band collapse — priced near-certain,
resolves 70%.

**That shape is the strongest lead in the exam.** It is the same signature as the Kalshi
prop-threshold settlement-collapse band (a settled post-game quote stamped as the line, resolving
far below its price), which the curve already excludes for player props via
`KALSHI_PROP_THRESHOLD_DEGENERATE_BAND` (>= 0.90). If entertainment is the same mechanism in a
different series family, the honest answer is a documented exclusion with its count — not a
recalibration. If it is *not*, that is a real miscalibration and more interesting.

Distinguishing them is a bounded query: for the 914 outcomes in that bucket, does the price move
before settlement, or is it a single stamped quote? **Needs a fresh prod window.**

### Free evidence nobody had collected — the `price_moved` split (CAL-P026, 2026-08-09 14:10 PT)

The published payload already carries `price_moved` on every bucket row, so the high-band cohort
can be split **without any new query at all**. Splitting kalshi entertainment's bucket 9:

| cohort | n | predicted | actual | error |
|---|---|---|---|---|
| `price_moved = true` | **816** | 95.1% | **67.5%** | **−27.5pp** |
| `price_moved = false` | 98 | 94.9% | 86.7% | −8.1pp |

**The collapse lives almost entirely on the MOVED side**, and the unchanged side is ~3.4x better
calibrated. That is consistent with the settlement-collapse mechanism rather than against it: a
settled post-game quote stamped as the closing line *is* a price that moved away from its opening,
so `price_moved` reads TRUE. (Stated explicitly because the intuition runs the other way — "a
single stamped quote" sounds like it should read as unchanged, and this window initially misread
it that way before checking what `price_moved` actually compares.)

It is **suggestive, not conclusive.** `price_moved` is `calibration_probability IS DISTINCT FROM
opening_probability` — it says a price moved, never *when*. The decisive question is whether the
close was captured after settlement, which needs snapshot timestamps and therefore still needs the
rail. What this does buy: a cheap, published discriminator that a future exclusion can be measured
against, and a reason to expect the answer to be an exclusion with a count rather than a
recalibration.

### polymarket cricket is ONE bucket, not a broad miscalibration

Same split, same payload. Cricket's 9.38pp/n=3,003 is concentrated, not diffuse:

| bucket | n | predicted | actual | error |
|---|---|---|---|---|
| b3 (34%) | **1,435** (48% of the cohort) | 33.6% | 33.7% | **+0.1pp** — well calibrated |
| b5 (52%) | 608 | 51.6% | 80.6% | **+29.0pp** |
| b2 (25%) | 263 | 25.6% | 9.5% | **−16.1pp** |

Nearly half the cohort sits in a well-calibrated bucket; the error mass is b5 (+29pp) with a
smaller opposite-signed b2 (−16pp). **Both directions appear on moved AND unchanged rows alike**
(b5: +30.7pp moved / +28.2pp unchanged), so unlike entertainment this one is *not* an artifact of
the closing-price capture — a defect that shows up equally regardless of whether the price moved
is a property of the population, not of the quote.

The bidirectional mid-band shape — a ~25% leg resolving ~10% and a ~52% leg resolving ~80% — is
what a **3-outcome market read as if it were 2-outcome** looks like: cricket carries draws /
ties / no-results, and a field whose third leg is systematically over-priced makes the other two
under-priced by the mirror amount. That is a concrete, falsifiable hypothesis and it is the first
one this exam has had for cricket. ~~**Untested**~~ — **TESTED AND CONFIRMED**, see below.

### ✅ CRICKET DIAGNOSED — 2026-08-09, window `7b21`; recorded here 2026-08-09 by CAL-P027

**The hypothesis directly above was right, and the confirming measurement already existed.** It was
taken by the window that exported the codex diagnosis bundle and, until now, lived only in
`.claude/handoff/CAL-DIAGNOSIS-BUNDLE-READY.md`. **Alex reads this document, not the handoff
directory** — so a confirmed diagnosis was sitting one directory away from the exam that calls it
untested. Recording it is the point of this entry; the measurement is not CAL-P027's.

| finding | figure |
|---|---|
| multi-winner 3-outcome cricket markets carrying a draw member | **0** of 556 markets (1,668 outcomes) |
| coherently-graded cricket markets carrying a draw member | **7,025** of 7,700 |
| independent questions behind the cohort (`vm_id` clusters) | 4,283 behind 15,812 outcomes (~3.7×) |

Draw-member capture predicts coherent grading almost perfectly. The cricket cohort reaching the
curve is precisely the set of markets **whose third leg we never captured** — so the field is
scored as if it were two-outcome, which is the shape the payload split predicted from the other
end. Both halves agree, and they were derived independently.

**Why they reach the curve at all:** the multi-winner exclusion (`nonexclusive_bundle_markets`) is
**census-only outside esports** — it counts these markets, it does not drop them.

**Verdict: `exclusion`, not `fix` and not "genuinely bad".** Per gotcha #21 this is read-side —
extend the exclusion, never re-grade a resolved population. Per the standing house rule the
extension ships **with its published count**.

**BLOCKED, and on the one thing everything else is blocked on:** an exclusion change alters what the
curve plots, so it carries a `CALIBRATION_POPULATION_VERSION` bump, which takes `/calibration` dark
until the next successful beat. No bump until the build publishes. This is diagnosis-complete and
fix-blocked, which is a different state from undiagnosed and should not be read as the same one.

⚠️ **Two caveats that will change conclusions if skipped**, from the bundle's own README: the
extract is **95.8% complete** (6,058 of 6,387 markets; one id window timed out even when split), and
the per-cell counts are the **RAW cohort, not the published cell** — cricket poly b5 is 1,947 raw
against 415 published, 48.9% vs 79.3% winrate. The published exclusions are strongly selective, so
the design effects transfer as an order-of-magnitude correction, not an exact one. **The published
count owed by the house rule must be computed on the published population, not from these rows.**

### 🟡 Entertainment — one MECHANISM is refuted; the timing rival is UNKNOWN (CAL-P030, corrected by CAL-P032 2026-08-10)

> **CORRECTION (CAL-P032, C258 item C).** This section previously read *"the rail ran, and it KILLED
> the stamped-settlement rival"*, and the scoreboard said **REFUTED**. That is an overclaim, and it is
> this lane's signature error in a new place: **density measures HOW MANY quotes were captured, never
> WHEN any of them was taken.** A cohort can be densely observed and still have its *final* quote
> taken after settlement — dense capture and late capture are independent properties, so no share of
> `density_band = "1"`, in either direction, is evidence about timing.
>
> What the measurement below genuinely establishes is narrower and still worth having: the
> **single-quote-only mechanism** is refuted. It does not establish that the timing rival is dead.
>
> **Timing verdict: UNKNOWN**, and that is a first-class answer rather than a shortfall.
> Adjudicating it needs two timestamps — a settlement time and a final-quote time — which the schema
> does not carry (`resolution_date` is a *scheduled* date; window 7b21 established this). The C258
> closure contract now encodes the rule directly: `evaluate_closure(...)["timing_verdict"]` is
> decided by **chronology alone** and returns `unknown` whenever either timestamp is missing, so this
> particular overclaim is no longer expressible in the rail.

The discriminator this section says it needs was walked on 2026-08-10 as part of item 1's
exhaustive census, and it answers against **one of the two mechanisms** it was built to test.

The single-quote signature is *a near-certain price carried by a single captured quote*. If that were
what makes kalshi entertainment miscalibrated, entertainment would be **enriched** in
`density_band = "1"` relative to kalshi's other categories. Measured on the complete walk:

| cohort | eligible n | density_band `1` | share |
|---|---|---|---|
| kalshi · entertainment | 15,624 | 1,028 | **6.58%** |
| kalshi · all other categories | 567,784 | 89,499 | **15.76%** |

**Lift 0.42x.** Entertainment carries single-quote outcomes at *two-fifths* the rate of its own
source's baseline — it is one of the better-observed kalshi cohorts, not a worse-observed one. And
`density_band = "0"` is **empty** (0 of 15,624): every eligible entertainment outcome was observed at
least once.

**So the two rivals are no longer symmetric — but not because one died.** The structural rival —
gotcha #17 threshold ladders reaching `calibration_probability` un-normalized, evidenced above by
market `6549959`'s 21 bands each priced 0.99 — is the only one with *positive* evidence behind it.
The timing rival has neither positive nor negative evidence, because nothing measured so far can
produce any.

**The scope of what the 0.42x lift refutes, stated exactly:** it refutes the mechanism *"these prices
are near-certain because each was captured exactly once, after the fact"*. It does not touch the
mechanism *"these prices were captured many times, and the last capture landed after settlement"* —
which is the timing rival proper. The earlier reading treated sparse capture as a proxy for late
capture; those are different properties, and the proxy was never licensed. **A cohort absolutely can
be observed densely and still be stamped after the fact**, which is the sentence the previous
version of this section implicitly denied.

**What would settle it, and why nobody can run it today:** a per-outcome comparison of the final
snapshot's `captured_at` against an authoritative settlement time. The schema carries no settlement
timestamp, so the measurement is not merely unperformed — it is unobtainable without new capture.
Recording that is the point: an exam item may not be marked green on a measurement that cannot be
taken, and it may not be marked red on one nobody attempted.

### Superseded — the pre-walk assessment, kept for the record

**Entertainment — still TWO live rivals, and CAL-P027's rail is what separates them**

Unchanged in substance: the structural half is evidenced, the timing half is not. Zero of the 1,107
bucket-9 rows are mex-normalized (`win_count` is 0 or 6–11, never 1), and the specimens are Kalshi
cumulative scalar-range ladders — market `6549959` carries **21 numeric bands each priced 0.99**
with `win_count = 0`, i.e. gotcha #17 surviving into `calibration_probability`.

**What is still not testable, and must not be reported as settled:** whether the close was captured
*after* settlement. There is no settlement timestamp in the schema — `resolution_date` is a
*scheduled* date — and quote chronology lives in `futures_odds_snapshots`, which the bundle did not
export.

**CAL-P027's rail supplies the discriminator without needing a settlement timestamp.** Its density
bands separate a single captured quote (`density_band = "1"`) from a long observation history, per
`(source, category)`. A near-certain price with **one** captured quote is the stamped-settlement
signature; a near-certain price with a long move history is not. That is a proxy — it narrows the
rival, it does not close it — and one walk of `overlap-trading-census` scoped to
`kalshi × entertainment` answers it.

---

## 4. Source graph redesigned — per-source panels, not overlaid lines

**Required proof:** rendered screenshot of the redesigned `/calibration` graph. Browser evidence.

**Status: 🔴 not started. Unblocked — stageable today.**

The legibility problem is quantifiable from the payload: the five sources differ by **28x in n**
(kalshi 420,594 · polymarket 191,738 · odds_api 14,960 · odds_api_totals 12,705 · odds_api_spreads
12,410) and by **3.3x in ECE** (kalshi 0.82pp · polymarket 2.72pp). Overlaid on one axis, the two
large sources dominate and the three sportsbook curves are unreadable — and the one comparison
that matters most (kalshi vs polymarket) is the hardest to see.

Per-source panels with a shared axis let a reader see both the shape and the size difference.

### 🟢 PASSED — photographed in production 2026-08-10 (CAL-P030)

Same run as item 2 (**`31431286342`**, manifest `result: pass` at `f6a40849`) — one dispatch
evidenced both items, because both live on `/calibration`.

**What the screenshot shows.** Five per-source panels, laid out as small multiples on a shared
0–100% axis, each captioned with its own sample size, its share of the curve, and its ECE:

| panel | outcomes | share of curve | ECE |
|---|---|---|---|
| Kalshi | 247,121 | — | 1.2pp |
| Polymarket | 81,199 | — | 4.4pp |
| Odds API | 14,960 | 3.8% | 1.4pp |
| Totals (Odds API) | 12,705 | 3.3% | 1.1pp |
| Spreads (Odds API) | 12,410 | 3.2% | 0.7pp |

The redesign does the thing the item wanted: the **28x spread in n** and the **~6x spread in ECE**
are both legible at a glance, where the overlaid version made five lines fight over one axis and
hid the fact that three of the five sources are ~3% of the curve each. Every panel carries 95% CI
error bars and renders thin buckets (n<1,000) as faded hollow dots — shown, never dropped.

**One detail worth recording, because ruling 003 predicted it.** The Spreads panel reads **0.7pp
ECE**, which is the *published* `by_source[].ece` — not a client re-derivation, which reads 0.6pp.
CAL-P025 was caught mid-build deriving this client-side and rewired to render the published figure.
The drift ruling 003 warns about is therefore live and visible on exactly one of five sources; the
page is on the correct side of it.

### Superseded — the pre-photograph assessment, kept for the record

**BUILT — CAL-P025, 2026-08-09, `program/calibration-23`**

The "All" tab of the By Source section is now small multiples: one panel per source, each drawn by
`CalibrationChart`, which fixes both axes at 0–100% **structurally** — so the shared axis is not a
convention anyone has to maintain. Selecting a source tab still gives the full-width chart, since
that is the view the per-bucket drill-in belongs to; the drill-in also works from any panel.

**The non-obvious half, and the reason this went through a tested function rather than inline JSX:
small multiples equalise panel AREA, which erases exactly the size difference the overlay conveyed
by accident.** A 12,410-outcome curve and a 420,594-outcome curve get identical frames and read as
equally authoritative. So `buildSourcePanels()` gives every panel its own **n, share of the curve,
and ECE**, and the panels are ordered largest-first.

#### Ruling 003 caught this mid-build, and it was right to

The panel ECE was first written as a client-side derivation from the same buckets. **Ruling 003
("clients format, never adjudicate", banked 2026-08-09 while this queue was being built) names
that exact thing as a failure**: *"dual ECE derivations — the same calibration number computed
twice, in two languages, which guarantees they drift."* The panels now render the server's
published `by_source[].ece` and print **nothing** where the payload published none, rather than
backfilling a client number into the gap.

**The drift is not hypothetical — it is already live on the payload production is serving:**

| source | published `by_source` | client-derived from the same buckets |
|---|---|---|
| kalshi | 0.8pp | 0.8pp |
| polymarket | 2.7pp | 2.7pp |
| odds_api | 1.4pp | 1.4pp |
| odds_api_totals | 1.1pp | 1.1pp |
| **odds_api_spreads** | **0.7pp** | **0.6pp** |

Four of five agree, which is precisely how a dual derivation survives review — it looks fine until
it doesn't, on one source, at one moment. Pinned by test.

**A pre-existing instance this surfaced, reported not fixed.** The *Source Comparison* table above
the panels still derives `srcECE` / `srcMCE` / `srcBrier` client-side, so on today's payload it is
showing **0.6pp for odds_api_spreads while `by_source` says 0.67pp**. That is the same violation,
older and wider (MCE and Brier are not published per source at all, so it cannot simply be
rewired). Fixing it means publishing those as typed backend decisions — which means editing the
precompute, which is frozen until the curve publishes. **Named here as owed, deliberately out of
this branch's scope.**

Pinned by test on the frozen payload: the five panels in order (kalshi 420,594 · polymarket
191,738 · odds_api 14,960 · odds_api_totals 12,705 · odds_api_spreads 12,410), reconciling to
652,407; shares summing to 1; the 28x span asserted directly; and kalshi's ECE below polymarket's
by more than 2x. A source with no outcomes is **dropped rather than drawn as an empty frame** —
an empty panel asserts "we measured this and found nothing", which is not what missing means.

New rail hooks: `calibration-source-panels`, and per panel `calibration-source-panel` carrying
`data-source`, `data-panel-n`, `data-panel-ece`.

**Still owed for GREEN: the rendered screenshot**, for the same reason as item 2 — the proof is
visual, and the rail that can take it grades production.

---

## 5. Native calibration surface consistent with web

**Required proof:** side-by-side — native surface and web `/calibration` showing the same
population version, the same generated-at, and the same headline figures. Rendered on both.

**Status: 🟢 PASSED 2026-08-09 (CAL-P026) — rendered on both surfaces, figures identical.**

### The proof

Both surfaces rendered against **the same production response** — `generated_at
2026-08-02T03:23:54.886392+00:00`, `population_version q267`. That is not a coincidence of timing:
production has been serving that one payload since 2026-08-02 (Item 0 of every window this week
re-confirms it), so a capture of web today and a render of the frozen 2026-08-02 fixture natively
are the same bytes, not two nearby snapshots.

| figure | web (browser rail) | native (`ImageRenderer`) |
|---|---|---|
| cohort / hero population | **389,385** | **389,385** |
| never-moved excluded | **263,022** | **263,022** |
| full population | **652,407** | **652,407** |
| markets | 534,269 | 534,269 |
| ECE · MCE | 1.5pp · 1.4pp | 1.5pp · 1.4pp |
| Brier | 0.165 | 0.165 |
| date range | Aug 2021–Aug 2026 | Aug 2021–Aug 2026 |
| stale banner | ✅ "Showing the last complete snapshot." | ✅ same sentence |

- **web** — `browser-audit.yml` run
  [31336823181](https://github.com/alexander-bain/bainluck/actions/runs/31336823181), pack
  `calibration`, `result: pass`, requested == observed frontend SHA
  `2a9f42b50fae93c33559cb680865967b04281c03`, backend `2a9f42b5`. Artifacts
  `calibration.anonymous.{desktop,mobile}.terminal.png`.
- **native** — `CalibrationParityTests.testProductionPayloadRendersTheStaleSurfaceForSideBySideEvidence`,
  which rasterises the real `CalibrationSurfaceView` from `CalibrationProdFixture` and prints its
  own parity line: `population=q267 contract=matched cache=stale
  generated=2026-08-02T03:23:54.886392+00:00 cohort_n=389385 full_n=652407 reconciles=true`.

**The flagged honesty risk is confirmed a FALSE ALARM, now with a picture rather than a source
read.** Native banners the stale payload in the same words web does.

### The one difference, and why it is not a defect

Web renders *"built Aug 2, 3:23 AM (8 days ago)"*; native renders *"built Aug 1, 8:27 PM (24h
ago)"*. Both are correct and neither disagrees about the instant:

- the **clock time** differs because both use a locale formatter and the two renderers sat in
  different zones (the CI runner in UTC, the simulator in PDT). `2026-08-02T03:23:54Z` *is*
  Aug 1, 8:23 PM PDT.
- the **age** differs because the native fixture is frozen with the `age_s` the server sent on the
  day it was captured (86,461 s ≈ 24 h), while web read today's envelope (~8 d).

This is exactly why the parity hooks publish the **raw ISO instant** rather than the formatted
string — a comparison of display text would have failed here on a timezone and passed on a wrong
number. Web's hook made the same choice; native's now matches it.

### What CAL-P026 had to build before the proof was possible

The exam predicted this item would be *"confirming correct behaviour, not finding a live bug"*.
On the honesty question that was right. But the item could not be *evidenced*, and the reason was
structural rather than cosmetic:

1. **Native never rendered the population version.** `CalibrationViewModel` decoded it,
   adjudicated it against `compatiblePopulationVersions`, and exposed `populationVersion` — and
   the View referenced 45 view-model properties, *not including that one*.
2. **Native had ZERO `accessibilityIdentifier`s on the entire surface**, while web publishes
   `data-population-version`, `data-cache-status`, `data-contract-state`, `data-generated-at`,
   `data-cohort-n`, `data-full-n` and the partition counts, with
   `calibrationAuditHooks.test.tsx` failing CI if one is dropped.

So the side-by-side could only ever have been a person comparing two screenshots — a check
performed once, on the day somebody cares, and drifting silently afterwards. **Web's own source
had already named this**, in the comment above its population-count hook: *"a native surface
reading the other one diverges silently. Both are published here as data so the parity check reads
numbers, not text."* The data was published for a consumer that did not exist.

CAL-P026 built it: `CalibrationViewModel.Parity` (one descriptor, read by both the hooks and the
tests, so there is no second derivation to drift — ruling 003), matching
`accessibilityIdentifier`s named with web's own testids, nine `CalibrationParityTests` pinning the
figures against the frozen production payload, and a three-test **cross-language** contract gate
(`frontend/e2e/contract/calibrationSurfaceParity.contract.test.js`) that fails when a native hook
is renamed away from web's testid or when the two fixtures stop describing the same response.

**So item 5 does not just pass — it stays passed.** A future divergence is a red CI run, not a
thing somebody notices in a screenshot months later.

### The one caveat worth stating

The native figures come from a **frozen fixture**, not a live device fetch, so this proves the two
surfaces AGREE ON A PAYLOAD rather than that native's networking is healthy. That is the right
scope — the exam asks whether the two surfaces describe the same data the same way — and the live
fetch path is covered separately by `CalibrationAvailabilityTests`. It is named here so nobody
reads more into the picture than it shows.

---

### Superseded — the pre-CAL-P026 assessment, kept for the record

**The specific fear was:** web renders the stale-tier banner (`data-cache-status`, "as of <time>
(N ago)"); if native does not, then during the current outage **native is showing a week-old curve
as current** — a "settled means settled"-class honesty failure on a second surface.

**In source, native already handles it:**

- `ViewModels/CalibrationViewModel.swift` — `isStale` (`data?.cache?.isStale == true`);
  `staleBannerDetail`, which *deliberately* falls back to the payload's own `generated_at` and then
  to a bare "earlier", so a stale payload whose envelope omits the date still banners rather than
  silently dropping it; `ageS` formatting; and a `populationVersionState` carrying an explicit
  `.mismatched` case.
- `Views/CalibrationView.swift:107` renders `staleBanner; refreshFailureBanner;
  partialDataBanner`, under the comment *"A stale curve is fine; a stale curve presented as live
  is not."*

**This does not make item 5 green.** The required proof is rendered side-by-side evidence that
native and web show the same population version, the same generated-at and the same headline
figures — that still needs the `xcodebuild` gate (gotcha #50) and a screenshot. But whoever takes
it should expect to be **confirming correct behaviour, not finding a live bug**, and budget
accordingly. The item is cheap and needs **no production credentials**, so it can run in any
window, including a tainted one.

Native gate: the canonical `xcodebuild` invocation, with `OTHER_SWIFT_FLAGS='$(inherited)
-Xfrontend -disable-sandbox'` (gotcha #50).

---

## 6. Monitoring proven by drill — observed firing, not merely merged

**Required proof:** the publish-age watchdog observed producing an alert with the failing phase
attached; the sentinel guards observed executing. Linked run output, not a merge SHA.

**Status: 🟢 WATCHDOG HALF PASSED — observed firing in production, 2026-08-09.**

**The drill was caught while the conditions were still live**, which was the time-sensitive part.
The check fired on its own, unprompted, against a genuinely broken publish.

**Proof — GitHub issue [#1604](https://github.com/alexander-bain/bainluck/issues/1604)**, filed
`2026-08-09T16:46:39Z` (09:46 PT), the FIRST live firing of the check:

| what Alex asked for | what production did |
|---|---|
| fires when a publish stops working | ✅ value **181.36 hours** against threshold `2` (`lte`) — 90x over |
| within ~2 hours | ✅ deployed ~08:47 PT, fired 09:46 PT, on its own schedule |
| auto-files a **P1** | ✅ labels `priority:p1`, `needs-agent`, `alert-intake` |
| **names the failing phase** | ⚠️ **partly** — see the gap below |
| doesn't spam | ✅ exactly one issue; the 24h Redis dedup held across ~12 runs |

The body's Evidence block named `terminal: cancelled`, `published: false`, **`phase: futures`**,
`phase_status: cancelled`, `duration_ms: 726557`, plus the four downstream phases as `pending`.

**The gap, and it is a real one.** CAL-P017 promised the issue would say *"phase futures, stage
`read:futures_population`"*. Production printed **`detail: ''`** and no stage at all, because:

- a phase **cancelled** by the build's own budget writes no `detail` (only a phase that dies on a
  statement timeout does — and since CAL-P016 the failure mode changed from timeout to
  cancellation, so the detail field went quiet exactly when the fix landed); and
- **the stage breakdown was never in `phases[]` to be read.** `record_stage` accumulates into a
  **top-level `stages` map**, so no query over `phases[]` could ever have named a stage.

Fixed in **CAL-P023**: the `context_query` now UNIONs the top-level `stages` map, ordered by cost.
On today's ledger that turns the alert from *"futures was cancelled"* into *"it spent 626s in
`read:futures_unit` and hit `staged:cursor_invalidate`"* — and that cursor line is the one that
distinguishes a build that is merely slow from one that is not converging.

**Verdict: the monitoring works.** It caught a real outage unprompted and routed it correctly;
the diagnosis was one level shallower than promised and is now deeper than promised.

The sentinel-guards half is **plumbing lane #1548** (ALEX-DECISIONS 2026-08-08 §4), routed there
by CAL-P017 Item 3 and explicitly out of this lane. The exam needs its evidence; the calibration
lane does not produce it.

---

## 7. Backfill recovery measurably progressing vs the 786K recoverable cohort

**Required proof:** two dated measurements of the recoverable cohort showing it shrinking, plus
the capture-floor re-measure on ~2026-08-15.

**Status: 🟡 BASELINE ESTABLISHED 2026-08-09 — the first datapoint now exists.**

### Baseline — reachability census walked to EXHAUSTION, 2026-08-09 10:47 PT, window `b2e4`

`POST /api/admin/repairs/reachability-census`, 7 calls, `exhausted: true`, `partition_ok: true`,
`partition_residual: 0`, `purge_horizon_days: 86`. Read-only rail; nothing was written.

| tier | outcomes | share |
|---|---|---|
| priced, in coverage | 1,672,620 | 58.58% |
| provably purged upstream (past the 86d horizon) | 384,820 | 13.48% |
| **unpriced but RECOVERABLE** | **797,871** | **27.94%** |
| unpriced, unknown age | 2 | ~0% |
| **total resolved outcomes** | **2,855,313** | 100% |

The four tiers sum to the population **exactly** (`partition_residual: 0`), so this is a
partition, not a sample — the census accounts for every resolved outcome it walked.

**This replaces "786K" with a measured number: 797,871.** That is the denominator item 7 must be
shown shrinking against. It also sets the honest ceiling on recovery: **13.48% of the resolved
population is provably gone** (gotcha #35's retention cliff) and can never be recovered by any
rail — so the achievable target is the 797,871, not the 2.86M.

**What item 7 still needs: a SECOND dated measurement.** "Measurably progressing" is a
derivative, and one point has no slope. The rail is cheap (7 calls, ~3 min) and re-runnable by
anyone, so the next window should simply re-run it and record the delta.

Two things gate actual recovery:

- **The largest recoverable prize needs a ruling.** 273,438 resolved Polymarket outcomes across
  ~133,576 markets carry no `resolution_source` at all, and **90.1% already have a calibration
  price**. CAL-P003 found both root causes (a candidate predicate that excluded the whole class —
  `bool_or` over all-NULL is NULL, never TRUE — and a Gamma **422** on `0x…` condition_ids
  misread as a rate limit, tripping the circuit breaker every run). **Nothing has been written;
  it needs Alex's authorisation before any recovery write.**
- **The capture-floor re-measure (#1586) waits on elapsed time**, ~2026-08-15 by Alex's date.

**AUTHORISED 2026-08-09 — bounded pilot.** Alex ruled: grade a capped batch (~5K outcomes),
attended, then **measure the effect on the published Polymarket curve and report before going
further**. Rationale: a full run could more than double the Polymarket curve (191,738 today), and
Polymarket is the worst-calibrated source — that is measured on 5K, not discovered on 246K.

The pilot must report: before/after ECE by bucket, the cleanly-resolvable vs ambiguous split
(sample says ~64.3% clean), and the disposition of the ~36% that do not resolve cleanly.

**First action, and it needs no ruling:** run the reachability census to exhaustion and publish
the baseline. It is a read-only rail that is already deployed, and without it there is no first
datapoint for "measurably progressing" to be measured against.

---

## Evidence log

Every claim above traces to a dated measurement. Add rows; never edit one.

| date (PT) | window | measurement | where |
|---|---|---|---|
| 2026-08-09 09:11 | c3f7 | `/api/calibration` 200 in 0.56s, `cache.status="stale"`, `reason="durable_over_age"`, `age_s=650830` | CAL-P020 report |
| 2026-08-09 09:11 | c3f7 | deployed `b4aa0039`; `calibration:main` last published 2026-08-02T03:23:54Z | CAL-P020 report |
| 2026-08-09 09:20 | c3f7 | staged cursor advancing — 4/128 units, `terminal=partial`, gen `5030f8f5` | CAL-P020 report |
| 2026-08-09 09:11 | c3f7 | per-source ECE: kalshi 0.82 · polymarket 2.72 · odds_api 1.35 · totals 1.10 · spreads 0.67 | payload `by_source` |
| 2026-08-09 09:35 | c3f7 | cohort ranking by error mass; cricket 9.38pp/n=3,003; entertainment 5.87pp/n=9,489 | items 3, 4 above |
| 2026-08-09 09:35 | c3f7 | matched-bucket `price_moved` split | item 2 above |
| 2026-08-09 10:36 | b2e4 | deployed `75dfee56` (INT-024); `prop-threshold-cliff-census` now live in `/api/admin/repairs` — CAL-P018's rail is deployed, unblocking CAL-P019 Item 0 | `/api/health`, `/api/admin/repairs` |
| 2026-08-09 10:36 | b2e4 | `/api/calibration` **200 in 0.98s**, `cache.status="stale"`, `age_s=655929` (7.59d) — CAL-P017's dated tier still carrying the page | payload `cache` |
| 2026-08-09 10:36 | b2e4 | publish still `2026-08-02T03:23:54Z`; census `status: "unavailable"`, `reason: "payload_predates_census"` | payload |
| 2026-08-09 10:40 | b2e4 | **watchdog drill PASSED** — issue #1604 filed 09:46 PT, value 181.36h vs threshold 2, P1 + `alert-intake`, one issue only; phase named, `detail` EMPTY, no stage | item 6; [#1604](https://github.com/alexander-bain/bainluck/issues/1604) |
| 2026-08-09 10:44 | b2e4 | ledger: `terminal=cancelled`, `plan.status=infeasible`, `floor_ms=1352317` over 10 observations (9 stale monolith timeouts + 1 staged run) | item "CAL-P016 convergence" |
| 2026-08-09 10:46 | b2e4 | ledger `stages`: `read:futures_unit` 626,242ms · `read:futures_generation` 25,752ms · **`staged:cursor_invalidate`** — one staged beat only, cross-beat retention UNOBSERVED | ibid. |
| 2026-08-09 10:47 | b2e4 | **reachability census to EXHAUSTION** — 7 calls, `partition_ok`, residual 0: 2,855,313 resolved · 1,672,620 priced · 384,820 purged · **797,871 recoverable** | item 7 |
| 2026-08-09 10:52 | b2e4 | volume coverage, 5M-id window: 20,117 resolved priced · 843 with `volume` (4.2%) · 797 `>0` | item 1 |
| 2026-08-09 10:52 | b2e4 | move-count over `futures_odds_snapshots` times out at 5M / 500K / **100K** ids; bare `COUNT(*)` on a 100K-id slice ALSO times out ⇒ tier 2 needs a rail | item 1 |
| 2026-08-09 10:53 | b2e4 | winner-field-coherence dry run, first 50K markets: 811 defects (`incoherent_field` 701 · `multi_winner` 142); politics 606 total but only **8** multi_winner | specimens above |
| 2026-08-09 11:15 | b2e4 | native DOES implement the stale banner in source (`isStale`, `staleBannerDetail`, `populationVersionState.mismatched`) — item 5's flagged honesty risk is likely a FALSE ALARM; rendered proof still owed | item 5 |
| 2026-08-09 11:20 | b2e4 | **the beat is NOT firing hourly** — watched 16:27Z→18:20Z: `failures_24h` stuck at 10, ledger generation stuck at 16:15:00Z, cursor stuck at 10 units @ 16:26:24Z. NEITHER the 17:15Z nor the 18:15Z beat ran | CAL-P016 convergence |
| 2026-08-09 13:07 | cae1 | `/api/calibration` **200 in 0.97s**, `cache.status="stale"`, `age_s=664868` (**7.70 d**) — publish still `2026-08-02T03:23:54Z`, census still `payload_predates_census`. Age is climbing monotonically (7.53 → 7.59 → 7.70 d across three windows today) exactly as CAL-P024 projected | items 1/3/7 blocked |
| 2026-08-09 13:07 | cae1 | deployed `30d10863` (INT-027); `git cherry` shows CAL-P024's three commits still outstanding ⇒ production still runs the census ON at ~632 s/unit | CAL-P024 |
| 2026-08-09 13:12 | cae1 | matched-bucket table **re-derived live from `/api/calibration`** and reproduces this document's 2026-08-02 figures to 0.1pp (b3 −0.9/−2.7 · b4 −1.4/−5.7 · b5 −1.6/−1.1) ⇒ items 2 and 4 need no publish | item 2 |
| 2026-08-09 13:40 | cae1 | **items 2 and 4 BUILT** — `compareMatchedBuckets` + `buildSourcePanels`; frontend suite **1,843 passed / 0 failed** (was 1,832), build clean, typecheck 84 = baseline. 7 mutations confirm every load-bearing rule | items 2, 4 |
| 2026-08-09 13:45 | cae1 | local Chromium **fails to launch** in the agent sandbox (`playwright-core` → "Target page, context or browser has been closed"), re-confirming that rendered evidence needs the remote rail against a deployed build | items 2, 4, 5 |
| 2026-08-09 14:05 | cae1 | **live dual-ECE drift**, published `by_source` vs client derivation on the same buckets: 4 of 5 sources agree at display precision, **`odds_api_spreads` 0.7pp published vs 0.6pp derived**. Panels rewired to render the published value (ruling 003); the pre-existing Source Comparison table still derives and is reported as owed | item 4 |

| 2026-08-09 14:06 | 8f3d | `/api/calibration` **200 in 0.66s**, `cache.status="stale"`, `age_s=668487` (**7.74 d**) — publish still `2026-08-02T03:23:54Z`, census still `payload_predates_census`. Fourth rising reading today (7.53 → 7.59 → 7.70 → 7.74 d) | items 1/3/7 blocked |
| 2026-08-09 14:10 | 8f3d | **kalshi entertainment b9 split by `price_moved`**: moved n=816 pred 95.1% act 67.5% (−27.5pp) vs unchanged n=98 pred 94.9% act 86.7% (−8.1pp) — collapse is on the MOVED side, consistent with settlement-collapse | item 3 |
| 2026-08-09 14:10 | 8f3d | **polymarket cricket is one bucket**: b3 n=1,435 (+0.1pp, well calibrated) · b5 n=608 (+29.0pp) · b2 n=263 (−16.1pp); b5's error is equal on moved and unchanged ⇒ population defect, not capture artifact | item 3 |
| 2026-08-09 14:11 | 8f3d | **the native gate RUNS in a program worktree** — `xcodebuild` fails resolving Firebase/gRPC binary artifacts (`dl.google.com` egress blocked), but `-clonedSourcePackagesDirPath <existing DerivedData>/SourcePackages -disableAutomaticPackageResolution` reuses the cached artifacts: `** BUILD SUCCEEDED **` | gotcha, below |
| 2026-08-09 14:22 | 8f3d | native suite **530 passed / 0 failed** (was 521); contract suite **311 / 0** (was 308); both new gates non-vacuous by mutation | item 5 |
| 2026-08-09 14:26 | 8f3d | **item 5 side-by-side PASSED** — browser-audit run [31336823181](https://github.com/alexander-bain/bainluck/actions/runs/31336823181) `result: pass`, frontend SHA requested == observed `2a9f42b5`; native `ImageRenderer` render of the same payload. 389,385 · 263,022 · 652,407 · ECE 1.5pp · MCE 1.4pp · Brier 0.165 identical on both; both banner staleness | item 5 |

| 2026-08-09 15:10 | 7b21 | **cricket identified** — every multi-winner 3-outcome cricket market has `draw_member_count = 0` (1,668 outcomes / 556 markets); coherently-graded ones carry a draw member 7,025 of 7,700. Reaches the curve because `nonexclusive_bundle_markets` is census-only outside esports. Extract 95.8% complete; per-cell counts are RAW not published | item 3 (recorded here by CAL-P027) |
| 2026-08-09 21:39 | e5b2 | `/api/calibration` **200 in 0.62s**, `cache.status="stale"`, `age_s=695807` (**8.05 d**) — publish still `2026-08-02T03:23:54Z`, census still `payload_predates_census`. **Sixth** rising reading (7.53 → 7.59 → 7.70 → 7.74 → 7.76 → 8.05) | items 1/3/7 blocked |
| 2026-08-09 21:41 | e5b2 | deployed `f78b8a6d` == `origin/master`, single-valued (the 7b21 two-dyno skew has cleared). **CAL-P024 still unmerged, verified by CONTENT** — `origin/master` still reads `COVERAGE_CENSUS_ENABLED = True` ⇒ production still builds at ~632 s/unit and ruling 009's baseline has not landed | CAL-P024 |
| 2026-08-09 21:45 | e5b2 | `futures_outcomes` = **3,237,030 rows across a 218,050,432-wide id space**; the bare `COUNT(*)` took **9.93 s against a 10 s timeout**. An 8M-id window at the dense head TIMED OUT; a 550K-id window returned in 0.47 s ⇒ row-bounded windows, re-confirmed | item 1 |
| 2026-08-09 21:50 | e5b2 | volume coverage is **not one number**: 14.2% (recent 550K ids, n=8,509) · 4.5% (mid, n=2,759) · 4.2% (old tail, from 10:52 above). **`volume = 0` did not occur once** in any window — every volume-bearing row was `> 0` | item 1 |
| 2026-08-09 21:52 | e5b2 | futures market population by source: polymarket **553,876** · kalshi **191,114** · datagolf 300 · **odds_api 12** ⇒ the multi-bookmaker case is rare, but DataGolf's write-time `reading_count` dedup means `COUNT(*)` is not observation density | item 1 |
| 2026-08-09 22:30 | e5b2 | **item 1's rail BUILT** — `census_overlap_trading.py` + `overlap-trading-census`; full backend **12,154 passed / 0 failed** (was 11,785), ruff clean, **12 mutations** each caught. N still UNMEASURED: first walk owed post-merge | item 1 |
| 2026-08-09 22:45 | e5b2 | **CAL-P024 MERGED AND DEPLOYED mid-queue** — master `ff627a39` (CAL-P024a/b/c, #1479), `/api/health` = `ff627a39`, and `COVERAGE_CENSUS_ENABLED = False` confirmed by content on `origin/master`. Supersedes the 21:41 reading in this log. **Ruling 009's baseline has landed; the ~13-beat count can start.** Publish still `2026-08-02T03:23:54Z` — the SLO stays RED until the build walks 128 units | ruling 009; SLO |
| 2026-08-09 22:47 | e5b2 | `git merge-tree origin/master program/calibration-25` = **clean**, no conflict, despite master's CAL-P024 also editing this document — its edits land in the convergence section, between this queue's | CAL-P027 hand-off |

## A gotcha this window measured — the native gate is NOT unavailable in a program worktree

Gotcha #50 covers the SwiftUI `#Preview` macro-sandbox failure and its
`-Xfrontend -disable-sandbox` fix. There is a **second, different** blocker that hits any
*fresh* worktree, and it looks like a hard wall:

```
failed downloading 'https://dl.google.com/firebase/ios/bin/grpc/1.69.1/rc0/grpc.zip'
  which is required by binary target 'grpc': downloadError("The request timed out.")   ×11
```

The git-based SPM packages are cached (`~/Library/Caches/org.swift.swiftpm/repositories`), but the
**binary** targets are zips fetched from `dl.google.com`, and that egress is blocked. A program
worktree at a new path gets a new DerivedData hash, so it re-resolves from scratch and dies here —
which reads as "iOS cannot be gated from this lane".

It can. The artifacts are already extracted under an existing DerivedData:

```
xcodebuild -scheme "Bain Luck" -destination 'generic/platform=iOS Simulator' \
  -clonedSourcePackagesDirPath ~/Library/Developer/Xcode/DerivedData/Bain_Luck-<hash>/SourcePackages \
  -disableAutomaticPackageResolution \
  OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' build
```

Both flags are needed: the first points at the cached artifacts, the second stops SPM trying to
re-resolve anyway. **Do not delete the SPM cache to "start clean"** — gotcha #50's existing warning
applies with double force here, since the artifacts cannot be re-downloaded at all.

## Open questions for Alex

**All three are ANSWERED as of 2026-08-09** (PRODUCT-BRAIN § RULINGS 2026-08-09(b)):

1. ~~Ruling 9 = Option A?~~ → **Ruled directly**, and more precisely than A: the volume /
   hardened-movement / unknown ladder. The inference is retired, not confirmed.
2. ~~Polymarket recovery write?~~ → **Bounded pilot first** (~5K, attended, curve impact reported
   before going further).
3. ~~Three-winner scope?~~ → **Pause; 10 eyeballed specimens per category first.** Plus the lane's
   own correction: the 1,885 multi-winner extension was already granted on 2026-08-08, and the
   3,585 figure mixes in `incoherent_field` (bad PRICES), which the winner rail cannot fix at all.
   **→ SPECIMENS DELIVERED 2026-08-09, below. Alex's call is now unblocked.**

---

## Specimens for Alex — the winner-field defects (#1527), 2026-08-09 window `b2e4`

`POST /api/admin/repairs/winner-field-coherence?limit=200000`, **dry run, nothing written.**
First 50,000 markets walked (`next_offset` 5,990,949 — this is a leading slice, not the
population): **811 defect markets**, `incoherent_field` 701 · `multi_winner` 142.

### The split Alex's politics concern turns on

| category | ALL defects | of which `multi_winner` |
|---|---|---|
| **politics** | **606** | **8** |
| basketball | 54 | 51 |
| entertainment | 31 | 16 |
| soccer | 24 | 10 |
| tennis | 20 | 20 |
| economics | 15 | 12 |
| golf | 8 | 8 |

**Politics is 75% of all defects and 5.6% of the actionable ones.** The 606 politics rows are
almost entirely `incoherent_field` — bad *prices* — which the winner rail cannot fix and does not
touch. Only **8** politics markets are `multi_winner`. The rail additionally fails closed (it
writes only where the CLOB returns exactly one winner), so politics is protected twice over.

### Specimens — genuine single-winner markets carrying multiple winners

`legs` = outcomes, `win` = outcomes flagged `is_winner`, `sum` = field probability sum.

**basketball** (51) — 3-leg first-half markets with 2 winners; prices sane, winners wrong:
| mkt | legs | win | sum | name |
|---|---|---|---|---|
| 949075 | 3 | 2 | 1.985 | New Mexico vs Nevada: First Half Winner |
| 949109 | 3 | 2 | 1.54 | Auburn vs Oklahoma: First Half Winner |
| 949199 | 3 | 2 | 1.60 | Marquette vs Georgetown: First Half Winner |
| 1193982 | 3 | 2 | 1.90 | Florida vs Texas: First Half Winner |
| 460 | 68 | 3 | 3.65 | Women's Championship: South Carolina vs UCLA |

**politics** (8) — large fields where ~all legs are flagged winner AND priced ~1.0:
| mkt | legs | win | sum | name |
|---|---|---|---|---|
| 112920 | 26 | 21 | 21.0025 | Next Prime Minister of Hungary |
| 114000 | 37 | 28 | 28.0105 | Assam Legislative Assembly Election Winner |
| 114010 | 37 | 28 | 28.0045 | Kerala Legislative Assembly Election Winner |
| 5973861 | 14 | 13 | 13.00 | Next President of Benin |

**tennis** (20) · **entertainment** (16) · **economics** (12) · **golf** (8):
| mkt | legs | win | sum | name |
|---|---|---|---|---|
| 114033 | 61 | 28 | 28.04 | 2026 Men's Australian Open Winner |
| 2954775 | 4 | 4 | 2.00 | Zizou Bergs vs Tommy Paul: Exact Match Score |
| 113177 | 37 | 28 | 28.009 | Most popular boy name 2025 |
| 3649032 | 15 | 15 | 7.425 | Top Global Song on Spotify on Mar 10, 2026? |
| 1460213 | 30 | 2 | 3.00 | S&P price range on Feb 26, 2026 at 4pm EST? |
| 2622557 | 40 | 40 | 19.80 | Steel price on Mar 31, 2026 at 5pm EDT? |
| 110593 | 147 | 55 | 51.385 | Kenya Open End Of Round 1 Leader |

### The finding worth Alex's attention: these are TWO different bugs

- **Signature A — "the whole field got graded true."** `winners ≈ field_sum` to two decimals
  (21/21.0025 · 28/28.0105 · 13/13.00 · 40/19.80's cousins). Every flagged leg is *also* priced
  ~1.0, so both the winner flag and the price were mass-set. Dominates politics, entertainment
  and the big tennis/golf fields.
- **Signature B — "one extra winner on a sane field."** 3 legs, 2 winners, `sum` ≈ 1.5–2.0. The
  prices are believable; only the winner flags are wrong. Dominates basketball/soccer first-half
  and the small tennis markets.

**These plausibly need different fixes**, and the ladder currently treats them as one cohort.
Signature B is the clean case for CLOB re-resolution. Signature A markets are *also* carrying
impossible prices, so re-resolving the winner alone leaves a field summing to 21.0.

**Alex's decision is now unblocked.** Nothing has been written; the rail remains paused.

Nothing is currently blocked on Alex. Every remaining item is blocked on a fresh production window,
on the publish converging, or on elapsed time.

### The one thing that would change this

If N turns out unmeasurable — i.e. too few rows carry BOTH volume and adequate snapshot density to
validate the proxy — then tier 2 has no empirical basis and item 1 comes back with a real choice
(ship tier 1 + unknown only, or keep the old bar). Flagged now so it is not a surprise later.
