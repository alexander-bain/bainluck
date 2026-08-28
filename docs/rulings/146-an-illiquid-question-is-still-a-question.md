# RULING 146 — An illiquid question is still a question: a prop is never hidden for age, and the age says what it is the age OF

date: 2026-08-28
author: Alex, reviewing UX-P149/P150/P151/P152 — relayed through the UX-P154 runner directive,
executed by the program-ux lane
issues: —

**Alex's words, quoted (ruling 144):**

> **NEVER EXCLUDE PROPS.** Illiquid props render with honest freshness indication, never hidden —
> *"that's part of the value of the product."*

And, on the treatment:

> **Staleness is per card, not per section**, because liquidity varies within a section. The
> *"32 hours ago"* ambiguity is real — created? updated? last traded? Define what the timestamp
> MEANS, label it so a reader knows. *"Continuing to riff on this until we have a better solution
> would be great"* — *"this is an open riff, not a settled design."*

**Binds:** every surface that decides whether a curated question appears.
**Overrules:** the second half of UX-P138's ruling 8 — *"when a prop resolves or goes stale, it
rotates out"*. The first half (an advance-to-round question is a grid cell, not a prop) stands.

---

## The case

`More predictions` on `/tournaments/us-open` has been **empty on production every day since it was
built**. Not intermittently: every day. The register held three curated questions, all three were
older than the 48-hour boundary, and ruling 8's rotation dropped all three. Four separate queues
then improved the wording of the apology that appeared in their place — UX-P139 made the empty box
visible, UX-P145 rewrote it into the reader's vocabulary, UX-P150 trimmed the venue names, ruling
142 removed the promise at the end of it. Every one of those was the right fix to the wrong object.

## The ruling

**A curated question is never removed from a surface for being old, for looking settled, or for
being thinly traded. Freshness is a TREATMENT, never a filter.**

Only one removal survives on this section, and it is a relocation rather than a hiding: an
advance-to-round market is a cell in the playoff grid and renders there, and the section says so.

## Why the old rule was wrong, and it is not "we lowered the bar"

A thin market on a real question is not noise to be filtered — **it is the product**, because the
places a reader could otherwise go do not have that question at all. What makes an old number
dangerous is presenting it as a current one, and the honesty treatment already solves that
completely: a non-live number is muted, never in the confident type, and says its age. Deleting the
card solves the danger by deleting the value.

**And the settled case is worse than the old case.** `propIsResolved` INFERS settlement from a
probability sitting at a rail, which on an illiquid market is a guess. Inferring settlement and then
HIDING the card is the worst available combination: a wrong guess the reader has no way to notice.
So a card that looks decided is LABELLED "Looks decided" — the strength of the word matching the
strength of the evidence — and real settlement detection is owed by the ingest lane, not by a
render rule. **Flagged to lane1 by UX-P154.**

## What the timestamp means, and it is none of the three things Alex named

Traced to the query. `age_hours` derives from

    MAX(futures_odds_snapshots.captured_at) WHERE probability IS NOT NULL

(`backend/app/routes/tournaments.py::_load_prices`), and every refresh writes a snapshot whether or
not the number moved. So:

> **"Last number 32 hours ago" = the last time a probability for this question reached us.**

Not when the market was created. Not when the venue last updated a row —
`futures_outcomes.last_updated` was measured a month stale against running snapshots on day 1, which
is exactly why the route does not read it. Not when it last traded; we do not receive trades.

**And the limit of what it can say, because the label must not over-claim.** "32 hours" has two
possible causes and the number cannot tell them apart: the market may be quoted and untraded, or our
reader may not be covering it. Both are *"no new number reached us in 32 hours"*, which is therefore
what the copy says — a fact about our knowledge, not a claim about the market's activity. Writing
"nobody has traded this in 32 hours" would be inventing the half we do not have.

## Three obligations on the treatment

1. **Per card, never per section.** Liquidity varies within one section — one question quoted every
   fifteen minutes above one that has not moved in a month — and a banner over both is wrong about
   one of them. The card is as fresh as its OLDEST printed outcome, and when only some are old it
   names which.
2. **The unit is defined once, in the section.** "Last number" is a definition, not a status; four
   repetitions of a footnote is a footnote nobody reads. The status is on the card; the unit is under
   the section, and only when something on screen needs it.
3. **A live card says nothing at all.** A healthy card that keeps apologising teaches the reader
   that the apology is decorative.

## The riff is open, and the variants are a real seam

Alex asked for 2–3 variants of illiquidity surfacing and said explicitly that this is not settled.
So `FreshnessVariant` is a prop on the shipped component — `labelled` (default), `sentence`, `dot` —
and the artifact renders all three from that component with the same real data, because a drawing of
an alternative proves nothing about what it would look like on the page. The default is pinned by a
test so production cannot drift onto one by accident.

`labelled` is the default because the ambiguity Alex named is a WORDING problem, and the chip is the
only one of the three that carries the label on every card without spending a line on it. `dot` is
the one to try if the section grows past a handful of cards.

## General form

**A surface may change how loudly it says something is old. It may not decide, on the reader's
behalf, that they would rather see nothing.** The two are constantly confused because both are
called "quality", and only one of them costs the reader something they cannot get back.
