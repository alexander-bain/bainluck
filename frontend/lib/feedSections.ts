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
    } else if (item.type === "tournament") {
      // Tournaments sort into live or upcoming based on schedule_status
      const td = item.data as unknown as Record<string, unknown>;
      if (td.schedule_status === "in-progress") {
        liveNow.push(item);
      } else {
        upcoming.push(item);
      }
    } else if (item.type === "concept") {
      // Event concepts (UFC cards, …) sort into live or upcoming by status.
      const cd = item.data as unknown as Record<string, unknown>;
      if (cd.status === "live") {
        liveNow.push(item);
      } else {
        upcoming.push(item);
      }
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
 * Outcome names of a futures item, lowercased and trimmed.
 * Empty set means "this item makes no claim about its outcomes".
 */
function outcomeNames(item: FeedItem): Set<string> {
  const data = item.data as FeedFuturesData;
  const names = new Set<string>();
  for (const outcome of data.top_outcomes ?? []) {
    const name = outcome?.name?.toLowerCase().trim();
    if (name) names.add(name);
  }
  return names;
}

/**
 * Do two futures items name at least one outcome in common?
 *
 * Mirrors the backend's `_outcomes_overlap` (`routes/feed.py`), including its
 * benefit-of-the-doubt rule: an item with no outcomes cannot be disproved, so
 * it is treated as overlapping. Binary Yes/No pairs overlap by construction,
 * which keeps the legitimate cross-source binary card intact.
 */
function outcomesOverlap(a: FeedItem, b: FeedItem): boolean {
  const namesA = outcomeNames(a);
  const namesB = outcomeNames(b);
  if (namesA.size === 0 || namesB.size === 0) return true;
  for (const name of namesA) {
    if (namesB.has(name)) return true;
  }
  return false;
}

/**
 * May these two items appear inside one CombinedFeedCard?
 *
 * A combined card is a CROSS-SOURCE comparison of one question — it prints an
 * "N sources" badge and takes its title and link from `items[0]`. So a pair
 * qualifies only when it is genuinely (a) two different sources and (b) the
 * same question. A shared `canonical_market_key` proves neither: the key has no
 * gender or discipline axis, so the 2026 Men's and Women's US Open winner
 * markets both key to `tennis::championship:2026` (#2622) — and 1,341 open
 * markets share that one key. Bundling them relabelled Carlos Alcaraz as the
 * favourite to win the women's draw.
 */
function canCombine(a: FeedItem, b: FeedItem): boolean {
  const sourceA = (a.data as FeedFuturesData).source ?? "unknown";
  const sourceB = (b.data as FeedFuturesData).source ?? "unknown";
  if (sourceA === sourceB) return false;
  return outcomesOverlap(a, b);
}

/**
 * Group Top Markets items by canonical_market_key.
 * Items sharing a key are bundled into GroupedMarket entries — but only when
 * they pass `canCombine`, i.e. they are the same question seen from different
 * sources. Items without a key, with a unique key, or that share a key with
 * nothing they may combine with, remain as singles.
 *
 * Returns { ordered } — sorted by best score descending.
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

  // Build ordered list: compatible clusters (2+ items) get bundled, the rest
  // stay flat. Highest-scoring item first so the strongest market seeds its
  // cluster and supplies the card's title and link.
  const ordered: (GroupedMarket | FeedItem)[] = [];

  for (const [canonicalKey, items] of byKey) {
    const clusters: FeedItem[][] = [];
    for (const item of [...items].sort((a, b) => b.score - a.score)) {
      const home = clusters.find((cluster) =>
        cluster.every((member) => canCombine(member, item))
      );
      if (home) home.push(item);
      else clusters.push([item]);
    }

    for (const cluster of clusters) {
      if (cluster.length >= 2) {
        ordered.push({
          canonicalKey,
          items: cluster,
          bestScore: Math.max(...cluster.map((i) => i.score)),
        });
      } else {
        ordered.push(cluster[0]);
      }
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
