# RULING 138 — "Price" is not a word we say to readers; the word is PROBABILITY

date: 2026-08-27
author: Alex (PRODUCT LANGUAGE RULING, permanent and product-wide; directive authored in Alex's
Fable session and delivered through the lane runner Alex launched under his standing
authorization)

**Replaces:** the noun/verb line UX-P145 drew inside
`frontend/__tests__/components/tournamentPlainLanguage.test.tsx` (2026-08-27, same day).
**Binds:** all user-facing copy, on every surface, from now on. Swept on the tournament surfaces
by UX-P146; the rest is named in "What is not yet swept" below and is owed, not done.

---

## The clause

> "price" as a noun is banned in user-facing copy — the word is PROBABILITY.
> — Alex, 2026-08-27

## What it replaces, and why the earlier line was wrong

UX-P145 swept the tournament surfaces for internal vocabulary and drew a line down the middle of
this one word. *Priced* as a verb done to a question — "nobody has priced it yet", "a priced
round to reach", "they come back when they are priced again" — was ruled jargon and removed.
*Price* as the **noun a market publishes** was kept, on the reasoning that it is plain English on
a prediction-market page and that the boards, the slate and `/calibration` already shared it, so
removing it would make three surfaces word one admission three ways.

That reasoning is about consistency, and consistency was the wrong thing to optimise. The product
thesis is in the first line of `CLAUDE.md`: we translate betting and prediction markets into
intuitive probabilities, so a reader sees **60% vs 40%** instead of **-150 / +130**. The entire
value we add is that nobody has to think in the trading layer. A page that does that arithmetic
for a reader and then tells them the result is a *price* hands the trading layer back at the last
step, in the caption, after having removed it from the number.

Three surfaces consistently using the wrong word is not an argument for keeping it. It is three
places to fix.

## The general clause

**When a product exists to translate a domain's vocabulary, the translated surface may not carry
the source vocabulary in its own voice — least of all in the sentence that explains the
translated number.** Internal names survive where our names belong: enum values, data attributes,
column names, code. They do not survive in a sentence aimed at a reader.

## What it does NOT touch

- **Data contracts.** `price_state`, `data-price-state`, `opening_probability`,
  `priced_cells`, `PRICED_STATES`, `futures_odds_snapshots` — every one of these keeps its name.
  CERT-411 and the sentinels read them and no user sees them. The plain-language sweep runs over
  rendered TEXT with attributes stripped, so it is indifferent to them by construction rather
  than by an exception list.
- **Code, comments and reports.** This is a ruling about copy.
- **The honesty the old copy carried.** "Prices paused. …These are the last prices we saw, not
  live prices" became "Updates paused. …These are the last probabilities we saw, not live ones".
  The admission is identical in force and specificity, and the guard pins BOTH halves — the
  banned word absent *and* the staleness still stated — because the failure mode of a copy
  ruling is a rewrite that removes the word and the meaning with it.
- **Words that are genuinely about money.** `/economics` prints "Inflation & Consumer Prices" and
  "the price at the pump". Those are prices — of goods, in the world, which is what those markets
  are *about*. The ruling bans naming OUR number a price; it does not ban the English word where
  the subject really is a price.

## What UX-P146 swept

Every user-visible string on the tournament surfaces, verified at the render:

| Was | Is |
|---|---|
| `Prices paused` (board + slate) | `Updates paused` |
| `These are the last prices we saw, not live prices.` | `These are the last probabilities we saw, not live ones.` |
| `No prices yet` | `No numbers yet` |
| `We have not recorded a price for this draw.` | `No market has put a probability on this draw yet.` |
| `No prices to show` | `No numbers to show` |
| `…have no price yet.` | `…have no number yet.` |
| `cells carry a market price` | `cells carry a number from a real market` |
| `every number is a price somebody quoted` | `every number is one a market quoted` |
| `Live price.` (grid cell tooltip / screen reader) | `Live number.` |
| `No title price on either winner field` (`tournament_grid.py`) | `Neither winner market has a number for this player yet` |
| `matches have prices that do not agree` | `matches have numbers that do not agree` |
| `the price comes later` | `the number comes later` |
| `The two prices for this match do not agree` | `The two numbers for this match do not agree` |

## What is not yet swept — owed, and named so it cannot be counted as done

Measured 2026-08-27 by grepping rendered text nodes and string literals outside
`components/tournament/`:

- `/calibration` — the heaviest user. "price moved" / "Price unchanged" / "Opening Price Only" /
  "closing line prices" / "the last traded price before the event begins", plus
  `lib/calibrationMath.ts` and `lib/calibrationCohort.ts` which author the same words.
  **This one needs care, not a find-and-replace:** the `price_moved` dimension is a real
  distinction about *trading*, and "did trading move the number" has to keep meaning what
  "did trading move the price" meant.
- `/futures/[id]` and `components/FuturesChart.tsx` — "Limited price history available",
  "Not enough price history yet", and `lib/priceCadenceCopy.ts`'s "Prices update every 1–2 hours".
- `lib/propDivergence.ts` — "has both a pregame mark and a current price".
- `/admin/matching` — "Prediction-market prices". Admin-only; lowest priority, and arguably
  outside "user-facing" altogether.

## The guard

`frontend/__tests__/components/tournamentPlainLanguage.test.tsx` bans the whole stem —
`/\b(un)?pric(e|es|ed|ing)\b/i` — over the rendered text of every tournament surface, replacing
the eleven hand-written variants UX-P145 needed in order to catch the verb while sparing the
noun. It carries a canary that renders each retired sentence and requires the sweep to reject it,
and a source scan over `components/tournament/*.tsx` JSX text nodes for the states no fixture
reaches.
