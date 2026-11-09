import { API_URL } from "@/lib/api";
import type { FeedEventData, FeedFuturesData, FeedItem } from "@/lib/types";
import { priceKey } from "@/lib/discover/priceRefresh";

export type CollectionState = "published" | "unpublished" | "withdrawn" | "empty" | "unavailable";
export interface CollectionMember {
  key: string;
  id: number;
  type: "event" | "market";
  href: string;
  item: FeedItem;
  questionIds: number[];
  eventId: number | null;
  linkPresentation?: "game" | "inline" | "secondary";
  relatedMarketCount?: number;
}
export interface CollectionSection { key: string; cls: string; title: string; note: string | null; layout?: string; members: CollectionMember[] }
export interface CollectionPin { slug: string; name: string; href: string; subtitle: string; pin_until: string }
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
  // #11040: a theme family's one-line page note and the
  // family itself ("departure"), both from the served edition. Null elsewhere.
  dek: string | null;
  family: string | null;
  // #9925 — a theme collection (AI, Oscars) is read a page at a time at one
  // revision. Null on every NFL/MLB hub, which arrives whole.
  theme: { totalCount: number; nextCursor: string | null; inventoryComplete: boolean; revisionMoved: boolean } | null;
  subtitle?: string | null;
  pin?: CollectionPin | null;
  relatedSummary?: { count: number; unclassifiedCount: number };
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
export const isNflWeekCollectionSlug = (slug: string): boolean => /^nfl-\d{4}-(?:preseason-|postseason-)?week-[1-9]\d?$/.test(slug);
export const collectionPath = (slug: string): string | null => safeCollectionSlug(slug) ? `/collections/${slug}` : null;
export const collectionMemberDomId = (key: string): string => `collection-member-${key}`;

function member(value: unknown, quiet = false): CollectionMember | null {
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
    if (row.related_count != null && !count(row.related_count)) return null;
  } else {
    if (!text(card.name) || !text(card.status) || !Array.isArray(card.top_outcomes)) return null;
    if (!card.top_outcomes.every((value) => {
      const outcome = object(value);
      return outcome && text(outcome.name) && (outcome.probability == null || (typeof outcome.probability === "number" && Number.isFinite(outcome.probability) && outcome.probability >= 0 && outcome.probability <= 1));
    })) return null;
  }
  // The route's hydrated serializers supply the familiar card. This projection
  // does not sort outcomes, infer prices or change the event's served lifecycle.
  // #11040: a story page prints no movement until a dated basis is
  // served for it. The served card's per-outcome `movement` is the stored
  // per-write change (reader_change_24h), whose age is unknown, so it is dropped.
  const shown = quiet && type === "market"
    ? { ...card, top_outcomes: (card.top_outcomes as unknown[]).map((o) => ({ ...(o as ObjectValue), movement: null })) }
    : card;
  const data = type === "event" ? shown as unknown as FeedEventData : shown as unknown as FeedFuturesData;
  const item: FeedItem = { type: type === "event" ? "event" : "futures", score: 0, reason: "", headline: null, data };
  const linkPresentation = card.collection_link_presentation;
  return { key: `${type}:${row.id}`, id: row.id, type, href, item,
    questionIds: Array.isArray(row.question_ids) ? row.question_ids.filter(positive) : [],
    eventId: positive(row.event_id) ? row.event_id : null,
    relatedMarketCount: type === "event" && count(row.related_count) ? row.related_count : undefined,
    linkPresentation: linkPresentation === "game" || linkPresentation === "inline" || linkPresentation === "secondary"
      ? linkPresentation : undefined };
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
// #11040: a departure story is a finite theme whose edition carries
// `family: "departure"`. The reader keys its label, sections and notes on the
// family, never on the person, so a second story needs no reader change.
const departureLabel = (edition: ObjectValue, slug: string): string | null =>
  edition.family === "departure" && edition.kind === "theme_edition" && typeof edition.subject === "string" && safeCollectionSlug(edition.subject)
  && positive(edition.edition) && slug === `${edition.subject}-${edition.edition}` && text(edition.role) && edition.role.length <= 60
    ? `${edition.role.trim()} · Story` : null;
