# RULING 111 — The script rail ranks MOVEMENT FIRST, with a per-ladder cap

date: 2026-08-20
author: Alex
issues: #195
amends: 105

**The capture was the argument.** UX-P107 implemented ruling 105 and, in the
same breath, reported that it had not fixed the card. Alex read the before/after
pair and ruled on the residual rather than on the constant.

## The ruling

> The script rail ranks **MOVEMENT FIRST WITH A PER-LADDER CAP**. Rows with real
> pregame travel (`|now − opened|`) rank first; conviction fills the remaining
> slots; at most ONE row per player-ladder family anywhere in the rail; the
> structural filter (ruling 105) stays underneath as a floor.

This amends **the 105-family ranking, not the filter**. Ruling 105 stands
unchanged and its predicate is untouched.

## Why a ranking change and not a better threshold

UX-P107's own sweep is the argument, and it is the reason this ruling exists at
all. Swept from `0.44` down to `0.35`, the Phillies rail kept **the same shape at
every value**. The rung population is a continuum with no gap (5.0, 6.0, 7.0,
7.2, 8.5, 8.8, 9.0 …), and conviction ranking selects a ladder's extreme rungs
*by construction* — those are the most convinced rows on the card. So a
certainty threshold is a treadmill: every rung it removes is replaced by the
rung one point less extreme.

**The defect's unit was the ladder; every rule on the rail had the row as its
subject.** No amount of tuning a per-row predicate reaches that. The cap is the
first rule on this surface whose subject is a group, which is why it works where
four measured constants did not.

## The measured before, on Alex's own card

Event `15199886` (Phillies @ Marlins), ruling 105's filter already applied:

| # | question | now | travel |
|---|---|---|---|
| 1 | Kyle Schwarber: 1+ home runs | 54.7% | 27.7 pt |
| 2 | Alec Bohm: 1+ home runs | 6.5% | 1.0 pt |
| 3 | Justin Crawford: 5+ hits + runs + rbis | 7.0% | **0.0 pt** |
| 4 | **Trea Turner: 4+ hits** | 7.0% | **0.0 pt** |
| 5 | **Trea Turner: 3+ hits** | 8.0% | **0.0 pt** |

Three rows that had not moved, and rows 4 and 5 are one ladder one point apart —
not two claims, one claim quoted twice at slightly different resolutions.

## The after

| # | question | now | travel |
|---|---|---|---|
| 1 | Kyle Schwarber: 1+ home runs | 54.7% | 27.7 pt |
| 2 | Kyle Schwarber: 2+ hits | 38.5% | 16.5 pt |
| 3 | Brandon Marsh: 2+ hits | 22.5% | 14.5 pt |
| 4 | Alec Bohm: 3+ hits | 11.0% | 4.0 pt |
| 5 | Bryan De La Cruz: 2+ hits | 14.0% | 2.0 pt |

Five distinct ladders, every row having moved. Captures:
`.claude/handoff/artifacts-ux-p108/{before,after}-pregame.png`.

Schwarber appears twice on two DIFFERENT stats — the per-player cap permitting
two claims about one player, which the ladder cap does not touch.

## The floor of "real travel" is the line that already types the bar

`PROP_TRAVEL_FLOOR = 0.005`, and it is **extracted, not introduced**: it is the
literal constant that has always typed `DivergenceRow.direction`. `hasTravelled`
is defined as `direction !== "flat"`, so the movement tier is exactly the set of
rows whose own bar draws a journey.

That coherence is load-bearing rather than tidy. This rail is ruled on from
screenshots. Any higher floor would rank a row whose bar visibly moved *below* a
flat one — which is the complaint this ruling came from, re-created one tier
down and invisible to the only instrument Alex uses on it.

The pregame travel distribution over the same 183 questions and four production
payloads is **zero-inflated, not smooth**: 103 of 183 (56.3%) have no movement
at all, so the tier boundary is a property of the population rather than a
percentile chosen on it.

## What it costs, measured and not glossed

Three costs, all reported rather than discovered later:

1. **A two-point move outranks a 93% favourite that has not moved.** That is
   what a strict tier means. Pinned in the suite so the trade is visible.
2. **The P106 coherence overlap weakens, 2 → 1.** The settled rail ranks by
   `|resolution − mark|`, which is maximised by exactly the near-certain marks
   this ruling stops leading with, so the direction is structural. The one row
   that survives on both rails is Freddie Freeman's 3+ — the biggest surprise of
   that game (93.0 pts) — kept because it also travelled 35.5 pts pregame.
3. **The floor removes five moved rungs on `14788546`**, all Brady Singer
   strikeout rungs, one of which travelled **34.0 points**. Under movement-first
   that row would otherwise sit at or near the top of the rail. Implemented as
   ruled — Alex's wording is "stays underneath as a floor", and ruling 105
   forbids an escape hatch — and **flagged back rather than re-litigated.** If
   the answer is "a rung that has travelled far enough is a view again", that is
   a ruling, and it changes one test.

## Scope

Pregame only. Both the tier and the cap are gated on `pregame`. In-game the rail
ranks by travel, where two rungs of one ladder moving together is corroboration
rather than repetition; ruling 035's blast-radius discipline says a rail nobody
ruled on is not re-ranked on the way past. The live and settled rails were read
as controls (ruling 050) before and after, over all four payloads, and are
**byte-identical** — including their rendered PNGs.

The detail view's membership is unchanged (the fold predicate did not move);
its ORDER changes with the sort, which is recorded rather than left to surface.

## Where it lives

`frontend/lib/propDivergence.ts` — `PROP_TRAVEL_FLOOR`, `RAIL_MAX_PER_LADDER`,
`ladderFamilyKey`, `hasTravelled`, `byScript` (replacing `byConviction`), and the
`perLadder` guard in `selectDivergenceRows`. Suite:
`frontend/__tests__/lib/propMovementFirst.test.tsx` (22 tests), plus four
UX-P107 assertions rewritten to state the new ruling rather than deleted.
