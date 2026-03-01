import type { FeedItem, FeedEventData } from "@/lib/types";

export interface FeedSection {
  key: string;
  emoji: string;
  title: string;
  accent: string;
  items: FeedItem[];
}

/**
 * Group feed items into visual sections: Live Now, Just Happened, Upcoming, Top Markets.
 * Shared between homepage and category pages.
 */
export function groupFeedIntoSections(items: FeedItem[]): FeedSection[] {
  if (items.length === 0) return [];

  const liveNow: FeedItem[] = [];
  const justHappened: FeedItem[] = [];
  const upcoming: FeedItem[] = [];
  const topMarkets: FeedItem[] = [];

  for (const item of items) {
    if (item.type === "futures") {
      topMarkets.push(item);
    } else {
      const data = item.data as FeedEventData;
      if (data.status === "live") {
        liveNow.push(item);
      } else if (data.status === "completed" || data.status === "closed") {
        justHappened.push(item);
      } else {
        upcoming.push(item);
      }
    }
  }

  const sections: FeedSection[] = [];
  if (liveNow.length > 0)
    sections.push({
      key: "live",
      emoji: "\uD83D\uDD34",
      title: "Live Now",
      accent: "text-accent-live",
      items: liveNow,
    });
  if (justHappened.length > 0)
    sections.push({
      key: "finished",
      emoji: "\uD83C\uDFC1",
      title: "Just Happened",
      accent: "text-text-secondary",
      items: justHappened,
    });
  if (upcoming.length > 0)
    sections.push({
      key: "upcoming",
      emoji: "\uD83D\uDCC5",
      title: "Upcoming",
      accent: "text-text-secondary",
      items: upcoming,
    });
  if (topMarkets.length > 0)
    sections.push({
      key: "markets",
      emoji: "\uD83D\uDCCA",
      title: "Top Markets",
      accent: "text-accent-futures",
      items: topMarkets,
    });

  return sections;
}
