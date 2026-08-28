# RULING 141 — Venue names are not part of the product a reader bought

date: 2026-08-28
author: Alex (PRODUCT LANGUAGE RULING, permanent and product-wide; directive authored in Alex's
Fable session and delivered through the lane runner Alex launched under his standing
authorization)

**Sits beside:** ruling 138 (`price` is not a word we say to readers) and ruling 142 (a section
states what it IS). The three were issued from one live-page reading and share one guard.
**Swept by:** UX-P150, on the tournament surfaces.
**AMENDED by Alex 2026-08-28, recorded by UX-P152** — the ban was overinterpreted and is now
scoped to narrative/empty-state/promotional copy. Attribution of a number the reader is looking at
is allowed. Read "The clause — AS AMENDED" first; the rest of this file predates it and is marked
where it does.

---

## The clause — AS AMENDED 2026-08-28

> the venue-name ban was overinterpreted. The precise rule: venue names are BANNED in
> narrative/empty-state/promotional copy (the US Open empty-state class — talking ABOUT sources
> instead of showing the product), but ALLOWED — and often good — as SOURCE ATTRIBUTION of a number
> or line the user is looking at.
> — Alex, 2026-08-28 (amendment; **this is the operative text**)

The clause as first written, which the amendment narrows:

> ~~Venue names — "Kalshi" and "Polymarket" — are BANNED in user-facing copy, everywhere. Users get
> our probability, not our sourcing.~~
> — Alex, 2026-08-28 (superseded by the amendment above)

**The two removals already made are KEPT.** The grid legend's *"nobody is answering that question"*
and the board row's *"one reading 20 days ago"* were honest improvements on their own merits and
stand — see "What the honesty was" below. What the amendment stops is the SWEEP: attribution
labels are not to be removed anywhere, and the debt list under "What is owed" is re-read in the
light of the test below rather than paid down as written.

### The test the amendment installs

Ask what the venue name is doing in the sentence:

- **Talking ABOUT our sourcing** — a subtitle, an empty state, a landing blurb, a promise about
  coverage. *"Kalshi + Polymarket, unified"*, *"we asked Kalshi and Polymarket and neither runs
  that market"*. **Banned.** This is the class the ruling was issued against: a page filling space
  with who we buy from instead of showing the reader the thing.
- **Attributing a number or line the reader is looking at** — the label on a faint source line in
  a trend chart, the dot row under a probability cell, a source chip beside a figure.
  **Allowed, and often good.** The reader is looking at a specific number; saying where that
  specific number came from is an answer, not an advertisement, and withholding it makes the chart
  less legible rather than more abstract.

The general clause below still holds for the first class and is scoped to it.

## Why

This is ruling 138's clause applied one level up. That ruling banned the trading layer's *noun*;
this one bans the trading layer's *proper nouns* **where they are the subject**. A reader who
came for a single blended number and is instead told, as the page's own content, which two
exchanges we read it from has been handed the plumbing back after we removed it — and handed a
decision to make about it, which is the decision the product exists to make for them. The standing
ruling is *the blend is the product*: one number per question, and source divergence is a data bug
to fix rather than a feature to show.

*Amendment (2026-08-28).* The sentence that stood here — "a venue name in a caption is that same
feature, smuggled in as attribution" — is the overinterpretation Alex named, and it is withdrawn.
A caption on a line the reader is already looking at is not smuggling the comparison back in; it
is telling them what they are looking at. The blend still leads and is still the product. The
thing being banned is a page whose CONTENT is our supplier list, not a label that answers
"which line is that".

There is a second reason, and it is the sharper one. Naming the venue makes an absence sound like
a coverage problem instead of a fact about the world. The grid legend said *"we asked Kalshi and
Polymarket and neither runs that market"* — which tells the reader we have two suppliers and both
let us down. What is actually true is that **nobody is answering that question**, anywhere, and
that is a more useful and more honest thing to know. The sentence got shorter and truer at once.

## The general clause

**A translated surface may not SELL the sources it translated.** Where the abstraction is the
product, the identity of what sits under it is implementation detail *when it is offered as the
subject*, and putting it in front of a reader in that form converts a finished answer back into a
research task.

(As first written this clause said "may not NAME". The amendment of 2026-08-28 narrows it: naming
a source AS the attribution of a number the reader is already looking at is not selling it. The
same distinction ruling 138's own scope note draws — see
`ruling_no_price_format_scope`: the ban is on odds SOLD as a feature, not odds NAMED as refused.)

## What it does NOT touch

