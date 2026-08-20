# RULING 105 — Suppress structural rungs: a rung's position in its own ladder is not a market view

date: 2026-08-20
author: Alex
issues: #195, #2024

**The screenshot won the call.** UX-P106 shipped THE SCRIPT and asked, in its own
commit message, whether structural near-zero ladder rungs belong in a pregame
rail. The capture answered it: four of the five rows on the real Phillies card
(`15199886`) read *"Kyle Stowers: 5+ hits + runs + rbis — market says NO, 95%"*.

That is arithmetic, not a view. A ladder that already prices 3+ at 10% cannot
price 5+ anywhere but the floor. The rung's certainty is a fact about **its own
position in its own ladder**, and a rail that leads with it is quoting a
subtraction back to the reader.

## The ruling

Near-certain ladder rungs whose certainty is explained by ladder position are
**filtered out of the five-row script rail**. Conviction ranking is unchanged
among what remains. Every suppressed rung **stays reachable through the same
"See all N questions" expand** — this is rail capacity in the exact sense
`notSelected` already means it, never a taxonomy loss and never a V3 drop.

## The implementation bar, and why it is stated as a bar

> "'Structural' needs a real predicate — rung position within its own ladder
> family plus threshold — never a bare probability cutoff; a genuine standalone
> 94% market view must survive the filter."

A price cutoff is the obvious implementation and it is wrong, because it deletes
the thing it is supposed to protect: a market that says *"this specific unlikely
thing, 6%"* as its only claim about a player is a view, and a rung that says the
same number because the rungs below it were already cheap is not. The two are
indistinguishable by price and trivially distinguishable by position.

So the predicate is a conjunction, and never the certainty half alone:

| | |
|---|---|
| near-certain NO **and** a LOWER rung exists | structural (the ladder's ceiling) |
| near-certain YES **and** a HIGHER rung exists | structural (the ladder's floor) |
| family of one | **never** structural, at any price |

**The population handed us the proof, on one card, at one price.** Event
`15199902` carries three questions reading "3+ hits", all priced at exactly
**6.0%**:

- `Jordan Beck: 3+ hits` — family `[3]` — **survives**
- `Kyle Tucker: 3+ hits` — family `[2,3]`, 2+ priced 15% — suppressed
- `Braxton Fulford: 3+ hits` — family `[2,3]`, 2+ priced 11% — suppressed

Same card, same stat, same threshold, same price, opposite dispositions. A bare
cutoff deletes all three.

## The measured line

`PROP_STRUCTURAL_CERTAINTY = 0.44` — p95 of the conviction distribution over the
same 183 questions and four production payloads that `PROP_SCRIPT_CONVICTION`
took p90 of. Selects 13 of 183 (7.1%).

The one-step gap between them is the argument: **the three existing constants
ESCALATE and this one REMOVES.** A wrongly escalated row is a loud row on a page
already being read; a wrongly suppressed row is a market that is not on the rail
at all. The costs are not symmetric, so the percentiles are not either —
suppression sits one step tighter than escalation on the very same distribution,
rather than being tuned to whatever number cleared the four rows in the capture.

## What the before/after capture also showed, and it is not a success

`.claude/handoff/artifacts-ux-p107/{before,after}-pregame.png`.

The filter removes the three rows Alex named, and **three rungs one point less
extreme step into their place** — Crawford 5+ at 7%, Turner 4+ at 7%, Turner 3+
at 8%. Swept from 0.44 down to 0.35, the Phillies rail keeps the same shape at
every value. The rung population is a continuum with no gap (5.0, 6.0, 7.0, 7.2,
8.5, 8.8, 9.0 …), and a conviction-ranked rail refills from one rung up the same
ladder.

So the ruling is implemented and the card is not fixed, and both halves are
reported. The residual is not this constant being mistuned; it is that
**conviction ranking systematically selects the extreme rungs of a ladder**,
because those are by construction the most convinced rows on the card. Two
candidate remedies are named for the next taste pass, neither taken here: a
per-ladder rail cap (the sibling of `RAIL_MAX_PER_PLAYER`), and ranking a ladder
by its PIVOT rung — the one nearest the coin flip — rather than by its loudest.

On the other two cards the filter is a plain win: `14788546` loses six Brady
Singer rungs all priced 5.0% and gains a real question, and `15199902` promotes
the two 92.5% rows, one of which turned out to be the game's second-biggest
surprise. **Nothing it suppressed was among the top five surprises on the one
payload where the answers are known** — the safety property, asserted rather
than assumed.

## Where it lives

`frontend/lib/propDivergence.ts` (`PROP_STRUCTURAL_CERTAINTY`, `DivergenceRow.
structural`, the family pass in `buildCandidates`), filtered only in
`selectDivergenceRows` when `pregame`. `frontend/__tests__/lib/
propStructuralRungs.test.tsx`, 36 tests. The rule is applied without an escape
hatch, so a card whose every high-conviction question is a ladder rung empties
the rail and says so (`emptyReason: "structural"`) — ruling 027's honest-empty,
because a filter that quietly un-applies itself is two behaviours wearing one
name and the second only ever runs where nobody is looking.
