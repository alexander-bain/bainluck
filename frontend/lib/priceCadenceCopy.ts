/**
 * The single authority for the "how often does this number move" footnote.
 *
 * #1803 leg 3. Three surfaces printed "Prices update every 1–2 hours" gated on
 * nothing but `totalPoints < 2` — a sparse-history test that is TRUE of every
 * settled market, because a market that stopped trading in April has almost no
 * recent points. So the copy promising the reader that prices will keep moving
 * appeared precisely where prices can never move again, which is the same
 * settled-means-settled failure as the round ladder it sat under.
 *
 * Sparseness and settledness are different facts and the old gate conflated
 * them: "few points" answers *how much history exists*, never *whether this
 * question is still open*. Only the caller knows the second one, so it is a
 * required argument rather than something inferred here.
 *
 * One authority rather than three literals, because these three had ALREADY
 * drifted — two spelled it with an en dash and the third with a hyphen (#1620,
 * the class this lane has now filed thirteen times). A guard test asserts this
 * file is the only place the string is built.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * #8135 — THE THIRD FACT: OPEN, UNSETTLED, AND NOT BEING PRICED ANY MORE.
 *
 * `/futures/59520336` resolves 30 September and its `status` is `open`, so
 * `settled` is false and the live promise was returned — over a board whose
 * newest number is 29 days old, four lines above the card's own "Last number 29
 * days ago". Sparseness and settledness are different facts, and so is this one:
 * "the question is still open" does not imply "somebody is still quoting it".
 *
 * WHY A FIXED BOUND AND NOT `seriesFreshness`'s `stale`. `seriesFreshness` asks
 * *is this line behind its OWN cadence?* — four times its observed median gap.
 * That is the right question for a caption qualifying a drawn line, and it is
 * the wrong one here: this string promises a SPECIFIC cadence, 1–2 hours, so
 * what makes it false is being further behind than the promise itself, not than
 * whatever the series happens to average. On a board whose median gap is a week,
 * the cadence rule would keep this promise alive for a month. Both rules fire on
 * the specimen; they are picked apart by mechanism, not by the case that found
 * them.
 *
 * The bound is 12× the promise's own ceiling — a full day — so that an ordinary
 * ingest hiccup or a quiet overnight cannot flip the copy, while a board silent
 * for a day cannot be described as updating hourly. Fail-safe, not a feature
 * removal: the promise returns by itself the moment a number arrives.
 */

/** Sparse history, but the question is still open — the number will keep moving. */
const LIVE_CADENCE = `Prices update every 1–2 hours`;

/** Settled: never promise an update that cannot come. */
const SETTLED_CADENCE = `Final — prices no longer update`;

/** The upper bound the promise itself states. */
export const CADENCE_PROMISE_CEILING_MS = 2 * 60 * 60 * 1000;

/** Silent this long and the promise above is not describing this board (#8135). */
export const CADENCE_DORMANT_AFTER_MS = 12 * CADENCE_PROMISE_CEILING_MS;

/**
 * Has this board stopped printing numbers?
 *
 * `newestObservation` is the newest instant in the history the page holds, or
 * `null` when it holds none. **`null` is NOT dormant** — a board with nothing to
 * date cannot support a claim about its staleness any more than one about its
 * freshness, and the caller's own empty/sparse branches already say so. A
 * future-stamped point (venue clock skew) is likewise not dormant.
 */
export function isCadenceDormant(
  newestObservation: number | null | undefined,
  now: number = Date.now(),
): boolean {
  if (newestObservation == null || !Number.isFinite(newestObservation)) return false;
  return now - newestObservation > CADENCE_DORMANT_AFTER_MS;
}

export interface PriceCadenceOptions {
  /**
   * Append "for this market". The long form reads correctly as a standalone
   * line under an empty chart; the short one is for an inline run-on after a
   * separator, where the subject is already established.
   */
  long?: boolean;
  /**
   * The board is open but is not printing numbers — see `isCadenceDormant`.
   * Like `settled`, only the caller knows it, so it is passed rather than
   * inferred here.
   */
  dormant?: boolean;
}

/**
 * `null` means SAY NOTHING. There is no third sentence, because the card that
 * needs one already carries it: the chart's own caption reads "Last number 29
 * days ago" directly beneath. A second line explaining the first is the
 * diagnostic prose notice 34 keeps off a reader's screen — the honest move is to
 * withdraw the false promise and leave the space empty.
 */
export function priceCadenceNote(
  settled: boolean,
  { long = false, dormant = false }: PriceCadenceOptions = {}
): string | null {
  // Settled outranks dormant: "Final — prices no longer update" is the stronger
  // and more useful fact, and every settled board goes dormant sooner or later.
  if (settled) return SETTLED_CADENCE;
  if (dormant) return null;
  return long ? `${LIVE_CADENCE} for this market` : LIVE_CADENCE;
}
