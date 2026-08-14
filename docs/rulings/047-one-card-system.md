# RULING 047 — One card system: every surface renders through the shared cards

date: 2026-08-13
author: Alex
issues: #1743, #1741

Every surface that shows an event or a market renders it through the **shared
card components**. League pages get **no bespoke variants**. A new card type
requires a **design ruling first** — it is not a thing a queue decides while
building a page.

Named failure: the **MLB league page's non-standard cards**. Nobody chose to
fork the card system; a page needed to show something the shared card did not
cover, and the cheapest move at that moment was a local variant. Repeat that
per page and the product stops having a card system and starts having a
collection of pages that each look nearly right.

## The three retrofits this ruling settles on the league page

| content | renders as |
|---|---|
| events | the **standard event card** — the same one Discover and the sports feed use |
| date-ladder props (debut dates and their shape) | the **existing heatmap card** |
| yes/no markets | **single-row binary presentation** |

**Two rows per binary is ruled out.** A yes/no market is one question with one
answer; rendering it as two rows makes the reader do the arithmetic of noticing
that the rows are complements, and invites the eye to read them as two
independent markets. It is the same disease as showing source divergence: a
presentation that hands the reader a reconciliation problem the product exists
to have already solved.

## WHY

**A card is a promise about what a thing IS, not a container for whatever a
page happens to have.** When a reader learns the standard event card — where
the probability sits, what the chip means, what tapping it does — that learning
has to transfer to every surface, or it is not learning, it is per-page
memorisation. A bespoke variant spends the reader's accumulated fluency to save
one queue an afternoon.

This is also why the escalation path is a **design ruling and not a code
review**. A reviewer looking at one page diff sees a reasonable local choice;
the cost is only visible across surfaces, which is exactly the view a diff does
not have. So the question "should this be a new card type?" has to be asked
somewhere that can see all the surfaces at once, and it has to be asked
**before** the variant exists — because once it ships, the argument becomes
"we already have one", and that argument has never lost.

## Scope

This governs **presentation**, not payload. A page may absolutely need data the
shared card does not yet carry; the answer to that is to extend the card's
contract (and its tier declaration) — which every surface then benefits from —
not to render a different card. #1762's per-element backend producers are the
worked example of the right direction.

Related: [[031]] (identity over popularity — the same instinct, applied to
matching), and the entity-page tier system in
`docs/entity-page-templates.md`, whose chrome-earning grammar assumes one card
vocabulary underneath it.
