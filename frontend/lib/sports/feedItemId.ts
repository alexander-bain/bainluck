// The Sports feed's stable per-item id.
//
// Lifted out of `app/sports/page.tsx` by UX-1035 / #2709, unchanged. It moved
// because the live rail's guard has to de-duplicate the SAME way the page does
// — the rail and page 1 overlap by construction — and a test that re-types this
// function is testing its own copy. A route file can only export the reserved
// Next.js names, so the shared definition has to live here.

import type {
  FeedItem,
  FeedEventData,
  FeedFuturesData,
  FeedConceptData,
  FeedTournamentData,
} from "@/lib/types";

/**
 * Stable per-item id for cross-page dedup (mirrors app/discover/page.tsx). The
 * paginated Sports feed can overlap a card across page boundaries — and since
 * #2709 the live rail overlaps it too — so dedup keeps any single question from
 * rendering twice.
 */
export function getSportsItemId(item: FeedItem): string {
  if (item.type === "event") return `event-${(item.data as FeedEventData).id}`;
  if (item.type === "futures") return `futures-${(item.data as FeedFuturesData).id}`;
  if (item.type === "concept") return `concept-${(item.data as FeedConceptData).key}`;
  return `tournament-${(item.data as FeedTournamentData).key}`;
}
