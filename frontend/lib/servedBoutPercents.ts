/**
 * #6816 — the web arm of "a fight's two percentages are ONE decision".
 *
 * WHAT A READER SAW. `/event/ufc/…26sep19`, production 2026-09-17: **Arman
 * Tsarukyan 74% / Mauricio Ruffy 28%**. The quotes are 0.735 / 0.275 — a venue's
 * half-cent grid puts BOTH sides of one bout on a rounding boundary, and a rail
 * that formats each row on its own rounds both up. Three more bouts on the card
 * did the same, and the eight whose quotes summed to exactly 1 printed 101.
 *
 * The combat builder now decides the pair once (`event_combat
 * .with_bout_display_percents`, the `contracts/rendered_percent.json` duel rule)
 * and serves it as `rendered_percent` on each of a bout's two rows — after price
 * support, and only for a pair it has PROVEN is two sides of one question. This
 * function is how a renderer reads that decision.
 *
 * 🔴 BOTH OR NEITHER (#2279's rule, on this envelope). The two integers are one
 * decision, so they are taken together or not at all. A row set that is not
 * exactly two rows, or carries one served value and not the other, or carries
 * anything that is not a whole percent, returns `null` for EVERY row — and a
 * `null` handed to `formatProbability(p, { rendered: null })` prints exactly what
 * it printed before this shipped. A served 73 beside a locally rounded 28 would
 * be the same defect arriving from the other direction.
 *
 * 🔴 THIS DOES NOT FALL BACK TO A LOCAL NORMALISE, deliberately — and that is the
 * one difference from `servedDuelPercents`. A game strip's two sides are a
 * complement by construction, so rebuilding the pair locally is safe. A concept
 * child's two rows are NOT: the same `outcomes` array carries a Yes/No claim, two
 * props under a matchup title, a draw leg. Whether two rows are one question is a
 * fact about the MARKET (its series, its venue's published rule for a draw or no
 * contest, its type, who its rows name), which the server can read and this
 * function cannot. So an envelope built before the field
 * shipped — they are cached, and refresh within a minute of the next read —
 * prints as it always did, rather than having a sum tidied by a client that
 * cannot know what the sum was of.
 *
 * The `<1%` / `>99%` boundary rule is untouched: it lives in `probabilityParts`
 * and runs on the PROBABILITY, so a served 100 over 0.995 still reads `>99%`.
 *
 * The native arm is `ConceptCardPresentation.servedPercents` in
 * `ios/Bain Luck/Bain Luck/Models/ConceptCardModels.swift`.
 */

/** Anything that may carry the server's decided whole percent. */
export interface ServedPercentRow {
  rendered_percent?: number | null;
}

function isWholePercent(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= 0 &&
    value <= 100
  );
}

/**
 * The served whole percent for each row, in the rows' own order — or `null` for
 * every row when the server made no two-sided decision about them.
 *
 * Pass the rows EXACTLY AS PRINTED (after any sort or slice): the value rides on
 * each row rather than in a positional array precisely so a re-ordered list
 * cannot mis-pair it.
 */
export function servedBoutPercents(
  rows: ReadonlyArray<ServedPercentRow | null | undefined> | null | undefined,
): Array<number | null> {
  const list = rows ?? [];
  if (list.length !== 2) return list.map(() => null);
  const served = list.map((row) => row?.rendered_percent);
  if (!served.every(isWholePercent)) return list.map(() => null);
  return served as number[];
}
