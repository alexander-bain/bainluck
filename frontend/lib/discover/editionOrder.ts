import { getDiscoverCategoryAdjustment, type DiscoverProfile } from "@/lib/discoverInteractions";

/**
 * #2603 — Alex, 2026-09-01: "The Discover cards reorder themselves on
 * web-desktop while I'm on the screen."
 *
 * #4430 stopped the 120 s revalidation from assigning a new page one over the
 * top: `reconcilePage1` holds the reader's order and only swaps in fresh copies.
 * But the page then runs the held list through the local personalization pass,
 * which re-sorts every window of five past the pinned lead by
 *
 *     card.score + categoryAdjustment(profile)
 *
 * and both inputs were LIVE. The fresh copy carries the server's new score (a
 * game "starting soon" goes 78 → 80, a futures card's movement decays), and the
 * profile is re-read on every like, dismiss, share and tap. Either one changing
 * re-sorted cards the reader was looking at — the reconcile held the order and
 * the very next stage undid it.
 *
 * 🔴 THE ORDER IS DECIDED ONCE PER EDITION. A card is ranked by the score it
 * carried when it first entered the edition, and the profile is the one that
 * stood when the edition opened. Live data still reaches the card (prices,
 * scores and clocks render from the fresh copy); only its PLACE is frozen. A
 * like still counts — it shapes the next edition (manual refresh or reload),
 * which is where "new/changed cards should slot in on next visit" puts it.
 */

/** Record each card's score the first time it is seen. First write wins. */
export function recordEditionScores<T extends { score?: number | null }>(
  scores: Map<string, number>,
  items: T[],
  getId: (item: T) => string,
): void {
  for (const item of items) {
    const id = getId(item);
    if (!scores.has(id)) scores.set(id, item.score ?? 0);
  }
}

export interface EditionRank {
  /** The score the card entered the edition with — never the live one. */
  score: number;
  category: string;
}

/**
 * Soft category personalization: the first three cards are pinned, and each
 * following window of five is re-ranked by edition score plus the profile's
 * bounded category adjustment. Ties keep the incoming order.
 */
export function applyLocalPersonalization<G>(
  items: G[],
  profile: DiscoverProfile | null,
  rankOf: (item: G) => EditionRank | null,
): G[] {
  if (!profile || items.length <= 6) return items;

  const pinnedLead = items.slice(0, 3);
  const rest = items.slice(3);
  const result: G[] = [...pinnedLead];
  const windowSize = 5;

  for (let start = 0; start < rest.length; start += windowSize) {
    const window = rest.slice(start, start + windowSize);
    const ranked = window
      .map((item, idx) => {
        const rank = rankOf(item);
        const adjustment = rank ? getDiscoverCategoryAdjustment(profile, rank.category) : 0;
        return { item, idx, adjustedScore: (rank?.score ?? 0) + adjustment };
      })
      .sort((a, b) => {
        const scoreDiff = b.adjustedScore - a.adjustedScore;
        return Math.abs(scoreDiff) > 0.001 ? scoreDiff : a.idx - b.idx;
      })
      .map((entry) => entry.item);
    result.push(...ranked);
  }

  return result;
}

/**
 * CERT-3393 repair `2603-MANUAL-REFRESH-OPENS-NEW-EDITION`.
 *
 * A manual refresh is the reader asking for a new edition, so it must not go
 * through the background path: `reconcilePage1` holds the old ids in the old
 * order and only appends, and the score map would immediately re-record the
 * old cards. An ACCEPTED, non-empty refresh therefore replaces page one
 * wholesale and reseeds the scores from the new cards alone. Anything else — a
 * thrown fetch, an unavailable or degraded payload, an empty page — keeps the
 * edition the reader already has.
 */
export type ManualRefreshOutcome<P, T> =
  | { kind: "new-edition"; payload: P; page1: T[]; scores: Map<string, number>; hasMore: boolean }
  | { kind: "keep"; showUnavailable: boolean };

export async function runManualRefresh<P extends { items?: T[] | null }, T extends { score?: number | null }>(deps: {
  fetchPage: () => Promise<P>;
  decide: (payload: P) => { acceptItems: boolean; hasMore: boolean; showUnavailable: boolean };
  getId: (item: T) => string;
}): Promise<ManualRefreshOutcome<P, T>> {
  let payload: P;
  try {
    payload = await deps.fetchPage();
  } catch {
    return { kind: "keep", showUnavailable: true };
  }
  const decision = deps.decide(payload);
  const page1 = payload.items ?? [];
  if (!decision.acceptItems || page1.length === 0) {
    return { kind: "keep", showUnavailable: decision.showUnavailable };
  }
  const scores = new Map<string, number>();
  recordEditionScores(scores, page1, deps.getId);
  return { kind: "new-edition", payload, page1, scores, hasMore: decision.hasMore };
}
