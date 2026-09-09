/**
 * #4403 — a badge that repeats the sentence underneath it is not worth a pixel.
 *
 * A futures feed card renders TWO strings built by the same backend branch:
 * the header pill (`item.headline`, `generate_futures_card_copy`) and the reason
 * line directly beneath the market name (`item.reason`, `generate_futures_reason`).
 * The pill is the reason with the market name taken out — by construction, not by
 * coincidence: both come out of the same `"leader_change"` / `"major_movement_24h"`
 * arm of `backend/app/utils/feed_reasons.py`.
 *
 * On production `/sports` at 390px that redundancy is what destroys the header row.
 * The pill is a variable-length sentence competing for ~150px with the category
 * chip, the resolution date and the sources chip, so it ellipsises at 43–56% gone
 * ("New favorite: …" says nothing) and takes the chip down with it (41–59% gone,
 * "🥋 …", where the ellipsis is wider than the text it replaced). Measured over 27
 * cards: 44 truncated elements, 40 of them ≥25% gone. All 23 pills on the page were
 * fully carried by the reason line one row below.
 *
 * So the pill yields — the same priority call #4244 made when it chose the
 * resolution date over the pill's pixels. It is dropped only when it is an ECHO:
 * when every word it contributes is already in the sentence beneath it. A headline
 * that says something new ("Bills odds up 12 points today" beside a reason about
 * the leader) still renders, and that is the case the tests pin from both sides.
 */

/**
 * Words that carry no information on their own, so their presence or absence
 * must not decide whether one string echoes another. Deliberately tiny and
 * closed: this is a redundancy test, not a stemmer, and every word added here
 * makes the echo test LOOSER (more pills suppressed), so the list stays short.
 */
const FILLER = new Set([
  "a",
  "an",
  "and",
  "at",
  "by",
  "for",
  "in",
  "is",
  "now",
  "of",
  "on",
  "the",
  "to",
  "vs",
]);

/**
 * Significant tokens: lowercase alphanumeric runs, filler removed.
 *
 * Punctuation is dropped rather than normalised because the two generators
 * differ in exactly that: "Volkanovski leads at 48%" vs "Volkanovski (48%) leads
 * …". Digits are kept as their own tokens so a pill quoting a DIFFERENT number
 * ("up 12 points") can never be swallowed by a reason quoting another ("48%").
 */
function significantTokens(text: string): Set<string> {
  const out = new Set<string>();
  for (const t of text.toLowerCase().match(/[a-z0-9]+/g) ?? []) {
    if (!FILLER.has(t)) out.add(t);
  }
  return out;
}

/**
 * True when `headline` adds nothing `reason` does not already say.
 *
 * Falsey/blank `reason` is never an echo — with no sentence beneath it, the pill
 * is the only copy on the card and must render however tight the row is.
 */
export function headlineEchoesReason(
  headline: string | null | undefined,
  reason: string | null | undefined,
): boolean {
  const h = (headline ?? "").trim();
  const r = (reason ?? "").trim();
  if (!h || !r) return false;

  const hTokens = significantTokens(h);
  if (hTokens.size === 0) return false;

  const rTokens = significantTokens(r);
  for (const t of hTokens) {
    if (!rTokens.has(t)) return false;
  }
  return true;
}
