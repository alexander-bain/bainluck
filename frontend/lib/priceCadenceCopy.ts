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
 */

/** Sparse history, but the question is still open — the number will keep moving. */
const LIVE_CADENCE = `Prices update every 1–2 hours`;

/** Settled: never promise an update that cannot come. */
const SETTLED_CADENCE = `Final — prices no longer update`;

export interface PriceCadenceOptions {
  /**
   * Append "for this market". The long form reads correctly as a standalone
   * line under an empty chart; the short one is for an inline run-on after a
   * separator, where the subject is already established.
   */
  long?: boolean;
}

export function priceCadenceNote(
  settled: boolean,
  { long = false }: PriceCadenceOptions = {}
): string {
  if (settled) return SETTLED_CADENCE;
  return long ? `${LIVE_CADENCE} for this market` : LIVE_CADENCE;
}
