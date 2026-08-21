# RULING 110 — The `heavy` lane gets a SCOPED two-task exception, with its falsifier armed in code

date: 2026-08-20
author: Fable (directive to the latency program, LAT-P077)
issues: #1609, #1545

## The ruling

The standing **"`heavy` is calibration-only"** constraint gets a **scoped exception for two
tasks, BY NAME**:

```
app.tasks.backfill_market_shapes
app.tasks.precompute_backfill_progress
```

They move from `background` to `heavy`. Fable, verbatim:

> the heavy-is-calibration-only rule gets a SCOPED EXCEPTION for the two explicitly-routed
> backfills — move them to heavy, WITH THE FALSIFIER ARMED IN CODE: if any calibration
> heavy-beat's latency degrades measurably after the move, the routing reverts the same window
> and the rule re-hardens. Ship the routing change and the falsifier test together; the
> exception is those two tasks by name, not a class.

Three obligations, all discharged in the commit that carries this file:

1. **By name, not a class.** Not "backfills", not a prefix, not "anything explicitly routed".
   The other twelve members of `_HEAVY_KEEP_ON_BACKGROUND` stay where they are, and
   `test_exception_is_not_a_prefix_rule` asserts it.
2. **The falsifier ships WITH the routing**, not after it —
   `app/utils/heavy_routing_falsifier.py`, with the pre-move baseline pinned from production
   measurement taken *before* the change, and `GET /api/admin/heavy-move/falsifier` to read the
   verdict. A halt with no readable instrument is a wish (LAT-P074); so is a conditional grant
   whose condition lives only in prose.
3. **REVERT obliges the same window** and the rule re-hardens: no further exception without a
   new ruling.

## Why the exception was asked for

LAT-P076's occupancy census found `background` running at **90 % busy** on `--concurrency=2`
with **102 beats**, while `heavy` sat at rho **0.59–0.81** with room. Its §4 costed five
levers; **E** — move these two explicitly-routed backfills to the lane with headroom — was the
only free one aimed at measured occupants rather than modelled ones. It was refused on the
spot because it is exactly what the calibration-only constraint forbids, and brought as a
ruling request instead. This is the answer.

## What the measurement says, including where it contradicts the request

The ask was priced by LAT-P076's 26-sample slot census at **32 % + 24 % = 56 % of one slot**.
Re-measured here from `recent_durations_ms` (n=50 each) against 24 h run counts:

| task | census share | measured, observed runs | measured, if every fire ran |
|---|---|---|---|
| `backfill_market_shapes` | 32 % | **6.1 %** | 14.2 % |
| `precompute_backfill_progress` | 24 % | **12.8 %** | 27.3 % |
| **together** | **56 %** | **18.9 %** | **41.5 %** |

**The census overstates by roughly 3x**, which is what a 26-sample per-task share does. The
ruling is granted anyway, but on the honest number: `background` sheds **~19 %** of one slot,
not 56 %.

🔴 **And the move is not symmetric, which is the reason the falsifier is not ceremony.** Both
movers run far below schedule today — **31 of 72** fires and **45 of 96** — *because they are
being starved on `background`*. A task that stops being starved runs more often. So `heavy`
can inherit up to **41.5 % of one slot** while `background` sheds **19 %**. Against `heavy`'s
0.59–0.81, that is ~0.21 of its two slots, landing it near **0.80–1.02**. The lane this ruling
protects is the lane the ruling might push over.

## What the falsifier watches, and what it admits it cannot see

Seven calibration heavy-beats, baselines pinned 2026-08-20T16:40–16:47Z against build v3873
**before** the move:

| beat | p50 | p95 | soft limit | succ 24 h | gradeable? |
|---|---|---|---|---|---|
| `precompute_calibration_main` | 214.7 s | 1302.1 s | 1500 s | 21 | yes (p95 at 87 % of limit) |
| `compute_calibration_prices` | 538.2 s | 599.9 s | 600 s | **0** | ❌ **CENSORED** |
| `compute_time_horizon_calibration` | 302.0 s | 302.7 s | 600 s | 0 | yes |
| `compute_fair_fight_comparison` | 147.8 s | 268.4 s | 600 s | 3 | yes |
| `precompute_source_intelligence` | 17.5 s | 27.3 s | 600 s | 2 | yes — the cleanest subject |
| `snapshot_coverage_metrics` | 480.1 s | 482.1 s | 600 s | 0 | yes (n=10, weak) |
| `precompute_backfill_winners_status` | 518.4 s | 601.0 s | 600 s | **0** | ❌ **CENSORED** |

