# RULING 141 — Venue names are not part of the product a reader bought

date: 2026-08-28
author: Alex (PRODUCT LANGUAGE RULING, permanent and product-wide; directive authored in Alex's
Fable session and delivered through the lane runner Alex launched under his standing
authorization)

**Sits beside:** ruling 138 (`price` is not a word we say to readers) and ruling 142 (a section
states what it IS). The three were issued from one live-page reading and share one guard.
**Swept by:** UX-P150, on the tournament surfaces. Everything else is named in "What is owed"
below and is owed, not done.

---

## The clause

> Venue names — "Kalshi" and "Polymarket" — are BANNED in user-facing copy, everywhere. Users get
> our probability, not our sourcing.
> — Alex, 2026-08-28

## Why

This is ruling 138's clause applied one level up. That ruling banned the trading layer's *noun*;
this one bans the trading layer's *proper nouns*. A reader who has been shown a single blended
number and is then told which two exchanges we read it from has been handed the plumbing back
after we removed it — and worse, handed a decision to make about it, which is the decision the
product exists to make for them. The standing ruling is *the blend is the product*: one number
per question, and source divergence is a data bug to fix rather than a feature to show. A venue
name in a caption is that same feature, smuggled in as attribution.

There is a second reason, and it is the sharper one. Naming the venue makes an absence sound like
a coverage problem instead of a fact about the world. The grid legend said *"we asked Kalshi and
Polymarket and neither runs that market"* — which tells the reader we have two suppliers and both
let us down. What is actually true is that **nobody is answering that question**, anywhere, and
that is a more useful and more honest thing to know. The sentence got shorter and truer at once.

## The general clause

**A translated surface may not name the sources it translated.** Where the abstraction is the
product, the identity of what sits under it is implementation detail, and putting it in front of
a reader converts a finished answer back into a research task.

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

## What is owed — named so it cannot be counted as done

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
