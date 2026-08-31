/**
 * UX-P238 — the hero number answers the question the card asks.
 *
 * A futures card headlines ONE number (Alex's standing ruling: "the blend is the
 * product — one number per question"). Every surface picked that number as
 * `top_outcomes[0]`, the probability leader. For a binary market that is a
 * silent inversion whenever the answer is "probably not": the card asks
 * *"Will Neuralink's valuation hit $47.5B?"* and prints the leader — which is
 * the **No** side — as a bare 4xl `73%`. The truth is 27.5%.
 *
 * 🔴 MEASURED on the live feed 2026-08-31 (`GET /api/feed?limit=100`, 96 items,
 * 62 futures cards). Every two-outcome futures card in the whole servable feed
 * is one of 7, and **2 of those 7 print the negation of their own question**:
 *
 *   59934328  Will "Onslaught" score at least 80 on the Tomatometer?
 *             hero 88%  ← 'No: "Onslaught" score at least 80 on ...'   truth 12%
 *   57792416  Will Neuralink's valuation hit (HIGH) $47.5B by August 31?
 *             hero 73%  ← "Not Neuralink's valuation"                  truth 27.5%
 *
 * Both were rendered through the real `DiscoverCard` entry point to confirm the
 * reader sees a bare number under the question with no outcome label attached —
 * measuring the RENDER, not the payload.
 *
 * 🔴 THE NEAR MISS THIS FILE EXISTS TO RECORD. `FeedCard.tsx` already carries a
 * measured note naming `Will Neuralink's valuation hit (HIGH) $47.5B` — #2088
 * audited that exact card because its two printed percents summed to 101, fixed
 * the rounding, and never noticed that the headline was the wrong side. A card
 * whose numbers add up is not a card that is telling the truth.
 *
 * WHY A SHARED MODULE. Three components pick this headline off the same payload
 * — `FuturesCard` (Discover), `FuturesCompactRow` (group + theme-bundle rows)
 * and `FeedCard` (`/categories/*`, `/sports`, `/my-stuff`) — and UX-P162 already
 * paid the price of letting two of them hand-copy one decision. The choice of
 * WHICH outcome is the headline belongs beside `renderedLeaderPercent`'s choice
 * of what percent to print for it.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO. It does not touch `renderedLeaderPercent`
 * or `renderedCardPercents`. Those are the cross-runtime rounding contract
 * (`contracts/rendered_percent.json`); the affirmative side is looked up there
 * BY IDENTITY, which that function already supports on purpose — "the hero is
 * then found BY IDENTITY, not by position ... 1 of the 103 multi-outcome cards
 * already ships `top_outcomes[0]` that is NOT the maximum, which is what makes
 * decision 3 load-bearing". This change is the first caller to use it.
 */

/** The shape any surface's outcome row has that this decision needs. */
export interface HeroCandidate {
  name?: string | null;
  probability?: number | null;
}

/**
 * A negation MARKER, not the word "no". The trailing `\s+` is load-bearing: it
 * is what stops "Norway" and "No. 1 seed" from parsing as negations of
 * something. The optional separator carries Polymarket's `No: <restatement>`.
 */
const NEGATION_PREFIX = /^\s*(?:no|not)\s*[:\-–—]?\s+/i;

/**
 * Below this many characters a restatement is too short to be evidence. "No A"
 * beside "A B C" would otherwise satisfy the prefix test on one letter.
 */
const MIN_RESTATEMENT_CHARS = 4;

/**
 * Feed outcome names arrive truncated at differing lengths on the two sides of
 * one pair — `'No: "Onslaught" score at least 80 on ...'` against
 * `'"Onslaught" score at least 80 on the ...'` — so the ellipsis comes off
 * before the two are compared and the comparison is prefix-tolerant in BOTH
 * directions.
 */
function normalize(name: string | null | undefined): string {
  return (name ?? "").replace(/\s*(?:\.{3}|…)\s*$/, "").trim().toLowerCase();
}

/**
 * True when `negative` reads as the explicit negation of `affirmative`.
 *
 * 🔴 THE RULE IS PAIR-RELATIVE ON PURPOSE, and a bare prefix regex would be
 * wrong. The Fed's real outcome row is **"No change"** — named in
 * `leaderOrder.ts` as the 56% row a slice once dropped — and `/^no\b/` matches
 * it. Requiring the text after the marker to RESTATE the sibling is what keeps
 * "No change" (whose sibling is "25 bps cut") from being read as a negation of
 * anything. The pair test is the guard; the prefix alone is not.
 */
export function negates(negative: HeroCandidate, affirmative: HeroCandidate): boolean {
  const neg = normalize(negative.name);
  const aff = normalize(affirmative.name);
  if (!neg || !aff) return false;

  // The canonical binary. "No" alone restates nothing, so it is matched as a
  // pair rather than through the restatement test below.
  if (neg === "no" && aff === "yes") return true;

  const marker = NEGATION_PREFIX.exec(neg);
  if (!marker) return false;
  const restatement = neg.slice(marker[0].length).trim();
  if (restatement.length < MIN_RESTATEMENT_CHARS) return false;
  return restatement.startsWith(aff) || aff.startsWith(restatement);
}

/**
 * The outcome a card's hero number speaks for.
 *
 * The served headline (`top_outcomes[0]`) in every case except one: a
 * two-outcome market whose headline is the explicit negation of its sibling,
 * where the hero becomes the affirmative side so the number answers the
 * question the title asks.
 *
 * 🔴 A SWAP THAT LEFT THE CARD WORSE WOULD NOT BE A FIX (UX-P237-5). The
 * affirmative side must actually have a number to print — otherwise the card
 * would trade a wrong hero for no hero at all — so an unpriced affirmative
 * keeps the served headline and the card renders exactly as it does today.
 */
export function heroOutcome<T extends HeroCandidate>(
  outcomes: readonly T[] | null | undefined,
): T | undefined {
  const served = outcomes?.[0];
  if (!served || !outcomes || outcomes.length !== 2) return served;

  const other = outcomes[1];
  if (!other || !negates(served, other)) return served;
  if (other.probability == null || !Number.isFinite(other.probability)) return served;
  return other;
}
