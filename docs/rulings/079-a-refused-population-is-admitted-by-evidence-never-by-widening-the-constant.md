# RULING 079 — A refused population is admitted by ATTENDED EVIDENCE, never by widening the constant that refused it

date: 2026-08-18
author: Alex
issues: #1947, #1779, #1798

## The ruling

When a safety predicate refuses a population, there are exactly two legitimate next moves:

1. **Leave it refused.**
2. **Run an ATTENDED mini-census: evidence per member, gathered from a source outside the
   predicate**, and act only on what that evidence says — per member, never per population.

**Relaxing the constant that produced the refusal is not one of them.** A threshold is refusing
because it cannot tell two cases apart. Widening it does not teach it the difference; it deletes
the question and keeps the answer.

Concretely, for `MAX_ABSORPTION_SEPARATION_SECONDS` (#1947): lowering it is safe, raising it is a
ruling-048 amendment, and "these four look fine to me" is never the argument. If a member should
be drained, the census says so with evidence and it is drained as an attended, member-scoped
action — an `MC` is written **only if deletion is actually warranted**, and never as the census's
default outcome.

## Why — the census inverted the verdict on its first run

This ruling was issued to bound a policy question and paid for itself in the same window it was
written.

Four MLB event pairs were rendering LIVE 40–51h before their own `commence_time`. They shared an
`espn_id`, agreed on matchup, and were recorded as *"true duplicates — same `espn_id`, same
matchup, same score"* that no rail could drain because the separation arm refused them. The open
question put to Alex was whether to admit them.

The attended census went to the provider instead of to the constant, and every id **dereferenced
to a single, FINAL, 2026-08-17 game** — while the ESPN scoreboard showed all four matchups
genuinely recurring on Aug 19/20 under **different** ids, at times matching our rows **to the
minute**:

| our row | our `commence_time` | our `espn_id` | the REAL game at that time |
|---|---|---|---|
| 15199901 | 08-19 16:35 | `401816564` (Aug 17) | `401816587` Tigers @ Pirates, 08-19T16:35Z |
| 15199882 | 08-19 17:10 | `401816566` (Aug 17) | `401816590` Padres @ Mets, 08-19T17:10Z |
| 15200229 | 08-19 20:10 | `401816562` (Aug 17) | `401816586` D-backs @ Red Sox, 08-19T20:10Z |
| 15199886 | 08-19 22:05 | `401816565` (Aug 17) | `401816588` Marlins @ Phillies, 08-19T22:05Z |
| 15200216 | 08-20 18:10 | `401816568` (Aug 17) | `401816606` Athletics @ Royals, 08-20T18:10Z |

They are **not duplicates**. Each is a **real, correctly-scheduled future game** carrying another
game's `espn_id` and another game's final score — which is exactly why it rendered live. The
"same score" that made them look like duplicates is the contaminant, not the corroboration.

**Widening the constant would have deleted five real scheduled games.** The refusal was correct,
and nobody could have known why until something looked outside the predicate. Note also that it is
five, not four: the fifth sat at 66.5h and fell outside the band the population was named for — a
population defined by the symptom's magnitude will always be the wrong size.

## The general form

A predicate that refuses is reporting **the limit of what it can distinguish**. The information
needed to resolve the case is, by construction, not available to it. So the resolution must come
from somewhere it cannot see — the provider's own schedule, a second source, a human — and it
arrives as evidence about one member, not as a new number.

Ruling 048 already says an id-less claim never absorbs. This is its operational twin: **an
unexplained refusal is never overridden in bulk.**