const familySections: Record<string, Record<string, { title: string; note: string }>> = {
  departure: {
    departure_announced: { title: "An announced exit counts", note: "An announced resignation or removal counts, even if it takes effect later. Each date covers everything up to that date." },
    departure_vacated: { title: "Only an actual departure counts", note: "Only actually leaving the job counts. An announcement alone doesn't. Each date covers everything up to that date." },
    departure_rules_unread: { title: "Leaving the job · rules not checked yet", note: "How each of these settles hasn't been checked, so their numbers may not be comparable." },
    departure_left_administration: { title: "Leaving the administration", note: "About leaving the administration altogether, not only this job." },
    after_role: { title: "What comes next", note: "About the next job, not about whether or when this one ends." },
    side_question: { title: "About the job", note: "Not about leaving it." },
  },
};
const familyDek: Record<string, string> = {
  departure: "When this job might end, and what comes next. Each market keeps its own number, because their rules can differ.",
};
const isTheme = (value: unknown): boolean => { const edition = object(value); return edition?.kind === "theme_continuing" || edition?.kind === "theme_edition"; };
const themeSectionTitles: Record<string, Record<string, string>> = {
  oscars: { title: "Award winners", advancement: "Nominations", side_question: "More questions" },
  ai: { side_question: "Markets" },
};
const cursorText = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 64 && /^[A-Za-z0-9_-]+$/.test(value);

// #5343: a provider event is one complete, unpaginated collection. Keep the
// provider identity as its digit string; coercion would admit a different slug.
const providerEventLabel = (edition: ObjectValue, slug: string): string | null =>
  edition.provider === "polymarket" && typeof edition.event_id === "string"
  && edition.event_id.trim() === edition.event_id && /^[1-9][0-9]{0,17}$/.test(edition.event_id)
  && slug === `polymarket-event-${edition.event_id}` ? "Polymarket · Event" : null;