- **Source ids.** `source: "kalshi"`, `group_id: "polymarket:12345"`, `stale_sources`,
  `KALSHI_TICKER_TO_SPORT_KEY`, every enum, every column and every data attribute keeps its name.
  The guard is case-sensitive precisely so that the lowercase ids pass and the capitalised names
  do not, and the sweep runs over rendered text with attributes stripped, so the exemption is
  structural rather than an allowlist.
- **Code, comments, reports, admin.** `/admin` exists so an operator can go and fix the exact
  venue and the exact ticker; a page that will not name them is useless to them. Ruling 138
  already recorded admin as "arguably outside user-facing altogether" and this ruling adopts that.
- **The privacy policy.** A legal disclosure of who we read data from has to name who we read data
  from. `/privacy` is exempt on its face.
- **Deliberate comparison surfaces.** The standing "deliberate comparison surfaces only" carve-out
  survives. `/calibration` exists to publish how well each source predicts, and a source-accuracy
  table with the sources anonymised is not a stronger version of itself. It is LISTED rather than
  exempted, below, because whether a source-accuracy table is "user-facing copy" in the sense Alex
  means is his call and not a sweep's.

## What the honesty was, and how it survived

The failure mode of a copy ruling is a rewrite that removes the word and the meaning with it, so
each of the two removals is pinned in BOTH directions by the guard:

| Was | Is | The fact that had to survive |
|---|---|---|
| `we asked Kalshi and Polymarket and neither runs that market` | `nobody is answering that question, so we have nothing to show` | the cell is blank because the question is unanswered, NOT because we failed to read it |
| `Polymarket 20 days ago` (under a muted board row) | `one reading 20 days ago` | only PART of this number is old — "20 days ago" alone reads as "nobody has looked at this in three weeks", which is false |

The second is the one worth dwelling on. `rowFreshnessLabel` exists (UX-P135) because a row blended
from a one-hour reading and a twenty-day one has to be aged from its OLDEST leg, and a bare age
would then libel the fresh leg. The venue name was never what carried that; the *partitioning*
was. `readingCountLabel` says "one reading" / "two readings" and carries it identically, in the
page's own honesty vocabulary — the same vocabulary as `"no reading yet"`, which was already
there.

## What is owed — RE-READ AGAINST THE AMENDMENT, not paid down as written

**Amendment note (2026-08-28):** every item below was listed under the unamended clause. Under the
amended one each needs the test applied — and several are attribution, not narrative, which means
they are NOT debt and must not be swept. They are left in place verbatim so the re-read is a
visible act rather than a quiet deletion, and the `OWED` map is not to be paid down until each line
has been classified.

Provisional classification, for whoever picks this up:
- **Narrative / promotional (still owed):** the shared landing blurbs; `/about`; the section
  subtitles on `/weather`, `/politics`, `/categories/golf` that read as coverage claims.
- **Attribution (NOT owed — leave them):** `SourceComparisonRow`, the source chips beside figures,
  and `/calibration`'s methodology prose, which is a deliberate comparison surface twice over.
  `CombinedFeedCard`'s cross-source legend was called "the next one that should go" under the old
  clause; under the amended one it is a legend on numbers the reader is looking at, and the call
  reverses.
- **Out of scope on the ruling's own terms:** `app/layout.tsx` keywords.

### The original list

Measured 2026-08-28 by scanning the built bundle, and recorded as executable debt in the `OWED`
map in `frontend/__tests__/components/shippedCopyBans.test.ts` — keyed on (surface, rule), so an
unlisted surface fails and a new KIND of violation on a listed surface also fails. The list can
only be paid down.

- `/calibration` — the judgment call above. Names both venues throughout the methodology prose.
- `/weather`, `/politics`, `/categories/golf`, `/about` — venue names in section subtitles and
  source chips ("Polymarket & Kalshi ·", "Kalshi + Polymarket, unified").
- The shared landing blurbs — "Sportsbooks, ESPN, Kalshi, Polymarket, and live stat models each
  have a guess."
- `components/CombinedFeedCard.tsx` and `components/SourceComparisonRow.tsx` — the cross-source
  legend on Discover cards. This one is closest to the standing "blend is the product" ruling and
  is the next one that should go.
- `app/layout.tsx` — `Kalshi` and `Polymarket` in the `<meta name="keywords">` list. Not visible
  to a reader, so out of scope on this ruling's own terms, but it IS in the bytes the page serves
  and removing it is an SEO call rather than a copy one. Flagged to Alex, not swept.

## The guard

`lib/copyBans.ts` holds the rules; `tournamentPlainLanguage.test.tsx` applies them to rendered
components and `shippedCopyBans.test.ts` applies the same list to the built bundle and, on demand,
to the chunks production is serving. See ruling 142 for why the second of those exists.
