# CAL-P154 — the statement was bounded, the walk was not

**Pillar: TRUTH. Ship: the published calibration curve stops being able to go out
~96,026 outcomes short without saying so.**

This file is the state for THIS session only. `artifacts/cal-p153/README.md` is the
state for the window and the supervisor finding; `cal-p152`'s **§7** remains the
state for the twelve code commits; `cal-p151`'s for the nine beneath them;
`cal-p150`'s for the five original commits.

---

## TL;DR

Step 1 of the queue was "poll the Integrator, and poll `CERT-QUEUE.md` for a cert
staged against `fef05751`". Both polls came back empty — the Integrator was on
`INT-172` and no such cert existed — so the queue's own fallback applied: staging
it is this lane's job.

**Instead of staging a cert against unchanged code, this session reproduced the
`CERT-457` finding, found it real, and fixed it.** Staging a re-grade of bytes a
cert already blocked is the measure/file/re-measure trap; the block named a
specific mechanism, and the mechanism was checkable.

1. 🔴 **`CERT-457` WAS RIGHT, TO THE DIGIT.** The pre-fix source issues **2,047
   timed queries** and logs **`1024/1024 chunks irreducible ... at depth 10`**.
   Arrived at independently, by mutation, not by reading the block.
2. **Fixed at `9f139d3d`, guard repaired at `7b401286`, `CERT-510` staged.**
3. 🔴 **One of my own guards was VACUOUS and I only caught it by mutating.** §3.
4. **The four session instruments all exit 0; nothing moved.** §5.

---

## 1. The defect, and why "safe" was not "fine"

`_CHUNK_TIMEOUT_S` (45 s) bounds one **statement**. Nothing bounded the
**traversal**, and the two are different quantities.

A calendar month is ~2.68 Ms. `_slice` halves on timeout until
`span <= _CHUNK_MIN_SPAN_S` (3,600 s), which bottoms out at depth 10 —
2.68 Ms / 2^10 = 2,615 s — giving **1,024 leaves under 2,047 timed nodes**. At
45 s each that is ~92 ks of querying inside an 1,800 s task.

The 600→1800 soft-limit raise was argued on:

> *"no single statement can run longer than `_CHUNK_TIMEOUT_S` (45 s), so the
> longest uninterrupted operation is bounded far below the limit"*

That sentence is **true**, and it is about the wrong quantity. It bounds a node.
What consumes the task is the tree. This is the whole lesson of the session:
**a bound on the part is not a bound on the walk over the parts.**

**Why a safe kill is still a defect.** The kill was never a data hazard — the one
`setex` lands after every slice, so nothing partial is published, and the raise's
second clause said so correctly. But safe is not diagnosed:
`SoftTimeLimitExceeded` unwinds before the terminal contract can be written, so
**the one run that knows what went wrong is the run that never gets to say.** Key
unwritten, 24 h TTL lapses, the publish outage the lift exists to END is
preserved, DB loaded for nothing — every six hours, indefinitely. An absence
nobody can attribute is precisely the failure this function was rewritten to stop
producing.

## 2. The fix

* `_TRAVERSAL_BUDGET_S = 1620.0` — 180 s margin under the 1,800 s beat. The margin
  must exceed the 45 s statement that can still be in flight past the final check.
* Checked at the **top of `_slice`** — the one site covering both ways the walk
  spends wall (issuing a statement, and recursing after one timed out). A check
  at the grid loop would bound the number of **cells** and leave the 2,047-node
  fan-out **inside** a cell untouched, which is the shape that actually consumes
  the task.
* **Two callers, two zeros.** Standalone it owns an 1,800 s beat; as the
  `bookmaker_closing` phase it has what is left of an 840 s task. The phase now
  passes `deadline=_pipeline_start + _SOFT_LIMIT_S - _BUDGET_MARGIN_S` — the
  convention already at three other call sites — and the existing tested
  `_effective_stop_at` takes the earlier. This also protects the pipeline:
  pre-fix an unbounded walk could blow the 840 s wall and kill every phase after
  it.
