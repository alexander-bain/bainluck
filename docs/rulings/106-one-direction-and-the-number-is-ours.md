# RULING 106 — Every script row quotes the chance it happens, and the number is ours

date: 2026-08-20
author: Alex
issues: #195, #2011, #1650

From Alex's first read of the UX-P106 capture
(`.claude/handoff/artifacts-ux-p107/before-pregame.png`). Verbatim:

> Every script row quotes the CHANCE IT HAPPENS, one consistent direction —
> Stowers reads "5% chance", Schwarber "55% chance". The bar stays centred on the
> coin flip as built. "market says YES/NO" is DROPPED entirely.

## Three faults, one four-word phrase

The shipped row printed a direction word and the probability **of that
direction**. Each row was internally consistent and correct, which is why the
suite was green and why the defect is only visible from a reader's seat.

**1. The number silently changed subject down the page.** Schwarber's 55% was
the chance the thing happens; the very next row's 95% was the chance it does
not. A column of percentages whose subject alternates cannot be scanned, and
nothing in it announces the problem — every entry is true. This is the fault
that made the ruling necessary; the other two are why nothing partial would fix
it.

**2. "NO" read as a verdict** — *the thing didn't happen* — on a page where
nothing has happened yet. That reading is not a stretch: the site's settled
vocabulary really does put a verdict in that position, two elements down the
same screen (#1650, #2011). A pregame surface borrowing the settled register is
the same class as the three-vocabularies defect, arriving from the other side.

**3. "market says" is off-doctrine.** *The blend is the product* — one number
per question. It is our number, not a market's opinion we are relaying, and a
label that hands it to somebody else contradicts the standing ruling that
governs every other surface on the site.

## What replaces it

One cell, right-aligned, reading `5% chance` — the over-side probability,
always, in every state of the pregame rail, including a coin flip (`50%
chance`, which is in the column rather than exempt from it).

Nothing occupies the left cell. The question is named above the bar and the bar
draws the conviction; a legend there would either re-attribute the number or
repeat the bar. Ruling 5 — nothing beats unhelpful.

**The bar is unchanged, as ruled** — still centred on the coin flip, still
growing out to the side it favours, still equal length for 7% and 93%. It
carries the direction as a shape; the number carries it as one consistent
quantity; nothing carries it as a word. Colour stays on the bar and off the
number, where it would read as a judgement about the number.

## The guard, and the shape it reuses

UX-P106's **differential census** is banked practice: render a surface twice
with one input flipped, everything else held, and diff the rendered token
multisets — *the tokens that differ ARE the vocabulary*, so a word nobody
predicted lands in the delta. It was built for the settled verdict axis after a
third spelling of hit/miss shipped.

This is the second vocabulary class, so it gets the same machinery on a new
axis: **flip the PRICE across the coin flip** (7% against 93%) and the delta
must be **empty**. Under the shipped design it contained `YES`, `NO` and `not`.
The helpers are now one implementation shared by both suites
(`frontend/__tests__/helpers/renderedTokens.ts`) rather than two copies free to
drift about what a reader receives.

**It paid out immediately, twice, against its own author.** The census caught a
"market" attribution surviving in the rail's `sr-only` header — a place a
capture cannot review — and then showed every number being announced **twice per
row** to a screen reader, because restating the ruled sentence in the detail
view's `sr-only` paragraph made it identical to the bar's own `aria-label`. That
paragraph is gone for pregame; the in-game and settled ones stay, because their
bars draw a journey a screen reader cannot see.

## The general clause

**A number is not readable until its subject is fixed across every row that
prints it.** Per-row correctness is not the property a reader consumes; a column
is. This is why the defect survived a green suite, a code review and a shipped
release: every test that could have caught it would have had to compare two
different rows, and tests are written one row at a time.

Verified by before/after capture of the same card
(`artifacts-ux-p107/{before,after}-pregame.png`), with the in-game state as a
control — byte-identical, 104,750 bytes both sides.
