# RULING 089 — A budget derived only from successes cannot be corrected by the failures it causes; the window's unallocated time goes to the phase that is starving on it

date: 2026-08-18
author: Fable (CAL-P072 directive, ruling a), banked with the attribution ruling 077 required
issues: #1977, #1680, #1544
supersedes: none — extends ruling 075's derivation with an allocation step

## The ruling

**Phase budgets derive from measured phase durations (ruling 075, unchanged), with the
1,380,000 ms window as the ceiling, and whatever no phase's measurement claims is
assigned to the bottleneck phase.** A 177,374 ms cap standing beside ~1,000,000 ms of
dead air is the defect, not the safety margin it resembles.

The policy shipped only behind attribution, per ruling 077 — "ran 219 s, banked nothing"
is not yet "timed out." What follows is the reading that authorised it.

## The attribution

Two consecutive failed beats, read end-to-end from the producer's own durable ledger row
`calibration:main:phase_ledger` on 2026-08-18.

**Beat 1** — generation `1787091300309`, dispatched 22:15:00Z, terminal written 22:19:12Z:

```
stage_counts   read:futures_generation 1 · read:futures_unit 1
stages         read:futures_generation           72,767 ms
               read:futures_unit                159,801 ms   <- cancelled
               staged:units_this_beat                  1
               staged:units_completed_this_beat        0
               staged:units_banked                     3   (of 128)
plan[futures]  budget_ms 177,374 · statement_timeout_ms 159,637
terminal       failed · checkpoint_write nothing_to_bank
```

and from `/api/admin/task-metrics?task=precompute_calibration_main`, same instant:

```
last_verdict         thrown
last_verdict_reason  DBAPIError
last_error           asyncpg.exceptions.QueryCanceledError:
                     canceling statement due to statement timeout
                     [SQL: WITH market_info AS ( ...
```

**Beat 2** — generation `1787094900158`, 23:15:00Z, terminal 23:20:16Z, read live one hour
later:

```
staged:units_this_beat                  2
staged:units_completed_this_beat        1
staged:unit_ms_mean_completed     103,473 ms   <- unit 1, finished
read:futures_unit                 263,240 ms   <- both units together
staged:units_banked                     4      (3 -> 4)
terminal                          failed
```

so the cancelled second unit ran `263,240 − 103,473 = 159,767 ms`.

**The failure mode is a TIMEOUT, and the clock that fired is ours.** 159,801 ms and
159,767 ms of measured unit read against a 159,637 ms `statement_timeout` this build sets
on itself: overheads of 164 ms and 130 ms. Not Celery, not the broker, not an exception in
build logic, not a refusal, not a silent skip. The cancellation is attributed to the
plan's own derived cap, twice, arithmetically.

## Two things the second beat settles that the first could not

**1. The population straddles the cap.** One unit finished at 103.5 s under the same cap
that killed the next. So the build is not slow — it is **sorted**. Every unit under
~160 s banks; every unit over it can never bank, at any beat count. That is why more
beats did not help and why CAL-P071's out-of-band beat banked nothing: the cheap units
drain, and then every remaining beat re-attempts a unit that cannot fit. **A permanent
stall, not a gradual one.**

**2. The cap cannot be corrected by the thing it caps.** `derive_plan` budgets a phase at
`max(observed completions) × BUDGET_SAFETY`. A cancelled phase records a **floor**, and a
floor is forbidden — correctly, per ruling 075 and CAL-P067 — from producing a budget: a
phase cancelled at 159,801 ms took longer than that by an unknown amount, so treating it
as a duration would under-budget it by construction. The consequence is a **one-way
ratchet**. The ten completions behind `budget_ms 177,374` are 47–118 s beats from before
the q268 bump, when nearly every unit was already banked and the phase did almost no work.
Every failure since has raised a floor the budget is not allowed to read. 111 consecutive
failures is that loop's fixed point, and no amount of running it changes the number.

**Reallocation is what breaks the loop from outside it**, which is the whole reason this
is a policy call and not a tuning one.

## What the unallocated time was, and was not

The deployed plan declared **382,139 ms of a 1,380,000 ms window** — ~72% unallocated. That
residue was never a reserve. The window's real reservations are taken out *before* budget
derivation sees it: `CLEANUP_MARGIN_MS` (120,000 ms) for the serialize/gate/publish tail,
outside `available_ms` entirely, and `STATEMENT_INNER_MARGIN_MS` inside every statement
timeout so Postgres cancels and releases its xmin before Celery can SIGKILL the worker
(#1479). What is left over is left over only because no phase's measurement claimed it.

## The rule, as implemented

`app/utils/calibration_phase_ledger.derive_plan`, provenance carried in the payload:

* **Bottleneck by evidence, never by name.** A phase qualifies on *truncation evidence*
  alone: a measured `budget_ms` **and** a `floor_ms` strictly greater than it — observed
  running past its own allotment without finishing. Ties to the larger floor. The string
  `futures` appears nowhere in the selector.
* **No qualifying phase ⇒ no reallocation.** A plan with no evidence of truncation has no
  basis for naming a bottleneck, and inventing one is the constant this module refuses to
  write.
* **A phase with no measured budget is reserved for, never allocated to.** Its cost is
  unknown in both directions. Its worst floor is the only lower bound that exists, so
  reserve exactly that and nothing more. If that reserve consumes the window, the handout
  declines rather than overcommitting.
* **Bounded by construction.** The widened budget is `available_ms` minus every other
  phase's declared budget minus that reserve, so the declared total *reaches* the ceiling
  and cannot pass it. Nothing is taken from a measured phase; this spends only time that
  was going to expire unspent.
* **Provenance, because a number is not self-describing.** `budget_basis` names the rule
  that produced the budget (`measured` / `measured_scaled_down` /
  `measured_plus_window_slack` / `unmeasured`) and `slack_assigned_ms` makes the
  measurement recoverable unmodified — `budget_ms − slack_assigned_ms` is the measured
  number, always. The plan payload additionally carries `slack_target` and
  `unallocated_ms`, so the ~72%-unspent defect would have been legible off the row instead
  of requiring arithmetic. This is CAL-P071's `per_beat_basis` discipline applied one level
  up.

On the production row: futures `177,374 → 1,172,893 ms`, statement timeout
`159,637 → 1,142,893 ms`, declared total `382,139 → 1,377,658 ms` against a 1,380,000 ms
ceiling. Every other phase byte-identical.

**`_main_input_fingerprint()` is unmoved at `b65faaacdc240b3b256934fcad528db1`**, verified
byte-identical to production's live ledger row at the branch tip. The four banked units
survive the deploy — which mattered more than usual here, because this change exists to
stop losing them.

## What this does NOT license

A budget is a **ceiling on a statement**, not a reservation of wall clock. A phase handed
slack it does not need still completes in the time it takes and hands the rest onward — so
"the phase absorbed the window" is never an argument that the phase *spent* it. And the
handout is not a substitute for measurement: the moment a unit completes, `unit_ms` becomes
a real duration and CAL-P071's projection divides by an allotment that is now real. The
reallocation buys the build the chance to measure itself; it does not stand in for having
done so.

Nor does it license widening a cap that is *not* the binding constraint. The argument that
carried here is "two beats show the cancel point IS our derived cap, to 164 ms and 130 ms."
The argument that does not carry is "the phase keeps failing, so give it more."

## Doctrine

The clause that survives deleting this case is lifted to `docs/doctrine.md` clause 9:
**a bound derived only from successes cannot be corrected by the failures it causes.**
