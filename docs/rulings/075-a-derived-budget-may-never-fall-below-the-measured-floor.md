# RULING 075 — A derived budget may never fall below the phase's own measured floor

date: 2026-08-17
author: Alex
issues: #1680, #1892, #1586
context: owed out of queue 359, banked by queue 360. The calibration producer strangled itself
  with a budget it derived from its own starved history.

## The ruling

**When a component derives a per-phase budget from measured history, that budget may never be
allowed to fall below the phase's own measured minimum unit cost.**

If the derived budget comes out smaller than the smallest unit of work that phase has ever been
observed to complete, the component **refuses loudly and marks itself unrunnable.** It does not
attempt the phase. It does not run-and-time-out. It records a refusal, names the arithmetic that
produced the impossible budget, and stops.

Three properties are required of the refusal, and the first is the one that makes the other two
worth anything:

1. **It is visible as a refusal** — a distinct verdict, not an empty success and not a silent skip.
   `app/utils/task_verdict.py` already exists for exactly this; the refusal goes through it.
2. **It names the floor it measured and the budget it derived**, both numbers, in the same record.
   A refusal that says only "budget too small" cannot be acted on by the next reader.
3. **It marks the component unrunnable rather than unhealthy.** These are different states with
   different owners: unhealthy is watched, unrunnable is fixed.

## Why — the self-locking mechanism

A run-and-timeout in this position is not merely a wasted run. It is a **ratchet that can only
tighten**, and it is #1680's exact mechanism:

1. The phase's budget is derived from the history ledger.
2. The budget comes out below the cost of one unit of work.
3. The phase runs anyway and is killed at the deadline.
4. **A killed phase appends nothing to the ledger** — the completion row that would have recorded a
   real, larger cost is never written.
5. The next derivation reads the same starved history, or a poorer one, and produces a budget that
   is the same or smaller.

There is no path out of that loop from inside the loop. Every subsequent run is a smaller run.
The component cannot recover by trying harder, because trying is precisely what fails to leave a
trace. This is why **deleting the ledger row is a RESTART, NOT A CURE.** It clears the current
strangle and re-arms the identical trap the moment one cheap phase completes and writes a small
number back into the history that the next budget is derived from. The cure is the refusal, because
a refusal is the only outcome in this family that produces a readable artifact.

Note the general shape: **any feedback loop whose failure mode writes no feedback is self-locking.**
The budget case is the specimen; the rule is the class. Where a component derives a bound from its
own history, ask what the failure path appends. If the answer is "nothing", the bound can only decay.

Sibling reading: ruling 009's lift condition was structurally unreachable while the strangle held —
it wanted a fresh publish plus roughly thirteen clean beats from a producer that could not complete
one. **A lift condition expressed in terms of output from the thing that is broken is not a
condition, it is a deadlock.** Write lift conditions against something the failure cannot suppress.

## Second clause — the q359 through-line, banked as doctrine

**"Could not check" must never render as "nothing to report."**

These are opposite readings of the same empty output, and every instrument in this repo that has
lied to us has lied by collapsing them. The specimens are now numerous enough that this is a class,
not an anecdote:

- **#1680** — a phase that could not run recorded no failure, so the producer read as quiet.
- **#1892** — an at-risk band measured as `0 rows` was reported as "no loss", when the clock that
  populates the band was not running. Nothing at risk and nothing measured are different facts.
- **#1586** — `unreached_existing` growing across the ring read as a healthy poll, because every
  angle that only asked "is the cursor moving" got a true answer to the wrong question.
- **Gotcha #53** — an empty `200` is a response shape, not an absence.
- **Gotcha #54** — a gate that never ran reports the exit code of `tail`.
- **Rulings 071 / 072 / 074** — a malformed lock, a fixture that agrees with the bug, and a green
  pass that names elapsed time instead of work done.

The obligation this creates is concrete and belongs at the point of *writing*, not the point of
reading: **before a component emits a zero, a null, an empty list, or a green, it must be able to
say which of the two facts it is asserting** — "I checked and there is nothing" or "I could not
check". If it cannot distinguish them from the signal it has, it must acquire a second signal
(an existence probe, an age against a measured bound, an explicit sentinel) or emit neither.

A reader cannot recover a distinction the writer discarded.

## Sibling rulings

- **074** — a green pass names the work it did; the refusal here names the numbers it measured, for
  the same reason.
- Queue 359's unnumbered **Ruling B** (`/health` HARD-FAILS when `error/accepted == 0` over 24h
  while `transaction/accepted` is non-zero — a muted channel must never render as a quiet one) is
  the second clause applied to one instrument. It lives in `.claude/commands/health.md`, which is
  gitignored, so it is local-only by construction; this file is where the general form is banked.
- **009** — the frozen file whose lift condition this ruling explains was unreachable.
