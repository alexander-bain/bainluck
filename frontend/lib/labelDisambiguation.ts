/**
 * Two tiles side by side must not print the same string — #2788.
 *
 * On `bainluck.com/events/15301243` the Bigger Picture "OTHER (3)" row rendered
 * three prop tiles whose labels came from the market's own outcome names:
 *
 *   "Will Carlos Alcaraz advance to the Quarterfinals in Men's Singles …"  79%
 *   "Will Carlos Alcaraz advance to the Semifinals in Men's Singles …"     55%
 *   "the 2026 US Open? Win"                                               22%
 *
 * The tile is 110px wide and truncates with CSS, so the first two rendered as
 * `Will Carlos Al…` — character for character identical, side by side, showing
 * different numbers. Nothing on the card told the reader which question was at
 * 79% and which at 55%. A confident number above an unreadable label is the
 * same class of defect as a card that contradicts itself.
 *
 * THE RULE. Drop the WORD prefix a label shares with a sibling, but only when
 * that shared prefix is at least as long as the tile's visible window — i.e.
 * only when the two labels would otherwise be indistinguishable on screen. The
 * remainder therefore begins at the first differing word, by construction.
 *
 * WHY THE GATE IS CHARACTERS AND NOT WORDS. A word count cannot tell "Derrick
 * White" from "Derrick Whiteman" (one shared word, plainly distinguishable in
 * the tile) apart from "Juan Carlos Rodriguez Garcia" vs "… Lopez" (three
 * shared words, indistinguishable). The question is not how much two labels
 * share, it is whether what they share fills the space the reader can see.
 *
 * WHY WORD BOUNDARIES AND NOT CHARACTERS. Cutting mid-word is what produced
 * "Will Carlos Al…" in the first place. A fragment is not a shorter label.
 *
 * THE INVARIANT: this never makes two distinct labels equal. A shared-prefix
 * strip can in principle collide a remainder with another label that was
 * already short ("A B C X" / "A B C Y" / "X"), so if the transform would reduce
 * the number of distinct strings the group is returned untouched. Worse-but-
 * readable beats a new instance of the exact bug being fixed.
 *
 * IDENTICAL LABELS ARE LEFT ALONE. Two rows that really do carry the same text
 * are the same question shown twice — a dedup problem, not a truncation one —
 * and shortening them to nothing would hide it.
 */

/**
 * How many characters of a label a reader can actually see before the ellipsis.
 *
 * MEASURED, not chosen: the production LOOK on 2026-09-03 rendered
 * "Will Carlos Al…" in a 110px tile at 11px semibold — 14 characters. It is a
 * parameter rather than a constant because the caller knows its own tile.
 */
export const DEFAULT_VISIBLE_CHARS = 14;

/** The number of leading whole words two labels share, case-insensitively. */
function sharedWordPrefix(a: string[], b: string[]): number {
  let i = 0;
  while (i < a.length && i < b.length && a[i].toLowerCase() === b[i].toLowerCase()) {
    i += 1;
  }
  return i;
}

/**
 * The labels a group of side-by-side tiles should print, in the same order.
 *
 * Returns the input unchanged whenever nothing is gained — which is the common
 * case, and deliberately so: player names, stat lines and short questions are
 * already distinguishable and must not be trimmed.
 */
export function disambiguateLabels(
  labels: string[],
  visibleChars: number = DEFAULT_VISIBLE_CHARS,
): string[] {
  if (labels.length < 2) return labels;

  const words = labels.map((l) => l.trim().split(/\s+/).filter(Boolean));

  const shortened = labels.map((label, i) => {
    let strip = 0;
    for (let j = 0; j < labels.length; j += 1) {
      if (i === j) continue;
      const shared = sharedWordPrefix(words[i], words[j]);
      // A label wholly contained in another (or identical to it) has nothing
      // left to print, so it keeps its full text.
      if (shared >= words[i].length) continue;
      if (shared > strip) strip = shared;
    }
    if (strip === 0) return label;

    // The shared run as the reader sees it — the trailing space counts, because
    // it is space the tile spends.
    const prefix = words[i].slice(0, strip).join(" ") + " ";
    if (prefix.length < visibleChars) return label;

    const remainder = words[i].slice(strip).join(" ");
    return remainder.length > 0 ? remainder : label;
  });

  // The invariant. Never trade one indistinguishable pair for another.
  if (new Set(shortened).size < new Set(labels).size) return labels;
  return shortened;
}
