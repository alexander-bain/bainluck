import type { FeedItem, FeedBundleData, FeedEventData, FeedFuturesData } from "@/lib/types";

export interface FeedSection {
  key: string;
  emoji: string;
  title: string;
  accent: string;
  items: FeedItem[];
  /**
   * How many CARDS this section renders — `items.length` unfolded, because a
   * bundle is one item that renders as several (#2597). The badge beside a
   * section title is a promise about what is below it, so it counts cards, not
   * feed slots. On the 2026-09-01 tennis payload the two numbers are 19 and 22.
   */
  count: number;
}

/** A group of FeedItems sharing the same canonical_market_key (cross-source). */
export interface GroupedMarket {
  canonicalKey: string;
  items: FeedItem[];
  /** Best score among the grouped items — used for sort position. */
  bestScore: number;
}

/** Recursion backstop, matching `feedItemSuppressionReason`'s own depth cap. */
const MAX_BUNDLE_DEPTH = 3;

/**
 * Replace every `bundle` item with its member items, recursively.
 *
 * #2597 — a bundle is a DISCOVER packaging device: one swipe-deck slot holding N
 * same-theme markets, so the deck spends one card on a story instead of five.
 * The grid surfaces that share this sectioner (`/categories/*`, `/sports`,
 * `/my-stuff`) have no slot pressure, so a bundle has nothing to buy there and
 * two things to break:
 *
 *  1. it has no `status`, so it fell through the sectioning ladder's events
 *     `else` arm below and filed a cluster of open markets under "Upcoming";
 *  2. it then reached `FeedCard`, whose default arm is the futures card, which
 *     read `data.top_outcomes.length` off a bundle that has no `top_outcomes`.
 *
 * (2) is why `/categories/tennis`, `/categories/soccer` and `/categories/politics`
 * all rendered "Something went wrong" on the second day of the US Open —
 * measured 2026-09-01, and `/categories/golf`, whose feed carried no bundle that
 * day, rendered normally in the same run. Unfolding makes the members visible as
 * their real market cards: on tennis the folded members were the two US Open
 * winner markets, the most-wanted questions on the site that week, invisible
 * behind an error boundary.
 *
 * Members are NOT also present at the top level — the serializer folds them out
 * — so this restores them rather than duplicating them.
 *
 * 🔴 WHERE THIS IS CALLED FROM IS A DELIBERATE CHOICE, NOT AN OVERSIGHT.
 * `FeedCard` calls it at the leaf. `groupFeedIntoSections` deliberately does NOT
 * — it routes a bundle to Top Markets whole and lets the leaf unfold it — because
 * flattening before `groupTopMarkets` feeds the members into the cross-source
 * grouping pass, and `canonical_market_key` does not currently mean what that
 * pass assumes. Measured on the committed 2026-09-01 tennis payload: THREE
 * unrelated markets share the key `tennis::championship:2026` — 114159 (men's US
 * Open winner), 114160 (women's US Open winner) and 59712997 ("Nikola Bartunkova
 * vs Elise Mertens: Set 1 Winner"). Only one of them is top-level today, so no
 * group forms; flattening would have made three, and `CombinedFeedCard` merges a
 * group's outcomes BY NAME across sources on the premise that they are one
 * question. The rendered card put Alcaraz and Elise Mertens in one outcome list.
 * Fixing a dead page by shipping that would be a bad trade. The key collision is
 * filed separately as a matching-layer defect; until it is fixed, unfolding stays
 * downstream of the grouping pass.
 */
export function flattenFeedBundles(
  items: FeedItem[],
  depth = 0,
): FeedItem[] {
  const out: FeedItem[] = [];
  for (const item of items) {
    if (item.type !== "bundle") {
      out.push(item);
      continue;
    }
    if (depth >= MAX_BUNDLE_DEPTH) continue;
    const members = (item.data as FeedBundleData).items ?? [];
    out.push(...flattenFeedBundles(members, depth + 1));
  }
  return out;
}

/**
 * How many cards a list of feed items renders — the bundle-unfolded length.
 * Exported because the page header counts the same thing the section badges do,
 * and two hand-rolled counts of one population is how they drift apart.
 */
export function countCards(items: FeedItem[]): number {
  return flattenFeedBundles(items).length;
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
    } else if (item.type === "bundle") {
      // #2597 — a bundle of markets belongs with the markets. Without this arm it
      // fell through to the events `else` at the bottom, where a missing `status`
      // reads as "not live, not completed" and filed a cluster of OPEN markets
      // under "Upcoming". It stays folded here on purpose (see
      // `flattenFeedBundles`); `FeedCard` unfolds it at the leaf, AFTER
      // `groupTopMarkets` has run, so the members never join a cross-source group.
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
  const push = (
    key: string,
    emoji: string,
    title: string,
    accent: string,
    items: FeedItem[],
  ) => {
    if (items.length === 0) return;
    sections.push({ key, emoji, title, accent, items, count: countCards(items) });
  };

  push("live", "\uD83D\uDD34", "Live Now", "text-accent-live", liveNow);
  push("finished", "\uD83C\uDFC1", "Just Happened", "text-text-secondary", justHappened);
  push("upcoming", "\uD83D\uDCC5", "Upcoming", "text-text-secondary", upcoming);
  push("markets", "\uD83D\uDCCA", "Top Markets", "text-accent-futures", topMarkets);

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
