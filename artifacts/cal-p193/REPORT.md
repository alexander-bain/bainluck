# CAL-P193 — the successor question, run and CLOSED NEGATIVE

**Session:** 2026-09-01 ~17:0x–17:3xZ / ~10:0x am PT. Directive `963` (self-staged by P192).
**Lane state:** read session. No build directive arrived. `960` D-G freeze in force.
**Verdict in one line:** the question P192 named as its successor **does not generalize** — it was
run to exhaustion over the frozen module and produced **one already-known hit and no new ones**. The
transferable yield is the *discriminator* for why, plus one new latent zero-conflation found on the
way, and the closure of standing question #4.

---

## 1. State (measured this session)

| thing | value | vs P192 |
|---|---|---|
| input fingerprint (live == local predictor) | `e2040f90154fae876f0fb65f5abf74c3` | unchanged — **no fifth reset**, 28 sessions |
| `origin/master` | `9eb9e086` | 🆕 **MOVED** from `35c50d48` |
| `git diff --name-only 7d066c50 origin/master \| grep -i calib` | empty, exit 1 | **ALL-CLEAR holds** |
| ledger `updated_at` | `2026-09-01 16:32:11.447482+00:00` | unchanged (4th session running) |
| published curve | `generated_at 2026-08-31T04:37:36Z`, `mce_closing_line 1.86` | unchanged, 28th session |
| branch HEAD | `9316b22f`, pushed, **NOT merged** | unchanged |

**Master moved but is inert for this lane.** The two commits are
`9eb9e086` (integrator cert-eligibility tooling) and `769a8633` (lane launcher scripts); the changed
paths are `.gitignore`, `CLAUDE.md`, `lane4-runner.sh`, `lanes-supervisor.sh`,
`scripts/cert_merge_eligibility.py`, `start-lanes.sh`. **No calibration path.** No warning owed to
any lane. Re-verify with the one-command diff after any further move — do not assume it stays clean.

**ETA to publish: `09-02T08:30–09:30Z`, unchanged and not re-derived** (nothing moved).

---

## 2. THE SUCCESSOR QUESTION — run, and it is SPENT

> *"This comment states a fact about production. Is it still true?"*

P192 named this after `precompute_calibration:4370` ("`staged:beats_to_publish` is absent from every
ledger") was disproven in one query by the live `stage_counts`. The module is frozen under ruling
009, so the premise was: *every* comment in it describes the world as of the freeze and none has
been re-checked. Ran the directive's named sweep over all **8,368 lines**.

### 2a. The sweep, exhaustively

| pattern | hits | result |
|---|--:|---|
| `which is why` | **6** | 1 = the known 4370. **The other 5 hold.** |
| `so that` | 1 | contract, cannot drift |
| `because` | 72 | filtered to claim-shaped; **none** undated-present-tense about live state |
| absence class (`absent from`/`never fires`/`dead code`/`never reached`/…) | 7 | 1 known (4370), 1 historical-analysis, 4 architectural, 1 verified-still-true |

**The five surviving `which is why` claims:**

* **1853** — the `is_winner` invariant. **Re-measured live, see §2b. HOLDS.**
* **2016** — "two-competitor duels, which is why the shape classifier exists" — definitional.
* **3808** — "/api/calibration was serving a 26h-stale…" — a dated historical incident.
* **4370** — P192's. Already disproven, already parked (`P192-1`), already guarded.
* **5376** — "which is why their silent absence took ~96,026 outcomes out of the candidate" — a
  dated post-mortem of the D21 outage, correctly past-tense.
* **6954** — "the run's budgets are derived from it — which is why no budget is invented here" —
  an internal contract.

### 2b. The two claims that were genuinely checkable, both re-measured

**(i) The cross-file config claim — `precompute_calibration:482`.** It asserts a fact about a
*different file*: "the beat's ONLY prior bound was Celery's hard `time_limit=1560s`", and the
backstop `_MAIN_COMPUTE_STMT_TIMEOUT_MS = 1500 * 1000` is "set at the soft limit (< the 1560s hard
limit)". This is the most fragile shape a comment can have — it decays whenever *someone else's*
file changes. **Verified STILL TRUE:** `app/tasks/__init__.py:3095` reads
`@celery_app.task(bind=True, soft_time_limit=1500, time_limit=1560, name="app.tasks.precompute_calibration_main")`.