* **`unrun` is not `irreducible`.** Separate list, separate terminal message.
  Both fail closed, but irreducible means a window will not answer however narrow
  it gets, and unrun means the walk ran out of wall. Pooling them would report a
  database problem every time the task was merely slow.

**Deliberately declared as a judgement call, not a measurement** (and flagged to
the grader): the phase can now enter with ~0 s before its handed-down wall and
mark every cell `unrun`. I judged that better than an unbounded walk that can
take the pipeline down, and the standalone beat is the primary drain by design.
**It is the most likely thing in the change to be wrong.**

## 3. 🔴 One of my own guards was vacuous, and only mutation found it

`test_the_phase_caller_hands_down_the_pipelines_wall` first asserted a **substring**
over `inspect.getsource(_backfill_all_winners)`. That function hands the identical
`deadline=_pipeline_start + _SOFT_LIMIT_S - _BUDGET_MARGIN_S` expression to
**three other callees**, so the string is present whether or not the bookmaker
call site has it. Measured: deleting the argument entirely left the guard **green,
exit 0**. It was asserting a fact about the neighbours.

Re-anchored on the AST — find the single `Call` node whose func is
`_precompute_bookmaker_calibration`, assert exactly one, assert a `deadline`
keyword, assert `ast.unparse` of it equals the pipeline's wall. Re-run against the
same mutation: **EXIT 1**.

**This is the session's second lesson and the more transferable one: I wrote the
guard, believed it, and it was worthless. What found it was mutating the thing the
guard watches.** The other three guards in this change are the same class of risk
and only this one was caught, which is why the cert block says so out loud rather
than presenting four guards as four proofs.

A near-miss worth recording: the first mutation-revert ran `git checkout` from
`backend/`, the pathspec did not resolve, and the source stayed mutated — the
`RESTORE MISMATCH` check is the only reason that did not become a committed
mutation. **Verify a revert by hash, never by having typed the revert.**

## 4. Evidence

| gate | result |
|---|---|
| full backend suite @ `7b401286` | **22,173 passed / 129 skipped / 61 xfailed, EXIT 0**, 916.14 s |
| red-first (bound removed) | **2 failed / 31 passed, EXIT 1**; restored byte-identical `41fa8a05` |
| red-first (phase caller drops the wall) | **EXIT 1**; restored byte-identical |
| focused file | 33 passed · startup smoke 4/4 |
| CI @ exact head | `CI 33342775898` · `CodeQL 33342775906` · `gitleaks 33342775899` — all success |
| ruff | unchanged vs `255fcc16`: 2 F811 + 6 F841, all pre-existing |
| ruling 063 ledger | `digest=33fee2691a40 mtime=2026-08-28T21:58:51Z claims=121 deviations=0 dropped=0` |

**Nothing is deployed.** The branch is not an ancestor of master and the board
still reads **1.88 pp on q268**. No headline was taken and none was available.

## 5. The instruments, and the ring

All four session instruments exit 0, nothing moved:

* `board-d15.py` — every cell named by the 2026-08-30 batch present and placed
* `promotion-datapoint.py` — headline **HELD** at 1.88 / q268; the one permanent
  loss (beat 14) still stands, unrecoverable
* `refusal-register.py` — 13 of 20 live seats under a documented refusal
* `window-beat-margins.py` — **21 gauged / 21 agree / 0 disagree**; beat 19 still
  the tightest CLEAN margin at 2,691 ms

Both daemons advancing, zero restarts: render banker (75909/75911, 15 censuses
banked), serve-phase probe (37525/37527). The rebaseline watcher and its
supervisor remain retired per CAL-P153 — **do not rebuild the window until the
lift deploys**, and when you do, give the watcher a lane-unique argv token.

## 6. What is still open

* **`CERT-510` is staged, not graded.** Poll it. If it blocks, the finding is the
  work.
* **`CAL-P151-P1a`** — the P1-a exclusion magnitude, parked by name. Untouched.
* **The legacy Redis-key detector classification** (D21's 21→22
  `uncovered_sql_shaping`). Untouched, and deliberately so.
* **`alex-inbox/calibration-919`** — the D13 per-market/per-variant call.
* **E2's scope** — still not derivable; it needs the deployed repaired population.
