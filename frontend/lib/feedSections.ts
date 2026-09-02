import type { FeedItem, FeedBundleData, FeedEventData, FeedFuturesData } from "@/lib/types";

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