function editionLabel(value: unknown, slug: string): string | null {
  const edition = object(value);
  // A family the reader doesn't know fails closed; an absent or null family is
  // an ordinary theme (AI, Oscars), so a server that writes `family: null`
  // everywhere cannot take those pages down.
  if (edition && isTheme(edition) && edition.family != null) return typeof edition.family === "string" && familySections[edition.family] ? departureLabel(edition, slug) : null;
  if (edition?.kind === "provider_event") return providerEventLabel(edition, slug);
  if (edition && isTheme(edition)) return themeLabel(edition, slug);
  if (!edition || !positive(edition.season)) return null;
  if (slug === "midterms-2026" && edition.kind === "midterms" && edition.league === "politics" && edition.season === 2026) return "2026 elections";
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
  const isRoundup = header?.kind === "roundup";
  const title = (state === "published" || state === "empty") && header?.slug === slug && text(header.name) ? header.name : null;
  const base: CollectionHub = { slug, revision: positive(row.revision) ? row.revision : null, state, title,
    edition: editionLabel(row.edition, slug), sections: [], children: [], members: [], related: {}, note: null, theme: null,
    dek: null, family: null };
  if (state !== "published") {
    const notes = { unpublished: "This collection isn't available yet.", withdrawn: "This collection is no longer available.",
      empty: isRoundup ? "There are no markets in this collection right now." : "There are no games or questions in this collection right now.", unavailable: "This collection isn't available right now." };
    return { ...base, note: notes[state] };
  }
  if (!base.revision || (!base.edition && !isRoundup) || !title || !Array.isArray(row.sections)) throw new Error("This collection isn't available right now.");
  let relatedSummary: CollectionHub["relatedSummary"];
  if (row.related_summary != null) {
    const summary = object(row.related_summary);
    if (!summary || !count(summary.count) || !count(summary.unclassified_count) || summary.unclassified_count > summary.count)
      throw new Error("This collection isn't available right now.");
    relatedSummary = { count: summary.count, unclassifiedCount: summary.unclassified_count };
  }
  // A theme page's `member_count` is this page; the whole collection's count is
  // the snapshot's `counts.shown_count`, the same on every page of a revision.
  const counts = object(row.counts), page = object(row.page);
  let theme: CollectionHub["theme"] = null;
  if (isTheme(row.edition)) {
    if (!counts || !count(counts.shown_count) || typeof counts.inventory_complete !== "boolean" || !page || (page.next_cursor !== null && !cursorText(page.next_cursor)))
      throw new Error("This collection isn't available right now.");
    theme = { totalCount: counts.shown_count, nextCursor: page.next_cursor as string | null, inventoryComplete: counts.inventory_complete, revisionMoved: row.revision_moved === true };
  }
  const family = theme && typeof object(row.edition)?.family === "string" ? object(row.edition)!.family as string : null;
  const familyTitles = family ? familySections[family] ?? null : null;
  const titles = theme ? themeSectionTitles[(object(row.edition)?.subject as string)] ?? {} : sectionTitles;
  const seen = new Set<string>();
  let partial = !count(row.member_count) || !count(row.withheld_count) || (row.withheld_count as number) > 0 || (Array.isArray(row.withheld) && row.withheld.length > 0);
  const sections: CollectionSection[] = [];
  row.sections.forEach((value, index) => {
    const section = object(value);
    if (!section || !text(section.class) || !Array.isArray(section.members)) { partial = true; return; }
    const accepted: CollectionMember[] = [];
    section.members.forEach((value) => {
      const card = member(value, family === "departure");
      if (!card) { partial = true; return; }
      if (seen.has(card.key)) return;
      seen.add(card.key); accepted.push(card);
    });
    if (section.count !== section.members.length || accepted.length !== section.members.length) partial = true;
    if (accepted.length) sections.push({ key: `${index}:${section.class}`, cls: section.class,
      title: (slug === "midterms-2026" || isRoundup) && text(section.title) ? section.title : familyTitles?.[section.class as string]?.title ?? titles[section.class] ?? "More",
      note: familyTitles?.[section.class as string]?.note ?? null,
      layout: slug === "midterms-2026" && text(section.layout) ? section.layout : undefined,
      members: accepted });
  });
  const members = sections.flatMap((section) => section.members);
  if (members.length !== row.member_count) partial = true;
  const summarizedCount = members.reduce((total, member) => total + (member.relatedMarketCount ?? 0), 0);
  if (summarizedCount !== (relatedSummary?.count ?? 0)) {
    relatedSummary = undefined;
    partial = true;
  }
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
  const pin = object(row.discover_pin);
  const admittedPin = slug === "midterms-2026" && pin?.slug === slug && pin.href === collectionPath(slug) && text(pin.name) && text(pin.subtitle) && text(pin.pin_until) && Number.isFinite(Date.parse(pin.pin_until)) ? pin as unknown as CollectionPin : null;
  return { ...base, members, related, children, theme, family, relatedSummary, dek: family ? familyDek[family] ?? null : null,
    subtitle: text(row.subtitle) ? row.subtitle : null, pin: admittedPin,
    sections: sections.map((section) => ({ ...section, members: section.members.filter((m) => !relatedKeys.has(m.key)) })).filter((s) => s.members.length > 0),
    note: partial ? (slug === "midterms-2026" || isRoundup ? "Some markets aren't available right now." : "Some games or questions aren't available right now.") : !members.length && !children.length ? "No markets are available right now." : null };
}

