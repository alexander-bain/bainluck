# RULING 038 — Circular authority: a grade computed from our own data is never tier-3

date: 2026-08-12
author: Alex
via: 339T sequencing, #1811 (Fable scoped it 08-13)
issues: #1811, #845
relates: ruling 021 (two graders reading one input must share the DECISION — same family: what a grade is computed FROM decides what it may claim)

**A resolution source that reads our own `events` columns to produce a grade is asserting our data
back to us with a venue's authority. It can never sit in tier 3.** Tier 3 is external settlement —
the venue's own answer, which nothing may overwrite because there is nothing above it to appeal to.
A grade we computed from a row we wrote has an appeal: our own row can be wrong, and when it is,
the grade must be re-derivable. Tier 2 (`DETERMINISTIC_SOURCES`) is exactly that — deterministic
from cited data, overwritable by a real settlement.

**The invariant, stated so the tests can enforce it: NO member of `AUTHORITATIVE_SOURCES` reads our
own `events` columns.** `backend/tests/test_resolution_authority_038.py` asserts it against a named
set. Adding a circular source to tier 3 in future turns the suite red.

## The instance

`poly_total_score` (`_resolve_polymarket_total_from_scores`, `backend/app/tasks/backfill_winners.py`)
grades Polymarket full-game Over/Under markets from `events.home_score + events.away_score` — our
column, our merge, our matching layer. It sat in `AUTHORITATIVE_SOURCES`.

This was not a judgment call, it was an inconsistency. Its sibling `game_score` takes the **same
input** and produces the **same shape** of grade — `events.home_score` / `events.away_score`, on a
market linked to the same event — and has always been tier 2. Two graders, one input, two tiers.
So the correction is one string: `poly_total_score` joins `game_score`.

The circularity is not theoretical on this input. `completed_at >= commence_time` is an invariant
whose violation means an earlier game's data merged onto the wrong event, and it was violated on 439
rows (gotcha #46); closed events keep frozen mid-game scores. A grade computed from those columns
inherits every one of those defects — and, in tier 3, was immune to being fixed by the venue's own
settlement arriving later.

## The audit that generalises it

Every remaining tier-3 member was traced to what it grades FROM:

| source | grades from |
|---|---|
| `api_settlement` | Kalshi `market.result` / Polymarket `outcomePrices` — the venue |
| `clob_authoritative`, `clob_never_graded`, `clob_ordinal` | Polymarket CLOB settlement |
| `clob_field_repair` | CLOB settlement, established per-leg by `condition_id` |
| `datagolf_settlement` | the DataGolf API's own settled field |
| `settlement_sync` | `futures_outcomes.current_probability` — price-derived, and already fenced out of calibration truth by `PRICE_DERIVED_SOURCES` |

None reads `events`. `poly_total_score` was the only one, which is why the invariant can be stated
absolutely rather than as a preference.

## Three consequences, each named

1. **It joins the recompute set.** Every tier-3 write guarded by
   `COALESCE(resolution_source,'') NOT IN AUTHORITATIVE_SOURCES_SQL` now supersedes a
   `poly_total_score` grade instead of skipping it. A late Gamma/CLOB settlement finally wins over
   our arithmetic — which is the whole point.
2. **`can_write_winner` tightens, and coverage does not move.** `poly_total_score` may no longer
   assert a winner on a market that is not `resolved`/`closed`; tier 3 was the only self-justifying
   tier. **Measured 2026-08-12: 7,468 production outcomes carry `resolution_source =
   'poly_total_score'`, and 7,468 of them sit on `status = 'resolved'` markets — delta 0.** The
   writer's own query already filters `m.status = 'resolved'`, so the tightening is a fence around
   a door nobody used.
3. **Calibration truth is UNCHANGED.** `CALIBRATION_TRUTH_ELIGIBLE_SOURCES` is
   `(AUTHORITATIVE_SOURCES - PRICE_DERIVED_SOURCES) | DETERMINISTIC_SOURCES | {date_passed}`, so a
   move between those two tiers is invisible to it. `poly_total_score` was eligible and stays
   eligible; **the published calibration curve does not move by a single outcome.** This is asserted
   explicitly so nobody re-litigates it as a calibration change.

The two axes stay orthogonal, as ruled in Queue #261: overwrite authority answers "may this write
STAND?", calibration eligibility answers "may this winner GRADE a forecast?". Circularity is a
statement about the first axis only. A grade computed from our scores is still independent of the
market's own price, which is what the second axis cares about.
