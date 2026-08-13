# RULING 041 — Search ranks by MATCH CLASS, and an entity ranks only on evidence it OWNS

date: 2026-08-12
author: Alex
issues: #993, #1206, #1494

Search ordering is **tier-lexicographic**. A candidate's match class decides its
position first; knobs tune ordering only *within* a class and can never lift a
candidate across one. And a candidate ranks **only on evidence it owns** — its
own name, its own aliases, its own outcomes. Never on a member's content, never
on anything derived. Derived-only evidence is UNRANKABLE: excluded, not demoted.

The classes, best first:

| class | meaning |
|---|---|
| MC0 | exact full-alias equality, **unfolded** (no stemming, no accent strip, no punctuation strip) |
| MC1 | every query token present in the entity's own name (folding allowed from here down) |
| MC2 | prefix match on the last query token |
| MC3 | partial token match |
| MC4 | outcome-only evidence — a market matching on its own outcomes |
| MC5 | fragment / fuzzy (trigram) |

Ties inside a class break by kind: **market > event > team**. No intent
classifier — `hurricane` resolves to the weather market because a market
outranks a team at equal class, and `celtics` resolves to the team because the
team matches *better* (its alias is exactly what was typed). That is what "team
floor" means: teams sit at the bottom of kind order and win by matching better,
never by being handed a slot.

Knobs: **at most eight**, defaults provisional until a measured run. A knob move
is accepted only if net flips ≥ 2·√f on the test split; at most two moves per
cycle; one ranking change in flight at a time.

Typeahead is the **measured surface**. `/search` follows the same order.

## Why

Two measured failure families, production v3792, 2026-08-12 21:48Z, `entity_top_1`
30/44 with 14 failures — eleven of them these two:

**Concepts ranked on evidence they did not own.** An event concept assembled
from a member market inherited that market's match and then presented itself as
the answer. Four separate gold queries — `super bowl`, `world series`, `wwe`,
`stranger things` — all answered `concept:event:awards:emmys`. The Emmys concept
matched none of them; a market underneath it did. Demotion is not the remedy,
because a wrong answer that merely sorts late still wins every time the right
answers are absent. Exclusion is.

**Nothing ranked the kinds against each other.** `/typeahead` merged its answer
from fixed slots — one hub, one team, two events, one concept, two markets — so
a team held the top slot on any query that produced one, whatever it had matched
on. `ai` answered *1. FC Kaiserslautern*, `ipo` answered *Asteras Tripolis*
(tr-**ipo**-lis), `british open` answered a team called *Brito*. Each pool was
well ordered internally; no relevance signal existed in the merge at all. A
guaranteed slot is precisely a promise to show something irrelevant whenever
nothing relevant matched.

Tier order is what makes the second family impossible: a fragment lives in MC5
and cannot outrank a token match, whatever kind it is. Owned-evidence-only is
what makes the first impossible: a concept with no owned basis does not appear.

## Provenance of this file, which is part of the ruling

The ratified spec was delivered **untracked and was lost** — it never entered
the repo, and its twelve property invariants were lost with it. This file and
`docs/search-scoring-spec.md` are a reconstruction of decisions Alex ratified by
MC on 2026-08-11, written down and committed *with the code they govern*
precisely so the loss cannot repeat. The reconstruction judgments not covered by
the ratified text are enumerated in the spec rather than smoothed over.
