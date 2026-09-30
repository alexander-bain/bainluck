/**
 * #9905 — web Discover opens the published NFL-week / MLB-postseason hubs.
 *
 * The feed places a `type: "collection"` card immediately before the strongest
 * of its members (`backend/app/utils/feed_collections.py`). This module is the
 * whole client side of that contract:
 *
 * - `admitCollection` decides whether one envelope may render. It refuses
 *   anything unpublished, malformed, of an edition this ship does not offer, or
 *   without the canonical `/collections/{slug}` destination (#9886) — a card
 *   that cannot open its hub is not shown.
 * - `splitCollections` / `placeCollections` keep the server's placement. The
 *   page re-orders ordinary cards (sport spacing, local personalization), and
 *   spacing alone would push an NFL hub away from the NFL game it sits in front
 *   of. So collections leave that pipeline, and each is put back directly
 *   before the first card that followed it in the served order and is still
 *   on the page. No inventory read, no slot, no score of its own.
 *
 * A refused collection is dropped on its own; the ordinary cards around it are
 * untouched.
 */

import type { FeedCollectionData, FeedItem } from "@/lib/types";

export interface DiscoverCollectionEntry {
  slug: string;
  name: string;
  href: string;
  /** "16 games · 40 questions" — empty parts are left out. */
  subtitle: string;
}

const NFL_STAGE_PREFIX: Record<string, string> = {
  "Regular Season": "",
  "Pre Season": "preseason-",
  "Post Season": "postseason-",
};

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isPositiveInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

/**
 * The slug the backend's own adapters would write for this edition, or null.
 * The same round-trip `edition_for_slug` and native `DiscoverCollectionFeed`
 * apply, so a slug and edition that disagree never become a link.
 */
function canonicalSlug(edition: FeedCollectionData["edition"]): string | null {
  if (!edition || !isPositiveInt(edition.season)) return null;
  const season = edition.season;
  if (edition.league === "mlb" && edition.kind === "mlb_postseason") {
    if (edition.stage != null || edition.week != null) return null;
    return `mlb-${season}-postseason`;
  }
  if (edition.league === "nfl" && edition.kind === "nfl_week") {
    const week = edition.week;
    if (!isPositiveInt(week) || week > 99) return null;
    const prefix = typeof edition.stage === "string" ? NFL_STAGE_PREFIX[edition.stage] : undefined;
    if (prefix === undefined) return null;
    return `nfl-${season}-${prefix}week-${week}`;
  }
  return null;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function isCollectionItem(item: FeedItem | null | undefined): boolean {
  return !!item && typeof item === "object" && item.type === "collection";
}

export function admitCollection(item: FeedItem | null | undefined): DiscoverCollectionEntry | null {
  if (!isCollectionItem(item)) return null;
  const data: unknown = item!.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  const card = data as FeedCollectionData;

  if (card.state !== "published") return null;
  if (!isPositiveInt(card.id) || !isPositiveInt(card.revision)) return null;
  const name = typeof card.name === "string" ? card.name.trim() : "";
  if (!name) return null;

  const slug = card.slug;
  if (typeof slug !== "string" || slug !== canonicalSlug(card.edition)) return null;

  const games = card.game_count;
  const questions = card.question_count;
  if (!isCount(games) || !isCount(questions) || games + questions === 0) return null;

  const href = `/collections/${slug}`;
  const dest = card.destination;
  if (!dest || dest.kind !== "container" || dest.slug !== slug || dest.web !== href) return null;

  const parts: string[] = [];
  if (games > 0) parts.push(plural(games, "game"));
  if (questions > 0) parts.push(plural(questions, "question"));
  return { slug, name, href, subtitle: parts.join(" · ") };
}

export interface AnchoredCollection {
  item: FeedItem;
  /** Ids of the ordinary cards served after this one, in served order. */
  followers: string[];
}

/**
 * Separate the collection cards from the ordinary ones. Refused collections
 * are dropped here; admitted ones remember which cards came after them.
 */
export function splitCollections(
  items: FeedItem[],
  getId: (item: FeedItem) => string,
): { ordinary: FeedItem[]; anchored: AnchoredCollection[] } {
  const ordinary: FeedItem[] = [];
  const anchored: AnchoredCollection[] = [];
  const pending: AnchoredCollection[] = [];
  for (const item of items) {
    if (isCollectionItem(item)) {
      if (admitCollection(item)) {
        const entry = { item, followers: [] as string[] };
        anchored.push(entry);
        pending.push(entry);
      }
      continue;
    }
    const id = getId(item);
    for (const entry of pending) entry.followers.push(id);
    ordinary.push(item);
  }
  return { ordinary, anchored };
}

/**
 * Put each collection back directly before the first of its followers still
 * on the page — normally the member the server placed it in front of. If none
 * of them survived (dismissed, stale), it goes at the end. Collections that
 * land in front of the same card keep their served order.
 */
export function placeCollections<G>(
  grouped: G[],
  anchored: AnchoredCollection[],
  idsOf: (group: G) => string[],
  wrap: (item: FeedItem) => G,
): G[] {
  if (anchored.length === 0) return grouped;
  const position = new Map<string, number>();
  grouped.forEach((group, index) => {
    for (const id of idsOf(group)) if (!position.has(id)) position.set(id, index);
  });
  const before = new Map<number, G[]>();
  const tail: G[] = [];
  for (const entry of anchored) {
    const target = entry.followers.find((id) => position.has(id));
    if (target === undefined) {
      tail.push(wrap(entry.item));
      continue;
    }
    const index = position.get(target)!;
    if (!before.has(index)) before.set(index, []);
    before.get(index)!.push(wrap(entry.item));
  }
  const result: G[] = [];
  grouped.forEach((group, index) => {
    const lead = before.get(index);
    if (lead) result.push(...lead);
    result.push(group);
  });
  result.push(...tail);
  return result;
}
