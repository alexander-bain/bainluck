# RULING 140 — An inference may reach a user surface only where an independently-pinned population can replay it as a test

date: 2026-08-28
author: program-ux lane (UX-P149) — **a lane judgement made in the course of the Q426 match-props
ship, FLAGGED TO ALEX FOR RATIFICATION, not self-certified**
issues: #1946

**Binds:** every place a user-facing surface derives an identity — a player, a team, a side, a
subject — from text rather than from an id.
**Sits beside:** ruling 048, which draws this exact line for ABSORPTION (an id-less claim never
absorbs). This is the same line drawn for DISPLAY.
**Applied by:** UX-P149 (`backend/app/utils/tournament_match.py`, `attribute_yes_side`).

---

## The case

Lane1's Q426 note routed the US Open match props to the match's own page, grouped under the
match-winner market, and handed the surface to this lane. Building it ran into one thing that
cannot be looked up:

**Polymarket stores a match prop's two outcomes as the literal words `Yes` and `No`, and which
player is `Yes` is not stored anywhere.** `futures_outcomes.name` is the word. The external id is
`{condition_id}_yes`. The label the source printed — *Aziz Dougaz* — is dropped at ingestion.

The register solves this for the match-WINNER market: `sides` is pinned offline, once, against the
source's own ordered labels, and that is why the slate can print two players instead of Yes and No.
It cannot solve it for the props. Twelve markets per match across ninety-six matches is not a
hand-reviewable population, which is lane1's own third reason for keeping them off the register.

So the page either infers the attribution or ships without its most legible half — "Who wins set 1"
is the question closest to the one the reader came for, and `Yes 53%` is not an answer to it.

## The ruling

An inference may reach a user surface **only where an independently-pinned population exists over
which the same rule can be replayed as an executing test.**

Here that population is the register's own 28 live matchups. Their yes/no → player mapping was
established offline, from the source's ordered labels, by a different process on a different day —
so it is not this rule's own output, it is a second and better source for the same fact. The rule
is: *`_yes` is the player named FIRST in that market's own title.* Replayed over those 28 titles it
holds **28 of 28, zero violations**, and
`backend/tests/test_tournament_match.py::test_the_yes_side_rule_holds_on_every_register_pin` runs
that replay against a committed capture of the real production titles. The day Polymarket flips the
convention, the register's own pins turn red — rather than the page quietly printing a number under
the wrong player's name.

**What this forbids** is an inference with no such population: a rule whose only evidence is that it
looked right on the rows somebody eyeballed. The distinction being drawn is not confidence. It is
**falsifiability by data we already hold.**

## What a soft corroboration is worth, stated as a number

There is a second, weaker check available on the prop class itself: a set-winner probability should
sit near its match-winner probability rather than near its complement. Measured opening-vs-opening
(the only settlement-immune basis — see below), it gives **51 agree / 2 disagree**, both
disagreements marginal and one of them a coin-flip match, mean gap **−0.16** in favour.

That supports the rule. It cannot establish it, and it is recorded here as a number precisely so it
is not later remembered as a proof. A corroboration whose oracle is itself noisy tells you where to
look; it does not tell you that you may ship.

*(The first run of that check used CURRENT prices and reported 10 disagreements. Every one was a
settled match-winner market compared against an unsettled prop. The oracle was wrong, not the rule
— which is the second reason a soft check may not be load-bearing: its own failure modes are
usually less well understood than the thing it is checking.)*

## Three obligations that come with the licence

1. **Refuse rather than guess.** Both players must appear in the title as whole words, at distinct
   positions, on tokens that are not shared between them; a handicap's minus must be on the
   first-named side. Any of those failing yields no card. Measured: **0 of 205** real prop titles
   refused today — so the refusal path is a guard and not the normal case, and that too is asserted
   (`test_no_real_prop_title_is_refused_today`) so a future tightening has to show its cost rather
   than quietly emptying the page.

2. **Count every refusal into the payload.** `props_dropped` carries named reasons. A surface that
   silently omits what it could not attribute reads as complete.

3. **Read the item's own evidence, never a sibling's.** **5 of 73** real prop titles name the
   players in the OPPOSITE order to their own match-winner market — every one a Set Handicap, where
   the source puts the favoured side first. Inheriting the order from the winner market would have
   mis-attributed all five, and each of those five would have looked entirely plausible on the page.

## Why the bar is here and not lower

A wrong number under a real player's name is the worst thing this page can print. It is not visibly
wrong, it is not self-correcting, and the reader has no way to detect it. Everything else on the
match page — the counts, the totals, the margins — needs no attribution at all, and **128 of the 206
prop markets in the measured corpus are Over/Unders**, which is to say the inference is buying the
minority of the page. A rule that risks the worst defect for the smaller half of the value has to be
the one we can prove.