**Two of the seven are already pinned at their 600 s soft limit with zero successes in 24 h.**
A beat clamped at its own timeout reports the same number however much further behind it
falls, so it cannot show degradation and is excluded from the grade rather than counted as
evidence of safety. That two of the protected beats are *already failing before the move* is
recorded here as a finding in its own right; it is not this ruling's to fix.

Verdicts are three-valued and **INCONCLUSIVE is not HOLD**: if nothing in the set can be
graded, the falsifier says it is not armed rather than reporting a clean bill of health
(gotcha #53).

### Its effective coverage TODAY is 3 of 7, and that is stated rather than implied

Run against real production task-metrics before the move (artifact:
`docs/audits/latency/lat-p077-heavy-premove-baseline.json`), `grade_move` returns:

```
VERDICT: HOLD | 3 of 7 watched beats graded, none degraded
  precompute_calibration_main         hold          p50 214.7s vs pre-move 214.7s
  compute_calibration_prices          censored      p95 at the 600s soft limit
  compute_time_horizon_calibration    no_new_runs   0 runs in the last 24h
  compute_fair_fight_comparison       hold          p50 147.8s vs pre-move 147.8s
  precompute_source_intelligence      hold          p50 17.5s vs pre-move 17.5s
  snapshot_coverage_metrics           no_new_runs   0 runs in the last 24h
  precompute_backfill_winners_status  censored      p95 at the 600s soft limit
```

So the condition this grant rests on is watched by **three** beats, not seven: two are
censored at their timeout and two have not run in 24 h. `precompute_source_intelligence` —
tight, fast, far from its limit — is the one that would show a `heavy` regression first.

**This is a real limit on the guarantee, not a formality.** A degradation confined to the two
censored beats would be invisible. It is written here so the next reader does not mistake
"HOLD" for "all seven are fine".

## 🔴 The trap this nearly fell into, recorded because it will recur

`_tracked_run` registers task metrics under a name that is frequently **not** the task name
(#1800). Reading `GET /api/admin/celery/task-metrics/<task>` therefore returns an empty body
for a task that is running perfectly. In one window that produced **three** false `NO DATA`
reads:

```
app.tasks.backfill_market_shapes           -> "market_shape_backfill"
app.tasks.snapshot_coverage_metrics        -> "coverage_metrics"
compute_time_horizon_calibration / compute_fair_fight_comparison
        -> readable only under their FULL names
```

A falsifier built on that first read would have been **blind on 3 of its 7 subjects while
reporting itself armed** — the precise shape gotcha #53 names, one level up: not an empty
result mistaken for a fact, but an empty result mistaken for *coverage*.
`test_metrics_names_match_tracked_run_registrations` reads the source of `app/tasks/__init__.py`
so the mapping cannot rot back.

## The revert, specified so it is four lines and not a judgement call

`verdict == "REVERT"` obliges, the same window:

1. delete the two names from `HEAVY_TASKS`;
2. set both beat entries' literal `options["queue"]` back to `"background"`;
3. record the reading that fired it in this file;
4. the rule re-hardens.

Step 2 is not bookkeeping. Beat `options` **override** `task_routes` at dispatch, and
`test_heavy_beat_literals_match_their_effective_queue` reads the source text — a revert that
touches only `HEAVY_TASKS` leaves two beat entries literally routing to `heavy` and turns that
guard red. LAT-P067 paid for this across nine entries.

## General clause

**A conditional grant ships with its condition executable, or it is an unconditional grant.**
The condition must name its subjects, pin its baseline *before* the change, and be able to
return the refusing verdict — a falsifier that cannot go red is the wrong-gate defect wearing
a safety coat (LAT-P075 found exactly that in this program's own
`test_live_beat_interval_is_not_unsafe`). Routed to `docs/doctrine.md` consideration; not
claimed as a clause here, because clause 14's duplication bar applies until a second unrelated
case appears.

## Status

**GRANTED and SHIPPED** on `program/latency-70` with the falsifier armed, 25 tests, 5 mutations
each caught at exit 1. The post-deploy read is **OWED**: the falsifier cannot be graded until
the routing is live, and this lane does not deploy.
