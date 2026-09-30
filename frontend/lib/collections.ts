import { API_URL } from "@/lib/api";
import type { FeedEventData, FeedFuturesData, FeedItem } from "@/lib/types";

export type CollectionState = "published" | "unpublished" | "withdrawn" | "empty" | "unavailable";
export interface CollectionMember {
  key: string;
  id: number;
  type: "event" | "market";
  href: string;
  item: FeedItem;
  questionIds: number[];
  eventId: number | null;
}
export interface CollectionSection { key: string; title: string; members: CollectionMember[] }
export interface CollectionHub {
  slug: string;
  revision: number | null;
  state: CollectionState;
  title: string | null;
  edition: string | null;
  sections: CollectionSection[];
  children: { key: string; name: string; href: string }[];
  members: CollectionMember[];
  related: Record<string, CollectionMember[]>;
  note: string | null;
}
export interface CollectionReadingContext {
  slug: string;
  memberKey: string | null;
  offset: number;
  expanded: string[];
}

type ObjectValue = Record<string, unknown>;
const object = (value: unknown): ObjectValue | null => value !== null && typeof value === "object" && !Array.isArray(value) ? value as ObjectValue : null;
const text = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const positive = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value > 0;
const count = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
export const safeCollectionSlug = (value: unknown): value is string => typeof value === "string" && value.length <= 200 && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value);
export const collectionPath = (slug: string): string | null => safeCollectionSlug(slug) ? `/collections/${slug}` : null;
export const collectionMemberDomId = (key: string): string => `collection-member-${key}`;

function member(value: unknown): CollectionMember | null {
  const row = object(value), card = object(row?.card), destination = object(row?.destination);
  if (!row || !card || !destination || !positive(row.id) || card.id !== row.id) return null;
  const type = row.type;
  if (type !== "event" && type !== "market") return null;
  const href = type === "event" ? `/events/${row.id}` : `/futures/${row.id}`;
  const api = type === "event" ? `/api/events/${row.id}` : `/api/futures/${row.id}`;
  if (destination.kind !== type || destination.id !== row.id || destination.web !== href || destination.api !== api) return null;
  if (type === "event") {
    if (!text(card.home_team) || !text(card.away_team) || !text(card.commence_time) || !text(card.status)) return null;
    if (card.current_odds != null && !object(card.current_odds)) return null;
  } else {
    if (!text(card.name) || !text(card.status) || !Array.isArray(card.top_outcomes)) return null;
    if (!card.top_outcomes.every((value) => {
      const outcome = object(value);
      return outcome && text(outcome.name) && (outcome.probability == null || (typeof outcome.probability === "number" && Number.isFinite(outcome.probability) && outcome.probability >= 0 && outcome.probability <= 1));
    })) return null;
  }
  // The route's hydrated serializers supply the familiar card. This projection
  // does not sort outcomes, infer prices or change the event's served lifecycle.
  const data = type === "event" ? card as unknown as FeedEventData : card as unknown as FeedFuturesData;
  const item: FeedItem = { type: type === "event" ? "event" : "futures", score: 0, reason: "", headline: null, data };
  return { key: `${type}:${row.id}`, id: row.id, type, href, item,
    questionIds: Array.isArray(row.question_ids) ? row.question_ids.filter(positive) : [],
    eventId: positive(row.event_id) ? row.event_id : null };
}

const sectionTitles: Record<string, string> = {
  match_winner: "Games and winners", prop: "Player and game questions", title: "Championship",
  advancement: "Advancement", side_question: "More questions", doubles: "Doubles", unclassified: "More",
};

function editionLabel(value: unknown, slug: string): string | null {
  const edition = object(value);
  if (!edition || !positive(edition.season)) return null;
  if (edition.kind === "mlb_postseason" && edition.league === "mlb" && slug === `mlb-${edition.season}-postseason`) return `MLB · ${edition.season} · Postseason`;
  if (edition.kind === "nfl_season" && edition.league === "nfl" && slug === `nfl-${edition.season}`) return `NFL · ${edition.season}`;
  if (edition.kind !== "nfl_week" || edition.league !== "nfl" || !positive(edition.week) || edition.week > 99) return null;
  const prefix = edition.stage === "Regular Season" ? "" : edition.stage === "Pre Season" ? "preseason-" : edition.stage === "Post Season" ? "postseason-" : null;
  return prefix !== null && slug === `nfl-${edition.season}-${prefix}week-${edition.week}` ? `NFL · ${edition.season} · ${edition.stage} · Week ${edition.week}` : null;
}

