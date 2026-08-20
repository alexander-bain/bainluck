# RULING 112 — Movement overrides the structural floor

date: 2026-08-20
author: Alex
issues: #195
amends: 111, 105

**UX-P108 shipped ruling 111, measured what the floor cost, and flagged the
residual back rather than re-litigating it.** Alex ruled on the flagged residual.
This is the second consecutive ruling made off a cost the implementing lane
reported against its own work.

## The ruling

> **MOVEMENT OVERRIDES THE STRUCTURAL FLOOR.** A structural rung whose travel
> clears the movement floor is rail-eligible — the per-ladder cap still applies,
> so no ladder floods the rail.

Ruling 105's **predicate is untouched for the third time**. What changes is that
the filter is no longer unconditional at the rail's selection step: it now removes
a structural rung only when that rung has not moved.

## Why — the floor asks where a rung sits and cannot see how it got there

Ruling 105 removes rungs whose near-certainty is *arithmetic*: a 5% "8+
strikeouts" sitting under a 5% "7+" is the ladder restating itself, not a claim
anyone made. That reading is right, and it is right about most rungs.

It is wrong about a rung that **arrived** at near-certainty. Event `14788546`
(Cardinals @ Reds) is the specimen, and UX-P108 measured it against itself. Brady
Singer's entire strikeout ladder collapsed onto the 5% floor before first pitch:

| rung | opened | now | travel | structural |
|---|---|---|---|---|
| 2+ | 46.0% | 46.0% | 0.0 pt | no |
| 3+ | 5.0% | 5.0% | 0.0 pt | yes |
| 4+ | 6.0% | 5.0% | 1.0 pt | yes |
| **5+** | **39.0%** | **5.0%** | **34.0 pt** | yes |
| 6+ | 23.0% | 5.0% | 18.0 pt | yes |
| 7+ | 14.0% | 5.0% | 9.0 pt | yes |
| 8+ | 6.0% | 5.0% | 1.0 pt | yes |

The 5+ rung is structural **because of where it landed**, and it landed there by
travelling 34.0 points — the second-largest pregame move on a 100-question card.
Under an unconditional floor the rail deleted it and led with rows that had moved
less. *An arithmetic certainty that broke* is not the ladder restating itself; it
is the single loudest thing the market said about this game, and saying that is
the rail's whole job.

## The per-ladder cap is what makes this affordable — and it already existed

Five of Singer's rungs are structural **and** moved (34.0, 18.0, 9.0, 1.0, 1.0
pt). Readmitting them un-capped puts three of them on a five-row rail: one ladder,
three quotes, precisely the defect ruling 111 was written to end.

`RAIL_MAX_PER_LADDER` admits one, and because the movement tier ranks by travel it
is the **pivot** rung, not an arbitrary sibling. **Neither ruling is safe without
the other**: 112 alone re-creates 111's bug, and 111 alone deletes 112's story.
That mutual dependency is asserted in the suite rather than left in prose.

## The measured before and after, on the proof subject

Event `14788546`, pregame rail, five rows:

| # | BEFORE | | AFTER | |
|---|---|---|---|---|
| 1 | Brycen Mautz: 5+ strikeouts | 40.0 pt | Brycen Mautz: 5+ strikeouts | 40.0 pt |
| 2 | Ivan Herrera: 1+ H+R+RBI | 28.7 pt | **Brady Singer: 5+ strikeouts** | **34.0 pt** |
| 3 | Victor Scott: 1+ H+R+RBI | 28.5 pt | Ivan Herrera: 1+ H+R+RBI | 28.7 pt |
| 4 | Bryan Torres: 1+ H+R+RBI | 28.0 pt | Victor Scott: 1+ H+R+RBI | 28.5 pt |
| 5 | Spencer Steer: 1+ H+R+RBI | 26.7 pt | Bryan Torres: 1+ H+R+RBI | 28.0 pt |

One row in, one row out. On screen the new row reads **"Singer's 5+ strikeouts
opened at 39% — it's 5% now."**

`structuralSuppressed` on that card goes **8 → 3**: the three rungs that never
moved (Singer's 3+, Liberatore's 10+, Mautz's 8+) are still removed, and the count
now reports what the loop actually skips rather than what carries the flag.

## Controls — read before and after, at the rendered layer (ruling 050)

Four production payloads × three states, rail **and** detail view. Everything
except the one surface under ruling is **byte-identical**, and not only in the
data: the harness's rendered HTML compares equal with `cmp` for the live rail, the
settled rail, Alex's own `15199886` pregame card, its expand, and **the Singer
card's own expand** — membership is unchanged, which is ruling 111's clause about
suppressed rungs staying reachable in *See all 100*.

`15199886` is the strongest of these: it is the card ruling 111 was made on, it
carries three structural rungs, and **all three are flat**, so it could have moved
and did not.

## What it costs, measured rather than assumed

**A moved structural rung now spends its ladder's one slot.** So a ladder whose
biggest mover is a collapsed rung cannot also show the rung the market has a live
view about. On the specimen the cost is **zero** — Singer's 2+ is 46.0%, never
moved, and sits at conviction 0.040, so it was never reaching a five-row rail from
tier 2 — but the shape is real and is covered synthetically in the suite rather
than left to be discovered on a card nobody was looking at.

If the answer is *"inside a ladder, prefer the rung the market has a live view
about over the biggest mover"*, that is a further ruling and it changes one test.
Reported, not taken.

## Scope

Pregame only, like 111. In-game and settled ranking are untouched, and were read
as controls. The detail view's membership and order are unchanged.

## Where it lives

`frontend/lib/propDivergence.ts` — `suppressedByStructuralFloor`, the narrowed
skip in `selectDivergenceRows`, and the `structuralSuppressed` count now sharing
that one predicate (doctrine clause 5). Suite:
`frontend/__tests__/lib/propMovementFirst.test.tsx` (five tests in the floor
describe, two of them UX-P108's own assertions inverted in place rather than
deleted) and one rewritten specimen in `propStructuralRungs.test.tsx`.
Capture rig: `tools/capture-prop-rail.sh` + `tools/render-captures.sh`, committed
this cycle after being rebuilt three times.
