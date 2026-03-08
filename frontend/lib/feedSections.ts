import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";

export interface FeedSection {
  key: string;
  emoji: string;
  title: string;
  accent: string;
  items: FeedItem[];
}

/** A group of FeedItems sharing the same canonical_market_key (cross-source). */
export interface GroupedMarket {
  canonicalKey: string;
  items: FeedItem[];
  /** Best score among the grouped items — used for sort position. */
  bestScore: number;
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

/**
 * Group Top Markets items by canonical_market_key.
 * Items sharing a key are bundled into GroupedMarket entries.
 * Items without a key (or unique keys) remain as singles.
 *
 * Returns { groups, singles } — both sorted by best score descending.
 */
export function groupTopMarkets(marketItems: FeedItem[]): {
  /** Ordered list mixing GroupedMarket and single FeedItem, sorted by score. */
  ordered: (GroupedMarket | FeedItem)[];
} {
  const byKey = new Map<string, FeedItem[]>();
  const noKey: FeedItem[] = [];

  for (const item of marketItems) {
    const data = item.data as FeedFuturesData;
    const key = data.canonical_market_key;
    if (key) {
      if (!byKey.has(key)) byKey.set(key, []);
      byKey.get(key)!.push(item);
    } else {
      noKey.push(item);
    }
  }

  // Build ordered list: groups (2+ items) get bundled, singles stay flat
  const ordered: (GroupedMarket | FeedItem)[] = [];

  for (const [canonicalKey, items] of byKey) {
    if (items.length >= 2) {
      ordered.push({
        canonicalKey,
        items,
        bestScore: Math.max(...items.map((i) => i.score)),
      });
    } else {
      ordered.push(items[0]);
    }
  }

  for (const item of noKey) {
    ordered.push(item);
  }

  // Sort by score (groups use bestScore, singles use item.score)
  ordered.sort((a, b) => {
    const scoreA = "bestScore" in a ? a.bestScore : a.score;
    const scoreB = "bestScore" in b ? b.bestScore : b.score;
    return scoreB - scoreA;
  });

  return { ordered };
}

/** Type guard: is this entry a GroupedMarket or a single FeedItem? */
export function isGroupedMarket(
  entry: GroupedMarket | FeedItem
): entry is GroupedMarket {
  return "canonicalKey" in entry && "items" in entry;
}