export function parseCollection(value: unknown, slug: string): CollectionHub {
  const row = object(value);
  if (!safeCollectionSlug(slug) || !row || row.slug !== slug) throw new Error("This collection isn't available right now.");
  const known: CollectionState[] = ["published", "unpublished", "withdrawn", "empty", "unavailable"];
  const state: CollectionState = known.includes(row.state as CollectionState) ? row.state as CollectionState : "unpublished";
  const header = object(row.container);
  const title = (state === "published" || state === "empty") && header?.slug === slug && text(header.name) ? header.name : null;
  const base: CollectionHub = { slug, revision: positive(row.revision) ? row.revision : null, state, title,
    edition: editionLabel(row.edition, slug), sections: [], children: [], members: [], related: {}, note: null };
  if (state !== "published") {
    const notes = { unpublished: "This collection isn't available yet.", withdrawn: "This collection is no longer available.",
      empty: "There are no games or questions in this collection right now.", unavailable: "This collection isn't available right now." };
    return { ...base, note: notes[state] };
  }
  if (!base.revision || !base.edition || !title || !Array.isArray(row.sections)) throw new Error("This collection isn't available right now.");
  const seen = new Set<string>();
  let partial = !count(row.member_count) || !count(row.withheld_count) || (row.withheld_count as number) > 0 || (Array.isArray(row.withheld) && row.withheld.length > 0);
  const sections: CollectionSection[] = [];
  row.sections.forEach((value, index) => {
    const section = object(value);
    if (!section || !text(section.class) || !Array.isArray(section.members)) { partial = true; return; }
    const accepted: CollectionMember[] = [];
    section.members.forEach((value) => {
      const card = member(value);
      if (!card) { partial = true; return; }
      if (seen.has(card.key)) return;
      seen.add(card.key); accepted.push(card);
    });
    if (section.count !== section.members.length || accepted.length !== section.members.length) partial = true;
    if (accepted.length) sections.push({ key: `${index}:${section.class}`, title: sectionTitles[section.class] ?? "More", members: accepted });
  });
  const members = sections.flatMap((section) => section.members);
  if (members.length !== row.member_count) partial = true;
  const related: Record<string, CollectionMember[]> = {};
  for (const event of members.filter((m) => m.type === "event")) {
    const ids = new Set(event.questionIds);
    related[event.key] = members.filter((m) => m.type === "market" && ids.has(m.id) && m.eventId === event.id);
  }
  const relatedKeys = new Set(Object.values(related).flat().map((m) => m.key));
  const children: CollectionHub["children"] = [];
  const seenChildren = new Set<string>();
  if (Array.isArray(row.children)) for (const value of row.children) {
    const child = object(value), destination = object(child?.destination);
    if (!child || child.publication_state !== "published") continue;
    const href = safeCollectionSlug(child.slug) ? collectionPath(child.slug) : null;
    if (!href || !text(child.name) || !destination || destination.kind !== "container" || destination.slug !== child.slug || destination.api !== `/api/containers/${child.slug}` || (destination.web != null && destination.web !== href)) { partial = true; continue; }
    if (!seenChildren.has(href)) children.push({ key: `container:${child.slug}`, name: child.name, href });
    seenChildren.add(href);
  }
  return { ...base, members, related, children,
    sections: sections.map((section) => ({ ...section, members: section.members.filter((m) => !relatedKeys.has(m.key)) })).filter((s) => s.members.length > 0),
    note: partial ? "Some games or questions aren't available right now." : !members.length && !children.length ? "No games or questions are available right now." : null };
}

export async function fetchCollection(slug: string, signal?: AbortSignal): Promise<CollectionHub> {
  if (!safeCollectionSlug(slug)) throw new Error("This collection isn't available right now.");
  const response = await fetch(`${API_URL}/api/containers/${slug}`, { cache: "no-store", signal });
  if (response.status === 404) return parseCollection({ slug, state: "unavailable" }, slug);
  if (!response.ok) throw new Error("Couldn't load this collection. Please try again.");
  return parseCollection(await response.json(), slug);
}

export function reconcileCollectionContext(context: CollectionReadingContext | null, hub: CollectionHub): CollectionReadingContext | null {
  if (!context || context.slug !== hub.slug || hub.state !== "published" || !Number.isFinite(context.offset) || !Array.isArray(context.expanded)) return null;
  const keys = new Set(hub.members.map((m) => m.key).concat(hub.children.map((c) => c.key)));
  return { ...context, memberKey: context.memberKey && keys.has(context.memberKey) ? context.memberKey : null,
    expanded: context.expanded.filter((key) => keys.has(key) && (hub.related[key]?.length ?? 0) > 0) };
}

export function collectionRefreshInterval(hub: CollectionHub | null, now = Date.now()): number {
  if (hub?.state !== "published") return 0;
  const games = hub.members.filter((m) => m.type === "event").map((m) => m.item.data as FeedEventData);
  if (games.some((e) => e.status === "live")) return 30000;
  return games.some((e) => ["scheduled", "upcoming"].includes(e.status) && Math.abs(Date.parse(e.commence_time) - now) <= 86400000) ? 60000 : 0;
}
