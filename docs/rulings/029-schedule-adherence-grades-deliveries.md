# RULING 029 — Schedule adherence grades DELIVERIES; a gate-skip is healthy

date: 2026-08-11
author: Alex
via: latency program, LAT-P039 report / LAT-P040 staging
issues: #1716, #1609
relates: ruling 021 (two graders reading one input must share the DECISION — same family: a verdict is only as good as what its numerator counts), ruling 026 (freshness is one architecture, not five mechanisms)

A beat-scheduled task is **`on_schedule` if celery DELIVERS it at its beat interval.** That is the
whole question the adherence surface asks, and `task_prerun` counting measures it directly.

**A gate-skip counts as healthy.** A task whose body declines its own fire — an adaptive interval,
a quota guard, a "nothing to do" early return — was still delivered on time. The scheduler did its
job. Whether the body chose to work is a different question, already answered by `task_verdict`.

`never_completes` stays as a **flag**, not a verdict. A task that fires and never reaches a
terminal (`precompute_interestingness`: 10 starts, 0 terminals) stays visible on the work-list
independently of its schedule grade.

## WHY

The numerator was asking the task's permission.

`record_task_started` documents itself as counting "fires that BEGAN", but it is called from
inside `_tracked_run` — a helper the **task body** invokes. So it counted only fires whose body
chose to call it, and a body chooses that only *after its own gate has already run*.

`poll_all_odds` therefore graded `behind` at **ratio 0.50** for two months. LAT-P039's control
settled it: same beat, same worker, same 304-second window, one task with a gate and one without.

| task | delivered | recorded starts |
|---|---|---|
| `poll_all_odds` (self-gates) | **10** (0.99x) | **5** (0.49x) |
| `sync_statpal_livescores` (no gate) | **10** (0.99x) | **11** (1.09x) |

Identical deliveries; 2.2x difference in starts. The 0.50 was the arithmetic of the design —
`LIVE_POLL_INTERVAL` is 32s against a 30s beat, and `last_poll_time` is stamped at the END of a
poll, so two consecutive fires can never both pass. Nothing was late. Two months of "running at
half speed" dissolved into a counting artifact.

The control is what elevated this from a theory to a proof, and it is the standard for this class:
**when you claim a counter is miscounting, run the same measurement against something that shares
every condition except the one you blame.**

## The general form, because this recurred immediately

A verdict is a claim about a population. It is only true if its numerator counts that population
and its denominator ages it. Both halves have now failed on this one surface, separately:

1. **The numerator asked permission** (this ruling) — `starts` counted gate-passes, not fires.
2. **The denominator belonged to something else** (#1790, found by LAT-P040 one cycle later) —
   `p95_duration_ms` is computed over a 50-sample rolling history and was printed beside
   `window_s`, which ages the *starts counter* on a 24h TTL. Measured on `poll_odds`: a p95
   describing ~50 minutes reported against 19.1 hours, a 23x mismatch. It promoted a transient
   46.2s burst into a standing `overruns` verdict that read 5.8s an hour later with nothing
   changed.

Same disease, one field apart, in a module whose founding docstring is *"a count of unknown age is
not a measurement."* **State the scope of every statistic next to the statistic.** A number whose
window the reader has to infer will be inferred wrong, by a careful reader, in good faith.
