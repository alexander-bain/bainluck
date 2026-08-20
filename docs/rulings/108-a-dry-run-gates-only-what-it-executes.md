# RULING 108 — A dry run gates only what it executes

date: 2026-08-20
author: Fable
issues: #1947, #1796, #2003, #2013, #2023, #2026

**A dry run that never executes the write gates NOTHING about the write.**

Not "gates it weakly", not "gates most of it". Nothing. A dry run is evidence about the code paths it
ran, and the write is not one of them. Every gate that stops short of the write is, with respect to
the write, silent — and silence read as approval is how a rail ships four times and writes zero rows.

## The charter case: four deaths, four depths, four green gates

The 328-game CREATE wave (#1947) fired four times across four `/triage` windows. Each attempt was
preceded by a gate that was **genuinely met and honestly verified** — merged ancestry proved against
the deployed release SHA, plan hash re-derived identical on the deployed tree, census read
`still_missing 328` / `already_present 0` / `gate.passes true`. Each time the gate was met, the wave
fired, and it died one layer deeper in the same write:

| # | Gate that was met | How the write actually died |
|---|---|---|
| #2003 | statpal absorber deployed, shadow read 0/62 | (sequencing gate — cleared) |
| #2013 | #2003 deployed | `asyncpg AmbiguousParameterError: inconsistent types deduced for parameter $2, text versus character varying` — `:truth_id` used in two positions, cast in neither |
| #2023 | #2013 deployed | espn_id minting writer still live — a create → drain → re-create loop on a ~30-minute cadence |
| #2026 | #2023 deployed, ancestry proved, writer fix live | `asyncpg DataError: invalid input for query argument $7: '2026-06-21T02:10:00+00:00' (expected a datetime.date or datetime.datetime instance, got 'str')` |

Nine consecutive `apply=true` calls on the last attempt. Every one sub-second. Every one dead inside
the write. Nothing was written — verified two ways, not assumed.

**Each failure was invisible to every upstream gate for the identical structural reason.** The dry run
is green *because* the dry run never executes the INSERT. `CAST(:commence_time AS timestamptz)` sat in
the statement the whole time and could not help, because asyncpg type-checks the PYTHON argument
before the statement reaches the server: a server-side cast applied to a value the server never
receives. No amount of reading the SQL finds that. Only a driver does.

## The finding is not the fourth bug

If #2026 lands and a fifth blocker appears one parameter over, the finding will not be the fifth bug.
It is that **this rail has no test that executes its INSERT against a real driver** — and that is the
thing to fix instead of the next parameter.

So: **no fifth attempt fires on gate-green plus a parameter fix.** The gate for the wave is now an
INSERT-executing test. It runs the rail's actual statement and actual bind dict against a real
asyncpg driver and a real PostgreSQL, it is proved RED on the defect class before it is accepted, and
the wave fires only when that test is green **on the deployed tree** (ruling 032 — a gate verifies
only where it runs).

## The obligations, general form

1. **A gate names what it executed.** "Dry run green" is not a verdict on a write; it is a verdict on
   a read. Report it as such, and never let it stand in the acceptance slot the write's own gate
   should occupy.
2. **A write path is gated by executing it**, against the real driver, on real infrastructure. A unit
   test with a session double cannot see a bind-type refusal, because the double discards the params
   — and the one test that reads the bind compares it against the same constant the production line
   binds. That is not a hypothetical: it is #1884 verbatim, which shipped with 39 green unit tests and
   threw `asyncpg.DataError` on the first statement of every run.
3. **A gate is proved red before it is trusted.** A test that cannot fail proves nothing. Prefer a
   negative control *inside* the test — one arm binds the defective form and asserts the driver
   refuses it — so the red-first proof cannot rot away from the gate it certifies.
4. **A helper is not a call site.** `test_the_helper_coerces()` can be satisfied by a helper nobody
   calls. Assert the value that reaches the driver, through the function production actually invokes.

Related: gotcha #53 (an empty 200 is not an absence — a run that recovered nothing looks identical to
a run with nothing to do), ruling 032 (merged is not deployed), and
`app/utils/task_verdict.py`, whose whole purpose is that "it returned" is not "it worked". This ruling
is the same family one step earlier: **"it was checked" is not "it was executed."**
