/**
 * Is a futures market's outcome set a one-winner partition, or a bundle of
 * independently-priced questions? (lane1-Q479, TOP-PRODUCT-DEFECTS item 13.)
 *
 * THE DEFECT THIS EXISTS FOR. `/futures/109441` ("Which companies will release a
 * Fully AI-generated multi-episode scripted series before 2027?") renders eight
 * rank-badged rows reading 27 · 7 · 6 · 5 · 5 · 4 · 3 · 3. A reader adds them,
 * gets 60, and concludes the page is broken. It is not the prices that are
 * broken — Kalshi's own event flag says `mutually_exclusive: false`, our ingest
 * stores it faithfully, and the detail payload already SERVES it. Those eight
 * tickers are eight independent binaries: several companies can each ship a
 * series, so several can each resolve Yes, and their prices have no reason to
 * sum to anything in particular. The page simply never read the field, and
 * presented an independent bundle in the geometry of a race.
 *
 * THE ASYMMETRY, and it is the whole reason this predicate is safe.
 * `futures_markets.mutually_exclusive` has ORM `default=True`
 * (`models.py`), so:
 *
 *   * `true`  is NOT evidence of anything — it is what an unwritten row says.
 *     `precompute_calibration.py`'s Rung 4 (Queue 299) stopped accepting it as
 *     proof of a partition for exactly this reason, and nothing here reinstates
 *     it. A `true` market renders exactly as it does today.
 *   * `false` is evidence ONLY FROM KALSHI. See the next paragraph — this is
 *     the correction CERT-609 forced, and it is not a detail.
 *
 * 🔴 `false` IS NOT UNIVERSALLY AFFIRMATIVE — IT DEPENDS ENTIRELY ON THE PARSER.
 * The first version of this file claimed `false` "IS evidence — somebody had to
 * overwrite the default to get it". That is true of exactly one of the two
 * writers, and CERT-609 caught it:
 *
 *   * Kalshi — `services/kalshi_api.py:1435`:
 *       `mutually_exclusive=event_data.get("mutually_exclusive", True)`
 *     An ABSENT key becomes `true`. So a Kalshi `false` could only have come
 *     from Kalshi literally saying `false`. Affirmative. The note is safe.
 *   * Polymarket — `services/polymarket_api.py:598`:
 *       `neg_risk=event_data.get("negRisk", False)`
 *     …stored straight through at `tasks/polymarket.py:1057`
 *     (`mutually_exclusive=event.neg_risk`). An ABSENT key becomes `false`.
 *     So a Polymarket `false` is indistinguishable from Polymarket never
 *     mentioning the field at all. NOT affirmative — it is the same "absence is
 *     not evidence" trap as `true`, arriving from the other side.
 *
 * So the note is gated on `source === "kalshi"`. And note WHERE the measured
 * table below came from: open **Kalshi** `market_type='field'` markets. The
 * evidence was always Kalshi-only; the claim was the thing that over-reached.
 * The ~1,970 Polymarket rows carrying the denial are not proved wrong — they are
 * unproved, which is a different thing and not something a page should assert.
 * Repairing Polymarket's provenance so its `false` means something is filed as a
 * follow-up, not smuggled in here.
 *
 * MEASURED, production 2026-08-31, open Kalshi `market_type='field'` markets
 * with >= 3 outcomes — the flag predicts the sum, so it is real signal:
 *
 *              sum < 0.80   0.80-0.95   0.95-1.05   1.05-1.20   > 1.20
 *   mx=false          346          33     38 (1.9%)        47     1,723
 *   mx=true            82         126  1,545 (52.2%)       526       836
 *
 * A source-affirmed set lands on ~1.0 twenty-seven times more often than a
 * source-denied one. 4,157 open `field` markets (2,187 Kalshi + 1,970
 * Polymarket) carry the denial today.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO. It does not renormalise anything. The
 * source says these are independent; dividing them by their own sum would
 * invent an exclusivity the source denies and would fabricate Amazon at 46%.
 * It also does not touch `market_type`: the classifier calling this set `field`
 * ("> 2 named competitors, ONE wins") is a real and separate bug whose blast
 * radius reaches the calibration cohorts, and it is filed rather than fixed
 * here.
 */

/**
 * Below this many outcomes the question "do these add up?" is not one a reader
 * asks, and a two-sided market is a duel whatever the flag says.
 */
export const MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE = 3;

/** The note an OPEN independent bundle prints above its outcome list. */
export const INDEPENDENT_OUTCOMES_NOTE_OPEN =
  "Several of these can happen — each is priced on its own, so they don't add up to 100%.";

/**
 * The same fact in the past tense for a settled market. Two states, two
 * renderings, both enumerated on purpose: a component whose copy changes with
 * state and is only ever tested in one state is how this board has repeatedly
 * shipped a claim the other branch disproves.
 */
export const INDEPENDENT_OUTCOMES_NOTE_SETTLED =
  "Several of these could happen — each was priced on its own, so they don't add up to 100%.";

/**
 * The sources whose parser makes a `false` mean the source SAID false.
 *
 * Kalshi only, and the membership test is a property of the parser, not of the
 * brand: `kalshi_api.py` defaults an absent key to `true`, so `false` had to be
 * written. Adding a source here without first checking what ITS parser does
 * with a missing key is how CERT-609 happened.
 */
const AFFIRMATIVE_EXCLUSIVITY_SOURCES = new Set(["kalshi"]);

/**
 * True when the source has POSITIVELY told us this outcome set is not a
 * one-winner partition. `undefined` / `null` / `true` all return false: absence
 * is not evidence, and neither is the column default.
 *
 * A `false` from a source whose parser invents `false` out of an absent key
 * (Polymarket) also returns false — see the module docstring. The page stays
 * silent rather than asserting independence it cannot support.
 */
export function outcomesArePricedIndependently(
  mutuallyExclusive: boolean | null | undefined,
  outcomeCount: number,
  source: string | null | undefined
): boolean {
  return (
    mutuallyExclusive === false &&
    outcomeCount >= MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE &&
    AFFIRMATIVE_EXCLUSIVITY_SOURCES.has((source ?? "").toLowerCase())
  );
}

/**
 * The note to print, or `null` when the page should say nothing. Returning
 * `null` rather than `""` keeps "we have no claim to make" distinguishable from
 * "the claim is empty" at every call site.
 */
export function independentOutcomesNote(
  mutuallyExclusive: boolean | null | undefined,
  outcomeCount: number,
  isResolved: boolean,
  source: string | null | undefined
): string | null {
  if (!outcomesArePricedIndependently(mutuallyExclusive, outcomeCount, source)) {
    return null;
  }
  return isResolved
    ? INDEPENDENT_OUTCOMES_NOTE_SETTLED
    : INDEPENDENT_OUTCOMES_NOTE_OPEN;
}
