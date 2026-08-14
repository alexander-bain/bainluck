# RULING 053 — A binary card leads with the side its own question names

date: 2026-08-14
author: Alex
issues: #1860, #1743

A card headed **"Will X happen?"** leads with the **Yes** side, named. One row.

Rendering **"No 94.9%"** under that heading hands the reader the *complement* of
the question they just read, in the position where the answer goes. The number
is correct; the line is the wrong side of it.

**Multi-outcome series keep both sides.** There, two rows are two answers, not
one answer stated backwards — the reader is choosing among outcomes rather than
reading the verdict on a question. The rule is about the binary case, and it is
about the *lead* line specifically: a binary card may still expose the other
side on tap, in a detail row, or in the chart. What it may not do is put the
complement where the answer goes.

Named failure: the MLB league page, measured under the ruling-047 retrofit —
**15 of 21 binary markets led with the complement of their own question.**

## WHY

**This is a communicates-green failure sitting inside standard-looking cards.**
Every one of those 21 cards rendered correctly. The probability was right, the
colour was right, the card matched the design system, and a screenshot of the
page would have passed any check that asks whether the surface rendered. It
still told 15 readers the opposite of what they asked. That is ruling 044's
distinction — rendered-green is not communicates-green — reaching a case where
the surface is not merely unclear but *inverted*, and where nothing about its
appearance says so.

The second reason to bank it rather than just fix it: **the retrofit is what
found this, which means the retrofit justified itself.** Ruling 047 sent the
league page to the shared card system on the grounds that a bespoke variant
spends the reader's fluency. The argument there was about *learning transfer* —
a cost that is real but slow. This is a faster and larger cost, and it was
invisible until the page was made to render through components that ask "which
side is the answer?" A per-page variant never has to answer that question,
because a per-page variant has no other page to be consistent with. So
unification is not only a tidiness gain; **it is a measurement instrument**, and
it found a class of defect nobody had gone looking for.

## Scope

- Binary yes/no markets, on every surface that renders them through the shared
  cards. The lead line is the Yes side, by name.
- Multi-outcome series and ladders are **out of scope and unchanged** — see the
  recorded decision at `FuturesCard.tsx:302-306`, which ruling 047 already
  declined to disturb.
- Where the Yes side has no natural name, the fix is to name it, not to fall
  back to the complement.
