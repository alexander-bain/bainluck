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
export interface CollectionSection { key: string; cls: string; title: string; members: CollectionMember[] }
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
  // #9925 — a theme collection (AI, Oscars) is read a page at a time at one
  // revision. Null on every NFL/MLB hub, which arrives whole.
  theme: { totalCount: number; nextCursor: string | null; inventoryComplete: boolean; revisionMoved: boolean } | null;
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

// #9925: the theme registry's own slugs — `ai` (continuing) and `oscars-<year>`
// (an edition). Any other theme subject is not a collection this reader knows.
const themeLabel = (edition: ObjectValue, slug: string): string | null =>
  edition.kind === "theme_continuing" && edition.subject === "ai" && slug === "ai" ? "AI · Ongoing"
  : edition.kind === "theme_edition" && edition.subject === "oscars" && positive(edition.edition) && slug === `oscars-${edition.edition}` ? `Oscars · ${edition.edition}`
  : null;
const isTheme = (value: unknown): boolean => { const edition = object(value); return edition?.kind === "theme_continuing" || edition?.kind === "theme_edition"; };
const themeSectionTitles: Record<string, Record<string, string>> = {
  oscars: { title: "Award winners", advancement: "Nominations", side_question: "More questions" },
  ai: { side_question: "Questions" },
};
const cursorText = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 64 && /^[A-Za-z0-9_-]+$/.test(value);

function editionLabel(value: unknown, slug: string): string | null {
  const edition = object(value);
  if (edition && isTheme(edition)) return themeLabel(edition, slug);
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
    edition: editionLabel(row.edition, slug), sections: [], children: [], members: [], related: {}, note: null, theme: null };
  if (state !== "published") {
    const notes = { unpublished: "This collection isn't available yet.", withdrawn: "This collection is no longer available.",
      empty: "There are no games or questions in this collection right now.", unavailable: "This collection isn't available right now." };
    return { ...base, note: notes[state] };
  }
  if (!base.revision || !base.edition || !title || !Array.isArray(row.sections)) throw new Error("This collection isn't available right now.");
  // A theme page's `member_count` is this page; the whole collection's count is
  // the snapshot's `counts.shown_count`, the same on every page of a revision.
  const counts = object(row.counts), page = object(row.page);
  let theme: CollectionHub["theme"] = null;
  if (isTheme(row.edition)) {
    if (!counts || !count(counts.shown_count) || typeof counts.inventory_complete !== "boolean" || !page || (page.next_cursor !== null && !cursorText(page.next_cursor)))
      throw new Error("This collection isn't available right now.");
    theme = { totalCount: counts.shown_count, nextCursor: page.next_cursor as string | null, inventoryComplete: counts.inventory_complete, revisionMoved: row.revision_moved === true };
  }
  const titles = theme ? themeSectionTitles[(object(row.edition)?.subject as string)] ?? {} : sectionTitles;
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
    if (accepted.length) sections.push({ key: `${index}:${section.class}`, cls: section.class, title: titles[section.class] ?? "More", members: accepted });
  });
  const members = sections.flatMap((section) => section.members);
  if (members.length !== row.member_count) partial = true;
  const related = relate(members);
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
  return { ...base, members, related, children, theme,
    sections: sections.map((section) => ({ ...section, members: section.members.filter((m) => !relatedKeys.has(m.key)) })).filter((s) => s.members.length > 0),
    note: partial ? "Some games or questions aren't available right now." : !members.length && !children.length ? "No games or questions are available right now." : null };
}

function relate(members: CollectionMember[]): Record<string, CollectionMember[]> {
  const related: Record<string, CollectionMember[]> = {};
  for (const event of members.filter((m) => m.type === "event")) {
    const ids = new Set(event.questionIds);
    related[event.key] = members.filter((m) => m.type === "market" && ids.has(m.id) && m.eventId === event.id);
  }
  return related;
}

export interface CollectionPageRequest { revision: number; cursor: string }
export async function fetchCollection(slug: string, signal?: AbortSignal, page?: CollectionPageRequest): Promise<CollectionHub> {
  if (!safeCollectionSlug(slug)) throw new Error("This collection isn't available right now.");
  // The cursor is opaque and belongs to its revision; both travel together.
  const query = page ? `?${new URLSearchParams({ revision: String(page.revision), cursor: page.cursor })}` : "";
  const response = await fetch(`${API_URL}/api/containers/${slug}${query}`, { cache: "no-store", signal });
  if (response.status === 404) return parseCollection({ slug, state: "unavailable" }, slug);
  if (!response.ok) throw new Error("Couldn't load this collection. Please try again.");
  return parseCollection(await response.json(), slug);
}

