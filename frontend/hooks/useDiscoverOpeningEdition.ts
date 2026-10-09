"use client";

import { useCallback, useRef, useState } from "react";
import {
  decideEditionTransition,
  nextPageRequest,
  type EditionDeck,
  type EditionTransition,
  type FeedEditionRequest,
} from "@/lib/discover/feedEditionTransition";
import type { ContinuationSections } from "@/lib/discover/continuationSections";

/**
 * #5105 — the Discover page's accepted edition, held for the page.
 *
 * Only reached while `DISCOVER_OPENING_EDITION_ENABLED` is on. Owns the one
 * `EditionDeck` the page pins to and the bookkeeping around it; every decision
 * about a reply is `decideEditionTransition`'s, and every card the page shows
 * still lives in the page's own `page1Items` / `allItems` state.
 *
 * 🔴 A REQUEST'S CONTEXT IS TAKEN WHEN IT IS ISSUED. `issue()` reads the deck
 * held at that moment, and the caller carries the result with the reply — the
 * SWR value included. Stamping a reply with the deck held when it is CONSUMED
 * would bless a late or cached reply as current.
 *
 * 🔴 GENERATIONS ARE UNIQUE FOR THE DOCUMENT, NOT THE MOUNT. SWR's cache
 * outlives a client-side navigation, so a reply issued by an earlier mount can
 * be the first value a later mount sees. Every adopted deck (a replacement or a
 * restore) takes the next value of one module-wide serial, so no reply issued
 * against an earlier deck — in this mount or another — can match the deck held
 * now.
 *
 * 🔴 A REQUEST IS OWNED BY THE MOUNT THAT ISSUED IT, BEFORE ANY DECK EXISTS.
 * A generation only fences replies once a deck is held: every cold request —
 * this mount's or an earlier one's — carries `generation: null`, so an earlier
 * mount's cold reply still in SWR's cache would be accepted as this mount's
 * first deck, and this mount's own reply then refused as stale. Each mount
 * takes one module-wide `owner` serial and stamps it on every request it
 * issues; `decide` refuses any reply whose request another mount (or no mount)
 * owns, whatever its generation. `owns` is the same test for the failure side:
 * a rejected request that is no longer current is as inert as a late reply.
 *
 * 🔴 UNSECTIONED EDITIONS RECORD POSITIONS HERE. `foldContinuationPage`
 * records server positions only for a section deck, but a tokened deck
 * without a continuation still needs them to survive Back with its token and
 * raw cursor (`feedRestore`'s retained frontier). `adopt` and `extend` record
 * each received card's first-seen raw position on such a deck; the fold
 * carries them forward like any other recorded position. A section deck and
 * an untokened deck are untouched.
 */

let generationSerial = 0;
let ownerSerial = 0;

function stamp<T>(deck: Omit<EditionDeck<T>, "generation">): EditionDeck<T> {
  generationSerial += 1;
  return { ...deck, generation: generationSerial };
}

/** A request with the mount that issued it. */
export interface OwnedEditionRequest extends FeedEditionRequest {
  readonly owner: number;
}

type RestartTransition<T> = Extract<EditionTransition<T>, { kind: "restart" }>;

/** `EditionTransition`, with a restart's request owned by the deciding mount. */
export type OwnedEditionTransition<T> =
  | Exclude<EditionTransition<T>, { kind: "restart" }>
  | (Omit<RestartTransition<T>, "request"> & { request: OwnedEditionRequest });

/** The issue-time context a page-zero reply travels with through SWR. */
export interface OpeningEditionTagged {
  openingRequest?: OwnedEditionRequest;
}

/** Record first-seen raw positions on a tokened deck without a section. */
function withUnsectionedPositions<T>(
  deck: EditionDeck<T>,
  offset: number,
  items: readonly T[],
  getId: (item: T) => string,
): EditionDeck<T> {
  if (deck.sections.boundary !== null || deck.edition === null) return deck;
  const positions = new Map(deck.sections.positions);
  items.forEach((item, index) => {
    const id = getId(item);
    if (!positions.has(id)) positions.set(id, offset + index);
  });
  return { ...deck, sections: { ...deck.sections, positions } };
}

export interface RestoredSectionEdition<T> {
  page1: readonly T[];
  rest: readonly T[];
  sections: ContinuationSections<T>;
  /** The raw server offset to resume from (`feedRestore`'s retained frontier). */
  cursor: number;
  hasMore: boolean;
}

