import type {
  FeedItem,
  FeedEventData,
  FeedFuturesData,
  FeedBundleData,
  FeedConceptData,
} from "@/lib/types";

/**
 * The stable per-card identity used for dedup, dismissal and React keys.
 *
 * Lifted out of `app/discover/page.tsx` by LAT-P205 so `ChallengeModal` could
 * move into its own module without importing the page back. The behaviour is
 * unchanged — the branches and their comments came across verbatim.
 */
export function getItemId(item: FeedItem): string {
  if (item.type === "event") return `event-${(item.data as FeedEventData).id}`;
  if (item.type === "futures") return `futures-${(item.data as FeedFuturesData).id}`;
  // Theme/comparison bundles carry a stable unique `id` (story_key/group_id +
  // member ids). Without this case bundles fell through to `tournament-undefined`,
  // collided, and got dropped by the dedup pass (Queue #62 / OPS-88).
  if (item.type === "bundle") return `bundle-${(item.data as FeedBundleData).id}`;
  // Concept cards (UFC/F1/cycling) carry their own `event:<domain>:<slug>` key —
  // give them a concept-specific id so they no longer share the `tournament-`
  // namespace (avoids a prefix collision in the dedup pass). (L2-167 Item 3.)
  if (item.type === "concept") return `concept-${(item.data as FeedConceptData).key}`;
  return `tournament-${(item.data as any).key}`;
}