function relate(members: CollectionMember[]): Record<string, CollectionMember[]> {
  const related: Record<string, CollectionMember[]> = {};
  for (const event of members.filter((m) => m.type === "event")) {
    const ids = new Set(event.questionIds);
    related[event.key] = members.filter((m) => m.type === "market" && ids.has(m.id) && m.eventId === event.id);
  }
  return related;
}

// #5342: a game's attached markets keep their own served routes on the hub. The
// game page does not draw every one (Week 5's Polymarket "O/U 47.5" is reachable
// only from here), so a game with a short served list names each as a plain
// link, in served order, with no number, count or ranking. #12337 adds the
// shared NFL presentation decision: winners are represented by the game card,
// while secondary contracts keep their direct links in a closed disclosure.
// A longer list stays behind "More on this game" (#10146).
export const RELATED_LINK_LIMIT = 12;
export function relatedMarketLinks(
  hub: CollectionHub,
  gameKey: string,
  presentation: "inline" | "secondary" = "inline",
): CollectionMember[] {
  const related = hub.related[gameKey] ?? [];
  if (related.length > RELATED_LINK_LIMIT) return [];
  return related.filter((member) => (member.linkPresentation ?? "inline") === presentation);
}

export interface CollectionPageRequest { revision: number; cursor: string }
export async function fetchCollection(slug: string, signal?: AbortSignal, page?: CollectionPageRequest): Promise<CollectionHub> {
  if (!safeCollectionSlug(slug)) throw new Error("This collection isn't available right now.");
  // The cursor is opaque and belongs to its revision; both travel together.
  const params = new URLSearchParams();
  if (page) {
    params.set("revision", String(page.revision));
    params.set("cursor", page.cursor);
  }
  if (isNflWeekCollectionSlug(slug)) params.set("compact", "true");
  const query = params.toString();
  const path = `${API_URL}/api/containers/${slug}`;
  const url = query ? `${path}?${query}` : path;
  const response = await fetch(url, { cache: "no-store", signal });
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
export const forgetAcceptedCollections = (): void => { acceptedHubs.clear(); closedBelow.clear(); drawnWeekNavigation.clear(); };
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
  const related = relate(members);
  const relatedKeys = new Set(Object.values(related).flat().map((m) => m.key));
  return {
    ...later,
    members,
    sections: sections.map((s) => ({ ...s, members: s.members.filter((m) => !relatedKeys.has(m.key)) })).filter((s) => s.members.length > 0),
    related,
    note,
    theme: { ...later.theme!, nextCursor },
  };
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
  if (hub.slug === "midterms-2026") return hub.members.some(m => !(m.item.data as FeedFuturesData & { settled_winner?: string }).settled_winner) ? 30000 : 0;
  const games = hub.members.filter((m) => m.type === "event").map((m) => m.item.data as FeedEventData);
  if (games.some((e) => e.status === "live")) return 30000;
  return games.some((e) => ["scheduled", "upcoming"].includes(e.status) && Math.abs(Date.parse(e.commence_time) - now) <= 86400000) ? 60000 : 0;
}

export interface CollectionWeekLink { slug: string; label: string; href: string }
export interface CollectionWeekNavigation { slug: string; state: "available" | "unavailable" | "not_applicable"; previous: CollectionWeekLink | null; next: CollectionWeekLink | null }

// #11567: the week navigation each hub last drew, held in memory like the hub
// itself (#9982). While the next read is in flight (Back, a refresh) the hub
// holds the links' place, so the games below them do not move when they draw.
const drawnWeekNavigation = new Map<string, CollectionWeekNavigation>();
export const lastWeekNavigation = (slug: string): CollectionWeekNavigation | null => drawnWeekNavigation.get(slug) ?? null;
export function rememberWeekNavigation(navigation: CollectionWeekNavigation): void {
  drawnWeekNavigation.delete(navigation.slug);
  drawnWeekNavigation.set(navigation.slug, navigation);
  for (const oldest of drawnWeekNavigation.keys()) { if (drawnWeekNavigation.size <= ACCEPTED_HUB_LIMIT) break; drawnWeekNavigation.delete(oldest); }
}

