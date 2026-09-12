/**
 * #4804 (D1 clause c) — the KEY that decides which Discover futures cards are
 * folded into one client-synthesized group.
 *
 * `groupRelatedMarkets` (app/discover/page.tsx) used to key on "the text before
 * a ':', or — when there is no colon — the first three words". The colon arm is
 * a real shared subject ("Valero Texas Open: Winner" / "Valero Texas Open: Top
 * 10"). The three-word arm was never a subject at all: it is whatever the
 * question happens to open with, so two questions that merely start the same
 * way became one card.
 *
 * Measured on production `GET /api/feed?limit=100` (2026-09-12 19:2xZ), the
 * three-word arm formed exactly two groups and one of them was this:
 *
 *     'Who will be'  ->  Who will be a part of the next government of Sweden?
 *                        Who will be Trump's next Press Secretary?
 *
 * Swedish government formation and a US press appointment, presented as one
 * card. `deriveGroupDisplayTitle` routes the no-colon case to the category, so
 * the reader saw a card pilled "politics" headed "2 markets" holding two
 * questions with nothing to do with each other — D1 clause c ("'N related
 * markets' is replaced by the group's shared question") read backwards.
 *
 * So the three-word arm is gone and a market with no colon subject is simply
 * not groupable. It renders as its own card, which is what it is.
 *
 * WHY NOT A SMARTER STEM RULE. The tempting repair is to keep the arm and
 * reject "generic" openers. Both live collisions — "Who will be" and "Which
 * party will" — are made entirely of function words, so a stopword test would
 * have caught both; but it only works because English questions happen to open
 * with function words, and the first three words of "Brazil Presidential
 * election winner?" are a subject while the first three of "Canadian Team to
 * Win the Stanley Cup" are not. The rule would be guessing at grammar to
 * recover a signal the colon already carries explicitly. A shared subject the
 * data actually states beats one inferred from spelling.
 *
 * The server-side direction (a bundle that carries its own `shared_question`,
 * the way theme and comparison bundles already do) remains the better end
 * state and is untouched by this — see #4804 option (a) / D2.
 */

/**
 * The longest a colon-prefixed subject may be before we stop believing it is a
 * subject. Carried over verbatim from the original expression in
 * `groupRelatedMarkets`, where it guarded against a question that merely
 * contains a colon deep in its text ("Will X happen, and if so: when?").
 */
export const MAX_GROUP_SUBJECT_LENGTH = 30;

/**
 * The grouping key for one futures market name, or `null` when it has none.
 *
 * `null` means "not groupable" — the caller renders the market as its own
 * card. It is deliberately not a fallback string: every fallback key anyone has
 * written here (the first three words, the whole name, the category) either
 * collides questions that are unrelated or collides nothing at all, and the
 * first of those is the bug this function exists to remove.
 *
 * @param name the futures market name
 * @returns the shared colon subject, or `null` if the name states none
 */
export function futuresGroupKey(name: string | null | undefined): string | null {
  const trimmed = (name || "").trim();
  const colonIdx = trimmed.indexOf(":");
  if (colonIdx > 0 && colonIdx < MAX_GROUP_SUBJECT_LENGTH) {
    const subject = trimmed.slice(0, colonIdx).trim();
    if (subject) return subject;
  }
  return null;
}
