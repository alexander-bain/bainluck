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
 * The one thing a bundled Top Markets card claims, and therefore the one thing
 * it has to be able to prove: **these are the same question, priced by
 * different venues.**
 *
 * #2622 — on 2026-09-01 `/sports` rendered a card headed "2026 Women's US Open
 * Winner (Tennis)", badged `1 sources`, with **Carlos Alcaraz #1 at 36%** and
 * Alexander Zverev third. Both US Open winner boards — men's and women's, two
 * distinct Polymarket markets with distinct `group_id`s and disjoint outcome
 * sets — carried the identical `canonical_market_key` `tennis::championship:2026`,
 * and this function bundled on that key ALONE. `CombinedFeedCard` then unioned
 * the outcomes and took the title from `items[0]`, so two men were relabelled
 * into the women's draw and one of them led it.
 *
 * The backend's own dedupe (`_dedupe_futures_by_canonical`, `routes/feed.py`)
 * had already refused to collapse the pair — it checks outcome overlap and
 * emitted both — but that verdict is never sent to the client, so the client
 * re-grouped on exactly the key the backend declined to trust.
 *
 * Two conditions now gate a bundle, and BOTH are structural rather than
 * cosmetic:
 *
 *  1. **At least two distinct sources.** A "N sources" card exists to compare
 *     venues. Two markets from ONE venue are two questions that venue chose to
 *     ask separately — it is the venue itself telling us they are not the same
 *     question. This alone kills the Alcaraz card (both rows are `polymarket`,
 *     which is why the badge read the absurd `1 sources`).
 *  2. **Non-disjoint outcomes.** Two venues pricing one question name at least
 *     one competitor the same way. Disjoint top-outcome sets mean the shared key
 *     is wrong, whatever it says.
 *
 * A key the discipline axis (#2622, `futures_categorization.py`) has not yet
 * separated therefore cannot produce a wrong card while the backfill drains —
 * the group simply falls apart into its members, each rendered under its own
 * real name.
 */
function outcomeNameSet(item: FeedItem): Set<string> {
  const data = item.data as FeedFuturesData;
  const names = new Set<string>();
  for (const outcome of data.top_outcomes ?? []) {
    const n = outcome?.name?.toLowerCase().trim();
    if (n) names.add(n);
  }
  return names;
}

export function bundleIsOneQuestion(items: FeedItem[]): boolean {
  if (items.length < 2) return false;

  const sources = new Set<string>();
  for (const item of items) {
    sources.add((item.data as FeedFuturesData).source || "unknown");
  }
  if (sources.size < 2) return false;

  // Every member must share at least one outcome with at least one other
  // member. A member that overlaps nothing is a different question wearing the
  // same key, and merging it is how a foreign outcome gets `items[0]`'s title.
  const sets = items.map(outcomeNameSet);
  return sets.every((set, i) => {
    if (set.size === 0) return false;
    return sets.some((other, j) => {
      if (i === j) return false;
      for (const name of set) if (other.has(name)) return true;
      return false;
    });
  });
}

/**
 * Group Top Markets items by canonical_market_key.
 * Items sharing a key are bundled into GroupedMarket entries — but only when
 * `bundleIsOneQuestion` can prove the group is a cross-source comparison.
 * Items without a key, with unique keys, or in a refused group remain as
 * singles.
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

  // Build ordered list: provable cross-source groups get bundled, everything
  // else stays flat under its own name.
  const ordered: (GroupedMarket | FeedItem)[] = [];

  for (const [canonicalKey, items] of byKey) {
    if (bundleIsOneQuestion(items)) {
      ordered.push({
        canonicalKey,
        items,
        bestScore: Math.max(...items.map((i) => i.score)),
      });
    } else {
      for (const item of items) ordered.push(item);
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
