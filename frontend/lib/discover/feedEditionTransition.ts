/**
 * #5105 / #5102 — what an edition-aware Discover page does with one feed reply.
 *
 * The page pins every later page to the edition page zero painted by sending
 * that page's `edition` token back (`fetchFeed({ edition })`). The server
 * answers with `edition_status`:
 *
 *   • `pinned`      — served in the requested edition's order, current prices.
 *   • `expired` / `superseded` / `invalidated` — the edition is retired and the
 *     CURRENT list was served instead, at the requested offset.
 *
 * 🔴 A RETIRED REPLY AT A NONZERO OFFSET IS PAGE N OF A DIFFERENT LIST. It is
 * never appended: the reader keeps the deck they have and the caller asks for
 * page zero WITHOUT the retired token (`restart`). A retired reply that is
 * already page zero IS the current list's first page, so it replaces the deck
 * directly when it is available — no second fetch.
 *
 * 🔴 A LATE REPLY IS INERT. Every request records the deck generation it was
 * issued against. A reply to an older generation (a page-two request still in
 * flight when page zero replaced the deck) changes nothing — in particular a
 * late retirement can never retire the newer deck.
 *
 * 🔴 FRESH BODIES, SERVER IDENTITY. `foldContinuationPage` is the identity /
 * position / section record and keeps the FIRST body it saw for each card. A
 * pinned page is the same order with live prices, so display data comes from
 * `deck.bodies` (latest body per id), never from `sections.opening` /
 * `sections.continuation`. `deckSections` joins the two.
 *
 * 🔴 THE CURSOR IS THE RAW SERVER OFFSET. `nextOffset` is the end of the
 * accepted server window, before any client filter or dedup; a page the caller
 * hides cards from still advances it by everything the server sent. Restore
 * wiring supplies it back as `{ edition, offset: nextOffset }` via
 * `nextPageRequest`; the snapshot format is not widened here.
 *
 * Availability is `decideFeedPage`'s and is read FIRST: an unavailable reply
 * (which knows nothing, its status included), or a degraded empty one over
 * rendered cards, keeps the deck and its paging. Boundaries, positions
 * and edition binding are `foldContinuationPage`'s; nothing is re-validated
 * here. Every refusal keeps the caller's state exactly as it was.
 *
 * Pure: no I/O, timers, retries, storage or mutation. Not called by any page
 * yet; the legacy paging / reconciliation / restore paths are unchanged.
 */

import type { FeedEditionStatus } from "@/lib/types";
import { decideFeedPage } from "./feedAvailability";
import {
  foldContinuationPage,
  type ContinuationSections,
  type ContinuationUnsupportedReason,
} from "./continuationSections";

export type RetiredEditionStatus = Exclude<FeedEditionStatus, "pinned">;

const RETIRED: ReadonlySet<string> = new Set(["expired", "superseded", "invalidated"]);

/** Read `edition_status` exactly: absent, one of the four, or malformed. */
export function readFeedEditionStatus(raw: unknown): FeedEditionStatus | "absent" | "malformed" {
  if (raw === undefined) return "absent";
  if (raw === "pinned" || (typeof raw === "string" && RETIRED.has(raw))) return raw as FeedEditionStatus;
  return "malformed";
}

/** What the caller sent. Recorded when the request is ISSUED. */
export interface FeedEditionRequest {
  /** The `edition` token sent, or null when none was. */
  edition: string | null;
  /** The raw server offset asked for. */
  offset: number;
  /** `deck.generation` when issued; null when there was no accepted deck. */
  generation: number | null;
}

/** One accepted edition. Never mutated after it is returned. */
export interface EditionDeck<T> {
  /** Bumped on every replacement; requests carry it to detect late replies. */
  readonly generation: number;
  /** The token later pages send. Null only for a legacy (no-section) deck from a server that sent none. */
  readonly edition: string | null;
  /** Identity / position / section record. Its item arrays are first-seen bodies — not display data. */
  readonly sections: ContinuationSections<T>;
  /** Latest body per card id. */
  readonly bodies: ReadonlyMap<string, T>;
  /** End of the accepted raw server window. */
  readonly nextOffset: number;
  readonly hasMore: boolean;
}

export type EditionPreserveReason =
  | "malformed_reply"
  | "stale_request"
  | "unavailable"
  | "degraded_empty"
  | "status_malformed"
  | "status_unrequested"
  | "status_missing"
  | "offset_mismatch"
  | "offset_gap"
  | "token_not_sent"
  | "edition_mismatch"
  | "no_deck"
  | ContinuationUnsupportedReason;

export type EditionTransition<T> =
  /** Keep everything. `showUnavailable` raises the surface's existing retry state. */
  | { kind: "preserve"; reason: EditionPreserveReason; showUnavailable: boolean; hasMore: boolean }
  /** A compatible page of the held edition: swap in `deck`. `items` are this reply's fresh bodies. */
  | { kind: "accept"; deck: EditionDeck<T>; items: readonly T[] }
  /** Page zero of a new edition: replace the deck with it (may be a supported empty deck). */
  | { kind: "replace"; deck: EditionDeck<T>; items: readonly T[] }
  /** The held edition is retired: keep the visible deck and send `request` (page zero, no token). */
  | { kind: "restart"; reason: RetiredEditionStatus; request: FeedEditionRequest };

export interface EditionTransitionInput<T> {
  accepted: EditionDeck<T> | null;
  request: FeedEditionRequest;
  /** The decoded reply, as returned by `fetchFeed` (untrusted). */
  payload: unknown;
  /** Whether cards are on screen (`decideFeedPage`'s input). */
  hasRenderedItems: boolean;
  getId: (item: T) => string;
}