// #9982: the last accepted (published) hub per slug, held in memory across
// client-side navigation. Back from a game and in-place refreshes redraw it at
// once instead of "Loading collection…"; a transient failure keeps it with an
// honest error. An authoritative non-published answer (404, withdrawn,
// unpublished, empty) replaces it, so a real withdrawal never stays visible.
const acceptedHubs = new Map<string, CollectionHub>();
const ACCEPTED_HUB_LIMIT = 4;
export const acceptedCollection = (slug: string): CollectionHub | null => acceptedHubs.get(slug) ?? null;
// #9925: causal order across the refresh and Load more lanes. Every read takes
// a ticket when it leaves. Accepting an authoritative non-published answer
// (withdrawn, unavailable, …) closes every ticket issued so far, so a read
// already in flight — which left while the old membership stood — can no
// longer bring it back; a read that leaves afterwards is admitted as usual.
let readsIssued = 0;
const closedBelow = new Map<string, number>();
export const openCollectionRead = (): number => ++readsIssued;
export const collectionReadAdmitted = (slug: string, ticket: number): boolean => ticket >= (closedBelow.get(slug) ?? 0);
export const forgetAcceptedCollections = (): void => { acceptedHubs.clear(); closedBelow.clear(); };
const accept = (slug: string, hub: CollectionHub): CollectionHub => {
  acceptedHubs.delete(slug);
  if (hub.slug === slug && hub.state === "published") {
    acceptedHubs.set(slug, hub);
    for (const oldest of acceptedHubs.keys()) { if (acceptedHubs.size <= ACCEPTED_HUB_LIMIT) break; acceptedHubs.delete(oldest); }
  } else closedBelow.set(slug, readsIssued + 1);
  return hub;
};

// #9925: two theme reads of ONE revision list the same members in the same
// order (the snapshot is immutable per revision), so `later`'s cards join or
// refresh `earlier`'s. Anything else — another slug, revision, a moved
// revision, a member the earlier pages never placed — is not one collection
// and returns null: the caller replaces rather than mixes.
function sameRevision(earlier: CollectionHub, later: CollectionHub): boolean {
  return earlier.slug === later.slug && earlier.state === "published" && later.state === "published" && !!earlier.theme && !!later.theme
    && !later.theme.revisionMoved && earlier.revision !== null && earlier.revision === later.revision;
}
function combine(earlier: CollectionHub, later: CollectionHub, nextCursor: string | null, note: string | null): CollectionHub {
  const fresh = new Map(later.members.map((m) => [m.key, m]));
  const members = earlier.members.map((m) => fresh.get(m.key) ?? m);
  const placed = new Set(members.map((m) => m.key));
  members.push(...later.members.filter((m) => !placed.has(m.key)));
  const sections: CollectionSection[] = earlier.sections.map((s) => ({ ...s, members: s.members.map((m) => fresh.get(m.key) ?? m) }));
  for (const section of later.sections) {
    const add = section.members.filter((m) => !placed.has(m.key));
    if (!add.length) continue;
    const last = sections[sections.length - 1];
    if (last?.cls === section.cls) sections[sections.length - 1] = { ...last, members: [...last.members, ...add] };
    else sections.push({ ...section, key: `${sections.length}:${section.cls}`, members: add });
  }
  return { ...later, members, sections, related: relate(members), note, theme: { ...later.theme!, nextCursor } };
}

// "Load more": `page` answers `requested` (the hub's revision and next_cursor
// when it was asked). Same revision appends; a moved revision or an
// authoritative non-published answer replaces; a page for a hub that has since
// moved on (a refresh, another slug) is dropped.
export function settleCollectionPage(slug: string, current: CollectionHub, requested: CollectionPageRequest, page: CollectionHub): CollectionHub {
  if (current.slug !== slug || page.slug !== slug || current.revision !== requested.revision || current.theme?.nextCursor !== requested.cursor) return current;
  if (!sameRevision(current, page)) return accept(slug, page);
  return accept(slug, combine(current, page, page.theme!.nextCursor, current.note ?? page.note));
}

export function settleCollectionRead(slug: string, read: { hub: CollectionHub } | { failed: true }): { hub: CollectionHub | null; error: string | null } {
  if ("hub" in read) {
    // A refresh re-reads page 1. At the same revision the pages already loaded
    // stay (and Back finds a later-page member); its own cards are refreshed.
    const held = acceptedCollection(slug);
    // A refresh and a Load more run side by side. A revision only moves forward,
    // so a refresh that answers with an EARLIER theme revision than the one the
    // page lane already admitted is the slower, older read: it never rolls the
    // list or cursor back. Non-published answers and NFL/MLB hubs still replace.
    if (held?.theme && read.hub.theme && held.state === "published" && read.hub.state === "published"
      && held.revision !== null && read.hub.revision !== null && read.hub.revision < held.revision)
      return { hub: held, error: null };
    const heldKeys = new Set(held?.members.map((m) => m.key));
    if (held && sameRevision(held, read.hub) && read.hub.members.every((m) => heldKeys.has(m.key)))
      return { hub: accept(slug, combine(held, read.hub, held.theme!.nextCursor, read.hub.note)), error: null };
    return { hub: accept(slug, read.hub), error: null };
  }
  const retained = acceptedCollection(slug);
  return retained ? { hub: retained, error: "Couldn't refresh this collection. Showing the last update." }
    : { hub: null, error: "Couldn't load this collection. Please try again." };
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
