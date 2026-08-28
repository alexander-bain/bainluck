# RULING 147 — A surface that shows an event shows it through THE event card, and the whole card is the target

date: 2026-08-28
author: Alex, reviewing the UX-P152 artifact — relayed through the UX-P154 runner directive,
executed by the program-ux lane
issues: —

**Alex's words, quoted (ruling 144),** on panel 4 of the UX-P152 artifact:

> *"it kinda feels like we're reinventing the event card inside the tournament product"*

And the instruction: **NO "See more on this match" link row — the whole match card is clickable,
exactly like every other card in the product. The tournament list uses THE standard event-card
component, full stop.**

**Binds:** every list of events, anywhere in the product.
**Extends:** ruling 047, whose acceptance was already *"the league page renders the SHARED event
card"*. This says the same thing about every other surface and adds the interaction half.
**Sits beside:** ruling 145 — the same clause about a different shape. A bespoke solution to a
systemic shape is a defect.

---

## The case

The tournament match list drew its own bordered container, its own row dividers, and its own
tap behaviour: the row was a `<button>` that opened an accordion, and inside the accordion was a
link reading *"See more on this match"*. Everywhere else in the product, a card IS a link.

So a reader who taps a match card gets an accordion, learns that this list works differently from
every other list on the site, and pays that cost on every row for a fact worth one row. And the
card itself was a second implementation of a card we already have — one that will drift, because
two implementations always do.

## The ruling

**A surface that shows an event renders it through the shared event card, and the whole card is the
navigation target. A link row inside a card is a defect.**

Three properties, and the second is what makes the first checkable:

1. **One `<Link>` wrapping everything.** No link row, no accordion standing between the tap and the
   page. Where there is nothing to navigate to, the card renders INERT — no anchor, no pointer, no
   hover lift — because a card that looks pressable and is not is worse than one that plainly is
   not.
2. **The card announces which component drew it.** `data-testid="event-card"`, emitted by
   `EventCardShell` and by nothing else. *"This surface renders the shared card"* is a claim about
   the DOM, and it is unanswerable from the DOM unless the shared card marks itself. A guard asserts
   there is exactly one emitter in the tree.
3. **Live / finished / hover treatment is decided in ONE place**, so two surfaces cannot drift into
   two ideas of what a live card looks like.

## What "THE component" means here, and the cost of the literal reading

The literal reading is that the tournament list renders `EventCard`. UX-P154 did **not** do that,
and the reason is a collision with a standing ruling rather than a preference — recorded here so
Alex can overrule it knowing the price:

- `EventCard` resolves its faces from the team name at render time (`espnTeamLogoByName`,
  `flagUrl`, `teamColorStyle`). The tournament surfaces are under Alex's ruling 8 — a player's face
  is **pinned in the register and never resolved client-side**. Feeding two tennis players through a
  team-logo lookup is how a basketball crest ends up beside Sabalenka.
- It has no seat for a SEED or for the title chip, both of which are rulings 1 and 8 on this list,
  and it would print *"Alcaraz at Bellucci"* for a match played at nobody's home.
- It keys everything off `event.id`, and **28 of the register's fixtures dereference to no `events`
  row** (the qualifying draw was never ingested). Those rows would have no card at all.

So what shipped is `EventCardShell`: the link, the card, the marker and the state treatment shared;
the contents left to the surface. The tournament list renders the same component, marked the same
way, behaving the same way, and keeps the facts a tennis draw has that a two-team game does not.
**If the literal version is wanted anyway, the change is `EventCard` growing a `sides` slot — not a
second card growing features.**

## A moved feature loses one half unless both are guarded

Deleting the accordion moved two things, and each is held in the place it landed AND in the place it
left:

- **Where to watch** → the event page (`TournamentExtensions`). Ruling 7 said it belongs *"in the
  DETAIL view"* rather than on every row; the detail view is now the page the tap arrives at. The
  positive is guarded in `tournamentExtensions.test.tsx`; the negative — that it did not quietly
  come back onto the row, including in the per-match case — in `tournamentMatches.test.tsx`.
- **The one sentence** (ruling 6's `detailNote`) → onto the card. It only fires when it adds
  something the numbers cannot say, and it was behind the tap only because the drawer happened to
  exist.

## General form

**Interaction is part of the component, not part of the page.** A surface that reimplements how a
card is pressed has reimplemented the card, whatever it reused of the styling — and the reader pays
for that in the one currency they cannot get back, which is knowing what will happen when they
touch something.

---

## AMENDMENT — the literal version is NOT wanted. Alex, 2026-08-28 ~4pm PT

This ruling's text above ends by naming the two ways to satisfy it and putting
the cost of each on the record: `EventCardShell`, which shipped, or `EventCard`
growing a `sides` slot, which would be the literal reading of *"the tournament
list uses THE standard event-card component, full stop."* The question went back
to Alex with that cost, and it is now answered.

Relayed through Fable's `019-cert-430-repair.md`, in that file's words rather
than Alex's own (ruling 144):

> **Item 9: option (a) RULED — keep EventCardShell (shared shell, marker,
> behavior; tennis facts intact). No literal-EventCard migration.**

So the shape above is final, not provisional, and the three properties it lists
are the whole of what *"the standard event-card component"* requires: one shared
shell, one marker, one behaviour. A future queue proposing the `sides`-slot
migration is proposing to reopen a closed ruling and needs a new reason — not
this file's own sentence, which was a costing, not an invitation.

**What is NOT loosened:** a second card growing features is still the defect.
`EventCardShell` is a shared component, and the day a surface reimplements the
link, the card, the marker or the state treatment beside it, this ruling has
been broken however tennis-shaped the contents are.