interface Reply<T> {
  items: readonly T[];
  offset: unknown;
  total: unknown;
  edition?: unknown;
  continuation_start?: unknown;
  edition_status?: unknown;
}

function readReply<T>(payload: unknown): Reply<T> | null {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const body = payload as Reply<T>;
  return Array.isArray(body.items) ? body : null;
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function withBodies<T>(prior: ReadonlyMap<string, T> | null, items: readonly T[], getId: (item: T) => string) {
  const bodies = new Map<string, T>(prior ?? []);
  for (const item of items) bodies.set(getId(item), item);
  return bodies;
}

function replaceFromPageZero<T>(
  input: EditionTransitionInput<T>,
  reply: Reply<T>,
  hasMore: boolean,
): EditionTransition<T> {
  const { accepted, getId } = input;
  const result = foldContinuationPage(null, reply, getId);
  if (result.status !== "ok") return preserve(input, result.reason);
  // A section deck is bound by its edition; without one a later page could
  // never prove it shares the boundary, so it is not accepted as one.
  if (result.sections.boundary !== null && result.sections.edition === null) {
    return preserve(input, "edition_missing");
  }
  const end = reply.items.length;
  return {
    kind: "replace",
    deck: {
      generation: (accepted?.generation ?? 0) + 1,
      edition: result.sections.edition,
      sections: result.sections,
      bodies: withBodies(null, reply.items, getId),
      nextOffset: end,
      // An empty page cannot advance the cursor, so it cannot promise more.
      hasMore: hasMore && end > 0,
    },
    items: reply.items,
  };
}

function preserve<T>(
  input: EditionTransitionInput<T>,
  reason: EditionPreserveReason,
  showUnavailable = false,
): EditionTransition<T> {
  return { kind: "preserve", reason, showUnavailable, hasMore: input.accepted?.hasMore ?? false };
}

/**
 * Decide one reply. The caller applies the result and nothing else: `accept`
 * and `replace` swap in `deck`, `restart` issues `request`, `preserve` changes
 * nothing.
 */
export function decideEditionTransition<T>(input: EditionTransitionInput<T>): EditionTransition<T> {
  const { accepted, request, getId } = input;
  const reply = readReply<T>(input.payload);
  if (!reply) return preserve(input, "malformed_reply");

  if (request.generation !== (accepted?.generation ?? null)) return preserve(input, "stale_request");
  if (accepted && request.edition !== null && request.edition !== accepted.edition) {
    return preserve(input, "stale_request");
  }

  const page = decideFeedPage({
    payload: input.payload,
    previousHasMore: accepted?.hasMore ?? false,
    hasRenderedItems: input.hasRenderedItems,
  });
  if (!page.acceptItems) {
    return preserve(input, page.showUnavailable ? "unavailable" : "degraded_empty", page.showUnavailable);
  }

  if (!isNonNegativeInteger(reply.offset)) return preserve(input, "invalid_page");
  const status = readFeedEditionStatus(reply.edition_status);
  if (status === "malformed") return preserve(input, "status_malformed");
  if (request.edition === null && status !== "absent") return preserve(input, "status_unrequested");
  if (request.edition !== null && status === "absent") return preserve(input, "status_missing");

  if (status !== "absent" && status !== "pinned") {
    if (request.offset !== 0 || reply.offset !== 0) {
      return {
        kind: "restart",
        reason: status,
        request: { edition: null, offset: 0, generation: accepted?.generation ?? null },
      };
    }
    return replaceFromPageZero(input, reply, page.hasMore);
  }

  if (reply.offset !== request.offset) return preserve(input, "offset_mismatch");

  if (status === "pinned" && reply.edition !== request.edition) return preserve(input, "edition_mismatch");
  if (status === "absent" && request.offset === 0) return replaceFromPageZero(input, reply, page.hasMore);

  if (!accepted) return request.offset === 0 ? replaceFromPageZero(input, reply, page.hasMore) : preserve(input, "no_deck");
  // A deck that has a token is only extended by pages that sent it.
  if (status === "absent" && accepted.edition !== null) return preserve(input, "token_not_sent");
  if (reply.offset > accepted.nextOffset) return preserve(input, "offset_gap");

  const result = foldContinuationPage(accepted.sections, reply, getId);
  if (result.status !== "ok") return preserve(input, result.reason);
  const end = reply.offset + reply.items.length;
  const extendsWindow = end > accepted.nextOffset;
  const askedFrontier = reply.offset === accepted.nextOffset;
  return {
    kind: "accept",
    deck: {
      generation: accepted.generation,
      edition: accepted.edition,
      sections: result.sections,
      bodies: withBodies(accepted.bodies, reply.items, getId),
      nextOffset: Math.max(accepted.nextOffset, end),
      // Only a page that extends the window speaks for what follows it. An
      // older or repeated window holds the deck's answer; an empty reply to the
      // next window ends paging rather than re-asking that window forever.
      hasMore: extendsWindow ? page.hasMore : askedFrontier ? false : accepted.hasMore,
    },
    items: reply.items,
  };
}

/** The next page's request, or null when the deck is exhausted. */
export function nextPageRequest(deck: EditionDeck<unknown>): FeedEditionRequest | null {
  if (!deck.hasMore) return null;
  return { edition: deck.edition, offset: deck.nextOffset, generation: deck.generation };
}

/** The deck's sections in server order, with each card's LATEST body. */
export function deckSections<T>(deck: EditionDeck<T>, getId: (item: T) => string) {
  const fresh = (item: T) => deck.bodies.get(getId(item)) ?? item;
  return {
    boundary: deck.sections.boundary,
    opening: deck.sections.opening.map(fresh),
    continuation: deck.sections.continuation.map(fresh),
  };
}
