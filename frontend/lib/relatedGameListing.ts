import type { RelatedGameListing } from "./types";

/**
 * #10298: what a Polymarket game listing says when search serves it beside its own
 * game, or `null` when the server did not mark it so. The listing's team-win leg
 * printed a second favourite next to the game card ("Packers 53%" under "Lions
 * 56%"), so it becomes a pointer to the questions it holds, with no percentages —
 * #10089's rule and words, as the NFL hubs print them. The relation is the served
 * key; nothing is inferred here from names, sources or leg labels.
 */
export function relatedGameListingText(listing: RelatedGameListing | null | undefined): string | null {
  if (!listing) return null;
  const count = Number.isSafeInteger(listing.question_count) && listing.question_count > 0 ? listing.question_count : 0;
  return count ? `${count} ${count === 1 ? "question" : "questions"} on this game` : "More questions on this game";
}
