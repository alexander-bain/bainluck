# RULING 107 — Drop the unlabelled surprise number; an unlabelled unit invites its own misread

date: 2026-08-20
author: Alex
issues: #195, #2011

From Alex's first read of the UX-P106 capture, alongside ruling 106. Verbatim:

> DROP the unlabeled grey "NN pts" from the how-the-props-landed card. The
> sentence already carries the information ("marked 93% — and it missed"), the
> card stays ranked by surprise, unannotated. Ruling 5 — nothing > unhelpful: an
> unlabeled unit invites exactly the misread it just got.

## What it was

`#2011` gave the settled rail its surprise ranking, and put the ranking key at
the right edge of every row as a grey `93 pts`. The reasoning at the time was
sound in isolation — it is unsigned on purpose, because a `+93` reads as a price
move, which is the thing #2011 had just removed.

But "not a price move" is not the same as "legible". The number arrived with no
unit anyone had met, in a column, beside a verdict, and the first person to read
it asked what it meant. That is the whole finding, and it arrived in the only
way this class ever does: from someone reading the page for the first time.

## The ruling

The visible `NN pts` is dropped from the settled card. The card **stays ranked
by surprise** — the key is not removed, it is not printed.

Nothing is lost, and that is the test this had to pass rather than an assertion
about it: the row still says `marked 93% → MISS`, and above it the escalated
sentence still says *"Freeman's 3+ hits + runs + rbis was marked 93% — and it
missed."* Ruling 5 is *nothing beats unhelpful*, not *less is more*; if the
sentence had stopped carrying the mark and the outcome, dropping the number
would have left a card that said nothing.

## The one place it survives, and why that is not an exception

The detail view's screen-reader line still says `93 pts from the mark`.

The failure mode being ruled out is a bare number in a column with no referent.
Spoken with its referent attached it does not have that failure mode, and
dropping it would cost a screen-reader user the only signal a sighted reader
gets for free from the row ORDER. The rule is about unlabelled units, not about
the number.

`backend`-side there is nothing here; `frontend/components/PropTravelBar.tsx`
keeps `surprisePoints()` for exactly that one consumer, and the guard asserts it
appears in no visible cell.

## The general clause

**A unit the reader has not been taught is not information, whatever it
measures.** The instinct that produced it — *show the ranking key so the order
is explicable* — is a good instinct answered in the wrong register: an order is
explained by prose or by nothing, not by exposing its sort key.

Verified by before/after capture of the same card
(`.claude/handoff/artifacts-ux-p107/crop-{before,after}-settled.png`, event
`15199902`): the grey `93 / 93 / 92 / 83 / 48 pts` column is gone, every other
pixel and the row order are unchanged.

**First-read bar, as far as a test can carry it:** every number remaining on the
settled rail sits inside a sentence that names it (`marked NN%`), asserted in
`frontend/__tests__/lib/propPregameDirection.test.tsx`. A test cannot run the
first-read test — only a reader can, which is how both of this cycle's rendering
rulings were made — but it can pin the property the reader was reacting to.
