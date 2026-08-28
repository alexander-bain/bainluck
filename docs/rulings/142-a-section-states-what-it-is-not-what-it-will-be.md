# RULING 142 — A section states what it IS, not what it WILL be; and a copy guard reads what shipped

date: 2026-08-28
author: Alex (PRODUCT LANGUAGE RULING, permanent and product-wide; directive authored in Alex's
Fable session and delivered through the lane runner Alex launched under his standing
authorization)

**Sits beside:** rulings 138 and 141. All three came out of one reading of the LIVE page.
**Swept by:** UX-P150, on the tournament surfaces.

---

## The clause

> No future-tense promises in product copy. We shouldn't be talking about what the section "will
> be", we should make it the thing it's supposed to be.
> — Alex, 2026-08-28

## The sentence that produced it

Live on `/tournaments/us-open-2026`, in the props empty state:

> Questions like *Will Sinner actually play?* live here. Once the main draw starts, Kalshi and
> Polymarket list more of them beyond who-reaches-what, and the ones worth asking appear here as
> they are priced.

Alex: *"violates every rule at once"* — and it does. It names two venues (ruling 141), it says
*priced* (ruling 138), and it spends its entire length describing a section that does not exist
yet. It was written in good faith: UX-P145 added it because a section that only apologises reads
as a dead feature, and naming the next thing reads as one between deliveries. That reasoning is
wrong in a specific way worth writing down.

## Why a promise is worse than an admission

**A promise about a listing is a promise about somebody else's business.** We do not decide when a
market opens a question. "…as soon as they have a number" therefore has no date behind it, and a
sentence with no date behind it is not information — it is reassurance, which is the register a
product uses when it has nothing to say.

**It also mis-states the failure.** "Questions appear here as they are priced" tells the reader
the section is waiting on a supplier. The truth is nearly always narrower and more interesting:
*nobody is answering that question right now*. The reader can act on the second one; the first
just asks them to come back.

**And it decays into a lie.** With CERT-422's merge the props section HAS content, so the empty
state should rarely render at all. A promise that survives past the delivery it promised is worse
than the apology it replaced.

So: the section states what it is. If it is empty, it says what it holds, in the present tense,
and says how much of it there is right now.

| Was | Is |
|---|---|
| `New questions are coming — check back soon.` | *(removed — the count and the reason were always the whole of the fact)* |
| `…and the ones worth asking appear here as they are priced.` | `This section holds the questions about this draw worth asking beyond who reaches which round … No market carries a probability on one today.` |
| `Questions about sets, games and margins appear here as soon as anyone opens one.` | `Who wins is the only question anyone is answering on this match. Sets, games and margins have no probability against them.` |
| `Matches appear here as they are scheduled.` | `This is where the day's matches sit.` |
| `It is in the draw; the number comes later.` | `It is in the draw with no probability against it.` |

## The general clause

**A surface describes its present state, not its intended one.** Where a product cannot name a
date, it may not name a time. An empty section owes the reader what it holds and why it holds
nothing — never a schedule for its own improvement.

## What it does NOT ban

Not the bare auxiliary. Half the questions on the page are questions a MARKET wrote — *Will
Sinner actually play?*, *Who will be the champion?* — and a rule broad enough to catch those is a
rule that gets switched off within a week. Every pattern in `FUTURE_PROMISE_BANS` is a phrase only
our own voice produces: "check back", "coming soon", "appear here", "as soon as anyone", "once the
main draw starts". The guard carries the market questions as explicit ALLOWED cases so a future
tightening has to break them visibly.

---

## The second half of this ruling: a copy guard reads what SHIPPED

> Extend the pinned copy test to run against the strings the PRODUCTION bundle serves, so
> branch-only sweeps can never look done again.
> — Alex, 2026-08-28

### The incident

Every string Alex quoted on 2026-08-28 had already been fixed. `No prices yet` was fixed by
UX-P146. `Prices paused` was fixed by UX-P146. `Nothing curated yet` and `gone dark and rotated
out` were fixed by UX-P145. Each sweep was real, each had a render guard, each reported done.

None of them had landed. Measured the same day against the chunks
`https://www.bainluck.com/tournaments/us-open-2026` actually serves: **41 violations across 30
distinct sentences**, including the entire output of both sweeps.

The guards were not weak. They were pointed at the wrong object. `tournamentPlainLanguage.test.tsx`
reads `components/tournament/*.tsx` and `renderToStaticMarkup` — a working tree and a fixture.
Neither is a reader. A green guard over a branch is a claim about the branch, and it was being
read as a claim about the product.

### The general clause

**A guard proves a property of the artifact it reads.** A test over source proves a property of
source; only a test over the shipped bundle proves a property of what shipped. When the claim is
"a user no longer sees X", the guard has to read something a user could have downloaded — and
where it cannot, it must say so out loud rather than pass.

### What was built

- `frontend/lib/copyBans.ts` — the rules for 138, 141, 142 and the UX-P145 jargon list, as data,
  in one place, with a string-literal extractor for minified JavaScript.
- `frontend/__tests__/components/shippedCopyBans.test.ts` — three layers over the same rules:
  the predicate pinned against every retired sentence AND against the market questions it must
  not eat; the local `.next/static/chunks` build output; and, when `SHIPPED_BUNDLE_DIR` points at
  one, the chunks downloaded from production.
- `frontend/scripts/fetch-shipped-copy.mjs` — the downloader, carrying no rules of its own so it
  cannot drift from them.
- The `OWED` map — the rest of the product's debt against all three rulings, keyed on
  (surface, rule) so it can only be paid down: an unlisted surface fails, a new kind of violation
  on a listed surface fails, and an entry that stops firing must be deleted.

### The rule that follows from it

**A copy ruling is not closed by a green branch.** It is closed by
`SHIPPED_BUNDLE_DIR=… npx jest shippedCopyBans` reading zero on the surface it names, against a
bundle fetched from production after the deploy.