> ⚠️ I also chased the arithmetic — the Postgres cancel is 1500 s from **statement** start while the
> SIGKILL is 1560 s from **task** start, so the up-front `SET LOCAL` can only beat the SIGKILL if the
> statement begins within 60 s of task start, which the 967.5 s of untimed overhead at line 6747
> makes doubtful. **This is a non-finding: the code already says so and already fixes it.** The
> comment at 6687-6692 states the up-front `SET LOCAL` "remains the floor for the no-runner path;
> with a runner, each phase re-applies a tighter bound derived from the time actually left before
> the absolute deadline (`PhaseRunner.apply_statement_timeout`)", and re-arms after each commit
> clears the transaction-local setting. The live path has a runner. **Recorded so the next session
> does not re-walk it.**

**(ii) The quantitative invariant with a live consequence — `precompute_calibration:1849-1853`.**
It is the stated reason for two standing decisions: that `resolution_source IS NOT NULL` (not
`is_winner IS NOT NULL`) is this repo's canonical grade predicate, and that CAL-P156's "rung 1b"
is dead code and **must not be re-added**.

```sql
SELECT count(*) AS total_outcomes,
       count(*) FILTER (WHERE is_winner IS NULL) AS iw_null,
       count(*) FILTER (WHERE is_winner IS NULL AND resolution_source IS NOT NULL) AS iw_null_but_graded,
       count(*) FILTER (WHERE is_winner = false AND resolution_source IS NULL) AS false_ungraded
FROM futures_outcomes
```

| | comment (measured 2026-08-31) | live (2026-09-01) | verdict |
|---|--:|--:|---|
| total outcomes | 3,893,126 | **3,909,256** | drifted +16,130 |
| `is_winner IS NULL` | 2,536 | **3,142** | drifted +606 |
| …of those, ALSO graded | 0 (the "EVERY ONE" claim) | **0** | 🟢 **INVARIANT HOLDS** |
| `is_winner=false, resolution_source NULL` | 778,306 | **702,252** | drifted −76,054 |

🟢 **The load-bearing half is intact.** The censuses drifted — expected, and the comment *dates
itself*, which is exactly why its drift is not a defect. **"Do not re-add rung 1b" stands.**
*(The −76,054 in one day is `backfill_winners` grading rows, ~4 runs at 6-hourly. Ordinary.)*

### 2c. 🔴 THE DISCRIMINATOR — the actually transferable result

**4370 was the only comment in 8,368 lines that was simultaneously all three of:**

1. **present-tense**, 2. **undated**, and 3. about **runtime/ledger state** — not schema, not a
contract, not a dated observation.

Every other claim-shaped comment in the frozen module is one of: a dated measurement (which declares
its own staleness and is therefore honest), an architectural contract (which cannot drift), or
design rationale about a pre-fix state (correctly past-tense). **That triple is why 4370 rotted and
nothing else did.**

🔴 **So: DO NOT RE-RUN THIS SWEEP ON `precompute_calibration.py`. It is exhausted.** The question
retains value only as the *triple* above, applied to a file nobody has swept — and note the frozen
module was the best candidate precisely because ruling 009 stops anyone from updating its comments.
An unfrozen file's comments get corrected in passing. **Expect lower yield anywhere else.**

---

## 3. Standing question #4 — ANSWERED, and now also exhausted

> *"Is this value CARRIED ACROSS BEATS, or beat-local?"* (trap 24, P189 — paid twice already:
> `unit_worst_history`, then `floors`.)

