# RULING 051 — Below its evidence floor a source is ABSENT, not stale: drop it and re-weight, never freeze

date: 2026-08-14
author: Alex
issues: #1841 · #1829 · #1828

> **The sportsbook consensus has a FLOOR OF THREE BOOKS. Fewer than three books quoting a
> moneyline means no sportsbook consensus exists — so the `betting` source contributes NOTHING,
> and the blend re-weights over whichever sources remain fresh.**
>
> **Never freeze. A refused source is not held at its last value; it is not there.**

## What produced it

#1841's measurement, on event 15192596 (Red Sox @ Blue Jays, 2026-08-13). Books pull the moneyline
when a game goes out of reach, and they pull it one at a time:

| time (UTC) | books still quoting | value |
|---|---|---|
| 20:55 | 12 | ~0.12 |
| 21:05 | 3 (fanduel 0.0140, betmgm 0.0288, rebet 0.1347) | 0.0592 |
| ~21:08 | **1** (rebet) | **0.1347** |

`win_probability_sources['betting']` ended at **0.1347** — one minor book's last quote, standing in
for "the sportsbook consensus", after the two sharper books pricing the same game at 1–3% had
already stopped. That is what the weighted median landed on to render **87 – 13** for a team
trailing 5-0 in the 9th.

The count did not collapse in one step and there was never a moment where anything looked broken.
Twelve books is a consensus, three is a thin one, one is an opinion — and the same field, with the
same name, carried all three readings without changing shape.

## Why the floor, and why three

Two is not a consensus, it is a disagreement with no tiebreak; a single outlier moves the median
to the midpoint of itself and one other quote. Three is the smallest population where a median
means what the word median implies — one book cannot carry it, and the odd one out is visibly the
odd one out. Below three, the honest statement is not "the consensus is X"; it is **that there
isn't one**.

This is why the floor is on the *count*, not on the *spread*. A wide spread is a real signal about
a live market. Two books that happen to agree closely are not evidence of consensus — they are two
books.

## Why DROP, and not freeze

The tempting alternative is to hold `betting` at its last well-supported value and let the blend
keep using it. That is worse than doing nothing, and the reason generalises past this source:

**A frozen value keeps its label while losing its referent.** Nothing downstream can tell "the
books say 13%" from "the books said 13% before they stopped saying anything", because the field
carries a number in both cases and a number is what the reader was promised. This is gotcha #53's
shape arriving through the blend instead of through an API: the emptier reading and the real
reading are rendered identically, so any consumer that infers a fact from it is inventing one.

Dropping is honest in a way freezing cannot be. When `betting` is absent, the blend re-weights over
the sources that are still reporting, and the hero it produces is a *current* answer built from
*current* evidence. It may be a worse-informed answer than a twelve-book consensus would have been.
It will not be a wrong one wearing a confident label.

And there is a product argument that decides it independently: the games where books pull the
moneyline are exactly the games that are **over**. Freezing puts a ghost of the betting market on
the one class of game where the ghost is loudest and the truth is least in doubt — a 5-0 ninth
inning — which is precisely the "settled means settled" failure the standing ruling forbids.

## What this is NOT

It is not #1829. #1829 stops a **stale** `betting` from out-voting fresh sources — a rule about
age. This is a rule about **support**: a value can be seconds old, perfectly current, and still be
one illiquid book's opinion presented as a market. #1841 exists because #1829 does not close it.
Both are needed and neither implies the other.

It is also not a threshold tuned to a specimen. Three is the structural minimum for the statistic
being computed, which is why it does not move when the next specimen arrives at four books or two.

## Implementation

The two non-policy halves shipped in queue 350 (`3f4e07eb`, PR #1850) and are the substrate:
**median rather than mean** across books, and **`betting_book_count`** recorded alongside the
value. The median alone narrows the defect without closing it — with one book left, the median
*is* that book. The policy half implements against those two.

Acceptance, as ruled:

1. The **87–13 specimen replayed under the policy yields the fresh-source hero** — not 87–13, and
   not a re-weighted average that still contains rebet.
2. A **below-floor game shows the blend without `betting`**, rather than with a ghost of it. The
   absence must be observable as an absence: the source is not in
   `Event.win_probability_sources`, and the weighted median re-normalises over what remains.

## The general form, worth asking of any aggregate

**Every derived-consensus field needs a support count and a floor, and below the floor it must
report absence rather than a last value.** The count is what turns "we have no evidence" into a
representable state; without it, no-evidence and weak-evidence and strong-evidence are the same
float. `betting` is the specimen because books visibly withdraw, but the shape is not specific to
sportsbooks — any source that averages over a varying population of contributors can degrade to
one contributor without the field changing shape.