export function useDiscoverOpeningEdition<T>(getId: (item: T) => string) {
  const [owner] = useState(() => {
    ownerSerial += 1;
    return ownerSerial;
  });
  const deckRef = useRef<EditionDeck<T> | null>(null);
  const [deck, setDeck] = useState<EditionDeck<T> | null>(null);
  // A session restored from a legacy (v2) snapshot holds no edition token, so
  // nothing it requests can be pinned. It stays on the legacy handlers until it
  // opens a new edition (a manual refresh).
  const legacySessionRef = useRef(false);
  // The generation a page-zero replacement is in flight for, or null.
  const replacingRef = useRef<number | null>(null);

  const hold = useCallback((next: EditionDeck<T> | null) => {
    deckRef.current = next;
    setDeck(next);
    return next;
  }, []);

  /** A replacement deck from `replace` (page zero, `items` as received): take it under a fresh generation. */
  const adopt = useCallback((next: EditionDeck<T>, items: readonly T[]) => {
    legacySessionRef.current = false;
    return hold(stamp(withUnsectionedPositions(next, 0, items, getId)))!;
  }, [getId, hold]);

  /** A compatible page of the held edition (`accept`, the reply at `offset`): same generation. */
  const extend = useCallback(
    (next: EditionDeck<T>, offset: number, items: readonly T[]) =>
      hold(withUnsectionedPositions(next, offset, items, getId))!,
    [getId, hold],
  );

  const clear = useCallback(() => {
    legacySessionRef.current = false;
    replacingRef.current = null;
    hold(null);
  }, [hold]);

  /** Rebuild the accepted deck from a validated section snapshot. */
  const restore = useCallback((stored: RestoredSectionEdition<T>) => {
    legacySessionRef.current = false;
    const bodies = new Map<string, T>();
    for (const item of [...stored.page1, ...stored.rest]) bodies.set(getId(item), item);
    return hold(stamp({
      edition: stored.sections.edition,
      sections: stored.sections,
      bodies,
      nextOffset: stored.cursor,
      hasMore: stored.hasMore,
    }))!;
  }, [getId, hold]);

  const restoreLegacy = useCallback(() => {
    hold(null);
    legacySessionRef.current = true;
  }, [hold]);

  /**
   * The context of a page-zero request issued now. `pinned` sends the held
   * edition's token (a background refresh); unpinned asks for the current list
   * (a manual refresh or a restart).
   */
  const issuePageZero = useCallback((pinned: boolean): OwnedEditionRequest => {
    const held = deckRef.current;
    return { edition: pinned ? held?.edition ?? null : null, offset: 0, generation: held?.generation ?? null, owner };
  }, [owner]);

  /** The next page's context from the held deck's raw cursor, or null when exhausted. */
  const issueNextPage = useCallback((): OwnedEditionRequest | null => {
    const held = deckRef.current;
    const request = held ? nextPageRequest(held) : null;
    return request ? { ...request, owner } : null;
  }, [owner]);

  /** Whether a request is still this mount's current one: issued here, against the deck held now. */
  const owns = useCallback(
    (request: OwnedEditionRequest) =>
      request.owner === owner && request.generation === (deckRef.current?.generation ?? null),
    [owner],
  );

  const decide = useCallback(
    (request: OwnedEditionRequest, payload: unknown, hasRenderedItems: boolean): OwnedEditionTransition<T> => {
      const accepted = deckRef.current;
      // Another mount's request — or one carrying no owner at all — is never this mount's reply.
      if (request?.owner !== owner) {
        return { kind: "preserve", reason: "stale_request", showUnavailable: false, hasMore: accepted?.hasMore ?? false };
      }
      const transition = decideEditionTransition({ accepted, request, payload, hasRenderedItems, getId });
      // A restart is issued by this mount, now.
      return transition.kind === "restart" ? { ...transition, request: { ...transition.request, owner } } : transition;
    },
    [getId, owner],
  );

  return {
    deck,
    deckRef,
    legacySessionRef,
    replacingRef,
    adopt,
    extend,
    clear,
    restore,
    restoreLegacy,
    owner,
    issuePageZero,
    issueNextPage,
    owns,
    decide,
  };
}