The directive named the last three untested candidates: `stage_ok_maxima` / `stage_ok_totals` /
`stage_ok_counts`.

**Answer: all three are BEAT-LOCAL, and beat-local BY DESIGN. No defect.**

* They are plain instance attributes — `calibration_phase_ledger.py:1220-1228`, `self.stage_ok_totals`,
  `self.stage_ok_counts`, `self.stage_ok_maxima` — initialized empty in `__init__`.
* **Independently confirmed against the live ledger:** the payload has **24 top-level keys** and none
  of the three is among them (`banked, carried, checkpoint_action, checkpoint_write,
  completed_required, elapsed_ms, floors, generation, history, input_fingerprint, outcome, owner,
  phases, plan, population_version, schema, session_identity, stage_counts, stages, task, terminal,
  unit_costs, unit_worst_history, unmeasured_overhead_ms`). They are never persisted.
* **And the docstrings already say so, in the right words.** `stage_completed_max_ms` is documented
  "Worst COMPLETED ``name`` stretch **this beat**"; `stage_completed_mean_ms` is "Mean cost of one
  COMPLETED stretch". The consumers agree — the fence model's cross-beat term is the *carried* ring
  (`unit_worst_history`), and its beat-local term is `this_beat_worst`. **The two kinds are kept
  apart deliberately.**

🔴 **Question #4 is now EXHAUSTED**: every named candidate is answered — `unit_worst_history`
CARRIED, `floors` CARRIED, `stage_ok_*` BEAT-LOCAL-by-design. **Do not re-ask it without a new
candidate.**

---

## 4. 🆕 One new finding: the same zero-conflation as P192, one file over — LATENT

`calibration_phase_ledger.py:1299`, in `stage_completed_max_ms`:

```python
count = self.stage_ok_counts.get(name, 0)
if count <= 0:
    return None
return self.stage_ok_maxima.get(name, 0) or None    # <-- the `or None`
```

The `count <= 0` guard has already established that **at least one stretch of this name completed**.
The `or None` then re-conflates: a stage that completed in **0 ms** yields `stage_ok_maxima[name] == 0`,
which is falsy, so the accessor returns `None` — documented as *"nothing of that name finished"*.

🔴 **The two accessors then contradict each other about the same beat:** `stage_completed_count`
returns `1` while `stage_completed_max_ms` returns "nothing finished". 0 ms is reachable in
principle because `record_stage_outcome` floors with `ms = max(0, int(duration_ms))` — **the exact
line P192 caught destroying the `-1` sentinel**, one accessor away. Same class: *a falsy zero in the
ledger standing in for absence.*

🟢 **Latent, and measured to be so — not assumed.** All three consumers pass one stage name only,
`STAGED_UNIT_STAGE` (`calibration_main_build.py:1569, 1570, 1638, 1668`), whose live completed mean
is **56,431 ms**. A 0 ms unit read is not a thing. **No user-visible effect, today.**

🔴 **Do not fix it.** It is a fold's call under ruling 134, and the file is inside the rebuild's
blast radius while D-G is in force. Parked as **P193-1**.

---

## 5. What did NOT happen, deliberately

* **No build.** No directive staged one; `960` D-G is in force; ruling 134 says an idle build lane
  is a legitimate outcome. P175–P189 were idle and all fifteen were correct.
* **No merge, no cert, no deploy.** Branch `9316b22f` stays pushed-and-unmerged per `920`.
* **No fix for §4.** See above.
* **No re-derivation of the fence model, the ETA, or the publish streak.** All three are settled and
  the directive forbids it.
* **No `YOUR-TURN.md` edit** — nothing this session changes an Alex-ask or its default.
* **The P185 datagolf discriminator was NOT re-run** — six consecutive zeroes, no scheduled trigger
  fired, and the directive says run it before grading a publish, not every hour. No publish to grade.
