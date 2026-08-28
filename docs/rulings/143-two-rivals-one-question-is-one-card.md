# RULING 143 — Two rivals asked one question are ONE card, with both numbers on it

date: 2026-08-28
author: Alex
issues: #2199

## Alex's words

Delivered in his Fable session (MC), 2026-08-28 ~10:45am PT, and quoted rather
than paraphrased because a paraphrase is what made this a three-queue problem:

> ONE COMBINED CARD — "Who wins a second major this year?" — showing BOTH
> players' probabilities (Alcaraz 2+ majors, Sinner 2+ majors, each from its own
> real Kalshi market: KXGRANDSLAM-CALC26-family and KXGRANDSLAM-JSIN26).

## The case, and why it took three queues

The US Open register carried two curated questions:

| key | question | market | answer leg |
|---|---|---|---|
| `alcaraz-second-major` | Can Alcaraz win a second major this year? | `KXGRANDSLAM-CALC26` | `2+ Grand Slam wins` = .25 |
| `sinner-second-major` | Can Sinner win a second major this year? | `KXGRANDSLAM-JSIN26` | `2+ Grand Slam wins` = .555 |

**UX-P138.** Alex's note said the pair was *"one templated question with the name
swapped"*, and ruling 8 of that queue banned *"a repeating template"*. What
shipped for it deleted Alcaraz — at render time, through a near-duplicate cap
keyed on the topic with the leading token stripped, and then in the file by hand.

**UX-P147.** Alex overruled that, verbatim: *"alcaraz-second-major and
sinner-second-major are DIFFERENT PLAYERS and must both render. Key the
near-duplicate rule so it never collapses across players."* And: *"I'd love to"*
see both. Alcaraz came back, the cap was rekeyed on the whole register key
(ruling 139), and the repetition came back with him.

**Both notes were right, and both readings were partial**, because both assumed
the unit is ONE CARD PER MARKET. Drop that assumption and the two constraints
stop fighting: one card carrying both men's numbers has every player present and
prints no question twice, which is the whole of what each note asked for.

## The ruling

**Where two curated markets answer the same question about different subjects,
the register may compose them into ONE card whose rows are the subjects.**

Four things follow, and each of them is a guard rather than a convention:

1. **A combined card names NO answer.** Two legs means no single outcome answers
   the question, so `answer_entity_key` is `null`, the renderer ranks instead of
   leading, and the "which number goes in the big type" question never has to be
   guessed. This is the field shape `validate_prop` has supported since UX-P134;
   this is the first curated card that uses it.
2. **A missing leg REFUSES the whole write.** A comparison card with one side is
   not a smaller card — it is "Who wins a second major?" with one man under it,
   which reads as an answer and is not one. That is the same defect UX-P134 fixed
   when it stopped a ladder maximum answering a calendar-slam question, and it is
   the defect both earlier queues shipped. The population pass exits non-zero.
3. **The rows are RENAMED, and the rename is recorded.** The source's own outcome
   name for both legs is `2+ Grand Slam wins`; printing that twice would be a
   threshold ladder, and what the reader is comparing is two MEN. The register
   carries `evidence.legs[].source_outcome_name` → `renamed_to` so the rename is
   traceable, the same doctrine as the matchup `sides` mapping: an identity
   decision made once against the evidence, never a request-time guess.
4. **The legs are NOT normalised.** There are four majors a year and each man
   needs two of them, not the same two, so both markets can resolve Yes and the
   two numbers do not sum to 100. A card that made them add up would assert an
   exclusivity the markets do not have — the same rule the cycling GC field
   carries, and gotcha #23 in the other direction. Because the title Alex wrote
   (*who* wins) reads as a race, the hook is load-bearing rather than decorative:
   *"These are two separate questions — they could both do it, or neither."*

## What this does NOT do

**It does not weaken ruling 139.** A near-duplicate rule still may never collapse
across subjects, and the render-time cap is unchanged. A REGISTER composing two
markets, offline, with both named and both rendered, is a different act from a
cap deciding at render time which of two curated cards a reader gets. The first
is curation; the second is a silent deletion. Ruling 139's guards are kept with
synthetic keys precisely because the clause outlives its case (ruling 081) — the
next two same-topic cards to be curated must not lose one.

**It does not license combining anything that merely looks similar.** The
composition is written by hand, market by market, in `COMBINED_CURATION`, and the
pass refuses if a market is claimed both as its own card and as a leg.

## The shipping truth on the day it was ruled

Both Kalshi markets were last read **2026-07-24**, so on merge the card is 856
hours old, rotates out under the page's own dark rule, and the section keeps its
empty state. What ships today is the SHAPE; the card appears the day those two
markets are read again, which is what the registered-market refresh arm (window
424, unmerged) is for. Recorded here rather than in a report because a ruling
whose visible effect is deferred will otherwise be re-litigated as unshipped.
