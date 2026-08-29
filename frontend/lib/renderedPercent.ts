// The whole percent this surface prints for a probability — web's arm of
// `contracts/rendered_percent.json` (#1933).
//
// This was `Math.round(probability * 100)` inline in the Label Pass page, which
// is correct and was never the bug. It is extracted because it is now half of a
// CROSS-RUNTIME contract: the server takes the graded card's fingerprint at this
// exact resolution so that a drift refusal is always explicable to the person
// who was looking at the card, and Swift prints the same number on native. An
// expression inlined in a JSX attribute cannot be driven through a shared table;
// a named function can, and all three arms now are.
//
// UX-P110 shipped the Python side using banker's rounding against this, and the
// test beside it asserted the JavaScript answer in a comment while expecting the
// Python one in the assertion. See the contract file for why a comment was never
// going to hold this together.

export function renderedPercent(probability: number | null | undefined): number | null {
  if (probability === null || probability === undefined) return null;
  if (!Number.isFinite(probability)) return null;
  return Math.round(probability * 100);
}

// ── The card-level half of the contract (#2060) ──────────────────────────────
//
// Getting each number right is not enough, because a surface prints a CARD and a
// card has a SUM. `Los Angeles D 0.925 / Colorado 0.075` renders 93 and 8 above —
// both correct, 101 together — because Kalshi quotes a complement pair on a
// half-cent grid, so `p * 100` lands on `.5` for both sides at once and half-up
// rounds both up.
//
// See `contracts/rendered_percent.json` for the measured population behind the
// [0.99, 1.01] band and for why `field_coherence`'s much looser [0.5, 1.5] is
// deliberately not the predicate.

const COMPLEMENT_MIN = 0.99;
const COMPLEMENT_MAX = 1.01;

export function isComplementPair(
  probabilities: Array<number | null | undefined> | null | undefined,
): boolean {
  if (!probabilities || probabilities.length !== 2) return false;
  const values = probabilities.filter(
    (p): p is number => p !== null && p !== undefined && Number.isFinite(p),
  );
  if (values.length !== 2) return false;
  const total = values[0] + values[1];
  return total >= COMPLEMENT_MIN && total <= COMPLEMENT_MAX;
}

/**
 * The whole percents this surface prints for ONE CARD's served outcomes.
 *
 * A complement pair is normalized by its true total (removing the vig
 * symmetrically rather than dumping it all on one side), index 0 is rounded once
 * with `renderedPercent`, and index 1 is DERIVED as `100 - index0`. Index 0 is the
 * card's headline, so it is the value that survives untouched.
 *
 * Everything else is rendered exactly as before — that direction is asserted by
 * the contract suite as explicitly as the fixed one.
 */
export function renderedCardPercents(
  probabilities: Array<number | null | undefined> | null | undefined,
): Array<number | null> {
  if (!probabilities || probabilities.length === 0) return [];
  if (!isComplementPair(probabilities)) return probabilities.map(renderedPercent);

  const total = (probabilities[0] as number) + (probabilities[1] as number);
  const leader = renderedPercent((probabilities[0] as number) / total);
  if (leader === null) return probabilities.map(renderedPercent);
  return [leader, 100 - leader];
}

// ── Why a card's two numbers do not add up (#2088) ───────────────────────────
//
// `renderedCardPercents` fixed the pair that SHOULD total 100 and left alone the
// pair that should not — correctly, because normalizing a pair summing to 0.97
// would invent three points of probability. But it left the reader a card reading
// `57 / 40` with nothing saying why, which looks exactly like the `93 / 8` bug it
// had just fixed. #2088: an unexplained non-100 is the defect, a labelled one is a
// fact.
//
// THE SERVER DECIDES THIS (`card_sum_reason` on both labeling serializers). These
// are the FALLBACK for a payload minted before that field existed, and they are in
// the contract so the fallback cannot drift from the served answer — the same role
// `renderedPercent` plays for a pre-#2060 payload.
//
// See `contracts/rendered_percent.json` (`card_sum_cases`) for the measured
// population, for why the reason is NOT an illiquidity mark (the exemplar's book
// grades `traded`), and for why arity other than two is null.

/** A served outcome has no price at all, so there is no total to check. */
export const SUM_UNPRICED_OUTCOME = "unpriced_outcome";
/** Both sides priced, outside the complement band — two independent questions. */
export const SUM_INDEPENDENT_PRICES = "independent_prices";

/**
 * The integer total this surface prints for one card, or null if it prints nothing.
 *
 * An unpriced outcome contributes nothing rather than a zero — "no price" and "0%"
 * are different cards — so `[57, null]` totals 57 and is explained by
 * `cardSumReason` rather than reported as a 43-point miss.
 */
export function cardSum(
  probabilities: Array<number | null | undefined> | null | undefined,
): number | null {
  const percents = renderedCardPercents(probabilities).filter(
    (p): p is number => p !== null,
  );
  if (percents.length === 0) return null;
  return percents.reduce((a, b) => a + b, 0);
}

/**
 * Why this card's printed percents do not total 100, or null if they do.
 *
 * Taken over `renderedCardPercents` rather than the raw floats, so it answers for
 * THE PICTURE. A complement pair is normalized, rounded once and derived, so it
 * totals 100 by construction and can never earn a reason.
 *
 * null for any arity other than two: it means "no claim about a total is made
 * here", never "checked and fine", and a surface must not render it as one.
 */
export function cardSumReason(
  probabilities: Array<number | null | undefined> | null | undefined,
): string | null {
  if (!probabilities || probabilities.length !== 2) return null;
  const percents = renderedCardPercents(probabilities);
  if (percents.some((p) => p === null)) return SUM_UNPRICED_OUTCOME;
  const total = percents.reduce((a, b) => (a ?? 0) + (b ?? 0), 0);
  return total === 100 ? null : SUM_INDEPENDENT_PRICES;
}

// ── The duel: the same question in FIXED positions (UX-P114) ─────────────────
//
// `renderedCardPercents` assumes served order, where index 0 is the headline. The
// Discover event card does not sort — away is always left, home is always right —
// yet it is the most exact complement pair in the product, because the feed derives
// the away side as `1 - home`. So whenever `home * 100` lands on `.5`, both sides
// round up and the strip prints 101. Measured 2026-08-21: 34 of 414 live/upcoming
// events (8.2%), all 101, never 99.
//
// THE SERVER NOW DECIDES THIS (`current_odds.{away,home}_rendered_percent`), because
// four surfaces draw this strip and only one of them is this file. This function is
// the local FALLBACK for a payload from before that field existed — and it is in the
// contract so the fallback cannot drift from the served answer.
//
// See `contracts/rendered_percent.json` (`duel_cases`) for why the FAVOURITE is the
// side that survives rather than the away side.

export function renderedDuelPercents(
  awayProbability: number | null | undefined,
  homeProbability: number | null | undefined,
): Array<number | null> {
  const pair = [awayProbability, homeProbability];
  if (!isComplementPair(pair)) {
    return [renderedPercent(awayProbability), renderedPercent(homeProbability)];
  }

  const away = awayProbability as number;
  const home = homeProbability as number;
  if (away >= home) return renderedCardPercents([away, home]);
  const [homePct, awayPct] = renderedCardPercents([home, away]);
  return [awayPct, homePct];
}
