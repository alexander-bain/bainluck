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
 */

let generationSerial = 0;

function stamp<T>(deck: Omit<EditionDeck<T>, "generation">): EditionDeck<T> {
  generationSerial += 1;
  return { ...deck, generation: generationSerial };
}

/** The issue-time context a page-zero reply travels with through SWR. */
export interface OpeningEditionTagged {
  openingRequest?: FeedEditionRequest;
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

  /** A replacement deck from `replace`: take it under a fresh generation. */
  const adopt = useCallback((next: EditionDeck<T>) => {
    legacySessionRef.current = false;
    return hold(stamp(next))!;
  }, [hold]);

  /** A compatible page of the held edition (`accept`): same generation. */
  const extend = useCallback((next: EditionDeck<T>) => hold(next)!, [hold]);

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
  const issuePageZero = useCallback((pinned: boolean): FeedEditionRequest => {
    const held = deckRef.current;
    return { edition: pinned ? held?.edition ?? null : null, offset: 0, generation: held?.generation ?? null };
  }, []);

  /** The next page's context from the held deck's raw cursor, or null when exhausted. */
  const issueNextPage = useCallback((): FeedEditionRequest | null => {
    const held = deckRef.current;
    return held ? nextPageRequest(held) : null;
  }, []);

  const decide = useCallback(
    (request: FeedEditionRequest, payload: unknown, hasRenderedItems: boolean): EditionTransition<T> =>
      decideEditionTransition({ accepted: deckRef.current, request, payload, hasRenderedItems, getId }),
    [getId],
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
    issuePageZero,
    issueNextPage,
    decide,
  };
}