export function parseCollectionWeekNavigation(value: unknown, slug: string): CollectionWeekNavigation {
  const row = object(value);
  const current = /^nfl-(\d{4})-(preseason-|postseason-)?week-([1-9]\d?)$/.exec(slug);
  if (!row || row.slug !== slug || !current || !["available", "unavailable", "not_applicable"].includes(row.state as string)) throw new Error("Week navigation isn't available right now.");
  const state = row.state as CollectionWeekNavigation["state"];
  const rank = (match: RegExpExecArray) => (match[2] === "preseason-" ? 0 : match[2] === "postseason-" ? 2 : 1) * 100 + Number(match[3]);
  const parseLink = (value: unknown, direction: number): CollectionWeekLink | null => {
    if (value === null) return null;
    const link = object(value), destination = object(link?.destination), edition = object(link?.edition);
    const match = typeof link?.slug === "string" ? /^nfl-(\d{4})-(preseason-|postseason-)?week-([1-9]\d?)$/.exec(link.slug) : null;
    if (!link || !match || match[1] !== current[1] || (rank(match) - rank(current)) * direction <= 0 || !edition || !editionLabel(edition, link.slug as string) || edition.kind !== "nfl_week" || !text(link.label) || !destination || destination.kind !== "container" || destination.slug !== link.slug || destination.api !== `/api/containers/${link.slug}` || destination.web !== collectionPath(link.slug as string)) throw new Error("Week navigation isn't available right now.");
    return { slug: link.slug as string, label: `NFL ${edition.season} · ${edition.stage === "Regular Season" ? "" : `${edition.stage} `}Week ${edition.week}`, href: destination.web as string };
  };
  if (state !== "available") {
    if (row.previous !== null || row.next !== null) throw new Error("Week navigation isn't available right now.");
    return { slug, state, previous: null, next: null };
  }
  return { slug, state, previous: parseLink(row.previous, -1), next: parseLink(row.next, 1) };
}

export async function fetchCollectionWeekNavigation(slug: string, signal?: AbortSignal): Promise<CollectionWeekNavigation> {
  if (!safeCollectionSlug(slug)) throw new Error("Week navigation isn't available right now.");
  const response = await fetch(`${API_URL}/api/containers/${slug}/week-navigation`, { cache: "no-store", signal });
  if (!response.ok) throw new Error("Week navigation isn't available right now.");
  return parseCollectionWeekNavigation(await response.json(), slug);
}

export function activeCollectionPin(hub: CollectionHub | null | undefined, now = Date.now()): CollectionPin | null {
  return hub?.state === "published" && hub.slug === "midterms-2026" && hub.pin && Date.parse(hub.pin.pin_until) > now ? hub.pin : null;
}

/**
 * #10090: a member the page already settled by the official result
 * (`settled_winner`, e.g. a called midterm race). It shows that winner, so it
 * never takes a streamed price: a venue card resolved later carries no
 * `settled_winner` and would turn the winner back into 100% / 0%.
 */
export function servedSettledMember(member: CollectionMember): boolean {
  const winner = (member.item.data as { settled_winner?: string | null } | null)?.settled_winner;
  return typeof winner === "string" && winner.trim() !== "";
}

/**
 * #10090: one member with its card re-priced by the price stream, matched by
 * price key (`event-<id>` / `futures-<id>`). The hub itself is never rewritten:
 * revisions, paging and reading context keep reading the served members.
 * Returns `member` itself when the stream holds nothing newer for it, or when
 * the served card is already settled (`servedSettledMember`).
 */
export function pricedCollectionMember(member: CollectionMember, priced: ReadonlyMap<string, FeedItem>): CollectionMember {
  if (servedSettledMember(member)) return member;
  const key = priceKey(member.item);
  const item = key ? priced.get(key) : undefined;
  return item && item !== member.item ? { ...member, item } : member;
}

